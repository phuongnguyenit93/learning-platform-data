# Restart Job sau khi thất bại

## 1. Restartability giải quyết vấn đề gì?

Một batch job nhập 5 triệu giao dịch có thể chạy trong nhiều giờ. Nếu kết nối cơ sở dữ liệu bị ngắt khi đã ghi xong 4 triệu giao dịch, việc bắt đầu lại từ bản ghi đầu tiên vừa tốn tài nguyên vừa có nguy cơ tạo dữ liệu trùng. **Restartability** trong Spring Batch là khả năng tiếp tục một lần xử lý đã thất bại hoặc bị dừng có kiểm soát, dựa trên trạng thái đã lưu trong **JobRepository**.

Đây là nội dung cốt lõi của chương **Restartability** thuộc module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Khi tải lớn, thời gian khôi phục sau sự cố quan trọng không kém throughput lúc job chạy bình thường.

Cần phân biệt ba thao tác:

| Thao tác | Ý nghĩa | Tác động đến trạng thái |
|---|---|---|
| **Retry** | Thử lại một thao tác lỗi tạm thời, chẳng hạn ghi một chunk bị deadlock | Thường diễn ra **bên trong** cùng một `StepExecution`, theo chính sách fault tolerance |
| **Restart** | Chạy tiếp một `JobInstance` có lần thực thi trước đó thất bại hoặc bị dừng | Tạo **`JobExecution` mới** cho cùng `JobInstance`, tận dụng metadata/checkpoint |
| **Run một instance mới** | Xử lý một lô dữ liệu mới hoặc chủ ý làm lại công việc | Thay đổi identifying `JobParameters` hoặc tên job; checkpoint cũ không được kế thừa |

**Restart không tương đương “phát lại chính xác phần việc chưa commit” trong mọi trường hợp.** Spring Batch lưu checkpoint và quản lý transaction, nhưng khả năng tiếp tục đúng phụ thuộc vào reader, writer, độ ổn định dữ liệu nguồn và các tác động bên ngoài transaction.

## 2. Nắm đúng mô hình `JobInstance` – `JobExecution` – `StepExecution`

Trong Spring Batch, danh tính một lần xử lý được xác định bởi:

~~~text
JobInstance = jobName + identifying JobParameters
~~~

Ví dụ:

~~~text
jobName           = ordersImportJob
inputFile         = /data/immutable/orders-2026-11-26.csv (identifying)
batchId           = 2026-11-26                         (identifying)
~~~

Với cùng hai tham số định danh và cùng tên job, Spring Batch tìm lại **cùng một `JobInstance`**. `JobExecution` đại diện cho một lần thử chạy instance đó. Mỗi lần restart thành công về mặt khởi động sẽ có một `JobExecution` riêng, ví dụ lần đầu `FAILED` và lần tiếp theo `COMPLETED`. Bên trong từng execution có các `StepExecution` với số lượng đọc, ghi, rollback, tình trạng và `ExecutionContext`.

~~~mermaid
flowchart TD
    I["JobInstance: ordersImportJob + batchId=2026-11-26"] --> E1["JobExecution #101: FAILED"]
    I --> E2["JobExecution #102: COMPLETED (restart)"]
    E1 --> S11["validateInputStep: COMPLETED"]
    E1 --> S12["importOrdersStep: FAILED sau checkpoint"]
    E2 --> S21["validateInputStep: được bỏ qua"]
    E2 --> S22["importOrdersStep: tiếp tục từ checkpoint"]
    S22 --> D["Đọc phần còn lại và ghi idempotent"]
~~~

`validateInputStep` ở hình trên đã hoàn thành và **mặc định không chạy lại** khi restart. `importOrdersStep` từng lỗi sẽ được thực thi lại dưới một `StepExecution` mới với trạng thái phù hợp để khôi phục.

| Trạng thái trước đó | Ý nghĩa đối với restart |
|---|---|
| `FAILED` | Có thể restart nếu job cho phép và không vướng điều kiện chặn khác |
| `STOPPED` | Có thể restart sau khi việc dừng đã hoàn tất |
| `COMPLETED` | Không thể restart **cùng JobInstance** như một lần xử lý mới; thường gặp `JobInstanceAlreadyCompleteException` |
| `STARTING` / `STARTED` / `STOPPING` | Chưa được phép chạy đồng thời cùng instance; cần xác minh execution hiện tại thực sự đã kết thúc |
| `ABANDONED` / `UNKNOWN` | Cần xem xét metadata và phương án khôi phục; không giả định framework có thể tiếp tục an toàn |

Thực tế, hệ thống phải có **JobRepository bền vững**, lưu metadata của Spring Batch trong database được duy trì qua lần deploy và khởi động ứng dụng. Dùng kho metadata trong bộ nhớ rồi khởi động lại tiến trình sẽ làm mất cơ sở để restart đúng execution cũ.

## 3. Điều kiện để một job có thể restart an toàn

### 3.1. Dùng lại đúng identifying `JobParameters`

Giả sử job nhập tệp `orders-2026-11-26.csv` thất bại. Nếu chạy lại với `batchId=2026-11-27` hoặc thêm `run.id` mới làm identifying parameter, Spring Batch coi đó là **một instance khác**. Hệ thống bắt đầu lại từ đầu mà không lấy checkpoint của hôm trước.

Nếu dùng `RunIdIncrementer` cùng `startNextInstance`, đây là hành vi phù hợp để tạo **lần chạy mới**, không phải cách restart một lần chạy lỗi. Cần lưu lại `JobExecution.id` đã thất bại, hoặc truyền lại chính xác các identifying parameters khi chạy qua `JobLauncher`.

Một số thông số như thời điểm người vận hành gửi lệnh có thể đặt là *non-identifying*, nhưng cũng không nên thay đổi tùy tiện khi restart: logic xử lý có thể đọc tham số đó và làm kết quả không còn tương thích với checkpoint. Nguyên tắc an toàn là dùng lại bộ tham số của lần thất bại.

### 3.2. Reader hỗ trợ `ItemStream` và checkpoint

Với chunk-oriented step, reader như `FlatFileItemReader`, `JdbcCursorItemReader` hoặc `JdbcPagingItemReader` có thể lưu trạng thái đọc vào `ExecutionContext` qua giao diện `ItemStream`. Spring Batch thực hiện `open` khi bắt đầu, `update` tại thời điểm checkpoint và `close` khi kết thúc. Trạng thái được lưu cùng metadata của step.

Điểm cần giữ:

- Đặt tên reader ổn định, không trùng với các `ItemStream` khác trong cùng step; ví dụ `ordersCsvReader`. Tên này được dùng để tạo khóa checkpoint.
- Giữ `saveState(true)` đối với reader được phép restart; không tắt chỉ để xử lý lỗi thread safety.
- Nếu dùng reader/writer tùy biến có trạng thái, triển khai `ItemStream` để khôi phục dữ liệu cần thiết; nếu `ItemStream` được dùng gián tiếp bên trong một bean hỗn hợp, phải đăng ký với step nếu framework không tự phát hiện.
- Tài nguyên nguồn phải ổn định: không ghi đè file đang đọc, không xáo trộn thứ tự bản ghi, không để truy vấn paging thay đổi tập kết quả trong lúc restart.

Checkpoint thường gắn với **lần commit chunk thành công**, không phải mọi item được đọc. Vì vậy khi lỗi xảy ra giữa chunk, các item trong chunk chưa commit có thể được đọc lại.

### 3.3. Writer và side effect phải nhất quán

Writer ghi qua cùng transaction manager với chunk có thể rollback các câu lệnh chưa commit khi step thất bại. Nhưng gửi email, gọi HTTP API, đẩy message hoặc ghi sang hệ thống không tham gia transaction là **side effect bên ngoài**; Spring Batch không tự rollback chúng.

Đối với nguồn/đích lớn hoặc hệ thống phân tán, nên thiết kế **idempotency**: cùng một bản ghi được xử lý lại không làm thay đổi kết quả nghiệp vụ theo cách ngoài ý muốn. Ví dụ dùng khóa nghiệp vụ duy nhất và `UPSERT`, bảng outbox, idempotency key hoặc de-duplication ở phía nhận.

### 3.4. Job thực sự cho phép restart

Spring Batch mặc định cho phép restart nếu không có cấu hình cấm. Nếu định nghĩa job gọi `.preventRestart()`, job đó không được restart dù execution trước thất bại. Bên cạnh đó, `startLimit` của step có thể giới hạn số lần step được bắt đầu; đạt giới hạn sẽ chặn các lần tiếp theo.

## 4. Ví dụ Java config: nhập CSV và restart sau khi lỗi

Ví dụ dùng **Spring Batch 5.x**, Java 17 và PostgreSQL. File CSV được đặt trên filesystem ở đường dẫn cố định, không sửa nội dung trong suốt vòng đời `JobInstance`. Mỗi bản ghi có `id` làm khóa nghiệp vụ.

~~~csv
id,amount
1,125000.00
2,52000.00
3,80000.00
~~~

Bảng đích:

~~~sql
CREATE TABLE imported_orders (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(18,2) NOT NULL
);
~~~

**Cấu hình job:**

~~~java
import java.math.BigDecimal;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class RestartableOrdersJobConfiguration {

    public record Order(long id, BigDecimal amount) {}

    @Bean
    public Job ordersImportJob(
            JobRepository jobRepository,
            @Qualifier("importOrdersStep") Step importOrdersStep) {
        return new JobBuilder("ordersImportJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("ordersCsvReader") FlatFileItemReader<Order> reader,
            @Qualifier("ordersJdbcWriter") JdbcBatchItemWriter<Order> writer) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, Order>chunk(100, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean
    @StepScope
    public FlatFileItemReader<Order> ordersCsvReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<Order>()
                .name("ordersCsvReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fs ->
                        new Order(
                                fs.readLong("id"),
                                fs.readBigDecimal("amount")))
                .saveState(true)
                .build();
    }

    @Bean
    public JdbcBatchItemWriter<Order> ordersJdbcWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<Order>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO imported_orders(id, amount)
                    VALUES (:id, :amount)
                    ON CONFLICT (id)
                    DO UPDATE SET amount = EXCLUDED.amount
                    """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("id", item.id())
                                .addValue("amount", item.amount()))
                .build();
    }
}
~~~

Ví dụ tập trung vào một step xử lý CSV. Hệ thống thực tế cần cấu hình `DataSource`, `PlatformTransactionManager`, `JobRepository` và tạo các bảng metadata Batch tương thích version; Spring Boot có thể hỗ trợ phần cấu hình hạ tầng này.

Các điểm liên quan trực tiếp tới restart:

1. `ordersCsvReader` được đánh dấu `@StepScope` để lấy `inputFile` từ `JobParameters` khi step chạy. Bean khai báo trả về kiểu cụ thể `FlatFileItemReader<Order>`, giúp Spring Batch thấy các phương thức `ItemStream` cần dùng cho checkpoint.
2. `name("ordersCsvReader")` phải ổn định giữa các lần chạy của **cùng instance**; thay tên hoặc thay implementation reader khi restart có thể làm các khóa trạng thái không còn phù hợp.
3. `saveState(true)` cho phép lưu vị trí đọc. Dòng header được bỏ qua cố định bằng `linesToSkip(1)`.
4. `chunk(100, transactionManager)` tạo các mốc commit theo nhóm tối đa 100 item. Chi phí commit, retry và rollback thay đổi theo chunk size.
5. Writer sử dụng PostgreSQL `ON CONFLICT` để cùng một `id` được ghi lại mà không tạo bản ghi trùng. Một hệ quản trị khác cần cú pháp upsert tương ứng.
6. Job và step **không** bật `preventRestart()`, `allowStartIfComplete(true)` hoặc thiết lập giới hạn bắt đầu không phù hợp.

**Phạm vi bảo đảm:** cấu hình giúp reader tiếp tục theo trạng thái đã lưu và writer ghi lặp an toàn ở mức khóa `id`. Nó **không tự giải quyết** trường hợp CSV bị thay thế, thay đổi thứ tự dòng hay hệ thống khác đã nhận side effect.

### 4.1. Chạy lần đầu với tham số định danh rõ ràng

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile",
                "/data/immutable/orders-2026-11-26.csv", true)
        .addString("batchId", "2026-11-26", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(ordersImportJob, parameters);
Long executionId = execution.getId();
// Lưu executionId để kiểm tra lỗi và restart khi cần.
~~~

Trong ví dụ, cả `inputFile` và `batchId` đều là identifying parameters (`true`). Đường dẫn file phải tồn tại trên host/JVM chạy job và nội dung file phải được giữ nguyên. Không nên sử dụng file mà một tiến trình khác đang tiếp tục append trong lúc xử lý.

### 4.2. Restart execution đã thất bại

Với `JobOperator` đã được cấu hình sẵn, gọi:

~~~java
// failedExecutionId là ID của JobExecution bị FAILED/STOPPED;
// đây KHÔNG PHẢI JobInstance ID.
long newExecutionId = jobOperator.restart(failedExecutionId);
~~~

`restart(...)` kiểm tra execution trước, job name, job parameters và trạng thái restartable rồi tạo execution mới cho **cùng JobInstance**. Tùy cấu hình launcher, lời gọi có thể trả về khi job vẫn đang chạy; phải theo dõi trạng thái của `newExecutionId` thay vì coi việc gọi API thành công là job đã hoàn tất.

Một cách khác là gọi lại:

~~~java
JobExecution restarted = jobLauncher.run(ordersImportJob, parameters);
~~~

Điều kiện là tham số `parameters` có **identifying values giống hệt** lần chạy lỗi, execution trước đã kết thúc ở trạng thái cho phép restart và không có một execution của instance đó đang chạy. Nếu lần trước đã hoàn thành, Spring Batch không chạy lại cùng instance; nó có thể ném `JobInstanceAlreadyCompleteException`.

Hai API nói trên là **hai cách khởi động thay thế**, không gọi cả hai cho cùng một lần restart.

## 5. Checkpoint hoạt động thế nào khi job lỗi?

Giả sử file có 1.000 dòng dữ liệu và `chunkSize=100`. Step đã commit thành công hai chunk, sau đó gặp lỗi ở dòng 250 trước khi chunk thứ ba commit.

~~~mermaid
sequenceDiagram
    participant R as Reader
    participant S as Chunk step
    participant DB as Database
    participant JR as JobRepository

    R->>S: Đọc dòng 1..100
    S->>DB: Ghi chunk 1; commit
    S->>JR: Lưu checkpoint tại dòng 100
    R->>S: Đọc dòng 101..200
    S->>DB: Ghi chunk 2; commit
    S->>JR: Lưu checkpoint tại dòng 200
    R->>S: Đọc dòng 201..250
    S--xDB: Gặp lỗi trước commit chunk 3
    Note over DB,JR: Chunk chưa commit được rollback
    Note over S,JR: JobExecution kết thúc FAILED
    JR-->>S: Restart từ checkpoint đã commit
    R->>S: Đọc lại từ dòng 201
~~~

Hình mô tả **logic checkpoint**, không mô tả thứ tự câu SQL nội bộ chính xác. Trạng thái của `ItemStream` và transaction commit được Spring Batch phối hợp qua JobRepository và transaction manager. Trong ví dụ, chunk thứ ba chưa commit nên 50 dòng vừa đọc có thể được đọc lại ở execution tiếp theo.

Khi restart đúng instance:

- Hai chunk đã commit không bị đọc lại nếu reader phục hồi checkpoint chính xác và nguồn không đổi.
- Chunk lỗi được đọc lại từ checkpoint cuối cùng; writer phải xử lý lặp an toàn trong mọi tình huống retry, rollback hoặc side effect ngoài DB.
- Nếu tiến trình chết đột ngột, metadata execution đôi khi còn ở `STARTED` thay vì `FAILED`. Khi đó cần quy trình vận hành xác minh thực tế job không còn chạy và xử lý metadata bằng cơ chế quản trị được hỗ trợ; không tạo execution cạnh tranh hoặc trực tiếp sửa bảng metadata theo cảm tính.

**Checkpoint không phải snapshot dữ liệu.** Một reader query `ORDER BY id` nhưng bảng thay đổi giữa hai lần chạy vẫn có thể bỏ sót hoặc xử lý lại bản ghi. Với dữ liệu truy vấn, nên dùng snapshot/cutoff cố định, khóa sắp xếp duy nhất và điều kiện lọc nhất quán; với file, nên lưu checksum và bảo vệ file khỏi chỉnh sửa.

## 6. Restart tác động thế nào tới nhiều step và partition?

### Job gồm nhiều step

Giả sử flow:

~~~text
validateInputStep -> importOrdersStep -> publishSummaryStep
~~~

Lần chạy đầu:

| Step | Trạng thái |
|---|---|
| `validateInputStep` | `COMPLETED` |
| `importOrdersStep` | `FAILED` |
| `publishSummaryStep` | Chưa chạy |

Khi restart, Spring Batch **mặc định bỏ qua** `validateInputStep` đã hoàn thành; `importOrdersStep` được chạy lại với state cần thiết, rồi mới tới `publishSummaryStep` nếu step nhập hoàn thành. Với một step đã hoàn tất nhưng cần chạy lại có chủ ý, có thể dùng `.allowStartIfComplete(true)` trên `StepBuilder`; đây là hành vi đặc biệt cần xem xét kỹ vì có thể lặp side effect.

### Multi-threaded step

Một `StepExecution` chứa các item được nhiều luồng xử lý sẽ khó duy trì vị trí đọc tuần tự đáng tin nếu reader có state không an toàn. `FlatFileItemReader` và nhiều reader stateful khác không mặc nhiên thread-safe. Việc bọc synchronized có thể bảo vệ thao tác đọc nhưng không tự bảo đảm thứ tự xử lý/commit và khả năng restart. Vô hiệu checkpoint bằng `saveState(false)` làm mất cơ chế tiếp tục từ vị trí đọc và buộc doanh nghiệp tự kiểm soát trùng/lặp.

### Partitioning

Ở partitioning, mỗi partition có **StepExecution riêng** cùng `ExecutionContext`, ví dụ dải `minId/maxId`. Các partition đã `COMPLETED` thường được bỏ qua khi restart, còn partition thất bại được chạy lại. Các điều kiện quan trọng:

- Đặt tên partition nhất quán để manager ghép được partition mới với lịch sử execution.
- Chốt phạm vi xử lý của lần chạy; không tự chia lại tập dữ liệu thành dải hoàn toàn khác khi restart.
- Dùng reader `@StepScope` riêng cho từng partition; không chia sẻ cursor mutable giữa các worker.
- Bảo đảm writer idempotent vì một partition hoặc một thông điệp công việc có thể được phát lại khi hệ thống gặp lỗi.

### Remote partitioning và remote chunking

Khi manager/worker chạy trên nhiều JVM, phải xét thêm gián đoạn mạng, middleware, thông điệp giao lại và tiến trình worker mất kết nối. Trạng thái trong JobRepository vẫn quan trọng, nhưng **giao nhận message không tự đồng nghĩa exactly-once nghiệp vụ**. Nên có partition/message ID ổn định, transaction hoặc outbox thích hợp, cơ chế chống xử lý trùng và giám sát worker mất tích.

## 7. Retry, skip, restart và giới hạn lỗi

Trong một chunk step, cấu hình fault tolerance có thể cho phép thử lại lỗi tạm thời và bỏ qua một số item lỗi có điều kiện. Ví dụ khái niệm:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(reader)
    .writer(writer)
    .faultTolerant()
    .retry(org.springframework.dao.DeadlockLoserDataAccessException.class)
    .retryLimit(3)
    .skip(org.springframework.batch.item.file.FlatFileParseException.class)
    .skipLimit(10)
    .build();
~~~

Trong hệ thống thực, phải xác định rõ retryable exception và skippable exception theo nghiệp vụ. Cú pháp trên là ví dụ thay thế cho phần cấu hình step trước đó; cần kiểm tra exception cụ thể do driver và Spring JDBC phát ra. Bỏ qua dòng lỗi tài chính hoặc thanh toán mà không có luồng đối soát có thể gây thiếu dữ liệu nghiêm trọng.

| Câu hỏi | Retry | Skip | Restart |
|---|---|---|---|
| Xảy ra khi nào? | Một thao tác lỗi trong step đang chạy | Có item lỗi nhưng chính sách cho phép bỏ qua | Job đã lỗi/dừng và được khởi động lại |
| Có tạo `JobExecution` mới? | Không | Không | Có |
| Mục tiêu | Chữa lỗi tạm thời | Tiếp tục dù có item không xử lý được | Tiếp tục công việc sau sự cố |
| Rủi ro chính | Side effect lặp, retry quá nhiều | Mất hoặc thiếu item nghiệp vụ | Checkpoint sai, nguồn đổi, ghi lặp |

Nên đặt giới hạn retry và skip, phân loại lỗi theo bản chất, ghi log item/partition lỗi có kiểm soát và cung cấp cơ chế đối soát. Đối với batch quy mô lớn, khả năng restart phải được kiểm chứng cùng với chính sách retry/skip trước khi tăng concurrency.

## 8. Quy trình vận hành khi job FAILED

Một runbook khôi phục có thể gồm các bước sau:

1. **Xác nhận job thực sự dừng.** Kiểm tra ứng dụng, worker và JobRepository để bảo đảm không còn execution hoặc message đang xử lý cùng instance.
2. **Lấy đúng execution ID.** Ghi nhận `jobName`, `JobInstance.id`, `JobExecution.id`, trạng thái, timestamps, identifying parameters và step/partition lỗi.
3. **Đọc nguyên nhân gốc.** Kiểm tra exception, SQL timeout/deadlock, file lỗi, dung lượng đĩa, trạng thái network, saturation CPU, pool kết nối và dữ liệu đầu vào.
4. **Sửa nguyên nhân mà không làm mất checkpoint.** Ví dụ tăng pool kết nối hoặc sửa cấu hình truy cập, khôi phục kết nối DB; nếu phải thay file, đổi schema hoặc logic xử lý, đánh giá lại tính tương thích của state trước khi restart.
5. **Kiểm tra tính nhất quán dữ liệu.** So sánh count, khóa nghiệp vụ, batch ID, checksum và các side effect ngoài transaction. Đối với lỗi không rollback được, xử lý bù trừ hoặc chống trùng trước khi tiếp tục.
6. **Restart đúng instance.** Dùng `JobOperator.restart(failedExecutionId)` hoặc launch lại với identifying parameters gốc. Không đổi `run.id` nhằm “ép chạy lại”.
7. **Giám sát execution mới đến trạng thái cuối.** Theo dõi `BatchStatus`, `ExitStatus`, `readCount`, `writeCount`, `skipCount`, `rollbackCount`, thời gian thực thi và StepExecution/partition lâu bất thường.
8. **Đối soát nghiệp vụ sau khi hoàn tất.** Job `COMPLETED` không bảo đảm mọi bản ghi đều hợp lệ nếu chính sách cho phép skip; đối chiếu tổng số, tổng tiền, checksum, số dòng lỗi và side effect đã phát.

Một ví dụ quan sát metadata bằng SQL (tên bảng/cột có thể phụ thuộc schema và cấu hình Spring Batch):

~~~sql
SELECT JOB_EXECUTION_ID, JOB_INSTANCE_ID, STATUS,
       EXIT_CODE, START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
WHERE JOB_EXECUTION_ID = :execution_id;

SELECT STEP_NAME, STATUS, READ_COUNT, WRITE_COUNT,
       READ_SKIP_COUNT, PROCESS_SKIP_COUNT, WRITE_SKIP_COUNT,
       ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :execution_id
ORDER BY STEP_EXECUTION_ID;
~~~

Có thể dùng `JobExplorer` hoặc công cụ vận hành để đọc metadata thay cho truy vấn SQL trực tiếp. Không tùy tiện `UPDATE` bảng metadata để đổi `STARTED` thành `FAILED`: hành vi này có thể phá bảo đảm chống chạy trùng nếu một worker còn hoạt động. Các execution mắc kẹt hoặc trạng thái `UNKNOWN` cần quy trình xử lý sự cố riêng.

## 9. Những lỗi thường gặp khi restart

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `JobInstanceAlreadyCompleteException` | Instance đã `COMPLETED` | Kiểm tra xác định instance; nếu nghiệp vụ cần lô mới, dùng identifying parameters mới |
| `JobExecutionAlreadyRunningException` | Có execution cùng instance đang `STARTING/STARTED/STOPPING` | Kiểm tra tiến trình/worker; không khởi động song song |
| `JobRestartException` | Job không restartable hoặc trạng thái không cho phép | Kiểm tra `preventRestart`, `JobExecution` và lịch sử trạng thái |
| `StartLimitExceededException` | Step đạt `startLimit` | Xem chính sách số lần thử và nguyên nhân lỗi lặp |
| Bị xử lý lại toàn bộ file | Đổi identifying parameter, `saveState(false)`, reader name khác hoặc state không tồn tại | So khớp instance, khóa checkpoint và `ItemStream` |
| Dòng đọc lại sai vị trí | File nguồn đã đổi hoặc paging SQL không ổn định | Khóa file/snapshot, sắp xếp theo khóa duy nhất và cố định cutoff |
| Đích có bản ghi trùng | Writer không idempotent, unique key không được áp dụng | Thiết kế khóa nghiệp vụ, upsert hoặc cơ chế de-duplication |
| Job `COMPLETED` nhưng thiếu dữ liệu | Step đã skip item, filter item hoặc phân vùng không đầy đủ | Đối chiếu counters, skip records, vùng dữ liệu và báo cáo nghiệp vụ |
| Restart chậm hơn lần đầu | Dữ liệu skew, index kém, contention, nhiều worker retry | Quan sát I/O, pool wait, per-step/partition runtime và throughput |

## 10. Kiểm thử restartability trước khi đưa vào production

Để kiểm chứng ví dụ CSV, nên dùng dữ liệu đầu vào đủ lớn và môi trường JobRepository **bền vững**:

1. Chạy một job với 1.000 dòng và chunk 100; xác nhận có 1.000 khóa `id` duy nhất trong bảng `imported_orders`.
2. Chèn lỗi có chủ đích tại item 250 **trước commit** (ví dụ processor thử nghiệm ném exception một lần); xác nhận execution đầu `FAILED`, hai chunk đầu đã commit, chunk đang xử lý rollback.
3. Tắt cơ chế chèn lỗi, restart bằng **execution ID của lần lỗi**; xác nhận execution mới cùng `JobInstance`, job hoàn thành, tổng số dòng và giá trị đúng.
4. Thử lỗi tại ranh giới commit và lỗi process/host bị tắt đột ngột; bảo đảm không có side effect bị nhân đôi. Cần phân biệt lỗi điều khiển từ ứng dụng với crash làm metadata còn `STARTED`.
5. Thử thay nội dung CSV rồi restart trên môi trường thử nghiệm để thấy rủi ro; trong thực tế phải có quy trình cấm ghi đè hoặc phát hiện checksum thay đổi.
6. Kiểm chứng job nhiều step và job partitioned: step/partition `COMPLETED` được bỏ qua đúng, step/partition lỗi tiếp tục đúng, tên partition không đổi.
7. Lặp thí nghiệm với concurrency 1, 2, 4 và đo throughput, lock, connection wait và thời gian recovery; concurrency cao hơn không được đánh đổi tính đúng đắn để lấy tốc độ.

### Câu hỏi tự kiểm tra

**Nếu job lỗi sau khi ghi 2.300/5.000 dòng, restart sẽ đọc từ dòng 2.301?** Không thể kết luận chỉ từ hai số đó. Cần biết chunk nào đã commit, reader có lưu checkpoint không, data source có ổn định không và ghi ngoài transaction có xảy ra không.

**Nếu đổi `batchId` để chạy lại, đó còn là restart không?** Không, nếu `batchId` là identifying JobParameter. Nó tạo `JobInstance` khác và không dùng checkpoint cũ.

**Nếu writer dùng upsert, có thể bỏ checkpoint không?** Vẫn nên duy trì checkpoint để giảm I/O và chi phí khôi phục. Upsert hạn chế ghi trùng, nhưng đọc lại toàn bộ nguồn sẽ tốn tài nguyên và không giải quyết mọi side effect.

**Một job có `COMPLETED` rồi có thể dùng restart để chạy báo cáo lại không?** Không theo mặc định cho cùng instance. Hãy thiết kế run nghiệp vụ mới với identifying parameters tương ứng hoặc một luồng reprocessing có kiểm soát.

## 11. Ghi nhớ

Restartability trong Spring Batch dựa trên **JobInstance ổn định, JobRepository bền vững, StepExecution/ExecutionContext và checkpoint hợp lệ**. `JobOperator.restart(executionId)` hoặc launch lại với cùng identifying parameters giúp tạo lần thực thi mới cho công việc cũ khi trạng thái cho phép. Với dữ liệu lớn, multi-threaded step và partitioning, khả năng khôi phục đúng chỉ đáng tin khi nguồn đầu vào không thay đổi ngoài dự kiến, các worker không chia sẻ state nguy hiểm và writer/side effect có cơ chế idempotency. Hãy kiểm thử lỗi thực tế và đối soát dữ liệu, thay vì chỉ nhìn thấy trạng thái `COMPLETED`.
