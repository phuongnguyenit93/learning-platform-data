# Mobile authentication

**Mobile authentication** là quá trình một ứng dụng di động, người dùng hoặc thiết bị chứng minh danh tính và quyền kiểm soát credential trước khi được cấp quyền truy cập dịch vụ. Một luồng mobile có thể kết hợp mật khẩu, MFA, passkey, authenticator của hệ điều hành, chứng chỉ thiết bị, OAuth/OIDC, token và session. Thiết kế an toàn phải xem xét cả ứng dụng, hệ điều hành, thiết bị, trình duyệt hệ thống, mạng và backend.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Mobile authentication kết nối các chủ đề đó trong môi trường có đặc điểm riêng: thiết bị có thể mất hoặc bị chia sẻ, ứng dụng có thể bị phân tích ngược, token có thể bị sao chép từ vùng lưu trữ yếu, deep link có thể bị ứng dụng khác chiếm và kết nối mạng thường xuyên thay đổi.

Điểm cốt lõi: **không thể coi ứng dụng mobile là một môi trường bí mật chỉ vì nó chạy trên điện thoại của người dùng**. Có thể kiểm soát tốt hơn bằng API chuẩn, browser hệ thống, PKCE, secure storage, authenticator chống phishing, token lifetime phù hợp và kiểm tra authorization ở server. Những tín hiệu như device ID, jailbreak detection hoặc app attestation chỉ là một phần của risk decision, không thay thế xác thực danh tính và kiểm soát quyền ở backend.

## 1. Mobile authentication là gì?

Mobile authentication là tập hợp các bước xác minh user, application client hoặc device trước khi cho phép truy cập tài nguyên. Cần phân biệt ba principal có thể xuất hiện trong một request:

- **User principal:** người dùng đã đăng nhập và được nhận diện bởi IdP hoặc hệ thống account.
- **Application/client principal:** ứng dụng mobile được đăng ký với authorization server, thường qua client ID và redirect URI.
- **Device/workload principal:** thiết bị hoặc thành phần runtime có thể được chứng minh bằng certificate, attestation hoặc workload identity.

Một ứng dụng mobile công khai thường không thể giữ client secret cố định một cách đáng tin. Mã ứng dụng có thể được tải xuống, phân tích và trích xuất; vì vậy client ID không phải secret và không nên dùng một shared secret nhúng trong binary để chứng minh ứng dụng là confidential client.

### 1.1. Các luồng phổ biến

| Luồng | Mục đích | Thành phần chính |
| --- | --- | --- |
| **Password + MFA** | Người dùng xác thực với IdP hoặc backend. | Password verifier, MFA challenge, risk policy. |
| **OAuth/OIDC Authorization Code + PKCE** | App nhận token sau khi người dùng xác thực tại authorization server. | System browser, redirect URI, state, PKCE. |
| **Passkey/WebAuthn** | Xác thực chống phishing bằng public-key credential. | OS authenticator, RP ID/origin, challenge. |
| **Local biometric unlock** | Mở khóa dữ liệu hoặc khóa cục bộ sau khi thiết bị xác minh user. | Face/fingerprint/PIN, Keychain/Keystore. |
| **Device certificate/mTLS** | Chứng minh device hoặc managed app với backend. | X.509 certificate, private key, CA/trust policy. |
| **Federated device identity** | Đổi bằng chứng từ nền tảng quản lý thiết bị thành credential có phạm vi. | Device management, attestation, identity provider. |

Các luồng có thể kết hợp. Ví dụ, user đăng nhập bằng passkey qua system browser, authorization server phát access token, app lưu refresh token trong secure storage và yêu cầu local biometric trước khi dùng khóa giải mã token.

### 1.2. Authentication, device trust và authorization

Đăng nhập thành công xác minh một principal theo policy. Nó không tự chứng minh:
- Thiết bị chưa bị compromise.
- Ứng dụng chưa bị sửa đổi.
- Người dùng được phép truy cập mọi dữ liệu.
- Token chưa bị sao chép.
- Request hiện tại được gửi bởi đúng thiết bị ban đầu.

Backend phải xác minh token, issuer, audience, thời hạn và quyền trên resource. Nếu policy cần device posture, hãy đánh giá nó như một tín hiệu bổ sung có provenance và freshness rõ ràng.

## 2. Threat model của ứng dụng mobile

Thiết bị mobile có nhiều lớp bảo vệ từ OS, nhưng ứng dụng vẫn hoạt động trong môi trường mà người dùng có thể cài app khác, bật developer mode, backup dữ liệu hoặc kết nối thiết bị với máy tính.

### 2.1. Tài sản cần bảo vệ

- Password, OTP, recovery code và passkey enrollment transaction.
- Access token, refresh token, session cookie và authorization code.
- Private key, client certificate, device key và encryption key.
- Account identifier, profile, tenant và dữ liệu cá nhân.
- Local database, cache, file tải xuống và thông báo.
- Deep link, redirect URI và app-to-app communication.
- Device enrollment, attestation result và trust state.
- Logs, crash report, analytics và backup.

### 2.2. Đối thủ và bề mặt tấn công

Threat model nên xét:
- Người khác cầm được thiết bị đã mở khóa.
- Malware hoặc ứng dụng độc hại trên cùng thiết bị.
- App giả mạo, overlay hoặc accessibility abuse.
- Attacker phân tích ngược binary và trích xuất cấu hình.
- Attacker kiểm soát Wi-Fi, DNS hoặc proxy trên mạng.
- Thiết bị root/jailbreak hoặc OS đã lỗi thời.
- Deep link bị ứng dụng khác đăng ký/chiếm.
- Backup hoặc debug interface làm lộ token.
- API bị gọi trực tiếp mà bỏ qua UI và kiểm tra client.
- Người dùng bị phishing hoặc social engineering.

Không giả định mọi thiết bị root/jailbreak đều bị compromise và mọi thiết bị không root đều an toàn. Đây là tín hiệu rủi ro, không phải bằng chứng tuyệt đối.

## 3. OAuth/OIDC cho ứng dụng native

Với ứng dụng native cần đăng nhập liên kết, thực hành phổ biến là Authorization Code Flow với Proof Key for Code Exchange (PKCE), mở authorization endpoint bằng external user-agent/system browser và nhận callback qua redirect URI đã đăng ký.

### 3.1. Vì sao dùng system browser?

System browser hoặc browser tab được hệ điều hành quản lý giúp:
- Tái sử dụng IdP session mà không chia sẻ password với app.
- Giữ trang xác thực trong origin của IdP.
- Tận dụng password manager, passkey và cơ chế bảo vệ của browser.
- Giảm rủi ro app tự dựng webview giả trang đăng nhập.
- Cho phép người dùng kiểm tra domain của authorization server.

Embedded WebView do ứng dụng kiểm soát thường không phù hợp cho đăng nhập liên kết vì app có thể quan sát nội dung nhập, can thiệp điều hướng hoặc tạo UI giống IdP. Dùng external user-agent theo native app best practice của OAuth.

### 3.2. Authorization Code + PKCE

Luồng tổng quát:

    Mobile app
       |
       | Tạo code_verifier ngẫu nhiên và code_challenge
       |
       | Mở system browser
       v
    Authorization server / IdP
       |
       | User authentication + consent/policy
       |
       | Redirect về registered URI với authorization code + state
       v
    Mobile app
       |
       | Kiểm tra state và transaction
       | Gửi code + code_verifier tới token endpoint
       v
    Authorization server
       |
       | Kiểm tra PKCE và redirect/client context
       | Cấp token theo grant
       v
    Mobile app
       |
       | Lưu credential theo policy trong secure storage
       v
    Resource API

Ứng dụng tạo code_verifier đủ ngẫu nhiên, giữ trong transaction hiện tại và gửi code_challenge theo phương thức S256. Khi đổi code, app gửi verifier. Authorization server chỉ cấp token nếu verifier khớp challenge đã gắn với authorization request.

PKCE chống việc một ứng dụng khác chặn authorization code rồi tự đổi code lấy token. Nó không thay thế TLS, state, redirect URI validation hoặc bảo vệ thiết bị.

### 3.3. State, nonce và transaction binding

- **state** liên kết callback với authorization request do app khởi tạo và giúp chống login CSRF/callback injection.
- **nonce** trong OIDC liên kết ID Token với authentication request và chống replay/substitution theo flow.
- **code_verifier** chứng minh app khởi tạo transaction kiểm soát secret tương ứng với challenge.
- **redirect URI** xác định nơi authorization response được gửi.

Mỗi transaction cần state/nonce/verifier ngẫu nhiên, đủ entropy, có TTL và chỉ dùng một lần. Lưu chúng tạm trong vùng phù hợp; không tái sử dụng qua nhiều lần đăng nhập. Kiểm tra callback đúng scheme/host/path và transaction đang chờ.

### 3.4. Không nhúng client secret trong mobile binary

Ứng dụng cài trên thiết bị người dùng là public client. Secret đặt trong source, resource, native library hoặc obfuscation vẫn có thể bị trích xuất. Không dùng client secret tĩnh để phân biệt app hợp pháp.

Có thể dùng client ID công khai cùng PKCE và redirect URI được đăng ký. Nếu cần chứng minh app/device theo risk policy, dùng app attestation hoặc device certificate có quy trình cấp/kiểm tra riêng; đừng gọi chúng là client secret.

## 4. Redirect URI, deep link và callback an toàn

Sau khi IdP hoàn tất xác thực, authorization response cần quay lại đúng ứng dụng. Trên mobile có thể dùng custom URL scheme, claimed HTTPS link (Universal Links/App Links) hoặc loopback redirect cho một số loại client cục bộ.

### 4.1. Custom URL scheme

Ví dụ minh họa:

    com.example.learning://oauth/callback

Custom scheme có thể được đăng ký bởi nhiều ứng dụng. Nếu app độc hại đăng ký cùng scheme, nó có thể nhận callback tùy theo cách OS xử lý. PKCE làm giảm nguy cơ đổi authorization code bị chặn, nhưng app vẫn phải validate state và không đưa token trực tiếp trong URL.

Không đặt access token hoặc refresh token trong query/fragment của redirect URI. Authorization code có lifetime ngắn và được bảo vệ bởi PKCE; token nên được nhận qua token endpoint.

### 4.2. Claimed HTTPS links

Universal Links trên iOS và Android App Links cho phép domain xác nhận ứng dụng được phép xử lý link qua association file được host trên domain chính thức. Chúng giảm nguy cơ app khác chiếm callback so với custom scheme, nhưng cần:
- Domain HTTPS chính thức và association file chính xác.
- Bundle ID/package name và signing fingerprint phù hợp.
- Kiểm tra callback path và state ở app.
- Cấu hình asset links/association được cập nhật cùng release.
- Xử lý khi app chưa cài hoặc link mở trong browser.

Association file không thay thế PKCE. App vẫn cần xác minh transaction và authorization code.

### 4.3. Kiểm tra callback

Khi nhận callback:
1. Parse URL bằng parser chuẩn của platform.
2. Xác minh scheme/host/path nằm trong allowlist đã đăng ký.
3. Từ chối URL có cấu trúc bất thường hoặc nhiều tham số trùng lặp.
4. Tìm transaction đang chờ theo state và kiểm tra TTL.
5. Đảm bảo transaction chưa được tiêu thụ.
6. Xử lý error response theo hợp đồng.
7. Chỉ gửi authorization code tới token endpoint đã cấu hình.
8. Không log URL chứa code, state hoặc dữ liệu nhạy cảm.

Không tin deep link chỉ vì nó được hệ điều hành chuyển tới app. Một ứng dụng khác có thể gửi intent hoặc URL do nó tự tạo.

## 5. Secure storage trên iOS và Android

Mobile app thường cần giữ refresh token, private key reference hoặc dữ liệu nhạy cảm qua nhiều lần mở app. Không lưu bearer credential trong nơi mọi ứng dụng hoặc backup có thể đọc.

### 5.1. iOS Keychain và Secure Enclave

Keychain cung cấp cơ chế lưu secret và key với access control do hệ điều hành quản lý. Secure Enclave có thể tạo và sử dụng private key trong phần cứng được bảo vệ trên thiết bị hỗ trợ; private key có thể không thể export ra ngoài.

Thiết kế cần quyết định:
- Keychain accessibility class phù hợp với nhu cầu khi khóa/mở thiết bị.
- Có yêu cầu device passcode không.
- Có yêu cầu user presence hoặc biometric access control không.
- Credential có được migrate qua backup/device restore hay phải enroll lại.
- Access group nào được chia sẻ giữa app/extension.
- Hành vi khi user thay đổi biometric enrollment hoặc passcode.

Không coi mọi item Keychain đều được bảo vệ giống nhau; cấu hình accessibility và access control ảnh hưởng đáng kể tới mức bảo vệ.

### 5.2. Android Keystore và hardware-backed key

Android Keystore cho phép ứng dụng tạo và sử dụng key mà private key material có thể không rời khỏi keystore. Trên thiết bị hỗ trợ, key có thể được bảo vệ bởi TEE hoặc StrongBox. App có thể đặt user authentication requirement và giới hạn mục đích sử dụng key.

Cần:
- Kiểm tra key purpose, algorithm, digest, padding và authentication policy.
- Dùng hardware-backed key khi threat model yêu cầu và thiết bị hỗ trợ.
- Kiểm tra attestation chain/claims nếu có dùng attestation.
- Có fallback policy cho thiết bị không hỗ trợ phần cứng tương ứng.
- Không giả định mọi Android device có cùng mức hardware protection.

### 5.3. Không lưu token trong nơi dễ đọc

Tránh lưu refresh token hoặc private key trong:
- Plaintext SharedPreferences/UserDefaults.
- File cấu hình hoặc database không mã hóa.
- External/shared storage.
- Clipboard, screenshot hoặc notification.
- Log, crash dump và analytics.
- Source code, resource bundle hoặc build artifact.

Nếu cần database local, có thể mã hóa dữ liệu bằng key được giữ trong OS secure storage. Cần quản lý backup, restore, key rotation và deletion. Mã hóa file bằng một key hardcode trong binary không tạo ra ranh giới bảo mật hữu ích.

### 5.4. Backup và device migration

Backup có thể sao chép dữ liệu ứng dụng sang thiết bị mới. Với bearer token, điều này có thể tạo bản sao credential ngoài dự kiến. Quy định rõ dữ liệu nào được backup:
- Có thể backup preference không nhạy cảm.
- Không backup refresh token hoặc key không được phép di chuyển.
- Credential cần device binding phải được tạo lại trên thiết bị mới.
- Sau restore, yêu cầu authentication hoặc enrollment lại theo policy.
- Khi thiết bị cũ mất, revoke session/credential gắn với thiết bị đó.

Không mặc định restore thành công đồng nghĩa thiết bị mới được tin cậy như thiết bị cũ.

## 6. Biometric và local user verification

Sinh trắc học trên mobile thường được dùng để xác minh người đang cầm thiết bị trước khi OS cho phép ứng dụng sử dụng một key hoặc mở dữ liệu cục bộ. Đây là local user verification; dữ liệu sinh trắc học thường do OS quản lý và không cần gửi về backend.

### 6.1. Biometric prompt không phải password gửi lên server

Khi app gọi API biometric của hệ điều hành:
- OS hiển thị prompt do platform kiểm soát.
- Sensor/secure subsystem xử lý mẫu sinh trắc học.
- OS trả kết quả xác minh hoặc mở quyền sử dụng key theo access control.
- App tiếp tục thao tác cục bộ hoặc dùng key để ký/decrypt.

Backend thường không nhận fingerprint/face template. Server chỉ có thể nhận bằng chứng mật mã hoặc token của một flow riêng nếu kiến trúc thiết kế như vậy.

Không tự thu thập, lưu hoặc gửi biometric template lên server chỉ để “xác thực mobile”. Sinh trắc học có tính nhạy cảm và không thể thay đổi dễ dàng như password.

### 6.2. Biometric-gated key

Một cách thiết kế là tạo key trong Keychain/Keystore với policy yêu cầu user presence hoặc biometric/device credential trước khi sử dụng. App có thể dùng key để:
- Giải mã refresh token được lưu dạng ciphertext.
- Ký một challenge server gửi tới.
- Mở khóa local vault.
- Chứng minh quyền kiểm soát key theo protocol đã thiết kế.

Nếu chỉ dùng biometric để mở một biến boolean trong app, attacker có thể bypass logic bằng instrumentation hoặc patch binary. Ràng buộc nên nằm trong OS key access control và server phải xác minh proof khi cần.

### 6.3. Biometric enrollment thay đổi

Người dùng có thể thêm hoặc xóa dấu vân tay/khuôn mặt trong cài đặt OS. Một số key access control có thể invalidated khi biometric set thay đổi; hành vi phụ thuộc platform và policy được chọn.

Ứng dụng cần:
- Xử lý key invalidation như một trạng thái cần re-auth/enrollment.
- Không tự động hạ xuống phương thức yếu hơn mà không có policy.
- Thông báo và hướng dẫn recovery an toàn.
- Kiểm thử khi thêm/xóa biometric, thay passcode và khôi phục thiết bị.

### 6.4. Fallback và khả năng tiếp cận

Không phải mọi người dùng đều có thể hoặc muốn dùng biometric. Cung cấp fallback được bảo vệ như device passcode, passkey, security key hoặc re-authentication theo policy. Không để fallback làm giảm assurance quá mức cho action nhạy cảm.

## 7. Passkey và WebAuthn trên mobile

Passkey có thể được đồng bộ trong hệ sinh thái platform hoặc gắn với security key/hardware authenticator. Ứng dụng mobile thường khởi tạo passkey ceremony qua API của OS/browser, trong khi RP server quản lý challenge và public key credential.

### 7.1. Registration

Luồng registration:
1. User đã được xác thực vào account hiện tại.
2. RP server tạo challenge ngẫu nhiên, một lần và có TTL.
3. App gọi platform credential manager/authenticator API.
4. OS hiển thị account/biometric/device prompt.
5. Authenticator tạo credential key pair gắn với RP ID.
6. App gửi attestation/credential response về RP.
7. Server xác minh challenge, origin/RP ID, flags, credential ID và public key theo policy.
8. Server lưu public key và metadata; private key ở authenticator.

Không kích hoạt passkey mới chỉ vì app nhận được một callback. Server phải xác minh ceremony và ràng buộc với account/session đã được xác thực.

### 7.2. Authentication

Luồng authentication:
1. RP server tạo challenge mới.
2. App yêu cầu platform authenticator tìm credential cho RP ID.
3. Người dùng xác minh cục bộ theo policy.
4. Authenticator ký assertion gắn challenge và RP context.
5. Server xác minh chữ ký, challenge, origin/RP ID, credential status và flags.
6. Server tạo session hoặc phát hành token theo policy.

Passkey chống phishing vì credential bị ràng buộc với RP ID/origin. Tuy nhiên, account recovery, device enrollment và app/backend compromise vẫn cần kiểm soát riêng.

### 7.3. Synced passkeys và device-bound credentials

Passkey có thể được đồng bộ giữa thiết bị qua hệ sinh thái của nhà cung cấp platform. Một số authenticator hoặc security key giữ credential gắn với thiết bị/phần cứng. Policy cần hiểu:
- Credential có thể sync hay không.
- Account của platform dùng để sync được bảo vệ ra sao.
- Thiết bị mới có thể khôi phục passkey bằng cách nào.
- RP nhận được metadata gì và không thể biết chắc điều gì.
- Khi user mất thiết bị, có cần revoke credential riêng hay không.

Không giả định passkey đồng bộ đồng nghĩa mọi thiết bị đã được tổ chức quản lý. RP nên quản lý credential list, last-used metadata và quy trình revoke.

## 8. Device identity, attestation và device trust

Một ứng dụng có thể cần biết request đến từ app/device hợp lệ, ví dụ để giảm abuse hoặc bảo vệ API nhạy cảm. Device identity và attestation có thể cung cấp tín hiệu, nhưng không chứng minh trực tiếp danh tính con người.

### 8.1. App attestation và device integrity

Các platform có cơ chế như Apple App Attest/DeviceCheck và Google Play Integrity API. Tùy API và cấu hình, backend có thể nhận bằng chứng về app instance, app identity, integrity verdict hoặc môi trường thiết bị.

Cần:
- Backend xác minh token/attestation response bằng cơ chế server-side của platform.
- Ràng buộc challenge để chống replay.
- Ràng buộc verdict với app, environment và request quan trọng.
- Kiểm tra timestamp/nonce và policy version.
- Không tin verdict do app tự gửi dưới dạng boolean.
- Có chính sách cho thiết bị không hỗ trợ hoặc không đạt verdict.

Attestation không phải phép đo hoàn hảo. Nó có thể bị giới hạn bởi platform, thiết bị, phiên bản OS, privacy policy và mô hình threat. Một verdict tốt không chứng minh user là chủ account hoặc request nghiệp vụ được phép.

### 8.2. Device binding

Có thể tạo key pair riêng cho app/device và đăng ký public key với backend sau một flow xác minh. Request nhạy cảm có thể yêu cầu chữ ký challenge bằng private key đó.

Device binding cần:
- Enrollment có xác minh account và risk policy.
- Private key được giữ trong Keystore/Secure Enclave khi hỗ trợ.
- Server lưu public key, device reference và trạng thái.
- Challenge có nonce, expiry và audience/action binding.
- Rotation/re-enrollment khi thiết bị thay đổi.
- Revoke khi mất thiết bị hoặc có dấu hiệu compromise.

Device ID do app tự tạo hoặc ID phần cứng có thể bị giả mạo, reset hoặc hạn chế bởi privacy policy; không dùng nó làm secret authentication factor.

### 8.3. Jailbreak/root detection

Root/jailbreak detection, debugger detection và runtime integrity checks có thể làm tăng chi phí tấn công hoặc cung cấp risk signal. Nhưng chúng có false positive, có thể bị bypass và có thể gây loại nhầm thiết bị hợp lệ.

Dùng như một input trong risk-based policy:
- Hành động nhạy cảm có thể yêu cầu step-up hoặc từ chối khi có nhiều tín hiệu rủi ro.
- Tài nguyên ít nhạy cảm có thể cho phép với giới hạn phù hợp.
- Không dựa duy nhất vào một flag do app client gửi.
- Không đưa thông tin chi tiết về detection rule vào response cho attacker.

## 9. MFA và risk-based authentication trên mobile

Mobile có thể dùng TOTP, push approval, SMS/voice OTP, passkey hoặc hardware security key. Mỗi yếu tố có khả năng chống phishing và rủi ro khác nhau.

### 9.1. Push MFA và number matching

Push notification tiện lợi nhưng có thể bị MFA fatigue: attacker liên tục gửi yêu cầu đăng nhập khiến user vô tình approve. Number matching hoặc hiển thị context như vị trí, thiết bị và ứng dụng giúp user đối chiếu request.

Tuy vậy:
- Không approve prompt không do mình khởi tạo.
- Không đọc mã number matching cho người gọi tự xưng support.
- Backend phải giới hạn tốc độ và phát hiện push spam.
- Push payload không chứa token hoặc dữ liệu nhạy cảm.
- App phải xác minh challenge và transaction trước khi approve.

### 9.2. OTP và SMS

OTP qua SMS chịu rủi ro SIM swap, SS7/interception, phishing relay và malware đọc SMS. TOTP giảm phụ thuộc nhà mạng nhưng vẫn có thể bị reverse proxy lấy mã theo thời gian thực. Không gọi OTP là phishing-resistant.

Với action nhạy cảm, ưu tiên passkey/FIDO2 hoặc phương thức proof-of-possession phù hợp. Nếu OTP là fallback, giới hạn rate, lifetime, attempts và binding với transaction.

### 9.3. Transaction confirmation

Với hành động có giá trị cao như chuyển tiền, đổi recovery hoặc cấp quyền admin, chỉ xác minh user đã đăng nhập có thể chưa đủ. Có thể cần confirmation gắn với nội dung giao dịch:
- Hiển thị người nhận, số tiền, resource hoặc thay đổi cụ thể.
- Server tạo challenge gắn với transaction ID và payload digest.
- Authenticator hoặc app ký/xác nhận challenge theo protocol.
- Server kiểm tra challenge dùng một lần và trạng thái transaction.
- Thay đổi payload sau khi xác nhận phải yêu cầu xác nhận mới.

Không hiển thị nội dung khác với dữ liệu server thực sự thực hiện; nếu user ký một chuỗi không ràng buộc với transaction, confirmation không bảo vệ được ý nghĩa giao dịch.

## 10. Token và session lifecycle trong mobile app

Sau OAuth/OIDC, app có thể nhận access token, refresh token và đôi khi ID Token. Mỗi loại có consumer, lifetime và cách lưu khác nhau.

### 10.1. Access token

Access token được gửi tới resource server có audience phù hợp. Thường nên có lifetime ngắn theo risk policy. App không nên gửi ID Token tới API thay cho access token và không tự sửa payload JWT.

Lưu access token trong memory nếu phù hợp; nếu phải persist, dùng secure storage và hạn chế thời gian tồn tại. Không log Authorization header hoặc token trong crash report.

### 10.2. Refresh token

Refresh token có thể cấp access token mới và vì vậy thường có giá trị cao hơn. Bảo vệ bằng:
- OS secure storage với access control phù hợp.
- Rotation và reuse detection khi authorization server hỗ trợ.
- Sender constraint như mTLS/DPoP nếu kiến trúc và platform phù hợp.
- Idle/absolute lifetime.
- Revoke khi logout, account disable hoặc compromise.
- Không backup/migrate ngoài policy.
- Không chia sẻ giữa app không cùng trust boundary.

Nếu app bị uninstall, server có thể không nhận được logout. Vì vậy refresh token cần expiry/revocation policy và session/device inventory phía server.

### 10.3. Token refresh và network race

Ứng dụng có thể có nhiều request đồng thời gặp 401 do access token hết hạn. Cần một refresh coordinator để tránh nhiều refresh song song:
1. Các request chờ một refresh operation dùng chung.
2. Client ghi nhận auth-state generation trước khi refresh.
3. Chỉ một refresh request sử dụng refresh token hiện tại.
4. Khi response về, kiểm tra generation và account state.
5. Lưu token mới atomically.
6. Retry request một lần nếu policy cho phép.
7. Nếu refresh bị reuse/revoked, xóa state và yêu cầu authentication lại.

Logout phải tăng generation hoặc hủy refresh transaction để response cũ không khôi phục session.

### 10.4. Account switch

Nếu app hỗ trợ nhiều account:
- Lưu token tách theo account/client/issuer.
- Không để refresh của account A ghi đè session B.
- Xóa dữ liệu nhạy cảm trong memory khi switch.
- Ràng buộc cache/resource với account và tenant.
- Có logout riêng cho account đang chọn và sign out all theo policy.
- Không dùng một global token slot nếu app hỗ trợ nhiều identity.

## 11. Certificate và mTLS trong mobile

Một số app enterprise, banking hoặc device-managed dùng client certificate để xác thực thiết bị hoặc ứng dụng với gateway/API.

### 11.1. Client certificate enrollment

Certificate có thể được provision qua MDM, SCEP/EST, private PKI hoặc enrollment flow có xác minh. Cần:
- Xác minh account/device enrollment.
- Tạo private key trong hardware-backed keystore nếu hỗ trợ.
- Gửi CSR hoặc proof of possession.
- Kiểm tra CA, SAN, EKU và policy.
- Lưu certificate reference và private key handle.
- Đặt lifetime, renewal và revocation.
- Không xuất private key ra file nếu không cần.

### 11.2. mTLS và TLS termination

Khi app kết nối trực tiếp API qua mTLS, server kiểm tra client certificate và mapping sang principal. Nếu TLS kết thúc tại gateway/load balancer, backend phải chỉ tin certificate metadata do gateway xác minh qua kênh nội bộ được bảo vệ. Không tin header certificate do client ngoài tự gửi.

### 11.3. Certificate pinning

Certificate/public key pinning có thể giới hạn CA/key mà app chấp nhận, nhưng tạo rủi ro outage khi certificate rotation hoặc CA thay đổi. Pinning không thay thế TLS validation chuẩn và không nên triển khai với một pin duy nhất không có backup/rotation plan.

Nếu dùng pinning:
- Có primary và backup pin theo quy trình.
- Có kế hoạch thay pin trước khi certificate đổi.
- Có telemetry và rollback an toàn.
- Không tắt hostname verification.
- Đánh giá tác động tới proxy enterprise, certificate renewal và incident response.

Không dùng custom trust-all certificate handler để “sửa lỗi SSL”.

## 12. Offline authentication và dữ liệu cục bộ

Một số app cần hoạt động khi mất mạng. Offline unlock có thể cho phép mở dữ liệu đã lưu cục bộ, nhưng không đồng nghĩa backend đã xác thực session hoặc quyền hiện tại.

### 12.1. Local unlock

Có thể dùng biometric/device credential để mở một key bảo vệ local database. Khi offline:
- Chỉ cho phép dữ liệu đã được cache và policy cho phép.
- Không tạo access token mới nếu không có authority hợp lệ.
- Không thực hiện action cần server-side authorization.
- Giới hạn thời gian offline và dữ liệu nhạy cảm.
- Kiểm tra trạng thái khi online trở lại.

Local biometric unlock chứng minh OS đã chấp nhận user verification cho key cục bộ theo policy; nó không chứng minh account chưa bị disable ở server.

### 12.2. Offline token và grace window

Nếu hệ thống cần offline access, xác định:
- Tài nguyên nào được phép truy cập.
- Token/cache tối đa bao lâu.
- Có thể biết revocation trong thời gian offline không.
- Hành động nào bị chặn.
- Dữ liệu local được mã hóa và xóa ra sao.
- Điều gì xảy ra khi thiết bị reconnect sau khi account bị revoke.

Không kéo dài credential hết hạn vô thời hạn vì thiết bị offline. Grace window phải được giới hạn và phê duyệt theo threat model.

## 13. App lifecycle, background và notification

Mobile OS có thể suspend app, kill process, giới hạn background execution hoặc trì hoãn notification. Không thiết kế authentication dựa trên giả định app luôn chạy.

### 13.1. Background refresh

Background task có thể thất bại vì mạng, battery policy hoặc OS scheduler. Refresh token không nên được gọi liên tục để giữ session sống. Tuân theo idle/absolute lifetime và refresh policy của authorization server.

### 13.2. Push notification

Push notification có thể báo có hoạt động hoặc yêu cầu user mở app. Không đưa access token, refresh token, OTP hoặc nội dung nhạy cảm vào payload notification. Push provider và lock-screen preview là các ranh giới dữ liệu khác.

Nếu dùng push approval:
- Payload chứa challenge/reference không phải bearer secret.
- App fetch transaction detail từ backend qua kênh xác thực.
- User xem đúng context trước khi approve.
- Server xác minh approval gắn với challenge và expiry.
- Chống replay và push fatigue.

### 13.3. App reinstall và device restore

App reinstall có thể làm mất local key hoặc secure storage item tùy platform/accessibility. Backend vẫn có thể giữ refresh token/device registration. Cần quy định:
- Credential nào bị revoke khi uninstall không thể phát hiện trực tiếp.
- Enrollment mới có cần step-up không.
- Device record cũ được dọn theo inactivity/expiry thế nào.
- Restore từ backup có được phép phục hồi credential không.
- User báo mất thiết bị có thể revoke device/session từ kênh khác ra sao.

## 14. Deep link và app-to-app authentication

Ứng dụng có thể mở app khác để xác thực, thanh toán hoặc xử lý callback. Đây là ranh giới tin cậy giữa các app.

Nguyên tắc:
- Dùng Universal Links/App Links hoặc redirect URI đã đăng ký.
- Validate scheme, host, path, state và transaction.
- Không truyền token hoặc secret trong deep link.
- Không tin extras/intent parameters như bằng chứng user identity.
- Kiểm tra caller/app identity khi platform cung cấp cơ chế đáng tin.
- Giới hạn exported activities/components.
- Không để một app khác gọi component nội bộ có quyền cao.
- Xử lý callback lặp, đến trễ hoặc ngoài transaction.

Nếu app nhận link chứa account ID hoặc action, server vẫn phải kiểm tra user có quyền trên account/resource. Deep link chỉ điều hướng tới app, không cấp quyền.

## 15. Privacy và dữ liệu mobile

Mobile app có thể thu thập device model, OS version, IP, locale, app version, device token và telemetry. Chỉ thu thập dữ liệu cần cho bảo mật, vận hành hoặc chức năng đã công bố.

Tránh:
- Dùng hardware identifier bền vững để theo dõi người dùng không cần thiết.
- Gửi biometric template về server.
- Ghi token, code, credential hoặc private key vào log.
- Đưa PII vào push payload.
- Dùng device fingerprint làm định danh duy nhất không thể thay đổi.
- Giữ device/location history vô thời hạn.

Device identifier có thể reset hoặc bị hạn chế bởi platform privacy. Ưu tiên app-scoped random identifier hoặc credential reference được quản lý, có mục đích và retention rõ.

## 16. Threat model cho mobile authentication

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Embedded WebView phishing** | App dựng trang login hoặc quan sát nội dung nhập. | Lộ password/MFA. | External user-agent/system browser và OIDC native flow. |
| **Authorization code interception** | App khác chiếm custom scheme callback. | Đổi code lấy token. | PKCE S256, state, redirect URI và one-time code. |
| **Callback injection** | Attacker gửi deep link tự tạo hoặc replay callback. | Login CSRF hoặc session substitution. | State/nonce, transaction TTL, callback validation và consume once. |
| **Token at rest theft** | Token lưu trong file/preferences/log/backup. | Account bị chiếm. | Keychain/Keystore, encryption và backup exclusion. |
| **Token leakage in logs** | Debug/crash/analytics ghi Authorization header. | Bearer credential bị lộ. | Redaction trước khi lưu và test logging. |
| **Refresh token replay** | Token bị copy và sử dụng từ thiết bị khác. | Attacker duy trì access. | Rotation, reuse detection, sender constraint và revoke. |
| **Deep link hijacking** | App khác đăng ký scheme hoặc nhận intent. | Callback/data bị chiếm hoặc giả mạo. | Claimed HTTPS links, PKCE và state. |
| **Root/jailbreak abuse** | Runtime bị instrument hoặc storage bị đọc. | Lộ key/token hoặc bypass client control. | Hardware-backed keys, server-side policy và risk signals. |
| **Biometric bypass** | App chỉ dựa vào boolean client hoặc fallback yếu. | Bỏ qua local user verification. | OS key access control và server verification khi cần. |
| **Device loss** | Thiết bị mất nhưng refresh token còn active. | Truy cập trái phép kéo dài. | Device/session inventory, revoke từ kênh khác, short lifetime. |
| **App attestation replay** | Verdict cũ hoặc challenge không ràng buộc request. | App giả mạo được chấp nhận. | Server-side verification, nonce/challenge và freshness. |
| **Push fatigue** | Attacker gửi nhiều push login request. | User approve nhầm. | Rate limit, number matching, context và phishing-resistant MFA. |
| **Offline stale access** | App tiếp tục dùng cache sau account revoke. | Dữ liệu/quyền cũ còn truy cập. | Offline window, data minimization và revalidation khi online. |
| **Certificate pinning outage** | Pin không được cập nhật khi certificate/CA đổi. | App mất kết nối dịch vụ. | Backup pin, rotation plan và rollback. |

## 17. Kiến trúc và pseudocode mobile login

Một mobile login flow có thể tách rõ phần điều phối trong app với phần xác minh ở authorization server.

    beginLogin():
        transaction.state = secureRandom()
        transaction.nonce = secureRandom()
        transaction.verifier = secureRandomHighEntropy()
        transaction.challenge = BASE64URL(SHA256(transaction.verifier))
        transaction.createdAt = nowUtc()
        savePendingTransactionSecurely(transaction)

        authorizationUrl = buildAuthorizationRequest(
            trustedIssuer = configuredIssuer,
            clientId = publicClientId,
            redirectUri = registeredRedirectUri,
            responseType = "code",
            codeChallenge = transaction.challenge,
            codeChallengeMethod = "S256",
            state = transaction.state,
            nonce = transaction.nonce
        )

        openSystemBrowser(authorizationUrl)

    handleCallback(callbackUrl):
        callback = parseWithPlatformUrlParser(callbackUrl)
        require callback.matchesRegisteredRedirect()
        transaction = loadPendingTransaction(callback.state)
        require transaction exists and not expired
        require not transaction.consumed

        if callback contains authorizationError:
            consumeTransaction(transaction)
            showSafeLoginError()
            return

        require callback contains authorizationCode
        markTransactionConsuming(transaction)

        tokenResponse = exchangeCodeAtConfiguredTokenEndpoint(
            code = callback.authorizationCode,
            verifier = transaction.verifier,
            redirectUri = registeredRedirectUri,
            clientId = publicClientId
        )

        verifyIssuerAudienceNonceAndTokenProfile(tokenResponse, transaction)
        storeTokensInOSSecureStorage(tokenResponse)
        consumeTransaction(transaction)
        clearTemporaryVerifier(transaction)

Pseudocode minh họa, không phải implementation copy-paste. Thư viện OIDC native đã được kiểm chứng nên xử lý protocol, discovery, PKCE, callback và token validation. Không tự xây URL hoặc parser JWT sơ sài; không ghi transaction secret vào log.

### 17.1. Những điều backend vẫn phải xác minh

API không tin rằng request an toàn chỉ vì nó đến từ app mobile:
- Validate access token như resource server.
- Kiểm tra issuer, audience, expiry, token type và scope.
- Xác minh sender constraint/device proof nếu policy yêu cầu.
- Kiểm tra account, tenant, resource ownership và authorization.
- Áp dụng rate limit và abuse detection.
- Kiểm tra attestation server-side nếu dùng.
- Hỗ trợ revoke token/session/device.
- Không tin user ID, role hoặc device trust boolean do app gửi.

## 18. Kiểm thử mobile authentication

Kiểm thử phải bao gồm platform behavior, protocol, secure storage, callback và server policy. Không chỉ kiểm thử happy path trên một thiết bị.

| Test case | Kết quả mong đợi |
| --- | --- |
| Authorization Code + PKCE S256 thành công | Code được đổi chỉ với verifier của transaction. |
| Intercept authorization code từ custom scheme | App khác không thể đổi code nếu thiếu verifier. |
| Callback state không khớp | Từ chối và không tạo session. |
| Callback bị replay hoặc đến sau TTL | Từ chối transaction đã consume/hết hạn. |
| Redirect URI sai host/path | Không xử lý callback như login hợp lệ. |
| Login qua embedded WebView | Luồng không dùng WebView tự quản để thu credential. |
| Token lưu trong plaintext preferences/file | Security test phát hiện và yêu cầu sửa. |
| Token xuất hiện trong log/crash report | Redaction test phải thất bại nếu secret bị ghi. |
| Thiết bị không hỗ trợ hardware-backed key | Áp dụng fallback policy đã phê duyệt. |
| Biometric enrollment thay đổi | Key invalidation được xử lý và yêu cầu re-auth/re-enroll. |
| App bị reinstall hoặc restore backup | Credential không được phục hồi ngoài policy. |
| Refresh response đến sau logout | Không khôi phục auth state đã kết thúc. |
| Device bị báo mất | Backend revoke session/refresh token/device binding theo policy. |
| Attestation nonce sai hoặc cũ | Backend từ chối verdict replay/stale. |
| Root/jailbreak signal | Risk policy xử lý nhất quán, không chỉ tin boolean client. |
| Push approval không có user intent | User có thể từ chối; server rate limit và audit. |
| Deep link từ app khác | State/PKCE/callback validation ngăn giả mạo transaction. |
| Offline cache sau account disable | Hành động server-side bị chặn; offline access theo giới hạn đã định. |
| Certificate hết hạn hoặc pin mismatch | Kết nối bị từ chối theo policy và có runbook phục hồi. |
| Multi-account switch | Token, cache và data được cô lập giữa các account. |

Kiểm thử trên các phiên bản OS/browser mục tiêu, thiết bị thật và môi trường có backup/restore. Mô phỏng mạng chập chờn, process bị kill, app background và callback tới trễ.

## 19. Tình huống thực hành: mất điện thoại có refresh token

**Bối cảnh:** Nhân viên An dùng app mobile để truy cập cổng nội bộ. App đăng nhập qua OIDC, lưu refresh token trong vùng secure storage và dùng biometric để mở khóa thao tác refresh. Điện thoại bị thất lạc khi đang mở khóa. Người nhặt được thiết bị có thể tiếp tục sử dụng app.

**Phân tích:**

1. Biometric prompt có thể làm tăng bảo vệ nhưng không bảo đảm thiết bị luôn khóa trước khi người khác cầm được.
2. Refresh token có thể còn active dù người dùng không còn kiểm soát thiết bị.
3. App uninstall hoặc tắt máy không đảm bảo server nhận logout.
4. Nếu backend chỉ chờ token hết hạn, attacker có thể duy trì access qua refresh.
5. Device ID đơn thuần không đủ để revoke đúng credential.

**Phản ứng và thiết kế:**

- An dùng một thiết bị/kênh đã xác minh khác để mở trang quản lý session hoặc liên hệ helpdesk theo recovery policy.
- Server revoke refresh token family, application session và device binding của thiết bị mất.
- Access token đã phát hành được xử lý theo lifetime, introspection hoặc state check của resource server.
- Kiểm tra login history, token exchange, account modification và authenticator enrollment sau thời điểm mất.
- Nếu nghi credential hoặc private key bị lộ, rotate/revoke theo phạm vi; không chỉ xóa device record.
- Thiết bị mới thực hiện authentication và enrollment lại; tạo key pair mới trong secure hardware nếu có.
- Notification gửi qua kênh độc lập đã xác minh và audit giữ reference, không ghi token.

**Bài tập:** Nếu người dùng chỉ đổi password thì refresh token cũ có chắc chắn bị vô hiệu không? Không mặc nhiên. Authorization server cần policy rõ về token/session revocation khi password reset hoặc account compromise; backend phải thực thi revoke và kiểm tra trạng thái.

## 20. Checklist thiết kế mobile authentication

- [ ] Phân biệt user identity, public client identity và device/workload identity.
- [ ] Xây threat model cho app, OS, browser, storage, deep link, network, backup và backend.
- [ ] Dùng OAuth Authorization Code Flow với PKCE S256 cho native public client.
- [ ] Mở đăng nhập liên kết trong system browser/external user-agent; tránh embedded WebView.
- [ ] Dùng state, nonce và code_verifier ngẫu nhiên, TTL ngắn và consume một lần.
- [ ] Đăng ký redirect URI chính xác; ưu tiên Universal Links/App Links khi phù hợp.
- [ ] Không truyền access/refresh token hoặc secret trong URL/deep link.
- [ ] Không nhúng client secret cố định trong mobile binary.
- [ ] Lưu refresh token/key reference trong Keychain/Keystore với access control phù hợp.
- [ ] Dùng hardware-backed key khi hỗ trợ và threat model yêu cầu; hiểu fallback.
- [ ] Loại credential nhạy cảm khỏi backup, log, crash report, clipboard và notification.
- [ ] Phân biệt local biometric verification với server-side authentication; không gửi biometric template.
- [ ] Ràng buộc biometric với key access control thay vì boolean client.
- [ ] Quản lý passkey qua WebAuthn ceremony và server-side challenge verification.
- [ ] Dùng attestation/device integrity như risk signal; verify server-side, challenge-bound và fresh.
- [ ] Không dùng device ID, IP hoặc root flag làm bằng chứng danh tính duy nhất.
- [ ] Quản lý access/refresh token lifetime, rotation, reuse detection và revocation.
- [ ] Xử lý refresh/logout race, background task, process kill và multi-account isolation.
- [ ] Cung cấp session/device inventory và quy trình revoke khi mất thiết bị.
- [ ] Dùng mTLS/client certificate chỉ khi có PKI lifecycle, trust mapping và rotation rõ.
- [ ] Không tắt TLS/hostname validation; nếu pinning, có backup pin và rotation plan.
- [ ] Thiết kế offline access có giới hạn; local unlock không đồng nghĩa server authorization.
- [ ] Không đưa token hoặc dữ liệu nhạy cảm vào push payload.
- [ ] Kiểm tra deep link, exported component, intent và app-to-app trust.
- [ ] Backend luôn validate token và authorization; không tin UI hoặc client-supplied role.
- [ ] Kiểm thử callback injection, PKCE interception, token theft, attestation replay, device loss và offline stale access.

## 21. Câu hỏi tự kiểm tra

**1. Mobile authentication là gì?**  
Là quá trình user, app client hoặc device chứng minh danh tính/quyền kiểm soát credential để truy cập dịch vụ qua môi trường mobile.

**2. Vì sao native app thường là public client?**  
Vì binary được phân phối tới thiết bị người dùng và secret nhúng trong đó có thể bị trích xuất; client ID không phải secret.

**3. Vì sao dùng Authorization Code Flow với PKCE?**  
PKCE ràng buộc authorization code với verifier của transaction, giảm nguy cơ app khác chặn code rồi đổi lấy token.

**4. Vì sao nên dùng system browser thay WebView tự quản?**  
System browser giữ xác thực tại origin của IdP, hỗ trợ SSO/password manager/passkey và giảm khả năng app quan sát credential.

**5. State, nonce và PKCE verifier có vai trò gì?**  
State liên kết callback với request; nonce liên kết ID Token với authentication transaction; verifier chứng minh app giữ secret tương ứng với challenge.

**6. Keychain/Keystore bảo vệ điều gì?**  
Chúng cung cấp cơ chế lưu và sử dụng secret/key do OS quản lý, có thể hỗ trợ hardware-backed protection và user authentication policy; mức bảo vệ phụ thuộc cấu hình và thiết bị.

**7. Biometric trên mobile có gửi fingerprint/face lên server không?**  
Thông thường không. OS xác minh cục bộ và có thể mở quyền sử dụng key; backend nhận proof/token theo flow riêng nếu được thiết kế.

**8. App attestation có chứng minh user là chủ account không?**  
Không. Nó cung cấp tín hiệu về app/device integrity theo platform; user authentication và authorization vẫn phải được kiểm tra riêng.

**9. Nếu điện thoại mất, chỉ đổi password có đủ không?**  
Không chắc. Cần revoke refresh token/session/device binding, kiểm tra hoạt động sau sự cố và xử lý access token đã phát hành theo policy.

**10. Local biometric unlock có chứng minh account vẫn active trên server không?**  
Không. Nó chỉ xác minh local user presence theo OS policy; backend vẫn phải kiểm tra token, account status và authorization.

**Ghi nhớ:** Mobile authentication phải bảo vệ cả user, app và device trong một môi trường không thể coi là hoàn toàn tin cậy. Dùng system browser và Authorization Code + PKCE, callback có state/nonce, secure storage của OS, passkey hoặc authenticator phù hợp, token lifecycle có revoke và device recovery rõ ràng. Biometric và attestation là tín hiệu/kiểm soát theo phạm vi của chúng; backend vẫn là nơi xác minh token và quyết định quyền truy cập cuối cùng.
