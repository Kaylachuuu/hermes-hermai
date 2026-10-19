package dev.hermai.herma

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.media.MediaPlayer
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

/** The herma's one screen: the room's name, a big button held to talk, and what Athena said. */
class MainActivity : Activity() {
    private lateinit var herma: Herma
    private lateinit var hermes: Hermes
    private val recorder = Recorder()
    private val work = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private var player: MediaPlayer? = null
    private var state = State.READY

    private lateinit var roomView: TextView
    private lateinit var talk: Button
    private lateinit var statusView: TextView
    private lateinit var heardView: TextView
    private lateinit var replyView: TextView

    enum class State(val label: String, val colour: Int) {
        READY("Hold to talk", 0xFF1F2A44.toInt()),
        LISTENING("Listening…", 0xFFB3412E.toInt()),
        THINKING("Thinking…", 0xFF6B5B95.toInt()),
        SPEAKING("Speaking · tap to stop", 0xFF2E7D5B.toInt()),
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        herma = Herma(this)
        hermes = Hermes(herma)
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
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
        }
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
        if (state == State.LISTENING) { recorder.stop(); show(State.READY) }
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
            text = "Athena · hold the room name for settings"
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
            else -> {}
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
            return
        }
        try {
            recorder.start()
            show(State.LISTENING)
            status("")
        } catch (e: Exception) {
            status("The microphone isn't available (${e.message})")
        }
    }

    private fun release() {
        if (state != State.LISTENING) return
        val wav = recorder.stop()
        if (wav == null) { show(State.READY); return }
        show(State.THINKING)
        work.execute {
            try {
                val r = hermes.voice(wav)
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

    private fun show(s: State) {
        state = s
        talk.text = s.label
        talk.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(s.colour); setStroke(dp(3), 0xFFE8C46A.toInt()) }
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
        player?.release()
        work.shutdownNow()
        super.onDestroy()
    }
}
