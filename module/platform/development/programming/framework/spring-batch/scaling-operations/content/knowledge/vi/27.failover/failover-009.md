# Checkpoint trước khi mất node trong Spring Batch

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **checkpoint bền vững cuối cùng** là điểm phục hồi sau khi một JVM, container, máy chủ hoặc worker node biến mất; không nhầm với việc đoán trước thời điểm sự cố.
- Phân biệt `JobExecutionContext`, `StepExecutionContext`, state của `ItemStream`, metadata trong `JobRepository` và kết quả đã commit ở business database.
- Mô tả vòng đời một chunk, các thời điểm cập nhật checkpoint và rủi ro khi worker crash **trước/sau business commit**, hoặc trước khi manager nhận reply.
- Thiết kế input snapshot, partition mapping, reader và writer để worker mới tiếp tục xử lý mà **không bỏ sót hoặc nhân đôi hiệu ứng nghiệp vụ**.
- Hiểu cách failover thay đổi giữa single-process, local partitioning, **remote partitioning** và **remote chunking**.
- Dùng Java 17, Spring Batch 5.x và PostgreSQL để xây dựng ví dụ reader `@StepScope`, `ItemStream` checkpoint, writer idempotent và manager/worker partitioning.
- Định nghĩa các biện pháp dừng có kiểm soát, phát hiện node mất, ngăn worker cũ ghi tiếp (**fencing**), restart và quan sát tiến độ.
- Đánh giá trade-off giữa chunk size, độ mới checkpoint, chi phí transaction, connection pool, RTO/RPO và throughput bằng thử nghiệm lỗi có kiểm soát.

## 1. Bài toán: node không hẹn trước lúc sẽ chết

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, một job nhập 12 triệu bản ghi được chia cho sáu worker JVM. Một worker đã xử lý gần hết partition thì máy bị reset hoặc container bị `SIGKILL`. Những record worker đã đọc và các biến trong heap biến mất ngay lập tức.

Câu hỏi không phải “làm sao gọi save checkpoint **ngay trước** khi node chết?” mà là:

> **Checkpoint nào đã được lưu bền vững trước thời điểm crash, và có đủ để tiếp tục trên một node khác không?**

Nếu lần checkpoint hợp lệ cuối cùng tương ứng chunk 120, còn worker đã bắt đầu chunk 121 nhưng chưa commit, worker mới cần đọc lại phần **chưa được xác nhận bền vững** từ checkpoint 120.

Nếu worker đã commit business output cho chunk 121 nhưng cập nhật metadata `JobRepository` không thành công, phần đó có thể được chạy lại. Vì vậy **checkpoint + transaction + idempotency** là một thiết kế thống nhất; chỉ “lưu vị trí đọc” không đủ.

~~~mermaid
flowchart LR
    A["Snapshot bất biến"] --> B["Worker A"]
    B --> C["Chunk transaction"]
    C --> D["Business output"]
    C --> E["Checkpoint bền vững trong JobRepository"]
    B -. "Node crash" .-> F["Trạng thái RAM mất"]
    E --> G["Recovery coordinator"]
    G --> H["Worker B"]
    H --> A
    H --> D
~~~

### Ba kết luận cần nhớ

1. **Không thể tin vào một callback trước crash.** Mất điện, OOM kill, kernel panic hoặc network partition có thể xảy ra mà `@PreDestroy`, shutdown hook hay `StepExecutionListener.afterStep` không chạy.
2. **Chỉ state được commit bền vững mới đáng tin cậy.** Reader count trong log hay counter trong memory không phải checkpoint.
3. **Spring Batch hỗ trợ restart thông qua metadata**, nhưng failover worker/job trên cluster không phải lúc nào cũng tự diễn ra. Cần coordinator, nhận diện owner cũ và recovery workflow phù hợp.

## 2. Thuật ngữ: checkpoint, progress, restart, failover

| Khái niệm | Định nghĩa thực hành | Không đồng nghĩa với |
| --- | --- | --- |
| **Progress in memory** | Reader đã đọc tới item nào ở JVM hiện tại | Dữ liệu đã commit hoặc checkpoint bền vững |
| **Checkpoint** | State persisted đủ để mở lại reader và tiếp tục xử lý | Bằng chứng exactly-once cho mọi side effect |
| **Chunk commit** | Giao dịch của một chunk hoàn tất theo transaction manager cấu hình | Broker reply hoặc manager đã quan sát trạng thái |
| **`StepExecutionContext`** | Map state của một `StepExecution`, gồm reader position và partition input | Shared-memory map giữa mọi worker |
| **`JobExecutionContext`** | State cấp `JobExecution`, thường được lưu ở ranh giới step | Checkpoint của từng item/chunk trong worker |
| **Restart** | Chạy tiếp một `JobInstance` đã dừng/thất bại trên metadata phù hợp | Tạo job instance mới bằng `run.id` khác |
| **Failover** | Khôi phục công việc khi node/process đang sở hữu nó không còn phục vụ | Đảm bảo tự động thành công trong mọi cấu hình |
| **Replay** | Thực hiện lại một phần công việc vì chưa chắc đã commit | Luôn là lỗi, hoặc phải tạo ra kết quả kép |
| **RTO** | Thời gian mục tiêu để khôi phục khả năng xử lý | Thời gian giữa hai checkpoint |
| **RPO** | Mức công việc/trạng thái đã xử lý có nguy cơ phải làm lại hoặc mất theo hợp đồng phục hồi | Số business record chắc chắn đã mất |

Trong ETL có input bất biến và writer idempotent, một chunk có thể bị đọc/ghi thử lại nhưng output cuối vẫn đúng. **RPO và RTO cần được định nghĩa trên kết quả nghiệp vụ**, không chỉ trên số item reader đã đi qua.

## 3. Vòng đời chunk: vị trí checkpoint thực sự xuất hiện ở đâu?

Spring Batch tổ chức xử lý chunk-oriented step theo chu kỳ đọc, xử lý, ghi và commit. Với các `ItemStream` được Step quản lý, framework dùng lifecycle `open(ExecutionContext)`, `update(ExecutionContext)` và `close()` để duy trì state phục vụ restart.

Một luồng đơn giản hóa:

~~~mermaid
sequenceDiagram
    participant R as ItemReader/ItemStream
    participant P as ItemProcessor
    participant W as ItemWriter
    participant T as Chunk Transaction
    participant J as JobRepository
    T->>R: read item(s)
    R-->>P: items
    P-->>W: transformed items
    W->>T: write chunk
    T->>R: update(ExecutionContext)
    T->>J: persist StepExecution / context
    T->>T: Commit
    Note over T,J: Atomicity tùy datasource/transaction config
~~~

Sơ đồ thể hiện **ý nghĩa logic**, không phải sequence API chính xác của mọi implementation Spring Batch. `ItemStream.update` nằm trong quy trình chuẩn bị lưu checkpoint tại chunk boundary; commit dữ liệu nghiệp vụ và metadata có thật sự nằm trong **cùng giao dịch vật lý** hay không phụ thuộc repository, datasource và transaction manager.

### Cần phân biệt hai loại context

- **`StepExecutionContext`**: trạng thái của worker step (ví dụ input range, reader index, key cuối đã commit), thường được persist tại các điểm commit chunk theo lifecycle framework.
- **`JobExecutionContext`**: state chung ở mức job execution (ví dụ snapshot manifest/version hoặc mốc điều phối). Nó thường được cập nhật giữa các step, **không nên dùng thay** checkpoint từng chunk của worker.

Không thiết kế “manager tự cập nhật `JobExecutionContext` sau mỗi message” để thay thế `StepExecutionContext` mà không có giao thức persist và concurrency rõ ràng.

### Một checkpoint đúng phải có gì?

Với reader đọc theo range:

~~~text
snapshotId: orders-snap-20261125
partitionName: partition0002
startInclusive: 4000001
endExclusive: 6000001
reader position: checkpoint do ItemStream quản lý
~~~

Phần `snapshotId` và boundaries giúp worker mới mở **đúng tập và đúng miền**, còn reader position giúp tiếp tục **bên trong miền**. Chỉ có offset mà input đã đổi thứ tự hoặc snapshot bị xóa thì checkpoint không đủ.

## 4. Bốn thời điểm crash và hệ quả

Hãy phân biệt các thời điểm so với transaction/metadata. Không nên suy luận từ log “đã xử lý item” rằng output chắc chắn đã commit.

| Điểm node mất | Business effect | Metadata checkpoint | Rủi ro và hướng phục hồi |
| --- | --- | --- | --- |
| **A. Trước khi reader hoàn thành chunk** | Thường chưa commit phần chunk này | Chỉ có checkpoint trước đó | Đọc lại từ checkpoint hợp lệ |
| **B. Sau khi gọi writer nhưng trước commit** | Có thể chưa commit; transaction rollback nếu cùng transaction DB | Không nên coi chunk đã checkpoint | Replay chunk; xác minh side effect ngoài DB |
| **C. Business DB đã commit nhưng checkpoint chưa persist** | Dữ liệu có thể đã có ở đích | Metadata còn cũ | Replay có thể xảy ra; writer phải idempotent |
| **D. Checkpoint đã commit, reply/ACK tới manager bị mất** | Output/metadata có thể đã hoàn tất | State bền vững đã có | Không suy luận timeout = chưa commit; xác minh repo và output |

Ví dụ crash loại C:

~~~mermaid
sequenceDiagram
    participant WA as Worker A
    participant B as Business DB
    participant J as JobRepository
    participant RC as Recovery
    participant WB as Worker B
    WA->>B: Ghi chunk 121
    B-->>WA: COMMIT thành công
    Note over WA,J: Node mất trước checkpoint metadata
    RC->>J: Đọc last durable checkpoint
    J-->>RC: Chunk 120
    RC->>WB: Giao lại phần chưa xác nhận
    WB->>B: Thử ghi chunk 121
    B-->>WB: UPSERT / dedup giữ business result đúng
~~~

**Lưu ý ranh giới giao dịch:** nếu metadata và dữ liệu nghiệp vụ cùng nằm trong **một transaction DB được cấu hình đúng**, khoảng hở ở C có thể được loại bỏ cho các write thuộc transaction đó. Nếu dùng hai DB, hai transaction manager, broker, HTTP API hoặc email, không được giả định atomicity xuyên các hệ thống. Luôn chứng minh bằng cấu hình thực tế và fault injection.

## 5. Kiến trúc nào đang bị failover?

Một node chết không có ý nghĩa giống nhau ở mọi mô hình scaling.

| Mô hình | State/reader ở đâu? | Khi một node chết | Điểm khôi phục cần giữ |
| --- | --- | --- | --- |
| **Single-process multi-threaded step** | Một `StepExecution`, nhiều thread có thể chia component | JVM chết làm toàn step dừng | Thread safety, checkpoint của reader dùng chung và restart |
| **Parallel steps** | Mỗi step có `StepExecution` | JVM local chết ảnh hưởng các step đang chạy | State riêng mỗi step và luồng phụ thuộc |
| **Local partitioning** | Worker `StepExecution` riêng trong cùng JVM | JVM chết làm mọi worker local ngừng | Context/checkpoint từng partition, manifest |
| **Remote partitioning** | Worker JVM tự đọc miền của mình | Một worker mất; các worker khác có thể tiếp tục | Shared JobRepository, snapshot, StepExecution ID và trạng thái ownership |
| **Remote chunking** | Manager thường sở hữu reader; worker xử lý chunk | Worker mất khi chunk đang in-flight | Manager reader checkpoint, request/reply correlation, delivery và dedup |

### Remote partitioning không có nghĩa tự động failover

Trong triển khai phổ biến dùng Spring Batch Integration, manager tạo worker `StepExecution` rồi gửi request qua middleware; worker dùng shared `JobRepository` để tra metadata và chạy step. Nếu worker chết:

- Manager có thể timeout hoặc mất reply.
- `StepExecution` có thể còn trạng thái `STARTED` trong metadata, vì process đã chết không cập nhật `FAILED`.
- Việc xác định worker nào đã chết, retry/re-dispatch hay restart job phụ thuộc **coordinator/protocol/configuration**.
- Worker mới chỉ được chạy lại khi đã giải quyết nguy cơ owner cũ vẫn đang làm việc.
- Không tự xóa metadata `BATCH_*` để “nhường việc” cho worker khác.

### Remote chunking cần nghĩ cả broker

Manager thường đọc item và gửi chunk request; worker không mặc định có reader checkpoint riêng giống partitioning. Nếu worker đã ghi chunk nhưng reply bị mất, manager có thể gặp trạng thái **không chắc chắn** và cần protocol tương quan/retry an toàn. Một message bị gửi lại có thể tạo side effect trùng nếu writer không idempotent.

## 6. Những thành phần phải bền vững ngoài JVM

~~~mermaid
flowchart TD
    A["Manager / Worker JVMs: có thể biến mất"] --> B["Shared JobRepository JDBC"]
    A --> C["Immutable input snapshot / manifest"]
    A --> D["Business DB / durable outbox"]
    A --> E["Middleware / request-reply nếu phân tán"]
    B --> R["Recovery workflow"]
    C --> R
    D --> R
    E --> R
    R --> N["Worker mới trên node khác"]
~~~

**Bất biến hạ tầng:**

1. **`JobRepository` dùng persistence bền vững, phù hợp cluster.** Không dùng in-memory repository làm nguồn sự thật cho failover đa node.
2. **Các process dùng metadata tương thích**: JDBC schema, serializer, table prefix, version framework, quyền DB, timeouts.
3. **Input tồn tại độc lập với node**: snapshot trong DB, object storage versioned hoặc manifest bền vững; không dùng đường dẫn local tạm chỉ một pod nhìn thấy.
4. **Tên partition và input range không đổi nghĩa** sau restart cùng `JobInstance`.
5. **Writer giữ business key/idempotency** xuyên các attempt và worker.
6. **Chính sách truy cập không phụ thuộc secret trong message**; worker mới dùng identity được cấp quyền tương ứng.
7. **Broker retry/DLQ/reply** được quản lý theo protocol, không giả định “queue rỗng” nghĩa mọi chunk đã commit.
8. **Backup/restore phải đồng bộ về ngữ nghĩa** giữa metadata, input snapshot và kết quả đã ghi; khôi phục repo về thời điểm cũ có thể gây replay cần đối soát.

Không lưu connection, cursor object, Spring bean, HTTP client hay token vào `ExecutionContext`. Chỉ lưu các giá trị serializable nhỏ và ổn định, cùng state do `ItemStream` quản lý.

## 7. Ví dụ PostgreSQL: snapshot và manifest để worker khác nhận lại việc

Một nguồn đang update/delete khiến cursor checkpoint không còn định danh được record cũ. Vì vậy ta dùng snapshot bất biến.

~~~sql
CREATE TABLE batch_input_snapshot (
    snapshot_id VARCHAR(100) PRIMARY KEY,
    state VARCHAR(20) NOT NULL
        CHECK (state IN ('BUILDING', 'READY', 'EXPIRED')),
    expected_count BIGINT NOT NULL CHECK (expected_count >= 0)
);

CREATE TABLE batch_input_order (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_input_snapshot(snapshot_id),
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);

CREATE TABLE batch_partition_manifest (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_input_snapshot(snapshot_id),
    partition_name VARCHAR(100) NOT NULL,
    start_inclusive BIGINT NOT NULL,
    end_exclusive BIGINT NOT NULL,
    expected_count BIGINT NOT NULL,
    PRIMARY KEY (snapshot_id, partition_name),
    CHECK (start_inclusive < end_exclusive)
);

CREATE TABLE batch_order_result (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

Bảng snapshot phải được chốt theo consistency contract: dữ liệu và partition manifest được capture, validate đầy đủ và chỉ sau đó mới có `state='READY'`. Nếu copy kéo dài qua nhiều transaction hoặc nguồn khác DB, cần staged publish/version để worker không thấy ảnh chụp thiếu dữ liệu.

### Một phân hoạch minh họa

~~~text
snapshotId = orders-snap-20261125
partition0000 = [1,       2000001)
partition0001 = [2000001, 4000001)
partition0002 = [4000001, 6000001)
partition0003 = [6000001, 8000001)
~~~

Dùng `[startInclusive,endExclusive)` để biên liền nhau không chồng lấn. **ID thưa** không phải vấn đề correctness nhưng tạo skew; `expected_count` phải được tính từ record thật, không suy bằng chiều rộng ID range.

### Đừng tự động dùng MAX(id) khi retry

Nếu node mới chạy `SELECT MAX(order_id) FROM live_order`, miền đầu vào có thể đổi. Reader checkpoint từ lần trước sẽ được diễn giải trên tập mới: có thể bỏ sót hoặc nhân đôi record. Job restart phải giữ **cùng snapshotId và manifest**, không tạo partition plan mới theo dữ liệu live.

## 8. Java 17: reader @StepScope phục hồi từ StepExecutionContext

Dùng `JdbcCursorItemReader` do Spring Batch quản lý `ItemStream`; nó lưu state phục vụ restart nếu cấu hình `saveState(true)` và được Step mở/update/đóng đúng lifecycle.

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record SnapshotOrder(
        String snapshotId,
        long orderId,
        long sourceVersion,
        String payload) {}

@Configuration
public class CheckpointReaderConfiguration {

    @Bean("snapshotOrderReader")
    @StepScope
    JdbcCursorItemReader<SnapshotOrder> snapshotOrderReader(
            DataSource inputDataSource,
            @Value("#{stepExecutionContext['snapshotId']}")
                String snapshotId,
            @Value("#{stepExecutionContext['startInclusive']}")
                Long startInclusive,
            @Value("#{stepExecutionContext['endExclusive']}")
                Long endExclusive) {

        if (snapshotId == null || snapshotId.isBlank()
                || startInclusive == null || endExclusive == null
                || startInclusive >= endExclusive) {
            throw new IllegalArgumentException(
                    "Invalid worker checkpoint / partition context");
        }

        return new JdbcCursorItemReaderBuilder<SnapshotOrder>()
                .name("snapshotOrderReader")
                .dataSource(inputDataSource)
                .sql("""
                    SELECT order_id, source_version, payload
                    FROM batch_input_order
                    WHERE snapshot_id = ?
                      AND order_id >= ?
                      AND order_id < ?
                    ORDER BY order_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotId);
                    ps.setLong(2, startInclusive);
                    ps.setLong(3, endExclusive);
                })
                .rowMapper((rs, rowNum) -> new SnapshotOrder(
                    snapshotId,
                    rs.getLong("order_id"),
                    rs.getLong("source_version"),
                    rs.getString("payload")))
                .fetchSize(500)
                .saveState(true)
                .build();
    }
}
~~~

### Vì sao ví dụ này restart được về mặt reader?

- `snapshotId` cố định nên input không đổi qua node.
- Một `StepExecution`/partition có reader riêng qua `@StepScope`.
- `ORDER BY order_id` duy nhất trong snapshot nhờ primary key `(snapshot_id,order_id)`.
- Context có ranh giới đúng miền và `ItemStream` giữ tiến độ tại các chunk boundary do framework quản lý.
- Node mới có `DataSource`, driver và quyền đọc phù hợp, không phụ thuộc cursor ở RAM của node cũ.

**Giới hạn:** `@StepScope` không biến một reader **được dùng đồng thời trong cùng StepExecution** thành thread-safe. Với multi-threaded step, cần thiết kế khác hoặc chọn partitioning để mỗi worker step có state độc lập.

### Checkpoint theo read count không phải khóa nghiệp vụ

Với input đã snapshot và thứ tự ổn định, việc khôi phục dựa trên read count có thể đúng. Nhưng nếu nguồn đổi hoặc SQL `ORDER BY` không deterministic, cùng read count sẽ chỉ vào item khác. Nếu cần keyset checkpoint để restart nhanh, phải lưu **khóa đã commit cuối**, không lưu “khóa vừa đọc cuối” trước transaction commit. Đừng tự ý bỏ `saveState` để giảm metadata IO khi hệ thống cần resume.

## 9. Writer idempotent bảo vệ khoảng hở giữa commit và checkpoint

Nếu một chunk đã ghi output nhưng checkpoint chưa persist, worker mới sẽ thử ghi lại. Với dữ liệu snapshot bất biến, kết quả cuối có thể được bảo vệ bằng unique business key.

Ví dụ PostgreSQL:

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class CheckpointWriterConfiguration {

    @Bean("orderResultWriter")
    ItemWriter<SnapshotOrder> orderResultWriter(JdbcTemplate jdbc) {
        return chunk -> {
            for (SnapshotOrder row : chunk) {
                jdbc.update("""
                    INSERT INTO batch_order_result(
                        snapshot_id, order_id, source_version, payload
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (snapshot_id, order_id) DO UPDATE
                    SET source_version = EXCLUDED.source_version,
                        payload = EXCLUDED.payload
                    WHERE (
                        batch_order_result.source_version,
                        batch_order_result.payload
                    ) IS DISTINCT FROM (
                        EXCLUDED.source_version,
                        EXCLUDED.payload
                    )
                    """,
                    row.snapshotId(), row.orderId(),
                    row.sourceVersion(), row.payload());
            }
        };
    }
}
~~~

Trong ví dụ này, **cùng một item snapshot** khi replay sẽ để lại **cùng row state**. Nhưng idempotency của một bản ghi DB không tự bảo vệ được:

- `UPDATE balance = balance + delta` nếu chạy lại.
- Email hoặc SMS được gửi hai lần.
- API thanh toán đã xử lý yêu cầu đầu tiên nhưng response bị mất.
- Event được publish hai lần ra Kafka/RabbitMQ.
- Trigger audit luôn insert một dòng mỗi lần write.

Với các trường hợp đó cần **business operation key**, unique ledger, transactional outbox/inbox hoặc endpoint hỗ trợ idempotency, và phép đối soát side effect độc lập. **Checkpoint không phải exactly-once guarantee.**

## 10. Java: manager/worker với partition cố định và pool có giới hạn

Một `Partitioner` nên lấy partition name/range từ manifest READY và tạo `ExecutionContext` nhỏ cho từng worker:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

record Range(long startInclusive, long endExclusive) {}

public final class StablePartitioner implements Partitioner {

    private final String snapshotId;
    private final Map<String, Range> manifestRanges;

    public StablePartitioner(
            String snapshotId,
            Map<String, Range> manifestRanges) {
        this.snapshotId = snapshotId;
        this.manifestRanges = Map.copyOf(manifestRanges);
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0 || snapshotId == null
                || snapshotId.isBlank() || manifestRanges.isEmpty()) {
            throw new IllegalArgumentException(
                    "Invalid immutable partition manifest");
        }

        Map<String, ExecutionContext> result =
                new LinkedHashMap<>();

        // Manifest đã được truy vấn từ bảng READY, validate trước đó.
        manifestRanges.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(e -> {
                    Range range = e.getValue();
                    if (range.startInclusive() >= range.endExclusive()) {
                        throw new IllegalArgumentException(
                                "Empty or reversed range");
                    }

                    ExecutionContext context = new ExecutionContext();
                    context.putString("snapshotId", snapshotId);
                    context.putLong("startInclusive", range.startInclusive());
                    context.putLong("endExclusive", range.endExclusive());
                    result.put(e.getKey(), context);
                });

        return result;
    }
}
~~~

Ví dụ dùng manifest **đã được tải và validate trước**; nó chưa minh họa việc kiểm tra gap/overlap hoặc biên toàn snapshot. Trong production, dữ liệu từ `batch_partition_manifest` phải có deterministic names, coverage/disjointness, không sửa sau READY và cùng identity khi restart. `gridSize` chỉ là hint về partitioning/concurrency, không được dùng để **tạo lại** mapping vào ngày failover.

Wiring local partitioning Spring Batch 5.x:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class CheckpointJobConfiguration {

    @Bean("checkpointWorker")
    Step checkpointWorker(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("snapshotOrderReader")
                JdbcCursorItemReader<SnapshotOrder> reader,
            @Qualifier("orderResultWriter")
                ItemWriter<SnapshotOrder> writer) {

        return new StepBuilder("checkpointWorker", repository)
                .<SnapshotOrder, SnapshotOrder>chunk(
                        200, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean("checkpointExecutor")
    ThreadPoolTaskExecutor checkpointExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("checkpoint-");
        executor.initialize();
        return executor;
    }

    @Bean("checkpointManager")
    Step checkpointManager(
            JobRepository repository,
            @Qualifier("checkpointWorker") Step worker,
            @Qualifier("snapshotPartitioner") Partitioner partitioner,
            @Qualifier("checkpointExecutor") TaskExecutor executor) {

        return new StepBuilder("checkpointManager", repository)
                .partitioner("checkpointWorker", partitioner)
                .step(worker)
                .gridSize(4)
                .taskExecutor(executor)
                .build();
    }

    @Bean("checkpointJob")
    Job checkpointJob(
            JobRepository repository,
            @Qualifier("checkpointManager") Step manager) {

        return new JobBuilder("checkpointJob", repository)
                .start(manager)
                .build();
    }
}
~~~

Giả định bean `snapshotPartitioner` được cung cấp bằng `StablePartitioner` với manifest đã chốt; các bean `DataSource`, `JobRepository`, `PlatformTransactionManager` và `JdbcTemplate` do ứng dụng cấu hình. `snapshotId` cần là **identifying `JobParameter`**. Ví dụ này **minh họa local partitioning**, không thay thế cấu hình handler và message protocol của remote partitioning.

Nếu các source/output/repository dùng datasource hoặc transaction manager khác nhau, phải kiểm chứng transaction boundary và writer idempotency trước production.

## 11. Node mất không tự làm JobExecution chuyển FAILED

Trong một sự cố đột ngột, tiến trình có thể chết trước khi Spring Batch ghi status cuối. `JobExecution` hoặc worker `StepExecution` trong repository có thể vẫn là `STARTED` dù thực tế không có process sống.

Các bước khôi phục an toàn:

1. **Phát hiện node thật sự mất:** từ orchestration/heartbeat, không chỉ dựa vào một request timeout.
2. **Ngăn owner cũ tiếp tục ghi:** Kubernetes pod termination, lease/lock/fencing hoặc quy trình cách ly tương ứng.
3. **Xem trạng thái `JobRepository` và business output:** không tự khẳng định mọi chunk chưa báo cáo đều chưa commit.
4. **Đưa execution vào trạng thái có thể restart bằng cơ chế vận hành/framework hỗ trợ**, không sửa bảng `BATCH_*` tùy tiện hoặc ép chạy hai lần.
5. **Khởi chạy lại cùng identifying parameters**, trỏ cùng snapshot/manifest.
6. **Đối soát sau recovery:** status thành công không thay thế so output theo business key.

Các API như `JobExplorer` và `JobOperator` hữu ích để xem/điều khiển execution theo phiên bản Spring Batch; không có lời gọi “failover tất cả worker đang chạy” chung áp dụng cho mọi Spring Batch deployment.

### Không tự đổi run.id để tránh lỗi STARTED

Tạo `run.id` mới có thể tạo **JobInstance khác** và chạy lại từ đầu, không phải restart checkpoint cũ. Nó có thể làm writer replay toàn bộ output hoặc phát lại side effect. Chỉ tạo run mới khi reprocess là quyết định nghiệp vụ có kế hoạch và đã chuẩn bị idempotency.

### Chú ý trạng thái STARTED mồ côi

Một `JobExecution` còn `STARTED` sau crash có thể ngăn việc restart theo API chuẩn cho tới khi sự cố được xác nhận và trạng thái được xử lý đúng. Khôi phục tùy hoàn cảnh phải dựa trên bằng chứng rằng process cũ đã kết thúc, quyền sở hữu không còn và có runbook được thử nghiệm. Đừng hướng dẫn DBA thay `STATUS='FAILED'` bằng SQL thủ công không xét version/lock/checkpoint.

## 12. Quá trình chuyển việc từ worker A sang worker B

Trong remote partitioning, worker B phải tái tạo được reader/processor/writer từ **dữ liệu bên ngoài node A**: metadata, immutable snapshot, manifest, dependency config và credentials runtime.

~~~mermaid
sequenceDiagram
    participant M as Manager / Orchestrator
    participant J as Shared JobRepository
    participant A as Worker A
    participant S as Immutable Snapshot
    participant D as Business DB
    participant B as Worker B
    M->>J: Tạo worker StepExecution / context
    M->>A: Dispatch partition P2
    A->>S: Đọc snapshot tại checkpoint
    A->>D: Commit chunk
    A->>J: Persist checkpoint
    Note over A,M: Node A mất kết nối hoặc crash
    M->>M: Xác minh thất bại, cô lập owner cũ
    M->>J: Kiểm tra state và restartability
    J-->>M: Durable checkpoint cuối
    M->>B: Redispatch/restart bằng protocol hợp lệ
    B->>S: Mở lại cùng snapshot/range
    B->>D: Replay an toàn bằng business key
    B->>J: Persist tiến độ mới
    B-->>M: Báo kết quả
~~~

Sơ đồ mô tả **quy trình recovery cấp hệ thống**, không phải bảo đảm mọi `PartitionHandler` mặc định tự thực hiện tất cả bước.

Trước khi giao lại việc, cần chứng minh:

1. Worker A đã dừng thật hoặc bị **fencing** ngăn ghi output cũ.
2. `JobInstance`, identifying `JobParameters`, `snapshotId` và partition range không thay đổi.
3. `JobRepository` giữ metadata/checkpoint đọc được từ node khác.
4. Worker B có framework/serializer/schema tương thích và quyền truy cập nguồn/đích.
5. Writer có idempotency khi business output đã commit nhưng reply hoặc metadata chưa đến.
6. Pending request/reply và DLQ được xử lý theo một giao thức rõ, không xóa mù.

Nếu thiếu điều kiện (1), manager có thể giao lại cùng partition cho hai node cùng chạy. Nếu thiếu (2) hoặc (3), checkpoint cũ có thể được diễn giải trên dữ liệu khác.

## 13. Remote partitioning: checkpoint thuộc worker StepExecution

Trong remote partitioning, manager chỉ điều phối partition; worker sở hữu reader/processor/writer cho miền của nó. Mỗi worker `StepExecution` lưu context riêng.

~~~text
JobInstance: import-orders(snapshotId=orders-snap-20261125)

workerStep:partition0000
  status: COMPLETED
  context: snapshotId, range và reader checkpoint

workerStep:partition0001
  status: FAILED / STARTED mồ côi
  context: snapshotId, range và last durable reader checkpoint

workerStep:partition0002
  status: COMPLETED
  context: snapshotId, range và reader checkpoint
~~~

**Không tự tính `MAX(order_id)` hoặc chốt snapshot mới trên worker B.** Khi restart, `partition0001` phải vẫn có đúng cùng miền với attempt trước. Nếu thay `gridSize` và tạo partition mapping mới dưới **cùng tên**, state reader có thể trỏ nhầm vị trí hoặc chồng lấn với partition khác.

### Số partition khác số pod

Một manifest 64 partition có thể được xử lý bởi 4, 8 hoặc 16 worker JVM tùy scheduler/handler. Thay đổi **concurrency** không buộc thay đổi 64 partition names/ranges của một `JobInstance` đang cần restart.

### Khi manager chết thay vì worker

Worker có thể vẫn tiếp tục và commit dù manager không còn kết nối. Reply có thể thất lạc hoặc nằm trong broker tới khi manager khởi động lại. Manager mới cần đọc trạng thái thực từ repository, broker và output; **không coi mọi partition chưa có reply là chưa chạy**.

## 14. Remote chunking: reader checkpoint nằm phía manager

Trong remote chunking, manager thường sở hữu `ItemReader` và gửi chunk item qua middleware; worker thực hiện processor/writer. Không được tìm “reader offset của chunk” trong `StepExecutionContext` của một worker remote nếu giao thức thực tế không thiết kế nó ở đó.

| Thành phần | Thường ở đâu? | Hệ quả khi node mất |
| --- | --- | --- |
| Reader position | Manager step + `ItemStream` | Manager restart phải khôi phục input |
| Chunk request | Broker/in-flight request channel | Có thể redeliver sau timeout |
| Business write | Worker-side DB/API | Có thể commit trước reply |
| Reply correlation | Message protocol + manager | Cần ghép đúng request, kể cả duplicate/out-of-order |
| Dedup guard | Business key/ledger/outbox | Ngăn replay tạo effect lặp |

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Broker
    participant A as Worker A
    participant D as Business DB
    participant B as Worker B
    M->>Q: Chunk request K
    Q->>A: Deliver K
    A->>D: Commit effect K
    Note over A,M: Reply / ACK bị mất
    Q->>B: Redelivery K
    B->>D: Thử ghi lại K
    D-->>B: UPSERT/dedup giữ business output đúng
    B-->>M: Reply K
~~~

`messageId` hoặc UUID của mỗi lần publish **không phải** business key đủ mạnh: sau restart, cùng record có thể nằm ở chunk được chia lại. Writer phải chống duplicate theo **business record/operation ổn định**, không chỉ theo `chunkId` có thể thay đổi.

Những message cũ có thể nằm trong ready queue, unacked, delayed retry, DLQ hoặc reply channel; không xóa để “dọn” khi chưa biết chúng có thể đã commit side effect hay chưa.

## 15. Graceful shutdown hữu ích, nhưng không bảo đảm checkpoint

Khi deploy/scale-down, nền tảng thường có thể gửi `SIGTERM` cho process. Nếu đủ thời gian, worker nên dừng nhận việc mới và kết thúc chunk đang chạy hoặc dừng có trật tự.

Một quy trình drain:

1. Đánh dấu worker **draining** để coordinator không gửi partition/chunk mới.
2. Dừng nhận business work mới khi sát deadline shutdown.
3. Hoàn tất/rollback chunk đang chạy theo transaction semantics.
4. Cho `ItemStream.update`/`JobRepository` persist checkpoint theo lifecycle khi còn điều kiện.
5. Đóng reader, writer, database connections và consumer.
6. Đối chiếu in-flight requests/replies, sau đó mới chuyển ownership.

**Không được chỉ checkpoint khi shutdown:** `SIGKILL`, OOM, mất điện, kernel panic hoặc network partition không đảm bảo callback `@PreDestroy`, shutdown hook hay `afterStep` được gọi.

### Kubernetes

`terminationGracePeriodSeconds` tạo cơ hội dừng có kiểm soát; khi hết hạn, container có thể bị kill. `preStop`/readiness giúp drain nhưng không bảo đảm tiến trình sẽ kịp commit chunk cuối.

Pod/Job restart policy tự tạo container mới **không tự động giải quyết** `JobExecution` còn `STARTED` hoặc tránh chạy song song với node cũ. Phải giữ identifying parameters, shared repository và ownership workflow.

## 16. Fencing: ngăn node cũ ghi sau khi mất quyền sở hữu

Tình huống nguy hiểm nhất không phải node chết hẳn mà là **network partition**: manager tưởng worker A mất, nhưng A vẫn kết nối được business DB. Manager giao cùng partition cho B, hai worker có thể ghi đồng thời.

~~~mermaid
flowchart TD
    M["Coordinator"] --> L["Lease / ownership store"]
    L --> A["Worker A epoch 12"]
    A -. "Mất kết nối manager" .-> M
    M --> B["Worker B epoch 13"]
    A --> D["Business DB"]
    B --> D
    D --> F{"Output có kiểm tra epoch?"}
    F -->|"Có"| OK["Từ chối owner cũ"]
    F -->|"Không"| BAD["Nguy cơ double side effect"]
~~~

**Lease timeout đơn thuần không đủ.** Một worker có lease đã hết vẫn có thể tiếp tục ghi nếu bên đích không kiểm tra quyền sở hữu.

Ví dụ bảng PostgreSQL cho ownership epoch:

~~~sql
CREATE TABLE batch_partition_owner (
    snapshot_id VARCHAR(100) NOT NULL,
    partition_name VARCHAR(100) NOT NULL,
    owner_id VARCHAR(200) NOT NULL,
    epoch BIGINT NOT NULL CHECK (epoch > 0),
    lease_until TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (snapshot_id, partition_name)
);
~~~

Một coordinator có thể dùng thao tác có điều kiện để cấp epoch mới:

~~~sql
INSERT INTO batch_partition_owner(
    snapshot_id, partition_name, owner_id, epoch, lease_until
)
VALUES (
    :snapshotId, :partitionName, :newOwner,
    1, CURRENT_TIMESTAMP + INTERVAL '60 seconds'
)
ON CONFLICT (snapshot_id, partition_name) DO UPDATE
SET owner_id = EXCLUDED.owner_id,
    epoch = batch_partition_owner.epoch + 1,
    lease_until = EXCLUDED.lease_until
WHERE batch_partition_owner.lease_until < CURRENT_TIMESTAMP
RETURNING epoch;
~~~

Câu SQL chỉ là ví dụ về **ownership record do ứng dụng tự thiết kế**, không phải API tự động của Spring Batch. Nếu lease hiện tại còn hiệu lực, thao tác có thể trả **0 hàng**. Production còn cần renew lease, monotonic epoch, xác minh coordinator và quản lý trạng thái theo transaction.

**Fencing thật phải được enforce ở bên đích.** Với PostgreSQL, một cách là kiểm tra epoch bằng khóa row `FOR UPDATE` và thực hiện business write trong **cùng DB transaction**, bảo đảm không có khoảng TOCTOU giữa check và write. Với HTTP API/broker/DB khác, cần destination-side fencing/idempotency, hoặc cô lập owner cũ. Chỉ xem giá trị epoch ở đầu method rồi ghi sau bằng transaction khác **không đủ**.

`JobRepository` không phải distributed lease/fencing service tổng quát cho mọi business side effect. Nếu chưa có fencing đáng tin cậy, hãy chờ xác minh worker cũ đã dừng trước khi takeover.

## 17. Chu kỳ checkpoint, chunk size, RTO và RPO

Checkpoint quá dày làm tăng transaction/metadata overhead; checkpoint quá thưa làm tăng work cần replay khi crash.

Giả sử worker xử lý trung bình **8.000 item/giây** và chunk size **200 item**:

~~~text
Idealized chunks/second = 8.000 / 200 = 40
Idealized compute time/chunk = 200 / 8.000 = 0,025 giây
~~~

Đây **không phải benchmark**. Thực tế có DB commit latency, JDBC/metadata IO, transaction lock, broker delay, retry và GC. Khi business DB và repository cùng transaction vật lý đã được kiểm chứng, phần chưa commit thường có thể replay tại chunk boundary. Nếu có hai transaction manager hoặc message in-flight, **không được tuyên bố số item có thể replay luôn ≤ chunk size**.

| Chọn lựa | Lợi thế | Chi phí/rủi ro |
| --- | --- | --- |
| Chunk nhỏ | Checkpoint thường xuyên, rollback ít item | Nhiều commit, repository IO và lock |
| Chunk lớn | Giảm số transaction | Replay/rollback nhiều, memory và thời gian commit tăng |
| Checkpoint sau từng item | Có thể giảm work không commit trong một số mô hình | Overhead rất cao, không tạo exactly-once cho external API |
| Chỉ checkpoint khi shutdown | Ít write | Không chống crash bất ngờ |
| Partition nhỏ và nhiều | Dễ chia tải, giảm thời gian một partition | Metadata/dispatch overhead và connection pressure |
| Snapshot bất biến | Restart chính xác cùng input | Tốn storage/retention và thời gian capture |

### Phân rã RTO

~~~text
RTO ≈ thời gian phát hiện node mất
    + thời gian xác minh/cô lập owner cũ
    + thời gian đưa execution vào trạng thái restartable
    + thời gian khởi động worker mới và mở reader
    + thời gian replay phần chưa chắc chắn
    + thời gian đối soát để tiếp tục an toàn
~~~

`JobLauncher.run()` khởi động nhanh không có nghĩa failover nhanh nếu việc cách ly owner cũ hoặc phục hồi `STARTED` mất nhiều thời gian.

### RPO theo nghĩa nghiệp vụ

Trong một hệ ETL transactional với input bất biến, replay lại record không đồng nghĩa mất output đã commit. Nhưng một external payment API hoặc email không transactional có thể đã thực hiện effect mà metadata chưa biết. Định nghĩa RPO bằng **số business operation cần đối soát/replay, dữ liệu có nguy cơ thiếu hoặc độ trễ hoàn tất**, không chỉ bằng số item reader đã đọc.

## 18. Giới hạn tài nguyên khi failover

Mỗi worker có thể dùng reader cursor connection, business writer connection, repository connection và broker connection. Số kết nối thực tế phụ thuộc transaction manager và cách cấu hình, **không nên giả định mỗi worker chỉ chiếm một JDBC connection**.

Ví dụ cluster có 6 worker gần chạm quota 60 DB connections; nếu coordinator khởi động 18 worker mới cùng lúc sau một node timeout, tăng concurrency có thể làm recovery **chậm hơn** vì connection wait, deadlock và retry storm.

Những thứ cần đo:

- Active/pending JDBC connections, acquisition wait, max pool size tổng across JVM.
- Business DB lock wait, deadlock, commit latency, WAL/IO và slow queries.
- `JobRepository` metadata update latency và serialization/DB throughput.
- Reader reopen/skip time, cursor fetch size, input snapshot IO.
- Broker ready/unacked/retry/DLQ và oldest message age.
- Worker CPU/heap/GC, thread pool active/queue/rejected.
- Output business keys committed unique/s, không đếm retry thành công mới.

Trong giờ recovery, ưu tiên **bounded concurrency** và đảm bảo snapshot/DB vẫn phục vụ ổn định. Đừng dùng autoscaling chỉ theo queue depth mà không xét connection budget và recovery load.

## 19. Quan sát last durable checkpoint

Một số metric gợi ý (không mặc định có sẵn trong mọi Spring Batch setup):

| Chỉ số | Ý nghĩa |
| --- | --- |
| `last_chunk_commit_at` | Thời điểm gần nhất có commit được xác nhận |
| `checkpoint_age_seconds` | Checkpoint đã đứng yên bao lâu |
| `step_read_count`, `step_write_count`, `step_commit_count` | Tiến độ theo `StepExecution` |
| `step_rollback_count` / retry count | Mức xử lý lại và thất bại |
| Worker heartbeat/last seen | Dấu hiệu worker mất, không tự chứng minh đã chết |
| Lease expiry và fencing epoch | Nhận diện takeover/stale worker |
| `jobrepository_write_latency_seconds` | Metadata IO bottleneck |
| `worker_reader_reopen_seconds` | Chi phí resume reader |
| `job_failover_duration_seconds` | RTO thực tế từ failure đến xử lý hữu ích |
| `output_missing_key_total` | Business keys bắt buộc nhưng thiếu |
| `output_duplicate_effect_total` | Trùng side effect theo ledger |
| `snapshot_version_mismatch_total` | Đọc sai phiên bản input |

Cảnh báo khi step vẫn `STARTED` nhưng không có checkpoint tiến thêm và heartbeat đã mất, khi pending retries tăng nhanh, khi metadata update chậm hoặc khi hai worker báo cùng partition với epoch khác nhau.

Không log toàn bộ `ExecutionContext` hoặc payload nhạy cảm. Log tối thiểu: job/step execution ID, partition name, commitCount, checkpoint freshness, owner epoch và mã lỗi đã được phân loại.

## 20. Kiểm thử failure injection trước production

Hãy thực sự **kill** process/worker trên môi trường staging với snapshot bất biến và cấu hình repository/broker đại diện cho production.

| Failure window | Cách mô phỏng | Kỳ vọng |
| --- | --- | --- |
| Trước khi đọc chunk | Kill worker trước reader | Resume từ checkpoint cũ |
| Sau khi đọc vài item | Kill giữa chunk | Không coi chunk đã commit |
| Sau processor, trước writer | Kill ở thời điểm tạm dừng | Không có output chunk mới ngoài transaction |
| Sau writer trước commit | Throw exception/rollback | Replay đúng khi mở lại |
| Business DB commit trước metadata | Inject lỗi ở đường metadata khi dùng hai DB | Replay không làm duplicate effect |
| Metadata commit trước reply | Drop reply/ACK | Manager không đoán nhầm timeout thành failure |
| Manager mất, worker còn chạy | Kill manager container | Không tạo hai owner và không mất state |
| Worker network partition | Chặn control plane, còn đường DB | Fencing ngăn stale writer |
| Graceful SIGTERM | Scale-down có thời gian drain | Chunk đang xử lý kết thúc/rollback đúng |
| SIGKILL/OOM kill | Kill bất ngờ | Recovery không phụ thuộc shutdown hook |
| Snapshot bị xóa/quên version | Cố tình tắt nguồn snapshot | Fail rõ, không fallback sang live source |
| Serializers khác phiên bản | Rolling deploy | Read lại context cũ hoặc migration rõ |
| Thay gridSize/worker slots | Restart execution | Partition mapping không đổi |
| Broker replay request cũ | Duplicate message | Writer idempotent và correlation đúng |
| JobRepository tạm ngừng | Inject DB outage | Không đánh dấu checkpoint thành công sai |
| Business DB tạm ngừng | Inject writer error | Transaction, retry và checkpoint đúng |
| Nhiều worker lúc DB đầy pool | Load recovery | Không tạo retry storm/outage dây chuyền |
| Reconciliation sau failover | So snapshot/output/side effects | Không thiếu, không thừa, đúng version |

### Kịch bản vàng

1. Tạo một snapshot cố định và chạy bốn partition với chunk size 200.
2. Cho một partition `COMPLETED`, một partition `FAILED`, một partition crash giữa chunk.
3. Giả lập worker commit business DB thành công nhưng manager mất reply/metadata chưa cập nhật, ở kiến trúc có cửa sổ như vậy.
4. Xác nhận worker cũ đã bị cô lập hoặc fenced.
5. Recovery cùng identifying `JobParameters`, không đổi snapshot/partition.
6. Kiểm tra reader reopen, metadata checkpoint, số record thực đã commit.
7. Đối soát business output và các side effect ngoài DB.
8. Đo RTO/RPO và lặp lại với rolling worker version khác nhau.

**PASS** chỉ khi metadata, business result, owner và thời gian khôi phục đạt yêu cầu; trạng thái `COMPLETED` đơn lẻ không đủ.

## 21. Runbook khi node biến mất trong production

1. **Khoanh vùng** `JobInstance`, `JobExecution`, worker `StepExecution`, partition, thời điểm mất node và phiên bản.
2. **Tạm ngừng dispatch** nếu có nguy cơ duplicate owner; không tiếp tục giao thêm việc mù theo timeout.
3. **Xác minh failure type**: process chết, SIGTERM, OOM, network partition hay mất broker.
4. **Cô lập owner cũ/fencing** trước khi cho replacement worker ghi cùng business key.
5. **Đọc JobRepository**: trạng thái `STARTED`/`FAILED`/`COMPLETED`, last checkpoint, `commitCount`.
6. **Đối chiếu business DB và broker**: chunk đã commit, chưa commit, reply chưa đến, retry/DLQ pending.
7. **Kiểm tra snapshot/manifest**: READY, version và boundaries bất biến, retention chưa hết.
8. **Kiểm tra worker mới**: repository/serializer/schema/ACL/secret/version và connection budget.
9. **Xử lý orphaned execution theo runbook/framework hỗ trợ**, không chỉnh trực tiếp bảng `BATCH_*` để ép restart.
10. **Restart cùng JobInstance** khi trạng thái đã hợp lệ và mục đích là tiếp tục checkpoint cũ.
11. **Giám sát replay** và business-key dedup, không tự hiểu mọi unique conflict là lỗi.
12. **Đối soát** missing/extra/version mismatch, cùng side effect độc lập với metadata status.
13. **Tổng kết RTO/RPO** và tìm bottleneck trong detect/fence/restart/replay.
14. **Tạo regression test** với chính failure window đã gặp.

Tránh các thao tác nguy hiểm: xóa `BATCH_STEP_EXECUTION_CONTEXT`, đổi `run.id` chỉ để né execution đang `STARTED`, sửa snapshot đang có checkpoint, xóa queue chưa đối soát hoặc tăng số worker vượt capacity.

## 22. Bài tập tình huống: mất node sau chunk 120

Một job remote partitioning xử lý sáu triệu order từ snapshot đã chốt:

~~~text
snapshotId: orders-snap-20261125

partition0000: [1,2000001)       COMPLETED
partition0001: [2000001,4000001) STARTED
partition0002: [4000001,6000001) STARTED

partition0001:
  chunkSize = 200
  last durable checkpoint = sau chunk 120
  worker A đang xử lý chunk 121
  business DB có thể đã commit chunk 121
  reply/ACK chưa đến manager

Sự cố: worker A bị network partition.
Coordinator định đưa worker B vào thay thế.
Worker A vẫn có thể kết nối business DB.
~~~

**Câu hỏi:**

1. Worker B nên lấy điểm resume từ RAM/log của A hay metadata nào?
2. Manager không nhận reply có chứng minh chunk 121 chưa commit không?
3. Vì sao `@PreDestroy` không đủ để tạo checkpoint ở tình huống này?
4. Writer `UPSERT` theo `(snapshotId,orderId)` bảo vệ được gì và còn rủi ro side effect nào?
5. Lease timeout có tự chặn A ghi khi B được giao việc không?
6. Nếu manifest `partition0001` đổi thành `[2500001,4500001)` lúc restart, hậu quả gì?
7. Nếu `JobRepository` và business DB dùng transaction manager khác nhau, có thể coi checkpoint atomic với business commit không?
8. DB pool đang gần cạn; tăng từ 6 lên 18 worker khi failover có chắc giảm RTO không?
9. Muốn xác nhận hệ thống đã phục hồi đúng, cần đối soát những gì?
10. Nếu tạo identifying `run.id` mới để tránh lỗi execution còn STARTED, đó có phải restart checkpoint không?

### Gợi ý đáp án

- **(1)** Last durable `StepExecutionContext`/`JobRepository`, cùng snapshot và partition.
- **(2)** Không. Có thể commit thành công và mất reply; kiểm tra DB/metadata.
- **(3)** Network partition/SIGKILL không bảo đảm callback xảy ra.
- **(4)** Bảo vệ final row state, nhưng không tự chống duplicate email/API/event hoặc trigger audit.
- **(5)** Không. Cần xác nhận A dừng hoặc fencing token được business destination enforce.
- **(6)** Reader checkpoint thuộc miền cũ, có thể bỏ sót/chồng lên partition khác.
- **(7)** Không mặc định; phải chứng minh transaction boundary và có idempotency.
- **(8)** Không; connection/lock/retry storm có thể làm recovery chậm hơn.
- **(9)** Business keys đủ, không output thừa, đúng version/payload, side effects đúng, ownership hợp lệ.
- **(10)** Không; đó là JobInstance mới/reprocess, cần kế hoạch chống replay trùng.

## Checklist trước production

- [ ] `JobRepository`, immutable snapshot và manifest bền vững ngoài node, có backup/retention.
- [ ] Identifying `JobParameters`, partition names và boundaries giữ nguyên khi restart.
- [ ] Reader quản lý `ItemStream` state, `saveState` bật khi cần, `@StepScope` bind đúng context.
- [ ] Writer replay-safe theo business key; external side effects có ledger/outbox hoặc idempotency key.
- [ ] Transaction boundary giữa business DB và metadata đã được xác minh; không khẳng định atomic xuyên hệ thống.
- [ ] Có cách phân biệt node chết với network partition/timeout.
- [ ] Ownership, lease/fencing hoặc quy trình cách ly được áp dụng trước takeover.
- [ ] Worker mới đọc được snapshot version, repository schema và serialized context từ phiên bản trước.
- [ ] Graceful shutdown có drain nhưng không là nơi lưu checkpoint duy nhất.
- [ ] Có policy cho retry/DLQ/reply, không xóa outstanding work chưa đối soát.
- [ ] Chunk size và số worker được benchmark với throughput/metadata IO và replay exposure.
- [ ] Đã thử kill trước/sau commit, mất reply, manager crash, fencing và rolling deployment.
- [ ] Có metric checkpoint age, recovery RTO/RPO, DB pool, JobRepository và reconciliation.
- [ ] Có runbook đưa orphaned execution về trạng thái restartable bằng cơ chế hợp lệ.
- [ ] Chỉ publish business output khi validation/reconciliation đạt yêu cầu.

## Tài liệu tham khảo

- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `StepExecution` và `ExecutionContext`.
- [Spring Batch Reference – ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open/update/close` và checkpoint.
- [Spring Batch Reference – Job Restart](https://docs.spring.io/spring-batch/reference/job.html): restartability và identifying JobParameters.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step và partitioning.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote partitioning/chunking.
- [Spring Batch Reference – Configuring JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): JDBC metadata/transaction.
- [Spring Batch Reference – Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope` và context binding.
- [Spring Batch 5.2 Reference](https://docs.spring.io/spring-batch/reference/5.2/index.html): API và cấu hình của dòng 5.x.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): boundaries và propagation.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): consistency và commit.
- [PostgreSQL – INSERT/ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): upsert/idempotency.
- [Kubernetes – Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination): grace period và tín hiệu shutdown.

## Ghi nhớ

**Checkpoint trước khi mất node không phải hành động xảy ra vào giây cuối mà là trạng thái bền vững được lưu định kỳ trong khi job chạy.** Spring Batch dùng `ExecutionContext`, `ItemStream` và `JobRepository` để restart, nhưng failover đúng còn cần **cùng snapshot/partition, owner cũ được cô lập, worker mới đọc state tương thích, writer idempotent và đối soát business output**. Graceful shutdown giúp giảm công việc phải làm lại nhưng không cứu được crash đột ngột. Không đồng nhất timeout, `STARTED` mồ côi hoặc counter trong log với commit bền vững. Khi mở rộng nhiều JVM, phải **đo RTO/RPO và kiểm thử crash quanh transaction thật** để worker thay thế tiếp tục đúng việc, chứ không chỉ khởi động thành công.
