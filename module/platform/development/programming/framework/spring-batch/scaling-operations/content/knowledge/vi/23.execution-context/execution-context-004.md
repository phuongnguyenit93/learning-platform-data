# Đặt input key cho worker trong Spring Batch Partitioning

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **input key** là khóa chỉ ra nguồn dữ liệu mà một worker được giao, không phải tên partition, business key hay checkpoint.
- Tạo input key trong `Partitioner` và truyền vào `StepExecutionContext` của từng partition.
- Sử dụng `@StepScope` với `#{stepExecutionContext['inputKey']}` để một cấu hình reader phục vụ nhiều worker mà không chia sẻ cursor.
- Thiết kế manifest và input key ổn định qua retry/restart cùng `JobInstance`, kể cả khi chuyển từ local sang remote partitioning.
- Cấu hình mẫu Spring Batch 5.x, Java 17: partitioner, reader, writer, manager step, worker step, executor và job.
- Kiểm tra tính bao phủ, không chồng lấn, idempotency, transaction, khả năng giải quyết key, bảo mật và hiệu năng khi scale dữ liệu lớn.

## 1. Bài toán: một worker step, nhiều nguồn đầu vào

Một job hằng ngày cần nhập 8 triệu đơn hàng đã chia thành bốn shard. Nếu viết bốn `Step` với đường dẫn hoặc câu SQL hardcode riêng, mã nguồn nhanh chóng trở nên khó mở rộng. Khi chuyển sang 16 hoặc 64 shard, việc tạo thêm bean và quản lý restart càng khó.

Spring Batch cho phép một **manager step** tạo các partition. Mỗi partition có một **worker `StepExecution`** và một **`ExecutionContext`** riêng. Manager có thể đặt một thuộc tính `inputKey` vào context, rồi worker dùng nó để chọn đúng nguồn.

| Partition | Giá trị `inputKey` | Tập dữ liệu |
| --- | --- | --- |
| `partition0000` | `orders/2026-11-25/shard-0000` | Shard số 0 |
| `partition0001` | `orders/2026-11-25/shard-0001` | Shard số 1 |
| `partition0002` | `orders/2026-11-25/shard-0002` | Shard số 2 |
| `partition0003` | `orders/2026-11-25/shard-0003` | Shard số 3 |

Ở đây, **`inputKey` là tên thuộc tính do ứng dụng tự quy định**, không phải một keyword mà Spring Batch bắt buộc phải sử dụng. Người phát triển có thể đặt `fileName`, `tenantId` hoặc `rangeStart` và `rangeEnd`. Contract quan trọng là manager ghi đúng tên, worker đọc đúng tên, kiểu và ý nghĩa không đổi giữa các lần chạy cần phục hồi.

~~~mermaid
flowchart TD
    J["importOrdersJob(snapshotId)"] --> M["managerStep"]
    M --> P["Partitioner đọc immutable manifest"]
    P --> C0["partition0000: inputKey shard-0000"]
    P --> C1["partition0001: inputKey shard-0001"]
    P --> C2["partition0002: inputKey shard-0002"]
    C0 --> W0["workerStep / StepScope reader"]
    C1 --> W1["workerStep / StepScope reader"]
    C2 --> W2["workerStep / StepScope reader"]
    W0 --> D["Bảng kết quả / writer idempotent"]
    W1 --> D
    W2 --> D
~~~

**Kết quả mong muốn:** bốn worker cùng dùng một definition của reader/processor/writer, nhưng mỗi worker chỉ thấy dữ liệu của input key được phân công. Worker hoàn thành nhanh hay chậm không làm thay đổi input key của worker khác.

## 2. Bốn loại khóa thường bị nhầm với nhau

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Identifying `JobParameter`** | `snapshotId=orders-2026-11-25` | Xác định cùng một `JobInstance` khi restart |
| **Partition name** | `partition0002` | Định danh worker `StepExecution` trong metadata |
| **Input key** | `orders/2026-11-25/shard-0002` | Chỉ nguồn/miền dữ liệu mà worker phải xử lý |
| **Business key** | `(snapshotId, orderId)` | Định danh record đích, giúp chống ghi trùng khi replay |
| **Checkpoint key** | State nội bộ của `ItemStream` reader | Ghi nhớ reader đã đọc tới đâu trong input |

Tên partition và input key không cần giống nhau. Input key có thể chứa đường dẫn dài hoặc ID manifest, trong khi partition name thường ngắn và ổn định.

**Input key không phải checkpoint.** `inputKey` trả lời “worker đang đọc shard nào?”, còn reader checkpoint trả lời “trong shard ấy, đã đọc đến vị trí nào?”. Nếu thay giá trị `inputKey` thành vị trí bản ghi cuối sau mỗi chunk, sẽ phá hợp đồng phân công và có thể khiến restart bỏ sót dữ liệu.

Đối với workload Spring Batch lớn, phải phân biệt thêm **đơn vị phân công** với **đơn vị ghi**: một input key có thể chứa 500.000 order, mỗi order có business key khác nhau. Writer không thể giả định rằng chỉ cần deduplicate theo input key là đủ để có một bản ghi cho mỗi order.

## 3. Input key thuộc ExecutionContext nào?

`Partitioner` trả về:

~~~java
Map<String, ExecutionContext> partition(int gridSize);
~~~

Mỗi phần tử của map có một **partition name** và một **`ExecutionContext` mới**. Context ấy được dùng làm tham số đầu vào cho worker `StepExecution`.

~~~java
Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

ExecutionContext a = new ExecutionContext();
a.putString("inputKey", "orders/2026-11-25/shard-0000");
partitions.put("partition0000", a);

ExecutionContext b = new ExecutionContext();
b.putString("inputKey", "orders/2026-11-25/shard-0001");
partitions.put("partition0001", b);
~~~

Vì `a` và `b` là hai context khác nhau, cùng tên khóa `inputKey` **không** đè giá trị giữa hai worker.

So sánh các phạm vi:

| Vị trí | Đặc điểm | Có nên đặt input key riêng của worker? |
| --- | --- | --- |
| `JobParameters` | Tham số chung, identifying hoặc non-identifying | Không phải nơi chính nếu mỗi partition khác input |
| `JobExecutionContext` | Context cấp job execution | Không dùng làm map chia việc concurrent cho tất cả worker |
| Manager `StepExecutionContext` | Context của manager step | Không tự động thay thế từng worker context |
| **Worker `StepExecutionContext`** | Riêng từng worker `StepExecution` | **Có**, đặt `inputKey` và boundary ở đây |

Không tái sử dụng **cùng object `ExecutionContext`** cho nhiều map entry rồi thay input key trong vòng lặp; tùy cách giữ reference, tất cả partition có thể trỏ đến giá trị cuối cùng.

### Từ manager đến reader

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant P as Partitioner
    participant R as JobRepository
    participant W as Worker
    participant I as Reader
    M->>P: partition(gridSize)
    P-->>M: partitionName + EC[inputKey]
    M->>R: Tạo / quản lý StepExecution
    M->>W: Dispatch worker StepExecution
    W->>I: Khởi tạo bean trong StepScope
    I->>I: Bind stepExecutionContext[inputKey]
    loop Chunk processing
      I-->>W: Đọc bản ghi đúng shard
      W->>R: Persist checkpoint qua ItemStream
    end
    W-->>M: Trả trạng thái
~~~

`JobRepository` giữ metadata cần thiết để phục hồi. Trong remote partitioning, worker có thể tra `StepExecution` theo ID và repository theo giao thức framework; không mặc định toàn bộ context được nhét nguyên dạng vào message.

## 4. Thiết kế input key ổn định và có thể khôi phục

Một input key đủ tốt cần thỏa những tiêu chí:

1. **Định danh chính xác một miền dữ liệu** trong snapshot. Không có hai key cùng chỉ tới cùng record nếu nghiệp vụ không cho phép overlap.
2. **Đủ duy nhất trong phạm vi `snapshotId`**; có thể dùng cùng chuỗi shard name giữa hai snapshot nếu hợp đồng ghép `(snapshotId,inputKey)` rõ ràng.
3. **Giữ nguyên nghĩa khi restart**: cùng key không được trỏ tới dữ liệu mới bị overwrite.
4. **Có thể tra từ worker khác**: không phụ thuộc heap, path local tạm hay object chỉ sống trong JVM manager.
5. **Nhỏ, dễ serialize**: String hoặc ID; không mang cả payload hàng triệu bản ghi.
6. **Có kiểm tra tồn tại và version**: manifest, checksum, object version hoặc dữ liệu snapshot đã đóng.
7. **Không chứa credential** và không biến thành URL/path tùy ý không được validate.
8. **Được định nghĩa bằng contract versioned** giữa manager và worker khi rolling deployment.

### Chọn theo nguồn

| Nguồn | Khóa gợi ý | Rủi ro |
| --- | --- | --- |
| Bảng DB đã gán shard | `inputKey=orders/.../shard-0001` | Thiếu index làm mọi worker full scan |
| Mỗi file là một shard | `objectKey=orders/.../part-1.csv` | File bị thay đổi, worker khác không thấy path local |
| Phân chia theo tenant | `tenantId=tenant-42` | Một tenant quá nặng hoặc có dữ liệu liên thuộc |
| Phân chia theo ID | `startId`, `endExclusive` | Biên overlap hoặc đổi giữa restart |
| Cửa sổ thời gian | `fromInclusive`, `toExclusive` | Timezone, late arrivals, ranh giới inclusive |
| Group nhiều file | `manifestGroupId=group-17` | Danh sách file khác đi khi restart |

Không cần ép mọi loại input thành một String. Với range, hai key dạng số giúp kiểm tra biên rõ hơn. Với file/object, input key là một **con trỏ**; để reproducible, giữ bản version của object hoặc manifest tương ứng.

## 5. Ví dụ dữ liệu: manifest đóng băng trước khi chạy

Giả sử PostgreSQL đã có bảng manifest lưu shard của snapshot và bảng record nguồn. Một `order_id` chỉ thuộc một shard trong cùng snapshot.

~~~sql
CREATE TABLE batch_input_manifest (
    snapshot_id VARCHAR(100) NOT NULL,
    shard_id    INTEGER      NOT NULL,
    input_key   VARCHAR(256) NOT NULL,
    PRIMARY KEY (snapshot_id, shard_id),
    UNIQUE (snapshot_id, input_key)
);

CREATE TABLE batch_input_order (
    snapshot_id VARCHAR(100) NOT NULL,
    input_key   VARCHAR(256) NOT NULL,
    order_id    BIGINT       NOT NULL,
    payload     TEXT         NOT NULL,
    PRIMARY KEY (snapshot_id, order_id),
    FOREIGN KEY (snapshot_id, input_key)
        REFERENCES batch_input_manifest(snapshot_id, input_key)
);

CREATE INDEX idx_batch_input_by_key
    ON batch_input_order(snapshot_id, input_key, order_id);

CREATE TABLE processed_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id    BIGINT       NOT NULL,
    payload     TEXT         NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

Manifest minh họa:

~~~sql
INSERT INTO batch_input_manifest(snapshot_id, shard_id, input_key)
VALUES
 ('orders-2026-11-25', 0, 'orders/2026-11-25/shard-0000'),
 ('orders-2026-11-25', 1, 'orders/2026-11-25/shard-0001'),
 ('orders-2026-11-25', 2, 'orders/2026-11-25/shard-0002'),
 ('orders-2026-11-25', 3, 'orders/2026-11-25/shard-0003');
~~~

Giả định bảng nguồn đã được nạp và **đóng snapshot** trước khi manager chạy. Record đã nạp không được chuyển shard, sửa payload hay xóa tùy ý cho đến khi mọi attempt hợp lệ của `JobInstance` kết thúc.

Ràng buộc `PRIMARY KEY(snapshot_id, order_id)` buộc một order chỉ thuộc một input key. Foreign key bắt buộc key có trong manifest. Nhưng schema không tự chứng minh manager đã tạo một partition cho **mọi** shard; cần test partitioner và đối soát output.

Nếu dữ liệu ở nhiều bảng cần chốt cùng thời điểm, phải định nghĩa isolation/snapshot nhất quán, không dựa vào việc các thread đều có cùng string `snapshotId`.

## 6. Java 17, Spring Batch 5.x: cấu hình end-to-end

Ví dụ sau đặt input key trong `Partitioner`, bind nó trong `@StepScope` reader và tạo job local partitioning. Giả định Spring Boot đã cấu hình `JobRepository`, `DataSource`, `JdbcTemplate` và `PlatformTransactionManager` thích hợp. `snapshotId` được truyền khi launch job như **identifying `JobParameter`**.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
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
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

record InputShard(int shardId, String inputKey) {}
record OrderRow(String snapshotId, long orderId, String payload) {}

@Configuration
public class InputKeyPartitionConfiguration {

    @Bean("inputKeyPartitioner")
    @StepScope
    Partitioner inputKeyPartitioner(
            JdbcTemplate jdbc,
            @Value("#{jobParameters['snapshotId']}") String snapshotId) {

        if (snapshotId == null || snapshotId.isBlank()) {
            throw new IllegalArgumentException("Missing snapshotId");
        }

        return gridSize -> {
            if (gridSize <= 0) {
                throw new IllegalArgumentException("Invalid gridSize");
            }

            List<InputShard> shards = jdbc.query("""
                SELECT shard_id, input_key
                FROM batch_input_manifest
                WHERE snapshot_id = ?
                ORDER BY shard_id
                """,
                (rs, n) -> new InputShard(
                    rs.getInt("shard_id"), rs.getString("input_key")),
                snapshotId);

            if (shards.isEmpty()) {
                throw new IllegalStateException("Snapshot has no shards");
            }

            Map<String, ExecutionContext> partitions =
                    new LinkedHashMap<>();

            for (InputShard shard : shards) {
                if (shard.shardId() < 0
                        || shard.inputKey() == null
                        || shard.inputKey().isBlank()) {
                    throw new IllegalStateException("Invalid input shard");
                }

                // Shard ID trong manifest phải bất biến khi restart.
                String name = String.format(
                        Locale.ROOT, "partition%04d", shard.shardId());

                ExecutionContext context = new ExecutionContext();
                context.putString("inputKey", shard.inputKey());
                partitions.put(name, context);
            }

            // Số partition theo manifest, gridSize chỉ là hint.
            return partitions;
        };
    }

    @Bean("workerReader")
    @StepScope
    JdbcCursorItemReader<OrderRow> workerReader(
            DataSource dataSource,
            @Value("#{jobParameters['snapshotId']}") String snapshotId,
            @Value("#{stepExecutionContext['inputKey']}") String inputKey) {

        if (snapshotId == null || snapshotId.isBlank()
                || inputKey == null || inputKey.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing snapshotId or inputKey");
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("workerReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT order_id, payload
                    FROM batch_input_order
                    WHERE snapshot_id = ?
                      AND input_key = ?
                    ORDER BY order_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setString(2, inputKey);
                })
                .rowMapper((rs, n) -> new OrderRow(
                    snapshotId,
                    rs.getLong("order_id"),
                    rs.getString("payload")))
                .saveState(true)
                .build();
    }

    @Bean("workerWriter")
    ItemWriter<OrderRow> workerWriter(JdbcTemplate jdbc) {
        return chunk -> {
            for (OrderRow row : chunk) {
                jdbc.update("""
                    INSERT INTO processed_order(snapshot_id, order_id, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT (snapshot_id, order_id) DO UPDATE
                    SET payload = EXCLUDED.payload
                    WHERE processed_order.payload IS DISTINCT FROM
                          EXCLUDED.payload
                    """, row.snapshotId(), row.orderId(), row.payload());
            }
        };
    }

    @Bean("workerStep")
    Step workerStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("workerReader") JdbcCursorItemReader<OrderRow> reader,
            @Qualifier("workerWriter") ItemWriter<OrderRow> writer) {

        return new StepBuilder("workerStep", repository)
                .<OrderRow, OrderRow>chunk(200, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean("inputKeyExecutor")
    ThreadPoolTaskExecutor inputKeyExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("input-key-");
        executor.initialize();
        return executor;
    }

    @Bean("managerStep")
    Step managerStep(
            JobRepository repository,
            @Qualifier("workerStep") Step workerStep,
            @Qualifier("inputKeyPartitioner") Partitioner partitioner,
            @Qualifier("inputKeyExecutor") TaskExecutor executor) {

        return new StepBuilder("managerStep", repository)
                .partitioner("workerStep", partitioner)
                .step(workerStep)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean("importOrdersJob")
    Job importOrdersJob(
            JobRepository repository,
            @Qualifier("managerStep") Step managerStep) {

        return new JobBuilder("importOrdersJob", repository)
                .start(managerStep)
                .build();
    }
}
~~~

### Các bước truyền input key

1. Manager khởi động `managerStep` và gọi `inputKeyPartitioner`.
2. Partitioner đọc các shard của `snapshotId` trong manifest theo `ORDER BY shard_id`.
3. Với mỗi shard, tạo **một `ExecutionContext`** và gọi `putString("inputKey", shard.inputKey())`.
4. Spring Batch tạo/quản lý `StepExecution` của `workerStep:partitionXXXX`.
5. Khi worker step chạy, bean reader `@StepScope` được tạo với `inputKey` của **chính partition đó**.
6. Reader dùng prepared statement `snapshot_id = ? AND input_key = ?` để chỉ đọc đúng shard.
7. `JdbcCursorItemReader` đọc theo `order_id` ổn định, `ItemStream` lưu tiến độ vào context của worker.
8. Writer ghi output bằng business key `(snapshot_id,order_id)`; replay cùng snapshot không tạo thêm dòng trùng.
9. Manager tổng hợp trạng thái các worker theo flow/step transition đã cấu hình.

Bài tập trung truyền input key nên lược bỏ bước tạo snapshot và bước đối soát sau manager. Trong ứng dụng thật, cần chạy bước chuẩn bị/đóng snapshot **trước** manager, và publish kết quả **sau** manager thành công.

### Vì sao `@StepScope` là điểm quan trọng?

Nếu reader là singleton, mọi partition có thể dùng **cùng cursor/state**, dù chúng có input key khác nhau. `@StepScope` tạo instance reader theo `StepExecution`; trong partitioning, mỗi worker step execution sở hữu reader và checkpoint riêng.

`@StepScope` **không đồng nghĩa `@ThreadScope`**. Nếu ứng dụng tự chạy nhiều thread trong **cùng `StepExecution`**, chúng vẫn có thể tham chiếu cùng reader step-scoped. Đó là một bài toán thread safety khác, không được giải quyết chỉ bằng annotation.

Return type của bean ở ví dụ là `JdbcCursorItemReader<OrderRow>`, một kiểu cụ thể triển khai `ItemStream`, giúp framework nhận diện lifecycle `open/update/close` và checkpoint.

## 7. Input key là file, object key hay một nhóm nguồn

Ví dụ trên dùng bảng DB. Một ứng dụng khác có thể truyền khóa file:

~~~text
snapshotId=orders-2026-11-25
inputKey=orders/2026-11-25/shard-0001.csv
~~~

Worker dùng input key để tra resource theo một prefix/bucket được phép:

~~~text
StepExecutionContext[inputKey]
          ↓
Step-scoped resource resolver
          ↓
Versioned object / shared file / manifest group
          ↓
FlatFileItemReader hoặc MultiResourceItemReader
          ↓
ItemProcessor / ItemWriter
~~~

| Loại nguồn | Điều kiện để worker khác đọc được | Lưu ý restart |
| --- | --- | --- |
| Shared filesystem | Worker mount cùng file ở đường dẫn hợp lệ | File bất biến và có offset ổn định |
| Object storage | Bucket/key/version, IAM và network phù hợp | Giữ object version/checksum |
| Manifest nhiều file | File list đã đóng băng, thứ tự cố định | Checkpoint gồm file index và offset |
| DB theo shard | SQL predicate và index đúng khóa | Snapshot bất biến, `ORDER BY` duy nhất |
| Time/range | Biên dạng typed, nguồn hỗ trợ lọc | Không thay biên lúc restart |

Đừng lấy một path local của manager như `C:\temp\orders.csv` hoặc `/tmp/orders.csv` làm input key rồi kỳ vọng pod ở máy khác nhìn thấy file. Đừng mặc định `FileSystemResource` đọc được mọi URI của object storage; cần resource adapter hoặc staging tương thích.

Có thể dùng riêng các key `startId`, `endExclusive` thay vì nhét range vào một chuỗi. Bất kể cách đặt tên, **ý nghĩa và kiểu của key cần được version hóa trong contract** nếu manager và worker có thể chạy hai phiên bản ứng dụng.

## 8. Restart: tên partition và input key phải giữ cùng nghĩa

Giả sử lần đầu chạy:

| Partition | Input key | Trạng thái |
| --- | --- | --- |
| `partition0000` | `.../shard-0000` | `COMPLETED` |
| `partition0001` | `.../shard-0001` | `COMPLETED` |
| `partition0002` | `.../shard-0002` | `FAILED` sau 120 chunk đã commit |
| `partition0003` | `.../shard-0003` | JVM chết khi đang xử lý |

Khi restart **cùng `JobInstance`**, Spring Batch dùng metadata và context đã lưu để xác định partition cần tiếp tục; các partition đã hoàn thành thường được bỏ qua theo restart policy mặc định.

Nếu `partition0002` trong lần đầu đọc `shard-0002` nhưng sau deploy bị gán thành `shard-0099`, checkpoint đọc được 120 chunk cũ **không còn tương ứng với input mới**. Đó là một lỗi nghiêm trọng dù Java code vẫn chạy.

### Sáu bất biến phục hồi

1. **Identifying `snapshotId` giữ nguyên** khi mục tiêu là restart cùng lần chạy logic; đừng thêm UUID/timestamp identifying để lách trạng thái job.
2. **Tên partition ổn định**: `partition0002` vẫn trỏ cùng shard; `shard_id` của manifest không bị tái đánh số.
3. **Nội dung input không đổi**: cùng key tới cùng snapshot/file version/checksum, không chỉ cùng đường dẫn string.
4. **Reader và checkpoint tương thích**: thứ tự `ORDER BY` xác định, `ItemStream` có tên/state không bị đổi vô cớ.
5. **Writer replay-safe**: cùng record được xử lý lại không tạo duplicate hoặc side effect sai.
6. **Metadata repository bền vững**: state job/step không bị xóa hoặc đổi DB trong quá trình phục hồi.

### `PartitionNameProvider`

Spring Batch có interface `PartitionNameProvider` cho phép cung cấp riêng danh sách tên partition. Khi sử dụng, danh sách tên provider trả về lúc restart phải **khớp với tên của `Partitioner`** ở lần chạy trước. Nó có ích khi tạo đầy đủ input context rất tốn kém, nhưng không cho phép thay mapping tên → input key tùy ý.

Tương tự, đừng thay `gridSize` hoặc thuật toán chia sao cho cùng partition name mang một shard/range khác nếu chưa có chiến lược tương thích restart đã được kiểm thử.

### Cửa sổ mất đồng bộ khi commit

Nếu worker commit dữ liệu trong business DB nhưng checkpoint/ack ở metadata chưa kịp lưu, lần restart có thể đọc/ghi lại một số item. Điều này đặc biệt cần chú ý khi `JobRepository` dùng datasource/transaction khác business DB.

**Input key đúng không bảo đảm exactly-once.** Writer ở DB cần unique key, upsert/version condition hoặc operation ledger. API/message/file ngoài transaction còn cần idempotency key, transactional outbox và reconciliation phù hợp.

## 9. Input key tĩnh khác checkpoint động

Một worker `ExecutionContext` có thể chứa cả assignment và state chạy thực tế:

| Thành phần | Ví dụ | Ai cập nhật? | Có nên đổi mỗi chunk? |
| --- | --- | --- | --- |
| Assignment tĩnh | `inputKey=.../shard-0002` | `Partitioner` | Không |
| Job identity | `snapshotId=orders-2026-11-25` | Job launcher/JobParameters | Không |
| Reader checkpoint | `workerReader.read.count` hoặc key nội bộ reader | `ItemStream` | Có theo lifecycle |
| Writer checkpoint | Key nội bộ của writer có state | `ItemStream` writer | Có nếu cần |
| Business output | Dòng `processed_order` đã commit | Business DB | Có theo transaction |
| Metrics tạm | read/write/rollback count | Framework/monitoring | Có, không thay DB |

Đừng lưu toàn bộ payload item trong `ExecutionContext`. Context được persist/serialize ở `JobRepository`, có thể được backup và cần đọc lại khi restart. Các object lớn hoặc custom class dễ làm metadata chậm, tăng độ rủi ro khi nâng phiên bản serializer.

### Vòng đời state của reader

~~~mermaid
sequenceDiagram
    participant S as Worker Step
    participant I as ItemStream Reader
    participant E as StepExecutionContext
    participant D as DB / JobRepository
    S->>I: open(E)
    loop Mỗi chunk
        S->>I: read() các item
        S->>D: Writer trong transaction chunk
        S->>I: update(E)
        S->>D: Persist checkpoint / commit theo cấu hình
    end
    S->>I: close()
~~~

Sơ đồ chỉ diễn tả ý tưởng. Điểm commit dữ liệu và metadata có thể thuộc các transaction vật lý khác nhau theo cấu hình. Vì vậy phải kiểm thử lỗi tại ranh giới commit và có cơ chế ghi idempotent.

Nếu cần tự lưu watermark, hãy dùng key checkpoint **khác `inputKey`**, cập nhật trong lifecycle phù hợp và chứng minh state không vượt quá những bản ghi đã commit.

## 10. Đảm bảo bảo mật và tính hợp lệ của input key

Input key là dữ liệu cấu hình được persist; cần validate trước khi worker dùng để truy cập DB hoặc resource.

- **Missing key:** `inputKey` null/blank phải fail fast, không fallback đọc toàn bộ nguồn.
- **Namespace:** key phải thuộc `snapshotId` và manifest đã khóa.
- **SQL:** dùng prepared parameter, không nối key trực tiếp thành SQL.
- **Path traversal:** nếu xây path từ key, chuẩn hóa và chỉ chấp nhận prefix/directory được phép.
- **Object URI:** chỉ dùng endpoint/bucket/host được phép, tránh SSRF nếu input không đáng tin cậy.
- **Secrets:** không lưu password, token hoặc access key trong context; lấy từ credential runtime.
- **Immutable content:** đối chiếu checksum, generation/version hoặc manifest trước khi resume.
- **Logs:** ẩn tenant/khóa nhạy cảm nếu input key mang dữ liệu định danh, tránh dump context vô điều kiện.
- **Protocol/schema:** manager và worker thống nhất key name/type, hỗ trợ rolling upgrade.

Một anti-pattern:

~~~java
// Sai: key thiếu thì đọc toàn bộ input.
String sql = inputKey == null
        ? "SELECT * FROM batch_input_order"
        : "SELECT * FROM batch_input_order WHERE input_key = ?";
~~~

Thay bằng fail fast:

~~~java
if (inputKey == null || inputKey.isBlank()) {
    throw new IllegalArgumentException("Missing worker inputKey");
}
~~~

Một worker không nhận được input key mà quét cả bảng có thể vừa **làm sai dữ liệu**, vừa tạo full scan khiến toàn hệ thống chậm hơn.

## 11. Local và remote partitioning: cùng contract, khác hạ tầng

| Khía cạnh | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Worker chạy ở đâu? | Thread trong một JVM | JVM/pod ở máy khác |
| `inputKey` đến từ đâu? | Context của worker `StepExecution` | Context của `StepExecution` được gửi/tra theo protocol |
| Reader được tạo ở đâu? | Worker thread cùng process | Worker JVM trong `@StepScope` |
| Nguồn dữ liệu | Cùng hạ tầng local/DB | Mỗi worker phải có network/resource permission |
| Fault model | JVM crash dừng tất cả worker trong đó | Worker/broker/network timeout, reply thất lạc |
| Nguồn metadata | `JobRepository` dùng cho các step | Repository và protocol cần nhất quán giữa manager/worker |

Worker remote **không nhận nguyên object reader, JDBC connection hoặc transaction của manager**. Nó nhận/tra thông tin partition và tự xây reader với input key của chính nó. Với một số cơ chế Spring Batch Integration, message mang ID của `StepExecution` và worker dùng repository để khôi phục context; cấu trúc message chính xác cần đối chiếu theo phiên bản đang triển khai.

**Remote chunking là mô hình khác:** manager thường sở hữu reader và gửi chunk item, worker xử lý/ghi. Không ép cơ chế input key cho reader của remote partitioning vào remote chunking khi worker không sở hữu reader.

Khi worker đã commit nhưng reply/ACK thất lạc, một partition/chunk có thể được giao lại. Worker mới phải ghi idempotent; nếu worker cũ còn sống khi timeout hết, cần owner/fencing hoặc cơ chế takeover an toàn.

## 12. Đánh giá hiệu năng: key chính xác chưa đủ để scale

Một key giúp phân chia dữ liệu đúng, nhưng throughput còn phụ thuộc:

| Chỉ số | Rủi ro | Hướng kiểm chứng |
| --- | --- | --- |
| Item count theo `inputKey` | Shard lệch tải, một worker thành straggler | Đo count, byte, duration mỗi shard |
| Query plan | Mỗi worker full scan vì thiếu index | `EXPLAIN` và index `(snapshot_id,input_key,order_id)` |
| JDBC active/pending | Tăng worker gây cạn pool | Đo pool và quota DB toàn cluster |
| DB lock/commit latency | Output cùng tranh một row aggregate | Upsert theo business key, partial aggregate |
| Checkpoint/metadata | Quá nhiều partition nhỏ làm chậm repository | Group shard theo chi phí thích hợp |
| Heap/GC, cursor | Nhiều reader giữ bộ nhớ/connection | Bounded executor, chunk/fetch size |
| Retry/restart duration | Input drift, writer không idempotent | Manifest bất biến và fault injection |

Ví dụ có 2.000 file rất nhỏ, mỗi file xử lý 0,2 giây. Nếu một file tạo một `StepExecution`, overhead dispatch/metadata có thể vượt lợi ích phân tán. Nên cân nhắc gom thành 40 nhóm cố định; mỗi nhóm có một `manifestGroupId` và danh sách file đã khóa. Khi đó reader phải lưu cả file index và offset để restart hợp lệ.

`gridSize=40` không đồng nghĩa 40 thread hoặc 40 JVM chạy đồng thời. `TaskExecutor`/`PartitionHandler`, CPU, DB/API, broker và số worker slots mới quyết định concurrency thực.

## 13. Quan sát các partition trong JobRepository

Với repository JDBC chuẩn, metadata thường nằm trong `BATCH_STEP_EXECUTION` và `BATCH_STEP_EXECUTION_CONTEXT`. Ví dụ truy vấn PostgreSQL:

~~~sql
SELECT
    s.STEP_EXECUTION_ID,
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

`SHORT_CONTEXT` là biểu diễn state đã serialize/rút gọn và **không phải JSON schema ổn định** để ứng dụng SQL parse input key. Dùng API `JobExplorer` và instrumentation nếu cần đọc dữ liệu state chính xác.

Log có thể mang:

~~~text
jobExecutionId=1234
step=workerStep:partition0002
inputKey=orders/2026-11-25/shard-0002
workerHost=worker-pod-03
status=COMPLETED
readCount=300000
writeCount=300000
~~~

Đây là format log gợi ý, không phải metric mặc định. Với số shard lớn, tránh gắn `inputKey`/`orderId` có cardinality rất cao lên metric time-series; dùng logs/traces có giới hạn và bảo vệ thông tin nhạy cảm.

## 14. Các lỗi dễ gặp và cách phòng ngừa

| Anti-pattern | Hậu quả | Khắc phục |
| --- | --- | --- |
| Tất cả worker dùng singleton reader với key hardcode | Đọc cùng input | `@StepScope` + context |
| Dùng chung một `ExecutionContext` object trong partitioner | Key cuối có thể ghi đè mọi entry | `new ExecutionContext()` mỗi partition |
| Key null thì tự quét toàn DB | Bỏ qua phân công, gây duplicate | Fail fast |
| Sinh tên partition theo UUID hiện tại | Restart không ghép metadata cũ | Tên deterministic theo manifest |
| Giữ tên partition nhưng đổi input key | Checkpoint sai nguồn | Manifest bất biến theo `JobInstance` |
| Object tại key bị overwrite | Offset cũ không còn hợp lệ | Version/checksum/snapshot |
| Đặt cả payload lớn trong context | Metadata chậm, serializer lỗi | Chỉ đặt ID/URI nhỏ |
| Dùng `JobExecutionContext` để cập nhật key từ nhiều worker | Race và state lưu không phù hợp | `StepExecutionContext` riêng |
| Nhầm input key là business dedup key | Duplicate order xuyên shard | Unique `(snapshotId,orderId)` |
| Tưởng `@StepScope` cô lập theo thread | Có thể chia sẻ trong cùng `StepExecution` | Thiết kế đúng execution model |
| Tăng partition nhưng reader không có index | Nhiều full scan tranh I/O | Index và benchmark query |
| Worker commit nhưng reply mất | Replay gây side effect kép | Idempotent writer/reconciliation |
| Truyền local path cho worker remote | Không tìm thấy file | Storage chung/versioned |
| Trùng checkpoint key giữa hai ItemStream | State bị ghi đè | Tên stream khác nhau |

## 15. Bộ kiểm thử cần có

1. **Manifest:** không có key null/trùng, `shard_id` bất biến, số shard đủ và snapshot đã đóng.
2. **Partitioner:** kiểm thử 1, 4 và nhiều shard; mỗi name có một context riêng và inputKey đúng.
3. **Late binding:** hai worker nhận key khác nhau và chỉ đọc đúng hàng của shard tương ứng.
4. **Missing key:** một worker thiếu `inputKey` phải fail, không đọc toàn DB.
5. **Bao phủ:** các record nguồn chỉ thuộc một shard, mọi shard được phân công.
6. **Checkpoint:** worker commit vài chunk rồi fail; restart đúng inputKey và resume state hợp lệ.
7. **Manifest drift:** cố tình đổi mapping, kiểm tra cơ chế từ chối hoặc ngăn thay đổi.
8. **Retry sau commit:** giả lập commit thành công nhưng metadata/reply lỗi; writer không nhân đôi business effect.
9. **JVM crash:** phục hồi các partition chưa hoàn thành, xác minh worker cũ dừng và trạng thái repository.
10. **Remote visibility:** worker trên pod khác vẫn truy cập input source với cùng key/version.
11. **Resource limits:** tăng concurrency 1 → 2 → 4 → 8, đo throughput, connection, lock, heap và straggler.
12. **Reconciliation:** đích đủ business keys, đúng payload/version, không có side effect thừa.

Với ví dụ copy input sang output, kiểm tra record thiếu bằng SQL:

~~~sql
SELECT order_id
FROM batch_input_order
WHERE snapshot_id = :snapshotId
EXCEPT
SELECT order_id
FROM processed_order
WHERE snapshot_id = :snapshotId;
~~~

Kiểm tra đích thừa bằng cách đổi thứ tự hai vế. Kiểm tra payload sai:

~~~sql
SELECT s.order_id
FROM batch_input_order s
JOIN processed_order t
  ON t.snapshot_id = s.snapshot_id
 AND t.order_id = s.order_id
WHERE s.snapshot_id = :snapshotId
  AND t.payload IS DISTINCT FROM s.payload;
~~~

Nếu nghiệp vụ biến đổi payload hợp lệ, dùng phép đối chiếu với **kết quả kỳ vọng**, không bắt output giống nguyên input.

## 16. Bài tập tình huống

Một snapshot có ba shard:

~~~text
partition0000 -> orders/2026-11-25/A
partition0001 -> orders/2026-11-25/B
partition0002 -> orders/2026-11-25/C
~~~

Lần chạy đầu:

- `partition0000` `COMPLETED`.
- `partition0001` đã commit 50 chunk, rồi `FAILED`.
- `partition0002` bị dừng giữa một chunk.
- Trước khi restart, quản trị viên sửa manifest để `partition0001` nay trỏ từ `B` sang `D`; đồng thời object `C` bị ghi đè nhưng vẫn giữ nguyên key.

**Câu hỏi:**

1. Vì sao không được đổi `B` sang `D` khi tiếp tục cùng `JobInstance`?
2. Vì sao việc key `C` giữ nguyên chuỗi chưa đủ để restart an toàn?
3. Viết biểu thức late binding để worker lấy `inputKey`.
4. Nhiều worker dùng cùng tên key `inputKey` có bị ghi đè lẫn nhau không?
5. Nếu writer dùng `UPDATE total = total + :delta`, replay chunk có idempotent không?
6. Khi chuyển sang remote partitioning, có thể gửi nguyên object `JdbcCursorItemReader` từ manager cho worker không?
7. Nếu một snapshot chứa 5.000 file nhỏ, cách giảm overhead partition mà vẫn restart đúng là gì?

**Gợi ý:** (1) Checkpoint cũ gắn với B; đổi sang D có thể bỏ sót hoặc lặp. (2) Cần version/checksum và snapshot bất biến. (3) `@Value("#{stepExecutionContext['inputKey']}")` trong bean `@StepScope`. (4) Không, nếu từng worker có `StepExecutionContext` riêng. (5) Không; cần ledger/partial aggregate hoặc phép ghi idempotent. (6) Không; truyền định danh/state và để worker tự dựng reader. (7) Gộp thành những manifest groups cố định, checkpoint file index/offset và đo tổng overhead.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): `Partitioner`, `ExecutionContext` và cách gán input vào worker.
- [Spring Batch 5.2 Reference – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): cú pháp partition manager/worker dòng 5.x.
- [Spring Batch Reference – Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope`, `stepExecutionContext` và `ItemStream` proxy.
- [Spring Batch 5.2 Reference – Late Binding](https://docs.spring.io/spring-batch/reference/5.2/step/late-binding.html): ví dụ bean step-scoped của Spring Batch 5.x.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `StepExecution` và `ExecutionContext`.
- [Spring Batch Reference – Item Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/index.html): reader state và checkpoint.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote manager/worker qua middleware.

## Ghi nhớ

**Đặt input key cho worker là gắn một định danh nguồn dữ liệu ổn định vào `StepExecutionContext` của mỗi partition, rồi để reader `@StepScope` lấy giá trị đó khi worker thực thi.** Tên key là contract của ứng dụng; giá trị phải tương ứng với snapshot/manifest của `JobInstance` và không đổi nghĩa khi restart. Cần giữ reader/checkpoint tách biệt, dùng writer idempotent, validate quyền truy cập nguồn, đối soát dữ liệu và kiểm soát tài nguyên trước khi mở rộng số worker trên một hoặc nhiều máy.
