# JobParameters khi launch

Trong Spring Batch, `JobParameters` là tập hợp các giá trị đầu vào được truyền vào mỗi lần khởi chạy Job. Khi gọi `JobLauncher.run(job, jobParameters)`, ứng dụng cung cấp Job cần chạy cùng các tham số mô tả lần chạy đó, chẳng hạn ngày nghiệp vụ, mã file đầu vào, phạm vi dữ liệu hoặc mã khách hàng.

JobParameters có hai vai trò quan trọng. Thứ nhất, chúng cung cấp dữ liệu để Job và các Step thực hiện công việc. Thứ hai, các tham số được đánh dấu là **identifying** tham gia xác định `JobInstance`. Vì vậy, cách chọn tham số ảnh hưởng trực tiếp đến việc một lần launch được xem là lần chạy mới hay là restart của một JobInstance đã tồn tại.

## 1. JobLauncher nhận JobParameters như thế nào?

`JobLauncher` là API khởi chạy một Job. Phương thức cơ bản nhận hai đối số: định nghĩa Job và đối tượng JobParameters.

```java
JobExecution run(Job job, JobParameters jobParameters)
```

Ví dụ, ứng dụng có Job tính phí theo ngày. Khi khởi chạy, service tạo tham số `businessDate` rồi truyền chúng cho JobLauncher:

```java
@Service
public class BillingJobService {

    private final JobLauncher jobLauncher;
    private final Job dailyBillingJob;

    public BillingJobService(
            JobLauncher jobLauncher,
            Job dailyBillingJob) {
        this.jobLauncher = jobLauncher;
        this.dailyBillingJob = dailyBillingJob;
    }

    public JobExecution launch(LocalDate businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addLocalDate("businessDate", businessDate, true)
                .toJobParameters();

        return jobLauncher.run(dailyBillingJob, parameters);
    }
}
```

Trong ví dụ, `businessDate` là tham số identifying. Nếu service được gọi nhiều lần với cùng ngày và cùng tên Job, những lần gọi đó nhắm đến cùng một JobInstance. Việc launch có thành công hay không còn phụ thuộc trạng thái execution hiện có: instance đang chạy, đã hoàn tất hay đã thất bại.

`JobLauncher.run()` trả về `JobExecution`, chứa thông tin về lần thực thi được tạo. Không nên mặc định rằng nhận được đối tượng này đồng nghĩa Job đã hoàn tất. Với launcher chạy đồng bộ, lời gọi thường chỉ trả về sau khi Job kết thúc. Với launcher chạy bất đồng bộ, lời gọi có thể trả về khi Job mới bắt đầu hoặc được đưa vào executor. Cách chạy phụ thuộc cấu hình JobLauncher.

## 2. Tạo JobParameters bằng JobParametersBuilder

`JobParametersBuilder` giúp tạo đối tượng `JobParameters` một cách rõ ràng. Mỗi tham số có tên, giá trị và cờ xác định nó có tham gia định danh JobInstance hay không.

Ví dụ kết hợp nhiều loại dữ liệu:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .addString("inputFile", "customers-20261115.csv", true)
        .addLong("requestedBy", 1024L, false)
        .addString("notificationEmail", "ops@example.com", false)
        .toJobParameters();
```

Trong ví dụ:

- `businessDate` xác định kỳ nghiệp vụ cần xử lý.
- `inputFile` xác định nguồn dữ liệu của lần chạy.
- `requestedBy` ghi nhận người yêu cầu chạy Job.
- `notificationEmail` chỉ định nơi gửi thông báo.

Hai tham số đầu là identifying (`true`); hai tham số sau là non-identifying (`false`). Khi thay đổi người yêu cầu hoặc địa chỉ nhận thông báo, JobInstance vẫn giữ nguyên nếu các tham số identifying không đổi.

Các phương thức thường dùng của builder gồm:

| Phương thức | Kiểu giá trị | Ví dụ |
|---|---|---|
| `addString()` | Chuỗi | Mã file, tên kỳ xử lý |
| `addLong()` | Số nguyên dài | ID, số thứ tự |
| `addDouble()` | Số thực | Ngưỡng hoặc giá trị số |
| `addDate()` | `java.util.Date` | Thời điểm theo API cũ |
| `addLocalDate()` | `java.time.LocalDate` | Ngày nghiệp vụ |
| `addLocalDateTime()` | `java.time.LocalDateTime` | Ngày giờ nghiệp vụ |

Các kiểu và overload cụ thể phụ thuộc phiên bản Spring Batch. Ở những phiên bản hỗ trợ, overload có tham số boolean cho phép chỉ rõ identifying. Nên dùng kiểu dữ liệu phù hợp với ý nghĩa nghiệp vụ, tránh biến mọi giá trị thành chuỗi nếu Job cần so sánh, tính toán hoặc xác thực chúng.

Sau khi gọi `toJobParameters()`, ứng dụng nhận được đối tượng `JobParameters` để truyền cho JobLauncher. Hãy xây dựng một đối tượng mới cho mỗi lần launch; builder giúp tập hợp tham số trước khi tạo đối tượng đầu vào.

## 3. Identifying và non-identifying parameters

Đây là điểm quan trọng nhất khi thiết kế JobParameters.

### Identifying parameters

Tham số identifying được dùng cùng tên Job để xác định `JobInstance`. Ví dụ, Job `dailyBillingJob` có tham số identifying `businessDate=2026-11-15`. Tổ hợp tên Job và các identifying parameters xác định một instance cho kỳ tính phí ngày đó.

Nếu thay đổi một identifying parameter, Spring Batch xem tổ hợp mới là một JobInstance khác. Ví dụ:

```text
dailyBillingJob + businessDate=2026-11-15
        -> JobInstance A

dailyBillingJob + businessDate=2026-11-16
        -> JobInstance B
```

Điều này phù hợp khi tham số thể hiện một đơn vị công việc độc lập, chẳng hạn ngày chốt sổ, mã file nhập hoặc mã kỳ thanh toán.

### Non-identifying parameters

Tham số non-identifying được lưu cùng lần thực thi và có thể được đọc trong Job, nhưng không tham gia tạo định danh JobInstance. Thay đổi một giá trị non-identifying không tự tạo JobInstance mới.

Ví dụ, `requestedBy` hoặc `notificationEmail` thường chỉ là thông tin vận hành. Hai lần launch có cùng `businessDate` và `inputFile` nhưng khác `requestedBy` vẫn hướng đến cùng JobInstance.

Không nên đánh dấu non-identifying cho một giá trị có thể làm thay đổi dữ liệu nghiệp vụ theo cách không tương thích giữa các lần restart. Chẳng hạn, nếu `exchangeRate` quyết định số tiền ghi ra database, việc thay đổi tỷ giá trong lần restart nhưng vẫn giữ cùng JobInstance có thể làm một phần dữ liệu được tính theo tỷ giá cũ, phần còn lại theo tỷ giá mới. Nếu giá trị đó xác định nội dung nghiệp vụ của lần chạy, thường nên đưa nó vào tập identifying hoặc lưu một bản snapshot bất biến gắn với JobInstance.

### Bảng so sánh

| Tiêu chí | Identifying | Non-identifying |
|---|---|---|
| Tham gia xác định JobInstance | Có | Không |
| Thay đổi giá trị có tạo instance mới? | Có | Không |
| Dùng để restart cùng instance | Phải giữ nguyên | Có thể thay đổi theo API và quy trình, nhưng cần bảo đảm nhất quán nghiệp vụ |
| Ví dụ phù hợp | Ngày nghiệp vụ, mã file, kỳ đối soát | Người yêu cầu, địa chỉ thông báo, nhãn theo dõi |

## 4. JobParameters quyết định JobInstance và restart

Spring Batch phân biệt `JobInstance` và `JobExecution`:

- `JobInstance` đại diện cho một lần chạy logic, được xác định bởi tên Job và identifying parameters.
- `JobExecution` đại diện cho một lần thực thi cụ thể của JobInstance.

Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại hoặc bị dừng và sau đó được restart.

```text
Job: dailyBillingJob
Identifying parameter: businessDate=2026-11-15
                   |
                   v
             JobInstance
                   |
          +--------+--------+
          |                 |
          v                 v
    JobExecution 1     JobExecution 2
       FAILED            COMPLETED
          |                 ^
          +---- restart ----+
```

Khi restart, ứng dụng thường gửi lại cùng tên Job và cùng identifying parameters để nhắm đến JobInstance cũ. Nếu thêm timestamp mới như một identifying parameter mỗi lần thử lại, Spring Batch sẽ tạo JobInstance mới và xử lý đây là công việc mới từ đầu, không phải restart instance đã thất bại.

Một số kết quả thường gặp khi launch:

| Tình trạng của JobInstance | Kết quả thường gặp |
|---|---|
| Chưa tồn tại | Spring Batch tạo JobInstance và JobExecution mới |
| Đang có execution chạy | Có thể nhận `JobExecutionAlreadyRunningException` |
| Execution trước đã COMPLETED | Có thể nhận `JobInstanceAlreadyCompleteException` |
| Execution trước FAILED hoặc STOPPED | Có thể restart nếu Job và Step cho phép |
| Job không cho phép restart | Có thể nhận `JobRestartException` |
| Parameters không hợp lệ | Có thể nhận `JobParametersInvalidException` |

Các ngoại lệ cụ thể còn phụ thuộc trạng thái, validator và cấu hình JobRepository. Ứng dụng nên xử lý chúng để trả thông báo vận hành phù hợp thay vì coi mọi lỗi launch là lỗi xử lý dữ liệu bên trong Step.

## 5. Đọc JobParameters bên trong Job và Step

JobParameters có thể được truy cập thông qua `StepExecution` hoặc `ChunkContext` trong quá trình chạy Step. Với Tasklet, có thể lấy tham số từ `StepContribution`:

```java
@Bean
@StepScope
Tasklet billingTasklet() {
    return (contribution, chunkContext) -> {
        LocalDate businessDate = (LocalDate) chunkContext
                .getStepContext()
                .getJobParameters()
                .get("businessDate");

        // Thực hiện xử lý cho businessDate.
        return RepeatStatus.FINISHED;
    };
}
```

Trong ứng dụng Spring Batch, `@StepScope` cho phép bean được khởi tạo trong phạm vi StepExecution, nhờ đó có thể truy cập tham số của lần chạy. Cần bảo đảm kiểu dữ liệu lấy ra phù hợp với kiểu đã đưa vào JobParameters.

Với reader hoặc writer, có thể dùng late binding qua `@Value`:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

Ở đây `inputFile` được lấy từ JobParameters của JobExecution hiện tại. `@StepScope` rất quan trọng vì giá trị tham số chỉ có khi Step thực thi; một singleton bean được tạo lúc khởi động ứng dụng không thể tự biết tham số của một lần launch tương lai.

Nếu tham số được lấy từ file hoặc một nguồn ngoài, cần kiểm tra quyền truy cập, đường dẫn, định dạng và sự tồn tại của file trước khi xử lý. Không nên tin tưởng tuyệt đối giá trị do API hoặc người vận hành gửi lên.

## 6. Xác thực JobParameters trước khi xử lý

JobParameters là đầu vào của Job, do đó cần xác thực trước khi bắt đầu công việc. Một Job có thể cần ngày nghiệp vụ, mã file hoặc phạm vi dữ liệu hợp lệ. Nếu thiếu tham số hoặc giá trị không phù hợp, nên từ chối launch sớm để tránh tạo execution thất bại sau khi đã chiếm tài nguyên.

Spring Batch cung cấp `JobParametersValidator`. Có thể dùng validator mặc định hoặc tự triển khai quy tắc nghiệp vụ.

Ví dụ validator yêu cầu `businessDate` và `inputFile`:

```java
public class BillingParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters.getLocalDate("businessDate") == null) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        String inputFile = parameters.getString("inputFile");
        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFile is required");
        }
    }
}
```

Gắn validator vào Job khi xây dựng:

```java
@Bean
Job dailyBillingJob(
        JobRepository jobRepository,
        Step billingStep,
        BillingParametersValidator validator) {

    return new JobBuilder("dailyBillingJob", jobRepository)
            .validator(validator)
            .start(billingStep)
            .build();
}
```

Validator nên kiểm tra tính hợp lệ của tham số ở mức đầu vào: có bắt buộc hay không, kiểu dữ liệu, miền giá trị và quan hệ giữa các tham số. Các quy tắc phụ thuộc dữ liệu thay đổi theo thời gian có thể cần kiểm tra thêm trong Step để tránh kết luận sai ở thời điểm launch.

## 7. Dùng JobParametersIncrementer khi cần instance tiếp theo

Trong một số quy trình, Job cần được chạy nhiều lần mà không có một tham số nghiệp vụ tự nhiên như ngày hoặc mã file. Spring Batch hỗ trợ `JobParametersIncrementer` để tạo bộ tham số cho instance tiếp theo. Một ví dụ quen thuộc là `RunIdIncrementer`, dùng tham số `run.id` tăng dần.

```java
@Bean
Job reportJob(JobRepository jobRepository, Step reportStep) {
    return new JobBuilder("reportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(reportStep)
            .build();
}
```

Incrementer được dùng bởi những cơ chế yêu cầu instance tiếp theo, chẳng hạn `JobOperator.startNextInstance()`. Nó không tự động thay đổi parameters khi ứng dụng gọi trực tiếp `JobLauncher.run(job, parameters)`. Với `JobLauncher.run()`, ứng dụng chịu trách nhiệm xây dựng bộ JobParameters cần truyền.

Không nên dùng `RunIdIncrementer` để né một lỗi restart. Mỗi `run.id` mới tạo một JobInstance mới nếu tham số đó là identifying; Job sẽ có thể xử lý lại dữ liệu từ đầu. Chỉ dùng incrementer khi nghiệp vụ thực sự yêu cầu một lần chạy logic mới.

## 8. Thiết kế JobParameters ổn định và an toàn

Một bộ JobParameters tốt cần mô tả rõ phạm vi công việc và hỗ trợ khôi phục khi cần.

### Chọn identifying parameters theo đơn vị nghiệp vụ

Hãy xác định điều gì làm cho một lần chạy khác với lần chạy khác. Với Job đối soát, có thể là ngày đối soát và mã nguồn dữ liệu. Với Job import, có thể là mã file hoặc phiên bản file. Không chọn tham số identifying chỉ vì nó tiện tạo ra giá trị duy nhất.

### Tránh timestamp tùy tiện

Thêm `LocalDateTime.now()` hoặc UUID vào identifying parameters ở mọi lần launch khiến mỗi lần gọi tạo một instance khác. Khi caller thử lại do timeout, ứng dụng có thể xử lý lại toàn bộ dữ liệu. Nếu mục tiêu là chống request trùng, nên dùng một request ID ổn định hoặc idempotency key được lưu và kiểm tra rõ ràng, thay vì tự sinh một ID mới trong mỗi lần retry.

### Giữ đầu vào bất biến khi restart

Nếu JobParameters chứa đường dẫn file, nội dung tại đường dẫn đó cần ổn định trong suốt lần chạy và các lần restart. Nếu file bị thay thế giữa chừng, checkpoint có thể trỏ đến vị trí không còn đúng. Có thể dùng tên file có version, checksum hoặc lưu bản sao bất biến của dữ liệu đầu vào.

### Không truyền bí mật trong JobParameters

JobParameters thường được lưu trong metadata repository để hỗ trợ lịch sử và restart. Vì vậy, không nên truyền password, access token hoặc thông tin bí mật trực tiếp vào tham số. Hãy truyền một mã tham chiếu đến secret hoặc cấu hình an toàn, sau đó lấy giá trị bí mật từ secret manager hay cơ chế bảo mật của ứng dụng khi cần.

### Kiểm soát kích thước và định dạng

Tránh truyền payload lớn hoặc toàn bộ danh sách bản ghi trong JobParameters. Chỉ truyền định danh, phạm vi hoặc tham chiếu đến dữ liệu. Dữ liệu lớn nên nằm trong file, database hoặc object storage; JobParameters chỉ chứa thông tin để Job tìm đúng nguồn.

## 9. Ví dụ luồng launch từ API

Một API có thể tiếp nhận yêu cầu chạy báo cáo cho một ngày. Controller xác thực request cơ bản, service xây dựng JobParameters và gọi JobLauncher:

```java
@RestController
@RequestMapping("/reports")
public class ReportController {

    private final JobLauncher jobLauncher;
    private final Job dailyReportJob;

    public ReportController(
            JobLauncher jobLauncher,
            Job dailyReportJob) {
        this.jobLauncher = jobLauncher;
        this.dailyReportJob = dailyReportJob;
    }

    @PostMapping
    public ResponseEntity<String> launch(
            @RequestParam LocalDate businessDate) throws Exception {

        JobParameters parameters = new JobParametersBuilder()
                .addLocalDate("businessDate", businessDate, true)
                .toJobParameters();

        JobExecution execution = jobLauncher.run(
                dailyReportJob, parameters);

        return ResponseEntity.accepted().body(
                "Job execution id: " + execution.getId());
    }
}
```

Ví dụ trả HTTP `202 Accepted` để biểu thị yêu cầu đã được tiếp nhận. Đây là cách phù hợp khi Job chạy bất đồng bộ hoặc có thể mất nhiều thời gian. Endpoint trạng thái riêng có thể dùng JobExplorer để trả trạng thái JobExecution cho client. Nếu JobLauncher chạy đồng bộ, controller có thể phải chờ Job hoàn tất trước khi trả response; khi đó cần cân nhắc timeout và cấu hình launcher phù hợp.

Trong production, API cần xử lý trường hợp cùng một ngày đã có Job chạy hoặc đã hoàn tất. Có thể trả mã HTTP phù hợp và thông tin trạng thái hiện có thay vì coi các ngoại lệ launch là lỗi máy chủ không phân loại.

## 10. Các lỗi thường gặp khi truyền JobParameters

**Mỗi lần retry lại tạo timestamp mới:** việc này tạo JobInstance mới, làm mất ý nghĩa restart và có thể khiến dữ liệu bị xử lý lại.

**Đánh dấu tất cả tham số là identifying:** thông tin vận hành như người yêu cầu hoặc địa chỉ thông báo có thể làm phát sinh JobInstance mới không cần thiết.

**Đánh dấu một giá trị nghiệp vụ là non-identifying:** một lần restart có thể sử dụng giá trị khác với lần đầu, dẫn đến kết quả không nhất quán giữa các chunk.

**Truyền sai kiểu dữ liệu:** giá trị được đọc dưới một kiểu khác với kiểu đã lưu có thể gây lỗi chuyển đổi hoặc ép kiểu. Cần thống nhất kiểu tham số giữa nơi launch và nơi đọc.

**Đưa dữ liệu lớn hoặc bí mật vào parameters:** metadata repository có thể lưu các giá trị này, gây phình metadata hoặc lộ thông tin nhạy cảm.

**Cho rằng incrementer tự chạy khi gọi JobLauncher:** `JobLauncher.run()` sử dụng chính bộ parameters được truyền vào; nếu cần instance mới, caller phải tạo tham số phù hợp hoặc dùng cơ chế `startNextInstance`.

**Bỏ qua xác thực đầu vào:** Job có thể bắt đầu rồi thất bại ngay trong Step do thiếu tham số hoặc dữ liệu không hợp lệ. Validator giúp phát hiện sớm những lỗi thuộc phạm vi tham số.

## Kết luận

Khi launch một Job, ứng dụng truyền `JobParameters` vào `JobLauncher.run()`. Tập tham số này vừa cung cấp đầu vào cho công việc vừa xác định JobInstance thông qua những giá trị được đánh dấu identifying. Hãy chọn identifying parameters theo đơn vị nghiệp vụ, dùng non-identifying parameters cho thông tin phụ trợ, xác thực dữ liệu trước khi chạy và giữ các giá trị ảnh hưởng kết quả ổn định qua restart. Khi thiết kế đúng, JobParameters giúp phân biệt lần chạy mới với lần restart, hỗ trợ theo dõi execution và hạn chế việc xử lý trùng ngoài ý muốn.
