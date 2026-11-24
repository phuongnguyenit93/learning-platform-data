# Logging review (Rà soát logging cho hệ thống xác thực)

> **Chương:** Security review  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Đánh giá thiết kế và vận hành logging trong hệ thống xác thực; xác minh nguồn log, độ bao phủ, ngữ nghĩa, context identity, correlation, bảo vệ secret/PII, tính toàn vẹn, pipeline, quyền truy cập và retention; bảo đảm log hỗ trợ detection, điều tra và audit mà không trở thành nơi rò rỉ credential.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mục tiêu của logging review và phân biệt application log, security event, audit record, metric và trace.
2. Lập inventory nguồn log trong password, MFA, passkey, federation, token, session, recovery và workload authentication.
3. Đánh giá độ bao phủ và chất lượng ngữ nghĩa của log theo từng authentication flow.
4. Kiểm tra actor, subject, tenant, client, source, outcome và reason code có đáng tin hay không.
5. Phát hiện password, OTP, token, cookie, private key và PII bị ghi vào log.
6. Đánh giá log injection, redaction, structured logging, timestamp và correlation.
7. Rà soát pipeline thu thập, vận chuyển, lưu trữ, integrity, access control và retention.
8. Xác định log có đủ context để phát hiện credential stuffing, MFA fatigue, session abuse và account takeover.
9. Kiểm tra khả năng truy vết sự cố qua IdP, RP, gateway, session service và downstream API.
10. Xây dựng review finding có evidence, risk, owner và remediation; thiết kế test xác minh sau sửa.

## 1. Logging review là gì?

**Logging review (rà soát logging)** là hoạt động đánh giá có hệ thống cách ứng dụng và nền tảng tạo, truyền, xử lý, lưu trữ, bảo vệ và sử dụng log.

Trong hệ thống authentication, logging review trả lời các câu hỏi:

- Hành động xác thực quan trọng có được ghi nhận không?
- Log có nói rõ actor, subject, method, outcome và lý do không?
- Nguồn log có phải thành phần có thẩm quyền không?
- Có credential hoặc dữ liệu cá nhân bị ghi quá mức không?
- Có thể nối một login flow qua nhiều service không?
- Log có thể bị sửa, xóa hoặc truy cập trái phép không?
- Pipeline có mất event khi broker hoặc storage lỗi không?
- SOC có đủ context để điều tra và phản ứng không?
- Log có được giữ đúng thời hạn và xóa theo policy không?

Logging review không chỉ kiểm tra một vài dòng log trong source code. Nó đánh giá toàn bộ lifecycle từ điểm phát sinh tới consumer và cách tổ chức dựa vào dữ liệu đó để vận hành bảo mật.

### Vì sao logging quan trọng với authentication?

Một hệ thống có thể từ chối password sai nhưng nếu không ghi reason code, rate-limit decision hoặc source context thì khó phân biệt lỗi người dùng với brute force. Một session có thể bị revoke nhưng nếu không log kết quả và propagation tới API thì không thể chứng minh backend đã từ chối session cũ.

Log tốt giúp:

- Phát hiện credential attack và hành vi bất thường.
- Điều tra account takeover, session theft và recovery abuse.
- Xác minh policy được thực thi.
- Đo sức khỏe IdP, token service và session store.
- Tìm cấu hình sai và lỗi vận hành.
- Xác định phạm vi ảnh hưởng khi credential bị lộ.
- Hỗ trợ audit và post-incident review.

Log kém có thể gây hai hậu quả trái ngược: thiếu dữ liệu khiến không phát hiện được sự cố, hoặc ghi quá nhiều khiến credential/PII bị lộ.

## 2. Phân biệt application log, security event, audit record, metric và trace

Các loại telemetry có thể cùng đi qua một nền tảng nhưng mục đích và yêu cầu khác nhau.

| Loại | Mục đích | Ví dụ | Điểm review |
| --- | --- | --- | --- |
| **Application log** | Debug và vận hành ứng dụng. | Database timeout, invalid configuration. | Log level, context, secret leakage. |
| **Security event** | Mô tả hành động/kết quả liên quan bảo mật. | Login failed, MFA denied. | Schema, source, outcome, correlation. |
| **Audit record** | Bằng chứng về hành động/quyết định cần truy cứu. | Admin gỡ MFA cho account. | Provenance, integrity, retention, access. |
| **Metric** | Đo số lượng/tỷ lệ/xu hướng. | Login failure rate. | Cardinality, aggregation, privacy. |
| **Trace/span** | Theo dõi request qua nhiều service. | Login flow qua gateway và IdP. | Trace propagation, sampling, sensitive attributes. |

Một security event có thể được ghi vào log backend; audit record có thể được xuất thành event; metric có thể được tính từ log. Tuy nhiên, không nên mặc định debug log đáp ứng yêu cầu audit hoặc trace sampling không làm mất bằng chứng cần thiết.

### Ví dụ

Khi người dùng đăng nhập thất bại:

- Application log có thể ghi authentication dependency timeout.
- Security event ghi login failure với reason code.
- Audit record ghi quyết định deny nếu policy yêu cầu.
- Metric tăng counter login_failure.
- Trace nối Gateway, Authentication API và Credential Store.

Mỗi dữ liệu trả lời một câu hỏi khác nhau. Review cần xác định nguồn nào là nguồn có thẩm quyền cho từng thông tin.

## 3. Phạm vi và mục tiêu review

Trước khi xem log, xác định rõ hệ thống, luồng và rủi ro cần đánh giá.

### Scope

- Environment: local, test, staging, production.
- Identity provider và relying party.
- Web, mobile, API và service-to-service authentication.
- Password, MFA, passkey, certificate, API key và token.
- Session creation, refresh, logout và revoke.
- Account linking, recovery và lifecycle.
- Gateway, service mesh, message broker và downstream API.
- SIEM, log platform, archive và alerting.

### Review objectives

- **Coverage:** các hành động quan trọng có được ghi nhận?
- **Accuracy:** log có phản ánh đúng điều đã xảy ra?
- **Context:** có đủ actor, subject, tenant, method và outcome?
- **Confidentiality:** secret và PII có được bảo vệ?
- **Integrity:** log có thể bị sửa/xóa không?
- **Availability:** log có truy cập được khi cần?
- **Correlation:** có nối được các hop?
- **Actionability:** SOC có dùng log để phát hiện và xử lý?
- **Governance:** access, retention và ownership có rõ?

### Tiêu chí ưu tiên

Ưu tiên luồng có impact cao: admin authentication, recovery, MFA removal, token issuance, federation trust change, session revocation và workload credential. Không cần review mọi debug statement với cùng mức độ.

## 4. Inventory nguồn log và data flow

Bước đầu tiên là lập danh sách nơi log được tạo và nơi log đi qua.

~~~mermaid
flowchart LR
    B["Browser / mobile"] --> G["Gateway / edge"]
    G --> RP["Web RP / API"]
    RP --> IDP["IdP / Authentication service"]
    IDP --> C["Credential / MFA provider"]
    RP --> S["Session / token service"]
    S --> API["Downstream API"]
    G --> P["Log pipeline"]
    RP --> P
    IDP --> P
    C --> P
    S --> P
    API --> P
    P --> SIEM["SIEM / log platform"]
    SIEM --> SOC["SOC / investigation"]
~~~

### Inventory nên ghi

| Thành phần | Log cần xem | Owner |
| --- | --- | --- |
| Browser/mobile | Client error và flow telemetry đã giảm nhạy cảm. | Client team. |
| Gateway | Request ID, route, auth result, upstream status. | Platform/edge. |
| IdP | Authentication, MFA, federation, policy decision. | Identity team. |
| Credential store | Verify result, lock/rate-limit decision; không ghi secret. | Identity/data team. |
| Passkey/WebAuthn RP | Registration/authentication result và validation reason. | Application/identity team. |
| Token service | Issue, refresh, revoke, introspection outcome. | Authorization team. |
| Session service | Create, rotate, expire, revoke và propagation. | Session/platform team. |
| API/resource server | Token validation và authorization outcome. | Service owner. |
| Secret manager/CA | Secret access, certificate issue/renew/revoke. | Platform/security. |
| SIEM/log store | Ingestion, normalization, query, export và retention. | Security operations. |

### Data flow

Với mỗi nguồn, xác định log được gửi trực tiếp hay qua agent/collector, có queue hay không, nơi redact, nơi enrich, nơi lưu và ai được query. Đánh dấu trust boundary, credential được dùng giữa các hop và điểm có thể drop hoặc duplicate event.

Không đọc các file cấu hình hoặc repository ngoài phạm vi được phê duyệt khi thực hiện review; inventory có thể được lập từ kiến trúc và artefact do owner cung cấp.

## 5. Coverage theo authentication lifecycle

Review cần đối chiếu các bước nghiệp vụ với event/log tương ứng.

| Flow | Những hành động cần có log |
| --- | --- |
| Account lifecycle | Create, activate, suspend, restore, deprovision. |
| Password | Login attempt, verify result, change/reset, blocklist deny, lock/throttle. |
| MFA | Enrollment, challenge create/deliver/approve/deny/expire, remove/recovery. |
| Passkey | Registration, assertion validation, credential add/remove/revoke. |
| Certificate | Issue, renew, validation failure, revoke, trust update. |
| Federation | Authorization request, callback result, issuer/audience/signature/state validation. |
| Token | Issue, refresh, introspection, grant change, revoke, reuse detection. |
| Session | Create, rotate, renew, timeout, logout, revoke và downstream deny. |
| Recovery | Request, verification, approval, completion, channel change. |
| Workload | Identity issuance, attestation, client authentication, rotation, deprovision. |
| Administration | Policy, role, issuer, key và trust configuration change. |

### Coverage không chỉ là có log

Một event có thể tồn tại nhưng không đủ thông tin để dùng. Ví dụ log “login failed” không có method, reason category hoặc tenant reference có thể không hỗ trợ phân biệt password attack với IdP outage.

Đánh giá coverage theo cả event presence và context completeness.

## 6. Chất lượng ngữ nghĩa và structured logging

Log nên có cấu trúc ổn định để máy có thể phân tích và con người có thể hiểu.

### Field gợi ý

- timestamp và timezone.
- severity/log level.
- service, environment và version.
- event_type hoặc action.
- actor_ref và subject_ref.
- tenant_ref.
- auth_method.
- outcome và reason_code.
- request_id/correlation_id/trace_id.
- source reference theo privacy policy.
- policy_version.
- duration và dependency status nếu liên quan.

### Structured logging

Ưu tiên JSON hoặc schema tương đương thay vì ghép chuỗi không có field boundary.

~~~json
{
  "timestamp": "2026-11-22T11:02:14.420Z",
  "level": "WARN",
  "service": "identity-api",
  "environment": "production",
  "event_type": "authentication.login.failed",
  "actor_ref": "subject-ref-42",
  "tenant_ref": "tenant-ref-8",
  "auth_method": "password",
  "outcome": "failure",
  "reason_code": "invalid_credential",
  "correlation_id": "corr-2a91",
  "policy_version": "login-policy-12"
}
~~~

Ví dụ không chứa password, token, cookie hoặc email thô. Field names và vocabulary cần được thống nhất giữa producer và consumer.

### Message không thay thế field

Một message như “Login failed for user” không đủ nếu subject, reason, source và outcome chỉ nằm trong free text. Giữ message ngắn để con người đọc; dùng field riêng cho truy vấn và detection.

## 7. Identity context: actor, subject, client và tenant

Một logging review cần kiểm tra hệ thống có phân biệt đúng các principal không.

- **Actor:** principal thực hiện hành động.
- **Subject:** account được xác thực hoặc bị tác động.
- **Client/workload:** ứng dụng/service gửi request.
- **Issuer:** bên phát hành identity assertion/token.
- **Tenant:** phạm vi tổ chức.
- **Producer:** service phát log.
- **Source:** browser, device hoặc network context.

### Ví dụ

Một helpdesk operator reset authenticator cho học viên:

- Actor là operator.
- Subject là học viên.
- Client là Staff Console.
- Producer là Identity Administration API.
- Tenant là trường sở hữu account.
- Target là authenticator reference.

Nếu log chỉ ghi user_id của học viên, người review không biết ai đã thực hiện thay đổi.

### Trust

Không lấy actor hoặc tenant từ request body/header do browser tự gửi. Identity context phải đến từ token/session/certificate đã xác minh hoặc từ gateway có trust relationship và integrity phù hợp.

## 8. Outcome, reason code và lỗi dependency

Log cần phân biệt thất bại xác thực với lỗi hạ tầng.

### Outcome gợi ý

- success
- failure
- denied
- challenged
- expired
- cancelled
- unavailable
- pending

### Reason code gợi ý

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
- dependency_timeout
- dependency_unavailable
- policy_denied
- internal_error

### Vì sao cần phân biệt?

Nếu database timeout được ghi thành invalid_credential, detection có thể tạo alert brute force sai và dashboard làm người vận hành hiểu nhầm chất lượng login. Nếu policy deny bị ghi thành internal error, team có thể bỏ sót việc policy đang chặn hợp lệ hoặc cấu hình sai.

Reason code nên ổn định, không lấy raw exception message hoặc stack trace làm giá trị chính.

## 9. Log level và severity

Log level cần có quy ước nhất quán.

| Level | Cách dùng gợi ý | Ví dụ |
| --- | --- | --- |
| TRACE | Chi tiết rất thấp, chỉ bật tạm thời. | Internal flow diagnostics đã redact. |
| DEBUG | Debug phát triển/điều tra có kiểm soát. | Policy branch hoặc dependency timing. |
| INFO | Hoạt động bình thường có ý nghĩa. | Session created, credential rotated. |
| WARN | Bất thường hoặc điều kiện cần chú ý. | Repeated MFA denial, fallback attempted. |
| ERROR | Thành phần không hoàn thành xử lý. | Session store write failed. |
| FATAL/CRITICAL | Service không thể tiếp tục an toàn. | Key material unavailable khi ký token. |

Không dùng ERROR cho mọi login failure do người dùng nhập sai; đó có thể là security event với outcome failure nhưng không phải lỗi ứng dụng. Ngược lại, một authentication bypass không nên bị ghi ở DEBUG chỉ vì request trả HTTP 200.

### Log level không thay severity của incident

Một event WARN không tự tương đương alert Medium. Severity phụ thuộc asset, exploitability, confidence và tác động. Detection engine cần logic riêng.

## 10. Secret leakage và redaction

Đây là phần quan trọng nhất trong logging review. Log có thể được sao chép sang SIEM, ticket, chat, email, backup và máy phân tích; một secret bị ghi một lần có thể tồn tại lâu ở nhiều nơi.

### Tuyệt đối không ghi trực tiếp

- Password hoặc password reset token.
- OTP, TOTP seed và recovery code.
- Session cookie.
- Access token, refresh token và bearer token.
- Authorization code và PKCE verifier.
- Private key, client secret và API key value.
- Database password hoặc secret manager response.
- Full SAML assertion/OIDC token nếu không có yêu cầu đặc biệt và bảo vệ tương ứng.
- Raw Authorization header.
- Request body có credential.

### Các nguồn rò rỉ thường gặp

- Log toàn bộ HTTP request/response.
- Exception chứa JDBC URL hoặc authentication header.
- Debug dump của security context.
- Tracing tự động capture header/query parameter.
- Reverse proxy access log ghi query string.
- Browser analytics ghi form field.
- Test failure report chứa cookie hoặc OTP.
- CI/CD debug log in toàn bộ environment.
- Heap dump, crash dump và diagnostic bundle.

### Redaction strategy

- Allowlist field được phép log.
- Redact ở nguồn trước khi gửi pipeline.
- Chặn header nhạy cảm như Authorization, Cookie và Set-Cookie.
- Loại bỏ query parameter có code/token/reset secret.
- Không serialize object chứa credential.
- Có unit test cho logger/serializer.
- Scan log pipeline và sample export định kỳ.
- Nếu secret đã lộ, xử lý như credential compromise: revoke/rotate và xác định bản sao.

Redaction ở cuối pipeline là lớp bổ sung, không thay thế việc ngăn secret đi vào log từ đầu.

## 11. PII minimization và privacy review

Log xác thực có thể chứa dữ liệu cá nhân và hành vi người dùng.

### Dữ liệu cần cân nhắc

- Email, phone, username.
- IP address và geolocation.
- User agent và device fingerprint.
- Tenant, role và group membership.
- Authentication history.
- Risk score và behavioral signal.
- Support/admin activity.

### Câu hỏi review

- Trường này phục vụ mục đích nào?
- Có thể thay bằng reference hoặc network zone không?
- Ai được truy cập?
- Có cần lưu ở mọi event không?
- Retention bao lâu?
- Có cần pseudonymization?
- Có thể export sang môi trường thấp hơn không?
- Có thể liên kết ngược về người dùng không?

### Pseudonymization

Dùng subject reference hoặc HMAC pseudonym có key được quản lý riêng có thể giảm việc lộ identifier thô. Hash email không key dễ bị dò dictionary vì không gian giá trị nhỏ. Pseudonymization không phải anonymization nếu tổ chức vẫn có thể ánh xạ về người dùng.

## 12. Log injection và dữ liệu đầu vào không tin cậy

Attacker có thể đưa newline, delimiter hoặc control character vào username, URL, user agent hay error field để làm giả dòng log hoặc phá parser.

### Rủi ro

- Forged log entry.
- JSON/log parser confusion.
- Terminal escape/control sequence.
- SIEM query injection khi downstream xử lý không an toàn.
- Alert title bị chèn nội dung gây hiểu nhầm.

### Kiểm soát

- Dùng structured logger có serializer đúng chuẩn.
- Escape control characters.
- Giới hạn độ dài field.
- Không nối input trực tiếp vào dòng log.
- Chuẩn hóa Unicode theo policy.
- Giữ raw input chỉ khi có mục đích và bảo vệ phù hợp.
- Không dùng log field làm câu lệnh query động.
- Kiểm thử CR/LF, delimiter, Unicode và chuỗi quá dài.

Ví dụ, username test có newline phải được serialize thành một field duy nhất, không tạo record giả thứ hai.

## 13. Timestamp, correlation và distributed tracing

Một authentication flow có thể đi qua Gateway, RP, IdP, MFA provider, Session Service và API. Logging review cần xác minh có thể nối các record mà không lộ credential.

### Timestamp

- Dùng UTC và định dạng chuẩn.
- Có timezone rõ ràng.
- Phân biệt occurred_at và recorded_at khi pipeline bất đồng bộ.
- Đồng bộ clock giữa service, broker và storage.
- Theo dõi clock skew và event đến muộn.

### Correlation

Dùng request_id, interaction_id, correlation_id và trace_id theo mục đích. ID cần được tạo/kiểm soát ở boundary tin cậy và truyền theo policy.

Không dùng access token, session cookie hoặc authorization code làm correlation ID. Không đưa email/username vào trace baggage nếu không cần.

### Sampling

Trace sampling có thể bỏ qua request. Không dựa vào sampled trace làm nguồn duy nhất cho audit-critical action. Security event và audit record cần delivery policy riêng; trace phục vụ phân tích dependency và latency.

## 14. Integrity và provenance của log

Log có thể bị giả mạo nếu producer không xác thực hoặc bị sửa ở storage.

### Provenance

- Xác thực producer bằng workload identity/mTLS.
- Ghi service, environment, build/version.
- Broker ACL giới hạn publish theo topic.
- Collector xác minh schema và producer.
- Tenant context đến từ nguồn tin cậy.
- Có event ID và sequence/reference phù hợp.

### Integrity

- Tách quyền append khỏi update/delete.
- Dùng append-only hoặc immutable storage cho audit cần thiết.
- Hash/sign batch hoặc checkpoint khi yêu cầu.
- Lưu backup độc lập.
- Audit việc thay đổi retention, key và access policy.
- Kiểm tra gap, duplicate và bất thường ingestion.

Hash/signature giúp phát hiện sửa đổi khi key/anchor được bảo vệ; chúng không tự chứng minh event nguồn là đúng hoặc đầy đủ.

## 15. Pipeline reliability và log loss

Logging review cần xem log có đến nơi và đến đúng thời điểm không.

### Failure mode

- Agent/collector bị dừng.
- Broker unavailable hoặc queue đầy.
- Network partition.
- Storage quota hết.
- Schema mới bị consumer từ chối.
- Retry tạo duplicate.
- Out-of-order delivery.
- Dead-letter queue không có owner.
- Sampling/drop rule cấu hình sai.
- Backpressure làm tăng latency.

### Kiểm soát

- Durable buffer/outbox cho event quan trọng.
- Retry có backoff và giới hạn.
- Deduplication theo event ID.
- Dead-letter queue có alert và quy trình xử lý.
- Metric cho dropped event, queue lag và ingestion delay.
- Schema compatibility test.
- Replay có kiểm soát.
- Capacity planning và retention budget.

Không để metrics/debug logging outage làm login thất bại nếu không cần thiết. Với audit-critical state change, cần durable write hoặc outbox theo policy; không âm thầm drop.

## 16. Access control cho log và audit

Log thường chứa dữ liệu nhạy cảm và có thể cho phép dựng lại hoạt động của người dùng.

### Tách quyền

- Application chỉ publish log của service mình.
- Analyst query theo phạm vi được cấp.
- Auditor có quyền read-only và scope rõ.
- Export operator cần approval/purpose.
- Storage administrator không mặc nhiên có quyền đọc nội dung.
- Retention administrator không sửa record nghiệp vụ.
- Break-glass access được ghi audit và review sau sử dụng.

### Review các đường truy cập

- Dashboard và SIEM search.
- API query/export.
- Object storage/archive.
- Dead-letter queue.
- Backup/replica.
- Developer console và debug endpoint.
- Support tooling và incident ticket.
- Vendor/SaaS integration.

Audit cả query, export, quyền mới cấp và thay đổi retention. Tenant isolation phải áp dụng ở ingestion, query và export.

## 17. Retention và lifecycle

Không giữ mọi log vô thời hạn. Retention cần theo purpose, sensitivity, threat model và yêu cầu pháp lý/hợp đồng.

### Phân lớp

- Hot: truy vấn gần thời gian thực và detection.
- Warm: điều tra thường xuyên.
- Archive: lưu dài hạn, ít truy cập.
- Expired: hết hạn và được xử lý theo policy.

### Review retention

- Event family nào được giữ?
- Thời hạn và lý do?
- Backup/replica có cùng lifecycle không?
- Legal hold được áp dụng thế nào?
- Có thể xóa theo subject/request khi cần không?
- Archive có integrity verification?
- Export tạm có bị xóa sau thời hạn?
- Ai phê duyệt thay đổi retention?

Không chọn thời hạn chỉ vì storage còn chỗ. Lưu quá lâu tăng privacy risk; lưu quá ngắn làm mất khả năng điều tra.

## 18. Khả năng dùng log cho detection và incident response

Một log chỉ hữu ích khi có thể trả lời câu hỏi điều tra và hỗ trợ detection rule.

### Detection use case

| Use case | Log cần có |
| --- | --- |
| Brute force | Account reference, source, auth method, outcome, reason, time. |
| Password spraying | Source, distinct account reference, tenant, time window. |
| Credential stuffing | Failure/success sequence, device/network context, session event. |
| MFA fatigue | Challenge create/deny/expire/approve và interaction reference. |
| Recovery abuse | Recovery request, channel change, approval, completion. |
| Session theft | Session create/use/revoke, context change, downstream request. |
| Token misuse | Issuer, audience, client, scope summary, validation outcome. |
| Federation attack | Issuer/key, state/nonce/PKCE or SAML validation result. |
| Workload compromise | Principal, certificate/attestation, target service, scope. |
| Privilege change | Actor, subject, before/after, approval và policy version. |

### Detection quality

- Event có tới đúng nơi không?
- Có field để group theo account/source/tenant?
- Reason code có phân biệt credential failure và dependency outage?
- Có correlation giữa login success và hành động sau login?
- Alert có reference tới raw event/audit record?
- Sampling có làm mất event cần detection?
- Analyst có quyền query đúng scope?

Logging review không cần thiết kế mọi detection rule, nhưng phải xác định log có đủ dữ liệu và chất lượng để detection hoạt động.

## 19. Review log configuration và deployment

Log policy có thể đúng trong source nhưng bị vô hiệu hóa bởi cấu hình production.

### Kiểm tra

- Log level theo environment.
- Sensitive header/body capture.
- Proxy access log format.
- Trace auto-instrumentation và baggage.
- Sampling và drop filters.
- Redaction configuration.
- Retention/rotation.
- Disk/queue limit.
- TLS và certificate cho log transport.
- Broker topic ACL.
- SIEM parser/schema mapping.
- Debug endpoint và admin access.
- Feature flag thay đổi logging behavior.

### Configuration drift

So sánh cấu hình giữa dev, staging và production. Production không nên bật debug body logging tùy tiện; staging cũng không nên chứa production secret hoặc dữ liệu thật chỉ để tiện debug.

Mọi thay đổi logging policy nên có owner, review và version. Emergency debug logging cần giới hạn thời gian, scope, quyền và kế hoạch tắt.

## 20. Java: structured logging an toàn

Ứng dụng Java nên log field đã được chọn lọc, không serialize toàn bộ request hoặc security context.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AuthenticationLog {

    private static final Logger log =
            LoggerFactory.getLogger(AuthenticationLog.class);

    private AuthenticationLog() {
    }

    public static void loginFailed(
            String subjectRef,
            String tenantRef,
            String correlationId,
            String reasonCode
    ) {
        log.warn(
                "event_type={} subject_ref={} tenant_ref={} correlation_id={} reason_code={}",
                "authentication.login.failed",
                safe(subjectRef),
                safe(tenantRef),
                safe(correlationId),
                safe(reasonCode)
        );
    }

    private static String safe(String value) {
        if (value == null) {
            return "unknown";
        }

        String normalized = value
                .replace("\r", "")
                .replace("\n", "");

        return normalized.length() > 120
                ? normalized.substring(0, 120)
                : normalized;
    }
}
~~~

Ví dụ minh họa cần bổ sung structured encoder/JSON layout trong ứng dụng thực tế. Hàm safe chỉ là lớp phòng vệ đơn giản, không thay thế schema validation, output encoding và redaction. subjectRef phải được tạo từ authenticated context, không nhận trực tiếp từ caller.

### Không log request object

Không ghi toàn bộ request, headers, cookies, Authentication object, token claims hoặc DTO có password. Tạo log/event DTO riêng với allowlist field. Không đưa exception có thể chứa JDBC URL, authorization header hoặc secret vào message.

## 21. Java: kiểm thử redaction và log injection

Kiểm thử logger cần xác minh dữ liệu nhạy cảm không xuất hiện trong output và input độc hại không tạo record giả.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class AuthenticationLogTest {

    @Test
    void untrustedNewlinesAreNotWrittenAsExtraLogLines() {
        String input = "learner-42\r\nlevel=INFO event=admin_login";
        String output = sanitizeForLog(input);

        assertFalse(output.contains("\r"));
        assertFalse(output.contains("\n"));
        assertTrue(output.startsWith("learner-42"));
    }

    @Test
    void secretFieldsAreExcludedFromEventPayload() {
        var event = AuthenticationEventFactory.loginFailed(
                "subject-ref-42",
                "tenant-ref-8",
                "corr-2a91",
                "invalid_credential"
        );

        String serialized = serialize(event);

        assertFalse(serialized.contains("TEST_ONLY_PASSWORD"));
        assertFalse(serialized.contains("TEST_ONLY_TOKEN"));
        assertFalse(serialized.contains("TEST_ONLY_OTP"));
    }
}
~~~

Các hàm sanitizeForLog, serialize và AuthenticationEventFactory là abstraction minh họa. Trong dự án thực tế, test nên dùng logger appender/encoder thật để kiểm tra output cuối cùng, gồm cả MDC, exception và auto-instrumentation.

## 22. Phương pháp thực hiện logging review

Một review có thể đi theo trình tự:

1. Xác định scope, owner và mục tiêu bảo mật.
2. Lập inventory producer, collector, broker, store và consumer.
3. Vẽ data flow và trust boundary.
4. Liệt kê authentication flow và event coverage cần có.
5. Lấy sample log đã được phép và redact.
6. Đánh giá schema, semantics, actor/subject, reason code và correlation.
7. Scan secret leakage, PII và log injection.
8. Kiểm tra transport, producer authentication, integrity và access control.
9. Kiểm tra retention, backup, export và deletion.
10. Đánh giá detection/incident use case và khả năng truy vấn.
11. Kiểm thử failure mode, event loss, duplicate và clock skew.
12. Ghi finding, risk, owner, remediation và verification criteria.

### Evidence review

- Log sample đã redact.
- Schema và mapping tài liệu.
- Configuration snapshot.
- Data flow/trust-boundary diagram.
- Access policy và retention policy.
- Pipeline health metrics.
- Test result và query mẫu.
- Owner/approval cho exception.

Không copy raw credential hoặc PII vào review report. Dùng reference và lưu bằng chứng gốc trong nơi được kiểm soát.

## 23. Ma trận kiểm thử logging

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Login success | Đăng nhập fixture hợp lệ. | Có event với actor/subject, method, outcome và correlation. |
| Login failure | Password test sai. | Có reason code; không có password. |
| MFA deny | Từ chối challenge. | Có event gắn đúng interaction. |
| Passkey registration | Enroll credential test. | Log registration result, không có private key. |
| OIDC callback | Hoàn tất hoặc làm sai callback test. | Issuer/client/result được ghi; không có code/token. |
| Session revoke | Revoke session test. | Log kết quả thực tế và propagation reference. |
| Recovery | Reset bằng fixture token. | Có event lifecycle; không ghi reset token. |
| Admin change | Thay đổi MFA/issuer policy. | Actor, target, before/after summary và policy version. |
| Actor spoofing | Gửi actor giả trong request body. | Log lấy actor từ trusted context. |
| Log injection | Gửi CR/LF và control characters. | Không tạo log line giả hoặc phá parser. |
| Header redaction | Gửi Authorization/Cookie trong test. | Header không xuất hiện trong log. |
| Query redaction | Gửi URL có code/token fixture. | Secret parameter bị loại bỏ. |
| PII minimization | Kiểm tra email/IP/device fields. | Chỉ giữ field cần thiết theo policy. |
| Structured schema | Parse log JSON. | Field type/name đúng contract. |
| Reason classification | Giả lập password sai và DB timeout. | Hai outcome/reason được phân biệt. |
| Correlation | Login qua nhiều service. | Có thể nối event mà không dùng token làm ID. |
| Clock skew | Mô phỏng node lệch giờ. | Timestamp/lag có thể phân biệt và cảnh báo. |
| Duplicate event | Replay cùng event ID. | Consumer deduplicate hoặc idempotent. |
| Broker outage | Ngắt broker trong staging. | Durable event được retry; lag được đo. |
| Collector drop | Mô phỏng mất log. | Drop metric/alert phát hiện. |
| Sampling | Kiểm tra security event và trace sampling. | Audit/security event quan trọng không bị sampling mất ngoài policy. |
| Producer spoofing | Publish từ identity không được phép. | Broker/collector từ chối. |
| Tenant isolation | Query log tenant khác. | Access bị từ chối. |
| Export access | Analyst export log. | Export có approval và audit. |
| Retention | Kiểm tra event hết hạn. | Lifecycle policy được thực thi. |
| Integrity | Sửa record trong test store. | Integrity verification phát hiện. |
| Log access audit | Query/export/change retention. | Hành động truy cập log được ghi. |
| Debug configuration | Bật debug trong môi trường test. | Secret vẫn bị redact; production policy không bị thay đổi. |
| Exception leakage | Tạo lỗi JDBC/authentication. | Stack/message không chứa credential. |
| Incident reconstruction | Dựng account takeover fixture. | Có thể nối login, MFA, session, recovery và API events. |

## 24. Các lỗi logging thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Log toàn bộ request | Password, token, cookie bị lộ. | Allowlist field và redaction tại nguồn. |
| Chỉ ghi free-text message | Khó query và detection. | Structured schema và reason code. |
| Không ghi actor/subject riêng | Không xác định được ai làm gì. | Identity context rõ. |
| Dùng IP làm identity | NAT/VPN gây nhầm lẫn. | Principal reference và source context riêng. |
| Debug log bật lâu dài | Tăng PII/secret exposure. | Time-bound debug và config review. |
| Trace sampling làm mất audit | Không thể chứng minh action. | Audit/security event delivery riêng. |
| Không có correlation | Không nối được multi-hop flow. | Interaction/correlation/trace ID. |
| Log dependency failure thành credential failure | Detection sai và triage chậm. | Outcome/reason taxonomy rõ. |
| Redact ở cuối pipeline | Secret đã đi qua broker/collector. | Chặn tại source, redact nhiều lớp. |
| Không xác thực producer | Có thể chèn log giả. | Workload identity/mTLS và broker ACL. |
| Không theo dõi ingestion lag | SOC dùng dữ liệu cũ. | Lag/drop metrics và alert. |
| Retention không rõ | Quá lưu hoặc mất evidence. | Policy theo purpose và owner. |
| Metric label chứa user ID | Cardinality và privacy risk. | Aggregate, pseudonymize và label giới hạn. |
| Exception chứa connection string | Lộ DB credential. | Sanitize exception và secret-safe config. |
| Không audit log export | Insider có thể lấy dữ liệu không dấu vết. | Audit query/export và separation of duties. |

## 25. Ví dụ thực tế: Learning Platform

Learning Platform gồm IdP của trường, Learning Portal, Staff Console, Session Service, Enrollment API và Security Operations.

### Luồng login

1. Gateway nhận request và tạo correlation ID.
2. Portal khởi tạo OIDC flow.
3. IdP xác minh password/passkey và MFA.
4. RP kiểm tra issuer, state, nonce, token profile.
5. Session Service tạo session.
6. Enrollment API xác minh token/audience và xử lý request.
7. Các service phát security event theo schema chung.
8. Pipeline chuẩn hóa và chuyển event tới SIEM.

### Kết quả logging review

Review phát hiện gateway access log đang ghi query string đầy đủ, trong đó có thể chứa authorization code ở callback. Đồng thời, một số API log cả Cookie header khi request lỗi.

### Remediation

- Cấu hình proxy bỏ query parameter nhạy cảm khỏi access log.
- Redact Authorization, Cookie và Set-Cookie ở application logger.
- Chuyển callback log sang field allowlist: issuer, client reference, result, reason và correlation ID.
- Thêm test scan log sau OIDC callback.
- Kiểm tra log archive và export cũ theo incident/retention policy.
- Rotate/revoke credential nếu evidence cho thấy token/session thực tế đã bị lộ.
- Bổ sung owner và regression test cho logging configuration.

### Xác minh

Chạy login success/failure, callback sai state và session revoke trong staging. Parse log output từ gateway, Portal, IdP và Session Service; xác nhận không có authorization code, cookie hoặc token, nhưng vẫn nối được flow bằng correlation ID.

## 26. Báo cáo finding của logging review

Một finding cần mô tả vấn đề, bằng chứng và tác động có thể đánh giá.

### Cấu trúc

- Finding ID và title.
- Affected service/environment.
- Log source/pipeline component.
- Policy/control expectation.
- Observed behavior.
- Evidence reference đã redact.
- Sensitive data hoặc event coverage bị ảnh hưởng.
- Exploitability và impact.
- Severity rationale.
- Recommendation.
- Owner và due date.
- Verification test và retest result.

### Severity tham khảo

| Mức | Ví dụ |
| --- | --- |
| Critical | Log chứa bearer token/private key dùng được cho account đặc quyền hoặc producer giả mạo có thể chèn/xóa audit diện rộng. |
| High | Password/OTP/session cookie bị ghi vào log truy cập rộng; thiếu log khiến không thể phát hiện hoặc thu hồi compromise nghiêm trọng. |
| Medium | Thiếu correlation/reason code hoặc ingestion lag làm detection chậm; PII được lưu vượt mục đích. |
| Low | Field naming không nhất quán hoặc log level gây khó vận hành nhưng không làm mất kiểm soát bảo mật. |
| Informational | Cải thiện tài liệu, dashboard hoặc test coverage. |

Severity phụ thuộc khả năng khai thác, phạm vi log access, loại secret, số account/tenant và biện pháp bù. Nếu bearer credential thực sự bị ghi, cần đánh giá như một incident tiềm năng, không chỉ là lỗi format log.

## 27. Checklist logging review

- [ ] Scope, owner và authentication flow đã được xác định.
- [ ] Có inventory producer, collector, broker, store và consumer.
- [ ] Data flow/trust boundary được lập.
- [ ] Password, MFA, passkey, certificate, token, session, recovery và workload event được bao phủ.
- [ ] Structured schema có timestamp, service, event type, actor/subject, tenant, outcome và reason.
- [ ] Actor/tenant đến từ trusted context, không từ caller tự khai.
- [ ] Credential failure được phân biệt với dependency/internal failure.
- [ ] Không log password, OTP, recovery code, token, cookie, authorization code, private key hoặc client secret.
- [ ] Authorization/Cookie headers và query secret được redact ở nguồn.
- [ ] PII được tối thiểu hóa và có retention.
- [ ] Log injection/control character được xử lý an toàn.
- [ ] Timestamp UTC, correlation và trace propagation hoạt động.
- [ ] Audit/security event quan trọng không bị trace sampling làm mất.
- [ ] Producer được xác thực; broker ACL và tenant isolation được cấu hình.
- [ ] Retry, duplicate, dead-letter, drop và ingestion lag được theo dõi.
- [ ] Append-only/integrity và backup phù hợp với audit requirement.
- [ ] Query/export/delete/retention change được kiểm soát và audit.
- [ ] Log có đủ context cho detection và incident reconstruction.
- [ ] Debug logging có scope, time limit và approval.
- [ ] Có test cho redaction, injection, outage, clock skew và schema compatibility.
- [ ] Finding có severity, evidence, owner, remediation và retest.

## 28. Tự kiểm tra

**Câu 1.** Logging review khác audit review như thế nào?

**Đáp án:** Logging review đánh giá toàn bộ cách tạo, truyền, xử lý và sử dụng log. Audit review tập trung vào record cần làm bằng chứng, provenance, integrity, retention và truy cứu hành động. Hai phạm vi giao nhau nhưng không đồng nhất.

**Câu 2.** Vì sao không nên log toàn bộ HTTP request trong authentication endpoint?

**Đáp án:** Request có thể chứa password, OTP, token, cookie hoặc authorization code. Log sẽ nhân bản bearer secret ra nhiều hệ thống và làm tăng nguy cơ compromise.

**Câu 3.** Actor và subject khác nhau thế nào?

**Đáp án:** Actor thực hiện hành động; subject là account được xác thực hoặc bị tác động. Ví dụ operator reset MFA cho learner thì operator là actor và learner là subject.

**Câu 4.** Vì sao phải phân biệt invalid credential với dependency timeout?

**Đáp án:** Hai nguyên nhân có ý nghĩa bảo mật và vận hành khác nhau. Gộp chúng làm detection sai, triage chậm và dashboard phản ánh sai chất lượng login.

**Câu 5.** Trace sampling có thể thay thế security event không?

**Đáp án:** Không. Sampling có thể bỏ request; event/audit quan trọng cần delivery policy riêng.

**Câu 6.** Vì sao log injection cần được kiểm thử?

**Đáp án:** Input có CR/LF hoặc control character có thể tạo dòng giả, phá parser và làm analyst hiểu sai bằng chứng.

**Câu 7.** Hash/signature có tự chứng minh log nguồn là đúng không?

**Đáp án:** Không. Chúng giúp kiểm tra integrity sau khi record được phát hành; vẫn cần producer authentication, source authority và schema validation.

**Câu 8.** Vì sao cần theo dõi ingestion lag và dropped event?

**Đáp án:** SOC có thể đang phân tích dữ liệu trễ hoặc thiếu. Pipeline health là điều kiện để detection và incident response đáng tin.

**Câu 9.** Có nên dùng email hoặc session ID làm metric label không?

**Đáp án:** Không nên. Chúng làm cardinality tăng cao và có thể tiết lộ dữ liệu cá nhân hoặc reference nhạy cảm; nên dùng label có tập giá trị nhỏ và dữ liệu tổng hợp.

**Câu 10.** Nếu phát hiện token đã bị ghi vào log, cần làm gì?

**Đáp án:** Đánh giá khả năng sử dụng và phạm vi bản sao; revoke/rotate credential liên quan theo incident policy, bảo toàn evidence, kiểm tra log/archive/export, khắc phục nguồn ghi và thêm regression test.

## Ghi nhớ

**Logging review** đánh giá chất lượng logging từ nguồn phát tới nơi lưu và nơi sử dụng. Với authentication, log cần bao phủ password, MFA, passkey, federation, token, session, recovery và workload identity; có schema nhất quán, actor/subject rõ, reason code chính xác và correlation xuyên service.

Không ghi password, OTP, token, cookie, authorization code, private key hoặc secret manager response. Bảo vệ log bằng producer authentication, transport security, integrity, access control, retention và monitoring pipeline. Log phải đủ context cho detection và incident response nhưng chỉ giữ dữ liệu cần thiết. **Logging tốt giúp hiểu điều gì đã xảy ra mà không tạo thêm một kho credential dễ bị khai thác.**
