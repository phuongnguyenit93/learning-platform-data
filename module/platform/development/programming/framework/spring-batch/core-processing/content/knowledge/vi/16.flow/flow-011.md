# Restart flow sau step thất bại

Một Job trong Spring Batch thường gồm nhiều Step nối tiếp hoặc rẽ nhánh theo kết quả thực thi. Khi một Step thất bại, Job có thể kết thúc ở trạng thái FAILED. Nếu Job được thiết kế cho phép restart, lần chạy tiếp theo có thể tiếp tục từ Step chưa hoàn thành mà không phải thực hiện lại các Step đã hoàn tất.

Restart flow là cách Spring Batch khôi phục luồng thực thi dựa trên metadata đã lưu trong JobRepository. Để hoạt động đúng, ứng dụng cần giữ nguyên danh tính JobInstance, hiểu trạng thái của từng Step, thiết kế transition phù hợp và bảo đảm các thao tác được chạy lại an toàn.

## 1. Phân biệt JobInstance, JobExecution và StepExecution

Ba khái niệm này quyết định cách Spring Batch khôi phục Job:

| Khái niệm | Vai trò |
| --- | --- |
| **JobInstance** | Đại diện cho một lần xử lý logic, được xác định bởi Job name và identifying JobParameters |
| **JobExecution** | Một lần thực thi cụ thể của JobInstance; restart tạo JobExecution mới |
| **StepExecution** | Một lần thực thi cụ thể của Step trong một JobExecution |

Ví dụ Job nhập đơn hàng theo ngày:

~~~text
Job: dailyOrderImport
JobParameters: businessDate=2026-11-15
        |
        v
JobInstance A
        |
        +-- JobExecution #1: FAILED
        |       |
        |       +-- prepareInput: COMPLETED
        |       +-- importOrders: FAILED
        |       +-- publishReport: chưa chạy
        |
        +-- JobExecution #2: STARTED -> COMPLETED
                |
                +-- prepareInput: được bỏ qua
                +-- importOrders: chạy lại và COMPLETED
                +-- publishReport: chạy
~~~

JobExecution thứ hai thuộc cùng JobInstance A vì Job name và identifying parameters không thay đổi. JobRepository lưu lịch sử của cả hai lần thực thi và các StepExecution liên quan.

Đừng đồng nhất restart với tạo một JobInstance mới. Restart tiếp tục cùng phạm vi nghiệp vụ đã được nhận diện trước đó. Nếu thay đổi identifying JobParameters, Spring Batch có thể tạo JobInstance khác và instance mới không kế thừa trạng thái của instance cũ.

## 2. Điều kiện để restart một Job

Restart chỉ thực hiện được khi JobInstance trước đó chưa hoàn tất thành công và Job được phép restart.

Các điều kiện quan trọng:

- Job có cùng tên với lần chạy trước.
- Các identifying JobParameters giống với JobInstance cần restart.
- Job không bị cấu hình preventRestart().
- JobExecution trước đó đã kết thúc ở trạng thái có thể restart, thường là FAILED hoặc STOPPED.
- Các Step cần chạy lại chưa vượt startLimit.
- Các thành phần reader/writer hoặc Tasklet có cơ chế khôi phục phù hợp nếu cần checkpoint.

Nếu JobInstance đã COMPLETED, chạy lại cùng identifying parameters thường bị từ chối bằng JobInstanceAlreadyCompleteException. Nếu JobExecution trước vẫn đang chạy, yêu cầu trùng có thể bị từ chối bằng JobExecutionAlreadyRunningException.

### Giữ nguyên JobParameters khi restart

Giả sử lần chạy đầu dùng:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

Khi restart, giữ nguyên các identifying values:

~~~java
JobParameters restartParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-2026-11-15", true)
        .addString("requestedBy", "operator", false)
        .toJobParameters();
~~~

requestedBy là non-identifying nên có thể thay đổi mà không tạo JobInstance mới. Tuy nhiên, không nên thay đổi tham số non-identifying nếu logic nghiệp vụ dựa vào nó để quyết định dữ liệu cần xử lý. Các giá trị làm thay đổi phạm vi dữ liệu phải được thiết kế là identifying.

Không thêm timestamp hoặc UUID mới vào nhóm identifying chỉ để né trạng thái COMPLETED. Nếu cần một lần xử lý nghiệp vụ mới, hãy dùng một revision hoặc business key mới có ý nghĩa rõ ràng.

## 3. Restart trong Job có các Step chạy tuần tự

Với một Job tuyến tính, Spring Batch ghi nhận trạng thái của từng Step:

~~~java
@Bean
public Job dailyImportJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Step importOrdersStep,
        Step publishReportStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
            .start(prepareInputStep)
            .next(importOrdersStep)
            .next(publishReportStep)
            .build();
}
~~~

Giả sử:

- prepareInputStep hoàn tất.
- importOrdersStep thất bại.
- publishReportStep chưa được chạy.

JobExecution kết thúc FAILED. Khi restart cùng JobInstance, Spring Batch thường bỏ qua prepareInputStep vì Step đã COMPLETED, thực hiện lại importOrdersStep và chỉ chạy publishReportStep sau khi import thành công.

~~~text
Lần chạy đầu:

prepareInputStep  ----> COMPLETED
        |
        v
importOrdersStep  ----> FAILED
        |
        v
publishReportStep ----> chưa chạy

Restart cùng JobInstance:

prepareInputStep  ----> bỏ qua (đã COMPLETED)
        |
        v
importOrdersStep  ----> chạy lại
        |
        v
publishReportStep ----> chạy sau khi import thành công
~~~

Đây là hành vi restart cơ bản. JobRepository cung cấp lịch sử thực thi để Spring Batch xác định Step nào đã hoàn thành và Step nào cần thực hiện lại.

## 4. Step đã hoàn tất có được chạy lại không?

Mặc định, Step đã COMPLETED thường được bỏ qua khi restart Job. Hành vi này tránh lặp lại các thao tác đã hoàn thành.

Nếu một Step cần chạy lại trong mỗi lần restart, có thể cấu hình allowStartIfComplete(true):

~~~java
@Bean
public Step prepareInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PreparationService preparationService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        preparationService.prepareWorkspace();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("prepareInputStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
~~~

Với cấu hình này, Step có thể được thực hiện lại ngay cả khi lần thực thi trước đã COMPLETED. Chỉ dùng khi thao tác an toàn nếu chạy lại, chẳng hạn kiểm tra hoặc chuẩn bị workspace theo cách idempotent.

Không bật allowStartIfComplete(true) tùy tiện cho Step gửi email, chuyển file, ghi dữ liệu hoặc phát message. Các thao tác này có thể tạo side effect trùng khi Job restart.

## 5. Flow transition khi Step thất bại

Job flow có thể rẽ nhánh dựa trên ExitStatus của Step. Trong Java DSL, phương thức on(...) xác định mẫu ExitStatus dùng để chọn transition.

Ví dụ, nếu import thất bại, Job chạy một Step ghi nhận lỗi rồi kết thúc với trạng thái thất bại:

~~~java
@Bean
public Job orderImportJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Step importOrdersStep,
        Step recordFailureStep,
        Step publishReportStep) {

    return new JobBuilder("orderImportJob", jobRepository)
            .start(prepareInputStep)
                .on("FAILED").fail()
            .from(prepareInputStep)
                .on("*").to(importOrdersStep)
            .from(importOrdersStep)
                .on("FAILED").to(recordFailureStep)
            .from(importOrdersStep)
                .on("*").to(publishReportStep)
            .from(recordFailureStep)
                .on("*").fail()
            .from(publishReportStep)
                .on("*").end()
            .end()
            .build();
}
~~~

Flow này có các nhánh:

- prepareInputStep thất bại: Job kết thúc FAILED.
- prepareInputStep thành công: chuyển sang importOrdersStep.
- importOrdersStep thất bại: chạy recordFailureStep.
- recordFailureStep hoàn tất: flow kết thúc FAILED.
- importOrdersStep thành công: chuyển sang publishReportStep rồi kết thúc bình thường.

Việc gọi fail() làm flow kết thúc với trạng thái thất bại. Khi JobExecution thất bại, JobInstance có thể được restart nếu các điều kiện restart được đáp ứng.

### Thứ tự khai báo transition

Các pattern ExitStatus nên được khai báo từ cụ thể đến tổng quát. Ví dụ FAILED cụ thể hơn *. Nếu nhánh wildcard được chọn trước trong một cấu hình không phù hợp, nhánh lỗi có thể không được điều hướng như mong đợi.

on("FAILED") khớp với ExitStatus code của Step. Nó không trực tiếp kiểm tra enum BatchStatus, dù trong trường hợp Step thất bại thông thường ExitStatus mặc định cũng có code FAILED.

## 6. Phân biệt FAILED, END và COMPLETED trong flow

Một điểm quan trọng là flow transition có thể thay đổi kết quả cuối cùng của Job. Step có ExitStatus FAILED không nhất thiết khiến Job luôn kết thúc FAILED nếu flow được cấu hình để xử lý nhánh đó và kết thúc bình thường.

Các transition thường gặp:

| Transition | Ý nghĩa |
| --- | --- |
| on("FAILED").fail() | Kết thúc Job flow với trạng thái thất bại |
| on("FAILED").to(recoveryStep) | Chuyển sang Step phục hồi |
| on("*").to(nextStep) | Chuyển sang Step tiếp theo với các exit code còn lại |
| on("COMPLETED").end() | Kết thúc flow theo nhánh hoàn tất |
| on("FAILED").stopAndRestart(restartStep) | Dừng Job và lưu vị trí để restart từ Step được chỉ định |

Nếu nhánh lỗi chuyển sang recoveryStep và recoveryStep hoàn tất, flow có thể tiếp tục sang một nhánh khác hoặc kết thúc bình thường. Khi Job đã kết thúc COMPLETED, cùng JobInstance thường không thể restart như một Job thất bại. Vì vậy, cần quyết định rõ mục tiêu:

- Ghi nhận lỗi nhưng Job vẫn được coi là hoàn tất theo nghiệp vụ.
- Xử lý phục hồi rồi tiếp tục Job.
- Kết thúc Job FAILED để người vận hành sửa nguyên nhân và restart.
- Dừng Job ở trạng thái STOPPED và tiếp tục từ một Step được chỉ định.

Đừng dùng end() nếu ý định thực sự là để Job có thể restart sau lỗi. end() kết thúc flow theo trạng thái hoàn tất; fail() thể hiện Job thất bại.

## 7. Dùng recovery Step trong flow

Recovery Step có thể thực hiện các công việc như:

- Ghi nhận mã lỗi và business key.
- Di chuyển input lỗi vào khu vực quarantine.
- Ghi trạng thái batch để vận hành điều tra.
- Gửi thông báo thông qua cơ chế có kiểm soát.
- Chuẩn bị dữ liệu để một lần restart tiếp theo có thể tiếp tục.

Ví dụ recovery Step ghi nhận thông tin thất bại:

~~~java
@Bean
public Step recordFailureStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FailureAuditService auditService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        StepExecution currentStep =
                contribution.getStepExecution();

        auditService.recordFailure(
                currentStep.getJobExecutionId(),
                currentStep.getStepName(),
                currentStep.getExitStatus().getExitCode());

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("recordFailureStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

Trong thực tế, StepExecution hiện tại ở đây là StepExecution của recordFailureStep, không phải importOrdersStep đã thất bại. Muốn lấy thông tin Step thất bại, hãy tra cứu các StepExecution thuộc JobExecution hiện tại qua JobExecution hoặc JobExplorer và chọn đúng Step cần điều tra.

Nếu recoveryStep hoàn tất nhưng flow sau đó fail(), Job vẫn kết thúc FAILED. Khi restart, Spring Batch đánh giá lại flow từ trạng thái thực thi đã lưu. Step đã COMPLETED như prepareInputStep hoặc recordFailureStep thường được bỏ qua; Step thất bại sẽ được thực hiện lại.

Recovery Step nên idempotent. Nếu Step được chạy lại do một lần thực thi khác hoặc do thiết kế flow, ghi nhận lỗi không nên tạo nhiều bản ghi hoặc gửi nhiều thông báo ngoài ý muốn.

## 8. Dùng stopAndRestart khi cần dừng tại một vị trí

Có những Job không muốn đánh dấu FAILED ngay mà cần dừng có kiểm soát để người vận hành kiểm tra. Có thể dùng stopAndRestart(...) để kết thúc Job ở trạng thái STOPPED và lưu vị trí restart.

Ví dụ:

~~~java
return new JobBuilder("controlledImportJob", jobRepository)
        .start(validateInputStep)
            .on("FAILED").stopAndRestart(validateInputStep)
        .from(validateInputStep)
            .on("*").to(importOrdersStep)
        .from(importOrdersStep)
            .on("*").end()
        .end()
        .build();
~~~

Ví dụ chỉ minh họa transition dừng và vị trí restart. Cần chọn Step restart phù hợp với trạng thái dữ liệu. Khi Job STOPPED, lần tiếp theo có thể tiếp tục theo vị trí đã lưu sau khi nguyên nhân dừng được xử lý.

stopAndRestart không giống fail():

- fail() kết thúc Job với trạng thái FAILED.
- stopAndRestart(step) kết thúc Job ở trạng thái STOPPED và chỉ định nơi flow tiếp tục khi restart.
- end() kết thúc flow theo trạng thái hoàn tất.

Không dùng STOPPED chỉ để che giấu lỗi kỹ thuật. Hãy dùng khi quy trình có bước dừng/chờ có chủ đích, ví dụ chờ phê duyệt hoặc can thiệp của người vận hành.

## 9. startLimit và allowStartIfComplete

Hai thuộc tính này ảnh hưởng trực tiếp đến restart flow:

**startLimit** giới hạn số lần một Step được phép bắt đầu. Nếu số lần bắt đầu vượt giới hạn, Spring Batch có thể ném StartLimitExceededException.

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .startLimit(3)
        .build();
~~~

Trong ví dụ, Step được phép bắt đầu tối đa ba lần theo giới hạn cấu hình. Cần tính cả các lần thực thi trước khi vận hành restart; không nên đặt giới hạn quá thấp nếu quy trình cần nhiều lần khôi phục.

**allowStartIfComplete** cho phép Step đã hoàn tất được chạy lại khi Job restart:

~~~java
return new StepBuilder("refreshReferenceDataStep", jobRepository)
        .tasklet(refreshTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
~~~

Hai thuộc tính giải quyết hai vấn đề khác nhau: startLimit giới hạn số lần bắt đầu, còn allowStartIfComplete quyết định có chạy lại Step đã COMPLETED hay không.

## 10. Flow restart và ExecutionContext

JobRepository lưu metadata của JobExecution, StepExecution và ExecutionContext. ExecutionContext giúp các thành phần lưu tiến độ cần thiết để tiếp tục sau restart.

Trong chunk-oriented Step, reader có thể triển khai ItemStream để lưu checkpoint:

- open(ExecutionContext): khôi phục vị trí hoặc trạng thái.
- update(ExecutionContext): lưu trạng thái hiện tại tại ranh giới chunk.
- close(): giải phóng resource.

Ví dụ FlatFileItemReader hỗ trợ lưu trạng thái:

~~~java
@Bean
public FlatFileItemReader<OrderInput> orderReader(Resource inputFile) {
    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerCode", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Nếu Step thất bại giữa một chunk, chunk chưa commit có thể phải được đọc và xử lý lại. Reader có thể khôi phục từ checkpoint gần nhất đã commit nếu trạng thái được lưu và nguồn dữ liệu vẫn ổn định.

Tasklet tùy chỉnh không tự động có checkpoint chi tiết. Nếu Tasklet đã thực hiện một phần công việc trước khi ném exception, cần lưu tiến độ trong ExecutionContext hoặc kho trạng thái bền vững và bảo đảm checkpoint nhất quán với dữ liệu nghiệp vụ.

### Giữ input ổn định giữa các lần chạy

Checkpoint theo số dòng hoặc offset chỉ đúng nếu file không bị thay thế. Với database, checkpoint theo khóa cần thứ tự truy vấn ổn định. Nếu nguồn thay đổi giữa lần chạy đầu và restart, reader có thể bỏ sót hoặc đọc trùng dữ liệu.

Có thể dùng file ID/version, snapshot, watermark hoặc keyset checkpoint để bảo đảm lần restart đọc cùng một phạm vi dữ liệu.

## 11. Restart flow với nhiều nhánh

Trong Job phức tạp, Step có thể rẽ nhánh theo ExitStatus hoặc kết quả từ JobExecutionDecider. Khi restart, flow được đánh giá lại dựa trên trạng thái và dữ liệu thực thi đã lưu.

Ví dụ flow:

~~~text
                  +----------------------+
                  |                      |
                  v                      |
prepareInput -> importOrders ------------+
                  |
                  +-- COMPLETED --> publishReport --> END
                  |
                  +-- FAILED ----> recordFailure --> FAIL
~~~

Nếu importOrders thất bại và recordFailure hoàn tất, Job vẫn kết thúc FAILED theo nhánh được cấu hình. Khi restart cùng JobInstance:

- prepareInput đã COMPLETED nên thường được bỏ qua.
- importOrders là Step thất bại nên được thực hiện lại.
- Nếu importOrders thành công, flow đi theo nhánh thành công đến publishReport.
- recordFailure đã COMPLETED từ execution trước thường không chạy lại vì flow thành công không đi qua nhánh lỗi.

Đây là lý do cần thiết kế flow có thể đánh giá lại đúng từ Step thất bại. Các Step phụ trợ nên idempotent vì có thể được thực thi lại trong những tình huống khác nhau.

### JobExecutionDecider

Nếu nhánh flow phụ thuộc vào dữ liệu nghiệp vụ hoặc trạng thái đã lưu, có thể dùng JobExecutionDecider để quyết định trạng thái flow:

~~~java
public class ImportDecision implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        boolean hasRejectedData =
                jobExecution.getExecutionContext()
                        .getBoolean("hasRejectedData", false);

        return hasRejectedData
                ? new FlowExecutionStatus("HAS_REJECTED")
                : FlowExecutionStatus.COMPLETED;
    }
}
~~~

Decider trả về FlowExecutionStatus để chọn transition tiếp theo. Khi dùng decider trong flow restart, dữ liệu mà decider dựa vào phải được lưu bền vững và nhất quán. Không dựa vào biến static hoặc trạng thái chỉ tồn tại trong bộ nhớ vì restart có thể chạy trên process hoặc node khác.

## 12. Restart và side effect

Restart có thể chạy lại một Step đã thất bại. Nếu Step ghi dữ liệu, gửi message, gọi API hoặc tạo file, việc thực hiện lại có thể tạo side effect trùng.

Ví dụ:

~~~text
importOrdersStep:
  1. ghi 500 đơn hàng vào database
  2. gửi thông báo tới hệ thống khác
  3. lỗi trước khi Step hoàn tất

Restart:
  Step được chạy lại
  -> có nguy cơ ghi trùng hoặc gửi thông báo lần hai
~~~

Để tránh lỗi:

- Dùng khóa nghiệp vụ hoặc unique constraint để chống ghi trùng.
- Thiết kế writer idempotent.
- Dùng outbox để ghi sự kiện cùng transaction dữ liệu.
- Dùng idempotency key ổn định cho API ngoài.
- Ghi nhận trạng thái operation để biết side effect nào đã hoàn tất.
- Tách các thao tác không thể rollback khỏi transaction database và thiết kế cơ chế đối soát.

Rollback transaction database không tự thu hồi HTTP request, email, message đã gửi hoặc file đã được chuyển. Restart flow chỉ điều khiển thứ tự Step; tính an toàn của side effect vẫn là trách nhiệm thiết kế của ứng dụng.

## 13. Khởi động lại Job bằng API

Có thể dùng JobOperator để restart một JobExecution đã kết thúc ở trạng thái có thể restart:

~~~java
long failedExecutionId = 12345L;
long newExecutionId =
        jobOperator.restart(failedExecutionId);
~~~

API cụ thể có thể ném các exception liên quan đến JobExecution không tồn tại, JobInstance đã hoàn tất, Job không thể restart hoặc JobParameters không hợp lệ. Cần xử lý các trường hợp đó ở lớp điều phối và trả thông tin phù hợp cho người vận hành.

Một cách khác là gọi JobLauncher với cùng Job và identifying JobParameters khi execution trước đã FAILED hoặc STOPPED:

~~~java
JobExecution execution =
        jobLauncher.run(dailyImportJob, originalParameters);
~~~

Nếu JobInstance cũ đủ điều kiện restart, JobRepository tạo JobExecution mới cho instance đó. Nếu instance đã COMPLETED hoặc đang chạy, yêu cầu có thể bị từ chối.

Không tạo tham số identifying mới khi mục tiêu là restart. Với vận hành production, nên lưu execution ID, business key và identifying parameters để có thể tra cứu chính xác execution cần restart.

## 14. Quan sát flow và lịch sử restart

JobExplorer cung cấp API đọc metadata để xem lịch sử JobInstance, JobExecution và StepExecution.

Ví dụ tra cứu các StepExecution của một JobExecution:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, exitStatus={}, read={}, write={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount());
    }
}
~~~

Khi điều tra restart, hãy đối chiếu:

- JobInstance ID và identifying JobParameters.
- JobExecution ID, BatchStatus và ExitStatus.
- StepExecution của từng Step qua các lần chạy.
- Step nào đã COMPLETED, FAILED hoặc STOPPED.
- ExecutionContext và checkpoint đã lưu.
- Flow transition nào được chọn sau ExitStatus.
- Exception gốc và side effect đã thực hiện.

Có thể truy vấn bảng metadata để hỗ trợ vận hành, nhưng không nên cập nhật hoặc xóa trực tiếp các hàng để ép Job restart. Việc sửa metadata thủ công có thể phá vỡ quan hệ khóa ngoại, trạng thái và checkpoint.

## 15. Những lỗi thường gặp

### Thay identifying parameters khi restart

JobRepository xem bộ tham số mới là một JobInstance khác. Giữ nguyên Job name và identifying parameters khi muốn restart instance cũ.

### Dùng end() cho nhánh cần restart

end() kết thúc flow theo trạng thái hoàn tất. Nếu mục tiêu là để Job FAILED và có thể restart, dùng transition fail() phù hợp.

### Nhầm ExitStatus với BatchStatus

Flow on(...) khớp ExitStatus code. BatchStatus mô tả vòng đời thực thi. Hai trạng thái thường tương ứng nhưng không phải cùng một khái niệm.

### Step đã COMPLETED chạy lại ngoài ý muốn

Kiểm tra allowStartIfComplete(true). Chỉ bật khi Step cần chạy lại và thao tác idempotent.

### Step thất bại nhưng bị chạy quá số lần cho phép

Kiểm tra startLimit. Nếu vượt giới hạn, Spring Batch có thể ném StartLimitExceededException.

### Recovery Step làm Job thành COMPLETED dù cần restart

Nếu nhánh lỗi đi qua recoveryStep rồi kết thúc bằng end(), Job có thể được xem là hoàn tất. Nếu cần người vận hành sửa lỗi rồi restart, kết thúc nhánh bằng fail() hoặc thiết kế STOPPED theo đúng mục đích.

### Flow wildcard che nhánh lỗi

Khai báo các transition cụ thể như FAILED trước wildcard. Kiểm tra ExitStatus thực tế của Step để bảo đảm pattern khớp.

### Step chạy lại tạo side effect trùng

Restart không tự hoàn tác API, message hoặc file đã tạo. Dùng idempotency key, unique key, outbox hoặc compensation.

### Reader không khôi phục được checkpoint

Custom reader cần hỗ trợ ItemStream hoặc một cơ chế checkpoint bền vững. Input cũng cần ổn định giữa lần chạy đầu và restart.

### Recovery logic phụ thuộc state trong bộ nhớ

Restart có thể chạy trên process hoặc node khác. Dùng JobRepository, ExecutionContext hoặc kho trạng thái bền vững thay cho biến static hoặc singleton state.

## 16. Quy trình thiết kế restart flow

Khi xây dựng Job có khả năng restart, hãy xác định:

1. JobInstance được nhận diện bằng những identifying parameters nào?
2. Step nào có thể thất bại và Step nào cần chạy lại?
3. Step đã COMPLETED có cần chạy lại không?
4. Nhánh FAILED sẽ kết thúc Job, chuyển sang recovery hay dừng chờ vận hành?
5. Recovery Step có cần chạy lại khi restart không và có idempotent không?
6. startLimit có đủ cho số lần khôi phục dự kiến không?
7. Reader/Tasklet lưu checkpoint ở đâu và checkpoint có nhất quán với dữ liệu đã commit không?
8. Side effect ngoài transaction được chống trùng như thế nào?
9. Flow transition dựa trên ExitStatus nào và wildcard có được đặt đúng thứ tự không?
10. Người vận hành tra cứu và restart bằng JobExecution ID nào?

Nên kiểm thử ít nhất các tình huống: Step đầu thất bại, Step giữa thất bại, recovery Step thất bại, restart thành công, Step đã hoàn tất được bỏ qua, Step có allowStartIfComplete và restart vượt startLimit.

## Kết luận

Restart flow sau Step thất bại dựa trên metadata JobRepository, trạng thái StepExecution và cùng JobInstance được xác định bởi Job name cùng identifying JobParameters. Khi restart, Spring Batch thường bỏ qua Step đã COMPLETED và chạy lại Step thất bại; allowStartIfComplete và startLimit điều chỉnh hành vi này. Flow transition dùng ExitStatus để chọn nhánh: fail() giữ Job ở trạng thái FAILED để có thể restart, recovery Step có thể ghi nhận hoặc xử lý lỗi, còn end() kết thúc flow theo trạng thái hoàn tất. Muốn restart an toàn, cần checkpoint bền vững, input ổn định và side effect idempotent.
