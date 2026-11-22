# Giới hạn của lớp trừu tượng chung giữa nhiều nhà cung cấp

Kiến trúc hybrid cloud và multi-cloud thường tìm cách tạo một lớp chung để triển khai workload trên nhiều môi trường. Một đội có thể dùng Kubernetes để đóng gói ứng dụng, Terraform để khai báo hạ tầng, service mesh để kết nối service và một bộ API nội bộ để che khác biệt của từng nhà cung cấp. Cách tiếp cận này giúp chuẩn hóa một số thao tác, giảm phụ thuộc vào công cụ riêng và hỗ trợ di chuyển workload.

Tuy nhiên, **trừu tượng hóa không làm các nhà cung cấp trở nên giống hệt nhau**. Cùng một API có thể che giấu những semantics khác nhau về IAM, network, storage, consistency, autoscaling, failure domain, managed database, security policy, quota, billing và support. Một abstraction quá thấp có thể biến thành “lowest common denominator”: chỉ giữ phần giao nhau nhỏ nhất, khiến đội ngũ không tận dụng được khả năng tốt nhất của từng nền tảng. Một abstraction quá cao lại có thể tạo ảo giác portability, đẩy khác biệt xuống runtime và làm việc vận hành, debug hoặc migration khó hơn.

Bài học thuộc chương **Đám mây lai và đa đám mây** của module **CLOUD_ARCHITECTURE**. Trọng tâm là xác định đúng giới hạn của lớp trừu tượng chung, phân biệt tính di động của ứng dụng với tính di động của toàn bộ nền tảng, và lựa chọn ranh giới chuẩn hóa phù hợp với độ tin cậy, bảo mật, hiệu năng, chi phí và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích lợi ích và giới hạn của abstraction trong hybrid cloud và multi-cloud.
2. Phân biệt portability của source, container, runtime, platform, data và operational model.
3. Nhận diện semantic gap giữa các nhà cung cấp ở compute, network, identity, storage, database và observability.
4. Đánh giá nguy cơ lowest common denominator và abstraction leakage.
5. Thiết kế cloud adapter, platform API và capability profile mà không che mất khác biệt quan trọng.
6. Xác định phần nào nên chuẩn hóa, phần nào nên dùng native service.
7. Ước tính chi phí thực của portability, bao gồm data transfer, duplicated platform, skills và operations.
8. Xây dựng chiến lược exit/migration có kiểm chứng thay vì dựa vào tuyên bố “cloud agnostic”.

## 2. Abstraction trong multi-cloud là gì?

### 2.1. Lớp trừu tượng chung

Abstraction cung cấp một giao diện ổn định phía trên một hoặc nhiều implementation. Ứng dụng hoặc đội vận hành gọi giao diện chung, còn lớp bên dưới chuyển thành thao tác cụ thể trên từng provider.

Ví dụ:

- Platform API tạo workload mà không yêu cầu developer biết tên dịch vụ compute của provider.
- Kubernetes manifest mô tả Deployment, Service và storage request theo API chung.
- IaC module nhận input chuẩn rồi tạo resource tương ứng trên từng cloud.
- Object storage adapter cung cấp API put/get, phía dưới dùng dịch vụ lưu trữ khác nhau.
- Identity broker ánh xạ workload identity từ nhiều môi trường về một contract.

~~~mermaid
flowchart TB
    APP[Business applications]
    APP --> API[Internal platform API]
    API --> CAP[Capability contract]
    CAP --> AD1[Provider A adapter]
    CAP --> AD2[Provider B adapter]
    CAP --> AD3[Private cloud adapter]
    AD1 --> A[Native services A]
    AD2 --> B[Native services B]
    AD3 --> C[On-prem infrastructure]
~~~

Giao diện chung có giá trị khi nó mô tả một capability thực sự có thể bảo đảm ở mọi implementation. Nếu một provider không hỗ trợ tính năng, adapter phải công bố giới hạn hoặc từ chối request có chủ đích; không nên giả vờ rằng thao tác đã có semantics giống nhau.

### 2.2. Abstraction không đồng nghĩa với portability

Một ứng dụng có thể build thành cùng container image trên hai cloud nhưng vẫn chưa chắc chạy được tương đương. Nó có thể phụ thuộc IAM role, private endpoint, managed database extension, queue semantics, DNS, KMS key, region-specific API hoặc observability agent. Portability cần xét toàn bộ dependency và quy trình vận hành.

### 2.3. Các tầng portability

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| Source portability | Mã nguồn có thể build ở môi trường khác không? | Ngôn ngữ, framework, dependency |
| Artifact portability | Artifact có thể tải và chạy ở nơi khác không? | Container image, binary, package |
| Runtime portability | Runtime behavior có tương đương không? | Kubernetes, VM, function runtime |
| Platform portability | Network, identity, storage và policy có thể tái tạo không? | IaC, platform API, service mesh |
| Data portability | Dữ liệu và metadata có thể export/import đúng không? | Database, object, schema, event |
| Operational portability | Đội ngũ có thể triển khai, giám sát và phục hồi ở nơi khác không? | IAM, logging, DR, incident process |
| Commercial portability | Có thể chuyển mà không gặp ràng buộc không thể chấp nhận? | Egress, contract, license, commitment |

Một thiết kế có thể portable ở artifact layer nhưng rất khó portable ở data hoặc operations. Cần nói rõ đang tối ưu tầng nào.

## 3. Lợi ích thực tế của abstraction

### 3.1. Giảm cognitive load

Developer có thể dùng một contract cho các nhu cầu phổ biến như tạo service, cấu hình health check, gắn identity hoặc yêu cầu object storage. Platform team chịu trách nhiệm chi tiết provider và các guardrail.

### 3.2. Chuẩn hóa governance

Platform API có thể áp dụng mặc định encryption, tagging, logging, network isolation, quota và policy. Khi làm tốt, abstraction giúp giảm cấu hình sai giữa nhiều môi trường.

### 3.3. Tạo lựa chọn triển khai

Ứng dụng stateless, được đóng gói và ít phụ thuộc native API có thể triển khai ở nhiều region/provider hơn. Điều này hỗ trợ DR, capacity placement, data residency hoặc chiến lược đàm phán thương mại.

### 3.4. Tách application intent khỏi provider syntax

Đội sản phẩm mô tả nhu cầu như “cần queue có retention, dead-letter và encryption”, thay vì trực tiếp chọn resource name của provider. Platform có thể ánh xạ capability đó sang implementation phù hợp.

### 3.5. Giảm chi phí thay đổi ở phần ổn định

Nếu nhiều ứng dụng dùng cùng một contract và requirement tương tự, thay đổi policy hoặc default một lần có thể lan tới nhiều implementation. Tuy nhiên, chi phí này chỉ giảm khi contract đủ ổn định và adapter được kiểm thử.

## 4. Giới hạn căn bản: lowest common denominator

### 4.1. Chỉ giữ phần giao nhau

Giả sử provider A có queue với FIFO ordering, deduplication và transaction; provider B có pub/sub throughput cao nhưng ordering theo partition; nền tảng nội bộ chỉ định nghĩa API “send message/receive message”. Contract đó dễ triển khai trên cả hai nhưng không mô tả đầy đủ semantics mà ứng dụng có thể cần.

Hậu quả:

- Ứng dụng không tận dụng được capability native có giá trị.
- Đội phát triển phải tự xây retry, ordering hoặc deduplication.
- Throughput/latency có thể kém hơn implementation native.
- Một abstraction tưởng đơn giản lại tạo thêm tầng code và vận hành.

### 4.2. Mất capability đặc thù

Các cloud có thể có database serverless, global replication, event routing, identity federation, accelerator hoặc analytics service khác nhau. Nếu abstraction chỉ hỗ trợ capability cơ bản nhất, tổ chức có thể từ bỏ lợi thế của nền tảng mà business đang trả tiền để sử dụng.

### 4.3. Phần giao nhau thay đổi theo thời gian

Provider liên tục thêm tính năng, bỏ API cũ, thay đổi giới hạn và pricing. Contract chung có thể nhanh chóng lỗi thời. Khi thêm capability mới, phải quyết định mở rộng contract, thêm optional capability, hay dùng native extension.

### 4.4. Không phải capability nào cũng nên được chuẩn hóa

Chuẩn hóa những phần phổ biến và có semantics rõ: service deployment metadata, health checks, workload identity intent, telemetry conventions, tagging và policy baseline. Với managed analytics, database advanced feature hoặc specialized AI accelerator, có thể chấp nhận provider-specific implementation.

## 5. Semantic gap: cùng tên API nhưng khác hành vi

### 5.1. Tên tương tự không bảo đảm semantics tương tự

Một API abstraction có thể cung cấp createLoadBalancer, createDatabase hoặc createQueue, nhưng các implementation khác nhau ở:

- Failure domain và HA behavior.
- Ordering, consistency và transaction semantics.
- Retry, timeout và delivery guarantees.
- Encryption defaults và key policy.
- Network reachability và private access.
- Scaling behavior và quota.
- Backup, PITR và restore semantics.
- Metrics, logs và operational controls.

Một abstraction tốt phải mô tả behavior có thể kiểm chứng, không chỉ đồng nhất tên gọi.

### 5.2. Capability contract

Contract nên ghi:

- Capability required/optional.
- Consistency hoặc delivery guarantee.
- Availability/failure semantics.
- Ordering, durability và retention.
- Security/identity model.
- Capacity/quota và scaling behavior.
- Observability và operational action.
- Cost dimension hoặc usage unit.

Nếu implementation không đáp ứng requirement, nó cần fail validation hoặc công bố constraint; không âm thầm hạ semantics.

### 5.3. Capability profile

~~~yaml
capability: messaging
required:
  encryption_at_rest: true
  dead_letter: true
  retention_hours: 72
  delivery: at_least_once
optional:
  ordering_scope: partition
  deduplication_window_seconds: 300
  transactions: false
constraints:
  max_message_bytes: 256000
  max_retention_hours: 168
~~~

Đây là schema minh họa. Mỗi adapter phải validate profile với giới hạn thực tế. Nếu ứng dụng yêu cầu exactly-once end-to-end, không thể chỉ nhìn một cờ capability của broker; cần xét producer, storage, consumer, side effect và idempotency.

## 6. Khác biệt giữa compute và runtime

### 6.1. Container không xóa hết khác biệt runtime

Container giúp đóng gói filesystem, application và dependency ở user space. Nó không mang theo kernel, hypervisor, network implementation, storage driver, node lifecycle hoặc IAM identity của host.

Sự khác biệt còn lại:

- CPU architecture và instruction set.
- Kernel feature, cgroup và security module.
- Container runtime và image pull behavior.
- Storage class và CSI driver.
- CNI/network policy implementation.
- Node autoscaling và disruption behavior.
- GPU/accelerator device plugin.

### 6.2. Kubernetes API cũng có phần provider-specific

Kubernetes cung cấp API workload tương đối nhất quán, nhưng cluster có thể khác nhau ở:

- Managed control plane và version lifecycle.
- CNI, ingress/gateway controller và load balancer integration.
- CSI/storage class và snapshot controller.
- Workload identity integration.
- Autoscaler và node provisioning.
- Policy engine, secrets integration và service mesh.
- Upgrade, backup, audit và support.

Một manifest chạy được ở hai cluster chưa chứng minh network, storage, security và operational behavior tương đương.

### 6.3. Node và accelerator

Workload cần GPU, local NVMe, huge pages, low-latency NIC hoặc specialized instance có thể phụ thuộc phần cứng và driver cụ thể. Abstraction chung có thể cung cấp resource class, nhưng phải công bố availability, topology, quota, driver và cost khác nhau.

### 6.4. Serverless portability

Function API có thể tương tự giữa nhà cung cấp nhưng khác runtime limit, concurrency, cold start, retry, event source mapping, execution duration và identity. Mang source code sang provider khác chưa đủ; phải chuyển trigger, event semantics, secret, observability và deployment configuration.

## 7. Network abstraction và giới hạn kết nối

### 7.1. Network không chỉ là subnet và route

Hybrid/multi-cloud network còn gồm IP address planning và overlap; DNS resolution, private zone và service discovery; VPN, dedicated connectivity và routing domain; firewall/security group và network policy; NAT, egress gateway và public IP; private endpoint/service endpoint; load balancer, health check và source IP behavior; MTU, routing convergence, latency và packet inspection.

### 7.2. Cùng một policy, implementation khác nhau

Một policy “service A chỉ gọi database B qua private network” có thể được thực hiện bằng security group ở cloud này, network policy ở cluster khác, firewall appliance ở data center và private service endpoint ở provider thứ ba. Một API chung có thể mô tả intent, nhưng cần test reachability thực tế, path, DNS và failure behavior.

### 7.3. IP và DNS portability

Private IP không thể luôn giữ nguyên khi chuyển region/provider. CIDR có thể trùng với data center hoặc VPC hiện có. DNS TTL không bảo đảm mọi client cập nhật đồng thời. Cần overlap window, resolver plan, connection draining và route withdrawal có thứ tự.

### 7.4. Egress và data gravity

Một workload portable về compute nhưng dữ liệu nằm ở provider khác có thể chịu latency và egress cost lớn. Di chuyển compute không tự di chuyển data gravity. Cần tính data volume/change rate, network bandwidth/transfer price, replication lag/consistency, cross-region route, service call latency/failure dependency và reverse migration.

## 8. Identity và security abstraction

### 8.1. Identity model không đồng nhất

IAM của từng provider có khái niệm principal, role, policy, trust relationship, resource policy và condition khác nhau. Một role abstraction chung có thể không diễn đạt được policy condition hoặc delegation đặc thù.

### 8.2. Workload identity

Có thể chuẩn hóa intent như “workload này được đọc bucket X” và ánh xạ sang managed identity, federated service account hoặc role cụ thể. Nhưng cần xác minh issuer/audience, trust policy/subject mapping, token lifetime/rotation, permission evaluation, cross-account boundary và audit principal.

### 8.3. Least privilege và policy translation

Không dịch policy bằng cách bỏ qua điều kiện không hỗ trợ. Nếu provider B không thể biểu diễn một điều kiện bắt buộc ở provider A, adapter phải từ chối hoặc yêu cầu thiết kế thay thế được phê duyệt. “Policy gần giống” có thể tạo lỗ hổng cross-cloud.

### 8.4. Key management

KMS/HSM service có thể khác nhau về key exportability, rotation, multi-region semantics, grant, audit và deletion window. Một abstraction encrypt/decrypt không thể tự bảo đảm key recovery, data portability hoặc compliance. Cần giữ key reference, encryption context và kế hoạch giải mã cho dữ liệu cũ.

## 9. Storage, database và consistency

### 9.1. Object storage

Các object store thường có API tương đồng nhưng khác ở versioning/delete marker, object lock/retention/legal hold, lifecycle transition/retrieval fees, consistency semantics, multipart upload/copy behavior, event notification, IAM/resource policy và encryption context.

Adapter phải công bố các khác biệt ảnh hưởng tính đúng đắn. Không được giả định mọi object store có cùng semantics chỉ vì đều hỗ trợ put/get.

### 9.2. Block và file storage

Storage class khác nhau về IOPS, throughput, latency, attachment scope, multi-attach, snapshot consistency và failure domain. File service có khác biệt về protocol, locking, identity mapping và throughput scaling. Workload cần shared filesystem hoặc low-latency block device phải test tại target environment.

### 9.3. Managed database

Database portability thường khó hơn ứng dụng vì engine/version và extension; SQL dialect, collation, timezone và data type; transaction/isolation behavior; replication/CDC và failover; backup/PITR và restore duration; connection pooling/authentication; indexing/query planner/performance; maintenance window, patch và upgrade.

Chạy cùng engine không đảm bảo hiệu năng hoặc operational semantics giống nhau. Managed service có thể giới hạn superuser, extension, parameter và access vào filesystem.

### 9.4. Data portability

Kế hoạch di chuyển cần xem schema, data, index, sequence, constraint, trigger, object reference, event history, encryption và application compatibility. Export/import có thể làm mất metadata hoặc thay đổi semantics nếu không kiểm thử.

### 9.5. Consistency model

Một provider có thể hỗ trợ global database với consistency tùy chọn; provider khác yêu cầu replication architecture do khách hàng tự quản. Đừng che khác biệt này sau một API replicate data. Hãy định nghĩa consistency requirement và failover RPO cụ thể.

## 10. Messaging và event semantics

### 10.1. API giống nhau chưa đủ

Queue và event broker có thể khác nhau về at-least-once/at-most-once delivery, ordering scope, visibility timeout/lease, redelivery và dead-letter behavior, partition/consumer group/offset, retention/replay, transaction, deduplication và throughput quota.

### 10.2. Exactly-once cần xét toàn workflow

Một broker quảng bá exactly-once semantics trong phạm vi nhất định không bảo đảm side effect tới database hoặc payment provider chỉ xảy ra một lần. Cần idempotency, deduplication, transactional outbox/inbox hoặc protocol phù hợp với toàn workflow.

### 10.3. Event schema và compatibility

Schema registry, serialization, compatibility rules và retention của schema có thể khác. Nếu event phải di chuyển giữa provider, cần contract versioning, schema export, replay test và kiểm tra backward/forward compatibility.

## 11. Observability và operational semantics

### 11.1. Chuẩn hóa tín hiệu, không giả định backend giống nhau

OpenTelemetry có thể chuẩn hóa instrumentation và export format, nhưng metrics backend, log indexing, trace sampling, retention, alert evaluation và cost model có thể khác. Một dashboard portable không tự bảo đảm số liệu có cùng định nghĩa hoặc cảnh báo có cùng độ trễ.

### 11.2. Semantic conventions

Chuẩn hóa service name, environment, operation, resource attributes và trace propagation giúp liên kết telemetry. Tuy nhiên, provider-native metrics có thể có đơn vị, aggregation interval và sampling khác. Cần mapping rõ trước khi so sánh.

### 11.3. Runbook portability

Runbook không thể chỉ ghi “restart service” nếu từng platform có quy trình drain, failover, scale, restore và audit khác nhau. Có thể chuẩn hóa decision tree và evidence cần thu thập, nhưng thao tác chi tiết cần adapter/runbook theo provider.

### 11.4. Incident ownership

Multi-cloud tạo thêm nhà cung cấp, support contract, control plane và escalation path. Cần xác định ai điều phối sự cố cross-provider, ai có quyền đổi route và ai chịu trách nhiệm service end-to-end.

## 12. Abstraction leakage

### 12.1. Khi chi tiết bên dưới lộ ra

Abstraction leakage xảy ra khi ứng dụng tưởng đang dùng một contract chung nhưng phải hiểu hoặc phản ứng với khác biệt implementation. Ví dụ adapter trả lỗi capacity unavailable nhưng mỗi provider có retryability khác; storage API chung có consistency khác nhau; network adapter không thể giữ private IP; database adapter yêu cầu query hint riêng; identity adapter không thể map một policy condition.

### 12.2. Dấu hiệu abstraction sai

- Nhiều cờ provider-specific xuất hiện trong API chung.
- Consumer phải kiểm tra tên provider để chọn behavior.
- Adapter chứa nhiều fallback không được kiểm thử.
- Contract mô tả capability nhưng không mô tả failure semantics.
- Developer phải đọc tài liệu từng provider để biết API nội bộ thực sự làm gì.
- Một thay đổi nhỏ ở provider buộc sửa nhiều consumer.

### 12.3. Cách giảm leakage

- Thu hẹp contract vào capability thực sự chung.
- Công bố capability profile và constraint.
- Cho phép extension có namespace rõ ràng.
- Tách control plane API với data plane behavior.
- Contract test cho từng adapter.
- Không giả lập thành công khi provider không đáp ứng semantics.
- Log rõ adapter/provider và lỗi gốc để hỗ trợ chẩn đoán.

## 13. Thiết kế platform API: common core và extension

### 13.1. Common core

Common core nên chứa các khái niệm ổn định: service identity/ownership, artifact reference/version, resource lifecycle intent, environment/region target, health/readiness contract, security baseline, telemetry conventions, cost tags và quota metadata.

### 13.2. Capability extension

~~~yaml
workload:
  name: analytics-api
  runtime: container
  image: registry.example.com/analytics/api@sha256:abc123
  common:
    replicas:
      min: 3
      max: 12
    health:
      readiness_path: /ready
    identity:
      access_profile: analytics-read
  providerExtensions:
    providerA:
      compute:
        accelerator: gpu-class-x
      network:
        private_endpoint: true
~~~

Đây là ví dụ minh họa. Extension cần được cô lập và ghi rõ phạm vi; tránh đưa provider-specific field vào common core chỉ để một workload dùng được.

### 13.3. Không biến platform API thành một cloud SDK khổng lồ

Nếu platform API cố bọc mọi feature của mọi provider, nó sẽ tái tạo toàn bộ provider API nhưng với semantics kém rõ hơn. Một platform nên tập trung vào paved road và policy có giá trị lặp lại, không nhất thiết làm mọi resource đều portable.

## 14. IaC abstraction và module đa nhà cung cấp

### 14.1. Reuse module có giới hạn

Terraform module hoặc IaC component có thể tái sử dụng naming, tagging, policy và input validation. Nhưng module tạo database ở hai provider có thể cần resource graph khác hoàn toàn. Cố ép cùng một module với hàng chục conditional có thể khó bảo trì hơn hai implementation riêng.

### 14.2. Pattern lựa chọn

- Shared module: cho logic thực sự chung, ví dụ labels, naming, validation.
- Provider-specific module: cho resource graph và lifecycle khác nhau.
- Composition layer: module cấp cao chọn implementation theo capability/environment.
- Policy layer: áp guardrail thống nhất độc lập với resource syntax.

### 14.3. State và lifecycle không đồng nhất

IaC state của từng provider có resource identity, import, replacement và dependency semantics riêng. Không giả định state có thể chuyển từ provider A sang provider B bằng cách đổi provider declaration. Migration thường là tạo resource mới, chuyển dữ liệu/traffic và retire resource cũ.

### 14.4. Plan phải thể hiện replacement

Khi property buộc resource replacement, pipeline cần làm rõ downtime, data preservation, parallel capacity và destructive operation. Một abstraction che mất việc resource sẽ bị destroy/recreate là nguy hiểm.

## 15. Hiệu năng và reliability của abstraction layer

### 15.1. Thêm một hop có chi phí

Nếu mọi request đi qua proxy/gateway/adapter trung tâm, lớp này có thể thêm network hop, serialization, connection pool và failure dependency. Với data plane nóng, overhead nhỏ trên mỗi request có thể cộng thành đáng kể.

### 15.2. Control plane hay data plane?

Ưu tiên dùng abstraction ở control plane để provision, validate và quản lý lifecycle. Data plane runtime nên gọi trực tiếp dependency ổn định khi cần hiệu năng hoặc semantics native, có thể thông qua SDK/adapter mỏng trong process. Không nhất thiết mọi data call phải đi qua một central platform service.

### 15.3. Blast radius

Một abstraction service dùng chung có thể trở thành điểm lỗi ảnh hưởng mọi workload và mọi cloud. Cần HA, rate limit, isolation, fallback và quyền triển khai tách biệt. Nếu adapter lỗi, workload đang chạy có nên tiếp tục hoạt động không? Với nhiều control-plane operation, câu trả lời nên là có thông qua cached configuration hoặc data plane độc lập.

### 15.4. Failure semantics

Abstraction cần xác định timeout, retry, idempotency, partial failure và error mapping. Không map mọi lỗi provider thành một lỗi chung khiến người vận hành mất khả năng phân biệt throttling, permission, quota và outage.

## 16. Chi phí ẩn của portability

### 16.1. Chi phí xây dựng và duy trì

- Adapter, test suite và compatibility matrix.
- Năng lực vận hành nhiều cloud.
- Tooling, security control và policy duplication.
- Network connectivity và data replication.
- Observability pipeline và incident integration.
- Contract, support và vendor management.

### 16.2. Chi phí duplication

Chạy hai platform production có thể cần hai cluster, hai control plane, hai bộ backup, hai pipeline và capacity dự phòng. DR hoặc residency có thể biện minh cho khoản này; nếu không có yêu cầu rõ, nó có thể tạo chi phí lớn mà không tăng giá trị tương xứng.

### 16.3. Egress và data gravity

Chi phí chuyển dữ liệu ra ngoài, cross-region replication, interconnect và retrieval có thể làm migration đắt hơn nhiều so với compute. Phải tính migration bandwidth, full copy, delta sync, dual-running window và reverse migration.

### 16.4. Skills và on-call

Đội ngũ cần hiểu IAM, network, storage, observability và incident semantics của từng provider. Đa dạng nền tảng làm tăng cognitive load, training và số lượng runbook. Abstraction có thể giảm phần việc thường ngày nhưng không xóa yêu cầu hiểu failure mode bên dưới.

## 17. Khi nào nên dùng native service?

Native managed service thường hợp lý khi capability tạo lợi thế đáng kể về độ tin cậy, hiệu năng hoặc tốc độ phát triển; workload gắn chặt với data service và không có migration thường xuyên; operational burden tự vận hành giải pháp portable lớn hơn rủi ro lock-in; tổ chức có chiến lược exit dựa trên export/contract; hoặc business chấp nhận provider dependency và có DR/contractual mitigation.

Ví dụ, dùng managed analytics hoặc database native có thể tốt hơn tự vận hành một bản portable nhiều thành phần nếu workload cần feature, scale và SLA cụ thể.

## 18. Decision framework: chuẩn hóa gì, giữ native gì?

### 18.1. Đánh giá theo capability

Với mỗi capability, chấm hoặc thảo luận:

1. Mức độ cần portability và xác suất phải chuyển.
2. Mức độ semantics giữa provider tương đương.
3. Giá trị của native feature.
4. Performance/latency sensitivity.
5. Security/compliance requirement.
6. Data gravity và migration complexity.
7. Operational skill và support readiness.
8. Tổng chi phí xây dựng, chạy và thoát.

### 18.2. Ma trận lựa chọn minh họa

| Capability | Hướng thường cân nhắc | Lý do |
|---|---|---|
| Container artifact | Chuẩn hóa | Digest và OCI image có tính di động tương đối cao |
| Kubernetes workload API | Chuẩn hóa có giới hạn | API chung hữu ích, nhưng cluster add-on/network/storage khác |
| Naming/tagging/ownership | Chuẩn hóa | Governance và cost allocation cần nhất quán |
| Telemetry instrumentation | Chuẩn hóa | OTel conventions giúp portability và correlation |
| IAM policy | Chuẩn hóa intent, implementation native | Semantics và policy language khác |
| VPC/network | Chuẩn hóa intent, adapter riêng | Topology, route, endpoint và firewall khác |
| Managed database | Native hoặc adapter hẹp | Feature, consistency, backup và operations khác sâu |
| Object storage | Contract hẹp + capability profile | API cơ bản gần nhau nhưng retention/versioning khác |
| Messaging | Chọn theo semantics | Ordering, replay, DLQ và delivery guarantees khác |
| Analytics/AI accelerator | Native khi có giá trị | Feature và hardware khác biệt tạo lợi thế |

Ma trận này chỉ là điểm khởi đầu. Quyết định cuối phải theo workload, không theo khẩu hiệu cloud-agnostic.

### 18.3. Quy tắc dừng abstraction

Nên dừng mở rộng abstraction khi consumer phải biết provider để dùng đúng; contract không thể diễn tả semantics bắt buộc; adapter phức tạp hơn việc dùng native SDK; performance overhead vượt ngân sách; capability chung làm mất feature có giá trị; hoặc test matrix/maintenance cost vượt lợi ích portability.

## 19. Kiểm thử portability và contract

### 19.1. Contract test

Với mỗi adapter, chạy cùng bộ contract test:

- Create/read/update/delete theo lifecycle.
- Security/identity và authorization.
- Error mapping, retry và idempotency.
- Timeout, quota và throttling.
- Data consistency, ordering và durability.
- Observability fields và audit.
- Recovery/backup/restore.

Contract test chứng minh các implementation đáp ứng phần contract chung; nó không chứng minh mọi feature của provider tương đương.

### 19.2. Conformance profile

| Test | Provider A | Provider B | Ý nghĩa |
|---|---|---|---|
| Encryption at rest | Pass | Pass | Requirement chung đạt |
| DLQ retention 72h | Pass | Pass | Messaging baseline |
| FIFO ordering | Pass | Not supported | Capability optional/constraint |
| Cross-region restore | Pass | Partial | Cần DR procedure riêng |
| Workload identity federation | Pass | Pass with different trust mapping | Adapter cần mapping khác |

Không chuyển “Partial” thành “Pass” chỉ để giữ một nhãn thống nhất.

### 19.3. Migration rehearsal

1. Build artifact từ cùng source.
2. Provision môi trường đích bằng IaC.
3. Thiết lập identity, network và secrets.
4. Restore/replicate dữ liệu và kiểm tra consistency.
5. Deploy và kiểm tra runtime.
6. Chuyển traffic thử hoặc chạy shadow traffic.
7. Đo latency, error, cost và operational effort.
8. Thử rollback/exit.

Ghi lại những phần cần provider-specific work. Đây là bằng chứng portability tốt hơn một manifest chạy thành công.

## 20. Chiến lược exit và giảm lock-in có chủ đích

### 20.1. Lock-in không phải luôn xấu

Mọi nền tảng đều tạo một mức phụ thuộc: kỹ năng, API, data format, tooling, hợp đồng hoặc location. Lock-in có thể đổi lấy managed capability, reliability và tốc độ. Câu hỏi đúng là mức phụ thuộc có được hiểu, chấp nhận, định giá và có phương án khi điều kiện thay đổi hay không.

### 20.2. Exit plan theo lớp

- Artifact: source, build recipe, image digest, SBOM và provenance.
- Configuration: IaC, deployment manifest, policy và service catalog.
- Identity: principal mapping, secret rotation và federation.
- Data: export format, schema, encryption/key strategy và transfer.
- Network: DNS, IP/route, endpoint và connectivity.
- Operations: dashboard, alert, audit, runbook và support contacts.
- Commercial: contract term, egress price, license, support và termination clause.

### 20.3. Exit cost và exit time

Ước tính thời gian dựng platform đích; data copy + delta sync + validation; dual-running và traffic cutover; tái lập identity/security/integration; engineering/on-call và business downtime; egress, license và contract termination.

Không nên tuyên bố “có thể chuyển trong vài ngày” nếu chưa tính data volume, bandwidth và dependency.

## 21. Ví dụ: Booking Platform trên hai cloud

### 21.1. Yêu cầu

Booking Platform muốn chạy API ở hai cloud để đáp ứng yêu cầu region và tránh phụ thuộc một nhà cung cấp. Workload gồm API stateless, database giao dịch, object storage, queue, identity và observability.

### 21.2. Phân loại abstraction

| Thành phần | Cách tiếp cận |
|---|---|
| Booking API container | Build một artifact OCI, pin digest |
| Deployment intent | Platform API chung cho health, replicas và ownership |
| Kubernetes cluster | Adapter/IaC riêng cho network, node và add-on |
| Workload identity | Contract quyền theo capability, mapping native |
| Database | Native managed DB theo provider; schema/migration chung nhưng failover riêng |
| Object storage | Adapter hẹp cho put/get; versioning/object lock qua capability profile |
| Queue | Contract event schema chung; adapter riêng cho ordering, DLQ và replay |
| Telemetry | OTel instrumentation chung, backend và alert mapping riêng |

### 21.3. Kiến trúc

~~~mermaid
flowchart TB
    APP[Booking application] --> PLATFORM[Internal platform contract]
    PLATFORM --> COMMON[Common: identity intent, tags, health, telemetry]
    COMMON --> A[Provider A adapters]
    COMMON --> B[Provider B adapters]
    A --> ADB[(Managed DB A)]
    A --> AQ[Queue A]
    A --> AS[(Object store A)]
    B --> BDB[(Managed DB B)]
    B --> BQ[Queue B]
    B --> BS[(Object store B)]
    APP --> NATIVE[Selected provider-native capabilities]
~~~

### 21.4. Rủi ro còn lại

Container digest giống nhau không bảo đảm runtime performance giống nhau. Database failover không thể tự chuyển transaction state. Queue delivery/order khác có thể làm thay đổi workflow. Workload identity cần mapping mới; object retention và KMS key cần kiểm thử. Nếu hai cloud cùng nhận write booking, cần thiết kế data ownership/consistency riêng thay vì giả định platform contract giải quyết được.

### 21.5. Tiêu chí thành công

- API stateless deploy được trên hai môi trường từ cùng artifact.
- Security baseline và ownership policy đạt trên cả hai.
- Capability profile ghi rõ feature chung và khác biệt.
- Database, queue và object semantics được kiểm thử theo yêu cầu nghiệp vụ.
- Latency/cost của cross-cloud dependency nằm trong ngưỡng.
- Runbook/monitoring có provider-specific step rõ.
- Migration/DR rehearsal đạt recovery target đã phê duyệt.
- Exit plan có số liệu về thời gian, chi phí và dữ liệu.

## 22. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Cho rằng container là portable hoàn toàn | Bỏ qua kernel, network, storage, identity và runtime | Đánh giá portability theo nhiều tầng |
| Chỉ hỗ trợ lowest common denominator | Mất native feature, hiệu năng và giá trị | Common core + capability extension |
| Cùng tên API được xem là cùng semantics | Khác biệt consistency, retry hoặc failure bị che | Contract mô tả behavior và test |
| Một IaC module cho mọi provider bằng nhiều conditional | Module khó hiểu và lifecycle không rõ | Composition với provider-specific module |
| Che provider-specific constraint | Workload lỗi ở production hoặc migration | Capability profile và fail validation |
| Một central abstraction service nằm trên mọi request | Thêm hop và điểm lỗi tập trung | Đặt abstraction chủ yếu ở control plane |
| Chuẩn hóa IAM bằng cách bỏ policy condition | Least privilege suy yếu | Mapping native và từ chối nếu không biểu diễn được |
| Tin object API put/get tương đương | Mất retention, versioning hoặc consistency | Contract test và capability profile |
| Bỏ qua data gravity và egress | Migration chậm và đắt | Rehearsal, transfer model và data locality |
| Không thử vận hành ở cloud thứ hai | Không phát hiện thiếu skill/runbook | DR/migration exercise thực tế |
| Gọi lock-in là thất bại mặc định | Tăng complexity không cần thiết | Định giá lock-in và lợi ích native |
| Không có exit plan | Bị động khi contract, pricing hoặc risk thay đổi | Exit strategy theo artifact, data, identity và operations |

## 23. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Platform contract có rõ owner, capability và runbook theo provider? | Common governance, adapter contract test và provider-specific runbook |
| **Security** | Policy translation có giữ least privilege và key semantics? | Intent chung, identity/key native, fail validation và audit |
| **Reliability** | Lớp abstraction có thêm điểm lỗi hoặc che failure semantics? | Control-plane abstraction, adapter HA, contract test và fault exercise |
| **Performance Efficiency** | Có hy sinh native feature, locality hoặc latency để giữ API chung? | Chỉ chuẩn hóa phần cần thiết, đo critical path và data gravity |
| **Cost Optimization** | Portability có tạo duplicated platform, egress và skills cost? | TCO model, cost per workload và exit-cost review |
| **Sustainability** | Có vận hành nhiều bản platform hoặc transfer dữ liệu dư thừa? | Giới hạn duplication, lifecycle policy và workload placement hợp lý |

Abstraction tốt làm rõ quyết định và giảm công việc lặp. Abstraction yếu che khuất semantics, khiến lỗi xuất hiện muộn ở runtime hoặc lúc migration. Đánh giá phải dựa trên capability contract, test evidence và tổng chi phí, không dựa vào số lượng provider mà một API tuyên bố hỗ trợ.

## 24. Bài tập áp dụng

### Bài tập A — Queue abstraction

Platform API cung cấp send/receive chung. Ứng dụng yêu cầu FIFO ordering và deduplication, nhưng provider đích chỉ hỗ trợ ordering theo partition.

**Câu hỏi:** Adapter nên làm gì?

**Gợi ý:** Công bố capability không đáp ứng và fail validation hoặc yêu cầu thiết kế partition/idempotency phù hợp. Không tuyên bố FIFO toàn cục nếu implementation không bảo đảm.

### Bài tập B — Kubernetes portability

Deployment manifest chạy trên hai cluster, nhưng workload chỉ có thể mount storage trên provider A.

**Câu hỏi:** Portability đang dừng ở tầng nào?

**Gợi ý:** Artifact/runtime API có thể portable, nhưng platform/storage integration chưa portable. Cần CSI/storage profile, data migration và test mount/failover.

### Bài tập C — IAM policy translation

Một policy yêu cầu access chỉ khi request có condition theo network origin và resource tag. Adapter provider B không thể biểu diễn đủ hai điều kiện.

**Câu hỏi:** Có nên bỏ condition không?

**Gợi ý:** Không. Từ chối capability hoặc thiết kế compensating control được security owner phê duyệt, có audit và test; không hạ least privilege âm thầm.

### Bài tập D — Native database

Provider A có managed database với replication và PITR tốt; provider B yêu cầu tự vận hành nhiều thành phần để đạt behavior tương tự.

**Câu hỏi:** Có nên ép dùng database portable?

**Gợi ý:** So sánh reliability, operations, cost, data portability và exit need. Có thể dùng native database và đầu tư export/restore procedure thay vì tự vận hành một lớp portable tốn kém.

### Bài tập E — Central adapter outage

Platform adapter trung tâm xử lý mọi request storage. Khi adapter gặp outage, cả hai cloud đều không đọc được object dù object service vẫn khỏe.

**Câu hỏi:** Ranh giới abstraction nên thay đổi thế nào?

**Gợi ý:** Đưa abstraction về control plane hoặc dùng adapter in-process/data plane có HA; tránh central synchronous hop cho mọi data access; xác định cache/fallback và failure isolation.

### Bài tập F — Exit cost

Workload container portable nhưng database có 20 TB, egress đắt, queue event chỉ giữ 24 giờ và identity tích hợp sâu với provider.

**Câu hỏi:** Kế hoạch exit cần bao gồm gì?

**Gợi ý:** Data seeding + delta sync, schema/consistency validation, event archive/replay, identity remapping, dual-run/cutover, network/DNS, cost model, rollback và rehearsal. Container image chỉ là một phần nhỏ.

## 25. Checklist thiết kế lớp trừu tượng multi-cloud

- [ ] Đã xác định mục tiêu portability và tầng cần portable (source, artifact, runtime, platform, data, operations).
- [ ] Mỗi abstraction có owner, consumer, contract và failure semantics.
- [ ] Contract mô tả capability, consistency, durability, retry, quota và security.
- [ ] Có capability profile để công bố feature required/optional và constraint.
- [ ] Không âm thầm hạ semantics về lowest common denominator.
- [ ] Common core chỉ chứa khái niệm thực sự ổn định; extension provider-specific có namespace rõ.
- [ ] Container/runtime portability đã xét kernel, CNI, CSI, identity và accelerator.
- [ ] Network design đã xét CIDR, DNS, IP, route, private endpoint và egress.
- [ ] IAM/key mapping giữ nguyên least privilege, audit và encryption requirements.
- [ ] Database/object/queue portability có schema, consistency, retention và replay test.
- [ ] Observability có semantic mapping và runbook provider-specific.
- [ ] IaC module tách common validation với resource graph native.
- [ ] State/import/replacement lifecycle được đánh giá riêng theo provider.
- [ ] Abstraction layer có HA, timeout, backpressure và failure isolation.
- [ ] Data gravity, egress, dual-running và migration cost được ước tính.
- [ ] Có contract/conformance test trên mọi adapter và version hỗ trợ.
- [ ] Đã thực hiện migration rehearsal cho workload đại diện.
- [ ] Native service được sử dụng khi lợi ích vượt chi phí lock-in có kiểm soát.
- [ ] Exit plan bao gồm artifact, config, identity, data, network, operations và contract.
- [ ] Quyết định portability gắn với SLO, security, TCO và business requirement.

**Điểm cốt lõi:** lớp trừu tượng chung chỉ nên che đi khác biệt không quan trọng với workload và phải giữ nguyên semantics quan trọng. Container, Kubernetes hay IaC giúp giảm một phần phụ thuộc nhưng không làm identity, network, storage, database, queue, operations và cost trở nên giống nhau. Hãy chuẩn hóa common core, công bố capability profile, dùng native extension khi cần và kiểm chứng bằng contract test cùng migration rehearsal. Mục tiêu không phải loại bỏ mọi lock-in, mà là chọn mức phụ thuộc có chủ đích và có phương án thoát khả thi.
