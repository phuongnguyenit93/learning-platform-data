# Chia theo khoảng khóa chính

**Chia theo khoảng khóa chính (primary-key range partitioning)** là cách tạo nhiều vùng dữ liệu độc lập từ một bảng bằng điều kiện trên khóa chính, ví dụ `id >= 1 AND id < 100001`. Trong Spring Batch, một **Partitioner** tạo `ExecutionContext` cho từng vùng, còn các **worker StepExecution** dùng các giá trị đó để đọc và xử lý những bản ghi tương ứng. Khi các vùng không giao nhau, nhiều worker có thể chạy đồng thời mà không cần cạnh tranh để lấy cùng một bản ghi nguồn.

Bài học thuộc chương **Partitioner** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán; đo nút thắt, giữ thread safety, thiết kế retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế. Ở bài này, trọng tâm là **thiết kế ranh giới ID, triển khai Partitioner, kiểm thử độ phủ, xử lý dữ liệu lệch và bảo vệ khả năng restart**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `Partitioner.partition(gridSize)` và cách manager chuyển các cặp ranh giới vào `ExecutionContext` của worker.
2. Tạo các khoảng khóa chính **không giao nhau, không bỏ trống vùng giá trị**, kể cả khi số bản ghi không chia hết cho số partition.
3. Phân biệt **khoảng giá trị ID** và **số bản ghi thực có** trong khoảng; nhận ra skew dữ liệu khi ID thưa hoặc tập trung vào một vùng.
4. Kết hợp `Partitioner`, `@StepScope`, `ItemReader` và writer trong một local partitioned step của Spring Batch 5.x.
5. Giữ ổn định ranh giới, dữ liệu nguồn và khóa idempotency khi worker retry hoặc job restart.
6. Kiểm thử invariant của thuật toán chia, kiểm chứng không trùng/thiếu dữ liệu và đo hiệu năng để chọn `gridSize` theo hạ tầng thực tế.

**Bối cảnh xuyên suốt:** hệ thống có khoảng hai triệu đơn hàng, cần chuẩn hóa tổng tiền trong một batch bất biến trước khi ghi sang bảng kết quả. Một worker đọc tuần tự quá chậm; nhóm muốn dùng bốn worker trong một JVM trước khi cân nhắc remote partitioning.

## 2. Partitioner nằm ở đâu trong Spring Batch?

**Manager step** yêu cầu `Partitioner` tạo bản đồ gồm `partitionName -> ExecutionContext`. Mỗi entry đại diện cho một vùng công việc. **PartitionHandler** lập lịch worker step theo chiến lược đã chọn: thread pool trong cùng JVM hoặc worker ở tiến trình/máy khác. Mỗi worker step có **StepExecution riêng**, nhận ranh giới dữ liệu qua `stepExecutionContext` rồi thực hiện chunk-oriented processing như bình thường.

~~~mermaid
flowchart TD
    J["JobExecution"] --> M["Manager Step"]
    M --> P["Partitioner.partition(gridSize)"]
    P --> A["partition0: [1, 250001)"]
    P --> B["partition1: [250001, 500001)"]
    P --> C["partition2: [500001, 750001)"]
    P --> D["partition3: [750001, 1000001)"]
    A --> W1["Worker StepExecution A"]
    B --> W2["Worker StepExecution B"]
    C --> W3["Worker StepExecution C"]
    D --> W4["Worker StepExecution D"]
    W1 --> DB[("Bảng kết quả")]
    W2 --> DB
    W3 --> DB
    W4 --> DB
~~~

Sơ đồ dùng một miền ID minh họa từ 1 đến 1.000.000; nó không biểu diễn toàn bộ hai triệu đơn hàng ở tình huống mở đầu.

**Phân biệt ba khái niệm dễ lẫn:**

| Khái niệm | Ý nghĩa | Không nên hiểu thành |
| --- | --- | --- |
| `gridSize` | Số partition **đề nghị** để Partitioner lập bản đồ công việc | Chắc chắn có đúng từng ấy worker đồng thời |
| Số entry trong map | Số partition thực tế Partitioner tạo | Số item sẽ được xử lý |
| Kích thước thread pool | Giới hạn tài nguyên chạy worker đồng thời ở local partitioning | Số partition hoặc số transaction luôn đồng thời |

Ví dụ `gridSize=8` nhưng chỉ có ba ID cần xử lý, thuật toán có thể trả ba partition hữu ích. Nếu pool có bốn thread và Partitioner trả tám vùng, tối đa khoảng bốn worker được lên lịch cùng lúc; số lượng thực còn phụ thuộc trạng thái thread, giới hạn khác và tài nguyên.

## 3. Chọn quy ước khoảng: [bao gồm, không bao gồm)

Bài này thống nhất cách biểu diễn:

~~~text
[fromInclusive, toExclusive)

WHERE id >= :fromInclusive
  AND id <  :toExclusive
~~~

Đầu trái được lấy; đầu phải không được lấy. Ví dụ 10 khóa chính liên tiếp, `minId=1`, `maxId=10`, `gridSize=3`:

| Partition | Cặp ranh giới | Các ID nguyên liên tiếp trong khoảng |
| --- | --- | --- |
| `partition0` | `[1, 5)` | 1, 2, 3, 4 |
| `partition1` | `[5, 9)` | 5, 6, 7, 8 |
| `partition2` | `[9, 11)` | 9, 10 |

Điểm cuối của partition trước **bằng** điểm đầu của partition sau. Vì truy vấn sử dụng `< toExclusive`, không có ID nào khớp cả hai khoảng.

Để chia đúng, phải duy trì ba invariant:

1. **Không chồng lấn:** các khoảng có thứ tự `toExclusive(i) <= fromInclusive(i+1)`; nếu muốn phủ kín cả miền giá trị, dấu bằng phải đúng ở ranh giới liên tiếp.
2. **Không bỏ sót miền:** khoảng đầu bắt đầu tại `minId`, khoảng cuối kết thúc tại `maxId + 1`, với giả định phép cộng này không tràn.
3. **Không có khoảng đảo chiều:** `fromInclusive < toExclusive` đối với mọi partition được tạo.

Nếu đổi sang khoảng đóng `[minId, maxId]` cũng có thể làm đúng, nhưng phải dùng điều kiện `<=` và tính điểm bắt đầu vùng sau bằng `maxPrevious+1`. Trộn hai quy ước sẽ tạo lỗi bỏ sót hoặc đọc trùng ở đúng ranh giới.

## 4. Thuật toán chia khoảng gần đều theo độ rộng ID

Với miền ID nguyên không âm có `minInclusive <= maxInclusive < Long.MAX_VALUE`, đặt:

\[
N = \text{maxInclusive} - \text{minInclusive} + 1,
\qquad
w = \left\lceil\frac{N}{\text{gridSize}}\right\rceil.
\]

Ở đây **N là số giá trị khóa có thể nằm trong miền**, **không phải số dòng thực có**. Mỗi partition lấy tối đa `w` giá trị nguyên liên tiếp. Khoảng cuối được cắt tại `maxInclusive + 1`.

Để tránh tràn trong biểu thức `(N + gridSize - 1) / gridSize`, khi `N` đã nằm trong `long` dùng:

~~~java
long width = total / gridSize
        + (total % gridSize == 0 ? 0 : 1);
~~~

Giả sử 20 ID từ 100 đến 119, `gridSize=3`: `width=7`. Các khoảng là `[100,107)`, `[107,114)`, `[114,120)`; vùng cuối ngắn hơn nhưng không bị bỏ qua.

### Những điều kiện đầu vào phải kiểm tra

- `gridSize > 0`: chia cho 0 không hợp lệ, số partition âm không có ý nghĩa.
- `minInclusive <= maxInclusive`: một khoảng ID rỗng phải được xử lý như một trường hợp nghiệp vụ riêng, chẳng hạn một job không có input.
- Với phiên bản thuật toán dưới đây, `minInclusive >= 1` và `maxInclusive < Long.MAX_VALUE`. Chúng phù hợp khóa BIGINT dương thông dụng và ngăn `max+1` tràn.
- Nếu bảng thực sự có khóa âm, bằng 0 hoặc bằng `Long.MAX_VALUE`, cần điều chỉnh miền được hỗ trợ hoặc dùng biểu diễn biên khác, ví dụ **khoảng đóng kết hợp BigInteger** để tính độ rộng.
- `min/max` phải được xác định từ **cùng tập dữ liệu logic** và giữ ổn định khi restart.

Đừng lấy `Integer.MAX_VALUE` hoặc `Long.MAX_VALUE` làm sentinel cận trên khi SQL thực tế phải bao gồm khóa bằng giá trị đó. Nếu dùng `maxExclusive = max + 1`, phép cộng phải được xác thực.

## 5. Cài đặt IdRangePartitioner

Spring Batch 5.x cung cấp interface `org.springframework.batch.core.partition.support.Partitioner` với phương thức `Map<String, ExecutionContext> partition(int gridSize)`. Ta tạo một lớp Java 17+ chỉ làm nhiệm vụ tính toán vùng ID; nó **không đọc hay ghi dữ liệu nghiệp vụ**, dễ unit test và không cần kết nối DB trong lúc tính khoảng.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class IdRangePartitioner implements Partitioner {
    private final long minInclusive;
    private final long maxInclusive;

    public IdRangePartitioner(long minInclusive, long maxInclusive) {
        if (minInclusive < 1 || maxInclusive < minInclusive
                || maxInclusive == Long.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "Require 1 <= minInclusive <= maxInclusive < Long.MAX_VALUE");
        }
        this.minInclusive = minInclusive;
        this.maxInclusive = maxInclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long endExclusive = Math.addExact(maxInclusive, 1L);
        long total = Math.subtractExact(endExclusive, minInclusive);
        long width = total / gridSize
                + (total % gridSize == 0 ? 0L : 1L);

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long from = minInclusive;
        int index = 0;

        while (from < endExclusive) {
            long remaining = endExclusive - from;
            long to = from + Math.min(width, remaining);

            ExecutionContext context = new ExecutionContext();
            context.putLong("fromInclusive", from);
            context.putLong("toExclusive", to);
            result.put("partition" + index++, context);

            from = to;
        }
        return result;
    }
}
~~~

**Tính chất của implementation:**

- `LinkedHashMap` giữ thứ tự đặt tên theo chiều tăng của ID, tiện cho đọc log và unit test; runtime không bảo đảm các worker kết thúc theo thứ tự map.
- Tên `partition0`, `partition1`... là **định danh ổn định** nếu ranh giới và `gridSize` không đổi. Thay đổi cách chia khi restart có thể làm metadata partition cũ không còn tương ứng.
- Nếu `gridSize > total`, thuật toán tạo tối đa `total` vùng, mỗi vùng có ít nhất một giá trị ID; không tạo partition rỗng chỉ để đủ số lượng.
- `total`, `width` và phép tính `from + ...` không tràn trong miền đầu vào đã kiểm tra: các giá trị đều nằm từ 1 đến `Long.MAX_VALUE` và `to <= endExclusive`.
- `gridSize` không nhất thiết bằng số thread trong `TaskExecutor`; hãy đo để xác định số worker thực tế đang chạy.

Nếu cần **đúng N partition**, kể cả partition rỗng, bạn có thể chọn thuật toán khác, nhưng phải ghi rõ quy tắc đó và xử lý vùng rỗng ở reader. Trong đa số workload xử lý bản ghi theo ID, tránh partition rỗng giúp bớt overhead StepExecution.

## 6. Đọc dữ liệu bằng phạm vi khóa chính của worker

Mỗi worker StepExecution nhận `fromInclusive` và `toExclusive` do Partitioner đặt vào `ExecutionContext`. Reader phải dùng đúng cùng quy ước trong câu SQL. Bài này minh họa bằng PostgreSQL:

~~~sql
CREATE TABLE source_order (
    id          BIGINT PRIMARY KEY,
    batch_key   VARCHAR(80) NOT NULL,
    gross_total NUMERIC(18, 2) NOT NULL
);

CREATE INDEX idx_source_order_batch_id
    ON source_order (batch_key, id);

CREATE TABLE normalized_order (
    batch_key   VARCHAR(80) NOT NULL,
    order_id    BIGINT NOT NULL,
    net_total   NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, order_id)
);
~~~

`batch_key` xác định một **tập dữ liệu nguồn ổn định** cho lần chạy logic. Trên bảng có primary key `id`, index `(batch_key, id)` có thể hữu ích cho truy vấn lọc theo `batch_key` rồi khoảng `id`. Có nên tạo thêm index hay không phụ thuộc kích thước bảng, phân bố dữ liệu, execution plan và chi phí cập nhật index.

Reader dùng `@StepScope` để mỗi worker StepExecution có **instance riêng** và nhận đúng biên:

~~~java
record OrderInput(long id, BigDecimal grossTotal) {}

@Bean
@StepScope
JdbcCursorItemReader<OrderInput> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromInclusive']}") Long from,
        @Value("#{stepExecutionContext['toExclusive']}") Long to,
        @Value("#{jobParameters['batchKey']}") String batchKey) {

    return new JdbcCursorItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT id, gross_total
                 FROM source_order
                 WHERE batch_key = ?
                   AND id >= ?
                   AND id < ?
                 ORDER BY id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, batchKey);
                ps.setLong(2, from);
                ps.setLong(3, to);
            })
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getLong("id"),
                    rs.getBigDecimal("gross_total")))
            .saveState(true)
            .build();
}
~~~

**Ba điểm bắt buộc:**

1. Điều kiện SQL phải là `id >= from` và `id < to` như Partitioner; không thay `<` bằng `<=` vì gây trùng khóa ở ranh giới.
2. `ORDER BY id` tạo thứ tự ổn định trong mỗi worker **nếu tập nguồn không thay đổi**, hữu ích cho reader lưu trạng thái và restart. Chỉ `ORDER BY` không đủ để bảo đảm restart an toàn khi row bị thêm, xóa hoặc đổi điều kiện lọc.
3. `@StepScope` phân biệt reader **theo StepExecution**, không phải theo mỗi lời gọi `read()`. Mỗi partition trong ví dụ có StepExecution riêng; reader cursor là stateful nên không nên bị chia sẻ tùy ý giữa các partition.

`JdbcCursorItemReader` có thể giữ kết nối/cursor trong suốt việc đọc của worker. Với bốn worker, mức sử dụng connection pool không chỉ bằng bốn: mỗi worker còn có nhu cầu kết nối ghi, transaction và JobRepository. Đừng cấu hình pool chỉ bằng đúng số partition mà không quan sát kiểu sử dụng kết nối thực tế.

### Processor và writer minh họa

Processor stateless, writer dùng khóa `(batch_key, order_id)` để ghi lặp an toàn khi job retry/restart:

~~~java
record OrderResult(long orderId, BigDecimal netTotal) {}

@Bean
ItemProcessor<OrderInput, OrderResult> normalizeOrder() {
    return row -> new OrderResult(
            row.id(),
            row.grossTotal().setScale(2, RoundingMode.HALF_UP));
}

@Bean
@StepScope
JdbcBatchItemWriter<OrderResult> orderWriter(
        DataSource dataSource,
        @Value("#{jobParameters['batchKey']}") String batchKey) {

    return new JdbcBatchItemWriterBuilder<OrderResult>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO normalized_order(batch_key, order_id, net_total)
                 VALUES (:batchKey, :orderId, :netTotal)
                 ON CONFLICT (batch_key, order_id)
                 DO UPDATE SET net_total = EXCLUDED.net_total
                 """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("batchKey", batchKey)
                            .addValue("orderId", item.orderId())
                            .addValue("netTotal", item.netTotal()))
            .build();
}
~~~

Ví dụ trên giả định giá trị đầu vào hợp lệ và quy tắc chuẩn hóa là **deterministic**. Nếu cùng `batchKey` và `orderId` có thể cho ra nhiều giá trị khác nhau vì nguồn thay đổi, UPSERT sẽ **ghi đè** thay vì phát hiện sai lệch; cần cố định snapshot, lưu version/checksum hoặc dùng chính sách reject conflict phù hợp.

## 7. Ghép Partitioner vào manager và worker Step

Với Spring Batch 5.x, worker là chunk-oriented step bình thường; manager step cấu hình partitioner và task executor. Bài này dùng **local partitioning**, nghĩa là worker chạy ở thread pool của cùng JVM:

~~~java
@Bean
@StepScope
Partitioner orderRangePartitioner(
        @Value("#{jobParameters['minId']}") Long minId,
        @Value("#{jobParameters['maxIdInclusive']}") Long maxIdInclusive) {

    return new IdRangePartitioner(minId, maxIdInclusive);
}

@Bean
Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Qualifier("orderReader") ItemReader<OrderInput> orderReader,
        @Qualifier("normalizeOrder")
                ItemProcessor<OrderInput, OrderResult> processor,
        @Qualifier("orderWriter") ItemWriter<OrderResult> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<OrderInput, OrderResult>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(processor)
            .writer(orderWriter)
            .build();
}

@Bean
ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("id-partition-");
    executor.initialize();
    return executor;
}

@Bean
Step orderManagerStep(
        JobRepository jobRepository,
        @Qualifier("orderWorkerStep") Step workerStep,
        @Qualifier("orderRangePartitioner") Partitioner partitioner,
        @Qualifier("partitionExecutor") TaskExecutor taskExecutor) {

    return new StepBuilder("orderManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(taskExecutor)
            .build();
}

@Bean
Job orderJob(JobRepository jobRepository,
             @Qualifier("orderManagerStep") Step managerStep) {
    return new JobBuilder("orderJob", jobRepository)
            .start(managerStep)
            .build();
}
~~~

Các import, cấu hình datasource và transaction manager được lược bớt; phải cung cấp chúng trong project Spring Batch/Spring Boot tương thích. **JobParameters** cần có `batchKey`, `minId`, `maxIdInclusive` hợp lệ ngay từ khi chạy job; đừng để worker tự truy vấn lại min/max rồi lấy một miền khác manager.

Ví dụ khởi chạy về mặt khái niệm:

~~~text
batchKey = orders-2026-11-26
minId = 1 (Long)
maxIdInclusive = 1000000 (Long)
gridSize = 4

partition0 -> [1, 250001)
partition1 -> [250001, 500001)
partition2 -> [500001, 750001)
partition3 -> [750001, 1000001)
~~~

Nếu muốn restart cùng JobInstance, phải giữ **identifying JobParameters** đã dùng để xác định tập dữ liệu và ranh giới. Đổi tham số định danh tạo một JobInstance khác, không tương đương restart của lần đang lỗi.

## 8. Chọn min/max và giữ tập nguồn ổn định

Cách lấy biên ban đầu thường là:

~~~sql
SELECT MIN(id) AS min_id, MAX(id) AS max_id, COUNT(*) AS row_count
FROM source_order
WHERE batch_key = :batch_key;
~~~

Tuy nhiên, trong hệ thống đang tiếp tục ghi dữ liệu, hai điều kiện phải được xem xét **trước** khi đưa min/max vào Partitioner:

**A. Khóa nguồn có ổn định không?** Nếu worker đang đọc mà transaction khác thêm bản ghi ID nằm trong khoảng đã chia, các worker có thể nhìn thấy tập dữ liệu khác nhau ở từng thời điểm. Nếu bản ghi bị xóa, hoặc `batch_key` thay đổi khi đang chạy, reader có thể bỏ qua dữ liệu mà job ban đầu dự kiến xử lý.

**B. Biên có ổn định qua restart không?** Nếu job thất bại rồi tính lại `MAX(id)` từ bảng live, ranh giới partition thay đổi. Một partition mang tên cũ có thể bao phủ miền mới, khiến StepExecution/ExecutionContext đã lưu không tương ứng với dữ liệu được đọc sau restart.

Các lựa chọn thiết kế:

- **Batch input bất biến:** nạp dữ liệu vào bảng có `batch_key` cố định; chỉ bắt đầu job khi batch đã được đóng, không thay đổi row thuộc batch đó cho tới khi job hoàn tất.
- **Snapshot hoặc danh sách ID đã chốt:** ghi tập ID dự kiến xử lý vào bảng staging hoặc batch manifest; worker chỉ đọc dữ liệu thuộc snapshot.
- **High-watermark cố định:** giữ `maxIdInclusive` ở JobParameters hoặc metadata bền vững, đồng thời xác định rõ dữ liệu cũ có được cập nhật/xóa trong lúc job chạy không. Một cutoff ID **đơn độc** chỉ chặn ID mới lớn hơn cutoff, không bảo vệ trước sửa/xóa/insert vào các lỗ ID cũ.
- **Keyset và version:** với nguồn thay đổi liên tục, có thể cần khóa kết hợp `(id, version)`, trạng thái claim hoặc mô hình CDC phù hợp; chia khoảng đơn thuần chưa đủ.

Nếu truy vấn trả `min_id = NULL` và `max_id = NULL`, batch không có dòng. Ứng dụng nên xác định quy tắc rõ: kết thúc không xử lý, chạy no-op step hoặc báo dữ liệu đầu vào rỗng theo nghiệp vụ. Đừng tự ép NULL thành `0` hay `Long.MAX_VALUE` rồi tạo partition giả.

### Ví dụ lỗi do nguồn thay đổi

Ban đầu bảng có ID `[10,20,30,40]`, hai worker nhận `[10,26)` và `[26,41)`. Sau khi partition đã khởi động, một giao dịch chèn hàng ID `25`. Tùy thời điểm và mức isolation, worker đầu có thể thấy hoặc không thấy ID 25. Việc dừng/restart worker với query cùng khoảng có thể cho tập kết quả khác trước đó.

**Kết luận cần ghi nhớ:** partition không chồng **miền ID** không đồng nghĩa job có snapshot dữ liệu nhất quán. Cần kiểm soát **tập bản ghi thuộc job**, không chỉ khoảng số nguyên.

## 9. ID thưa và skew: chia đều giá trị không đồng nghĩa chia đều công việc

Giả sử khóa chính trải từ 1 đến 1.000.000 nhưng 90% bản ghi nằm trong khoảng 900.001–1.000.000. Chia bốn khoảng bằng độ rộng ID tạo rất nhiều worker rảnh, một worker xử lý phần lớn dữ liệu. Tăng số thread có thể không giúp vì worker nặng nhất chi phối tổng thời gian job.

| Dữ liệu đầu vào | Chia đều theo độ rộng ID | Điều có thể xảy ra |
| --- | --- | --- |
| ID tăng liên tục, mật độ gần đều | Thường phân phối tương đối cân | Dễ triển khai, query range tận dụng index |
| ID bị xóa nhiều hoặc có khoảng trống lớn | Mỗi vùng nhiều giá trị nhưng ít dòng | Một số worker xong gần như ngay |
| 90% bản ghi tập trung cuối bảng | Vùng cuối cực nặng | Worker cuối là critical path |
| Các ID có cost xử lý rất khác nhau | Cùng số dòng nhưng thời gian khác | Cần đo cost, không chỉ COUNT(*) |
| Khóa UUID ngẫu nhiên | Không dễ chia khoảng số nguyên | Cân nhắc bảng staging, hash bucket hoặc chiến lược khác |

### Biện pháp cân bằng

1. **Đo phân bố dữ liệu:** đếm số item và thời gian xử lý theo vùng ID; dùng histogram hoặc thống kê từ DB.
2. **Tạo nhiều partition nhỏ hơn số thread:** ví dụ 32 vùng cho pool 4 thread, để worker rảnh tiếp nhận vùng kế tiếp. Cách này giảm tác động skew khi vùng nhỏ nhưng tăng overhead StepExecution và quản lý metadata.
3. **Dùng ranh giới theo lượng dữ liệu (quantile):** tìm các khóa ID tại các mốc 25%, 50%, 75% của **tập nguồn đã chốt** rồi tạo khoảng `[start, boundary)`. Cần xử lý đúng record tại biên và lưu các ranh giới cố định cho restart.
4. **Ước lượng theo chi phí thực:** nếu mỗi row có thời gian xử lý khác nhau, có thể nhóm theo loại dữ liệu, ngày hoặc business key phù hợp hơn là chỉ theo số lượng.

**Không tính lại quantile theo dữ liệu live trong cùng một lần restart.** Các mốc phải nhất quán với snapshot/manifest mà job đang xử lý. Việc truy vấn toàn bộ bảng để tính ranh giới đều có chi phí; phải so sánh chi phí chuẩn bị partition với lợi ích throughput.

### Khi có hàng triệu ID nhưng chỉ vài nghìn hàng

Chia `[1, 10_000_001)` thành 100 khoảng không gây ra lỗi nếu truy vấn SQL đúng, nhưng có thể sinh rất nhiều StepExecution gần rỗng. Một số lựa chọn thực tế:

- Giảm `gridSize` khi số bản ghi thực ít.
- Lấy mẫu/quantile từ ID hiện có, tạo các khoảng có dữ liệu.
- Dùng bảng staging chứa danh sách ID đã chốt; worker đọc theo `batch_key` và vùng/nhóm được chỉ định.

Mục tiêu là **cân bằng lượng việc**, không chỉ làm cho các con số ranh giới trông đều.

## 10. Thread safety của reader, processor và writer

Local partitioning cho **mỗi partition một StepExecution**, nên `@StepScope` giúp tạo reader có trạng thái riêng theo execution. Đây là lợi thế so với mô hình **multi-threaded step**, nơi nhiều thread có thể cùng tham gia xử lý chunk trong **một** StepExecution.

| Thành phần | Lựa chọn an toàn trong ví dụ | Rủi ro nếu sai |
| --- | --- | --- |
| `Partitioner` | Chỉ tính cặp biên từ tham số bất biến, không giữ cursor | Ranh giới thay đổi khi retry/restart |
| `ItemReader` | `@StepScope`, nhận biên qua context, ORDER BY khóa ổn định | Chia sẻ vị trí cursor, đọc thiếu/trùng |
| `ItemProcessor` | Stateless, dữ liệu bất biến theo item | Race condition do cache/counter singleton mutable |
| `ItemWriter` | Transactional, có unique key/upsert phù hợp | Ghi trùng khi retry hoặc worker trùng vùng |
| `JobRepository` | Bền vững, metadata mỗi StepExecution được lưu nhất quán | Không biết partition nào đã hoàn tất |
| `DataSource` | Pool đủ cho các worker, có timeout và metric | Cạn kết nối, commit chậm, deadlock/lock wait |

**Một cảnh báo quan trọng:** local partitioning không biến mọi thành phần thành thread-safe. Processor singleton hoặc service dùng chung vẫn có thể được gọi bởi nhiều worker. Nếu một worker step lại bật `taskExecutor` riêng cho chunk, concurrency còn tăng theo nhiều cấp và phải rà soát lại reader/writer, transaction và giới hạn pool.

## 11. Restart: giữ tên partition và biên ổn định

Spring Batch sử dụng `JobRepository` để lưu `JobExecution`, `StepExecution` và `ExecutionContext`. Khi job thất bại, restart có thể dựa trên metadata để **bỏ qua những partition đã COMPLETED** và tiếp tục các partition cần xử lý, theo chính sách step và trạng thái lưu được. Nhưng cần thỏa những điều kiện:

1. **Identifying JobParameters không thay đổi** nếu mục tiêu là restart cùng JobInstance.
2. **Tên partition** ổn định: `partition0` của lần trước phải tiếp tục tương ứng cùng vùng logic nếu được tái tạo.
3. **Cặp biên** được lưu hoặc tái tạo nhất quán, kể cả khi triển khai phiên bản mới; không tùy ý tăng `gridSize` hay đổi thuật toán giữa chừng.
4. **Input snapshot** ổn định để reader có thể định vị lại theo state.
5. **Writer idempotent** hoặc có đối soát rõ để việc xử lý lại chunk không nhân đôi tác động nghiệp vụ.

Ví dụ partition1 đã xử lý một nửa khoảng `[250001,500001)` rồi worker chết. Trong lần restart, nếu reader phục hồi từ checkpoint trên cùng nguồn ổn định, nó có thể tiếp tục phần còn lại. Nếu nguồn bị xóa/chèn giữa chừng hoặc ranh giới đổi, checkpoint đọc trước đó có thể không còn phản ánh tập item đã commit.

Không chỉnh trực tiếp trạng thái `StepExecution` trong bảng metadata để “đánh dấu xong” khi chưa đối chiếu. Trạng thái COMPLETED không chứng minh bảng kết quả chính xác nếu code writer hoặc dữ liệu đầu vào có lỗi.

### Retry/rollback tại ranh giới chunk

Giả sử writer đã ghi dữ liệu nhưng kết nối worker bị đứt hoặc transaction chưa được xác nhận dứt khoát. Khi chạy lại, **một số item có thể bị xử lý lại**. UPSERT theo khóa `(batch_key, order_id)` giúp giảm rủi ro bản ghi trùng, nhưng không thay thế việc cố định input và bảo đảm các side effect khác như gửi email hoặc xuất event không bị nhân đôi.

Nếu cần xuất message sau khi ghi DB, cân nhắc **transactional outbox** và khóa idempotency ở consumer. Không đặt một lời gọi API tạo tác động không thể rollback trực tiếp trong `ItemProcessor` rồi giả định Spring Batch sẽ undo khi chunk lỗi.

## 12. Chia partition khác với cố gắng “mỗi ID đúng một lần”

Hai invariant cần kiểm tra **tách biệt**:

**Invariant thuật toán:** với `min=1, max=10`, mọi số nguyên từ 1 đến 10 thuộc **đúng một** khoảng. Đây là thuộc tính của Partitioner, có thể kiểm chứng hoàn toàn bằng unit test.

**Invariant dữ liệu thực:** mỗi row thuộc batch input được xử lý cho kết quả đúng và không có bản ghi kết quả trùng business key. Đây là thuộc tính của toàn hệ thống gồm SQL reader, processor, transaction, writer, restart và trạng thái nguồn.

Một partitioner hoàn hảo vẫn có thể gây **dữ liệu thiếu** nếu SQL dùng `id > from`, bộ lọc `batch_key` khác nhau, tập nguồn thay đổi hoặc output bị rollback. Ngược lại, writer có unique key không bảo đảm một row chưa từng bị đọc trùng hoặc kết quả giá trị chính xác.

## 13. Unit test: biên, độ phủ và không chồng lấn

Vì `IdRangePartitioner` là lớp Java thuần, có thể kiểm thử mà không khởi động Spring context:

~~~java
@Test
void splitsTenIdsIntoThreeContiguousRanges() {
    Map<String, ExecutionContext> parts =
            new IdRangePartitioner(1L, 10L).partition(3);

    assertEquals(3, parts.size());
    assertEquals(List.of("partition0", "partition1", "partition2"),
            new ArrayList<>(parts.keySet()));

    long cursor = 1L;
    for (ExecutionContext ctx : parts.values()) {
        long from = ctx.getLong("fromInclusive");
        long to = ctx.getLong("toExclusive");

        assertEquals(cursor, from); // Không hở giữa các khoảng
        assertTrue(to > from);      // Không có khoảng rỗng/đảo
        cursor = to;                // Cận sau == cận đầu kế tiếp
    }

    assertEquals(11L, cursor);
}

@Test
void createsOnlyUsefulPartitionsWhenGridExceedsDomain() {
    Map<String, ExecutionContext> parts =
            new IdRangePartitioner(5L, 6L).partition(10);
    assertEquals(2, parts.size());
    assertEquals(5L, parts.get("partition0").getLong("fromInclusive"));
    assertEquals(7L, parts.get("partition1").getLong("toExclusive"));
}

@Test
void rejectsInvalidBoundsAndGridSize() {
    assertThrows(IllegalArgumentException.class,
            () -> new IdRangePartitioner(8L, 7L));
    assertThrows(IllegalArgumentException.class,
            () -> new IdRangePartitioner(1L, Long.MAX_VALUE));
    assertThrows(IllegalArgumentException.class,
            () -> new IdRangePartitioner(1L, 10L).partition(0));
}
~~~

### Property-based testing cho nhiều miền ngẫu nhiên

Ngoài ví dụ cố định, tạo hàng nghìn miền nhỏ với `min <= max` và `gridSize` dương. Với mỗi miền:

- Kiểm tra số khoảng `<= gridSize` và số khoảng `<= số giá trị ID`.
- Khoảng đầu bắt đầu tại `min`; khoảng cuối kết thúc tại `max+1`.
- Tất cả khoảng được sắp nối tiếp và không có khoảng có độ dài 0.
- Với từng ID trong miền nhỏ, đếm số khoảng thỏa `from <= id < to`; kết quả phải **đúng bằng 1**.

Phép thử random có thể bắt lỗi off-by-one khó phát hiện bằng 2–3 input thủ công. Không cần dùng `Thread.sleep` vì thuộc tính này là toán học, không phụ thuộc concurrency.

## 14. Integration test: đối soát dữ liệu khi chạy nhiều worker

Trên database test tương đương production:

1. Nạp tập nguồn thuộc cùng `batch_key`, ví dụ các ID `1, 2, 5, 10, 11, 100, 101, 501` (có khoảng trống).
2. Khởi chạy job với `minId=1`, `maxIdInclusive=501`, `gridSize=4`; dùng output `normalized_order`.
3. Đợi job hoàn tất, kiểm tra từng worker StepExecution và trạng thái manager.
4. So sánh **tập khóa đầu vào thuộc batch** với **tập khóa đầu ra**; nếu nghiệp vụ không filter/skip, hai tập phải bằng nhau.
5. So sánh giá trị `net_total` theo từng order; không chỉ kiểm `COUNT(*)`.
6. Chèn lỗi sau khi một số chunk/partition đã commit, cho job thất bại rồi **restart cùng JobInstance**; kiểm tra không nhân đôi tác động và partition hoàn tất không bị chạy lại ngoài ý muốn.

Một phép kiểm tra row bị bỏ sót:

~~~sql
SELECT s.id
FROM source_order AS s
LEFT JOIN normalized_order AS n
       ON n.batch_key = s.batch_key
      AND n.order_id = s.id
WHERE s.batch_key = :batch_key
  AND n.order_id IS NULL;
~~~

Nếu câu này trả dòng, có input chưa có kết quả. Nếu nghiệp vụ có filter/skip, phải điều chỉnh theo danh sách row hợp lệ cần xuất. Kiểm tra thêm tổng theo nghiệp vụ và bản ghi ngoài tập nguồn; primary key của bảng đích ngăn hai **dòng** cùng khóa nhưng không chứng minh đúng tất cả giá trị hoặc side effect bên ngoài DB.

**Test restart không nên dùng input live đang thay đổi**, vì sẽ rất khó biết lỗi đến từ Partitioner, checkpoint reader hay thay đổi dữ liệu.

## 15. Đo hiệu năng: chọn gridSize và pool theo nút thắt thực

Giả sử dữ liệu đã chốt có 1.000.000 row và mỗi worker dùng `chunk(200)`, số chunk lý tưởng trên toàn job khoảng **5.000**, nếu không có filter/skip hoặc cơ chế gây thêm lượt xử lý. Tổng commit thực đo có thể khác do chunk cuối, rollback, retry và metadata.

Một thí nghiệm kiểm soát:

| Thử nghiệm | `gridSize` | Pool thread | Cần so sánh |
| --- | --- | --- | --- |
| Baseline | 1 | 1 | Tổng thời gian, read/write count, DB latency |
| B | 4 | 2 | Có cải thiện khi hai partition hoạt động đồng thời? |
| C | 4 | 4 | CPU/DB pool có còn khả năng tăng throughput? |
| D | 16 | 4 | Nhiều vùng nhỏ có giảm skew so với overhead? |
| E | 32 | 8 | Có nghẽn pool, lock hoặc JobRepository không? |

Nên quan sát:

- **Theo partition:** readCount, writeCount, filterCount, skipCount, commitCount, rollbackCount, thời gian bắt đầu/kết thúc và throughput.
- **Theo executor:** active threads, queue depth, rejected tasks, thời gian chờ lịch.
- **Theo DB:** query plan cho range scan, index usage, latency, connection pool active/waiting, lock contention, transaction duration.
- **Theo JVM:** CPU, heap, GC pauses, thread contention.
- **Theo kết quả:** số khóa đầu ra, checksum/tổng tiền, lỗi nghiệp vụ và lượng bản ghi phải replay.

Khi nhiều partition chạy song song, tổng thời gian thường bị chi phối bởi **partition chậm nhất** cộng overhead điều phối, cộng tranh chấp tài nguyên. Nếu một partition mất 40 phút, ba partition còn lại mất 5 phút, tăng thread lên 16 chưa chắc hiệu quả; ưu tiên phân phối lại dữ liệu, giảm skew hoặc xử lý nguyên nhân gây chậm riêng của vùng đó.

**Không nhầm `gridSize` với số kết nối DB an toàn.** Bốn worker có thể dùng hơn bốn connection vì read cursor, write transaction, metadata hoặc tài nguyên khác. Giới hạn concurrency theo số đo, khả năng DB và các tác vụ ngoài batch cùng dùng hạ tầng.

## 16. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| ID ở ranh giới bị ghi hai lần | Cả hai worker dùng `<= max` hoặc biên kế tiếp không nhất quán | Dùng đúng `[from, to)` ở cả Partitioner và SQL |
| Mất ID đầu hoặc cuối | Dùng `>` ở cận trái; `max+1` tính sai | Unit test biên, kiểm tra inclusive/exclusive |
| Partition cuối trống/bị bỏ qua | Chia làm tròn sai, `gridSize > total` không xử lý | Dùng phép chia làm tròn lên và cắt cận cuối |
| Tràn `long` | `maxInclusive == Long.MAX_VALUE`, cộng biên không kiểm tra | Validate hoặc dùng BigInteger/biên đóng |
| Nhiều partition xong rất nhanh, một vùng chậm | ID thưa/skew hoặc row cost lệch | Đo row-count/cost theo khoảng, dùng quantile/nhiều vùng nhỏ |
| Restart bị thiếu/trùng dữ liệu | Đổi bounds, `gridSize`, tên partition hoặc nguồn live thay đổi | Cố định snapshot/JobParameters và writer idempotent |
| Reader lỗi cursor hoặc state | Dùng chung reader stateful, không tách scope | `@StepScope` theo StepExecution |
| Tăng worker khiến job chậm | Pool DB cạn, lock, disk I/O hoặc CPU đầy | Giảm concurrency và đo bottleneck |
| Job COMPLETED nhưng sai tổng | Processor hoặc writer có race/logic không idempotent | Đối soát business invariant, thử rollback/restart |
| Số partition không đúng dự tính | `gridSize` chỉ là yêu cầu; thuật toán trả ít entry | Ghi rõ hợp đồng Partitioner và kiểm thử map trả về |

## 17. Khi nào không nên chia theo khoảng khóa chính?

Range partitioning hoạt động tốt khi:

- Khóa chính có thứ tự và hỗ trợ so sánh khoảng, thường là số nguyên tăng dần.
- Có index phù hợp để đọc vùng dữ liệu hiệu quả.
- Các vùng được xử lý độc lập và output có khóa chống ghi trùng.
- Tập nguồn có thể chốt được trước khi chạy hoặc có chiến lược snapshot/restart rõ ràng.

Cân nhắc mô hình khác nếu:

- Khóa là UUID/hash không có thứ tự hữu ích cho range scan.
- Phân bố dữ liệu quá lệch, thời gian xử lý mỗi dòng biến thiên lớn và cân bằng bằng khoảng ID kém hiệu quả.
- Nghiệp vụ yêu cầu thứ tự xử lý theo tài khoản hoặc nhóm business key thay vì thứ tự ID.
- Dữ liệu nguồn thay đổi liên tục, không thể chốt snapshot và cần cơ chế queue/claim/CDC để xác định item đã xử lý.
- Một JVM không đủ tài nguyên và cần dùng **remote partitioning** qua middleware; thuật toán chia có thể giữ nguyên nhưng cần thêm retry, phản hồi và chống điều phối trùng.

Các lựa chọn thay thế bao gồm **partition theo ngày/tenant**, **bảng staging chứa danh sách ID đã chốt**, **hash bucket với số bucket ổn định**, hoặc **quantile boundary** trên nguồn bất biến. Quyết định dựa trên index, tính chất truy cập, yêu cầu restart và chi phí vận hành.

## 18. Bài thực hành và checklist

**Bài thực hành:** xây job Spring Batch chuẩn hóa 100.000 bản ghi có khóa `id` nhưng chủ động xóa ngẫu nhiên một số khoảng, tạo skew mạnh ở 10% miền ID cuối. Chạy cùng bộ dữ liệu với `gridSize=1,4,16` và pool `1,2,4`. Ghi lại thời gian từng partition và so sánh kết quả đầu ra.

Tiêu chí:

1. Với mọi cấu hình, mọi ID nguồn hợp lệ được xử lý **đúng theo nghiệp vụ** và xuất hiện đúng một khóa kết quả.
2. Không thiếu/trùng ở `id=1`, tại điểm chia và tại `id=maxId`.
3. Nếu một worker fail rồi restart, các partition trước đó hoàn tất không bị xử lý lại sai và kết quả cuối vẫn chính xác.
4. Có bằng chứng từ StepExecution/DB metrics để giải thích tại sao tăng `gridSize` hữu ích hoặc không.
5. Có phương án cải thiện skew dựa trên số liệu, không chọn concurrency chỉ từ số core CPU.

Checklist trước khi dùng trong môi trường thực:

- [ ] Định nghĩa rõ `fromInclusive` và `toExclusive` xuyên suốt Partitioner–ExecutionContext–SQL.
- [ ] Validate `gridSize`, min/max, trường hợp batch rỗng và phép cộng `max+1`.
- [ ] Giữ ổn định `batch_key`, snapshot, tên partition và identifying JobParameters khi restart.
- [ ] Reader có instance theo StepExecution, thứ tự đọc có tính xác định và checkpoint phù hợp.
- [ ] Writer có transaction, unique key/idempotency và xử lý retry/rollback được kiểm chứng.
- [ ] Unit test các ranh giới, dữ liệu thưa, `gridSize > total`, giá trị lớn và input không hợp lệ.
- [ ] Integration test so sánh tập ID và giá trị đầu vào/đầu ra, kể cả sau failure/restart.
- [ ] Đo độ lệch workload từng partition, connection pool, lock, CPU, GC và throughput.

**Ghi nhớ:** chia theo khoảng khóa chính giúp Spring Batch mở rộng một workload bằng những vùng dữ liệu có thể xử lý độc lập. **Tính đúng đắn** đến từ ranh giới không trùng/thiếu, tập nguồn bất biến, reader theo StepExecution và ghi có thể replay an toàn; **hiệu năng** đến từ phân bố dữ liệu thực, truy vấn có index và tài nguyên của worker/DB, chứ không chỉ từ việc tăng số partition.
