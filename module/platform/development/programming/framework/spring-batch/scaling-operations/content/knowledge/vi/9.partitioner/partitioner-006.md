# Chia theo dòng dữ liệu

**Chia theo dòng dữ liệu (row/record partitioning)** là chiến lược phân phối các **bản ghi logic** của một tập đầu vào thành những phần việc độc lập để nhiều worker Spring Batch xử lý đồng thời. Thay vì chia theo khoảng khóa chính hoặc giao nguyên một file cho một worker, ta chia theo **số thứ tự bản ghi, nhóm dòng hoặc nhóm record đã được xác định**. Ví dụ, một snapshot có 10.000 bản ghi được chia thành các khoảng số thứ tự `[1, 2501)`, `[2501, 5001)`, `[5001, 7501)` và `[7501, 10001)`.

Bài học thuộc chương **Partitioner** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn thông qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Chủ đề ở đây tập trung vào **tính đúng đắn của ranh giới dòng, cách tạo bản chụp dữ liệu ổn định, cách đọc đúng vùng được giao và bảo đảm khôi phục khi worker gặp lỗi**.

> **Quy ước của bài:** “dòng dữ liệu” là một **record nghiệp vụ** được parser/reader trả về; nó không nhất thiết tương ứng một hàng văn bản trên đĩa. Một bản ghi CSV có trường được đặt trong dấu ngoặc kép chứa ký tự xuống dòng có thể chiếm nhiều dòng vật lý.

## 1. Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Phân biệt **row/record partitioning**, **phân vùng theo khóa chính**, **phân vùng theo file** và **multi-threaded step**.
2. Định nghĩa ranh giới nửa mở `[startInclusive, endExclusive)` để không giao trùng hoặc bỏ sót số thứ tự bản ghi.
3. Tạo một tập bản ghi có số thứ tự **ổn định** bằng bảng staging hoặc manifest/snapshot, rồi xây `Partitioner` cung cấp vùng dữ liệu cho worker.
4. Cấu hình worker `@StepScope` với `JdbcPagingItemReader`, `ItemProcessor` và `ItemWriter` trong Spring Batch 5.x.
5. Giải thích vì sao `ROW_NUMBER()` tính lại trên bảng đang thay đổi, `OFFSET` lớn hoặc chia trực tiếp theo ký tự xuống dòng có thể gây sai dữ liệu hay giảm hiệu năng.
6. Kiểm thử độ phủ, thứ tự, dữ liệu thiếu/trùng, rollback, restart và tác động nghiệp vụ idempotent.
7. Chọn số partition và số thread theo khối lượng công việc thực, độ lệch chi phí mỗi record, CPU, I/O và khả năng của JobRepository/DB.

**Tình huống xuyên suốt:** một hệ thống cần xử lý khoảng 1,2 triệu giao dịch bán hàng mỗi đêm. Khóa nghiệp vụ có thể thưa hoặc không liên tiếp, dữ liệu đến từ nhiều tệp và bảng nguồn; mỗi giao dịch cần chuẩn hóa giá trị và ghi vào bảng đích. Mục tiêu là tạo một snapshot gồm đúng N bản ghi rồi phân công các **khoảng ordinal** cho những worker độc lập.

## 2. “Dòng dữ liệu” có những cách hiểu nào?

| Nguồn dữ liệu | “Dòng” có thể là | Cách chia phù hợp | Điều cần tránh |
| --- | --- | --- | --- |
| Bảng quan hệ | Một hàng theo điều kiện truy vấn và snapshot | Gán `row_no` ổn định trong staging rồi chia khoảng | Tính `ROW_NUMBER()` lại độc lập ở mỗi worker trên nguồn động |
| CSV đơn giản | Một record trên một dòng văn bản | Chia theo record index hoặc tạo nhiều shard bất biến | Mỗi worker tự bỏ qua hàng triệu dòng từ đầu file |
| CSV chuẩn có quoted newline | Một record có thể chiếm nhiều dòng vật lý | Parser đúng chuẩn tạo record index/manifest | Cắt file ở mỗi ký tự `\n` |
| JSON Lines / NDJSON | Thường một JSON object/record trên một dòng | Chia theo ranh giới dòng, khi hợp đồng format bảo đảm | Cắt byte offset giữa ký tự UTF-8 hoặc JSON object |
| Log/sự kiện | Một sự kiện với ID hoặc offset | Chia theo segment, source offset hoặc snapshot của stream | Coi offset chưa commit như dữ liệu đã xử lý xong |

Trong bài, phần triển khai chính dùng **row ordinal của bảng staging** vì có thể minh họa đầy đủ một `Partitioner`, reader, transaction và restart. Cuối bài có phần riêng dành cho file/CSV và những ranh giới của record trên storage.

## 3. Luồng thực thi của một row Partitioner

`Partitioner.partition(gridSize)` tạo `Map<String, ExecutionContext>`. Mỗi entry chứa ranh giới bản ghi, sau đó một `PartitionHandler` điều phối `StepExecution` của worker. Worker nhận `ExecutionContext`, đọc đúng khoảng được giao, xử lý theo chunk và commit kết quả.

~~~mermaid
flowchart TD
    S["Snapshot đã chốt: N record"] --> M["Manager Step"]
    M --> P["RowOrdinalPartitioner"]
    P --> A["partition0: row [1, 2501)"]
    P --> B["partition1: row [2501, 5001)"]
    P --> C["partition2: row [5001, 7501)"]
    P --> D["partition3: row [7501, 10001)"]
    A --> WA["Worker StepExecution A"]
    B --> WB["Worker StepExecution B"]
    C --> WC["Worker StepExecution C"]
    D --> WD["Worker StepExecution D"]
    WA --> DB[("Bảng kết quả")]
    WB --> DB
    WC --> DB
    WD --> DB
~~~

Sơ đồ dùng N = 10.000 để dễ nhìn. **Local partitioning** thực thi worker trên thread pool của cùng JVM; **remote partitioning** có thể phân phối worker sang tiến trình hoặc máy khác. Cách tính ranh giới vẫn hữu ích ở cả hai, nhưng remote partitioning cần thêm middleware, cơ chế phản hồi, metadata chung và quản lý mất kết nối.

**Không nhầm lẫn:**

- `gridSize` là số vùng công việc mà manager đề nghị; Partitioner quyết định số entry thực trả về.
- Số partition không đồng nghĩa số worker chạy đồng thời; executor/handler giới hạn concurrency.
- Chunk size là số item được xử lý trong một transaction của **mỗi worker**; nó khác độ rộng partition.
- Trong partitioning, mỗi vùng có **StepExecution riêng**, thuận lợi cho thống kê và restart; multi-threaded step sử dụng nhiều thread trong **một StepExecution**.

## 4. Quy ước khoảng dòng nửa mở

Giả sử snapshot có N bản ghi và được đánh số **1, 2, ..., N** theo một quy tắc duy nhất. Ta dùng:

~~~text
[fromRowInclusive, toRowExclusive)

WHERE row_no >= :fromRowInclusive
  AND row_no <  :toRowExclusive
~~~

Ví dụ N = 10 và `gridSize = 3`:

| Partition | Khoảng | Ordinal được xử lý |
| --- | --- | --- |
| `partition0` | `[1, 5)` | 1, 2, 3, 4 |
| `partition1` | `[5, 9)` | 5, 6, 7, 8 |
| `partition2` | `[9, 11)` | 9, 10 |

Ba **bất biến (invariants)** bắt buộc:

1. **Đủ miền:** khoảng đầu bắt đầu ở 1, khoảng cuối kết thúc ở N + 1.
2. **Không chồng lấn:** `toRowExclusive(i) == fromRowInclusive(i + 1)`, với các partition sắp theo thứ tự.
3. **Không rỗng/đảo:** `fromRowInclusive < toRowExclusive` trong mỗi partition được tạo.

Nhờ điều kiện SQL `row_no >= from AND row_no < to`, một ordinal nằm ở điểm giáp ranh chỉ thuộc **partition phía sau**. Nếu một worker dùng `<= to` trong khi worker khác dùng `>= from`, ordinal biên có thể bị đọc hai lần.

### Công thức chia đều theo số dòng

Với `N > 0` và `gridSize > 0`, độ rộng mỗi partition:

~~~text
width = ceil(N / gridSize)
      = N / gridSize + (N % gridSize == 0 ? 0 : 1)
~~~

Lần lượt lấy tối đa `width` ordinal từ 1 đến N, cắt khoảng cuối ở `N + 1`. Dùng công thức với phép chia và số dư thay vì `(N + gridSize - 1) / gridSize` để tránh tràn số trong biểu thức cộng.

Nếu `N < gridSize`, tạo tối đa N partition hữu ích, mỗi partition một dòng. Nếu `N = 0`, ứng dụng nên định nghĩa nhánh **không có công việc** trước khi gọi manager partitioning; không giả lập dòng dữ liệu không tồn tại.

## 5. Tại sao phải chốt thứ tự trước khi chia dòng?

Câu truy vấn sau **không** định nghĩa thứ tự ổn định:

~~~sql
SELECT *
FROM inbound_order
WHERE business_date = :business_date;
~~~

Nếu một worker gọi câu này rồi tính “dòng thứ 1..1000”, còn worker khác làm như vậy lúc dữ liệu hoặc query plan đã thay đổi, họ có thể đánh số bản ghi khác nhau. Ngay cả `ORDER BY id` cũng chưa đủ nếu **bảng nguồn đang được sửa/chèn/xóa** giữa các worker và restart.

Một mẫu cần tránh:

~~~sql
-- Mỗi worker tự đánh số trên bảng nguồn đang thay đổi.
SELECT *
FROM (
    SELECT ROW_NUMBER() OVER (ORDER BY created_at) AS row_no,
           id, gross_total
    FROM inbound_order
) AS dynamic_rows
WHERE row_no >= :from
  AND row_no <  :to;
~~~

Vấn đề:

- `created_at` có thể không duy nhất; hai bản ghi cùng timestamp không có thứ tự xác định nếu thiếu tie-break.
- Bảng live có thể thay đổi giữa các truy vấn; row_no của bản ghi cũ có thể dịch chuyển.
- `ROW_NUMBER()` phải tính trên một tập đủ lớn mỗi lần chạy; nhiều worker có thể lặp cùng chi phí sort/window.
- Nếu điều kiện lọc hoặc source cutoff thay đổi trong lần restart, vùng `row_no` cũ không còn tương ứng tập đầu vào ban đầu.

**Thiết kế an toàn hơn:** làm một bước **materialize snapshot/manifest** trước, ghi từng record với `row_no` duy nhất và bất biến vào staging; tất cả worker đọc chung staging snapshot đó. Thứ tự gán ordinal phải có tie-break là khóa duy nhất, chẳng hạn `ORDER BY event_time, id`.

## 6. Tạo bảng staging chứa row ordinal bất biến

Ví dụ PostgreSQL. Bảng nguồn chứa giao dịch; bảng staging chứa **bản chụp dữ liệu cần xử lý của một batch logic**, cả ID lẫn giá trị nghiệp vụ:

~~~sql
CREATE TABLE inbound_order (
    id            BIGINT PRIMARY KEY,
    business_date DATE NOT NULL,
    gross_total   NUMERIC(18, 2) NOT NULL
);

CREATE TABLE staged_order (
    batch_key   VARCHAR(100) NOT NULL,
    row_no      BIGINT NOT NULL,
    source_id   BIGINT NOT NULL,
    gross_total NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, row_no),
    UNIQUE (batch_key, source_id)
);

CREATE TABLE normalized_order (
    batch_key  VARCHAR(100) NOT NULL,
    source_id  BIGINT NOT NULL,
    net_total  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, source_id)
);
~~~

Một lần **chuẩn bị input** độc lập chụp tập hàng vào staging:

~~~sql
INSERT INTO staged_order(batch_key, row_no, source_id, gross_total)
SELECT :batch_key,
       ROW_NUMBER() OVER (ORDER BY id) AS row_no,
       id,
       gross_total
FROM inbound_order
WHERE business_date = :business_date;
~~~

Các điểm quan trọng:

- `id` là **primary key**, nên `ORDER BY id` xác định thứ tự duy nhất cho snapshot này.
- Trong PostgreSQL, câu `INSERT ... SELECT` chạy với một snapshot MVCC nhất quán trong phạm vi statement. Dữ liệu đã được sao chép vào `staged_order` thì không phụ thuộc những update sau đó ở `inbound_order`, miễn là **không sửa staging của batch đang chạy**.
- Không chạy lại câu `INSERT` trên cùng `batch_key` khi restart; unique constraints có thể bắt lỗi, nhưng quan trọng hơn là **tập snapshot phải giữ nguyên**.
- Nếu dữ liệu có nhiều cột cần xử lý, hãy copy những cột đó hoặc lưu một **source version/snapshot ID** được bảo đảm bất biến. Chỉ lưu `source_id` rồi worker đọc lại giá trị biến động từ bảng live có thể phá tính nhất quán.
- Khối lượng dữ liệu staging có chi phí lưu trữ/ghi/index. Đây là **đổi không gian lấy tính tái lập và khả năng chia đồng đều theo record count**.

Đếm số row **sau khi staging đã commit**:

~~~sql
SELECT COUNT(*) AS total_rows
FROM staged_order
WHERE batch_key = :batch_key;
~~~

Lưu `batchKey`, `totalRows` và phiên bản/cách tạo snapshot trong manifest/job parameters bền vững. Với job này, lấy `totalRows` lúc khởi chạy và **giữ cố định** trên các lần restart của cùng JobInstance. Đừng để mỗi worker tự tính lại COUNT trên nguồn đang thay đổi.

### Trường hợp số dòng quá lớn

`ROW_NUMBER()` trên PostgreSQL trả `bigint`. Thuật toán mẫu ở phần sau sử dụng `long`, yêu cầu `1 <= totalRows < Long.MAX_VALUE` để có thể tạo cận `totalRows + 1`. Tập dữ liệu quá lớn hoặc cần mô tả cận tối đa bằng `Long.MAX_VALUE` phải chọn kiểu số/ràng buộc khác. Không âm thầm tràn `long` tại cận cuối.

## 7. RowOrdinalPartitioner cho Spring Batch 5.x

Một `Partitioner` nên chỉ phân chia **metadata đã chốt**, không tự quét bảng nguồn live trong mỗi lần worker khởi chạy. Lớp sau dùng Java 17+, nhận `totalRows` từ snapshot và sinh map `partitionName -> ExecutionContext`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class RowOrdinalPartitioner implements Partitioner {
    private final long totalRows;

    public RowOrdinalPartitioner(long totalRows) {
        if (totalRows <= 0 || totalRows == Long.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "Require 1 <= totalRows < Long.MAX_VALUE");
        }
        this.totalRows = totalRows;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long width = totalRows / gridSize
                + (totalRows % gridSize == 0 ? 0L : 1L);
        long endExclusive = Math.addExact(totalRows, 1L);

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long from = 1L;
        int index = 0;

        while (from < endExclusive) {
            long remaining = endExclusive - from;
            long to = from + Math.min(width, remaining);

            ExecutionContext context = new ExecutionContext();
            context.putLong("fromRowInclusive", from);
            context.putLong("toRowExclusive", to);
            result.put("partition" + index++, context);

            from = to;
        }
        return result;
    }
}
~~~

**Ví dụ kết quả** với `totalRows = 10` và `gridSize = 3`:

~~~text
partition0: fromRowInclusive=1, toRowExclusive=5
partition1: fromRowInclusive=5, toRowExclusive=9
partition2: fromRowInclusive=9, toRowExclusive=11
~~~

`LinkedHashMap` giúp tên partition được tạo có thứ tự dễ kiểm tra; runtime **không bảo đảm thứ tự các worker hoàn thành**. Tên `partition0`, `partition1` gắn với vùng ordinal cố định, nên phải giữ `totalRows`, `gridSize`, thuật toán và các tham số định danh ổn định trong một JobInstance, đặc biệt qua restart.

Với N = 1 và gridSize = 8, Partitioner trả một vùng `[1,2)`, không tạo bảy StepExecution rỗng. Với số partition nhiều hơn thread pool, worker được xếp lịch theo khả năng executor; số entry trong map **không phải** số thread chạy cùng lúc.

## 8. Reader theo ordinal cho từng worker

Worker chỉ được đọc những record có `row_no` nằm trong khoảng đã giao. Ví dụ dùng `JdbcPagingItemReader` của Spring Batch 5.x. Đường truy vấn có index/primary key `(batch_key, row_no)` và sắp theo một khóa **duy nhất trong batch**.

~~~java
record StagedOrder(long rowNo, long sourceId, BigDecimal grossTotal) {}
record NormalizedOrder(long sourceId, BigDecimal netTotal) {}

@Bean
@StepScope
JdbcPagingItemReader<StagedOrder> stagedOrderReader(
        DataSource dataSource,
        @Value("#{jobParameters['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['fromRowInclusive']}") Long from,
        @Value("#{stepExecutionContext['toRowExclusive']}") Long to) {

    return new JdbcPagingItemReaderBuilder<StagedOrder>()
            .name("stagedOrderReader")
            .dataSource(dataSource)
            .selectClause("SELECT row_no, source_id, gross_total")
            .fromClause("FROM staged_order")
            .whereClause("""
                 WHERE batch_key = :batchKey
                   AND row_no >= :fromRow
                   AND row_no < :toRow
                 """)
            .sortKeys(Map.of("row_no", Order.ASCENDING))
            .parameterValues(Map.of(
                    "batchKey", batchKey,
                    "fromRow", from,
                    "toRow", to))
            .rowMapper((rs, rowNum) -> new StagedOrder(
                    rs.getLong("row_no"),
                    rs.getLong("source_id"),
                    rs.getBigDecimal("gross_total")))
            .pageSize(200)
            .saveState(true)
            .build();
}
~~~

**Vì sao paging thay vì OFFSET theo worker?**

- Reader dùng khóa sắp xếp `row_no` và điều kiện vùng, thuận lợi cho cơ chế phân trang dựa trên sort key.
- Truy vấn `WHERE batch_key = ? AND row_no BETWEEN ...` tận dụng index tương ứng, tránh bỏ qua lượng lớn dòng trước vùng được giao.
- Trong mỗi partition, `row_no` ổn định và duy nhất, giúp reader có cơ sở phục hồi vị trí theo metadata.
- Cấu hình `saveState(true)` có ý nghĩa khi input bất biến, tên ItemStream ổn định và JobRepository được lưu bền vững; nó **không tự cứu** một snapshot bị chỉnh sửa.

`@StepScope` tạo reader riêng theo **StepExecution**, không phải theo từng thread. Nhờ local partitioning có StepExecution riêng cho mỗi partition, các reader không chia sẻ cùng một state cursor. Nếu bật thêm multi-threaded step bên trong worker, phải đánh giá lại tính thread-safe và restart của chính reader.

### Vì sao không dùng LIMIT/OFFSET trực tiếp?

Một cách tưởng đơn giản là:

~~~sql
SELECT id, gross_total
FROM inbound_order
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

Ở những offset rất lớn, nhiều hệ quản trị phải duyệt/bỏ qua số lượng hàng đáng kể trước khi trả dữ liệu, làm các worker phía sau chậm hơn. Nếu nguồn live chèn/xóa row, cùng `OFFSET` có thể trả record khác trong lần truy vấn hoặc restart. Ngay cả khi đã có snapshot, `OFFSET` lớn vẫn có thể gây chi phí lặp; dùng **ordinal được index** hoặc **keyset/range** phù hợp thường dễ kiểm soát hơn.

## 9. Processor và writer: output phải ghi lặp an toàn

Processor mẫu là **stateless**: cùng một `StagedOrder` hợp lệ cho cùng một kết quả, không sửa state chia sẻ hoặc gửi side effect ngoài transaction:

~~~java
@Bean
ItemProcessor<StagedOrder, NormalizedOrder> normalizeOrder() {
    return row -> {
        if (row.grossTotal() == null ||
                row.grossTotal().signum() < 0) {
            throw new IllegalArgumentException(
                    "Invalid total for sourceId=" + row.sourceId());
        }

        return new NormalizedOrder(
                row.sourceId(),
                row.grossTotal().setScale(2, RoundingMode.HALF_UP));
    };
}
~~~

Writer dùng `(batch_key, source_id)` làm **khóa duy nhất**, vì row ordinal chỉ là vị trí trong snapshot, không phải khóa nghiệp vụ có thể sử dụng xuyên nhiều batch:

~~~java
@Bean
@StepScope
JdbcBatchItemWriter<NormalizedOrder> normalizedOrderWriter(
        DataSource dataSource,
        @Value("#{jobParameters['batchKey']}") String batchKey) {

    return new JdbcBatchItemWriterBuilder<NormalizedOrder>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO normalized_order(batch_key, source_id, net_total)
                 VALUES (:batchKey, :sourceId, :netTotal)
                 ON CONFLICT (batch_key, source_id)
                 DO UPDATE SET net_total = EXCLUDED.net_total
                 """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("batchKey", batchKey)
                            .addValue("sourceId", item.sourceId())
                            .addValue("netTotal", item.netTotal()))
            .build();
}
~~~

UPSERT cho phép cùng một record được xử lý lại mà không tạo thêm dòng kết quả. Tuy nhiên, **nếu input hoặc công thức thay đổi, UPSERT có thể ghi đè giá trị khác**. Do đó cần giữ snapshot và phiên bản quy tắc xử lý ổn định; khi có yêu cầu phát hiện conflict, lưu input version/hash hoặc dùng chính sách từ chối thay đổi ngoài dự kiến.

Nếu nghiệp vụ cần trừ tiền, gửi email hay publish event ngoài DB, không thể xem UPSERT ở bảng kết quả là đủ. Hãy dùng **idempotency key** tại hệ thống nhận hoặc **transactional outbox** để quản lý side effect không cùng transaction với kết quả.

## 10. Ghép vào local partitioning Step

Worker xử lý theo chunk 200 item; manager tạo các StepExecution và điều phối qua `ThreadPoolTaskExecutor`. Ví dụ dùng Spring Batch 5.x/Java 17+ và giả định JobRepository, DataSource, PlatformTransactionManager đã được cấu hình:

~~~java
@Bean
@StepScope
Partitioner rowPartitioner(
        @Value("#{jobParameters['totalRows']}") Long totalRows) {
    return new RowOrdinalPartitioner(totalRows);
}

@Bean
Step rowWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Qualifier("stagedOrderReader") ItemReader<StagedOrder> reader,
        @Qualifier("normalizeOrder")
                ItemProcessor<StagedOrder, NormalizedOrder> processor,
        @Qualifier("normalizedOrderWriter")
                ItemWriter<NormalizedOrder> writer) {

    return new StepBuilder("rowWorkerStep", jobRepository)
            .<StagedOrder, NormalizedOrder>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
ThreadPoolTaskExecutor rowPartitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("row-partition-");
    executor.initialize();
    return executor;
}

@Bean
Step rowManagerStep(
        JobRepository jobRepository,
        @Qualifier("rowWorkerStep") Step workerStep,
        @Qualifier("rowPartitioner") Partitioner partitioner,
        @Qualifier("rowPartitionExecutor") TaskExecutor taskExecutor) {

    return new StepBuilder("rowManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(taskExecutor)
            .build();
}

@Bean
Job rowJob(JobRepository jobRepository,
           @Qualifier("rowManagerStep") Step managerStep) {
    return new JobBuilder("rowJob", jobRepository)
            .start(managerStep)
            .build();
}
~~~

**Các giả định cần được thỏa trước khi chạy:**

- Batch staging đã được tạo và **commit xong** trước khi `rowJob` bắt đầu.
- JobParameters `batchKey` (String) và `totalRows` (Long) lấy từ chính batch staging đó, không thay đổi giữa các lần restart.
- `totalRows > 0`; trường hợp đầu vào rỗng phải được xử lý bằng bước điều phối/no-op do ứng dụng định nghĩa.
- Các bean reader, writer và Partitioner trong ví dụ là proxy `@StepScope`, nhận đúng ExecutionContext tại runtime.
- `gridSize=4` yêu cầu tối đa bốn vùng hữu ích từ Partitioner; số worker đồng thời còn phụ thuộc thread pool và tài nguyên.

Các import đã được lược bớt để tập trung vào thiết kế; mã cần được ghép vào cấu hình Spring Boot/Spring Batch tương thích. Trong ứng dụng thực, job tạo snapshot có thể là một job chuẩn bị riêng, hoặc một bước bền vững **trước** manager; quan trọng là restart không tự tính lại ordinal cho cùng JobInstance.

## 11. Chia theo dòng trong file: bẫy vật lý và logic

Với file text, cần phân biệt:

~~~text
Dòng vật lý trên đĩa: phân cách bằng LF hoặc CRLF
Record logic: một phần tử mà parser trả về cho nghiệp vụ
Ordinal: vị trí record sau khi tập input đã được chốt
Byte offset: vị trí byte trong file; không đồng nghĩa record index
~~~

Ví dụ CSV hợp lệ có một record chiếm nhiều dòng vật lý:

~~~csv
order_id,customer_note,amount
O-1,"giao sau 18:00",100.00
O-2,"khách dặn:
gọi điện trước",200.00
O-3,"giao bình thường",300.00
~~~

File có **năm dòng vật lý** nhưng chỉ có **ba record dữ liệu** sau header. Nếu chia file bằng cách đếm ký tự xuống dòng rồi đưa từ dòng vật lý 3 sang worker khác, worker đó có thể nhận phần giữa của record O-2 và parse sai.

Đối với **NDJSON** hoặc CSV đơn giản được hợp đồng dữ liệu bảo đảm mỗi record trên một dòng, có thể tạo manifest theo line index/byte offset; nhưng vẫn cần xét:

- UTF-8 ký tự nhiều byte, BOM, CRLF/LF và file nén (gzip stream không dễ random seek).
- Dòng cuối không có newline, file rỗng hoặc chỉ có header.
- Dòng comment/blank có được coi là record không; parser bỏ qua thế nào.
- File bất biến từ lúc xây index đến lúc worker đọc/restart.
- Worker phải **dừng đúng cuối vùng**, không tự đọc qua các record được giao cho worker khác.

### Hai chiến lược thực tế cho file lớn

**A. Tách file thành các shard bất biến:** một bước chuẩn bị đọc file bằng parser đúng định dạng, ghi các file con theo **record boundary**, tạo manifest với `fileId`, `recordCount`, checksum/version. Sau đó dùng một file/partition. Cách này tốn I/O và disk staging nhưng đơn giản, dễ restart và dễ test.

**B. Tạo record-offset index:** bước chuẩn bị dùng parser biết chính xác điểm bắt đầu/kết thúc record, lưu offset phù hợp; worker có custom reader seek tới vị trí đã định rồi dừng ở cuối vùng. Cần kiểm thử kỹ encoding, file codec, restart, cùng chi phí lưu index. Không thể dùng `RandomAccessFile.seek()` theo số thứ tự dòng nếu chưa có offset.

### Tại sao chỉ dùng FlatFileItemReader.linesToSkip không đủ?

`linesToSkip(n)` thường phục vụ **bỏ header hoặc dòng đầu của một tài nguyên**; nó không tự đảm bảo giới hạn “chỉ đọc tới record K rồi dừng”, cũng không giải quyết chuẩn CSV có embedded newline. Mỗi worker dùng cùng một file và bỏ qua N dòng đầu còn có thể tốn I/O tỷ lệ với phần cần bỏ qua. Nếu phải chia nội file, hãy thiết kế reader theo **record index/bounds** hoặc tiền xử lý thành shard rồi kiểm thử toàn vẹn.

## 12. Khi nào chia theo ordinal tốt hơn theo khóa chính?

| Tình huống | Ordinal row partitioning | PK range partitioning |
| --- | --- | --- |
| PK thưa, ID có khoảng trống lớn | Có thể cân bằng **số record** khi staging dày từ 1..N | Chia độ rộng ID có thể tạo nhiều vùng gần rỗng |
| PK tuần tự, index tốt, nguồn đã chốt | Cần thêm chi phí gán/staging ordinal | Có thể đọc trực tiếp theo range tiết kiệm chuẩn bị |
| Nguồn kết hợp nhiều bảng/file | Manifest/ordinal chung dễ quản lý vùng record | Không phải nguồn nào cũng có PK cùng kiểu |
| Worker xử lý không đều theo record | Cân đều số record nhưng vẫn có skew **chi phí** | Cũng có thể lệch do dữ liệu/chi phí |
| Dữ liệu nguồn thường xuyên thay đổi | Cần snapshot bất biến hoặc staging | Cũng cần snapshot/cutoff hợp lệ |
| Yêu cầu restart chính xác | Ordinal ổn định giúp xác định vùng và kiểm thử độ phủ | PK range ổn định cũng hỗ trợ nếu nguồn phù hợp |

Ordinal hữu ích nhất khi muốn chia **số lượng record gần đều**, đặc biệt khi khóa tự nhiên thưa hoặc không phù hợp để tính khoảng. Nhưng để làm được vậy, ta phải trả chi phí tạo và lưu bản snapshot/ordinal. Nếu có sẵn nguồn ổn định với PK tốt, chia khoảng PK có thể nhanh hơn vì tránh bước staging.

### Chiến lược round-robin bằng modulo

Một biến thể dùng `MOD(row_no - 1, P) = partitionIndex` để phân bổ record xen kẽ:

~~~text
P = 3
worker 0: row 1, 4, 7, 10, ...
worker 1: row 2, 5, 8, ...
worker 2: row 3, 6, 9, ...
~~~

Modulo có thể phân tán chi phí nếu record nặng tập trung liền nhau, nhưng đổi lại:

- SQL modulo có thể không tận dụng range scan/index như `[from, to)`, tùy DB và thiết kế dữ liệu.
- `P` và quy tắc phân bổ phải ổn định khi restart; đổi P sẽ thay owner của rất nhiều record.
- Mỗi worker có thể quét nhiều vùng dữ liệu hoặc gây random I/O.
- Nếu processor cần thứ tự liên tục theo một khóa nghiệp vụ, round-robin có thể phá ràng buộc đó.

Không lựa chọn modulo chỉ vì trông phân bố đều; cần đo truy vấn và chi phí thực.

## 13. Cân bằng theo số bản ghi chưa chắc cân bằng thời gian

Cho hai partition đều có 100.000 record:

- Vùng A gồm giao dịch đơn giản, mỗi item cần 1 ms.
- Vùng B gồm giao dịch phải gọi service ngoài, mỗi item cần 50 ms.

Hai vùng có row count bằng nhau nhưng thời gian xử lý có thể chênh lệch rất lớn. Tổng thời gian job thường bị chi phối bởi **worker/partition chậm nhất**, cộng overhead và tranh chấp tài nguyên.

Các chiến lược giảm skew:

1. **Tạo nhiều partition nhỏ hơn số thread:** ví dụ 32 vùng cho pool 4 thread. Khi một worker hoàn thành vùng ngắn, nó có thể xử lý vùng còn lại.
2. **Chia theo ước lượng chi phí:** manifest của mỗi record/nhóm lưu loại nghiệp vụ, số field, size hoặc thời gian xử lý lịch sử; cân bằng **expected work** thay vì chỉ COUNT(*).
3. **Nhóm theo business key:** khi record cùng tài khoản phải xử lý tuần tự, phân nhóm theo account/tenant thay vì cắt ngẫu nhiên theo ordinal.
4. **Dùng loại nguồn phù hợp:** dữ liệu có key ổn định và query range nhanh có thể dùng PK range; file lớn có thể tiền-shard; sự kiện liên tục cần cơ chế streaming/claim riêng.

Tăng concurrency vô hạn không xử lý được skew hoặc database lock. Cần đo thời gian từng partition, CPU, heap, DB connection pool, I/O và lock wait.

## 14. Thread safety, transaction và StepExecution

Row partitioning thường cho mỗi worker một **StepExecution** và một reader riêng qua `@StepScope`. Tuy vậy, processor/writer singleton hoặc service dùng chung vẫn có thể bị nhiều worker gọi đồng thời.

| Thành phần | Nguyên tắc | Rủi ro cần thử |
| --- | --- | --- |
| Partitioner | Tính bounds từ `totalRows` bất biến, không cập nhật dữ liệu nguồn | Tên/biên thay đổi giữa các lần restart |
| Reader | `@StepScope`, sắp xếp ổn định, đọc đúng range | State cursor/paging bị chia sẻ hoặc đọc quá biên |
| Processor | Stateless, deterministic hoặc dependency thread-safe | Shared counter/cache, gọi API ngoài transaction |
| Writer | Transactional, unique business key, idempotency | Ghi trùng khi retry, update cạnh tranh |
| JobRepository | Bền vững, StepExecution và ExecutionContext riêng | Metadata sai/mất khi worker fail |
| DB pool | Dự phòng connection cho worker, metadata và tác vụ khác | Connection starvation/timeout |
| Snapshot | Bất biến, version/tổng số row đã chốt | Record dịch ordinal, checkpoint không còn phù hợp |

**Không đồng nhất “một record được đọc đúng một lần trong kế hoạch” với “processor chỉ được gọi một lần”.** Spring Batch có thể gọi lại processor sau lỗi/rollback/retry; job restart có thể đọc lại một phần công việc. Tính đúng đắn nằm ở **tác động cuối cùng của hệ thống**, không phải số lời gọi Java.

Nếu một worker có chunk size 200, 50.000 record trong partition tương ứng khoảng 250 chunk thành công lý tưởng; commitCount thực tế có thể khác do metadata, rollback, skip, retry và chunk cuối. Không gán trực tiếp “một partition = một transaction”.

## 15. Restart và rủi ro khi ordinal thay đổi

Khi job thất bại, Spring Batch dùng `JobRepository` để đánh giá `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`. Với partitioning, các partition đã COMPLETED thường không cần chạy lại theo hợp đồng step/restart; phần chưa hoàn tất tiếp tục dựa trên metadata và trạng thái reader tương ứng.

Để restart có ý nghĩa:

1. **Giữ JobParameters định danh** (`batchKey`, `totalRows`, snapshot/version) và tên partition.
2. **Giữ nguyên bảng staging** cùng tất cả row_no đã gán; không tính lại `ROW_NUMBER` trên nguồn live.
3. **Không đổi gridSize/thuật toán phân vùng** giữa các lần restart nếu điều đó đổi ánh xạ tên partition → khoảng row.
4. **Reader state** phải dùng đúng tên và input bất biến để checkpoint có thể áp dụng lại.
5. **Writer idempotent**, hoặc có đối soát và cơ chế bù; đừng phụ thuộc vào giả định “mỗi item đúng một lần” qua mọi hệ thống.

### Ví dụ lỗi sau commit một phần

~~~text
partition1: [2501, 5001), chunk size 200

chunk 1..8: đã commit 1.600 item
chunk 9: lỗi DB, transaction rollback
StepExecution partition1: FAILED

Restart cùng JobInstance:
- dùng lại row_no và bounds của partition1
- tiếp tục theo reader checkpoint đã lưu, hoặc replay phần cần thiết
- writer không nhân đôi kết quả có cùng (batch_key, source_id)
- đối soát đủ row_no 2501..5000 và business value
~~~

Đây là ví dụ khái niệm, không hứa rằng mọi implementation luôn resume ở đúng item thứ 1.601. Vị trí thực tế phụ thuộc reader, transaction, cách lưu ExecutionContext và trạng thái từng chunk. Kiểm chứng bằng test failure injection trên đúng DB/reader của ứng dụng.

Nếu một partition báo STARTED nhưng worker không còn sống sau sự cố, cần xác định trạng thái thực tế trước khi kích hoạt lại; không sửa trực tiếp bảng metadata của Spring Batch để ép COMPLETED nếu chưa đối soát.

## 16. Unit test toán học cho Partitioner

Vì `RowOrdinalPartitioner` không phụ thuộc Spring context và DB, có thể kiểm thử trực tiếp JUnit 5:

~~~java
@Test
void coversTenRecordsExactlyOnceAcrossThreePartitions() {
    Map<String, ExecutionContext> parts =
            new RowOrdinalPartitioner(10L).partition(3);

    assertEquals(List.of("partition0", "partition1", "partition2"),
            new ArrayList<>(parts.keySet()));
    assertEquals(3, parts.size());

    long expectedFrom = 1L;
    for (ExecutionContext context : parts.values()) {
        long from = context.getLong("fromRowInclusive");
        long to = context.getLong("toRowExclusive");

        assertEquals(expectedFrom, from);
        assertTrue(to > from);
        expectedFrom = to;
    }
    assertEquals(11L, expectedFrom);
}

@Test
void gridLargerThanRecordsDoesNotCreateEmptyPartitions() {
    Map<String, ExecutionContext> parts =
            new RowOrdinalPartitioner(2L).partition(8);

    assertEquals(2, parts.size());
    assertEquals(1L, parts.get("partition0")
                         .getLong("fromRowInclusive"));
    assertEquals(3L, parts.get("partition1")
                         .getLong("toRowExclusive"));
}

@Test
void rejectsInvalidDomain() {
    assertThrows(IllegalArgumentException.class,
            () -> new RowOrdinalPartitioner(0L));
    assertThrows(IllegalArgumentException.class,
            () -> new RowOrdinalPartitioner(Long.MAX_VALUE));
    assertThrows(IllegalArgumentException.class,
            () -> new RowOrdinalPartitioner(10L).partition(0));
}
~~~

**Property-based testing** có thể tạo nhiều bộ `(N, gridSize)` ngẫu nhiên nhỏ và kiểm tra: mọi `row_no` từ 1 đến N thuộc đúng một khoảng, không khoảng rỗng, điểm đầu/cuối đúng và số partition không vượt `min(N, gridSize)`. Với N nhỏ, có thể đếm trực tiếp mỗi ordinal được bao nhiêu khoảng chứa:

~~~java
for (long rowNo = 1; rowNo <= totalRows; rowNo++) {
    final long ordinal = rowNo;
    long owners = parts.values().stream()
            .filter(ctx -> ctx.getLong("fromRowInclusive") <= ordinal
                    && ordinal < ctx.getLong("toRowExclusive"))
            .count();
    assertEquals(1L, owners);
}
~~~

Đoạn property này chỉ nên chạy trên **miền nhỏ** trong unit test, không phải lặp tới hàng tỷ row. Nó xác minh thuật toán chia; dữ liệu đầu ra đúng hay không vẫn cần integration test.

## 17. Integration test: dữ liệu thưa, đồng thời và đối soát

Hãy dùng database thử nghiệm tương đương production (ví dụ PostgreSQL qua Testcontainers), tạo nguồn có ID thưa:

~~~text
source_id:  3, 9, 17, 100, 101, 7000, 9000, 20000, 20002, 55000
row_no:    1, 2,  3,   4,   5,    6,    7,     8,     9,    10
~~~

Lần thử:

1. Materialize đúng 10 record vào staging theo `ORDER BY source_id`, xác nhận ordinal 1..10 liên tiếp.
2. Khởi chạy `rowJob` với `totalRows=10`, `gridSize=3`, pool ít nhất hai thread; log `partitionName`, `StepExecutionId`, `from/to`.
3. Kiểm tra các worker đọc đúng ba khoảng `[1,5)`, `[5,9)`, `[9,11)`; nếu không có filter/skip, kết quả có **đúng 10 source_id** với giá trị chuẩn hóa kỳ vọng.
4. Inject lỗi tạm thời ở writer khi một số chunk đã commit; xác minh rollback/restart không nhân đôi khóa và tất cả dữ liệu cuối đúng.
5. Cố sửa staging cùng `batchKey` trong môi trường test; quy trình bảo vệ snapshot phải phát hiện vi phạm thay vì âm thầm tiếp tục.
6. Thử `gridSize=1, 3, 16`; đầu ra phải giống nhau, dù số partition và thời gian thực thi khác.

Ví dụ truy vấn đối soát từ staging sang kết quả:

~~~sql
-- Những row nguồn được kỳ vọng nhưng chưa có output.
SELECT s.row_no, s.source_id
FROM staged_order AS s
LEFT JOIN normalized_order AS n
  ON n.batch_key = s.batch_key
 AND n.source_id = s.source_id
WHERE s.batch_key = :batch_key
  AND n.source_id IS NULL;

-- Output không có record nguồn tương ứng.
SELECT n.source_id
FROM normalized_order AS n
LEFT JOIN staged_order AS s
  ON s.batch_key = n.batch_key
 AND s.source_id = n.source_id
WHERE n.batch_key = :batch_key
  AND s.source_id IS NULL;
~~~

Ngoài so sánh tập khóa, hãy so sánh `net_total` với công thức nghiệp vụ, thống kê **readCount/writeCount/filterCount/skipCount/rollbackCount**, và các side effect nếu có. Khi nghiệp vụ cho phép filter/skip, cần xây tập output **kỳ vọng** theo chính sách ấy; không thể mặc định tổng row đích luôn bằng row nguồn.

## 18. Đo nút thắt và chọn kích thước partition

Chia theo ordinal cân đều **số record được giao**, nhưng không tự động chia đều tải CPU, kích thước dữ liệu hay số lần I/O. Một thí nghiệm nên giữ cùng snapshot và thay đổi số partition, số worker cùng chunk size một cách có kiểm soát:

| Thử nghiệm | `gridSize` | Worker pool | Chunk size | Điều cần đo |
| --- | --- | --- | --- | --- |
| A | 1 | 1 | 200 | Baseline throughput, commit latency |
| B | 4 | 2 | 200 | Có đạt overlap thực, DB pool có chờ? |
| C | 4 | 4 | 200 | CPU, I/O, DB lock và throughput |
| D | 16 | 4 | 200 | Partition nhỏ có giảm skew hay thêm overhead? |
| E | 16 | 8 | 200 | Giới hạn DB/JobRepository và GC |
| F | 16 | 4 | 500 | Commit overhead so với rollback/memory |

Theo dõi:

- **Per partition:** số dòng được giao, read/write/filter/skip, commit/rollback, duration và tốc độ item/giây.
- **Per executor:** active threads, queue depth, rejection, thời gian chờ lịch.
- **Per DB:** query plan/index scan, page latency, connection wait, lock wait, transaction duration.
- **Per JVM:** CPU, heap, allocation, GC pause, thread contention.
- **Snapshot stage:** thời gian tạo và dung lượng staging, chi phí dọn dữ liệu khi job hoàn tất/qua retention.

**Chi phí chuẩn bị snapshot phải được tính vào tổng thời gian pipeline.** Nếu việc materialize ordinal mất 20 phút nhưng tiết kiệm chỉ 5 phút xử lý, chia theo ordinal không mang lại lợi ích tổng thể. Trong một workload đã có PK index tốt, chia theo khoảng khóa có thể ít overhead hơn. Nếu một DB khác cần đọc snapshot của PostgreSQL, chi phí vận chuyển dữ liệu staging cũng có thể đáng kể.

Với workload có 1,2 triệu record, `chunk(200)` tương đương khoảng 6.000 chunk dữ liệu thành công lý tưởng trên toàn job (nếu không filter/skip); số commit thật có thể khác bởi chunk cuối, retry, rollback và metadata. Tăng số worker làm chi phí đồng thời lên DB cao hơn; cần dành connection cho các tác vụ khác.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Record ở ranh giới xuất hiện hai lần | Worker dùng `<= to` thay vì `< to` | Thống nhất `[from,to)`, test off-by-one |
| Thiếu record đầu/cuối | Row index bắt đầu 0 nhưng Partitioner bắt đầu 1, hoặc cận cuối tính sai | Chốt 1-based ordinal, kiểm tra N+1 |
| Cùng một source_id có hai ordinal | Snapshot truy vấn bị lặp do join nhiều-một | Unique constraint `(batch_key,source_id)`, xác định record logic |
| Restart sau khi source thêm hàng bị thiếu/trùng | Row number được tính lại trên nguồn live | Stage snapshot bất biến và reuse khi restart |
| Worker vùng cuối chậm khi dùng OFFSET | DB phải bỏ qua lượng lớn hàng | Dùng ordinal có index hoặc PK/keyset range |
| Chia đều row nhưng một partition rất chậm | Cost/item khác nhau hoặc lock/I/O tập trung | Tăng số vùng nhỏ hoặc cân bằng theo estimated cost |
| File CSV bị cắt giữa record | Nhầm newline vật lý với record boundary | Pre-shard bằng parser hoặc xây record-offset index |
| Reader restart sai vị trí | Input bị đổi, sort key không duy nhất, state name thay đổi | Snapshot ổn định, khóa sắp xếp duy nhất, kiểm thử recovery |
| Tăng thread nhưng throughput giảm | DB pool thiếu, nhiều lock, GC/I/O saturation | Đo bottleneck rồi giảm/tối ưu concurrency |
| Job báo COMPLETED nhưng số liệu sai | Processor/writer race hoặc skip/filter ngoài dự kiến | Đối soát record ID và business value |
| `totalRows=0` gây lỗi | Job chưa định nghĩa nhánh empty input | Preflight COUNT và no-op rõ ràng |
| Overflow khi `N + 1` | Không validate miền `long` | Giới hạn N, `Math.addExact` hoặc dùng representation khác |

## 20. Bài thực hành cuối bài và checklist

**Bài thực hành:** chuẩn bị snapshot gồm 100.000 bản ghi có source ID thưa, 10% bản ghi nặng gấp nhiều lần số còn lại. Cấu hình `RowOrdinalPartitioner`, `JdbcPagingItemReader` và writer idempotent; chạy thử trên cùng staging với `gridSize=1,4,16` và pool `1,2,4`.

Đầu ra yêu cầu:

1. Chứng minh bằng unit test mọi ordinal thuộc đúng một partition, kể cả khi `gridSize > N` hoặc `N` không chia hết.
2. Chứng minh bằng integration test mọi business key hợp lệ có kết quả đúng, không bị bỏ sót hay nhân đôi.
3. Tạo lỗi writer sau một số chunk đã commit; restart cùng JobInstance và đối soát đầu ra.
4. Thử một phiên bản sai có `ROW_NUMBER()` tính lại trên nguồn thay đổi và giải thích rủi ro mà snapshot tránh được.
5. Ghi số liệu per partition, CPU, DB wait, throughput và tổng chi phí snapshot để quyết định chia theo ordinal hay theo PK.

Checklist trước khi vận hành:

- [ ] Định nghĩa rõ **record logic**; không dùng số dòng vật lý tùy tiện với CSV có quoted newline.
- [ ] Có snapshot/manifest bất biến, sort key duy nhất, `row_no` liên tiếp từ 1 tới N.
- [ ] Chốt `batchKey`, `totalRows`, tên partition, `gridSize` và chính sách restart.
- [ ] Dùng ranh giới `[fromRowInclusive, toRowExclusive)` đồng nhất ở Partitioner và reader.
- [ ] Reader thuộc `@StepScope`, phân trang theo sort key ổn định; các dependency dùng chung thread-safe.
- [ ] Writer có transaction và idempotency theo business key; mọi side effect ngoài DB được bảo vệ.
- [ ] Có test dữ liệu thưa, trường hợp N nhỏ, biên cuối, rollback, restart và thay đổi snapshot bị cấm.
- [ ] Có metric per partition, executor queue, DB pool, I/O, thời gian chuẩn bị snapshot và worker chậm nhất.
- [ ] Chọn số partition, chunk size và thread pool từ dữ liệu thực; không mặc định nhiều thread luôn nhanh hơn.

**Ghi nhớ:** chia theo dòng dữ liệu chỉ an toàn khi mỗi “dòng” là **một record logic có định danh và thứ tự ổn định**, được giao vào **đúng một khoảng**. Partitioner quyết định ranh giới; `@StepScope` giúp worker đọc đúng vùng; checkpoint, nguồn bất biến và writer idempotent giữ kết quả đúng sau retry/restart. Hiệu quả mở rộng phụ thuộc tổng chi phí tạo snapshot, độ lệch công việc và tài nguyên DB/CPU/I/O, chứ không chỉ số row hay số worker.
