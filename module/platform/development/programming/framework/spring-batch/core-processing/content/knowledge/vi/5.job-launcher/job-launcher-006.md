# Job đang chạy và duplicate launch

Khi một ứng dụng gọi JobLauncher để khởi chạy Spring Batch Job, cùng một yêu cầu có thể được gửi nhiều lần: người dùng nhấn nút hai lần, trình duyệt retry HTTP request, scheduler chạy trùng trên nhiều node hoặc message broker giao lại một message. Nếu không kiểm soát, hệ thống có thể tạo nhiều lần xử lý cho cùng một lô dữ liệu.

Spring Batch có cơ chế bảo vệ dựa trên JobInstance, JobExecution và JobRepository. Cơ chế này giúp ngăn hai JobExecution cùng chạy cho một JobInstance, đồng thời phân biệt một lần chạy mới với một lần restart. Tuy nhiên, nó chỉ hoạt động đúng khi JobParameters được thiết kế phù hợp và các tiến trình dùng chung một JobRepository có khả năng điều phối.

## 1. Phân biệt JobInstance và JobExecution

Hai lần gọi JobLauncher với cùng tên Job chưa chắc là hai lần chạy khác nhau. Spring Batch xác định một JobInstance bằng:

- Tên Job.
- Các identifying JobParameters của lần chạy.

Một JobInstance có thể có nhiều JobExecution. Mỗi JobExecution đại diện cho một lần thực thi cụ thể của JobInstance.

~~~text
Job: importOrders
Identifying parameters:
  businessDate = 2026-11-15
  sourceFileId = file-8421

JobInstance A
  JobExecution 101: FAILED
  JobExecution 108: STARTED
  JobExecution 108: COMPLETED
~~~

Trong ví dụ, ba execution thuộc cùng một JobInstance. Execution 108 là lần restart sau khi execution 101 thất bại.

Có thể hiểu:

- **JobInstance** xác định công việc logic cần thực hiện, ví dụ nhập đơn hàng của một ngày hoặc xử lý một file cụ thể.
- **JobExecution** ghi nhận một lần thực thi công việc logic đó, bao gồm thời điểm chạy, trạng thái, lỗi và các StepExecution.
- **JobRepository** lưu metadata của JobInstance, JobExecution, StepExecution và ExecutionContext.

Do đó, “cùng Job” và “cùng JobInstance” là hai khái niệm khác nhau. Duplicate launch được Spring Batch nhận diện dựa trên cùng JobInstance, không chỉ dựa trên tên Job.

## 2. Điều gì xảy ra khi launch cùng một JobInstance?

Khi JobLauncher nhận một Job cùng JobParameters, JobRepository kiểm tra lịch sử execution của JobInstance tương ứng. Kết quả phụ thuộc vào trạng thái của các execution trước đó.

| Trạng thái execution trước | Kết quả thường gặp khi launch lại cùng identifying parameters |
|---|---|
| Đang chạy (STARTING, STARTED) | Ném JobExecutionAlreadyRunningException |
| Đã hoàn thành (COMPLETED) | Ném JobInstanceAlreadyCompleteException |
| Đã bị bỏ (ABANDONED) | JobInstance không thể restart theo cách thông thường; thường nhận JobInstanceAlreadyCompleteException |
| Thất bại (FAILED) | Có thể tạo JobExecution mới để restart nếu Job cho phép restart |
| Đã dừng (STOPPED) | Có thể tạo JobExecution mới để tiếp tục nếu trạng thái và cấu hình cho phép |

Điều này có nghĩa một lời gọi trùng khi Job đang chạy không tạo thêm một JobExecution chạy đồng thời cho cùng JobInstance. Lời gọi thứ hai nhận lỗi để ứng dụng biết công việc đã được khởi chạy.

Nếu execution trước đã hoàn thành, Spring Batch cũng không tự chạy lại JobInstance đó. Nếu execution trước thất bại hoặc dừng, một lần gọi cùng parameters có thể là yêu cầu restart hợp lệ. Khi restart, Spring Batch sử dụng metadata và checkpoint đã lưu để tiếp tục theo quy tắc restart của Job và Step.

Một Job được cấu hình không cho restart có thể từ chối việc chạy lại sau thất bại bằng JobRestartException.

## 3. Nhận diện duplicate launch qua JobParameters

Ví dụ dưới đây tạo parameters cho Job nhập đơn hàng:

~~~java
JobParameters jobParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFileId", "file-8421", true)
        .addString("requestId", requestId, false)
        .toJobParameters();
~~~

Tham số thứ ba của các phương thức addString là cờ identifying:

- businessDate và sourceFileId là identifying. Chúng xác định lô nghiệp vụ cần xử lý.
- requestId là non-identifying. Nó có thể dùng để trace yêu cầu hoặc ghi log nhưng không làm thay đổi danh tính JobInstance.

Nếu hai request có cùng tên Job, cùng businessDate và sourceFileId, chúng trỏ đến cùng JobInstance dù requestId khác nhau.

Nếu đánh dấu requestId là identifying, mỗi request có thể tạo ra một JobInstance riêng. Khi đó, hai request thực chất cùng yêu cầu xử lý một file vẫn có thể chạy thành hai JobInstance khác nhau.

### Chọn identifying parameters theo nghiệp vụ

Một identifying parameter nên đại diện cho đơn vị công việc mà hệ thống chỉ muốn xử lý một lần tại một thời điểm hoặc một lần trong vòng đời của nó.

Ví dụ:

| Job | Identifying parameters phù hợp |
|---|---|
| Nhập file đơn hàng | ID file bất biến hoặc checksum file |
| Tổng hợp doanh thu ngày | Ngày nghiệp vụ và mã tenant |
| Đồng bộ một tài khoản | Mã tài khoản và phiên bản dữ liệu cần đồng bộ |
| Xử lý một lô message | Mã batch hoặc khoảng offset |
| Tạo báo cáo theo kỳ | Kỳ báo cáo và loại báo cáo |

Tránh dùng timestamp hiện tại, UUID mới hoặc request ID mới làm identifying parameter nếu mục tiêu là để Spring Batch nhận ra các request lặp lại cho cùng một công việc. Mỗi giá trị mới như vậy sẽ tạo danh tính JobInstance mới.

Nếu một file có thể được ghi đè tại cùng đường dẫn, chỉ dùng đường dẫn làm identifying parameter có thể không đủ. Nên dùng file ID bất biến, checksum hoặc version để phân biệt nội dung thực tế.

## 4. Gọi JobLauncher và xử lý các lỗi duplicate

Một ứng dụng thường gọi JobLauncher từ service hoặc controller. Ví dụ dưới đây minh họa việc tạo JobParameters ổn định và xử lý các trường hợp launcher từ chối yêu cầu:

~~~java
@Service
public class OrderImportService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public OrderImportService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(
            String businessDate,
            String sourceFileId,
            String requestId) throws Exception {

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("sourceFileId", sourceFileId, true)
                .addString("requestId", requestId, false)
                .toJobParameters();

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
~~~

Ở tầng gọi, cần xử lý các exception mà JobLauncher có thể ném:

~~~java
try {
    JobExecution execution =
            orderImportService.launch(businessDate, fileId, requestId);

    return ResponseEntity.accepted()
            .body(execution.getId());
} catch (JobExecutionAlreadyRunningException ex) {
    // JobInstance tương ứng đang có execution chạy.
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("Job cho lô dữ liệu này đang chạy");
} catch (JobInstanceAlreadyCompleteException ex) {
    // JobInstance đã hoàn thành.
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("Lô dữ liệu này đã được xử lý");
} catch (JobRestartException ex) {
    // JobInstance không thể restart theo cấu hình hoặc trạng thái hiện tại.
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("Không thể restart JobInstance");
} catch (JobParametersInvalidException ex) {
    // Parameters không hợp lệ theo validator của Job.
    return ResponseEntity.badRequest()
            .body("Job parameters không hợp lệ");
}
~~~

Đoạn controller chỉ minh họa cách ánh xạ kết quả. Trong ứng dụng thực tế, nên trả về một response DTO có mã JobExecution, JobInstance hoặc mã yêu cầu phù hợp, đồng thời ghi log exception và correlation ID.

JobExecutionAlreadyRunningException là tín hiệu rằng một execution của JobInstance đã tồn tại và đang chạy. Không nên coi exception này như một lỗi hệ thống không xác định. Ứng dụng có thể phản hồi rằng công việc đang được xử lý, hoặc truy vấn metadata để hiển thị trạng thái execution hiện tại nếu có đủ thông tin nhận diện.

JobInstanceAlreadyCompleteException lại mang nghĩa khác: công việc logic đã hoàn thành. Nếu người dùng muốn xem kết quả, ứng dụng nên truy vấn kết quả nghiệp vụ hoặc execution đã hoàn thành. Nếu người dùng thực sự muốn chạy một lượt nghiệp vụ mới, cần tạo JobInstance mới theo một định danh nghiệp vụ có chủ đích.

## 5. JobLauncher chạy đồng bộ và bất đồng bộ

JobLauncher không nhất thiết thực hiện công việc trên cùng thread với request gọi nó. Cách thực thi phụ thuộc vào TaskExecutor được cấu hình cho launcher.

### Chạy đồng bộ

Với executor đồng bộ, ví dụ SyncTaskExecutor, lời gọi run() thực hiện Job trên thread gọi và thường chỉ trả về khi Job kết thúc.

~~~text
HTTP request
    |
    v
JobLauncher.run()
    |
    v
Job thực thi trên request thread
    |
    v
Job hoàn tất
    |
    v
HTTP response
~~~

Cách này đơn giản, phù hợp với job ngắn hoặc môi trường thử nghiệm. Tuy nhiên, request có thể phải chờ lâu và dễ gặp timeout nếu Job xử lý lượng dữ liệu lớn.

### Chạy bất đồng bộ

Với executor bất đồng bộ, launcher tạo JobExecution và giao công việc cho thread thực thi. Lời gọi run() có thể trả về trước khi Job hoàn tất.

~~~text
HTTP request
    |
    v
JobLauncher.run()
    |
    +----> trả JobExecution (STARTING/STARTED)
    |
    v
TaskExecutor
    |
    v
Job thực thi nền
    |
    v
COMPLETED hoặc FAILED
~~~

Trong trường hợp này, response HTTP thường chỉ xác nhận đã tiếp nhận yêu cầu. Trạng thái Job có thể vẫn là STARTING hoặc STARTED. Client cần dùng JobExecution ID hoặc một mã công việc để truy vấn trạng thái sau đó.

Cấu hình executor bất đồng bộ không tự ngăn duplicate launch. Cơ chế kiểm tra JobInstance và điều phối của JobRepository vẫn là phần quan trọng để các request trùng không cùng chạy một JobInstance.

## 6. Vì sao hai request đồng thời vẫn cần JobRepository điều phối?

Giả sử hai node nhận cùng một sự kiện gần như đồng thời:

~~~text
Node A                         Node B
  |                              |
  | launch Job + parameters      | launch Job + same parameters
  v                              v
JobRepository  <------------> JobRepository
  |                              |
  | tạo JobExecution             | kiểm tra JobInstance
  v                              v
STARTED                      Already running
  |                              |
  v                              v
Job chạy                     JobExecutionAlreadyRunningException
~~~

Nếu cả hai node dùng chung một JobRepository bền vững, repository có thể điều phối việc tạo JobExecution cho cùng JobInstance. Các thao tác tạo execution được bảo vệ bằng transaction và mức cô lập phù hợp. Cấu hình mặc định của Spring Batch sử dụng isolation level chặt cho thao tác tạo execution để tránh hai tiến trình cùng tạo execution chạy cho một JobInstance.

Cơ chế này chỉ có ý nghĩa khi các node thực sự dùng chung repository và metadata database. Nếu mỗi node dùng repository riêng hoặc một repository chỉ tồn tại trong bộ nhớ, chúng không nhìn thấy trạng thái của nhau. Khi đó, cả hai node có thể tin rằng JobInstance chưa chạy và cùng xử lý dữ liệu.

Với ứng dụng triển khai nhiều instance, cần bảo đảm:

- Tất cả node dùng cùng JobRepository và cùng kho metadata bền vững.
- Các bảng metadata của Spring Batch được cấu hình và duy trì đúng.
- Transaction manager và transaction isolation của repository được cấu hình phù hợp với database.
- Không tự sửa hoặc xóa metadata đang được dùng để điều phối execution.
- Không tạo một JobRepository độc lập cho từng node nếu muốn chống duplicate ở cấp cụm.

## 7. Duplicate launch từ HTTP, scheduler và message broker

Duplicate launch có thể xuất phát từ nhiều tầng khác nhau. Xác định đúng nguồn giúp chọn biện pháp bảo vệ phù hợp.

### Người dùng nhấn nút nhiều lần hoặc HTTP retry

Một request có thể được gửi lại khi người dùng nhấn nút hai lần, trình duyệt retry hoặc gateway không nhận được response kịp thời. Request đầu có thể đã khởi chạy Job dù client tưởng rằng nó thất bại.

Cách xử lý:

- Dùng một business key ổn định làm identifying JobParameters.
- Vô hiệu hóa nút khởi chạy trong giao diện khi request đang được gửi để cải thiện trải nghiệm.
- Có thể dùng idempotency key ở API để nhận diện request lặp.
- Trả về mã công việc hoặc trạng thái hiện tại để client truy vấn thay vì khởi chạy lại vô điều kiện.

Vô hiệu hóa nút chỉ là hỗ trợ giao diện; nó không bảo vệ được khi có retry từ proxy hoặc request từ một client khác.

### Scheduler chạy trên nhiều node

Nếu mỗi application instance đều chạy cùng một lịch, nhiều node có thể cùng phát yêu cầu khởi chạy. Dùng JobParameters giống nhau và một JobRepository dùng chung giúp Spring Batch nhận diện cùng JobInstance.

Tuy nhiên, nếu mỗi node tự thêm timestamp hoặc run ID mới, các lần chạy sẽ thành các JobInstance khác nhau. Khi đó, cơ chế chống execution trùng của cùng JobInstance không thể hợp nhất chúng.

Có thể bổ sung cơ chế khóa scheduler phân tán hoặc leader election để chỉ một node phát trigger. Đây là lớp điều phối ở tầng scheduler, hữu ích khi muốn tránh cả việc nhiều node cùng phát request, kể cả trước khi JobRepository kiểm tra.

### Message broker giao lại message

Broker có thể giao lại cùng một message nếu consumer bị ngắt kết nối, timeout hoặc chưa xác nhận message. Consumer nên chuyển định danh message hoặc mã batch nghiệp vụ thành identifying JobParameters nếu mỗi message đại diện cho một đơn vị công việc riêng.

Ngoài JobRepository, nên có cơ chế idempotency ở tầng consumer hoặc business database. Việc một JobInstance chỉ chạy một lần tại một thời điểm không tự bảo đảm rằng mọi tác động bên ngoài như gửi email, gọi API hoặc phát message sẽ không bị lặp khi restart.

## 8. JobRepository bảo vệ đến đâu?

JobRepository giải quyết việc quản lý metadata và trạng thái thực thi của JobInstance/JobExecution. Nó giúp ngăn các execution chạy đồng thời cho cùng JobInstance và áp dụng quy tắc restart của Spring Batch.

Nó không tự giải quyết mọi dạng duplicate trong nghiệp vụ.

| Tình huống | JobRepository xử lý? | Cơ chế cần cân nhắc |
|---|---|---|
| Hai request cùng Job và cùng identifying parameters, execution đang chạy | Có, với repository dùng chung và cấu hình đúng | Xử lý JobExecutionAlreadyRunningException |
| Launch lại cùng JobInstance đã hoàn thành | Có | Hiển thị kết quả hoặc tạo instance mới có chủ đích |
| Hai request cùng nghiệp vụ nhưng khác identifying parameters | Không nhận ra là cùng công việc | Chuẩn hóa business key và parameters |
| Hai node dùng repository riêng | Không phối hợp được giữa các node | Dùng repository chung, bền vững |
| Writer gửi email rồi restart | Không tự chống gửi trùng | Idempotency hoặc outbox |
| Hai Job khác tên cùng ghi một tập dữ liệu | Không xem là cùng JobInstance | Unique constraint hoặc khóa nghiệp vụ |
| Một scheduler phát trigger lặp với run ID mới | Mỗi lần có thể thành instance mới | Scheduler lock và định danh công việc ổn định |

Vì vậy, không nên xem JobRepository như một hệ thống khóa nghiệp vụ tổng quát. Nó điều phối execution theo danh tính JobInstance mà Spring Batch nhận được.

## 9. Chủ động cho phép chạy một JobInstance mới

Có trường hợp người vận hành thật sự muốn chạy lại công việc sau khi một JobInstance đã hoàn thành, ví dụ tạo lại báo cáo với một phiên bản nghiệp vụ mới hoặc xử lý một lần hiệu chỉnh riêng.

Có thể thêm một identifying parameter đại diện cho lượt chạy nghiệp vụ mới:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("reportVersion", "revision-2", true)
        .toJobParameters();
~~~

Vì reportVersion là identifying, bộ parameters này tạo JobInstance khác với lần chạy có reportVersion=revision-1.

Spring Batch cũng có cơ chế JobParametersIncrementer, thường dùng với RunIdIncrementer, để tạo bộ parameters tiếp theo. Ví dụ:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(importOrdersStep)
            .build();
}
~~~

Incrementer phù hợp khi nghiệp vụ thực sự cần các JobInstance kế tiếp. Không nên tự động thêm run ID mới cho mọi request nếu mục tiêu là loại bỏ duplicate launch. Mỗi run ID khác nhau sẽ khiến JobRepository coi đó là một JobInstance khác.

Nếu cần restart một JobInstance đã thất bại, phải sử dụng đúng identifying parameters của instance đó. Không thêm run ID mới chỉ để “thử lại”, vì như vậy có thể khởi động một instance mới từ đầu và bỏ qua checkpoint của lần trước.

## 10. Kiểm tra trạng thái Job đang chạy

Khi một request bị từ chối vì JobInstance đang chạy, ứng dụng có thể cần cung cấp trạng thái hiện tại cho người dùng hoặc hệ thống gọi.

JobExplorer là API đọc metadata của Spring Batch. Ví dụ, có thể tìm các execution đang chạy theo tên Job:

~~~java
@Service
public class BatchStatusQueryService {

    private final JobExplorer jobExplorer;

    public BatchStatusQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public Set<JobExecution> findRunningExecutions(String jobName) {
        return jobExplorer.findRunningJobExecutions(jobName);
    }
}
~~~

Kết quả là tập JobExecution đang chạy của Job có tên tương ứng. Nếu Job có nhiều JobInstance, cần so sánh identifying JobParameters để tìm execution của đúng đơn vị nghiệp vụ. Không nên chỉ lấy execution đầu tiên trong tập kết quả và coi đó là request hiện tại.

Một response trạng thái có thể chứa:

- JobExecution ID.
- JobInstance ID.
- Tên Job.
- BatchStatus và ExitStatus.
- Thời điểm bắt đầu, kết thúc và thời điểm cập nhật gần nhất nếu có.
- Step đang chạy và các bộ đếm tiến độ quan trọng.

JobExplorer phục vụ truy vấn metadata. Nó không thay thế JobLauncher và không nên được dùng để sửa trực tiếp trạng thái execution.

## 11. Phân biệt duplicate launch, restart và rerun

Ba thao tác này thường bị nhầm lẫn:

**Duplicate launch:** Một request khác cố khởi chạy cùng JobInstance trong khi execution hiện tại đang chạy. Spring Batch từ chối request trùng bằng JobExecutionAlreadyRunningException.

**Restart:** Một JobInstance có execution trước thất bại hoặc bị dừng được khởi chạy lại với cùng identifying parameters. Spring Batch tạo JobExecution mới và phục hồi từ metadata/checkpoint theo cấu hình.

**Rerun:** Nghiệp vụ muốn thực hiện một lượt công việc logic mới. Cần tạo JobInstance mới bằng một identifying parameter mới có ý nghĩa nghiệp vụ hoặc một incrementer được dùng có chủ đích.

Ví dụ:

~~~text
businessDate=2026-11-15, sourceFileId=file-8421

JobExecution 101: STARTED
  -> request trùng: JobExecutionAlreadyRunningException

JobExecution 101: FAILED
  -> gọi lại cùng parameters: restart JobInstance
  -> JobExecution 108

JobExecution 108: COMPLETED
  -> gọi lại cùng parameters: JobInstanceAlreadyCompleteException

reportVersion=revision-2
  -> JobInstance mới, có thể chạy một lượt nghiệp vụ mới
~~~

Việc chọn đúng thao tác rất quan trọng. Duplicate launch cần được phản hồi là công việc đã tồn tại; restart cần giữ định danh và checkpoint; rerun cần một định danh nghiệp vụ mới để lịch sử execution không bị nhập nhằng.

## 12. Checklist thiết kế chống duplicate launch

Khi triển khai JobLauncher trong ứng dụng thực tế, hãy xem xét các điểm sau:

1. Xác định business key cho một đơn vị công việc, ví dụ file ID, ngày nghiệp vụ hoặc batch ID.
2. Đưa business key vào identifying JobParameters.
3. Giữ request ID, correlation ID và thông tin trace ở dạng non-identifying nếu chúng không làm thay đổi đơn vị công việc.
4. Không tạo timestamp hoặc run ID mới cho mọi request khi cần nhận diện request lặp.
5. Dùng JobRepository bền vững và dùng chung giữa các application node.
6. Xử lý rõ JobExecutionAlreadyRunningException, JobInstanceAlreadyCompleteException, JobRestartException và JobParametersInvalidException.
7. Phân biệt xác nhận tiếp nhận yêu cầu với xác nhận Job đã hoàn thành, đặc biệt khi launcher chạy bất đồng bộ.
8. Bảo vệ các tác động nghiệp vụ ngoài transaction bằng idempotency, unique constraint hoặc outbox.
9. Nếu scheduler chạy nhiều node, cân nhắc khóa phân tán hoặc cơ chế chỉ định node phát trigger.
10. Cung cấp API tra cứu JobExecution để người dùng biết công việc đang chạy, đã hoàn thành hay thất bại.

Một hệ thống launch an toàn cần kết hợp định danh JobInstance ổn định, JobRepository dùng chung, xử lý exception đúng và tính idempotent ở tầng nghiệp vụ. Nhờ đó, request lặp có thể được nhận diện, restart được thực hiện đúng cách và một lượt xử lý mới chỉ được tạo khi có chủ đích rõ ràng.

