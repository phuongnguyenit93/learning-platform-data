# Local chunking trong một JVM với Spring Batch

Một job đọc file CSV, làm sạch dữ liệu, rồi ghi hàng triệu bản ghi vào PostgreSQL có thể được triển khai bằng **một ứng dụng Spring Batch chạy trên một JVM**. Toàn bộ thao tác đọc, xử lý, ghi và điều khiển chunk nằm trong cùng tiến trình; chỉ các hệ thống dữ liệu mà ứng dụng truy cập (file, database, API) là các tài nguyên bên ngoài. Đây là mô hình **local chunking** thường gặp khi bắt đầu xây dựng batch pipeline.

Local chunking có thể vận hành rất tốt nếu dùng đúng ranh giới transaction, chunk size và cơ chế restart. Khi dữ liệu tăng, có thể thêm concurrency trong JVM bằng multi-threaded step, parallel steps hoặc local partitioning. Tuy nhiên, chuyển sang xử lý đồng thời không làm mất các giới hạn I/O, CPU và tính an toàn của state.

Bài học thuộc chương **Mô hình đồng thời** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload lớn thông qua multi-threaded step, parallel steps, partitioning và xử lý phân tán; đồng thời học cách đo nút thắt, bảo đảm thread safety, retry/restart và lựa chọn kiến trúc theo tài nguyên thực tế. Trọng tâm ở đây là hiểu **local chunking trong một JVM** và giới hạn mà mô hình này giải quyết được trước khi tăng độ phức tạp hệ thống.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả vòng đời chunk-oriented step chạy tại chỗ trong một JVM.
2. Phân biệt local chunking tuần tự, multi-threaded step và local partitioning.
3. Hiểu ranh giới commit/rollback, checkpoint và vai trò của `JobRepository`.
4. Viết cấu hình Spring Batch 5.x đơn giản có `ItemReader`, `ItemProcessor`, `ItemWriter`, `Job` và `Step`.
5. Lựa chọn `chunk size`, cách ghi batch và tài nguyên database theo số đo.
6. Đánh giá thread safety và restartability trước khi tăng số luồng.
7. Xác định khi nào local chunking đủ đáp ứng SLA và khi nào nên mở rộng sang các mô hình khác.

## 2. Local chunking là gì?

**Local** ở đây mô tả *nơi chạy các thành phần Spring Batch*: reader, processor, writer và logic step chạy trong cùng tiến trình JVM. **Chunking** là cách chia dòng dữ liệu thành những nhóm nhỏ để xử lý và commit theo từng nhóm, thay vì đợi toàn bộ dataset hoàn tất mới commit.

Local chunking là mô tả **kiến trúc triển khai**, không phải một kiểu `Step` hoặc API độc lập có tên `LocalChunkingStep`. Spring Batch dùng **chunk-oriented processing** và các builder như `StepBuilder`. Thông thường một chunk-oriented step thực thi tuần tự theo một luồng khi không cung cấp executor/chế độ concurrency khác.

Ví dụ job nhập 1.000.000 bản ghi với `chunk size = 500`:

- Reader đọc các item từng cái một.
- Processor biến đổi hoặc loại bỏ item theo quy tắc.
- Writer nhận một tập item đã qua xử lý.
- Transaction của chunk được commit; checkpoint tương ứng được cập nhật theo cơ chế framework.
- Vòng lặp tiếp tục đến EOF.

Trong trường hợp lý tưởng không có lỗi hoặc skip, ứng dụng xử lý khoảng `1.000.000 / 500 = 2.000` chunk dữ liệu. Số transaction thực tế, listener calls và `commitCount` có thể khác số chunk dữ liệu do vòng lặp kết thúc, retry, skip hay cơ chế quản lý transaction. Không dùng phép chia này làm cam kết tuyệt đối về số lần commit.

### 2.1. Luồng xử lý

~~~mermaid
flowchart TD
    I["JobLauncher / Scheduler"] --> J["Job: importOrdersJob"]
    J --> S["Step: importOrdersStep"]
    S --> R["ItemReader.read()"]
    R --> P["ItemProcessor.process(item)"]
    P --> C{"Đủ commit interval<br/>hoặc hết dữ liệu?"}
    C -->|Chưa| R
    C -->|Rồi| W["ItemWriter.write(chunk)"]
    W --> T{"Transaction thành công?"}
    T -->|Có| K["Commit + checkpoint theo cấu hình"]
    K --> N{"Còn dữ liệu?"}
    N -->|Có| R
    N -->|Không| Z["Step COMPLETED"]
    T -->|Lỗi| F["Rollback / retry / skip / fail"]
    F --> S2["JobRepository lưu trạng thái"]
    Z --> S2
~~~

Sơ đồ mang tính khái niệm: trong chunk transaction, hành vi đọc/xử lý/ghi, các lần retry/skip, việc gọi listener và lúc lưu `ExecutionContext` có các chi tiết tùy reader, writer và chính sách fault tolerance. Không coi sơ đồ như thứ tự chính xác của tất cả callback Spring Batch.

Các thành phần cốt lõi:

| Thành phần | Trách nhiệm | Cần lưu ý |
| --- | --- | --- |
| `Job` | Gom các step và xác định workflow | `JobInstance` phân biệt từng đợt xử lý bằng identifying parameters |
| `Step` | Định nghĩa một đơn vị công việc | Mỗi lần chạy step tạo `StepExecution` |
| `ItemReader<I>` | Trả từng item nguồn; trả `null` khi hết dữ liệu | Reader có cursor/state cần checkpoint để restart |
| `ItemProcessor<I,O>` | Biến đổi hoặc lọc item; trả `null` để lọc | Lọc item khác với skip do lỗi |
| `ItemWriter<O>` | Ghi tập item đã xử lý trong chunk | Phải bảo đảm transaction và xử lý lại an toàn |
| `PlatformTransactionManager` | Điều khiển commit/rollback | Cần hiểu chính xác tài nguyên nào nằm trong transaction |
| `JobRepository` | Lưu metadata job/step và execution context | Phải bền vững nếu job yêu cầu restart sau crash |
| `ItemStream` / `ExecutionContext` | Mở, cập nhật và khôi phục trạng thái đọc/ghi | Không lưu state tùy tiện không nhất quán với commit |

**Local không có nghĩa tất cả dữ liệu nằm trong RAM.** Có thể đọc file trên shared storage, truy vấn database qua JDBC hoặc gọi HTTP; chỉ có phần xử lý Spring Batch là trong một JVM.

## 3. Local chunking tuần tự là nền tảng dễ kiểm soát

Ở cấu hình tuần tự cơ bản, một chunk kết thúc rồi chunk tiếp theo mới được xử lý. Ưu điểm:

- Ranh giới giao dịch dễ theo dõi.
- Reader có cursor và checkpoint thường đơn giản hơn khi chỉ có một thread.
- Thứ tự đọc và thứ tự hoàn tất chunk dễ dự đoán hơn, dù business ordering vẫn cần ràng buộc rõ.
- Không cần broker, request/reply, remote worker deployment hoặc điều phối partition phân tán.
- Có thể đo baseline trước khi tối ưu một biến như fetch size, chunk size hay cách ghi batch.

Hạn chế:

- Một thread xử lý chunk có thể để CPU rảnh khi chờ JDBC/network.
- Không tận dụng hết CPU cores nếu processor nặng và workload có tính độc lập cao.
- Một step tuần tự có thể không đủ throughput trước deadline.
- Một JVM vẫn chịu giới hạn heap, CPU quota, số file descriptor, số connection và I/O của máy/container.

Giả sử mỗi chunk 200 item cần 100 ms CPU và 400 ms I/O blocking:

\[
T_{\text{chunk}} \approx 0{,}1 + 0{,}4 = 0{,}5\text{ s}
\]

Một thread tối đa lý tưởng khoảng:

\[
\frac{200\text{ items}}{0{,}5\text{ s}}
= 400\text{ items/s}
\]

Đây là phép ước lượng giả định. Overhead khởi động, serialization, commit log, retry, GC và chênh lệch kích cỡ item có thể khiến số đo thực khác đáng kể. Cần đo throughput **đã commit thành công**, không dùng tốc độ gọi `read()` làm kết quả.

## 4. Một JVM không có nghĩa một thread

Ba cách triển khai thường bị nhầm:

| Mô hình | Đơn vị concurrency | StepExecution/ExecutionContext | Đặc điểm |
| --- | --- | --- | --- |
| **Local chunking tuần tự** | Các chunk của một step chạy lần lượt | Một StepExecution cho lần chạy step | Dễ kiểm thử và restart nhất khi reader stateful |
| **Multi-threaded step trong JVM** | Nhiều chunk cùng step được dispatch qua `TaskExecutor` | Thường các chunk chia sẻ **một StepExecution** | Có thể tăng throughput nhưng reader/state/thread safety và commit order phức tạp |
| **Local partitioning trong JVM** | Nhiều partition của cùng một worker step chạy song song | **Mỗi partition có StepExecution và ExecutionContext riêng** | Dễ tách input/reader theo file hoặc khoảng ID ổn định |

Cả ba đều có thể hoạt động **trong một JVM**, không cần broker. Chỉ mô hình thứ hai và thứ ba bắt đầu chạy nhiều phần việc đồng thời; mô hình partitioning tạo danh tính/checkpoint riêng cho mỗi shard.

~~~mermaid
flowchart TB
    subgraph SEQ["Chunk-oriented step tuần tự"]
        A1["chunk 1"] --> A2["chunk 2"] --> A3["chunk 3"]
    end
    subgraph MT["Multi-threaded step: một StepExecution"]
        B0["TaskExecutor"] --> B1["chunk 1"]
        B0 --> B2["chunk 2"]
        B0 --> B3["chunk 3"]
    end
    subgraph PART["Local partitioning: nhiều StepExecution"]
        C0["Manager Step"] --> C1["partition A<br/>workerStep:A"]
        C0 --> C2["partition B<br/>workerStep:B"]
        C0 --> C3["partition C<br/>workerStep:C"]
    end
~~~

Điểm phân biệt **local chunking** với **remote chunking** là ở remote chunking: manager đọc/chia chunk, gửi yêu cầu qua middleware để worker ở JVM khác xử lý/ghi rồi trả phản hồi. Còn local partitioning có thể dùng nhiều thread để chạy riêng từng worker StepExecution tại chỗ. Tên gọi “local chunking” đôi khi được dùng không chính thức để chỉ xử lý chunk trong cùng JVM; khi tài liệu hoặc thiết kế yêu cầu chính xác, hãy nói rõ đang dùng **chunk-oriented step tuần tự**, **multi-threaded step** hay **local partitioning**.

## 5. Ví dụ Spring Batch 5.x: CSV → processor → PostgreSQL

Xây một job nhập giao dịch từ tệp CSV. Mỗi dòng có `order_id` và `amount`. Processor tính tổng đã cộng phí dịch vụ 5%; writer upsert vào PostgreSQL. Toàn bộ reader/processor/writer chạy trong **một JVM**, step xử lý tuần tự khi không cấu hình `TaskExecutor`.

Đây là ví dụ cấu hình dành cho **Spring Batch 5.2.x với Spring Boot 3.x và Java 17+**; cần cấu hình `DataSource`, `JobRepository`, `PlatformTransactionManager` và đường dẫn file thực. Các record Java được dùng để đơn giản hóa minh họa; nếu dùng Spring Batch 6.x, phải đối chiếu API của đúng phiên bản.

### 5.1. Dữ liệu và bảng đích

~~~text
order_id,amount
101,120.00
102,500.00
103,75.50
~~~

~~~sql
-- PostgreSQL, cấu trúc minh họa
CREATE TABLE order_amount (
    order_id BIGINT PRIMARY KEY,
    final_amount NUMERIC(18, 2) NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

`order_id` là khóa nghiệp vụ duy nhất. Bảng có thể dùng upsert để một chunk được retry/restart không tạo thêm dòng trùng. Quy tắc sản xuất cần xác định thêm cách xử lý cùng order ID nhưng dữ liệu khác version.

### 5.2. Cấu hình job và step

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LocalOrderBatchConfig {

    public record OrderRow(long orderId, BigDecimal amount) {}
    public record OrderAmount(long orderId, BigDecimal finalAmount) {}

    @Bean
    @StepScope
    public FlatFileItemReader<OrderRow> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<OrderRow>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .saveState(true)
                .delimited()
                .names("order_id", "amount")
                .fieldSetMapper(fieldSet -> new OrderRow(
                        fieldSet.readLong("order_id"),
                        fieldSet.readBigDecimal("amount")))
                .build();
    }

    @Bean
    public ItemProcessor<OrderRow, OrderAmount> feeProcessor() {
        BigDecimal multiplier = new BigDecimal("1.05");
        return row -> new OrderAmount(
                row.orderId(),
                row.amount().multiply(multiplier)
                        .setScale(2, RoundingMode.HALF_UP));
    }

    @Bean
    public JdbcBatchItemWriter<OrderAmount> orderWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderAmount>()
                .dataSource(dataSource)
                .sql("""
                        INSERT INTO order_amount(order_id, final_amount)
                        VALUES (:orderId, :finalAmount)
                        ON CONFLICT (order_id)
                        DO UPDATE SET final_amount = EXCLUDED.final_amount
                        """)
                .itemSqlParameterSourceProvider(row ->
                        new MapSqlParameterSource()
                                .addValue("orderId", row.orderId())
                                .addValue("finalAmount", row.finalAmount()))
                .build();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<OrderRow> orderReader,
            ItemProcessor<OrderRow, OrderAmount> feeProcessor,
            JdbcBatchItemWriter<OrderAmount> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<OrderRow, OrderAmount>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(feeProcessor)
                .writer(orderWriter)
                .build(); // Không gắn TaskExecutor: baseline tuần tự
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository, Step importOrdersStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
~~~

Các bean `JobRepository`, `DataSource` và `PlatformTransactionManager` được cấp từ cấu hình Spring Boot/Spring Batch tương ứng. Ứng dụng phải bảo đảm writer dùng transaction manager phù hợp với chính datasource đích. Chỉ riêng snippet chưa bao gồm ứng dụng Spring Boot khởi chạy, dependency, schema metadata hoặc cơ chế scheduling.

**Những chi tiết quan trọng của ví dụ:**

- `chunk(500, transactionManager)` cấu hình khoảng 500 item đầu vào cho một lần commit thông thường. Trong trường hợp có filter/skip, số item ghi có thể ít hơn số item đọc.
- `ItemReader.read()` trả về từng `OrderRow`; `FlatFileItemReader` là `ItemStream` nên lưu vị trí khi `saveState(true)` và được framework quản lý lifecycle.
- `@StepScope` giúp late-bind `inputFile` từ job parameters khi step được thực thi; đây là một instance reader theo StepExecution, không phải một reader cho mỗi record.
- Processor ở đây không giữ state mutable giữa các item; phép nhân dùng `BigDecimal` để tránh lỗi số thực nhị phân.
- `JdbcBatchItemWriter` ghi một chunk thông qua cơ chế JDBC batch trong transaction.
- `ON CONFLICT ... DO UPDATE` là **cú pháp PostgreSQL**, không áp dụng nguyên xi cho mọi loại database.
- Vì không gắn `taskExecutor(...)`, step này là **chunk-oriented processing tuần tự**; không có chuyện tự động dùng nhiều thread chỉ vì máy có nhiều CPU cores.

### 5.3. JobParameters và tính bất biến của input

Ví dụ khi khởi chạy, cung cấp identifying job parameter `inputFile` trỏ tới file của kỳ xử lý; trong thực tế nên có thêm `businessDate` hoặc `snapshotId` ổn định. Để restart đúng:

1. Dùng lại **cùng JobInstance** (cùng tên job và identifying parameters).
2. Bảo đảm file đầu vào giữ nguyên nội dung, thứ tự dòng và quyền truy cập.
3. Không tự tăng identifying `run.id` để “restart”, vì có thể tạo JobInstance khác.
4. Giữ `JobRepository` và `ExecutionContext` để reader có thể khôi phục checkpoint.

Nếu file nguồn được ghi tiếp, thay thế hoặc sắp lại thứ tự sau khi job lỗi, offset lưu trong `ExecutionContext` có thể không còn trỏ đúng bản ghi. Với tải lớn và yêu cầu phục hồi, nên đọc **snapshot bất biến có checksum/manifest**.

## 6. Transaction: tại sao xử lý theo chunk?

Nếu ghi từng item bằng một transaction riêng, overhead commit/log/round-trip có thể lớn. Nếu chỉ commit một lần cuối job 1 triệu item, transaction có thể kéo dài rất lâu, giữ lock, tăng memory và khiến rollback toàn bộ khi lỗi. Chunking cân bằng hai cực này.

Giả sử `chunk size = 500`:

~~~text
BEGIN transaction (chunk #12)
    read/process item 5501..6000
    writer.write(500 processed items)
    cập nhật execution context / metadata theo cơ chế step
COMMIT transaction

BEGIN transaction (chunk #13)
    read/process item 6001..6500
    writer.write(...)
COMMIT transaction
~~~

Từng chunk là ranh giới commit/rollback điển hình. **Lưu ý:** không phải mọi resource nằm chung một transaction; file cursor, JDBC write, JMS publish hoặc HTTP call có mức phối hợp khác nhau. Việc writer gọi API ngoài transaction DB không tự động rollback được side effect ở API.

### 6.1. Khi xảy ra lỗi giữa chunk

| Điểm lỗi | Hệ quả cơ bản | Điều kiện để phục hồi đúng |
| --- | --- | --- |
| Reader không đọc được dòng chưa hợp lệ | Chunk có thể rollback hoặc chuyển sang skip theo policy | Có quy định lỗi dữ liệu nào được phép skip |
| Processor gặp lỗi tạm thời | Có thể retry nếu là fault-tolerant step | Retry giới hạn, xử lý lặp an toàn |
| JDBC writer lỗi trước commit | Thay đổi trong transaction DB rollback | Writer và transaction manager phải phối hợp đúng |
| Process crash sau các chunk đã commit | Chunk cũ vẫn bền vững, chunk hiện tại có thể chưa commit | `ExecutionContext`/JobRepository khôi phục được checkpoint |
| Commit DB thành công nhưng service ngoài bị chậm/lỗi | Trạng thái giữa các hệ thống có thể lệch | Outbox, idempotency key và đối soát |
| Metadata checkpoint mất hoặc không nhất quán | Reader có thể phát lại hoặc bỏ sót dữ liệu | Cần bảo vệ JobRepository và dùng transaction phù hợp |

Đừng suy luận “local là exactly once”. Với JDBC trong cùng transaction quản lý phù hợp, có thể đạt tính nhất quán mạnh trong phạm vi database ấy; với API bên ngoài, cần thiết kế chống lặp và cơ chế đối soát riêng.

### 6.2. Ví dụ retry có giới hạn

Spring Batch có cơ chế fault-tolerant chunk processing:

~~~java
// Trích phần cấu hình StepBuilder cho trường hợp nghiệp vụ phù hợp.
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, OrderAmount>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(feeProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(org.springframework.dao.TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

`retryLimit(3)` định nghĩa mức thử theo hợp đồng của Spring Batch (bao gồm lần thử đầu trong quy tắc đếm của framework), **không** có nghĩa luôn thử thêm đúng ba lần sau lần đầu. Không nên retry mọi `Exception`: lỗi phân tích định dạng, khóa duy nhất không hợp lệ hoặc lỗi nghiệp vụ cố định thường phải được xử lý riêng. Nếu retry làm quá tải DB, kết hợp backoff và giới hạn throughput khi cần.

Bài viết dùng retry như minh họa; chính sách skip/retry thực tế cần định nghĩa trong yêu cầu nghiệp vụ, có alert và theo dõi số item bị bỏ qua.

## 7. Checkpoint và restart trong một JVM

Spring Batch lưu metadata để phục hồi JobInstance qua `JobRepository`. Một lần restart tạo **JobExecution mới** cho cùng JobInstance; các step đã `COMPLETED` thường được bỏ qua, còn step chưa hoàn tất được chạy lại theo chính sách restart.

~~~mermaid
flowchart TD
    JI["JobInstance: importOrdersJob<br/>snapshot=2026-11-25"] --> E1["JobExecution #101 FAILED"]
    E1 --> S1["importOrdersStep<br/>đã commit nhiều chunk"]
    S1 --> M[("JobRepository<br/>StepExecution + ExecutionContext")]
    JI --> E2["JobExecution #102<br/>restart"]
    M --> E2
    E2 --> S2["Reader khôi phục vị trí<br/>từ checkpoint đã lưu"]
    S2 --> OUT["Tiếp tục ghi các item còn lại"]
~~~

Ví dụ step đọc 100.000 bản ghi, commit xong đến dòng 70.000 và crash trước commit chunk tiếp theo. Nếu `FlatFileItemReader` lưu checkpoint đúng, input bất biến và metadata không mất, khi restart nó có thể tiếp tục từ vị trí đã lưu. Chunk chưa commit thường có khả năng được đọc/xử lý lại.

Điều kiện restart an toàn gồm:

- `JobRepository` bền vững và không bị xóa giữa các lần chạy.
- Input data không thay đổi và JobParameters không bị tự ý đổi thành JobInstance mới.
- Reader/writer có hợp đồng `ItemStream` và checkpoint phù hợp.
- Transaction manager điều khiển đúng tác dụng ghi cần rollback.
- Side effect không thể rollback có cơ chế idempotency hoặc đối soát.
- Không bật `preventRestart()` nếu nghiệp vụ cần khôi phục JobInstance cũ.
- Nếu JobInstance đã `COMPLETED`, Spring Batch thường không cho “restart” bằng cách tạo JobExecution mới cho cùng instance; cần quy trình reprocess khác nếu muốn chạy lại.

**Không nên đặt `allowStartIfComplete(true)` chỉ để “giữ step hoạt động”.** Thiết lập đó cho phép step thành công chạy lại trong một số kịch bản restart, có thể trái mong muốn và tạo tác dụng phụ nếu writer không chống lặp.

### 7.1. Local không đồng nghĩa miễn nhiễm crash

Một JVM có thể bị giết giữa transaction vì OOM, node restart hoặc deploy. `JobRepository` phải tồn tại trên một hệ thống lưu trữ bền vững, còn file đầu vào và output phải có thể truy cập lại. Nếu sử dụng database in-memory cho metadata rồi JVM chết, job có thể mất lịch sử cần thiết để restart. Với production, dùng repository bền vững, backup/retention và kiểm thử kill process thật.

## 8. Chọn chunk size theo I/O và transaction

`Chunk size` (hay commit interval) tác động lên số lần commit, lượng dữ liệu được buffer và thời gian giữ transaction. Nó **không phải** số worker threads hay kích thước file đầu vào.

| Chunk size | Ưu điểm có thể có | Rủi ro cần đo |
| --- | --- | --- |
| 1–10 | Rollback scope nhỏ, transaction ngắn | Commit/round-trip quá nhiều |
| 100–500 | Thường là điểm thử hợp lý với nhiều workload | Phụ thuộc kích cỡ item và độ chậm writer |
| 1.000–5.000 | Giảm commit overhead, JDBC batch lớn hơn | Lock kéo dài, memory tăng, phạm vi rollback lớn |
| Rất lớn | Ít transaction | Hết heap, transaction log lớn, khó recovery và gây tranh chấp |

Các khoảng chỉ là **đề xuất thăm dò**, không phải mặc định hay giá trị tốt nhất của Spring Batch. Với item là ảnh hoặc JSON vài MB, chunk 500 có thể tiêu tốn bộ nhớ không chấp nhận được. Với row vài chục byte và DB tối ưu batch insert, chunk 500 có thể là mức nhỏ.

### 8.1. Ước lượng bộ nhớ một chunk

Nếu mỗi item sau xử lý chiếm trung bình 10 KB và chunk 500 items:

\[
500 \times 10\text{ KB} \approx 5\text{ MB}
\]

Đây chỉ là kích thước payload, **chưa tính** object overhead, buffer reader, JDBC driver, mạng, Java collections, các bản sao intermediate và transaction state. Nếu sau này chạy 8 chunk đồng thời, lượng dữ liệu đang xử lý có thể tăng đáng kể. Đừng lấy phép tính 5 MB để kết luận heap 5 MB là đủ.

### 8.2. Hiểu số lần commit

Giả sử 2,4 triệu item được ghi, chunk size 500 và không filter/skip, số chunk chứa dữ liệu khoảng:

\[
2{,}400{,}000/500 = 4{,}800
\]

Mỗi chunk cần overhead commit. Nếu một lần commit mất thêm 15 ms so với xử lý item, riêng overhead lý tưởng xấp xỉ 72 giây. Tăng chunk lên 1.000 có thể giảm số chunk dữ liệu xuống 2.400, nhưng chỉ thực sự có lợi nếu DB không nghẽn lock, transaction log hoặc RAM.

## 9. Khi nào thêm thread trong cùng JVM?

Khi baseline cho thấy một thread không đạt SLA **và** các tài nguyên vẫn còn headroom, có thể cân nhắc multi-threaded step:

~~~java
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public TaskExecutor chunkExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("chunk-local-");
    executor.initialize();
    return executor;
}

// Trong StepBuilder:
// .taskExecutor(chunkExecutor)
~~~

Đây là mẫu executor tham khảo, **không nên thêm trực tiếp vào `importOrdersStep` ở mục 5 nếu reader chưa được chứng minh thread-safe và restartable dưới concurrency**. `FlatFileItemReader` là reader có trạng thái/cursor, không mặc nhiên an toàn khi nhiều thread gọi cùng một instance.

Một số lưu ý kỹ thuật:

- Trong multi-threaded step, nhiều worker threads có thể cùng **StepExecution**. `@StepScope` theo StepExecution, **không** tự tạo một reader riêng cho mỗi chunk thread.
- Một reader đồng bộ hóa `read()` có thể ngăn data race nhưng không tự chứng minh checkpoint an toàn khi các chunk commit không theo thứ tự.
- `ThreadPoolTaskExecutor` có `maxPoolSize` và `queueCapacity`, nhưng concurrency thực có thể còn bị giới hạn bởi repeat operations, reader lock, JDBC connection hoặc API.
- `throttleLimit` đã bị deprecated trong Spring Batch 5.x; với nhu cầu giới hạn phức tạp, đối chiếu `StepBuilder.stepOperations(...)` và API của phiên bản đang sử dụng.
- Khi cần cô lập reader state/chunk restart, local partitioning với StepExecution riêng thường dễ lý giải hơn.

Không có yêu cầu phải chuyển toàn bộ job sang concurrency. Nếu thời gian chạy 20 phút trong cửa sổ 4 giờ và job có thể restart an toàn, **giữ mô hình đơn giản** thường hiệu quả về chi phí vận hành.

## 10. Local partitioning: mở rộng trong JVM mà tách checkpoint

Nếu dữ liệu chia được theo file, khóa hoặc khoảng ID, local partitioning có thể cấp một reader riêng cho từng partition:

~~~text
Manager Step
  ├─ workerStep:file-A -> File A, reader instance A, ExecutionContext A
  ├─ workerStep:file-B -> File B, reader instance B, ExecutionContext B
  └─ workerStep:file-C -> File C, reader instance C, ExecutionContext C
                      [TaskExecutor chạy các partition song song]
~~~

Ưu điểm:

- Partition tách rời nguồn dữ liệu và checkpoint.
- Có thể restart chỉ partition chưa hoàn tất khi tên partition và metadata ổn định.
- Dễ kiểm soát phạm vi dữ liệu để tránh nhiều thread dùng chung cursor.
- Sử dụng thêm CPU cores và chồng lấp I/O trong một JVM.

Hạn chế:

- Phải thiết kế partitioner có tên/phạm vi dữ liệu **ổn định qua restart**.
- Các partition có thể không cân bằng (một shard chứa 90% dữ liệu).
- Mọi worker vẫn tranh cùng RAM, JDBC pool và CPU của JVM/host.
- Chạy nhiều partition không tự giải quyết nút thắt writer/database.

Nếu nhu cầu là “chạy cùng chunk step nhanh hơn nhưng không sửa reader state”, chuyển sang partitioning là một lựa chọn có căn cứ **khi dữ liệu có thể chia thành các miền độc lập**. Nếu không có ranh giới dữ liệu an toàn, partitioning cũng không phải phép màu.

## 11. Đo nút thắt trước khi mở rộng

Với mô hình tuần tự, xác định thời gian nằm ở đâu:

| Thành phần | Tín hiệu đo | Hướng tối ưu |
| --- | --- | --- |
| Reader | `read()` chậm, truy vấn lâu, disk read lớn | Index, fetch/page size, snapshot, streaming reader, giảm round-trip |
| Processor | CPU tăng gần đầy core, GC nhiều | Tối ưu thuật toán, giảm object allocation, cache có kiểm soát |
| Writer | JDBC batch/commit lâu, lock wait | Batch SQL, index, transaction size, tách khóa ghi |
| Connection pool | Active/pending/acquire latency | Rút ngắn thời gian giữ connection, cân đối Hikari max và DB budget |
| HTTP/external I/O | p95/p99 tăng, 429/503, retries | Giới hạn in-flight, rate limiting, backoff, cache khi hợp lệ |
| JVM/OS | CPU quota, heap, GC, disk IOPS | Cấp tài nguyên đúng nút thắt, không chỉ tăng threads |
| JobRepository | Metadata/transaction chậm | Kiểm tra database, connection và retention; tránh metric/log quá nặng |

### 11.1. So throughput đã commit với SLA

Giả sử có **2.400.000 item** phải hoàn tất trong **40 phút**:

\[
R_{\text{required}}=
\frac{2{,}400{,}000}{40\times60}
=1{,}000\text{ items/s}
\]

Nếu baseline local chunking đạt 700 items/s, thời gian xử lý item ước tính:

\[
T_{\text{baseline}}\approx
\frac{2{,}400{,}000}{700}
\approx 3{,}429\text{ s} \approx57{,}1\text{ phút}
\]

Chưa cộng setup, validation, publish và thời gian phục hồi. Cần tối ưu/scale để tăng công suất hiệu dụng hoặc thương lượng lại cửa sổ. Thêm 4 threads có thể đạt 1.000 items/s nếu downstream còn headroom, nhưng không thể khẳng định trước khi benchmark.

**Một benchmark cần đo output đúng và bền vững**, không chỉ `readCount` tăng. Với retry/skip, số item đọc chưa chắc tương ứng số record hợp lệ được ghi.

### 11.2. Benchmark từng biến

1. Chạy tuần tự `chunk=100` với snapshot cố định; lưu throughput, latency, CPU, DB metrics và output checksum.
2. Chạy tuần tự `chunk=500`, rồi `1.000`; so sánh commit overhead, heap và lock duration.
3. Nếu chưa đạt SLA, xác định nút thắt thuộc reader, processor hay writer.
4. Khi dữ liệu độc lập và implementation an toàn, thử `TaskExecutor` 2/4/8 threads hoặc partitioning tương ứng.
5. Khi tăng concurrency, kiểm tra tổng JDBC/HTTP connections từ tất cả steps, pods và workload online.
6. Chạy một lần có lỗi, rollback, process crash và restart; đối soát output cuối cùng giống baseline hợp lệ.

Tối ưu đúng nghĩa là **giảm thời gian end-to-end** mà vẫn đạt quality/restart SLA. Không chọn cấu hình chỉ vì p50 chunk latency đẹp trong khi p99 và retry tăng.

## 12. Một JVM có thể nghẽn ở nhiều nơi

Giả sử executor có 8 threads nhưng JDBC pool `maximumPoolSize=4` và mọi chunk phải giữ JDBC connection suốt transaction:

~~~text
8 worker threads
  ├─ 4 threads đang giữ DB connection
  └─ 4 threads đang đợi connection

JDBC pool tối đa 4
  -> tăng threads thêm chưa chắc tăng DB throughput
~~~

Nếu mỗi transaction chờ API 2 giây mà vẫn giữ DB connection và khóa, database CPU có thể thấp nhưng Hikari pending cao. Cần đo **connection hold time**, thời gian trong transaction và thời gian chờ ngoài DB. Giải pháp có thể là giảm transaction scope hoặc đưa API call ra ngoài vùng giữ connection, với thiết kế idempotency/outbox phù hợp.

### 12.1. Công thức tham khảo cho workload I/O blocking

\[
N_{\text{threads}} \approx
N_{\text{CPU}}\left(1+\frac{W}{C}\right)
\]

Với `C` là thời gian CPU mỗi task và `W` là thời gian chờ blocking I/O, công thức có thể gợi ý concurrency ban đầu. Nó giả định các task độc lập và downstream chưa nghẽn. **Không dùng công thức để đặt JDBC pool bằng số thread** mà không xét số connection bị giữ, transaction và ngân sách toàn database.

Little's law cho biết số tác vụ in-flight trung bình:

\[
L = \lambda\times T_{\text{average}}
\]

Ví dụ muốn 100 requests/giây với latency trung bình 0,2 giây cần trung bình khoảng 20 requests trong hệ thống ở trạng thái ổn định. Đây là quan hệ về concurrency tại **ranh giới đang đo**, không suy ra mỗi worker phải giữ 20 JDBC connections.

## 13. Local chunking và các lựa chọn phân tán

| Yêu cầu | Local chunking tuần tự | Multi-threaded step | Local partitioning | Remote chunking / partitioning |
| --- | --- | --- | --- | --- |
| Đơn giản triển khai | Cao | Trung bình | Trung bình | Thấp hơn do cần hạ tầng phối hợp |
| Phù hợp nguồn dữ liệu stateful khó chia | Tốt nhất khi một reader tuần tự | Cần kiểm chứng reader concurrency | Chỉ khi có thể tách shard | Remote chunking giữ reader ở manager |
| Sử dụng nhiều CPU cores trong một JVM | Giới hạn | Tốt nếu CPU/IO có thể chạy độc lập | Tốt với partition cân bằng | Có thể mở rộng qua nhiều JVM |
| Checkpoint riêng theo shard | Không | Không tự có | Có | Remote partitioning có; remote chunking dùng giao thức request/reply riêng |
| Hệ thống middleware | Không bắt buộc | Không bắt buộc | Không bắt buộc | Thường cần broker/messaging hoặc kênh phân phối phù hợp |
| Áp lực lên DB/API | Một luồng chunk | Tăng theo concurrency | Tăng theo partition concurrency | Có thể tăng nhanh theo tổng worker |
| Failure/restart | Đơn giản hơn | Rủi ro shared state/commit order | Chọn lại partition lỗi nếu thiết kế đúng | Còn phải xử lý broker, mạng, worker crash |

**Không chọn mô hình theo số lượng máy sẵn có.** Chọn sau khi biết mục tiêu throughput, giới hạn input/output, khả năng chia dữ liệu, yêu cầu thứ tự, recovery SLA và chi phí điều phối.

### 13.1. Khi local chunking vẫn là quyết định đúng

- Input vừa đủ nhỏ hoặc batch window rộng.
- Job chạy tuần tự nhưng đạt throughput và có recovery buffer.
- Reader có cursor/checkpoint khó chia và tính chính xác quan trọng hơn tăng tốc nhỏ.
- Hệ thống đích đã bão hòa, thêm worker chỉ tăng tranh chấp.
- Đội vận hành muốn hạn chế broker và mô hình phân tán khi chưa cần thiết.

### 13.2. Khi cần tiến lên local partitioning

- Input có thể tách thành các file, khoảng ID hoặc nhóm khóa không chồng lấn.
- CPU có nhiều core chưa sử dụng hoặc I/O wait có thể chạy chồng lấp.
- Reader stateful cần được cô lập theo partition.
- Muốn restart chỉ shard lỗi với tên partition/ExecutionContext riêng.
- Một JVM và DB/API vẫn còn headroom đủ để tăng concurrency.

### 13.3. Khi local không còn đủ

- Một host đã hết CPU/RAM/I/O và vẫn không đạt deadline.
- Dữ liệu phân phối tự nhiên trên nhiều máy.
- Cần scale worker độc lập với manager để xử lý CPU/IO lớn.
- Hạ tầng cần job có thể chịu worker JVM crash, chia lại workload và monitor phân tán.

Trước khi chuyển sang remote, tính lại tổng DB pool, quota API, latency middleware, chi phí serialization, retry/redelivery và cách lưu JobRepository. Remote thường tăng khả năng mở rộng, nhưng cũng có thể làm lỗi khó tái lập và recovery phức tạp hơn.

## 14. Kịch bản kiểm thử tối thiểu

Ví dụ chuẩn bị snapshot 100.000 đơn hàng có checksum nguồn, chạy job `importOrdersJob` trong một JVM với `chunk=500`.

| Kịch bản | Thực hiện | Kỳ vọng |
| --- | --- | --- |
| Baseline | Chạy hoàn tất dữ liệu bất biến | Số order và tổng tiền khớp nguồn; Step `COMPLETED` |
| Chạy lại với JobInstance mới | Dùng snapshot/key mới theo nghiệp vụ | Output xử lý theo chính sách upsert/reprocess đã xác định |
| Crash trước commit | Chủ động gây lỗi ở chunk thứ 15 trước writer commit | Rollback phần chưa commit, restart không bỏ mất item |
| Crash sau commit | Giết process sau nhiều chunk đã commit | Restart dựa trên checkpoint; không nhân đôi tác dụng nghiệp vụ |
| Thay input giữa chừng | Sửa/xáo trộn file nguồn khi JobInstance vẫn chưa xong | Phát hiện vi phạm snapshot, không âm thầm tiếp tục |
| Lỗi dữ liệu | Một dòng amount không hợp lệ | Job fail hoặc skip theo chính sách rõ ràng; có số liệu đối soát |
| DB chậm | Giả lập query/commit latency cao | Throughput giảm được quan sát; không có kết luận sai về thread pool |
| Chunk-size benchmark | So 100/500/1.000 cùng input | Đo TPS, lock, memory, retry/rollback và output correctness |
| Thêm concurrency | Thử 2/4 threads **chỉ khi các bean an toàn** | Không đọc trùng/bỏ sót, checkpoint và output vẫn đúng |

Khi kiểm thử restart, nên dùng **JobRepository bền vững**, transaction thật và kiểm tra StepExecution/ExecutionContext của hai lần chạy; không chỉ mock một reader và xác nhận lặp gọi `read()`. Nếu chạy thử trong database in-memory rồi mất metadata sau khi process chết, kết quả không chứng minh được restart production.

### 14.1. Bộ chỉ số nên lưu

- `JobExecution`: ID, trạng thái, start/end time, thời gian chạy, số lần restart.
- `StepExecution`: `readCount`, `writeCount`, `filterCount`, `skipCount`, `commitCount`, `rollbackCount`.
- Throughput item/giây **đã commit**, chunk duration p50/p95/p99.
- CPU quota/usage, heap, GC, disk I/O.
- JDBC pool active/idle/pending, connection acquire latency, slow queries và DB locks.
- Số bản ghi nghiệp vụ duy nhất, tổng số tiền/checksum, sai khác reconciliation.
- ETA so với deadline, mức dự phòng cho validation/publish/restart.

Các metric quan sát có thể được tích hợp qua Micrometer/Actuator và log theo `jobExecutionId`/`stepExecutionId`; tên metric cụ thể tùy Spring Batch/Spring Boot version và instrumentation thực tế.

## 15. Sai lầm phổ biến

| Nhận định | Điều cần sửa |
| --- | --- |
| “Local chunking là một API step riêng.” | Đây là mô tả xử lý chunk trong cùng JVM; API chuẩn là chunk-oriented step. |
| “Trong một JVM thì luôn chỉ có một thread.” | Có thể dùng multi-threaded step, parallel steps và local partitioning. |
| “Chunk size = số thread.” | Chunk size là số item mỗi ranh giới commit; concurrency do executor và kiến trúc quyết định. |
| “Local không cần JobRepository bền vững.” | Vẫn cần metadata bền vững nếu muốn restart qua process crash. |
| “Cứ bật `@StepScope` là reader chạy đa luồng an toàn.” | Scope theo StepExecution, không tự tạo instance theo chunk thread. |
| “Transaction rollback cả HTTP request đã gửi.” | Giao dịch DB không tự rollback side effect ngoài transaction. |
| “`saveState(false)` sẽ sửa mọi lỗi concurrency.” | Nó có thể phá khả năng resume từ checkpoint. |
| “Tăng chunk size luôn tăng tốc.” | Chunk lớn gây thêm lock, RAM và rollback scope. |
| “Thêm worker luôn tăng throughput.” | Reader, database, API và CPU/RAM có thể trở thành bottleneck. |
| “Job có status `COMPLETED` nghĩa output đúng.” | Cần đối soát số lượng, giá trị và khả năng downstream đọc được. |

## 16. Checklist chọn local chunking cho production

- [ ] Đã có SLA, time budget, volume peak và mục tiêu throughput commit.
- [ ] Đã kiểm tra input snapshot, business date và identifying JobParameters ổn định.
- [ ] Đã chọn `chunk size` sau benchmark commit, memory, lock và rollback.
- [ ] Reader/processor/writer có hợp đồng đúng, lỗi dữ liệu có chính sách skip/retry.
- [ ] `JobRepository` bền vững và `ExecutionContext` hỗ trợ restart qua process crash.
- [ ] DB writer/side effects có transaction và idempotency theo đúng nghiệp vụ.
- [ ] Có số đo reader/processor/writer để xác định nút thắt thực, không phỏng đoán.
- [ ] Có ngân sách JDBC/HTTP pool và tài nguyên JVM đủ cả khi retry/restart.
- [ ] Nếu tăng concurrency, các bean và checkpoint đã được kiểm thử thread safety.
- [ ] Có phép thử kill/restart và đối soát output không trùng/không thiếu.
- [ ] Có cảnh báo sớm nếu ETA xử lý + validate + publish vượt deadline.
- [ ] Có tiêu chí chuyển sang partitioning hoặc remote khi một JVM không đủ năng lực.

## 17. Câu hỏi tự kiểm tra

1. Local chunking có bắt buộc phải dùng một thread hay không? Hãy phân biệt với multi-threaded step và local partitioning.
2. Với 500.000 item và chunk size 500, có khoảng bao nhiêu chunk dữ liệu nếu không filter/skip? Con số ấy có luôn bằng `StepExecution.commitCount` không?
3. Vì sao `JobRepository` và `ExecutionContext` vẫn quan trọng dù job chỉ chạy trong một JVM?
4. Job đã commit 60% số chunk thì process crash. Những điều kiện nào giúp restart tiếp tục từ phần đã commit?
5. Vì sao writer gọi API thanh toán trong transaction DB vẫn có thể tạo charge trùng khi retry?
6. Với reader CSV stateful và mục tiêu sử dụng 8 CPU cores, vì sao không thể thêm `taskExecutor(8)` rồi coi như xong?
7. Một job đang đạt SLA với dư 2 giờ và throughput DB đã bão hòa. Có cần chuyển sang remote chunking không? Dựa trên số liệu nào để quyết định?
8. Nếu dữ liệu có thể chia thành 20 file cố định và cần restart riêng file lỗi, mô hình local nào thường phù hợp hơn?
9. Chạy chunk size 100 nhanh 50 phút, chunk size 1.000 nhanh 35 phút nhưng p99 lock tăng và rollback kéo dài. Chọn cấu hình dựa trên những tiêu chí nào?
10. Làm sao chứng minh một lần restart tạo output nghiệp vụ giống lần chạy sạch?

**Gợi ý đáp án:** (1) Không; local mô tả nơi chạy, concurrency phụ thuộc cấu hình. (2) Khoảng 1.000 chunk dữ liệu; commitCount phụ thuộc lifecycle/error semantics. (3) Để lưu lịch sử, checkpoint và khôi phục giữa các JobExecution. (4) Input bất biến, cùng JobInstance, metadata bền vững, transaction/ItemStream chính xác, writer an toàn khi retry. (5) HTTP không nhất thiết thuộc cùng DB transaction; cần idempotency key/outbox. (6) Reader có cursor mutable chưa an toàn khi nhiều thread; checkpoint còn có thể sai. (7) Không nếu SLA và recovery đã đạt; tìm bottleneck thực. (8) Local partitioning với reader và StepExecution riêng cho mỗi file. (9) Throughput, memory, lock, tail latency, retry và restart budget. (10) So khớp khóa nghiệp vụ, số lượng, checksum/tổng tiền, trạng thái JobRepository sau crash/restart.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chu trình reader/processor/writer và commit interval.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, ExecutionContext và restart.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded steps, parallel flows, local/remote partitioning và remote chunking.
- [Spring Batch Reference — Job Repository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): lưu trạng thái bền vững của job/step.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): nguyên lý transaction và ranh giới tài nguyên.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): giới hạn số kết nối database và lý do tăng connection không luôn tăng throughput.

**Điểm cốt lõi:** Local chunking là nền tảng triển khai **chunk-oriented step trong một JVM**. Chạy tuần tự trước giúp nắm rõ transaction, checkpoint, dữ liệu đúng và throughput. Khi cần mở rộng, hãy đo nút thắt, giới hạn concurrency theo downstream và phân biệt rõ multi-threaded step với local partitioning. Một job local đơn giản nhưng restart an toàn và đáp ứng SLA là một kiến trúc hợp lệ, không cần phân tán chỉ vì dữ liệu lớn.
