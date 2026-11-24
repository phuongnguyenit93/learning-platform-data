# Audit trail (Dấu vết kiểm toán cho hoạt động xác thực)

> **Chương:** Monitoring và audit  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Xây dựng dấu vết kiểm toán đáng tin cậy cho các quyết định và thay đổi liên quan đến identity; ghi nhận actor, subject, action, target, outcome, thời điểm và nguồn gốc; bảo đảm tính đầy đủ, toàn vẹn, khả năng truy vết và kiểm soát truy cập; hỗ trợ điều tra, chứng minh việc thực thi policy và quản lý dữ liệu theo retention/privacy.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích audit trail và phân biệt audit record với application log, authentication event, metric, trace và event sourcing.
2. Xác định hành động xác thực, quản trị và vòng đời identity cần được kiểm toán.
3. Thiết kế record có actor, subject, action, target, result, reason, source, timestamp và correlation.
4. Phân biệt người khởi tạo, người phê duyệt, workload thực thi và đối tượng bị tác động.
5. Ghi nhận thay đổi trạng thái theo cách đủ để điều tra nhưng không làm lộ password, token, OTP hoặc private key.
6. Bảo đảm audit record được tạo tại nguồn có thẩm quyền và nhất quán với transaction nghiệp vụ.
7. Áp dụng append-only storage, hash chain, signed checkpoint, WORM và separation of duties.
8. Quản lý chain of custody, retention, legal hold, quyền truy cập và export bằng chứng.
9. Thiết kế audit review, detection, forensic timeline và incident response.
10. Kiểm thử tính đầy đủ, tính toàn vẹn, ordering, privacy, khả năng phục hồi và các đường truy cập audit.

## 1. Audit trail là gì?

**Audit trail (dấu vết kiểm toán)** là tập hợp các bản ghi có cấu trúc, được liên kết theo thời gian và nguồn gốc, mô tả các hành động quan trọng đã xảy ra trong hệ thống. Với authentication, audit trail cho biết danh tính được tạo, xác minh, liên kết, thay đổi, sử dụng hoặc thu hồi như thế nào; ai hoặc thành phần nào thực hiện; kết quả ra sao; và policy nào được áp dụng.

Một audit trail hữu ích phải cho phép người có thẩm quyền trả lời:

- Ai đã thực hiện hành động?
- Hành động nào đã xảy ra?
- Đối tượng hoặc account nào bị tác động?
- Hành động diễn ra khi nào và từ thành phần nào?
- Kết quả thành công, thất bại, bị từ chối hay đang chờ?
- Bằng chứng xác thực và policy nào liên quan?
- Sự kiện trước/sau nào tạo thành cùng một workflow?
- Record có bị sửa, xóa hoặc thiếu trong quá trình lưu trữ không?

### Ví dụ

Một quản trị viên gỡ authenticator khỏi tài khoản học viên. Audit trail cần thể hiện:

- Actor là quản trị viên đã xác thực bằng privileged access workflow.
- Subject là tài khoản học viên.
- Action là remove authenticator.
- Target là authenticator reference đã được bảo vệ.
- Reason và approval reference theo policy.
- Thời điểm, nguồn, tenant và kết quả.
- Session hoặc interaction reference liên quan.
- Policy version đã được áp dụng.

Chỉ ghi một dòng “MFA removed” không đủ để điều tra nếu không biết ai thực hiện và account nào bị ảnh hưởng.

## 2. Phân biệt audit trail với log, event và event sourcing

Các khái niệm có thể dùng chung hạ tầng nhưng không có cùng mục đích.

| Khái niệm | Mục đích | Đặc điểm |
| --- | --- | --- |
| **Audit trail** | Bằng chứng về hành động, quyết định và thay đổi cần truy cứu. | Có actor/target/result, provenance, integrity và retention. |
| Authentication event | Mô tả một sự kiện xác thực cụ thể. | Schema event, outcome và context; có thể là đầu vào của audit. |
| Application log | Debug và vận hành ứng dụng. | Có thể chi tiết, ngắn hạn và thay đổi theo phiên bản code. |
| Metric | Đo số lượng, tỷ lệ và xu hướng. | Dữ liệu tổng hợp, không phải bằng chứng cho từng hành động. |
| Distributed trace | Theo dõi request qua nhiều service. | Timing và dependency; trace có thể bị sampling. |
| Event sourcing | Lưu chuỗi domain event làm nguồn dựng trạng thái ứng dụng. | Phục vụ mô hình dữ liệu và replay state, không mặc nhiên là audit evidence. |

Không phải mọi log đều là audit trail. Debug log có thể bị rotate, sampling hoặc xóa theo vận hành; event sourcing có thể chỉ lưu thay đổi domain mà không có actor, approval hoặc nguồn xác thực cần cho kiểm toán.

### Một hành động có thể tạo nhiều record

Ví dụ admin thay đổi MFA policy:

- Application log ghi lỗi hoặc latency của request.
- Authentication event ghi policy change initiated/completed.
- Audit trail ghi actor, target, before/after summary, approval, result và policy version.
- Metric tăng bộ đếm policy change.
- Trace nối request qua Admin API và Identity Service.

Các bản ghi bổ sung nhau nhưng không thay thế audit record.

## 3. Phạm vi audit trong vòng đời identity

Audit trail cần bao phủ những hành động có thể thay đổi danh tính, bằng chứng xác thực, quyền hoặc trạng thái phiên.

~~~mermaid
flowchart TD
    A["Account created / linked"] --> B["Credential enrolled"]
    B --> C["Authentication decision"]
    C --> D["MFA / passkey / federation"]
    D --> E["Token and session issued"]
    E --> F["Privilege / policy change"]
    F --> G["Recovery / credential change"]
    G --> H["Logout / revoke / deprovision"]
    C --> I["Audit trail"]
    E --> I
    F --> I
    G --> I
    H --> I
~~~

### Nhóm hành động cần xem xét

| Nhóm | Hành động cần audit |
| --- | --- |
| Account lifecycle | Tạo, kích hoạt, suspend, restore, deprovision, merge. |
| Identity linking | Link/unlink external identity, đổi primary identity. |
| Credential | Password reset/change, passkey add/remove, certificate issue/revoke. |
| Authentication | Login success/failure, step-up, MFA approve/deny, federation callback. |
| Session/token | Session create/rotate/revoke, token grant/revoke, refresh-token reuse. |
| Recovery | Recovery request, verification, completion, thay recovery channel. |
| Authorization | Role/group/tenant membership change, policy decision nhạy cảm. |
| Administration | Thay issuer, signing key, MFA policy, trusted device, risk threshold. |
| Privileged access | Elevation, break-glass, impersonation, support access. |
| Service identity | Workload credential issue/rotation/revoke, client registration change. |
| Audit administration | Query/export/delete/retention change, integrity verification. |

Không nhất thiết lưu mọi lần đọc tài nguyên thông thường trong cùng audit stream. Xác định phạm vi dựa trên rủi ro, yêu cầu điều tra, privacy và nghĩa vụ lưu giữ.

## 4. Nguyên tắc của audit trail đáng tin cậy

Một audit trail tốt cần đáp ứng nhiều thuộc tính đồng thời:

1. **Attributable:** có thể xác định actor và nguồn thực hiện hành động.
2. **Accurate:** record phản ánh đúng kết quả và trạng thái đã commit.
3. **Complete:** các hành động thuộc phạm vi được ghi nhận, có thể phát hiện khoảng trống.
4. **Chronological:** có timestamp và quan hệ thứ tự đủ để dựng timeline.
5. **Tamper-evident:** sửa đổi hoặc xóa trái phép có thể bị phát hiện.
6. **Confidential:** chỉ người được phép mới đọc được dữ liệu.
7. **Available:** record có thể truy xuất khi điều tra hoặc audit.
8. **Traceable:** liên kết được các hành động qua account, session, request và service.
9. **Understandable:** vocabulary, schema và reason code có ý nghĩa ổn định.
10. **Proportionate:** chỉ giữ dữ liệu cần thiết và trong thời hạn phù hợp.

### Audit không tự chứng minh ý định của con người

Một record có actor identity chứng minh hệ thống đã gắn hành động với principal được xác thực. Nó không tự chứng minh người đó thực sự có ý định hoặc không bị malware điều khiển. Khi cần, kết hợp authentication assurance, approval workflow, device context và evidence độc lập.

Chữ ký của audit service chứng minh record được phát hành bởi service/key đó; không phải chữ ký của con người đã nhấn nút.

## 5. Cấu trúc một audit record

Schema nên đủ ổn định để nhiều service ghi cùng ngữ nghĩa.

| Field | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| audit_id | ID duy nhất của record. | Dùng deduplication và tham chiếu bằng chứng. |
| schema_version | Version cấu trúc. | Quản lý compatibility. |
| event_type | Hành động đã xảy ra. | Vocabulary có kiểm soát. |
| occurred_at | Thời điểm hành động theo nguồn. | UTC, có độ chính xác phù hợp. |
| recorded_at | Thời điểm record được ghi bền vững. | Phân biệt với occurred_at. |
| actor | Principal thực hiện hành động. | User, workload, client hoặc operator. |
| subject | Principal/account được đại diện hoặc bị tác động. | Có thể khác actor. |
| approver | Người/phần tử phê duyệt nếu có. | Lưu approval reference. |
| target | Đối tượng bị tác động. | Account, credential, session, policy. |
| action | Hành động và phạm vi. | Ví dụ credential.remove. |
| result | Kết quả cuối. | Success, denied, failed, pending. |
| reason_code | Lý do chuẩn hóa. | Không dùng raw exception. |
| source | Service, client, device hoặc network context. | Theo privacy policy. |
| tenant_ref | Tenant đã được xác minh. | Không tin giá trị client tự khai. |
| correlation_id | Liên kết workflow. | Không dùng token/cookie làm ID. |
| causation_id | Record/event gây ra hành động này. | Hữu ích cho chuỗi workflow. |
| policy_version | Policy áp dụng. | Hỗ trợ tái dựng quyết định. |
| change_summary | Tóm tắt thay đổi đã được phép ghi. | Redact giá trị nhạy cảm. |
| evidence_refs | Tham chiếu record/bằng chứng liên quan. | Không nhúng secret. |

### Ví dụ JSON

~~~json
{
  "audit_id": "aud-01J8N3R2",
  "schema_version": 1,
  "event_type": "identity.authenticator.removed",
  "occurred_at": "2026-11-22T10:21:14.120Z",
  "recorded_at": "2026-11-22T10:21:14.128Z",
  "actor": {
    "type": "operator",
    "issuer": "https://staff-id.example.edu",
    "subject_ref": "operator-ref-31"
  },
  "subject": {
    "type": "user",
    "subject_ref": "learner-ref-82"
  },
  "target": {
    "type": "authenticator",
    "reference": "auth-ref-19"
  },
  "action": "remove",
  "result": "success",
  "reason_code": "verified_account_recovery",
  "tenant_ref": "tenant-ref-12",
  "correlation_id": "corr-6a20",
  "policy_version": "recovery-policy-8",
  "change_summary": {
    "attribute": "authenticator_status",
    "from": "active",
    "to": "revoked"
  }
}
~~~

Ví dụ dùng reference giả và không chứa secret. Trong hệ thống thực tế, subject_ref và target reference cần được bảo vệ theo quyền truy cập và retention.

## 6. Actor, subject, approver và producer

Audit record phải phân biệt các vai trò.

- **Actor:** principal khởi tạo hoặc thực hiện hành động.
- **Subject:** account hoặc identity bị tác động, hoặc người mà actor đại diện.
- **Approver:** principal phê duyệt theo workflow.
- **Producer:** service ghi record.
- **Source:** thiết bị, client, network hoặc upstream component.
- **Target:** resource cụ thể bị thay đổi.

### Ví dụ: helpdesk recovery

Helpdesk operator hỗ trợ học viên khôi phục tài khoản:

- Actor: operator.
- Subject: học viên.
- Approver: supervisor nếu policy yêu cầu.
- Producer: identity administration service.
- Target: recovery method hoặc authenticator.
- Source: admin console và managed workstation.

Không ghi actor là học viên chỉ vì tài khoản học viên đang được xử lý. Điều này làm sai lệch trách nhiệm và gây khó khăn khi điều tra insider threat.

### Actor không được lấy từ request body

Không tin trường actor/user ID do browser gửi. Actor phải lấy từ authenticated principal của session/token hoặc workload identity đã xác minh. Nếu gateway truyền actor, backend cần xác thực gateway và bảo đảm header/context không thể bị caller giả mạo.

## 7. Action, target và thay đổi trước/sau

Một record nên mô tả rõ hành động và đối tượng thay đổi.

### Action

Dùng verb hoặc action code có vocabulary ổn định:

- create
- activate
- link
- unlink
- verify
- enroll
- remove
- rotate
- revoke
- suspend
- restore
- approve
- deny
- export
- change_policy

### Target

Target có thể là:

- User/account.
- Credential/authenticator.
- Session/token grant.
- External identity link.
- Tenant membership.
- Role/group.
- Federation issuer hoặc signing key.
- Authentication policy.
- Workload/service principal.

### Before/after

Với thay đổi trạng thái, ghi delta đủ để điều tra. Không sao chép toàn bộ object hoặc record nhạy cảm.

Ví dụ:

- MFA required: false → true.
- Account state: active → suspended.
- Role: learner → instructor.
- Certificate state: active → revoked.

Không ghi password cũ/mới, private key, OTP seed, recovery code hoặc raw token. Với dữ liệu nhạy cảm, chỉ ghi thuộc tính đã thay đổi và reference có quyền kiểm soát.

## 8. Nguồn có thẩm quyền và provenance

Audit record phải được phát ra từ thành phần biết kết quả thực tế và có quyền ghi nhận nó.

| Hành động | Nguồn có thẩm quyền |
| --- | --- |
| Password verification | Authentication service sau khi thực hiện verify. |
| MFA approval | MFA verifier sau khi kiểm tra challenge. |
| Passkey registration | WebAuthn RP sau khi xác minh ceremony. |
| OIDC login accepted | RP sau khi kiểm tra callback và token. |
| Session revoked | Session service/store sau khi commit revoke. |
| Token grant issued | Authorization Server sau khi phát token. |
| Role changed | Authorization/identity administration service sau khi commit. |
| DB secret accessed | Secret manager/provider audit. |
| Audit exported | Audit service sau khi tạo export. |

### Requested và completed là hai sự kiện khác nhau

Một admin gửi yêu cầu suspend account chưa có nghĩa account đã bị suspend. Có thể ghi:

1. account.suspension.requested
2. account.suspension.approved
3. account.suspension.completed hoặc account.suspension.failed

Điều này giúp phân biệt ý định, phê duyệt và trạng thái cuối.

### Provenance

Producer identity, service version, environment và nguồn request cần được xác minh. Nếu producer không xác thực hoặc có quyền publish tùy ý, attacker có thể chèn record giả vào audit trail.

## 9. Ghi audit nhất quán với transaction

Một thay đổi nghiệp vụ và audit record cần có quan hệ nhất quán. Nếu account đã bị suspend nhưng audit không ghi, điều tra sẽ thiếu bằng chứng. Nếu audit ghi thành công trước khi transaction rollback, record lại mô tả điều chưa xảy ra.

### Transactional outbox

Ghi thay đổi nghiệp vụ và audit event vào cùng database transaction, sau đó publisher gửi event tới audit pipeline.

~~~mermaid
flowchart TD
    R["Admin action"] --> T["Database transaction"]
    T --> S["Update identity / credential state"]
    T --> O["Insert audit outbox record"]
    S --> C["Commit"]
    O --> C
    C --> P["Outbox publisher"]
    P --> Q["Durable audit queue"]
    Q --> A["Audit store"]
    A --> V["Integrity verification"]
~~~

### Quy tắc

- Nếu nghiệp vụ rollback, audit record completed cũng phải rollback.
- Nếu commit thành công nhưng publish lỗi, outbox giữ record để retry.
- Publisher có thể gửi trùng; consumer deduplicate theo audit_id.
- Không đánh dấu published trước khi broker xác nhận.
- Có metric cho backlog, retry, dead-letter và delivery lag.
- Event requested/denied có thể được ghi theo transaction riêng nếu không có state change.

Không giả định exactly-once delivery xuyên database, broker và audit store. Thiết kế at-least-once cùng consumer idempotent thường thực tế hơn.

## 10. Append-only và tamper-evident storage

Audit trail cần chống sửa hoặc xóa trái phép. Append-only nghĩa là record mới được thêm vào; record cũ không bị sửa trực tiếp trong luồng vận hành bình thường.

### Kiểm soát lưu trữ

- Database role ghi audit chỉ được INSERT, không UPDATE/DELETE.
- Quyền quản trị retention tách khỏi quyền ghi record.
- Dùng immutable/WORM storage khi yêu cầu.
- Bật versioning và retention lock theo policy.
- Mã hóa at rest và bảo vệ encryption key.
- Backup sang account/region có quyền độc lập.
- Audit mọi hành động query, export, delete và thay đổi policy.
- Định kỳ kiểm tra restore và integrity.

Nếu cần sửa thông tin sai, tạo correction record tham chiếu record cũ và giải thích lý do. Không âm thầm ghi đè lịch sử.

### Append-only không đồng nghĩa không thể bị xóa

Một database user không có DELETE vẫn có thể bị administrator hoặc storage operator xóa ở tầng cao hơn. Cần phân tách quyền, immutable retention, external checkpoint và giám sát hoạt động quản trị.

## 11. Hash chain và signed checkpoint

Hash chain liên kết record với record trước để phát hiện thay đổi trong chuỗi.

~~~text
H0 = trusted_initial_anchor
H1 = HASH(H0 || canonical_record_1)
H2 = HASH(H1 || canonical_record_2)
H3 = HASH(H2 || canonical_record_3)
...
~~~

Nếu record giữa chuỗi bị sửa, hash tiếp theo sẽ không còn khớp với giá trị đã lưu.

### Canonicalization

Trước khi hash, phải xác định cách serialize ổn định:

- Thứ tự field.
- Encoding UTF-8.
- Chuẩn hóa timestamp.
- Cách biểu diễn null/number/string.
- Quy tắc escape và Unicode normalization nếu cần.
- Version của canonicalization.

Nếu cùng record có hai cách serialize khác nhau, hash sẽ khác dù nội dung logic giống nhau.

### Signed checkpoint

Có thể ký hash đầu/cuối của batch bằng signing key được bảo vệ trong KMS/HSM, rồi lưu checkpoint ở hệ thống độc lập hoặc archive có retention lock.

### Giới hạn

Hash chain không tự chứng minh event đã đầy đủ. Nếu attacker xóa record và có quyền tính lại toàn bộ chain cùng anchor, chuỗi mới vẫn có thể hợp lệ. Cần external anchoring, separation of duties, immutable backup và kiểm tra sequence/gap để tăng khả năng phát hiện.

Chữ ký checkpoint chứng minh holder của signing key đã ký digest; không chứng minh nội dung nghiệp vụ là đúng nếu producer ban đầu phát dữ liệu sai.

## 12. Chain of custody và bảo toàn bằng chứng

Khi audit record được dùng trong điều tra hoặc quy trình pháp lý, cần bảo đảm bằng chứng không bị thay đổi ngoài kiểm soát.

### Các bước

1. Xác định phạm vi và nguồn dữ liệu.
2. Ghi người thu thập, thời điểm và quyền được sử dụng.
3. Tạo bản export có định dạng và manifest rõ.
4. Tính hash cho file/batch export.
5. Lưu bản gốc ở nơi chỉ đọc/immutable.
6. Ghi mọi lần copy, transfer, access và analysis.
7. Giữ timezone, schema version và mapping tài liệu.
8. Ghi công cụ và phiên bản dùng để parse/verify.
9. Phân biệt bản gốc, bản đã redact và bản phân tích.
10. Ghi người nhận và lý do chia sẻ.

Không chỉnh sửa trực tiếp bản gốc để ẩn PII. Tạo bản sao đã redact, giữ reference và audit việc tạo bản sao.

### Evidence reference

Ticket hoặc incident report nên tham chiếu audit_id, time range và export manifest. Không copy token, password hoặc raw assertion vào ticket để “giữ bằng chứng”.

## 13. Timestamp, ordering và correlation

Audit timeline cần xử lý đồng hồ lệch và event đến muộn.

### Thời gian

- Dùng UTC và timestamp có timezone.
- Ghi occurred_at và recorded_at riêng.
- Đồng bộ đồng hồ của service, database và collector.
- Ghi nhận clock skew khi vượt ngưỡng.
- Không chỉ dựa timestamp để kết luận thứ tự khi hai máy lệch giờ.

### Ordering

Có thể dùng sequence number theo account, session hoặc aggregate. Nếu hệ thống không bảo đảm thứ tự toàn cục, tài liệu phải nêu rõ phạm vi ordering.

### Correlation

Dùng correlation_id/interaction_id để nối:

- Login transaction.
- MFA challenge.
- OIDC/SAML callback.
- Session creation.
- Token issuance.
- Privileged action.
- Recovery workflow.

Không dùng session cookie, access token hoặc authorization code làm correlation ID. Dùng reference đã bảo vệ hoặc identifier ngẫu nhiên không mang quyền truy cập.

## 14. Audit pipeline và ranh giới tin cậy

Audit data có thể đi qua nhiều thành phần trước khi lưu trữ.

~~~mermaid
flowchart LR
    S["Source service"] -->|"Authenticated publish"| B["Message broker"]
    B --> C["Collector / schema validation"]
    C --> N["Normalize / redact"]
    N --> A["Append-only audit store"]
    A --> H["Integrity checkpoint"]
    A --> Q["Authorized query service"]
    Q --> SIEM["SIEM / investigation"]
~~~

### Kiểm soát từng hop

- Producer xác thực bằng workload identity/mTLS.
- Broker ACL giới hạn producer theo topic và tenant.
- Collector xác minh schema, producer và payload size.
- Normalization không được thay đổi ngữ nghĩa hoặc xóa evidence quan trọng.
- Audit store tách quyền append, query, export và administration.
- Integrity verifier chạy độc lập với writer.
- SIEM nhận dữ liệu theo quyền read-only.
- Dead-letter queue được bảo vệ và có quy trình xử lý.

### Tenant isolation

Tenant context phải do nguồn tin cậy xác định và được kiểm tra tại ingestion. Không cho consumer hoặc analyst tenant A query record tenant B nếu không có quyền cross-tenant được phê duyệt.

## 15. Privacy và data minimization

Audit trail cần đủ chi tiết để điều tra nhưng không nên trở thành kho chứa credential hoặc hồ sơ cá nhân không giới hạn.

### Không ghi

- Password hoặc password hash nếu không cần thiết cho mục đích audit.
- OTP, TOTP seed, recovery code.
- Session cookie, access token, refresh token.
- Authorization code, PKCE verifier.
- Private key, client secret hoặc DB password.
- Raw request body chứa credential.
- Full assertion/token nếu chỉ cần issuer, subject reference và result.

### Dữ liệu cần cân nhắc

- Email, phone và username.
- IP address, geolocation và device fingerprint.
- Role, group và tenant membership.
- Authentication assurance và risk signal.
- Admin/operator identifier.
- Nội dung before/after của profile.

Chỉ ghi dữ liệu cần cho mục đích audit. Có thể dùng subject reference, HMAC pseudonym hoặc identifier nội bộ; hash email không key vẫn dễ bị dò dictionary.

### Redaction và access

- Redact ở nguồn trước khi ghi.
- Giới hạn field allowlist.
- Có test scan secret trong event.
- Kiểm soát quyền query/export.
- Ghi audit mọi lần truy cập audit data.
- Dùng bản export đã redact cho chia sẻ.
- Có retention và deletion policy rõ.

Pseudonymization không phải anonymization nếu tổ chức vẫn có thể liên kết reference với người dùng.

## 16. Retention, legal hold và lifecycle

Retention phụ thuộc mục đích, rủi ro, hợp đồng và nghĩa vụ pháp lý. Không có một thời hạn đúng cho mọi event.

### Phân lớp

- Hot: truy vấn nhanh và phát hiện gần thời gian thực.
- Warm: điều tra và audit định kỳ.
- Archive: lưu dài hạn, ít truy cập, có integrity protection.
- Expired: hết retention hoặc được xử lý theo yêu cầu hợp lệ.

### Policy cần quy định

- Event family nào được giữ.
- Retention duration và lý do.
- Ai có quyền đọc/export.
- Legal hold áp dụng thế nào.
- Backup/replica có cùng lifecycle hay không.
- Xóa an toàn khi hết hạn.
- Xử lý yêu cầu xóa/correction dữ liệu cá nhân.
- Cách giữ integrity khi archive hoặc migrate storage.

Legal hold phải có owner, phạm vi, thời điểm bắt đầu/kết thúc và audit trail. Không dùng legal hold như lý do giữ mọi dữ liệu vô thời hạn.

## 17. Quyền truy cập audit và audit chính audit

Audit trail có thể chứa dữ liệu nhạy cảm và bằng chứng về hoạt động nội bộ. Quyền đọc nó cần được kiểm soát.

### Tách vai trò

| Vai trò | Quyền gợi ý |
| --- | --- |
| Audit writer | Append record, không sửa/xóa record cũ. |
| SOC analyst | Query event theo phạm vi điều tra. |
| Auditor | Read-only theo scope được phê duyệt. |
| Export operator | Tạo export theo approval và purpose. |
| Retention administrator | Quản lý lifecycle, không sửa nội dung nghiệp vụ. |
| Storage administrator | Vận hành storage, không tự ý đọc nội dung nếu có thể tách. |
| Integrity verifier | Kiểm tra hash/signature độc lập. |

### Ghi nhận việc đọc audit

Các hành động sau cũng cần audit:

- Search/query audit.
- Export/download.
- Thay đổi query scope hoặc retention.
- Cấp quyền analyst/auditor.
- Thay signing key hoặc integrity configuration.
- Xóa theo retention/legal hold.
- Truy cập break-glass.

Nếu audit reader có thể đọc dữ liệu của mọi người mà không để lại dấu vết, audit system trở thành điểm mù và insider risk.

## 18. Review và detection dựa trên audit trail

Audit trail hỗ trợ cả điều tra sau sự cố và phát hiện sớm.

### Hành động cần review định kỳ

- Admin thay đổi MFA, password hoặc recovery policy.
- Thêm/bỏ trusted issuer hoặc signing key.
- Cấp quyền đặc biệt hoặc cross-tenant role.
- Helpdesk reset authenticator.
- Account merge hoặc identity link/unlink.
- Break-glass và impersonation.
- Bulk export user/session/audit data.
- Thay đổi retention hoặc audit configuration.
- Workload credential issue/revoke.
- Audit query/export ngoài baseline.

### Detection pattern

| Pattern | Audit evidence liên quan | Hành động |
| --- | --- | --- |
| MFA removed rồi login mới | Authenticator removal, login, session created. | Review account takeover risk. |
| Recovery channel changed rồi password reset | Recovery method update, reset completed. | Step-up/revoke session theo policy. |
| Privilege escalation | Role/grant change, approval, admin action. | Alert và xác minh approval. |
| Cross-tenant access | Actor, tenant, target resource, decision. | Deny và điều tra mapping. |
| Break-glass use | Emergency access start/end, commands/actions. | Review sau sự cố bắt buộc. |
| Audit export bất thường | Query/export actor, scope, volume. | Alert, suspend export nếu cần. |
| Revoked identity vẫn hoạt động | Revoke record và downstream access event. | Tìm propagation gap. |

Detection là tín hiệu cần xác minh; không nên tự động kết luận sai phạm chỉ từ một event.

## 19. Forensic timeline và incident response

Audit trail giúp dựng timeline và phạm vi ảnh hưởng khi có account takeover, insider misuse hoặc credential compromise.

### Quy trình điều tra

1. Xác định alert/incident ID, account, tenant và khoảng thời gian.
2. Thu thập audit record từ IdP, RP, session, token, admin và downstream service.
3. Xác minh producer, schema, timestamp và integrity.
4. Nối actor, subject, target, correlation và causation.
5. Dựng timeline, đánh dấu event đến muộn hoặc thiếu.
6. Xác định credential, session, token, role và resource bị ảnh hưởng.
7. Preserve evidence và ghi chain of custody.
8. Contain: revoke session/token/grant, disable identity hoặc workload theo policy.
9. Kiểm tra dữ liệu đã đọc/sửa/xuất và thay đổi policy.
10. Recover và theo dõi hành vi sau containment.
11. Ghi residual risk, quyết định và bài học.

### Không suy diễn vượt bằng chứng

Audit record cho biết hệ thống đã ghi nhận một hành động theo identity và nguồn tại thời điểm đó. Nó không tự chứng minh ai ngồi trước thiết bị hoặc ý định của họ. Ghi rõ điều gì được quan sát, điều gì suy luận và điều gì chưa xác định.

## 20. Java: mô hình audit record

Dùng type rõ và allowlist field để tránh vô tình serialize toàn bộ request hoặc credential object.

~~~java
import java.time.Instant;
import java.util.UUID;

public record AuditRecord(
        String auditId,
        int schemaVersion,
        String eventType,
        Instant occurredAt,
        Instant recordedAt,
        String actorRef,
        String subjectRef,
        String targetType,
        String targetRef,
        String action,
        String result,
        String reasonCode,
        String tenantRef,
        String correlationId,
        String policyVersion
) {
    public static AuditRecord sessionRevoked(
            String actorRef,
            String subjectRef,
            String sessionRef,
            String tenantRef,
            String correlationId
    ) {
        Instant now = Instant.now();

        return new AuditRecord(
                UUID.randomUUID().toString(),
                1,
                "authentication.session.revoked",
                now,
                now,
                actorRef,
                subjectRef,
                "session",
                sessionRef,
                "revoke",
                "success",
                "security_policy",
                tenantRef,
                correlationId,
                "session-policy-5"
        );
    }
}
~~~

Record chỉ minh họa. Production cần phân biệt occurredAt và recordedAt thực tế, validate actor/subject từ trusted context, schema versioning, redaction, producer identity và persistence bền vững. Không cho client tự truyền actorRef hoặc result.

## 21. Java/SQL: transactional outbox

Ví dụ bảng PostgreSQL cho outbox:

~~~sql
CREATE TABLE audit_outbox (
    audit_id VARCHAR(100) PRIMARY KEY,
    event_type VARCHAR(200) NOT NULL,
    schema_version INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX audit_outbox_pending_idx
    ON audit_outbox (created_at)
    WHERE published_at IS NULL;
~~~

Bảng này là hàng đợi phát hành tạm thời; audit store cuối cùng cần policy append-only và integrity riêng. Payload phải được tạo từ allowlist field, không serialize HTTP request.

~~~java
@Transactional
public void revokeAuthenticator(
        String subjectRef,
        String authenticatorRef,
        TrustedActor actor,
        String correlationId
) {
    authenticatorRepository.revoke(
            subjectRef,
            authenticatorRef
    );

    AuditRecord record = auditFactory.authenticatorRevoked(
            actor.subjectRef(),
            subjectRef,
            authenticatorRef,
            actor.tenantRef(),
            correlationId
    );

    auditOutboxRepository.insert(record);
}
~~~

Ví dụ dùng abstraction repository để minh họa. Thay đổi credential state và insert outbox phải nằm trong cùng transaction. Publisher gửi record sau commit; consumer deduplicate theo audit_id.

## 22. Failure mode và resilience

Audit system cũng có thể lỗi. Phải phân loại mức quan trọng của hành động và định nghĩa behavior khi audit store unavailable.

### Failure cases

- Database transaction commit nhưng publisher dừng.
- Broker nhận message nhưng acknowledgement bị mất.
- Audit store đầy hoặc không ghi được.
- Schema version mới chưa được consumer hỗ trợ.
- Signing key/checkpoint service unavailable.
- Collector nhận event trễ hoặc sai thứ tự.
- Storage replication lag.
- Integrity verification phát hiện gap.
- Clock synchronization lỗi.
- Audit export bị timeout giữa chừng.

### Chính sách

- Audit-critical state change nên dùng outbox hoặc durable local queue.
- Không báo action completed nếu state chưa commit.
- Retry có backoff và giới hạn; dead-letter có owner.
- Consumer idempotent theo audit_id.
- Có alert cho backlog, gap, drop và integrity failure.
- Hành động đặc quyền có thể fail closed hoặc chờ durable audit theo policy.
- Metrics/debug telemetry có thể degrade riêng, không nhất thiết làm login thất bại.
- Có backup/restore và reconciliation.

Không âm thầm bỏ audit record quan trọng để duy trì availability mà không phát hiện hoặc cảnh báo.

## 23. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Biện pháp |
| --- | --- | --- |
| Chỉ ghi “success/failure” | Không biết actor, target hoặc policy. | Schema actor/action/target/result. |
| Dùng debug log làm audit | Log có thể bị rotate, sampling hoặc sửa. | Audit store và retention riêng. |
| Ghi sau khi trả success | Record có thể mất nếu process crash. | Transactional outbox/durable write. |
| Ghi trước khi commit | Audit mô tả thay đổi chưa xảy ra. | Commit state và outbox cùng transaction. |
| Actor do client khai | Có thể giả mạo người thực hiện. | Trusted principal từ session/token/workload. |
| Lưu raw token/password | Audit leak trở thành credential compromise. | Allowlist, redaction và reference. |
| Một admin vừa ghi vừa xóa audit | Có thể che dấu hành động. | Separation of duties, WORM và external checkpoint. |
| Hash chain không external anchor | Attacker có thể tính lại chuỗi. | Signed checkpoint và anchor độc lập. |
| Không có event ID | Duplicate khó nhận diện. | ID duy nhất và idempotent consumer. |
| Chỉ dùng timestamp | Clock skew làm sai timeline. | occurred_at, recorded_at, sequence và correlation. |
| Không audit việc đọc/export | Insider có thể truy cập dữ liệu mà không dấu vết. | Audit query/export/permission change. |
| Retention vô hạn | Tăng privacy risk và chi phí. | Retention theo purpose và legal policy. |
| Before/after quá chi tiết | Lộ PII/secret trong history. | Change summary và data minimization. |
| Không kiểm tra completeness | Event gap không được phát hiện. | Sequence/gap monitoring và reconciliation. |
| Gộp actor với subject | Quy trách nhiệm sai. | Model role riêng. |
| Không version schema | Consumer hiểu sai record mới. | Schema version và contract test. |

## 24. Ví dụ thực tế: Learning Platform

Learning Platform có IdP của trường, Learning Portal, Session Service, Enrollment API, Staff Console và Audit Pipeline.

### Admin reset authenticator

1. Staff operator đăng nhập qua IdP và MFA.
2. Staff Console gửi yêu cầu reset authenticator cho học viên.
3. Identity Administration xác minh role, tenant, approval và reason.
4. Service revoke authenticator và commit trạng thái.
5. Transactional outbox ghi audit record trong cùng transaction.
6. Publisher gửi record tới Audit Pipeline.
7. Audit Store lưu append-only và cập nhật integrity checkpoint.
8. SOC có thể query theo actor, subject, tenant và correlation ID.

### Điều tra account takeover

Học viên báo có người lạ truy cập. Điều tra viên tìm thấy:

- Login failure từ nhiều nguồn.
- Login success sau một lần MFA approval.
- Passkey mới được thêm.
- Session mới được tạo.
- Recovery email thay đổi.
- Export dữ liệu sau đó.

Audit trail giúp nối các hành động theo subject, session reference và interaction. Team xác minh actor/source của passkey enrollment, revoke session và authenticator theo policy, rồi đánh giá dữ liệu đã export.

### Audit export bất thường

Một analyst tải lượng lớn audit records ngoài phạm vi incident. Hệ thống ghi audit query/export, alert theo volume và yêu cầu approval bổ sung. Quyền đọc audit cũng được kiểm toán như quyền quản trị identity.

## 25. Kiểm thử audit trail

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Login success | Đăng nhập bằng fixture hợp lệ. | Có record actor, subject, method, outcome và correlation. |
| Login failure | Dùng credential test sai. | Có record failure, không có password. |
| MFA change | Thêm/gỡ authenticator. | Actor, subject, target và result chính xác. |
| Recovery admin | Operator reset recovery method. | Operator là actor, user là subject; approval được tham chiếu. |
| Role change | Thay role/tenant membership. | Before/after summary, actor và policy version được ghi. |
| Failed transaction | Rollback thay đổi identity. | Không có audit record completed giả. |
| Outbox retry | Ngắt broker sau commit. | Outbox giữ record và publisher retry. |
| Duplicate publish | Publish cùng audit_id hai lần. | Consumer deduplicate hoặc idempotent. |
| Ordering | Gửi record đến muộn. | Timeline dùng sequence/correlation; không ghi đè state mới. |
| Actor spoofing | Gửi actorRef giả trong request body. | Audit lấy actor từ trusted principal. |
| Producer spoofing | Publish từ workload không được phép. | Broker/collector từ chối. |
| Tenant spoofing | Gửi tenant khác với trusted context. | Record không bị gắn tenant giả; request bị deny khi cần. |
| Secret scan | Quét payload, log và outbox. | Không có password, OTP, token, cookie hoặc private key. |
| PII review | Kiểm tra email/IP/device fields. | Chỉ lưu trường cần thiết, có bảo vệ. |
| Tamper test | Sửa record trong test store. | Integrity verifier phát hiện mismatch. |
| Deletion attempt | Writer role thử UPDATE/DELETE. | DB/storage từ chối. |
| Admin separation | Storage admin thử sửa audit content. | Không có quyền hoặc hành động được phát hiện qua independent control. |
| Checkpoint verification | Sửa batch sau khi ký checkpoint. | Signature/hash verification thất bại. |
| Missing record | Bỏ một sequence trong test stream. | Gap monitoring cảnh báo. |
| Export audit | Analyst export theo scope được cấp. | Export được audit, manifest/hash được tạo. |
| Unauthorized query | Tenant analyst query tenant khác. | Access bị từ chối và có audit event. |
| Retention expiry | Chạy policy trên fixture hết hạn. | Dữ liệu được xử lý theo policy; legal hold được tôn trọng. |
| Legal hold | Đặt hold trên fixture. | Record không bị xóa trong thời gian hold. |
| Clock skew | Mô phỏng lệch đồng hồ. | occurred_at/recorded_at phân biệt và skew được cảnh báo. |
| Storage outage | Làm audit store unavailable. | Outbox/durable queue giữ record; hành động nhạy cảm theo fail policy. |
| Incident timeline | Tạo chuỗi login, MFA, session và recovery test. | Có thể dựng timeline qua correlation và evidence references. |
| Audit-of-audit | Query/export/change retention. | Hành động truy cập audit cũng được ghi nhận. |

## 26. Checklist triển khai

- [ ] Đã xác định hành động identity/authentication cần audit.
- [ ] Audit record có schema version, ID, actor, subject, action, target và result.
- [ ] Actor, subject, approver, producer và source được phân biệt.
- [ ] Actor/tenant được lấy từ trusted context, không từ payload tự khai.
- [ ] Record được phát ra từ service có thẩm quyền sau khi biết kết quả.
- [ ] State change và audit outbox nhất quán transaction.
- [ ] Delivery retry, duplicate, late event và dead-letter được xử lý.
- [ ] Audit store append-only; correction tạo record mới.
- [ ] Hash/signature/checkpoint được bảo vệ bằng quyền và key độc lập.
- [ ] Có kiểm tra gap/completeness và integrity định kỳ.
- [ ] Chain of custody được ghi khi export bằng chứng.
- [ ] Không ghi password, OTP, token, cookie, recovery code hoặc private key.
- [ ] PII được tối thiểu hóa, pseudonymize và có retention.
- [ ] Query/export/delete/retention change đều được audit.
- [ ] Quyền writer, analyst, auditor, export và storage admin được tách.
- [ ] Tenant isolation áp dụng ở ingestion, query và export.
- [ ] Timestamp UTC, occurred_at/recorded_at và correlation được chuẩn hóa.
- [ ] Có alert cho privilege change, recovery, break-glass và audit tampering.
- [ ] Có runbook cho account takeover, insider misuse và credential compromise.
- [ ] Có test transaction rollback, duplicate, out-of-order, tamper, outage và legal hold.
- [ ] Có backup, restore, retention review và owner cho audit system.

## 27. Tự kiểm tra

**Câu 1.** Audit trail khác application log như thế nào?

**Đáp án:** Audit trail là bằng chứng có cấu trúc về actor, action, target và result, có provenance, integrity và retention rõ. Application log chủ yếu phục vụ debug/vận hành và không mặc nhiên đáp ứng các yêu cầu đó.

**Câu 2.** Vì sao phải phân biệt actor và subject?

**Đáp án:** Actor thực hiện hành động; subject là account bị tác động hoặc được đại diện. Nhầm hai vai trò làm sai lệch trách nhiệm và timeline.

**Câu 3.** Khi admin gửi yêu cầu suspend account, có nên ghi ngay audit success không?

**Đáp án:** Không. Cần phân biệt requested, approved và completed; chỉ ghi completed sau khi trạng thái thực sự được commit.

**Câu 4.** Transactional outbox giải quyết vấn đề gì?

**Đáp án:** Nó ghi state change và audit event trong cùng transaction, sau đó publisher retry phát event, giảm nguy cơ thay đổi đã commit nhưng audit record bị mất.

**Câu 5.** Vì sao audit writer không nên có quyền sửa/xóa record cũ?

**Đáp án:** Nếu writer có thể sửa lịch sử, lỗi hoặc insider có thể che dấu hành động. Append-only và separation of duties tăng khả năng phát hiện.

**Câu 6.** Hash chain có bảo đảm audit trail đầy đủ không?

**Đáp án:** Không. Hash chain giúp phát hiện sửa đổi trong chuỗi đã có; cần sequence/gap monitoring, external anchor và independent backup để phát hiện thiếu record hoặc việc tính lại chuỗi.

**Câu 7.** Chữ ký checkpoint chứng minh điều gì?

**Đáp án:** Nó chứng minh digest được ký bằng key tương ứng. Nó không tự chứng minh actor con người có ý định hoặc dữ liệu nguồn là đúng.

**Câu 8.** Vì sao phải audit việc đọc và export audit data?

**Đáp án:** Audit trail chứa dữ liệu nhạy cảm; query/export trái phép có thể là insider misuse hoặc data exfiltration và cần được truy vết.

**Câu 9.** Có nên lưu raw access token để tiện điều tra không?

**Đáp án:** Không. Token là bearer credential. Lưu token có thể tạo đường truy cập mới cho người đọc log; dùng reference đã bảo vệ và metadata tối thiểu.

**Câu 10.** Audit record có thể chứng minh ai thực sự ngồi trước thiết bị không?

**Đáp án:** Không tự nó. Record liên kết hành động với principal và nguồn đã xác thực; malware, shared device hoặc session theft vẫn có thể khiến người điều khiển thực tế khác chủ tài khoản.

## Ghi nhớ

**Audit trail** là bằng chứng có cấu trúc về ai đã làm gì, trên đối tượng nào, khi nào, từ nguồn nào và với kết quả ra sao. Một record đáng tin cần actor/subject/approver rõ, provenance từ service có thẩm quyền, timestamp/correlation ổn định và được ghi nhất quán với thay đổi nghiệp vụ.

Append-only storage, separation of duties, hash chain, signed checkpoint và chain of custody giúp phát hiện hoặc kiểm soát việc sửa/xóa bằng chứng; chúng cần được kết hợp với external anchor, backup và kiểm tra completeness. Bảo vệ privacy bằng data minimization, redaction, retention và kiểm toán cả hoạt động query/export. **Audit trail chỉ hữu ích khi record phản ánh đúng hành động, có thể kiểm chứng nguồn gốc, truy vết được và không trở thành nơi lưu credential.**
