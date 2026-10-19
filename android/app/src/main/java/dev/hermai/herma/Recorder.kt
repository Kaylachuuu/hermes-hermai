package dev.hermai.herma

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Records 16 kHz mono speech while held, and hands it back as a WAV file. */
class Recorder {
    private var record: AudioRecord? = null
    private var thread: Thread? = null
    private val pcm = ByteArrayOutputStream()

    @SuppressLint("MissingPermission") // asked for before the first recording
    fun start() {
        if (record != null) return
        pcm.reset()
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val r = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, RATE, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT, maxOf(min, RATE))
        record = r
        r.startRecording()
        thread = Thread {
            val buf = ByteArray(4096)
            while (record === r) {
                val n = r.read(buf, 0, buf.size)
                if (n > 0) synchronized(pcm) { pcm.write(buf, 0, n) }
            }
        }.also { it.start() }
    }

    /** Stops and returns the recording as WAV, or null when it was too short to be speech. */
    fun stop(): ByteArray? {
        val r = record ?: return null
        record = null
        thread?.join(500)
        thread = null
        r.stop()
        r.release()
        val data = synchronized(pcm) { pcm.toByteArray() }
        if (data.size < RATE * 2 * MIN_MS / 1000) return null
        return wav(data)
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
        const val MIN_MS = 300
    }
}
