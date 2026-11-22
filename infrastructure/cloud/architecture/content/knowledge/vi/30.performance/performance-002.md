# Thông lượng, mức đồng thời, độ trễ và quan hệ hàng đợi

## 1. Bốn đại lượng mô tả hiệu năng hệ thống

Khi đánh giá một dịch vụ cloud, cần hiểu hệ thống xử lý được bao nhiêu công việc, có bao nhiêu công việc đang chạy cùng lúc, mỗi công việc mất bao lâu và công việc phải chờ bao lâu trước khi được xử lý. Bốn khái niệm liên kết chặt chẽ:

- **Throughput (thông lượng):** tốc độ hệ thống hoàn thành công việc trong một đơn vị thời gian, ví dụ request/second, transaction/second hoặc message/second.
- **Concurrency (mức đồng thời):** số công việc đang được xử lý hoặc đang tồn tại trong hệ thống tại cùng một thời điểm, tùy cách đo.
- **Latency (độ trễ):** thời gian từ khi một operation bắt đầu tới khi kết quả tương ứng được trả về hoặc công việc hoàn tất.
- **Queue (hàng đợi):** nơi giữ công việc đang chờ tài nguyên hoặc bước xử lý tiếp theo.

Queue có thể giúp hấp thụ burst và tách tốc độ producer khỏi consumer. Tuy nhiên, queue không tạo ra capacity vô hạn. Khi tốc độ đến vượt tốc độ xử lý trong thời gian dài, backlog và thời gian chờ tăng. Một hệ thống có throughput cao vẫn có thể có latency rất xấu nếu số request chờ tăng nhanh.

Trong module **CLOUD_ARCHITECTURE**, chương **Hiệu năng** xem các đại lượng này như một hệ thống quan hệ. Quyết định về compute, database, network, cache và worker cần dựa trên workload, SLO, giới hạn tài nguyên và hành vi khi tải tăng.

Sau bài học, người học có thể:

1. Phân biệt throughput, concurrency, latency, queue depth và queue wait.
2. Áp dụng định luật Little để ước lượng số công việc đồng thời.
3. Giải thích ảnh hưởng của utilization, service time và arrival rate đến thời gian chờ.
4. Phân tích queue backlog, drain time và điểm mất ổn định.
5. Chọn concurrency limit, worker count, connection pool và queue policy.
6. Thiết kế backpressure, admission control, timeout và retry budget.
7. Đọc p50/p95/p99, phát hiện tail latency và saturation.
8. Xây dựng workload model và kiểm thử hiệu năng có thể lặp lại.

## 2. Định nghĩa chính xác trước khi đo

Các số liệu chỉ có ý nghĩa khi xác định ranh giới đo.

| Đại lượng | Câu hỏi | Đơn vị thường dùng |
| --- | --- | --- |
| Arrival rate (λ) | Bao nhiêu công việc đến mỗi giây? | requests/s, messages/s |
| Throughput (X) | Bao nhiêu công việc hoàn thành mỗi giây? | requests/s, jobs/s |
| Concurrency (L) | Có bao nhiêu công việc đang ở trong hệ thống? | requests, jobs, sessions |
| Response time (W) | Một công việc ở trong hệ thống bao lâu? | ms, s |
| Service time (S) | Tài nguyên thực sự xử lý công việc bao lâu? | ms, s |
| Queue depth (Q) | Có bao nhiêu công việc đang chờ? | messages, jobs |
| Queue wait (Wq) | Công việc chờ bao lâu trước khi service bắt đầu? | ms, s |
| Utilization (U) | Tài nguyên bận bao nhiêu phần thời gian/capacity? | ratio, % |

Throughput không nhất thiết bằng arrival rate. Trong hệ thống ổn định dài hạn, throughput có thể gần arrival rate nếu không drop, reject hoặc tích lũy backlog. Khi tải vượt capacity, throughput thường chạm trần trong khi arrival rate tiếp tục tăng.

Latency cần nói rõ điểm bắt đầu và kết thúc: từ client gửi request tới nhận response, từ gateway tới service, hay chỉ thời gian xử lý trong database. Không so sánh các con số có measurement boundary khác nhau.

## 3. Định luật Little

Định luật Little liên hệ số công việc trung bình trong một hệ thống ổn định với throughput trung bình và thời gian trung bình một công việc ở trong hệ thống:

```text
L = λ × W

L: average number of items in the system
λ: average throughput / arrival rate in steady state
W: average time in the system
```

Ví dụ hệ thống hoàn thành 200 request/s và mỗi request ở trong hệ thống trung bình 0,25 giây:

```text
L = 200 requests/s × 0.25 s
  = 50 requests
```

Trung bình có khoảng 50 request đang tồn tại trong hệ thống. Đây là concurrency trung bình theo ranh giới đã chọn, không phải số thread hay số connection cần cấu hình trực tiếp.

### 3.1. Điều kiện áp dụng

Định luật Little áp dụng cho một hệ thống ổn định trong khoảng quan sát phù hợp, với định nghĩa flow nhất quán:
- Hệ thống không tích lũy backlog vô hạn trong khoảng tính.
- Arrival và departure được đo trên cùng population.
- Time in system tính từ lúc item vào đến lúc item rời cùng boundary.
- Dùng giá trị trung bình trên cùng cửa sổ đo.

Nếu arrival rate đang tăng và backlog liên tục phình ra, lấy λ nhân W tại một thời điểm ngắn có thể không mô tả trạng thái ổn định. Công thức vẫn là quan hệ dòng chảy, nhưng cần cẩn thận với cửa sổ đo và transient behavior.

### 3.2. Tính ngược các đại lượng

```text
Throughput: λ = L / W
Time in system: W = L / λ
Average concurrency: L = λ × W
```

Nếu chỉ có giới hạn concurrency và latency budget, có thể ước lượng throughput trung bình khả thi theo L/W. Đây là ước lượng theo quan hệ trung bình; chưa xét CPU, I/O, lock, fan-out hoặc service capacity.

## 4. Tách queue wait và service time

Response time của một operation có thể gồm nhiều thành phần:

```text
Response time =
    queue wait
  + service processing
  + downstream wait
  + network / serialization / scheduling overhead
```

Trong một worker queue đơn giản:

```text
W = Wq + S

Wq: time waiting before service
S: service time after a worker starts
```

Ví dụ job mất 120 ms để xử lý nhưng chờ 1,8 giây trong queue. Tối ưu thuật toán giảm service time từ 120 xuống 80 ms chỉ cải thiện một phần nhỏ; vấn đề chính nằm ở queue wait hoặc consumer capacity.

Phải đo từng thành phần bằng trace/span hoặc queue telemetry thay vì chỉ nhìn end-to-end latency.

## 5. Arrival rate, service rate và điều kiện ổn định

Gọi:
- λ là tốc độ công việc đến.
- μ là tốc độ một worker xử lý công việc.
- c là số worker hoạt động song song.

Capacity xử lý lý thuyết:

```text
Service capacity ≈ c × μ
```

Trong mô hình đơn giản với worker tương đương, hệ thống có thể xử lý ổn định khi λ nhỏ hơn tổng service capacity. Nếu λ lớn hơn capacity trong thời gian dài, backlog tăng xấp xỉ theo phần chênh lệch.

```text
Backlog growth rate ≈ λ - c × μ
when λ > c × μ
```

Ví dụ producer đưa 500 job/s, mỗi worker xử lý 100 job/s và có 4 worker:

```text
Total service capacity = 4 × 100 = 400 jobs/s
Backlog growth = 500 - 400 = 100 jobs/s
```

Sau 10 phút, trong điều kiện đơn giản và không có drop/scale/retry, backlog tăng khoảng 60.000 job. Queue chỉ trì hoãn thời điểm quá tải nếu thiếu capacity kéo dài.

## 6. Utilization và thời gian chờ

Utilization đo tỷ lệ capacity đang được sử dụng. Với mô hình lý tưởng có c worker giống nhau:

```text
ρ = λ / (c × μ)

ρ: utilization ratio
```

Khi ρ tiến gần 1, hệ thống ít capacity trống để hấp thụ biến động. Queue wait có thể tăng nhanh dù throughput chỉ tăng một ít. Vì arrival và service time biến động, vận hành gần 100% utilization thường làm tail latency xấu đi.

### 6.1. Ví dụ trực quan

Một worker có capacity 100 jobs/s:
- Tải 50 jobs/s: còn dư nhiều capacity cho burst.
- Tải 80 jobs/s: utilization 80%, ít headroom hơn.
- Tải 98 jobs/s: utilization 98%, một burst nhỏ hoặc job chậm có thể tạo queue dài.
- Tải 110 jobs/s kéo dài: backlog tăng vì arrival lớn hơn service capacity.

Không có một utilization threshold đúng cho mọi hệ thống. Database, CPU-bound service, network I/O và queue worker có đặc tính khác nhau. Đặt ceiling từ load test và SLO thay vì áp dụng một tỷ lệ chung.

### 6.2. Service time variability

Khi service time có độ biến thiên lớn, một số job chậm giữ worker lâu hơn, làm job phía sau phải chờ. Hai hệ thống có cùng average service time nhưng variance khác nhau có thể có queue latency rất khác.

Cần xem phân phối service time, không chỉ average. Heavy-tailed workload, lock contention, garbage collection, cold cache và downstream timeout đều làm tăng tail behavior.

## 7. Mô hình hàng đợi và trực giác M/M/1

M/M/1 là mô hình hàng đợi cơ bản với:
- Arrival theo Poisson process.
- Service time phân phối exponential.
- Một server/worker.
- Hệ thống ổn định khi λ < μ.

Trong mô hình này:

```text
ρ = λ / μ

Average time in system:
W = 1 / (μ - λ)

Average number in system:
L = λ / (μ - λ)

Average queue wait:
Wq = ρ / (μ - λ)
```

Ví dụ μ = 100 jobs/s.

| Arrival rate λ | Utilization ρ | Average time in system W |
| ---: | ---: | ---: |
| 50 jobs/s | 50% | 20 ms |
| 80 jobs/s | 80% | 50 ms |
| 90 jobs/s | 90% | 100 ms |
| 95 jobs/s | 95% | 200 ms |
| 99 jobs/s | 99% | 1 s |

Bảng cho thấy khi utilization tiến sát 100%, thời gian trung bình trong hệ thống tăng phi tuyến trong mô hình. Đây là trực giác hữu ích, không phải công thức dự báo trực tiếp cho mọi service production.

### 7.1. M/M/c và giới hạn mô hình

Với nhiều worker, queueing behavior phụ thuộc số server, phân phối arrival/service và scheduler. M/M/c có thể dùng để ước lượng xác suất phải chờ và queueing delay trong giả định đơn giản.

Hệ thống thực tế thường có:
- Nhiều loại request với cost khác nhau.
- Worker pool tách biệt.
- Downstream dependency.
- Batch processing.
- Retry và timeout.
- Rate limit và admission control.
- Autoscaling có delay.

Dùng queueing model để đặt giả thuyết, sau đó kiểm chứng bằng workload test và telemetry thực tế.

## 8. Concurrency không đồng nghĩa số thread

Concurrency mô tả số operation đang tồn tại/được tiến hành cùng lúc. Thread count là một cách triển khai cụ thể, không phải định nghĩa concurrency.

Một runtime asynchronous có thể duy trì nhiều request đang chờ I/O trên ít thread. Ngược lại, nhiều thread có thể tồn tại nhưng phần lớn đang idle hoặc tranh chấp lock.

Cần phân biệt:
- **In-flight requests:** request đã được nhận nhưng chưa hoàn tất.
- **Active execution:** request đang dùng CPU hoặc worker.
- **Waiting operations:** request đang chờ database, network, lock hoặc queue.
- **Open connections:** kết nối tồn tại, không nhất thiết đang xử lý.
- **Threads/tasks:** đơn vị thực thi do runtime quản lý.

Không tăng thread count chỉ để xử lý concurrency cao. Nếu bottleneck là database connections hoặc downstream quota, thêm thread có thể làm contention và memory tăng.

## 9. Latency distribution và tail latency

Average latency có thể che giấu trải nghiệm xấu của một nhóm request. Nên theo dõi percentile:

- **p50:** median, một nửa request nhanh hơn hoặc bằng giá trị này.
- **p90/p95:** phần lớn request hoàn tất trong khoảng này; hữu ích cho SLO.
- **p99/p99.9:** tail, thể hiện trải nghiệm của nhóm request chậm nhất.
- **Max:** dễ bị ảnh hưởng bởi outlier và số lượng mẫu; không nên dùng đơn lẻ.

Ví dụ:

| Metric | API search |
| --- | ---: |
| p50 | 45 ms |
| p95 | 180 ms |
| p99 | 1.4 s |
| Max | 4.8 s |

Median tốt nhưng p99 cao có thể cho thấy hot partition, GC pause, lock, retry, cache miss hoặc downstream tail latency.

### 9.1. Percentile không cộng đơn giản

Nếu một request gọi nhiều service nối tiếp, end-to-end latency là tổng các thành phần theo từng request. Không thể cộng p99 của service A với p99 của service B rồi coi đó là p99 end-to-end vì các percentile có thể đến từ những request khác nhau.

Dùng distributed tracing hoặc histogram end-to-end để biết request thực tế đi qua đường nào và thành phần nào tạo tail.

### 9.2. Coordinated omission

Load generator có thể gửi request mới sau khi request trước hoàn thành. Khi hệ thống chậm, generator tự giảm offered load và bỏ qua thời điểm đáng lẽ phải gửi request; latency report vì thế đánh giá thấp tail.

Dùng open-loop hoặc schedule-aware load generation khi cần mô phỏng arrival rate độc lập với response, đồng thời kiểm soát để load generator không trở thành bottleneck.

## 10. Queue depth, queue age và queue wait

Queue depth là số item đang chờ. Nhưng depth không tự cho biết thời gian phải chờ vì service rate và kích thước công việc khác nhau.

Cần theo dõi:
- Queue depth/backlog.
- Oldest message age.
- Enqueue rate và dequeue/completion rate.
- Processing duration.
- Retry count và visibility timeout.
- Dead-letter queue depth.
- Estimated drain time.
- Per-tenant hoặc per-priority backlog khi phù hợp.

### 10.1. Queue age thường gần trải nghiệm hơn

Một queue có 10.000 message và consumer xử lý 20.000/s có thể drain nhanh. Queue khác có 100 message nhưng mỗi message mất 30 giây mới xử lý; message cũ nhất vẫn có thể chờ lâu.

Đối với deadline nghiệp vụ, oldest age và estimated wait thường quan trọng hơn depth đơn lẻ.

## 11. Tính thời gian drain backlog

Nếu backlog có B items, arrival rate ổn định λ và tổng service capacity μ_total, với μ_total > λ:

```text
Net drain rate = μ_total - λ

Approximate drain time = B / (μ_total - λ)
```

Ví dụ queue có 90.000 jobs, producer vẫn gửi 100 jobs/s và workers xử lý tổng cộng 400 jobs/s:

```text
Net drain rate = 400 - 100 = 300 jobs/s

Drain time = 90,000 / 300
           = 300 seconds
           = 5 minutes
```

Nếu producer dừng hoàn toàn, drain time gần B/μ_total. Nếu processing rate không lớn hơn arrival rate, backlog không drain.

Đây là ước lượng khi rates ổn định và job có cost gần nhau. Với nhiều priority, retry, batch và service time biến động, cần mô phỏng hoặc đo thực tế.

## 12. Backpressure và admission control

**Backpressure** là cơ chế truyền tín hiệu hoặc giới hạn tốc độ khi downstream không thể nhận thêm công việc. **Admission control** quyết định request nào được phép vào hệ thống dựa trên capacity, priority và policy.

Các biện pháp:
- Bounded queue thay queue vô hạn.
- Giới hạn in-flight requests và worker concurrency.
- Rate limit theo client/tenant/route.
- Trả 429/503 có retry guidance phù hợp.
- Queue producer theo quota hoặc demand.
- Ưu tiên critical workload và trì hoãn best-effort.
- Load shedding khi latency/queue vượt ngưỡng.
- Circuit breaker tránh gửi tiếp tới dependency đang lỗi.

Queue vô hạn thường biến overload thành latency và memory exhaustion muộn hơn. Bounded queue làm hệ thống từ chối sớm và rõ ràng hơn, bảo vệ phần còn lại.

### 12.1. Bounded queue

Chọn queue capacity dựa trên:
- Thời gian chờ tối đa nghiệp vụ chấp nhận.
- Tốc độ consumer và peak arrival.
- Memory/disk budget của mỗi item.
- Khả năng durable persistence.
- Thời gian dự kiến để khôi phục consumer.

Không chọn queue size chỉ vì “càng lớn càng an toàn”. Queue rất lớn có thể giữ công việc lâu hơn deadline và tạo backlog khó drain sau recovery.

## 13. Timeout, retry và retry amplification

Timeout giới hạn thời gian chờ; retry thử lại operation thất bại. Kết hợp sai có thể làm tải tăng đúng lúc downstream đang quá tải.

Ví dụ một request gọi ba tầng, mỗi tầng tự retry ba lần có thể nhân số lần gọi lên nhiều lần ở downstream. Thực tế cần xác định retry budget tổng, không chỉ max retries ở từng service.

Nguyên tắc:
- Deadline end-to-end được truyền qua service chain.
- Timeout từng dependency nhỏ hơn deadline còn lại.
- Exponential backoff và jitter.
- Retry chỉ với lỗi tạm thời và operation an toàn/idempotent.
- Có idempotency key cho operation tạo side effect.
- Giới hạn tổng retry attempts và retry rate.
- Không retry đồng thời ở mọi lớp.
- Hủy công việc khi client cancel nếu có thể.
- Circuit breaker và load shedding khi dependency mất capacity.

Retry không làm dependency khỏe hơn. Retry có thể giúp vượt lỗi ngắn, nhưng khi kéo dài sẽ tăng queue và contention.

## 14. Connection pool và concurrency

Connection pool giới hạn số kết nối tới database hoặc downstream. Pool quá nhỏ tạo pool wait; pool quá lớn có thể làm database quá tải.

Một service có 20 replicas, mỗi replica pool tối đa 80 connections có thể mở tới 1.600 connections. Khi autoscaling tăng replicas lên 50, theoretical maximum thành 4.000, dù DB không tăng capacity.

Cần tính tổng trên toàn fleet:

```text
Maximum potential connections =
  replicas × pool size per replica
  + background workers
  + admin / migration reserve
```

Cần:
- Giới hạn pool theo DB budget.
- Có connection timeout và acquisition timeout.
- Đo active, idle, pending waiters và wait duration.
- Tách pool cho workload critical/batch nếu cần.
- Dùng proxy/pooling mode phù hợp transaction semantics.
- Giới hạn replica/autoscaling maximum dựa trên downstream budget.

## 15. Concurrency control cho worker và job

Worker count không chỉ dựa vào CPU cores. Job có thể CPU-bound, I/O-bound hoặc bị giới hạn downstream.

| Workload | Đặc điểm | Hướng sizing |
| --- | --- | --- |
| CPU-bound | Giữ CPU trong phần lớn service time | Benchmark theo cores và CPU saturation |
| I/O-bound | Chờ network/storage nhiều | Concurrency cao hơn có thể phù hợp, nhưng giới hạn connection |
| Database-heavy | Nhiều query hoặc lock | Theo DB capacity và query cost |
| External API | Bị quota/latency bên ngoài giới hạn | Theo provider rate limit và deadline |
| Long-running batch | Service time dài, tốn memory | Queue riêng, bounded concurrency và checkpoint |

Nếu tăng worker count làm throughput không tăng nhưng CPU/DB wait/queue age tăng, hệ thống đã chạm bottleneck ở dependency hoặc contention. Hạ concurrency đôi khi cải thiện throughput hữu ích bằng cách giảm tranh chấp.

## 16. Fan-out và multiplicative load

Một request API có thể gọi nhiều dependency song song hoặc nối tiếp. Fan-out làm tổng operation rate ở downstream lớn hơn ingress rate.

Ví dụ mỗi request search gọi 4 service, mỗi service query 3 lần tới shared catalog:

```text
Downstream calls per inbound request = 4 × 3 = 12

At 500 inbound requests/s:
  downstream call rate = 500 × 12 = 6,000 calls/s
```

Cần lập call graph và cost per request. Cache, batching, query consolidation và bounded fan-out có thể giảm load. Parallel fan-out giảm latency trong một số trường hợp nhưng tăng concurrency và tải tức thời lên tất cả dependency.

## 17. Autoscaling theo tín hiệu đúng

CPU utilization không phản ánh mọi queueing bottleneck. Một service chờ database có thể CPU thấp nhưng latency và in-flight request rất cao.

Signal phù hợp tùy workload:
- CPU/memory cho compute saturation.
- Request concurrency/in-flight cho API.
- Queue depth và oldest message age cho workers.
- Completion rate và processing lag cho stream.
- Connection pool wait cho DB-bound service.
- Custom work units nếu request cost không đồng nhất.

### 17.1. Scale-out và scale-in

Autoscaling cần:
- Threshold và target có cơ sở từ load test.
- Cooldown/stabilization để tránh flapping.
- Maximum replicas theo downstream budget.
- Minimum capacity để giữ baseline.
- Scale-in protection cho worker đang xử lý stateful task.
- Warm-up/readiness trước khi nhận traffic.
- Quota, IP/subnet và placement capacity.
- Không scale-out vô hạn khi dependency đã quá tải.

Scaling compute mà không scale hoặc bảo vệ database có thể biến bottleneck nhỏ thành incident lớn hơn.

## 18. Throughput hữu ích và workload mix

Không phải mọi request hoàn thành đều có giá trị như nhau. Một số request có thể là retry trùng, health check, background polling hoặc operation bị timeout trước khi client nhận kết quả.

Nên phân biệt:
- Offered load: lượng công việc generator/client gửi.
- Accepted load: lượng hệ thống chấp nhận.
- Completed throughput: lượng công việc hoàn tất.
- Successful throughput: lượng operation hoàn tất đúng contract.
- Useful throughput: công việc hoàn tất tạo kết quả nghiệp vụ hữu ích, sau khi loại duplicate/failed work theo định nghĩa.

Trong booking platform, 1.000 request/s nhưng 30% là retry trùng hoặc 409 do contention không tương đương 1.000 booking hợp lệ/s.

### 18.1. Capacity theo cost unit

Có thể quy đổi các loại request:

```text
Work units/s = Σ (rate_i × cost_weight_i)

Search: 400 req/s × 1 = 400 units/s
Booking: 80 req/s × 5 = 400 units/s
Export: 5 req/s × 20 = 100 units/s
Total = 900 units/s
```

Cost weight cần được hiệu chỉnh từ CPU, DB query, network và service time đo được. Không dùng weight chủ quan lâu dài mà không benchmark.

## 19. Saturation và overload behavior

Saturation xảy ra khi một tài nguyên đạt giới hạn khiến thêm demand không làm throughput tăng tương ứng và latency/error tăng.

Dấu hiệu:
- CPU run queue hoặc throttling cao.
- Memory pressure, GC pause, OOM.
- DB connection wait, lock wait, IOPS saturation.
- Queue age tăng liên tục.
- Network retransmit/drop hoặc bandwidth ceiling.
- Thread pool/task queue đầy.
- Rate limit/429/503 tăng.
- Retry và timeout tăng cùng lúc.

Cần định nghĩa overload mode:
1. Giữ operation critical.
2. Từ chối sớm request vượt budget.
3. Giảm hoặc dừng background workload.
4. Ngăn retry storm.
5. Giữ hệ thống có thể phục hồi sau khi load giảm.
6. Khôi phục dần thay vì mở toàn bộ backlog cùng lúc.

## 20. Đo lường và dashboard hiệu năng

| Nhóm | Metric cần theo dõi |
| --- | --- |
| Load | Offered/accepted/completed/successful requests/s |
| Concurrency | In-flight requests, active workers, pool waiters |
| Latency | p50/p90/p95/p99 end-to-end và service time |
| Queue | Depth, oldest age, enqueue/dequeue rate, drain estimate |
| Resource | CPU, memory, GC, IOPS, bandwidth, connections |
| Dependency | Latency/error/rate limit theo downstream |
| Overload | 429/503, timeout, retry, dropped/rejected work |
| Autoscaling | Detection, provision, ready time, replica count |
| Business | Successful booking/payment, duplicate, abandoned request |

### 20.1. Dashboard phải giữ measurement boundary

Đặt tên metric rõ: API latency tại gateway hay service; queue wait trước worker hay total job age; throughput là request accepted hay transaction committed. Dùng trace để liên hệ end-to-end với component span.

Không dùng average duy nhất khi tail latency quyết định user experience. Histogram buckets phải phù hợp SLO threshold.

## 21. Kiểm thử hiệu năng và queueing

Các loại test:

- **Load test:** tải dự kiến bình thường và design peak.
- **Stress test:** tăng tới khi saturation/overload.
- **Spike test:** tăng đột ngột để kiểm tra burst handling.
- **Soak test:** duy trì lâu để phát hiện leak, backlog và degradation.
- **Capacity test:** tìm throughput tối đa vẫn giữ SLO.
- **Queue recovery test:** tạo backlog rồi đo drain time.
- **Dependency degradation test:** làm DB/API chậm hoặc rate-limit.
- **Concurrency test:** thay đổi in-flight limit, worker count và connection pool.
- **Failover test:** mất một replica/zone trong khi đang ở peak.

### 21.1. Closed-loop và open-loop load

Closed-loop generator chờ response trước khi gửi request kế tiếp; nó phù hợp mô phỏng số user đồng thời nhưng offered rate giảm khi hệ thống chậm.

Open-loop generator phát request theo lịch độc lập với response; phù hợp kiểm tra arrival rate và queue growth, nhưng cần giới hạn generator và đo dropped sends.

Dùng cả hai khi cần trả lời hai câu hỏi khác nhau. Ghi lại offered load, accepted load và completed throughput để biết client hoặc generator có vô tình tự điều tiết không.

### 21.2. Điều kiện test đáng tin cậy

- Dataset và cache state đại diện.
- Request mix giống production.
- Dependency thật hoặc mock có latency/limit tương đương.
- Warm-up và steady-state window rõ.
- Không để load generator là bottleneck.
- Đo p95/p99 và business success.
- Lưu config, build, data set, seed và workload profile để tái lập.
- Có tiêu chí dừng an toàn.
- Test lặp lại và so sánh cùng điều kiện.

## 22. Quy trình phân tích một bottleneck

1. Xác định user journey và SLO đang vi phạm.
2. So sánh offered load, accepted load và completed throughput.
3. Xem concurrency và queue depth/age thay đổi thế nào.
4. Tách end-to-end latency thành gateway, service, queue và downstream waits.
5. Kiểm tra utilization/saturation theo từng resource.
6. Kiểm tra service time distribution, p95/p99 và lock contention.
7. Xác định bottleneck có thể là compute, DB, network, provider quota hay scheduler.
8. Thử thay đổi có kiểm soát: worker count, pool size, batching, cache hoặc query.
9. Đo throughput hữu ích, latency và error cùng lúc.
10. Chọn giải pháp giữ SLO dưới design peak và overload.
11. Thêm alert/limit/runbook để vấn đề không tái diễn âm thầm.

Không kết luận “cần thêm CPU” chỉ từ CPU high; cũng không kết luận “cần thêm worker” chỉ vì queue sâu. Phải tìm resource hoặc stage đang giới hạn service capacity.

## 23. Tình huống thực hành: queue đặt chỗ tăng nhanh

**Bối cảnh:** Một nền tảng booking nhận 600 jobs/s vào queue trong campaign. Mỗi worker xử lý trung bình 80 jobs/s nhưng thực tế có 5 worker. Queue depth bắt đầu ở 12.000 jobs. Hệ thống phải giữ queue age dưới 2 phút cho booking jobs. Export jobs dùng chung worker pool và trung bình tốn tài nguyên gấp 4 lần booking.

### 23.1. Tính capacity và backlog

Với giả định 80 jobs/s là năng lực mỗi worker cho workload mix hiện tại:

```text
Total service capacity = 5 × 80 = 400 jobs/s
Backlog growth = 600 - 400 = 200 jobs/s
```

Queue đang tăng, do đó thêm worker hoặc giảm arrival/admission load là cần thiết. Chỉ tăng queue retention không giải quyết được mất ổn định.

### 23.2. Tính drain time khi load giảm

Giả sử campaign kết thúc và arrival rate giảm còn 100 jobs/s, worker capacity vẫn 400 jobs/s:

```text
Net drain rate = 400 - 100 = 300 jobs/s
Drain time for 12,000 jobs = 12,000 / 300 = 40 seconds
```

Nếu backlog đã tăng thêm 200 jobs/s trong 5 phút campaign, backlog tăng thêm 60.000 jobs. Sau khi campaign kết thúc:

```text
Total backlog = 12,000 + 60,000 = 72,000 jobs
Drain time = 72,000 / 300 = 240 seconds = 4 minutes
```

Queue age có thể vượt deadline 2 phút ngay cả khi queue cuối cùng drain được. Cần theo dõi oldest age và phân biệt booking với export.

### 23.3. Thiết kế khắc phục

- Tách queue/worker pool cho booking và export.
- Đặt concurrency và weighted fair scheduling.
- Giới hạn export jobs trong campaign.
- Scale booking consumers theo queue age và completion rate.
- Bảo đảm database connection budget không bị worker mới làm vượt.
- Dùng idempotency để retry không tạo booking trùng.
- Rate limit producer hoặc trả trạng thái accepted/pending khi queue gần đầy.
- Đo queue age, drain estimate và successful booking throughput.

## 24. ADR mẫu: giới hạn concurrency và bảo vệ queue

```text
ADR-164: Admission control và worker pool riêng cho booking

Bối cảnh:
- Campaign làm arrival rate tăng nhanh.
- Booking và export dùng chung worker pool.
- Export có cost cao, làm booking queue age vượt SLO.
- Tăng worker vô hạn có thể làm database quá tải.

Lựa chọn:
A. Tăng queue retention và để worker xử lý dần.
B. Tăng worker count cho mọi job.
C. Tách priority/workload pool, bounded concurrency và admission control.

Quyết định:
- Chọn C.
- Booking có worker pool/concurrency budget riêng.
- Export được giới hạn và có thể trì hoãn trong peak.
- Queue bounded; producer nhận backpressure khi vượt budget.
- Autoscaling dựa trên queue age, completion rate và dependency capacity.
- DB connection budget được tính trên toàn fleet.

Đánh đổi:
- Scheduling và vận hành phức tạp hơn.
- Export có thể chờ lâu trong campaign.
- Cần workload classification và fairness policy.

Kiểm chứng:
- Load test peak giữ booking queue age trong SLO.
- Export không chiếm hết worker/DB connections.
- Retry không tạo duplicate booking.
- Drain time sau burst nằm trong recovery objective.
- Overload trả lỗi/accepted state theo API contract.

Điều kiện xem lại:
- Traffic mix hoặc job cost thay đổi.
- Queue age/throughput SLO thay đổi.
- Database/provider capacity thay đổi.
```

## 25. Những sai lầm thường gặp

1. **Đồng nhất throughput với latency:** xử lý nhiều request/s không có nghĩa từng request nhanh.
2. **Đồng nhất concurrency với thread count:** runtime async và I/O wait làm quan hệ khác nhau.
3. **Dùng average latency duy nhất:** che giấu p99 và nhóm request rất chậm.
4. **Coi queue là capacity:** backlog vô hạn chỉ trì hoãn overload.
5. **Không đo queue age:** depth có thể lớn nhưng drain nhanh hoặc nhỏ nhưng chờ lâu.
6. **Tăng worker không giới hạn:** làm DB, network hoặc provider quá tải.
7. **Tăng connection pool theo replica count:** tổng connections vượt DB budget.
8. **Autoscale chỉ theo CPU:** bỏ qua queue wait và downstream saturation.
9. **Retry ở mọi tầng:** tạo retry amplification và storm.
10. **Không bounded queue:** memory/disk cạn trước khi có tín hiệu rõ.
11. **Không tách workload cost khác nhau:** batch/export gây noisy neighbor.
12. **Tính Little's Law ngoài steady state mà không cảnh báo:** kết quả bị diễn giải sai.
13. **Cộng percentile từng service:** không tạo ra percentile end-to-end chính xác.
14. **Dùng closed-loop test cho mọi mục tiêu:** load tự giảm khi hệ thống chậm.
15. **Bỏ qua coordinated omission:** tail latency bị đánh giá thấp.
16. **Chỉ đo accepted requests:** bỏ qua operation bị drop/reject hoặc không thành công.
17. **Không tính fan-out:** một inbound request có thể tạo nhiều downstream calls.
18. **Không test recovery backlog:** queue tiếp tục tăng sau khi incident kết thúc.

## 26. Checklist trước production

- [ ] Throughput, arrival rate và successful throughput có định nghĩa nhất quán.
- [ ] Concurrency phân biệt in-flight, active execution, waiting và connections.
- [ ] Latency đo end-to-end và các stage quan trọng.
- [ ] Có p50/p95/p99 và SLO threshold phù hợp.
- [ ] Little's Law được dùng với steady-state boundary và đơn vị nhất quán.
- [ ] Queue depth, oldest age, enqueue/dequeue rate và drain estimate được theo dõi.
- [ ] Worker/service capacity được benchmark với workload mix thực tế.
- [ ] Utilization ceiling và headroom được xác định theo resource.
- [ ] Queue được bounded và có retention/dead-letter policy.
- [ ] Admission control, backpressure và load shedding có contract rõ.
- [ ] Timeout, retry budget, backoff/jitter và idempotency được thiết kế.
- [ ] Connection pool được sizing trên toàn fleet và autoscaling maximum.
- [ ] Fan-out và downstream cost per request được đo.
- [ ] Autoscaling dùng signal phù hợp và không vượt dependency budget.
- [ ] Overload/degraded mode ưu tiên operation critical.
- [ ] Dashboard phân biệt offered/accepted/completed/successful workload.
- [ ] Load test gồm open-loop/closed-loop, peak, spike, soak và stress phù hợp.
- [ ] Test kiểm tra tail latency, coordinated omission và queue recovery.
- [ ] Có owner/runbook cho saturation, backlog và dependency throttling.

---

**Ghi nhớ:** Throughput cho biết tốc độ hoàn thành, concurrency cho biết lượng công việc đang tồn tại, latency cho biết thời gian hoàn tất, còn queue biểu hiện phần công việc đang chờ capacity. Định luật Little nối ba đại lượng trung bình; utilization gần saturation làm thời gian chờ tăng nhanh. Thiết kế hiệu năng phải giới hạn queue, đo tail latency, kiểm soát concurrency/retry và kiểm thử dưới workload đại diện để giữ SLO khi tải biến động.
