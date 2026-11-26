# Đặc điểm single-process nhiều luồng khi mở rộng Spring Batch

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích mô hình **single-process, multi-threaded**: một JVM chứa nhiều thread, chia sẻ heap và tài nguyên nhưng mỗi thread có ngữ cảnh điều khiển riêng.
- Phân biệt multi-threaded step, parallel steps và local partitioning trong **một process** với remote partitioning/chunking trên nhiều process.
- Phát hiện race condition, vấn đề visibility, reader không thread-safe, transaction gắn với thread và lỗi checkpoint.
- Cấu hình `TaskExecutor` có giới hạn, phân bổ state theo `StepExecution` và đo contention của JDBC connection pool, CPU, bộ nhớ, I/O.
- Thiết kế retry/restart và writer idempotent để một JVM chết không làm hỏng kết quả các chunk đã commit.
- Nhận biết khi nào đa luồng cục bộ vẫn hiệu quả và khi nào cần đổi thuật toán hoặc scale-out.

## 1. Single-process nhiều luồng là gì?

**Single-process** trong bối cảnh Java/Spring Batch là một tiến trình hệ điều hành chạy **một JVM**. Trong JVM đó, nhiều Java thread có thể xử lý các phần việc đồng thời; chúng chạy song song thực sự khi có đủ CPU core và được scheduler hệ điều hành cấp thời gian xử lý.

Các thread trong một process **dùng chung heap**, nơi chứa Spring bean singleton, cache, `DataSource`, connection pool và nhiều object ứng dụng. Mỗi thread có **stack thực thi riêng** cho lời gọi hàm, biến local và thông tin điều khiển; các giá trị `ThreadLocal` được liên kết riêng với thread. Trong Spring transaction kiểu imperative, ngữ cảnh transaction/JDBC connection thường gắn với **thread thực thi transaction**.

~~~mermaid
flowchart TD
    J["Một process: Spring Batch JVM"] --> H["Heap chung: bean singleton, cache, metrics"]
    J --> E["TaskExecutor: queue + worker pool"]
    E --> T1["Thread A: stack & transaction context riêng"]
    E --> T2["Thread B: stack & transaction context riêng"]
    E --> T3["Thread C: stack & transaction context riêng"]
    T1 --> P1["StepExecution / task A"]
    T2 --> P2["StepExecution / task B"]
    T3 --> P3["StepExecution / task C"]
    T1 --> D["JDBC pool / Business DB"]
    T2 --> D
    T3 --> D
    H -.-> T1
    H -.-> T2
    H -.-> T3
~~~

Hai điều tưởng như trái ngược phải luôn được nhớ:

1. **Thread riêng không có nghĩa dữ liệu riêng.** Nếu các thread cùng tham chiếu một reader singleton có cursor mutable, việc đọc có thể tranh chấp, dù stack từng thread khác nhau.
2. **Chung process không có nghĩa chung transaction.** Một transaction mở trên thread A không tự truyền sang thread B chỉ vì B được tạo bởi executor của cùng JVM.

### Phạm vi của các loại state

| Thành phần | Phạm vi thường gặp | Hệ quả |
| --- | --- | --- |
| Heap, `static` fields, bean singleton | Toàn JVM | Mutable state dùng chung phải có chiến lược thread safety |
| `TaskExecutor`/queue | Các tác vụ cùng dùng pool | Một pool có thể thành nút thắt hoặc gây starvation |
| `DataSource` và pool | Bean/pool được chia sẻ | Thread tranh connection; DB còn quota toàn server |
| CPU quota, RAM, GC | Toàn process/container | Tăng thread không làm tăng CPU core/RAM |
| Thread stack, biến local | Riêng thread hoặc lời gọi | An toàn khi không để reference mutable bị chia sẻ ngoài ý muốn |
| `ThreadLocal`/Spring transaction context | Riêng thread | Không tự lan theo `CompletableFuture`/`@Async` |
| `StepExecution` | Theo lần thực thi step | Một local partition có thể có step execution riêng |
| `StepExecutionContext` | Theo `StepExecution` | Chứa boundary/checkpoint của worker được quản lý đúng |
| `JobExecutionContext` | Theo lần thực thi job | Không xem là map ghi đồng thời vô điều kiện |
| DB row/lock, API quota | Nhiều process cùng chia sẻ | Thread safety trong JVM không đủ bảo đảm nghiệp vụ |

Một process đơn giản giúp giảm chi phí vận hành, nhưng cũng tạo **single failure domain**: JVM dừng bất thường thì mọi worker thread trong JVM dừng theo.

## 2. Lợi ích và giới hạn so với nhiều process

Mô hình nhiều luồng cục bộ thường phù hợp khi một JVM còn CPU/memory, công việc chia được và nguồn/đích chịu được concurrency. Không cần broker để giao việc cho những thread trong cùng process và không cần serialize toàn bộ payload chỉ để chuyển giữa worker cục bộ.

| Ưu điểm | Đánh đổi |
| --- | --- |
| Ít thành phần triển khai hơn worker phân tán | Mọi worker mất cùng lúc nếu JVM crash |
| Tận dụng CPU đa core cho processor độc lập | CPU quota một node vẫn là trần |
| Có thể chồng thời gian chờ I/O giữa các thread | DB/API có thể bão hòa trước ứng dụng |
| Chia sẻ cấu hình, `JobRepository` và dependency Spring | Sai sót singleton mutable có thể ảnh hưởng mọi worker |
| Dễ chẩn đoán bằng JVM metrics và thread dump | GC pause/OOM ảnh hưởng nhiều worker cùng lúc |
| Thử tăng concurrency theo nấc 1, 2, 4, 8 | Thread và queue quá nhiều gây tốn RAM/chờ lock |

**Tăng worker không đồng nghĩa tốc độ tăng tuyến tính.** Nếu một worker tạo 200 request/s đến API giới hạn 500 request/s, bốn worker có thể tạo nhu cầu 800 request/s, nhưng API vẫn chỉ có capacity 500 request/s hoặc thấp hơn dưới tải thật.

## 3. Ba mô hình Spring Batch thường nằm trong một JVM

Single-process nhiều luồng là thuộc tính của **môi trường chạy**, còn Spring Batch có nhiều mô hình tạo concurrency.

| Mô hình | Đơn vị chạy song song | Điểm cần quan tâm |
| --- | --- | --- |
| **Multi-threaded step** | Một step có nhiều phần công việc/chunk/processor chạy song song tùy phiên bản | Reader/writer/state có thể được truy cập đồng thời; semantics transaction theo phiên bản |
| **Parallel steps** | Các `Flow` độc lập, mỗi flow có step riêng | `split` đợi các flow kết thúc trước transition sau join; data dependency phải rõ |
| **Local partitioning** | Manager step giao nhiều partition cho worker step trên thread cục bộ | Mỗi partition có `StepExecution` và `ExecutionContext` riêng; cần phân vùng input chính xác |
| **Task tự tạo bằng `@Async`/`CompletableFuture`** | Runnable/future ứng dụng gửi vào pool | Spring Batch không tự đợi, không tự quản lý lỗi/checkpoint nếu step return sớm |
| **Nhiều `JobExecution` cùng process** | Nhiều lần chạy logic của job | Không có barrier chung mặc định; cạnh tranh toàn bộ tài nguyên JVM/DB |

### Multi-threaded step khác partitioning thế nào?

Với **multi-threaded step**, cấu hình dùng một step để tổ chức các task chạy song song; nhiều thread có thể liên quan đến cùng `StepExecution` và cùng bean reader/writer. Vì vậy cần kiểm chứng chính xác ai sử dụng reader, transaction nào được mở và checkpoint cập nhật ra sao.

Với **local partitioning**, manager chia các miền dữ liệu, ví dụ `[1, 250001)`, `[250001, 500001)`; mỗi miền được chạy như một **worker `StepExecution` riêng**. Reader `@StepScope` trong mỗi worker có thể nhận range riêng từ `stepExecutionContext`, giúp tránh chia sẻ cursor.

Không nhầm một partition với một thread: `gridSize=8` mô tả số partition dự kiến, nhưng executor giới hạn bốn thread có thể khiến các partition phải xếp hàng, không phải tám thread chạy đồng thời.

### Lưu ý về phiên bản Spring Batch

Cơ chế multi-threaded step có khác biệt giữa các release. **Spring Batch 5.2** cho phép xử lý các chunk trên worker thread trong multi-threaded step; ở **Spring Batch 6.1**, mô hình được mô tả với processor thực thi song song trên worker trong khi reader/writer do thread điều khiển step thực hiện. Vì vậy không khẳng định “processor luôn nằm trong chunk transaction” hay “reader luôn chạy trên worker” cho mọi phiên bản. Hãy đối chiếu đúng tài liệu/API của release đang triển khai.

Nguyên tắc không đổi: transaction imperative **gắn với thread đang mở nó**, `@StepScope` **gắn với `StepExecution`**, và không có phép màu biến object mutable thành thread-safe.

## 4. Race condition và visibility của Java Memory Model

### Race trên biến dùng chung

~~~java
class UnsafeProgress {
    private long finished;

    void markDone() {
        finished++; // Không nguyên tử: read + increment + write.
    }

    long current() {
        return finished;
    }
}
~~~

Hai thread có thể cùng đọc giá trị 100, cùng tính 101 và ghi 101; một lần tăng bị mất. Đổi sang `volatile long` làm một số thao tác đọc/ghi quan sát được giữa thread, nhưng **không biến `finished++` thành atomic**.

Nếu chỉ đếm metric thống kê trong process, `LongAdder` là lựa chọn hữu ích:

~~~java
import java.util.concurrent.atomic.LongAdder;

final class ConcurrentProgress {
    private final LongAdder finished = new LongAdder();

    void markDone() {
        finished.increment();
    }

    long approximateSnapshot() {
        return finished.sum();
    }
}
~~~

Đừng dùng counter JVM làm **checkpoint nghiệp vụ**: process crash làm mất state, đồng thời số lần xử lý có thể khác số bản ghi nghiệp vụ đã commit do retry/upsert.

### Visibility và happens-before

Một thread thay đổi flag mà thread khác đọc có thể không hoạt động đúng nếu thiếu cơ chế đồng bộ. `volatile`, lock, concurrent collections và các quan hệ happens-before trong Java hỗ trợ nhìn thấy dữ liệu mới theo đúng quy tắc.

~~~java
final class StopFlag {
    private volatile boolean requested;

    void requestStop() {
        requested = true;
    }

    boolean isRequested() {
        return requested;
    }
}
~~~

`volatile` phù hợp với cờ một biến, không biến chuỗi thao tác đọc–sửa–ghi thành transaction. `Thread.interrupt()` cũng cần worker và thư viện I/O hợp tác; không đảm bảo cắt được ngay mọi SQL/HTTP đang chạy.

### Quy tắc thiết kế shared state

- Ưu tiên `ItemProcessor` **stateless**; dữ liệu input là object bất biến hoặc không bị chia sẻ mutable giữa worker.
- Tránh singleton có field `currentOrder`, `currentIndex`, `pendingRows` được mọi worker cùng thay đổi.
- Dùng concurrent collection/atomic khi thật sự cần chia sẻ state trong process; kiểm tra thao tác tổ hợp “check rồi write” vẫn atomic hay không.
- JDBC `Connection`, JPA `EntityManager`/Hibernate `Session` không nên được đưa nguyên instance cho các worker cùng thao tác.
- Không khóa toàn bộ `process()` bằng `synchronized` rồi mong throughput tăng theo 8 thread: khóa rộng có thể tuần tự hóa toàn bộ xử lý.
- Dữ liệu nghiệp vụ phải được bảo vệ ở nguồn lưu bền vững bằng transaction/unique key/version, không chỉ bằng `AtomicLong` hoặc lock JVM.

## 5. `@StepScope` cô lập theo step, không mặc định theo thread

Một bean `@StepScope` được tạo trong scope của **`StepExecution`**, phù hợp với late binding `JobParameters` và `stepExecutionContext`. Trong local partitioning, vì mỗi partition có step execution riêng, reader có cursor sẽ được cấp instance riêng cho từng partition.

Ngược lại, nếu nhiều thread xử lý trong **cùng step execution**, chúng có thể truy cập **cùng bean step-scoped**. Vì vậy `@StepScope` không phải `@ThreadScope` và không tự sửa mọi lỗi thread safety của reader.

| Loại state | Đặt ở đâu | Tránh |
| --- | --- | --- |
| `startId/endExclusive` của partition | `StepExecutionContext` | Tính lại ranh giới khác khi restart |
| `snapshotId/businessDate` | `JobParameters` định danh, snapshot/manifest cố định | Lấy `now()` mới ở mỗi worker |
| Cursor và checkpoint | `ItemStream` reader theo `StepExecution` | Singleton cursor chia cho nhiều thread |
| Kết quả partial | Bảng có key theo partition/business window | Nhiều worker cùng ghi biến tổng mutable |
| Tổng hợp sau worker | Một step reduce sau manager/split join | Đọc kết quả còn chưa commit |
| Metric tạm thời | Counter thread-safe, instrumentation | Dùng metric thay bằng chứng dữ liệu |

Hơn nữa, `@StepScope` không tự mở transaction và không tự truyền `ThreadLocal` sang thread mới do ứng dụng tự tạo. Nếu gọi step-scoped bean từ một `CompletableFuture` không có Batch step context được framework quản lý, proxy có thể không resolve đúng scope.

## 6. `TaskExecutor` phải có giới hạn tài nguyên

`ThreadPoolTaskExecutor` cho phép giới hạn số thread, queue và theo dõi trạng thái của executor. Ví dụ dành cho **local partitioning**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class LocalExecutorConfiguration {
    @Bean("localPartitionExecutor")
    ThreadPoolTaskExecutor localPartitionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("batch-partition-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }
}
~~~

Bốn worker là giá trị **minh họa**, không phải cấu hình chuẩn; cần cân nhắc CPU core, JDBC connection, broker/API, data skew và số job có thể cùng chạy. Queue có giới hạn giúp lộ overload thay vì tích lũy vô hạn task/payload.

Các cạm bẫy thường gặp:

1. `gridSize` lớn nhưng executor chỉ có bốn thread: nhiều partition đợi trong queue, không nhất thiết sai nhưng thời gian sẽ phụ thuộc capacity.
2. `maxPoolSize` lớn nhưng queue còn nhiều chỗ: thread pool có thể chưa tăng tới max như dự tính vì cách hoạt động của `ThreadPoolExecutor`.
3. Parent task chiếm toàn bộ thread rồi đồng bộ chờ các child task cũng nằm trong cùng pool: nguy cơ **thread starvation/deadlock**.
4. Chỉ gửi `executor.execute(() -> work())` rồi trả `RepeatStatus.FINISHED`: Spring Batch có thể đánh dấu step xong khi work chưa hoàn tất.
5. Worker chờ DB connection quá lâu, thêm thread làm nhiều worker kẹt hơn; cần đo pool pending và DB lock.
6. Shutdown thông thường cho executor không bảo đảm các side effect HTTP hay JDBC bên ngoài transaction đã được hủy và rollback.

Giới hạn queue, timeout, backpressure và graceful shutdown phải được thiết kế cùng lifecycle step/job.

## 7. Ví dụ đầy đủ: local partitioning với một JVM, bốn worker

Giả sử một snapshot đơn hàng có schema:

~~~sql
CREATE TABLE batch_order_snapshot (
    snapshot_id VARCHAR(100) NOT NULL,
    id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);

CREATE TABLE batch_order_result (
    snapshot_id VARCHAR(100) NOT NULL,
    id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);
~~~

Một job xử lý snapshot đã đóng, với ID thuộc miền `[1, 1_000_001)`. Bốn partition liên tiếp, mỗi partition chạy **một worker step chunk-oriented** trên executor trong cùng JVM. Writer dùng `UPSERT` theo khóa `(snapshot_id, id)` để việc chạy lại chunk không sinh duplicate.

Ví dụ dưới dùng API phổ biến của **Spring Batch 5.x**, Java 17, PostgreSQL. Giả định Spring Boot đã cấu hình `JobRepository`, `DataSource`, `PlatformTransactionManager`; `snapshotId` là identifying job parameter. Các range cố định chỉ để minh họa; trong thực tế lấy từ snapshot/manifest và giữ ổn định theo `JobInstance`.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

record OrderRow(String snapshotId, long id, String payload) {}

@Configuration
class OrderLocalPartitionConfiguration {

    @Bean
    Partitioner orderRangePartitioner() {
        return gridSize -> {
            long first = 1L;
            long endExclusive = 1_000_001L;
            int count = Math.max(1, gridSize);
            long total = endExclusive - first;
            long base = total / count;
            long remainder = total % count;
            long start = first;

            Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
            for (int i = 0; i < count; i++) {
                long size = base + (i < remainder ? 1 : 0);
                if (size == 0) break;

                ExecutionContext context = new ExecutionContext();
                context.putLong("startId", start);
                context.putLong("endExclusive", start + size);
                partitions.put("partition" + i, context);
                start += size;
            }
            return partitions;
        };
    }

    @Bean
    @StepScope
    JdbcCursorItemReader<OrderRow> orderReader(
            DataSource dataSource,
            @Value("#{jobParameters['snapshotId']}") String snapshotId,
            @Value("#{stepExecutionContext['startId']}") Long startId,
            @Value("#{stepExecutionContext['endExclusive']}") Long endExclusive) {
        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("orderReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, payload
                    FROM batch_order_snapshot
                    WHERE snapshot_id = ?
                      AND id >= ? AND id < ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, startId);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, n) -> new OrderRow(
                        snapshotId, rs.getLong("id"),
                        rs.getString("payload")))
                .saveState(true)
                .build();
    }

    @Bean
    ItemWriter<OrderRow> orderWriter(JdbcTemplate jdbc) {
        // Stateless: không có cursor hay counter mutable dùng chung.
        return chunk -> {
            for (OrderRow row : chunk) {
                jdbc.update("""
                    INSERT INTO batch_order_result(snapshot_id, id, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT (snapshot_id, id) DO UPDATE
                    SET payload = EXCLUDED.payload
                    """, row.snapshotId(), row.id(), row.payload());
            }
        };
    }

    @Bean
    Step orderWorker(JobRepository repository,
                     PlatformTransactionManager transactionManager,
                     JdbcCursorItemReader<OrderRow> orderReader,
                     ItemWriter<OrderRow> orderWriter) {
        return new StepBuilder("orderWorker", repository)
                .<OrderRow, OrderRow>chunk(200, transactionManager)
                .reader(orderReader)
                .writer(orderWriter)
                .build();
    }

    @Bean
    Step orderManager(JobRepository repository,
                      @Qualifier("orderWorker") Step worker,
                      Partitioner orderRangePartitioner,
                      @Qualifier("localPartitionExecutor") TaskExecutor executor) {
        return new StepBuilder("orderManager", repository)
                .partitioner("orderWorker", orderRangePartitioner)
                .step(worker)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean
    Job orderImportJob(JobRepository repository,
                       @Qualifier("orderManager") Step manager) {
        return new JobBuilder("orderImportJob", repository)
                .start(manager)
                .build();
    }
}
~~~

Bean `localPartitionExecutor` được cấu hình ở mục 6 và phải có trong ứng dụng. Để hoàn chỉnh ví dụ, khởi chạy job bằng identifying `JobParameter` tên `snapshotId` trỏ tới snapshot đã tồn tại và bất biến. Mọi step/bean dùng chung `DataSource` với transaction manager thích hợp; nếu writer dùng DB/connection không tham gia transaction, rollback của chunk không bao phủ writer như mong muốn.

### Luồng chạy trong một JVM

~~~text
orderImportJob
  └── orderManager (manager thread)
      ├── orderWorker:partition0 → thread 1 → chunk TX...
      ├── orderWorker:partition1 → thread 2 → chunk TX...
      ├── orderWorker:partition2 → thread 3 → chunk TX...
      └── orderWorker:partition3 → thread 4 → chunk TX...
      
Snapshot ID là chung; StepExecution / reader / checkpoint riêng từng partition.
~~~

Các biên dùng quy ước **đầu bao gồm, cuối không bao gồm**: `id >= startId AND id < endExclusive`. Với snapshot cố định, bốn khoảng bao phủ không chồng lấn. Nếu nguồn thay đổi khi worker chạy hoặc partition được tính lại khác giữa các lần restart, checkpoint có thể mất ý nghĩa.

Writer `UPSERT` làm thao tác ghi **về cùng trạng thái** khi replay cùng record snapshot, nhưng không làm các trigger, audit hay API side effect khác tự idempotent. Khi production cần tốc độ cao, thử `JdbcBatchItemWriter` hoặc batch update và đo chi phí commit; code loop là ví dụ dễ đọc.

### Vì sao local partitioning giúp cô lập state?

Manager tạo các `ExecutionContext` riêng cho partition, framework cấp worker `StepExecution` tương ứng. Mỗi reader `@StepScope` nhận đúng boundary và có cursor của mình; các worker song song nhưng không tranh nhau di chuyển một con trỏ đọc chung.

Tuy vậy, DB pool, JVM heap và writer dependencies vẫn chia sẻ. Nếu bốn worker cùng giữ JDBC connection và DB có ít slot, throughput có thể không tăng. Các chunk của worker commit độc lập: partition 0 đã commit không tự rollback khi partition 2 gặp lỗi.

## 8. Transaction: thread khác không có nghĩa transaction chung

Trong Spring Framework, transaction imperative liên kết với thread mở transaction. Khi thread A gọi một `TaskExecutor` để chạy việc trên thread B, transaction của A **không tự lan** sang B.

~~~java
@Transactional
public void saveAndDispatch(OrderRow row) {
    repository.save(row);
    executor.execute(() -> auditService.writeAudit(row));
    // Audit chạy ở thread khác, không tự tham gia transaction ở đây.
}
~~~

Nếu `auditService` có `@Transactional` được gọi **qua proxy**, nó có thể mở transaction khác ở B. Nếu B commit nhưng transaction A rollback, audit có thể vẫn còn. Nếu A commit mà B lỗi, A cũng không tự rollback theo B.

Trong local partitioning, Spring Batch tự quản lý worker step và transaction các chunk trên worker tương ứng, thay vì ứng dụng tùy ý tạo thread con trong mỗi writer. Đây là lý do local partitioning thường dễ kiểm soát hơn `CompletableFuture.runAsync` được gọi trong một step mà không có join/retry contract.

Ngoài ra:

- Ghi bằng `JdbcTemplate` chỉ được rollback cùng chunk nếu đúng `DataSource` và transaction manager.
- Một HTTP request hoặc message broker nằm ngoài JDBC transaction không được rollback tự động.
- `REQUIRES_NEW` có thể commit transaction vật lý riêng, ảnh hưởng cách replay.
- Self-invocation `this.methodAnnotatedTransactional()` có thể bỏ qua Spring transaction proxy.
- Không “sao chép” `TransactionSynchronizationManager` hoặc JDBC connection qua thread để cố tạo transaction dùng chung.

## 9. Retry, restart và giới hạn fault isolation của một JVM

Giả sử bốn partition đang chạy:

| Partition | Trạng thái trước sự cố | Hệ quả |
| --- | --- | --- |
| P0 | `COMPLETED` | Các chunk đã commit vẫn còn |
| P1 | `COMPLETED` | Không rollback cùng partition khác |
| P2 | Commit 30 chunk, chunk 31 lỗi | Chunk 31 rollback theo transaction tương ứng; có thể phải đọc lại |
| P3 | Commit 18 chunk, đang chạy chunk 19 | Khi JVM chết, chunk chưa commit cần phục hồi |

Khi restart **cùng `JobInstance`** bằng identifying `JobParameters` không đổi, framework sử dụng trạng thái `StepExecution`/`ExecutionContext` để quyết định bỏ qua step đã hoàn thành và thực hiện tiếp phần cần thiết theo restart policy. Không nên suy luận rằng tất cả partition bắt đầu lại từ đầu, cũng không có transaction chung rollback mọi chunk đã commit.

Với process chết đột ngột, repository có thể còn `JobExecution` ở `STARTED`. Trước khi can thiệp hoặc restart cần xác nhận không còn worker cũ đang ghi; dùng quy trình vận hành phù hợp phiên bản. **Không xóa bảng metadata `BATCH_*`** để “mở khóa”.

### Đúng checkpoint cần gì?

1. **Snapshot/manifest bất biến:** record của một lần chạy logic không thay đổi khi restart.
2. **Partition mapping ổn định:** tên partition, ID range, key trong `ExecutionContext` và số lượng phân vùng dùng lại có contract rõ ràng.
3. **Thứ tự đọc xác định:** `ORDER BY` trên khóa duy nhất, reader tham gia `ItemStream` lifecycle.
4. **Writer idempotent:** replay cùng business key không tạo side effect sai.
5. **Bảo vệ nguồn ngoài DB:** có outbox/idempotency key/reconciliation cho HTTP, message, file.
6. **Giới hạn retry:** phân loại lỗi transient so với permanent; tránh nhiều thread đồng thời retry tạo storm.

Không dùng `static AtomicLong`, cache hay `ThreadLocal` làm checkpoint bền vững. Chúng mất khi JVM chết và không bảo đảm trạng thái đúng sau commit/rollback.

## 10. Trần hiệu năng của một JVM

Tốc độ toàn job bị giới hạn bởi stage yếu nhất và chi phí điều phối:

~~~text
R_effective ≤ min(
    R_reader,
    R_processor_cpu,
    R_writer_db,
    R_connection_lock,
    R_api_network,
    R_executor
)
~~~

Các chỉ số phải quy về **cùng đơn vị** (ví dụ đơn hàng hợp lệ mỗi giây), không so sánh thẳng SQL statements/s với item/s nếu mỗi item cần nhiều statement.

### Đường cong tăng worker minh họa

| Worker đồng thời | Throughput giả định | Diễn giải |
| ---: | ---: | --- |
| 1 | 450 order/s | Baseline |
| 2 | 840 order/s | Tăng gần tuyến tính |
| 4 | 1.420 order/s | Overhead và contention tăng |
| 8 | 1.530 order/s | Đến gần trần DB writer |
| 16 | 1.400 order/s | Giảm vì connection wait/lock/retry |

Đây là **số liệu giả định**, không phải benchmark chuẩn của Spring Batch. Nếu tăng 8 lên 16 worker khiến throughput giảm, cần phân tích bottleneck thay vì tiếp tục tăng concurrency.

### CPU

Nếu processor cần trung bình `4 ms CPU/item`, muốn đạt `2.000 item/s` cần khoảng:

~~~text
CPU busy demand = 2.000 × 0,004 = 8 CPU-cores
~~~

Nếu JVM bị giới hạn 4 CPU core, tạo 32 thread CPU-bound không tăng công suất CPU. Với I/O-bound có thể dùng nhiều thread hơn số core, nhưng phải kiểm soát tốc độ API/DB và in-flight.

### Heap và GC

Bốn worker, mỗi worker giữ một chunk 200 item với kích thước thực trung bình 64 KiB/item:

~~~text
4 × 200 × 64 KiB = 50 MiB
~~~

Đó mới là phần dữ liệu chunk ước lượng; heap còn chứa queue, buffer, cache, JDBC objects và chi phí JVM. Nếu item p99 lớn hơn average nhiều lần, phải đo peak heap/RSS, GC pause và nguy cơ OOM khi tăng số worker.

### Connection pool

Nếu trong một process có 12 connection DB khả dụng, 3 dành cho manager/metadata/hoạt động khác, một worker có thể giữ 2 connection đồng thời và muốn chừa 1 connection dự phòng:

~~~text
Available worker connections = 12 - 3 - 1 = 8
workers_by_connections = floor(8 / 2) = 4
~~~

Con số **2 connection/worker** là giả định phải xác minh bằng metric thật; reader cursor và writer có thể dùng số connection khác theo cấu hình. Nếu có hai replica cùng dùng DB, **hai pool tối đa 12** có thể cùng đưa tới 24 connection trên DB, không phải 12 trên toàn cluster.

## 11. Giám sát single-process multi-threading

| Lớp | Số đo hữu ích | Mục đích |
| --- | --- | --- |
| JVM/container | CPU quota/throttling, heap, GC pause, thread count, RSS | Xác định CPU/memory saturation |
| `TaskExecutor` | Active threads, queue depth, rejected tasks, task wait | Tìm starvation/overload |
| JDBC pool | Active/idle/pending, acquisition wait, timeout | Phát hiện thiếu connection |
| Database | Query latency, lock wait, deadlock, IOPS, WAL/commit latency | Chỉ ra bottleneck chung ngoài JVM |
| Job/Step | `JobExecutionId`, `StepExecutionId`, read/write/commit/rollback, status | Xác định worker/partition lỗi |
| Nghiệp vụ | Unique business keys/s, missing/duplicate keys, SLA | Chứng minh throughput **hữu ích** |

Một log chẩn đoán có thể in thread name và trạng thái Spring transaction:

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

static void trace(String stage, Long stepExecutionId) {
    System.out.printf(
        "stage=%s step=%d thread=%s txActive=%s%n",
        stage, stepExecutionId, Thread.currentThread().getName(),
        TransactionSynchronizationManager.isActualTransactionActive());
}
~~~

`txActive` chỉ phản ánh Spring transaction trên thread hiện tại, **không chứng minh** side effect HTTP hay DB khác cùng transaction. Muốn xác minh atomicity, cố tình ném exception giữa các lệnh JDBC và kiểm tra dữ liệu sau rollback.

MDC/tracing dựa trên `ThreadLocal` không tự lan qua mọi executor; cần context propagation phù hợp, đồng thời dọn context khi thread trong pool được tái sử dụng để tránh ghép log nhầm job.

## 12. Kịch bản kiểm thử trước khi tăng concurrency

1. Chạy **một worker** với snapshot cố định, ghi baseline end-to-end, row count và checksum.
2. Tăng **2, 4, 8 worker** trên cùng snapshot, xác nhận mọi input thuộc đúng một partition và output không thiếu/trùng.
3. Kiểm tra **ID ranh giới**, partition rỗng, ID thưa, payload lớn và partition lệch thời gian.
4. Tạo lỗi **race trên singleton** trong staging để hiểu hậu quả, sau đó chuyển sang bean per-step hoặc state/algorithm đồng bộ phù hợp.
5. Ném exception trong một chunk sau một số JDBC write, kiểm tra các lệnh cùng transaction rollback đúng.
6. Để một partition `COMPLETED`, một partition `FAILED` rồi restart cùng identifying params; kiểm tra checkpoint và kết quả idempotent.
7. Kill JVM ở staging giữa chunk; kiểm tra trạng thái metadata và quy trình phục hồi an toàn, không tự xóa dữ liệu repository.
8. Giảm connection pool để tạo timeout; xác minh lỗi được xử lý và không có task silently lost.
9. Thử kết hợp `split` và partitioning, đo tổng worker thực tế, tránh deadlock do cùng executor nhỏ.
10. Đo chung với tải DB/API của ứng dụng khác, không lấy benchmark trong hệ thống trống làm định mức production.
11. Xác minh stop/shutdown: các worker hoàn thành/rollback transaction đang xử lý theo contract và không còn ghi sau khi owner mới chạy.
12. Dừng tăng số worker khi throughput bão hòa hoặc p95 latency, retry, lock wait và GC tăng.

Kết quả cuối phải dựa trên **dữ liệu nghiệp vụ đã đối soát**, không chỉ tổng `readCount` hoặc log “processed N items”. Retry và writer upsert có thể khiến các số đếm kỹ thuật khác số business key hợp lệ đã hoàn tất.

## 13. Khi nào chuyển sang nhiều process?

| Trường hợp | Single-process nhiều luồng | Hướng khác |
| --- | --- | --- |
| Một node còn CPU/RAM, DB/API còn dư | Giữ local, ít thành phần | Chưa cần broker |
| Tập input phân chia tốt theo ID/file/tenant | Local partitioning | Remote partitioning nếu vượt khả năng host |
| Hai flow độc lập có điểm join | Parallel steps trong JVM | Scheduler/job độc lập nếu lifecycle khác nhau |
| CPU node cạn nhưng DB còn dư | Tăng thread không vượt CPU quota | Thêm node/worker remote |
| Writer DB đạt trần lock/I/O | Thêm thread thường phản tác dụng | Tối ưu DB/writer/transaction |
| Crash một JVM làm mọi worker mất cùng lúc, RTO gắt | Cần checkpoint và recovery mạnh | Nhiều JVM giảm failure domain nhưng thêm giao thức |
| Manager reader đã là bottleneck | Tối ưu reader, index, snapshot | Remote partitioning nếu chia nguồn được |
| Processor/writer nặng, manager reader còn dư | Có thể song song local | Remote chunking nếu broker/backpressure phù hợp |

Remote partitioning đưa **miền dữ liệu/StepExecution** sang worker process khác; remote chunking giữ reader ở manager và gửi **chunk** qua middleware. Các mô hình phân tán cần xử lý network, ack, redelivery, correlation và idempotency, không đơn thuần là đổi executor.

**Nếu DB là nút thắt**, chuyển từ 8 thread trong một JVM sang 8 worker ở nhiều JVM vẫn có thể không tăng throughput, vì DB không tự tăng công suất.

## 14. Bài tập tình huống

Một job nhập 6 triệu giao dịch, chạy trên JVM được cấp 8 vCPU. Các giao dịch trong cùng một tài khoản phải được xử lý đúng thứ tự. Có ba đề xuất:

- **A:** Dùng multi-threaded step với một singleton `JdbcCursorItemReader` chung cho tám thread.
- **B:** Dùng local partitioning chia theo `account_id`, mỗi worker `StepExecution`/`@StepScope` reader riêng; trong worker đọc theo `(event_time, transaction_id)`.
- **C:** Một tasklet tạo tám `CompletableFuture` rồi lập tức trả `RepeatStatus.FINISHED`.

DB pool có 12 connection, ba connection đang dành cho hoạt động khác, mỗi worker có thể giữ hai connection đồng thời. Writer cập nhật số dư theo account.

**Câu hỏi:**

1. Phương án nào dễ bảo vệ thứ tự, checkpoint và restart? Vì sao?
2. Vấn đề thread safety của A và lifecycle của C là gì?
3. Theo công thức đơn giản, pool có thể cấp tối đa bao nhiêu worker đồng thời trước headroom?
4. Nếu một tài khoản chiếm 60% dữ liệu, tăng số worker có giải quyết đường găng không?
5. Khi JVM chết sau khi một số chunk commit, dữ liệu nào còn, dữ liệu nào cần xử lý lại?

**Gợi ý:** B có cấu trúc rõ ràng nhất nếu account được gán ổn định, reader per-step và writer an toàn. A có nguy cơ chia sẻ cursor mutable; C có thể khiến framework coi step đã hoàn tất dù future chưa xong. `floor((12−3)/2)=4` worker trước headroom. Tài khoản quá lớn vẫn là đường găng nếu bắt buộc tuần tự trong account; cần thuật toán có chứng minh tính đúng hoặc chấp nhận giới hạn. Chunk đã commit không tự rollback theo những worker khác; restart dùng metadata/checkpoint và writer idempotent.

## Tài liệu tham khảo

- [Spring Batch – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, local/remote partitioning.
- [Spring Batch 5.2 – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): cấu hình executor và mô hình nhiều luồng trên dòng 5.x.
- [Spring Batch – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): reader/writer, `ItemStream` và state.
- [Spring Batch – JobRepository and Metadata](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `JobExecution`, `StepExecution`, `ExecutionContext`.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor` và pool.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): imperative transactions gắn với thread.
- [Java Language Specification – Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model và happens-before.

## Ghi nhớ

**Single-process nhiều luồng là scale-up bằng nhiều thread trong một JVM: dễ triển khai và không cần broker nội bộ, nhưng chia sẻ heap, pool, CPU/RAM và cùng chịu lỗi process.** Mỗi thread có stack/transaction context riêng; mutable singleton có thể race, còn `@StepScope` cô lập theo `StepExecution` chứ không mặc nhiên theo thread. Hãy chọn đúng đơn vị song song, kiểm soát executor và tài nguyên, dùng reader/writer có checkpoint, idempotency và phép đối soát, rồi đo throughput cùng khả năng restart trước khi tăng số worker.
