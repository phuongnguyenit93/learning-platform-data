# FIDO2

## 1. FIDO2 là gì?

**FIDO2** là bộ tiêu chuẩn xác thực dựa trên mật mã khóa công khai, được xây dựng để hỗ trợ đăng nhập an toàn, giảm phụ thuộc vào mật khẩu và chống phishing. Kiến trúc FIDO2 kết hợp hai thành phần chính:

- **WebAuthn (Web Authentication):** chuẩn API web do W3C chuẩn hóa, cho phép website (relying party) yêu cầu tạo credential hoặc xác thực bằng authenticator thông qua browser/platform.
- **CTAP (Client to Authenticator Protocol):** giao thức của FIDO Alliance để client platform giao tiếp với authenticator bên ngoài, ví dụ security key qua USB, NFC hoặc Bluetooth.

Có thể nhớ ngắn gọn: **WebAuthn nối ứng dụng web với trình duyệt/platform; CTAP nối client platform với authenticator**. Cả hai phối hợp để tạo ceremony FIDO2. Website không nhận private key và không cần gửi mật khẩu dùng chung tới server.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, FIDO2 là nền tảng quan trọng để hiểu passkey, credential, xác thực chống phishing, MFA, authenticator assurance, session và recovery. Người học cần nắm cả cách giao thức hoạt động lẫn các ranh giới tin cậy: relying party, browser, operating system, authenticator, server verifier và kho public key.

Sau bài học, người học có thể:

- Giải thích mối quan hệ giữa WebAuthn, CTAP và FIDO2.
- Mô tả hai ceremony: đăng ký credential và xác thực bằng credential.
- Giải thích vai trò của challenge, origin, RP ID, public key, private key, UP và UV.
- Phân biệt platform authenticator, roaming authenticator, security key, passkey đồng bộ và credential gắn thiết bị.
- Xác định các bước server phải kiểm tra để chống phishing, replay và giả mạo.
- Thiết kế enrollment, recovery, revoke và session phù hợp với threat model.

## 2. Kiến trúc: WebAuthn + CTAP

FIDO2 không phải một thuật toán đơn lẻ. Nó định nghĩa cách các thành phần trao đổi yêu cầu và bằng chứng xác thực.

~~~mermaid
flowchart LR
    U[Người dùng] --> B[Browser / Client]
    B <-->|WebAuthn API| RP[Relying Party website]
    B <--> P[Platform / OS authenticator]
    P <-->|CTAP nếu dùng authenticator ngoài| K[Roaming authenticator / Security key]
    RP --> DB[(Credential store: public key)]
~~~

Sơ đồ thể hiện vai trò khái niệm; trong triển khai, browser gọi WebAuthn API và phối hợp với hệ điều hành để tìm authenticator phù hợp. Nếu dùng authenticator ngoài, client platform có thể giao tiếp qua CTAP.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Relying Party (RP)** | Website hoặc dịch vụ yêu cầu xác thực; định danh bằng RP ID | example.test |
| **WebAuthn client** | Thành phần browser/platform thực thi API, tạo client data và chuyển kết quả | Browser trên máy tính hoặc điện thoại |
| **Platform authenticator** | Authenticator tích hợp với thiết bị/nền tảng | Cảm biến sinh trắc và kho khóa của hệ điều hành |
| **Roaming authenticator** | Authenticator có thể dùng với nhiều client tương thích | Security key USB/NFC/Bluetooth |
| **CTAP** | Giao thức trao đổi giữa client platform và authenticator bên ngoài | CTAP2 qua USB HID, NFC hoặc BLE tùy thiết bị |
| **Authenticator** | Tạo và giữ private key, thực hiện thao tác xác thực theo chính sách | Security key hoặc platform authenticator |
| **RP server** | Tạo challenge, lưu public key, kiểm tra assertion và quản lý tài khoản/phiên | Backend ứng dụng |

### 2.1. WebAuthn không phải CTAP

WebAuthn là API và định dạng dữ liệu giữa website và browser/client. Ứng dụng web không trực tiếp mở kênh CTAP tới USB security key. Browser và hệ điều hành xử lý việc lựa chọn authenticator và giao tiếp phù hợp.

CTAP là lớp giao thức giúp client platform yêu cầu authenticator bên ngoài thực hiện các thao tác như tạo credential hoặc ký challenge. CTAP không thay thế WebAuthn và cũng không phải API web mà website gọi trực tiếp.

### 2.2. FIDO2 và FIDO U2F

FIDO U2F là thế hệ giao thức trước, chủ yếu hỗ trợ security key như yếu tố thứ hai trong flow đăng nhập. FIDO2 mở rộng mô hình với WebAuthn và CTAP2, hỗ trợ nhiều loại ceremony, bao gồm credential có thể dùng cho đăng nhập không mật khẩu tùy cấu hình.

Một số authenticator hỗ trợ tương thích U2F/CTAP1 có thể được dùng như security key trong flow phù hợp, nhưng không nên suy ra chúng hỗ trợ toàn bộ tính năng FIDO2 hoặc passkey hiện đại. Khi triển khai, kiểm tra khả năng thật của authenticator, browser và policy thay vì chỉ nhìn nhãn FIDO.

## 3. Mô hình khóa công khai

FIDO2 dùng cặp khóa mật mã được tạo cho credential. Về cơ bản:

1. Authenticator tạo cặp khóa riêng/công khai trong quá trình đăng ký.
2. Private key được giữ bởi authenticator hoặc cơ chế quản lý khóa được nền tảng hỗ trợ.
3. Public key và credential metadata được gửi tới RP server và lưu trong tài khoản.
4. Khi xác thực, authenticator ký dữ liệu gắn với challenge và relying party.
5. Server xác minh chữ ký bằng public key đã lưu.

~~~mermaid
sequenceDiagram
    participant A as Authenticator
    participant R as RP Server
    Note over A: Registration
    A->>R: Credential ID + public key + attestation data nếu có
    Note over R: Lưu public key và metadata
    Note over A,R: Authentication về sau
    R->>A: Challenge mới và RP context qua client
    A->>R: Assertion có chữ ký bằng private key
    R->>R: Verify signature bằng public key đã đăng ký
~~~

**Điểm khác biệt với mật khẩu:** server không cần lưu một bí mật dùng chung có thể được nhập lại và gửi qua mạng. Nếu database public key bị đọc, kẻ tấn công không thể tạo assertion hợp lệ chỉ từ public key. Tuy vậy, chiếm tài khoản vẫn có thể xảy ra qua enrollment yếu, recovery yếu, session theft hoặc lỗi verifier.

Private key không nhất thiết luôn nằm trong một chip vật lý riêng. Tùy loại authenticator và hệ sinh thái, khóa có thể được bảo vệ trong phần cứng thiết bị, vùng bảo mật của OS hoặc được đồng bộ qua nhà cung cấp. Cần đánh giá cấu hình và yêu cầu assurance cụ thể.

## 4. Hai ceremony chính

FIDO2/WebAuthn có hai loại hoạt động phổ biến:

- **Registration / credential creation:** tạo credential mới và gắn public key với tài khoản tại RP.
- **Authentication / assertion:** chứng minh quyền kiểm soát credential đã đăng ký bằng cách ký challenge mới.

### 4.1. Registration ceremony

Luồng khái niệm:

1. Người dùng đã được xác định trong ứng dụng; server yêu cầu xác thực hiện tại phù hợp trước khi thêm authenticator.
2. RP server tạo challenge ngẫu nhiên, duy trì trạng thái flow, principal, thời hạn và RP context.
3. Browser gọi WebAuthn API với publicKey options từ server.
4. Authenticator tạo credential mới và trả về credential ID, public key và attestation object theo lựa chọn.
5. Browser gửi response tới server.
6. Server kiểm tra client data, challenge, origin, RP ID hash, loại ceremony, attestation theo policy, thuật toán và dữ liệu credential.
7. Server lưu credential ID, public key, user handle và metadata cần thiết gắn với principal.

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant R as RP Server
    participant A as Authenticator
    C->>R: Yêu cầu bắt đầu đăng ký
    R-->>C: Challenge + RP + user + authenticatorSelection
    C->>A: navigator.credentials.create()
    A-->>C: Credential ID + public key + attestation
    C->>R: Registration response
    R->>R: Verify challenge, origin, RP ID, attestation/policy
    R->>R: Lưu public key và credential metadata
    R-->>C: Registration thành công
~~~

Server không được lưu private key. Việc đăng ký cũng không nên được mở cho một request ẩn danh chỉ vì client gửi một username. Cần xác định đúng tài khoản và bảo vệ thao tác thêm authenticator, vì kẻ tấn công có thể cố đăng ký khóa của mình vào tài khoản nạn nhân.

### 4.2. Authentication ceremony

Luồng xác thực:

1. Client yêu cầu bắt đầu đăng nhập bằng FIDO2.
2. Server tạo challenge mới và trả về options phù hợp, có thể kèm danh sách credential được phép hoặc cho phép discoverable credential.
3. Browser gọi WebAuthn API để lấy assertion.
4. Authenticator xác minh người dùng theo cấu hình và ký dữ liệu challenge.
5. Client gửi assertion về RP server.
6. Server tìm credential tương ứng, xác minh challenge, origin, RP ID hash, chữ ký, cờ UP/UV và các policy liên quan.
7. Nếu hợp lệ, server cập nhật trạng thái xác thực và cấp session/token theo policy.

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant R as RP Server
    participant A as Authenticator
    C->>R: Bắt đầu đăng nhập
    R-->>C: Challenge + RP context + allowCredentials nếu có
    C->>A: navigator.credentials.get()
    A-->>C: Assertion: authenticatorData + clientDataJSON + signature
    C->>R: Authentication response
    R->>R: Verify challenge, origin, RP ID, flags, signature
    R->>R: Resolve principal và policy
    R-->>C: Session/token nếu xác thực hoàn tất
~~~

**Mỗi lần xác thực phải dùng challenge mới.** Không chấp nhận assertion cũ, challenge hết hạn hoặc response thuộc flow khác. Một chữ ký hợp lệ nhưng không được gắn với giao dịch đang chờ chưa đủ để xác thực request hiện tại.

## 5. Các trường dữ liệu cần hiểu

WebAuthn response chứa nhiều lớp dữ liệu. Không phải mọi field đều có cùng nguồn gốc hoặc ý nghĩa.

| Trường | Nguồn/ý nghĩa | Kiểm tra phía server |
| --- | --- | --- |
| **credential ID** | Định danh credential do authenticator tạo | Tra cứu credential đã đăng ký, gắn đúng principal |
| **clientDataJSON** | Dữ liệu client ceremony như type, challenge, origin | Parse an toàn; kiểm tra type, challenge và origin |
| **authenticatorData** | Dữ liệu do authenticator tạo, gồm RP ID hash, flags và sign counter | Kiểm tra RP ID hash, flags, counter theo policy |
| **signature** | Chữ ký bằng private key của credential | Xác minh bằng public key đã lưu |
| **attestationObject** | Bằng chứng đăng ký authenticator, có thể chứa attestation statement và credential data | Xác minh theo attestation policy nếu RP yêu cầu |
| **userHandle** | Định danh người dùng trong phạm vi RP, khi được trả về | Đối chiếu với tài khoản/credential đã liên kết |
| **transports** | Gợi ý transport mà credential hỗ trợ | Chủ yếu phục vụ UX; không phải bằng chứng bảo mật độc lập |

### 5.1. Challenge

Challenge phải được tạo bằng bộ sinh số ngẫu nhiên mật mã, đủ độ dài, có thời hạn và gắn với đúng flow. Server nên lưu challenge ở trạng thái chờ và tiêu thụ nó khi hoàn tất hợp lệ, đồng thời từ chối challenge đã hết hạn hoặc đã dùng.

Không nhận challenge do client tự tạo làm nguồn sự thật. Client có thể gửi lại giá trị do server phát hành, nhưng server phải đối chiếu với trạng thái đang lưu.

### 5.2. Origin và RP ID

**Origin** thường gồm scheme, host và port của trang khởi tạo ceremony. Server kiểm tra origin nằm trong danh sách được phép. **RP ID** là định danh relying party mà credential được tạo cho; authenticatorData chứa hash của RP ID.

Hai khái niệm liên quan nhưng không đồng nhất. Không nên dùng kiểm tra chuỗi hostname lỏng lẻo hoặc cho phép mọi subdomain không cần thiết. Ví dụ, RP ID là example.test có phạm vi khác với login.example.test; việc chọn RP ID ảnh hưởng các subdomain được phép tham gia.

WebAuthn gắn credential với relying party để một trang phishing ở origin khác không thể dùng credential của website thật theo cách xác thực hợp lệ nếu server kiểm tra đúng. Bỏ qua origin hoặc RP ID sẽ phá vỡ một phần quan trọng của khả năng chống phishing.

### 5.3. User Presence (UP) và User Verification (UV)

- **UP — User Presence:** cho biết có thao tác xác nhận sự hiện diện của người dùng theo cách authenticator hỗ trợ, ví dụ chạm vào security key.
- **UV — User Verification:** cho biết authenticator đã thực hiện bước xác minh người dùng cục bộ theo cơ chế hỗ trợ, ví dụ PIN hoặc sinh trắc trên thiết bị.

UP không tương đương UV. Một lần chạm security key có thể chứng minh tương tác hiện diện nhưng không nhất thiết chứng minh người cụ thể đã được xác minh. Nếu policy yêu cầu UV, server phải kiểm tra cờ UV trong authenticator data theo chuẩn và cấu hình.

Không tin việc browser hiện hộp thoại sinh trắc như bằng chứng duy nhất. Server cần xác minh assertion và cờ do authenticator cung cấp trong dữ liệu đã ký.

### 5.4. Backup eligibility và backup state

Các cờ **BE** và **BS** trong authenticator data liên quan tới khả năng backup và trạng thái backup của credential trong các phiên bản WebAuthn hỗ trợ. Chúng giúp RP hiểu credential có thuộc loại có thể backup/sync và đang ở trạng thái backup hay không.

Các cờ này có thể hỗ trợ policy và quản lý credential, nhưng không tự chứng minh nhà cung cấp đồng bộ có bảo mật ở mức cụ thể hoặc người dùng đã đáp ứng một AAL nhất định. Phải diễn giải theo chuẩn và chính sách, tránh gán mức assurance chỉ từ một bit.

### 5.5. Signature counter

Một số authenticator cung cấp sign counter tăng theo lần sử dụng nhằm giúp phát hiện credential bị clone. Tuy nhiên, nhiều passkey đồng bộ hoặc authenticator hiện đại có thể trả counter bằng 0 hoặc không đảm bảo tăng đơn điệu trên mọi thiết bị. RP phải áp dụng quy tắc phù hợp với loại credential, không từ chối mọi passkey chỉ vì counter không tăng; cũng không bỏ qua tín hiệu counter khi chính sách và authenticator cho phép dùng nó.

## 6. Platform authenticator và roaming authenticator

| Loại | Đặc điểm | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Platform authenticator** | Tích hợp với thiết bị/OS, thường sử dụng cơ chế bảo vệ khóa và user verification của nền tảng | Windows Hello, Touch ID/Face ID trong flow WebAuthn phù hợp | Phụ thuộc nền tảng, khóa có thể sync tùy hệ sinh thái |
| **Roaming authenticator** | Thiết bị ngoài có thể kết nối với nhiều client | Security key USB, NFC hoặc BLE | Cần quản lý mất khóa và credential dự phòng |
| **Synced passkey** | Credential có thể đồng bộ giữa các thiết bị qua hệ sinh thái | Passkey trong credential manager hỗ trợ sync | Tin cậy thêm vào account sync, cloud recovery và bảo vệ nhà cung cấp |
| **Device-bound credential** | Khóa gắn với thiết bị hoặc vùng bảo mật, không được đồng bộ theo cấu hình | Một số security key hoặc platform configuration | Cần hiểu khả năng export, backup và thay thiết bị |

Không phải mọi platform authenticator đều tạo passkey đồng bộ, và không phải mọi security key đều đáp ứng cùng khả năng UV hoặc attestation. Cần kiểm tra khả năng cụ thể thay vì suy từ loại thiết bị.

## 7. Discoverable credential và đăng nhập không cần username

WebAuthn hỗ trợ **discoverable credential** (trước đây thường gọi resident credential). Với loại này, authenticator lưu đủ thông tin để có thể chọn credential cho RP mà không cần server gửi trước danh sách credential ID.

Điều này hỗ trợ trải nghiệm **username-less**: người dùng chọn tài khoản/passkey từ authenticator, rồi server dùng credential ID hoặc user handle để xác định principal. Tuy nhiên, username-less không có nghĩa server không cần xác minh tài khoản. Server vẫn phải kiểm tra credential đã đăng ký, chữ ký, challenge, origin, RP ID và trạng thái tài khoản.

Một flow có thể sử dụng:

1. Server phát challenge và yêu cầu discoverable credential.
2. Browser/authenticator hiển thị lựa chọn credential phù hợp RP.
3. Authenticator trả assertion cùng credential ID và có thể có userHandle.
4. Server tra cứu credential ID trong kho dữ liệu, đối chiếu userHandle nếu có và xác minh chữ ký.
5. Server tạo authentication context cho principal đã được xác định.

**User handle** nên là định danh nội bộ ổn định, không chứa email hoặc thông tin cá nhân trực tiếp nếu không cần. Cần thiết kế cách xử lý nhiều credential cho một tài khoản, nhiều tài khoản trên cùng authenticator và credential bị thu hồi.

## 8. Attestation: chứng minh về authenticator trong enrollment

Attestation là cơ chế có thể cho RP biết thông tin về nguồn gốc/loại authenticator trong quá trình đăng ký. Nó không giống assertion xác thực đăng nhập và cũng không phải bằng chứng trực tiếp về danh tính pháp lý của người dùng.

Một RP có thể:

- Chấp nhận attestation kiểu none để giảm thu thập thông tin thiết bị.
- Yêu cầu attestation cụ thể trong môi trường quản lý thiết bị hoặc yêu cầu compliance.
- Kiểm tra chữ ký attestation, certificate chain, trust anchor và metadata theo policy.
- Dùng FIDO Metadata Service hoặc nguồn metadata đáng tin phù hợp để đánh giá authenticator model, trạng thái bảo mật và thông tin liên quan.

Attestation có thể làm tăng khả năng quản lý rủi ro thiết bị, nhưng cũng tạo nguy cơ fingerprinting hoặc liên kết thiết bị. Cần cân nhắc dữ liệu nào được thu thập, lưu bao lâu, ai được truy cập và có thực sự cần xác minh model hay không.

**Attestation không thay thế user verification, authorization hoặc kiểm tra assertion.** Một authenticator thuộc model được chấp nhận vẫn có thể bị mất hoặc bị sử dụng trái phép; session và quyền cần được quản lý riêng.

## 9. Passkey, FIDO2 và trải nghiệm passwordless

**Passkey** là cách triển khai credential khóa công khai hướng tới trải nghiệm đăng nhập đơn giản, thường dựa trên WebAuthn/FIDO. Tùy hệ sinh thái, passkey có thể được đồng bộ giữa các thiết bị hoặc gắn với thiết bị cụ thể.

FIDO2 hỗ trợ passwordless khi RP cho phép discoverable credential và authenticator thực hiện user verification theo policy. Nhưng FIDO2 cũng có thể dùng như yếu tố thứ hai hoặc thay thế một bước trong flow hiện có; không phải mọi flow FIDO2 đều tự động là passwordless.

| Thuật ngữ | Ý nghĩa thực tế |
| --- | --- |
| **FIDO2** | Kiến trúc/tiêu chuẩn kết hợp WebAuthn và CTAP |
| **WebAuthn credential** | Credential public-key được đăng ký cho một RP |
| **Passkey** | Credential FIDO dựa trên public-key, thường được thiết kế để người dùng dùng lại trên các thiết bị/nền tảng |
| **Security key** | Authenticator vật lý có thể hỗ trợ FIDO2/WebAuthn |
| **Passwordless** | Flow không yêu cầu người dùng nhập password |
| **Phishing-resistant** | Bằng chứng được ràng buộc với relying party/origin và được verifier kiểm tra đúng |

Không nên gọi mọi phương thức không mật khẩu là passkey. Magic link, email OTP và SMS OTP có thể là passwordless nhưng không có ràng buộc mật mã với RP như WebAuthn.

## 10. Phòng chống phishing và replay

### 10.1. Phishing resistance

WebAuthn chống phishing nhờ credential gắn với RP ID và dữ liệu client chứa origin. Trang giả mạo ở origin khác không thể yêu cầu authenticator ký cho RP thật theo cách server chấp nhận nếu server xác minh đúng.

Điều kiện:

- RP ID được chọn chính xác và không quá rộng.
- Origin được kiểm tra theo allowlist nghiêm ngặt.
- Challenge được phát hành và kiểm tra phía server.
- Chữ ký được xác minh bằng public key của credential đúng.
- Không có fallback yếu làm mất toàn bộ lợi ích, ví dụ recovery qua email dễ bị chiếm.
- Enrollment credential mới được bảo vệ như một thao tác nhạy cảm.

### 10.2. Replay resistance

Challenge ngẫu nhiên và có thời hạn giúp ngăn assertion cũ được dùng lại. Server cần lưu trạng thái challenge, ràng buộc với flow/principal và tiêu thụ theo quy tắc một lần. Một response hợp lệ cho challenge trước không được chấp nhận cho login mới.

FIDO2 không tự bảo vệ mọi thứ sau khi đăng nhập. Nếu session cookie bị đánh cắp, đối thủ có thể dùng phiên đã cấp cho đến khi bị thu hồi hoặc hết hạn. Vì vậy cần session TTL, rotation, revoke, bảo vệ cookie/token và step-up cho thao tác nhạy cảm.

## 11. Threat model: lỗi triển khai thường gặp

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Bỏ kiểm tra origin** | Chấp nhận assertion từ website không được phép | Allowlist origin, kiểm thử sai origin |
| **Sai RP ID** | Dùng RP ID quá rộng hoặc kiểm tra không chính xác | Chọn RP ID tối thiểu cần thiết và kiểm tra RP ID hash |
| **Replay challenge** | Chấp nhận response cũ hoặc challenge đã dùng | Nonce/challenge mới, TTL, consume-once |
| **Enrollment takeover** | Kẻ tấn công thêm public key của mình vào tài khoản nạn nhân | Reauthentication/step-up, audit, notification, account binding |
| **Credential confusion** | Dùng credential ID không thuộc principal hoặc tenant | Kiểm tra mapping credential–principal–RP |
| **Bỏ qua UV** | Policy yêu cầu user verification nhưng server chỉ kiểm tra UP | Kiểm tra UV flag theo yêu cầu |
| **Tin client state** | Client gửi cờ passkeyVerified=true | Chỉ tin verifier đã kiểm tra assertion |
| **Attestation misconfiguration** | Tin certificate/metadata không đúng trust anchor | Validate chain, metadata và policy |
| **Counter false positive** | Từ chối synced passkey do counter không tăng | Diễn giải counter theo loại authenticator và chuẩn |
| **Sync account takeover** | Tài khoản cloud đồng bộ passkey bị chiếm | Đánh giá recovery và bảo vệ tài khoản đồng bộ |
| **Recovery bypass** | Email reset yếu thay thế passkey mạnh | Recovery assurance tương xứng, giới hạn quyền và review |
| **Session hijacking** | Cookie bị lấy sau WebAuthn login | Secure/HttpOnly/SameSite, TTL, rotation, revoke, CSRF/XSS controls |
| **Credential loss** | Người dùng mất thiết bị/khóa duy nhất | Credential dự phòng, recovery an toàn và revoke |

Một triển khai cần kiểm thử cả các nhánh lỗi và fallback. Đường đăng nhập chính có thể rất mạnh nhưng đường đăng ký lại hoặc khôi phục có thể trở thành điểm yếu nhất.

## 12. Triển khai server: checklist xác minh

Server cần xử lý registration và authentication như các giao dịch có trạng thái. Một checklist khái niệm:

### 12.1. Registration

- Tài khoản/principal đã được xác định và flow enrollment được phép.
- Challenge do server tạo, ngẫu nhiên, còn hạn và gắn đúng flow.
- Kiểm tra type của client data là ceremony tạo credential.
- Kiểm tra challenge và origin.
- Kiểm tra RP ID hash trong authenticator data.
- Kiểm tra attestation theo policy; nếu yêu cầu, xác minh chain và metadata.
- Xác minh credential public key, credential ID, thuật toán và user handle.
- Kiểm tra credential chưa bị trùng hoặc liên kết sai tài khoản.
- Lưu public key và metadata cần thiết; không lưu private key.
- Ghi audit và thông báo enrollment theo policy.

### 12.2. Authentication

- Challenge mới được phát hành và còn hạn.
- Kiểm tra client data type là ceremony lấy assertion.
- Kiểm tra challenge và origin allowlist.
- Kiểm tra RP ID hash.
- Tra cứu đúng credential public key đã đăng ký.
- Xác minh chữ ký trên dữ liệu theo chuẩn.
- Kiểm tra UP/UV theo policy.
- Đối chiếu userHandle/principal nếu được trả về.
- Diễn giải sign counter và backup flags phù hợp loại credential.
- Kiểm tra trạng thái account/credential và risk policy.
- Tiêu thụ challenge, tạo auth context phía server và cấp session/token phù hợp.
- Không để client tự khai mức assurance hoặc principal.

**Khuyến nghị:** dùng thư viện WebAuthn server đã được duy trì và kiểm thử; không tự viết parser hoặc verifier mật mã nếu không có chuyên môn và kiểm thử tương ứng. Cần theo dõi phiên bản thư viện, chuẩn WebAuthn/CTAP và cập nhật bảo mật.

## 13. Ví dụ cấu trúc dữ liệu phía server

Mô hình dữ liệu nội bộ có thể gồm:

~~~ts
type WebAuthnCredential = {
  credentialId: Uint8Array;
  publicKey: Uint8Array;
  userHandle: Uint8Array;
  rpId: string;
  userId: string;
  signCount: number;
  transports?: string[];
  backupEligible?: boolean;
  backupState?: boolean;
  createdAt: string;
  lastUsedAt?: string;
  status: "active" | "revoked";
};

type WebAuthnChallenge = {
  challengeId: string;
  challenge: Uint8Array;
  userId?: string;
  purpose: "registration" | "authentication";
  expiresAt: string;
  consumedAt?: string;
};
~~~

Đây là **mô hình khái niệm**, không phải schema chuẩn bắt buộc. Khi triển khai cần xử lý serialization, index, uniqueness, transaction, tenant boundary, dữ liệu credential nhạy cảm và quy tắc lưu trữ. Không lưu raw attestation hoặc telemetry dư thừa nếu không có mục đích và chính sách retention rõ ràng.

## 14. Vòng đời credential: thêm, mất, revoke và recovery

FIDO2 giảm việc phụ thuộc mật khẩu nhưng không loại bỏ nhu cầu quản lý vòng đời:

1. **Thêm credential:** chỉ qua flow enrollment được xác thực; yêu cầu step-up nếu thao tác nhạy cảm.
2. **Hiển thị credential:** người dùng có thể nhận biết thiết bị/credential ở mức metadata phù hợp, như tên do họ đặt, ngày tạo và lần dùng gần nhất.
3. **Đổi thiết bị:** hỗ trợ đăng ký credential mới trước khi bỏ credential cũ nếu an toàn.
4. **Mất authenticator:** có cách báo mất và thu hồi credential/session liên quan.
5. **Recovery:** đánh giá tài khoản đồng bộ, credential dự phòng, recovery code và xác minh thủ công; không để đường recovery yếu hơn đáng kể.
6. **Revoke:** cập nhật trạng thái credential ở server, thu hồi session/token theo policy và ghi audit.
7. **Offboarding:** với tài khoản doanh nghiệp, thu hồi credential và thiết bị khi nhân viên rời tổ chức hoặc thiết bị không còn được quản lý.

Nếu một tài khoản chỉ có duy nhất một passkey trên điện thoại và người dùng mất điện thoại, không có phương thức dự phòng sẽ dẫn tới khóa tài khoản. Ngược lại, recovery quá dễ có thể cho kẻ tấn công đăng ký passkey của họ. Thiết kế cần cân bằng khả năng truy cập và mức bảo đảm.

## 15. Quyền riêng tư và khả năng tiếp cận

FIDO2 được thiết kế để hạn chế việc chia sẻ bí mật với website, nhưng triển khai vẫn có thể thu thập metadata nhạy cảm.

- Chỉ yêu cầu attestation khi có nhu cầu rõ ràng.
- Không dùng attestation hoặc credential metadata để fingerprint người dùng ngoài mục đích bảo mật đã công bố.
- Không lưu thông tin thiết bị/transport dư thừa nếu không phục vụ policy hoặc UX.
- Giải thích rõ passkey được lưu/đồng bộ ở đâu theo nền tảng và cách quản lý thiết bị.
- Hỗ trợ nhiều authenticator, thiết bị dự phòng và quy trình recovery.
- Kiểm thử dialog WebAuthn với công nghệ hỗ trợ, trình duyệt và thiết bị thực tế.
- Không ép người dùng cung cấp sinh trắc cho website; user verification có thể được thực hiện cục bộ bằng cơ chế phù hợp của authenticator.
- Bảo vệ dữ liệu account linking, credential ID, user handle và audit theo chính sách riêng tư.

## 16. Checklist đánh giá một triển khai FIDO2

| Câu hỏi | Dấu hiệu triển khai tốt |
| --- | --- |
| Có hiểu đúng WebAuthn và CTAP? | Website dùng WebAuthn; client platform giao tiếp authenticator ngoài qua CTAP |
| RP ID và origin có chính xác? | Danh sách cho phép rõ, không dùng wildcard tùy tiện |
| Challenge có an toàn? | Ngẫu nhiên, mới, có TTL, gắn flow và tiêu thụ theo quy tắc |
| Registration có được bảo vệ? | Principal xác thực, step-up, kiểm tra binding và audit |
| Server có xác minh chữ ký? | Public key đã đăng ký, dữ liệu đúng ceremony |
| Có kiểm tra UP/UV? | Đúng policy; không nhầm hiện diện với xác minh người dùng |
| Attestation có cần thiết? | Policy rõ, trust anchor/metadata hợp lệ, cân nhắc privacy |
| Synced passkey có được xử lý đúng? | Hiểu BE/BS và sign counter, không gán AAL từ một cờ |
| Có credential dự phòng? | Hỗ trợ nhiều authenticator và quy trình mất thiết bị |
| Recovery có yếu hơn login? | Có threat model, giới hạn, step-up, notification và audit |
| Session được bảo vệ? | TTL, rotation, revoke, cookie/token an toàn |
| Có kiểm thử phishing/replay? | Sai origin, sai RP ID, challenge cũ và assertion giả đều bị từ chối |
| Có kiểm soát privacy/accessibility? | Attestation tối thiểu, hỗ trợ công nghệ và nhiều thiết bị |

### Tình huống tự kiểm tra

**Tình huống 1:** Một website nhận WebAuthn response, decode JSON và thấy credential ID có trong database. Có thể đăng nhập ngay không?

**Trả lời:** Không. Cần kiểm tra challenge, origin, RP ID hash, chữ ký, cờ UP/UV và mapping credential/principal theo chuẩn.

**Tình huống 2:** Authenticator báo UP=true nhưng UV=false, trong khi policy yêu cầu xác minh người dùng. Có chấp nhận không?

**Trả lời:** Không. UP chỉ chứng minh có thao tác hiện diện; policy yêu cầu UV thì verifier phải kiểm tra UV.

**Tình huống 3:** Sign counter của passkey đồng bộ không tăng. Có thể kết luận credential bị clone không?

**Trả lời:** Không thể kết luận chỉ từ counter. Cần diễn giải theo loại authenticator, backup/sync behavior và policy.

**Tình huống 4:** Server xác minh đúng chữ ký nhưng chấp nhận mọi origin. Còn chống phishing không?

**Trả lời:** Không. Ràng buộc origin và RP ID là phần cốt lõi; chữ ký đúng mà không kiểm tra bên nhận vẫn có thể tạo lỗi trust boundary.

**Tình huống 5:** Người dùng mất thiết bị, support thêm passkey mới chỉ bằng email link. Đây có phải recovery tương xứng không?

**Trả lời:** Không mặc nhiên. Phải đánh giá mức tin cậy của email, risk, giá trị tài khoản và yêu cầu xác minh/step-up bổ sung.

## 17. Ghi nhớ

**FIDO2 kết hợp WebAuthn và CTAP để xác thực bằng mật mã khóa công khai.** WebAuthn là giao diện giữa website và browser/platform; CTAP là giao thức giữa client platform và authenticator bên ngoài. Trong registration, authenticator tạo credential và RP lưu public key. Trong authentication, authenticator ký challenge mới và server xác minh assertion theo đúng relying party.

Sức mạnh của FIDO2 đến từ việc credential được ràng buộc với RP ID/origin, private key không được gửi cho website và verifier kiểm tra challenge/chữ ký. Nhưng triển khai chỉ an toàn khi enrollment, UP/UV, attestation policy, session, recovery, revoke và authorization đều được thiết kế đúng. Hãy đánh giá **toàn bộ vòng đời credential và các ranh giới tin cậy**, không chỉ việc browser hiển thị nút passkey.
