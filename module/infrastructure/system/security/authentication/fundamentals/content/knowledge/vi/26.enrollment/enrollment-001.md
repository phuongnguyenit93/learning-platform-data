# Authenticator enrollment: đăng ký và quản lý phương thức xác thực

> **Chương:** Enrollment  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào vòng đời đăng ký authenticator: xác minh người yêu cầu, liên kết authenticator với đúng tài khoản, kiểm tra bằng chứng đăng ký, quản lý recovery và thu hồi phương thức đã mất hoặc không còn tin cậy.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích authenticator enrollment và phân biệt đăng ký phương thức mới với đăng nhập bằng phương thức đã đăng ký.
2. Mô hình hóa các ranh giới tin cậy khi một tài khoản thêm passkey, khóa bảo mật, TOTP hoặc phương thức dự phòng.
3. Thiết kế bootstrap và step-up để ngăn attacker đã chiếm một phiên yếu tự đăng ký authenticator của họ.
4. Mô tả WebAuthn registration ceremony và các kiểm tra server phải thực hiện trước khi lưu credential.
5. Thiết kế TOTP enrollment an toàn, bảo vệ shared secret và xác minh mã trước khi kích hoạt.
6. Quản lý recovery codes, thông báo, thiết bị, đổi tên, thu hồi và xóa authenticator.
7. Ngăn enrollment hijacking, CSRF, replay, race condition, account recovery abuse và lockout.
8. Triển khai enrollment flow trong Java/Spring bằng thư viện xác thực đã được kiểm chứng và xây dựng ma trận kiểm thử.

## 2. Authenticator enrollment là gì?

**Authenticator enrollment** là quy trình liên kết một authenticator mới với một tài khoản đã được xác định. Sau khi enrollment hoàn tất, hệ thống có thể chấp nhận bằng chứng từ authenticator đó trong các lần xác thực tiếp theo.

Authenticator có thể là:

- **Passkey/WebAuthn credential:** cặp khóa mật mã gắn với relying party; private key được giữ bởi authenticator, public key được server lưu.
- **Security key:** thiết bị FIDO2/WebAuthn như khóa USB/NFC/Bluetooth.
- **TOTP authenticator:** ứng dụng tạo mã dựa trên shared secret và thời gian.
- **Push authenticator:** ứng dụng đã đăng ký nhận và phản hồi challenge.
- **Client certificate:** chứng chỉ và private key được provision cho user/device theo mô hình PKI.
- **Recovery code:** bằng chứng dự phòng dùng khi mất phương thức chính; thường là mã dùng một lần, không nên xem là authenticator chính tương đương passkey.

Enrollment khác login:

| Hoạt động | Mục tiêu | Bằng chứng chính |
|---|---|---|
| **Enrollment** | Liên kết authenticator mới với account | Phiên hiện tại đủ tin cậy và bằng chứng sở hữu authenticator mới |
| **Authentication** | Xác minh người dùng đang kiểm soát authenticator đã đăng ký | Assertion/OTP/challenge hợp lệ |
| **Re-authentication** | Xác minh lại gần thời điểm thao tác | Authenticator hiện có, theo freshness policy |
| **Recovery** | Khôi phục quyền truy cập khi mất authenticator | Bằng chứng recovery theo assurance policy |
| **Removal/revocation** | Ngừng tin cậy authenticator | Xác thực lại, policy kiểm soát và cập nhật trạng thái server |

Enrollment là thao tác bảo mật nhạy cảm. Nếu attacker đã chiếm một phiên đăng nhập yếu và có thể tự thêm authenticator, họ có thể duy trì quyền truy cập ngay cả khi chủ tài khoản đổi mật khẩu hoặc đăng xuất các phiên khác.

## 3. Mô hình tin cậy của enrollment

Enrollment có hai câu hỏi khác nhau:

1. **Ai đang yêu cầu đăng ký?** Hệ thống phải xác định account và mức tin cậy của phiên hiện tại.
2. **Authenticator mới có thực sự được tạo và kiểm soát trong giao dịch này không?** Server phải xác minh challenge/response theo giao thức.

~~~mermaid
flowchart TD
    U["User / existing account"] --> S["Authenticated session"]
    S --> R["Re-authentication / step-up policy"]
    R --> P{"Session đủ tin cậy?"}
    P -->|"No"| X["Deny hoặc recovery flow"]
    P -->|"Yes"| C["Create one-time enrollment challenge"]
    C --> A["New authenticator"]
    A --> V["Server verifies registration proof"]
    V --> Q{"Proof hợp lệ và đúng account?"}
    Q -->|"No"| X
    Q -->|"Yes"| D["Persist credential as pending/active"]
    D --> N["Notify account owner"]
    N --> E["Audit and monitor"]
~~~

Ranh giới tin cậy:

- Browser/app là môi trường phía client; không tin user ID, credential ID hoặc trạng thái enrollment do client tự khai.
- Session hiện tại phải được xác minh ở server và gắn với account đúng.
- Challenge phải do server tạo, có entropy, hết hạn và chỉ dùng một lần.
- Authenticator verifier phải kiểm tra phản hồi theo chuẩn giao thức.
- Credential store phải lưu public key hoặc secret đã bảo vệ cùng metadata cần thiết.
- Thông báo và audit phải giúp phát hiện enrollment trái phép.

## 4. Xác minh người yêu cầu trước khi thêm authenticator

Không nên cho phép bất kỳ phiên đăng nhập nào cũng tự thêm authenticator mới. Đặc biệt, một phiên vừa được khôi phục bằng email hoặc vừa đăng nhập bằng mật khẩu có thể chưa đủ assurance để thay đổi gốc tin cậy của tài khoản.

Các kiểm soát thường dùng:

- Yêu cầu xác thực lại bằng authenticator hiện có, nhất là khi thêm passkey/khóa bảo mật hoặc thay đổi phương thức recovery.
- Kiểm tra thời điểm xác thực gần nhất (freshness) và mức assurance của phiên.
- Với tài khoản đặc quyền, yêu cầu phương thức chống phishing hoặc phê duyệt bổ sung theo policy.
- Nếu user vừa recovery, vừa đổi mật khẩu hoặc có tín hiệu compromise, áp dụng delay/hold hoặc hạn chế enrollment.
- Ràng buộc thao tác với đúng session, principal, account và mục đích enrollment.
- Yêu cầu CSRF protection nếu browser dùng cookie tự động gửi.

Nếu đây là lần enrollment đầu tiên của tài khoản mới, hệ thống cần bootstrap trust bằng quy trình tạo tài khoản đã xác minh, invitation có ràng buộc, danh tính được kiểm tra hoặc quy trình provisioning đáng tin cậy. Không thể dùng một authenticator chưa đăng ký để tự chứng minh rằng nó thuộc về đúng người.

### Vì sao email/SMS không nên là bằng chứng duy nhất cho enrollment mạnh?

Email hoặc SMS có thể hữu ích trong bootstrap hoặc recovery theo mô hình rủi ro, nhưng chúng có thể bị chiếm qua email takeover, SIM swap, chuyển tiếp mã, phishing hoặc quy trình nhà mạng. Nếu một attacker kiểm soát email yếu có thể thêm passkey mới, mọi bảo vệ mạnh hơn phía sau có thể bị vô hiệu hóa.

Chọn phương thức enrollment dựa trên assurance của tài khoản và tác động nếu authenticator bị gắn nhầm. Với admin hoặc tài khoản có dữ liệu nhạy cảm, cần quy trình bootstrap và recovery mạnh hơn.

## 5. Vòng đời enrollment

Một flow hoàn chỉnh thường gồm:

1. **Start:** user mở trang quản lý bảo mật và chọn loại authenticator.
2. **Authorize:** server xác minh session, quyền thay đổi credential, freshness, step-up và CSRF.
3. **Challenge:** server tạo challenge ngẫu nhiên, gắn với account/session/type và deadline.
4. **Register:** browser/app giao tiếp với authenticator để tạo credential hoặc lấy shared secret theo giao thức.
5. **Verify:** server kiểm tra response, challenge, origin/RP ID, chữ ký/attestation hoặc mã OTP.
6. **Persist:** lưu credential record với trạng thái, owner, metadata và thời điểm tạo.
7. **Activate:** chỉ đánh dấu active sau khi bằng chứng đăng ký hợp lệ; với TOTP, phải xác minh mã đầu tiên trước khi kích hoạt.
8. **Notify:** thông báo qua kênh đã xác minh và hiển thị thời điểm/thiết bị vừa thêm.
9. **Audit:** ghi sự kiện enrollment, loại phương thức, kết quả và session/device context cần thiết.
10. **Maintain:** cho phép xem, đổi tên, thu hồi, recovery và kiểm tra phương thức còn hoạt động.

Không lưu authenticator ở trạng thái active chỉ vì client gửi yêu cầu bắt đầu enrollment. Chỉ bằng chứng đã được xác minh mới hoàn tất liên kết.

## 6. WebAuthn/passkey registration ceremony

WebAuthn đăng ký một public-key credential gắn với relying party. Trong registration, authenticator tạo credential key pair; private key được giữ ở authenticator và public key được gửi về server để lưu.

### Các bước chính

1. User đã xác thực vào RP và được phép thêm authenticator.
2. Server tạo challenge ngẫu nhiên, lưu trạng thái pending với account, session, RP và thời hạn.
3. Server gửi PublicKeyCredentialCreationOptions tới browser, gồm challenge, rp, user, algorithms, timeout và authenticator selection policy.
4. Browser gọi WebAuthn API; authenticator tạo credential và trả attestation object cùng client data.
5. Browser gửi response tới server.
6. Server xác minh challenge, origin, RP ID hash, type, flags, attestation theo policy, credential ID và public key.
7. Server lưu credential ID, public key, user handle, sign counter/backup metadata nếu áp dụng và thời điểm đăng ký.
8. Server đánh dấu enrollment hoàn tất và thông báo cho user.

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant RP as Relying Party server
    participant Auth as Authenticator

    User->>RP: Start add passkey (authenticated session)
    RP->>RP: Step-up + create challenge bound to account/session
    RP-->>Browser: PublicKeyCredentialCreationOptions
    Browser->>Auth: create(options)
    Auth-->>Browser: Credential + attestation response
    Browser->>RP: Registration response
    RP->>RP: Verify challenge, origin, RP ID, type and attestation policy
    RP->>RP: Store credential public key and metadata
    RP-->>User: Enrollment complete + notification
~~~

### Những gì server phải xác minh

- **Challenge:** khớp challenge đang chờ của đúng account/session, chưa hết hạn và chưa dùng.
- **Type:** client data type phải là webauthn.create.
- **Origin:** đúng origin được RP cho phép, bao gồm scheme/host/port theo quy tắc.
- **RP ID hash:** khớp RP ID đã cấu hình.
- **Credential ID:** hợp lệ, không trùng hoặc gắn sai user.
- **Attestation object:** parse và xác minh theo policy; nếu yêu cầu attestation, kiểm tra chain/format phù hợp.
- **Public key:** lấy từ authenticator data và lưu theo định dạng chuẩn.
- **User presence / user verification:** kiểm tra các flags theo yêu cầu RP; không mặc định mọi registration đều đã có user verification mạnh.
- **Algorithm:** chỉ chấp nhận thuật toán/curve được cấu hình và hỗ trợ.
- **Challenge lifecycle:** response không được replay trong enrollment khác hoặc account khác.

Không tự viết parser hoặc chữ ký WebAuthn. Dùng thư viện server-side được duy trì và kiểm thử theo WebAuthn conformance.

### Attestation và quyền riêng tư

Attestation có thể cung cấp bằng chứng về loại authenticator hoặc nguồn gốc thiết bị theo format và trust model. Tuy nhiên, yêu cầu attestation quá chi tiết có thể tạo khả năng fingerprint người dùng hoặc làm giảm khả năng tương thích.

RP nên chọn policy:

- Không yêu cầu attestation khi use case không cần xác minh model/vendor.
- Dùng attestation phù hợp khi quản lý thiết bị doanh nghiệp hoặc yêu cầu assurance cụ thể.
- Xác định metadata/roots tin cậy và cách cập nhật.
- Tránh lưu dữ liệu thiết bị dư thừa hoặc dùng attestation như bằng chứng duy nhất về danh tính con người.

### Discoverable credential và user verification

Passkey có thể là discoverable credential để authenticator chọn account mà không cần user nhập username trước. User verification (UV) có thể dùng PIN hoặc sinh trắc học cục bộ của authenticator để xác nhận user đang kiểm soát thiết bị.

RP cần đặt authenticator selection và userVerification requirement theo use case. UV là thao tác xác minh cục bộ trên authenticator; server không nhận dữ liệu sinh trắc học thô.

## 7. TOTP enrollment

TOTP tạo mã ngắn hạn dựa trên shared secret và thời gian. Khác WebAuthn, TOTP enrollment phải chuyển shared secret tới ứng dụng authenticator, thường qua QR code hoặc URI provisioning.

### Quy trình

1. User đã vượt qua step-up policy.
2. Server tạo shared secret ngẫu nhiên bằng CSPRNG.
3. Server lưu secret ở trạng thái pending, được mã hóa bằng cơ chế bảo vệ khóa phù hợp.
4. Server hiển thị QR code/URI provisioning qua kênh TLS; chỉ hiển thị trong phiên enrollment.
5. User quét QR bằng authenticator app.
6. User nhập mã TOTP đầu tiên.
7. Server xác minh mã theo time window policy, chống replay theo yêu cầu.
8. Sau khi hợp lệ, server chuyển secret sang trạng thái active và thông báo.

Ví dụ URI provisioning có dạng:

~~~text
otpauth://totp/Example:an@example.test?secret=BASE32_SECRET&issuer=Example&algorithm=SHA1&digits=6&period=30
~~~

Đây là chuỗi mẫu, không phải secret sử dụng thật. QR code chứa shared secret tương đương thông tin bí mật; ai chụp hoặc lấy được QR có thể tạo mã trong tương lai. Không ghi URI/QR hoặc secret vào log, analytics, screenshot hay ticket.

### Bảo vệ TOTP seed

- Sinh secret ngẫu nhiên với độ dài phù hợp thư viện/chuẩn.
- Mã hóa khi lưu bằng khóa được quản lý riêng; giới hạn quyền giải mã.
- Không lưu seed dạng plaintext trong log hoặc database nếu có thể bảo vệ bằng envelope encryption.
- Chỉ hiển thị QR trong luồng enrollment có TLS và session đủ tin cậy.
- Không để seed pending tồn tại vô thời hạn; hết hạn thì hủy.
- Không cho phép nhiều request đồng thời tạo seed mới rồi kích hoạt nhầm seed.
- Khi xóa authenticator, hủy seed và bản sao/cache theo chính sách.

### Time window và replay

TOTP verifier có thể chấp nhận một cửa sổ thời gian nhỏ để bù lệch đồng hồ. Cửa sổ càng rộng, thời gian mã có thể được chấp nhận càng dài. Chọn skew hợp lý và giới hạn số lần thử.

Một mã hợp lệ không nên được dùng lại để hoàn tất nhiều lần enrollment hoặc xác thực trong cùng time step nếu policy chống replay yêu cầu. Có thể lưu time step đã chấp nhận gần nhất cho credential để ngăn replay, tùy cách triển khai TOTP.

## 8. Push authenticator và thiết bị di động

Push enrollment thường yêu cầu ứng dụng di động tạo hoặc nhận diện một device credential, đăng ký public key/device binding hoặc token push. Push notification chỉ là kênh thông báo; việc nhận push không tự chứng minh người dùng đã xác thực.

Một flow an toàn cần:

- Step-up trước khi liên kết thiết bị mới.
- Challenge một lần gắn với account, device registration và giao dịch.
- Xác minh proof-of-possession của private key/device credential nếu thiết kế dùng khóa.
- Ràng buộc push approval với phiên, request và nội dung cần xác nhận.
- Chống push bombing bằng rate limit, number matching/context và cơ chế từ chối.
- Không coi push token/APNs/FCM device token là authenticator secret đủ mạnh.
- Hỗ trợ thu hồi thiết bị bị mất và xoay khóa khi cần.

Nếu ứng dụng mobile lưu private key, cần dùng secure hardware/keystore phù hợp nền tảng khi có thể; không hardcode khóa trong binary hoặc chỉ dựa vào obfuscation.

## 9. Enrollment recovery codes

Recovery codes giúp người dùng truy cập khi mất authenticator chính. Chúng là phương thức dự phòng có thể mang rủi ro cao vì thường là bearer secret.

Quy trình cấp:

1. Yêu cầu xác thực đủ mạnh hoặc recovery policy được phê duyệt.
2. Sinh một tập mã ngẫu nhiên với entropy đủ lớn.
3. Hiển thị một lần và yêu cầu người dùng lưu ở nơi an toàn.
4. Chỉ lưu verifier/hash của từng mã, không lưu plaintext để đọc lại.
5. Đánh dấu từng mã đã dùng và không cho dùng lại.
6. Khi tạo lại bộ mã, vô hiệu toàn bộ mã cũ.
7. Thông báo khi recovery code được dùng hoặc bộ mã được tạo lại.

Không gửi recovery code qua email hoặc chat. Không log mã trong audit. Không dùng recovery code để âm thầm thêm authenticator mới mà không áp dụng step-up/recovery policy tương ứng.

## 10. Enrollment hijacking và các đường tấn công

### 10.1. Attacker đã chiếm phiên yếu

Attacker lấy mật khẩu hoặc cookie phiên yếu, sau đó mở trang bảo mật và đăng ký passkey của chính họ. Từ đây, attacker có thể quay lại bằng passkey ngay cả khi nạn nhân đổi mật khẩu.

Kiểm soát:

- Re-authentication bằng phương thức hiện có.
- MFA/step-up mạnh cho enrollment.
- Notification tới kênh đã xác minh.
- Delay hoặc hold nếu tài khoản vừa recovery hoặc có risk signals.
- Hiển thị danh sách authenticator và lịch sử enrollment để user phát hiện.

### 10.2. CSRF enrollment

Nếu endpoint enrollment dùng cookie session tự động gửi và không có CSRF protection, website độc hại có thể cố gắng kích hoạt thao tác thay đổi trạng thái dưới phiên của user.

Kiểm soát:

- CSRF token hoặc cơ chế chống CSRF phù hợp framework.
- SameSite cookie theo luồng ứng dụng.
- Kiểm tra Origin/Referer khi phù hợp.
- Challenge được tạo và xác minh ở server, không chấp nhận dữ liệu client tự dựng.
- Endpoint kích hoạt enrollment không dùng GET và không thay đổi trạng thái khi chỉ tải trang.

### 10.3. Challenge replay hoặc cross-account binding

Nếu challenge không gắn với account/session, attacker có thể gửi response của mình trong phiên hoặc tài khoản khác.

Kiểm soát:

- Challenge ngẫu nhiên, có hạn dùng, một lần.
- Lưu quan hệ challenge → account → session → loại authenticator.
- Tiêu thụ challenge theo thao tác nguyên tử sau khi verify.
- Không cho phép response của challenge đã hoàn tất được dùng lại.

### 10.4. Race condition

Hai request cùng hoàn tất enrollment hoặc một request remove chạy đồng thời với một request login có thể tạo trạng thái không nhất quán.

Kiểm soát:

- Giao dịch DB và unique constraint cho credential ID.
- Optimistic locking/version trên account authenticator set.
- Challenge chỉ chuyển trạng thái pending → consumed một lần.
- Kiểm tra trạng thái account và authenticator trong cùng giao dịch phù hợp.
- Audit sự kiện xung đột và không tự khôi phục trạng thái active từ request cũ.

### 10.5. Account recovery abuse

Attacker có thể dùng recovery yếu để reset MFA rồi đăng ký authenticator của họ. Recovery phải có assurance tương xứng và có giám sát; nếu không, MFA enrollment trở thành điểm bypass của toàn bộ hệ thống.

## 11. Quản lý nhiều authenticator

Người dùng có thể đăng ký nhiều passkey/khóa bảo mật và một số phương thức dự phòng. UI quản lý nên hiển thị:

- Tên do user đặt, loại authenticator và thời điểm đăng ký.
- Thời điểm sử dụng gần nhất nếu có dữ liệu đáng tin.
- Trạng thái active, pending, revoked hoặc expired.
- Thiết bị/metadata ở mức tối thiểu cần thiết.
- Cách thu hồi từng phương thức và hậu quả nếu đó là phương thức cuối cùng.

Không hiển thị credential secret hoặc private key. Với WebAuthn, credential ID có thể được dùng làm định danh kỹ thuật nhưng vẫn cần bảo vệ theo chính sách dữ liệu.

### Đổi tên thiết bị

Đổi tên thiết bị chủ yếu là thay đổi metadata. Vẫn cần xác thực session và kiểm tra account ownership; tên thiết bị do user nhập phải được escape khi hiển thị và giới hạn độ dài.

### Xóa authenticator

- Yêu cầu xác thực lại/step-up theo mức nhạy cảm.
- Kiểm tra còn phương thức thay thế hoặc recovery hợp lệ.
- Nếu xóa phương thức cuối cùng, yêu cầu quy trình recovery/enrollment khác hoặc từ chối theo policy.
- Đánh dấu revoked ở server ngay; không chỉ xóa khỏi UI/browser.
- Với TOTP, hủy seed; với WebAuthn, đánh dấu credential không còn được chấp nhận.
- Thông báo qua kênh liên hệ đã xác minh và ghi audit.

## 12. Thiết kế trạng thái credential

Không nên chỉ có boolean enrolled. Một credential có thể trải qua nhiều trạng thái:

| Trạng thái | Ý nghĩa | Được dùng đăng nhập? |
|---|---|---|
| pending | Đã bắt đầu enrollment nhưng chưa xác minh xong | Không |
| active | Bằng chứng hợp lệ, liên kết với account | Có, theo policy |
| suspended | Tạm ngừng do risk/incident hoặc yêu cầu quản trị | Không |
| revoked | Đã thu hồi; không còn được chấp nhận | Không |
| expired | Hết hạn theo policy hoặc chứng chỉ | Không |
| replaced | Đã thay bằng credential mới | Không |

Chuyển trạng thái phải được thực hiện phía server với kiểm soát concurrency. Không tin trạng thái do browser gửi lên.

~~~mermaid
stateDiagram-v2
    [*] --> pending
    pending --> active: proof verified
    pending --> revoked: cancel or expire
    active --> suspended: risk / incident
    active --> revoked: user or admin removal
    active --> replaced: new credential replaces old
    suspended --> active: reviewed and restored
    suspended --> revoked: confirmed compromise
    replaced --> [*]
    revoked --> [*]
~~~

## 13. Lưu trữ và bảo vệ credential record

Một bản ghi authenticator có thể gồm:

| Trường | Ví dụ/ý nghĩa |
|---|---|
| credential_id | Định danh credential do giao thức cấp |
| account_id | Account sở hữu credential |
| type | webauthn, totp, push, certificate |
| status | pending, active, suspended, revoked |
| public_key | Public key với WebAuthn nếu có |
| encrypted_secret | TOTP seed đã mã hóa nếu có |
| created_at | Thời điểm enrollment |
| last_used_at | Lần sử dụng gần nhất nếu được ghi nhận |
| display_name | Tên thiết bị do user đặt |
| authenticator_metadata | AAGUID/backup flags/metadata cần thiết theo policy |
| revoked_at | Thời điểm thu hồi |

Nguyên tắc:

- Không lưu private key WebAuthn của user; server chỉ lưu public key.
- TOTP seed phải được mã hóa và giới hạn quyền giải mã.
- Không lưu recovery code plaintext; chỉ lưu verifier/hash.
- Bảo vệ credential store bằng quyền truy cập tối thiểu, audit và backup.
- Không log public key/credential metadata quá mức nếu không cần; không bao giờ log secret.
- Dùng unique constraint phù hợp để tránh credential ID bị gắn cho nhiều account.
- Có quy trình backup/restore không làm sống lại credential đã revoked.

## 14. Thông báo và audit enrollment

Sau khi thêm, xóa hoặc thay đổi authenticator, người dùng nên nhận thông báo qua kênh liên hệ đã xác minh. Thông báo nên bao gồm:

- Loại thao tác: authenticator mới được thêm, bị xóa hoặc bị thu hồi.
- Thời gian và ứng dụng/account liên quan.
- Tên thiết bị do user đặt hoặc mô tả tối thiểu nếu có.
- Hướng dẫn báo cáo nếu user không thực hiện.
- Liên kết tới trang quản lý bảo mật; không đưa secret hoặc token vào link.

Audit event nên ghi:

- account/principal nội bộ.
- loại authenticator và trạng thái trước/sau.
- thời gian, session ID/correlation ID và actor.
- kết quả, reason code, policy version và nguồn request cần thiết.
- dấu hiệu risk được dùng ở mức tối thiểu.

Không ghi TOTP seed, QR provisioning URI, OTP, recovery code, private key, access token hoặc cookie session.

Thông báo là cơ chế phát hiện và phản ứng; nó không thay thế xác minh enrollment. Nếu người dùng báo thao tác lạ, cần quy trình revoke session/credential và điều tra.

## 15. Java/Spring: tổ chức enrollment service

Ví dụ sau minh họa một service điều phối enrollment WebAuthn. Các thành phần giao thức phải được thực hiện bởi thư viện WebAuthn server-side đã được kiểm chứng; không tự triển khai crypto hoặc parser.

~~~java
enum EnrollmentStatus {
    PENDING,
    ACTIVE,
    REVOKED,
    EXPIRED
}

record EnrollmentStart(
    UUID accountId,
    UUID sessionId,
    String authenticatorType
) {}

record PendingEnrollment(
    UUID challengeId,
    UUID accountId,
    UUID sessionId,
    String challenge,
    Instant expiresAt
) {}

@Service
class AuthenticatorEnrollmentService {
    private final SessionVerifier sessions;
    private final StepUpPolicy stepUpPolicy;
    private final WebAuthnRegistrationService webAuthn;
    private final EnrollmentRepository enrollments;

    AuthenticatorEnrollmentService(
            SessionVerifier sessions,
            StepUpPolicy stepUpPolicy,
            WebAuthnRegistrationService webAuthn,
            EnrollmentRepository enrollments) {
        this.sessions = sessions;
        this.stepUpPolicy = stepUpPolicy;
        this.webAuthn = webAuthn;
        this.enrollments = enrollments;
    }

    RegistrationOptions begin(EnrollmentStart request) {
        AuthenticatedPrincipal principal =
            sessions.requirePrincipal(request.sessionId());

        if (!principal.accountId().equals(request.accountId())) {
            throw new AccessDeniedException("Account mismatch");
        }

        stepUpPolicy.requireRecentStrongAuthentication(principal);

        PendingEnrollment pending =
            enrollments.createPending(
                principal.accountId(),
                request.sessionId(),
                request.authenticatorType()
            );

        return webAuthn.createRegistrationOptions(
            principal.accountId(),
            pending.challenge(),
            pending.expiresAt()
        );
    }
}
~~~

Đây là ví dụ khung. Repository phải lưu challenge và trạng thái pending có TTL, liên kết account/session/type; service phải chống CSRF ở web layer. Hàm createRegistrationOptions cần dùng thư viện WebAuthn để tạo options đúng RP ID/origin/algorithm.

### Xác minh và kích hoạt

~~~java
@Transactional
void complete(
        UUID accountId,
        UUID sessionId,
        UUID challengeId,
        RegistrationResponse response) {

    PendingEnrollment pending =
        enrollments.lockPending(challengeId)
            .orElseThrow(InvalidEnrollmentException::new);

    if (!pending.accountId().equals(accountId)
            || !pending.sessionId().equals(sessionId)
            || pending.expiresAt().isBefore(Instant.now())) {
        throw new InvalidEnrollmentException();
    }

    VerifiedWebAuthnCredential verified =
        webAuthn.verifyRegistration(pending, response);

    enrollments.consumeChallenge(challengeId);
    enrollments.activateCredential(
        accountId,
        verified.credentialId(),
        verified.publicKey(),
        verified.metadata()
    );
    audit.recordEnrollment(accountId, "WEBAUTHN", "ACTIVE");
}
~~~

Mã trên minh họa trình tự; cần bảo đảm consumeChallenge là thao tác nguyên tử, challenge chưa bị dùng, unique credential constraint được áp dụng và toàn bộ thay đổi nằm trong transaction thích hợp. Không gọi hàm verifyRegistration tự viết; thư viện phải kiểm tra challenge, origin, RP ID, attestation và authenticator data theo WebAuthn.

### TOTP activation

Với TOTP, không chuyển trạng thái sang active cho tới khi mã đầu tiên được xác minh:

~~~java
void confirmTotp(UUID accountId, String submittedCode) {
    PendingTotp pending = totpRepository.requirePending(accountId);
    if (!totpVerifier.verify(pending.encryptedSecret(), submittedCode)) {
        throw new InvalidAuthenticatorCodeException();
    }

    totpRepository.activatePending(accountId, pending.id());
    audit.recordEnrollment(accountId, "TOTP", "ACTIVE");
}
~~~

Đoạn mã chỉ là pseudocode ở mức ứng dụng; verifier phải giải mã seed trong vùng tin cậy, áp dụng time window/rate limit/replay policy và không log code/seed. Cần xử lý đồng thời để một pending seed không thể bị thay thế giữa lúc xác minh và kích hoạt.

## 16. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Cho phép enrollment chỉ bằng phiên mật khẩu cũ | Attacker có phiên bị chiếm tự thêm authenticator | Step-up và freshness policy |
| Kích hoạt TOTP ngay khi tạo QR | Seed chưa được chứng minh đã cài đúng | Yêu cầu mã TOTP đầu tiên |
| Tin credential ID do browser gửi | Có thể gắn credential giả hoặc của account khác | Xác minh WebAuthn response ở server |
| Không ràng buộc challenge với account/session | Cross-account binding hoặc replay | Challenge one-time, account/session-bound |
| Không kiểm tra origin/RP ID | Credential có thể được đăng ký từ origin không tin cậy | Verify WebAuthn origin và RP ID hash |
| Lưu TOTP seed plaintext | DB leak làm lộ authenticator | Mã hóa seed và hạn chế giải mã |
| Log QR/OTP/recovery code | Tạo thêm bản sao của bí mật | Redact và không log secret |
| Email là bằng chứng duy nhất để thêm passkey | Email takeover dẫn đến MFA takeover | Bootstrap/recovery assurance phù hợp |
| Không có notification | User khó phát hiện authenticator lạ | Thông báo enrollment/removal |
| Cho xóa authenticator cuối cùng mà không recovery | Tạo lockout hoặc bypass policy | Kiểm tra phương thức thay thế |
| Xóa credential chỉ ở browser | Server vẫn chấp nhận credential cũ | Revoke trong credential store |
| Không xử lý race condition | Credential duplicate hoặc challenge dùng nhiều lần | Transaction, lock và unique constraint |
| Không thu hồi credential downstream sau compromise | Attacker vẫn dùng phiên/token đã tạo | Incident review và revoke liên quan |

## 17. Ma trận kiểm thử authenticator enrollment

| Kiểm thử | Kết quả mong đợi |
|---|---|
| User chưa đăng nhập bắt đầu enrollment | Từ chối |
| Session account A gửi request thêm authenticator cho account B | Từ chối |
| Session quá cũ hoặc thiếu step-up theo policy | Yêu cầu xác thực lại |
| CSRF request thử thêm authenticator bằng cookie | Bị chặn |
| WebAuthn challenge sai/hết hạn/đã dùng | Từ chối |
| WebAuthn origin hoặc RP ID hash sai | Từ chối |
| WebAuthn response có chữ ký/attestation không hợp lệ | Từ chối |
| Credential ID đã gắn với account khác | Từ chối và audit |
| WebAuthn user verification không đạt requirement | Từ chối |
| TOTP QR được tạo nhưng chưa xác minh mã | Credential vẫn pending |
| TOTP code sai hoặc hết time window | Từ chối |
| TOTP code bị replay theo policy | Từ chối |
| TOTP seed pending hết hạn | Hủy pending secret |
| Hai request hoàn tất cùng challenge | Chỉ một request thành công |
| Hai account cùng đăng ký một credential ID | Unique constraint ngăn liên kết trùng |
| Recovery code đã dùng | Từ chối lần dùng tiếp theo |
| Tạo bộ recovery code mới | Bộ cũ bị vô hiệu |
| Xóa authenticator cuối cùng | Yêu cầu recovery/phương thức thay thế hoặc từ chối |
| User vừa recovery rồi thêm passkey | Áp dụng delay/hold/step-up theo policy |
| Notification enrollment | Gửi thông báo không chứa secret |
| Audit enrollment | Có actor, account, type, result; không có OTP/seed/private key |
| Revoke authenticator | Credential bị từ chối ở lần xác thực tiếp theo |
| Backup restore sau revoke | Không làm sống lại credential đã thu hồi |

Kiểm thử bằng authenticator, account và secret giả lập trong môi trường test. Không dùng QR, seed TOTP, passkey credential hoặc recovery code thật của người dùng trong fixture công khai.

## 18. Tình huống phân tích

### Tình huống A: attacker thêm passkey sau khi lấy mật khẩu

An dùng mật khẩu để đăng nhập trên một máy lạ. Attacker đã có mật khẩu và chiếm được session cookie. Ứng dụng cho phép thêm passkey mà không yêu cầu xác thực lại.

**Phân tích:** attacker có thể liên kết passkey của mình và giữ quyền truy cập sau khi mật khẩu được đổi. Cần step-up bằng authenticator hiện có, session rotation, notification, risk checks và quy trình thu hồi mọi phiên/credential không nhận diện.

### Tình huống B: QR TOTP bị ghi vào log

Ứng dụng tạo URI provisioning rồi ghi toàn bộ URI vào debug log để hỗ trợ người dùng.

**Phân tích:** log đã trở thành bản sao của TOTP seed. Cần ngừng ghi log, đánh giá quyền truy cập/retention, thu hồi seed cũ, tạo seed mới và xác minh mã mới trước khi kích hoạt.

### Tình huống C: WebAuthn challenge được dùng lại

Server không đánh dấu challenge đã hoàn tất. Một response registration hợp lệ được gửi hai lần và tạo hai credential record.

**Phân tích:** challenge phải được tiêu thụ nguyên tử một lần và ràng buộc với account/session. Dùng transaction/lock, unique constraint và idempotency policy rõ ràng.

### Tình huống D: user mất authenticator cuối cùng

Người dùng chỉ có một khóa bảo mật và muốn xóa nó vì thiết bị hỏng, nhưng chưa có phương thức thay thế.

**Phân tích:** cần recovery flow có assurance tương xứng. Không cho xóa credential cuối cùng bằng một phiên yếu; sau recovery phải thông báo, kiểm tra rủi ro và đăng ký phương thức mới.

### Tình huống E: email bị chiếm và recovery MFA

Attacker chiếm email của user, dùng link recovery để xóa TOTP rồi đăng ký passkey mới.

**Phân tích:** recovery là một phần của authenticator lifecycle. Cần đánh giá độ mạnh của kênh recovery, yêu cầu bằng chứng bổ sung, delay cho thay đổi bảo mật và cảnh báo qua các kênh đã xác minh khác.

## 19. Quy trình thiết kế và vận hành

Trước khi phát hành enrollment flow, hãy xác định:

1. Loại authenticator nào được hỗ trợ và assurance/giới hạn của từng loại?
2. Ai có thể bắt đầu enrollment; session và step-up yêu cầu mức nào?
3. Bootstrap trust cho account mới dựa trên bằng chứng nào?
4. Challenge được tạo, lưu, gắn account/session, hết hạn và tiêu thụ một lần ra sao?
5. WebAuthn origin, RP ID, attestation và user verification policy được cấu hình thế nào?
6. TOTP seed được sinh, hiển thị, mã hóa, xác minh, kích hoạt và hủy ra sao?
7. Recovery code được cấp, lưu verifier, dùng một lần và tạo lại thế nào?
8. Credential record có trạng thái pending/active/suspended/revoked/expired không?
9. Thông báo enrollment/removal được gửi qua kênh nào và có tránh chứa secret không?
10. Xóa authenticator cuối cùng, mất thiết bị hoặc account recovery được xử lý ra sao?
11. Có bảo vệ CSRF, replay, race condition, duplicate credential và cross-account binding không?
12. Log/audit có đủ điều tra nhưng không chứa seed, OTP, private key, recovery code hoặc session token không?
13. Khi credential bị compromise, có thể revoke ngay và kiểm tra session/token downstream không?
14. Có diễn tập enrollment hijacking, recovery abuse và restore sau revoke không?

## 20. Ghi nhớ trọng tâm

- **Enrollment là thao tác thay đổi gốc tin cậy của tài khoản.** Phải xác minh người yêu cầu và bằng chứng sở hữu authenticator mới.
- **Phiên yếu không được tự thêm authenticator mạnh.** Dùng step-up, freshness, CSRF defense và risk controls.
- **WebAuthn registration cần kiểm tra challenge, origin, RP ID, type, credential và attestation theo policy.** Dùng thư viện server-side đã được kiểm chứng.
- **TOTP chỉ active sau khi mã đầu tiên được xác minh.** Seed/QR là bí mật tương đương authenticator và phải được bảo vệ.
- **Recovery code là bearer secret dùng một lần.** Lưu verifier, không log và vô hiệu mã cũ khi tạo lại.
- **Authenticator có vòng đời và trạng thái.** Pending không được đăng nhập; revoked/expired không được chấp nhận.
- **Xóa credential phải thu hồi ở server.** Kiểm tra phương thức cuối cùng và yêu cầu recovery phù hợp.
- **Thông báo và audit giúp phát hiện enrollment trái phép**, nhưng không thay thế xác minh giao thức.
- **Recovery và enrollment phải được thiết kế cùng nhau.** Một đường recovery yếu có thể vô hiệu toàn bộ MFA.

Authenticator enrollment an toàn là một giao dịch có xác minh: đúng người, đúng account, đúng session, đúng challenge và đúng authenticator. Khi mỗi bước được ràng buộc và có thể thu hồi, hệ thống giảm nguy cơ attacker tự gắn credential của họ vào tài khoản nạn nhân.
