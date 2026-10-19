package dev.hermai.herma

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.KeyEvent
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.util.concurrent.Executors

/** Setting up a herma: where Hermes is, a dashboard sign-in, the room, and the talk key. */
class SetupActivity : Activity() {
    private lateinit var herma: Herma
    private val work = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private var capturing = false

    private lateinit var server: EditText
    private lateinit var username: EditText
    private lateinit var password: EditText
    private lateinit var room: EditText
    private lateinit var keyView: TextView
    private lateinit var message: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        herma = Herma(this)
        val pad = dp(24)
        fun label(t: String) = TextView(this).apply { text = t; textSize = 15f; setTextColor(0xFF9AA3B5.toInt()); setPadding(0, dp(16), 0, dp(4)) }
        fun field(value: String, hint: String, type: Int) = EditText(this).apply {
            setText(value); this.hint = hint; inputType = type; textSize = 20f
            setTextColor(Color.WHITE); setHintTextColor(0xFF5D6577.toInt()); setSingleLine()
        }
        server = field(herma.server, "http://athena.local:9119", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI)
        username = field(herma.username, "Dashboard username", InputType.TYPE_CLASS_TEXT)
        password = field("", if (herma.refreshToken.isEmpty()) "Dashboard password" else "Signed in; leave empty to keep it",
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        room = field(herma.room, "Kitchen, Living room…", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS)
        keyView = TextView(this).apply { textSize = 16f; setTextColor(Color.WHITE) }
        message = TextView(this).apply { textSize = 16f; setTextColor(0xFFE8C46A.toInt()); setPadding(0, dp(16), 0, 0) }
        showKey()

        val save = Button(this).apply { text = "Save and sign in"; isAllCaps = false; textSize = 18f; setOnClickListener { save() } }
        val setKey = Button(this).apply {
            text = "Set talk key"; isAllCaps = false
            setOnClickListener { capturing = true; keyView.text = "Press the side key now…" }
        }
        val clearKey = Button(this).apply {
            text = "No talk key"; isAllCaps = false
            setOnClickListener { capturing = false; herma.talkKey = 0; showKey() }
        }
        val keys = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; addView(setKey); addView(clearKey) }

        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            addView(TextView(this@SetupActivity).apply { text = "Hermai"; textSize = 32f; setTextColor(Color.WHITE); gravity = Gravity.START })
            addView(TextView(this@SetupActivity).apply {
                text = "This tablet is a herma: Athena's voice in one room. It's ${herma.id} to Hermes."
                textSize = 15f; setTextColor(0xFF9AA3B5.toInt())
            })
            addView(label("Hermes dashboard address")); addView(server)
            addView(label("Username")); addView(username)
            addView(label("Password")); addView(password)
            addView(label("Room")); addView(room)
            addView(label("Talk key (held like the on-screen button)")); addView(keyView); addView(keys)
            addView(save, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(24) })
            addView(message)
        }
        setContentView(ScrollView(this).apply { setBackgroundColor(0xFF0F1626.toInt()); addView(column) })
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (capturing && keyCode != KeyEvent.KEYCODE_BACK) {
            capturing = false
            herma.talkKey = keyCode
            showKey()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    @Deprecated("Activity's own back handling")
    override fun onBackPressed() {
        if (herma.ready) super.onBackPressed() else finishAffinity() // nothing to go back to yet
    }

    private fun showKey() {
        val k = herma.talkKey
        keyView.text = if (k == 0) "None; use the on-screen button" else "${KeyEvent.keyCodeToString(k)} ($k)"
    }

    private fun save() {
        val s = server.text.toString().trim()
        val u = username.text.toString().trim()
        val p = password.text.toString()
        val r = room.text.toString().trim().replace(Regex("\\s+"), " ")
        if (s.isEmpty() || r.isEmpty()) { message.text = "The address and the room are both needed."; return }
        val sameServer = Hermes.normalise(s) == herma.server && u == herma.username
        if (p.isEmpty() && !(sameServer && herma.refreshToken.isNotEmpty())) { message.text = "Enter the password to sign in."; return }
        message.text = "Signing in…"
        work.execute {
            try {
                val hermes = Hermes(herma)
                if (p.isNotEmpty()) hermes.signIn(s, u, p)
                herma.room = r
                hermes.hello()
                main.post { finish() }
            } catch (e: Exception) {
                main.post { message.text = e.message ?: e.javaClass.simpleName }
            }
        }
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        work.shutdownNow()
        super.onDestroy()
    }
}
