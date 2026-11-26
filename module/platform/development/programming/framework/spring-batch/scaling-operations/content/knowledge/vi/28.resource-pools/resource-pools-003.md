# Thread pool và worker count trong Spring Batch

Một Spring Batch job chạy tuần tự mất 90 phút để xử lý dữ liệu, trong khi cửa sổ batch chỉ có 30 phút. Nhóm phát triển tăng `maxPoolSize` từ 4 lên 32 và tạo 64 partition. Kết quả không như mong đợi: throughput gần như đứng yên, `HikariCP` xuất hiện nhiều thread chờ connection, số lần retry tăng, còn CPU của ứng dụng chỉ hoạt động ở mức trung bình. Vấn đề không nằm ở việc thiếu một con số “đủ lớn”, mà ở chỗ **thread pool, số worker đang chạy, lượng công việc độc lập và khả năng của các resource pool khác nhau không đồng nhất**.

Bài học **“Thread pool và worker count”** thuộc chương **Resource pool** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu chung là mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning, remote chunking và các mô hình phân tán phù hợp; đo nút thắt, giữ thread safety, retry/restart và vận hành job theo tài nguyên thực tế. Trọng tâm ở đây là **hiểu và điều chỉnh đúng mức đồng thời** thay vì mặc định tăng số thread là tăng tốc.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **thread**, **executor thread pool**, **worker count**, **task queue**, **partition count**, **chunk size** và **JDBC connection pool**.
2. Giải thích ý nghĩa `corePoolSize`, `maxPoolSize` và `queueCapacity` của `ThreadPoolTaskExecutor`.
3. Hiểu mức đồng thời ở multi-threaded step, parallel steps, local partitioning, remote partitioning và remote chunking.
4. Xác định giới hạn concurrency theo CPU, I/O, database, API quota, memory, số partition và chính sách của framework.
5. Ước lượng nhu cầu concurrency bằng throughput/SLA, Little's law và tỷ lệ thời gian chờ I/O.
6. Cấu hình một executor có giới hạn trong Spring Batch 5.2.x, không mặc định tạo thread vô hạn.
7. Nhận diện các rủi ro thread safety, queue backlog, pool exhaustion, retry storm và deadlock.
8. Benchmark theo `committed throughput`, latency, pool utilization, số connection và dữ liệu đầu ra đúng.
9. Đặt runbook để tăng/giảm worker, xử lý quá tải và phục hồi sau lỗi mà không phá checkpoint.

## 2. Thuật ngữ: không phải số nào cũng là “worker”

Một câu như “job có 16 workers” còn thiếu ngữ cảnh: đó là 16 Java threads, 16 remote JVM, 16 partition StepExecution hay 16 message consumers?

| Khái niệm | Định nghĩa | Điều **không** đồng nghĩa |
| --- | --- | --- |
| `Thread` | Luồng thực thi bên trong một JVM | Không mặc nhiên có CPU core riêng |
| `TaskExecutor` | Cơ chế dispatch tác vụ sang thread | Không tự chứng minh reader/writer thread-safe |
| `ThreadPoolTaskExecutor` | Executor dùng pool thread với chính sách tăng/giảm/queue | Không phải JDBC pool |
| `corePoolSize` | Số thread lõi executor quản lý | Không phải số partition |
| `maxPoolSize` | Trần số thread của **executor đó** | Không phải trần concurrency toàn hệ thống |
| `queueCapacity` | Sức chứa task đang chờ trong executor | Không phải số task được xử lý cùng lúc |
| `worker count` | Số đơn vị thực thi nghiệp vụ đang hoạt động; phải xác định phạm vi | Không mặc nhiên bằng `maxPoolSize` |
| `gridSize` | Hint cho cơ chế partitioning về số mảnh công việc | Không phải worker count hay threads |
| `chunk size` | Số item đầu vào mỗi lượt commit thông thường của chunk-oriented step | Không phải số thread |
| `HikariCP.maximumPoolSize` | Trần JDBC connections trong **một DataSource pool** | Không phải số worker hoặc trần toàn cluster |
| Broker consumer concurrency | Số request có thể được lấy/xử lý đồng thời theo adapter | Prefetch không tương đương số consumers |

**Quy ước trong bài:** “worker concurrency” (`C`) là số đơn vị công việc xử lý cùng lúc tại **ranh giới được đo**, ví dụ số worker `StepExecution` đang chạy trong local partitioning. Với remote chunking, `C` là số chunk requests được thực thi cùng lúc trên các consumer; với remote partitioning, đó là số remote worker StepExecution đang thực thi.

### 2.1. Một pipeline có nhiều hàng đợi và pool

~~~mermaid
flowchart LR
    S["Partitioner / Chunk dispatch"] --> EQ["Executor queue"]
    EQ --> TP["Worker threads"]
    TP --> CP["JDBC pool<br/>connections"]
    CP --> DB[("Database")]
    TP --> HC["HTTP client pool<br/>in-flight requests"]
    HC --> API["External API"]
    TP --> BR[("Broker / Remote workers")]
~~~

Đây là sơ đồ khái niệm: không phải job nào cũng gọi HTTP, JDBC và broker cùng lúc. Nó minh họa rằng **task đã được executor nhận chưa chắc đang làm công việc hữu ích**: một thread có thể đang chờ DB connection, HTTP response, lock hoặc message reply.

Một queue dài ở tầng executor và một queue dài ở tầng JDBC pool có nguyên nhân khác nhau. Khi sửa bottleneck phải nhìn đúng hàng đợi, không chỉ tăng `maxPoolSize`.

## 3. Worker count ở từng mô hình Spring Batch

Các mô hình mở rộng Spring Batch có **đơn vị song song hóa khác nhau**.

| Mô hình | Đơn vị work đồng thời | Cách điều khiển concurrency | State/checkpoint cần chú ý |
| --- | --- | --- | --- |
| Chunk-oriented step tuần tự | Một chuỗi chunk | Không thêm executor thì thường chạy tuần tự | Một StepExecution, reader checkpoint dễ kiểm soát hơn |
| **Multi-threaded step** | Nhiều chunk tasks của cùng một step | `TaskExecutor` cùng giới hạn dispatch/repeat của phiên bản | Nhiều chunk thường chung StepExecution; reader/processor/writer phải thread-safe |
| **Parallel steps** | Các branch/flow step độc lập | Executor của split flow, số branches sẵn sàng | Mỗi step có StepExecution của mình |
| **Local partitioning** | Nhiều worker StepExecution trong một JVM | `TaskExecutorPartitionHandler` / `taskExecutor` + số partition | Mỗi partition có StepExecution/ExecutionContext riêng |
| **Remote partitioning** | Worker StepExecution trên JVM/pod khác | Partition count, broker, consumer capacity, replica count | Shared JobRepository, tên partition/checkpoint ổn định |
| **Remote chunking** | Chunk request được worker process xử lý | Message consumer concurrency, replica count, in-flight request/backpressure | Manager đọc item; request/reply, retry và idempotency |

### 3.1. Multi-threaded step: worker là chunk task

Một chunk-oriented step có thể dispatch nhiều lượt chunk processing qua một `TaskExecutor`. Các chunk có thể hoàn tất **không theo thứ tự đọc**.

~~~text
StepExecution chung
  ├─ thread-1: chunk A -> commit
  ├─ thread-2: chunk B -> commit
  ├─ thread-3: chunk C -> commit
  └─ thread-4: chunk D -> commit
~~~

Nếu dùng một `FlatFileItemReader` hoặc `JdbcCursorItemReader` có cursor mutable chung mà chưa chứng minh thread safety, tăng pool từ 1 lên 8 có thể làm mất/trùng item. `@StepScope` là scope theo **StepExecution**, không tự tạo reader riêng cho từng chunk thread. Kiểm thử restart sau khi các chunk commit lệch thứ tự là bắt buộc với reader stateful.

**Lưu ý phiên bản:** `throttleLimit` của Spring Batch đã bị đánh dấu deprecated trong nhánh 5.x. Mức đồng thời thực tế có thể bị giới hạn bởi tầng repeat operations/step implementation bên cạnh executor. Với nhu cầu thay đổi throttling, hãy xem API `StepBuilder.stepOperations(...)` và `RepeatOperations` của đúng phiên bản, thay vì mặc định `maxPoolSize` là giới hạn duy nhất.

### 3.2. Parallel steps: worker là nhánh độc lập

Một job có ba nhánh độc lập như nhập hóa đơn, nhập tài khoản và nhập bảng giá có thể chạy các `Step` theo các flow song song. Dù split-flow executor có 16 threads, **chỉ ba nhánh sẵn sàng** thì không thể tự tạo thêm 13 nhánh công việc.

Parallel steps phù hợp khi có những pipeline nghiệp vụ độc lập. Nếu cả ba nhánh cùng dùng một database, tổng kết nối và lock của ba step vẫn cộng dồn. Đừng cấp tối đa 16 threads cho từng nhánh mà bỏ qua giới hạn chung.

### 3.3. Local partitioning: worker là StepExecution

Một manager chia dữ liệu thành 40 partition. Executor có tối đa tám threads, nên thường **không quá tám worker StepExecution** có thể được thực thi đồng thời bởi executor ấy; phần còn lại chờ lượt.

~~~text
P = 40 logical partitions
C = 8 concurrent worker StepExecutions
K = 500 items/chunk trong mỗi worker

Không phải:
  40 partitions = 40 threads
  hay 500 items/chunk = 500 threads.
~~~

Mỗi worker có `ExecutionContext` riêng, có thể cấu hình reader `@StepScope` theo file/khoảng ID. Đây là cách kiểm soát state theo shard tốt hơn nhiều trường hợp multi-threaded step dùng chung cursor.

### 3.4. Remote partitioning: worker có thể là pod nhưng không chỉ đếm pod

Giả sử có sáu worker pods, mỗi pod cho listener xử lý tối đa hai `StepExecutionRequest` đồng thời. **Năng lực tiếp nhận tối đa theo cấu hình** có thể là 12 requests, nhưng concurrency **thực tế** còn bị giới hạn bởi số partition sẵn sàng, tài nguyên/StepExecution ownership và việc xử lý trùng request.

Nếu chỉ có tám partition đang chờ, hệ thống không thể có 12 worker StepExecution hữu ích. Nếu mỗi pod chỉ chạy một worker step tại một thời điểm, sáu pod tương ứng tối đa khoảng sáu partition đang chạy. Vì thế luôn ghi rõ:

~~~text
remote worker replicas = 6
max concurrent step requests per replica = 2
configured execution capacity = 12
eligible partitions = 8
actual useful concurrency <= 8
~~~

Manager và workers phải dùng metadata JobRepository tương thích. Không scale bằng cách cho hai thế hệ worker cùng xử lý một `StepExecution` cũ khi manager đã restart mà chưa kiểm tra liveness/fencing.

### 3.5. Remote chunking: worker là consumer đang xử lý chunk

Với RabbitMQ/JMS, số worker replicas, số consumer threads **mỗi replica** và broker partitioning/routing tạo ra concurrency. `Prefetch=100` có thể làm một consumer giữ nhiều message **chưa ACK**; nó **không** tạo 100 thread thực thi.

Với Kafka consumer group, số consumer chủ động cho một topic không thể vượt số partitions được gán một cách hữu ích ở thời điểm đó; một consumer có thể giữ nhiều records nhưng không tự tạo một worker thread cho mỗi record.

Khi scale remote chunking, phải giám sát **request queue, reply queue, độ trễ correlation** và idempotency của worker. Một chunk có thể được giao lại nếu worker đã commit DB nhưng mất reply hoặc ACK.

## 4. Cơ chế ThreadPoolTaskExecutor: core, max và queue

`ThreadPoolTaskExecutor` của Spring Framework bao bọc cơ chế pool tương tự `ThreadPoolExecutor` của Java, với ba tham số quan trọng:

- `corePoolSize`: số thread lõi được sử dụng.
- `maxPoolSize`: số thread tối đa executor có thể tạo.
- `queueCapacity`: số task có thể xếp hàng chờ trước khi executor tạo thêm thread ngoài core, theo chính sách queue.

Giả sử cấu hình:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(20);
executor.setThreadNamePrefix("batch-worker-");
executor.initialize();
~~~

Diễn giải điển hình với một `ThreadPoolExecutor` có queue dương:

1. Executor tạo thread tới mức core khi có nhu cầu.
2. Sau mức core, task mới thường được **đưa vào queue** khi còn chỗ.
3. Khi queue đầy và vẫn còn khả năng tăng worker threads, executor tăng thread vượt core, tối đa max.
4. Khi cả threads và queue đều hết sức chứa, task mới bị **rejected** theo policy.

~~~text
corePoolSize = 4
maxPoolSize  = 12
queueCapacity = 20

  active<=4 -> các task dư thường vào queue
  queue đầy -> có thể tạo thêm thread 5..12
  active=12 và queue=20 -> submit thêm sẽ bị reject/policy xử lý
~~~

**Sai lầm thường gặp:** cấu hình `core=4, max=32, queue=1000` rồi kỳ vọng 32 threads lập tức xử lý batch. Với queue dài, số thread có thể ở gần core trong khi 1.000 task đang chờ; `maxPoolSize` chỉ được dùng khi queue đầy. Đó là một lý do vì sao cấu hình “max thật lớn” không làm tăng tốc.

### 4.1. queueCapacity = 0 không phải giải pháp mặc định

`queueCapacity=0` khiến executor ưu tiên giao trực tiếp task cho thread thay vì xếp hàng trong queue có dung lượng dương, nên có thể tăng thread nhanh tới `maxPoolSize`. Nhưng nếu submit vượt năng lực, rejection cũng xảy ra nhanh hơn.

Đừng đặt `queueCapacity=0` với `maxPoolSize` cực lớn hoặc vô hạn chỉ để tránh backlog: ứng dụng có thể tạo quá nhiều threads, hết bộ nhớ stack, tranh CPU/DB và tạo retry storm. Queue ít hay nhiều đều cần **giới hạn downstream** và handling rejection có kiểm soát.

### 4.2. Kích thước queue có phải độ song song không?

Không. Với core=max=8 và queue=64:

- Tối đa tám task thực thi đồng thời trong pool.
- Có thể thêm tối đa 64 task **chờ** trong queue của pool.
- Tổng 72 không phải concurrency.
- Task ở queue vẫn có độ trễ end-to-end và giữ các reference trong heap.
- Nếu job cần hoàn tất trong một cửa sổ ngắn, queue sâu có thể che giấu việc hệ thống đã không kịp SLA.

Một task phải được tính là “đang làm work” khi nó thực sự có tiến độ commit, không phải khi vừa submit thành công.

### 4.3. Rejection policy và backpressure

Khi executor bão hòa, `ThreadPoolExecutor.AbortPolicy` thường ném exception, còn `CallerRunsPolicy` chuyển việc chạy task sang thread gọi trong một số tình huống. Cần hiểu hậu quả:

| Chính sách | Tác động điển hình | Cảnh báo với Spring Batch |
| --- | --- | --- |
| Fail/reject rõ ràng | Báo ngay không thể nhận task, phù hợp cơ chế retry/stop đã thiết kế | Cần để job phản ánh lỗi, không âm thầm mất work |
| Caller-runs | Làm thread submit bị chậm, tạo backpressure cục bộ | Có thể làm manager/step thread bị block, ảnh hưởng transaction/context và scheduling |
| Queue giới hạn | Hạn chế task tồn đọng; tạo điểm phản hồi áp lực | Queue dài vẫn tạo latency và chiếm heap |
| Thêm thread vô hạn | Có vẻ giảm queue tạm thời | Dễ vượt CPU, DB pool, memory và API quotas |

Không dùng `DiscardPolicy` hoặc cơ chế âm thầm bỏ task cho xử lý batch nếu không có lớp logic bảo đảm không mất dữ liệu và báo lỗi. Spring Batch cần biết chính xác đơn vị công việc nào được thực thi.

## 5. Ví dụ cấu hình executor cho Spring Batch 5.2.x

Ví dụ dưới đây giả định Spring Batch 5.2.x, Spring Boot 3.x và Java 17+. Cần định nghĩa `JobRepository`, transaction manager và reader/processor/writer thật trong ứng dụng.

### 5.1. Executor cố định cho multi-threaded step

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class BatchWorkerPoolConfig {

    @Bean("chunkTaskExecutor")
    public ThreadPoolTaskExecutor chunkTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("batch-chunk-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step transformStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputRow> safeReader,
            ItemProcessor<InputRow, OutputRow> safeProcessor,
            ItemWriter<OutputRow> safeWriter,
            @Qualifier("chunkTaskExecutor")
                    ThreadPoolTaskExecutor executor) {

        return new StepBuilder("transformStep", jobRepository)
                .<InputRow, OutputRow>chunk(200, transactionManager)
                .reader(safeReader)
                .processor(safeProcessor)
                .writer(safeWriter)
                .taskExecutor(executor)
                .build();
    }
}
~~~

`InputRow`/`OutputRow` là kiểu dữ liệu của dự án; đoạn code minh họa wiring step, không phải ứng dụng chạy độc lập. Những tên `safeReader`, `safeProcessor`, `safeWriter` **không bảo đảm thread safety** — từng implementation phải được đánh giá.

Tại sao ban đầu chọn `core=max=4`?

- Có trần concurrency rõ ràng.
- Không có bất ngờ do queue dương làm `maxPoolSize` khó được sử dụng.
- Dễ benchmark mức 1/2/4/8 threads trong điều kiện kiểm soát.
- Có thể giữ nhiều cấu hình khác nhau cho các job workload khác nhau.
- Sau khi đo mới cân nhắc pool elastic hoặc mở rộng CPU/DB.

Không bật multi-threading cho `FlatFileItemReader`/`JdbcCursorItemReader` stateful dùng chung mà chưa kiểm chứng checkpoint/restart. Reader đồng bộ hóa `read()` có thể giảm race trong một số trường hợp nhưng còn nguy cơ bottleneck và thứ tự commit. Với input chia shard được, **partitioning có reader riêng theo StepExecution** thường dễ kiểm soát hơn.

### 5.2. Executor cho local partitioning

~~~java
@Bean("partitionExecutor")
public ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(6);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(12);
    executor.setThreadNamePrefix("batch-partition-");
    executor.initialize();
    return executor;
}

@Bean
public Step managerStep(
        JobRepository jobRepository,
        @Qualifier("orderPartitioner") Partitioner partitioner,
        @Qualifier("orderWorkerStep") Step workerStep,
        @Qualifier("partitionExecutor") ThreadPoolTaskExecutor executor) {

    return new StepBuilder("managerStep", jobRepository)
            .partitioner("orderWorkerStep", partitioner)
            .step(workerStep)
            .gridSize(24)
            .taskExecutor(executor)
            .build();
}
~~~

Snippet giả định các import `Step`, `JobRepository`, `StepBuilder`, `Partitioner` và các annotation đã có như ở ví dụ trước. Với 24 partition logic và executor 6 threads, manager có thể thực thi nhiều nhất khoảng sáu worker step cùng lúc thông qua pool này; các partition còn lại chờ. `gridSize(24)` chỉ là hint: partitioner có thể dựa vào manifest cố định để tạo số shard khác.

Mỗi worker thường có reader `@StepScope` và `ExecutionContext` chứa file/range riêng. Đó là điểm khác với multi-threaded step chia chung reader state.

### 5.3. Có nên dùng chung một executor cho mọi step?

Dùng chung một pool có thể giúp đặt tổng hạn mức thread và tránh cấp quá nhiều threads ở nhiều step; nhưng nếu một job dài giữ hết worker threads, job khẩn cấp có thể **starve**. Dùng **pool riêng theo workload/SLA** giúp cô lập nhưng làm tổng thread capacity phình ra khi nhiều job cùng chạy.

| Phương án | Lợi ích | Rủi ro |
| --- | --- | --- |
| Một bounded executor chung | Tổng trần threads dễ kiểm soát | Starvation, khó ưu tiên critical jobs |
| Pool riêng per job/step | Cô lập, đo latency/SLA dễ hơn | Nhiều pool cùng đạt max làm host/DB quá tải |
| Pool chung + admission control | Giới hạn tổng in-flight, có ưu tiên | Cần thiết kế scheduling/fairness |
| Remote workers autoscale | Tăng tài nguyên xử lý sang pods khác | Downstream DB/API quota cộng dồn, worker overlap/restart |

Nếu dùng nhiều executor, tính **tổng concurrency đồng thời** của những job có thể chạy trùng cửa sổ, không chỉ giá trị lớn nhất của một executor.

## 6. Phân biệt thread pool với JDBC connection pool

Giả sử Spring Batch có 12 chunk workers, nhưng datasource HikariCP chỉ cho tối đa sáu connection:

~~~text
Executor: 12 threads đang chạy
  ├─ 6 threads giữ JDBC connections
  └─ 6 threads có thể đang chờ mượn connection

HikariCP: maximumPoolSize = 6
Database: chịu thêm tải từ online traffic và JobRepository
~~~

Nếu phần lớn chunk luôn cần JDBC, tăng worker threads từ 12 lên 24 có thể chỉ làm tăng `pending` và `connectionTimeout`. CPU vẫn có thể thấp vì threads đang blocked.

### 6.1. Số connection cần cho mỗi worker không luôn là một

Worker có thể cần đồng thời:

- Một connection đang giữ JDBC cursor cho reader.
- Một connection cho transaction writer/chunk.
- Một connection khác cho audit hoặc call sang datasource riêng.
- Metadata DB connection cho `JobRepository` tùy cấu hình hạ tầng.
- Connection HTTP/broker hoàn toàn khác JDBC.

Tùy `JdbcCursorItemReader`, driver, transaction manager và resource lifecycle, reader cursor có thể giữ một connection trong lúc writer cần một connection khác. **Không tự đặt `HikariCP.maximumPoolSize = workerCount`**. Cần kiểm tra connection acquire/hold time trong môi trường thật, cùng transaction boundaries.

### 6.2. Tính ngân sách toàn hệ thống

Giả sử database có ngân sách **80 connections cho batch subsystem** sau khi đã dành capacity cho online workload.

Có một manager JVM dùng pool tối đa 8 và 6 worker pods, mỗi pod HikariCP `maximumPoolSize=10`:

\[
C_{\text{configured}}=8+6\times10=68.
\]

Mức trần cấu hình 68 nằm trong ngân sách 80 theo giả định. Nhưng đây chỉ là **số connection tối đa có thể cấp từ các pool đó**, không chứng minh DB đủ CPU, IOPS, lock hoặc query throughput cho 68 connections.

Nếu autoscaler tăng từ 6 lên 10 worker pods mà không giảm per-pod pool, trần tăng thành:

\[
C_{\text{configured,new}}=8+10\times10=108,
\]

vượt ngân sách 80. Vì vậy autoscaling workers phải có **global DB connection budget** hoặc chính sách phân bổ per-pod rõ ràng.

### 6.3. Pool khác cũng có trần riêng

- HTTP client có max connections per route/host và max in-flight.
- Kafka/RabbitMQ listener concurrency, prefetch, broker partitions và rate limit tạo giới hạn khác.
- File handles và OS descriptors có trần.
- Executor queue và JDBC pool pending là hai hàng đợi, cần quan sát riêng.
- JVM heap có giới hạn cho item/chunk buffers khi nhiều worker cùng giữ dữ liệu.
- Thread stack memory tăng theo số platform threads (không đồng nghĩa heap usage).

## 7. Sizing theo loại workload: CPU-bound và I/O-bound

Không có một “pool size chuẩn” cho mọi job. Trước tiên phân loại thời gian task:

**CPU-bound:** phần lớn thời gian là parse, nén, mã hóa, tính toán, transform trên CPU. Khi một process được cấp bốn CPU cores hiệu dụng, tạo 100 platform threads chạy tính toán liên tục thường không làm throughput gấp 25 lần. Quá nhiều threads gây context switching, cache contention và memory pressure.

**Blocking I/O-bound:** thread dành phần lớn thời gian chờ DB, HTTP, disk/network; có thể sử dụng nhiều threads hơn CPU cores để che thời gian chờ nếu downstream còn capacity.

**Mixed:** một chunk có cả CPU và I/O; cần phân tách thời gian thực đo được, đừng chỉ nhìn CPU trung bình thấp mà kết luận phải tăng threads.

### 7.1. Quy tắc kinh nghiệm cho blocking I/O

Một công thức điểm xuất phát:

\[
N_{\text{threads}}\approx
N_{\text{CPU}}\left(1+\frac{W}{C_{\text{cpu}}}\right),
\]

trong đó `W` là thời gian chờ blocking I/O và `C_cpu` là thời gian CPU hữu ích trung bình của một task.

Ví dụ một máy có 4 CPU cores hiệu dụng, mỗi task dùng 25 ms CPU và đợi 75 ms I/O:

\[
N\approx4(1+75/25)=16\text{ threads}.
\]

**Không mặc định đặt pool=16**: công thức giả định các task độc lập, không nghẽn ở DB/API và không tạo tranh chấp khác. Nếu external API chỉ cho phép 8 requests đồng thời, hoặc JDBC pool đang cạn, 16 threads có thể là quá nhiều.

Với container Kubernetes, nên dùng **CPU quota/cgroup capacity thực cấp cho pod**, không lấy `Runtime.availableProcessors()` rồi giả định toàn bộ node CPU luôn thuộc về batch khi cấu hình không tương ứng.

### 7.2. Little's law: concurrency từ throughput và latency

Với một tầng hệ thống ổn định:

\[
L=\lambda\times T,
\]

trong đó:

- `L`: số request/chunk in-flight trung bình.
- `\lambda`: tốc độ hoàn tất request/chunk mỗi giây.
- `T`: thời gian request/chunk ở **đúng ranh giới đo** (giây).

Nếu cần 50 chunk/s và mỗi chunk xử lý trên worker mất trung bình 0,2 s, số chunk đang xử lý trung bình cần khoảng:

\[
L=50\times0,2=10.
\]

Đây không phải số consumer chính xác để cấu hình production, vì có biến động p95/p99, retries, queue wait, broker latency và headroom. **Đừng đưa queue waiting time vào `T` rồi coi toàn bộ `L` là số threads cần tạo**; cần phân biệt in-flight tại worker với message/task chỉ đang chờ.

### 7.3. Giới hạn hiệu quả là min của nhiều trần

Một cách nhìn thực dụng:

\[
C_{\mathrm{effective}}\le
\min(
C_{\mathrm{ready\ work}},
C_{\mathrm{executor}},
C_{\mathrm{framework}},
C_{\mathrm{CPU/IO}},
C_{\mathrm{DB/API}},
C_{\mathrm{broker}}
).
\]

Biểu thức là mô hình khái niệm, không phải công thức để cộng trừ đơn vị khác nhau trực tiếp. Khi kiểm chứng bằng metrics, phải chuyển từng giới hạn về cùng **đơn vị công việc/concurrency tại ranh giới đang đo**.

Nếu database đã đạt trần IOPS, tăng thread pool sẽ không làm `C_DB/API` tăng. Nếu có 4 partitions mà executor 32 threads, `C_ready work` chỉ tối đa 4.

## 8. Từ SLA tới worker count

Giả sử một job cần xử lý **1.200.000 item**. Cửa sổ end-to-end là 40 phút, trong đó dành 5 phút cho chuẩn bị, 5 phút cho validate/publish và **30 phút cho xử lý**.

Throughput bắt buộc trong 30 phút:

\[
R_{\mathrm{required}}=
\frac{1.200.000}{30\times60}
\approx667\text{ item/s}.
\]

Baseline một worker đạt **120 committed items/s**, số worker lý tưởng nếu scale tuyến tính:

\[
C_{\mathrm{ideal}}=
\left\lceil\frac{667}{120}\right\rceil=6.
\]

Nhưng sáu worker chỉ có trần lý tưởng `6×120=720` item/s — biên dự phòng nhỏ, và throughput thường không scale tuyến tính.

### 8.1. Một benchmark giả định

| Concurrent workers | Committed throughput (items/s) | p95 chunk latency | JDBC pending | Đánh giá |
| ---: | ---: | ---: | ---: | --- |
| 1 | 120 | 1,8 s | 0 | Baseline |
| 2 | 235 | 1,9 s | 0 | Gần tuyến tính |
| 4 | 455 | 2,1 s | 0 | Còn headroom |
| 6 | 610 | 2,8 s | 1 | Chưa đạt yêu cầu 667 |
| 8 | 690 | 3,6 s | 3 | Đạt sát yêu cầu, ít recovery buffer |
| 10 | 708 | 5,4 s | 7 | Gần bão hòa DB |
| 12 | 680 | 8,0 s | 11 | Thêm workers lại giảm throughput |

Đây là **số liệu giả định minh họa**, không phải benchmark Spring Batch. Với mức 8 worker, thời gian item processing lý tưởng theo throughput đo được:

\[
T\approx \frac{1.200.000}{690}
\approx1.739\text{ s}\approx29\text{ phút}.
\]

Nó còn khoảng một phút trong phần 30 phút xử lý, chưa chắc đủ để xử lý retry hoặc một worker restart. Không nên công bố rằng SLA đã “an toàn” chỉ vì chạy mẫu một lần đạt 29 phút.

Để có thêm 20% công suất dự phòng so với throughput tối thiểu, đích thiết kế có thể là khoảng `667/0,8≈834` item/s. Bảng benchmark cho thấy tăng đến 12 worker **không đạt** đích này. Giải pháp tiếp theo nên là tối ưu truy vấn/transaction, tăng năng lực DB có kiểm chứng, giảm chi phí API hoặc điều chỉnh work window, **không chỉ tiếp tục tăng threads**.

### 8.2. Xem xét tài nguyên trước khi chọn C

Giả sử workload này còn các giới hạn:

- 8 CPU cores hiệu dụng cho batch pod pool.
- DB có ngân sách 24 connection cho workers.
- Mỗi worker có thể cùng lúc cần tối đa hai JDBC connections trong implementation đang dùng.
- API giới hạn 30 requests in-flight.
- Có 16 logical partitions sẵn sàng.

Từ connection budget, số worker tối đa **bảo thủ** là khoảng `floor(24/2)=12` nếu một worker thực sự có thể giữ hai connections đồng thời và mọi worker cùng chạm DB. Nhưng muốn yêu cầu 834 item/s, nếu mỗi item gọi API tốn trung bình 50 ms thì theo Little's law:

\[
L_{\mathrm{API}}\approx834\times0,05=41,7
\]

requests in-flight trung bình, **vượt giới hạn API=30**. Khi đó mục tiêu throughput không khả thi với một API request/item và latency ấy, dù có bao nhiêu executor threads. Cần thay chiến lược API, giảm latency, batching/cache hợp lệ, xin thêm quota hoặc điều chỉnh SLA.

Các giới hạn này là **giả định kiểm tra năng lực**, không phải con số tốt nhất áp dụng cho mọi hệ thống.

## 9. Chunk size và worker count: tune hai chiều riêng

Với worker `chunk(200)`, 8 worker đồng thời không có nghĩa 1.600 item được commit trong **một transaction chung**. Mỗi worker chunk có transaction riêng. Nếu mỗi partition worker step xử lý các chunk tuần tự, có thể có khoảng tám chunk transactions đồng thời, tùy resource/lifecycle.

| Thay đổi | Lợi ích tiềm năng | Rủi ro |
| --- | --- | --- |
| Tăng chunk size | Ít commit/log overhead hơn, JDBC batch lớn hơn | Memory, transaction duration, lock, rollback scope tăng |
| Tăng worker count | Che I/O wait, dùng thêm cores | DB/API contention, thread safety, queue/retry pressure |
| Tăng partition count | Cân bằng skew, giữ worker luôn có việc | Metadata/startup overhead, restart plan phức tạp |
| Tăng JDBC pool | Giảm thời gian chờ mượn connection nếu DB còn capacity | DB CPU/IOPS/lock có thể bão hòa |
| Tăng broker consumers | Drain queue nhanh nếu worker+DB còn dư | API/DB quotas, redelivery và correlation tăng |

Khi benchmark, **giữ chunk size cố định** và thử các mức workers 1/2/4/8 trước, rồi mới thay chunk size theo hiệu quả transaction. Nếu thay mọi tham số cùng lúc, khó xác định nguyên nhân throughput thay đổi.

### 9.1. Buffer memory tăng theo concurrency

Ví dụ mỗi item sau xử lý chiếm trung bình 8 KiB, chunk size 500, concurrency 12:

\[
M_{\mathrm{payload}}\approx
12\times500\times8\text{ KiB}
=48.000\text{ KiB}\approx46,9\text{ MiB}.
\]

Đây mới là payload logic, **chưa tính** object overhead, input/processed copies, reader buffers, transaction resources, JDBC driver, serialization và GC. Nếu item là ảnh/JSON lớn hơn nhiều, concurrency có thể làm JVM OOM trước khi CPU/DB đạt trần.

### 9.2. Partition count cao không phải concurrency cao

Nếu `P=1.000` partition nhưng executor có 8 threads, số worker StepExecution đồng thời của executor vẫn giới hạn khoảng 8. Phần còn lại sẽ xếp lịch tuần tự qua nhiều đợt. Quá nhiều partition nhỏ có thể làm `StepExecution`, `ExecutionContext`, reader open/close và JobRepository metadata overhead chiếm phần lớn thời gian. Vì vậy tuning pool luôn cần kết hợp độ hạt partition hợp lý.

## 10. Thread safety khi tăng workers

Tăng số thread trong cùng JVM làm thay đổi giả định về shared mutable state.

### 10.1. Reader, processor, writer

| Thành phần | Vấn đề khi cùng instance được gọi đồng thời | Biện pháp |
| --- | --- | --- |
| `ItemReader` stateful | Cursor, page index hoặc buffer bị data race | Chứng minh thread-safe; đồng bộ `read` khi phù hợp hoặc chia partition/reader riêng |
| `ItemProcessor` | Mutable counters, cache, `currentItem` | Stateless/immutable, thread-safe clients |
| `ItemWriter` | Shared buffer, transaction state hoặc update cùng row | Thread-safe implementation, DB transaction, unique key/version |
| Listeners | Counter, mutable diagnostic state | Metrics concurrent-safe, log theo StepExecution |
| `ExecutionContext` | Nhiều threads ghi cùng key không có hợp đồng | Không tự sửa state chung ngoài lifecycle đã thiết kế |
| HTTP clients | Pool/rate limit nhỏ, không thread-safe | Client đúng hợp đồng, bounded in-flight và timeout |

Ví dụ **không an toàn**:

~~~java
public final class UnsafeProcessor
        implements ItemProcessor<InputRow, OutputRow> {

    private long processed; // không đồng bộ, không transaction-aware

    @Override
    public OutputRow process(InputRow row) {
        processed++;
        return transform(row);
    }
}
~~~

Thay `long` bằng `AtomicLong` chỉ sửa một loại data race, **không** khiến counter trở thành số item đã commit. Counter có thể tăng trước rollback/retry, bị reset khi JVM restart và không đối chiếu với output.

### 10.2. StepScope theo StepExecution, không theo thread

Với multi-threaded step, nhiều chunk threads thường dùng **cùng StepExecution**, nên `@StepScope` không tự tạo instance reader riêng cho từng thread. Với partitioning, từng partition có **StepExecution riêng**; một reader `@StepScope` sẽ có context riêng theo partition, thuận lợi hơn cho checkpoint. Singleton writer/service dùng chung vẫn phải được kiểm chứng thread safety.

### 10.3. Thứ tự commit không còn bảo đảm

Hai chunks hoặc hai partitions có thể commit đảo thứ tự. Nếu cùng account được cập nhật phiên bản 1 và 2 bởi hai workers, bản cũ commit sau có thể ghi đè kết quả mới. Cần partition theo key, optimistic locking/version checks hoặc quy tắc nghiệp vụ phù hợp; không dựa vào thứ tự reader trả item.

### 10.4. Idempotency là điều kiện của retry/restart

Ví dụ `UPDATE balance = balance + amount` không idempotent: worker bị retry có thể cộng tiền hai lần. Với kết quả xác định theo business key, dùng unique constraint và upsert theo source version khi hợp lệ. Side effect ngoài transaction DB phải có idempotency key/outbox hoặc cơ chế bù trừ/đối soát.

**Worker count cao không biến một tác vụ không idempotent thành an toàn.** Nó tăng khả năng các race/lock/timeouts xảy ra và khó tái lập hơn.

## 11. Deadlock và starvation do cấu hình pool

### 11.1. Thread starvation

Giả sử một executor có 4 threads. Mỗi task giữ thread rồi submit một tác vụ con **vào chính executor đó**, sau đó gọi `future.get()` để đợi. Nếu cả 4 task cha đang chờ, không còn thread rảnh chạy tác vụ con. Các tác vụ con nằm trong queue và hệ thống có thể **kẹt vĩnh viễn**.

~~~text
Pool max = 4
thread-1: parent A -> waits child A (queued)
thread-2: parent B -> waits child B (queued)
thread-3: parent C -> waits child C (queued)
thread-4: parent D -> waits child D (queued)

No free thread to execute children -> starvation deadlock
~~~

Giải pháp: không thiết kế nested blocking submission vào cùng pool cạn threads; có thể tách executor, dùng xử lý không blocking hoặc bảo đảm số thread/queue/timeout với mô hình được chứng minh.

### 11.2. Giữ JDBC connection trong khi chờ external I/O

Nếu transaction lấy DB connection rồi gọi HTTP API mất 3 giây, 8 workers có thể giữ hết 8 connections trong lúc DB CPU thấp. Các worker khác chờ mượn connection, job chạy chậm. Không đơn giản tăng pool lên 50 nếu DB bị giới hạn.

Cần kiểm tra transaction boundary, có thể tách call API khỏi vùng giữ JDBC connection nếu mô hình retry/idempotency cho phép. Một thay đổi transaction scope phải được xem xét kỹ vì failure giữa API và DB có thể làm trạng thái hai hệ thống lệch nhau.

### 11.3. Overlapping scheduled jobs

Hai job chạy trùng cửa sổ, mỗi job có pool max=12, sẽ có thể tạo đến 24 executor threads trên cùng pod — chưa kể Step threads, framework infrastructure và application threads. Nếu cả hai cùng dùng Hikari pool max=12 và DB quotas nhỏ hơn, chúng có thể tranh connection lẫn nhau và làm tăng deadline miss.

Cần admission control ở tầng scheduler, ngân sách concurrency theo JobInstance hoặc tách workload theo ưu tiên. Không chỉ dựa vào mỗi job có “pool riêng đúng kích thước”.

## 12. Backpressure xuyên nhiều tầng

**Backpressure** là cách hạn chế tốc độ sinh công việc khi downstream đang xử lý chậm, tránh biến lượng đợi thành backlog vô hạn.

~~~mermaid
flowchart LR
    M["Manager dispatch"] --> Q["Bounded task/request queue"]
    Q --> W["Bounded workers"]
    W --> D["DB / HTTP / Broker capacity"]
    D --> W
    W --> A["Completion / reply / commit"]
    A --> M
~~~

Trong multi-threaded step/local partitioning, `ThreadPoolTaskExecutor` có queue giới hạn tạo một lớp admission. Nhưng nếu tầng step liên tục submit hoặc số task pending lớn, vẫn phải hiểu cách framework xử lý rejection và giới hạn repeat operations.

Trong remote chunking, manager cần giới hạn **số chunk requests in-flight** và độ sâu backlog; mỗi worker replica cần giới hạn consumer concurrency/prefetch và DB connections. Trong remote partitioning, số partition request cần được giới hạn/điều phối cùng worker capacity và JobRepository.

### 12.1. Điều không phải backpressure hiệu quả

- Queue không giới hạn và không có alert.
- Retry vô hạn khi API trả 429 hoặc DB timeout.
- Autoscale pods theo queue depth mà không tính DB connection budget.
- Tăng `maxPoolSize` liên tục vì thấy queue vẫn còn.
- Bỏ qua rejected tasks rồi để job báo thành công.
- Sử dụng broker prefetch lớn và tưởng đã có nhiều consumers.

### 12.2. Điều có ích

- Bounded executor queue và cách xử lý rejection rõ ràng.
- Giới hạn requests in-flight bằng semaphore/bulkhead/rate limiter khi phù hợp.
- Exponential backoff với jitter cho lỗi transient, retry budget hữu hạn.
- Autoscale có **trần global downstream budget**.
- Đo queue age, không chỉ queue length.
- Tách workload ưu tiên để job khẩn không bị starvation.
- Stop/fail có thể quan sát được thay vì âm thầm drop work.

## 13. Thread pool có giải quyết vấn đề CPU cores không?

Không. Pool là cách điều phối các tác vụ Java; năng lực xử lý CPU do core/quota, cache, memory bandwidth, GC và việc dùng SIMD/vectorization/algorithm quyết định.

### 13.1. CPU-bound

Nếu một JVM được cấp 4 cores và đang ở gần 400% CPU host-equivalent hoặc CPU quota cgroup bão hòa, tăng từ 4 lên 16 runnable platform threads không làm xuất hiện 12 cores mới. Có thể có lợi nhỏ do chờ I/O ngắn, nhưng cũng có thể giảm throughput vì context switch.

### 13.2. Blocking I/O-bound

Nếu threads phần lớn chờ network, pool có thể lớn hơn số cores khi DB/API còn capacity. Nhưng cần tách:

- **Chờ có thể chồng lấp hữu ích:** external API trả lời độc lập, quota còn dư.
- **Chờ tài nguyên khan hiếm:** Hikari pending do connections cạn, DB lock wait dài.
- **Chờ do lỗi:** retry/backoff, dead-letter, broker outage.

Chỉ trường hợp thứ nhất thường hưởng lợi rõ từ thêm concurrency. Hai trường hợp sau thường cần sửa bottleneck ở nguồn/đích hoặc admission.

### 13.3. Virtual threads không tạo thêm downstream capacity

Với Java 21+, virtual threads có thể giúp giảm chi phí duy trì nhiều hoạt động **blocking I/O** trong một số cấu hình. Tuy nhiên:

- Không làm CPU-bound work chạy vượt core/quota.
- Không tạo thêm JDBC connections hoặc tăng API quota.
- Không tự sửa thread safety hay checkpoint/restart.
- Không thay thế việc đặt giới hạn in-flight và backpressure.
- Cần kiểm tra tương thích của Spring Batch, Spring Framework, thư viện/driver và cơ chế blocking thực tế.

Bài dùng `ThreadPoolTaskExecutor` platform threads làm baseline dễ vận hành cho Spring Batch 5.2.x/Java 17+. Nếu dùng virtual threads, hãy đánh giá theo phiên bản Java/Spring cụ thể và giữ semaphore/rate limiter để tránh oversubscribe database.

## 14. Worker count và restartability

Nhiều workers giúp throughput cao hơn nhưng **phạm vi lỗi và checkpoint** thay đổi theo mô hình.

| Mô hình | Khi một worker gặp lỗi | Việc cần kiểm chứng |
| --- | --- | --- |
| Multi-threaded step | Một chunk lỗi/rollback trong StepExecution chung | Shared reader state và out-of-order commit có làm mất/trùng item không? |
| Local partitioning | Một partition StepExecution `FAILED` | Restart đúng partition, context/reader state bất biến |
| Remote partitioning | Worker pod chết giữa StepExecution | Worker cũ đã dừng, JobRepository status chính xác, không có hai thế hệ cùng làm |
| Remote chunking | Worker đã ghi nhưng reply/ACK mất | Request redelivery không tạo duplicate effect; manager correlation chính xác |
| Parallel steps | Một branch thất bại | Các branch completed có bị chạy lại hay gây side effect không? |

### 14.1. Bẫy “scale lên trong lúc restart”

Giả sử manager tạo 32 partition và 8 workers; một partition lỗi. Khi restart, có thể tăng worker pods lên 16 để phục hồi nhanh hơn **nhưng không đổi tên/phạm vi của 32 partition đã có**. Tên partition và `ExecutionContext` được dùng để đối chiếu với `JobRepository`.

Đổi `gridSize`, số shard và mapping theo số workers mới trong cùng JobInstance có thể làm checkpoint sai hoặc dữ liệu chồng lấn. Scaling capacity thực thi khác với repartition một snapshot.

### 14.2. Worker cũ đang chạy

Nếu manager gặp timeout nhưng một worker remote vẫn đang ghi DB, tạo worker mới cho cùng partition mà không kiểm tra có thể gây **double execution**. Dùng liveness/ownership, fencing tokens khi cần, idempotent writer và runbook trước restart. Không sửa trực tiếp `BATCH_STEP_EXECUTION.STATUS` để “đánh dấu completed” khi chưa đối soát.

### 14.3. Graceful shutdown

Khi deploy/scale down:

1. Dừng nhận work mới theo cơ chế listener/scheduler.
2. Cho chunk/partition đang xử lý cơ hội hoàn tất hoặc bị stop theo hợp đồng Spring Batch.
3. Chờ bounded thời gian và ghi lại trạng thái/timeout.
4. Không để message ACK sớm trong khi business output chưa commit.
5. Nếu phải kill process, restart dựa trên metadata + idempotency, không suy rằng mọi công việc chưa commit đều chưa có side effect.

`ThreadPoolTaskExecutor` có cấu hình lifecycle như `setWaitForTasksToCompleteOnShutdown` và `setAwaitTerminationSeconds`, nhưng cách dùng phải phù hợp với termination/grace period thực tế. Không coi gọi `shutdown()` là đã bảo đảm mọi remote worker cũng dừng.

## 15. Quan sát: phải đo hiệu quả chứ không chỉ đếm threads

Các metric nên thu thập ở **cả executor, Batch, datasource và downstream**:

| Tầng | Metric | Dấu hiệu |
| --- | --- | --- |
| Executor | `poolSize`, `activeCount`, queue size, completed tasks, rejected tasks | Pool có bão hòa, queue tăng hay bị starvation? |
| Spring Batch | `readCount`, `writeCount`, `commitCount`, `rollbackCount`, skip/retry | Tiến độ có bền vững hay đang rollback liên tục? |
| Throughput | **Committed items/s** và bytes/s | Tăng threads có tăng output thật không? |
| Chunk latency | p50/p95/p99, thời gian đọc/xử lý/ghi/commit | Bottleneck nằm ở đâu, tail có xấu đi không? |
| HikariCP | Active/idle/pending, acquire latency, timeout count | Threads chờ connection hay DB đang căng? |
| Database | CPU, IOPS, lock waits, query latency, WAL/redo, transaction time | DB đã đến điểm saturation? |
| HTTP | In-flight, latency p95/p99, 429/503, retry rate | Quota/rate limit có ngăn scale? |
| Broker | Ready/unacked messages, oldest age, redeliveries, DLQ, reply lag | Remote workers hay routing đang chậm? |
| JVM/OS | CPU quota, RSS/heap, GC pauses, thread count, context switches | Có oversubscribe CPU/memory? |
| Data quality | Unique business keys, missing keys, totals/checksums | Có sai dữ liệu do race/restart không? |
| SLA | Remaining work, ETA, processing window, recovery buffer | Đã đạt throughput bền vững chưa? |

Tên metric Micrometer/Actuator cụ thể phụ thuộc phiên bản và instrumentation được bật. `ThreadPoolTaskExecutor` có thể cung cấp các số liệu pool, nhưng không phải mọi executor hoặc broker đều tự xuất metric giống nhau. Gắn `jobExecutionId`/`stepExecutionId` và tên partition vào log/traces khi cần điều tra, tránh metric label với từng item ID vì cardinality lớn.

### 15.1. Cần nhìn đồng thời queue và throughput

| Executor active | Queue depth | Committed throughput | Khả năng |
| --- | --- | --- | --- |
| Thấp | Cao | Thấp | Dispatch/pool config hạn chế, tasks kẹt, thread starvation |
| Cao | Cao | Thấp | Threads đang chờ DB/API/lock hoặc retry nhiều |
| Cao | Gần 0 | Cao | Pool bận và work được tiêu thụ đều |
| Thấp | Gần 0 | Thấp | Không đủ work, reader/manager dispatch chậm hoặc job gần hoàn tất |
| Cao | Cao | Cao nhưng p99 tăng | Có nguy cơ backlog/timeout, cần kiểm tra SLA và recovery |

Không thể kết luận chỉ từ một hàng của bảng; cần thêm CPU, DB waits, pending pool và retry. Ví dụ active=8 không chứng minh có 8 workers hữu ích nếu cả 8 đều đang block tại `getConnection()`.

### 15.2. ETA nên tính theo work còn lại

Một ETA cơ bản:

\[
ETA_{\mathrm{seconds}}\approx
\frac{\text{remaining valid items}}
     {\text{recent committed items per second}}.
\]

Khi partition bị skew, ETA trung bình có thể quá lạc quan nếu chỉ còn một shard rất lớn đang chạy tuần tự. Khi tính deadline cần cộng validation/publish và recovery buffer, đo longest-running partition và có cảnh báo **at-risk** trước khi job `FAILED`.

## 16. Kế hoạch benchmark lựa chọn worker count

Thực hiện theo thứ tự để giảm nhiễu:

1. **Chốt snapshot dữ liệu** và kỳ vọng output (ID/tổng/checksum) độc lập.
2. **Chạy 1 worker** để đo per-chunk CPU, I/O, DB connection hold time và baseline committed throughput.
3. **Chọn chunk size cố định**, ví dụ 200, chưa tăng cùng lúc.
4. **Quét concurrency 1 → 2 → 4 → 6 → 8 → 10**, giữ cùng workload, cùng DB load nền.
5. Với từng mức, ghi tổng thời gian, p95/p99, Hikari pending, CPU, locks, retries và output reconciliation.
6. Xác định điểm throughput bắt đầu tăng ít, latency/timeout tăng nhanh — **điểm bão hòa thực tế**.
7. Nếu dùng partitioning, thử partition count `P` độc lập với worker concurrency `C` để giảm skew nhưng không quá nhiều partition nhỏ.
8. Chạy thử **peak data**, skew, backfill, nhiều job chồng cửa sổ và lỗi downstream.
9. Kiểm thử **process crash/restart**, đảm bảo tăng concurrency không gây duplicate/missing business effects.
10. Chọn cấu hình đạt deadline **với headroom**, ghi giả định tài nguyên và runbook scale down.

### 16.1. Một bảng thí nghiệm mẫu

| Run | Chunk size K | Partition count P | Concurrent workers C | Ghi chú cần đo |
| --- | ---: | ---: | ---: | --- |
| A | 200 | 32 | 1 | Baseline |
| B | 200 | 32 | 2 | Throughput có gần gấp đôi? |
| C | 200 | 32 | 4 | DB/pool bắt đầu căng chưa? |
| D | 200 | 32 | 8 | p95/p99 và retry có tăng mạnh? |
| E | 200 | 64 | 8 | Partition mịn hơn có giảm skew? |
| F | 500 | 64 | 8 | Commit overhead giảm nhưng memory/lock ra sao? |

Chỉ nên so throughput giữa các run khi input và các điều kiện ngoài được kiểm soát. Nếu nhiều run ghi lên cùng output bảng, phải có snapshot/output namespace hoặc reset có kiểm soát; không để kết quả cũ làm benchmark nhanh giả.

### 16.2. Đo đúng điểm kết thúc

Job thành công kỹ thuật chưa đủ:

~~~text
Completed item count and distinct business IDs
    == expected snapshot values

No missing IDs
No duplicate business side effects
No stale-version overwrites
Restarted run final output == clean-run final output
SLA including validation/publish/recovery budget is met
~~~

`readCount` có thể tăng vì retry rồi rollback, nên không dùng riêng `readCount/s` làm throughput đã xử lý bền vững.

## 17. Kịch bản xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Hành động điều tra trước khi tune |
| --- | --- | --- |
| `maxPoolSize` tăng nhưng pool chỉ có core threads | Queue dương còn chỗ; executor ưu tiên queue | Xem `corePoolSize`, queue depth, submit rate |
| Active threads cao, CPU thấp, Hikari pending cao | Threads chờ JDBC connections | Đo connection hold time, DB wait, tối ưu transaction/pool budget |
| CPU quota luôn đầy, throughput giảm khi tăng threads | CPU-bound oversubscription | Giảm concurrency, tối ưu algorithm hoặc cấp thêm CPU |
| Broker queue sâu, workers rảnh | Routing/consumer/prefetch/deserialization lỗi | Kiểm tra listener, queue binding, consumer health |
| Broker queue sâu, workers bận, DB locks cao | Writer DB là bottleneck | Giảm in-flight, tối ưu SQL/index/lock |
| p99 chunk latency tăng mạnh | Contention, GC, slow external calls | Phân tích thread dumps, DB/APM traces và GC |
| Thread pool rejected tasks | Pool + queue bão hòa | Admission/backpressure, xử lý lỗi rõ, không drop work |
| Worker pod tăng nhưng DB timeout tăng | Tổng connection quota bị vượt | Tính `replicas × pool per pod` và tải nền |
| Một partition chạy mãi dù threads rảnh | Partition skew hoặc hot key | Kiểm tra shard size, plan và per-partition metrics |
| Job restart thiếu/trùng item | Reader/ExecutionContext không an toàn, writer không idempotent | Dừng publish, đối soát checkpoint và output |
| Scale down gây duplicate requests | Worker ACK/reply/commit không đồng bộ | Xem broker redelivery, idempotency, graceful shutdown |

### 17.1. Runbook tăng concurrency an toàn

- Ghi lại cấu hình hiện tại và số đo baseline.
- Kiểm tra còn CPU/DB/API headroom thật, xác định bottleneck.
- Thay **một tham số** nhỏ (ví dụ worker 4 → 6), canary trên snapshot đại diện.
- Theo dõi queue depth/age, throughput commit, p99, Hikari pending, rollback/retry.
- So sánh output correctness và restart test.
- Nếu throughput không tăng hoặc lỗi nhiều hơn, rollback cấu hình về mức cũ.
- Khi đổi số remote workers giữa các lần restart, giữ partition plan, names và ExecutionContext ổn định.

## 18. Những hiểu nhầm phổ biến

| Khẳng định | Điều cần sửa |
| --- | --- |
| “Pool max=32 nghĩa có 32 threads chạy ngay.” | Queue có thể hấp thụ task trước khi pool tăng vượt core. |
| “Queue capacity=100 nghĩa concurrency=100.” | Queue giữ task chờ, không làm task chạy song song. |
| “gridSize=64 nghĩa có 64 workers.” | Grid size là hint số partition, worker concurrency là biến khác. |
| “Chunk size=1000 nghĩa có 1000 threads.” | Chunk size là ranh giới commit của item. |
| “8 worker thì cần đúng 8 JDBC connections.” | Reader/writer/JobRepository có thể cần nhiều connection hoặc giữ lâu. |
| “Tăng threads luôn làm job nhanh hơn.” | Chỉ khi chưa bão hòa CPU/DB/API và work thực sự độc lập. |
| “@StepScope làm reader riêng cho mỗi chunk thread.” | Scope theo StepExecution, không theo thread. |
| “Prefetch=100 nghĩa 100 consumers đang xử lý.” | Prefetch chỉ là số message broker có thể giao trước. |
| “Autoscale pods không ảnh hưởng database.” | Tổng JDBC pools và transaction concurrency tăng theo replicas. |
| “AtomicLong counter bằng số item đã commit.” | Rollback/retry có thể khiến counter lệch và mất khi restart. |
| “Thread pool giới hạn là đủ backpressure toàn hệ thống.” | Có thể còn broker backlog, JDBC pending, API queues và retries. |
| “Virtual threads sẽ sửa mọi bottleneck.” | Không tạo thêm CPU, DB connection hoặc quota API. |
| “Job COMPLETED nghĩa worker count tối ưu.” | Phải xem SLA headroom, throughput, cost và dữ liệu đúng. |

## 19. Checklist trước production

- [ ] Đã xác định rõ worker count theo **mô hình execution cụ thể**.
- [ ] Có baseline committed throughput và SLA xử lý end-to-end.
- [ ] `corePoolSize`, `maxPoolSize` và `queueCapacity` được cấu hình có giới hạn, hiểu điều kiện tăng thread/rejection.
- [ ] Không đồng nhất `gridSize`, partition count, chunk size và worker concurrency.
- [ ] Đã tính giới hạn CPU/quota, RAM, JDBC pool và API/broker cho **toàn bộ cluster**.
- [ ] Reader/processor/writer/listeners an toàn khi đồng thời trong phạm vi dùng chung.
- [ ] Worker StepExecution dùng context riêng theo partition khi cần tách state.
- [ ] Checkpoint/restart được test sau rollback và process crash.
- [ ] Writer idempotent hoặc có biện pháp chống side effect lặp.
- [ ] Có queue/backpressure/rate limit, retry hữu hạn và DLQ đối với remote topology.
- [ ] Đã thử C=1/2/4/8 với chunk size và input cố định, đo điểm bão hòa.
- [ ] Đã đo p95/p99 chunk latency, Hikari pending, DB lock, GC và queue age.
- [ ] Đã thử nhiều job chạy cùng lúc, peak/backfill và partition skew.
- [ ] Có alert ETA at-risk, retry storm, pool exhaustion, rejected tasks.
- [ ] Có runbook tăng/giảm concurrency, graceful shutdown, fencing worker cũ và rollback cấu hình.
- [ ] Không thay đổi partition identity/manifest chỉ để tăng worker count khi restart.

## 20. Câu hỏi tự kiểm tra

1. Vì sao `maxPoolSize=32` nhưng executor có thể vẫn chỉ chạy 4 threads?
2. `queueCapacity=20` có nghĩa executor chạy thêm 20 tasks đồng thời không?
3. Với 40 partitions, executor local 8 threads và `chunk(500)`, tối đa khoảng bao nhiêu worker StepExecution đang hoạt động?
4. Khi nào nên dùng nhiều threads hơn CPU cores? Khi nào điều đó có thể gây hại?
5. `@StepScope` có tạo reader riêng cho từng chunk thread trong một multi-threaded step không?
6. Nếu có 6 worker pods, mỗi pod dùng Hikari pool max=10, manager pool max=8, tổng trần cấu hình là bao nhiêu?
7. Cần 50 chunk/s, worker processing latency trung bình 0,2s: số chunk in-flight trung bình theo Little's law là bao nhiêu?
8. Một executor active=12, CPU thấp nhưng Hikari pending lớn. Nên điều tra gì trước khi tăng thêm threads?
9. Vì sao remote chunking `prefetch=100` không tạo ra 100 worker threads?
10. Nếu có 4 partitions nhưng 32 remote worker replicas, có thể có 32 StepExecution hữu ích chạy cùng lúc không?
11. Chunk size tăng từ 200 lên 1.000 có thể giúp và gây hại theo những cách nào?
12. Một worker được retry sau khi đã gửi email thành công nhưng trước khi cập nhật checkpoint. Làm sao tránh gửi hai email?
13. Vì sao tăng số pods mà không tính tổng DB connections có thể làm throughput giảm?
14. Một job đạt 667 items/s nhưng SLA cần 667 items/s và thường có restart 3–5 phút. Có đủ headroom không?
15. Vì sao thay `gridSize` và mapping partition trong lần restart cùng JobInstance có thể nguy hiểm?
16. Đâu là ba metric nên xem đầu tiên khi tăng threads mà throughput không tăng?
17. Vì sao `readCount`/giây không phải metric duy nhất để đánh giá tăng tốc?
18. Nên kiểm thử điều gì khi dùng chung một executor cho nhiều jobs cùng cửa sổ?

**Gợi ý trả lời:** (1) Với queue dương, task thường được queue trước khi pool vượt core. (2) Không, nó chứa tasks chờ. (3) Khoảng tám, tùy cơ chế dispatch. (4) Blocking I/O còn headroom; gây hại khi CPU/DB/API bão hòa. (5) Không, scope theo StepExecution. (6) `6×10+8=68`. (7) 10. (8) Connection hold/acquire time, DB locks và transaction boundaries. (9) Prefetch là outstanding deliveries, không phải consumers. (10) Không nếu chỉ bốn partition sẵn sàng. (11) Giảm commit overhead nhưng tăng memory/lock/rollback scope. (12) Idempotency key/outbox hoặc dedupe ở hệ thống đích. (13) `replicas × pool` có thể vượt ngân sách và tăng lock contention. (14) Không, còn phải trừ recovery/validation buffer. (15) Metadata/checkpoint gắn với identity plan cũ. (16) Executor queue/active, DB pool pending/locks, CPU/API latency. (17) Retry/rollback và read-ahead có thể không tạo output đã commit. (18) Starvation/fairness, tổng concurrency, shared DB/CPU và behavior khi một job giữ hết threads.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel flows, partitioning, remote processing.
- [Spring Batch 5.2 Reference — Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): cấu hình local/remote concurrency và lưu ý `throttleLimit`.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `ThreadPoolTaskExecutor` và cơ chế chạy task.
- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): `corePoolSize`, `maxPoolSize`, `queueCapacity` và monitoring.
- [Java SE — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): chính sách queue và thread creation/rejection.
- [Spring Batch Reference — Step Scope and Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope` và ExecutionContext.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và restart.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): tại sao số DB connection lớn hơn không đồng nghĩa throughput cao hơn.

**Điểm cốt lõi:** **Thread pool là cơ chế điều phối; worker count là concurrency thực tế của đúng loại công việc; resource pool của database/API lại là giới hạn khác.** Hãy phân biệt core/max/queue với `gridSize` và chunk size, tăng mức đồng thời theo throughput/SLA nhưng luôn tính tổng CPU, JDBC connections, broker/API quotas trên toàn cluster. Một cấu hình tốt không phải cấu hình có nhiều threads nhất, mà là cấu hình **hoàn tất công việc đúng dữ liệu, có restart an toàn, còn headroom khi sự cố và không làm các tài nguyên chung bão hòa**.
