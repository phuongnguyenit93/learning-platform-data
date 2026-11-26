# Phân tích giới hạn tài nguyên dùng chung khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện các tài nguyên **dùng chung** giữa worker, partition, flow, `JobExecution`, replica và ứng dụng khác: CPU, heap, thread pool, JDBC connection, lock, I/O, JobRepository, mạng, broker và API.
- Phân biệt khả năng cấp phát tài nguyên **trong một process** với giới hạn vật lý hoặc quota **trên toàn hệ thống**.
- Tạo ngân sách tài nguyên, tính số worker tối đa theo nút thắt và dành dự phòng khi chạy nhiều job đồng thời.
- Phát hiện dấu hiệu saturation, hàng đợi tăng, lock contention, retry storm và chênh lệch tải giữa partition qua số đo thực tế.
- Lựa chọn giữa multi-threaded step, parallel steps, partitioning và worker phân tán dựa vào ràng buộc nguồn/đích.
- Đặt giới hạn executor, pool, concurrency và chính sách vận hành để tăng throughput mà vẫn giữ thread safety, restart và tính đúng đắn dữ liệu.

## 1. Vì sao tài nguyên dùng chung quyết định khả năng scale?

Giả sử job nhập 12 triệu đơn hàng từ PostgreSQL, chuẩn hóa dữ liệu rồi ghi vào bảng đích. Bắt đầu bằng một worker, job chạy đúng nhưng quá thời hạn. Tăng lên tám partition làm CPU ứng dụng tăng vừa phải; tuy nhiên thời gian hoàn tất chỉ giảm một chút, thỉnh thoảng còn phát sinh `SQLTransientConnectionException`, deadlock và nhiều retry.

Nguyên nhân có thể là: **worker chạy riêng nhưng cùng cạnh tranh một cơ sở dữ liệu**, connection pool, lock, storage và metadata của Spring Batch. Tăng số worker chỉ tăng số yêu cầu được gửi đến nút thắt, không tạo thêm năng lực cho nút thắt đó.

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, cần phân tích tài nguyên trước khi chọn multi-threaded step, parallel steps, partitioning hoặc mô hình phân tán. Những kiến trúc này thay đổi nơi và cách công việc chạy, nhưng không tự nhân đôi throughput của DB, băng thông mạng hay giới hạn API.

~~~mermaid
flowchart TD
    J["Scheduler → Spring Batch Job"] --> M["Manager Step / Split"]
    M --> W1["Worker / Flow 1"]
    M --> W2["Worker / Flow 2"]
    M --> W3["Worker / Flow N"]
    W1 --> CPU["CPU / RAM / Thread pool"]
    W2 --> CPU
    W3 --> CPU
    W1 --> DB["DB connections, locks, I/O"]
    W2 --> DB
    W3 --> DB
    W1 --> API["API / Network / Broker"]
    W2 --> API
    W3 --> API
    M --> JR["JobRepository metadata"]
    W1 --> JR
    W2 --> JR
    W3 --> JR
~~~

Câu hỏi cốt lõi là: **ở mức song song dự kiến, tổng nhu cầu tài nguyên có vượt giới hạn dùng chung nào không?** Nếu có, kiến trúc phải thêm backpressure, điều tiết concurrency hoặc cải thiện nguồn tài nguyên đó.

## 2. Xác định phạm vi chia sẻ của từng tài nguyên

Một giới hạn chỉ có ý nghĩa khi xác định **ai đang dùng chung** và **giới hạn áp dụng ở đâu**.

| Tài nguyên | Phạm vi chia sẻ điển hình | Dấu hiệu quá tải |
| --- | --- | --- |
| CPU / CPU quota container | Các thread trong một process/pod, các process trên node | CPU throttling, processor latency tăng, run queue cao |
| Heap, direct memory, GC | Tất cả worker/flow trong JVM | GC pause, tăng heap sau chunk, `OutOfMemoryError` |
| `TaskExecutor` / thread pool | Các task dùng cùng executor trong JVM | Active thread chạm max, queue tăng, task bị từ chối |
| JDBC connection pool | Những thao tác dùng **cùng `DataSource` instance** trong một process | Pending connection, timeout chờ connection |
| Giới hạn session của DB | **Tất cả pool** từ mọi pod/ứng dụng nối tới DB | Số session gần `max_connections`, backend quá tải |
| DB lock, WAL, storage IOPS | Các transaction ghi/đọc trên cùng DB, bảng/index | Lock wait, deadlock, I/O latency, commit chậm |
| `JobRepository` | Các job/worker dùng chung repository metadata | Metadata SQL chậm, conflict, nhiều commit/partition update |
| Network, object storage | Pod/node/VPC, endpoint, bucket hoặc thiết bị dùng chung | Bandwidth đầy, request latency, throttling |
| Broker partitions / consumer quota | Nhiều worker dùng cùng topic, queue hoặc consumer group | Lag, in-flight tăng, redelivery |
| API rate limit | API key, account/tenant, IP hoặc endpoint theo hợp đồng | HTTP 429, timeout, retry tăng |
| Khóa nghiệp vụ | Cùng account, tenant, row tổng hợp hoặc file đích | Lost update, lock contention, kết quả phụ thuộc thứ tự |

**Quan trọng:** một `HikariDataSource` có `maximumPoolSize=10` trong mỗi replica không tạo pool mười connection **cho toàn cluster**. Nếu có ba replica giống nhau, tổng số connection có thể lên tới ba mươi, chưa kể pool riêng cho JobRepository hoặc ứng dụng khác.

Tương tự, `gridSize=16` mô tả số partition dự kiến; số task thực thi đồng thời còn phụ thuộc `PartitionHandler`, `TaskExecutor`, số worker remote và các giới hạn triển khai. Đừng dùng `gridSize` làm số connection thực tế mà không đo.

### Tài nguyên “riêng” nhưng gây tác động “chung”

Mỗi partition có `StepExecution` và reader `@StepScope` riêng vẫn có thể dùng **chung** một DB. Bean reader riêng bảo vệ state cursor của worker, nhưng không loại bỏ giới hạn storage, số connection hay tranh chấp row.

Transaction chunk của partition A và partition B là hai transaction độc lập. Nếu chúng cập nhật cùng row tổng hợp, một transaction có thể chặn transaction kia hoặc deadlock, dù hai partition đã được chia theo ID không chồng lấn.

## 3. Phân tích cả workload nền và workload đỉnh

Không nên chỉ thống kê “job này cần tám connection”. Cần vẽ toàn bộ những thứ có thể hoạt động **đồng thời** trong cửa sổ batch:

- Số replica của dịch vụ batch, số `JobExecution` có thể chạy cùng lúc và số flow/partition tối đa mỗi job.
- Tải đọc/ghi từ API phục vụ người dùng, CDC/ETL khác, báo cáo, transaction OLTP và hoạt động bảo trì DB.
- Worker remote, message consumers, các service dùng chung API key hoặc storage.
- Số connection dùng bởi reader, writer, checkpoint/metadata, health check và tác vụ điều hành.
- Lượng buffer/cursor, chunk size, payload p95/p99, thời gian giữ lock và độ lớn object trong heap.
- Thời điểm dữ liệu dồn (cuối ngày/cuối tháng), retry sau timeout và nhu cầu chạy bù nhiều ngày.

Một bảng tài nguyên nên có **giới hạn**, **tải nền đã giữ chỗ**, **khả dụng còn lại** và **khoảng dự phòng**. Có thể cần nhiều bảng cho CPU, DB, broker và API vì không thể cộng “connection” với “request/s” thành một con số duy nhất.

| Tài nguyên ví dụ | Giới hạn đã xác nhận | Tải nền / phần giữ chỗ | Ngân sách ban đầu cho batch |
| --- | ---: | ---: | ---: |
| DB connection | 100 session tối đa | 64 session cho các hệ khác và vận hành | 36 session |
| CPU node dành cho batch | 16 vCPU khả dụng | 4 vCPU cho dịch vụ khác | 12 vCPU |
| API ngoài | 500 request/giây theo API key | 200 request/giây từ realtime | 300 request/giây |
| Writer DB | 1.500 lượt ghi tương đương/giây bền vững | Đã đo dưới tải đồng thời | Không được tính cao hơn 1.500/s |
| Shared storage | 800 MiB/giây đọc tối đa đo được | 450 MiB/giây tải khác | 350 MiB/giây trước headroom |

Các con số là **giả định của bài học**, không phải cấu hình chuẩn của Spring Batch. Đặc biệt, `max_connections` là giới hạn session, **không** đồng nghĩa DB xử lý hiệu quả ở số session đó; bão hòa CPU/IO hoặc lock có thể xảy ra trước.

### Khi nhiều job cùng chạy

Giả sử mỗi job có bốn partition. Nếu scheduler cho phép hai `JobExecution` cùng chạy và mỗi job dùng executor riêng có bốn worker, số worker đồng thời có thể tăng lên tám. Nếu hai replica cùng nhận lịch, tổng có thể tăng tiếp. Việc giới hạn “bốn worker/job” không tự đặt giới hạn “bốn worker/cluster”.

Phân tích tài nguyên cần lập **đồ thị concurrency tối đa**, bao gồm job chạy bù, retry, restart và đợt deploy có hai phiên bản ứng dụng chạy song song. Khi có đường truy cập chạy tay qua API, đường đó cũng phải tuân thủ chính sách tài nguyên.

## 4. Tính ngân sách connection DB theo toàn hệ thống

### 4.1. Công thức ngân sách

Đặt:

- `C_batch`: tổng số session DB cho batch sau khi trừ hệ khác và phần vận hành.
- `P`: số replica batch chạy đồng thời.
- `F`: số connection cố định dự trù trong **mỗi replica**, ngoài số connection tiêu thụ tỷ lệ với worker.
- `c`: số connection **tối đa quan sát/ước lượng** mỗi worker cần đồng thời ở hoạt động bình thường.
- `h`: tỷ lệ ngân sách connection biến thiên cần để trống làm headroom.

Nếu mỗi replica có `w` worker song song, mô hình cận trên đơn giản là:

~~~text
C_fixed = P × F
C_variable = C_batch - C_fixed

P × w × c ≤ C_variable × (1 - h)

w_max = floor(C_variable × (1 - h) / (P × c))
~~~

Cần bảo đảm `C_variable > 0`. Công thức này giả định các replica đồng nhất, các worker có nhu cầu tương đương và `c` đã tính đủ mọi connection cùng lúc. Khi có nhiều datasource (business DB, JobRepository DB, audit DB), lập **ngân sách riêng cho từng DB**.

### 4.2. Ví dụ: hai replica và pool chia sẻ

Giả sử DBA xác nhận trong 100 session DB, phải dành 64 cho ứng dụng khác/vận hành, tức `C_batch=36`. Batch chạy **2 replica**, mỗi replica cần khoảng **4 connection cố định** cho các tác vụ ngoài worker. Quan sát cho thấy một worker có thể giữ **2 connection cùng lúc** (ví dụ reader cursor và transaction ghi ở hai connection; tùy driver và cấu hình thực tế). Muốn để trống 25% phần connection biến thiên:

~~~text
C_fixed     = 2 × 4 = 8
C_variable  = 36 - 8 = 28
Headroom    = 25% của C_variable

Tổng worker tối đa theo ngân sách
    = floor(28 × 0,75 / 2)
    = floor(10,5)
    = 10 workers

Hai replica đồng đều: tối đa 5 worker / replica.
Connection dự kiến = 8 + (2 × 5 × 2) = 28
Còn trống = 36 - 28 = 8 session trong phần được cấp cho batch.
~~~

Nếu tăng từ **5 lên 8 worker mỗi replica**, cùng giả định 2 connection/worker:

~~~text
C_needed = 2 × 4 + 2 × 8 × 2 = 40
40 > 36  → vượt ngân sách session batch.
~~~

Hệ thống có thể bắt đầu chờ connection hoặc chiếm tài nguyên được giữ cho dịch vụ khác. Tăng `maximumPoolSize` trên mỗi replica không làm tăng `max_connections` của DB.

**Cảnh báo về giả định:** số connection/worker phụ thuộc reader cursor/paging, transaction manager, nguồn DB, việc reader dùng connection nào, kích thước pool và retry. Có cấu hình chỉ dùng một connection đồng thời cho worker, cấu hình khác cần nhiều hơn. Công thức phải được **hiệu chỉnh từ peak usage đo trong workload thật**, không áp đặt “2” như hằng số.

### 4.3. Quan hệ giữa thread pool, connection pool và DB

~~~mermaid
flowchart LR
    E["Executor: tối đa 5 worker / replica"] --> H["JDBC pool: hạn mức per replica"]
    H --> G["DB server: giới hạn session toàn hệ thống"]
    E --> Q["Task queue có giới hạn"]
    G --> L["DB CPU, lock, WAL và I/O"]
~~~

Tăng số thread trước khi xác định `C_needed` có thể tạo hàng dài chờ connection và gây timeout. Tăng pool chỉ giúp worker nhận connection sớm hơn **nếu DB còn khả năng xử lý**. Tăng `max_connections` trong khi storage đang bão hòa có thể làm lock wait và latency xấu thêm.

Đặc biệt, nếu **cùng một pool** vừa cấp connection cho reader đang giữ cursor vừa cấp transaction writer, một worker có thể chờ một connection khác trong khi vẫn giữ connection cũ. Nếu pool quá nhỏ và nhiều worker đều giữ một connection rồi chờ thêm, hệ thống có nguy cơ đình trệ. Cần đo cấu hình reader/driver cụ thể, cân nhắc paging reader, giới hạn concurrency hoặc tách/tối ưu cách dùng nguồn DB.

## 5. DB bottleneck không chỉ là số connection

### 5.1. Lock và tranh chấp dữ liệu

Hai partition đọc input không chồng lấn vẫn có thể cùng ghi vào một row tổng hợp:

~~~sql
-- Hai worker cập nhật cùng một row ngày 2026-11-25.
UPDATE daily_summary
SET total_amount = total_amount + :amount
WHERE business_date = :businessDate;
~~~

Database có thể tuần tự hóa các transaction trên row này bằng lock; throughput tăng rất ít dù CPU application còn rảnh. Nếu logic writer trước đó đọc giá trị rồi cập nhật trong hai câu SQL không có cơ chế phù hợp, còn có rủi ro lost update.

Giải pháp tùy nghiệp vụ: mỗi worker ghi **partial aggregate** theo `(businessDate, partitionId)` rồi một bước reduce/merge sau khi các partition hoàn tất; hoặc dùng atomic update và chấp nhận/đo lock contention. Idempotency cũng cần xét: `total_amount = total_amount + :amount` không an toàn nếu chunk được thực hiện lại sau sự cố ngoài transaction.

### 5.2. Query và index

Khi mỗi worker dùng:

~~~sql
SELECT order_id, payload
FROM source_order
WHERE order_id >= :fromId
  AND order_id < :toId
ORDER BY order_id;
~~~

Index phù hợp trên `order_id` có thể giúp giới hạn dữ liệu đọc. Nếu DB planner vẫn chọn full table scan cho từng partition, tám worker có thể biến một lần quét thành tám lần quét cạnh tranh I/O. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trên dataset đại diện để kiểm tra execution plan, số block đọc và thời gian. Hạn chế chạy `EXPLAIN ANALYZE` với truy vấn ghi nguy hiểm trên production vì lệnh đó **thực sự thực thi** truy vấn.

Reader cursor lâu có thể giữ session/transaction hoặc snapshot theo cấu hình, tạo áp lực VACUUM/lock. Paging reader có overhead truy vấn và yêu cầu sort key duy nhất; lựa chọn phải dựa trên phép đo và tính đúng khi restart.

### 5.3. Commit, WAL, IOPS

Nếu một worker ghi mỗi item một câu SQL, writer có thể bị giới hạn bởi round trip và WAL. `JdbcBatchItemWriter` hoặc JDBC batch update có thể giảm overhead nếu phù hợp. Tuy vậy, chunk quá lớn làm transaction dài, tăng thời gian giữ lock, heap sử dụng và lượng công việc phải retry khi rollback.

Một mối quan hệ đơn giản:

~~~text
R_effective ≤ min(R_read, R_process, R_write, R_external)
~~~

Các `R` phải quy đổi về **cùng đơn vị công việc** và đo dưới tải đồng thời. Tốc độ ghi `1.500 lượt SQL/s` không tự có nghĩa `1.500 order/s` nếu mỗi order sinh ba lượt ghi.

## 6. CPU, memory, GC và giới hạn container

### 6.1. CPU có thể hết dù nhiều worker đang chờ I/O

Nếu một item cần trung bình `5 ms CPU` trong processor và mục tiêu là `2.000 item/s`, nhu cầu CPU lý tưởng riêng cho phần processor:

~~~text
CPU busy ≈ 2.000 × 0,005 = 10 CPU-cores
~~~

Để vận hành quanh 70% utilization thay vì liên tục sát 100%, nhu cầu provision xấp xỉ `10 / 0,70 ≈ 14,3 cores`, chưa kể reader, writer, GC và overhead. Nếu container chỉ được cấp 8 CPU, tăng từ 8 lên 32 thread CPU-bound không tạo thêm core; có thể tăng context switch hoặc CPU throttling.

Với **CPU quota** của container, cần theo dõi `throttled_time` và mức CPU thực, không chỉ nhìn số core vật lý của node. Remote partitioning có thể bổ sung CPU từ nhiều máy nếu việc phân phối phù hợp, nhưng vẫn phải tính bottleneck chung DB/API.

### 6.2. Bộ nhớ không tăng tuyến tính “miễn phí”

Bộ nhớ có thể tăng theo:

- `chunkSize × số worker × kích thước item trong bộ nhớ`.
- Buffer của reader/writer, JDBC fetch size, cache, request/response HTTP, serialization.
- Số thread và stack, queue task chưa xử lý, số batch đang đợi commit.
- Object graph lớn hơn kích thước payload thô, GC retention và direct buffers.

Ví dụ một replica có năm worker, mỗi worker giữ tối đa 200 item kích thước **trung bình thực trong heap** là 64 KiB:

~~~text
5 workers × 200 items × 64 KiB ≈ 62,5 MiB
~~~

Đó mới là phần dữ liệu item được tính trực tiếp; heap thực còn chứa buffer, writer, map phụ trợ, JVM và GC. Nếu payload p99 lớn hơn nhiều p50, đừng dùng p50 để tính mức cần tránh `OutOfMemoryError`.

Giới hạn queue executor cũng quan trọng: hàng nghìn `Runnable` giữ closure/payload lớn có thể tiêu tốn heap trước cả khi worker nhận task. Backpressure nên áp dụng **trước khi** tạo quá nhiều item/task trong bộ nhớ.

### 6.3. Chọn biểu đồ thời gian phù hợp

CPU saturation, GC pause và DB latency có thể xuất hiện theo pha. Xem **p95/p99 chunk duration** và thời gian end-to-end của job, không chỉ CPU trung bình một phút. Một sự cố GC 30 giây đúng lúc gần SLA có thể quan trọng hơn việc throughput trung bình ngày thường rất đẹp.

## 7. Executor và số tầng song song

Trong một job, có thể có ba tầng:

1. **Parallel steps:** `split` chạy nhiều flow đồng thời.
2. **Partitioning:** mỗi flow lại có manager step tạo nhiều worker step.
3. **Song song trong worker:** worker xử lý item/chunk/processor đồng thời tùy kiến trúc và phiên bản Spring Batch.

Số task khả dĩ có thể nhân qua các tầng nếu chúng dùng những executor độc lập và tài nguyên cho phép. Giả sử hai flow, mỗi flow có bốn partition: có thể có **tối đa tám worker partition** cùng hoạt động, chưa tính thread điều phối. Nếu hai `JobExecution` cùng chạy, nhu cầu có thể nhân tiếp.

~~~mermaid
flowchart TD
    J["Một JobExecution"] --> S["split"]
    S --> F1["Flow A"]
    S --> F2["Flow B"]
    F1 --> M1["Manager A: 4 partitions"]
    F2 --> M2["Manager B: 4 partitions"]
    M1 --> A1["A0"]
    M1 --> A2["A1"]
    M1 --> A3["A2"]
    M1 --> A4["A3"]
    M2 --> B1["B0"]
    M2 --> B2["B1"]
    M2 --> B3["B2"]
    M2 --> B4["B3"]
~~~

**Không cộng máy móc `gridSize` qua các flow nếu một executor chung giới hạn concurrent tasks.** Hãy dựng **đồ thị thực thi**, đọc cấu hình executor và đo active thread. Ngược lại, nếu hai flow có executor độc lập, giả định mỗi executor tự bảo vệ tổng tài nguyên toàn job là sai.

### Tạo executor có giới hạn rõ ràng

Ví dụ Spring Framework/Spring Batch 5.x, một executor dành cho local partition manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class PartitionExecutorConfiguration {

    @Bean(name = "partitionExecutor")
    ThreadPoolTaskExecutor partitionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(5);
        executor.setMaxPoolSize(5);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("partition-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }
}
~~~

Giới hạn **5** ở đây lấy từ ngân sách connection ví dụ **cho một replica**, không phải thông số mặc định được khuyến nghị cho mọi hệ thống. Hàng đợi 10 task chỉ là mức thử nghiệm; cần xem `PartitionHandler` dispatch task thế nào, áp lực bộ nhớ và yêu cầu dừng job. Với `ThreadPoolTaskExecutor`, core/max/queue tương tác theo cơ chế của `ThreadPoolExecutor`; nếu queue còn chỗ, pool thường chưa tăng quá core size. Khi đã cố định core=max, giới hạn đồng thời rõ hơn.

Hàm `setWaitForTasksToCompleteOnShutdown(true)` hỗ trợ graceful shutdown ở tầng executor, **không bảo đảm** mọi external operation hoặc mọi chunk tự động rollback/ack. Việc dừng job phải có cơ chế chờ có giới hạn, điều phối trạng thái Spring Batch và ngăn worker cũ tiếp tục ghi khi một worker mới được khởi động.

### Phân biệt backpressure và timeout

- **Backpressure:** hạn chế lượng công việc nhận thêm theo năng lực nguồn đích, ví dụ queue giới hạn, semaphore, rate limiter hoặc backlog bền vững.
- **Timeout:** giới hạn thời gian chờ connection/API/lock/task. Timeout ngăn chờ vô hạn nhưng không bổ sung năng lực.
- **Retry:** thử lại sau lỗi có khả năng tạm thời. Nếu toàn bộ worker retry ngay vì DB quá tải, mỗi retry lại chiếm connection và có thể kéo dài sự cố.

Một chính sách tốt kết hợp giới hạn in-flight, retry có backoff/jitter, circuit breaker hoặc giảm concurrency khi hệ thống đích báo throttling. Trong cluster, semaphore in-memory chỉ giới hạn **một JVM**; quota dùng chung nhiều replica cần coordinator/limiter được chia sẻ hoặc một giới hạn tổng toàn hệ thống tương đương.

## 8. JobRepository là tài nguyên dùng chung cần tính riêng

`JobRepository` ghi metadata `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`, checkpoint và trạng thái restart. Nếu một job có hàng nghìn partition nhỏ, mỗi partition commit rất nhiều chunk, số lần ghi metadata có thể tăng đáng kể. JobRepository có thể dùng chung DB với nghiệp vụ hoặc một DB riêng; mỗi phương án có bottleneck khác nhau.

Những tình huống cần đo:

- Số `StepExecution` và kích thước `ExecutionContext` của mỗi job.
- Số commit/checkpoint trên giây, độ trễ update metadata.
- Lock contention trên bảng `BATCH_*` hoặc transaction isolation cho thao tác tạo execution.
- Pool connection của repository, kích thước bảng/index metadata và chính sách dọn dữ liệu lịch sử.
- Tác động khi nhiều job được lịch chạy hoặc restart cùng lúc.

**Không tắt checkpoint hoặc giảm metadata tùy tiện** chỉ để tăng tốc. Việc này có thể khiến restart đọc lại toàn bộ hoặc mất khả năng theo dõi lỗi. Hãy điều chỉnh chunk/partition size và cấu trúc state dựa trên trade-off throughput với khả năng phục hồi.

Nếu JobRepository dùng **DB khác** với business DB, transaction ghi metadata và dữ liệu nghiệp vụ không mặc định là một transaction vật lý chung. Khi bị crash ở khoảng giữa hai commit, writer và quy trình restart vẫn cần idempotency. Không giả định hai hệ thống có exactly-once chỉ vì cả hai đều sử dụng JDBC.

## 9. API, broker, mạng và object storage: quota bên ngoài

### 9.1. Tốc độ API phụ thuộc quota chung

Giả sử API xác thực địa chỉ chỉ cho phép **300 request/giây** trên cùng API key. Mỗi item cần một lần gọi. Dù mười worker xử lý được 1.000 item/giây về CPU, throughput liên quan API vẫn bị chặn bởi quota khoảng 300 item/giây khi không dùng cache/batch và không có quota riêng.

Nếu hai ứng dụng cùng chia API key và ứng dụng realtime đã dùng 120 request/giây, ngân sách còn lại cho batch chỉ khoảng **180 request/giây** trước dự phòng. Chạy batch ở 300 request/giây sẽ gây HTTP 429, retry, tăng latency và có thể ảnh hưởng hệ realtime.

Không phải mọi API quota đều đo bằng requests/s. Có thể có burst limit, số request đang bay, số request/ngày, quota theo tenant hoặc giới hạn payload. Đọc contract và đo header/rate-limit response thực tế.

### 9.2. Công suất từ Little's Law

Với hệ thống ổn định, luật Little cho trực giác:

~~~text
L ≈ λ × W

L = số request trung bình đang in-flight
λ = tốc độ hoàn thành request/s
W = thời gian một request ở hệ thống (giây)
~~~

Để duy trì 180 requests/s với latency trung bình 0,25 giây cần xấp xỉ `180 × 0,25 = 45` request đang xử lý đồng thời. Nếu chỉ cho phép 20 in-flight request với cùng latency, throughput tối đa xấp xỉ `20 / 0,25 = 80 requests/s`. Tuy nhiên, tăng in-flight request không vượt được **rate limit 180/s** hoặc cải thiện được latency khi API bị quá tải.

### 9.3. Broker và object storage

Trong remote partitioning/chunking, broker có giới hạn số partition, throughput publish/consume, retention, quota và in-flight message. Nếu manager tạo task nhanh hơn worker nhận/ack, backlog tăng; worker timeout có thể khiến message được giao lại. Phải thiết kế idempotency key và cơ chế tránh hai worker cùng ghi khi lease hết hạn.

Với object storage, nhiều worker tải cùng một file lớn có thể bão hòa băng thông hoặc quota GET, còn ghi cùng một object đích có thể gây ghi đè. Tốt hơn là chia theo manifest file bất biến, output theo khóa riêng từng partition, rồi có bước merge/publish sau khi tất cả phần bắt buộc hoàn thành.

## 10. Nút thắt, độ sử dụng và hiệu ứng hàng đợi

Khi tải gần bằng công suất phục vụ, độ trễ thường tăng **phi tuyến** vì xếp hàng, lock và retry. Một mô hình lý tưởng hóa một server có tốc độ đến `λ` và tốc độ phục vụ `μ`, với `λ < μ`:

~~~text
ρ = λ / μ

Với hàng đợi M/M/1 lý tưởng:
thời gian trung bình trong hệ thống W = 1 / (μ - λ)
~~~

Ví dụ `μ=1.000 request/s`:

| Tốc độ đến `λ` | Utilization `ρ` | Thời gian trung bình mô hình M/M/1 |
| --- | ---: | ---: |
| 500/s | 50% | 2 ms |
| 800/s | 80% | 5 ms |
| 950/s | 95% | 20 ms |
| 990/s | 99% | 100 ms |

Đây là **mô hình toán học minh họa**, không phải dự báo latency thật của DB. Database có nhiều tài nguyên, dịch vụ có thời gian không phân phối mũ, lock và queue ở nhiều tầng; p95/p99 có thể tăng nhanh hơn. Bài học là: đặt toàn hệ thống sát 100% công suất làm giảm khả năng chịu biến động và retry.

Khi có nhiều stage, throughput bền vững bị chặn bởi stage có **năng lực hữu ích thấp nhất** sau khi quy đổi về cùng đơn vị. Việc đo `peak` trên benchmark 30 giây không đại diện cho tốc độ **sustained** trong job hai giờ, khi cache, GC, WAL, nhiệt độ CPU và workload nền đều thay đổi.

## 11. Tính thông lượng dưới nhiều giới hạn tài nguyên

Giả sử một job cần xử lý **12 triệu đơn hàng trong 2 giờ xử lý hữu ích**. Mục tiêu nghiệp vụ:

~~~text
N_required = 12.000.000 đơn hàng
T_available = 2 × 60 × 60 = 7.200 giây

R_effective_target = 12.000.000 / 7.200
                   ≈ 1.667 đơn hàng hợp lệ/giây
~~~

Một benchmark nhỏ cho thấy mỗi worker xử lý tương đương `320 thao tác thô/s`. Tỷ lệ retry/rework làm trung bình mỗi đơn hàng hợp lệ cần `1,10` thao tác thô; nhóm vận hành muốn thêm 20% năng lực so với nhu cầu thô:

~~~text
R_raw_required = 1.667 × 1,10 ≈ 1.833 thao tác/s
R_raw_planned  = 1.833 × 1,20 ≈ 2.200 thao tác/s

Workers lý tưởng cần ≈ ceil(2.200 / 320) = 7
~~~

Đặt **7 worker** chỉ là ước lượng lý tưởng. Quan sát cho thấy năng lực tối đa khi các stage cùng chịu tải:

| Stage / giới hạn | Năng lực thô đo bền vững |
| --- | ---: |
| Reader/source DB | 3.000 thao tác tương đương/s |
| Processor CPU | 2.500 thao tác tương đương/s |
| Writer/business DB | **1.500 thao tác tương đương/s** |
| Worker tổng theo benchmark đơn lẻ, 7 worker | 2.240 thao tác tương đương/s |

Do đó:

~~~text
R_raw_sustainable ≤ min(3000, 2500, 1500, 2240) = 1500/s

R_effective_sustainable ≈ 1500 / 1,10 ≈ 1.364 đơn hàng/s

T_process_estimate ≈ 12.000.000 / 1.364
                   ≈ 8.800 giây ≈ 147 phút
~~~

Mục tiêu chỉ có 120 phút, nên **không đạt SLA**, dù số worker “theo công thức” có vẻ đủ. Nên cải thiện writer, DB/index/I/O, giảm thao tác ghi mỗi order, tăng khả năng DB hoặc điều chỉnh thời gian xử lý; thêm worker sẽ làm tăng xếp hàng mà không vượt trần 1.500/s.

Lưu ý các năng lực phải được đo bằng **cùng loại thao tác** và cùng tải đại diện. Nếu một đơn hàng tạo 3 câu SQL, không được so sánh trực tiếp `3.000 rows/s` với `1.500 SQL calls/s` như thể cùng đơn vị. Con số 147 phút cũng là ước lượng, cần load test end-to-end.

## 12. Java: bộ tính ngân sách worker theo kết nối dùng chung

Đoạn Java 17 sau đây minh họa cách đưa giới hạn vào một phép kiểm tra sơ bộ. Nó chỉ tính dựa trên input được cung cấp, không tự phát hiện kết nối thực tế hoặc bảo đảm an toàn vận hành:

~~~java
public final class SharedResourceBudget {

    public static void main(String[] args) {
        int dbConnectionsForBatch = 36;
        int replicaCount = 2;
        int fixedConnectionsPerReplica = 4;

        // Giá trị lấy từ peak measurement của workload đại diện.
        int connectionsPerWorker = 2;

        // Giữ 25% connection biến thiên làm dự phòng.
        double variableHeadroom = 0.25;

        int fixedTotal = replicaCount * fixedConnectionsPerReplica;
        int variableBudget = dbConnectionsForBatch - fixedTotal;

        if (replicaCount <= 0 || connectionsPerWorker <= 0
                || variableBudget <= 0
                || variableHeadroom < 0 || variableHeadroom >= 1) {
            throw new IllegalArgumentException("Invalid resource budget");
        }

        int maxTotalWorkers = (int) Math.floor(
                variableBudget * (1 - variableHeadroom)
                        / connectionsPerWorker);

        int maxWorkersPerReplica = maxTotalWorkers / replicaCount;
        int plannedWorkersTotal = maxWorkersPerReplica * replicaCount;

        int expectedConnections = fixedTotal
                + plannedWorkersTotal * connectionsPerWorker;
        int freeConnections = dbConnectionsForBatch - expectedConnections;

        System.out.printf("Budget: %d DB sessions%n",
                dbConnectionsForBatch);
        System.out.printf("Max workers aggregate: %d%n", maxTotalWorkers);
        System.out.printf("Max workers per replica: %d%n",
                maxWorkersPerReplica);
        System.out.printf("Expected DB sessions: %d%n",
                expectedConnections);
        System.out.printf("Free DB sessions in budget: %d%n",
                freeConnections);
    }
}
~~~

Kết quả dự kiến:

~~~text
Budget: 36 DB sessions
Max workers aggregate: 10
Max workers per replica: 5
Expected DB sessions: 28
Free DB sessions in budget: 8
~~~

Phải kiểm tra thêm các ràng buộc khác:

~~~text
workers_planned ≤ min(
  workers_limited_by_DB_sessions,
  workers_limited_by_CPU_and_memory,
  workers_limited_by_API_and_network,
  workers_limited_by_writer_locks_and_IO,
  workers_limited_by_thread_pool_and_scheduler
)
~~~

Với API RPS hoặc CPU, không phải lúc nào cũng có phép đổi trực tiếp thành số worker chính xác. Cần biết tài nguyên tiêu thụ **trên một item**, độ phân bố item và concurrency đo thực nghiệm; công thức là điểm bắt đầu để tìm ràng buộc, không thay cho benchmark.

## 13. Quan trắc tài nguyên dùng chung và phân tích sự cố

### 13.1. Các lớp metric nên ghép lại

| Lớp | Metric/quan sát | Mục đích |
| --- | --- | --- |
| **Job/Step** | Duration, read/write/commit/rollback count, status, số partition hoàn tất | Năng lực và tính đúng của Spring Batch |
| **Executor** | Active threads, queue depth, rejection count, task wait | Phát hiện nghẽn dispatch và backpressure |
| **JDBC pool** | Active, idle, pending, acquisition latency, timeout | Phát hiện thiếu pool và nhu cầu connection |
| **Database** | Session count, CPU, lock wait, deadlock, transaction age, WAL/IO | Phát hiện bottleneck chung vượt phạm vi JVM |
| **JVM/pod** | CPU usage/quota/throttling, heap, GC pause, RSS/OOM, network | Giải thích khi worker không dùng hết năng lực |
| **API/broker** | RPS, 429, error, latency, in-flight, lag, retry/redelivery | Giới hạn dịch vụ ngoài và tác động phụ |
| **Nghiệp vụ** | Unique records completed/s, missing/duplicate keys, end-to-end SLA | Chứng minh đầu ra hữu ích, không chỉ số thao tác |

Tên metric cụ thể tùy Spring Boot, Micrometer, JDBC pool, DB và hệ quan sát. Không giả định tất cả tên trong bảng là metric có sẵn; cần kiểm tra instrumentation thực tế. Tránh label theo từng `orderId`/`partitionId` không giới hạn vì cardinality quá cao có thể làm hệ giám sát tốn tài nguyên.

### 13.2. Truy vấn quan sát PostgreSQL

Ví dụ gộp session theo application name/state và loại chờ (quyền đọc `pg_stat_activity` phụ thuộc role và cấu hình):

~~~sql
SELECT application_name,
       state,
       wait_event_type,
       COUNT(*) AS session_count
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state, wait_event_type
ORDER BY session_count DESC;
~~~

Truy vấn này là **quan sát tại một thời điểm**, không thay thế peak connection metrics qua một job dài. Với PostgreSQL có thể quan sát thêm `pg_stat_database`, `pg_stat_statements` khi được bật, dashboard storage và execution plan của truy vấn chậm. Đừng kết luận “thiếu connection” chỉ vì `active` cao: có thể DB đang giới hạn CPU/IO hoặc chờ lock.

### 13.3. Dấu hiệu → giả thuyết → phép kiểm tra

| Hiện tượng | Giả thuyết | Kiểm tra quyết định |
| --- | --- | --- |
| Tăng từ 4 lên 8 worker, thời gian không giảm | Writer DB hoặc API đã chạm trần | Throughput stage, DB wait, API 429 theo cùng thời điểm |
| Worker có nhiều thời gian idle, queue vẫn dài | Executor dispatch/hàng đợi hoặc dependency có vấn đề | Active threads, task wait, trạng thái blocking thread |
| JDBC acquire timeout tăng | Connection pool nhỏ hoặc connection bị giữ lâu | Active/pending, thread dump, cursor/transaction age |
| DB session nhiều nhưng CPU thấp | Lock wait hoặc I/O wait | `pg_stat_activity`, lock graph, disk metrics |
| Heap tăng theo số partition | Chunk/buffer/queue giữ nhiều item | Heap histogram, GC, pending task/payload |
| JobRepository chậm khi có rất nhiều partition | Metadata contention, transaction update dày | Query latency/bảng `BATCH_*`, chunk commit rate |
| Retry làm CPU/DB tăng mà business throughput giảm | Retry amplification / thundering herd | Retry attempts, backoff, errors, effective item/s |
| Một partition kéo dài gấp nhiều lần | Skew do dữ liệu hoặc chi phí item khác nhau | Count/byte/CPU/duration theo partition |

## 14. Thử nghiệm mở rộng có kiểm soát

Một kế hoạch load test có ý nghĩa cần **giữ dataset và điều kiện nền có thể so sánh**:

1. **Đặt invariant nghiệp vụ:** cùng input phải tạo đủ output đúng, không trùng side effect; restart có thể tiếp tục an toàn.
2. **Chốt ngân sách:** giới hạn DB connections, API RPS, CPU quota, heap, thread pool, broker, nhu cầu các ứng dụng khác và headroom.
3. **Đo baseline một worker:** wall time, items hữu ích/s, CPU/item, DB sessions, lock wait, IOPS, p95 chunk latency.
4. **Tăng dần 2 → 4 → 5 worker/replica:** giữ cùng snapshot, ghi lại throughput end-to-end, queue, pool pending và sự cố.
5. **Kiểm tra đồng thời hai replica:** xác minh tổng DB sessions và API RPS không vượt ngân sách toàn cluster.
6. **Thử job overlap/rerun:** cho hai `JobExecution` xuất hiện khi chính sách cho phép, kiểm tra tổng concurrency và fair scheduling.
7. **Tạo lỗi có chủ đích:** DB timeout, 429, một worker crash, restart partition; đo retry amplification và recovery time.
8. **Theo dõi dữ liệu cuối:** count/checksum/khóa nghiệp vụ, mất hoặc trùng record; không chỉ nhìn `BatchStatus.COMPLETED`.
9. **Dừng tăng concurrency khi đã bão hòa:** nếu throughput tăng ít hoặc giảm trong khi wait/error tăng, xác định bottleneck rồi tối ưu.
10. **Đặt alert và runbook:** cảnh báo pending connection, API throttling, partition treo, CPU throttling, backlog và nguy cơ quá hạn SLA.

Không lấy kết quả benchmark trong môi trường DB trống để suy ra sẽ đúng trên production khi các dịch vụ khác cùng dùng bảng/index. Nếu cần thay đổi quota/tài nguyên thật, lập phép đo trước–sau có điều kiện so sánh rõ và kế hoạch rollback cấu hình.

### Các trạng thái vận hành cần phân biệt

- **Thiếu capacity:** lưu lượng yêu cầu vượt năng lực thực sự; cần giảm tải, queue hoặc tăng/tối ưu tài nguyên.
- **Thiếu pool cục bộ:** DB còn dư nhưng ứng dụng đặt pool quá thấp; có thể điều chỉnh pool sau khi kiểm tra giới hạn tổng.
- **Contention:** nhiều worker tranh chấp cùng khóa/hàng; có thể cần đổi thuật toán hoặc chia lại miền ghi.
- **Skew:** một số partition quá nặng, worker khác rảnh; cân bằng theo số item/chi phí.
- **Retry storm:** lỗi tăng khiến worker gửi thêm request, làm nguồn đích xấu hơn; cần giới hạn retry và backoff.
- **Oversubscription:** nhiều executor/job/replica cùng dùng resource mà không có coordinator; cần concurrency budget xuyên suốt.

## 15. Chọn kiến trúc theo tài nguyên thực tế

| Bằng chứng | Hướng kiến trúc | Điều kiện quan trọng |
| --- | --- | --- |
| Processor CPU-bound, DB còn dư, một node còn core | Song song hóa phần tính toán theo mô hình Batch hỗ trợ | Processor stateless/thread-safe, hiểu transaction boundary theo phiên bản |
| Hai nguồn dữ liệu độc lập, hai bước chậm khác nhau | Parallel steps qua `split` | Flow độc lập, step phụ thuộc chỉ chạy sau join, pool chung đủ |
| Tập dữ liệu lớn, phân chia đúng thành nhiều miền | Local partitioning | Reader `@StepScope`, ranh giới ổn định, DB có capacity |
| Node hiện tại hết CPU nhưng DB/API còn dư | Remote partitioning | Tăng compute trên nhiều node, vẫn giữ ngân sách DB/API toàn hệ thống |
| Reader đủ nhanh, xử lý/ghi có thể giao qua message | Remote chunking | Broker/backpressure, worker idempotent, không để manager thành nút thắt |
| Writer DB đạt trần IOPS/lock | Tối ưu writer/query hoặc mở rộng DB trước | Thêm thread không làm trần DB tăng |
| API có quota thấp hơn throughput yêu cầu | Cache/batch API/giảm số call hoặc đổi SLA | Rate limiter chung, retry có backoff, chi phí API được tính |
| Nhiều job tranh chấp cùng DB theo lịch | Admission control, queue, tránh overlap không cần thiết | Đồng bộ cả job và worker; không bỏ lỡ business window |

**Không mặc định mô hình phân tán sẽ nhanh hơn.** Nó đổi giới hạn CPU/RAM cục bộ thành nhu cầu phối hợp nhiều worker và tăng áp lực lên tài nguyên chung. Chỉ mở rộng khi có phần công việc độc lập và nguồn/đích thực sự đủ khả năng đáp ứng.

## 16. Bài tập tình huống

Một hệ thống có ba ứng dụng batch replica. DB cho phép tối đa 120 session, trong đó ứng dụng realtime và tác vụ vận hành cần giữ 60 session. Mỗi replica batch dùng 4 connection cố định ngoài worker, mỗi worker có thể cần đồng thời 2 connection. Nhóm muốn dành 20% phần connection còn lại sau khi trừ fixed làm dự phòng.

1. Tính ngân sách DB cho batch, số connection fixed và variable.
2. Ước lượng số worker tối đa **toàn cluster** theo ngân sách, rồi số worker đều nhau trên mỗi replica.
3. Nếu mỗi replica có hai `JobExecution` chạy đồng thời, mỗi job tạo 6 worker với executor riêng, cấu hình này có thể vượt ngân sách không?
4. Nếu CPU từng replica còn dư nhưng DB writer đã đạt trần, tăng số worker có thể giúp giảm thời gian không?
5. Nếu một worker chạy query lâu giữ connection, sau đó gọi API đang bị throttle, giải pháp ưu tiên nên ở đâu?

**Gợi ý lời giải:**

~~~text
C_batch    = 120 - 60 = 60
C_fixed    = 3 × 4 = 12
C_variable = 60 - 12 = 48

Headroom 20%:
C_workers_planned ≤ 48 × 0,8 = 38,4 connections

Tổng worker tối đa = floor(38,4 / 2) = 19 workers
Chia đều 3 replica = floor(19 / 3) = 6 workers / replica

Dự kiến 18 workers toàn cluster:
C_expected = 12 + 18 × 2 = 48, còn 12 session trong ngân sách 60.

Hai jobs × 6 workers × 3 replicas = 36 workers
C_needed = 12 + 36 × 2 = 84 > 60
→ Không phù hợp nếu thực sự đồng thời và cùng giữ 2 connection/worker.
~~~

Câu 4: cần cải thiện writer/DB, giảm contention hoặc thay cách ghi trước; CPU dư không thay đổi trần DB. Câu 5: nên giới hạn đồng thời/API RPS, giảm thời gian giữ connection trước lúc chờ API, tách giai đoạn thao tác theo transaction boundary phù hợp và đánh giá idempotency khi retry.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): các mô hình mở rộng, parallel steps và partitioning.
- [Spring Batch 5.2 – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): tham chiếu cấu hình `TaskExecutor` và partitioning với Batch 5.x.
- [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): vai trò của repository và transaction metadata.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): quan sát job/step và metric.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executor, thread pool và scheduling.
- [HikariCP README – Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): `maximumPoolSize` và các thông số pool.
- [PostgreSQL Documentation – Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, hoạt động database và thông tin chờ.

## Ghi nhớ

**Giới hạn tài nguyên dùng chung phải được tính trên tất cả worker, flow, JobExecution và replica cùng truy cập nguồn/đích.** Pool cục bộ không tạo thêm năng lực DB toàn hệ thống; tăng partition không làm lock, I/O hoặc API quota tự mở rộng. Trước khi scale Spring Batch, hãy lập ngân sách tài nguyên có headroom, đo concurrency thực và throughput nghiệp vụ, xác định bottleneck, đặt backpressure và kiểm thử retry/restart dưới tải đại diện. Kiến trúc phù hợp là kiến trúc tăng lượng công việc hoàn thành đúng hạn mà vẫn giữ kết quả đúng và tài nguyên vận hành ổn định.
