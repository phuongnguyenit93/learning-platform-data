# Test audit event

Kiểm thử audit event xác minh rằng hệ thống quản lý khóa ghi nhận đúng những gì đã xảy ra, đúng actor, đúng resource, đúng operation, đúng kết quả và đủ bằng chứng để điều tra sau này. Một API Encrypt trả về thành công chưa chứng minh audit hoạt động. Test phải kiểm tra event được tạo, chuyển qua pipeline, giữ đúng ngữ nghĩa, không lộ key material và có thể truy xuất theo request hoặc correlation ID.

Trong key management, audit event là một phần của security control. Các thao tác create/import/rotate/disable/destroy, encrypt/decrypt/wrap/unwrap/sign, thay key policy, cấp grant, restore backup và truy cập secret đều cần được ghi nhận theo yêu cầu tương ứng. Event thiếu actor hoặc key version có thể khiến incident responder không xác định được ai đã dùng khóa nào. Event ghi success trước khi provider hoàn tất có thể tạo bằng chứng sai. Event chứa plaintext, private key hoặc token lại biến log thành một kênh rò rỉ.

Bài học trình bày cách thiết kế kiểm thử cho audit event từ schema contract đến end-to-end pipeline: xác định coverage, kiểm tra event semantics, success/denied/failure, correlation, timestamp, retry/deduplication, gap detection, integrity, provenance, redaction, access control, retention và khả năng điều tra.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích audit event và vai trò của nó trong key management.
- Phân biệt audit event với application log, metric, trace, alert và incident.
- Xây dựng event coverage matrix cho từng operation và lifecycle transition.
- Kiểm tra schema, field bắt buộc, kiểu dữ liệu, version và tương thích.
- Xác minh actor, action, resource, key version, tenant, outcome và reason.
- Kiểm tra sự khác nhau giữa attempted, accepted, completed, denied và failed event.
- Kiểm thử event cho KMS/HSM, IAM, secret manager, PKI và ứng dụng.
- Xác minh request ID, trace ID, correlation ID và provider operation ID.
- Kiểm tra timestamp, clock skew, event ordering, late arrival và duplicate.
- Phát hiện event bị mất, sai thứ tự, sửa đổi hoặc giả mạo.
- Xác minh redaction và ngăn log lộ key material, secret, token hoặc plaintext.
- Kiểm tra access control, retention, export và evidence integrity.
- Viết unit, contract, integration và end-to-end test.
- Thiết kế fixture và test data an toàn, có thể lặp lại.
- Đánh giá test coverage và xử lý lỗi audit pipeline.

Phạm vi là kiểm thử audit event trong hệ thống quản lý khóa mật mã. Tên field và semantics thực tế phải theo provider, schema nội bộ và chính sách audit của hệ thống đang triển khai.

## 2. Audit event là gì?

Audit event là bản ghi có cấu trúc mô tả một hành động, quyết định hoặc thay đổi trạng thái có ý nghĩa bảo mật. Event cần đủ thông tin để trả lời ai đã làm gì, với tài nguyên nào, khi nào, từ đâu, kết quả ra sao và operation thuộc request nào.

Ví dụ:

- Workload payments-api gọi Decrypt trên key version 7.
- Operator thay đổi key policy.
- IAM cấp quyền Unwrap cho service account.
- KMS từ chối request do key đã bị disable.
- HSM ghi nhận operator login hoặc tamper alarm.
- Secret manager cấp lease mới hoặc revoke lease.
- Workflow schedule deletion và provider trả trạng thái pending deletion.

Audit event nên được tạo từ thành phần đáng tin cậy quan sát operation. Không lấy nội dung do client tự khai báo làm bằng chứng actor hoặc outcome nếu chưa xác thực bằng identity/provider context.

## 3. Phân biệt audit event với log, metric, trace và alert

| Loại dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Audit event | Bằng chứng về hành động hoặc quyết định | Principal A gọi Decrypt trên key K |
| Application log | Chẩn đoán luồng xử lý | Request validation failed |
| Metric | Đo lường số lượng/trạng thái theo thời gian | decrypt_requests_total |
| Trace | Theo dõi một request qua nhiều service | Trace từ API tới KMS adapter |
| Alert | Thông báo tín hiệu cần điều tra | Decrypt spike vượt baseline |
| Incident | Hồ sơ điều phối ứng phó | Credential workload bị nghi lộ |

Một trace có thể chứa span metadata nhưng không thay thế audit record có retention và integrity phù hợp. Metric có thể cho biết số lần Decrypt nhưng không định danh từng key version. Alert là kết quả phân tích, không phải event nguồn.

Test audit event phải kiểm tra đúng loại dữ liệu và nơi lưu trữ được yêu cầu. Không coi việc application log có dòng “decrypt succeeded” là bằng chứng KMS audit event đã được ghi.

## 4. Nguồn audit cần kiểm thử

| Nguồn | Event cần xác minh |
|---|---|
| KMS | Create, import, encrypt, decrypt, wrap, unwrap, sign, verify, disable, rotate, schedule deletion, destroy |
| HSM | Login, logout, role change, partition change, key generation, backup/restore, tamper |
| IAM/Identity | Authentication, MFA, role assignment, grant, policy change, session revoke |
| Secret manager | Read, version create, rotate, lease issue, renew, revoke, access denied |
| PKI/CA | Certificate issue, renew, revoke, CRL/OCSP update, CA policy change |
| Key service/application | Business authorization, key reference, request result, tenant context |
| Backup/recovery | Backup create, restore start/completion, integrity failure |
| CI/CD | Workload identity, secret injection, pipeline permission change, deployment |
| Audit pipeline | Collect, parse, normalize, enrich, store, export, retention/delete |

Mỗi source cần owner, cách bật audit, retention, delivery mode, failure behavior và phương pháp test. Provider có thể không phát event cho một số operation hoặc chỉ cung cấp event qua control-plane audit service. Phải xác định semantics thực tế trước khi viết assertion.

## 5. Event coverage matrix

Trước khi test, lập danh sách operation và event kỳ vọng. Đây là cách phát hiện khoảng trống mà một vài test happy path không thể bao phủ.

| Operation | Event kỳ vọng | Các field quan trọng |
|---|---|---|
| Create key | key.created | actor, key ID, algorithm, purpose |
| Import key | key.imported | actor, source/reference, key ID, custody context |
| Encrypt | key.encrypt | principal, key ID/version, request ID, outcome |
| Decrypt | key.decrypt | principal, key ID/version, tenant, outcome |
| Wrap/unwrap | key.wrap / key.unwrap | KEK ID/version, wrapped-key reference, outcome |
| Rotate | key.rotated | old/new version, reason, workflow ID |
| Policy update | key.policy.changed | actor, policy revision, before/after reference |
| Grant create/revoke | key.grant.created / revoked | grantee, action, resource scope |
| Disable | key.disabled | actor, key ID/version, reason |
| Schedule deletion | key.destroy.scheduled | approval reference, deletion date |
| Destroy | key.destroyed | provider operation ID, final state |
| Access denied | key.operation.denied | actor, action, resource, reason |
| Backup restore | key.restore.started/completed | backup ID, key ID/version, result |

Tên event trong bảng là taxonomy minh họa. Nếu provider phát tên khác, mapper phải giữ original event name và chuyển sang canonical event type có version.

Coverage matrix nên có thêm cột test ID, source, expected outcome, required fields, privacy rule, retention class và owner. Mỗi security-relevant operation phải có ít nhất một test success và một test denial/failure phù hợp.

## 6. Event schema và field bắt buộc

Một schema audit thường cần các nhóm field sau:

| Nhóm | Field ví dụ | Lý do |
|---|---|---|
| Identity | event_id, source_event_id | Định danh và deduplicate |
| Type | event_type, schema_version | Diễn giải event |
| Time | event_time, observed_time, ingested_time | Timeline và độ trễ |
| Actor | actor_id, actor_type, auth_context | Ai thực hiện |
| Action | action, operation_category | Điều gì đã xảy ra |
| Resource | key_id, key_version, tenant_id | Key nào bị tác động |
| Context | environment, workload_id, source_ip | Bối cảnh operation |
| Correlation | request_id, trace_id, correlation_id | Nối workflow |
| Result | outcome, reason_code, provider_status | Kết quả thực tế |
| Provenance | source_system, collector_id, integrity_ref | Nguồn và tính toàn vẹn |

Không bắt buộc mọi nguồn có đủ mọi field. Schema phải phân biệt field required, optional, nullable và unavailable. Nếu một field không có từ source, ghi rõ absent/unknown theo schema; không tự điền giá trị giả để làm test pass.

### Ví dụ event metadata

~~~~json
{
  "eventId": "evt-8c21",
  "schemaVersion": "1.2",
  "eventType": "key.decrypt",
  "eventTime": "2026-11-28T04:15:22.418Z",
  "observedTime": "2026-11-28T04:15:22.611Z",
  "sourceSystem": "kms-prod",
  "sourceEventId": "provider-784120",
  "actor": {
    "id": "workload:payments-api",
    "type": "workload"
  },
  "resource": {
    "keyId": "key-payments-tenant-42",
    "keyVersion": "v7",
    "tenantId": "tenant-42"
  },
  "action": "Decrypt",
  "requestId": "req-7b3a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "correlationId": "payment-job-2026-11-28-01",
  "outcome": "success",
  "reasonCode": null
}
~~~~

Event mẫu chỉ chứa metadata. Không thêm key bytes, plaintext, password, bearer token, secret value hoặc raw Authorization header.

## 7. Kiểm thử semantics của event

Một event phải mô tả đúng giai đoạn của operation. Các trạng thái thường gặp:

- attempted: request đã được gửi hoặc nhận để xử lý.
- accepted: provider chấp nhận request, nhưng operation có thể chưa hoàn tất.
- completed: operation đã hoàn tất và có kết quả xác nhận.
- denied: policy hoặc authorization từ chối operation.
- failed: operation được xử lý nhưng thất bại.
- unknown: chưa xác định được kết quả, thường do timeout hoặc mất kết nối.

Không được phát event completed/success trước khi có bằng chứng operation hoàn tất. Với asynchronous deletion, event schedule accepted không có nghĩa key đã bị destroyed. Với provider timeout, kết quả có thể unknown và cần reconciliation.

Test phải xác minh cả event type lẫn outcome. Chỉ kiểm tra event tồn tại là chưa đủ.

## 8. Phân biệt actor, requester và executor

Trong workflow tự động, người tạo yêu cầu có thể khác workload thực thi:

- requester: người hoặc service khởi tạo request.
- approver: người xác nhận request.
- executor: service identity gọi KMS/HSM.
- effective principal: identity mà provider ghi nhận đã gọi API.
- resource owner: người/team chịu trách nhiệm key.

Schema cần phân biệt các vai trò khi có liên quan. Không ghi requester thành actor của provider event nếu thực tế executor service gọi KMS. Test nên xác minh actor_id trong KMS event khớp provider principal, còn requester/approver được liên kết qua workflow audit event.

## 9. Kiểm thử schema contract

Contract test xác minh producer và consumer hiểu cùng một schema.

Các assertion:

- Schema version hợp lệ.
- Event type nằm trong taxonomy đã công bố.
- Field required không null hoặc rỗng.
- Timestamp parse được theo format quy định.
- Outcome nằm trong enum hợp lệ.
- Key ID/version không bị thay bằng alias mơ hồ.
- Field numeric/string/boolean có đúng kiểu.
- Event payload tuân theo size limit.
- Unknown field được xử lý theo compatibility policy.
- Event cũ vẫn được consumer hỗ trợ trong thời gian migration.
- Breaking change phải tăng schema version và có migration plan.

Contract test cần chạy trên payload do producer thật tạo ra và trên fixture đại diện các version đang hỗ trợ. Một JSON mẫu viết tay có thể bỏ sót lỗi serializer thực tế.

## 10. Unit test cho audit publisher

Unit test tập trung vào việc component tạo event đúng khi operation thành công hoặc thất bại.

Nên kiểm tra:

- Event type và action chính xác.
- Actor được lấy từ authenticated security context.
- Resource là key ID/version đã resolve.
- Tenant và environment đúng.
- Request/correlation ID được propagate.
- Outcome phản ánh kết quả thực tế.
- Reason code có mặt với denied/failed event.
- Không có secret hoặc plaintext trong field.
- Một operation không tạo event success trùng lặp.
- Exception trong audit publisher được xử lý theo policy.

Không mock toàn bộ logic rồi chỉ assert rằng hàm publish được gọi. Hãy xác minh nội dung event và điểm gọi tương ứng với trạng thái operation.

## 11. Test success path

Với một Encrypt hoặc Decrypt thành công, test nên thực hiện operation qua service hoặc provider test double rồi truy vấn audit sink.

Ví dụ các điều kiện:

1. Principal hợp lệ gọi operation.
2. Provider trả success.
3. Event xuất hiện trong thời hạn delivery SLA.
4. Event có đúng actor, action, key ID/version và tenant.
5. Outcome là success/completed theo semantics.
6. Provider operation ID hoặc request ID được lưu.
7. Không có field chứa key material hoặc plaintext.
8. Event có thể truy xuất bằng event ID và correlation ID.

Test phải chứng minh event phản ánh operation thực tế. Nếu provider trả lỗi sau khi application đã ghi success, test phải fail.

## 12. Test denied và authorization failure

Denied event quan trọng vì chuỗi từ chối liên tiếp có thể cho thấy brute force, privilege probing hoặc cấu hình sai.

Test các trường hợp:

- Principal không có quyền Decrypt.
- Principal thuộc tenant khác.
- Key disabled hoặc revoked.
- Key purpose không phù hợp.
- Approval chưa đủ quorum.
- Request dùng key version không hợp lệ.
- Policy condition không thỏa mãn.
- HSM partition không cho phép operator.
- Credential hết hạn hoặc session bị revoke.

Event cần ghi outcome denied và reason code đủ cụ thể để phân tích. Không ghi credential, token hoặc nội dung secret gây ra denial. Không phát event success khi provider từ chối operation.

## 13. Test provider failure và kết quả không xác định

Provider failure khác authorization denial. Các tình huống:

- KMS trả service unavailable.
- HSM mất kết nối.
- Request timeout trước khi biết provider đã nhận hay chưa.
- Provider trả throttling.
- Operation asynchronous chưa hoàn tất.
- Response parse lỗi.
- Network connection bị reset sau khi provider thực thi.

Test cần xác minh event có outcome failure hoặc unknown phù hợp. Với timeout, không tự kết luận operation thất bại. Nếu provider trả operation ID, event phải giữ ID đó để reconcile.

Không phát hai event completed chỉ vì client retry. Có thể có event attempted cho mỗi lần thử, nhưng operation-level completion cần gắn cùng operation identity và provider state.

## 14. Kiểm thử event cho key lifecycle

Key lifecycle có nhiều bước và mỗi bước phải được ghi nhận theo semantics.

~~~~mermaid
flowchart TD
    A[Create key]
    B[Activate]
    C[Use key]
    D[Rotate]
    E[Retire old version]
    F[Schedule deletion]
    G[Destroy confirmed]
    A --> B --> C --> D --> E --> F --> G
~~~~

Test theo từng transition:

- Create: key ID, algorithm, purpose và owner.
- Activate: state transition và actor.
- Rotate: old/new version và workflow reference.
- Retire: không còn new-write operation theo policy.
- Schedule deletion: deletion date và approval reference.
- Cancel deletion: actor, reason và provider state.
- Destroy: chỉ ghi completed khi provider xác nhận final state.

Nếu state transition bị từ chối, event phải phản ánh denied/failed và trạng thái key không được ghi như đã chuyển.

## 15. Correlation và propagation test

Audit event từ nhiều service cần được nối bằng identifier ổn định.

Các ID thường gặp:

| ID | Phạm vi |
|---|---|
| event_id | Một event |
| source_event_id | Một event tại source |
| request_id | Một request boundary |
| trace_id | Một distributed trace |
| correlation_id | Một workflow dài |
| provider_operation_id | Một operation tại KMS/HSM |
| incident_id | Một incident được liên kết sau này |

Test propagation qua API gateway, application, key service, KMS adapter và event collector. Xác minh ID không bị thay đổi hoặc mất ở async queue, retry và batch worker.

Không mặc định các event cùng correlation ID là cùng một hành động. Cần kiểm tra actor, resource và operation. Một workflow rotation có thể chứa hàng nghìn event; correlation chỉ là một thuộc tính nối nhóm.

## 16. Timestamp, ordering và clock skew

Một pipeline có thể nhận event trễ hoặc sai thứ tự. Test cần phân biệt:

- event_time: source ghi nhận hành động xảy ra.
- observed_time: collector nhận event.
- ingested_time: storage ghi event.
- processed_time: detection engine xử lý event.

Kiểm thử:

- Timestamp UTC parse đúng.
- Timezone gốc được giữ nếu source cung cấp.
- Event đến trễ vẫn được lưu.
- Event ordering dựa vào event_time/sequence phù hợp, không chỉ ingest_time.
- Clock skew vượt ngưỡng được gắn quality flag.
- Timestamp bất thường không làm event bị drop âm thầm.
- Sequence gap được phát hiện.
- Không suy diễn causal order chỉ từ timestamp gần nhau.

Test nên dùng clock có thể điều khiển hoặc fixture timestamp cố định, tránh sleep và phụ thuộc đồng hồ máy chạy test.

## 17. Duplicate, retry và idempotency

Nhiều pipeline dùng at-least-once delivery nên event có thể đến nhiều lần. Consumer phải xử lý duplicate an toàn.

Test:

- Gửi lại cùng source_event_id.
- Gửi event giống nội dung nhưng khác event ID.
- Retry sau collector timeout.
- Provider response bị mất sau khi operation hoàn tất.
- Consumer restart giữa lúc xử lý.
- Batch được gửi lại sau dead-letter replay.

Deduplication thường dựa vào source system + source event ID hoặc một khóa idempotency được định nghĩa. Không deduplicate chỉ theo timestamp và payload vì hai operation hợp lệ có thể giống nhau.

Kết quả mong đợi: raw delivery có thể xuất hiện nhiều lần theo delivery semantics, nhưng normalized event/incident/action không bị nhân đôi ngoài policy.

## 18. Completeness và phát hiện audit gap

Test completeness cần biết có bao nhiêu operation xảy ra và bao nhiêu event được thu thập.

Các cách đối soát:

- Provider operation count với số event nhận được.
- Sequence number hoặc checkpoint.
- Collector offset và queue lag.
- Event ID range.
- Batch manifest và checksum.
- Synthetic canary operation định kỳ.
- Reconciliation API của provider khi có hỗ trợ.

Test tạo một operation có chủ đích rồi xác minh event đến end-to-end. Test thêm collector outage hoặc queue saturation để bảo đảm gap được phát hiện và cảnh báo.

Không thể chứng minh không mất log chỉ bằng việc truy vấn một vài event có mặt. Cần kiểm tra completeness theo nguồn, time window và operation scope.

## 19. Integrity và provenance test

Audit event có thể bị sửa, xóa hoặc giả mạo trước khi tới storage. Test integrity cần bao gồm:

- Hash/digest được tạo ở ingestion boundary.
- Digest được xác minh khi đọc lại.
- Signature/manifest có thể xác minh bằng trust anchor độc lập.
- Source system và collector identity được ghi nhận.
- Sequence/checkpoint phát hiện thiếu hoặc đổi thứ tự bất thường.
- Event bị sửa sau ingest phải fail verification.
- Unauthorized delete/update bị từ chối.
- Export evidence giữ nguyên digest và provenance.
- Key dùng ký audit không nằm cùng blast radius với hệ thống đang được audit.

Hash chỉ chứng minh dữ liệu khớp digest đã lưu; không tự chứng minh nguồn event đáng tin. Chữ ký cũng không chứng minh semantics của event là đúng nếu producer bị compromise. Test phải xác minh cả source trust và integrity chain.

## 20. Privacy và redaction test

Audit cần đủ dữ liệu điều tra nhưng không lưu bí mật.

Không được ghi:

- Raw DEK, KEK, private key hoặc HSM PIN.
- Password, API key, client secret, bearer token.
- Plaintext trước hoặc sau Decrypt.
- Full Authorization header hoặc cookie.
- Secret manager response body.
- Recovery share hoặc escrow package.
- Wrapped key blob nếu policy không cho phép.

Có thể ghi key ID/version, secret ID/version, operation, actor, outcome, provider operation ID và reference tới evidence an toàn.

Redaction test nên dùng sentinel giả, ví dụ chuỗi TEST_SECRET_DO_NOT_STORE, rồi quét toàn bộ raw event, normalized event, dead-letter queue, error log và test report. Không chỉ kiểm tra UI đã mask; raw storage cũng phải không chứa giá trị nhạy cảm.

## 21. Access control và retention test

Kiểm tra ai có thể đọc, export, sửa hoặc xóa audit event.

Test:

- Analyst chỉ đọc event theo scope được cấp.
- Application runtime không được xóa audit.
- Operator key không được sửa evidence của chính mình.
- Export cần authorization và tạo access audit.
- Retention policy áp dụng đúng loại event.
- Legal hold chặn deletion khi cần.
- Expired event được xử lý theo retention policy.
- Backup/restore của audit store giữ integrity.
- Search API không cho truy vấn cross-tenant trái phép.
- Redaction hoặc privacy deletion không phá integrity của evidence còn phải giữ.

Test retention bằng clock/test environment hoặc lifecycle policy simulator. Không xóa dữ liệu production thật để chứng minh retention.

## 22. Kiểm thử audit pipeline end-to-end

Một pipeline tham khảo:

~~~~mermaid
flowchart LR
    K[KMS/HSM operation]
    P[Provider audit source]
    C[Collector]
    N[Normalize and validate]
    Q[Durable queue]
    S[Audit storage]
    I[SIEM/search]
    K --> P --> C --> N --> Q --> S --> I
~~~~

End-to-end test cần xác minh:

1. Thực hiện một operation trong test account/project.
2. Provider phát audit event.
3. Collector nhận đúng source event.
4. Parser giữ raw event và tạo normalized event.
5. Schema validation thành công.
6. Queue delivery không làm mất hoặc nhân đôi event sai semantics.
7. Storage lưu event với retention/access policy.
8. Search API truy vấn được theo event ID, key ID và request ID.
9. SIEM nhận event hoặc detection signal theo SLA.
10. Export evidence vẫn giữ provenance và integrity.

Nếu provider audit có độ trễ không cố định, dùng bounded polling với deadline rõ ràng thay vì sleep cố định. Test phải báo timeout có chẩn đoán source, collector lag và queue state.

## 23. Test failure của audit pipeline

Audit sink có thể ngừng hoạt động trong khi key operation vẫn tiếp tục. Policy phải xác định behavior theo loại operation.

| Operation | Failure policy có thể áp dụng |
|---|---|
| Encrypt/decrypt runtime | Durable local buffer, cảnh báo và xử lý theo risk/availability policy |
| Change key policy | Tạm dừng nếu audit bắt buộc không ghi được |
| Export key material | Fail closed hoặc cấm export theo policy |
| Schedule deletion/destroy | Tạm dừng nếu không thể ghi audit bắt buộc |
| HSM ceremony | Dùng audit path thay thế đã phê duyệt và đối soát sau |
| Read-only metadata | Có thể queue event nếu không làm giảm kiểm soát |

Test phải chứng minh behavior thực tế đúng với policy đã chọn. Không giả định mọi operation đều fail closed hoặc fail open. Nếu dùng buffer, kiểm tra durability, capacity, encryption, access control và replay sau recovery.

## 24. Java 17: mô hình audit event

Ví dụ record dưới đây giữ metadata của một operation. Nó không có field chứa key bytes, plaintext hay secret value.

~~~~java
import java.time.Instant;
import java.util.Objects;

public record KeyAuditEvent(
        String eventId,
        String schemaVersion,
        String eventType,
        Instant eventTime,
        Instant observedTime,
        String sourceSystem,
        String sourceEventId,
        String actorId,
        String actorType,
        String action,
        String keyId,
        String keyVersion,
        String tenantId,
        String requestId,
        String correlationId,
        String outcome,
        String reasonCode
) {
    public KeyAuditEvent {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(schemaVersion);
        Objects.requireNonNull(eventType);
        Objects.requireNonNull(eventTime);
        Objects.requireNonNull(observedTime);
        Objects.requireNonNull(sourceSystem);
        Objects.requireNonNull(sourceEventId);
        Objects.requireNonNull(actorId);
        Objects.requireNonNull(actorType);
        Objects.requireNonNull(action);
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(keyVersion);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(outcome);

        if (eventId.isBlank() || sourceEventId.isBlank()
                || keyId.isBlank() || actorId.isBlank()) {
            throw new IllegalArgumentException(
                    "Required audit identifiers are missing"
            );
        }
    }
}
~~~~

Trong production, event time và observed time có thể đảo thứ tự do clock skew hoặc collector/source clock. Không nên ném exception chỉ vì observedTime sớm hơn eventTime; hãy giữ event và gắn timestamp quality flag. Đoạn record trên chỉ minh họa field validation cơ bản; phần timestamp anomaly cần được xử lý trong normalizer.

## 25. Java 17: test publisher với JUnit 5

Ví dụ sau kiểm tra event được phát ra sau operation thành công và không ghi secret. AuditSink là test double để kiểm tra nội dung event.

~~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

final class KeyAuditPublisherTest {
    record AuditEvent(
            String actorId,
            String action,
            String keyId,
            String keyVersion,
            String outcome,
            String requestId,
            String payload
    ) {}

    interface AuditSink {
        void publish(AuditEvent event);
    }

    static final class InMemoryAuditSink implements AuditSink {
        private final List<AuditEvent> events = new ArrayList<>();

        @Override
        public void publish(AuditEvent event) {
            events.add(event);
        }

        List<AuditEvent> events() {
            return List.copyOf(events);
        }
    }

    static final class KeyService {
        private final AuditSink sink;

        KeyService(AuditSink sink) {
            this.sink = sink;
        }

        String decrypt(
                String actorId,
                String keyId,
                String keyVersion,
                String requestId
        ) {
            String plaintext = "test-data";
            sink.publish(new AuditEvent(
                    actorId,
                    "Decrypt",
                    keyId,
                    keyVersion,
                    "success",
                    requestId,
                    null
            ));
            return plaintext;
        }
    }

    @Test
    void publishesMetadataAfterSuccessfulDecrypt() {
        InMemoryAuditSink sink = new InMemoryAuditSink();
        KeyService service = new KeyService(sink);

        String plaintext = service.decrypt(
                "workload:payments",
                "key-tenant-42",
                "v7",
                "req-123"
        );

        assertEquals("test-data", plaintext);
        assertEquals(1, sink.events().size());

        AuditEvent event = sink.events().get(0);
        assertEquals("workload:payments", event.actorId());
        assertEquals("Decrypt", event.action());
        assertEquals("key-tenant-42", event.keyId());
        assertEquals("v7", event.keyVersion());
        assertEquals("success", event.outcome());
        assertEquals("req-123", event.requestId());
        assertNotNull(event.keyId());
        assertFalse(String.valueOf(event.payload()).contains("test-data"));
    }
}
~~~~

Ví dụ dùng API List.get(0), tương thích Java 17. Test double ở đây chỉ minh họa contract; service production phải phát event theo provider result thật, xử lý denied/failure và không để audit exception làm sai trạng thái operation.

## 26. Test denied path và bảo đảm không ghi secret

Test bổ sung nên kiểm tra cả denial và redaction:

~~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void redactsCredentialMaterialBeforePublishingDeniedEvent() {
    InMemoryAuditSink sink = new InMemoryAuditSink();
    String fakeToken = "TEST_SECRET_DO_NOT_STORE";
    String rawPayload = "reason=POLICY_DENIED; credential=" + fakeToken;
    String safePayload = AuditRedactor.redact(rawPayload);

    AuditEvent event = new AuditEvent(
            "user:operator-7",
            "Decrypt",
            "key-prod-42",
            "v3",
            "denied",
            "req-denied-9",
            safePayload
    );
    sink.publish(event);

    String storedPayload = sink.events().get(0).payload();

    assertEquals("denied", sink.events().get(0).outcome());
    assertFalse(storedPayload.contains(fakeToken));
    assertTrue(storedPayload.contains("[REDACTED]"));
}
~~~~

AuditRedactor là thành phần redaction của ứng dụng cần được kiểm thử riêng; test phải gọi đúng implementation production thay vì tự viết hàm thay thế trong test. Dùng sentinel giả, không dùng credential thật. Với pipeline thực tế, quét raw event, normalized event, retry queue, dead-letter queue, application error log và exported test report. Redaction chỉ ở giao diện search không đủ.

## 27. Test event contract với schema version

Khi schema thay đổi, consumer có thể parse sai hoặc bỏ field quan trọng. Test nên có:

- Fixture cho mọi schema version đang hỗ trợ.
- Required field validation.
- Enum validation.
- Backward compatibility test.
- Unknown field handling.
- Migration test giữa schema version.
- Payload size limit.
- Invalid timestamp/type test.
- Producer serialization test.
- Consumer parser test.

Không tự động drop event không parse được. Giữ raw event trong quarantine/dead-letter storage có access control, alert parser failure và cho phép replay sau khi sửa parser.

## 28. Test data và môi trường an toàn

Audit test có thể tạo ra log lâu dài. Cần dùng test account/project, key giả và data tổng hợp.

Nguyên tắc:

- Không dùng production key hoặc production secret.
- Dùng key test được tạo mới và có lifecycle cleanup.
- Không đưa secret thật vào fixture hoặc test assertion.
- Dùng tenant giả và workload identity test.
- Không ghi plaintext nhạy cảm trong test log.
- Không test destroy trên key dùng dữ liệu thật.
- Test destructive lifecycle trong sandbox hoặc provider simulator.
- Kiểm tra log/test report cũng không lộ material.
- Dọn test resource theo TTL và policy.
- Gắn marker test để phân biệt event thử nghiệm với production event.

Nếu cần xác minh provider audit thật, dùng isolated account/project và giới hạn scope. Không làm giảm logging hoặc retention của production để test nhanh.

## 29. Kiểm thử access control của audit store

Audit store thường chứa metadata nhạy cảm như tenant ID, actor, key usage và incident context. Test access control cần bao phủ:

- Runtime workload không có quyền sửa/xóa audit event.
- Key operator chỉ đọc event theo role/scope được cấp.
- Auditor có thể truy xuất evidence nhưng không thay đổi nội dung.
- Cross-tenant search bị từ chối.
- Export cần authorization và tạo access event.
- Retention admin không thể âm thầm xóa event đang legal hold.
- Break-glass access có TTL và được audit.
- Search result không trả secret đã bị redaction.
- Backup/restore không làm mất integrity metadata.

Test bằng identity có quyền khác nhau, không chỉ mock một boolean isAdmin.

## 30. Kiểm thử retention và archive

Retention policy cần được xác minh theo loại event và yêu cầu tổ chức.

Test:

- Event được lưu đủ thời gian theo retention class.
- Event hết hạn được xử lý đúng policy.
- Legal hold ngăn xóa event trong phạm vi.
- Archive có manifest/hash/signature nếu thiết kế yêu cầu.
- Restore archive giữ event ID, source ID và timestamp.
- Search có thể truy xuất archived event theo quy trình.
- Access vào archive được ghi audit.
- Lifecycle deletion không xóa event đang cần cho incident.

Test retention bằng clock/test environment hoặc lifecycle policy simulator. Không dùng test thực tế để xóa hàng loạt log production.

## 31. Test detection dựa trên audit event

Audit event có thể là input cho SIEM rule. Test detection cần xác minh event đủ dữ liệu để rule hoạt động.

Ví dụ:

~~~~text
WHEN
  key.operation.denied occurs 10 times
  for the same principal within 2 minutes
AND
  at least one later key.operation succeeds
THEN
  create a high-severity alert
  attach source event IDs, principal, key IDs and time range
~~~~

Một số test:

- Decrypt spike theo principal/key/tenant.
- Denied-then-success.
- Policy change trước privileged operation.
- Destroy schedule không có approval reference.
- Key usage từ workload/region chưa từng thấy.
- HSM tamper hoặc operator login bất thường.
- Event ingestion gap trong giờ có operation.
- Audit sink outage và synthetic canary failure.

Test phải kiểm tra false positive với batch job, scheduled rotation và maintenance window. Detection rule không nên giả định một event đơn lẻ luôn là compromise.

## 32. Metrics và tiêu chí pass

Các chỉ số có thể theo dõi:

- Event coverage theo operation.
- Tỷ lệ operation có audit event.
- Required-field completeness.
- Schema validation failure rate.
- Collector availability và ingestion lag.
- Duplicate rate.
- Late event rate.
- Sequence gap count.
- Redaction violation count.
- Integrity verification failure.
- Unauthorized audit read/write attempt.
- Retention/archive restore test result.
- Time to search event theo request/key ID.

Tiêu chí pass nên cụ thể:

- Mỗi operation bắt buộc có event theo semantics đã định nghĩa.
- Actor/resource/outcome không bị mất.
- Denied/failure không bị ghi nhầm thành success.
- Event không chứa secret hoặc plaintext.
- Correlation ID và provider operation ID được giữ.
- Duplicate/gap được xử lý đúng policy.
- Tamper/access-control test bị từ chối hoặc phát hiện.
- Search/export/retention đáp ứng yêu cầu.

Không đặt một tỷ lệ coverage chung mà không chỉ rõ operation nào được tính và event nào bắt buộc.

## 33. Lỗi kiểm thử thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ assert API trả success | Không chứng minh event được ghi | Query audit sink và assert payload |
| Chỉ test happy path | Bỏ sót denied/failure | Thêm negative path |
| Tin event do client tạo | Actor/outcome có thể giả | Xác minh provider/authenticated context |
| So sánh timestamp chính xác tuyệt đối | Test flaky do clock skew | Dùng tolerance và quality flag |
| Sleep cố định để chờ log | Chậm và không ổn định | Poll có deadline |
| Không test duplicate | Incident bị nhân đôi | Dedup theo source event ID |
| Không đối soát event count | Không phát hiện log gap | Sequence/checkpoint/reconciliation |
| Chỉ mask trên UI | Raw storage vẫn lộ secret | Redact trước ingest |
| Hash nhưng không kiểm tra source | Provenance không được bảo đảm | Test source/collector trust |
| Dùng production credential | Test tạo rủi ro rò rỉ | Dùng test identity và secret giả |
| Test destroy trên key thật | Có thể mất dữ liệu | Sandbox/provider simulator |
| Không test retention/archive | Evidence có thể mất | Lifecycle và restore tests |

## 34. Tình huống thực tế

### Tình huống A: Decrypt thành công nhưng thiếu key version

Một service gọi Decrypt thành công, nhưng normalized audit event chỉ chứa alias. Incident responder không thể xác định version nào đã được dùng sau một lần rotation.

Contract test phải yêu cầu immutable key ID/version hoặc provider resource reference tương đương. Integration test tạo hai version và xác minh event trỏ đúng version thực tế.

### Tình huống B: Denied request bị ghi thành success

Application phát event success ngay khi nhận request, trước khi KMS trả kết quả. KMS từ chối do policy nhưng SIEM vẫn nhận success.

Test cần điều khiển provider response denied và xác minh không có completed/success event. Có thể có attempted event, nhưng outcome phải phân biệt rõ.

### Tình huống C: Retry tạo duplicate audit

Provider đã hoàn tất operation nhưng response bị mất. Client retry và publisher tạo hai event success cho một provider operation.

Test mô phỏng timeout sau commit, retry cùng idempotency key và xác minh event được liên kết bằng operation ID; consumer deduplicate theo source semantics.

### Tình huống D: Secret bị ghi vào dead-letter queue

Parser lỗi khi event có field mở rộng và đẩy raw payload vào DLQ. Payload vô tình chứa Authorization header.

Redaction phải chạy trước queue hoặc theo boundary đã được xác định. Test quét cả DLQ, retry store và export để bảo đảm token giả không xuất hiện.

## 35. Checklist triển khai

### Event contract và coverage

- [ ] Có event taxonomy và schema version.
- [ ] Có coverage matrix cho key lifecycle và key usage.
- [ ] Field actor/resource/action/outcome được xác định rõ.
- [ ] Provider source event name và ID được giữ.
- [ ] Success, denied, failure và unknown có semantics riêng.
- [ ] Key ID/version và tenant được ghi đúng.

### Pipeline và integrity

- [ ] Contract test chạy với producer payload thực tế.
- [ ] Có unit, integration và end-to-end tests.
- [ ] Request/trace/correlation/provider operation ID được propagate.
- [ ] Có duplicate handling và idempotency.
- [ ] Có sequence/gap monitoring và reconciliation.
- [ ] Timestamp và clock skew được xử lý.
- [ ] Integrity/provenance được xác minh.

### Privacy và operations

- [ ] Redaction xảy ra trước khi lưu raw event.
- [ ] Không có key material, secret, token hoặc plaintext.
- [ ] Audit store có access control và cross-tenant isolation.
- [ ] Retention/legal hold được test.
- [ ] Archive restore giữ integrity.
- [ ] Failure policy của audit sink được kiểm thử.
- [ ] Detection rule có positive và false-positive tests.
- [ ] Test data không dùng production secrets.

## 36. Câu hỏi tự kiểm tra

**1. Test audit event xác minh điều gì?**

Xác minh hệ thống tạo, chuyển, lưu và cung cấp đúng event có đủ actor, action, resource, outcome và provenance.

**2. API trả success có chứng minh audit pass không?**

Không. Phải truy vấn audit sink và kiểm tra event payload.

**3. Audit event khác application log thế nào?**

Audit event là bản ghi có schema, provenance, integrity và retention phục vụ accountability; application log chủ yếu hỗ trợ chẩn đoán.

**4. Vì sao cần event coverage matrix?**

Để xác định operation nào cần event và tránh bỏ sót lifecycle transition hoặc denied path.

**5. Actor trong provider event nên là ai?**

Principal thực tế mà provider xác thực, thường là workload/executor identity.

**6. Requester và executor có thể khác nhau không?**

Có. Workflow cần liên kết requester/approver với executor/provider event bằng request hoặc correlation reference.

**7. Attempted khác completed thế nào?**

Attempted chỉ thể hiện request được gửi/nhận; completed yêu cầu bằng chứng operation hoàn tất.

**8. Provider timeout có luôn là failure không?**

Không. Kết quả có thể unknown nếu provider đã thực thi nhưng response bị mất.

**9. Vì sao key version quan trọng?**

Alias có thể đổi đích; key version giúp xác định chính xác material đã được dùng.

**10. Request ID và trace ID có giống nhau không?**

Không. Request ID định danh request boundary; trace ID theo dõi luồng phân tán.

**11. Event duplicate nên được xử lý thế nào?**

Deduplicate theo source system/event ID hoặc idempotency identity đã định nghĩa.

**12. Làm sao phát hiện event bị mất?**

Đối soát operation count, sequence/checkpoint, collector offset, canary và provider reconciliation.

**13. Timestamp ingest có thể thay event time không?**

Không. Cần giữ cả hai để xử lý late arrival và clock skew.

**14. Hash event có chứng minh source đáng tin không?**

Không. Hash kiểm tra nội dung; source và collector provenance cần được xác thực riêng.

**15. Có được ghi plaintext để phục vụ điều tra không?**

Không. Ghi metadata và reference an toàn, không ghi key material hoặc plaintext.

**16. Vì sao cần quét dead-letter queue?**

Raw payload có thể đi vào DLQ khi parser lỗi và chứa dữ liệu nhạy cảm nếu redaction quá muộn.

**17. Khi audit sink ngừng hoạt động, có phải dừng mọi key operation không?**

Không có quy tắc chung. Behavior phải theo operation risk, durable buffer và policy fail-open/fail-closed.

**18. Vì sao cần test retention và restore?**

Để bảo đảm evidence tồn tại đủ thời gian và vẫn xác minh được sau archive/restore.

**19. Test detection rule cần kiểm tra gì ngoài alert?**

Event references, principal, key IDs, time range, severity, deduplication và false positive behavior.

**20. Khi nào audit event test được coi là đầy đủ?**

Khi coverage, semantics, schema, delivery, integrity, privacy, access, retention và end-to-end retrieval đều được kiểm chứng.

## 37. Tài liệu tham khảo

- NIST SP 800-53 Rev. 5 — Security and Privacy Controls, nhóm Audit and Accountability (AU).
- NIST SP 800-92 — Guide to Computer Security Log Management.
- NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management.
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management.
- RFC 5424 — The Syslog Protocol.
- RFC 8785 — JSON Canonicalization Scheme, khi áp dụng canonical JSON.
- W3C Trace Context — Distributed tracing context propagation.
- Tài liệu audit logging, event schema, retention và key lifecycle của KMS/HSM/secret manager đang triển khai.
- Chính sách nội bộ về audit evidence, privacy, incident response và log retention.

