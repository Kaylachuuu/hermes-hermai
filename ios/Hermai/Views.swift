import NetworkExtension
import SwiftUI

private let ink = Color(red: 0.06, green: 0.09, blue: 0.15)
private let gold = Color(red: 0.91, green: 0.77, blue: 0.42)
private let mist = Color(red: 0.60, green: 0.64, blue: 0.71)

struct RootView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        ZStack {
            ink.ignoresSafeArea()
            if model.paired { TalkView() } else { PairView() }
        }
    }
}

// MARK: - Talking

struct TalkView: View {
    @EnvironmentObject var model: AppModel
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                Spacer()
                Button { showSettings = true } label: {
                    Image(systemName: "gearshape").font(.title2).foregroundColor(mist)
                }
                .accessibilityLabel("Settings")
            }
            Text(model.personName.isEmpty ? "Hermai" : "Hi, \(model.personName)")
                .font(.largeTitle).foregroundColor(.white)
            Text("Athena").foregroundColor(mist)
            Spacer(minLength: 8)
            TalkButton(phase: model.phase, press: model.press, release: model.release)
                .disabled(!model.mayTalk)
                .opacity(model.mayTalk ? 1 : 0.4)
            Text(model.status).foregroundColor(gold).multilineTextAlignment(.center)
            Text(model.heard).foregroundColor(mist).multilineTextAlignment(.center)
            Text(model.reply).font(.title3).foregroundColor(.white).multilineTextAlignment(.center)
            Spacer()
        }
        .padding(24)
        .task { await model.hello() }
        .sheet(isPresented: $showSettings) { SettingsView().environmentObject(model) }
        .alert("Athena is asking", isPresented: Binding(get: { model.confirming != nil },
                                                        set: { if !$0 && model.confirming != nil { model.cancelConfirm() } }),
               presenting: model.confirming) { _ in
            Button("Confirm with Face ID") { model.confirm() }
            Button("Cancel", role: .cancel) { model.cancelConfirm() }
        } message: { request in
            Text("Confirm with Face ID to let her do this: \(request.what)")
        }
    }
}

struct TalkButton: View {
    let phase: AppModel.Phase
    let press: () -> Void
    let release: () -> Void
    @State private var held = false

    private var label: String {
        switch phase {
        case .ready: return "Hold to talk"
        case .listening: return "Listening…"
        case .thinking: return "Thinking…"
        case .speaking: return "Speaking · tap to stop"
        }
    }

    private var colour: Color {
        switch phase {
        case .ready: return Color(red: 0.12, green: 0.16, blue: 0.27)
        case .listening: return Color(red: 0.70, green: 0.25, blue: 0.18)
        case .thinking: return Color(red: 0.42, green: 0.36, blue: 0.58)
        case .speaking: return Color(red: 0.18, green: 0.49, blue: 0.36)
        }
    }

    var body: some View {
        Text(label)
            .font(.title2).foregroundColor(.white).multilineTextAlignment(.center)
            .frame(width: 240, height: 240)
            .background(Circle().fill(colour))
            .overlay(Circle().stroke(gold, lineWidth: 3))
            .gesture(DragGesture(minimumDistance: 0)
                .onChanged { _ in if !held { held = true; press() } }
                .onEnded { _ in held = false; release() })
            .accessibilityAddTraits(.isButton)
    }
}

// MARK: - Pairing

struct PairView: View {
    @EnvironmentObject var model: AppModel
    @State private var server = Store.server
    @State private var code = ""
    @State private var scanning = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Hermai").font(.largeTitle).foregroundColor(.white)
                Text("Pair this phone with Athena. Kayla makes a pairing code for you in Hermes; scan its QR code, or enter the address and the code.")
                    .foregroundColor(mist)
                Button { scanning = true } label: {
                    Label("Scan pairing QR code", systemImage: "qrcode.viewfinder").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).tint(gold).foregroundColor(ink)
                Text("Hermes address").foregroundColor(mist)
                TextField("http://10.0.0.20:9119", text: $server)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    .textFieldStyle(.roundedBorder)
                Text("Pairing code").foregroundColor(mist)
                TextField("hp1_…", text: $code)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .textFieldStyle(.roundedBorder)
                Button("Pair this phone") { Task { await model.pair(server: server, code: code) } }
                    .buttonStyle(.bordered).disabled(server.isEmpty || code.isEmpty)
                Text(model.status).foregroundColor(gold)
                Divider().background(mist)
                VPNSection()
            }
            .padding(24)
        }
        .sheet(isPresented: $scanning) {
            ScannerView { text in
                scanning = false
                if let url = URL(string: text), url.scheme == "hermai" { model.handle(url: url) }
                else { model.status = "That isn't a Hermai pairing code." }
            }
        }
    }
}

// MARK: - Settings

struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @AppStorage("showTone") private var showTone = false

    var body: some View {
        NavigationView {
            Form {
                Section("This phone") {
                    LabeledContent("Paired as", value: model.personName)
                    LabeledContent("Hermes", value: Store.server)
                    Button("Unpair", role: .destructive) { model.unpair(); dismiss() }
                }
                Section(footer: Text("Off: Athena answers as fully as she would in a chat. On: short, quick answers.")) {
                    Toggle("Short replies", isOn: Binding(
                        get: { model.shortReplies },
                        set: { value in Task { await model.setShortReplies(value) } }))
                }
                Section(footer: Text("Shows Athena's note on how you said it under your words, as she gets it. Useful for checking her hearing.")) {
                    Toggle("Show how it was said", isOn: $showTone)
                }
                Section("VPN") { VPNSection() }
            }
            .navigationTitle("Settings")
            .toolbar { Button("Done") { dismiss() } }
        }
    }
}

/// The WireGuard profile from the firewall's QR code, and turning the VPN on and off.
struct VPNSection: View {
    @EnvironmentObject var model: AppModel
    @State private var scanning = false
    @State private var problem = ""

    var body: some View {
        #if NO_TUNNEL
        // The free-account build (project-personal.yml): Apple gives free accounts no VPN extensions.
        Text("Away from home, turn on the WireGuard app's VPN first; this build of Hermai has none of its own.")
            .foregroundColor(.gray)
        #else
        VPNControls(tunnel: model.tunnel, scanning: $scanning, problem: $problem)
            .sheet(isPresented: $scanning) {
                ScannerView { text in
                    scanning = false
                    Task {
                        do { try await model.tunnel.save(profile: text); problem = "" }
                        catch { problem = error.localizedDescription }
                    }
                }
            }
        #endif
    }
}

private struct VPNControls: View {
    @ObservedObject var tunnel: Tunnel
    @Binding var scanning: Bool
    @Binding var problem: String

    private var state: String {
        switch tunnel.status {
        case .connected: return "On"
        case .connecting, .reasserting: return "Connecting…"
        case .disconnecting: return "Turning off…"
        default: return tunnel.hasProfile ? "Off" : "Not set up"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Away from home, Hermai reaches Athena through its own WireGuard VPN. It only carries traffic for Hermes.")
                .font(.footnote).foregroundColor(mist)
            HStack {
                Text("VPN: \(state)").foregroundColor(.white)
                Spacer()
                if tunnel.hasProfile {
                    Button(tunnel.status == .connected ? "Turn off" : "Turn on") {
                        if tunnel.status == .connected { tunnel.disconnect() }
                        else { do { try tunnel.connect() } catch { problem = error.localizedDescription } }
                    }
                }
            }
            Button(tunnel.hasProfile ? "Scan a new VPN profile" : "Scan VPN profile QR code") { scanning = true }
            if !problem.isEmpty { Text(problem).foregroundColor(gold).font(.footnote) }
        }
    }
}
