# Batch insert và batch update trong Spring Batch

## 1. Vì sao một triệu lệnh INSERT chưa chắc phải là một triệu round-trip?

Một job tổng hợp đơn hàng cần đưa 12 triệu bản ghi từ bảng staging sang bảng đích. Nếu mỗi item được ghi bằng một lệnh `INSERT` riêng lẻ, thời gian có thể bị chi phối bởi **network round-trip**, parse/bind/execute, transaction commit và cập nhật index. Mở thêm 32 worker không chắc giúp ích: các worker có thể cùng tạo áp lực lên connection pool, WAL, unique index và row locks của database.

**Batch insert** và **batch update** là kỹ thuật gom nhiều thao tác ghi dữ liệu thành một hoặc một số lượt thực thi có tổ chức. Trong Spring Batch, kỹ thuật này thường phối hợp với **chunk-oriented step**, `JdbcBatchItemWriter` và JDBC driver, nhưng ba khái niệm không đồng nhất:

- **Spring Batch chunk** quyết định ranh giới xử lý/commit/checkpoint của một nhóm item.
- **JDBC batch** gom nhiều lần bind cùng một câu SQL để driver thực thi với ít overhead hơn.
- **Set-based SQL** thao tác trực tiếp trên một tập hàng trong database, ví dụ `INSERT ... SELECT` hoặc `UPDATE ... FROM`, đôi khi còn hiệu quả hơn item-oriented JDBC batching.

Bài **“Batch insert và batch update”** thuộc chương **Database scaling** trong module `SPRING_BATCH_SCALING_OPERATIONS`. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán phù hợp; đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và vận hành job dựa trên tài nguyên thực tế.

Sau bài học, bạn sẽ:

1. Phân biệt được `chunk size`, `JDBC batch size` và số lượng statement/transaction thực tế.
2. Cấu hình `JdbcBatchItemWriter` để insert/update bằng prepared statement và tham số an toàn.
3. Hiểu ý nghĩa **update count**, `assertUpdates`, optimistic locking và xử lý record không được cập nhật.
4. Thiết kế **idempotency** cho duplicate delivery, crash sau commit và restart.
5. So sánh batch INSERT, PostgreSQL UPSERT và set-based staging/merge.
6. Đo DB throughput, WAL/lock/I/O, pool pending, p95 latency để chọn batch/chunk/concurrency.
7. Viết kiểm thử fault injection và runbook khi worker gặp deadlock, duplicate key hoặc database timeout.

**Phiên bản ví dụ:** Java 17+, Spring Batch **5.2.x**, Spring Boot **3.x** và PostgreSQL. Các nguyên tắc áp dụng cho những phiên bản mới hơn, nhưng API/import của Spring Batch 6.x cần đối chiếu với phiên bản triển khai. Ví dụ PostgreSQL không mặc nhiên dùng được nguyên vẹn với MySQL, SQL Server hoặc Oracle.

## 2. Ba tầng batching không giống nhau

~~~mermaid
flowchart LR
    R[ItemReader] --> P[ItemProcessor]
    P --> C["Chunk: 500 items"]
    C --> W[JdbcBatchItemWriter]
    W --> B["JDBC PreparedStatement batch"]
    B --> D[(PostgreSQL)]
    C <-->|Commit và checkpoint| J[(JobRepository)]
~~~

### 2.1. Spring Batch chunk

Một step chunk-oriented được khai báo, chẳng hạn `chunk(500, transactionManager)`. Framework thường tích lũy tối đa 500 item để ghi trước khi kết thúc một transaction; tùy filter, EOF, retry/skip và reader semantics, số item thực sự tới writer có thể ít hơn.

~~~text
Đọc 500 item
  -> Process 500 item (có thể filter)
  -> Writer nhận một Chunk với số item thực tế
  -> Transaction commit
  -> ItemStream/StepExecution metadata được cập nhật theo lifecycle
~~~

Điều này **không** có nghĩa framework tạo 500 connection hay mọi statement trong chunk được DB commit độc lập. Với transaction manager và writer đúng cấu hình, business writes trong một chunk được commit/rollback theo giao dịch của nó. Khi metadata và business database là hai resource manager riêng, **không mặc định** commit hai bên nguyên tử.

### 2.2. JDBC batch

Với JDBC tiêu chuẩn, một `PreparedStatement` có thể dùng:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "INSERT INTO processed_orders "
           + "(source_snapshot, source_order_id, customer_id, amount_cents) "
           + "VALUES (?, ?, ?, ?)")) {

    for (OrderRow item : orders) {
        ps.setString(1, item.snapshotKey());
        ps.setLong(2, item.id());
        ps.setLong(3, item.customerId());
        ps.setLong(4, item.amountCents());
        ps.addBatch();
    }
    int[] counts = ps.executeBatch();
}
~~~

Đây chỉ là **một đoạn giải thích JDBC**, không phải writer Spring Batch hoàn chỉnh: cần khai báo/import các kiểu `OrderRow`, `Connection`, `PreparedStatement`, `DataSource`, và **transaction management**. Nếu tự mở connection bên ngoài Spring transaction, không được mặc định thao tác ấy tự tham gia chunk transaction. Khi viết ứng dụng Spring Batch, ưu tiên `JdbcBatchItemWriter` hoặc `JdbcTemplate.batchUpdate` và để framework quản lý transaction.

`executeBatch()` có thể giảm overhead ở client/driver, nhưng **không cam kết** driver gửi đúng một request SQL qua mạng hoặc một statement duy nhất tới server. Hành vi phụ thuộc driver, câu SQL, cấu hình và kích thước batch.

### 2.3. Set-based SQL

~~~sql
INSERT INTO processed_orders
    (source_snapshot, source_order_id, customer_id, amount_cents)
SELECT snapshot_key, id, customer_id, amount_cents
FROM incoming_orders
WHERE snapshot_key = :snapshotKey
  AND id >= :minId
  AND id < :maxId
ON CONFLICT (source_snapshot, source_order_id) DO NOTHING;
~~~

Database tự thực hiện thao tác **theo tập hàng**, không cần Java đọc rồi bind từng item. Đây là lựa chọn mạnh khi chỉ di chuyển/biến đổi SQL đơn giản và không cần processor Java phức tạp. Nó có thể gây transaction/lock/WAL rất lớn nếu quét một tập quá rộng; vẫn cần phân lô, checkpoint và kiểm soát restart.

| Tiêu chí | Item + JDBC batch | Set-based SQL |
|---|---|---|
| Biến đổi Java phức tạp | Linh hoạt với `ItemProcessor` | Thường khó, cần diễn đạt bằng SQL |
| Số lần chuyển dữ liệu qua ứng dụng | Có đọc và bind item | Có thể không đưa item qua JVM |
| Checkpoint | Theo chunk/reader `ItemStream` | Phải thiết kế theo range hoặc đơn vị SQL riêng |
| Retry một item lỗi | Có cơ chế fault tolerance nhưng cần hiểu batch failure | Thường retry cả đơn vị SQL/set, hoặc tách tập để xác định row lỗi |
| Lock/WAL/IO | Phụ thuộc batch/chunk và index | Phụ thuộc số row tác động trong mỗi statement/transaction |
| Tính đúng | Cần unique key và writer idempotent | Vẫn cần unique key, consistency và restart |

Không có kỹ thuật nào luôn nhanh nhất. Đo cả **thời gian xử lý**, **DB resource usage** và **tính đúng** trên dữ liệu thực.

## 3. Bài toán xuyên suốt: xử lý đơn hàng từ immutable snapshot

Một ETL nhận snapshot cố định `snap-2026-11-25-v1`. Input là các row trong `incoming_orders`; output là `processed_orders`. Mỗi đơn hàng có ID duy nhất trong nguồn, `snapshot_key` bất biến và các cột dữ liệu không thay đổi trong lúc job chạy.

~~~sql
CREATE TABLE incoming_orders (
    id            BIGINT PRIMARY KEY,
    snapshot_key  VARCHAR(96) NOT NULL,
    customer_id   BIGINT NOT NULL,
    amount_cents  BIGINT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_incoming_orders_snapshot_id
    ON incoming_orders (snapshot_key, id);

CREATE TABLE processed_orders (
    source_snapshot VARCHAR(96) NOT NULL,
    source_order_id BIGINT NOT NULL,
    customer_id     BIGINT NOT NULL,
    amount_cents    BIGINT NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_snapshot, source_order_id)
);
~~~

Đây là schema **minh họa**. Trong hệ thống thực tế, cột money, precision, constraint, tenant key và retention phải được thiết kế theo nghiệp vụ; không dùng `BIGINT` làm số tiền nếu có nguy cơ overflow mà chưa kiểm tra. Unique key `(source_snapshot, source_order_id)` giúp nhận diện một item đã ghi cho **snapshot cụ thể**, nhưng không thể phát hiện việc nguồn tái sử dụng ID với payload khác nếu writer chỉ `DO NOTHING`.

### Contract đầu vào

~~~text
JobParameters:
  snapshotKey = "snap-2026-11-25-v1"
  fromId      = 1
  toId        = 12000001  (exclusive)

Một partition:
  [1, 500001)
  [500001, 1000001)
  ...
~~~

Mỗi worker xử lý khoảng `[fromId, toId)` không giao nhau, SQL đọc `id >= fromId AND id < toId`. Đây là cách giảm overlap khi partition theo ID; nếu dùng nhiều worker, phải có `ExecutionContext` riêng cho mỗi `StepExecution` và giữ plan cố định khi restart.

**Immutable snapshot là giả định thiết kế**, không phải kết quả tự sinh ra từ một chuỗi `snapshotKey`. Nếu upstream vẫn sửa/xóa/append vào tập snapshot trong lúc chạy, reader restart có thể bỏ sót hoặc xử lý lặp record.

## 4. JDBC batch INSERT với JdbcBatchItemWriter

`JdbcBatchItemWriter` nhận một `Chunk<T>` từ Spring Batch và dùng Spring JDBC để thực thi batch các tham số của cùng SQL. Khi sử dụng named parameters, `JdbcBatchItemWriterBuilder` có thể nhận `ItemSqlParameterSourceProvider<T>`.

### 4.1. Record và writer bean

~~~java
import java.time.OffsetDateTime;
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

record OrderRow(
        long id,
        String snapshotKey,
        long customerId,
        long amountCents,
        OffsetDateTime createdAt) {}

@Configuration
public class OrderInsertWriterConfiguration {

    @Bean
    public JdbcBatchItemWriter<OrderRow> processedOrdersWriter(
            @Qualifier("businessDataSource") DataSource businessDataSource) {

        return new JdbcBatchItemWriterBuilder<OrderRow>()
                .dataSource(businessDataSource)
                .sql("""
                    INSERT INTO processed_orders
                        (source_snapshot, source_order_id,
                         customer_id, amount_cents)
                    VALUES
                        (:snapshotKey, :id, :customerId, :amountCents)
                    ON CONFLICT
                        (source_snapshot, source_order_id) DO NOTHING
                    """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("snapshotKey", item.snapshotKey())
                                .addValue("id", item.id())
                                .addValue("customerId", item.customerId())
                                .addValue("amountCents", item.amountCents()))
                .assertUpdates(false)
                .build();
    }
}
~~~

`OrderRow` là record **package-private** trong ví dụ; khi tách ra file Java riêng, dùng `OrderRow.java` và khai báo `public` nếu cần truy cập từ package khác. `businessDataSource` phải là bean trỏ tới business DB, không vô tình trỏ sang metadata database của `JobRepository`.

**Vì sao `assertUpdates(false)`?** Với PostgreSQL `ON CONFLICT DO NOTHING`, một item đã tồn tại hợp lệ có thể ảnh hưởng **0 row**. Chế độ assert updates mặc định trong nhiều cấu hình `JdbcBatchItemWriter` yêu cầu mỗi item cập nhật ít nhất một row; nếu giữ `true`, duplicate hợp lệ có thể bị coi là lỗi. Tắt kiểm tra **chỉ khi** duplicate thực sự thuộc contract idempotency.

**Không coi `DO NOTHING` là giải pháp mọi lỗi:**

- Duplicate ID với amount/customer khác có thể bị bỏ qua mà không cảnh báo.
- Nếu cần cập nhật dữ liệu phiên bản mới, phải dùng `ON CONFLICT ... DO UPDATE` với quy tắc version/checksum.
- Unique index vẫn có thể gây contention/wait khi hai transaction insert cùng key đồng thời.
- Writer không bảo đảm side effect ở API/broker ngoài transaction được thực hiện đúng một lần.

### 4.2. Reader theo range ID cho mỗi partition

Để ghép writer với input đã đóng băng, có thể dùng reader `@StepScope`. Nó lấy `snapshotKey` từ `JobParameters` và ranh giới `fromId`/`toId` từ `StepExecutionContext`; mỗi worker `StepExecution` sẽ có một cursor riêng. Các ranh giới do `Partitioner` tạo, trong đó `toId` là **exclusive**:

~~~java
import java.time.OffsetDateTime;
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderRangeReaderConfiguration {

    @Bean
    @StepScope
    public JdbcCursorItemReader<OrderRow> orderReader(
            @Qualifier("businessDataSource") DataSource businessDataSource,
            @Value("#{jobParameters['snapshotKey']}") String snapshotKey,
            @Value("#{stepExecutionContext['fromId']}") Long fromId,
            @Value("#{stepExecutionContext['toId']}") Long toId) {

        if (snapshotKey == null || snapshotKey.isBlank()
                || fromId == null || toId == null || fromId >= toId) {
            throw new IllegalArgumentException("Invalid snapshot or ID range");
        }
        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("ordersByRangeReader")
                .dataSource(businessDataSource)
                .sql("""
                    SELECT id, snapshot_key, customer_id,
                           amount_cents, created_at
                    FROM incoming_orders
                    WHERE snapshot_key = ?
                      AND id >= ?
                      AND id < ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotKey);
                    ps.setLong(2, fromId);
                    ps.setLong(3, toId);
                })
                .rowMapper((rs, rowNum) -> new OrderRow(
                        rs.getLong("id"),
                        rs.getString("snapshot_key"),
                        rs.getLong("customer_id"),
                        rs.getLong("amount_cents"),
                        rs.getObject("created_at",
                                OffsetDateTime.class)))
                .saveState(true)
                .build();
    }
}
~~~

`OrderRow` là record từ phần 4.1. `JdbcCursorItemReader` giữ state/cursor nên phải được tạo riêng theo partition và có `ItemStream` checkpoint. Driver PostgreSQL hiện đại hỗ trợ `OffsetDateTime` cho `TIMESTAMPTZ`; với driver khác phải thử binder/mapper thực tế. **Không chia sẻ một cursor giữa các chunk thread của cùng một `StepExecution`** chỉ vì bean có `@StepScope`.

### 4.3. Một worker step dùng chunk transaction

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderInsertStepConfiguration {

    @Bean
    public Step loadOrdersStep(
            JobRepository repository,
            @Qualifier("businessTransactionManager")
            PlatformTransactionManager businessTransactionManager,
            @Qualifier("orderReader")
            JdbcCursorItemReader<OrderRow> orderReader,
            @Qualifier("processedOrdersWriter")
            JdbcBatchItemWriter<OrderRow> processedOrdersWriter) {

        return new StepBuilder("loadOrdersStep", repository)
                .<OrderRow, OrderRow>chunk(
                        500, businessTransactionManager)
                .reader(orderReader)
                .writer(processedOrdersWriter)
                .build();
    }
}
~~~

Đây là cấu hình **một worker step** dùng reader và writer ở trên; vẫn cần bean `businessTransactionManager`, `JobRepository`, `Job`/`JobLauncher` và partition manager phù hợp. Tên `businessTransactionManager` trong `@Qualifier` là contract bean ứng dụng phải cung cấp. Reader stateful dùng `@StepScope` khi partitioning, và phải quản lý `ItemStream` checkpoint; không chia sẻ một `JdbcCursorItemReader` singleton mutable giữa nhiều partition execution.

### 4.4. Transaction và checkpoint

~~~mermaid
sequenceDiagram
    participant R as ItemReader
    participant W as JdbcBatchItemWriter
    participant D as Business DB
    participant J as JobRepository
    R->>R: Đọc tới 500 item
    W->>D: Batch INSERT 500 tham số
    D-->>W: Update counts / kết quả batch
    Note over W,D: Commit/rollback theo transaction của chunk
    W-->>J: Spring Batch lưu metadata theo lifecycle
    J-->>R: Checkpoint sử dụng cho restart
~~~

Sơ đồ mô tả **dòng logic**, không cam kết commit business DB và commit metadata DB là một thao tác nguyên tử nếu hai datasource dùng hai resource manager khác nhau. Với lỗi mạng ở thời điểm commit, ứng dụng có thể không biết ngay transaction thực sự đã commit hay chưa. Unique key/idempotency và đối soát là hàng rào quan trọng.

## 5. JDBC batch UPDATE và kiểm tra row count

Trong ETL, batch update thường dùng để thay đổi trạng thái, gắn mã đối soát hoặc sửa dữ liệu theo key đã biết:

~~~sql
UPDATE processed_orders
SET amount_cents = :newAmountCents
WHERE source_snapshot = :snapshotKey
  AND source_order_id = :sourceOrderId;
~~~

Tuy nhiên, **0 updated rows** có thể mang ít nhất ba nghĩa khác nhau:

1. Row không tồn tại trong DB.
2. Row đã bị worker khác thay đổi, nên điều kiện optimistic version không còn đúng.
3. SQL cố tình có điều kiện lọc mà bản ghi không thỏa.

Vì vậy, `assertUpdates` không có một giá trị thích hợp cho mọi writer.

### 5.1. Optimistic update theo version

Mở rộng schema để theo dõi thay đổi:

~~~sql
ALTER TABLE processed_orders
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;

-- Update chỉ thành công khi row còn ở version đã đọc:
UPDATE processed_orders
SET amount_cents = :amountCents,
    version = version + 1
WHERE source_snapshot = :snapshotKey
  AND source_order_id = :sourceOrderId
  AND version = :expectedVersion;
~~~

`ALTER TABLE` là ví dụ migration, phải xem dữ liệu hiện có và thời gian lock DDL trước khi chạy production. Với optimistic locking, khi update count bằng **0**, không được âm thầm coi như thành công vì có thể đã xảy ra **lost-update conflict**.

### 5.2. Một JdbcBatchItemWriter dùng assertUpdates(true)

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

record OrderChange(
        String snapshotKey,
        long sourceOrderId,
        long amountCents,
        long expectedVersion) {}

// Phương thức @Bean đặt trong class @Configuration tương ứng.
@Bean
public JdbcBatchItemWriter<OrderChange> optimisticOrderUpdateWriter(
        DataSource businessDataSource) {

    return new JdbcBatchItemWriterBuilder<OrderChange>()
            .dataSource(businessDataSource)
            .sql("""
                UPDATE processed_orders
                SET amount_cents = :amountCents,
                    version = version + 1
                WHERE source_snapshot = :snapshotKey
                  AND source_order_id = :sourceOrderId
                  AND version = :expectedVersion
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("snapshotKey", item.snapshotKey())
                            .addValue("sourceOrderId", item.sourceOrderId())
                            .addValue("amountCents", item.amountCents())
                            .addValue("expectedVersion", item.expectedVersion()))
            .assertUpdates(true)
            .build();
}
~~~

`assertUpdates(true)` buộc writer phát hiện các item có **0 row updated** khi driver trả được row count tương ứng. Với JDBC batching, driver có thể trả các giá trị đặc biệt như `Statement.SUCCESS_NO_INFO (-2)`; không được suy diễn mọi update count trên mọi driver là số row chính xác. Nếu nghiệp vụ cần phân biệt “không tìm thấy row”, “version conflict” và “trạng thái đã đạt”, hãy dùng một writer/DAO có logic kiểm tra và đối soát phù hợp thay vì chỉ dựa vào cờ assert.

Nếu một item trong batch optimistic update thất bại, writer có thể ném exception khiến **toàn chunk transaction rollback**, tùy cách định nghĩa datasource và transaction manager. Đó có thể là hành vi đúng: cần quyết định rõ liệu conflict thuộc retry, skip hay failure; không bỏ qua trừ khi nghiệp vụ cho phép.

### 5.3. Idempotency và optimistic update khác nhau

`UPDATE ... WHERE version = expectedVersion` bảo vệ **không ghi đè thay đổi đồng thời** nhưng **không tự làm lần chạy lại idempotent**:

~~~text
Lần đầu: version 4 -> 5, commit thành công.
Worker mất ACK, cùng event được phát lại.
Lần hai: WHERE version = 4 -> cập nhật 0 row.
~~~

Row count bằng 0 có thể là **replay của event đã áp dụng** hoặc **conflict thật với event khác**. Chỉ có một business event key/version tracking rõ mới phân biệt an toàn hai tình huống. Với một sự kiện phải được áp dụng tối đa một lần, cần event ledger/unique constraint cùng transaction với cập nhật dữ liệu.

## 6. UPSERT: update khi key đã tồn tại

PostgreSQL hỗ trợ:

~~~sql
INSERT INTO processed_orders
    (source_snapshot, source_order_id, customer_id, amount_cents)
VALUES
    (:snapshotKey, :id, :customerId, :amountCents)
ON CONFLICT (source_snapshot, source_order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount_cents = EXCLUDED.amount_cents;
~~~

Khác `DO NOTHING`, nhánh `DO UPDATE` **chạm vào row hiện có** và có thể gây lock contention, WAL, trigger hoặc updated timestamp thay đổi. Với input chứa hai row cùng conflict key **trong một SQL multi-row INSERT ... ON CONFLICT DO UPDATE**, PostgreSQL có thể từ chối vì một row đích không được phép bị tác động hai lần bởi cùng statement; cần deduplicate/stabilize input trước khi gộp thành multi-row SQL.

### Một UPSERT có điều kiện theo phiên bản dữ liệu

Giả sử nguồn có `source_version` tăng đơn điệu cho mỗi order:

~~~sql
-- Cần thêm processed_orders.source_version qua migration trước:
INSERT INTO processed_orders
    (source_snapshot, source_order_id,
     customer_id, amount_cents, source_version)
VALUES
    (:snapshotKey, :id,
     :customerId, :amountCents, :sourceVersion)
ON CONFLICT (source_snapshot, source_order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount_cents = EXCLUDED.amount_cents,
    source_version = EXCLUDED.source_version
WHERE processed_orders.source_version < EXCLUDED.source_version;
~~~

Nếu incoming version bằng hoặc thấp hơn version đã ghi, `DO UPDATE` không được áp dụng. Đây là **last-version-wins** có điều kiện, **chỉ đúng** khi nguồn bảo đảm thứ tự/version tăng ổn định và sự kiện không bị mâu thuẫn với cùng version. Với các event additive (ví dụ cộng tiền), upsert thay giá trị tuyệt đối có thể **khác hoàn toàn ngữ nghĩa** so với áp dụng từng delta.

**Không mặc định `ON CONFLICT DO UPDATE` là “idempotent”**. Nếu mỗi lần retry lại thực hiện `counter = counter + EXCLUDED.delta`, một duplicate vẫn cộng hai lần. Cần unique event ID/ledger hoặc logic guard transactionally.

## 7. Tối ưu truyền lệnh: JDBC batch và PostgreSQL driver

Với PostgreSQL JDBC (pgjdbc), có tùy chọn connection `reWriteBatchedInserts=true` giúp driver **có thể** biến những batch `INSERT` phù hợp thành dạng multi-row INSERT, giảm overhead gửi lệnh.

~~~properties
# Giá trị minh họa trong cấu hình datasource/driver:
jdbc:postgresql://db.internal:5432/app?reWriteBatchedInserts=true
~~~

Đây là **tùy chọn của pgjdbc**, không phải property Spring Batch. Việc rewrite có xảy ra hay không phụ thuộc **version driver, SQL shape, batch parameterization, RETURNING/upsert và những hạn chế của driver**. Không quảng bá kết quả “N INSERT thành 1 statement” nếu chưa kiểm tra query/log/benchmark với driver đang dùng.

| Kỹ thuật | Lợi ích có thể có | Giới hạn/rủi ro |
|---|---|---|
| `PreparedStatement.addBatch/executeBatch` | Giảm overhead từ Java/driver | Còn phụ thuộc network round trips và server execution |
| `JdbcBatchItemWriter` | Tích hợp chunk transaction, lỗi và Spring Batch lifecycle | Chunk lớn giữ transaction/lock lâu |
| pgjdbc `reWriteBatchedInserts` | Có thể giảm lệnh gửi cho INSERT phù hợp | Không áp dụng cho mọi SQL hoặc driver/version |
| SQL multi-row `INSERT ... VALUES (...), (...)` | Một statement xử lý nhiều row | Giới hạn số bind params, độ dài SQL, memory và duplicate keys trong cùng statement |
| PostgreSQL `COPY` | Nạp dữ liệu lớn rất hiệu quả | API/semantics PostgreSQL riêng, cần transaction/validation/restart |
| `INSERT ... SELECT` | Không chuyển từng row qua JVM | Lock/WAL/transaction size và checkpoint theo range phải tự thiết kế |

### Parameter count và memory

Nếu một multi-row SQL có 4 parameters/row và bạn thử gộp 20.000 row, SQL có thể cần khoảng **80.000 bound parameters**. Giới hạn protocol/driver và chi phí parse/memory có thể làm chiến lược đó thất bại; không viết SQL khổng lồ không giới hạn.

JDBC batch gửi cùng prepared SQL và tham số theo từng item có cách biểu diễn khác multi-row SQL do ứng dụng tự dựng. Hãy đo **batch size**, kích thước payload, JDBC/DB latency, WAL và memory thay vì giả định gộp càng lớn càng nhanh.

### Generated keys và RETURNING

Nếu ứng dụng cần ID do database tự sinh cho từng row, một số JDBC generated-key/`RETURNING` flow có thể giảm lợi ích của batch rewrite hoặc cần đường xử lý khác. Với ETL, thường tốt hơn nếu **business key ổn định đã có sẵn ở input** và có unique constraint rõ ràng; đừng tạo ngẫu nhiên một ID mới mỗi lần retry rồi kỳ vọng writer idempotent.

## 8. SQL set-based thay thế update từng item

Khi dữ liệu đã nằm trong database, thay vì đọc 1 triệu row vào Java rồi gửi 1 triệu `UPDATE`, có thể chạy một câu SQL **theo tập**:

~~~sql
UPDATE processed_orders AS dst
SET amount_cents = src.amount_cents
FROM incoming_orders AS src
WHERE src.snapshot_key = :snapshotKey
  AND src.id >= :minId
  AND src.id < :maxId
  AND dst.source_snapshot = src.snapshot_key
  AND dst.source_order_id = src.id
  AND dst.amount_cents IS DISTINCT FROM src.amount_cents;
~~~

`IS DISTINCT FROM` là cú pháp PostgreSQL xử lý so sánh có `NULL`; ví dụ này dùng cột NOT NULL nhưng vẫn giúp diễn đạt “chỉ update khi giá trị thay đổi”. Tránh ghi lại hàng triệu row không thay đổi để giảm WAL, index maintenance và row locks. Nếu row nguồn có nhiều bản cho cùng target key, phải deduplicate trước khi `UPDATE ... FROM`; PostgreSQL không cam kết bạn chọn được “đúng bản” nếu JOIN trả nhiều source row cho một target.

### Thiết kế staging theo job/partition

Nếu processor Java cần biến đổi dữ liệu phức tạp, có thể:

~~~text
Step 1: đọc và validate nguồn
  -> JDBC batch INSERT vào staging (job_execution_id + partition_id + item_key)

Step 2: một hoặc nhiều SQL set-based theo range/partition
  -> UPDATE target FROM staging
  -> kiểm tra affected rows và business invariant

Step 3: đánh dấu đã áp dụng và cleanup staging có kiểm soát
~~~

Staging cần **khóa duy nhất** gắn với dữ liệu và attempt/job phù hợp, để restart có thể nhận biết bản ghi đã ghi. Không dùng `TRUNCATE staging` trên bảng dùng chung khi các job khác còn active; cleanup theo `job_execution_id` hoặc retention sau khi đối soát.

### Bulk insert không bỏ qua khóa ghi

`INSERT ... SELECT`, `COPY` và `UPDATE ... FROM` có thể đẩy rất nhiều write vào DB nhanh hơn; nếu nhiều worker cùng upsert một hot key, chúng vẫn có thể chờ row/unique locks. SQL set-based với một transaction cực lớn có thể giữ lock dài, tăng WAL và làm rollback nặng. Cần chia theo **khóa sở hữu ghi**, range và ngân sách concurrency, không chỉ đổi API.

## 9. Tuning chunk size, batch size và concurrency

Không có một giá trị `chunk(1000)` hay `pool.max=20` đúng cho mọi workload. Một chiến lược tuning có ba núm riêng:

1. **Chunk size**: bao nhiêu item đi vào một đơn vị transaction/commit/checkpoint.
2. **JDBC batch size**: bao nhiêu parameter sets đưa vào một lần `executeBatch` hoặc `batchUpdate`.
3. **Worker concurrency**: có bao nhiêu chunk/partition/worker đang đồng thời đọc và ghi.

Với `JdbcBatchItemWriter` thông thường, mỗi lần `write(Chunk<T>)` thường thực hiện một JDBC batch cho các item trong chunk. Do đó **batch size thực tế thường gần số item được truyền vào writer**; nhưng không phải quy tắc bất biến: filter, skip, end-of-input, custom writer hoặc chính driver có thể thay đổi số item/statement thực tế.

### 9.1. Phân biệt số row và số parameter set

~~~text
chunk(500)
    reader đọc 500 item
    processor filter 40 item
    writer nhận 460 item
    jdbc batchUpdate chạy 460 parameter sets
    ON CONFLICT DO NOTHING bỏ qua 20 duplicate

Spring Batch writeCount có thể tăng theo 460 item tới writer.
Số row thực tế INSERT thành công có thể chỉ là 440.
~~~

Đây là **kịch bản minh họa**. `writeCount` là một chỉ số về item Spring Batch xử lý ở tầng writer, không phải một phép đo vĩnh viễn của **số row mới được tạo trong database**. Với `DO NOTHING`, trigger, batching hoặc stored procedures, chênh lệch có thể còn lớn hơn. Khi cần kế toán dữ liệu, hãy đối soát unique business keys, audit tables hoặc truy vấn độc lập trên output.

### 9.2. Tăng batch size giảm overhead đến một mức

Một mô hình thời gian đơn giản:

\[
T_{\mathrm{total}}\approx
\left\lceil\frac{N}{B}\right\rceil L
+N\,t_{\mathrm{db}}
+T_{\mathrm{commit/locks/WAL}}
\]

Với `N` là số item, `B` là số item được gửi theo lô, `L` là overhead mỗi lần gọi JDBC/round-trip, `t_{\mathrm{db}}` là thời gian DB xử lý trung bình mỗi row. Đây chỉ là **ước lượng để giải thích trade-off**, không phải công thức dự đoán benchmark: driver rewrite, mạng, query plan, lock, I/O, WAL và transaction có hành vi phi tuyến.

Tăng `B` có thể giảm số lần gọi, nhưng cũng có thể:

- Giữ transaction/row lock lâu hơn.
- Tăng memory cho chunk, parameter arrays và driver buffer.
- Tạo nhiều WAL/redo log và áp lực disk flush.
- Làm rollback/retry phải xử lý lại nhiều item hơn.
- Kéo dài thời gian giữ JDBC connection và làm worker khác chờ pool.
- Tạo độ trễ lớn trên một statement khi có constraint/trigger phức tạp.

### 9.3. Bắt đầu với phép thử có kiểm soát

| Cấu hình thử nghiệm | Chunk size | Worker active | Mục tiêu đo |
|---|---:|---:|---|
| A | 50 | 1 | Baseline, overhead commit |
| B | 200 | 1 | Lợi ích giảm số lần batch call |
| C | 500 | 1 | Transaction p95 và tốc độ ghi |
| D | 1000 | 1 | Memory/WAL/lock và rollback cost |
| E | 500 | 4 | Scale ngang khi DB còn capacity |
| F | 500 | 8 | Điểm nghẽn pool/lock/IO khi tăng worker |

**Đây là ma trận thử nghiệm, không phải kết quả đo thực.** Giữ nguyên snapshot, SQL, schema/index, transaction isolation, driver/version và cấu hình database giữa các lần thử. Không cùng lúc đổi chunk size, pool size và số pod rồi suy luận một thay đổi là nguyên nhân cải thiện.

### 9.4. Sizing nhiều worker với connection pool

Giả sử `N=8` worker pod, mỗi pod có business Hikari pool tối đa `P=12`:

\[
C_{\mathrm{workerPools}}\le N\times P=8\times12=96
\]

Đây là trần **connection có thể mở từ các pool worker**, không phải số connection active. Phải cộng cả pool manager, metadata `JobRepository`, web/API và số pod có thể tồn tại khi HPA/rolling update. Nếu metadata DB và business DB nằm trên hai instance khác nhau, tính ngân sách từng instance; nếu cùng instance, tất cả cùng chiếm `max_connections`.

**Một worker không nhất thiết chỉ dùng một connection.** `JdbcCursorItemReader` có thể giữ connection lâu, trong khi transaction writer mượn connection khác; nested `REQUIRES_NEW` còn có thể cần thêm slot. Khi pool pending tăng mà DB CPU thấp, xem transaction/connection hold time trước khi tăng pool.

## 10. Transaction dài, khóa ghi và hot keys

Một câu SQL batched có thể ghi nhanh hơn nhưng nhiều writer vẫn tranh nhau cùng dữ liệu đích:

~~~mermaid
flowchart TB
    P[Partitioner chia input theo thời gian] --> W1[Worker A]
    P --> W2[Worker B]
    P --> W3[Worker C]
    W1 --> U1["UPSERT tổng hợp account 42"]
    W2 --> U2["UPSERT tổng hợp account 42"]
    W3 --> U3["UPSERT tổng hợp account 42"]
    U1 --> H[(Một hot row trong DB)]
    U2 --> H
    U3 --> H
~~~

**Partition theo input không đồng nghĩa partition theo write keys.** Mỗi partition có thể đọc một range ID độc lập nhưng cùng cập nhật row tổng hợp khách hàng. PostgreSQL phải phối hợp khóa, làm các transaction chờ nhau; khi đó tăng batch size/concurrency có thể kéo dài lock wait và giảm throughput.

### Giảm write contention

- **Partition theo khóa ghi** (tenant, customer, account hoặc bucket) nếu đảm bảo một key chỉ được một worker sở hữu trong job.
- **Append-only staging/ledger** với unique business key trước, aggregate sau bằng một owner hoặc theo các bucket xác định.
- **Atomic SQL update** thay vì Java đọc trạng thái cũ rồi ghi đè (tránh lost update).
- **Thứ tự khóa ổn định** khi mỗi transaction cập nhật nhiều key để giảm deadlock.
- **Transaction ngắn**; tránh gọi HTTP, tải file, chờ async job trong lúc đang giữ row locks.
- **Giới hạn concurrency** thay vì tăng worker vô hạn; giảm số connection đợi lock.

Với PostgreSQL, lỗi deadlock thường có SQLSTATE `40P01`, còn serialization failure có thể là `40001`. Cả hai thường cần **rollback và retry toàn đơn vị transaction** với giới hạn; không thể chữa bằng cách gọi lại cùng JDBC statement trong một PostgreSQL transaction đã ở trạng thái aborted.

### Một UPSERT update “không đổi” vẫn có chi phí

~~~sql
-- Hạn chế update row khi dữ liệu mới giống hệt:
ON CONFLICT (source_snapshot, source_order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount_cents = EXCLUDED.amount_cents
WHERE (processed_orders.customer_id, processed_orders.amount_cents)
      IS DISTINCT FROM
      (EXCLUDED.customer_id, EXCLUDED.amount_cents);
~~~

Đây là **phần nối tiếp của câu INSERT ... ON CONFLICT**, không phải SQL độc lập. Điều kiện `IS DISTINCT FROM` giảm những update không cần thiết. Tuy nhiên, việc đi vào conflict path vẫn có thể cần lock/check uniqueness; nó **không đảm bảo** toàn bộ contention biến mất.

## 11. JDBC batch failure và vấn đề “item nào lỗi?”

Với một batch 500 parameter sets, chỉ một record vi phạm constraint cũng có thể làm batch call thất bại. JDBC có `BatchUpdateException` và `getUpdateCounts()`, nhưng **không nên giả định** một mảng counts luôn mô tả chính xác từng item đã commit:

- Driver có thể dừng ngay tại statement lỗi hoặc tiếp tục tùy cơ chế.
- Mỗi count có thể là số row, `Statement.SUCCESS_NO_INFO (-2)` hoặc `Statement.EXECUTE_FAILED (-3)`.
- Câu lệnh có thể chạy trong một transaction rồi **rollback toàn bộ** khi writer ném exception.
- Một số database/driver không xác định rõ transaction đã commit hay chưa khi kết nối mất đúng thời điểm commit.
- Với skip/retry ở mức item, framework có thể cần phân tách/replay để xác định item gây lỗi; **chi phí rất lớn** nếu batch chứa hàng nghìn item.

### 11.1. Phân loại lỗi trước khi retry

| Lỗi hoặc tín hiệu | Nguyên nhân thường gặp | Phản ứng gợi ý |
|---|---|---|
| `23505` PostgreSQL unique violation | Trùng business key hoặc dữ liệu bất hợp lệ | Nếu duplicate hợp lệ: thiết kế idempotent SQL; nếu payload sai: fail/quarantine |
| `23502` NOT NULL violation | Dữ liệu thiếu trường bắt buộc | Validate trước writer; không retry vô hạn |
| `23503` foreign-key violation | Thiếu row tham chiếu hoặc thứ tự load sai | Chỉnh dependency/validation; chỉ retry nếu parent sẽ tới sau theo contract |
| `40P01` deadlock detected | Hai transaction khóa trái thứ tự | Rollback và retry có giới hạn, backoff; sửa lock ordering |
| `40001` serialization failure | Isolation yêu cầu chạy lại transaction | Retry transaction từ đầu, giữ idempotency |
| `55P03` lock not available | NOWAIT hoặc lock timeout | Điều tra blockers, retry theo SLA |
| `57014` query canceled | Statement timeout hoặc cancellation | Xác định timeout/hủy chủ động, tránh retry mù |
| `08xxx` connection exception | Kết nối DB lỗi | Đối soát khả năng commit trước khi phát lại |
| Hikari acquisition timeout | Không mượn được connection | Đo pool pending, SQL/transaction hold, giảm concurrency |

SQLSTATE là mã của **PostgreSQL**; Spring exception translation có thể bọc trong các loại `DataAccessException` khác nhau. Khi cấu hình `.retry(...)` hoặc `.skip(...)` cho Spring Batch, hãy kiểm tra exception **thực tế của driver + Spring JDBC + transaction manager**. Không coi mọi `DataAccessException` là transient.

### 11.2. Validate trước writer thay vì “thử rồi skip”

Nếu `amount_cents` phải không âm và `customer_id` phải hợp lệ, validate bằng processor/reader hoặc staging constraint sớm. Với lỗi dữ liệu vĩnh viễn, cần chính sách quarantine có audit và số bản ghi bị loại; không để batch cứ retry một payload sai.

Nếu lỗi writer xảy ra ở item thứ 417 nhưng batch driver chỉ báo lỗi chung, việc debug có thể khó hơn khi ghi từng item. Cân nhắc một fallback chẩn đoán **chỉ trong luồng lỗi** để cô lập item xấu trên một transaction riêng/nguồn test; đừng luôn ghi per-row trong production vì sẽ đánh mất lợi ích batching. Tập dữ liệu lỗi phải được bảo vệ thông tin nhạy cảm.

### 11.3. Skip và retry phải bảo toàn tính đúng

- **Skip** một item là quyết định nghiệp vụ: nếu bỏ qua dữ liệu bắt buộc đối soát, `COMPLETED` có thể vẫn sai.
- **Retry** deadlock cần rollback đúng transaction, tránh transaction đã bị PostgreSQL đánh dấu aborted.
- Với chunk đã có side effect bên ngoài DB, cần outbox/idempotency trước khi retry.
- Không chuyển một lỗi unique-key do **hai worker xử lý trùng cùng input** thành `skip` mà bỏ qua vấn đề partition plan.
- Trong hệ thống tài chính, một item sai thường nên **fail và điều tra** thay vì cho phép skip đến một ngưỡng lớn.

## 12. Retry, restart và idempotency xuyên nhiều resource

Sơ đồ lỗi quan trọng:

~~~mermaid
sequenceDiagram
    participant W as Worker Step
    participant B as Business DB
    participant J as JobRepository
    participant Q as Broker hoặc manager
    W->>B: Batch INSERT một chunk
    B-->>W: Commit thành công
    Note over W,J: Mất điện/kết nối trước khi toàn bộ metadata được thấy
    W--xJ: Checkpoint chưa phản ánh đầy đủ
    Q->>W: Restart / redelivery
    W->>B: Item được thử lại
    B-->>W: Unique key/idempotent conflict
~~~

Trong hệ thống đơn giản mà business writer và metadata cùng transaction database, khả năng nguyên tử có thể tốt hơn; nhưng **đừng mặc định** mọi cấu hình Spring Batch có một giao dịch bao trùm business DB, metadata DB và broker. Thực tế nhiều hệ thống có hai datasources và transport khác nhau.

### Bốn bất biến restart

1. **Input bất biến:** snapshot/cutoff, identifying `JobParameters` và dữ liệu trong partition không dịch chuyển giữa các lần chạy.
2. **Partition plan ổn định:** cùng tên partition và ranh giới, không tạo lại với `gridSize`/bucket count khác sau khi một số partition đã commit.
3. **Checkpoint ổn định:** `ItemStream` name/key và thứ tự reader không thay đổi tùy ý; không thay cursor sang paging mà bỏ qua migration state.
4. **Side effect idempotent:** unique key/upsert/ledger/outbox đảm bảo cùng item thử lại không sinh thêm kết quả ngoài ý muốn.

Nếu dùng `JobRepository` để restart, hãy giữ **cùng identifying `JobParameters`** của `JobInstance` bị lỗi. Thêm `run.id` mới có thể tạo job instance mới, không phải tiếp tục instance cũ.

### Idempotent không có nghĩa “bỏ qua mọi duplicate”

Trong bài toán đơn hàng, cùng `snapshotKey` + `id` đến lại với payload **giống nhau** có thể là retry hợp lệ. Nhưng cùng khóa với `amountCents` khác có thể là **nguồn dữ liệu bị sửa trái contract**. Phải chọn một trong các cách rõ ràng:

- Immutable snapshot và checksum: duplicate phải cùng payload/checksum.
- Versioned upsert: chỉ nhận source version mới hơn, có quy tắc giải quyết equal-version conflict.
- Reject/quarantine: báo lỗi nếu business key trùng nhưng payload khác.
- Event ledger: một event ID chỉ gây một hiệu ứng, sửa sai dùng event bù trừ mới thay vì ghi đè lịch sử.

Một statement `ON CONFLICT DO NOTHING` **chỉ giải quyết việc không thêm row trùng**, không chứng minh dữ liệu nguồn đúng. Kiểm thử cần cố tình gửi duplicate **cùng key nhưng khác amount** để xác nhận hệ thống phát hiện hoặc xử lý theo chính sách.

## 13. Multi-threaded step, partitioning và remote workers

Spring Batch có nhiều cơ chế mở rộng; batch INSERT/UPDATE tương tác khác nhau với từng mô hình:

| Mô hình | Cách writer được gọi | Điểm cần bảo vệ |
|---|---|---|
| Step tuần tự | Các chunk chạy lần lượt | Chunk size, SQL index và transaction duration |
| Multi-threaded step | Nhiều chunk cùng một `StepExecution` | Reader/processor/writer thread safety, checkpoint và pool |
| Parallel steps | Nhiều `StepExecution` chạy song song | Cross-step write keys, contention và pool budget |
| Local partitioning | Nhiều worker `StepExecution` trong cùng JVM | Một reader stateful theo partition; writer idempotent |
| Remote partitioning | Mỗi pod xử lý partition executions | Tổng `replicas × pool max`, message redelivery, version compatibility |
| Remote chunking | Manager đọc, worker xử lý/ghi chunk | Manager reader bottleneck, payload size, worker idempotency |
| Remote step (Spring Batch 6.x) | Step logic chạy tại một process khác | Placement không tự làm một step thành nhiều partition |

**Đừng dùng `@StepScope` để giải quyết mọi lỗi concurrency.** Nó tạo bean theo **`StepExecution`**, không theo thread; trong multi-threaded step, nhiều thread có thể chia sẻ cùng một reader target. Với partitioning, mỗi execution có `ExecutionContext` và reader instance riêng, nhưng writer SQL vẫn có thể va chạm các hot rows ở database.

### Partition theo write keys

Giả sử 16 partition cùng INSERT vào `processed_orders` với unique key `(snapshotKey,id)`. Nếu các ID partition hoàn toàn không overlap và input cố định, xung đột thường thấp. Nhưng nếu mỗi partition còn update `daily_customer_totals`, một khách hàng xuất hiện ở nhiều range ID có thể tạo hot row.

Khi đó có thể dùng:

~~~text
Giai đoạn A:
  N worker -> batch INSERT kết quả immutable với unique event/order key

Giai đoạn B:
  chia theo customer_id/bucket -> GROUP BY/aggregate
  một owner cho mỗi customer key tại thời điểm merge
~~~

Đánh đổi là thêm một bước và có thể có độ trễ tổng hợp; lợi ích là **tách concurrent ingestion khỏi việc cập nhật aggregate row có khóa nóng**. Benchmark phải đo cả hai giai đoạn, không chỉ thời gian của bước ingest.

## 14. Observability: không chỉ nhìn writeCount

Một hệ thống cần số đo từ **worker → Spring Batch → JDBC driver → database → business output**.

| Tầng | Metric/tín hiệu | Câu hỏi |
|---|---|---|
| Spring Batch | `readCount`, `filterCount`, `writeCount`, skip/retry, commit/rollback | Có item nào bị filter/skip/rollback? |
| Writer/JDBC | Số parameter sets/call, batch duration, update count failures | Một lần gọi chứa bao nhiêu item, có lỗi row count? |
| HikariCP | active, idle, pending, acquire/usage p95 | Worker đợi connection hay giữ connection lâu? |
| PostgreSQL | SQL latency, wait events, lock/IO, WAL, buffer hit, active sessions | DB nghẽn ở đâu khi tăng batch/concurrency? |
| JVM/pod | CPU, GC, heap, allocation, throttling | Lô lớn có gây áp lực bộ nhớ/CPU? |
| Business | Unique target keys, checksum, amount totals, duplicate conflicts | Kết quả thực tế có chính xác? |

### Query chẩn đoán PostgreSQL

Một truy vấn read-only thống kê session/wait event:

~~~sql
SELECT state, wait_event_type, wait_event, count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Nếu `wait_event_type='Lock'` tăng khi worker tăng, nên xem hot keys/transaction duration, không tăng pool vô hạn. Nếu `IO`/WAL trở thành giới hạn, thay batch size hoặc SQL plan có thể hữu ích hơn tăng replicas.

Để kiểm tra row đích sau khi load một snapshot:

~~~sql
SELECT
    count(*) AS actual_rows,
    count(DISTINCT source_order_id) AS distinct_order_ids,
    sum(amount_cents) AS total_amount_cents
FROM processed_orders
WHERE source_snapshot = :snapshotKey;
~~~

Đây chỉ là **một bước đối soát**. Cần so sánh với count/tổng trên **immutable input snapshot**, và khi có thể so sánh **tập khóa ID**, checksum hoặc audit theo partition. Tổng count và sum vẫn có thể tình cờ khớp trong một dataset trùng và thiếu dữ liệu khác.

### Metric cardinality và điều tra execution

`jobExecutionId`, `stepExecutionId`, `partitionName` rất quan trọng trong log/trace, nhưng không nên dùng mỗi execution ID làm nhãn time series có retention dài trên mọi metric. Tập trung metrics theo `jobName`, `stepName`, `poolName` và dùng structured logs/traces để truy đúng execution khi có sự cố.

## 15. Runbook: batch insert/update bị chậm hoặc thất bại

### Bước 1 — Xác định phạm vi lỗi

Ghi job name, `jobExecutionId`, `stepExecutionId`, SQL template, datasource, số worker/partition, chunk size và driver version. Phân biệt lỗi xảy ra tại **reader**, **processor**, **writer batch**, **transaction commit** hay **metadata repository**.

### Bước 2 — Kiểm tra tính đúng trước khi retry

Từ unique business key, xác định item/partition nào đã ghi thành công, output có bị trùng hoặc thiếu không. Khi connection mất trong commit, **không coi exception là bằng chứng chắc chắn transaction chưa commit**.

### Bước 3 — Phân loại nguyên nhân kỹ thuật

- Unique conflict `23505`: duplicate retry hợp lệ hay dữ liệu sai?
- NOT NULL/FK violation: validation hoặc thứ tự nạp dữ liệu có sai?
- `40P01`/`40001`: lock ordering, isolation hoặc hot rows?
- Pool acquisition timeout: pending cao do nhiều cursor/transaction hay DB bị chậm?
- Statement timeout: query/IO/lock đang kéo dài, batch quá lớn?
- Metadata lỗi: business DB đã commit nhưng checkpoint có theo kịp không?

### Bước 4 — Kiểm soát tải

Khi DB quá tải, **giảm concurrency**, tạm dừng producer hoặc áp backpressure. Đừng tăng số worker cùng retry ngay; các transaction có thể tiếp tục xếp hàng trên cùng hot key và làm pool cạn.

### Bước 5 — Sửa theo bottleneck

- Batch size quá nhỏ: tăng thử 50 → 200 → 500 và đo giảm round-trip.
- Batch quá lớn: giảm chunk/batch để rút ngắn transaction và rollback cost.
- Không dùng prepared statements: chuyển sang JDBC batching/`JdbcBatchItemWriter` phù hợp.
- Upsert hot row: phân write ownership, append-only staging rồi aggregate.
- DB I/O/WAL bão hòa: tối ưu SQL/index, batching, scheduling và tài nguyên DB.
- Pool pending: đo cursor/transaction hold time trước khi tăng pool.
- Poison record: validate, quarantine hoặc fail theo contract, không retry vô hạn.

### Bước 6 — Restart đúng metadata

Dùng Spring Batch lifecycle/`JobOperator` theo phiên bản, không sửa `BATCH_STEP_EXECUTION.STATUS` bằng SQL để “ép” job hoàn tất. Giữ identifying parameters, snapshot và partition plan ổn định; xác minh worker cũ đã dừng trước khi dispatch lại cùng execution.

### Bước 7 — Đối soát kết quả

So sánh **tập khóa ID**, tổng tiền hoặc checksum theo business contract, số unique conflicts và trạng thái downstream. Một job `COMPLETED` nhưng có những item bị `DO NOTHING` vì cùng ID khác payload cần được kiểm tra riêng.

### Bước 8 — Ghi benchmark và giới hạn production

Lưu chunk size, driver version, pool max, số worker, DB stats và throughput thực trước/sau thay đổi. Bổ sung cảnh báo retry/lock/pool pending và quy tắc không autoscale vượt ngân sách connection của cụm.

## 16. Ma trận kiểm thử trước production

| Test | Input/sự cố | Điều kiện đạt |
|---|---|---|
| Happy path INSERT | 500 item hợp lệ, key duy nhất | Ghi đúng 500 row, checksum/tập key khớp |
| Chunk cuối ngắn | 1.203 item, `chunk(500)` | Xử lý 500+500+203, không bỏ sót |
| Duplicate replay hợp lệ | Một `snapshotKey`+ID lặp cùng payload | Không có row trùng, status/restart hợp lệ |
| Duplicate khác payload | Cùng key nhưng amount khác | Phát hiện/quarantine hoặc xử lý theo version contract, không bỏ im lặng |
| Optimistic update success | Version đúng | Update một row và tăng version |
| Optimistic update conflict | Version đã bị worker khác tăng | 0-row update được phân loại đúng, không coi là thành công |
| Multi-row UPSERT duplicate | Hai source rows cùng conflict key trong một statement | Dữ liệu được dedupe trước hoặc lỗi được xử lý rõ |
| Một item sai constraint | Batch có một row NOT NULL/FK sai | Transaction/skip/fail policy đúng, không mất item hợp lệ |
| JDBC batch failure | Driver báo `BatchUpdateException` | Không giả định counts là committed rows; đối soát và rollback |
| Worker crash giữa chunk | Kill worker trước commit | Chunk rollback hoặc recovery đúng, writer idempotent |
| Crash sau business commit | Mất kết nối trước checkpoint/ACK | Restart không tạo side effect trùng |
| Lock contention | Nhiều worker update một hot key | Đo lock wait, bounded retry và concurrency |
| Pool exhaustion | Active executions vượt pool budget | Có backpressure/timeout theo policy, không sai dữ liệu |
| PgJDBC rewrite option | So sánh cùng input có/tắt rewrite | Đo SQL behavior và throughput; không khẳng định rewrite luôn xảy ra |
| Set-based SQL | `INSERT ... SELECT` theo các range | Range không overlap, đúng row counts và restart |
| Benchmark | Chunk 50/200/500/1000, worker 1/4/8 | So sánh throughput, p95, WAL/lock và output correctness |

### Một test đối soát bằng tập khóa

Với input ID từ 1 đến 1.000, có thể lấy hai tập:

~~~text
expected = các (snapshotKey, id) hợp lệ trong immutable snapshot
actual   = các (source_snapshot, source_order_id) trong output

assert expected == actual
assert mỗi khóa trong output xuất hiện đúng một lần
assert amount/related fields phù hợp với business rule
~~~

Đây là **pseudocode**. Nếu hệ thống cố tình filter item, tập expected phải tính sau những quy tắc lọc đã được công nhận; nếu có late events hoặc nhiều snapshot versions, chúng phải là input riêng có dấu vết.

## 17. Checklist vận hành và thiết kế

- [ ] Phân biệt `chunk size`, số tham số trong JDBC batch và số statement DB thực thi.
- [ ] Có unique business key/idempotency key phù hợp với retry/restart.
- [ ] Không coi `writeCount` là số row mới inserted khi dùng `ON CONFLICT DO NOTHING`.
- [ ] Đã chọn rõ INSERT, UPDATE, UPSERT hay set-based SQL theo ngữ nghĩa nghiệp vụ.
- [ ] `JdbcBatchItemWriter` dùng prepared/named parameters, không nối chuỗi input vào SQL.
- [ ] `assertUpdates` phù hợp: false cho 0-row outcome hợp lệ, true khi update bắt buộc tác động row.
- [ ] Optimistic locking phân biệt replay và conflict thực, không che 0-row update.
- [ ] Đã kiểm tra duplicate key với payload khác, không bỏ qua dữ liệu sai.
- [ ] Input snapshot/cutoff, partition plan và ItemStream checkpoint ổn định qua restart.
- [ ] Reader stateful có scope/lifecycle đúng; multi-threaded step không chia cursor không an toàn.
- [ ] Chunk/batch size đã benchmark với dữ liệu thật, không chọn chỉ vì một con số phổ biến.
- [ ] Đã đo Hikari active/pending/acquire, SQL latency, WAL/IO và lock wait.
- [ ] Số worker/concurrency nằm trong ngân sách connection của business và metadata DB.
- [ ] pgjdbc rewrite/COPY/multi-row SQL chỉ bật khi kiểm thử đúng driver và SQL shape.
- [ ] Retry lỗi transient có giới hạn và backoff, lỗi dữ liệu vĩnh viễn không retry vô hạn.
- [ ] Các side effect ngoài DB có outbox/dedupe hoặc bảo vệ idempotency phù hợp.
- [ ] Đã thử crash trước/sau commit, duplicate redelivery, version conflict và đối soát output.

## 18. Bài tập thực hành

### Bài tập 1 — Chunk khác JDBC batch

Với 1.203 item, `chunk(500)`, processor loại 13 item trong chunk đầu và 6 item trong chunk cuối, hãy tính số item writer nhận ở mỗi lượt và giải thích vì sao `writeCount` không nhất thiết bằng số row mới khi SQL có `DO NOTHING`.

### Bài tập 2 — Tạo JdbcBatchItemWriter INSERT

Viết writer nhận `OrderRow` và insert vào `processed_orders`. Thử `assertUpdates(true)` rồi phát lại một duplicate hợp lệ với `ON CONFLICT DO NOTHING`; ghi nhận hành vi, giải thích lúc nào dùng `assertUpdates(false)` và cách kiểm tra duplicate khác payload.

### Bài tập 3 — UPDATE theo version

Thêm cột `version` và viết writer update với `WHERE version = :expectedVersion`. Chạy hai worker cùng đọc version 4. Xác minh chỉ một update thành công; worker còn lại phải phân loại 0-row update và quyết định retry/reconcile theo business rule, không ghi đè dữ liệu.

### Bài tập 4 — Benchmark pgjdbc

Trên cùng snapshot và driver, so sánh JDBC batch INSERT khi tắt/bật `reWriteBatchedInserts` với các SQL shape khác nhau (plain insert, insert with conflict handling). Quan sát driver/server logs/query metrics xem rewrite có thực sự xảy ra và có thay đổi throughput hay không.

### Bài tập 5 — JDBC batch so với INSERT SELECT

Với một phép biến đổi chỉ đổi tên cột và tính thêm một số đơn giản, so sánh Spring Batch `JdbcBatchItemWriter` với `INSERT ... SELECT` theo range. Đo wall-clock, DB CPU/IO/WAL, transaction duration, output keys và khả năng restart mỗi range.

### Bài tập 6 — Tìm batch size hợp lý

Chạy các mức `chunk(50)`, `chunk(200)`, `chunk(500)` và `chunk(1000)` với worker 1, 4, 8 trên cùng snapshot. Thu throughput, p95 query/commit time, lock wait, Hikari pending, rollbacks và memory. Giải thích khi nào tăng chunk hoặc worker bắt đầu làm hệ thống chậm đi.

### Bài tập 7 — Fault injection sau commit

Cho worker commit một batch thành công rồi mất kết nối trước khi manager nhìn thấy checkpoint. Restart cùng `JobInstance` và xác minh unique business keys/output đúng. Thử lại với writer không idempotent để chỉ ra lỗi data duplication, sau đó bổ sung guard phù hợp.

### Bài tập 8 — Runbook dữ liệu sai

Một job báo `COMPLETED` và `writeCount=1.000.000` nhưng output chỉ có 998.700 row vì nhiều `ON CONFLICT DO NOTHING`. Thiết kế cách phân biệt duplicate hợp lệ, source reuse ID, processing overlap và thiếu bản ghi; nêu số liệu/audit cần có trước khi cho job downstream sử dụng output.

**Câu hỏi tự kiểm tra:** Vì sao `chunk(500)` không đồng nghĩa 500 connection? `JdbcBatchItemWriter` có bắt buộc driver gửi một SQL duy nhất không? Khi nào `assertUpdates(false)` hợp lý và khi nào nguy hiểm? Tại sao UPSERT cộng thêm delta có thể không idempotent? Vì sao `writeCount` khác số row inserted? Khi nào `INSERT ... SELECT` thích hợp hơn ItemWriter Java? Tại sao một batch quá lớn có thể làm rollback/lock/pool pressure tệ hơn? Làm thế nào chứng minh dữ liệu chính xác sau crash giữa commit và checkpoint?

## 19. Tổng kết

**Batch insert và batch update** giúp Spring Batch giảm overhead khi ghi dữ liệu lớn, nhưng kỹ thuật này phải được hiểu ở **ba tầng riêng**: Spring Batch chunk điều phối transaction/checkpoint, JDBC batch gom parameter sets và SQL set-based tận dụng xử lý tập của database. `JdbcBatchItemWriter` kết nối thuận tiện với chunk-oriented steps; PostgreSQL UPSERT, pgjdbc rewrite và `INSERT ... SELECT` là những lựa chọn cần đo theo SQL shape, driver và workload thực.

Hiệu năng không được đánh đổi bằng dữ liệu sai. Cần thiết kế **unique business key, lựa chọn `assertUpdates` đúng nghĩa, optimistic update có kiểm tra conflict, reader/checkpoint ổn định, retry/rollback đúng transaction, side effect idempotent và đối soát tập khóa nghiệp vụ**. Chỉ tăng batch size hoặc số worker khi throughput, lock/I/O, connection pool và khả năng restart đã được kiểm chứng bằng phép đo trên dữ liệu đại diện.
