# Đánh giá hàng đợi, tải đồng thời và dấu hiệu quá tải

Một truy vấn **Database No SQL** mất 800 ms không nhất thiết vì database cần 800 ms để đọc dữ liệu. Request có thể đã **chờ 500 ms trong hàng đợi của Java**, chờ thêm 250 ms để lấy connection, sau đó mới thực thi truy vấn 50 ms. Nếu chỉ xem “database latency” trên biểu đồ HTTP mà không phân tách các giai đoạn, nhóm vận hành có thể thêm index, tăng replica hoặc tăng timeout nhưng không chữa đúng điểm nghẽn.

Ví dụ một hệ đọc Product:

~~~text
20,000 HTTP requests/s đi vào API
   -> Executor queue dài dần
   -> Java driver connection pool checkout wait
   -> NoSQL coordinator/server đang bão hòa CPU/IO
   -> Một số requests timeout và được retry
   -> Retry tạo thêm request, queue còn dài hơn
~~~

Đây là **vòng khuếch đại quá tải**. Khi lưu lượng đến vượt tốc độ xử lý bền vững, hàng đợi tích tụ, tail latency tăng và cơ chế retry có thể khiến hệ suy sụp dù mỗi query riêng lẻ vốn rất nhanh.

Bài học thuộc chương **Quan sát và chẩn đoán** của **Database No SQL**, tập trung vào cách xác định hàng đợi nằm ở đâu, đo arrival/completion rates, tải đồng thời và mức sử dụng tài nguyên; phân biệt queue wait với service time; phát hiện quá tải trước khi error rate bùng nổ; và dùng backpressure, bounded queues, admission control cùng giới hạn retry để bảo vệ tính sẵn sàng lẫn tính đúng đắn.

> **Nguyên tắc:** Đừng đánh giá database chỉ bằng “QPS” hoặc “CPU 80%”. Hãy quan sát **lưu lượng đến, tốc độ hoàn thành, số request đang chờ, tuổi request già nhất, thời gian chờ từng tầng, p95/p99, số lỗi và tình trạng nguồn lực** trên cùng một khoảng thời gian.

## 1. Các khái niệm cơ bản

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Arrival rate** | Số công việc đến một tầng mỗi giây | 5.000 GET/s vào API |
| **Service rate** | Tốc độ một worker/server hoàn thành khi được cấp việc | 200 queries/s/worker theo giả định |
| **Throughput** | Số công việc được hoàn thành thực tế | 4.800 successful reads/s |
| **Concurrency** | Số công việc đang đồng thời tồn tại hoặc đang được xử lý trong phạm vi đo | 150 in-flight operations |
| **Queue depth** | Số việc đang chờ, chưa được xử lý ở hàng đợi đó | 1.200 queued tasks |
| **Queue wait** | Thời gian từ lúc vào queue đến khi bắt đầu service | 300 ms |
| **Service time** | Thời gian một đơn vị xử lý thực hiện công việc theo ranh giới đo | 25 ms |
| **Response time** | Tổng thời gian chờ và xử lý trong scope | 325 ms |
| **Utilization** | Phần năng lực tài nguyên đang bận theo mô hình đo | CPU hoặc active worker ratio |
| **Backlog age** | Tuổi của việc chưa hoàn thành, thường quan trọng hơn queue size đơn lẻ | Event già nhất 8 phút |
| **Saturation** | Năng lực xử lý/queue/nguồn tài nguyên đạt ngưỡng gây waiting/rejection | Pool hết, disk queue tăng |

Các từ này không hoàn toàn đồng nghĩa. **Concurrency** đếm công việc đang có mặt; **parallelism** đếm công việc thật sự thực thi đồng thời trên tài nguyên. Một server có 1.000 in-flight requests có thể chỉ có 16 database connections đang thực thi.

## 2. Sơ đồ những hàng đợi trong đường đi

~~~mermaid
flowchart TD
  Client["Client / upstream API"] --> Edge["Gateway rate limit / pending"]
  Edge --> Http["Java HTTP worker / event loop"]
  Http --> Local["Java executor / semaphore queue"]
  Local --> Pool["NoSQL driver pool wait"]
  Pool --> Net["Network and server selection"]
  Net --> Server["NoSQL request admission / scheduler"]
  Server --> Disk["CPU, index, cache, disk IO"]
  Server --> Repl["Replication / consistency wait"]
  Disk --> Result["Database response"]
  Repl --> Result
  Result --> Http
  Http --> Client
~~~

Một request có thể chờ ở nhiều điểm. Hai request đi cùng endpoint nhưng một là cache hit và một là transaction xuyên shards sẽ dùng các nhánh hoàn toàn khác nhau.

Các lớp cần quan sát riêng:

1. Gateway/API queue.
2. Java executor, virtual-thread hoặc event-loop scheduling.
3. Application concurrency limiter.
4. Driver connection checkout/pending acquire.
5. Socket/network/server selection.
6. Database accept/admission, coordinator và scheduler.
7. CPU/IO/index query execution.
8. Replication/quorum/transaction coordination.
9. Kênh bất đồng bộ sau commit: event, outbox, CDC, search indexing.

Không cộng tất cả số queue depth vào một metric “total queue” rồi suy thành số request unique: cùng request có thể lần lượt đi qua nhiều hàng đợi.

## 3. Queue wait khác execution time

Một phân rã đơn giản:

\[
T_{\text{response}} =
T_{\text{app wait}} +
T_{\text{pool wait}} +
T_{\text{network}} +
T_{\text{database}} +
T_{\text{serialization}} +
T_{\text{other}}
\]

Đây là mô hình **tuần tự hóa logic** để xác định bottleneck; async/pipelining có thể chồng lấp các giai đoạn, nên phép cộng chỉ chính xác khi ranh giới và span được định nghĩa không trùng nhau.

Ví dụ:

~~~text
HTTP total              620 ms
  Auth/business code      10 ms
  Worker queue           180 ms
  Connection checkout    250 ms
  Driver + DB RTT        170 ms
  Serialize response      10 ms
~~~

Nếu chỉ xem database server thực thi truy vấn 35 ms, vẫn phải tìm phần chờ còn lại trong driver, network và ứng dụng.

## 4. Hàng đợi và tốc độ tới/ra

Ký hiệu:

- \(\lambda\): arrival rate, jobs/s.
- \(\mu\): service capacity của một server/worker trong mô hình phù hợp.
- \(c\): số server/worker thực sự có thể xử lý song song.
- \(Q(t)\): số công việc chờ tại thời điểm \(t\).

Ước lượng trực giác:

\[
\frac{dQ}{dt}\approx\lambda-\text{departure rate}
\]

Khi \(\lambda\) liên tục lớn hơn tốc độ xử lý bền vững, queue tăng. Khi \(\lambda\) thấp hơn, queue có cơ hội giảm. Nhưng deadline, cancellations, retries và load shedding có thể làm công việc rời queue mà **chưa thành công**, nên phải đo từng outcome.

## 5. Ví dụ backlog tích tụ

Giả định:

~~~text
Incoming jobs:    1,500/s
Completed jobs:   1,200/s
Difference:         300/s
Duration:          60 s
~~~

Nếu không reject/cancel và sức chứa cho phép:

\[
\Delta Q\approx(1500-1200)\times60=18{,}000
\]

Hàng đợi tăng khoảng 18.000 jobs trong một phút. Đây không phải trạng thái steady state.

Một dashboard chỉ vẽ throughput=1.200/s có thể trông ổn; biểu đồ **queue depth slope** và **oldest wait** mới cho thấy hệ đang nợ ngày càng nhiều công việc.

## 6. Little's Law

Trong một hệ tương đối ổn định, với ranh giới và mẫu thống nhất:

\[
L=\lambda W
\]

Trong đó:

- \(L\): số công việc trung bình hiện diện trong hệ.
- \(\lambda\): throughput/arrival rate hiệu dụng của hệ ổn định.
- \(W\): thời gian trung bình trong hệ.

Ví dụ 2.000 completed requests/s, mean response time 50 ms:

\[
L=2000\times0.050=100
\]

Trung bình có khoảng 100 requests trong scope.

**Không dùng Little's Law tùy tiện cho quá tải kéo dài đang tích tụ queue** mà không xác định việc hoàn thành, hủy hoặc dropped jobs. Nó cũng không cho trực tiếp p99 từ mean.

## 7. Little's Law cho riêng queue

Nếu chỉ đo công việc **đang chờ**, ta có thể dùng:

\[
L_q = \lambda W_q
\]

với cùng trạng thái ổn định và định nghĩa jobs/queue thích hợp.

Ví dụ:

~~~text
Effective arrival/completion = 1,000/s
Mean queue wait = 80 ms
Estimated mean queue length = 80 jobs
~~~

Vì:

\[
L_q\approx1000\times0.08=80
\]

Nếu dashboard đo actual queued jobs ~800 ở cùng scope/window, cần kiểm tra **measurement mismatch, non-steady state, hidden requests hoặc queue time estimation**, không mặc định công thức sai.

## 8. Utilization không phải phần trăm QPS

Đối với một tài nguyên có capacity theo mô hình:

\[
\rho=\frac{\lambda}{c\mu}
\]

Ví dụ 8 workers, mỗi worker phục vụ 100 jobs/s ổn định, arrival 720/s:

\[
\rho=720/(8\times100)=0.90
\]

Nhưng “90% utilization” theo mô hình không giống **CPU 90%**: một DB có thể nghẽn disk IO ở CPU 40%, nghẽn network ở CPU 20%, hoặc transaction lock contention dù worker threads còn rảnh.

Đừng tìm một ngưỡng chung “CPU chưa đạt 100% thì chưa quá tải”.

## 9. M/M/1: trực giác gần saturation

Trong mô hình lý tưởng M/M/1 với arrival Poisson, service time exponential, một server, hàng đợi vô hạn và \(\lambda<\mu\):

\[
E[W]=\frac{1}{\mu-\lambda}
\]

Đây là **mean time trong system** (queue + service).

Giả sử service capacity \(\mu=100\) jobs/s:

| Arrival \(\lambda\) | Utilization | Mean system time mô hình |
|---|---:|---:|
| 50/s | 50% | 20 ms |
| 80/s | 80% | 50 ms |
| 90/s | 90% | 100 ms |
| 95/s | 95% | 200 ms |
| 99/s | 99% | 1.000 ms |

Dù service time khi rỗng chỉ 10 ms, thời gian tổng tăng rất mạnh khi gần capacity.

**Không dùng M/M/1 làm dự đoán chính xác cho MongoDB/Cassandra/DynamoDB**: real systems có nhiều server, cache, batching, non-Poisson arrivals, giới hạn queue, timeouts, heterogeneous queries và load balancing.

## 10. Vì sao p99 tăng trước khi throughput giảm?

Khi hệ gần giới hạn:

- Một request chậm giữ connection lâu.
- Request sau phải xếp hàng.
- Chỉ một số requests rơi vào hàng đợi dài.
- Mean có thể chưa biến động nhiều.
- p95/p99 tăng nhanh.
- Đến một ngưỡng, timeout/rejections tăng.
- Throughput successful có thể dừng tăng hoặc giảm.

Sơ đồ:

~~~text
Load increases →
Latency:
  p50       ___----__
  p95       ____------________
  p99       _________/^^^^^^^^
Throughput:
  grows -> flatten -> possibly degrades
Queue:
  low   -> rising  -> unbounded without controls
~~~

Các đường chỉ minh họa xu hướng; hình thực nghiệm phụ thuộc workload và engine.

## 11. “Điểm gãy” của hệ

Một cách tìm capacity hữu ích:

1. Giữ offered rate thấp, đo steady-state.
2. Tăng từng bước nhỏ.
3. Với mỗi mức, chờ hệ ổn định hoặc ghi rõ không ổn định.
4. Đo p99, successful RPS, errors, queue depth, resource saturation và lag.
5. Tìm điểm mà **p99 vượt SLO, queue/backlog không tự giảm, hoặc lỗi tăng**.
6. Chọn operating point có headroom trước điểm gãy.
7. Kiểm tra lại dưới burst, key skew và node failure.

Maximum QPS đúng tại 100% CPU và p99 không kiểm soát **không phải sustainable production capacity**.

## 12. Three USE signals: utilization, saturation, errors

Đối với mỗi resource, đặt ba câu hỏi:

- **Utilization:** tài nguyên bận bao nhiêu?
- **Saturation:** có công việc chờ hoặc không được nhận vào không?
- **Errors:** tài nguyên thất bại ra sao?

Ví dụ:

| Resource | Utilization | Saturation | Errors |
|---|---|---|---|
| Java worker pool | Active threads / max | Queue depth, queue age | RejectedExecution |
| NoSQL connection pool | Checked-out / max | Pending checkout, wait time | Pool checkout timeout |
| DB CPU | CPU busy | Run queue / scheduler wait | Operation timeouts |
| Storage | IO utilization | Device queue, fsync wait | IO errors |
| Kafka consumer | Busy processing fraction | Consumer lag, oldest age | Failed retries, DLQ |
| DynamoDB table | Consumed capacity/throttle signals | Request throttling/backoff | Throttling exceptions |
| Redis | Ops/sec, CPU, network | Pending commands, client buffers | TIMEOUT/OOM/connection errors |

Không có một API duy nhất cho mọi row; một metric có thể không khả dụng ở managed service. Khi thiếu metric trực tiếp, dùng latency, throughput và queue age làm dấu hiệu tương quan nhưng **không tự khẳng định nguyên nhân**.

## 13. Golden signals ở API

Song song USE, quan sát:

- **Latency** p50/p95/p99 và deadline violations.
- **Traffic** incoming/eligible RPS và sizes.
- **Errors** 4xx business rejection, 5xx, timeout, retry.
- **Saturation** in-flight, queue depth, pool wait, DB resource pressure.

Vì một timeout có thể xảy ra ở gateway trước khi database nhìn thấy request, phải thu thập **client-observed latency** và **server metrics** trên cùng trục thời gian.

## 14. Hàng đợi nào không nên gộp?

| Queue | Đơn vị | Chủ sở hữu | Hành động khi quá dài |
|---|---|---|---|
| HTTP pending | HTTP requests | Gateway/server | Admission/rate limit |
| Java executor | Tasks | Application | Bounded queue/concurrency |
| Driver pool checkout | Callers waiting for connection | Driver | Tìm query chậm, pool sizing |
| DB server scheduler | Accepted operations | Database | Query plan/capacity/lock |
| Disk device | IO operations/bytes | Storage | Index/IO/instance |
| Replication apply | Log positions/bytes/time lag | Database replicas | Catch-up/capacity |
| Kafka/CDC | Records/partitions/oldest age | Stream consumer | Consumer scale/backpressure |
| Search indexing | Documents/tasks | Search engine | Bulk/reindex tuning |
| Retry queue | Attempts/backoff jobs | Client/worker | Retry budget/error triage |

Một Kafka backlog 1 triệu records không đồng nghĩa 1 triệu HTTP requests đang chờ, và một replication lag 30 s không phải driver pool wait 30 s.

## 15. Queue depth phải đi với throughput và age

Một queue có 100 jobs nhưng worker xử lý 10.000 jobs/s có thể trống rất nhanh. Một queue có 20 jobs nhưng xử lý 1 job/phút có thể chứa task rất già.

Cần đồng thời:

- Current queue depth.
- Arrival rate.
- Completed rate.
- Oldest queued job age.
- Waiting time histogram.
- Retry count.
- Dead-letter/rejected count.
- Processing time distribution.
- Number of active workers.

**Backlog age** thường có ý nghĩa trực tiếp với SLO hơn số lượng records đơn lẻ, nhất là khi kích thước/chi phí jobs khác nhau.

## 16. Queue age không chỉ tính bằng queueLength/throughput

Ước lượng:

\[
T_{\text{drain}}\approx Q/\mu_{\text{net drain}}
\]

chỉ có ý nghĩa khi tốc độ xử lý và arrival pattern được định nghĩa. Nếu arrivals vẫn tiếp tục, hoặc \(\mu_{\text{net drain}}\le0\), queue không thể hết theo mô hình đơn giản. Nếu từng job có service time rất khác, chia `count/opsPerSec` còn thiếu thông tin về work size.

Hãy dùng **measured oldest age và waiting distribution** để quyết định đã vượt SLO chưa.

## 17. In-flight là gì?

Một request là **in-flight** từ khi được nhận vào một scope đến khi outcome hoàn tất, bị hủy hoặc timeout, tùy instrumentation.

Có thể có:

~~~text
HTTP in-flight = 800
NoSQL driver in-flight = 300
Pool checked out = 64
DB actively executing = 24
~~~

Đây không tự mâu thuẫn:

- Một số HTTP requests đang xử lý business logic.
- Một số chờ driver pool.
- Nhiều operations có thể dùng pooled/multiplexed connections.
- DB có scheduler riêng và service time khác network RTT.

Không dùng `activeConnections` làm số lượng truy vấn đồng thời một cách máy móc nếu driver hỗ trợ pipelining/multiplexing.

## 18. Concurrency cap và connection pool size khác nhau

Giả sử application cho phép 500 concurrent operations tới database, nhưng pool chỉ có 50 connections. Việc tăng pool lên 500 có thể:

- Giảm checkout wait tạm thời.
- Đẩy đồng thời 500 operations xuống server.
- Làm server IO/CPU/lock saturation.
- Tăng tail latency và lỗi.
- Khiến service khác thiếu tài nguyên.

Pool size là **giới hạn kết nối**, không phải capacity bảo đảm của DB. Cần chọn concurrency/admission theo khả năng server xử lý bền vững và operation mix.

## 19. Java synchronous vs async

Với Java synchronous:

~~~text
Request thread calls database
Thread blocks while waiting for result
```

Nếu thread pool nhỏ, blocking calls giữ thread lâu và gây queue.

Với async/reactive:

~~~text
Request sends non-blocking operation
Completion callback receives result later
```

Điều này có thể giảm số threads cần thiết, nhưng **không làm database có thêm throughput**. Async cũng có thể cho phép tạo 100.000 in-flight requests quá nhanh nếu không có limiter, gây queue bên trong driver/server.

Reactive backpressure phải được truyền tới nơi tạo requests; đổi kiểu trả về `Mono`/`CompletionStage` không tự bảo vệ backend.

## 20. Virtual threads không xóa giới hạn backend

Java virtual threads giúp xử lý nhiều blocking tasks với chi phí thread thấp hơn trong nhiều trường hợp, nhưng:

- Connection pool vẫn hữu hạn.
- DB CPU/IO vẫn hữu hạn.
- Hot partitions vẫn tồn tại.
- Transaction conflicts vẫn xảy ra.
- Network/replication vẫn có RTT.
- Dữ liệu vẫn cần giữ consistency.

Một triệu virtual threads cùng chờ pool không làm database xử lý nhanh hơn. **Giới hạn đồng thời theo tài nguyên đích** vẫn cần.

## 21. Độ trễ driver có nhiều thành phần

Một operation MongoDB có thể bao gồm:

~~~text
Server selection wait
Connection checkout wait
Socket/TLS I/O
Server queue + execution
Replication/write concern wait
Response decode
Retry/backoff
~~~

Một request DynamoDB SDK có thể bao gồm HTTP pool acquisition, signing, network, managed service processing và retries. Không đặt tất cả thành một metric tên `db_query_time` rồi dùng nó để chẩn đoán query plan.

## 22. Connection checkout wait

Khi một driver pool đã hết connections khả dụng, caller phải đợi.

Dấu hiệu:

- Checked-out connections gần max.
- Checkout wait p95/p99 tăng.
- Wait queue depth tăng.
- Pool acquisition timeouts.
- Requests bị giữ lâu vì query chậm.
- In-flight requests tăng dù DB CPU thấp hoặc cao tùy nguyên nhân.

Cách điều tra:

1. Xem query/transaction duration.
2. Kiểm session/connection leaks.
3. Xem data skew/hot queries.
4. So pool max với DB server capacity.
5. Kiểm timeouts/retry và cancellation.
6. Chỉ tăng pool khi server còn headroom và có bằng chứng pool là bottleneck.

## 23. Phân biệt pool exhausted và server saturated

| Triệu chứng | Pool exhausted | Server saturated |
|---|---|---|
| Checkout wait | Thường tăng | Có thể tăng thứ cấp |
| DB CPU/IO | Có thể còn thấp | Thường một resource chạm giới hạn |
| Operation RTT | Có thể bình thường sau checkout | Thường tăng |
| Connection count | Chạm pool limit | Có thể cao hoặc không |
| Tăng pool | Có thể giúp nếu DB còn capacity | Dễ làm nặng hơn |
| Hành động tốt | Tối ưu lifetimes/limits | Giảm work, thêm capacity hoặc sửa query |

Cần correlation theo thời gian. Một query chậm ở server có thể làm pool exhausted **sau đó**; chữa nguyên nhân gốc tốt hơn chỉ chữa hậu quả.

## 24. Server selection wait khác pool wait

Với cluster replica set, driver có thể chờ tìm eligible primary/secondary.

~~~text
Primary election in progress
Driver cannot select write server
Requests wait in server selection
```

Tăng max pool không giúp nếu không có server phù hợp. Kiểm:

- Topology state và election.
- DNS/advertised addresses.
- Network/TLS.
- Read preference.
- Server selection timeout.
- Driver monitor heartbeat.
- Retry/failover behavior.

**Queue wait do topology** khác queue wait vì **connection checkout**, dù HTTP p99 đều cao.

## 25. Overload có thể nằm ở một partition

Một cluster 10 nodes có CPU trung bình 35% nhưng một shard/token range nóng ở 100%:

~~~text
Node A: 100% CPU, hot tenant
Nodes B-J: 28% CPU on average
Cluster average: 35%
```

Dashboard aggregate che bottleneck. Cần phân rã theo:

- Shard/partition/rack/zone.
- Coordinator/leader.
- Query/collection/table.
- Tenant cohort.
- Key distribution.
- Per-node connections/requests.
- Read/write mix.

Không tự tăng cluster node count nếu partition key vẫn dồn traffic vào một owner.

## 26. Hot-key contention khác high QPS thông thường

Hai workloads cùng 5.000 writes/s:

~~~text
Uniform:
  requests spread over 100,000 keys

Skewed:
  90% writes target 10 keys
```

Workload skew có thể gây:

- CAS version conflicts.
- Lock/latch contention.
- Transaction aborts.
- Retry storms.
- Hot coordinator/partition.
- Replica apply bottleneck.

Cần đo conflict/retry per aggregate class hoặc sampled hot keys, không chỉ QPS trung bình.

## 27. Query không có index gây hàng đợi sâu

Nếu MongoDB phải scan nhiều document cho mỗi request, CPU/IO per query tăng.

~~~text
Before:
  1000 queries/s * 2 ms service = manageable

After collection grows:
  1000 queries/s * 100 ms service = huge work demand
~~~

Khi execution time tăng, connections giữ lâu và queue checkout tăng, ngay cả khi request arrival rate không đổi.

Để chẩn đoán:

- MongoDB query plan/index usage.
- Keys/docs examined vs returned.
- Disk reads, sort/memory.
- Query result sizes.
- Per-op duration histograms.

**Queue depth là triệu chứng; query work có thể là nguyên nhân.**

## 28. Large result sets và streaming

Một query trả 100.000 documents có thể:

- Giữ cursor/connection lâu.
- Tốn decode và network.
- Tạo heap pressure.
- Chặn pool checkout cho requests nhỏ.
- Tăng p99 trên một endpoint không liên quan.

Các hướng:

- Bounded pagination.
- Projection fields.
- Cursor lifecycle và cancellation.
- Separate pool/workload class nếu phù hợp.
- Streaming/backpressure cho consumers.
- Limit export concurrency.
- Query/index design cho access pattern.

Tăng pool vô hạn chỉ để chứa các exports dài thường không phải giải pháp bền vững.

## 29. Timeout làm queue khó đọc

Một job có thể rời queue vì:

- Hoàn thành thành công.
- Bị business rejection.
- Hết request deadline.
- Client đã disconnect/cancel.
- Connection acquire timeout.
- Retry được chuyển sang queue khác.
- Worker bị restart.

Nếu dashboard chỉ đếm `queueDepth`, nó có thể giảm sau khi các requests **timeout hàng loạt**, tạo ấn tượng throughput cải thiện.

Luôn đo **departures by outcome** và successful throughput bên cạnh queue size.

## 30. Retries làm arrival rate thực lớn hơn

Ví dụ 1.000 business requests/s, mỗi request tạo trung bình 1,5 DB attempts:

\[
R_{\text{db attempts}}=1000\times1.5=1500/s
\]

Khi DB chậm, số retries có thể tăng từ 0,1 lên 2 lần/request, làm arrival rate xuống DB tăng dù external traffic giữ nguyên.

Một hệ có ba tầng retry:

~~~text
Gateway: up to 3 attempts
Application: up to 3 attempts
Driver: up to 3 attempts
```

Trong đường lặp lồng nhau lý thuyết có thể tới 27 low-level attempts cho một ý định. Thực tế phụ thuộc error classification và SDK semantics, nhưng **retry amplification** là rủi ro phải đo và giới hạn.

## 31. Retry storm tạo feedback loop

~~~mermaid
flowchart TD
    A["Database gets slower"] --> B["Requests timeout"]
    B --> C["More retries"]
    C --> D["Higher effective arrival rate"]
    D --> E["Longer queue and pool waits"]
    E --> A
~~~

Một cách cắt vòng:

- Retry chỉ lỗi transient có tín hiệu phù hợp.
- Exponential backoff + jitter.
- Global/request retry budget.
- Deadline propagation.
- Idempotency cho write.
- Concurrency limiter.
- Load shedding khi không có headroom.
- Circuit breaker khi upstream/backend không đáp ứng.

Không giảm timeout xuống rất thấp mà không xem retries, vì timeout sớm hơn có thể kích hoạt attempts nhiều hơn.

## 32. Bounded queue và admission control

Một queue **vô hạn** tránh reject trong chốc lát nhưng có thể giữ requests tới khi hết deadline, tiêu thụ RAM và tạo latency vô dụng.

Một bounded queue xác định rõ:

~~~text
maxConcurrentDbOperations = 100
maxPendingDbOperations = 300
maxPendingWait = 50 ms

When full:
  reject/defer according to API contract
```

Những giới hạn trên là **ví dụ**, phải được đo và điều chỉnh. Từ chối sớm một phần request có thể bảo vệ p99/success rate của phần được nhận và ngăn toàn hệ sụp đổ.

## 33. Load shedding không được phá nghiệp vụ

Đối với GET sản phẩm có thể trả 503/429 với Retry-After phù hợp và cache fallback an toàn theo policy. Đối với `POST Checkout`, việc retry có thể gây trùng đơn hàng nếu thiếu idempotency.

Khi reject/throttle:

- Trả status code đúng ý nghĩa.
- Không báo “đặt hàng thành công” nếu write chưa commit.
- Giữ stable operation ID khi retry.
- Không xóa message khỏi durable queue trước khi xử lý.
- Không discard payment fact vì queue đầy.
- Có dead-letter/durable spool/priority policy khi cần.

**Backpressure giải quyết overload mà vẫn phải giữ correctness và durability contract.**

## 34. Rate limit và concurrency limit khác nhau

**Rate limit** giới hạn số requests đến trong một khoảng, ví dụ 1.000 requests/s.

**Concurrency limit** giới hạn số requests đồng thời trong tầng xử lý, ví dụ 100 in-flight.

Nếu mỗi request nhanh hơn/chậm hơn theo workload, hai giới hạn bảo vệ những thứ khác nhau:

- Rate limit chặn burst hoặc traffic sustained.
- Concurrency limit chặn số connections/operations đang chiếm tài nguyên.
- Queue bound giới hạn lượng việc chưa được nhận xử lý.
- Deadline giới hạn thời gian chờ tổng.
- Retry budget giới hạn work nhân lên.

Dùng phối hợp, không tự coi một token bucket là giải pháp cho mọi tail latency.

## 35. Fairness cho nhiều tenants

Một tenant có 95% traffic có thể chiếm hết queue khiến tenants nhỏ dù ít request cũng timeout.

Các lựa chọn:

- Per-tenant quotas.
- Weighted fair queueing.
- Priority classes theo business impact.
- Isolate background jobs khỏi interactive traffic.
- Separate concurrency pools cho hot/cold operations nếu đủ căn cứ.
- Limit một tenant không được giữ toàn bộ active slots.
- Track waiting time theo tenant cohort.

Không đưa raw tenant ID vào mọi metric label nếu cardinality quá cao. Có thể dùng cohorts, sampled traces và secure per-tenant investigation.

## 36. Head-of-line blocking

Một FIFO queue có:

~~~text
1. Heavy analytics job: 2 seconds
2. Simple point GET: 2 ms
3. Simple point GET: 2 ms
```

Nếu chỉ có một worker hoặc shared serial bottleneck, hai GET phải chờ job lớn. Đây là **head-of-line blocking**.

Cách giảm:

- Tách loại công việc.
- Bounded concurrent execution nếu server có headroom.
- Batching/limits.
- Separate queues theo latency class.
- Cursor pagination.
- Query optimizer/index phù hợp.

Không giải quyết bằng cách tăng mọi request timeout lên 10 giây.

## 37. Priority queues có thể gây starvation

Nếu luôn ưu tiên interactive requests, background reconciliation có thể không bao giờ được chạy, làm dữ liệu sai lệch lâu ngày.

Cần:

- Quota/minimum capacity cho background jobs.
- Maximum queue age và starvation metrics.
- Deadline/priority aging.
- Incident priority cho security/deletion events.
- Capacity headroom cho repair.
- Runbook khi phải tạm dừng batch jobs.

Một queue ưu tiên không bảo đảm công bằng nếu thiếu starvation policy.

## 38. Batching giảm overhead nhưng tăng waiting

Batching nhiều writes có thể giảm network roundtrips, nhưng cần đợi đủ batch hoặc timer:

~~~text
Batch size 100:
  fewer requests to DB
  higher per-batch throughput possible
  extra wait for low-traffic keys
```

Đánh đổi:

- Batch size.
- Max batch wait.
- Maximum bytes.
- Retry granularity.
- Partial failure semantics.
- Idempotency per item.
- Hot partition grouping.
- Transaction limits.

Đừng kết luận batch size lớn nhất luôn tốt nhất: p99 của những requests đến sớm trong batch có thể xấu đi.

## 39. Cache hit ratio và queue pressure

Một Redis/Caffeine cache tốt có thể giảm tải nguồn. Nhưng khi nhiều keys expire hoặc Redis outage, NoSQL source có thể nhận lượng miss gấp nhiều lần.

Ví dụ:

~~~text
Eligible reads: 10,000/s
Cache hit ratio: 98%
Origin reads: approximately 200/s

Hit ratio drops to 80%
Origin reads: approximately 2,000/s
```

Theo mô hình một miss tạo một source read, origin traffic tăng **10 lần**. Nếu một miss gọi nhiều collections, tải còn cao hơn.

Cần benchmark **cache failure/cold start**, không chỉ steady-state hit ratio.

## 40. Cache stampede tạo hàng đợi bất ngờ

Một key rất hot hết TTL, hàng nghìn Java requests cùng load source:

~~~text
Cache key expires
Thousands of GETs miss
All query same NoSQL key
Hot partition overloads
Driver pool checkout queue rises
More requests timeout and retry
```

Giải pháp phù hợp:

- Single-flight/coalescing per key.
- TTL jitter trong freshness SLO.
- Refresh-ahead với rate bound.
- Negative caching khi hợp lệ.
- Origin backpressure.
- Short cache timeout/circuit breaker.
- Caching version guards để tránh stale overwrite.

Không coi một lần cache stampede là bằng chứng phải tăng replicas ngay.

## 41. Replication queue và HTTP queue khác nhau

Một primary có thể ACK writes nhanh nhưng secondary apply lag tăng:

~~~text
Primary: accepts 5,000 writes/s
Secondary: applies 3,000 writes/s
Lag backlog: +2,000 mutations/s
```

HTTP write latency có thể còn thấp theo acknowledgment policy, nhưng read từ secondary càng stale và log retention margin giảm.

Cần monitor:

- Replica apply/commit positions.
- Time lag và bytes/entries behind.
- Secondary CPU/IO.
- Catch-up time sau load.
- Oplog/stream retention.
- Read consistency contract.

Một throughput benchmark không thực sự bền vững nếu **background queue tăng liên tục**.

## 42. CDC/Event consumer lag

Một stream consumer có thể chậm:

~~~text
Source event production: 30,000 records/s
Consumer applied:        25,000 records/s
Lag grows:                5,000 records/s
```

Lúc này app read model có thể trở nên stale dù source DB vẫn khỏe.

Phải phân biệt:

- Broker backlog count.
- Lag age / oldest unprocessed event.
- Per-partition skew.
- Consumer processing time.
- Sink write latency/throughput.
- Retry/DLQ counts.
- Stream retention margin.
- Projection applied watermark.

Không lấy một tổng lag count cho toàn Kafka topic làm SLA về thời gian trễ mà không biết event rate và partition behavior.

## 43. Queue age quan trọng cho CDC hơn offset count đơn lẻ

Nếu stream sản sinh 100.000 events/s, lag 10.000 records có thể tương đương rất ít thời gian khi records đều. Nếu stream chỉ có một event/giờ, một record bị kẹt có thể kéo dài hàng giờ.

Đo cả:

- Max age of unprocessed messages.
- Per-partition lag.
- Output/source version difference.
- Time to drain after outage.
- Backpressure on sink.
- Consumer failure/rebalance metrics.

Một consumer chỉ báo “lag=0” ngay sau reset offset mà không rebuild những events bỏ qua là sai về coverage.

## 44. Queue length không thay phép đo durability

Khi queue giảm vì worker đã `ACK` trước khi commit vào sink, công việc có thể **bị mất** dù dashboard lag đẹp. Một consumer đúng cần:

- ACK/checkpoint sau durable effect hoặc durable disposition.
- Idempotency vì redelivery có thể xảy ra.
- Replay/retention tracking.
- Gap detection.
- Reconciliation giữa source và read model.

Tải và tính đúng đắn luôn phải cùng được quan sát.

## 45. Backpressure xuyên chuỗi

Một pipeline:

~~~text
Source CDC -> Broker -> Worker -> Search Index
```

Nếu Search chỉ nhận 2.000 docs/s trong khi CDC tạo 10.000/s, không thể cứ cấp vô hạn RAM cho worker. Cần:

- Rate limit write to Search.
- Durable broker backlog/consumer pause theo API hỗ trợ.
- Bounded batches.
- DLQ cho poison records.
- Scale sink/cải thiện indexing.
- SLO về lag và retention margin.
- Alert sớm trước khi log hết hạn.

**Thêm workers** đôi khi chỉ tạo thêm concurrent writes và làm Search chậm hơn.

## 46. “DB CPU thấp” không loại trừ quá tải

Một hệ có CPU 20% vẫn có thể timeout vì:

- Disk I/O saturation.
- Lock/transaction contention.
- Connection pool exhausted.
- Network packet loss.
- Cross-region RTT.
- Leader election.
- Slow storage fsync.
- Max in-flight requests.
- Quota/throttling của managed service.
- Hot partition trên một node trong cluster lớn.
- External dependency giữ requests.

Vì vậy CPU là một trong nhiều tín hiệu, không phải thước đo duy nhất.

## 47. “DB CPU cao” cũng chưa chỉ ra giải pháp

CPU 95% có thể đến từ:

- Thiếu index, nhiều docs examined.
- Serialization lớn.
- Complex aggregations.
- Write/index maintenance.
- Compaction/repair.
- Encryption/compression.
- Retry storm.
- Data skew.

Tùy nguyên nhân, giải pháp là index/query rewrite, giới hạn batch, thêm capacity, sửa retry hoặc phân vùng tốt hơn. Không tự tăng driver pool/concurrency khi CPU đã chạm giới hạn.

## 48. Tại sao average latency có thể đánh lừa?

Một tập 1.000 requests:

~~~text
990 requests complete in 10 ms
10 requests complete in 1,000 ms
```

Average:

\[
E[T]=(990\times10+10\times1000)/1000=19.9\text{ ms}
\]

Nghe rất tốt, nhưng 1% requests phải chịu khoảng một giây. Tùy estimator, p99 có thể ở vùng ranh giới giữa 10 ms và 1.000 ms; p99.9 chắc chắn bộc lộ nhóm đuôi trong tập minh họa.

Đừng chỉ báo mean hoặc p50. Theo dõi p95/p99, **fraction exceeding deadline** và error rate.

## 49. Không lấy trung bình p99 của các pods

Ba API pods có:

~~~text
Pod A: p99  30 ms, 10,000 requests
Pod B: p99 300 ms,    100 requests
Pod C: p99  50 ms,  5,000 requests
```

Trung bình ba p99 không phải p99 tổng của 15.100 requests. Cần aggregate **request-level samples hoặc histograms có cùng bucket definitions**, sau đó tính quantile đúng.

Đồng thời giữ per-pod/per-shard p99 để phát hiện điểm nóng bị trung bình hóa.

## 50. Queue wait p99 và end-to-end p99

Một common mistake:

~~~text
p99(poolWait)=200ms
p99(DBExecution)=100ms
therefore p99(total)=300ms
```

Phân vị của tổng **không bằng tổng các phân vị** theo cách tổng quát, do correlation giữa các spans. Muốn biết p99 end-to-end, đo end-to-end histogram trực tiếp; spans giúp tìm nguyên nhân.

## 51. Không bỏ timeout khỏi histogram

Một benchmark báo:

~~~text
Offered 10,000 requests
Succeeded 8,000
Timed out 2,000
p99 of successes = 40ms
```

Không thể nói “99% requests hoàn thành trong 40 ms”. 20% requests không thành công.

Cần báo:

- Offered attempts.
- Unique business requests.
- Successful throughput.
- Business rejection rate.
- Timed-out/rejected rate.
- User-facing latency/deadline violations.
- In-flight và queue trajectory.

Timeout có thể khiến measured p99 success **đẹp lên giả tạo** khi requests chậm nhất bị loại bỏ.

## 52. Open-loop và closed-loop load tests

**Closed-loop:** mỗi client gửi request tiếp sau khi request trước kết thúc. Khi hệ chậm, client tự giảm offered rate.

**Open-loop:** phát theo arrival schedule đặt trước, độc lập với tốc độ response, giúp nhìn rõ queue/saturation.

Hai cách có giá trị khác nhau; phải hiểu thử nghiệm đang mô phỏng user behavior hay kiểm capacity tại arrival rate cụ thể.

**Coordinated omission** xuất hiện khi tool không ghi nhận những requests đáng ra đến trong lúc server pause, làm tail latency bị đánh giá thấp. Chọn generator/recording policy phù hợp.

## 53. “Steady state” phải có queue ổn định

Một test chạy năm phút ở 10.000 RPS và thấy p99 50 ms nhưng backlog CDC tăng 1 triệu records không phải steady state cho pipeline đó.

Điều kiện quan sát steady state có thể gồm:

- Input/output rates gần cân bằng theo scope.
- No unbounded queue growth.
- Replication lag bounded and recovering.
- Driver pool không tích tụ waiters vô hạn.
- Error/timeout không tăng theo thời gian.
- CPU/IO/memory ổn định trong giai đoạn đủ dài.
- Time-to-drain sau burst phù hợp SLO.

Không buộc mọi queue luôn bằng 0; mục tiêu là **ổn định trong bound**.

## 54. Triệu chứng “throughput plateau”

Khi tăng offered RPS từ 5.000 lên 20.000:

~~~text
Offered:   5k   8k  10k  12k  15k  20k
Completed: 5k   8k   9k   9k   8k   7k
p99:      20ms 40ms 100ms 500ms timeout...
~~~

Đây là dấu hiệu capacity knee/saturation. Nếu arrival rate vượt completion rate, queue/timeout sẽ tăng trừ khi admission control reject sớm.

Một load generator có retries có thể làm **effective DB attempts** tăng nhanh hơn offered unique business requests.

## 55. Trình tự xác định bottleneck

Bắt đầu từ user-facing SLO, không từ một đồ thị CPU bất kỳ:

1. **Xác định symptom:** endpoint nào, p99/error/tỷ lệ timeout từ lúc nào?
2. **Đối chiếu input:** RPS, mix, payload, tenant cohorts có đổi không?
3. **Xem offered vs completed:** backlog có tăng không?
4. **Nhìn queue age/wait theo lớp:** HTTP, executor, pool, DB, CDC.
5. **Xem tài nguyên bị bão hòa:** CPU, IO, network, connection/locks.
6. **Tách operation types:** point reads, scans, writes, transactions.
7. **Kiểm query plans/slow queries/hot partitions.**
8. **Kiểm retries, failover, cache miss, background work.**
9. **Xác minh business correctness và source freshness.**
10. **Đề xuất thay đổi nhỏ có kiểm soát, so lại cùng workload.**

Đừng chuyển ngay tới “tăng max pool”, “thêm replicas” hay “bật cache dài hơn” trước khi xác định hàng đợi tăng ở đâu.

## 56. Một bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Bằng chứng cần thêm |
|---|---|---|
| HTTP p99 cao, DB RTT thấp | App/driver queue | Executor wait, checkout histogram |
| Pool checked out=max, DB CPU thấp | Pool undersized, session leak, slow external hold | Connection lifecycle, in-flight |
| Pool wait cao, DB CPU/IO cao | Server bottleneck gây giữ connection lâu | Query plan, disk queue, server exec |
| DB CPU thấp, disk latency cao | I/O-bound | IOPS, fsync, page faults, compaction |
| Một shard lag, các shard khỏe | Hot partition/key | Per-shard throughput, key distribution |
| Cassandra coordinator timeout | Replica unavailable/slow, CL không đạt | Per-replica latency, consistency errors |
| DynamoDB throttling nhưng CPU không thấy | Managed service quota/hot key | Throttle reasons, capacity, key mix |
| Redis GET p99 cao | Event-loop/slow scripts, network, client queue | SLOWLOG, latency, pending commands |
| Kafka lag age tăng | Consumer/sink chậm hoặc poison record | Per-partition lag, retry/DLQ |
| Replication lag tăng nhưng writes ACK | Follower apply lag | Secondary IO/CPU, log positions |
| Queue giảm cùng lúc timeout tăng | Work dropped/expired | Success vs rejected/timeout |
| p99 tăng sau deploy | Pool/GC, new query path, cache cold | Diff config, traces, load cohorts |

Đây là **bản đồ giả thuyết**, không phải kết luận tự động.

## 57. Một runbook thực tế

~~~text
ALERT: Product GET p99 > 250ms for 10 minutes

Check:
  1. Is error/timeout rate elevated?
  2. Is incoming RPS or key skew changed?
  3. Are Java executor and driver pool queues growing?
  4. Are MongoDB selected nodes healthy?
  5. Is DB operation time or pool wait dominant?
  6. Any index-plan regression, lock or IO pressure?
  7. Is cache hit ratio down or stampede occurring?
  8. Are retries amplifying load?
  9. Is there a single tenant/shard affected?
 10. Are requests being dropped or timing out?

Mitigate:
  - rate-limit excessive/batch traffic
  - stop noncritical heavy scans if safe
  - bound retries and concurrency
  - route/bypass cache only if correctness allows
  - add capacity when bottleneck confirmed
  - roll back regressed query/deployment

Verify:
  - queue age falls
  - p99 and success rate recover
  - DB/replica/CDC backlogs catch up
  - no data/correctness regression
~~~

Không áp runbook vào hệ thật mà bỏ qua quyền vận hành, SLO và data consistency policy.

## 58. MongoDB: nhìn đúng tầng chờ

Với MongoDB Java driver, một request có thể chờ:

- Server selection vì chưa tìm thấy primary/secondary đủ điều kiện.
- Connection checkout trong pool của selected server.
- Network I/O/response decoding.
- Database execution, lock/CPU/disk/query planner.
- Write concern và replication acknowledgment.
- Retry sau topology change/step-down.
- Transaction commit và conflict handling.

Một driver có thể có pool riêng cho nhiều servers; **maxPoolSize** không nhất thiết là một giới hạn connections toàn ứng dụng cho toàn cluster. Đọc chính xác semantics của driver version và topology.

## 59. MongoDB: tín hiệu pool và server-side

Ở phía client, nên ghi:

- Connection checked out/current available.
- Checkout started/succeeded/failed.
- Checkout wait histogram.
- Connection created/closed.
- Command started/succeeded/failed duration.
- Server selection timeouts và topology changes.
- Retry attempts.

Ở phía server, nên xem:

- Operations throughput và latency.
- CPU, filesystem IO, cache hit/miss.
- Connections, queued operations khi metric hỗ trợ.
- Active/queued reads/writes tùy version/engine.
- Query plans, keys/docs examined.
- Lock contention, transactions đang mở.
- Primary/secondary lag.
- Per-shard data skew.

**Metric pool client không thay metric server**, vì chờ trong JVM xảy ra trước lúc server nhìn thấy request.

## 60. MongoDB Java: lắng nghe pool events

Driver cho phép đăng ký listeners khi xây settings. Ví dụ khung API:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.ConnectionPoolListener;
import com.mongodb.event.ConnectionCheckOutStartedEvent;
import com.mongodb.event.ConnectionCheckedOutEvent;
import com.mongodb.event.ConnectionCheckOutFailedEvent;

public final class MongoObservedClient {
    public static MongoClient create(String uri) {
        ConnectionPoolListener listener = new ConnectionPoolListener() {
            @Override
            public void connectionCheckOutStarted(
                    ConnectionCheckOutStartedEvent event) {
                // Counter: checkout requests started.
            }

            @Override
            public void connectionCheckedOut(
                    ConnectionCheckedOutEvent event) {
                // Counter: connections acquired.
            }

            @Override
            public void connectionCheckOutFailed(
                    ConnectionCheckOutFailedEvent event) {
                // Counter by bounded failure reason.
            }
        };

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applyToConnectionPoolSettings(b ->
                b.addConnectionPoolListener(listener))
            .build();

        return MongoClients.create(settings);
    }
}
~~~

Đây là mẫu minh họa Java MongoDB Sync Driver; loại event, import và API builder cần khớp driver version. Muốn đo checkout wait một cách đáng tin phải **tương quan start với success/fail cho request tương ứng** theo thông tin/IDs được API cung cấp hoặc dùng telemetry có sẵn — không gán một ThreadLocal ngây thơ trong hệ async rồi tin số liệu.

Đăng ký listener khi tạo shared MongoClient, không tạo MongoClient cho mỗi HTTP request.

## 61. MongoDB: chẩn đoán một query chậm

Giả sử endpoint GET Order p99 tăng. Lộ trình:

1. Lấy slow query samples theo collection/query shape.
2. Kiểm explain plan có scan/sort không.
3. Tách `docs examined`, `keys examined`, `nReturned`.
4. Kiểm document size và serialization time.
5. Kiểm pool wait vs server exec time.
6. Kiểm topology election/primary selection.
7. Kiểm một shard quá nóng hoặc scatter-gather.
8. Kiểm background index build, checkpoint, backup, compaction/IO.
9. Kiểm retries và write concern nếu operation là write.

Một `COLLSCAN` không tự là nguyên nhân trong mọi trường hợp (collection rất nhỏ có thể nhanh), nhưng trên tập lớn nó là giả thuyết cần đo.

## 62. MongoDB: transaction kéo dài giữ tài nguyên

Một transaction thực hiện:

~~~text
Read 10 documents
Wait 500ms for external API
Update 3 documents
Commit
```

Có thể gây:

- Snapshot/resource retention.
- Tăng conflicts/aborts.
- Connections/session dùng lâu hơn.
- Wait trong các requests khác.
- P95/p99 commit tăng.
- Retries làm source load cao hơn.

Giải pháp thường là rút ngắn transaction, bỏ external call khỏi transaction callback, dùng outbox/saga/idempotency và CAS cho invariant gói gọn một document.

## 63. Cassandra: coordinator, replicas và consistency wait

Trong Cassandra, một node **coordinator** nhận request và làm việc với replicas theo consistency level. Độ trễ có thể gồm:

~~~text
Java driver picks coordinator
Coordinator receives request
Coordinator contacts relevant replicas
Replicas read/write and respond
Coordinator satisfies consistency rule or times out
Java driver receives result
```

Một số loại waiting:

- Driver request throttling/queue.
- Connection capacity hoặc per-node in-flight cap.
- Coordinator admission/scheduler.
- Replica CPU/disk/compaction.
- Network giữa nodes/DC.
- Consistency-level quorum wait.
- LWT Paxos rounds.
- Repair/hints/background maintenance.

Không suy “coordinator CPU thấp” nghĩa replicas khỏe. Một replica chậm có thể làm LOCAL_QUORUM tail latency cao trong điều kiện nhất định.

## 64. Cassandra: hot partitions và large partitions

Một bảng theo partition key không cân bằng có thể gây:

- Một token range nhận nhiều reads/writes.
- Large partition scans.
- Tombstone scanning.
- Coordinator/replica timeouts.
- Pending compactions.
- High GC/heap pressure tùy triển khai.
- Retry/overload messages.

Cần phân tích query shape, partition size, tombstones, compaction, read/write latency per node và load-balancing policy.

**Thêm contact points** không chữa được partition key làm một key nóng; contact points chỉ phục vụ discovery/bootstrap.

## 65. Cassandra: consistency timeout khác unavailable

Một operation có thể thất bại vì:

- Không đủ eligible replicas để thực hiện consistency level: unavailable.
- Đã gửi yêu cầu tới các replicas nhưng không nhận đủ response trong deadline: timeout.
- Coordinator/server quá tải: overload.
- Client-side connection/pool throttling trước khi gửi.

Các lỗi có semantics riêng, nên đo/chẩn đoán riêng. Không retry tất cả như nhau; retry có thể làm tăng áp lực khi replicas đã quá tải. Với LWT, phải xét unknown outcome và idempotency.

## 66. Cassandra speculative execution

Một driver có thể chạy speculative execution cho những statement được phép, nghĩa là gửi thêm một attempt khi attempt đầu chậm.

Điều này có thể giảm tail latency một số reads **idempotent/safe**, nhưng tăng load lên cluster và có thể làm overload tệ hơn.

Cần:

- Chỉ áp khi operation semantics cho phép.
- Kiểm idempotency/side effects.
- Đo speculative attempts per logical request.
- So p99 cải thiện với QPS/CPU/IO tăng.
- Tắt/giới hạn khi backend saturated nếu policy phù hợp.

Không bật speculative execution vô điều kiện cho increment, payment hoặc non-idempotent write.

## 67. DynamoDB: giới hạn không lộ dưới dạng CPU host

DynamoDB là managed service. Java client thường không xem được CPU của physical partition nhưng có thể quan sát:

- Request latency/client RTT.
- Throttled requests/throttling reasons.
- Consumed read/write capacity units.
- Provisioned/on-demand limits.
- ConditionalCheckFailed (business conflict, không mặc định overload).
- HTTP connection pool wait và retries.
- Per-operation attempts.
- Hot partition-key access skew khi ứng dụng đo.
- Item size và Query page count.
- Error/retry budgets.

CPU 80% của một VM Java **không nói trực tiếp** DynamoDB service đã bão hòa; cần nhìn capacity/quota/throttling và request-level metrics.

## 68. DynamoDB: hot key vẫn có thể throttle

Một table có tổng capacity còn headroom nhưng một partition-key pattern quá nóng có thể tạo throttling theo cơ chế partition/adaptive capacity của dịch vụ.

Ví dụ:

~~~text
Tenant A key: 20,000 requests/s
Many small tenants: 100 requests/s each
```

Một thiết kế có thể cần:

- Distribute hot writes qua buckets nếu domain cho phép.
- Dùng keys truy vấn phù hợp access patterns.
- Batch/pagination đúng giới hạn.
- Cache read results được phép stale.
- Rate limit một hot tenant.
- Giảm conditional conflict hot key.
- Quan sát reasons/capacity để phân biệt quota table và partition hot spot.

Không tự nói biết physical partition IDs nếu service không công bố chúng qua API.

## 69. DynamoDB SDK v2: timeout và retries

Một Java application dùng AWS SDK v2 có thể có:

- API call timeout cho toàn operation.
- API attempt timeout cho từng attempt.
- HTTP client connection acquisition timeout.
- Retry policy/backoff.
- Connection pooling/keep-alive.
- Region endpoint và IAM signing.

Khi cấu hình, cần bảo đảm **request deadline lớn hơn hoặc tương thích** với attempt budget. Không cài 30-second SDK retries trong HTTP request chỉ có deadline 1 second mà không quản lý cancellation/outcome.

Một `ProvisionedThroughputExceeded` hoặc throttling signal không nên dẫn tới retry vô hạn; một `ConditionalCheckFailedException` thường phản ánh condition nghiệp vụ không đạt, không tự là server overload.

## 70. DynamoDB: Query page amplification

Một request HTTP có thể gọi nhiều paginated DynamoDB Query/Scan operations:

~~~text
HTTP GET /reports
  Query page 1
  Query page 2
  Query page 3
  ...
  Query page 100
```

Một request HTTP = 100 API calls; tổng call count tăng dù incoming RPS không tăng. Cần đo:

- Pages per business request.
- RCUs/read units per request.
- Item sizes.
- Total server-side scans/filters.
- Pagination cursor lifecycle.
- Client concurrency.
- Whether Scan is appropriate for interactive traffic.

Giảm page count/index/query shape có thể chữa queue pressure tốt hơn tăng connection pool.

## 71. Redis: single-command latency và client backlog

Redis thường có event loop thực thi command logic chính theo kiến trúc của phiên bản triển khai. Dù một số version có I/O threads và cơ chế khác, **long-running commands/scripts** vẫn có thể gây head-of-line blocking trên đường xử lý tương ứng.

Các dấu hiệu:

- Redis command latency tăng.
- SLOWLOG chứa costly commands.
- CPU high hoặc event loop latency spikes.
- Client buffers và pending commands tăng.
- Connection churn / network issues.
- Evictions, fragmentation/OOM.
- Large keys và massive result payloads.

Không kết luận Redis khỏe chỉ vì `PING` nhanh hoặc hit ratio cao; workload thực có thể dùng Lua/SCAN/sort operations nặng.

## 72. Redis client queue và Redis server work khác nhau

Một Lettuce/Redis Java client có thể có nhiều commands đang chờ phản hồi; server cũng có hàng chờ network/event processing.

Nếu Java đo:

~~~text
Redis command RTT p99 = 400ms
SLOWLOG shows few slow operations
```

Có thể có:

- Network latency/packet loss.
- Client event-loop blocked.
- Huge response serialization.
- Connection/pending command congestion.
- Redis server pausing vì persistence/fork/GC-like mechanisms khác.
- Commands waiting trước khi được thực thi mà không nằm trong SLOWLOG execution duration.

Cần so client span với server latency telemetry và runtime event-loop/pool metrics; SLOWLOG không bao quát mọi nguồn delay.

## 73. Redis Pub/Sub, Streams và durability

Không gộp:

- Redis command queue.
- Redis Streams Pending Entries List.
- Pub/Sub subscribers.
- Cache refresh workers.
- NoSQL source replication lag.

Một Redis Streams consumer group có thể có pending messages đã giao nhưng chưa ACK. Số pending tăng có thể do slow consumer, crash hoặc chưa claim. Cần theo dõi consumer pending age, retry/reclaim, stream retention và idempotent sink effects.

Một queue có lag bằng 0 vì messages bị trim quá sớm **không chứng minh không mất dữ liệu**.

## 74. Search indexing cũng có queue

Trong hệ NoSQL phục vụ search, outbox/CDC → Search có thể gây:

- Bulk indexing queue.
- Refresh/merge backlog.
- Shard hot spots.
- Thread pool rejections.
- Visibility lag.
- Disk IO saturation.
- Mapping/index maintenance cost.

API index thành công nhưng search query chưa thấy data do refresh semantics không phải cùng chỉ số với “DB write latency”. Cần đo **commit-to-visible time** và age của Search projection, không chỉ queue length.

## 75. Đồng bộ nhiều tầng: đo điểm “nợ” dữ liệu

Một thay đổi Product:

~~~text
Source commit
  -> Outbox pending
  -> Kafka partition backlog
  -> Consumer in-flight
  -> Search indexing
  -> Search refresh
  -> API reads visible
```

Sự chậm có thể ở bất kỳ chặng nào. Một dashboard hữu ích theo dõi:

- Source commit version/time.
- Outbox pending/oldest age.
- Broker lag per partition.
- Consumer processing time/retries.
- Search index ACK latency.
- Search refresh visibility lag.
- Source vs projection version gap.

Không đo chỉ event publication latency rồi gọi toàn bộ “data freshness”.

## 76. Java: giới hạn đồng thời bằng Semaphore

Một tầng bảo vệ trước Repository:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class GuardedProductReader {
    private final Semaphore permits = new Semaphore(64);
    private final ProductRepository repository;

    public GuardedProductReader(ProductRepository repository) {
        this.repository = repository;
    }

    public Product read(String key) throws InterruptedException {
        boolean acquired = permits.tryAcquire(
            30, TimeUnit.MILLISECONDS);

        if (!acquired) {
            throw new CapacityRejectedException(
                "NoSQL read concurrency limit reached");
        }

        try {
            return repository.findByKey(key);
        } finally {
            permits.release();
        }
    }
}
~~~

`ProductRepository`, `Product` và `CapacityRejectedException` là domain types minh họa; đây là skeleton, chưa đủ để biên dịch nếu chưa định nghĩa chúng. `64` và `30 ms` chỉ là thông số giả định.

Những điểm cần giữ:

- Giới hạn concurrency trước khi gọi DB.
- Chỉ release permit nếu đã acquire.
- Bounded wait và cancellation.
- Distinguish capacity rejection from business not-found.
- Không retry rejected requests vô hạn.
- Dùng metrics cho available permits, acquire wait và rejected count.

Semaphores per JVM **không tự là global quota** khi service có nhiều pods; phải tính số pods nhân giới hạn và DB capacity.

## 77. Java: bounded executor

Ví dụ `ThreadPoolExecutor` với queue có giới hạn:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor pool = new ThreadPoolExecutor(
    8,
    16,
    60,
    TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(200),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Khi pool và queue đầy, task có thể bị từ chối bằng `RejectedExecutionException` theo policy, thay vì RAM tăng vô hạn. Application phải map rejection thành outcome phù hợp và đảm bảo task quan trọng chưa commit được durable-enqueue trước khi ACK upstream.

Đừng chạy cùng một executor cho long analytics jobs và latency-critical reads mà không xét head-of-line blocking.

## 78. CallerRunsPolicy không phải thuốc chữa mọi queue

Một executor có `CallerRunsPolicy` có thể chạy task ngay trên thread gọi khi pool bão hòa. Điều này tạo backpressure trong một số pipeline, nhưng trong HTTP server/event-loop nó có thể:

- Block event-loop.
- Giảm khả năng xử lý connections.
- Tạo request timeouts dây chuyền.
- Gây deadlock nếu task phụ thuộc chính executor ấy.

Chọn rejection/backpressure policy theo thread model. Không bật `CallerRunsPolicy` chỉ để tránh exceptions.

## 79. Java: đo từng phần của Repository call

Một skeleton thu thập histogram:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class ObservedRepository {
    private final ProductRepository delegate;
    private final MeterRegistry meters;

    public ObservedRepository(
            ProductRepository delegate, MeterRegistry meters) {
        this.delegate = delegate;
        this.meters = meters;
    }

    public Product find(String key) {
        long started = System.nanoTime();
        String outcome = "success";

        try {
            return delegate.findByKey(key);
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            long elapsedNanos = System.nanoTime() - started;
            Timer.builder("nosql.repository.duration")
                .tag("operation", "product_find")
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(meters)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

`ProductRepository` và `Product` là giả định; cấu hình meter registry và cardinality cần được tối ưu theo ứng dụng. Nếu đồng thời muốn đo pool wait, cần instrumentation của driver tương ứng; wrapper này đo **toàn bộ thời gian Repository call**, không tự tách pool wait và server execution.

Dùng `System.nanoTime()` để đo elapsed time, không làm timestamp so sánh giữa nodes.

## 80. Micrometer gauges cho executor

Các chỉ số có thể export:

~~~text
java_executor_active_threads
java_executor_queue_depth
java_executor_task_completed_total
java_executor_task_rejected_total
java_executor_queue_wait_seconds
```

Đây là **tên metric minh họa**, không nhất thiết là tên mặc định của Micrometer binder. Một số fields có thể lấy từ `ThreadPoolExecutor.getActiveCount()`, `getQueue().size()` và `getCompletedTaskCount()`, nhưng queue wait histogram cần đo thời điểm enqueue/dequeue hoặc dùng binder/hook phù hợp.

Đừng tự xem `completedTaskCount` là business successes nếu tasks có thể fail.

## 81. Micrometer và OpenTelemetry spans

Một trace có thể gồm:

~~~text
HTTP GET /orders/{id}          320ms
  auth                           5ms
  app semaphore wait            90ms
  MongoDB pool checkout        160ms
  MongoDB command RTT           60ms
  serialize response             5ms
```

Mỗi span/metric phải có scope:

- Start/end time.
- Backend/operation name.
- Outcome/retry attempt.
- Pool/server/region identity khi được phép.
- Trace ID để correlate.
- Bound tag cardinality.

Tránh gắn raw orderId, email, token hay full SQL/NoSQL payloads lên metric labels.

## 82. Một metric contract thống nhất

Ví dụ:

~~~text
http_requests_total{route,result}
http_request_duration_seconds_bucket{route,le}

app_queue_depth{queue}
app_queue_wait_seconds_bucket{queue,le}
app_rejected_total{queue,reason}
app_inflight_requests{route}

nosql_operation_total{engine,operation,result}
nosql_operation_duration_seconds_bucket{engine,operation,le}
nosql_pool_checkout_wait_seconds_bucket{engine,pool,le}
nosql_pool_in_use{engine,pool}
nosql_retry_attempts_total{engine,operation}
nosql_timeouts_total{engine,stage}

cdc_unprocessed_records{pipeline,partition_group}
cdc_oldest_unprocessed_age_seconds{pipeline}
replication_apply_lag_seconds{cluster,replica_group}
```

Tên/cấu trúc là gợi ý. Một số engine chỉ có metrics tương đương; không ép đo sai hoặc giả định các API cung cấp tất cả.

Không dùng raw key hoặc high-cardinality tenant IDs làm Prometheus labels. Dùng cohort, fixed classification và traces có quyền truy cập cho chẩn đoán chi tiết.

## 83. PromQL: request arrival rate

Nếu có counter:

~~~promql
sum by (route) (
  rate(http_requests_total{result=~"success|business_reject|error"}[5m])
)
~~~

Đây là arrival/completed **events được instrument** theo semantics counter. Nếu metric chỉ được tăng khi response kết thúc, `rate` là completion rate, không phải thật sự arrival rate. Muốn arrival, tăng counter **khi request bắt đầu**; đo completed counter riêng.

Tên metric không tự chứng minh thời điểm increment.

## 84. PromQL: p99 end-to-end

Với classic histogram:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, route) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

Cần buckets phù hợp SLO, cùng units, và aggregation đúng. Không lấy mean của instance-level p99 làm global p99.

Nếu tool dùng native histogram hoặc client library khác, cú pháp có thể thay đổi.

## 85. PromQL: checkout wait p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le, engine, pool) (
    rate(nosql_pool_checkout_wait_seconds_bucket[5m])
  )
)
~~~

Nếu không có histogram riêng, bạn không thể suy checkout wait p95 từ `connections_in_use` đơn thuần. Cần instrumentation trước khi kết luận pool saturation.

## 86. PromQL: successful vs attempted rates

~~~promql
sum(rate(nosql_operation_total{
  engine="mongodb", result="success"
}[5m]))
~~~

So với:

~~~promql
sum(rate(nosql_operation_total{
  engine="mongodb"
}[5m]))
~~~

Mẫu số gồm tất cả outcomes được instrument trong bộ metric. Nếu mỗi retry attempt tăng cùng counter, đây là **attempt-level success ratio**, không phải unique business-request success ratio. Nên có thêm counter tăng mỗi business intent.

## 87. PromQL: retry amplification

Nếu metric semantics nhất quán:

~~~promql
sum(rate(nosql_attempts_total[5m]))
/
sum(rate(business_intents_started_total[5m]))
~~~

Mức tỷ lệ lớn hơn 1 có thể do retries **hoặc do một business intent vốn gọi nhiều DB operations**. Để đo retry amplification riêng, nhóm theo operation type hoặc so **attempt count với first-attempt count cho cùng logical DB operation**.

Không phát ngôn “ratio 3 nghĩa retries gấp ba” nếu một checkout tự nhiên gọi ba queries.

## 88. PromQL: queue depth và queue age

Queue depth thường là gauge:

~~~promql
sum by (queue) (app_queue_depth)
~~~

Cẩn thận: chỉ cộng gauges của **các partitions/workers độc lập**; không cộng queue stages cùng request rồi coi là unique tasks.

Oldest age gauge có thể biểu diễn:

~~~promql
max by (pipeline) (
  cdc_oldest_unprocessed_age_seconds
)
~~~

`max` giúp phát hiện partition lâu nhất thay vì giấu nó trong average. Phải có alert nếu oldest age gần vượt event log retention hoặc freshness SLO.

## 89. Queue slope và saturation trend

Một dấu hiệu sớm:

~~~text
arrival rate         8,000/s
completion rate      7,500/s
queue depth          growing steadily
queue wait p95       increasing
error rate           still low
```

Khi queue liên tục tăng, dù errors chưa tăng, đây là **pre-overload symptom**. Cần giảm input/đẩy backpressure hoặc tăng capacity hợp lệ trước khi toàn bộ requests chạm deadline.

Không chỉ alert khi queue depth vượt số cố định: một hệ có 100 jobs/s và một hệ 100.000 jobs/s có tuổi backlog khác nhau.

## 90. Alert có điều kiện, tránh false alarm

Ví dụ quy tắc vận hành (không phải giá trị mặc định phổ quát):

~~~text
Warning:
  queue age > 2x normal baseline
  AND arrival > completion
  sustained for 5 minutes

Critical:
  p99 exceeds SLO
  AND timeout rate > threshold
  OR CDC oldest age approaches log retention margin
```

Ngưỡng phải dựa trên baseline, traffic, SLO và failure mode. Một queue tăng rất nhanh trong 10 giây peak có thể nghiêm trọng hơn queue tăng nhẹ trong 5 phút.

Alerts nên kết hợp **symptom (SLO)** và **cause indicators (queue/resource)** để giảm paging noise.

## 91. Topology failover có thể tạo spikes

Một leader/primary đổi vai trò:

~~~text
Old leader steps down
Driver server selection waits
Retry attempts accumulate
New leader elected
Queued work flushes to new leader
```

Ngay cả sau khi failover hoàn tất, **retry burst** có thể làm new leader quá tải.

Để giảm:

- Bounded retries with jitter.
- Per-client concurrency limits.
- Admission controls.
- Topology-aware driver configuration.
- Idempotent business commands.
- Observability of unknown commit results.
- Không mở một lượng connections mới vô hạn sau failover.

## 92. Multi-region queue amplification

Khi application region A không tới được DB writer region B, nhiều requests có thể timeout rồi retry qua alternate region.

Rủi ro:

- WAN RTT tăng.
- Duplicate write intents.
- Cross-region replication lag.
- Different consistency/conflict policies.
- Queue growth ở fallback region.
- Throttle/quota và data residency violations.

Chuyển endpoint sang region khác không tự giải quyết consensus/quorum hoặc transactional guarantees. Phải có runbook và routing policy đã kiểm thử.

## 93. Làm sao chọn max concurrency?

Một cách xây dựng:

1. Đo capacity server tại các levels offered load.
2. Tìm mức giữ p99/error/freshness trong SLO.
3. Đo số in-flight cần để đạt throughput đó.
4. Đặt per-instance cap có headroom và tính tổng số pods.
5. Dùng bounded waiting cho burst ngắn.
6. Xem phân bố read/write/transaction/cold query.
7. Re-evaluate khi thay shard/instance size hoặc driver.

Một xấp xỉ theo Little's Law:

\[
L \approx \text{throughput}\times\text{mean latency}
\]

Ví dụ 4.000 ops/s × 25 ms ≈ 100 in-flight. Đây là **ước lượng điểm vận hành**, không phải công thức trực tiếp đặt max concurrency 100 cho mọi workload. Burst, p99, service variability và queue scope cần đo thực nghiệm.

## 94. Bounded waiting phải nhỏ hơn deadline

Một request có total deadline 250 ms:

~~~text
App queue wait cap:       20 ms
Pool checkout wait cap:   30 ms
DB operation timeout:    150 ms
Response/serialization:  20 ms
Reserve for jitter:       30 ms
```

Đây chỉ là ví dụ phân bổ budget; các giai đoạn có thể overlap hoặc retry. Nhưng một rule quan trọng: không để request xếp hàng 500 ms khi client sẽ hủy sau 250 ms.

Nếu async cancellation không được truyền xuống driver, phần việc đã vô ích có thể tiếp tục chiếm DB capacity.

## 95. Reject sớm đôi khi tốt hơn timeout muộn

Hai phương án dưới overload:

**Không giới hạn queue**

~~~text
100% requests accepted
70% timeout after 10 seconds
Origin and heap saturated
```

**Bounded queue + admission**

~~~text
70% requests accepted and handled within SLO
30% rejected quickly with retry advice
Origin remains healthy
```

Không tự nói phương án thứ hai “tốt hơn” cho mọi nghiệp vụ; phải xét user experience, retries, SLAs và durable commands. Nhưng từ chối sớm có thể tránh **cascading failure** và bảo vệ phần traffic quan trọng.

## 96. Circuit breaker có tác dụng gì?

Nếu database đang liên tục lỗi/timeout, circuit breaker có thể mở để một số requests không tiếp tục được gửi xuống backend. Nó thường đi cùng:

- Error threshold/window.
- Half-open probes.
- Maximum wait/recovery policy.
- Fallback theo business consistency.
- Metrics cho open/rejected/probe.
- Backoff để tránh đồng loạt half-open rush.

Không dùng cache stale làm fallback cho quyền truy cập hoặc chuyển tiền nếu policy đòi dữ liệu hiện hành. Circuit breaker **không thay authoritative write validation**.

## 97. Queue trong source vs sink: một ví dụ đầy đủ

Giả sử Order API:

~~~text
Client sends 1,000 checkout/s
API admission cap: 200 in flight
MongoDB orders/index write p99 rises
Outbox publisher produces 1,000 events/s
Kafka consumer handles 800 events/s
Search index handles 600 updates/s
```

Đây có thể là hai bottlenecks:

1. Checkout write path ở MongoDB.
2. Search projection indexing backlog.

Tăng MongoDB instance có thể chữa (1), nhưng làm producer nhanh hơn có thể khiến (2) xấu hơn. Cần **capacity plan end-to-end** và queue SLO riêng cho mỗi hop.

## 98. Khác biệt giữa queue và transaction conflict

Transaction bị abort do `version` mismatch có thể không phải server overload: đó là kết quả **optimistic concurrency control** hợp lệ.

Nhưng một hot aggregate tạo hàng nghìn abort/s gây **retry load** và server saturation.

Do vậy cần tách:

- Business conditional rejection.
- Optimistic write conflict.
- Transient transport timeout.
- Overload/throttling.
- Unknown commit outcome.
- Durable queue DLQ disposition.

Nếu trộn tất cả vào `db_errors_total`, rất khó chọn biện pháp: retry có thể tốt cho transport transient nhưng sai cho sold-out/duplicate.

## 99. Idempotency giúp retry an toàn nhưng không giảm tải miễn phí

Một idempotency key có thể chặn business effect trùng, nhưng mỗi retry vẫn có thể:

- Đi tới API.
- Lấy DB connection.
- Đọc idempotency record.
- Chạy condition check.
- Gửi network traffic.

Vì vậy vẫn cần backoff, admission, payload/request validation và caching idempotency outcomes khi phù hợp.

Không xem “đã có idempotency key” là giấy phép retry không giới hạn.

## 100. Một dashboard điều tra nên đặt cạnh nhau

Gợi ý bố cục theo thời gian:

| Hàng đồ thị | Chỉ số cần xem |
|---|---|
| 1. User impact | HTTP p95/p99, error rate, SLO violations |
| 2. Traffic | Incoming RPS, successful RPS, data sizes, retries |
| 3. App queue | Depth, oldest age, wait p95/p99, rejects |
| 4. Driver | Pool in-use, acquisition wait, selection errors |
| 5. DB execution | RTT, query durations, slow operations |
| 6. Resources | CPU, IO queues, network, memory, locks |
| 7. Distribution | Per-shard/tenant/operation mix |
| 8. Async | Outbox/Kafka/CDC lag, replica apply lag |
| 9. Correctness | Unknown commits, duplicate effects, stale projection |
| 10. Change events | Deploys, scaling, index builds, failures |

**Cùng timeline** giúp nhận biết một index build bắt đầu trước p99 spike, hay timeout spike dẫn tới retries tăng rồi DB bão hòa.

## 101. Tracing sampling có thể che sự cố hiếm

Nếu chỉ sample 1% traces ngẫu nhiên, một lỗi tail hiếm có thể bị bỏ sót. Có thể kết hợp:

- Metrics đầy đủ theo counters/histograms.
- Tail-based sampling cho những traces chậm/lỗi theo khả năng hệ.
- Exemplars từ latency histograms.
- Logs có correlation IDs.
- Targeted diagnostic sampling theo route/region.
- Không log PII/secrets.

Không thay toàn bộ telemetry bằng request logs của mọi key; log volume quá lớn có thể làm ứng dụng chậm thêm.

## 102. Điều tra sự cố theo nhân quả thời gian

Một ví dụ:

~~~text
09:00 Deploy changed cache TTL
09:02 Cache hit ratio drops
09:03 MongoDB reads increase 8x
09:04 Driver checkout wait rises
09:05 HTTP p99 exceeds SLO
09:06 Retry volume doubles
09:07 DB CPU/disk saturates
```

Giả thuyết hợp lý là cache miss amplification gây tải nguồn, sau đó retries khuếch đại. Nhưng cần chứng minh bằng:

- Same traffic cohort.
- Actual origin query count.
- Cache error/TTL metrics.
- Query mix.
- No independent index/build/failover incident.

**Tương quan cùng thời điểm không luôn là nguyên nhân**, song timeline giúp ưu tiên điều tra đúng hơn việc nhìn từng biểu đồ độc lập.

## 103. Fault injection cho hàng đợi

Các bài test trong môi trường được phép:

- Tăng DB latency 50→500 ms.
- Tạm thời giới hạn connection pool.
- Thả một burst gấp 3 traffic.
- Làm một replica chậm.
- Khởi động index build/background scan.
- Gây Kafka consumer rebalance.
- Mô phỏng một hot key.
- Làm Redis timeout để ép cache fallback.
- Mất ACK sau commit.
- Thử client cancellations.

Đo queue trajectory, p99, load shedding, retry budget và **invariant correctness**. Có kill switch để kết thúc test không làm hỏng môi trường.

## 104. Bài tập A — Queue growth

Incoming 1.500 jobs/s, completed 1.200 jobs/s trong 60 giây, không reject/cancel.

**Hỏi:** backlog tăng xấp xỉ bao nhiêu?

**Hướng giải:** \((1500-1200)\times60=18.000\) jobs.

## 105. Bài tập B — Little's Law

Hệ ổn định ở 2.000 completed requests/s, mean response time 50 ms.

**Hỏi:** average in-flight?

**Hướng giải:** \(L=\lambda W=2000\times0.05=100\) requests.

## 106. Bài tập C — Chờ trong pool

HTTP GET mất 300 ms; pool checkout wait 220 ms, DB command RTT 20 ms.

**Hỏi:** có nên thêm index trước?

**Hướng giải:** chưa đủ bằng chứng. Phần chờ pool chiếm đa số; kiểm pool usage, long-running operations, leaks và backend headroom trước.

## 107. Bài tập D — CPU thấp nhưng p99 cao

Cluster CPU trung bình 30%, một shard có 100% disk IO và lag lớn.

**Hỏi:** có quá tải không?

**Hướng giải:** có thể bão hòa cục bộ ở disk/hot shard. Average cluster CPU không loại trừ.

## 108. Bài tập E — Tăng pool

Driver pool 50 connections đang đầy; DB CPU 99%, disk IO queue tăng.

**Hỏi:** tăng pool lên 500 chắc cải thiện?

**Hướng giải:** không; có thể tăng request concurrency và làm server quá tải hơn. Cần giảm query work, concurrency và xác minh capacity.

## 109. Bài tập F — Retry amplification

1.000 business requests/s tạo trung bình 2,5 DB attempts.

**Hỏi:** attempts/s?

**Hướng giải:** 2.500/s, nếu mẫu số và một attempt được định nghĩa nhất quán.

## 110. Bài tập G — Pool vs selection

Trong MongoDB election, driver không chọn được eligible primary.

**Hỏi:** đây là lỗi thiếu maxPoolSize?

**Hướng giải:** không. Server selection/topology không có primary phù hợp; tăng pool không giải quyết.

## 111. Bài tập H — Queue giảm sau overload

Queue depth từ 10.000 xuống 100, cùng lúc timeout rate tăng từ 0% lên 80%.

**Hỏi:** có nên tuyên bố đã hồi phục?

**Hướng giải:** không. Requests có thể đang hết hạn/bị hủy, không được xử lý thành công. Xem successful throughput và SLO.

## 112. Bài tập I — L1 cache outage

10.000 eligible reads/s, cache hit ratio giảm từ 98% xuống 80%, mỗi miss tạo một source read.

**Hỏi:** origin RPS tăng thế nào?

**Hướng giải:** từ khoảng 200/s lên 2.000/s, tăng 10 lần trong mô hình giả định.

## 113. Bài tập J — CDC lag

Event production 30.000/s; consumer apply 25.000/s trong 2 phút.

**Hỏi:** backlog tăng bao nhiêu?

**Hướng giải:** \(5.000\times120=600.000\) records, nếu không có drop/retention/replay thay đổi.

## 114. Bài tập K — p99 vs mean

990 requests 10 ms, 10 requests 1.000 ms.

**Hỏi:** mean khoảng bao nhiêu? Mean có đại diện người chậm nhất không?

**Hướng giải:** 19,9 ms; không, cần tail quantiles và deadline violations.

## 115. Bài tập L — M/M/1

Giả định \(\mu=100\) jobs/s, \(\lambda=95\) jobs/s trong M/M/1.

**Hỏi:** mean system time theo mô hình?

**Hướng giải:** \(1/(100-95)=0,2\) s = 200 ms, dù service time khi không chờ là 10 ms.

## 116. Bài tập M — MongoDB query plan

Sau khi data tăng, một GET bắt đầu scan 1 triệu docs. Pool wait tăng theo.

**Hỏi:** nên tối ưu yếu tố nào trước?

**Hướng giải:** tìm nguyên nhân service time/query work, xem index/query shape. Pool wait có thể là hậu quả connections bị giữ lâu.

## 117. Bài tập N — Cassandra LOCAL_QUORUM

Coordinator nhận đủ request nhưng replica chậm khiến LOCAL_QUORUM timeout.

**Hỏi:** có nhất thiết thiếu contact points không?

**Hướng giải:** không. Cần xem per-replica health, consistency level, network/IO và coordinator load.

## 118. Bài tập O — DynamoDB throttling

SDK nhận throttling trong khi Java CPU thấp.

**Hỏi:** đây có thể là bottleneck managed service không?

**Hướng giải:** có. Kiểm consumed capacity, throttling reasons, hot partition-key pattern và retry policy.

## 119. Bài tập P — Redis SLOWLOG trống

Redis RTT p99=500 ms, SLOWLOG gần trống.

**Hỏi:** server chắc khỏe?

**Hướng giải:** không. Client/network/event loop/queues hoặc latency ngoài command execution vẫn có thể lớn.

## 120. Bài tập Q — Kafka oldest age

Kafka partition P0 có 100 records lag nhưng event già nhất 3 giờ; P1 có 100.000 records lag nhưng event già nhất 5 giây.

**Hỏi:** nên ưu tiên điều tra theo lag count tổng không?

**Hướng giải:** không. Xem age/SLO, stream retention, processing cost và partition semantics. P0 có thể nghiêm trọng hơn dù backlog count nhỏ.

## 121. Bài tập R — ThreadPoolExecutor bounded queue

Executor có 8–16 workers và queue tối đa 200. Khi overload, AbortPolicy ném RejectedExecutionException.

**Hỏi:** xử lý ở API thế nào?

**Hướng giải:** trả capacity rejection có semantics phù hợp (ví dụ 503/429 tùy policy), ghi metric, không để task durable bị mất/ACK trước commit.

## 122. Bài tập S — CallerRuns trên event loop

Executor bị đầy; CallerRunsPolicy chạy một query blocking trên event-loop HTTP thread.

**Hỏi:** rủi ro?

**Hướng giải:** block event loop, giảm throughput và gây queue/timeouts dây chuyền. Cần design backpressure tương thích thread model.

## 123. Bài tập T — Đo p99 nhiều pods

Ba pods có p99 riêng; nhóm lấy trung bình.

**Hỏi:** kết quả có phải global p99 không?

**Hướng giải:** không. Phải gộp observations/histograms đúng.

## 124. Bài tập U — Batching

Tăng batch size từ 20 lên 500 giúp ops/s nhưng p99 của requests ít traffic tăng.

**Hỏi:** tại sao?

**Hướng giải:** requests đến đầu batch phải đợi đủ batch/timer; đo queue wait và maxBatchWait.

## 125. Bài tập V — Tăng throughput nhưng replication lag tăng

Primary ACK 20.000 writes/s; secondaries chỉ apply 13.000/s, backlog tăng liên tục.

**Hỏi:** throughput đó có bền vững?

**Hướng giải:** chưa, nếu pipeline cần followers hội tụ; phải xem catch-up, log retention và freshness SLO.

## 126. Bài tập W — Retry của payment

API timeout rồi retry `CreatePayment` không có idempotency key.

**Hỏi:** overload protection có đủ giữ đúng nghiệp vụ không?

**Hướng giải:** không. Cần stable business operation ID, unknown outcome reconciliation và retry policy an toàn.

## 127. Bài tập X — Tìm operating point

Benchmark tại 8.000 RPS có p99 80 ms, tại 10.000 RPS p99 500 ms, queue tăng và timeout nhiều.

**Hỏi:** nên báo production capacity là 10.000 RPS không?

**Hướng giải:** không chỉ dựa peak throughput; chọn capacity dưới điểm gãy, có headroom và kiểm tra failure scenarios.

## 128. Bài tập Y — Fairness

Tenant A chiếm 99% queue; tenant B có traffic nhỏ nhưng chờ 10 giây.

**Hỏi:** thêm FIFO workers có giải quyết triệt để?

**Hướng giải:** chưa chắc. Cần per-tenant admission/fair queuing/capacity reserves và kiểm soát hot key.

## 129. Bài tập Z — Source và Search

MongoDB write p99 ổn, nhưng Search projection trễ 30 phút.

**Hỏi:** có thể nói “NoSQL pipeline khỏe” không?

**Hướng giải:** không. Phải đo outbox/CDC/consumer/index refresh age và verify freshness.

## 130. Checklist chẩn đoán hàng đợi và quá tải

**Định nghĩa**

1. `request`, `attempt`, `job`, `message` có được phân biệt không?
2. Scope của arrival/completion rates là gì?
3. Queue depth đang đếm những việc chờ ở tầng nào?
4. Có oldest queue age và wait histograms không?
5. In-flight tính từ khi nào đến khi nào?
6. Có phân biệt queue wait với service execution không?
7. Các timeout/cancellations có được tính là departures riêng không?

**Java/driver**

8. Có đo HTTP executor/event-loop scheduling delay không?
9. Có bounded queue và rejection policy rõ không?
10. Có giới hạn concurrent DB operations theo tổng số pods không?
11. Driver pool checked-out/available/wait có được đo không?
12. Có tách server selection timeout khỏi pool checkout timeout không?
13. Có retry budget, jitter, deadline propagation không?
14. Async/virtual threads có bị hiểu nhầm thành tăng DB capacity không?
15. Có cancel/close cursor/session/transaction đúng lifecycle không?
16. Có per-operation durations và outcome categories không?

**Database**

17. Có xem resource bottleneck theo node/shard/partition không?
18. Có đo CPU, disk queue, network và memory headroom không?
19. Query plans/keys/docs examined và scans có bất thường không?
20. Có hot key, large partition hay transaction conflicts không?
21. Replication lag có tăng bền vững dưới load không?
22. Có kiểm MongoDB topology/primary election không?
23. Cassandra consistency/coordinator/replica errors có được tách không?
24. DynamoDB throttling reasons/capacity có được theo dõi không?
25. Redis latency/SLOWLOG/client pending có đủ không?
26. Có phân biệt index build/repair/background workloads không?

**Event/CDC và trải nghiệm**

27. Có đo outbox/CDC/Kafka per-partition lag và oldest age không?
28. Checkpoint/ACK có theo durable effect không?
29. Có SLO về source commit-to-visible projection không?
30. Có báo p95/p99 end-to-end và deadline violation rate không?
31. Có phân biệt business rejections với server overload không?
32. Có theo dõi retry-amplified DB attempts per business intent không?
33. Có histogram đúng, không trung bình p99 của các instances không?
34. Có kiểm cache miss/stampede và multi-stage fan-out không?
35. Có fairness/latency theo tenant cohort và operation type không?

**Thử nghiệm và vận hành**

36. Benchmark có phân biệt offered vs achieved throughput không?
37. Có thử open-loop/closed-loop và kiểm coordinated omission không?
38. Có steady-state, burst, cold cache và failover tests không?
39. Có kiểm capacity khi giảm một node/AZ không?
40. Queue có giảm về bình thường sau burst không?
41. Có thể reject sớm mà không làm mất durable business work không?
42. Có circuit breaker/backpressure/load shedding đúng policy không?
43. Có trace từ HTTP đến driver/DB và queue stage không?
44. Có dashboard cùng timeline của traffic, latency, queues, CPU/IO không?
45. Có runbook rollback thay đổi concurrency/pool/retry không?
46. Có invariant/correctness tests khi concurrency tăng không?

## 131. Mẫu hợp đồng quan sát

~~~yaml
service: JavaProductApi
database:
  engine: MongoDB
  sourceOfTruth: CatalogCollection
  operationClasses:
    - ProductPointRead
    - ProductSearch
    - ProductConditionalUpdate
concurrency:
  appLimitPerInstance: measured
  maxPendingWaitMs: bounded
  poolSize: tunedWithBackendCapacity
  totalInstanceCount: tracked
queues:
  - httpPending
  - javaWorkerPending
  - appConcurrencyWait
  - driverPoolCheckout
  - dbExecution
  - cdcConsumerLag
measurement:
  traffic:
    - incomingRequestsPerSecond
    - completedOperationsPerSecond
    - attemptsPerBusinessIntent
  latency:
    - httpP50
    - httpP95
    - httpP99
    - appQueueWaitP95
    - poolCheckoutWaitP95
    - databaseRoundTripP99
  saturation:
    - queueDepthByStage
    - oldestWaitAge
    - activeAndAvailableConnections
    - cpuAndIoPerShard
    - networkAndCompaction
  outcome:
    - successful
    - businessRejected
    - overloadRejected
    - timedOut
    - cancelled
    - unknownWriteOutcome
  replicationAndAsync:
    - replicaApplyLag
    - cdcOldestUnprocessedAge
    - searchVisibilityLag
resilience:
  boundedRetries: true
  backoffAndJitter: true
  admissionControl: true
  idempotencyForWrites: required
  gracefulCancellation: required
alerts:
  - userFacingSloViolation
  - increasingQueueAge
  - sustainedInputOutputImbalance
  - persistentReplicaLag
  - retentionMarginAtRisk
  - highRetryAmplification
experiments:
  - stableRateSweep
  - openLoopBurst
  - hotKeySkew
  - nodeFailover
  - cacheMissStorm
  - cdcSinkSlowdown
  - transactionContention
~~~

Đây là **YAML mô tả hệ thống quan sát**, không phải cấu hình có thể dùng nguyên xi cho Spring, Micrometer, MongoDB hoặc Prometheus. Cần ánh xạ vào metrics API của engine/driver phiên bản thực.

## 132. Kết luận

Trong NoSQL phân tán, “database chậm” thường là một **chuỗi hàng đợi** chứ không phải một câu lệnh chậm. Ứng dụng có thể chờ worker, driver pool, server selection, DB CPU/IO, consistency acknowledgment hoặc pipeline CDC phía sau. Khi arrival rate vượt tốc độ xử lý, queue age tăng, p99 xấu đi và retries có thể khuếch đại load.

Một phương pháp đáng tin cậy phải:

- **Đo từng stage:** arrival, queue wait, execution, completion, retry và hậu kỳ bất đồng bộ.
- **Phân biệt concurrency với capacity:** nhiều threads/connections không tự làm database mạnh hơn.
- **Tìm điểm bão hòa:** p99, rejection, queue growth và resource headroom quan trọng hơn peak QPS.
- **Quan sát phân bố:** hot keys, tenant cohorts, shards, region, long-running queries.
- **Giới hạn công việc:** bounded queues, concurrency caps, admission control, deadline và backoff.
- **Bảo vệ tính đúng đắn:** idempotency, durable ACK/checkpoint, conditional writes và phân loại unknown outcomes.
- **Kiểm thử suy giảm:** cache outage, leader failover, replica lag, burst, CDC sink slow và hot-key contention.

> **Đừng tăng pool hoặc timeout chỉ để giấu hàng đợi. Hãy đo hàng đợi xuất hiện ở đâu, vì sao tốc độ xử lý không theo kịp lưu lượng đến, và chọn biện pháp khiến hệ ổn định trở lại mà không làm mất hoặc nhân đôi dữ liệu nghiệp vụ.**

Khi observability đủ rõ, nhóm vận hành sẽ biết lúc nào cần thêm năng lực xử lý, lúc nào cần sửa query/index, lúc nào phải giảm concurrency, và lúc nào phải tạm từ chối một số công việc để giữ SLO cho phần còn lại — thay vì phản ứng với một con số CPU hay QPS đơn độc.
