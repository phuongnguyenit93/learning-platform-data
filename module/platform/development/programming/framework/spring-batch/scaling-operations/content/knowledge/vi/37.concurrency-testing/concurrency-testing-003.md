# Test local partitioning

Trong Spring Batch, **local partitioning** chia một bước xử lý dữ liệu thành nhiều **worker StepExecution** chạy trên các thread khác nhau **trong cùng một JVM**. Manager step lập danh sách partition, một `PartitionHandler` phân phối công việc qua `TaskExecutor`, và mỗi worker step nhận `ExecutionContext` riêng để đọc/ghi phần dữ liệu được giao. Mô hình này giúp tận dụng nhiều CPU, chồng lấp thời gian I/O và xử lý những nguồn lớn; đồng thời nó tạo ra rủi ro **phân vùng bị trùng hoặc thiếu, bean state bị chia sẻ sai, tranh chấp database, retry/restart khó đoán và những bài test “xanh” dù thực tế chỉ chạy tuần tự**.

Bài học thuộc chương **Testing concurrency** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán phù hợp; đo bottleneck, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế. Nội dung tập trung vào **kiểm thử local partitioning có bằng chứng**: từ partition ranges, concurrency thực, isolation của `ExecutionContext`, JDBC transactions và output tới failure injection, restart và kiểm thử tải.

> **Nguyên tắc:** một `JobExecution` có `BatchStatus.COMPLETED` **không tự chứng minh** mọi record đã được xử lý đúng một lần, các partition không chồng nhau hoặc thực sự có nhiều worker chạy cùng lúc. Kiểm thử concurrency phải phân biệt **tính đúng đắn dữ liệu**, **mức song song thực tế** và **khả năng phục hồi**; cả ba cần assertion riêng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `PartitionStep`, `Partitioner`, `TaskExecutorPartitionHandler`, `TaskExecutor`, worker `StepExecution` và `ExecutionContext`.
2. Tạo fixture dữ liệu và partition theo khoảng khóa **nửa mở** `[startInclusive, endExclusive)` với định danh ổn định.
3. Kiểm tra partition **không overlap**, **không bỏ sót**, đúng phạm vi tenant/batch và hoạt động với empty/sparse inputs.
4. Phân biệt `gridSize`/số partitions với **số thread thực sự đồng thời**; dùng `CountDownLatch`/`CyclicBarrier` để chứng minh concurrency.
5. Tạo worker reader `@StepScope`, tránh chia sẻ `ItemStream` có mutable cursor giữa partitions.
6. Kiểm tra `JobRepository` ghi đúng số `StepExecution`, counts, status và khả năng restart.
7. Dùng idempotent writer, unique business keys và kiểm tra dữ liệu theo **tập khóa và giá trị**, không chỉ `COUNT(*)`.
8. Tiêm lỗi chính xác ở một partition, chunk transaction hoặc trước/sau commit để kiểm tra rollback/restart.
9. Đo lock contention, connection pool, executor queue, throughput, skew và hiệu quả tăng `gridSize`.
10. Phân biệt test local partitioning với test multi-threaded step, parallel flows và remote partitioning.

**Tình huống xuyên suốt:** một job import 40.000 giao dịch của `batchKey=daily-settlement-2026-11-26` từ bảng staging bất biến. Manager tạo bốn partition theo `record_id` và dùng bốn thread. Worker đọc dữ liệu trong khoảng được giao, chuẩn hóa số tiền rồi ghi vào PostgreSQL. Bộ test phải chứng minh **mỗi record hợp lệ thuộc đúng một partition, tất cả output đúng, và restart một partition lỗi không làm tăng tác động nghiệp vụ**.

## 2. Kiến trúc local partitioning cần kiểm thử

~~~mermaid
flowchart TB
    J["JobExecution"] --> M["Manager PartitionStep"]
    M --> P["Partitioner / ExecutionContext ranges"]
    M --> H["TaskExecutorPartitionHandler"]
    H --> E["TaskExecutor: bounded threads"]
    E --> W0["workerStep:partition0"]
    E --> W1["workerStep:partition1"]
    E --> W2["workerStep:partition2"]
    E --> W3["workerStep:partition3"]
    W0 --> DB[("Business database")]
    W1 --> DB
    W2 --> DB
    W3 --> DB
    W0 -. "StepExecution metadata" .-> JR[("JobRepository")]
    W1 -. "StepExecution metadata" .-> JR
    W2 -. "StepExecution metadata" .-> JR
    W3 -. "StepExecution metadata" .-> JR
    M -. "Manager metadata" .-> JR
~~~

Trong local partitioning:

- **Manager step** điều phối; nó không nhất thiết trực tiếp đọc từng item nghiệp vụ.
- **Partitioner** trả về `Map<String, ExecutionContext>`. Mỗi key định danh một partition, mỗi context chứa phạm vi dữ liệu worker sẽ nhận.
- **PartitionHandler** chạy các worker steps; `TaskExecutorPartitionHandler` dùng local executor để gọi worker steps trong **cùng JVM**.
- **Worker step** vẫn là Spring Batch step bình thường với reader, processor, writer, transaction/chunk, listener, skip/retry và metadata.
- **JobRepository** quản lý manager và worker `StepExecution`, trạng thái/counters để hỗ trợ vận hành và restart.

**Đừng gọi mô hình này là remote partitioning:** local không cần broker/worker JVM khác. Với remote partitioning cần kiểm thêm transport, request/reply correlation, lease và node crash. Ở local partitioning, thread safety, shared datasource, executor và process crash là trọng tâm.

## 3. Phân biệt các loại concurrency để không test nhầm

| Mô hình | Đơn vị song song | Reader ở đâu? | Test đặc trưng |
| --- | --- | --- | --- |
| **Multi-threaded step** | Nhiều chunk của **một StepExecution** | Có thể là một reader được gọi từ nhiều thread | Shared reader/processor/writer thread safety, chunk order |
| **Local partitioning** | Nhiều **worker StepExecution** | Mỗi partition có reader/state riêng theo thiết kế | Partition boundaries, `ExecutionContext`, concurrency, restart từng worker |
| **Parallel steps/flows** | Các steps/flows khác nhau | Theo từng step | Branch order, dependency, data races giữa flows |
| **Remote partitioning** | Worker steps ở nhiều JVM/nodes | Worker JVM | Broker, failover, correlation, duplicate dispatch |
| **Remote chunking** | Chunks được phát qua middleware | Manager giữ reader; worker process/write | Request/reply, ACK, duplicate chunks và remote worker |

Trong local partitioning, `Step` có thể là một **bean cấu hình dùng chung**, nhưng mỗi worker thực thi một `StepExecution` khác nhau. Một reader singleton có cursor mutable **không trở thành an toàn chỉ vì nó được sử dụng trong partitioned step**. Dùng `@StepScope` hoặc factory tạo reader riêng per worker execution, và kiểm tra chính xác số instance/lifecycle trong integration test.

## 4. Ba lớp bằng chứng bắt buộc

| Lớp | Assertion cần có | Assertion không đủ |
| --- | --- | --- |
| **Partition correctness** | Union ranges = toàn bộ source snapshot; không overlap/gap; đúng tenant/version | `partitioner.partition(4).size() == 4` |
| **Actual concurrency** | Ít nhất 2 worker cùng có mặt trước barrier; thread IDs/name và max active phù hợp | Executor có `corePoolSize=4` hoặc `gridSize=4` |
| **Business correctness** | Expected key set/value = output; không duplicate/extra; status/count hợp lệ | Job `COMPLETED` hoặc output `COUNT(*)` đúng |
| **Recovery correctness** | Sau fault/restart: work không mất, effects không nhân đôi, failed partitions có outcome đúng | Chạy job lần hai không ném exception |
| **Resource safety** | DB pool, executor queue, locks, latency không vượt giới hạn | CPU cao hoặc throughput tăng một lần |

Mỗi bài test phải chỉ rõ **nó chứng minh gì và không chứng minh gì**. Ví dụ test `CountDownLatch` xác nhận concurrency **không** thay thế SQL reconciliation; SQL reconciliation xác nhận output cuối **không** chứng minh đã chạy song song.

## 5. Chuẩn bị fixture bất biến và expected outcomes

Giả sử nguồn là PostgreSQL staging:

~~~sql
CREATE TABLE staged_payment (
    batch_key    VARCHAR(120) NOT NULL,
    record_id    BIGINT NOT NULL,
    tenant_id    VARCHAR(100) NOT NULL,
    amount       NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (batch_key, record_id)
);

CREATE TABLE normalized_payment (
    batch_key    VARCHAR(120) NOT NULL,
    record_id    BIGINT NOT NULL,
    tenant_id    VARCHAR(100) NOT NULL,
    net_amount   NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (batch_key, record_id)
);

CREATE INDEX idx_staged_payment_range
    ON staged_payment (batch_key, record_id);
~~~

**Data fixture cần chứa nhiều kiểu phân bố:**

1. **Dãy liên tục**: 0..39.999 để nhìn rõ union và các ranh giới.
2. **Dãy có lỗ**: IDs 1, 2, 9, 100, 10.000 để chứng minh range query không cần ID liên tục.
3. **Nguồn rỗng** và chỉ một record.
4. **Mốc biên**: ID đúng `startInclusive`, ngay trước `endExclusive` và đúng `endExclusive`.
5. **Hai tenants/batches** dùng cùng record IDs để phát hiện thiếu predicate về batch/tenant.
6. **Input bất biến**: snapshot `batch_key` không được append/thay giữa test và restart.
7. **Giá trị kiểm tra được**: expected net amount có thể tính độc lập với processor để tránh test lập lại đúng chính bug.

**Không dùng random seed không cố định trong correctness test**. Khi muốn stress/probabilistic test, lưu seed và fixture manifest để tái hiện failure. Mọi test nên cleanup theo `batchKey` riêng, không dùng `DELETE FROM output` toàn hệ khi nhiều tests chạy song song.

## 6. Dùng khoảng nửa mở cho partition

Một cách chia dễ kiểm chứng là `[startInclusive, endExclusive)`:

~~~text
Source IDs: 0 ... 19
gridSize = 4

partition0: [0, 5)    -> 0..4
partition1: [5, 10)   -> 5..9
partition2: [10, 15)  -> 10..14
partition3: [15, 20)  -> 15..19
~~~

So với hai đầu inclusive, khoảng nửa mở tránh việc record tại boundary xuất hiện ở hai partitions khi một người viết `BETWEEN start AND end` còn người khác dùng `start=end+1`.

Predicate đọc **phải khớp** hợp đồng partition:

~~~sql
SELECT record_id, tenant_id, amount
FROM staged_payment
WHERE batch_key = :batchKey
  AND record_id >= :startInclusive
  AND record_id <  :endExclusive
ORDER BY record_id;
~~~

Đừng vô tình dùng `BETWEEN :startInclusive AND :endExclusive`: PostgreSQL `BETWEEN` bao gồm cả hai biên, gây overlap. Nếu có tenant isolation, cần thêm `tenant_id=:tenantId` hoặc đảm bảo `batchKey` đã là namespace được xác thực; test phải chứng minh record tenant khác không rò vào output.

## 7. Ví dụ Partitioner theo range trong Spring Batch 5.x

Ví dụ Java 17+ với cận đã chốt từ **immutable source snapshot**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

final class HalfOpenRangePartitioner implements Partitioner {
    private final long minInclusive;
    private final long maxExclusive;
    private final String batchKey;

    HalfOpenRangePartitioner(long minInclusive,
                             long maxExclusive,
                             String batchKey) {
        if (minInclusive > maxExclusive) {
            throw new IllegalArgumentException("Invalid bounds");
        }
        this.minInclusive = minInclusive;
        this.maxExclusive = maxExclusive;
        this.batchKey = batchKey;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be > 0");
        }
        long total = Math.subtractExact(maxExclusive, minInclusive);
        if (total == 0) {
            // Hợp đồng test: không tạo empty partitions.
            // Manager workflow phải xử lý empty input rõ ràng.
            return Map.of();
        }

        int count = (int) Math.min((long) gridSize, total);
        long base = total / count;
        long remainder = total % count;
        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long start = minInclusive;

        for (int i = 0; i < count; i++) {
            long size = base + (i < remainder ? 1 : 0);
            long end = Math.addExact(start, size);
            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("batchKey", batchKey);
            ctx.putLong("startInclusive", start);
            ctx.putLong("endExclusive", end);
            result.put("partition" + i, ctx);
            start = end;
        }

        if (start != maxExclusive) {
            throw new IllegalStateException("Partition coverage mismatch");
        }
        return result;
    }
}
~~~

**Điều kiện:**

- `maxExclusive` là cận **loại trừ**, phải lấy đúng từ snapshot. Ví dụ nguồn có ID cao nhất `39_999` thì `maxExclusive=40_000`, với kiểm tra overflow.
- `Math.subtractExact`/`Math.addExact` giúp phát hiện overflow arithmetic; với miền ID quá lớn hoặc `Long.MAX_VALUE` cần phương án tránh `max+1` tràn số.
- `gridSize` là **hint/budget chia**, không nhất thiết số partitions trả về bằng đúng `gridSize`. Khi khoảng chỉ có 2 đơn vị mà gridSize=8, ví dụ trả 2 partitions.
- Map key `partition0`, `partition1`... phải **ổn định qua restart** cùng JobInstance và input snapshot. Không dùng UUID hoặc thời gian hiện tại làm partition key.
- Với **sparse IDs**, có partition chứa **0 record** dù khoảng ID không rỗng; điều này hợp lệ nếu partitioning theo range, nhưng ảnh hưởng cân bằng tải.
- Trả `Map.of()` cho nguồn rỗng là **policy của ví dụ**, không mặc định framework sẽ tạo một step COMPLETED như mong muốn; phải có integration test empty-work case, hoặc chọn một explicit no-op flow.

## 8. Unit test các bất biến của partitioner

Kiểm tra ít nhất bốn tính chất:

1. Mỗi khoảng hợp lệ: `start < end`.
2. Sắp theo start, các khoảng sát nhau: `end(i) == start(i+1)`.
3. Biên đầu/cuối: `start(0)==min` và `end(last)==maxExclusive`.
4. Tổng độ dài các khoảng bằng `maxExclusive-minInclusive`; kết quả độc lập với lịch chạy threads.

~~~java
@Test
void partitionRangesAreDisjointAndCoverWholeDomain() {
    Map<String, ExecutionContext> partitions =
            new HalfOpenRangePartitioner(0, 23, "batch-A")
                    .partition(4);

    List<ExecutionContext> ordered = partitions.values().stream()
            .sorted(Comparator.comparingLong(
                    c -> c.getLong("startInclusive")))
            .toList();

    assertEquals(4, ordered.size());
    assertEquals(0, ordered.get(0).getLong("startInclusive"));
    assertEquals(23, ordered.get(3).getLong("endExclusive"));

    long sum = 0;
    long previousEnd = 0;
    for (ExecutionContext ctx : ordered) {
        long start = ctx.getLong("startInclusive");
        long end = ctx.getLong("endExclusive");
        assertEquals(previousEnd, start);
        assertTrue(start < end);
        sum += end - start;
        previousEnd = end;
        assertEquals("batch-A", ctx.getString("batchKey"));
    }
    assertEquals(23, sum);
}
~~~

### Ma trận edge cases

| Input | `gridSize` | Kỳ vọng |
| --- | ---: | --- |
| `[0,20)` | 4 | 4 ranges không overlap, đủ 20 IDs |
| `[0,23)` | 4 | Phân đều 6,6,6,5; không mất 3 IDs lẻ |
| `[10,11)` | 8 | 1 non-empty range |
| `[10,10)` | 4 | Empty-work policy rõ, không crash |
| `[100,150)` | 1 | Một range, không chứng minh concurrency |
| `[0,100)` | 0 | Reject cấu hình sai |
| Sparse IDs [1,9,100] | 4 | Range union đầy đủ; reader chỉ chọn IDs có thực |
| IDs gần giới hạn long | 4 | Không overflow khi tạo cận exclusive |
| Hai tenants cùng IDs | 4 | Predicate không cross-tenant |

Nếu dùng **partition theo file list** thay range, thay tính chất coverage của các khoảng bằng **mỗi immutable file identity xuất hiện đúng một lần**, không có file ngoài manifest, không có cùng file ở hai `ExecutionContext`. Không cần giả định mọi partition chứa số file bằng nhau.

## 9. Property-based test giúp tìm lỗi biên khó thấy

Viết generator tạo `minInclusive`, `maxExclusive` và `gridSize` hợp lệ, rồi kiểm các bất biến `start/end/coverage` trên hàng trăm cấu hình. Đối với miền nhỏ, có thể xây **tập expected IDs** để kiểm một cách độc lập thay vì chỉ cộng kích thước:

~~~text
Expected = { min, min+1, ..., maxExclusive-1 }
Actual = union(IDs của mọi partition)

Assert Actual == Expected.
Assert mỗi ID có frequency == 1.
~~~

Ví dụ seed 42, miền từ -50 đến 150, gridSize từ 1 đến 32. Cần đảm bảo generator tránh `Long` overflow trước khi truyền vào partitioner. **Property test của Partitioner không thay integration test query reader**, vì SQL có thể dùng nhầm điều kiện inclusive hoặc thiếu batch predicate dù partitioner đúng.

## 10. Tạo một mô hình kiểm thử có expected output độc lập

Giả sử quy tắc nghiệp vụ đơn giản: `netAmount = amount * 0.95` làm tròn 2 số thập phân theo `HALF_UP`, nhưng expected values được tính từ **fixture/SQL độc lập** trong test để tránh chỉ copy/paste logic processor.

~~~text
Staging:
 (batch-A, id=0, tenant=A, amount=100.00)
 (batch-A, id=1, tenant=A, amount=200.00)
 (batch-A, id=9, tenant=B, amount=300.00)
 (batch-B, id=1, tenant=X, amount=999.00)

Output expected chỉ batch-A:
 id 0 = 95.00
 id 1 = 190.00
 id 9 = 285.00

Không có id 1 của batch-B trong output batch-A.
~~~

Khi chạy test concurrency, không so sánh **thứ tự commit của partitions** với thứ tự ID. Các worker có thể hoàn thành theo lịch tùy ý; chỉ yêu cầu **set/key/value đúng**. Nếu nghiệp vụ thật cần thứ tự, phải thiết kế một serialization/ordering contract riêng, không áp đặt giả lên local partitioning.

## 11. Worker reader phải riêng cho mỗi StepExecution

Với partition theo khoảng ID, một reader `@StepScope` nhận cận từ `stepExecutionContext` và giữ cursor/state riêng theo worker.

~~~java
record PaymentRow(
        String batchKey,
        long recordId,
        String tenantId,
        BigDecimal amount) {}

record PaymentResult(
        String batchKey,
        long recordId,
        String tenantId,
        BigDecimal netAmount) {}

@Bean
@StepScope
JdbcCursorItemReader<PaymentRow> paymentReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['startInclusive']}") Long start,
        @Value("#{stepExecutionContext['endExclusive']}") Long end) {

    return new JdbcCursorItemReaderBuilder<PaymentRow>()
            .name("paymentReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT batch_key, record_id, tenant_id, amount
                    FROM staged_payment
                    WHERE batch_key = ?
                      AND record_id >= ?
                      AND record_id < ?
                    ORDER BY record_id
                    """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, batchKey);
                ps.setLong(2, start);
                ps.setLong(3, end);
            })
            .rowMapper((rs, rowNum) -> new PaymentRow(
                    rs.getString("batch_key"),
                    rs.getLong("record_id"),
                    rs.getString("tenant_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

**Cách đọc mẫu:**

- `@StepScope` tạo reader per worker `StepExecution`, tránh chia sẻ mutable cursor giữa các worker.
- Cận lấy từ `ExecutionContext` **khác nhau** theo partition, không lấy từ một biến static hay một singleton mutable.
- Reader lưu state vào metadata khi framework mở/cập nhật `ItemStream`; tên reader phải không gây xung đột key state **trong cùng StepExecution**. Các worker StepExecutions có context riêng nên dùng cùng tên reader nhất quán thường phù hợp.
- `ORDER BY record_id` giúp thứ tự ổn định **trong partition** nếu snapshot bất biến; nó không ép thứ tự completion giữa partitions.
- `JdbcCursorItemReader` giữ JDBC cursor/connection trong lifecycle, vì thế pool và connection lifetime phải được đo. Nếu datasource không thể giữ nhiều cursor lâu, cân nhắc paging reader với sort key unique, nhưng vẫn cần snapshot consistency.
- Các null/cận sai trong context phải **fail sớm**, không mặc định `start=0`/`end=MAX` làm nhiều worker cùng đọc toàn bộ bảng.

**Cảnh báo:** `@StepScope` không tự bảo vệ writer singleton có state hoặc service mutable khác. Nó chỉ quản lý bean scope; race vẫn có thể xảy ra ở processor, caches, counters, formatter không thread-safe và downstream.

## 12. Processor thuần và writer chống replay

Ở ví dụ dưới, processor không có state thay đổi giữa các item:

~~~java
@Bean
ItemProcessor<PaymentRow, PaymentResult> normalizePayment() {
    return row -> new PaymentResult(
            row.batchKey(),
            row.recordId(),
            row.tenantId(),
            row.amount()
                    .multiply(new BigDecimal("0.95"))
                    .setScale(2, RoundingMode.HALF_UP));
}
~~~

Writer có **business key** `(batch_key, record_id)`, cho phép replay mà không tạo hai rows:

~~~java
@Bean
JdbcBatchItemWriter<PaymentResult> paymentWriter(DataSource ds) {
    return new JdbcBatchItemWriterBuilder<PaymentResult>()
            .dataSource(ds)
            .sql("""
                    INSERT INTO normalized_payment(
                        batch_key, record_id, tenant_id, net_amount)
                    VALUES (:batchKey, :recordId, :tenantId, :netAmount)
                    ON CONFLICT (batch_key, record_id) DO NOTHING
                    """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("batchKey", item.batchKey())
                            .addValue("recordId", item.recordId())
                            .addValue("tenantId", item.tenantId())
                            .addValue("netAmount", item.netAmount()))
            .assertUpdates(false)
            .build();
}
~~~

**Giới hạn quan trọng:** `ON CONFLICT DO NOTHING` chỉ ngăn tạo **dòng trùng**, không phát hiện cùng key mang `net_amount` khác. Production cần xác minh giá trị/tenant/rule version khi conflict, hoặc dùng một **idempotency ledger** có payload hash và policy fail với mismatch. Nếu nghiệp vụ dùng `balance = balance + delta`, unique row ở output không tự chống cộng hai lần; cần ghi operation ledger và hiệu ứng trong **cùng transaction**.

Test phải kiểm **source key set, output key set và netAmount**. Khi writer dedup, hai partitions đọc trùng có thể vẫn cho `COUNT(*)` đầu ra đúng — vì vậy nên có thêm **read/processor visit audit trong test happy-path không retry** để phát hiện overlap.

## 13. Cấu hình worker StepBuilder trong Spring Batch 5.x

Ví dụ một worker step chunk-oriented sử dụng `JobRepository` và business transaction manager:

~~~java
@Bean
Step workerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentRow> paymentReader,
        ItemProcessor<PaymentRow, PaymentResult> processor,
        ItemWriter<PaymentResult> writer) {

    return new StepBuilder("workerStep", jobRepository)
            .<PaymentRow, PaymentResult>chunk(200, transactionManager)
            .reader(paymentReader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Trong Java config thực, `paymentReader` thường là một **scoped proxy** do Spring quản lý, còn instance reader thật được tạo trong worker execution. Các imports, datasource, Boot/Spring Batch configuration và transaction manager phải phù hợp phiên bản dùng.

**Không mặc định sử dụng `.taskExecutor(...)` trên chính worker step** nếu mục tiêu test **local partitioning**. Làm vậy sẽ tạo thêm cấp multi-threaded chunk processing trong từng partition, khiến tính toán concurrency, reader thread safety và transaction ordering phức tạp hơn. Trước tiên test **một worker step tuần tự bên trong mỗi partition**, nhưng nhiều worker StepExecutions chạy trên các thread khác nhau.

## 14. ThreadPoolTaskExecutor và TaskExecutorPartitionHandler

`gridSize` biểu thị số partition được yêu cầu/tạo theo partitioner; `corePoolSize` và `maxPoolSize` xác định khả năng thực thi đồng thời. Không thể suy ra có bốn worker chạy song song chỉ vì `gridSize(4)`.

~~~java
@Bean
ThreadPoolTaskExecutor localPartitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(4);
    executor.setThreadNamePrefix("local-partition-");
    executor.initialize();
    return executor;
}

@Bean
TaskExecutorPartitionHandler localPartitionHandler(
        @Qualifier("workerStep") Step worker,
        @Qualifier("localPartitionExecutor") TaskExecutor executor) {

    TaskExecutorPartitionHandler handler =
            new TaskExecutorPartitionHandler();
    handler.setStep(worker);
    handler.setTaskExecutor(executor);
    handler.setGridSize(4);
    return handler;
}
~~~

Với nhiều worker steps hơn capacity của thread pool, một số partitions sẽ **xếp hàng**, không biến mất. `TaskExecutorPartitionHandler` dùng local executor; khi request tasks vượt thread/queue giới hạn, submission có thể bị **rejected** theo policy của executor. Test cần đo rejection và failure status, không assume mọi partition sẽ luôn bắt đầu.

### Manager PartitionStep

~~~java
@Bean
Step managerStep(
        JobRepository jobRepository,
        Partitioner immutableRangePartitioner,
        TaskExecutorPartitionHandler localPartitionHandler) {

    return new StepBuilder("managerStep", jobRepository)
            .partitioner("workerStep", immutableRangePartitioner)
            .partitionHandler(localPartitionHandler)
            .build();
}

@Bean
Job localPartitionJob(JobRepository repository,
                      @Qualifier("managerStep") Step manager) {
    return new JobBuilder("localPartitionJob", repository)
            .start(manager)
            .build();
}
~~~

`immutableRangePartitioner` phải được cấu hình bằng **snapshot bounds và batchKey đã chốt**, không tính lại `MIN/MAX` tùy ý từ bảng đang thay đổi khi restart. Có thể sử dụng `@JobScope` để nhận JobParameters/snapshot manifest, nhưng cần xét scope trong luồng manager và bảo đảm partition names/context **ổn định**.

**Các code block là bộ khung để học/test Spring Batch 5.x, không phải một project copy-paste đầy đủ**: các bean nguồn, imports, wiring, transaction manager, package, dependencies và test fixture cần được cung cấp rõ trong ứng dụng.

## 15. Kiểm thử trạng thái và metadata worker StepExecution

Khi job hoàn tất, nên kiểm:

1. `JobExecution.getStatus()==BatchStatus.COMPLETED` và `ExitStatus` hợp lệ.
2. Có đúng các worker `StepExecution` mà partitioner đã tạo; không chỉ manager `StepExecution`.
3. Worker step names chứa partition identity đúng, ví dụ `workerStep:partition0`.
4. Mỗi worker `StepExecution` có `ExecutionContext` chứa `batchKey/startInclusive/endExclusive` mong đợi.
5. `readCount`, `writeCount`, `filterCount`, `readSkipCount/processSkipCount/writeSkipCount` phù hợp từng partition và tổng job.
6. Input/output theo khóa thực tế đúng; không có record ngoài snapshot/tenant.
7. Mọi worker có status đúng sau normal run; khi fault injection, failed partition phải hiện diện trong metadata/diagnostics.

**Đừng lấy manager `StepExecution.readCount` rồi so sánh với 40.000**. Manager là step điều phối, dữ liệu read/write nghiệp vụ nằm ở các **worker StepExecutions**. Bộ đếm tổng cần aggregate đúng các worker theo tên/partition và làm rõ cơ chế retry/skip/filter.

### Ví dụ kiểm worker metadata trong integration test

~~~java
List<StepExecution> workerExecutions = jobExecution
        .getStepExecutions()
        .stream()
        .filter(s -> s.getStepName().startsWith("workerStep:"))
        .toList();

assertEquals(4, workerExecutions.size());
assertTrue(workerExecutions.stream()
        .allMatch(s -> s.getStatus() == BatchStatus.COMPLETED));

long totalRead = workerExecutions.stream()
        .mapToLong(StepExecution::getReadCount)
        .sum();
assertEquals(40_000L, totalRead);
~~~

**Phụ thuộc fixture:** giả định batch có đúng 40.000 records hợp lệ và mỗi partition reader không retry từ đầu trong happy-path. Nếu IDs sparse, filter/skip hoặc failure/restart, `readCount` và `writeCount` có thể phản ánh những điều khác; test phải mô tả semantics thay vì cố ép bằng số `gridSize*chunkSize`.

## 16. @SpringBatchTest integration test: từ job đến database

Một test ví dụ dùng `spring-batch-test`, JUnit 5 và ứng dụng Spring Boot/Spring Batch đã có một Job bean target:

~~~java
@SpringBatchTest
@SpringBootTest
class LocalPartitioningIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobs;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void allPartitionsCommitExpectedOutput() throws Exception {
        // Fixture riêng: 40_000 staged_payment rows cho batchKey này.
        String batchKey = "it-local-partition-001";
        insertImmutableFixture(batchKey);

        JobParameters params = new JobParametersBuilder()
                .addString("batchKey", batchKey)
                .addLong("snapshotVersion", 1L)
                .toJobParameters();

        JobExecution execution = jobs.launchJob(params);
        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        List<StepExecution> workers = execution
                .getStepExecutions().stream()
                .filter(s -> s.getStepName().startsWith("workerStep:"))
                .toList();
        assertEquals(4, workers.size());
        assertTrue(workers.stream().allMatch(
                s -> s.getStatus() == BatchStatus.COMPLETED));

        long outputCount = jdbc.queryForObject("""
                SELECT COUNT(*) FROM normalized_payment
                WHERE batch_key = ?
                """, Long.class, batchKey);
        assertEquals(40_000L, outputCount);

        assertExactBusinessKeyAndValueCoverage(batchKey);
    }
}
~~~

`insertImmutableFixture` và `assertExactBusinessKeyAndValueCoverage` là **test helpers phải tự hiện thực**: fixture cần được tạo bằng SQL/CSV độc lập, test cleanup theo batchKey và assertion coverage kiểm **khóa + giá trị + tenant**, không chỉ COUNT. Nếu project có nhiều Job beans, cấu hình rõ Job cho `JobLauncherTestUtils` (ví dụ `setJob(...)`); không dựa vào auto-selection mơ hồ.

**Không sử dụng một JobParameters đã có status COMPLETED để chạy lại cùng JobInstance rồi mong job xử lý lại**: Spring Batch thường từ chối rerun job instance đã hoàn tất theo hợp đồng restart. Test khác nhau cần batchKey/snapshot version xác định riêng; **restart test** phải cố tình dùng lại identifying parameters của JobInstance chưa hoàn tất.

## 17. Assertion dữ liệu: so sánh tập khóa và giá trị

Ví dụ PostgreSQL kiểm input **thiếu output**:

~~~sql
SELECT s.record_id
FROM staged_payment s
LEFT JOIN normalized_payment o
  ON o.batch_key = s.batch_key
 AND o.record_id = s.record_id
WHERE s.batch_key = :batchKey
  AND o.record_id IS NULL;
~~~

Và output **không thuộc input**:

~~~sql
SELECT o.record_id
FROM normalized_payment o
LEFT JOIN staged_payment s
  ON s.batch_key = o.batch_key
 AND s.record_id = o.record_id
WHERE o.batch_key = :batchKey
  AND s.record_id IS NULL;
~~~

Đối với giá trị:

~~~sql
SELECT s.record_id, s.tenant_id, o.tenant_id, s.amount, o.net_amount
FROM staged_payment s
JOIN normalized_payment o
  ON o.batch_key = s.batch_key
 AND o.record_id = s.record_id
WHERE s.batch_key = :batchKey
  AND (
       o.tenant_id <> s.tenant_id
       OR o.net_amount <> ROUND(s.amount * 0.95, 2)
  );
~~~

**Kỳ vọng:** cả ba truy vấn **không có rows** cho fixture tất cả-record-hợp-lệ. Nếu policy có filter/skip, thêm các tập **approved filtered/quarantined** vào phép đối soát; không xem record vắng output như bug khi nó đã được loại theo chính sách.

**Vì sao COUNT(*) không đủ?** Hai worker có thể cùng đọc `id=100` và bỏ qua `id=101`; nếu writer có unique key, output count chỉ giảm một, và một lỗi khác có thể bù lại count. Assertions theo **tập ID/tenant/value** phát hiện gap/overlap mà số lượng đơn thuần không phát hiện.

## 18. Chứng minh thật sự có nhiều worker đồng thời

Khai báo bốn worker threads **không bảo đảm** có ít nhất hai thread thực thi cùng lúc: executor có thể bị cấu hình sai, hàng chờ che giấu tuần tự hoặc partitioner chỉ tạo một partition. Một **barrier trong worker StepExecution** giúp test thất bại rõ khi không có concurrency.

~~~java
final class ConcurrentWorkerStartProbe
        implements StepExecutionListener {
    private final CountDownLatch firstTwoStarted =
            new CountDownLatch(2);
    private final Set<String> threadNames =
            ConcurrentHashMap.newKeySet();
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger maxActive = new AtomicInteger();

    @Override
    public void beforeStep(StepExecution stepExecution) {
        threadNames.add(Thread.currentThread().getName());
        int now = active.incrementAndGet();
        maxActive.accumulateAndGet(now, Math::max);
        firstTwoStarted.countDown();
        try {
            if (!firstTwoStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Expected two concurrent worker steps");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Worker start interrupted", e);
        }
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        active.decrementAndGet();
        return stepExecution.getExitStatus();
    }

    int maxActive() {
        return maxActive.get();
    }

    int distinctThreads() {
        return threadNames.size();
    }
}
~~~

Gắn listener **vào worker step**, không manager step:

~~~java
return new StepBuilder("workerStep", jobRepository)
        .<PaymentRow, PaymentResult>chunk(200, transactionManager)
        .reader(paymentReader)
        .processor(processor)
        .writer(writer)
        .listener(concurrentWorkerStartProbe)
        .build();
~~~

Sau job:

~~~java
assertEquals(BatchStatus.COMPLETED, execution.getStatus());
assertTrue(probe.distinctThreads() >= 2);
assertTrue(probe.maxActive() >= 2);
~~~

**Ý nghĩa của barrier:** worker thứ nhất **đợi** worker thứ hai vào `beforeStep`. Nếu executor chỉ có một thread, worker thứ hai không bao giờ tới barrier trong thời gian chờ, nên test fail. Điều này có giá trị hơn việc assert `gridSize=4` hoặc nhìn tên thread trong log.

**Giới hạn:** probe là **test-only, singleton thread-safe**, nhưng cần reset/new instance cho mỗi test để latch không mang kết quả lần chạy trước. Listener `beforeStep`/`afterStep` kiểm cửa vào worker step, chưa chứng minh **hai DB transactions commit chồng nhau** hay throughput tăng; nếu muốn, cần probe bên trong processor/write/transaction và metric latency riêng. Nếu `beforeStep` throw, code instrumentation cần được quản lý để không để các tests khác bị ảnh hưởng; mỗi test nên có context/fixture riêng.

## 19. Dùng barrier có kiểm soát, tránh tự tạo deadlock trong test

`CountDownLatch(4)` ở **mỗi item** có thể khiến test treo nếu:

- Partitioner chỉ tạo ba worker vì input ít.
- Executor chỉ có hai active threads, hai tasks còn lại đang queue.
- Một partition không chứa record nên processor không được gọi.
- Một partition lỗi trước khi tới barrier.

**Cách tốt hơn:** đặt barrier ở một mốc chắc chắn có đủ participants, chẳng hạn `beforeStep` với `CountDownLatch(2)` khi đã cấu hình ít nhất hai worker tasks và hai active threads. Nếu bắt buộc cần bốn participants, cấu hình pool tối thiểu bốn threads, tạo bốn non-empty partitions và đặt timeout rõ.

### Kiểm thử concurrent write phải khác kiểm thử start

Để kiểm tra locking/throughput khi ghi, có thể tạo test harness:

~~~text
Worker A vào transaction và cập nhật bảng output.
Barrier A báo đã tới trước COMMIT.
Worker B vào transaction khác cùng lúc.
Test runner xác nhận cả hai active.
Cho A và B commit hoặc rollback theo thứ tự chỉ định.
Assert output và locks không tạo lost update/deadlock.
~~~

Muốn chứng minh transaction A thực sự **COMMIT**, không chỉ báo `writer.write()` trả về: callback writer thường chạy **trong transaction**, và dữ liệu có thể bị rollback sau callback. Dùng transaction synchronization hook/test DB session khác để xác minh mốc commit đúng.

## 20. Kiểm tra state isolation của worker beans

Ở local partitioning, nhiều worker threads dùng chung Spring ApplicationContext. Những state sau **không được vô tình chia sẻ**:

- Reader cursor, current item/line number, paging state, `ItemStream`.
- Một `SimpleDateFormat` static không thread-safe (thay bằng `DateTimeFormatter` immutable).
- Bộ đếm dạng `int processed++` trên singleton.
- Mutable `List`, `HashMap` hoặc cache nội bộ không có concurrency policy.
- `ExecutionContext` bị lưu tham chiếu chung ngoài scope.
- HTTP client/session, writer buffer hoặc file handle được chia sẻ sai.

### Một test kiểm source range ở từng worker

Thêm test-only `ItemProcessListener` hoặc processor decorator lưu dấu:

~~~java
final class SourceVisitAudit {
    private final ConcurrentMap<Long, AtomicInteger> visits =
            new ConcurrentHashMap<>();

    void seen(long id) {
        visits.computeIfAbsent(id, ignored -> new AtomicInteger())
              .incrementAndGet();
    }

    int visitCount(long id) {
        AtomicInteger n = visits.get(id);
        return n == null ? 0 : n.get();
    }
}
~~~

Trong **happy-path không có retry/rollback**, processor decorator gọi `audit.seen(row.recordId())` và assert mỗi expected ID có `visitCount==1`. Đây là bằng chứng giúp phát hiện overlap **đã bị writer dedup che giấu**.

**Không áp dụng assertion `visitCount==1` cho retry/restart tests**: item có thể được processor gọi nhiều lần hợp lệ do retry/rollback. Trong test phục hồi, tiêu chí đúng là **logical business effect cuối cùng**, source coverage và counts/status, không phải chính xác một lần gọi Java.

## 21. Kiểm thử transaction boundary khi các partitions commit độc lập

Mỗi worker step xử lý các chunks với transaction riêng. **Không tồn tại một global DB transaction** mặc định bao trùm mọi partition từ lúc manager bắt đầu đến khi tất cả worker hoàn tất.

~~~mermaid
sequenceDiagram
    participant M as Manager PartitionStep
    participant A as Worker partition0
    participant B as Worker partition1
    participant D as Business DB
    M->>A: StepExecution + range A
    M->>B: StepExecution + range B
    A->>D: Chunk A1 COMMIT
    B->>D: Chunk B1 COMMIT
    A->>D: Chunk A2 COMMIT
    B--xD: Chunk B2 ROLLBACK
    Note over A,B: Partition B FAILED; A có thể đã commit nhiều chunks
    M-->>M: Manager/Job status theo kết quả tổng hợp
~~~

**Kịch bản assertion:**

1. Cho partition 0/1 xử lý hợp lệ.
2. Tiêm lỗi permanent vào partition 2 khi các partitions khác đã commit một vài chunks.
3. Xác minh partition 2/manager/job thất bại theo policy, **nhưng các chunks đã commit ở partition khác không tự rollback**.
4. Khi restart, records của các chunks đã commit không được tạo business effect lần hai.
5. Chỉ chuyển batch sang `PUBLISHED` sau khi toàn bộ partitions đạt success và dữ liệu được đối soát, không sau partition đầu tiên hoàn thành.

### Kiểm thử với hai database

Nếu business writer và `JobRepository` dùng hai datasources/transaction managers, kết quả business commit và metadata checkpoint có thể **lệch thời điểm**. Cần một test: business DB commit thành công nhưng metadata update/lưu execution context thất bại, sau đó restart/replay. **Idempotency ở sink** phải giữ dữ liệu đúng dù reader checkpoint trễ.

Không suy ra thêm `@Transactional` vào processor sẽ làm DB business, JobRepository và file/broker có một transaction ACID chung.

## 22. Đừng cho cả bốn partitions tranh chấp cùng một hot row

Phân vùng dữ liệu đọc đúng không bảo đảm writer không tranh nhau một **aggregate row**. Ví dụ mỗi record ở các partitions khác nhau đều cập nhật một dòng `daily_total`:

~~~sql
UPDATE daily_total
SET total_amount = total_amount + :amount
WHERE batch_key = :batchKey;
~~~

**Rủi ro:**

- DB serialize các transactions qua row lock, khiến throughput không tăng dù bốn workers hoạt động.
- Retry sau deadlock/timeout có thể **cộng lại** nếu business operation ID không được kiểm tra.
- Những code kiểu `SELECT total; UPDATE total=newTotal` ở hai transactions có thể dẫn tới lost update nếu isolation/locking không đủ.

**Kiến trúc/test thay thế:** mỗi partition ghi **kết quả riêng theo partition/batch/record**, rồi một bước reduce/aggregate sau đó chạy theo transaction xác định; hoặc dùng operation ledger/atomic upsert đủ idempotent.

~~~sql
CREATE TABLE partition_totals (
    batch_key     VARCHAR(120) NOT NULL,
    partition_id  VARCHAR(100) NOT NULL,
    sum_amount    NUMERIC(20,2) NOT NULL,
    PRIMARY KEY (batch_key, partition_id)
);

SELECT SUM(sum_amount)
FROM partition_totals
WHERE batch_key = :batchKey;
~~~

Nếu mỗi partition ghi một tổng cuối có khóa riêng, người tổng hợp chỉ được publish khi **toàn bộ partitions đã hoàn tất hợp lệ**. Một partition retry không được cộng tổng cũ vào tổng mới; write kết quả partition phải replay-safe và theo source version.

## 23. Connection pool, cursor và executor tạo nút thắt chung

Local partitioning có thể tạo N worker threads, nhưng chúng vẫn chia sẻ:

- `DataSource` connection pool.
- PostgreSQL/MySQL database server và locks/indexes.
- JobRepository connection/metadata update capacity.
- CPU/memory/GC của **một JVM**.
- Disk I/O hoặc network resource của input source.

Ví dụ cấu hình:

~~~text
Partitions returned:         16
Executor max active threads:  4
Hikari maximumPoolSize:       3
Cursor reader:                1 connection/active worker (tùy setup)
Writer/metadata:              cần thêm connections tùy transaction config

=> Có thể có worker chờ connection, throughput thấp,
   hoặc timeouts nếu pool không đủ cho concurrency thực.
~~~

**Không dùng một công thức cố định `poolSize=gridSize`**. Reader kiểu cursor, writer transactions, JobRepository, coordinator, validation và những services khác có nhu cầu connection khác nhau. Hãy **đo số connection active/pending**, xác định readers giữ connection bao lâu, rồi chọn pool với headroom và giới hạn phù hợp DB.

### Kiểm thử khả năng chịu tải connection

| Tình huống | Biến đổi | Assertion |
| --- | --- | --- |
| Pool đủ cho workload | 4 active workers, pool được sizing từ đo đạc | Job thành công, wait hợp lý, đúng output |
| Pool thiếu | Giảm pool có chủ đích | Timeout/fail rõ, không deadlock vô thời hạn |
| Executor queue đầy | Nhiều partitions, queue nhỏ | Rejection policy xử lý được, không mất work âm thầm |
| Slow reader | Thêm I/O latency kiểm soát | Backpressure/monitoring có hiệu lực |
| Hot DB row | Cho nhiều partitions cùng update một key | Đo lock wait, không lost update/duplicate effect |
| Vary chunk size | 50/200/1.000 | So throughput, latency, rollback cost và memory |
| Sparse/skewed data | Một range có 80% records | Nhận diện tail latency, thiết kế phân vùng phù hợp |

**Chỉ số tối ưu là thời gian kết thúc job và tính đúng**, không phải số thread nhiều nhất. Nếu DB là bottleneck, tăng `gridSize` có thể làm chậm thêm vì locks, context switches và pool contention.

## 24. Kiểm thử executor queue và số partitions thực sự chạy

Giả sử partitioner trả 12 partitions nhưng executor chỉ có 3 workers, 3 tasks queue. Mọi partition có thể **cuối cùng** chạy, nhưng đồng thời chỉ tối đa 3.

~~~text
gridSize                 = 12
partitioner output size  = 12
corePoolSize             = 3
maxPoolSize              = 3
queueCapacity            = 3

Không suy ra 12 worker chạy cùng lúc.
Nếu submit 12 tasks nhanh hơn khả năng drain, queue có thể đầy.
~~~

`ThreadPoolTaskExecutor` có thể reject tasks khi pool/queue đầy tùy cấu hình. Trong môi trường Spring Batch, rejection phải được bộc lộ thành **failure rõ**, không được đánh dấu worker StepExecution thành công khi task chưa chạy. Test cần:

1. Cố ý cấu hình số partitions lớn và queue nhỏ.
2. Làm worker chậm có kiểm soát để queue được lấp đầy.
3. Xác nhận outcome: các tasks thực chạy, task nào bị reject, manager/job status, có đủ `StepExecutions` và business output không.
4. Thay đổi pool/queue hoặc rate điều phối theo capacity đã đo rồi chạy lại.
5. Không dùng timeout quá ngắn rồi cho rằng mọi scheduler có lỗi; phân biệt **expected overload test** và correctness test bình thường.

**`CallerRunsPolicy` nếu được dùng** có thể làm task được chạy trên thread caller, thay đổi mô hình concurrency và ảnh hưởng đến việc manager đang điều phối. Không tự áp dụng policy ấy chỉ để che rejection mà chưa kiểm thử propagation/context và throughput.

## 25. Failure injection: cho đúng một partition thất bại

Một cách kiểm thử đơn giản là đặt **fault switch** trong test-controlled processor cho một record thuộc partition xác định:

~~~java
final class FaultSwitch {
    private final AtomicBoolean enabled = new AtomicBoolean();

    void enable() {
        enabled.set(true);
    }

    void disable() {
        enabled.set(false);
    }

    boolean isEnabled() {
        return enabled.get();
    }
}

final class InjectedFailureProcessor
        implements ItemProcessor<PaymentRow, PaymentResult> {

    private final FaultSwitch fault;
    private final long failingId;

    InjectedFailureProcessor(FaultSwitch fault, long failingId) {
        this.fault = fault;
        this.failingId = failingId;
    }

    @Override
    public PaymentResult process(PaymentRow row) {
        if (fault.isEnabled() && row.recordId() == failingId) {
            throw new IllegalStateException(
                    "Injected permanent partition failure");
        }
        return new PaymentResult(
                row.batchKey(), row.recordId(), row.tenantId(),
                row.amount().multiply(new BigDecimal("0.95"))
                        .setScale(2, RoundingMode.HALF_UP));
    }
}
~~~

**Cấu hình test:** processor cho test có thể thay thế bean production qua `@TestConfiguration`/test profile. Không cấu hình `skip(IllegalStateException.class)` hoặc retry vô hạn cho lỗi này, vì mục đích là **partition FAILED**. `FaultSwitch` phải được test điều khiển, không bật nhầm trong production.

### Quy trình test

~~~text
1. Lập input snapshot và gán failingId vào partition2.
2. fault.enable().
3. Run JobInstance lần 1 -> FAILED do partition2.
4. Xác minh những partitions/chunks thành công có output đã commit.
5. fault.disable().
6. Restart CÙNG JobInstance/identifying JobParameters.
7. Verify Job COMPLETED, đầy đủ output keys, không duplicate effects.
8. Xem StepExecutions: failed partition có attempt tiếp theo,
   partitions completed trước đó không được làm sai đầu ra.
~~~

Một `AtomicBoolean` sống trong JVM giúp điều khiển lỗi **giữa hai executions trong cùng test process**; nó không mô phỏng một lỗi thực sự bật/tắt qua **whole-JVM crash** vì khi JVM mới khởi động switch có thể reset. Test crash process cần **fault configuration bên ngoài và bền vững** hoặc script harness điều khiển theo phase.

## 26. Restart: cùng JobInstance, cùng partition identity

Spring Batch gắn `JobInstance` với identifying `JobParameters`. Khi job thất bại, restart thường tạo **JobExecution mới** của cùng JobInstance; worker StepExecutions cũ/hợp lệ giúp framework quyết định phần nào đã hoàn tất và phần nào cần chạy lại theo hợp đồng `PartitionStep`.

**Điều bắt buộc cho test:**

- Dùng lại cùng identifying parameters trong **restart**; đừng thêm `run.id` mới rồi gọi đó là restart cùng JobInstance.
- Không thay source snapshot, `batchKey`, partition names hoặc logic chia range giữa hai lần chạy.
- Đừng dùng `Math.random()`, current timestamp hoặc worker hostname làm partition name trong `Partitioner`.
- `ExecutionContext` chứa những giá trị serializable/đơn giản, không lưu JDBC connection, stream hoặc service object.
- Worker reader checkpoint có thể được framework dùng khi step restart; business writer vẫn idempotent khi checkpoint trễ hơn DB commit.
- Không tự sửa JobRepository thành COMPLETED nếu một partition chưa hoàn tất hoặc còn outcome không rõ.

**Phân biệt restart và chạy batch mới:** nếu cần xử lý một snapshot đã thay đổi sau lỗi, đó có thể là **correction/new batch** theo policy, không phải vô tư restart JobInstance cũ với dữ liệu khác.

## 27. Thử restart thật với @SpringBatchTest

Một skeleton integration test:

~~~java
@Test
void restartAfterOnePartitionFailsKeepsBusinessEffectsCorrect()
        throws Exception {
    String batchKey = "it-restart-partition-002";
    insertImmutableFixture(batchKey);

    JobParameters params = new JobParametersBuilder()
            .addString("batchKey", batchKey)
            .addLong("snapshotVersion", 1L)
            .toJobParameters();

    faultSwitch.enable();
    JobExecution first = jobs.launchJob(params);
    assertEquals(BatchStatus.FAILED, first.getStatus());

    // Checkpoint/output/failed partition assertions ở đây.
    assertPartitionFailureIsVisible(first);

    faultSwitch.disable();
    JobExecution restart = jobs.launchJob(params);
    assertEquals(BatchStatus.COMPLETED, restart.getStatus());

    assertEquals(first.getJobInstance().getInstanceId(),
                 restart.getJobInstance().getInstanceId());
    assertExactBusinessKeyAndValueCoverage(batchKey);
}
~~~

Đây là **bộ khung**, cần fixture, bean `FaultSwitch`, test profile và helper assertions. `jobs.launchJob(params)` lần hai có ý nghĩa restart **nếu JobInstance trước ở trạng thái có thể restart và Job/config cho phép**. Trong trường hợp một JobExecution còn `STARTED/UNKNOWN` sau process crash, không được assume lời gọi trên luôn chạy ngay; phải xử lý metadata/liveness/recovery theo hợp đồng framework.

### Test không nên chỉ assert COMPLETED

Sau restart cần kiểm:

1. `JobInstance ID` giữ nguyên.
2. `JobExecution ID` thay đổi (một execution mới).
3. Partition names và source ranges giữ nguyên.
4. Những business operations đã commit trước khi fail không tăng đôi.
5. Những records còn thiếu được xử lý đúng.
6. Tổng output và values match source snapshot.
7. Metadata cuối phù hợp, không còn failed partition chưa giải quyết.

## 28. Whole-JVM crash khác lỗi một worker thread

**Local partitioning chạy trong một JVM.** Khi một worker throw exception, các worker threads khác vẫn có thể đã commit hoặc đang xử lý tùy lifecycle và cấu hình. Nhưng khi **JVM process bị kill**, **tất cả các worker threads và manager trong process đó đều chết cùng lúc**.

Do đó cần **hai tầng test riêng**:

| Tầng | Cách gây lỗi | Điều chứng minh |
| --- | --- | --- |
| Worker-level fault | Processor/writer ném exception ở partition2 | Step failure aggregation, transaction rollback, restart partition |
| Whole-JVM fault | Kill process đang chạy manager + workers | Crash recovery của JobRepository, dữ liệu partial committed, restart trên JVM mới |

**Không gọi “worker node failover” là local partitioning** nếu chỉ một thread bị exception trong cùng JVM. Node/process crash là sự cố chung cho tất cả partitions local ở thời điểm ấy.

### Whole-JVM crash test harness

~~~text
1. Spawn child JVM chạy Spring Batch job trên DB bền vững.
2. Chờ test hook báo các worker đã commit >= N chunks.
3. Kill child JVM (không gọi graceful shutdown).
4. Test runner dùng connection độc lập đối soát output.
5. Khởi động JVM mới cùng JobInstance/snapshot.
6. Áp dụng recovery hợp lệ cho metadata trạng thái bất thường.
7. Kiểm tra output cuối đúng, JobRepository không bị đánh dấu giả.
~~~

**Lưu ý:** Spring Batch không bảo đảm mọi JobExecution `STARTED` bị bỏ lại sau kill có thể restart ngay mà không cần xử lý stale metadata; phải dùng quy trình recovery tương ứng phiên bản/framework và tránh ép chạy song song trên JobInstance chưa rõ owner.

## 29. Kiểm thử retry/skip không được làm sai business correctness

Trong local partitioning, mỗi worker `StepExecution` có thể dùng `faultTolerant()`, `retry()`, `skip()`. Cần phân biệt:

- **Transient DB deadlock/timeout:** retry hữu hạn/backoff nếu phù hợp, không mặc định skip item tốt.
- **Validation exception gắn với record:** skip chỉ khi business policy cho phép, có durable quarantine và đối soát.
- **Lỗi cấu hình/serializer/SQL:** fail, không nuốt dưới `skip(Exception.class)`.

Ví dụ worker step cho phép retry transient (chỉ minh họa, phải xác minh tính idempotent):

~~~java
return new StepBuilder("workerStep", jobRepository)
        .<PaymentRow, PaymentResult>chunk(200, transactionManager)
        .reader(paymentReader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

**Test:** tiêm lỗi một lần rồi phục hồi, xác nhận item không được skip và output cuối đúng. Tiêm lỗi thường trực cho đến hết retry, xác nhận partition/job thất bại **hoặc** xử lý theo policy rõ; không được completed với dữ liệu thiếu. Khi rollback xảy ra, processor có thể được gọi lại nhiều lần; assertion `processCallCount==sourceRowCount` không còn phù hợp.

### Skip budget khi có nhiều partition

`skipLimit(10)` áp dụng cho một worker `StepExecution`, không tự tạo giới hạn **10 records toàn JobExecution** khi có 20 partitions. Nếu SLA cho phép tối đa 10 errors toàn batch, cần **quality gate** sau worker completion và tổng hợp đúng dữ liệu. Test phải có scenario từng partition chỉ skip vài records nhưng tổng job vượt policy, và xác minh batch **không được PUBLISHED**.

## 30. Race và deadlock với output ghi theo thứ tự khác nhau

Một số bugs chỉ lộ khi hai worker tranh nhiều DB rows theo thứ tự khác nhau:

~~~text
Partition A:
  lock account_1 -> lock account_2

Partition B:
  lock account_2 -> lock account_1

Hai transactions có thể deadlock.
~~~

Các biện pháp:

- Giữ **lock ordering ổn định** ở writer (ví dụ cập nhật accounts theo ID tăng dần) khi nghiệp vụ cho phép.
- Giữ chunk transactions đủ ngắn.
- Index chính xác theo partition keys; giảm full-table scans gây lock contention.
- Retry deadlock theo bounded policy và bảo đảm business idempotency.
- Dùng integration test DB thật, vì H2/in-memory DB có thể khác transaction/locking semantics so với PostgreSQL/MySQL/Oracle.

**Assertion:** test không kết thúc vô hạn, lỗi deadlock được báo/chuyển theo policy, không có lost update hoặc double-apply sau retry. Không chấp nhận chỉ tăng isolation level vô tội vạ nếu làm throughput giảm hoặc tạo thêm deadlocks.

## 31. Snapshot thay đổi giữa các lần chạy: một negative test quan trọng

Partition ranges chỉ đúng khi chúng được xây từ **một source snapshot xác định**. Một lỗi tinh vi là manager tính `MIN(record_id)` và `MAX(record_id)` ở lần chạy đầu, nhưng khi restart lại tính từ bảng staging **đã được bổ sung/xóa record**.

~~~text
Run 1:
  snapshot=batch-A-v1, IDs 0..9999
  partition0=[0,2500), partition1=[2500,5000), ...
  75% chunks đã commit, rồi job thất bại.

Trước restart:
  upstream thêm ID 10000 hoặc sửa record 2000.

Run 2 tính lại partition ranges và reader query bảng mutable:
  record có thể bị bỏ, xử lý lại hoặc lệch giá trị.
~~~

**Test âm:** cố tình thay input trong lúc job FAILED, rồi restart. Hệ thống phải **phát hiện sourceVersion/snapshot mismatch và fail/quarantine** hoặc áp dụng một protocol snapshot versioned đã định nghĩa. Không được âm thầm tiếp tục với dữ liệu mới và tuyên bố old JobInstance đã phục hồi đúng.

**Cách tốt hơn:** stage dữ liệu vào một tập immutable có `batchKey`, high-water mark hoặc snapshot ID được chốt trước khi manager tạo partition. Đối với file, manifest lưu `fileId/sourceVersion/checksum`; với database source, có thể dùng bảng staging đã khóa phiên nhập hoặc snapshot keys đã persist. Chỉ `ORDER BY record_id` không ngăn nguồn bị thay đổi giữa các transaction.

## 32. Partition skew: đều theo range chưa chắc đều theo khối lượng

Nếu IDs phân bố không đều:

~~~text
partition0: [0,2500)      50 records
partition1: [2500,5000)   200 records
partition2: [5000,7500)   37,000 records
partition3: [7500,10000)  2,750 records
~~~

Thời gian job gần như bị partition 2 chi phối; ba threads khác kết thúc sớm rồi rảnh. **Bộ test correctness có thể pass hoàn toàn**, nhưng scalability không tốt.

Các hướng phân vùng:

- **Range theo số lượng item** dựa trên sorted key snapshot, không theo numeric width.
- **Partition theo file/object** nếu mỗi file có record count ước lượng.
- **Hash/modulo partition** như `MOD(record_id, N)` khi query/index và restart mapping cho phép.
- **Pre-shard** file hoặc stage logical record IDs để cân bằng.
- **Dynamic work queue** nếu số lượng file rất lớn và độ lệch lớn; quản lý claim/lease/recovery riêng.

**Test không chỉ xem partition count**: đo `readCount`, thời gian theo partition, CPU/I/O, idle time và end-to-end elapsed. Với bài test đơn giản, tạo fixture skew 95/5, chạy gridSize 1/2/4/8 và quan sát tail; đừng tăng số threads mà không thay partition strategy khi skew là nút thắt.

## 33. Stress test: chạy lặp để phát hiện race

Một test functional duy nhất không chứng minh code không có race. Test concurrency có tính **nondeterministic** khi thread scheduling, GC, database latency và máy CI khác nhau.

Chiến lược stress:

1. Chạy nhiều vòng với **batchKey riêng và input seed cố định**.
2. Thay đổi executor pool 1/2/4/8 và `gridSize` 1/2/4/8/16.
3. Chèn jitter/controlled pauses trong processor hoặc writer, nhưng không dựa chúng làm bằng chứng overlap.
4. Giữ processor/reader/writer state isolation và ghi test audit để phát hiện duplicate visits ở happy-path.
5. Mỗi vòng kiểm set difference, business values, không có output ngoài snapshot và metadata hợp lệ.
6. Theo dõi tests bị treo, connection pending, deadlocks, repeated `StepExecution` và queue rejection.
7. Khi có failure, giữ **seed, JobParameters, partition ranges, thread dump/logs và DB snapshot** đủ để tái hiện.

### Không dùng randomness như một lời giải

Gắn `Thread.sleep(randomDelay)` vào code có thể làm race dễ hoặc khó xảy ra, nhưng **không bảo đảm** đụng đúng cửa sổ race. Hãy dùng `CountDownLatch`/barrier có timeout để tạo **happens-before/overlap mong muốn**, và dùng randomized stress như **lớp bổ sung**.

### Thread safety của test harness cũng phải đúng

Đừng để test tự có race khiến nó báo sai:

~~~java
// Sai: cùng ArrayList bị nhiều worker threads add.
List<Long> visited = new ArrayList<>();

// Đúng hơn cho audit đồng thời:
ConcurrentMap<Long, AtomicInteger> visited =
        new ConcurrentHashMap<>();
~~~

Khi dùng `AtomicInteger` cho bộ đếm, cần phân biệt **số lần gọi processor** và **số logical effects đã commit**. Processor visit tăng trước commit có thể cao hơn số dòng DB sau rollback; điều này không nhất thiết là bug.

## 34. Measurement: speedup, hiệu suất và tính đúng

Một phép đo scaling tối thiểu:

| `gridSize` | Executor active max | Job wall time | Throughput | DB wait | Kết quả |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | Đo thực tế | Đo | Đo | Đối soát PASS/FAIL |
| 2 | 2 | Đo thực tế | Đo | Đo | Đối soát PASS/FAIL |
| 4 | 4 | Đo thực tế | Đo | Đo | Đối soát PASS/FAIL |
| 8 | 8 | Đo thực tế | Đo | Đo | Đối soát PASS/FAIL |

Tính:

\[
\text{Speedup}(N) = \frac{T_1}{T_N},\qquad
\text{Efficiency}(N) = \frac{\text{Speedup}(N)}{N}
\]

Trong đó `T1` là thời gian với một worker và `TN` là thời gian cùng workload/DB/storage khi dùng N active workers. **Không so sánh hai fixture khác nhau**, hoặc môi trường đầu vào còn warm cache khác mà không ghi chú; chạy warm-up và lặp nhiều lần khi cần đo đáng tin cậy.

### Những điều cần nhìn ngoài throughput

- **CPU usage**: CPU cao ở manager JVM hay DB server?
- **DB connection pending**: có đang đợi pool không?
- **Lock waits/deadlocks**: writer hot rows, index contention.
- **Disk/network IOPS**: nhiều readers đụng cùng storage.
- **GC pause và heap**: mỗi reader giữ buffer/state riêng.
- **Thread count và executor queue**: gridSize có nhiều partitions nhưng active workers có ít không?
- **JobRepository update latency**: metadata persistence bị nghẽn?
- **Retry/rollback rate**: throughput báo cao nhưng nhiều work bị làm lại?
- **Correctness**: mọi kết quả phải PASS; throughput cao nhưng duplicate/missing records không có giá trị.

**Local partitioning scale theo tài nguyên của một JVM/host**, không phải tự động scale ngang qua nodes. Nếu CPU/heap/I/O của một máy là giới hạn, remote partitioning có thể cần thiết nhưng mang thêm chi phí messaging, failover và consistency.

## 35. Các kịch bản test nên có trong một test suite

| Test | Đầu vào/điểm lỗi | Kết quả mong đợi |
| --- | --- | --- |
| T01. Coverage | 40.000 IDs, 4 partitions | Đủ ranges, không overlap/gap |
| T02. Sparse IDs | 1,2,9,100,10.000 | Đọc đúng actual rows, không giả định IDs liên tiếp |
| T03. Edge boundaries | IDs đúng start/end | `start` included, `end` excluded |
| T04. Empty input | 0 records | Explicit no-op path, không metadata sai |
| T05. Grid larger than domain | 1 record, grid=8 | Không tạo overlap/empty không kiểm soát |
| T06. Isolation | Hai batches/tenants cùng IDs | Không cross-batch/cross-tenant output |
| T07. Actual parallelism | 4 partitions, pool 4, barrier 2 | Ít nhất 2 worker start đồng thời |
| T08. Thread safety | Shared processor/writer + readers scoped | Không race/mutable cursor lẫn partitions |
| T09. Idempotent sink | Duplicate logical record | Không áp dụng side effect hai lần |
| T10. Business reconciliation | SQL set/value checks | Không thiếu, trùng, thừa, sai tiền/tenant |
| T11. One worker fails | Inject exception partition2 | Job/manager fail rõ; partial commits được ghi nhận |
| T12. Restart | Disable fault, same JobInstance | Hoàn tất sau replay, không duplicate effect |
| T13. JVM kill | Kill process sau chunks commit | Restart/recover theo metadata, output đúng |
| T14. Pool exhaustion | Pool intentionally undersized | Timeout/alert rõ, không treo vĩnh viễn |
| T15. Queue rejection | Nhiều partitions, queue nhỏ | Worker/job không báo COMPLETED giả |
| T16. DB deadlock | Hai workers lock inverse order | Retry/fail theo policy, không lost update |
| T17. Source mutation | Thay input snapshot trước restart | Detect mismatch, fail/reconcile |
| T18. Skip budget | Nhiều partitions skip dưới local limit | Global policy chặn publish khi vượt |
| T19. Skew | Một partition chứa 80–95% records | Đo tail latency và nhận diện bottleneck |
| T20. Repeat stress | Lặp nhiều lần và thay pool/grid | Không race/data corruption, kết quả ổn định |

**Không nhất thiết chạy tất cả trong mỗi unit-test commit**. Có thể phân tầng **fast deterministic tests → DB integration tests → destructive crash/chaos tests → performance benchmarks**; nhưng các tests quan trọng về tính đúng và restart phải được chạy thường xuyên ở môi trường sát production.

## 36. Tổ chức test suite trong CI

Một đề xuất phân lớp:

**Lớp A — Unit, vài giây**

- Partitioner coverage/property tests, grid edge cases.
- Processor thuần và validation logic.
- Serialization của `ExecutionContext` chỉ chứa simple values.
- Config fail-fast khi thiếu `batchKey`/range hoặc snapshot mismatch.

**Lớp B — Integration DB với Spring Batch**

- `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepository` và PostgreSQL test container/schema.
- 4 workers thật, bounded executor, `StepScope` reader, output writer.
- Barriers/latches, StepExecutions, SQL reconciliation.
- Fault injection ở một partition, restart cùng JobInstance.
- Isolation, transactional/idempotent SQL và connection pool constraints.

**Lớp C — Process-level crash/chaos**

- Chạy child JVM, điều khiển commit hook rồi terminate process.
- DB/JobRepository persistence survive process restart.
- Xử lý stale metadata/partial commits theo recovery protocol.
- Với nguồn file, kiểm source version/checksum và ổn định partition mapping.

**Lớp D — Load/performance**

- Dataset đủ lớn, pool/grid/chunk size matrix, skewed ranges.
- So throughput, resource utilization, oldest partition age, rollback/retry rate.
- Kiểm bảo đảm data correctness sau mỗi lần bench, không chỉ wall time.

### Giữ môi trường test độc lập

- Mỗi test có `batchKey`/schema hoặc fixture được dọn đúng phạm vi.
- Không dùng chung `JobRepository` state cũ giữa các bài test mà không kiểm soát, vì identifying parameters có thể đụng JobInstance đã COMPLETED.
- Không reset/truncate cả production-like database trong lúc các tests chạy song song.
- Test concurrency dùng clock/timeouts hợp lý và cleanup executor/threads/DB connections.
- Capture cấu hình `gridSize`, pool sizes, DB version, Java/Spring Batch versions cùng failed seed để điều tra.

**Một test flaky không nên được chữa bằng cách tăng `Thread.sleep` vô thời hạn.** Tìm race điều kiện setup, dùng barrier khi cần; nếu chỉ là performance variation, tách SLA perf test khỏi deterministic correctness test.

## 37. Telemetry cần thu trong integration test

Thay vì in một log “thread started”, nên thu các tín hiệu đủ phân biệt lỗi scheduling, DB và business data:

| Metric/signal | Ý nghĩa | Khi bất thường |
| --- | --- | --- |
| `partitions_created` | Partitioner tạo mấy partitions? | Khác manifest/snapshot dự kiến |
| `worker_step_executions` | JobRepository thấy những worker steps nào? | Thiếu/trùng partition identity |
| `executor_active_threads` | Bao nhiêu threads thực chạy? | Thấp hơn concurrency mong muốn |
| `executor_queue_size` | Tasks đang chờ? | Backlog tăng; grid quá lớn |
| `partition_read_count` | Phân bố input theo partition | Skew/hole bất thường |
| `partition_commit_count` | Số chunk commits | Có worker treo hoặc rollback nhiều |
| `partition_rollback_count` | Chunks bị rollback | Retry loop, SQL contention |
| `db_pool_active/pending` | Có chờ connection? | Hết pool hoặc cursor giữ connection |
| `db_lock_wait_seconds` | Nút thắt lock DB | Hot keys, deadlock |
| `job_repository_latency` | Metadata update có chậm? | Quá nhiều StepExecutions/commits |
| `worker_failure_total` | Partition nào fail/loại lỗi? | Permanent source bug hoặc hạ tầng |
| `input_output_mismatch_total` | Có thiếu/trùng/sai dữ liệu? | Không publish |
| `job_restart_lag` | Thời gian khôi phục sau crash | Vượt SLA |

**Không dùng `recordId`/transactionId của hàng triệu records làm metric labels** vì cardinality lớn; log/tracing có quyền truy cập có thể chứa IDs cần điều tra, metrics nên aggregate theo job, step, partition class, worker pool và failure code.

### Nguyên tắc đo cạnh tranh

~~~text
gridSize       = số partition yêu cầu/được trả từ Partitioner
poolSize       = capacity thực của executor
activeThreads  = số thread đang chạy ở thời điểm đo
inFlightChunks = chunks chưa hoàn tất transaction
DB connections = connections active/idle/pending ở pool
~~~

Các con số **không tương đương**. Một thread có thể bị DB blocked, một reader cursor có thể giữ connection lâu, còn một chunk chưa commit không thể đếm như thành công chỉ vì processor đã xong.

## 38. Logging và trace context nên giữ gì?

Khi nhiều worker threads log xen kẽ, cần định danh:

~~~text
jobInstanceId
jobExecutionId
managerStepExecutionId
workerStepExecutionId
partitionName
batchKey/sourceVersion
rangeStart/rangeEnd
threadName
chunkCommitOutcome
retryAttempt / failureCode
~~~

Không dùng chỉ `Thread.currentThread().getName()` làm business identity: executor threads được tái sử dụng, một thread có thể chạy nhiều partitions. **Partition name + StepExecution ID + JobExecution ID** phân biệt logical work và runtime attempt rõ hơn.

Ví dụ một trace sự cố:

~~~text
09:12:01 managerStep partitioner produced partition2=[20000,30000)
09:12:02 workerStep:partition2 id=882 started thread=local-partition-3
09:12:04 workerStep:partition2 chunk commit records=200
09:12:05 workerStep:partition2 transient DB deadlock, retry=1
09:12:06 workerStep:partition2 chunk rollback
09:12:08 workerStep:partition2 retry succeeded, chunk commit
09:12:19 workerStep:partition2 status=COMPLETED
~~~

**Không log “COMMIT OK” từ `ItemWriter.write` khi transaction chưa thực sự commit**. Trong test có thể instrument transaction synchronization `afterCommit` theo đúng Spring transaction manager để phân biệt write method return và outcome commit.

## 39. Runbook khi test local partitioning fail

Khi job `FAILED`, bị treo hoặc `COMPLETED` nhưng output thiếu:

1. **Khoanh vùng:** JobInstance/Execution, identifying params, source snapshot, manager step, partition count/ranges.
2. **Xác minh partitions:** có overlap/gap, range exclusive/inclusive sai, tên partition thay đổi qua restart hay không?
3. **Xác minh worker metadata:** mỗi worker `StepExecution` status, `ExecutionContext`, read/write/filter/skip counts, failure exceptions.
4. **Xem executor:** core/max pool, queue capacity, rejected submissions, actual active threads, lingering tasks.
5. **Xem DB resources:** connections, cursor lifetimes, lock waits, deadlocks, transaction timeouts, JobRepository latency.
6. **Kiểm tra input:** `batchKey`/tenant/sourceVersion còn bất biến hay staging đã bị sửa sau khi partitions được tạo?
7. **Đối soát business data:** expected source key set vs output/filter/quarantine, giá trị và side effects.
8. **Phân loại fail:** worker-level exception, DB transaction, manager aggregation, whole-JVM crash hay metadata state bị treo.
9. **Chọn recovery hợp lệ:** retry/restart cùng JobInstance nếu status cho phép, giữ partition mapping và source; xử lý stale `STARTED/UNKNOWN` theo protocol.
10. **Chặn replay nguy hiểm:** bảo đảm writer idempotent, không gọi external side effect hai lần; không reset toàn bộ output mù quáng.
11. **Đo lại sau sửa:** chạy correctness/integration test trước, mới performance; giữ seed, thread dumps và SQL evidence.
12. **Đóng sự cố:** ghi nguyên nhân, partition ảnh hưởng, commit boundary, thời gian recovery và những test mới được bổ sung.

### Một lỗi điển hình: test chỉ có một thread

~~~text
Test expected: 4 workers đồng thời.
Actual:
  partitioner trả 4 contexts.
  TaskExecutor bị cấu hình SyncTaskExecutor (hoặc pool=1).
  Worker steps chạy tuần tự.
  Job vẫn COMPLETED, output hoàn toàn đúng.

Barriers ở beforeStep phát hiện không có worker thứ hai,
trong khi test chỉ assert COMPLETED sẽ bỏ sót.
~~~

### Một lỗi điển hình khác: overlap bị writer che giấu

~~~text
partition0=[0,101)
partition1=[100,200)
Record 100 được đọc ở cả hai partitions.
ON CONFLICT DO NOTHING khiến output chỉ có 1 row ID=100.
Job vẫn COMPLETED.

Unit test ranges + visit audit happy-path phát hiện record 100
đã được processor gọi hai lần.
~~~

**Không sửa `BATCH_STEP_EXECUTION` bằng tay để chuyển thành COMPLETED và làm xanh dashboard.** Nếu job có outcome không rõ, cần reconciliation/recovery có căn cứ theo transaction boundaries thay vì che dấu data correctness bug.

## 40. Anti-patterns trong bộ kiểm thử

| Anti-pattern | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| Chỉ assert `BatchStatus.COMPLETED` | Không thấy missing/duplicate business effects | Full key/value reconciliation |
| Chỉ assert `gridSize=4` | Có thể chạy tuần tự | Barrier + actual active thread evidence |
| `Thread.sleep` để “ép race” | Không deterministic, flaky | `CountDownLatch`/barrier và explicit failpoint |
| Dùng `ArrayList` chia sẻ trong test audit | Test harness tự có data race | Concurrent structures/atomic counters |
| Reader singleton mutable | Cursor/state lẫn partitions | `@StepScope` hoặc factory riêng |
| SQL dùng `BETWEEN start AND end` | End inclusive gây overlap | `>= start AND < endExclusive` |
| Tên partitions sinh bằng UUID | Restart mapping thay đổi | Stable partition names/context |
| Rerun với `run.id` mới rồi gọi là restart | JobInstance mới, không kiểm checkpoint | Same identifying params/job instance |
| Dùng H2 làm bằng chứng mọi DB locking | Isolation/SQL khác production | PostgreSQL/Testcontainers hoặc DB thật tương ứng |
| Giả định step counts là rows DB đã commit | Retry/skip/conflict khác nhau | Query business DB + metadata |
| Dùng `ON CONFLICT DO NOTHING` và thôi | Che duplicate khác payload | Verify existing values/hash |
| Kỳ vọng item processor gọi đúng một lần trong restart | Retry/rollback có thể gọi lại | Assert logical business effect |
| Chia quá nhiều partitions cho ít dữ liệu | Metadata/queue overhead, empty tasks | Bounded partitioning, measured grid |
| Đọc dữ liệu đang thay đổi | Restart sai source snapshot | Immutable input/manifest |
| Dùng global `skipLimit` tưởng có sẵn | Per StepExecution không bằng whole job | Quality gate aggregate |
| Crash test chỉ throw exception ở một worker | Không mô phỏng kill JVM | Process-level test riêng |
| Đo throughput nhưng bỏ correctness | Scaling che lỗi dữ liệu | Mọi benchmark kèm reconciliation |

## 41. Bài thực hành tổng hợp

**Yêu cầu:** triển khai một Spring Batch local partitioning job với `HalfOpenRangePartitioner`, `TaskExecutorPartitionHandler`, `@StepScope` JDBC reader và writer idempotent. Dữ liệu giả lập gồm 100.000 records của một `batchKey`, trong đó có sparse IDs, hai tenants và một nhóm records dùng chung tài khoản tổng hợp để tạo tranh chấp có kiểm soát.

**Phần A — Unit và correctness**

1. Chia `[0,100_000)` theo `gridSize=1,2,4,8` và assert union/không overlap.
2. Test boundary `start/end`, empty domain, một record và sparse IDs.
3. Thêm batch/tenant khác có cùng IDs để xác minh predicate và business output isolation.
4. Tạo expected key/value set độc lập, không chỉ assert counts.

**Phần B — Concurrency và resources**

5. Dùng pool 4, gridSize 4; gắn `ConcurrentWorkerStartProbe` và assert có ít nhất hai workers đồng thời.
6. Chạy negative control pool 1 để thấy barrier test fail đúng mục đích.
7. Đo số worker `StepExecution`, thread names, `ExecutionContext` và max active threads.
8. Giảm pool DB có chủ đích, quan sát chờ connection/timeout và fail rõ.
9. Tạo skew/hot key để đo lock contention và tail latency.

**Phần C — Fail/restart**

10. Tiêm lỗi ở partition 2 sau khi các partitions khác đã commit vài chunks.
11. Xác nhận JobExecution failed, partial business data còn và metadata đúng.
12. Tắt lỗi và restart **cùng JobInstance**, giữ nguyên snapshot/partition names.
13. Kiểm tra output cuối có đúng mỗi logical business key với giá trị chuẩn.
14. Kill whole JVM sau một số chunks commit trong test process-level; khôi phục theo JobRepository status.
15. Cố tình sửa source snapshot trước restart; test phải từ chối source mismatch.

**Phần D — Scaling**

16. Lặp với grids 1/2/4/8, concurrency budgets tương ứng và chunk sizes 50/200/1.000.
17. Báo throughput, wall time, DB pool wait, lock waits, GC, metadata latency và data correctness.
18. Đề xuất grid/pool/chunk size dựa trên nút thắt thật thay vì lấy số CPU làm đáp án cố định.

**Tiêu chí đạt:** phân vùng không overlap/gap, ít nhất hai worker thực sự chạy song song trong test có điều kiện, output đủ từng key/value, fault injection hiện đúng FAILED state, restart không nhân đôi business effect và đo performance kèm giải thích bottleneck.

## 42. Checklist trước production

- [ ] Đã phân biệt local partitioning với multi-threaded step, parallel flows và remote partitioning.
- [ ] Partition names và `ExecutionContext` ổn định qua restart cùng JobInstance/snapshot.
- [ ] Có unit/property tests cho range boundaries, empty/sparse input và tenant isolation.
- [ ] Reader SQL khớp `[startInclusive,endExclusive)`, không dùng `BETWEEN` làm overlap.
- [ ] `ItemReader/ItemStream` state tách per worker (`@StepScope` hoặc factory phù hợp).
- [ ] Shared processor/writer/listeners được kiểm tra thread safety và resource lifecycle.
- [ ] Test chứng minh **actual concurrency** bằng barrier/latch, không chỉ cấu hình grid/pool.
- [ ] Mỗi worker `StepExecution` được kiểm status, context, counts và failure exceptions.
- [ ] Có source snapshot bất biến và kiểm source version trước restart.
- [ ] Writer idempotent theo business key, có phát hiện duplicate khác nội dung.
- [ ] Có đối soát source/output theo tập khóa và giá trị; không chỉ COUNT(*).
- [ ] Có failure injection tại một partition và test rollback/partial commits.
- [ ] Có restart cùng JobInstance, giữ nguyên identifying params và partition mapping.
- [ ] Có process-level crash test riêng vì local partitions cùng một JVM.
- [ ] Có kế hoạch khi StepExecution/JobExecution còn STARTED/UNKNOWN sau kill.
- [ ] Có retry/skip policy đúng phân loại lỗi, global quality gate nếu cần.
- [ ] Đã đo DB pool, executor queue, connection wait, lock contention và metadata overhead.
- [ ] Có test skew, stress lặp, pool exhaustion và queue rejection.
- [ ] Không mặc định order commit/worker completion ổn định giữa các lần chạy.
- [ ] Benchmark speedup/efficiency luôn kèm business correctness assertions.
- [ ] Có logs/metrics mang partition/StepExecution identity nhưng tránh high-cardinality metric tags.
- [ ] CI phân tầng deterministic unit, DB integration, destructive crash và performance.
- [ ] Có runbook xử lý failed/unknown partition và không sửa metadata mù quáng.

**Ghi nhớ:** test local partitioning không dừng ở `job.getStatus() == COMPLETED`. Một hệ thống Spring Batch mở rộng đúng cần **phân vùng xác định không trùng/không thiếu, worker execution thật sự đồng thời, reader state tách biệt, writer idempotent, JobRepository metadata nhất quán và recovery khi transaction lỗi**. Hãy phối hợp **unit/property test của Partitioner, integration test với DB thật và barrier, fault/restart test cùng JobInstance, whole-JVM crash test và load measurements** để chứng minh cả **độ đúng dữ liệu lẫn lợi ích mở rộng thực tế**.
