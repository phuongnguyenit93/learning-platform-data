# Mở rộng dọc, ngang và các giới hạn kiến trúc

Một ứng dụng chạy tốt với vài trăm request mỗi phút có thể trở nên chậm khi lưu lượng tăng gấp mười lần. Tăng CPU hoặc RAM cho máy chủ có thể giải quyết tình trạng thiếu tài nguyên trước mắt, nhưng một máy lớn hơn vẫn có giới hạn phần cứng và tạo ra điểm lỗi tập trung. Thêm nhiều máy hoặc container giúp phân phối tải, nhưng chỉ hiệu quả khi ứng dụng, dữ liệu và các dependency có thể làm việc với nhiều instance cùng lúc.

**Mở rộng dọc (vertical scaling, scale-up)** là tăng tài nguyên cho một đơn vị compute hiện có, chẳng hạn CPU, RAM, IOPS hoặc network bandwidth. **Mở rộng ngang (horizontal scaling, scale-out)** là tăng số đơn vị xử lý và phân phối công việc giữa chúng, chẳng hạn thêm VM, container, pod hoặc worker. Hai cách có thể kết hợp; lựa chọn phụ thuộc bottleneck, đặc điểm state, giới hạn nền tảng, SLO và chi phí.

Bài học này thuộc chương **Mở rộng hệ thống** của module **CLOUD_ARCHITECTURE**. Mục tiêu là đánh giá cách hệ thống đáp ứng nhu cầu tăng tải, xác định giới hạn của từng tầng, lập capacity plan và lựa chọn scale-up, scale-out hoặc thay đổi kiến trúc. Trọng tâm là đánh đổi giữa hiệu năng, độ tin cậy, bảo mật, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mở rộng hệ thống nghĩa là gì?

Mở rộng (scaling) là khả năng đáp ứng nhu cầu tăng hoặc thay đổi bằng cách bổ sung, phân bổ hoặc tổ chức lại tài nguyên. Nhu cầu có thể tăng theo:
- Số người dùng đồng thời.
- Request mỗi giây và độ phức tạp mỗi request.
- Số message hoặc event chờ xử lý.
- Dung lượng dữ liệu và tốc độ đọc/ghi.
- Số tenant, khu vực địa lý hoặc workload.
- Kích thước model, file hoặc payload.
- Yêu cầu availability, latency và recovery.

Một hệ thống được xem là scale tốt khi tăng tài nguyên giúp tăng năng lực phục vụ hoặc duy trì SLO với chi phí hợp lý. **Thêm máy không đồng nghĩa tự động tăng năng lực tuyến tính.** Nếu mọi request đều phải chờ cùng một database lock, một external API có quota thấp hoặc một partition nóng, thêm application server có thể làm bottleneck nặng hơn.

### 1.1. Các thuộc tính cần phân biệt

- **Scalability:** khả năng tăng năng lực khi nhu cầu tăng.
- **Elasticity:** khả năng tự động tăng/giảm tài nguyên theo nhu cầu.
- **Capacity:** năng lực tối đa hoặc năng lực an toàn mà hệ thống có thể phục vụ trong điều kiện xác định.
- **Headroom:** phần năng lực dự phòng so với tải hiện tại.
- **Bottleneck:** thành phần giới hạn throughput hoặc latency của toàn hệ thống.
- **Saturation:** trạng thái một tài nguyên gần hoặc chạm giới hạn, khiến queueing và latency tăng mạnh.

Một hệ thống có thể scalable nhưng không elastic nếu cần con người thêm node. Một hệ thống elastic cũng có thể không scalable nếu bottleneck nằm ở một dependency không tăng theo.

## 2. Mở rộng dọc (scale-up)

Scale-up tăng tài nguyên của một máy hoặc một instance hiện có.

~~~mermaid
flowchart TB
    A["Trước: 1 application instance"] --> A1["2 vCPU / 4 GB RAM"]
    B["Sau: cùng một instance"] --> B1["8 vCPU / 32 GB RAM"]
    A1 --> S["Năng lực xử lý mỗi instance tăng"]
    B1 --> S
~~~

Ví dụ Booking API đang chạy trên VM 2 vCPU, 4 GB RAM. Khi traffic tăng và CPU đạt 90%, có thể nâng lên 8 vCPU, 32 GB RAM để xử lý nhiều request hơn trên cùng instance.

### 2.1. Ưu điểm

- Kiến trúc ứng dụng có thể giữ nguyên.
- Ít thay đổi về routing, service discovery và phân phối state.
- Có thể tăng năng lực nhanh nếu cloud provider hỗ trợ resize phù hợp.
- Phù hợp với database hoặc phần mềm legacy khó chia tải.
- Dễ quan sát vì số instance ít.

### 2.2. Hạn chế

- Có giới hạn cấu hình lớn nhất của instance hoặc máy vật lý.
- Giá tăng theo loại máy; cấu hình lớn có thể có cost/throughput kém hơn.
- Một máy lớn trở thành failure domain lớn hơn.
- Việc resize có thể cần restart, downtime hoặc migration.
- Không giải quyết được giới hạn ở database, external service, network hoặc lock.
- Tài nguyên lớn nhưng ít sử dụng có thể lãng phí.

Scale-up thường là bước tốt để xử lý bottleneck đơn giản hoặc tạo headroom, nhưng không thay thế phân tích nguyên nhân. Nếu CPU thấp mà latency tăng do database connection pool cạn, tăng vCPU có thể không giúp gì.

## 3. Mở rộng ngang (scale-out)

Scale-out thêm instance xử lý và phân phối request hoặc công việc giữa chúng.

~~~mermaid
flowchart TB
    U["Users / clients"] --> LB["Load balancer"]
    LB --> A["App instance A"]
    LB --> B["App instance B"]
    LB --> C["App instance C"]
    A --> DB[("Shared data store")]
    B --> DB
    C --> DB
~~~

Ví dụ Booking API có thể chạy ba container giống nhau sau một load balancer. Khi request tăng, orchestrator thêm replica; khi tải giảm, có thể giảm bớt replica để tiết kiệm chi phí.

### 3.1. Ưu điểm

- Tăng tổng throughput bằng cách thêm instance.
- Có thể chịu lỗi một instance mà vẫn phục vụ qua các instance còn lại.
- Dễ triển khai theo từng vùng hoặc availability zone.
- Tăng/giảm linh hoạt, phù hợp workload biến động.
- Cho phép tách nhóm workload với tài nguyên hoặc SLO khác nhau.

### 3.2. Hạn chế

- Ứng dụng cần xử lý nhiều instance đồng thời.
- State trong bộ nhớ local có thể không dùng chung.
- Cần load balancing, health check, discovery và graceful shutdown.
- Shared database, cache, queue hoặc API có thể trở thành bottleneck mới.
- Thêm node làm tăng network calls, replication traffic và chi phí vận hành.
- Distributed systems có lỗi mới: timeout, retry, duplicate, partial failure và consistency.

Scale-out hiệu quả nhất khi mỗi request hoặc job có thể được xử lý độc lập, hoặc state được quản lý bằng một tầng chuyên biệt phù hợp.

## 4. So sánh scale-up và scale-out

| Tiêu chí | Scale-up | Scale-out |
|---|---|---|
| Cách tăng năng lực | Tăng CPU/RAM/IOPS/bandwidth cho instance | Tăng số instance/worker |
| Thay đổi kiến trúc | Thường ít | Thường cần thiết kế phân phối |
| Giới hạn | Trần cấu hình phần cứng/instance | Giới hạn phân phối, coordination và dependency |
| Failure domain | Có thể tập trung vào một máy lớn | Có thể phân tán qua nhiều instance/zone |
| State | Dễ giữ local state hơn | Cần xử lý state dùng chung hoặc partition |
| Scaling speed | Phụ thuộc thao tác resize và provider | Có thể tự động nhưng cần thời gian khởi động |
| Cost | Máy lớn có thể đắt và kém linh hoạt | Có thể right-size, nhưng thêm network/coordination |
| Use case điển hình | Legacy app, database, workload ít chia được | Web/API stateless, worker, service độc lập |

Không có lựa chọn tuyệt đối. Một hệ thống có thể scale-up database để tăng năng lực một node, scale-out API để phục vụ nhiều request và partition workload batch thành nhiều worker.

## 5. Stateless và stateful: điều kiện quan trọng của scale-out

### 5.1. Stateless application

Một application instance stateless không giữ trạng thái phiên hoặc dữ liệu nghiệp vụ duy nhất trong bộ nhớ local giữa các request. Bất kỳ instance khỏe mạnh nào cũng có thể nhận request tiếp theo nếu có đủ input và truy cập tới nguồn state cần thiết.

Ví dụ:
- Authentication dựa trên token đã ký và được xác minh theo policy.
- Session lưu ở distributed store hoặc client token có kiểm soát.
- Booking data lưu ở database.
- File lưu trong object storage thay vì local disk của container.

~~~mermaid
flowchart LR
    C["Client"] --> LB["Load balancer"]
    LB --> A["Stateless API A"]
    LB --> B["Stateless API B"]
    LB --> C2["Stateless API C"]
    A --> S[("Shared session / database / cache")]
    B --> S
    C2 --> S
~~~

Stateless không có nghĩa ứng dụng không có state; nó có nghĩa state cần dùng giữa các request được lưu ở một nơi phù hợp và không phụ thuộc vào instance cụ thể.

### 5.2. Stateful application

Stateful workload giữ state trong process, disk local hoặc một vai trò cần nhận diện. Ví dụ:
- WebSocket connection hoặc session gắn với một node.
- Database primary/replica.
- Stateful stream processor với partition state.
- Game server giữ trạng thái phiên chơi.
- Worker xử lý một luồng có ordering gắn với partition.

Stateful vẫn có thể scale-out, nhưng cần partition, replication, leader election, state transfer, affinity hoặc storage bền vững. Chi phí coordination và recovery cao hơn.

### 5.3. Sticky session có giải quyết state không?

Sticky session khiến load balancer thường gửi cùng client về cùng instance. Điều này có thể giảm nhu cầu chuyển session giữa node, nhưng:
- Instance chết có thể làm mất state local.
- Scale-in/migration khó hơn.
- Phân phối tải có thể lệch nếu một nhóm client rất hoạt động.
- Không đảm bảo request tới cùng node nếu cookie hết hạn hoặc routing thay đổi.

Sticky session là một kỹ thuật routing, không thay thế thiết kế state bền vững hoặc replication.

## 6. Tìm bottleneck trước khi thêm tài nguyên

Throughput và latency của toàn hệ thống bị giới hạn bởi tầng yếu nhất hoặc tài nguyên bão hòa đầu tiên.

~~~mermaid
flowchart LR
    C["Client"] --> GW["Gateway"]
    GW --> APP["Application"]
    APP --> CACHE["Cache"]
    APP --> DB["Database"]
    APP --> EXT["External API"]
    APP --> Q["Queue"]
    Q --> W["Workers"]
    W --> DB
~~~

Cần đo từng tầng:
- Gateway/load balancer: request rate, connection limit, TLS CPU, queueing.
- Application: CPU, memory, thread pool, connection pool, GC, event loop.
- Cache: hit/miss, hot keys, memory, evictions, network latency.
- Database: CPU, IOPS, locks, slow queries, connection count, replication lag.
- Queue: depth, oldest age, publish/consume rate, retry và DLQ.
- External API: latency, quota, rate limit, error rate.
- Network: bandwidth, packet loss, DNS, cross-zone traffic và connection setup.

### 6.1. CPU bottleneck

Dấu hiệu có thể gồm CPU utilization cao, run queue tăng, request compute-intensive và latency tăng cùng tải. Biện pháp: profile code, tối ưu thuật toán, cache kết quả phù hợp, tăng CPU hoặc thêm replica.

### 6.2. Memory bottleneck

Dấu hiệu gồm memory pressure, GC pause, swap, OOM kill, cache eviction bất thường. Cần phân biệt memory leak, heap quá nhỏ, payload quá lớn và working set tăng. Tăng RAM có thể giúp tạm thời nhưng không sửa leak.

### 6.3. Database bottleneck

Ứng dụng nhiều replica có thể tạo quá nhiều connection và query vào một database. Cần kiểm tra query plan, index, lock contention, pool size, read/write ratio và storage IOPS. Biện pháp có thể là tối ưu query, connection pooling, cache phù hợp, read replica, partitioning hoặc thay đổi mô hình ghi.

### 6.4. Network hoặc external dependency bottleneck

Tăng app instance không giúp nếu external API có quota cố định hoặc network hop chiếm phần lớn latency. Cần batching, connection reuse, asynchronous processing, rate limiting, circuit breaker và thỏa thuận capacity với provider.

## 7. Capacity planning và headroom

Capacity planning ước lượng tài nguyên cần thiết để đáp ứng tải hiện tại, tăng trưởng và tình huống lỗi.

Ví dụ đơn giản:
- Một replica Booking API xử lý ổn định 200 request/giây tại SLO p95.
- Peak dự kiến là 1.200 request/giây.
- Mục tiêu vận hành ở tối đa 70% năng lực benchmark để có headroom.

Năng lực mỗi replica dùng trong tính toán:

\[
200 \times 0.70 = 140\ requests/s
\]

Số replica ước lượng:

\[
N = \lceil 1200 / 140 \rceil = 9
\]

Cần thêm capacity cho failure scenario. Nếu muốn vẫn đáp ứng peak khi mất một replica, phải có ít nhất 10 replica theo mô hình đơn giản, hoặc tính chính xác theo phân phối và autoscaling policy. Benchmark cần được đo trên cùng model, kích thước request, feature dependency và cấu hình production-like.

### 7.1. Những yếu tố capacity plan cần có

- Baseline, average và peak traffic.
- Burst rate và tốc độ tăng tải.
- Request/job mix và tài nguyên mỗi loại.
- SLO latency/error/availability.
- Resource utilization mục tiêu và headroom.
- Thời gian phát hiện, scale và warm-up.
- Capacity khi mất node/zone.
- Quota cloud và thời gian cấp tài nguyên.
- Dự báo tăng trưởng theo tenant, region hoặc mùa vụ.
- Ngân sách và giới hạn cost.

### 7.2. Không dùng utilization làm mục tiêu duy nhất

CPU 90% có thể là dấu hiệu saturation, nhưng CPU 30% không chứng minh hệ thống còn dư tải nếu database connection pool đã cạn. Theo dõi utilization cùng latency, queueing, errors, throughput và dependency metrics.

## 8. Queueing và lý do latency tăng nhanh gần saturation

Khi tải tiến gần năng lực phục vụ, request phải xếp hàng chờ. Latency có thể tăng nhanh hơn mức tăng traffic.

Một mô hình đơn giản của hệ thống queue:
- Arrival rate: tốc độ request đến.
- Service rate: tốc độ hệ thống xử lý.
- Utilization: tỷ lệ nhu cầu so với năng lực phục vụ.

\[
\rho = \frac{\lambda}{\mu}
\]

Trong đó lambda là arrival rate và mu là service rate trong mô hình một server. Khi rho tiến gần 1, thời gian chờ có thể tăng mạnh; khi lambda vượt mu trong thời gian dài, queue tiếp tục lớn lên.

Ví dụ, worker xử lý 100 job/giây và nhận 95 job/giây có ít headroom hơn nhiều so với trường hợp nhận 50 job/giây. Một burst ngắn có thể được queue hấp thụ, nhưng nếu tốc độ đến luôn cao hơn tốc độ xử lý, backlog sẽ không tự giảm.

Cần:
- Đặt queue depth/oldest age alert.
- Có backpressure hoặc admission control.
- Giới hạn concurrency và batch size.
- Scale worker dựa trên queue depth/age khi phù hợp.
- Đặt retry budget để tránh retry amplification.
- Xác định hành động khi backlog vượt thời gian nghiệp vụ cho phép.

## 9. Autoscaling: tăng giảm tài nguyên theo nhu cầu

Autoscaling tự động điều chỉnh số instance hoặc tài nguyên dựa trên metric và policy.

### 9.1. Metric-driven scaling

Các tín hiệu thường dùng:
- CPU/memory utilization.
- Request per second hoặc active connections.
- Request concurrency và latency.
- Queue depth/oldest message age.
- Custom metric như jobs outstanding hoặc GPU utilization.
- Schedule cho tải có tính chu kỳ.

Không phải metric nào cũng phù hợp cho mọi workload. CPU-based scaling có thể phản ứng kém nếu app chờ database; queue-based scaling phù hợp worker bất đồng bộ hơn; latency-based scaling cần cẩn thận vì latency là chỉ số trễ và có thể tăng sau khi hệ thống đã bão hòa.

### 9.2. Scale-out và scale-in

Scale-out phải tính thời gian:
1. Metric vượt ngưỡng.
2. Autoscaler phát hiện.
3. Cloud cấp compute.
4. Instance tải container/image.
5. Runtime khởi động và nạp config/model.
6. Health/readiness check thành công.
7. Load balancer đưa traffic vào.

Nếu quá trình này mất 2 phút, traffic burst trong 20 giây cần baseline capacity hoặc queue để hấp thụ.

Scale-in cần graceful:
- Ngừng nhận request mới.
- Hoàn thành hoặc chuyển giao request/job đang chạy.
- Drain connection.
- Gỡ node khỏi load balancer.
- Chỉ terminate sau khi an toàn.

Scale-in quá nhanh gây connection reset, job duplicate hoặc mất state.

### 9.3. Cooldown, stabilization và hysteresis

Nếu ngưỡng scale-out/scale-in quá nhạy, hệ thống dao động liên tục. Dùng cooldown/stabilization window, nhiều mẫu metric, khác ngưỡng tăng và giảm hoặc policy giới hạn tốc độ. Tránh scale-in ngay sau một đợt burst nếu backlog hoặc latency chưa ổn định.

## 10. Database scaling: giới hạn thường xuất hiện sau application tier

Thêm application replica làm tăng khả năng nhận request nhưng cũng làm tăng connection và query. Database thường là tầng khó scale ngang hơn application.

Một số lựa chọn:

| Kỹ thuật | Mục tiêu | Đánh đổi |
|---|---|---|
| Vertical scale database | Tăng CPU/RAM/IOPS một node | Giới hạn instance, chi phí và failure domain |
| Connection pooling | Giảm số connection vật lý | Pool quá nhỏ tạo queue, quá lớn gây áp lực DB |
| Read replica | Phân phối read workload | Replication lag và eventual consistency |
| Caching | Giảm query lặp | Staleness, invalidation và cache failure |
| Partitioning | Chia dữ liệu/khối lượng theo key | Query cross-partition và vận hành phức tạp |
| Sharding | Phân tán dữ liệu qua nhiều database | Routing, rebalancing, transaction và join khó hơn |
| CQRS/materialized view | Tối ưu read model theo use case | Eventual consistency và thêm pipeline |

Không thêm read replica rồi mặc định tất cả read có thể chuyển sang đó. Một số thao tác cần read-after-write hoặc dữ liệu authoritative phải đọc primary hoặc cơ chế đồng bộ phù hợp.

### 10.1. Sharding và chọn partition key

Partition key cần phân phối tải đủ đều, hỗ trợ query chính và tránh hot partition. Ví dụ sharding theo tenant có thể phù hợp nếu tenant phân bố cân bằng, nhưng một tenant rất lớn có thể trở thành hotspot. Sharding theo thời gian có thể giúp retention và range scan nhưng dữ liệu mới dồn về partition hiện hành.

Cần xem:
- Cardinality và phân bố key.
- Query cần truy cập một hay nhiều partition.
- Join, transaction và uniqueness constraint.
- Rebalancing khi thêm shard.
- Cross-shard reporting và backup/restore.
- Data locality và tenant isolation.

## 11. Cache, replication và partitioning ở các tầng khác

Scaling hiếm khi là thao tác riêng ở application. Các tầng khác cũng có giới hạn.

### Cache
- Scale-up memory/cache node có thể tăng working set.
- Scale-out cache cluster có thể phân vùng key nhưng thêm routing và replication.
- Hot key có thể quá tải một shard dù tổng cluster còn rảnh.
- Cache stampede có thể khiến database chịu tải đột biến khi cache miss.

### Object storage
Object storage thường mở rộng dung lượng và request rate theo khả năng dịch vụ, nhưng vẫn có quota, request pattern, prefix/partition behavior, egress và lifecycle. Cần kiểm tra giới hạn thực tế của provider, không giả định vô hạn.

### Queue và event streaming
Tăng consumer chỉ có ích khi queue/partition có thể phân phối thêm công việc. Với partitioned stream, số consumer hoạt động song song thường bị giới hạn bởi số partition hoặc ordering key. Tăng partition có thể cần migration và làm thay đổi ordering semantics.

### External API
Nếu provider giới hạn 500 request/giây, scale-out client lên 20 replica không làm provider nhận được nhiều hơn mức quota; nó có thể chỉ làm 429 tăng. Dùng rate limiter chung, queue, batching, caching hợp lệ và capacity negotiation.

## 12. Distributed coordination và giới hạn scale-out

Khi có nhiều instance, một số nhiệm vụ cần phối hợp:
- Leader election cho công việc chỉ có một executor.
- Distributed lock để điều phối thao tác có xung đột.
- Idempotency để chống xử lý lặp.
- Consensus hoặc quorum cho state có yêu cầu mạnh.
- Replication và conflict resolution cho dữ liệu nhiều nơi.

Coordination thêm latency và failure mode. Distributed lock có thể hết hạn trong khi tiến trình cũ vẫn chạy; lease/fencing token cần được cân nhắc cho tài nguyên quan trọng. Không dùng lock để thay thế thiết kế dữ liệu có thể phân vùng hoặc xử lý idempotent.

Một hệ thống có thể scale tốt hơn nếu giảm coordination:
- Chia công việc theo tenant hoặc aggregate key.
- Dùng partition ownership rõ.
- Thiết kế thao tác độc lập và idempotent.
- Chấp nhận eventual consistency ở phần nghiệp vụ cho phép.
- Tổng hợp kết quả bất đồng bộ thay vì dùng transaction xuyên nhiều service.

## 13. Resilience, availability và failure domains

Scale-out có thể tăng availability nếu instance phân bố trên nhiều failure domain và ứng dụng chịu được việc mất một phần capacity.

Cần xem:
- Replica có nằm trên nhiều availability zone không?
- Load balancer có health check và drain không?
- Database/cache/queue có cùng failure domain với app không?
- Khi mất zone, capacity còn lại có phục vụ tải tối thiểu không?
- Autoscaler có phụ thuộc control plane hoặc quota ở zone bị lỗi không?
- Có degradation mode khi thiếu tài nguyên không?

Một cụm 10 replica cùng nằm trên một node hoặc một zone không tương đương với 10 replica trải trên nhiều failure domain. Tuy nhiên, phân tán zone tạo thêm latency và chi phí network; cần cân bằng với SLO và data consistency.

### N+1 capacity

Nếu hệ thống cần N replica để đáp ứng peak, có thể provision thêm một hoặc nhiều replica để vẫn phục vụ khi một instance lỗi. Nhưng N+1 chỉ có ý nghĩa nếu các tầng khác cũng có đủ capacity. Nếu database chỉ đủ xử lý peak khi mọi app replica hoạt động, mất một zone và retry có thể làm DB quá tải.

Cần kiểm thử failure scenario thực tế, không chỉ dựa trên số replica.

## 14. Security khi scale-out

Tăng số instance làm tăng số workload identity, network endpoint và nơi chứa cấu hình/secret. Bảo mật phải mở rộng cùng hệ thống:

- Mỗi workload hoặc nhóm workload dùng identity riêng với least privilege.
- Secret lấy từ secret manager hoặc cơ chế cấp phát an toàn, không nhúng trong image.
- Network policy giới hạn luồng giữa tier.
- TLS/mTLS khi yêu cầu xác thực peer và bảo vệ dữ liệu.
- Autoscaling group/pod template dùng image đã kiểm soát và artifact provenance.
- Log/metric không ghi PII, token hoặc secret.
- Quota/rate limit chống abuse khi autoscaling làm tăng khả năng nhận request.
- Scale-to-zero và scale-in phải xóa hoặc thu hồi credential/session local theo đúng vòng đời.

Không để mỗi replica mới tự động nhận quyền rộng hơn chỉ vì việc cấp quyền thủ công khó quản lý. Dùng policy và identity automation có kiểm soát.

## 15. Chi phí và right-sizing

Scale-up và scale-out có cost profile khác nhau:
- Máy lớn hơn có thể tăng giá nhanh theo cấu hình.
- Nhiều máy nhỏ tạo overhead về network, load balancing, logging và orchestration.
- Giữ baseline cao để tránh cold start làm tăng idle cost.
- Autoscaling quá nhạy gây churn, warm-up và phí tài nguyên.
- Cross-zone/region traffic và replication có thể làm tăng chi phí.
- Database read replica/shard tăng storage, backup và operations.
- Capacity dự phòng cho failure scenario cần tính vào ngân sách.

Nên theo dõi:
- Cost per request/job hoặc per successful transaction.
- Cost theo tenant/workload.
- Average và peak utilization.
- Idle capacity và thời gian scale-to-zero.
- Network egress/cross-zone transfer.
- Database cost trên mỗi query/transaction.
- Chi phí lỗi, retry, backlog và overprovisioning.

Tối ưu không đồng nghĩa duy trì CPU ở 95%. Nếu mức utilization cao làm tăng tail latency và lỗi, cost mỗi request thành công có thể tăng. Right-sizing nên dựa trên SLO và cost per successful unit of work.

## 16. Quy trình đánh giá và lựa chọn chiến lược scaling

Một review có thể đi theo thứ tự:

1. **Định nghĩa nhu cầu:** xác định baseline, peak, burst, tăng trưởng và các SLO.
2. **Đo hiện trạng:** throughput, latency phân vị, error, queue age và utilization từng tầng.
3. **Tìm bottleneck:** xác định tài nguyên hoặc dependency giới hạn trước khi thêm capacity.
4. **Kiểm tra giới hạn instance:** xem có thể scale-up trong trần cấu hình và downtime chấp nhận được không.
5. **Đánh giá scale-out:** request/job có độc lập không? State đang nằm đâu? Cần partition hoặc coordination gì?
6. **Đánh giá dependency:** database, cache, queue, network và external API có chịu tải tăng không?
7. **Tính capacity/headroom:** benchmark mỗi replica, failure scenario, warm-up và cloud quota.
8. **Thiết kế autoscaling:** chọn metric, threshold, cooldown, min/max, scale-in và graceful drain.
9. **Thiết kế resilience/security:** nhiều failure domain, identity, network policy, fallback và recovery.
10. **So sánh cost:** cost per request, idle capacity, data transfer và vận hành.
11. **Thử nghiệm:** load test, burst test, scale event, mất node/zone và dependency failure.
12. **Ghi ADR:** lựa chọn, giới hạn đã biết, giả định, owner và điều kiện xem xét lại.

### Ma trận quyết định nhanh

| Tình huống | Hướng cân nhắc ban đầu |
|---|---|
| CPU của một instance cao, app khó phân tán và còn trần cấu hình | Scale-up sau khi profile |
| Web/API stateless, traffic tăng và request độc lập | Scale-out sau load balancer |
| Worker xử lý queue với backlog tăng | Scale consumer theo queue depth/age, có giới hạn downstream |
| DB query/lock là bottleneck | Tối ưu query/index/pool trước; sau đó xem replica/partition |
| External provider đạt quota | Rate limit, queue, batch hoặc thương lượng quota; không chỉ thêm replica |
| Một key/partition nhận phần lớn tải | Xử lý hot key/partition và thiết kế lại distribution |
| Tải có chu kỳ dễ dự báo | Scheduled/pre-scaling kết hợp autoscaling |
| Tải hiếm, không có SLO latency gắt | Scale-to-zero hoặc batch có thể phù hợp |
| State local gắn với instance | Externalize state hoặc thiết kế partition/failover trước scale-out |

## 17. ADR minh họa — Mở rộng Booking API

> **Bối cảnh:** Booking API chạy một VM 4 vCPU, 8 GB RAM. Khi chiến dịch khuyến mại, traffic tăng từ 150 lên 900 request/giây. CPU đạt 95%, p95 tăng mạnh; database connection và query latency cũng tăng.
>
> **Phương án A:** Nâng VM lên 16 vCPU, 32 GB. Có thể tạo headroom nhanh, ít thay đổi ứng dụng, nhưng vẫn là một failure domain và không giải quyết giới hạn database nếu query/pool là nguyên nhân.
>
> **Phương án B:** Chạy nhiều API replica sau load balancer, giữ app stateless và giới hạn connection tổng tới database. Thêm query optimization, pooler và read replica cho các read phù hợp.
>
> **Quyết định minh họa:** Profile trước để tách thời gian CPU khỏi database wait. Nếu CPU thực sự là bottleneck, nâng instance tạm thời để ổn định rồi scale-out API. Đặt max replica theo capacity database, không scale vô hạn.
>
> **Autoscaling:** Scale-out theo request concurrency/CPU có giới hạn; scale-in chậm hơn và drain request đang xử lý.
>
> **Resilience:** Phân replica qua nhiều zone; kiểm thử còn đủ capacity khi mất một replica/zone. Booking write vẫn qua transaction/authoritative database.
>
> **Kiểm chứng:** Load test 900 request/giây, đo p95/p99, DB connections, query latency, error, cost/request và test mất một zone.
>
> **Điều kiện xem xét lại:** Nếu database vẫn là bottleneck sau tối ưu và replica, xem partitioning/sharding hoặc thay đổi mô hình đọc/ghi.

## 18. Bài tập thực hành: tìm giới hạn trước khi scale

Một nền tảng đặt chỗ có kiến trúc:
- API chạy trên 2 container.
- Redis dùng làm cache/session.
- Một relational database primary.
- Notification Worker đọc từ queue.
- Payment provider có quota 300 request/giây.

Khi traffic tăng gấp bốn lần:
- API CPU lên 85%.
- p95 tăng từ 120 ms lên 900 ms.
- Database connections đạt giới hạn.
- Cache hit ratio giảm từ 92% xuống 60%.
- Queue oldest age tăng.
- Payment provider trả nhiều HTTP 429.

**Yêu cầu:**
1. Xếp hạng bottleneck có khả năng cao và xác định phép đo bổ sung cần thu thập.
2. Nêu việc nào có thể giải quyết bằng scale-up, việc nào cần scale-out hoặc thay đổi kiến trúc.
3. Thiết kế giới hạn tổng database connections khi thêm API replica.
4. Đề xuất cache investigation cho hit ratio giảm và khả năng cache stampede.
5. Thiết kế autoscaling worker theo queue depth/oldest age.
6. Xử lý payment quota bằng rate limiting, queue hoặc batching.
7. Tính capacity/headroom và failure scenario cho API.
8. Đề xuất load test và kiểm thử mất một instance/zone.

### Hướng giải quyết

- CPU 85% là một tín hiệu nhưng database connections đã đạt giới hạn và p95 tăng mạnh; cần trace từng request, query plan, pool wait, DB CPU/locks/IO và cache miss path để xác định đóng góp latency.
- Thêm API replica trước khi giới hạn connection có thể làm DB quá tải hơn. Tính tổng connection: số replica × pool tối đa, cộng worker/admin/replication và headroom; dùng connection pooler và giới hạn toàn hệ thống.
- Cache hit ratio giảm có thể do key cardinality, working set mới, TTL đồng loạt, hot key, cache eviction hoặc invalidation; kiểm tra theo namespace/endpoint trước khi tăng cache node.
- Queue worker scale theo oldest age/queue depth, nhưng đặt max concurrency theo database và provider capacity; xử lý poison message và retry có giới hạn.
- Với payment provider quota 300 request/giây, dùng rate limiter phân tán hoặc token bucket chung; queue request nếu nghiệp vụ cho phép, tôn trọng 429/Retry-After và idempotency key. Thêm replica không làm quota tăng.
- API capacity dựa trên benchmark mỗi replica tại latency mục tiêu, peak traffic và headroom; tính trường hợp mất replica/zone và thời gian autoscale.
- Load test có warm-up, ramp, burst, soak và dependency fault; đo p95/p99, errors, DB connections, queue age, cache hit, payment throttle và cost.

### Câu hỏi tự kiểm tra

1. Scale-up và scale-out khác nhau thế nào về giới hạn và failure domain?
2. Vì sao thêm application replica có thể làm database chậm hơn?
3. Stateless application cần externalize những loại state nào?
4. Sticky session có bảo đảm không mất session khi instance lỗi không?
5. Vì sao utilization thấp không chứng minh hệ thống còn capacity?
6. Queueing làm latency tăng ra sao khi arrival rate tiến gần service rate?
7. Autoscaling cần tính những giai đoạn nào trước khi replica nhận traffic?
8. Khi nào read replica phù hợp và khi nào replication lag làm nó không an toàn?
9. Vì sao số consumer có thể bị giới hạn bởi partition count trong stream?
10. Làm sao xác định capacity cần thiết khi mất một availability zone?
11. Vì sao retry và autoscaling cùng lúc có thể tạo retry amplification?
12. Metric nào giúp quyết định nên scale-up, scale-out hay tối ưu bottleneck trước?

Một kiến trúc mở rộng tốt không chỉ tăng CPU hoặc số replica. Nó phải **xác định đúng bottleneck, phân phối được công việc, quản lý state và dependency, duy trì headroom trong failure scenario và chứng minh chi phí trên mỗi đơn vị công việc vẫn hợp lý**. Scale-up là công cụ đơn giản để tăng năng lực một node; scale-out mở rộng qua nhiều instance nhưng đòi hỏi thiết kế phân tán. Lựa chọn đúng bắt đầu từ phép đo, workload profile và SLO, sau đó được xác minh bằng load test và diễn tập lỗi.
