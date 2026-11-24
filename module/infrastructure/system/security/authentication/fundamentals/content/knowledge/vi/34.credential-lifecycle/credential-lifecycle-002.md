# Credential activation

## 1. Credential activation là gì?

**Credential activation** là quy trình chuyển một credential từ trạng thái được tạo hoặc cấp phát nhưng chưa được phép dùng sang trạng thái hoạt động để xác thực một principal. Activation xác nhận rằng credential đã được thiết lập đúng với tài khoản dự kiến, người dùng hoặc thiết bị có quyền kiểm soát authenticator và các điều kiện bảo mật bắt buộc đã hoàn tất.

Credential có thể là password, passkey, security key, authenticator TOTP, thiết bị push, client certificate hoặc khóa của workload. Cách activation khác nhau theo loại credential, nhưng đều cần trả lời ba câu hỏi: credential được gắn với principal nào, ai có thể hoàn tất activation và hệ thống dựa vào bằng chứng nào để tin credential đó.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, credential activation là bước nối identity proofing, account lifecycle, authentication factor, passkey, certificate, session và recovery. Tạo một bản ghi credential trong database chưa có nghĩa credential đã an toàn để sử dụng. Nếu activation link bị đánh cắp, người khác có thể đăng ký authenticator của họ vào tài khoản nạn nhân và chiếm quyền kiểm soát tài khoản ngay từ đầu.

Sau bài học, người học có thể:

- Phân biệt credential issuance, enrollment, activation và authentication.
- Thiết kế activation ceremony gắn credential với đúng principal.
- Bảo vệ activation token, challenge, QR code và kênh phân phối.
- Áp dụng activation phù hợp cho password, passkey, MFA, certificate và thiết bị.
- Xác minh proof of possession và các điều kiện enrollment.
- Quản lý trạng thái pending, active, suspended, revoked và expired.
- Xử lý activation thất bại, retry, recovery và thông báo bảo mật.
- Kiểm thử replay, account binding, phishing, race condition và credential takeover.

## 2. Credential lifecycle và vị trí của activation

Credential lifecycle quản lý credential từ lúc được tạo tới khi hết hạn hoặc bị thu hồi. Activation là một giai đoạn trong vòng đời đó.

| Giai đoạn | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Provisioning / issuance** | Tạo hoặc phân phối credential hay thông tin để đăng ký credential | Tạo invitation, phát hành certificate request hoặc tạo enrollment record |
| **Enrollment** | Thu thập public key, verifier hoặc thông tin authenticator cần quản lý | Đăng ký passkey, TOTP seed hoặc public certificate |
| **Activation** | Xác minh binding và điều kiện cần thiết rồi cho phép credential được sử dụng | Xác nhận passkey vừa đăng ký, kích hoạt token phần cứng |
| **Authentication** | Dùng credential active để chứng minh quyền kiểm soát | Ký WebAuthn assertion, nhập password hoặc tạo TOTP |
| **Rotation / replacement** | Thay credential cũ bằng credential mới | Đổi certificate hoặc thêm passkey mới |
| **Suspension** | Tạm ngừng credential khi có nghi ngờ hoặc yêu cầu quản trị | Tạm khóa security key bị thất lạc |
| **Revocation / deletion** | Thu hồi quyền sử dụng credential | Xóa passkey, thu hồi certificate |
| **Expiration** | Credential hết hạn theo policy | Certificate hết hạn, activation code hết TTL |

Các hệ thống có thể gộp enrollment và activation trong một giao dịch. Dù triển khai gộp, cần giữ rõ các điều kiện logic: dữ liệu credential đã được nhận, binding đã được xác minh và trạng thái active chỉ được ghi khi toàn bộ bước bắt buộc thành công.

### 2.1. Issuance không phải activation

Ví dụ, hệ thống tạo một invitation token cho nhân viên mới. Token đó chỉ cho phép bắt đầu quy trình enrollment trong một thời hạn. Nó chưa phải password, passkey hoặc credential đăng nhập chính thức. Tương tự, một certificate request được tạo chưa có nghĩa certificate đã được cấp, tin cậy và cài đặt trên đúng thiết bị.

Không cấp quyền truy cập chỉ vì credential record đã được tạo. Backend phải kiểm tra trạng thái active và policy của credential khi xác thực.

### 2.2. Activation không phải authentication thường xuyên

Activation là thiết lập hoặc mở khóa một credential cho việc sử dụng về sau. Authentication là sử dụng credential active trong một lần đăng nhập hoặc giao dịch. Người dùng có thể hoàn tất activation passkey hôm nay rồi dùng passkey đó nhiều lần sau này.

Một lần activation thành công không tự chứng minh mọi lần đăng nhập sau này là hợp lệ. Mỗi authentication vẫn cần challenge, signature/verifier check, session policy và authorization.

## 3. Trust binding: gắn credential với đúng principal

Rủi ro cốt lõi của activation là credential hợp lệ nhưng được gắn vào sai tài khoản. Một attacker có thể chiếm activation link của người khác, thay đổi recipient, hoặc lợi dụng lỗi race condition để đăng ký authenticator vào principal không thuộc quyền kiểm soát của họ.

Một activation flow phải ràng buộc:

- **Principal:** subject/account đã được xác định từ nguồn tin cậy.
- **Credential type:** loại authenticator được phép đăng ký.
- **Enrollment transaction:** mã giao dịch duy nhất và trạng thái server-side.
- **Initiator:** người hoặc hệ thống yêu cầu activation.
- **Proof of control:** bằng chứng người thực hiện kiểm soát authenticator hoặc kênh được phê duyệt.
- **Policy:** yêu cầu identity proofing, reauthentication, MFA hoặc approval.
- **Expiry:** thời hạn hoàn tất.
- **Context:** tenant, issuer, relying party, device hoặc môi trường phù hợp.

Không nhận subject ID, email, tenant ID hoặc credential owner do browser tự gửi rồi tin chúng. Server phải lấy principal từ invitation transaction đã được tạo và phê duyệt trước đó.

~~~mermaid
flowchart TD
    A[Request tạo credential] --> B[Resolve principal từ nguồn tin cậy]
    B --> C[Tạo enrollment transaction]
    C --> D[Phân phối challenge / activation token]
    D --> E[Người dùng chứng minh quyền kiểm soát]
    E --> F[Validate authenticator và binding]
    F --> G{Policy và proof đạt?}
    G -- Không --> H[Giữ pending hoặc hủy transaction]
    G -- Có --> I[Consume challenge atomically]
    I --> J[Đặt credential active]
    J --> K[Audit và notification]
~~~

### 3.1. Binding với tài khoản và tenant

Trong hệ thống đa tenant, credential cần được gắn với đúng principal trong đúng tenant. Cùng một email có thể xuất hiện ở nhiều tổ chức; không dùng email làm căn cứ duy nhất để chọn account.

Với federated identity, mapping cần dựa trên issuer và subject theo hợp đồng. Với account nội bộ, dùng internal subject ID ổn định. Nếu một credential được chia sẻ giữa nhiều tài khoản hoặc nhiều người, phải có mô hình ownership và policy riêng; không tạo binding ngầm dựa trên thiết bị đang đăng nhập.

### 3.2. Reauthentication trước khi thêm credential

Thêm password reset method, passkey hoặc MFA mới có thể làm thay đổi cách lấy lại tài khoản. Vì vậy, người đang đăng nhập cần chứng minh quyền kiểm soát account hiện tại trước khi đăng ký credential bổ sung.

Với hành động rủi ro cao, policy có thể yêu cầu:
- Reauthentication bằng credential hiện có.
- Step-up bằng MFA hoặc phương thức chống phishing.
- Xác minh qua kênh độc lập đã được đăng ký trước.
- Approval của administrator hoặc sponsor.
- Notification tới các kênh hiện có sau khi activation.

Không để một session yếu hoặc vừa recovery tự thêm authenticator mạnh rồi lập tức loại bỏ mọi credential cũ mà không có kiểm soát.

## 4. Activation ceremony

**Activation ceremony** là chuỗi bước mà người dùng, client, authenticator và server thực hiện để thiết lập credential. Một ceremony tốt cần dễ hiểu, có thể xác minh và không dựa vào bí mật dùng chung hoặc thao tác ngoài luồng không được ràng buộc.

Các bước khái quát:

1. Xác định principal và kiểm tra trạng thái account.
2. Kiểm tra người yêu cầu có quyền kích hoạt credential.
3. Tạo enrollment transaction và challenge ngẫu nhiên.
4. Phân phối thông tin activation qua kênh được policy chấp nhận.
5. Người dùng thực hiện thao tác trên authenticator.
6. Server kiểm tra proof, challenge, origin/issuer hoặc dữ liệu tương ứng.
7. Kiểm tra credential chưa bị đăng ký cho principal khác nếu policy yêu cầu uniqueness.
8. Consume transaction một lần và ghi credential ở trạng thái active.
9. Gửi thông báo và lưu audit event.
10. Hủy các activation token, challenge và dữ liệu tạm không còn cần thiết.

### 4.1. Activation token

Activation token là credential tạm thời cho phép tiếp tục enrollment. Nó cần được bảo vệ tương tự một bearer secret:

- Sinh bằng cryptographically secure random generator.
- Có entropy đủ cao và không thể đoán theo user ID hoặc timestamp.
- Có thời hạn ngắn và mục đích giới hạn.
- Gắn với principal, loại credential và enrollment transaction.
- Chỉ dùng một lần; thao tác tiêu thụ phải nguyên tử.
- Lưu hash/HMAC ở server nếu phù hợp, không lưu token thô không cần thiết.
- Không ghi token vào application log, analytics, referrer hoặc crash report.
- Có thể revoke khi người dùng báo lộ link hoặc yêu cầu tạo link mới.

Token trong URL có thể xuất hiện trong browser history, proxy log hoặc referrer. Dùng HTTPS, đặt Referrer-Policy phù hợp, tránh tải tài nguyên bên thứ ba trên trang activation và đổi token thành trạng thái server-side ngay khi xác nhận hợp lệ. Không để token tồn tại trong URL sau khi transaction đã được tạo nếu có thể tránh.

### 4.2. One-time và race condition

Hai request đồng thời có thể cùng kiểm tra một activation token trước khi một request tiêu thụ nó. Nếu kiểm tra và cập nhật không nguyên tử, cùng một token có thể kích hoạt hai credential hoặc tạo hai principal.

Dùng transaction/conditional update để chỉ một request chuyển enrollment từ pending sang consumed/active. Các request lặp sau đó phải bị từ chối hoặc trả trạng thái đã hoàn tất mà không lặp side effect.

### 4.3. Kênh phân phối

Kênh gửi activation phụ thuộc mức assurance và loại account:

| Kênh | Có thể phù hợp khi | Giới hạn |
| --- | --- | --- |
| **Email đã xác minh** | Onboarding ít hoặc trung bình rủi ro, recipient binding rõ | Mailbox có thể bị chiếm hoặc chuyển tiếp |
| **SMS/voice** | Xác nhận quyền truy cập số điện thoại trong flow được phép | SIM swap, tái cấp số và interception |
| **In-person handoff** | Credential phần cứng hoặc môi trường đặc quyền | Cần xác minh người nhận và audit bàn giao |
| **Administrator/sponsor workflow** | Nhân viên, contractor hoặc thiết bị được tổ chức quản lý | Insider risk và phê duyệt nhầm |
| **Existing authenticated session** | Người dùng đang xác thực đủ mạnh để thêm credential | Session có thể bị chiếm; cần reauthentication/step-up |
| **Device management channel** | Certificate hoặc workload/device credential | Phải bảo vệ enrollment agent và management plane |

Không dùng cùng một kênh yếu để vừa tạo account, vừa xác nhận danh tính, vừa kích hoạt credential đặc quyền nếu threat model yêu cầu bằng chứng độc lập.

## 5. Password activation

Password activation thường cho phép người dùng đặt password đầu tiên hoặc thay password tạm thời bằng secret do chính họ chọn.

Quy trình có thể:

1. Xác minh activation transaction và principal.
2. Kiểm tra người dùng chưa bị khóa hoặc transaction đã hết hạn.
3. Thu nhận password qua TLS.
4. Kiểm tra chính sách password và danh sách password phổ biến/đã lộ.
5. Hash bằng password hashing scheme phù hợp, có salt riêng và cost được cấu hình.
6. Lưu credential verifier và đánh dấu credential active trong cùng giao dịch logic.
7. Hủy activation token.
8. Gửi thông báo rằng password đã được thiết lập.

Không lưu password dạng plaintext, không mã hóa có thể giải ngược để tiện hỗ trợ và không dùng hash nhanh như SHA-256 đơn lẻ làm password storage. Dùng password hashing chuyên dụng như Argon2id, scrypt hoặc bcrypt theo khuyến nghị hiện hành và khả năng nền tảng; tham số cần được benchmark và cập nhật.

### 5.1. Password tạm thời

Nếu tổ chức cấp password tạm thời, password đó phải có thời hạn ngắn, được phân phối qua kênh bảo vệ và buộc thay đổi theo policy. Tuy nhiên, password tạm thời vẫn là một secret có thể bị đánh cắp; không gửi chung password và username qua cùng một kênh không bảo vệ.

Không dùng password mẫu như ngày sinh, mã nhân viên hoặc tên công ty. Tốt hơn là cho người dùng tự thiết lập password qua activation transaction được bảo vệ, hoặc ưu tiên passkey nếu phù hợp.

### 5.2. Password activation không chứng minh danh tính mạnh

Người đặt được password chứng minh họ có quyền truy cập activation flow tại thời điểm đó. Nếu activation flow dựa vào email yếu hoặc invitation bị chuyển tiếp, password mới có thể được gắn vào account sai người. Identity proofing và account binding cần được giải quyết trước hoặc trong ceremony theo risk policy.

## 6. Passkey và WebAuthn activation

Passkey enrollment tạo một cặp khóa: private key nằm trong authenticator và public key được relying party lưu. Activation hoàn tất khi server xác minh registration response và lưu credential gắn với đúng account.

Một flow WebAuthn cơ bản:

1. Người dùng đã đăng nhập hoặc hoàn tất onboarding proofing.
2. Server tạo challenge ngẫu nhiên, gắn với principal và transaction.
3. Client gọi WebAuthn credential creation với RP ID, user identity và các tùy chọn được policy cho phép.
4. Authenticator tạo credential key pair và trả attestation/registration response.
5. Server xác minh challenge, origin, RP ID hash, type, credential ID và chữ ký/attestation theo policy.
6. Server lưu public key, credential ID và metadata cần thiết; không nhận hoặc lưu private key.
7. Server tiêu thụ challenge và chuyển credential sang active.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Authenticator
    participant S as Relying Party Server
    U->>B: Chọn thêm passkey
    B->>S: Yêu cầu registration options
    S-->>B: Challenge + RP/user options
    B->>A: WebAuthn create()
    A->>A: Tạo key pair và user verification
    A-->>B: Attestation / credential response
    B->>S: Gửi registration response
    S->>S: Verify challenge, origin, RP ID và response
    S->>S: Lưu public key + credential ID
    S-->>B: Activation thành công
~~~

### 6.1. Kiểm tra registration response

Server cần xác minh theo WebAuthn:
- Challenge khớp và chưa được sử dụng.
- Origin thuộc allowlist chính xác của RP.
- RP ID hash khớp RP ID dự kiến.
- Type và client data đúng loại ceremony.
- Credential ID không bị collision hoặc gắn với account khác theo policy.
- Attestation được xử lý theo trust policy; không mặc định mọi attestation phải được tin hoặc mọi authenticator đều có cùng assurance.
- User verification đáp ứng yêu cầu nếu policy yêu cầu.
- Thuật toán và key type nằm trong allowlist.
- Enrollment transaction vẫn pending và gắn với đúng principal.

Không tự xác minh WebAuthn bằng cách chỉ đọc JSON phía client. Dùng thư viện server-side được duy trì và tuân thủ đặc tả.

### 6.2. Attestation và user verification

Attestation có thể cung cấp thông tin về authenticator model hoặc nguồn gốc theo format và trust metadata. Tùy sản phẩm, RP có thể dùng attestation để áp dụng policy thiết bị. Nhiều dịch vụ consumer không cần nhận diện model cụ thể và có thể chấp nhận none attestation.

User verification là bước authenticator xác minh người dùng cục bộ, ví dụ PIN hoặc biometrics trên thiết bị. Nó khác user presence và khác identity proofing. RP phải kiểm tra cờ tương ứng trong authenticator data nếu policy yêu cầu UV.

### 6.3. Passkey đồng bộ và thiết bị

Passkey có thể được đồng bộ qua hệ sinh thái nhà cung cấp hoặc gắn với thiết bị/security key. Mô hình đồng bộ tăng tiện dụng nhưng tổ chức cần hiểu recovery, account ecosystem và khả năng đồng bộ của credential. Không giả định mọi passkey đều là hardware-bound hoặc có cùng mức bảo đảm.

Nếu dữ liệu nhạy cảm yêu cầu authenticator phần cứng được quản lý, cần policy xác định attestation/managed device và quy trình cấp phát phù hợp. Không suy ra thuộc tính đó chỉ từ việc giao diện hiển thị biểu tượng passkey.

## 7. MFA và authenticator activation

MFA enrollment có thể bao gồm TOTP, push authenticator, security key, SMS hoặc phương thức khác. Activation cần chứng minh người dùng kiểm soát phương thức mới và gắn nó với đúng account.

### 7.1. TOTP activation

Với TOTP:
1. Server tạo secret ngẫu nhiên cho account và enrollment transaction.
2. Hiển thị QR code/otpauth URI qua kênh TLS trong session đã được xác minh.
3. Người dùng quét bằng authenticator app.
4. Người dùng nhập mã hiện tại.
5. Server kiểm tra mã với secret và time window cho phép.
6. Nếu đúng, server kích hoạt factor và lưu secret được mã hóa bảo vệ.
7. QR/secret enrollment bị xóa khỏi trạng thái hiển thị và không ghi log.

Không đánh dấu TOTP active ngay khi hiển thị QR. Người dùng có thể chưa quét hoặc đã quét nhầm. Yêu cầu proof bằng mã hợp lệ trước khi kích hoạt.

Secret TOTP cần được bảo vệ vì server phải có khả năng tính mã để xác minh. Mã hóa khi lưu, quản lý khóa tách biệt, hạn chế quyền đọc và không ghi secret vào log. Không dùng password hashing một chiều cho secret mà server cần đọc lại để xác minh.

### 7.2. Push authenticator activation

Push enrollment có thể yêu cầu cài app, liên kết thiết bị và xác nhận mã ghép nối. Activation cần ràng buộc device registration với account và transaction. Mã ghép nối phải ngẫu nhiên, TTL ngắn, one-time và không cho phép một thiết bị đăng ký vào account khác chỉ bằng cách biết mã.

Sau activation, thông báo push cần hiển thị thông tin đủ để người dùng nhận ra request. Number matching hoặc challenge rõ ràng giúp giảm MFA fatigue và push bombing. Push approval không tự chống phishing nếu người dùng bị dụ chấp thuận.

### 7.3. Security key

Security key FIDO2/WebAuthn thường được đăng ký qua ceremony passkey/security key. Nếu tổ chức cấp key vật lý, cần ghi nhận bàn giao, serial/asset reference nếu phù hợp, người nhận và trạng thái. Serial number không phải credential và không thay thế cryptographic proof.

Nếu yêu cầu nhiều yếu tố hoặc backup factor, activation phải xác minh từng factor riêng. Không coi việc thêm số điện thoại làm recovery channel là đã kích hoạt MFA mạnh.

### 7.4. Recovery codes

Recovery code là credential dự phòng. Khi phát hành:
- Sinh mã có entropy đủ cao.
- Chỉ hiển thị một lần sau khi xác thực.
- Lưu verifier/hash phù hợp để kiểm tra; không lưu plaintext.
- Mỗi mã chỉ dùng một lần và tiêu thụ nguyên tử.
- Cảnh báo người dùng cất giữ an toàn.
- Cho phép tạo bộ mã mới và thu hồi bộ cũ qua quy trình reauthentication.
- Audit sự kiện phát hành và sử dụng nhưng không log giá trị mã.

## 8. Certificate và device credential activation

Certificate-based authentication thường có bước tạo key pair, gửi Certificate Signing Request (CSR), xác minh requester, cấp certificate và cài đặt certificate trên thiết bị/workload.

Một quy trình có thể:

1. Xác định principal hoặc device/workload identity từ nguồn quản lý.
2. Tạo key pair trong TPM, secure enclave, HSM hoặc keystore phù hợp.
3. Tạo CSR chứa public key và subject/SAN theo policy.
4. Registration Authority kiểm tra requester, device posture, tenant và quyền yêu cầu.
5. CA cấp certificate với subject, SAN, key usage, extended key usage và validity phù hợp.
6. Certificate được cài vào keystore; private key không rời vùng bảo vệ nếu kiến trúc hỗ trợ.
7. Client thực hiện handshake hoặc proof-of-possession.
8. Server/PKI ghi trạng thái active và mapping certificate tới principal.

### 8.1. Không nhầm certificate với private key

Certificate chứa public key và thông tin được CA ký. Private key là bí mật dùng để chứng minh quyền kiểm soát. Activation phải xác nhận thiết bị giữ private key tương ứng, không chỉ nhận được file certificate.

Không gửi private key qua email hoặc ticket. Nếu private key được tạo trên thiết bị, ưu tiên key không xuất được khi threat model yêu cầu. CSR chỉ mang public key và dữ liệu yêu cầu; CA cần kiểm tra subject/SAN và quyền cấp.

### 8.2. Device binding

Với device credential, cần xác định credential gắn với:
- Người dùng cụ thể.
- Thiết bị được quản lý.
- Workload/service.
- Một tenant hoặc môi trường cụ thể.

Không tự động chuyển certificate của một thiết bị sang thiết bị khác. Khi thiết bị bị mất, thay thế hoặc retire, cần revoke certificate và thu hồi session/credential liên quan theo policy.

## 9. State machine và activation status

Một state model giúp tránh sử dụng credential chưa được xác minh.

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Active: Proof và policy đạt
    Pending --> Expired: Hết TTL
    Pending --> Revoked: Hủy enrollment
    Active --> Suspended: Rủi ro / tạm khóa
    Suspended --> Active: Review và re-enable
    Active --> Revoked: Thu hồi
    Active --> Expired: Hết hạn
    Expired --> [*]
    Revoked --> [*]
~~~

| Trạng thái | Ý nghĩa | Có được dùng để xác thực? |
| --- | --- | --- |
| **Pending** | Đã tạo enrollment nhưng chưa hoàn tất proof | Không |
| **Active** | Activation thành công, policy cho phép | Có, theo policy |
| **Suspended** | Tạm ngừng do rủi ro, quản trị hoặc người dùng yêu cầu | Không |
| **Expired** | Hết thời hạn credential hoặc enrollment | Không |
| **Revoked** | Đã thu hồi vĩnh viễn hoặc cần đăng ký lại | Không |
| **Compromised** | Có dấu hiệu lộ/mất quyền kiểm soát | Không; cần incident/recovery |

Không cho phép chuyển từ pending sang active chỉ dựa trên client flag. State transition phải do server quyết định sau khi kiểm tra proof. Với credential có thể phục hồi, việc re-enable cần quy trình xác minh và audit rõ ràng.

## 10. Activation failure, retry và idempotency

Activation có thể thất bại do người dùng nhập sai OTP, browser đóng, authenticator không hỗ trợ, CA từ chối CSR, mạng gián đoạn hoặc token hết hạn.

Thiết kế cần:
- Mỗi enrollment có transaction ID duy nhất.
- Retry không tạo nhiều credential active ngoài ý muốn.
- Giới hạn số lần thử và tốc độ gửi challenge.
- Phân biệt lỗi tạm thời với lỗi vĩnh viễn.
- Không tiết lộ secret hoặc lý do nhạy cảm trong thông báo.
- Cho phép hủy và tạo enrollment mới sau khi kiểm tra principal.
- Tiêu thụ token/challenge atomically.
- Có cleanup cho enrollment pending hết hạn.
- Audit failure reason bằng reason code an toàn.

Ví dụ pseudocode:

~~~text
function activateCredential(request):
    tx = loadEnrollmentTransaction(request.transactionId)
    require(tx.status == "pending")
    require(tx.expiresAt > serverNow())
    require(tx.principalId == authenticatedPrincipal())
    require(tx.credentialType == request.credentialType)

    proof = verifyCredentialProof(request, tx.challenge)
    require(proof.valid)

    beginTransaction()
      consumeChallengeOnce(tx.id)
      ensureCredentialNotConflicting(proof.credentialId, tx.principalId)
      saveCredential(tx.principalId, proof.publicMaterial, status="active")
      markEnrollmentCompleted(tx.id)
      appendAuditEvent("credential_activated", tx.id)
    commitTransaction()

    notifyPrincipal(tx.principalId)
~~~

Pseudocode chỉ mô tả nguyên tắc. Production cần xử lý concurrency, rollback, outbox/notification delivery, key management và thư viện kiểm chứng theo từng giao thức.

### 10.1. Partial failure

Nếu credential đã được lưu active nhưng gửi notification thất bại, không nên tạo credential thứ hai khi retry. Dùng transactional outbox hoặc trạng thái notification riêng để retry gửi thông báo mà không lặp activation.

Nếu enrollment thất bại sau khi CA đã cấp certificate nhưng trước khi thiết bị cài đặt, cần quy trình revoke/cleanup hoặc tiếp tục transaction theo trạng thái. Không để certificate mồ côi tồn tại vô thời hạn.

## 11. Activation và account recovery

Activation và recovery có quan hệ chặt chẽ vì credential mới có thể trở thành con đường duy nhất để lấy lại tài khoản.

Các nguyên tắc:
- Yêu cầu bằng chứng đủ mạnh trước khi thêm credential recovery.
- Thông báo qua kênh đã đăng ký trước đó khi có credential mới.
- Có thể áp dụng delay hoặc giới hạn hành động nhạy cảm sau activation tùy rủi ro.
- Không cho phép email/phone vừa thêm trong session đáng ngờ làm bằng chứng duy nhất cho recovery.
- Cho phép người dùng báo cáo credential được thêm trái phép.
- Thu hồi credential mới và session liên quan khi xác định activation gian lận.
- Lưu lịch sử credential để điều tra và tránh tái sử dụng identifier sai cách.

Nếu người dùng mất toàn bộ credential, recovery cần quy trình identity proofing phù hợp. Không bypass activation policy chỉ vì support agent muốn giúp người dùng đăng nhập nhanh.

## 12. Notification và audit

Sau khi credential được kích hoạt, người dùng nên được thông báo về loại credential, thời điểm và thiết bị/đặc điểm đủ nhận diện mà không tiết lộ bí mật.

Notification có thể bao gồm:
- Credential type vừa được thêm.
- Tên thiết bị hoặc label do người dùng đặt.
- Thời điểm và vị trí ước lượng nếu policy cho phép, kèm lưu ý rằng vị trí có thể không chính xác.
- Hướng dẫn nếu người dùng không thực hiện.
- Cách revoke credential hoặc liên hệ support qua domain chính thức.

Không gửi private key, TOTP seed, recovery code hoặc activation token trong notification. Tránh link hành động nhạy cảm không được bảo vệ; nếu có nút revoke, cần xác thực lại và kiểm tra anti-CSRF.

Audit event nên ghi:
- Principal reference và credential ID nội bộ.
- Loại credential và enrollment transaction ID.
- Nguồn yêu cầu, issuer/tenant/device context phù hợp.
- Thời điểm tạo, kích hoạt hoặc thất bại.
- Phương thức proof và policy decision.
- Actor/service đã thực hiện.
- Kết quả và reason code.

Không log password, activation token, private key, TOTP seed, recovery code, full certificate private material hoặc session cookie. Dùng masking, access control và retention phù hợp.

## 13. Threat model cho credential activation

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Activation link theft** | Attacker lấy link qua email, browser history hoặc log | TTL ngắn, one-time, referrer policy và transaction binding |
| **Wrong-account binding** | Credential của attacker được gắn vào principal nạn nhân | Principal server-side, reauthentication và proofing |
| **Activation replay** | Dùng lại token/challenge đã tiêu thụ | Atomic consume, nonce và expiry |
| **Phishing** | Người dùng bị dụ nhập secret hoặc hoàn tất ceremony trên domain giả | Passkey origin binding, domain rõ và training |
| **MFA fatigue** | Người dùng chấp thuận push enrollment/request không chủ động | Number matching, rate limit và hiển thị context |
| **QR/seed leakage** | TOTP QR hoặc secret bị chụp/lưu trong log | TLS, short-lived enrollment, no-store và redaction |
| **Credential collision** | Credential ID/key bị gắn vào nhiều principal trái policy | Uniqueness check và transaction |
| **Race condition** | Nhiều request đồng thời kích hoạt cùng transaction | Database transaction và conditional state transition |
| **Device substitution** | Certificate/token được cài lên thiết bị khác | Device binding, key attestation/management theo policy |
| **Insider activation** | Admin kích hoạt credential cho người không đúng | Separation of duties, approval và audit |
| **Recovery takeover** | Credential mới tạo ra đường recovery yếu | Re-proofing, notification và delay/step-up |
| **Stale pending enrollment** | Enrollment cũ vẫn có thể hoàn tất sau khi account thay đổi | TTL, revoke pending transaction và state check |

## 14. Ví dụ: kích hoạt passkey cho nhân viên mới

Một nhân viên mới đã được HR xác nhận và account đã được tạo ở trạng thái scheduled. Tới ngày bắt đầu, người dùng mở invitation để thiết lập passkey.

Flow:

1. Identity platform kiểm tra joiner transaction vẫn hợp lệ, đúng principal và đã tới start date.
2. Người dùng hoàn tất bước xác minh onboarding theo policy.
3. Server tạo WebAuthn challenge, gắn với subject ID, RP ID và enrollment transaction.
4. Browser gọi authenticator để tạo passkey.
5. Authenticator tạo private key trong môi trường bảo vệ và trả public credential data.
6. Server xác minh challenge, origin, RP ID hash, credential ID và user verification.
7. Server kiểm tra credential chưa được gắn với principal khác theo uniqueness policy.
8. Transaction được tiêu thụ một lần; passkey chuyển sang active.
9. Account được kích hoạt nếu các điều kiện khác như start date, approval và MFA policy đều đạt.
10. Người dùng nhận thông báo passkey đã được thêm và có thể dùng nó cho lần đăng nhập tiếp theo.

Nếu browser đóng sau khi authenticator tạo key nhưng trước khi server nhận response, enrollment có thể ở pending hoặc failed. Người dùng có thể bắt đầu transaction mới; không được tự suy ra credential active chỉ vì thiết bị đã hiển thị thành công.

~~~mermaid
sequenceDiagram
    participant U as Nhân viên
    participant W as Browser
    participant RP as Identity Service
    participant A as Authenticator
    U->>W: Mở invitation
    W->>RP: Xác nhận enrollment transaction
    RP->>RP: Kiểm tra principal, start date và policy
    RP-->>W: WebAuthn challenge + RP options
    W->>A: Tạo passkey
    A-->>W: Public credential response
    W->>RP: Gửi registration response
    RP->>RP: Verify origin, RP ID, challenge và UV
    RP->>RP: Consume transaction và lưu public key
    RP-->>W: Credential active
    RP-->>U: Thông báo bảo mật
~~~

## 15. Kiểm thử credential activation

| Test case | Kết quả mong đợi |
| --- | --- |
| Activation token hợp lệ, đúng principal | Cho phép tiếp tục enrollment |
| Token hết hạn | Từ chối và yêu cầu transaction mới |
| Token đã sử dụng | Không kích hoạt lần hai |
| Token bị sửa hoặc đoán | Từ chối, rate limit và audit |
| Token của principal A dùng trong session B | Từ chối |
| Tenant hoặc credential type không khớp | Từ chối |
| Hai request activation đồng thời | Chỉ một transaction hoàn tất |
| Passkey challenge sai | Từ chối registration |
| WebAuthn origin/RP ID sai | Từ chối |
| Credential ID đã gắn account khác | Từ chối hoặc review theo policy |
| User verification bắt buộc nhưng không có | Không active |
| TOTP code sai hoặc hết time window | Không active |
| TOTP secret đã hiển thị nhưng chưa xác nhận | Vẫn pending |
| Certificate không có proof of possession | Không active |
| Certificate hết hạn hoặc issuer không tin | Từ chối |
| Notification thất bại sau activation | Retry notification, không tạo credential trùng |
| Account bị suspend trong lúc enrollment | Từ chối activation |
| Invitation bị revoke | Transaction pending không thể hoàn tất |
| Recovery sau credential activation | Áp dụng proofing và policy riêng |
| Audit event | Không chứa password, token, seed hoặc private key |

## 16. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Principal được xác định từ nguồn tin cậy? | Không nhận owner từ client |
| Activation có transaction riêng? | ID, TTL, trạng thái và purpose rõ |
| Token/challenge có entropy cao? | CSPRNG, expiry và one-time |
| Kênh phân phối có phù hợp rủi ro? | Recipient binding và bằng chứng độc lập khi cần |
| Có reauthentication trước khi thêm credential? | Session hiện tại đáp ứng policy |
| Proof of possession được kiểm tra? | Passkey assertion/registration, TOTP code hoặc certificate proof |
| WebAuthn được xác minh đầy đủ? | Challenge, origin, RP ID, signature và UV theo policy |
| Private key có được bảo vệ? | Không gửi hoặc lưu ở server nếu key thuộc authenticator |
| TOTP seed có được bảo vệ? | Mã hóa, key management và redaction log |
| Credential state có rõ? | Pending không được dùng; active chỉ sau proof |
| Chống replay và race? | Atomic consume, uniqueness và transaction |
| Failure/retry có idempotent? | Không tạo credential trùng |
| Recovery có được đánh giá? | Credential mới không trở thành bypass |
| Có notification và audit? | Người dùng được cảnh báo, log không chứa secret |
| Có revoke/cleanup? | Pending hết hạn và credential compromise được xử lý |
| Có test negative cases? | Wrong principal, wrong origin, expired, replay và concurrent request |

### Tình huống tự kiểm tra

**Tình huống 1:** Server đã tạo bản ghi passkey pending. Có thể cho phép đăng nhập bằng credential đó chưa?

**Trả lời:** Chưa. Server phải xác minh registration response, challenge, origin, RP ID và các điều kiện policy rồi mới chuyển sang active.

**Tình huống 2:** Người dùng quét QR TOTP nhưng chưa nhập mã xác nhận. Factor có nên active không?

**Trả lời:** Không. QR chỉ phân phối secret; server cần xác minh mã hợp lệ để chứng minh authenticator đã được thiết lập đúng.

**Tình huống 3:** Activation link của nhân viên A được mở trong session của nhân viên B. Có thể kích hoạt credential cho A không?

**Trả lời:** Chỉ khi transaction và proofing policy xác minh đúng người nhận; không dựa vào session B hoặc dữ liệu principal do browser gửi. Nếu không chứng minh được binding, phải từ chối.

**Tình huống 4:** Certificate đã được CA ký nhưng private key không nằm trên thiết bị dự kiến. Credential có active không?

**Trả lời:** Không nên. Certificate issuance chưa chứng minh thiết bị giữ private key tương ứng; cần proof of possession và device binding.

**Tình huống 5:** Hai request cùng gửi activation token gần như đồng thời. Cả hai có thể active credential không?

**Trả lời:** Không. State transition và consume token phải nguyên tử; chỉ một request được hoàn tất.

**Tình huống 6:** Notification gửi email thất bại sau khi credential đã active. Có nên rollback rồi tạo credential khác khi retry không?

**Trả lời:** Không mặc nhiên. Activation và notification cần trạng thái riêng; retry notification không được lặp việc tạo credential.

## 17. Ghi nhớ

**Credential activation là bước xác minh và mở trạng thái sử dụng của credential sau khi nó được cấp hoặc enrollment.** Nó phải gắn credential với đúng principal, kiểm tra proof of control, bảo vệ activation token/challenge và chỉ chuyển sang active sau khi server xác minh toàn bộ điều kiện.

Mỗi loại credential có ceremony riêng: password cần thiết lập verifier an toàn; passkey cần WebAuthn registration validation; TOTP cần xác nhận mã; certificate cần proof of possession và trust chain; thiết bị cần binding với owner. Dùng trạng thái rõ ràng, one-time transaction, idempotency, recovery, notification và audit để ngăn credential bị kích hoạt nhầm hoặc bị chiếm quyền ngay từ bước đầu.
