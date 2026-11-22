# Launch exception và lỗi validation

`JobLauncher` là thành phần nhận một Job cùng `JobParameters` và yêu cầu Spring Batch bắt đầu thực thi. Trong quá trình khởi chạy, framework phải kiểm tra tham số, xác định `JobInstance`, kiểm tra lịch sử chạy trước đó, tạo `JobExecution` và chuyển công việc cho executor. Mỗi bước có thể phát sinh lỗi với nguyên nhân khác nhau.

Hiểu đúng launch exception và lỗi validation giúp phân biệt một yêu cầu khởi chạy không hợp lệ, một Job đang chạy, một JobInstance đã hoàn tất, một yêu cầu restart không được phép và một lỗi phát sinh bên trong Step. Các trường hợp này cần cách xử lý khác nhau; nếu gom tất cả thành một lỗi chung, hệ thống khó phản hồi chính xác và có thể vô tình chạy trùng công việc.

## 1. Vòng đời của một yêu cầu khởi chạy Job

Một yêu cầu launch thường đi qua các bước sau:

1. Ứng dụng nhận yêu cầu từ scheduler, REST API, command line hoặc một thành phần khác.
2. Ứng dụng chuyển dữ liệu đầu vào thành `JobParameters` có kiểu dữ liệu phù hợp.
3. `JobLauncher` kiểm tra tham số bằng `JobParametersValidator` đã cấu hình cho Job.
4. `JobRepository` xác định JobInstance dựa trên tên Job và các identifying parameters.
5. Repository kiểm tra lịch sử execution để xác định Job có đang chạy, đã hoàn tất hay có thể restart.
6. Nếu hợp lệ, repository tạo `JobExecution` mới.
7. `JobLauncher` giao execution cho executor để bắt đầu chạy Job.
8. Job thực thi các Step và cập nhật trạng thái, exit status cùng metadata trong repository.

```text
Scheduler / REST / CLI
          |
          v
  Tạo JobParameters
          |
          v
   JobParametersValidator
          |
          v
      JobRepository
          |
          +-- Xác định JobInstance
          |
          +-- Kiểm tra execution trước
          |
          +-- Tạo JobExecution
          |
          v
      JobLauncher
          |
          v
        Executor
          |
          v
       Job / Steps
```

Lỗi có thể xảy ra trước khi có `JobExecution`, ví dụ validator từ chối tham số hoặc repository phát hiện JobInstance đã hoàn tất. Lỗi cũng có thể xảy ra sau khi JobExecution được tạo, ví dụ executor không nhận được tác vụ hoặc một Step thất bại trong lúc xử lý. Cần xác định lỗi thuộc giai đoạn nào trước khi quyết định trả lỗi cho người gọi, retry hay restart.

## 2. Các exception thường gặp khi gọi JobLauncher

Phương thức `JobLauncher.run(job, jobParameters)` khai báo các checked exception chính sau:

| Exception | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `JobParametersInvalidException` | Tham số thiếu, không hợp lệ hoặc không thỏa quy tắc của validator. | Trả lỗi đầu vào và yêu cầu sửa tham số. |
| `JobExecutionAlreadyRunningException` | JobInstance tương ứng đang có execution chạy. | Kiểm tra execution hiện tại; không khởi chạy bản trùng. |
| `JobInstanceAlreadyCompleteException` | JobInstance tương ứng đã hoàn tất. | Xác định người gọi muốn restart, chạy nghiệp vụ mới hay chạy lại có chủ đích. |
| `JobRestartException` | JobInstance không thể restart theo trạng thái hoặc cấu hình hiện tại. | Kiểm tra restartability, trạng thái cũ và chính sách của Step. |

Ngoài các checked exception này, ứng dụng còn có thể gặp lỗi hạ tầng như database không truy cập được, lỗi transaction hoặc executor từ chối nhận tác vụ. Ví dụ, `TaskRejectedException` có thể xuất hiện khi thread pool đã đầy hoặc đang shutdown. Đây là lỗi hạ tầng/điều phối, không phải lỗi validation của JobParameters.

Các exception trên phản ánh vấn đề khác nhau. Không nên bắt tất cả rồi trả về cùng một thông báo “Batch failed”. Thông tin cụ thể giúp caller quyết định có cần sửa request, chờ execution đang chạy, tạo một JobInstance mới hay yêu cầu hỗ trợ vận hành.

## 3. JobParametersInvalidException và validation

`JobParametersInvalidException` được dùng khi các tham số khởi chạy không đáp ứng yêu cầu của Job. Việc validation nên diễn ra trước khi Job thực hiện tác dụng phụ nghiệp vụ, để tránh bắt đầu một quy trình với ngày nghiệp vụ sai, thiếu tệp đầu vào hoặc lựa chọn không hợp lệ.

Spring Batch cung cấp interface `JobParametersValidator`:

```java
public interface JobParametersValidator {
    void validate(JobParameters parameters)
            throws JobParametersInvalidException;
}
```

Validator nhận `JobParameters`. Nếu tham số hợp lệ, phương thức kết thúc bình thường. Nếu không hợp lệ, validator ném `JobParametersInvalidException` kèm thông tin đủ rõ để người gọi biết điều gì cần sửa.

### Các loại quy tắc nên kiểm tra

Validation có thể kiểm tra:

- Tham số bắt buộc có tồn tại hay không.
- Tên tham số có thuộc danh sách được phép hay không.
- Giá trị có đúng định dạng, miền giá trị hoặc quy tắc nghiệp vụ cơ bản hay không.
- Các tham số có tương thích với nhau hay không, ví dụ `startDate` không được sau `endDate`.
- Một chế độ chạy có yêu cầu thêm tham số hay không, ví dụ `reprocess=true` phải đi kèm `sourceBatchId`.

Nên giữ validator nhanh, xác định và ít tác dụng phụ. Những kiểm tra cần truy cập hệ thống ngoài, đọc tệp lớn hoặc truy vấn dữ liệu có thể thay đổi theo thời gian thường phù hợp hơn với một bước preflight riêng trong Job. Validator không nên gửi email, ghi dữ liệu nghiệp vụ hoặc thực hiện thao tác không thể hoàn tác.

## 4. Dùng DefaultJobParametersValidator

`DefaultJobParametersValidator` phù hợp với trường hợp cần khai báo danh sách tham số bắt buộc và tham số tùy chọn. Ví dụ, Job import cần `inputFile` và `businessDate`; `requestedBy` và `dryRun` là tùy chọn.

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
            new String[] {"inputFile", "businessDate"},
            new String[] {"requestedBy", "dryRun"}
    );
}
```

Gắn validator vào Job:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(importParametersValidator)
            .start(importOrdersStep)
            .build();
}
```

Trong ví dụ này, `inputFile` và `businessDate` phải có mặt. `requestedBy` và `dryRun` có thể có hoặc không. Các tham số ngoài danh sách được phép sẽ bị validator từ chối. Nếu cần kiểm tra kiểu dữ liệu hoặc quan hệ giữa các giá trị, hãy bổ sung custom validator.

`DefaultJobParametersValidator` chủ yếu giải quyết quy tắc về tên và sự hiện diện của tham số. Nó không thay thế toàn bộ validation nghiệp vụ. Ví dụ, việc một chuỗi ngày có đúng định dạng ISO hay ngày kết thúc có sau ngày bắt đầu cần được kiểm tra bằng logic riêng.

## 5. Viết custom JobParametersValidator

Khi cần kiểm tra định dạng và quan hệ giữa các tham số, có thể triển khai `JobParametersValidator`.

Ví dụ Job nhận tên tệp và ngày nghiệp vụ dưới dạng chuỗi:

```java
public class ImportParametersValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");
        String businessDate = parameters.getString("businessDate");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "Required parameter 'inputFile' is missing");
        }

        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "Required parameter 'businessDate' is missing");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException exception) {
            throw new JobParametersInvalidException(
                    "Parameter 'businessDate' must use ISO date format (yyyy-MM-dd)");
        }
    }
}
```

Đăng ký validator:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new ImportParametersValidator();
}
```

Đoạn code cần các import Java tương ứng như `LocalDate` và `DateTimeParseException`. Trong Spring Batch 5, `JobParameters` hỗ trợ tham số có kiểu; nếu ứng dụng truyền `LocalDate` trực tiếp, có thể dùng API đọc đúng kiểu thay vì chuyển đổi qua chuỗi. Ví dụ dùng chuỗi ở đây để thể hiện rõ quy tắc định dạng đầu vào.

Một validator tốt nên nêu tên tham số và quy tắc bị vi phạm. Không nên trả thông báo mơ hồ như “Invalid parameters”. Đồng thời, tránh đưa giá trị nhạy cảm của tham số vào exception message vì thông báo có thể được ghi vào log hoặc metadata.

## 6. Phân biệt lỗi validation với lỗi chuyển đổi tham số

Validation diễn ra sau khi ứng dụng đã có `JobParameters`. Tuy nhiên, dữ liệu đầu vào từ command line, REST request hoặc file cấu hình thường phải được chuyển đổi thành kiểu tham số trước đó.

Ví dụ, nếu API nhận `businessDate="15-11-2026"` nhưng converter hoặc code binding yêu cầu định dạng khác, lỗi parse có thể xảy ra trước khi gọi `JobLauncher`. Trong trường hợp đó, `JobParametersValidator` có thể chưa được chạy.

Nên phân biệt các giai đoạn:

| Giai đoạn | Ví dụ lỗi | Nơi xử lý phù hợp |
|---|---|---|
| Nhận request | Thiếu field JSON hoặc sai kiểu dữ liệu. | Controller/request validation. |
| Chuyển đổi tham số | Chuỗi ngày không parse được thành kiểu ngày. | Converter hoặc lớp mapping đầu vào. |
| Job validation | Thiếu `inputFile`, ngày nghiệp vụ sai quy tắc. | `JobParametersValidator`. |
| Kiểm tra trạng thái instance | Instance đang chạy hoặc đã hoàn tất. | `JobLauncher`/`JobRepository` và logic điều phối. |
| Thực thi Step | Tệp không đọc được, database timeout, lỗi nghiệp vụ. | Reader, processor, writer, Tasklet và fault-tolerance policy. |

Tách các lớp này giúp API trả lỗi đầu vào phù hợp, đồng thời không buộc validator phải xử lý những dữ liệu chưa được chuyển thành `JobParameters`.

## 7. JobExecutionAlreadyRunningException

`JobExecutionAlreadyRunningException` xảy ra khi một JobInstance tương ứng đã có execution đang chạy. Trường hợp này thường xuất hiện khi scheduler gửi trùng yêu cầu, người dùng nhấn nút launch nhiều lần hoặc nhiều ứng dụng cùng cố khởi chạy một Job với cùng identifying parameters.

Ví dụ:

```text
Job: dailySettlementJob
Identifying parameter: businessDate=2026-11-15

Request A --> JobExecution 5001 --> STARTED
Request B --> cùng JobInstance --> JobExecutionAlreadyRunningException
```

Hướng xử lý:

1. Tra cứu execution đang hoạt động bằng `JobExplorer` hoặc màn hình vận hành.
2. Xác định request mới là gửi trùng hay là một yêu cầu nghiệp vụ khác.
3. Nếu là gửi trùng, trả về ID execution đang chạy hoặc thông báo trạng thái hiện tại.
4. Nếu thực sự là một đợt nghiệp vụ mới, xác định identifying parameter mới theo quy tắc nghiệp vụ.
5. Nếu metadata báo đang chạy nhưng tiến trình đã chết, điều tra trạng thái tiến trình, database và transaction trước khi thực hiện quy trình phục hồi.

Không nên xóa bản ghi JobExecution hoặc tự đổi `STATUS` trong bảng metadata để bỏ qua exception. Làm như vậy có thể khiến hai tiến trình cùng xử lý một JobInstance hoặc khiến checkpoint không còn phản ánh dữ liệu thực tế.

Để giảm request trùng, ứng dụng có thể dùng idempotency key ở API, khóa phân tán hoặc cơ chế điều phối scheduler. Tuy nhiên, unique constraint và transaction của JobRepository vẫn là lớp bảo vệ quan trọng ở cấp metadata.

## 8. JobInstanceAlreadyCompleteException

`JobInstanceAlreadyCompleteException` xảy ra khi JobInstance được xác định bởi tên Job và identifying parameters đã hoàn tất. Spring Batch không tạo một lần thực thi mới cho cùng instance đã hoàn tất theo cách khởi chạy thông thường.

Ví dụ, `dailySettlementJob` đã hoàn tất với `businessDate=2026-11-15`. Nếu gửi lại đúng tên Job và cùng identifying parameters, framework nhận ra đây là cùng JobInstance và từ chối launch.

Trước khi xử lý exception, hãy xác định ý định:

- **Muốn tiếp tục một lần chạy thất bại:** dùng cùng định danh JobInstance và restart theo chính sách của Spring Batch.
- **Muốn chạy một đợt nghiệp vụ mới:** truyền identifying parameter mới theo quy tắc nghiệp vụ, ví dụ ngày nghiệp vụ khác hoặc mã batch mới.
- **Muốn chạy lại có chủ đích cùng dữ liệu nghiệp vụ:** cần thiết kế một định danh lần chạy lại rõ ràng, chẳng hạn `run.id` hoặc `reprocessVersion`, đồng thời bảo đảm thao tác nghiệp vụ idempotent và có thể đối soát.

Không nên tự thêm timestamp ngẫu nhiên vào mọi lần launch chỉ để tránh exception. Nếu mỗi lần retry đều tạo JobInstance mới, Spring Batch sẽ không thể nhận diện đó là restart của lần chạy cũ và checkpoint trước đó có thể không được dùng.

`allowStartIfComplete(true)` là tùy chọn của Step, cho phép Step đã hoàn tất được chạy lại trong một lần restart Job phù hợp. Nó không tự cho phép khởi chạy lại một JobInstance đã `COMPLETED` bằng cách gọi `JobLauncher.run` với đúng định danh cũ.

## 9. JobRestartException

`JobRestartException` biểu thị yêu cầu restart không được chấp nhận theo trạng thái hoặc cấu hình hiện tại. Một số nguyên nhân có thể gồm:

- Job được cấu hình không cho restart, ví dụ dùng `preventRestart()`.
- Execution trước ở trạng thái không phù hợp để tiếp tục, chẳng hạn `ABANDONED` hoặc `UNKNOWN`.
- Trạng thái Step hoặc chính sách start limit khiến lần chạy lại không thể tiếp tục theo cách yêu cầu.
- Metadata hoặc điều kiện restart không nhất quán.

Ví dụ Job không cho restart:

```java
@Bean
Job oneTimeExportJob(
        JobRepository jobRepository,
        Step exportStep) {

    return new JobBuilder("oneTimeExportJob", jobRepository)
            .preventRestart()
            .start(exportStep)
            .build();
}
```

Chỉ dùng `preventRestart()` khi nghiệp vụ thực sự không cho phép tiếp tục một execution đã dừng hoặc thất bại. Nếu Job cần phục hồi sau lỗi hạ tầng, thiết kế restartable thường phù hợp hơn, kèm reader/writer hỗ trợ checkpoint và các thao tác idempotent.

Khi gặp `JobRestartException`, hãy xem JobExecution trước đó, BatchStatus, ExitStatus, failure exception, trạng thái StepExecution, start limit và cấu hình restart. Không nên xóa metadata cũ trước khi xác định tác dụng của nó đối với dữ liệu đã xử lý.

## 10. Identifying parameters và quyết định tạo JobInstance

Spring Batch phân biệt identifying và non-identifying JobParameters. Tên Job cùng identifying parameters xác định JobInstance. Non-identifying parameters có thể mang thông tin vận hành như người yêu cầu hoặc nhãn ghi log mà không làm thay đổi định danh nghiệp vụ.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "orders-2026-11-15.csv", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Trong ví dụ, `businessDate` và `inputFile` tham gia xác định JobInstance. `requestedBy` chỉ là thông tin vận hành. Nếu một lần khởi chạy mới dùng cùng Job name và cùng identifying parameters, nó trỏ tới cùng JobInstance.

### Restart và run mới là hai ý định khác nhau

Khi Job thất bại giữa chừng, restart thường cần giữ định danh của JobInstance để Spring Batch liên kết lần chạy mới với lịch sử và checkpoint trước đó.

Khi muốn tạo một lần nghiệp vụ mới, có thể dùng `JobParametersIncrementer`, chẳng hạn `RunIdIncrementer`:

```java
@Bean
Job monthlyReportJob(
        JobRepository jobRepository,
        Step reportStep) {

    return new JobBuilder("monthlyReportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(reportStep)
            .build();
}
```

Incrementer thường thêm hoặc tăng tham số định danh như `run.id`. Nó phù hợp khi mỗi lần chạy được xem là một JobInstance mới. Không dùng incrementer để che giấu một JobInstance đang chạy hoặc để thay thế việc restart một Job thất bại.

## 11. Lỗi hạ tầng khi launch

Không phải mọi lỗi trong lúc gọi `JobLauncher.run` đều là lỗi tham số hoặc trạng thái instance. Một số lỗi có thể đến từ hạ tầng:

### TaskRejectedException

Với launcher sử dụng `TaskExecutor`, executor có thể từ chối tác vụ khi thread pool đã đạt giới hạn, hàng đợi đầy hoặc executor đang shutdown. Đây là dấu hiệu năng lực xử lý hoặc vòng đời executor cần được kiểm tra.

Hướng xử lý gồm giới hạn tốc độ nhận yêu cầu, cấu hình pool/queue phù hợp, theo dõi số tác vụ đang chạy và xử lý tình trạng executor shutdown. Không nên retry liên tục ngay lập tức nếu hệ thống vẫn quá tải; điều đó có thể làm hàng đợi nặng hơn.

### Lỗi JobRepository hoặc database

Nếu database lưu metadata không truy cập được, JobLauncher có thể không tạo hoặc cập nhật được JobExecution. Các lỗi thường gặp gồm timeout, mất kết nối, thiếu quyền, sai schema, thiếu sequence hoặc optimistic locking conflict.

Kiểm tra datasource, transaction manager, schema repository, quyền truy cập và log database. Nếu không rõ JobExecution đã được tạo hay chưa, hãy truy vấn repository trước khi gửi lại launch để tránh tạo yêu cầu trùng.

### Lỗi cấu hình Job hoặc registry

Nếu ứng dụng lấy Job theo tên từ `JobRegistry` hoặc một cơ chế đăng ký tương tự, tên Job không tồn tại có thể gây lỗi tra cứu trước khi gọi launcher. Đây là lỗi cấu hình/lookup, khác với `JobParametersInvalidException`.

Hãy kiểm tra tên Job được yêu cầu, cấu hình đăng ký Job và môi trường đang chạy. Không nên biến lỗi “không tìm thấy Job” thành lỗi validation của tham số.

## 12. Phân biệt launch exception với lỗi trong Step

Một điểm dễ nhầm là `JobLauncher.run` có thể trả về một `JobExecution` mang trạng thái `FAILED` khi lỗi phát sinh trong quá trình thực thi Job. Điều đó khác với việc launcher ném một checked exception trước hoặc trong lúc giao tác vụ.

Ví dụ:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, parameters);

BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();
```

Với lỗi xảy ra trong reader, processor, writer hoặc Tasklet, Spring Batch thường ghi nhận lỗi vào execution, cập nhật `BatchStatus`/`ExitStatus` và lưu failure exception. Ứng dụng phải xem trạng thái trả về hoặc truy vấn execution sau đó để biết kết quả.

Với launcher bất đồng bộ, `run` có thể trả về khi Job mới ở trạng thái `STARTING` hoặc `STARTED`; công việc tiếp tục trên executor. Trạng thái khi nhận response chưa phải kết quả cuối cùng. Cần theo dõi bằng `JobExplorer`, sự kiện hoặc API trạng thái của ứng dụng.

Vì vậy:

- Exception từ validator hoặc repository thường cho biết yêu cầu launch bị từ chối.
- `JobExecution` có `FAILED` thường cho biết Job đã bắt đầu và lỗi xảy ra trong execution.
- `STARTING` hoặc `STARTED` nghĩa là chưa có kết quả cuối cùng.
- `COMPLETED` cần được đọc cùng `ExitStatus` và kết quả nghiệp vụ.

Không nên chỉ dựa vào việc `jobLauncher.run` không ném exception để kết luận Job đã thành công.

## 13. Xử lý exception ở lớp gọi JobLauncher

Lớp gọi launcher nên phân loại các checked exception cụ thể. Ví dụ sau minh họa một service điều phối:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(JobParameters parameters)
            throws JobParametersInvalidException,
                   JobExecutionAlreadyRunningException,
                   JobInstanceAlreadyCompleteException,
                   JobRestartException {

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

Service có thể để exception cụ thể đi lên controller hoặc lớp gọi, nơi có đủ ngữ cảnh để quyết định cách phản hồi. Nếu service bắt exception, hãy giữ nguyên nguyên nhân và chuyển thành kết quả có kiểu rõ ràng; tránh chỉ ghi log rồi trả `null`.

### Ví dụ ánh xạ lỗi sang HTTP response

Với REST API, có thể ánh xạ lỗi theo ý nghĩa của request:

```java
try {
    JobExecution execution = jobLauncher.run(job, parameters);
    return ResponseEntity.accepted().body(execution.getId());
} catch (JobParametersInvalidException exception) {
    return ResponseEntity.badRequest().body("Invalid Job parameters");
} catch (JobExecutionAlreadyRunningException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("This JobInstance is already running");
} catch (JobInstanceAlreadyCompleteException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("This JobInstance has already completed");
} catch (JobRestartException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("This JobInstance cannot be restarted");
}
```

Đây là ví dụ ánh xạ ở mức khái niệm; controller thực tế cần khai báo kiểu trả về phù hợp và ghi log exception theo chính sách ứng dụng. HTTP `202 Accepted` phù hợp khi request đã được chấp nhận để xử lý bất đồng bộ. Nếu launcher chạy đồng bộ và đã có kết quả cuối cùng, response có thể phản ánh trạng thái thực tế theo hợp đồng API.

Không trả nguyên văn stack trace, SQL, đường dẫn nội bộ hoặc nội dung nhạy cảm của JobParameters cho client. Client chỉ cần mã lỗi ổn định và hướng xử lý; chi tiết kỹ thuật nên nằm trong log có kiểm soát.

## 14. Đồng bộ và bất đồng bộ ảnh hưởng thế nào đến launch?

`JobLauncher` có thể dùng executor đồng bộ hoặc bất đồng bộ.

### Đồng bộ

Với executor đồng bộ như `SyncTaskExecutor`, tác vụ chạy trên luồng gọi. Phương thức launch thường chỉ trả về sau khi Job thực thi xong. Điều này dễ hiểu trong ứng dụng nhỏ hoặc command line, nhưng request có thể chờ lâu nếu Job xử lý nhiều dữ liệu.

### Bất đồng bộ

Với executor bất đồng bộ, launcher giao tác vụ cho thread khác và trả về sớm. Caller nhận một `JobExecution` có thể vẫn đang chạy. Cần có cơ chế tra cứu trạng thái, thông báo hoàn tất và xử lý lỗi sau khi request ban đầu đã kết thúc.

Khi chạy bất đồng bộ, lỗi phát sinh trong Step không thể được trả như một HTTP exception của request launch đã kết thúc. Nó được ghi vào JobExecution; ứng dụng cần cung cấp endpoint hoặc cơ chế quan sát để người dùng xem kết quả.

## 15. Retry launch, restart Job và tạo JobInstance mới

Ba thao tác này không giống nhau:

| Thao tác | Mục đích | Định danh |
|---|---|---|
| Retry gửi yêu cầu launch | Gửi lại request do lỗi mạng hoặc timeout ở phía caller. | Cần idempotency để không tạo hoặc chạy trùng. |
| Restart Job | Tiếp tục JobInstance đã thất bại hoặc dừng, theo chính sách Spring Batch. | Giữ định danh JobInstance. |
| Tạo JobInstance mới | Bắt đầu một đợt nghiệp vụ mới hoặc một lần reprocess có định danh riêng. | Dùng identifying parameter mới. |

Ví dụ, caller gửi request nhưng bị timeout trước khi nhận response. Không thể kết luận Job chưa chạy. Trước khi gửi lại, caller nên dùng idempotency key hoặc tra cứu JobExecution theo business key để xác định request trước đã được tiếp nhận hay chưa.

Nếu Job thất bại sau khi một số chunk đã commit, restart có thể tiếp tục từ checkpoint nếu reader/writer hỗ trợ restart và các tác dụng phụ được thiết kế an toàn. Nếu tạo JobInstance mới bằng `run.id` thay vì restart, công việc có thể chạy lại từ đầu và tạo dữ liệu trùng nếu không có kiểm soát.

## 16. Logging và chẩn đoán lỗi launch

Khi ghi log một yêu cầu launch, nên có đủ thông tin để liên kết request, JobInstance và JobExecution:

- Tên Job.
- Mã request hoặc idempotency key.
- Business key và các identifying parameters không nhạy cảm.
- JobExecution ID nếu đã được tạo.
- Exception class và nguyên nhân gốc.
- BatchStatus, ExitStatus và thời điểm xảy ra lỗi nếu execution đã tồn tại.

Không log bí mật, token, mật khẩu hoặc toàn bộ payload nếu payload có dữ liệu cá nhân. Có thể che giá trị nhạy cảm và chỉ ghi các tham số cần thiết để chẩn đoán.

Khi điều tra, đi theo thứ tự:

1. Xác định lỗi xảy ra trước hay sau khi JobExecution được tạo.
2. Kiểm tra Job name và identifying JobParameters.
3. Nếu validator từ chối, xem tên tham số và quy tắc bị vi phạm.
4. Nếu instance đang chạy hoặc đã hoàn tất, tra cứu JobExecution trước đó.
5. Nếu restart bị từ chối, kiểm tra BatchStatus, restartability, start limit và trạng thái Step.
6. Nếu lỗi hạ tầng, kiểm tra executor, datasource, transaction và repository schema.
7. Nếu execution đã bắt đầu nhưng thất bại, đọc failure exception và log của Step tương ứng.

## 17. Những sai lầm thường gặp

### Bắt mọi exception và trả về cùng một mã lỗi

Điều này khiến caller không biết nên sửa tham số, chờ Job hiện tại hay yêu cầu một lần chạy mới. Hãy phân loại các exception launch chính và giữ thông tin nguyên nhân.

### Dùng tham số ngẫu nhiên để né JobInstanceAlreadyCompleteException

Thêm timestamp hoặc UUID cho mọi request tạo ra JobInstance mới liên tục, làm mất khả năng nhận diện restart và có thể xử lý trùng dữ liệu. Chỉ tạo định danh mới khi nghiệp vụ thực sự yêu cầu một lần chạy mới.

### Xem JobParametersValidator là nơi kiểm tra mọi thứ

Validator phù hợp với kiểm tra nhanh, xác định trên JobParameters. Việc kiểm tra tệp lớn, gọi API hoặc khóa tài nguyên nên nằm ở bước preflight hoặc thành phần nghiệp vụ có cơ chế timeout và xử lý lỗi phù hợp.

### Nghĩ rằng run() trả về là Job đã thành công

Launcher bất đồng bộ có thể trả về khi Job vẫn đang chạy. Ngay cả với launcher đồng bộ, một Job có thể kết thúc với `BatchStatus.FAILED` mà không cần biến lỗi Step thành exception ở caller. Luôn kiểm tra trạng thái execution.

### Tự sửa metadata để khởi chạy lại

Xóa execution hoặc đổi `STATUS` trực tiếp trong bảng `BATCH_*` có thể phá vỡ quan hệ metadata và checkpoint. Dùng API vận hành hoặc quy trình phục hồi đã thiết kế sau khi xác định dữ liệu nghiệp vụ thực tế.

### Retry vô hạn khi executor hoặc database quá tải

Retry không giới hạn có thể làm tăng tải và tạo thêm request trùng. Dùng backoff, giới hạn retry, giám sát năng lực và cơ chế idempotency.

## 18. Quy trình thiết kế validation và launch an toàn

Khi xây dựng một endpoint hoặc scheduler khởi chạy Job, có thể áp dụng trình tự sau:

1. Xác định business key và identifying parameters để phân biệt JobInstance.
2. Chuyển request thành `JobParameters` có kiểu; xử lý lỗi parse ngay tại lớp mapping.
3. Dùng `JobParametersValidator` kiểm tra tham số bắt buộc, định dạng và quan hệ cơ bản.
4. Để JobRepository kiểm tra trạng thái JobInstance và execution trước đó.
5. Phân loại exception launch để caller nhận hướng xử lý phù hợp.
6. Ghi nhận JobExecution ID và trả trạng thái tiếp nhận rõ ràng.
7. Theo dõi execution sau launch, đặc biệt khi dùng executor bất đồng bộ.
8. Thiết kế retry/restart riêng biệt, bảo đảm thao tác nghiệp vụ có thể chạy lại an toàn.
9. Kiểm tra log, metadata và dữ liệu đích trước khi thực hiện quy trình phục hồi thủ công.

Một thiết kế tốt giúp validation từ chối request sai trước khi tạo tác dụng phụ, JobRepository ngăn các lần chạy xung đột, còn trạng thái execution giúp caller theo dõi kết quả sau khi Job bắt đầu.

## Kết luận

Launch exception trong Spring Batch phản ánh những vấn đề khác nhau ở giai đoạn nhận tham số, xác định JobInstance, kiểm tra trạng thái restart hoặc giao tác vụ cho executor. `JobParametersValidator` giúp kiểm tra tham số bắt buộc và quy tắc đầu vào trước khi Job thực thi. `JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException` và `JobRestartException` cần được xử lý theo trạng thái thực tế của JobInstance. Sau khi launch, hãy kiểm tra `JobExecution` và các trạng thái của nó để phân biệt một Job bị từ chối khởi chạy với một Job đã bắt đầu nhưng thất bại trong Step.
