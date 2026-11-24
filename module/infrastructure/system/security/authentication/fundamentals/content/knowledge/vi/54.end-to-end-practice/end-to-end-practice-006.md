# Thiết lập MFA và recovery — Bài thực hành tổng hợp từ enrollment đến khôi phục tài khoản

## 1. Bối cảnh và mục tiêu thực hành

Một ứng dụng quản lý hồ sơ doanh nghiệp đang sử dụng mật khẩu để đăng nhập. Nhóm bảo mật muốn bổ sung xác thực đa yếu tố (MFA) và quy trình khôi phục khi người dùng mất điện thoại hoặc không còn truy cập được authenticator. Bài thực hành này xây dựng một luồng hoàn chỉnh: chuẩn bị chính sách, đăng ký factor, xác minh factor, tạo session, lưu recovery code, xử lý mất thiết bị, thu hồi credential cũ và xác minh quyền truy cập sau khôi phục.

Mục tiêu không chỉ là thêm một màn hình nhập OTP. Hệ thống cần chứng minh người dùng kiểm soát một factor bổ sung, gắn factor với đúng account, ngăn replay, bảo vệ secret, chống lạm dụng recovery và giữ audit trail xuyên suốt vòng đời credential.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài thực hành kết nối credential, password, MFA, passkey, certificate, token, session, account linking và account recovery. Người học sẽ mô hình hóa trust boundary, phòng chống phishing/replay, xử lý login abuse và thiết kế một quy trình có thể vận hành an toàn.

Sau bài thực hành, người học có thể:

- Chọn factor phù hợp với rủi ro và khả năng tiếp cận của người dùng.
- Thiết kế enrollment có xác minh bằng session/factor hiện có.
- Đăng ký TOTP hoặc passkey mà không làm lộ secret.
- Tạo và quản lý recovery code dùng một lần.
- Xây dựng recovery flow không biến email hoặc helpdesk thành đường bypass.
- Thu hồi session, token và authenticator cũ sau khi recovery.
- Ghi audit event và thông báo bảo mật mà không ghi secret.
- Kiểm thử success path, failure path, replay, concurrency và abuse.

## 2. Kịch bản và phạm vi

Ứng dụng có ba nhóm principal:

| Nhóm | Nhu cầu | Mức bảo vệ |
| --- | --- | --- |
| Nhân viên | Đăng nhập hàng ngày và truy cập hồ sơ. | MFA cho login; step-up cho thao tác nhạy cảm. |
| Quản trị viên | Quản lý người dùng, role và cấu hình bảo mật. | Factor chống phishing được ưu tiên; approval cho thao tác rủi ro cao. |
| Service/workload | Gọi API không có tương tác người dùng. | Workload identity, certificate hoặc client credential; không dùng recovery flow của người dùng. |

Phạm vi bài này tập trung vào tài khoản nhân viên và quản trị viên. Workload identity được đề cập ở phần phân biệt để tránh áp dụng TOTP/recovery code của người dùng cho service account.

Giả định hệ thống đã có:

- Identity database với principal ID và tenant ID.
- Password verifier và login session.
- HTTPS ở mọi endpoint xác thực.
- Notification service gửi email hoặc push.
- Audit pipeline có event ID và correlation ID.
- Secret manager/KMS để bảo vệ khóa mã hóa.

Nếu một thành phần chưa có, bài thực hành cần ghi rõ dependency và cách kiểm soát trước khi triển khai.

## 3. Yêu cầu chức năng và bất biến bảo mật

### Yêu cầu chức năng

1. Người dùng có thể đăng ký ít nhất một factor bổ sung.
2. Người dùng có thể đăng ký factor dự phòng.
3. Mỗi factor phải được xác minh trước khi chuyển sang active.
4. Người dùng có thể xem danh sách factor đã đăng ký và thu hồi factor phù hợp.
5. Hệ thống có thể tạo recovery code một lần.
6. Người dùng có thể khởi động recovery khi mất factor.
7. Recovery phải xác minh bằng evidence theo policy và risk.
8. Sau recovery, người dùng có thể đăng ký factor mới và nhận bộ recovery code mới.
9. Hệ thống thông báo các thay đổi bảo mật qua kênh đã xác minh.
10. Support có thể hỗ trợ theo workflow được audit, không được xem secret.

### Security invariants

- Không tạo authenticated session khi factor bắt buộc chưa được xác minh.
- Enrollment factor mới yêu cầu xác minh session/factor hiện có hoặc recovery policy.
- TOTP secret chỉ được hiển thị trong giai đoạn provisioning có kiểm soát; không ghi log.
- Challenge và recovery code dùng một lần không được consume hai lần.
- Recovery không được hạ assurance chỉ vì người dùng mất factor.
- Email/SMS notification không tự nó chứng minh danh tính.
- Credential bị revoke không được active lại do retry, cache stale hoặc restore snapshot.
- Thay đổi MFA/recovery phải tạo audit event.
- Token, cookie, password, OTP, recovery code và private key không xuất hiện trong log.

## 4. Threat model và ranh giới tin cậy

Các tài sản cần bảo vệ:

- Password verifier và session của principal.
- TOTP seed, passkey credential và recovery code.
- Kênh email/phone đã xác minh.
- Recovery transaction và evidence.
- Refresh token family, access token và authorization grant.
- Audit record và notification destination.

Threat actor có thể:

- Phishing password và OTP.
- Đánh cắp session cookie hoặc refresh token.
- Gửi push bombing để người dùng approve nhầm.
- Chiếm email hoặc SIM để thử recovery.
- Lợi dụng helpdesk/social engineering.
- Replay TOTP/recovery request hoặc submit đồng thời.
- Chiếm thiết bị có authenticator.
- Khai thác account enumeration và recovery rate limit.

~~~mermaid
flowchart TD
    USER["Người dùng / Browser / Authenticator"]
    EDGE["TLS edge / API gateway"]
    ID["Identity and MFA service"]
    DB[("Account + factor registry")]
    KMS["KMS / Secret encryption"]
    REC["Recovery service"]
    NOTI["Notification provider"]
    SESS["Session / token service"]
    AUD[("Audit store")]
    SUPPORT["Helpdesk / approver"]
    USER --> EDGE --> ID
    ID <--> DB
    ID <--> KMS
    ID --> SESS
    ID --> NOTI
    ID --> AUD
    USER --> REC
    REC <--> ID
    REC --> SUPPORT
    REC --> NOTI
    REC --> AUD
~~~

Browser và authenticator là vùng do người dùng kiểm soát nhưng có thể bị mất hoặc compromise. Identity service là authority cho account và factor status. KMS bảo vệ secret at rest. Notification provider là bên thứ ba, không được coi là nguồn xác thực độc lập. Helpdesk có thể phê duyệt một số recovery case nhưng phải chịu separation of duties và audit.

## 5. Chọn factor và chính sách MFA

Factor có thể thuộc ba nhóm:

- **Something you know:** password hoặc PIN.
- **Something you have:** authenticator, security key, thiết bị có private key.
- **Something you are:** đặc điểm sinh trắc học được authenticator/thiết bị xử lý.

Một phương thức chỉ được coi là factor khi có thiết kế và xác minh phù hợp. Hai bước cùng dựa vào một bí mật hoặc một thiết bị bị compromise không nhất thiết tạo ra hai yếu tố độc lập.

| Phương thức | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Passkey/WebAuthn | Chống phishing nhờ ràng buộc RP ID/origin; UX tốt. | Cần hỗ trợ nền tảng; cần hiểu syncable và device-bound. |
| Security key | Phishing-resistant, có thể độc lập với điện thoại. | Người dùng phải giữ thiết bị; cần factor dự phòng. |
| TOTP authenticator | Hoạt động offline, phổ biến. | Mã có thể bị phishing hoặc relay; secret cần bảo vệ. |
| Push approval | Dễ dùng khi triển khai đúng. | Có nguy cơ MFA fatigue/push bombing; cần number matching/context. |
| SMS OTP | Dễ tiếp cận trong một số trường hợp. | SIM swap, SS7/social engineering; không phải lựa chọn chống phishing. |
| Email OTP | Có thể hữu ích trong một số recovery policy. | Hộp thư có thể bị chiếm; thường không nên coi là factor độc lập mạnh. |

Chính sách tham khảo:

- Nhân viên: passkey/security key hoặc TOTP theo mức rủi ro và khả năng hỗ trợ.
- Admin: ưu tiên phishing-resistant factor; có factor dự phòng được kiểm soát.
- Hành động nhạy cảm: step-up với factor đủ assurance và authentication freshness phù hợp.
- Recovery: dùng evidence độc lập, không tự động thay bằng SMS/email yếu hơn.

Không bắt buộc mọi tổ chức dùng cùng một factor. Quyết định phải dựa trên tài sản, threat model, assurance target, user population và yêu cầu tuân thủ.

## 6. Mô hình trạng thái của factor

Factor không nên chuyển trực tiếp từ “được tạo” sang “được tin cậy”. Dùng state machine có trạng thái rõ:

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Active: Proof verified
    Pending --> Expired: Enrollment timeout
    Pending --> Cancelled: User cancels
    Active --> Suspended: Risk / admin action
    Active --> Revoked: User or policy revoke
    Suspended --> Active: Approved reactivation
    Suspended --> Revoked: Confirmed compromise
    Revoked --> [*]
    Expired --> [*]
    Cancelled --> [*]
~~~

Pending chưa được dùng để hoàn tất login. Active được phép tham gia xác thực theo policy. Suspended tạm dừng khi cần điều tra hoặc xử lý risk. Revoked, Expired và Cancelled không được dùng để xác thực.

Không tái sử dụng record đã revoked bằng cách đổi status thành active. Nếu người dùng đăng ký lại, tạo credential reference mới và liên kết audit với factor cũ.

## 7. Chuẩn bị dữ liệu và schema

Mỗi factor cần record độc lập:

| Trường | Mục đích |
| --- | --- |
| factor_id | Định danh nội bộ duy nhất. |
| principal_id / tenant_id | Chủ sở hữu và phạm vi tenant. |
| factor_type | TOTP, WebAuthn, security key, push... |
| status | Pending, active, suspended, revoked, expired. |
| created_at / verified_at | Thời điểm enrollment và proof thành công. |
| last_used_at | Hoạt động gần nhất nếu được cập nhật đáng tin. |
| display_name | Tên thân thiện do người dùng đặt, đã giới hạn và escape. |
| secret_ciphertext | Chỉ có với loại cần giữ shared secret; mã hóa bằng envelope encryption. |
| public_key / credential_id | Dữ liệu public/identifier với WebAuthn. |
| version | Chống update cũ ghi đè trạng thái mới. |
| revoked_at / reason | Thời điểm và lý do thu hồi. |

Recovery code cần record riêng hoặc verifier list có trạng thái consumed. Recovery transaction có ID, principal reference, purpose, expiry, evidence status, decision, actor/approver và kết quả. Không lưu recovery code bản rõ sau khi hiển thị.

## 8. Thiết kế enrollment flow

Enrollment bắt đầu từ một session đã xác thực:

1. Người dùng mở mục Security/Authentication.
2. Server kiểm tra session còn hợp lệ và đủ freshness.
3. Với hành động nhạy cảm, yêu cầu step-up bằng factor hiện có.
4. Người dùng chọn phương thức muốn thêm.
5. Server tạo enrollment transaction ngắn hạn, purpose-bound.
6. Authenticator được cấu hình hoặc tạo credential.
7. Người dùng thực hiện proof để chứng minh kiểm soát factor.
8. Server xác minh proof, challenge, account binding và trạng thái transaction.
9. Factor chuyển sang active trong transaction nguyên tử.
10. Audit event được ghi và thông báo qua kênh đã xác minh.

Enrollment transaction phải gắn với principal, tenant, factor type và expiry. Không cho phép đổi principal hoặc factor type giữa chừng. Nếu người dùng hủy, transaction phải bị consume/cancel và không thể dùng lại.

## 9. Thực hành đăng ký TOTP

TOTP dùng shared secret và thời gian để tạo mã dùng một lần. Các bước triển khai:

1. Server sinh secret ngẫu nhiên cho enrollment transaction.
2. Server mã hóa secret bằng DEK; DEK được wrap bằng KMS/HSM-managed key.
3. Server hiển thị QR/otpauth provisioning URI qua trang HTTPS đã xác thực.
4. Người dùng quét QR bằng authenticator app.
5. Người dùng nhập mã hiện tại để chứng minh app đã nhận secret.
6. Server xác minh mã trong time window được policy cho phép.
7. Nếu hợp lệ, server kích hoạt factor và ghi verified_at.
8. QR/secret không được ghi log, analytics, screenshot telemetry hoặc support ticket.

### Ví dụ provisioning URI

~~~text
otpauth://totp/Example%20Corp:alice@example.test
  ?secret=<BASE32_SECRET>
  &issuer=Example%20Corp
  &algorithm=SHA1
  &digits=6
  &period=30
~~~

Đây là ví dụ cấu trúc, không phải secret sử dụng thật. Provisioning URI chứa secret bản rõ; không đưa vào query log, referrer, analytics hoặc bên thứ ba. Trang hiển thị QR nên hạn chế script ngoài và có cache policy phù hợp.

### Xác minh TOTP

- Gắn mã với đúng factor và principal.
- Chấp nhận time window hẹp để xử lý clock skew.
- Giới hạn số lần thử và tốc độ gửi lại.
- Không chấp nhận cùng time-step/code nhiều lần nếu policy yêu cầu replay resistance.
- Cập nhật last accepted counter/time-step nguyên tử.
- Không tiết lộ account/factor tồn tại qua response.

TOTP có thể bị phishing/relay theo thời gian thực. Khi cần chống phishing mạnh, ưu tiên passkey/security key.

## 10. Thực hành đăng ký passkey

Passkey/WebAuthn sử dụng cặp khóa. Relying party lưu credential ID và public key; private key được authenticator giữ theo mô hình của nền tảng.

Quy trình:

1. Server tạo challenge ngẫu nhiên, một lần, có TTL ngắn.
2. Server tạo creation options với RP ID, user handle, algorithms và authenticator selection phù hợp.
3. Browser gọi WebAuthn API; authenticator yêu cầu user verification theo policy.
4. Browser gửi attestation/credential response về server.
5. Server kiểm tra challenge, origin, RP ID hash, flags và dữ liệu theo policy.
6. Server lưu credential ID, public key, transports và metadata cần thiết.
7. Factor active sau khi transaction được xác minh và commit.

Không lưu private key ở server. Không chấp nhận origin/RP ID do client tự chọn. Challenge phải được consume một lần và gắn với đúng account/transaction.

### Device-bound và syncable

Passkey có thể được đồng bộ qua nền tảng hoặc gắn với authenticator cụ thể. Giao diện nên giải thích đúng mô hình nếu thông tin đó có sẵn, và hướng dẫn đăng ký factor dự phòng. Không giả định người dùng có thể export hoặc phục hồi private key device-bound.

## 11. Đăng ký factor dự phòng

Một factor duy nhất có thể khiến người dùng bị khóa tài khoản khi mất thiết bị. Sau enrollment factor chính, hướng dẫn người dùng:

- Thêm passkey trên thiết bị khác hoặc security key dự phòng.
- Thiết lập TOTP nếu policy cho phép.
- Tạo recovery code và lưu an toàn.
- Xác minh email/phone recovery theo policy, nhưng không coi chúng là yếu tố mạnh mặc định.
- Kiểm tra danh sách session và thiết bị.

Không khuyến khích lưu factor dự phòng trên cùng thiết bị duy nhất nếu mục tiêu là chống mất thiết bị. Factor dự phòng cần độc lập đủ mức với factor chính và được bảo vệ như credential thật.

## 12. Tạo recovery code

Recovery code là phương thức dự phòng dùng một lần để bắt đầu hoặc hoàn tất một quy trình recovery theo policy. Nó không phải mã để support hỏi qua điện thoại.

Thiết kế:

- Sinh bằng CSPRNG với entropy phù hợp.
- Tạo một bộ nhiều mã độc lập.
- Hiển thị bản rõ một lần sau khi người dùng đã xác thực.
- Lưu verifier/hash và trạng thái unused/consumed ở server.
- Hướng dẫn lưu offline hoặc trong password manager.
- Không gửi recovery code qua email/SMS.
- Khi tạo bộ mới, revoke/consume bộ cũ theo policy.
- Khi dùng mã, đánh dấu consumed nguyên tử để chống race condition.

Recovery code đã tiêu thụ không được phục hồi từ backup cũ. Nếu người dùng mất toàn bộ mã, họ phải đi qua recovery flow khác và nhận bộ mới sau khi xác minh.

## 13. Recovery readiness và onboarding

Đừng đợi người dùng mất điện thoại mới hướng dẫn recovery. Sau khi bật MFA, giao diện nên hiển thị trạng thái readiness:

| Trạng thái | Gợi ý UX |
| --- | --- |
| Chưa có factor | Hướng dẫn đăng ký factor chính. |
| Có một factor | Khuyến nghị thêm factor dự phòng. |
| Có factor dự phòng, chưa có recovery code | Hướng dẫn tạo và lưu code. |
| Recovery code đã dùng gần hết | Nhắc tạo bộ mới sau khi xác thực. |
| Kênh recovery chưa xác minh | Giải thích cách xác minh qua flow chính thức. |
| Có credential lạ hoặc thay đổi bất thường | Cảnh báo và hướng dẫn kiểm tra bảo mật. |

Không hiển thị secret hoặc recovery code trong trạng thái readiness. Chỉ hiển thị metadata đủ để người dùng hiểu mình đã chuẩn bị tới đâu.

## 14. Thiết kế recovery flow

Recovery phải bắt đầu bằng response chống account enumeration:

1. Người dùng gửi yêu cầu khôi phục bằng identifier.
2. Server trả thông điệp chung, không tiết lộ account có tồn tại hay không.
3. Nếu account hợp lệ, tạo recovery transaction với ID ngẫu nhiên và TTL.
4. Thu thập evidence theo policy: recovery code, factor dự phòng, passkey khác, proofing hoặc helpdesk.
5. Đánh giá risk, account sensitivity, lịch sử thay đổi và tín hiệu compromise.
6. Yêu cầu independent approval nếu thuộc trường hợp đặc quyền/rủi ro cao.
7. Nếu đủ điều kiện, đưa transaction sang approved/completing.
8. Revoke factor bị mất/compromise, session và token liên quan theo policy.
9. Người dùng đăng ký factor mới và tạo recovery code mới.
10. Gửi thông báo qua kênh đã xác minh trước đó.
11. Đóng transaction, ghi audit và theo dõi hoạt động sau recovery.

Recovery transaction cần state machine và idempotency. Một request retry không được tạo nhiều lần thay credential hoặc dùng lại evidence đã consume.

## 15. Recovery state machine

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> EvidencePending
    EvidencePending --> Approved: Evidence meets policy
    EvidencePending --> Rejected: Evidence invalid
    EvidencePending --> Expired: TTL elapsed
    Approved --> Completing
    Completing --> Completed: Credential replaced
    Completing --> Failed: Operation error
    Failed --> Completing: Safe retry
    Completed --> [*]
    Rejected --> [*]
    Expired --> [*]
~~~

Requested chưa cấp quyền. EvidencePending đang xác minh. Approved chỉ có nghĩa evidence đạt policy, chưa nhất thiết đã thay credential. Completing thực hiện thu hồi/cấp mới. Completed chỉ được ghi khi các bước bắt buộc đã xác minh.

Không chuyển transaction từ Rejected hoặc Expired về Approved bằng cách sửa record. Tạo transaction mới sau khi người dùng bắt đầu lại và cung cấp evidence mới.

## 16. Chọn recovery evidence

Không có một phương thức recovery phù hợp mọi tài khoản. Có thể kết hợp:

| Evidence | Giá trị | Giới hạn |
| --- | --- | --- |
| Recovery code chưa dùng | Bằng chứng người dùng giữ mã đã cấp trước đó. | Có thể bị sao chép; phải one-time và entropy cao. |
| Factor dự phòng | Xác minh bằng authenticator độc lập. | Có thể cùng bị mất hoặc compromise. |
| Passkey trên thiết bị khác | Phishing-resistant nếu được xác minh đúng. | Phụ thuộc thiết bị/platform và trạng thái credential. |
| Verified contact | Kênh nhận thông báo hoặc hỗ trợ một số bước. | Email/SMS có thể bị chiếm; không mặc định là proof mạnh. |
| Identity proofing/helpdesk | Dùng khi mất mọi factor theo quy trình có kiểm soát. | Rủi ro social engineering, insider và dữ liệu cá nhân. |
| Organizational sponsor | Xác nhận quan hệ công việc hoặc quyền yêu cầu. | Không thay thế proof của người dùng cho mọi loại account. |

Với admin hoặc tài khoản có quyền cao, cần assurance cao hơn, independent approval và kiểm tra chéo. Không để một helpdesk agent có thể vừa xác minh, vừa phê duyệt, vừa hoàn tất recovery cho chính mình.

## 17. Chống lạm dụng recovery và social engineering

Các kiểm soát:

- Rate limit theo account, nguồn, device và toàn hệ thống.
- Response công khai đồng nhất để chống enumeration.
- Recovery transaction có TTL, purpose binding và one-time evidence.
- Step-up hoặc approval độc lập cho account đặc quyền.
- Notification tới kênh đã xác minh trước đó.
- Cooldown/hạn chế một số thay đổi nhạy cảm sau recovery theo risk policy.
- Helpdesk script không yêu cầu password, OTP, recovery code hoặc private key.
- Ghi actor, approver, evidence type và decision.
- Phát hiện nhiều recovery request, đổi contact và enrollment liên tiếp.

Không dùng câu hỏi bảo mật dễ đoán hoặc thông tin công khai làm evidence chính. Không coi việc attacker biết tên, ngày sinh hoặc vài thông tin nhân sự là bằng chứng sở hữu account.

## 18. Thu hồi session, token và credential sau recovery

Khi account được recovery do mất hoặc nghi compromise factor, cần đánh giá các đường truy cập cũ:

- Revoke factor bị mất hoặc nghi bị sao chép.
- Revoke session hiện tại hoặc tất cả session theo policy.
- Revoke refresh token family và OAuth grant liên quan nếu cần.
- Tăng security epoch/version để vô hiệu hóa session/token cũ theo kiến trúc.
- Kiểm tra passkey, API key, certificate và recovery method mới được thêm.
- Xác minh revocation propagation tới mọi region/resource server.
- Không restore session cũ từ snapshot hoặc cache stale.

Không phải recovery nào cũng cần logout tất cả thiết bị; quyết định dựa trên evidence và impact. Tuy nhiên, nếu factor bị compromise hoặc có dấu hiệu account takeover, revoke rộng hơn thường cần thiết.

## 19. Notification sau enrollment và recovery

Thông báo bảo mật nên gửi qua kênh đã xác minh trước đó:

- Factor mới được thêm hoặc xóa.
- Recovery được yêu cầu, phê duyệt, từ chối hoặc hoàn tất.
- Session/token bị thu hồi.
- Recovery method hoặc contact thay đổi.
- Bộ recovery code mới được tạo.

Nội dung chỉ nêu sự kiện, thời điểm, ứng dụng và cách báo cáo. Không gửi OTP, recovery code, TOTP seed, private key hoặc bearer recovery token. Link trong email phải dùng domain chính thức; hành động nhạy cảm cần mở ứng dụng và xác minh, không chỉ dựa vào click.

Nếu notification provider lỗi, giữ event trong durable queue và retry idempotently. Không coi notification delivery là bằng chứng người dùng đã đọc hoặc chấp thuận.

## 20. Session freshness và step-up

Enrollment và recovery có thể thay đổi toàn bộ cách account được xác thực. Do đó:

- Kiểm tra authentication time và assurance của session hiện tại.
- Yêu cầu step-up trước khi thêm/xóa factor nếu policy quy định.
- Ràng buộc step-up với purpose cụ thể, ví dụ add_totp hoặc remove_passkey.
- Challenge có TTL ngắn và chỉ dùng một lần.
- Không chấp nhận session cũ chỉ vì cookie vẫn còn.
- Sau thay đổi bảo mật, đánh giá session khác có cần revoke không.

Session freshness phải dựa trên thời gian do server xác minh, không tin timestamp từ browser. Một session có thể hợp lệ về expiry nhưng không đủ freshness cho thay đổi factor nhạy cảm.

## 21. Mã giả: enrollment TOTP và recovery code

Mã giả sau minh họa transaction và state change. Nó không thay thế thư viện TOTP, WebAuthn, KMS hoặc hệ thống identity đã được kiểm thử.

~~~text
beginTotpEnrollment(principal, session):
    require session.isValid
    require session.principal == principal.id
    require session.isFreshFor("add_totp")

    tx = createOneTimeTransaction(
        principal = principal.id,
        purpose = "totp_enrollment",
        expiresAt = now + shortTtl
    )
    secret = CSPRNG()
    encryptedSecret = envelopeEncrypt(secret, kmsKeyVersion)
    savePendingFactor(tx.id, encryptedSecret)
    return provisioningUriForCurrentAuthenticatedSession(tx, secret)

verifyTotpEnrollment(tx, submittedCode):
    require tx.isPending and not tx.isExpired
    factor = loadPendingFactor(tx)
    step = verifyTotpWithinAllowedWindow(factor.secret, submittedCode)
    require step.valid
    atomically:
        require tx.status == "pending"
        require step > factor.lastAcceptedStep
        activateFactor(factor.id)
        consumeTransaction(tx.id)
        appendAudit("factor.enrolled", factor.reference)
    return success

createRecoveryCodes(principal, freshSession):
    require freshSession.isFreshFor("create_recovery_codes")
    codes = generateIndependentHighEntropyCodes(count = policy.codeCount)
    verifiers = codes.map(code => keyedVerifier(code))
    atomically:
        revokeUnusedRecoveryCodeSet(principal)
        storeRecoveryVerifiers(principal, verifiers, unused = true)
        appendAudit("recovery_codes.created", principal.reference)
    return displayOnce(codes)
~~~

Trong triển khai thật:

- Secret TOTP phải được mã hóa trước khi lưu và chỉ decrypt trong verifier được cấp quyền.
- Không lưu provisioning URI hoặc QR image trong log/cache ngoài kiểm soát.
- Enrollment transaction và counter update phải nguyên tử.
- displayOnce không có API lấy lại code bản rõ.
- Recovery code verifier cần keyed protection phù hợp và trạng thái consumed bền vững.
- Các endpoint phải chống CSRF/session fixation và có rate limit.

## 22. Mã giả: recovery có kiểm soát

~~~text
startRecovery(identifier):
    publicResponse = genericRecoveryResponse()
    principal = resolveIdentifierInternally(identifier)
    if principal is null:
        return publicResponse

    tx = createRecoveryTransaction(
        principal = principal.id,
        purpose = "account_recovery",
        expiresAt = now + recoveryTtl
    )
    sendMinimalNoticeToPreviouslyVerifiedChannel(principal, tx.reference)
    return publicResponse

submitRecoveryEvidence(tx, evidence):
    require tx.status == "evidence_pending"
    require tx.notExpired
    require rateLimitAllows(tx.principal)
    result = verifyEvidenceUnderPolicy(tx.principal, evidence)
    recordEvidenceTypeAndOutcome(result)  # never store reusable secret
    if not result.accepted:
        updateRecoveryState(tx, "rejected_or_pending_review")
        return genericNextStep()
    require independentApprovalIfHighRisk(tx.principal)
    approveRecovery(tx)

completeRecovery(tx, newFactorProof):
    require tx.status == "approved"
    require verifyNewFactorProof(tx.principal, newFactorProof)
    atomically:
        revokeLostOrCompromisedFactors(tx.principal)
        revokeSessionsAndRefreshFamiliesByPolicy(tx.principal)
        activateNewFactor(tx.principal, newFactorProof)
        consumeRecoveryEvidence(tx)
        incrementSecurityEpoch(tx.principal)
        markRecoveryCompleted(tx)
        appendAudit("account.recovery.completed", tx.reference)
    notifyPreviouslyVerifiedChannels(tx.principal)
    return success
~~~

Recovery evidence chỉ được lưu theo loại và kết quả cần thiết. Không lưu bản rõ recovery code, OTP hoặc tài liệu proofing trong log thông thường. Nếu cần evidence nhạy cảm theo quy trình tổ chức, lưu ở kho riêng với retention và quyền truy cập được kiểm soát.

## 23. Tình huống thực tế: nhân viên mất điện thoại

Một nhân viên đã bật password + TOTP trên điện thoại cá nhân. Điện thoại bị mất khi đi công tác. Nhân viên vẫn còn một passkey trên laptop công ty và bộ recovery code đã lưu trong password manager.

### Bước 1 — Tiếp nhận

Người dùng mở trang recovery chính thức và nhập identifier. Hệ thống trả thông điệp chung, tạo transaction nếu account tồn tại và gửi cảnh báo tối thiểu tới kênh đã xác minh.

### Bước 2 — Xác minh

Người dùng xác minh bằng passkey dự phòng hoặc recovery code chưa dùng theo policy. Nếu là tài khoản đặc quyền, có thể cần thêm approval độc lập.

### Bước 3 — Containment

Hệ thống suspend/revoke TOTP binding trên điện thoại bị mất, xem xét session trên thiết bị đó và revoke token/session theo policy. Không xóa passkey laptop còn tin cậy nếu evidence cho thấy nó không bị ảnh hưởng.

### Bước 4 — Re-enrollment

Người dùng đăng ký TOTP secret mới trên điện thoại thay thế, xác minh mã, rồi tạo bộ recovery code mới. Bộ recovery code cũ bị consume/revoke theo policy; mã đã dùng không được tái sử dụng.

### Bước 5 — Xác nhận và theo dõi

Hệ thống gửi notification qua kênh cũ đã xác minh, hiển thị danh sách factor còn active và ghi audit. Người dùng kiểm tra session/thiết bị, còn hệ thống theo dõi login bất thường sau recovery.

### Điều gì xảy ra nếu người dùng không còn passkey hoặc recovery code?

Transaction chuyển sang identity proofing/helpdesk flow. Nhân viên hỗ trợ không được yêu cầu mật khẩu hoặc OTP. Cần xác minh độc lập, dual control với account nhạy cảm, thời gian xử lý rõ và audit toàn bộ quyết định. Không bỏ MFA chỉ để giải quyết nhanh.

## 24. Kiểm thử end-to-end

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Đăng ký TOTP thành công | Secret được tạo, proof hợp lệ, factor chuyển active. |
| TOTP code sai/hết hạn | Không kích hoạt factor; có rate limit và thông báo phù hợp. |
| Replay cùng TOTP time-step | Bị từ chối theo replay policy. |
| Enrollment transaction hết hạn | Không thể dùng lại; factor pending bị dọn theo policy. |
| Đăng ký passkey | Challenge, origin, RP ID và user verification được kiểm tra. |
| Enrollment không có session freshness | Bị yêu cầu step-up hoặc từ chối. |
| Tạo recovery code | Hiển thị một lần; server chỉ giữ verifier và trạng thái. |
| Dùng recovery code hợp lệ | Code được consume nguyên tử và không dùng lại được. |
| Hai request dùng cùng recovery code | Chỉ một request thành công. |
| Recovery identifier không tồn tại | Response công khai không tiết lộ account existence. |
| Recovery evidence sai | Không cấp quyền; transaction bị giới hạn và audit. |
| Recovery account admin | Có assurance/approval bổ sung theo policy. |
| Mất điện thoại | Factor/thiết bị bị mất được revoke; factor khác còn tin cậy được giữ theo policy. |
| Recovery hoàn tất | Factor mới active, session/token cũ được xử lý và security epoch cập nhật. |
| Notification provider lỗi | Event được giữ/retry; không làm recovery thành công giả. |
| KMS unavailable | Không lưu hoặc xác minh TOTP bằng cách bỏ qua bảo vệ secret. |
| Cache stale sau revoke | Verifier từ chối factor cũ trong propagation SLA. |
| Restore snapshot cũ | Revocation/consumed state mới hơn snapshot không bị rollback. |
| Helpdesk self-approval | Bị chặn bởi separation of duties. |
| Log/trace inspection | Không có password, OTP, seed, recovery code hoặc token. |
| Cross-tenant factor reference | Bị từ chối do tenant/principal mismatch. |

## 25. Kiểm thử abuse và failure mode

Ngoài happy path, cần thử:

- Password spraying trước khi MFA challenge.
- Push bombing và người dùng approve nhầm.
- Phishing proxy relay TOTP theo thời gian thực.
- Replay challenge enrollment hoặc recovery.
- Submit song song cùng recovery code.
- Thay principal ID giữa lúc bắt đầu và hoàn tất enrollment.
- CSRF trên thao tác thêm/xóa factor.
- Session fixation trước và sau MFA.
- Account enumeration qua response, timing hoặc notification.
- Rate limit bypass qua nhiều node/IP.
- Helpdesk social engineering và approver collusion.
- Refresh token reuse sau recovery.
- Credential status rollback từ backup/cache.

Mỗi test cần nêu precondition, request sequence, expected state và audit evidence. Không dùng account người thật hoặc gửi push/SMS hàng loạt ngoài môi trường thử nghiệm được kiểm soát.

## 26. Vận hành, monitoring và metrics

Theo dõi:

- MFA enrollment và completion rate.
- Tỷ lệ factor verification thất bại theo loại.
- TOTP replay/clock skew signal.
- Push deny/timeout và số challenge trên mỗi transaction.
- Recovery request, approval, rejection, expiry và completion.
- Recovery code consumption và số code còn lại.
- Factor add/remove/revoke bất thường.
- Session/token revocation propagation.
- KMS decrypt/sign error và latency.
- Helpdesk recovery volume, approver và thời gian xử lý.

Không dùng metrics chứa OTP, seed, recovery code hoặc token. Dashboard có thể dùng principal reference/pseudonymized ID và chỉ giải định danh khi có quyền và case hợp lệ.

### Alert đáng chú ý

- Nhiều factor bị thêm/xóa trong thời gian ngắn.
- Recovery request rồi đổi email/phone và thêm passkey liên tiếp.
- Push approve bất thường sau nhiều lần deny.
- Recovery từ nguồn lạ trên account đặc quyền.
- TOTP replay hoặc challenge reuse.
- Session/token được sử dụng sau khi revoke.
- Helpdesk recovery ngoài quy trình hoặc thiếu approver.

## 27. Checklist triển khai

- [ ] Xác định threat model, account sensitivity và assurance target.
- [ ] Chọn factor chính/dự phòng phù hợp; ưu tiên phishing-resistant khi cần.
- [ ] Thiết kế factor state machine và recovery state machine.
- [ ] Enrollment yêu cầu session hợp lệ, freshness và step-up theo policy.
- [ ] Challenge/transaction có entropy, TTL, purpose binding và one-time use.
- [ ] TOTP secret được mã hóa bằng envelope encryption; không log provisioning URI.
- [ ] Passkey kiểm tra challenge, origin, RP ID và user verification.
- [ ] Recovery code sinh ngẫu nhiên, hiển thị một lần và consume nguyên tử.
- [ ] Recovery response chống account enumeration.
- [ ] Recovery evidence phù hợp risk; helpdesk có independent approval khi cần.
- [ ] Recovery không hạ assurance hoặc bỏ qua account suspension.
- [ ] Sau recovery, xử lý factor mất, session, refresh token và security epoch.
- [ ] Notification gửi qua kênh đã xác minh, không chứa secret.
- [ ] Audit actor, subject, factor reference, decision và outcome.
- [ ] Rate limit, abuse detection và alert được bật.
- [ ] Cache/revocation propagation và disaster restore được kiểm thử.
- [ ] Accessibility và phương thức dự phòng được đánh giá.
- [ ] Có runbook support, owner, escalation và incident response.

## 28. Deliverables của bài thực hành

Người học cần nộp hoặc trình bày:

1. Sơ đồ trust boundary cho enrollment, login và recovery.
2. Bảng policy factor theo nhóm user và độ nhạy cảm.
3. State machine cho factor và recovery transaction.
4. API contract hoặc pseudocode cho enrollment TOTP/passkey.
5. Thiết kế lưu secret/verifier và recovery code.
6. Recovery playbook cho trường hợp mất thiết bị.
7. Audit event schema và notification mẫu đã redact.
8. Test matrix gồm happy path, failure, replay, concurrency và abuse.
9. Metrics/alert và runbook vận hành.
10. Danh sách trade-off, giả định và rủi ro còn lại.

## 29. Tiêu chí đánh giá

| Tiêu chí | Đạt khi |
| --- | --- |
| Threat model | Xác định đúng tài sản, actor, trust boundary và abuse case. |
| Factor selection | Giải thích được assurance và giới hạn từng factor. |
| Enrollment | Có step-up, challenge binding, proof verification và atomic activation. |
| Secret handling | TOTP/recovery material không bị log hoặc lưu bản rõ ngoài thiết kế. |
| Replay resistance | Challenge, OTP/recovery code và transaction được consume đúng. |
| Recovery | Có evidence phù hợp, anti-enumeration, approval và không bypass MFA. |
| Session/token | Credential mất/compromise dẫn tới revoke đúng phạm vi và propagation. |
| Audit/notification | Có attribution và thông báo nhưng không lộ secret. |
| UX/accessibility | Hướng dẫn rõ, có factor dự phòng và hỗ trợ người dùng. |
| Testing/operations | Có test matrix, metrics, alert, owner và runbook. |

Không đạt nếu chỉ có màn hình nhập OTP nhưng không có enrollment proof, recovery policy, replay handling, revocation hoặc audit evidence.

## 30. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không thể coi việc nhập password thành công là đủ để thêm một factor mới?

**Gợi ý:** Session có thể bị chiếm hoặc đã quá cũ. Enrollment factor làm thay đổi khả năng truy cập lâu dài, nên cần session freshness và step-up theo policy.

**Câu 2.** Vì sao TOTP secret phải được bảo vệ như credential?

**Gợi ý:** Ai có seed có thể tạo mã hợp lệ. Secret cần mã hóa, hạn chế decrypt và không xuất hiện trong log/QR cache.

**Câu 3.** Recovery code khác OTP như thế nào?

**Gợi ý:** Recovery code là mã dự phòng được cấp trước, có entropy cao và dùng một lần; OTP thường được tạo theo challenge/time hoặc gửi qua kênh.

**Câu 4.** Vì sao recovery response cần chống account enumeration?

**Gợi ý:** Attacker có thể dùng endpoint để xác nhận account tồn tại, rồi nhắm phishing hoặc social engineering.

**Câu 5.** Khi người dùng mất điện thoại, có nên tự động bỏ MFA không?

**Gợi ý:** Không. Dùng factor dự phòng hoặc recovery evidence theo policy; nếu không đủ bằng chứng thì chuyển quy trình proofing/hỗ trợ.

**Câu 6.** Vì sao recovery cần xử lý session và refresh token?

**Gợi ý:** Attacker có thể đã tạo session trước khi người dùng khôi phục. Đổi factor không tự thu hồi các token/session đó.

**Câu 7.** Tại sao helpdesk không nên tự xác minh và tự phê duyệt recovery đặc quyền?

**Gợi ý:** Thiếu separation of duties làm tăng nguy cơ insider abuse và social engineering; cần approval độc lập và audit.

## 31. Ghi nhớ

**Thiết lập MFA và recovery là một quy trình vòng đời credential, không phải hai tính năng tách rời.** Enrollment phải gắn với session đủ freshness, challenge có purpose/TTL/one-time semantics và proof được xác minh trước khi factor active. TOTP seed, passkey metadata và recovery code cần được bảo vệ đúng loại; recovery code chỉ hiển thị một lần và consume nguyên tử. Recovery phải dùng evidence theo risk, chống account enumeration/social engineering, có independent approval khi cần và không hạ assurance chỉ vì người dùng mất thiết bị. Sau recovery, cần xử lý factor cũ, session, refresh token, security epoch, audit và notification. Chỉ coi quy trình hoàn tất khi factor mới hoạt động, credential cũ bị thu hồi đúng phạm vi và mọi verifier đã nhận trạng thái mới.
