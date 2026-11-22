# Chunk quá nhỏ làm throughput thấp trong Spring Batch

## 1. Hiện tượng: job xử lý đúng nhưng chạy quá chậm

Giả sử một Spring Batch job cần chuyển một triệu bản ghi đơn hàng từ bảng staging sang bảng kết quả. Reader đọc từng item, processor chuẩn hóa dữ liệu, writer ghi vào database. Job chạy thành công, không có exception, CPU không phải lúc nào cũng cao, nhưng tổng thời gian xử lý kéo dài hàng giờ.

Khi kiểm tra cấu hình, ta thấy:

```java
. <Order, ProcessedOrder>chunk(1, transactionManager)
```

Về mặt cú pháp Java, generic type argument phải được viết liền với dấu chấm:

```java
.<Order, ProcessedOrder>chunk(1, transactionManager)
```

Với **chunk size bằng 1**, mỗi item thường khiến framework đi qua gần như toàn bộ vòng đời một chunk: đọc, xử lý, ghi, cập nhật trạng thái và commit transaction. Nếu job cần xử lý hàng triệu item, chi phí transaction, database round-trip, flush và hạ tầng framework lặp đi lặp lại nhiều lần.

Nhưng **chunk nhỏ không phải luôn sai**. Với bản ghi rất nặng, writer gọi dịch vụ ngoài, yêu cầu độ trễ từng item thấp hoặc cần rollback nhỏ, chunk size 1–10 có thể phù hợp. Vấn đề là dùng một giá trị quá nhỏ **so với workload và chi phí cố định mỗi transaction**, khiến throughput thấp không cần thiết.

Mục tiêu của bài học là nhận diện nguyên nhân, đo đúng chi phí và chọn **commit interval** phù hợp mà không đánh đổi sự ổn định, bộ nhớ và khả năng restart một cách mù quáng.

## 2. Chunk-oriented processing hoạt động như thế nào?

Spring Batch phân biệt *tasklet-oriented step* và *chunk-oriented step*. Trong chunk-oriented step, framework thường đọc các item cho tới khi đủ chunk theo `completion policy`/commit interval, thực hiện xử lý/ghi và commit trong transaction tương ứng.

```text
                Chunk-oriented step
                         |
           Bắt đầu transaction / chunk
                         |
                    ItemReader
                         |
                    ItemProcessor
                         |
             Gom items cho một chunk
                         |
                    ItemWriter
                         |
              ItemStream.update(...)
                         |
             Commit transaction/chunk
                         |
                  Chunk tiếp theo
```

Đây là sơ đồ khái niệm. Thứ tự callback thực tế, listener, retry, skip, buffer và việc cập nhật metadata phụ thuộc cấu hình step. Không nên hiểu mỗi lần gọi `read()` đều lập tức mở/đóng một transaction riêng khi chunk size lớn hơn 1.

Ví dụ step có `chunk(100, transactionManager)`:

```text
Chunk 1: items 1 ... 100    -> write -> commit
Chunk 2: items 101 ... 200  -> write -> commit
Chunk 3: items 201 ... 300  -> write -> commit
...
```

Với cùng 1.000 item và không có retry/skip:

| Chunk size | Số chunk chứa dữ liệu, xấp xỉ | Ý nghĩa |
|---|---:|---|
| 1 | 1.000 | Nhiều transaction nhỏ. |
| 10 | 100 | Giảm đáng kể số commit. |
| 100 | 10 | Writer có cơ hội xử lý một nhóm lớn. |
| 500 | 2 | Ít commit hơn, nhưng tăng kích thước mỗi transaction. |
| 1.000 | 1 | Một chunk rất lớn cho tập dữ liệu này. |

Số chunk có dữ liệu về mặt toán học thường được ước lượng bằng `ceil(totalItems / chunkSize)`. Tuy nhiên **`StepExecution.getCommitCount()` không nhất thiết bằng đúng phép tính này**: chunk cuối, cách phát hiện end-of-stream, rollback/retry và cơ chế framework có thể tạo thêm lần commit hay thay đổi thống kê. Hãy dùng count và trace thực tế để đánh giá, không dùng công thức ước lượng làm assertion cứng cho mọi reader.

## 3. Vì sao chunk quá nhỏ kéo throughput xuống?

### 3.1. Transaction overhead lặp quá thường xuyên

Mỗi chunk có thể kéo theo những việc cố định:

1. Bắt đầu hoặc tham gia transaction do `PlatformTransactionManager` quản lý.
2. Lấy connection từ pool hoặc chuẩn bị transaction context.
3. Thực thi writer, flush, JDBC batch hoặc SQL tương ứng.
4. Cập nhật `ExecutionContext` và metadata step theo lifecycle Batch.
5. Commit transaction; database có thể cần ghi transaction log và đồng bộ durability theo cấu hình.
6. Gọi listener, cập nhật số liệu, giải phóng tài nguyên liên quan.

Khi chunk size là 1, phần overhead này có thể bị lặp lại **mỗi item**. Khi chunk size là 500, một số chi phí được phân bổ cho cả 500 item. Các chi phí không được giảm đều như nhau: processor CPU theo item vẫn phải chạy; câu SQL cũng vẫn phải xử lý tất cả dữ liệu.

### 3.2. Writer không tận dụng được batch I/O

`JdbcBatchItemWriter` hoặc writer hỗ trợ ghi nhiều phần tử cùng lúc có thể gom các lệnh SQL trong một lần thực thi JDBC batch theo `Chunk`. Nếu mỗi chunk chỉ có một item, khả năng gom lệnh bị hạn chế. Tùy driver/database và implementation, chunk lớn hơn có thể giảm round-trip, tăng hiệu quả network và cải thiện throughput.

**Không phải cứ tăng chunk size thì SQL tự được tối ưu.** Nếu writer tự viết `for` rồi gọi một HTTP request riêng cho từng item, số request vẫn có thể giữ nguyên. Nếu writer mở connection mới cho mỗi item, bottleneck thực sự nằm ở implementation. Cần phân biệt:

- Chunk transaction: nhóm item được commit cùng ranh giới transaction.
- JDBC batch: nhóm statement gửi tới database theo API `PreparedStatement.addBatch/executeBatch` hoặc abstraction tương đương.
- Bulk SQL: một statement cập nhật/chèn nhiều row theo cú pháp database.
- Reader fetch/page size: số row được fetch từ nguồn trong một đợt.

Chúng có liên quan nhưng **không phải một tham số duy nhất**.

### 3.3. Tăng overhead của framework và metadata

Nhiều commit thường đi cùng nhiều lượt cập nhật trạng thái `StepExecution`, checkpoint, transaction boundary và callback của listener. Chi phí này đặc biệt rõ nếu `JobRepository` nằm trên database khác có độ trễ mạng đáng kể hoặc dùng transaction manager/connection pool bị giới hạn.

Tuy nhiên, không nên kết luận cứ thấy nhiều dòng log `Executing step` là do commit interval: đây có thể chỉ là log cấp step, còn bottleneck nằm ở SQL hay remote API. Cần đo tại các tầng.

### 3.4. Log và metrics quá chi tiết cũng làm chậm

Nếu `ChunkListener.afterChunk(...)` ghi `INFO` ở mỗi chunk, chunk size bằng 1 sẽ làm log tăng cùng số item. Một triệu item tương đương khoảng một triệu lần gọi listener ở cấp chunk và có thể tạo một triệu dòng tiến độ. Khi appender đồng bộ hoặc stdout/log collector chậm, chi phí logging làm tình hình tệ hơn.

Nên log tổng kết ở `StepExecutionListener`, ghi progress thưa theo mốc và dùng metrics để đo latency/throughput. Tránh bật `DEBUG`/`TRACE` của JDBC hoặc Spring Batch trong thời gian benchmark trừ khi đang điều tra có mục tiêu.

## 4. Mô hình ước lượng đơn giản về throughput

Ta có thể dùng một mô hình gần đúng để hiểu chi phí:

\[
T(N,C) \approx N \cdot t_{item}
  + \left\lceil\frac{N}{C}\right\rceil \cdot t_{fixed}
  + T_{other}
\]

Trong đó:

- `N`: tổng số item cần xử lý.
- `C`: chunk size hay commit interval.
- `t_item`: chi phí trung bình của đọc/xử lý/ghi một item không tính overhead cố định mỗi chunk.
- `t_fixed`: chi phí cố định của một chunk (transaction, commit, callbacks, round-trip...), theo điều kiện đo.
- `T_other`: startup, kết nối, chuẩn bị reader, I/O và các phần chi phí không được mô hình hóa.

Ví dụ giả định **1.000.000 item**, trong môi trường cụ thể mỗi chunk có 3 ms overhead cố định và chi phí item giữ nguyên:

| Chunk size | Chunk có dữ liệu xấp xỉ | Overhead cố định ước lượng |
|---|---:|---:|
| 1 | 1.000.000 | 3.000 giây (50 phút) |
| 10 | 100.000 | 300 giây (5 phút) |
| 100 | 10.000 | 30 giây |
| 500 | 2.000 | 6 giây |
| 1.000 | 1.000 | 3 giây |

Đây là **minh họa toán học**, không phải số benchmark chung cho Spring Batch. Chi phí cố định không luôn giữ nguyên khi tăng chunk size: transaction dài hơn, batch SQL lớn hơn, memory pressure, lock contention hoặc DB log flush có thể khiến `t_fixed` và `t_item` thay đổi. Mô hình cũng không tính concurrency, retry và tác động của dữ liệu không đồng nhất.

Thông lượng có thể đo theo:

\[
\text{Throughput} = \frac{\text{số item được xác nhận theo mục tiêu}}{\text{thời gian chạy thực tế (giây)}}
\]

Khi dùng số đếm của Spring Batch, phải định nghĩa rõ mẫu số và tử số: số item được `read`, được `write`, số row đã commit hay số business record đã hoàn tất. Processor có thể lọc item, writer có thể bulk update, retry có thể phát sinh xử lý lại. **Không dùng một bộ đếm bất kỳ rồi gọi đó là “records per second” nếu ngữ nghĩa không khớp.**

## 5. Dấu hiệu nhận diện chunk quá nhỏ

Một số tín hiệu thường gặp khi commit interval là nguyên nhân chính:

| Tín hiệu | Diễn giải cần kiểm chứng |
|---|---|
| Chunk size nhỏ (1, 5, 10) trên dataset lớn | Có khả năng overhead theo transaction cao. |
| `commitCount` rất lớn so với lượng work thực tế | Có nhiều transaction nhỏ; cần xem end-of-stream/retry. |
| Thời gian commit/JDBC round-trip chiếm tỷ trọng cao | Batch size lớn hơn có thể giảm số lượt commit. |
| DB transaction log/fsync hoạt động dày | Commit thường xuyên có thể là yếu tố gây tải. |
| CPU processor thấp nhưng throughput thấp | Có thể đang chờ DB/network/transaction, không nhất thiết do Java chậm. |
| Writer chạy `executeBatch()` với kích thước 1 | Chưa tận dụng lợi ích JDBC batching. |
| Log mỗi chunk chiếm phần lớn log output | Overhead logging nhân với số chunk. |
| Tăng size từ 10 lên 100 cải thiện rõ nhưng 500 lên 1.000 không cải thiện | Gợi ý đang tiến tới vùng tối ưu, cần đo thêm. |

Tín hiệu **không đủ để kết luận**:

- Job chậm nhưng chunk size đã 500: có thể do truy vấn không có index, API ngoài, lock hay GC.
- CPU 100%: có thể do processor quá nặng và commit interval không phải điểm nghẽn.
- `readCount` cao: chỉ cho biết số item được đọc theo semantics Batch, không cho biết chỗ tốn thời gian.
- DB có nhiều connection: không tự chứng minh chunk nhỏ; có thể do partitioning, nhiều job hay connection leak.

## 6. Cấu hình chunk size trong Spring Batch 5.x

Các ví dụ dưới đây dùng **Java 17+, Spring Boot 3.x, Spring Batch 5.x** và builder API tương ứng. Spring Batch 6.x có thay đổi package/API; cần dùng reference docs khớp dependency của dự án.

### 6.1. Step với commit interval cố định

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersStepConfiguration {

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, ProcessedOrder> orderProcessor,
            ItemWriter<ProcessedOrder> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, ProcessedOrder>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }
}
```

`Order`, `ProcessedOrder` và các bean reader/processor/writer là lớp nghiệp vụ của ứng dụng, không phải thành phần Spring Batch tự sinh. Ở Spring Batch 5.x, `.chunk(500, transactionManager)` xác định commit interval 500 cho step có một transaction manager tương ứng.

Đừng tăng size của job production lên 500 chỉ vì ví dụ này. Nó là **giá trị thử nghiệm ban đầu**, cần benchmark trên workload và database thực tế.

### 6.2. Đưa chunk size ra cấu hình

Trong `application.yml`:

```yaml
app:
  batch:
    import-orders:
      chunk-size: 500
```

Trong cấu hình step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter,
        @Value("${app.batch.import-orders.chunk-size:500}") int chunkSize) {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be positive");
    }

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(chunkSize, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Thêm import `org.springframework.beans.factory.annotation.Value` và các import ở ví dụ trước. Key `app.batch.import-orders.chunk-size` là **property tự định nghĩa của ứng dụng**, không phải thuộc tính Spring Batch tự nhận. Việc cấu hình ngoài code giúp thử các giá trị theo profile test, nhưng cần lưu lại giá trị được dùng cho mỗi execution để có thể tái hiện benchmark và quản lý thay đổi.

Với ứng dụng yêu cầu chunk size khác nhau theo từng job execution, có thể tạo cấu hình step-scope hoặc xây dựng completion policy có kiểm soát; tuy nhiên không nên tùy tiện thay completion policy giữa lúc một `StepExecution` đang chạy. Khi restart, phải hiểu sự thay đổi ảnh hưởng tới checkpoint, memory và thời gian xử lý thế nào.

### 6.3. Chunk size không phải page size, fetch size hay grid size

```text
chunkSize              = số item được gom vào transaction/chunk
JdbcCursor.fetchSize   = gợi ý số row JDBC driver fetch mỗi lượt
JdbcPaging.pageSize    = kích thước trang query ở reader phân trang
partition grid size    = cách chia dữ liệu cho worker/partition
thread pool size       = số luồng chạy song song
```

Ví dụ `JdbcPagingItemReader` có `pageSize=1.000` và step có `chunkSize=250`: một trang đọc có thể phục vụ nhiều chunk. Đây là cấu hình hợp lệ nếu reader, sort key và transaction được thiết kế phù hợp. Việc tăng một tham số không tự thay đổi các tham số còn lại.

## 7. Writer JDBC: chunk lớn chỉ hữu ích khi tận dụng batch I/O

Nếu writer phải ghi hàng triệu dòng vào database, một implementation hỗ trợ JDBC batch thường là điểm khởi đầu tốt. Spring Batch có `JdbcBatchItemWriter` để gom một `Chunk` item vào các thao tác JDBC batch.

Ví dụ với một record ứng dụng:

```java
import java.math.BigDecimal;

public record ProcessedOrder(long id, BigDecimal amount) {
}
```

Và writer:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.context.annotation.Bean;

@Bean
JdbcBatchItemWriter<ProcessedOrder> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order (id, amount)
                VALUES (:id, :amount)
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("id", item.id())
                            .addValue("amount", item.amount()))
            .build();
}
```

Lý do dùng `itemSqlParameterSourceProvider`: `ProcessedOrder` là Java record với accessor `id()`/`amount()`, nên ta ánh xạ tham số SQL một cách tường minh, không phụ thuộc tên getter theo JavaBeans. Với JDBC driver/database mục tiêu, cần quan sát **batch size và thời gian thực thi thực tế**, vì việc framework gọi JDBC batch không bảo đảm database biến tất cả lệnh thành một thao tác mạng duy nhất.

Đặt ví dụ DDL phục vụ test:

```sql
CREATE TABLE imported_order (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(14, 2) NOT NULL
);
```

Khi so sánh `chunkSize=10` với `chunkSize=500`, cần giữ cùng reader, writer, index, database server, mức đồng thời và bộ dữ liệu đầu vào. Nếu cùng lúc thêm JDBC batch, index mới hoặc tăng connection pool, ta không thể kết luận mức cải thiện đến từ commit interval.

### 7.1. Khi writer vẫn gọi API từng item

Một writer tự lặp qua `Chunk` và gọi HTTP cho từng item:

```java
@Override
public void write(Chunk<? extends ProcessedOrder> chunk) {
    for (ProcessedOrder item : chunk) {
        externalApi.sendOrder(item);
    }
}
```

Đoạn code là ví dụ về **một writer có thể bị giới hạn bởi số request**; `externalApi` là dependency ứng dụng. Tăng chunk size không làm số HTTP request giảm nếu vẫn có một call cho mỗi item. Đồng thời, các call HTTP không tự rollback khi database transaction rollback. Đối với loại writer này, cần xem batching do API hỗ trợ, timeout, rate limit, idempotency và phương án outbox. Không tăng chunk size vô hạn để kỳ vọng API sẽ tự nhanh hơn.

## 8. Đo throughput và transaction overhead đúng cách

### 8.1. Thu thập baseline trước khi thay đổi

Trước khi tuning, cần ghi lại tối thiểu:

| Chỉ số | Cách sử dụng |
|---|---|
| Tổng elapsed time của job và từng step | Xác định step nào cần tối ưu. |
| `readCount`, `writeCount`, `filterCount`, `skipCount` | Kiểm tra khối lượng work và số liệu trước/sau. |
| `commitCount`, `rollbackCount` | Quan sát số lần transaction/chunk và lỗi/retry. |
| Throughput theo item/s hoặc row commit/s | So sánh các cấu hình có cùng semantics. |
| CPU/heap/GC của JVM | Phát hiện processor CPU-bound hoặc memory pressure. |
| Connection pool metrics | Xem thời gian đợi connection và saturation. |
| SQL query latency/batch execution time | Đánh giá DB/driver có đang là bottleneck. |
| Database locks/log I/O/wait events | Nhận diện commit và transaction contention. |
| Log volume và listener latency | Xác định overhead observability. |

Spring Batch có `StepExecution` để đọc các thống kê sau khi chạy. Khi đã có `JobExecution`, có thể tổng hợp:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

for (StepExecution step : jobExecution.getStepExecutions()) {
    System.out.printf(
            "step=%s read=%d written=%d commits=%d rollbacks=%d status=%s%n",
            step.getStepName(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getCommitCount(),
            step.getRollbackCount(),
            step.getStatus());
}
```

Chỉ nên in tổng kết này **sau khi có trạng thái cuối** và khi code có quyền truy cập metadata. Nếu `JobLauncher` chạy bất đồng bộ, `JobExecution` được trả về có thể chưa hoàn tất; cần theo dõi tới trạng thái kết thúc hoặc đọc lại qua `JobExplorer`.

### 8.2. Ghi duration theo chunk có giới hạn

Với Spring Batch 5.x, `ChunkListener` giúp quan sát callback quanh chunk. Một cách đo thô trong môi trường thử nghiệm là lưu thời điểm bắt đầu bằng `System.nanoTime()` và tính chênh lệch khi `afterChunk` hoặc `afterChunkError` được gọi.

```java
import java.util.concurrent.atomic.LongAdder;

import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public final class ChunkTimingListener implements ChunkListener {

    private static final String START_KEY = "chunkStartNanos";

    private final LongAdder successfulChunkCount = new LongAdder();
    private final LongAdder totalSuccessfulNanos = new LongAdder();

    @Override
    public void beforeChunk(ChunkContext context) {
        context.setAttribute(START_KEY, System.nanoTime());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        Object started = context.getAttribute(START_KEY);
        if (started instanceof Long startNanos) {
            long elapsed = System.nanoTime() - startNanos;
            successfulChunkCount.increment();
            totalSuccessfulNanos.add(elapsed);
        }
    }

    public long getSuccessfulChunkCount() {
        return successfulChunkCount.sum();
    }

    public long getTotalSuccessfulNanos() {
        return totalSuccessfulNanos.sum();
    }
}
```

Đây là **đo lường minh họa**: biến đếm thuộc instance listener; nếu bean singleton được nhiều step/job dùng chung, các số đo bị gộp. Trong sản phẩm thật nên tách metrics theo tên step hoặc phạm vi execution, sử dụng Micrometer/Observation và tránh lưu state không có giới hạn. `ChunkContext` là thuộc tính của callback chunk; cách lưu/đọc key trên phục vụ một đường chạy bình thường, không phải cơ chế checkpoint bền vững.

Thời gian đo từ `beforeChunk` đến `afterChunk` có thể bao gồm nhiều thành phần của chunk lifecycle, **không phải riêng thời gian database commit**. Để định lượng chi phí commit, cần instrumentation/DB metrics riêng hoặc tracing cho transaction manager. Nếu tăng chunk size mà chunk duration tăng, chưa chắc throughput giảm: mỗi chunk có thể đang chứa nhiều item hơn.

### 8.3. Dùng Micrometer/Actuator thay cho log mọi chunk

Spring Batch hỗ trợ metrics với Micrometer, gồm thời gian job, step, đọc/xử lý item và ghi chunk. Khi ứng dụng Spring Boot đã cấu hình Actuator và registry phù hợp, có thể theo dõi latency qua dashboard để so sánh các size mà không phát hàng triệu dòng `INFO`.

Giữ tag của metrics ở phạm vi hữu hạn (`jobName`, `stepName`, trạng thái...). **Không đặt `orderId`, `jobExecutionId` hay file path tùy ý vào mọi metric tag**, vì cardinality lớn có thể làm backend metrics quá tải. Execution ID phù hợp với log/trace khi cần điều tra một lần chạy riêng.

## 9. Benchmark chunk size theo một kế hoạch kiểm soát

Một quy trình thử nghiệm phù hợp hơn việc chỉ tăng từ 1 lên 10.000:

1. Chọn bộ input đại diện: đủ lớn, có tỷ lệ item hợp lệ/bị filter, kích thước record và phân bố dữ liệu gần production.
2. Giữ cố định database engine, schema/index, JVM memory, CPU quota, connection pool, reader/writer và mức đồng thời.
3. Chạy warm-up nếu có JIT, connection pool hoặc cache ảnh hưởng đáng kể; không dùng kết quả warm-up làm số chính.
4. Thử các size hợp lý như `10`, `50`, `100`, `250`, `500`, `1.000` thay vì chỉ hai giá trị quá xa nhau.
5. Chạy nhiều lượt cho mỗi size, reset dữ liệu/metadata đúng cách và đảo thứ tự thử để giảm sai lệch do cache hoặc tải nền.
6. Đo elapsed time, throughput, p95/p99 chunk duration, heap/GC, số commit, rollback, DB waits và errors.
7. Chọn **vùng hiệu năng ổn định** thay vì chỉ giá trị có thời gian nhanh nhất trong một lượt đo.
8. Kiểm tra lại dưới tải gần production với concurrency và dữ liệu lỗi, sau đó mới thay đổi cấu hình triển khai.

Ví dụ bảng kết quả **giả định**, không phải kết quả benchmark thực tế:

| Chunk size | Throughput (items/s) | Throughput tương đối | Ghi nhận |
|---|---:|---:|---|
| 1 | 230 | 1,0× | Commit overhead lớn. |
| 10 | 1.500 | 6,5× | Cải thiện nhanh. |
| 100 | 4.700 | 20,4× | Writer bắt đầu tận dụng batch. |
| 250 | 5.100 | 22,2× | Gần điểm bão hòa. |
| 500 | 5.250 | 22,8× | Cải thiện nhẹ, transaction lớn hơn. |
| 1.000 | 5.200 | 22,6× | Không có lợi ích thêm, tốn heap hơn. |

Trong bộ số giả định này, `250` hoặc `500` có thể là ứng viên tốt để kiểm tra tiếp. Không kết luận `500` luôn tốt nhất: có thể `250` ổn định hơn khi gặp lỗi dữ liệu hoặc nhiều job chạy song song.

### 9.1. Đừng benchmark trên dữ liệu ít hơn chunk size

Nếu test có 50 item nhưng chunk size là 500, tất cả chỉ chạy trong một chunk. Bạn chưa đo được tác động của nhiều lần commit, tương tác với GC hoặc DB transaction log. Cần bộ dữ liệu đủ lớn để có **nhiều chunk** ở từng giá trị được thử và đủ thời gian chạy để giảm nhiễu đo.

### 9.2. Đừng benchmark với log DEBUG per-item đang bật

Khi một cấu hình phát log mỗi item còn cấu hình khác không phát, kết quả phản ánh cả chi phí logger/appender, không chỉ overhead commit. Đặt logging level nhất quán và chỉ dùng log/timing bổ sung khi cần quan sát bottleneck; sau đó đo lại trong cấu hình gần production.

## 10. Các trade-off khi tăng chunk size

### 10.1. RAM và độ lớn của một chunk

Spring Batch có thể giữ một nhóm input/output items trong bộ nhớ trong quá trình xử lý. Với item lớn, `chunkSize=5.000` có thể gây memory pressure, tăng tần suất GC hoặc OutOfMemoryError. Kích thước object thật thường lớn hơn dung lượng file/row thô vì object headers, strings, collections, buffer và intermediate representations.

Ví dụ **ước lượng đơn giản**: nếu tập object sống trung bình mỗi item trong chunk chiếm khoảng 10 KiB, thì chunk 1.000 item có thể cần ít nhất khoảng 10 MiB cho payload đó, **chưa tính** reader buffers, output objects, retry state, connection pool, JVM và các luồng khác. Đây không phải công thức cấp phát bộ nhớ chính xác; hãy đo heap thực tế.

### 10.2. Transaction kéo dài, lock và contention

Chunk lớn làm transaction dài hơn. Database có thể giữ row locks lâu hơn, làm các job/service khác phải chờ, tăng xác suất deadlock hay timeout. Với hệ thống có nhiều writer cạnh tranh cùng bảng, hiệu năng tổng có thể xấu đi dù một job đơn lẻ nhanh hơn trên môi trường test.

Nên đo lock waits, deadlocks, thời gian transaction và độ trễ dịch vụ cùng chia sẻ database, không chỉ items/s của một step riêng lẻ.

### 10.3. Rollback và retry mất nhiều công hơn

Khi một chunk 1.000 item bị rollback do lỗi ở cuối, logic đọc/xử lý/ghi của nhiều item có thể phải chạy lại. Với chunk 10, phạm vi work phải replay nhỏ hơn. Fault-tolerant step có thể retry/skip theo cấu hình, nên số lần gọi processor/writer và tác động bên ngoài không đơn giản bằng phép nhân với chunk size.

Một writer gọi dịch vụ ngoài mà không có idempotency còn đặc biệt nguy hiểm: HTTP request đã thành công **không tự rollback** cùng database transaction. Đừng tăng chunk size lớn khi chưa hiểu rõ ranh giới transaction và duplicate side effects.

### 10.4. Checkpoint thưa hơn và restart

`ItemStream` có thể cập nhật checkpoint trong `ExecutionContext` theo transaction/chunk. Chunk lớn khiến khoảng cách giữa những điểm commit thường xa hơn. Nếu process bị kill giữa chunk, phần work chưa commit có thể cần xử lý lại khi restart, và các side effects không transactional phải được kiểm soát.

**Tăng chunk size không được làm mất tính restartable của reader/writer.** Cần giữ input bất biến, ổn định sort key khi paging, và sử dụng `saveState`/stream registration đúng theo implementation.

### 10.5. Latency của từng item

Với batch import qua đêm, throughput tổng thường quan trọng hơn việc từng item xuất hiện ở bảng đích ngay lập tức. Nhưng nếu ứng dụng có yêu cầu dữ liệu phải có trong vài giây, chunk lớn có thể làm tăng thời gian chờ tới commit. Cân nhắc SLA về **end-to-end latency** thay vì chỉ throughput.

### 10.6. Một số writer giới hạn batch size

Database driver, API hoặc hệ thống đích có thể giới hạn số parameters/batch rows, kích thước request, transaction log hoặc payload. Ví dụ, một bulk API chỉ nhận tối đa 200 bản ghi mỗi request. Khi đó, tăng chunk size lên 1.000 không có nghĩa được gửi một request 1.000 bản ghi; writer có thể phải chia ra. Chunk size và remote batch size cần được thiết kế riêng, có kiểm soát rollback/retry.

## 11. Điều chỉnh cả reader, processor và writer

Chunk size chỉ là **một núm chỉnh** trong pipeline. Khi đã giảm overhead transaction, bottleneck tiếp theo có thể chuyển sang thành phần khác.

### 11.1. Reader JDBC cursor

`JdbcCursorItemReader` đọc row từ cursor JDBC. Thuộc tính `fetchSize` có thể giúp driver tối ưu số row fetch mỗi lượt. Nó là một **hint cho JDBC driver**, không bảo đảm số row mỗi network round-trip giống nhau giữa mọi database.

```java
JdbcCursorItemReader<Order> reader = new JdbcCursorItemReader<>();
reader.setDataSource(dataSource);
reader.setSql("SELECT id, amount FROM staging_order ORDER BY id");
reader.setFetchSize(500);
reader.setRowMapper(orderRowMapper);
reader.setName("stagingOrderCursor");
reader.setSaveState(true);
```

Đây là cấu hình minh họa, giả định `dataSource` và `orderRowMapper` đã tồn tại. Fetch size cần được điều chỉnh theo driver. Với một số DB, cấu hình autocommit hoặc connection behavior cũng ảnh hưởng đến streaming cursor.

### 11.2. Reader phân trang

`JdbcPagingItemReader` dùng `pageSize` và sort key để phân trang. Sort key phải **duy nhất, ổn định** nếu muốn tránh bỏ sót/trùng lặp khi đọc nhiều trang, đặc biệt khi dữ liệu nguồn có thể bị cập nhật. Page size 1.000 không bắt buộc chunk size cũng bằng 1.000.

### 11.3. Processor CPU-bound

Nếu processor tính toán, parse XML hoặc mã hóa nặng, thời gian CPU trên mỗi item có thể chiếm gần hết. Khi đó tăng chunk size chỉ giảm một phần nhỏ transaction overhead. Profile CPU để tìm hot methods, allocation và serialization; tối ưu thuật toán hoặc dùng concurrency có kiểm soát nếu reader/writer thread-safe.

### 11.4. Writer và index/SQL

Kiểm tra:

- Writer có dùng JDBC batching hay vẫn `executeUpdate` riêng từng item?
- Có index hỗ trợ câu truy vấn reader và constraint cần thiết ở bảng đích không?
- Có trigger quá nặng, foreign key validation hoặc unique check trở thành bottleneck không?
- Driver có thực sự gửi batch hiệu quả không? Một số database hỗ trợ tùy chọn driver để rewrite batches.
- Có đang mở connection/transaction riêng trong mỗi item dù step đã quản lý transaction không?
- Database có bị cạnh tranh với các service khác hoặc thiếu tài nguyên I/O không?

Đừng loại bỏ constraint/index bảo vệ tính đúng đắn chỉ để benchmark đẹp hơn. Nếu cần tối ưu bulk load, hãy thiết kế một phương án staging/load/merge có kiểm soát và đo tính đúng đắn lẫn hiệu năng.

## 12. Chunk size, concurrency và partitioning

Tăng `chunkSize` và tăng số worker/threads là **hai phép tối ưu khác nhau**:

| Biện pháp | Tác động chính | Rủi ro |
|---|---|---|
| Tăng chunk size | Giảm số transaction/commit, tăng lượng work mỗi chunk | Heap, lock duration, rollback/restart work. |
| Multi-threaded step | Nhiều chunk có thể xử lý đồng thời | Reader/writer không thread-safe, cạnh tranh connection, thứ tự xử lý. |
| Partitioning | Chia dataset thành các phân vùng xử lý độc lập | Phân vùng trùng/thiếu, tổng hợp kết quả, quản lý state. |
| Remote chunking | Phân phối xử lý/ghi qua messaging | Network, delivery semantics, duplicate, vận hành nhiều thành phần. |

Khi chạy song song, tổng số connection và transaction active tăng. Nếu chunk size cũng lớn, lock contention và memory có thể tăng nhanh. Không tự nâng `chunkSize`, `gridSize` và thread pool cùng lúc rồi kết luận nguyên nhân cải thiện hoặc suy giảm.

Một thiết kế dễ đo là tối ưu chunk size trên một worker ở mức đồng thời cố định, sau đó thay đổi concurrency ở một vòng benchmark riêng, kiểm tra tính nhất quán, hiệu năng DB và khả năng restart.

## 13. Ảnh hưởng của skip, retry và fault tolerance

Chunk nhỏ có thể làm nhiều transaction hơn, nhưng chunk quá lớn có thể trở nên đắt khi dữ liệu có lỗi.

Ví dụ có 100.000 item, 1% item có lỗi được skip hợp lệ. Tùy điểm lỗi và cấu hình `.faultTolerant().skip(...)`, framework có thể cần rollback và thử lại, hoặc chia/định vị item lỗi. Không thể lấy `ceil(100000 / chunkSize)` làm số commit thực tế nếu có retry/skip.

Những điều cần đo riêng:

| Tình huống | Vì sao ảnh hưởng tối ưu? |
|---|---|
| `skipCount` cao | Work lại và listener callback nhiều có thể làm chunk lớn đắt hơn. |
| `rollbackCount` cao | Reprocessing và DB contention che lợi ích giảm commits. |
| Retry backoff dài | Bottleneck là chờ lỗi tạm thời, không phải commit interval. |
| Processor có side effect | Retry có thể gọi lại processor; cần thiết kế idempotent. |
| Writer không transaction-safe | Rollback không đảo ngược các call HTTP/file đã thành công. |

Với dataset có lỗi, hãy benchmark ít nhất hai bộ: một bộ sạch và một bộ phản ánh tỷ lệ lỗi thực tế. Một giá trị nhanh trên dữ liệu hoàn hảo có thể rất kém ổn định khi gặp lỗi ngẫu nhiên hoặc deadlock.

### 13.1. Skip limit không phải công cụ tăng throughput

Việc nâng `skipLimit` chỉ để job khỏi fail khi thử chunk lớn có thể che giấu lỗi dữ liệu nghiêm trọng. Tương tự, giảm retry/backoff để tăng throughput có thể làm tăng thất bại thực tế và gây áp lực lên dịch vụ ngoài. Tối ưu commit interval không được thay đổi ý nghĩa nghiệp vụ của việc chấp nhận/từ chối bản ghi.

## 14. Kiểm thử và xác nhận tính đúng đắn khi đổi chunk size

Một thay đổi cấu hình commit interval vẫn phải giữ kết quả nghiệp vụ và khả năng restart.

### 14.1. Integration test với cùng input

Với Spring Boot 3.x và Spring Batch 5.x, có thể dùng `@SpringBatchTest`, `@SpringBootTest`, `@ActiveProfiles("test")`, `JobLauncherTestUtils` và JDBC `JobRepository` riêng cho test.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest(properties = "app.batch.import-orders.chunk-size=100")
@ActiveProfiles("test")
class ImportOrdersChunkIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importOrdersJob")
    Job importOrdersJob;

    @BeforeEach
    void setUp() {
        repositoryTestUtils.removeJobExecutions();
        launcherTestUtils.setJob(importOrdersJob);
        jdbcTemplate.update("DELETE FROM imported_order");
        // Nạp bộ fixture staging_order cố định ở đây, ví dụ bằng @Sql.
    }

    @Test
    void completesAndWritesExpectedRows() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputId", "chunk-benchmark-fixture-1")
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        Integer actual = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM imported_order", Integer.class);
        assertEquals(1000, actual);
    }
}
```

Đây là **khung integration test minh họa**: giả định ứng dụng có bean `Job` tên `importOrdersJob`, cấu hình Batch phù hợp, bảng test, fixture gồm 1.000 bản ghi và transaction manager đúng. `@SpringBootTest` không tự sinh những thành phần nghiệp vụ này. Khi triển khai, nạp fixture tường minh bằng `@Sql` hoặc test-data factory; cleanup trong `@BeforeEach` chỉ phù hợp với database test riêng, không dùng trên môi trường chia sẻ.

`JobRepositoryTestUtils.removeJobExecutions()` xóa metadata trong repository được nó dùng; không gọi khi test khác đang chạy song song trên cùng repository. `spring.batch.job.enabled=false` nên đặt trong profile test để job không tự chạy lúc context startup.

### 14.2. So sánh nhiều size bằng test/benchmark riêng

Để đo `10`, `100`, `500`, mỗi giá trị có thể là một profile/test context cấu hình tương ứng, hoặc một benchmark harness tạo step theo size đang thử. Đảm bảo:

- Input/expected output y hệt.
- Dữ liệu đích được reset trước mỗi lượt đo.
- Metadata mới/JobParameters riêng để tránh `JobInstanceAlreadyCompleteException`.
- Warm-up và các vòng đo đủ ổn định, không đo trên một test chỉ có vài item.
- Không dùng `@Transactional` bao toàn bộ test launch job với giả định mọi commit của step sẽ rollback theo test method.
- Kiểm tra dữ liệu, status và counts trước khi tin kết quả throughput.

### 14.3. Test rollback và restart khi chunk lớn

Một bài test quan trọng: cố ý gây lỗi ở giữa một chunk, giữ nguyên `JobRepository`/`ExecutionContext`, rồi chạy lại bằng cùng **identifying JobParameters**. Kiểm tra:

1. Các chunk đã commit trước lỗi không bị ghi trùng.
2. Chunk đang rollback được replay theo cách an toàn.
3. Các input/output streams khôi phục checkpoint đúng.
4. Không có side effect ngoài transaction bị thực hiện hai lần trái phép.
5. Job cuối cùng đạt trạng thái đúng và dữ liệu được đối soát.

Nếu đổi chunk size làm test restart thất bại, không nên bỏ kiểm thử này chỉ để giữ throughput cao; cần hiểu nguyên nhân ở reader/writer hoặc thiết kế transaction.

## 15. Các cách tối ưu thường gây hiểu lầm

### 15.1. “Càng lớn càng nhanh”

Sai vì lợi ích giảm overhead có thể bão hòa, trong khi heap, lock duration, rollback cost và thời gian chờ commit tăng. Khi từ `500` lên `1.000` chỉ cải thiện rất ít hoặc bắt đầu giảm throughput, cần đánh giá vùng tối ưu thay vì tiếp tục tăng theo cấp số nhân.

### 15.2. “Chunk size lớn nghĩa là ít SQL statement hơn”

Không nhất thiết. Writer có thể vẫn phát một SQL statement mỗi item. JDBC batch có thể giảm round-trip, nhưng số thao tác được database xử lý vẫn phụ thuộc driver và SQL. Đo batch execution và network thực tế.

### 15.3. “Chỉ cần tăng connection pool”

Nếu job chạy một step tuần tự với một connection mỗi transaction, tăng pool từ 10 lên 100 không tự làm nhiều chunk chạy song song. Pool sizing cần dựa trên concurrency thực tế và workload tổng, không dùng để thay cho tối ưu commit interval.

### 15.4. “Commit ít hơn nghĩa là chắc chắn giảm thời gian database”

Giảm số commit có thể tiết kiệm overhead nhưng các transaction lớn cũng có thể làm DB buffer/log và locking đắt hơn. Nếu bottleneck là query không có index hoặc chờ lock, thay commit interval có thể không hiệu quả.

### 15.5. “Đọc nhanh là job nhanh”

Reader có thể đọc 100.000 item/s trong khi writer chỉ ghi 500 item/s do API rate limit. Tăng fetch size hoặc chunk size ở reader không loại bỏ giới hạn của writer. Cần phân tích thời gian cho từng công đoạn.

### 15.6. “Throughput tăng là thay đổi đã đúng”

Job có thể chạy nhanh hơn nhưng commit sai số liệu, không khôi phục được sau crash, bỏ qua item lỗi hoặc tăng lock khiến hệ thống khác chậm. Tiêu chí chọn size gồm **tính đúng đắn, throughput, độ ổn định và yêu cầu vận hành**, không phải một con số duy nhất.

## 16. Bảng chẩn đoán sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `commitCount` rất lớn, chunk size bằng 1 | Mỗi item nằm trong transaction riêng | Thử size 50/100/500 và đo DB/throughput. |
| `writeCount` cao nhưng throughput thấp | Writer nhiều round-trip hoặc DB wait | Xem `JdbcBatchItemWriter`, SQL và driver batching. |
| Chunk size 500 nhưng mỗi writer vẫn gửi một HTTP request/item | Không có bulk API hoặc writer không batch | Thiết kế batch request/outbox/idempotency riêng. |
| Tăng từ 100 lên 1.000 nhưng không nhanh hơn | Đã đạt vùng bão hòa hoặc bottleneck khác | Profile processor, SQL, network, locks. |
| Chunk lớn làm heap tăng và GC dài | Tập item/intermediate state lớn trong memory | Giảm size, giảm object allocations, theo dõi heap/GC. |
| Chunk lớn gây deadlock hoặc timeout | Transaction giữ lock lâu hơn | Giảm size, tối ưu thứ tự cập nhật/index, đo contention. |
| Job lỗi rồi restart phải xử lý lại nhiều item | Điểm commit/checkpoint quá thưa | Chọn size vừa đủ, giữ reader/writer restartable. |
| Log rất nhiều dòng `afterChunk` | Listener ghi tiến độ mỗi chunk | Ghi theo mốc hoặc dùng Micrometer. |
| `readCount` khác `writeCount` | Processor filter hoặc skip | Xem `filterCount`, skip counts, logic nghiệp vụ. |
| Benchmark 50 item cho chunk size 1.000 báo rất nhanh | Không có nhiều chunk, dữ liệu quá nhỏ | Dùng dataset lớn, đo nhiều lượt và warm-up. |
| Kết quả thay đổi khi retry/skip bật | Rollback/reprocessing ảnh hưởng work | Test dữ liệu lỗi đại diện, đo rollback/skip/retry. |
| Nhiều partitions chạy chậm hơn một worker | DB/network saturation và lock | Điều chỉnh concurrency, không tăng tất cả thông số cùng lúc. |
| Thay size không có tác dụng | Step không dùng property, bean được cache hoặc writer là bottleneck | Xác minh cấu hình thực sự được nạp và đo đúng công đoạn. |
| Job bị `JobInstanceAlreadyCompleteException` khi benchmark lại | Dùng cùng identifying parameters trên repository cũ | Dùng repository test riêng/reset metadata hoặc instance hợp lệ mới. |

## 17. Quy trình tối ưu thực tế cho một job lớn

Khi nhận được báo cáo “job chạy chậm do chunk size quá nhỏ”, một runbook hợp lý gồm:

1. **Xác nhận phạm vi:** job/step nào chậm, bao nhiêu item, môi trường nào, SLA là gì?
2. **Đọc cấu hình:** chunk size thực tế, transaction manager, reader fetch/page size, writer implementation và retry/skip policy.
3. **Chụp baseline:** elapsed time, throughput, commit/rollback counts, memory/GC và DB waits.
4. **Xác định bottleneck chính:** transaction overhead, network/SQL, reader, processor CPU hay external service.
5. **Thử size tăng dần:** chọn các mốc hợp lý, giữ các biến khác cố định và reset dữ liệu test.
6. **Đo dưới dữ liệu thật đại diện:** có cả item lớn, dữ liệu xấu, retry/skip và mức đồng thời gần production.
7. **Kiểm tra correctness:** output count, giá trị, constraint, transaction, idempotency và restart.
8. **Chọn vùng cân bằng:** throughput tốt nhưng transaction không quá dài, heap/DB lock trong giới hạn.
9. **Triển khai có kiểm soát:** ghi lại chunk size được chọn, thời điểm/phiên bản và khả năng rollback cấu hình.
10. **Theo dõi sau triển khai:** job duration, p95/p99, error rate, lock/GC, queue backlog và tác động lên workload khác.

### Bài tập 1 — Mô hình overhead

Giả sử `N=2.000.000`, chi phí cố định 4 ms mỗi chunk, item cost giữ nguyên. Tính chi phí cố định ước lượng cho chunk size 1, 20, 200 và 1.000. Nêu rõ vì sao phép tính này không thay thế benchmark khi size lớn làm transaction dài hơn.

### Bài tập 2 — Đo commit interval

Tạo chunk-oriented step đọc 100.000 records từ bảng staging và ghi vào bảng đích qua `JdbcBatchItemWriter`. Thử size 10, 100, 500, 1.000 trên cùng input. Ghi `readCount`, `writeCount`, `commitCount`, elapsed time, heap và DB round-trip. Giải thích size nào cho vùng throughput tốt nhất trên máy thử và vì sao.

### Bài tập 3 — Gây lỗi giữa chunk

Với chunk size 500, tạo lỗi ghi dữ liệu ở gần cuối chunk thứ ba, rồi restart bằng cùng identifying parameters. Kiểm tra kết quả đã commit và dữ liệu được replay. So sánh số item phải xử lý lại với chunk size 50, không bỏ qua yêu cầu idempotency.

### Bài tập 4 — Phát hiện bottleneck giả

Tạo hai writer: writer A dùng JDBC batch, writer B gọi HTTP một lần mỗi item. Thử tăng chunk size từ 10 lên 500. Quan sát rằng lợi ích có thể khác rất lớn; thiết kế kế hoạch đo để không nhầm chunk tuning với API/network bottleneck.

### Bài tập 5 — Tuning khi chạy song song

Cho hai partition độc lập cùng ghi vào một bảng database, kiểm tra contention khi thay chunk size và số workers. Đo throughput toàn hệ thống và lock waits, không chỉ thời gian một partition. Đề xuất giới hạn an toàn cho đồng thời và commit interval.

## 18. Nguyên tắc ghi nhớ

- **Chunk size quá nhỏ** thường làm lặp transaction/commit, metadata và writer I/O quá nhiều lần trên job lớn.
- **Tăng chunk size có thể cải thiện throughput**, đặc biệt khi writer hỗ trợ JDBC batch hoặc bulk I/O; mức cải thiện phụ thuộc workload.
- **Chunk size không đồng nghĩa fetch size, page size, SQL batch size hay concurrency.** Cần đo đúng thành phần gây nghẽn.
- **Không có một con số tối ưu chung** cho mọi Spring Batch job. Hãy benchmark trên bộ dữ liệu và database đại diện.
- **Đừng tối ưu bằng cách hy sinh restart và tính đúng đắn.** Transaction dài hơn làm tăng rollback/retry cost, memory và lock duration.
- **Theo dõi cả tổng thể:** CPU, GC, DB waits, commit count, throughput và kết quả nghiệp vụ; không kết luận từ một log duy nhất.
- **Chọn một vùng giá trị ổn định**, có thể vận hành và tái kiểm thử, thay vì đơn thuần chọn giá trị size lớn nhất.

## 19. Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): cơ chế đọc, xử lý, ghi theo chunk và commit interval.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html): cấu hình commit interval cho step.
- [Spring Batch Reference — JDBC Batch Item Writer](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): các thành phần database reader/writer và JDBC batch.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, start limit và `allowStartIfComplete`.
- [Spring Batch Reference — Fault Tolerance](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): skip/retry policy và ảnh hưởng tới giao dịch chunk.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): metrics/timing của job, step, item và chunk.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundary và propagation.

