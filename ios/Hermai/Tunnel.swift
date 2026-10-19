import NetworkExtension

/// Hermai's own VPN: one WireGuard profile, scanned from the firewall's QR code, run by the
/// HermaiTunnel extension. It shows in iOS Settings as "Hermai".
@MainActor
final class Tunnel: ObservableObject {
    @Published private(set) var hasProfile = false
    @Published private(set) var status: NEVPNStatus = .invalid
    private var manager: NETunnelProviderManager?
    private var observer: NSObjectProtocol?

    static let extensionID = (Bundle.main.bundleIdentifier ?? "io.github.kaylachuuu.hermai") + ".tunnel"

    func load() async {
        let managers = (try? await NETunnelProviderManager.loadAllFromPreferences()) ?? []
        manager = managers.first
        hasProfile = manager != nil
        watch()
    }

    /// Saves a wg-quick profile (the text in the firewall's QR code) as Hermai's VPN.
    func save(profile: String) async throws {
        guard profile.contains("[Interface]"), profile.contains("[Peer]") else {
            throw HermesError(message: "That QR code isn't a WireGuard profile.")
        }
        let m = manager ?? NETunnelProviderManager()
        let proto = NETunnelProviderProtocol()
        proto.providerBundleIdentifier = Tunnel.extensionID
        proto.serverAddress = Tunnel.endpoint(in: profile) ?? "Home"
        proto.providerConfiguration = ["wgQuickConfig": profile]
        m.protocolConfiguration = proto
        m.localizedDescription = "Hermai"
        m.isEnabled = true
        try await m.saveToPreferences()
        try await m.loadFromPreferences()
        manager = m
        hasProfile = true
        watch()
    }

    func connect() throws {
        try manager?.connection.startVPNTunnel()
    }

    func disconnect() {
        manager?.connection.stopVPNTunnel()
    }

    func remove() async {
        try? await manager?.removeFromPreferences()
        manager = nil
        hasProfile = false
        status = .invalid
    }

    private func watch() {
        status = manager?.connection.status ?? .invalid
        if let observer { NotificationCenter.default.removeObserver(observer) }
        observer = NotificationCenter.default.addObserver(
            forName: .NEVPNStatusDidChange, object: manager?.connection, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.status = self?.manager?.connection.status ?? .invalid }
        }
    }

    private static func endpoint(in profile: String) -> String? {
        for line in profile.split(whereSeparator: \.isNewline) {
            let parts = line.split(separator: "=", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
            if parts.count == 2, parts[0].lowercased() == "endpoint" { return parts[1] }
        }
        return nil
    }
}
