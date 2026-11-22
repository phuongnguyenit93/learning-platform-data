# Theo dõi status của job con

Trong Spring Batch, `JobStep` cho phép một job cha khởi chạy một job khác như một step trong quy trình. Cách tổ chức này hữu ích khi một quy trình lớn gồm nhiều job con có trách nhiệm riêng, chẳng hạn job cha điều phối nhập dữ liệu, đối soát và tạo báo cáo. Khi sử dụng JobStep, cần theo dõi trạng thái ở nhiều cấp: `JobExecution` của job con, `StepExecution` của JobStep trong job cha và `JobExecution` của chính job cha.

Các cấp trạng thái này có quan hệ với nhau nhưng không phải cùng một đối tượng. Hiểu đúng quan hệ đó giúp ứng dụng giám sát chính xác, xử lý lỗi, restart và quyết định nhánh flow tiếp theo.

## 1. JobStep là gì?

`JobStep` là một loại step có nhiệm vụ khởi chạy một `Job` khác. Job đang chứa JobStep được gọi là job cha (parent job); job được khởi chạy từ step đó là job con (child job).

Ví dụ, một quy trình xử lý đơn hàng cuối ngày có thể được tổ chức như sau:

```text
dailyOrderJob (job cha)
        |
        v
   validateInputStep
        |
        v
   importChildJobStep --------> importOrdersJob (job con)
        |                              |
        |                              +-- readOrdersStep
        |                              +-- writeOrdersStep
        |                              +-- validateResultStep
        v
   reconcileChildJobStep -----> reconcileOrdersJob (job con)
        |
        v
   publishReportStep
```

Trong sơ đồ, `importChildJobStep` là một `StepExecution` thuộc job cha. Khi step này chạy, nó dùng `JobLauncher` để khởi chạy `importOrdersJob`. Job con có `JobExecution` và các `StepExecution` riêng của nó.

JobStep giúp tái sử dụng job đã có, chia quy trình lớn thành các đơn vị có thể vận hành riêng và giữ mỗi job con có metadata, trạng thái, listener và lịch sử thực thi riêng.

## 2. Có những status nào cần theo dõi?

Khi một JobStep chạy, tối thiểu cần phân biệt ba đối tượng:

| Đối tượng | Thuộc về | Vai trò |
|---|---|---|
| Child `JobExecution` | Job con | Trạng thái của lần thực thi job con, gồm các step bên trong job con. |
| Parent `StepExecution` | Job cha | Trạng thái của step đang khởi chạy job con. |
| Parent `JobExecution` | Job cha | Trạng thái tổng thể của lần chạy job cha. |

Ví dụ:

```text
Parent JobExecution: dailyOrderJob
  |
  +-- StepExecution: validateInputStep       COMPLETED
  |
  +-- StepExecution: importChildJobStep      COMPLETED
  |       |
  |       +-- Child JobExecution: importOrdersJob
  |               +-- readOrdersStep         COMPLETED
  |               +-- writeOrdersStep        COMPLETED
  |               +-- validateResultStep     COMPLETED
  |
  +-- StepExecution: publishReportStep       STARTED
```

Khi job con hoàn tất, JobStep ghi nhận kết quả của lần chạy con trong quá trình thực thi step cha. Job cha sau đó tiếp tục theo flow được cấu hình. Nếu job con thất bại, JobStep thường thất bại và ảnh hưởng đến trạng thái job cha, trừ khi flow của job cha có nhánh xử lý kết quả đó.

Không nên chỉ nhìn một status duy nhất rồi kết luận toàn bộ quy trình thành công. Cần xác định status đang nói đến job con, step khởi chạy job con hay job cha.

## 3. BatchStatus và ExitStatus

Spring Batch sử dụng hai khái niệm trạng thái quan trọng:

- `BatchStatus`: trạng thái vòng đời thực thi, ví dụ `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPING`, `STOPPED`, `ABANDONED` hoặc `UNKNOWN`.
- `ExitStatus`: mã kết quả của job hoặc step, có thể là `COMPLETED`, `FAILED`, `STOPPED` hoặc một mã tùy chỉnh do ứng dụng định nghĩa.

`BatchStatus` thường được dùng để biết execution đang chạy, đã hoàn tất hay thất bại. `ExitStatus` được dùng nhiều trong điều khiển flow, listener và báo cáo kết quả nghiệp vụ.

Ví dụ một job con có thể hoàn tất về mặt kỹ thuật nhưng trả exit code tùy chỉnh:

```java
return new ExitStatus("COMPLETED_WITH_WARNINGS");
```

Khi đó cần phân biệt:

| Giá trị | Ý nghĩa |
|---|---|
| `BatchStatus.COMPLETED` | JobExecution đã kết thúc thành công theo trạng thái thực thi của framework. |
| `ExitStatus("COMPLETED_WITH_WARNINGS")` | Kết quả kết thúc tùy chỉnh, có cảnh báo nghiệp vụ. |

JobStep có thể chuyển tiếp kết quả `ExitStatus` của job con lên step cha theo cơ chế thực thi của nó. Trạng thái của step cha và job cha còn phụ thuộc cách JobStep xử lý kết quả và flow transition đã khai báo. Vì vậy, nếu ứng dụng cần phân biệt thành công hoàn toàn với thành công có cảnh báo, hãy thiết kế exit code rõ ràng và kiểm tra hành vi truyền trạng thái trên phiên bản Spring Batch đang dùng.

## 4. Khai báo một JobStep

Trong Spring Batch 5 trở lên, có thể xây dựng JobStep bằng `StepBuilder` với job con, launcher và parameters extractor:

```java
@Bean
Step importChildJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job importOrdersJob,
        JobParametersExtractor childParametersExtractor) {

    return new StepBuilder("importChildJobStep", jobRepository)
            .job(importOrdersJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

Các thành phần:

- `jobRepository`: lưu metadata cho step thuộc job cha.
- `jobLauncher`: khởi chạy job con.
- `importOrdersJob`: định nghĩa job được gọi.
- `JobParametersExtractor`: tạo bộ JobParameters truyền cho job con dựa trên thông tin thực thi của job cha.

JobStep không tự động có nghĩa là tất cả JobParameters của job cha luôn được truyền nguyên vẹn cho job con. Hãy cấu hình extractor để xác định rõ tham số nào cần chuyển tiếp và giá trị nào cần lấy từ execution context.

## 5. JobParameters của job con

Job con có danh tính riêng. `JobInstance` của job con được xác định bởi tên job con và các identifying `JobParameters` mà extractor cung cấp.

Ví dụ job cha chạy với:

```text
Parent job parameters:
  businessDate = 2026-11-15
  sourceSystem = ERP
  requestedBy  = scheduler
```

Job con có thể chỉ cần hai tham số định danh:

```text
Child job parameters:
  businessDate = 2026-11-15   identifying = true
  sourceSystem = ERP          identifying = true
```

Nếu lần chạy job cha sau đó khởi chạy lại cùng job con với cùng identifying parameters, Spring Batch sẽ nhận diện cùng JobInstance của job con. Điều này rất quan trọng đối với restart. Nếu tự động thêm một UUID mới mỗi lần gọi, mỗi lần sẽ tạo một JobInstance khác và không còn là restart cùng instance.

### Sử dụng DefaultJobParametersExtractor

`DefaultJobParametersExtractor` hỗ trợ lấy các key được chỉ định từ JobParameters hoặc ExecutionContext của step cha để tạo JobParameters cho job con. Ví dụ:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    DefaultJobParametersExtractor extractor =
            new DefaultJobParametersExtractor();
    extractor.setKeys(new String[]{"businessDate", "sourceSystem"});
    return extractor;
}
```

Các key cần được cung cấp ở nguồn mà extractor đọc, và kiểu/giá trị phải phù hợp với job con. Nếu cần quy tắc ánh xạ phức tạp hơn, có thể triển khai `JobParametersExtractor` riêng.

Nên xác định rõ tham số nào là identifying của job con. Tham số không định danh có thể dùng để ghi nhận người yêu cầu hoặc thông tin trace mà không làm thay đổi identity của child JobInstance.

## 6. Child JobExecution được tạo và lưu ở đâu?

Khi JobStep gọi `JobLauncher`, launcher đăng ký và thực thi job con thông qua `JobRepository` mà launcher đang sử dụng. Job con có `JobInstance` và `JobExecution` riêng, cùng các `StepExecution` cho những step bên trong.

Thông thường, job cha và job con cùng dùng một JobRepository của ứng dụng Spring Batch. Khi đó metadata của parent và child được lưu trong các bảng metadata tương ứng, có thể tra cứu qua `JobExplorer`.

```text
JobRepository
  |
  +-- Parent JobInstance
  |      +-- Parent JobExecution
  |              +-- Parent StepExecution: importChildJobStep
  |
  +-- Child JobInstance
         +-- Child JobExecution
                 +-- Child StepExecution: readOrdersStep
                 +-- Child StepExecution: writeOrdersStep
```

Parent `StepExecution` không phải là child `JobExecution`. Việc JobStep khởi chạy job con không biến các step bên trong job con thành step trực tiếp của job cha. Chúng được lưu dưới child JobExecution.

Nếu ứng dụng cấu hình nhiều JobRepository hoặc nhiều datasource, cần xác định rõ repository nào được JobLauncher sử dụng và nơi lưu metadata của child job. Khi parent và child dùng repository khác nhau, việc giám sát và vận hành phải tra cứu đúng repository tương ứng.

## 7. Theo dõi child job bằng JobExplorer

`JobExplorer` là API đọc metadata thực thi. Nó phù hợp để xây dựng màn hình giám sát hoặc service truy vấn trạng thái job con.

Nếu biết child JobExecution ID, có thể tra cứu trực tiếp:

```java
@Service
public class ChildJobStatusService {

    private final JobExplorer jobExplorer;

    public ChildJobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Từ JobExecution có thể đọc:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    BatchStatus status = execution.getStatus();
    ExitStatus exitStatus = execution.getExitStatus();
    var startTime = execution.getStartTime();
    var endTime = execution.getEndTime();
}
```

Tên kiểu thời gian cụ thể của getter phụ thuộc phiên bản Spring Batch; ví dụ trên minh họa các trường thông tin cần theo dõi. Có thể đọc thêm `failureExceptions`, `stepExecutions` và `jobParameters` để hiển thị nguyên nhân hoặc tiến độ.

Nếu chưa biết execution ID, có thể tìm các JobInstance của job con theo tên:

```java
List<JobInstance> instances = jobExplorer.getJobInstances(
        "importOrdersJob", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions =
            jobExplorer.getJobExecutions(instance);

    for (JobExecution execution : executions) {
        System.out.println(
                execution.getId() + " : " + execution.getStatus());
    }
}
```

Đây là cách tra cứu lịch sử theo job name. Trong hệ thống thật, nên lọc theo identifying parameters hoặc một mã batch nghiệp vụ để xác định đúng child JobInstance, thay vì chỉ lấy một số instance gần nhất rồi đoán execution nào thuộc parent run.

## 8. Làm thế nào liên kết parent StepExecution với child JobExecution?

Để giám sát một quy trình lồng nhau, hệ thống cần biết child execution nào được khởi chạy từ parent `JobStep`. Một cách chắc chắn là ghi lại định danh liên kết trong metadata hoặc bảng giám sát nghiệp vụ.

Không nên giả định mọi phiên bản hoặc cấu hình JobStep đều cung cấp sẵn một API công khai để lấy child JobExecution ID từ parent StepExecution. Nếu màn hình giám sát cần liên kết trực tiếp, hãy thiết kế việc ghi nhận rõ ràng.

Một số hướng triển khai:

- Dùng listener của child job để ghi nhận child JobExecution ID cùng parent job/step identity nếu thông tin cha được truyền vào.
- Đưa parent execution ID hoặc parent step execution ID vào child JobParameters dưới dạng non-identifying để phục vụ trace.
- Dùng một bảng điều phối riêng lưu parent execution ID, parent step execution ID, child execution ID, child job name và batch reference.
- Khi khởi chạy child job qua một service tùy chỉnh, lưu lại ID trả về từ JobLauncher trong một cơ chế metadata phù hợp.

Ví dụ, parent execution ID có thể được truyền cho child job để truy vết:

```java
JobParameters childParameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("sourceSystem", sourceSystem, true)
        .addLong("parentExecutionId", parentExecutionId, false)
        .toJobParameters();
```

`parentExecutionId` ở đây là non-identifying vì nó chỉ phục vụ liên kết vận hành. Nếu nó được đánh dấu identifying, cùng một kỳ xử lý khi khởi chạy từ parent execution mới có thể tạo child JobInstance mới, làm thay đổi semantics restart.

Khi sử dụng JobStep mặc định, cần xem cách extractor lấy parameters và cách listener được gọi để truyền/ghi nhận thông tin cha. Nếu cần lưu ID child chính xác, có thể bọc việc khởi chạy bằng thành phần điều phối riêng hoặc dùng listener/metadata tùy chỉnh phù hợp với kiến trúc.

## 9. Child job thất bại ảnh hưởng đến parent như thế nào?

Khi child job kết thúc với `BatchStatus.FAILED`, JobStep thường không thể coi step cha là hoàn tất thành công. Kết quả thất bại của child được phản ánh lên JobStep và parent flow sẽ tiếp tục theo cấu hình xử lý lỗi.

Ví dụ flow đơn giản:

```java
@Bean
Job dailyOrderJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importChildJobStep,
        Step publishReportStep) {

    return new JobBuilder("dailyOrderJob", jobRepository)
            .start(validateInputStep)
            .next(importChildJobStep)
            .next(publishReportStep)
            .build();
}
```

Nếu `importChildJobStep` thất bại, flow tuần tự mặc định không tiếp tục `publishReportStep` như một step thành công thông thường. Parent job có thể kết thúc `FAILED`.

Nếu cần xử lý lỗi có chủ đích, có thể khai báo nhánh theo `ExitStatus`:

```java
@Bean
Job dailyOrderJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importChildJobStep,
        Step publishReportStep,
        Step recordImportFailureStep) {

    return new JobBuilder("dailyOrderJob", jobRepository)
            .start(validateInputStep)
            .next(importChildJobStep)
                .on("COMPLETED").to(publishReportStep)
            .from(importChildJobStep)
                .on("FAILED").to(recordImportFailureStep)
            .from(publishReportStep)
                .on("*").end()
            .from(recordImportFailureStep)
                .on("*").fail()
            .end()
            .build();
}
```

Ví dụ minh họa flow có nhánh theo exit code. Trong ứng dụng thực tế, cần cấu hình tất cả transition cần thiết và xác định rõ trạng thái cuối cùng của parent job. Không nên kết thúc parent job với `COMPLETED` nếu child job thất bại mà nghiệp vụ yêu cầu toàn quy trình phải được xem là thất bại.

## 10. Theo dõi tiến độ bên trong child job

Child JobExecution có tập `StepExecution` riêng. Để biết job con đang ở step nào, có thể đọc `getStepExecutions()` từ child JobExecution hoặc dùng `JobExplorer` truy vấn metadata.

Ví dụ xây dựng thông tin tiến độ:

```java
JobExecution childExecution = jobExplorer.getJobExecution(childExecutionId);

if (childExecution != null) {
    for (StepExecution stepExecution : childExecution.getStepExecutions()) {
        System.out.printf(
                "%s: %s, read=%d, write=%d, skip=%d%n",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount());
    }
}
```

Các counter như `readCount`, `writeCount`, `filterCount`, `skipCount`, `commitCount` và `rollbackCount` giúp hiểu tiến độ xử lý. Chúng là số liệu của từng StepExecution, không nhất thiết là tổng số bản ghi nghiệp vụ đã được áp dụng thành công ở mọi hệ thống ngoài.

Nếu child job có nhiều step, màn hình giám sát nên hiển thị:

- Child job name và JobExecution ID.
- BatchStatus và ExitStatus.
- Step hiện tại hoặc danh sách step cùng trạng thái.
- Thời điểm bắt đầu, kết thúc và thời gian chạy.
- Số item đọc, ghi, filter, skip và rollback.
- Exception hoặc thông tin lỗi đã được phép hiển thị.
- Parent execution/step ID để người vận hành lần ngược về job cha.

## 11. JobExecutionListener và StepExecutionListener

Listener giúp ghi log hoặc phát thông tin khi job/step bắt đầu và kết thúc. Với mô hình parent-child, có thể gắn listener vào job con để ghi nhận kết quả child execution và listener vào JobStep để theo dõi trạng thái step cha.

Ví dụ listener cho child job:

```java
@Component
public class ChildJobExecutionListener implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution jobExecution) {
        // Ghi log child execution bắt đầu.
        log.info("Child job {} execution {} started",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        // Ghi status và exit code sau khi child job kết thúc.
        log.info("Child job execution {} ended with status {} and exit {}",
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());
    }
}
```

Listener có thể ghi metric, audit hoặc cập nhật bảng giám sát. Nên giữ listener ngắn và tránh để lỗi ghi log/monitoring làm thay đổi kết quả nghiệp vụ của job nếu đó không phải yêu cầu có chủ đích.

Đối với parent JobStep, `StepExecutionListener` có thể ghi nhận thời gian và trạng thái của step khởi chạy job con. Nếu cần lưu child execution ID, listener child job hoặc một cơ chế điều phối tùy chỉnh cần ghi nhận ID đó rõ ràng.

## 12. JobExplorer và JobOperator khác nhau thế nào?

Hai API này thường được dùng trong công cụ vận hành nhưng có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| `JobExplorer` | Đọc và tra cứu metadata như JobInstance, JobExecution và StepExecution. |
| `JobOperator` | Cung cấp các thao tác quản trị như start, restart, stop và tra cứu thông tin execution theo API phiên bản hỗ trợ. |
| `JobRepository` | Lưu metadata và được framework sử dụng trong quá trình thực thi. |
| `JobLauncher` | Khởi chạy một job với JobParameters. |

Với màn hình theo dõi status, `JobExplorer` thường là điểm truy vấn phù hợp. Với thao tác vận hành như yêu cầu dừng hoặc restart child job, dùng API quản trị như `JobOperator` theo cấu hình của ứng dụng.

Không nên cập nhật trực tiếp các bảng metadata để ép child job sang `COMPLETED`, `FAILED` hoặc `STOPPED`. Việc sửa metadata thủ công có thể làm sai quan hệ giữa JobInstance, JobExecution, StepExecution và trạng thái parent-child.

## 13. Restart khi child job thất bại

Một lợi ích của JobStep là child job có lịch sử thực thi và cơ chế restart riêng. Khi child job thất bại, có thể xử lý nguyên nhân rồi restart parent job hoặc thực hiện quy trình restart child phù hợp với thiết kế.

Luồng thường gặp:

```text
Parent JobExecution #1
   |
   +-- importChildJobStep -> FAILED
             |
             v
       Child JobExecution #1 -> FAILED

Sau khi khắc phục nguyên nhân:

Parent JobExecution #2 (restart parent JobInstance)
   |
   +-- importChildJobStep -> khởi chạy lại child job
             |
             v
       Child JobExecution #2 -> COMPLETED
```

Để child job restart đúng JobInstance, extractor cần cung cấp cùng các identifying parameters đã dùng trước đó. Nếu tham số định danh thay đổi, child job sẽ tạo một JobInstance mới.

Các điều kiện cần kiểm tra:

- Child job có cho phép restart hay được cấu hình `preventRestart()`?
- Child JobInstance đang ở trạng thái nào?
- Step thất bại có vượt `startLimit` hoặc có cấu hình restart đặc biệt không?
- Reader/writer của child job có lưu checkpoint và có thể khôi phục không?
- Các thao tác đã commit hoặc tác dụng phụ ngoài transaction có an toàn khi chạy lại không?
- Parent JobStep có được phép bắt đầu lại theo cấu hình của step không?

Nếu child job đã `COMPLETED` nhưng parent JobStep chưa kịp ghi nhận hoàn tất do process dừng ở một thời điểm nhạy cảm, lần restart có thể cố khởi chạy cùng child JobInstance và gặp `JobInstanceAlreadyCompleteException`. Khi đó cần tra cứu metadata của cả parent và child trước khi quyết định cách tiếp tục. Không nên tự thêm run ID mới để né lỗi nếu nghiệp vụ thực sự cần tiếp tục cùng đơn vị xử lý.

## 14. Child job chạy đồng bộ và bất đồng bộ

JobStep thường cần biết kết quả thực thi của child job để hoàn tất `StepExecution` của parent. Vì vậy, cách cấu hình JobLauncher có ảnh hưởng trực tiếp đến việc theo dõi trạng thái.

Với launcher đồng bộ, lời gọi `run` chờ child job kết thúc rồi mới trả về. JobStep có thể sử dụng kết quả cuối cùng để xác định trạng thái step cha.

Với launcher bất đồng bộ, `run` có thể trả về khi child job vẫn đang chạy. Nếu dùng trực tiếp launcher bất đồng bộ trong JobStep mà không có cơ chế điều phối bổ sung, parent step có nguy cơ kết thúc trước khi child job thực sự hoàn tất hoặc không phản ánh đúng trạng thái cuối cùng.

Do đó, với JobStep tiêu chuẩn, nên dùng launcher đồng bộ để parent step chờ child job hoàn tất. Nếu yêu cầu nghiệp vụ là khởi chạy child job nền rồi cho parent tiếp tục ngay, hãy thiết kế một mô hình điều phối bất đồng bộ riêng: lưu child execution ID, có trạng thái chờ/đối soát, và chỉ đánh dấu giai đoạn cha hoàn tất khi điều kiện nghiệp vụ được đáp ứng.

## 15. Status của child job có thể khác kết quả nghiệp vụ

Một child job có thể kết thúc `COMPLETED` dù đã skip một số item hoặc filter một số bản ghi. Điều này có thể hoàn toàn đúng nếu job được thiết kế để chấp nhận dữ liệu không hợp lệ trong giới hạn cho phép.

Ví dụ:

```text
Child JobExecution: COMPLETED
  readCount   = 10,000
  writeCount  = 9,970
  filterCount = 20
  skipCount   = 10
```

`COMPLETED` chỉ cho biết job hoàn tất theo quy tắc thực thi đã cấu hình. Nó không có nghĩa tất cả 10.000 item đều được ghi thành công. Nếu parent cần quyết định có tiếp tục hay không dựa trên tỷ lệ skip, child job nên phát ra một ExitStatus tùy chỉnh hoặc lưu kết quả nghiệp vụ để parent kiểm tra.

Ví dụ child job có thể đặt exit code `COMPLETED_WITH_WARNINGS` khi số bản ghi skip vượt một ngưỡng cảnh báo. Parent flow có thể định tuyến theo exit code đó.

## 16. Ví dụ theo dõi child status bằng bảng giám sát

Trong hệ thống có nhiều job con, có thể tạo bảng giám sát riêng để liên kết parent và child. Một cấu trúc đơn giản có thể gồm:

| Cột | Mục đích |
|---|---|
| `parent_execution_id` | ID JobExecution của job cha. |
| `parent_step_execution_id` | ID StepExecution chứa JobStep. |
| `child_job_name` | Tên job con. |
| `child_execution_id` | ID JobExecution của job con. |
| `business_reference` | Mã batch hoặc kỳ nghiệp vụ. |
| `child_status` | Trạng thái gần nhất của child execution. |
| `started_at` / `ended_at` | Thời điểm bắt đầu và kết thúc. |

Bảng này có thể được cập nhật bởi listener hoặc thành phần điều phối. JobRepository vẫn là nguồn metadata chuẩn của Spring Batch; bảng giám sát chỉ bổ sung quan hệ và dữ liệu hiển thị phù hợp với nghiệp vụ.

Khi cập nhật status vào bảng giám sát, nên lưu child execution ID và thời điểm cập nhật. Tránh chỉ lưu một chuỗi status không có định danh execution, vì một child JobInstance có thể có nhiều JobExecution qua các lần restart.

## 17. Các lỗi thường gặp khi theo dõi JobStep

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Parent step báo FAILED nhưng không biết child lỗi ở đâu | Chỉ xem Parent StepExecution, không truy vấn child JobExecution và các step con. | Dùng JobExplorer để đọc child execution và step executions. |
| Không tìm thấy child execution | Không lưu child execution ID hoặc tra cứu sai JobRepository/JobInstance. | Ghi nhận ID liên kết hoặc tra cứu theo child job name và identifying parameters. |
| Child job bị coi là instance mới mỗi lần parent restart | Extractor thêm tham số identifying thay đổi. | Giữ nguyên identifying parameters cho cùng đơn vị xử lý logic. |
| Child job báo đã hoàn tất khi parent restart | Child JobInstance đã `COMPLETED` nhưng parent step chưa ghi nhận kết quả cuối cùng. | Đối chiếu metadata parent/child và xử lý theo trạng thái thực tế; không tự ý xóa metadata. |
| Parent hoàn tất khi child vẫn chạy | Dùng launcher bất đồng bộ mà không có cơ chế chờ/giám sát. | Dùng launcher đồng bộ cho JobStep tiêu chuẩn hoặc xây dựng orchestration bất đồng bộ riêng. |
| Parent báo COMPLETED dù child có skip | Child job hoàn tất theo BatchStatus nhưng có lỗi dữ liệu được skip. | Kiểm tra counters và ExitStatus nghiệp vụ; định nghĩa mã kết quả tùy chỉnh nếu cần. |
| Không restart được child | Child job `preventRestart`, step vượt `startLimit` hoặc trạng thái không cho phép. | Kiểm tra cấu hình restart và metadata của child JobInstance. |
| Parent flow đi sai nhánh | Dùng nhầm BatchStatus và ExitStatus hoặc thiếu transition. | Kiểm tra exit code thực tế của JobStep và cấu hình flow. |
| Không truy vết được quan hệ parent-child | Không truyền parent ID hoặc không có bảng liên kết. | Bổ sung parent reference vào child parameters dạng non-identifying hoặc metadata giám sát riêng. |

## 18. Quy trình vận hành khi child job có vấn đề

Khi JobStep thất bại hoặc màn hình giám sát hiển thị child job bất thường, có thể xử lý theo trình tự:

1. **Xác định parent execution:** lấy JobExecution ID của job cha và step execution tương ứng với JobStep.
2. **Xác định child job:** kiểm tra tên job con và bộ parameters mà extractor tạo ra.
3. **Tra cứu child execution:** dùng JobExplorer hoặc bảng liên kết để lấy đúng child JobExecution ID.
4. **Đọc trạng thái chi tiết:** xem BatchStatus, ExitStatus, thời gian, failure exceptions và StepExecution bên trong child.
5. **Đánh giá dữ liệu nghiệp vụ:** kiểm tra số item đọc/ghi/skip, chunk đã commit và các tác dụng phụ bên ngoài.
6. **Khắc phục nguyên nhân:** sửa dữ liệu đầu vào, khôi phục dịch vụ hoặc giải phóng tài nguyên bị khóa.
7. **Kiểm tra điều kiện restart:** xác nhận child JobInstance, identifying parameters, restart policy và parent JobStep đều cho phép chạy lại.
8. **Restart có kiểm soát:** khởi chạy lại parent hoặc child theo quy trình vận hành đã thiết kế, dùng đúng identity khi muốn tiếp tục cùng đơn vị xử lý.
9. **Theo dõi cả hai cấp:** xác nhận child JobExecution mới hoàn tất và parent StepExecution/JobExecution đã nhận kết quả phù hợp.

Không nên chỉ sửa status trong bảng metadata hoặc xóa child execution để parent có thể chạy tiếp. Hành động đó có thể làm mất lịch sử và khiến framework khởi chạy lại dữ liệu đã được xử lý.

## 19. Những điểm cần ghi nhớ

- `JobStep` khởi chạy một job con như một step trong job cha.
- Child job có `JobInstance`, `JobExecution` và các `StepExecution` riêng; JobStep có `StepExecution` thuộc parent job.
- Cần phân biệt child `BatchStatus`, child `ExitStatus`, parent StepExecution và parent JobExecution.
- `JobParametersExtractor` quyết định tham số nào được truyền cho child job; identifying parameters xác định child JobInstance.
- `JobExplorer` dùng để tra cứu child execution và các step bên trong; `JobOperator` hỗ trợ thao tác vận hành theo API được cấu hình.
- Nếu cần liên kết trực tiếp parent và child execution, hãy ghi nhận child execution ID rõ ràng qua listener, parameters hoặc bảng giám sát.
- Child thất bại thường làm JobStep thất bại; parent flow quyết định nhánh xử lý tiếp theo.
- Child `COMPLETED` không đồng nghĩa mọi item đều được ghi; hãy xem counter và ExitStatus nghiệp vụ.
- JobStep tiêu chuẩn thường nên dùng JobLauncher đồng bộ để chờ kết quả child job.
- Khi restart, dùng đúng identifying parameters của child JobInstance và kiểm tra cả metadata parent lẫn child.

Khi xây dựng màn hình giám sát hoặc quy trình vận hành cho JobStep, hãy lưu ý rằng parent và child là hai execution độc lập có quan hệ điều phối. Theo dõi đúng child JobExecution, trạng thái từng step con và kết quả JobStep ở parent sẽ giúp phát hiện lỗi chính xác, điều khiển flow đúng và restart an toàn.
