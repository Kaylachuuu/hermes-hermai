package dev.hermai.herma

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class SignedOut : IOException("This herma's sign-in has expired; sign in again in Settings.")

class HermesError(message: String) : IOException(message)

/**
 * Talks to Hermes: the dashboard's own sign-in, then Hermai's routes under /api/plugins/hermai/.
 * Every call blocks, so callers run it off the main thread.
 */
class Hermes(private val herma: Herma) {

    /** `ignored` when Hermai heard no "Athena" in a wake word's recording: a false start, nothing to say. */
    class Reply(val heard: String, val reply: String, val audio: String?, val speechError: String?,
                val ignored: Boolean = false)

    /** Signs in with a dashboard username and password and keeps the renewable tokens. */
    fun signIn(server: String, username: String, password: String) {
        val base = normalise(server)
        val providers = try {
            JSONObject(request("GET", "$base/api/auth/providers").text()).getJSONArray("providers")
        } catch (e: IOException) {
            throw HermesError("Can't reach $base (${e.message})")
        } catch (e: org.json.JSONException) {
            throw HermesError("$base doesn't look like a Hermes dashboard")
        }
        var provider = ""
        for (i in 0 until providers.length()) {
            val p = providers.getJSONObject(i)
            if (p.optBoolean("supports_password")) { provider = p.getString("name"); break }
        }
        if (provider.isEmpty()) throw HermesError("This Hermes has no password sign-in turned on")
        val body = JSONObject().put("provider", provider).put("username", username).put("password", password)
        val conn = request("POST", "$base/auth/password-login", body.toString().toByteArray(), "application/json")
        if (conn.responseCode != 200) throw HermesError("Hermes didn't accept that username and password (HTTP ${conn.responseCode})")
        var access = ""
        var refresh = ""
        for ((name, values) in conn.headerFields) {
            if (name == null || !name.equals("Set-Cookie", ignoreCase = true)) continue
            for (cookie in values) {
                val (key, value) = cookie.substringBefore(';').split('=', limit = 2).let { it[0].trim() to it.getOrElse(1) { "" }.trim('"') }
                if (key == "hermes_session_at") access = value
                if (key == "hermes_session_rt") refresh = value
            }
        }
        conn.disconnect()
        if (access.isEmpty() || refresh.isEmpty()) throw HermesError("Signed in, but Hermes gave no renewable sign-in")
        herma.server = base
        herma.username = username
        herma.provider = provider
        herma.accessToken = access
        herma.refreshToken = refresh
    }

    /** Tells Hermai this herma is here and which room it's in. */
    fun hello(): JSONObject {
        val body = JSONObject().put("herma", herma.id).put("room", herma.room)
        return JSONObject(call("POST", "/hello", body.toString().toByteArray(), "application/json").decodeToString())
    }

    /** One spoken turn: a WAV recording in, what was heard and Athena's reply out. `wake` when it
     *  started with "Hey Athena" rather than the talk button. */
    fun voice(wav: ByteArray, wake: Boolean = false): Reply =
        reply(call("POST", "/voice?herma=${enc(herma.id)}${if (wake) "&wake=1" else ""}", wav, "audio/wav"))

    /** One typed turn. */
    fun ask(text: String): Reply {
        val body = JSONObject().put("text", text).toString().toByteArray()
        return reply(call("POST", "/ask?herma=${enc(herma.id)}", body, "application/json"))
    }

    /** Athena's spoken reply, as WAV. */
    fun audio(key: String): ByteArray = call("GET", "/voice/audio/${enc(key)}")

    private fun reply(raw: ByteArray): Reply {
        val j = JSONObject(raw.decodeToString())
        return Reply(j.optString("heard"), j.optString("reply"),
            if (j.isNull("audio")) null else j.optString("audio"),
            if (j.has("speech_error")) j.optString("speech_error") else null,
            j.optBoolean("ignored"))
    }

    /** A Hermai route, renewing the sign-in once if it has lapsed. */
    private fun call(method: String, path: String, body: ByteArray? = null, type: String? = null): ByteArray {
        var renewed = false
        while (true) {
            if (herma.accessToken.isEmpty()) { renew(); renewed = true }
            val conn = request(method, "${herma.server}/api/plugins/hermai$path", body, type, herma.accessToken)
            val code = conn.responseCode
            if (code == 401 && !renewed) { conn.disconnect(); renew(); renewed = true; continue }
            if (code == 401) throw SignedOut()
            if (code !in 200..299) {
                val detail = try { JSONObject(conn.errorStream?.readBytes()?.decodeToString() ?: "").optString("detail") } catch (e: Exception) { "" }
                conn.disconnect()
                throw HermesError(detail.ifEmpty { "Hermes answered HTTP $code" })
            }
            return conn.inputStream.use { it.readBytes() }.also { conn.disconnect() }
        }
    }

    /** Swaps the refresh token for a new pair; Hermes rotates it, so the new one is kept. */
    private fun renew() {
        if (herma.refreshToken.isEmpty()) throw SignedOut()
        val body = JSONObject().put("refresh_token", herma.refreshToken).put("provider", herma.provider)
        val conn = request("POST", "${herma.server}/auth/native/refresh", body.toString().toByteArray(), "application/json")
        val code = conn.responseCode
        if (code == 400 || code == 401) { conn.disconnect(); herma.signOut(); throw SignedOut() }
        if (code != 200) { conn.disconnect(); throw HermesError("Renewing the sign-in failed (HTTP $code)") }
        val fresh = JSONObject(conn.text())
        val access = fresh.optString("access_token")
        if (access.isEmpty()) throw HermesError("Renewing the sign-in: unexpected reply")
        herma.accessToken = access
        fresh.optString("refresh_token").takeIf { it.isNotEmpty() }?.let { herma.refreshToken = it }
    }

    private fun request(method: String, url: String, body: ByteArray? = null, type: String? = null, bearer: String? = null): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = method
        conn.connectTimeout = 15_000
        conn.readTimeout = 200_000 // Athena may take a while on a long answer
        conn.instanceFollowRedirects = false
        bearer?.let { conn.setRequestProperty("Authorization", "Bearer $it") }
        if (body != null) {
            conn.doOutput = true
            type?.let { conn.setRequestProperty("Content-Type", it) }
            conn.setFixedLengthStreamingMode(body.size)
            conn.outputStream.use { it.write(body) }
        }
        return conn
    }

    private fun HttpURLConnection.text(): String = inputStream.use { it.readBytes().decodeToString() }.also { disconnect() }

    companion object {
        fun normalise(server: String): String {
            val s = server.trim().trimEnd('/')
            return if (s.startsWith("http://") || s.startsWith("https://")) s else "http://$s"
        }

        private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
    }
}
