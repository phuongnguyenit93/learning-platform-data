# Đồng bộ các giới hạn tài nguyên trong Spring Batch

Một batch job được mở rộng từ 4 lên 32 worker threads. Mỗi worker dùng JDBC, đôi khi gọi HTTP để làm giàu dữ liệu, rồi ghi kết quả. Mặc dù số threads tăng gấp tám, tốc độ xử lý không tăng tương ứng: HikariCP báo hết connection, HTTP API trả `429 Too Many Requests`, broker tồn đọng, và database liên tục rollback các transaction bị deadlock. Nguyên nhân không nhất thiết do code sai; **các giới hạn tài nguyên đã được cấu hình độc lập, không theo cùng một ngân sách hệ thống**.

Bài **“Đồng bộ các giới hạn tài nguyên”** thuộc chương **Resource pool** trong module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng đến mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, giữ thread safety, retry/restart và vận hành theo tài nguyên thực tế.

Ở đây, *đồng bộ giới hạn tài nguyên* không có nghĩa sử dụng từ khóa Java `synchronized` cho mọi bước. Nó có nghĩa **phối hợp các ngân sách concurrency, queue, connection, CPU, bộ nhớ và quota** trên **mỗi step, JVM, pod, toàn cluster và các hệ thống phụ thuộc**. Một worker chỉ nên được nhận thêm công việc khi nó còn khả năng hoàn tất công việc đó mà không làm quá tải thành phần yếu nhất.

Nguyên lý trọng tâm:

> **Số worker hiệu quả phải tuân theo mọi giới hạn mà mỗi worker tiêu thụ, không chỉ giới hạn của TaskExecutor.**

Các ví dụ sử dụng Spring Batch **5.2.x**, Spring Framework **6.x**, Java **17+**, HikariCP và PostgreSQL khi minh họa SQL. Những con số pool, quota và SLA là **giả định để học phương pháp**, không phải thông số mặc định hay khuyến nghị dùng nguyên xi trong production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `gridSize`, số partitions, worker count, `ThreadPoolTaskExecutor` core/max/queue, chunk size, HTTP in-flight limit và JDBC pool size.
2. Tạo một **resource budget ledger** ghi giới hạn theo JVM, cluster và cả lưu lượng ứng dụng online.
3. Tính mức concurrency khả thi dựa trên CPU, heap, database connections, API rate limit, broker và SLA.
4. Dùng Little's law như một ước lượng có điều kiện, không nhầm `requests/s` với `requests đang chờ`.
5. Cấu hình executor và Hikari pool có giới hạn, nhận biết queue/backpressure và lý do max threads không luôn được dùng.
6. Tách giới hạn **in-flight**, **throughput theo thời gian**, **dung lượng hàng đợi** và **tổng tài nguyên vật lý**.
7. Phối hợp local/remote partitioning và remote chunking với quotas dùng chung, kể cả retry/restart.
8. Không giữ JDBC connection/transaction trong lúc chờ network hoặc permit không cần thiết.
9. Thiết kế admission control, rate limiter, backoff, circuit breaker và graceful shutdown theo một ngân sách hữu hạn.
10. Đo throughput **đã commit**, p95/p99, retry amplification, pool pending, queue age và SLO trước khi điều chỉnh.
11. Kiểm thử lỗi nguồn phụ thuộc, broker redelivery và worker crash để bảo đảm dữ liệu đúng khi giảm/tăng concurrency.
12. Lập runbook giảm tải và điều chỉnh ngân sách mà không làm hỏng JobRepository checkpoint.

## 2. “Đồng bộ” là phối hợp nhiều trần, không phải tăng cùng một con số

Giả sử môi trường có:

- Executor cho phép **32** task chạy đồng thời.
- Hikari business pool chỉ có **12** connections/pod.
- HTTP API đối tác cho toàn hệ thống chỉ **20 in-flight** và **100 requests/s**.
- Database có ngân sách **60 connections dành cho batch toàn cluster**.
- Tám pods đang chạy cùng module.
- Mỗi worker có thể cần một JDBC connection, đôi khi hai, và một HTTP request.

Nếu mỗi pod tự chạy 32 worker và pool cũng tăng thành 32, tổng worker lên 256, còn toàn cluster chỉ được cấp 60 DB connections và 20 API calls in-flight. Các worker còn lại chờ pool, retry và tranh lock; concurrency được quảng cáo **không trở thành throughput hữu ích**.

Vì vậy phải trả lời:

1. Mỗi công việc tiêu thụ **loại tài nguyên nào, bao lâu và đồng thời lúc nào**?
2. Giới hạn đó có hiệu lực **trên mỗi pod hay trên toàn cluster**?
3. Ai khác cũng dùng tài nguyên này: online services, scheduler khác, backup, replica?
4. Có bao nhiêu job/steps/partitions có thể đồng thời hoạt động?
5. Khi hết quota, hệ thống **chờ, từ chối, giảm tốc, hay retry**?
6. Những xử lý được nhận nhưng chưa hoàn tất có trạng thái **bền vững** không?
7. Khi hệ thống phụ thuộc chậm, giới hạn nào sẽ được chạm **đầu tiên**?

### 2.1. Bốn loại giới hạn khác nhau

| Loại giới hạn | Đơn vị | Ví dụ | Không được nhầm |
| --- | --- | --- | --- |
| **Concurrency / in-flight** | Công việc đang chạy | 8 active tasks, 20 HTTP requests in-flight | Không phải 20 requests/s |
| **Rate / throughput** | Công việc mỗi giây/phút | 100 HTTP requests/s | Không đảm bảo có 100 slots đồng thời |
| **Queue / backlog** | Công việc đang chờ | Executor queue tối đa 40 tasks | Không phải 40 threads hoặc 40 DB connections |
| **Capacity vật lý** | Connections, CPU cores, memory bytes, disk IOPS | 64 JDBC connections trên DB, 4 vCPU/pod | Không đồng nghĩa 64 transactions/s |

Một API có thể cho phép **10 concurrent calls** nhưng mỗi giây tối đa **40 requests**. Hai constraints phải cùng được áp dụng nếu đối tác công bố cả hai.

### 2.2. Định nghĩa đơn vị đo

- `P`: số **partition logic** có tên ổn định phục vụ restart.
- `C_worker`: số worker StepExecutions hoạt động đồng thời.
- `C_chunk`: số chunk threads đang xử lý cùng lúc trong một multi-threaded step.
- `C_http`: số request API còn in-flight.
- `R_http`: requests/s hoặc requests/min được cho phép.
- `C_db`: số JDBC connections có thể được mượn đồng thời.
- `Q_exec`: số tasks đang nằm trong queue executor.
- `K`: chunk size, số items dự kiến trước một commit.
- `N_pod`: số pods/instances chạy đồng thời.
- `B_mem`: ngân sách memory còn lại cho item buffers và in-flight work.

`P`, `C_worker` và `K` là các thông số **khác nhau**; tăng `P` có thể tăng hạt chia/cân bằng skew nhưng không nhất thiết tăng `C_worker`, còn tăng `K` có thể giảm commit overhead song tăng rollback scope và heap usage.

## 3. Bức tranh toàn hệ thống: admission phải nhìn xuyên các tầng

~~~mermaid
flowchart TD
    S["Scheduler / JobLauncher"] --> M["Job / Partition Manager"]
    M --> E["Bounded TaskExecutor / remote dispatcher"]
    E --> W1["Worker A"]
    E --> W2["Worker B"]
    E --> W3["Worker N"]
    W1 --> H["HTTP in-flight + rate-limit gate"]
    W2 --> H
    W3 --> H
    W1 --> DBP["Hikari business connection pool"]
    W2 --> DBP
    W3 --> DBP
    W1 --> REP["JobRepository pool"]
    W2 --> REP
    W3 --> REP
    H --> API[("Partner API<br/>cluster-wide quota")]
    DBP --> DB[("Business DB<br/>connections + CPU + locks")]
    REP --> META[("Metadata DB")]
    E --> Q[("Broker / durable queue")]
    Q -.-> W2
~~~

Sơ đồ trình bày các đường tài nguyên có thể có; một worker cụ thể không nhất thiết vừa gọi API vừa dùng broker. Khi business và metadata cùng datasource, hai đường `DBP`/`REP` có thể chia sẻ pool hoặc một server. Nếu cùng server nhưng khác pools, **giới hạn CPU/IOPS/connection của server vẫn là ngân sách chung**.

### 3.1. “Nút thắt nhỏ nhất” nhưng không áp dụng một công thức min máy móc

Với một mô hình đơn giản: mỗi worker cần **đồng thời 1 JDBC connection và 1 API permit trong suốt công việc**, concurrency khả dụng bị giới hạn bởi:

\[
C_{\mathrm{effective}}
\le \min(
C_{\mathrm{executor}},
C_{\mathrm{DB\,budget}},
C_{\mathrm{API\,inflight}},
C_{\mathrm{CPU/memory}}
).
\]

Nhưng trong thiết kế tốt, worker có thể **nhả connection trước khi gọi HTTP**, nên nhu cầu DB và API không đồng thời trong toàn vòng đời item. Khi đó lấy `min` của mọi connection/concurrency limit theo tỷ lệ 1:1 có thể **quá bảo thủ**. Phải mô hình hóa **mỗi phase** và **thời gian chiếm dụng** thật, đặc biệt khi pipeline có queue giữa các phase.

Cách làm đúng: lập resource demand vector theo operation, tính concurrency/throughput cho từng tài nguyên và chọn quota/scheduling policy không làm phase khác quá tải.

## 4. Resource budget ledger: bảng cần có trước khi scale

Một ledger nên ghi rõ **giới hạn toàn cluster, phần dành cho online traffic, phần còn cho batch, quota theo instance, peak simultaneous consumers, headroom và cách thực thi giới hạn**.

| Tài nguyên | Trần ví dụ | Đã dành chỗ | Ngân sách batch khả dụng | Enforcement |
| --- | ---: | ---: | ---: | --- |
| Business DB connections | 120 | Online 35 + admin/HA reserve 15 | 70 | Hikari pools toàn cluster + DB roles/limits |
| Metadata DB connections | 40 | Reserve 8 | 32 | Batch manager + worker pool budgets |
| External API in-flight | 24 | Online 6 | 18 | Cluster limiter hoặc per-pod permits bảo thủ |
| External API rate | 120 req/s | Online 40 | 80 req/s | Shared rate limiter, retry budget |
| Broker concurrent consumers | 36 | Other apps 12 | 24 | Consumer concurrency/prefetch |
| CPU worker pods | 6 pods × 4 vCPU | Hệ điều hành/runtime headroom | Đo theo CPU throttling thực | Kubernetes requests/limits |
| Memory worker pods | 6 pods × 4 GiB | JVM, thread stacks, direct buffers, OS | Dành một phần cho chunk buffers | JVM/container limits + bounded queue |
| Database write IOPS | Theo benchmark | Online/maintenance | Theo latency SLO | DB monitoring + bounded writers |

**Tất cả con số ở bảng là ví dụ.** `120 - 35 - 15 = 70` chỉ là phép tính ngân sách connection; không chứng minh DB có thể chạy 70 transactions hiệu quả đồng thời. Tốc độ xử lý còn bị giới hạn bởi CPU, disk, lock waits và SQL design.

### 4.1. Tránh double counting và bỏ sót consumers

Nếu business manager + worker pods dùng **cùng pool bean trong cùng JVM**, không cộng pool đó hai lần. Nhưng nếu manager là một JVM khác với Hikari pool riêng, **phải cộng pool manager**.

Nếu một pod chạy hai jobs đồng thời dùng cùng một Hikari pool, trần connections không tăng; nhưng số task chờ/khả năng pool starvation tăng. Nếu hai pods có mỗi pool 10, trần cấu hình tổng là 20 — kể cả chúng hiện đang idle.

### 4.2. Ngân sách “để dành” không phải dung lượng thừa vô ích

Giữ headroom cho:

- Online requests trong giờ cao điểm.
- Transaction replay/backfill hoặc một job khác chạy đột xuất.
- Database failover hoặc replica chậm.
- Connection health checks, admin access, migration/maintenance.
- Retries gây burst và lệch p99.
- Broker redelivery khi worker bị crash.
- Recovery window trước SLA deadline.

Headroom cần được chứng minh bằng tải peak và failure drills. Một hệ thống vận hành ở 100% quota liên tục thường không còn sức phục hồi khi một dependency chậm.

## 5. Phân biệt executor core/max/queue/gridSize/chunk size

| Tham số | Thuộc component | Điều khiển | Bẫy |
| --- | --- | --- | --- |
| `corePoolSize` | `ThreadPoolTaskExecutor` | Số threads nền executor cố giữ theo cấu hình | Không phải tổng số task có thể pending |
| `maxPoolSize` | Executor | Trần threads executor khi có nhu cầu và queue đầy | Queue unbounded có thể khiến max không được dùng |
| `queueCapacity` | Executor | Độ dài queue đợi | Queue lớn che overload và làm timeout sau nhiều phút |
| `gridSize` | Partitioning manager/handler | Hint/độ chia work, giới hạn dispatch phụ thuộc partitioner/handler | Không đồng nhất gridSize với số threads/pods |
| `chunk(K)` | Worker chunk step | Số items mục tiêu trong một commit | Không phải concurrency limiter |
| `throttleLimit` | Multi-threaded step legacy 5.x | Cơ chế throttle cũ | **Deprecated từ Spring Batch 5.0** |
| `maximumPoolSize` | HikariCP | Trần active + idle JDBC connections của một pool | Không phải tổng DB budget qua tất cả pods |
| `connectionTimeout` | HikariCP | Thời gian tối đa chờ mượn connection | Không giới hạn thời gian giữ connection |
| `prefetch` | Broker consumer | Số message chưa ACK có thể đệm trước | Có thể tăng memory và lệch cân bằng worker |
| Kubernetes replicas | Cluster | Số worker instances | Replicas × per-pod pools phải còn trong toàn cluster budget |

### 5.1. Thứ tự cấp task trong ThreadPoolTaskExecutor

Với backing `ThreadPoolExecutor` tiêu chuẩn và một bounded queue:

1. Tạo threads tới `corePoolSize` khi có task.
2. Khi core threads bận, **xếp tasks vào queue**.
3. Khi queue đầy, có thể tạo thêm threads tới `maxPoolSize`.
4. Khi cả queue và max threads đều hết, **reject** task theo handler.

Vì vậy cấu hình `core=4, max=16, queue=10_000` thường khiến executor nằm ở khoảng **4 threads** rất lâu; max=16 không trở thành concurrency thực chỉ vì đặt giá trị lớn.

Trong batch, cấu hình executor có core gần desired concurrency và queue bounded có thể dễ dự đoán hơn việc hy vọng max tăng đúng lúc. Nhưng không lấy queue size làm một “buffer vô hạn”: task queued giữ object references và chậm phát hiện overload.

### 5.2. Spring Batch throttleLimit trong 5.2

Tài liệu Spring Batch 5.2 mô tả multi-threaded step với `.taskExecutor(...)` và cũng có ví dụ `.throttleLimit(...)`. Nhưng **`throttleLimit` đã deprecated từ 5.0**. Không lấy nó làm giải pháp tương lai cho resource synchronization.

Nếu cần thay throttling mechanism mặc định, tài liệu 5.2 hướng tới custom `RepeatOperations` được cung cấp qua `StepBuilder.stepOperations(...)` và một bounded task queue. Thiết kế cần kiểm thử worker throughput và rollback; không dùng đồng thời nhiều cơ chế throttle mà không hiểu chúng tương tác.

### 5.3. Vì sao CallerRunsPolicy có thể gây hiệu ứng ngoài ý muốn?

Khi queue đầy, `CallerRunsPolicy` có thể khiến thread nộp task **tự thực thi** task bị từ chối, tạo backpressure cục bộ. Nhưng trong hệ thống batch, caller có thể là thread điều phối/transaction hoặc message listener; việc phải chạy task dài sẽ làm thay đổi latency, liveness và thời gian giữ resource.

Không tự thay rejection handler thành CallerRuns chỉ để “không bao giờ reject”. Nếu dùng, phải chứng minh caller không giữ DB transaction/lock, không ở critical listener thread và shutdown behavior đúng. Có khi **reject rõ ràng + durable retry/backoff** là lựa chọn an toàn hơn.

## 6. Tính concurrency theo SLA và thời gian chiếm dụng

Ví dụ phải xử lý 2,4 triệu records trong 50 phút dành riêng cho xử lý (thời gian validation và publish được tính ngoài cửa sổ này):

\[
R_{\mathrm{required}}
=\frac{2{,}400{,}000}{50\times60}
=800\ \text{items/s}.
\]

Nếu đo một worker được **160 committed items/s** trong môi trường chưa tranh chấp, số worker lý tưởng:

\[
C_{\mathrm{ideal}}
=\left\lceil\frac{800}{160}\right\rceil
=5.
\]

Đó chỉ là mức thấp nhất lý tưởng. Nếu ở mức cluster hiệu suất song song còn 70% vì lock, skew và scheduling, ước lượng cần:

\[
C_{\mathrm{plan}}
=\left\lceil\frac{800}{160\times0.70}\right\rceil
=\lceil7.143\rceil=8.
\]

**Tám worker** là giả thuyết để benchmark, không phải mức được phép tự động: chúng phải còn nằm trong ngân sách CPU, JDBC, API và broker. Nếu throughput của worker **không tuyến tính theo C**, không thể dùng hệ số hiệu suất cố định khi tăng tới 64 workers.

### 6.1. Little's law và API in-flight

Nếu mỗi item cần một API request, mục tiêu `R = 800` requests/s, thời gian response trung bình `W = 0,25` giây:

\[
L=R\times W=800\times0.25=200
\]

requests đang in-flight **trung bình** để duy trì tốc độ ấy trong một hệ ổn định, theo giả định một request/item và không có queue/throttling đáng kể.

Nếu API chỉ cho phép **20 requests in-flight**, tốc độ tối đa lý tưởng dưới giả định latency không đổi là:

\[
R_{\mathrm{API}}
\lesssim\frac{20}{0.25}
=80\ \text{requests/s}.
\]

Thêm worker threads không giúp đạt 800 requests/s qua API có quota này. Phải batch requests, cache/dedupe hợp lệ, giảm số request, tăng quota, cải thiện latency hoặc thay SLA.

**Lưu ý:** Little's law mô tả trung bình ổn định; p95/p99, retries, bursts và queue waiting vẫn cần headroom. Rate limit **80 req/s** có thể được thực thi bổ sung dù in-flight capacity còn; không suy từ concurrency mà bỏ qua rate quota.

### 6.2. JDBC connection hold time

Giả sử ở một phase SQL, hệ thống đạt 80 operations/s và mỗi operation giữ connection trung bình 35 ms:

\[
L_{\mathrm{JDBC}}
\approx80\times0.035=2.8
\]

connections đang bận **trung bình cho phase ấy**, chưa tính concurrent readers, transaction overlap, metadata và peaks.

Nếu worker giữ connection trong khi chờ 400 ms HTTP, occupancy có thể trở thành:

\[
L'_{\mathrm{JDBC}}
\approx80\times(0.035+0.400)=34.8.
\]

Trong ví dụ đó, tách HTTP ra khỏi transaction có thể giảm áp lực connection rất mạnh **mà không tăng pool**. Nhưng phải lưu ý thời điểm connection thật sự được mượn và nhả: logic `@Transactional` mở chưa chắc đã giữ physical connection từ giây đầu; cần instrument đúng.

### 6.3. Bảo đảm tài nguyên bằng measurement, không bởi một công thức

Để sizing chính xác:

1. Đo per-worker committed rate, p50/p95/p99 chunk duration.
2. Đo JDBC acquire/hold và lock waits.
3. Đo HTTP in-flight, rate, p99, retry amplification.
4. Đo CPU throttling, heap/RSS, GC và queue age.
5. Lặp theo C=1,2,4,8,... trong ngân sách cho phép.
6. Dừng tăng C khi committed throughput phẳng/giảm hoặc error/rollback tăng.
7. Giữ recovery headroom và kiểm tra SLA end-to-end.

## 7. HikariCP: tổng mọi pool không vượt ngân sách DB

Một sai lầm thường gặp là chọn `spring.datasource.hikari.maximum-pool-size=30` cho mỗi pod vì database cho 100 connections; sau đó scale từ 2 lên 8 pods và quên tổng trần đã tăng lên 240.

Công thức **cộng các pool tới cùng database endpoint**:

\[
C_{\mathrm{total\,configured}}
= \sum_{p=1}^{N_{\mathrm{pods}}}
\sum_{r\in \mathrm{pools}(p)} C_{p,r}
+\sum_{\mathrm{other\,services}} C_s.
\]

Phải có:

\[
C_{\mathrm{total\,configured}}
\le C_{\mathrm{DB\,connection\,budget}}
\]

nếu mục tiêu là **không vượt trần cấu hình ngay khi tất cả pools có thể đầy**. Có thể áp dụng oversubscription có chủ đích trong workload khác giờ, nhưng đó phải là quyết định capacity có bằng chứng và admission control, **không phải an toàn mặc định**.

### 7.1. Ví dụ ngân sách 120 connections

Database cho tối đa 120 connections theo policy nội bộ:

- Online services: 35.
- Admin/HA/maintenance reserve: 15.
- Batch manager: 4.
- Sáu worker pods: mỗi pod 10.

Tổng trần:

\[
35+15+4+6\times10=114\le120.
\]

Còn **6 connections headroom theo phép tính cấu hình**. Tuy nhiên DB có thể bị CPU/lock bottleneck trước khi dùng hết 114; việc “không vượt `max_connections`” chưa chứng minh throughput tốt.

Nếu scale worker pods từ 6 lên 10 mà giữ 10 connections/pod, tổng thành 154, **vượt ngân sách 120**. Cần hạ per-pod pool theo tổng replicas, giảm pods, hoặc tăng ngân sách DB sau khi đánh giá. Không chỉ sửa `maxPoolSize` trên một pod.

### 7.2. Hikari timeout là thời gian chờ mượn, không phải thời gian thực thi

- `maximumPoolSize`: số connection tối đa (idle + active) trong pool này.
- `minimumIdle`: số idle connections pool cố duy trì khi được cấu hình.
- `connectionTimeout`: thời gian tối đa caller chờ `getConnection()` khi pool đầy.
- `maxLifetime`: chính sách retirement connection; không phải giới hạn transaction lifetime.
- `leakDetectionThreshold`: phát hiện connection giữ lâu có thể hỗ trợ điều tra, nhưng giữ connection lâu chưa chắc “leak”.
- `idleTimeout` chỉ có ý nghĩa theo chính sách min/max idle và hành vi Hikari version.

Đừng “chữa Hikari timeout” bằng cách tăng `connectionTimeout` lên vài phút khi DB đang nghẽn. Điều đó có thể khiến worker queue lâu hơn và SLA xấu hơn.

### 7.3. Metadata DB cũng tiêu thụ connections

`JobRepository` cập nhật `StepExecution` và `ExecutionContext` định kỳ, cần JDBC access. Nếu metadata DB tách business DB, đó là **ngân sách pool thứ hai**; nếu chung database nhưng hai Hikari pools khác nhau, vẫn dùng chung server max_connections/IOPS.

Nếu repository và business data cần atomic chunk checkpoint, chọn datasource/transaction manager theo consistency contract, **không tách chỉ vì muốn chia pool**, rồi quên failure window giữa business commit và checkpoint.

## 8. Java: cấu hình bounded ThreadPoolTaskExecutor

Ví dụ một worker JVM chạy tối đa **4 local partitions đồng thời**, queue chứa tối đa 16 tasks, không mở thêm threads vì một burst lớn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BatchExecutorConfig {

    @Bean(name = "partitionExecutor")
    public ThreadPoolTaskExecutor partitionExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setThreadNamePrefix("batch-partition-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(60);
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        // Spring initializes the managed @Bean executor via its lifecycle.
        return executor;
    }
}
~~~

**Ý nghĩa giới hạn:**

- Active worker threads trong executor: tối đa **4**.
- Queue có thể giữ tối đa **16** tasks (không phải 16 active workers).
- Nếu đã có 4 active + 16 queued, submit tiếp có thể bị reject.
- `setAwaitTerminationSeconds(30)` là thời gian chờ trong shutdown flow theo executor implementation; không phải bảo đảm transaction/job đã hoàn tất trong 30 giây.
- Không cho rằng reject task là “đã xử lý xong”: phải quan sát lỗi, lưu durable state và retry/restart theo Spring Batch/middleware policy.

Nếu muốn executor thay đổi max khi queue đầy, cần chọn core/max/queue tương ứng; không dựa vào một `queueCapacity` khổng lồ khiến `maxPoolSize` không có tác dụng.

### 8.1. Không dùng Executor queue làm work queue bền

Task đang nằm trong RAM của `ThreadPoolTaskExecutor` **không bền vững** khi JVM crash. Đối với local partitioning, JobRepository giữ metadata partition/StepExecution và khả năng restart; nhưng nếu manager không thể dispatch/reconcile chính xác sau rejection/shutdown thì cần test failure path.

Nếu cần hàng triệu work items chờ lâu, dùng input manifest/partition state hoặc broker/durable DB queue phù hợp, **không** đặt hàng triệu Runnable vào executor queue.

## 9. Java: ghép executor limit với partition manager

Một manager local partitioning sử dụng executor đã giới hạn:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;

@Bean(name = "localPartitionManager")
public Step localPartitionManager(
        JobRepository repository,
        Partitioner immutablePartitioner,
        @Qualifier("workerStep") Step workerStep,
        @Qualifier("partitionExecutor") TaskExecutor executor) {

    return new StepBuilder("localPartitionManager", repository)
            .partitioner("workerStep", immutablePartitioner)
            .step(workerStep)
            .gridSize(16)
            .taskExecutor(executor)
            .build();
}
~~~

`workerStep` phải là một `Step` có tên `workerStep` và reader/writer/transaction manager đúng resource; `immutablePartitioner` phải tạo tên partition và `ExecutionContext` ổn định cho JobInstance. Đây là **snippet cấu hình** cần đặt trong class `@Configuration` và thêm bean hạ tầng.

- `gridSize(16)` là input/hint cho partitioner/handler, **không phải** bảo đảm tối đa 16 threads.
- Executor cap **4 active** là giới hạn local concurrency trong ví dụ, nếu không có executor thứ hai chạy cùng workload.
- Queue 16 có thể hấp thụ dispatch burst, nhưng không phải 16 connections hay 16 active workers.
- Nếu partitioner tạo 16 work units và 4 threads xử lý, các partitions còn lại có thể chờ; tổng thời gian phụ thuộc skew.
- Một JobInstance restart phải giữ **cùng partition names và ranges**. Không thay `gridSize` rồi phát lại một partition plan khác trên checkpoint cũ.
- Nếu cùng executor được dùng cho **hai JobExecutions đồng thời**, bốn threads được **chia sẻ**, không phải mỗi job được bốn.

### 9.1. Worker Step: chunk không phải concurrency

~~~java
@Bean(name = "workerStep")
public Step workerStep(
        JobRepository repository,
        @Qualifier("businessTxManager")
            PlatformTransactionManager businessTxManager,
        @Qualifier("partitionReader")
            ItemReader<SourceRow> reader,
        @Qualifier("businessWriter")
            ItemWriter<SourceRow> writer) {

    return new StepBuilder("workerStep", repository)
            .<SourceRow, SourceRow>chunk(200, businessTxManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

`SourceRow`/reader/writer là kiểu và bean ứng dụng cung cấp; reader nên `@StepScope` để có state riêng theo `StepExecution` của từng partition. Chỉ tăng `chunk(200)` thành `chunk(2000)` **không** tạo thêm worker threads; nó tăng số items trong một transaction, có thể giảm metadata commit overhead nhưng tăng memory/rollback/lock duration.

### 9.2. Hạn chế với multi-threaded step

Có thể thêm `.taskExecutor(executor)` vào chunk step để chạy nhiều chunks song song. Tuy nhiên các readers/writers stateful có thể không thread-safe; xử lý chunk có thể không còn thứ tự cố định. **`@StepScope` không biến một bean thành riêng theo chunk thread** nếu nhiều threads dùng cùng StepExecution.

Đối với input cần checkpoint xác định, **partitioning với StepExecution riêng** thường dễ kiểm soát hơn multi-threaded chunk processing trên một reader stateful. Nếu buộc dùng multi-threaded step, kiểm tra thread safety và restart semantics bằng integration test.

## 10. HTTP quota: giới hạn in-flight và giới hạn rate là hai cổng

Một `Semaphore(4)` trong mỗi JVM có thể giới hạn 4 request in-flight/pod, nhưng **không phải một global rate limiter**. Với sáu pods, trần in-flight của các semaphores này là 24, chưa tính online services.

### 10.1. Ví dụ semaphore tại service boundary

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Service;

@Service
public class EnrichmentGate {

    private final Semaphore permits = new Semaphore(3, true);
    private final ExternalEnrichmentClient client;

    public EnrichmentGate(ExternalEnrichmentClient client) {
        this.client = client;
    }

    public EnrichmentResponse fetch(
            long customerId, String idempotencyKey)
            throws InterruptedException {

        boolean acquired = permits.tryAcquire(2, TimeUnit.SECONDS);
        if (!acquired) {
            throw new UpstreamBusyException(
                    "No HTTP concurrency capacity");
        }

        try {
            // Client phải có connect/read/overall deadlines riêng.
            // Nếu tạo side effect, đích phải hiểu idempotencyKey.
            return client.fetch(customerId, idempotencyKey);
        } finally {
            permits.release();
        }
    }
}
~~~

`ExternalEnrichmentClient`, `EnrichmentResponse` và `UpstreamBusyException` là các kiểu của ứng dụng; ví dụ minh họa **concurrency gate**, không phải Spring Batch ItemProcessor hoàn chỉnh.

**Điều kiện cực quan trọng:** nếu gọi `fetch` trong một `ItemProcessor` đang có chunk DB transaction mở, thread có thể **giữ DB connection/lock trong lúc đợi permit hoặc chờ HTTP**. Như vậy đã giới hạn HTTP nhưng **làm nghẽn JDBC pool**. Với API chậm, nên stage enrichment **ngoài transaction DB đang mở** (claim transaction ngắn → HTTP ngoài transaction → persist transaction ngắn) rồi xử lý kết quả trong chunk.

### 10.2. Rate limit cần một cổng khác

Nếu đối tác cho tối đa `R=80 requests/s` trên toàn hệ thống, dù concurrency là 18, vẫn cần tính cả burst/token bucket/window và `Retry-After`. Một semaphore chỉ giới hạn số in-flight, không kiểm soát số request hoàn tất trong một giây: nếu latency 10 ms, 3 permits có thể gửi tới ~300 requests/s ở trạng thái lý tưởng.

Các lựa chọn:

- **Cluster-wide limiter** có lease/token hợp lệ nếu cần quota chia sẻ chính xác.
- **Per-pod ngân sách bảo thủ** với trần tổng trên max replicas, kể cả rolling deployments; ví dụ 5 pods × 10 req/s = 50 req/s dưới quota 80.
- **Ingress/broker dispatcher tập trung** kiểm soát requests/s nếu có một đường gọi duy nhất.
- Dùng thư viện như Resilience4j/Bucket4j khi phù hợp, nhưng đánh giá cẩn thận cơ chế distributed backing store; limiter cục bộ **không tự** trở thành global.

Không triển khai ad-hoc `Thread.sleep()` trong transaction chunk để “rate limit”. Backoff cần có deadline, durable retry state và không giữ JDBC locks trong lúc ngủ.


## 11. Message broker: consumers, prefetch, unacked và queue backlog

Trong remote chunking và remote partitioning, middleware có thể chuyển việc từ manager sang nhiều workers. Nhưng **số consumer** và **số message đã phát cho consumer nhưng chưa ACK** là hai giới hạn khác nhau.

Ví dụ RabbitMQ:

- Sáu worker pods.
- Mỗi pod có hai consumer sessions.
- `prefetch=10` theo semantics của listener/container/channel đã cấu hình.
- Mỗi message chứa một chunk nhiều items hoặc một yêu cầu thực thi partition.

Số messages được broker cho phép nằm **unacked** có thể xấp xỉ `6×2×10=120` theo mô hình per-consumer prefetch, dù chỉ 12 consumer callbacks đang thực thi đồng thời. Nếu mỗi message chứa chunk 2.000 items và payload lớn, lượng dữ liệu bị đệm trong các JVM có thể gây áp lực heap và khiến một worker giữ work nhiều hơn worker khác.

Không mặc định prefetch=10 có cùng semantics ở mọi broker/driver. RabbitMQ, JMS và Kafka có mô hình fetch/ack/poll/concurrency khác nhau; cần đọc contract của transport đang dùng.

### 11.1. Các giới hạn cần đồng bộ khi dùng broker

| Giới hạn | Ý nghĩa | Sai lệch thường gặp |
| --- | --- | --- |
| Consumer concurrency | Số listener callbacks/consumers chạy đồng thời | Nhiều callbacks cạnh tranh cùng Hikari pool |
| Prefetch / in-flight fetch | Messages được buffer nhưng chưa ACK | Memory tăng, fairness giảm, redelivery burst |
| Broker queue depth | Backlog còn trên broker | Lag tăng nếu downstream bão hòa |
| Producer publish rate | Tốc độ manager gửi requests | Hàng đợi tăng nhanh hơn workers xử lý |
| Reply queue retention | Lưu phản hồi manager chưa nhận | Out-of-date replies, correlation failures |
| DLQ/retry queue policy | Work bị lỗi liên tục | Poison message làm vòng lặp vô hạn |
| Message TTL/deadline | Thời hạn work trong transport | Expire work trước khi recover business state |

**Không tăng prefetch để “tăng tốc” nếu worker đang thiếu DB connections.** Prefetch chỉ đưa nhiều messages từ broker vào bộ đệm consumer, không làm database mạnh hơn.

### 11.2. ACK sau business effect và redelivery

Trong một hệ thống at-least-once:

~~~text
1. Worker nhận message.
2. Worker ghi DB và COMMIT.
3. Worker crash trước ACK/reply.
4. Broker giao lại message.
5. Worker khác có thể ghi lại cùng business key.
~~~

Hành vi an toàn cần:

- Durable correlation theo job/step/partition/chunk.
- Writer idempotent theo business key/source version.
- ACK policy đúng với transaction và reply semantics.
- Giới hạn redelivery/backoff/DLQ để không retry storm.
- Với remote partition, kiểm tra worker liveness/ownership trước khi cho worker thứ hai ghi cùng partition.

Broker ACK không thay thế `JobRepository` checkpoint; checkpoint cũng không thay thế business idempotency.

## 12. CPU, heap và JVM thread budget

DB/API có thể là nút thắt đầu tiên, nhưng memory và CPU vẫn phải tính. Một pod với 4 GiB memory limit không có toàn bộ 4 GiB cho chunk data.

Các thành phần tiêu thụ:

- JVM heap (objects, buffers, persistence context).
- Thread stacks và native allocations.
- Direct byte buffers (HTTP, broker, NIO).
- JDBC driver/result set buffers.
- Class metadata, JIT, GC, runtime.
- Những tasks queued còn giữ references tới payload.
- Caches, tracing và logging buffers.
- OS/container memory headroom.

### 12.1. Công thức ngân sách bộ nhớ dạng điều kiện

Ước lượng bảo thủ:

\[
M_{\mathrm{peak}}
\approx M_{\mathrm{runtime}}
+ C_{\mathrm{worker}}\times M_{\mathrm{inflight\,worker}}
+ Q_{\mathrm{exec}}\times M_{\mathrm{queued\,task}}
+ M_{\mathrm{broker\,buffers}}
+ M_{\mathrm{headroom}}.
\]

Trong đó `M_inflight_worker` có thể tăng theo chunk size K và kích thước object sau deserialize/process, nhưng không nhất thiết tuyến tính nếu reader streaming và writer không giữ toàn chunk trong heap. Đo thực bằng JFR/heap profiles.

Ví dụ:

- Runtime/caches: 700 MiB.
- 6 workers, mỗi worker đỉnh 120 MiB gồm chunk/persistence objects.
- Queue + broker buffers: 250 MiB.
- Native, stacks, direct memory và reserve: 600 MiB.

\[
M_{\mathrm{estimate}}
=700+6\times120+250+600
=2{,}270\ \mathrm{MiB}.
\]

Với container 3 GiB, còn một phần headroom trước peak chưa dự đoán; **không** coi đây là bảo đảm không OOM. Một JSON payload bất thường hoặc partition skew có thể tăng `M_inflight_worker` mạnh hơn trung bình.

### 12.2. Chunk size × worker count

Nếu một chunk chứa `K=500` items, mỗi item sau xử lý chiếm trung bình 25 KiB trong heap và có 8 chunks in-flight, riêng item objects có thể tới:

\[
8\times500\times25\ \mathrm{KiB}
=100{,}000\ \mathrm{KiB}
\approx97.7\ \mathrm{MiB}.
\]

Đây là phép tính minh họa, **chưa tính** các bản sao intermediate, persistence context, writer buffers hoặc GC overhead. Tăng K lên 5.000 có thể tăng peak đáng kể ngay cả khi number of threads không đổi.

### 12.3. CPU quota và parallelism

- Với CPU-bound `ItemProcessor`, worker concurrency gần số core hữu ích là điểm khởi đầu để benchmark.
- Với I/O-bound workloads, concurrency có thể vượt core count nhưng không vượt DB/API/heap budgets.
- Kubernetes CPU limit có thể gây **CPU throttling**; nhiều runnable threads không làm tăng quota CPU.
- Memory limit là giới hạn cứng ở container level; OOMKill có thể ngắt worker trước khi checkpoint/ACK.
- GC pause và context switching tăng khi tạo quá nhiều threads/objects.

Không dùng công thức “threads = cores×2” cho mọi job. Đo **CPU sử dụng thực, throttling, GC, committed throughput và p99** dưới workload representative.

## 13. Coordinated backpressure: nhận công việc theo năng lực xử lý

Một pipeline ổn định phải kiểm soát **tốc độ nhận việc** theo khả năng hoàn thành. Nếu producer tạo work `R_in` nhanh hơn worker hoàn tất `R_out` trong thời gian dài, backlog tăng:

\[
\Delta Q \approx (R_{\mathrm{in}}-R_{\mathrm{out}})\times\Delta t
\]

với đơn vị nhất quán và bỏ qua thời gian trống/đột biến. Nếu API giảm tốc từ 100 req/s xuống 30 req/s mà manager vẫn publish 100 req/s trong 10 phút, backlog tăng lý tưởng:

\[
(100-30)\times600=42{,}000\ \text{requests}.
\]

Hàng đợi dài có thể là **durable buffer có chủ đích** nếu có TTL/retention/SLA; nhưng không được để một executor queue trong RAM âm thầm giữ 42.000 tasks và khiến restart mất work.

### 13.1. Các lớp backpressure theo vị trí

| Lớp | Giới hạn | Phản ứng khi đầy |
| --- | --- | --- |
| Job admission | JobInstances/JobExecutions tối đa đồng thời | Hoãn launch/đưa vào scheduler queue |
| Partition dispatch | Max active workers/StepExecutions | Giữ partitions chưa dispatch trong durable plan |
| Thread executor | Bounded active threads + queue | Reject/báo lỗi để retry có kiểm soát |
| JDBC pool | Max connections + acquire timeout | Giảm worker load, phân tích SQL/transactions |
| External API | Shared concurrent permits + rate tokens | Không gửi thêm, backoff theo contract |
| Broker | Consumers, prefetch, durable queue retention | Giảm producer rate hoặc mở năng lực xử lý có budget |
| Writer DB | Transaction duration/lock budget | Tune SQL/chunk size, giảm concurrency |
| Publish | Outbox backlog/ack confirmations | Retain durable events, retry và báo động |

Không phải mọi “queue đầy” đều nên biến thành `skip`. Với dữ liệu bắt buộc, thiếu capacity là lỗi **hạ tầng tạm thời** hoặc tín hiệu cần giảm tải, không phải lý do bỏ record nghiệp vụ.

### 13.2. Thứ tự lấy permit để tránh giữ tài nguyên khi chờ

Anti-pattern:

~~~text
BEGIN JDBC TRANSACTION
  acquire JDBC connection + lock row
  wait for HTTP permit (may take 30 seconds)
  make HTTP request
COMMIT
~~~

Đây là transaction dài vì chờ tài nguyên khác trong khi đang giữ DB resources.

Mẫu an toàn hơn:

~~~text
TX claim (ngắn):
  reserve work with stable key/lease
COMMIT

outside DB transaction:
  acquire HTTP permit (bounded wait)
  perform HTTP with overall deadline
  release permit

TX persist (ngắn):
  save response/check lease token
COMMIT
~~~

Nếu không cần network call, chunk writer chỉ cần DB transaction, không đặt HTTP semaphore vào đường thực thi.

**Không cố nắm đồng thời permit DB, permit API và broker permit lâu hơn cần thiết.** Nếu một tài nguyên phải chờ tài nguyên khác khi đã giữ locks, deadlock/starvation có thể xảy ra ở mức ứng dụng ngay cả khi SQL không deadlock. Tách phases, giữ locks ngắn, và có timeout/finally/recovery.

### 13.3. Admission control chỉ có ý nghĩa nếu work bền

Khi hệ thống từ chối submit vì hết concurrency:

- Source item vẫn ở input snapshot/manifest hoặc durable queue.
- Không đánh dấu business state là thành công.
- Với step fail, JobRepository phản ánh failure/restart eligibility.
- Với message, ACK/requeue policy không làm rơi work.
- Với task ngoài Batch, có durable retry state thay vì chỉ biến `Runnable` trong JVM.
- Dead-letter/poison queue không bị “quên” khỏi reconciliation.

Tránh ghi `COMPLETED` khi còn hàng nghìn pending work items chưa được publish/confirm.

## 14. Quota phải tính cả retry, skip và replay

Khi thiết kế admission, phải tính **nỗ lực thực thi** chứ không chỉ unique records.

Nếu xác suất một request thất bại transient là `p` độc lập qua mỗi lượt, và cho tối đa `k` lần retry bổ sung, số attempts kỳ vọng ở mô hình giản lược:

\[
E[A]=1+p+p^2+\cdots+p^k.
\]

Với `p=0.2` và `k=3`:

\[
E[A]=1+0.2+0.04+0.008=1.248.
\]

Nếu hệ thống cần **100 unique operations/s**, tải requests thực tới API có thể ~124,8 req/s trong giả định này. Nếu quota chỉ 120 req/s, retry có thể tự làm quá tải đối tác. Trong thực tế failures có thể **tương quan** (API outage, DB deadlock storm), do đó còn xấu hơn mô hình độc lập.

### 14.1. Backoff khác concurrency limiter

- Retry limit giới hạn số lượt thử cho một operation/context.
- Exponential backoff + jitter phân tán thời điểm retry.
- Rate limiter kiểm soát requests/s hoặc bursts.
- Semaphore kiểm soát in-flight requests.
- Circuit breaker có thể ngăn gửi thêm khi dependency đang hỏng.
- Bulkhead giới hạn tài nguyên cho một downstream, không cho nó chiếm cả worker pool.

Phải có **overall retry budget/deadline** theo item/job. Retry `429` phải tôn trọng `Retry-After` nếu hợp lệ; `400` do schema sai thường không nên retry. Với HTTP POST tạo side effect, timeout có thể xảy ra **sau khi server đã xử lý**, nên cần stable idempotency key hoặc reconciliation trước retry.

### 14.2. Retry ở nhiều tầng có thể nhân tải

Một manager retry message 3 lần, worker Step retry DB 3 lần, HTTP client retry API 3 lần, broker lại redeliver. Nếu các layers retry vô điều kiện, một business request có thể kích hoạt **nhiều attempts hơn một retryLimit đơn**.

Lập bản đồ retry ownership:

~~~text
Scheduler / Job launch retry
  -> Partition/Step restart
      -> Chunk retry
          -> HTTP client retry
              -> Broker request redelivery
~~~

Không có nghĩa tất cả tầng trên đều đồng thời áp dụng; đây là mô hình các lớp **có khả năng** phát lại công việc. Chỉ một vài tầng nên nắm trách nhiệm retry cho mỗi failure type, với tổng budget bền vững và idempotency.

### 14.3. Backpressure phải chống thundering herd sau outage

Khi DB phục hồi, hàng chục pods có thể đồng thời retry:

- Dùng jitter để tránh cùng thời điểm.
- Tăng concurrency theo bước nhỏ dựa trên committed throughput.
- Giới hạn outstanding retries trên toàn cluster.
- Giữ online traffic reservation.
- Quan sát DB lock waits và pending pool.
- Không ép tất cả partitions đã FAILED vào một lượt restart đồng thời nếu chưa đủ capacity.

## 15. Đồng bộ giới hạn qua nhiều pods và nhiều job

Một `Semaphore(3)` trong mỗi JVM **không** biết có bao nhiêu pods đang chạy. Khi horizontal scale, global capacity phải được tính lại.

Giả sử API cho batch **18 in-flight** sau khi trừ online usage. Với 6 pods và mỗi pod 3 permits:

\[
6\times3=18.
\]

Nếu rolling update chạy đồng thời 6 pods cũ và 3 pods mới, trần theo local semaphores có thể thành:

\[
(6+3)\times3=27,
\]

vượt quota batch 18. **Max replicas khi rollout** chứ không chỉ replicas steady-state phải nằm trong tính toán nếu dùng per-pod quotas.

### 15.1. Ba chiến lược thực thi global limit

**A. Chia quota tĩnh bảo thủ.** Ấn định `perPod = floor(globalBudget / maxSimultaneousPods)` theo max replicas kể cả surge. Dễ vận hành nhưng có thể để capacity idle khi ít pods.

**B. Điều phối centrally.** Một gateway/dispatcher chung giữ in-flight/rate budget cho tất cả traffic, enforce bằng admission. Đơn giản hóa quota ở client nhưng cần HA, throughput và failure policy của gateway.

**C. Distributed limiter.** Dùng service/Redis/etc. hỗ trợ atomic grant/expiry, lease, timeout và failover, có metrics. Cần thiết kế khi coordinator unavailable: fail-closed, degrade hay budget fallback; tránh tự động fail-open làm quá quota.

Mỗi chiến lược đều cần kiểm soát **rate và concurrency nếu API công bố cả hai**. Một Redis counter tăng/giảm đơn giản có thể rò permit sau worker crash, không đủ nếu không có expiry/reconciliation.

### 15.2. Per-job budget trong một pod

Hai jobs `dailySettlement` và `historicalBackfill` cùng chạy trong một JVM có thể dùng chung:

- TaskExecutor.
- Hikari pool.
- API limiter.
- Broker consumer pool.

Nếu cả hai đều tự nghĩ “tôi được 8 workers”, tổng nhu cầu là 16 dù executor chỉ có 8. Một job có thể làm job kia đói tài nguyên. Dùng **shared admission controller**, per-job quotas hoặc tách resource pools có tổng budget rõ ràng.

Priority admission phù hợp khi daily SLA phải ưu tiên hơn backfill; nhưng tránh starvation vô hạn của low-priority work bằng aging/quota policies.

### 15.3. JobRepository metadata cũng là tài nguyên chia sẻ

Nếu mọi workers cùng ghi metadata vào một JobRepository, tăng số partitions và chunk commits làm tăng update rate, optimistic locking contention và connection demand. Không tự tách repository datasource chỉ để bớt contention nếu điều đó làm mất atomicity giữa business chunk và checkpoint; cần đánh giá failure window, idempotent writer và recovery contract.

## 16. Một bài toán sizing có đủ các giới hạn

Giả định workload:

- 2.400.000 items trong 50 phút xử lý ⇒ `800 items/s`.
- Chỉ **5% items** cần gọi API bên ngoài, còn lại xử lý JDBC thuần.
- API trung bình 300 ms, budget batch 18 in-flight và 80 requests/s.
- Sáu worker pods, mỗi pod 4 partition threads.
- Hikari business pool tối đa 10 connections/pod.
- Manager Hikari pool tối đa 4 connections.
- Business DB max connection budget 120, online 35, HA/admin reserve 15.
- Executor queue bounded.
- API calls thực hiện ở phase **ngoài DB transaction**.

### 16.1. Kiểm tra API capacity

Tốc độ API cần:

\[
R_{\mathrm{API\,required}}
=800\times0.05=40\ \text{req/s}.
\]

In-flight trung bình theo Little's law:

\[
L_{\mathrm{API}}
\approx40\times0.3=12.
\]

Quota batch là 18 in-flight và 80 req/s, nên **theo trung bình lý tưởng**, nhu cầu 12 in-flight và 40 req/s nằm dưới hai giới hạn. Tuy nhiên phải kiểm tra p99/variance, retry amplification và bursts: nếu mọi request tập trung cuối chunk, một limiter bảo đảm in-flight/rate vẫn cần thiết.

### 16.2. Kiểm tra JDBC capacity

Tổng connections trần:

\[
C_{\mathrm{DB,total}}
=6\times10+4+35+15
=114\le120.
\]

Con số đó chỉ nói pool cấu hình không vượt max connections trong ví dụ, **không** nói DB đủ năng lực commit 800 items/s. Cần benchmark SQL/lock/IOPS, metadata, cursor và transaction hold times.

### 16.3. Kiểm tra worker throughput

Sáu pods × 4 worker threads = **24 active local partition workers** tối đa nếu mỗi pod dùng đúng một executor cap và không có workers thêm từ steps khác.

Để đạt 800 items/s, committed throughput bình quân cần:

\[
R_{\mathrm{per\,worker}}\approx\frac{800}{24}
\approx33.3\ \text{items/s}.
\]

Nếu mỗi worker đo được ≥40 committed items/s ở load representative, hệ thống có headroom lý tưởng; nếu database bắt đầu lock contention ở 16 workers, **24 workers có thể chậm hơn 16**. Không lấy per-worker throughput ở C=1 rồi nhân 24 mà bỏ qua contention.

### 16.4. Kiểm tra kết hợp

| Giới hạn | Nhu cầu | Ngân sách | Kết luận sơ bộ |
| --- | ---: | ---: | --- |
| HTTP rate | 40 req/s | 80 req/s | Có dư địa lý thuyết |
| HTTP in-flight trung bình | 12 | 18 | Có dư địa, cần p99 test |
| Worker active | 24 | 24 | Đúng trần thiết kế |
| JDBC max configured | 114 tổng cùng online/reserve | 120 | Không vượt trần cấu hình |
| DB committed throughput | 800 items/s | Chưa đo | **Chưa kết luận khả thi** |
| Memory/CPU | Theo chunk/payload | Chưa đo | **Chưa kết luận khả thi** |
| SLA end-to-end | ≤50 phút xử lý | 50 phút | Cần retry/recovery headroom |

Đây là cách phối hợp **tất cả giới hạn** thay vì thấy API có dư địa rồi tăng thêm workers, hoặc thấy JDBC pool còn connections rồi tăng chunk size.

### 16.5. Nếu workload thay đổi thành 100% items gọi API?

Khi toàn bộ 800 items/s phải gọi API, quota 18 in-flight và latency trung bình 0.3 giây cho trần lý tưởng khoảng:

\[
18/0.3=60\ \text{requests/s},
\]

thấp hơn nhiều so với 800 items/s. Job không thể đạt SLA bằng cách tăng pods, JDBC pool hay CPU. Cần đổi chiến lược: batch requests tại API, cache/version reuse hợp lệ, nâng quota, giảm số API calls hoặc thay SLA.

**Bài học:** resource budget phải được tính theo **tỷ lệ item thực sự dùng từng resource**, không chỉ tổng số items.

## 17. Gắn resource budgets với restartability

Tính toán concurrency không thể tách khỏi tính đúng đắn khi crash.

### 17.1. Các invariants quan trọng

- Partition names và `ExecutionContext` phải ổn định qua các JobExecutions của cùng JobInstance.
- Một worker crash không làm mất nguồn work trong executor RAM; work phải có trong snapshot/JobRepository hoặc broker/durable queue.
- JDBC writer idempotent theo business key/version khi replay.
- Không ACK/publish success trước khi business state bền vững theo protocol.
- Worker cũ không được tiếp tục ghi cùng partition nếu worker mới bắt đầu, trừ khi writer/fencing đã bảo vệ.
- API tạo side effect dùng stable idempotency key qua retry/restart.
- Thay đổi executor pool size giữa restarts **không thay đổi partition plan logic**.
- Giảm concurrency khi lỗi không được làm mất record hoặc tự động `skip` dữ liệu bắt buộc.
- `BatchStatus.COMPLETED` phải đi kèm business reconciliation trước publish.

### 17.2. Mối liên hệ với JobRepository

Nếu JobRepository và business writer dùng **cùng datasource/transaction manager**, metadata checkpoint có thể tham gia cùng local chunk transaction. Nếu nằm trên hai databases với local managers riêng, có failure window business commit–checkpoint. Giảm threads hoặc tăng Hikari pool **không** sửa non-atomicity đó.

Hãy coi recovery contract là một **constraint thiết kế** ngang hàng với max connections. Không tối ưu thông lượng bằng cách chuyển checkpoint sang database khác mà không đánh giá idempotency, outbox và reconciliation.


## 18. Đồng bộ cấu hình Hikari, executor và deployment

Một sai sót tinh vi là tài liệu capacity ghi **6 pods × pool 10**, nhưng file cấu hình Hikari vẫn để `maximumPoolSize=20`, trong khi HPA có thể scale 10 pods và rolling update thêm pod mới. Từ **một** configuration drift đã xuất hiện nhiều trần không còn ăn khớp.

### 18.1. Ví dụ cấu hình Spring Boot (một datasource do Boot quản lý)

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: batch-business
      maximum-pool-size: 10
      connection-timeout: 2000

app:
  batch:
    max-active-partitions-per-pod: 4
    partition-executor-queue-capacity: 16
    external-api:
      max-inflight-per-pod: 3
      max-rate-per-second-per-pod: 10
~~~

Đây là **ví dụ cấu hình**, không phải ứng dụng hoàn chỉnh: các key `app.batch.*` là custom properties **không tự kích hoạt bất kỳ limiter nào**. Ứng dụng phải có `@ConfigurationProperties`, validator và components để áp dụng chúng. `spring.datasource.hikari.*` chỉ tự áp dụng cho datasource được Spring Boot autoconfigure phù hợp; nếu dùng nhiều datasource tùy biến, cần cấu hình từng `HikariDataSource`/properties binding và kiểm tra pool đã khởi tạo.

Với multi-datasource environment:

~~~text
businessDataSource:
  maximumPoolSize = 10

batchMetadataDataSource:
  maximumPoolSize = 4

externalApiLimiter:
  concurrency permits per pod = 3
  rate tokens per pod = 10/s

partitionExecutor:
  active threads = 4
  queued tasks <= 16
~~~

Không coi những tên cấu hình minh họa là key chính thức của Hikari hay Spring Boot nếu chưa có wiring. Nếu business/metadata cùng JDBC connection pool, không nhân đôi ngân sách; nếu hai pools cùng DB server, phải cộng cả hai.

### 18.2. Static budget validation khi khởi động

Một validator ứng dụng có thể kiểm tra các ràng buộc cục bộ và environment:

~~~java
public record BatchCapacityLimits(
        int activeWorkers,
        int queuedTasks,
        int jdbcPoolMax,
        int apiInflightPerPod,
        int configuredMaxPods,
        int apiInflightGlobalBudget) {

    public void validate() {
        if (activeWorkers <= 0
                || queuedTasks < 0
                || jdbcPoolMax <= 0
                || apiInflightPerPod <= 0
                || configuredMaxPods <= 0) {
            throw new IllegalArgumentException(
                    "Capacity limits must be positive");
        }

        long maxApiDemand =
                (long) apiInflightPerPod * configuredMaxPods;

        if (maxApiDemand > apiInflightGlobalBudget) {
            throw new IllegalStateException(
                    "API quota would be exceeded at max rollout pods");
        }

        // Không giả định mỗi worker luôn cần 1 JDBC connection;
        // mối quan hệ worker -> pool cần biết reader/writer/metadata.
    }
}
~~~

Đây là **pseudocode biên dịch được về phép kiểm tra**, không thay cho global admission control. `configuredMaxPods` chỉ là số **cấu hình/giả định**, có thể lỗi thời nếu autoscaler/deployment thay đổi; production cần policy test với cấu hình thực tế và metrics.

Nếu muốn hệ thống tự điều chỉnh per-pod budgets theo replica count, phải có cơ chế phân phối quota nhất quán và xác định behavior khi coordinator unavailable. Chỉ đọc `replicas` rồi chia tại startup không đủ nếu số pods thay đổi trong lúc job đang chạy.

### 18.3. Bản đồ cấu hình và nguồn chân lý

| Giá trị | Nơi cấu hình | Cần kiểm tra |
| --- | --- | --- |
| Max job concurrency | Scheduler/admission service | Có nhiều scheduler instances không? |
| Local worker concurrency | ThreadPoolTaskExecutor | Active/queue/rejection đúng? |
| Partition gridSize | Spring Batch Step config | Plan restart có ổn định? |
| Business JDBC max | Hikari datasource của writer | Tổng qua pods có trong DB budget? |
| Metadata JDBC max | Hikari datasource của JobRepository | Có đang dùng chung DB/pool không? |
| API in-flight/rate | Limiter client/gateway | Local hay global, max rollout pods? |
| Broker consumers/prefetch | Listener container / client | Có quá nhiều unacked payloads không? |
| CPU/memory | Container manifests / autoscaler | JVM heap + native + GC có headroom? |
| Retry attempts/deadlines | Step/API client/transport | Có retry lồng nhau gây nhân tải? |
| SLA / publish gate | Orchestrator/monitoring | Đã trừ thời gian recovery và đối soát? |

Đừng để runbook ghi “limit bằng 8” trong khi code, Helm values và HPA đều là các con số khác nhau. Một **capacity contract** versioned với deployment tốt hơn spreadsheet tĩnh không có owner.

## 19. Dashboard xác minh giới hạn có thực sự ăn khớp

Tài liệu capacity chỉ có giá trị khi metrics xác minh được **tầng nào đang chạm trần**.

| Nhóm | Metric đề xuất | Dấu hiệu |
| --- | --- | --- |
| Job | Committed items/s, ETA, JobExecution/StepExecution status | Job đang tiến hay chỉ bận retry? |
| Executor | Active threads, pool size, queue depth, rejected tasks | Queue đầy, max không được dùng |
| JDBC | Hikari active/idle/pending, connection acquire p95/p99 | Pool exhausted hoặc SQL/locks chậm |
| DB | Query p95/p99, deadlocks, lock waits, CPU/IOPS | Tăng workers chỉ gây contention |
| Metadata | JobRepository update duration, failures, optimistic conflicts | Metadata DB là bottleneck |
| API | Requests/s, in-flight, 429/503, p95/p99, retry attempts | Rate/in-flight quota hoặc dependency fail |
| Broker | Ready/unacked, consumer lag, redeliveries, DLQ | Backlog tăng/ACK chậm |
| JVM | Heap used, RSS, GC pauses, thread count | Chunk buffers/queue gây memory pressure |
| Kubernetes | CPU usage/throttling, OOMKills, restart count | Resource limits làm worker chết |
| Correctness | Unique business keys, version conflicts, outbox pending age | Tăng throughput đổi lấy lỗi dữ liệu? |
| SLA | Time remaining, backlog drain ETA, recovery buffer | Có kịp publish sau reconciliation? |

Tên metric cụ thể phụ thuộc Spring Boot/Micrometer, Spring Batch observation, Hikari, broker và instrumentation đã bật. Bảng mô tả **điều cần đo**, không khẳng định mọi tên có sẵn.

### 19.1. “Active threads cao” không chứng minh workload hiệu quả

Nếu tất cả 16 threads active nhưng 12 threads đang chờ JDBC connection, CPU 10%, committed throughput thấp, hệ thống đang **xếp hàng ở DB pool**.

Nếu Hikari pending thấp nhưng DB lock waits cao, tăng pool có thể tệ hơn: vấn đề có thể là SQL transaction dài hoặc update cùng hot rows.

Nếu API 429 cao mà DB bình thường, cần giảm HTTP rate/concurrency, không tăng Hikari connections.

Nếu heap tăng khi executor queue depth tăng, giảm `queueCapacity` hoặc áp dụng durable backpressure, không chỉ tăng `-Xmx` mà bỏ qua memory limit pod.

### 19.2. Dashboard một hàng cho một tầng

~~~text
Job:         committed 480 items/s | target 800 | ETA +45m
Workers:     active 24/24, queued 16, rejected 5/min
Business DB: Hikari active 10/10, pending 14, SQL p99 2.3s
Metadata:    update p99 20ms, pending 0
API:         rate 39 req/s, inflight 7/18, 429 0
Broker:      queue age stable, redelivery low
CPU:         20% utilization, GC low

Nhận định sơ bộ:
  Business DB/connection hold hoặc SQL contention là limiter đầu tiên.
  Tăng worker count không giúp; cần xem lock/SQL/transaction duration.
~~~

Đây là **tình huống giả định**. Muốn chẩn đoán chính xác, xem connection acquisition vs hold, locks, query plans và traces trước khi quyết định giảm chunk size hay tối ưu index.

## 20. Benchmark theo bậc và thử sự cố có kiểm soát

Không test chỉ **happy path**. Một cấu hình đạt SLA khi API bình thường nhưng tạo retry storm lúc 429 là cấu hình chưa đủ an toàn.

### 20.1. Ma trận tải

Chạy cùng một immutable snapshot ở các concurrency levels được phép, ví dụ:

| Run | Local workers/pod | Pods | Chunk size | Điều đo |
| --- | ---: | ---: | ---: | --- |
| A | 1 | 1 | 200 | Baseline per-worker |
| B | 2 | 2 | 200 | Mức scale thấp |
| C | 4 | 2 | 200 | Contention bắt đầu? |
| D | 4 | 4 | 200 | Quota cluster có đủ? |
| E | 4 | 6 | 200 | Peak rollout budget |
| F | 4 | 6 | 500 | Transaction/heap/commit tradeoff |
| G | 4 | 6 | 200 | API throttle + DB slowdown injection |

Không chạy run vượt quota thực: nếu sáu pods × 3 HTTP permits = 18 và rolling update có surge, cần điều chỉnh max pods hoặc tạm dùng môi trường riêng. Các runs phải giữ nguồn dữ liệu, index, cache warmup và workload profile so sánh được.

### 20.2. Fault injection matrix

| Sự cố | Cách mô phỏng | Bất biến nghiệm thu |
| --- | --- | --- |
| DB connection saturation | Hạ pool trong môi trường test | Pending có giới hạn, lỗi rõ, không nuốt work |
| DB lock contention | Hai workers tranh hot rows | Retry/backoff hữu hạn, không deadlock storm |
| Metadata DB chậm | Delay repository writes | Checkpoint đúng, không giả completion |
| API latency p99 tăng | Fake API delay 10s | HTTP permit bounded, JDBC TX không bị giữ nếu tách phase |
| API rate limit | Trả 429 + Retry-After | Giảm request rate, không retry storm |
| API 503/outage | Fail 100% trong 1 phút | Circuit breaker/backoff và durable work state |
| Consumer prefetch quá cao | Tăng payload/prefetch trên test | Memory budget phát hiện overflow, config được hạ |
| Broker ACK lost | Publish/consume rồi drop ACK | Redelivery không nhân đôi effect |
| Executor rejection | Queue đầy rồi submit thêm | Work có recover path; không marked COMPLETED |
| Worker OOMKill | Kill pod giữa chunk | Restart đúng checkpoint, writer idempotent |
| Horizontal rollout surge | Chạy old+new pods đồng thời | Global DB/API quotas vẫn được tôn trọng |
| Multiple jobs | Daily SLA + backfill đồng thời | Per-job admission bảo vệ job ưu tiên |
| Crash after DB commit | Kill trước checkpoint/reply | Replay an toàn hoặc reconciliation detect lệch |
| Partition plan drift | Thay manifest giữa restarts | Fail closed, không silently repartition |
| Shutdown under load | Graceful SIGTERM rồi timeout | Không mất durable messages/partitions |
| Retry budget exhausted | Dependency fail dài | Fail rõ, DLQ/quarantine theo policy, không loop vô hạn |

### 20.3. Tiêu chí đánh giá benchmark

Một run đạt yêu cầu phải có đồng thời:

1. **Business output đúng** theo unique keys, versions, totals và invariants.
2. **Throughput đã commit** đạt mục tiêu với headroom (không dùng read attempts).
3. **SLA end-to-end** gồm processing, retry, validation, publish và recovery.
4. **Không vượt quota** DB connections, API rate/in-flight, broker limits, CPU/RSS.
5. **Không có queue growth vô hạn**; backlog có khả năng drain theo ETA.
6. **Rollback/retry có giới hạn**, không nhân đôi side effects.
7. **Restart giống clean run** khi fault-injection xảy ra.
8. **Metadata/JobRepository** phản ánh tiến độ hợp lệ.
9. **Work bị reject/dead-letter** vẫn có owner và recover path.
10. **Worker scaling/rollout** không phá quotas hoặc partition identity.

Một cấu hình nhanh hơn 30% nhưng tạo duplicate payments hoặc mất item khi crash **không đạt**.

## 21. Runbook khi job chậm và nhiều resource cùng báo lỗi

Một thứ tự điều tra hữu ích:

1. **Khóa identity:** job name, JobInstanceId, snapshot, partition plan, số JobExecutions đang hoạt động.
2. **Đo committed throughput:** có đang giảm thật không, hay chỉ `readCount`/attempts tăng?
3. **Xác định tầng chạm trần:** executor active/queued/rejected, Hikari pending, DB locks, API 429, broker unacked, CPU throttling hay RSS.
4. **Kiểm tra concurrency thực:** active workers trên tất cả pods và các jobs cạnh tranh cùng pools.
5. **Kiểm tra quota rollout:** old+new pods, HPA max replicas, online traffic reservation.
6. **So resource hold times:** JDBC acquire/hold, chunk transaction p99, HTTP p99, broker ACK lag.
7. **Kiểm tra retry amplification:** có lỗi transient ở nhiều tầng cùng retry vô hạn không?
8. **Nếu overload đang diễn ra:** giảm admission/worker concurrency theo quy trình được chứng minh; không tăng tất cả pools cùng lúc.
9. **Đảm bảo durability:** không ACK/drop item khi hạ tải; JobRepository/queue lưu work còn tồn.
10. **Nếu là API quota:** áp shared limiter, Retry-After, giảm pods/permits, không chỉnh JDBC vô nghĩa.
11. **Nếu là DB contention:** xem transaction boundary/SQL/index/lock ordering, giảm chunk/worker concurrency khi cần.
12. **Nếu là metadata bottleneck:** đo StepExecution/context update latency và batch repository pool, cân nhắc chunk/partition size có test.
13. **Nếu là memory:** hạ chunk size/prefetch/queue/concurrency trước khi tăng container limit.
14. **Nếu worker đã crash:** điều tra STARTED/UNKNOWN, liveness và side effects trước restart.
15. **Đối soát output:** business keys, source versions, outbox events, totals, checksums.
16. **Thay đổi một tham số mỗi lượt:** lưu trước/sau committed throughput, error rate và SLA ETA.
17. **Cập nhật capacity contract:** giới hạn per-pod/cluster, max rollout pods và các ngưỡng cảnh báo.

### 21.1. Những quyết định không nên làm dưới áp lực incident

- Tăng `maximumPoolSize` trên mọi worker pods khi DB `max_connections` đang gần trần.
- Tăng số consumers và prefetch khi business writer đang chờ locks.
- Bật retry không giới hạn để “job tự hết lỗi”.
- Tắt timeout hoặc tăng queue vô hạn để che errors.
- Gọi HTTP trong chunk transaction rồi `Thread.sleep()` để chờ quota.
- Đổi partition ranges/key giữa restart để “cân bằng lại”.
- Chuyển metadata sang DB khác mà không có idempotency/reconciliation.
- Sửa `BATCH_STEP_EXECUTION.STATUS` trực tiếp để vượt trạng thái FAILED.
- Bỏ qua reconciliation vì `BatchStatus.COMPLETED`.

### 21.2. Khi nào nên giảm thay vì tăng worker count?

Giảm worker concurrency khi:

- DB lock waits/deadlocks tăng nhanh hơn committed throughput.
- Hikari pending cao dù CPU thấp.
- HTTP 429/503 và retry storm tăng.
- Broker redelivery/unacked backlog phình do consumer xử lý quá lâu.
- Heap/RSS hoặc GC pauses tăng với số chunks in-flight.
- Metadata DB update p99 vượt mức an toàn.
- Work đã đầy đủ concurrency nhưng downstream throughput phẳng.

Tăng worker count chỉ khi **bottleneck thật còn headroom** và benchmark ở cấp cluster chứng minh output/SLA cải thiện.

## 22. Những hiểu nhầm thường gặp

| Nhận định | Điều cần chỉnh |
| --- | --- |
| “Executor có 32 threads thì job chạy được 32 DB writes đồng thời.” | Chỉ nếu JDBC pool/DB thực chịu được, writer transaction tham gia đúng. |
| “GridSize chính là max worker threads.” | GridSize liên quan partition dispatch/splitting; executor/remote worker capacity khác. |
| “Chunk size là concurrency.” | Chunk size là số items/commit, không phải thread limit. |
| “Queue càng lớn càng an toàn.” | Queue trong RAM che overload, tăng latency/memory, không durable. |
| “MaxPoolSize=32 thì executor chắc dùng 32 threads.” | Queue unbounded có thể giữ executor ở core threads. |
| “ThrottleLimit là cách chuẩn mới cho Spring Batch 5.2.” | API đã deprecated từ 5.0; cần thiết kế bounded execution phù hợp. |
| “Hikari connectionTimeout là transaction timeout.” | Chỉ giới hạn thời gian chờ mượn connection. |
| “Mỗi pod pool 10 nên DB chỉ cần 10 connections.” | Tổng pool tăng theo pods, jobs và services. |
| “Cùng DB URL nghĩa chung transaction.” | Connections/pools/managers khác có thể độc lập. |
| “Semaphore 3 permits giới hạn API toàn cluster ở 3 calls.” | Mỗi JVM có 3; nhiều pods cộng lại. |
| “Concurrency limit 20 nghĩa tối đa 20 req/s.” | Concurrency và rate là hai đơn vị khác. |
| “HTTP 429 thì tăng threads để gửi lại nhanh.” | Tăng tải; phải tuân Retry-After/rate budget. |
| “Prefetch 100 luôn nhanh hơn 10.” | Có thể tăng unacked backlog/memory và unfairness. |
| “Tăng connections luôn làm DB nhanh hơn.” | DB có thể bị CPU/lock/IOPS contention sớm hơn. |
| “CPU thấp nghĩa còn nhiều capacity.” | Workers có thể chờ DB/API/broker/locks. |
| “Worker count giống nhau ở mọi job là công bằng.” | Jobs có work demand/SLA khác, cần quotas/admission. |
| “RetryLimit 3 bảo đảm tối đa 3 calls trên toàn hệ thống.” | Nhiều tầng/JobExecutions có thể retry lại. |
| “Không có rejected tasks nghĩa không overload.” | Unbounded queue có thể âm thầm tích backlog. |
| “Thêm pods không ảnh hưởng partner API.” | Global in-flight/rate demand tăng; rolling surge còn cộng thêm. |
| “Completed nghĩa event đã xử lý đúng duy nhất.” | Cần business reconciliation và consumer idempotency. |

## 23. Checklist trước production

- [ ] Có resource budget ledger theo **cluster, mỗi pod, mỗi job và mỗi phase**.
- [ ] Đã tính online traffic, admin/HA reserve và max rollout pods.
- [ ] Worker concurrency không vượt executor active cap/CPU/memory budget.
- [ ] Executor queue bounded, rejection/overload có durable recovery.
- [ ] Không phụ thuộc `throttleLimit` deprecated làm kiểm soát duy nhất.
- [ ] `gridSize` không bị nhầm với threads/pods; partition manifest ổn định.
- [ ] Chunk size được benchmark theo memory, commit overhead, lock và rollback scope.
- [ ] Hikari pools của **mọi pods/manager/services** nằm trong DB connection budget.
- [ ] Reader cursor và JobRepository có pool budget nếu cần connection riêng.
- [ ] JDBC connection hold p99 không kéo dài bất hợp lý vì network wait.
- [ ] API có in-flight cap **và** rate cap khi contract yêu cầu cả hai.
- [ ] Shared quota accounting hoạt động khi autoscaling và rolling update surge.
- [ ] HTTP deadlines/retry/backoff hữu hạn, API idempotency key ổn định.
- [ ] Broker consumer concurrency/prefetch/unacked được đo theo memory và downstream capacity.
- [ ] Retry ở các tầng không nhân tải vượt quota; DLQ/quarantine có owner.
- [ ] Có admission control bảo vệ daily SLA khỏi backfill job.
- [ ] CPU throttling, heap/RSS, GC và executor queue age được đo ở peak.
- [ ] Có cảnh báo sớm DB lock wait, Hikari pending, API 429, broker lag và OOM.
- [ ] Có capacity contract đồng bộ với config/deployment, không chỉ một tài liệu tĩnh.
- [ ] Resource constraints được kiểm thử lúc dependency slow/unavailable.
- [ ] Shutdown và worker crash không làm mất work đang chờ trong memory.
- [ ] JobRepository metadata và business writer transaction/restart semantics được kiểm tra.
- [ ] Writer idempotent theo business key/version, external effects có outbox/inbox khi cần.
- [ ] Mỗi benchmark đo committed throughput và output correctness.
- [ ] Không publish JobExecution chỉ vì status COMPLETED nếu reconciliation chưa đạt.

## 24. Câu hỏi tự kiểm tra

1. Vì sao tăng `ThreadPoolTaskExecutor.maxPoolSize` mà throughput không tăng khi queue quá lớn?
2. `gridSize`, `chunk(200)` và worker thread count khác nhau thế nào?
3. Có 8 pods, mỗi pod Hikari max 15, manager max 5 và online services dùng 20: trần connections của nhóm bằng bao nhiêu?
4. Một API cho 20 in-flight và 60 req/s. Nếu mỗi request mất 1 giây, cần cả hai giới hạn không?
5. Vì sao `Semaphore(3)` trong 6 pods có thể tạo tới 18 HTTP calls đồng thời?
6. Nếu rolling update có 6 pods cũ + 3 pods mới, per-pod permits=3, global budget 18 thì vi phạm bao nhiêu?
7. `connectionTimeout` của Hikari giới hạn điều gì?
8. Nếu chunk giữ JDBC connection qua 400 ms HTTP, nên tăng pool hay thay transaction boundary trước?
9. Với mục tiêu 800 items/s và mỗi worker đạt 160 items/s ở zero contention, số worker lý tưởng là bao nhiêu?
10. Nếu giả định hiệu suất song song còn 70%, cần khoảng bao nhiêu worker theo cách ước lượng bài học?
11. Dùng Little's law, 40 req/s với latency trung bình 300 ms cần trung bình bao nhiêu HTTP in-flight?
12. Với sáu pods × pool 10, manager pool 4, online 35, reserve 15, DB budget 120, còn bao nhiêu connection trần?
13. Vì sao 64 worker threads không nhất thiết cải thiện batch CPU-bound trên 4 vCPU?
14. Vì sao prefetch quá cao có thể gây OOM dù consumer concurrency không đổi?
15. Một API outage có `p=0.2` và ba retries bổ sung: số attempts kỳ vọng theo mô hình độc lập là bao nhiêu?
16. Vì sao retryLimit của một Step không nhất thiết là retry budget toàn vòng đời operation?
17. Khi executor reject một partition task, việc nào phải được giữ bền vững?
18. JobRepository và business DB khác datasource có thể gặp failure window nào?
19. Nên đo metric gì để biết DB pool hay API quota đang chạm trần?
20. Vì sao `BatchStatus.COMPLETED` không đủ chứng minh không mất/trùng business records?
21. Khi job chậm, nên xem throughput “read attempts” hay “committed unique records”?
22. Cấu hình `app.batch.external-api.max-rate-per-second-per-pod` trong YAML có tự tạo rate limiter không?
23. Vì sao max replicas lúc rolling update cần có trong tính toán quota?
24. Khi nào giảm concurrency là biện pháp bảo vệ tốt hơn tăng JDBC pool?

**Gợi ý trả lời:** (1) Tasks vào queue trước khi executor tăng vượt core. (2) Grid chia work, chunk là commit interval, threads là concurrency thực. (3) `8×15+5+20=145` (chưa tính reserve khác). (4) Có; concurrency lý tưởng giới hạn khoảng 20 req/s trong giả định, rate vẫn là contract riêng. (5) Mỗi JVM có permits riêng. (6) 27-18=9 in-flight. (7) Thời gian chờ mượn connection. (8) Rút transaction ngắn và gọi API ngoài DB TX trước. (9) `ceil(800/160)=5`. (10) `ceil(800/(160×0.7))=8`. (11) `40×0.3=12`. (12) `120-(60+4+35+15)=6`. (13) CPU quota/throttling và context switching. (14) Buffer unacked payloads. (15) `1.248` attempts. (16) Có nhiều retry layers và JobExecutions. (17) Partition manifest, metadata/work queue để restart. (18) Business commit trước checkpoint hoặc ngược lại. (19) Hikari pending/lock wait vs HTTP 429/in-flight/p99. (20) Cần reconciliation. (21) Committed business records. (22) Không, custom properties cần code wiring. (23) Old+new pods đồng thời tiêu thụ permits. (24) Khi lock/retry/pool contention tăng và committed throughput không tăng.

## Tài liệu tham khảo

- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): multi-threaded Step, partitioning, gridSize, pooled resources và ghi chú throttleLimit deprecated.
- [Spring Batch 5.2 — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html): commit interval/transaction boundary.
- [Spring Batch 5.2 — Restarting a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): checkpoint và `ExecutionContext`.
- [Spring Batch 5.2 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): metadata transactions và isolation.
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max threads, queueCapacity, task rejection và shutdown.
- [Spring Framework — TaskExecutor / TaskScheduler](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executor implementations và task scheduling.
- [HikariCP — README, Configuration Knobs](https://github.com/brettwooldridge/HikariCP): `maximumPoolSize`, `connectionTimeout`, `minimumIdle` và connection lifetime.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): pool size là capacity decision, không phải càng lớn càng tốt.
- [Spring Batch Integration — Remote Chunking](https://docs.spring.io/spring-batch/reference/5.2/spring-batch-integration/sub-elements.html): mô hình middleware/remote worker và reply handling.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): consumer concurrency và cấu hình listener.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): prefetch và unacknowledged deliveries.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests/limits, throttling và OOM.
- [Resilience4j — Rate Limiter](https://resilience4j.readme.io/docs/ratelimiter): rate control và giới hạn trong ứng dụng.

**Điểm cốt lõi:** Mở rộng Spring Batch hiệu quả cần **một ngân sách tài nguyên nhất quán từ Job admission → partition/thread executor → JDBC/JobRepository → HTTP quota → broker → CPU/heap**, được thực thi trên **toàn cluster kể cả rolling updates**, chứ không phải tăng từng pool riêng lẻ. `gridSize`, chunk size, thread count, connection pool size, queue capacity, API in-flight và requests/s là **các đại lượng khác nhau**. Hãy thiết kế bounded concurrency, durable backpressure, short transactions, idempotency và retry budget có kiểm soát; chỉ tăng worker count khi **committed throughput, output correctness và SLA** đều được kiểm chứng bằng benchmark/fault injection.
