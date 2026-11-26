# ExecutionContext theo partition trong Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **mỗi partition có `StepExecution` và `ExecutionContext` riêng**, trong khi các partition vẫn thuộc cùng một `JobExecution`.
- Phân biệt `JobParameters`, `JobExecutionContext`, `StepExecutionContext` của manager và từng worker.
- Tạo `Partitioner` sinh tên partition ổn định cùng ranh giới `startId` / `endExclusive` không trùng lặp.
- Dùng `@StepScope` và biểu thức `#{stepExecutionContext[...]}` để truyền tham số cho reader của từng partition.
- Hiểu cách `ItemStream` cập nhật checkpoint, `JobRepository` lưu metadata và cách state được dùng khi restart.
- Tránh chia sẻ mutable state, làm mất checkpoint, thay đổi mapping giữa các lần chạy hoặc dùng `ExecutionContext` như một kho dữ liệu nghiệp vụ.
- Kiểm thử local/remote partitioning, retry/restart và khả năng scale khi dữ liệu lớn.

## 1. Bài toán: nhiều worker, mỗi worker phải nhớ mình xử lý phần nào

Một job nhập **12 triệu đơn hàng** trong module **SPRING_BATCH_SCALING_OPERATIONS** đang chạy quá chậm. Nhóm phát triển chia input thành bốn khoảng ID để sử dụng local partitioning, sau đó có thể mở rộng sang remote worker.

Giả sử một snapshot bất biến gồm các đơn hàng có `id` trong miền từ 1 đến 12.000.000. Manager giao:

| Tên partition | `startId` | `endExclusive` | Predicate của reader |
| --- | ---: | ---: | --- |
| `partition000` | 1 | 3000001 | `id >= 1 AND id < 3000001` |
| `partition001` | 3000001 | 6000001 | `id >= 3000001 AND id < 6000001` |
| `partition002` | 6000001 | 9000001 | `id >= 6000001 AND id < 9000001` |
| `partition003` | 9000001 | 12000001 | `id >= 9000001 AND id < 12000001` |

Mỗi worker phải biết **biên dữ liệu riêng**, không đọc trùng phạm vi của worker khác. Sau khi commit được nhiều chunk, worker có thể chết; lúc khởi động lại nó cần biết **biên gốc** và **vị trí checkpoint cuối đã lưu**.

`ExecutionContext` theo partition chính là cơ chế để Spring Batch gắn các thông số có thể lưu bền vững với từng `StepExecution` của partition đó.

> **Ý chính:** `ExecutionContext` không phải một map toàn cục dùng chung cho mọi worker. Trong partitioning, mỗi partition có một context riêng, được `JobRepository` quản lý cùng metadata của `StepExecution` tương ứng.

## 2. Phân biệt bốn nơi chứa dữ liệu

Tên `ExecutionContext` dễ khiến người học nghĩ mọi state của job đều nằm trong một map. Thực tế có nhiều cấp độ.

| Nơi chứa | Phạm vi | Ví dụ | Cần chú ý |
| --- | --- | --- | --- |
| `JobParameters` | Định danh và cấu hình một lần chạy logic | `snapshotId=orders-2026-11-25`, `businessDate` | Identifying parameters quyết định `JobInstance`; nên bất biến khi restart |
| `JobExecution.getExecutionContext()` | Một `JobExecution` | Dấu hiệu bước chuẩn bị nguồn hoàn thành, thông tin phục vụ step sau | Không phải channel an toàn để nhiều partition cùng ghi tùy ý |
| Manager `StepExecutionContext` | `StepExecution` của **manager step** | Trạng thái quản lý/điều phối của manager tùy handler | Không tự đồng nhất với context worker |
| Worker `StepExecutionContext` | **Một `StepExecution` của mỗi partition** | `startId`, `endExclusive`, cursor/checkpoint | Mỗi partition độc lập về namespace và trạng thái |

Có thể hình dung quan hệ:

~~~mermaid
flowchart TD
    J["JobInstance: snapshotId=orders-2026-11-25"] --> E["JobExecution"]
    E --> JC["JobExecutionContext"]
    E --> M["managerStep / StepExecution"]
    M --> MC["Manager StepExecutionContext"]
    M --> P0["workerStep:partition000 / StepExecution"]
    M --> P1["workerStep:partition001 / StepExecution"]
    M --> P2["workerStep:partition002 / StepExecution"]
    P0 --> C0["EC0: range 1–3000001, reader checkpoint"]
    P1 --> C1["EC1: range 3000001–6000001, reader checkpoint"]
    P2 --> C2["EC2: range 6000001–9000001, reader checkpoint"]
~~~

Trong thực tế, cấu trúc `JobExecution` và các `StepExecution` được quản lý trong metadata của framework; mũi tên thể hiện quan hệ điều phối, không phải quan hệ Java object cha–con cố định.

### Mỗi partition có key giống nhau vẫn được

Cả bốn worker có thể dùng tên key `startId`, `endExclusive` và checkpoint key như `orderReader.read.count`, vì **mỗi worker có `ExecutionContext` của riêng nó**.

Ví dụ:

~~~text
workerStep:partition000:
  startId         = 1
  endExclusive    = 3000001
  orderReader.*   = checkpoint riêng của worker 0

workerStep:partition001:
  startId         = 3000001
  endExclusive    = 6000001
  orderReader.*   = checkpoint riêng của worker 1
~~~

Không phải thêm `partition001` vào **mọi key** để phân biệt giữa các `StepExecution`. Tuy nhiên, **trong cùng một context**, các component dùng chung một keyspace: hai `ItemStream` khác nhau không được dùng cùng tên checkpoint nếu chúng ghi đè dữ liệu của nhau.

## 3. `Partitioner` tạo input context ban đầu như thế nào?

Một `Partitioner` của Spring Batch có contract cốt lõi:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Giá trị trả về:

- **Key của map**: tên partition, ví dụ `partition000`; framework dùng tên này để đặt tên `StepExecution` worker, thường theo dạng `workerStep:partition000`.
- **Value của map**: `ExecutionContext` đầu vào của partition đó, ví dụ `startId=1`, `endExclusive=3000001`.
- **`gridSize`**: số partition được yêu cầu như một gợi ý/phần cấu hình; nó **không phải** con số bảo đảm số thread hoặc số process đang chạy.

Tên partition phải phân biệt được giữa các step execution của job và **ổn định theo logic restart**. Mỗi context cũng cần mô tả một miền dữ liệu ổn định. Có thể đặt tên theo range hoặc counter, nhưng đừng tạo tên mới bằng UUID mỗi lần gọi `partition()`.

### Vòng đời ngắn gọn

~~~mermaid
sequenceDiagram
    participant M as Manager Step
    participant P as Partitioner
    participant R as JobRepository
    participant W as Worker Step
    M->>P: partition(gridSize)
    P-->>M: Map tên partition → ExecutionContext
    M->>R: Tạo / quản lý StepExecution của partition
    M->>W: Phân công worker + context tương ứng
    W->>W: @StepScope nhận startId, endExclusive
    loop Các chunk
      W->>W: Read → Process → Write
      W->>R: Persist state/checkpoint theo commit
    end
    W-->>M: StepExecution result
    M->>R: Tổng hợp trạng thái manager
~~~

Khi **restart**, Spring Batch dùng metadata hiện có và cơ chế splitter/partition handler để xử lý phần cần tiếp tục, không đơn giản tạo lại từ đầu mọi context. Vì vậy:

1. Không viết `Partitioner` sinh tên/boundary ngẫu nhiên.
2. Không mặc định rằng mọi restart luôn gọi lại `partition(gridSize)` để tính lại range và ghi đè checkpoint.
3. Nếu hiện thực `PartitionNameProvider`, danh sách tên nó sinh ra phải **trùng tên** từ `Partitioner`; trên restart framework có thể chỉ cần hỏi danh sách tên, không dựng lại đầy đủ context.
4. Không thay `gridSize`/thuật toán chia cho một `JobInstance` đang cần restart mà không có chính sách tương thích và kiểm thử.

Đừng nhầm việc `Partitioner` cung cấp **tham số ban đầu** với vai trò `ItemStream` cập nhật **checkpoint đang tiến triển**. Hai loại dữ liệu cùng nằm trong context của worker nhưng có người sở hữu/lifecycle khác nhau.

## 4. Ví dụ `Partitioner` theo khoảng ID ổn định

Đây là một `Partitioner` minh họa **Spring Batch 5.x, Java 17**, tạo các khoảng nguyên không giao nhau theo quy ước **đầu bao gồm, cuối không bao gồm**.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class RangePartitioner implements Partitioner {

    private final long firstInclusive;
    private final long endExclusive;

    public RangePartitioner(long firstInclusive, long endExclusive) {
        if (firstInclusive < 0 || endExclusive < firstInclusive) {
            throw new IllegalArgumentException("Invalid nonnegative range");
        }
        this.firstInclusive = firstInclusive;
        this.endExclusive = endExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = endExclusive - firstInclusive;
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        if (total == 0) {
            return result;
        }

        // Không tạo partition rỗng khi số giá trị ID nhỏ hơn gridSize.
        int count = (int) Math.min(total, (long) gridSize);
        long base = total / count;
        long remainder = total % count;
        long start = firstInclusive;

        for (int i = 0; i < count; i++) {
            long width = base + (i < remainder ? 1 : 0);
            long end = start + width;

            ExecutionContext context = new ExecutionContext();
            context.putLong("startId", start);
            context.putLong("endExclusive", end);

            result.put(String.format("partition%03d", i), context);
            start = end;
        }

        if (start != endExclusive) {
            throw new IllegalStateException("Partition coverage mismatch");
        }

        return result;
    }
}
~~~

Ví dụ cấu hình bốn partition:

~~~java
Partitioner partitioner = new RangePartitioner(1L, 12_000_001L);
Map<String, ExecutionContext> ranges = partitioner.partition(4);

// partition000: [1, 3_000_001)
// partition001: [3_000_001, 6_000_001)
// partition002: [6_000_001, 9_000_001)
// partition003: [9_000_001, 12_000_001)
~~~

Đây là một **bài toán khoảng ID**, chưa bảo đảm số bản ghi và thời gian mỗi partition bằng nhau. ID có thể bị thưa, các bản ghi có thể mang payload rất khác nhau. Nếu dữ liệu nguồn là snapshot không liền ID, vẫn có thể dùng range nếu query/index phù hợp.

### Quy tắc ranh giới quan trọng

~~~sql
SELECT id, payload
FROM order_snapshot
WHERE snapshot_id = :snapshotId
  AND id >= :startId
  AND id < :endExclusive
ORDER BY id;
~~~

Sử dụng `BETWEEN :startId AND :endId` với hai partition liền kề khi cả hai đầu đều lấy có thể khiến bản ghi tại ranh giới bị đọc trùng. Quy ước `[startId, endExclusive)` loại bỏ nhập nhằng đó.

**Lưu ý triển khai:** các biên 1 và 12.000.001 được hardcode chỉ để minh họa. Production cần sinh hoặc tra ranh giới từ **snapshot/manifest bất biến** theo định danh logic của job. Không tính lại `MAX(id)` từ bảng nguồn đang thay đổi mỗi lần restart rồi kỳ vọng checkpoint vẫn đúng.

## 5. Từ `ExecutionContext` sang reader bằng `@StepScope`

Giả sử nguồn và đích có schema PostgreSQL:

~~~sql
CREATE TABLE order_snapshot (
    snapshot_id VARCHAR(100) NOT NULL,
    id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);

CREATE TABLE processed_order (
    snapshot_id VARCHAR(100) NOT NULL,
    id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, id)
);
~~~

Điều kiện của ví dụ:

- `snapshotId` là identifying `JobParameter` do scheduler/caller cung cấp.
- Bảng `order_snapshot` **đã đóng snapshot**, không bị sửa trong suốt run và lần restart tương ứng.
- Cả hai bảng có index phù hợp với predicate `(snapshot_id, id)`.
- `ExecutionContext` của mỗi partition chứa `startId` và `endExclusive` từ manager.
- Mỗi worker sử dụng một reader theo `StepExecution`, không có một singleton cursor dùng chung giữa các partition.

Bean reader minh họa, dùng API Spring Batch 5.x:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderRow(String snapshotId, long id, String payload) {}

@Configuration
class PartitionReaderConfiguration {

    @Bean
    @StepScope
    JdbcCursorItemReader<OrderRow> partitionOrderReader(
            DataSource dataSource,
            @Value("#{jobParameters['snapshotId']}") String snapshotId,
            @Value("#{stepExecutionContext['startId']}") Long startId,
            @Value("#{stepExecutionContext['endExclusive']}") Long endExclusive) {

        if (snapshotId == null || startId == null || endExclusive == null
                || startId >= endExclusive) {
            throw new IllegalArgumentException("Missing partition context");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("partitionOrderReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, payload
                    FROM order_snapshot
                    WHERE snapshot_id = ?
                      AND id >= ?
                      AND id < ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, startId);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, rowNum) -> new OrderRow(
                        snapshotId,
                        rs.getLong("id"),
                        rs.getString("payload")))
                .saveState(true)
                .build();
    }
}
~~~

### Đọc chính xác biểu thức late binding

- `#{jobParameters['snapshotId']}` lấy giá trị chung định danh snapshot.
- `#{stepExecutionContext['startId']}` lấy biên **chỉ dành cho partition hiện tại**.
- `#{stepExecutionContext['endExclusive']}` lấy biên cuối tương ứng.
- `@StepScope` hoãn khởi tạo reader đến khi có `StepExecution` hợp lệ; các partition có step execution riêng nên có instance reader riêng.
- `.name("partitionOrderReader")` đặt namespace checkpoint của `ItemStream` trong từng context.
- `.saveState(true)` cho phép reader cập nhật state dùng khi restart, khi `ItemStream` được Spring Batch quản lý đúng.

Không viết một bean **singleton** rồi cố inject trực tiếp `@Value("#{stepExecutionContext['startId']}")` ở thời điểm application startup: lúc đó chưa có context worker cần thiết. Cũng không tự mở reader trong thread ngẫu nhiên ngoài lifecycle step mà vẫn kỳ vọng scope và transaction tồn tại.

### `@StepScope` không phải `@ThreadScope`

Trong **local partitioning**, mỗi partition có `StepExecution` riêng, nên scope cô lập reader phù hợp. Nhưng nếu bạn chạy **nhiều thread trong cùng một `StepExecution`**, bean `@StepScope` vẫn có thể được dùng chung bởi các thread đó. Nó không tự biến một cursor mutable thành thread-safe.

## 6. Tổ chức manager step và worker step

Một cấu hình local partitioning Spring Batch 5.x có thể sử dụng `StepBuilder`, `TaskExecutor` và `gridSize`:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class PartitionJobConfiguration {

    @Bean
    Partitioner orderPartitioner() {
        // Giá trị ví dụ, thực tế lấy từ manifest snapshot ổn định.
        return new RangePartitioner(1L, 12_000_001L);
    }

    @Bean("partitionExecutor")
    ThreadPoolTaskExecutor partitionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("batch-part-");
        executor.initialize();
        return executor;
    }

    @Bean
    ItemWriter<OrderRow> orderWriter(JdbcTemplate jdbc) {
        // Stateless: có thể dùng trong nhiều worker khi dependency an toàn.
        return chunk -> {
            for (OrderRow row : chunk) {
                jdbc.update("""
                    INSERT INTO processed_order(snapshot_id, id, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT (snapshot_id, id) DO UPDATE
                    SET payload = EXCLUDED.payload
                    """, row.snapshotId(), row.id(), row.payload());
            }
        };
    }

    @Bean
    Step workerStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcCursorItemReader<OrderRow> partitionOrderReader,
            ItemWriter<OrderRow> orderWriter) {

        return new StepBuilder("workerStep", repository)
                .<OrderRow, OrderRow>chunk(200, transactionManager)
                .reader(partitionOrderReader)
                .writer(orderWriter)
                .build();
    }

    @Bean
    Step managerStep(
            JobRepository repository,
            @Qualifier("workerStep") Step workerStep,
            @Qualifier("orderPartitioner") Partitioner partitioner,
            @Qualifier("partitionExecutor") TaskExecutor executor) {

        return new StepBuilder("managerStep", repository)
                .partitioner("workerStep", partitioner)
                .step(workerStep)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean
    Job orderImportJob(
            JobRepository repository,
            @Qualifier("managerStep") Step managerStep) {

        return new JobBuilder("orderImportJob", repository)
                .start(managerStep)
                .build();
    }
}
~~~

Đoạn trên giả định hai configuration cùng nằm trong ứng dụng, Spring Boot đã tạo `DataSource`, `JdbcTemplate`, `JobRepository` và `PlatformTransactionManager` phù hợp. `OrderRow` là record ở mục 5. `snapshotId` phải được truyền qua identifying `JobParameters` khi launch.

Trong một ví dụ production, nên kiểm tra cả dependency injection nếu có nhiều bean cùng kiểu `Step`, `ItemWriter` hoặc `Partitioner`; dùng `@Qualifier` tương ứng khi cần.

### Manager tạo bao nhiêu partition thì có bấy nhiêu thread?

**Không nhất thiết.** `gridSize(4)` yêu cầu bốn partition trong ví dụ, còn `TaskExecutor` ở đây cho tối đa bốn worker thread; nếu dùng pool nhỏ hơn, các partition sẽ xếp hàng. Với remote partitioning, concurrency còn phụ thuộc pod/worker slot, broker và handler.

Mỗi worker `StepExecution` có transaction chunk riêng; các chunk đã commit ở partition A không bị rollback chỉ vì partition B fail. Đó là lý do writer cần giữ idempotency và metadata cần đủ cho restart.

### Còn trường hợp snapshot rỗng?

Một cách triển khai `Partitioner` trả map rỗng khi không có ID cần xử lý có thể cần kiểm chứng với `PartitionHandler`/step transition của phiên bản hiện tại. Trong production, nên xác định chính sách rõ: hoặc **bỏ qua bước partitioning** sau bước kiểm tra input rỗng, hoặc dùng partition no-op có contract được kiểm thử. Không coi map rỗng là tự động tương thích mọi handler.

## 7. `ExecutionContext` gồm “tham số tĩnh” và “checkpoint động”

Trong context của một partition, nên tách hai nhóm theo **người sở hữu cập nhật**:

| Nhóm | Ví dụ key | Người thiết lập/cập nhật | Ý nghĩa |
| --- | --- | --- | --- |
| Ranh giới ban đầu | `startId`, `endExclusive` | `Partitioner` khi phân công lần đầu | Miền dữ liệu partition được phép đọc |
| Định danh dữ liệu | `snapshotId`, `fileKey` (nếu không nằm ở JobParameters) | Manager/partitioner theo manifest | Cố định tập input |
| State của reader | Key nội bộ theo tên `ItemStream` | Reader trong `update(ExecutionContext)` | Vị trí đọc/checkpoint gần nhất |
| State của writer tùy loại | Key nội bộ của writer `ItemStream` | Writer | Trạng thái phục hồi của writer |
| Custom state nhỏ | `lastProcessedBusinessKey`, counter phụ | Component/lifecycle được quản lý | Dùng khi cần, nhưng không thay thế output DB |
| Kết quả nghiệp vụ lớn | Hàng triệu record/payload | **Không nên đặt trong context** | Ghi vào DB/object store, context chỉ chứa ID tham chiếu |

Không nên thay `startId` giữa các chunk, vì reader đang hiểu nó là **biên cố định** của cả partition. Nếu cần checkpoint, để reader ghi key **riêng**, không biến `startId` thành “cursor đã xử lý đến” nếu các component đang dựa trên nghĩa cố định của `startId`.

### Khi nào metadata được lưu?

Tài liệu Spring Batch phân biệt:

- `StepExecutionContext` thường được cập nhật **ở ranh giới commit của step/chunk**, theo lifecycle `ItemStream` và `JobRepository`.
- `JobExecutionContext` được lưu theo các điểm điều phối **giữa những step**, không phải kho checkpoint cho từng chunk đang chạy.
- Nếu business DB và JobRepository dùng **hai transaction manager/datasource khác nhau**, không mặc định checkpoint và nghiệp vụ commit trong một transaction vật lý.

Vì vậy, không nên dùng `jobExecution.getExecutionContext().put(...)` trong mỗi chunk rồi giả định giá trị được commit cùng dữ liệu của chunk. Cách phù hợp là state của reader/writer nằm trong **step context**, và dữ liệu nghiệp vụ trong nơi lưu bền vững được quản lý đúng.

### Ví dụ một component tự lưu state nhỏ

Nếu cần lưu một watermark riêng cho từng worker:

~~~java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStream;

public final class WorkerWatermark implements ItemStream {

    private static final String KEY = "workerWatermark.lastId";
    private long lastId = -1L;

    @Override
    public void open(ExecutionContext context) {
        if (context.containsKey(KEY)) {
            lastId = context.getLong(KEY);
        }
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(KEY, lastId);
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên nếu component có giữ tài nguyên.
    }

    public void markProcessed(long id) {
        lastId = Math.max(lastId, id);
    }

    public long lastSeenId() {
        return lastId;
    }
}
~~~

**Quan trọng:** đoạn này chỉ minh họa contract `ItemStream`; nó **không thể tự động thay checkpoint của reader**. Nếu dùng nó trong step thực tế, phải đăng ký đúng lifecycle (ví dụ `.stream(...)` nếu không được tự động nhận diện) và cập nhật state trong logic phù hợp với **kết quả đã commit**. Nếu `markProcessed` được gọi trước writer commit rồi snapshot state không đúng transaction, watermark có thể vượt quá dữ liệu đã ghi: restart sẽ bỏ sót record.

Do đó, với `JdbcCursorItemReader` đã có checkpoint được framework hỗ trợ, không tự viết thêm watermark để điều khiển việc skip record khi chưa chứng minh semantics.

## 8. Lưu bền vững: `JobRepository` và các bảng metadata

Với `JobRepository` JDBC chuẩn, Spring Batch lưu thông tin thực thi và context trong các bảng metadata. Trong schema thường gặp của Spring Batch 5.x:

- `BATCH_JOB_INSTANCE` và `BATCH_JOB_EXECUTION` lưu các thực thể job.
- `BATCH_STEP_EXECUTION` lưu step name, status, thời gian, read/write/commit/rollback count và liên kết tới job execution.
- `BATCH_STEP_EXECUTION_CONTEXT` lưu các context gắn với từng `STEP_EXECUTION_ID`.
- `BATCH_JOB_EXECUTION_CONTEXT` lưu context ở mức job execution.

Có thể xem metadata các worker trong một job execution bằng truy vấn (cú pháp tham số `:jobExecutionId` tùy DB client):

~~~sql
SELECT
    s.STEP_EXECUTION_ID,
    s.JOB_EXECUTION_ID,
    s.STEP_NAME,
    s.STATUS,
    s.READ_COUNT,
    s.WRITE_COUNT,
    s.COMMIT_COUNT,
    s.ROLLBACK_COUNT,
    c.SHORT_CONTEXT
FROM BATCH_STEP_EXECUTION s
JOIN BATCH_STEP_EXECUTION_CONTEXT c
  ON c.STEP_EXECUTION_ID = s.STEP_EXECUTION_ID
WHERE s.JOB_EXECUTION_ID = :jobExecutionId
  AND s.STEP_NAME LIKE 'workerStep:%'
ORDER BY s.STEP_NAME;
~~~

Kết quả giúp phân biệt `workerStep:partition000` với `workerStep:partition001`, xác nhận mỗi step execution có context riêng. Với schema khác phiên bản hoặc repository tùy biến, kiểm tra tên bảng/cột thực tế.

**Cảnh báo:** cột `SHORT_CONTEXT` có thể là bản rút gọn/trình bày đã serialize, không phải định dạng JSON ổn định để ứng dụng parse bằng SQL. Không viết logic nghiệp vụ dựa trên nội dung chuỗi `SHORT_CONTEXT`. Muốn quan sát state một cách có contract, ưu tiên `JobExplorer`/`JobRepository` API và instrumentation được thiết kế phù hợp.

Ngoài ra, không lưu secret/token hoặc thông tin nhạy cảm trong `ExecutionContext` rồi ghi thẳng ra log/monitoring; metadata có thể được lưu lâu dài và được sao lưu.

## 9. Kịch bản restart: partition nào giữ lại state?

Giả sử lần đầu chạy có bốn partition:

| Partition | Kết quả trước sự cố | Nội dung context quan trọng | Khi restart cùng `JobInstance` |
| --- | --- | --- | --- |
| `partition000` | `COMPLETED` | Boundary và checkpoint cuối | Thường không chạy lại theo restart policy mặc định |
| `partition001` | `COMPLETED` | Boundary và checkpoint cuối | Thường được bỏ qua |
| `partition002` | `FAILED` sau 120 chunk | Boundary và state reader từ commit gần nhất | Được xem xét thực thi lại/tiếp tục từ checkpoint |
| `partition003` | Worker bị kill trong chunk 51 | Boundary và checkpoint trước chunk chưa commit | Cần xác minh worker đã chết, phục hồi metadata và restart |

Khởi chạy một job mới với identifying `run.id` khác **không phải** restart cùng `JobInstance`. Nó có thể tạo toàn bộ partition mới, không dùng lại checkpoint cũ. Khi muốn khôi phục, phải giữ các identifying `JobParameters` cố định và dùng đường restart hợp lệ.

### Vòng đời state khi restart

1. Job được yêu cầu chạy lại với cùng định danh logic.
2. Framework kiểm tra trạng thái job/step trong `JobRepository`.
3. Với partition cần thực thi lại, metadata/context đã được lưu được dùng để phục hồi thông tin partition và state của `ItemStream` theo cơ chế của handler/splitter.
4. Worker tạo các component step-scoped cho `StepExecution` mới hoặc được chuẩn bị thích hợp, mở reader từ context tương ứng.
5. Các chunk chưa commit có thể được **xử lý lại**; các chunk đã commit không bị rollback theo toàn job.
6. Khi toàn bộ worker đạt trạng thái phù hợp, manager mới hoàn tất hoặc cho phép chuyển tiếp theo cấu hình.

Không suy luận chính xác “khôi phục tới dòng N” chỉ từ `readCount`: reader checkpoint có thể có quy tắc riêng; filter/skip/retry cũng làm số item đọc, xử lý, ghi khác nhau.

### Trường hợp crash nguy hiểm

Nếu worker commit business DB xong nhưng cập nhật checkpoint bị lỗi (đặc biệt khi metadata DB và business DB không chung transaction), lần restart có thể chạy lại một số item. Đây là lý do writer cần **idempotent** theo business key và hệ thống cần đối soát đầu ra, không chỉ tin checkpoint.

Một `StepExecution` có thể còn `STARTED` sau crash mà process đã chết. Trước khi sửa metadata hoặc restart phải xác nhận worker cũ không còn ghi, nhất là trong remote partitioning với network timeout. **Không xóa thủ công bảng `BATCH_*`** để “mở khóa”.

## 10. Những lỗi phổ biến liên quan đến context theo partition

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Mọi partition dùng cùng một `ExecutionContext` object | Đè boundary/khóa state, sai phạm vi xử lý | Tạo `new ExecutionContext()` cho **từng** map entry |
| Hai partition cùng range hoặc cả hai đầu đều inclusive | Đọc trùng, ghi trùng hoặc DB lock | Ranh giới `[start, end)`, test coverage/disjointness |
| Cùng tên partition được sinh với range khác khi restart | Checkpoint trỏ sai tập dữ liệu | Tên và mapping bất biến theo `JobInstance` |
| Dùng `System.currentTimeMillis()` làm tên partition | Không khớp metadata cũ, mất restart semantics | Tên deterministic theo business key/range |
| Lưu checkpoint ở `JobExecutionContext` trong mỗi chunk | Metadata không được lưu theo nhịp checkpoint mong muốn; race | Dùng `StepExecutionContext` |
| Reader singleton giữ cursor mutable giữa các partition | Race/đọc sai thứ tự | `@StepScope` reader trong từng worker `StepExecution` |
| Một `ItemStream` ghi key trùng với stream khác trong cùng context | State bị ghi đè | Đặt tên stream/namespace key khác nhau |
| Đặt toàn bộ item payload/list lớn vào context | Metadata DB lớn, serialize chậm, memory/IO tăng | Chỉ lưu primitive, ID, offset hoặc đường dẫn snapshot |
| Lưu non-serializable/custom object không tương thích | Lỗi lưu/khôi phục state theo serializer/version | Dùng kiểu đơn giản hoặc serializer tương thích và test restart |
| Thay `gridSize` giữa các attempt không có chiến lược | Mapping và tên có thể đổi | Giữ cách chia ổn định, thử restart theo chính sách |
| Tưởng `@StepScope` là thread isolation | Reader vẫn có thể bị dùng chung trong multi-threaded step | Phân biệt `StepExecution` với thread |
| Chạy lại job với identifying timestamp mới | Tạo instance mới, không nhận checkpoint cũ | Giữ identifying parameters để restart |
| Cho rằng metadata status bảo đảm output đúng | Có thể có side effect bên ngoài transaction hoặc re-delivery | Writer idempotent + reconciliation |

**Không dùng `ExecutionContext` làm kênh đồng bộ realtime giữa các worker.** Mỗi partition có context riêng; muốn trao đổi dữ liệu nghiệp vụ giữa các worker, hãy dùng nguồn bền vững và bước tổng hợp sau manager theo thứ tự được thiết kế.

## 11. Phạm vi thay đổi khi chuyển sang remote partitioning

Trong **local partitioning**, manager và worker chạy trong cùng JVM, nhưng các worker đã có `StepExecution`/context riêng. Khi chuyển sang **remote partitioning**, các worker chạy ở JVM khác:

- Manager phân phối **định danh partition/StepExecution hoặc metadata miền dữ liệu** theo giao thức.
- Worker nhận/tra state tương ứng thông qua hạ tầng Spring Batch Integration và repository được cấu hình phù hợp.
- `@StepScope` trên worker vẫn bind theo `StepExecutionContext` của partition đó.
- Không truyền bean Spring, JDBC `Connection`, thread-local transaction hay object cursor qua mạng.
- Context cần dùng kiểu dữ liệu có thể persist/deserialize với serializer tương thích giữa manager và worker.
- JobRepository là tài nguyên dùng chung trong các triển khai mà worker tra/cập nhật `StepExecution` theo ID; quyền truy cập metadata và version schema phải được kiểm soát.
- Nếu worker hoàn thành nhưng reply hoặc ACK thất lạc, manager có thể nghĩ partition chưa xong. Cần xác minh metadata và writer idempotency trước khi giao lại.
- Timeout/lease hết hạn **không chứng minh worker cũ đã ngừng ghi**; khi cần độc quyền phải có ownership/fencing hoặc chính sách takeover an toàn.

~~~mermaid
flowchart LR
    M["Manager / Partitioner"] --> Q["Broker: partition ID / StepExecutionRequest"]
    Q --> W1["Worker JVM A"]
    Q --> W2["Worker JVM B"]
    W1 --> R["Metadata repository / StepExecution context"]
    W2 --> R
    W1 --> D["Business DB / snapshot"]
    W2 --> D
    W1 -. "Reply/status" .-> M
    W2 -. "Reply/status" .-> M
~~~

**Remote chunking không giống remote partitioning.** Với remote chunking, manager thường sở hữu reader và gửi **chunk item** cho worker; đừng áp dụng máy móc giả định “mỗi worker có reader + partition `ExecutionContext`” của remote partitioning.

## 12. Kiểm tra dữ liệu: context đúng chưa chắc kết quả đúng

Cần có hai lớp kiểm chứng:

1. **Kiểm tra phân công:** mọi bản ghi thuộc đúng một partition, biên không chồng lấn, tên ổn định.
2. **Kiểm tra thực thi:** output đã commit đủ business key, không mất/trùng khi retry, kết quả có đúng version/payload.

Để kiểm tra phân công, có thể dùng bảng các khoảng kiểm thử:

~~~sql
WITH partition_ranges(partition_name, start_id, end_exclusive) AS (
    VALUES
      ('partition000', 1::BIGINT, 3000001::BIGINT),
      ('partition001', 3000001::BIGINT, 6000001::BIGINT),
      ('partition002', 6000001::BIGINT, 9000001::BIGINT),
      ('partition003', 9000001::BIGINT, 12000001::BIGINT)
),
assignments AS (
    SELECT s.id, COUNT(r.partition_name) AS assigned_count
    FROM order_snapshot s
    LEFT JOIN partition_ranges r
      ON s.id >= r.start_id
     AND s.id < r.end_exclusive
    WHERE s.snapshot_id = :snapshotId
    GROUP BY s.id
)
SELECT
    COUNT(*) FILTER (WHERE assigned_count = 0) AS missing_rows,
    COUNT(*) FILTER (WHERE assigned_count > 1) AS duplicate_assignments
FROM assignments;
~~~

Kỳ vọng cả hai cột bằng **0**. Truy vấn giả định `id` duy nhất trong snapshot (đã có primary key). Với dữ liệu rất lớn, kiểm thử trên snapshot đại diện và đối soát có chiến lược để tránh mỗi lần kiểm tra làm quét toàn nguồn; nhưng trước khi chạy production cần có bằng chứng đầy đủ về logic chia.

Đối soát kết quả sau job:

~~~sql
SELECT id
FROM order_snapshot
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT id
FROM processed_order
WHERE snapshot_id = :snapshotId;
~~~

Kết quả **0 dòng** nghĩa không thiếu ID ở đích theo điều kiện này; muốn phát hiện output thừa, đảo hai vế `EXCEPT`. Muốn kiểm tra payload sai, join theo `(snapshot_id, id)` và so sánh nội dung. Nếu nghiệp vụ có filter/transform, đổi invariant cho phù hợp chứ không bắt output phải bằng input thô.

## 13. Hiệu năng của context và partition

`ExecutionContext` được dùng để hỗ trợ restart, không phải cache xử lý dữ liệu khổng lồ. Khi tăng số partition/chunk:

- Mỗi partition có `StepExecution` và context tương ứng, làm tăng số bản ghi metadata.
- Reader/writer `ItemStream` có thể cập nhật state ở nhiều commit point; chunk quá nhỏ tạo nhiều lần update metadata.
- Context chứa object lớn khiến serialize/deserialize và IO repository chậm, có thể gây áp lực transaction/DB.
- Tên và state partition không ổn định sẽ làm restart khó hơn, khiến worker phải đọc lại nhiều dữ liệu.
- Nếu partition quá nhỏ, overhead dispatch, tạo step, quản lý context có thể lớn hơn lợi ích chia CPU.
- Nếu partition quá lớn hoặc lệch tải, worker chậm nhất kéo dài toàn job, dù các worker khác đã xong.

### Ví dụ đánh đổi chunk size

Giả sử một worker xử lý 1.000.000 item:

| Chunk size | Số lần commit lý tưởng | Ý nghĩa |
| --- | ---: | --- |
| 100 | Khoảng 10.000 | Checkpoint thường xuyên hơn, overhead nhiều |
| 500 | Khoảng 2.000 | Giảm overhead, rollback chunk lớn hơn |
| 2.000 | Khoảng 500 | Ít commit hơn nhưng transaction/payload lớn hơn |

Đây là số **ước lượng đơn giản** nếu mọi item được xử lý/commit đều, không có retry/skip; số `commitCount` thực có thể khác. Điều quan trọng là đánh giá **thời gian job**, **tài nguyên** và **khả năng restart** đồng thời.

Tăng `gridSize` từ 4 lên 40 không đồng nghĩa có 40 worker CPU thực sự: executor, broker, số process, DB connection và quota API giới hạn concurrency. `gridSize` nên được chọn cùng phân bố dữ liệu và chính sách metadata/restart.

## 14. Bộ kiểm thử cần có trước khi đưa vào production

1. **Unit test `Partitioner`:** trên miền có 0, 1, 2, 10, 1.000 giá trị; kiểm tra không lỗ hổng hoặc overlap, key duy nhất và số lượng hợp lý.
2. **Test boundary:** ID tại `endExclusive` chỉ thuộc partition kế tiếp; ID thưa và snapshot rỗng được xử lý theo chính sách.
3. **Late binding:** tạo nhiều partition có `startId` khác nhau và kiểm tra reader thực tế chỉ đọc đúng miền của nó.
4. **Namespace:** hai reader `ItemStream` trong một `StepExecution` không ghi trùng checkpoint key.
5. **Crash sau vài commit:** worker A hoàn thành, worker B lỗi; restart cùng identifying parameters và quan sát context B được khôi phục.
6. **Crash giữa ghi DB và metadata:** nếu dùng hai datasource/transaction, xác minh upsert không tạo duplicate và reconciliation đủ output.
7. **Snapshot thay đổi:** cố tình thêm/xóa record sau checkpoint trong staging để chứng minh vì sao cần snapshot bất biến.
8. **Đổi tên/range/gridSize:** thử sửa cách chia rồi restart; yêu cầu phát hiện sai hoặc dùng lại mapping đã persist.
9. **Parallel worker:** chạy đủ bốn worker trên cùng DB, kiểm tra reader state tách biệt, transaction và output không thiếu/trùng.
10. **Remote redelivery:** worker commit rồi mất reply; giao lại partition, kiểm tra business key idempotent và owner không ghi đồng thời sai.
11. **Serialization:** nâng phiên bản worker/serializer với context cũ có các key/kiểu dữ liệu đã lưu; kiểm tra backward compatibility.
12. **Resource test:** đo `JobRepository` latency, JDBC connection, CPU, GC, throughput và skew khi tăng số partition.

Với mỗi bài test, cần kiểm tra metadata **và** output nghiệp vụ. Một job có status `COMPLETED` nhưng thiếu ID không đạt yêu cầu.

## 15. Bài tập tự kiểm tra

Một snapshot có 11 ID: `1, 2, 4, 5, 7, 8, 9, 11, 12, 14, 15`. Manager tạo ba partition:

~~~text
partition000: startId=1,  endExclusive=6
partition001: startId=6,  endExclusive=11
partition002: startId=11, endExclusive=16
~~~

Khi chạy lần đầu:

- `partition000` đã `COMPLETED`.
- `partition001` đã commit các chunk chứa 7 và 8, sau đó lỗi khi xử lý 9.
- `partition002` đã `COMPLETED`.

**Câu hỏi:**

1. `id=11` thuộc partition nào? Có bị đọc trùng nếu dùng predicate `id < endExclusive` không?
2. Hai partition có thể cùng sử dụng key `startId` trong context mà không đè lên nhau không?
3. Nếu restart, step/partition nào thường cần xử lý lại?
4. Nếu lần restart manager đổi `partition001` thành `[6, 13)` nhưng giữ tên cũ, điều gì có thể sai?
5. Nếu writer dùng `UPDATE total = total + :amount` rồi chunk được chạy lại sau sự cố, idempotency có được bảo đảm không?
6. Khi chuyển từ local sang remote partitioning, có thể gửi nguyên object `JdbcCursorItemReader` qua broker để worker tiếp tục dùng không?

**Gợi ý đáp án:**

- (1) `id=11` thuộc `partition002`; đầu cuối exclusive tránh overlap.
- (2) Có, vì mỗi worker `StepExecution` có context riêng.
- (3) `partition001` là phần chưa hoàn thành, có thể resume theo checkpoint khi metadata hợp lệ; các partition hoàn thành thường được bỏ qua.
- (4) Context/checkpoint cũ có thể không tương ứng miền dữ liệu mới, gây thiếu/trùng hoặc lỗi restart.
- (5) Không; cần ledger theo operation key, partial aggregate/merge hoặc cơ chế ghi chống lặp được chứng minh.
- (6) Không; gửi định danh/context có thể persist, và worker tự tạo reader trong step scope.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): `Partitioner`, tên partition, `PartitionNameProvider`, `StepScope` và cách local/remote partitioning.
- [Spring Batch 5.2 Reference – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): API và hành vi partitioning của dòng 5.x.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`.
- [Spring Batch Reference – Common Batch Patterns](https://docs.spring.io/spring-batch/reference/common-patterns.html): phân biệt step/job context và truyền state giữa step.
- [Spring Batch Reference – Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): chuyển tiếp step và xử lý trạng thái.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): `ItemStream`, reader state và checkpoint.
- [Spring Batch Reference – JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): lưu metadata và quản lý transaction.

## Ghi nhớ

**Trong partitioning, mỗi partition được quản lý bởi một `StepExecution` có `ExecutionContext` riêng.** `Partitioner` cung cấp tên và tham số miền dữ liệu ban đầu; `@StepScope` giúp reader nhận đúng context của worker; `ItemStream` cập nhật checkpoint để hỗ trợ restart. Không dùng context như bộ nhớ chia sẻ realtime giữa các worker, không đổi tên/range/snapshot tùy ý giữa các lần chạy, và không coi metadata thay cho kết quả nghiệp vụ. Muốn mở rộng Spring Batch an toàn, hãy kiểm tra biên dữ liệu, giao dịch, idempotency, thời điểm persist checkpoint, khả năng phục hồi và giới hạn tài nguyên trên workload thật.
