package dev.hermai.herma

import android.content.Context
import android.content.SharedPreferences
import java.util.UUID

/** What this tablet remembers: its server, its sign-in, its room and its talk key. */
class Herma(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("herma", Context.MODE_PRIVATE)

    var server: String
        get() = prefs.getString("server", "") ?: ""
        set(v) = prefs.edit().putString("server", v).apply()
    var username: String
        get() = prefs.getString("username", "") ?: ""
        set(v) = prefs.edit().putString("username", v).apply()
    var room: String
        get() = prefs.getString("room", "") ?: ""
        set(v) = prefs.edit().putString("room", v).apply()
    var accessToken: String
        get() = prefs.getString("access", "") ?: ""
        set(v) = prefs.edit().putString("access", v).apply()
    var refreshToken: String
        get() = prefs.getString("refresh", "") ?: ""
        set(v) = prefs.edit().putString("refresh", v).apply()
    var provider: String
        get() = prefs.getString("provider", "") ?: ""
        set(v) = prefs.edit().putString("provider", v).apply()

    /** The hardware key held to talk, such as the Tab Active3's side key; 0 when none is set. */
    var talkKey: Int
        get() = prefs.getInt("talk_key", 0)
        set(v) = prefs.edit().putInt("talk_key", v).apply()

    /** Whether the tablet listens for "Hey Athena" as well as the talk button. */
    var wakeWord: Boolean
        get() = prefs.getBoolean("wake_word", true)
        set(v) = prefs.edit().putBoolean("wake_word", v).apply()

    /** This tablet's id with Hermai, made once and kept. */
    val id: String
        get() = prefs.getString("id", null) ?: ("herma-" + UUID.randomUUID().toString().take(8)).also {
            prefs.edit().putString("id", it).apply()
        }

    val ready: Boolean get() = server.isNotEmpty() && room.isNotEmpty() && refreshToken.isNotEmpty()

    fun signOut() = prefs.edit().remove("access").remove("refresh").apply()
}
