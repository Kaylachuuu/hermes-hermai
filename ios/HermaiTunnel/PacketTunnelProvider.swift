import NetworkExtension
import WireGuardKit

/// The VPN half of Hermai: WireGuard to the home firewall, carrying only what the profile's
/// AllowedIPs name (Athena's server), so the rest of the phone's traffic goes out as usual.
final class PacketTunnelProvider: NEPacketTunnelProvider {
    private lazy var adapter = WireGuardAdapter(with: self) { _, message in
        NSLog("Hermai VPN: %@", message)
    }

    override func startTunnel(options: [String: NSObject]?, completionHandler: @escaping (Error?) -> Void) {
        guard let proto = protocolConfiguration as? NETunnelProviderProtocol,
              let text = proto.providerConfiguration?["wgQuickConfig"] as? String else {
            completionHandler(TunnelError("This VPN has no WireGuard profile; scan one in Hermai's settings."))
            return
        }
        let config: TunnelConfiguration
        do {
            config = try WgQuick.parse(text)
        } catch {
            completionHandler(error)
            return
        }
        adapter.start(tunnelConfiguration: config) { error in
            completionHandler(error.map { TunnelError("WireGuard couldn't start: \($0)") })
        }
    }

    override func stopTunnel(with reason: NEProviderStopReason, completionHandler: @escaping () -> Void) {
        adapter.stop { _ in completionHandler() }
    }
}

struct TunnelError: LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}
