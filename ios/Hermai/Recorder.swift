import AVFoundation

/// Records 16 kHz mono speech while held, as WAV; plays Athena's reply.
final class Recorder: NSObject {
    private var recorder: AVAudioRecorder?
    private var player: AVAudioPlayer?
    private var started = Date()
    var onFinishedPlaying: (() -> Void)?

    private var file: URL { FileManager.default.temporaryDirectory.appendingPathComponent("speech.wav") }

    static func askPermission() async -> Bool {
        await withCheckedContinuation { done in
            AVAudioSession.sharedInstance().requestRecordPermission { done.resume(returning: $0) }
        }
    }

    func start() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setActive(true)
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16_000, AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false,
        ]
        let r = try AVAudioRecorder(url: file, settings: settings)
        recorder = r
        started = Date()
        r.record()
    }

    /// The recording, or nil when it was too short to be speech.
    func stop() -> Data? {
        guard let r = recorder else { return nil }
        r.stop()
        recorder = nil
        if Date().timeIntervalSince(started) < 0.3 { return nil }
        return try? Data(contentsOf: file)
    }

    func play(_ wav: Data) throws {
        stopPlaying()
        let p = try AVAudioPlayer(data: wav)
        p.delegate = self
        player = p
        p.play()
    }

    func stopPlaying() {
        player?.stop()
        player = nil
    }
}

extension Recorder: AVAudioPlayerDelegate {
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        self.player = nil
        onFinishedPlaying?()
    }
}
