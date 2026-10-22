package dev.hermai.herma

import android.annotation.SuppressLint
import android.content.res.AssetManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.KeywordSpotter
import com.k2fsa.sherpa.onnx.KeywordSpotterConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Listens on the tablet itself for "Hey Athena" (sherpa-onnx keyword spotting, nothing leaves the
 * tablet), then records what's said after it until the speaker stops, and hands that over as WAV.
 * The recording starts a little before the wake word, so Hermai can hear it too and check it.
 *
 * It stops itself after each recording; [start] it again once the reply has been spoken.
 */
class WakeListener(private val assets: AssetManager, private val events: Events) {
    interface Events {
        fun onWake()
        fun onUtterance(wav: ByteArray)
        fun onNothingSaid()
        fun onProblem(message: String)
    }

    @Volatile private var running = false
    private var thread: Thread? = null
    private var spotter: KeywordSpotter? = null

    val listening: Boolean get() = running

    fun start() {
        if (running) return
        thread?.join(1000) // the last round may still be letting go of the microphone
        running = true
        thread = Thread({ loop() }, "hey-athena").also { it.start() }
    }

    /** Stops listening and frees the microphone, so the talk button can use it. */
    fun stop() {
        running = false
        thread?.join(1000)
        thread = null
    }

    fun release() {
        stop()
        spotter?.release()
        spotter = null
    }

    private fun spotter(): KeywordSpotter = spotter ?: KeywordSpotter(
        assets,
        KeywordSpotterConfig(
            featConfig = FeatureConfig(sampleRate = RATE, featureDim = 80),
            modelConfig = OnlineModelConfig(
                transducer = OnlineTransducerModelConfig(
                    encoder = "kws/encoder.onnx", decoder = "kws/decoder.onnx", joiner = "kws/joiner.onnx"),
                tokens = "kws/tokens.txt",
                numThreads = 1,
                provider = "cpu",
            ),
            keywordsFile = "kws/keywords.txt",
            keywordsScore = KEYWORDS_SCORE,
            keywordsThreshold = KEYWORDS_THRESHOLD,
            numTrailingBlanks = 1,
        ),
    ).also { spotter = it }

    @SuppressLint("MissingPermission") // started only once the microphone is allowed
    private fun loop() {
        val kws = try { spotter() } catch (e: Throwable) {
            running = false
            events.onProblem("\"Hey Athena\" isn't available (${e.message ?: e.javaClass.simpleName})")
            return
        }
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = try {
            AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, RATE, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, max(min, RATE)).also { it.startRecording() }
        } catch (e: Exception) {
            running = false
            events.onProblem("The microphone isn't available (${e.message})")
            return
        }
        val stream = kws.createStream()
        val chunk = ShortArray(CHUNK)
        val floats = FloatArray(CHUNK)
        val preroll = ShortArray(PREROLL)  // the last two seconds, round and round
        var prerollAt = 0
        var prerollFull = false
        var floor = 0.0           // the room's quiet level, learned while waiting
        var capture: ByteArrayOutputStream? = null
        var chunks = 0            // chunks since the wake word
        var spoke = false
        var quiet = 0             // chunks of quiet since they last spoke
        try {
            while (running) {
                val n = record.read(chunk, 0, CHUNK)
                if (n <= 0) continue
                var sum = 0.0
                for (i in 0 until n) { floats[i] = chunk[i] / 32768f; sum += floats[i] * floats[i] }
                val level = sqrt(sum / n)

                val heard = capture
                if (heard == null) {
                    floor = if (floor == 0.0) level else if (level < floor * 2) floor * 0.95 + level * 0.05 else floor
                    for (i in 0 until n) { preroll[prerollAt] = chunk[i]; prerollAt = (prerollAt + 1) % PREROLL }
                    if (prerollAt < n) prerollFull = true
                    stream.acceptWaveform(if (n == CHUNK) floats else floats.copyOf(n), RATE)
                    while (kws.isReady(stream)) kws.decode(stream)
                    if (kws.getResult(stream).keyword.isNotEmpty()) {
                        kws.reset(stream)
                        capture = ByteArrayOutputStream().also { out ->
                            if (prerollFull) write(out, preroll, prerollAt, PREROLL - prerollAt)
                            write(out, preroll, 0, prerollAt)
                        }
                        chunks = 0; spoke = false; quiet = 0
                        events.onWake()
                    }
                    continue
                }

                write(heard, chunk, 0, n)
                chunks++
                if (level > max(floor * SPEECH_OVER_FLOOR, MIN_SPEECH_LEVEL)) { spoke = true; quiet = 0 } else quiet++
                val done = (spoke && quiet >= END_QUIET_CHUNKS) || chunks >= MAX_CHUNKS
                if (!spoke && chunks >= WAIT_CHUNKS) {
                    events.onNothingSaid()
                    capture = null
                    prerollAt = 0; prerollFull = false
                } else if (done) {
                    running = false
                    events.onUtterance(wav(heard.toByteArray()))
                }
            }
        } finally {
            stream.release()
            record.stop()
            record.release()
        }
    }

    private fun write(out: ByteArrayOutputStream, samples: ShortArray, from: Int, count: Int) {
        val bytes = ByteBuffer.allocate(count * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (i in from until from + count) bytes.putShort(samples[i])
        out.write(bytes.array(), 0, count * 2)
    }

    private fun wav(data: ByteArray): ByteArray {
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray()); putInt(36 + data.size); put("WAVE".toByteArray())
            put("fmt ".toByteArray()); putInt(16); putShort(1); putShort(1)
            putInt(RATE); putInt(RATE * 2); putShort(2); putShort(16)
            put("data".toByteArray()); putInt(data.size)
        }
        return header.array() + data
    }

    companion object {
        const val RATE = 16_000
        const val CHUNK = RATE / 10                  // 100 ms
        const val PREROLL = RATE * 2                 // kept from before the wake word
        const val WAIT_CHUNKS = 50                   // 5 s for them to start talking after it
        const val END_QUIET_CHUNKS = 9               // 0.9 s of quiet ends what they're saying
        const val MAX_CHUNKS = 150                   // 15 s at most
        const val SPEECH_OVER_FLOOR = 3.0
        const val MIN_SPEECH_LEVEL = 0.01
        // Lenient on purpose: Hermai checks the recording for "Athena" before anything reaches her.
        const val KEYWORDS_SCORE = 3.0f
        const val KEYWORDS_THRESHOLD = 0.05f
    }
}
