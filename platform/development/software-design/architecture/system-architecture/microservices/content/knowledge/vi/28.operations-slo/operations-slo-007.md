# Quản lý năng lực và dự báo nhu cầu tài nguyên trong Microservices

## Mục tiêu học tập

Sau bài này, người học có thể giải thích **capacity planning** và **demand forecasting** trong hệ thống microservices; chuyển yêu cầu nghiệp vụ và SLO thành nhu cầu CPU, RAM, I/O, kết nối, số replica và năng lực xử lý hàng đợi; nhận diện điểm nghẽn ở service và dependency; lập dự báo theo giờ cao điểm, tăng trưởng, sự kiện bất thường và kịch bản lỗi; thiết kế headroom cùng cơ chế autoscaling phù hợp; thực hiện load test, quan sát sai lệch dự báo và điều chỉnh ngân sách tài nguyên.

Ý tưởng trung tâm là: **năng lực hệ thống phải được chứng minh bằng thông lượng thành công ở mức SLO chấp nhận được, thay vì chỉ bằng số pod hoặc tỷ lệ CPU còn trống**. Quản lý năng lực còn bao gồm khả năng phục hồi khi một node, một zone hay một dependency bị giảm năng lực.

## 1. Capacity planning là gì?

**Capacity (năng lực)** là khối lượng công việc hệ thống có thể xử lý trong những ràng buộc cụ thể: độ trễ, tỷ lệ lỗi, tính đúng đắn, chi phí và mức dự phòng. Capacity planning là quá trình đo hiện trạng, dự báo tải, xác định giới hạn và chuẩn bị tài nguyên đủ để đáp ứng tải đó.

**Demand (nhu cầu)** là lượng công việc đến hệ thống: request, giao dịch, event, job, số người dùng đồng thời, byte cần lưu trữ hoặc tác vụ tính toán. Demand forecasting là ước lượng nhu cầu theo thời gian và theo kịch bản, không chỉ dựa vào một giá trị trung bình.

Ví dụ, một website bán hàng có những dòng tải rất khác nhau:

~~~text
                       Người dùng
                           |
                      API Gateway
                           |
           +---------------+------------------+
           |               |                  |
           v               v                  v
     Catalog API       Order API        Account API
    đọc sản phẩm      tạo đơn hàng     xác thực / hồ sơ
           |               |
           v               +----------> Payment Provider
      Search / DB           |
                           v
                     Order Database
                           |
                           v
                        Message Broker
                        /            \
                       v              v
                Inventory Worker   Email Worker
~~~

Một đợt flash sale làm Catalog tăng gấp mười lần, nhưng lượng đặt hàng có thể chỉ tăng gấp ba. Nếu nhân bản mọi service theo cùng một hệ số, hệ thống tốn tài nguyên mà chưa chắc giải quyết nghẽn. Microservices cho phép hoạch định **mỗi dịch vụ theo đặc tính công việc riêng**, đồng thời phải theo dõi sức chịu tải của những dependency mà nhiều service cùng sử dụng.

### Ba câu hỏi bắt buộc

1. **Nhu cầu sẽ đến khi nào và theo hình dạng nào?** Tăng đều theo tháng, tăng theo giờ trong ngày, burst kéo dài vài giây, chạy batch ban đêm hay khuyến mãi có thời điểm định trước?
2. **Năng lực hiện tại và giới hạn thật ở đâu?** CPU của pod, connection pool, database IOPS, lock, Kafka partition, Redis memory, network, rate limit của hệ thống bên ngoài?
3. **Khi một thành phần hỏng, phần còn lại có đủ năng lực không?** Một zone bị mất, rolling deploy đang diễn ra, cache cold hoặc một service cần retry hàng loạt có thể làm thay đổi yêu cầu capacity.

Một kế hoạch chỉ có con số “10 replica” mà không có SLO, đặc tính tải và kiểm thử chứng minh con số đó là chưa đầy đủ.

## 2. Phân biệt capacity, utilization, saturation và demand

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Demand | Công việc được gửi tới | 1.200 HTTP request/giây |
| Throughput | Công việc hoàn thành thực sự | 1.000 request thành công/giây |
| Capacity | Thông lượng bền vững trong các ràng buộc SLO | 1.100 request/giây với p95 dưới 200 ms |
| Utilization | Tỷ lệ sử dụng tài nguyên | CPU trung bình 68% trên request được cấp |
| Saturation | Dấu hiệu hàng chờ và tài nguyên bắt đầu nghẽn | DB pool wait tăng, thread queue dài |
| Headroom | Phần năng lực chưa dùng để đón đột biến/lỗi | Khả năng xử lý cao hơn tải dự báo 25% |
| Backlog | Công việc còn chờ | 40.000 message trong queue |
| Latency | Thời gian hoàn thành | p95 HTTP = 180 ms |
| Error rate | Tỷ lệ yêu cầu không hoàn thành đúng | 0,2% request lỗi |

**Utilization thấp không chứng minh hệ thống còn nhiều capacity.** Một Payment Service có CPU 15% nhưng đang chờ nhà cung cấp thanh toán với giới hạn 100 giao dịch/giây có thể đã đạt ngưỡng nghiệp vụ. Một Order Service với CPU 40% nhưng database connection pool bị đợi hàng trăm mili giây cũng có thể mất SLO.

Ngược lại, CPU trung bình 85% không tự động là lỗi. Nếu workload CPU-bound, ứng dụng ổn định, độ trễ và lỗi nằm trong SLO, mức sử dụng cao có thể chấp nhận; cần xét khả năng phản ứng trước burst và tác động khi mất replica.

### Capacity luôn đi kèm một điều kiện đo

Câu “một pod xử lý 300 RPS” thiếu thông tin nếu không nêu request mix, payload, cache hit, số kết nối DB, tỉ lệ lỗi, phiên bản ứng dụng, máy chủ và mục tiêu độ trễ. Một kết quả đo cần có dạng:

> Với workload W, bản phát hành V, cấu hình C và những dependency D, một replica xử lý bền vững X request/giây trong T phút, với p95 dưới giới hạn L, error rate dưới ngưỡng E, không tích lũy backlog.

Chỉ khi điều kiện thử gần với production, số liệu mới có ích cho capacity planning.

## 3. Bắt đầu từ SLO và hành trình nghiệp vụ

**Service Level Indicator (SLI)** là số đo phản ánh trải nghiệm hoặc kết quả dịch vụ, chẳng hạn tỷ lệ HTTP request thành công, p95/p99 latency, số đơn tạo chính xác hay thời gian hoàn thành một batch.

**Service Level Objective (SLO)** là ngưỡng mong muốn cho SLI trong cửa sổ thời gian. Ví dụ:
- 99,9% request đọc Catalog hợp lệ được đáp ứng thành công trong cửa sổ 30 ngày.
- p95 truy vấn sản phẩm trong giờ cao điểm dưới 200 ms theo định nghĩa đo thống nhất.
- 99% sự kiện thanh toán đủ điều kiện được xử lý trong vòng 60 giây.
- Báo cáo đối soát của ngày D hoàn tất trước 05:00 ngày D+1.

Các ví dụ là mục tiêu minh họa; từng sản phẩm cần chốt mục tiêu thật theo kỳ vọng nghiệp vụ.

Capacity planning cần bảo vệ **SLO của hành trình quan trọng**, không chỉ SLO riêng từng service. Nếu Checkout phải qua Inventory, Payment và Order, việc Order còn rất nhiều CPU nhưng Payment quá tải vẫn khiến khách hàng không hoàn tất thanh toán.

~~~text
Checkout SLO
    |
    +--> Gateway latency
    +--> Order API latency
    +--> Inventory reservation latency
    +--> Payment latency / quota
    +--> DB commit / consistency
~~~

Tùy nghiệp vụ, một yêu cầu có thể thất bại do bất kỳ thành phần bắt buộc nào. Do đó, cần ngân sách latency cho từng đoạn đường, timeout theo ngân sách toàn tuyến và năng lực dự phòng cho các dependency chính.

**Error budget** là mức không đạt mục tiêu được SLO cho phép trong một cửa sổ. Nó giúp đánh giá rủi ro vận hành và ưu tiên độ tin cậy, nhưng không phải lý do để cố tình để hệ thống sát ngưỡng nghẽn. Capacity thiếu thường dẫn tới lỗi đột biến, retry storm và tỷ lệ gián đoạn không tuyến tính.

## 4. Đo tải nền trước khi dự báo

Một dự báo tốt bắt đầu từ telemetry hiện có. Thu thập theo thời gian, phiên bản triển khai, tenant, vùng và loại endpoint hoặc loại công việc; tránh chỉ nhìn tổng traffic.

**Đối với HTTP/API:**
- Request rate theo route/nhóm route, method và mã kết quả.
- p50, p95, p99 latency; tỷ lệ timeout và HTTP 429/5xx.
- In-flight requests, queue trong executor, số thread bận.
- Request/response size, loại payload, tỷ lệ cache hit/miss.
- CPU sử dụng, CPU throttling, memory working set, heap và GC pause.
- Connection pool active/idle/pending và độ trễ truy vấn DB.
- Tỷ lệ retry và số lời gọi tới downstream trên mỗi giao dịch nghiệp vụ.

**Đối với worker, broker và job:**
- Số message/s đến, xử lý thành công, retry và dead-letter.
- Consumer lag, tuổi message lâu nhất, queue depth.
- Thời gian xử lý một message và concurrency an toàn.
- Số partition, consumer đang hoạt động và khả năng rebalance.
- Thời gian chạy job, tỷ lệ job thành công, lịch bị bỏ lỡ và khối lượng theo từng kỳ.

**Đối với storage và dependency:**
- Query/transaction rate, DB CPU/I/O, lock waits, WAL và replication lag.
- Tổng số kết nối từ mọi pod, số kết nối đang xử lý thực.
- Redis hit ratio, memory, eviction và network.
- Dung lượng dữ liệu, tăng trưởng index, backup size và tốc độ restore.
- Giới hạn API bên ngoài: request/giây, concurrency, quota ngày và rate limit.

Thông tin tải cần bao phủ ngày thường, cuối tuần, cuối tháng, kỳ kế toán, chiến dịch, giờ cao điểm và sự cố đã xảy ra. Bình quân ngày có thể rất thấp trong khi đỉnh năm phút gây outage.

### Chọn cửa sổ thời gian có ý nghĩa

Ví dụ tổng traffic trong ngày là 8,64 triệu request:

~~~text
Daily average = 8.640.000 / 86.400 = 100 RPS
~~~

Nhưng có thể lúc 20:00–20:15 tải đạt 1.200 RPS. Nếu thiết kế bằng 100 RPS trung bình, hệ thống thiếu năng lực hơn mười lần ở thời điểm quan trọng. Cần xem cả:
- Đỉnh trong cửa sổ ngắn, ví dụ 1 phút/5 phút, để đánh giá burst.
- Đỉnh duy trì 15–60 phút, để thiết kế năng lực bền vững.
- Phân phối request theo các endpoint nặng và nhẹ.
- Đỉnh của các service có xảy ra đồng thời hay không.
- Những giờ đầu của batch sau khi scheduler bị gián đoạn.

Đừng dùng p99 của các mẫu có quá ít quan sát để suy diễn chính xác; xem số mẫu, cửa sổ và cách histogram/metric được tổng hợp.

## 5. Chuyển tải nghiệp vụ thành tải kỹ thuật

Một giao dịch người dùng không tương đương một request nội bộ.

Giả sử một lượt checkout bình thường tạo:
- 1 request tới Gateway.
- 1 request tới Order API.
- 2 lời gọi đồng bộ tới Inventory/Pricing.
- 1 lời gọi tới Payment.
- 1 lần ghi transaction DB và 3 event cho các consumer.

Nếu đạt 200 checkout/giây, workload downstream có thể là hàng trăm đến hàng nghìn thao tác/giây, chưa tính cache miss, retry, dead-letter hoặc tác vụ bổ sung.

Dùng **fan-out factor** để mô tả số việc phát sinh bởi một giao dịch:

~~~text
External checkout rate       = 200 transactions/s
Calls to inventory / checkout = 1
Inventory request demand     = 200 requests/s
Events per checkout          = 3
Event production             = 600 events/s
~~~

Nếu 5% transaction gặp timeout rồi có một retry, tải có thể tăng hơn so với đầu vào. Không nhân một hệ số retry chung cho mọi service vì chính sách và số lần thử khác nhau; đo attempt rate tại đúng điểm.

### Little's Law và số tác vụ đồng thời

Trong một hệ thống tương đối ổn định, định luật Little:

~~~text
L = λ × W

L = số công việc trung bình đồng thời trong hệ
λ = throughput đến / rời trung bình trong cùng trạng thái ổn định
W = thời gian công việc ở trong hệ
~~~

Ví dụ, API nhận 500 request/giây, mỗi request mất trung bình 0,2 giây; số request in-flight trung bình khoảng 100. Nếu dependency chậm làm thời gian tăng lên 2 giây, số công việc đồng thời có thể lên khoảng 1.000 nếu đầu vào tiếp tục, kéo theo áp lực lên thread, pool và bộ nhớ.

Công thức giúp liên kết rate với concurrency. Nó **không** nói rằng tăng pool lên 1.000 sẽ giải quyết nghẽn: nếu DB chỉ xử lý được 300 transaction/giây thì số request chờ chỉ tăng lên.

## 6. Tìm điểm nghẽn trước khi quyết định thêm replica

Một đường xử lý chỉ có thể tăng thông lượng đến mức các tài nguyên bắt buộc cho phép.

~~~text
Client -> Gateway -> Order API -> Database
                              -> Payment Provider
                              -> Broker / Consumer
~~~

Giới hạn có thể chuyển từ CPU Order API sang DB hoặc Payment khi thêm pod. Vì vậy cần phân tích:

| Tầng | Điểm nghẽn thường gặp | Dấu hiệu | Hướng xử lý |
| --- | --- | --- | --- |
| Gateway | Connection, rate limit, network | Timeout, 429/5xx tại edge | Tối ưu routing, connection, quota, tăng edge capacity |
| CPU-bound service | CPU / GC | CPU cao, request queue tăng | Profiling, tối ưu code, thêm replica khi còn nguồn CPU |
| I/O-bound service | Chờ DB/API ngoài | CPU thấp, p95 cao, pool wait | Tối ưu dependency, timeout, bounded concurrency |
| PostgreSQL/MySQL | Query, lock, IOPS, connection | Lock wait, slow queries, replica lag | Index, query plan, transaction, pooling, scale data |
| Redis/cache | Eviction / hot key / network | Hit ratio giảm, latency tăng | Điều chỉnh TTL, key, memory, fallback |
| Kafka consumer | Partition và xử lý | Lag tăng, một số consumer idle | Tối ưu handler, thêm partition/worker có đánh giá order |
| Object storage/network | Bandwidth, request quota | Throughput plateau, timeout | Batch, CDN, parallelism trong quota |
| Payment provider | Rate limit đối tác | 429, request bị từ chối | Queue, throttle, hợp đồng tăng quota, idempotency |

**Nguyên tắc nút thắt:** capacity toàn tuyến bị giới hạn bởi thành phần mà luồng bắt buộc phải đi qua và khả năng xử lý hiệu quả của nó. Với nhiều nhánh song song, phép tính chi tiết có thể phức tạp hơn, nhưng tăng năng lực cho thành phần không nghẽn hiếm khi cải thiện throughput toàn tuyến.

### Ví dụ database connection

Một pod Order có pool tối đa 20 connection. Khi scale từ 5 lên 20 pod:

~~~text
5 × 20  = 100 connection tiềm năng
20 × 20 = 400 connection tiềm năng
~~~

Nếu DB chỉ chịu tốt khoảng 150 connection theo workload thật, việc tăng 20 pod có thể làm DB tốn thêm bộ nhớ, lock và context switching. Khi hoạch định replica, phải tính tổng pool của **mọi service và job** sử dụng cùng DB, cả thời điểm rolling deployment khi số pod tạm vượt định mức.

## 7. Tính năng lực mỗi replica bằng đo tải bền vững

Mô hình tuyến tính là điểm khởi đầu, không phải kết luận cuối. Giả sử load test trên Catalog API cho thấy một replica có thể phục vụ ổn định 150 request/giây với p95 dưới 180 ms, lỗi không quá mục tiêu và các dependency không nghẽn.

Nếu dự báo peak 1.200 request/giây:

~~~text
N_base = ceil(1.200 / 150) = 8 replicas
~~~

Nếu muốn dự trữ khoảng 25% khả năng xử lý trên tải peak dự báo:

~~~text
N_with_headroom = ceil((1.200 × 1,25) / 150) = 10 replicas
~~~

Số 10 phụ thuộc hoàn toàn vào điều kiện load test và giả định headroom. Nó không tính được tự động bằng cách lấy CPU của 1 pod nhân số pod nếu cache miss, connection pool hay DB contention thay đổi theo quy mô.

### Dự phòng khi mất một zone

Giả sử 10 replica đủ phục vụ đỉnh với 25% headroom; hệ thống triển khai cân bằng trên ba availability zones. Nếu yêu cầu vẫn đủ năng lực tương đương sau khi mất một zone, số pod tổng có thể cần khoảng:

~~~text
N_3zones = ceil(10 × 3 / 2) = 15 replicas
~~~

Mục đích là sau khi một phần ba replica mất đi, phần còn lại khoảng 10 replica. Con số này chỉ hợp lý khi traffic có thể chuyển sang zone còn sống, các dependency cũng đủ dự phòng, node còn capacity, và topology spread thực sự phân phối pod như mong muốn. Nếu không cần giữ nguyên toàn bộ headroom khi mất zone, công thức mục tiêu sẽ khác.

**N+1** hoặc dự phòng một replica không tự tương đương với khả năng chịu mất một zone. Hãy chỉ rõ failure domain cần bảo vệ: pod, node, zone hay region.

## 8. CPU planning: usage, request, limit và throttling

Kubernetes phân biệt:
- **CPU usage:** số CPU core đang sử dụng thực tế; ví dụ 500m tương đương 0,5 core.
- **CPU request:** mức CPU dùng để scheduler bố trí pod và để HPA tính CPU utilization khi dùng resource metric.
- **CPU limit:** ngưỡng CPU có thể bị throttling khi vượt; nó không phải mục tiêu tự nhiên của HPA.
- **Node allocatable:** tài nguyên node còn lại cho pod sau khi trừ phần Kubernetes/system reserve.

Ví dụ cấu hình:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1500m"
    memory: "1Gi"
~~~

Nếu có 15 replica, tổng CPU requests cho service là 7,5 core; tổng memory requests là 7,5 GiB. Đây chỉ là phần một workload, chưa tính kube-system, sidecar, logging agent, daemonset, namespace khác, rolling surge và tài nguyên dự phòng.

**Không lấy CPU limits cộng lại để suy ra node nào đủ đặt pod.** Scheduler dùng requests để quyết định bố trí. Nhưng limits vẫn có thể ảnh hưởng latency do throttling; ứng dụng JVM có burst CPU cần được đo trong môi trường gần production.

### CPU cost per request

Với workload CPU-bound, một ước lượng khác là CPU-seconds mỗi request:

~~~text
CPU_seconds_per_request = CPU_cores_used / successful_RPS
Required_cores ≈ predicted_RPS × CPU_seconds_per_request
~~~

Ví dụ 2 core sử dụng tại 400 RPS tương ứng khoảng 0,005 CPU-second/request. 1.000 RPS với cùng workload cần khoảng 5 core CPU thực sử dụng trước khi tính headroom. Nếu cache hit, payload, tỷ lệ endpoint hay phiên bản JVM thay đổi, con số CPU/request cũng thay đổi.

Mô hình CPU giúp kiểm tra chéo kết quả load test; **không** thay thế kiểm tra memory, I/O và latency.

## 9. Memory planning: không chỉ đếm heap

Với Java/Spring Boot, RSS hoặc memory working set thường bao gồm:
- JVM heap cho object đang sống.
- Metaspace, code cache và thread stacks.
- Direct/off-heap buffers, native libraries, bộ nhớ TLS/network.
- Cache trong tiến trình, batch buffers và dữ liệu deserialize.
- Overhead của agent/sidecar và các thay đổi cấu hình khi deploy.

Nếu pod có memory limit 1 GiB, không thể mặc định cấu hình heap 1 GiB là an toàn; JVM cần bộ nhớ ngoài heap. Phải đo bộ nhớ trong steady state, spike, GC, leak và batch lớn. Cân nhắc cách JVM nhận diện container limit theo phiên bản JDK đang dùng, cấu hình MaxRAMPercentage hoặc heap nếu dự án quy định.

**Tăng replica không làm giảm tổng memory một cách tuyến tính.** Mỗi pod mới có baseline JVM, local cache và connection pool. Nếu một service từ 4 lên 16 replica, tổng bộ nhớ nền có thể tăng xấp xỉ bốn lần dù workload không tăng tương ứng. Do đó cần theo dõi *memory per replica* và tổng memory cluster.

Đối với dịch vụ giữ dữ liệu lớn trong RAM, tăng replica có thể làm copy cùng cache nhiều lần. Chuyển một phần dữ liệu sang shared cache hoặc điều chỉnh cache admission có thể hữu ích, nhưng sẽ tạo dependency network mới.

### Dự báo dung lượng storage

Capacity planning không dừng ở CPU/RAM:

~~~text
Projected_storage =
  current_storage
  + daily_ingestion × days × retention_factor
  + index / replication / backup overhead
~~~

Ví dụ 20 GiB dữ liệu mới mỗi ngày trong 180 ngày tạo 3.600 GiB dữ liệu thô trước khi tính nén, index, replication, phân mảnh và backup. Cần đo hệ số thực tế của DB và chính sách lưu trữ riêng. Retention policy, phân vùng, archive và dọn dữ liệu hết hạn phải được đưa vào kế hoạch; không đợi đĩa đầy mới xử lý.

Với Kafka, capacity storage phụ thuộc ingress bytes/giây, retention, replication factor, compression và các topic ngoài dữ liệu chính. Với object storage, cần xét băng thông, số request API và thời gian restore ngoài dung lượng.

## 10. Queue capacity và thời gian xóa backlog

Với message-driven microservices, hệ thống có thể tạm chấp nhận tải nhanh hơn tốc độ xử lý nhờ queue, nhưng backlog không thể tăng mãi.

Gọi:
- λ = số message đến trung bình mỗi giây.
- μ = số message xử lý thành công mỗi giây trên mỗi worker ở SLO chấp nhận được.
- N = số worker hoạt động hiệu quả.

Trong giả định đơn giản, tổng service rate khoảng N × μ. Backlog tăng khi λ lớn hơn N × μ.

~~~text
Backlog_growth_per_second ≈ max(0, λ - N × μ)
Drain_rate_when_overprovisioned ≈ N × μ - λ
Drain_time_seconds ≈ current_backlog / drain_rate
~~~

Ví dụ Inventory nhận 500 event/giây, mỗi worker xử lý bền vững 100 event/giây, có 4 worker:

~~~text
Processing capacity = 4 × 100 = 400 event/s
Backlog growth       = 500 - 400 = 100 event/s
After 10 minutes     ≈ 60.000 queued events
~~~

Nếu tăng lên 8 worker và λ vẫn là 500 event/giây:

~~~text
Drain rate = 8 × 100 - 500 = 300 event/s
Drain time ≈ 60.000 / 300 = 200 seconds
~~~

Ước lượng bỏ qua retry, rebalance, cold start, skew giữa partition và giới hạn database. Với Kafka, 8 worker chỉ hoạt động song song nếu có đủ partition và phân bổ hợp lý. Nếu topic có 4 partition và consumer group đang dùng đủ 4 consumer, tăng thêm lên 8 có thể tạo worker idle.

**Age of oldest message** thường là SLI quan trọng hơn chỉ queue depth. Một hàng đợi 10.000 message xử lý trong vài giây có thể khỏe; một hàng đợi 100 message nhưng mỗi message đã chờ 30 phút có thể vi phạm yêu cầu nghiệp vụ.

## 11. Dự báo nhu cầu: baseline, tăng trưởng, mùa vụ và sự kiện

Một dự báo nên tách ít nhất bốn thành phần:

1. **Baseline:** tải điển hình theo ngày/giờ, gồm sự khác biệt giữa ngày làm việc và cuối tuần.
2. **Growth:** tăng trưởng số người dùng, transaction, kích thước dữ liệu hoặc request mỗi người dùng.
3. **Seasonality:** giờ cao điểm, kỳ lương, cuối tháng, ngày lễ hoặc chu kỳ batch.
4. **Events/changes:** chiến dịch marketing, ra mắt sản phẩm, thay đổi cấu trúc API, di chuyển tenant, sự cố của dependency và retry.

Mô hình đơn giản để tạo kịch bản:

~~~text
Expected_peak =
    observed_reference_peak
    × user_growth_factor
    × usage_per_user_factor
    × event_factor
    × request_amplification_factor
~~~

Ví dụ peak quan sát là 700 RPS; dự báo người dùng tăng 20%, số request/người tăng 10%, campaign tăng tạm thời 1,5 lần:

~~~text
Expected_peak = 700 × 1,20 × 1,10 × 1,50
              = 1.386 RPS
~~~

Nếu có fan-out hoặc retry mới thì phải tính thêm ở đúng service liên quan. Các hệ số không phải chắc chắn độc lập; đây là phép tính kịch bản để minh họa, cần kiểm tra bằng dữ liệu và thông tin từ đội sản phẩm.

### Dự báo theo nhiều kịch bản

| Kịch bản | Tình huống | Dữ liệu cần chốt |
| --- | --- | --- |
| Base | Tăng trưởng thông thường | Baseline, dự báo MAU/DAU, RPS/active user |
| High | Tăng trưởng nhanh, campaign lớn | Peak event, marketing reach, tỷ lệ chuyển đổi |
| Stress | Burst, retry hoặc cache miss cao | Request amplification, cold cache, dependency latency |
| Degraded | Mất một node/zone hoặc giảm năng lực DB | Năng lực còn lại, failover time, headroom |
| Recovery | Hệ thống hồi phục sau downtime | Queue backlog, tốc độ drain, quota downstream |

Điều quan trọng là các kịch bản mang ý nghĩa quyết định: cái nào cần đáp ứng hoàn toàn, cái nào được phép giảm chất lượng chức năng, và cái nào yêu cầu phê duyệt thêm tài nguyên hoặc giới hạn lưu lượng.

### Sai lệch giữa trung bình và đỉnh

Không lấy MAU rồi chia đều cho toàn bộ số giây của tháng để suy ra peak. Ví dụ một triệu người dùng hằng tháng không cho biết bao nhiêu người cùng bấm thanh toán lúc mở bán. Cần quan sát session concurrency, conversion funnel, tỷ lệ request theo giờ và thông tin campaign để ước lượng.

Với một hệ thống mới chưa đủ dữ liệu, có thể dùng giả định từ kế hoạch kinh doanh và chạy load test theo nhiều mức tải, đánh dấu rõ độ bất định. Sau khi có telemetry thực, cập nhật mô hình thay vì giữ một dự báo “một lần cho cả năm”.

## 12. Dự báo theo thời gian và kiểm soát độ bất định

Forecast có thể xây bằng đường trung bình trượt, thống kê cùng giờ/cùng ngày, phân tích xu hướng, hoặc mô hình time series phức tạp hơn khi dữ liệu đủ tốt. Không cần dùng machine learning nếu một mô hình mùa vụ đơn giản đã giải thích được tải và hỗ trợ quyết định.

Một cách thực hành:
1. Thu thập chuỗi thời gian request/event theo service, route, tenant và vùng.
2. Loại bỏ hoặc gắn nhãn các giai đoạn monitoring lỗi, deploy thử, load test và downtime; không xóa âm thầm spike nghiệp vụ thật.
3. Tạo baseline theo giờ trong tuần, phân tích trend tăng trưởng.
4. Bổ sung thông tin sự kiện tương lai từ sản phẩm, marketing, vận hành.
5. Sinh các kịch bản base/high/stress, ghi rõ giả định.
6. So sánh forecast với số liệu thực tế theo tuần; điều chỉnh khi usage profile đổi.

Không nên chỉ xuất một con số chính xác giả tạo như “1.387,42 RPS vào 20:05”. Hãy biểu diễn khoảng dự báo hoặc nhiều kịch bản; con số dùng để chọn năng lực cần có độ bảo thủ tương ứng với chi phí gián đoạn và khả năng scale nhanh.

**Forecast horizon** cũng ảnh hưởng giải pháp:
- Vài phút: autoscaling, rate limit, queue, cache và headroom.
- Vài ngày/tuần: đặt trước node/quota, lập lịch capacity cho campaign.
- Vài tháng: tăng DB/storage, phân vùng dữ liệu, hợp đồng quota với nhà cung cấp, thay đổi kiến trúc.
- Vài năm: chiến lược dữ liệu, partitioning/sharding, vòng đời lưu trữ và chi phí dài hạn.

Autoscaling có thể tạo pod trong vài chục giây hoặc vài phút, nhưng tăng giới hạn rate của provider, thay đổi partition key hoặc tối ưu một database đã đầy có thể cần nhiều tuần. Forecast cần dẫn tới hành động theo **thời gian chuẩn bị** của từng loại tài nguyên.

## 13. Headroom và dự phòng năng lực

Headroom là phần năng lực dự trữ để hấp thụ burst, biến động nhu cầu, triển khai mới và lỗi. Có thể biểu diễn:

~~~text
Headroom_fraction = (Sustainable_capacity - Expected_demand)
                    / Sustainable_capacity
~~~

Hoặc dùng hệ số năng lực dự trữ:

~~~text
Provisioned_capacity = Expected_demand × reserve_factor
~~~

Hai cách biểu diễn không đồng nhất hoàn toàn. Ví dụ năng lực cung cấp 1.250 RPS cho demand 1.000 RPS là 20% headroom theo mẫu số capacity, nhưng tương đương cấp năng lực cao hơn demand 25%. Trong báo cáo phải ghi rõ công thức, tránh gọi cùng con số “25% headroom” với hai cách tính khác nhau.

Headroom cần phản ánh:
- Độ bất định của forecast và biến động traffic.
- Time to scale: thời gian từ metric tăng đến khi pod mới Ready.
- Rolling deployment tạo thêm hoặc giảm instance tạm thời.
- Nhu cầu failover từ pod/node/zone khác.
- Cache cold, retry amplification và batch đột biến.
- Khoảng thời gian phải duy trì SLO khi sự cố xảy ra.

Không nên dự trữ mọi tầng cùng một tỷ lệ máy móc. Database, cache, broker, storage và nhà cung cấp bên ngoài có thời gian mở rộng khác nhau. Hãy có headroom tương ứng với thời gian phát hiện, khởi tạo và khôi phục của từng thành phần.

## 14. Kubernetes HPA: scale theo tín hiệu phù hợp

Kubernetes Horizontal Pod Autoscaler (HPA) điều chỉnh số replica của workload từ metric. Ví dụ autoscaling/v2 cho Catalog API theo CPU:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: catalog-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: catalog-api
  minReplicas: 4
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 20
          periodSeconds: 60
~~~

**CPU utilization 65%** được tính tương đối với CPU requests của pod/container theo cách HPA xử lý resource metrics, không phải phần trăm CPU limit hay toàn bộ node. Nếu request CPU bị đặt quá thấp hoặc quá cao, hành vi HPA có thể không phản ánh đúng tải.

Trong xấp xỉ lý tưởng:

~~~text
desiredReplicas ≈ ceil(currentReplicas × observedMetric / targetMetric)
~~~

Nếu đang có 5 replica, CPU utilization trung bình 91% so với request và mục tiêu 65%, công thức đơn giản cho kết quả ceil(5 × 91/65) = 7. HPA thực tế còn xét tolerance, pod chưa Ready, metric thiếu và các chính sách scale.

**HPA phù hợp khi metric liên hệ nhân quả với tài nguyên cần thêm.** Với API CPU-bound, CPU thường có ích. Với worker đọc queue, queue lag hoặc tuổi message có thể phù hợp hơn. Với service đang chờ DB hoặc provider, tăng pod theo CPU có thể không phản ứng, còn tăng theo latency không giới hạn có thể làm dependency tệ hơn.

### Những điều kiện vận hành

- Metrics pipeline phải cung cấp dữ liệu đúng thời điểm; resource metrics có thể dùng metrics-server.
- Đặt minReplicas theo khả năng phục vụ tải nền và SLO lúc cold start.
- Đặt maxReplicas theo capacity của node, database, broker và hệ thống ngoài.
- Dùng stabilization window cho scale down để tránh tăng giảm liên tục.
- Định nghĩa rõ thành phần sở hữu trường replica giữa HPA, manifest và GitOps.
- Khi node không đủ chỗ, HPA tạo mong muốn tăng pod nhưng pod có thể vẫn Pending.
- Theo dõi desired/current/available replicas, thời gian startup và số lần scale, không chỉ metric CPU.

Không dùng HPA như một biện pháp thay thế cho sửa memory leak, truy vấn SQL chậm hoặc service có xử lý blocking thiếu giới hạn.

## 15. Scale theo queue với KEDA hoặc cơ chế tương đương

KEDA có thể cung cấp cơ chế scale workload dựa trên Kafka lag, queue length và trigger sự kiện. Phù hợp với worker bất đồng bộ khi CPU không phản ánh lượng việc còn chờ.

Ví dụ ý tưởng:

~~~text
Inventory queue lag > mục tiêu
          |
          v
Autoscaler tăng Inventory Worker
          |
          v
Consumer group xử lý nhanh hơn
          |
          v
Lag giảm, nếu downstream còn capacity
~~~

Cần kiểm tra:
- Số partition hoặc cách chia work item giới hạn concurrency.
- Mỗi worker xử lý an toàn bao nhiêu event/giây dưới tải thật.
- Queue có cần scale-to-zero hay giữ worker tối thiểu để giảm cold start.
- Khi scale down có rebalance/ack và xử lý message đang bay đúng không.
- Retry và duplicate delivery có tạo tác động nghiệp vụ lặp không.
- Các API/DB downstream có quota và concurrency budget riêng không.

Một scaler chỉ nhìn queue length có thể yêu cầu rất nhiều pod ngay khi database giảm tốc. Nên đặt max replica, rate limit, backpressure và cảnh báo về nguyên nhân nghẽn.

## 16. Cluster capacity và node autoscaling

Pod không chạy trên khái niệm “cluster vô hạn”. Kubernetes scheduler phải tìm node đáp ứng requests CPU, memory, topology, affinity và các giới hạn khác.

Ví dụ:
- 15 replica Catalog, mỗi pod request 500m CPU và 512 MiB.
- Tổng requests riêng Catalog là 7,5 core và 7,5 GiB.
- Có thêm Ingress, API khác, logging, metrics, sidecar và hệ thống nền.
- Rolling deployment có thể cần thêm pod theo maxSurge.
- Nếu trải đều ba zone, mỗi zone cần đủ tài nguyên cho phần replica tương ứng.

Cần tách:
1. **Pod scaling:** HPA tăng/giảm replica.
2. **Node scaling:** cơ chế Cluster Autoscaler hoặc node provisioner đáp ứng các pod Pending khi điều kiện cho phép.
3. **Storage/database scaling:** nâng tài nguyên backing services, thường có độ trễ và giới hạn riêng.
4. **Quota/budget:** namespace quota, cloud quota, node type availability và ngân sách tài chính.

Một HPA muốn tăng lên 20 replica không có nghĩa 20 pod có thể chạy. Nếu cloud quota đã chạm hoặc node provisioner không có node phù hợp, desiredReplicas tăng nhưng Ready replicas đứng yên, backlog tiếp tục tăng.

### Pod distribution và failure domain

Nếu tất cả pod của service quan trọng nằm trên một node, scale-out không bảo vệ được khi node hỏng. Topology spread constraints hoặc affinity có thể giúp phân bổ qua node/zone. PodDisruptionBudget hỗ trợ quản lý những gián đoạn tự nguyện theo cơ chế eviction, nhưng không chống mọi loại lỗi đột ngột.

Trong capacity plan, phải định nghĩa sau khi mất một zone, các zone còn lại có đủ CPU/RAM, ingress capacity và năng lực database để giữ SLO tối thiểu hay không. Dự phòng ở tầng ứng dụng vô nghĩa nếu toàn bộ service vẫn phụ thuộc một database đơn điểm lỗi.

## 17. Vertical scaling và khi nào không nên scale ngang

Một số workload cần nhiều CPU/RAM cho một job đơn lẻ, hoặc bị giới hạn bởi cấu trúc không thể chia song song. Khi đó tăng kích cỡ instance có thể hữu ích hơn tạo nhiều replica.

Ví dụ:
- Một job xử lý file lớn cần nhiều RAM tại một thời điểm.
- Một phép tính được thực hiện tuần tự trong một worker.
- Một DB writer bị giới hạn bởi lock hoặc thiết kế dữ liệu.
- Một consumer group có số partition đã đạt giới hạn song song.
- Một máy chứa in-memory index lớn, việc nhân bản bản sao tốn RAM.

Vertical Pod Autoscaler (VPA) có thể hỗ trợ đề xuất hoặc điều chỉnh resource requests theo cách cấu hình và chế độ vận hành, nhưng việc thay đổi resource có thể yêu cầu thay pod tùy cơ chế/phiên bản. Không dùng đồng thời HPA và VPA trên cùng tín hiệu tài nguyên mà không hiểu xung đột giữa controllers. Tách trách nhiệm tối ưu kích cỡ pod và tối ưu số replica theo chiến lược được kiểm thử.

Đừng coi horizontal scaling là tiêu chí bắt buộc của mọi microservice. Cách mở rộng phù hợp phải căn cứ nút thắt và quyền sở hữu dữ liệu.

## 18. Dự báo tác động của cache và thay đổi phiên bản

Một thay đổi nhỏ trong cache có thể biến capacity plan thành lỗi thời.

Giả sử Catalog chịu 1.000 request/giây với cache hit 90%. Backend DB chỉ nhận khoảng 100 cache miss/giây trong giả định một request miss tạo một truy vấn. Nếu cache hit giảm còn 50%, DB có thể phải xử lý khoảng 500 truy vấn/giây, tăng gấp năm lần mà traffic từ người dùng không đổi.

~~~text
DB demand ≈ incoming_requests × miss_ratio × DB_calls_per_miss
~~~

Phải tính **warm cache** và **cold cache** khi đo capacity. Rolling deployment có thể xóa local cache ở nhiều pod; Redis eviction hoặc invalidation đồng loạt cũng gây miss storm. Capacity ở mức bình thường không đủ nếu sự cố cache tạo tải đột biến vượt sức chịu của DB.

Tương tự, sau một phiên bản mới:
- CPU/request tăng do serialization/logging.
- Memory baseline tăng vì thay đổi JVM/cấu trúc cache.
- Số lần gọi downstream trên mỗi request tăng.
- Một truy vấn mới thiếu index làm DB latency tăng.
- Retry policy đổi, làm traffic amplification cao hơn.

Capacity plan cần liên kết số đo với **version và cấu hình**; không sử dụng benchmark cũ như một bảo đảm vĩnh viễn.

## 19. Quản lý năng lực hệ thống bên ngoài

Payment API, email/SMS provider, search SaaS, cloud API, DNS và object storage đều có giới hạn không do mình trực tiếp điều chỉnh.

Các giới hạn có thể gồm:
- Requests/giây hoặc transactions/phút.
- Số kết nối đồng thời.
- Tổng quota theo ngày/tháng.
- Bandwidth và maximum payload.
- Hạn mức burst.
- Rate limit riêng theo tài khoản/tenant hoặc region.

Nếu provider chỉ cho 100 giao dịch/giây, tăng Payment Adapter từ 2 lên 20 pod không làm năng lực provider tăng. Thậm chí, retry đồng thời có thể làm xuất hiện nhiều 429 hơn.

Cần:
1. Dự báo lượng request gửi tới provider theo giao dịch nghiệp vụ, gồm retry.
2. Thỏa thuận nâng quota nếu kịch bản high demand vượt giới hạn.
3. Dùng bounded concurrency, token bucket hoặc queue/backpressure.
4. Dùng idempotency key cho các tác động có thể được retry.
5. Có chính sách giảm tải/tạm chờ rõ ràng khi provider quá tải.
6. Theo dõi rate limit, thời gian trả lời và phần backlog chờ nhà cung cấp.

**Capacity plan tốt là kế hoạch của cả chuỗi dependency**, không chỉ bảng replica nội bộ.

## 20. Load test để xác nhận dự báo

Dự báo tạo giả thuyết. Load test và quan sát sản xuất mới giúp xác nhận năng lực thực.

Các dạng thử nghiệm cần cân nhắc:

| Kiểu test | Cách tạo tải | Mục tiêu |
| --- | --- | --- |
| Baseline | Tải thường ngày ổn định | Đo latency, lỗi, CPU và dependency |
| Step load | Tăng theo bậc | Tìm điểm throughput ngừng tăng/latency vọt |
| Ramp | Tăng dần theo lịch | Quan sát autoscaler và cold start |
| Spike | Tăng mạnh trong vài giây/phút | Đánh giá headroom, rate limit, burst |
| Soak | Tải cao trong nhiều giờ | Phát hiện leak, GC, connection, queue |
| Failover | Mất pod/node/zone theo phạm vi thử | Kiểm tra SLO ở trạng thái giảm năng lực |
| Recovery | Dừng consumer rồi bật lại | Đo thời gian drain backlog |
| Cold-cache | Xóa cache theo kế hoạch thử | Đo DB surge và stampede |

**Load generator cũng phải có đủ capacity.** Nếu chính máy tạo tải đạt 100% CPU hoặc hết connection, kết quả “backend chỉ chịu 2.000 RPS” có thể là giới hạn của generator.

Kết quả cần nêu lượng request đã gửi **và lượng thành công**, thời gian thực hiện, phân phối endpoint, payload, tỷ lệ cache hit, phiên bản ứng dụng và bối cảnh dependency. Một hệ thống có throughput cao nhờ trả nhanh HTTP 500 không được coi là có capacity tốt.

### Cần kiểm tra load test có giống nghiệp vụ thật?

Nếu production có 70% GET sản phẩm, 20% search, 8% add-to-cart và 2% checkout, dùng 100% GET sản phẩm để benchmark sẽ đánh giá sai CPU, DB và fan-out. Nên dùng workload mix sát thực tế và chạy thêm kịch bản stress cho endpoint nặng.

Dữ liệu thử cũng quan trọng: 1.000 sản phẩm lặp lại làm cache hit rất cao; production có một triệu sản phẩm và truy vấn đa dạng sẽ có hành vi khác. Dùng dữ liệu có cardinality và phân bố hot key gần thực tế.

## 21. Capacity review định kỳ và trách nhiệm sở hữu

Capacity planning không phải bảng tính lập một lần. Nên có lịch review phù hợp tốc độ thay đổi của sản phẩm, ví dụ hằng tuần ở giai đoạn tăng trưởng nhanh và trước mỗi campaign lớn.

Bảng theo dõi mỗi service có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| Service / owner | Ai chịu trách nhiệm và có quyền điều chỉnh |
| SLO quan trọng | Độ trễ, availability, queue age hoặc batch deadline |
| Current demand | p95/p99 theo cửa sổ, peak 5 phút, số giao dịch |
| Sustainable capacity | Kết quả benchmark dưới SLO |
| Current replicas/requests | Tài nguyên đang cấp và chính sách HPA |
| Headroom | Chênh năng lực với demand và cách tính |
| Hard constraints | DB, broker, quota, partition, node |
| Forecast high/stress | Tải dự kiến theo kịch bản và ngày sự kiện |
| Lead time | Thời gian chuẩn bị tài nguyên/tăng quota |
| Trigger/action | Khi nào phải thêm capacity, tối ưu hoặc giảm tải |

Những thay đổi về kiến trúc, tính năng, retention, cache hoặc phiên bản runtime cần được đưa vào vòng review. Các kế hoạch tăng quota bên ngoài thường có lead time lớn hơn HPA, nên phải triển khai sớm hơn ngày event.

## 22. Theo dõi forecast accuracy

Để đánh giá dự báo, so sánh demand dự kiến với demand thực tế ở cùng service, thời điểm, cửa sổ và định nghĩa metric.

Một số chỉ số:
- **Forecast error:** thực tế trừ dự báo tại từng mốc.
- **Absolute percentage error:** độ lệch tuyệt đối chia cho thực tế khi thực tế khác 0; không nên dùng mù với chuỗi có nhiều giá trị bằng 0.
- **Peak coverage:** kịch bản high có bao phủ được đỉnh thực không?
- **Capacity utilization under SLO:** bao nhiêu phần năng lực được dùng mà vẫn đạt SLO?
- **Time to scale:** từ khi demand tăng đến khi replica mới Ready.
- **Cost per successful request/transaction:** chi phí cho kết quả đúng thay vì số pod.

Một forecast có trung bình tháng rất chính xác nhưng thường xuyên thấp hơn peak trong 10 phút quan trọng vẫn có thể gây outage. Do đó, cần chấm sai lệch theo **quyết định capacity**: dự báo có giúp chuẩn bị đủ tài nguyên đúng lúc, giữ SLO và kiểm soát chi phí hay không.

Không nên điều chỉnh model chỉ để khớp dữ liệu quá khứ mà bỏ qua các sự kiện mới. Khi traffic pattern đổi sau khi ra mắt một tính năng, dữ liệu cũ không còn đại diện cho tương lai như trước.

## 23. Cân đối độ tin cậy và chi phí

Overprovisioning khiến hệ thống có nhiều headroom nhưng tốn chi phí. Underprovisioning giảm chi phí ngắn hạn nhưng có thể gây lỗi, mất giao dịch và mất lòng tin khách hàng.

Một quyết định thường kết hợp:
- Chi phí CPU/RAM của pod và node.
- Chi phí DB tier, IOPS, storage, replication, backup.
- Chi phí Redis, message broker, network egress.
- Chi phí dịch vụ bên ngoài.
- Chi phí môi trường dự phòng và đa zone.
- Chi phí vận hành khi hệ thống liên tục quá tải.
- Tác động doanh thu và SLO khi dịch vụ gián đoạn.

Mục tiêu không phải tối thiểu hóa số replica bất kể rủi ro, cũng không phải luôn vận hành ở mức tải rất thấp. Nên phân tầng ưu tiên:
1. Những phần đường đi doanh thu hoặc an toàn dữ liệu cần headroom và kế hoạch failover rõ.
2. Workload batch ít khẩn cấp có thể chạy trong khung giờ thấp tải, pause/resume và dùng capacity còn dư.
3. Môi trường không production có thể hạ tài nguyên hoặc tắt theo lịch nếu có chính sách phù hợp.
4. Tối ưu code, SQL, cache và network trước khi tăng chi phí cho một điểm nghẽn có thể giải quyết bằng kỹ thuật.

Khi scale down để tiết kiệm, vẫn phải giữ khả năng xử lý burst, tránh thrashing và bảo đảm các tác vụ đang chạy được bàn giao an toàn.

## 24. Ví dụ hoàn chỉnh: chuẩn bị flash sale cho hệ thống bán hàng

Giả sử flash sale dự kiến vào 20:00 và kéo dài 30 phút. Nhóm đã có load test ở phiên bản đang triển khai.

### Dữ liệu minh họa

| Thành phần | Năng lực đo được | Nhu cầu dự báo peak | Giới hạn khác |
| --- | --- | --- | --- |
| Catalog API | 150 GET/s/replica dưới SLO | 1.200 GET/s | Search DB và cache |
| Order API | 40 checkout/s/replica dưới SLO | 120 checkout/s | Order DB transaction |
| Inventory worker | 80 event/s/worker | 360 event/s | Kafka có 8 partitions |
| Payment provider | Quota 100 payments/s | Có thể 120 payments/s | Hợp đồng ngoài, không scale bằng pod |
| PostgreSQL Order | Đã đo ngưỡng query/lock riêng | 120 checkout/s × fan-out DB | Connection và lock |

### Bước 1 — Catalog

Nhu cầu 1.200 GET/s chia cho 150 GET/s/replica cho kết quả tối thiểu 8 replica theo điều kiện benchmark. Nếu cấp năng lực cao hơn peak 25%, cần 10 replica. Nếu còn yêu cầu giữ mức đó sau khi mất một trong ba zone cân bằng, có thể cần khoảng 15 replica cùng đủ năng lực node và backend.

Dự đoán chính xác có thể thay đổi nếu cache hit giảm vì hàng loạt sản phẩm mới hoặc traffic tập trung vào một hot key. Phải load test với cả warm cache/cold cache và kiểm tra Search DB.

### Bước 2 — Order

120 checkout/s chia cho 40 checkout/s/replica cho tối thiểu 3 replica theo năng lực service. Nhưng không nên tăng lên 10 pod nếu DB đang có lock wait hoặc pool wait cao. Đo transaction per checkout, tổng connection sau scale, latency p95/p99 và throughput thành công. Nếu DB đạt ngưỡng, tối ưu transaction, index hoặc giới hạn nhận việc trước khi tăng replica.

### Bước 3 — Inventory worker

360 event/s chia cho 80 event/s/worker gợi ý ít nhất 5 worker để không tích backlog trong điều kiện lý tưởng. Với 8 Kafka partitions, có thể tăng worker tới 8 consumer hoạt động nếu phân phối partition phù hợp và database còn sức. Tăng lên 20 worker trong cùng consumer group cho topic đó không tự tăng song song vượt số partition.

Cần đo tuổi event, backlog, duplicate processing, retry, rebalancing và độ trễ DB khi scale.

### Bước 4 — Payment

Nếu mỗi checkout cần một payment và nhu cầu đạt 120 payment/s, provider quota 100 payment/s là nút thắt trực tiếp. Có hai hướng:
- Thỏa thuận nâng quota trước sự kiện.
- Nếu nghiệp vụ cho phép, đưa thanh toán vào queue có kiểm soát và thông báo trạng thái pending; giới hạn tốc độ gửi để không vượt quota, bảo vệ idempotency và deadline.

Chỉ thêm replica Payment Adapter không giải quyết được giới hạn 100 payment/s.

### Bước 5 — Chuẩn bị cluster và rollout

Xác nhận đủ node allocatable cho min/max replicas, tài nguyên DB/Redis, rolling maxSurge, spread across zones và pod startup. Nếu thời gian startup JVM + image pull + readiness là vài phút, có thể **pre-scale** trước 20:00 thay vì chờ metric HPA tăng tại đúng phút sự kiện.

### Bước 6 — Guardrails và kế hoạch phản ứng

- Cảnh báo khi p95 Checkout vượt SLO, lỗi tăng hoặc payment queue age vượt giới hạn.
- Bảo vệ DB bằng bounded concurrency và connection pool size.
- Bảo vệ provider bằng rate limiter và idempotency key.
- Ưu tiên loại bớt traffic không thiết yếu khi một dependency quá tải.
- Theo dõi autoscaler desired/ready replicas, Pending pod và node scale.
- Xác định người quyết định dừng chiến dịch, hạ chức năng hoặc thay đổi quota.

### Bước 7 — Sau sự kiện

So sánh forecast với peak thật, thời gian HPA phản ứng, cost, lỗi, queue drain và DB saturation. Nếu Catalog đã tăng pod nhưng Search DB vẫn nghẽn, hành động vòng sau là tối ưu truy vấn/cache hoặc tăng capacity Search, không tiếp tục nâng maxReplicas mù quáng.

## 25. Capacity planning cho dữ liệu và tác vụ nền

Nhiều hệ thống chỉ lập kế hoạch cho API request mà quên batch và storage. Trong microservices, data backfill, retention job, reindex, snapshot, backup và message replay có thể cùng cạnh tranh CPU/I/O vào lúc tải người dùng cao.

Ví dụ một job reindex 20 triệu sản phẩm có thể làm Search Cluster bị quá tải dù traffic HTTP không đổi. Hãy:
- Định nghĩa resource budget cho batch, job và consumer.
- Chạy ngoài giờ cao điểm nếu nghiệp vụ cho phép.
- Chia batch và checkpoint; tạm dừng khi CPU/I/O/latency vượt ngưỡng.
- Dự báo dung lượng mới của index và temporary storage.
- Tính mức tăng tải khi replay message sau downtime.
- Giới hạn tốc độ backfill để không tranh chấp với transaction quan trọng.
- Kiểm tra thời gian restore có đáp ứng RTO/RPO đã cam kết hay không.

Quy hoạch storage còn cần xét thời hạn lưu trữ, nén, tăng trưởng log/audit, số phiên bản backup, multi-AZ replication và yêu cầu pháp lý. Một hệ thống còn dư CPU nhưng hết dung lượng ghi hoặc disk IOPS vẫn có thể ngừng xử lý giao dịch.

## 26. Các sai lầm thường gặp

**Chỉ tính số người dùng trung bình:** bỏ qua fan-out, burst, conversion và thời điểm cao điểm. Cần chuyển nhu cầu nghiệp vụ thành công việc kỹ thuật theo cửa sổ thời gian đúng.

**Scale mọi microservice cùng một hệ số:** từng service có loại tải, SLO và dependency khác nhau. Tăng replica ở điểm không nghẽn chủ yếu tăng chi phí.

**Lấy CPU usage làm capacity duy nhất:** dịch vụ chờ DB, lock hoặc provider có thể nghẽn khi CPU vẫn thấp. Cần quan sát saturation và latency tại các ranh giới.

**Giả định throughput tăng tuyến tính theo replica:** cache miss, connection pool, shared DB, quota và network có thể phá tính tuyến tính. Phải đo ở nhiều quy mô.

**Dự báo bằng số liệu của bản release cũ:** thay đổi code, cache, payload và retry có thể làm chi phí mỗi request thay đổi. Liên kết benchmark với version.

**Không xét thời gian autoscaling:** một burst ngắn có thể kết thúc trước khi pod mới Ready. Cần headroom, pre-scale hoặc queue/rate limiting tùy loại tải.

**Đặt HPA maxReplicas rất lớn:** nếu node quota hoặc DB không đủ, pod Pending hoặc gây nghẽn phía sau. Max phải gắn với downstream capacity.

**Quên CPU throttling và memory RSS:** chỉ nhìn heap hoặc trung bình CPU dễ bỏ lỡ giới hạn container và p99 latency.

**Không tính rolling deployment:** maxSurge, old/new pod cùng tồn tại và warm-up có thể làm capacity/kết nối tăng tạm thời.

**Không dự phòng failure domain:** nhiều replica trên cùng node không giúp chịu được node failure; DB đơn điểm lỗi vẫn là nút thắt.

**Không tính queue backlog và catch-up:** sau sự cố, workload cần xử lý gồm cả traffic mới và dữ liệu còn đọng. Phải đo thời gian drain.

**Không kiểm thử cold cache và failure mode:** số liệu chỉ từ cache ấm có thể quá lạc quan so với ngày có incident.

**Dùng tải lỗi làm throughput:** hệ thống trả 429/500 rất nhanh không chứng minh năng lực xử lý giao dịch thành công.

**Không sở hữu forecast:** không có người cập nhật giả định, dữ liệu forecast và quota có thể lỗi thời đúng trước campaign.

**Chỉ tối ưu chi phí theo CPU trung bình:** giảm replica mà không xem SLO, failover và time to scale có thể làm mất giao dịch tại peak.

## 27. Checklist trước sự kiện tăng tải hoặc phát hành lớn

- [ ] SLO và hành trình nghiệp vụ quan trọng được định nghĩa bằng metric rõ.
- [ ] Có baseline demand theo giờ/ngày, peak ngắn hạn và peak duy trì.
- [ ] Có request mix, fan-out, retry và cache hit/miss đủ đại diện.
- [ ] Biết năng lực bền vững mỗi replica dưới SLO ở bản release hiện tại.
- [ ] Đã xác định điểm nghẽn ở CPU, memory, DB, broker, Redis, network hoặc provider.
- [ ] Có forecast base/high/stress và giả định đầu vào được ghi rõ.
- [ ] Tính headroom, thời gian scale, rolling surge và kịch bản mất node/zone.
- [ ] CPU/memory requests, limits, pool sizes và max replica có kiểm tra với cluster capacity.
- [ ] HPA/KEDA có metric phù hợp, min/max, stabilization và alert.
- [ ] Node autoscaling/quota có thể cấp pod theo nhu cầu; không còn điểm Pending chưa xử lý.
- [ ] Database connection, lock, IOPS và index có headroom cho số replica dự kiến.
- [ ] Queue/consumer có đủ partition, xử lý duplicate an toàn và giới hạn downstream.
- [ ] Provider bên ngoài đủ quota hoặc có queue/throttle/giảm tải theo chính sách.
- [ ] Đã chạy load test theo baseline, step, ramp, spike, soak, cold cache và failover.
- [ ] Có kế hoạch capacity cho batch, storage, log, backup và phục hồi.
- [ ] Dashboard theo dõi successful throughput, latency, lỗi, backlog, saturation và chi phí.
- [ ] Có người phụ trách giám sát sự kiện, ngưỡng dừng và phương án ứng cứu.
- [ ] Sau sự kiện có buổi đối soát forecast với số liệu thực và cập nhật kế hoạch.

## 28. Bài tập áp dụng

Một hệ thống gồm Catalog, Order, Payment và Inventory Worker. Giả định:

- Catalog nhận tối đa 900 GET/giây trong đợt khuyến mãi; một replica phục vụ bền vững 125 GET/giây dưới SLO.
- Order nhận 140 checkout/giây; một replica phục vụ bền vững 35 checkout/giây nếu DB không nghẽn.
- Payment Provider cho 100 giao dịch/giây; mọi checkout đều cần thanh toán.
- Kafka topic của Inventory có 6 partition. Một consumer xử lý 70 event/giây; dự kiến 300 event/giây.
- Các pod Catalog request 400m CPU và 512 MiB RAM; các pod Order request 500m CPU và 768 MiB RAM.
- Cluster hiện có 12 core CPU allocatable còn lại và 20 GiB RAM allocatable còn lại sau workload thường trực.

Hãy thực hiện:
1. Tính replica tối thiểu của Catalog và Order theo throughput đo được.
2. Thêm mức dự phòng cho burst và giải thích cách lựa chọn headroom.
3. Tính CPU/RAM requests dự kiến và xác định liệu cluster còn đủ để đặt pod cùng lúc.
4. Giải thích giới hạn concurrency Inventory do chỉ có 6 partition.
5. Đề xuất cách xử lý khi Payment cần 140 TPS nhưng quota chỉ 100 TPS.
6. Nêu metric cần quan sát để xác minh database Order còn năng lực khi tăng replica.
7. Xây hai kịch bản: hoạt động bình thường và mất một node/zone.
8. Thiết kế kế hoạch pre-scale/HPA cho event chỉ kéo dài 15 phút.
9. Nêu load test chứng minh các con số replica và dự báo đã hợp lệ.
10. Sau sự kiện, quyết định metric nào cho biết nên tăng capacity, tối ưu code hay điều chỉnh forecast.

Trong phần trả lời, hãy phân biệt **giá trị tối thiểu tính bằng công thức** với **năng lực đã được kiểm chứng trên toàn hệ thống**. Nếu database, broker hoặc provider đã đạt giới hạn, một phép tính số pod đúng về mặt toán học có thể vẫn không tạo ra throughput nghiệp vụ mong đợi.

## Kết luận

Quản lý năng lực trong microservices là quá trình liên tục nối **demand → workload kỹ thuật → capacity của từng thành phần → SLO toàn hành trình → tài nguyên và chi phí**. Dự báo phải xét giờ cao điểm, tăng trưởng, sự kiện và tình huống suy giảm; sizing phải dựa vào benchmark, headroom, dependency và thời gian scale; triển khai cần autoscaling, quota và khả năng chịu lỗi; còn vận hành phải so sánh forecast với số liệu thực sau mỗi thay đổi. Chỉ khi hệ thống hoàn thành đúng công việc ở mức SLO với chi phí và mức dự phòng hợp lý, capacity planning mới đạt mục tiêu.
