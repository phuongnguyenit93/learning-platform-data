# Exit code cho scheduler

Khi chạy Spring Batch từ scheduler như cron, Windows Task Scheduler hoặc hệ thống điều phối batch của doanh nghiệp, scheduler thường cần biết Job kết thúc thành công hay thất bại. Một cách phổ biến là đọc process exit code của chương trình Java. Spring Batch biểu diễn kết quả Job bằng ExitStatus có mã dạng chuỗi; scheduler của hệ điều hành lại nhận một số nguyên. Vì vậy, ứng dụng cần một bước ánh xạ rõ ràng từ kết quả Job sang process exit code.

Cần phân biệt ba khái niệm: BatchStatus mô tả trạng thái vòng đời của execution; ExitStatus mô tả kết quả logic của Job hoặc Step; process exit code là số nguyên mà tiến trình trả về cho hệ điều hành. Nếu không ánh xạ đúng, scheduler có thể đánh dấu một Job thất bại là thành công, hoặc ngược lại, dù metadata trong JobRepository vẫn ghi trạng thái chính xác.

## 1. Ba loại trạng thái cần phân biệt

Spring Batch và hệ điều hành dùng các kiểu dữ liệu khác nhau để biểu diễn kết quả.

| Khái niệm | Kiểu dữ liệu | Mục đích | Ví dụ |
|---|---|---|---|
| BatchStatus | Enum | Trạng thái vòng đời của JobExecution hoặc StepExecution | STARTED, COMPLETED, FAILED, STOPPED |
| ExitStatus | Value object với exit code dạng String | Kết quả logic và mô tả kết thúc của Job/Step | COMPLETED, FAILED, COMPLETED_WITH_WARNINGS |
| Process exit code | Số nguyên | Kết quả tiến trình trả về cho OS hoặc scheduler | 0, 1, 4, 10 |

BatchStatus trả lời câu hỏi execution đã hoàn thành, thất bại hay bị dừng. ExitStatus trả lời kết quả của công đoạn theo quy ước ứng dụng và có thể được dùng trong flow transition. Process exit code là hợp đồng giữa chương trình và scheduler bên ngoài.

Ví dụ một Job có thể có:

~~~text
BatchStatus: COMPLETED
ExitStatus:  COMPLETED_WITH_WARNINGS
Process code: 4
~~~

Trường hợp này có nghĩa Job đã hoàn tất về mặt lifecycle nhưng có cảnh báo nghiệp vụ, chẳng hạn một số item bị skip. Scheduler có thể được cấu hình coi code 4 là trạng thái hoàn thành có cảnh báo và thực hiện bước thông báo hoặc đối soát.

Không nên xem ba giá trị này là một. Một ExitStatus tùy chỉnh không tự thay đổi BatchStatus, và một ExitStatus dạng chuỗi không tự trở thành process exit code số nguyên.

## 2. ExitStatus của Job và Step

ExitStatus là kết quả của một Step hoặc Job. Nó có hai phần chính:

- exit code: chuỗi định danh kết quả.
- exit description: mô tả bổ sung, thường dùng cho thông tin chẩn đoán.

Các giá trị phổ biến gồm COMPLETED, EXECUTING, FAILED, NOOP, STOPPED và UNKNOWN. Ứng dụng có thể tạo mã tùy chỉnh như COMPLETED_WITH_WARNINGS hoặc VALIDATION_FAILED nếu flow và scheduler cần phân biệt những kết quả đó.

Ví dụ tạo ExitStatus tùy chỉnh:

~~~java
ExitStatus warningStatus =
        new ExitStatus("COMPLETED_WITH_WARNINGS",
                "Completed with skipped records");
~~~

ExitStatus không phải một mã lỗi hệ điều hành. Giá trị COMPLETED_WITH_WARNINGS cần được ánh xạ sang một số nguyên riêng trước khi trả về scheduler.

Một Step có thể trả ExitStatus trong StepExecutionListener.afterStep. JobExecution cũng có ExitStatus cuối cùng, được tổng hợp từ kết quả các Step và có thể được điều chỉnh bởi JobExecutionListener. Khi ánh xạ cho scheduler, thường nên dựa trên kết quả cuối của JobExecution, vì đó là kết quả của toàn bộ Job.

## 3. BatchStatus và ExitStatus có thể khác nhau

BatchStatus và ExitStatus liên quan nhưng không đồng nhất.

| BatchStatus | ExitStatus | Cách hiểu |
|---|---|---|
| COMPLETED | COMPLETED | Job hoàn tất bình thường |
| COMPLETED | COMPLETED_WITH_WARNINGS | Job hoàn tất nhưng có cảnh báo theo quy ước ứng dụng |
| FAILED | FAILED | Job thất bại |
| STOPPED | STOPPED | Job dừng có kiểm soát |
| COMPLETED | custom code | Lifecycle hoàn tất, kết quả logic do ứng dụng định nghĩa |

BatchStatus được framework dùng để quản lý lifecycle, restart và trạng thái execution trong JobRepository. ExitStatus thường dùng để điều khiển flow, ghi kết quả và trao đổi ý nghĩa kết thúc với hệ thống ngoài.

Không đặt BatchStatus thành COMPLETED chỉ để scheduler nhận code 0 khi Job thực tế đã thất bại. Cũng không nên đặt ExitStatus thành FAILED tùy tiện trong khi BatchStatus vẫn COMPLETED, trừ khi đó là quy ước được thiết kế và kiểm thử rõ ràng. Scheduler và người vận hành cần hiểu cả hai trường.

## 4. Vì sao scheduler cần process exit code?

Scheduler thường khởi chạy một process, chờ process kết thúc và đọc exit code. Quy ước chung trên nhiều hệ điều hành:

- 0 thường biểu thị thành công.
- Giá trị khác 0 thường biểu thị lỗi hoặc kết quả đặc biệt.

Ví dụ:

~~~text
Scheduler
   |
   | start java -jar batch-app.jar
   v
Spring Batch Job
   |
   | execute Steps
   v
JobExecution kết thúc
   |
   | ExitStatus = COMPLETED
   v
Map ExitStatus -> integer
   |
   v
Process exits with code 0
   |
   v
Scheduler đánh dấu SUCCESS
~~~

Nếu ứng dụng luôn kết thúc process với code 0 bất kể JobExecution, scheduler không thể phân biệt Job thành công và Job thất bại. Điều này thường xảy ra khi ứng dụng chỉ launch Job rồi thoát mà không truyền kết quả Batch ra khỏi hàm main.

Process exit code phù hợp khi scheduler chạy một batch application độc lập theo từng lịch. Với ứng dụng Spring Boot chạy lâu dài như service hoặc API server, process thường không kết thúc sau mỗi Job; trong mô hình đó, scheduler nên theo dõi Job qua API, JobRepository hoặc event thay vì dựa vào exit code của process server.

## 5. Ánh xạ ExitStatus thành mã số

Nên định nghĩa một bảng mapping rõ ràng giữa exit code dạng chuỗi và process code.

Ví dụ:

| Job ExitStatus | Process exit code | Ý nghĩa với scheduler |
|---|---:|---|
| COMPLETED | 0 | Thành công |
| COMPLETED_WITH_WARNINGS | 4 | Hoàn tất có cảnh báo |
| STOPPED | 20 | Dừng có kiểm soát |
| FAILED | 10 | Thất bại |
| VALIDATION_FAILED | 11 | Dữ liệu đầu vào không hợp lệ |
| UNKNOWN hoặc mã không nhận diện | 30 | Kết quả không xác định |

Các số trên là quy ước ví dụ, không phải chuẩn bắt buộc của Spring Batch. Cần thống nhất với cấu hình scheduler và quy ước vận hành của tổ chức. Một số scheduler coi mọi mã khác 0 là failure; nếu muốn code 4 được xem là warning/success-with-warning, phải cấu hình scheduler nhận diện code này riêng.

Nên giữ bảng mapping tập trung trong một class hoặc configuration, không rải số nguyên ở nhiều listener và script. Khi thay đổi một mã, ứng dụng và scheduler phải được cập nhật đồng bộ.

## 6. ExitCodeMapper trong Spring Batch

Spring Batch cung cấp interface ExitCodeMapper để ánh xạ một exit code dạng String sang số nguyên:

~~~java
public interface ExitCodeMapper {
    int intValue(String exitCode);
}
~~~

Một implementation tùy chỉnh có thể định nghĩa quy ước cho scheduler:

~~~java
public class SchedulerExitCodeMapper implements ExitCodeMapper {

    @Override
    public int intValue(String exitCode) {
        if ("COMPLETED".equals(exitCode)) {
            return 0;
        }
        if ("COMPLETED_WITH_WARNINGS".equals(exitCode)) {
            return 4;
        }
        if ("STOPPED".equals(exitCode)) {
            return 20;
        }
        if ("VALIDATION_FAILED".equals(exitCode)) {
            return 11;
        }
        if ("FAILED".equals(exitCode)) {
            return 10;
        }

        // Mã chưa được định nghĩa phải được xử lý thận trọng.
        return 30;
    }
}
~~~

Điểm quan trọng là xử lý cả mã không nhận diện. Nếu trả 0 cho một ExitStatus lạ, lỗi mới phát sinh trong tương lai có thể bị scheduler hiểu thành thành công. Một giá trị non-zero dành cho UNKNOWN/default thường an toàn hơn.

Trong Spring Batch, CommandLineJobRunner sử dụng ExitCodeMapper để chuyển kết quả Job thành process exit code. Có thể cung cấp mapper phù hợp qua extension point của runner hoặc dùng một launcher wrapper nếu ứng dụng có cách khởi chạy riêng. Kiểm tra API của phiên bản Spring Batch đang triển khai vì cách cấu hình runner có thể khác giữa các phiên bản.

## 7. SimpleJvmExitCodeMapper mặc định

Spring Batch có SimpleJvmExitCodeMapper để cung cấp ánh xạ số nguyên đơn giản cho command-line execution. Mapping mặc định thường dùng các mã như:

- COMPLETED ánh xạ thành 0.
- FAILED ánh xạ thành 1.
- NOOP ánh xạ thành 2.
- Exit code không có trong mapping ánh xạ thành một mã mặc định khác 0.

Chi tiết mapping mặc định cần được xác nhận theo phiên bản framework đang dùng. Không nên phụ thuộc vào mã mặc định nếu scheduler cần phân biệt nhiều trạng thái nghiệp vụ như completed-with-warning, stopped hoặc validation failure.

Khi scheduler chỉ cần success/failure, mapping đơn giản có thể đủ. Khi cần phân nhánh theo kết quả, hãy định nghĩa mapper rõ ràng và ghi lại hợp đồng mã trong tài liệu vận hành.

## 8. Đặt ExitStatus tùy chỉnh từ Step

Một Step có thể thay đổi ExitStatus thông qua StepExecutionListener.afterStep. Ví dụ, Step hoàn tất nhưng có một số item bị skip:

~~~java
public class WarningExitStatusListener
        implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        long skipped = execution.getReadSkipCount()
                + execution.getProcessSkipCount()
                + execution.getWriteSkipCount();

        if (execution.getStatus() == BatchStatus.COMPLETED
                && skipped > 0) {
            return execution.getExitStatus().and(
                    new ExitStatus("COMPLETED_WITH_WARNINGS"));
        }

        return execution.getExitStatus();
    }
}
~~~

Đăng ký listener trên Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        WarningExitStatusListener warningListener,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(warningListener)
            .build();
}
~~~

Listener chỉ tạo mã cảnh báo khi BatchStatus của Step là COMPLETED và có skip. Nếu Step FAILED, listener giữ ExitStatus hiện tại để không che lỗi.

Trong flow DSL, ExitStatus của Step có thể được dùng để chọn transition. Nếu Job có nhiều Step, cần xác định cách kết quả của từng Step được tổng hợp thành ExitStatus cuối Job. Không giả định mã custom của một Step sẽ luôn trở thành mã cuối của Job nếu các Step sau có thể thay đổi kết quả.

## 9. Đặt ExitStatus cuối cùng ở cấp Job

Khi cần đưa kết quả tổng thể ra scheduler, có thể dùng JobExecutionListener để điều chỉnh ExitStatus cuối của Job dựa trên BatchStatus và counters của các Step.

Ví dụ:

~~~java
public class JobResultListener implements JobExecutionListener {

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() != BatchStatus.COMPLETED) {
            return;
        }

        long totalSkips = jobExecution.getStepExecutions()
                .stream()
                .mapToLong(step -> step.getReadSkipCount()
                        + step.getProcessSkipCount()
                        + step.getWriteSkipCount())
                .sum();

        if (totalSkips > 0) {
            jobExecution.setExitStatus(
                    new ExitStatus(
                            "COMPLETED_WITH_WARNINGS",
                            "Job completed with " + totalSkips + " skipped items"));
        }
    }
}
~~~

Đăng ký listener trên Job:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        JobResultListener resultListener,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .listener(resultListener)
            .start(importOrdersStep)
            .build();
}
~~~

Ví dụ này giữ BatchStatus COMPLETED và chỉ thay ExitStatus thành mã cảnh báo. JobRepository lưu trạng thái execution theo lifecycle của Job; cần kiểm tra kết quả thực tế qua integration test của phiên bản Spring Batch đang dùng.

Nếu Job thất bại, không ghi đè ExitStatus FAILED bằng COMPLETED_WITH_WARNINGS. Scheduler phải nhận mã thất bại tương ứng.

## 10. Flow transition và exit code cho scheduler là hai việc khác nhau

ExitStatus có thể điều khiển flow bên trong Job. Process exit code lại được dùng sau khi Job kết thúc để báo kết quả cho hệ điều hành.

Ví dụ một flow có thể xử lý riêng trạng thái validation:

~~~java
return new JobBuilder("importOrdersJob", jobRepository)
        .start(validateInputStep)
            .on("VALIDATION_FAILED").fail()
        .from(validateInputStep)
            .on("COMPLETED").to(importOrdersStep)
        .from(importOrdersStep)
            .on("*").end()
        .end()
        .build();
~~~

Đoạn mã minh họa cách phân nhánh theo ExitStatus; flow thực tế cần được cấu hình theo các trạng thái mà Step trả về và API builder của phiên bản đang dùng.

Flow transition không trực tiếp gọi scheduler và cũng không tự tạo process exit code. Sau khi Job kết thúc, launcher hoặc wrapper mới đọc ExitStatus cuối và ánh xạ thành số nguyên.

Cần tránh dùng cùng một chuỗi exit code cho hai ý nghĩa khác nhau. Ví dụ, nếu VALIDATION_FAILED được dùng để kết thúc Job theo flow, hãy thống nhất nó có nghĩa BatchStatus FAILED hay là một trạng thái nghiệp vụ đã xử lý xong nhưng không có dữ liệu hợp lệ. BatchStatus, ExitStatus và process code cần cùng phản ánh đúng hợp đồng đã chọn.

## 11. Dùng CommandLineJobRunner

CommandLineJobRunner là cách Spring Batch cung cấp để khởi chạy Job từ command line. Runner nạp cấu hình, xác định Job, nhận JobParameters, chạy Job và dùng ExitCodeMapper để chuyển ExitStatus thành process exit code.

Luồng khái quát:

~~~text
java command
    |
    v
CommandLineJobRunner
    |
    +--> tạo ApplicationContext
    |
    +--> tìm Job và parse JobParameters
    |
    +--> JobLauncher.run(...)
    |
    +--> nhận JobExecution
    |
    +--> lấy ExitStatus.exitCode
    |
    +--> ExitCodeMapper.intValue(...)
    |
    v
process exit code
~~~

Khi dùng runner, hãy kiểm tra command line arguments, tên Job, classpath và JobParameters. Nếu dùng custom ExitCodeMapper, bảo đảm runner thực sự được cấu hình dùng mapper đó. Một custom mapper chỉ được khai báo thành bean nhưng không được runner sử dụng sẽ không thay đổi process exit code.

Với phiên bản Spring Batch mới hoặc ứng dụng Spring Boot, cách khởi chạy có thể dựa trên launcher riêng thay vì CommandLineJobRunner. Nguyên tắc vẫn giống nhau: phải có thành phần cuối cùng đọc kết quả JobExecution và trả số nguyên cho process.

## 12. Spring Boot và process exit code

Một ứng dụng Spring Boot có thể tự động chạy Job khi khởi động. Tuy nhiên, việc Job kết thúc và việc JVM trả exit code là hai bước khác nhau. Nếu ứng dụng chạy như một process batch độc lập, cần chủ động chuyển kết quả Job sang exit code trước khi process kết thúc.

Spring Boot cung cấp ExitCodeGenerator và SpringApplication.exit để lấy mã thoát từ application context. Có thể tạo một bean vừa lắng nghe Job vừa cung cấp mã số:

~~~java
@Component
public class BatchProcessExitCode
        implements JobExecutionListener, ExitCodeGenerator {

    private volatile int exitCode = 30;

    @Override
    public void beforeJob(JobExecution execution) {
        // Mặc định giữ mã lỗi cho đến khi có kết quả cuối.
        exitCode = 30;
    }

    @Override
    public void afterJob(JobExecution execution) {
        String code = execution.getExitStatus().getExitCode();

        if ("COMPLETED".equals(code)) {
            exitCode = 0;
        } else if ("COMPLETED_WITH_WARNINGS".equals(code)) {
            exitCode = 4;
        } else if ("STOPPED".equals(code)) {
            exitCode = 20;
        } else if ("VALIDATION_FAILED".equals(code)) {
            exitCode = 11;
        } else {
            exitCode = 10;
        }
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
~~~

Trong hàm main của ứng dụng batch chạy độc lập:

~~~java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(BatchApplication.class, args);

    int code = SpringApplication.exit(
            context,
            context.getBean(BatchProcessExitCode.class));

    System.exit(code);
}
~~~

Ví dụ giả định Job chạy đồng bộ trong startup flow và listener đã nhận afterJob trước khi SpringApplication.exit được gọi. Nếu dùng asynchronous JobLauncher, hàm main có thể thoát trước khi Job hoàn tất; khi đó cần chờ execution hoặc dùng mô hình điều phối khác.

Không gọi System.exit từ listener hoặc từ code xử lý item. Việc kết thúc JVM ngay trong callback có thể bỏ qua cleanup, đóng resource không đúng lifecycle và làm metadata không được cập nhật đầy đủ.

Đối với Spring Boot server chạy lâu dài, không dùng System.exit sau mỗi Job. Một process server có thể chạy nhiều Job và phục vụ request khác; hãy cung cấp trạng thái qua JobRepository, API quản trị, event hoặc hệ thống monitoring.

## 13. Đảm bảo Job đã kết thúc trước khi process thoát

Để scheduler nhận đúng mã, process chỉ nên kết thúc sau khi JobExecution có trạng thái cuối cùng và kết quả đã được lưu.

Các điểm cần kiểm tra:

- JobLauncher có chạy đồng bộ hay bất đồng bộ.
- Ứng dụng có chờ JobExecution hoàn tất hay không.
- JobExecutionListener.afterJob đã được gọi chưa.
- JobRepository đã cập nhật BatchStatus và ExitStatus cuối chưa.
- Custom ExitCodeGenerator đã nhận đúng kết quả chưa.
- Hàm main có truyền mã số đó ra process hay không.

Nếu launcher trả về một JobExecution đang STARTED vì chạy bất đồng bộ, không thể lấy exit status cuối ngay tại thời điểm đó. Process cần chờ hoặc có một cơ chế callback/monitoring riêng.

Không lấy trạng thái từ log text hoặc từ việc một thread đã được tạo. Dùng JobExecution và JobRepository làm nguồn trạng thái chính thức.

## 14. Quy ước mã exit với scheduler

Scheduler thường cho phép định nghĩa code nào được coi là success, warning, retryable failure hoặc fatal failure. Hãy thống nhất quy ước trước khi triển khai.

Ví dụ:

| Code | Ý nghĩa | Hành động scheduler minh họa |
|---:|---|---|
| 0 | Hoàn thành bình thường | Đánh dấu thành công |
| 4 | Hoàn thành có cảnh báo | Thành công có cảnh báo, gửi notification |
| 10 | Lỗi xử lý | Đánh dấu thất bại, gửi cảnh báo |
| 11 | Dữ liệu đầu vào không hợp lệ | Dừng luồng và yêu cầu kiểm tra dữ liệu |
| 20 | Dừng có kiểm soát | Chờ quyết định restart |
| 30 | Kết quả không xác định | Đưa vào điều tra, không tự động coi là thành công |

Các mã này chỉ là ví dụ. Một số scheduler chỉ có hai nhóm success/failure và coi mọi code khác 0 là thất bại. Nếu cần code 4 là warning nhưng không phải failure, phải cấu hình scheduler tương ứng.

Không dùng code 0 cho một trạng thái mà downstream không thể tiếp tục an toàn. Scheduler có thể khởi chạy Job phụ thuộc ngay sau đó dựa trên code 0.

## 15. Process exit code trên Unix và Windows

Trên Unix-like systems, shell thường dùng 0 cho success và non-zero cho failure. Nhiều shell chỉ giữ một phạm vi giá trị exit status giới hạn; nên chọn mã nhỏ, dễ quản lý và không dựa vào các giá trị ngoài phạm vi portable.

Trên Windows, process cũng trả integer exit code, nhưng scheduler hoặc script wrapper có thể diễn giải khác nhau. Cần xác nhận cách công cụ điều phối lấy mã từ process Java.

Nếu dùng shell script, hãy bảo đảm script trả lại exit code của Java process. Ví dụ shell:

~~~bash
java -jar batch-app.jar
exit $?
~~~

Nếu script chạy thêm các lệnh sau Java, phải lưu mã kết quả trước khi lệnh tiếp theo ghi đè giá trị exit status.

Với PowerShell, có thể truyền mã của native process bằng:

~~~powershell
java -jar batch-app.jar
exit $LASTEXITCODE
~~~

Một wrapper không truyền exit code có thể khiến scheduler nhìn thấy kết quả của lệnh cuối cùng trong script thay vì kết quả của Job.

## 16. Logging và audit kết quả trả về scheduler

Khi Job kết thúc, nên log các trường đủ để liên kết kết quả trong scheduler với metadata Spring Batch:

- Job name.
- JobInstance ID.
- JobExecution ID.
- BatchStatus.
- ExitStatus exit code.
- Exit description đã được làm sạch.
- Process exit code cuối cùng.
- Thời gian bắt đầu và kết thúc.
- Read/write/filter/skip counts quan trọng.

Ví dụ log có cấu trúc:

~~~text
event=job_finished
job=importOrdersJob
jobInstanceId=842
jobExecutionId=108
batchStatus=COMPLETED
exitStatus=COMPLETED_WITH_WARNINGS
processExitCode=4
readCount=12000
writeCount=11995
skipCount=5
~~~

Không log toàn bộ JobParameters hoặc payload nếu chúng có thể chứa credential hay dữ liệu cá nhân. Dùng execution ID để đối chiếu với JobRepository và audit store.

Khi điều tra một Job scheduler báo thất bại, so sánh process exit code với BatchStatus và ExitStatus. Nếu hai hệ thống không đồng ý, kiểm tra mapper và script wrapper trước khi kết luận Job xử lý dữ liệu sai.

## 17. Không để custom exit code che giấu BatchStatus

Một quy ước exit code có thể phân loại kết quả chi tiết, nhưng không nên làm sai trạng thái lifecycle.

Ví dụ, Job có BatchStatus FAILED vì database unavailable. Nếu listener đặt ExitStatus thành COMPLETED_WITH_WARNINGS và mapper trả 4, scheduler có thể hiểu đây là thành công có cảnh báo. Điều đó che giấu lỗi nghiêm trọng.

Nên đặt quy tắc ưu tiên:

1. BatchStatus FAILED luôn ánh xạ thành process code failure, trừ khi có quy trình đặc biệt được phê duyệt.
2. BatchStatus STOPPED ánh xạ thành mã dừng riêng nếu scheduler cần phân biệt.
3. Chỉ phân loại warning khi BatchStatus COMPLETED và điều kiện cảnh báo được xác định rõ.
4. UNKNOWN hoặc exit code chưa nhận diện phải ánh xạ thành non-zero.
5. Không để listener thay đổi kết quả FAILED thành COMPLETED chỉ để scheduler chạy bước downstream.

Nếu Job có trạng thái nghiệp vụ đặc biệt như VALIDATION_FAILED, quyết định rõ đó là một Job thất bại hay một Job hoàn tất với kết quả từ chối đầu vào. Scheduler, dashboard và người vận hành phải dùng cùng một định nghĩa.

## 18. Kiểm thử exit code

Cần kiểm thử cả mapping và process thực tế. Unit test cho mapper không đủ để chứng minh JVM trả đúng mã cho scheduler.

### Unit test cho mapper

~~~java
@Test
void mapsBatchExitStatusesToSchedulerCodes() {
    SchedulerExitCodeMapper mapper = new SchedulerExitCodeMapper();

    assertEquals(0, mapper.intValue("COMPLETED"));
    assertEquals(4, mapper.intValue("COMPLETED_WITH_WARNINGS"));
    assertEquals(20, mapper.intValue("STOPPED"));
    assertEquals(10, mapper.intValue("FAILED"));
    assertEquals(30, mapper.intValue("UNRECOGNIZED"));
}
~~~

Test cần khớp với bảng mapping thực tế của ứng dụng.

### Integration test cho Job

Chạy Job với các kịch bản:

- Job hoàn tất bình thường.
- Job hoàn tất có skip và tạo warning status.
- Job thất bại do reader, processor hoặc writer.
- Job bị stop có kiểm soát.
- ExitStatus tùy chỉnh được tổng hợp đúng ở JobExecution.
- Exception trong listener không làm mất kết quả hoặc metadata ngoài chủ đích.

### Test process thực tế

Khởi chạy application bằng cùng command mà scheduler sử dụng, rồi kiểm tra process exit code ở shell hoặc công cụ test process. Cần xác nhận:

- Code 0 khi Job hoàn thành.
- Code non-zero khi Job thất bại.
- Code warning theo quy ước khi Job hoàn tất có cảnh báo.
- Unknown exit status không bị ánh xạ thành 0.
- Script wrapper truyền đúng mã của Java process.
- Process chỉ thoát sau khi JobExecution kết thúc.

Đối với Spring Boot, test hàm main/exit integration hoặc khởi chạy process con trong môi trường kiểm thử. Không chỉ kiểm tra ExitCodeGenerator.getExitCode() rồi suy luận rằng scheduler sẽ nhận đúng giá trị.

## 19. Những lỗi thường gặp

**Nhầm ExitStatus với process exit code.** ExitStatus là chuỗi; scheduler cần số nguyên. Phải có mapper.

**Chỉ kiểm tra BatchStatus.** Job có thể COMPLETED nhưng ExitStatus tùy chỉnh cho biết có cảnh báo.

**Luôn trả code 0.** Scheduler có thể đánh dấu Job FAILED là thành công.

**Dùng code không xác định.** Scheduler có thể xử lý sai trạng thái mới. Luôn có default non-zero cho mã lạ.

**Custom mapper không được runner sử dụng.** Khai báo bean chưa chắc đã tích hợp vào command line runner. Xác nhận wiring thực tế.

**Process thoát trước khi Job kết thúc.** Với asynchronous launcher, exit code có thể phản ánh trạng thái trung gian.

**Script wrapper làm mất mã trả về.** Lệnh sau Java có thể ghi đè exit status nếu script không lưu và truyền lại mã.

**Dùng System.exit trong listener.** Có thể cắt ngang lifecycle và không lưu metadata đầy đủ.

**Dùng process exit code cho server lâu dài.** Server không nên thoát theo kết quả của từng Job; dùng API hoặc JobRepository để theo dõi.

**Đổi mapping mà không đổi scheduler.** Hai hệ thống không còn thống nhất ý nghĩa của code.

## 20. Quy trình triển khai exit code cho scheduler

Khi tích hợp Spring Batch với scheduler, hãy thực hiện theo trình tự:

1. Xác định scheduler cần phân biệt success/failure hay cả warning, stopped và validation failure.
2. Chọn quy ước process exit code, ghi rõ mã và ý nghĩa.
3. Phân biệt BatchStatus, ExitStatus và process exit code trong thiết kế.
4. Tạo ExitStatus tùy chỉnh ở cấp Step/Job khi thật sự cần.
5. Bảo đảm BatchStatus FAILED không bị chuyển thành mã success.
6. Cấu hình ExitCodeMapper hoặc ExitCodeGenerator phù hợp với cách launch.
7. Nếu dùng CommandLineJobRunner, xác nhận runner sử dụng mapper đã chọn.
8. Nếu dùng Spring Boot, chờ Job hoàn tất rồi gọi SpringApplication.exit và trả mã từ main cho process.
9. Bảo đảm shell/PowerShell wrapper truyền lại exit code của Java.
10. Kiểm thử bằng chính command và môi trường mà scheduler sẽ chạy.

ExitStatus cho Spring Batch biết Job kết thúc với kết quả logic nào; ExitCodeMapper hoặc ExitCodeGenerator chuyển kết quả đó thành số nguyên cho process; scheduler dùng process exit code để quyết định bước tiếp theo. Khi ba lớp này được thiết kế và kiểm thử cùng nhau, trạng thái Job trong JobRepository, mã trả về của JVM và kết quả mà scheduler hiển thị sẽ nhất quán.

