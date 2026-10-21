package dev.hermai.herma

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.ToneGenerator
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File
import java.util.concurrent.Executors

/** The herma's one screen: the room's name, a big button held to talk, and what Athena said.
 *  With "Hey Athena" on, it also listens for that, on the tablet, whenever it's ready. */
class MainActivity : Activity(), WakeListener.Events {
    private lateinit var herma: Herma
    private lateinit var hermes: Hermes
    private val recorder = Recorder()
    private val work = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private var player: MediaPlayer? = null
    private var state = State.READY
    private lateinit var wake: WakeListener
    private var paused = true

    private lateinit var roomView: TextView
    private lateinit var talk: Button
    private lateinit var statusView: TextView
    private lateinit var heardView: TextView
    private lateinit var replyView: TextView

    enum class State(val label: String, val colour: Int) {
        READY("Hold to talk", 0xFF1F2A44.toInt()),
        WAITING("“Hey Athena”\nor hold to talk", 0xFF1F2A44.toInt()),
        LISTENING("Listening…", 0xFFB3412E.toInt()),
        THINKING("Thinking…", 0xFF6B5B95.toInt()),
        SPEAKING("Speaking · tap to stop", 0xFF2E7D5B.toInt()),
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        herma = Herma(this)
        hermes = Hermes(herma)
        wake = WakeListener(assets, this)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) // a wall tablet stays awake
        buildScreen()
    }

    override fun onResume() {
        super.onResume()
        if (!herma.ready) {
            startActivity(Intent(this, SetupActivity::class.java))
            return
        }
        roomView.text = herma.room
        paused = false
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
        }
        if (state == State.READY || state == State.WAITING) show(State.READY)
        status("Connecting…")
        work.execute {
            try {
                hermes.hello()
                main.post { status("") }
            } catch (e: Exception) {
                main.post { status(problem(e)) }
            }
        }
    }

    override fun onPause() {
        super.onPause()
        paused = true
        wake.stop()
        if (state == State.LISTENING) { recorder.stop(); show(State.READY) }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (state == State.READY || state == State.WAITING) show(State.READY)
    }

    // --- "Hey Athena" ---

    /** Listens for the wake word when this herma is idle, it's turned on and the mic is allowed. */
    private fun listen() {
        if (paused || !herma.wakeWord || !herma.ready || wake.listening) return
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) return
        wake.start()
    }

    override fun onWake() {
        main.post {
            if (state == State.WAITING) { chime(); show(State.LISTENING); status("") }
        }
    }

    override fun onUtterance(wav: ByteArray) {
        main.post { send(wav, woke = true) }
    }

    override fun onNothingSaid() {
        main.post { if (state == State.LISTENING && !recorder.recording) show(State.WAITING) }
    }

    override fun onProblem(message: String) {
        main.post { status(message); show(State.READY, andListen = false) }
    }

    private fun chime() {
        try {
            val tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 70)
            tone.startTone(ToneGenerator.TONE_PROP_ACK, 150)
            main.postDelayed({ tone.release() }, 400)
        } catch (e: RuntimeException) { /* no tone, still listening */ }
    }

    private fun buildScreen() {
        val pad = dp(24)
        roomView = TextView(this).apply {
            textSize = 34f
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setOnLongClickListener { startActivity(Intent(this@MainActivity, SetupActivity::class.java)); true }
        }
        val hint = TextView(this).apply {
            text = "Athena"
            textSize = 14f
            setTextColor(0xFF9AA3B5.toInt())
            gravity = Gravity.CENTER
        }
        talk = Button(this).apply {
            textSize = 26f
            setTextColor(Color.WHITE)
            isAllCaps = false
            setOnTouchListener { _, ev ->
                when (ev.actionMasked) {
                    MotionEvent.ACTION_DOWN -> press()
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> release()
                }
                true
            }
        }
        statusView = TextView(this).apply { textSize = 16f; setTextColor(0xFFE8C46A.toInt()); gravity = Gravity.CENTER }
        heardView = TextView(this).apply { textSize = 18f; setTextColor(0xFF9AA3B5.toInt()); gravity = Gravity.CENTER }
        replyView = TextView(this).apply { textSize = 24f; setTextColor(Color.WHITE); gravity = Gravity.CENTER }

        val settings = TextView(this).apply {
            text = "⚙  Settings"
            textSize = 16f
            setTextColor(0xFF9AA3B5.toInt())
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(12), dp(16), dp(12))
            setOnClickListener { startActivity(Intent(this@MainActivity, SetupActivity::class.java)) }
        }

        val size = dp(260)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(pad, pad, pad, pad)
            setBackgroundColor(0xFF0F1626.toInt())
            addView(roomView)
            addView(hint)
            addView(talk, LinearLayout.LayoutParams(size, size).apply { topMargin = dp(32); bottomMargin = dp(16) })
            addView(statusView)
            addView(heardView, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(16) })
            addView(replyView, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
            addView(settings, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(24) })
        }
        setContentView(column)
        show(State.READY)
    }

    // A held side key works like the on-screen button.
    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (herma.talkKey != 0 && keyCode == herma.talkKey) {
            if (event.repeatCount == 0) press()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean {
        if (herma.talkKey != 0 && keyCode == herma.talkKey) { release(); return true }
        return super.onKeyUp(keyCode, event)
    }

    private fun press() {
        when (state) {
            State.SPEAKING -> { stopSpeaking(); return }
            State.THINKING -> return
            State.LISTENING -> return // already listening after "Hey Athena"
            else -> {}
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
            return
        }
        wake.stop() // the talk button takes the microphone
        try {
            recorder.start()
            show(State.LISTENING)
            status("")
        } catch (e: Exception) {
            status("The microphone isn't available (${e.message})")
        }
    }

    private fun release() {
        if (state != State.LISTENING || !recorder.recording) return
        val wav = recorder.stop()
        if (wav == null) { show(State.READY); return }
        send(wav, woke = false)
    }

    private fun send(wav: ByteArray, woke: Boolean) {
        show(State.THINKING)
        work.execute {
            try {
                val r = hermes.voice(wav, woke)
                if (r.ignored) { main.post { show(State.READY) }; return@execute }
                val audio = r.audio?.let { hermes.audio(it) }
                main.post {
                    heardView.text = if (r.heard.isEmpty()) "" else "“${r.heard}”"
                    replyView.text = r.reply
                    if (r.heard.isEmpty()) status("I didn't catch that.")
                    r.speechError?.let { status("Couldn't speak the reply: $it") }
                    if (audio != null) play(audio) else show(State.READY)
                }
            } catch (e: Exception) {
                main.post { status(problem(e)); show(State.READY) }
            }
        }
    }

    private fun play(wav: ByteArray) {
        val file = File(cacheDir, "reply.wav").apply { writeBytes(wav) }
        stopSpeaking()
        try {
            player = MediaPlayer().apply {
                setDataSource(file.path)
                setOnCompletionListener { stopSpeaking() }
                prepare()
                start()
            }
            show(State.SPEAKING)
        } catch (e: Exception) {
            status("Couldn't play the reply (${e.message})")
            show(State.READY)
        }
    }

    private fun stopSpeaking() {
        player?.release()
        player = null
        if (state == State.SPEAKING) show(State.READY)
    }

    /** Shows a state. READY becomes WAITING while "Hey Athena" is being listened for. */
    private fun show(s: State, andListen: Boolean = true) {
        var shown = s
        if (s == State.READY && andListen) {
            listen()
            if (wake.listening) shown = State.WAITING
        }
        state = shown
        talk.text = shown.label
        talk.textSize = if (shown == State.WAITING) 22f else 26f
        talk.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(shown.colour); setStroke(dp(3), 0xFFE8C46A.toInt()) }
    }

    private fun status(text: String) { statusView.text = text }

    private fun problem(e: Exception): String = when (e) {
        is SignedOut -> e.message ?: "Signed out"
        is HermesError -> e.message ?: "Hermes had a problem"
        is java.net.ConnectException, is java.net.SocketTimeoutException, is java.net.UnknownHostException ->
            "Can't reach Hermes at ${herma.server}. Is this tablet on the home network?"
        else -> "Something went wrong: ${e.message ?: e.javaClass.simpleName}"
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        wake.release()
        player?.release()
        work.shutdownNow()
        super.onDestroy()
    }
}
