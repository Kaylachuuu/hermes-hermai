import Foundation

struct HermesError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

/// Talks to Hermai's phone routes on Hermes with this phone's own token.
struct Hermes {
    var server: String
    var token: String?

    struct Reply: Decodable {
        let heard: String
        let reply: String
        let audio: String?
        let speech_error: String?
        let confirm: Confirm?  // the guard is asking this phone for Face ID
    }

    struct Confirm: Decodable, Identifiable {
        let id: String
        let what: String
        let challenge: String
    }

    struct FaceID: Decodable {
        let key: Bool
        let allowed: Bool
    }

    struct Paired: Decodable {
        let token: String
        let person: String
        let name: String
        let may_talk: Bool
    }

    struct Hello: Decodable {
        let person: String
        let name: String
        let may_talk: Bool
        let why_not: String?  // why this phone can't talk yet, when it can't
        let short: Bool?      // Short replies; missing from an older Hermai
        let face_id: FaceID?  // missing from an older Hermai
    }

    struct Settings: Decodable {
        let short: Bool
    }

    static func normalise(_ server: String) -> String {
        var s = server.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasSuffix("/") { s.removeLast() }
        if !s.hasPrefix("http://") && !s.hasPrefix("https://") { s = "http://" + s }
        return s
    }

    /// Trades a one-time pairing code for this phone's token.
    func pair(code: String, device: String) async throws -> Paired {
        let body = try JSONSerialization.data(withJSONObject: ["device": device])
        let data = try await call("POST", "/pair/claim", body: body, type: "application/json", bearer: code)
        return try JSONDecoder().decode(Paired.self, from: data)
    }

    func hello() async throws -> Hello {
        try JSONDecoder().decode(Hello.self, from: try await call("POST", "/p/hello"))
    }

    func setShort(_ short: Bool) async throws -> Settings {
        let body = try JSONSerialization.data(withJSONObject: ["short": short])
        return try JSONDecoder().decode(Settings.self,
                                        from: try await call("POST", "/p/settings", body: body, type: "application/json"))
    }

    func registerKey(_ publicKey: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["public_key": publicKey])
        _ = try await call("POST", "/p/key", body: body, type: "application/json")
    }

    /// Face ID passed: the signed challenge goes back, and Athena goes ahead.
    func confirm(id: String, signature: String) async throws -> Reply {
        let body = try JSONSerialization.data(withJSONObject: ["id": id, "signature": signature])
        return try JSONDecoder().decode(Reply.self, from: try await call("POST", "/p/confirm", body: body,
                                                                         type: "application/json"))
    }

    func voice(wav: Data) async throws -> Reply {
        try JSONDecoder().decode(Reply.self, from: try await call("POST", "/p/voice", body: wav, type: "audio/wav"))
    }

    func audio(key: String) async throws -> Data {
        let q = key.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? key
        return try await call("GET", "/p/audio?key=\(q)")
    }

    private func call(_ method: String, _ path: String, body: Data? = nil, type: String? = nil,
                      bearer: String? = nil) async throws -> Data {
        guard let url = URL(string: "\(server)/api/plugins/hermai\(path)") else {
            throw HermesError(message: "That Hermes address isn't valid.")
        }
        var req = URLRequest(url: url, timeoutInterval: 200) // Athena may take a while on a long answer
        req.httpMethod = method
        if let b = bearer ?? token { req.setValue("Bearer \(b)", forHTTPHeaderField: "Authorization") }
        if let type { req.setValue(type, forHTTPHeaderField: "Content-Type") }
        req.httpBody = body
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: req)
        } catch {
            throw HermesError(message: "Can't reach Hermes at \(server). Is the VPN on? (\(error.localizedDescription))")
        }
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            if code == 401 { throw HermesError(message: detail ?? "This phone isn't paired any more. Pair it again in Settings.") }
            throw HermesError(message: detail ?? "Hermes answered HTTP \(code).")
        }
        return data
    }
}
