import Foundation
import Security

/// What the phone remembers: the Hermes address and who it's paired as in UserDefaults, and its
/// Hermai token in the Keychain (this device only, never synced or backed up).
enum Store {
    private static let defaults = UserDefaults.standard
    private static let tokenAccount = "hermai-token"

    static var server: String {
        get { defaults.string(forKey: "server") ?? "" }
        set { defaults.set(newValue, forKey: "server") }
    }

    static var personName: String {
        get { defaults.string(forKey: "personName") ?? "" }
        set { defaults.set(newValue, forKey: "personName") }
    }

    static var token: String? {
        get {
            var query = baseQuery
            query[kSecReturnData as String] = true
            query[kSecMatchLimit as String] = kSecMatchLimitOne
            var item: CFTypeRef?
            guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
                  let data = item as? Data else { return nil }
            return String(data: data, encoding: .utf8)
        }
        set {
            SecItemDelete(baseQuery as CFDictionary)
            guard let value = newValue, let data = value.data(using: .utf8) else { return }
            var add = baseQuery
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    private static var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "Hermai",
         kSecAttrAccount as String: tokenAccount]
    }
}
