# Liên kết audit với incident

Audit log ghi lại những gì đã xảy ra; incident record mô tả sự kiện bảo mật nào cần điều tra, tác động ra sao và tổ chức đã phản ứng thế nào. Liên kết hai nguồn này giúp đội bảo mật đi từ một dấu hiệu bất thường tới bằng chứng có thể kiểm chứng: ai đã gọi key operation, key và dữ liệu nào bị ảnh hưởng, quyền nào đã thay đổi, sự kiện nào xảy ra trước hoặc sau, và biện pháp ứng phó có thực sự chặn được rủi ro hay không.

Trong quản lý khóa mật mã, một incident có thể bắt đầu từ một lần decrypt bất thường, thao tác export key, thay đổi key policy, quyền destroy được cấp trái phép, secret xuất hiện trong CI log hoặc HSM báo hiệu can thiệp vật lý. Nếu audit event không có định danh nhất quán, timestamp đáng tin cậy và thông tin resource đủ chi tiết, việc ghép các sự kiện thành timeline sẽ chậm và dễ sai. Nếu log chứa key material, password hoặc plaintext, chính hệ thống điều tra lại trở thành nơi rò rỉ bí mật.

Bài học trình bày cách liên kết audit event với incident lifecycle trong hệ thống key management: chuẩn hóa sự kiện, correlation identifier, timeline, evidence integrity, chain of custody, SIEM/SOAR, phân tích phạm vi key compromise, playbook ứng phó, bảo vệ dữ liệu nhạy cảm và kiểm thử end-to-end.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Phân biệt audit event, security alert, incident và evidence record.
- Xác định các nguồn audit quan trọng trong KMS/HSM, IAM, secret manager, PKI, ứng dụng và hạ tầng.
- Thiết kế schema sự kiện có actor, action, resource, outcome, timestamp, request ID và correlation ID.
- Liên kết event từ nhiều hệ thống mà vẫn giữ nguyên nguồn gốc và nội dung gốc.
- Tạo incident timeline với event time, ingest time, clock skew và thứ tự nhân quả.
- Phân tích key lifecycle event, key usage anomaly, policy change và privileged action.
- Xác định key, key version, tenant, ciphertext, DEK, KEK và workload bị ảnh hưởng.
- Bảo toàn audit evidence, integrity, provenance và chain of custody.
- Kết nối SIEM/SOAR với incident management mà không tự động thực hiện destructive action thiếu kiểm soát.
- Thiết kế playbook cho key compromise, unauthorized decrypt, key export, policy tampering và secret leak.
- Bảo vệ log khỏi chứa secret, key material, password, token hoặc plaintext.
- Kiểm thử khả năng phát hiện, correlation, escalation, containment và hậu kiểm.

Phạm vi tập trung vào audit và incident liên quan tới vòng đời, truy cập và sử dụng key. Cách tích hợp cụ thể phụ thuộc KMS/HSM, cloud provider, SIEM, log pipeline và hệ thống quản lý incident đang triển khai.

## 2. Audit event, alert, incident và evidence khác nhau thế nào?

Các khái niệm có liên quan nhưng có vai trò riêng:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Audit event | Bản ghi một hành động hoặc thay đổi đã xảy ra | Principal gọi Decrypt trên key version 7 |
| Security signal | Dấu hiệu có thể liên quan tới rủi ro | Một workload decrypt tăng đột biến |
| Alert | Thông báo được tạo khi signal vượt điều kiện phát hiện | 500 lần decrypt trong 2 phút |
| Incident | Vụ việc bảo mật được quản lý theo quy trình ứng phó | Credential của service thanh toán bị lộ |
| Evidence | Dữ liệu được bảo toàn để hỗ trợ điều tra và kết luận | Log gốc có chữ ký, snapshot IAM policy |
| Case/ticket | Hồ sơ theo dõi công việc và quyết định | SEC-INC-2026-042 |

Một audit event không tự động là incident. Một alert cũng chưa chứng minh compromise. Incident được mở khi tín hiệu đạt tiêu chí phân loại hoặc cần điều phối phản ứng. Evidence cần giữ được nguồn gốc và integrity; ticket chỉ là nơi quản lý công việc, không tự động thay thế kho evidence.

### Ví dụ

Một KMS ghi nhận principal service-A gọi Decrypt 20 lần trong một phút. Đây là audit event. SIEM phát hiện số lần tăng vượt baseline và tạo alert. Analyst kiểm tra deployment, source IP, tenant và key usage; nếu phát hiện credential bị đánh cắp, đội ứng phó mở incident. Audit log gốc, identity logs, deployment record và network telemetry được bảo toàn thành evidence.

## 3. Vì sao phải liên kết audit với incident?

Nếu mỗi hệ thống ghi log riêng và không có correlation, điều tra phải ghép dữ liệu thủ công. Điều này làm tăng thời gian xác định phạm vi và nguy cơ bỏ sót hành động liên quan.

Liên kết audit với incident giúp:

- Xác định chuỗi sự kiện trước, trong và sau dấu hiệu đầu tiên.
- Tìm principal, session, workload và source đã thực hiện operation.
- Xác định key ID/version, purpose và tenant bị tác động.
- Tìm những lần encrypt/decrypt/sign/unwrap khác dùng cùng credential hoặc key.
- Xác định policy/IAM change nào đã mở đường cho hành động.
- Đánh giá dữ liệu nào có thể đã bị đọc, sửa hoặc ký giả mạo.
- Xác minh containment đã chặn được operation hay chưa.
- Theo dõi rotation, revoke, rekey, rewrap và recovery trong cùng incident.
- Chứng minh quyết định, approval và thời điểm thực hiện.
- Rút kinh nghiệm và cập nhật detection rule.

Trong key management, một sự kiện đơn lẻ thường chưa đủ để đánh giá. Một lần Decrypt có thể hợp lệ; nhưng nếu cùng principal vừa được cấp quyền mới, đăng nhập từ vùng bất thường, rồi decrypt nhiều tenant trong thời gian ngắn, chuỗi event đó có ý nghĩa khác.

## 4. Nguồn audit trong hệ thống quản lý khóa

Một incident liên quan tới key có thể trải qua nhiều control plane và data plane. Cần inventory nguồn log thay vì chỉ thu thập KMS audit.

| Nguồn | Sự kiện cần thu thập |
|---|---|
| KMS | Create, import, encrypt, decrypt, wrap, unwrap, sign, verify, disable, schedule deletion, destroy |
| HSM | Login, role change, partition access, key generation, key usage, tamper alarm, backup/restore, operator ceremony |
| IAM/Identity provider | Authentication, MFA, role assignment, policy change, token issuance, session revoke |
| Secret manager | Secret read, version create, rotate, access denied, lease issue/renew/revoke |
| PKI/CA | Certificate issue, renew, revoke, CRL/OCSP status, CA policy change |
| Application | Business request, authorization decision, key reference, operation result |
| Database/object store | Access tới ciphertext, metadata, export, object version và restore |
| CI/CD | Build identity, secret injection, deployment, artifact provenance, pipeline permission change |
| Network/host | Source IP, workload identity, process, container, endpoint và egress |
| Incident platform | Alert, case creation, assignment, severity, decision, containment và closure |

Không phải mọi nguồn đều có cùng độ tin cậy. Audit từ KMS có thể xác nhận provider nhận một operation; application log có thể mô tả business purpose; IAM log có thể cho biết principal được cấp quyền khi nào. Phải giữ source identity và phân biệt dữ liệu quan sát trực tiếp với dữ liệu do ứng dụng tự khai báo.

## 5. Event taxonomy cho key management

Một taxonomy ổn định giúp detection rule và dashboard không phụ thuộc vào cách đặt tên riêng của từng provider.

Các nhóm event gợi ý:

| Nhóm | Event điển hình |
|---|---|
| Key lifecycle | key.created, key.imported, key.enabled, key.disabled, key.rotated, key.destroy.scheduled, key.destroyed |
| Key usage | key.encrypt, key.decrypt, key.wrap, key.unwrap, key.sign, key.verify |
| Access control | key.policy.changed, key.grant.created, key.grant.revoked, role.assigned |
| Authentication | principal.authenticated, mfa.failed, session.created, session.revoked |
| Secret lifecycle | secret.read, secret.version.created, secret.rotated, secret.revoked |
| Certificate/PKI | certificate.issued, certificate.renewed, certificate.revoked |
| HSM operations | hsm.login, hsm.partition.changed, hsm.tamper.detected |
| Recovery | key.backup.created, key.restore.started, key.restore.completed |
| Incident response | incident.opened, incident.severity.changed, containment.applied, incident.closed |

Tên event chuẩn hóa không thay thế provider event name. Lưu cả event type chuẩn hóa và original event name để có thể truy ngược parser, provider semantics và dữ liệu nguồn.

### Event category và outcome

Ngoài event type, nên có category và outcome:

- Category: identity, access, key_lifecycle, key_usage, policy, secret, certificate, hsm, recovery.
- Outcome: success, denied, failure, partial, unknown.
- Reason: policy_denied, invalid_state, provider_error, timeout, approval_missing.
- Severity: informational, low, medium, high, critical.

Không gán severity cao chỉ vì event name có chữ destroy. Severity phải phụ thuộc key type, environment, actor, context và kết quả thực tế.

## 6. Schema audit event chuẩn hóa

Một event hữu ích cho incident response cần trả lời ai, làm gì, với resource nào, khi nào, ở đâu, theo request nào và kết quả ra sao.

Các trường cốt lõi:

| Field | Mô tả |
|---|---|
| event_id | ID duy nhất của event nguồn hoặc event chuẩn hóa |
| event_type | Tên event chuẩn hóa |
| event_time | Thời điểm hành động xảy ra theo nguồn |
| observed_time | Thời điểm collector quan sát event |
| ingested_time | Thời điểm event được lưu vào pipeline |
| source_system | KMS, HSM, IAM, application, SIEM... |
| source_event_id | ID gốc của provider |
| actor_id | Principal/workload đã xác thực |
| actor_type | human, service, workload, automation |
| action | Operation thực hiện |
| resource_id | Immutable key ID/secret ID/certificate ID |
| resource_version | Key/secret/certificate version |
| tenant_id | Tenant hoặc namespace |
| environment | dev, staging, production |
| request_id | ID của request trong service |
| trace_id | Trace context nếu có |
| correlation_id | ID nối các event cùng workflow |
| outcome | success, denied, failure, unknown |
| reason_code | Mã lý do |
| source_ip | Nguồn mạng nếu phù hợp |
| workload_id | Service, pod, job hoặc device |
| policy_version | Phiên bản policy tại thời điểm quyết định |
| integrity_metadata | Chữ ký, hash, collector sequence hoặc provenance |

Không phải nguồn nào cũng cung cấp mọi field. Không tự bịa giá trị còn thiếu. Dùng null/unknown và giữ nguyên source payload để parser có thể được cải tiến sau.

### Event mẫu

~~~~json
{
  "eventId": "evt-kms-9f21",
  "eventType": "key.decrypt",
  "eventTime": "2026-11-28T03:15:22.418Z",
  "observedTime": "2026-11-28T03:15:22.611Z",
  "sourceSystem": "kms-prod-eu",
  "sourceEventId": "provider-784120",
  "actor": {
    "id": "workload:payments-api",
    "type": "workload"
  },
  "resource": {
    "id": "key-payments-tenant-42",
    "version": "v7",
    "tenantId": "tenant-42",
    "environment": "production"
  },
  "action": "Decrypt",
  "requestId": "req-7b3a",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "correlationId": "rotation-job-2026-11-28-01",
  "outcome": "success",
  "reasonCode": null
}
~~~~

Event mẫu chỉ chứa metadata. Không thêm plaintext, key bytes, wrapped key blob, password, access token hoặc toàn bộ Authorization header.

## 7. Correlation ID, request ID, trace ID và incident ID

Các ID này giải quyết những bài toán khác nhau:

| ID | Mục đích | Phạm vi |
|---|---|---|
| event_id | Định danh một event | Một bản ghi |
| source_event_id | Định danh event tại hệ thống nguồn | Một provider/source |
| request_id | Theo dõi một request hoặc command | Một request boundary |
| trace_id | Theo dõi luồng xử lý phân tán | Một distributed trace |
| correlation_id | Nối các event cùng business workflow hoặc operation | Một workflow |
| incident_id | Nối evidence, alert, task và quyết định ứng phó | Một incident |

Không dùng incident ID làm correlation ID cho mọi event. Một incident có thể chứa hàng nghìn workflow; một workflow có thể xảy ra trước khi incident được mở. Khi incident được tạo, hệ thống incident management có thể liên kết các event/correlation đã phát hiện với incident ID.

### Correlation strategy

- Propagate request ID qua service boundary khi request còn cùng ngữ nghĩa.
- Propagate trace context qua distributed tracing theo chuẩn đang dùng.
- Tạo correlation ID riêng cho workflow dài như key rotation hoặc destruction ceremony.
- Giữ source event ID để deduplicate và truy ngược.
- Khi mở incident, lưu danh sách event ID, trace ID, correlation ID và time range liên quan.
- Không cho caller tự gắn incident ID tùy ý vào event nếu không có quyền hoặc workflow hợp lệ.
- Giữ quan hệ nhiều-nhiều: một event có thể liên quan nhiều incident và một incident chứa nhiều event.

Correlation ID không phải bằng chứng rằng các event có quan hệ nhân quả. Phải kiểm tra actor, resource, request context và thời gian.

## 8. Timeline và xử lý thời gian

Incident timeline thường kết hợp event từ nhiều hệ thống có clock khác nhau. Một event có event time 10:00:05 nhưng collector nhận lúc 10:00:12; hệ thống khác có thể lệch đồng hồ 4 giây.

Cần phân biệt:

- Event time: thời điểm source nói hành động xảy ra.
- Observed time: thời điểm collector nhận/quan sát.
- Ingest time: thời điểm pipeline ghi event vào storage.
- Processed time: thời điểm detection engine xử lý event.
- Decision time: thời điểm analyst hoặc automation đưa ra quyết định.

Nguyên tắc:

- Chuẩn hóa thời gian về UTC khi lưu trữ.
- Giữ timestamp gốc và timezone/source metadata.
- Đồng bộ clock bằng NTP hoặc cơ chế đáng tin cậy.
- Đo và cảnh báo clock skew.
- Không sắp xếp chỉ theo ingest time.
- Khi cần, dùng sequence number hoặc provider operation ID.
- Đánh dấu timeline entry có timestamp không đáng tin cậy.
- Không suy diễn thứ tự nhân quả chỉ từ timestamp gần nhau.

Một incident report nên thể hiện cả event time và ingest time khi độ trễ có ý nghĩa. Ví dụ, log HSM được đẩy ra sau khi thiết bị reconnect có thể tạo khoảng trống quan sát trong thời gian outage.

## 9. Liên kết audit event với incident record

Incident record cần tham chiếu tới event/evidence gốc, không sao chép tùy tiện payload rồi bỏ mất provenance.

Một incident có thể lưu:

- Incident ID, title, severity, status và owner.
- Detection rule hoặc nguồn phát hiện.
- First seen, last seen và time range.
- Actor/principal và workload bị nghi ngờ.
- Key/secret/certificate IDs liên quan.
- Tenant, environment và business service.
- Event IDs và source event IDs.
- Trace/request/correlation IDs.
- Evidence object references và integrity hashes.
- Hypothesis, findings và confidence.
- Containment/eradication/recovery actions.
- Approval và change/incident decision.
- Kết quả xác minh và lessons learned.

Incident platform nên lưu reference tới evidence store có access control riêng. Không biến ticket thành nơi chứa secret, raw key material, memory dump hoặc plaintext.

### Quan hệ nhiều-nhiều

Một event policy change có thể liên quan incident compromise và incident change-control. Một incident compromise có thể liên quan nhiều key version và nhiều service. Dùng bảng liên kết event-to-incident thay vì nhét một incident ID duy nhất vào event bất biến sau khi phát sinh.

## 10. Quy trình incident lifecycle

~~~~mermaid
flowchart TD
    A[Audit events từ các nguồn]
    B[Normalize và validate]
    C[Correlate và detect]
    D[Alert]
    E[Triage và mở incident]
    F[Preserve evidence]
    G[Containment]
    H[Eradication và recovery]
    I[Validate và close]
    J[Lessons learned]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J
~~~~

Các giai đoạn:

1. **Prepare:** xác định nguồn log, owner, quyền truy cập, retention và playbook.
2. **Detect:** rule, anomaly hoặc report tạo signal.
3. **Triage:** kiểm tra context, false positive, severity và phạm vi.
4. **Preserve:** bảo toàn log gốc, snapshot policy và evidence liên quan.
5. **Contain:** chặn credential, session, key operation hoặc workload bị ảnh hưởng.
6. **Eradicate:** loại bỏ persistence, credential bị lộ và policy độc hại.
7. **Recover:** phát hành key/secret mới, khôi phục workload và kiểm tra dữ liệu.
8. **Validate:** xác nhận detection, access control và key state đã ổn định.
9. **Close:** ghi kết luận, impact, evidence và action còn lại.
10. **Improve:** cập nhật policy, detection rule, inventory và training.

Thứ tự preserve và containment có thể diễn ra song song. Khi có nguy cơ exfiltration đang tiếp diễn, containment có thể phải thực hiện ngay trong khi collector tiếp tục giữ evidence. Không trì hoãn biện pháp ngăn chặn cấp thiết chỉ để hoàn thành một bản export log thủ công.

## 11. Phát hiện bất thường trong key usage

Một event chỉ trở thành signal đáng chú ý khi được đặt trong baseline và context.

Các pattern cần phát hiện:

- Decrypt volume tăng đột ngột.
- Một principal truy cập nhiều key/tenant ngoài phạm vi thường lệ.
- Decrypt từ region, IP hoặc workload mới.
- Encrypt/decrypt ngoài thời gian hoạt động dự kiến.
- Một key được dùng bởi principal chưa từng thấy.
- Nhiều access denied liên tiếp trước một lần thành công.
- Operation export/import hoặc unwrap bất thường.
- Key usage tăng sau khi cấp role hoặc thay policy.
- Key version cũ được dùng sau khi đã retire.
- HSM login hoặc operator action ngoài ceremony.
- Một secret được đọc bởi nhiều workload mới.
- Certificate hoặc signing key được dùng ngoài service owner.

Baseline cần xét deployment, batch schedule, seasonality và business event. Không cảnh báo chỉ theo ngưỡng tuyệt đối nếu workload có traffic biến động tự nhiên.

## 12. Phát hiện thay đổi policy và quyền đặc quyền

Policy tampering có thể xảy ra trước khi attacker dùng key. Vì vậy, audit của IAM, KMS key policy, grant và organization guardrail phải được liên kết với key usage.

Các chuỗi cần correlation:

- Role assignment → key policy change → decrypt spike.
- Grant creation → principal mới → key export attempt.
- MFA failure → privileged session → schedule deletion.
- CI/CD permission change → secret read → production deployment.
- HSM operator login → partition policy change → key operation.
- Break-glass activation → destroy schedule → cancel deletion.

Một policy change hợp lệ cũng cần audit actor, approval, change ticket, before/after diff và rollout result. Không chỉ ghi rằng “policy updated”; phải có reference tới policy version hoặc canonical diff có integrity.

## 13. Phân tích incident key compromise

Khi nghi ngờ key compromise, incident team phải xác định key nào bị lộ, khả năng attacker sử dụng key và dữ liệu phụ thuộc.

Phân loại:

| Loại compromise | Điều tra chính |
|---|---|
| API/KMS credential bị lộ | Principal, session, permissions, KMS calls và token lifetime |
| DEK bị lộ | Ciphertext, object, tenant, backup và plaintext exposure |
| KEK bị lộ | Wrapped DEK inventory, unwrap operations, dependent DEK và rewrap |
| Signing private key bị lộ | Signature, certificate, token/JWT, artifact và trust propagation |
| HMAC key bị lộ | Message authenticity, webhook, replay và shared consumers |
| HSM/KMS control plane bị chiếm | Key policy, grants, admin actions, audit integrity và key state |
| Recovery/escrow material bị lộ | Backup, recovery package, trustee access và restore activity |

### Dependency graph

~~~~mermaid
flowchart TD
    KMSCred[KMS credential]
    KEK[KEK version 4]
    DEK1[DEK tenant A]
    DEK2[DEK tenant B]
    C1[Ciphertext objects A]
    C2[Backup archive B]
    S[Signing key]
    T[Signed tokens]
    KMSCred --> KEK
    KEK --> DEK1 --> C1
    KEK --> DEK2 --> C2
    S --> T
~~~~

Một KMS credential bị lộ không tự động có nghĩa raw KEK đã bị export. Cần xem credential có quyền gọi operation nào, policy có cho export không, provider có non-exportable guarantee và audit có ghi nhận hành vi bất thường không. Phân biệt khả năng truy cập operation với việc key material đã bị lấy.

## 14. Evidence integrity và chain of custody

Evidence chỉ có giá trị điều tra khi có thể giải thích nó đến từ đâu, ai thu thập, lúc nào, có bị thay đổi không và ai đã truy cập.

Các kiểm soát:

- Giữ bản ghi gốc bất biến hoặc append-only.
- Tạo hash khi ingest và xác minh khi truy xuất.
- Ký manifest hoặc batch metadata bằng signing key được bảo vệ độc lập.
- Lưu source system, source event ID, collector identity và ingest timestamp.
- Ghi mọi lần export, read, copy và transfer evidence.
- Hạn chế quyền xóa/sửa evidence.
- Tách quyền vận hành SIEM khỏi quyền quản trị evidence archive.
- Dùng WORM/immutable storage khi phù hợp với retention.
- Bảo vệ signing key của evidence khỏi cùng blast radius với hệ thống đang điều tra.
- Ghi rõ mọi khoảng trống log hoặc collector outage.

Hash chứng minh dữ liệu không đổi so với digest đã ghi; nó không chứng minh nguồn tạo log là đáng tin cậy. Chữ ký cũng chỉ chứng minh dữ liệu được ký bởi key tương ứng, không tự chứng minh event là đúng. Cần xác thực source, collector, key custody và ingestion path.

### Chain of custody

Một evidence transfer record nên ghi:

- Evidence ID và incident ID.
- Source, source event range và collection method.
- Collector/analyst identity.
- Timestamp bắt đầu/kết thúc thu thập.
- Hash algorithm và digest.
- Storage location/reference.
- Người bàn giao, người nhận và thời điểm.
- Integrity verification result.
- Mục đích truy cập và authorization.

Không dùng một file CSV gửi qua email làm evidence archive duy nhất cho incident nghiêm trọng.

## 15. Bảo vệ log khỏi lộ secret

Audit phải ghi đủ thông tin điều tra nhưng không chứa bí mật có thể tái sử dụng.

Không ghi:

- Raw DEK, KEK, private key hoặc HSM PIN.
- Password, API key, client secret và bearer token.
- Plaintext trước/sau decrypt.
- Full Authorization header.
- Secret manager response body.
- Wrapped key blob nếu không cần thiết và chưa đánh giá sensitivity.
- Recovery share hoặc escrow package.
- Nội dung nhạy cảm không cần thiết của request.

Có thể ghi:

- Immutable key ID/version.
- Secret ID/version nhưng không ghi value.
- Operation name và outcome.
- Principal/workload ID.
- Tenant/resource ID theo access policy.
- Provider operation ID.
- Policy version và reason code.
- Hash hoặc fingerprint đã được thiết kế để không tiết lộ material và được phê duyệt.

Redaction phải diễn ra trước khi event vào log sink. Không dựa vào dashboard masking nếu raw payload đã được lưu ở nơi khác.

## 16. Detection rule và correlation logic

Detection rule nên kết hợp nhiều nguồn, không chỉ một event đơn lẻ.

### Ví dụ: decrypt bất thường sau khi cấp quyền

~~~~text
WHEN
  IAM role assignment succeeds
AND
  the assigned role includes key.decrypt
AND
  a new principal uses that role on production keys
AND
  decrypt volume exceeds the principal baseline
WITHIN
  15 minutes
THEN
  create high-severity alert
  attach IAM event IDs and KMS decrypt event IDs
  include key IDs, principal ID, tenant IDs and source context
~~~~

### Ví dụ: destroy workflow bị bypass

~~~~text
WHEN
  KMS reports ScheduleDeletion or Destroy
AND
  no matching approved destruction request exists
AND
  no authorized break-glass record exists
THEN
  create critical alert
  preserve KMS event, IAM policy snapshot and actor session
  notify key custodian and incident response
~~~~

### Ví dụ: key export attempt

~~~~text
WHEN
  key.export or private-key export is attempted
AND
  resource classification is non-exportable or production
THEN
  alert immediately
  correlate principal, role changes, source host and HSM/KMS audit
  preserve denied and successful attempts
~~~~

Các tên event là dạng chuẩn hóa minh họa. Rule production phải dùng event semantics thực tế, xử lý duplicate, late arrival và false positive. Với operation bị deny, vẫn phải ghi nhận vì chuỗi denied-then-success có thể quan trọng.

## 17. SIEM và SOAR integration

SIEM tập trung thu thập, chuẩn hóa, truy vấn, correlation và phát hiện. SOAR điều phối playbook và hành động phản ứng qua connector.

Một luồng tích hợp:

~~~~mermaid
flowchart LR
    S1[KMS/HSM]
    S2[IAM/Secrets]
    S3[Application/CI]
    C[Collectors]
    N[Normalize and enrich]
    D[SIEM detection]
    I[Incident platform]
    O[SOAR playbook]
    A[Approved response]
    S1 --> C
    S2 --> C
    S3 --> C
    C --> N --> D --> I --> O --> A
~~~~

SIEM/SOAR có thể:

- Tạo incident khi detection rule đạt điều kiện.
- Enrich principal với owner, workload và environment.
- Enrich key ID với purpose, tenant, key version và dependency.
- Tạo timeline và danh sách event liên quan.
- Mở task cho key owner hoặc security approver.
- Gọi action containment đã được phê duyệt.
- Theo dõi kết quả provider và xác minh sau action.

Không để alert tự động destroy key hoặc xóa evidence. Các hành động như disable, revoke, rotate hoặc destroy có thể làm gián đoạn dịch vụ hoặc mất dữ liệu; cần playbook, scope, approval và rollback policy tương ứng. Có thể tự động hóa bước read-only enrichment và preserve evidence trước.

## 18. Playbook: unauthorized decrypt

Khi phát hiện decrypt trái phép hoặc nghi ngờ:

1. Mở incident và gắn KMS event IDs, principal, key ID/version, tenant và request context.
2. Kiểm tra actor là user, service account hay workload; xác minh identity và session.
3. Correlate IAM role/grant/policy change trước event.
4. Tìm decrypt operations khác của cùng principal, key và source.
5. Kiểm tra object/ciphertext được truy cập và business authorization.
6. Xác định plaintext có thể đã rời khỏi trust boundary qua application/network log.
7. Preserve KMS, IAM, application, database và network evidence.
8. Contain bằng revoke session/credential hoặc giảm quyền operation theo incident decision.
9. Nếu key material hoặc credential compromise, tạo key/credential mới và xử lý dữ liệu phụ thuộc.
10. Verify old principal/credential bị từ chối và không còn session hoạt động.
11. Ghi phạm vi, confidence, impact và quyết định recovery.

Không kết luận plaintext đã bị exfiltrate chỉ từ một lần Decrypt thành công. Cần correlation với ứng dụng, network egress, object access và telemetry phù hợp.

## 19. Playbook: key policy hoặc IAM tampering

Khi có policy change bất thường:

- Thu thập before/after policy, actor, session và approval reference.
- Kiểm tra change ticket và deployment pipeline.
- Xác định action/resource scope mới được cấp.
- Tìm operation sử dụng quyền vừa cấp.
- So sánh policy version với baseline đã phê duyệt.
- Kiểm tra grant, role inheritance và organization guardrail.
- Preserve audit từ control plane và identity provider.
- Revert policy bằng change được phê duyệt nếu policy độc hại.
- Revoke session hoặc credential có khả năng bị chiếm.
- Chạy access test để xác nhận quyền trái phép đã bị loại bỏ.
- Theo dõi việc policy không bị attacker khôi phục.

Không chỉ so sánh text policy. Cần đánh giá semantics của wildcard, condition, inherited role, grant và deny precedence.

## 20. Playbook: secret leak trong CI/CD

Secret có thể bị lộ qua pipeline output, build artifact, environment dump hoặc dependency compromise.

Điều tra:

1. Xác định pipeline run, commit, actor và runner.
2. Tìm secret ID/version được inject, không truy xuất value vào ticket.
3. Kiểm tra log masking và artifact retention.
4. Xác định secret có thể đã bị tải xuống hoặc copy sang nơi khác.
5. Kiểm tra downstream API usage sau thời điểm leak.
6. Revoke secret tại issuer theo incident policy.
7. Phát hành version mới và cập nhật workload.
8. Kiểm tra token/session đã cấp bằng secret cũ.
9. Loại bỏ artifact/cache/log bản sao theo retention và forensic policy.
10. Sửa pipeline để dùng workload identity hoặc short-lived credential.

Xóa dòng log chứa secret không thay thế việc revoke. Giả định secret đã bị sao chép nếu đã xuất hiện trong output mà người không được phép có thể đọc.

## 21. Containment, recovery và key lifecycle

Incident response có thể cần nhiều thao tác key lifecycle. Phải chọn action theo loại compromise và impact.

| Hành động | Mục đích | Điều cần kiểm tra |
|---|---|---|
| Revoke credential | Chặn principal tiếp tục xác thực | Session, token và consumer |
| Disable key | Ngăn operation dùng key | Tác động decrypt/unwrap và cache |
| Rotate secret | Thay API/database/client secret | Issuer và consumer rollout |
| Rekey | Tạo key material mới | Certificate, key registry và consumer |
| Rewrap | Bọc lại DEK bằng KEK mới | Tất cả wrapped DEK và backup |
| Re-encrypt | Mã hóa lại dữ liệu bằng key/algorithm mới | Plaintext handling, integrity và migration |
| Re-sign | Ký lại dữ liệu/artifact đáng tin cậy | Nguồn gốc nội dung và timestamp |
| Destroy | Hủy key material | Dependency, retention, approval và recovery |

Không chọn destroy chỉ vì tên incident là “key compromise”. Có trường hợp cần disable/revoke trước để containment, sau đó preserve evidence và đánh giá dependency. Nếu raw DEK bị lộ, rewrap DEK không đủ; cần DEK mới và re-encrypt dữ liệu. Nếu KEK bị lộ, cần đánh giá wrapped DEK và quyền unwrap. Nếu signing key bị lộ, cần revoke certificate/token trust và xác minh signature trong khoảng thời gian bị ảnh hưởng.

## 22. Incident timeline và impact assessment

Timeline nên phân biệt sự kiện đã xác minh, giả thuyết và khoảng trống quan sát.

Ví dụ:

| Thời điểm UTC | Event | Nguồn | Diễn giải |
|---|---|---|---|
| 03:10:02 | Role được thêm quyền Decrypt | IAM | Quyền mới xuất hiện |
| 03:12:18 | Workload login từ IP mới | Identity | Có thể là session bất thường |
| 03:15:22 | Decrypt thành công trên key v7 | KMS | Operation cần điều tra |
| 03:15:24 | Object được đọc | Storage | Có thể liên quan payload |
| 03:16:01 | Egress tăng | Network | Cần xác minh exfiltration |
| 03:18:30 | Incident mở | Incident platform | Analyst bắt đầu điều tra |
| 03:20:10 | Session bị revoke | Identity | Containment |
| 03:22:45 | Decrypt bị từ chối | KMS | Bằng chứng containment có hiệu lực |

Impact assessment cần trả lời:

- Key nào và version nào bị tác động?
- Operation nào đã thành công, operation nào bị từ chối?
- Có bao nhiêu tenant/object/ciphertext phụ thuộc?
- Dữ liệu có thể đã bị đọc hoặc sửa không?
- Key có thể bị export hay chỉ dùng qua provider API?
- Backup, archive, replica và DR có bị ảnh hưởng?
- Certificate, token, signature hoặc MAC nào cần đánh giá?
- Credential nào có thể cùng bị lộ?
- Khoảng thời gian nào log đầy đủ, khoảng nào thiếu?

Phải ghi rõ mức confidence và giới hạn của telemetry. “Không thấy event” không đồng nghĩa “không xảy ra” nếu nguồn log bị gián đoạn.

## 23. Audit pipeline: reliability và failure handling

Audit pipeline có thể gặp mất log, duplicate, late event, out-of-order, schema drift hoặc collector compromise.

Thiết kế nên có:

- Durable buffering ở collector.
- At-least-once delivery và deduplication theo source event ID.
- Sequence number hoặc checkpoint để phát hiện gap.
- Retry có backoff và dead-letter queue.
- Schema version và compatibility validation.
- Monitoring cho collector lag và ingestion gap.
- Integrity check theo batch.
- Backpressure và capacity planning.
- Quarantine event không parse được nhưng vẫn giữ raw payload.
- Reconciliation giữa provider event count và SIEM ingest count khi có API hỗ trợ.

Exactly-once end-to-end thường khó đảm bảo. Thiết kế thực tế nên xử lý at-least-once an toàn: event có thể đến nhiều lần nhưng không tạo nhiều incident hoặc chạy lại destructive action.

### Khi audit sink không hoạt động

Chính sách fail-open/fail-closed phụ thuộc operation:

- Với thao tác destroy, policy change đặc quyền hoặc export key: thường cần chặn hoặc tạm dừng nếu audit bắt buộc không thể ghi.
- Với decrypt traffic quan trọng: có thể cần durable local buffer và cảnh báo khẩn cấp thay vì dừng mọi request, tùy risk acceptance.
- Với HSM ceremony: phải có cơ chế audit thay thế được phê duyệt và đối soát sau khi hệ thống phục hồi.

Không dùng một quy tắc fail-closed duy nhất cho mọi operation mà không xét availability và threat model. Quyết định phải được policy owner phê duyệt.

## 24. Enrichment và data minimization

Enrichment giúp analyst hiểu event mà không cần truy cập thêm nhiều hệ thống.

Enrichment có thể thêm:

- Principal owner, team và workload identity.
- Key owner, key purpose, algorithm và lifecycle state.
- Tenant classification và environment.
- Service criticality và dependency graph.
- Change ticket, deployment version và maintenance window.
- Baseline usage và expected region.
- Provider account, region và resource tag đã xác thực.

Chỉ enrich từ nguồn authoritative. Nếu tag hoặc owner metadata do caller tự gửi, phải đánh dấu là untrusted input.

Data minimization:

- Chỉ thu thập payload cần cho security monitoring.
- Redact secret trước ingest.
- Giới hạn PII và retention theo mục đích.
- Phân quyền theo incident role.
- Audit mọi lần truy cập evidence nhạy cảm.
- Có quy trình legal hold và deletion.
- Tách operational logs khỏi forensic evidence.

## 25. Java 17: chuẩn hóa audit event

Ví dụ sau mô hình hóa event metadata và validation cơ bản. Nó không ghi secret hoặc key material.

~~~~java
import java.time.Instant;
import java.util.Objects;

public record KeyAuditEvent(
        String eventId,
        String eventType,
        Instant eventTime,
        Instant observedTime,
        String sourceSystem,
        String sourceEventId,
        String actorId,
        String action,
        String keyId,
        String keyVersion,
        String tenantId,
        String requestId,
        String correlationId,
        String outcome,
        String reasonCode,
        boolean timestampOrderAnomaly
) {
    public KeyAuditEvent {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(eventType);
        Objects.requireNonNull(eventTime);
        Objects.requireNonNull(observedTime);
        Objects.requireNonNull(sourceSystem);
        Objects.requireNonNull(sourceEventId);
        Objects.requireNonNull(actorId);
        Objects.requireNonNull(action);
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(keyVersion);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(outcome);

        if (eventId.isBlank() || keyId.isBlank()
                || sourceEventId.isBlank()) {
            throw new IllegalArgumentException(
                    "Required audit identifiers are missing"
            );
        }

        // Preserve the event while making a suspicious timestamp order explicit.
        timestampOrderAnomaly = observedTime.isBefore(eventTime);
    }
}
~~~~

Ví dụ cho thấy các field định danh và timestamp. Production parser cần giữ raw event gốc, schema version, collector identity, source signature/hash và các field mở rộng. Timestamp không hợp lý không nên làm event biến mất; hãy giữ event và gắn quality flag để timeline không dùng nó như một mốc chắc chắn.

## 26. Java 17: liên kết event với incident

Ví dụ sau tạo một link record giữa event và incident. Nó không tự kết luận event là bằng chứng compromise; quyết định liên kết phải đến từ analyst hoặc detection workflow được ủy quyền.

~~~~java
import java.time.Instant;
import java.util.Objects;

public record IncidentEventLink(
        String incidentId,
        String eventId,
        String relation,
        String linkedBy,
        Instant linkedAt,
        String rationale
) {
    public IncidentEventLink {
        Objects.requireNonNull(incidentId);
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(relation);
        Objects.requireNonNull(linkedBy);
        Objects.requireNonNull(linkedAt);
        Objects.requireNonNull(rationale);

        if (incidentId.isBlank() || eventId.isBlank()
                || linkedBy.isBlank() || rationale.isBlank()) {
            throw new IllegalArgumentException(
                    "Incident link metadata is incomplete"
            );
        }
    }
}
~~~~

Một event có thể liên quan incident dưới nhiều quan hệ như trigger, context, containment, recovery hoặc evidence. Nên lưu rationale và actor tạo link để analyst sau này hiểu vì sao event được đưa vào case.

Không sửa event gốc để thêm incident ID. Link nên là record riêng, có audit và có thể được cập nhật khi điều tra tiến triển.

## 27. Detection test và incident exercise

Kiểm thử cần chứng minh pipeline giữ được event, tạo đúng correlation và hỗ trợ response.

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Normal decrypt | Workload hợp lệ dùng key trong baseline | Không tạo incident giả |
| Decrypt spike | Usage vượt baseline | Alert có event IDs và key context |
| New role then decrypt | Role mới cấp trước operation bất thường | Correlation phát hiện chuỗi |
| Unauthorized destroy | Destroy không có approval | Critical alert và evidence preservation |
| Secret leak | Secret xuất hiện trong CI log | Alert, issuer revoke workflow và consumer inventory |
| Duplicate event | Source event gửi lại | Deduplicate, không mở incident trùng |
| Late event | Event đến trễ | Timeline cập nhật và giữ event time |
| Clock skew | Source clock lệch | Flag timestamp quality |
| Missing sequence | Collector bỏ sót batch | Ingestion gap alert |
| Parser failure | Schema mới chưa hỗ trợ | Giữ raw event trong quarantine |
| Evidence tampering | Digest không khớp | Integrity alert và bảo toàn bản gốc |
| SIEM outage | Collector không gửi được | Buffer, lag alert và reconciliation |
| Incident link | Analyst gắn event vào case | Link có actor, rationale và timestamp |
| Revoke verification | Credential bị revoke | Operation cũ bị từ chối |
| Key rewrap | KEK compromise response | Wrapped DEK inventory được đối soát |
| False positive | Batch job hợp lệ tăng usage | Analyst có context để đóng alert |
| Break-glass | Emergency action hợp lệ | Có approval, TTL và hậu kiểm |
| Log redaction | Event chứa token test | Token bị loại trước khi lưu |
| Restore exercise | Audit archive được phục hồi | Integrity và provenance vẫn xác minh được |
| Incident closure | Evidence và action đầy đủ | Closure record có findings và residual risk |

Thực hiện tabletop exercise với KMS/HSM, IAM, application, incident response và data owner. Đừng chỉ test rule trên sample JSON; cần test toàn đường từ provider log tới incident timeline và evidence archive.

## 28. Metrics và operational dashboard

Các metric hữu ích:

- Audit event volume theo source và event type.
- Ingestion lag và collector availability.
- Số sequence gap hoặc event parse failure.
- Tỷ lệ event duplicate và late arrival.
- Số key operation theo principal, tenant và key version.
- Số policy change và privileged action.
- Số alert theo rule, severity và false positive rate.
- Mean time to detect (MTTD).
- Mean time to acknowledge/respond (MTTA/MTTR theo định nghĩa tổ chức).
- Thời gian từ alert tới incident creation.
- Thời gian preserve evidence và containment.
- Số incident liên quan key compromise.
- Số credential/key chưa có owner.
- Số key lifecycle operation thiếu correlation ID.
- Số incident thiếu event reference hoặc evidence integrity check.

Dashboard cần cho phép drill-down từ incident tới event, source payload, actor, key version và timeline. Giới hạn quyền truy cập theo role; không hiển thị secret value chỉ để tiện điều tra.

## 29. Tình huống thực tế

### Tình huống A: Decrypt bất thường trên nhiều tenant

SIEM phát hiện một workload mới gọi Decrypt trên key của nhiều tenant trong khoảng thời gian ngắn. Audit KMS cho biết key ID/version và request ID; IAM log cho thấy role vừa được cấp; application log cho biết deployment không có change ticket.

Đội ứng phó mở incident, liên kết các event bằng principal, time range và trace/request IDs. Họ preserve IAM policy snapshot, KMS source events, deployment record và network telemetry. Sau khi xác định credential của workload bị lộ, đội ứng phó revoke identity/session, giới hạn key access, đánh giá ciphertext và phát hành credential mới. Nếu DEK hoặc KEK bị lộ, kế hoạch re-encrypt/rewrap được lập riêng theo dependency.

### Tình huống B: Schedule deletion không có approval

KMS ghi nhận schedule deletion cho KEK production. Detection rule không tìm thấy request ID trong destruction workflow. Incident platform mở critical incident và đính kèm KMS event, actor session, key policy snapshot và dependency graph.

Executor bị chặn qua IAM guardrail; key custodian xác minh provider state và cancel deletion nếu provider còn cho phép. Điều tra cho thấy một role tạm thời đã được cấp ngoài change process. Đội bảo mật thu hồi role, kiểm tra các key khác bị tác động và rà soát mọi policy change cùng session.

### Tình huống C: Secret xuất hiện trong CI artifact

Một pipeline upload artifact chứa environment dump. Secret scanner phát hiện pattern API token. Audit secret manager cho thấy secret version đã được đọc bởi build identity; provider log cho thấy token được dùng từ source IP ngoài runner range.

Incident liên kết pipeline run, artifact digest, secret version, issuer API calls và identity events. Đội vận hành revoke token tại issuer, cập nhật secret manager, redeploy consumer và kiểm tra các request trong khoảng thời gian exposure. Artifact bị cô lập và xử lý theo evidence/retention policy.

### Tình huống D: HSM tamper alarm

HSM phát tamper alarm và chuyển trạng thái theo semantics của thiết bị. Audit event được liên kết với operator login, facility access và key usage gần thời điểm đó. Incident team bảo toàn device log, custody record và access control evidence, đồng thời áp dụng containment theo vendor runbook.

Không tự khởi động lại hoặc tái enroll thiết bị trước khi xác định evidence cần giữ và ảnh hưởng tới key material. Recovery cần phối hợp HSM custodian, security, backup owner và business owner.

## 30. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ thu thập application log | Thiếu bằng chứng provider/IAM | Thu thập nhiều control plane và data plane |
| Dùng một ID cho mọi thứ | Correlation sai | Tách event, request, trace, workflow và incident ID |
| Sắp timeline theo ingest time | Thứ tự sự kiện sai | Dùng event time, observed time và sequence |
| Sửa event gốc khi mở incident | Mất provenance | Tạo incident-event link riêng |
| Log raw secret | Tạo thêm điểm rò rỉ | Redact trước ingest |
| Hash log nhưng không xác thực source | Không chứng minh nguồn gốc | Bảo vệ source, collector và signing key |
| Alert tự destroy key | Mất dữ liệu hoặc gây outage | Approval và playbook có kiểm soát |
| Không xử lý duplicate | Mở incident hoặc chạy action nhiều lần | Idempotency và deduplication |
| Không phát hiện ingestion gap | Điều tra thiếu event | Sequence/checkpoint và gap alert |
| Xem mọi decrypt là compromise | Nhiều false positive | Baseline và business context |
| Không inventory key dependency | Response thiếu phạm vi | Key lineage và dependency graph |
| Đóng incident khi chỉ revoke token | Bỏ sót persistence hoặc data exposure | Verify containment và impact assessment |

## 31. Checklist triển khai

### Audit collection

- [ ] KMS/HSM, IAM, secret manager, PKI và application có audit source rõ ràng.
- [ ] Giữ source event ID và raw payload.
- [ ] Có schema version và event taxonomy.
- [ ] Có event time, observed time và ingest time.
- [ ] Có principal, action, resource ID/version, tenant và outcome.
- [ ] Có request/trace/correlation ID khi nguồn cung cấp.
- [ ] Có monitoring collector lag, duplicate và sequence gap.

### Correlation và incident

- [ ] Correlation ID được propagate qua workflow.
- [ ] Incident record tham chiếu event/evidence IDs.
- [ ] Timeline phân biệt event time và ingest time.
- [ ] Có enrichment từ owner, workload, key inventory và policy version.
- [ ] Detection rule kiểm tra policy change và key usage cùng nhau.
- [ ] Có playbook unauthorized decrypt, key compromise, secret leak và destroy bypass.
- [ ] SIEM/SOAR không tự thực hiện destructive action ngoài policy.

### Evidence và response

- [ ] Log không chứa key material, password, token hoặc plaintext.
- [ ] Evidence có hash/signature/provenance phù hợp.
- [ ] Chain of custody ghi actor, thời gian và transfer.
- [ ] Evidence archive có access control và retention.
- [ ] Containment được xác minh qua negative test.
- [ ] Dependency graph được dùng để đánh giá key compromise.
- [ ] Incident closure có findings, impact, confidence và residual risk.
- [ ] Lessons learned cập nhật policy, inventory và detection.

## 32. Câu hỏi tự kiểm tra

**1. Audit event khác incident thế nào?**

Audit event ghi một hành động; incident là vụ việc được quản lý và điều tra theo quy trình ứng phó.

**2. Alert có chứng minh compromise không?**

Không. Alert là tín hiệu cần triage và xác minh bằng context/evidence.

**3. Vì sao cần source event ID?**

Để truy ngược event gốc và deduplicate khi pipeline gửi lại.

**4. Request ID khác trace ID thế nào?**

Request ID định danh request boundary; trace ID theo dõi luồng phân tán qua nhiều service.

**5. Correlation ID có chứng minh quan hệ nhân quả không?**

Không. Nó giúp nhóm event theo workflow; analyst vẫn cần kiểm tra context và thứ tự.

**6. Incident ID có nên thay correlation ID không?**

Không. Incident có thể chứa nhiều workflow; event có thể được liên kết với nhiều incident.

**7. Vì sao phải giữ event time và ingest time?**

Để xử lý clock skew, late arrival và xác định độ trễ pipeline.

**8. Audit KMS nên ghi những gì?**

Principal, operation, key ID/version, tenant, outcome, request/provider event ID và thời điểm.

**9. Audit có nên ghi plaintext hoặc key bytes để tiện điều tra không?**

Không. Chỉ ghi metadata cần thiết và giữ secret ngoài log.

**10. Hash log có chứng minh nguồn gốc event không?**

Không. Hash chứng minh nội dung khớp digest; cần xác thực source, collector và provenance.

**11. Chain of custody ghi gì?**

Ai thu thập, phương pháp, thời gian, hash, vị trí lưu trữ và các lần bàn giao/truy cập.

**12. Vì sao cần audit IAM policy change cùng KMS usage?**

Policy change có thể mở quyền trước khi principal sử dụng key; correlation giúp nhận ra chuỗi hành động.

**13. Decrypt thành công có chứng minh dữ liệu đã bị exfiltrate không?**

Không. Cần thêm application, storage và network evidence.

**14. Khi phát hiện key compromise, có nên destroy ngay không?**

Không mặc định. Cần containment, preserve evidence, đánh giá dependency và chọn disable/revoke/rekey/rewrap/re-encrypt phù hợp.

**15. Vì sao cần giữ raw event gốc?**

Để kiểm tra parser, provenance và diễn giải khi schema chuẩn hóa thay đổi.

**16. At-least-once delivery có vấn đề gì?**

Event có thể bị gửi trùng; cần deduplication và idempotent incident workflow.

**17. SIEM/SOAR có nên tự destroy key khi có alert không?**

Không nếu chưa có policy, scope và approval rõ ràng; ưu tiên enrichment và preserve evidence tự động.

**18. Khi audit sink ngừng hoạt động, mọi key operation có phải dừng không?**

Không có một câu trả lời chung. Phải xác định operation criticality, durable buffer, risk acceptance và fail-open/fail-closed policy.

**19. Incident closure cần có gì?**

Findings, timeline, impact, evidence references, containment/recovery verification, confidence và residual risk.

**20. Liên kết audit với incident được coi là hiệu quả khi nào?**

Khi analyst truy được event gốc, actor, resource, timeline, dependency và response action có bằng chứng integrity trong một quy trình có thể lặp lại.

## 33. Tài liệu tham khảo

- NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management.
- NIST SP 800-92 — Guide to Computer Security Log Management.
- NIST SP 800-86 — Guide to Integrating Forensic Techniques into Incident Response.
- NIST SP 800-53 Rev. 5 — Security and Privacy Controls, đặc biệt nhóm Audit and Accountability (AU) và Incident Response (IR).
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management.
- RFC 5424 — The Syslog Protocol.
- W3C Trace Context — chuẩn truyền trace context trong distributed systems.
- Tài liệu audit logging, key lifecycle, IAM và incident response của KMS/HSM/secret manager đang triển khai.
- Chính sách nội bộ về evidence retention, privacy, legal hold, incident severity và chain of custody.

