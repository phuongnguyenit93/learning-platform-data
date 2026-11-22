# Chọn chunk hay tasklet trong thiết kế Spring Batch

## 1. Vì sao phải lựa chọn giữa chunk và tasklet?

Khi tạo một step trong Spring Batch, một quyết định quan trọng là **đơn vị công việc sẽ được framework quản lý như thế nào**. Cùng một yêu cầu như “nhập file đơn hàng rồi đánh dấu lô đã xử lý” có thể được lập trình bằng một vòng lặp tự viết trong tasklet hoặc bằng `ItemReader`, `ItemProcessor` và `ItemWriter` trong chunk-oriented step. Cả hai đều có thể thực hiện được công việc, nhưng khác nhau nhiều ở **ranh giới transaction, checkpoint, khả năng restart, thống kê, retry/skip và chi phí bảo trì**.

Ví dụ:

- Cần kiểm tra file đầu vào có tồn tại và header hợp lệ trước khi xử lý: một thao tác ngắn, thường hợp với **tasklet**.
- Cần đọc 2 triệu dòng CSV, chuẩn hóa từng record và ghi database theo nhóm: thường hợp với **chunk**.
- Cần gọi một lệnh SQL `UPDATE` có điều kiện để đổi trạng thái của cả một lô: **tasklet** có thể đủ nếu thời gian và transaction được kiểm soát.
- Cần copy 100.000 object giữa hai kho lưu trữ, xử lý lỗi riêng từng object và tiếp tục sau failure: thường nên mô hình hóa từng object thành **item của chunk**, thay vì viết vòng lặp không có checkpoint trong tasklet.

Trong ngữ cảnh **Spring Batch Core Processing → Quyết định thiết kế**, mục tiêu là chọn mô hình phù hợp với *hành vi nghiệp vụ và vận hành* của step. Số dòng dữ liệu là tín hiệu quan trọng, nhưng không phải tiêu chí duy nhất.

## 2. Mô hình thực thi của hai loại step

### 2.1. Chunk-oriented step

Chunk step tổ chức việc xử lý thành các đơn vị item:

```text
                    Job
                     |
                     v
              chunk-oriented Step
                     |
           +---------+---------+
           |                   |
       ItemReader<I>       Transaction
           |                   |
           v                   |
       ItemProcessor<I,O>      |
           |                   |
        O hoặc null            |
           |                   |
           v                   |
       ItemWriter<O>           |
           |                   |
      commit chunk ------------+
           |
         repeat
           |
     Step COMPLETED/FAILED
```

Với `chunk(100, transactionManager)`, Spring Batch cố gắng gom tối đa 100 item được đọc trong một chunk, xử lý và ghi chúng trước khi commit transaction của chunk. Trong một chunk, processor có thể trả `null` để filter item; số item thực sự truyền cho writer có thể nhỏ hơn số được đọc.

Ví dụ file có 250 item, không filter/skip và mọi thao tác đều thành công:

```text
Chunk 1: read 1..100   -> process -> write -> COMMIT
Chunk 2: read 101..200 -> process -> write -> COMMIT
Chunk 3: read 201..250 -> process -> write -> COMMIT
```

Framework cung cấp sẵn các khái niệm reader/processor/writer, các bộ đếm `readCount`, `writeCount`, `filterCount`, `skipCount`, cơ chế fault tolerance và hỗ trợ restart qua `ItemStream`/`ExecutionContext` khi component được thiết kế đúng.

**Chunk không đồng nghĩa “mỗi item là một transaction”.** Một chunk là ranh giới transaction thông dụng; nếu writer gọi API bên ngoài, transaction JDBC không tự rollback hiệu ứng ở API đó.

### 2.2. Tasklet step

Tasklet step chạy một khối logic do ứng dụng định nghĩa:

```text
                    Job
                     |
                     v
                Tasklet Step
                     |
                 execute(...)
                     |
             +-------+---------+
             |                 |
     RepeatStatus.FINISHED   RepeatStatus.CONTINUABLE
             |                 |
      hoàn thành step       gọi execute(...) tiếp
```

`Tasklet.execute(StepContribution contribution, ChunkContext chunkContext)` là callback thực hiện công việc. Nó có thể trả:

- `RepeatStatus.FINISHED`: không cần gọi tiếp, step hoàn tất nếu không có lỗi.
- `RepeatStatus.CONTINUABLE`: framework có thể gọi tasklet thêm lần nữa theo chính sách lặp.

Trong một `TaskletStep` thông thường, mỗi lần thực thi tasklet diễn ra trong phạm vi transaction do step cấu hình. Nếu tasklet thực hiện một thao tác rất lớn trong **một lần execute**, transaction tương ứng có thể kéo dài; nếu tự chia việc thành nhiều lần `CONTINUABLE` thì ứng dụng phải quản lý tiến độ, tính idempotent và cách dừng/restart phù hợp.

**Tasklet không có bộ ba reader/processor/writer do framework điều phối.** Có thể viết vòng lặp trong tasklet, nhưng khi ấy bạn tự chịu trách nhiệm phần lớn những việc mà chunk-oriented step đã hỗ trợ sẵn.

## 3. Bảng so sánh để quyết định

| Tiêu chí | Chunk-oriented step | Tasklet step |
| --- | --- | --- |
| Đơn vị công việc | Một chuỗi item được đọc, biến đổi và ghi | Một hành động hoặc một khối nghiệp vụ do lập trình viên định nghĩa |
| Mô hình lập trình | `ItemReader` → `ItemProcessor` → `ItemWriter` | `Tasklet.execute(...)` |
| Transaction | Thường commit theo chunk | Thường theo mỗi lần gọi `execute` |
| Checkpoint/restart | Hạ tầng thuận tiện với `ItemStream`, reader/writer có state | Cần tự tổ chức state nếu hành động có nhiều giai đoạn |
| Skip item lỗi | Có cơ chế `skip` và `skipLimit` | Tự phân loại và quyết định lỗi trong logic |
| Retry item/operation | Hỗ trợ fault tolerance của chunk step | Có thể dùng retry ở service hoặc cơ chế riêng |
| Read/write/skip metrics | Bộ đếm chuẩn ở `StepExecution` | Không có các bộ đếm item tự phát sinh nếu không dùng cơ chế item |
| Xử lý dữ liệu lớn | Thích hợp với streaming, pagination, item-by-item | Phù hợp nếu hành động bounded hoặc xử lý set-based tại nguồn |
| Logic một lần | Làm được nhưng thường dư cấu trúc | Gọn, trực tiếp |
| Đọc file, parse, transform, ghi | Rất phù hợp | Thường phải tự viết vòng lặp/checkpoint |
| Quản lý file/move/rename | Có thể dùng, không bắt buộc | Thường phù hợp |
| Khả năng mở rộng song song | Có partitioning, multi-threaded chunk và các mô hình scaling | Tự thiết kế đồng thời nếu phải chia nhiều đơn vị |
| Chi phí thiết lập | Nhiều component hơn | Ít component hơn khi thao tác đơn giản |
| Rủi ro thiết kế sai | Transaction/restart/reader state | Vòng lặp quá dài, không checkpoint, tự xử lý retry và metric |

Từ bảng này có thể hình thành nguyên tắc:

> **Nếu step xử lý nhiều đơn vị độc lập, cần commit theo nhóm và cần theo dõi tiến độ từng item, ưu tiên chunk. Nếu step là một hành động có phạm vi rõ ràng, chạy xong là hoàn tất, ưu tiên tasklet.**

Quy tắc này có ngoại lệ. Một câu lệnh SQL set-based xử lý hàng triệu dòng vẫn có thể hợp với tasklet nếu database thực hiện trọn thao tác và kế hoạch transaction/lock được đánh giá. Ngược lại, việc tạo 20 file báo cáo độc lập có thể hợp với chunk nếu cần retry riêng từng file.

## 4. Cây quyết định thực tế

```text
Step cần làm gì?
    |
    +-- Một hành động hữu hạn?
    |      |  ví dụ: kiểm tra manifest, tạo thư mục, đánh dấu READY
    |      +--> TASKLET
    |
    +-- Duyệt nhiều phần tử/record?
           |
           +-- Mỗi phần tử có thể xử lý, bỏ qua, retry riêng?
           |      +--> CHUNK
           |
           +-- Cần checkpoint/tiếp tục sau chunk đã commit?
           |      +--> CHUNK
           |
           +-- Có thể ủy thác toàn bộ bằng một lệnh SQL/set-based?
                  |
                  +-- Transaction và lock nằm trong giới hạn cho phép?
                  |       +--> TASKLET có thể phù hợp
                  |
                  +-- Transaction quá lớn, cần chia việc và quan sát tiến độ?
                          +--> CHUNK hoặc chia việc có checkpoint rõ
```

Một số câu hỏi khi đánh giá step:

1. **Input có đơn vị rõ ràng không?** Record, object key, message, customer, invoice hay chỉ một “lệnh đóng sổ”?
2. **Từng đơn vị có outcome riêng không?** Có cần skip một dòng sai, retry một request lỗi, ghi quarantine hoặc thống kê số item?
3. **Một lần chạy có thể kéo dài bao lâu?** Nếu fail ở 99% tiến độ, có cần tiếp tục thay vì làm lại từ đầu?
4. **Transaction cần commit tại đâu?** Theo 100 item, theo một lệnh SQL hay sau toàn bộ lô?
5. **Output có side effect bên ngoài transaction không?** Gửi email, gọi API thanh toán, ghi object storage?
6. **Có kỳ vọng về scale và concurrency không?** Nhiều worker, partition, remote chunking?
7. **Có cần metrics dạng read/write/skip chuẩn không?** Hay chỉ cần outcome và duration của một hành động?

Sau khi trả lời, lựa chọn thường rõ ràng hơn nhiều so với việc đoán từ tên bước “import”, “cleanup” hoặc “sync”.

## 5. Khi tasklet là lựa chọn phù hợp

### 5.1. Preflight và validation cấp lô

Trước khi nhập CSV, job cần kiểm tra file tồn tại, có thể đọc, đúng schema và đã được upstream công bố. Đây là một thao tác giới hạn đầu vào/đầu ra:

```text
preflightStep:
  input  = location + source version
  output = pass hoặc failure có lý do
```

Không có lợi ích rõ ràng khi tạo `ItemReader` chỉ để “đọc một đối tượng file” rồi gửi qua writer. Một tasklet nhận resource, kiểm tra và kết thúc thường dễ hiểu hơn.

### 5.2. Các thao tác hạ tầng một lần

Ví dụ:

- Kiểm tra quyền truy cập vào nguồn trước khi chạy import.
- Tạo staging directory nếu contract cho phép.
- Kiểm tra marker `_SUCCESS` hoặc manifest.
- Xác nhận bảng staging đã được chuẩn bị.
- Chạy một câu lệnh `UPDATE` hoặc `DELETE` được giới hạn rõ phạm vi.
- Đánh dấu batch `READY_FOR_PUBLISH` khi quá trình đối soát đã đạt.

Các thao tác này có thể có side effect; vì vậy vẫn cần transaction hoặc idempotency phù hợp. **Tasklet gọn hơn không có nghĩa có thể bỏ qua recovery.**

### 5.3. Thực thi một operation tại nguồn

Giả sử database đã có dữ liệu staging; có thể dùng một câu SQL để cập nhật trạng thái các dòng hợp lệ:

```sql
UPDATE staging_orders
SET validation_status = 'READY'
WHERE source_id = :sourceId
  AND validation_status = 'NEW';
```

Một tasklet gọi câu SQL này có thể hợp lý nếu thao tác đủ ngắn, tính lại được và đã có chỉ mục/transaction thích hợp. Không nhất thiết phải đọc hàng triệu dòng từ database lên Java rồi cập nhật từng dòng chỉ để thực hiện một phép set-based.

Tuy nhiên, với bảng rất lớn, câu SQL có thể giữ lock lâu, phát sinh log/undo lớn hoặc vượt timeout. Cần xem xét kế hoạch query, batch size tại database và khả năng khôi phục; đôi khi chia thành nhiều đơn vị qua chunk lại tốt hơn.

## 6. Ví dụ tasklet thực tế bằng Spring Batch 5.x

Các ví dụ Java trong bài sử dụng **Java 17+, Spring Batch 5.x và Spring Framework 6/Spring Boot 3.x**. Hạ tầng `JobRepository`, `PlatformTransactionManager` và `DataSource` được giả định đã cấu hình. Spring Batch 6.x có thay đổi ở một số package/API, nên cần dùng đúng tài liệu phiên bản khi tích hợp.

### 6.1. Một tasklet kiểm tra input

Giả sử `inputPath` là đường dẫn nội bộ **đã được server phê duyệt** và chỉ trỏ đến thư mục staging của job:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
Tasklet validateInputTasklet(
        @Value("#{jobParameters['inputPath']}") String inputPath) {

    return (contribution, chunkContext) -> {
        Path input = Path.of(inputPath);

        if (!Files.isRegularFile(input)
                || !Files.isReadable(input)
                || Files.size(input) == 0) {
            throw new IllegalStateException(
                    "Input file is missing, empty or unreadable");
        }
        return RepeatStatus.FINISHED;
    };
}
```

Đây là ví dụ **validation tối thiểu**. Trong ứng dụng thực tế, hãy thêm kiểm tra schema/manifest và kiểm soát đường dẫn bên trong approved root; không nhận đường dẫn tùy ý từ caller để đọc bằng quyền của service account. `isReadable()` chỉ kiểm tra tại một thời điểm, cần xử lý lỗi mở thực tế và dùng snapshot nguồn ổn định.

`@StepScope` giúp tham số `inputPath` được resolve khi step chạy; bean không phụ thuộc vào một đường dẫn cứng lấy tại startup.

### 6.2. Cấu hình TaskletStep

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateInputTasklet, transactionManager)
            .build();
}
```

Khi `validateInputTasklet.execute(...)` trả `FINISHED`, step có thể hoàn tất. Khi nó ném exception, step thường kết thúc `FAILED` và flow tuần tự thông thường không chạy tiếp import step.

### 6.3. Tasklet cập nhật trạng thái bằng một SQL bounded

Một ví dụ khác: sau khi đối soát thành công, đánh dấu batch đã sẵn sàng:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
Tasklet markReadyTasklet(
        @Value("#{jobParameters['sourceId']}") String sourceId,
        JdbcTemplate jdbcTemplate) {

    return (contribution, chunkContext) -> {
        jdbcTemplate.update("""
            UPDATE import_control
            SET state = 'READY'
            WHERE source_id = ?
              AND state = 'VALIDATED'
            """, sourceId);

        return RepeatStatus.FINISHED;
    };
}
```

Giả định bảng `import_control` và `source_id` đã có, với trạng thái `VALIDATED` là điều kiện được phép chuyển. Một lần chạy lại không làm nhân đôi hiệu ứng nếu trạng thái đã là `READY`, nhưng cần quy định rõ khi số dòng update bằng 0: đã xử lý rồi, không có source hay vi phạm điều kiện? Nên ghi audit hoặc kiểm tra trạng thái cũ theo contract.

Nếu dùng cùng `DataSource` và transaction manager với `JdbcTemplate`, thay đổi JDBC có thể tham gia transaction của tasklet. Nếu tasklet gọi HTTP API hoặc ghi một file bên ngoài database, rollback JDBC **không tự hoàn tác** hiệu ứng đó.

## 7. Khi chunk là lựa chọn phù hợp

Chunk-oriented step đặc biệt hữu ích khi công việc có **nhiều item với vòng đời xử lý tương đối giống nhau**, và yêu cầu một hoặc nhiều đặc điểm:

- Streaming để không nạp toàn bộ dữ liệu vào bộ nhớ.
- Commit theo nhóm, tránh một transaction quá lớn.
- Restart từ checkpoint đã lưu.
- Skip record không hợp lệ trong giới hạn.
- Retry lỗi tạm thời ở reader/processor/writer theo chính sách.
- Theo dõi read/write/filter/skip counts.
- Scale bằng multi-thread, partitioning hoặc remote processing khi mô hình cho phép.

Ví dụ:

```text
orders.csv (500.000 records)
       |
       v
 FlatFileItemReader<OrderRow>
       |
       v
 ItemProcessor<OrderRow, OrderRow>
       |-- validate amount
       |-- normalize business key
       |-- return null nếu chủ động filter
       v
 JdbcBatchItemWriter<OrderRow>
       |
       v
    database, commit mỗi 500 item
```

Một chunk step không nhất thiết phải có processor: nếu chỉ đọc và ghi, có thể bỏ `ItemProcessor` và cấu hình trực tiếp reader/writer.

## 8. Ví dụ chunk: đọc CSV và ghi database

Giả sử input:

```csv
order_id,amount
ORD-001,100.00
ORD-002,150.50
ORD-003,75.00
```

Database:

```sql
CREATE TABLE imported_order (
    order_id VARCHAR(80) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
```

### 8.1. Model và reader

```java
import java.math.BigDecimal;

public record OrderRow(String orderId, BigDecimal amount) {}
```

```java
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputPath']}") String inputPath) {

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("orderCsvReader")
            .resource(new FileSystemResource(Path.of(inputPath)))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("order_id", "amount")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("order_id"),
                    fields.readBigDecimal("amount")
            ))
            .build();
}
```

Ví dụ giả định `inputPath` đã được xác thực theo nguồn được phép và input là CSV đơn giản với header đã kiểm tra. `FlatFileItemReader` sử dụng `ItemStream`/`ExecutionContext` để hỗ trợ restart khi được đặt tên ổn định, `saveState` phù hợp và dữ liệu nguồn không bị thay đổi.

### 8.2. Processor xác thực và chuẩn hóa

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
ItemProcessor<OrderRow, OrderRow> orderProcessor() {
    return item -> {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new IllegalArgumentException("order_id is required");
        }
        if (item.amount() == null
                || item.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }
        return new OrderRow(
                item.orderId().strip(),
                item.amount().setScale(2, RoundingMode.HALF_UP)
        );
    };
}
```

Không mặc định cấu hình `skip(IllegalArgumentException.class)` cho mọi trường hợp vì có thể che giấu bug; trong production nên định nghĩa exception riêng cho dữ liệu không hợp lệ và quyết định policy theo nghiệp vụ.

### 8.3. Writer JDBC theo lô

```java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<OrderRow> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderRow>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order(order_id, amount)
                VALUES (:orderId, :amount)
                """)
            .itemSqlParameterSourceProvider(row ->
                    new MapSqlParameterSource()
                            .addValue("orderId", row.orderId())
                            .addValue("amount", row.amount()))
            .build();
}
```

`JdbcBatchItemWriter` gửi nhiều statement parameters theo batch JDBC để giảm chi phí gọi database. Nếu `order_id` bị trùng, unique constraint có thể làm chunk fail và rollback theo database/transaction policy; khi cần import lặp lại phải thêm thiết kế idempotency/upsert phù hợp, không đơn giản bỏ constraint.

### 8.4. Tạo chunk Step

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, OrderRow> orderProcessor,
        JdbcBatchItemWriter<OrderRow> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Giá trị `500` chỉ là ví dụ, không phải kích thước chunk tối ưu mặc định. Hãy đo với kích thước item thực tế, latency database, lượng memory, thời gian transaction và mức độ rollback có thể chấp nhận.

## 9. Kết hợp tasklet và chunk trong một job

Trong nhiều ứng dụng, lựa chọn đúng là **mỗi step dùng mô hình phù hợp**, không cố áp dụng một loại step cho toàn bộ job.

```text
importOrdersJob
     |
     v
validateInputStep         Tasklet: file tồn tại, checksum/schema
     |
     v
importOrdersStep          Chunk: đọc từng đơn, validate, ghi DB
     |
     v
reconcileTotalsStep       Tasklet: so sánh control total
     |
     v
publishBatchStep          Tasklet: đánh dấu dữ liệu có thể sử dụng
```

Ví dụ cấu hình luồng:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importOrdersStep,
        Step reconcileTotalsStep,
        Step publishBatchStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateInputStep)
            .next(importOrdersStep)
            .next(reconcileTotalsStep)
            .next(publishBatchStep)
            .build();
}
```

`reconcileTotalsStep` và `publishBatchStep` trong ví dụ là các step do dự án tự định nghĩa, chưa có triển khai ở các đoạn code trước. Một flow tuần tự như trên chỉ đi tiếp khi step trước đạt điều kiện chuyển tiếp thành công theo flow.

Điểm đáng chú ý là không nên publish dữ liệu vào phạm vi sử dụng cuối cùng **trước khi quality gate đạt**. Nếu chunk import đã commit một phần, việc tasklet reconcile cuối thất bại không tự rollback mọi chunk trước đó. Có thể nhập vào staging rồi chỉ publish khi dữ liệu được kiểm chứng, hoặc thiết kế output trạng thái `PENDING/VALIDATED` để downstream không thấy lô chưa hoàn chỉnh.

## 10. Transaction: khác biệt thường quyết định kiến trúc

### 10.1. Chunk commit theo nhóm

Với `chunk(100)`, sau khi 100 item được đọc và xử lý thành công, writer ghi chúng trong transaction của chunk và commit. Nếu một chunk sau đó thất bại, dữ liệu chunk trước đã commit có thể vẫn còn.

```text
Chunk 1: 100 items -> COMMIT
Chunk 2: 100 items -> COMMIT
Chunk 3: item 251 lỗi -> ROLLBACK/FAILED
```

Điều này cho phép lưu tiến độ và giảm transaction size nhưng đặt yêu cầu **restart và xử lý lại an toàn**.

### 10.2. Tasklet một lời gọi có thể là transaction dài

Nếu tasklet viết:

```java
return (contribution, context) -> {
    for (OrderRow row : loadMillionRows()) {
        jdbcTemplate.update("UPDATE ...", /* parameters */);
    }
    return RepeatStatus.FINISHED;
};
```

thì toàn bộ vòng lặp có thể chạy trong **một lần execute và một transaction dài** (khi các thao tác JDBC tham gia transaction của tasklet). Hệ quả có thể là lock lâu, memory lớn, rollback tốn kém và không có checkpoint mức item được framework hỗ trợ. Đây là dấu hiệu nên chuyển sang chunk hoặc một chiến lược database set-based có transaction được kiểm soát.

### 10.3. Cùng một transaction manager chưa đủ cho nhiều hệ thống

Một chunk hoặc tasklet có thể gọi database và gửi message. Transaction JDBC không tự bao gồm HTTP API, filesystem hay message broker. Với hiệu ứng bên ngoài, cần:

- Idempotency key theo business key ổn định.
- Outbox hoặc mô hình đảm bảo phát hành sau commit phù hợp.
- Khả năng phát lại mà không nhân đôi kết quả.
- Phân loại timeout với trạng thái “không rõ đã thành công hay chưa”.

Chọn chunk chỉ giúp framework kiểm soát ranh giới xử lý item; nó không biến nhiều hệ thống thành một giao dịch ACID.

## 11. Restart và checkpoint: yếu tố quan trọng nhất với dữ liệu dài

### 11.1. Chunk và ItemStream

Các reader/writer có trạng thái có thể triển khai `ItemStream`:

```java
void open(ExecutionContext executionContext);
void update(ExecutionContext executionContext);
void close();
```

Spring Batch sử dụng `ExecutionContext` để lưu trạng thái checkpoint khi cần. Ví dụ `FlatFileItemReader` có thể lưu vị trí đọc được trong file sau các lần commit, giúp restart từ trạng thái phù hợp thay vì đọc toàn bộ từ đầu.

Để restart đáng tin cậy:

- Tên reader/step ổn định.
- `saveState` được cấu hình phù hợp.
- Nguồn input không thay đổi giữa các execution của cùng `JobInstance`.
- `JobRepository` được giữ lại.
- Writer không tạo duplicate nếu có item được phát lại.
- Processor tránh mutable state không được checkpoint hoặc có cơ chế lưu/khôi phục riêng.

**Không phải mọi ItemReader đều restart được** chỉ vì được dùng trong chunk. Reader tự viết phải tuân đúng contract của `ItemStream`/`ExecutionContext`; nguồn non-repeatable như message stream cần chiến lược riêng.

### 11.2. Tasklet và tiến độ tùy chỉnh

Tasklet đơn giản như kiểm tra một file hoặc đổi trạng thái một lần thường **không cần checkpoint bên trong**: nếu thất bại có thể gọi lại toàn bộ thao tác khi job restart, miễn là thao tác an toàn khi lặp lại.

Nếu tasklet xử lý hàng nghìn đơn vị, ứng dụng phải tự quản lý:

- Đơn vị đã xử lý đến đâu.
- Khi nào trạng thái được commit cùng output.
- Cách bỏ qua phần đã hoàn tất.
- Cách xử lý crash sau side effect nhưng trước khi ghi checkpoint.
- Cách kiểm tra dữ liệu đầu vào không đổi khi restart.

Nếu câu trả lời là “tôi tự lưu offset, tự retry, tự skip và tự tính count”, đó là tín hiệu mạnh cho thấy **chunk đã giải quyết phần lớn bài toán**.

### 11.3. Trạng thái của step đã completed

Trong một restart, các step `COMPLETED` thường được bỏ qua theo cấu hình mặc định, còn step chưa hoàn tất có thể chạy lại. Điều này đúng cho cả tasklet step và chunk step.

Ví dụ job:

```text
validateInputStep (Tasklet) COMPLETED
importOrdersStep  (Chunk)   FAILED
```

Khi restart cùng `JobInstance`, `validateInputStep` thường không cần chạy lại. Nếu muốn luôn kiểm tra quyền đọc/manifest lại, có thể cân nhắc `allowStartIfComplete(true)` cho preflight, nhưng phải biết kiểm tra đó có thể thay đổi kết quả và cần gắn với cùng snapshot đầu vào.

## 12. Retry, skip và filter: tại sao chunk thuận lợi hơn?

Giả sử file 100.000 dòng có 10 dòng lỗi định dạng nghiệp vụ và đôi lúc database bị deadlock.

Với chunk, có thể cấu hình:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, OrderRow>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderDataException.class)
        .skipLimit(20)
        .retry(TransientDatabaseException.class)
        .retryLimit(3)
        .build();
```

`InvalidOrderDataException` và `TransientDatabaseException` trong ví dụ là exception do ứng dụng định nghĩa hoặc adapter phân loại; cần tạo class và ánh xạ lỗi cụ thể trước khi dùng. Không nên skip/retry mọi `Exception` vì dễ che bug hoặc retry lỗi không thể phục hồi.

Chunk-oriented step có:

- `filterCount` khi processor trả `null`.
- `processSkipCount` khi một item được skip tại processor.
- `readSkipCount`, `writeSkipCount` khi lỗi được skip ở reader/writer.
- `rollbackCount` khi transaction rollback.
- `SkipListener` để ghi audit về item bị bỏ qua.

Với tasklet, có thể viết logic bắt exception, thử lại hoặc ghi quarantine, nhưng `StepExecution` không tự sinh những bộ đếm item như chunk nếu không có cơ chế lập trình thêm.

**Không nhầm retry với đúng-một-lần.** Chunk retry có thể làm processor/writer được gọi lại. Với API hoặc filesystem, phải bảo đảm side effect idempotent dù model là chunk hay tasklet.

## 13. Hiệu năng: có phải chunk luôn nhanh hơn?

Không. Hiệu năng phụ thuộc loại thao tác và chi phí I/O.

### 13.1. Khi chunk giảm chi phí

Với JDBC insert, writer có thể gửi nhiều item trong một batch, giúp giảm số round-trip và số lần commit so với việc commit từng item riêng. Với file lớn, reader theo luồng giúp memory ổn định hơn đọc cả file vào một `List`.

Chunk size quá nhỏ:

- Tăng số transaction/commit.
- Tăng overhead framework và database.
- Làm throughput giảm với thao tác ghi có latency.

Chunk size quá lớn:

- Giữ nhiều item trong memory.
- Có thể làm transaction dài và khóa lâu.
- Khi rollback phải xử lý lại nhiều việc hơn.
- Tăng thời gian chờ commit và áp lực tài nguyên.

Nên đánh giá chunk size bằng throughput, transaction latency, memory, rollback/retry, tốc độ writer và khả năng chịu tải của downstream.

### 13.2. Khi tasklet hiệu quả hơn

Một lệnh SQL:

```sql
UPDATE orders
SET archive_flag = true
WHERE business_date < :cutoff
  AND archive_flag = false;
```

được database thực hiện set-based có thể hiệu quả hơn việc Java đọc từng order rồi update. Nhưng nếu số bản ghi bị ảnh hưởng rất lớn hoặc việc giữ lock lâu không được phép, cần chia thành nhiều batch/tranche với kế hoạch checkpoint/commit tương ứng.

Khi tác vụ chỉ kiểm tra một file bằng một phép mở stream hoặc gọi một stored procedure đã quản lý transaction, tạo một chunk step chỉ để xử lý đúng một item thường làm cấu trúc phức tạp không cần thiết.

### 13.3. Chi phí vận hành cũng là hiệu năng

Một tasklet viết nhanh bằng một vòng lặp lớn có thể tiết kiệm vài chục dòng code, nhưng làm mất khả năng restart sau 90% tiến độ, tăng thời gian khắc phục sự cố. Với batch quan trọng, **thời gian recovery** là một phần của hiệu năng hệ thống, không chỉ throughput trong trường hợp thành công.

## 14. Scaling và concurrency

Chunk step có các mô hình hỗ trợ phân chia công việc:

- Multi-threaded step với `TaskExecutor` khi reader/writer và nguồn dữ liệu hỗ trợ concurrency đúng cách.
- Partitioning: phân chia dữ liệu thành các partition, mỗi partition có `StepExecution` và phạm vi input riêng.
- Remote chunking hoặc mô hình remote processing cho hệ thống phân tán, tùy kiến trúc/phiên bản.

Không mặc định bật multi-thread là an toàn: `FlatFileItemReader` và nhiều reader có state thường không phải thread-safe nếu dùng chung. Khi cần throughput, có thể chia input thành partition riêng và mỗi worker sở hữu reader độc lập.

Tasklet cũng có thể chạy thread pool hoặc chia nhỏ công việc, nhưng khi đó ứng dụng tự quản lý phân phối work, checkpoint, trạng thái từng phần, retry và cancel. Nếu công việc tự nhiên là nhiều item độc lập, chunk/partition thường rõ ràng hơn.

**Cảnh báo về số lượng worker:** tăng concurrency có thể tạo contention, saturate connection pool hoặc gây rate limit ở API ngoài. Việc chọn chunk/tasklet không thay thế capacity planning.

## 15. Logging và monitoring theo từng mô hình

| Thông tin | Chunk-oriented step | Tasklet step |
| --- | --- | --- |
| `JobExecution` / `StepExecution` status | Có | Có |
| Bắt đầu/kết thúc step, duration | Có | Có |
| `readCount` / `writeCount` | Theo semantics của item processing | Thường không phản ánh số record nghiệp vụ nếu thao tác không qua reader/writer |
| `filterCount` / skip counts | Có thể có | Không tự sinh theo từng item |
| Chunk commit/rollback | Framework theo dõi | Không tương ứng trực tiếp với số task “con” |
| Số record SQL bị ảnh hưởng | Cần query writer/DB nếu muốn chính xác | Cần dùng row count từ operation và audit |
| Retry attempts | Cần instrumentation khi muốn đếm chi tiết | Tự instrumentation trong service/policy |

Ví dụ `JdbcBatchItemWriter` nhận 500 item nhưng dùng upsert để bỏ qua 20 duplicate; `writeCount` có thể vẫn phản ánh 500 item mà writer được framework ghi, không phải số row database mới được thêm. Với tasklet chạy `UPDATE` 1.000 row, `StepExecution.writeCount` không tự thành 1.000 vì không có `ItemWriter`.

Vì vậy, định nghĩa metric theo đúng ý nghĩa:

```text
job_execution_status
step_execution_status
chunk_read_count / chunk_write_count
business_records_inserted
business_records_updated
tasklet_operation_duration
validation_failure_reason
```

Các tên trên chỉ mang tính khái niệm; metric xuất qua Micrometer/Prometheus có tên/tag thực tế phụ thuộc cấu hình và phiên bản framework. Không dùng `jobExecutionId` hay `stepExecutionId` làm metric label cardinality cao; giữ chúng ở log hoặc trace.

## 16. Các tình huống thiết kế nên cân nhắc

| Bài toán | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Kiểm tra file đầu vào có thể đọc | Tasklet | Một thao tác preflight hữu hạn |
| Validate header, checksum trước nhập | Tasklet | Kiểm tra ở cấp nguồn/lô |
| Đọc CSV lớn và import từng đơn | Chunk | Có item, commit, skip/retry, restart |
| Đọc bảng và chuyển đổi từng customer | Chunk | Cần xử lý theo record |
| Xóa một bảng staging nhỏ có điều kiện | Tasklet | Một lệnh SQL rõ scope |
| Ghi một câu SQL set-based cập nhật cả kỳ | Tasklet có điều kiện | DB xử lý trực tiếp; cần xét transaction/lock |
| Gửi 100.000 email giao dịch | Chunk hoặc hàng đợi chuyên dụng | Nhiều item, retry riêng, idempotency |
| Gửi một thông báo “kỳ đã đóng” | Tasklet | Một hành động bounded, cần idempotent |
| Di chuyển một file sau khi hoàn tất | Tasklet | Operation trên một resource |
| Di chuyển 50.000 object độc lập | Chunk | Theo dõi/retry/checkpoint từng object |
| Đối soát tổng tiền kỳ | Tasklet hoặc step truy vấn tổng hợp | Một kết quả aggregate nếu data đã staging |
| Tính tổng bằng cách parse mọi record và lưu từng kết quả | Chunk | Dữ liệu có item và cần kiểm soát processing |
| Chờ file xuất hiện bằng vòng lặp vô hạn | Thường chuyển sang scheduler/orchestrator | Tránh giữ worker/transaction và che lỗi upstream |
| Gọi một stored procedure được thiết kế cho cả batch | Tasklet có điều kiện | Một operation có contract transaction và recovery |
| Nạp API phân trang và ghi từng bản ghi | Chunk nếu có cursor/reader phù hợp | Retry, page checkpoint, output item |
| Cleanup 1.000.000 bản ghi theo batch | Phụ thuộc chiến lược | SQL set-based có thể nhanh, nhưng chunk hữu ích nếu cần chia commit |

### Ví dụ 1: “Gửi báo cáo”

Nếu yêu cầu là **tạo một file PDF tổng hợp từ dữ liệu đã truy vấn**, một tasklet tạo file đầu ra có thể đủ, nhưng cần xử lý file tạm, atomic publish và retry. Nếu yêu cầu là **tạo 100.000 báo cáo PDF riêng cho từng khách hàng**, mỗi báo cáo là một item, nên cân nhắc chunk và idempotency per customer.

### Ví dụ 2: “Đồng bộ dữ liệu”

Nếu đồng bộ là một lệnh database `MERGE` với điều kiện rõ, tasklet hợp lý. Nếu đồng bộ cần gọi API cho từng customer, xử lý HTTP 429 và ghi trạng thái riêng từng customer, chunk thường hữu ích hơn. Cùng từ “sync” nhưng ranh giới công việc khác nhau.

### Ví dụ 3: “Xóa dữ liệu cũ”

Một `DELETE WHERE created_at < cutoff` trên bảng nhỏ có thể thực hiện ở tasklet. Với bảng lớn hàng trăm triệu dòng, cần xét partition, kích thước transaction, index và lịch chạy; có thể chọn database partition management hoặc chunk hóa các khóa cần xóa. Không có quy tắc rằng tasklet luôn dành cho ít dòng.

## 17. Những thiết kế dễ gặp vấn đề

### 17.1. Tasklet chứa vòng lặp đọc, xử lý và ghi hàng triệu item

```java
public RepeatStatus execute(
        StepContribution contribution, ChunkContext context) {
    while (hasNext()) {
        var item = read();
        var mapped = process(item);
        write(mapped);
    }
    return RepeatStatus.FINISHED;
}
```

Đoạn này thực chất tự tái tạo chunk processing nhưng thường thiếu checkpoint, commit interval, skip/retry và metrics chuẩn. Nếu mục đích là xử lý một luồng item, hãy tách thành reader/processor/writer và dùng chunk.

### 17.2. Chunk với một reader giả chỉ phát ra một phần tử

Nếu yêu cầu là xóa một file đã xử lý, tạo reader phát một item `"delete-this-file"` rồi writer xóa file có thể chạy được, nhưng làm luồng khó đọc hơn tasklet với một hành động rõ ràng. Không nên tạo abstraction item chỉ để dùng chunk bằng mọi giá.

### 17.3. Dùng tasklet để chờ dữ liệu mãi mãi

```java
while (!Files.exists(input)) {
    Thread.sleep(1000);
}
```

Kiểu chờ này có thể giữ transaction/thread lâu, không có deadline và khiến job treo thay vì báo tình trạng upstream. Dùng scheduler, event-driven trigger, ready marker và cơ chế retry/backoff có giới hạn ngoài transaction khi phù hợp.

### 17.4. Giả định tasklet tự động restart từ giữa vòng lặp

Một tasklet không tự biết “đã xử lý đến item thứ 50.000”. Muốn tiếp tục phải quản lý checkpoint và idempotency riêng; đó là một trong các lý do nên dùng chunk cho dữ liệu nhiều item.

### 17.5. Xóa metadata Spring Batch để chạy lại

Khi chunk đã commit một phần, xóa `BATCH_JOB_EXECUTION`/`BATCH_STEP_EXECUTION` có thể khiến logic restart/checkpoint mất tác dụng. Tasklet đã có side effect cũng có nguy cơ chạy lại. Phải tách **restart cùng instance**, **rerun tạo instance mới** và **reprocess một phiên bản dữ liệu khác**.

### 17.6. Tasklet thực hiện thao tác không idempotent

Ví dụ tasklet gửi một lệnh “thanh toán ngay” rồi sau đó process crash trước khi metadata được đánh dấu thành công. Khi restart, thao tác có thể được gọi lại. Nếu side effect không thể rollback, cần idempotency key hoặc orchestration giao dịch phù hợp.

### 17.7. Dùng chunk để tạo một transaction “all-or-nothing” toàn job

Chunk commit từng nhóm. Nếu yêu cầu dữ liệu cuối cùng chỉ xuất hiện khi **toàn lô đạt chất lượng**, cần staging và bước publish sau validation. Không thể giả định một job `FAILED` sẽ rollback tất cả các chunk đã commit.

## 18. Kiểm thử quyết định thiết kế

Lựa chọn mô hình cần được xác nhận bằng hành vi khi có failure, không chỉ bằng việc job chạy happy path.

### 18.1. Test tasklet preflight

Với tasklet `validateInputTasklet`:

1. Tạo file hợp lệ trong thư mục test → tasklet trả `FINISHED`.
2. Tạo file rỗng hoặc đường dẫn thiếu → tasklet ném exception.
3. Dùng integration test gồm preflight step và import step → khi preflight `FAILED`, import step không chạy.
4. Chạy lại sau khi nguồn hợp lệ → xác minh không có side effect đã tạo từ lần thất bại.

Với Spring Batch 5.x, `spring-batch-test` cung cấp `@SpringBatchTest` và `JobLauncherTestUtils` cho integration test. Tasklet có thể được unit test trực tiếp bằng mock `StepContribution` và `ChunkContext` nếu logic chỉ cần hai đối tượng ấy; nếu không cần dùng chúng, có thể đưa validation vào service riêng để test dễ hơn.

### 18.2. Test chunk với failure giữa hai lần commit

Với file 250 item và `chunk(100)`:

1. Reader đọc 250 item, processor biến đổi, writer ghi DB.
2. Chủ động cho item thứ 150 gặp lỗi không được skip.
3. Xác minh step thất bại, kiểm tra dữ liệu đã commit theo transaction policy.
4. Sửa nguyên nhân failure nhưng giữ input snapshot và `JobRepository`.
5. Restart cùng `JobInstance`, xác minh đủ 250 record nghiệp vụ, không trùng và không mất.

Không mặc định số dòng đang có sau lần failure bằng 100 trong mọi cấu hình: đọc/writer có thể có behavior đặc biệt, transaction manager khác hoặc side effect ngoài transaction. Quan sát database thực tế cùng metadata `StepExecution` để khẳng định.

### 18.3. Test skip và retry trong chunk

Kịch bản:

```text
Input 5 item:
  A valid
  B valid
  C invalid -> skippable
  D dependency timeout lần đầu, lần sau OK
  E valid
```

Khi chính sách skip/retry cho phép, kết quả nghiệp vụ mong đợi là 4 item hợp lệ được xử lý, `processSkipCount=1` nếu lỗi ở processor, và không có duplicate output do retry. Các bộ đếm khác phụ thuộc implementation và transaction policy.

### 18.4. Ví dụ assertion trong integration test

```java
JobExecution execution = launcher.launchJob(
        new JobParametersBuilder()
                .addString("inputPath", approvedInput.toString())
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters()
);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution importStep = execution.getStepExecutions().stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(3, importStep.getReadCount());
assertEquals(3, importStep.getWriteCount());
assertEquals(3, countImportedOrdersFromDatabase());
```

Đây là đoạn minh họa trong một test có sẵn launcher, `approvedInput`, `countImportedOrdersFromDatabase()`, các import JUnit và context đã cấu hình. Mục tiêu là assert cả **metadata** lẫn **kết quả thực tế**. Khi dùng file fixture có số record khác hoặc logic filter, thay kỳ vọng tương ứng.

### 18.5. Test restart một tasklet có side effect

Nếu tasklet đổi trạng thái bằng SQL:

- Gây lỗi sau khi thao tác đã commit hoặc giả lập crash tại một điểm có thể xảy ra thực tế.
- Restart đúng instance hoặc chạy lại theo chính sách của hệ thống.
- Kiểm tra update có điều kiện không thực hiện lại hiệu ứng không phù hợp.
- Nếu gọi hệ thống ngoài, kiểm tra idempotency tại phía nhận.

Tasklet “chỉ chạy một lần” theo mong muốn không tự bảo đảm exactly-once khi process crash và trạng thái phân tán chưa nhất quán.

## 19. Khuôn mẫu quyết định cho một thiết kế mới

Trước khi tạo step, có thể điền bảng sau trong tài liệu thiết kế:

| Câu hỏi | Ví dụ câu trả lời |
| --- | --- |
| Business operation là gì? | Nhập các đơn hàng từ một CSV đã xác thực |
| Đơn vị có thể đếm là gì? | Một record đơn hàng |
| Số lượng/khối lượng dự kiến? | 500.000 record mỗi đêm |
| Mất bao lâu nếu phải chạy lại từ đầu? | Khoảng 45 phút |
| Boundary transaction phù hợp? | 500 record mỗi commit |
| Có cần skip/retry riêng từng item? | Có, validation và lỗi transient |
| Có cần restart/checkpoint? | Có, tiếp tục từ chunk đã commit |
| Output có side effect không? | JDBC insert có unique key |
| Cần metric nào? | read, write, skip, duration, số order mới |
| Kết luận | **Chunk-oriented step** |

Nếu câu trả lời là “kiểm tra một manifest”, “không có tập item”, “hoàn tất dưới vài giây”, “có thể lặp lại an toàn” và “chỉ cần pass/fail”, kết luận thường là **Tasklet step**.

Hãy ghi cả **lý do và giả định** thay vì chỉ ghi nhãn. Khi số lượng dữ liệu, SLA hoặc kiến trúc input thay đổi, bảng này giúp nhóm biết thời điểm nên điều chỉnh từ tasklet sang chunk hoặc ngược lại.

## 20. Bài thực hành

**Bài 1 — Chọn mô hình.** Phân loại các yêu cầu: xác minh checksum của một file; đọc 200.000 hóa đơn; tạo một directory; xóa 100.000 tài khoản theo danh sách; chạy một SQL aggregate; gửi 2.000 email. Giải thích theo transaction, item-level recovery và khả năng restart.

**Bài 2 — Tạo TaskletStep.** Viết `validateInputStep` kiểm tra file có thể đọc và không rỗng. Khi file không hợp lệ, assert step `FAILED` và bước import phía sau không chạy.

**Bài 3 — Tạo ChunkStep.** Viết `FlatFileItemReader`, `ItemProcessor` và `JdbcBatchItemWriter` để nạp CSV vào bảng có unique key. Chạy với các giá trị chunk size khác nhau và so sánh throughput/commit count.

**Bài 4 — Test restart.** Cho chunk đầu commit, chunk sau thất bại. Giữ nguyên database metadata và source; restart cùng instance rồi kiểm tra không có bản ghi trùng.

**Bài 5 — Retry và skip.** Thêm một record invalid và một lỗi database tạm thời. Dùng exception cụ thể để cấu hình skip/retry; kiểm tra output, `processSkipCount` và trạng thái job.

**Bài 6 — Tasklet có side effect.** Tạo tasklet đổi trạng thái lô từ `VALIDATED` sang `READY`. Thực hiện lại tasklet và chứng minh thao tác có điều kiện không làm phát sinh hiệu ứng ngoài mong đợi.

**Bài 7 — Job kết hợp.** Xây flow `preflightTasklet → importChunk → reconcileTasklet → publishTasklet`. Khi reconciliation thất bại, xác minh dữ liệu chưa được công bố cho downstream dù chunk import đã commit vào staging.

**Bài 8 — Quyết định theo số liệu.** Với 1 triệu record, đo thời gian writer/transaction, thời gian rollback và memory ở chunk size 100, 500 và 1.000. Dựa trên giới hạn tài nguyên và yêu cầu recovery để chọn size hợp lý.

## 21. Kết luận

**Chunk** phù hợp với luồng nhiều item cần streaming, commit theo nhóm, skip/retry, metrics và khả năng restart từ checkpoint. **Tasklet** phù hợp với một thao tác có phạm vi rõ ràng như preflight, kiểm tra manifest, đánh dấu trạng thái, chuyển file hoặc gọi một lệnh SQL có thể kiểm soát.

Sự lựa chọn không phải giữa “công nghệ mạnh” và “công nghệ đơn giản”, mà giữa **hai cách phân chia và quản lý đơn vị công việc**. Một job thực tế thường kết hợp chúng: tasklet chuẩn bị/đối soát/publish, còn chunk xử lý các record nghiệp vụ. Khi xác định rõ transaction, idempotency, restart và trạng thái dữ liệu ở từng step, thiết kế sẽ dễ kiểm thử, vận hành và mở rộng hơn.

### Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html)
- [Spring Batch Reference — ItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-reader.html)
- [Spring Batch Reference — ItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-writer.html)
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch Reference — ExecutionContext](https://docs.spring.io/spring-batch/reference/common-patterns.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
