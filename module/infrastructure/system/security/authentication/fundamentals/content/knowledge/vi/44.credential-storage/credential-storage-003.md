# Keychain và keystore

## Mục tiêu học tập

Một ứng dụng di động thường cần giữ refresh token, khóa riêng dùng xác thực thiết bị, seed mã hóa hoặc thông tin đăng nhập của một dịch vụ. Nếu lưu các giá trị này trong file cấu hình, cơ sở dữ liệu ứng dụng hoặc vùng lưu trữ có thể đọc trực tiếp, việc sao chép dữ liệu ứng dụng có thể làm lộ credential và cho phép attacker mạo danh người dùng.

**Keychain** trên nền tảng Apple và **Android Keystore** trên Android là các cơ chế nền tảng để lưu trữ hoặc sử dụng credential, khóa mật mã và dữ liệu nhạy cảm với sự bảo vệ của hệ điều hành. Chúng cung cấp ranh giới truy cập, chính sách sử dụng khóa và trong một số thiết bị khả năng bảo vệ bằng phần cứng. Ứng dụng có thể yêu cầu hệ điều hành thực hiện thao tác ký hoặc giải mã mà không cần lấy private key thô ra khỏi vùng bảo vệ.

Keychain và Keystore không phải là một giải pháp thần kỳ chống mọi loại malware. Chúng giảm nguy cơ lộ dữ liệu khi file ứng dụng hoặc backup bị sao chép, nhưng một ứng dụng đang chạy dưới quyền người dùng vẫn có thể được phép sử dụng credential. Nếu process bị chiếm quyền, attacker có thể gọi API hợp lệ, đọc dữ liệu sau giải mã hoặc thao túng giao diện để lừa người dùng xác thực.

Bài học thuộc chương **Lưu trữ credential** của mô-đun **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Mô-đun tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Keychain và Keystore là lớp lưu trữ phía thiết bị giúp bảo vệ token, khóa và credential trong suốt vòng đời xác thực.

Sau bài học, bạn có thể:

- Phân biệt secure storage, key management, encryption at rest và hardware-backed key protection.
- Mô tả vai trò của Apple Keychain, Secure Enclave, Android Keystore và StrongBox.
- Chọn loại dữ liệu phù hợp để lưu trực tiếp, mã hóa rồi lưu, hoặc không lưu trên thiết bị.
- Thiết kế lưu access token, refresh token, private key, TOTP seed và recovery material.
- Cấu hình quyền truy cập theo trạng thái khóa thiết bị, passcode, biometric và mục đích sử dụng.
- Hiểu access group, app sandbox, key alias, key attestation và giới hạn backup/synchronization.
- Thiết kế enrollment, rotation, revocation, logout và xử lý khi thiết bị bị mất.
- Tránh hardcode secret, lưu token trong log, local storage hoặc file không được bảo vệ.
- Viết ví dụ Swift và Kotlin/Java, cùng bộ kiểm thử và checklist triển khai.

## 1. Credential storage giải quyết vấn đề gì?

Credential là dữ liệu hoặc vật mang bí mật/khóa mà hệ thống dùng để xác thực hoặc cho phép một thao tác. Trên thiết bị di động, credential có thể gồm:

- Refresh token hoặc access token.
- Private key của thiết bị dùng ký challenge.
- Client certificate hoặc khóa riêng tương ứng.
- Seed TOTP, recovery code hoặc secret dùng cho một giao thức.
- Mật khẩu được lưu theo yêu cầu đặc biệt của ứng dụng (thường nên tránh lưu).
- Khóa mã hóa dữ liệu cục bộ hoặc khóa bọc khóa.
- Cookie phiên trong ứng dụng có embedded browser hoặc web view.

Rủi ro không chỉ nằm ở việc attacker đọc được file. Credential có thể lộ qua backup, crash dump, log, analytics, clipboard, screenshot, debug build, thiết bị đã root/jailbreak, thư viện bên thứ ba hoặc một API chẩn đoán quá rộng.

### Mục tiêu bảo vệ

Một thiết kế lưu trữ credential cần xem xét:

1. **Confidentiality:** người không được phép không thể đọc secret hoặc private key.
2. **Integrity:** attacker không thể thay credential, metadata hoặc policy mà ứng dụng tin cậy.
3. **Isolation:** ứng dụng khác không thể đọc dữ liệu của app.
4. **Key non-exportability:** private key có thể được sử dụng nhưng không xuất ra dạng byte thô.
5. **Access control:** thao tác nhạy cảm chỉ diễn ra khi điều kiện thiết bị/người dùng phù hợp.
6. **Lifecycle:** credential có thể được tạo, dùng, xoay vòng, thu hồi và xóa.
7. **Recovery:** mất thiết bị hoặc gỡ ứng dụng không tạo ra đường khôi phục yếu.
8. **Auditability:** hệ thống backend có thể phát hiện credential bị thay thế, thu hồi hoặc sử dụng bất thường.

### Phân biệt các lớp bảo vệ

| Lớp | Bảo vệ điều gì | Ví dụ |
| --- | --- | --- |
| App sandbox | Cách ly file và process giữa ứng dụng | App A không đọc thư mục riêng của App B |
| Keychain/Keystore | Lưu hoặc thao tác với credential/key theo policy | Lưu refresh token, ký challenge |
| Secure Enclave/StrongBox | Bảo vệ một số thao tác và key material bằng phần cứng | Private key không xuất được |
| File/data encryption | Mã hóa dữ liệu ứng dụng trước khi lưu | SQLite được mã hóa bằng data key |
| Server-side control | Thu hồi và giới hạn quyền credential | Revoke refresh-token family |
| Device integrity/attestation | Cung cấp tín hiệu về trạng thái thiết bị/app | Kiểm tra key attestation hoặc app integrity |

Không lớp nào thay thế toàn bộ các lớp khác. Keychain/Keystore không tự quyết định người dùng được phép đọc đơn hàng nào; backend vẫn phải xác minh token và authorization.

## 2. Chọn đúng nơi lưu dữ liệu

Không phải dữ liệu nào cũng cần đưa vào Keychain hoặc Keystore. Trước tiên cần phân loại dữ liệu theo giá trị, khả năng tái tạo, thời hạn và tác động nếu bị lộ.

| Dữ liệu | Cách lưu phù hợp thường gặp | Lưu ý |
| --- | --- | --- |
| Access token ngắn hạn | Memory khi có thể | Tránh lưu lâu; không log |
| Refresh token | Keychain hoặc encrypted storage dựa trên Keystore | Có rotation và revocation phía server |
| Private key thiết bị | Tạo và giữ trong Keychain/Secure Enclave hoặc Android Keystore | Ưu tiên non-exportable khi phù hợp |
| Public key | App database hoặc server | Không phải secret; vẫn cần integrity và identity binding |
| TOTP seed | Secret store được bảo vệ, thường mã hóa bằng key trong Keystore | Chỉ app cần xác minh mới được đọc |
| Recovery code | Tránh lưu lâu trên thiết bị; nếu cần thì mã hóa và giới hạn truy cập | Ưu tiên hiển thị một lần và lưu ở nơi an toàn do người dùng kiểm soát |
| Password | Thông thường không lưu | Dùng password manager/OS autofill thay vì tự giữ plaintext |
| User profile/cache | App storage; mã hóa nếu nhạy cảm | Không phải mọi dữ liệu đều cần Keychain |
| Khóa mã hóa dữ liệu | Keychain/Keystore/KMS tùy nơi dữ liệu tồn tại | Tách data key và key-encryption key |
| API secret dùng chung | Không nhúng vào app mobile | Secret trong app có thể bị trích xuất |

### Không lưu mật khẩu để “đăng nhập tự động”

Ứng dụng native nên dùng OAuth/OIDC Authorization Code Flow với PKCE và browser/system authentication session khi phù hợp. Sau khi đổi authorization code, lưu refresh token trong secure storage; access token nên giữ trong memory nếu kiến trúc cho phép. Khi cần xác thực lại, dùng passkey, system credential provider hoặc flow chuẩn thay vì lưu password người dùng.

### Không nhúng client secret vào ứng dụng public

Ứng dụng mobile và browser không thể giữ client secret lâu dài trước người dùng kiểm soát thiết bị. Secret nhúng trong APK, IPA, JavaScript bundle hoặc native binary có thể bị trích xuất. Dùng public client với PKCE; credential của backend confidential client phải ở server-side secret manager.

## 3. Apple Keychain là gì?

Keychain là dịch vụ lưu trữ an toàn của các nền tảng Apple. Ứng dụng thao tác với Keychain qua Security framework, tạo item có thuộc tính và access control. Hệ điều hành quản lý việc lưu trữ, bảo vệ và kiểm soát truy cập theo entitlement, access group và accessibility class.

Keychain có thể lưu password, token, certificate, key và dữ liệu nhỏ nhạy cảm. Private key có thể được tạo hoặc sử dụng thông qua API mật mã; với một số loại key và thiết bị, private key có thể được bảo vệ bởi Secure Enclave.

### Keychain item

Một item có thể gồm:

- Class: generic password, internet password, key, certificate hoặc identity.
- Account/service/server: thuộc tính định danh item.
- Access group: nhóm ứng dụng được phép chia sẻ item theo entitlement.
- Accessibility: thời điểm và điều kiện thiết bị cho phép truy cập.
- Access control: điều kiện xác thực người dùng như passcode hoặc biometric.
- Value data hoặc key reference: dữ liệu hoặc tham chiếu khóa được bảo vệ.

Không dùng một service/account cố định cho mọi credential nếu điều đó khiến các token hoặc tài khoản khác nhau ghi đè nhau. Đặt namespace rõ ràng, quản lý version và xử lý duplicate item.

### Accessibility class

Accessibility class quy định khi nào item có thể được truy cập, ví dụ khi thiết bị đang mở khóa hoặc sau lần mở khóa đầu tiên sau khi khởi động. Các biến thể chỉ dùng trên thiết bị hiện tại giúp giới hạn việc di chuyển item qua backup/restore hoặc đồng bộ.

Các lựa chọn thường gặp trong Keychain Services gồm:

- **When unlocked:** chỉ truy cập khi thiết bị đang mở khóa.
- **After first unlock:** có thể truy cập sau khi người dùng mở khóa thiết bị lần đầu sau khi khởi động; phù hợp một số tác vụ nền nhưng phải cân nhắc rủi ro.
- **When passcode set:** yêu cầu thiết bị có passcode và có thể gắn với Secure Enclave/access control tùy loại key.
- **This device only:** item không được migrate theo backup/restore hoặc sync theo semantics của class tương ứng.

Tên class và khả năng kết hợp thay đổi theo API/platform version. Chọn theo yêu cầu thực tế, không mặc định class tiện nhất là an toàn nhất.

### Access group và Keychain sharing

Nhiều ứng dụng cùng nhà phát triển có thể chia sẻ Keychain item qua Keychain access group nếu được cấp entitlement phù hợp. Đây là ranh giới tin cậy giữa các ứng dụng cùng nhóm phát triển.

- Chỉ chia sẻ credential khi có nhu cầu sản phẩm rõ ràng.
- Không cấp access group rộng cho mọi app chỉ để tiện tích hợp.
- Kiểm tra entitlement trong signing/provisioning.
- Không xem bundle identifier giống nhau là bằng chứng đủ để chia sẻ.
- Khi gỡ hoặc chuyển ứng dụng, xử lý item cũ theo policy; không giả định uninstall luôn xóa sạch Keychain item.

Keychain item có thể tồn tại sau khi app bị gỡ trong một số trường hợp. Nếu dữ liệu cần bị xóa khi người dùng xóa tài khoản hoặc gỡ app, phải thiết kế thao tác xóa rõ ràng và có server-side revocation; đừng dựa vào uninstall làm cơ chế xóa credential.

## 4. Secure Enclave trên thiết bị Apple

Secure Enclave là một subsystem bảo mật dựa trên phần cứng, tách biệt với application processor. Nó hỗ trợ tạo và sử dụng một số loại khóa theo policy, đồng thời bảo vệ key material khỏi việc trích xuất trực tiếp qua API thông thường.

### Non-exportable private key

Với private key được bảo vệ bởi Secure Enclave, ứng dụng có thể yêu cầu ký dữ liệu bằng key reference. Ứng dụng nhận chữ ký nhưng không nhận private key thô.

Điều này giúp giảm hậu quả khi attacker đọc được file app hoặc memory của một số thành phần. Tuy nhiên:

- App bị chiếm quyền vẫn có thể gọi thao tác ký nếu policy cho phép.
- Attacker có thể điều khiển dữ liệu được ký nếu app không xác minh transaction/context.
- Secure Enclave không thay thế server-side authorization.
- Khả năng hỗ trợ thuật toán/key type phụ thuộc thiết bị và API.
- Backup/restore không biến private key Secure Enclave thành key có thể xuất.

### User presence và biometric access control

Ứng dụng có thể yêu cầu thao tác với key/item sau khi người dùng xác thực bằng passcode hoặc biometric. Access control có thể gắn với trạng thái biometric enrollment, tập biometric hiện tại hoặc yêu cầu user presence.

Ví dụ, một private key dùng ký giao dịch có thể yêu cầu biometric mỗi lần sử dụng. Khi biometric set thay đổi, policy có thể làm key không còn dùng được và yêu cầu đăng ký lại.

Không nên yêu cầu biometric cho mọi thao tác nhỏ nếu điều đó làm UX khó dùng. Chọn policy theo hậu quả: mở ứng dụng, xem dữ liệu, xuất dữ liệu, thay authenticator hoặc ký giao dịch có thể có yêu cầu khác nhau.

### Biometric không phải secret mà server nhận

Face ID/Touch ID xác minh người dùng cục bộ qua hệ điều hành. Ứng dụng thường nhận kết quả cho phép thao tác hoặc key được sử dụng; không nhận mẫu sinh trắc học thô. Không gửi dữ liệu sinh trắc học đến backend và không tuyên bố server đã nhận diện khuôn mặt/vân tay chỉ vì local biometric prompt thành công.

## 5. Android Keystore là gì?

Android Keystore là hệ thống cho phép ứng dụng tạo, lưu và sử dụng key material thông qua API Android. Key có thể được giữ trong software-backed Keystore hoặc được bảo vệ bởi phần cứng như Trusted Execution Environment (TEE) hay StrongBox nếu thiết bị hỗ trợ.

Điểm quan trọng là ứng dụng thường giữ alias/tham chiếu khóa, còn thao tác mật mã được thực hiện bởi provider. Private key có thể không xuất được khỏi Keystore; ứng dụng yêu cầu ký/giải mã mà không đọc key bytes.

### Alias và key entry

Mỗi key entry có alias trong namespace của ứng dụng. Alias không phải secret; nó là tên tham chiếu. Bảo vệ nằm ở quyền truy cập key, trạng thái và policy.

- Tạo alias riêng theo mục đích, ví dụ khóa ký challenge và khóa mã hóa database.
- Không dùng một key cho nhiều mục đích mật mã khác nhau.
- Có version trong alias hoặc metadata để hỗ trợ rotation.
- Kiểm tra key còn tồn tại và có thể dùng sau update/restore.
- Xử lý trường hợp thiết bị không hỗ trợ hardware-backed key.
- Không lưu private key bytes vào file chỉ vì Keystore không khả dụng.

### TEE và StrongBox

TEE là môi trường thực thi được cô lập bằng phần cứng/firmware trên một số thiết bị. StrongBox là môi trường bảo mật chuyên dụng có yêu cầu bảo vệ cao hơn, nếu thiết bị có hỗ trợ.

Hardware-backed key có thể giảm nguy cơ trích xuất key, nhưng mức bảo đảm phụ thuộc thiết bị, nhà sản xuất, phiên bản Android và triển khai. Ứng dụng cần kiểm tra security level/attestation khi policy yêu cầu, không suy ra StrongBox chỉ từ việc tạo key thành công.

### User authentication requirement

Android Keystore có thể cấu hình key chỉ dùng sau khi người dùng xác thực bằng cơ chế được nền tảng hỗ trợ. Tùy API level và cấu hình, key có thể yêu cầu xác thực cho mỗi thao tác hoặc trong một validity window.

Cần phân biệt:

- Key được bảo vệ bằng phần cứng.
- Key yêu cầu user authentication.
- Prompt biometric hiển thị.
- Key được ràng buộc với biometric enrollment hoặc device credential.

Đây là các thuộc tính khác nhau. Một key có thể hardware-backed nhưng không yêu cầu biometric; một key yêu cầu biometric không nhất thiết nằm trong StrongBox.

## 6. StrongBox và key attestation

StrongBox có thể cung cấp môi trường lưu và sử dụng key độc lập hơn TEE, với các bảo vệ phần cứng bổ sung. Không phải thiết bị Android nào cũng có StrongBox; ứng dụng phải có fallback policy rõ ràng.

### Khi nào yêu cầu StrongBox?

Có thể yêu cầu StrongBox cho private key có giá trị cao nếu:

- Thiết bị hỗ trợ.
- Hiệu năng và thuật toán đáp ứng use case.
- Chính sách sản phẩm yêu cầu mức bảo vệ phần cứng cụ thể.
- Có quy trình fallback hoặc từ chối rõ ràng khi không hỗ trợ.

Không nên bắt mọi thiết bị dùng StrongBox nếu nghiệp vụ không cần và người dùng sẽ bị loại khỏi dịch vụ mà không có phương án thay thế.

### Key attestation

Android key attestation có thể cung cấp bằng chứng về thuộc tính key generation, security level và trạng thái boot/OS theo cấu trúc attestation được nền tảng hỗ trợ. Backend cần xác minh attestation chain, challenge, thời gian, trạng thái chứng thư và các extension liên quan.

Quy trình khái quát:

1. Backend tạo challenge ngẫu nhiên, một lần và gắn với enrollment transaction.
2. App tạo key pair trong Android Keystore, yêu cầu attestation challenge.
3. App gửi certificate chain và public key về backend.
4. Backend xác minh chain tới trust anchor phù hợp, kiểm tra challenge khớp và chưa dùng.
5. Backend đánh giá security level, application identity, verified boot và thuộc tính policy.
6. Backend gắn public key với account/device theo policy.
7. Backend consume challenge và hoàn tất enrollment.

Attestation không chứng minh thiết bị hoàn toàn không bị compromise. Nó là tín hiệu về môi trường và key theo thời điểm tạo; backend vẫn cần authorization, risk assessment, revocation và kiểm tra hành vi.

### Không gửi private key lên server

Server chỉ cần public key và bằng chứng attestation theo protocol. Nếu app gửi private key để “đăng ký thiết bị”, thiết kế đã mất lợi ích chính của Keystore.

## 7. Keychain và Keystore: điểm giống và khác

| Khía cạnh | Apple Keychain / Secure Enclave | Android Keystore / StrongBox |
| --- | --- | --- |
| Mục đích | Lưu credential và quản lý key/access control | Quản lý key và thao tác mật mã |
| Secret/token | Keychain item | Thường mã hóa secret rồi lưu app storage; key bảo vệ nằm trong Keystore |
| Private key | Có thể tạo/sử dụng key trong Secure Enclave khi hỗ trợ | Có thể tạo/sử dụng key hardware-backed trong TEE/StrongBox |
| Non-exportable key | Có với loại key và thiết bị hỗ trợ | Có với key được tạo trong Keystore |
| User authentication | Keychain access control, passcode/biometric policy | Key authorization và user-auth requirement |
| App sharing | Keychain access groups/entitlements | App UID/sandbox; chia sẻ qua cơ chế Android identity/IPC, không chia sẻ alias tùy tiện |
| Backup/sync | Accessibility class, synchronizable và iCloud Keychain semantics | Key material Keystore thường gắn với thiết bị; app data backup cần policy riêng |
| Attestation | Có cơ chế chứng minh key/device theo API và hệ sinh thái Apple phù hợp | Android key attestation với certificate chain |
| Hardware assurance | Secure Enclave trên thiết bị hỗ trợ | TEE/StrongBox tùy thiết bị |
| Khả năng tương thích | Khác theo OS/device/API | Khác theo API level, nhà sản xuất và phần cứng |

Không cố tạo một abstraction giả định hai nền tảng giống nhau hoàn toàn. Có thể xây interface chung như SecureCredentialStore hoặc DeviceKeyProvider, nhưng adapter iOS/Android cần giữ semantics riêng về accessibility, biometric, backup, attestation và key lifecycle.

## 8. Lưu token và credential ứng dụng native

Ứng dụng native cần quyết định token nào được lưu, token nào chỉ ở memory và khi nào phải xóa.

### OAuth/OIDC cho ứng dụng native

Flow phổ biến:

1. Mở system browser hoặc authentication session do nền tảng cung cấp.
2. Dùng Authorization Code Flow với PKCE.
3. Kiểm tra state và OIDC nonce theo transaction.
4. Đổi authorization code tại token endpoint bằng PKCE verifier.
5. Xác minh ID token theo OIDC client library.
6. Lưu refresh token trong Keychain/Keystore-backed storage.
7. Giữ access token trong memory nếu có thể; refresh khi cần.
8. Khi logout, xóa token local và gọi revocation/logout endpoint phù hợp.
9. Khi refresh-token reuse hoặc credential compromise, xử lý theo server-side revocation policy.

Không dùng embedded web view để thu thập mật khẩu nếu platform/system browser flow phù hợp. Không tự triển khai OAuth protocol parsing bằng chuỗi thủ công khi có thư viện chuẩn.

### Access token và refresh token

- Access token thường có thời hạn ngắn và audience cụ thể.
- Refresh token có giá trị cao hơn vì có thể tạo access token mới.
- Refresh token nên được bảo vệ bằng secure storage và rotation/reuse detection phía server.
- Nếu refresh token bị mất, attacker có thể duy trì truy cập cho tới khi token family bị thu hồi.
- Không lưu token trong preferences không mã hóa, SQLite plaintext hoặc log.
- Xóa token khỏi memory/cache khi logout hoặc account switch.

### Cookie và WebView

Nếu ứng dụng dùng web session, cookie nên được quản lý bởi cookie store của nền tảng với Secure, HttpOnly, SameSite và domain/path phù hợp. Không copy session cookie vào custom preferences hoặc JavaScript storage. Local logout cần kết thúc server session; xóa cookie chỉ là bước client-side.

### Browser storage

Đối với web app, tránh lưu bearer token dài hạn trong localStorage hoặc sessionStorage vì JavaScript chạy trong origin có thể đọc được khi XSS xảy ra. Ưu tiên kiến trúc BFF/server-side session hoặc cookie HttpOnly, Secure, SameSite phù hợp. Cookie tự động gửi theo request cần CSRF protection. Không có lựa chọn lưu trữ nào bù được việc XSS và CSRF không được xử lý.

## 9. Lưu secret và data key trên thiết bị

Một số ứng dụng cần mã hóa dữ liệu offline như ghi chú, tài liệu hoặc cơ sở dữ liệu cục bộ. Keychain/Keystore có thể bảo vệ key-encryption key, còn dữ liệu lớn được mã hóa trong file/database.

### Envelope encryption

Một mô hình phổ biến:

1. Sinh Data Encryption Key (DEK) ngẫu nhiên.
2. Mã hóa dữ liệu bằng DEK với AEAD như AES-GCM.
3. Bọc DEK bằng Key Encryption Key (KEK) được giữ trong Keychain/Keystore hoặc KMS.
4. Lưu ciphertext, nonce/IV, authentication tag và metadata version.
5. Khi đọc, lấy KEK/key handle, unwrap DEK và xác minh AEAD tag.
6. Khi rotation KEK, rewrap DEK; khi rotation DEK, mã hóa lại dữ liệu.

Không mã hóa mọi file trực tiếp bằng một key cứng nhúng trong app. Nếu key được hardcode hoặc lưu cùng ciphertext, attacker có thể lấy cả hai từ package.

### Nonce của AEAD

Với AES-GCM, nonce/IV phải tuân thủ yêu cầu uniqueness cho mỗi key. Tái sử dụng nonce với cùng key có thể phá vỡ bảo đảm bảo mật. Nonce này là tham số của thuật toán AEAD; nó không tự ngăn replay một ciphertext hợp lệ. Nếu ứng dụng cần từ chối dữ liệu cũ, cần version/counter hoặc integrity-protected state riêng.

### Không tự xây thuật toán

Dùng API crypto của nền tảng hoặc thư viện được duy trì. Không tự viết AES, RSA, PBKDF2 hoặc thuật toán serialize key. Cấu hình algorithm, key size, mode và padding theo profile hiện hành của nền tảng và threat model.

## 10. Biometric, passcode và policy truy cập

Biometric có thể tạo UX thuận tiện nhưng không phải lúc nào cũng là lựa chọn đúng cho mọi credential.

### Chọn policy theo thao tác

| Thao tác | Policy gợi ý |
| --- | --- |
| Đọc preference không nhạy cảm | App sandbox thông thường |
| Lấy refresh token để duy trì phiên | Secure storage; có thể yêu cầu thiết bị đã mở khóa |
| Ký giao dịch giá trị cao | Non-exportable key, user presence/verification và transaction binding |
| Thêm/xóa authenticator | Reauthentication mạnh, notification và audit |
| Đọc dữ liệu offline nhạy cảm | Mã hóa dữ liệu và key access policy phù hợp |
| Khôi phục sau mất thiết bị | Recovery ceremony riêng; không dựa duy nhất vào biometric |

### Biometric enrollment thay đổi

Một số policy có thể ràng buộc key với tập biometric hiện tại. Khi người dùng thêm hoặc xóa biometric, key/item có thể không còn truy cập được. Ứng dụng cần:

- Thông báo rõ khi enrollment mới làm credential không dùng được.
- Yêu cầu reauthentication hoặc recovery theo policy.
- Không tự động hạ xuống password yếu mà không có quyết định.
- Có authenticator dự phòng hoặc quy trình khôi phục.
- Thu hồi key cũ trên server nếu thiết bị bị mất hoặc nghi compromise.

### Device passcode fallback

Nếu policy cho phép device passcode, người dùng có thể truy cập key bằng passcode khi biometric không khả dụng. Đây là quyết định assurance của ứng dụng. Không mô tả mọi biometric prompt là “chỉ Face ID” nếu hệ điều hành có thể cho phép passcode fallback.

## 11. Backup, restore, synchronization và migration

Backup/sync là nơi dễ làm sai mô hình credential storage. Một item có thể an toàn trong Keychain nhưng không nên được sao chép sang thiết bị khác hoặc cloud backup.

### Apple

- Accessibility class và thuộc tính synchronizable quyết định hành vi truy cập/sync.
- Một số item có thể đồng bộ qua iCloud Keychain theo semantics nền tảng.
- Item có thuộc tính this-device-only được thiết kế để không migrate theo một số đường backup/restore.
- Private key trong Secure Enclave gắn với phần cứng và không được khôi phục như byte key thông thường.
- Khi đổi thiết bị, cần enrollment credential mới hoặc quy trình sync/recovery được hỗ trợ.
- Không coi iCloud sync là bằng chứng rằng mọi app item đều được đồng bộ.

### Android

- Key material trong Android Keystore thường gắn với thiết bị và không được backup như dữ liệu ứng dụng thông thường.
- Khi gỡ ứng dụng Android, key thuộc namespace/UID của ứng dụng thường bị hệ thống xóa; không thiết kế dựa trên giả định alias sẽ còn sau khi cài lại.
- Backup app data có thể sao chép ciphertext nhưng thiết bị mới không có key để giải mã.
- Cấu hình backup/restore phải loại trừ dữ liệu nhạy cảm hoặc thiết kế migration có chủ đích.
- Khi restore, app phải phát hiện key alias không còn tồn tại hoặc không dùng được.
- Người dùng cần reauthenticate/re-enroll thay vì cố khôi phục private key đã mất.
- Không export private key chỉ để làm cho backup hoạt động.

### Quyết định sync

Cần trả lời:

- Dữ liệu có được phép sync giữa các thiết bị không?
- Nếu sync, dữ liệu là ciphertext hay plaintext?
- Khóa giải mã được đồng bộ bằng cơ chế nào?
- Thiết bị mới phải xác minh thế nào để nhận key?
- Người dùng mất mọi thiết bị thì recovery ra sao?
- Thu hồi một thiết bị có làm mất khả năng đọc dữ liệu của thiết bị khác không?

Đồng bộ token hoặc private key không phải mặc định an toàn. Với credential gắn thiết bị, thường nên enroll key riêng cho từng thiết bị và lưu public key ở server.

## 12. Lifecycle: enrollment, rotation, revocation và logout

Secure storage là một phần của lifecycle, không phải thao tác ghi một lần rồi quên.

### Enrollment

- Tạo key trong Keychain/Keystore.
- Lấy public key hoặc credential reference.
- Gửi public key và bằng chứng cần thiết lên server.
- Server gắn key với subject/device và policy.
- Lưu metadata về key ID, algorithm, createdAt, status và attestation nếu có.
- Không gửi private key lên server.

### Rotation

- Tạo key version mới.
- Đăng ký public key mới với server.
- Xác minh thao tác ký bằng key mới.
- Chuyển client sang key mới.
- Thu hồi key cũ khi an toàn.
- Xóa alias/item cũ theo policy.
- Giữ audit metadata.

### Revocation

Khi thiết bị bị mất, app bị gỡ khỏi tổ chức hoặc key bị nghi lộ:

- Server thu hồi device credential/public key.
- Thu hồi refresh-token family và session gắn với thiết bị.
- Đánh dấu thiết bị không còn trusted.
- App xóa local item nếu còn truy cập được.
- Backend từ chối assertion/challenge từ key cũ.
- Thông báo chủ tài khoản và ghi audit.

Xóa item local không thu hồi public key đã đăng ký trên server. Thu hồi server-side là bước bắt buộc để ngăn attacker tiếp tục dùng credential đã sao chép.

### Logout

Logout nên xóa refresh token và dữ liệu phiên khỏi secure storage, đồng thời gọi server-side revocation khi có kết nối. Nếu logout offline, app có thể xóa local credential và ghi nhận trạng thái pending theo thiết kế; không tuyên bố đã thu hồi mọi session nếu server chưa xác nhận.

### Gỡ ứng dụng

Không dựa vào uninstall để bảo đảm credential bị xóa. Keychain item có thể tồn tại sau khi app bị gỡ; Android app data thường bị xóa theo uninstall nhưng backup, shared storage hoặc server credential vẫn tồn tại. Cần thao tác account removal/revocation riêng.

## 13. Threat model và giới hạn bảo vệ

Keychain/Keystore bảo vệ key material ở một ranh giới nhất định. Chúng không biến thiết bị thành môi trường hoàn toàn đáng tin.

| Mối đe dọa | Keychain/Keystore giúp gì? | Kiểm soát bổ sung |
| --- | --- | --- |
| Sao chép app database | Giữ key riêng khỏi file app hoặc mã hóa key | Mã hóa dữ liệu, backup policy |
| App khác đọc dữ liệu | Sandbox và access control | Entitlement, UID isolation |
| Trích xuất private key | Non-exportable/hardware-backed key giảm khả năng | Attestation, server-side risk |
| Malware điều khiển app | Có thể không đọc key nhưng có thể gọi API hợp lệ | Transaction binding, step-up, integrity signals |
| Thiết bị root/jailbreak | Có thể làm suy yếu sandbox và runtime trust | Risk policy, limit action, revoke |
| XSS/WebView injection | Secure storage không ngăn JavaScript điều khiển phiên nếu token được đưa vào JS | HttpOnly cookie/BFF, CSP, input/output security |
| Backup bị lộ | This-device-only và backup exclusion giảm rủi ro | Mã hóa backup, không backup secret |
| Debug/log leakage | Keychain/Keystore không bảo vệ dữ liệu đã log | Redaction, disable sensitive debug |
| Người dùng bị lừa xác thực | Biometric/passcode có thể bị dụ bấm | Hiển thị transaction context, anti-phishing |
| Server compromise | Device key có thể bị server giả yêu cầu dùng nếu protocol yếu | Audience binding, challenge, authorization, key revocation |

### Runtime compromise

Nếu attacker điều khiển process của ứng dụng, họ có thể gọi API đọc Keychain item mà app được phép đọc, yêu cầu Keystore ký dữ liệu hoặc lấy token sau khi app giải mã. Non-exportable key ngăn trích xuất key bytes nhưng không tự ngăn việc sử dụng key như một signing oracle.

Vì vậy, với thao tác có giá trị cao, cần ràng buộc chữ ký với transaction digest, audience, nonce và action. Backend phải xác minh proof rồi kiểm tra quyền; không coi “chữ ký hợp lệ từ thiết bị” là cho phép mọi thao tác.

### Jailbreak/root signals

Không nên dựa vào một dấu hiệu root/jailbreak duy nhất. Detection có thể bị bypass và có false positive. Dùng nhiều tín hiệu và quyết định theo rủi ro: yêu cầu step-up, giới hạn tính năng nhạy cảm, từ chối thao tác đặc biệt hoặc thu hồi session khi có bằng chứng compromise.

## 14. Swift: lưu refresh token trong Keychain

Ví dụ sau minh họa thao tác thêm, đọc và xóa generic password item bằng Security framework. Ứng dụng cần kiểm soát service/account, accessibility và lỗi duplicate/update. Không ghi token ra log.

```swift
import Foundation
import Security

enum KeychainStoreError: Error {
    case unexpectedStatus(OSStatus)
    case invalidData
}

final class RefreshTokenStore {
    private let service = "com.example.auth"
    private let account = "refresh-token"

    func save(_ token: String) throws {
        guard let data = token.data(using: .utf8) else {
            throw KeychainStoreError.invalidData
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]

        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String:
                kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]

        let status = SecItemAdd(
            query.merging(attributes) { _, new in new } as CFDictionary,
            nil
        )

        if status == errSecDuplicateItem {
            let updateStatus = SecItemUpdate(
                query as CFDictionary,
                attributes as CFDictionary
            )
            guard updateStatus == errSecSuccess else {
                throw KeychainStoreError.unexpectedStatus(updateStatus)
            }
        } else if status != errSecSuccess {
            throw KeychainStoreError.unexpectedStatus(status)
        }
    }

    func read() throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw KeychainStoreError.unexpectedStatus(status)
        }
        guard let data = result as? Data,
              let token = String(data: data, encoding: .utf8) else {
            throw KeychainStoreError.invalidData
        }
        return token
    }

    func delete() throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]

        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainStoreError.unexpectedStatus(status)
        }
    }
}
```

Đây là ví dụ tối giản. Production cần xử lý migration/version, account switching, access group, accessibility class, concurrency và lỗi thiết bị bị khóa. Nếu token cần biometric hoặc passcode mỗi lần đọc, dùng access control phù hợp thay vì chỉ đặt accessibility. Với refresh token, server vẫn cần rotation/reuse detection và revocation.

### Lưu private key trong Secure Enclave

Với key dùng ký challenge, có thể tạo key pair qua API Security và chỉ lưu key reference/metadata. Public key được gửi lên server; private key không được export. Cần cấu hình access control theo policy và xác minh challenge do server cấp trước khi ký. Không dùng private key này để mã hóa dữ liệu tùy tiện nếu key được tạo cho mục đích signing.

## 15. Kotlin/Java: tạo key trong Android Keystore

Ví dụ Kotlin sau tạo cặp EC key cho signing trong Android Keystore. Tùy phiên bản Android, thiết bị và provider, thuật toán/curve/StrongBox có thể khác; cần kiểm tra khả năng hỗ trợ và có fallback policy.

```kotlin
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature

class DeviceSigningKey(private val alias: String) {

    fun create() {
        val generator = KeyPairGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_EC,
            "AndroidKeyStore"
        )

        val spec = KeyGenParameterSpec.Builder(
            alias,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
        )
            .setAlgorithmParameterSpec(
                java.security.spec.ECGenParameterSpec("secp256r1")
            )
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(true)
            .build()

        generator.initialize(spec)
        generator.generateKeyPair()
    }

    fun sign(challenge: ByteArray): ByteArray {
        val keyStore = KeyStore.getInstance("AndroidKeyStore")
        keyStore.load(null)

        val privateKey = keyStore.getKey(alias, null) as java.security.PrivateKey
        val signer = Signature.getInstance("SHA256withECDSA")
        signer.initSign(privateKey)
        signer.update(challenge)
        return signer.sign()
    }

    fun publicKeyEncoded(): ByteArray? {
        val keyStore = KeyStore.getInstance("AndroidKeyStore")
        keyStore.load(null)
        return keyStore.getCertificate(alias)?.publicKey?.encoded
    }
}
```

Ví dụ minh họa luồng cơ bản; production phải xử lý user-auth validity, biometric prompt/crypto object, key invalidation, hardware security level, StrongBox fallback, attestation và lỗi key không còn tồn tại. Không gọi sign trên challenge tùy ý từ client; challenge phải có expiry, nonce, audience và transaction binding được backend xác minh.

### Phân biệt tạo key và lưu secret

Android Keystore chủ yếu bảo vệ key material và thao tác mật mã. Nếu cần lưu một refresh token hoặc secret dạng chuỗi, thường tạo một AES key trong Keystore, mã hóa secret bằng AEAD rồi lưu ciphertext trong app-private storage. Khi đọc, dùng key trong Keystore để giải mã. Thiết kế này vẫn phải quản lý nonce uniqueness, authentication tag, backup/restore và key invalidation.

## 16. Kiểm thử và vận hành

Secure storage cần được kiểm thử trên thiết bị thật và nhiều trạng thái vòng đời. Emulator/simulator có thể không mô phỏng đầy đủ phần cứng, biometric hoặc key attestation.

### Bảng kiểm thử

| Trường hợp | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Lưu token | Lưu refresh token mới | Đọc lại đúng token, không ghi log |
| Token bị sửa | Thay ciphertext hoặc tag | Giải mã thất bại |
| Item không tồn tại | Đọc lần đầu hoặc sau delete | Trả trạng thái không có item, không crash |
| Duplicate item | Lưu cùng service/account | Update có kiểm soát, không tạo item cạnh tranh |
| Account switch | Đăng xuất user A, đăng nhập user B | Không trả token của A |
| Thiết bị khóa | Đọc item có accessibility yêu cầu unlocked | API trả lỗi phù hợp; app không fallback yếu |
| Biometric enrollment đổi | Thêm/xóa biometric | Key theo policy bị invalidated hoặc yêu cầu recovery |
| Biometric bị khóa | Nhiều lần xác thực thất bại | Xử lý theo OS policy, không lộ token |
| App reinstall | Cài lại ứng dụng | Xử lý item còn sót theo policy, xác minh account |
| Backup/restore iOS | Restore sang thiết bị khác | This-device-only item không được giả định migrate |
| Backup/restore Android | Restore ciphertext không có Keystore key | App phát hiện key thiếu và yêu cầu recovery |
| StrongBox không hỗ trợ | Tạo key trên thiết bị không có StrongBox | Fallback hoặc từ chối theo policy |
| Key attestation sai | Chain/challenge/identity không hợp lệ | Backend từ chối enrollment |
| Key bị xóa | Xóa alias/item | App yêu cầu enroll lại, backend xử lý key status |
| Thiết bị mất | Admin/user revoke device | Backend từ chối assertion và refresh token |
| Logout | Xóa token local và revoke server-side | Session/token family bị xử lý đúng scope |
| Root/jailbreak | Chạy trong môi trường rủi ro | Risk policy được áp dụng, không dựa một tín hiệu đơn |
| Debug build | Kiểm tra log/crash report | Không có token, key hoặc secret |
| Memory/runtime compromise | Điều khiển app process | Backend vẫn yêu cầu proof/context và authorization |
| Concurrent access | Nhiều luồng đọc/ghi token | Không trả token cũ sau account switch |
| Key rotation | Enroll key mới và revoke key cũ | Key mới hoạt động; key cũ bị từ chối |
| App data backup | Kiểm tra file backup | Không có plaintext secret hoặc private key |
| Access group | App không thuộc entitlement cố đọc item | Keychain từ chối truy cập |
| WebView/XSS | Script cố đọc token | Token không nằm trong JavaScript storage |
| Refresh token reuse | Dùng lại token đã rotate | Server phát hiện và áp dụng family revocation policy |

### Observability

Có thể ghi nhận metadata như:

- Credential reference hoặc key ID không nhạy cảm.
- Loại thao tác: create, read, sign, refresh, revoke hoặc delete.
- Kết quả và reason code.
- App version, OS version và security level nếu policy cho phép.
- Thời điểm, device reference và correlation ID.

Không ghi token, password, private key, TOTP seed, recovery code, plaintext secret, biometric data hoặc toàn bộ assertion vào log. Hạn chế thu thập device fingerprint và dữ liệu môi trường quá mức cần thiết.

## 17. Lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Lưu refresh token trong preferences plaintext | Token bị lộ khi app data bị sao chép | Keychain/Keystore-backed storage |
| Hardcode API secret trong binary | Attacker trích xuất secret từ app | Không đặt confidential secret trong public client |
| Lưu private key dạng file | Key có thể bị sao chép | Tạo non-exportable key trong platform store |
| Nghĩ Keystore tự lưu mọi chuỗi secret | Lưu sai API hoặc để token plaintext | Mã hóa secret bằng key trong Keystore |
| Dùng một key cho mọi mục đích | Key compromise ảnh hưởng nhiều chức năng | Key riêng theo purpose và usage |
| Bỏ qua accessibility/access control | Credential truy cập trong trạng thái không phù hợp | Chọn policy theo threat model |
| Mặc định biometric luôn có mặt | Người dùng bị khóa khi biometric thay đổi | Fallback/recovery có assurance phù hợp |
| Tin hardware-backed key tuyệt đối | Runtime malware vẫn có thể gọi key | Transaction binding, attestation và backend checks |
| Gửi private key lên server | Mất lợi ích non-exportable | Chỉ gửi public key và attestation |
| Tin attestation không xác minh chain | Chấp nhận key giả hoặc challenge cũ | Verify chain, challenge và policy server-side |
| Coi uninstall là xóa Keychain | Item có thể còn tồn tại | Xóa/revoke credential theo lifecycle |
| Backup ciphertext nhưng không quản lý key | Restore không thể giải mã | Backup policy và recovery/migration |
| Sync credential thiết bị không giới hạn | Mất một account cloud ảnh hưởng nhiều thiết bị | Phân biệt sync và device-bound key |
| Dùng localStorage cho bearer token | XSS có thể đọc token | BFF/HttpOnly cookie hoặc secure storage phù hợp |
| Không xóa token khi đổi account | User B có thể dùng session của user A | Account-scoped keychain item và logout |
| Không revoke server khi xóa local item | Attacker vẫn dùng bản sao token/key đã đăng ký | Server-side revocation |
| Log lỗi kèm secret | Credential lộ trong telemetry | Redaction và metadata tối thiểu |
| Không xử lý key invalidation | App crash hoặc fallback yếu | State machine và re-enrollment |
| Dùng một API abstraction làm mất semantics nền tảng | Sai khác backup/biometric/accessibility bị bỏ qua | Adapter riêng cho từng OS |
| Không kiểm tra thiết bị thật | Bỏ sót khác biệt phần cứng/provider | Ma trận test thiết bị/OS |

## 18. Checklist thiết kế Keychain và Keystore

Trước khi phát hành, hãy trả lời:

1. **Data inventory:** Dữ liệu nào là secret, token, private key, public key hay dữ liệu thông thường?
2. **Purpose:** Mỗi key dùng cho signing, encryption, wrapping hay authentication?
3. **Storage:** Secret lưu trực tiếp trong Keychain hay mã hóa bằng key trong Keystore?
4. **Non-exportability:** Có cần private key không xuất được không? Thiết bị hỗ trợ mức nào?
5. **Hardware:** Secure Enclave, TEE hoặc StrongBox có được yêu cầu hay chỉ là tín hiệu bổ sung?
6. **Access control:** Khi nào key/item được truy cập? Có cần passcode, biometric hoặc user presence không?
7. **Fallback:** Khi biometric thay đổi, thiết bị không hỗ trợ hoặc key invalidated, recovery ra sao?
8. **Token lifecycle:** Refresh token được rotate/revoke thế nào? Access token giữ trong memory bao lâu?
9. **Backup/sync:** Dữ liệu nào được backup/sync? Key nào device-bound? Restore xử lý ra sao?
10. **App boundary:** Access group, UID, entitlement và IPC có được giới hạn đúng không?
11. **Runtime:** App process bị chiếm quyền thì attacker có thể đọc hoặc gọi key thế nào?
12. **Server binding:** Public key gắn với subject/device ra sao? Challenge có nonce, audience và expiry không?
13. **Revocation:** Thiết bị mất hoặc credential compromise thì backend thu hồi gì?
14. **Logout/account switch:** Local item, cookie, cache và server session được xử lý thế nào?
15. **Logging:** Có loại bỏ token, seed, private key và dữ liệu nhạy cảm khỏi telemetry không?
16. **Testing:** Có test thiết bị khóa, biometric change, backup/restore, key invalidation, root/jailbreak và app reinstall không?

## 19. Bài tập vận dụng

Một ứng dụng tài chính trên iOS và Android lưu access token và refresh token trong file preferences. Ứng dụng tạo một RSA private key dạng file để ký yêu cầu chuyển tiền. Khi người dùng bật Face ID hoặc vân tay, app chỉ kiểm tra kết quả prompt ở giao diện rồi vẫn đọc private key từ file. Khi logout, app xóa preferences nhưng không gọi server revocation. Backup tự động sao chép toàn bộ thư mục dữ liệu app. Backend chỉ kiểm tra chữ ký mà không ràng buộc challenge với nội dung giao dịch.

**Yêu cầu:**

1. Liệt kê rủi ro của cách lưu token và private key hiện tại.
2. Thiết kế lưu refresh token bằng Keychain trên iOS và Keystore-backed encryption trên Android.
3. Đề xuất tạo private key non-exportable trong Secure Enclave/Android Keystore; nêu điều kiện dùng StrongBox và fallback.
4. Thiết kế access control yêu cầu biometric hoặc device credential tại thời điểm ký.
5. Mô tả enrollment public key, key attestation và cách backend kiểm tra challenge.
6. Ràng buộc chữ ký với nonce, audience, action, người nhận và số tiền của giao dịch.
7. Thiết kế backup/restore và account recovery khi người dùng đổi hoặc mất thiết bị.
8. Thiết kế logout và revoke session/refresh-token family/key trên server.
9. Viết test cho backup restore, biometric enrollment change, app reinstall, root/jailbreak, key invalidation và replay transaction.

**Gợi ý tự đánh giá:** Prompt biometric ở giao diện không bảo vệ private key nếu app vẫn đọc key từ file. Private key cần được tạo và sử dụng trong platform keystore; server chỉ nhận public key. Token phải được lưu bằng cơ chế secure storage, nhưng logout vẫn cần revocation server-side. Chữ ký phải gắn với transaction digest và challenge một lần để không thể dùng lại cho giao dịch khác.

---

**Điểm cần nhớ:** Keychain và Keystore cung cấp ranh giới lưu trữ và sử dụng credential do hệ điều hành quản lý. Thiết kế an toàn cần **phân loại dữ liệu, giữ private key không xuất được khi phù hợp, áp dụng access control theo rủi ro, quản lý backup/sync và vòng đời, đồng thời thu hồi credential phía server**. Hardware-backed key giảm khả năng trích xuất nhưng không ngăn process bị chiếm quyền gọi key; backend vẫn phải xác minh challenge, transaction binding và authorization.
