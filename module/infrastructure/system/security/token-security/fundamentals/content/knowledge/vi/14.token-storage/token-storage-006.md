# Mobile secure storage

Trong ứng dụng di động, **access token**, **refresh token** và những khóa dùng để chứng minh quyền sở hữu thiết bị là **tài sản bảo mật**, không phải các chuỗi cấu hình thông thường. Một access token OAuth 2.0 có thể cho phép gọi API trong phạm vi `scope` và `aud` được cấp; refresh token có thể tiếp tục xin access token mới nếu grant còn hợp lệ. Khi chúng bị sao chép, người giữ token có thể lợi dụng quyền đó, đặc biệt với **bearer token**.

Bài học **“Mobile secure storage”** thuộc chương **Token storage** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là hiểu cách bảo vệ token trên **iOS và Android**, gắn với vòng đời phát hành, kiểm tra JWT/opaque token, OAuth 2.0/OpenID Connect (OIDC), lưu trữ, thu hồi và chống đánh cắp/phát lại. Trọng tâm không chỉ là “cất token vào đâu”, mà còn là **ai có thể truy cập, vào thời điểm nào, sau khi thiết bị khóa/backup/khôi phục ra sao, và điều gì xảy ra khi token bị lộ**.

**Nguyên tắc:** dùng kho bảo mật của hệ điều hành hoặc **khóa không xuất được từ Android Keystore để mã hóa dữ liệu**, giữ quyền tối thiểu, không lưu token trong vùng dễ đọc, và **không coi secure storage là biện pháp thay thế OAuth/AS/API authorization**. Máy đã bị root/jailbreak hoặc tiến trình ứng dụng bị chiếm quyền vẫn có rủi ro ngay cả khi đã dùng đúng kho hệ điều hành.

## 1. Cần bảo vệ tài sản nào và trước ai?

Trước khi chọn API lưu trữ, hãy định nghĩa **threat model**. Ví dụ một ứng dụng mobile `orders-mobile` đăng nhập bằng Authorization Code + PKCE, gọi `Orders API` và có thể duy trì phiên khi user không mở ứng dụng.

| Tài sản | Ý nghĩa | Nếu bị lộ | Định hướng bảo vệ |
|---|---|---|---|
| **Access token** | Credential gọi Resource Server theo audience/scope/thời gian | Bị replay để gọi API nếu bearer và chưa bị chặn | Hạn ngắn; ưu tiên trong bộ nhớ khi đủ; nếu phải persist thì mã hóa/kho an toàn |
| **Refresh token** | Credential xin access token mới tại token endpoint | Có thể kéo dài quyền truy cập qua nhiều lần refresh | Lưu Keychain/Keystore-backed encryption, rotation/reuse detection, ràng buộc client/grant |
| **ID token (OIDC)** | Thông tin authentication dành cho client, có thể chứa claims cá nhân | Lộ thông tin hoặc bị hệ thống dùng sai purpose | Chỉ giữ nếu cần, hạn chế log/cache; không dùng gọi API |
| **PKCE code_verifier** | Bí mật tạm thời cho một authorization transaction | Bị dùng cùng code bị lấy cắp để đổi token | Giữ ngắn hạn, gắn với transaction, xóa sau callback hoặc timeout |
| **DPoP private key** | Khóa ký proof-of-possession theo thiết kế | Bản sao token + khóa có thể bị lợi dụng | Ưu tiên khóa non-exportable và hạn chế thao tác ký bằng Keystore/Keychain/Secure Enclave tùy platform |
| **Client secret nhúng trong app** | **Không nên coi là bí mật** với public mobile client | Bất kỳ ai có binary cũng có thể trích xuất | Không dựa vào secret hardcoded để xác thực mobile client |
| **Phiên ứng dụng, cookie, thông tin user** | Ngữ cảnh người dùng và session | Session hijacking hoặc lộ PII | Policy riêng cho session, cookie và cache; chỉ lưu tối thiểu |

**Bảo vệ cần tính đến nhiều đối thủ:** ứng dụng độc hại cùng thiết bị, mất máy, backup, debug/log/analytics, clipboard, malware, runtime instrumentation, Android root, iOS jailbreak, và backend/AS bị compromise. Không biện pháp lưu trữ nào một mình giải quyết toàn bộ các nguy cơ đó.

### Ba mục tiêu không giống nhau

1. **Bí mật khi lưu (at rest):** kẻ đọc được file/backup không nên đọc được token ở dạng plaintext.
2. **Kiểm soát quyền sử dụng:** một số bí mật/khóa có thể yêu cầu thiết bị mở khóa hoặc xác thực người dùng; khóa có thể được giới hạn cho ứng dụng/thiết bị.
3. **An toàn trong lúc chạy (in use):** sau khi app đã được phép dùng token, nó cần đưa token vào bộ nhớ và HTTP request. Malware hoặc hook vào tiến trình có thể đánh cắp token ngay lúc đó.

**Không tuyên bố** “Keychain/Keystore bảo đảm không thể lấy token trong mọi trường hợp”. Kho bảo mật giảm nhiều đường tấn công, nhưng không phải lá chắn tuyệt đối trước tiến trình hoặc hệ điều hành đã bị chiếm quyền.

## 2. Vòng đời OAuth trên mobile và điểm lưu trữ phù hợp

Với ứng dụng native thông thường, dùng **Authorization Code + PKCE S256 qua system browser** theo RFC 8252. App không nhúng password của user và không đưa client secret vào binary như một bí mật đáng tin.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant M as Mobile app
    participant B as System browser
    participant AS as Authorization Server
    participant S as OS secure storage
    participant API as Resource Server

    M->>M: Tạo state, code_verifier, code_challenge
    M->>B: Mở /authorize với PKCE
    B->>AS: User authentication / consent nếu cần
    AS-->>B: Redirect authorization code + state
    B-->>M: Redirect được OS định tuyến về app
    M->>M: Kiểm tra state và transaction
    M->>AS: /token với code + code_verifier
    AS-->>M: Access token (+ refresh/ID token nếu đủ điều kiện)
    M->>S: Lưu refresh token an toàn nếu được cấp
    M->>M: Giữ access token ngắn hạn trong memory khi có thể
    M->>API: HTTPS + đúng access token
    API->>API: Kiểm tra issuer, audience, scope, expiry, policy
    API-->>M: Phản hồi theo quyền
~~~

Đường redirect cần được đăng ký và kiểm soát đúng chuẩn. Ưu tiên **claimed HTTPS redirects** (Android App Links/iOS Universal Links) khi triển khai khả thi; với custom URI scheme cần hiểu nguy cơ app khác đăng ký cùng scheme. PKCE giúp chống đổi authorization code bị chặn bắt, **không bảo vệ refresh token đã lưu**.

### Token nào cần persist?

| Nhu cầu | Cách tiếp cận | Lưu ý |
|---|---|---|
| Người dùng chỉ dùng app khi foreground; đăng nhập lại được chấp nhận | Access token ngắn hạn trong memory; không nhất thiết lưu refresh token | Giảm dấu vết tồn tại trên disk |
| Muốn giữ phiên qua app/process restart | Có thể lưu refresh token trong secure storage, access token trong memory | Grant/refresh token có thể bị thu hồi hoặc hết hạn bất kỳ lúc nào |
| Background sync | Cân nhắc policy refresh và thuộc tính khả dụng khi thiết bị khóa | Không hạ bảo vệ toàn bộ kho chỉ để tiện background job |
| Ứng dụng có quyền tài chính/quản trị nhạy cảm | Có thể yêu cầu user presence/re-authentication tại thao tác nhạy cảm | Biometric gate không thay thế authorization tại server |
| Cần multi-account | Mỗi account/tenant có mục lưu và chính sách rõ | Không để token của account A bị lấy dùng trong account B |

**Access token không mặc định phải được persist.** Khi có refresh token hợp lệ, ứng dụng có thể xin access token mới; nhưng phải xử lý rotation, mạng lỗi, rate limit và user experience. Nếu cần lưu access token để hỗ trợ tiến trình, dùng cơ chế được bảo vệ tương đương và hiểu rủi ro còn lại.

## 3. Không nên lưu token ở đâu?

| Nơi/cách lưu | Vì sao không đủ an toàn cho raw token |
|---|---|
| Android `SharedPreferences` hoặc DataStore **không mã hóa** | App-private storage là sandbox, nhưng dữ liệu vẫn có thể lộ qua backup, cấu hình, lỗi hệ điều hành hoặc thiết bị bị compromise |
| iOS `UserDefaults`, plist hoặc file trong Documents/Caches | Không phải API chuyên quản lý bí mật; dễ vô tình backup, đồng bộ hoặc truy cập qua đường không mong muốn |
| SQLite/Room/Core Data dạng plaintext | Chỉ là hệ quản lý dữ liệu; không tự tạo ranh giới bảo vệ bí mật token |
| External/shared storage, thư mục ảnh, clipboard | Dễ bị ứng dụng khác hoặc người dùng/thiết bị phụ đọc |
| URL query, deep link, crash report, HTTP log, analytics | Có thể rò đến nhiều hệ thống trung gian, lịch sử, referrer hoặc nhân viên hỗ trợ |
| Source code, `BuildConfig`, resource, chuỗi hardcoded trong binary | Mobile package được phân phối; attacker có thể trích xuất |
| Base64/Base64url encoding, “obfuscation”, tự XOR chuỗi | Chỉ thay cách biểu diễn; **không mã hóa bí mật** |
| Hash một chiều access/refresh token rồi định gửi hash lên API | Token dùng để chứng thực phải được trình đúng protocol; “hash token” thường không thay token hợp lệ và có thể tạo sai thiết kế |

**App sandbox cần có**, nhưng **không đủ để coi plaintext token được bảo vệ đúng mục tiêu**. Nếu dùng app-private file/SharedPreferences, hãy **mã hóa bằng khóa được bảo vệ**, chọn cơ chế đã được thẩm định và loại trừ dữ liệu phù hợp khỏi backup.

## 4. So sánh lựa chọn lưu trữ trên iOS và Android

| Nền tảng | Cơ chế phù hợp | Token nằm ở đâu? | Điều cần hiểu |
|---|---|---|---|
| **iOS/iPadOS** | Keychain Services (`SecItemAdd`, `SecItemCopyMatching`, `SecItemUpdate`, `SecItemDelete`) | Keychain item với lớp khả dụng và quyền truy cập | Chọn `kSecAttrAccessible`, entitlement, hành vi backup và user presence |
| **iOS/iPadOS** | Secure Enclave cho khóa phù hợp | Khóa private/key operation được phần cứng hỗ trợ, **không phải nơi nhét mọi JWT string** | Secure Enclave chủ yếu bảo vệ khóa và thao tác mật mã; token vẫn thường ở Keychain |
| **Android** | Android Keystore + mã hóa có xác thực, ví dụ AES-GCM | Key non-exportable trong Keystore; ciphertext token ở app-private storage | Bảo vệ key khác với nơi lưu ciphertext; cần backup exclusion, IV/tag đúng cách và xử lý lỗi giải mã |
| **Android** | Hardware-backed Keystore/StrongBox khi có và phù hợp | Vật liệu khóa trong TEE/StrongBox tùy thiết bị/khả năng | Không giả định mọi máy có StrongBox hay mọi khóa là hardware-backed |
| **Cả hai** | Giữ access token ngắn hạn trong memory khi hợp lý | Memory của tiến trình | Hạn chế dữ liệu at rest nhưng không ngăn hooking/memory compromise |
| **Cả hai** | Backend/session-oriented architecture nếu sản phẩm hỗ trợ | Credential nhạy cảm hơn ở backend; mobile chỉ giữ ít thông tin cần thiết | Backend không loại bỏ mọi rủi ro session/device/API; xem xét threat model |

**Các wrapper secure storage** trong Kotlin Multiplatform, Flutter hoặc React Native chỉ an toàn nếu implementation thực sự dùng nền tảng phù hợp, không rơi về plaintext, cấu hình backup/accessibility đúng và lifecycle được kiểm thử. Tên package “secure storage” **không phải bằng chứng đã bảo vệ đúng**.

## 5. iOS Keychain: chọn lớp bảo vệ theo nhu cầu

Apple Keychain lưu bí mật như password, key, token thông qua các API `SecItem*`. Điểm quan trọng là thuộc tính **`kSecAttrAccessible`**, quy định khi nào app có thể đọc item, đồng thời một số giá trị điều khiển khả năng di chuyển qua thiết bị khác.

| Thuộc tính | Khi nào có thể dùng? | Đặc điểm |
|---|---|---|
| `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` | Khi thiết bị được mở khóa; phù hợp token chỉ cần lúc foreground | Không di chuyển sang thiết bị mới qua restore |
| `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` | Sau lần mở khóa đầu tiên kể từ reboot; có thể hỗ trợ background | Không di chuyển sang thiết bị mới; item còn có thể truy cập khi thiết bị khóa sau lần mở khóa đầu |
| `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` | Khi có device passcode và thiết bị được mở khóa | Không có passcode sẽ không dùng được; bỏ passcode làm item thuộc lớp này bị xóa |
| `kSecAttrAccessibleWhenUnlocked` | Khi thiết bị mở khóa | Có thể di chuyển qua một số cơ chế backup/restore, tùy chính sách của OS |
| `kSecAttrAccessibleAfterFirstUnlock` | Sau lần mở khóa đầu kể từ reboot | Có thể được di chuyển trong quá trình restore được hỗ trợ; thường cho nhu cầu background |

Với refresh token dùng cho app chỉ khi người dùng mở thiết bị, **`WhenUnlockedThisDeviceOnly`** là một lựa chọn chặt chẽ, dễ giải thích. Với background sync cần hoạt động sau khi đã mở khóa một lần, có thể cân nhắc **`AfterFirstUnlockThisDeviceOnly`** nhưng phải chấp nhận bề mặt truy cập khi thiết bị đang khóa sau lần mở khóa đầu.

**Đừng dùng các lớp `Always` đã lỗi thời** để né lỗi truy cập khi khóa máy. Cũng không mặc định bật **`kSecAttrSynchronizable`** để đưa refresh token lên iCloud Keychain; khả năng đồng bộ token qua thiết bị là một quyết định kiến trúc cần phân tích, không chỉ là tiện ích đăng nhập.

### Quyền chia sẻ và user presence

- **Keychain Access Groups** cho phép chia sẻ item giữa các app có entitlement hợp lệ. Chỉ bật khi thực sự cần; chia sẻ sai nhóm mở rộng số tiến trình có thể truy cập.
- Có thể dùng **`SecAccessControlCreateWithFlags`** với các chính sách như `userPresence` hoặc `biometryCurrentSet` cho bí mật/khóa cần xác nhận người dùng. Việc xác thực này phù hợp cho thao tác nhạy cảm, nhưng **không nên gắn bắt buộc vào refresh token được dùng liên tục trong background** nếu trải nghiệm đó không hỗ trợ.
- **Face ID/Touch ID** giúp kiểm soát khả năng truy cập theo chính sách thiết bị; chúng không tự chứng minh người dùng có scope OAuth hợp lệ tại API.
- Với **`ThisDeviceOnly`**, mất thiết bị/chuyển máy có thể yêu cầu đăng nhập lại. Đây là hành vi bảo mật mong muốn nếu chính sách không cho phép credential di chuyển.
- Keychain item có thể tồn tại qua một số chu kỳ gỡ/cài lại ứng dụng; **không giả định uninstall luôn xóa token**. Thiết kế quy trình cleanup và kiểm thử hành vi trên thiết bị/phiên bản OS mục tiêu.

## 6. Swift: lưu refresh token bằng Keychain

Ví dụ Swift sử dụng **Keychain generic password item** cho một ứng dụng có một tài khoản đang hoạt động. Dùng `WhenUnlockedThisDeviceOnly`, không đưa token vào `UserDefaults` hay log.

~~~swift
import Foundation
import Security

enum TokenStoreError: Error {
    case keychain(OSStatus)
    case invalidUTF8
}

struct RefreshTokenKeychain {
    private let service = "com.example.orders.auth"
    private let account = "refresh-token"

    private var identityQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }

    func save(_ token: String) throws {
        let tokenData = Data(token.utf8)

        // Trường hợp item đã tồn tại: chỉ cập nhật dữ liệu,
        // giữ nguyên thuộc tính bảo vệ của item cũ.
        let status = SecItemUpdate(
            identityQuery as CFDictionary,
            [kSecValueData as String: tokenData] as CFDictionary
        )

        if status == errSecSuccess {
            return
        }
        guard status == errSecItemNotFound else {
            throw TokenStoreError.keychain(status)
        }

        var addQuery = identityQuery
        addQuery[kSecValueData as String] = tokenData
        addQuery[kSecAttrAccessible as String] =
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly

        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw TokenStoreError.keychain(addStatus)
        }
    }

    func load() throws -> String? {
        var query = identityQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(
            query as CFDictionary, &item
        )

        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw TokenStoreError.keychain(status)
        }
        guard let data = item as? Data,
              let token = String(data: data, encoding: .utf8) else {
            throw TokenStoreError.invalidUTF8
        }
        return token
    }

    func delete() throws {
        let status = SecItemDelete(identityQuery as CFDictionary)
        guard status == errSecSuccess
                || status == errSecItemNotFound else {
            throw TokenStoreError.keychain(status)
        }
    }
}
~~~

**Những giới hạn và điểm cần hoàn thiện trước production:**

1. Hàm trên không tự xử lý token/refresh rotation, OAuth consent, mạng lỗi hoặc phân quyền API.
2. **Đồng bộ các thao tác save/load/delete** khi có nhiều coroutine/task/thread; hai lệnh tạo item đồng thời có thể gây `errSecDuplicateItem`. Cần retry có kiểm soát và không làm mất refresh token mới.
3. Item **đã tồn tại từ bản app cũ** có thể có `kSecAttrAccessible` khác. `SecItemUpdate` chỉ cập nhật data, không tự nâng chính sách Keychain; cần migration được kiểm thử để đảm bảo item cũ có class phù hợp.
4. Trên thiết bị khóa, API có thể trả lỗi do quyền truy cập Keychain; ứng dụng không nên fallback sang plaintext hoặc âm thầm chấp nhận token không hợp lệ.
5. Với nhiều tài khoản, dùng định danh account/tenant an toàn làm **key của item**, không dùng token thật làm `kSecAttrAccount`. Cần kiểm tra app session hiện tại trước khi lấy item.
6. Xóa item local khi logout chỉ giải quyết bản lưu trên thiết bị; vẫn cần **revoke refresh token tại AS** theo khả năng/chính sách và xử lý access token còn hạn.
7. `String`/`Data` có thể tồn tại tạm trong memory; không thể cam kết xóa sạch mọi bản sao do runtime/OS tạo. Giảm thời gian sống, không in dữ liệu nhạy cảm.

## 7. Android Keystore: khóa được bảo vệ, ciphertext ở app-private storage

**Android Keystore** quản lý khóa mật mã và hạn chế việc xuất vật liệu private/secret key. Ứng dụng có thể tạo một khóa AES chỉ dùng để mã hóa/giải mã và dùng nó để bảo vệ refresh token trước khi ghi **ciphertext** vào file trong sandbox của ứng dụng.

~~~mermaid
flowchart LR
    T["Refresh token nhận từ AS"]
    K["Android Keystore\nAES key non-exportable"]
    E["AES-GCM authenticated encryption"]
    F[("Private app file\nversion + IV + ciphertext/tag")]
    M["Access token trong memory"]
    AS["Authorization Server / token endpoint"]
    API["Orders API"]

    T --> E
    K -->|"Crypto operation"| E
    E -->|"Ghi blob"| F
    F -->|"Đọc và giải mã qua Keystore"| E
    E -->|"Refresh token khi cần"| T
    T -->|"Refresh grant"| AS
    AS -->|"Access token mới"| M
    AS -->|"Refresh token mới nếu rotation"| T
    M -->|"API call đúng audience"| API
~~~

**Phân biệt đúng:** Android Keystore không phải một `SharedPreferences` đặc biệt để lưu nguyên chuỗi refresh token. Nó bảo vệ **vật liệu khóa**; ứng dụng phải tự dùng khóa để **mã hóa có xác thực** nội dung nếu chọn lưu ở file hoặc preferences.

### Những ràng buộc nên có

- Tạo khóa AES trong provider `AndroidKeyStore` bằng `KeyGenParameterSpec`, giới hạn `PURPOSE_ENCRYPT`/`PURPOSE_DECRYPT`, `BLOCK_MODE_GCM` và `ENCRYPTION_PADDING_NONE`.
- Dùng **AES-GCM** với IV/nonce mới cho mỗi lần mã hóa. Để provider **tự tạo IV khi encrypt**, lưu IV bên cạnh ciphertext/tag. Không tái sử dụng IV với cùng khóa.
- Giữ ciphertext trong **app-private storage**, không external/shared storage. Quy định loại trừ file khỏi cloud backup/device transfer khi khóa gắn với thiết bị không thể phục hồi.
- Không lưu khóa AES ở source, preferences, `BuildConfig` hay cùng file dưới dạng plaintext.
- Một số thiết bị cung cấp TEE/hardware-backed Keystore hoặc **StrongBox**. Tính khả dụng khác nhau; nếu yêu cầu phần cứng, cần kiểm tra và có chiến lược sản phẩm khi không đạt. Không giả định StrongBox luôn có.
- Cần xử lý **key invalidation**, file được restore nhưng thiếu khóa, thay đổi biometric nếu key policy ràng buộc, hoặc storage blob hỏng. Hành vi an toàn là xóa trạng thái không thể tin cậy và yêu cầu user đăng nhập lại, không bỏ mã hóa.

### Về `EncryptedSharedPreferences`

AndroidX `EncryptedSharedPreferences` đã được tài liệu Android đánh dấu **deprecated** ở phiên bản `security-crypto 1.1.0`, nên tránh lấy các đoạn mẫu cũ làm kiến trúc mới. Hướng thay thế không phải **lưu raw token trong `SharedPreferences`**: vẫn cần **mã hóa bằng cơ chế bảo vệ khóa phù hợp**, ví dụ Android Keystore + authenticated encryption và app-private file. Với sản phẩm hiện có, migration phải được thiết kế/test kỹ để không làm lộ token hoặc mất phiên hàng loạt.

## 8. Kotlin: ví dụ Android Keystore + AES-GCM + file được bảo vệ

Ví dụ Kotlin cho **Android API 23+**. Ứng dụng sử dụng `AndroidKeyStore` để tạo khóa AES và `AtomicFile` để lưu blob đã mã hóa. Đây là **một tài khoản và một mục refresh token**; phần xác thực OAuth, đồng bộ token rotation và xử lý lỗi người dùng phải triển khai bên ngoài.

~~~kotlin
import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.io.FileNotFoundException
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

object RefreshTokenVault {
    private const val ALIAS = "orders.refresh.aes.v1"
    private const val BLOB = "orders-refresh-v1.enc"
    private const val VERSION: Byte = 1
    private val AAD = "orders.refresh.v1".toByteArray(Charsets.UTF_8)

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore")
        store.load(null)

        (store.getKey(ALIAS, null) as? SecretKey)?.let {
            return it
        }

        val gen = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore"
        )
        val spec = KeyGenParameterSpec.Builder(
            ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or
                KeyProperties.PURPOSE_DECRYPT
        )
            .setKeySize(256)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(
                KeyProperties.ENCRYPTION_PADDING_NONE
            )
            .setRandomizedEncryptionRequired(true)
            .build()

        gen.init(spec)
        return gen.generateKey()
    }

    private fun file(context: Context) =
        AtomicFile(File(context.filesDir, BLOB))

    fun save(context: Context, token: ByteArray) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        cipher.updateAAD(AAD)

        val ciphertextWithTag = cipher.doFinal(token)
        val iv = cipher.iv  // IV do provider tạo mới

        val blob = ByteBuffer.allocate(
            2 + iv.size + ciphertextWithTag.size
        )
            .put(VERSION)
            .put(iv.size.toByte())
            .put(iv)
            .put(ciphertextWithTag)
            .array()

        val atomic = file(context)
        val output = atomic.startWrite()
        try {
            output.write(blob)
            atomic.finishWrite(output)
        } catch (e: Exception) {
            atomic.failWrite(output)
            throw e
        }
    }

    fun load(context: Context): ByteArray? {
        val blob = try {
            file(context).openRead().use { it.readBytes() }
        } catch (e: FileNotFoundException) {
            return null
        }

        require(blob.size >= 2 + 12 + 16) {
            "Invalid encrypted token blob"
        }

        val input = ByteBuffer.wrap(blob)
        require(input.get() == VERSION) {
            "Unsupported storage version"
        }

        val ivLength = input.get().toInt() and 0xff
        require(ivLength == 12 && input.remaining() >= 16 + ivLength) {
            "Invalid GCM parameters"
        }

        val iv = ByteArray(ivLength).also { input.get(it) }
        val ciphertextWithTag = ByteArray(input.remaining())
            .also { input.get(it) }

        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(
            Cipher.DECRYPT_MODE,
            key(),
            GCMParameterSpec(128, iv)
        )
        cipher.updateAAD(AAD)
        return cipher.doFinal(ciphertextWithTag)
    }

    fun delete(context: Context) {
        file(context).delete()
    }
}
~~~

**Ý nghĩa bảo mật của ví dụ:**

- `ciphertextWithTag` bao gồm ciphertext và GCM authentication tag; nếu dữ liệu, IV hoặc AAD bị sửa, giải mã phải thất bại.
- IV 12 byte phù hợp cấu hình GCM dùng trong ví dụ. Khi định dạng blob đổi, cần version và quá trình migration có kiểm soát; không cố decode mọi blob bằng “đoán định dạng”.
- `AAD` ràng buộc ciphertext với mục đích lưu trữ của app. Với multi-account, cần thiết kế context/account binding đáng tin cậy, chống tráo ciphertext giữa các tài khoản.
- `AtomicFile` giảm nguy cơ ghi dở khi ứng dụng crash. Nhưng **ghi file nguyên tử không tự bảo đảm atomicity với refresh token rotation tại AS**: vẫn phải điều phối request refresh, việc commit token mới và phục hồi lỗi.
- Nếu file đã được restore sang thiết bị khác nhưng khóa Keystore không có, giải mã thất bại. **Không fallback plaintext, không tự dùng một khóa hardcoded**, mà xóa blob không đọc được, thông báo và khởi động lại authorization flow.
- Ví dụ **không có auth-gated key** để minh họa background-compatible storage; với tác vụ nhạy cảm cần user presence, triển khai key policy riêng và kiểm thử tính khả dụng khi thiết bị khóa.
- Một thiết bị/OS có thể có giới hạn thuật toán/kích cỡ khóa/StrongBox; handle exception và không hạ cấp thuật toán tùy ý. Dữ liệu trong `ByteArray` cũng có thể được sao chép vào memory của runtime.
- Thực hiện I/O và phép toán Keystore trên dispatcher/luồng nền phù hợp, không chặn main/UI thread; khóa Keystore hoặc phần cứng có thể mất thời gian xử lý.

Ví dụ vẫn chưa thay thế thư viện bảo mật/kiến trúc sản xuất: cần giới hạn kích thước blob khi đọc, serialize các lần ghi, chống rollback cũ, backup exclusion, theo dõi error an toàn và kiểm thử các thiết bị mục tiêu. **Không chạy hoặc xem snippet này là proof rằng app đạt chuẩn bảo mật sản xuất.**

## 9. Backup, restore, di chuyển thiết bị và cài lại app

Mobile secure storage thường gặp lỗi **mất khóa sau restore** hoặc **giữ token lâu hơn dự tính sau uninstall**.

### iOS

- Các lớp `ThisDeviceOnly` không di chuyển item Keychain sang một thiết bị khác qua restore; client cần **đăng nhập lại** để nhận credential mới.
- Các lớp không có `ThisDeviceOnly` có hành vi backup/migration khác. Việc cho phép token di chuyển phải là một quyết định có chủ đích.
- Keychain có thể tồn tại qua một số lần gỡ và cài lại app. Trên lần mở đầu, không nên chỉ thấy refresh token cũ rồi tự gán nó vào user khác; cần định danh account/session và chính sách first-run/cleanup rõ ràng.
- Với passcode-gated class, người dùng tắt passcode có thể khiến item bị xóa. App cần chuyển về trạng thái cần đăng nhập thay vì rơi vào vòng lặp lỗi.

### Android

- Khóa Android Keystore gắn với môi trường cài đặt/thiết bị; **không giả định key sẽ có sau khi app data được restore sang máy mới**.
- Nếu backup mang theo `orders-refresh-v1.enc` nhưng không có key, app sẽ không giải mã được. Nên **loại trừ blob token/ciphertext khỏi backup và device-transfer**, theo cấu hình version Android áp dụng.
- Với Android hiện đại, rà **`dataExtractionRules`**, **`fullBackupContent`**, cấu hình backup/transfer và các kênh MDM/thiết bị. Chỉ đặt `allowBackup=false` mà không kiểm tra hành vi trên các OS version/thiết bị là chưa đủ để tự tin.
- Khi KeyStore alias bị mất, key invalidated hoặc blob hỏng, xử lý rõ ràng: xóa trạng thái local không tin cậy, revoke grant nếu có cơ hội hợp lệ và yêu cầu user đăng nhập lại.
- Không lưu token trong external/shared storage hoặc thư mục có thể được đồng bộ bởi công cụ bên ngoài theo mặc định.

**Hành vi đúng không nhất thiết là “tài khoản luôn tự đăng nhập lại sau khi đổi máy”**. Với credential nhạy cảm, buộc authorization flow mới thường an toàn hơn migrate refresh token đã cấp cho một thiết bị khác.

## 10. Biometric gating không có nghĩa token không thể bị lạm dụng

Face ID, Touch ID và Android `BiometricPrompt` có thể dùng để yêu cầu người đang sử dụng thiết bị xác thực **trước khi truy xuất khóa hoặc cho phép hành động nhạy cảm**.

| Nhu cầu | Cách triển khai hợp lý | Cạm bẫy |
|---|---|---|
| Xác nhận user trước thao tác chuyển tiền/xóa dữ liệu | BiometricPrompt/`SecAccessControl` cho khóa/operation nhạy cảm; server xác thực lại khi cần | Chỉ thấy “biometric success” rồi bỏ kiểm tra quyền API |
| Mở khóa refresh token chỉ khi foreground | Keychain class phù hợp hoặc Android auth-bound key theo policy | Không xem xét fallback khi biometric không khả dụng |
| Background sync | Dùng cơ chế lưu trữ đủ an toàn nhưng không cần interactive prompt mỗi lần | Bật yêu cầu biometric mỗi lần decrypt khiến background job lỗi hoặc phát sinh bypass |
| Thiết bị không có secure hardware hoặc biometric | Chính sách sản phẩm có thể giảm khả năng hoặc yêu cầu reauthentication | Âm thầm dùng key plaintext để “tiếp tục hoạt động” |
| Đổi biometric, xóa passcode | Xác định khả năng key bị invalidated theo lựa chọn policy | App crash hoặc mất token mà không thể phục hồi phiên an toàn |

**Biometric là một phương tiện kiểm soát truy cập tại thiết bị, không phải quyền OAuth.** Resource Server vẫn phải kiểm tra access token, issuer, audience, scope, thời gian, người dùng và quyền trên đối tượng. Nếu attacker kiểm soát tiến trình sau khi user đã unlock, thao tác ký/giải mã vẫn có thể bị lạm dụng trong cửa sổ được phép.

## 11. Refresh token rotation, crash safety và nhiều tài khoản

Refresh token thường có vòng đời dài hơn access token. Khi AS áp dụng **rotation**:

~~~text
Trạng thái trước refresh:
    Local secure storage = RT1

Client gửi RT1 tới AS:
    AS xác minh grant/client, vô hiệu RT1
    AS trả AT2 và RT2

Trạng thái sau refresh thành công:
    Local secure storage = RT2
    Memory = AT2

Nếu client dùng lại RT1:
    AS có thể phát hiện reuse/replay
    và xử lý token family theo policy
~~~

Vì vậy, lưu trữ mobile phải giải quyết **đồng thời** ba vấn đề:

1. **Single-flight refresh:** không để hai request cùng lúc đọc RT1, cùng đổi và tạo reuse giả. Dùng mutex/actor/serialized queue trong app; nếu app có nhiều process, cần coordination phù hợp hơn một mutex chỉ trong một process.
2. **Commit token mới an toàn:** chỉ coi refresh thành công khi RT2 đã được lưu đúng cách. Cần thiết kế khi AS trả RT2 nhưng app crash trước lúc save: không tiếp tục thử RT1 vô hạn; thường phải đưa user về reauthentication hoặc cơ chế recovery do AS hỗ trợ.
3. **Account isolation:** item/key của account A và B được phân vùng theo định danh tin cậy. Logout/switch account phải thay đúng item và xóa access token in-memory tương ứng; không gửi RT của A trong session B.

**Race khó tránh hoàn toàn:** khi server đã rotation nhưng app mất kết nối trước khi nhận RT2, client có thể không có credential mới. Không khắc phục bằng việc lưu RT1 vĩnh viễn hoặc dùng cơ chế replay không giới hạn; dùng chính sách phục hồi được AS hỗ trợ, hoặc đăng nhập lại.

### Token cũ và rollback

Ứng dụng có thể phục hồi từ app snapshot/backup/cached data cũ, vô tình lấy lại RT1 đã bị rotation. **Storage encryption không chống rollback trạng thái server**. AS phải nhận biết family/sequence/rotation và từ chối reuse; client xử lý kết quả `invalid_grant` bằng cách dừng refresh và đưa user qua authorization flow hợp lệ, không xóa toàn bộ dữ liệu ứng dụng một cách vô điều kiện.

## 12. Chuyển từ access token sang refresh token và xử lý lỗi

Một quy trình quản lý credential hợp lý:

~~~mermaid
flowchart TD
    A["App khởi động"] --> B{"Có refresh token đọc được?"}
    B -->|"Không"| L["Authorization Code + PKCE"]
    B -->|"Có"| C["Giữ refresh token trong secure storage"]
    C --> D{"Access token còn hợp lệ ở client?"}
    D -->|"Có"| E["Gửi API request"]
    D -->|"Không hoặc gần hết hạn"| F["Single-flight refresh tại AS"]
    F --> G{"Refresh thành công?"}
    G -->|"Có"| H["Lưu RT mới an toàn nếu rotation"]
    H --> E
    G -->|"Không, invalid_grant/revoked"| I["Dọn trạng thái, yêu cầu đăng nhập lại"]
    G -->|"Lỗi mạng tạm thời"| J["Retry có giới hạn, không log token"]
    J --> F
    E --> K{"API trả 401 invalid_token?"}
    K -->|"Có"| F
    K -->|"Không"| M["Tiếp tục theo response/policy"]
~~~

Sơ đồ minh họa: **không làm refresh vô hạn khi API trả 401**. Cần phân biệt clock skew, token thực sự hết hạn, bearer token bị revoked, sai audience, scope và lỗi mạng. Nếu refresh thành công mà API vẫn trả 401, có thể là cấu hình issuer/audience hoặc policy; không nên tiếp tục refresh liên tục.

Trên mobile, **refresh token thuộc token endpoint của AS**. Không đưa RT vào `Authorization: Bearer` khi gọi Resource Server. ID token dành cho client OIDC, không dùng gọi API thay access token; `scope` của token không tự cho quyền với mọi bản ghi thuộc tenant.

## 13. Sender-constrained token: DPoP, mTLS và khóa thiết bị

Bảo vệ token at rest làm giảm khả năng bị sao chép từ storage. Nhưng nếu access token đã được lấy đi nguyên vẹn, **bearer token** vẫn có thể bị replay cho đến khi hết hạn hoặc bị từ chối.

**Sender-constrained access token** có thể bổ sung ràng buộc bằng chứng khóa:

- **DPoP (RFC 9449):** client ký proof cho request (method, URI, thời gian, `jti`, `ath` đối với API), AS/RS kiểm tra khóa gắn với token, thường qua `cnf.jkt`.
- **mTLS certificate-bound access token (RFC 8705):** Resource Server xác minh certificate/key binding theo contract; cách triển khai mobile cần cân nhắc quản lý certificate và các tầng TLS.
- **Khóa non-exportable:** có thể sinh khóa proof-of-possession trong iOS Secure Enclave/Keychain hoặc Android Keystore nếu thuật toán/API/profile được hỗ trợ. Server vẫn phải xác minh proof, replay và token binding.

**Không đồng nhất “khóa không xuất được” với “khóa không thể bị dùng trái phép”.** Nếu attacker điều khiển app hoặc OS, họ có thể cố gọi API ký bằng khóa vẫn đang nằm trong thiết bị. DPoP cũng không tự xác thực user hoặc thay thế refresh rotation, scope, audience và revocation.

Ví dụ request DPoP:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: DPoP <DPOP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_PROOF_JWT>
~~~

Bằng chứng khóa được bảo vệ thêm lớp storage; **cả access token và proof vẫn phải được xử lý an toàn**. Không ghi DPoP proof hay raw key vào log để “debug”.

## 14. HTTPS, logging, deep links và dữ liệu ngoài kho

Token có thể bị lộ **sau khi đã lưu an toàn** vì hoạt động truyền tải hoặc giám sát.

| Đường rò | Cách phòng ngừa |
|---|---|
| HTTP không TLS hoặc bỏ xác minh server certificate | Bắt buộc HTTPS, kiểm tra certificate/hostname và cấu hình networking đúng |
| `Authorization` header bị log ở client/network interceptor | Redact toàn bộ bearer token, refresh token, client assertion và cookie phiên |
| Crash reporter/analytics tự đính kèm request hoặc response | Cấu hình lọc secrets và PII trước khi gửi SDK bên thứ ba |
| Copy token ra clipboard/debug console | Không có tính năng copy token; dùng token reference an toàn cho hỗ trợ |
| Query/deep link chứa access/refresh token | Không đưa token vào URL; với code flow chỉ dùng authorization code đúng redirect và PKCE |
| WebView/Javascript bridge đọc credential mobile | Dùng system browser cho OAuth; không chuyển bí mật vào web content không tin cậy |
| Log JWT payload vì “chỉ là Base64url” | Payload JWS có thể chứa PII; không log decoded claims ngoài trường đã allowlist |
| HTTP proxy trong môi trường debug | Chỉ bật debug tools khi được kiểm soát, không đưa credential production vào bản debug |
| Screenshot/UI overlay/notification hiển thị token | Không hiển thị token trên UI; hạn chế thông tin nhạy cảm trong notification/app switcher preview khi cần |

**Không nên dùng certificate pinning như giải pháp duy nhất** hoặc thay TLS validation tiêu chuẩn bằng callback “accept all”. Pinning có trade-off vận hành và thay khóa; áp dụng theo threat model và cơ chế backup được thiết kế cẩn thận.

### Server vẫn phải kiểm tra access token đầy đủ

Ngay cả khi ứng dụng mobile có Keychain/Keystore tốt:

- **JWT access token:** Resource Server xác minh chữ ký, `iss`, `aud`, `exp`, loại token và quyền; `scope` chỉ có giá trị từ token đã xác minh.
- **Opaque access token:** Resource Server introspect/tra trạng thái đáng tin cậy và kiểm tra `active`, audience, scope và ACL.
- **Thu hồi:** API cần biết trạng thái revoke theo kiến trúc (introspection, denylist, grant state hoặc TTL); xóa local token không làm mọi bản sao bên ngoài tự mất hiệu lực.

Secure storage là một lớp của **defense in depth**, không phải thay thế việc kiểm tra quyền ở API.

## 15. Logout, mất thiết bị và nghi token bị lộ

Khi user đăng xuất hoặc thiết bị mất/compromise, cần phân biệt **local cleanup** và **server-side revocation**.

~~~text
Logout hợp lệ tại app:
    1. Dừng request/refresh đang chạy nếu có thể.
    2. Chọn đúng account và grant đang sử dụng.
    3. Gửi revocation request cho refresh token/grant khi AS hỗ trợ.
    4. Xóa local secure storage và memory token.
    5. Xóa app session/cache nhạy cảm và chuyển về signed-out state.
    6. Theo dõi lỗi revoke theo chính sách thay vì khẳng định
       mọi token ở API đã bị vô hiệu ngay.

Thiết bị bị mất hoặc nghi compromise:
    1. User/admin dùng kênh quản lý tin cậy để revoke phiên/grant.
    2. AS ngăn refresh hoặc token issuance trái phép.
    3. API áp dụng cơ chế từ chối access token còn hạn nếu cần.
    4. Rà audit token reference và phạm vi dữ liệu đã truy cập.
    5. Chỉ cấp lại credential sau khi xử lý thiết bị/account.
~~~

Ví dụ yêu cầu revocation RFC 7009 (client public theo chính sách AS có thể dùng request tương ứng, ví dụ kèm `client_id` và các điều kiện xác thực/ràng buộc khác; không có hardcoded client secret):

~~~http
POST /revoke HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

token=<REFRESH_TOKEN>&token_type_hint=refresh_token&client_id=orders-mobile
~~~

**Response HTTP 200 không bảo đảm JWT access token đã cấp bị chặn tức thì tại mọi API.** AS có thể ngừng cấp token mới, nhưng Resource Server tự xác minh JWT có thể tiếp tục chấp nhận token đến `exp` nếu không có cơ chế revocation state. Ứng dụng cần hiểu chính sách revocation/propagation của hệ thống.

Khi app cần hỗ trợ nhiều thiết bị, một thao tác logout có thể chỉ thu hồi **grant/phiên của thiết bị hiện tại** hoặc tất cả thiết bị theo product policy. Không tự xóa token người dùng trên thiết bị khác nếu không có yêu cầu rõ ràng; ngược lại, khi mất thiết bị cần cơ chế quản trị revoke đúng bản ghi thiết bị/grant.

## 16. Case study: ứng dụng đơn hàng có đăng nhập dài ngày

Giả sử `orders-mobile` dùng OAuth Authorization Code + PKCE và nhận:

- **Access token AT1:** JWT đã ký, `aud=https://orders-api.example.test`, `scope=orders:read`, còn hạn 10 phút.
- **Refresh token RT1:** opaque, AS cho phép rotation theo policy, chỉ dùng tại token endpoint.
- **ID token I1:** OIDC token để client xác minh user khi đăng nhập, không gửi vào Orders API.

Trên iPhone, app lưu RT1 trong **Keychain `WhenUnlockedThisDeviceOnly`**; trên Android, app lưu **AES-GCM ciphertext** tại app-private storage, với key trong Android Keystore. AT1 chỉ giữ trong memory khi đủ.

### Dòng thời gian

| Thời điểm | Sự kiện | Cách xử lý |
|---|---|---|
| 09:00 | User login qua system browser + PKCE | AS cấp AT1/RT1 theo grant |
| 09:01 | App lưu RT1 an toàn và gọi Orders API bằng AT1 | API vẫn kiểm tra chữ ký/audience/scope/ACL |
| 09:08 | AT1 gần hết hạn, app cần token mới | Single-flight refresh dùng RT1 |
| 09:08:01 | AS trả AT2 và RT2, RT1 bị vô hiệu | App commit RT2 vào secure storage; không dùng lại RT1 |
| 09:09 | App bị kill/restart | Access token trong memory mất; RT2 có thể được đọc khi OS cho phép |
| 09:10 | Thiết bị Android được restore sang máy mới, file RT2 mã hóa có nhưng key Keystore không có | Không decrypt được; không fallback plaintext, yêu cầu login lại |
| 09:11 | User chọn logout | Xóa local RT2 và yêu cầu revoke tại AS theo policy |
| 09:12 | Bản sao AT2 bị nghi lộ trước logout | API có thể cần denylist/introspection/TTL để chặn; local delete không đủ |

### Bốn quyết định kiến trúc

1. **Không lưu raw token trong `SharedPreferences`/`UserDefaults`** chỉ để tránh phải viết lớp secure storage.
2. **Không coi Keychain/Keystore là phiên đăng nhập hợp lệ vĩnh viễn**: refresh token có thể đã revoke, user mất quyền hoặc grant bị gỡ.
3. **Không làm mới token song song không kiểm soát** vì rotation có thể biến hai request hợp lệ thành tình huống reuse.
4. **Không xem việc key không đọc được sau migration là lỗi cần “bỏ qua mã hóa”**; user đăng nhập lại là hành vi an toàn hơn.

## 17. Ma trận kiểm thử Mobile secure storage

| Test | Cách kiểm tra trong staging/test device | Kết quả mong đợi |
|---|---|---|
| **T1 — Dữ liệu at rest** | Kiểm tra app-private files/preferences/database | Không có raw access/refresh token ở dạng plaintext |
| **T2 — Keychain accessibility** | Lock/unlock và reboot iOS; truy xuất item | Hành vi đúng class đã chọn; không fallback thiếu an toàn |
| **T3 — iOS backup/migration** | Restore sang thiết bị khác với `ThisDeviceOnly` | Item không di chuyển, app yêu cầu login hợp lệ |
| **T4 — iOS uninstall/reinstall** | Gỡ và cài lại app theo OS mục tiêu | Không tái dùng token cũ cho user/tenant khác; cleanup đúng policy |
| **T5 — Android backup/restore** | Restore app-private ciphertext mà không có key | Decrypt thất bại an toàn, không lưu plaintext |
| **T6 — Android key invalidation** | Mô phỏng mất/invalidated Keystore alias | Không crash loop; xóa trạng thái lỗi và reauthenticate |
| **T7 — AES-GCM tampering** | Đổi IV/ciphertext/tag hoặc AAD trong test blob | Giải mã thất bại; không chấp nhận dữ liệu giả |
| **T8 — Refresh rotation** | RT1 → RT2 và app restart ngay sau commit | RT2 được dùng, RT1 không bị gửi lại |
| **T9 — Concurrent refresh** | Kích hoạt nhiều request cùng nhận 401/expiry | Single-flight, không gây reuse giả hay loop |
| **T10 — Crash giữa response và lưu** | Mô phỏng crash trước commit RT mới | Phục hồi an toàn hoặc login lại; không replay vô hạn |
| **T11 — Multi-account** | Chuyển giữa account A/B | Token không bị dùng chéo, logout xóa đúng mục |
| **T12 — Background locked device** | Chạy job khi thiết bị khóa | Hành vi đúng accessibility/auth policy; không bỏ khóa bảo vệ |
| **T13 — Biometrics changed** | Đổi biometric/passcode trong thiết bị test | Key/item invalidation được xử lý phù hợp |
| **T14 — Logging/analytics** | Dùng giá trị token giả làm canary trong môi trường test | Không xuất hiện trong log/crash/analytics/network trace không được phép |
| **T15 — Deep link interception** | Thử callback sai state/code/redirect | Bị từ chối; chỉ đổi code sau xác minh PKCE/state |
| **T16 — Lost device** | Revoke grant/refresh từ AS, thử dùng token test | AS từ chối refresh, RS theo đúng SLA revoke |
| **T17 — DPoP proof** | Gửi token bound không kèm khóa/proof | API từ chối theo profile |
| **T18 — Root/jailbreak analysis** | Phân tích trên thiết bị test được phép | Ghi rõ giới hạn bảo vệ; không tuyên bố mật mã ngăn được mọi runtime hook |

**Không dùng token production thật cho kiểm thử extraction, log canary hoặc instrument trên thiết bị test.** Sử dụng credential giả/staging và chỉ thực hiện kiểm tra trong môi trường có quyền.

## 18. Checklist triển khai trước phát hành

1. **Phân loại credential:** access, refresh, ID token, code verifier, DPoP key và session; không lưu tất cả bằng một chính sách chung.
2. **OAuth native đúng chuẩn:** Authorization Code + PKCE S256, system browser, callback/`state` được kiểm tra, không hardcode client secret.
3. **Ưu tiên giảm dữ liệu at rest:** access token ngắn hạn trong memory nếu đủ; chỉ persist những gì thật sự cần.
4. **iOS Keychain:** dùng `SecItem*`, chọn `kSecAttrAccessible` theo foreground/background, cân nhắc `ThisDeviceOnly` và Keychain Access Groups.
5. **Android Keystore:** tạo khóa non-exportable, dùng authenticated encryption như AES-GCM, ciphertext ở app-private storage, không plaintext preferences.
6. **Đừng lấy mẫu deprecated làm chuẩn mới:** rà trạng thái `EncryptedSharedPreferences` và migration; bảo vệ dữ liệu ngay cả khi dùng storage API khác.
7. **Backup/restore:** xác định device migration, loại trừ blob nếu key không đi theo, xử lý restore/mất key bằng login lại.
8. **Key lifecycle:** xử lý rotate/invalidate, passcode/biometric changes và lỗi hardware-backed/StrongBox không khả dụng.
9. **Refresh rotation:** serialize request, commit token mới an toàn, xử lý crash/mạng lỗi/`invalid_grant` và chống rollback.
10. **Multi-account:** khóa lưu trữ gắn với account/tenant đã được xác thực, không dùng token A trong phiên B.
11. **Biometric đúng vai trò:** gate thao tác nhạy cảm khi cần; không coi prompt thành quyền server và không làm background task phải bypass.
12. **Bảo vệ lúc sử dụng:** TLS, không log token, không URL/clipboard/debug, không nhúng credential vào WebView/JavaScript bridge.
13. **Sender constraints nếu phù hợp:** bảo vệ khóa DPoP/mTLS và kiểm tra proof ở API, không chỉ cất key an toàn.
14. **Server validation:** API kiểm tra issuer, audience, time, token purpose, scope và object/tenant policy; Keychain/Keystore không thay bước này.
15. **Logout và lost device:** xóa local, revoke grant/refresh token tại AS theo policy, chặn access token còn hạn nếu cần, không nhầm logout với thu hồi tức thì.
16. **Kiểm thử trên device thật:** lock/reboot, background, backup/restore, uninstall, device migration, root/jailbreak threat, race và crash.
17. **Bảo vệ audit:** chỉ log token/grant reference và reason code; không lưu bearer token, refresh token, client secret, private key.
18. **Tài liệu hóa threat model:** ghi rõ giả định về malware, OS compromise, khả năng hardware-backed và rủi ro còn lại.

**Kết luận:** Mobile secure storage không chỉ là chọn Keychain hoặc Keystore. Một thiết kế đáng tin cần **phân loại token**, giữ ít credential nhất có thể, **bảo vệ khóa và dữ liệu at rest**, xử lý **backup/restore, biometric, background và refresh rotation**, đồng thời có **thu hồi ở AS/Resource Server** khi thiết bị mất hoặc token lộ. **Keychain/Android Keystore giảm đáng kể nguy cơ rò rỉ ở tầng lưu trữ, nhưng mọi access token vẫn phải được AS/API kiểm tra và chịu giới hạn scope, audience, thời gian và trạng thái cấp quyền.**

### Tài liệu chuẩn và hướng dẫn nền tảng

- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): system browser/external user agent và redirect cho native client.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): bảo vệ authorization code exchange.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh rotation, bảo vệ OAuth và token replay.
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009) và [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): thu hồi và xác minh trạng thái token.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token theo bằng chứng khóa.
- [Apple — Restricting Keychain Item Accessibility](https://developer.apple.com/documentation/security/restricting-keychain-item-accessibility): lớp `kSecAttrAccessible`, device-only và background access.
- [Apple — Keychain item attributes](https://developer.apple.com/documentation/security/item-attribute-keys-and-values): các Keychain Security attributes.
- [Android Developers — Android Keystore System](https://developer.android.com/privacy-and-security/keystore): quản lý khóa và hardware-backed/StrongBox.
- [Android Developers — KeyGenParameterSpec](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec): giới hạn usage và cấu hình mã hóa Android.
- [Android Developers — EncryptedSharedPreferences API](https://developer.android.com/reference/androidx/security/crypto/EncryptedSharedPreferences): trạng thái deprecated và lưu ý backup.
- [OWASP MASTG — Android Data Storage](https://mas.owasp.org/MASTG/0x05d-Testing-Data-Storage/): bảo vệ dữ liệu nhạy cảm khi lưu trên thiết bị.
- [OWASP MASVS — Mobile Application Security](https://mas.owasp.org/MASVS/): tiêu chí thiết kế và kiểm thử bảo mật mobile.
