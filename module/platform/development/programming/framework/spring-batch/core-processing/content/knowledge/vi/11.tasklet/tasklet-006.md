# Tasklet xử lý file hoặc gọi thủ tục

Trong Spring Batch, `Tasklet` phù hợp với một tác vụ batch có đơn vị công việc tương đối rõ ràng, chẳng hạn kiểm tra hoặc di chuyển một file, tạo file đánh dấu, dọn dữ liệu tạm hay gọi stored procedure trong cơ sở dữ liệu. Thay vì đọc từng item qua `ItemReader`, xử lý qua `ItemProcessor` rồi ghi theo chunk, Tasklet thực hiện công việc trong phương thức `execute()`.

Một Step dùng Tasklet được quản lý bởi `TaskletStep`. Spring Batch gọi `execute()` và dựa vào `RepeatStatus` để biết tác vụ đã hoàn tất hay cần được gọi tiếp. Tasklet thường trả về `RepeatStatus.FINISHED` khi công việc xong. Nếu cần tiếp tục lặp, có thể trả về `RepeatStatus.CONTINUABLE`.

## 1. Tasklet là gì?

`Tasklet` là một interface đơn giản trong Spring Batch, định nghĩa một thao tác thực thi:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

Hai đối tượng được truyền vào có vai trò khác nhau:

- `StepContribution` cho phép Tasklet cập nhật các contribution của Step, chẳng hạn số bản ghi đọc hoặc ghi và `ExitStatus`.
- `ChunkContext` cung cấp ngữ cảnh của lần thực thi chunk/tasklet hiện tại, bao gồm `StepContext` và các thuộc tính liên quan.

Tasklet không bắt buộc phải xử lý dữ liệu theo từng item. Nó có thể thực hiện một thao tác tổng thể như gọi thủ tục tính toán trong database hoặc chuyển một file đầu vào sang thư mục lưu trữ.

### Tasklet và chunk processing khác nhau thế nào?

| Tiêu chí | Tasklet | Chunk-oriented processing |
|---|---|---|
| Đơn vị xử lý | Một tác vụ hoặc một lần thực thi logic | Một nhóm item theo commit interval |
| Thành phần chính | `Tasklet.execute()` | `ItemReader`, `ItemProcessor`, `ItemWriter` |
| Phù hợp với | Gọi stored procedure, kiểm tra file, dọn dữ liệu, thao tác tổng thể | Đọc và xử lý nhiều bản ghi theo từng nhóm |
| Kiểm soát transaction | Transaction manager của TaskletStep | Transaction theo từng chunk |
| Theo dõi số lượng item | Tasklet tự cập nhật contribution nếu cần | Spring Batch cập nhật các bộ đếm đọc, xử lý và ghi |

Nếu yêu cầu là gọi một thủ tục database để tổng hợp một kỳ dữ liệu, Tasklet thường đơn giản và dễ hiểu. Nếu cần đọc hàng triệu dòng, validate từng dòng và ghi theo lô, chunk processing thường phù hợp hơn.

## 2. RepeatStatus và vòng đời của Tasklet

`execute()` trả về `RepeatStatus` để điều khiển việc lặp:

- `RepeatStatus.FINISHED`: tác vụ đã hoàn tất; Step có thể kết thúc bình thường.
- `RepeatStatus.CONTINUABLE`: Tasklet cần được gọi tiếp trong cùng Step.

Luồng tổng quát:

```text
TaskletStep bắt đầu
       |
       v
Gọi Tasklet.execute()
       |
       +----> FINISHED ------> Step hoàn tất
       |
       +----> CONTINUABLE --> Gọi execute() tiếp
       |
       +----> Exception ----> Step thất bại / xử lý theo policy
```

Với Tasklet thực hiện một thao tác như move file hoặc gọi stored procedure một lần, thông thường trả về `FINISHED`. Chỉ dùng `CONTINUABLE` khi có lý do rõ ràng để chia tác vụ thành nhiều lần gọi, ví dụ xử lý từng phần của một tác vụ dài hoặc kiểm tra trạng thái của một tiến trình bất đồng bộ.

TaskletStep quản lý transaction thông qua `PlatformTransactionManager` được cung cấp khi khai báo Step. Mỗi lần gọi Tasklet được thực hiện trong transaction do Step quản lý. Tuy nhiên, transaction chỉ bao phủ những tài nguyên tham gia vào transaction đó; thao tác file hệ thống hoặc dịch vụ HTTP không tự động trở thành transactional.

## 3. Khai báo một Tasklet Step

Với Spring Batch 5 trở lên, có thể tạo Step bằng `StepBuilder` và cung cấp Tasklet cùng transaction manager:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MaintenanceJobConfig {

    @Bean
    public Step cleanupStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet cleanupTasklet) {

        return new StepBuilder("cleanupStep", jobRepository)
                .tasklet(cleanupTasklet, transactionManager)
                .build();
    }
}
```

`JobRepository` lưu metadata của Job và Step; `PlatformTransactionManager` quản lý transaction cho TaskletStep. Tasklet có thể được khai báo thành bean riêng hoặc viết trực tiếp bằng lambda nếu logic ngắn.

Ví dụ lambda đơn giản:

```java
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

@Bean
public Tasklet logStartTasklet() {
    return (contribution, chunkContext) -> {
        System.out.println("Starting maintenance task");
        return RepeatStatus.FINISHED;
    };
}
```

Khi logic có nhiều nhánh, phụ thuộc hoặc cần kiểm thử riêng, nên tách thành một class triển khai `Tasklet` hoặc một bean có phương thức tạo Tasklet để cấu hình dễ đọc hơn.

## 4. Ví dụ Tasklet kiểm tra và di chuyển file

Một tác vụ thường gặp là chuyển file đã nhập thành công từ thư mục `incoming` sang thư mục `archive`. File path nên được truyền bằng JobParameters để cùng một Job có thể xử lý nhiều file mà không cần thay đổi mã nguồn.

Ví dụ chạy Job:

```bash
java -jar batch-app.jar \
    --spring.batch.job.name=archiveInputJob \
    inputFile=/data/incoming/orders-2026-11-15.csv \
    archiveDir=/data/archive
```

Tasklet lấy các giá trị từ JobParameters thông qua `@StepScope`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ArchiveFileTaskletConfig {

    @Bean
    @StepScope
    public Tasklet archiveFileTasklet(
            @Value("#{jobParameters['inputFile']}") String inputFile,
            @Value("#{jobParameters['archiveDir']}") String archiveDir) {

        return (contribution, chunkContext) -> {
            Path source = Path.of(inputFile);
            Path target = Path.of(archiveDir).resolve(source.getFileName());

            if (Files.exists(target) && !Files.exists(source)) {
                // Lần chạy trước có thể đã move file trước khi ứng dụng dừng.
                return RepeatStatus.FINISHED;
            }

            if (!Files.isRegularFile(source)) {
                throw new IllegalStateException(
                        "Input file does not exist: " + source);
            }

            if (Files.exists(target)) {
                throw new IllegalStateException(
                        "Archive target already exists: " + target);
            }

            Files.createDirectories(target.getParent());
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);

            return RepeatStatus.FINISHED;
        };
    }
}
```

Đoạn code giả định file nguồn và thư mục archive nằm trên cùng filesystem để hỗ trợ `ATOMIC_MOVE`. Nếu hệ thống file không hỗ trợ thao tác atomic hoặc hai đường dẫn thuộc filesystem khác nhau, cần chọn chiến lược copy, xác minh nội dung rồi xóa nguồn phù hợp với môi trường triển khai.

### Vì sao ví dụ cần kiểm tra file đích?

Thao tác di chuyển file không tham gia transaction database của Spring Batch. Có thể xảy ra tình huống file đã được chuyển thành công nhưng transaction hoặc tiến trình dừng trước khi Step ghi nhận hoàn tất. Khi restart, file nguồn không còn nhưng file đích đã tồn tại.

Ví dụ kiểm tra `target` tồn tại và `source` không còn giúp nhận diện trường hợp thao tác move đã hoàn thành trước đó. Nếu cả hai cùng tồn tại, Tasklet dừng với lỗi để tránh ghi đè file archive. Trong hệ thống thực tế, nên xác nhận thêm checksum, kích thước hoặc mã file để chắc chắn file đích đúng là file của lần xử lý này.

Nếu file đích có thể tồn tại từ một lần nhập khác, chỉ kiểm tra tên file là chưa đủ. Có thể lưu mã lô hoặc checksum trong metadata/database và dùng nó làm khóa idempotency.

## 5. Ví dụ Tasklet gọi stored procedure

Một Tasklet khác có thể gọi stored procedure để thực hiện phép tính hoặc cập nhật dữ liệu ngay trong database. Đây là lựa chọn phù hợp khi phần lớn logic đã được triển khai trong thủ tục SQL và Job chỉ cần kích hoạt nó với các tham số đầu vào.

Giả sử database có stored procedure `process_daily_sales` nhận ngày nghiệp vụ và trả về số lượng bản ghi đã xử lý. Có thể dùng `SimpleJdbcCall`:

```java
import java.sql.Date;
import java.sql.Types;
import java.time.LocalDate;
import java.util.Map;

import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration
public class DailySalesProcedureTaskletConfig {

    @Bean
    @StepScope
    public Tasklet processDailySalesTasklet(
            JdbcTemplate jdbcTemplate,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        SimpleJdbcCall procedure = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("process_daily_sales")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_business_date", Types.DATE),
                        new SqlOutParameter("p_processed_count", Types.INTEGER));

        return (contribution, chunkContext) -> {
            LocalDate date = LocalDate.parse(businessDate);
            Map<String, Object> result = procedure.execute(
                    new MapSqlParameterSource()
                            .addValue("p_business_date", Date.valueOf(date)));

            Number processedCount =
                    (Number) result.get("p_processed_count");
            if (processedCount == null || processedCount.intValue() < 0) {
                throw new IllegalStateException(
                        "Stored procedure returned an invalid processed count");
            }

            contribution.incrementWriteCount(processedCount.intValue());
            return RepeatStatus.FINISHED;
        };
    }
}
```

Các tên procedure, tên tham số và kiểu SQL trong ví dụ cần được điều chỉnh theo database đang sử dụng. `withoutProcedureColumnMetaDataAccess()` yêu cầu khai báo rõ tham số vào/ra; điều này hữu ích khi metadata procedure của database không được phát hiện tự động hoặc muốn kiểm soát mapping tường minh.

`JdbcTemplate` dùng `DataSource` đã được cấu hình trong Spring. Nếu `JdbcTemplate` và TaskletStep dùng cùng DataSource cùng transaction manager, lời gọi stored procedure thường tham gia transaction hiện tại. Khi procedure ném lỗi SQL, exception được truyền ra ngoài Tasklet và Step có thể rollback transaction.

### Lưu ý về transaction của stored procedure

Không phải stored procedure nào cũng tuân thủ transaction do Spring quản lý. Một số procedure có thể tự `COMMIT`, `ROLLBACK`, dùng autonomous transaction hoặc gọi hệ thống bên ngoài. Khi đó, transaction rollback ở phía Spring không nhất thiết hoàn tác được toàn bộ thay đổi của procedure.

Trước khi dùng Tasklet gọi procedure, cần xác định:

- Procedure có tự commit hay tự rollback không?
- Procedure chạy trên cùng DataSource và transaction manager với Step không?
- Procedure có gọi database khác hoặc dịch vụ ngoài không?
- Nếu Job restart và procedure được gọi lại, dữ liệu có bị cập nhật hoặc ghi trùng không?
- Procedure có thể nhận một mã batch để nhận diện lần xử lý không?

Nên thiết kế procedure có tính idempotent hoặc có bảng kiểm soát trạng thái theo ngày/lô xử lý. Nếu procedure đã commit độc lập trước khi Tasklet thất bại, restart có thể gọi procedure thêm lần nữa.

## 6. Khai báo Step và Job cho Tasklet

Tasklet được gắn vào Step bằng `.tasklet(tasklet, transactionManager)`. Có thể tổ chức nhiều Tasklet Step trong cùng một Job, ví dụ kiểm tra file, gọi thủ tục nhập dữ liệu rồi archive file:

```java
@Configuration
public class ImportFileJobConfig {

    @Bean
    public Step processFileStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet processFileTasklet) {
        return new StepBuilder("processFileStep", jobRepository)
                .tasklet(processFileTasklet, transactionManager)
                .build();
    }

    @Bean
    public Job importFileJob(
            JobRepository jobRepository,
            Step processFileStep) {
        return new JobBuilder("importFileJob", jobRepository)
                .start(processFileStep)
                .build();
    }
}
```

Các import và bean dependency được lược bớt trong ví dụ này để tập trung vào cách kết hợp Step và Job. `processFileTasklet` phải là bean Tasklet đã được khai báo; nếu Job có nhiều Step, có thể nối chúng bằng `.next(...)` hoặc cấu hình flow theo kết quả thoát.

## 7. Tasklet có thể được gọi nhiều lần

Mặc dù Tasklet thường thực hiện một thao tác, Spring Batch có thể gọi `execute()` nhiều lần nếu Tasklet trả về `RepeatStatus.CONTINUABLE`.

Ví dụ Tasklet kiểm tra trạng thái của một tác vụ ngoài và tiếp tục chờ nếu chưa hoàn tất:

```java
@Bean
public Tasklet checkExternalTaskTasklet(ExternalTaskService service) {
    return (contribution, chunkContext) -> {
        boolean completed = service.isCompleted();
        if (completed) {
            return RepeatStatus.FINISHED;
        }
        return RepeatStatus.CONTINUABLE;
    };
}
```

Ví dụ trên chỉ minh họa ý nghĩa của `CONTINUABLE`. Trong ứng dụng thật, không nên tạo vòng lặp chờ không giới hạn. Cần có timeout, giới hạn số lần kiểm tra hoặc một cơ chế polling có backoff để tránh giữ tài nguyên và transaction quá lâu. Với một tiến trình bất đồng bộ kéo dài, thường nên lưu mã tác vụ, kết thúc lần chạy hiện tại rồi dùng cơ chế điều phối phù hợp để kiểm tra sau.

## 8. Xử lý lỗi và restart Tasklet

Nếu Tasklet ném exception, TaskletStep ghi nhận lỗi và Step thường kết thúc `FAILED`. Nếu Job cho phép restart, Spring Batch có thể tạo JobExecution mới cho cùng JobInstance khi khởi chạy lại với cùng identifying JobParameters.

Tuy nhiên, restart không tự động hoàn tác các thao tác bên ngoài transaction:

| Công việc Tasklet | Khi lỗi xảy ra sau khi thao tác đã thực hiện | Cách thiết kế restart |
|---|---|---|
| Di chuyển file | File có thể đã nằm ở thư mục đích | Kiểm tra nguồn/đích, checksum và mã lô trước khi di chuyển lại. |
| Ghi file kết quả | File có thể đã được tạo một phần hoặc hoàn chỉnh | Ghi vào file tạm, xác minh rồi đổi tên; xử lý file đã tồn tại theo quy tắc rõ ràng. |
| Gọi stored procedure | Procedure có thể đã commit dữ liệu | Procedure cần idempotency key hoặc bảng trạng thái batch. |
| Gọi HTTP API | Hệ thống đích có thể đã xử lý yêu cầu | Dùng request ID/idempotency key và tra cứu kết quả trước khi gửi lại. |

Không nên dựa vào việc JobExecution trước `FAILED` để kết luận toàn bộ tác dụng phụ đã được rollback. Cần xem transaction boundary thực tế và khả năng khôi phục của tác vụ.

### Dùng ExecutionContext khi cần lưu trạng thái

Nếu Tasklet xử lý nhiều phần hoặc cần ghi nhận tiến độ, có thể dùng `ExecutionContext` thông qua `StepExecution` để lưu checkpoint. Ví dụ lưu tên file đã xử lý hoặc mã lô hiện tại:

```java
String inputFile = jobParameters.getString("inputFile");
stepExecution.getExecutionContext().putString("inputFile", inputFile);
```

Trong Tasklet, có thể lấy StepExecution qua `contribution.getStepExecution()`. Trạng thái trong ExecutionContext được Spring Batch lưu theo cơ chế repository; nên lưu những giá trị nhỏ cần thiết cho restart, không dùng nó làm nơi chứa nội dung file hoặc dữ liệu nghiệp vụ lớn.

## 9. Theo dõi kết quả Tasklet

Tasklet không tự động đếm số item như chunk-oriented Step. Nếu Tasklet gọi stored procedure xử lý 500 bản ghi và nhận output count là 500, có thể cập nhật `StepContribution`:

```java
contribution.incrementWriteCount(500);
```

Nếu Tasklet kiểm tra file hoặc tạo marker mà không có khái niệm item đọc/ghi, không cần tự đặt các bộ đếm giả. Có thể ghi log có cấu trúc, lưu kết quả nghiệp vụ vào database hoặc cập nhật `ExitStatus` để thể hiện kết quả riêng.

Ví dụ đặt mã thoát tùy chỉnh:

```java
contribution.setExitStatus(new ExitStatus("FILE_ARCHIVED"));
return RepeatStatus.FINISHED;
```

Nếu Job dùng kết quả Step để rẽ nhánh, có thể cấu hình flow dựa trên `ExitStatus`. Cần phân biệt `ExitStatus` với `BatchStatus`: mã thoát thể hiện kết quả của Step, còn BatchStatus biểu diễn trạng thái thực thi như `COMPLETED` hoặc `FAILED`.

## 10. Khi nào nên dùng Tasklet?

Tasklet thường phù hợp khi công việc là một thao tác tổng thể, không cần framework chia dữ liệu thành các chunk. Ví dụ:

- Kiểm tra sự tồn tại, kích thước hoặc checksum của file.
- Di chuyển, đổi tên, nén hoặc tạo file đánh dấu.
- Gọi stored procedure để tính toán hoặc đồng bộ dữ liệu.
- Dọn dữ liệu tạm hoặc cập nhật trạng thái một lô.
- Gọi một công cụ hoặc dịch vụ bên ngoài với cơ chế kiểm soát kết quả.

Chunk processing thường phù hợp hơn khi cần đọc, validate, biến đổi và ghi từng bản ghi theo commit interval. Nếu Tasklet tự viết vòng lặp đọc file hàng triệu dòng và tự xử lý từng dòng, ứng dụng sẽ phải tự quản lý buffer, checkpoint, retry, skip và transaction. Trong trường hợp đó, `ItemReader`/`ItemProcessor`/`ItemWriter` thường cung cấp cấu trúc rõ ràng và khả năng quan sát tốt hơn.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tasklet bị gọi lặp ngoài dự kiến | Trả về `CONTINUABLE` thay vì `FINISHED`. | Chỉ trả `CONTINUABLE` khi thực sự cần lặp. |
| File đã move nhưng Step vẫn FAILED | File system không thuộc transaction database; lỗi xảy ra sau move. | Thiết kế kiểm tra nguồn/đích, checksum và thao tác idempotent. |
| Stored procedure chạy lặp khi restart | Procedure đã commit độc lập trước khi Job thất bại. | Dùng batch key, trạng thái xử lý hoặc logic idempotent trong procedure. |
| Transaction không rollback dữ liệu procedure | Procedure dùng transaction khác hoặc tự commit. | Kiểm tra transaction semantics của database và procedure. |
| Tasklet giữ transaction quá lâu | Một lần execute thực hiện quá nhiều công việc hoặc polling không giới hạn. | Chia nhỏ công việc, dùng `CONTINUABLE` có giới hạn hoặc chuyển sang chunk processing. |
| Không thấy số lượng bản ghi đã xử lý | Tasklet không tự tăng item counters. | Cập nhật contribution từ số liệu thực tế do tác vụ trả về. |
| Dùng Tasklet cho xử lý từng dòng lớn | Tự triển khai lại nhiều cơ chế mà chunk processing đã hỗ trợ. | Dùng chunk-oriented Step khi cần xử lý item theo nhóm. |

## Kết luận

Tasklet là cách triển khai một Step cho một tác vụ batch cụ thể như kiểm tra hoặc di chuyển file, dọn dữ liệu hay gọi stored procedure. `TaskletStep` quản lý vòng đời và transaction, còn `RepeatStatus.FINISHED` báo rằng tác vụ đã hoàn tất. Với thao tác file và procedure, cần nhớ rằng tác dụng phụ bên ngoài transaction không tự động được rollback. Thiết kế idempotent, kiểm tra trạng thái trước khi thực hiện và lưu checkpoint khi cần sẽ giúp Job restart an toàn. Khi yêu cầu chuyển sang xử lý nhiều item theo nhóm, chunk-oriented processing thường là lựa chọn phù hợp hơn.
