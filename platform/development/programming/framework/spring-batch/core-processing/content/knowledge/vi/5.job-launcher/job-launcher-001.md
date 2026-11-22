# JobLauncher khởi chạy JobExecution

Trong Spring Batch, `Job` mô tả một quy trình batch, còn `JobExecution` đại diện cho một lần thực thi cụ thể của quy trình đó. Thành phần nhận yêu cầu chạy job và khởi động lần thực thi là `JobLauncher`.

`JobLauncher` thường được gọi từ một service của ứng dụng, một scheduler, một REST endpoint hoặc một thành phần điều phối khác. Nó nhận một `Job` cùng `JobParameters`, phối hợp với `JobRepository` để tạo thông tin thực thi, sau đó yêu cầu job chạy. Kết quả trả về là một đối tượng `JobExecution` chứa metadata về lần chạy đó.

Để hiểu đúng vai trò của JobLauncher, cần phân biệt việc **khởi chạy** với việc **định nghĩa và thực hiện nghiệp vụ**. JobLauncher không quyết định job cần làm những bước nào và cũng không đọc hay ghi dữ liệu nghiệp vụ. Những trách nhiệm đó thuộc về `Job`, các `Step` và các thành phần reader, processor, writer hoặc tasklet.

## 1. JobLauncher nằm ở đâu trong kiến trúc?

Một luồng khởi chạy cơ bản có thể hình dung như sau:

```text
Người dùng / REST API / Scheduler / Application
                     |
                     v
                JobLauncher
                     |
                     v
          JobRepository tạo execution
                     |
                     v
                    Job
                     |
              +------+------+
              |             |
              v             v
            Step 1        Step 2
              |             |
              +------+------+
                     |
                     v
              JobExecution
              (trạng thái và kết quả)
```

Các thành phần liên quan có trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| `Job` | Định nghĩa quy trình batch và các step. |
| `JobLauncher` | Nhận yêu cầu chạy một job với bộ tham số cụ thể và khởi động execution. |
| `JobRepository` | Lưu metadata về JobInstance, JobExecution, StepExecution và ExecutionContext. |
| `JobParameters` | Cung cấp dữ liệu đầu vào cho lần chạy và xác định JobInstance thông qua các tham số identifying. |
| `JobExecution` | Đại diện cho một lần thực thi cụ thể, lưu trạng thái, thời gian, ExitStatus và thông tin lỗi. |
| `Step` | Thực hiện một giai đoạn trong job. |

Thông thường, ứng dụng inject `JobLauncher` và bean `Job` vào service hoặc thành phần điều phối. JobLauncher sử dụng JobRepository để đăng ký execution trước khi gọi job thực thi.

## 2. JobInstance và JobExecution khi khởi chạy

Hai lần gọi JobLauncher có thể tạo ra các execution thuộc cùng một JobInstance hoặc thuộc hai JobInstance khác nhau. Điều này phụ thuộc vào tên job và các identifying `JobParameters`.

Ví dụ, job `importOrdersJob` xử lý đơn hàng theo ngày nghiệp vụ:

```text
Job: importOrdersJob

JobParameters:
  businessDate = 2026-11-15 (identifying)
  inputFile    = orders.csv (identifying)

                |
                v
JobInstance: importOrdersJob / 2026-11-15 / orders.csv
                |
                +-- JobExecution #1
                +-- JobExecution #2 (nếu restart được phép)
```

`JobInstance` xác định đơn vị xử lý logic. `JobExecution` ghi nhận từng lần thực thi cụ thể. Khi một lần chạy thất bại và được restart bằng cùng các identifying parameters, Spring Batch tạo một JobExecution mới thuộc cùng JobInstance.

Nếu thay đổi một identifying parameter, chẳng hạn ngày nghiệp vụ, JobLauncher sẽ làm việc với một JobInstance khác. Vì vậy, cách xây dựng tham số có ảnh hưởng trực tiếp đến việc chạy mới hay restart.

## 3. Gọi JobLauncher để chạy một Job

API chính của `JobLauncher` là:

```java
JobExecution run(Job job, JobParameters jobParameters)
```

Phương thức nhận hai đối số:

- `job`: bean Job đã được cấu hình trong Spring application context.
- `jobParameters`: tập tham số đầu vào cho lần chạy.

Ví dụ tạo tham số và khởi chạy job:

```java
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

    public JobExecution launch(String inputFile, String businessDate)
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", inputFile, true)
                .addString("businessDate", businessDate, true)
                .toJobParameters();

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

Trong ví dụ, `inputFile` và `businessDate` được đánh dấu là identifying. Hai giá trị này cùng tên job xác định JobInstance. Service không tự thực hiện các bước import; nó chỉ chuẩn bị tham số và giao yêu cầu thực thi cho JobLauncher.

Các bean `JobLauncher` và `importOrdersJob` phải được cấu hình trong application context. Với Spring Boot, cấu hình Spring Batch tự động có thể cung cấp các thành phần hạ tầng nếu ứng dụng có dependency và cấu hình phù hợp. Trong ứng dụng cấu hình Spring Batch trực tiếp, cần khai báo JobRepository và launcher tương ứng.

## 4. Điều gì xảy ra bên trong một lần gọi run()?

Ở mức khái niệm, quá trình khởi chạy diễn ra theo các bước sau:

1. Thành phần gọi truyền `Job` và `JobParameters` vào `JobLauncher.run`.
2. JobLauncher phối hợp với `JobRepository` để tạo hoặc tìm `JobInstance` tương ứng và đăng ký một `JobExecution` mới.
3. Spring Batch kiểm tra các điều kiện thực thi, bao gồm tính hợp lệ của tham số và khả năng chạy hoặc restart instance theo trạng thái hiện tại.
4. Job được thực thi với JobExecution vừa tạo.
5. Job điều phối các step. Mỗi step cập nhật metadata và trạng thái thực thi của mình thông qua JobRepository.
6. Khi job kết thúc, JobExecution phản ánh trạng thái và kết quả của lần chạy.

Trình tự chi tiết của việc xác thực, đăng ký metadata và thực thi có thể phụ thuộc implementation và phiên bản Spring Batch. Điểm quan trọng là JobLauncher làm việc với JobRepository để quản lý lần chạy, còn Job và Step mới chứa logic xử lý.

JobLauncher không tự tạo một JobInstance mới cho mọi lần gọi. Nó dựa vào tên job và identifying parameters, đồng thời tuân theo trạng thái đã lưu. Ví dụ, một instance đang chạy có thể bị từ chối khi khởi chạy thêm execution; một instance đã hoàn tất cũng thường không thể được chạy lại với cùng tham số như một lần chạy mới.

## 5. JobExecution trả về chứa thông tin gì?

`JobLauncher.run` trả về `JobExecution`. Đối tượng này đại diện cho lần thực thi mà launcher đã đăng ký. Nó cung cấp những thông tin quan trọng để ứng dụng theo dõi và phản hồi kết quả.

| Thông tin | Ý nghĩa |
|---|---|
| `id` | Định danh của JobExecution trong metadata repository. |
| `jobInstance` | JobInstance mà execution này thuộc về. |
| `jobParameters` | Bộ tham số đã dùng để khởi chạy. |
| `status` | Trạng thái thực thi như `STARTING`, `STARTED`, `COMPLETED`, `FAILED` hoặc `STOPPED`. |
| `startTime` | Thời điểm bắt đầu execution. |
| `endTime` | Thời điểm kết thúc execution, nếu đã kết thúc. |
| `exitStatus` | Kết quả kết thúc, có thể chứa mã tùy chỉnh và mô tả. |
| `stepExecutions` | Tập các StepExecution thuộc execution này. |
| `executionContext` | Trạng thái key-value ở phạm vi job execution. |
| `failureExceptions` | Các exception được ghi nhận trong quá trình thực thi. |

Ví dụ đọc một số thông tin sau khi gọi launcher:

```java
JobExecution execution = jobLauncher.run(job, parameters);

System.out.println("Execution ID: " + execution.getId());
System.out.println("Job status: " + execution.getStatus());
System.out.println("Exit status: " + execution.getExitStatus());
System.out.println("Start time: " + execution.getStartTime());
System.out.println("End time: " + execution.getEndTime());
```

Nếu launcher chạy đồng bộ, khi `run` trả về thông thường job đã kết thúc và các thông tin trạng thái phản ánh kết quả cuối cùng. Nếu launcher chạy bất đồng bộ, `run` có thể trả về khi job mới bắt đầu hoặc vẫn đang chạy. Trong trường hợp đó, không được coi trạng thái ban đầu của đối tượng trả về là kết quả cuối cùng.

## 6. Chạy đồng bộ và bất đồng bộ

`JobLauncher` có thể thực thi job trên luồng gọi hoặc giao công việc cho một executor khác. Sự khác biệt này ảnh hưởng đến cách ứng dụng chờ kết quả và phản hồi cho người dùng.

### Chạy đồng bộ

Với cách thực thi đồng bộ, luồng gọi `run` chờ job thực hiện xong rồi mới nhận lại kết quả. Đây là cách dễ hiểu và thuận tiện cho job ngắn hoặc các chương trình chạy batch theo lịch mà không cần trả lời request ngay lập tức.

```text
Thread gọi API
    |
    +---- JobLauncher.run() ----------------------+
    |                                             |
    |                                      Job thực thi
    |                                             |
    +<----------- JobExecution hoàn tất ----------+
    |
    v
Xử lý kết quả cuối cùng
```

Ưu điểm là nơi gọi có thể đọc trạng thái cuối cùng ngay sau khi `run` trả về. Nhược điểm là luồng gọi phải chờ trong suốt thời gian job chạy. Nếu gọi từ HTTP request và job kéo dài, request có thể chiếm một thread lâu hoặc vượt timeout của gateway.

### Chạy bất đồng bộ

Với cách thực thi bất đồng bộ, launcher sử dụng `TaskExecutor` để thực thi job trên một luồng khác. Phương thức `run` có thể trả về JobExecution trước khi các step hoàn tất.

```text
Thread gọi API                         Worker thread
     |                                      |
     +-- JobLauncher.run() ---------------->|
     |                                      +-- chạy Job
     |                                      +-- chạy các Step
     |<-- JobExecution đang thực thi         |
     |                                      +-- cập nhật metadata
     v                                      +-- kết thúc Job
Trả execution ID
```

Trong trường hợp này, nơi gọi nên lưu hoặc trả về execution ID để người dùng có thể tra cứu trạng thái sau. Không nên đọc ngay `execution.getStatus()` rồi khẳng định job đã thành công nếu job vẫn đang chạy.

Spring Batch cung cấp `TaskExecutorJobLauncher` để cấu hình launcher sử dụng một `TaskExecutor`. Trong ứng dụng Spring Boot, launcher có thể được cấu hình tự động; nếu cần hành vi bất đồng bộ hoặc executor riêng, hãy cấu hình theo phiên bản Spring Batch và Spring Boot đang dùng.

Ví dụ cấu hình launcher với executor:

```java
@Bean
TaskExecutorJobLauncher jobLauncher(
        JobRepository jobRepository,
        TaskExecutor taskExecutor) throws Exception {

    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(taskExecutor);
    launcher.afterPropertiesSet();
    return launcher;
}
```

Bean `taskExecutor` cần được cấu hình riêng. Với môi trường production, nên chọn executor có giới hạn thread và hàng đợi phù hợp, đồng thời quản lý vòng đời và khả năng shutdown. Không nên mặc định tạo vô hạn thread khi người dùng có thể gửi nhiều yêu cầu khởi chạy cùng lúc.

## 7. Xử lý kết quả khởi chạy và các ngoại lệ thường gặp

Phương thức `run` có thể phát sinh các ngoại lệ thể hiện việc yêu cầu khởi chạy không thể được chấp nhận:

| Ngoại lệ | Nguyên nhân thường gặp |
|---|---|
| `JobExecutionAlreadyRunningException` | JobInstance tương ứng đang có một execution hoạt động. |
| `JobInstanceAlreadyCompleteException` | JobInstance đã hoàn tất và không thể được chạy lại theo cách thông thường với cùng identifying parameters. |
| `JobRestartException` | Không thể restart instance hoặc execution theo trạng thái và cấu hình hiện tại. |
| `JobParametersInvalidException` | Bộ tham số không hợp lệ theo quy tắc kiểm tra của job. |

Ví dụ xử lý ở lớp điều phối:

```java
public JobExecution launchImport(Job job, JobParameters parameters) {
    try {
        return jobLauncher.run(job, parameters);
    } catch (JobExecutionAlreadyRunningException ex) {
        throw new IllegalStateException(
                "Job instance is already running", ex);
    } catch (JobInstanceAlreadyCompleteException ex) {
        throw new IllegalStateException(
                "Job instance has already completed", ex);
    } catch (JobRestartException ex) {
        throw new IllegalStateException(
                "Job instance cannot be restarted", ex);
    } catch (JobParametersInvalidException ex) {
        throw new IllegalArgumentException(
                "Invalid job parameters", ex);
    }
}
```

Trong ứng dụng thực tế, có thể ánh xạ các trường hợp này thành mã phản hồi API hoặc thông báo phù hợp cho hệ thống gọi. Không nên gộp mọi ngoại lệ thành một thông báo “job thất bại” vì một số lỗi xảy ra ngay tại bước tiếp nhận yêu cầu, trước khi job có thể chạy nghiệp vụ.

Ngoài các ngoại lệ khởi chạy, job có thể được khởi chạy thành công nhưng sau đó kết thúc với `BatchStatus.FAILED`. Đây là hai loại kết quả khác nhau:

- **Không khởi chạy được:** launcher không thể chấp nhận yêu cầu, ví dụ instance đang chạy hoặc parameters không hợp lệ.
- **Đã khởi chạy nhưng thực thi thất bại:** JobExecution đã được tạo và job đã chạy, nhưng một step hoặc logic trong job phát sinh lỗi.

Với trường hợp thứ hai, hãy đọc trạng thái JobExecution, StepExecution, ExitStatus và failure exceptions để tìm nguyên nhân.

## 8. JobLauncher không phải scheduler và không phải JobOperator

Các thành phần điều phối batch có thể có tên gần nhau nhưng vai trò khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `JobLauncher` | Khởi chạy một Job với JobParameters. |
| Scheduler (ví dụ Spring Scheduling hoặc Quartz) | Quyết định khi nào cần gửi yêu cầu chạy job. |
| `JobExplorer` | Tra cứu metadata và trạng thái các job execution đã lưu. |
| `JobOperator` | Cung cấp API vận hành cấp cao hơn như start, restart, stop hoặc tra cứu execution theo khả năng của phiên bản. |
| `JobRepository` | Lưu metadata thực thi để framework quản lý và khôi phục trạng thái. |

Ví dụ, scheduler có thể gọi một service vào lúc nửa đêm. Service chuẩn bị JobParameters và gọi JobLauncher. Scheduler chịu trách nhiệm thời điểm chạy; JobLauncher chịu trách nhiệm tiếp nhận và khởi động execution.

Nếu ứng dụng cần một giao diện quản trị để tìm execution thất bại rồi restart hoặc dừng job, `JobOperator` và `JobExplorer` có thể phù hợp hơn. Không nên dùng JobLauncher như một bộ lập lịch hoặc một API quản trị đầy đủ.

## 9. Khởi chạy từ REST API

Một ứng dụng có thể cung cấp endpoint để người dùng yêu cầu chạy batch. Endpoint nên xác thực đầu vào, tạo parameters có ý nghĩa nghiệp vụ và trả kết quả phù hợp với chế độ đồng bộ hay bất đồng bộ.

Ví dụ minh họa cho một endpoint khởi chạy:

```java
@RestController
@RequestMapping("/batch")
public class BatchController {

    private final OrderImportService orderImportService;

    public BatchController(OrderImportService orderImportService) {
        this.orderImportService = orderImportService;
    }

    @PostMapping("/orders")
    public ResponseEntity<Map<String, Object>> importOrders(
            @RequestParam String inputFile,
            @RequestParam String businessDate) throws Exception {

        JobExecution execution = orderImportService.launch(
                inputFile, businessDate);

        Map<String, Object> body = Map.of(
                "executionId", execution.getId(),
                "status", execution.getStatus().toString());

        return ResponseEntity.accepted().body(body);
    }
}
```

Đây là ví dụ đơn giản về cách nối HTTP request với service khởi chạy. Trong ứng dụng thật, cần kiểm tra quyền truy cập, xác thực đường dẫn file, kiểm soát loại job được phép chạy và xử lý các ngoại lệ ở tầng web.

Nếu launcher bất đồng bộ, phản hồi `202 Accepted` cùng execution ID thường phù hợp hơn việc chờ job hoàn tất trong request. Ứng dụng có thể cung cấp endpoint trạng thái riêng, dùng `JobExplorer` để tra cứu execution từ repository. Nếu launcher đồng bộ, chỉ trả `202` cũng không có nghĩa job đang chạy bất đồng bộ; mã HTTP nên phản ánh hợp đồng thực tế của API.

Không nên cho phép client truyền tùy ý tên class, tên bean hoặc đường dẫn hệ thống để chọn job. Hãy dùng một tập job được ứng dụng cho phép và validate mọi tham số đầu vào.

## 10. JobParameters và việc tránh khởi chạy trùng

JobLauncher phối hợp với JobRepository để bảo vệ danh tính và trạng thái của JobInstance. Vì thế, thiết kế JobParameters cần gắn với ý nghĩa nghiệp vụ.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSystem", "ERP", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Trong trường hợp này, ngày nghiệp vụ và hệ thống nguồn xác định đơn vị dữ liệu cần xử lý. `requestedBy` chỉ là thông tin bổ sung, không làm thay đổi JobInstance.

Một số lỗi thiết kế phổ biến:

- Thêm timestamp hoặc UUID làm identifying parameter trong mọi lần gọi, khiến mỗi yêu cầu trở thành một JobInstance mới và làm mất khả năng nhận diện instance cần restart.
- Dùng cùng tham số identifying cho hai lần xử lý nghiệp vụ khác nhau, khiến lần chạy sau gặp lỗi instance đã hoàn tất hoặc đang chạy.
- Dùng một giá trị mặc định không phản ánh kỳ nghiệp vụ, khiến nhiều yêu cầu khác nhau vô tình cùng nhận một JobInstance.
- Không validate đường dẫn file, ngày xử lý hoặc phạm vi dữ liệu trước khi khởi chạy.

Nếu nghiệp vụ cần tạo một lần xử lý mới cho cùng loại job, hãy thiết kế identifying parameters thể hiện rõ đơn vị xử lý mới. Nếu mục tiêu là restart, hãy dùng đúng các identifying parameters của instance cũ.

## 11. Theo dõi execution sau khi launcher trả về

Đối với job dài hoặc launcher bất đồng bộ, nơi gọi không nên giữ đối tượng `JobExecution` trong bộ nhớ làm nguồn trạng thái duy nhất. Metadata trong JobRepository mới là nguồn lưu trữ bền vững để tra cứu trạng thái.

`JobExplorer` có thể được sử dụng để tìm execution theo ID và đọc trạng thái mới nhất:

```java
@Service
public class JobStatusService {

    private final JobExplorer jobExplorer;

    public JobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Khi trả trạng thái cho client, nên cung cấp những thông tin phù hợp như execution ID, job name, BatchStatus, ExitStatus, thời điểm bắt đầu/kết thúc và thông tin lỗi đã được phép hiển thị. Tránh trả stack trace hoặc dữ liệu nhạy cảm từ exception ra API công khai.

Ứng dụng cũng có thể đăng ký `JobExecutionListener` để ghi log thời điểm bắt đầu và kết thúc, gửi metric hoặc phát sự kiện nội bộ. Listener hỗ trợ quan sát vòng đời job, còn JobRepository giữ metadata thực thi.

## 12. JobLauncher và quản lý đồng thời

Trong hệ thống có nhiều yêu cầu khởi chạy, cần cân nhắc số job có thể chạy đồng thời và tài nguyên mà chúng sử dụng.

Một số nguyên tắc quan trọng:

- Cấu hình thread pool có giới hạn để kiểm soát số execution đồng thời.
- Xác định chính sách khi có hai yêu cầu cho cùng một JobInstance.
- Không giả định hai job khác nhau có thể ghi cùng bảng hoặc cùng file mà không xung đột.
- Dùng JobRepository bền vững và nhất quán khi ứng dụng chạy nhiều instance.
- Thiết kế lock, unique constraint hoặc cơ chế điều phối nghiệp vụ khi nhiều job có thể xử lý cùng dữ liệu.
- Theo dõi hàng đợi executor và thời gian chờ trước khi job thực sự bắt đầu.

JobRepository giúp Spring Batch nhận diện các execution của một JobInstance và ngăn một số trường hợp khởi chạy trùng. Nó không thay thế mọi cơ chế đồng bộ dữ liệu nghiệp vụ giữa các job khác nhau hoặc giữa các hệ thống bên ngoài.

## 13. Kiểm thử thành phần gọi JobLauncher

Khi kiểm thử service hoặc controller gọi JobLauncher, cần xác định rõ mục tiêu:

- Kiểm tra service tạo đúng JobParameters.
- Kiểm tra service gọi đúng Job với đúng bộ tham số.
- Kiểm tra cách xử lý ngoại lệ khi instance đang chạy hoặc đã hoàn tất.
- Kiểm tra endpoint trả execution ID và trạng thái phù hợp.
- Với integration test, xác nhận job thực sự chạy và metadata được lưu như mong đợi.

Spring Batch Test cung cấp các tiện ích như `JobLauncherTestUtils` để hỗ trợ chạy job trong integration test. Một bài kiểm thử có thể tạo tham số riêng cho từng test để tránh các JobInstance dùng chung identifying parameters làm ảnh hưởng lẫn nhau.

Ví dụ kiểm thử ở mức khái niệm:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("testRun", UUID.randomUUID().toString(), true)
        .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

Đoạn code trên giả định test đã cấu hình `JobLauncherTestUtils`, job cần kiểm thử và các dependency test phù hợp. Nếu kiểm tra service điều phối đơn thuần, có thể mock JobLauncher và xác minh lời gọi thay vì chạy toàn bộ job.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| JobLauncher chính là Job | JobLauncher là thành phần khởi chạy; Job là định nghĩa quy trình. |
| Gọi `run()` nghĩa là job đã hoàn tất | Chỉ chắc chắn khi launcher chạy đồng bộ và phương thức đã trả về sau khi thực thi. Launcher bất đồng bộ có thể trả về khi job còn chạy. |
| Mỗi lần gọi launcher luôn tạo JobInstance mới | Instance được xác định bởi tên job và identifying JobParameters. |
| JobLauncher tự lập lịch chạy | Scheduler hoặc thành phần điều phối quyết định thời điểm gọi launcher. |
| JobExecution chỉ có một trạng thái cuối cùng ngay khi tạo | Execution có thể chuyển qua nhiều trạng thái như STARTING, STARTED, COMPLETED hoặc FAILED. |
| JobLauncher xử lý mọi lỗi nghiệp vụ | Nó khởi chạy job; lỗi trong reader, processor, writer hoặc tasklet được ghi nhận trong quá trình thực thi job. |
| JobRepository và JobLauncher có cùng trách nhiệm | Launcher khởi động execution; repository lưu metadata thực thi. |
| Dùng JobLauncher để dừng hoặc restart execution đang chạy | Các thao tác vận hành này thường được thực hiện qua JobOperator hoặc cơ chế quản trị phù hợp. |

## 15. Quy trình khởi chạy một job trong ứng dụng thực tế

Một luồng khởi chạy có thể được tổ chức theo trình tự sau:

1. **Nhận yêu cầu:** từ scheduler, REST API, command line hoặc một service khác.
2. **Kiểm tra đầu vào:** xác thực ngày nghiệp vụ, file, mã nguồn và quyền thực hiện.
3. **Tạo JobParameters:** chọn identifying parameters theo đơn vị xử lý nghiệp vụ; thêm tham số không định danh nếu cần lưu thông tin yêu cầu.
4. **Chọn Job:** lấy bean Job đã được cấu hình và được phép chạy.
5. **Gọi JobLauncher:** truyền Job và JobParameters.
6. **Xử lý kết quả tiếp nhận:** ghi nhận execution ID, trạng thái ban đầu hoặc các ngoại lệ không thể khởi chạy.
7. **Theo dõi execution:** với job bất đồng bộ, truy vấn metadata qua JobExplorer hoặc nhận sự kiện trạng thái.
8. **Phản hồi kết quả:** cung cấp trạng thái và thông tin phù hợp cho người gọi hoặc hệ thống vận hành.

Việc tách rõ các bước này giúp lớp điều phối dễ kiểm thử, đồng thời giữ logic xử lý dữ liệu trong Job và Step.

## 16. Những điểm cần ghi nhớ

- `JobLauncher` là điểm vào để khởi chạy một `Job` với `JobParameters`.
- Launcher phối hợp với `JobRepository` để đăng ký `JobExecution` và yêu cầu job thực thi.
- `JobInstance` được xác định bởi tên job và identifying parameters; một instance có thể có nhiều JobExecution khi restart.
- `JobExecution` cung cấp ID, trạng thái, thời gian, ExitStatus, StepExecution và thông tin lỗi.
- Launcher có thể chạy đồng bộ hoặc bất đồng bộ tùy executor được cấu hình.
- Với launcher bất đồng bộ, cần tra cứu trạng thái mới nhất từ JobRepository/JobExplorer thay vì coi kết quả trả về ban đầu là kết quả cuối cùng.
- Các ngoại lệ khởi chạy như instance đang chạy, instance đã hoàn tất, không thể restart hoặc parameters không hợp lệ cần được xử lý riêng.
- JobLauncher không thay thế scheduler, JobOperator hoặc JobRepository.
- Cần thiết kế JobParameters và chính sách đồng thời cẩn thận để tránh tạo instance ngoài ý muốn hoặc xử lý trùng dữ liệu.

Khi đọc một ứng dụng Spring Batch, hãy tìm nơi inject `JobLauncher`, xem cách tạo `JobParameters` và xác định job nào được truyền vào `run`. Sau đó kiểm tra launcher dùng executor nào, metadata được lưu ở đâu và ứng dụng theo dõi JobExecution bằng cách nào. Những chi tiết này cho biết job được khởi chạy, giám sát và vận hành ra sao trong toàn bộ ứng dụng.
