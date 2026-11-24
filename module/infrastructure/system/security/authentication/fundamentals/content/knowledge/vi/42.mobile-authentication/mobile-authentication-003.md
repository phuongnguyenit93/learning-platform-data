# Secure storage — Bảo vệ credential và dữ liệu nhạy cảm trên thiết bị di động

> **Chương:** Authentication trong mobile  
> **Chủ đề:** Secure storage  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách ứng dụng di động lưu trữ credential, token, khóa mật mã và dữ liệu nhạy cảm bằng cơ chế bảo vệ của hệ điều hành; đồng thời xử lý backup, khôi phục thiết bị, sinh trắc học, vòng đời khóa, logout và giới hạn của thiết bị đã root/jailbreak.

## 1. Secure storage là gì?

**Secure storage** là cách lưu credential và dữ liệu nhạy cảm sao cho chỉ thành phần, người dùng và trạng thái thiết bị được phép mới có thể truy cập. Trên mobile, ứng dụng nên tận dụng kho khóa và cơ chế kiểm soát truy cập do hệ điều hành cung cấp, thay vì tự tạo một file chứa secret rồi chỉ dựa vào việc làm khó đọc file đó.

Ví dụ, ứng dụng ngân hàng nhận access token và refresh token sau khi người dùng đăng nhập. Access token có thời hạn ngắn có thể giữ trong bộ nhớ khi cần. Refresh token cần lưu bền vững hơn để duy trì phiên, nên được đặt trong Keychain trên iOS hoặc được mã hóa bằng khóa do Android Keystore quản lý. Khi người dùng logout, ứng dụng xóa credential cục bộ và backend thu hồi refresh token/session theo policy.

Secure storage không chỉ là “mã hóa file”. Một thiết kế tốt phải trả lời:
- Dữ liệu nào thực sự cần lưu trên thiết bị?
- Ai hoặc tiến trình nào có thể đọc dữ liệu?
- Khóa mã hóa được tạo, bảo vệ và sử dụng ở đâu?
- Dữ liệu có được backup hoặc chuyển sang thiết bị khác không?
- Điều gì xảy ra khi thiết bị khóa, mất, root/jailbreak hoặc bị thu hồi?
- Làm sao phát hiện và xử lý credential cũ, key invalidation và logout?

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân loại credential, token, private key và dữ liệu nhạy cảm cần lưu trên mobile.
2. Phân biệt Keychain, Secure Enclave, Android Keystore, TEE và StrongBox.
3. Chọn chính sách accessibility và access control phù hợp với luồng sử dụng.
4. Mã hóa dữ liệu lớn bằng AEAD và bảo vệ khóa mã hóa riêng biệt.
5. Ràng buộc thao tác nhạy cảm với biometric hoặc device passcode khi phù hợp.
6. Xử lý backup, restore, migration, reinstall, logout và key invalidation.
7. Giảm rủi ro từ logs, cache, clipboard, screenshots và bộ nhớ tiến trình.
8. Hiểu giới hạn của root/jailbreak detection và device attestation.
9. Thiết kế key rotation, token revocation và recovery an toàn.
10. Xây dựng kiểm thử cho secure storage trên thiết bị và phiên bản OS mục tiêu.

## 2. Threat model cho dữ liệu trên mobile

Thiết bị di động có thể bị mất, cho mượn, sửa đổi, root/jailbreak hoặc chạy ứng dụng khác có quyền cao. Kẻ tấn công có thể:
- lấy thiết bị đã mở khóa;
- khai thác lỗ hổng OS hoặc ứng dụng;
- đọc backup, file cache hoặc log;
- lấy dữ liệu từ thiết bị đã root/jailbreak;
- phân tích binary để tìm hardcoded secret;
- hook API hoặc đọc memory khi ứng dụng đang chạy;
- phục hồi dữ liệu cũ từ backup;
- lấy token từ crash report, clipboard hoặc telemetry;
- đánh cắp thiết bị rồi cố tiếp tục sử dụng session cũ.

Threat model cần xác định tài sản và đối thủ:
- **Tài sản:** refresh token, access token, private key, client certificate, recovery secret, dữ liệu cá nhân và khóa mã hóa database.
- **Đối thủ:** người nhặt được thiết bị, malware, attacker có quyền root/jailbreak, insider, hoặc người có quyền truy cập backup.
- **Trust boundary:** OS secure storage, app sandbox, backend, MDM, IdP, cloud backup và thiết bị khác.
- **Hậu quả:** account takeover, giả mạo API request, lộ dữ liệu, replay, hoặc mất khả năng thu hồi phiên.

Không có một API lưu trữ nào bảo vệ ứng dụng khỏi mọi trường hợp thiết bị đã bị kiểm soát. Secure storage làm tăng chi phí tấn công và giới hạn truy cập; backend vẫn phải có expiry, revocation, authorization và phát hiện bất thường.

## 3. Phân loại dữ liệu trước khi lưu

Không phải dữ liệu nào cũng cần lưu bền vững hoặc cùng mức bảo vệ.

| Loại dữ liệu | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Password người dùng | Mật khẩu đăng nhập | Không lưu lại; gửi qua TLS để server xác minh |
| Access token | Token gọi API có thời hạn ngắn | Ưu tiên memory; chỉ persist khi có nhu cầu rõ |
| Refresh token | Token lấy access token mới | Keychain/Keystore-backed secure storage; rotation và revoke |
| Private key | Khóa ký request hoặc client authentication | Tạo và giữ trong Keychain/Secure Enclave hoặc Android Keystore khi phù hợp |
| Client certificate | Certificate và private key tương ứng | Certificate có thể lưu công khai; private key được bảo vệ bởi OS key store |
| Encryption key | Khóa mã hóa database/file | OS key store/KMS; không lưu cùng ciphertext ở dạng plaintext |
| Biometric data | Vân tay/khuôn mặt | Không thu thập hoặc lưu biometric template; dùng API hệ điều hành |
| Profile/cache | Tên, ảnh, nội dung đã tải | Giảm thiểu, phân loại, mã hóa nếu nhạy cảm và đặt retention |
| Recovery code | Mã khôi phục account | Tránh lưu nếu không cần; nếu lưu phải bảo vệ như credential mạnh |

**Nguyên tắc đầu tiên là giảm dữ liệu:** nếu không cần lưu credential thì đừng lưu. Không lưu password người dùng để tự động đăng nhập; dùng flow token/session được thiết kế cho mobile.

## 4. Secure storage không đồng nghĩa với mã hóa mọi thứ

Một ứng dụng có thể mã hóa file nhưng vẫn không an toàn nếu:
- khóa mã hóa được hardcode trong binary;
- khóa được tạo từ device ID, username hoặc một chuỗi cố định;
- key và ciphertext được lưu cùng nơi mà attacker đọc được;
- ứng dụng giải mã dữ liệu quá sớm và giữ plaintext lâu trong memory;
- token bị ghi vào log hoặc crash report;
- app không revoke token khi thiết bị mất;
- backup khôi phục ciphertext nhưng không có khóa tương ứng.

Mã hóa chỉ hữu ích khi key lifecycle và access control được thiết kế đúng. Dữ liệu bí mật cần được bảo vệ cả lúc lưu, lúc sử dụng và khi truyền.

## 5. iOS Keychain

**Keychain Services** là cơ chế hệ điều hành để lưu các item nhạy cảm như password, token, key và certificate. Keychain quản lý quyền truy cập, accessibility và một số điều kiện yêu cầu xác thực người dùng.

Các loại item thường gặp:
- generic password: secret/token dạng dữ liệu;
- internet password: credential liên quan dịch vụ internet;
- key: khóa mật mã;
- certificate và identity: certificate cùng private key tương ứng.

Keychain phù hợp với secret nhỏ và credential cần truy cập qua API bảo mật của hệ điều hành. Không dùng UserDefaults hoặc file plist như kho credential.

### Keychain accessibility

Accessibility class xác định khi nào item có thể được truy cập, ví dụ:
- **WhenUnlocked:** chỉ truy cập khi thiết bị đang mở khóa;
- **AfterFirstUnlock:** có thể truy cập sau lần mở khóa đầu tiên kể từ khi khởi động, phù hợp một số tác vụ nền;
- **WhenPasscodeSetThisDeviceOnly:** yêu cầu passcode trên thiết bị và không migrate item sang thiết bị khác;
- các biến thể **ThisDeviceOnly:** hạn chế item được migrate qua backup/restore sang thiết bị khác.

Chọn mức chặt nhất mà chức năng vẫn hoạt động. Với refresh token cần dùng khi app foreground, item chỉ truy cập khi thiết bị mở khóa thường là lựa chọn phù hợp. Tác vụ nền cần quyền truy cập sau first unlock phải có threat model và scope rõ ràng.

Không chọn AfterFirstUnlock chỉ để né lỗi khi thiết bị đang khóa. Chính sách accessibility ảnh hưởng trực tiếp đến thời điểm secret có thể được sử dụng.

## 6. Keychain access control và sinh trắc học trên iOS

Keychain item có thể gắn với access control policy thông qua SecAccessControl. Tùy yêu cầu, policy có thể đòi:
- người dùng hiện diện;
- device passcode;
- biometric;
- biometric thuộc tập hiện tại đã đăng ký;
- điều kiện kết hợp theo khả năng OS.

Ví dụ, item yêu cầu biometric current set có thể không còn truy cập được khi người dùng thay đổi tập biometric đã đăng ký. Đây là hành vi bảo mật cần được xử lý như key/item invalidation, không phải lỗi ngẫu nhiên.

Cần cân nhắc:
- biometric có fallback bằng device passcode hay không;
- hành động nào cần xác thực lại;
- item có được dùng trong background không;
- app xử lý khi biometric enrollment thay đổi ra sao;
- người dùng không có biometric thì flow thay thế là gì.

Ứng dụng không nhận template vân tay hoặc khuôn mặt từ Keychain. Hệ điều hành thực hiện kiểm tra và cho phép hoặc từ chối thao tác theo policy. Không tự lưu ảnh vân tay, khuôn mặt hoặc dữ liệu sinh trắc học.

## 7. Secure Enclave trên iOS

**Secure Enclave** là phần cứng bảo mật trong thiết bị Apple hỗ trợ một số thao tác khóa mật mã và bảo vệ private key. Với API phù hợp, ứng dụng có thể tạo private key được bảo vệ bởi Secure Enclave để ký hoặc thực hiện thao tác mật mã mà private key không cần được export ra app memory.

Secure Enclave phù hợp khi:
- cần private key cho ký challenge hoặc request;
- muốn gắn thao tác sử dụng key với user presence/biometric/passcode;
- cần giảm khả năng trích xuất private key;
- server có thể xác minh public key đã đăng ký.

Secure Enclave không phải nơi lưu mọi loại dữ liệu tùy ý. Không thể coi nó như một ổ đĩa mã hóa để đặt refresh token hoặc database. Với secret dạng bytes, dùng Keychain; với dữ liệu lớn, dùng encryption key được bảo vệ bởi OS key store.

Không phải mọi thiết bị hoặc mọi thuật toán đều hỗ trợ cùng khả năng Secure Enclave. Ứng dụng cần kiểm tra khả năng, có fallback phù hợp và không giả định mọi private key đều hardware-backed.

## 8. Android Keystore

**Android Keystore** cho phép ứng dụng tạo và sử dụng key thông qua hệ thống keystore. Key material có thể được giữ trong môi trường bảo vệ phần cứng như TEE hoặc StrongBox nếu thiết bị hỗ trợ và cấu hình phù hợp.

Ứng dụng thường dùng Keystore để:
- tạo AES key mã hóa dữ liệu cục bộ;
- tạo key pair để ký hoặc xác minh;
- yêu cầu user authentication trước khi dùng key;
- giới hạn mục đích, thuật toán, block mode và padding;
- kiểm tra thông tin key security level trên phiên bản Android phù hợp.

Android Keystore không phải nơi lưu trữ tùy ý mọi secret. Key material được hệ thống quản lý; ứng dụng gọi API để thực hiện crypto operation. Nếu cần lưu token hoặc dữ liệu, ứng dụng mã hóa bằng key Keystore rồi lưu ciphertext ở vùng app-private.

### TEE và StrongBox

- **TEE (Trusted Execution Environment):** môi trường thực thi được cách ly tương đối với Android userspace.
- **StrongBox:** phần cứng bảo mật chuyên dụng trên một số thiết bị, cung cấp mức cô lập cao hơn cho một số thao tác key.
- **Software-backed Keystore:** có thể tồn tại khi thiết bị không hỗ trợ phần cứng tương ứng.

Không giả định mọi thiết bị Android đều có StrongBox. Nếu policy yêu cầu hardware-backed key, ứng dụng cần kiểm tra security level hoặc dùng attestation theo threat model; nếu không đạt, từ chối hoặc áp dụng degraded policy được phê duyệt.

## 9. Tạo khóa AES trong Android Keystore

Ví dụ Kotlin minh họa tạo AES-GCM key trong Android Keystore. Key alias là tên tham chiếu, không phải key material:

~~~kotlin
val alias = "session-data-v1"

val keyStore = KeyStore.getInstance("AndroidKeyStore").apply {
    load(null)
}

if (!keyStore.containsAlias(alias)) {
    val generator = KeyGenerator.getInstance(
        KeyProperties.KEY_ALGORITHM_AES,
        "AndroidKeyStore"
    )

    val spec = KeyGenParameterSpec.Builder(
        alias,
        KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
    )
        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
        .setRandomizedEncryptionRequired(true)
        .build()

    generator.init(spec)
    generator.generateKey()
}
~~~

Ví dụ này tạo key có thể dùng cho AES-GCM. Trong production:
- kiểm tra key đã tồn tại và algorithm/parameters phù hợp;
- không export key material;
- quản lý alias theo version và purpose;
- xử lý key invalidation và lỗi keystore;
- không dùng cùng key cho nhiều mục đích không liên quan;
- kiểm thử trên nhiều OEM/Android version.

## 10. Mã hóa dữ liệu bằng AEAD

Với dữ liệu cục bộ lớn hơn một item nhỏ, có thể mã hóa bằng **AEAD (Authenticated Encryption with Associated Data)** như AES-GCM. AEAD cung cấp confidentiality và integrity/authentication tag cho ciphertext.

Một bản ghi có thể lưu:
- version của format;
- key alias/version;
- nonce/IV;
- ciphertext;
- authentication tag (thường được đóng gói trong output của thư viện).

Ví dụ Kotlin:

~~~kotlin
val cipher = Cipher.getInstance("AES/GCM/NoPadding")
cipher.init(Cipher.ENCRYPT_MODE, key)

val aad = "account:acct-42|purpose:refresh-token|v:1"
    .toByteArray(Charsets.UTF_8)
cipher.updateAAD(aad)

val ciphertextAndTag = cipher.doFinal(secretBytes)
val iv = cipher.iv

// Persist version + IV + ciphertextAndTag in app-private storage.
// The AES key remains in Android Keystore.
~~~

Khi giải mã, dùng đúng key, IV và AAD. Nếu AAD hoặc ciphertext bị thay đổi, AEAD verification phải thất bại.

### Quy tắc quan trọng với AES-GCM

- Không tái sử dụng nonce/IV với cùng key.
- Dùng IV ngẫu nhiên theo API crypto chuẩn; không tự đặt IV cố định.
- Lưu IV cùng ciphertext vì IV không cần bí mật.
- Không bỏ qua authentication tag hoặc chấp nhận plaintext khi tag sai.
- Giới hạn kích thước dữ liệu và số lần dùng key theo hướng dẫn thuật toán.
- AAD có thể ràng buộc ciphertext với account, purpose, tenant hoặc version.
- Khi đổi format/key version, có migration path rõ ràng.

Không dùng AES-CBC hoặc XOR tự chế để thay AEAD. Nếu phải hỗ trợ legacy encryption, cần protocol riêng và kiểm tra integrity độc lập.

## 11. Lưu secret nhỏ và dữ liệu lớn

Không phải mọi dữ liệu đều nên đi qua cùng một cơ chế.

| Nhu cầu | iOS | Android |
| --- | --- | --- |
| Refresh token/secret nhỏ | Keychain | Mã hóa bằng Android Keystore rồi lưu app-private |
| Private key ký | Keychain/Secure Enclave khi hỗ trợ | Android Keystore/TEE/StrongBox khi hỗ trợ |
| Certificate public | Keychain hoặc bundle/config phù hợp | App-private storage hoặc certificate store phù hợp |
| Database nhạy cảm | File protection + database encryption/key trong Keychain | Database encryption/key trong Keystore |
| Cache không nhạy cảm | App container với retention | App-private storage với retention |
| Password người dùng | Không lưu | Không lưu |

Key store bảo vệ key và access policy; nó không tự động mã hóa mọi file của ứng dụng. Ứng dụng phải thiết kế rõ cách ciphertext được lưu và key được dùng.

## 12. Những nơi không nên lưu credential

Tránh lưu refresh token, client secret hoặc private key trong:
- UserDefaults hoặc SharedPreferences dưới dạng plaintext;
- file JSON/plist trong app container không mã hóa;
- SQLite database không có encryption phù hợp;
- cache directory;
- temporary file;
- clipboard;
- notification payload;
- analytics event;
- crash report;
- URL query string;
- source code, build config hoặc container/app bundle;
- logcat, NSLog, print hoặc debug console.

App sandbox giúp cô lập dữ liệu ứng dụng trong điều kiện OS hoạt động bình thường. Nó không thay thế secure key storage và không bảo vệ khỏi mọi malware/rooted device.

## 13. Refresh token, access token và session trên mobile

Mobile app thường dùng OAuth/OIDC Authorization Code Flow với PKCE qua system browser hoặc browser tab được nền tảng hỗ trợ. Native app là public client; không nhúng client secret cố định vào binary vì attacker có thể trích xuất.

Khuyến nghị:
- Access Token ngắn hạn, giữ trong memory nếu có thể.
- Refresh Token được lưu trong secure storage.
- Dùng refresh token rotation và reuse detection nếu AS hỗ trợ.
- Ràng buộc token với client/device theo khả năng và policy.
- Không dùng ID Token làm bearer token gọi API.
- Không lưu token trong URL hoặc log.
- Khi logout, xóa token cục bộ và gọi revoke/logout endpoint.
- Khi account bị disable hoặc thiết bị mất, backend phải revoke session/token.

Lưu refresh token trong Keychain/Keystore không làm nó hết hạn hoặc tự revoke. Nếu attacker có thể sử dụng app/process đã mở khóa, họ có thể yêu cầu hệ điều hành giải mã hoặc dùng token. Server-side expiry, revocation và risk controls vẫn cần thiết.

## 14. Biometric và device passcode

Sinh trắc học có thể yêu cầu người dùng hiện diện trước khi mở khóa key hoặc thực hiện thao tác nhạy cảm. Nó không phải một loại secret mà ứng dụng nên tự thu thập.

### iOS

Ứng dụng có thể dùng LocalAuthentication và Keychain access control để yêu cầu biometric hoặc device passcode. Policy như biometric-current-set có thể làm item/key không còn dùng được khi biometric enrollment thay đổi.

### Android

Ứng dụng có thể dùng BiometricPrompt và liên kết prompt với CryptoObject. Keystore key có thể được cấu hình yêu cầu user authentication trước khi sử dụng; thời hạn xác thực và loại authenticator cần được chọn theo API level và policy.

### UX và fallback

- Có phương án device passcode hoặc recovery khi biometric không khả dụng.
- Không tự động hạ xuống password yếu hơn mà không có policy.
- Phân biệt biometric enrollment changed với credential bị server revoke.
- Yêu cầu xác thực lại cho hành động nhạy cảm thay vì mỗi lần mở app nếu phù hợp.
- Không lưu kết quả biometric thành cờ vĩnh viễn trong preferences.

Một biến boolean như biometricPassed=true do client lưu có thể bị sửa hoặc trở nên stale. Server không nên tin cờ đó như bằng chứng độc lập; nếu cần assurance, dùng cryptographic proof và protocol được thiết kế cho mục đích đó.

## 15. Backup, restore và migration thiết bị

Backup có thể sao chép ciphertext sang thiết bị mới trong khi key cũ không được migrate. Khi đó dữ liệu không thể giải mã. Ngược lại, nếu backup cả plaintext token hoặc key material, attacker có thể lấy credential từ backup.

Nguyên tắc:
- không backup access/refresh token và private key nếu không có thiết kế đồng bộ credential rõ;
- trên iOS, cân nhắc Keychain accessibility class có hậu tố ThisDeviceOnly cho credential gắn với thiết bị;
- cấu hình file protection và loại trừ file nhạy cảm khỏi backup khi phù hợp;
- trên Android, cấu hình Auto Backup/Data Extraction Rules để loại trừ secret/ciphertext không thể restore an toàn;
- sau restore, nếu key không còn hoặc bị invalidated, yêu cầu xác thực lại/enrollment lại;
- không cố tạo key mới rồi giải mã ciphertext cũ bằng key mới;
- kiểm thử migration từ OS/device version cũ sang mới.

Nếu sản phẩm cần đồng bộ credential giữa thiết bị, dùng cơ chế platform-supported sync hoặc account-based re-enrollment có xác minh; không tự copy private key/token qua cloud backup không được bảo vệ.

## 16. Reinstall và vòng đời ứng dụng

Hành vi key/Keychain sau uninstall và reinstall có thể khác nhau giữa nền tảng, API, cấu hình và phiên bản OS. Không xây security guarantee dựa trên giả định “uninstall chắc chắn xóa mọi credential”.

Ứng dụng cần:
- xử lý trường hợp Keychain item còn tồn tại sau reinstall;
- có installation marker hoặc account binding phù hợp nếu cần phân biệt lần cài mới;
- kiểm tra server-side session/token status khi khởi động;
- revoke refresh token khi logout hoặc account closure;
- không coi reinstall là logout;
- xóa local data và key theo policy khi user chủ động logout;
- có flow recovery nếu key bị xóa hoặc invalidated.

Uninstall không thể thay thế logout server-side. Nếu thiết bị mất hoặc app bị xóa mà token còn active, backend vẫn cần cơ chế thu hồi.

## 17. Key invalidation và credential recovery

Key có thể không còn dùng được khi:
- người dùng thay đổi biometric enrollment;
- thiết bị reset hoặc restore;
- passcode bị thay đổi theo policy key;
- key bị xóa hoặc Keystore/Keychain gặp lỗi;
- OS migration làm thay đổi điều kiện bảo vệ;
- key hết hạn hoặc bị revoke;
- app update thay đổi key alias/format không tương thích.

Khi key invalidated:
1. Không fallback sang hardcoded key hoặc plaintext.
2. Xóa ciphertext không còn giải mã được theo policy.
3. Xác định account/session nào bị ảnh hưởng.
4. Yêu cầu người dùng xác thực lại qua flow server.
5. Revoke credential/token cũ nếu có dấu hiệu compromise.
6. Tạo key mới và lưu dữ liệu mới.
7. Ghi audit reason code mà không ghi secret.

Không tự động coi key invalidation là compromise; nhưng cần xử lý fail-closed cho dữ liệu và yêu cầu reauthentication phù hợp.

## 18. Root/jailbreak và giới hạn của secure storage

Root/jailbreak có thể cho attacker quyền đọc app container, hook API, inspect memory hoặc thay đổi runtime. Hardware-backed key có thể vẫn không export được, nhưng attacker có thể điều khiển ứng dụng hợp lệ để yêu cầu key thực hiện decrypt/sign.

Vì vậy:
- secure storage không bảo vệ tuyệt đối khi runtime bị kiểm soát;
- root/jailbreak detection có thể bị bypass;
- không chỉ dựa vào một dấu hiệu filesystem hoặc package;
- có thể dùng device/app attestation như risk signal;
- backend cần đánh giá context và có thể giới hạn thao tác nhạy cảm;
- token nên ngắn hạn, có revoke và rotation;
- hạn chế dữ liệu nhạy cảm giữ trên thiết bị;
- với threat model cao, yêu cầu managed device hoặc hardware-backed key proof.

Không tuyên bố ứng dụng “root-proof”. Hãy mô tả chính xác threat model và phản ứng khi phát hiện thiết bị có rủi ro.

## 19. Device attestation không phải secure storage

Device attestation giúp server đánh giá ứng dụng hoặc thiết bị có đáp ứng một số thuộc tính integrity hay không. Ví dụ, Android có Play Integrity API; hệ sinh thái Apple có App Attest/DeviceCheck theo mục đích và khả năng tương ứng.

Attestation có thể hỗ trợ:
- quyết định có cho phép enrollment credential hay không;
- đánh giá risk trước khi cấp token;
- giới hạn giao dịch có rủi ro;
- phát hiện app binary hoặc môi trường không đạt policy.

Attestation không lưu secret thay cho Keychain/Keystore. Nó cũng không chứng minh tuyệt đối rằng thiết bị sạch malware hoặc người dùng là chủ account. Token attestation cần được xác minh server-side, có nonce/challenge và chống replay theo API tương ứng.

## 20. Key lifecycle: tạo, dùng, rotate và revoke

Một khóa an toàn cần vòng đời được quản trị:

1. **Generate:** dùng CSPRNG hoặc key generation API của OS/KMS.
2. **Bind:** gắn key với purpose, account, app, tenant và algorithm.
3. **Protect:** đặt access control, hardware backing nếu cần và quyền sử dụng tối thiểu.
4. **Use:** gọi crypto API; hạn chế export và thời gian plaintext tồn tại.
5. **Rotate:** tạo version mới, chuyển ciphertext/token signing sang key mới.
6. **Revoke:** vô hiệu key khi compromise, mất thiết bị hoặc account closure.
7. **Delete:** xóa key và dữ liệu phụ thuộc khi hết retention.
8. **Audit:** ghi key reference/version và event, không ghi key material.

Không dùng cùng một key cho encryption, MAC, signing và nhiều mục đích khác nếu không có key derivation/profile được thiết kế đúng. Domain separation và key purpose phải rõ.

## 21. Mã hóa database và file cục bộ

Nếu app lưu dữ liệu nhạy cảm lớn, có thể dùng database encryption hoặc mã hóa file bằng data-encryption key (DEK). Một mô hình envelope encryption:
- tạo DEK ngẫu nhiên để mã hóa dữ liệu bằng AEAD;
- dùng key trong Keychain/Keystore để wrap hoặc bảo vệ DEK;
- lưu ciphertext và wrapped DEK trong app-private storage;
- khi mở app, yêu cầu OS key store unwrap DEK theo access policy;
- khi rotate, rewrap DEK hoặc mã hóa lại dữ liệu theo thiết kế.

Không lưu DEK plaintext lâu dài trong preferences. Không dùng một khóa hardcoded chung cho mọi installation. Với database lớn, cần kiểm tra khả năng mã hóa page/file, WAL, journal, temporary files và backup; chỉ mã hóa file chính có thể chưa đủ.

## 22. Memory, clipboard, screenshots và logs

Ngay cả khi secret lưu an toàn, app có thể làm lộ nó khi sử dụng:
- giữ access token trong memory lâu hơn cần thiết;
- in token vào log;
- copy OTP/recovery code vào clipboard;
- hiển thị dữ liệu nhạy cảm trong notification;
- lưu screenshot hoặc screen recording;
- đưa secret vào analytics/crash report;
- để dữ liệu trong recent-app snapshot;
- ghi plaintext vào temporary file.

Biện pháp:
- redaction log theo allowlist;
- không log request Authorization hoặc token response;
- xóa/zeroize mutable secret buffer khi có thể;
- giới hạn lifetime và scope của in-memory token;
- ẩn dữ liệu nhạy cảm trong UI snapshot khi phù hợp;
- dùng clipboard policy có thời hạn và cảnh báo;
- kiểm tra crash/analytics SDK;
- không ghi token vào URL hoặc deep link.

Zeroization trên managed runtime không phải lúc nào cũng bảo đảm xóa mọi bản sao bộ nhớ. Giảm số lần copy và thời gian tồn tại thường thực tế hơn.

## 23. Logout và thu hồi credential

Logout mobile nên có cả client-side cleanup và server-side revocation:
1. Gọi endpoint revoke/logout khi có kết nối và theo protocol.
2. Server revoke refresh token/token family và session theo phạm vi yêu cầu.
3. Xóa token khỏi Keychain/secure storage và memory.
4. Xóa cache/dữ liệu account-scoped theo policy.
5. Xóa key hoặc key wrapping material nếu dữ liệu cần không thể truy cập sau logout.
6. Cập nhật UI và xóa trạng thái remembered account nếu policy yêu cầu.

Nếu offline, app có thể xóa local secret ngay nhưng server chưa xác nhận revoke. Không hiển thị “đã logout mọi thiết bị” nếu chỉ mới xóa local token. Khi thiết bị có mạng lại, có thể gửi revoke operation idempotent nếu token/reference còn được bảo vệ và policy cho phép.

Logout không nhất thiết xóa mọi dữ liệu nghiệp vụ hoặc audit. Tách credential/session khỏi dữ liệu cần retention.

## 24. Multi-account và app extension

Ứng dụng có thể hỗ trợ nhiều account, widget, share extension hoặc background worker. Cần tránh nhầm lẫn key/token giữa các account.

Thiết kế:
- keychain item/service name có account reference và purpose;
- Android key alias tách theo account hoặc data key version;
- không dùng một global token slot cho nhiều tenant;
- app extension chỉ truy cập Keychain access group cần thiết;
- giới hạn access group và entitlement;
- background worker chỉ nhận credential cần cho nhiệm vụ;
- logout một account không xóa nhầm dữ liệu account khác;
- kiểm tra race khi đổi account trong lúc request đang chạy.

Không chia sẻ refresh token với extension chỉ vì có chung app group; cần đánh giá extension có thực sự cần token và scope gì.

## 25. Backup, export và dữ liệu đồng bộ

Một số dữ liệu nghiệp vụ có thể cần backup hoặc đồng bộ; credential xác thực thường cần chính sách riêng.

- Backup dữ liệu công việc đã mã hóa có thể được cho phép nếu key management hỗ trợ recovery an toàn.
- Refresh token và private key thiết bị thường không nên được restore mù quáng sang thiết bị mới.
- Export file không được chứa token, private key hoặc wrapped key có thể dùng ngoài policy.
- Sync qua cloud cần encryption, access control, device binding và recovery model rõ.
- Restore phải xác minh account và thiết bị trước khi tái cấp credential.

Nếu người dùng đổi thiết bị, thường nên đăng nhập lại và enroll credential mới. Không cố phục hồi private key thiết bị cũ chỉ từ bản backup file.

## 26. Quan sát và audit secure storage

Có thể ghi:
- key alias/reference và version;
- key generation/rotation/invalidation event;
- loại access control policy;
- kết quả thao tác secure storage ở mức reason code;
- biometric/passcode requirement outcome (không ghi biometric data);
- token issue/refresh/revoke event reference;
- backup/restore detection;
- device/app integrity verdict ở mức cần thiết.

Không log:
- token, password, OTP, recovery code;
- private key, DEK hoặc HMAC secret;
- plaintext decrypted payload;
- raw biometric data;
- toàn bộ Keychain/Keystore contents.

Metrics:
- secure storage read/write failure;
- key invalidation rate;
- token refresh/revoke failure;
- biometric cancellation/failure;
- restore có ciphertext nhưng thiếu key;
- app integrity/attestation failure;
- logout cleanup completion;
- key rotation lag.

Telemetry cần data minimization, access control và retention. Không thu thập fingerprint hoặc device identifiers vượt nhu cầu đã xác định.

## 27. Pseudocode lưu refresh token an toàn trên Android

Ví dụ Kotlin rút gọn: token được mã hóa bằng AES-GCM; key do Android Keystore quản lý; ciphertext và IV được lưu trong app-private storage.

~~~kotlin
data class EncryptedValue(
    val version: Int,
    val iv: ByteArray,
    val ciphertextAndTag: ByteArray
)

fun encryptToken(token: ByteArray, key: SecretKey): EncryptedValue {
    val cipher = Cipher.getInstance("AES/GCM/NoPadding")
    cipher.init(Cipher.ENCRYPT_MODE, key)

    val aad = "mobile-app|refresh-token|v1"
        .toByteArray(Charsets.UTF_8)
    cipher.updateAAD(aad)

    val encrypted = cipher.doFinal(token)

    return EncryptedValue(
        version = 1,
        iv = cipher.iv,
        ciphertextAndTag = encrypted
    )
}

fun decryptToken(value: EncryptedValue, key: SecretKey): ByteArray {
    require(value.version == 1)

    val cipher = Cipher.getInstance("AES/GCM/NoPadding")
    cipher.init(
        Cipher.DECRYPT_MODE,
        key,
        GCMParameterSpec(128, value.iv)
    )

    val aad = "mobile-app|refresh-token|v1"
        .toByteArray(Charsets.UTF_8)
    cipher.updateAAD(aad)

    return cipher.doFinal(value.ciphertextAndTag)
}
~~~

Đây là ví dụ khái niệm. Hàm lấy key phải resolve đúng alias từ Android Keystore; không tạo key mới khi decrypt thất bại. Production cần xử lý key invalidation, nonce uniqueness, serialization/versioning, atomic write, backup exclusion và xóa buffer nhạy cảm.

## 28. Pseudocode Keychain trên iOS

Với secret nhỏ như refresh token, dùng Keychain item thay vì lưu file plaintext. Các thuộc tính cụ thể phụ thuộc yêu cầu UX và background access.

Ví dụ cấu hình khái niệm:
- class: generic password;
- service: định danh ứng dụng và purpose;
- account: account reference opaque;
- value data: token bytes;
- accessibility: WhenUnlockedThisDeviceOnly nếu chỉ cần khi thiết bị mở khóa và không cần migrate;
- access control: yêu cầu user presence/biometric khi hành động cần step-up.

Khi thêm item, ứng dụng nên:
1. Xác định service/account key ổn định nhưng không chứa PII không cần thiết.
2. Đặt accessibility và access-control theo threat model.
3. Xử lý item đã tồn tại bằng update có kiểm soát.
4. Không bật synchronizable nếu token cần gắn với thiết bị.
5. Xử lý errSecItemNotFound, interaction not allowed và authentication failure riêng.
6. Xóa item theo account/purpose khi logout.

Không tự hạ accessibility hoặc bỏ biometric requirement khi gặp lỗi mà không có policy và user consent phù hợp.

## 29. Kiểm thử secure storage

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Token được ghi vào secure storage | Không xuất hiện plaintext trong preferences, file hoặc log. |
| App process restart | Token được đọc theo access policy đã chọn. |
| Thiết bị đang khóa | Item không truy cập được nếu policy yêu cầu unlocked. |
| Biometric enrollment thay đổi | Item/key gắn với current biometric set bị invalidated theo policy; yêu cầu re-auth/enroll lại. |
| Device passcode bị xóa/thay đổi | Xử lý invalidation/accessibility theo platform policy. |
| Android device không có StrongBox | Fallback hoặc từ chối theo policy; không giả định hardware-backed. |
| KeyStore key bị xóa | Ciphertext không được giải mã bằng key mới; recovery flow được kích hoạt. |
| Ciphertext bị sửa | AEAD authentication tag thất bại; không trả plaintext. |
| IV bị tái sử dụng | Test/static review phát hiện; mỗi encryption dùng IV mới. |
| AAD account/purpose không khớp | Decryption thất bại. |
| Backup/restore sang thiết bị mới | Secret device-bound không được khôi phục ngoài policy. |
| Android Auto Backup | Token/key/ciphertext nhạy cảm bị loại trừ hoặc xử lý theo restore design. |
| iOS ThisDeviceOnly item | Không migrate theo hành vi accessibility đã chọn. |
| Reinstall app | Không dựa vào uninstall để chứng minh server logout; account/session được kiểm tra. |
| Root/jailbreak | Risk policy được áp dụng; không tuyên bố secure storage tuyệt đối. |
| Hook API lúc runtime | Backend/token TTL/attestation giảm tác động; hành động nhạy cảm được bảo vệ. |
| Logout online | Server revoke và local secret được xóa. |
| Logout offline | Local cleanup hoàn tất; server revoke pending được mô tả đúng. |
| Multi-account | Token/key của account A không đọc hoặc ghi đè account B. |
| App extension | Chỉ truy cập item trong access group được cấp. |
| Crash/analytics review | Không có token, password, key hoặc plaintext nhạy cảm. |
| Memory inspection | Giảm thời gian token tồn tại và số bản copy; không log buffer. |
| Key rotation | Ciphertext được migrate an toàn hoặc yêu cầu re-auth; không mất dữ liệu âm thầm. |
| Token refresh rotation | Token cũ bị xử lý theo reuse detection và server policy. |
| Device lost | Server có thể revoke token/session dù app không còn truy cập được. |

### Kiểm thử trên thiết bị thật

Secure storage behavior có thể khác theo OS version, OEM, phần cứng và trạng thái thiết bị. Kiểm thử ít nhất:
- phiên bản OS thấp nhất và cao nhất được hỗ trợ;
- thiết bị có/không có hardware-backed key;
- biometric có và không có;
- thiết bị có passcode và không có;
- backup/restore, reinstall và device migration;
- background task khi device locked;
- key invalidation và storage corruption.

Không chỉ dựa vào simulator/emulator để kết luận hardware-backed protection hoạt động như production.

## 30. Bài tập tình huống

Một ứng dụng mobile lưu refresh token trong SharedPreferences để dễ truy cập. Token cũng xuất hiện trong crash log khi API trả lỗi. Ứng dụng mã hóa SQLite bằng AES nhưng key được hardcode trong source. Khi người dùng đổi điện thoại, app restore cả database và token từ cloud backup. Backend không rotate refresh token và không có chức năng revoke từng thiết bị.

**Yêu cầu phân tích:**

1. Những vị trí nào đang làm lộ credential?
2. Vì sao AES không giúp nếu key hardcode?
3. Nên dùng Keychain và Android Keystore như thế nào?
4. Token nào nên giữ trong memory, token nào cần secure persistence?
5. Backup/restore và device migration nên hoạt động ra sao?
6. Cần thiết kế refresh token rotation và per-device revocation thế nào?
7. Nếu thiết bị root/jailbreak, backend cần kiểm soát gì?
8. Những test nào chứng minh logout và key invalidation hoạt động?

**Hướng phân tích:** Loại bỏ token khỏi SharedPreferences/log; dùng Keychain hoặc ciphertext được mã hóa bằng key Android Keystore. Key database không hardcode; dùng envelope encryption và AEAD. Access token ngắn hạn ở memory; refresh token được bảo vệ trong secure storage và rotate. Không restore token/private key thiết bị mù quáng; thiết bị mới phải reauthenticate/enroll. Backend quản lý token family và per-device session để revoke. Root/jailbreak là risk signal, không phải bằng chứng duy nhất; kiểm soát server-side, expiry, attestation và authorization vẫn cần.

## 31. Checklist review

- [ ] Có data inventory và threat model cho credential/dữ liệu mobile.
- [ ] Không lưu password người dùng hoặc hardcode secret trong binary.
- [ ] Access token chỉ persist khi có nhu cầu; refresh token được bảo vệ bằng OS secure storage.
- [ ] iOS dùng Keychain với accessibility/access-control phù hợp.
- [ ] Secure Enclave chỉ được dùng cho key operation được hỗ trợ, không coi là file store.
- [ ] Android dùng Keystore; hardware backing/StrongBox được kiểm tra khi policy yêu cầu.
- [ ] Key và ciphertext được lưu tách biệt.
- [ ] Dữ liệu lớn dùng AEAD; nonce/IV duy nhất và AAD ràng buộc purpose/account/version.
- [ ] Không dùng custom crypto, hash nối secret hoặc key hardcoded.
- [ ] Biometric/passcode gating được cấu hình ở OS key access, không chỉ lưu boolean.
- [ ] Có fallback và xử lý biometric/key invalidation rõ ràng.
- [ ] Backup/restore/migration không làm lộ hoặc phục hồi credential trái policy.
- [ ] Reinstall không được coi là server logout.
- [ ] Root/jailbreak detection không phải lớp phòng vệ duy nhất.
- [ ] Attestation được xác minh server-side và dùng như tín hiệu theo threat model.
- [ ] Token/key không xuất hiện trong logs, analytics, crash report, clipboard hoặc URL.
- [ ] Logout xóa local secret và revoke server session/token theo phạm vi.
- [ ] Multi-account, extension và background task có access scope riêng.
- [ ] Key lifecycle có generate, bind, protect, rotate, revoke, delete và audit.
- [ ] Có test trên thiết bị thật, nhiều OS/OEM và các trạng thái khóa/backup/reinstall.

## 32. Ghi nhớ

**Secure storage trên mobile là sự kết hợp giữa giảm thiểu dữ liệu, kho khóa của hệ điều hành, mã hóa đúng cách, access control và quản lý vòng đời credential.** iOS Keychain lưu secret nhỏ và áp dụng accessibility/access control; Secure Enclave bảo vệ một số private key và thao tác mật mã. Android Keystore quản lý key, có thể dùng TEE hoặc StrongBox tùy thiết bị; dữ liệu lớn được mã hóa bằng AEAD rồi lưu trong app-private storage.

Không hardcode key, không lưu token trong preferences/log, không giả định backup hoặc uninstall sẽ xử lý credential như mong muốn. Biometric gating không thay server authorization; root/jailbreak detection không bảo đảm thiết bị an toàn. Khi review, hãy hỏi: **Dữ liệu nào thật sự cần lưu? Key nằm ở đâu và ai có thể yêu cầu sử dụng? Ciphertext có được ràng buộc với account/purpose không? Backup hoặc reinstall có thể mang credential sang thiết bị khác không? Khi logout, mất thiết bị hoặc key invalidation, backend có thu hồi phiên và token được không?**
