import WireGuardKit

/// Reads a WireGuard profile in the usual wg-quick form, as a firewall exports it:
///
///     [Interface]
///     PrivateKey = ...
///     Address = 10.8.0.5/32
///     DNS = 10.0.0.1
///
///     [Peer]
///     PublicKey = ...
///     Endpoint = home.example.net:51820
///     AllowedIPs = 10.0.0.20/32
///     PersistentKeepalive = 25
enum WgQuick {
    static func parse(_ text: String) throws -> TunnelConfiguration {
        var section = ""
        var interface: InterfaceConfiguration?
        var peers: [PeerConfiguration] = []
        var peer: PeerConfiguration?

        func finishPeer() {
            if let p = peer { peers.append(p) }
            peer = nil
        }

        for raw in text.split(whereSeparator: \.isNewline) {
            let line = raw.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)[0]
                .trimmingCharacters(in: .whitespaces)
            if line.isEmpty { continue }
            if line.hasPrefix("[") {
                finishPeer()
                section = line.lowercased()
                continue
            }
            let parts = line.split(separator: "=", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
            guard parts.count == 2 else { throw TunnelError("Couldn't read this line of the profile: \(line)") }
            let key = parts[0].lowercased()
            let value = parts[1]
            let list = value.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }

            switch section {
            case "[interface]":
                if key == "privatekey" {
                    guard let k = PrivateKey(base64Key: value) else { throw TunnelError("The profile's private key isn't valid.") }
                    interface = InterfaceConfiguration(privateKey: k)
                    continue
                }
                guard interface != nil else { throw TunnelError("The profile needs PrivateKey first in [Interface].") }
                switch key {
                case "address": interface!.addresses = try list.map { try range($0) }
                case "dns": interface!.dns = list.compactMap { DNSServer(from: $0) }
                case "mtu": interface!.mtu = UInt16(value)
                case "listenport": interface!.listenPort = UInt16(value)
                default: break
                }
            case "[peer]":
                if key == "publickey" {
                    finishPeer()
                    guard let k = PublicKey(base64Key: value) else { throw TunnelError("A peer's public key isn't valid.") }
                    peer = PeerConfiguration(publicKey: k)
                    continue
                }
                guard peer != nil else { throw TunnelError("Each [Peer] needs its PublicKey first.") }
                switch key {
                case "presharedkey": peer!.preSharedKey = PreSharedKey(base64Key: value)
                case "allowedips": peer!.allowedIPs = try list.map { try range($0) }
                case "endpoint":
                    guard let e = Endpoint(from: value) else { throw TunnelError("The peer's endpoint isn't valid: \(value)") }
                    peer!.endpoint = e
                case "persistentkeepalive": peer!.persistentKeepAlive = UInt16(value)
                default: break
                }
            default:
                break
            }
        }
        finishPeer()
        guard let iface = interface else { throw TunnelError("This isn't a WireGuard profile: it has no [Interface].") }
        guard !peers.isEmpty else { throw TunnelError("The WireGuard profile has no [Peer].") }
        return TunnelConfiguration(name: "Hermai", interface: iface, peers: peers)
    }

    private static func range(_ s: String) throws -> IPAddressRange {
        guard let r = IPAddressRange(from: s) else { throw TunnelError("Not an address: \(s)") }
        return r
    }
}
