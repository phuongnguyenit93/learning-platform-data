# Test remote partitioning trong Spring Batch

## 1. Một job báo COMPLETED nhưng dữ liệu vẫn thiếu: kiểm thử đã bỏ sót điều gì?

Một batch job nhập 2 triệu giao dịch được chia thành 16 partition. Manager gửi request qua broker tới bốn worker, mỗi worker xử lý nhiều partition. Trong kiểm thử tuần tự, tất cả đều thành công. Nhưng production xảy ra tình huống: worker A đã commit một chunk rồi mất kết nối; broker gửi lại request, worker B nhận trong khi A chưa dừng hẳn. Cuối cùng manager báo `COMPLETED`, `writeCount` trông hợp lý, nhưng báo cáo chứa một giao dịch được cộng hai lần và một giao dịch khác bị bỏ qua.

Điểm mấu chốt: **remote partitioning không chỉ là chạy nhiều thread**. Đây là một giao thức giữa **manager, broker/transport, worker, shared `JobRepository` và business data store**, gồm những ranh giới lỗi độc lập. Kiểm thử đúng phải xác nhận **cả tiến độ điều phối lẫn tính đúng của dữ liệu**, bao gồm duplicate, out-of-order, timeout, restart và crash giữa các mốc commit/ACK.

Bài **“Test remote partitioning”** thuộc chương **Testing concurrency** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module học cách mở rộng Spring Batch cho workload lớn qua multi-threaded step, parallel steps, partitioning và mô hình phân tán, đi kèm đo bottleneck, thread safety, retry/restart và vận hành theo tài nguyên thực tế.

Sau bài này, bạn có thể:

1. Phân biệt unit test `Partitioner`, test worker step, integration test broker/metadata và end-to-end test nhiều process.
2. Tạo fixture **deterministic** để kiểm tra các partition phủ đủ dữ liệu, không chồng lấn và có checkpoint restart ổn định.
3. Kiểm tra manager nhận kết quả từ **đúng `StepExecution`**, thay vì chỉ đếm message reply.
4. Giả lập worker crash, mất ACK/reply, redelivery, request trễ, worker chậm, manager/broker/DB outage.
5. Thiết kế writer idempotent, phát hiện duplicate khác payload và đối soát business keys sau restart.
6. Dùng barrier/latch, fault injection, trace và Testcontainers để tạo race có khả năng tái hiện.
7. Phân biệt lỗi nghiệp vụ với deadlock, pool starvation, network partition và việc manager tưởng worker đã dừng.
8. Lập test matrix, quality gate và runbook cho remote partitioning trước production.

**Phạm vi ví dụ:** Java 17+, Spring Batch 5.2.x, Spring Integration messaging, JUnit 5, AssertJ, Spring Batch Test, Testcontainers, PostgreSQL và một broker hỗ trợ request/reply phù hợp. Các ví dụ đánh dấu rõ **code có thể dùng làm thành phần** và **pseudocode topology**; API integration/serialization tùy Spring Batch 5.x/6.x và Spring Integration version cần xác minh ở dự án. Không coi ví dụ là một hệ thống production có thể chạy chỉ nhờ copy một class.

## 2. Remote partitioning thực sự trao đổi những gì?

Trong remote partitioning, manager tạo nhiều **worker `StepExecution`** với mỗi `ExecutionContext` riêng; request tới worker tham chiếu execution tương ứng. Worker **tải execution đã tồn tại từ shared metadata repository**, chạy worker step rồi ghi trạng thái/metrics về `JobRepository`. Manager cần chờ và tổng hợp trạng thái worker executions bằng cơ chế reply hoặc theo dõi repository phù hợp với cấu hình/phiên bản.

~~~mermaid
sequenceDiagram
    participant M as Manager / partition step
    participant J as Shared JobRepository
    participant Q as Broker request/reply
    participant W as Remote worker
    participant D as Business database
    M->>J: Tạo JobExecution + partition StepExecutions
    M->>Q: Dispatch StepExecution requests
    Q->>W: Delivery request
    W->>J: Load StepExecution + ExecutionContext
    W->>D: Read / process / write / chunk commit
    W->>J: Ghi StepExecution status + checkpoint
    W-->>Q: Reply / completion message (nếu topology dùng)
    Q-->>M: Reply hoặc manager theo dõi state
    M->>J: Tổng hợp worker executions
    M-->>J: Manager step/job final status
~~~

**Các ranh giới cần phân biệt:**

| Khái niệm | Nó cho biết | Nó **không** cho biết |
|---|---|---|
| Request đã publish | Manager gửi được một message đến transport theo acknowledgment của nó | Worker đã bắt đầu, xử lý đúng hay commit |
| Broker ACK | Message đã được xử lý theo contract/ACK mode của broker | Business DB và `JobRepository` cùng commit nguyên tử |
| Reply đã nhận | Manager có tín hiệu từ worker/transport | Reply không thể trễ, trùng hoặc thuộc attempt cũ |
| `StepExecution.BATCH_STATUS=COMPLETED` | Metadata ghi nhận worker step hoàn tất | Side effects ngoài DB/broker đều exactly-once |
| `ExitStatus` | Exit code dùng cho flow/transitions | Luôn giống `BatchStatus` hoặc được tổng hợp đúng chỉ bằng số reply |
| Job `COMPLETED` | Luồng điều phối báo hoàn tất theo cấu hình | Tập business keys chính xác khi writer không idempotent |
| Business output đã đối soát | Dữ liệu thỏa invariant được kiểm tra | Mọi sự cố hạ tầng sau đó đều không thể xảy ra |

### 2.1. Phân biệt ba mô hình thường bị nhầm

| Mô hình | Ai đọc item? | Đơn vị giao cho worker | Test trọng tâm |
|---|---|---|---|
| **Remote partitioning** | Worker reader theo `ExecutionContext` riêng | Worker `StepExecution` / partition | Ranh giới partition, shared repository, restart và dispatch |
| **Remote chunking** | Manager đọc, worker xử lý/ghi chunk | Item chunk/message | Đúng payload/chunk, ACK/replay, manager reader checkpoint |
| **Remote step (Spring Batch 6.x)** | Một logical step chạy trên worker từ xa | Step execution từ xa, không tự chia N partitions | Placement, shared metadata, execution lifecycle |

Đừng dùng một test remote chunking để kết luận remote partitioning đã đúng: hai mô hình có **vị trí reader, checkpoint và ownership state khác nhau**.

### 2.2. Những câu hỏi phải trả lời trước khi viết test

- Manager và worker có trỏ về **cùng `JobRepository`**, cùng schema và cấu trúc bảng metadata không?
- Request mang **tham chiếu định danh execution** nào (jobExecutionId, stepExecutionId, stepName) theo transport/version?
- Partition names và `ExecutionContext` keys có cố định để restart không?
- Worker được xử lý tối đa bao nhiêu execution đồng thời? Broker prefetch/consumer concurrency và pool budget?
- Manager nhận reply bắt buộc hay có chiến lược theo dõi shared repository? Timeout/aggregation xử lý thế nào?
- Message retry, ACK, dead-letter và duplicate detection do **thành phần nào** chịu trách nhiệm?
- Có trường hợp worker A còn sống khi worker B được phát lại cùng request không?
- Business write có idempotent **theo event/business key** không, kể cả khi metadata/broker không cùng transaction?

Không nên lập test dựa trên giả định “broker bảo đảm exactly-once” khi chưa có bằng chứng end-to-end về database commit, metadata state, ACK và replay.

## 3. Chọn test oracle: cần kiểm chứng trạng thái nào và dữ liệu nào?

**Test oracle** là tập điều kiện quyết định một lần chạy đúng hay sai. Một remote partitioning test cần ít nhất ba lớp:

### 3.1. Điều phối (control plane)

- `JobExecution` kết thúc với `BatchStatus`/`ExitStatus` phù hợp.
- Manager step biết **đúng tập worker partitions** đã được tạo.
- Mỗi worker `StepExecution` có trạng thái phù hợp: thành công, fail, stopped hoặc retry/restart.
- Không gộp kết quả trùng của một execution rồi coi như hai partition đã hoàn tất.
- Một reply trễ từ execution đã lỗi/attempt cũ **không** được đổi trạng thái của execution mới.
- Không để partition `STARTED` mãi khi worker mất, trừ khi đó là state chờ recovery đã được giám sát rõ.

### 3.2. Dữ liệu (data plane)

- Tập input xác định từ một snapshot bất biến.
- Các partition **không bỏ sót và không overlap ngoài kế hoạch**.
- Mỗi business key hợp lệ xuất hiện đúng một lần trong kết quả logic, hoặc có chính sách update/aggregate được xác định.
- Nội dung/amount/checksum của output khớp input được chấp nhận.
- Duplicate delivery hoặc restart **không tạo thêm tác động nghiệp vụ**.
- Nếu có skip/filter, expected set phải phản ánh **chính sách đã phê duyệt**, không âm thầm nới invariant để test xanh.

### 3.3. Hạ tầng và khả năng phục hồi

- Crash, timeout, DB outage và broker redelivery không dẫn đến job “thành công giả”.
- Connection pool, transaction, lock và consumer concurrency nằm trong ngân sách đã định.
- Retry có giới hạn, có backoff/quan sát; lỗi không được retry vô hạn.
- Worker cũ không thể tạo side effects không kiểm soát khi request đã bị giao lại.
- Restart dùng đúng `JobInstance` và dữ liệu/checkpoint cố định.

### Quy tắc vàng: không chỉ kiểm tra `readCount == writeCount`

Giả sử expected IDs là `{1,2,3,4}`, output ghi `{1,2,2,4}`. Tổng số row vẫn là 4, nhưng thiếu ID 3 và trùng ID 2. Đối với writer có unique key, duplicate có thể bị `DO NOTHING`; khi ấy `writeCount` vẫn khác số **new committed rows**. Vì vậy, **so tập khóa nghiệp vụ, count, checksum/amount và trạng thái metadata**, không chỉ một counter.

## 4. Fixture PostgreSQL deterministic cho test nhiều worker

Một fixture tốt phải biết chính xác expected output trước khi test chạy và giữ nguyên dữ liệu qua các lượt retry.

### 4.1. Schema input, output và business key

~~~sql
CREATE TABLE source_events (
    snapshot_key VARCHAR(80) NOT NULL,
    event_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    PRIMARY KEY (snapshot_key, event_id)
);

CREATE TABLE processed_events (
    snapshot_key VARCHAR(80) NOT NULL,
    event_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_key, event_id)
);
~~~

Fixture 1.003 events, các ID từ 1 đến 1003:

~~~sql
INSERT INTO source_events
    (snapshot_key, event_id, customer_id, amount_cents)
SELECT
    'snap-test-001',
    n,
    MOD(n, 17),
    n * 10
FROM generate_series(1, 1003) AS g(n);
~~~

Với cùng snapshot, expected business output là **1.003 event IDs** và `SUM(amount_cents) = 5.035.060`. Nhưng **tổng tiền và số row vẫn chưa chứng minh tập khóa khớp**; phải so từng key hoặc dùng `EXCEPT`.

Để test lập lại, dùng **PostgreSQL container/schema dành riêng cho từng test suite**, không chạy `TRUNCATE` trên shared DB của môi trường khác. Metadata `BATCH_*` cũng phải được khởi tạo từ schema phù hợp với **Spring Batch version thực sự dùng**; không tự dựng bảng metadata rút gọn rồi cho rằng behavior tương đương repository chuẩn.

### 4.2. Range partition dùng interval nửa mở

Chọn quy tắc:

~~~text
Partition 0: [1, 252)
Partition 1: [252, 503)
Partition 2: [503, 754)
Partition 3: [754, 1004)
~~~

Tức worker SQL phải đọc:

~~~sql
SELECT event_id, snapshot_key, customer_id, amount_cents
FROM source_events
WHERE snapshot_key = :snapshotKey
  AND event_id >= :fromInclusive
  AND event_id < :toExclusive
ORDER BY event_id;
~~~

`toExclusive` **không phải ID cuối cùng được xử lý**. Một lỗi `<=` thay cho `<` có thể tạo overlap giữa hai partition. Nếu manager tạo trùng range hoặc reader dùng boundary không nhất quán, số lượng read vẫn có thể đúng ở một số test nhỏ nhưng output thiếu/trùng khi tăng worker.

### 4.3. Test các dạng dữ liệu lệch

Ngoài fixture 1.003 row, cần có:

| Dataset | Mục tiêu |
|---|---|
| 0 row | Không tạo invalid range, không treo step |
| 1 row | Không tạo off-by-one/partition rỗng ngoài thiết kế |
| 3 rows, gridSize 16 | Xử lý `gridSize` lớn hơn số ID |
| 1.003 rows, 4 partitions | Kiểm tra remainder và boundaries |
| ID không liên tục, 20% gaps | Range vẫn phủ mọi ID tồn tại, không giả định row count theo khoảng |
| ID gần `Long.MAX_VALUE` | Kiểm tra overflow khi tính range |
| Nhiều record cùng customer ID | Kiểm tra reader partition độc lập **nhưng writer aggregate có thể lock trùng** |
| Duplicate message cùng partition | Kiểm tra idempotency và same-execution coordination |
| Input bị sửa giữa restart | Test phát hiện vi phạm immutable snapshot contract |

Nếu module dùng partition theo file, ngày hoặc tenant, thay `event_id` bằng đúng business boundary nhưng vẫn kiểm tra **coverage, exclusivity, stable names, checkpoint và ownership**.

## 5. Unit test Partitioner: không cần broker để bắt off-by-one

Đây là lớp test **nhanh, deterministic và bắt buộc** trước khi chạy integration qua messaging.

### 5.1. Một Partitioner tối giản cho range cố định

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class IdRangePartitioner implements Partitioner {
    private final long firstInclusive;
    private final long endExclusive;

    public IdRangePartitioner(long firstInclusive, long endExclusive) {
        if (firstInclusive >= endExclusive) {
            throw new IllegalArgumentException("Expected non-empty ID range");
        }
        this.firstInclusive = firstInclusive;
        this.endExclusive = endExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }
        long span = Math.subtractExact(endExclusive, firstInclusive);
        int partitions = Math.toIntExact(Math.min(span, (long) gridSize));
        long width = span / partitions + (span % partitions == 0 ? 0 : 1);

        Map<String, ExecutionContext> plan = new LinkedHashMap<>();
        long from = firstInclusive;
        for (int i = 0; i < partitions; i++) {
            // Last range may be shorter than width. Avoid overflow when
            // endExclusive is close to Long.MAX_VALUE.
            long to = endExclusive - from <= width
                    ? endExclusive : Math.addExact(from, width);
            ExecutionContext ctx = new ExecutionContext();
            ctx.putLong("fromInclusive", from);
            ctx.putLong("toExclusive", to);
            plan.put(String.format("partition-%04d", i), ctx);
            from = to;
            if (from == endExclusive) {
                break;
            }
        }
        return plan;
    }
}
~~~

Code minh họa dùng `Math.subtractExact` và `Math.addExact` để **báo lỗi** với các phép tính vượt `long`, nhưng ở partition cuối kiểm tra số phần tử còn lại **trước khi cộng width** để một range hợp lệ sát `Long.MAX_VALUE` không bị báo overflow giả. Với range `[1,1004)`, `gridSize=4` sẽ cho đúng bốn khoảng trong phần 4.2. Để xử lý input rỗng, nên quyết định ngay ở manager trước khi khởi tạo partitioner; class trên **cố ý từ chối** range rỗng và test phải xác nhận contract ấy.

**Lưu ý:** `gridSize` là gợi ý/phần cấu hình lập plan; tổng số `StepExecution` và worker active thực tế còn phụ thuộc partitioner/handler/executor và consumer concurrency. Không viết test cứng rằng `gridSize=32` thì phải có 32 pod.

### 5.2. JUnit 5 kiểm tra coverage và exclusivity

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class IdRangePartitionerTest {

    @Test
    void fourPartitionsCoverAllIdsWithoutOverlap() {
        Map<String, ExecutionContext> plan =
                new IdRangePartitioner(1L, 1004L).partition(4);

        assertThat(plan).hasSize(4);
        List<ExecutionContext> contexts = plan.values().stream()
                .sorted(Comparator.comparingLong(
                        c -> c.getLong("fromInclusive")))
                .toList();

        long expectedFrom = 1;
        long coveredSlots = 0;
        for (ExecutionContext ctx : contexts) {
            long from = ctx.getLong("fromInclusive");
            long to = ctx.getLong("toExclusive");
            assertThat(from).isEqualTo(expectedFrom);
            assertThat(to).isGreaterThan(from);
            coveredSlots += to - from;
            expectedFrom = to;
        }
        assertThat(expectedFrom).isEqualTo(1004L);
        assertThat(coveredSlots).isEqualTo(1003L);
        assertThat(plan.keySet()).containsExactly(
                "partition-0000", "partition-0001",
                "partition-0002", "partition-0003");
    }

    @Test
    void fewerIdsThanGridSizeStillProducesValidPlan() {
        Map<String, ExecutionContext> plan =
                new IdRangePartitioner(1L, 4L).partition(16);
        assertThat(plan).hasSize(3);
        assertThat(plan.values().stream()
                .mapToLong(c -> c.getLong("toExclusive")
                        - c.getLong("fromInclusive")).sum())
                .isEqualTo(3L);
    }

    @Test
    void validRangeNearLongMaxDoesNotOverflowLastPartition() {
        long end = Long.MAX_VALUE;
        Map<String, ExecutionContext> plan =
                new IdRangePartitioner(end - 10, end).partition(3);
        assertThat(plan).hasSize(3);
        assertThat(plan.values().stream()
                .mapToLong(c -> c.getLong("toExclusive")
                        - c.getLong("fromInclusive")).sum())
                .isEqualTo(10L);
        assertThat(plan.get("partition-0002")
                .getLong("toExclusive")).isEqualTo(end);
    }
}
~~~

Đây là **unit test Java độc lập với broker** (cần dependencies Spring Batch, JUnit 5, AssertJ và class `IdRangePartitioner` trong source test). Trong production cần test thêm tính **ổn định của partition names** qua restart: nếu lần đầu dùng `gridSize=4` nhưng restart lại tạo kế hoạch `gridSize=8`, các `StepExecution` names/`ExecutionContext` có thể không tương thích với trạng thái cũ.

### 5.3. Property-based test và boundary data

Có thể sinh các tổ hợp `min, max, gridSize` hợp lệ với giới hạn long an toàn:

1. Mọi `from < to`.
2. Không có hai khoảng trùng nhau.
3. Hợp các khoảng bằng `[min,max)`.
4. Key partition duy nhất.
5. Thứ tự kế hoạch deterministic.
6. Nếu khoảng không có row do ID gap, worker hoàn tất mà không ghi dữ liệu.

Property-based test giúp phát hiện off-by-one và overflow mà vài fixture thủ công dễ bỏ qua. Nhưng **unit test partitioner không chứng minh worker đọc SQL đúng boundary**: cần integration test tiếp theo.

## 6. Worker step phải đọc đúng ExecutionContext

Một worker reader trong remote partitioning phải sử dụng input từ **đúng worker `StepExecution`** thay vì một singleton state chia sẻ giữa tất cả partition.

### 6.1. Reader @StepScope theo range

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record SourceEvent(
        String snapshotKey, long eventId, long customerId, long amountCents) {}

@Configuration
public class RemoteWorkerReaderConfiguration {

    @Bean
    @StepScope
    public JdbcCursorItemReader<SourceEvent> partitionReader(
            @Qualifier("businessDataSource") DataSource dataSource,
            @Value("#{jobParameters['snapshotKey']}") String snapshotKey,
            @Value("#{stepExecutionContext['fromInclusive']}") Long from,
            @Value("#{stepExecutionContext['toExclusive']}") Long to) {

        if (snapshotKey == null || snapshotKey.isBlank()
                || from == null || to == null || from >= to) {
            throw new IllegalArgumentException("Invalid partition range");
        }

        return new JdbcCursorItemReaderBuilder<SourceEvent>()
                .name("sourceEventsReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT snapshot_key, event_id,
                           customer_id, amount_cents
                    FROM source_events
                    WHERE snapshot_key = ?
                      AND event_id >= ?
                      AND event_id < ?
                    ORDER BY event_id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setString(1, snapshotKey);
                    ps.setLong(2, from);
                    ps.setLong(3, to);
                })
                .rowMapper((rs, rowNum) -> new SourceEvent(
                        rs.getString("snapshot_key"),
                        rs.getLong("event_id"),
                        rs.getLong("customer_id"),
                        rs.getLong("amount_cents")))
                .saveState(true)
                .build();
    }
}
~~~

`SourceEvent` là record package-private đặt cùng package; khi chia file Java, khai báo `public` trong `SourceEvent.java` nếu cần truy cập khác package. `@StepScope` dùng late binding các tham số của `StepExecution`. `JdbcCursorItemReader` giữ cursor/state trong vòng đời step, vì vậy không chia sẻ một instance mutable giữa nhiều worker executions.

**Điểm cần test:**

- Worker có thực sự nhận `fromInclusive/toExclusive` từ **shared metadata** của execution được request không?
- `JobParameters['snapshotKey']` là cùng immutable snapshot manager dự kiến?
- Reader dùng `< toExclusive`, không dùng `<=`?
- Khi restart, tên `ItemStream` `sourceEventsReader` và `ExecutionContext` keys có tương thích?
- Với input gapped, không giả định mỗi khoảng có `to-from` row.
- Reader/writer có datasource và transaction manager phù hợp, tránh sử dụng nhầm metadata DB cho dữ liệu nghiệp vụ.

### 6.2. Writer idempotent làm hàng rào cho replay

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration
public class RemoteWorkerWriterConfiguration {

    @Bean
    public JdbcBatchItemWriter<SourceEvent> processedEventWriter(
            @Qualifier("businessDataSource") DataSource ds) {

        return new JdbcBatchItemWriterBuilder<SourceEvent>()
                .dataSource(ds)
                .sql("""
                    INSERT INTO processed_events
                        (snapshot_key, event_id, customer_id, amount_cents)
                    VALUES
                        (:snapshotKey, :eventId, :customerId, :amountCents)
                    ON CONFLICT (snapshot_key, event_id) DO NOTHING
                    """)
                .itemSqlParameterSourceProvider(e ->
                        new MapSqlParameterSource()
                                .addValue("snapshotKey", e.snapshotKey())
                                .addValue("eventId", e.eventId())
                                .addValue("customerId", e.customerId())
                                .addValue("amountCents", e.amountCents()))
                .assertUpdates(false)
                .build();
    }
}
~~~

`assertUpdates(false)` cho phép một replay hợp lệ ảnh hưởng **0 row** khi unique key đã tồn tại. Đây là **ví dụ về row-level dedupe**, không tự bảo đảm payload giống nhau. Nếu cùng business key có amount khác, `DO NOTHING` có thể che lỗi nguồn; cần thêm checksum/version hoặc một phép kiểm tra nghiệp vụ để fail/quarantine.

Với writer làm `balance += delta`, unique key ở bảng output tổng hợp **không đủ chống cộng hai lần**. Phải có event ledger/idempotency key guard **cùng transaction** hoặc một kiến trúc append-only rồi aggregate.

## 7. Test pyramid: mỗi cấp phải chứng minh một loại lỗi khác nhau

Một bộ remote partitioning test bền vững không nên chỉ có một end-to-end test mất nhiều phút và khó debug.

~~~mermaid
flowchart TB
    E["E2E: manager + broker + ≥2 worker processes + DB"]
    I["Integration: handler, transport, shared JobRepository, step scope"]
    W["Worker/DB: reader, writer, transaction, idempotency, restart"]
    U["Unit: Partitioner, boundaries, reply correlation, policies"]
    E --> I
    I --> W
    W --> U
~~~

| Cấp test | Dùng thật hay giả? | Bắt lỗi gì? | Không đủ để khẳng định |
|---|---|---|---|
| **Unit Partitioner** | Java in-memory, `ExecutionContext` | Overlap, gap, names, off-by-one, overflow | Transport/metadata/worker deployment đúng |
| **Unit reply correlation** | Fake message, manager aggregator | Trùng, trễ, sai execution ID và attempt | Broker ACK, serialization, partition execution thật |
| **Worker DB integration** | Real PostgreSQL, một worker step | Reader SQL, transaction, unique key, checkpoint | Remote dispatch qua broker thành công |
| **Transport integration** | Real broker + message converters | Serialization, routing, retry/DLQ, correlation metadata | Tính đúng business output của toàn job |
| **Multi-context integration** | Manager và worker context tách biệt, shared DB | Configuration, `StepLocator`, repository, replies | Process isolation/network thực |
| **Multi-process E2E** | Manager process, broker, ≥2 worker processes, DB thật | Routing, concurrency, restart, kill, recovery | Mọi loại outage/cluster scale được mô phỏng |
| **Resilience/chaos staging** | Containers/network faults/partition skew | Crash, network timeout, redelivery, eventual recovery | An toàn production nếu không có đối soát và monitoring |

**Không gọi unit test `Partitioner` là “remote integration test”.** Nó rất hữu ích nhưng chưa chạy một request qua broker. Ngược lại, nếu E2E chỉ assert `JobExecution.COMPLETED` thì vẫn thiếu kiểm tra dữ liệu.

### 7.1. Lưu test artifacts để tái hiện

Mỗi lần test lỗi nên lưu:

- `testRunId`, `snapshotKey`, JDK/Spring Batch/Integration/driver versions.
- Manager `jobExecutionId` và các worker `stepExecutionId`.
- Partition map: tên, `fromInclusive`, `toExclusive`.
- Broker queue/consumer/prefetch, số worker replica, instance identifiers.
- Timeline publish → delivery → execution start → commit → metadata update → reply.
- PostgreSQL query/update counts và **business reconciliation**.
- Retry/timeout policy và fault injection point.

Đảm bảo không đưa password, access token, SQL bind data nhạy cảm hoặc raw message payload lên CI artifacts không được kiểm soát.

## 8. Testcontainers: chạy infrastructure thật, không thay toàn bộ hệ thống bằng mock

JUnit 5 + Testcontainers có thể tạo **PostgreSQL và RabbitMQ** dùng chung cho một test suite. Mẫu sau là phần **khởi tạo hạ tầng**; nó **không tự launch manager/worker remote**, vốn phải được cấu hình riêng.

### 8.1. Hạ tầng Testcontainers

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class RemotePartitioningInfrastructureTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("remote_partition_test")
                    .withUsername("test")
                    .withPassword("test");

    @Container
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:3.13-management-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }

    @Test
    void infrastructureCanStart() {
        // Test ứng dụng thật cần thêm schema/queues và assertions.
    }
}
~~~

**Lưu ý phiên bản:** các phương thức và module của Testcontainers/RabbitMQ có thể khác giữa các phiên bản; kiểm tra artifact/version sử dụng. Có thể thay RabbitMQ bằng JMS/Kafka tùy transport production; mục tiêu là test **broker semantics tương ứng**, không giả định mọi broker có ACK/requeue/ordering giống nhau.

`spring.datasource.*` trong ví dụ chỉ cấu hình **một datasource auto-configured**. Nếu ứng dụng dùng `businessDataSource` và `batchMetadataDataSource` riêng với custom prefixes, phải truyền đúng custom properties cho từng pool. Một test có một datasource không chứng minh kiến trúc hai datasource trong production được wiring đúng.

### 8.2. Multi-process thật cần topology khác one-context test

Một `@SpringBootTest` tạo một application context; nếu manager và worker beans tình cờ được load trong cùng context, test có thể **thành công mà không có một worker process độc lập nào**. Để kiểm thử remote thật:

~~~text
JUnit host/test harness
       |
       +--> PostgreSQL Testcontainer (shared metadata + business schemas)
       |
       +--> RabbitMQ Testcontainer
       |
       +--> Worker process/container A --+
       |                                 +--> same Postgres & Rabbit
       +--> Worker process/container B --+
       |
       +--> Manager process/context
                  |
                  +--> launch job and await result
~~~

Trong các containers chạy cùng Docker network, dùng **network aliases** của Postgres/broker, không dùng `localhost` hoặc host-mapped port của JUnit host một cách mù quáng. Các giá trị `spring.rabbitmq.host` dùng trên test JVM **khác** địa chỉ internal network của worker container.

Cần tách cấu hình rõ:

- **Manager role:** `JobRepository`, `Partitioner`, manager partition step, request/outbound channel, reply/inbound channel nếu dùng.
- **Worker role:** worker step bean, `StepLocator`, `StepExecutionRequestHandler`/cơ chế worker request handler tương ứng, inbound request adapter, outbound reply adapter nếu dùng.
- **Shared:** tương thích Spring Batch/Integration/message serializer, DB metadata schema, broker topology, transaction policies.

Nếu chỉ startup hai worker Java threads trong cùng JVM, đó là **multi-context/in-process concurrency test**, hữu ích nhưng chưa kiểm chứng process crash, socket reconnect, container shutdown hoặc mixed versions.

### 8.3. Không để Boot tự chạy job ngoài test harness

Trong test manager, `spring.batch.job.enabled=false` thường giúp ngăn Spring Boot tự launch các job lúc context khởi tạo (kiểm tra đúng Boot version). Sau đó test tự gọi `JobLauncher` với **cùng identifying `JobParameters` đã chuẩn bị**.

Nếu đồng thời có `ApplicationRunner` custom launch job hoặc scheduler đang chạy trong test context, cần vô hiệu hóa nó riêng. Không để job được launch hai lần do auto-run và test method, rồi quy lỗi duplicate cho broker.

### 8.4. Khi nào dùng broker giả thay thật?

Mock `MessageChannel` hợp lý để kiểm tra **routing/correlation logic** tại một lớp. Nhưng nếu mục tiêu là kiểm chứng redelivery sau ACK chưa đến, prefetch, durable queue hoặc consumer restart, phải chạy **transport thật** hoặc một adapter có fidelity tương ứng.

Một in-memory channel không chứng minh:

- Message đã tồn tại bền vững sau khi manager/worker crash.
- Requeue có semantics giống RabbitMQ/Kafka/JMS.
- Message converter bảo toàn numeric IDs/`ExecutionContext` fields qua process khác.
- Hệ thống chống gửi lại cùng request sau broker reconnect.

## 9. End-to-end test: launch job rồi so tập dữ liệu

Một E2E test tối thiểu nên:

1. Tạo schema metadata chính thức + business schema trong test DB.
2. Seed `snap-test-001` 1.003 event; đặt output ở **trạng thái đã biết**.
3. Bật RabbitMQ/JMS broker và **khởi động ≥2 worker process độc lập**; chờ consumer subscribed.
4. Launch manager job với `snapshotKey` và partition plan đã xác định.
5. Chờ job hoàn tất với **deadline hữu hạn**; nếu timeout, thu thread dumps/logs/metadata.
6. Đọc lại `JobExecution`, tất cả worker `StepExecution` từ repository.
7. So output actual với expected bằng SQL và business checksums.
8. Xác minh worker logs/traces cho thấy **ít nhất hai instance thực sự xử lý partition**, nếu đó là mục tiêu test concurrency.

### 9.1. Đoạn integration test cho JobLauncher

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(properties = "spring.batch.job.enabled=false")
class RemotePartitioningEndToEndTest {

    @Autowired JobLauncher jobLauncher;
    @Autowired JobExplorer jobExplorer;
    @Autowired @Qualifier("remotePartitionJob") Job remotePartitionJob;
    @Autowired @Qualifier("businessJdbcTemplate") JdbcTemplate jdbc;

    @Test
    void allRemotePartitionsCompleteAndOutputIsExact() throws Exception {
        // Harness đã seed schema/snapshot và khởi động workers trước.
        JobParameters params = new JobParametersBuilder()
                .addString("snapshotKey", "snap-test-001", true)
                .toJobParameters();

        JobExecution launched = jobLauncher.run(remotePartitionJob, params);
        JobExecution reloaded =
                jobExplorer.getJobExecution(launched.getId());
        assertThat(reloaded).isNotNull();
        assertThat(reloaded.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        Long actualRows = jdbc.queryForObject("""
            SELECT count(*) FROM processed_events
            WHERE snapshot_key = ?
            """, Long.class, "snap-test-001");
        assertThat(actualRows).isEqualTo(1003L);

        Long actualTotal = jdbc.queryForObject("""
            SELECT sum(amount_cents) FROM processed_events
            WHERE snapshot_key = ?
            """, Long.class, "snap-test-001");
        assertThat(actualTotal).isEqualTo(5_035_060L);
    }
}
~~~

Đây là **lõi assertions** của E2E, không phải test tự khởi động đầy đủ workers. Trước khi dùng, cấu hình harness tạo/seed DB và broker, chạy worker processes, khởi tạo `remotePartitionJob`/`businessJdbcTemplate`; thêm timeout có giới hạn cho lời gọi launcher nếu job launcher chờ đồng bộ. `JobLauncher.run` thường đợi job chạy xong với launcher đồng bộ, nhưng **có thể trả về sớm** với launcher bất đồng bộ; trong trường hợp đó phải poll `JobExplorer` bằng deadline, không assert trạng thái ngay lập tức.

**Không chạy E2E test có side effects dưới `@Transactional` ở test method** rồi giả định worker process ở connection khác nhìn thấy dữ liệu chưa commit. Seed fixture phải **commit trước** khi manager dispatch. Test DB nên được tách riêng, không để cleanup hoặc transaction từ JUnit vô tình che output của remote worker.

### 9.2. Kiểm tra chính xác tập key bằng EXCEPT

So sánh count/tổng tiền là cần nhưng **chưa đủ**. Chạy hai truy vấn read-only:

~~~sql
-- Input có nhưng output thiếu:
SELECT event_id, customer_id, amount_cents
FROM source_events
WHERE snapshot_key = 'snap-test-001'
EXCEPT
SELECT event_id, customer_id, amount_cents
FROM processed_events
WHERE snapshot_key = 'snap-test-001';
~~~

~~~sql
-- Output có nhưng không khớp input:
SELECT event_id, customer_id, amount_cents
FROM processed_events
WHERE snapshot_key = 'snap-test-001'
EXCEPT
SELECT event_id, customer_id, amount_cents
FROM source_events
WHERE snapshot_key = 'snap-test-001';
~~~

Hai tập chênh lệch đều phải **rỗng** khi business contract là identity transform. `EXCEPT` theo semantics set, nên vẫn cần unique constraints và kiểm tra count để phát hiện duplicates nếu schema không có primary key. Với pipeline có filter/transform, so với **expected transformed set**, không so trực tiếp row thô.

### 9.3. Đọc trạng thái worker StepExecutions

Trong test schema PostgreSQL của Spring Batch, các bảng `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và execution context cần khớp phiên bản đang dùng. Có thể đọc trạng thái worker qua `JobExplorer` và repository API hoặc truy vấn read-only có phạm vi test:

~~~sql
SELECT STEP_EXECUTION_ID,
       JOB_EXECUTION_ID,
       STEP_NAME,
       STATUS,
       EXIT_CODE,
       READ_COUNT,
       WRITE_COUNT,
       COMMIT_COUNT,
       ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Trong Spring Batch, tên worker executions thường phản ánh `workerStepName:partitionName` nhưng quy ước tên phụ thuộc cấu hình. Test phải kiểm tra **tập names/executions đúng với partition map của job**, không khớp một prefix ngẫu nhiên rồi đếm N row. Với step restart, **một partition logic có thể có nhiều `StepExecution` qua các lần chạy**, nên tách logic partition identity khỏi attempt/execution ID.

### 9.4. Xác minh thật sự có concurrency

Một job chạy 16 partition nhưng chỉ có một consumer có thể vẫn hoàn tất chính xác. Nếu mục tiêu test **remote concurrency**, cần thêm oracle:

- Workers ghi structured log `workerInstanceId, stepExecutionId, partitionName, start/end`.
- Có ≥2 **instance IDs khác nhau** đã nhận partition thực.
- Thời gian chạy partition **có overlap**, không chỉ tuần tự.
- Tổng số worker active không vượt concurrency limit được cấu hình.
- Không có 2 worker cùng ghi business effect của một partition **ngoài recovery contract**.

**Không dựa chỉ vào số request gửi** để chứng minh parallel execution: broker có thể queue tất cả trong khi một worker xử lý lần lượt.

## 10. Test message/reply correlation và request trễ

Transport có thể trả reply không đúng thứ tự dispatch. Nếu manager giao P0, P1, P2 nhưng nhận P2, P0, P1, đó là bình thường với nhiều worker; manager không được cộng “reply thứ 2” vào “partition thứ 2” chỉ theo vị trí.

### 10.1. Correlation nên dựa vào execution identity

Một envelope **test-only** để mô hình hóa logic:

~~~java
record TestPartitionRequest(
        long jobExecutionId,
        long stepExecutionId,
        String partitionName,
        String requestId) {}

record TestPartitionReply(
        long jobExecutionId,
        long stepExecutionId,
        String partitionName,
        String requestId,
        String reportedStatus) {}
~~~

**Đây không phải wire DTO chuẩn của Spring Batch.** Remote partitioning thực tế có `StepExecutionRequest`/`StepExecution` và converter/integration adapters riêng. Test envelope minh họa cách thiết kế **correlation validation**, không phải cấu trúc message để tự thay thế serializer framework.

### 10.2. Các invariants quan trọng

- Reply chỉ được áp vào **đúng jobExecutionId và stepExecutionId** đang đợi.
- `partitionName` phải phù hợp partition plan/metadata; không chỉ tin một tên do payload tự khai.
- Nhận lại reply của cùng execution **không làm tăng số partition completed**.
- Reply trễ từ execution cũ không làm execution mới chuyển sang `COMPLETED`.
- Reply `FAILED`/`STOPPED` không được đổi thành success chỉ vì manager đã nhận đủ số message.
- Phản hồi báo `COMPLETED` nhưng shared `JobRepository` chưa ghi hoàn tất phải có chính sách **đợi/xác minh/fail**, không tin reply một cách mù quáng.
- Request thiếu/không hợp lệ execution ID phải bị từ chối có quan sát, không tạo một StepExecution mới ngoài partition plan.

### 10.3. Bảng tình huống test tương quan

| Thứ tự nhận | Tình huống | Kết quả đúng |
|---|---|---|
| P2, P0, P1 | Out-of-order replies | Đúng ba partition, kết quả không dựa vị trí |
| P0, P0, P1 | Duplicate P0 | Không coi P0 hai lần thay cho P2 |
| P0(old), P0(new) | Late reply từ attempt cũ | Không ghi đè trạng thái execution mới |
| P0(jobA), P1(jobB) | Hai job instances cùng chạy | Không trộn completion giữa jobs |
| P0 reported FAILED | Worker thất bại | Manager step/job không thành công giả |
| P0 COMPLETED reply, metadata chưa hoàn tất | Eventual consistency/transport race | Đợi/xác minh repository hoặc timeout báo rõ |
| Reply P99 không tồn tại | Unknown execution | Reject/quarantine, có log và cảnh báo |
| Không có reply | Missing reply/worker crash | Có deadline/recovery; không đợi vô hạn |

**Tùy implementation**, `MessageChannelPartitionHandler` có thể cần reply channel và cơ chế aggregation hoặc phiên bản khác có chiến lược đọc repository. Không áp chính sách timeout/polling của một topology vào topology khác mà chưa đọc chính cấu hình runtime. Test phải phản ánh **lựa chọn request/reply/metadata đang vận hành**, không “sửa” kết quả bằng một fake aggregator dễ dãi.

## 11. Thiết kế test race có thể tái hiện bằng barrier

Không dùng `Thread.sleep(100)` rồi hy vọng hai worker tình cờ va nhau. Trên CI nhanh/chậm khác nhau, sleep-based tests thường flaky và không chứng minh đã tạo concurrency.

### 11.1. Một test hai transaction cùng INSERT key

Ví dụ dưới đây **chỉ kiểm tra hàng rào idempotency ở PostgreSQL** trước; nó **không tự chạy qua broker**. Chạy trên database test với `processed_events` đã tạo và chưa có key `race-test/9999`.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest(properties = "spring.batch.job.enabled=false")
class DuplicateWriteRaceTest {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate tx;

    @Autowired
    DuplicateWriteRaceTest(
            @Qualifier("businessJdbcTemplate")
            JdbcTemplate businessJdbcTemplate,
            @Qualifier("businessTransactionTemplate")
            TransactionTemplate businessTransactionTemplate) {
        this.jdbc = businessJdbcTemplate;
        this.tx = businessTransactionTemplate;
    }

    @Test
    void concurrentDuplicateEventsCreateOneRow() throws Exception {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        Callable<Integer> attempt = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Barrier timed out");
            }
            return tx.execute(status -> jdbc.update("""
                INSERT INTO processed_events
                    (snapshot_key, event_id, customer_id, amount_cents)
                VALUES ('race-test', 9999, 1, 250)
                ON CONFLICT (snapshot_key, event_id) DO NOTHING
                """));
        };

        try {
            Future<Integer> a = executor.submit(attempt);
            Future<Integer> b = executor.submit(attempt);
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            assertThat(a.get(15, TimeUnit.SECONDS)
                    + b.get(15, TimeUnit.SECONDS)).isEqualTo(1);

            Long rows = jdbc.queryForObject("""
                SELECT count(*) FROM processed_events
                WHERE snapshot_key = 'race-test' AND event_id = 9999
                """, Long.class);
            assertThat(rows).isEqualTo(1L);
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Class trên dùng Spring Boot Test để inject hai bean `businessJdbcTemplate` và `businessTransactionTemplate`, cần khai báo những bean ấy trỏ vào **cùng business database và transaction manager tương ứng**. Pool phải đủ connection để hai transaction đồng thời, tối thiểu theo measured connection usage; không sử dụng cùng một connection JDBC trên cả hai thread. Test cũng cần một `processed_events` schema và output namespace/snapshot `race-test` được isolate, không dùng lại dữ liệu của suite khác.

Không gắn `@Transactional` trên test method rồi giả định transaction ấy bao trùm hai worker threads: Spring transaction context thường thread-bound và các threads mới **không kế thừa** transaction test. `TransactionTemplate` trong mỗi callable giúp tạo transaction riêng, và unique constraint là cơ chế DB bảo vệ kết quả.

### 11.2. Điểm tiêm lỗi có khả năng kiểm soát

Ở E2E, để tái hiện crash tại ranh giới cụ thể, dùng **test-only hook** hoặc instrumented sidecar:

~~~text
Hook A: sau khi worker load StepExecution, trước reader.open()
Hook B: sau read N items, trước write chunk
Hook C: ngay sau writer SQL execution, trước business COMMIT
Hook D: sau business COMMIT, trước worker metadata/reply/ACK
Hook E: sau metadata COMPLETED, trước reply publish
Hook F: sau manager nhận reply, trước final aggregation
~~~

**Không coi mọi hook đều có thể đặt tùy ý bằng một listener chuẩn.** Điểm “sau COMMIT trước metadata” phụ thuộc transaction topology; muốn tạo crash đúng mốc, dùng transaction synchronization/instrumentation phù hợp hoặc một harness có quyền kiểm soát commit/transport. Hãy ghi rõ test đã tiêm lỗi **trước hay sau transaction commit thực tế**, không chỉ “ở đâu đó trong `write()`”.

### 11.3. Timeout hữu hạn thay cho test treo

- Dùng `CountDownLatch.await(timeout)`, `Future.get(timeout)`, Awaitility hoặc polling với deadline.
- Khi timeout, collect thread dumps, process state, `BATCH_STEP_EXECUTION`, broker queue counts và database locks.
- Cleanup mọi latch/container/pool trong `finally` để không ảnh hưởng test tiếp theo.
- Không làm assert thời gian quá ngắn tùy ý trên CI máy yếu; tách **functional deadline** khỏi **performance SLO**.

Một test kết thúc đúng sau khi `sleep(2s)` không chứng minh manager aggregation đúng. **Đợi đúng condition** (state, count, checksum) và timeout có giải thích.

## 12. Ma trận lỗi remote partitioning: business commit, metadata và ACK

Remote partitioning cần test cả **failure mode** và **recovery mode**. Mục tiêu không phải ép mọi job đều `COMPLETED` dù cơ sở dữ liệu hỏng; mục tiêu là **không báo thành công giả**, trạng thái lỗi có thể quan sát và restart/reconciliation đúng khi hạ tầng phục hồi.

| Điểm lỗi cần inject | Trạng thái khả dĩ | Oracle bắt buộc |
|---|---|---|
| Manager crash **trước khi publish** request | Partition executions đã được tạo nhưng chưa giao | Không mất vĩnh viễn một partition; recovery tìm được missing work |
| Publish thành công nhưng manager **mất publish ACK** | Manager có thể gửi lại cùng request | Transport duplicate không làm business effect nhân đôi |
| Worker crash trước `StepExecution` được load | Broker có thể redeliver | Không tạo một execution ngẫu nhiên ngoài repository |
| Worker crash sau reader.open, trước write | Chưa có business commit chunk đó | Restart reader checkpoint đúng, không bỏ sót |
| Worker crash giữa JDBC batch trước commit | Transaction chưa được công nhận commit | Rollback hoặc kết quả không chắc chắn được đối soát, không tin update counts |
| Worker crash **sau business commit, trước metadata/reply** | Business result đã có, manager chưa biết | Replay idempotent; JobRepository và output cuối nhất quán |
| Worker hoàn tất nhưng reply thất lạc | Metadata có thể là `COMPLETED`, manager vẫn đợi | Timeout/recovery/polling theo topology; không treo vô hạn |
| Reply đến hai lần | Aggregator nhận duplicate | Không đếm hai lần thay cho partition thiếu |
| Reply đến sai thứ tự | P3 trước P0 | Kết quả theo execution identity, không theo thứ tự |
| Reply cũ đến sau restart | Stale execution/attempt | Không cập nhật execution mới bằng reply cũ |
| Broker mất kết nối khi worker đang xử lý | Request có thể bị redeliver/requeued | Không hai side effects trái contract; có log/alert rõ |
| Metadata DB tạm unavailable | Worker có thể không đọc/ghi `StepExecution` được | Job không `COMPLETED` giả, retry/rollback có giới hạn |
| Business DB unavailable sau metadata load | Worker execution thất bại hoặc retry | State đúng, input giữ nguyên và restart an toàn |
| Worker vừa fail do `40P01` deadlock | Transaction rollback | Retry transaction theo policy, không retry vô hạn |
| Pool cạn vì concurrency quá cao | Worker đợi connection hoặc timeout | Backpressure, budget, không khiến toàn job mất dữ liệu |
| Manager restart khi workers còn chạy | Hai generation manager có thể cùng quan tâm job | Không launch duplicate JobInstance/work units ngoài contract |
| Rolling deploy mixed worker versions | Request cũ gặp worker mới | Serializer/schema/stepName compatibility hoặc drain an toàn |
| Input snapshot bị sửa giữa restart | Reader thấy tập ID khác | Test phát hiện contract vi phạm, không âm thầm success |

**Đừng rút gọn ma trận thành “kill worker rồi job thành công”**. Cần xem **kill đúng lúc nào**, manager/worker đang dùng transaction manager nào, broker ACK mode nào, và trạng thái cuối của từng execution.

### 12.1. Ghi rõ ranh giới transaction

~~~text
Business SQL execute
  |
  +---- transaction COMMIT tại business DB
  |
  +---- StepExecution/ExecutionContext metadata update
  |
  +---- Reply publication (nếu topology có reply)
  |
  +---- Request ACK ở broker (thời điểm phụ thuộc adapter)
~~~

Sơ đồ là **một topology giả định để thiết kế fault points**, không khẳng định mọi Spring Batch configuration luôn có đúng thứ tự này. Với business và metadata nằm trong **cùng một JDBC local transaction**, commit boundary có thể gộp một phần. Với hai DB/broker, thường không có distributed atomicity mặc định.

Trong report test phải mô tả **transaction nào bao phủ thao tác nào** và injection được đặt **trước hay sau COMMIT xác nhận**.

### 12.2. Crash trước commit và sau commit không được gộp

**Trước business commit:** Nếu transaction thực sự chưa commit và rollback thành công, item có thể được đọc/ghi lại mà không tạo duplicate business effect. Nhưng nếu kết nối mất khi commit đang diễn ra, client **không chắc biết kết quả**. Không suy từ exception rằng database chưa ghi gì.

**Sau business commit:** DB đã có output; nếu worker/metadata/broker chưa thống nhất completion, item/chunk có thể được xử lý lại. Writer có unique business key hoặc event ledger bảo vệ output; các API/email/queue side effects cần outbox/dedupe riêng.

### 12.3. Người quản lý không được “đếm ACK thay cho kết quả”

Nếu broker ACK báo request đã được xử lý theo một điểm nào đó của consumer adapter, nhưng business transaction lỗi sau đó, ACK không tự chứng minh kết quả cuối thành công. Nếu reply gửi trùng, manager cũng không được coi hai reply tương đương hai worker StepExecutions đã hoàn tất. **Shared `JobRepository` và business reconciliation phải là các lớp kiểm chứng độc lập**.

## 13. Restart một partition: giữ identity hay tạo execution mới?

Spring Batch phân biệt:

- **`JobInstance`:** job name + identifying `JobParameters`.
- **`JobExecution`:** một lần thực thi của JobInstance; restart có thể tạo execution mới cùng instance.
- **`StepExecution`:** một attempt/thực thi cụ thể của step.
- **Logical partition:** đơn vị dữ liệu có tên/boundary đã lập kế hoạch, có thể liên quan nhiều `StepExecution` qua các lần restart.

Đó là lý do **không dùng `stepExecutionId` đơn độc làm business dedupe key**: khi restart có thể xuất hiện ID mới cho cùng logical data. Business dedupe nên dựa vào `snapshotKey + eventId` hoặc event ID bền vững, không phụ thuộc attempt ID.

### 13.1. Test contract cho restart

1. Khởi chạy job với identifying `snapshotKey="snap-test-001"`.
2. Làm một partition fail có kiểm soát sau một số chunk; cho các partition khác hoàn tất.
3. Xác nhận job/manager step **không thành công giả**.
4. Tắt/giải phóng worker execution cũ (hoặc dùng fencing nếu có khả năng stale worker).
5. Khôi phục hạ tầng, dùng Spring Batch restart **cùng JobInstance** với input snapshot không đổi.
6. Xác minh metadata/ExecutionContext phản ánh partition cần tiếp tục, không tự lập một plan khác.
7. Đối soát output toàn bộ snapshot bằng expected set, kể cả chunk đã commit trước lỗi.
8. Xác nhận không có partition bị bỏ quên `STARTED` mãi hoặc duplicate active.

Nếu dùng một tham số kiểu `run.id` mới để ép job chạy lại, bạn có thể đã tạo **JobInstance khác** chứ không restart instance lỗi. Test phải khẳng định **identifying parameters** và tên job/step phù hợp; đừng chỉ so “cùng source file”.

### 13.2. Partition plan phải ổn định

Nếu lần chạy đầu tạo:

~~~text
partition-0000 [1,252)
partition-0001 [252,503)
partition-0002 [503,754)
partition-0003 [754,1004)
~~~

thì khi restart, không tự ý đổi `gridSize=8`, partition names hay `fromInclusive/toExclusive` rồi giả định các checkpoint cũ có thể dùng lại chính xác. Khi có yêu cầu thay đổi topology, cần **chiến lược re-partitioning/migration** có kiểm soát và test riêng.

### 13.3. Không khôi phục bằng cách sửa bảng metadata thủ công

Không chạy:

~~~sql
-- ANTI-PATTERN: tuyệt đối không dùng như script sửa lỗi production.
UPDATE BATCH_STEP_EXECUTION
SET STATUS = 'COMPLETED'
WHERE STEP_EXECUTION_ID = :id;
~~~

Việc sửa trực tiếp status có thể phá liên hệ giữa `JobExecution`, `StepExecution`, version column, `ExecutionContext`, rollback và restart semantics. Dùng API vận hành/restart phù hợp Spring Batch version, có runbook kiểm tra stale executions và consistency.

### 13.4. Một test có worker cũ quay lại

Scenario:

~~~text
t0 Worker A nhận partition P1, bắt đầu ghi
t1 Manager/transport nghĩ A đã mất; P1 được giao lại cho B
t2 B hoàn tất và commit P1
t3 A khôi phục kết nối, cố commit hoặc gửi reply cũ
~~~

**Kỳ vọng:** output idempotent, metadata không bị completion reply cũ làm sai trạng thái, và quy tắc ownership/fencing bảo vệ các side effects không thể idempotent đơn giản.

Nếu cần fencing theo **epoch/lease token**, token phải được **kiểm tra trong chính thao tác ghi hoặc tại resource bị bảo vệ**; chỉ lưu token trong memory/metadata mà không kiểm tra ở business resource **không chặn được stale worker đang tiếp tục viết**. Đây là thiết kế tùy ứng dụng, **không phải bảo đảm mặc định** của `MessageChannelPartitionHandler`.

## 14. Broker semantics: test dưới giả định at-least-once

Nhiều hệ thống messaging được cấu hình để **có thể giao lại** khi consumer chết, timeout, ACK bị mất hoặc kết nối gián đoạn. Test phải thiết kế cho **possible duplicate delivery**, trừ khi đã chứng minh một contract mạnh hơn **xuyên suốt business DB/metadata/broker**.

### 14.1. Những tham số broker cần cố định trong test report

- Queue/topic durable hay transient, message persistent hay không.
- Consumer prefetch/batch size/parallel listener concurrency.
- Manual ACK/auto ACK, thời điểm ACK so với transaction commit.
- Redelivery/requeue, dead-letter và max attempts.
- Message TTL, retry delay, out-of-order contract.
- Correlation ID / request ID / execution ID và serializer version.
- Manager reply timeout, polling/aggregation strategy.

Nếu production dùng Kafka nhưng integration test chỉ dùng in-memory `DirectChannel`, test đó không bắt lỗi consumer group rebalances, offset commits hay partition ordering của Kafka. Nếu dùng RabbitMQ, phải test requeue/ACK/prefetch theo cách ứng dụng kết nối thật.

### 14.2. Kịch bản redelivery cần có

| Kịch bản | Cách inject trong staging | Oracle |
|---|---|---|
| Consumer chết **trước ACK** | Kill process sau nhận request | Broker redeliver theo policy; output không trùng |
| ACK bị mất do network | Cắt kết nối tại mốc có kiểm soát | Không mất work hoặc silently duplicate effect |
| Cùng request publish hai lần | Test harness publish duplicate với cùng execution ID | Không coi đó là hai logical partitions |
| Reply được gửi nhưng manager chưa nhận | Chặn reply channel | Manager timeout/reconcile theo metadata |
| Reply trễ sau retry | Giữ reply cũ, cho retry, rồi phát lại | Không overwrite attempt mới |
| Worker xử lý vượt SLA | Delay có kiểm soát | Không tự phát thêm worker chạy cùng work unit sai contract |
| Request poison payload | Gửi invalid execution metadata | Quarantine/DLQ có giám sát, không retry vô hạn |
| Broker restart | Restart container có kiểm soát | Durable messages theo config, worker reconnect có giới hạn |

**Tái phát message phải được thực hiện bằng công cụ/harness mà dự án kiểm soát**, không trực tiếp gửi `StepExecutionRequest` ngẫu nhiên tới broker production. Với request chứa metadata execution, nếu ID không tồn tại, worker đúng ra phải fail rõ ràng; đó là **negative test**, không phải dữ liệu để “làm nóng” listener.

### 14.3. Broker pause không giống worker crash

Khi broker outage:

- Worker có thể vẫn đang xử lý một chunk và commit business DB.
- Manager có thể không nhận completion message.
- Connection tới `JobRepository` có thể vẫn hoạt động.
- Sau reconnect, reply/request có thể được gửi lại.

Khi worker process crash:

- OS đóng sockets/DB connections; in-flight transactions có thể rollback.
- Message thường được requeue theo ACK semantics, nhưng thời điểm tùy broker.
- Các in-memory cursors, step-scoped beans và caches mất.

Test cả hai loại sự cố; đừng dùng `Thread.interrupt()` trong cùng JVM rồi báo “đã kiểm thử process crash”.

## 15. Kiểm thử transaction isolation, locks và connection pool

Remote partitioning đưa nhiều transaction lên một business database. Dù các partition đọc range không chồng lấn, worker vẫn có thể cập nhật **cùng aggregate row** hoặc unique index nóng.

### 15.1. Đo lock contention

~~~sql
SELECT a.pid,
       a.application_name,
       a.wait_event_type,
       a.wait_event,
       pg_blocking_pids(a.pid) AS blocker_pids,
       now() - a.xact_start AS xact_age
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY xact_age DESC NULLS LAST;
~~~

`xact_age` là tuổi transaction, không phải thời gian chờ lock chính xác. PostgreSQL có thể báo wait trên `transactionid` khi đợi row update, không nhất thiết có một dòng dễ thấy cho từng row lock trong `pg_locks`.

### 15.2. Đo pool budget theo process và cluster

Với `N` worker pod, mỗi pod có Hikari business pool `maximumPoolSize=P`, trần worker connections có thể mở gần:

\[
C_{\mathrm{workerBusiness,max}}\le N\times P
\]

Cộng thêm manager, metadata pool, các ứng dụng khác và rolling-deployment surge nếu trỏ vào cùng DB instance. **Số connection active không nhất thiết bằng số worker threads**: cursor reader có thể giữ connection và writer transaction có thể cần connection khác, nested `REQUIRES_NEW` có thể mượn thêm slot.

### 15.3. Các test tải có ý nghĩa

| Test | Chỉ số cần thu | Dấu hiệu bất thường |
|---|---|---|
| 1 worker, tuần tự | Baseline wall time, commit latency | SQL chậm ngay cả khi không tranh chấp |
| 2–4 workers | Speedup, DB CPU/IO, pool pending | Không tăng throughput dù còn CPU |
| 8–16 workers | Lock waits, Hikari acquisition p95, retry | Pending/lock tăng, throughput giảm |
| Hot key distribution | Blocker fan-in, transaction p95 | Partition input khác nhau nhưng writer chạm cùng row |
| Large chunk | Transaction duration, rollback cost | Lock dài, fail phải làm lại nhiều item |
| Small chunk | Commit count, metadata writes | Overhead nhiều commit khiến tổng runtime tăng |
| Worker burst after recovery | Reconnects, DB max_connections | Thundering herd làm DB outage kéo dài |

**Đừng biến performance SLO thành một assert quá ngắn ngay trong mọi unit test CI.** Functional E2E phải có deadline hữu hạn và correctness oracle; benchmark performance chạy trong môi trường có tài nguyên ổn định, ghi median/p95/variance.

### 15.4. Test non-thread-safe reader hoặc writer

Đặc biệt khi dùng **multi-threaded step** trong **một worker process**, `@StepScope` không tự tạo reader riêng cho từng chunk thread của **cùng `StepExecution`**. Nếu reader cursor stateful bị dùng chung, cần test race/readCount/idempotent output. Với remote partitioning, mỗi partition `StepExecution` có reader step-scoped riêng, nhưng trong **cùng worker** vẫn có thể có nhiều partition executions chạy song song qua consumer concurrency.

Không dùng kết quả “test với 1 worker pass” làm bằng chứng reader/writer thread-safe. Tạo test đủ đồng thời và phân tích cả bean scope, shared mutable fields, static caches và database write conflict.

## 16. Observability: đồng bộ timeline từ manager đến business commit

Một test thất bại cần trả lời: **request đi đâu, worker nào thực sự xử lý, business đã commit chưa, metadata ghi gì và manager vì sao kết luận như vậy?**

### 16.1. Các mốc nên ghi log

~~~text
manager.jobStarted
manager.partitionPlanCreated
manager.requestPublished
worker.requestReceived
worker.stepExecutionLoaded
worker.stepStarted
worker.firstChunkCommitted
worker.chunkRetried / chunkRolledBack
worker.stepMetadataUpdated
worker.replyPublished (nếu dùng)
manager.replyReceived / statusObserved
manager.partitionAggregationCompleted
manager.jobCompleted / jobFailed
business.reconciliationCompleted
~~~

Mỗi event cần timestamp và correlation fields. Với remote processes, **không trừ `System.nanoTime()` của hai JVM khác nhau**. Dùng trace context, đồng bộ wall clock ở mức phù hợp và đo duration nội bộ bằng monotonic clock cho mỗi process.

### 16.2. Tag và cardinality

| Trong time-series metric | Trong structured log/trace |
|---|---|
| `jobName`, `stepName`, `workerRole`, `poolName` | `jobExecutionId`, `stepExecutionId` |
| `status`, `errorCategory`, `brokerName` | `partitionName`, `requestId`, `messageId` |
| `result=completed/failed` | `snapshotKey`, `workerInstanceId`, attempt/epoch nếu có |

Không gắn mỗi `stepExecutionId` hoặc `requestId` làm label có retention dài cho mọi metric, vì cardinality tăng nhanh. Trong test logs có thể giữ đầy đủ ID nhưng phải ẩn dữ liệu nhạy cảm/PII.

### 16.3. Chỉ số nên đặt cạnh nhau

- `partition dispatch → worker start` p50/p95.
- `StepExecution` active/completed/failed/stopped counts.
- Chunk read/write/commit/rollback/retry/skip.
- End-to-end wall clock và slowest partition duration.
- Broker queue age/depth, redelivery count, consumer count, DLQ size.
- Hikari business/metadata active/idle/pending, connection acquire time.
- PostgreSQL CPU/IO/WAL, lock blockers, long transactions.
- **Business unique committed keys** và mismatch/reconciliation count.

Nếu throughput của worker tăng nhưng `business unique keys/s` không tăng, có thể worker đang retry, xử lý duplicate hoặc write bị `DO NOTHING`. **Một metric `writeCount` đẹp không đủ chứng minh job đúng.**

## 17. Các anti-pattern làm test xanh nhưng production sai

| Anti-pattern | Vì sao nguy hiểm | Thay thế |
|---|---|---|
| Chỉ gọi `Partitioner.partition(4)` | Không test transport/worker | Unit test + multi-process E2E riêng |
| Chỉ assert `JobExecution.COMPLETED` | Không tìm ra duplicate/missing data | So expected business key set + metadata |
| Dùng H2 để đại diện PostgreSQL | Khác transaction/SQL/locks/driver behavior | Testcontainers DB giống production |
| Manager và worker cùng context nhưng gọi là “remote” | Không test process isolation | Chạy ≥2 worker processes thật |
| `Thread.sleep` thay barrier | Flaky, không chắc đã có race | Latch/barrier, test hook và deadline |
| Mock ACK rồi coi business commit | ACK không bảo đảm DB/metadata atomic | Fault test quanh commit/reply/ACK |
| Đếm số reply thay tập execution IDs | Duplicate reply che partition thiếu | Correlation + shared repository |
| Thay `run.id` mỗi lần retry | Tạo JobInstance mới, mất ý nghĩa restart | Restart cùng identifying parameters |
| `ON CONFLICT DO NOTHING` cho mọi payload | Có thể giấu duplicate khác amount | Checksum/version/business validation |
| Kiểm tra `writeCount` thay committed keys | Retry/skip/DO NOTHING làm đếm lệch | SQL reconciliation theo business key |
| Dùng `@Transactional` trên test JUnit để bao worker threads | Transaction không tự qua process/thread | Commit fixture riêng, TransactionTemplate cho race |
| Test chỉ có 1 consumer | Không test parallelism/concurrency | Nhiều process, xác minh overlapping execution |
| Giết một thread rồi gọi là crash process | Socket/DB/broker cleanup khác nhau | Kill container/process thật |
| Không giới hạn timeout trong E2E | CI có thể treo vô hạn | Deadline có log/metadata artifacts |
| Sửa `BATCH_STEP_EXECUTION` để test “recover” | Phá repository invariants | Dùng lifecycle/restart API |
| Dọn shared DB giữa hai parallel tests | Lẫn fixture/metadata, flaky | Mỗi suite có DB/schema/snapshot isolation |
| Tắt unique/FK constraints để tăng tốc CI | Test không phản ánh correctness production | Giữ cùng constraints |

## 18. Runbook khi test remote partitioning timeout hoặc không hoàn tất

Một E2E test bị timeout không chỉ có nghĩa “worker quá chậm”. Có thể manager chưa tạo partition, broker chưa nhận message, worker không có bean đúng tên, metadata DB không dùng chung, transaction bị lock hoặc reply không về.

### Bước 1 — Đóng băng bằng chứng, chưa restart ngay

Ghi:

- `jobExecutionId`, các `stepExecutionId` và expected partition plan.
- Manager/worker image, role, version và broker configuration.
- Request messages/routing keys/queue depth, consumer count, redelivery count, DLQ.
- `JobRepository` state của manager và worker.
- Hikari active/idle/pending và PostgreSQL `pg_stat_activity`.
- Transaction/commit timeline, lỗi root cause và log/trace correlation.

**Đừng xóa queue hoặc chỉnh status metadata ngay** để “test xanh lại”: bạn có thể mất bằng chứng và không biết worker cũ còn đang ghi hay không.

### Bước 2 — Phân biệt chưa dispatch, chưa execute và chưa aggregate

| Quan sát | Điểm nghi vấn |
|---|---|
| Không có partition `StepExecution` trong repository | `Partitioner`/manager step chưa chạy hoặc lỗi trước lưu metadata |
| Có partition executions nhưng không có request | Outbound channel/manager/broker publish failure |
| Request nằm trong queue nhưng không có consumer | Worker chưa start, subscription/credentials/routing |
| Consumer nhận request nhưng không có StepExecution loaded | Mismatched repository/schema, ID, converter hoặc `StepLocator` |
| Worker `STARTED` mãi | Long processing, DB lock/pool, lost process, stale metadata |
| Worker `COMPLETED` nhưng manager vẫn đợi | Reply lost, aggregator/timeout/polling policy khác runtime |
| Manager `COMPLETED` nhưng output thiếu | Writer/skip/filter/partition coverage/idempotency bug |
| Output đúng nhưng manager `FAILED` | Metadata/reply/aggregation failure; cần repair/restart theo contract |

### Bước 3 — Tìm worker đang giữ business transaction

Với PostgreSQL và quyền quan sát phù hợp:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS xact_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_age DESC NULLS LAST;
~~~

Một worker có thể chờ row lock trong khi vẫn giữ JDBC connection. `Connection is not available, request timed out` của Hikari có thể là **hệ quả** của các connection bị giữ lâu, không phải nguyên nhân gốc. Phân biệt `Lock`, `IO`, WAL wait, CPU-bound processor, network timeout và broker lag.

### Bước 4 — Xác định failure boundary

Lỗi xảy ra **trước business commit**, **trong commit với kết quả không chắc chắn**, hay **sau commit trước metadata/reply**? Xem bảng output/ledger và transaction logs. Một `BatchUpdateException` hay connection reset không tự chứng minh business transaction chưa commit.

### Bước 5 — Bảo vệ trạng thái trước khi retry

Không phát lại cùng partition cho worker mới nếu worker cũ có thể còn làm side effect ngoài ý muốn. Theo kiến trúc, cần đợi timeout/stop/drain hoặc áp fencing/idempotency. Giữ immutable snapshot và partition plan; giới hạn số request retry đang in-flight.

### Bước 6 — Khởi động lại đúng JobInstance

Sử dụng Spring Batch restart/lifecycle API phù hợp version và quy trình của ứng dụng. Giữ identifying `JobParameters`; không tạo một `run.id` khác chỉ để bỏ qua metadata lỗi. Nếu mixed deployment, kiểm tra worker compatibility và quy tắc drain.

### Bước 7 — Đối soát lại toàn bộ dữ liệu

Trên test fixture:

~~~sql
SELECT count(*) AS rows,
       count(DISTINCT event_id) AS unique_ids,
       sum(amount_cents) AS total_amount_cents
FROM processed_events
WHERE snapshot_key = 'snap-test-001';
~~~

Sau đó chạy hai phép `EXCEPT` ở phần 9.2 để phát hiện cả row thiếu lẫn payload sai. Với pipeline biến đổi dữ liệu, so với expected transformed set.

### Bước 8 — Chốt kết luận và thêm regression test

Ghi root cause, failure boundary, cách tái hiện, ảnh hưởng tới output, timeout được áp ở đâu và cách sửa. Nếu lỗi chỉ xuất hiện sau 100 lần random CI, hãy biến nó thành **deterministic scenario** bằng barrier/fault injection, không chỉ tăng timeout rồi coi như xong.

## 19. Thiết kế CI quality gates theo mức độ tốn kém

Một bộ test remote partitioning đủ mạnh không nhất thiết phải chạy toàn bộ chaos tests trên mỗi thay đổi một dòng Java. Có thể phân tầng:

| Gate | Thời điểm | Yêu cầu tối thiểu |
|---|---|---|
| **G1: Unit** | Mỗi commit/PR | Range coverage, deterministic partition names, serializer/correlation policy |
| **G2: Worker DB** | Mỗi PR | Reader boundaries, writer idempotency, transaction rollback, no lost update |
| **G3: Multi-process E2E** | PR chính/merge | Manager + real broker + ≥2 workers + shared metadata, exact expected output |
| **G4: Recovery** | Merge/định kỳ | Worker kill trước/sau commit, duplicate reply, broker reconnect, restart |
| **G5: Staging resilience/perf** | Release/định kỳ | DB/broker outage, mixed versions, load skew, pool budgets, timeouts |

**Gate là đề xuất quy trình**, không phải chức năng Spring Batch tự có. Mỗi môi trường cần Docker/container runtime và quyền tương ứng. Nếu CI không cấp Docker, không “thay” Testcontainers bằng một mock rồi gọi đó là cùng một phép thử; hãy báo riêng những gates không thể chạy và giữ integration gate ở môi trường được hỗ trợ.

### 19.1. Phòng tránh test flaky

- Sử dụng **immutable fixtures** với ID và expected checksum cố định.
- Isolate DB/schema và broker queue per suite/run; không reuse `JobParameters` có thể đụng JobInstance cũ.
- Chờ đúng **condition** thay vì sleep duration không xác định.
- Có deadline hữu hạn cùng artifact logs khi timeout.
- Dọn worker/broker/DB resources trong teardown; đảm bảo không có process cũ còn tiêu thụ queue.
- Đừng đặt mọi performance threshold vào test chức năng trên runner CI dùng chung.
- Log seeds, versions, correlation IDs và fault injection points để test reproducible.
- Không vô hiệu hóa unique keys/transaction boundaries chỉ để test chạy nhanh.

### 19.2. Không làm production phụ thuộc test harness

Fault injection hooks, artificial delays và message replay endpoint cần **chỉ tồn tại hoặc được khóa chặt trong test/staging profile**, có xác thực nếu buộc phải tích hợp. Không tạo endpoint public cho phép kill worker, thay `StepExecution` hoặc phát lại message production.

## 20. Ma trận xác nhận cuối bài

| Nhóm | Test case bắt buộc | Mục tiêu |
|---|---|---|
| Partition plan | Non-overlap half-open ranges | Không trùng/thiếu |
| Partition plan | 0/1/gapped/overflow input | Boundary chính xác |
| Step scope | Hai partitions chạy song song | Reader state độc lập |
| Metadata | Worker đọc shared `StepExecution` | Không tạo execution sai |
| Message | Out-of-order reply | Correlate đúng execution |
| Message | Duplicate request/reply | Không giả success hoặc thêm business effect |
| Message | Reply stale từ previous attempt | Không ghi đè status mới |
| Message | Missing reply/consumer | Manager có deadline và recovery policy |
| Business | Duplicate same key/same payload | Idempotent |
| Business | Duplicate same key/different payload | Detect conflict theo contract |
| Business | Exactly expected key set | Không thiếu/trùng/sai payload |
| Transaction | Crash before commit | Rollback/restart đúng |
| Transaction | Commit outcome unknown | Reconcile/idempotent replay |
| Metadata | Business commit trước metadata/reply | Không double effect |
| Failure | Worker process kill | Broker recovery + JobRepository chính xác |
| Failure | Broker restart/network cut | Không mất work/treo vô hạn |
| Failure | DB unavailable/lock timeout | Bounded failure/retry |
| Restart | Same identifying parameters | Cùng JobInstance được tiếp tục |
| Restart | Partition names/context ổn định | Đọc đúng checkpoint |
| Ownership | Old worker quay lại sau redispatch | Fencing/idempotency hoặc không song song nguy hiểm |
| Concurrency | ≥2 worker instances xử lý overlap | Thực sự remote parallel |
| Resource | Pool/DB locks/queue under load | Không vượt budget |
| Performance | 1/2/4/8 workers trên cùng snapshot | Throughput + correctness + bottleneck |
| Deployment | Mixed image/serializer versions | Compatibility/drain an toàn |

**Một kịch bản được coi PASS** khi có đủ *expected metadata state*, *expected business data state* và *bounded outcome*, chứ không chỉ việc test method kết thúc không ném exception.

## 21. Checklist production / code review

- [ ] Có test `Partitioner` coverage, non-overlap, stable names và range boundary.
- [ ] Reader sử dụng `StepExecutionContext`/`JobParameters` của **đúng partition**, không dùng singleton mutable.
- [ ] Manager và workers trỏ vào **cùng `JobRepository`** theo đúng schema/version.
- [ ] Worker step name/`StepLocator`/message converter phù hợp contract thực tế.
- [ ] Có E2E manager + broker thật + ít nhất hai worker **processes riêng**.
- [ ] Test chứng minh worker processes thực sự xử lý đồng thời, không chỉ request được queue.
- [ ] Tách `JobInstance`, `JobExecution`, `StepExecution` và logical partition identity.
- [ ] Correlate reply bằng execution identity và loại bỏ duplicate/stale results.
- [ ] Timeout/recovery policy rõ khi worker chết hoặc reply bị mất; không wait vô hạn.
- [ ] Có test message redelivery/requeue/ACK semantics của broker đang dùng.
- [ ] Mỗi input snapshot bất biến, partition plan và reader checkpoint ổn định qua restart.
- [ ] Writer idempotent theo **business key**, không dùng `stepExecutionId` làm dedupe key duy nhất.
- [ ] Duplicate ID khác payload phải phát hiện hoặc xử lý theo version contract.
- [ ] Crash-before-commit và crash-after-commit được test **riêng**.
- [ ] Có phương án khi commit outcome unknown; không dựa vào exception để đoán dữ liệu.
- [ ] Có test stale worker tiếp tục sau redispatch, với fencing/ownership khi cần.
- [ ] Không sửa trực tiếp bảng `BATCH_*` để ép trạng thái thành công.
- [ ] Có timeout hữu hạn và test hooks/barriers để race deterministic.
- [ ] Có đối soát tập business keys và checksum sau **mỗi** kịch bản lỗi quan trọng.
- [ ] Theo dõi broker queue age, worker concurrency, pool pending, DB locks và slowest partition.
- [ ] Có kế hoạch mixed-version rolling deployment, worker drain và serializer compatibility.
- [ ] CI có gates phù hợp, biết rõ gates nào chưa chạy được trong môi trường hiện tại.

## 22. Bài tập thực hành

### Bài tập 1 — Bắt lỗi lệch một ID

Dùng fixture 1.003 event trong phần 4. Tạo `IdRangePartitioner` với bốn partition rồi cố tình đổi điều kiện reader từ `event_id < :toExclusive` thành `event_id <= :toExclusive`. Chạy worker integration test và xác minh:

1. Một số boundary ID bị đọc ở hai partition.
2. Unique key có thể làm output không nhân đôi, nhưng read/write attempts có thể tăng.
3. Test **partition coverage/exclusivity** phải fail, kể cả khi `processed_events` cuối cùng vẫn có 1.003 row nhờ `DO NOTHING`.

### Bài tập 2 — Thử phản hồi sai thứ tự

Lập ba test execution IDs cho P0, P1, P2; fake replies đến P2, P0, P1. Assert aggregator trả về đúng tập hoàn tất. Lặp lại với P0, P0, P1 và xác nhận **P2 vẫn chưa hoàn tất**. Sau đó cho reply `FAILED` và reply `COMPLETED` của cùng một execution; kiểm tra policy không tự biến job thành success.

### Bài tập 3 — Xây E2E nhiều process

Dùng PostgreSQL + RabbitMQ Testcontainers, một manager và hai worker Java processes/container riêng. Cấu hình shared `JobRepository`, worker step, request/reply channels và `StepExecutionRequestHandler` đúng theo Spring Batch Integration version. Launch job với `snapshotKey="snap-test-001"`, chứng minh ít nhất hai worker instances xử lý những partitions khác nhau và đối soát `EXCEPT` hai chiều bằng zero mismatch.

### Bài tập 4 — Worker chết trước commit

Tiêm lỗi có kiểm soát khi worker đã đọc một chunk nhưng chưa commit. Kill process, để broker/manager phát hiện lỗi theo policy rồi restart **cùng JobInstance**. So expected key set, `BATCH_STEP_EXECUTION` status, rollback/retry counters và absence của ghost writes.

### Bài tập 5 — Worker chết sau business commit

Trên topology business DB và metadata/broker có boundary độc lập, cho writer commit xong rồi crash trước metadata/reply. Kích hoạt redelivery/restart. Thử trước với writer thiếu unique business key để thấy nguy cơ double effect trong staging, sau đó bổ sung idempotency guard và xác minh output đúng.

### Bài tập 6 — Reply trễ từ execution cũ

Giữ một reply từ attempt trước, cho manager/worker tiếp tục attempt mới, rồi phát lại reply cũ. Assert metadata trạng thái attempt mới không bị ghi đè và manager không đếm trùng partition. Ghi rõ logic correlation lấy từ **shared repository** chứ không chỉ tin trường status trên message.

### Bài tập 7 — Long-running hot key

Tạo workload mà 80% events thuộc một account và writer cập nhật aggregate row. So sánh 1/2/4/8 worker; đo PostgreSQL `pg_blocking_pids`, Hikari pending, throughput và retry. Thiết kế lại workflow thành append-only events rồi aggregate theo account; xác minh correctness và measured improvement.

### Bài tập 8 — Scale workers và startup

So 2 worker luôn chạy với scale-to-zero rồi tăng lên 8 worker pod. Đo scheduler → consumer ready → first chunk commit → job complete, cùng DB connection budget. Một job nhỏ có thể có steady throughput tốt nhưng wall-clock kém do startup; giải thích trade-off cho SLA cụ thể.

### Bài tập 9 — Đối soát dữ liệu thay vì đếm row

Chuẩn bị expected IDs 1..1003; cho một lỗi test làm worker xử lý ID 251 hai lần và bỏ ID 252. Nếu output table không có unique constraint trong **bài test staging có kiểm soát**, tổng số row có thể vẫn 1003. Viết assertions so exact key set, multiplicity và payload để phát hiện lỗi. Trong cấu hình production vẫn giữ unique constraints.

### Bài tập 10 — Viết runbook test timeout

Giả sử manager publish 12 requests, `JobRepository` có 12 worker executions nhưng chỉ 11 `COMPLETED`, queue hết pending, worker pod cuối bị kill và manager đợi reply mãi. Viết thứ tự chẩn đoán từ broker logs, StepExecution state, business DB commit và owner cũ; mô tả recovery/restart đúng dữ liệu và ngưỡng cảnh báo.

**Câu hỏi tự kiểm tra:** Vì sao `JobExecution.COMPLETED` chưa đủ chứng minh business output đúng? Khác biệt giữa remote partitioning và remote chunking là gì? Vì sao `StepExecutionRequest` phải trỏ tới execution đã tồn tại trong shared repository? `gridSize=16` có bảo đảm 16 worker pod chạy đồng thời không? Vì sao `ON CONFLICT DO NOTHING` vừa hỗ trợ idempotency vừa có thể che payload sai? Khi nào lỗi commit khiến client không biết transaction đã thành công chưa? Vì sao không dùng `Thread.sleep` để chứng minh race? Vì sao restart cần cùng identifying parameters và partition plan? Reply trễ nên được xử lý dựa trên execution identity nào? Làm cách nào test một worker thật sự chết thay vì chỉ bị interrupt?

## 23. Tổng kết

**Test remote partitioning** cần nhìn Spring Batch như một **hệ thống phân tán có transaction boundaries**, không chỉ một step có nhiều thread. Manager tạo partition `StepExecution`, broker vận chuyển request/reply, worker xử lý dữ liệu, `JobRepository` lưu metadata và business database nhận kết quả. Lỗi ở bất kỳ ranh giới nào cũng có thể tạo **request/reply trễ hoặc trùng, execution chưa được cập nhật, retry sai thời điểm và business side effect lặp**.

Một chiến lược test vững chắc đi từ **unit `Partitioner` → worker database integration → broker/metadata integration → E2E nhiều process → fault injection/restart**. Ở mỗi tầng, phải kiểm tra **đúng tập business keys, trạng thái từng execution, bounded timeout, correlation và idempotency**. Có thể có nhiều delivery attempts nhưng chỉ một business effect hợp lệ; có thể mất một reply nhưng không được mất dữ liệu hoặc báo thành công giả.

**Tiêu chí cuối cùng không phải “16 partition chạy xong” mà là: sau concurrency, crash, redelivery và restart, toàn bộ dữ liệu hợp lệ vẫn chính xác, execution state có thể giải thích và hệ thống phục hồi theo quy trình đã được kiểm chứng.**
