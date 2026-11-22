# Chi phí hạ tầng tối thiểu khi có nhiều dịch vụ

**Nhóm kiến thức:** Chi phí và đánh đổi trong Software Design, System Architecture và Microservices.

Một hệ thống có nhiều microservice không chỉ phải trả tiền cho CPU dùng để xử lý request. Ngay cả khi lưu lượng gần bằng không, mỗi dịch vụ có thể vẫn cần một hoặc nhiều instance luôn sẵn sàng, bộ nhớ runtime, health check, kết nối cơ sở dữ liệu, network routing, log, metric, trace, secrets, bản sao dự phòng và pipeline triển khai. Tổng các khoản cần duy trì để hệ thống tồn tại và đáp ứng mức phục vụ cam kết tạo nên **chi phí hạ tầng tối thiểu (infrastructure cost floor)**.

Khi tách một ứng dụng thành nhiều service, tổ chức mua được những khả năng có giá trị: phát hành theo domain, mở rộng độc lập, hạn chế phạm vi lỗi, tách quyền dữ liệu và giao quyền sở hữu cho nhiều nhóm. Nhưng mỗi ranh giới tiến trình và vận hành mới có chi phí. Nếu 30 service đều phải chạy hai replica Spring Boot dù traffic chỉ vài request mỗi phút, phần nền có thể lớn hơn phần xử lý nghiệp vụ. Ngược lại, ở hệ thống có tải lệch mạnh giữa các domain, việc tách service để scale đúng chỗ có thể tiết kiệm tổng chi phí.

Bài học giúp định lượng **fixed cost, usage-based cost, shared platform cost và operational TCO**; lập mô hình capacity; đánh giá chi phí của VM, Kubernetes, managed container và serverless; tính tài nguyên Java/JVM; thiết kế HA; tối ưu non-production; và quyết định khi nào microservices thật sự mang lại lợi ích xứng đáng.

## 1. Cost floor là gì?

**Cost floor** là khoản chi tối thiểu gần như phải trả để kiến trúc đạt trạng thái sẵn sàng đã định, trước khi tính thêm tải của người dùng. Nó không nhất thiết là một khoản phí cố định tuyệt đối: có phần tăng theo số service, có phần tăng theo bậc thang capacity và có phần phát sinh khi bật HA hoặc một chính sách bảo mật.

~~~text
Tổng chi phí / tháng
    |
    +-- COST FLOOR
    |     +-- Compute tối thiểu, min replicas, warm instances
    |     +-- Control plane, gateway, load balancer, NAT
    |     +-- Database, broker, cache, backup
    |     +-- Telemetry, secrets, registry, hệ thống nền
    |     +-- Môi trường thử nghiệm và năng lực vận hành
    |
    +-- VARIABLE COST
          +-- Request, CPU/GB-duration, invocation, I/O
          +-- Network egress, inter-zone/cross-region traffic
          +-- Lượng log, trace, event, storage theo tải
          +-- Autoscaling trên mức tối thiểu
~~~

**Chi phí nền của một service không chỉ là Pod chạy service ấy.** Một Pod nhỏ có thể cần DB HA, broker, router, log pipeline và nhân sự hỗ trợ. Không tính những phần này khiến kiến trúc nhiều dịch vụ trông rẻ hơn thực tế.

Cũng cần phân biệt:
- **Cost floor theo workload:** tài nguyên cần cho một service khi nhàn rỗi.
- **Cost floor theo platform:** cluster, control plane, ingress, observability, pipeline và công cụ chung.
- **Cost floor theo nghiệp vụ:** mọi thành phần tối thiểu để hoàn thành một critical journey, ví dụ Checkout phải có Orders, Payment, Inventory và data tier hoạt động.
- **Cost per successful transaction:** phân bổ chi phí theo kết quả nghiệp vụ, không phải chỉ theo request kỹ thuật.

Một kiến trúc có floor cao có thể hợp lý nếu nó mua sự tin cậy, mức độ tuân thủ hoặc khả năng tăng trưởng đủ lớn.

## 2. Tại sao số service lớn làm baseline tăng?

Một monolith có thể chứa nhiều module trong cùng process:

~~~text
Client -> Load Balancer -> Java application
                          +-- Catalog
                          +-- Checkout
                          +-- Inventory
                          +-- Notification
                                 |
                                 +-- Database
~~~

Nếu tách thành microservices:

~~~mermaid
flowchart TB
    U["Client"] --> GW["Gateway"]
    GW --> C["Catalog Service"]
    GW --> O["Checkout Service"]
    O --> P["Payment Service"]
    O --> I["Inventory Service"]
    O --> MQ[("Broker")]
    MQ --> N["Notification Worker"]
    C --> DB1[("Catalog DB")]
    O --> DB2[("Orders DB")]
    P --> DB3[("Payment DB")]
    I --> DB4[("Inventory DB")]
~~~

Các overhead có thể xuất hiện ở **mỗi service**:
1. Process/container riêng với memory nền.
2. Replica tối thiểu cho HA và rolling deployment.
3. Service discovery, ingress/routing, network policies.
4. CPU/heap của HTTP server, framework và dependency.
5. Pool kết nối DB/cache/broker.
6. Danh tính runtime, secrets, certificates và audit.
7. Log, metric, trace, health endpoints.
8. Build, image, registry, deployment và runtime config.
9. Owner, on-call, runbook, incident, patching và nâng cấp.
10. Contract giữa service cùng kiểm thử tương thích.

Không phải tất cả khoản trên đều nhân chính xác với số dịch vụ. Ví dụ gateway hoặc cluster có thể dùng chung, còn node mới chỉ được thêm khi requests vượt capacity. Nhưng **sự độc lập có giá**, và phải được mua vì nhu cầu cụ thể.

## 3. Phân loại chi phí trước khi tính

| Nhóm | Ví dụ | Đặc điểm |
|---|---|---|
| Theo service | Min replica, sidecar, resource request | Thường tăng với số workload luôn bật |
| Theo cluster/môi trường | Control plane, node pool, ingress | Chia sẻ và tăng theo bậc thang |
| Theo dữ liệu | Managed DB, search, cache, broker, backup | Có thể là phần floor lớn nhất |
| Theo mạng | LB, NAT, public IP, egress, private endpoint | Có cả mức nền và mức theo traffic |
| Theo telemetry | Log ingestion, metric cardinality, trace retention | Tăng theo service và hoạt động |
| Theo release | Build runner, artifact registry, scans | Tăng theo số repo/build và retention |
| Theo bảo mật | Secrets, KMS, certificates, audit | Một phần trực tiếp, một phần công người |
| Theo môi trường | Staging, dev, preprod, preview | Có thể nhân nhiều lần capacity |
| Theo vận hành | On-call, recovery, patch, integration | Không luôn có trên cloud bill |
| Theo rủi ro | Multi-zone, DR, spare capacity | Chi phí mua khả năng chịu lỗi |

Một hệ thống nên có **một catalog tài nguyên có owner** và một quy tắc phân bổ rõ. Không gán chung tất cả vào một dòng “Kubernetes cost” rồi cho rằng mỗi service không có chi phí khác biệt.

## 4. Mô hình tổng chi phí sở hữu

Một mô hình sơ bộ:

\[
C_{\text{total}}=C_{\text{compute}}+C_{\text{network}}+C_{\text{data}}+C_{\text{platform}}+C_{\text{telemetry}}+C_{\text{storage}}+C_{\text{nonprod}}+C_{\text{operations}}
\]

Trong đó:
- **Compute:** node, VM, min instances, capacity autoscale.
- **Network:** LB, NAT, egress, cross-zone, VPN/private connectivity.
- **Data:** DB, broker, cache, search, replication.
- **Platform:** control plane, registry, CI/CD, secrets và tooling nếu chưa tính ở nhóm khác.
- **Telemetry:** log/metrics/traces, collector, alerting.
- **Storage:** disk, snapshot, backup, retention.
- **Nonprod:** staging, performance test, preview và môi trường dev.
- **Operations:** công vận hành, incident, patch, diễn tập, compliance.

Mô hình này là khung tư duy, **không phải bảng giá**. Cần tránh tính trùng, ví dụ phí node tính một lần chứ không cộng thêm giá CPU giả định của từng Pod như khoản chi thật. Một PaaS có thể đã bao gồm control plane và một phần network trong đơn giá.

Với service \(i\), giả sử có \(r_i\) replica phải chạy \(H\) giờ và giá compute quy đổi \(c_i\) mỗi giờ:

\[
C_{\text{compute floor},i}\approx H\times r_i\times c_i
\]

Nếu dùng cluster node chung, \(c_i\) là giá trị **phân bổ** chứ không nhất thiết là đơn giá trực tiếp trên hóa đơn. Giá theo node có bậc thang khi cần cấp thêm máy.

## 5. Replica tối thiểu tạo ra phần chi phí không tránh được

Một API production đôi khi cần ít nhất hai instance để tiếp tục phục vụ khi một process restart hoặc rolling deployment. Một số hệ thống còn cần replica phân bố qua zone độc lập.

| Workload | Mức nền có thể xem xét | Rủi ro/cần kiểm chứng |
|---|---|---|
| Sandbox cá nhân | 0 hoặc 1 replica khi dùng | Cold start/downtime chấp nhận |
| Internal tool ít quan trọng | 1 instance | Một điểm lỗi |
| API production có SLO | Nhiều replica + LB | Phân vùng lỗi và startup |
| Payment/critical journey | Multi-zone, capacity và data HA | RTO/RPO, tính đúng dữ liệu |
| Scheduled job | 0 worker khi idle nếu nền tảng hỗ trợ | Deadline, trigger, retry |
| Continuous consumer | Một hoặc nhiều consumer liên tục | Broker lifecycle, partition, lag |

Không có quy tắc “service nào cũng phải có hai replica”. Quyết định phụ thuộc mức tác động khi ngừng, traffic, thời gian khởi động, RTO và yêu cầu HA.

### 5.1. Ví dụ 12 service chạy tối thiểu hai replica

Mỗi replica request 0,25 vCPU và 512 MiB:

~~~text
Services:                12
Min replicas / service:   2
Application Pods:        24
Total requested CPU:     12 × 2 × 0,25 = 6 vCPU
Total requested memory:  12 × 2 × 512 MiB = 12 GiB
~~~

Đây là **resource requests scheduler**, chưa phải giá tiền và chưa tính DNS, DaemonSet, CNI, telemetry, ingress, rolling surge, backup hoặc headroom. Khi chọn node count cần xét cả CPU/RAM, topology, failure modes và Pod density.

Nếu hệ thống có 40 service tương tự, floor requests tăng thành 20 vCPU và 40 GiB trước khi xét việc một số service thậm chí không có traffic. Số đó cho thấy tại sao tách dịch vụ quá nhỏ làm phần nền tăng.

## 6. JVM và Spring Boot có overhead trên mỗi process

Một service Java có chi phí memory/CPU nền từ:
- Heap khởi tạo và class/object graph.
- Class metadata, metaspace, JIT code.
- Thread stacks, direct buffer và native memory.
- HTTP server, thread pools và connection pools.
- Spring context, security filters, serializer.
- Logging, metrics và health probes.
- Cache cục bộ và thư viện tích hợp.

Khi tách 1 process thành 20 process, một số overhead trở thành **20 lần khởi tạo**. Nó không có nghĩa mọi service tiêu thụ cùng lượng RAM; cần đo RSS thật.

Ví dụ minh họa: mỗi replica idle dùng 300 MiB RSS, có 20 service × 2 replica:

~~~text
20 × 2 × 300 MiB = 12.000 MiB ≈ 11,72 GiB RSS idle
~~~

Con số 300 MiB **chỉ là giả định**, không phải đặc tả Spring Boot. Ứng dụng chạy native image, ít bean hoặc profile tải khác có thể có footprint khác đáng kể.

**Xmx không bằng RSS.** Nếu memory limit 512 MiB và heap max gần 512 MiB thì native memory/metaspace/thread có thể khiến container OOM. Rightsizing phải dựa trên working set/RSS và peak, không chỉ heap used.

### 6.1. Các metric JVM nên đo

- CPU idle và CPU khi peak.
- RSS, heap used/committed/max, native memory.
- Metaspace, thread count, direct buffer.
- GC pause và allocation rate.
- Startup-to-readiness, cold start.
- DB pool active/idle/wait.
- p95/p99 latency và OOMKilled/CPU throttling.

Một ứng dụng có CPU idle 2% vẫn có thể cần CPU headroom để vượt peak hoặc khởi động đủ nhanh khi scale.

## 7. Kubernetes: chi phí node, packing và fragmentation

Với Kubernetes trên VM node, cloud thường tính phí **node đang hoạt động** cùng các dịch vụ hỗ trợ. Pod requests là đầu vào scheduling, không nhất thiết tạo dòng hóa đơn riêng cho mỗi Pod.

~~~text
3 nodes:
A: 3,5 vCPU / 12 GiB allocatable
B: 3,5 vCPU / 12 GiB allocatable
C: 3,5 vCPU / 12 GiB allocatable

Total allocatable: 10,5 vCPU / 36 GiB
Application requests: 6 vCPU / 12 GiB
~~~

Không thể kết luận 3 node là đủ HA chỉ bằng tổng requests. Còn phải tính cách Pod phân bố theo zone, anti-affinity, PDB, rolling surge, DaemonSets và năng lực khi mất node.

### 7.1. Fragmentation

~~~text
Node A còn 0,4 CPU, 5 GiB RAM
Node B còn 1,8 CPU, 0,5 GiB RAM
Node C còn 0,6 CPU, 2 GiB RAM

Pod mới cần 1 CPU, 2 GiB RAM
=> Không node nào đủ cả hai điều kiện.
~~~

Dù tổng tài nguyên còn rảnh, Pod vẫn không được schedule. Cluster có thể phải thêm một node nguyên chiếc. Đây là chi phí **theo bậc thang**, không tuyến tính với từng millicore.

### 7.2. Bin packing và headroom

Các yếu tố:
- Resource requests lớn hơn usage thực.
- Node pool chia nhỏ theo team/region/architecture.
- CPU-heavy và memory-heavy không phối hợp tốt.
- DaemonSet/sidecar chiếm tài nguyên.
- Pod anti-affinity và topology spread.
- Yêu cầu dữ liệu/volume theo zone.
- HPA và rolling deployment cần Pod bổ sung.
- Node bị mất và cần reschedule.

Không đặt mục tiêu 100% node utilization nếu production cần phục hồi nhanh. **Headroom là khoản chi có chủ đích để mua khả năng chịu lỗi và giảm thời gian chờ scale.**

## 8. HA và multi-zone có floor riêng

Hai replica trên cùng một node có thể cùng chết khi node hỏng. Để chịu lỗi zone, ứng dụng có thể cần:

~~~text
Zone A                      Zone B
 Checkout replica 1          Checkout replica 2
 Payment replica 1           Payment replica 2
 Catalog replica 1           Catalog replica 2
         \                       /
          ---- Load Balancer -----
~~~

Ngoài replicas ứng dụng còn phải xem:
- Database có failover/replication không?
- Broker có quorum/replication qua failure domains không?
- Gateway/LB có hoạt động khi zone hỏng không?
- Năng lực còn lại có chịu được full traffic không?
- DNS, secrets và control plane có dependency nào đơn điểm lỗi?
- Backup đã được restore thử chưa?
- RTO/RPO có phù hợp business SLO không?

Một cluster trả thêm tiền để giữ 30 service mỗi service 2 replica nhưng dùng một database không HA có thể chưa đạt mục tiêu sẵn sàng. **HA phải được tính theo critical path**, không chỉ số Pod.

### 8.1. Năng lực khi rollout và node failure

Ví dụ 10 replica vừa đủ tải cao điểm, nhưng rolling update muốn tạo thêm 2 Pod. Nếu node đã đầy, rollout có thể Pending. Nếu một zone chết, replica còn lại không đủ capacity.

Kế hoạch cần biết maxSurge, maxUnavailable, PDB, scale-up lag, node autoscaler và thời gian khởi tạo JVM. Cost floor có thể cần headroom cao hơn bình thường; đó là một quyết định gắn với mức độ phục vụ chứ không phải lãng phí mặc định.

## 9. Cluster riêng hay cluster chung?

Một tổ chức có 10 team, mỗi team tạo cluster riêng cho vài service nhỏ. Mỗi cluster có:
- Control plane và node pool.
- Ingress, DNS và policy.
- Registry/CI integration.
- Monitoring/log pipeline.
- Patch/upgrade và quản lý quyền.
- Khả năng dư thừa khi node hỏng.

Tổng idle capacity có thể rất cao. Chia sẻ cluster đa tenant qua namespace, RBAC, NetworkPolicy và quota có thể tận dụng capacity tốt hơn.

Tuy nhiên **namespace không là ranh giới host/kernel riêng**. Nếu tenant chạy mã không tin cậy, dữ liệu nhạy cảm hoặc compliance đòi cách ly vật lý, có thể vẫn cần node pool, sandbox hoặc cluster riêng.

Một phương án trung gian là nhóm cluster theo **mức tin cậy và failure domain**, không theo đúng số team. Quyết định cần cân bằng chi phí, bảo mật, blast radius và năng lực platform team.

## 10. Load balancer và gateway có thể nhân phí cố định

Một mô hình mỗi service public có một LB có thể tạo phí theo số LB và năng lực. Có thể gom nhiều route vào shared gateway:

~~~text
Internet
  |
Shared LB / API Gateway
  |
  +-- /catalog -> Catalog
  +-- /orders  -> Orders
  +-- /pay     -> Payments
~~~

**Shared gateway** thường phù hợp khi service dùng chính sách mạng tương thích, cần một điểm công bố API, có khả năng HA và owner. **LB riêng** có thể hợp lý cho nhóm dữ liệu nhạy cảm, endpoint private, giới hạn tải/đối tác hoặc fault isolation.

Giả sử giá hoàn toàn minh họa mỗi LB là $25/tháng:
- 1 shared LB: $25.
- 12 LB riêng: $300.
- Chênh lệch: $275/tháng.

Không coi số này là báo giá thực. Nhà cung cấp có thể tính phí theo request, byte, rule và capacity, nên phải thay bằng giá hiện hành của sản phẩm.

Không được bỏ gateway bảo mật hoặc gộp toàn bộ traffic vào một điểm lỗi thiếu HA chỉ để tiết kiệm vài khoản.

## 11. Network east–west và NAT

Trong monolith, một phương thức nội bộ thường không tạo RPC qua mạng. Với nhiều service:

~~~text
Checkout -> Inventory -> Pricing -> Promotion -> Customer
~~~

Mỗi hop thêm serialization/deserialization, router, connection, TLS/mTLS, logging, tracing và rủi ro timeout/retry. Một request ngoài có thể sinh 10 RPC nội bộ.

Chi phí liên quan:
- CPU cho proxy/TLS/serialization.
- Network bytes trong zone, giữa zone hoặc region.
- NAT gateway, private networking và egress.
- Cross-region replication.
- Load balancer/egress proxy theo route.

Không phải mọi traffic nội bộ có phí tách riêng, nhưng **CPU, bandwidth và latency vẫn được tiêu thụ**. Nếu một service gọi N lần per item, giảm N+1 bằng batch hoặc read model có thể giúp giảm latency và cả chi phí.

### 11.1. NAT gateway có thể thành khoản nền bất ngờ

NAT thường có phí theo thời gian hoạt động và lượng dữ liệu xử lý tùy dịch vụ. Một container nhỏ cần Internet egress qua NAT có thể phát sinh chi phí vượt compute của chính nó, đặc biệt khi kiến trúc có nhiều environment và nhiều NAT riêng.

Cân nhắc kiến trúc private endpoint, VPC routing, shared egress và giảm data transfer, **nhưng không làm yếu network isolation**. Mỗi thay đổi phải kiểm tra compliance, IAM, firewall và đường giám sát.

## 12. Database-per-service: tách quyền không luôn cần instance vật lý riêng

Trong microservices, service nên **sở hữu dữ liệu và schema của mình**. Nhưng ownership logic không buộc mỗi service phải trả một database server vật lý độc lập trong mọi hoàn cảnh.

| Mô hình | Lợi thế | Rủi ro |
|---|---|---|
| Một DB instance, nhiều schema/DB logic | Chi phí nền thấp, quản lý tập trung | Shared capacity và blast radius |
| Managed instance theo bounded context | Tách tải/quyền/backup hợp lý | Tăng chi phí mỗi domain |
| Dedicated cluster theo service | Isolation cao | Tăng HA/ops/backup floor |
| Managed serverless DB | Có thể phù hợp tải biến động | Min capacity/cold start/giá theo sản phẩm |

Nếu chia sẻ instance:
- Mỗi service có DB user/role và quyền riêng.
- Không cho service khác đọc/ghi trực tiếp schema ngoài quyền sở hữu.
- Có quota connection và query latency.
- Cần kiểm tra ảnh hưởng migration/lock đến tenant khác.
- Backup và phục hồi phải đáp ứng RPO/RTO.
- Có lộ trình tách khi SLO hoặc capacity yêu cầu.

**Chi phí thấp không bù được lỗi thanh toán do schema migration của service ít quan trọng.** Data isolation là quyết định rủi ro, không chỉ quyết định billing.

## 13. Connection pools tăng theo số replica

Giả sử 15 service, mỗi service 2 replica, mỗi replica mở tối đa 20 connection tới DB:

~~~text
15 × 2 × 20 = 600 connections tiềm năng
~~~

Số này chưa phải số connection đang hoạt động, nhưng DB phải có kế hoạch chịu được spike khi autoscale. Khi số service tăng, nhiều pool idle có thể chiếm năng lực và khiến database phải nâng tier dù traffic chưa cao.

Giải pháp:
- Right-size pool mỗi service.
- Kiểm soát tổng maxReplicas × connections/replica.
- Dùng connection proxy/pooler khi phù hợp.
- Tránh tạo pool không cần trong ứng dụng ít tải.
- Theo dõi DB active/idle/wait, CPU, locks và latency.
- Đặt backpressure và rate limit để bảo vệ DB.

Tăng replica để giải quyết API latency khi bottleneck thực là DB có thể làm tình hình tệ hơn. **Compute scale không thể thay thế capacity planning phía sau.**

## 14. Broker, Redis và search cluster tạo stateful baseline

Khi dùng event-driven để tách domain, có thể cần Kafka/RabbitMQ/managed queue, schema registry, DLQ và log retention. Broker có thể cần replication và disk dự phòng.

Cache như Redis có thể cần:
- Instance/cluster tối thiểu.
- Replica/failover.
- Network, memory, key eviction.
- Backup nếu dữ liệu có ý nghĩa bền vững.
- Kế hoạch khi cache miss hàng loạt.

Search cluster có thể cần nhiều node và index replication, khiến baseline đáng kể ngay cả khi lượng search thấp.

Không thêm broker/cache/search chỉ vì danh sách công nghệ của microservices. Mỗi thành phần tăng rủi ro vận hành và chi phí nền; nên chứng minh nó xử lý một nhu cầu về hiệu năng, consistency, decoupling hoặc tìm kiếm đủ quan trọng.

## 15. Observability tăng theo số service, replica và traffic

Chi phí observability gồm:
- Log ingestion và retention.
- Trace span count, sample rate và storage.
- Metric time-series cardinality và scrape/query.
- Agent/collector CPU, RAM và network.
- Dashboard, alert rule, paging và nhân sự điều tra.

Ví dụ có 20 service, mỗi service 2 replica, mỗi replica trung bình ghi 0,5 GiB log/ngày:

~~~text
20 × 2 × 0,5 GiB = 20 GiB/ngày
30 ngày ≈ 600 GiB log ingest
~~~

Ví dụ là giả định. Tỷ lệ log thực tế còn phụ thuộc log level, sampling, request và lỗi. Khi retry storm xảy ra, lượng stack trace có thể tăng nhanh đúng lúc hệ thống đang lỗi.

Nên dùng:
- Structured log với mức cần thiết.
- Retention phân tầng theo yêu cầu vận hành/audit.
- Trace sampling có chủ đích.
- Giới hạn nhãn metric cardinality cao.
- Alert về log ingestion bất thường.
- Bảo vệ PII và secrets trong telemetry.

Không tắt tất cả logging để cắt hóa đơn. Thiếu trace/log có thể làm MTTR tăng và đẩy chi phí tác động kinh doanh cao hơn khoản tiết kiệm.

## 16. Sidecar/service mesh có chi phí theo replica

Nếu mesh dùng sidecar cho mỗi Pod, 24 application Pods có thể kèm 24 proxy containers và control-plane/telemetry.

~~~text
12 services × 2 replicas = 24 application Pods
24 app containers + 24 sidecars (nếu cấu hình một sidecar/Pod)
~~~

Sidecar tiêu thụ CPU/RAM, thêm hop mạng/TLS và số metric/traces. Nhưng nó có thể cung cấp mTLS, traffic routing, identity và policy rất có giá trị. Cần đo:
- Proxy CPU/RSS theo traffic.
- Startup và readiness.
- Chi phí control plane.
- Log/trace của mesh.
- Latency p95/p99.
- Vận hành/nâng cấp policy.

Có mô hình mesh khác không dùng sidecar per Pod; không áp chi phí một kiểu mesh cho mọi sản phẩm.

## 17. CI/CD, artifact và security overhead

Khi số service tăng, số image, build, pipeline và dependency cũng tăng. Các khoản chi gồm:
- Build/test runner minutes.
- Registry storage và image distribution.
- Vulnerability scanning, SBOM, provenance.
- Integration/contract tests.
- Secrets và service accounts per environment.
- Deploy revisions và rollback history.
- Artifact retention và backup.
- Thời gian nâng cấp base image/JDK.

Để giảm lặp:
- Golden path/pipeline templates.
- Build cache và versioned artifacts.
- Test pyramid có contract tests.
- Dọn image/preview hết hạn theo retention.
- Không dựng tất cả microservices cho một unit test.
- Cho service deploy độc lập khi contract không đổi.

**Đừng tắt vulnerability scanning hoặc gộp credential admin chỉ để tiết kiệm.** Tối ưu là tự động hóa bảo mật với guardrail và quy trình ít thủ công.

## 18. Môi trường staging/dev/preview có thể nhân floor

Nếu production có 20 service luôn bật, staging và preprod sao chép cùng cấu hình HA sẽ làm compute baseline tăng đáng kể. Thêm ephemeral environments theo PR có thể tăng nhanh số namespace/node/DB tạm.

| Môi trường | Yêu cầu thường gặp | Phương án giảm floor |
|---|---|---|
| Production | HA, SLO, data security | Không giảm bất chấp rủi ro |
| Staging | Contract/integration/release rehearsal | Capacity nhỏ hơn nếu vẫn đại diện |
| Performance test | Tải và scale behavior | Bật theo lịch, có dữ liệu test |
| Dev shared | Cộng tác hàng ngày | Giới hạn quota và autoscale |
| PR preview | Review thay đổi cô lập | TTL, tự dọn khi PR đóng |
| Personal sandbox | Thử nghiệm | Schedule shutdown/scale-to-zero |

Phân biệt môi trường dùng để **kiểm tra semantic** và môi trường dùng để **chứng minh HA/peak**. Staging một replica có thể đủ cho API integration nhưng không chứng minh rolling deploy multi-zone; cần một cuộc diễn tập trong môi trường phù hợp.

Các tác vụ tiết kiệm:
1. Tắt nonprod ngoài giờ nếu không ảnh hưởng công việc được lập lịch.
2. Dọn preview khi PR đóng.
3. Quota CPU/RAM/storage per environment.
4. Không tạo managed DB production-size cho từng nhánh.
5. Giữ fixture và dữ liệu test đúng thời hạn.
6. Theo dõi resource không owner.
7. Đo chi phí môi trường trên mỗi PR/test run.

## 19. VM, Kubernetes, PaaS và serverless có cấu trúc floor khác nhau

| Mô hình | Phần nền thường gặp | Khi đáng thử |
|---|---|---|
| VM | Máy chạy liên tục, disk, LB, patch OS, HA | Workload đều, phụ thuộc đặc thù |
| Container trên VM | Host/node + registry/monitoring | Muốn artifact bất biến và điều phối vừa phải |
| Managed Kubernetes | Node, control plane (tùy dịch vụ), networking, telemetry | Nhiều workload cần orchestration/policy |
| PaaS/managed container | Min instances, compute cấp phát, network | Đội muốn ít vận hành host |
| Serverless container | Request/duration, warm instances nếu cấu hình, egress | HTTP stateless tải biến động |
| FaaS | Invocation, memory/CPU-duration, trigger, network | Handler ngắn theo sự kiện |
| Managed batch/job | Job duration và các dịch vụ nền | Công việc ngắn hoặc theo lịch |

Không được kết luận “Kubernetes luôn đắt hơn” hoặc “serverless luôn rẻ hơn”. Một số nền tảng có scale-to-zero, một số có min instances/CPU allocation khi idle; control plane có thể có phí hoặc chương trình miễn/giảm theo điều kiện. Cần kiểm tra **giá theo thời điểm, sản phẩm, region và cấu hình thực** trước khi lập ngân sách.

## 20. Scale-to-zero giảm compute floor, không xóa system floor

Một function/serverless container có thể không giữ process khi idle. Nhưng:
- DB vẫn có capacity/storage tối thiểu.
- Gateway/NAT có thể vẫn trả phí.
- Broker giữ message/backlog.
- Registry lưu image.
- Logs/metrics có retention.
- Secret/KMS có chính sách phí riêng.
- Các request đầu có cold start.
- Scale lên có thể tạo bão connection DB.

Với ứng dụng cần p99 latency chặt, có thể phải giữ warm instances. Việc này đưa phần compute floor trở lại.

**Decision rule:** Nếu workload rất ít traffic và chấp nhận cold start, scale-to-zero đáng thử. Nếu phải giữ nhiều instance 24/7, cần so TCO với managed container hoặc VM/node theo số đo thật.

### 20.1. Java cold start

Spring Boot có thể tốn thời gian khởi tạo runtime, bean, security, client và DB pool. Có thể đo startup-to-ready, thử giảm bean không dùng, class-data sharing hoặc native image khi phù hợp. Native image có tradeoff về build, reflection compatibility và debug. Không giả định một lựa chọn luôn tốt hơn nếu chưa có benchmark.

## 21. Worker liên tục và job theo sự kiện

Một hệ thống có 30 loại worker nhưng mỗi loại chỉ xử lý vài phút mỗi ngày: giữ 2 worker 24/7 có thể là nguồn floor lớn.

Các hướng:
- Managed job/scheduled container cho công việc có điểm kết thúc.
- Queue-triggered function nếu timeout/memory/trigger phù hợp.
- Scale theo queue depth và oldest message age.
- Gom handler có cùng mức trust/lifecycle khi không phá ranh giới.
- Tách HTTP service khỏi worker để scale độc lập.
- Theo dõi idempotency, retries, DLQ và checkpoint.

Không scale Kafka consumer về zero nếu hợp đồng thời gian xử lý, heartbeat/rebalance hoặc nguồn event không hỗ trợ như kỳ vọng. Khi worker start chậm, backlog có thể vượt deadline. Scale-to-zero chỉ hữu ích khi **tổng chi phí + SLO xử lý** chấp nhận được.

## 22. TCO của con người: công vận hành không có trên cloud bill

Microservices có thể tạo công:
- Nâng JDK/base image cho nhiều repo.
- Theo dõi SLO và incident từng service.
- Điều tra trace qua nhiều tầng.
- Migration API/event schema.
- Tối ưu CI/CD và staging.
- Quản lý secrets, mTLS và network policy.
- Diễn tập backup, replay và rollback.
- Xử lý version mismatch và release coordination.

Một hệ thống chi $1.000 cloud bill nhưng đòi hàng chục giờ vận hành mỗi tuần có thể đắt hơn hệ thống $1.500/tháng nhưng gần như tự phục vụ, tùy cấu trúc nhân sự và rủi ro.

Các thước đo bổ sung:
- On-call toil hours.
- Incident count và time to restore.
- Manual tickets per deployment.
- Lead time của thay đổi bình thường.
- Số service cùng phải release.
- Thời gian patch/cập nhật runtime.
- Change failure rate và error budget.

Không gán tùy tiện toàn bộ chi phí nhân sự vào một service; cần quy tắc phân bổ và mục tiêu đo rõ.

## 23. Cost per business outcome

Một chỉ số hữu ích:

\[
\mathrm{Cost\ per\ successful\ outcome} =
\frac{\mathrm{Allocated\ infrastructure\ cost}}
{\mathrm{Number\ of\ successful\ business\ outcomes}}
\]

Ví dụ chi phí được phân bổ cho Checkout là **$4.000/tháng**:
- 100.000 checkout thành công: **$0,04/checkout**.
- 40.000 checkout thành công: **$0,10/checkout**.

Đây là số giả định, không phải báo giá. Nó thể hiện fixed cost ảnh hưởng mạnh khi volume thấp.

Khi tính:
- Dùng giao dịch thành công, không đếm retry kỹ thuật như kết quả mới.
- Ghi rõ cách phân bổ shared infrastructure.
- Kiểm tra sản phẩm có đủ SLO và tính đúng dữ liệu.
- Không bỏ chi phí peak capacity.
- Phân biệt đơn vị tiền và các kỳ thanh toán.

Một unit cost thấp nhưng tỷ lệ thanh toán sai hoặc outage cao không phải lợi ích kinh doanh.

## 24. Ví dụ ngân sách minh họa hoàn toàn

Giả sử hệ thống có 12 API/worker services, hai replica mỗi service, dùng cluster chung và một số managed services. Các số **giả định để học lập ngân sách**, không dùng làm báo giá cloud.

| Khoản mục | Giả định | Chi phí / tháng |
|---|---|---:|
| Node ứng dụng | 3 node × $100 | $300 |
| Shared LB | 1 × $25 | $25 |
| Network/NAT cơ bản | Ước lượng minh họa | $40 |
| Managed database | Một tier chung có phân quyền | $120 |
| Backup và storage | Giả định | $20 |
| Logs/metrics/traces | Giả định | $60 |
| Registry/CI | Giả định | $10 |
| DNS, secrets, nền khác | Giả định | $40 |
| **Tổng cost floor mô phỏng** | **Chưa tính nhân sự/usage growth** | **$615** |

Kiểm tra: 300 + 25 + 40 + 120 + 20 + 60 + 10 + 40 = 615.

Ba node có thể đủ hoặc không đủ cho workload tùy allocatable, Pod requests, zone placement, headroom. Bảng chỉ nói về phép phân bổ tiền, không xác nhận capacity.

### 24.1. Nếu mỗi service có LB riêng

12 LB giá giả định $25/LB thay cho một LB:
- LB mới: $300.
- LB cũ: $25.
- Tăng thêm: **$275/tháng**.
- Floor mô phỏng: **$890/tháng**.

Tác động thực phụ thuộc mô hình phí và rủi ro gateway dùng chung.

### 24.2. Nếu mỗi service có database instance riêng

12 DB instance giả định $120 thay cho một DB $120:
- Chi phí DB mới: $1.440.
- Tăng thêm: **$1.320**.
- Floor mô phỏng: **$1.935/tháng**.

Đổi lại có thể có quyền và capacity riêng tốt hơn. Nếu Payments cần cách ly cao, nó có thể vẫn cần DB riêng dù tốn hơn. Không gộp database bằng mọi giá nếu gây rủi ro dữ liệu.

## 25. Tính điểm hòa vốn giữa hai mô hình

Một mô hình tuyến tính sơ bộ:

~~~text
Cost_A = Fixed_A + UnitCost_A × Transactions
Cost_B = Fixed_B + UnitCost_B × Transactions
~~~

Giả sử:
- A: fixed $500/tháng, variable $0,02/giao dịch.
- B: fixed $1.500/tháng, variable $0,005/giao dịch.

Điểm hòa vốn:

\[
N^* = \frac{1500-500}{0.02-0.005}
\]

Kết quả khoảng **66.667 giao dịch/tháng**. Dưới mức này A có thể rẻ hơn; trên mức này B có thể rẻ hơn theo giả định.

Nhưng thực tế:
- Node capacity có bậc thang.
- DB tier tăng theo ngưỡng.
- Network/observability không luôn tuyến tính.
- Discount, free tier, commitment khác nhau.
- Peak RPS có thể yêu cầu capacity lớn dù tổng giao dịch thấp.
- Availability/compliance có thể loại phương án rẻ.
- Tiền on-call và rủi ro outage chưa nằm trong công thức.

Dùng điểm hòa vốn để **tạo giả thuyết** rồi benchmark workload, không thay thế quyết định kiến trúc.

## 26. Resource requests và rightsizing

Kubernetes scheduling sử dụng requests, còn limit ảnh hưởng cơ chế hạn CPU/memory. Nếu Pod có request 2 vCPU nhưng thường chỉ sử dụng 0,1 vCPU, cluster có thể phải giữ nhiều node hơn cần thiết.

Tuy vậy, giảm request xuống 0,1 vCPU ngay có thể gây chậm khi traffic burst. Quy trình:
1. Thu CPU/RSS/GC theo nhiều ngày, bao gồm peak và startup.
2. So requests với usage và SLO.
3. Phân tích CPU throttling, memory OOM, pool saturation.
4. Tính headroom khi autoscaling lag và node hỏng.
5. Điều chỉnh dần theo canary.
6. Load-test và diễn tập node failure.
7. Đo node count/hours và tổng bill sau thay đổi.
8. Khôi phục cấu hình nếu error budget xấu.

**Giảm requests không đồng nghĩa giảm hóa đơn ngay**: nếu node chưa được giải phóng hoặc packing bị fragmentation, số node và bill có thể không đổi.

## 27. Autoscaling và bẫy node không giảm

HPA có thể hạ từ 10 xuống 2 replica. Nhưng cluster autoscaler không chắc xóa node vì:
- Một Pod khác có anti-affinity hoặc PDB.
- Workloads còn lại bị phân tán không gộp được.
- Node giữ DaemonSet/system Pod hoặc local storage ràng buộc.
- Requests cao làm không còn node nào chứa được Pod khi di dời.
- Cooldown và cấu hình autoscaler.
- Node pool có minimum size.
- Pod có topology/zone constraints.

Vì vậy, dashboard nên đo **node hours, allocatable, requested/used, unschedulable Pods và waste theo capacity**, không chỉ số replica.

Đừng cố giảm min node khi production cần khả năng chịu lỗi một zone. Tối ưu phải bảo toàn những failure scenarios đã cam kết.

## 28. Chi phí dịch vụ chung và cách phân bổ

Một cluster chung có thể được sử dụng bởi Checkout, Catalog và Payments. Có thể phân bổ theo:
- CPU/RAM requests có trọng số.
- Node usage thời gian thực.
- Log ingest bytes/retention.
- Egress bytes hoặc traffic.
- DB capacity/query/connection.
- Số lần build hoặc thời lượng CI.
- Một phần platform overhead cố định.

Tuy nhiên, một phần idle capacity phục vụ HA phải được ghi nhận riêng hoặc phân bổ theo quy tắc nhất quán. Không nhất thiết mọi tài nguyên phải được gán chính xác cho một request.

**Showback** cho team nhìn chi phí quy đổi; **chargeback** thực sự phân bổ ngân sách. Ở tổ chức đang bắt đầu FinOps, showback giúp xây thói quen trước khi áp chargeback quá cứng.

Metadata minh họa:

~~~yaml
costAllocation:
  team: commerce
  service: checkout-api
  environment: production
  product: checkout
  costCenter: commerce-core
~~~

Đây là mẫu logic, không phải Kubernetes manifest có hiệu lực. Thực tế cần tag/label đúng loại resource và billing export.

## 29. Dashboard cần xem chi phí và reliability cùng nhau

| Góc nhìn | Chỉ số |
|---|---|
| Spend | Monthly cost, forecast, budget variance |
| Floor | Cost lúc idle/ít traffic |
| Compute | Node hours, CPU/RAM requests vs usage |
| Density | Node packing, unallocated capacity |
| HA | Min replicas, zones, headroom |
| Network | NAT, LB, inter-zone/egress bytes |
| Data | DB tier, IOPS, connection saturation, backup |
| Telemetry | Log GB, metric series, trace sampling |
| Nonprod | Idle hours, preview resources chưa xóa |
| Unit economics | Cost per successful transaction |
| Reliability | SLO burn, p95/p99, recovery time |
| Operations | Toil hours, patching, manual tickets |

Nếu sau tối ưu cloud bill giảm 15% nhưng lỗi checkout tăng mạnh, tiết kiệm đó chưa chắc là thành công. **Cost và quality phải là guardrail của nhau.**

## 30. Budget alert và các nguồn cost spike

Một số nguồn làm chi phí tăng:
- Autoscaler giữ max replica lâu.
- Retry storm làm tăng request, log và downstream traffic.
- Dev environment không tự dọn.
- Một service tạo LB/DB mới không có owner.
- Image registry giữ vô hạn build cũ.
- Cross-region replication bật nhầm.
- Tracing 100% request ở API fan-out lớn.
- Log lỗi lặp khi dependency outage.
- Test workload tải lớn ngoài giờ.
- Egress qua NAT hoặc gateway không dự kiến.

Biện pháp:
- Budget theo team/môi trường.
- Owner cho resource, TTL cho preview.
- Quota CPU/RAM/storage và policy tạo tài nguyên.
- Forecast và anomaly alerts.
- Giới hạn maxReplicas/concurrency.
- Log sampling/retention hợp lý.
- Kiểm toán LB, IP, disk, backup và database không dùng.
- Đánh giá tác động bảo mật/SLO trước khi tắt resource.

Không tự động tắt tài nguyên đang được dùng cho recovery, backup hoặc điều tra incident chỉ vì hệ thống phát hiện giá cao.

## 31. Ví dụ công thức bảng tính FinOps

Một sheet có các cột:

| Cột | Trường |
|---|---|
| A | Service |
| B | Min replicas |
| C | CPU request / replica (vCPU) |
| D | RAM request / replica (GiB) |
| E | Hours/month |
| F | Effective CPU-unit price |
| G | Effective memory-unit price |
| H | Modeled compute floor |
| I | Fixed allocated overhead |
| J | Modeled total floor |

Công thức cho hàng 2:

~~~text
H2 = B2 * E2 * (C2 * F2 + D2 * G2)
J2 = H2 + I2
~~~

Đây là mô hình phân bổ logical cost. Với node VM, bill thực phụ thuộc số node/hours. Không được **cộng cả bill node và CPU-equivalent cost** nếu chúng phản ánh cùng một khoản.

Đối với node floor, lower-bound sơ bộ:

~~~text
minNodesByCPU = ceil(totalCpuRequests / allocatableCpuPerNode)
minNodesByRAM = ceil(totalRamRequests / allocatableRamPerNode)
minNodeLowerBound = max(minNodesByCPU, minNodesByRAM)
~~~

Lower bound chưa xét zones, HA, Pod density, sidecars, node restrictions, burst và rolling deployment.

## 32. Mã Java 21 ước lượng floor CPU/RAM

~~~java
import java.util.List;

record WorkloadBaseline(
    String service,
    int replicas,
    double cpuVcpu,
    double memoryGiB
) {
    WorkloadBaseline {
        if (replicas < 0 || cpuVcpu < 0 || memoryGiB < 0) {
            throw new IllegalArgumentException("Negative baseline resource");
        }
    }
}

record FloorEstimate(
    int replicas,
    double requestedVcpu,
    double requestedGiB,
    int minNodesLowerBound
) {}

final class ClusterFloorCalculator {
    static FloorEstimate estimate(
        List<WorkloadBaseline> services,
        double nodeAllocatableVcpu,
        double nodeAllocatableGiB
    ) {
        if (nodeAllocatableVcpu <= 0 || nodeAllocatableGiB <= 0) {
            throw new IllegalArgumentException("Invalid node capacity");
        }

        int count = services.stream()
            .mapToInt(WorkloadBaseline::replicas).sum();
        double cpu = services.stream()
            .mapToDouble(s -> s.replicas() * s.cpuVcpu()).sum();
        double memory = services.stream()
            .mapToDouble(s -> s.replicas() * s.memoryGiB()).sum();

        int cpuNodes = (int)Math.ceil(cpu / nodeAllocatableVcpu);
        int memNodes = (int)Math.ceil(memory / nodeAllocatableGiB);

        return new FloorEstimate(
            count, cpu, memory, Math.max(cpuNodes, memNodes));
    }
}
~~~

Ví dụ sử dụng:

~~~java
import java.util.stream.IntStream;

var services = IntStream.range(0, 12)
    .mapToObj(i -> new WorkloadBaseline("s" + i, 2, 0.25, 0.5))
    .toList();

var estimate = ClusterFloorCalculator.estimate(services, 3.5, 12);

System.out.println(estimate.replicas());           // 24
System.out.println(estimate.requestedVcpu());      // 6.0
System.out.println(estimate.requestedGiB());       // 12.0
System.out.println(estimate.minNodesLowerBound()); // 2
~~~

Lower-bound 2 node **không bảo đảm** production có HA hoặc capacity khi một node lỗi. Cần tính thêm vùng lỗi, DaemonSet, Pod security, surge, quota và load tests.

### 32.1. Unit test

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ClusterFloorCalculatorTest {
    @Test
    void twelveServicesTwoReplicas() {
        var services = java.util.stream.IntStream.range(0, 12)
            .mapToObj(i -> new WorkloadBaseline("s" + i, 2, 0.25, 0.5))
            .toList();

        FloorEstimate result =
            ClusterFloorCalculator.estimate(services, 3.5, 12);

        assertEquals(24, result.replicas());
        assertEquals(6.0, result.requestedVcpu(), 0.0001);
        assertEquals(12.0, result.requestedGiB(), 0.0001);
        assertEquals(2, result.minNodesLowerBound());
    }

    @Test
    void invalidNodeCapacityIsRejected() {
        assertThrows(IllegalArgumentException.class,
            () -> ClusterFloorCalculator.estimate(
                java.util.List.of(), 0, 12));
    }
}
~~~

Đây là kiểm tra phép tính logic; **không phải** kiểm thử Kubernetes scheduler hay xác nhận giá cloud.

## 33. Case study: startup có quá nhiều service

**Bối cảnh:** 6 engineer vận hành 18 Spring Boot microservice, mỗi service hai replica mặc định. Traffic thấp, nhiều feature cần thay đổi 4–5 service đồng thời.

Vấn đề:
- Memory/JVM floor lặp.
- DB connections idle cao.
- Nhiều pipeline, logs, alerts.
- Khó debug cross-service.
- Team vẫn không có independent deployability thật vì version coupling.

Phương án đánh giá:
1. Đo CPU/RSS, requests và cost per service.
2. Liệt kê domain có change coupling cao.
3. Cân nhắc modular monolith hoặc hợp nhất vài service trong cùng bounded context.
4. Chuyển job ít tải sang scheduled/managed job khi phù hợp.
5. Xem hạ tầng DB vật lý dùng chung với isolation logic.
6. Right-size requests, giảm resource không owner.
7. Giữ service độc lập cho Payment/critical components nếu SLO/security yêu cầu.
8. Thử canary, đánh giá bill và SLO.

**Không gộp bất chấp rủi ro.** Mục tiêu là chỉ trả overhead độc lập ở nơi quyền sở hữu, fault isolation và scale riêng đem lợi ích thật.

## 34. Case study: Catalog có tải cao hơn các domain khác

Một monolith chứa Catalog, Checkout và Admin. Catalog chiếm phần lớn CPU ở peak, nhưng khi tăng instance monolith, cả Checkout và Admin cũng được nhân bản.

Tách Catalog có thể đem:
- Scale riêng CPU-heavy search traffic.
- Cache/DB/index phù hợp với domain.
- Admin giữ instance thấp.
- Checkout bảo vệ SLO khỏi spike Catalog.
- Phát hành tính năng Catalog không restart Checkout.

Chi phí thêm:
- Service container, endpoint, IAM, telemetry.
- Network call nếu Checkout cần Catalog.
- API contract và versioning.
- Cache/search cluster.
- Incident ownership.

Nếu khoản tiết kiệm khi scale peak và giảm outage đủ lớn, **nhiều service có thể rẻ hơn tổng thể** dù floor ban đầu cao hơn. Cần benchmark cùng workload thật.

## 35. Case study: 30 worker chỉ chạy vài phút một ngày

Mỗi loại job có hai process 24/7. Một phương án khác:
- Chuyển job ngắn sang managed batch hoặc function.
- Queue trigger với concurrency tối đa.
- Checkpoint và idempotency để retry.
- DLQ và reprocessing.
- Giữ broker/database nền theo SLO.
- Theo dõi startup, queue age và completion deadline.

Nếu workload cần giữ kết nối Kafka liên tục, chạy rất lâu hoặc dùng GPU đặc thù, serverless function phổ thông có thể không phù hợp. Đánh giá theo lifecycle, timeout, quota và cost per completed job, không chỉ theo CPU idle.

## 36. Case study: mỗi team một Kubernetes cluster

12 team yêu cầu mỗi team một cluster. Có thể làm tăng control plane, node floor, ingress, observability, upgrade work.

Các phương án:
1. Cluster riêng mỗi team khi yêu cầu isolation thật.
2. Shared cluster đa namespace với RBAC/NetworkPolicy/quota.
3. Cluster riêng theo mức trust hoặc compliance.
4. PaaS cho ứng dụng đơn giản không cần Kubernetes trực tiếp.

Chọn theo threat model, fault isolation, cost allocation và operational cognitive load. **Namespace không hoàn toàn cách ly kernel**, nên không áp shared cluster cho mọi mã không tin cậy chỉ vì tiết kiệm.

## 37. Modular monolith là đối chứng hợp lệ

Một modular monolith có module rõ ràng và một số process triển khai:
- Ít JVM/process và pipeline hơn.
- Ít API nội bộ qua mạng.
- Đơn giản hơn về transaction và debug.
- Có thể tiết kiệm baseline khi tải thấp.

Đánh đổi:
- Scale theo cả ứng dụng.
- Một lỗi process tác động nhiều module.
- Deploy chung làm giảm độc lập phát hành.
- Cần kỷ luật ranh giới module để tránh coupling.

Không chọn modular monolith mặc định cho mọi hệ thống; cũng không chọn microservices chỉ vì nó hiện đại. **Bounded context, team ownership, change coupling, SLO và traffic** là yếu tố quyết định.

## 38. Lộ trình tối ưu cost floor

### Giai đoạn 1: tạo baseline

- Thu billing export và bảng owner/resource.
- Phân loại fixed, shared, usage-based.
- Đo min replicas, CPU/RAM requests và usage.
- Thu DB/connection/network/telemetry cost.
- Thống kê nonprod và resource không owner.
- Ghi SLO, RTO/RPO và yêu cầu bảo mật không thể giảm.

### Giai đoạn 2: giảm lãng phí có thể đảo ngược

- Dọn preview và disk không dùng.
- Điều chỉnh CPU/RAM requests có canary.
- Tối ưu node packing, HA headroom có chủ đích.
- Tắt nonprod ngoài giờ theo chính sách.
- Điều chỉnh log sampling/retention.
- Chuẩn hóa gateway và CI templates nơi phù hợp.
- Giảm idle connection pools.
- Theo dõi bill và SLO trước/sau.

### Giai đoạn 3: đánh giá kiến trúc

- Thử scale-to-zero cho job phù hợp.
- Xem xét service boundary quá vụn.
- Đánh giá một số DB instance có thể dùng chung vật lý.
- So PaaS với managed Kubernetes/VM.
- Tối ưu east–west traffic và read model.
- Lập ADR, test tải và diễn tập phục hồi.
- Quyết định bằng total cost và business outcomes.

Không làm một lần cắt giảm lớn rồi hy vọng SLO vẫn ổn. Mỗi thay đổi nên có owner, guardrail, rollback và khoảng đo đại diện.

## 39. ADR mẫu cho quyết định tách service

~~~markdown
# ADR: Có tách Catalog Search thành dịch vụ riêng không?

## Bối cảnh
- Catalog chịu phần lớn peak traffic
- Ứng dụng hiện phải scale nguyên khối
- Checkout có SLO nghiêm ngặt

## Phương án
1. Giữ modular monolith và tối ưu cache
2. Tách Catalog Search thành service
3. Dùng managed search/index service

## Baseline
- Fixed infrastructure cost
- Peak compute, DB/network/telemetry cost
- CPU/RSS và p95/p99
- On-call, incident, deployment frequency

## Đánh đổi
- Cost floor tăng thêm khi tách
- Peak compute có thể giảm nhờ scale riêng
- API/data contract và eventual consistency
- Fault isolation và owner rõ hơn

## Quyết định
- Điền sau thử tải và review SLO/security

## Kiểm chứng
- Load test với baseline và peak
- Canary/rollback, node failure drill
- Hóa đơn và cost/transaction
- Không làm xấu critical journey SLO
~~~

ADR cần ghi lý do chọn và lý do loại phương án thay vì chỉ ghi tên công nghệ. Điều kiện xem lại quyết định nên rõ: traffic thay đổi, số team tăng, SLO mới hoặc cost floor vượt ngân sách.

## 40. Các ngộ nhận thường gặp

1. **“Container nhỏ nên nhiều container miễn phí.”** Mỗi process có overhead và node vẫn tính tiền.
2. **“Kubernetes chia sẻ node nên không có per-service floor.”** Replica, requests, sidecar và telemetry vẫn dùng tài nguyên.
3. **“Serverless = không trả gì khi không có request.”** DB, network, storage, registry và warm instances có thể vẫn có phí.
4. **“Mỗi service bắt buộc một DB server.”** Data ownership có thể tách logic; isolation vật lý theo rủi ro.
5. **“Hai replica là HA.”** Cùng zone hoặc cùng DB đơn điểm lỗi không đủ.
6. **“Giảm CPU request giảm bill ngay.”** Cluster có thể vẫn dùng cùng số node.
7. **“100% utilization là tối ưu.”** Thiếu headroom có thể kéo dài incident và rollout.
8. **“Chỉ đo cloud bill là đủ.”** On-call, outage và lead time cũng là chi phí.
9. **“Tắt log để tiết kiệm vô hại.”** Mất khả năng điều tra và audit.
10. **“Microservices luôn đắt hơn monolith.”** Scale riêng ở peak và fault isolation có thể tạo lợi ích lớn.
11. **“Microservices luôn giúp deploy độc lập.”** Shared DB/schema có thể gây lockstep.
12. **“Càng nhiều service càng có kiến trúc tốt.”** Ranh giới phải theo domain, không theo mỗi bảng.
13. **“Chi phí thấp hơn đồng nghĩa tối ưu thành công.”** Phải xem SLO, security và user impact.
14. **“Peak RPS là đủ để chọn capacity.”** Cần concurrency, CPU/memory, data-tier và latency.
15. **“Số node tối thiểu từ CPU là số node cần mua.”** RAM, topology, HA và rollout có thể làm tăng.
16. **“Gộp hết hạ tầng để tiết kiệm.”** Một số thành phần phải tách vì compliance hoặc blast radius.

## 41. Bài tập thực hành

**Bài A — tính baseline:** 18 Spring Boot service, mỗi service 2 replica, mỗi replica 0,3 vCPU/768 MiB. Tính Pod, CPU, RAM requests. Với node 3,5 vCPU/12 GiB allocatable, tính lower-bound theo CPU và RAM, giải thích vì sao chưa đủ cho production HA.

**Bài B — shared ingress:** 15 service có LB riêng. Với phí giả định $20/LB/tháng, tính chênh lệch nếu dùng 1 shared LB. Nêu khi nào tách LB vẫn cần thiết.

**Bài C — database:** 12 service có schema riêng và DB instance riêng. Thiết kế phương án dùng shared physical DB nhưng giữ quyền logic, quota, migration và kế hoạch tách lại khi quá tải.

**Bài D — logs:** 25 service, 2 replica/service, 0,7 GiB log/ngày/replica. Tính ingest 30 ngày; đưa chính sách sampling/retention không làm mất incident evidence.

**Bài E — JVM:** Một process idle RSS=350 MiB, 30 service × 2 replica. Tính RAM baseline và đề xuất metric cần đo trước khi thay memory limits hoặc thử native image.

**Bài F — autoscaling:** HPA giảm 10 xuống 2 replicas nhưng node count không giảm. Liệt kê nguyên nhân fragmentation, min node, Pod constraints, PDB, requests và cách kiểm tra.

**Bài G — unit economics:** Floor $5.000/tháng, variable cost $0,01/giao dịch, 50.000 giao dịch thành công. Tính unit cost. Nếu giao dịch tăng 200.000 và phải nâng DB thêm $2.000, đánh giá hiệu quả quy mô.

**Bài H — fault tolerance:** Một service giảm từ 2 xuống 1 replica tiết kiệm một phần compute. Xác định SLO/RTO, node failure, rollout và p99 có thể thay đổi thế nào; đề xuất canary và rollback.

**Bài I — shared cluster:** 12 team muốn cluster riêng. So cluster chung với namespace/RBAC/quota và cluster riêng theo trust level. Cân bằng security, blast radius, operations và cost floor.

**Bài J — service boundary:** Một ứng dụng có 25 service nhưng 80% thay đổi cần release 7 service cùng lúc. Đề xuất đánh giá bounded context và change coupling; khi nào nên hợp nhất vào modular monolith?

**Bài K — capacity calculator:** Mở rộng class Java để tính thêm headroom 30%, overhead DaemonSets và số zone tối thiểu. Viết test xác nhận lower-bound không bị nhầm với scheduling thực.

**Bài L — ADR:** Chọn một capability như Catalog, Payment hoặc Notification; viết ADR so monolith module, managed container, Kubernetes, VM và FaaS theo cost floor, peak traffic, SLO, dữ liệu và TCO.

## 42. Checklist ra quyết định

1. **Mô tả workload:** baseline, peak, burst, latency, job duration.
2. **Ghi rõ SLO/RTO/RPO** và mức isolation bắt buộc.
3. **Tính min replicas** theo nhu cầu phục vụ, không theo template mặc định.
4. **Đo overhead JVM/sidecar** và startup.
5. **Tính node requests/packing** với headroom, zones và rollout.
6. **Ghi fixed network:** LB, NAT, IP, private endpoint.
7. **Tính east–west traffic** và cross-zone/egress.
8. **Liệt kê DB/broker/cache/search** cùng backup/replication.
9. **Tính log/metric/trace volume** và retention.
10. **Tính security/CI/CD** và công quản lý.
11. **Phân biệt production/nonprod**, có TTL cho preview.
12. **So VM/Kubernetes/PaaS/serverless** theo workload thật.
13. **Đo cost per successful outcome** chứ không chỉ request.
14. **Phân bổ shared infrastructure minh bạch** và tránh tính trùng.
15. **Xem xét modular monolith** như đối chứng.
16. **Kiểm tra team ownership/change coupling** trước khi thêm service.
17. **Giữ HA/privacy/backup guardrails**, không cắt mù.
18. **Lập ADR và PoC** có cost, latency, error budget và recovery drill.
19. **Đặt cost anomaly alerts** và resource owner.
20. **Xem lại kiến trúc định kỳ** khi volume hoặc rủi ro thay đổi.

## 43. Ghi nhớ

- **Cost floor** là phần chi tối thiểu giữ kiến trúc hoạt động, không chỉ CPU của một container.
- **Nhiều service lặp overhead** của JVM, replica HA, network, connection pools, telemetry, CI/CD và on-call.
- **Kubernetes giúp chia node**, nhưng bin packing, headroom và topology quyết định node hours thực.
- **HA phải được thiết kế xuyên critical journey**, gồm app, DB, broker và mạng.
- **Data ownership không tự đồng nghĩa instance DB riêng**, nhưng phải giữ quyền, schema và isolation đủ cho SLO.
- **Serverless có thể giảm compute floor**, song không xóa phần nền DB, networking, logging và tradeoff cold start.
- **Modular monolith là lựa chọn hợp lệ** khi chi phí tách service vượt lợi ích phát hành/scale độc lập.
- **Microservices có thể có lợi ở quy mô lớn** khi cần scale từng domain, cô lập lỗi và ownership rõ.
- **FinOps phải đo cùng reliability**: chi phí giảm nhưng SLO/khả năng khôi phục xấu đi không phải tối ưu tốt.
- **Cần bằng chứng thay vì khẩu hiệu:** đo workload, lập capacity model, so TCO và xác nhận bằng thử tải.

Chi phí hạ tầng tối thiểu là **giá của những mức độ độc lập và sẵn sàng mà kiến trúc lựa chọn**. Một hệ thống tốt chỉ trả giá đó ở những ranh giới thật sự tạo giá trị cho sản phẩm, và có khả năng chứng minh quyết định bằng dữ liệu về chi phí, hiệu năng, bảo mật và sự ổn định khi xảy ra sự cố.
