# Chia theo primary key range trong Spring Batch

## 1. Giới thiệu và mục tiêu

Trong chương **Chia dữ liệu** của module **SPRING_BATCH_SCALING_OPERATIONS**, một bài toán cơ bản là làm thế nào để xử lý hàng triệu bản ghi mà không buộc một step duy nhất đọc và ghi tất cả theo thứ tự. **Chia theo primary key range** (phân vùng theo khoảng khóa chính) giải quyết bài toán này bằng cách tạo nhiều phạm vi ID độc lập và giao mỗi phạm vi cho một worker.

Ví dụ bảng `orders_staging` có một triệu dòng với khóa chính số `id`. Thay vì một reader đọc từ đầu tới cuối, ta tạo bốn khoảng `[1, 250000]`, `[250001, 500000]`, `[500001, 750000]` và `[750001, 1000000]`. Mỗi worker step đọc các dòng thỏa điều kiện ID trong khoảng được giao. Nếu các worker đủ độc lập và tài nguyên đủ, chúng có thể chạy đồng thời qua `TaskExecutor` hoặc trên những process khác qua remote partitioning.

Bài này liên kết với mục tiêu của module: mở rộng Spring Batch qua **multi-threaded step, parallel steps, partitioning và xử lý phân tán**, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và chọn kiến trúc phù hợp với CPU, database, bộ nhớ và dịch vụ ngoài.

Sau bài học, bạn cần biết cách:

- Tính các khoảng khóa chính chính xác, không chồng lấn và không bỏ trống miền ID.
- Cấu hình `Partitioner`, `ExecutionContext`, `@StepScope` và worker step với Spring Batch.
- Xử lý khóa chính thưa, dữ liệu lệch, batch rỗng và trường hợp biên kiểu `BIGINT`.
- Giữ dữ liệu nguồn ổn định, bảo đảm transaction/restart và tránh xử lý trùng khi retry.
- Đánh giá số partition, số worker đồng thời, throughput và tài nguyên thực tế.

## 2. Range là gì? Quy ước biên và các bất biến

Với khóa chính kiểu số, một partition có thể được biểu diễn bằng `minId` và `maxId`. Trong bài này, sử dụng khoảng **bao gồm cả hai đầu mút**: `[minId, maxId]`.

```sql
SELECT id, customer_id, total_amount
FROM orders_staging
WHERE id >= :minId
  AND id <= :maxId
ORDER BY id ASC;
```

Điều kiện cần để chia đúng:

1. **Không overlap:** một ID thuộc tối đa một khoảng.
2. **Không có khoảng trống trong miền khóa:** cận dưới của partition sau bằng cận trên của partition trước cộng một.
3. **Bao phủ:** range đầu bắt đầu từ `MIN(id)`, range cuối kết thúc ở `MAX(id)` của tập đầu vào đã chọn.

Ví dụ có miền ID từ 101 đến 125, tổng 25 giá trị và muốn chia bốn phần. Ta chia lấy thương `q = 25 / 4 = 6` và dư `r = 25 % 4 = 1`; một partition đầu có 7 giá trị, các partition còn lại mỗi phần 6.

| Partition | Biên dưới | Biên trên | Độ rộng miền khóa |
| --- | ---: | ---: | ---: |
| partition0 | 101 | 107 | 7 |
| partition1 | 108 | 113 | 6 |
| partition2 | 114 | 119 | 6 |
| partition3 | 120 | 125 | 6 |

Tổng độ rộng là 25 và không có ID nào thuộc hai partition. Nếu dùng các khoảng `[1, 250]` rồi `[250, 500]` với truy vấn `BETWEEN`, ID 250 sẽ được đọc **hai lần**. Phải đổi khoảng thứ hai thành `[251, 500]` hoặc dùng quy ước khoảng nửa mở `[start, endExclusive)` nhất quán trong toàn bộ hệ thống.

**Phân biệt miền ID với số dòng:** một khoảng rộng 100.000 ID vẫn có thể chỉ chứa 10 bản ghi nếu rất nhiều ID bị xóa, không được cấp phát hoặc thuộc batch khác. Công thức chia đều khoảng khóa **không** mặc nhiên chia đều số record hay thời gian xử lý.

## 3. Kiến trúc Spring Batch partitioning

Spring Batch dùng một **manager step** để chia dữ liệu thành các partition; mỗi partition thường ứng với một `StepExecution` của cùng một worker step, nhưng có `ExecutionContext` riêng.

```text
             Job: importOrders
                    |
             managerStep
                    |
       OrderIdRangePartitioner
           /        |         \
      partition0 partition1 partition2 ...
       min/max    min/max    min/max
           \        |         /
            TaskExecutor (local)
           /        |         \
      workerStep workerStep workerStep
       Reader0    Reader1    Reader2
           |        |         |
          chunks + transactions riêng
                    |
        JobRepository / checkpoint
```

| Thành phần | Vai trò |
| --- | --- |
| `Partitioner.partition(gridSize)` | Trả về map tên partition → `ExecutionContext`, chứa cận ID và các thông số filter. |
| Manager step | Điều phối worker step, tổng hợp trạng thái và xử lý metadata phân vùng. |
| Worker step | Đọc, xử lý, ghi đúng range được giao; có `StepExecution` riêng. |
| `@StepScope` | Tạo/lấy bean reader theo StepExecution, binding các giá trị từ context ở runtime. |
| `TaskExecutor` | Cấp luồng thực thi các worker của **local partitioning** trong một JVM. |
| `JobRepository` | Lưu `JobExecution`, `StepExecution`, `ExecutionContext` và thông tin phục hồi. |

`gridSize` chỉ là gợi ý cho số partition mà `Partitioner` nên tạo. Executor có thể có ít luồng hơn. Ví dụ 20 partition và pool 4 thread có thể có bốn worker thực thi cùng lúc, những partition khác chờ đến lượt. **Không nhầm số partition với số thread**.

Local partitioning sử dụng luồng trong cùng một JVM; remote partitioning cần cơ chế trao đổi thông điệp, worker process riêng và quy tắc khôi phục khi mất message hoặc worker chết. `TaskExecutor` một mình không phân phối dữ liệu qua network.

Spring Batch partitioning cũng khác **database table partitioning**. Một `Partitioner` của Spring Batch chia công việc xử lý; nó không tự tạo phân mảnh lưu trữ, shard hay index trong database.

## 4. Điều kiện đầu vào: khóa chính, bộ lọc và snapshot

Ta dùng PostgreSQL và tập dữ liệu staged được chốt theo tham số `batchId`:

```sql
CREATE TABLE orders_staging (
    id            BIGINT PRIMARY KEY,
    batch_id      VARCHAR(80) NOT NULL,
    customer_id   BIGINT NOT NULL,
    total_amount  NUMERIC(18, 2) NOT NULL
);

CREATE INDEX idx_orders_staging_batch_id_id
    ON orders_staging (batch_id, id);
```

Một job instance xử lý, chẳng hạn, `batchId = nightly-2026-11-26`. Trước khi chạy, pipeline nạp dữ liệu cần **đóng băng membership** của batch này: không thêm, xóa, đổi `id` hoặc đổi `batch_id` của dòng thuộc batch trong khi job chạy hay restart. Đây là giả định quan trọng để đọc ổn định.

Lấy biên:

```sql
SELECT MIN(id) AS min_id, MAX(id) AS max_id
FROM orders_staging
WHERE batch_id = :batchId;
```

Sau khi chia thành các khoảng, mỗi worker đọc:

```sql
SELECT id, customer_id, total_amount
FROM orders_staging
WHERE batch_id = :batchId
  AND id >= :minId
  AND id <= :maxId
ORDER BY id ASC;
```

**Điều kiện lọc batch phải giống nhau** ở truy vấn lấy biên và truy vấn reader. Nếu quên `batch_id` trong worker, các bản ghi từ những batch khác có ID nằm trong range cũng có thể được đọc.

Cần kiểm tra các tiền đề trước khi chọn kỹ thuật:

- Khóa chính phải duy nhất, không đổi và có kiểu phù hợp cho range. `BIGINT`/`INTEGER` là trường hợp điển hình; UUID v4 không có mật độ và thứ tự hữu ích như khóa tự tăng.
- Query worker có index hỗ trợ. Index kép `(batch_id, id)` có thể giúp truy vấn lọc theo batch rồi duyệt khoảng ID; dùng `EXPLAIN (ANALYZE, BUFFERS)` để xác nhận với dữ liệu thực.
- Mỗi record độc lập hoặc các record phụ thuộc nhau được nhóm đúng vào cùng phạm vi; nếu nhiều worker cùng cập nhật một account/số dư, lock hoặc thứ tự nghiệp vụ có thể trở thành vấn đề.
- Có chiến lược giữ ổn định tập đầu vào khi xảy ra lỗi và restart.

Một cột `batch_id` đơn thuần **không** tự bảo đảm snapshot: phải có quy trình chuyển trạng thái batch từ nạp sang đã chốt, hoặc một bảng/list ID bất biến cho lần chạy. Chỉ dùng `MAX(id)` cũng không loại trừ khả năng có record backfill với ID nhỏ được thêm sau khi job bắt đầu.

## 5. Tính toán range không tràn số và không tạo khoảng rỗng

Với miền `[minId, maxId]`, tổng số giá trị nguyên về mặt toán học là:

\[
L = maxId - minId + 1
\]

Nếu muốn tạo `P` partition với `1 ≤ P ≤ L`, đặt:

\[
q = \lfloor L/P \rfloor,\qquad r = L\bmod P
\]

`r` partition đầu có độ rộng `q+1`, những partition sau có độ rộng `q`. Nhờ đó mọi độ rộng đều dương. Với kiểu `long`, phép `maxId - minId + 1` có thể overflow nếu miền quá lớn; có thể tính bằng `BigInteger` rồi chuyển từng cận (vốn nằm trong miền ID của database) về `long`.

Thuật toán có thể kiểm chứng bằng hai bất biến trong vòng lặp:

```text
lower[i] = cursor
upper[i] = cursor + width[i] - 1
cursor mới = upper[i] + 1
```

Độ rộng cộng lại là `r(q+1) + (P-r)q = L`. Từ đó range đầu nằm ở minId, range cuối kết thúc ở maxId và các range kế tiếp nhau không chồng lấn.

Nếu không có record, `MIN(id)` và `MAX(id)` trả về `NULL`: phải định nghĩa rõ batch rỗng (ví dụ không tạo worker partition và hoàn tất hợp lệ). Không thay `NULL` bằng 0 rồi vô tình đọc dữ liệu ngoài phạm vi.

## 6. Cài đặt Partitioner bằng Java

Ví dụ dùng **Spring Batch 5.x**, Java 17+ và PostgreSQL. Các đoạn code tập trung vào partitioning; ứng dụng cần thêm import, cấu hình datasource, JobRepository, transaction manager và domain writer.

```java
public final class OrderIdRangePartitioner implements Partitioner {

    private final JdbcTemplate jdbcTemplate;
    private final String batchId;

    public OrderIdRangePartitioner(JdbcTemplate jdbcTemplate, String batchId) {
        this.jdbcTemplate = jdbcTemplate;
        this.batchId = batchId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Map<String, Object> bounds = jdbcTemplate.queryForMap(
            """
            SELECT MIN(id) AS min_id, MAX(id) AS max_id
            FROM orders_staging
            WHERE batch_id = ?
            """,
            batchId
        );

        if (bounds.get("min_id") == null) {
            return Collections.emptyMap();  // Batch không có dòng nào.
        }

        long minId = ((Number) bounds.get("min_id")).longValue();
        long maxId = ((Number) bounds.get("max_id")).longValue();

        BigInteger one = BigInteger.ONE;
        BigInteger total = BigInteger.valueOf(maxId)
            .subtract(BigInteger.valueOf(minId))
            .add(one);

        int partitionCount =
            total.compareTo(BigInteger.valueOf(gridSize)) < 0
                ? total.intValueExact()
                : gridSize;

        BigInteger[] qr = total.divideAndRemainder(
            BigInteger.valueOf(partitionCount)
        );
        BigInteger baseWidth = qr[0];
        int extra = qr[1].intValueExact();

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        BigInteger cursor = BigInteger.valueOf(minId);

        for (int i = 0; i < partitionCount; i++) {
            BigInteger width = baseWidth.add(
                i < extra ? one : BigInteger.ZERO
            );
            BigInteger upper = cursor.add(width).subtract(one);

            ExecutionContext context = new ExecutionContext();
            context.putString("batchId", batchId);
            context.putLong("minId", cursor.longValueExact());
            context.putLong("maxId", upper.longValueExact());

            partitions.put("partition" + i, context);
            cursor = upper.add(one);
        }

        return partitions;
    }
}
```

Giải thích các quyết định:

- `gridSize` phải dương; số partition không vượt quá số giá trị ID của miền.
- `BigInteger` tránh tràn số khi tính tổng độ rộng và cận trung gian, trong khi `ExecutionContext.putLong` giữ đúng kiểu ID ở database.
- `LinkedHashMap` giữ thứ tự thêm tên partition, nhưng **không bảo đảm thứ tự thực thi hoặc commit**.
- `partition0`, `partition1`, ... là các tên xác định, cần ổn định để hỗ trợ restart.
- Thông tin `batchId` được lưu cùng mỗi range để reader dùng đúng tập đầu vào.

Thuật toán tạo **số khoảng đều theo miền khóa**; không biết record count trong từng khoảng. Nếu dữ liệu rất thưa, một hoặc nhiều partition có thể không có item; vẫn cần đo overhead thực tế. Với batch rỗng, việc trả map rỗng cần được kiểm thử trong cấu hình manager và theo tiêu chí vận hành của ứng dụng.

## 7. Đọc đúng range với @StepScope

Bean reader của worker cần lấy `batchId`, `minId` và `maxId` từ `ExecutionContext` của partition. `@StepScope` cung cấp cơ chế **late binding** khi StepExecution bắt đầu, giúp các worker có reader và trạng thái checkpoint riêng.

```java
@Bean
@StepScope
public JdbcPagingItemReader<OrderRow> rangeReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    PostgresPagingQueryProvider provider = new PostgresPagingQueryProvider();
    provider.setSelectClause("id, customer_id, total_amount");
    provider.setFromClause("orders_staging");
    provider.setWhereClause(
        "batch_id = :batchId AND id >= :minId AND id <= :maxId"
    );
    provider.setSortKey("id");

    return new JdbcPagingItemReaderBuilder<OrderRow>()
        .name("rangeReader")
        .dataSource(dataSource)
        .queryProvider(provider)
        .parameterValues(Map.of(
            "batchId", batchId,
            "minId", minId,
            "maxId", maxId
        ))
        .pageSize(200)
        .rowMapper((rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getLong("customer_id"),
            rs.getBigDecimal("total_amount")
        ))
        .saveState(true)
        .build();
}
```

Với domain minh họa:

```java
public record OrderRow(
    long id,
    long customerId,
    BigDecimal totalAmount
) {}
```

Điểm cần nhớ:

- `sortKey("id")` dùng khóa chính duy nhất, không thay đổi, cần thiết cho việc phân trang ổn định và khôi phục state.
- `pageSize(200)` là số bản ghi cho mỗi lần reader lấy một trang. Đây là cấu hình khác với **chunk size** (mục tiêu số item cho một transaction).
- `saveState(true)` giúp reader lưu vị trí/metadata, nhưng **không thể chữa việc tập dữ liệu biến động hoặc writer không idempotent**.
- Reader scoped theo **StepExecution**, không đồng nghĩa mỗi thread luôn có một instance riêng trong một multi-threaded step. Ở đây mỗi worker partition có StepExecution riêng, vì vậy không cần gắn thêm executor vào chính worker step.
- Không mặc định mọi triển khai reader JDBC/file đều thread-safe. Nếu thay reader hoặc triển khai xử lý khác, cần đọc contract và thử lỗi/restart.

Spring Batch `JdbcPagingItemReader` quản lý việc phân trang dựa trên sort key và state của nó. Không nên tự giả định việc paging chỉ đơn giản là OFFSET, cũng không nên cập nhật chính filter của reader khi đang đọc.

## 8. Lắp worker step, manager step và Job

Trong cấu hình Spring Batch 5.x minh họa, dùng một pool bốn thread để thực thi local partitions. Bean writer `orderWriter` có thể ghi sang bảng đích bằng upsert theo ID; nó phải an toàn với concurrency và retry.

```java
@Configuration
public class OrderRangeBatchConfig {

    @Bean
    @StepScope
    public Partitioner orderRangePartitioner(
            JdbcTemplate jdbcTemplate,
            @Value("#{jobParameters['batchId']}") String batchId) {
        return new OrderIdRangePartitioner(jdbcTemplate, batchId);
    }

    @Bean
    public ThreadPoolTaskExecutor rangePartitionExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("range-worker-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step rangeWorkerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("rangeReader")
            JdbcPagingItemReader<OrderRow> rangeReader,
            @Qualifier("orderWriter")
            ItemWriter<OrderRow> orderWriter) {

        return new StepBuilder("rangeWorkerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(200, transactionManager)
            .reader(rangeReader)
            .writer(orderWriter)
            .build();
    }

    @Bean
    public Step rangeManagerStep(
            JobRepository jobRepository,
            @Qualifier("rangeWorkerStep") Step workerStep,
            @Qualifier("orderRangePartitioner") Partitioner partitioner,
            @Qualifier("rangePartitionExecutor") TaskExecutor executor) {

        return new StepBuilder("rangeManagerStep", jobRepository)
            .partitioner("rangeWorkerStep", partitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(executor)
            .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            @Qualifier("rangeManagerStep") Step managerStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
            .start(managerStep)
            .build();
    }
}
```

Đây là khung wiring phục vụ học tập; `orderWriter`, datasource và bean hạ tầng được cấu hình ở ứng dụng. Tham số `batchId` phải được cung cấp và kiểm tra hợp lệ trước khi job bắt đầu.

Theo cấu hình trên:

1. Job bắt đầu từ `rangeManagerStep`. Manager tạo nhiều worker `rangeWorkerStep`, không tạo một `JobInstance` độc lập cho mỗi range.
2. `gridSize(4)` là gợi ý số range cho partitioner; thuật toán có thể tạo ít hơn nếu miền chỉ có ít giá trị.
3. Pool bốn thread điều tiết worker đồng thời; queue capacity là số tác vụ chờ, **không phải số thread bổ sung**.
4. `rangeWorkerStep` **không** có `taskExecutor(...)`, vì cấp đồng thời đã diễn ra ở manager step.
5. Reader nhận tham số theo partition; writer cần stateless hoặc có cơ chế chia state/đồng bộ đúng.

Một ứng dụng có nhiều job hoặc flow đồng thời còn phải tính tổng số worker sử dụng cùng database/API, chứ không chỉ mỗi `rangeManagerStep`.

## 9. Mất cân bằng do ID thưa và phương án cải thiện

Giả sử bảng thực chỉ chứa:

```text
10, 11, 50, 51, 52, 1000, 1001, 1002
```

Miền `[10,1002]` có 993 giá trị, chia thành 3 range độ rộng 331:

| Partition | Range | Số dòng thật |
| --- | --- | ---: |
| P0 | 10–340 | 5 |
| P1 | 341–671 | 0 |
| P2 | 672–1002 | 3 |

P1 rỗng, P0 nhiều hơn P2. Khi số dòng hoặc chi phí xử lý mỗi record lệch mạnh, một partition chậm sẽ kéo dài thời gian toàn job dù worker khác đã rảnh. Vì vậy **chia đều miền khóa không có nghĩa chia đều tải**.

Có vài cách điều chỉnh:

| Chiến lược | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| MIN/MAX chia đều range | Rẻ và dễ chứng minh chính xác. | Không cân bằng khi ID thưa. |
| Chia theo phân vị ID hoặc số dòng ước tính | Range có record count tương đối đều. | Cần thống kê, sampling hoặc truy vấn tốn tài nguyên. |
| Tạo nhiều range nhỏ hơn số worker | Worker có thể xử lý các range ngắn kế tiếp, giảm ảnh hưởng range lệch. | Tăng metadata, scheduling và thời gian khởi tạo step. |
| Chia theo ngày, tenant, shard, khóa nghiệp vụ | Phù hợp locality hoặc ràng buộc nghiệp vụ. | Cần bảo đảm nhóm độc lập; group có thể lệch lớn. |
| Dựa vào thời gian xử lý lịch sử | Có thể cân bằng khối lượng thực tế tốt hơn count. | Phải cập nhật dự báo khi dữ liệu thay đổi. |

Có thể dùng truy vấn quan sát:

```sql
SELECT COUNT(*)
FROM orders_staging
WHERE batch_id = :batchId
  AND id >= :minId
  AND id <= :maxId;
```

Tuy nhiên `COUNT(*)` nhiều lần trên bảng cực lớn có thể đắt. Nếu cần chia theo phân vị, cân nhắc thống kê đã lưu, sampling hoặc danh sách ID được materialize trước. Hãy đo **thời gian mỗi partition**; hai range có cùng số dòng vẫn có thể chênh lệch runtime nếu một range phải gọi API nhiều hơn.

## 10. Khi dữ liệu biến động: record mới, thay khóa, xóa bản ghi

**Record có ID mới cao hơn cận trên:** manager đã chốt `maxId = 1000`, record mới có `id = 1001` không thuộc partition nào. Có thể đây là kết quả đúng nếu record đó được dành cho batch sau.

**Record mới có ID ở giữa:** nếu upstream backfill `id = 400` trong cùng `batchId` sau khi worker đã đi qua vùng này, record có thể bị bỏ sót. Nếu xuất hiện trước khi đọc, nó có thể được đưa vào kết quả. Chia range không tạo được snapshot xuyên mọi transaction.

**Record đổi filter:** nếu worker vừa đọc vừa đổi `batch_id` hoặc cột status dùng làm điều kiện lọc, reader có thể thấy tập kết quả thay đổi trong khi paging. Dù sort key ổn định, không nên dựa vào dữ liệu thay đổi mà không kiểm chứng.

**Record bị xóa:** một record ban đầu có trong batch nhưng bị xóa trước khi worker đọc sẽ không còn xuất hiện; biên `MIN/MAX` lúc đầu không thể ngăn được điều này.

Biện pháp an toàn là dùng batch staging bất biến, khóa/phiên bản dữ liệu nghiệp vụ, hoặc materialize chính xác danh sách khóa cần xử lý cho lần chạy. Transaction isolation có thể giúp trong từng transaction, nhưng một job gồm nhiều chunk, nhiều connection và nhiều worker **không mặc nhiên chia sẻ một snapshot chung** từ đầu tới cuối.

## 11. Transaction, retry và restart

Mỗi partition có `StepExecution` và `ExecutionContext` riêng. Bên trong partition, các chunk vẫn commit/rollback theo transaction boundary của step.

```text
P0: chunk1 COMMIT -> chunk2 COMMIT -> COMPLETED
P1: chunk1 COMMIT -> chunk2 FAIL   -> FAILED
P2: chunk1 COMMIT -> chunk2 COMMIT -> COMPLETED

Restart một JobInstance phù hợp:
  - metadata xác định partition đã hoàn tất và chưa hoàn tất;
  - partition FAILED được tiếp tục theo checkpoint/chính sách restart;
  - kết quả đã COMMIT ở partition khác không bị rollback toàn cục.
```

Để restart đúng, cần bảo đảm:

1. **Tên partition xác định và ổn định:** `partition0`, `partition1`,... Không dùng tên ngẫu nhiên mỗi khi gọi `partition()`.
2. **Biên range và membership của batch ổn định:** khi restart không được âm thầm chia lại dữ liệu thành vùng khác, khiến phần đã ghi bị mất hoặc lặp.
3. **Reader có checkpoint hợp lệ:** `saveState(true)`, sort key duy nhất, nguồn ổn định, `@StepScope` chính xác. Đổi thành `saveState(false)` không phải phép chữa vấn đề thread safety/restart.
4. **Writer idempotent:** retry chunk có thể lặp thao tác nếu hệ thống không rollback được side effect. Cần unique constraint, upsert, idempotency key hoặc outbox/dedup.
5. **Có đối soát bằng khóa nghiệp vụ:** `BatchStatus.COMPLETED` và count bằng nhau chưa đủ chứng minh không thiếu/trùng khóa.

Một dạng ghi idempotent vào bảng đích trong PostgreSQL:

```sql
INSERT INTO orders_result (id, batch_id, normalized_amount)
VALUES (:id, :batchId, :normalizedAmount)
ON CONFLICT (id)
DO UPDATE SET
    batch_id = EXCLUDED.batch_id,
    normalized_amount = EXCLUDED.normalized_amount;
```

Upsert chỉ thật sự an toàn khi bản ghi cho cùng ID được tính ra kết quả tương thích, không có phiên bản mới đang tranh chấp. Nếu kết quả phụ thuộc thứ tự, phải có version hoặc điều kiện cập nhật rõ ràng.

**Restart khác chạy job instance mới.** Restart của instance lỗi dựa vào metadata cũ và các job parameter định danh instance. Một instance mới có thể có snapshot hoặc phạm vi khác. Đừng nhầm cấu hình tính lại biên ở lần chạy mới với phục hồi instance đang dở.

Các kịch bản bắt buộc kiểm tra:

- Một partition lỗi giữa chừng sau khi các partition khác đã commit. Restart, rồi đối soát tập ID.
- Process chết sau khi side effect ngoài DB đã xảy ra nhưng trước khi trạng thái được ghi nhận. Retry không được tạo tác động trùng.
- Batch rỗng, chỉ có một ID, ID có lỗ hổng lớn, miền gần giới hạn `BIGINT`.
- Dữ liệu đầu vào lặp lỗi tạm thời; cấu hình retry/skip không dẫn đến tăng tải vô hạn cho API/DB.

Ví dụ đếm sơ bộ:

```sql
SELECT COUNT(*) AS input_count
FROM orders_staging
WHERE batch_id = :batchId;

SELECT COUNT(*) AS output_count, COUNT(DISTINCT id) AS unique_count
FROM orders_result
WHERE batch_id = :batchId;
```

Count bằng nhau **chưa đủ**: hai tập có thể khác ID nhưng cùng số lượng. Với yêu cầu chính xác, đối chiếu hai tập ID bằng `EXCEPT`/anti-join và đối soát thêm tổng tiền hoặc checksum.

## 12. Thread safety và tài nguyên thực tế

Partitioning giúp chia state theo `StepExecution` thay vì cho nhiều thread chia sẻ một reader duy nhất trong một multi-threaded step. Tuy nhiên:

- `@StepScope` của reader tạo ngữ cảnh riêng cho từng partition; processor/writer singleton **có thể vẫn được chia sẻ** giữa worker. Hãy giữ processor stateless, writer thread-safe hoặc quản lý state theo step.
- Không thêm `taskExecutor(...)` vào **worker step** chỉ để tăng tốc nếu chưa kiểm chứng thread safety của reader, checkpoint và writer. Làm vậy khiến nhiều chunk của cùng partition có thể chia sẻ state.
- Mỗi worker có thể giữ JDBC connection, page buffer, chunk buffer và các tài nguyên khác. Tăng `gridSize`, pool size và chunk size cùng lúc có thể làm heap/GC/connection wait tăng mạnh.
- Retry, skip và xử lý HTTP là những nguồn tăng tải đột biến. Giới hạn rate, timeout và số worker truy cập downstream.

Một ước lượng:

```text
worker đồng thời ≈ min(partition sẵn sàng, active-capacity executor)
nhưng throughput còn bị giới hạn bởi CPU, DB, network, API
```

Cấu hình pool bốn thread không có nghĩa chỉ cần bốn connection database: `JobRepository`, người dùng khác, flow khác và các tác vụ nền cũng sử dụng kết nối. Dành ngân sách tài nguyên và headroom cho toàn ứng dụng.

Nếu database đang chờ lock hoặc I/O bão hòa, tăng worker có thể làm thời gian tệ hơn. Nếu các worker rảnh vì một partition quá lớn, cải thiện cách chia hoặc tăng số partition nhỏ có thể có ích hơn nâng số thread.

## 13. Benchmark và quan sát

Bắt đầu bằng baseline tuần tự trên **cùng bộ dữ liệu**, giữ nguyên hạ tầng và workload. Sau đó tăng dần concurrency và kiểm tra tính đúng đắn cùng hiệu năng.

| Thử nghiệm | Grid size | Pool size | Chunk size | Mục tiêu |
| --- | ---: | ---: | ---: | --- |
| Baseline | 1 | 1 | 200 | Thời gian/record, dữ liệu đúng. |
| A | 4 | 2 | 200 | Lợi ích chạy đồng thời. |
| B | 8 | 4 | 200 | Cân bằng range và sử dụng pool. |
| C | 16 | 4 | 200 | Nhiều range nhỏ có giảm skew? |
| D | 16 | 8 | 200 | DB/API có chịu thêm worker? |

Các metric tối thiểu:

| Metric | Dấu hiệu cần phát hiện |
| --- | --- |
| Items/s, elapsed time mỗi partition | Partition nóng, partition rỗng, throughput thực. |
| Reader/write/commit latency | Nút thắt chuyển từ CPU sang DB hay không. |
| Active threads, queue depth, rejected tasks | Executor được dùng hết hay bị overload. |
| DB connection wait, lock wait, deadlock | Gia tăng tranh chấp khi mở rộng. |
| CPU, heap, GC pause, I/O | Tài nguyên JVM hoặc host bị bão hòa. |
| Retry, skip, failed/restarted steps | Độ tin cậy khi tăng đồng thời. |
| Duplicate/missing IDs, checksum/tổng tiền | Tính đúng đắn nghiệp vụ sau chạy/restart. |

Với `T(1)` là thời gian một worker và `T(N)` là thời gian N worker, `speedup = T(1) / T(N)`. Ví dụ giả định một job mất 50 phút với một worker và 18 phút với bốn worker thì speedup khoảng `2,78 lần`, thấp hơn `4 lần` do overhead, contention và mất cân bằng. Không chấp nhận một cấu hình nhanh hơn nếu nó tạo kết quả thiếu/trùng hoặc không restart được.

## 14. Khi nào nên chọn phương án khác?

| Tình huống | Giải pháp cân nhắc |
| --- | --- |
| Không có khóa số có thứ tự phù hợp | Chia theo ngày/tenant/shard, hash, hoặc danh sách ID đã snapshot. |
| Khóa UUID phân bố khó chia đều theo range | Hash partition hoặc chia theo một khóa nghiệp vụ có locality. |
| Dữ liệu thưa, mật độ quá lệch | Quantile/count-based boundaries hoặc nhiều range nhỏ hơn. |
| Record phụ thuộc thứ tự toàn cục | Giữ bước tuần tự hoặc thiết kế cơ chế đồng bộ rõ ràng. |
| Nhiều record cùng cập nhật một entity | Partition theo entity/khóa nghiệp vụ để tránh cross-partition contention. |
| Dữ liệu thay đổi liên tục, không thể snapshot | Queue/event, materialized list hoặc cơ chế CDC thích hợp. |
| Cần thêm nhiều máy | Remote partitioning hoặc remote chunking, với messaging và quản trị worker. |
| Cổ chai là DB connection, lock hoặc API rate limit | Tối ưu tài nguyên downstream trước khi thêm thread/partition. |

## 15. Bài thực hành

**Bài tập 1 — Tính range:** `minId = 100`, `maxId = 112` và `gridSize = 4`. Tổng 13 giá trị, thương 3, dư 1. Kết quả đúng là `[100,103]`, `[104,106]`, `[107,109]`, `[110,112]`.

**Bài tập 2 — Tìm lỗi biên:** P0 đọc `[1,500]` và P1 đọc `[500,1000]`. Nếu reader dùng `BETWEEN`, giải thích vì sao ID 500 có thể được xử lý hai lần và sửa thành `[501,1000]`.

**Bài tập 3 — Lệch tải:** bảng có ID ở hai cụm `1–1000` và `900001–901000`. Chia đều miền ID thành bốn phần thì có những range nào rỗng? Đề xuất dùng phân vị ID hoặc nhiều range nhỏ để cân bằng.

**Bài tập 4 — Restart:** P0/P2 đã hoàn tất, P1 lỗi ở chunk thứ ba. Dựng job restart cùng `batchId`, đối soát tập ID đích với nguồn đã chốt, kiểm tra không tạo duplicate sau khi retry.

**Bài tập 5 — Đo hệ thống:** chạy grid size 4, 8 và 16 với pool size cố định 4. Ghi thời gian mỗi partition, tổng thời gian, connection wait và lock wait. Kết luận bằng số liệu xem số partition lớn hơn có giúp giảm skew hay chỉ tăng overhead.

## 16. Checklist trước khi vận hành

- [ ] Đầu vào có `batchId`/snapshot rõ ràng và được chốt ổn định khi chạy/restart.
- [ ] Khóa chia range là duy nhất, không đổi, có index và không bị bỏ sót filter tenant/batch.
- [ ] Range không overlap, liên tiếp trong miền ID, bao phủ đúng biên và xử lý batch rỗng.
- [ ] Tên partition và `ExecutionContext` xác định, có thể khôi phục từ JobRepository.
- [ ] Reader `@StepScope`, sort key ổn định, checkpoint đúng; processor/writer an toàn với nhiều partition.
- [ ] Writer idempotent hoặc có unique/dedup/outbox cho retry và side effect.
- [ ] Đã thử crash/restart, dữ liệu thưa, ID biên và phép đối soát tập khóa nghiệp vụ.
- [ ] Executor, chunk/page size và connection pool được chọn theo số đo và ngân sách hệ thống.
- [ ] Có metric và log theo partition để tìm hotspot, lỗi, rejected tasks và tài nguyên bão hòa.
- [ ] Đã benchmark trên dữ liệu đại diện; throughput cải thiện mà không đánh đổi tính chính xác.

## 17. Ghi nhớ

**Primary key range partitioning** biến một miền ID lớn thành các khoảng không chồng lấn, mỗi khoảng được xử lý bởi một `StepExecution` riêng. `Partitioner` tạo biên, `ExecutionContext` mang tham số, `@StepScope` định cấu hình reader, và executor cung cấp concurrency cho các worker.

Để kỹ thuật này thực sự phù hợp với workload dữ liệu lớn, phải kiểm tra **ba yêu cầu đồng thời**: chia đúng tập dữ liệu, phục hồi đúng sau lỗi, và đạt tăng tốc đo được dưới giới hạn CPU, database, bộ nhớ và dịch vụ ngoài. Chia range là cách phân công việc; tính đúng đắn và khả năng mở rộng vẫn do toàn bộ thiết kế xử lý quyết định.
