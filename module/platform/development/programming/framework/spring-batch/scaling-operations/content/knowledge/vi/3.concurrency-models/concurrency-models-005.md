# Partitioning Step trong Spring Batch

Một công việc tổng hợp 120 triệu giao dịch có thể mất nhiều giờ nếu chỉ một `Step` tuần tự đọc và ghi toàn bộ dữ liệu. Nếu dữ liệu chia được thành những phần độc lập, chẳng hạn các file hoặc các khoảng ID không chồng lấn, **Partitioning Step** cho phép Spring Batch tạo nhiều lần thực thi worker step, mỗi lần chịu trách nhiệm một phần dữ liệu. Các partition có thể chạy đồng thời trên nhiều thread trong **một JVM** hoặc được chuyển tới các worker JVM khác qua cơ chế phân phối phù hợp.

Bài học thuộc chương **Mô hình đồng thời** của module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán, đồng thời đo nút thắt thực tế, bảo đảm thread safety, retry/restart và tính ổn định khi vận hành. Nội dung tập trung vào cách **Partitioning Step** hoạt động, thiết kế partition an toàn, cấu hình local partitioning và quyết định khi nào nên dùng mô hình này.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích kiến trúc **manager step – partitioner – worker step – partition handler**.
2. Phân biệt `StepExecution` của manager với `StepExecution` và `ExecutionContext` riêng của từng partition.
3. Tạo `Partitioner` theo khoảng ID hoặc file, bảo đảm tên và phạm vi dữ liệu ổn định.
4. Cấu hình local partitioning trong Spring Batch 5.x với `StepBuilder`, `TaskExecutor`, reader `@StepScope` và writer có transaction.
5. Hiểu `gridSize`, concurrency thực tế, giới hạn tài nguyên và hiện tượng partition skew.
6. Phân tích restart khi một partition lỗi, ranh giới checkpoint và idempotency.
7. So sánh partitioning với multi-threaded step, parallel steps, remote chunking và remote partitioning.
8. Thiết kế kiểm thử tải, kiểm thử lỗi và các phép đối soát dữ liệu trước khi triển khai.

## 2. Partitioning Step là gì?

**Partitioning** là kỹ thuật chia tập dữ liệu đầu vào hoặc một công việc độc lập thành **nhiều partition logic**. Với Spring Batch, mỗi partition chạy **cùng định nghĩa worker step** nhưng được cấp **ExecutionContext riêng** để biết nó phải xử lý phần dữ liệu nào.

Ví dụ job đọc đơn hàng trong khoảng ID `1..1_200_000`:

| Partition key | Phạm vi đọc | Worker thực thi |
| --- | --- | --- |
| `range-00` | 1–100.000 | Worker StepExecution 0 |
| `range-01` | 100.001–200.000 | Worker StepExecution 1 |
| `range-02` | 200.001–300.000 | Worker StepExecution 2 |
| … | … | … |
| `range-11` | 1.100.001–1.200.000 | Worker StepExecution 11 |

Tất cả worker chạy cùng công thức xử lý và logic ghi dữ liệu. Một worker không được phép tự đọc phần của worker khác nếu các partition được thiết kế không chồng lấn. Chúng có thể cùng ghi vào một bảng đích, nhưng writer phải an toàn khi nhiều transaction đồng thời.

~~~mermaid
flowchart LR
    I[("Nguồn đơn hàng")] --> M["Manager Step"]
    M --> P["Partitioner<br/>tạo 12 ExecutionContext"]
    P --> S["StepExecutionSplitter"]
    S --> H["PartitionHandler"]
    H --> W1["orderWorker:range-00"]
    H --> W2["orderWorker:range-01"]
    H --> W3["orderWorker:range-02"]
    H --> WX["… các partition khác"]
    W1 --> O[("Bảng kết quả")]
    W2 --> O
    W3 --> O
    WX --> O
    W1 -.-> J[("JobRepository")]
    W2 -.-> J
    W3 -.-> J
    M -.-> J
~~~

Các mũi tên từ handler tới nhiều worker biểu diễn **những StepExecution khác nhau**. Trong local partitioning, worker thường chạy trên các thread cùng JVM. Trong remote partitioning, handler phân phối StepExecution tới các JVM/worker khác; việc transport và cập nhật metadata phải được cấu hình đúng.

### 2.1. Chia work, không chia một Java object

Partition không phải là sao chép một object `ItemReader` rồi cùng tăng biến cursor. Ý tưởng là giao mỗi worker một phạm vi dữ liệu, ví dụ:

~~~text
workerStep:range-00
  stepExecutionContext = {minId: 1, maxId: 100000}

workerStep:range-01
  stepExecutionContext = {minId: 100001, maxId: 200000}

workerStep:range-02
  stepExecutionContext = {minId: 200001, maxId: 300000}
~~~

Mỗi worker dùng thông tin từ context của mình để cấu hình reader. Tập dữ liệu phải có một **quy tắc phân vùng xác định**; nếu dữ liệu bị chồng giữa hai partition, framework không tự khử trùng bản ghi.

### 2.2. Vì sao partitioning thường dễ quản lý state hơn multi-threaded step?

Trong một **multi-threaded step**, nhiều chunk task có thể cùng sử dụng một `StepExecution` và cùng reader stateful nếu ứng dụng cấu hình như vậy. Khi chunk hoàn tất lệch thứ tự, checkpoint có thể phức tạp.

Trong **partitioning**, từng partition có `StepExecution` và `ExecutionContext` riêng. Nếu dùng `@StepScope` cho reader, bean reader thuộc về từng worker StepExecution. Nhờ vậy có thể tách cursor và checkpoint theo file/khoảng ID, rồi chỉ restart partition chưa hoàn tất theo lịch sử trong `JobRepository`.

Điều đó **không** làm processor/writer/service singleton tự động thread-safe: nhiều partition vẫn có thể gọi cùng một singleton writer, JDBC pool và bảng đích. Phạm vi reader đã tách, nhưng tài nguyên dùng chung vẫn phải được kiểm chứng.

## 3. Các thành phần trong cơ chế partitioning

| Thành phần | Trách nhiệm | Điều phải giữ đúng |
| --- | --- | --- |
| `PartitionStep` | Manager step điều phối split, execute và aggregate | Tên manager/worker step ổn định |
| `Partitioner` | Trả về `Map<String, ExecutionContext>`, xác định tên và dữ liệu từng partition | Không có vùng dữ liệu trùng hoặc bị bỏ quên |
| `StepExecutionSplitter` | Tạo/khôi phục StepExecution cho các partition cần thực thi | Sử dụng lịch sử `JobRepository` khi restart |
| `PartitionHandler` | Gửi/khởi chạy worker StepExecution và thu thập kết quả | Giới hạn concurrency và xử lý lỗi đúng |
| **Worker `Step`** | Reader → processor → writer → commit các chunk trong partition | Thread safety, transaction, checkpoint |
| `JobRepository` | Lưu trạng thái JobExecution, manager/worker StepExecution và context | Metadata bền vững, khôi phục được |
| `StepExecutionAggregator` | Tổng hợp thông tin StepExecution của các worker cho manager | Không làm mất trạng thái và số liệu từ partition cũ khi restart |

### 3.1. Vòng đời khi manager bắt đầu

1. Job chạy tới manager partition step.
2. Manager gọi splitter, splitter dùng partitioner để lấy tên và `ExecutionContext`, rồi tạo StepExecution tương ứng.
3. `PartitionHandler` thực thi các StepExecution bằng local thread pool hoặc transport tới remote worker.
4. Worker đọc đúng phạm vi, xử lý và commit từng chunk theo transaction của worker step.
5. Mỗi worker cập nhật trạng thái và checkpoint của **StepExecution riêng**.
6. Handler thu nhận kết quả; aggregator tổng hợp cho manager.
7. Manager và job được đánh giá thành công hay lỗi theo kết quả các partition và cấu hình luồng job.

Đây là mô hình khái niệm cho một lần thực thi. Chi tiết về callback, cách gửi/nhận kết quả, thời điểm cập nhật trạng thái và retry khác nhau giữa `TaskExecutorPartitionHandler` và transport remote cụ thể.

~~~mermaid
sequenceDiagram
    participant J as Job
    participant M as PartitionStep
    participant S as StepExecutionSplitter
    participant R as JobRepository
    participant H as PartitionHandler
    participant W as Worker Step
    J->>M: Chạy manager step
    M->>S: split(workerStep, gridSize)
    S->>R: Đọc metadata partition (nếu restart)
    R-->>S: Lịch sử StepExecution
    S-->>M: Các worker StepExecution cần chạy
    M->>H: handle(stepExecutions)
    H->>W: Thực thi worker theo partition context
    W->>R: Lưu commit/checkpoint/status
    W-->>H: Kết quả StepExecution
    H-->>M: Tập kết quả worker
    M->>R: Tổng hợp & ghi trạng thái manager
~~~

## 4. Thiết kế partitioner cho dữ liệu lớn

Một partitioner tốt phải trả lời được bốn câu hỏi:

- **Coverage:** toàn bộ dữ liệu hợp lệ thuộc một partition nào đó chưa?
- **Disjointness:** có bản ghi nào xuất hiện trong hai partition không?
- **Stability:** cùng một JobInstance restart có dùng lại đúng tên/phạm vi đã định không?
- **Balance:** thời gian xử lý của các partition có tương đối đều nhau không?

Coverage và disjointness quyết định tính đúng đắn; stability quyết định khả năng restart; balance quyết định khả năng mở rộng.

### 4.1. Chia theo khoảng ID

Nếu phạm vi snapshot là `[1, 1_200_000]` và chia 12 phần, mỗi phần 100.000 ID. Query worker dùng điều kiện tương ứng:

~~~sql
SELECT order_id, amount
FROM orders
WHERE order_id BETWEEN :minId AND :maxId
ORDER BY order_id;
~~~

`BETWEEN` bao gồm cả hai biên. Nếu tạo khoảng tiếp theo bắt đầu bằng `maxId` cũ, hai partition sẽ trùng bản ghi ở biên; phải bắt đầu bằng `maxId + 1`. Có thể dùng khoảng nửa mở `[startInclusive, endExclusive)` để giảm nguy cơ nhầm biên.

**Không giả định ID liên tiếp đồng nghĩa dữ liệu cân bằng.** Với ID bị xóa, dữ liệu lịch sử dồn vào một vùng hoặc thời gian processor khác nhau theo loại đơn hàng, 12 khoảng ID bằng nhau vẫn có thể tạo một partition dài hơn hẳn.

### 4.2. Chia theo file hoặc manifest

Ví dụ một đợt import có các file `orders-2026-11-25-001.csv`, `...002.csv`. Partitioner tạo key ổn định dựa trên định danh file; context chứa URI, checksum và version snapshot:

~~~text
"file-001" -> {uri: ".../orders-001.csv", checksum: "..."}
"file-002" -> {uri: ".../orders-002.csv", checksum: "..."}
"file-003" -> {uri: ".../orders-003.csv", checksum: "..."}
~~~

Cần tránh đặt tên `partition0`/`partition1` theo thứ tự không ổn định của `File.listFiles()`. Nếu thứ tự file thay đổi trước restart, một tên cũ có thể trỏ sang file khác, làm checkpoint sai. Hãy **đóng băng manifest đầu vào** theo JobInstance, có tên partition và dữ liệu tham chiếu ổn định.

### 4.3. Chia theo khóa nghiệp vụ

Nếu cùng `customer_id` có nhiều bản ghi phụ thuộc thứ tự, có thể gán tất cả giao dịch của một khách hàng vào cùng một partition bằng hàm băm khóa hoặc bảng phân bổ cố định. Điều này giúp tránh hai worker cùng tranh cập nhật một khách hàng.

Cần cảnh giác `hash(customer_id) % partitionCount`: nếu đổi `partitionCount` giữa các lần chạy cùng JobInstance, các key có thể chuyển partition, phá mapping checkpoint. Cách phân tuyến phải được cố định theo phiên bản partitioning/snapshot trong vòng đời JobInstance.

### 4.4. Snapshot và thay đổi dữ liệu trong khi chạy

Query worker có thể đúng phạm vi nhưng kết quả vẫn thiếu/trùng khi dữ liệu nguồn thay đổi trong lúc các partition đọc:

- Một bản ghi được insert với ID thuộc một range vừa đọc xong.
- Bản ghi chuyển trạng thái khiến điều kiện `WHERE` thay đổi.
- Dữ liệu bị cập nhật và mỗi partition đọc tại một thời điểm khác nhau.

Cần quy định **data cutoff, snapshot, isolation level hoặc chiến lược watermark**. Với dữ liệu lớn, có thể dùng bảng staging/snapshot bất biến hoặc mốc `updated_at <= cutoff` kết hợp điều kiện ổn định; watermark thời gian đơn độc không loại bỏ mọi race nếu nguồn còn thay đổi hồi tố.

## 5. Ví dụ Java: local partitioning với Spring Batch 5.2

Ví dụ sau chia snapshot đơn hàng thành 12 khoảng ID, thực thi tối đa bốn worker StepExecution đồng thời **trong cùng JVM**. Mỗi worker đọc dữ liệu bằng reader `@StepScope`, xử lý phí 5% và upsert kết quả vào PostgreSQL.

Đây là **ví dụ cấu hình tích hợp**, không phải ứng dụng độc lập hoàn chỉnh: cần Spring Batch 5.2.x, Spring Framework/Boot tương ứng, Java 17+, `DataSource`, `JobRepository`, transaction manager và bảng nguồn/đích. Danh sách khoảng ID được cố định chỉ để minh họa; production phải lấy từ một snapshot/manifest đáng tin cậy.

### 5.1. Bảng nguồn và đích minh họa

~~~sql
-- PostgreSQL, ví dụ tối giản
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL
);

CREATE TABLE order_summary (
    order_id BIGINT PRIMARY KEY,
    total_amount NUMERIC(18, 2) NOT NULL
);
~~~

### 5.2. Định nghĩa Partitioner, worker step và manager step

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.LinkedHashMap;
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
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class PartitioningExampleConfig {

    public record OrderRow(long id, BigDecimal amount) {}
    public record OrderResult(long id, BigDecimal total) {}

    @Bean
    public Partitioner orderRangePartitioner() {
        return gridSize -> {
            Map<String, ExecutionContext> parts = new LinkedHashMap<>();
            for (int i = 0; i < 12; i++) {
                long minId = 1L + i * 100_000L;
                long maxId = minId + 99_999L;
                ExecutionContext context = new ExecutionContext();
                context.putLong("minId", minId);
                context.putLong("maxId", maxId);
                parts.put(String.format("range-%02d", i), context);
            }
            return parts;
        };
        // Ví dụ cố định 12 range; gridSize là hint, không bắt buộc
        // Partitioner phải tạo đúng gridSize partition.
    }

    @Bean
    @StepScope
    public JdbcCursorItemReader<OrderRow> orderRangeReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['minId']}") Long minId,
            @Value("#{stepExecutionContext['maxId']}") Long maxId) {

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("orderRangeReader")
                .dataSource(dataSource)
                .sql("""
                     SELECT order_id, amount
                     FROM orders
                     WHERE order_id BETWEEN ? AND ?
                     ORDER BY order_id
                     """)
                .preparedStatementSetter(ps -> {
                    ps.setLong(1, minId);
                    ps.setLong(2, maxId);
                })
                .rowMapper((rs, rowNum) -> new OrderRow(
                        rs.getLong("order_id"),
                        rs.getBigDecimal("amount")))
                .fetchSize(500)
                .saveState(true)
                .build();
    }

    @Bean
    public ItemProcessor<OrderRow, OrderResult> addFeeProcessor() {
        BigDecimal factor = new BigDecimal("1.05");
        return row -> new OrderResult(
                row.id(),
                row.amount().multiply(factor)
                        .setScale(2, RoundingMode.HALF_UP));
    }

    @Bean
    public JdbcBatchItemWriter<OrderResult> orderSummaryWriter(
            DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderResult>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO order_summary(order_id, total_amount)
                     VALUES (:id, :total)
                     ON CONFLICT (order_id)
                     DO UPDATE SET total_amount = EXCLUDED.total_amount
                     """)
                .itemSqlParameterSourceProvider(row ->
                        new MapSqlParameterSource()
                                .addValue("id", row.id())
                                .addValue("total", row.total()))
                .build();
    }

    @Bean
    public Step orderWorkerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcCursorItemReader<OrderRow> orderRangeReader,
            ItemProcessor<OrderRow, OrderResult> addFeeProcessor,
            JdbcBatchItemWriter<OrderResult> orderSummaryWriter) {

        return new StepBuilder("orderWorkerStep", jobRepository)
                .<OrderRow, OrderResult>chunk(500, transactionManager)
                .reader(orderRangeReader)
                .processor(addFeeProcessor)
                .writer(orderSummaryWriter)
                .build();
    }

    @Bean
    public TaskExecutor partitionTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(12);
        executor.setThreadNamePrefix("partition-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step orderManagerStep(
            JobRepository jobRepository,
            @Qualifier("orderRangePartitioner") Partitioner partitioner,
            @Qualifier("orderWorkerStep") Step worker,
            @Qualifier("partitionTaskExecutor") TaskExecutor executor) {

        return new StepBuilder("orderManagerStep", jobRepository)
                .partitioner("orderWorkerStep", partitioner)
                .step(worker)
                .gridSize(12)
                .taskExecutor(executor)
                .build();
    }

    @Bean
    public Job summarizeOrdersJob(
            JobRepository jobRepository,
            @Qualifier("orderManagerStep") Step orderManager) {

        return new JobBuilder("summarizeOrdersJob", jobRepository)
                .start(orderManager)
                .build();
    }
}
~~~

**Cách đọc cấu hình:**

- `orderRangePartitioner` tạo 12 key `range-00` tới `range-11`, tương ứng 12 `ExecutionContext`. Ví dụ bỏ qua giá trị `gridSize` có chủ đích vì snapshot được cố định thành 12 range.
- `partitioner("orderWorkerStep", partitioner)` gắn partitioner với tên worker step. Các StepExecution con được định danh theo dạng `orderWorkerStep:range-00`, `...:range-01`.
- `@StepScope` giúp mỗi worker `StepExecution` có reader riêng và late-bind `minId`/`maxId` từ context. Reader không phải chia sẻ một JDBC cursor mutable giữa bốn thread.
- `chunk(500, transactionManager)` áp dụng **trong từng worker partition**. Manager không trực tiếp đọc/ghi tất cả item.
- `taskExecutor` với core/max = 4 có thể chạy tối đa bốn worker step đồng thời trong executor minh họa, còn các partition khác đợi. `queueCapacity=12` chỉ chứa task đợi, không có nghĩa 16 partition đồng thời.
- `gridSize(12)` là gợi ý tới splitter/partitioner, **không phải** trần worker threads, chunk size hay số connection.
- Writer upsert theo `order_id` giúp chạy lại cùng kết quả không tạo thêm dòng; nếu nghiệp vụ cho phép dữ liệu khác phiên bản cập nhật chồng lấn, cần thêm versioning hoặc quy tắc idempotency.
- Cấu hình JDBC cần dự trù reader cursor connection, writer transaction connection, JobRepository và các step khác. Không được suy “4 worker = đúng 4 JDBC connections”.

### 5.3. Một số lưu ý API

Ví dụ sử dụng API phổ biến của **Spring Batch 5.2.x**. Với Spring Batch 6.x hoặc custom infrastructure, hãy đối chiếu signature và cách cung cấp transaction manager/datasource của phiên bản đang dùng. Tùy loại reader, cấu hình cursor, fetch size, transaction isolation và driver PostgreSQL, số connection giữ mở và hành vi checkpoint khác nhau; cần thử nghiệm với driver/database thực.

Trong dự án thực, Partitioner cũng có thể được triển khai thành class riêng để kiểm thử coverage/disjointness, lấy snapshot ID từ identifying `JobParameters` và đọc manifest có version. Không dùng một hằng range `1..1_200_000` nếu nguồn thực vượt phạm vi; các bản ghi bên ngoài range sẽ không được xử lý và không tạo lỗi mặc định.

## 6. Khi chạy thực tế, số worker phụ thuộc điều gì?

Phân biệt ba con số thường gặp:

- **Số partition logic (`P`):** bao nhiêu mảnh dữ liệu được chia.
- **Số worker concurrent (`C`):** bao nhiêu StepExecution đang hoạt động đồng thời.
- **Chunk size (`K`):** số item mỗi transaction chunk thông thường bên trong một worker.

Với ví dụ `P=12`, `C=4`, `K=500`:

~~~text
12 partition logic
    |
    +-- 4 partition tối đa đang chạy trong executor
    |      |
    |      +-- mỗi partition tự chạy các chunk 500 item
    |
    +-- 8 partition còn lại chờ lịch
~~~

Nếu mỗi partition có 100.000 item, một partition cần khoảng 200 chunk dữ liệu. Nhưng đó **không** có nghĩa cả 800 chunk (4 × 200) chạy đồng thời; trong mẫu local partitioning, mỗi worker step thường xử lý các chunk của partition **tuần tự** trừ khi chính worker step còn được cấu hình thêm multi-threading.

### 6.1. Bài toán capacity sơ bộ

Giả sử một worker xử lý ổn định 400 item/s khi đứng một mình và các nguồn/đích không tranh chấp. Bốn worker có trần lý tưởng:

\[
R_{\mathrm{ideal}} = 4\times400 = 1{,}600\ \text{item/s}.
\]

Với 1.200.000 item, thời gian xử lý lý tưởng khoảng:

\[
T_{\mathrm{ideal}}=\frac{1{,}200{,}000}{1{,}600}
=750\ \text{s}=12{,}5\ \text{phút}.
\]

Con số này bỏ qua overhead manager, startup, context switch, skew, DB locks, I/O, transaction, validation, retry và publish. Nếu DB chỉ có thể commit 900 item/s khi nhiều transaction đồng thời, thêm worker không thể vượt trần ấy một cách bền vững.

### 6.2. `gridSize` không quyết định throughput một mình

Một partitioner có thể dùng `gridSize` để quyết định số mảnh; cũng có thể bỏ qua nó để lấy danh sách file đã biết. `gridSize` là hint cho partitioning, không phải một lệnh bắt buộc tạo đúng bằng đó partition.

Chẳng hạn tạo 200 partition nhưng executor chỉ có 8 threads cho phép chia work mịn hơn, có thể giúp cân bằng tải nếu mỗi partition đủ nhỏ. Tuy nhiên, 200 partition tạo thêm StepExecution/metadata/khởi động reader và truy vấn. Partition quá nhỏ có thể khiến overhead lấn át lợi ích concurrency.

Ngược lại, chỉ có hai partition dù executor 16 threads thì thường chỉ có tối đa hai worker StepExecution độc lập để chạy trong mô hình minh họa, khiến phần lớn thread rảnh.

## 7. Partition skew và chiến lược cân bằng tải

**Partition skew** là hiện tượng một số partition xử lý lâu hơn hẳn các partition khác. Tổng thời gian job thường bị quyết định bởi các partition chậm nhất, ngay cả khi nhiều worker rảnh sau khi hoàn thành phần của mình.

Ví dụ có tám partition chạy trên bốn threads:

| Partition | Thời gian xử lý nếu không tranh chấp | Nguyên nhân |
| --- | ---: | --- |
| `range-00` đến `range-06` | Mỗi cái 2 phút | Ít record, xử lý đồng đều |
| `range-07` | 20 phút | Nhiều record hoặc dữ liệu đòi API chậm |

Cho dù chạy bốn hay tám threads, job khó hoàn tất dưới khoảng **20 phút** nếu `range-07` chỉ chạy trên một worker tuần tự. Cần phân tích phạm vi dữ liệu của partition nặng, không chỉ tăng pool size.

Các lựa chọn:

1. Dùng **histogram/count per range** từ snapshot để chia các khoảng chứa số bản ghi gần nhau.
2. Chia theo file có dung lượng và độ phức tạp tương đối cân bằng.
3. Phân hoạch theo hash key ổn định khi độ phân bố ID không đều; bảo toàn yêu cầu giữ thứ tự theo khóa.
4. Tạo nhiều partition nhỏ hơn mức concurrency nếu overhead metadata và startup chấp nhận được.
5. Đối với skew do API hoặc DB lock, tối ưu processor, writer và thứ tự truy cập trước khi chia thêm.

Một partition cần có ranh giới **không đổi trong một lần restart của cùng JobInstance**. Thay đổi sơ đồ chia shard giữa chừng để “cứu” partition lỗi có thể làm checkpoint và metadata sai; thay đổi lớn nên áp dụng cho JobInstance mới hoặc có kế hoạch migration/đối soát riêng.

## 8. Thread safety và transaction khi chạy nhiều partition

Partitioning tách reader state theo worker StepExecution, nhưng nhiều bean vẫn có thể dùng chung:

| Thành phần | Thường chia sẻ giữa các worker? | Việc cần kiểm tra |
| --- | --- | --- |
| `@StepScope` reader | Instance riêng theo StepExecution trong cấu hình đúng | Input partition không trùng, checkpoint đúng |
| Singleton `ItemProcessor` | Có thể dùng chung | Không giữ biến instance `currentItem` mutable |
| Singleton `ItemWriter` | Có thể dùng chung | Implementation có an toàn khi gọi đồng thời, transaction-bound resources |
| `DataSource` / HikariCP | Thường dùng chung trong JVM | Số connection, acquire time, pool pending |
| `JobRepository` | Dùng chung | Database metadata đủ throughput, transaction nhất quán |
| HTTP client/service | Có thể dùng chung | Connection pool, thread safety, rate limit |
| Bảng đích | Thường dùng chung | Row locks, deadlocks, unique keys, partition conflict |

### 8.1. Mỗi worker chunk có transaction riêng

Trong worker step chunk-oriented, mỗi chunk thường chạy trong một transaction. Nhiều worker có thể cùng có transaction mở, nên tổng lock contention tăng theo concurrency và phạm vi dữ liệu ghi.

Ví dụ sai nếu hai partition cùng tăng một số dư:

~~~sql
-- Không idempotent; dữ liệu nguồn trùng ở hai partition sẽ bị cộng hai lần.
UPDATE account_balance
SET balance = balance + :amount
WHERE account_id = :account_id;
~~~

Nếu mục tiêu là kết quả cuối cùng xác định theo ID, có thể ghi kiểu upsert:

~~~sql
INSERT INTO account_snapshot(account_id, final_balance, source_version)
VALUES (:account_id, :balance, :version)
ON CONFLICT (account_id) DO UPDATE
SET final_balance = EXCLUDED.final_balance,
    source_version = EXCLUDED.source_version
WHERE account_snapshot.source_version < EXCLUDED.source_version;
~~~

Dù upsert hạn chế một số tác dụng lặp, nó không tự bảo đảm business correctness nếu partition tạo ra hai kết quả mâu thuẫn cùng version. Với thanh toán và side effect ngoài database transaction, cần idempotency key/outbox hoặc cơ chế đối soát với hệ thống đích.

### 8.2. Tại sao giữ partition không trùng vẫn cần idempotency?

Một worker đã commit chunk rồi bị crash trước khi các trạng thái liên quan được xác nhận đầy đủ. Khi restart, một số item/chunk có thể được xử lý lại tùy transaction/checkpoint. Trong remote partitioning, mất kết nối/response còn làm yêu cầu phục hồi phức tạp hơn.

**Partition không trùng** ngăn hai worker cố ý lấy cùng bản ghi ở một lần chia; **idempotency** bảo vệ tác dụng nghiệp vụ khi retry, redelivery hoặc restart. Hai lớp bảo đảm giải quyết hai vấn đề khác nhau và đều cần thiết.

### 8.3. Database pool và transaction resources

Với bốn partition đang chạy, nếu mỗi worker giữ một JDBC cursor connection để đọc và cần connection khác để ghi, số connection cần thiết có thể cao hơn bốn, chưa kể JobRepository. Không lấy số thread làm đúng bằng `maximumPoolSize` mà không đo.

Một ví dụ ngân sách:

~~~text
DB cho batch còn tối đa 24 connections
    4 dành cho JobRepository/manager và tải nền
    4 dự phòng phục hồi/monitoring
   16 dành cho worker I/O

Nếu mỗi worker có thể giữ tối đa 2 connections cùng lúc,
thử ban đầu khoảng 8 worker concurrent là trần bảo thủ,
sau đó đo active/pending/hold time và DB wait.
~~~

Đây là kịch bản minh họa, không phải quy tắc Spring Batch. Các connection có thể cấp phát theo các giai đoạn khác nhau; số connection tối ưu phải dựa vào ranh giới transaction và quan sát thực tế.

## 9. Restart chỉ partition cần phục hồi

Một lợi ích lớn của Spring Batch partitioning là metadata theo **partition StepExecution**.

Giả sử JobInstance `dailyOrders(snapshot=2026-11-25)` chạy bốn partition:

| Worker step name | JobExecution lần 1 | Lần restart cùng JobInstance |
| --- | --- | --- |
| `orderWorkerStep:range-00` | `COMPLETED` | Mặc định được bỏ qua |
| `orderWorkerStep:range-01` | `COMPLETED` | Mặc định được bỏ qua |
| `orderWorkerStep:range-02` | `FAILED` | Được chọn chạy lại |
| `orderWorkerStep:range-03` | `COMPLETED` | Mặc định được bỏ qua |

Khi restart cùng **JobInstance**, `SimpleStepExecutionSplitter` dùng trạng thái các partition đã lưu trong `JobRepository`. Partition đã `COMPLETED` thường không cần thực thi lại, còn partition `FAILED`/`STOPPED` hoặc chưa hoàn tất sẽ được phục hồi theo trạng thái và chính sách restart. `gridSize` có thể được bỏ qua khi khôi phục tập partition trước đó.

~~~mermaid
flowchart TD
    A["Restart JobExecution cùng JobInstance"] --> B["Đối chiếu JobRepository"]
    B --> C{"Partition đã COMPLETED?"}
    C -->|Có| D["Không chạy lại partition đó<br/>dùng metadata đã có"]
    C -->|Chưa| E["Khôi phục StepExecution / ExecutionContext"]
    E --> F["Worker tiếp tục từ checkpoint hợp lệ"]
    D --> G["Manager tổng hợp kết quả"]
    F --> G
~~~

**Hai cấp cần phân biệt:**

- **Chọn partition:** dựa vào tên partition và trạng thái StepExecution trước đó.
- **Tiếp tục trong partition:** dựa vào checkpoint của `ItemReader`/`ItemStream` và `ExecutionContext` tại các lần commit hợp lệ.

Một partition `FAILED` có thể đã commit 8.000/10.000 item. Nếu reader lưu state đúng và input không đổi, restart có thể tiếp tục từ checkpoint, không nhất thiết đọc lại toàn bộ 10.000 item.

### 9.1. Các điều kiện làm restart an toàn

1. **Cùng JobInstance:** giữ identifying `JobParameters`; không tự tăng `run.id` để “restart”.
2. **Metadata bền vững:** giữ `JobRepository` và các bảng `BATCH_STEP_EXECUTION`, `BATCH_STEP_EXECUTION_CONTEXT`.
3. **Tên ổn định:** không đổi `orderWorkerStep` thành tên khác hoặc đổi key `range-02` thành một key mới trước restart.
4. **Input ổn định:** snapshot/file/query range không thay đổi ngữ nghĩa giữa các lần chạy.
5. **Checkpoint hợp lệ:** `ItemStream` được quản lý đúng, context phản ánh công việc đã commit.
6. **Writer có transaction/idempotency:** chunk chưa commit hoặc side effect ngoài transaction không làm lặp nghiệp vụ.
7. **Chính sách step đúng:** không bật `allowStartIfComplete(true)` cho worker nếu chủ đích là bỏ qua partition đã hoàn tất.
8. **Vận hành có kiểm soát:** xác minh worker cũ thực sự dừng trước khi restart, đặc biệt ở remote topology.

Có thể dùng `JobOperator.restart(failedJobExecutionId)` trên một JobExecution phù hợp để tạo lần thử mới cho cùng JobInstance. Không tự chạy lẻ worker step trong JobInstance khác nếu muốn giữ quan hệ manager, metadata và tổng hợp kết quả.

### 9.2. `PartitionNameProvider` trong restart

Một số partitioner tính toán hàng triệu phạm vi hoặc quét manifest lớn trước khi chia. Có thể triển khai `PartitionNameProvider` để khi restart framework lấy **tên partition** nhanh hơn mà không tạo lại toàn bộ context; các context đã lưu được dùng cho partition cũ.

Điều kiện tiên quyết là tên do `getPartitionNames(int gridSize)` trả về phải **giống key của partitioner** ở lần chạy ban đầu. Đây là tối ưu cách lấy tên, không phải cho phép đổi danh tính partition giữa các lần chạy.

## 10. Local partitioning và remote partitioning

Cùng mô hình manager/splitter/worker có thể được thực thi với hai cách phân phối:

| Tiêu chí | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Worker chạy ở đâu? | Nhiều thread trong **cùng JVM** | Nhiều JVM/pod/máy |
| PartitionHandler | Thường `TaskExecutorPartitionHandler` | Handler dùng messaging/transport hoặc cơ chế phân phối tương thích |
| Hạ tầng | JobRepository và executor local | Thêm broker/network/routing/worker deployment |
| Input | Có thể là file hoặc JDBC truy cập trong JVM | Mọi worker phải truy cập được đúng snapshot hoặc shared storage |
| Failure | Thread exception/process crash | Ngoài lỗi worker còn có broker/network/timeout/reply |
| Concurrency | Giới hạn bởi một JVM và downstream | Có thể tăng theo worker pods, vẫn bị downstream giới hạn |
| Restart | Metadata StepExecution theo partition | Cùng nguyên tắc, nhưng cần xử lý trạng thái worker/response nhất quán |

**Remote partitioning không phải remote chunking.** Với remote partitioning, manager chia **StepExecution/partition** để worker **tự đọc, xử lý và ghi** phần dữ liệu của nó. Với remote chunking, manager **đọc và tạo chunk request**, sau đó các worker nhận chunk để xử lý/ghi qua request/reply middleware.

~~~text
Remote partitioning:
Manager -> phân phối {workerStep:range-02, minId, maxId}
Worker  -> tự read/process/write range-02

Remote chunking:
Manager -> tự read và gửi chunk gồm các item
Worker  -> process/write chunk rồi gửi reply
~~~

Remote partitioning thích hợp khi có thể chia input để worker chủ động đọc. Remote chunking thích hợp khi reader tập trung đã đủ nhanh nhưng processor/writer cần phân tán. Cả hai phải tính đến network, broker, idempotency và vận hành job.

## 11. So sánh Partitioning Step với các mô hình concurrency

| Mô hình | Đơn vị song song | Phạm vi state | Khi nào chọn |
| --- | --- | --- | --- |
| Chunk step tuần tự | Các chunk lần lượt | Một StepExecution | Baseline, input stateful khó chia, SLA vẫn đáp ứng |
| Multi-threaded step | Nhiều chunk trên một step | Thường chung StepExecution; cần xử lý shared reader/checkpoint | Chunk độc lập và các component thread-safe |
| **Partitioning Step** | Nhiều worker StepExecution trên các shard | Mỗi partition có ExecutionContext riêng | Input chia được, muốn kiểm soát checkpoint/restart theo shard |
| Parallel steps | Nhiều step/flow độc lập | StepExecution theo step | Pipeline có nhiều nhánh nghiệp vụ độc lập |
| Remote chunking | Chunk request qua middleware | Reader ở manager, xử lý/ghi ở worker | Processor/writer cần scale, reader không phải nút thắt |

Lựa chọn phụ thuộc dữ liệu và nghẽn thực tế. Nếu một bảng nguồn chỉ hỗ trợ một query chậm, chia theo ID có thể giúp tăng song song; nhưng nếu database đã bão hòa CPU hoặc I/O, thêm partition chỉ tăng tranh chấp. Nếu nhiều dòng cùng cập nhật một account và cần thứ tự toàn cục, phải thiết kế quy tắc phân tuyến theo khóa hoặc serialization trước khi chia.

## 12. Benchmark partitioning theo SLA và nút thắt

Một kế hoạch đo tốt phải dùng dữ liệu đại diện, đúng số lượng record, phân bố giá trị và tải đồng thời của các ứng dụng khác. Giả sử có 12 triệu item, deadline dành riêng cho xử lý là 40 phút:

\[
R_{\text{required}} =
\frac{12{,}000{,}000}{40\times60} = 5{,}000\ \text{item/s}.
\]

Nếu baseline một worker đạt 900 item/s và ít tranh chấp, cần thử khoảng sáu worker cho công suất lý tưởng 5.400 item/s. Tuy nhiên, **không đủ cơ sở để kết luận sáu worker chắc chắn đạt SLA**: tổng throughput có thể suy giảm khi cùng tranh DB pool, API hoặc hot rows.

### 12.1. Ma trận thử nghiệm minh họa

| Partition count | Concurrent workers | Throughput commit thực nghiệm *giả định* | p95 worker chunk latency | Nhận xét |
| ---: | ---: | ---: | ---: | --- |
| 1 | 1 | 900 item/s | 600 ms | Baseline |
| 12 | 2 | 1.720 item/s | 650 ms | Tăng gần tuyến tính |
| 12 | 4 | 3.150 item/s | 720 ms | Còn lợi ích |
| 12 | 6 | 4.850 item/s | 850 ms | Gần mục tiêu, cần thêm headroom |
| 12 | 8 | 5.050 item/s | 1.600 ms | DB/lock có dấu hiệu bão hòa |
| 24 | 12 | 4.780 item/s | 2.900 ms | Tăng tranh chấp, throughput giảm |

Các con số **giả định** chỉ minh họa dạng đường cong throughput khi scale; không phải số đo của Spring Batch. Nếu muốn đạt 5.000 item/s với dự phòng phục hồi, có thể cần tối ưu DB, giảm thời gian xử lý hoặc thay đổi resource allocation, thay vì chỉ dùng mức tám worker có headroom quá nhỏ.

### 12.2. Bộ metric quan trọng

- **Batch/partition:** `JobExecutionId`, `StepExecutionId`, tên partition, `readCount`, `writeCount`, `commitCount`, `rollbackCount`, skip/retry và duration.
- **Skew:** thời gian từng partition, số item, p50/p95/p99 duration và partition cuối cùng hoàn tất.
- **Executor:** active threads, queue depth, rejected tasks, task wait time.
- **DB/transaction:** Hikari active/pending/acquire latency, DB connection usage, lock waits/deadlocks, slow query, transaction duration, IOPS.
- **JVM:** CPU quota/usage, heap, GC pause, thread count, memory peak.
- **Remote nếu có:** broker backlog, delivery/retry, worker liveness, request/response correlation.
- **Data correctness:** số ID duy nhất, không thiếu/nhân đôi phạm vi, checksum/reconciliation sau restart.

Khi một worker bị chậm, tổng thời gian job có thể bị chi phối bởi partition cuối cùng. Quan sát **max partition duration**, không chỉ average worker duration. Khi tune `gridSize` và concurrency, thay từng biến ở một lần thử để phân biệt tác động của chi phí phân vùng và giới hạn worker.

## 13. Kịch bản kiểm thử Partitioning Step

Hãy bắt đầu với một snapshot có 120.000 `order_id` duy nhất, chia 12 partition; đánh dấu log theo `partitionKey`, `StepExecutionId` và job ID.

| Kịch bản | Thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Coverage | Chạy với 12 range không chồng lấn | Mọi ID thuộc snapshot được xử lý đúng một phạm vi |
| Biên range | Đặt dữ liệu ở ID `100000` và `100001` | Hai record đi đúng hai partition kề nhau |
| Partition thiếu dữ liệu | Một range không có record | Worker hoàn tất rỗng hợp lệ, không làm thiếu record khác |
| Thay concurrency | Cùng 12 partition, thử executor 1/2/4/8 | Output cuối giống nhau, throughput được đo |
| Skew | Một range chứa item xử lý chậm | Đo được long-tail; phát hiện nút thắt partition |
| Writer conflict | Nhiều partition ghi chung bảng | Không deadlock kéo dài, ghi đúng unique key và transaction |
| Lỗi một partition | Cố ý ném exception tại `range-03` | Manager/job phản ánh lỗi, các partition còn lại có trạng thái riêng |
| Restart partition lỗi | Sửa nguyên nhân, restart đúng JobInstance | Theo chính sách mặc định chỉ partition chưa hoàn tất phải chạy lại |
| Crash sau commit | Kill worker/process giữa các chunk | Checkpoint và writer bảo toàn kết quả, không thiếu/ghi lặp |
| Input thay đổi | Sửa snapshot sau khi job lỗi | Phát hiện vi phạm, không âm thầm gắn checkpoint cũ vào dữ liệu mới |
| DB pool cạn | Giảm pool hoặc tăng workers quá mức | Có metrics/alert, backpressure/recovery phù hợp |
| Worker remote mất tín hiệu | Chặn response hoặc kill pod (nếu remote) | Đối soát và khôi phục, không giả định dữ liệu chưa ghi |

Dữ liệu sau chạy phải thỏa các bất biến đã định:

~~~text
Count(DISTINCT output.order_id) == Count(expected source order_id)
Every expected source order_id has exactly one final business result
No order_id outside approved snapshot/ranges is processed
Aggregate totals match independently calculated reference
Restarted run produces same final business result as a clean run
~~~

Khi kiểm thử, nên dùng `JobRepository` bền vững, database đầu ra thật trong môi trường thử nghiệm và mô phỏng crash ở nhiều điểm commit. Một test chỉ so map `Partitioner.partition(...)` với danh sách dự kiến **không đủ chứng minh** restart và transaction an toàn.

### 13.1. Tách kiểm thử logic và integration test

- **Unit test partitioner:** chứng minh tên duy nhất, đủ phạm vi, không trùng ranh giới, stable khi đầu vào cố định; đặc biệt test nửa mở/đóng biên.
- **Integration test worker:** reader nhận đúng `StepExecutionContext`, writer commit/rollback đúng, checkpoint có thể resume.
- **End-to-end test manager:** tạo nhiều StepExecution, tổng hợp đúng trạng thái, restart chỉ phần lỗi.
- **Load test:** chạy trên volume/partition skew đại diện, xem DB IOPS, connection pool, p95/p99 và deadline.

Các thử nghiệm này có giá trị vì kiểm tra **hợp đồng giữa các thành phần**, không chỉ lặp lại chi tiết code đang triển khai.

## 14. Những hiểu nhầm phổ biến

| Nhận định | Điều cần sửa |
| --- | --- |
| “`gridSize=12` thì có 12 thread hoạt động.” | `gridSize` là hint phân vùng; concurrency phụ thuộc `PartitionHandler`/executor và số partition thực. |
| “Mỗi partition là một JobInstance.” | Các partition là **worker StepExecution** trong cùng lần điều phối job, không phải JobInstance độc lập. |
| “Partition là các chunk song song của một StepExecution.” | Đó gần với multi-threaded step; partitioning có StepExecution riêng theo shard. |
| “`@StepScope` tạo reader riêng cho mỗi item.” | Scope theo StepExecution của partition, không theo item. |
| “Chia ID đều sẽ chia đều công việc.” | Dữ liệu và độ khó xử lý có thể phân bố không đều. |
| “Đã chia phạm vi không trùng thì writer không cần idempotent.” | Retry/crash/restart vẫn có thể xử lý lại chunk. |
| “Thêm partition luôn giảm thời gian job.” | Metadata/reader startup, DB locks, I/O và skew có thể giới hạn throughput. |
| “Restart job đồng nghĩa chạy lại tất cả partition.” | Khi tên/metadata ổn định, partition `COMPLETED` thường được skip mặc định. |
| “Có thể đổi partition key sau khi lỗi mà không ảnh hưởng.” | Key liên kết với StepExecution/ExecutionContext; đổi có thể làm sai restart. |
| “Remote partitioning và remote chunking giống nhau.” | Một bên gửi partition để worker tự đọc; bên kia manager đọc và gửi chunk item. |

## 15. Checklist áp dụng Partitioning Step

- [ ] Xác định SLA, volume peak và throughput commit cần đạt.
- [ ] Có phương pháp chia input thành các partition **đủ và không trùng**.
- [ ] Tên partition, phạm vi dữ liệu và snapshot ổn định qua restart.
- [ ] Reader dùng đúng `stepExecutionContext` và có state riêng theo `StepExecution`.
- [ ] Processor/writer/service singleton được kiểm chứng thread safety.
- [ ] Writer có transaction, idempotency và quy tắc version nghiệp vụ.
- [ ] `JobRepository` bền vững, đọc được lịch sử partition/chunk checkpoint.
- [ ] `gridSize`, worker concurrency và chunk size được đo như **ba biến khác nhau**.
- [ ] Tổng kết nối JDBC/HTTP và DB capacity đã tính trên mọi pod/step.
- [ ] Theo dõi skew, longest partition, pending pool, lock waits và retry rate.
- [ ] Đã thử crash/restart theo partition, kiểm tra không thiếu/nhân đôi kết quả.
- [ ] Chỉ chuyển sang remote khi một JVM không đủ và có kế hoạch hạ tầng phục hồi.
- [ ] Đã có runbook để xử lý partition lỗi và đối soát dữ liệu trước khi restart.

## 16. Câu hỏi tự kiểm tra

1. Partitioning Step khác multi-threaded step ở cách lưu `StepExecution` và `ExecutionContext` như thế nào?
2. Với 12 partition, executor có bốn threads và chunk size 500, có thể có bao nhiêu worker partition hoạt động đồng thời trong cấu hình local minh họa?
3. Vì sao `range-00` và `range-01` không được cùng chứa ID `100000`?
4. Khi dữ liệu nguồn liên tục có bản ghi mới, chỉ chia theo `MAX(id)` tính lại mỗi lần restart có rủi ro gì?
5. Cùng một `@StepScope` reader bean có được dùng cho hai partition StepExecution khác nhau dưới dạng chung một cursor không?
6. Khi một partition `FAILED` nhưng ba partition `COMPLETED`, restart cùng JobInstance thường chạy lại những gì? Điều kiện để bỏ qua ba partition kia?
7. Vì sao `gridSize=32` với 8 worker threads có thể vẫn tốt hơn `gridSize=8` trong workload skew? Rủi ro của quá nhiều partition?
8. Remote partitioning khác remote chunking ở việc đọc item diễn ra ở đâu?
9. Có 6 worker cùng writer upsert một bảng DB. Khi throughput không tăng thêm và DB lock wait tăng, nên điều tra gì trước khi tăng worker?
10. Nên dùng những bất biến nào để chứng minh kết quả chạy song song và restart giống kết quả chạy sạch?

**Gợi ý trả lời:** (1) Partitioning có StepExecution và context riêng cho mỗi shard; multi-threaded step thường dùng một StepExecution. (2) Tối đa khoảng bốn worker step đồng thời, không phải 12 hay 2.000 chunk đồng thời. (3) Trùng sẽ đọc/ghi bản ghi hai lần. (4) Mất ổn định phạm vi/checkpoint và có thể bỏ sót dữ liệu. (5) Không, với scope hoạt động đúng, bean reader theo từng StepExecution. (6) Chỉ partition chưa hoàn tất, nếu tên/metadata còn và không bật chính sách chạy lại step đã xong. (7) Shard nhỏ có thể cân bằng tốt hơn nhưng tốn overhead metadata/reader. (8) Worker tự đọc ở remote partitioning, manager đọc ở remote chunking. (9) Row locks, index, transaction và ngân sách DB pool. (10) Coverage, unique key, checksum/tổng tiền và output idempotent sau restart.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): tổng quan partitioning, manager/worker, `Partitioner`, `PartitionHandler` và các mô hình mở rộng.
- [Spring Batch 5.2 Reference — Partitioning](https://docs.spring.io/spring-batch/reference/5.2/scalability.html#partitioning): cách tạo partition và local `TaskExecutorPartitionHandler`.
- [Spring Batch API — `Partitioner`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/Partitioner.html): hợp đồng trả `Map<String, ExecutionContext>`.
- [Spring Batch API — `SimpleStepExecutionSplitter`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/SimpleStepExecutionSplitter.html): chia, khôi phục partition trên cơ sở `JobRepository`.
- [Spring Batch Reference — Step Scope](https://docs.spring.io/spring-batch/reference/step/late-binding.html): late binding và `StepExecutionContext`.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, `ItemStream` và restart.

**Điểm cốt lõi:** Partitioning Step mở rộng một bước dữ liệu bằng cách tạo **nhiều worker StepExecution có phạm vi dữ liệu và checkpoint riêng**. Mấu chốt của tính đúng đắn là chia đủ/không trùng, giữ tên và snapshot ổn định, kiểm soát transaction/idempotency và chỉ tăng concurrency khi downstream còn năng lực. Nhờ vậy có thể mở rộng workload lớn, quan sát từng shard và phục hồi những partition chưa hoàn tất mà không phải chạy lại toàn bộ dữ liệu đã xử lý thành công.
