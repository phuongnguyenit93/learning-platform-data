# Thiết lập audit và alert

**Thiết lập audit và alert** là bài thực hành tổng hợp để biến các hoạt động xác thực thành bằng chứng có cấu trúc, lưu giữ đáng tin cậy và tín hiệu cảnh báo có thể hành động. Một hệ thống authentication có thể xác minh password, MFA, passkey, token và session đúng, nhưng vẫn khó phát hiện account takeover nếu không ghi nhận được ai đã làm gì, vào lúc nào, trên tài khoản nào, bằng phương thức nào và kết quả ra sao. Ngược lại, nếu ghi quá nhiều dữ liệu, audit store và SIEM có thể trở thành nơi tập trung password, OTP, session cookie, token và dữ liệu cá nhân.

Trong bài này, người học sẽ thiết kế và triển khai một luồng hoàn chỉnh cho StudyHub: xác định sự kiện cần audit, chuẩn hóa event schema, phát event tại đúng điểm quyết định, vận chuyển và lưu trữ có kiểm soát, xây detection rule, gửi alert tới đúng người phụ trách và kiểm thử khả năng phát hiện cũng như phản ứng. Kết quả không chỉ là dashboard có nhiều biểu đồ; hệ thống phải giữ được bằng chứng, phát hiện được hành vi đáng ngờ và hướng dẫn đội vận hành hành động đúng.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn. Trong chương **Thực hành tổng hợp**, bài này kết nối các kiến thức đó thành một hệ thống audit và alert có thể vận hành.

## 1. Kết quả cần đạt

Sau bài thực hành, người học có thể:

1. Xác định tài sản, threat scenario và authentication flow cần audit.
2. Phân biệt security audit event, application log, metric, trace và alert.
3. Xây event taxonomy cho login, password, MFA, passkey, token, session, recovery, identity link và admin action.
4. Thiết kế schema có actor, subject, action, outcome, timestamp, correlation và policy context.
5. Ngăn secret và dữ liệu cá nhân không cần thiết đi vào log, queue, SIEM, trace hoặc alert.
6. Phát event tại điểm quyết định và bảo đảm event quan trọng không bị mất khi service crash.
7. Xử lý duplicate, out-of-order, retry, schema evolution và event đến muộn.
8. Bảo vệ audit store bằng phân quyền, encryption, integrity, retention và backup.
9. Xây detection rule có window, grouping key, threshold, severity, confidence và owner.
10. Thiết kế alert payload, deduplication, suppression, triage và incident runbook.
11. Kiểm thử từ producer tới alert, bao gồm event loss, redaction, tamper, false positive và recovery.
12. Đánh giá hiệu quả bằng coverage, detection latency, alert quality và response time.

## 2. Bối cảnh thực hành: StudyHub

StudyHub có web app và mobile app. Người dùng là học viên, giảng viên hoặc quản trị viên tenant. Tài khoản có thể dùng password, passkey, TOTP hoặc push MFA. Một số luồng đăng nhập qua external identity provider bằng OAuth 2.0/OpenID Connect. Web app dùng session cookie; mobile app dùng access token và refresh token rotation. Người dùng có thể quản lý thiết bị, liên kết identity, đổi recovery contact và khôi phục tài khoản.

### 2.1. Kiến trúc giả định

| Thành phần | Trách nhiệm | Event cần phát |
| --- | --- | --- |
| Web/Mobile Gateway | Nhận request và áp dụng rate limit | Request accepted/limited, client context. |
| Identity Service | Điều phối login và policy | Login requested/success/failure, risk decision. |
| Credential Store | Lưu password verifier và credential metadata | Credential changed/enrolled/revoked, không log secret. |
| MFA Service | Tạo và xác minh challenge | Challenge issued/approved/denied/expired. |
| Passkey Service | Xác minh WebAuthn registration/assertion | Registration/assertion success/failure. |
| Authorization Server | Cấp và thu hồi token/grant | Token issued/rotated/revoked/reuse detected. |
| Session Service | Tạo, rotate, expire và revoke session | Session lifecycle event. |
| Recovery Service | Khôi phục tài khoản | Recovery requested/verified/completed/denied. |
| Identity Link Service | Liên kết/gỡ external identity | Identity linked/unlinked/denied. |
| Risk Engine | Phân tích tín hiệu và quyết định step-up/deny | Risk evaluated, step-up required, policy deny. |
| Audit Outbox/Collector | Nhận, kiểm tra và vận chuyển event | Ingestion, schema rejection, queue health. |
| Audit Store | Lưu record cần truy vết | Durable audit record, integrity checkpoint. |
| Detection Engine/SIEM | Correlation và phát hiện hành vi | Detection match, alert created/suppressed. |
| Notification/Case Service | Chuyển alert và quản lý xử lý | Alert delivered/acknowledged/escalated/closed. |
| Course API | Kiểm tra quyền truy cập tài nguyên | Access allowed/denied cho hành động nhạy cảm. |

### 2.2. Luồng cần bảo vệ

- Login password: nhận request, kiểm tra account, verify password, áp risk policy, yêu cầu MFA nếu cần, tạo session/token.
- Login passkey: tạo challenge, xác minh assertion, kiểm tra user verification và tạo session.
- MFA: phát challenge, nhận approval/OTP, xác minh đúng transaction và giới hạn replay.
- Token refresh: kiểm tra refresh token, rotate token family, phát hiện reuse.
- Session: tạo, rotate, expire và revoke.
- Credential management: thêm/gỡ passkey, TOTP, security key hoặc push factor.
- Account recovery: yêu cầu proof, thay recovery factor và kết thúc recovery.
- Identity linking: xác minh identity hiện tại và provider mới trước khi link.
- Admin action: thay đổi authentication policy, reset factor hoặc hỗ trợ recovery.

Không phải mỗi request đều cần một audit record dài. Hãy chọn các sự kiện có ý nghĩa bảo mật, quyết định policy, thay đổi trạng thái hoặc tạo bằng chứng điều tra. Metric và trace bổ sung khả năng vận hành nhưng không thay thế audit record bắt buộc.

## 3. Phạm vi, tài sản và threat model

Trước khi cấu hình công cụ, xác định điều gì cần phát hiện và hậu quả nếu không phát hiện.

### 3.1. Tài sản

| Tài sản | Hậu quả nếu bị lạm dụng | Audit cần hỗ trợ |
| --- | --- | --- |
| Account và identity | Account takeover, impersonation | Login, recovery, identity link và account state. |
| Password verifier | Offline cracking nếu database bị lộ | Thay đổi credential và truy cập quản trị kho credential, không ghi verifier vào event. |
| MFA factor | Bypass MFA, fatigue, factor takeover | Enrollment, challenge, approval, deny, remove và recovery. |
| Passkey | Đăng nhập trái phép nếu credential bị liên kết sai | Registration, assertion, revoke và credential reference. |
| Session | Duy trì quyền truy cập sau login | Created, rotated, expired, revoked và replay signal. |
| Token/grant | API access và persistence | Issued, rotated, revoked, reuse và client/scope context. |
| Recovery channel | Chiếm tài khoản qua reset | Contact change, proof, recovery completion và notification. |
| Identity link | Đăng nhập qua provider không mong muốn | Issuer/subject reference, actor, subject và link state. |
| Audit evidence | Mất khả năng điều tra hoặc che giấu hành động | Event completeness, integrity, access và retention. |

### 3.2. Threat scenario cần phát hiện

1. Brute force: nhiều password được thử cho một account.
2. Password spraying: một số password được thử trên nhiều account.
3. Credential stuffing: cặp credential bị lộ được thử trên nhiều account.
4. MFA fatigue: nhiều challenge được gửi rồi một challenge được approve.
5. Enrollment takeover: session bị chiếm dùng để thêm authenticator mới.
6. Recovery abuse: recovery contact hoặc factor bị thay trái phép.
7. Token replay: refresh token đã rotate được dùng lại.
8. Session abuse: session được sử dụng từ context rủi ro hoặc sau revoke.
9. Identity-link abuse: external identity được liên kết mà không có proof phù hợp.
10. Privileged misuse: admin thay đổi policy hoặc reset factor ngoài quy trình.
11. Audit tampering/loss: event bị sửa, xóa, rơi hoặc pipeline ngừng phát.
12. Alert fatigue: quá nhiều alert trùng hoặc ít context khiến analyst bỏ qua.

### 3.3. Giả định và giới hạn

IP, geolocation, user-agent, device fingerprint và ASN là tín hiệu risk, không phải bằng chứng chắc chắn về danh tính. Một IP có thể đại diện cho nhiều người qua NAT; một người dùng có thể đổi mạng hoặc dùng VPN. Alert nên kết hợp nhiều tín hiệu, hành động thực tế, lịch sử account và policy outcome. Không tự động khóa tài khoản chỉ vì một IP lạ.

## 4. Phân biệt audit, log, metric, trace và alert

| Loại dữ liệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Audit event | Ai đã làm gì, với đối tượng nào, lúc nào và kết quả gì? | Admin reset MFA cho một account. |
| Application log | Code/service đã gặp điều gì khi chạy? | Credential database query timeout. |
| Metric | Tần suất, tỷ lệ và độ trễ thay đổi ra sao? | Login failure rate trong 5 phút. |
| Distributed trace | Một request đi qua service nào và chậm ở đâu? | Login từ gateway tới identity/MFA/session service. |
| Alert | Tín hiệu nào cần người hoặc hệ thống xử lý? | Refresh token reuse trên token family. |
| Incident/case | Ai đang điều tra, evidence nào được thu thập và xử lý đến đâu? | Case nghi ngờ account takeover. |

Một audit event có schema và semantics ổn định. Application log thường phục vụ debug và có thể thay đổi theo code. Metric tổng hợp dữ liệu, không đủ để dựng lại một hành động cụ thể. Trace có thể sampling và không nên là nguồn duy nhất cho audit. Alert là kết quả của detection rule; không phải mọi event đều cần tạo alert.

## 5. Thiết kế event taxonomy

Tên event phải ổn định, dễ query và không chứa dữ liệu động như email, IP hoặc username. Chọn quy ước nhất quán theo category và action/outcome.

| Category | Event type | Khi nào phát |
| --- | --- | --- |
| authentication | login.requested | Login request được nhận. |
| authentication | login.success | Toàn bộ authentication policy hoàn tất. |
| authentication | login.failure | Flow kết thúc thất bại. |
| authentication | password.verification.success | Password factor đúng, nhưng chưa chắc login hoàn tất. |
| authentication | password.verification.failure | Password factor không hợp lệ. |
| authentication | step_up.required | Policy yêu cầu xác thực tăng cường. |
| mfa | challenge.issued | Challenge được tạo/gửi. |
| mfa | challenge.approved | Challenge được xác minh thành công. |
| mfa | challenge.denied | Người dùng từ chối hoặc factor không chấp nhận. |
| mfa | challenge.expired | Challenge hết hạn. |
| credential | passkey.enrolled | Passkey được xác minh và lưu thành công. |
| credential | passkey.revoked | Passkey bị thu hồi. |
| credential | totp.enrolled | TOTP factor được xác minh và kích hoạt. |
| credential | factor.removed | Factor bị gỡ. |
| token | access_token.issued | Access token được cấp. |
| token | refresh_token.rotated | Refresh token được rotate. |
| token | refresh_token.reuse_detected | Token đã rotate bị dùng lại. |
| token | grant.revoked | Grant/token family bị thu hồi. |
| session | session.created | Session được tạo. |
| session | session.rotated | Session identifier được đổi. |
| session | session.revoked | Session bị thu hồi. |
| recovery | recovery.requested | Yêu cầu recovery được tiếp nhận. |
| recovery | recovery.completed | Proof đạt và recovery commit. |
| recovery | recovery.denied | Recovery bị từ chối. |
| identity | identity.linked | External identity được liên kết. |
| identity | identity.unlinked | External identity bị gỡ. |
| account | recovery_contact.changed | Recovery contact thay đổi. |
| admin | authentication_policy.changed | Admin thay đổi policy xác thực. |
| authorization | resource.access.denied | Resource access bị từ chối. |
| audit | event.ingestion.failed | Event không được ingest theo contract. |
| audit | pipeline.coverage_gap | Có khoảng thời gian hoặc nguồn event bị thiếu. |

### 5.1. Quy tắc semantics

- Phát event tại nơi quyết định được thực hiện, không chỉ tại UI.
- Phân biệt attempt, factor result và final login result.
- Chỉ phát login.success sau khi policy authentication hoàn tất; nếu session issuance là điều kiện thành công thì chờ session được tạo.
- Dùng event riêng cho denied, failure, expired, cancelled và error nếu chúng có ý nghĩa khác nhau.
- Không phát event thành công trước khi trạng thái được commit.
- Event admin phải có actor và subject riêng.
- Event recovery phải phân biệt request, proof verification và completion.
- Ghi policy version để giải thích quyết định ở thời điểm xảy ra.
- Định nghĩa owner và contract cho từng event type.

### 5.2. Sự kiện không nên bị gộp

Password verification success không đồng nghĩa login success nếu MFA còn pending. MFA challenge issued không đồng nghĩa challenge đã tới thiết bị. Token request nhận được không đồng nghĩa token đã được cấp. Recovery requested không đồng nghĩa tài khoản đã được khôi phục. Identity link started không đồng nghĩa identity đã được liên kết.

Nếu gộp các trạng thái này thành một event chung, dashboard và alert có thể đưa ra kết luận sai. Hãy phát event theo trạng thái thực tế, có outcome và reason code.

## 6. Thiết kế event schema

Một event tối thiểu cần có định danh, loại sự kiện, thời gian, actor, subject, kết quả, nguồn phát và correlation. Thêm context theo nguyên tắc cần biết.

| Field | Mục đích | Quy tắc |
| --- | --- | --- |
| event_id | Định danh duy nhất | Sinh ở producer hoặc outbox; ổn định khi retry. |
| schema_version | Version schema | Consumer phải xử lý version được hỗ trợ. |
| event_type | Taxonomy event | Không chứa PII/secret. |
| occurred_at | Thời điểm producer ghi nhận sự kiện | UTC, server clock đồng bộ. |
| observed_at | Thời điểm collector nhận event | Do collector bổ sung. |
| actor | Principal/service thực hiện | Dùng internal reference. |
| subject | Account/identity bị tác động | Dùng pseudonymous/internal reference. |
| target | Credential/session/token/resource bị tác động | Reference không thể dùng để truy cập. |
| outcome | success/failure/denied/pending/expired/error | Enum có tài liệu. |
| reason_code | Lý do chuẩn hóa | Không chứa input hoặc secret. |
| auth_method | Password/passkey/TOTP/certificate/SSO | Ghi phương thức thực tế. |
| client_id | Ứng dụng gọi | Client đã đăng ký. |
| source_service | Producer | Tên service và version. |
| tenant_ref | Tenant liên quan | Chỉ ghi khi cần phân tách điều tra. |
| network_context | Context mạng | Tối thiểu hóa, pseudonymize khi phù hợp. |
| device_context | Platform/browser/device class | Không coi fingerprint là proof. |
| session_ref | Tham chiếu session | Không phải raw cookie/session ID. |
| credential_ref | Tham chiếu credential | Không phải password, seed hay private key. |
| token_family_ref | Tham chiếu token family | Không phải token value. |
| correlation_id | Liên kết các bước trong một flow | Không dùng làm secret. |
| trace_id | Liên kết distributed trace | Audit không phụ thuộc trace sampling. |
| policy_version | Policy đã quyết định | Hữu ích cho điều tra và reproducibility. |

### 6.1. Event mẫu

~~~json
{
  "event_id": "evt_01JQ8Z6Q9K7M",
  "schema_version": "1.0",
  "event_type": "authentication.login.failure",
  "occurred_at": "2026-11-22T07:15:12.482Z",
  "observed_at": "2026-11-22T07:15:12.510Z",
  "actor": {
    "type": "user",
    "ref": "usr_7f3a91"
  },
  "subject": {
    "type": "account",
    "ref": "acct_2c9d11"
  },
  "target": {
    "type": "credential",
    "ref": "cred_81bd"
  },
  "outcome": "failure",
  "reason_code": "INVALID_CREDENTIAL",
  "auth_method": "password",
  "client_id": "studyhub-web",
  "tenant_ref": "tenant_04",
  "source_service": {
    "name": "identity-service",
    "version": "4.8.2"
  },
  "network_context": {
    "source_ref": "src_84ac",
    "country": "VN"
  },
  "correlation_id": "flow_19d2b6",
  "policy_version": "auth-policy-12"
}
~~~

Đây là dữ liệu giả lập. Các reference là định danh nội bộ không dùng để xác thực. Nếu điều tra cần IP gốc hoặc định danh trực tiếp, lưu ở vùng dữ liệu riêng với quyền và retention chặt hơn; không mặc định đưa chúng vào mọi event hoặc alert.

### 6.2. Actor và subject

Actor là principal hoặc service thực hiện hành động. Subject là account/identity chịu tác động. Ví dụ admin reset MFA cho user: actor là admin, subject là user. Nếu risk engine tự động revoke session, actor có thể là risk-engine service và subject là account. Không gán mọi event cho user chỉ vì thao tác được khởi tạo từ UI.

### 6.3. Outcome và reason code

Outcome nên có tập enum nhỏ, ổn định: success, failure, denied, pending, expired, cancelled, error. Reason code như INVALID_CREDENTIAL, MFA_CHALLENGE_EXPIRED, TOKEN_REUSE, ACCOUNT_DISABLED hoặc RISK_POLICY_DENY giúp query và correlation.

Không đưa password người dùng nhập, OTP, stack trace, raw request hoặc nội dung support ticket vào reason code. UI có thể dùng thông báo chung để tránh account enumeration, trong khi audit event giữ reason code nội bộ.

### 6.4. occurred_at và observed_at

occurred_at là thời điểm producer ghi nhận hành động; observed_at là thời điểm collector nhận event. Hai timestamp giúp đo queue delay, clock skew và event đến muộn. Dùng UTC, đồng bộ server clock và không tin client timestamp là nguồn chuẩn. Nếu cần client time để điều tra, lưu riêng và đánh dấu untrusted.

## 7. Phân loại dữ liệu và redaction

Audit event phải đủ dùng cho bảo mật nhưng không trở thành kho credential.

### 7.1. Tuyệt đối không ghi raw secret

Không ghi:
- Password hoặc password reset secret.
- OTP/TOTP code, TOTP seed, QR provisioning URI.
- Recovery code chưa sử dụng.
- Access token, refresh token, ID token hoặc authorization code.
- Session cookie, raw session ID hoặc CSRF secret.
- API key, client secret, private key hoặc signing key.
- PKCE code verifier, DPoP private key hoặc biometric template.
- Authorization, Cookie và Set-Cookie header nguyên vẹn.
- Request/response body có thể chứa secret.

Không chỉ redaction ở dashboard. Secret phải được loại bỏ tại producer, framework logging, gateway, APM agent và collector trước khi ingest. Nếu secret đã vào queue hoặc storage, ẩn nó ở UI không giải quyết được sự cố.

### 7.2. PII và network context

Email, phone, IP, user-agent, vị trí và device identifier có thể là dữ liệu cá nhân. Trước khi ghi, xác định:
- Mục đích phát hiện/điều tra.
- Field tối thiểu cần dùng.
- Ai được xem dữ liệu trực tiếp.
- Có thể dùng internal reference hoặc pseudonymization không.
- Retention bao lâu.
- Cách xóa khỏi replica, index và export.

Pseudonymization không tự động biến dữ liệu thành anonymous. Nếu reference có thể liên kết ngược về người dùng, vẫn phải bảo vệ như dữ liệu cá nhân.

### 7.3. Kiểm thử redaction

Tạo test payload cố ý có marker giả lập ở các trường nhạy cảm, ví dụ TEST_PASSWORD_MARKER, TEST_TOKEN_MARKER và TEST_OTP_MARKER. Sau khi đi qua producer, collector, queue, storage, SIEM và alert, tìm marker ở mọi nơi. Kết quả mong đợi là không marker nào xuất hiện. Không dùng secret thật làm marker test.

## 8. Phát event đáng tin cậy từ producer

Event nên được tạo tại điểm quyết định hoặc thay đổi trạng thái. Không dựa vào frontend để tuyên bố login thành công.

### 8.1. Điểm phát trong login flow

~~~mermaid
sequenceDiagram
    actor U as User
    participant W as Web App
    participant I as Identity Service
    participant M as MFA Service
    participant S as Session Service
    participant O as Audit Outbox
    U->>W: Submit credentials
    W->>I: Login request
    I->>O: login.requested
    I->>I: Verify password
    alt Password invalid
        I->>O: password.verification.failure
        I-->>W: Generic failure
    else Password valid
        I->>O: password.verification.success
        I->>M: Verify required factor
        M->>O: challenge.approved or denied
        alt Policy satisfied
            I->>S: Create session
            S->>O: session.created
            I->>O: login.success
            I-->>W: Authentication complete
        else Policy not satisfied
            I->>O: login.failure
            I-->>W: Authentication incomplete
        end
    end
~~~

Nếu session creation thất bại sau khi factor hợp lệ, phát event riêng cho lỗi provisioning/session. Không ghi login.success trước khi toàn bộ điều kiện thành công đã commit theo semantics của hệ thống.

### 8.2. Transactional outbox

Một lỗi phổ biến là cập nhật database thành công nhưng process crash trước khi gửi event, hoặc gửi event thành công rồi transaction database rollback. Transactional outbox giảm khoảng trống này:

1. Trong cùng transaction với thay đổi trạng thái, ghi audit event/outbox row.
2. Commit state và outbox atomically.
3. Worker đọc outbox và gửi event tới durable broker.
4. Sau khi broker xác nhận, đánh dấu outbox row đã publish.
5. Nếu worker crash, retry cùng event_id.
6. Consumer deduplicate theo event_id.

~~~mermaid
flowchart LR
    A[Authentication action] --> T[Database transaction]
    T --> S[(Account/session state)]
    T --> O[(Audit outbox row)]
    O --> P[Outbox publisher]
    P --> Q[Durable broker]
    Q --> C[Validated consumer]
    C --> L[(Audit store)]
    C --> D[Detection engine]
~~~

Outbox không tự bảo đảm mọi hệ thống exactly-once. Mô hình thường là at-least-once; consumer phải idempotent. Định nghĩa retention cho outbox, xử lý poison message và cảnh báo khi publish backlog tăng.

### 8.3. Event producer authentication

Collector không nên tin event chỉ vì request tới từ mạng nội bộ. Dùng service identity/mTLS hoặc cơ chế workload identity phù hợp; giới hạn producer được phép phát event type nào; validate schema, size, timestamp range và source metadata. Không cho client browser tự gửi event login.success hoặc session.revoked để tạo audit evidence.

## 9. Pipeline ingest, normalize và store

Pipeline tham khảo:

~~~mermaid
flowchart TD
    P[Identity / MFA / Token / Session / Recovery producers] --> G[Authenticated ingestion gateway]
    G --> V[Schema validation + redaction]
    V --> Q[Durable queue]
    Q --> N[Normalize + deduplicate]
    N --> A[(Append-only audit store)]
    N --> S[SIEM / detection engine]
    S --> AL[Alert router]
    AL --> C[Case management / on-call]
    A --> I[Investigation and reporting]
~~~

### 9.1. Ingestion gateway

Gateway cần:
- Xác thực producer.
- Kiểm tra schema/version và event type allowlist.
- Giới hạn kích thước, tốc độ và field cardinality.
- Reject hoặc quarantine event không hợp lệ.
- Gắn observed_at và ingestion metadata.
- Redact/drop field không được phép.
- Trả status rõ cho producer và theo dõi rejection.

Không âm thầm bỏ event sai schema. Quarantine cần quyền truy cập hẹp và retention ngắn; payload quarantine cũng phải redacted.

### 9.2. Queue và consumer

- Dùng durable queue cho event cần audit.
- Có retry/backoff và dead-letter queue.
- Theo dõi queue depth, oldest message age và publish failure.
- Consumer dùng event_id để deduplicate.
- Xử lý event đến muộn và out-of-order theo occurred_at/correlation.
- Không giả định thứ tự arrival là thứ tự nghiệp vụ.
- Có replay procedure và kiểm tra duplicate sau replay.
- Giới hạn retry để poison event không chặn cả partition.

### 9.3. Audit store

Audit store cần:
- Encryption in transit và at rest.
- Append-only hoặc immutable retention khi phù hợp.
- Tách quyền ingest, query, export, retention admin và deletion.
- Audit mọi lần đọc/export và thay đổi policy.
- Index theo event type, subject reference, time, correlation và tenant.
- Backup độc lập và kiểm thử restore.
- Retention theo mục đích, rủi ro và yêu cầu pháp lý.
- Quy trình legal hold và xóa theo policy.

Không giữ mọi event vô thời hạn. Có thể tách security audit, operational telemetry và analytics để có retention/access policy khác nhau.

## 10. Tính toàn vẹn và khả năng truy vết

Audit chỉ có giá trị khi người điều tra có cơ sở tin rằng record không bị sửa hoặc xóa âm thầm.

Các kiểm soát:
- Append-only storage hoặc WORM/retention lock theo yêu cầu.
- Tách quyền producer, storage administrator và investigator.
- TLS cho truyền tải và encryption at rest.
- Audit truy cập, export, delete, retention change và permission change.
- Đồng bộ clock và theo dõi drift.
- Hash/checkpoint/signature nếu threat model yêu cầu tamper evidence.
- Backup ở failure domain độc lập và kiểm thử restore.

### 10.1. Hash chain minh họa

~~~text
record_hash[i] =
    H(canonical_event[i] || record_hash[i-1])
~~~

Hash chain có thể phát hiện sửa record trong chuỗi, nhưng nếu attacker kiểm soát toàn bộ store và có thể viết lại cả chuỗi thì hash chain đơn lẻ không đủ. Cần checkpoint độc lập, signing key được bảo vệ hoặc immutable storage. Không tự nhận log là tamper-proof; mô tả đúng guarantee thực tế.

### 10.2. Chain of custody

Khi mở incident:
- Ghi incident ID và người thu thập evidence.
- Giữ bản gốc read-only.
- Ghi thời gian export, query và phạm vi dữ liệu.
- Hash evidence package nếu cần.
- Ghi mọi bản sao, chuyển giao và truy cập.
- Không sửa event gốc để thêm nhận xét; tạo analyst note riêng.
- Tách fact, hypothesis và conclusion.

## 11. Xây detection rule

Detection rule biến chuỗi event thành tín hiệu cần xem xét. Mỗi rule phải xác định event đầu vào, window, grouping key, threshold/baseline, exclusions, severity, confidence, owner và runbook.

### 11.1. Login failure burst

Phát hiện nhiều failure cho một account trong thời gian ngắn.

| Thuộc tính | Thiết kế minh họa |
| --- | --- |
| Input | authentication.login.failure |
| Window | 5 phút |
| Grouping | subject_ref + client_id |
| Threshold | Ví dụ 10 failure trong window |
| Severity | Medium, tăng theo context |
| Follow-up | Kiểm tra source diversity, sau đó có success hay không |

Không coi 10 là threshold production chung. Hiệu chỉnh theo baseline, tenant, client, traffic và rate limit hiện tại.

### 11.2. Password spraying/credential stuffing

Phát hiện một nguồn hoặc nhóm nguồn thử nhiều account trong thời gian ngắn.

- Group theo source reference, client và time window.
- Đếm distinct subject thay vì chỉ tổng request.
- Kết hợp failure rate và success sau chuỗi failure.
- So sánh theo ASN/network reputation nếu policy cho phép.
- Giảm false positive từ NAT, corporate proxy, test traffic và shared devices.
- Không chỉ dựa trên IP vì botnet có thể phân tán nguồn.

### 11.3. MFA fatigue

Phát hiện challenge liên tiếp bị deny/timeout rồi một challenge được approve.

- Input: mfa.challenge.issued, denied, expired, approved.
- Group: subject_ref, factor_ref và login correlation.
- Window: một khoảng ngắn theo policy.
- Signal: số challenge, số deny/timeout, approve sau chuỗi bất thường.
- Response: cooldown, step-up khác hoặc alert; không mặc định khóa account.
- Context: app/client, challenge age, device reference và risk decision.

### 11.4. Security change sau login rủi ro

Correlation các event:
- Login success từ context mới hoặc risk score cao.
- Recovery contact changed.
- Identity linked.
- Passkey/MFA factor enrolled.
- Session/token created.
- Sensitive API access ngay sau đó.

Một thay đổi đơn lẻ có thể hợp lệ. Tổ hợp nhiều thay đổi trong cùng flow/time window có thể tăng severity và yêu cầu review.

### 11.5. Refresh token reuse

Khi refresh token đã rotate bị dùng lại:
- Phát refresh_token.reuse_detected.
- Group theo token_family_ref, client_id và subject_ref.
- Revoke family/grant theo token policy.
- Alert owner của authorization server.
- Kiểm tra session/API activity liên quan.
- Không đưa token value vào alert.

### 11.6. Privileged action bất thường

Theo dõi:
- Admin reset MFA hoặc recovery factor.
- Authentication policy thay đổi.
- Tạo/revoke API key hoặc grant.
- Identity link thay đổi.
- Bulk account unlock.
- Export audit data hoặc thay retention/permission.

Alert cần actor, subject, target reference, reason/approval reference và policy version. Severity cao hơn nếu action ngoài change window, thiếu approval hoặc ảnh hưởng nhiều account.

### 11.7. Audit pipeline health

Thiếu event cũng là một tín hiệu bảo mật. Theo dõi:
- Producer im lặng bất thường.
- Outbox backlog.
- Queue lag và dead-letter count.
- Schema rejection tăng.
- Collector auth failure.
- Event drop hoặc duplicate bất thường.
- Detection engine không xử lý kịp.
- Alert router delivery failure.

Không thể tin rằng “không có login failure” nếu producer đã ngừng phát event. Pipeline health phải được giám sát độc lập.

## 12. Ví dụ detection query

Các query dưới đây là pseudocode SQL để diễn đạt logic; cú pháp và window function cần điều chỉnh theo SIEM hoặc database thật.

### 12.1. Login failure theo account

~~~sql
SELECT
    subject_ref,
    client_id,
    COUNT(*) AS failures,
    MIN(occurred_at) AS first_seen,
    MAX(occurred_at) AS last_seen
FROM authentication_events
WHERE event_type = 'authentication.login.failure'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '5 minutes'
GROUP BY subject_ref, client_id
HAVING COUNT(*) >= 10;
~~~

### 12.2. Password spraying theo nguồn

~~~sql
SELECT
    source_ref,
    client_id,
    COUNT(*) AS attempts,
    COUNT(DISTINCT subject_ref) AS distinct_accounts
FROM authentication_events
WHERE event_type = 'authentication.login.failure'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
GROUP BY source_ref, client_id
HAVING COUNT(DISTINCT subject_ref) >= 20;
~~~

### 12.3. MFA fatigue signal

~~~sql
SELECT
    subject_ref,
    correlation_id,
    SUM(CASE WHEN event_type IN
        ('mfa.challenge.denied', 'mfa.challenge.expired')
        THEN 1 ELSE 0 END) AS rejected_challenges,
    SUM(CASE WHEN event_type = 'mfa.challenge.approved'
        THEN 1 ELSE 0 END) AS approvals
FROM authentication_events
WHERE occurred_at >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
GROUP BY subject_ref, correlation_id
HAVING SUM(CASE WHEN event_type IN
    ('mfa.challenge.denied', 'mfa.challenge.expired')
    THEN 1 ELSE 0 END) >= 5
   AND SUM(CASE WHEN event_type = 'mfa.challenge.approved'
    THEN 1 ELSE 0 END) >= 1;
~~~

### 12.4. Credential change sau login

~~~sql
SELECT
    l.subject_ref,
    l.correlation_id,
    l.occurred_at AS login_time,
    c.event_type AS security_change,
    c.occurred_at AS change_time
FROM authentication_events l
JOIN authentication_events c
  ON c.subject_ref = l.subject_ref
 AND c.occurred_at BETWEEN l.occurred_at
                       AND l.occurred_at + INTERVAL '15 minutes'
WHERE l.event_type = 'authentication.login.success'
  AND l.risk_level IN ('high', 'critical')
  AND c.event_type IN (
      'recovery_contact.changed',
      'identity.linked',
      'credential.passkey.enrolled',
      'mfa.factor.enrolled'
  );
~~~

Query chỉ minh họa correlation; cần xử lý event duplicate, nhiều login flow song song, tenant boundary và event đến muộn. Nếu correlation_id không được giữ xuyên service, phải dùng transaction reference phù hợp, không ghép chỉ theo account và thời gian một cách mù quáng.

### 12.5. Refresh token reuse

~~~sql
SELECT
    subject_ref,
    token_family_ref,
    client_id,
    occurred_at
FROM authentication_events
WHERE event_type = 'token.refresh_token.reuse_detected'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour';
~~~

Event reuse nên được phát bởi authorization server tại nơi kiểm tra token lineage. Detection engine không tự suy ra reuse bằng cách lưu hoặc so sánh raw token.

## 13. Alert design và routing

Alert là lời yêu cầu hành động. Một alert tốt cần nói rõ điều gì xảy ra, tại sao đáng quan tâm, evidence nào hỗ trợ, ai chịu trách nhiệm và bước tiếp theo là gì.

### 13.1. Alert payload

| Field | Nội dung |
| --- | --- |
| alert_id | ID duy nhất để deduplicate. |
| rule_id/rule_version | Rule tạo alert. |
| created_at | Thời điểm alert được tạo. |
| severity | Informational/Low/Medium/High/Critical theo taxonomy nội bộ. |
| confidence | Độ tin cậy của detection. |
| subject_ref | Account/tenant bị ảnh hưởng. |
| actor_ref | Actor nếu xác định được. |
| event_refs | Các event hỗ trợ kết luận. |
| time_window | Khoảng thời gian được phân tích. |
| summary | Mô tả ngắn, không chứa secret. |
| reason | Vì sao rule match. |
| recommended_action | Bước triage/runbook. |
| owner/team | Nhóm chịu trách nhiệm. |
| case_ref | Incident/case nếu đã mở. |

Không đưa raw token, cookie, OTP, email đầy đủ hoặc payload nhạy cảm vào notification channel. Alert có thể chứa link tới evidence query được bảo vệ bằng access control.

### 13.2. Severity và confidence

Severity phản ánh tác động tiềm tàng; confidence phản ánh độ mạnh của bằng chứng. Hai giá trị không giống nhau.

| Severity | Ví dụ | Hành động |
| --- | --- | --- |
| Critical | Refresh token reuse cùng dấu hiệu account takeover; privileged change không được phê duyệt | On-call security ngay, containment theo runbook. |
| High | MFA fatigue rồi security factor change từ context rủi ro | Triage khẩn, xem xét step-up/revoke có kiểm soát. |
| Medium | Login failure burst hoặc nhiều account bị thử | Theo dõi, rate limit/risk review. |
| Low/Info | Browser/device mới hoặc một tín hiệu bất thường đơn lẻ | Ghi nhận và correlation thêm. |

Một signal severity cao nhưng confidence thấp có thể cần triage nhanh để xác minh, không tự động thực hiện hành động phá hủy. Một sự kiện có confidence cao nhưng tác động thấp có thể được xử lý theo queue thông thường.

### 13.3. Deduplication và suppression

- Gom alert cùng subject/rule/time window vào một case.
- Giữ số lượng event và thời gian đầu/cuối để analyst không mất context.
- Suppress có thời hạn, có owner và lý do.
- Không suppress alert Critical chỉ vì đã có alert tương tự nếu event mới làm thay đổi phạm vi.
- Có cơ chế mở lại case khi xuất hiện evidence mới.
- Không để suppression che giấu pipeline outage hoặc producer silence.

### 13.4. Routing

| Alert type | Owner chính | Escalation |
| --- | --- | --- |
| Login abuse | Identity Security Operations | Identity on-call nếu vượt threshold. |
| MFA fatigue | Authentication team | Security incident commander nếu có approve bất thường. |
| Token reuse | Authorization Server team | Security on-call và API owner. |
| Recovery/identity link change | Account Security team | Support lead và incident commander khi có ATO. |
| Admin policy change | IAM/platform security | Security lead và approver. |
| Audit pipeline health | Observability/platform team | Security on-call nếu có coverage gap. |

Không gửi mọi alert tới mọi người. Routing theo owner giảm nhiễu và giúp xử lý nhanh hơn.

## 14. Runbook triage cho alert account takeover

Khi nhận alert có khả năng ATO:

1. Xác nhận alert không phải test, deployment hoặc duplicate.
2. Kiểm tra rule version, severity, confidence và time window.
3. Dựng timeline login, MFA, session, token, recovery, identity link và credential events.
4. Tách facts đã xác nhận khỏi hypotheses.
5. Xác định actor, subject, tenant, client, session reference và credential reference.
6. Kiểm tra security changes sau login rủi ro.
7. Xem API/resource activity sau thời điểm nghi ngờ.
8. Đánh giá token/session còn hoạt động và revocation propagation.
9. Xác minh người dùng qua kênh độc lập đã biết trước đó.
10. Chọn containment theo phạm vi evidence; bảo toàn audit evidence.
11. Ghi action, approver, timestamp và kết quả.
12. Theo dõi recovery, thông báo và kiểm thử sau containment.

Không yêu cầu người dùng gửi password, OTP, recovery code, private key hoặc session cookie. Không dùng recovery email vừa thay làm kênh xác minh duy nhất.

## 15. Alert pipeline và độ tin cậy vận hành

Alert có thể bị mất sau khi detection match nếu router, email, paging hoặc case service lỗi. Theo dõi cả đường đi của alert:

- Detection rule execution lag.
- Match count và suppressed count.
- Alert creation failure.
- Notification delivery failure.
- On-call acknowledgement latency.
- Escalation timeout.
- Case creation/closure status.
- Dead-letter queue và retry count.
- Alert deduplication ratio.
- Rule error/compile failure.
- Event-to-alert latency.

Với alert Critical, nên có delivery acknowledgement hoặc kênh dự phòng theo policy. Không coi việc gọi API notification thành công là người trực đã nhận alert. Alert cần trạng thái created, delivered, acknowledged, escalated và resolved.

### 15.1. Giám sát chính hệ thống audit

| Chỉ số | Ý nghĩa | Khi cần cảnh báo |
| --- | --- | --- |
| Event production rate | Producer còn phát event không | Giảm bất thường so với baseline. |
| Outbox backlog | Event chờ publish | Tăng liên tục hoặc vượt SLA. |
| Queue lag | Consumer xử lý chậm | Event quá cũ trước khi searchable. |
| Schema rejection | Event không hợp lệ | Tăng đột biến hoặc producer mới bị reject. |
| Event drop | Bằng chứng bị mất | Bất kỳ event critical nào bị drop. |
| Duplicate rate | Retry hoặc producer behavior | Tăng bất thường, ảnh hưởng counting. |
| Clock drift | Timestamp có tin cậy không | Producer vượt tolerance. |
| Redaction violation | Secret/PII lọt qua policy | Alert Critical và xử lý incident. |
| Detection lag | Rule chưa xử lý event kịp | Vượt detection SLO. |
| Alert delivery lag | Người xử lý nhận chậm | Vượt acknowledgement/escalation SLO. |

Không dùng một dashboard tổng hợp để che việc một producer critical ngừng phát. Theo dõi từng service và event family quan trọng.

## 16. Quyền truy cập, retention và privacy

Audit data thường tập trung nhiều thông tin về tài khoản và hành vi. Phải thiết kế quyền truy cập theo least privilege.

- Producer chỉ được ghi event type được cấp phép.
- Analyst chỉ đọc dữ liệu phục vụ case/role.
- Export cần phê duyệt hoặc audit theo policy.
- Storage administrator không mặc nhiên được sửa event.
- Retention administrator và investigator nên là vai trò tách biệt khi phù hợp.
- Mọi query, export, delete và policy change đều có audit.
- Mã hóa storage, transport và backup.
- Pseudonymize subject/network references khi không cần định danh trực tiếp.
- Đặt retention theo loại event, mục đích và nghĩa vụ pháp lý.
- Xóa đúng hạn khỏi primary store, index, replica, export và bản sao phân tích.
- Legal hold cần owner, lý do và thời điểm kết thúc.

Không giữ event vô thời hạn chỉ để “phòng khi cần”. Privacy review cần tham gia khi thêm field network, device, location hoặc user behavior.

## 17. Kế hoạch triển khai theo giai đoạn

Một triển khai tốt nên bắt đầu từ các luồng có giá trị bảo mật cao và mở rộng sau khi schema/pipeline ổn định.

### Giai đoạn 1 — Inventory và contract

1. Liệt kê authentication flow và owner service.
2. Chọn event taxonomy và semantics.
3. Chốt schema version, enum, reference và privacy classification.
4. Xác định event nào bắt buộc durable trước commit.
5. Định nghĩa producer authentication và consumer contract.
6. Review threat model và data retention.

**Deliverable:** event catalog, schema contract, data classification và ownership map.

### Giai đoạn 2 — Instrument producer

1. Thêm event tại login, MFA, passkey, token, session, recovery và admin decision point.
2. Ghi event vào transactional outbox cho state change quan trọng.
3. Tạo stable event_id và correlation_id.
4. Redact secret ở nguồn.
5. Viết contract test và schema validation.
6. Kiểm tra actor/subject/target semantics.

**Deliverable:** producer event coverage và test chứng minh không log secret.

### Giai đoạn 3 — Ingest và store

1. Xác thực producer.
2. Validate schema/version và giới hạn payload.
3. Gắn observed_at.
4. Đẩy vào durable queue.
5. Normalize và deduplicate.
6. Lưu audit store với encryption, access control và integrity.
7. Cấu hình backup, restore, retention và audit truy cập.

**Deliverable:** pipeline có thể replay, đo lag và phát hiện event loss.

### Giai đoạn 4 — Detection và alert

1. Chọn rule ưu tiên theo threat model.
2. Xây query/rule và test dữ liệu.
3. Đặt threshold/baseline, grouping, suppression và severity.
4. Tạo alert payload có evidence references.
5. Route tới owner/on-call và case service.
6. Viết runbook, escalation và acknowledgement.
7. Đo false positive/negative và tuning có review.

**Deliverable:** rule catalog, alert route, runbook và dashboard.

### Giai đoạn 5 — Tabletop và production readiness

1. Chạy kịch bản credential stuffing, MFA fatigue và token reuse.
2. Giả lập queue outage, collector outage và notification outage.
3. Kiểm thử redaction, duplicate, out-of-order và tamper evidence.
4. Đo event-to-alert latency và response time.
5. Kiểm thử restore/replay.
6. Review privacy, access và retention.
7. Chốt owner, SLO và release gate.

**Deliverable:** test evidence, incident exercise report và go-live checklist.

## 18. Bài thực hành chi tiết: triển khai cho StudyHub

### 18.1. Yêu cầu đầu vào

Team nhận các flow sau:
- Login password + optional MFA.
- Passkey assertion.
- TOTP enrollment/removal.
- Push challenge approve/deny.
- Refresh token rotation/reuse.
- Session create/revoke/logout.
- Recovery contact change/account recovery.
- Identity link/unlink.
- Admin reset MFA và authentication policy change.
- Course API access tới tài liệu nhạy cảm.

Hãy tạo event catalog cho từng flow. Với mỗi event, ghi producer, trigger, actor, subject, target, outcome, reason code, correlation strategy, required durability và privacy classification.

### 18.2. Thiết kế event catalog mẫu

| Event | Producer | Trigger | Durability | Alert candidate |
| --- | --- | --- | --- | --- |
| login.failure | Identity Service | Password/MFA flow kết thúc thất bại | Durable queue | Có, theo correlation/window. |
| login.success | Identity Service | Authentication policy hoàn tất | Durable audit | Không mặc định; dùng correlation. |
| mfa.challenge.issued | MFA Service | Challenge tạo/gửi | Durable event | Có khi burst. |
| mfa.challenge.denied | MFA Service | User deny | Durable event | Có khi fatigue pattern. |
| passkey.enrolled | Passkey Service | Credential được verify và persist | Audit before/with commit | Có khi login risk cao. |
| refresh_token.reuse_detected | Authorization Server | Token lineage phát hiện reuse | Critical durable | Có, High/Critical. |
| session.revoked | Session Service | Session bị revoke | Critical durable | Có khi propagation breach. |
| recovery_contact.changed | Recovery Service | Contact change commit | Critical durable | Có khi context rủi ro. |
| identity.linked | Identity Link Service | Link commit | Critical durable | Có khi actor/session mới. |
| admin.authentication_policy.changed | Admin Service | Policy change commit | Critical durable | Có, High/Critical. |

### 18.3. Định nghĩa rule và test

Với mỗi rule, tạo một record gồm:
- Rule ID và version.
- Mục tiêu phát hiện.
- Event type và schema version.
- Window, grouping key và threshold.
- Exclusion/suppression.
- Severity và confidence.
- Hành động tự động nếu có, kèm điều kiện an toàn.
- Owner, runbook và escalation.
- Positive test, negative test và expected alert.

Ví dụ rule MFA fatigue:
- Positive: cùng subject có nhiều challenge deny/expired rồi một approve trong window.
- Negative: user có hai lần retry do mạng nhưng không có approve bất thường.
- Expected: một alert gộp, có event references và không chứa OTP.
- Response: analyst xác minh user và transaction; policy có thể cooldown hoặc yêu cầu factor chống phishing.

### 18.4. Bảng kết quả triển khai

| Hạng mục | Trạng thái mẫu | Bằng chứng cần đính kèm |
| --- | --- | --- |
| Event catalog | Chưa chạy | Catalog đã review và owner rõ. |
| Schema contract | Chưa chạy | Schema version và contract test. |
| Producer coverage | Chưa chạy | Event sample từ từng service. |
| Secret redaction | Chưa chạy | Marker test không xuất hiện ở pipeline. |
| Durable outbox | Chưa chạy | Crash/retry test và backlog metric. |
| Audit store integrity | Chưa chạy | Access control, integrity check và restore test. |
| Detection rules | Chưa chạy | Positive/negative test cho mỗi rule. |
| Alert routing | Chưa chạy | Delivery/acknowledgement test. |
| Runbooks | Chưa chạy | Owner, triage, containment và escalation. |
| Privacy/retention | Chưa chạy | Field review, retention và deletion evidence. |
| Tabletop | Chưa chạy | Timeline, decisions và action items. |

Đây là bảng mẫu cho người học điền sau khi thực hiện. Không đánh dấu PASS nếu chưa có bằng chứng.

## 19. Bộ ca kiểm thử chấp nhận end-to-end

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| AUD-01 | Password login success | Event factor success và login success đúng semantics. |
| AUD-02 | Password sai | Failure event có reason code; không có password. |
| AUD-03 | MFA pending | Không phát login success trước khi policy hoàn tất. |
| AUD-04 | MFA deny/expire | Event riêng cho denied/expired. |
| AUD-05 | Passkey enroll | Actor/subject/credential reference và outcome đúng; không có private key. |
| AUD-06 | TOTP enrollment | Seed/QR/OTP không xuất hiện trong log hoặc queue. |
| AUD-07 | Refresh rotation | Token family reference được ghi; raw token không được ghi. |
| AUD-08 | Refresh token reuse | Critical event durable và alert được tạo. |
| AUD-09 | Session revoke | Revoke event được ghi; replay session bị từ chối. |
| AUD-10 | Recovery contact change | Actor/subject và old/new contact handling tuân privacy policy. |
| AUD-11 | Identity link | Issuer/subject reference được ghi; không có ID token raw. |
| AUD-12 | Admin reset MFA | Actor admin, subject user và approval reference đầy đủ. |
| AUD-13 | Producer crash sau DB commit | Outbox phát event sau restart, không mất event. |
| AUD-14 | Publisher retry | Event ID ổn định; consumer deduplicate. |
| AUD-15 | Duplicate message | Không tạo hai audit record logic hoặc alert trùng. |
| AUD-16 | Out-of-order event | Timeline dùng occurred_at/correlation, không dựa arrival order. |
| AUD-17 | Unknown schema version | Reject/quarantine có audit; không silent drop. |
| AUD-18 | Raw secret marker | Marker không xuất hiện ở storage, SIEM, alert hoặc artifact. |
| AUD-19 | Collector authentication fail | Producer không được giả mạo; rejection được ghi nhận. |
| AUD-20 | Queue outage | Outbox backlog được đo; event critical không bị mất âm thầm. |
| AUD-21 | Audit store tamper attempt | Integrity/immutable control phát hiện hoặc ngăn theo guarantee. |
| AUD-22 | Analyst không có quyền | Query/export bị từ chối và audit access event được tạo. |
| AUD-23 | Retention expiry | Event bị xóa theo policy khỏi store/index/replica. |
| AUD-24 | Login failure burst | Rule match và alert được deduplicate. |
| AUD-25 | Password spraying | Rule đếm distinct accounts và không chỉ dựa IP. |
| AUD-26 | MFA fatigue | Alert có challenge references và không có OTP. |
| AUD-27 | Security change sau risky login | Correlation alert có event timeline. |
| AUD-28 | Token reuse | Alert route tới authorization owner và runbook. |
| AUD-29 | Privileged policy change | Alert high/critical theo policy, có actor và approval. |
| AUD-30 | Producer im lặng | Pipeline health alert phát hiện coverage gap. |
| AUD-31 | Detection engine lag | Detection SLO breach được cảnh báo. |
| AUD-32 | Notification delivery fail | Alert được retry/escalate theo delivery policy. |
| AUD-33 | Alert duplicate | Suppression/dedup giữ evidence và không mất severity escalation. |
| AUD-34 | Alert acknowledge | Case chuyển trạng thái và lưu actor/time. |
| AUD-35 | Tabletop ATO | Analyst dựng timeline, containment và recovery đúng runbook. |
| AUD-36 | Backup restore | Integrity được xác minh; revoke state không bị hồi sinh. |

### 19.1. Tiêu chí PASS end-to-end

Một test không chỉ kiểm tra event xuất hiện ở producer. Cần chứng minh:
1. Event được phát đúng semantics.
2. Event không chứa secret/PII ngoài policy.
3. Event tới durable store trong SLO.
4. Duplicate/retry không làm sai kết quả.
5. Detection rule match đúng dữ liệu.
6. Alert được route và acknowledgement.
7. Analyst có đủ evidence để triage.
8. Runbook tạo ra hành động đúng và có audit.
9. Revoke/containment có hiệu lực ở các service/region liên quan.
10. Recovery không mở lại đường truy cập cũ.

## 20. Đo lường hiệu quả

Theo dõi chất lượng audit và alert qua các chỉ số:

| Metric | Cách hiểu | Mục tiêu |
| --- | --- | --- |
| Event coverage | Tỷ lệ event dự kiến thực sự được nhận | Không có khoảng trống ở event critical. |
| Event durability | Tỷ lệ event critical được ghi bền vững | Đạt SLO đã định. |
| Event-to-search latency | Thời gian từ occurred_at tới khi searchable | Đủ nhanh cho threat window. |
| Detection latency | Thời gian từ event đầu tiên tới rule match | Nằm trong detection SLO. |
| Alert delivery latency | Từ alert creation tới delivery/ack | Đáp ứng on-call policy. |
| False positive rate | Alert không cần hành động sau triage | Giảm mà không bỏ lọt threat. |
| False negative rate | Threat scenario không tạo alert | Đo qua simulation/tabletop và incident review. |
| Duplicate alert rate | Alert trùng cùng một pattern | Giảm nhiễu, giữ escalation mới. |
| Mean time to acknowledge | Thời gian nhận alert | Theo severity/on-call target. |
| Mean time to contain | Thời gian giới hạn tác động | Theo incident class. |
| Redaction violation | Secret/PII bị ghi sai policy | Mục tiêu bằng 0. |
| Audit query auditability | Query/export có record truy vết | 100% theo policy. |

Không tối ưu bằng cách giảm số alert một cách máy móc. Alert ít hơn có thể là detection tốt hơn hoặc do producer bị mất event. Luôn xem cùng event coverage, simulation result và pipeline health.

## 21. Lỗi triển khai thường gặp

- **Chỉ ghi login success/failure:** bỏ sót factor change, recovery, token, session và admin action.
- **Ghi event từ frontend:** client có thể giả mạo outcome.
- **Gộp password success với login success:** sai semantics khi MFA pending.
- **Không có actor/subject:** không biết ai thực hiện thay mặt ai.
- **Thiếu event_id:** không deduplicate được retry.
- **Chỉ có một timestamp:** khó phân biệt event delay và clock skew.
- **Ghi raw token/OTP/cookie:** biến audit store thành kho credential.
- **Redaction chỉ ở dashboard:** secret đã vào storage.
- **Không có outbox:** event mất khi process crash giữa state commit và publish.
- **Giả định exactly-once:** duplicate gây sai số và alert trùng.
- **Không xử lý event out-of-order:** timeline sai.
- **Không giám sát producer silence:** tưởng không có tấn công trong khi log bị mất.
- **Threshold cố định:** tạo false positive hoặc bỏ lọt hành vi chậm.
- **Chỉ group theo IP:** NAT/VPN/botnet làm detection kém chính xác.
- **Alert không có owner/runbook:** không ai chịu trách nhiệm.
- **Alert chứa PII/secret:** notification channel trở thành nơi rò dữ liệu.
- **Suppression vô thời hạn:** che mất tín hiệu mới.
- **Không audit analyst access:** evidence có thể bị lạm dụng.
- **Retention vô hạn:** tăng privacy risk và chi phí.
- **Không kiểm thử restore:** revocation state hoặc evidence có thể bị mất.
- **Không đo alert acknowledgement:** alert được tạo nhưng không được xử lý.

## 22. Tài liệu tham khảo và hướng đọc tiếp

- **OWASP Logging Cheat Sheet:** dữ liệu nên/không nên ghi, bảo vệ log và event design.
- **OWASP Authentication Cheat Sheet:** password, MFA, re-authentication và account controls.
- **OWASP Multifactor Authentication Cheat Sheet:** enrollment, recovery và factor management.
- **OWASP Session Management Cheat Sheet:** session lifecycle, rotation và invalidation.
- **OWASP OAuth 2.0 Cheat Sheet:** token, redirect và refresh-token protection.
- **NIST SP 800-92 — Guide to Computer Security Log Management:** thu thập, phân tích, bảo vệ và vận hành log.
- **NIST SP 800-53 — Security and Privacy Controls:** audit generation, review, protection và accountability.
- **NIST SP 800-61 — Incident Response:** chuẩn bị, phát hiện, containment, recovery và lessons learned.
- **OpenTelemetry Logs Data Model:** timestamp, resource, trace correlation và structured logs.
- **RFC 6749, RFC 7009 và RFC 7662:** OAuth token issuance, revocation và introspection.
- **OpenID Connect Core:** issuer, subject, nonce và identity validation.
- **WebAuthn specification:** passkey registration và assertion verification.
- **SIEM/detection engineering documentation:** correlation, rule testing, alert lifecycle và case management.

Khi triển khai thật, cần kiểm tra phiên bản chuẩn và tài liệu của nền tảng đang dùng. Event schema, retention, threshold, alert route và runbook phải được review theo threat model, dữ liệu thực tế và chính sách privacy của tổ chức. Các threshold trong bài chỉ là ví dụ học tập, không phải cấu hình production mặc định.

**Kết luận:** Thiết lập audit và alert là một chuỗi liên tục từ event producer tới hành động phản ứng. Event phải được phát đúng điểm quyết định, có schema và correlation ổn định, không chứa secret, được vận chuyển/lưu trữ bền vững và có thể truy vết. Detection rule cần kết hợp nhiều tín hiệu, có threshold được hiệu chỉnh, owner và runbook rõ. Chỉ khi kiểm thử được event coverage, redaction, integrity, detection, alert delivery và containment thì hệ thống mới chứng minh được khả năng phát hiện và xử lý lạm dụng xác thực.
