# So sánh hiệu năng với chi phí và mục tiêu chất lượng

> **Chương:** Hiệu năng  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào cách so sánh hiệu năng, chi phí và mục tiêu chất lượng để chọn cấu hình kiến trúc phù hợp; đồng thời đánh giá đánh đổi giữa latency, throughput, availability, scalability, reliability, security, vận hành và tổng chi phí theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chuyển nhu cầu nghiệp vụ thành quality attributes, SLI/SLO và workload model có thể đo.
2. Phân biệt latency, throughput, concurrency, utilization, saturation và capacity; chọn metric phù hợp.
3. Thiết kế benchmark/load test công bằng và có thể lặp lại để so sánh phương án kiến trúc.
4. Quy đổi chi phí cloud thành cost per request, transaction, tenant hoặc đơn vị công việc hữu ích.
5. So sánh đường cong hiệu năng–chi phí, tìm Pareto frontier và điểm diminishing returns.
6. Đánh giá tradeoff của compute, storage, database, cache, network, managed services và scaling strategy.
7. Đưa ra quyết định dựa trên SLO, risk, total cost of ownership (TCO), headroom và bằng chứng thay vì chỉ chọn cấu hình nhanh nhất hoặc rẻ nhất.

## 1. Hiệu năng chỉ có ý nghĩa khi gắn với mục tiêu chất lượng

Một kiến trúc có thể trả response rất nhanh nhưng chi phí quá cao; một kiến trúc có cost thấp nhưng p99 latency vượt ngưỡng; hoặc một hệ thống có throughput cao nhưng tỷ lệ giao dịch sai tăng khi tải lớn. Vì vậy, hiệu năng không được đánh giá tách rời mục tiêu nghiệp vụ và các thuộc tính chất lượng.

Ví dụ nền tảng đặt chỗ:
- Người dùng cần tìm dịch vụ nhanh, kể cả giờ cao điểm.
- Checkout phải hoàn tất với trạng thái giao dịch đúng.
- Dashboard vận hành có thể trễ vài phút.
- Báo cáo tài chính cần đầy đủ và đối soát được.
- Chi phí trên mỗi booking phải nằm trong biên lợi nhuận.
- Hệ thống cần đủ headroom khi một availability zone gặp sự cố.

Các yêu cầu này không đồng nhất. Search có thể ưu tiên read cache và stale data trong giới hạn; checkout ưu tiên correctness và consistency; báo cáo ưu tiên completeness và cost-efficient batch processing.

**Câu hỏi kiến trúc cần trả lời không phải “cấu hình nào nhanh nhất?” mà là “cấu hình nào đạt chất lượng cần thiết với chi phí và rủi ro chấp nhận được?”**

### 1.1. Quality attributes thường gặp

| Thuộc tính | Câu hỏi đo lường | Metric/đích thường dùng |
| --- | --- | --- |
| Performance | Hành động hoàn thành nhanh đến đâu? | p50/p95/p99 latency, throughput |
| Scalability | Tải tăng thì năng lực tăng thế nào? | Throughput theo replica, scale time |
| Availability | Người dùng có hoàn thành được nghiệp vụ? | Journey success rate, error budget |
| Reliability | Hệ thống có giữ đúng hành vi khi lỗi? | Failure rate, recovery, data correctness |
| Security | Quyền và dữ liệu có được bảo vệ? | Unauthorized access, policy coverage |
| Maintainability | Có dễ thay đổi và vận hành? | Deployment lead time, toil, change failure |
| Cost efficiency | Đạt outcome với chi phí nào? | Cost/request, cost/transaction, TCO |
| Data quality | Kết quả có đúng và đủ? | Reconciliation, freshness, duplicate rate |

Không phải mọi quality attribute đều có thể tối ưu đồng thời. Tăng replication có thể tăng availability nhưng cũng tăng storage/network cost; cache có thể cải thiện latency nhưng làm tăng invalidation complexity và rủi ro stale data.

## 2. Từ yêu cầu nghiệp vụ tới SLI/SLO

### 2.1. Chuyển câu nói định tính thành yêu cầu đo được

Yêu cầu "ứng dụng phải nhanh" chưa đủ để chọn kiến trúc. Cần hỏi:
- Người dùng thực hiện hành động gì?
- Thời gian bắt đầu/kết thúc được đo ở đâu?
- Tải bình thường, peak và burst là bao nhiêu?
- Tỷ lệ thành công và tính đúng đắn cần đạt?
- SLO được đo theo request, transaction hay thời gian?
- Môi trường, vùng địa lý, thiết bị và phân khúc tenant nào thuộc phạm vi?

Ví dụ chuyển đổi:

| Yêu cầu ban đầu | Định nghĩa có thể kiểm chứng |
| --- | --- |
| Search nhanh | p95 search latency dưới 300 ms ở tải 2.000 request/giây với workload đã thống nhất |
| Checkout ổn định | 99,9% giao dịch hợp lệ đạt trạng thái nghiệp vụ xác định trong cửa sổ đo |
| Báo cáo đúng hạn | 99% batch kết thúc trước 06:00 và reconciliation sai lệch dưới ngưỡng |
| Hệ thống chịu peak | Xử lý 3 lần traffic giờ bình thường mà error rate vẫn dưới ngưỡng |
| Chi phí hợp lý | Cost per completed booking không vượt ngân sách mục tiêu ở tải bình thường và peak |

Các con số trên là giả định ví dụ, không phải chuẩn phổ quát. Product, SRE, Finance và Data owner cần xác nhận mẫu số, kỳ đo, loại trừ và nguồn metric.

### 2.2. SLI và SLO

- **SLI:** phép đo thực tế như tỷ lệ request hợp lệ thành công, p95 latency, queue age hoặc freshness.
- **SLO:** mục tiêu đặt cho SLI trong kỳ đo.
- **SLA:** cam kết với bên ngoài, có định nghĩa và điều khoản hợp đồng.

Ví dụ SLI latency có thể là tỷ lệ request hợp lệ hoàn thành dưới 300 ms:

\[
SLI_{\text{latency}} =
\frac{\text{Requests hoàn thành trong 300 ms}}
{\text{Tổng requests hợp lệ}}
\]

Đối với checkout, cần đo trạng thái nghiệp vụ đúng, không chỉ HTTP 2xx. Nếu payment provider timeout nhưng charge đã được thực hiện, request timeout không tự động đồng nghĩa giao dịch thất bại.

### 2.3. Multi-dimensional SLO

Một SLO duy nhất hiếm khi mô tả đầy đủ chất lượng. Có thể cần:
- Latency SLO.
- Availability/success SLO.
- Data correctness SLO.
- Freshness SLO.
- Capacity/queue-age objective.
- Cost budget hoặc unit-cost target.

Phải tránh đặt quá nhiều SLO không có owner hoặc không có hành động tương ứng. Mỗi SLO nên gắn với trải nghiệm hoặc rủi ro nghiệp vụ cụ thể.

## 3. Đo đúng hiệu năng: latency, throughput và saturation

### 3.1. Latency

Latency là thời gian từ điểm bắt đầu tới điểm kết thúc đã định nghĩa. Nên xem phân phối, không chỉ trung bình:
- p50: một nửa request nhanh hơn hoặc bằng giá trị này.
- p95: 95% request hoàn thành không chậm hơn giá trị này.
- p99: thể hiện tail latency ảnh hưởng nhóm request chậm nhất.
- Max: hữu ích để điều tra nhưng rất nhạy với outlier.

Average latency có thể che khuất tail latency. Một API có average 100 ms nhưng p99 3 giây vẫn có trải nghiệm kém cho một nhóm người dùng.

### 3.2. Throughput

Throughput là số công việc hoàn thành trên một đơn vị thời gian:
- requests/second,
- transactions/second,
- messages/second,
- jobs/hour,
- GB processed/hour.

Phải phân biệt offered load (tải gửi vào) với achieved throughput (tải thực sự hoàn tất). Hệ thống có thể nhận 5.000 request/giây nhưng chỉ hoàn tất 3.000 request/giây; phần còn lại timeout, bị từ chối hoặc chờ trong queue.

### 3.3. Concurrency và Little's Law

Concurrency là số request/job hiện diện trong hệ thống cùng lúc. Trong trạng thái ổn định, Little's Law:

\[
L = \lambda W
\]

Trong đó:
- \(L\): số công việc trung bình trong hệ thống.
- \(\lambda\): throughput trung bình.
- \(W\): thời gian trung bình ở trong hệ thống.

Ví dụ throughput 400 request/giây, thời gian trung bình 0,2 giây:

\[
L = 400 \times 0.2 = 80
\]

Trung bình có khoảng 80 request đang hiện diện trong ranh giới đo. Đây không phải sizing formula đầy đủ; cần xét phân phối, burst, queue và tài nguyên từng request.

### 3.4. Utilization và saturation

Utilization cho biết tài nguyên đang được sử dụng bao nhiêu; saturation phản ánh mức tranh chấp hoặc công việc phải chờ do thiếu tài nguyên.

Ví dụ:
- CPU 90% liên tục có thể giảm headroom.
- DB connection pool có 95% connection đang bận và wait queue tăng.
- Disk latency tăng khi IOPS đạt giới hạn.
- Network interface chạm throughput cap.
- Consumer lag và oldest message age tăng.
- Thread pool đầy khiến request phải chờ dù CPU thấp.

Không đặt mục tiêu utilization 100%. Cần headroom để hấp thụ burst, failure và scale delay. Mức utilization mục tiêu phụ thuộc workload và SLO.

## 4. Workload model: so sánh phải công bằng

Benchmark không đại diện workload production sẽ dẫn tới quyết định sai.

### 4.1. Mô tả workload

Workload model cần:
- Tỷ lệ read/write và loại thao tác.
- Endpoint/transaction mix.
- Payload size và response size.
- Phân bố key/tenant, hot key và data cardinality.
- Concurrency, arrival rate, think time và session pattern.
- Cache hit/miss ratio.
- Query complexity và data volume.
- Background job, batch và event rate.
- Peak, burst, seasonality và growth.
- Geographic distribution, network RTT và client characteristics.

Ví dụ search-only benchmark không phản ánh checkout nếu checkout cần transaction, row lock, payment call và event publish. Data set nhỏ trong cache nóng cũng không đại diện database production.

### 4.2. Các kiểu load test

| Test | Mục tiêu | Điều cần quan sát |
| --- | --- | --- |
| Baseline/load | Hành vi ở tải dự kiến | p95/p99, throughput, cost |
| Stress | Giới hạn và điểm degradation | Saturation, rejection, failure mode |
| Spike | Tăng tải đột ngột | Autoscale delay, cold cache, queue |
| Soak | Tải kéo dài | Leak, GC, backlog, storage growth |
| Capacity | Throughput tối đa theo SLO | Cost/capacity và bottleneck |
| Skew | Phân bố tenant/key lệch | Hot partition, noisy neighbor |
| Failover | Mất node/AZ/dependency | SLO trong failure mode |
| Regression | So sánh version/cấu hình | Thay đổi latency, error và cost |

### 4.3. Kiểm soát biến số

So sánh hai phương án cần giữ ổn định:
- Cùng workload, input data và thời gian warm-up.
- Cùng vị trí test/region hoặc ghi nhận rõ network difference.
- Cùng SLO và tiêu chí thành công.
- Ghi lại version artifact, config, instance type và autoscaling policy.
- Nhiều lần chạy đủ để nhận biết biến động.
- Phân biệt cold run và warm run.
- Không thay nhiều yếu tố cùng lúc nếu mục tiêu là tìm nguyên nhân.

Một kết quả nhanh hơn nhưng chạy trên cache warm trong khi phương án khác cold start không phải phép so sánh công bằng.

## 5. Đo chi phí theo outcome

Tổng hóa đơn cloud không cho biết một giao dịch hữu ích tốn bao nhiêu. Nên quy đổi cost theo đơn vị nghiệp vụ.

### 5.1. Unit economics

Một số thước đo:
- Cost per request.
- Cost per successful transaction.
- Cost per booking.
- Cost per active tenant.
- Cost per GB ingested/queried.
- Cost per million events.
- Cost per report completed.
- Cost per inference or model prediction.

Công thức cơ bản:

\[
CostPerSuccess =
\frac{\text{Tổng chi phí trong kỳ}}
{\text{Số outcome thành công trong kỳ}}
\]

Ví dụ giả định một tháng:
- Chi phí platform liên quan checkout: 12.000 USD.
- Booking hoàn tất hợp lệ: 600.000.
- Cost per successful booking:

\[
12{,}000 / 600{,}000 = 0.02\text{ USD}
\]

Nếu phương án mới tốn 14.000 USD nhưng tạo 800.000 booking hợp lệ:

\[
14{,}000 / 800{,}000 = 0.0175\text{ USD}
\]

Tổng chi phí tăng nhưng unit cost giảm. Cần xác định chi phí nào được phân bổ vào checkout và so sánh trên cùng phạm vi.

### 5.2. Cost per request có thể gây hiểu nhầm

Nếu một hệ thống rẻ vì từ chối nhiều request hoặc trả kết quả sai, cost/request có thể trông tốt. Nên dùng cost per **successful, valid outcome** và đi kèm SLO về latency, correctness và availability.

Cũng cần tính:
- Retry và duplicate work.
- Failed job và waste.
- Idle capacity để giữ SLO.
- Backup, replication và DR.
- Logs/metrics/traces.
- Egress và cross-region traffic.
- License/managed service charge.
- Công vận hành và incident response.

### 5.3. TCO

\[
TCO = C_{\text{compute}} + C_{\text{storage}} +
C_{\text{database}} + C_{\text{network}} +
C_{\text{managed services}} + C_{\text{observability}} +
C_{\text{security}} + C_{\text{operations}}
\]

TCO nên dùng một khoảng thời gian nhất quán, ví dụ 12 hoặc 36 tháng, và gồm chi phí migration, dual-run, training, support, vendor lock-in risk và decommission.

## 6. Đường cong hiệu năng–chi phí

Khi tăng compute, cache hoặc replica, hiệu năng thường cải thiện tới một điểm rồi lợi ích biên giảm dần. Chi phí có thể tăng gần tuyến tính hoặc theo bậc; một số dịch vụ có tier/quota và phí network riêng.

### 6.1. Marginal gain

Ví dụ giả định:

| Cấu hình | Throughput đạt SLO | Chi phí/tháng | Cost trên 1.000 request hoàn tất |
| --- | ---: | ---: | ---: |
| A: 2 replicas | 1.000 req/s | 1.000 USD | 0,0039 USD |
| B: 4 replicas | 1.850 req/s | 1.650 USD | 0,0029 USD |
| C: 6 replicas | 2.100 req/s | 2.400 USD | 0,0033 USD |
| D: 8 replicas | 2.200 req/s | 3.100 USD | 0,0041 USD |

Các số liệu minh họa, cần workload và kỳ đo nhất quán. Cấu hình C/D tăng throughput ít hơn chi phí, nên cost/unit xấu đi so với B. Tuy nhiên nếu business cần capacity 2.000 req/s cộng headroom cho failure, B có thể chưa đủ; cần xét cả peak và failure capacity.

### 6.2. Pareto frontier

Một phương án Pareto-dominated nếu có phương án khác:
- Không đắt hơn và nhanh hơn hoặc
- Không chậm hơn và rẻ hơn,
với ít nhất một chiều tốt hơn.

Pareto frontier là tập phương án mà không thể cải thiện một mục tiêu mà không làm xấu mục tiêu khác trong tập phương án đã đo.

~~~mermaid
quadrantChart
    title So sánh cost và latency (minh họa)
    x-axis Low cost --> High cost
    y-axis Low latency --> High latency
    quadrant-1 Cần xem xét hiệu năng
    quadrant-2 Có thể kém hiệu quả
    quadrant-3 Hiệu quả tương đối
    quadrant-4 Chi phí cao, hiệu năng tốt
    A: [0.25, 0.75]
    B: [0.48, 0.35]
    C: [0.72, 0.22]
    D: [0.90, 0.18]
~~~

Với biểu đồ trên, trục latency được ghi từ thấp tới cao theo cách minh họa; khi dựng dashboard thực tế phải đảm bảo hướng trục rõ và dùng số đo thật. Không dùng Pareto frontier thay cho constraint: phương án rẻ nhưng vi phạm security hoặc data correctness không phải lựa chọn hợp lệ.

## 7. Tìm mức capacity tối ưu, không chỉ cấu hình rẻ nhất

Capacity cần đáp ứng:
- Peak workload.
- Growth forecast.
- Failure headroom khi mất node/AZ.
- Autoscaling reaction time.
- Warm-up/cold start.
- Batch window và maintenance.
- Quota giới hạn từ nhà cung cấp.
- SLO latency/availability ở trạng thái bình thường và degraded mode.

Một mô hình sizing thô:

\[
N_{\text{replicas}} \geq
\left\lceil \frac{\lambda_{\text{peak}}}
{\mu_{\text{replica}} \times U_{\text{target}}} \right\rceil
\]

Trong đó:
- \(\lambda_{\text{peak}}\): offered workload đỉnh.
- \(\mu_{\text{replica}}\): throughput mỗi replica đã benchmark.
- \(U_{\text{target}}\): mức sử dụng mục tiêu nhỏ hơn 1.

Ví dụ peak 1.600 req/s, một replica đạt 250 req/s ở ngưỡng SLO, target utilization 0,7:

\[
N \geq \left\lceil \frac{1600}{250 \times 0.7} \right\rceil
= 10
\]

Nếu cần chịu mất một AZ chứa 3 replica, tổng số replica hoặc phân bố capacity phải đủ để phần còn lại vẫn đạt SLO. Công thức chỉ là phép ước lượng; request cost, skew, coordination, dependency capacity và autoscaling delay có thể thay đổi kết quả.

Không sizing dựa trên CPU trung bình. Benchmark theo throughput đạt SLO và kiểm chứng khi failure.

## 8. Đánh đổi compute: scale up, scale out và managed services

| Phương án | Lợi ích hiệu năng | Chi phí/đánh đổi |
| --- | --- | --- |
| Larger instance (scale up) | Tăng CPU/RAM/network trên node, đơn giản hóa một số workload | Giá mỗi node cao, trần phần cứng, downtime khi resize tùy dịch vụ |
| More replicas (scale out) | Tăng song song cho workload stateless | Coordination, load balancing, connection và memory tổng tăng |
| Serverless | Scale theo event/request, giảm quản trị server | Cold start, concurrency/quota, cost theo invocation/time, execution limit |
| Managed container | Tự do runtime hơn và dễ chuẩn hóa | Cluster/node/patching và capacity vẫn cần quản trị |
| Dedicated capacity | Hiệu năng ổn định, cô lập noisy neighbor | Chi phí idle và capacity planning |
| Spot/preemptible | Giảm compute cost cho workload chịu gián đoạn | Có thể bị thu hồi; checkpoint/retry cần thiết |

Chọn theo bottleneck. Scale API không giải quyết database write contention. Scale worker không có ích nếu sink bị throttle. Managed service giảm toil nhưng không tự bảo đảm performance hoặc cost tối ưu.

## 9. Đánh đổi storage và database

### 9.1. Storage tier

| Loại lưu trữ | Đặc điểm | Workload phù hợp | Đánh đổi |
| --- | --- | --- | --- |
| High-performance block | Latency/IOPS cao | Transactional DB, latency-sensitive state | Giá/GB và IOPS cao |
| General-purpose block | Cân bằng cost và performance | Application volume, moderate DB | Cần benchmark theo IOPS/throughput |
| Object storage hot | Durable, scale lớn, access thường xuyên | Active files, data lake, backup gần | Request/egress và latency khác block |
| Object storage cool/archive | Storage cost thấp hơn | Backup/lịch sử ít truy cập | Retrieval latency và fee |
| In-memory cache | Latency thấp | Hot read, session, computed result | Memory đắt, invalidation và stale-data risk |

Không so giá/GB đơn thuần. Phải tính IOPS, throughput, request count, retrieval, egress, replication và recovery.

### 9.2. Database choices

- Relational database: transaction, constraints và query phong phú; cần sizing, index, connection và write scaling.
- Distributed SQL: scale và availability theo thiết kế nhưng có coordination/latency/operational complexity.
- Key-value/document store: access pattern rõ, horizontal scale; query flexibility và consistency model cần hiểu.
- Columnar warehouse: analytics scan/aggregation hiệu quả; không phải transactional serving database.
- Search engine: full-text/filtering; index freshness và storage duplication.
- Cache: giảm read latency; không thay source of truth nếu chưa có semantics phù hợp.

### 9.3. Read replica và cache

Read replica giúp tách read load nhưng có replication lag. Cache giảm latency và DB cost nhưng tạo freshness/invalidation concerns. Cần đo:
- Cache hit ratio theo workload/key/tenant.
- Origin request reduction.
- Data staleness.
- Cache memory/replication cost.
- Invalidation traffic và stampede.
- Read replica lag và failover behavior.

Một cache hit ratio cao vẫn có thể tệ nếu hit chủ yếu là request rẻ còn query đắt vẫn miss. Theo dõi cost và latency theo endpoint/business outcome.

## 10. Network và vị trí dữ liệu

Network thường bị bỏ qua khi tối ưu application latency. Các yếu tố:
- Client-to-edge RTT và geographic distribution.
- Cross-AZ/cross-region traffic.
- Service-to-service hop count.
- TLS handshake và connection reuse.
- Payload size/compression.
- NAT gateway, load balancer và egress cost.
- Private connectivity và partner link.

Một dependency ở region khác có thể tăng latency và network cost. Đưa service gần database giảm RTT nhưng có thể làm phức tạp multi-region availability và data consistency.

Biện pháp:
- Co-locate service/data theo access pattern khi phù hợp.
- Dùng CDN/edge caching cho nội dung public hoặc cacheable.
- Connection pooling/keep-alive.
- Giảm payload và serialization overhead.
- Batch request khi semantics cho phép.
- Hạn chế cross-region chatter.
- Đo network egress và latency riêng theo hop.

Không chuyển dữ liệu nhạy cảm sang region khác chỉ để giảm latency nếu data residency hoặc policy không cho phép.

## 11. Autoscaling và cost-performance tradeoff

Autoscaling phản ứng với demand nhưng có độ trễ. Nếu tải tăng nhanh hơn scale-up, người dùng vẫn gặp latency/error trong giai đoạn provision/warm-up.

### 11.1. Chọn scaling signal

| Signal | Khi hữu ích | Hạn chế |
| --- | --- | --- |
| CPU | Compute-bound workload | Không phản ánh I/O wait hoặc queue age |
| Memory | Memory pressure/cache | Thường scale-down khó do state/cache |
| Request rate | API stateless | Request cost có thể khác nhau |
| In-flight concurrency | Worker/API có giới hạn concurrency | Cần tune threshold |
| Queue age/backlog | Async worker | Sink có thể là bottleneck |
| Custom business metric | Workload có cost khác nhau | Cần tính toán và vận hành metric |

### 11.2. Scale policy

Cần min/max replicas, stabilization window, scale-up/down step, warm capacity, cooldown, quota và dependency protection. Scale-down quá nhanh có thể làm latency tăng lại hoặc gián đoạn job. Scale-up quá nhanh có thể tạo connection storm vào database.

### 11.3. Scheduled và predictive scaling

Với workload có seasonality rõ (campaign, payroll, batch window), scheduled/predictive capacity có thể rẻ và ổn định hơn chờ autoscaler phản ứng. Tuy nhiên forecast sai gây idle cost; cần so sánh chi phí pre-warm với error budget và business impact khi thiếu capacity.

## 12. Managed services hay tự vận hành?

Managed service có thể giảm toil, patching và control-plane work; đổi lại cost model, quota, observability, portability và control có thể khác.

| Tiêu chí | Managed service | Self-managed |
| --- | --- | --- |
| Operations | Provider quản lý một phần hạ tầng | Đội tự chịu trách nhiệm nhiều hơn |
| Scaling | API/setting có sẵn nhưng có quota | Linh hoạt hơn nếu đủ năng lực |
| Performance tuning | Một số giới hạn/provider abstraction | Kiểm soát sâu hơn |
| Cost | Giá theo usage/tier/feature | Compute/storage cộng nhân lực vận hành |
| Reliability | HA/backup có thể tích hợp nhưng phải cấu hình | Tự thiết kế và kiểm chứng |
| Portability | Có thể phụ thuộc API/feature riêng | Mã nguồn/config có thể portable hơn, nhưng operations phức tạp |
| Security | Shared responsibility | Nhiều trách nhiệm runtime/platform hơn |

So sánh phải tính **toàn bộ operations cost**, không chỉ invoice. Một dịch vụ managed đắt hơn 20% nhưng giảm đáng kể on-call, patching và downtime có thể có TCO thấp hơn.

Ngược lại, managed service có minimum tier/capacity lớn hơn nhu cầu hoặc phí request/egress cao có thể kém kinh tế. Hãy benchmark và mô hình hóa growth.

## 13. Độ tin cậy và chi phí dự phòng

Redundancy, backup, replication và DR làm tăng cost nhưng giảm expected business loss và recovery risk.

Có thể so sánh:

\[
ExpectedAnnualLoss = P(\text{incident}) \times Impact(\text{incident})
\]

\[
EconomicValueOfControl =
ExpectedLoss_{\text{before}} -
ExpectedLoss_{\text{after}} -
ControlCost
\]

Đây là mô hình định hướng, xác suất và impact thường không chắc chắn. Với rủi ro pháp lý, an toàn hoặc nghĩa vụ bắt buộc, không thể chỉ quyết định dựa trên phép tính tài chính.

Ví dụ multi-AZ database có thể tăng chi phí compute/storage/network nhưng giảm thời gian gián đoạn. Active-active multi-region có thể tăng resilience, nhưng cũng làm tăng data replication, conflict handling, testing, operational complexity và incident risk.

Nên xác định:
- RTO/RPO theo hành trình và data.
- Failure mode cần chịu được.
- Capacity trong trạng thái mất AZ/region.
- Cost của standby và replication.
- Test frequency và restore evidence.
- Điều kiện failover/failback.

## 14. Security và performance không nên tối ưu tách rời

Một cấu hình có thể nhanh hơn nếu bỏ TLS, logging hoặc authorization, nhưng đó không phải cải thiện hợp lệ nếu vi phạm policy hoặc tăng rủi ro không chấp nhận được.

So sánh phải giữ security baseline tương đương:
- TLS/mTLS và encryption.
- Authentication/authorization.
- Network segmentation.
- Audit và telemetry.
- Vulnerability scanning và artifact verification.
- Data retention/residency.

Một số kiểm soát tạo overhead; hãy đo overhead và tìm cách tối ưu implementation (connection reuse, async logging có durability, cache policy evaluation phù hợp) thay vì xóa kiểm soát.

Không coi security exception là cách tối ưu performance nếu có phương án kiến trúc an toàn hơn.

## 15. FinOps: gắn chi phí với kiến trúc và sản phẩm

FinOps kết nối engineering, finance và business để đưa dữ liệu chi phí vào quyết định thiết kế.

### 15.1. Phân bổ chi phí

Gắn cost với:
- Service/team/owner.
- Environment.
- Tenant hoặc product line khi có thể.
- Workload type: API, batch, analytics, ML.
- Cost center/project.
- Shared platform allocation rule.

Tagging không đầy đủ sẽ làm unit cost mất chính xác. Shared cost như network, security monitoring, CI runners và control plane cần quy tắc phân bổ minh bạch.

### 15.2. Cost drivers cần xem

- Compute hours, CPU/RAM và accelerator.
- Storage GB-month, IOPS, request và retrieval.
- Database capacity, replicas, backup, snapshot.
- Broker partition, throughput và retention.
- NAT, load balancer, egress, cross-region/AZ traffic.
- Logs, metrics, traces, retention và ingestion volume.
- Managed service tier, support/license.
- Idle resource và orphan resource.
- Build/test/DR/temporary environment.

### 15.3. Unit cost và growth forecast

Không chỉ đo cost tháng hiện tại. Dự báo theo:
- Active users/tenant.
- Requests và transactions.
- Data volume và retention.
- Peak-to-average ratio.
- Replica/partition growth.
- Cross-region traffic.
- Security/observability coverage.
- DR footprint.

Mô hình chi phí cần có base, expected và peak scenarios; ghi assumptions và sensitivity. Giá cloud thay đổi theo region, commitment, volume tier và hợp đồng; dùng price book/invoice hiện hành của tổ chức khi ra quyết định.

## 16. Quy trình ra quyết định so sánh phương án

Một quy trình thực tế:

1. Xác định outcome nghiệp vụ và quality constraints.
2. Xác định SLI/SLO, workload profile và failure scenario.
3. Lập danh sách phương án kiến trúc khả thi.
4. Loại phương án vi phạm security, data residency, availability hoặc functional constraints.
5. Thiết kế benchmark đại diện và cost model.
6. Đo latency/throughput/quality/capacity/cost trên cùng workload.
7. Tính unit economics, headroom, TCO và sensitivity.
8. Phân tích Pareto và marginal gain.
9. Ghi assumptions, uncertainty, residual risk và operational burden.
10. Chọn phương án, đặt trigger review và theo dõi sau production.

### 16.1. Scorecard tham khảo

| Tiêu chí | Trọng số ví dụ | Phương án A | Phương án B | Phương án C |
| --- | ---: | ---: | ---: | ---: |
| Latency/SLO | 25% |  |  |  |
| Throughput/capacity | 15% |  |  |  |
| Cost per success | 20% |  |  |  |
| Availability/recovery | 15% |  |  |  |
| Security/compliance | Gate bắt buộc | Pass/Fail | Pass/Fail | Pass/Fail |
| Operational toil | 10% |  |  |  |
| Scalability/growth | 10% |  |  |  |
| Portability/lock-in | 5% |  |  |  |

Trọng số chỉ minh họa. Không dùng weighted score để bù cho một điều kiện bắt buộc bị fail. Security/compliance, correctness và minimum SLO thường là hard constraints; chỉ xếp hạng các phương án đã qua điều kiện bắt buộc.

### 16.2. Sensitivity analysis

Thử thay đổi giả định:
- Traffic tăng 2x/3x/5x.
- Cache hit giảm.
- Một AZ không khả dụng.
- Egress tăng do data transfer.
- Managed service chuyển tier.
- Log retention tăng do yêu cầu compliance.
- Discount/commitment hết hạn.
- Dependency có latency hoặc error tăng.

Một phương án chỉ rẻ trong một giả định rất hẹp có thể không bền vững.

## 17. Tình huống thực tế: chọn cấu hình cho Booking API

### 17.1. Bối cảnh và mục tiêu

Một nền tảng đặt chỗ có Booking API chạy trên cloud. Tải bình thường 600 request/giây, peak 1.800 request/giây; 70% read và 30% write. Mục tiêu giả định:
- p95 dưới 250 ms cho API trong điều kiện bình thường.
- p95 dưới 400 ms tại peak.
- Error rate dưới 0,5% cho request hợp lệ.
- Không mất booking đã commit.
- Có thể chịu mất một AZ theo recovery objective.
- Cost per completed booking phải giảm hoặc giữ ổn định khi scale.

Các con số là giả định của bài tập, không phải SLO khuyến nghị cho mọi sản phẩm.

### 17.2. Ba phương án

- **A: Small instances, scale out mạnh:** nhiều API replicas nhỏ, database primary và cache cơ bản.
- **B: Balanced instances + read replica/cache:** ít replica hơn, compute vừa phải, tách read workload, cache hot read.
- **C: Large dedicated instances + high redundancy:** compute/database lớn, capacity dự phòng cao, ít phụ thuộc autoscaling trong peak.

### 17.3. Kết quả benchmark giả định

| Chỉ số ở peak | A | B | C |
| --- | ---: | ---: | ---: |
| Throughput đạt SLO | 1.500 req/s | 2.000 req/s | 2.200 req/s |
| p95 latency | 390 ms | 310 ms | 260 ms |
| Error rate | 0,8% | 0,3% | 0,2% |
| Monthly cost | 8.000 USD | 9.200 USD | 13.500 USD |
| Ops complexity | Cao do nhiều replica | Trung bình | Trung bình |
| AZ failure headroom | Thấp | Đạt sau sizing | Cao |

Kết quả minh họa. Phương án A rẻ nhưng không đạt peak throughput/error target; C có hiệu năng tốt nhất nhưng chi phí cao; B có thể là lựa chọn cân bằng nếu SLO peak được xác nhận và failure headroom đã kiểm thử.

Không thể chọn B chỉ từ bảng. Cần xác minh data correctness, write contention, replica lag, cache staleness, network egress và cost per successful booking.

### 17.4. Cost per successful booking

Giả sử monthly cost và booking hoàn tất:
- A: 8.000 USD / 350.000 booking = 0,0229 USD/booking.
- B: 9.200 USD / 500.000 booking = 0,0184 USD/booking.
- C: 13.500 USD / 650.000 booking = 0,0208 USD/booking.

B có unit cost thấp hơn trong giả định này dù monthly cost cao hơn A. A từ chối nhiều request ở peak và throughput không đủ; C đạt volume cao nhưng capacity đắt. Nếu business cần hơn 650.000 booking/tháng hoặc phải chịu failure mode nặng hơn, kết quả có thể đổi.

## 18. Tình huống thứ hai: chọn xử lý batch hay streaming

Một data platform nhận 100 triệu event/ngày. Consumer muốn dashboard cập nhật dưới 5 phút; một nhóm fraud detection cần alert dưới 5 giây. So sánh:
- Batch hourly: chi phí compute theo job thấp nhưng không đạt alert SLA.
- Micro-batch 1–5 phút: có thể đáp ứng dashboard, chi phí vừa phải.
- Continuous streaming: phù hợp alert nhanh nhưng có broker, always-on processing, state/checkpoint, retention và on-call cost.

Kiến trúc kết hợp có thể:
- Streaming cho fraud event và operational alert.
- Micro-batch cho dashboard.
- Batch reconciliation cuối ngày cho tài chính.

Chọn đúng theo freshness objective của từng consumer sẽ tránh trả chi phí streaming liên tục cho tất cả dữ liệu. Cần đo throughput, event skew, late data, replay, broker cost và operational burden.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chọn phương án có p50 thấp nhất | Tail latency có thể tệ | Đo p95/p99 và journey SLO |
| Chỉ so monthly bill | Không thấy cost per outcome | Tính cost per successful transaction |
| Benchmark workload không đại diện | Quyết định không phản ánh production | Mô hình endpoint, key, payload, cache và peak |
| Chỉ đo average | Bỏ sót outlier và queueing | Histogram, percentile và trace |
| So cấu hình không cùng điều kiện | Kết quả thiếu công bằng | Cố định data, warm-up, region, version và load |
| Scale đến 100% utilization | Không có headroom | Chọn target utilization và failure capacity |
| Tăng API replicas để sửa DB bottleneck | Tăng connection/DB pressure | Tìm bottleneck theo từng tầng |
| Cache mọi thứ | Stale data, invalidation và memory cost | Cache theo freshness và consistency |
| Chọn serverless chỉ vì không có server | Có thể cold start/quota/cost cao | Benchmark latency, concurrency và unit cost |
| Dùng managed service mà không xem quota | Throttle hoặc giới hạn khi peak | Quota review và load test |
| Bỏ qua egress/cross-region fee | Cost vượt dự báo | Network flow/cost analysis |
| Đánh đổi security để giảm latency | Tăng risk không chấp nhận được | Optimize implementation, giữ security baseline |
| Không tính DR và backup | Cấu hình rẻ nhưng recovery kém | Tính TCO và failure scenario |
| Weighted score bù cho hard constraint fail | Chọn phương án không đủ điều kiện | Dùng hard gate trước scoring |
| Không kiểm tra sau production | Benchmark không phản ánh live traffic | Continuous SLI/cost monitoring |
| Không review assumptions | Growth/price/workload đổi nhưng kiến trúc cũ | Trigger review và sensitivity analysis |

## 20. Bài tập thực hành

Một nền tảng đặt chỗ đang chọn kiến trúc cho API và data processing. Tải 800 request/giây trung bình, peak 2.400 request/giây; 65% read, 35% write; event pipeline nhận 3.000 event/giây. Product yêu cầu p95 checkout dưới 350 ms, search dưới 250 ms, dashboard mới trong 5 phút và fraud alert trong 5 giây. Finance yêu cầu cost per successful booking không vượt 0,025 USD.

Hãy thực hiện:

1. Chuyển yêu cầu thành SLI/SLO, định nghĩa mẫu số và điều kiện thành công cho từng hành trình.
2. Lập workload model với endpoint mix, payload, tenant skew, cache hit, concurrency và peak.
3. Đề xuất ít nhất ba phương án compute/database/cache/streaming.
4. Thiết kế benchmark/load/stress/spike/soak/failover test công bằng.
5. Tạo bảng latency p50/p95/p99, throughput, error rate, saturation và capacity headroom.
6. Xây cost model gồm compute, database, storage, broker, network, observability, security và operations.
7. Tính cost per successful booking và cost per million events; nêu assumption.
8. Vẽ cost-performance curve, loại phương án Pareto-dominated và xác định điểm diminishing returns.
9. Phân tích failure case mất một AZ, cache cold, database lag và provider quota.
10. Đặt hard constraints về security, data correctness, availability và compliance trước khi chấm điểm.
11. Viết ADR chọn phương án, nêu tradeoff, residual risk, owner và trigger review.

**Tiêu chí tự đánh giá:** phương án tốt đạt SLO bằng workload đại diện, cost được quy đổi theo outcome thành công, có headroom/failure capacity, giữ security/data correctness và giải thích rõ vì sao phần chi phí tăng thêm tạo ra giá trị cần thiết.

## 21. Checklist trước khi chốt hiệu năng và ngân sách kiến trúc

- [ ] Business outcome và quality attributes được mô tả rõ.
- [ ] SLI/SLO có mẫu số, kỳ đo, scope và owner.
- [ ] Workload model gồm mix, payload, concurrency, skew, peak và growth.
- [ ] Benchmark dùng cùng điều kiện, data set, warm-up và artifact/config có version.
- [ ] Đo p50/p95/p99, throughput, offered load, error và saturation.
- [ ] Xác định bottleneck theo compute, database, network, queue và dependency.
- [ ] Có load/stress/spike/soak/skew/failover test phù hợp.
- [ ] Cost model gồm compute, storage, database, network, managed service và operations.
- [ ] Tính cost per successful outcome, không chỉ cost/request hoặc invoice.
- [ ] Phân tích utilization, headroom, autoscaling delay và failure capacity.
- [ ] So sánh scale up/out, serverless, managed/self-managed theo TCO.
- [ ] Cache/storage/database có freshness, consistency và retrieval cost rõ.
- [ ] Egress/cross-region, observability, security và DR được tính.
- [ ] Hard constraints về security, correctness, compliance và minimum SLO được đáp ứng.
- [ ] Có Pareto/marginal gain và sensitivity analysis.
- [ ] Giả định, uncertainty, residual risk và operational burden được ghi.
- [ ] Có kế hoạch theo dõi performance/cost sau production.
- [ ] ADR có decision, rationale, owner và điều kiện xem xét lại.

## Ghi nhớ

So sánh hiệu năng với chi phí phải bắt đầu từ **mục tiêu chất lượng của nghiệp vụ**. Đo latency theo percentile, throughput đạt SLO, saturation, correctness và availability trên workload đại diện; quy đổi chi phí theo outcome thành công; rồi so sánh các phương án theo TCO, headroom, risk và lợi ích biên.

Không chọn cấu hình chỉ vì nhanh nhất hoặc rẻ nhất. Chọn phương án đáp ứng các hard constraints, nằm trên Pareto frontier phù hợp và có mức chi phí tăng thêm được biện minh bằng giá trị nghiệp vụ. Sau khi triển khai, tiếp tục đo SLI/SLO và unit cost để xác nhận giả định kiến trúc vẫn đúng khi tải, giá và sản phẩm thay đổi.
