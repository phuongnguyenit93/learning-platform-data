# Phối hợp transaction với JobRepository trong Spring Batch

Một job nhập dữ liệu thanh toán xử lý 12 triệu bản ghi qua 32 partition. Mỗi worker ghi 500 giao dịch rồi commit. Một worker bị mất kết nối ngay khi ghi chunk thứ 80; khi khởi động lại, vài trăm kết quả xuất hiện trùng, dù SQL writer “đã chạy trong transaction”. Điều tra cho thấy **dữ liệu nghiệp vụ** nằm ở một PostgreSQL database, còn các bảng `BATCH_*` của **JobRepository** nằm ở database khác. Hai hệ thống dùng hai transaction manager độc lập, vì vậy checkpoint có thể không đồng bộ với business commit.

Bài **“Phối hợp transaction với JobRepository”**, thuộc chương **Transaction boundary** của module **SPRING_BATCH_SCALING_OPERATIONS**, giải quyết câu hỏi: **một chunk được xem là đã xử lý khi nào, metadata nào ghi nhận tiến độ, và điều gì xảy ra nếu commit dữ liệu cùng commit checkpoint không thực sự nguyên tử?**

Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và chọn kiến trúc theo tài nguyên thực tế. Nội dung dưới đây dùng Spring Batch **5.2.x**, Spring Framework **6.x** và Java **17+** làm hệ quy chiếu. Code là các mảnh cấu hình/logic có chú giải, không phải ứng dụng hoàn chỉnh với tất cả bean và schema khởi tạo.

**Nguyên tắc xuyên suốt:** `JobRepository` là nguồn metadata phục vụ điều phối và restart; **business database là nguồn hiệu ứng nghiệp vụ**. Chúng chỉ có thể commit cùng một local transaction khi được cấu hình thực sự chia sẻ tài nguyên và transaction, hoặc cần một cơ chế phối hợp khác. Nếu commit độc lập, phải thiết kế **idempotency, durable state, snapshot ổn định và reconciliation** cho các khoảng lỗi không thể loại bỏ bằng annotation.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `JobRepository`, `JobExplorer`, `JobLauncher`, `JobOperator` với transaction của worker `Step`.
2. Xác định quan hệ giữa `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` và tiến độ chunk.
3. Giải thích thời điểm `TaskletStep` cập nhật metadata và vì sao cập nhật “trước commit” **không tự bảo đảm atomicity** giữa hai datasource.
4. Cấu hình `JobRepository` và chunk step dùng **cùng `DataSource`/`PlatformTransactionManager`** khi cần local atomicity.
5. Cấu hình metadata datasource và business datasource khác nhau mà không nhầm `transactionManagerRef` của repository với `chunk(..., transactionManager)`.
6. Phân tích các cửa sổ lỗi: business commit trước checkpoint, checkpoint tiến trước business commit, lỗi commit không xác định, worker crash.
7. Thiết kế reader checkpoint đúng, writer idempotent và partition manifest bất biến để restart không bỏ sót hoặc tạo hiệu ứng nghiệp vụ lặp.
8. Hiểu vai trò của isolation level cho `JobRepository.create*`, optimistic locking, transaction propagation và multi-process job launching.
9. Lựa chọn giữa dùng chung local transaction, JTA/XA và outbox/inbox khi nhiều resource cần phối hợp.
10. Viết kế hoạch fault-injection, SQL đối soát và runbook xử lý `STARTED`, `FAILED`, `UNKNOWN`, remote worker mất kết nối.

## 2. JobRepository quản lý gì và không quản lý gì?

`JobRepository` là thành phần persistence metadata trung tâm của Spring Batch. Nó lưu thông tin về định danh job, lần thực thi, step và state phục vụ restart.

| Đối tượng | Ý nghĩa | Vai trò khi restart |
| --- | --- | --- |
| `JobInstance` | Một lần chạy logic, định danh bởi job name + identifying `JobParameters` | Xác định lịch sử công việc cần phục hồi |
| `JobExecution` | Một **lần thực thi** cụ thể của JobInstance | Ghi lần start/restart, status và timestamps |
| `StepExecution` | Một lần thực thi step (bao gồm worker step của partition) | Counters, status, commit/rollback và lỗi |
| `ExecutionContext` | Bản đồ trạng thái serializable của Job/Step | Reader offset, partition context và checkpoint |
| `BatchStatus` | Trạng thái kỹ thuật như `STARTED`, `COMPLETED`, `FAILED` | Quyết định có thể restart và phải xử lý phần nào |
| `ExitStatus` | Mã kết quả cho điều kiện flow | Không thay thế `BatchStatus` hoặc dữ liệu đã commit |

Schema JDBC mặc định thường có các bảng:

~~~text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION
BATCH_STEP_EXECUTION_CONTEXT
BATCH_JOB_SEQ / BATCH_JOB_EXECUTION_SEQ / BATCH_STEP_EXECUTION_SEQ
  (hoặc cơ chế cấp ID khác theo DB)
~~~

Tên bảng, sequence và cấu trúc chi tiết có thể khác theo vendor, table prefix và phiên bản. Không tự viết/đổi schema từ danh sách này; dùng schema tương thích với **đúng phiên bản Spring Batch** và kiểm tra migration.

**JobRepository không phải business database transaction coordinator.** Nó biết Step nào `COMPLETED`, nhưng không tự biết một HTTP charge đã thành công, một file đã được publish hay một JDBC write ở datasource khác đã commit.

### 2.1. JobExplorer, JobLauncher và JobOperator

- `JobLauncher` nhận Job, parameters rồi khởi động một `JobExecution`.
- `JobExplorer` cung cấp khả năng **đọc** metadata lịch sử.
- `JobOperator` cung cấp thao tác vận hành như start/stop/restart theo API/phiên bản.
- `JobRepository` thực hiện CRUD metadata bền vững để các thành phần trên hoạt động.

Một dashboard chỉ đọc `JobExplorer` có thể kết luận “framework hoàn tất”. Để công bố báo cáo tài chính, vẫn phải đối soát business output với tập nguồn được phê duyệt.

### 2.2. Phân biệt metadata và dữ liệu nghiệp vụ

~~~mermaid
flowchart TB
    JL["JobLauncher / JobOperator"] --> JR["JobRepository"]
    JR --> META[("Metadata BATCH_*")]
    JL --> J["JobExecution"]
    J --> S["Worker StepExecution"]
    S --> CT["Chunk transaction"]
    CT --> DATA[("Business tables")]
    S --> EC["ExecutionContext checkpoint"]
    EC --> JR
    S --> EXT["Message / HTTP / File"]
    EXT -.-> N["Không tự thuộc JDBC TX"]
~~~

Một hệ thống có thể dùng cùng database cho `META` và `DATA`, hoặc hai databases khác nhau. **Sơ đồ logic giống nhau không có nghĩa chúng dùng cùng transaction vật lý.**

## 3. Bốn ranh giới transaction thường bị nhầm

Trước khi xem code, hãy phân biệt:

1. **Repository CRUD transaction:** transaction do proxy/advice của `JobRepository` dùng để create/update metadata.
2. **Chunk transaction:** transaction do `StepBuilder.chunk(commitInterval, transactionManager)` sử dụng cho một lượt read/process/write/checkpoint.
3. **Job/step lifecycle updates:** tạo JobExecution/StepExecution, đánh dấu `STARTED`/`COMPLETED`/`FAILED`; không nên suy rằng tất cả lifecycle update nằm cùng một transaction kéo dài toàn Job.
4. **External resource transaction:** Kafka/JMS/Rabbit local transaction, HTTP call, file/object write hoặc JDBC datasource khác.

| Ranh giới | Tài nguyên | Có bảo đảm bao cả JobInstance? |
| --- | --- | --- |
| `chunk(250, businessTxManager)` | Business datasource nếu writer tham gia đúng | Không; commit theo chunk |
| `JobRepository` transactional methods | Metadata datasource của repository | Không; các method dùng transaction theo advice |
| `@Transactional("auditTxManager")` | Audit datasource của manager này | Không tự gộp business và audit |
| Broker send/ACK | Broker channel/producer/session | Không atomic với business DB theo mặc định |
| HTTP charge | Remote service transaction của chính nó | Không rollback theo JDBC local transaction |

**Điểm nguy hiểm:** cùng gọi “transaction” nhưng resource và thời điểm commit khác nhau. Một `StepExecution` có thể `FAILED` dù nhiều chunk business đã commit; một message có thể đã tới broker dù chunk rollback.

## 4. Một chunk đi qua JobRepository như thế nào?

Với `TaskletStep` thông thường, framework chạy một vòng chunk trong transaction do **step transaction manager** quản lý. `ItemStream` có thể lưu state vào `StepExecution.ExecutionContext`; framework cập nhật metadata gần thời điểm commit.

~~~mermaid
sequenceDiagram
    participant S as Worker TaskletStep
    participant T as Step TX Manager
    participant R as Reader / Writer
    participant B as Business DB
    participant M as JobRepository
    S->>T: BEGIN chunk TX
    S->>R: read / process / write chunk
    R->>B: JDBC INSERT/UPDATE
    S->>R: ItemStream.update(ExecutionContext)
    S->>M: updateExecutionContext / update StepExecution
    S->>T: COMMIT
    Note over B,M: Chỉ atomic khi cùng transactional resource/coordination
~~~

Tài liệu Spring Batch 5.2 ghi rõ `JobRepository` lưu `StepExecution` và `ExecutionContext` định kỳ, **ngay trước commit**. Điều này không có nghĩa transaction manager của repository và business Step tự động là cùng một transaction. Nếu cùng local transaction, cập nhật metadata thường tham gia cùng commit; nếu hai managers khác nhau, có khoảng lỗi.

### 4.1. Ví dụ 1.050 item và chunk size 100

Giả sử input là immutable snapshot, reader có thứ tự ID ổn định:

| Chu kỳ | Item logic | Business effect | Metadata/checkpoint |
| --- | --- | --- | --- |
| Chunk 1 | 1–100 | Commit | Đánh dấu tiến qua chunk 1 |
| Chunk 2 | 101–200 | Commit | Đánh dấu tiến qua chunk 2 |
| Chunk 3 | 201–300 | Rollback vì deadlock | Không được giả định checkpoint đã tiến nếu metadata cùng TX |
| Retry chunk 3 | Công việc chưa hoàn tất | Có thể commit sau retry | Tiến tiếp theo cơ chế ItemStream |
| Chunk 4–11 | 301–1.050 | Commit nếu thành công | Hoàn tất Step |

Trong cấu hình **cùng local transaction**, rollback của chunk 3 bao gồm business updates và các metadata changes **tham gia đúng transaction đó**. Trong cấu hình **hai local transactions**, phải kiểm thử cả hai thứ tự lệch nhau; metadata có thể không khớp business output sau crash.

**Không rollback toàn bộ Step đã chạy** khi một chunk lỗi; các chunk trước đã commit vẫn tồn tại.

### 4.2. ItemStream và checkpoint không phải chỉ là readCount

`ItemStream.open(...)` khôi phục state; `ItemStream.update(...)` cung cấp trạng thái để checkpoint; `ItemStream.close()` giải phóng resource. `ExecutionContext` được lưu ở JobRepository để lần restart tìm lại tiến độ.

- Reader file: offset/line number và khả năng nguồn file không đổi.
- Reader JDBC cursor: vị trí đọc theo hợp đồng reader, query deterministic và snapshot nhất quán.
- Paging reader: page/keyset state, sort key ổn định và lưu ý tập dữ liệu bị mutate.
- Reader queue: redelivery và transaction/ACK theo transport, không tương đương file offset.

`readCount` là thống kê; nó **không thay thế** state reader, business key và snapshot. Nếu input thay đổi, checkpoint số dòng có thể trỏ sang item khác.

## 5. Mô hình A: dùng chung một DataSource và transaction manager

Khi metadata và business data có thể cùng nằm trong **một transactional datasource**, đây thường là mô hình đơn giản nhất để giảm khoảng lỗi giữa chunk commit và checkpoint.

~~~text
Single PostgreSQL database / one transaction domain
  ├─ BATCH_* metadata tables
  ├─ source_snapshot tables
  ├─ normalized_result tables
  └─ business_outbox table

Shared DataSource bean
Shared JdbcTransactionManager bean
JobRepository + Step chunk use shared transactional resource
~~~

### 5.1. Cấu hình Spring Batch 5.2.x với một datasource

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing(
        dataSourceRef = "dataSource",
        transactionManagerRef = "transactionManager")
public class SharedTransactionBatchConfig {

    // DataSource bean tên "dataSource" được cung cấp ở nơi khác;
    // gồm cả Spring Batch metadata tables và business tables.

    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(
            @Qualifier("dataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    public Step normalizeStep(
            JobRepository jobRepository,
            @Qualifier("transactionManager")
            PlatformTransactionManager txManager,
            ItemReader<SnapshotRow> reader,
            ItemWriter<SnapshotRow> writer) {

        return new StepBuilder("normalizeStep", jobRepository)
                .<SnapshotRow, SnapshotRow>chunk(200, txManager)
                .reader(reader)
                .writer(writer)
                .build();
    }
}
~~~

`SnapshotRow`, `dataSource` và reader/writer là phần do ứng dụng định nghĩa. Code minh họa wiring, không phải runnable project hoàn chỉnh. `@EnableBatchProcessing` tương tác với Spring Boot auto-configuration; **không trộn nhiều cơ chế tạo JobRepository** rồi giả định Boot tạo đúng bean mong muốn. Trong Spring Batch 5.2, `dataSourceRef` chọn bean datasource của repository và `transactionManagerRef` chọn bean manager của repository.

### 5.2. Vì sao “cùng database” vẫn chưa chắc cùng transaction?

| Điều quan sát | Có đủ chứng minh atomicity giữa metadata và writer? |
| --- | --- |
| Cùng hostname/DB URL | **Không**: hai connections/pools riêng vẫn có commits độc lập |
| Cùng DB username | **Không**: credential không xác định transaction |
| Hai `DataSource` beans trỏ cùng DB | **Không tự động**: có thể lấy hai physical connections |
| Hai `JdbcTransactionManager` beans khác nhau | **Không tự động**: transaction resource binding có thể khác |
| Cùng `DataSource` bean + cùng `PlatformTransactionManager`, writer dùng Spring-aware JDBC | Có cơ sở để cùng local TX **nếu resource thực sự tham gia**, cần integration test |
| Writer gọi API/broker rồi commit JDBC | **Không**: API/broker không thuộc JDBC TX |

Với JDBC, `JdbcTemplate`/`JdbcBatchItemWriter` phải dùng **đúng datasource**. Tự gọi `DriverManager.getConnection()` hoặc một datasource proxy khác không tương thích có thể tạo connection ngoài transaction.

### 5.3. Test rollback end-to-end

Không chỉ nhìn annotation. Một test có giá trị:

1. Ghi hai bản ghi business trong chunk, cho writer ném exception **trước commit**.
2. Xác minh business rows chưa commit **không tồn tại**.
3. Xác minh checkpoint không nhảy qua chunk bị rollback.
4. Sửa lỗi, restart cùng `JobInstance` và so tập business keys.
5. Chạy thêm test lỗi sát thời điểm DB commit vì “kết quả commit không xác định” vẫn là trạng thái phải đối soát.

Ngay cả mô hình một DB, external API/file writes nằm ngoài JDBC TX vẫn có thể lặp khi chunk retry.

## 6. Mô hình B: JobRepository và business ở hai DataSource

Tách metadata DB khỏi dữ liệu nghiệp vụ hữu ích khi muốn cô lập vận hành, credentials hoặc throughput. Nhưng mô hình này **không tự giữ tính nguyên tử của chunk/checkpoint**.

~~~mermaid
flowchart LR
    S["Worker Step"] --> ST["Step TX Manager"]
    ST --> A[("Business Database A")]
    S --> JR["JobRepository"]
    JR --> MT["Repository TX Manager"]
    MT --> B[("Metadata Database B")]
    A -.->|"Không có local atomic commit chung"| B
~~~

### 6.1. Cấu hình rõ tên và resource

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTxManager")
public class SplitDataSourceBatchConfig {

    // Hai bean DataSource được cấu hình riêng tại nơi khác.
    // Metadata tables dùng batchDataSource;
    // business writer dùng businessDataSource.

    @Bean("batchTxManager")
    public PlatformTransactionManager batchTxManager(
            @Qualifier("batchDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean("businessTxManager")
    public PlatformTransactionManager businessTxManager(
            @Qualifier("businessDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    public Step migrateStep(
            JobRepository jobRepository,
            @Qualifier("businessTxManager")
            PlatformTransactionManager businessTx,
            ItemReader<SnapshotRow> reader,
            ItemWriter<SnapshotRow> writer) {

        return new StepBuilder("migrateStep", jobRepository)
                .<SnapshotRow, SnapshotRow>chunk(250, businessTx)
                .reader(reader)
                .writer(writer)
                .build();
    }
}
~~~

`dataSourceRef`/`transactionManagerRef` thuộc **repository configuration**. Tham số thứ hai của `chunk(250,businessTx)` thuộc **worker chunk transaction**. Đây là hai lựa chọn riêng biệt, phải ghi rõ trong tài liệu vận hành.

### 6.2. Bảng failure window khi hai local commits không atomic

| Thời điểm sự cố | Business A | Checkpoint B | Nguy cơ |
| --- | --- | --- | --- |
| Cả hai chưa commit | Không ghi chunk mới | Chưa tiến | Restart làm lại phần còn thiếu |
| A commit nhưng B còn state cũ | Dữ liệu đã ghi | Chưa đánh dấu | **Xử lý lại item** đã có ở A |
| B đã tiến nhưng A rollback | Dữ liệu còn thiếu | Có vẻ đã xử lý | **Bỏ sót** nếu reader resume sau chunk đó |
| A và B commit | Đúng | Đúng | Trạng thái mong đợi |
| Mất kết nối sát commit | Không chắc | Có thể không chắc | Phải xác minh từ hai hệ thống trước restart |

Thứ tự thực tế tùy transactional advice, propagation, commit phase và điểm lỗi. **Không giả định một thứ tự cố định rồi thiết kế hệ thống chỉ chống một nửa các trường hợp.**

Spring Batch 5.2 mô tả rõ: transaction manager của Step được phép khác manager của JobRepository, nhưng khi đó **repository và processing database không ở cùng transaction**; nếu xử lý thành công rồi metadata chưa được cập nhật, restart có thể dẫn đến xử lý trùng. Phải phòng bằng **idempotent processing hoặc external transaction coordination**.

### 6.3. Repository transaction có phải một transaction phân tán?

Không. Việc `JobRepository` và business writer cùng hoạt động trong một Java method/thread **không** tạo two-phase commit. `@Transactional` trên service chỉ chọn một manager/transaction domain theo quy tắc Spring; Spring Batch không tự enlist datasource khác vào transaction đó.

Nếu thật sự phải commit A và B cùng một atomic transaction, cần đánh giá `JtaTransactionManager` với **XA-capable resources** và coordinator/recovery được cấu hình, không chỉ hai local managers.

## 7. Chiến lược giảm rủi ro khi không thể dùng chung transaction

Với hai databases độc lập, hướng thực dụng là **làm thao tác business an toàn khi replay** và tạo cơ chế phát hiện sai khác metadata/output.

1. Chốt **immutable snapshot** theo `snapshotId` và identifying JobParameters.
2. Reader dùng deterministic ordering và phạm vi partition không chồng lấn.
3. Writer có unique business key, upsert/version guard và logic phát hiện conflict.
4. External side effects (payment, email, broker) có idempotency key hoặc outbox/inbox.
5. Lưu audit/correlation đủ để tái dựng các item đã commit mà repository chưa xác nhận.
6. Sau crash, so metadata với business output; không restart mù nếu trạng thái commit chưa chắc chắn.
7. Trước publish dữ liệu downstream, thực hiện reconciliation theo business keys và aggregate values.

**Lưu ý:** idempotent writer chủ yếu làm an toàn tình huống **replay**. Nó **không tự sửa tình huống checkpoint đã tiến nhưng business rows chưa commit**. Với yêu cầu không bỏ sót, phải có reconciliation, durable work ledger/verification theo snapshot, hoặc kiến trúc transaction coordination phù hợp.

### 7.1. Đừng đánh đồng idempotency với bỏ qua lỗi

Nếu writer nhận lại một item cùng `event_id` và cùng source version:

- Cùng payload: no-op idempotent có thể chấp nhận.
- Khác payload với cùng version: đó là **conflict**; cần fail/audit, không im lặng bỏ qua.
- Version mới hơn: upsert nếu business semantics cho phép.
- Version cũ hơn: không ghi đè version mới, đồng thời ghi metric về stale replay.

Một câu SQL `ON CONFLICT DO NOTHING` không đủ chứng minh kết quả cuối đúng nếu thiếu so sánh version/payload và reconciliation.

## 8. Schema ví dụ: dữ liệu nguồn bất biến và kết quả versioned

Với PostgreSQL, ví dụ một nguồn snapshot vật lý:

~~~sql
CREATE TABLE source_snapshot (
    snapshot_id VARCHAR(100) NOT NULL,
    event_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY(snapshot_id, event_id)
);

CREATE TABLE normalized_event (
    event_id BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    amount NUMERIC(18,2) NOT NULL
);
~~~

Ràng buộc:

- `(snapshot_id,event_id)` là định danh duy nhất trong snapshot.
- Một JobInstance cần xử lý **đúng một snapshot** với range/file partition plan ổn định.
- Nếu đa tenant, `event_id` phải được mở rộng thành composite key `(tenant_id,event_id)` ở output.
- `source_version` tăng đơn điệu theo quy tắc nghiệp vụ; không lấy version chỉ vì “timestamp trông mới hơn”.
- Snapshot không được sửa trong lúc retry/restart; nếu thay đổi, phải có JobInstance/reprocess policy rõ ràng.

### 8.1. Writer SQL idempotent với version guard

~~~sql
INSERT INTO normalized_event(event_id, source_version, amount)
VALUES (:eventId, :sourceVersion, :amount)
ON CONFLICT (event_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    amount = EXCLUDED.amount
WHERE normalized_event.source_version < EXCLUDED.source_version;
~~~

Nếu item same/older version được replay, PostgreSQL có thể ghi nhận **0 updated rows**. Đó là behavior hợp lệ nhưng không chứng minh payload same-version đã đúng. Cần kiểm tra conflict theo nghiệp vụ.

### 8.2. JdbcBatchItemWriter dùng datasource của business transaction

~~~java
@Bean
public JdbcBatchItemWriter<SnapshotRow> resultWriter(
        @Qualifier("businessDataSource") DataSource ds) {

    return new JdbcBatchItemWriterBuilder<SnapshotRow>()
            .dataSource(ds)
            .sql("""
                INSERT INTO normalized_event(
                    event_id, source_version, amount)
                VALUES (:eventId, :sourceVersion, :amount)
                ON CONFLICT (event_id)
                DO UPDATE SET
                    source_version = EXCLUDED.source_version,
                    amount = EXCLUDED.amount
                WHERE normalized_event.source_version
                      < EXCLUDED.source_version
                """)
            .itemSqlParameterSourceProvider(row ->
                    new MapSqlParameterSource()
                        .addValue("eventId", row.eventId())
                        .addValue("sourceVersion", row.sourceVersion())
                        .addValue("amount", row.amount()))
            .assertUpdates(false)
            .build();
}
~~~

`SnapshotRow` là record/class do ứng dụng cung cấp; imports `JdbcBatchItemWriter`, builder, `MapSqlParameterSource`, `@Bean` và `@Qualifier` phải có trong ứng dụng. `assertUpdates(false)` giúp chấp nhận no-op khi replay cùng version; nếu bật assert mặc định, item idempotent no-op có thể bị hiểu là lỗi writer. Sự tồn tại của writer này **không thay thế transaction manager đúng datasource** hoặc kiểm tra xung đột payload.

### 8.3. Vì sao upsert không giải quyết mọi case?

Một nguồn tiền tệ có nghiệp vụ “cộng amount vào balance”. Nếu retry và SQL dùng `UPDATE balance = balance + :amount`, replay sẽ **cộng hai lần**. Không được coi code cộng dồn là idempotent chỉ vì có transaction.

Cách xử lý có thể là **ledger unique event_id** và cập nhật balance trong cùng business transaction có kiểm tra record đã áp dụng, hoặc tính kết quả xác định từ snapshot và upsert theo version. Khi business effect nằm ở HTTP service, cần stable idempotency key hoặc reconciliation với hệ thống đó.

## 9. Reader checkpoint: snapshot, thứ tự và restart

Một reader stateful phải được quản lý qua `ItemStream` nếu muốn Spring Batch lưu state phục vụ restart.

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<SnapshotRow> snapshotReader(
        @Qualifier("sourceDataSource") DataSource ds,
        @Value("#{jobParameters['snapshotId']}")
            String snapshotId,
        @Value("#{stepExecutionContext['startInclusive']}")
            Long start,
        @Value("#{stepExecutionContext['endExclusive']}")
            Long end) {

    return new JdbcCursorItemReaderBuilder<SnapshotRow>()
            .name("snapshotReader")
            .dataSource(ds)
            .sql("""
                SELECT event_id, source_version, amount
                FROM source_snapshot
                WHERE snapshot_id = ?
                  AND event_id >= ?
                  AND event_id < ?
                ORDER BY event_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, snapshotId);
                ps.setLong(2, start);
                ps.setLong(3, end);
            })
            .rowMapper((rs, n) -> new SnapshotRow(
                rs.getLong("event_id"),
                rs.getLong("source_version"),
                rs.getBigDecimal("amount")))
            .fetchSize(500)
            .saveState(true)
            .build();
}
~~~

Ví dụ cần `SnapshotRow` record, Spring beans và import tương ứng. Nếu `sourceDataSource` khác business datasource, reader không tự tham gia business DB local transaction; input snapshot phải bền vững theo JobInstance.

### 9.1. Vì sao cần range nửa mở?

Hai worker dùng:

~~~text
range-0000: [1,100001)
range-0001: [100001,200001)
~~~

Điều kiện `id >= start AND id < end` không trùng biên. Dùng `BETWEEN start AND end` sẽ làm ID ở biên thuộc cả hai partition vì `BETWEEN` thường gồm biên cuối.

Khi restart, đừng tính lại `MAX(event_id)`, đổi `gridSize`, thay tên worker step hoặc lấy danh sách file mới, làm plan khác lịch sử checkpoint.

### 9.2. ItemStream checkpoint không phải bảo đảm exactly-once

Reader có thể khôi phục offset đã lưu, nhưng:

- Business DB đã commit mà metadata chưa tiến: reader có thể phát lại item.
- Metadata tiến nhưng business DB chưa commit: reader có thể bỏ qua item.
- Source mutable: cùng offset có thể trỏ bản ghi khác.
- Cursor/transaction semantics khác nhau giữa JDBC, file và broker readers.
- Multi-threaded step dùng shared state và out-of-order commits có thể phức tạp hơn partitioned worker step.

Checkpoint là cơ chế **phục hồi tiến độ kỹ thuật**, phải đi cùng business idempotency và kiểm chứng data completeness.

## 10. Isolation level và tạo JobInstance đồng thời

JobRepository cần tránh hai process vô tình tạo/chạy **cùng JobInstance** đồng thời. Cấu hình JDBC repository của Spring Batch dùng transaction advice quanh CRUD methods, với isolation dành riêng cho thao tác `create*`.

Ví dụ Spring Batch 5.2:

~~~java
@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTxManager",
        isolationLevelForCreate = "SERIALIZABLE")
public class RepositoryIsolationConfig {
    // DataSource + PlatformTransactionManager beans được cấu hình riêng.
}
~~~

Tài liệu Spring Batch nêu default isolation cho repository `create*` thường là `SERIALIZABLE`. Trong một số database/workload, `READ_COMMITTED` có thể đủ nếu đã kiểm chứng cạnh tranh tạo JobInstance và unique constraints; **đổi isolation phải dựa trên test multi-launch đồng thời**, không chỉ giảm lock vì benchmark.

### 10.1. Isolation của repository create khác chunk isolation

| Tham số | Áp dụng | Ý nghĩa |
| --- | --- | --- |
| `isolationLevelForCreate` | Transaction repository khi tạo JobInstance/JobExecution | Tránh race khi hai launcher đồng thời tạo same instance |
| `transactionAttribute(...isolation...)` trên Step | Transaction của chunk work | DB consistency/locks cho nghiệp vụ |
| Isolation của remote worker database | Transaction của worker | Không thể suy từ manager repository |
| `JobParameters` identifying | Danh tính logic JobInstance | Không phải transaction isolation |

Không tăng isolation toàn bộ chunk lên `SERIALIZABLE` chỉ vì repository create dùng mức đó; nhiều worker có thể tăng deadlock/serialization retry và giảm throughput.

### 10.2. JobParameters: identifying và non-identifying

Một JobInstance được định danh bởi job name cộng **identifying JobParameters**. Nếu thêm `run.id` mới rồi chạy lại, có thể tạo **JobInstance khác**, không phải restart JobInstance bị lỗi.

~~~text
JobInstance A:
  jobName = settlementJob
  snapshotId = v42 (identifying)
  businessDate = 2026-11-25 (identifying)

JobExecution 1001: FAILED
JobExecution 1002: RESTART -> cùng JobInstance A

Nếu đổi snapshotId hoặc thêm identifying run.id:
  JobInstance B -> không có lịch sử worker completed của A
~~~

Khi phục hồi, dùng API restart phù hợp của `JobOperator`/launcher và giữ identifying parameters. Không dùng một lần start mới để lách trạng thái `FAILED` nếu nó khiến toàn bộ dữ liệu được xử lý lại.


## 11. Phối hợp JobRepository trong partitioned step

Một partitioned step có **manager StepExecution** và các **worker StepExecution**. Manager chia input thành partition keys và `ExecutionContext`; `PartitionHandler` thực thi workers. Mỗi worker có chunk transactions và checkpoint của riêng mình.

~~~mermaid
flowchart TB
    J["JobInstance(snapshot=v42)"] --> MS["Manager StepExecution"]
    MS --> PH["PartitionHandler"]
    PH --> W0["worker:range-0000"]
    PH --> W1["worker:range-0001"]
    PH --> W2["worker:range-0002"]
    W0 --> C0["COMMIT các chunks riêng"]
    W1 --> C1["COMMIT các chunks riêng"]
    W2 --> C2["COMMIT các chunks riêng"]
    W0 --> JR[("JobRepository")]
    W1 --> JR
    W2 --> JR
    MS --> JR
~~~

Một chunk ở `range-0001` rollback **không** rollback những chunk đã commit ở `range-0000` hay `range-0002`. Nếu worker `range-0001` cuối cùng `FAILED`, manager/job có thể fail dù các partition khác đã có kết quả bền vững.

### 11.1. Local partitioning với repository chung

~~~java
@Bean("workerStep")
public Step workerStep(
        JobRepository repository,
        @Qualifier("businessTxManager")
            PlatformTransactionManager businessTx,
        ItemReader<SnapshotRow> reader,
        ItemWriter<SnapshotRow> writer) {

    return new StepBuilder("workerStep", repository)
            .<SnapshotRow, SnapshotRow>chunk(250, businessTx)
            .reader(reader)
            .writer(writer)
            .build();
}

@Bean("managerStep")
public Step managerStep(
        JobRepository repository,
        Partitioner partitioner,
        @Qualifier("workerStep") Step worker,
        @Qualifier("partitionExecutor") TaskExecutor executor) {

    return new StepBuilder("managerStep", repository)
            .partitioner("workerStep", partitioner)
            .step(worker)
            .gridSize(24)
            .taskExecutor(executor)
            .build();
}
~~~

Đây là các bean methods minh họa; `Partitioner`, `TaskExecutor`, Spring imports và hạ tầng datasource cần được cung cấp. `gridSize(24)` là hint cho partitioner, **không nhất thiết có 24 threads**. Nếu immutable manifest tạo 40 partitions, số partition logic có thể khác hint.

**Mấu chốt:** mỗi worker dùng `JobRepository` được inject để lưu checkpoint. Chunk business work dùng `businessTxManager`. Nếu repository nằm trên datasource khác, hai loại ghi **không tự atomic** chỉ vì cùng Java `JobRepository` object được truyền vào StepBuilder.

### 11.2. Identity của partition và PartitionNameProvider

~~~text
snapshot=v42
  workerStep:range-0000 => [1,100001)
  workerStep:range-0001 => [100001,200001)
  workerStep:range-0002 => [200001,300001)
~~~

Khi restart, splitter đối chiếu tên worker step/partition với metadata lịch sử. Vì vậy:

- Dùng partition keys ổn định, không tạo UUID mới.
- Giữ manifest nguồn và ranges không chồng lấn.
- Không tính lại `MAX(id)` hoặc chia lại số partitions theo số pods mới.
- `PartitionNameProvider#getPartitionNames(...)` có thể lấy **toàn bộ tên từ manifest cũ** để tối ưu restart; splitter mới quyết định partition nào cần chạy theo JobRepository.
- Reader dùng `@StepScope` và `ExecutionContext` của worker riêng; tránh chia sẻ reader state giữa chunk threads.

### 11.3. Restart các partition chưa hoàn tất

~~~text
JobExecution #700:
  workerStep:range-0000 COMPLETED
  workerStep:range-0001 FAILED
  workerStep:range-0002 COMPLETED

JobExecution #701 (cùng JobInstance):
  workerStep:range-0001 được xem xét chạy lại
  range-0000 và range-0002 không chạy lại theo mặc định
~~~

Điều kiện là metadata nhất quán, names không đổi, không bật chính sách ép completed step chạy lại và worker cũ không còn thực thi. Với repository khác DB writer, cần thêm reconciliation trước restart vì metadata có thể chậm hơn business commits.

## 12. Trạng thái repository sau crash không phản ánh đầy đủ business state

| Trạng thái | Ý nghĩa thường gặp | Hành động đúng |
| --- | --- | --- |
| `STARTING` | Execution đã được tạo nhưng chưa bắt đầu hoàn toàn | Kiểm tra launcher/worker |
| `STARTED` | Metadata ghi nhận execution đang chạy | Không tự kết luận worker đã chết khi mất kết nối |
| `COMPLETED` | Step/Job kết thúc thành công kỹ thuật | Đối soát business output trước publish |
| `FAILED` | Framework ghi nhận thất bại | Kiểm tra checkpoint, dữ liệu commit và retry/restart |
| `STOPPING` | Có yêu cầu dừng | Theo dõi graceful shutdown |
| `STOPPED` | Đã dừng có điều phối | Đánh giá điều kiện restart |
| `UNKNOWN` | Không xác định chắc trạng thái | Điều tra, không đổi metadata tùy tiện |

Khi remote worker bị `SIGKILL` hoặc node mất điện, nó **không có cơ hội** cập nhật StepExecution thành `FAILED`. JobRepository có thể giữ `STARTED` dù process đã chết.

### 12.1. Đừng sửa BATCH_* để ép completed

~~~sql
-- ANTI-PATTERN, KHÔNG THỰC THI:
UPDATE BATCH_STEP_EXECUTION
SET STATUS = 'COMPLETED'
WHERE STEP_EXECUTION_ID = :id;
~~~

Đổi status bằng SQL không làm business rows xuất hiện, không sửa reader checkpoint và có thể phá version optimistic locking. Khi metadata `STARTED`/`UNKNOWN`, phải kiểm tra worker liveness, DB commits, broker, logs và snapshot trước khi quyết định recovery.

### 12.2. Optimistic locking không phải distributed fencing

Spring Batch repository dùng các version fields và optimistic locking để phát hiện cập nhật metadata không nhất quán. Nhưng optimistic locking metadata **không tự ngăn worker cũ** tiếp tục gửi HTTP charge, ghi file hoặc commit JDBC writer ở một resource khác.

Nếu manager mất kết nối tới worker A nhưng A còn chạy, việc phát worker B cùng partition có thể tạo double execution. Cần liveness checks, lease/fencing khi cần, và business idempotency.

## 13. Remote partitioning và metadata dùng chung

Remote partitioning mở rộng worker StepExecutions qua nhiều JVM/pods. Manager gửi `StepExecutionRequest`; worker nhận và thực thi với repository/context phù hợp.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Middleware
    participant W as Worker JVM
    participant B as Business DB
    participant R as JobRepository
    M->>R: Create worker StepExecutions
    M->>Q: StepExecutionRequest
    Q->>W: Deliver request
    W->>R: Load StepExecution / ExecutionContext
    W->>B: Process chunk + COMMIT
    W->>R: Update checkpoint/status
    Note over W,Q: Worker crash trước reply hoặc ACK
    W--xM: Reply không tới manager
    Note over M,Q: Timeout không chứng minh business chưa commit
~~~

Nếu mỗi worker vô tình kết nối tới một JobRepository schema khác, nó có thể không tìm thấy StepExecution hoặc cập nhật sai metadata. Các worker phải nhất quán về:

1. Metadata JDBC URL/schema/table prefix.
2. Transaction manager/isolation và resource policy.
3. Version Spring Batch và serializer `ExecutionContext`.
4. Tên Job/Step, identifying JobParameters và partition keys.
5. Schema migrations, permissions và connection pool.
6. Correlation IDs, broker request/reply contract.
7. Graceful stop, retries và timeout.

Một transaction local **không được truyền qua message**. Shared repository là persisted coordination, không phải một distributed transaction bao mọi remote worker.

### 13.1. Ba tín hiệu không thể thay thế nhau

| Tín hiệu | Cho biết | Không chứng minh |
| --- | --- | --- |
| Broker ACK | Message được xác nhận theo transport policy | Business DB đã commit hay manager nhận reply |
| Worker reply success | Worker gửi kết quả thực thi | Downstream API side effect xảy ra đúng một lần |
| `StepExecution.COMPLETED` | Repository lưu trạng thái thành công kỹ thuật | Business output độc lập đã được đối soát |
| Business row có key/version | Writer đã ghi hiệu ứng nghiệp vụ | Checkpoint đã phản ánh commit |
| Outbox marked SENT | Dispatcher ghi nhận gửi | Consumer chắc chắn áp dụng đúng duy nhất |

Khi mất ACK/reply, không đơn giản phát lại worker request nếu có thể worker cũ vẫn hoạt động. Xác minh `StepExecution`, liveness và business data trước khi khôi phục.

### 13.2. Remote chunking có checkpoint khác

Trong **remote chunking**, manager đọc item và gửi chunk requests cho worker; trong **remote partitioning**, worker tự đọc shard. Cả hai có thể gặp redelivery sau broker/worker crash, nhưng nơi giữ reader state và cách lưu metadata khác nhau.

Không sao chép retry protocol giữa hai mô hình khi chưa xét transaction boundaries, request correlation, reply/ACK và ownership.

## 14. @Transactional, propagation và sự tách biệt resource

Một callback của reader/processor/writer thường chạy trong chunk transaction. Nếu callback gọi service có `@Transactional`, kết quả phụ thuộc **manager được chọn và propagation**.

| Service/callback | Khi chunk đang transactional | Rủi ro |
| --- | --- | --- |
| `@Transactional("businessTxManager")` + `REQUIRED` | Có thể tham gia cùng chunk TX | Phù hợp nếu resource giống nhau |
| `REQUIRES_NEW` cùng manager | Mở TX mới, suspend outer | Inner commit tồn tại dù chunk rollback; có thể cần connection khác |
| `@Transactional("auditTxManager")` | Có thể mở transaction domain khác | Audit commit độc lập với business |
| `NOT_SUPPORTED` | Suspend TX phù hợp | Không tự nhả locks của outer transaction |
| `@Async` | Thread mới không tự mang imperative TX | Side effect có thể xảy ra trước commit và mất sau crash |
| Gửi broker trực tiếp từ writer | Broker ngoài JDBC transaction | Message có thể publish nhưng DB rollback |

### 14.1. Marker dedupe trong REQUIRES_NEW gây sai dữ liệu

~~~java
@Transactional(
        transactionManager = "businessTxManager",
        propagation = Propagation.REQUIRES_NEW)
public void markApplied(long itemId) {
    auditDao.insertAppliedMarker(itemId);
}
~~~

Nếu gọi trong writer của outer chunk, method này có thể commit marker độc lập. Sau đó outer chunk rollback, marker “đã áp dụng” **vẫn tồn tại** dù business data chưa được commit. Restart thấy marker và bỏ qua item sẽ **mất dữ liệu**.

Nếu marker dùng bảo vệ idempotency, nó nên commit **cùng transaction/resource với business write**, hoặc có một durable workflow được thiết kế rõ.

### 14.2. Proxy boundary, exception và transaction timeout

- Trong proxy mode mặc định, `this.helper()` cùng bean có thể bỏ qua `@Transactional` vì không qua Spring proxy.
- Mặc định `@Transactional` rollback `RuntimeException`/`Error`; checked exception có thể cần `rollbackFor`.
- Bắt rồi nuốt exception có thể khiến interceptor coi method thành công và commit.
- Transaction timeout không mặc định cắt một HTTP call đang block; cần deadline của HTTP client.
- Một `@Transactional` chọn nhầm manager có thể khiến writer trên datasource khác không rollback.

Không kiểm chứng chỉ bằng unit test mock manager; dùng integration tests trên resource thật.

## 15. Ghi DB và publish broker: dùng outbox, không dùng checkpoint làm queue

Gọi broker send ngay trong `ItemWriter` trước chunk commit là một **dual-write problem**:

~~~text
BEGIN business DB TX
UPDATE order_projection
broker.publish("ORDER_READY")   -- message có thể đã tới consumer
ROLLBACK business DB            -- broker event không rollback theo JDBC
~~~

Ngược lại, nếu DB commit rồi process crash **trước** khi publish, downstream có thể không nhận event.

**Transactional outbox** làm ý định gửi và business write cùng một local DB transaction, rồi dispatcher publish sau commit:

~~~mermaid
sequenceDiagram
    participant S as Spring Batch Writer
    participant D as Business DB
    participant X as Outbox Dispatcher
    participant Q as Broker
    S->>D: BEGIN
    S->>D: UPSERT business result
    S->>D: INSERT outbox event
    S->>D: COMMIT
    X->>D: Claim pending event; COMMIT
    X->>Q: Publish outside DB TX
    Q-->>X: Confirm
    X->>D: Mark SENT; COMMIT
    Note over X,Q: Crash sau publish trước SENT => có thể gửi lại
~~~

### 15.1. Outbox SQL cùng business datasource

~~~sql
CREATE TABLE normalized_event_outbox (
    event_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    PRIMARY KEY(event_id, source_version, event_type)
);

-- Trong CÙNG business chunk transaction với normalized_event:
INSERT INTO normalized_event_outbox(
    event_id, source_version, event_type, payload)
VALUES (
    :eventId, :sourceVersion,
    'EVENT_NORMALIZED', CAST(:payload AS jsonb))
ON CONFLICT (event_id, source_version, event_type)
DO NOTHING;
~~~

Outbox ở datasource khác với business write **không atomic** chỉ vì cùng method Java. Dispatcher nên claim và commit trước network call; không giữ JDBC lock trong lúc chờ broker. Consumer phải có inbox/dedupe theo stable event ID vì publish có thể lặp sau crash.

### 15.2. AFTER_COMMIT callback có đủ không?

`@TransactionalEventListener(phase=AFTER_COMMIT)` hoặc transaction synchronization giúp gọi handler sau DB commit khi JVM còn sống, nhưng **không đảm bảo durable delivery** nếu JVM chết ngay sau commit. Outbox row bền vững hoặc cơ chế tương đương mới bảo vệ khoảng lỗi này.

`BATCH_STEP_EXECUTION_CONTEXT` không thay thế outbox. Nó lưu **checkpoint** của framework, không được thiết kế như business message queue để chứa hàng triệu events, retries/DLQ và payloads cho downstream.


## 16. Một local transaction, JTA/XA hay eventual consistency?

| Kiến trúc | Bảo đảm | Điểm mạnh | Chi phí/rủi ro |
| --- | --- | --- | --- |
| Repository + business cùng JDBC datasource/manager | Có thể commit cùng **local DB transaction** nếu cả hai tham gia đúng | Giảm khoảng lỗi checkpoint/business | Chung DB workload, metadata contention |
| Repository DB riêng + business DB riêng | Hai local commits độc lập | Cô lập dữ liệu, permissions và vận hành | Replay/missing khi metadata và output lệch |
| JTA/XA với XA-capable resources | Global two-phase commit khi enlist đúng | Atomicity mạnh hơn cho resources hỗ trợ | Coordinator/recovery, in-doubt, lock lâu và overhead |
| Business DB + transactional outbox | Atomic business result + **ý định gửi** trong DB | Recovery event bền, phù hợp broker/API | Eventual delivery, consumer dedupe |
| Durable work ledger + idempotency | Recovery theo từng business operation | Linh hoạt với HTTP/external services | State machine, lease, reconciliation |
| Saga/compensation | Nhiều transactions độc lập với bước bù | Không bắt mọi resource dùng XA | Logic bù và trạng thái trung gian phức tạp |

### 16.1. JTA/XA không chỉ là thay bean

Nếu muốn metadata DB A và business DB B atomic:

1. Có **global transaction coordinator** thật với recovery logs.
2. Cả hai datasources phải XA-capable và enlist trong **cùng global transaction**.
3. JobRepository advice/Step transaction phải dùng transaction coordination tương ứng.
4. Driver, connection pool, isolation và timeout phải hỗ trợ XA.
5. Đã test coordinator crash, in-doubt và heuristic outcomes.
6. Đã benchmark two-phase commit, lock duration và throughput ở peak load.

`JtaTransactionManager` không tự biến một JDBC DataSource thường thành XA resource. HTTP API, file output và nhiều broker deployments không tham gia XA, nên cần outbox/idempotency hoặc protocol khác.

### 16.2. ChainedTransactionManager không tạo atomicity

Một chain gọi commit manager A rồi manager B không có prepare phase. Nếu A đã commit mà B lỗi, A không thể rollback ngược đơn giản. Đừng coi chained local transactions hoặc transaction synchronization là thay thế XA khi nghiệp vụ đòi atomic cross-resource commit.

**Quy tắc:** xác định resource nào bắt buộc commit cùng nhau, chúng có cùng local transaction/XA không, và mọi partial outcome còn lại được phục hồi bằng cách nào.

## 17. JobRepository dưới tải lớn: locks và resource pools

Tăng từ 4 lên 64 workers làm số StepExecutions/chunk commits tăng. Metadata DB có thể trở thành nút thắt do lock, connection acquisition hoặc IOPS, ngay cả khi business writer còn nhiều headroom.

### 17.1. Ước lượng metadata update rate

Giả sử 32 worker StepExecutions đang chạy; mỗi worker commit trung bình 10 chunks/s:

\[
R_{\mathrm{chunk}}=32\times10=320\ \text{chunk commits/s}.
\]

**Không đồng nhất** 320 chunk commits/s với đúng 320 metadata SQL statements/s. Một chunk có thể cập nhật `StepExecution`, `ExecutionContext` khi dirty và các callback khác; số SQL phụ thuộc implementation. Cần đo JobRepository DB thật.

### 17.2. Chunk size và partition count khác nhau

| Tăng tham số | Hiệu quả có thể có | Rủi ro |
| --- | --- | --- |
| Chunk size K | Ít commits/metadata updates | Transaction dài, lock, rollback scope, heap |
| Partition count P | Giảm skew và tạo work units | StepExecution metadata, startup/reader overhead |
| Worker concurrency C | Che I/O wait, thêm CPU utilization | Business/JobRepository pool contention, retry storm |
| Repository JDBC pool | Giảm pending nếu DB còn headroom | DB lock/IOPS saturation nếu đã bão hòa |
| Business JDBC pool | Giảm acquire wait có điều kiện | Tăng DB CPU, locks, contention |
| Isolation của repository create | Kiểm soát job-launch races | Isolation quá mạnh tốn lock, quá yếu gây race |

Ví dụ 20 triệu records với `chunk(200)` tương ứng khoảng **100.000 chunk commits** lý tưởng (chưa tính retry/skip/partial chunks). Tăng lên chunk 2.000 giảm commits lý tưởng khoảng 10 lần nhưng có thể giữ locks/heap lâu hơn. Phải benchmark với lỗi và restart, không chỉ clean run.

### 17.3. Connection budget toàn cluster

Tám worker pods, mỗi pod Hikari tối đa 12 business connections; manager tối đa 8:

\[
C_{\mathrm{configured}}=8\times12+8=104.
\]

Đây là tổng trần cấu hình nhóm giả định, không phải active connections. Nếu metadata DB riêng, nó có connection budget riêng; nếu dùng chung server, tải CPU/IOPS vẫn cộng dồn. `JdbcCursorItemReader` có thể giữ cursor connection riêng với writer chunk connection tùy driver/config.

### 17.4. Tách metadata DB là thay đổi recovery contract

Có thể giúp cô lập IOPS, backup, permissions và capacity, nhưng thay topology **từ same local transaction sang two local commits** nếu trước đó cùng resource.

Trước khi triển khai phải có idempotent writer, immutable source snapshot, fault tests tại business commit–metadata update, reconciliation detect missing keys và JobRepository HA/backup. Một metadata DB outage khi business DB còn khỏe **không được âm thầm bỏ qua checkpoint failures**.

## 18. SQL đọc metadata và đối soát business output

Các SQL dưới đây chỉ là **read-only diagnostics**. Không dùng SQL để tự sửa trạng thái `BATCH_*`.

### 18.1. Lịch sử StepExecutions trong một JobInstance

~~~sql
SELECT
    je.JOB_INSTANCE_ID,
    se.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.START_TIME,
    se.END_TIME,
    se.VERSION
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
WHERE je.JOB_INSTANCE_ID = :jobInstanceId
ORDER BY se.STEP_NAME, se.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
~~~

Với partitioning có thể thấy cùng logical partition name qua các JobExecutions. `VERSION` ở đây là optimistic-locking metadata, **không** phải source version nghiệp vụ.

Không cộng `READ_COUNT` qua mọi executions để tính unique items: retry/restart có thể đọc lại cùng record.

### 18.2. Xem JobExecutions và trạng thái

~~~sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    STATUS,
    EXIT_CODE,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_JOB_EXECUTION
WHERE JOB_INSTANCE_ID = :jobInstanceId
ORDER BY JOB_EXECUTION_ID;
~~~

Nhiều JobExecutions cùng JobInstance có thể phản ánh restart. Nếu có nhiều JobInstances gần giống nhau, xem identifying `JobParameters`, đặc biệt `snapshotId` và `run.id`.

### 18.3. Reconciliation theo business key/version

~~~sql
SELECT s.event_id, s.source_version
FROM source_snapshot s
LEFT JOIN normalized_event o
       ON o.event_id = s.event_id
      AND o.source_version = s.source_version
WHERE s.snapshot_id = :snapshotId
  AND o.event_id IS NULL;
~~~

Query tìm source rows không có output cùng version. **Giới hạn:** nếu `normalized_event` chỉ lưu latest version từ một snapshot sau, query này có thể báo thiếu theo chính sách không phù hợp. Muốn kiểm tra từng snapshot chính xác, lưu output/audit theo `snapshot_id` hoặc ledger phiên bản.

### 18.4. Count và totals chỉ là một phần bằng chứng

~~~sql
SELECT COUNT(*) AS expected_count,
       COALESCE(SUM(amount), 0) AS expected_amount
FROM source_snapshot
WHERE snapshot_id = :snapshotId;

SELECT COUNT(*) AS output_count,
       COALESCE(SUM(amount), 0) AS output_amount
FROM normalized_event
WHERE event_id IN (
    SELECT event_id FROM source_snapshot
    WHERE snapshot_id = :snapshotId
);
~~~

Count/tổng bằng nhau **chưa chứng minh** không thiếu/trùng; một missing và một duplicate có thể bù nhau. Cần kiểm tra unique business keys, source versions, domain invariants và aggregate độc lập.

### 18.5. Hai databases không join trực tiếp theo mặc định

Khi metadata và business ở hai databases:

1. Đọc JobInstance/StepExecution metadata từ repository DB.
2. Đọc output keys/versions/totals từ business DB.
3. Đọc tập expected từ immutable source snapshot.
4. Đối soát theo cùng `snapshotId` trong một công cụ read-only, có audit.
5. Với mismatch, phân biệt checkpoint behind, ahead hay commit outcome chưa rõ.
6. Không mark job `COMPLETED` chỉ vì count ở hai nơi “trông giống nhau”.

## 19. Integration test: chứng minh contract ở resource thật

Không chỉ mock `PlatformTransactionManager` rồi assert rollback được gọi. Một test có giá trị phải kiểm tra **database output** và **JobRepository metadata** ở cả hai phía commit.

| Kịch bản | Fault injection | Điều chứng minh |
| --- | --- | --- |
| Shared datasource/manager | Throw giữa writer và commit | Business rows + checkpoint chưa commit cùng rollback |
| Các chunks trước đã commit | Lỗi ở chunk thứ 6 | Chunk 1–5 còn, chunk 6 không partial commit |
| Hai datasources | Kill ở business commit/metadata update | Detect crash windows; recovery đúng |
| Commit outcome mơ hồ | Cắt JDBC connection sát commit | Business key reconciliation trước retry |
| Repository DB mất kết nối | Block metadata DB | Step fail rõ, không đánh dấu completed giả |
| Duplicate job launch | Hai launchers cùng identifying params | Repository isolation/uniqueness đúng |
| Reader snapshot drift | Thay source giữa executions | Fail closed, không resume sai |
| Partition plan drift | Đổi keys/ranges | Phát hiện hoặc từ chối plan khác |
| Partition FAILED | Một worker fail, others COMPLETED | Restart chỉ phần cần |
| Remote worker crash | Kill sau DB commit trước reply | Idempotent writer khi redelivery |
| Remote worker A còn chạy | Start worker B cùng partition | Ownership/fencing hoặc protocol ngăn double effects |
| Outbox dispatcher crash | Kill sau publish trước SENT | Consumer inbox/dedupe |
| Wrong transaction manager | Writer datasource B, Step manager A | Integration test thấy rollback sai |
| Concurrency | 1/4/8/16 workers | Correctness + committed throughput + locks |

### 19.1. Test một datasource chia sẻ transaction

~~~text
Given:
  snapshot v42 có 1.000 items, chunk size=100;
  output rỗng; repository và writer cùng datasource/manager.

When:
  chunk #1 và #2 commit;
  chunk #3 ghi một phần rồi ném RuntimeException trước commit.

Then:
  output có đúng kết quả 2 chunks đã commit;
  chunk #3 không còn partial rows;
  checkpoint không nhảy qua chunk #3;
  StepExecution có rollback/failure state phù hợp.
~~~

### 19.2. Test two-datasource replay và missing

~~~text
Given:
  batchDataSource và businessDataSource tách biệt;
  cùng immutable snapshot và writer upsert theo event_id/version.

When:
  mô phỏng business COMMIT nhưng checkpoint cũ,
  sau đó restart cùng JobInstance.

Then:
  item có thể được phát lại;
  writer không tạo duplicate business effect;
  output cuối == clean-run reference.

Also test:
  checkpoint đã tiến nhưng business output thiếu.
  Reconciliation phát hiện missing business key,
  recovery không được silently mark completed.
~~~

Test ở thời điểm commit thật có thể khó deterministic; cần fault-injection harness DB/network hoặc fault hooks kiểm soát điểm crash. Không tuyên bố đã kiểm thử khi mới chỉ có unit test mock services.

### 19.3. Concurrent launch isolation

Cho hai processes gọi start cùng Job name + identifying parameters gần như đồng thời. Repository/DB phải tránh duplicate active execution sai nghiệp vụ. Quan sát constraint/exception và transaction behavior trước khi thay default `SERIALIZABLE` bằng isolation nhẹ hơn.


## 20. Runbook khi JobRepository và business data không khớp

Một runbook vận hành có thể theo trình tự:

1. **Giữ publish output**: không gửi dữ liệu chưa được đối soát xuống hệ thống thanh toán/báo cáo.
2. **Xác định identity**: ghi job name, JobInstanceId, JobExecutionId, StepExecutionId, snapshot ID và partition key.
3. **Kiểm tra liveness**: manager/worker nào còn đang chạy, đặc biệt remote worker còn `STARTED`.
4. **Khoanh vùng resource**: JobRepository và business writer dùng **datasource/transaction manager** nào, có cùng local TX không?
5. **Đọc lịch sử metadata**: status, commit/rollback counters, checkpoint/ExecutionContext đã persist.
6. **Xác minh business output**: các keys/versions đã commit, duplicate conflicts, incomplete chunks và side effects bên ngoài.
7. **Phân loại failure window**: checkpoint behind business, checkpoint ahead business, commit unknown hay nguồn snapshot drift.
8. **Kiểm tra lỗi gốc**: metadata DB outage, deadlock, JDBC timeout, stale StepExecution, broker redelivery hoặc misconfiguration.
9. **Đối chiếu partition plan**: tên và phạm vi không đổi so với lần chạy đầu, không chồng lấn.
10. **Chọn phương án phục hồi có kiểm chứng**: restart đúng JobInstance khi replay an toàn; với missing do checkpoint ahead cần repair/reprocess có kiểm soát theo business keys.
11. **Không sửa BATCH_* trực tiếp** như cách che lỗi; cần thủ tục thay đổi có kiểm toán nếu việc sửa metadata là bất khả kháng.
12. **Chạy fault test trên staging** cho kịch bản tương tự; kiểm tra cả worker generations và output.
13. **Đối soát lại trước publish**: key set, source versions, totals và external operation IDs.
14. **Cập nhật incident notes và alerts**: thêm metric detection thời gian commit/metadata lag và SLA headroom.

### 20.1. Ví dụ incident: metadata phía sau business

~~~text
snapshot=v42; partition=workerStep:range-0017

09:00:00  Chunk A bắt đầu
09:00:01  Business DB A ghi 250 items, COMMIT
09:00:01  Repository DB B chưa bền checkpoint mới
09:00:01  JVM crash
09:05:00  Restart cùng JobInstance
09:05:01  Reader đọc lại 250 items
~~~

Trong trạng thái này, **idempotent upsert** theo event ID/version có thể ngăn double writes khi reader replay. Đồng thời phải kiểm tra payload cùng version không mâu thuẫn, và kiểm tra các external side effects đã phát ra.

### 20.2. Ví dụ incident: metadata phía trước business

~~~text
snapshot=v42; partition=workerStep:range-0017

09:00:00  Chunk B bắt đầu
09:00:01  Metadata DB B ghi state tiến qua item #500
09:00:01  Business DB A rollback chunk vì connection failure
09:05:00  Reader restart từ state sau #500
~~~

Nếu không có reconciliation, các items chưa commit có thể bị bỏ sót. **Idempotent writer không tạo được row của item không bao giờ được đọc lại**. Cần durable audit/ledger hoặc reprocess strategy theo snapshot để phát hiện/sửa missing keys. Tránh tự sửa reader offset mà không đồng bộ output và repository state.

## 21. Những hiểu nhầm phổ biến

| Nhận định | Điều cần sửa |
| --- | --- |
| “Step có JobRepository là metadata và data atomic.” | Chỉ khi thật sự cùng transaction resource/coordination. |
| “Hai datasources cùng trỏ một PostgreSQL server nghĩa cùng TX.” | Hai connections/managers có thể commit độc lập. |
| “Step manager bằng repository manager theo mặc định mọi cấu hình.” | Hai dependency khác nhau; cần xem bean thực tế. |
| “JobRepository.updateExecutionContext trước COMMIT luôn an toàn.” | Hai local transactions vẫn có crash window. |
| “`readCount` bằng 1 triệu nghĩa đã xử lý duy nhất 1 triệu records.” | Retry/restart có thể đọc lại và rollback. |
| “Commit business rồi metadata fail thì Spring Batch tự biết DB đã có.” | Repository không tự đối soát resource ngoài transaction. |
| “Idempotent writer chữa được cả missing do checkpoint ahead.” | Nó ngăn duplicate khi replay, không tự sinh item bị bỏ qua. |
| “Metadata `COMPLETED` nghĩa không có duplicate external effects.” | Cần đối soát business keys, broker/API operations. |
| “Dùng `REQUIRES_NEW` trong writer làm checkpoint chắc hơn.” | Inner commit độc lập có thể phá atomicity chunk. |
| “`@Async` mặc định chạy sau DB commit và bền qua crash.” | Không tự mang transaction, không durable. |
| “Outbox row nên lưu trong JobRepository ExecutionContext.” | Context là checkpoint metadata, không phải business event queue. |
| “JobInstance restart chỉ cần tăng run.id.” | Identifying params mới có thể tạo JobInstance khác. |
| “`SERIALIZABLE` cho create* nghĩa chunks cũng SERIALIZABLE.” | Repository create isolation khác chunk isolation. |
| “64 partitions nghĩa 64 worker threads và 64 JDBC connections.” | GridSize, worker count, pools là các giới hạn khác. |
| “Worker mất reply nghĩa chưa commit.” | Worker có thể commit rồi ACK/reply bị mất. |
| “Sửa status BATCH_STEP_EXECUTION thành COMPLETED là hồi phục.” | Không sửa business output, checkpoint và locking contract. |
| “Có JTA bean tức cả hai DB đã XA.” | Cần XA factories, coordinator và enlistment thật. |
| “Publisher confirm nghĩa consumer đã áp dụng đúng một lần.” | Publish/ACK khác business idempotency. |

## 22. Checklist triển khai và vận hành

- [ ] Đã xác định chính xác datasource và `PlatformTransactionManager` của JobRepository.
- [ ] Đã xác định transaction manager của từng chunk/tasklet Step.
- [ ] Business writer thực sự tham gia transaction manager đúng resource.
- [ ] Biết rõ metadata và business nằm cùng local TX hay hai commits độc lập.
- [ ] `@EnableBatchProcessing`/Spring Boot auto-configuration không tạo nhầm repository.
- [ ] Schema, table prefix, serializer `ExecutionContext` và version Spring Batch phù hợp.
- [ ] Reader có `ItemStream`/checkpoint ổn định và snapshot nguồn bất biến.
- [ ] JobInstance identifying JobParameters được chốt trước lần chạy đầu.
- [ ] Partition keys/ExecutionContext/manifest không đổi khi restart.
- [ ] Worker remote chia sẻ đúng metadata repository và không có hai thế hệ ghi cùng partition.
- [ ] Các callback `@Transactional` dùng đúng manager/proxy/propagation.
- [ ] Writer idempotent với unique business key/version và conflict detection.
- [ ] Có reconciliation phát hiện **duplicate và missing** giữa source/output.
- [ ] External API/broker/file side effects có idempotency/outbox/inbox hoặc compensation.
- [ ] `JobRepository.create*` isolation được test với concurrent launch.
- [ ] Không dùng metadata tables làm message queue/payload store.
- [ ] Chunk size và worker concurrency được benchmark với JobRepository contention.
- [ ] Tính tổng JDBC connection pools trên mọi manager/worker pods.
- [ ] Đã test rollback/commit failures trên database thật.
- [ ] Đã test business commit–metadata lag và metadata ahead–business rollback.
- [ ] Đã test remote redelivery, worker crash và lost reply.
- [ ] Có dashboard JobRepository latency, pending pools, rollback count, committed throughput.
- [ ] Có runbook xử lý `STARTED`/`UNKNOWN`, không tự sửa BATCH_*.
- [ ] Business output chỉ được publish sau khi đối soát đạt.
- [ ] SLA còn recovery buffer cho các tình huống metadata DB outage.

## 23. Câu hỏi tự kiểm tra

1. `JobRepository` lưu những loại metadata nào, và vì sao không thể coi nó là business DB?
2. Khi `StepBuilder.chunk(250, businessTx)` nhận một manager khác repository manager, có còn đảm bảo một local commit chung không?
3. Tại sao metadata update “ngay trước commit” chưa đủ bảo đảm atomicity qua hai datasources?
4. Nếu business DB commit nhưng repository checkpoint cũ, restart có thể làm gì?
5. Nếu repository checkpoint tiến còn business DB rollback, tại sao upsert idempotent chưa đủ?
6. Hai pools trỏ cùng JDBC URL có phải một transaction không?
7. `@EnableBatchProcessing(dataSourceRef,transactionManagerRef)` định nghĩa manager của thành phần nào?
8. Khi chọn `@Transactional("auditTxManager")` trong writer của một business chunk, điều gì cần lưu ý?
9. `REQUIRES_NEW` có thể khiến marker dedupe commit nhưng business data rollback như thế nào?
10. Vì sao JobInstance identifying parameters phải ổn định khi restart?
11. Khi thay gridSize hoặc partition names giữa restart, splitter có nguy cơ gì?
12. Repository `create*` isolation dùng để ngăn tình huống nào?
13. Vì sao không nên dùng `READ_COUNT` qua các JobExecutions để tính unique source records?
14. Worker remote commit DB rồi mất reply; có được suy rằng partition chưa xử lý không?
15. `@TransactionalEventListener(AFTER_COMMIT)` có bảo đảm event không mất sau JVM crash không?
16. Outbox phải nằm ở database nào để atomic với business writer?
17. Vì sao outbox dispatcher và consumer vẫn cần dedupe?
18. Khi nào cần cân nhắc XA thay vì outbox? Cần những resource và hạ tầng nào?
19. Một JobExecution `COMPLETED` nhưng business source/version counts lệch: có công bố output được không?
20. Test nào xác nhận cùng datasource/manager thực sự rollback metadata và writer cùng nhau?
21. Metrics nào cảnh báo JobRepository đã thành bottleneck khi tăng worker?
22. Vì sao không nên sửa thủ công `BATCH_STEP_EXECUTION.STATUS` để ép restart?

**Gợi ý:** (1) Job/Step executions, contexts, statuses/counters, không quản lý toàn bộ business side effects. (2) Không, khi hai resources/managers khác nhau. (3) Trước commit về thứ tự callback không phải distributed atomic commit. (4) Reprocess chunk đã ghi, cần idempotency. (5) Reader có thể bỏ qua item còn thiếu. (6) Không tự động. (7) Repository datasource/manager. (8) Audit commit độc lập. (9) Inner TX commit trước outer rollback. (10) Giữ JobInstance và lịch sử checkpoint. (11) Mất mapping context/đọc trùng-bỏ sót. (12) Hai launchers cùng tạo same instance. (13) Retry/restart có thể đọc lại. (14) Không, DB có thể đã commit. (15) Không, cần durable outbox. (16) Cùng transactional datasource/manager với business output. (17) Publish có thể lặp sau crash trước mark SENT. (18) Resource XA-capable + coordinator/recovery. (19) Chưa, phải đối soát. (20) Inject writer failure rồi kiểm tra DB và checkpoint. (21) Repository latency, connection pending/lock, chunk commit p99, throughput. (22) Có thể phá context/version consistency, che mất dữ liệu.

## Tài liệu tham khảo

- [Spring Batch 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html): Step manager có thể khác repository manager; nguy cơ duplicate khi business processing và metadata không cùng transaction.
- [Spring Batch 5.2 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): repository transaction advice, `@EnableBatchProcessing` và `isolationLevelForCreate`.
- [Spring Batch 5.2 — Commit Interval](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/commit-interval.html): chunk transaction boundary.
- [Spring Batch 5.2 — Transaction Attributes](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/transaction-attributes.html): Step propagation/isolation/timeout.
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `ItemStream`, `ExecutionContext` và restart.
- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): partition manager/worker và distributed patterns.
- [Spring Batch 5.2 — TaskletStep API](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/step/tasklet/TaskletStep.html): chunk/transaction lifecycle và metadata state.
- [Spring Batch 5.2 — JobRepository API](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/repository/JobRepository.html): `updateExecutionContext` và `update(StepExecution)`.
- [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): local vs JTA transaction managers.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional` và proxy boundaries.
- [Spring Framework — JDBC Connection Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `JdbcTransactionManager`, `DataSourceTransactionManager` và resource binding.
- [Spring AMQP — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): local broker transactions và giới hạn XA.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): producer transactions, synchronization và failure window.

**Điểm cốt lõi:** `JobRepository` lưu tiến độ để Spring Batch restart, nhưng **chỉ khi metadata và business operations thực sự cùng transaction domain** thì chunk commit và checkpoint mới có cơ sở atomic trong local database. Khi dùng các transaction managers/datasources độc lập, luôn tồn tại khả năng **business commit nhưng checkpoint chưa tiến** hoặc **checkpoint đã tiến nhưng business output thiếu**. Hãy giữ immutable snapshot và partition plan ổn định, thiết kế writer idempotent cùng reconciliation phát hiện cả duplicate lẫn missing, dùng outbox cho external events, và kiểm thử crash/restart ở đúng các ranh giới transaction. Chỉ scale workers và tối ưu pool sau khi đã chứng minh được tính đúng đắn của dữ liệu cuối.
