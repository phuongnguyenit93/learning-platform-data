# Chuẩn hóa hợp đồng ứng dụng và các phần cần khả năng di chuyển

Kiến trúc hybrid cloud và multi-cloud thường bắt đầu từ một nhu cầu thực tế: một số workload phải ở datacenter riêng, một số chạy trên public cloud, hoặc tổ chức muốn có khả năng chuyển dịch vụ giữa nhà cung cấp theo yêu cầu về chi phí, địa lý, tuân thủ và độ tin cậy. Nhưng việc triển khai cùng một ứng dụng ở hai môi trường không tự tạo ra tính di động. API, schema, identity, storage, messaging, observability và quy trình vận hành có thể dùng semantics khác nhau dù tên dịch vụ trông giống nhau.

**Chuẩn hóa hợp đồng ứng dụng** là xác định giao diện, semantics, dữ liệu và hành vi mà các thành phần phải tuân thủ để có thể tương tác độc lập với nơi triển khai. **Khả năng di chuyển (portability)** là mức độ một workload hoặc thành phần có thể được build, triển khai, vận hành và chuyển đổi sang môi trường khác với thay đổi có kiểm soát. Không phải mọi thành phần đều cần portable tuyệt đối. Mục tiêu là xác định ranh giới: phần nào nên dùng contract chung, phần nào được phép tận dụng dịch vụ đặc thù, và adapter/anti-corruption layer nào bảo vệ domain khỏi khác biệt nền tảng.

Bài học thuộc chương **Đám mây lai và đa đám mây** của lộ trình **Cloud Architecture**. Lộ trình hướng dẫn thiết kế kiến trúc ứng dụng cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Bài này tập trung vào việc chuẩn hóa hợp đồng có giá trị, lựa chọn portability boundary và quản lý thay đổi khi workload chạy trên nhiều nền tảng.

Sau bài học, bạn có thể:

- Phân biệt portability của source, artifact, runtime, data, operation và business contract.
- Xác định application contract ổn định cho API, event, schema và error semantics.
- Chọn chuẩn mở và protocol chung ở ranh giới tích hợp.
- Thiết kế adapter/port để cô lập service đặc thù của nhà cung cấp.
- Phân biệt abstraction hữu ích với lowest-common-denominator platform.
- Đánh giá portability của compute, storage, identity, messaging và observability.
- Quản lý schema/version compatibility và contract testing.
- Lập kế hoạch data migration, cutover, rollback và dual-run.
- Đo mức độ lock-in, chi phí chuyển đổi và operational readiness.

## 1. Portability không chỉ là chạy cùng container

Một container image có thể chạy trên nhiều Kubernetes cluster, nhưng ứng dụng vẫn có thể phụ thuộc vào managed database, object storage API, identity provider, message service, KMS, DNS, load balancer và dịch vụ observability riêng của nhà cung cấp. Khi chuyển runtime, những dependency đó có thể cần thay thế hoặc migration.

Nên đánh giá portability theo nhiều lớp:

| Lớp | Câu hỏi |
| --- | --- |
| Source code | Có phụ thuộc SDK/API độc quyền trong domain logic không? |
| Build artifact | Có thể build từ cùng source và pin dependency không? |
| Runtime | Có yêu cầu OS, kernel, architecture hoặc orchestrator cụ thể không? |
| Configuration | Có contract và mapping giữa môi trường không? |
| Identity/security | Có thể ánh xạ workload identity, role và policy sang nền tảng khác không? |
| Data | Schema, export/import, consistency và encryption key có chuyển được không? |
| Integration | API, event, queue và protocol có contract độc lập provider không? |
| Operations | Logging, metrics, tracing, deployment và incident workflow có tương đương không? |
| Governance | Policy, audit, residency và control evidence có được duy trì không? |

Portability chỉ ở tầng compute có thể không đủ để chuyển workload nếu dữ liệu và integration không thể di chuyển trong RTO/RPO cho phép.

## 2. Xác định mục tiêu di động trước khi chuẩn hóa

Multi-cloud không phải mục tiêu tự thân. Cần xác định lý do cần portability:

- **Exit strategy:** có thể rời provider nếu giá, hợp đồng hoặc dịch vụ thay đổi.
- **Regulatory/data residency:** triển khai một phần workload ở vị trí được phép.
- **Resilience:** có recovery location khác khi provider/region gặp sự cố.
- **Acquisition or divestiture:** tách workload sang account/organization khác.
- **Hybrid integration:** kết nối datacenter/on-premises với public cloud.
- **Workload placement:** chọn nơi chạy phù hợp latency, GPU, data gravity hoặc cost.
- **Vendor negotiation:** giảm phụ thuộc bằng khả năng chuyển đổi thực tế.

Mục tiêu khác nhau dẫn tới mức portability khác nhau. Disaster recovery đa vùng có thể cần backup/restore và redeploy, không nhất thiết chạy active-active trên hai cloud. Exit strategy có thể cần export dữ liệu và tái triển khai trong vài tháng, không cần abstraction mọi dịch vụ ngay từ đầu.

## 3. Application contract là ranh giới ổn định

Một contract tốt mô tả hành vi mà consumer có thể dựa vào, thay vì mô tả cách provider triển khai nội bộ.

Một application contract thường bao gồm:

- Operation, resource và payload.
- Request/response schema hoặc event schema.
- Authentication và authorization expectations.
- Error model và retryability.
- Timeout/deadline và cancellation.
- Idempotency, ordering và consistency.
- Pagination, filtering và rate limits.
- Versioning và compatibility policy.
- Data classification và retention.
- SLO, availability và support expectations.

Contract phải đủ cụ thể để hai implementation khác nhau vẫn có thể được thay thế mà consumer không cần hiểu provider.

## 4. Chuẩn hóa API contract

Với HTTP API, có thể chuẩn hóa resource semantics, method, status code, pagination, error envelope, idempotency và trace context. OpenAPI là một cách mô tả contract để generate client/server, validate và review breaking change.

Ví dụ một error envelope:

~~~json
{
  "type": "https://api.example.com/errors/version-conflict",
  "title": "Resource version conflict",
  "status": 409,
  "code": "VERSION_CONFLICT",
  "correlationId": "corr-82a1",
  "retryable": false
}
~~~

Consumer nên dựa vào status/code và semantics đã công bố, không parse message tự do hoặc phụ thuộc tên exception của provider. Tránh trả raw provider error vì nó có thể làm lộ thông tin nội bộ và buộc client gắn với implementation cụ thể.

### 4.1. Chuẩn hóa error semantics

Hai database hoặc queue có thể trả lỗi khác nhau cho cùng một tình huống. Adapter cần map lỗi sang domain/application error ổn định:

| Tình huống | Contract ứng dụng |
| --- | --- |
| Resource không tồn tại | NOT_FOUND |
| Version không khớp | CONFLICT |
| Caller thiếu quyền | FORBIDDEN |
| Quá quota | RATE_LIMITED hoặc QUOTA_EXCEEDED |
| Dependency tạm thời không khả dụng | UNAVAILABLE, có thể retry theo policy |
| Payload sai schema | INVALID_ARGUMENT |
| Kết quả commit chưa xác định | UNKNOWN_OUTCOME, cần query/reconcile |

Không map mọi lỗi provider thành 500 rồi retry vô hạn. Semantics retryable và unknown outcome ảnh hưởng trực tiếp correctness.

## 5. Schema và version compatibility

API/event contract sống lâu hơn một lần deploy. Producer và consumer có thể được nâng cấp lệch thời điểm; multi-cloud còn có thể có nhiều release channel. Cần quản lý backward/forward compatibility.

Các nguyên tắc thường dùng:

- Ưu tiên additive change: thêm optional field thay vì đổi ý nghĩa field.
- Không tái sử dụng field cũ cho ý nghĩa mới.
- Consumer bỏ qua field chưa biết khi schema contract cho phép.
- Không làm field optional thành required trong minor version.
- Dùng explicit enum evolution policy.
- Version event/schema độc lập với application build.
- Có deprecation window, owner và migration date.
- Contract test giữa producer/consumer.
- Lưu schema registry/contract artifact có version và audit.

### 5.1. Expand–migrate–contract

1. Expand: thêm field/schema mới vẫn tương thích.
2. Deploy consumer có thể đọc cả dạng cũ và mới.
3. Deploy producer bắt đầu phát field mới.
4. Backfill dữ liệu hoặc replay event nếu cần.
5. Đo consumer legacy và xác nhận đã chuyển.
6. Contract: loại bỏ field cũ sau thời hạn và xác minh.

Đối với migration giữa provider, giai đoạn dual-read/dual-write có thể giúp chuyển dần nhưng cần giải quyết ordering, duplicate và source of truth.

## 6. Event contract và messaging portability

Message broker khác nhau về partitioning, ordering, retention, transaction, delivery guarantee, consumer group, acknowledgement và schema integration. Một abstraction chỉ có hàm publish/subscribe là chưa đủ nếu nó che mất semantics quan trọng.

Contract event nên xác định:

- Event ID, type, source và schema version.
- Aggregate/business key và partitioning expectation.
- Correlation/causation context.
- Ordering scope.
- Delivery semantics và duplicate handling.
- Retention/replay expectation.
- Dead-letter behavior.
- Payload size và throughput limits.
- Security identity, encryption và tenant context.

### 6.1. Portability theo semantics

Ví dụ ứng dụng cần thứ tự event theo booking ID. Một implementation có thể dùng partition key, implementation khác dùng subject/session. Adapter phải đảm bảo consumer nhận đúng ordering scope đã cam kết. Nếu một provider chỉ bảo đảm ordering trong partition, contract không thể hứa global ordering nếu hệ thống không có thêm coordination.

Không nên viết contract “exactly once” chung chung. Phải mô tả exactly-once effect ở boundary nào, transaction nào được bao phủ và side effect ngoài broker được xử lý ra sao.

## 7. Data contract và portability của database

Database portability không chỉ là chuyển schema SQL. Các engine khác nhau có semantics về transaction isolation, JSON, collation, sequence, locking, index, stored procedure, generated column và query planner.

Data contract cần quy định:

- Entity/aggregate ownership.
- Schema và field meaning.
- Primary/business key.
- Nullability và constraints.
- Transaction boundary và isolation requirement.
- Ordering/version semantics.
- Timestamp/time zone and precision.
- Decimal/currency precision.
- Retention, deletion và export format.
- Encryption, key management và residency.

### 7.1. Tránh phụ thuộc ngầm vào engine

Nếu domain logic dựa vào một stored procedure hoặc vendor-specific query, việc chuyển engine có thể đòi hỏi viết lại logic. Điều đó không luôn sai; stored procedure có thể là lựa chọn tốt vì performance và correctness. Nhưng dependency nên được ghi nhận như provider-specific boundary thay vì giả định SQL tiêu chuẩn là portable.

### 7.2. Data export/import contract

Định dạng export phải xác định encoding, schema version, ordering, checkpoint, checksum, encryption, metadata và cách resume. CSV không tự bảo đảm kiểu dữ liệu, null semantics hoặc timezone. Với migration lớn, cần snapshot cộng CDC/log replay hoặc chiến lược tương đương.

## 8. Identity contract và authorization mapping

IAM model giữa cloud provider, Kubernetes, on-premises directory và SaaS identity khác nhau. Application nên sử dụng identity abstraction có ý nghĩa nghiệp vụ: principal, subject, tenant, role/permission, audience và authorization decision.

Không cố ép tất cả policy vào một common role string nếu semantics khác nhau. Một contract có thể mô tả:

- Workload identity được xác thực bằng cơ chế platform.
- Principal subject/audience có định dạng đã công bố.
- Authorization dựa trên application permission/resource.
- Tenant scope được xác thực từ nguồn tin cậy.
- Token lifetime, refresh và revocation behavior.
- Audit fields và policy decision.

Adapter ánh xạ cloud role/service account tới application principal. Không để application tin trực tiếp claim do caller tự gửi mà chưa xác minh issuer/signature/audience.

## 9. Secret, KMS và certificate portability

Mỗi provider có secret manager, KMS và certificate service với API/policy khác nhau. Cần chuẩn hóa hành vi cần thiết thay vì trừu tượng mọi thao tác cryptographic.

Một secret port có thể cung cấp get/version/rotate metadata, nhưng không nên trả về danh sách mọi secret cho application. KMS port có thể cung cấp encrypt/decrypt/wrap/unwrap theo key reference. Việc export key material có thể bị cấm bởi policy hoặc HSM boundary; migration có thể cần re-encryption thay vì copy key.

Cần xác định:

- Key ownership và key custody.
- Algorithm/key size/usage.
- Envelope encryption format.
- Key ID/version metadata trong ciphertext.
- Rotation và decrypt retention.
- Certificate trust chain và renewal.
- Workload identity để truy cập.
- DR/key availability và residency.

Portability không được làm yếu security. Nếu một provider hỗ trợ HSM policy hoặc customer-managed key mà provider khác không có mức bảo vệ tương đương, phải coi đó là capability gap và quyết định có chấp nhận hay không.

## 10. Object storage contract

Object storage API có thể trông giống nhau nhưng khác về consistency, versioning, multipart upload, lifecycle, ACL/IAM, event notification, retention lock, metadata và error semantics.

Một storage port nên mô tả nghiệp vụ:

- Put/get object với key và content metadata.
- Conditional write/version check.
- Multipart upload nếu cần.
- Range read.
- Object version/retention policy.
- Delete semantics và legal hold.
- Encryption/key reference.
- Lifecycle tiering.
- Event notification contract.
- Checksum và integrity validation.

Không đưa bucket name hoặc provider ARN vào domain model nếu chỉ cần logical storage location. Có thể map logical container/object key sang provider resource ở adapter/config layer.

## 11. Compute và runtime portability

VM, container, Kubernetes, serverless function và managed application platform có mức portability khác nhau.

| Mô hình | Tính di động | Dependency thường gặp |
| --- | --- | --- |
| Container OCI | Tương đối cao nếu image portable | Kernel/architecture, runtime, network, storage và secret integration |
| Kubernetes workload | Cao hơn trong ecosystem Kubernetes | API version, CRD, CNI/CSI, ingress, identity và policy |
| VM image | Phụ thuộc format/driver/hypervisor | Boot mode, device driver, licensing và cloud-init |
| Serverless function | Thường phụ thuộc provider hơn | Event source, IAM, timeout/runtime, deployment package |
| Managed application platform | Phụ thuộc platform | Scaling, routing, buildpack, config và add-on |

Chọn runtime theo lợi ích thực tế. Không nên chuyển mọi workload sang Kubernetes chỉ để có vẻ portable nếu team chưa có năng lực vận hành cluster và các workload phù hợp hơn với managed service.

## 12. Platform capability matrix

Trước khi chuẩn hóa, lập matrix so sánh capability giữa các môi trường. Không chỉ so tên dịch vụ.

| Capability | Provider/on-prem A | Provider B | Contract ứng dụng |
| --- | --- | --- | --- |
| Container runtime | Kubernetes | Managed Kubernetes | OCI image, health/port/resource contract |
| Object storage | S3-compatible | Native object API | Logical object store contract + adapter |
| Queue | Managed queue | Kafka-like broker | Event delivery/ordering contract |
| Database | PostgreSQL-compatible | Managed relational engine | SQL feature subset + migration test |
| Identity | Cloud IAM | Federated IAM | Workload principal + app authorization |
| Secrets | Vault | Native secret manager | Secret reference/access lifecycle |
| Observability | OpenTelemetry collector | Native monitoring | OTLP/resource attributes + SLO contract |
| KMS | HSM-backed KMS | Managed KMS | Envelope encryption metadata and rotation |

S3-compatible không đồng nghĩa mọi S3 API/feature giống nhau. PostgreSQL-compatible không đồng nghĩa extension, replication và planner semantics giống hệt. Matrix cần ghi version, quota, SLA, limitation và operational ownership.

## 13. Ports and adapters / hexagonal architecture

Ports and adapters giúp domain/application logic phụ thuộc vào interface do ứng dụng định nghĩa. Adapter triển khai interface bằng database, queue, object storage hoặc identity cụ thể.

~~~mermaid
flowchart TB
    API["HTTP / Event entry adapters"] --> APP["Application use cases"]
    APP --> D["Domain model"]
    APP --> P1["Storage port"]
    APP --> P2["Message port"]
    APP --> P3["Identity port"]
    A1["Provider A adapter"] --> P1
    A2["Provider B adapter"] --> P1
    B1["Queue adapter A"] --> P2
    B2["Queue adapter B"] --> P2
    I1["IAM adapter A"] --> P3
    I2["IAM adapter B"] --> P3
~~~

Port nên thể hiện nhu cầu thật của use case. Ví dụ BookingRepository có contract cho reserve/confirm/cancel với version semantics; đừng tạo một generic database interface gồm hàng trăm method tương ứng mọi feature của từng engine.

### 13.1. Anti-corruption layer

Khi tích hợp legacy/on-premises hoặc provider-specific API, anti-corruption layer chuyển đổi model, errors và semantics sang domain contract. Lớp này ngăn model bên ngoài lan vào core application.

Adapter không nên chỉ đổi tên method. Nó phải đảm bảo behavioral contract: timeout, retry, consistency, partial failure, idempotency và error mapping.

## 14. Chuẩn mở và giao thức chung

Chuẩn mở có thể giảm chi phí tích hợp và tăng khả năng thay thế, nhưng cần xem xét mức mature và feature coverage.

Ví dụ:

- HTTP/REST, gRPC và OpenAPI cho API.
- W3C Trace Context và OpenTelemetry cho tracing/telemetry.
- OCI image format cho container artifacts.
- Kubernetes API cho orchestration nơi phù hợp.
- CloudEvents hoặc schema-defined event envelope cho event metadata.
- SQL/standard data formats như Parquet/Avro/JSON theo use case.
- OIDC/OAuth 2.0 và SAML cho identity federation.
- Terraform/OpenTofu hoặc chuẩn IaC phù hợp cho provisioning.

Chuẩn không tự đảm bảo interoperability. Hai implementation có thể khác version, extension, default hoặc semantics. Cần conformance tests và documented profile/subset.

## 15. Abstraction đúng mức

Một abstraction tốt ẩn sự khác biệt không có ý nghĩa với consumer nhưng vẫn cho phép tận dụng capability cần thiết. Một abstraction quá rộng có thể trở thành lowest common denominator, làm mất tính năng quan trọng và tạo thêm lớp phức tạp.

Có thể dùng ba mức:

1. **Direct provider API:** chấp nhận lock-in có chủ đích khi service đem lại lợi ích lớn.
2. **Application port + adapter:** domain cần một tập operation hẹp, adapter ánh xạ sang provider.
3. **Portable platform contract:** dùng cho nhiều workload/teams cần cùng semantics và có thể kiểm chứng.

Đừng tạo một abstraction chung chỉ vì muốn mọi service “giống nhau”. Nếu provider-native service tạo lợi ích rất lớn và migration không phải mục tiêu thực tế, dùng trực tiếp với exit plan có thể hợp lý hơn.

## 16. Những phần nên và không nên portable

| Thành phần | Hướng thiết kế thường hợp lý | Lý do |
| --- | --- | --- |
| Domain rules | Portable ở core application | Không nên phụ thuộc cloud SDK |
| API/event contract | Chuẩn hóa | Nhiều consumer/provider cần tương tác |
| Container artifact | Portable khi workload phù hợp | Dễ chuyển runtime |
| Observability fields | Chuẩn hóa | Correlate và chuyển công cụ |
| Secret values | Không chia sẻ xuyên environment | Cần scope và custody riêng |
| Data store implementation | Có thể provider-specific | Consistency/performance khác nhau |
| KMS/HSM | Có thể native với migration strategy | Bảo vệ key là capability nhạy cảm |
| Analytics/AI managed services | Có thể provider-specific | Capability/price thay đổi nhanh |
| Deployment workflow | Chuẩn hóa interface, adapter riêng | Các API cloud khác nhau |
| Business workflow state | Portable qua data contract | Cần khả năng recovery/migration |

Portability nên được chọn theo business value, không phải theo số lượng interface trừu tượng.

## 17. Kiểm thử contract và conformance

Một API contract test xác minh provider/adapter mới tuân cùng hành vi consumer mong đợi. Consumer-driven contract testing hữu ích khi producer và consumer deploy độc lập.

Các loại test:

- Schema validation và compatibility test.
- API behavior/status/error contract.
- Idempotency/retry/timeout behavior.
- Ordering và duplicate message semantics.
- Transaction isolation và concurrency.
- Object storage consistency/versioning/conditional writes.
- Identity claim/policy mapping.
- Encryption/decryption và key rotation compatibility.
- Observability propagation và audit fields.
- Performance/quota/load limits.
- Disaster recovery/export/import.

### 17.1. Golden conformance suite

Duy trì một bộ test chạy trên mọi adapter/provider candidate. Test phải kiểm tra cả thành công lẫn edge cases: timeout sau commit, duplicate event, stale version, permission denied, quota exceeded, partial batch failure và reconnect sau network partition.

Một adapter chỉ được coi là tương thích khi vượt conformance suite ở version/profile đã công bố.

## 18. Version hóa adapter và capability discovery

Provider capability thay đổi theo region, plan và version. Không chỉ kiểm tra provider name; cần capability discovery ở thời điểm provision/deploy.

Một capability record có thể chứa:

~~~yaml
platform:
  name: provider-b
  region: region-2
  profileVersion: 3
capabilities:
  objectVersioning: true
  conditionalWrite: true
  orderedMessagesByKey: true
  transactionalOutbox: false
  customerManagedKey: true
limits:
  maxMessageBytes: 1048576
  maxBatchItems: 100
~~~

Đây là ví dụ minh họa; thông số cần được xác minh từ platform thực. Application phải chọn behavior theo capability contract, không tự giả định feature có mặt ở mọi region.

## 19. Data portability và migration

Data thường là phần khó di chuyển nhất vì khối lượng lớn, dependency, consistency, downtime và chi phí egress.

Các phương pháp:

- **Offline migration:** dừng ghi, export, import, validate rồi cutover; đơn giản nhưng downtime dài.
- **Snapshot + delta/CDC:** copy baseline rồi replay thay đổi; giảm downtime nhưng tăng complexity.
- **Dual-write:** ghi cả hai nơi trong giai đoạn chuyển; cần xử lý partial success và ordering.
- **Read shadowing:** gửi read tới hệ thống mới để so sánh nhưng chỉ trả kết quả từ nguồn chính.
- **Progressive tenant migration:** chuyển từng tenant/partition theo cohort.
- **Rebuild derived data:** tái tạo search/cache/analytics từ source of truth thay vì migrate mọi index.

### 19.1. Data migration sequence

1. Inventory dataset, owner, volume, sensitivity và residency.
2. Định nghĩa schema mapping, type conversion và invariants.
3. Chọn snapshot/export và encryption transfer.
4. Chuyển baseline data.
5. Bắt CDC/log delta hoặc pause writes theo window.
6. Import/replay và kiểm tra lag.
7. Compare row counts, checksum và business aggregates.
8. Chạy application conformance/synthetic transactions.
9. Cutover reader/writer với fencing và version.
10. Theo dõi discrepancy và rollback window.
11. Retire old system sau retention/approval.

Không xóa nguồn cũ ngay khi DNS hoặc routing đã đổi. Giữ read-only hoặc backup đủ thời gian để điều tra và phục hồi.

## 20. Dual-run, shadow traffic và cutover

Trước khi chuyển traffic, có thể chạy application mới ở chế độ shadow: nhận bản sao request/read nhưng không thực hiện side effect. So sánh response, latency và error semantics.

Với write path, shadow phải tránh ghi thật hoặc tạo payment/email/job trùng. Có thể chạy validation ở read-only mode, synthetic tenant hoặc isolated test environment.

Cutover cần:

- Freeze/coordinate schema changes.
- Xác định write authority.
- Drain inflight request.
- Chốt CDC checkpoint.
- Fencing writer cũ.
- Chuyển routing và identity.
- Verify data and business invariants.
- Theo dõi rollback criteria.

Rollback sau khi hệ thống mới đã nhận write không thể chỉ đổi DNS về nguồn cũ. Phải có reverse replication, reconciliation hoặc quyết định giữ platform mới làm source of truth.

## 21. Configuration và deployment portability

Không hardcode provider resource ID, ARN, project name hoặc endpoint vào domain logic. Dùng logical configuration key và provider-specific mapping trong deployment layer.

Tuy vậy, config contract phải mô tả các khác biệt ảnh hưởng behavior: storage consistency, queue ordering, KMS key access, network timeout, autoscaling limit và service quota.

IaC module có thể dùng interface chung cho resource phổ biến nhưng cần extension point và capability flags. Không cố ép provider-specific feature vào một boolean chung nếu semantics khác.

### 21.1. Artifact promotion

Build artifact một lần, ký và promote cùng digest qua dev/staging/production hoặc qua môi trường khác khi compatibility cho phép. Không rebuild artifact khác nhau cho từng provider mà không truy vết provenance. Config và secret được inject riêng cho từng environment.

## 22. Observability và vận hành đa nền tảng

Khi workload chạy trên nhiều provider, metrics/logs/traces dễ khác schema và naming. Chuẩn hóa resource attributes, service identity, region/environment, trace context, error taxonomy và SLO giúp so sánh.

Những phần cần contract:

- Service name/version/environment.
- Region/provider/cluster attributes.
- Log severity và structured fields.
- Trace propagation và sampling policy.
- Metric naming/unit/temporality.
- SLO/error budget semantics.
- Alert ownership/escalation.
- Audit trail và retention.
- Incident ID/correlation ID.

OpenTelemetry có thể cung cấp một lớp instrumentation/transport chuẩn, nhưng exporter/backend vẫn có thể khác nhau. Cần kiểm tra sampling, cardinality, cost và data residency.

## 23. Security, policy và compliance portability

Policy chung nên diễn đạt control objective, còn adapter/platform policy map sang enforcement point cụ thể.

Ví dụ control objective “storage object phải được mã hóa bằng key do tổ chức kiểm soát” có thể được thực hiện bằng nhiều KMS/object storage API khác nhau. Conformance test cần chứng minh encryption thực sự bật, key owner đúng, audit tồn tại và cross-region copy tuân policy.

Không nên chỉ kiểm tra tên option trong IaC. Kiểm chứng actual state, effective policy, identity permission và audit evidence. Multi-cloud cũng không làm mất trách nhiệm phân loại dữ liệu, xử lý yêu cầu xóa, residency và access review.

## 24. Đo lock-in và portability risk

Lock-in không phải thuộc tính nhị phân. Có thể đánh giá theo:

- Số lượng API/provider-specific dependency trong domain code.
- Số lượng adapter cần thay.
- Dữ liệu cần export và thời gian chuyển.
- Khả năng tái tạo infra từ IaC ở môi trường khác.
- Compatibility gap của database/queue/object storage.
- Key custody và crypto migration constraints.
- Network egress và data transfer cost.
- Số quy trình vận hành phải viết lại.
- Vendor-specific skill và support dependency.
- Thời gian đạt production readiness sau chuyển đổi.

Có thể dùng portability tier:

| Tier | Mô tả | Ví dụ |
| --- | --- | --- |
| P0: Native | Dùng trực tiếp dịch vụ provider, không có exit abstraction | Managed AI/service đặc thù |
| P1: Adaptable | Có adapter hoặc export path đã biết | Storage/queue qua application port |
| P2: Portable | Contract và artifact có thể chạy ở nhiều nền tảng đã test | OCI workload + open API |
| P3: Proven portable | Đã diễn tập chuyển đổi end-to-end trong RTO/RPO mục tiêu | Workload/data đã migrate thử |

Không tuyên bố P3 dựa trên kiến trúc trên giấy; cần bằng chứng migration drill.

## 25. Ví dụ: booking platform hybrid và multi-cloud

Một nền tảng SaaS có core booking chạy trên public cloud, thiết bị tại kho chạy trong datacenter/on-premises và analytics tại một cloud khác. Mục tiêu là có thể chuyển booking service nếu provider hiện tại tăng giá hoặc region gặp sự cố, nhưng payment và inventory cần consistency rõ.

### 25.1. Ranh giới contract

- Booking domain có API contract và event schema độc lập provider.
- Inventory adapter kết nối hệ thống on-prem qua API/event gateway.
- Database implementation được cô lập sau repository/domain boundary, nhưng transaction semantics và migration constraints được ghi rõ.
- Object storage dùng logical document port; adapter map metadata/versioning/retention.
- Identity federates workload identity, còn application authorization dùng permission model của domain.
- Observability fields chuẩn hóa theo OpenTelemetry và structured logging.
- Payment provider integration giữ adapter riêng do idempotency, webhook và reconciliation semantics.

~~~mermaid
flowchart TB
    API["Booking API contract"] --> APP["Booking application/domain"]
    APP --> DBP["Repository port"]
    APP --> INV["Inventory port"]
    APP --> DOC["Document storage port"]
    APP --> PAY["Payment port"]
    DBP --> DBA["Cloud A database adapter"]
    DBP --> DBB["Cloud B database adapter"]
    INV --> ONP["On-prem inventory adapter"]
    DOC --> OA["Object store adapter A"]
    DOC --> OB["Object store adapter B"]
    PAY --> PSP["Payment provider adapter"]
~~~

### 25.2. Migration sequence

1. Tách provider SDK khỏi domain logic và tạo adapter cho database/storage/identity.
2. Xây conformance suite cho contract và error semantics.
3. Dựng platform đích bằng IaC và workload identity riêng.
4. Copy baseline data, bật CDC và verify schema/invariants.
5. Chạy shadow read và synthetic booking không tạo side effect thật.
6. Đo latency, quota, consistency và operational capability.
7. Chuyển tenant/cohort nhỏ, giữ write authority duy nhất.
8. Mở rộng cutover sau khi reconciliation đạt.
9. Giữ hệ thống cũ read-only trong rollback window.
10. Chỉ retire khi backup, retention, audit và support sign-off đủ.

### 25.3. Trade-offs

- Dùng database native có thể tối ưu performance nhưng tăng migration work.
- Dùng open protocol có thể giảm adapter cost nhưng không đồng nhất transaction semantics.
- Multi-cloud active-active write có thể tăng availability nhưng khó bảo đảm booking/inventory invariants.
- Hybrid on-prem integration giảm latency tới thiết bị cục bộ nhưng tăng network/security operations.
- Chuẩn hóa observability giảm switching cost nhưng telemetry pipeline vẫn cần provider-specific tuning.

## 26. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Mục tiêu là “portable everywhere” | Abstraction quá rộng, mất capability | Gắn portability với business objective |
| Dùng cùng container rồi tuyên bố portable | Data/identity/queue vẫn lock-in | Đánh giá mọi lớp dependency |
| Common interface quá thấp mẫu số | Không thể dùng semantics quan trọng | Port theo use case và explicit capability |
| Ẩn transaction semantics trong adapter | Duplicate/lost update khi đổi provider | Contract consistency/idempotency rõ |
| Dùng SQL chuẩn nhưng phụ thuộc extension | Migration thất bại hoặc behavior đổi | Feature inventory và conformance test |
| Giả định S3-compatible giống nhau | Versioning/consistency/ACL khác | Test exact API profile |
| Replicate mọi dữ liệu toàn cầu | Tăng cost và vi phạm residency | Data classification và placement policy |
| Dual-write không có reconciliation | Hai nguồn dữ liệu lệch nhau | Outbox/CDC, idempotency và authority |
| Cutover chỉ đổi DNS | Writer cũ và inflight session tiếp tục hoạt động | Fencing, drain và data checkpoint |
| Rollback không xét write mới | Mất dữ liệu sau cutback | Reverse sync/reconcile hoặc forward recovery |
| Provider error được trả nguyên cho client | Consumer phụ thuộc provider | Error mapping và stable contract |
| Bỏ qua quota/limit | Adapter tương thích nhưng workload không chịu tải | Capability/limit matrix và load test |
| Không kiểm thử identity mapping | Quyền quá rộng hoặc request bị từ chối | Principal/policy conformance |
| Chuẩn hóa observability chỉ ở tên field | Sampling/metric unit/retention khác nhau | Telemetry contract và dashboard test |
| Đo portability bằng số adapter | Không phản ánh thời gian chuyển thực tế | Migration drill và portability tier |
| Không tính egress và data gravity | Exit plan quá đắt hoặc không khả thi | Cost model và data transfer rehearsal |

## 27. Quy trình chuẩn hóa và triển khai

1. **Xác định động lực portability:** exit, DR, residency, hybrid, latency hay workload placement.
2. **Lập dependency inventory:** SDK, API, database, queue, storage, identity, KMS, observability và operations.
3. **Phân loại dependency:** portable, adaptable, provider-native hoặc không thể di chuyển theo policy.
4. **Xác định contract:** API, event, schema, error, identity, storage và SLO.
5. **Định nghĩa capability profile:** version, quota, consistency, ordering, retention và limitation từng platform.
6. **Thiết kế ports/adapters:** giữ domain logic độc lập nhưng không che semantics quan trọng.
7. **Chuẩn hóa artifact/config:** pin image digest, schema, config contract và secret reference.
8. **Tạo conformance suite:** chạy cùng test trên mọi adapter/platform candidate.
9. **Thiết kế data migration:** snapshot, CDC, reconciliation, authority và cutover.
10. **Thiết kế security/operations:** identity, KMS, residency, observability, audit và on-call.
11. **Benchmark và cost model:** latency, throughput, egress, support effort và quota.
12. **Diễn tập migration/exit:** chuyển một workload/tenant end-to-end và đo thời gian.
13. **Review định kỳ:** provider API change, deprecation, lock-in risk và capability gap.

## 28. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Contract có định nghĩa timeout, retry, idempotency và consistency? Có thể chuyển platform, phục hồi data và rollback trong mục tiêu? |
| **Bảo mật** | Identity, key custody, residency, audit và secret scope có giữ nguyên khi chuyển? Adapter có kiểm tra tenant authorization? |
| **Hiệu quả hiệu năng** | Abstraction có thêm latency? Provider-specific capability có bị mất? Cross-cloud network/data transfer có nằm trong SLO? |
| **Tối ưu chi phí** | Portability layer có đáng với chi phí vận hành? Egress, dual-run, duplicate capacity và adapter maintenance đã được tính? |
| **Khả năng vận hành** | Có capability matrix, conformance test, dependency inventory, runbook, owner và migration drill? |

### Checklist nghiệm thu

- [ ] Mục tiêu portability và workload scope được xác định theo business value.
- [ ] Dependency inventory bao gồm runtime, data, identity, secrets, messaging và operations.
- [ ] API/event/error contracts có version và compatibility policy.
- [ ] Retry, timeout, idempotency, ordering và consistency semantics được công bố.
- [ ] Data contract xác định schema, precision, timezone, transaction và retention.
- [ ] Provider-specific code nằm sau adapter hoặc được ghi nhận rõ như native dependency.
- [ ] Abstraction giữ capability cần thiết và không che semantics quan trọng.
- [ ] Capability matrix có version, quota, limitation và regional support.
- [ ] Identity/KMS/certificate migration không làm yếu security hoặc key custody.
- [ ] Artifact provenance, config contract và secret reference được quản lý riêng.
- [ ] State/data export có encryption, checksum, schema version và resume capability.
- [ ] Contract/conformance test chạy trên mọi implementation được hỗ trợ.
- [ ] Shadow/dual-run không tạo side effect trùng.
- [ ] Cutover có checkpoint, writer fencing, reconciliation và rollback criteria.
- [ ] Data residency bao gồm replica, backup, log và telemetry.
- [ ] Egress, dual-run, support và operational cost được tính.
- [ ] Có migration drill chứng minh portability tier đã công bố.

## 29. Bài tập áp dụng

Một doanh nghiệp vận hành nền tảng booking trên Cloud A. Ứng dụng dùng managed relational database, object storage, managed queue, provider IAM và dịch vụ observability native. Một bộ phận có dữ liệu phải nằm tại datacenter nội bộ; ban lãnh đạo muốn có exit option sang Cloud B trong vòng sáu tháng. Booking và payment cần idempotency/ordering rõ, document archive có retention dài, còn analytics có thể rebuild.

Hãy thiết kế:

1. Dependency inventory nào cần tạo và phân loại portable/adaptable/native?
2. Application/API/event contract nào phải chuẩn hóa trước?
3. Database semantics nào có thể cản trở chuyển engine?
4. Queue ordering, redelivery và transaction semantics được map thế nào?
5. Thiết kế object storage port nhưng vẫn giữ versioning, retention và encryption.
6. Identity/KMS/certificate có thể federate hoặc migrate bằng cách nào?
7. Adapter nào nên được xây và adapter nào không đáng abstraction?
8. Data migration dùng snapshot, CDC, dual-run hay progressive tenant cutover?
9. Làm sao đảm bảo không có hai writer và không mất booking/payment trong cutover?
10. Conformance suite, cost model và migration drill nào chứng minh exit option thực tế?

Một phương án có cơ sở sẽ chuẩn hóa API/event/error/data contract và telemetry trước; giữ domain logic độc lập qua ports có phạm vi hẹp; sử dụng adapter cho queue/storage/identity; ghi nhận database feature gap thay vì giả định SQL portable; và thực hiện snapshot+CDC cùng reconciliation. Cloud B phải vượt conformance, load, security và DR test trước khi chuyển production. Managed analytics hoặc dịch vụ native chỉ được thay khi business case đủ mạnh.

**Điểm cốt lõi:** chuẩn hóa hợp đồng để các thành phần thống nhất về hành vi, không phải để mọi provider trông giống nhau. Khả năng di chuyển phải được đánh giá xuyên source, runtime, data, identity, integration và operations. Giữ domain logic portable ở nơi có giá trị, cô lập dependency native bằng adapter, kiểm tra bằng conformance suite và chứng minh bằng migration drill. Một exit strategy đáng tin cần cả đường chuyển dữ liệu, writer authority, security, cost và quy trình vận hành, không chỉ một container image có thể chạy ở nhiều nơi.
