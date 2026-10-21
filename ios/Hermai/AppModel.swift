import SwiftUI
import UIKit

/// The app's state: pairing, and one spoken turn at a time with Athena.
@MainActor
final class AppModel: ObservableObject {
    enum Phase: Equatable { case ready, listening, thinking, speaking }

    @Published var paired = Store.token != nil && !Store.server.isEmpty
    @Published var personName = Store.personName
    @Published var mayTalk = true
    @Published var shortReplies = false
    @Published var phase: Phase = .ready
    @Published var heard = ""
    @Published var reply = ""
    @Published var status = ""
    let tunnel = Tunnel()
    private let recorder = Recorder()

    init() {
        recorder.onFinishedPlaying = { [weak self] in Task { @MainActor in self?.phase = .ready } }
        #if !NO_TUNNEL
        Task { await tunnel.load() }
        #endif
    }

    private var hermes: Hermes { Hermes(server: Store.server, token: Store.token) }

    // MARK: pairing

    /// A pairing link from a QR code: hermai://pair?server=...&code=...
    func handle(url: URL) {
        guard url.scheme == "hermai", url.host == "pair",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
              let server = items.first(where: { $0.name == "server" })?.value,
              let code = items.first(where: { $0.name == "code" })?.value else {
            status = "That isn't a Hermai pairing code."
            return
        }
        Task { await pair(server: server, code: code) }
    }

    func pair(server: String, code: String) async {
        status = "Pairing…"
        let s = Hermes.normalise(server)
        do {
            let p = try await Hermes(server: s, token: nil).pair(code: code.trimmingCharacters(in: .whitespacesAndNewlines),
                                                                 device: UIDevice.current.name)
            Store.server = s
            Store.token = p.token
            Store.personName = p.name
            personName = p.name
            mayTalk = p.may_talk
            paired = true
            status = ""
        } catch {
            status = error.localizedDescription
        }
    }

    func unpair() {
        Store.token = nil
        paired = false
        heard = ""
        reply = ""
    }

    func hello() async {
        guard paired else { return }
        do {
            let h = try await hermes.hello()
            personName = h.name
            mayTalk = h.may_talk
            shortReplies = h.short ?? false
            status = h.may_talk ? "" : "This phone can't talk to Athena yet: \(h.why_not ?? "Hermes hasn't allowed it")."
        } catch {
            status = error.localizedDescription
        }
    }

    /// The Short replies switch in Settings: Hermes keeps it for this phone.
    func setShortReplies(_ short: Bool) async {
        do {
            shortReplies = try await hermes.setShort(short).short
        } catch {
            status = error.localizedDescription
        }
    }

    // MARK: talking

    func press() {
        switch phase {
        case .speaking:
            recorder.stopPlaying()
            phase = .ready
            return
        case .thinking, .listening:
            return
        case .ready:
            break
        }
        Task {
            guard await Recorder.askPermission() else {
                status = "Hermai needs the microphone. Turn it on in Settings › Hermai."
                return
            }
            do {
                try recorder.start()
                phase = .listening
                status = ""
            } catch {
                status = "The microphone isn't available (\(error.localizedDescription))."
            }
        }
    }

    func release() {
        guard phase == .listening else { return }
        guard let wav = recorder.stop() else {
            phase = .ready
            return
        }
        phase = .thinking
        Task {
            do {
                let r = try await hermes.voice(wav: wav)
                heard = r.heard.isEmpty ? "" : "“\(r.heard)”"
                reply = r.reply
                if r.heard.isEmpty { status = "I didn't catch that." }
                if let e = r.speech_error { status = "Couldn't speak the reply: \(e)" }
                if let key = r.audio {
                    try recorder.play(try await hermes.audio(key: key))
                    phase = .speaking
                } else {
                    phase = .ready
                }
            } catch {
                status = error.localizedDescription
                phase = .ready
            }
        }
    }
}
