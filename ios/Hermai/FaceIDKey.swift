import Foundation
import LocalAuthentication
import Security

/// This phone's Face ID key: a P-256 key made in the Secure Enclave, which never leaves it and signs
/// only after Face ID (or Touch ID) passes. Hermes keeps the public half and checks each signature, so
/// approving an unlock takes Face ID on this phone, not just its Hermai token.
enum FaceIDKey {
    private static let tag = Data("io.github.kaylachuuu.hermai.face-id".utf8)

    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// The public key to register with Hermes (X9.63, base64), making the key first if there isn't one.
    static func publicKey() throws -> String {
        let key = try existing() ?? make()
        guard let pub = SecKeyCopyPublicKey(key),
              let raw = SecKeyCopyExternalRepresentation(pub, nil) as Data? else {
            throw Failure(message: "Couldn't read this phone's Face ID key.")
        }
        return raw.base64EncodedString()
    }

    /// Asks for Face ID, then signs ``challenge`` (DER ECDSA over SHA-256). Blocks while Face ID shows.
    static func sign(_ challenge: String, reason: String) throws -> String {
        let context = LAContext()
        context.localizedReason = reason
        guard let key = try existing(context: context) else {
            throw Failure(message: "This phone has no Face ID key for Hermai. Unpair it and pair it again.")
        }
        var error: Unmanaged<CFError>?
        guard let signature = SecKeyCreateSignature(key, .ecdsaSignatureMessageX962SHA256,
                                                    Data(challenge.utf8) as CFData, &error) as Data? else {
            throw Failure(message: "Face ID didn't confirm it, so nothing was done.")
        }
        return signature.base64EncodedString()
    }

    static func delete() {
        SecItemDelete([kSecClass as String: kSecClassKey, kSecAttrApplicationTag as String: tag] as CFDictionary)
    }

    private static func existing(context: LAContext? = nil) throws -> SecKey? {
        var query: [String: Any] = [kSecClass as String: kSecClassKey,
                                    kSecAttrApplicationTag as String: tag,
                                    kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom,
                                    kSecReturnRef as String: true]
        if let context { query[kSecUseAuthenticationContext as String] = context }
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let item else { throw Failure(message: "Couldn't open the Face ID key (\(status)).") }
        return (item as! SecKey)
    }

    private static func make() throws -> SecKey {
        guard let access = SecAccessControlCreateWithFlags(nil, kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly,
                                                           [.privateKeyUsage, .biometryCurrentSet], nil) else {
            throw Failure(message: "Couldn't set up a Face ID key.")
        }
        let attributes: [String: Any] = [
            kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom,
            kSecAttrKeySizeInBits as String: 256,
            kSecAttrTokenID as String: kSecAttrTokenIDSecureEnclave,
            kSecPrivateKeyAttrs as String: [kSecAttrIsPermanent as String: true,
                                            kSecAttrApplicationTag as String: tag,
                                            kSecAttrAccessControl as String: access],
        ]
        var error: Unmanaged<CFError>?
        guard let key = SecKeyCreateRandomKey(attributes as CFDictionary, &error) else {
            throw Failure(message: "This phone can't make a Face ID key (it needs a passcode and Face ID or Touch ID set up).")
        }
        return key
    }
}
