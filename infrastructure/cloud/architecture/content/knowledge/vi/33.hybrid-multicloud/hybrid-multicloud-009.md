# Chiến lược thoát nhà cung cấp và kiểm chứng khả năng di chuyển

> **Chương:** Đám mây lai và đa đám mây  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào giảm phụ thuộc nhà cung cấp, chứng minh khả năng chuyển workload và dữ liệu, đồng thời quản lý chi phí, bảo mật, độ tin cậy và vận hành trong quá trình exit theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt portability, interoperability, reversibility và exit strategy.
2. Lập inventory các phụ thuộc provider ở compute, data, identity, network, observability, control plane, commercial và operations.
3. Xác định trigger, scope, mục tiêu và mức portability cho từng workload.
4. So sánh nền tảng thay thế theo capability, semantics, performance, security, cost và khả năng vận hành.
5. Thiết kế data export, migration, cutover, rollback và retirement có kiểm soát.
6. Tổ chức portability test, migration rehearsal và exit drill với bằng chứng định lượng.
7. Ước tính exit cost, thời gian, rủi ro và nguồn lực; quyết định đầu tư portability phù hợp.

## 1. Vì sao cần chiến lược thoát nhà cung cấp?

Một tổ chức có thể chọn cloud provider vì khả năng mở rộng, region, managed service, giá, bảo mật hoặc hệ sinh thái. Sau nhiều năm, ứng dụng có thể phụ thuộc sâu vào API, database, event service, IAM, network, proprietary runtime, backup, observability và quy trình vận hành của nhà cung cấp.

Khi cần chuyển đi, khó khăn thường không nằm ở việc tạo VM hoặc copy container image. Các câu hỏi khó hơn là:

- Dữ liệu có thể export đầy đủ, đúng định dạng và đọc được không?
- Database mới có cùng transaction, isolation, query semantics và consistency không?
- Identity, permission, key và audit có thể tái tạo tương đương không?
- Network connectivity, DNS, certificate, private endpoint và routing có chuyển đổi được không?
- Event, queue, scheduler và workflow có giữ semantics không?
- Provider đích có đáp ứng performance, capacity, DR và security không?
- Contract, license, egress fee và data deletion obligation có cho phép rời đi?
- Đội vận hành có đủ kỹ năng, runbook và tooling để chạy nền tảng mới?

**Exit strategy** là kế hoạch có thể thực thi để giảm, thay thế hoặc chấm dứt việc sử dụng provider/service trong phạm vi xác định, với mục tiêu, thời hạn, trách nhiệm, chi phí, bằng chứng và phương án phục hồi rõ ràng.

Không phải workload nào cũng cần chuyển được ngay sang mọi cloud. Một dịch vụ native có thể mang lại lợi ích lớn hơn chi phí lock-in. Điều quan trọng là tổ chức hiểu phụ thuộc đó, hậu quả khi rời đi và chi phí thực tế để chuyển đổi.

### 1.1. Phân biệt khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Portability | Khả năng chuyển workload/data/config sang môi trường khác với thay đổi có giới hạn | Container image chạy trên runtime tương thích |
| Interoperability | Hai hệ thống khác nhau có thể trao đổi và phối hợp | Ứng dụng cloud gọi API on-premises |
| Reversibility | Khả năng đảo ngược hoặc rút khỏi lựa chọn công nghệ/provider | Export dữ liệu, thay API và thu hồi dịch vụ |
| Exit strategy | Kế hoạch quản trị để thực hiện rời đi | Migrate database, cutover traffic, chấm dứt contract |
| Vendor lock-in | Chi phí/kỹ thuật/ràng buộc khiến rời provider khó hoặc tốn kém | Data model và API độc quyền |
| Multi-cloud | Chạy workload trên nhiều cloud provider | Nhiều provider phục vụ các workload khác nhau |
| Hybrid cloud | Kết hợp cloud và môi trường private/on-premises | Dữ liệu nhạy cảm ở private environment |

Multi-cloud không tự động chứng minh portability. Một hệ thống có thể chạy trên hai cloud nhưng vẫn dùng database độc quyền, identity model riêng và cách vận hành khác nhau.

## 2. Xác định trigger, scope và mục tiêu exit

Không bắt đầu bằng việc chọn cloud đích. Trước hết xác định cần thoát khỏi cái gì và vì lý do nào.

### 2.1. Trigger kích hoạt

Trigger có thể gồm:
- Provider tăng giá hoặc thay đổi pricing model.
- Region/service không còn đáp ứng availability, latency hoặc capacity.
- Dịch vụ bị deprecate hoặc ngừng hỗ trợ.
- Yêu cầu data residency, compliance hoặc sovereign control thay đổi.
- Vendor thay đổi hợp đồng, điều khoản dữ liệu hoặc support.
- Rủi ro tập trung provider vượt risk appetite.
- Quota hoặc khả năng cung ứng không còn đáp ứng business.
- Sáp nhập, tách doanh nghiệp hoặc thay đổi chiến lược sản phẩm.
- Một service không còn hiệu quả về cost/performance.

Trigger nên có ngưỡng rõ. "Giá quá cao" cần chuyển thành điều kiện đo được như unit cost vượt ngân sách trong các kỳ liên tiếp, sau khi đã kiểm tra utilization và cơ hội tối ưu.

### 2.2. Các kiểu mục tiêu

| Mục tiêu | Phạm vi | Ví dụ |
| --- | --- | --- |
| Service exit | Thay một managed service | Chuyển queue sang broker khác |
| Data exit | Export và chuyển dữ liệu | Di chuyển object storage |
| Workload exit | Di chuyển một ứng dụng | Chuyển API và worker |
| Region exit | Rời một region | Chuyển workload khỏi region không phù hợp |
| Provider exit | Chấm dứt provider | Di chuyển workload, data và control plane |
| Partial exit | Giảm footprint nhưng giữ một số dịch vụ | Thay workflow, giữ CDN trong thời hạn |
| Contractual exit | Kết thúc hợp đồng và xử lý dữ liệu | Export, deletion evidence, đóng account |

Mỗi mục tiêu có scope, chi phí và rủi ro khác nhau. Không nhất thiết phải chuyển toàn bộ cloud trong một lần.

### 2.3. Điều kiện thành công

Exit chỉ được coi là hoàn thành khi:
- Người dùng hoàn thành hành trình nghiệp vụ theo SLO.
- Dữ liệu đầy đủ, đúng và đối soát được.
- Identity, authorization, key và audit đạt policy.
- Backup/restore, DR và incident process đã được kiểm chứng.
- Performance/capacity đạt tải và failure headroom.
- Chi phí vận hành nằm trong ngân sách.
- Tích hợp bên ngoài hoạt động.
- Data retention/export/deletion với provider cũ hoàn tất.
- Contract, license, support và account được đóng đúng quy trình.

## 3. Lập inventory phụ thuộc và đánh giá lock-in

Inventory phải mô tả dependency thực tế, không chỉ liệt kê dịch vụ trên hóa đơn.

### 3.1. Các lớp phụ thuộc

| Lớp | Ví dụ | Câu hỏi portability |
| --- | --- | --- |
| Compute/runtime | VM, proprietary function, container, orchestration, GPU | Code và runtime có chạy nơi khác? |
| Storage | Block, object, file, archive, snapshot | Export có giữ metadata, version và retention? |
| Database | Relational, NoSQL, warehouse, search | Schema, transaction, query và consistency có tương đương? |
| Messaging | Queue, event bus, stream, scheduler | Ordering, delivery, retry, retention và replay? |
| Identity | IAM, SSO, workload identity, KMS | Principal, role, federation và policy map thế nào? |
| Network | VPC/VNet, firewall, private endpoint, DNS | Routing, segmentation và connectivity có tái tạo? |
| Security | KMS, HSM, WAF, secrets, threat detection | Key custody, audit và control chuyển thế nào? |
| Observability | Metrics, logs, traces, alerts | Có export lịch sử và giữ được ý nghĩa metric? |
| Delivery/control plane | IaC, registry, GitOps, deployment API | Resource và state có thể chuyển đổi? |
| Operations | Runbook, support, quota, incident tooling | Đội có thể vận hành và phục hồi? |
| Commercial/legal | Contract, egress, license, committed spend | Quyền export, phí, notice và deletion? |

### 3.2. Phụ thuộc trực tiếp và gián tiếp

- **Direct dependency:** ứng dụng gọi API hoặc SDK riêng của provider.
- **Transitive dependency:** framework/library phụ thuộc dịch vụ khác.
- **Operational dependency:** deploy, backup, monitor hoặc incident chỉ chạy qua console/API riêng.
- **Data dependency:** schema, format, metadata hoặc semantics gắn với service.
- **Commercial dependency:** license, committed spend, egress fee hoặc termination clause.
- **Knowledge dependency:** chỉ một nhóm nhỏ hiểu automation và vận hành.

Một ứng dụng không import cloud SDK trực tiếp vẫn có thể lock-in qua database extension, queue semantics, IAM policy, proprietary SQL, workflow engine hoặc deployment controller.

### 3.3. Dependency graph

~~~mermaid
flowchart TB
    APP["Business application"] --> API["Managed API / runtime"]
    API --> DB[("Managed database")]
    API --> Q["Provider event / queue"]
    API --> IAM["Provider IAM"]
    API --> SEC["KMS / secret manager"]
    API --> OBS["Logs / metrics / tracing"]
    Q --> WF["Managed workflow"]
    WF --> DB
    DB --> BK["Provider backup / snapshot"]
    IAM --> K["Provider key control plane"]
    OBS --> SIEM["Security analytics"]
~~~

Graph giúp tìm dependency có fan-out lớn. Nếu nhiều workload cùng dựa vào một identity, key hoặc event platform, chi phí exit của thành phần đó có thể lớn hơn chi phí của một ứng dụng.

### 3.4. Chấm mức độ lock-in

Đánh giá từng dependency theo:
- Technical specificity: API, data model và semantics đặc thù tới mức nào?
- Data gravity: dữ liệu lớn, thay đổi liên tục hoặc khó export ra sao?
- Substitutability: có phương án thay thế tương đương không?
- Migration complexity: số bước, downtime và thay đổi code/config.
- Operational readiness: kỹ năng, runbook, tooling và support.
- Commercial friction: egress, contract, license và notice.
- Blast radius: số workload/hành trình bị ảnh hưởng.
- Recovery constraint: có thể rollback hoặc chạy song song không?

Thang định tính tham khảo:
- Thấp: chuẩn mở, export dễ, nhiều lựa chọn thay thế, test tự động.
- Trung bình: cần adapter, chuyển schema hoặc đổi một phần vận hành.
- Cao: API/format proprietary, dữ liệu lớn, semantics khác, dual-run dài.
- Rất cao: không có export đầy đủ, hạn chế pháp lý/thương mại hoặc không thể tái tạo business behavior trong thời hạn cần thiết.

Không dùng điểm tổng để che giấu blocker nghiêm trọng về data portability hoặc legal exit.

## 4. Chọn chiến lược portability phù hợp

Portability có chi phí. Cố làm mọi thứ portable ở mọi lớp có thể tạo abstraction quá mức, mất lợi ích managed service và tăng toil.

### 4.1. Các chiến lược

| Chiến lược | Mô tả | Phù hợp khi | Đánh đổi |
| --- | --- | --- | --- |
| Native-first with documented exit | Dùng dịch vụ native nhưng có exit analysis và export | Lợi ích provider cao, lock-in chấp nhận được | Exit có thể cần dự án lớn |
| Open standards | Ưu tiên protocol/format chuẩn | Cần interoperability | Chuẩn không đảm bảo semantics giống nhau |
| Portable runtime | Container/Kubernetes/standard runtime | Workload cần di chuyển | Platform operations phức tạp |
| Adapter/abstraction | Encapsulate provider API sau interface | Nhiều implementation hoặc cần thay service | Abstraction drift |
| Data-first portability | Ưu tiên export, schema, CDC và open format | Data gravity là rủi ro chính | Có thể mất một số tối ưu native |
| Active multi-cloud | Vận hành nhiều provider cùng lúc | Có yêu cầu rõ về resilience/regulation | Cost, consistency và complexity cao |

### 4.2. Không trừu tượng hóa mọi thứ

Một interface chung cho object storage có thể che giấu khác biệt về:
- Versioning và object lock.
- Multipart upload/copy.
- Event notification.
- Lifecycle/retention.
- Encryption context và key policy.
- Consistency và listing semantics.
- Request pricing và egress.
- Metadata, tagging và access control.

Adapter nên giữ được capability cần thiết. Nếu buộc dùng common denominator quá nhỏ, ứng dụng có thể mất performance hoặc security features quan trọng.

### 4.3. Portability tier theo workload

- **Tier 0 — Native commitment:** dùng dịch vụ đặc thù; có exit analysis và chấp nhận thời gian/chi phí chuyển cao.
- **Tier 1 — Exportable:** có data export, API contract và runbook; thay thế cần migration project.
- **Tier 2 — Replaceable:** có adapter/standard, automated test và target option đã thử.
- **Tier 3 — Rehearsed portable:** có thể deploy/migrate qua quy trình đã diễn tập và đo được.

Tier là công cụ governance, không phải xếp hạng chất lượng. Workload quan trọng có thể cần Tier 2/3; workload ít quan trọng có thể chấp nhận Tier 0 nếu business case rõ.

## 5. Chọn target bằng capability mapping

Không chọn provider đích chỉ bằng danh sách sản phẩm hoặc giá compute. Phải đối chiếu capability và semantics.

| Capability | Nền tảng hiện tại | Nền tảng đích | Câu hỏi kiểm chứng |
| --- | --- | --- | --- |
| Compute | Managed container/function | Runtime/Kubernetes | Startup, autoscale, networking, limits |
| Database | Managed relational | Managed hoặc self-managed DB | SQL dialect, isolation, replication, backup |
| Event | Proprietary event bus | Broker khác | Ordering, retention, replay, delivery |
| Identity | Provider IAM | Federation/OIDC/workload identity | Role mapping, token, audit |
| Secrets/KMS | Native vault | KMS/HSM/secret manager khác | Key custody, rotation, envelope encryption |
| Object storage | Proprietary object API | Storage tương thích | Versioning, lifecycle, retention, metadata |
| Observability | Native monitoring | OpenTelemetry + backend | Metric semantics, trace context, alert |
| Network | VPC/private endpoint | Network đích | Routing, DNS, firewall, latency |
| Delivery | Provider IaC | IaC/GitOps khác | State migration, drift, policy |

"S3-compatible", "Kubernetes-compatible" hay "PostgreSQL-compatible" không đủ để kết luận tương thích. Cần test operation thực tế, giới hạn, failure behavior và performance.

### 5.1. Capability thay vì product name

Mô tả yêu cầu bằng capability:
- Durable queue cần delivery semantics nào?
- Transaction database cần isolation nào?
- Object store cần versioning, retention và legal hold ra sao?
- IAM cần workload identity federation và conditional policy nào?
- Workflow cần durable execution, compensation và audit?
- Observability cần cardinality, retention và trace propagation thế nào?

Sau đó map capability vào dịch vụ hiện tại và các phương án đích. Cách này tránh chọn target chỉ vì tên sản phẩm tương tự.

## 6. Portability của application, runtime và control plane

### 6.1. Giảm phụ thuộc API proprietary trong business logic

Không để business logic gọi trực tiếp cloud SDK ở hàng trăm nơi nếu không có lý do. Có thể đặt adapter cho object storage, queue, email, secrets hoặc identity. Interface phải thể hiện semantics nghiệp vụ cần thiết và có contract test cho từng implementation.

~~~mermaid
flowchart LR
    DOMAIN["Business logic"] --> PORT["Application port / interface"]
    PORT --> A["Provider A adapter"]
    PORT --> B["Provider B adapter"]
    A --> AAPI["Provider A API"]
    B --> BAPI["Provider B API"]
~~~

Interface queue không nên chỉ biểu diễn thao tác publish nếu ứng dụng cần ordering, deduplication, delay, retry, dead-letter và replay. Contract phải mô tả guarantee thực tế.

### 6.2. Container không đảm bảo toàn bộ workload portable

Các phụ thuộc còn lại:
- Persistent volume/CSI driver có thể provider-specific.
- Load balancer/ingress annotation khác nhau.
- IAM integration và secret injection khác nhau.
- Storage class, network plugin và service mesh có semantics riêng.
- Autoscaling signal và quota khác nhau.
- GPU/accelerator và kernel capability khác.
- Runtime security và admission policy không giống nhau.

Cần kiểm kê manifest, operator/CRD, image architecture, persistent state, node requirement và runtime control.

### 6.3. IaC và control plane

Terraform/Pulumi hoặc công cụ tương tự không làm mọi resource portable. Provider-specific resource, data source và state có thể buộc viết lại.

Để giảm lock-in:
- Tách module logic chung khỏi module resource-specific.
- Dùng input/output contract rõ.
- Version pin provider và module.
- Review plan, state migration và drift.
- Không giả định resource có tên giống nhau có hành vi giống nhau.
- Có automated policy/security test trên target.
- Lưu export inventory, config và dependency graph.

Không sửa state file thủ công nếu chưa hiểu format và quy trình lock/backup. State có thể chứa secret và cần bảo vệ như dữ liệu nhạy cảm.

## 7. Data portability: phần thường khó nhất

### 7.1. Data inventory

Phân loại dữ liệu cần xử lý:
- Primary database và replica.
- Object/file/blob, metadata và version.
- Queue/topic/event log và consumer offset.
- Search index và materialized view.
- Cache/session state.
- Backup, snapshot và archive.
- Audit/log/trace/security event.
- Encryption key, certificate và secret.
- Schema registry, data catalog, lineage và retention metadata.

Không phải dữ liệu nào cũng cần migrate. Cache có thể tái tạo; audit có thể cần lưu lâu; queue có thể cần drain hoặc replay; key có thể phải giữ tại HSM hiện tại theo policy trước khi re-encrypt.

### 7.2. Export format và semantics

Cần xác định:
- Format có mở và được mô tả không?
- Export có gồm schema, index, constraints và metadata?
- Timestamp/timezone, encoding và collation có giữ nguyên?
- Transaction boundary và ordering thể hiện ra sao?
- Object version, retention/legal hold và tags có xuất được không?
- Delete marker, tombstone và soft-delete có được giữ?
- Có checksum và manifest?
- Export API có giới hạn, throttling hoặc phí?

CSV không nhất thiết là bản export đầy đủ của database. Nó có thể bỏ constraints, sequence, binary field, index, transaction state và relationship.

### 7.3. Data migration patterns

| Pattern | Cách làm | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| Offline bulk copy | Dừng ghi, export/import, verify rồi cutover | Dataset nhỏ hoặc downtime cho phép | Downtime dài |
| Online bulk + CDC | Copy baseline rồi đồng bộ change log | Dataset lớn, downtime thấp | Lag, ordering, schema compatibility |
| Dual-write | Ghi hai hệ thống trong giai đoạn chuyển | Có semantics và idempotency rõ | Partial success và divergence |
| Event replay | Rebuild target từ event history | Log đầy đủ, contract ổn định | Retention, versioning, poison event |
| Logical replication | Replicate database changes | Engine hỗ trợ, target tương thích | Type, DDL, sequence, extension |
| Snapshot/restore | Snapshot và restore target | Format tương thích | Version/region constraint |

Không dùng dual-write chỉ để giảm downtime. Nó tạo giao dịch phân tán: một bên thành công, bên kia lỗi. Nếu cần, phải có outbox/inbox, idempotency, reconciliation và source of truth rõ.

### 7.4. Data validation

Kiểm tra:
- Record count theo bảng/partition/tenant.
- Checksum/hash theo batch hoặc object.
- Aggregate business totals.
- Referential integrity và constraint.
- Null, duplicate và outlier profile.
- Sequence/offset/timestamp cuối.
- Query result comparison.
- Reconciliation nguồn/đích.
- Spot-check dữ liệu nhạy cảm có kiểm soát.

Cùng số row không chứng minh dữ liệu tương đương. Có thể thiếu giao dịch mới, sai timezone, mất tombstone hoặc thay đổi numeric precision.

## 8. Identity, security và key portability

### 8.1. Identity mapping

Role và permission không thể dịch một-một chỉ bằng tên. Cần map:
- Human identity, group và federation.
- Workload/service identity.
- Role, resource scope và condition.
- Cross-account/project access.
- MFA, privileged access và break-glass.
- Token issuer/audience và trust policy.
- Audit principal và attribution.

Test cả allow và deny. Permission rộng hơn ở target có thể là lỗi nghiêm trọng dù application chạy được.

### 8.2. Secret và encryption key

Secret/password có thể tạo lại tại target; encryption key không phải lúc nào cũng export được hoặc được phép export. Phải xác định key custody, ownership, HSM/KMS capability, envelope encryption, rotation và re-encryption strategy.

Phương án có thể gồm:
- Giữ key ở nguồn trong giai đoạn dual-run và cho target gọi qua network bảo vệ.
- Re-encrypt dữ liệu tại nguồn bằng format trung gian được phê duyệt.
- Decrypt/encrypt lại trong môi trường kiểm soát, có audit và separation of duties.
- Dùng customer-managed key có thể import/replicate nếu provider và policy cho phép.

Không export plaintext key vào ticket, file share hoặc build pipeline chỉ để tăng tốc migration.

### 8.3. Security control parity

Target cần có control tương đương hoặc residual risk được phê duyệt:
- TLS/mTLS, encryption at rest.
- Network segmentation, egress control.
- IAM least privilege, workload identity, JIT admin.
- Secret management và rotation.
- Vulnerability scanning, provenance và runtime hardening.
- Logging, retention, alerting và incident response.
- Backup immutability và restore testing.
- Data residency, deletion và audit.

Control parity không yêu cầu sản phẩm giống nhau; phải chứng minh outcome bảo mật tương đương theo threat model.

## 9. Network, connectivity và traffic cutover

Di chuyển workload có thể cần thay đổi IP range, subnet, route, firewall, VPN/private interconnect, DNS, certificate, load balancer, WAF, service discovery, NAT, egress allowlist và partner integration.

### 9.1. DNS cutover

DNS TTL thấp có thể giúp một số client cập nhật endpoint nhanh hơn, nhưng không đảm bảo mọi resolver/client cập nhật ngay. Cần:
1. Kiểm tra quyền quản lý domain/zone và record.
2. Giảm TTL trước cutover theo thời gian phù hợp.
3. Chuẩn bị endpoint đích và certificate.
4. Kiểm tra health, routing, firewall và capacity.
5. Chuyển traffic theo percentage/weighted routing nếu hỗ trợ.
6. Theo dõi connection, error, latency và business SLI.
7. Giữ nguồn cũ hoạt động trong rollback window.
8. Sau ổn định mới đưa TTL về mục tiêu.

### 9.2. Traffic cutover patterns

| Pattern | Cách làm | Ưu điểm | Điều cần kiểm soát |
| --- | --- | --- | --- |
| Big-bang | Chuyển toàn bộ traffic một thời điểm | Đơn giản về lịch | Blast radius và rollback lớn |
| Weighted/canary | Chuyển một phần từng bước | Giảm rủi ro | Session affinity và data writes |
| Blue-green | Môi trường mới chạy song song | Điểm chuyển rõ | Dual-run cost và data sync |
| Cell/tenant wave | Di chuyển từng nhóm tenant | Cô lập blast radius | Tenant routing |
| Regional wave | Di chuyển từng region | Phù hợp data locality | Cross-region dependencies |

Nếu hai môi trường cùng nhận write mà không có replication/ownership rõ, weighted traffic có thể tạo data divergence.

## 10. Runbook migration và cutover

### 10.1. Giai đoạn chuẩn bị

- Xác định source/target, owner, scope và success criteria.
- Freeze hoặc kiểm soát thay đổi schema/API trong migration window.
- Kiểm tra quota, network, identity, key, registry và dependency.
- Tạo baseline data/performance/cost.
- Chạy bulk copy rehearsal và đo thời gian.
- Xác minh backup/restore ở target.
- Chuẩn bị traffic routing và DNS.
- Chuẩn bị communication, escalation và incident commander.
- Kiểm tra rollback precondition và decision owner.

### 10.2. Giai đoạn cutover

~~~mermaid
flowchart TD
    A["Preflight: capacity, security, backup"] --> B["Initial data copy"]
    B --> C["CDC / replication catch-up"]
    C --> D["Validate data and application"]
    D --> E{"Cutover gates pass?"}
    E -->|"No"| X["Stop, repair or abort rehearsal"]
    E -->|"Yes"| F["Freeze writes / drain transactions"]
    F --> G["Final sync and reconciliation"]
    G --> H["Switch routing and identity paths"]
    H --> I["Smoke / synthetic / business checks"]
    I --> J{"SLO and correctness pass?"}
    J -->|"No"| K["Rollback or forward recovery decision"]
    J -->|"Yes"| L["Observe stabilization window"]
    L --> M["Accept target as primary"]
    M --> N["Retire source after exit criteria"]
~~~

### 10.3. Cutover gates

Không chuyển primary chỉ vì migration job báo hoàn thành. Gates cần gồm:
- Replication lag bằng 0 hoặc trong ngưỡng đã duyệt.
- Final sequence/offset được đối soát.
- Data checksum và business aggregate đạt.
- Target schema/version được application hỗ trợ.
- Identity/authorization test pass.
- Encryption/backup/restore được xác minh.
- Latency/throughput/capacity đạt load target.
- Error rate và business SLI trong ngưỡng.
- On-call, escalation và runbook sẵn sàng.
- Risk owner/change approver xác nhận cutover.

## 11. Rollback và quyết định quay lại

Rollback data phức tạp hơn rollback application. Sau khi target nhận write mới, quay lại source có thể mất giao dịch nếu không đồng bộ ngược.

### 11.1. Rollback window

Trước cutover, xác định:
- Khoảng thời gian giữ source và dữ liệu có thể đồng bộ ngược.
- Source còn writable hay đã fenced/read-only.
- Có reverse replication không?
- External side effect nào đã xảy ra?
- Cần reconciliation hoặc compensation nào?
- Khi nào rollback không còn an toàn và phải roll-forward?

~~~mermaid
flowchart TD
    A["Target has issue after cutover"] --> B{"Any new writes?"}
    B -->|"No"| C["Route to source if still valid"]
    B -->|"Yes"| D{"Reverse sync/reconcile reliable?"}
    D -->|"Yes"| E["Freeze, reverse sync, validate, rollback"]
    D -->|"No"| F["Keep target and forward-fix/manual recovery"]
    E --> G["Verify correctness and SLO"]
    C --> G
    F --> G
~~~

Không rollback nếu source đã decommission, key bị revoke, schema không tương thích hoặc external side effect không thể đảo ngược. Runbook cần decision owner và deadline cho quyết định.

## 12. Exit cost và mô hình tài chính

Exit cost thường lớn hơn phí data egress. Cần tính kỹ thuật, vận hành, thương mại và rủi ro trong toàn bộ quá trình.

### 12.1. Thành phần exit cost

- Egress, export API, snapshot, retrieval và temporary storage.
- Target compute/storage/database trong dual-run.
- Data conversion, schema adaptation, re-encryption và validation.
- Rewrite application adapter, IaC, CI/CD, observability và policy.
- Network interconnect, DNS, certificate và security tooling.
- Testing, rehearsal, performance tuning và DR.
- Vendor professional service hoặc termination fee.
- License portability và support contract mới.
- Kỹ năng, training, hiring và on-call load.
- Downtime, business disruption và opportunity cost.
- Decommission, deletion certification và audit.
- Contingency cho delay, mismatch và rollback.

### 12.2. Ví dụ exit budget

Giả sử một dịch vụ có 80 TB data. Mô hình giả định:

| Hạng mục | Ước tính |
| --- | ---: |
| Data transfer/export và temporary storage | 18.000 USD |
| Target platform chạy song song 2 tháng | 42.000 USD |
| Engineering và application adaptation | 70.000 USD |
| Database migration, testing và reconciliation | 28.000 USD |
| Security, network và observability integration | 16.000 USD |
| Training, support và operational readiness | 12.000 USD |
| Contingency 20% | 37.200 USD |
| **Tổng giả định** | **223.200 USD** |

Đây là ví dụ số học, không phải báo giá. Dự toán thật cần price book, hợp đồng, data size/egress, export rate, dual-run duration, labor rate và workload risk.

### 12.3. Exit readiness như một khoản đầu tư

\[
ExpectedExitCost = P(trigger) \times Cost(exit\ when\ triggered)
\]

\[
PortabilityValue =
ExpectedExitCost_{before} -
ExpectedExitCost_{after} -
Cost(portability\ controls)
\]

Đây là mô hình trao đổi, không phải dự báo chắc chắn. Ngoài financial value còn có strategic option value, negotiating leverage, regulatory readiness và resilience.

## 13. Hợp đồng, dữ liệu và shared responsibility khi exit

Exit plan cần review cùng Procurement, Legal, Privacy, Security và Finance.

Các mục cần xác minh:
- Quyền export data và metadata; format, API, thời gian cung cấp.
- Egress/export fee và phí archive/snapshot retrieval.
- Notice period, termination date và auto-renewal.
- Data processor/subprocessor và vị trí xử lý.
- Retention sau termination.
- Deletion, backup expiry và certificate of destruction.
- Quyền truy cập audit/evidence sau khi đóng account.
- License portability, BYOL và third-party software.
- Support trong migration window.
- Điều khoản transition assistance.
- Ownership của key, domain, certificate và IP.
- Cách xử lý provider không export được hoặc outage.

Không giả định xóa resource đồng nghĩa xóa toàn bộ dữ liệu. Cần xác nhận replica, snapshot, backup, log, cache và subprocessor theo điều khoản áp dụng.

## 14. Exit test và migration rehearsal

Một exit plan chưa từng diễn tập chỉ là giả thuyết.

### 14.1. Các cấp độ kiểm thử

| Cấp | Nội dung | Bằng chứng |
| --- | --- | --- |
| Inventory test | Export dependency/resource inventory | Coverage và owner |
| Export test | Export dataset đại diện | Duration, completeness, checksum |
| Restore test | Import vào target | Restore success, schema/data validation |
| Compatibility test | Chạy application contract/test suite | Functional/integration results |
| Performance test | Benchmark target | p95/p99, throughput, saturation, cost |
| Security test | IAM, key, network, audit | Policy/negative test, scan và audit |
| Operational test | Deploy, monitor, backup, incident và DR | Runbook và on-call signoff |
| Cutover rehearsal | Diễn tập toàn bộ trình tự | Downtime, lag và decision timing |
| Exit drill | Partial/full exit giả lập | Duration, cost và blocker |

### 14.2. Workload đại diện

Không chỉ dùng dataset nhỏ:
- Giữ tỷ lệ dữ liệu, index, object size và partition skew gần production.
- Mô phỏng peak traffic, background job và event rate.
- Kiểm tra data growth trong lúc initial copy.
- Thử schema change giữa lúc CDC.
- Mô phỏng network interruption và API throttling.
- Thử target restart, failover và restore.
- Đo thời gian reconcile và downtime cuối.

### 14.3. Portability proof

Một proof tối thiểu cần chứng minh:
1. Deploy workload trên target từ source/version-controlled artifacts.
2. Cung cấp identity, network, secret và config qua quy trình review.
3. Import dữ liệu và đạt integrity checks.
4. Application xử lý journey quan trọng.
5. Performance/capacity nằm trong ngưỡng.
6. Backup/restore và monitoring hoạt động.
7. Cutover và rollback/forward recovery đã thử.
8. Người vận hành khác có thể làm theo runbook.

## 15. Điều kiện retire provider cũ

Không đóng provider account hoặc xóa source resource ngay sau khi traffic chuyển.

Trước retirement:
- Target qua stabilization window.
- Data reconciliation hoàn tất, owner ký xác nhận.
- Backup/retention/legal hold được xử lý.
- DNS, certificate, webhook, partner allowlist và integration cập nhật.
- Không còn traffic, job, scheduled task, cross-account role hoặc callback về nguồn.
- Key/secret cũ được rotate/revoke theo kế hoạch.
- Log/audit cần giữ đã export và truy cập được.
- Data deletion/retention có evidence.
- License, contract, committed spend và support được đóng đúng.
- Rollback window kết thúc và decision owner chấp nhận.
- CMDB/inventory/architecture/DR runbook được cập nhật.

~~~mermaid
flowchart TD
    A["Target stable and accepted"] --> B["Confirm data reconciliation"]
    B --> C["Drain jobs, queues and integrations"]
    C --> D["Export required audit/evidence"]
    D --> E["Revoke old access, keys and credentials"]
    E --> F["Delete/expire source data per policy"]
    F --> G["Verify deletion and residual backups"]
    G --> H["Close license, contract and billing"]
    H --> I["Update inventory and architecture records"]
~~~

Mỗi bước cần evidence và owner. Có thể giữ provider account ở trạng thái hạn chế trong một thời gian theo retention/audit policy trước khi đóng hoàn toàn.

## 16. Tình huống thực tế: chuyển nền tảng booking giữa hai cloud

Một SaaS booking chạy trên Provider A với containerized API/worker, managed relational database, event bus/workflow engine, object storage, IAM, secret manager, KMS và monitoring. Tổ chức xem xét exit vì chi phí tăng, yêu cầu data residency mới và muốn giảm phụ thuộc vào event/workflow platform. Không cần chuyển tất cả service cùng lúc.

### 16.1. Phân loại workload

| Workload | Lock-in chính | Chiến lược |
| --- | --- | --- |
| Booking API | IAM, database driver, secret integration | Container, adapter và DB compatibility test |
| Notification worker | Event semantics | Event contract và idempotency |
| Workflow | Proprietary state machine | Chuyển theo use case, test timeout/compensation |
| Invoice storage | Object metadata, retention, KMS | Export manifest, re-encrypt, verify version/tags |
| Analytics | Warehouse SQL và data format | Open format/export, query validation |
| Observability | Query/alert language | OpenTelemetry pipeline, migrate dashboard |
| CI/CD | Provider deploy API/IaC | Versioned pipeline và target deploy identity |

### 16.2. Lộ trình theo wave

1. **Discovery:** inventory, dependency graph, contract review, baseline cost/SLO.
2. **Foundation:** target landing zone, network, IAM, logging, KMS, registry, policy và CI/CD.
3. **Stateless workload:** deploy API read-only/canary, xác minh token, routing và performance.
4. **Data:** baseline copy, CDC, object export, checksum và reconciliation.
5. **Events/workflow:** migrate producer/consumer, idempotency, replay và durable state.
6. **Transaction cutover:** freeze/dual-run theo design, final sync và traffic shift.
7. **Stabilization:** SLO, cost, security, backup/restore và on-call exercise.
8. **Exit:** drain nguồn, revoke credential, export audit, deletion evidence và contract closure.

### 16.3. Success gates

- Checkout/search SLO đạt trên target.
- Booking/payment state đối soát trong ngưỡng.
- Event không mất và duplicate được xử lý idempotent.
- Access control và tenant isolation qua negative test.
- Key/secret và encryption policy được xác minh.
- Backup restore và DR đạt RTO/RPO.
- Cost per successful booking trong business threshold.
- Không còn production dependency bắt buộc quay về Provider A sau retirement.

## 17. Tình huống thứ hai: managed service độc quyền không có tương đương trực tiếp

Một nhóm analytics dùng dịch vụ workflow/streaming độc quyền tích hợp chặt với warehouse. Target không có API tương đương.

Không chọn sản phẩm chỉ vì tên gần giống. Hãy:
- Liệt kê capability đang dùng: ordering, windowing, state store, watermark, replay, exactly-once boundary, schema registry, scheduler và lineage.
- Xác định capability bắt buộc và capability có thể thay bằng thiết kế khác.
- Đưa semantics vào contract test và data correctness test.
- So sánh tự vận hành broker/stream processor với managed alternative.
- Đo throughput, latency, late event, recovery, replay và cost.
- Chấp nhận rewrite nếu business case và exit objective biện minh.
- Ghi residual risk và chi phí duy trì hai hệ thống trong migration.

Có thể giữ dịch vụ độc quyền trong phạm vi nhỏ nếu lợi ích lớn và exit risk được chấp nhận. Exit strategy không bắt buộc thay mọi công nghệ bằng một sản phẩm tổng quát.

## 18. Đo lường exit readiness và portability

| Metric | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| Dependency inventory coverage | Tỷ lệ workload có dependency/owner đã ghi | Tìm vùng mù |
| Critical dependency portability | Tỷ lệ dependency critical có phương án đã test | Đánh giá readiness |
| Data export completeness | Tỷ lệ dữ liệu/metadata export và validate được | Tìm data lock-in |
| Migration rehearsal success | Tỷ lệ rehearsal đạt gates | Bằng chứng thực thi |
| Measured exit time | Thời gian diễn tập để đạt target | So với RTO/contract window |
| Exit cost variance | Chênh estimate với rehearsal/actual | Cải thiện dự toán |
| Provider-specific surface | Phạm vi code/config gắn API riêng | Theo dõi trend |
| Unresolved exit blockers | Blocker kỹ thuật, pháp lý, commercial | Escalation |
| Operational readiness | Runbook/owner/on-call được xác nhận | Khả năng vận hành |
| Residual source dependency | Luồng còn phụ thuộc provider cũ | Điều kiện retire |

Không dùng số dòng provider-specific code làm KPI duy nhất. Một ít code có thể gọi dịch vụ độc quyền chứa phần lớn business state; hệ thống nhiều adapter vẫn có thể khó vận hành.

## 19. Well-Architected tradeoffs

| Trụ cột | Câu hỏi |
| --- | --- |
| Operational Excellence | Đội có kỹ năng, runbook, IaC, monitoring và owner cho target? |
| Security | Identity, key custody, data protection và audit có tương đương? |
| Reliability | Migration có backup, replication, rollback, DR và fencing? |
| Performance Efficiency | Target đạt latency/throughput trên workload thật? |
| Cost Optimization | Egress, dual-run, license, operations và unit economics? |
| Sustainability | Có tránh duplicate footprint, transfer dư thừa và over-provision? |

Multi-cloud có thể giảm concentration risk nhưng tăng số control plane, network path, IAM model, on-call skill và observability backend. Chỉ nên đầu tư khi lợi ích về resilience, negotiation, residency hoặc continuity lớn hơn complexity và cost.

## 20. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi container đồng nghĩa portable | Data, IAM, network và managed service vẫn lock-in | Inventory toàn bộ dependency |
| Chọn target theo tên sản phẩm | Semantics khác gây lỗi business | Capability mapping và contract test |
| Chỉ thử app startup | Không chứng minh data, security, performance | End-to-end portability proof |
| Export CSV rồi coi là data exit | Mất schema, transaction, metadata, history | Data inventory và semantic validation |
| Dual-write không idempotency | Divergence và duplicate transaction | Outbox/inbox, reconciliation |
| Chuyển traffic trước khi data catch-up | Mất hoặc đọc stale data | Replication lag gate và final sync |
| Không có rollback window | Không thể quay lại sau write mới | Define reverse sync hoặc forward recovery |
| Đánh giá thấp egress/dual-run | Budget và timeline vỡ | Exit cost model đầy đủ |
| Bỏ qua contract/deletion | Còn nghĩa vụ hoặc dữ liệu tại provider cũ | Legal review và deletion evidence |
| Multi-cloud mọi thứ | Complexity và cost vượt lợi ích | Portability theo criticality |
| Abstraction quá mức | Mất feature, performance hoặc semantics | Adapter theo capability thực |
| Không kiểm tra key portability | Không giải mã/khôi phục được dữ liệu | Key custody/re-encryption test |
| Không migrate observability | Target thiếu alert và incident context | Dashboard, trace, log và runbook parity |
| Tắt provider cũ quá sớm | Mất rollback/evidence/data access | Stabilization và retirement gates |
| Không có owner | Exit plan lỗi thời, không ai diễn tập | Assign owner và review cadence |

## 21. Bài tập thực hành

Một SaaS booking chạy trên Provider A với managed PostgreSQL, object storage, event bus, serverless workflow, IAM, KMS và monitoring. Ban lãnh đạo muốn đánh giá khả năng chuyển workload quan trọng sang Provider B trong 9 tháng do chi phí và rủi ro tập trung. Hệ thống có 12 TB database, 90 TB object, hàng triệu event mỗi ngày và nhiều tenant có yêu cầu data residency.

Hãy thực hiện:

1. Vẽ dependency graph cho API, database, event bus, workflow, storage, identity, key và observability.
2. Tạo inventory direct/transitive/operational/data/commercial dependencies; chấm lock-in.
3. Xác định workload nào cần Tier 0/1/2/3 portability và giải thích.
4. Xây capability matrix Provider A/B; kiểm tra semantics chứ không dựa tên sản phẩm.
5. Thiết kế data export/migration cho database, object, event history và workflow state.
6. Chọn bulk copy, CDC, replay hoặc phương án kết hợp; định nghĩa consistency/cutover gate.
7. Thiết kế identity mapping, workload identity, KMS/re-encryption, network và audit.
8. Lập migration wave, staffing, downtime budget, rollback window và forward recovery.
9. Tính exit cost gồm egress, dual-run, engineering, testing, license, training, decommission và contingency.
10. Xây portability test matrix, rehearsal và exit drill.
11. Xác định contract/legal/residency/deletion checks trước khi terminate provider.
12. Viết ADR về mức portability nên đầu tư; nêu residual lock-in, owner và trigger review.

**Tiêu chí tự đánh giá:** lời giải phải nêu workload/data nào chuyển được, bằng cách nào, trong bao lâu, với chi phí và rủi ro nào; có bằng chứng thử nghiệm, rollback/retirement plan; không coi multi-cloud hoặc container là bằng chứng portability tự thân.

## 22. Checklist trước khi cam kết exit readiness

- [ ] Trigger, scope và mục tiêu exit được định nghĩa.
- [ ] Workload, data, service, identity, network, control plane và contract có inventory.
- [ ] Dependency graph xác định direct, transitive, operational, data và commercial lock-in.
- [ ] Criticality, residency, recovery và blast radius được phân loại.
- [ ] Portability tier có rationale và owner.
- [ ] Target capability matrix kiểm tra semantics và giới hạn thực tế.
- [ ] Application/provider-specific code và adapter có contract test.
- [ ] IaC, CI/CD, registry, observability và runbook có phương án chuyển.
- [ ] Data export gồm schema, metadata, version, retention và audit cần thiết.
- [ ] Migration có checksum, reconciliation, CDC/replay và cutover gate.
- [ ] Identity, permission, secret, key custody và encryption được kiểm chứng.
- [ ] Network, DNS, certificate, private connectivity và routing đã thử.
- [ ] Performance, capacity, cost và failure headroom đạt mục tiêu.
- [ ] Backup/restore, rollback, reverse sync hoặc forward recovery đã diễn tập.
- [ ] Legal, Procurement, Privacy và Security xác nhận data/contract obligations.
- [ ] Exit cost có egress, dual-run, engineering, training và decommission.
- [ ] Owner, staffing, timeline, escalation và communication rõ.
- [ ] Portability proof và end-to-end rehearsal có evidence.
- [ ] Stabilization window và điều kiện retire provider cũ rõ.
- [ ] Data deletion, key revocation, license/contract closure có audit evidence.
- [ ] Exit plan được review khi provider/service thay đổi.

## Ghi nhớ

Chiến lược thoát nhà cung cấp bắt đầu bằng việc hiểu phụ thuộc thực tế, data gravity, semantics và ràng buộc thương mại. Portability không chỉ là chạy container ở cloud khác; nó phải bao gồm dữ liệu, identity, key, network, delivery, observability, security, vận hành và phục hồi.

Một exit plan đáng tin cậy đi theo chuỗi **inventory → lock-in assessment → target capability mapping → data/application preparation → migration rehearsal → gated cutover → stabilization → deletion và contract closure**. Chỉ tuyên bố sẵn sàng rời provider khi đã có bằng chứng về thời gian, chi phí, tính đúng đắn, SLO, bảo mật và khả năng đội ngũ thực hiện quy trình.
