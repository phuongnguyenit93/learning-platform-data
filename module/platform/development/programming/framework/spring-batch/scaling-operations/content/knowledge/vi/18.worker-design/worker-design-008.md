# Worker concurrency và resource pool trong Spring Batch

## Mục tiêu bài học

Khi mở rộng Spring Batch, một phản xạ phổ biến là tăng số worker: từ 2 lên 8 thread, thêm JVM/pod, tăng số message consumer hoặc nâng `gridSize` của partition manager. Nhưng **số worker lớn hơn không đồng nghĩa với throughput lớn hơn**. Nếu các worker cùng chờ JDBC connection, tranh một dòng dữ liệu nóng hoặc vượt quota của HTTP API, việc tăng song song có thể làm chậm job và tạo thêm retry, rollback, lỗi dữ liệu.

Bài **“Worker concurrency và resource pool”** thuộc chương **Thiết kế worker** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán phù hợp; đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực tế.

Ở đây, **worker concurrency** là mức công việc thực đang tiến hành đồng thời; **resource pool** là cơ chế giới hạn và tái sử dụng JDBC/HTTP connection, thread, message consumer, session, buffer và tài nguyên đắt đỏ. Hai phần phải được thiết kế **cùng nhau**.

Sau bài này, bạn có thể:

- Phân biệt worker JVM, partition, StepExecution, chunk thread, broker consumer và request inflight.
- Đọc topology concurrency và xác định nơi có thể xếp hàng/chờ tài nguyên.
- Tính trần JDBC connections **toàn cluster**, kể cả manager và headroom.
- Cấu hình giới hạn local partition executor, worker listener và resource pool.
- Đánh giá chunk size, prefetch, queue capacity, API rate limit và backpressure.
- Kiểm tra thread safety của reader/processor/writer và SDK được nhiều worker chia sẻ.
- Phân tích retry storm, duplicate delivery, shutdown, restart và idempotency.
- Thực hiện benchmark có kiểm soát và chọn concurrency dựa trên SLA, throughput **hữu ích** cùng tính đúng dữ liệu.

## 1. “Worker” không phải lúc nào cũng là một thread

Một hệ thống Batch phân tán có nhiều cấp thực thi:

| Đơn vị | Vai trò | Điều dễ nhầm |
| --- | --- | --- |
| **Worker JVM/pod** | Một process chạy ứng dụng worker | Một JVM có thể nhận nhiều phần việc đồng thời |
| **Consumer** | Nhận message từ broker | Prefetch có thể giữ nhiều message nhưng không xử lý đồng thời |
| **Handler invocation** | Một lượt xử lý chunk/request | Có thể đồng bộ hoặc dispatch tiếp qua executor |
| **Worker StepExecution** | Một partition chạy worker step | Có thể gồm một hoặc nhiều chunk threads |
| **Chunk thread** | Thread thực thi chunk trong StepExecution | Khác thread điều phối partition |
| **Partition** | Phạm vi input do Partitioner tạo | Chưa chắc đang chạy; có thể đợi executor |
| **Inflight request** | Đã gửi nhưng chưa nhận kết quả cuối | Có thể nằm trong broker hoặc chờ DB |
| **JDBC/HTTP connection** | Handle truy cập downstream | Không có quan hệ 1:1 cố định với worker |

Ví dụ cluster **4 worker JVM**, mỗi JVM có **3 consumer threads**: có thể có khoảng 12 request handlers đồng thời nếu mỗi consumer chạy handler đồng bộ và không có giới hạn khác. Nếu handler lại tạo bốn tác vụ async, công việc nội bộ có thể cao hơn 12. Nếu DB chỉ cấp sáu connections, không có nghĩa 12 request cùng commit một lúc.

**Nguyên tắc:** không dùng một thuộc tính `concurrency` để suy luận độ song song của toàn pipeline.

## 2. Bản đồ các hàng đợi và resource pool

~~~mermaid
flowchart LR
    M["Manager / PartitionHandler"] --> Q[["Request broker"]]
    Q --> C["Consumer concurrency"]
    C --> E["Worker handler/executor"]
    E --> CPU["CPU quota"]
    E --> DBP["JDBC connection pool"]
    E --> HTTP["HTTP client pool"]
    E --> MEM["Heap / chunk buffers"]
    DBP --> DB[("Source/target DB")]
    HTTP --> API[["External API"]]
    E -. "reply" .-> Q
~~~

Một chunk có thể lần lượt chờ tại:

1. Manager: đã được đọc/tạo nhưng còn đợi quyền phát request.
2. Broker: queue/topic đã nhận nhưng chưa được consumer lấy.
3. Consumer: đã prefetched/unacked nhưng handler chưa chạy.
4. Executor: task đang đợi trong worker queue.
5. Connection pool: handler chờ JDBC hoặc HTTP connection.
6. Database: đã có connection nhưng SQL chờ I/O hoặc lock.
7. Reply path: worker đã xử lý nhưng kết quả chưa về manager.

Tăng consumer có thể làm broker backlog giảm nhưng khiến **executor queue hoặc JDBC pending** tăng. Như vậy ta chỉ chuyển điểm chờ từ tầng này sang tầng khác, chưa chắc tăng số item hoàn tất.

### Một phép chẩn đoán

Giả sử 40 requests inflight:

~~~text
18 đang trong broker/consumer buffer
10 đang xếp hàng trong executor
 8 đang chờ connection
 4 đang thực sự truy vấn DB
~~~

Các con số minh họa. 40 inflight **không có nghĩa 40 request đang dùng CPU hoặc commit DB**. Trước khi tăng worker, hãy biết chúng đang chờ ở đâu.

## 3. Concurrency, parallelism và inflight

- **Concurrency:** số phần việc cùng tiến hành về mặt logic, kể cả khi đang đợi I/O.
- **Parallelism:** số phần thực sự chạy cùng lúc trên tài nguyên tính toán.
- **Inflight:** request đã phát nhưng chưa có outcome cuối theo protocol.
- **Capacity:** lượng công việc hữu ích mà hệ thống có thể hoàn tất trên đơn vị thời gian.
- **Saturation:** khi thêm tải làm tăng wait/latency nhưng throughput hữu ích tăng rất ít hoặc giảm.

Ví dụ một process có 8 threads nhưng chỉ có 2 vCPU. Có thể có tám handler đang chạy, nhưng tối đa khoảng hai luồng CPU-bound có thể thực sự dùng CPU ở một thời điểm trên quota đó. Nếu I/O-bound, concurrency lớn hơn CPU cores có thể hữu ích, với điều kiện downstream còn năng lực.

Hãy luôn nêu rõ **đơn vị đo**: item/s, chunk/s, partition/s, request/s hay transaction/s. Một chunk có thể chứa 100 hoặc 1.000 item; không so chunk/s với item/s một cách trực tiếp.

## 4. Lập ngân sách tài nguyên trước khi tăng worker

| Tài nguyên | Giới hạn cần xem | Hậu quả khi vượt |
| --- | --- | --- |
| CPU / vCPU quota | Cores và CPU throttling | Context switch, latency/CPU saturation |
| JVM heap | `-Xmx`, memory limit pod, GC | OutOfMemoryError, GC pause |
| JDBC pool | Max connection, acquire timeout | Handler pending, timeout |
| DB server | Connection cap, CPU, IOPS, locks, WAL | Chậm query, deadlock, rollback |
| HTTP pool | Connection per host/route, acquire timeout | Client pending, network timeout |
| API quota | QPS, concurrent requests, token bucket | HTTP 429, retry storm |
| Broker | Consumer, prefetch, unacked, lag, channel | Backlog, redelivery, memory |
| Executor | Core/max threads, queue capacity | Rejection, queue quá dài |
| File descriptor | Open files/sockets | Không tạo được handle |
| JobRepository | Metadata DB latency và connection | Chậm checkpoint/partition dispatch |
| SDK ngoài | Session/object pool và concurrency contract | Race, lock nội bộ, state leak |

Không chọn pool size với mục tiêu “sử dụng hết” tài nguyên. Pool là giới hạn/cơ chế tái sử dụng; mức tối ưu phụ thuộc **thời gian giữ tài nguyên** và năng lực downstream.

## 5. Đo baseline để phân biệt nút thắt

Trước khi tune, hãy chạy một workload đại diện với **1–2 worker** và snapshot dữ liệu ổn định. Đo từng giai đoạn:

| Metric | Mục đích |
| --- | --- |
| Read/processor/write throughput | Định vị công đoạn chậm |
| CPU, GC, allocation | Phát hiện CPU/memory bottleneck |
| JDBC active/idle/pending/acquire wait | Phát hiện pool congestion |
| SQL p95, rows scanned, DB I/O/lock | Phân biệt pool nhỏ với DB quá tải |
| HTTP p95, pool pending, 429/5xx | Phát hiện API saturation |
| Broker queue age/unacked/redelivery | Phát hiện worker chưa bắt kịp |
| Chunk latency, commit/rollback | Theo dõi transaction và lỗi |
| Business reconciliation | Kiểm tra đúng dữ liệu sau song song hóa |

Công thức cận trên đơn giản với pipeline một input tạo một output:

\[
R_{\mathrm{job}}
\le \min(R_{\mathrm{read}},R_{\mathrm{process}},
         R_{\mathrm{write}},R_{\mathrm{transport}})
\]

Nếu processor filter hoặc sinh nhiều output, cần quy đổi các throughput về cùng đơn vị. Khi reader của manager chỉ cung cấp được 5.000 item/s, thêm 20 worker có thể không giúp vượt cận đó.

**Đừng suy luận “CPU worker thấp → tăng threads”**. CPU thấp cũng có thể do đang chờ connection, lock hoặc API quota.

## 6. Sizing CPU-bound và I/O-bound

**CPU-bound** gồm parse phức tạp, mã hóa, chuẩn hóa tính toán, nén, transform lớn trong RAM. Tăng số runnable threads quá nhiều trên một máy CPU-bound thường tạo context switching và GC hơn là tăng công việc hữu ích.

**I/O-bound** gồm JDBC, HTTP API, object storage, filesystem, broker. Một số thread khác có thể chạy khi một thread chờ, nhưng chỉ khi DB/API còn năng lực.

Một heuristic ban đầu:

\[
N_{\mathrm{threads}}
\approx N_{\mathrm{CPU}}
\left(1+\frac{W}{C}\right)
\]

Trong đó `W` là thời gian chờ, `C` là thời gian CPU. Với 4 vCPU, một item dùng 10 ms CPU và 30 ms đợi I/O, heuristic cho `4(1+30/10)=16` threads.

**Đây không phải mức concurrency nên áp dụng ngay.** Nếu DB chỉ xử lý hữu ích tối đa 8 query đồng thời, 16 handler có thể khiến pool wait tăng. Hãy thử 4 → 8 → 12 → 16 trong cùng điều kiện và chọn điểm throughput hữu ích/chi phí tốt nhất.

### Lưu ý với virtual threads

Virtual threads có thể giảm chi phí thread chờ I/O trong kiến trúc Java hỗ trợ, nhưng **không tạo thêm DB connection, CPU cores hay API quota**. Việc dùng chúng với Spring Batch/Integration và các SDK cụ thể cần kiểm thử context, blocking/pinning, transaction/thread-local lifecycle và giới hạn downstream. Không thay đổi thread model chỉ để né việc phải sizing pool.

## 7. Tính ngân sách JDBC connection cho toàn cluster

Nếu có `P` worker JVM, mỗi JVM có HikariCP `maximumPoolSize=C`, trần cấu hình phía worker là:

\[
C_{\mathrm{workers,max}}=P\times C
\]

Đó **không phải số connections luôn đang mở**, mà là mức có thể xảy ra khi tải cao. Tổng còn có pool của manager, JobRepository và các ứng dụng khác.

Ví dụ PostgreSQL cho phép **160 kết nối**, cần dành 35 cho thành phần khác và headroom:

\[
C_{\mathrm{batch,budget}}=160-35=125
\]

Với tám worker JVM, mỗi JVM max 12 connections:

\[
C_{\mathrm{workers,max}}=8\times12=96
\]

Còn ngân sách tối đa 29 cho manager/metadata và các pool batch khác trong giả định. Nếu auto-scale lên 12 JVM vẫn giữ pool 12:

\[
C_{\mathrm{workers,max}}=12\times12=144
\]

Chỉ worker đã vượt ngân sách 125.

### Công thức tổng quát

\[
\sum_{\mathrm{pools\ to\ DB}} C_{\mathrm{pool,max}}
+C_{\mathrm{other}}
+C_{\mathrm{reserve}}
\le C_{\mathrm{DB,allowed}}
\]

Cộng theo **pool thực**, không tính đôi pool khi JobRepository và writer dùng cùng DataSource. Nếu có nhiều DataSource kết nối đến một DB, phải tính tất cả.

### Quan hệ với worker concurrency

Không có quy tắc `pool size = thread count` đúng mọi trường hợp:

- Một chunk có thể dùng connection theo transaction.
- Reader cursor có thể giữ connection riêng trong thời gian dài.
- JobRepository có thể cần connection trong lúc cập nhật metadata.
- Handler có thể chờ HTTP trước khi giải phóng DB connection.
- Một số worker chỉ xử lý CPU và không cần connection suốt thời gian chạy.

**Hãy đo số connection active/pending và thời gian giữ**, rồi chọn pool theo workload thay vì suy ra từ số consumer.

## 8. Ví dụ Spring Boot: giới hạn HikariCP

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/batch
    username: DB_USER_FROM_SECRET
    password: DB_PASSWORD_FROM_SECRET
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 10000
      max-lifetime: 1800000
~~~

Đây là **cấu hình minh họa**, không phải giá trị tối ưu chung. Tên chứa `FROM_SECRET` là placeholder để diễn đạt việc cấp qua hệ thống secret, không được đưa secret thật vào repository.

- `maximum-pool-size`: trần connections trong pool.
- `minimum-idle`: mục tiêu idle connections theo điều kiện của pool.
- `connection-timeout`: thời gian tối đa chờ mượn connection trước khi lỗi.
- `max-lifetime`: vòng đời tối đa dự kiến của connection; cần phối hợp với giới hạn hạ tầng.

### Các câu hỏi trước khi tăng pool

1. DB đang dư CPU/I/O hay đã bão hòa?
2. Query plan và index có phù hợp các partition range không?
3. Có slow transaction hoặc lock wait kéo dài không?
4. Có reader giữ cursor lâu và không trả connection không?
5. Có connection leak sau exception/retry không?
6. Có process khác cũng dùng DB mà không có ngân sách riêng không?
7. Khi auto-scale thêm replica, tổng `maximum-pool-size` trở thành bao nhiêu?

Nếu DB đã bão hòa, tăng pool có thể làm truy vấn chậm hơn. Cần tối ưu SQL, chunk transaction, hot rows và concurrency trước.

## 9. Reader/writer ảnh hưởng thời gian giữ connection

| Thành phần | Đặc điểm cần xem |
| --- | --- |
| `JdbcCursorItemReader` | Có thể giữ cursor/connection qua nhiều chunk; phải đo theo driver và transaction |
| `JdbcPagingItemReader` | Query theo page; cần sort key duy nhất và dữ liệu ổn định để restart |
| `JdbcBatchItemWriter` | Ghi batch theo transaction; quan tâm commit, lock và batch size |
| Spring Batch `JobRepository` | Lưu execution/checkpoint; có thể tranh DB/pool |
| JPA/Hibernate | Session/persistence context mutable thường không chia sẻ giữa thread |
| SDK tự viết | Có thể giữ connection trong singleton field ngoài lifecycle đúng |

Một `JdbcCursorItemReader` mở cursor trong hàng chục phút có thể giữ một tài nguyên DB trong suốt StepExecution, ngay cả khi worker đang xử lý CPU. Khi tăng partition count, số cursor kết nối có thể tăng tương ứng.

### Anti-pattern: giữ transaction khi chờ HTTP

~~~text
BEGIN DB transaction
  → cập nhật một số rows
  → gọi HTTP API chờ 20 giây
  → cập nhật tiếp
COMMIT
~~~

Nếu transaction/lock bị giữ suốt HTTP wait, pool nhanh cạn khi nhiều worker. Nên thiết kế ranh giới transaction ngắn hơn khi nghiệp vụ cho phép, hoặc dùng outbox/idempotency để tách side effect khỏi transaction nội bộ một cách có thể phục hồi.

Không đơn giản chuyển API call ra ngoài transaction rồi bỏ qua rủi ro duplicate: hai hệ thống vẫn không cùng một atomic commit.

## 10. Scope và thread safety khi nhiều worker cùng chạy

Một Spring singleton là **một bean trên mỗi ApplicationContext**, không phải thread-safe theo mặc định. Cùng JVM, nhiều partition/chunk requests có thể truy cập chung singleton processor, writer hoặc SDK.

**`@StepScope` gắn với StepExecution, không gắn với chunk thread.** Đây là khác biệt quan trọng giữa mô hình:

| Mô hình | Đơn vị concurrency | Rủi ro chia sẻ state |
| --- | --- | --- |
| Multi-threaded step | Nhiều chunk threads trong một StepExecution | Reader/processor/writer `@StepScope` có thể cùng target |
| Parallel steps | Các StepExecution của flow khác nhau | Singleton SDK/service vẫn chung JVM |
| Local partitioning | Nhiều worker StepExecution cùng JVM | Scoped reader tách partition; DataSource và singleton vẫn chung |
| Remote partitioning | Nhiều worker StepExecution ở một/nhiều JVM | Singleton trong từng JVM, DB chung toàn cluster |
| Remote chunking | Nhiều chunk messages/handlers | Cùng processor/writer singleton ở worker JVM nếu cấu hình như vậy |

### Ví dụ lỗi thường gặp

~~~java
@Service
public class UnsafeEncoder {
    private final StringBuilder shared = new StringBuilder();

    public String encode(long id, String value) {
        shared.setLength(0);
        shared.append(id).append('|').append(value);
        return shared.toString();
    }
}
~~~

Nhiều thread dùng chung `shared` có thể làm output lẫn nhau. Tăng JDBC pool hoặc gắn `@StepScope` lên processor sử dụng singleton `UnsafeEncoder` **không tự sửa race**.

Thay bằng xử lý stateless, instance riêng theo phạm vi concurrency thật, hoặc adapter đồng bộ/pool đối tượng được thiết kế đúng. Đồng bộ hóa có thể tạo bottleneck, nên phải đo throughput sau khi sửa.

## 11. Local partitioning: concurrency giữa các StepExecution

Local partitioning có manager chia input thành nhiều partition rồi giao worker StepExecutions qua TaskExecutor cùng JVM.

~~~mermaid
flowchart TB
    M["Partition manager"] --> A["StepExecution A"]
    M --> B["StepExecution B"]
    M --> C["StepExecution C"]
    A --> R1["Reader @StepScope A"]
    B --> R2["Reader @StepScope B"]
    C --> R3["Reader @StepScope C"]
    R1 --> P["DataSource pool dùng chung"]
    R2 --> P
    R3 --> P
    P --> DB[("DB chung")]
~~~

Nếu mỗi worker step xử lý chunk tuần tự, mỗi reader stateful có phạm vi StepExecution rõ. Nhưng tất cả vẫn tranh connection pool và DB.

**Grid size không phải số thread.** Một Partitioner có thể tạo 20 partitions, executor chỉ cho 4 chạy đồng thời; các partition còn lại chờ. Một partition có thể có 1 hoặc nhiều chunk threads nếu worker step bật multi-threading nội bộ.

Nếu worker step đã stateful, thường nên tăng concurrency ở cấp **partition độc lập** trước khi đồng thời bật đa luồng bên trong mỗi partition. Điều này giúp dễ chứng minh checkpoint và dữ liệu không chồng lấn.

## 12. Java: TaskExecutor có giới hạn cho local partitioning

Ví dụ Spring Batch 5.x, Java 17. Giả định đã có `ordersPartitioner`, `ordersWorkerStep` và `JobRepository` cấu hình đúng.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class LocalPartitionWorkerConfig {

    @Bean
    public ThreadPoolTaskExecutor partitionExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(12);
        executor.setThreadNamePrefix("partition-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        executor.initialize();
        return executor;
    }

    @Bean
    public Step ordersManagerStep(
            JobRepository jobRepository,
            @Qualifier("ordersPartitioner")
                    Partitioner partitioner,
            @Qualifier("ordersWorkerStep")
                    Step workerStep,
            @Qualifier("partitionExecutor")
                    TaskExecutor executor) {

        return new StepBuilder("ordersManagerStep", jobRepository)
                .partitioner("ordersWorkerStep", partitioner)
                .step(workerStep)
                .gridSize(12)
                .taskExecutor(executor)
                .build();
    }
}
~~~

### Giải thích đúng giới hạn

- Executor có **tối đa 4 threads chạy tasks do bean này quản lý**.
- Queue capacity 12 là số tác vụ có thể đợi trong executor queue theo cấu hình, **không phải 12 tasks đang chạy**.
- `gridSize(12)` là tham số đi vào Partitioner/handler, không bắt buộc tạo đúng 12 partitions.
- `awaitTerminationSeconds(60)` là thời gian chờ khi shutdown, không phải cam kết worker hoàn tất mọi transaction trong 60 giây.
- Nếu Partitioner sinh nhiều task hơn giới hạn queue/executor và handler phát quá nhanh, có thể xảy ra task rejection; cần test và backpressure rõ.

**Chưa phải chương trình độc lập:** phải định nghĩa Worker Step, Partitioner, Job và hạ tầng. Code minh họa kiến trúc, không tuyên bố đã chạy build.

### Hai cấp concurrency có thể nhân nhu cầu resource

Nếu 4 partitions chạy cùng lúc mà mỗi worker StepExecution lại bật 8 chunk threads, số chunk threads tiềm năng có thể rất lớn so với dự tính. Không được coi đó là `gridSize=4` và cấp DB pool size 4 là chắc chắn đủ.

## 13. Remote partitioning: số partition khác số worker process

Trong remote partitioning, manager tạo `StepExecution` và `ExecutionContext`, gửi yêu cầu thực thi qua middleware; worker truy xuất metadata và tự đọc input theo partition.

~~~mermaid
flowchart LR
    M["Manager + Partitioner"] --> Q[["Request broker"]]
    Q --> A["Worker JVM A: 2 StepExecutions"]
    Q --> B["Worker JVM B: 2 StepExecutions"]
    Q --> C["Worker JVM C: 2 StepExecutions"]
    A --> DB[("Nguồn/đích DB")]
    B --> DB
    C --> DB
    J[("JobRepository")] --- M
    J --- A
    J --- B
    J --- C
~~~

Nếu manager tạo 80 partition, ba JVM mỗi JVM xử lý hai StepExecutions đồng thời, khoảng **6 partition** có thể hoạt động ở một thời điểm, tùy listener, handler, executor và các phần việc khác.

**Cần phân biệt:**

1. Tổng số partition được định danh.
2. Số request broker đang giữ.
3. Số worker StepExecutions đồng thời mỗi JVM.
4. Số chunk threads bên trong StepExecution (nếu có).
5. Resource pool trong từng JVM và DB chung.

### Điều kiện restart

Partition name và ExecutionContext phải ổn định trong cùng công việc logic; không tạo ID/range ngẫu nhiên mỗi lần restart. Khi manager timeout, worker cũ **có thể vẫn đang chạy**: không tự gửi cùng StepExecution cho worker khác nếu chưa reconcile trạng thái và có ownership policy phù hợp.

## 14. Remote chunking: consumer concurrency và inflight chunks

Remote chunking khác remote partitioning: **manager đọc và chia chunk**, worker nhận chunk từ broker để process/write rồi phản hồi.

~~~mermaid
flowchart LR
    M["Manager reader/chunk"] --> B[["Request broker"]]
    B --> C["Consumer threads"]
    C --> H["Worker handler"]
    H --> DB[("DB/API")]
    H --> REP[["Reply broker"]]
    REP --> M
~~~

Một worker JVM có thể nhận nhiều chunk đồng thời. Điều này tạo các giới hạn riêng:

- Số consumer có thể lớn hơn số request đang thực sự xử lý.
- Prefetch có thể giữ nhiều request *unacked*.
- Handler có thể dispatch async qua một executor khác.
- Nhiều chunk có thể gọi cùng singleton writer/SDK.
- Reply có thể về đảo thứ tự; correlation phải ghép đúng request.
- Redelivery có thể gọi lại cùng business operation sau commit.

**Không giả định một remote chunk tương ứng với một worker StepExecution độc lập**, và không dùng `@StepScope` như giải pháp mặc định cho mọi concurrency trong remote chunking.

Nếu manager reader chỉ cung cấp được 4.000 item/s, tăng worker vượt năng lực đó sẽ không tự làm pipeline nhanh hơn.

## 15. RabbitMQ: consumer count, prefetch và ACK

Với RabbitMQ/AMQP:

- **Consumer concurrency** quyết định số consumer/listener có thể nhận message đồng thời.
- **Prefetch** là giới hạn cấp phát message trước khi consumer xác nhận theo phạm vi broker/adapter tương ứng.
- **ACK/NACK** liên quan đến trạng thái giao nhận, **không mặc nhiên atomic** với DB commit.
- **Requeue/redelivery** có thể tạo duplicate work.
- **Request–reply correlation** phải giữ đúng khi worker hoàn thành đảo thứ tự.

Một factory Spring AMQP minh họa:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.context.annotation.Bean;

@Bean
public SimpleRabbitListenerContainerFactory workerListenerFactory(
        ConnectionFactory connectionFactory) {

    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrentConsumers(4);
    factory.setMaxConcurrentConsumers(4);
    factory.setPrefetchCount(2);
    factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
    return factory;
}
~~~

**Đây chỉ là factory cho Spring AMQP listener.** Nếu ứng dụng sử dụng Spring Integration AMQP inbound gateway/adapter, phải nối factory/container theo đúng phiên bản của adapter đang chạy; đoạn mã không tự tạo remote chunking worker flow.

Với bốn consumers, prefetch hai message mỗi consumer, có thể có nhiều message đã giao nhưng chưa ACK hơn số handler đang chạy. Phải kiểm tra scope prefetch thực tế, message size và container policy.

### Những điều cần test

1. ACK xảy ra khi nào trong cấu hình listener/transaction cụ thể?
2. Nếu worker commit rồi chết trước ACK/reply, broker có redeliver không?
3. Nếu prefetch cao và worker bị kill, có bao nhiêu request phải được giao lại?
4. Nếu lỗi schema không retry được, message đi DLQ hay nóng vòng requeue?
5. Nếu worker gọi async handler rồi return, ACK có bị gửi trước business completion không?

**Prefetch không phải số thread**, và ACK broker không chứng minh business side effect đã ghi đúng một lần.

## 16. Kafka: topic partitions giới hạn consumer parallelism

Với Kafka, consumer concurrency trong một consumer group chỉ có ích khi có đủ **topic partitions** để gán. Nếu request topic chỉ có bốn partition, tăng concurrency của group lên 16 không làm 16 consumer cùng được assign một partition riêng.

Ví dụ cấu hình Spring Boot mang tính minh họa:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 4
    consumer:
      enable-auto-commit: false
      max-poll-records: 100
~~~

Cần xác nhận listener container factory, ack mode và adapter thực tế. `enable-auto-commit: false` **chưa định nghĩa thời điểm offset được commit** hay việc worker DB commit có đồng bộ với offset hay không.

### Thứ tự trong Kafka

Kafka bảo đảm thứ tự log trong một partition, **không bảo đảm thứ tự commit DB giữa các tác vụ async**. Nếu nghiệp vụ cần sequence theo key, phải kiểm tra key routing, consumer execution và sequence guard ở dữ liệu đích.

Retry topic có thể làm message sau vượt message đang retry. Nếu chỉ quan sát lag giảm mà business output sai thứ tự, không thể coi thiết kế đã đạt.

### Tài nguyên Kafka

Đo partition assignments, consumer lag, rebalance count, poll/handler latency, offset commit failure, heap và throughput hữu ích. Nếu một worker chậm làm lag tăng, tăng số consumers chỉ giúp khi topic có đủ partitions và downstream còn năng lực.

## 17. HTTP pool khác API rate limit

Một HTTP client thường có cơ chế reuse connections hoặc giới hạn concurrency per host. Nhưng **số HTTP connections không phải số requests/s được API cho phép**.

Ví dụ API chỉ cho **50 requests/s trên toàn tài khoản**, trong khi 10 worker JVM mỗi JVM có 8 handlers. Dù mỗi JVM có HTTP pool 20 connections, tổng cluster vẫn phải điều tiết về quota chung.

| Điều kiện | Cần kiểm tra |
| --- | --- |
| Connection pool | Tổng/per-host connection, acquire timeout |
| Network | Connect timeout, read timeout, keep-alive |
| API quota | QPS, burst size, concurrency, Retry-After |
| Retry | SDK retry + handler retry + broker redelivery |
| Security | Token refresh và credential lifecycle khi concurrent |
| Correctness | Idempotency key nếu API có side effect |

**Không giữ DB transaction/connection trong lúc chờ API lâu** nếu có thể thiết kế khác mà vẫn bảo đảm phục hồi. Với API bên ngoài DB transaction, cần idempotency, outbox hoặc reconciliation.

Một client thread-safe cũng không có nghĩa mutable request builder/session do client trả về được dùng đồng thời an toàn.

## 18. Semaphore giới hạn downstream trong một worker JVM

Nếu một dịch vụ enrichment đắt đỏ chỉ cho tối đa bốn lời gọi đồng thời **trong một JVM**, có thể dùng `Semaphore` làm bulkhead.

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class LimitedEnrichmentGateway {

    private final Semaphore permits = new Semaphore(4);
    private final ExternalEnrichmentClient client;

    public LimitedEnrichmentGateway(
            ExternalEnrichmentClient client) {
        this.client = client;
    }

    public EnrichedResult enrich(String businessId) {
        final boolean acquired;
        try {
            acquired = permits.tryAcquire(
                    2, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while waiting for permit", ex);
        }

        if (!acquired) {
            throw new DownstreamCapacityException(
                    "Enrichment capacity exhausted");
        }

        try {
            return client.enrich(businessId);
        } finally {
            permits.release();
        }
    }
}
~~~

`ExternalEnrichmentClient`, `EnrichedResult` và `DownstreamCapacityException` là kiểu minh họa của ứng dụng, cần tự định nghĩa. Đoạn mã bảo vệ đường gọi qua gateway này; nếu caller đi đường khác, giới hạn không áp dụng.

**Hạn chế:**

- Mười JVM có mười semaphore riêng: tối đa khoảng **40 lời gọi đồng thời** qua các gateway, không phải bốn toàn cluster.
- Concurrency không đồng nghĩa QPS.
- Timeout đợi permit cần được phân loại retryable hoặc backpressure theo nghiệp vụ.
- Semaphore không tự tạo transaction, idempotency hay ordering.
- Không nên giữ JDBC connection trong lúc chờ permit nếu tránh được.

## 19. Backpressure: giới hạn inflight thay vì queue vô hạn

**Backpressure** làm manager/broker/worker không cấp việc nhanh hơn năng lực downstream có thể hoàn tất.

~~~mermaid
flowchart TD
    M["Manager tạo chunk"] --> D{"Inflight trong giới hạn?"}
    D -->|Có| Q[["Broker request queue"]]
    D -->|Không| STOP["Giảm / tạm dừng cấp việc"]
    Q --> W["Worker executor"]
    W --> DB[("DB/API")]
    W -. "Reply/outcome" .-> M
~~~

Các giới hạn liên quan:

1. **Manager outstanding requests**: số chunk chưa có outcome cuối.
2. **Broker prefetch/unacked**: message đã cấp cho consumer nhưng chưa xác nhận.
3. **Worker executor threads + queue**: tác vụ chạy và chờ.
4. **JDBC/HTTP pools**: concurrent resource operations.
5. **External service quota**: tốc độ được phép trên toàn cluster.

Một queue rất lớn có thể khiến producer gửi nhanh, nhưng kéo dài *oldest message age* và thời gian phục hồi khi worker chết. Hãy ưu tiên **bounded queues, deadlines và metric rõ**.

### Task rejection

Khi executor đầy, cần có chính sách rõ: dừng phát, reject để middleware retry có backoff, hoặc fail công việc với trạng thái có thể phục hồi.

**Không mặc định dùng `CallerRunsPolicy` trong mọi listener**. Nó có thể tạo backpressure nhưng cũng có thể chặn broker callback thread, làm ảnh hưởng ACK, heartbeats và timeout. Phải kiểm thử với adapter cụ thể.

## 20. Little's Law để đối chiếu inflight và latency

Trong hệ thống ổn định và khi các đại lượng đo trên cùng phạm vi, **Little's Law**:

\[
L=\lambda W
\]

Trong đó:

- `L`: số request/chunk trung bình trong hệ thống được đo.
- `\lambda`: tốc độ hoàn tất trung bình.
- `W`: thời gian request/chunk ở trong hệ thống.

Ví dụ 80 chunks/s và mỗi chunk mất trung bình 0,25 giây từ lúc nhận tới lúc hoàn thành:

\[
L=80\times0,25=20\ \mathrm{chunks}
\]

Đó là mức inflight **trung bình**, không phải mệnh lệnh tạo 20 threads. Chunks có thể đợi queue/I/O hoặc có quy mô khác nhau.

### Những trường hợp khó áp dụng trực tiếp

- Backlog liên tục tăng, chưa ở trạng thái ổn định.
- Tốc độ arrival khác completion trong cửa sổ đo.
- Retry/duplicate làm số transport messages khác số logical chunks.
- `W` đo từ manager send nhưng `L` chỉ đếm queue consumer.
- Chunk size thay đổi mạnh theo phân bố dữ liệu.

Dùng công thức để kiểm tra tính hợp lý của metric; quyết định concurrency vẫn phải dựa trên benchmark và saturation của tài nguyên thật.

## 21. Chunk size, prefetch và memory footprint

Kích thước chunk lớn có thể giảm số transaction và request/reply, nhưng làm tăng số item nằm trong bộ nhớ mỗi worker.

Ước lượng sơ bộ phần payload:

\[
M_{\mathrm{payload}}
\approx N_{\mathrm{resident\ chunks}}
\times C_{\mathrm{chunk}}
\times S_{\mathrm{item}}
\]

Với tám chunks đang giữ, 500 item/chunk, mỗi item chiếm khoảng 2 KiB sau deserialize:

\[
M_{\mathrm{payload}}
\approx 8\times500\times2\ \mathrm{KiB}
=7{,}8125\ \mathrm{MiB}
\]

Đây **chỉ là payload ước lượng**, không bao gồm object overhead, serializer buffers, writer batch arrays, threads, metaspace, JVM GC và các bản sao ở manager/broker.

### Cân nhắc chunk size

| Chunk nhỏ | Chunk lớn |
| --- | --- |
| Ít item cần rollback khi lỗi | Ít commit/message overhead hơn |
| Payload nhỏ và dễ retry | Có thể tăng throughput khi writer batch hiệu quả |
| Tăng số message, reply, metadata | Tăng payload/buffer và thời gian giữ transaction |
| Có thể giảm latency mỗi chunk | Tăng chi phí replay sau timeout/crash |
| Có thể kém tận dụng JDBC batching | Có nguy cơ vượt message size limit |

**Không tune chunk size, concurrency, prefetch và pool size cùng lúc.** Thay một biến lớn mỗi vòng giúp biết yếu tố nào tạo ra cải thiện hoặc regression.

## 22. Retry amplification và pool exhaustion

Một workload đang lỗi có thể bị thử lại ở nhiều tầng:

| Tầng | Ví dụ | Tác động |
| --- | --- | --- |
| Producer retry | Publish confirm timeout | Có thể tạo duplicate request |
| Broker redelivery | Worker chết trước ACK | Toàn request được xử lý lại |
| Integration handler retry | DB timeout | Gọi handler nhiều lần |
| Batch item/chunk retry | Fault-tolerant step | Processor/writer được gọi lại |
| Manager request timeout | Reply mất hoặc trễ | Có thể yêu cầu reconciliation/retry |
| Job restart | StepExecution thất bại | Đọc lại phần chưa hoàn tất |

Nếu DB thiếu connection, nhiều consumer đồng thời retry tức thì có thể gây **retry storm** và tăng tải lên DB đang lỗi. Cần:

- Max attempts hữu hạn.
- Exponential backoff có jitter.
- Retry deadline/budget xuyên tầng.
- Phân loại lỗi tạm thời và lỗi dữ liệu cố định.
- DLQ/quarantine cho poison message.
- Giảm consumer concurrency hoặc pause khi downstream outage.
- Idempotency cho side effect khi message/chunk chạy lại.

### Cửa sổ lỗi quan trọng

~~~text
T0  Broker giao chunk 42
T1  Worker ghi DB thành công
T2  DB commit
T3  Reply mất / worker chết trước ACK
T4  Chunk 42 được xem xét lại hoặc redeliver
T5  Writer phải tránh nhân đôi business effect
~~~

**Timeout manager không chứng minh worker đã dừng.** Với remote partitioning, không tự giao cùng StepExecution sang worker khác khi chưa reconcile trạng thái worker cũ.

## 23. Idempotency và writer concurrency

Khi nhiều worker có thể nhận lại cùng work, correlation ID của message **không phải** idempotency key bền vững xuyên mọi restart.

### Snapshot upsert theo version

~~~sql
INSERT INTO order_projection
    (order_id, source_version, normalized_state)
VALUES (:orderId, :sourceVersion, :normalizedState)
ON CONFLICT (order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    normalized_state = EXCLUDED.normalized_state
WHERE order_projection.source_version
      < EXCLUDED.source_version;
~~~

Mẫu PostgreSQL này phù hợp khi event mang **snapshot đầy đủ** và phiên bản tăng theo nghiệp vụ. Nếu cùng version nhưng payload khác, cần phát hiện conflict. Không sử dụng last-version-wins để bỏ các event delta bắt buộc.

### Event ledger cho thao tác cộng dồn

~~~sql
CREATE TABLE applied_event (
    event_id UUID PRIMARY KEY,
    account_id BIGINT NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong **cùng transaction DB**:

1. Cố ghi event ID theo unique constraint.
2. Nếu duplicate, đối chiếu hash/payload và không áp dụng delta lần nữa.
3. Nếu mới, cập nhật business state một lần.
4. Commit ledger và business update cùng nhau; rollback cả hai khi lỗi.

Một truy vấn `SELECT` rồi `INSERT` không có uniqueness/locking có thể race khi hai worker cùng xử lý một event. Với API ngoài DB, cần idempotency key/outbox hoặc reconciliation riêng.

## 24. Deadlock, hot row và transaction giữ lâu

Không phải mọi lỗi resource pool đều do pool nhỏ. Hai worker có thể lock các row theo thứ tự khác nhau:

~~~text
Worker A: lock row 1 → chờ row 2
Worker B: lock row 2 → chờ row 1
~~~

Tăng pool lên 100 connections **không sửa được deadlock logic**.

Một số nguyên nhân khác:

- Update cùng một dòng tổng hợp từ nhiều partition.
- Query không có index, quét quá nhiều row.
- Transaction giữ lock trong lúc gọi API.
- Connection bị giữ sau exception/rollback không cleanup đúng.
- Cursor reader lâu làm cạn DB session.
- Executor queue vô hạn làm OOM.
- HTTP permit và DB connection tạo vòng phụ thuộc.

~~~mermaid
flowchart LR
    A["Thread A giữ DB connection"] --> B["Chờ HTTP permit"]
    C["Thread B giữ HTTP permit"] --> D["Chờ DB connection"]
    B -. "resource dependency" .-> C
    D -. "resource dependency" .-> A
~~~

### Biện pháp

- Lấy resource theo thứ tự nhất quán.
- Giảm transaction lifetime, tối ưu index và batch SQL.
- Có timeout hữu hạn và rollback rõ.
- Chia dữ liệu không chồng lấn, tránh hot row.
- Tránh giữ resource này trong khi chờ resource khác nếu có thể.
- Kiểm thử deadlock, retry, pool leak và cancellation.
- Dùng transaction/outbox phù hợp khi tách external side effect.

## 25. Data skew: nhiều worker vẫn có thể chờ một partition

Một partition chứa 10 triệu records còn bảy partition khác mỗi partition 100 nghìn. Tám worker có thể khởi chạy cùng lúc nhưng cuối job vẫn bị **partition lớn nhất** chi phối.

~~~mermaid
flowchart TB
    M["8 partitions"] --> H["Hot partition: 10 triệu rows"]
    M --> L["7 partitions nhỏ"]
    H --> W1["Worker 1: chạy lâu"]
    L --> W2["Workers 2..8: xong sớm"]
    W1 --> DONE["Manager chờ mọi phần việc"]
    W2 --> DONE
~~~

Không nên thêm nhiều JVM khi chỉ còn một partition không thể chia tiếp. Hãy:

1. Đo read count, elapsed time từng partition.
2. Chia theo range ID/time đủ nhỏ để cân bằng.
3. Dùng thống kê/histogram workload nếu phân bố lệch mạnh.
4. Giữ partition names và ExecutionContext ổn định khi restart.
5. Không tạo hàng chục nghìn partition quá nhỏ làm JobRepository/dispatch thành bottleneck.
6. Nếu một business key nóng phải xử lý tuần tự, tối ưu thuật toán hoặc thay mô hình nghiệp vụ chứ không tùy tiện tách key vào nhiều worker.

## 26. Quan sát concurrency trong production

Một dashboard cần trả lời: **Worker đang làm việc hữu ích, hay đang chờ pool?**

| Layer | Metric khuyến nghị | Ý nghĩa |
| --- | --- | --- |
| Executor | Active threads, queued/rejected tasks | Có bão hòa tại handler không? |
| HikariCP | Active/idle/pending, acquire timeout | Có đang đợi connection? |
| DB | Query p95, IOPS, lock wait, deadlocks | DB có bị contention? |
| HTTP | Pool pending, inflight, p95 latency, 429 | API có chạm quota? |
| RabbitMQ | Ready, unacked, redelivery, oldest message age | Work đang nằm ở đâu? |
| Kafka | Lag, assigned partitions, rebalance | Consumer có theo kịp không? |
| JVM | CPU, heap/GC, thread count, FD count | Worker có thiếu tài nguyên cục bộ? |
| Spring Batch | Read/write/filter, commit/rollback, step elapsed | Công việc thật hoàn thành thế nào? |
| JobRepository | Metadata latency, stale executions | Điều phối/restart có bị nghẽn? |
| Business | Unique keys, duplicates blocked, reconciliation failures | Dữ liệu có đúng không? |
| SLA | Job elapsed, pending work age | Có kịp cửa sổ xử lý? |

Log minh họa:

~~~text
jobExecutionId=7008
stepExecutionId=7021
workerInstance=worker-jvm-04
partition=customer-range-03
consumerThread=amqp-consumer-2
activeHandlers=4
jdbcPoolActive=8
jdbcPoolPending=3
jdbcAcquireP95Ms=410
brokerUnacked=12
chunkSize=500
chunkElapsedMs=1850
rollbackCount=1
action=LIMIT_CONCURRENCY
~~~

Các giá trị chỉ minh họa. Không đưa mọi JobExecutionId, customerId hay correlationId vào metric labels có cardinality quá cao; dùng structured logs/traces cho định danh động.

### Cảnh báo hữu ích

- Hikari pending/acquire timeout tăng liên tục.
- Executor queue và rejection tăng.
- Oldest message age tiến sát phần dự phòng SLA.
- DB lock wait hoặc deadlock tăng sau scale.
- HTTP 429 và retry attempts cùng tăng.
- Worker CPU thấp nhưng JDBC wait cao.
- Heap/GC tăng sau khi nâng chunk size/prefetch.
- Job `COMPLETED` nhưng business reconciliation FAIL.

## 27. Benchmark tuning theo một biến

Quy trình khuyến nghị:

1. Dùng cùng dataset, cutoff/snapshot và business assertions.
2. Đo baseline ít worker.
3. Ghi CPU, JDBC pool, DB lock, broker age, rollback và output đúng.
4. Tăng concurrency theo nấc 2 → 4 → 6 → 8.
5. Chỉ đổi một biến lớn mỗi lần; giữ chunk size/pool trước khi kết luận.
6. Nếu pool wait cao, xem DB có dư tài nguyên hay không rồi mới thay pool.
7. Chạy lặp nhiều lần, không chỉ chọn kết quả nhanh nhất.
8. Kiểm tra lỗi/restart trên cấu hình ứng viên.
9. Chọn điểm có headroom và chi phí tốt, không chỉ peak throughput.

Ví dụ benchmark **giả định** trên một worker JVM:

| Handler concurrency | JDBC pool max | Throughput hữu ích | p95 chunk latency | DB connection wait | Nhận xét |
| ---: | ---: | ---: | ---: | --- | --- |
| 1 | 8 | 3.200 item/s | 160 ms | Rất thấp | Baseline |
| 2 | 8 | 5.900 item/s | 180 ms | Thấp | Có ích |
| 4 | 8 | 9.200 item/s | 220 ms | Thấp | Có ích |
| 6 | 8 | 10.400 item/s | 340 ms | Trung bình | Lợi ích giảm |
| 8 | 8 | 10.600 item/s | 650 ms | Cao | Gần trần |
| 12 | 8 | 9.900 item/s | 1.200 ms | Rất cao | Phản tác dụng |

Con số **không phải benchmark thật của Spring Batch/HikariCP**. Mục tiêu là nhận diện điểm mà thêm concurrency chủ yếu tăng wait thay vì công việc hoàn tất.

## 28. Case study: 36 triệu hóa đơn trong 45 phút

Giả sử hệ thống xử lý **36.000.000 hóa đơn** trong cửa sổ **45 phút**, sử dụng manager Spring Batch, RabbitMQ và worker JVM ghi vào PostgreSQL.

Thông lượng tối thiểu lý tưởng:

\[
R_{\mathrm{required}}=
\frac{36.000.000}{45\times60}
\approx 13.333\ \mathrm{items/s}
\]

Phải có headroom cho startup, retry, checkpoint và bước cuối job.

### Bước 1 — Đo baseline

Bốn worker JVM, mỗi JVM bốn consumers, đạt **11.500 item/s** trong benchmark giả định; chưa đạt SLA. Đo được:

- Worker CPU khoảng 58%, không phải giới hạn CPU.
- JDBC acquire wait tăng vào giờ cao tải.
- DB lock wait cao khi nhiều worker cùng update bảng tổng ngày.
- Broker backlog tăng vì writer bị chậm.

**Không nên tăng JVM ngay:** hot-row contention có thể là nút thắt.

### Bước 2 — Phân tích ngân sách DB

DB cho phép 180 connections; dành 50 cho hệ khác và headroom, ngân sách batch là 130. Bốn worker mỗi worker pool 12, trần 48; manager/JobRepository có tổng trần 24, cộng là 72.

Với tám JVM: worker trần 96 + 24 = 120, gần ngân sách 130.

Với 12 JVM: worker trần 144 + 24 = 168, **vượt ngân sách**. Đây chỉ là bài toán trần cấu hình; DB CPU/I/O/lock có thể bão hòa trước đó.

### Bước 3 — Giảm tranh chấp DB

Thay vì mọi worker cùng cập nhật một dòng tổng ngày, writer ghi theo business key/partition và tổng hợp ở một step riêng hoặc dùng SQL atomic phù hợp nghiệp vụ. Sau tối ưu, lock wait giảm và throughput tăng.

### Bước 4 — Benchmark giả định

| Cấu hình | JVM | Consumers/JVM | Throughput hữu ích | Thời gian lý tưởng cho 36 triệu |
| --- | ---: | ---: | ---: | ---: |
| Ban đầu | 4 | 4 | 11.500 item/s | 52,2 phút |
| Sửa hot-row contention | 4 | 4 | 13.900 item/s | 43,2 phút |
| Tăng vừa đủ | 6 | 4 | 16.200 item/s | 37,0 phút |
| Tăng thêm | 8 | 4 | 16.600 item/s | 36,1 phút |
| Quá nhiều consumer | 8 | 8 | 15.800 item/s | 38,0 phút |

Các số liệu đều **giả định**; thời gian `N/R` là phép ước lượng, **không cam kết** JobExecution thực sự có cùng elapsed. Sáu JVM cho dư địa tốt hơn bốn JVM; tám JVM chỉ tăng ít trong khi chi phí cao hơn. Cần đo toàn job qua nhiều lần và thử fault injection.

### Bước 5 — Xác nhận recovery và correctness

1. Gửi duplicate của chunk đã commit.
2. Kill worker sau commit trước reply.
3. Mô phỏng DB outage ngắn, đo connection wait/retry storm.
4. Đảm bảo message không vào vòng requeue nóng.
5. Restart cùng JobInstance với input ổn định.
6. Đối soát mọi invoice ID và source version.
7. Rolling deploy trong lúc có unacked requests.
8. Xác minh connection budget khi replica tăng tối đa.

**Kết luận tình huống:** sửa tranh chấp DB, chọn số worker phù hợp và kiểm soát pool có thể hiệu quả hơn tăng concurrency không giới hạn.

## 29. Graceful shutdown, rolling deploy và scale-down

Một worker đang xử lý Batch có thể giữ cursor, transaction, request unacked hoặc reply chưa gửi. Khi scale-down:

1. Ngừng nhận phần việc mới bằng cơ chế quiesce/pause phù hợp.
2. Quan sát số active handlers và requests unacked.
3. Cho chunk/StepExecution đang chạy cơ hội kết thúc trong deadline.
4. Ghi checkpoint, commit/rollback và reply theo giao thức.
5. Đóng DataSource/HTTP client/executor theo lifecycle.
6. Phần chưa hoàn tất được phục hồi qua broker/JobRepository một cách có kiểm soát.
7. Không giao cùng StepExecution cho hai process nếu worker cũ có thể vẫn chạy.
8. Đối soát business data sau rollout.

`terminationGracePeriodSeconds` của orchestration phải được cân nhắc theo **chunk p99 latency, rollback và publish reply**. Graceful shutdown không bảo đảm mọi chunk đều commit; kiến trúc vẫn phải chịu được kill đột ngột.

Nếu nhiều phiên bản worker cùng tiêu thụ queue trong rolling upgrade, kiểm tra tương thích message schema, Spring Batch Integration protocol, serializer và hạ tầng trước khi scale.

## 30. Kiểm thử concurrency và pool exhaustion

Một test một worker thành công **không** chứng minh concurrency và recovery an toàn.

### 30.1. Đo peak handler concurrency

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class InflightProbe {
    private final AtomicInteger active =
            new AtomicInteger();
    private final AtomicInteger peak =
            new AtomicInteger();

    public void enter() {
        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);
    }

    public void exit() {
        active.decrementAndGet();
    }

    public int peak() {
        return peak.get();
    }
}
~~~

Instrument handler:

~~~java
probe.enter();
try {
    processRequest();
} finally {
    probe.exit();
}
~~~

Cho 100 requests đến JVM được giới hạn bốn handler, assert `peak() <= 4` khi toàn bộ đường handler đều được instrument. **Test này không đo các tác vụ async được spawn bên ngoài handler**, nên nếu có async phải instrument thêm resource thật.

### 30.2. Test JDBC pool exhaustion

- Dùng DB/test environment riêng.
- Giữ một số connection trong các transaction có kiểm soát.
- Cho nhiều handlers tranh pool nhỏ.
- Kiểm tra pending/timeout có giới hạn, không deadlock.
- Giải phóng resource và xác nhận pool phục hồi.
- Đảm bảo request lỗi được retry/recover đúng thay vì mất message.

### 30.3. Test worker crash

- Dừng JVM trước commit.
- Dừng JVM **sau commit trước ACK/reply**.
- Kiểm tra redelivery không nhân đôi side effect.
- Restart JobInstance/StepExecution theo cơ chế phù hợp.
- Đối soát business keys/values, không chỉ tổng `writeCount`.

### 30.4. Test nhiều JVM

Một semaphore trong một JVM không giới hạn toàn cluster. Chạy ít nhất hai worker processes để xác minh aggregate HTTP QPS, tổng Hikari connections, lock contention và output đúng khi cùng DB/API.

### 30.5. Test retry storm

Cắt DB hoặc mô phỏng HTTP 503; đo attempts, backoff/jitter, oldest message age, DB acquire wait và số active threads. Sau khi phục hồi, backlog phải giảm và business output vẫn đúng; poison message không được giữ vòng lặp vô hạn.

## 31. Checklist trước khi tăng số worker

- [ ] Đã phân biệt worker JVM, consumer, StepExecution, chunk thread và inflight request.
- [ ] Có baseline với dataset cố định và business reconciliation.
- [ ] Đã xác định phần CPU-bound/I/O-bound bằng metric thực.
- [ ] Đã liệt kê CPU, JDBC/HTTP pools, broker, executor, DB I/O/locks và API quota.
- [ ] Biết số pool trên **một JVM** và tổng trần connections **toàn cluster**.
- [ ] Có ngân sách DB connection cho manager, JobRepository và headroom.
- [ ] Không tăng pool nếu DB đã bão hòa mà chưa xử lý bottleneck.
- [ ] Reader/processor/writer/SDK tuân thủ thread-safety contract.
- [ ] Không nhầm `@StepScope` với phạm vi từng chunk thread.
- [ ] Không nhầm gridSize với số partition hoặc số worker chạy đồng thời.
- [ ] Với RabbitMQ, đã kiểm chứng listener concurrency, prefetch, ACK/redelivery.
- [ ] Với Kafka, đã kiểm tra topic partitions, offset policy và ordering.
- [ ] Có bounded queue, inflight limit và backpressure.
- [ ] Không tạo nhiều tầng async concurrency ngoài ngân sách.
- [ ] HTTP connection concurrency và API rate limit được kiểm soát riêng.
- [ ] Không giữ connection/lock khi chờ downstream không cần thiết.
- [ ] Writer idempotent, checkpoint và partition identity ổn định khi restart.
- [ ] Retry có attempts/backoff/budget, không có hot requeue.
- [ ] Không giao lại cùng StepExecution thiếu ownership/reconciliation.
- [ ] Có metric p95/p99, DB pool pending, broker queue age, rollback và GC.
- [ ] Có test tăng concurrency theo một biến và dữ liệu không đổi.
- [ ] Có test kill worker sau commit trước reply và replay.
- [ ] Có runbook scale-down/rolling deploy, alert và rollback.
- [ ] Chỉ tăng worker khi throughput hữu ích và tính đúng đều PASS.

## 32. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “16 worker tức 16 JDBC connections.” | Một worker có thể dùng nhiều hoặc ít connection theo lifecycle. |
| “gridSize=16 là chạy 16 partitions cùng lúc.” | Executor/handler concurrency có thể nhỏ hơn. |
| “Prefetch=20 là 20 threads xử lý.” | Prefetch là credit/message đã cấp trước ACK, không phải thread count. |
| “CPU thấp thì tăng thread là đúng.” | Có thể đang chờ DB/API/lock. |
| “Pool càng lớn thì database càng nhanh.” | Quá nhiều connections có thể làm contention tăng. |
| “@StepScope tạo instance riêng mỗi chunk thread.” | StepScope gắn với StepExecution. |
| “Nhiều JVM không còn tranh resource.” | Mỗi JVM có heap riêng nhưng DB/broker/API là tài nguyên chung. |
| “Executor queue vô hạn giúp không mất task.” | Queue quá lớn gây heap pressure và deadline miss. |
| “Tăng max threads luôn tạo đủ threads.” | Nhiều executor ưu tiên queue theo cấu hình trước khi tăng thread. |
| “RabbitMQ ACK là DB commit exactly once.” | ACK không mặc nhiên atomic với transaction DB. |
| “Kafka partition order bảo đảm DB commit order.” | Handler async/transaction có thể đảo side effect. |
| “Connection pool sửa được SQL deadlock.” | Deadlock cần sửa thứ tự lock/transaction. |
| “Thêm retry làm throughput tốt hơn.” | Retry storm có thể giảm throughput hữu ích. |
| “Hot partition cần thêm JVM.” | Nếu một partition không chia được, JVM khác có thể rảnh. |
| “HTTP connection pool 50 tức API cho 50 RPS.” | Concurrency và QPS quota là hai giới hạn khác nhau. |
| “Job COMPLETED bảo đảm output đúng.” | Cần business reconciliation sau lỗi/restart. |

## 33. Câu hỏi tự kiểm tra

**1. Có sáu JVM, mỗi HikariCP maximumPoolSize=10. Trần connection phía worker là bao nhiêu?**

Tối đa **60 connection** theo tổng cấu hình nếu các pool đều mở đến trần. Số active thực có thể nhỏ hơn; ngân sách DB còn phải tính manager và ứng dụng khác.

**2. Một worker có tám consumers và JDBC pool bốn connections. Có chắc tám chunk cùng commit không?**

Không. Nhiều handler có thể chờ connection, và số connections mỗi chunk cần cũng không cố định.

**3. gridSize=12 nhưng executor chỉ có bốn threads. Bao nhiêu partitions chạy đồng thời?**

Nếu mỗi task tương ứng một worker StepExecution và không có tầng concurrency khác, khoảng tối đa **bốn** có thể chạy trên executor ấy; số partition được tạo do Partitioner quyết định.

**4. Vì sao @StepScope không bảo vệ reader stateful trong multi-threaded step?**

Vì nhiều chunk threads của **cùng một StepExecution** có thể truy cập chung target reader. Phải kiểm tra thread safety và checkpoint.

**5. Hikari pool pending tăng, có nên tăng pool ngay không?**

Chưa. Cần xem DB CPU/I/O/lock, slow SQL và thời gian giữ connection; DB đã bão hòa thì tăng pool có thể làm chậm thêm.

**6. RabbitMQ prefetch cao ảnh hưởng gì khi worker chết?**

Có thể tăng số message đã giao nhưng chưa ACK cần được redeliver/reconcile và tăng memory footprint, dù handler threads không đổi.

**7. Kafka topic bốn partitions, group có 12 consumers. Có 12 partitions được xử lý không?**

Không. Một group không thể assign hơn bốn partitions của topic đó cùng lúc; nhiều consumers có thể idle.

**8. Vì sao semaphore bốn permits không đảm bảo bốn HTTP calls trên toàn cluster?**

Semaphore thuộc phạm vi JVM. Mười JVM có thể tạo khoảng 40 calls qua các gateway riêng; cần quota điều phối theo tổng cluster.

**9. Worker DB commit rồi mất reply. Rủi ro là gì?**

Request có thể được redeliver/retry, dẫn tới side effect lặp nếu writer không idempotent. Correlation và reconciliation cần phối hợp với business key/ledger.

**10. Little's Law `L=λW` dùng để làm gì?**

Đối chiếu mức inflight trung bình với tốc độ hoàn tất và thời gian lưu trong một hệ thống ổn định, không trực tiếp chọn thread count tối ưu.

**11. Tại sao không nên giữ JDBC transaction trong lúc chờ HTTP API?**

Có thể giữ connection/lock lâu, khiến các worker khác chờ và timeout. Cần ranh giới transaction và idempotency/outbox phù hợp.

**12. Tăng từ bốn lên tám worker khiến throughput tăng 2% nhưng DB lock wait tăng gấp ba. Nên làm gì?**

Đánh giá lại bottleneck và chi phí; thường không nên giữ concurrency cao hơn chỉ vì throughput tăng rất ít. Kiểm chứng SLA và resource headroom.

**13. Chunk size lớn ảnh hưởng gì?**

Giảm số transaction/message nhưng tăng payload, memory, thời gian giữ transaction và chi phí replay sau lỗi.

**14. Khi worker bị scale-down, ACK và checkpoint phải được xử lý thế nào?**

Ngừng nhận việc mới, có thời gian drain, commit/rollback và reply theo protocol; phần chưa hoàn tất được broker/JobRepository phục hồi an toàn. Vẫn phải chịu được kill đột ngột.

**15. Vì sao một benchmark 15.000 message processed/s có thể kém hơn 10.000 item/s hữu ích?**

Vì message count có thể bao gồm retries, duplicates và rollback; business throughput chỉ đếm công việc được commit hợp lệ, không đếm attempts.

---

**Ghi nhớ:** Worker concurrency phải được thiết kế cùng **resource pools và năng lực thật của downstream**, không theo một con số threads đơn lẻ. Hãy phân biệt JVM, consumer, StepExecution, chunk thread và request inflight; tính tổng JDBC/HTTP budgets trên toàn cluster; đo pool wait, DB locks, broker queue age và throughput hữu ích. Spring Batch có nhiều mô hình scaling, nhưng **thread safety, idempotency, retry/restart và backpressure** luôn cần được kiểm chứng. Cấu hình tốt là cấu hình **đúng dữ liệu, đạt SLA và còn khả năng phục hồi khi worker, broker hoặc DB gặp sự cố**.
