# Authentication event (Sự kiện xác thực)

> **Chương:** Monitoring và audit  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Thiết kế sự kiện xác thực có cấu trúc để quan sát, kiểm toán và phát hiện lạm dụng trong toàn bộ vòng đời identity; chuẩn hóa actor, subject, phương thức, kết quả, nguồn và ngữ cảnh; bảo vệ tính toàn vẹn, quyền riêng tư, khả năng truy vết và độ tin cậy của event khi truyền qua nhiều thành phần.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích authentication event và phân biệt event, application log, audit record, metric và trace.
2. Xác định những sự kiện cần ghi nhận trong login, MFA, passkey, SSO, token, session, recovery và service authentication.
3. Thiết kế schema event có version, event ID, actor, subject, outcome, timestamp, source và correlation context.
4. Phân biệt người thực hiện hành động, người được đại diện và workload phát sinh request.
5. Bảo đảm event được phát sinh từ nguồn có thẩm quyền, không dựa vào dữ liệu do browser tự khai.
6. Thiết kế pipeline thu thập có xác thực, retry, deduplication, ordering và xử lý backpressure.
7. Bảo vệ event khỏi sửa/xóa trái phép và hạn chế dữ liệu nhạy cảm trong log.
8. Xây dựng detection rule cho brute force, credential stuffing, MFA fatigue, session abuse, recovery abuse và thay đổi quyền.
9. Tổ chức alert, SIEM correlation, incident response và audit trail xuyên nhiều service.
10. Kiểm thử event completeness, integrity, privacy, retention, clock skew và failure scenarios.

## 1. Authentication event là gì?

**Authentication event (sự kiện xác thực)** là bản ghi có cấu trúc mô tả một hành động hoặc kết quả liên quan đến việc chứng minh, duy trì, thay đổi hay thu hồi danh tính và trạng thái xác thực.

Ví dụ:

- Người dùng gửi yêu cầu đăng nhập.
- Password verification thành công hoặc thất bại.
- MFA challenge được tạo, phê duyệt, từ chối hoặc hết hạn.
- Passkey được đăng ký hoặc xóa.
- OIDC callback được chấp nhận hoặc từ chối.
- Session được tạo, gia hạn, rotate hoặc revoke.
- Password reset hoặc account recovery hoàn tất.
- Một service lấy access token hoặc certificate.
- Quản trị viên thay đổi policy MFA.
- Tài khoản bị suspend hoặc deprovision.

Event giúp trả lời: điều gì đã xảy ra, xảy ra khi nào, với principal nào, do thành phần nào thực hiện, kết quả ra sao và hệ thống đã áp dụng policy nào.

### Vì sao cần event xác thực?

Một hệ thống có thể trả lỗi đăng nhập nhưng không có dữ liệu để biết đó là người dùng nhập sai, bot thử credential, IdP gặp lỗi hay database timeout. Ngược lại, login thành công không có nghĩa hành vi là bình thường: attacker có thể đăng nhập bằng credential bị đánh cắp, thêm authenticator mới hoặc tạo session bất thường.

Event có cấu trúc giúp:

- Điều tra sự cố và dựng lại chuỗi hành động.
- Phát hiện lạm dụng đăng nhập và account takeover.
- Chứng minh policy đã được thực thi.
- Theo dõi sức khỏe của authentication service.
- Đo tỷ lệ thành công, lỗi và độ trễ.
- Hỗ trợ audit nội bộ và yêu cầu tuân thủ.
- Xác định ảnh hưởng khi credential hoặc signing key bị compromise.

Event chỉ có giá trị nếu dữ liệu đáng tin, đầy đủ theo mục đích và được bảo vệ khỏi truy cập trái phép.

## 2. Phân biệt event, log, audit, metric và trace

Các loại dữ liệu quan sát thường được lưu cùng hệ thống nhưng phục vụ mục đích khác nhau.

| Loại dữ liệu | Mục đích | Ví dụ | Yêu cầu nổi bật |
| --- | --- | --- | --- |
| **Authentication event** | Mô tả một hành động/kết quả xác thực có schema. | MFA denied, session revoked. | Ngữ nghĩa ổn định, actor/outcome rõ. |
| Application log | Hỗ trợ debug và vận hành ứng dụng. | Kết nối DB timeout. | Có ngữ cảnh kỹ thuật, tránh secret. |
| Audit record | Bằng chứng về hành động và quyết định cần truy cứu. | Admin thay đổi MFA policy. | Nguồn có thẩm quyền, integrity và retention. |
| Metric | Đo số lượng, tỷ lệ hoặc phân phối. | Login failure rate. | Tổng hợp, cardinality được kiểm soát. |
| Trace/span | Theo dõi một request qua nhiều thành phần. | Login request qua gateway và IdP. | Correlation và timing xuyên service. |

Một authentication event có thể được dùng làm nguồn cho audit, metric hoặc trace correlation, nhưng không nên coi mọi debug log là audit evidence. Audit record cần provenance, quyền truy cập, retention và integrity rõ ràng hơn.

### Ví dụ

- Event: người dùng có subject U-42 đăng nhập thất bại do password không hợp lệ.
- Metric: tổng số login failure theo phút và tenant.
- Trace: request đi qua Gateway, Authentication API và Credential Store.
- Audit: sự kiện admin disable MFA cho account đặc quyền.

Không cần lưu toàn bộ request body hoặc token chỉ để tạo một event. Event phải mang dữ liệu tối thiểu đủ cho mục đích.

## 3. Phạm vi sự kiện trong vòng đời authentication

Event taxonomy nên bao phủ các bước từ đăng ký credential tới thu hồi quyền.

~~~mermaid
flowchart TD
    A["Identity / account lifecycle"] --> B["Credential enrollment"]
    B --> C["Authentication attempt"]
    C --> D["MFA / passkey / federation"]
    D --> E["Session and token issuance"]
    E --> F["Session use and step-up"]
    F --> G["Credential or recovery change"]
    G --> H["Logout / revoke / deprovision"]
    C --> I["Detection and response"]
    E --> I
    G --> I
    H --> I
~~~

### Nhóm event thường gặp

| Nhóm | Event tiêu biểu |
| --- | --- |
| Account lifecycle | Account created, activated, suspended, restored, deprovisioned. |
| Credential lifecycle | Password changed, passkey enrolled/removed, certificate issued/revoked. |
| Primary authentication | Login initiated, succeeded, failed, blocked, throttled. |
| MFA | Challenge created, delivered, approved, denied, expired, locked. |
| Federation | OIDC/SAML request, callback accepted/rejected, identity linked/unlinked. |
| Token | Token issued, refreshed, introspection inactive, grant revoked. |
| Session | Session created, rotated, renewed, idle-expired, revoked, logout. |
| Recovery | Reset requested, verified, completed, denied, recovery method changed. |
| Risk and policy | Risk elevated, step-up required, policy deny, suspicious session. |
| Administrative | MFA policy changed, trusted issuer added, account unlocked. |
| Workload/service | Client authentication, certificate rotation, workload identity revoked. |

Không phải mọi hệ thống cần phát mọi event với cùng mức chi tiết. Chọn taxonomy dựa trên threat model, yêu cầu audit và khả năng vận hành.

## 4. Event taxonomy và naming convention

Tên event nên ổn định, mô tả hành động và kết quả bằng một quy tắc nhất quán.

Ví dụ theo dạng domain.action.result:

- **authentication.login.succeeded**
- **authentication.login.failed**
- **authentication.mfa.challenge_created**
- **authentication.mfa.denied**
- **authentication.passkey.registered**
- **authentication.federation.callback_rejected**
- **authentication.session.revoked**
- **authentication.recovery.completed**
- **identity.account.suspended**
- **identity.link.created**
- **authorization.policy.denied**
- **workload.client_authentication.failed**

### Nguyên tắc đặt tên

- Dùng vocabulary có kiểm soát, tránh mỗi service đặt một tên khác cho cùng ý nghĩa.
- Tên event mô tả sự kiện đã xảy ra, không phải phán đoán như “hacker_detected” nếu chưa có kết luận.
- Outcome và reason code nên là field riêng để dễ truy vấn.
- Phân biệt event initiated, challenged, completed và failed.
- Version schema độc lập với version ứng dụng.
- Không nhúng username, email, tenant name hoặc token vào event name.
- Không dùng event name làm nơi chứa dữ liệu động.

Một event login failure có thể có reason code như invalid_credential, account_disabled, rate_limited hoặc dependency_unavailable. Reason code cần được định nghĩa để không vô tình tiết lộ account existence cho người chưa xác thực.

## 5. Schema của authentication event

Schema tốt phải đủ cho điều tra và correlation, nhưng không lưu dữ liệu nhạy cảm không cần thiết.

### Các field cơ bản

| Field | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| event_id | ID duy nhất của event. | Không phải credential; dùng deduplicate. |
| event_type | Loại event. | Vocabulary có kiểm soát. |
| event_version | Version schema. | Cho phép consumer nâng cấp dần. |
| occurred_at | Thời điểm hành động xảy ra theo nguồn. | UTC, timestamp chuẩn hóa. |
| observed_at | Thời điểm collector nhận event. | Hữu ích đo trễ pipeline. |
| producer | Service phát event. | Được xác minh qua workload identity. |
| actor | Principal thực hiện hành động. | User, workload, client hoặc operator. |
| subject | Principal/tài khoản bị tác động hoặc được đại diện. | Có thể khác actor. |
| tenant | Phạm vi tổ chức. | Lấy từ context tin cậy. |
| outcome | Kết quả. | success, failure, denied, challenged, expired. |
| reason_code | Lý do đã chuẩn hóa. | Không dùng raw exception làm reason. |
| auth_method | Phương thức xác thực. | Password, passkey, TOTP, mTLS, federation. |
| source | Ngữ cảnh nguồn. | IP/device/network theo privacy policy. |
| session_ref | Tham chiếu session đã bảo vệ. | Không lưu session cookie. |
| correlation_id | Liên kết các event trong một interaction. | Không dùng token làm correlation ID. |
| trace_id | Liên kết distributed trace. | Theo trace context đã xác minh. |
| policy_version | Policy đã được áp dụng. | Hỗ trợ điều tra quyết định. |

### Ví dụ event JSON

~~~json
{
  "event_id": "evt-01J8M7K4",
  "event_type": "authentication.login.failed",
  "event_version": 1,
  "occurred_at": "2026-11-22T09:15:31.240Z",
  "observed_at": "2026-11-22T09:15:31.288Z",
  "producer": {
    "service": "identity-api",
    "environment": "production"
  },
  "actor": {
    "type": "user",
    "issuer": "https://id.example.edu",
    "subject_ref": "usr-ref-7f21"
  },
  "tenant_ref": "tenant-ref-12",
  "outcome": "failure",
  "reason_code": "invalid_credential",
  "auth_method": "password",
  "source": {
    "network_zone": "external",
    "ip_ref": "ip-pseudonym-91"
  },
  "correlation_id": "corr-5e81",
  "policy_version": "login-policy-12"
}
~~~

Đây là schema minh họa. Giá trị subject_ref, tenant_ref và ip_ref có thể là identifier pseudonymized hoặc reference nội bộ. Không dùng identifier giả trong ví dụ để suy ra cách triển khai cụ thể của một sản phẩm.

### Field bắt buộc và field tùy chọn

Nên định nghĩa rõ field nào bắt buộc theo từng event type. Ví dụ login failure cần event ID, producer, thời gian, outcome và auth method; session revoked cần session reference, actor/reason và kết quả revoke. Không ép mọi event mang cùng một tập field nếu field đó không có ý nghĩa.

## 6. Actor, subject, producer và source

Một lỗi phổ biến là ghi tất cả danh tính vào một field user_id. Trong hệ thống phân tán, actor, subject và producer có thể khác nhau.

- **Actor:** người hoặc workload thực hiện hành động.
- **Subject:** account hoặc principal bị tác động/được đại diện.
- **Producer:** service tạo event.
- **Source:** browser, device, network hoặc upstream system tạo request.
- **Approver:** principal phê duyệt hành động nếu workflow có bước approval.

Ví dụ, helpdesk operator reset authenticator cho học viên:

- Actor: operator đã xác thực qua privileged workflow.
- Subject: học viên bị thay đổi authenticator.
- Producer: identity administration service.
- Approver: supervisor nếu policy yêu cầu.
- Source: admin console và managed device.

Event phải phản ánh đúng vai trò. Không ghi operator thành subject hoặc ghi service phát event thành actor nếu user/operator mới là người thực hiện hành động.

### Không tin actor do client tự khai

Browser có thể gửi header X-User hoặc trường actor trong JSON. Những giá trị này không tự chứng minh danh tính. Actor phải được lấy từ session/token/certificate đã xác minh hoặc từ một proxy/service có integrity và trust relationship rõ.

## 7. Event phát sinh ở đâu và nguồn nào có thẩm quyền?

Event cần được tạo tại thành phần biết chắc hành động và kết quả đã xảy ra.

| Event | Nguồn có thẩm quyền thường gặp |
| --- | --- |
| Password verification success/failure | Authentication service thực hiện verify. |
| MFA approval/denial | MFA verifier hoặc trusted authenticator integration. |
| Passkey registration | WebAuthn RP sau khi xác minh registration ceremony. |
| OIDC callback accepted | RP sau khi validate state, nonce, token và issuer. |
| Session revoked | Session service/store sau khi thay đổi trạng thái. |
| Token issued | Authorization Server sau khi phát token. |
| DB credential read | Secret manager hoặc provider ghi access audit. |
| Admin policy changed | Administration service sau khi commit thay đổi. |
| Account deprovisioned | Identity lifecycle service sau khi áp dụng trạng thái. |

Không phát event “session revoked success” ngay khi nhận yêu cầu logout nếu backend chưa xác nhận revoke. Có thể ghi riêng logout requested và session revocation result.

### Server-side event

Browser telemetry có thể bổ sung thông tin UX, nhưng không nên là nguồn duy nhất cho security audit. Event từ client có thể bị giả mạo, mất do browser đóng hoặc bị chặn bởi extension/network. Các quyết định quan trọng cần được ghi ở server-side authority.

## 8. Outcome, reason code và lỗi phụ thuộc

Outcome phải mô tả kết quả theo ngữ nghĩa nghiệp vụ. Reason code nên ổn định, không phụ thuộc message của exception hoặc ngôn ngữ hiển thị.

### Outcome gợi ý

- success: hành động hoàn tất.
- failure: xác thực không thành công.
- denied: policy từ chối.
- challenged: yêu cầu thêm bằng chứng.
- expired: transaction hoặc credential hết hạn.
- cancelled: người dùng hoặc operator hủy.
- unavailable: dependency không khả dụng.
- pending: chưa có kết quả cuối.

### Phân biệt credential failure và dependency failure

Password sai khác với database timeout. Nếu gộp cả hai vào invalid_credential, detection sẽ hiểu sai và người vận hành có thể khóa nhầm account.

Reason code có thể gồm:

- invalid_credential
- account_disabled
- account_suspended
- mfa_required
- mfa_denied
- challenge_expired
- rate_limited
- issuer_untrusted
- audience_mismatch
- signature_invalid
- session_revoked
- dependency_unavailable
- policy_denied
- internal_error

Không đưa exception stack, raw SQL error hoặc nội dung token vào reason code. Chi tiết kỹ thuật cần được lưu trong log vận hành đã redact và có quyền truy cập phù hợp.

## 9. Thời gian, ordering và correlation

Điều tra chuỗi xác thực cần biết thứ tự tương đối của sự kiện qua nhiều service.

### Timestamp

- Dùng UTC và định dạng timestamp thống nhất.
- Phân biệt occurred_at với observed_at.
- Đồng bộ đồng hồ bằng nguồn time synchronization đáng tin.
- Ghi nhận clock skew nếu vượt ngưỡng.
- Không suy ra thứ tự tuyệt đối chỉ từ timestamp của các máy có đồng hồ lệch.

### Event ordering

Một event có thể được phát ở service A, chuyển qua broker và đến SIEM sau event từ service B. Thứ tự nhận không nhất thiết là thứ tự xảy ra.

Có thể dùng:

- event sequence theo aggregate/session/account.
- event version hoặc state version.
- occurred_at và observed_at.
- correlation/interaction ID.
- causation ID để biểu diễn event nào gây ra event nào.

Không yêu cầu ordering toàn cục nếu hệ thống không có cơ chế bảo đảm. Thường chỉ cần ordering trong phạm vi account, session hoặc transaction.

### Correlation

Một login flow có thể phát event ở Gateway, IdP, RP và Session Service. Correlation ID giúp liên kết chúng mà không phải truyền session cookie hoặc token vào log.

- Tạo correlation ID tại boundary tin cậy.
- Giữ nguyên qua downstream theo propagation policy.
- Không cho client tùy ý chọn giá trị có thể gây collision hoặc log injection.
- Có thể lưu parent/cause reference khi tạo event mới.
- Redact identifier nếu có thể liên kết trực tiếp tới cá nhân ngoài phạm vi cần thiết.

## 10. Reliable event delivery và transactional outbox

Nếu ứng dụng commit thay đổi session vào database nhưng event publish thất bại, audit trail có thể thiếu sự kiện. Nếu publish event trước khi commit rồi transaction rollback, log lại ghi một hành động chưa xảy ra.

### Transactional outbox

Outbox lưu event trong cùng transaction với thay đổi nghiệp vụ. Một publisher riêng đọc outbox và gửi event tới broker; sau đó đánh dấu đã publish.

~~~mermaid
flowchart TD
    R["Authentication request"] --> T["Database transaction"]
    T --> S["Update session / account state"]
    T --> O["Insert outbox event"]
    S --> C["Commit transaction"]
    O --> C
    C --> P["Outbox publisher"]
    P --> B["Message broker"]
    B --> L["Log / audit pipeline"]
    L --> SIEM["SIEM / detection"]
~~~

### Vì sao hữu ích?

- State change và event record được commit cùng nhau.
- Publisher có thể retry khi broker unavailable.
- Consumer có thể deduplicate theo event_id.
- Event không bị mất chỉ vì network tạm thời lỗi sau commit.

### At-least-once và duplicate

Outbox publisher có thể gửi lại event nếu broker nhận message nhưng publisher chưa ghi nhận acknowledgement. Vì vậy consumer nên idempotent và deduplicate theo event_id.

Không giả định exactly-once end-to-end. Thiết kế cần chấp nhận duplicate delivery và đảm bảo side effect ở consumer không bị lặp ngoài ý muốn.

## 11. Bảo vệ pipeline thu thập event

Event có thể đi qua collector, queue, broker, stream processor, data lake và SIEM. Mỗi hop là một trust boundary.

### Kiểm soát

- Producer authentication bằng workload identity hoặc mTLS.
- Broker ACL theo topic/tenant/event family.
- TLS cho transport.
- Schema registry hoặc schema validation.
- Size limit và rate limit để chống event flood.
- Dead-letter queue cho message không hợp lệ.
- Retry có backoff và giới hạn.
- Consumer identity riêng.
- Tách quyền publish, consume, query và administer.
- Theo dõi queue lag, drop rate và delivery delay.

### Không tin payload chỉ vì broker nhận được

Một producer có thể bị compromise hoặc có quyền publish nhầm topic. Consumer cần kiểm tra producer identity, schema, tenant và event type theo policy. Với audit event quan trọng, có thể cần chữ ký hoặc integrity envelope bổ sung.

### Multi-tenant pipeline

Không cho tenant A đọc event của tenant B. Tenant context phải do producer tin cậy xác định và được xác minh tại ingestion. Không dùng tenant ID trong payload làm ranh giới bảo mật duy nhất nếu producer không được xác thực.

## 12. Tính toàn vẹn và chống sửa/xóa audit event

Audit record có giá trị khi người có quyền bị kiểm toán không thể âm thầm thay đổi lịch sử.

### Các lớp bảo vệ

- Append-only write path cho audit store.
- Quyền xóa/sửa tách khỏi quyền ghi event.
- Immutable/WORM storage khi yêu cầu retention.
- Encryption at rest và key management.
- Hash chain hoặc signed batch để phát hiện thay đổi.
- Trusted timestamp hoặc external anchoring khi cần.
- Backup và kiểm tra restore.
- Audit mọi hành động truy cập, export, retention và policy change.

### Hash chain minh họa

~~~text
H0 = initial_anchor
H1 = HASH(H0 || canonical_event_1)
H2 = HASH(H1 || canonical_event_2)
H3 = HASH(H2 || canonical_event_3)
...
~~~

Nếu một event giữa chuỗi bị sửa, hash tiếp theo không còn khớp. Tuy nhiên, hash chain đơn lẻ không ngăn attacker có toàn quyền trên cả dữ liệu và anchor tạo lại toàn bộ chuỗi. Cần bảo vệ key/anchor độc lập, phân tách quyền và lưu bản checkpoint ở nơi tin cậy khác.

### Không đồng nhất integrity với confidentiality

Chữ ký/hash giúp phát hiện sửa đổi nhưng không che giấu dữ liệu. Audit store vẫn cần encryption, access control, minimization và retention.

## 13. Bảo vệ dữ liệu nhạy cảm và privacy

Authentication event thường chứa thông tin có thể liên kết tới cá nhân hoặc credential. Ghi quá nhiều dữ liệu làm tăng hậu quả khi log bị lộ.

### Không ghi trực tiếp

- Password, password reset token hoặc OTP.
- TOTP seed, recovery code và private key.
- Session cookie, refresh token hoặc access token nguyên vẹn.
- Authorization code và PKCE verifier.
- Full SAML assertion/OIDC token nếu không có nhu cầu và bảo vệ đặc biệt.
- Secret manager response hoặc JDBC password.
- Nội dung request body có credential.
- Screenshot chứa secret hoặc recovery material.

### Dữ liệu cần cân nhắc

- Email, username và phone.
- IP address và geolocation.
- User agent/device fingerprint.
- Tenant membership và role.
- Authentication history.
- Risk score và behavioral signals.

Các trường này có thể là dữ liệu cá nhân. Cần mục đích xử lý, access policy, retention và pseudonymization phù hợp.

### Pseudonymization

Thay vì ghi email thô, có thể dùng internal subject reference hoặc HMAC-based pseudonym với key quản lý riêng. Hash không có key đối với email/phone dễ bị dò dictionary vì không gian giá trị nhỏ.

Pseudonymization không đồng nghĩa anonymization. Nếu tổ chức vẫn có thể liên kết reference về người dùng, dữ liệu vẫn cần được bảo vệ theo policy.

### Redaction theo nhiều lớp

- Redact ở application logger.
- Redact ở gateway/proxy.
- Redact ở tracing instrumentation.
- Redact ở error reporter.
- Kiểm tra message broker/dead-letter payload.
- Redact khi export và chia sẻ ticket.
- Scan log định kỳ để phát hiện secret leakage.

Không dựa vào một regex cuối pipeline để xử lý mọi loại secret; tốt nhất là không đưa secret vào event ngay từ đầu.

## 14. Retention, access control và data lifecycle

Không giữ mọi event mãi mãi. Retention phụ thuộc mục đích, mức rủi ro, yêu cầu pháp lý và khả năng điều tra.

### Phân lớp lưu trữ

- Hot storage: dữ liệu gần đây để alert và điều tra nhanh.
- Warm storage: dữ liệu cần truy vấn định kỳ.
- Archive: audit cần giữ lâu hơn nhưng ít truy cập.
- Expired/deleted: hết retention hoặc có yêu cầu xử lý theo policy.

### Access control

- SOC có quyền query event phục vụ detection.
- Auditor có quyền đọc audit theo phạm vi.
- Application operator không mặc nhiên được đọc mọi event người dùng.
- Developer chỉ truy cập dữ liệu đã giảm nhạy cảm ở môi trường cần thiết.
- Export/download cần audit và approval theo policy.
- Quyền quản trị retention tách khỏi quyền điều tra.

### Retention policy cần nêu

- Loại event và mục đích.
- Thời gian giữ ở hot/warm/archive.
- Ai được đọc và export.
- Quy trình legal hold nếu áp dụng.
- Cách xóa an toàn khi hết hạn.
- Backup/replica có cùng lịch lifecycle hay không.
- Cách xử lý subject deletion và yêu cầu pháp lý.

Không đặt một thời hạn chung cho tất cả dữ liệu nếu mức nhạy cảm và nghĩa vụ khác nhau.

## 15. Detection: từ event đến tín hiệu bất thường

Event là dữ liệu đầu vào. Detection rule kết hợp nhiều event và context để phát hiện hành vi có thể nguy hiểm.

### Một số detection use case

| Tín hiệu | Event cần tương quan | Hành động gợi ý |
| --- | --- | --- |
| Brute force | Nhiều login failure cho một account/source. | Throttle, challenge, alert. |
| Password spraying | Một source thử ít password trên nhiều account. | Rate limit theo source/tenant và điều tra. |
| Credential stuffing | Nhiều account có failure rồi success từ cùng automation pattern. | Risk step-up, block nguồn và kiểm tra account. |
| MFA fatigue | Nhiều push challenge bị deny hoặc timeout. | Chặn push tạm thời, cảnh báo user. |
| Impossible travel | Login thành công từ vị trí xa bất thường trong khoảng ngắn. | Risk evaluation; không kết luận chỉ từ IP. |
| Session theft | Session được dùng từ context khác hoặc sau revoke. | Revoke session và điều tra. |
| Recovery abuse | Reset, recovery hoặc đổi email/phone bất thường. | Hold, step-up và human review. |
| New authenticator | Passkey/MFA mới sau login rủi ro. | Notify, step-up và review. |
| Privilege change | Admin thay đổi role/MFA/federation policy. | Audit alert và approval review. |
| Token misuse | Wrong audience, unusual client, token refresh anomaly. | Deny, revoke grant hoặc disable client. |
| Workload compromise | Service identity mới gọi nhiều API ngoài baseline. | Revoke workload identity và contain. |

### Detection không phải kết luận chắc chắn

IP có thể thay đổi do VPN, mobile network hoặc NAT. Device fingerprint có thể không ổn định. Một login ở vị trí xa không tự chứng minh account takeover. Detection nên kết hợp nhiều tín hiệu, confidence, asset criticality và policy.

## 16. Correlation xuyên IdP, RP, gateway và session service

Một login flow có thể tạo nhiều event:

1. Gateway nhận request.
2. RP tạo OIDC authorization transaction.
3. IdP xác thực password/passkey.
4. MFA provider xử lý challenge.
5. IdP phát authorization response.
6. RP validate callback.
7. Session service tạo session.
8. API nhận request đầu tiên.

Nếu không có correlation, điều tra viên chỉ thấy các mảnh rời rạc.

### Correlation strategy

- Dùng interaction_id cho một flow xác thực.
- Dùng trace_id cho distributed request tracing.
- Dùng event_id riêng cho từng event.
- Dùng session_ref pseudonymized cho event gắn với session.
- Dùng account reference ổn định trong namespace nội bộ.
- Dùng causation_id để nối event phát sinh từ event trước.
- Không dùng token, cookie hoặc raw authorization code làm ID.

### Ví dụ timeline

~~~text
09:15:00.010  login.initiated          interaction=I-91
09:15:00.120  password.verified       interaction=I-91 outcome=success
09:15:00.180  mfa.challenge_created   interaction=I-91
09:15:06.410  mfa.approved            interaction=I-91
09:15:06.600  oidc.callback_accepted  interaction=I-91
09:15:06.720  session.created         interaction=I-91
09:16:02.050  session.used            session_ref=S-21
~~~

Timeline minh họa giúp thấy thứ tự và khoảng thời gian. Event collector vẫn phải xử lý clock skew và late arrival.

## 17. Alert design và vận hành SOC

Alert tốt cần giúp người nhận hiểu điều gì xảy ra và hành động nào phù hợp.

### Thành phần alert

- Alert ID và rule/version.
- Severity và confidence.
- Principal/tenant reference đã bảo vệ.
- Event references liên quan.
- Time window.
- Detection rationale.
- Suggested triage steps.
- Owner/on-call và escalation path.
- Status: new, acknowledged, investigating, contained, closed.

### Tránh alert fatigue

- Group các event cùng incident.
- Suppress duplicate alert có TTL.
- Phân biệt signal đơn lẻ với pattern nhiều tín hiệu.
- Dùng threshold theo tenant/service baseline.
- Theo dõi false positive và false negative.
- Có rule owner và review định kỳ.
- Không gửi raw credential hoặc PII quá mức vào chat/notification.

### Severity

Severity phụ thuộc khả năng khai thác, quyền tài khoản, dữ liệu và hậu quả. Nhiều login failure trên account thường có thể là Medium; một admin account có login bất thường kèm thay đổi MFA có thể là High/Critical theo context.

## 18. Metrics và SLO cho authentication

Metrics cho biết hệ thống có đang hoạt động đúng và ổn định không. Chúng không thay thế audit event.

### Metrics gợi ý

- Login success/failure rate.
- MFA challenge success/denial/expiry rate.
- Passkey authentication success rate.
- Token issuance and introspection latency.
- Session creation/revocation latency.
- Password reset/recovery completion rate.
- IdP dependency error rate.
- Event publish failure và outbox backlog.
- Event ingestion lag và dropped event count.
- Queue depth, consumer lag và dead-letter count.
- Audit storage write latency.
- Detection-to-alert latency.

### Cardinality

Không gắn email, username, session ID hoặc token ID làm metric label. Số lượng label tăng không giới hạn làm hệ thống metrics quá tải và có thể rò dữ liệu cá nhân. Dùng label có tập giá trị nhỏ như event_type, outcome, auth_method, environment và service.

### SLO

SLO có thể xác định latency cho login, availability của token endpoint, tỷ lệ event quan trọng được ghi nhận trong thời hạn và thời gian phát alert. Đặt SLO dựa trên yêu cầu sản phẩm và threat model; không lấy một con số tùy ý làm chuẩn chung.

## 19. Java: định nghĩa event có cấu trúc

Ứng dụng Java nên dùng schema/type rõ thay vì ghép chuỗi log tự do.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public record AuthenticationEvent(
        String eventId,
        String eventType,
        int eventVersion,
        Instant occurredAt,
        String producer,
        String actorRef,
        String subjectRef,
        String tenantRef,
        String outcome,
        String reasonCode,
        String authMethod,
        String correlationId,
        String policyVersion,
        Map<String, String> safeAttributes
) {
    public static AuthenticationEvent loginFailure(
            String actorRef,
            String tenantRef,
            String correlationId,
            String reasonCode
    ) {
        return new AuthenticationEvent(
                UUID.randomUUID().toString(),
                "authentication.login.failed",
                1,
                Instant.now(),
                "identity-api",
                actorRef,
                actorRef,
                tenantRef,
                "failure",
                reasonCode,
                "password",
                correlationId,
                "login-policy-12",
                Map.of()
        );
    }
}
~~~

Đây là record minh họa. Production cần schema validation, field constraints, event versioning, producer identity, redaction và không cho caller tùy ý đặt actor/subject. Instant.now() dùng đồng hồ hệ thống; môi trường cần time synchronization và có thể bổ sung observed_at tại collector.

### Không serialize credential vào event

Không đưa Authentication object, HTTP request, headers hoặc DTO chứa password/token vào serializer. Tạo event DTO riêng với allowlist field. Cách này giảm nguy cơ vô tình log secret khi model ứng dụng được mở rộng.

## 20. Java: transactional outbox minh họa

Nếu authentication state và event cần nhất quán, có thể ghi event vào outbox trong cùng transaction.

~~~sql
CREATE TABLE authentication_outbox (
    event_id VARCHAR(100) PRIMARY KEY,
    event_type VARCHAR(200) NOT NULL,
    event_version INTEGER NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    payload JSON NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
~~~

Schema SQL cần điều chỉnh theo DBMS; JSON type, index, locking và cleanup strategy khác nhau theo engine.

### Luồng xử lý

~~~java
@Transactional
public void revokeSession(String sessionRef, String actorRef) {
    sessionRepository.markRevoked(sessionRef);

    AuthenticationEvent event = eventFactory.sessionRevoked(
            sessionRef,
            actorRef
    );

    outboxRepository.insert(event);
}
~~~

Publisher chạy riêng đọc event chưa publish, gửi broker rồi cập nhật published_at. Cần xử lý crash giữa publish và update: event có thể được gửi lại, nên consumer deduplicate theo event_id.

Không gửi event ra broker trước khi transaction commit nếu event khẳng định một thay đổi trạng thái đã hoàn tất.

## 21. Schema evolution và interoperability

Event schema thay đổi theo thời gian khi có phương thức xác thực mới hoặc thêm field. Nếu không quản lý version, consumer cũ có thể parse sai hoặc bỏ qua dữ liệu quan trọng.

### Nguyên tắc

- Có event_version hoặc schema version.
- Thay đổi tương thích ngược khi có thể.
- Field mới nên optional hoặc có default semantics rõ.
- Không đổi nghĩa field hiện có mà giữ nguyên version.
- Không tái sử dụng event type cũ cho hành động khác.
- Consumer bỏ qua field không biết theo quy tắc an toàn.
- Breaking change cần version mới và migration plan.
- Schema registry/contract test giúp producer và consumer thống nhất.

Có thể tham khảo các schema/chuẩn như Open Cybersecurity Schema Framework (OCSF), Elastic Common Schema (ECS) hoặc OpenTelemetry Logs để mapping và interoperability. Không nhất thiết ép mọi hệ thống dùng nguyên schema bên ngoài; quan trọng là định nghĩa canonical event model và mapping có tài liệu.

## 22. Failure mode và resilience

Event pipeline có thể lỗi độc lập với authentication path. Cần xác định event nào bắt buộc phải lưu đồng bộ và event nào có thể gửi bất đồng bộ.

### Các tình huống

- Broker unavailable.
- Outbox publisher dừng.
- Collector mất kết nối.
- Queue đầy.
- Schema registry không khả dụng.
- Consumer lỗi parse event.
- Clock lệch.
- Event đến muộn hoặc trùng.
- Storage hết dung lượng.
- Signing key hoặc certificate của producer bị revoke.

### Chính sách

- Với audit-critical state change, ưu tiên transactional outbox hoặc durable local queue.
- Với debug telemetry, có thể drop có kiểm soát nhưng phải có metric báo drop.
- Không làm login path mất khả dụng chỉ vì một metrics backend lỗi.
- Không âm thầm bỏ event audit bắt buộc.
- Có backpressure, bounded retry, dead-letter và replay tool có kiểm soát.
- Khi audit store không khả dụng, quyết định fail-closed hay queue local theo mức rủi ro và yêu cầu pháp lý.
- Theo dõi backlog và thời gian phục hồi.

Phải phân biệt event loss với authentication failure. Người dùng không nên nhận lỗi login chỉ vì dashboard metrics không truy cập được; nhưng một hành động đặc quyền có thể phải chờ khi audit bắt buộc chưa được ghi bền vững.

## 23. Incident response dựa trên authentication event

Event giúp dựng timeline và xác định phạm vi ảnh hưởng. Runbook cần biến detection thành hành động có thể kiểm chứng.

### Quy trình

1. **Triage:** xác định alert, principal, tenant, event family và time window.
2. **Correlate:** nối event từ IdP, RP, gateway, session store, token service và resource API.
3. **Validate:** kiểm tra event source, producer identity, integrity và khả năng false positive.
4. **Scope:** xác định account, session, token, authenticator, workload và dữ liệu liên quan.
5. **Contain:** revoke session/token/grant, suspend account hoặc workload identity theo policy.
6. **Preserve evidence:** bảo toàn audit log, event references và chain of custody.
7. **Recover:** reset credential, re-enroll authenticator hoặc khôi phục account qua kênh tin cậy.
8. **Review:** tìm thay đổi recovery, privilege, federation, API key và dữ liệu đã truy cập.
9. **Improve:** cập nhật detection, policy, test và runbook.
10. **Close:** ghi quyết định, owner, thời gian containment và residual risk.

### Event cần ưu tiên khi điều tra account takeover

- Login success sau chuỗi failure.
- MFA denied/push fatigue trước login success.
- Passkey hoặc authenticator mới.
- Recovery email/phone thay đổi.
- Session mới từ context bất thường.
- Token refresh hoặc OAuth consent bất thường.
- Role/tenant membership thay đổi.
- Session revoke nhưng vẫn có request được chấp nhận.
- Data export hoặc API access sau thời điểm nghi compromise.

## 24. Ví dụ thực tế: Learning Platform

Learning Platform dùng IdP của trường, Learning Portal, Enrollment API, Session Service và Security Event Pipeline.

### Luồng đăng nhập bình thường

1. Portal khởi tạo login transaction và ghi event login.initiated.
2. IdP xác minh password hoặc passkey.
3. MFA service phát challenge và ghi outcome.
4. IdP trả authentication result cho Portal.
5. Portal xác minh issuer, state, nonce và token.
6. Session Service tạo session và ghi session.created.
7. Portal ghi nhận login success với interaction ID chung.
8. Event pipeline đưa event vào SIEM và dashboard.

### Phát hiện hành vi đáng ngờ

Một account có nhiều password failure từ nhiều network source, sau đó login success và thêm passkey mới. Detection kết hợp failure pattern, success, source change và authenticator enrollment. SOC nhận alert có event references, revoke session theo policy và liên hệ người dùng qua kênh tin cậy.

### Điều tra

Điều tra viên truy vấn interaction ID để nối IdP, MFA, Portal và Session Service. Audit cho biết login success xảy ra sau MFA approval; event tiếp theo cho thấy passkey được thêm. Hệ thống kiểm tra actor của enrollment event, source device và liệu user đã step-up trước khi thay đổi authenticator.

### Một event bị mất

Nếu broker ngừng hoạt động sau khi session được tạo, outbox giữ event bền vững và publisher retry khi broker phục hồi. Dashboard thể hiện ingestion lag; event không bị mất chỉ vì consumer tạm thời offline.

## 25. Kiểm thử authentication event và audit pipeline

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Login success | Đăng nhập bằng fixture hợp lệ. | Có event success với producer, actor, method và correlation. |
| Login failure | Dùng credential test sai. | Có event failure; không có password trong payload. |
| Account disabled | Login vào account disabled. | Outcome/reason đúng policy, không tạo session. |
| MFA denied | Từ chối challenge test. | Có event denied gắn đúng interaction. |
| MFA replay | Gửi lại challenge/response đã dùng trong lab. | Bị từ chối; event thể hiện replay/invalid state. |
| Passkey enrollment | Đăng ký passkey test. | Có event registration với actor/subject và credential reference đã bảo vệ. |
| Passkey removal | Xóa authenticator. | Có event removal và actor đúng. |
| OIDC callback | Hoàn tất flow test. | Event thể hiện issuer/client và kết quả; không chứa token/code. |
| SAML rejection | Gửi assertion sai audience trong lab. | Event rejection có reason code chuẩn hóa. |
| Session rotation | Login và kiểm tra session ID đổi. | Có event session created/rotated, không log cookie. |
| Logout/revoke | Revoke session. | Event success chỉ sau khi state commit; session cũ bị từ chối. |
| Recovery | Hoàn tất reset bằng fixture token. | Có event requested/completed; token không xuất hiện. |
| Admin policy change | Thay đổi MFA policy bằng admin test. | Audit ghi actor, target, policy version và approval nếu cần. |
| Actor spoofing | Gửi header actor giả từ client. | Event lấy actor từ trusted context, không từ header tùy ý. |
| Duplicate delivery | Gửi cùng event_id hai lần. | Consumer deduplicate hoặc xử lý idempotent. |
| Out-of-order | Gửi event version cũ sau event mới. | Consumer không ghi đè state mới. |
| Clock skew | Mô phỏng node lệch giờ. | occurred_at/observed_at phân biệt; cảnh báo skew. |
| Broker outage | Ngắt broker sau transaction. | Outbox giữ event và retry; không mất audit-critical event. |
| Publisher crash | Crash sau publish trước acknowledgement. | Duplicate được xử lý an toàn. |
| Schema mismatch | Gửi event version không hỗ trợ. | Reject/quarantine hoặc xử lý tương thích theo policy. |
| Secret redaction | Scan payload/log/trace. | Không có password, OTP, token, cookie hoặc private key. |
| PII minimization | Kiểm tra email/IP/device fields. | Chỉ lưu trường cần thiết, có pseudonymization/retention. |
| Tamper detection | Sửa bản copy audit trong test store. | Integrity control phát hiện thay đổi. |
| Access control | User không có quyền query audit tenant khác. | Query/export bị từ chối và được audit. |
| Retention | Chạy lifecycle policy trên fixture cũ. | Dữ liệu hết hạn được xử lý đúng policy và backup. |
| Event flood | Tạo burst trong giới hạn lab. | Rate limit/backpressure hoạt động; drop/lag được đo. |
| Detection rule | Phát chuỗi failure rồi success test. | Alert được tạo, có rationale và event references. |
| Alert deduplication | Phát lại cùng pattern trong window. | Alert được group/suppress theo rule. |
| Incident drill | Mô phỏng session compromise. | SOC correlate, revoke và preserve evidence đúng runbook. |
| Multi-tenant isolation | Query event của tenant khác. | Không truy cập được ngoài quyền. |

## 26. Checklist triển khai

- [ ] Có taxonomy cho login, MFA, passkey, federation, token, session, recovery và admin event.
- [ ] Mỗi event có event ID, type/version, timestamp, producer, actor/subject và outcome phù hợp.
- [ ] Actor, subject, producer và source được phân biệt.
- [ ] Event phát sinh từ thành phần có thẩm quyền và sau khi biết kết quả thực tế.
- [ ] Không lấy identity từ header hoặc payload do client tự khai.
- [ ] Correlation ID/trace ID được truyền qua hop mà không dùng token/cookie làm identifier.
- [ ] Timestamp UTC, occurred_at và observed_at được phân biệt.
- [ ] Ordering, duplicate và late event được xử lý theo policy.
- [ ] Audit-critical event dùng outbox/durable delivery hoặc cơ chế tương đương.
- [ ] Producer/consumer xác thực; broker ACL và tenant isolation được cấu hình.
- [ ] Schema validation, versioning và compatibility test được duy trì.
- [ ] Không ghi password, OTP, recovery code, token, cookie, authorization code hoặc private key.
- [ ] PII được tối thiểu hóa, pseudonymize và có retention policy.
- [ ] Audit store có append-only/integrity protection và backup.
- [ ] Quyền query/export/delete audit được tách biệt và ghi nhận.
- [ ] Detection bao phủ brute force, stuffing, MFA fatigue, recovery abuse và session anomalies.
- [ ] Alert có severity, confidence, event references, owner và triage steps.
- [ ] Metrics tránh high-cardinality identifier và không chứa PII không cần thiết.
- [ ] Có SLO cho event delivery/ingestion lag và alert latency.
- [ ] Có runbook khi broker, collector, storage hoặc signing key gặp sự cố.
- [ ] Có kiểm thử outage, duplicate, out-of-order, clock skew, tamper và redaction.
- [ ] Có quy trình rà soát detection rule, false positive và retention định kỳ.

## 27. Tự kiểm tra

**Câu 1.** Authentication event là gì?

**Đáp án:** Là bản ghi có cấu trúc mô tả hành động hoặc kết quả liên quan đến xác thực, credential, MFA, session, recovery hoặc identity lifecycle.

**Câu 2.** Authentication event khác metric như thế nào?

**Đáp án:** Event mô tả một lần xảy ra cụ thể với actor, outcome và context; metric tổng hợp số lượng/tỷ lệ để theo dõi xu hướng và SLO.

**Câu 3.** Actor và subject khác nhau thế nào?

**Đáp án:** Actor thực hiện hành động; subject là tài khoản/chủ thể bị tác động hoặc được đại diện. Ví dụ operator là actor khi reset authenticator cho học viên là subject.

**Câu 4.** Vì sao không ghi access token hoặc session cookie vào event?

**Đáp án:** Chúng là bearer credential. Người có được log có thể dùng chúng để truy cập hệ thống; event chỉ cần reference đã bảo vệ hoặc metadata tối thiểu.

**Câu 5.** occurred_at khác observed_at thế nào?

**Đáp án:** occurred_at là thời điểm nguồn cho biết hành động xảy ra; observed_at là thời điểm collector nhận event. Chênh lệch giúp đo pipeline lag và xử lý event đến muộn.

**Câu 6.** Transactional outbox giải quyết vấn đề gì?

**Đáp án:** Nó ghi state change và event trong cùng transaction, sau đó publisher retry gửi event. Điều này giảm nguy cơ trạng thái đã commit nhưng audit event bị mất.

**Câu 7.** Vì sao consumer phải xử lý duplicate event?

**Đáp án:** At-least-once delivery có thể gửi lại khi publisher không nhận acknowledgement. Consumer cần deduplicate hoặc idempotent theo event ID.

**Câu 8.** Hash chain có tự ngăn mọi sửa đổi audit log không?

**Đáp án:** Không. Hash chain giúp phát hiện sửa đổi, nhưng anchor/key phải được bảo vệ độc lập; attacker kiểm soát cả dữ liệu và anchor có thể tạo lại chuỗi.

**Câu 9.** Vì sao không nên dùng email hoặc session ID làm metric label?

**Đáp án:** Chúng tạo cardinality cao, tăng chi phí và có thể rò dữ liệu cá nhân hoặc credential reference. Dùng label có tập giá trị nhỏ, tổng hợp.

**Câu 10.** Một chuỗi login failure rồi success có chứng minh account takeover không?

**Đáp án:** Không. Đây là tín hiệu cần correlation với source, MFA, session, authenticator change và hành vi sau login. Detection tạo alert để điều tra, không tự kết luận chỉ từ một pattern.

## Ghi nhớ

**Authentication event** cung cấp dấu vết có cấu trúc về việc danh tính được xác minh, credential được thay đổi, session được tạo/thu hồi và policy được áp dụng. Event cần taxonomy và schema ổn định, actor/subject/producer rõ ràng, timestamp/correlation đáng tin và được phát sinh từ thành phần có thẩm quyền.

Một pipeline tốt phải xác thực producer, bảo đảm delivery và xử lý duplicate/out-of-order, bảo vệ integrity, giới hạn quyền truy cập và giữ dữ liệu theo retention phù hợp. Không ghi password, OTP, token, cookie, recovery code hoặc private key; chỉ giữ context tối thiểu để phát hiện và điều tra. Kết hợp event với metric, trace, detection rule và incident runbook để biến dữ liệu quan sát thành hành động bảo mật. **Audit có giá trị khi sự kiện đúng, đủ, có nguồn tin cậy, bảo vệ được và có thể truy vết mà không làm lộ credential.**
