import SwiftUI

@main
struct HermaiApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .onOpenURL { model.handle(url: $0) }
                .preferredColorScheme(.dark)
        }
    }
}
