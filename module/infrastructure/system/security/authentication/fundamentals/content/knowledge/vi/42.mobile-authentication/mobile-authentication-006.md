# Biometric unlock

## 1. Biometric unlock là gì?

**Biometric unlock** là cơ chế dùng đặc điểm sinh học của chủ thiết bị, chẳng hạn dấu vân tay hoặc khuôn mặt, để cho phép mở khóa thiết bị, mở khóa ứng dụng hoặc sử dụng một credential được bảo vệ. Trên điện thoại hiện đại, ứng dụng thường gọi API sinh trắc học do hệ điều hành cung cấp. Hệ điều hành làm việc với cảm biến, vùng thực thi bảo mật và cơ chế xác minh của nền tảng.

Biometric unlock thường là một thao tác **xác minh cục bộ**. Dấu vân tay hoặc dữ liệu khuôn mặt được xử lý trong thiết bị; ứng dụng không cần và không nên thu thập template sinh trắc học. Server của ứng dụng thường không nhận dữ liệu sinh trắc học. Thay vào đó, kết quả xác minh cục bộ có thể mở khóa session cục bộ hoặc cho phép dùng một khóa mật mã được bảo vệ bởi hệ điều hành.

Điểm quan trọng là không đồng nhất việc mở khóa ứng dụng với việc xác thực danh tính từ xa. Nếu ứng dụng chỉ hiển thị màn hình sau khi Face ID/vân tay thành công, server chưa nhận được bằng chứng mật mã mới rằng người dùng vừa xác minh. Nếu ứng dụng dùng khóa riêng gắn với thiết bị và yêu cầu xác minh sinh trắc học trước khi ký challenge của server, server có thể xác minh chữ ký đó mà không cần nhận dữ liệu sinh trắc học.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, biometric unlock kết nối authentication factor, device security, passkey, credential lifecycle, session và trust boundary. Thiết kế an toàn phải xác định chính xác sinh trắc học đang mở khóa điều gì, khóa nào được phép sử dụng, fallback nào được chấp nhận và điều gì xảy ra khi người dùng thêm/xóa biometric hoặc thay đổi thiết bị.

Sau bài học, người học có thể:

- Phân biệt local biometric verification với remote authentication.
- Giải thích vai trò của OS biometric framework, TEE và Secure Enclave.
- Dùng Android BiometricPrompt/Keystore và iOS LocalAuthentication/Keychain theo đúng mục đích.
- Bảo vệ cryptographic key bằng user authentication requirement.
- Phân biệt biometric unlock, device passcode và passkey user verification.
- Thiết kế fallback, lockout, enrollment change và recovery.
- Đánh giá privacy, spoofing, rooted/jailbroken device và app lifecycle.
- Kiểm thử cancel, fallback, biometric enrollment change, key invalidation và remote challenge.

## 2. Hai mô hình khác nhau: mở khóa cục bộ và xác thực từ xa

Cùng một giao diện yêu cầu Face ID hoặc vân tay có thể phục vụ hai mục đích bảo mật khác nhau.

### 2.1. Local app unlock

Ứng dụng yêu cầu hệ điều hành xác minh biometric. Nếu thành công, app mở một vùng dữ liệu cục bộ hoặc tiếp tục hiển thị session đã được bảo vệ.

Ví dụ:
- Mở ứng dụng ngân hàng sau khi người dùng đã đăng nhập trước đó.
- Mở màn hình chứa dữ liệu được mã hóa bằng khóa lưu trong Keychain/Keystore.
- Mở khóa một refresh token cục bộ hoặc secret dùng trong phiên hiện tại.
- Xác nhận người dùng hiện đang cầm thiết bị trước khi xem nội dung riêng tư.

Trong mô hình này, server có thể không nhận request mới. Biometric result chỉ là tín hiệu cục bộ cho app. Nếu app tự đặt biến isAuthenticated=true sau khi callback thành công rồi cho phép gọi mọi API bằng token cũ, cần đánh giá thời hạn token, session và khả năng app state bị can thiệp.

### 2.2. Remote authentication bằng proof-of-possession

Nếu cần server xác minh rằng một thiết bị đã thực hiện user verification, ứng dụng có thể sử dụng private key được tạo và bảo vệ trong phần cứng hoặc keystore. Private key được cấu hình yêu cầu user authentication trước khi sử dụng.

Flow khái quát:
1. Server tạo challenge ngẫu nhiên và gắn với account, session, action hoặc transaction.
2. App yêu cầu biometric verification qua OS.
3. Khi xác minh thành công, OS cho phép thao tác ký bằng private key đã được bảo vệ.
4. App ký challenge hoặc dữ liệu transaction bằng private key.
5. Server xác minh chữ ký bằng public key đã đăng ký, kiểm tra challenge chưa dùng, expiry, audience và transaction binding.
6. Server đưa ra quyết định authentication/authorization theo policy.

Server không cần biết người dùng dùng ngón tay nào hoặc khuôn mặt ra sao. Nó xác minh rằng thiết bị giữ private key đã tạo chữ ký hợp lệ; việc user verification được bảo vệ bởi nền tảng và thuộc tính key/attestation theo mô hình tin cậy đã chọn.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Mobile App
    participant OS as Biometric Framework / Secure Hardware
    participant S as Server
    U->>A: Yêu cầu thao tác nhạy cảm
    A->>S: Xin challenge
    S-->>A: Nonce + transaction context
    A->>OS: Yêu cầu biometric và dùng private key
    OS->>U: Xác minh sinh trắc học
    U->>OS: Hoàn tất xác minh
    OS-->>A: Cho phép ký bằng key được bảo vệ
    A->>S: Chữ ký + key reference + challenge
    S->>S: Verify signature, freshness, binding và policy
    S-->>A: Kết quả quyết định
~~~

### 2.3. Bảng so sánh

| Đặc điểm | Local app unlock | Remote proof-of-possession |
| --- | --- | --- |
| Mục tiêu | Mở khóa UI hoặc dữ liệu trên thiết bị | Chứng minh quyền kiểm soát key cho server |
| Biometric data | Xử lý cục bộ bởi OS | Vẫn xử lý cục bộ bởi OS |
| Bằng chứng gửi server | Có thể không có | Chữ ký trên challenge hoặc transaction |
| Key | Có thể chỉ là key mã hóa local | Private key gắn với thiết bị và policy user verification |
| Replay protection | Session/app state policy | Challenge one-time, expiry, transaction binding |
| Assurance | Phụ thuộc cách app bảo vệ local state | Phụ thuộc key protection, enrollment và server validation |

Không tuyên bố remote authentication chỉ vì app đã hiện hộp thoại sinh trắc học. Phải xác định server nhận được bằng chứng gì và bằng cách nào chứng minh bằng chứng đó gắn với principal.

## 3. Biometric factor và giới hạn của sinh trắc học

Sinh trắc học là đặc điểm vật lý hoặc hành vi có thể dùng để nhận diện/xác minh người. Trên điện thoại, phương thức thường gặp:
- Vân tay.
- Nhận diện khuôn mặt.
- Một số nền tảng có thể hỗ trợ đặc điểm sinh học khác.

Sinh trắc học có tính tiện dụng cao vì người dùng không cần nhớ secret. Tuy nhiên, nó khác password:
- Người dùng không dễ thay đổi dấu vân tay hoặc khuôn mặt khi dữ liệu bị lộ.
- Sensor và thuật toán có xác suất false accept/false reject.
- Chất lượng xác minh phụ thuộc thiết bị, điều kiện cảm biến và policy nền tảng.
- Biometric matching không tự chứng minh ý định cho từng giao dịch.
- Không phải mọi phương thức sinh trắc học trên mọi thiết bị có cùng assurance.

### 3.1. False Accept và False Reject

- **False Accept Rate (FAR):** xác suất hệ thống chấp nhận nhầm người không được phép.
- **False Reject Rate (FRR):** xác suất hệ thống từ chối nhầm người hợp lệ.

Hai chỉ số chịu ảnh hưởng của cảm biến, thuật toán, môi trường và cấu hình. Nhà phát triển ứng dụng thường không tự đặt ngưỡng matching của hệ điều hành; họ chọn policy/API phù hợp và dựa trên assurance mà nền tảng công bố.

Không so sánh trực tiếp các con số marketing giữa nhà sản xuất nếu điều kiện đo và định nghĩa khác nhau. Với ứng dụng nhạy cảm, cần dùng platform authenticator có security class phù hợp và yêu cầu key protection theo policy.

### 3.2. Liveness và presentation attack

Attacker có thể thử đánh lừa cảm biến bằng ảnh, video, mặt nạ, bản sao vân tay hoặc vật thể giả. Cảm biến và hệ điều hành có thể dùng liveness detection, depth sensing hoặc các biện pháp chống presentation attack.

Ứng dụng không nên tự thay thế cơ chế này bằng camera thường hoặc tự viết thuật toán nhận diện. Hãy dùng API hệ điều hành và đánh giá loại biometric/platform được chấp nhận cho mục đích. Không suy ra mức chống giả mạo giống nhau từ việc hai thiết bị đều có nút biometric.

### 3.3. Biometric không phải secret có thể rotate

Nếu password bị lộ, người dùng có thể đổi password. Nếu template sinh trắc học bị lộ, người dùng không thể dễ dàng thay dấu vân tay hoặc khuôn mặt. Do đó:
- Không thu thập hoặc lưu template trong backend.
- Không gửi ảnh vân tay/khuôn mặt tới server.
- Không ghi dữ liệu sinh trắc học vào log hoặc analytics.
- Để OS quản lý template và matching.
- Dùng cryptographic key có thể revoke/rotate làm bằng chứng từ xa.
- Cung cấp phương thức fallback/recovery khác khi biometric không dùng được.

## 4. Biometric matching nằm ở đâu?

Trên thiết bị hiện đại, template và logic matching thường được quản lý bởi hệ điều hành và phần cứng bảo mật. Ứng dụng yêu cầu một policy; nền tảng trả kết quả thành công, thất bại, hủy hoặc yêu cầu fallback.

Các thành phần có thể gồm:
- Sensor: thu thập tín hiệu vân tay/khuôn mặt.
- OS biometric service: điều phối enrollment và authentication.
- Trusted Execution Environment (TEE) hoặc Secure Enclave: xử lý hoặc bảo vệ dữ liệu/key theo nền tảng.
- Keystore/Keychain: quản lý key và access control.
- Application: yêu cầu xác minh và phản ứng với kết quả.
- Backend: xác minh chữ ký/token nếu flow cần remote proof.

Không phải mọi thiết bị đều có cùng kiến trúc phần cứng. App cần dựa trên capability và security level mà API công bố, không tự giả định mọi biometric đều được xử lý trong cùng loại secure hardware.

### 4.1. Template không được đưa vào app

Ứng dụng không nên đọc raw fingerprint image, face template hoặc dữ liệu matching nội bộ. API hệ điều hành chỉ cung cấp kết quả xác minh và/hoặc cho phép thao tác với key đã được bảo vệ.

Nếu một SDK yêu cầu upload ảnh khuôn mặt/vân tay để tự match, đó là một mô hình khác với platform biometric unlock và tạo ra rủi ro privacy, data protection và compliance lớn. Cần có cơ sở pháp lý, consent, security review và threat model riêng; không coi đó là cách triển khai mặc định.

### 4.2. User verification và user presence

User presence cho biết có thao tác hiện diện/xác nhận trên authenticator. User verification thể hiện authenticator đã xác minh người dùng theo cơ chế được hỗ trợ, ví dụ biometric hoặc PIN.

Hai khái niệm không đồng nghĩa. Với WebAuthn/passkey, server có thể kiểm tra cờ User Verified trong authenticator data nếu policy yêu cầu. Với app local unlock, callback thành công của OS chỉ có ý nghĩa trong phạm vi API/policy được gọi.

## 5. Android: BiometricPrompt

Android cung cấp **BiometricPrompt** để ứng dụng yêu cầu hệ điều hành thực hiện biometric authentication. App không tự đọc template hoặc triển khai matching. Framework điều phối giao diện và kết quả từ các authenticator mà thiết bị hỗ trợ.

Các lựa chọn thường gặp:
- **BIOMETRIC_STRONG:** biometric đạt class mạnh theo phân loại Android.
- **BIOMETRIC_WEAK:** biometric đạt class yếu hơn; phù hợp một số use case thuận tiện nhưng không tương đương strong.
- **DEVICE_CREDENTIAL:** PIN, pattern hoặc password của thiết bị, tùy policy và API version.

Với thao tác mật mã nhạy cảm, dùng crypto-based authentication và yêu cầu authenticator phù hợp, thường là BIOMETRIC_STRONG khi key policy cần biometric mạnh. Không dùng BIOMETRIC_WEAK rồi giả định có cùng khả năng bảo vệ private key.

### 5.1. BiometricPrompt cho local unlock

App tạo BiometricPrompt, cung cấp prompt text rõ ràng và nhận callback:
- Authentication succeeded.
- Authentication failed.
- Authentication error hoặc lockout.
- User canceled hoặc system canceled.

Callback success không nên được dùng như một quyền tổng quát không giới hạn. Gắn kết quả với hành động cụ thể, thời gian ngắn và trạng thái app hiện tại. Khi app chuyển background hoặc session thay đổi, xử lý lại theo lifecycle policy.

### 5.2. CryptoObject và Android Keystore

Với remote proof hoặc mở khóa key mã hóa, app có thể tạo key trong Android Keystore và yêu cầu xác thực người dùng trước khi sử dụng. BiometricPrompt có thể gắn với CryptoObject chứa một thao tác mật mã như Cipher, Signature hoặc Mac.

Flow khái quát:
1. Tạo key trong Android Keystore với yêu cầu user authentication.
2. Cấu hình authenticator type và thời gian hiệu lực xác thực theo mục đích.
3. Khi cần ký challenge, khởi tạo Signature bằng private key.
4. Đưa Signature vào CryptoObject cho BiometricPrompt.
5. Sau khi xác minh thành công, hoàn tất thao tác ký.
6. Gửi signature lên server để xác minh public key và challenge.

~~~text
keyGen = AndroidKeyStoreKeyGenerator()
keyGen.setUserAuthenticationRequired(true)
keyGen.setAllowedAuthenticators(BIOMETRIC_STRONG)
privateKey = keyGen.generateKeyPair()

signature = Signature.getInstance("SHA256withECDSA")
signature.initSign(privateKey)

cryptoObject = BiometricPrompt.CryptoObject(signature)
prompt.authenticate(promptInfo, cryptoObject)

// In onAuthenticationSucceeded:
// obtain the authenticated Signature from CryptoObject
// sign the server challenge and submit the signature
~~~

Đây là pseudocode minh họa, không phải mã Kotlin hoàn chỉnh. Cần tuân thủ API level, AndroidX/Platform API và các quy tắc cấu hình key của phiên bản Android mục tiêu.

### 5.3. Device credential fallback trên Android

Nếu policy cho phép, BiometricPrompt có thể hỗ trợ device credential như PIN/pattern/password. Cần hiểu fallback này làm thay đổi assurance: thành công có thể đến từ device credential chứ không phải biometric.

Nếu business policy yêu cầu biometric specifically, không bật fallback device credential rồi báo server rằng user đã xác minh biometric. Nếu mục tiêu là user verification nói chung, có thể chấp nhận device credential nhưng phải ghi đúng authentication context.

### 5.4. Biometric enrollment thay đổi và key invalidation

Android Keystore có các tùy chọn để key bị vô hiệu khi biometric enrollment thay đổi, tùy cách key được tạo và cấu hình. Ví dụ, setInvalidatedByBiometricEnrollment(true) có thể làm key yêu cầu biometric bị invalidated khi enrollment biometric thay đổi theo semantics của API.

Điều này hữu ích khi ứng dụng muốn bảo đảm chỉ tập biometric đã có tại thời điểm key được tạo mới có thể mở khóa key. Nếu người dùng thêm vân tay mới hoặc enrollment thay đổi, app có thể yêu cầu đăng ký lại credential/key theo quy trình xác minh.

Không bật invalidation mà không có recovery plan. Key bị invalidated có thể khiến dữ liệu được mã hóa bằng key đó không còn giải mã được. Cần phân biệt key bảo vệ dữ liệu có thể phục hồi với key dùng ký challenge có thể đăng ký lại.

### 5.5. StrongBox và hardware-backed key

StrongBox Keymaster/KeyMint là môi trường bảo mật phần cứng riêng trên một số thiết bị. Keystore có thể báo key được hardware-backed hay không và có thể cung cấp security level. App cần kiểm tra capability theo API và policy; không mặc định thiết bị Android nào cũng có StrongBox.

Nếu threat model yêu cầu hardware-backed key, có thể từ chối thiết bị không đáp ứng hoặc dùng assurance thấp hơn có kiểm soát. Không chỉ kiểm tra model name hoặc Android version để suy ra hardware protection.

## 6. iOS: LocalAuthentication

iOS cung cấp **LocalAuthentication** để app yêu cầu hệ điều hành xác minh người dùng bằng Face ID hoặc Touch ID, tùy thiết bị. App dùng LAContext để đánh giá policy và nhận kết quả. App không đọc biometric template.

Các policy thường gặp:
- **deviceOwnerAuthenticationWithBiometrics:** yêu cầu biometric.
- **deviceOwnerAuthentication:** cho phép cơ chế xác minh chủ thiết bị, có thể bao gồm passcode fallback theo nền tảng.

Chọn policy dựa trên mục tiêu. Nếu yêu cầu chính xác biometric, không thay bằng policy cho phép passcode rồi ghi nhận kết quả như biometric. Nếu chấp nhận user presence/owner authentication, mô tả policy và audit đúng.

### 6.1. LocalAuthentication cho local unlock

App tạo LAContext, kiểm tra khả năng evaluate policy rồi gọi evaluate. Kết quả có thể thành công, thất bại, user cancel, system cancel, biometric lockout hoặc không khả dụng.

Cần:
- Xử lý mọi error code rõ ràng.
- Không coi cancel là authentication failure của password.
- Không mở khóa app nếu session đã hết hạn hoặc account đã bị revoke.
- Không giữ state success vô thời hạn.
- Hủy context và dọn dữ liệu tạm phù hợp.
- Hiển thị fallback an toàn khi Face ID/Touch ID không khả dụng.

### 6.2. Keychain và access control

Keychain có thể lưu key hoặc secret với access control yêu cầu user presence hoặc biometric. Một số access control flag thường dùng:
- **biometryAny:** cho phép biometric được enrollment trên thiết bị theo semantics nền tảng.
- **biometryCurrentSet:** ràng buộc với tập biometric hiện tại; enrollment thay đổi có thể làm item không còn truy cập được.
- **userPresence:** yêu cầu user presence theo cơ chế được hệ điều hành hỗ trợ, có thể bao gồm passcode/biometric tùy policy.

Dùng Keychain access control để bảo vệ secret/key; không chỉ gọi LocalAuthentication rồi lưu một cờ boolean trong UserDefaults. Boolean đó có thể bị thay đổi nếu app state bị can thiệp.

### 6.3. Secure Enclave

Secure Enclave là một subsystem bảo mật phần cứng trên các thiết bị Apple được hỗ trợ. Có thể tạo private key trong Secure Enclave và sử dụng Keychain access control để yêu cầu user authentication trước khi thao tác.

Khi dùng cho remote proof:
1. Tạo private key trong Secure Enclave theo cấu hình phù hợp.
2. Đăng ký public key với server.
3. Server tạo challenge ngẫu nhiên gắn với account và action.
4. App yêu cầu thao tác ký với LAContext/Keychain access control.
5. OS yêu cầu Face ID/Touch ID hoặc fallback theo policy.
6. Key thực hiện ký challenge.
7. Server xác minh chữ ký và trạng thái challenge.

Không gửi private key ra khỏi Secure Enclave. Việc có Secure Enclave không tự chứng minh mọi request đều được user verification; cần cấu hình access control và kiểm tra flow thực tế.

### 6.4. BiometryCurrentSet và thay đổi enrollment

Access control ràng buộc với biometric set hiện tại có thể làm Keychain item không còn truy cập được khi người dùng thêm hoặc xóa biometric. Đây là một lựa chọn để phát hiện thay đổi enrollment và buộc app đăng ký lại key.

Cần thông báo rõ cho người dùng rằng thay đổi Face ID/Touch ID có thể yêu cầu xác minh lại hoặc đăng ký lại thiết bị. Không tự động hạ xuống một phương thức yếu hơn mà không có policy.

## 7. Biometric unlock và passkey

Passkey dùng cặp khóa công khai/bí mật theo WebAuthn/FIDO. Biometric có thể là một phương thức user verification cục bộ để cho phép authenticator sử dụng private key. Server nhận assertion đã ký và xác minh challenge, origin, RP ID, credential và flags theo protocol.

Phân biệt:
- Biometric unlock app: mở khóa giao diện/dữ liệu local.
- Biometric-gated key: cho phép key thực hiện thao tác sau local verification.
- Passkey: credential WebAuthn/FIDO được dùng để xác thực với relying party.
- Biometric data: template được OS quản lý; không phải dữ liệu server cần nhận.

Một passkey có thể yêu cầu biometric, PIN hoặc phương thức user verification khác tùy authenticator. Vì vậy, server cần kiểm tra user verification flag và policy; không giả định mọi passkey assertion đều được xác minh bằng dấu vân tay hoặc khuôn mặt.

### 7.1. Synced passkeys và device-bound keys

Passkey có thể được đồng bộ trong hệ sinh thái credential provider hoặc gắn với thiết bị/security key. Mô hình synced tăng khả năng khôi phục và dùng trên nhiều thiết bị; device-bound key có thể phù hợp yêu cầu thiết bị quản lý hoặc key không xuất được.

Không giả định mọi passkey là hardware-bound hoặc mọi passkey đều yêu cầu biometric. Relying party cần dựa vào protocol flags, attestation policy nếu dùng và assurance profile đã xác định.

### 7.2. Không tự xây protocol passkey

Dùng WebAuthn/FIDO library và platform credential API được duy trì. Không gửi kết quả boolean biometric từ app lên server rồi gọi đó là passkey. Remote authentication cần cryptographic assertion gắn challenge và RP/origin theo chuẩn.

## 8. Fallback: device passcode, PIN và recovery

Biometric có thể không hoạt động vì tay ướt, cảm biến lỗi, khuôn mặt thay đổi, ánh sáng, lockout hoặc người dùng tắt biometric. Ứng dụng cần fallback rõ ràng.

Các lựa chọn:
- Device passcode/PIN qua OS authentication policy.
- Password của tài khoản nếu policy cho phép.
- Passkey hoặc security key khác.
- Recovery flow có identity proofing phù hợp.
- Support-assisted recovery có kiểm soát và audit.

Fallback thường là điểm yếu nếu dễ bị lạm dụng. Không thiết kế biometric mạnh nhưng cho phép bypass bằng một PIN ứng dụng cố định, mã email yếu hoặc support override không xác minh.

### 8.1. Phân biệt device credential và account credential

Device passcode bảo vệ thiết bị và có thể được OS dùng để mở khóa key. Account password xác thực với dịch vụ. Hai credential thuộc trust domain khác nhau.

Nếu app chấp nhận device credential, server không nên tự hiểu đó là account password hoặc một MFA factor độc lập đã được server xác minh. Cần mô tả rõ local policy và remote proof.

### 8.2. Recovery khi biometric bị thay đổi

Nếu key bị invalidated sau enrollment change:
1. App phát hiện key không còn sử dụng được.
2. App yêu cầu user xác minh qua recovery policy đã định nghĩa.
3. Server đánh giá session, risk và proofing cần thiết.
4. App tạo key mới và đăng ký public key mới.
5. Server revoke key cũ và ghi audit.
6. App thông báo thay đổi tới kênh đã xác minh.

Không cho phép chỉ cần mở app bằng một session cũ rồi đăng ký key mới và xóa key cũ nếu threat model yêu cầu xác minh độc lập.

## 9. Lockout, rate limiting và session lifecycle

OS thường quản lý số lần thử biometric và có thể yêu cầu device passcode sau nhiều lần thất bại. Ứng dụng cần xử lý trạng thái lockout theo API thay vì tự triển khai camera/fingerprint matching.

Nguyên tắc:
- Tôn trọng lockout do OS trả về.
- Không tạo vòng lặp prompt liên tục.
- Có cooldown hoặc giới hạn app-level cho thao tác nhạy cảm.
- Không ghi biometric failure thành password failure.
- Phân biệt user cancel, sensor unavailable, not enrolled và lockout.
- Không tự reset OS lockout bằng cách đổi screen hoặc tạo context mới.
- Không mở session vô hạn sau một lần biometric thành công.

### 9.1. Session timeout

Biometric unlock không nên biến session server thành session không hết hạn. App có thể giữ refresh token hoặc local session handle được bảo vệ; server vẫn áp dụng access token expiry, refresh policy, idle timeout, absolute timeout và revocation.

Khi user unlock local app, kiểm tra:
- Account/session còn active.
- Token chưa hết hạn hoặc có thể refresh theo policy.
- Device/key chưa bị revoke.
- App không ở trạng thái compromised hoặc recovery pending.
- Hành động hiện tại có yêu cầu step-up từ server hay không.

### 9.2. App lifecycle

Khi app chuyển background, bị suspend, process bị kill hoặc thiết bị khóa, cần quyết định có khóa lại màn hình/dữ liệu không. Không dựa vào một biến in-memory tồn tại mãi. Khi quay lại foreground sau thời gian idle hoặc khi app state thay đổi, yêu cầu xác minh lại theo policy.

Không chụp màn hình hoặc log dữ liệu nhạy cảm trong quá trình biometric prompt. Dùng cơ chế bảo vệ nội dung preview theo nền tảng khi phù hợp.

## 10. Privacy và dữ liệu sinh trắc học

Biometric data là dữ liệu nhạy cảm. Ứng dụng nên tuân theo nguyên tắc data minimization:
- Để OS quản lý enrollment và matching.
- Không upload raw fingerprint, face image hoặc template.
- Không lưu template trong database ứng dụng.
- Không đưa biometric result chi tiết vào analytics.
- Không log ảnh, sensor output hoặc credential.
- Chỉ lưu trạng thái/capability tối thiểu cần cho UX.
- Cung cấp privacy notice rõ ràng về mục đích dùng biometric.
- Cho phép người dùng tắt biometric unlock và dùng phương thức khác.

Server có thể lưu public key, credential ID, device registration, key status và thông tin audit phù hợp. Những dữ liệu này không phải biometric template nhưng vẫn cần bảo vệ và retention policy.

### 10.1. Consent và user control

Người dùng cần hiểu biometric được dùng để mở khóa điều gì. Ví dụ, app có thể giải thích rằng Face ID chỉ mở khóa key trên thiết bị; dịch vụ không nhận ảnh khuôn mặt. Không dùng thông điệp mơ hồ khiến người dùng nghĩ họ đang gửi dữ liệu khuôn mặt lên server.

Nếu app không còn hỗ trợ hoặc user tắt biometric, cần xóa/revoke local key theo policy và chuyển sang fallback đã được thiết kế.

## 11. Threat model

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Biometric spoofing** | Ảnh, video, mặt nạ hoặc bản sao giả mạo sensor | OS biometric class, liveness/platform control và policy thiết bị |
| **Local state bypass** | Attacker sửa boolean unlocked trong app | Key access control của OS, server-side proof và integrity |
| **Key extraction** | Malware/root tìm cách lấy private key | Keystore/Secure Enclave, non-exportable key và hardware backing |
| **Biometric enrollment change** | Attacker thêm biometric của họ vào thiết bị | Invalidate key theo current-set policy, re-enrollment và notification |
| **Device theft** | Kẻ trộm thử mở khóa app | OS lockout, short session, device passcode và remote revoke |
| **Fallback downgrade** | Attacker chọn recovery yếu hơn biometric | Recovery policy tương đương rủi ro, re-proofing và audit |
| **Root/jailbreak** | Attacker có quyền cao can thiệp app/runtime | Device posture/risk, key protection và server validation |
| **Prompt confusion** | User bị dụ xác nhận prompt không mong muốn | Prompt text rõ, bind với action và transaction |
| **Replay signature** | Chữ ký challenge cũ được gửi lại | Nonce, expiry, one-time challenge và transaction binding |
| **Session theft** | Token/session lộ dù app có biometric | Secure storage, token lifetime, revocation và TLS |
| **Privacy leakage** | App/SDK thu thập ảnh hoặc template | OS-only matching, data minimization và SDK review |
| **Biometric lockout DoS** | Attacker cố ý gây nhiều lần thất bại | OS-managed lockout, fallback an toàn và rate limit |

### 11.1. Rooted và jailbroken device

Root/jailbreak có thể làm suy yếu isolation, hook API, đọc memory hoặc can thiệp app. Detection không hoàn hảo và attacker có thể né. Không dùng root detection làm bằng chứng duy nhất cho authentication.

Với thao tác nhạy cảm, có thể kết hợp device integrity/attestation theo nền tảng, hardware-backed key, short-lived token và risk policy. Server cần quyết định khi attestation thiếu hoặc thiết bị không đáp ứng yêu cầu.

### 11.2. Prompt phải gắn với hành động

Nếu prompt chỉ ghi Authenticate, người dùng khó hiểu họ đang cho phép điều gì. Với thao tác nhạy cảm, UI cần hiển thị ngữ cảnh rõ như Xác nhận dùng passkey để ký đăng nhập hoặc Mở khóa khóa ký giao dịch. Nếu có thể, challenge phải ràng buộc amount, destination hoặc transaction ID để chữ ký không thể chuyển sang giao dịch khác.

## 12. Thiết kế local unlock an toàn

Một pattern local unlock có thể gồm:
1. User đăng nhập từ xa bằng flow chính thức.
2. App nhận session/token theo policy.
3. App tạo hoặc lấy key mã hóa local được bảo vệ bởi biometric/device credential.
4. App lưu token/secret ở Keychain/Keystore với access control phù hợp.
5. Khi mở app, OS xác minh user trước khi cho dùng key.
6. App kiểm tra session và token lifecycle.
7. Nếu session hết hạn, app thực hiện refresh hoặc yêu cầu login lại.
8. Nếu biometric enrollment thay đổi và key bị invalidated, app chạy recovery/re-enrollment.

Không lưu access token trong plaintext chỉ vì màn hình đã được khóa bằng biometric. Khóa biometric cần bảo vệ chính secret/key mà app dùng, không chỉ bảo vệ UI.

### 12.1. Không dùng boolean làm khóa bảo mật

Anti-pattern:

~~~text
if biometricSuccess:
    preferences.set("isUnlocked", true)

if preferences.get("isUnlocked"):
    showSensitiveData()
~~~

Giá trị boolean trong storage của app có thể bị sửa hoặc replay. Thay vào đó, bảo vệ key/data bằng OS access control và kiểm tra session/authorization độc lập.

### 12.2. Data encryption at rest

Nếu app lưu dữ liệu nhạy cảm offline, dùng encryption key được bảo vệ bởi Keystore/Keychain. Có thể yêu cầu biometric hoặc device credential trước khi giải mã. Phân biệt:
- Key mã hóa dữ liệu local.
- Private key ký challenge cho server.
- Access/refresh token dùng truy cập API.
- Session cookie hoặc local session handle.

Không dùng một key cho mọi mục đích. Dùng key separation và metadata/purpose rõ ràng.

## 13. Thiết kế remote proof bằng biometric-gated key

Nếu cần chứng minh người dùng vừa xác minh trên thiết bị, một private key có thể yêu cầu user authentication trước khi ký. Server đăng ký public key và phát challenge theo transaction.

~~~mermaid
flowchart TD
    A[User bắt đầu action nhạy cảm] --> B[Server tạo challenge một lần]
    B --> C[App nhận challenge + transaction context]
    C --> D[OS yêu cầu biometric/user verification]
    D --> E{Verification thành công?}
    E -- Không --> X[Hủy hoặc fallback theo policy]
    E -- Có --> F[OS cho phép dùng private key]
    F --> G[Ký challenge và transaction digest]
    G --> H[Server verify public key/signature]
    H --> I{Nonce, expiry, binding và policy hợp lệ?}
    I -- Không --> X
    I -- Có --> J[Authorize action và audit]
~~~

Server cần kiểm tra:
- Challenge sinh ngẫu nhiên, gắn principal và transaction.
- Challenge chưa dùng, chưa hết hạn và đúng audience.
- Chữ ký hợp lệ với public key đã đăng ký.
- Key chưa bị revoke hoặc thay thế.
- Request gắn với đúng action/resource.
- User verification property được bảo đảm bởi credential enrollment/profile đã tin cậy.
- Authorization vẫn cho phép hành động.

Một chữ ký hợp lệ chỉ chứng minh private key đã được sử dụng. Để kết luận user verification đã diễn ra, server cần tin cậy cách key được provision, access control được cấu hình và evidence/attestation phù hợp. Không thể suy ra điều đó chỉ từ chữ ký ECDSA.

### 13.1. Challenge không được tái sử dụng

Server tạo nonce mới cho mỗi transaction, lưu trạng thái và consume atomically. Nếu client retry do timeout, cần phân biệt retry cùng transaction với request mới. Idempotency key ở tầng nghiệp vụ có thể giúp tránh lặp side effect; nonce vẫn cần ngăn replay challenge.

### 13.2. Transaction binding

Với thanh toán, challenge nên gắn với amount, currency, destination, transaction ID và thời hạn. Nếu user xác nhận một giao dịch nhưng attacker thay body trước khi gửi, server phải phát hiện digest không khớp.

## 14. Fallback và recovery policy

Biometric có thể mất khả dụng khi:
- User xóa hoặc thêm biometric.
- Sensor hỏng.
- OS lockout.
- Thiết bị reset hoặc đổi máy.
- Key bị invalidated.
- App bị cài lại.
- User đổi device passcode hoặc security setting theo policy nền tảng.

Recovery phải xác định lại quyền kiểm soát account hoặc đăng ký key mới theo mức rủi ro. Không để fallback yếu hơn trở thành đường bypass toàn bộ bảo vệ.

Một quy trình có thể:
1. Phát hiện local key không dùng được.
2. Giải thích nguyên nhân ở mức phù hợp.
3. Yêu cầu login/recovery bằng credential khác đã đăng ký.
4. Step-up hoặc identity proofing nếu cần.
5. Revoke device key cũ trên server.
6. Đăng ký key mới và xác minh public key.
7. Thông báo thay đổi qua kênh đã xác minh.
8. Ghi audit và cập nhật device inventory.

Không yêu cầu người dùng upload ảnh khuôn mặt/vân tay để khôi phục biometric nếu app chỉ dùng platform biometric. OS sẽ quản lý enrollment; app chỉ cần đăng ký lại key hoặc credential.

## 15. Monitoring, audit và user notification

Biometric unlock cục bộ không cần gửi từng kết quả matching về server. Tuy nhiên, các sự kiện credential/key lifecycle và remote proof có thể cần audit.

Có thể ghi:
- Device/credential reference.
- Key ID và public key fingerprint/reference.
- Enrollment, activation, invalidation, rotation và revocation.
- Remote challenge ID và transaction reference.
- Kết quả signature verification.
- Authentication context được khẳng định theo policy.
- OS/platform capability ở mức cần thiết.
- Thời điểm, app version và reason code.

Không ghi:
- Fingerprint/face template.
- Ảnh camera hoặc raw sensor data.
- Private key.
- Access/refresh token thô.
- Biometric secret hoặc dữ liệu nhạy cảm không cần thiết.

Thông báo người dùng khi có key mới được đăng ký, biometric enrollment change làm mất key, thiết bị bị revoke hoặc có remote authentication bất thường. Không gửi nội dung sinh trắc học trong thông báo.

## 16. Ví dụ: mở khóa ứng dụng ngân hàng

Một ứng dụng ngân hàng đã đăng nhập và muốn cho phép user mở lại app bằng Face ID. Ứng dụng lưu một key trong Keychain/Keystore, key chỉ được sử dụng sau local user verification.

Flow:
1. User đăng nhập bằng OIDC/passkey hoặc phương thức tài khoản theo policy.
2. App tạo key bảo vệ local token/session handle với access control phù hợp.
3. App chuyển background và khóa màn hình chứa dữ liệu nhạy cảm.
4. User quay lại app.
5. App yêu cầu LocalAuthentication hoặc BiometricPrompt.
6. OS xác minh Face ID/vân tay và cho phép dùng key.
7. App lấy token/secret từ secure storage và kiểm tra expiry/revocation theo policy.
8. Nếu token còn hợp lệ, app hiển thị dữ liệu được phép.
9. Nếu token hết hạn, app refresh hoặc yêu cầu login lại.
10. Nếu key bị invalidated do biometric enrollment change, app yêu cầu recovery/re-enrollment.
11. Với chuyển tiền, app có thể yêu cầu remote challenge và ký transaction bằng key có user authentication requirement.

~~~mermaid
sequenceDiagram
    participant U as User
    participant App as Banking App
    participant OS as Secure OS / Key Store
    participant API as Banking API
    U->>App: Mở lại ứng dụng
    App->>OS: Yêu cầu biometric để dùng local key
    OS->>U: Face ID / fingerprint prompt
    U->>OS: Xác minh
    OS-->>App: Cho phép key operation
    App->>OS: Lấy/decrypt local session material
    App->>API: Request với access token còn hiệu lực
    API->>API: Verify token và authorization
    API-->>App: Dữ liệu theo quyền
    App-->>U: Hiển thị màn hình
~~~

Nếu user chỉ mở app, biometric có thể là local unlock. Khi user chuyển tiền, app có thể cần thêm remote proof hoặc transaction confirmation. Không tự động coi local unlock vừa xảy ra là bằng chứng đủ mạnh cho mọi hành động.

## 17. Kiểm thử biometric unlock

| Test case | Kết quả mong đợi |
| --- | --- |
| Biometric enrolled và prompt thành công | Chỉ mở đúng resource/key theo policy |
| User cancel | Không mở khóa; cho phép thử lại hoặc fallback an toàn |
| Biometric mismatch | Không cấp key operation |
| Sensor unavailable | Hiển thị fallback theo policy |
| OS lockout | Tôn trọng lockout, không prompt loop |
| Device credential fallback | Ghi đúng authentication context; không gọi nhầm là biometric |
| Biometric chưa enrolled | Hướng dẫn enrollment hoặc fallback đã định nghĩa |
| Biometric enrollment thay đổi | Key invalidation/re-enrollment hoạt động theo policy |
| Key không hardware-backed khi yêu cầu hardware | Từ chối hoặc hạ assurance theo policy rõ |
| App process bị kill | Không giữ boolean unlock có thể replay |
| App chuyển background quá lâu | Khóa lại theo idle/session policy |
| Access token hết hạn | Refresh hoặc yêu cầu login lại |
| Account/session bị revoke | Không mở quyền chỉ vì biometric local thành công |
| Root/jailbreak signal | Risk policy áp dụng; không dựa vào detection duy nhất |
| Prompt bị hủy giữa chừng | Không ký challenge hoặc thực hiện side effect |
| Server challenge hết hạn | Chữ ký không được chấp nhận |
| Challenge bị replay | Từ chối do nonce đã consume |
| Signature dùng key đã revoke | Từ chối |
| Transaction body bị thay đổi | Digest/binding mismatch |
| Key invalidated | Recovery/re-enrollment, không fallback ngầm |
| Private key extraction attempt | Key không export được theo platform guarantee |
| Biometric template inspection | App không có API hoặc lưu trữ template |
| Analytics/log inspection | Không có biometric data, token hoặc private key |
| iOS biometricCurrentSet change | Keychain item invalidated theo cấu hình |
| Android invalidatedByBiometricEnrollment | Key invalidation xử lý theo cấu hình |
| Multi-device enrollment | Mỗi device/key được quản lý và revoke riêng |

## 18. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Mục đích biometric được xác định? | Local unlock và remote authentication tách biệt |
| App có thu thập template? | Không; OS quản lý matching |
| Có dùng API hệ điều hành? | BiometricPrompt/LocalAuthentication |
| Security level phù hợp? | Android strong hoặc platform capability theo risk |
| Key có access control? | Keychain/Keystore yêu cầu user verification |
| Remote proof có chữ ký? | Challenge, key binding và server validation |
| Có phân biệt device credential fallback? | Authentication context chính xác |
| Enrollment change có xử lý? | Key invalidation và re-enrollment |
| Key có thể revoke? | Device inventory, key status và server revoke |
| Session vẫn có expiry? | Local unlock không tạo session vô hạn |
| Recovery có an toàn? | Proofing, step-up và notification |
| App lifecycle được xử lý? | Background/idle/process death khóa lại |
| Root/jailbreak được đánh giá? | Risk/attestation theo policy, không dựa một tín hiệu |
| Prompt gắn với action? | User biết đang mở khóa hoặc ký điều gì |
| Replay được ngăn? | Challenge one-time, expiry và transaction binding |
| Privacy được bảo vệ? | Không log/upload biometric data |
| Có test fallback và lockout? | Cancel, unavailable, enrollment change và recovery |
| Có kiểm tra backend? | Token/session/authorization vẫn được xác minh |

### Tình huống tự kiểm tra

**Tình huống 1:** App gọi Face ID thành công rồi gửi một boolean biometricSuccess=true lên server. Server có thể coi đây là remote authentication mạnh không?

**Trả lời:** Không. Boolean do app gửi không phải bằng chứng mật mã. Cần key được bảo vệ bởi OS, ký challenge và server xác minh public key cùng transaction.

**Tình huống 2:** Server cần biết người dùng dùng ngón tay nào để xác minh?

**Trả lời:** Không. Server thường chỉ cần xác minh chữ ký của key đã đăng ký. Template sinh trắc học được OS quản lý cục bộ.

**Tình huống 3:** Người dùng thêm một dấu vân tay mới. App có nên tiếp tục dùng key cũ mà không đánh giá không?

**Trả lời:** Phụ thuộc access control. Nếu key được ràng buộc với biometric set hiện tại, enrollment change có thể invalidated key; app cần recovery/re-enrollment theo policy.

**Tình huống 4:** Thiết bị Android chỉ hỗ trợ BIOMETRIC_WEAK nhưng ứng dụng yêu cầu key operation với biometric mạnh. Có nên âm thầm hạ xuống weak không?

**Trả lời:** Không. Cần từ chối hoặc áp dụng fallback được policy cho phép, và ghi đúng assurance. Không tuyên bố mức bảo vệ mạnh hơn khả năng thiết bị.

**Tình huống 5:** User vừa mở khóa app bằng biometric. Có thể bỏ qua expiry của access token không?

**Trả lời:** Không. Local unlock và token lifetime là hai lớp khác nhau. Server vẫn kiểm tra expiry, revocation và authorization.

**Tình huống 6:** App dùng Secure Enclave để ký challenge. Chữ ký có tự chứng minh Face ID vừa được dùng không?

**Trả lời:** Không tự động. Key phải được cấu hình access control yêu cầu biometric/user verification và server cần tin cậy provisioning/evidence phù hợp. Chữ ký chỉ chứng minh private key đã được sử dụng.

**Tình huống 7:** User mất khả năng dùng Face ID. Có nên cho phép một email link chưa xác minh thay thế ngay lập tức không?

**Trả lời:** Không. Recovery phải có assurance phù hợp, kiểm tra account/session, revoke key cũ và thông báo qua kênh đã xác minh.

## 19. Ghi nhớ

**Biometric unlock thường là xác minh cục bộ do hệ điều hành và phần cứng thiết bị quản lý.** Ứng dụng không nên thu thập template sinh trắc học. Việc mở khóa UI hoặc dữ liệu local không tự trở thành bằng chứng xác thực từ xa; server vẫn cần token/session hợp lệ hoặc proof-of-possession được tạo bằng key bảo vệ bởi user verification.

Trên Android, dùng BiometricPrompt kết hợp Android Keystore/CryptoObject khi cần key operation. Trên iOS, dùng LocalAuthentication và Keychain/Secure Enclave access control. Phân biệt biometric với device credential fallback, xử lý lockout và enrollment change, bảo vệ session lifecycle, cung cấp recovery an toàn và không dựa vào boolean local. Với remote action, dùng challenge one-time, chữ ký và transaction binding; server xác minh public key, freshness, revocation và authorization. Privacy, key lifecycle và kiểm thử thiết bị thực là các phần thiết yếu của thiết kế.
