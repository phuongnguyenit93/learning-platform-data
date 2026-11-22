# Log JobInstance và JobExecution trong Spring Batch

Khi vận hành Spring Batch, thông báo “Job failed” hoặc “Job completed” thường chưa đủ để xác định **lần xử lý nào** đã xảy ra, có phải một lần restart hay không, bản ghi nào được xử lý và bước nào gặp lỗi. Một hệ thống có thể chạy cùng một Job hàng trăm lần mỗi ngày; nếu log không gắn với danh tính của từng lần thực thi, việc điều tra sự cố trở nên khó khăn.

Trong chủ đề **Monitoring** của **Spring Batch Core Processing**, “Log job instance và execution” là kỹ thuật ghi nhận có cấu trúc thông tin về **JobInstance** và **JobExecution** ở những điểm quan trọng trong vòng đời Job. Mục tiêu là truy vết được một lần chạy từ lúc yêu cầu được gửi đến khi hoàn tất, đồng thời phân biệt lịch sử của một đơn vị công việc với từng nỗ lực thực thi của nó.

Bài học trình bày mô hình định danh, những trường log nên có, cách dùng `JobExecutionListener`, cách liên kết log Job và Step, lưu ý với launcher bất đồng bộ, thực hành tra cứu bằng `JobExplorer` và kiểm thử nội dung log.

## 1. Hiểu đúng Job, JobInstance và JobExecution

Spring Batch có ba khái niệm liên quan nhưng không đồng nhất:

- **`Job`:** định nghĩa công việc cần thực hiện, ví dụ `dailySettlementJob`.
- **`JobInstance`:** một đơn vị công việc logic, được nhận diện bằng **tên Job** và tập **identifying JobParameters**. Ví dụ Job xử lý ngày nghiệp vụ `2026-11-16`.
- **`JobExecution`:** một lần cố gắng thực thi JobInstance. Nếu lần đầu thất bại và được restart, vẫn là **cùng JobInstance**, nhưng có **JobExecution mới**.

Ví dụ lịch sử:

```text
Job: dailySettlementJob
│
├── JobInstance #51
│   identifying parameters: {businessDate=2026-11-16}
│   ├── JobExecution #2001: FAILED
│   │   ├── StepExecution #3101: loadPaymentsStep     COMPLETED
│   │   └── StepExecution #3102: settlePaymentsStep  FAILED
│   └── JobExecution #2002: COMPLETED (restart)
│       └── StepExecution #3103: settlePaymentsStep  COMPLETED
│
└── JobInstance #52
    identifying parameters: {businessDate=2026-11-17}
    └── JobExecution #2003: COMPLETED
```

Trong ví dụ:

| Trường | Ý nghĩa | Tác dụng khi tìm log |
| --- | --- | --- |
| `jobName` | Tên định nghĩa Job, ví dụ `dailySettlementJob`. | Lọc theo loại công việc. |
| `jobInstanceId` | ID của đơn vị công việc logic. | Nhóm các lần restart liên quan đến cùng dữ liệu nghiệp vụ. |
| `jobExecutionId` | ID của một lần chạy thực tế. | Theo dõi trạng thái, lỗi và thời gian của **đúng một lần chạy**. |
| `stepName` | Tên Step được thực thi. | Khoanh vùng công đoạn xảy ra vấn đề. |
| `stepExecutionId` | ID một lần thực thi Step. | Phân biệt Step ở các lần restart hoặc partition khác nhau. |
| `businessDate`/`windowKey` | Tham số nghiệp vụ **được phép ghi log**. | Liên kết dữ liệu kinh doanh với đơn vị chạy. |

**Không chỉ dùng `jobName` làm khóa tương quan.** Hai `JobExecution` của cùng tên Job có thể đang chạy song song; riêng tên Job không cho biết dòng log thuộc lần nào.

### Identifying JobParameters ảnh hưởng đến JobInstance

Giả sử có hai bộ tham số:

```text
A: dailySettlementJob + businessDate=2026-11-16 + requestId=abc
B: dailySettlementJob + businessDate=2026-11-16 + requestId=xyz
```

Nếu `requestId` được đánh dấu là **identifying**, A và B là hai JobInstance khác nhau. Nếu `requestId` là **non-identifying** và `businessDate` là identifying, chúng hướng đến cùng JobInstance.

Vì thế, log nên có cả ID thực tế do `JobRepository` cấp và một business key an toàn (ví dụ ngày xử lý). Không nên cố tái dựng JobInstance từ một chuỗi các tham số bất kỳ rồi xem đó là ID duy nhất.

## 2. Những sự kiện cần ghi log trong vòng đời Job

Một chuỗi sự kiện dễ theo dõi:

```text
Scheduler / API / Message consumer
  │
  ├─ batch.job.launch.requested    (yêu cầu chạy Job)
  │
  ├─ batch.job.launch.accepted     (JobRepository tạo JobExecution)
  │   │
  │   ├─ batch.job.started         (Job bắt đầu thực thi)
  │   │
  │   ├─ batch.step.started        (Step bắt đầu)
  │   ├─ batch.step.finished       (Step kết thúc)
  │   │
  │   └─ batch.job.finished        (Job kết thúc)
  │
  └─ batch.job.launch.rejected     (không tạo được lần chạy)
```

Không phải mọi Job đều phát sinh toàn bộ sự kiện. Ví dụ `JobExecutionAlreadyRunningException` có thể xảy ra **trước khi một JobExecution mới được tạo**. Trong trường hợp này có sự kiện `launch.rejected` nhưng không có `jobExecutionId` mới để ghi.

| Sự kiện | Điểm phát log phù hợp | Các trường nên có |
| --- | --- | --- |
| Yêu cầu chạy | Lớp scheduler hoặc service gọi launcher/operator | `jobName`, `trigger`, `requestId`, tham số nghiệp vụ được cho phép |
| Được chấp nhận | Ngay sau lời gọi launch trả về | `jobInstanceId`, `jobExecutionId`, trạng thái ban đầu |
| Bắt đầu Job | `JobExecutionListener.beforeJob` | ID instance/execution, `jobName`, mốc bắt đầu |
| Bắt đầu/kết thúc Step | `StepExecutionListener` hoặc lớp quan sát tương đương | ID execution, `stepName`, số bản ghi |
| Kết thúc Job | `JobExecutionListener.afterJob` | `BatchStatus`, `ExitStatus`, thời gian và số lỗi |
| Bị từ chối/lỗi khởi chạy | `catch` ở scheduler/service | Loại ngoại lệ, tên Job, request ID; thông tin không nhạy cảm |

Tách **accepted** và **finished** rất quan trọng khi launcher bất đồng bộ: việc gọi được `run(...)` không có nghĩa Job đã thành công.

## 3. Những trường log cần thiết và mức log

Một sự kiện kết thúc Job nên đủ để trả lời: Job gì, instance nào, execution nào, kết thúc như thế nào và mất bao lâu?

```text
INFO  batch.job.finished
      jobName=dailySettlementJob
      jobInstanceId=51
      jobExecutionId=2002
      status=COMPLETED
      exitCode=COMPLETED
      durationMs=4280
```

Đây là ví dụ minh họa về cấu trúc trường, không phải yêu cầu một định dạng log cụ thể. Các thông số giả định như ID và thời lượng chỉ dùng để diễn giải.

Nên quy ước:

| Trường | Nội dung | Gợi ý |
| --- | --- | --- |
| `event` | `batch.job.started`, `batch.job.finished`, ... | Tên ổn định giữa các phiên bản code. |
| `jobName` | Tên Job. | Giữ nguyên tên được định nghĩa trong Spring Batch. |
| `jobInstanceId` | ID từ `JobInstance`. | Sử dụng để nối những lần restart. |
| `jobExecutionId` | ID từ `JobExecution`. | Sử dụng để mở metadata của đúng execution. |
| `batchStatus` | `COMPLETED`, `FAILED`, `STOPPED`, ... | Phản ánh trạng thái thực thi. |
| `exitCode` | Mã kết thúc của `ExitStatus`. | Có thể là mã tùy chỉnh của ứng dụng. |
| `durationMs` | Thời gian giữa mốc bắt đầu và kết thúc. | Chỉ tính khi có đủ timestamp hợp lệ. |
| `failureCount` | Số ngoại lệ thu thập được. | Hữu ích cho chẩn đoán; không phải số bản ghi bị skip. |
| `trigger` | `scheduler`, `manual`, `api`, `retry`,... | Xác định nguồn kích hoạt nếu hệ thống có nhiều đường chạy. |
| `businessDate` | Ngày/cửa sổ dữ liệu đã được duyệt cho phép log. | Không ghi các tham số chứa dữ liệu riêng tư hoặc bí mật. |
| `traceId`/`requestId` | ID tương quan với hệ thống gọi. | Giúp nối log ở cấp ứng dụng và dịch vụ ngoài. |

**Mức log khuyến nghị:**

- `INFO` cho những chuyển trạng thái Job/Step quan trọng và kết quả kết thúc thông thường.
- `WARN` cho kết quả bất thường có thể xử lý, ví dụ Job `STOPPED` có chủ đích, trigger bị bỏ qua hoặc số lượng skip vượt ngưỡng cảnh báo của nghiệp vụ.
- `ERROR` khi Job thất bại hoặc xảy ra lỗi khởi chạy nghiêm trọng; phân biệt lỗi thật với từ chối hợp lệ như Job đang chạy.
- `DEBUG` cho tham số đã lọc an toàn, quyết định phân nhánh và các chi tiết phục vụ điều tra.
- `TRACE` cho thông tin cực chi tiết chỉ khi cần, có kiểm soát dung lượng và bảo mật.

Nếu một Job chạy hàng triệu bản ghi, **không ghi một log INFO cho từng item**. Log theo ranh giới Job/Step/chunk hoặc ghi số liệu tổng hợp; việc phát log trên từng bản ghi có thể biến logging thành nút thắt của pipeline.

## 4. Ghi log tự động bằng `JobExecutionListener`

`JobExecutionListener` là điểm mở rộng thích hợp để phát log thống nhất cho mọi lần chạy của Job. Nó có hai callback chính:

- `beforeJob(JobExecution execution)`: gọi trước khi Job thực thi các bước.
- `afterJob(JobExecution execution)`: gọi sau quá trình thực thi Job và có trạng thái kết thúc, thích hợp ghi kết quả.

Ví dụ dưới đây dùng **Spring Batch 5.x**, **Spring Boot 3.x** và **SLF4J**. Ở Spring Batch 6.x, một số kiểu dữ liệu được chuyển sang package con; nội dung log và ý nghĩa callback không thay đổi.

```java
package example.batch.monitoring;

import java.time.Duration;
import java.time.LocalDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.stereotype.Component;

@Component
public class BatchExecutionLoggingListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchExecutionLoggingListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        log.info(
            "batch.job.started jobName={} jobInstanceId={} "
                + "jobExecutionId={} batchStatus={} businessDate={}",
            execution.getJobInstance().getJobName(),
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            execution.getStatus(),
            execution.getJobParameters().getString("businessDate")
        );
    }

    @Override
    public void afterJob(JobExecution execution) {
        Long durationMs = elapsedMillis(
                execution.getStartTime(),
                execution.getEndTime()
        );

        log.info(
            "batch.job.finished jobName={} jobInstanceId={} "
                + "jobExecutionId={} batchStatus={} exitCode={} "
                + "durationMs={} failureCount={}",
            execution.getJobInstance().getJobName(),
            execution.getJobInstance().getInstanceId(),
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus().getExitCode(),
            durationMs,
            execution.getAllFailureExceptions().size()
        );

        for (StepExecution step : execution.getStepExecutions()) {
            log.info(
                "batch.step.finished jobExecutionId={} "
                    + "stepExecutionId={} stepName={} batchStatus={} "
                    + "readCount={} writeCount={} skipCount={} "
                    + "commitCount={} rollbackCount={}",
                execution.getId(),
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount()
            );
        }

        if (execution.getStatus() == BatchStatus.FAILED) {
            execution.getAllFailureExceptions().stream()
                    .findFirst()
                    .ifPresent(error -> log.error(
                        "batch.job.failure jobExecutionId={} "
                            + "exceptionType={}",
                        execution.getId(),
                        error.getClass().getName()
                    ));
        }
    }

    private static Long elapsedMillis(
            LocalDateTime started, LocalDateTime ended) {
        if (started == null || ended == null) {
            return null;
        }
        return Duration.between(started, ended).toMillis();
    }
}
```

Trong mã trên:

1. `jobInstanceId` giúp tìm tất cả lần chạy thuộc cùng một đơn vị công việc.
2. `jobExecutionId` giúp nối log của từng Step vào đúng lần chạy.
3. `batchStatus` là enum trạng thái của Spring Batch.
4. `exitCode` lấy từ `ExitStatus`, có thể khác với `batchStatus` nếu ứng dụng cấu hình kết quả tùy chỉnh.
5. `businessDate` là **trường cho phép ghi log** đã được xác định trước; không dump toàn bộ `JobParameters`.
6. `durationMs` chỉ được tính nếu cả hai timestamp hiện hữu. Nếu callback hoặc cơ chế ghi metadata của phiên bản chưa cung cấp `endTime` tại thời điểm đó, trường có thể bằng `null`; không nên tự suy đoán.
7. `failureCount` cho biết số ngoại lệ được ghi nhận, không phản ánh trực tiếp số item đã retry/skip.
8. Lỗi mặc định chỉ ghi **tên loại ngoại lệ**; việc log message/stack trace phải xét quy tắc bảo mật vì ngoại lệ có thể chứa dữ liệu đầu vào.

Để đăng ký listener vào Job được tạo bằng Java configuration:

```java
@Bean
Job dailySettlementJob(
        JobRepository jobRepository,
        Step settlementStep,
        BatchExecutionLoggingListener loggingListener) {

    return new JobBuilder("dailySettlementJob", jobRepository)
            .listener(loggingListener)
            .start(settlementStep)
            .build();
}
```

Các kiểu `Job`, `Step`, `JobBuilder`, `JobRepository` được import theo phiên bản Spring Batch hiện tại. Đoạn mã giả định `settlementStep` là bean Step đã được cấu hình đầy đủ trong ứng dụng.

**Đăng ký listener ở cấu hình Job**, không chỉ khai báo `@Component`: bean được Spring tạo ra nhưng chưa được gắn vào Job thì callback sẽ không chạy. Nếu nhiều Job cùng dùng chung listener không có state mutable, đây là lựa chọn giúp format log nhất quán.

### Vì sao không chỉ log trong scheduler?

Scheduler biết **ai yêu cầu chạy**, nhưng không nhất thiết biết **Job kết thúc khi nào**, nhất là với launcher bất đồng bộ. Listener chạy trong vòng đời Job và có thể đọc thông tin của execution đang thực thi. Hai nơi log bổ sung nhau:

- Scheduler/service: log nguồn kích hoạt và các lỗi **trước khi Job được chấp nhận**.
- Listener: log kết quả **của JobExecution đã được tạo**.

Một Job có thể được chạy qua REST API, cron, message consumer hoặc thao tác thủ công; listener đặt ở Job giúp không bỏ sót các đường khởi chạy hợp lệ.

## 5. Ghi nhận yêu cầu khởi chạy và lỗi chưa tạo JobExecution

Một số lỗi xảy ra ngay lúc gọi launcher: Job đã chạy, instance đã hoàn thành, tham số không hợp lệ hoặc repository gặp sự cố. Khi đó, `afterJob` không phải nơi duy nhất để quan sát lỗi.

Ví dụ cho Spring Batch 5.x:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

public final class BatchLaunchService {

    private static final Logger log =
            LoggerFactory.getLogger(BatchLaunchService.class);

    private final JobLauncher jobLauncher;
    private final Job job;

    public BatchLaunchService(JobLauncher jobLauncher, Job job) {
        this.jobLauncher = jobLauncher;
        this.job = job;
    }

    public JobExecution launch(JobParameters parameters)
            throws JobExecutionException {
        String businessDate = parameters.getString("businessDate");

        log.info("batch.job.launch.requested jobName={} businessDate={}",
                job.getName(), businessDate);

        try {
            JobExecution execution = jobLauncher.run(job, parameters);

            log.info(
                "batch.job.launch.accepted jobName={} "
                    + "jobInstanceId={} jobExecutionId={} batchStatus={}",
                job.getName(),
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus()
            );
            return execution;

        } catch (JobExecutionException ex) {
            log.warn(
                "batch.job.launch.rejected jobName={} "
                    + "businessDate={} exceptionType={}",
                job.getName(),
                businessDate,
                ex.getClass().getSimpleName()
            );
            throw ex;
        }
    }
}
```

Trong hệ thống thực tế, lớp service có thể nhận thêm `requestId` hoặc `triggerId` được tạo ở nơi nhận yêu cầu. Chỉ cần một ID ổn định cho mỗi yêu cầu là có thể liên kết log `launch.requested` với `launch.accepted` hoặc `launch.rejected`, kể cả khi chưa tồn tại `jobExecutionId`.

Sự kiện `launch.accepted` **không được đặt tên là `job.finished`**. Nếu launcher dùng executor bất đồng bộ, `execution.getStatus()` tại thời điểm trả về có thể vẫn là `STARTING` hoặc `STARTED`. Trạng thái kết thúc phải lấy sau khi công việc thực thi xong.

### Phân loại lỗi khi khởi chạy

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý log |
| --- | --- | --- |
| `JobExecutionAlreadyRunningException` | Cùng JobInstance đang thực thi. | Ghi nhận như trigger trùng hoặc điều kiện điều phối; có thể là WARN/INFO tùy chính sách. |
| `JobInstanceAlreadyCompleteException` | JobInstance đã hoàn thành. | Xác định có phải yêu cầu lặp có chủ đích hay tham số identifying không đúng. |
| `JobParametersInvalidException` | Tham số không đáp ứng ràng buộc. | Ghi loại lỗi và tên tham số an toàn; không ghi giá trị bí mật. |
| `JobRestartException` | Restart không hợp lệ. | Kiểm tra trạng thái trước đó, restartability và metadata. |
| Lỗi datasource/JobRepository | Không thể tạo hoặc lưu execution bình thường. | Phát log ERROR có request/trace ID và điều tra hạ tầng. |

Đừng mặc định mọi `JobExecutionException` đều là lỗi nghiệp vụ của một JobExecution đang chạy. Nhiều trường hợp không có Step nào được thực thi.

## 6. Ghi log StepExecution để giải thích kết quả Job

`JobExecution` phản ánh trạng thái của cả Job; `StepExecution` cho biết Job đã làm gì trong từng bước.

Ví dụ:

```text
INFO  batch.job.started  jobName=importOrdersJob
      jobInstanceId=72 jobExecutionId=810

INFO  batch.step.finished jobExecutionId=810
      stepExecutionId=1801 stepName=readOrders
      batchStatus=COMPLETED readCount=100 writeCount=100 skipCount=0

INFO  batch.step.finished jobExecutionId=810
      stepExecutionId=1802 stepName=writeOrders
      batchStatus=FAILED readCount=60 writeCount=40
      skipCount=0 rollbackCount=1

INFO  batch.job.finished jobName=importOrdersJob
      jobInstanceId=72 jobExecutionId=810
      batchStatus=FAILED exitCode=FAILED
```

Khi đọc log, có thể xác định Step `writeOrders` gặp vấn đề và lần chạy cụ thể là `jobExecutionId=810`. Không thể kết luận rằng 100 bản ghi đã được ghi vào đích chỉ từ trạng thái của Step `readOrders`; số lượng phải được diễn giải theo cấu trúc Job và fixture thực tế.

### Listener riêng cho Step

Nếu muốn log ngay khi một Step bắt đầu/kết thúc, thay vì chờ toàn Job hoàn tất, dùng `StepExecutionListener`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class BatchStepLoggingListener
        implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchStepLoggingListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        log.info(
            "batch.step.started jobExecutionId={} "
                + "stepExecutionId={} stepName={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
            "batch.step.finished jobExecutionId={} "
                + "stepExecutionId={} stepName={} batchStatus={} "
                + "exitCode={} readCount={} writeCount={} skipCount={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getSkipCount()
        );

        // Không thay đổi ExitStatus đã được xác định cho Step.
        return step.getExitStatus();
    }
}
```

Đăng ký listener ở Step khi cấu hình Step builder. Trong một số trường hợp, Spring Batch tự phát sinh log ở các tầng launcher/step; cần xem cấu hình logging để không tạo quá nhiều sự kiện trùng lặp. Không thay đổi `ExitStatus` trong listener chỉ nhằm mục đích log.

### Bộ đếm Step cần hiểu theo nghiệp vụ

| Bộ đếm | Tác dụng quan sát |
| --- | --- |
| `readCount` | Số item đã đọc được theo cơ chế Step. |
| `writeCount` | Số item đã được ghi thành công theo cơ chế Step. |
| `filterCount` | Số item processor lọc bỏ. |
| `readSkipCount` / `processSkipCount` / `writeSkipCount` | Phân loại nơi item bị skip. |
| `skipCount` | Tổng số item bị skip. |
| `commitCount` | Số transaction commit được ghi nhận cho Step. |
| `rollbackCount` | Số lần rollback được ghi nhận. |

Không nên xem `readCount == writeCount` là điều kiện bắt buộc của mọi Job. Nếu processor lọc bản ghi, nếu Step chỉ kiểm tra dữ liệu hoặc nếu Job có skip được cho phép, hai bộ đếm có thể khác nhau mà Job vẫn `COMPLETED`.

## 7. Phân biệt `BatchStatus` và `ExitStatus` trong log

Hai thuộc tính phục vụ mục đích khác nhau:

```java
BatchStatus batchStatus = execution.getStatus();
String exitCode = execution.getExitStatus().getExitCode();
String exitDescription =
        execution.getExitStatus().getExitDescription();
```

- **`BatchStatus`:** trạng thái thực thi, ví dụ `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`.
- **`ExitStatus`:** kết quả kết thúc có `exitCode` và `exitDescription`, có thể được tùy chỉnh bởi flow/listener.

Ví dụ Job có thể có:

```text
batchStatus=COMPLETED
exitCode=COMPLETED_WITH_WARNINGS
```

Điều này có thể đúng theo hợp đồng nghiệp vụ nếu Job hoàn tất với cảnh báo. Log chỉ một trường `status=COMPLETED` sẽ bỏ mất thông tin kết thúc bổ sung; log cả hai giúp giải thích quyết định của luồng Job.

**Không ghi nguyên văn `exitDescription` một cách mặc định** nếu nó có thể chứa stack trace, câu SQL, dữ liệu đầu vào hoặc thông tin khách hàng. Ghi một mã lỗi đã chuẩn hóa vào log chung; đưa mô tả chi tiết sang nơi lưu an toàn phù hợp chính sách.

## 8. Liên kết các lần restart theo JobInstance

Xem lại chuỗi sự kiện:

```text
batch.job.started
  jobName=dailySettlementJob jobInstanceId=51 jobExecutionId=2001

batch.job.finished
  jobName=dailySettlementJob jobInstanceId=51
  jobExecutionId=2001 batchStatus=FAILED

batch.job.started
  jobName=dailySettlementJob jobInstanceId=51 jobExecutionId=2002

batch.job.finished
  jobName=dailySettlementJob jobInstanceId=51
  jobExecutionId=2002 batchStatus=COMPLETED
```

Khi tìm lỗi, trước tiên lọc `jobInstanceId=51` để lấy **tất cả các lần cố gắng**. Sau đó lọc `jobExecutionId=2001` để xem riêng lần thất bại và các Step liên quan.

Một restart bình thường có thể không chạy lại toàn bộ Step đã `COMPLETED` trước đó. Vì vậy, `afterJob` sẽ ghi các StepExecution thực sự thuộc JobExecution đang xét, không nên giả định lần restart có cùng danh sách StepExecution với lần đầu.

### Cách chọn identifying parameters

Ví dụ trong Spring Batch 5.x:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("triggerRequestId", "request-abc", false)
        .toJobParameters();
```

Ở đây `businessDate` được dùng để nhận diện đơn vị công việc; `triggerRequestId` được đánh dấu non-identifying để không tạo JobInstance mới chỉ vì một yêu cầu chạy khác. Điều này chỉ phù hợp nếu nghiệp vụ thật sự định nghĩa một instance cho mỗi ngày xử lý.

Nếu Job chạy một ngày nhiều cửa sổ khác nhau, hãy sử dụng identifying key thể hiện đúng cửa sổ, ví dụ `windowStart`. Không thay đổi identifying parameters tùy tiện khi restart, vì điều đó có thể tạo một JobInstance mới và làm mất ý nghĩa của lịch sử cũ.

## 9. Log trong Job chạy bất đồng bộ và Step đa luồng

### 9.1. JobLauncher bất đồng bộ

Với launcher bất đồng bộ, dòng thời gian có thể như sau:

```text
Thread scheduler                   Thread batch-worker
----------------                   -------------------
launch.requested
JobLauncher.run(...)
launch.accepted status=STARTING
return from scheduled method
                                   beforeJob -> job.started
                                   execute Step...
                                   afterJob -> job.finished
```

Dòng `launch.accepted` là bằng chứng rằng Job đã được chấp nhận để chạy, **không phải bằng chứng Job đã kết thúc**. Nếu cần lấy trạng thái cuối, hãy đọc lại `JobExecution` qua `JobExplorer` hoặc cơ chế giám sát có timeout.

Ví dụ Spring Batch 5.x:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution == null) {
    // Có thể do metadata chưa sẵn sàng hoặc ID không tồn tại.
} else {
    log.info(
        "batch.job.observed jobExecutionId={} batchStatus={} exitCode={}",
        execution.getId(),
        execution.getStatus(),
        execution.getExitStatus().getExitCode()
    );
}
```

Trong hệ thống cần polling, luôn có timeout và tiêu chí trạng thái cuối; không polling vô hạn. Khi Job bị dừng đột ngột, một bản ghi metadata có thể vẫn `STARTED`. Hãy quan sát thời gian cập nhật và hạ tầng worker trước khi kết luận rằng Job chắc chắn còn chạy.

### 9.2. Step đa luồng và `MDC`

SLF4J `MDC` (*Mapped Diagnostic Context*) giúp gắn ID vào các dòng log trong cùng thread:

```java
import org.slf4j.MDC;

try (MDC.MDCCloseable context =
        MDC.putCloseable(
                "jobExecutionId",
                String.valueOf(execution.getId()))) {

    log.info("processing batch chunk");
}
```

Ví dụ pattern Logback có thể đọc MDC:

```text
%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level
jobExecutionId=%X{jobExecutionId:-} [%thread] %logger - %msg%n
```

Tuy nhiên, MDC thường gắn với **thread-local state**. Khi `TaskExecutor` chuyển việc sang worker thread hoặc Step dùng nhiều thread, MDC của thread gọi có thể không tự xuất hiện trong worker.

Có hai cách tiếp cận:

1. **Đặt ID trực tiếp vào tham số log** ở các listener/Step/task: dễ hiểu, không phụ thuộc MDC có được truyền giữa threads hay không.
2. Nếu cần MDC cho mọi log trong worker, dùng `TaskDecorator` hoặc wrapper có kiểm soát để **chụp bối cảnh, đặt bối cảnh trong worker và khôi phục bối cảnh cũ trong `finally`**. Việc này đặc biệt quan trọng khi dùng thread pool vì worker threads được tái sử dụng.

Ví dụ `TaskDecorator` chuyển bối cảnh đã có ở thời điểm submit:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> original = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (original == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(original);
                }
            }
        };
    }
}
```

Gắn decorator này vào `ThreadPoolTaskExecutor` khi cấu hình executor cho những đường xử lý cần truyền MDC. **Decorator chỉ chuyển context đang tồn tại lúc submit**: nếu `jobExecutionId` chưa được đặt vào MDC khi tạo task, decorator không thể tự biết ID đó. Phần log tại listener có thể gắn ID trực tiếp để vẫn tra cứu được.

Ngoài ra, không dùng `MDC.put(...)` mà quên `MDC.remove(...)`/`MDC.clear()` khi kết thúc scope. Thread pool có thể tái sử dụng worker cho Job khác, dẫn đến log bị gắn nhầm ID của lần chạy trước.

### 9.3. Partitioning và remote workers

Ở partitioning hoặc remote chunking, một JobExecution có thể kích hoạt nhiều StepExecution hoặc tiến trình ở các worker khác nhau. Hãy truyền **ID tương quan ở mức công việc** thông qua message/header hoặc metadata an toàn; log worker bằng `jobExecutionId`, `stepExecutionId`, `partitionId` và ID nghiệp vụ khi phù hợp.

Không nên chỉ dựa vào tên thread hoặc hostname, vì cùng một JobExecution có thể xuất hiện trên nhiều thread hoặc máy, còn tên thread có thể được tái sử dụng qua nhiều lần chạy.

## 10. Truy vấn lịch sử bằng `JobExplorer` và JobRepository

**Log phục vụ quan sát; metadata Spring Batch là nguồn dữ liệu về trạng thái và lịch sử execution.** Trong những tình huống log bị mất do hệ thống thu thập log lỗi hoặc process bị kill, cần đối chiếu với `JobRepository`.

`JobExplorer` cung cấp giao diện đọc metadata. Ví dụ:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchHistoryReader {

    private final JobExplorer jobExplorer;

    public BatchHistoryReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(Long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Sau khi lấy JobExecution, có thể truy cập:

```java
JobExecution execution = reader.findExecution(2001L);

if (execution != null) {
    String jobName = execution.getJobInstance().getJobName();
    Long instanceId = execution.getJobInstance().getInstanceId();
    Long executionId = execution.getId();
    BatchStatus status = execution.getStatus();

    // Dùng các ID và status để đối chiếu với log tập trung.
}
```

Cũng có thể lấy các instance gần đây theo tên Job, sau đó lấy những execution thuộc từng instance:

```java
jobExplorer.getJobInstances("dailySettlementJob", 0, 20)
        .forEach(instance -> {
            jobExplorer.getJobExecutions(instance)
                    .forEach(execution -> log.info(
                        "batch.job.history jobName={} "
                            + "jobInstanceId={} jobExecutionId={} status={}",
                        instance.getJobName(),
                        instance.getInstanceId(),
                        execution.getId(),
                        execution.getStatus()
                    ));
        });
```

Đoạn mã trên là thao tác **đọc lịch sử** phục vụ công cụ quản trị hoặc tác vụ giám sát theo nhu cầu. Không nên chạy toàn bộ truy vấn lịch sử trong từng lần xử lý item; việc đọc metadata liên tục sẽ tạo tải không cần thiết lên database.

### SQL đối chiếu metadata

Với schema quan hệ mặc định, có thể tìm JobInstance của một execution qua hai bảng metadata:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID = :execution_id;
```

Tên bảng có thể được đổi bằng `tablePrefix`; nội dung schema có thể khác theo hệ quản trị cơ sở dữ liệu và phiên bản Spring Batch. Thao tác SQL này thích hợp để điều tra, **không phải lệnh cập nhật trạng thái Job**. Không tự sửa các bản ghi metadata để làm cho log “trông đúng”.

## 11. Phân biệt log, metrics và tracing

Ba tín hiệu quan sát thường được dùng cùng nhau:

| Tín hiệu | Trả lời câu hỏi | Cách dùng ID |
| --- | --- | --- |
| **Logs** | Điều gì đã diễn ra với một execution cụ thể? | Gắn `jobInstanceId`, `jobExecutionId`, `stepExecutionId`. |
| **Metrics** | Tỷ lệ lỗi, thời gian chạy và throughput đang thay đổi ra sao? | Tag thấp cardinality: tên Job/Step, status. |
| **Traces** | Tác vụ đi qua các thành phần/dịch vụ nào? | Trace/span ID nối các operation khi tracing được cấu hình. |

`jobExecutionId` là khóa tra cứu rất hữu ích trong log nhưng **không nên dùng làm tag metric**: mỗi lần chạy tạo một giá trị mới, gây cardinality lớn trong hệ thống time-series. Tương tự, không biến file path, user ID hay transaction ID thành nhãn metric.

Spring Batch có các điểm tích hợp quan sát và metric tùy phiên bản và cấu hình Micrometer. Khi ứng dụng đã bật metric tự động, log thủ công vẫn có ích cho việc nối từng execution, nhưng tránh tạo hai bộ metric cùng ý nghĩa hoặc vô tình ghi hai lần mỗi sự kiện.

## 12. Không để log làm lộ dữ liệu và không để logging phá hỏng Job

Một `JobParameters` có thể chứa tên file, đường dẫn trên máy, customer ID, token hoặc chuỗi kết nối. `ExecutionContext` có thể lưu checkpoint và dữ liệu trung gian nhạy cảm. Do đó:

- **Chỉ log các tham số trong danh sách cho phép** như `businessDate` hoặc mã phân vùng đã được phân loại an toàn.
- Không ghi nguyên `execution.getJobParameters()`, toàn bộ `ExecutionContext` hay nội dung item vào log INFO.
- Không tự động log giá trị access token, mật khẩu, header xác thực, thông tin tài khoản, email khách hàng hoặc nội dung bản ghi.
- Nếu cần log lỗi kỹ thuật đầy đủ, áp dụng chính sách phân quyền, lưu giữ và che giấu thông tin trước khi gửi đến log sink.
- Cân nhắc độ dài của `exitDescription` và message ngoại lệ trước khi log, vì chúng có thể chứa dữ liệu chưa được làm sạch.
- Dùng formatter có placeholder `{}` của SLF4J để tránh nối chuỗi tốn chi phí khi mức log bị tắt.

Trong listener, hạn chế thao tác nặng và các lệnh gọi mạng đồng bộ. Logging là chức năng quan sát, không nên làm thay đổi trạng thái nghiệp vụ hoặc tạo thêm một điểm lỗi cho Job. Nếu log sink gặp sự cố, cần cơ chế thu thập phù hợp và giám sát riêng; không đặt giả định rằng mọi dòng log đều được ghi bền vững trước khi Job kết thúc.

## 13. Kiểm thử log của JobInstance và JobExecution

Ngoài việc kiểm tra trạng thái Job, có thể kiểm tra rằng listener ghi đủ ID tương quan. Spring Boot cung cấp `OutputCaptureExtension` để bắt nội dung log trong một bài test tích hợp.

Ví dụ Spring Batch 5.x / Spring Boot 3.x:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ExtendWith(OutputCaptureExtension.class)
class BatchExecutionLoggingIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("dailySettlementJob")
    private Job dailySettlementJob;

    @Test
    void shouldLogBothInstanceAndExecutionId(CapturedOutput output)
            throws Exception {

        jobLauncherTestUtils.setJob(dailySettlementJob);

        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        assertThat(output.getOut())
                .contains("batch.job.started")
                .contains("batch.job.finished")
                .contains("jobExecutionId=" + execution.getId())
                .contains("jobInstanceId="
                        + execution.getJobInstance().getInstanceId());
    }
}
```

Giả định để bài test có ý nghĩa:

1. `dailySettlementJob` được đăng ký với `BatchExecutionLoggingListener` ở mục 4.
2. Job có fixture hợp lệ để hoàn tất thành công; đoạn test không tự tạo dữ liệu cho Job.
3. Logger của listener có mức `INFO` hoặc thấp hơn và ghi ra appender mà `OutputCaptureExtension` có thể bắt.
4. Job được chạy đồng bộ trong bài test; nếu chạy bất đồng bộ thì cần chờ Job kết thúc trước khi assert log.
5. `JobRepository` và dữ liệu nghiệp vụ của bài test được cô lập để không ảnh hưởng những test khác.

Không nên assert **toàn bộ chuỗi log** gồm timestamp, thread name, duration, vị trí logger hoặc thứ tự giữa những tác vụ song song. Những phần đó dễ thay đổi theo môi trường. Tập trung kiểm tra **event name** và **ID được ghi đúng**.

### Test thất bại và restart

Một bộ test log cho kịch bản có lỗi có thể:

1. Khởi chạy Job bằng input cố ý khiến một Step thất bại.
2. Assert `JobExecution.status == FAILED`.
3. Assert log có `batch.job.finished`, `batchStatus=FAILED`, `jobExecutionId` và loại lỗi phù hợp.
4. Sửa điều kiện gây lỗi; restart bằng **cùng identifying parameters**.
5. Assert lần restart có `jobInstanceId` bằng lần đầu, nhưng `jobExecutionId` khác.
6. Kiểm tra log có hai sự kiện kết thúc riêng để truy vết từng execution.

Đối với test restart, **không dọn metadata giữa lần lỗi và lần restart**. Chỉ dọn sau khi kiểm tra xong, bằng công cụ dành cho `JobRepository` test.

## 14. Những lỗi ghi log thường gặp

### Chỉ ghi tên Job

```text
INFO importOrdersJob completed
```

Dòng log không cho biết lần chạy nào, dữ liệu ngày nào hoặc có phải restart không. Bổ sung `jobInstanceId`, `jobExecutionId` và business key an toàn.

### Dùng nhầm JobInstance ID làm JobExecution ID

Một JobInstance có thể có nhiều JobExecution. Nếu gắn `jobInstanceId` vào trường `jobExecutionId`, người vận hành sẽ không phân biệt được lần thất bại và lần restart. Cần dùng đúng getter từ `JobExecution` và `JobInstance`.

### Cho rằng `JobLauncher.run(...)` trả về là Job đã hoàn thành

Với executor bất đồng bộ, trả về chỉ có thể nghĩa là Job được chấp nhận. Log `launch.accepted` và dựa vào listener/JobExplorer để biết kết quả cuối.

### Ghi mọi `JobParameters` và `ExecutionContext`

Điều này tạo rủi ro lộ thông tin và log quá lớn. Ghi whitelist những trường đã phân loại an toàn. Nếu cần debug checkpoint, dùng công cụ quản trị có kiểm soát.

### Chỉ nhìn `BatchStatus` mà bỏ qua `ExitStatus`

Ứng dụng có thể dùng exit code tùy chỉnh như `COMPLETED_WITH_WARNINGS`. Log cả status và exit code để hiểu đúng kết quả được công bố.

### Ghi log INFO cho từng item

Trong xử lý khối lượng lớn, việc log từng dòng có thể làm tăng latency, chi phí lưu trữ và khó tìm sự kiện quan trọng. Dùng log theo Job/Step và metric cho throughput.

### MDC bị gắn nhầm sau khi thread pool tái sử dụng thread

Nếu không dọn MDC trong `finally`, log của Job mới có thể mang ID Job cũ. Cần scope và khôi phục context rõ ràng.

### Kết luận Job đã dừng chỉ vì không còn log mới

Khi process chết hoặc log sink gián đoạn, metadata có thể chưa phản ánh trạng thái kết thúc. Đối chiếu `JobExplorer`, trạng thái process, thời gian cập nhật và hệ thống giám sát trước khi quyết định restart hoặc can thiệp metadata.

## 15. Bài tập thực hành

Xây dựng Job `importInventoryJob` chạy theo lịch mỗi giờ để đồng bộ tồn kho. Khi gặp lỗi database tạm thời, Job có thể được restart sau khi khắc phục nguyên nhân.

**Yêu cầu thực hành:**

1. Định nghĩa identifying parameter `windowStart` cho mỗi cửa sổ giờ. Đảm bảo hai yêu cầu cho cùng cửa sổ nhận cùng JobInstance khi các identifying parameters khác không đổi.
2. Viết `JobExecutionListener` ghi sự kiện `batch.job.started` và `batch.job.finished` với `jobName`, `jobInstanceId`, `jobExecutionId`, `batchStatus` và `exitCode`.
3. Viết `StepExecutionListener` ghi số lượng item đọc, ghi, lọc và skip ở mỗi Step, kèm ID execution.
4. Thêm log `launch.requested`/`launch.accepted`/`launch.rejected` ở lớp điều phối.
5. Tạo fixture khiến Job chạy thất bại lần đầu rồi restart thành công. Truy vấn log theo `jobInstanceId` để thấy **hai `jobExecutionId` khác nhau**.
6. Tạo một test sử dụng `OutputCaptureExtension` để xác nhận cả ID instance và execution xuất hiện trong log.
7. Chạy thử với launcher bất đồng bộ; xác nhận log `launch.accepted` có thể đến trước log `job.finished`.
8. Xem lại danh sách trường log và loại bỏ toàn bộ thông tin riêng tư, bí mật hoặc giá trị không được phép ghi log.

Một ví dụ kết quả mong đợi:

```text
INFO batch.job.launch.requested jobName=importInventoryJob windowStart=10:00
INFO batch.job.started jobName=importInventoryJob jobInstanceId=100 jobExecutionId=800
ERROR batch.job.failure jobExecutionId=800 exceptionType=...
INFO batch.job.finished jobName=importInventoryJob jobInstanceId=100 jobExecutionId=800 batchStatus=FAILED
INFO batch.job.started jobName=importInventoryJob jobInstanceId=100 jobExecutionId=801
INFO batch.job.finished jobName=importInventoryJob jobInstanceId=100 jobExecutionId=801 batchStatus=COMPLETED
```

Nếu tìm theo `jobInstanceId=100`, bạn thấy toàn bộ lịch sử của cửa sổ cần xử lý. Nếu tìm theo `jobExecutionId=800`, bạn chỉ thấy lần gặp lỗi. Hai khóa truy vết này bổ sung nhau và giúp monitoring Spring Batch rõ ràng khi Job có retry, restart hoặc chạy song song.

## Tài liệu tham khảo

- [Spring Batch Reference – Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): quan hệ `Job`, `JobInstance`, `JobExecution` và `StepExecution`.
- [Spring Batch Reference – Intercepting Job Execution](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): trạng thái metadata, callback và lịch sử Job.
- [Spring Batch Reference – Job and Step Listeners](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): listener tại Job/Step và thao tác trước/sau thực thi.
- [Spring Batch Reference – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng metadata lưu lịch sử thực thi.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): quan sát batch qua metrics và tracing.
- [Spring Boot Reference – Test Utilities](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): kiểm thử ứng dụng và công cụ hỗ trợ capture output.

