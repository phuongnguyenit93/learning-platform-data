# Theo dõi kết quả từ JobLauncher

Trong Spring Batch, **JobLauncher** là thành phần nhận yêu cầu chạy Job. Khi gọi phương thức **run()**, ứng dụng nhận về một **JobExecution** đại diện cho lần thực thi vừa được yêu cầu. Từ đối tượng này, bạn có thể xem trạng thái Job, mã kết quả, thời điểm chạy, các Step đã thực thi và những số liệu xử lý.

Cách theo dõi phụ thuộc vào cách JobLauncher thực thi Job:

- Với launcher chạy đồng bộ, lời gọi run() thường chỉ trả về sau khi Job kết thúc. Có thể đọc kết quả cuối ngay từ JobExecution được trả về.
- Với launcher chạy bất đồng bộ, run() có thể trả về khi Job vẫn đang chạy. Cần lưu execution ID và truy vấn trạng thái mới nhất qua JobExplorer hoặc nhận thông báo khi Job kết thúc.

Đừng xem việc run() trả về là bằng chứng Job đã hoàn thành. Hãy đọc trạng thái của JobExecution và hiểu launcher đang chạy đồng bộ hay bất đồng bộ.

## 1. JobLauncher trả về JobExecution

JobLauncher không trả về một giá trị boolean để cho biết thành công hay thất bại. Nó trả về JobExecution, đối tượng chứa thông tin của một lần chạy Job.

Ví dụ một service khởi chạy Job nhập khách hàng:

~~~java
@Service
public class CustomerImportService {

    private final JobLauncher jobLauncher;
    private final Job customerImportJob;

    public CustomerImportService(
            JobLauncher jobLauncher,
            Job customerImportJob) {
        this.jobLauncher = jobLauncher;
        this.customerImportJob = customerImportJob;
    }

    public JobExecution launch(String inputFile)
            throws JobExecutionException {

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", inputFile, true)
                .toJobParameters();

        return jobLauncher.run(customerImportJob, parameters);
    }
}
~~~

Trong ví dụ:

1. Ứng dụng tạo JobParameters chứa đường dẫn file.
2. JobLauncher nhận Job cùng bộ tham số.
3. Spring Batch kiểm tra JobInstance và điều kiện khởi chạy.
4. Nếu yêu cầu hợp lệ, framework tạo JobExecution cho lần chạy.
5. JobExecution được trả về cho bên gọi.

Mỗi lần thử chạy Job có một JobExecution ID riêng. Khi restart một JobInstance, Spring Batch tạo JobExecution mới thuộc cùng JobInstance. Vì vậy, khi lưu lịch sử hoặc theo dõi một lần chạy cụ thể, hãy lưu **JobExecution ID**, không chỉ lưu tên Job.

## 2. Những thông tin cần đọc từ JobExecution

JobExecution chứa các thông tin quan trọng sau:

| Thuộc tính | Ý nghĩa |
|---|---|
| id | ID của lần thực thi Job |
| jobInstance | JobInstance mà lần thực thi thuộc về |
| status | Trạng thái thực thi ở cấp framework |
| exitStatus | Kết quả thoát của Job |
| createTime | Thời điểm tạo JobExecution |
| startTime | Thời điểm bắt đầu thực thi |
| endTime | Thời điểm kết thúc |
| lastUpdated | Thời điểm metadata được cập nhật gần nhất |
| executionContext | Trạng thái ở cấp Job |
| stepExecutions | Tập hợp các lần thực thi Step |
| failureExceptions | Các exception được giữ trên đối tượng thực thi hiện tại |

Ví dụ đọc thông tin:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

Long executionId = execution.getId();
BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();

System.out.println("Execution ID: " + executionId);
System.out.println("Status: " + status);
System.out.println("Exit code: " + exitStatus.getExitCode());
System.out.println("Exit description: " + exitStatus.getExitDescription());
~~~

Các giá trị này trả lời những câu hỏi khác nhau:

- **ID** cho biết cần truy vấn lần chạy nào.
- **BatchStatus** cho biết framework đang chạy, đã hoàn tất, thất bại hay dừng.
- **ExitStatus** cho biết mã kết quả mà Job phát ra.
- **Thời gian** giúp đo thời lượng và xác định lần cập nhật gần nhất.
- **StepExecutions** giúp tìm công đoạn cụ thể gây lỗi hoặc xử lý ít dữ liệu hơn dự kiến.

## 3. Phân biệt BatchStatus và ExitStatus

Đây là hai thông tin cần xem cùng nhau khi theo dõi kết quả.

**BatchStatus** biểu diễn trạng thái thực thi của Job hoặc Step. Các giá trị thường gặp gồm:

| BatchStatus | Ý nghĩa |
|---|---|
| STARTING | Đang chuẩn bị bắt đầu |
| STARTED | Đang thực thi |
| STOPPING | Đang yêu cầu dừng |
| STOPPED | Đã dừng theo yêu cầu |
| COMPLETED | Đã hoàn thành theo trạng thái framework |
| FAILED | Thực thi thất bại |
| ABANDONED | Lần thực thi được đánh dấu không tiếp tục restart |
| UNKNOWN | Không xác định được trạng thái đáng tin cậy |

**ExitStatus** mô tả kết quả thoát. Nó có exit code và có thể có exit description. Các mã mặc định thường gồm COMPLETED, FAILED và EXECUTING; ứng dụng cũng có thể sử dụng mã riêng như NO_DATA hoặc COMPLETED_WITH_WARNINGS.

Ví dụ:

~~~java
BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();

if (status == BatchStatus.COMPLETED) {
    System.out.println("Job đã hoàn tất ở cấp framework.");
}

if ("NO_DATA".equals(exitStatus.getExitCode())) {
    System.out.println("Job hoàn tất nhưng không có dữ liệu cần xử lý.");
}
~~~

Một Job có thể có BatchStatus COMPLETED nhưng ExitStatus mang mã nghiệp vụ tùy chỉnh. Điều đó cho phép ứng dụng phân biệt Job chạy thành công về mặt kỹ thuật với những kết quả nghiệp vụ khác nhau.

Ngược lại, BatchStatus FAILED cho biết Job thất bại ở cấp framework. Khi gặp trường hợp này, hãy xem ExitStatus và log để hiểu nguyên nhân.

Trong flow, các transition được khai báo bằng on() khớp với exit code của ExitStatus. Vì vậy, nếu một nhánh flow không chạy như mong đợi, hãy xem ExitStatus của Step và Job thay vì chỉ nhìn BatchStatus.

## 4. Theo dõi kết quả của từng Step

JobExecution chứa các StepExecution thuộc lần chạy đó. Mỗi StepExecution đại diện cho một lần thực thi cụ thể của Step và cung cấp trạng thái, thời gian, số liệu đọc/ghi cùng thông tin lỗi.

Ví dụ duyệt các Step:

~~~java
for (StepExecution stepExecution : execution.getStepExecutions()) {
    System.out.println("Step: " + stepExecution.getStepName());
    System.out.println("Status: " + stepExecution.getStatus());
    System.out.println(
            "Exit code: " + stepExecution.getExitStatus().getExitCode());

    System.out.println("Read: " + stepExecution.getReadCount());
    System.out.println("Write: " + stepExecution.getWriteCount());
    System.out.println("Filter: " + stepExecution.getFilterCount());
    System.out.println("Commit: " + stepExecution.getCommitCount());
    System.out.println("Rollback: " + stepExecution.getRollbackCount());
}
~~~

Các số liệu thường dùng:

| Số liệu | Cách hiểu |
|---|---|
| readCount | Số item đã đọc |
| writeCount | Số item đã ghi |
| filterCount | Số item bị lọc bởi processor |
| readSkipCount | Số item bị bỏ qua ở giai đoạn đọc |
| processSkipCount | Số item bị bỏ qua ở giai đoạn xử lý |
| writeSkipCount | Số item bị bỏ qua ở giai đoạn ghi |
| commitCount | Số transaction đã commit |
| rollbackCount | Số transaction đã rollback |
| startTime / endTime | Thời điểm bắt đầu và kết thúc Step |

Những số liệu này giúp xác định Step nào xử lý chậm, có nhiều bản ghi bị lọc, hoặc gặp nhiều rollback.

Không nên giả định readCount luôn bằng writeCount. Processor có thể trả về null để lọc item, writer có thể ghi theo lô, và skip policy có thể bỏ qua item lỗi. Khi đối soát số liệu, cần xem cả các skip count, filter count và log của ứng dụng.

## 5. Theo dõi khi JobLauncher chạy đồng bộ

Khi JobLauncher sử dụng cơ chế thực thi đồng bộ, lời gọi run() chờ Job kết thúc trước khi trả quyền điều khiển cho bên gọi.

Luồng xử lý:

~~~text
Ứng dụng
   |
   v
JobLauncher.run()
   |
   v
Job thực thi các Step
   |
   v
Job kết thúc
   |
   v
Trả về JobExecution
   |
   v
Đọc status và exitStatus cuối cùng
~~~

Ví dụ:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

if (execution.getStatus() == BatchStatus.COMPLETED) {
    // Xử lý kết quả hoàn tất.
} else if (execution.getStatus() == BatchStatus.FAILED) {
    // Ghi nhận lỗi và xử lý theo chính sách của ứng dụng.
}
~~~

Đây là cách đơn giản khi Job ngắn và ứng dụng có thể chờ kết quả. Bên gọi có thể trả kết quả cuối cho người dùng hoặc thực hiện bước tiếp theo sau khi Job kết thúc.

Tuy nhiên, Job dài có thể khiến HTTP request hoặc luồng xử lý của ứng dụng phải chờ lâu. Với tác vụ chạy hàng phút hoặc hàng giờ, nên cân nhắc khởi chạy bất đồng bộ và cung cấp cơ chế truy vấn trạng thái riêng.

## 6. Theo dõi khi JobLauncher chạy bất đồng bộ

JobLauncher có thể được cấu hình với TaskExecutor để chạy Job trên một luồng khác. Trong trường hợp đó, run() có thể trả về JobExecution khi Job vẫn đang STARTING hoặc STARTED.

Luồng xử lý:

~~~text
Ứng dụng
   |
   v
JobLauncher.run()
   |
   +----> Gửi công việc tới TaskExecutor
   |                |
   |                v
   |           Job chạy nền
   |
   v
Trả JobExecution ban đầu
   |
   v
Lưu execution ID
   |
   v
Truy vấn trạng thái mới qua JobExplorer
   |
   v
Job COMPLETED / FAILED / STOPPED
~~~

Ví dụ, ngay sau khi run() trả về:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

Long executionId = execution.getId();

System.out.println("Execution ID: " + executionId);
System.out.println("Current status: " + execution.getStatus());
~~~

Nếu launcher chạy bất đồng bộ, status tại thời điểm này có thể chưa phải trạng thái cuối. Không nên dựa vào đối tượng JobExecution ban đầu để kết luận Job đã hoàn tất. Hãy truy vấn lại metadata mới nhất bằng execution ID.

Cách cấu hình executor cụ thể phụ thuộc vào cấu hình hạ tầng Batch của ứng dụng. Điểm cần nhớ là chế độ đồng bộ hay bất đồng bộ được quyết định bởi TaskExecutor mà JobLauncher sử dụng.

## 7. JobExplorer: truy vấn trạng thái mới nhất

**JobExplorer** cung cấp API chỉ đọc để truy vấn thông tin thực thi từ JobRepository. Đây là lựa chọn phù hợp để theo dõi Job bất đồng bộ, hiển thị lịch sử chạy hoặc xây dựng endpoint trạng thái.

Ví dụ truy vấn một JobExecution bằng ID:

~~~java
@Service
public class JobMonitoringService {

    private final JobExplorer jobExplorer;

    public JobMonitoringService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(Long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
~~~

Khi nhận được JobExecution mới nhất, có thể đọc trạng thái và các Step:

~~~java
JobExecution latest = jobExplorer.getJobExecution(executionId);

if (latest == null) {
    throw new IllegalArgumentException(
            "Không tìm thấy JobExecution: " + executionId);
}

System.out.println("Status: " + latest.getStatus());
System.out.println("Exit code: " + latest.getExitStatus().getExitCode());

for (StepExecution step : latest.getStepExecutions()) {
    System.out.println(
            step.getStepName() + ": " + step.getStatus());
}
~~~

JobExplorer truy vấn metadata đã lưu trong repository. Khi dùng nó để theo dõi tiến trình, cần bảo đảm JobRepository và JobExplorer cùng truy cập một kho metadata.

Với launcher bất đồng bộ, một cách triển khai phổ biến là:

1. Khởi chạy Job.
2. Lấy execution ID từ JobExecution được trả về.
3. Lưu ID cùng thông tin yêu cầu nghiệp vụ.
4. Dùng JobExplorer truy vấn trạng thái mới nhất khi cần.
5. Dừng polling khi Job đạt trạng thái kết thúc.

Không nên truy vấn liên tục với tần suất quá cao. Hãy dùng lịch polling hợp lý, giới hạn thời gian theo dõi và tránh giữ một HTTP request mở trong suốt thời gian Job chạy.

### Tìm các Job đang chạy

JobExplorer cũng có thể hỗ trợ tìm những JobExecution đang chạy theo tên Job:

~~~java
Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("customerImportJob");

for (JobExecution execution : running) {
    System.out.println(
            execution.getId() + " - " + execution.getStatus());
}
~~~

Điều này hữu ích khi xây dựng trang vận hành để hiển thị các Job đang hoạt động. Nếu một Job có nhiều JobInstance hoặc nhiều lần restart, hãy phân biệt từng JobExecution bằng ID của nó.

## 8. JobExecutionListener: nhận kết quả khi Job kết thúc

Nếu ứng dụng cần thực hiện một hành động sau khi Job kết thúc, có thể sử dụng **JobExecutionListener**.

Listener có hai callback chính:

- beforeJob(): được gọi trước khi Job thực thi.
- afterJob(): được gọi sau khi Job kết thúc, bất kể kết quả thành công hay thất bại.

Ví dụ:

~~~java
@Component
public class CustomerImportListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(CustomerImportListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info(
                "Starting JobExecution id={}",
                jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        log.info(
                "Finished JobExecution id={}, status={}, exitCode={}",
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());

        if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
            log.info("Customer import completed.");
        } else if (jobExecution.getStatus() == BatchStatus.FAILED) {
            log.error("Customer import failed.");
        }
    }
}
~~~

Đăng ký listener trong Job:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step importCustomersStep,
        CustomerImportListener listener) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(importCustomersStep)
            .listener(listener)
            .build();
}
~~~

Listener phù hợp với việc ghi log, cập nhật trạng thái nghiệp vụ hoặc phát sự kiện hoàn tất. Vì listener chạy trong tiến trình thực thi Job, nó cũng hoạt động khi Job được khởi chạy bất đồng bộ.

Nếu gửi thông báo ra hệ thống bên ngoài, hãy cân nhắc khả năng gửi trùng khi Job restart hoặc listener được gọi lại. Với sự kiện cần bảo đảm độ tin cậy, nên dùng một cơ chế lưu sự kiện bền vững như outbox và xử lý idempotent ở bên nhận.

## 9. Xây dựng endpoint theo dõi Job

Một ứng dụng web có thể trả về execution ID ngay sau khi khởi chạy Job. Client dùng ID này để truy vấn trạng thái qua một endpoint khác.

Ví dụ response khi bắt đầu:

~~~json
{
  "executionId": 125,
  "status": "STARTED",
  "message": "Job đã được tiếp nhận"
}
~~~

Endpoint theo dõi có thể trả về:

~~~json
{
  "executionId": 125,
  "jobName": "customerImportJob",
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "startTime": "2026-11-15T10:00:00",
  "endTime": "2026-11-15T10:00:12",
  "steps": [
    {
      "name": "importCustomersStep",
      "status": "COMPLETED",
      "readCount": 1000,
      "writeCount": 980,
      "filterCount": 20
    }
  ]
}
~~~

Đây là cấu trúc response minh họa do ứng dụng thiết kế, không phải JSON cố định mà Spring Batch tự trả về.

Một thiết kế API thường có hai thao tác:

- POST /jobs/customer-import: nhận yêu cầu và trả về execution ID.
- GET /jobs/executions/{id}: truy vấn trạng thái và số liệu mới nhất.

Khi xây dựng endpoint, chỉ trả các trường mà người dùng hoặc hệ thống gọi cần. Không nên trả toàn bộ ExecutionContext vì nó có thể chứa thông tin nội bộ hoặc dữ liệu nghiệp vụ nhạy cảm.

Nếu Job chạy đồng bộ và request chờ đến khi Job kết thúc, endpoint POST có thể trả kết quả cuối cùng. Nếu Job chạy bất đồng bộ, trả execution ID giúp client theo dõi tiến trình mà không phải giữ kết nối mở.

## 10. Theo dõi lịch sử và các lần restart

Một Job có thể có nhiều JobInstance. Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại hoặc bị dừng rồi được restart.

Ví dụ:

~~~text
customerImportJob
   |
   +-- JobInstance A (file=customers-01.csv)
   |       |
   |       +-- JobExecution 101: FAILED
   |       +-- JobExecution 105: COMPLETED
   |
   +-- JobInstance B (file=customers-02.csv)
           |
           +-- JobExecution 110: COMPLETED
~~~

Khi hiển thị lịch sử, cần phân biệt:

- **JobInstance ID**: định danh một lần xử lý logic theo Job name và identifying parameters.
- **JobExecution ID**: định danh một lần thực thi cụ thể.
- **JobExecution status**: kết quả của lần thực thi đó.

Nếu chỉ lưu JobInstance ID, bạn sẽ không biết lần restart gần nhất có kết quả gì. Nếu chỉ lưu tên Job, bạn không phân biệt được các lần xử lý khác nhau.

JobExplorer cung cấp các thao tác đọc lịch sử theo tên Job, JobInstance và JobExecution. Có thể dùng chúng để xây dựng danh sách lần chạy, chi tiết từng lần chạy và các Step tương ứng.

## 11. JobLauncher exception khác với JobExecution FAILED

Không phải mọi lỗi khi gọi JobLauncher.run() đều tạo ra một JobExecution thất bại.

Một số trường hợp yêu cầu khởi chạy bị từ chối ngay từ đầu:

| Exception | Nguyên nhân thường gặp |
|---|---|
| JobExecutionAlreadyRunningException | Một JobInstance với cùng identifying parameters đang chạy |
| JobInstanceAlreadyCompleteException | JobInstance đó đã hoàn thành và không thể chạy lại như một lần mới |
| JobRestartException | Không thể restart JobInstance theo trạng thái hoặc cấu hình hiện tại |
| JobParametersInvalidException | Bộ JobParameters không hợp lệ |
| TaskRejectedException | Executor từ chối nhận công việc, nếu launcher chạy bất đồng bộ |

Ví dụ bắt lỗi khi khởi chạy:

~~~java
public Long launch(Job job, JobParameters parameters)
        throws JobExecutionException {
    try {
        JobExecution execution = jobLauncher.run(job, parameters);
        return execution.getId();
    } catch (JobExecutionAlreadyRunningException ex) {
        // Yêu cầu tương ứng đang được thực thi.
        throw ex;
    } catch (JobInstanceAlreadyCompleteException ex) {
        // JobInstance đã hoàn thành với identifying parameters này.
        throw ex;
    } catch (JobRestartException ex) {
        // Không thể restart JobInstance.
        throw ex;
    } catch (JobParametersInvalidException ex) {
        // Tham số đầu vào không hợp lệ.
        throw ex;
    }
~~~

Trong code thực tế, có thể bắt nhóm exception chung theo chính sách của ứng dụng. Điều quan trọng là phân biệt lỗi khởi chạy với một JobExecution đã được tạo rồi kết thúc ở trạng thái FAILED.

Nếu run() ném exception trước khi trả về JobExecution, bên gọi có thể không có execution ID để truy vấn. Hãy ghi log yêu cầu, tên Job và identifying parameters phù hợp để điều tra, đồng thời tránh ghi dữ liệu nhạy cảm.

## 12. Chẩn đoán kết quả Job không như mong đợi

Khi người vận hành báo Job “chạy xong nhưng không có dữ liệu” hoặc “không thấy kết quả”, hãy lần lượt xem các thông tin sau:

| Hiện tượng | Nơi cần kiểm tra |
|---|---|
| Không nhận được JobExecution | Exception khi gọi JobLauncher, cấu hình launcher và executor |
| Job vẫn ở STARTED | Executor, tiến trình worker, JobExplorer và metadata cập nhật gần nhất |
| Job có status FAILED | ExitStatus, failure description, StepExecution và application log |
| Job COMPLETED nhưng output rỗng | ExitStatus tùy chỉnh, readCount, writeCount, filterCount và dữ liệu nguồn |
| Một Step không xuất hiện | Flow transition, Step có được chọn chạy hay không |
| Số đọc và ghi khác nhau | Processor filter, skip count và logic writer |
| Dashboard hiển thị trạng thái cũ | Đang dùng JobExecution object cũ thay vì truy vấn lại JobExplorer |
| Không tìm thấy execution ID | Sai ID, khác JobRepository hoặc metadata đã bị dọn |

Đối với lỗi xảy ra bên trong Step, hãy kiểm tra StepExecution cụ thể thay vì chỉ nhìn trạng thái Job. ExitDescription có thể cung cấp thông tin bổ sung, nhưng stack trace đầy đủ thường nằm trong log ứng dụng. Đừng giả định mọi Throwable được giữ trong đối tượng Java đều được lưu và khôi phục nguyên vẹn từ database metadata.

Với launcher bất đồng bộ, nếu status không thay đổi trong thời gian dài, hãy kiểm tra worker thread, TaskExecutor, log của tiến trình và JobRepository. Một lần truy vấn JobExplorer không tự làm Job tiếp tục chạy; nó chỉ đọc trạng thái đã được lưu.

## 13. Thiết kế cơ chế monitoring dễ vận hành

Một cơ chế theo dõi tốt nên cung cấp đủ thông tin để trả lời Job nào đang chạy, chạy cho yêu cầu nghiệp vụ nào, đã xử lý đến đâu và kết thúc ra sao.

Một số nguyên tắc:

- Lưu JobExecution ID ngay sau khi JobLauncher chấp nhận yêu cầu.
- Gắn execution ID với mã yêu cầu nghiệp vụ để người vận hành tìm kiếm dễ dàng.
- Dùng JobExplorer để truy vấn trạng thái mới nhất khi chạy bất đồng bộ.
- Hiển thị cả BatchStatus và ExitStatus.
- Hiển thị trạng thái, thời gian và số liệu của từng Step.
- Ghi log có execution ID để liên kết sự kiện giữa các thành phần.
- Giữ lịch sử JobExecution đủ lâu để điều tra và đối soát.
- Đặt tần suất polling hợp lý, có thời gian chờ tối đa và xử lý trường hợp không tìm thấy execution.
- Phân biệt lỗi khởi chạy với lỗi trong quá trình thực thi.
- Thiết kế callback hoặc sự kiện hoàn tất có khả năng chống gửi trùng.

Nếu hệ thống cần dừng hoặc restart Job từ giao diện vận hành, hãy tìm hiểu JobOperator cho các thao tác điều khiển. JobExplorer phù hợp để đọc trạng thái và lịch sử; nó không phải API dùng để thay đổi trạng thái thực thi.

## 14. Quy trình theo dõi hoàn chỉnh

Một luồng điển hình trong ứng dụng nhập dữ liệu có thể được tổ chức như sau:

~~~text
Người dùng gửi yêu cầu nhập file
              |
              v
       Ứng dụng tạo JobParameters
              |
              v
         JobLauncher.run()
              |
              v
         Nhận JobExecution
              |
              +---- Lưu execution ID
              |
              v
       Trả ID cho client
              |
              v
       Client hỏi trạng thái
              |
              v
      JobExplorer.getJobExecution(id)
              |
              v
      Đọc Job và Step status
              |
       +------+------+
       |             |
       v             v
   Đang chạy      Đã kết thúc
       |             |
       v             v
   Tiếp tục       Hiển thị exit code,
   theo dõi       số liệu và kết quả
~~~

Khi JobLauncher chạy đồng bộ, ứng dụng có thể đọc kết quả cuối ngay sau run(). Khi launcher chạy bất đồng bộ, execution ID là khóa để truy vấn trạng thái mới nhất qua JobExplorer. Trong cả hai trường hợp, JobExecution và các StepExecution là nguồn thông tin chính để hiểu lần chạy đã diễn ra như thế nào.

Hãy luôn xem **BatchStatus**, **ExitStatus** và số liệu của từng Step cùng nhau. Một Job chỉ được coi là đáp ứng yêu cầu nghiệp vụ khi trạng thái kỹ thuật, mã kết quả và dữ liệu đầu ra đều phù hợp với mục tiêu xử lý.
