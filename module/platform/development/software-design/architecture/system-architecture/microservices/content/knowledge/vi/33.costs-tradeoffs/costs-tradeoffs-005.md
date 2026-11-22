# Phân bổ chi phí theo dịch vụ và hành trình nghiệp vụ

## 1. Mục tiêu bài học

Khi một sản phẩm được tách thành nhiều microservices, hóa đơn cloud thường được gom theo tài khoản, project, cluster hoặc resource. Một cluster có thể chạy Order, Payment, Inventory, Search, Notification và nhiều worker; database, broker, cache, gateway và observability lại được dùng chung. Finance nhìn thấy tổng tiền, Platform nhìn thấy tài nguyên, còn Product muốn biết một checkout thành công tốn bao nhiêu.

Nếu chỉ chia đều hóa đơn cho số service, kết quả thường không công bằng. Nếu gán toàn bộ chi phí shared infrastructure cho team sở hữu cluster, team đó có thể bị tính phần của mọi người. Nếu phân bổ theo CPU mà không đo workload, service memory-heavy hoặc hành trình có nhiều lần retry có thể bị đánh giá thấp. **Phân bổ chi phí phải liên kết được billing, usage, ownership và kết quả nghiệp vụ, đồng thời công khai phần ước tính và phần chưa thể quy thuộc chính xác.**

Bài này thuộc nhóm **Chi phí và đánh đổi**. Nội dung tập trung vào FinOps cho microservices, cách xây mô hình direct/shared costs, đo unit economics, showback/chargeback, cost per business journey và dùng dữ liệu để ra quyết định kiến trúc.

Sau bài học, bạn có thể:

1. Phân biệt cost allocation, showback, chargeback, budgeting và unit economics.
2. Xây taxonomy cho compute, storage, network, managed services, tooling và labor.
3. Gắn cost ownership vào service, team, environment, region và business capability.
4. Phân bổ chi phí trực tiếp và chi phí dùng chung bằng driver có thể giải thích.
5. Liên kết trace/workflow với usage telemetry mà không làm lộ PII hoặc tăng cardinality vô hạn.
6. Tính cost per request, cost per successful order, cost per payment và cost-to-serve.
7. Nhận diện sai lệch do idle capacity, retries, shared dependencies, burst traffic và data retention.
8. Thiết kế showback trước khi triển khai chargeback.
9. Dùng budget, anomaly detection và unit-cost trends để cải thiện kiến trúc.
10. Thiết lập review, dispute, ownership và kiểm soát thay đổi mô hình phân bổ.

Ví dụ xuyên suốt là cửa hàng trực tuyến có Order, Payment, Inventory, Fulfillment, Search, Notification, API Gateway, database, message broker và Kubernetes hoặc managed container platform. Các số tiền chỉ là giả định minh họa, không phải báo giá của nhà cung cấp.

## 2. Cost allocation là gì?

**Cost allocation** là quy trình gắn chi phí tài nguyên, dịch vụ nền tảng và hoạt động vận hành vào đối tượng tiêu thụ hoặc sở hữu theo quy tắc được công bố.

Một mô hình hữu ích cần trả lời bốn câu hỏi:

- **Ai sở hữu chi phí?** Team, domain, platform hoặc cost center chịu trách nhiệm.
- **Ai tiêu thụ chi phí?** Service, environment, region, tenant hoặc workload sử dụng tài nguyên.
- **Chi phí phát sinh cho kết quả nào?** Checkout, payment, search, notification, shipment hoặc workflow.
- **Chi phí có thể tránh được không?** Nếu giảm traffic, xóa môi trường hoặc thay kiến trúc, khoản chi nào thực sự giảm?

Bốn câu hỏi này không luôn có cùng câu trả lời. Platform team có thể sở hữu cluster nhưng nhiều product teams tiêu thụ compute. Order Service có thể gọi Payment và Inventory; chi phí checkout nằm rải rác qua nhiều service. Một database có thể do Data Platform sở hữu nhưng phục vụ ba domain.

### 2.1. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Câu hỏi chính |
|---|---|---|
| Cost visibility | Khả năng nhìn thấy hóa đơn và usage | Tiền đang đi đâu? |
| Cost allocation | Gán chi phí cho owner/consumer theo driver | Ai dùng hoặc chịu trách nhiệm? |
| Showback | Báo cáo chi phí cho team, chưa chuyển ngân sách | Team cần biết mình tiêu thụ gì? |
| Chargeback | Chuyển chi phí vào ngân sách/cost center | Đơn vị nào chịu khoản chi? |
| Budgeting | Đặt giới hạn và dự báo | Có thể tiêu bao nhiêu? |
| Forecasting | Ước lượng chi phí tương lai | Cuối kỳ sẽ tốn bao nhiêu? |
| Unit economics | Chi phí trên một đơn vị kết quả | Một đơn thành công tốn bao nhiêu? |
| Optimization | Thay đổi để giảm cost hoặc tăng giá trị | Có thể làm tốt hơn ở đâu? |

Cost allocation không tự động là hóa đơn chargeback. Giai đoạn đầu thường nên dùng showback để kiểm tra driver, dữ liệu và phản hồi của team trước khi gắn vào ngân sách chính thức.

### 2.2. Vì sao microservices làm bài toán khó hơn?

Trong microservices:

- Một request có thể gọi nhiều service và tạo nhiều event.
- Một database, broker hoặc cluster được dùng chung.
- Autoscaling làm resource ownership thay đổi theo thời gian.
- Team sở hữu service có thể khác team tạo ra traffic.
- Retries, fan-out và background jobs tạo usage không nhìn thấy ở ingress.
- Data retention, logs và traces có chi phí tăng theo volume.
- Shared platform cần idle capacity để bảo đảm headroom/availability.
- Billing dimensions và discount khác nhau giữa provider.

Vì vậy **không thể chỉ đọc tên resource rồi gán chi phí một cách chính xác**. Cần kết hợp billing data, runtime telemetry, ownership catalog và business events.

## 3. Xây taxonomy chi phí

Trước khi phân bổ, hãy thống nhất những khoản nào nằm trong phạm vi.

| Nhóm | Thành phần thường gặp | Driver tiềm năng |
|---|---|---|
| Compute | VM, node, container CPU/RAM, serverless execution | vCPU-seconds, GiB-seconds, node share |
| Storage | Block, object, database disk, snapshots | GB-month, IOPS, retained bytes |
| Network | Egress, NAT, load balancer, inter-zone | GB, requests, connection-hours |
| Database | Managed DB, replicas, backup, IOPS | Query time, CPU, connections, storage |
| Messaging | Kafka/broker, queue, stream processing | Bytes, partitions, messages, retention |
| Cache | Redis/memory cache | Memory-hours, commands, bandwidth |
| Observability | Logs, metrics, traces, alerting | Ingested bytes, series, spans, retention |
| Security/tooling | Registry, scanning, secrets, CI runners | Builds, artifacts, seats, usage |
| Platform labor | On-call, upgrades, SRE, platform engineering | FTE share, effort, service count |
| Resilience overhead | HA replicas, standby, DR, backups | Reserved capacity, criticality |
| Shared software | License, support plan, vendor minimum | Seats, usage, fixed allocation |
| Migration/one-off | Data migration, temporary dual-run | Project owner, amortization policy |

Đừng gộp tất cả vào một dòng “Kubernetes cost”. Cluster bill có thể gồm node compute, disks, load balancers, egress, control plane, logging, registry và managed services. Nếu không phân tách, nhóm sẽ không biết tối ưu workload hay chuyển một dịch vụ managed.

### 3.1. Direct cost và shared cost

**Direct cost** có thể quy thuộc tương đối rõ:

- Một VM chỉ chạy Search.
- Một database instance chỉ phục vụ Billing.
- Một bucket có tag service và usage riêng.
- Một build runner dedicated cho một nhóm.

**Shared cost** phục vụ nhiều consumers:

- Kubernetes worker nodes chạy nhiều services.
- Kafka cluster có nhiều topics/consumer groups.
- API Gateway, NAT, load balancer.
- Central logging/tracing/metrics.
- Shared database cluster.
- Platform engineering, on-call và support contracts.

Direct cost nên được gán trực tiếp trước. Shared cost cần driver phù hợp; không nên dùng một tỷ lệ tùy tiện cho mọi loại chi phí.

### 3.2. Fixed, variable và step cost

- **Fixed cost:** license hoặc baseline platform fee ít thay đổi theo tải ngắn hạn.
- **Variable cost:** network egress, request-based compute, log ingestion tăng theo usage.
- **Step cost:** thêm node, shard, replica hoặc license tier làm bill tăng theo bậc.
- **Committed/discounted cost:** reservation hoặc savings plan khiến giá thực trả khác list price.
- **One-off cost:** migration, setup, incident recovery hoặc dual-running.

Một service giảm CPU 20% chưa chắc hóa đơn giảm ngay nếu node vẫn phải chạy để phục vụ workload khác. Phân biệt **consumption attribution** với **avoidable cost**.

## 4. Ownership taxonomy và tagging

Mọi resource nên có metadata đủ để trả lời ai sở hữu, dùng cho gì và ở đâu.

~~~text
organization = my-business
cost_center = commerce
team = checkout-platform
service = order-service
domain = order-management
environment = production
region = apac
criticality = tier-1
data_classification = confidential
owner = team-order
managed_by = terraform
business_capability = checkout
~~~

Tên tag cần theo quy ước, giá trị hữu hạn và được validate. Không đưa email cá nhân, customer ID, order ID hoặc dữ liệu nhạy cảm vào resource tags.

### 4.1. Tag coverage

\[
TagCoverage =
\frac{EligibleSpendWithValidOwnerMetadata}
{TotalEligibleSpend}\times100\%
\]

Ví dụ 92% spend có team/service/environment hợp lệ. 8% còn lại phải vào hàng “unallocated” với owner xử lý, không tự gán cho một team chỉ để báo cáo đủ 100%.

### 4.2. Metadata phải được duy trì

Kiểm tra drift:

- Resource tạo ngoài Terraform/approved pipeline có tag không?
- Autoscaled nodes có giữ cost-center metadata?
- Ephemeral environments có owner và expiry?
- Bucket/DB mới có data classification?
- Resource đổi team ownership có cập nhật catalog?
- Resource đã xóa nhưng delayed billing vẫn xuất hiện?

Có thể áp policy tại IaC/cluster admission/cloud account, kết hợp periodic inventory scan. Không phụ thuộc developer tự nhớ gắn tag.

### 4.3. Service catalog

| Trường | Ví dụ |
|---|---|
| service_id | order-service |
| domain | order-management |
| owning_team | team-order |
| cost_center | commerce |
| criticality | tier-1 |
| runtime | managed-containers |
| dependencies | payment, inventory, kafka |
| business_capabilities | checkout, order-history |
| environment | production/staging |
| on_call | order-oncall |
| cost_owner | team-order |
| allocation_policy | direct + shared-compute-v2 |

Catalog là cầu nối giữa billing resource và telemetry. Service ID nên ổn định qua đổi tên repo hoặc deployment.

## 5. Chọn cost driver phù hợp

Driver là đại lượng dùng để chia một pool chi phí. Driver tốt có quan hệ hợp lý với việc tiêu thụ hoặc trách nhiệm.

### 5.1. Compute pool

Có thể dùng:

- **Requested resource share:** phù hợp reserved capacity và quota đã cấp.
- **Actual usage share:** phù hợp phần tiêu thụ đo được.
- **Peak/weighted usage:** phản ánh capacity cần dự phòng.
- **Dedicated node ownership:** gán thẳng nếu node pool chỉ phục vụ một nhóm.
- **Idle/overhead pool:** giữ thành shared/platform cost nếu không quy thuộc được.

Không dùng CPU đơn độc khi service memory-heavy. Không tính cả CPU request và CPU usage như hai khoản chi phí cộng độc lập; chúng có thể là hai driver để phân tích cùng một pool.

### 5.2. Storage

Dùng GB-month, IOPS, throughput, backup size hoặc retained bytes. Một service có 2 TB archive ít truy cập có thể tốn storage nhiều dù CPU thấp. Nếu chỉ phân bổ theo requests, chi phí storage sai.

### 5.3. Network

Egress, NAT và inter-zone traffic nên phân bổ theo bytes/connection/request nếu có dữ liệu. Phân biệt traffic giữa services, traffic Internet và traffic cùng zone vì provider có thể tính giá khác nhau. Nếu không có telemetry đủ tin cậy, giữ shared network pool và ghi rõ độ tin cậy.

### 5.4. Observability

Logs, metrics và traces có thể phân bổ theo:

- Ingested bytes per service.
- Retention bytes × days.
- Trace spans hoặc sampled bytes.
- Custom metrics/active series.
- Query/alert usage nếu license tính theo usage.

Service log quá verbose có thể tạo bill lớn dù compute thấp. Không giảm audit/security logs chỉ để giảm chi phí.

### 5.5. Labor và shared platform

Chi phí người vận hành có thể phân bổ theo FTE effort, số services/workloads, ticket/incident effort hoặc fixed percentage đã thỏa thuận. Đây là phần có độ bất định cao hơn cloud invoice. Công bố phương pháp và không trình bày như số đo chính xác tới từng giờ nếu không có timesheet phù hợp.

## 6. Nguyên tắc phân bổ

1. **Consistent:** cùng driver và công thức cho đối tượng cùng loại.
2. **Explainable:** owner hiểu vì sao bị tính khoản đó.
3. **Traceable:** truy ngược được tới billing line/resource/usage.
4. **Stable:** không đổi rule giữa kỳ mà không version.
5. **Complete:** có dòng unallocated/central overhead.
6. **Proportional:** chi phí gắn với mức sử dụng/trách nhiệm phù hợp.
7. **Privacy-safe:** không dùng customer-level IDs làm metric dimensions.
8. **Actionable:** team có khả năng tác động vào driver.
9. **Fair:** không phạt service chỉ vì phục vụ nhiều khách hàng hơn.
10. **Reconciled:** allocated + unallocated khớp billing source sau điều chỉnh.

Không có một driver duy nhất đúng cho tất cả pool. Mục tiêu là **mô hình phù hợp với quyết định cần đưa ra**, không phải tạo ra độ chính xác giả.

## 7. Phân bổ chi phí Kubernetes/shared compute

Giả sử node pool có tổng chi phí $10.000/tháng và chạy Order, Payment, Inventory, Search.

| Service | CPU-hours | Memory GiB-hours | CPU share | Memory share |
|---|---:|---:|---:|---:|
| Order | 3.000 | 8.000 | 30% | 40% |
| Payment | 2.500 | 5.000 | 25% | 25% |
| Inventory | 2.000 | 3.000 | 20% | 15% |
| Search | 2.500 | 4.000 | 25% | 20% |
| **Tổng** | **10.000** | **20.000** | **100%** | **100%** |

Nếu compute pool chia 50% theo CPU và 50% theo memory:

\[
WeightedShare_i=0.5\times CPUShare_i+0.5\times MemoryShare_i
\]

| Service | Weighted share | Allocated $10.000 |
|---|---:|---:|
| Order | 35% | $3.500 |
| Payment | 25% | $2.500 |
| Inventory | 17,5% | $1.750 |
| Search | 22,5% | $2.250 |
| **Tổng** | **100%** | **$10.000** |

Đây là ví dụ, trọng số 50/50 không phải chuẩn chung. Nếu memory request quyết định số node, memory reservation có thể là driver tốt hơn actual memory. Nếu workload bursty, peak share hoặc reserved capacity cần tính riêng.

### 7.1. Phân bổ idle capacity

Node pool cần headroom để autoscale, rolling update, tolerate failure và bảo đảm SLO. Không nên coi toàn bộ phần idle là “lãng phí” rồi gán cho team cuối cùng dùng node.

Có thể chia:

- **Consumed share:** tài nguyên đang dùng.
- **Reserved share:** capacity đã cấp.
- **Platform resilience overhead:** headroom cần để đạt HA.
- **Unallocated capacity:** phần chưa có owner rõ hoặc do overprovisioning.

Nếu team yêu cầu reserved capacity đặc biệt, phần incremental có thể gán trực tiếp cho team đó.

### 7.2. Requests và limits khác actual usage

Kubernetes CPU requests ảnh hưởng scheduling; memory requests ảnh hưởng placement; limits ảnh hưởng throttling/OOM. Chi phí node không nhất thiết được tính trực tiếp từ usage container. Một mô hình nên xem requested CPU/memory, actual CPU/memory, node allocatable, daemon overhead và unallocated headroom.

Đừng phân bổ tổng node bill chỉ theo lệnh xem usage hiện thời nếu mục tiêu là phản ánh reserved capacity.

## 8. Shared database, broker, gateway và network

### 8.1. Managed database

Một DB instance $4.000/tháng phục vụ Order, Inventory và Reporting. Driver có thể kết hợp query execution time, IOPS, storage/backup bytes, connections và dedicated replicas.

Ví dụ weights: 40% query resource, 30% storage, 20% I/O, 10% fixed baseline. Cần bảo đảm các dimension không đếm cùng một khoản hai lần. Nếu provider không có metering per-service đáng tin, dùng telemetry nội bộ làm proxy và ghi confidence.

### 8.2. Message broker

Broker cost phụ thuộc node, disk, network, retention, partitions và throughput. Phân bổ theo số messages đơn thuần không công bằng nếu payload hoặc retention khác nhau.

\[
C_{broker,i}=C_{fixed}\times FixedShare_i+
C_{variable}\times UsageShare_i
\]

Usage share có thể là weighted combination của bytes in/out, retained byte-hours, consumer throughput và dedicated partition capacity. Topic thuộc riêng domain có thể gán trực tiếp.

### 8.3. API Gateway/load balancer

Phân bổ theo request count, bytes, connection-hours hoặc route ownership. Xác định billing source tính từng retry attempt hay logical request. Có thể gán fixed baseline cho Platform và variable share cho capability.

### 8.4. NAT/egress/inter-zone

Nếu có flow logs/telemetry, gán bytes theo source service/region/destination class. Nếu thiếu dữ liệu, giữ shared network pool và dùng driver ước lượng có confidence. Không tạo metric chứa raw IP/customer ID không cần thiết.

## 9. Từ service cost tới business journey cost

Service cost trả lời “service này tiêu bao nhiêu”. Product/Finance thường cần “một hành trình thành công tốn bao nhiêu”.

Một checkout có thể đi qua:

~~~text
Customer
  -> API Gateway
  -> Order Service
  -> Inventory Service
  -> Payment Service
  -> Message Broker
  -> Fulfillment Worker
  -> Notification Service
~~~

Một journey có thể tạo nhiều requests, events, retries và background jobs. Vì vậy **chi phí hành trình phải gồm phần tài nguyên phát sinh ở các bước**, kể cả async nếu có quan hệ nhân quả và có thể đo.

### 9.1. Định nghĩa đơn vị nghiệp vụ

- Successful checkout: order đạt trạng thái hoàn tất theo business contract.
- Payment authorization: logical payment intent có kết quả rõ.
- Search session: phiên tìm kiếm theo định nghĩa sản phẩm.
- Shipment: lô hàng được bàn giao thành công.
- Notification delivered: thông báo đạt trạng thái delivery được định nghĩa.

Không dùng số HTTP requests làm denominator cho “cost per order” nếu một order tạo nhiều attempts. Không dùng số order mới nếu mục tiêu là cost per successful order; phải xử lý cancelled/failed/refunded theo định nghĩa.

### 9.2. Cost per successful checkout

\[
CostPerSuccessfulCheckout=
\frac{AllocatedCheckoutRelatedCost}
{SuccessfulEligibleCheckouts}
\]

Tử số có thể gồm compute Order/Payment/Inventory, broker/workers, DB/storage/network, shared gateway, observability và một phần platform labor nếu đang tính full TCO.

Mẫu số phải lấy từ business events/ledger đã định nghĩa, không lấy số 202 Accepted ở Gateway.

### 9.3. Ví dụ

| Thành phần | Chi phí được phân bổ cho checkout |
|---|---:|
| Order Service | $2.400 |
| Payment Service | $1.800 |
| Inventory Service | $1.200 |
| Broker + workers | $900 |
| Shared gateway/network | $700 |
| Observability | $300 |
| Platform overhead | $700 |
| **Tổng** | **$8.000** |

Có 40.000 successful checkouts:

\[
8000/40000=\$0.20
\]

Cost per successful checkout là $0,20 theo mô hình giả định. Nếu chỉ tính compute trực tiếp mà không có shared cost, kết quả thấp hơn; báo cáo phải ghi rõ scope.

### 9.4. Cost per attempt và cost per success

Có 50.000 attempts nhưng 40.000 thành công, tổng chi phí $8.000:

- Cost per attempt = $8.000 / 50.000 = $0,16.
- Cost per successful checkout = $8.000 / 40.000 = $0,20.

Nếu success rate giảm, cost per success tăng dù tổng bill không đổi. Phân tích nguyên nhân: traffic mix, business decline, lỗi platform, fraud policy hay campaign; không mặc định service owner gây inefficiency.

## 10. Liên kết telemetry với business workflow

Để tính cost per journey, cần biết request/event thuộc service, capability và workflow nào. Có thể dùng OpenTelemetry traces, propagated trace context, business correlation IDs và metrics tổng hợp.

### 10.1. Trace context

~~~text
checkout.request
  ├─ order.create
  ├─ inventory.reserve
  ├─ payment.authorize
  ├─ kafka.publish
  └─ fulfillment.schedule
~~~

Trace context nối span đồng bộ và một số bước async. Tuy nhiên trace sampling có thể bỏ nhiều journeys; không lấy một trace mẫu làm số liệu chính xác cho tổng usage nếu không điều chỉnh sampling bias.

### 10.2. Business correlation ID

Có thể truyền workflow ID hoặc correlation ID qua event headers/logs/traces để nối hành trình. Không đưa customer email, token, payment card hoặc raw order ID làm Prometheus label. Dùng ID có quyền kiểm soát trong traces/logs, aggregate metrics theo service, region, capability và outcome.

### 10.3. Metric tổng hợp

~~~text
service_compute_seconds_total{service="order",capability="checkout"}
workflow_steps_total{capability="checkout",service="payment",step="authorize"}
workflow_terminal_total{capability="checkout",outcome="success"}
service_egress_bytes_total{service="inventory",destination_class="database"}
log_ingested_bytes_total{service="order",environment="production"}
db_query_cpu_seconds_total{database="commerce",consumer="order"}
~~~

Tên metric minh họa. Container CPU seconds có thể lấy từ runtime telemetry rồi join với service metadata. Đừng giả định provider tự xuất cost per trace.

### 10.4. Gán service cost xuống workflow

Nếu Payment Service tốn $1.800 và 70% compute/requests gắn với checkout, có thể gán $1.260 cho checkout và phần còn lại cho refund/other flows. Driver phải phản ánh **tài nguyên sử dụng**, không chỉ tỷ trọng business events nếu request có độ nặng khác nhau.

Refund API có thể chỉ chiếm 5% requests nhưng dùng nhiều reconciliation/DB reads. Weighted usage theo CPU, DB, network hoặc execution time có thể chính xác hơn request count.

## 11. Attribution model cho chi phí shared

### 11.1. Direct attribution

Gán chi phí vào service/resource có owner rõ. Đây là bước đầu nên ưu tiên vì dễ audit.

### 11.2. Usage-based allocation

Chia pool theo driver đo được: CPU-seconds, memory GiB-hours, bytes, query time, requests hoặc retained bytes. Phù hợp khi telemetry đủ tốt.

### 11.3. Weighted allocation

\[
Share_i=\sum_{k=1}^{m}w_k\times UsageShare_{i,k}
\]

với \(\sum w_k=1\). Chỉ áp dụng khi driver không double count và weights có lý do. Ví dụ DB cost dùng query execution, storage và I/O.

### 11.4. Fixed allocation

Chia đều hoặc theo số service/team/tenant. Dễ thực hiện nhưng có thể không công bằng. Chỉ phù hợp phần fixed baseline nhỏ hoặc chi phí quản trị không có driver tốt.

### 11.5. Capacity reservation

Team yêu cầu node pool/replica/dedicated DB capacity để đáp ứng SLO. Phần reserved có thể gán theo reservation, kể cả lúc không dùng hết. Điều này tạo động lực yêu cầu tài nguyên có trách nhiệm.

### 11.6. Central platform allocation

Một số chi phí platform là đầu tư chung, không nên ép toàn bộ xuống product teams. Có thể giữ central cost center cho resilience, security baseline, shared tooling và platform R&D.

## 12. Công thức tổng quát

Cho service \(i\) trong kỳ \(t\):

\[
C_{i,t}=D_{i,t}+\sum_{p=1}^{P}Pool_{p,t}\times Share_{i,p,t}
\]

Trong đó \(D\) là direct costs; \(Pool\) là shared cost pool; \(Share\) là tỷ trọng của service trong pool. Với mỗi pool được phân bổ đầy đủ:

\[
\sum_i Share_{i,p,t}+UnallocatedShare_{p,t}=1
\]

Phần unallocated có thể gồm unknown tags, platform overhead hoặc capacity chưa quy thuộc. Không xóa dòng này để ép từng team chịu chi phí chưa có bằng chứng.

### 12.1. Ví dụ nhiều pool

Trong tháng:

- Direct compute Order: $1.000.
- Shared compute pool: $6.000, Order share 30%.
- Shared database pool: $3.000, Order share 25%.
- Shared observability pool: $1.000, Order share 20%.

\[
C_{Order}=1000+6000(0.30)+3000(0.25)+1000(0.20)=\$4{,}150
\]

Đây là chi phí được phân bổ cho Order theo policy giả định. Không cộng toàn bộ shared pool vào mỗi service; tổng allocation phải khớp từng pool sau unallocated.

## 13. SQL minh họa cho allocation data

~~~sql
CREATE TABLE cloud_cost_line_items (
    billing_date DATE NOT NULL,
    resource_id TEXT NOT NULL,
    cost_pool TEXT NOT NULL,
    amount NUMERIC(18, 6) NOT NULL,
    currency CHAR(3) NOT NULL,
    tags JSONB,
    PRIMARY KEY (billing_date, resource_id, cost_pool)
);

CREATE TABLE resource_usage_daily (
    usage_date DATE NOT NULL,
    resource_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    cpu_seconds NUMERIC(20, 6),
    memory_gib_hours NUMERIC(20, 6),
    storage_gib_month NUMERIC(20, 6),
    network_egress_gib NUMERIC(20, 6),
    PRIMARY KEY (usage_date, resource_id, service_id)
);

CREATE TABLE allocation_rules (
    rule_version TEXT NOT NULL,
    cost_pool TEXT NOT NULL,
    driver_name TEXT NOT NULL,
    weight NUMERIC(8, 6) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    PRIMARY KEY (rule_version, cost_pool, driver_name)
);
~~~

Đây là mô hình khái niệm. Billing export thực tế có thể có line items, credits, discounts, taxes, refunds và usage periods khác nhau. Nên giữ raw source bất biến hoặc có version để audit.

### 13.1. Phân bổ compute theo CPU usage

~~~sql
WITH service_usage AS (
    SELECT usage_date, service_id, SUM(cpu_seconds) AS cpu_seconds
    FROM resource_usage_daily
    GROUP BY usage_date, service_id
),
pool_usage AS (
    SELECT usage_date, SUM(cpu_seconds) AS total_cpu_seconds
    FROM service_usage
    GROUP BY usage_date
)
SELECT
    u.usage_date,
    u.service_id,
    c.amount * u.cpu_seconds / NULLIF(p.total_cpu_seconds, 0)
      AS allocated_cost
FROM service_usage u
JOIN pool_usage p USING (usage_date)
JOIN daily_compute_pool_cost c USING (usage_date);
~~~

Query chỉ minh họa. Production cần join theo pool/resource scope, currency, discount allocation, environment, reserved capacity và billing period. Nếu một resource chạy nhiều service nhưng usage không được đo per-service, SQL không thể tự suy ra chính xác.

### 13.2. Reconciliation

~~~sql
SELECT
    billing_date,
    cost_pool,
    SUM(allocated_amount) AS allocated,
    SUM(unallocated_amount) AS unallocated,
    MAX(source_pool_amount) AS source_amount,
    SUM(allocated_amount) + SUM(unallocated_amount)
      - MAX(source_pool_amount) AS variance
FROM allocation_results
GROUP BY billing_date, cost_pool;
~~~

Mục tiêu là variance bằng 0 trong tolerance đã định hoặc có giải thích về rounding, late billing adjustments và currency conversion. Không cộng source pool total lặp theo từng service.

## 14. Billing basis: actual, amortized và credits

Cloud invoice không phải lúc nào cũng là usage × list price:

- Discounts/committed use có thể tính ở billing account.
- Credits, refunds và taxes thay đổi tổng phải trả.
- Reservation/savings plan có upfront và recurring components.
- Shared services có minimum charge.
- Cross-region traffic và support fees có thể xuất hiện riêng.
- Billing export có thể đến trễ hoặc điều chỉnh hồi tố.
- Currency conversion có thể dùng tỷ giá theo kỳ kế toán.

Cần chọn và công bố basis:

- **Unblended cost:** giá line item theo billing source, trước một số phân bổ discount.
- **Amortized/effective cost:** phân bổ chi phí cam kết/discount theo thời gian sử dụng.
- **Net cost:** sau credits/discounts theo quy tắc thống nhất.
- **Cash/invoice view:** số tiền thực trả theo hóa đơn/kỳ kế toán.

Không trộn basis giữa service/team. Báo cáo FinOps nên drill-down từ allocation tới billing export và giải thích khác biệt với Finance invoice.

### 14.1. Shared discounts

Nếu enterprise discount cấp ở account level, cần policy phân bổ theo eligible usage, effective rate hoặc central discount pool. Không tùy tiện dùng discount để làm một team trông rẻ hơn. Reservation mua cho workload cụ thể có thể gán benefit cho workload đó.

## 15. Cost per business journey: phương pháp thực tế

### 15.1. Xác định boundary

Một journey cần có:

- Start event, ví dụ CheckoutStarted.
- Terminal success, ví dụ OrderCompleted theo domain contract.
- Failure/cancel/timeout states.
- Correlation/trace linkage.
- Asynchronous steps và deadline.
- Quy tắc retry và compensation.
- Time window/cohort để tránh denominator chưa trưởng thành.

Một journey có thể kéo dài vài phút hoặc vài ngày. Với shipment, không lấy đơn tạo hôm nay làm thất bại nếu deadline giao hàng chưa tới.

### 15.2. Gán service usage cho journey

Có thể dùng:

1. Span/trace attribution cho synchronous request.
2. Correlation ID trong message headers cho async steps.
3. Aggregate metrics theo capability/service.
4. DB query/bytes usage theo consumer nếu có metering.
5. Cost model per service rồi chia theo capability workload share.
6. Sampling correction hoặc statistical estimate khi không thể trace toàn bộ.

Không phải mọi CPU cycle truy ngược được tới một order. Background compaction, cache warming, health checks và platform idle capacity cần allocation riêng hoặc driver tổng hợp.

### 15.3. Unit economics nhiều cấp

| Metric | Công thức | Dùng để |
|---|---|---|
| Cost per request | Service cost / eligible requests | Hiệu quả API/service |
| Cost per attempt | Journey cost / attempts | Chi phí trước kết quả |
| Cost per successful journey | Journey cost / successful journeys | Unit economics |
| Cost per active customer | Allocated cost / active customers | Cost-to-serve |
| Cost per GB retained | Storage cost / GB-month | Data lifecycle |
| Cost per event | Broker/consumer cost / events | Event processing |
| Cost per shipment | Fulfillment cost / shipments | Logistics |
| Cost per refund | Refund flow cost / completed refunds | After-sales |

Tử số và mẫu số phải cùng kỳ và cùng cohort logic. Nếu cost thuộc tháng 6 nhưng một số journeys bắt đầu tháng 6 hoàn tất tháng 7, unit cost có thể sai lệch. Dùng cohort maturity hoặc phân bổ theo event time/processing period tùy mục tiêu.

## 16. Shared journey và multi-tenancy

Một request có thể phục vụ nhiều users/tenants; một batch job có thể xử lý hàng nghìn orders. Gán toàn bộ chi phí batch cho order đầu tiên là sai.

Các phương pháp:

- **Per-record allocation:** chia theo số record nếu workload đồng đều.
- **Weighted records:** dùng complexity/bytes/CPU estimate per record.
- **Batch fixed + variable:** một phần chia theo số jobs, phần còn lại theo volume.
- **Tenant quota:** charge theo capacity reserved hoặc usage metered.
- **Service pool:** giữ chi phí shared nếu không thể quy về journey.
- **Activity-based costing:** xác định hoạt động tạo chi phí và driver.

### 16.1. Privacy và fairness

Cost per tenant hữu ích cho enterprise contracts, nhưng không nhất thiết cần gắn user ID vào metrics. Có thể tính trong warehouse có quyền truy cập, aggregate theo tenant tier và giữ raw identifiers ở nơi được kiểm soát.

Một tenant tạo nhiều requests nhẹ; tenant khác ít requests nhưng query nặng. Chargeback theo request count có thể không công bằng. Cân nhắc weighted compute units, storage/egress metering hoặc capacity reservation. Mô hình phải được giải thích trong contract.

## 17. Cost of retries, failures và inefficiency

Một journey thất bại vẫn tiêu tốn:

- Retry API/DB/PSP.
- Duplicate message processing.
- Timeout chờ connection.
- Compensation/refund.
- Dead-letter queue và reconciliation.
- Repeated search queries do UX lỗi.
- Rebuild index sau bug.
- Log/trace volume tăng trong incident.

Nếu chỉ chia chi phí cho successful journeys, failed journeys bị bỏ khỏi denominator nhưng chi phí của chúng vẫn trong numerator. Điều đó có thể đúng về unit economics, nhưng cần phân tích **cost of failure** riêng.

Ví dụ tổng chi phí checkout path $10.000, có 45.000 successful checkouts và 5.000 failed/abandoned attempts:

- Cost per successful = $10.000 / 45.000 = $0,2222.
- Cost per attempt = $10.000 / 50.000 = $0,20.

Nếu retry storm làm chi phí tăng $2.000 mà số success không đổi, cost per success tăng lên $0,2667. Đây là tín hiệu cần điều tra; nguyên nhân có thể là provider outage hoặc client behavior, không nhất thiết do service owner.

### 17.1. Failure attribution

Có thể tách chi phí theo success path, business decline, platform failure/retry, fraud/review path, compensation/refund và operational incident. Phân loại rõ giúp Product thấy cost-to-serve và SRE thấy chi phí do reliability debt.

## 18. Chi phí observability và dữ liệu

Observability vừa là công cụ kiểm soát vừa là cost center.

### 18.1. Logs

Chi phí thường phụ thuộc bytes ingest, indexing, retention và query. Có thể giảm bằng structured logs, sampling có chọn lọc, giảm debug logs production, deduplicate errors, retention theo classification và archive sang tier rẻ hơn. Không log PII/secret; cũng không cắt audit/security logs tùy tiện.

### 18.2. Metrics

Cardinality tăng khi labels chứa user ID, order ID, raw URL hoặc exception text. Dùng labels hữu hạn, histogram buckets hợp lý và recording rules.

### 18.3. Traces

Sampling toàn bộ traces ở traffic cao có thể tốn kém. Tail-sample lỗi/slow traces và head-sample baseline có thể hữu ích, nhưng nếu dùng traces để attribution cost cần hiểu sampling rate, span completeness và bias.

### 18.4. Data protection

Encryption, backups, audit, retention và regional replication có chi phí nhưng có thể là yêu cầu bắt buộc. Tối ưu bằng classification, retention, compression, tiering và access patterns; không bỏ controls cần thiết.

## 19. Chi phí resilience: HA, DR và idle headroom

Một hệ thống Tier-1 có thể cần nhiều replicas, standby DB, broker replication, cross-zone traffic, backup/restore drills, warm standby DR, capacity headroom và on-call.

Nếu phân bổ hết overhead cho service traffic cao, nó có thể bị đánh giá quá đắt; nếu giữ toàn bộ ở Platform, product teams không thấy cost của yêu cầu SLO cao. Có thể chia:

- **Baseline resilience:** central platform pool.
- **Incremental resilience:** capacity/replication riêng do capability yêu cầu.
- **Data-specific DR:** backup/replica tăng thêm do data owner.
- **Regulatory controls:** central compliance pool hoặc domain cost center.

Phân biệt **chi phí phục vụ business requirement** với **chi phí do inefficiency**. Replica dự phòng cần thiết không phải lãng phí; ba replicas idle do autoscaler cấu hình sai có thể cần tối ưu.

## 20. Showback trước, chargeback sau

### 20.1. Showback

Báo cáo mỗi team gồm direct/shared cost, usage drivers, trend tháng/tháng, cost per service/unit, unallocated portion, confidence và top anomalies/actions. Mục tiêu là kiểm tra mô hình và nhận phản hồi.

### 20.2. Chargeback

Chỉ áp khi:

- Ownership taxonomy ổn định.
- Billing data được reconcile.
- Shared-cost rules được công bố và phê duyệt.
- Team có quyền kiểm soát driver bị charge.
- Có dispute và correction process.
- Finance thống nhất accounting basis, discounts, tax và currency.
- Có policy cho central overhead, unallocated và exceptions.

Nếu chargeback dùng số ước tính chưa đáng tin để cắt ngân sách, team có thể tối ưu metric cho đẹp hoặc tránh nhận ownership. Showback minh bạch là bước học cần thiết.

### 20.3. Không dùng chargeback để trừng phạt

Mục đích là tạo trách nhiệm và quyết định đầu tư. Chi phí tăng có thể do growth, SLO mới, security requirement hoặc incident dependency bên ngoài. Tách growth-driven spend, price/discount changes, architectural inefficiency và incident costs.

## 21. Budget, forecast và anomaly detection

Một cost allocation system nên có:

- **Budget:** ngưỡng chi phí theo tháng/quý.
- **Forecast:** dự báo cuối kỳ theo usage và commitments.
- **Anomaly:** phát hiện thay đổi bất thường so với baseline.

Ví dụ budget tháng:

| Đối tượng | Budget giả định | Owner |
|---|---:|---|
| Checkout capability | $12.000 | Checkout domain |
| Search | $5.000 | Discovery team |
| Notification | $2.000 | Messaging team |
| Shared platform | $8.000 | Platform |
| DR/resilience | $4.000 | SRE/Platform |

Budget cần xét seasonality và growth. Tháng campaign lớn không thể so trực tiếp tháng thấp điểm mà không chuẩn hóa business volume.

### 21.1. Theo dõi normalized cost

Một service tăng từ $1.000 lên $1.300 có thể hợp lý nếu orders tăng 50%. Service khác giữ bill $1.000 nhưng cost per successful order tăng gấp đôi do success rate giảm. Theo dõi spend vs budget/forecast, spend growth vs workload growth, unit cost, anomalies, unallocated spend, idle capacity, retention và retries.

### 21.2. Forecast đơn giản

\[
Forecast_{month}=Actual_{toDate}+ExpectedDailyRunRate\times RemainingDays
\]

Run rate nên điều chỉnh weekday/weekend, campaign, billing delays và committed usage. Không ngoại suy một ngày spike thành cả tháng nếu đó là sự kiện một lần.

## 22. FinOps review: từ số liệu tới hành động

Một review tốt không dừng ở “Search tốn nhiều nhất”. Hãy hỏi:

1. Chi phí tăng vì volume, unit price, resource shape, retention hay discount?
2. Service nào tạo usage, ai sở hữu và ai có thể thay đổi?
3. Có SLO/latency/business trade-off nào nếu tối ưu?
4. Tối ưu nào làm giảm actual bill, tối ưu nào chỉ giảm attributed share?
5. Chi phí one-off có bị nhầm thành recurring?
6. Có thể xóa/scale down resource không dùng mà không ảnh hưởng DR?
7. Đã đo trước/sau cùng workload profile chưa?
8. Có tác động tới security/compliance/data durability không?

Ví dụ Search chiếm 28% cluster compute. Điều tra thấy index replicas nhiều, cache hit ratio thấp, query retry tăng, debug logs lớn và node pool memory-bound. Không nên giảm replicas 50% ngay; kiểm load, failover, search SLO, query correctness và index recovery trước.

Cost optimization có thể làm tăng cost nơi khác: giảm retention logs giảm bill nhưng tăng thời gian điều tra incident; serverless giảm idle cost nhưng tăng cold start; compression giảm storage nhưng tăng CPU. So **total cost và business outcome**, không chỉ một line item.

## 23. Serverless và managed containers

Với serverless, cost có thể tính theo invocation, CPU/memory duration, concurrency, request count, egress và minimum instances. Attribution cần function/service identity, environment/region, execution duration, memory, request/event count, concurrency, cold start, retries và shared networking.

Với managed containers, provider có thể charge instance-hours hoặc CPU/memory allocation. Nếu một instance chạy nhiều process, cần telemetry per container/process. Nếu billing theo instance, allocation có thể dựa reserved share, actual utilization hoặc concurrency.

Không so serverless với Kubernetes chỉ bằng compute price. So TCO gồm idle capacity, observability, network, support, engineering effort, SLO và operational risk.

## 24. Data platform và data gravity

Data lake/warehouse có thể phục vụ nhiều domains. Cost drivers gồm storage GB-month, query bytes scanned/compute seconds, ingestion/stream processing, materialization/refresh, retention/replication và egress.

Một team chạy query không tối ưu có thể tiêu phần lớn warehouse compute. Allocation theo query owner/cost label hữu ích, nhưng cần kiểm retries, shared dashboards và scheduled jobs. Data platform nên cung cấp budgets, query limits, caching và remediation.

Retention vừa là quyết định chi phí vừa là governance. Giữ events lâu hơn hỗ trợ replay/audit/analytics nhưng tăng storage và security/privacy obligations. Không xóa event để giảm bill khi nó còn là nguồn sự thật hoặc bằng chứng bắt buộc.

## 25. Unit economics và quyết định sản phẩm

| Capability | Cost per unit giả định | Trend | Câu hỏi |
|---|---:|---|---|
| Successful checkout | $0,20 | +12% MoM | Retry, payment fees, infra hay mix? |
| Search session | $0,004 | -5% MoM | Cache/query efficiency cải thiện? |
| Shipment | $0,35 | +8% MoM | Carrier hay fulfillment? |
| Refund completed | $0,08 | +20% MoM | Volume hay reconciliation? |
| Notification delivered | $0,001 | ổn định | Provider/retention? |

Cost per unit không tự trả lời lợi nhuận. Cần revenue, payment fees, refunds, discounts, fraud losses, fulfillment, support và margin. Checkout rẻ hơn nhưng oversell/fraud tăng có thể làm unit economics xấu hơn.

### 25.1. Cohort và mix effects

So theo channel, region, device, payment method hoặc product class có thể giải thích khác biệt. Nhưng dimensions cần có lý do kinh doanh và bảo vệ privacy. Tháng có nhiều international cards có thể tăng PSP fees dù kiến trúc không đổi.

### 25.2. Cost-to-serve theo customer tier

Enterprise tenant có thể cần dedicated capacity, data residency và custom retention. Cost-to-serve cao hơn nhưng contract pricing/strategic value có thể bù. Phân bổ hỗ trợ quyết định pricing, không tự quyết định khách nào nên giữ/bỏ.

## 26. Central overhead và avoidable cost

Một số chi phí không nên chargeback trực tiếp:

- Platform R&D và enablement.
- Security baseline và compliance.
- DR readiness toàn tổ chức.
- Enterprise support contract.
- Corporate network/identity.
- Unallocated headroom.
- Innovation/experimentation.

Có thể giữ central cost center hoặc phân bổ theo headcount/revenue/usage ở cấp tổ chức nếu Finance cần. Ghi rõ central pool, không lẫn vào cost per service khi unit economics chỉ đo variable cost.

### 26.1. Allocated khác avoidable

Một service bị phân bổ $5.000 shared node cost nhưng nếu xóa service, cluster vẫn chạy và bill không giảm. $5.000 là attributed cost, chưa chắc là avoidable cost. Quyết định đóng service cần xét incremental/avoidable cost, migration effort và shared capacity.

### 26.2. Fully loaded và marginal cost

- **Fully loaded cost:** direct + allocated shared + overhead.
- **Marginal cost:** chi phí tăng thêm khi xử lý request/order/tenant.
- **Avoidable cost:** phần có thể thực sự loại bỏ bằng một quyết định.
- **Committed cost:** khoản đã cam kết hoặc khó giảm trong kỳ.

Unit economics có thể cần fully loaded; pricing/scale decision thường cần marginal cost; consolidation cần avoidable cost. Đừng dùng một số cho mọi quyết định.

## 27. Chất lượng dữ liệu attribution

Cost data có thể thiếu, trễ hoặc không đồng nhất:

- Billing line item đến muộn.
- Resource tags thiếu hoặc sai.
- Autoscaled resources thay đổi owner.
- Shared services không có usage breakdown.
- Telemetry sampling và clock mismatch.
- Discounts/credits điều chỉnh hồi tố.
- Trace bị mất hoặc không nối async workflow.
- Một resource phục vụ nhiều services theo thời gian.
- Currency conversion và accounting date khác usage date.

Nên gắn confidence:

| Confidence | Ý nghĩa | Cách sử dụng |
|---|---|---|
| High | Direct billing tag/usage metering rõ | Showback/chargeback theo policy |
| Medium | Driver nội bộ đáng tin nhưng là proxy | Planning/showback, ghi phương pháp |
| Low | Ước tính fixed share hoặc thiếu telemetry | Giữ shared/unallocated, không dùng phạt ngân sách |

Báo cáo trung thực với 5% unallocated tốt hơn báo cáo gán sai 100% hóa đơn.

### 27.1. Late-arriving billing data

Billing export có thể điều chỉnh sau kỳ sử dụng. Báo cáo nên có trạng thái preliminary/finalized, usage period, ingest time và revision. Nếu tháng trước đã chargeback rồi có credit hồi tố, cần quy trình điều chỉnh có audit.

## 28. Pipeline cost data

~~~mermaid
flowchart LR
    B[Cloud Billing Exports] --> S[Raw Cost Storage]
    U[Runtime Usage Metrics] --> S
    C[Service Catalog / Ownership] --> T[Normalize and Join]
    S --> T
    W[Workflow / Business Events] --> T
    T --> A[Allocation Engine]
    A --> R[Reconciliation and Confidence]
    R --> D[Cost Dashboards / Showback]
    D --> F[Budget, Forecast and Actions]
~~~

Các lớp:

1. **Ingestion:** billing exports, provider usage, cluster metrics, service catalog, workflow aggregates.
2. **Raw storage:** giữ source records bất biến hoặc có version.
3. **Normalization:** currency, dates, resource IDs, tag aliases, discount basis.
4. **Enrichment:** map resource tới service/team/domain/environment.
5. **Allocation:** direct assignment, pool drivers, weights và unallocated.
6. **Reconciliation:** so với invoice/source totals.
7. **Presentation:** showback, unit economics, budget và anomaly.
8. **Governance:** rule versions, approvals, disputes, audit và corrections.

Không để mỗi dashboard chứa công thức allocation riêng. Một engine/rule layer versioned giúp mọi báo cáo dùng cùng định nghĩa.

## 29. Allocation record có lineage

~~~json
{
  "period": "2026-11",
  "service_id": "order-service",
  "team": "team-order",
  "cost_pool": "shared-compute",
  "source_amount": 10000.00,
  "currency": "USD",
  "driver": "weighted_cpu_memory",
  "usage_share": 0.35,
  "allocated_amount": 3500.00,
  "rule_version": "allocation-v2",
  "confidence": "medium",
  "source_reference": "billing-export-partition-2026-11",
  "calculated_at": "2026-12-02T03:00:00Z"
}
~~~

Một allocation record cần period, source, driver, weight/rule version, currency, owner và confidence. Không chỉ lưu kết quả cuối vì khi rule đổi sẽ không giải thích được số tháng trước.

### 29.1. Versioning policy

Khi đổi từ CPU-only sang weighted CPU+memory, cần ngày hiệu lực, lý do, impact analysis, backfill hay không, cách tính lại kỳ đã finalized, người phê duyệt và release note. Không đổi driver giữa kỳ mà không thông báo rồi so trends như thể cùng phương pháp.

## 30. Chargeback: kiểm soát và dispute

Nếu dùng chargeback chính thức:

1. Publish cost statement theo kỳ và basis.
2. Team xem direct/shared allocation và usage evidence.
3. Có cửa sổ dispute với resource IDs và driver.
4. Allocation owner phản hồi và điều chỉnh nếu sai.
5. Finance finalize kỳ và xử lý late credits.
6. Ghi audit trail cho correction.
7. Không cho team tự sửa billing source hoặc rule để giảm charge.
8. Có policy cho central/unallocated spend.
9. Escalation nếu dispute ảnh hưởng ngân sách lớn.
10. Review fairness định kỳ.

Chargeback không thay thế quản lý sản phẩm. Domain tăng chi phí vì business growth khác với service tạo bill do retry storm không kiểm soát.

## 31. Budget guardrails trong CI/CD

Một số chi phí có thể phát hiện trước khi apply:

- Terraform plan tạo thêm 30 GPU nodes.
- Thay retention từ 7 lên 365 ngày.
- Tạo database replica lớn hơn.
- Bật verbose logging ở mọi service.
- Mở egress route qua NAT đắt hơn.
- Tăng min instances/reserved concurrency.
- Thêm license seats hoặc managed cluster.

CI có thể ước tính delta cost, cảnh báo owner hoặc route high-impact changes. Estimate không chính xác tuyệt đối do discount, actual traffic và provider pricing; dùng như **guardrail/delta signal**, không thay hóa đơn.

### 31.1. Budget policy minh họa

~~~yaml
costPolicy:
  service: order-service
  environment: production
  monthlyBudgetUsd: 6000
  warningThreshold: 0.80
  criticalThreshold: 1.00
  forecastAlert: true
  owner: team-order
  actions:
    warning:
      - notify-owner
      - review-unit-cost
    critical:
      - notify-platform-and-finance
      - require-capacity-review
~~~

Đây là cấu hình minh họa. Không tự động scale down hoặc block deployment chỉ vì budget threshold; một payment system có thể cần capacity để khắc phục outage dù vượt ngân sách. Phân biệt cảnh báo chi phí với hành động ảnh hưởng availability.

## 32. Tối ưu theo service và journey

### 32.1. Right-sizing

So requested/limit với actual usage, headroom, peak và failover. Giảm overprovisioning nhưng giữ đủ capacity khi node/zone mất.

### 32.2. Autoscaling

Chọn metric phù hợp (concurrency, queue age, CPU, request rate), min/max, stabilization windows và quota. Autoscaling quá nhạy tạo churn/cold starts; quá chậm gây queue/latency.

### 32.3. Giảm fan-out và retry

Một checkout gọi tám downstream services tạo nhiều network/compute. Tối ưu batching, caching, request coalescing, timeouts, retry budgets và circuit breakers. Không bỏ retry cần thiết; mục tiêu là tránh retry storm và call không có giá trị.

### 32.4. Data lifecycle

Partition, compression, retention, archival và deletion có thể giảm storage/compute. Kiểm audit, privacy, replay và legal retention trước khi đổi.

### 32.5. Observability efficiency

Giảm debug noise, sampling có kiểm soát, cardinality và retention tiering. Giữ critical events/security evidence và khả năng điều tra incident.

### 32.6. Managed vs self-managed

So TCO managed DB/broker với tự vận hành gồm compute, license, backups, on-call, patching, DR và incident risk. Managed service giá cao hơn trên invoice vẫn có thể rẻ hơn fully loaded.

### 32.7. Architecture simplification

Service quá nhỏ, ít traffic nhưng tạo deployment/runtime/observability overhead có thể hợp nhất nếu boundaries không mang lại lợi ích tương xứng. Cần xem ownership, security, release independence và failure isolation; không gộp chỉ để giảm bill nếu tăng coupling/blast radius.

## 33. Trade-offs và nguy cơ tối ưu sai

| Hành động | Lợi ích | Trade-off/rủi ro |
|---|---|---|
| Giảm replicas | Ít compute | Giảm HA/headroom, tăng latency |
| Giảm log retention | Giảm ingest/storage | Điều tra/security/audit kém |
| Sampling traces thấp hơn | Giảm observability bill | Mất bằng chứng hiếm |
| Serverless scale-to-zero | Giảm idle | Cold start, latency, quota |
| Dedicated DB per service | Ownership rõ | Nhiều baseline/backup/ops |
| Shared DB | Ít overhead | Coupling, noisy neighbor, allocation khó |
| Nén dữ liệu | Giảm storage/network | Tăng CPU và complexity |
| Batch processing | Throughput cao hơn | Latency, retry/recovery phức tạp |
| Multi-region | RTO tốt hơn | Replication/egress/consistency cost |
| Chargeback chính xác hơn | Accountability | Telemetry, governance, dispute cost |

Quyết định tối ưu phải xem **chi phí, reliability, security, developer productivity và business outcome cùng lúc**. Không tối ưu một line item rồi tạo chi phí lớn hơn ở nơi khác.

## 34. Case study: cost per successful checkout tăng

### 34.1. Số liệu giả định

Tháng trước: allocation $8.000, successful checkouts 40.000, unit cost $0,20.

Tháng này: allocation $9.600, successful checkouts 40.000, unit cost $0,24.

Tổng chi phí tăng 20%, output không đổi, unit cost tăng 20%.

### 34.2. Điều tra

- Payment retry count tăng sau PSP timeout.
- Order CPU tăng do duplicate workflow events.
- Kafka retention tăng do consumer lag.
- Logs tăng vì debug logging production.
- DB query time tăng do reporting query dùng chung.
- Traffic mix có thể đã thay đổi.

### 34.3. Hành động

1. Giới hạn retries/backoff và kiểm idempotency.
2. Sửa consumer duplication và xử lý backlog.
3. Hạ log verbosity có kiểm soát, giữ audit/security logs.
4. Tách/report query workload hoặc giới hạn resource.
5. Load test và so cost/unit trước/sau.
6. Theo dõi checkout SLO, payment integrity và cost per success.

Không chỉ giảm node count; nguyên nhân có thể là mỗi checkout tạo nhiều work hơn.

## 35. Case study: shared platform bị gán chi phí không công bằng

Một Kubernetes cluster $20.000/tháng phục vụ 10 teams. Team A nhiều CPU, Team B memory-heavy, Team C chạy batch theo giờ, Platform cần headroom và system daemons.

Chia đều $2.000/team sai khác usage. Chia theo CPU khiến Team B bị under-allocated. Chia theo requested CPU/RAM có thể tính batch team phần reserved capacity dù chỉ chạy vài giờ; điều đó có thể đúng nếu reservation là do team yêu cầu, nhưng cần phân biệt reserved và consumed.

Một mô hình:

- Dedicated pools gán trực tiếp.
- Shared pool chia theo weighted CPU/memory request + actual usage.
- System/daemon overhead và resilience headroom giữ central.
- Batch reservation gán theo reserved capacity nếu đã phê duyệt.
- Unallocated usage báo riêng.
- Mỗi quý review driver và đối chiếu node capacity.

Mục tiêu là rule nhất quán và minh bạch, không phải một công thức duy nhất hoàn hảo.

## 36. Case study: journey đi qua nhiều domains

Checkout tạo Order, Payment, Inventory và Notification. Refund xảy ra sau vài ngày, Shipment sau một ngày. Product muốn biết cost per successful checkout.

1. Định nghĩa workflow identity trong business event, không dùng raw ID làm metric label.
2. Trace synchronous calls và propagate correlation qua message headers.
3. Thu usage aggregates theo service/capability.
4. Gán compute, DB, broker, network và observability theo driver.
5. Gán background jobs bằng lineage/causation hoặc allocation rule.
6. Phân biệt cost phát sinh lúc checkout với cost hậu mãi.
7. Chọn unit economics: initial checkout, completed order, delivered order hay lifetime cost.
8. Đối soát successful order count với domain/financial source.

Có thể báo cáo hai số:

- **Cost to place an order:** chi phí tạo và xác nhận đơn.
- **Full cost to serve an order:** gồm fulfillment, notification, support, refunds và hậu mãi liên quan.

Không trộn hai khái niệm rồi so sánh với pricing model khác mà không thống nhất phạm vi.

## 37. Governance: ai quyết định driver?

| Vai trò | Trách nhiệm |
|---|---|
| FinOps/Finance | Billing basis, reconciliation, budget, accounting |
| Platform Engineering | Resource inventory, telemetry, shared pools |
| Service Owner | Service tags, usage interpretation, optimization |
| Domain/Product | Business journey definitions, unit denominator |
| SRE | Resilience overhead, SLO trade-offs, DR cost |
| Data Platform | Warehouse/retention/query allocation |
| Security/Compliance | Data classification, retention, controls |
| Leadership | Central overhead, budget ownership, dispute escalation |

### 37.1. Dispute workflow

Team có thể phản hồi resource không thuộc service, billing period lệch usage period, DB driver không phản ánh workload, discount phân bổ sai, ownership đã đổi, denominator thiếu workflows hoặc one-off bị tính thành recurring.

Mỗi dispute cần source evidence, owner, SLA xử lý, kết quả và audit. Không sửa dashboard bằng tay mà không sửa rule/source mapping.

### 37.2. Thay đổi allocation policy

Khi đổi driver/weight, cần version, effective date, impact analysis, approver, cách backfill và cách xử lý kỳ đã finalized. Mô hình phân bổ là một phần của governance, không phải query cá nhân trong dashboard.

## 38. Privacy và telemetry quality

Cost attribution càng chi tiết càng có nguy cơ tạo cardinality và privacy issues:

- Metric labels chỉ dùng dimensions hữu hạn.
- Trace/log IDs có access control và retention.
- Không log secrets, payment data, email hoặc payload nhạy cảm.
- Không lấy raw customer identifiers làm dimension mặc định.
- Aggregate theo capability, service, region, environment, outcome.
- Sampling rate và bias được ghi.
- Clock synchronization và event-time semantics rõ.
- Có quality score cho coverage, missingness và late data.

Nếu không thể nối một phần workflow với service usage, phân bổ vào shared pool hoặc estimate có confidence thay vì giả vờ attribution chính xác.

## 39. Dashboard FinOps

Một dashboard nên có các góc nhìn:

### 39.1. Executive

- Total spend, forecast, budget variance.
- Spend theo domain/cost center.
- Unit economics capability chính.
- Top anomalies và savings opportunities.
- Central/unallocated/one-off costs.

### 39.2. Team/service

- Direct vs shared allocated cost.
- CPU/memory/storage/network/observability.
- Cost per request/attempt/success.
- Month-over-month normalized by workload.
- Tag coverage, exceptions và actions.

### 39.3. Business journey

- Cost per successful checkout/delivered order/refund.
- Cost by region/channel/payment method tier nếu phù hợp.
- Failure/retry/compensation cost.
- Shared vs attributable portion.
- Cohort maturity và data confidence.

### 39.4. Engineering diagnostics

- Node utilization/requests/limits.
- DB query/IO/connection drivers.
- Queue bytes/retention/consumer throughput.
- Log/trace ingest and retention.
- Egress/NAT/inter-zone traffic.
- Forecast và capacity headroom.

Đặt unit economics và spend ownership ở tầng trên, driver và resource detail ở drill-down.

## 40. Lộ trình triển khai

### Giai đoạn 1 — Visibility

Kết nối billing exports; chuẩn hóa cost centers, teams, service IDs và tags; xây raw dataset/dashboard; tạo unallocated bucket và owner remediation. Chưa chargeback.

### Giai đoạn 2 — Direct allocation

Gán dedicated resources, reconcile invoice, báo direct cost theo service/environment/region, kiểm ownership catalog.

### Giai đoạn 3 — Shared pools

Chọn driver cho compute, DB, broker, network, observability; xác định fixed/variable/idle/resilience overhead; version rules, confidence và dispute process; chạy showback vài kỳ.

### Giai đoạn 4 — Unit economics

Định nghĩa business journey start/terminal events; thu workflow/usage aggregates; tính cost per request/attempt/success; kiểm cohort maturity và sampling bias; review với Product/Finance.

### Giai đoạn 5 — Budget và optimization

Đặt budgets/forecasts, anomaly alerts, review actions, đo actual savings và tác động SLO, tự động hóa remediation có guardrails.

### Giai đoạn 6 — Chargeback nếu cần

Finance approve accounting basis; owners chấp nhận allocation policy; dispute/late-adjustment workflow; audit và fairness review. Không charge phần low-confidence như actual metered cost.

## 41. Những sai lầm thường gặp

1. Chia đều hóa đơn cluster cho số service.
2. Gán toàn bộ shared cost cho team sở hữu Kubernetes.
3. Dùng CPU làm driver duy nhất cho mọi pool.
4. Cộng CPU request và actual usage như hai khoản độc lập.
5. Coi idle capacity là lãng phí mà bỏ qua HA/headroom.
6. Không tách direct, shared, central và unallocated.
7. Dùng request count cho mọi cost dù payload/complexity khác nhau.
8. Tính cost per order từ HTTP 202 thay vì terminal business outcome.
9. Bỏ qua retries, compensation và failed journeys.
10. Dùng sampled traces mà không điều chỉnh bias nhưng khẳng định unit cost chính xác.
11. Gắn user/order IDs vào metric labels gây cardinality/privacy risk.
12. Không reconcile allocations với billing source.
13. Trộn invoice, amortized và net cost basis.
14. Thay driver giữa kỳ mà không version/announce.
15. Ép unallocated spend về một team để tổng trông đẹp.
16. Chargeback trước khi ownership/telemetry đáng tin.
17. Dùng cost attribution để phạt team thay vì hỗ trợ quyết định.
18. Giảm retention/audit/security để đạt budget.
19. Scale down replicas mà không xem SLO/failure domains.
20. Chỉ tối ưu compute, bỏ qua network, storage, logs và labor.
21. Coi allocated cost là avoidable cost.
22. Dùng fully loaded cost để quyết định marginal pricing.
23. Không tính labor/on-call hoặc tính quá chính xác khi không có dữ liệu.
24. Bỏ qua growth/mix/seasonality khi so tháng.
25. Không có dispute/late credit workflow.
26. Dùng một allocation formula cho mọi workload.
27. Tự động scale down vì budget vượt mà không xét criticality.
28. Không bảo vệ privacy khi join cost với business events.
29. Chỉ báo tổng spend, không có cost per successful outcome.
30. Tối ưu một line item nhưng làm tăng tổng chi phí hoặc rủi ro.

## 42. Bài tập thực hành

### Bài A — Phân loại chi phí

Một hệ thống có ba services trên một cluster, DB dùng chung, Kafka, observability, NAT, DR region và một platform engineer. Phân loại direct/shared/central/one-off; chọn driver cho từng pool và nêu phần chưa thể phân bổ chính xác.

### Bài B — Tính shared compute allocation

Node pool có $12.000/tháng. Order CPU share 30%, memory share 40%; Payment 25%/25%; Inventory 20%/15%; Search 25%/20%. Với trọng số CPU 50%, memory 50%, tính weighted share và chi phí mỗi service. Giải thích vì sao weights phải được thống nhất và kiểm tra.

### Bài C — Cost per successful checkout

Chi phí checkout-related là $9.600, có 48.000 successful checkouts và 60.000 attempts. Tính cost per success và per attempt. Nếu retry storm làm bill tăng 15% nhưng success không đổi, unit cost thay đổi bao nhiêu?

### Bài D — Tìm driver phù hợp

DB dùng chung có CPU thấp nhưng storage/IOPS cao. Nếu phân bổ theo CPU, team Reporting chịu ít dù giữ bảng lịch sử lớn. Đề xuất weighted driver và cách tránh double-count.

### Bài E — Chargeback fairness

Platform sở hữu cluster và 8 product teams sử dụng. Thiết kế showback report, unallocated pool, dispute window, confidence labels và điều kiện chuyển sang chargeback.

### Bài F — Attribution cho async journey

Checkout kết thúc ở Order Service nhưng Notification và Fulfillment chạy sau đó nhiều giờ. Thiết kế correlation, cost boundary và cohort maturity để báo cost to place order và full cost to serve order.

### Bài G — Forecast

Actual spend tới ngày 10 là $3.000; expected daily run rate còn lại là $350/ngày trong tháng 30 ngày. Tính forecast cuối tháng theo mô hình đơn giản. Nêu yếu tố cần điều chỉnh như weekends, campaign, discounts và one-off spend.

### Bài H — FinOps optimization

Cost per successful checkout tăng 20%, compute tăng 5%, egress tăng 40%, logs tăng 80%, successful volume không đổi. Đề xuất trình tự điều tra và actions, kèm guardrails để không ảnh hưởng SLO/security.

### Bài I — Allocated và avoidable cost

Order Service bị phân bổ $4.000 shared cluster cost. Nếu xóa service, cluster bill chỉ giảm $500 vì node pool vẫn cần chạy cho services khác. Giải thích fully loaded, marginal và avoidable cost; quyết định nào dùng từng số.

### Bài J — Viết allocation policy

Tạo policy có direct costs, shared compute weights, DB driver, observability usage, unallocated bucket, confidence, effective date và dispute process. Ghi rõ ai phê duyệt và cách version/backfill.

## 43. Checklist áp dụng

### Nguồn dữ liệu và ownership

- [ ] Billing exports và usage telemetry được lưu có lineage.
- [ ] Service catalog có owner, team, cost center, domain, environment.
- [ ] Resource tags được validate và drift được phát hiện.
- [ ] Direct/shared/central/one-off pools được phân loại.
- [ ] Currency, billing period, discount basis và invoice reconciliation rõ.

### Allocation model

- [ ] Mỗi shared pool có driver phù hợp và công thức versioned.
- [ ] CPU, memory, storage, I/O, network và observability được xét theo đúng pool.
- [ ] Idle/resilience/central overhead có cách xử lý.
- [ ] Unallocated spend được hiển thị và có owner.
- [ ] Tổng allocation + unallocated reconcile với source.
- [ ] Confidence và limitations được công bố.
- [ ] Không double-count usage hoặc chi phí.
- [ ] Allocation rule có effective date và dispute process.

### Business unit economics

- [ ] Journey có start/terminal events và denominator rõ.
- [ ] Success/failure/cancel/decline được phân loại.
- [ ] Async/background work có lineage phù hợp.
- [ ] Sampling và missing telemetry được điều chỉnh/ghi nhận.
- [ ] Cohorts đủ trưởng thành theo workflow duration.
- [ ] Cost per attempt và cost per success được tách.
- [ ] Fully loaded, marginal và avoidable cost không bị nhầm.

### Governance và tối ưu

- [ ] Showback chạy trước chargeback.
- [ ] Budget, forecast và anomaly alerts có owner.
- [ ] Dispute/late adjustment có audit.
- [ ] Optimization được đo trước/sau cùng workload profile.
- [ ] SLO, security, privacy, retention và DR không bị hy sinh.
- [ ] Savings được phân biệt với allocated-share changes.
- [ ] Policy changes được version, review và thông báo.

## 44. Ghi nhớ cốt lõi

**Phân bổ chi phí tốt phải nối được ba lớp: hóa đơn và usage thực tế, ownership của dịch vụ, và kết quả nghiệp vụ mà hệ thống tạo ra.** Direct costs nên gán thẳng; shared pools cần driver có thể giải thích; phần chưa thể quy thuộc phải hiển thị minh bạch. Sau đó, cost per request/attempt/successful journey giúp nhóm nhìn thấy chi phí thực của việc phục vụ khách hàng.

Không có công thức hoàn hảo cho mọi tổ chức. Hãy bắt đầu với dữ liệu đáng tin, thống nhất taxonomy và billing basis, chạy showback để kiểm fairness, rồi mới chargeback nếu cần. Dùng số liệu tìm retry waste, overprovisioning, data retention, network và observability cost; đồng thời giữ SLO, security, privacy và khả năng khôi phục.

Một báo cáo thành công không phải là báo cáo phân bổ được 100% hóa đơn bằng mọi giá. Nó là báo cáo **có thể truy vết, giải thích được, chỉ rõ độ tin cậy và giúp team đưa ra quyết định tốt hơn về chi phí trên mỗi kết quả kinh doanh**.