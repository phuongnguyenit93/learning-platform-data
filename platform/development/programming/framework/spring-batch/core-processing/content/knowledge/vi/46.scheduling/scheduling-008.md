# Job completion signal trong Spring Batch

## 1. Job completion signal là gì?

Khi một job Spring Batch được kích hoạt bằng cron, API hoặc hệ thống lập lịch, có hai thời điểm hoàn toàn khác nhau:

1. **Job đã được khởi chạy**: `JobLauncher` đã nhận yêu cầu và một `JobExecution` đã được tạo.
2. **Job đã kết thúc**: `JobExecution` đã đạt trạng thái cuối cùng, kết quả xử lý và metadata cần thiết đã có thể quan sát.

**Job completion signal** là thông tin gửi cho hệ thống khác hoặc cho thành phần điều phối biết rằng **một lượt chạy cụ thể (`JobExecution`) đã kết thúc**, kèm kết quả của lượt chạy ấy. Đây là khái niệm tích hợp/thiết kế; Spring Batch cung cấp lifecycle callback và metadata để triển khai, chứ không tự động bảo đảm một message hoàn tất đã được giao tới mọi hệ thống bên ngoài.

Ví dụ: job `dailySettlement` được scheduler chạy lúc 01:00 để đối soát giao dịch của ngày hôm trước. Sau khi hoàn tất, hệ thống cần:

- Nếu thành công: cho phép gửi báo cáo, mở bước phân phối dữ liệu hoặc kích hoạt job downstream.
- Nếu thất bại: phát cảnh báo, giữ dữ liệu đầu ra chưa được xác nhận và chờ xử lý/restart.
- Nếu bị dừng: báo trạng thái tạm dừng, không tự coi là thành công.
- Với mọi kết quả: lưu `jobExecutionId` để người vận hành tra cứu.

Một tín hiệu tốt phải xác định rõ **job nào, execution nào, ngày nghiệp vụ nào, trạng thái gì và được phát hiện bằng cơ chế nào**.

### Phân biệt các loại tín hiệu

| Tín hiệu | Được tạo khi nào? | Có chứng minh job đã chạy xong? |
|---|---|---|
| Scheduler trigger | Cron hoặc bộ điều phối đến thời điểm chạy | **Không** |
| Job launch accepted | `JobLauncher.run(...)` đã tạo/trả `JobExecution` | **Không nhất thiết**; launcher có thể chạy bất đồng bộ |
| Step completed | Một `StepExecution` đã kết thúc | **Không**; job có thể còn step khác |
| `JobExecutionListener.afterJob` | Framework đi tới pha kết thúc job | Có, theo trạng thái `JobExecution` hiện tại; callback cục bộ không bảo đảm message đã tới nơi nhận |
| JobRepository terminal status | `JobExplorer` thấy `COMPLETED`, `FAILED` hoặc `STOPPED` | Có cho execution đó, với giới hạn độ mới dữ liệu metadata |
| Durable completion event | Bản ghi sự kiện đã được lưu bền vững và được chuyển tới consumer | Có thể dùng để điều phối nếu kèm định danh, trạng thái và cơ chế xử lý trùng/mất |

Một job kết thúc với trạng thái `FAILED` **vẫn là “đã kết thúc”**, nhưng **không phải “hoàn tất thành công”**. Hãy đặt tên tín hiệu rõ ràng: `JobFinished` cho mọi kết quả cuối, `JobSucceeded` chỉ khi thực sự `COMPLETED`.

## 2. Đối tượng nào xác nhận completion?

Trong Spring Batch, `JobExecution` đại diện cho **một lần thực thi** của `JobInstance`. Nó chứa trạng thái, tham số và thông tin lỗi. Các thuộc tính thường dùng:

| Thuộc tính | Mục đích |
|---|---|
| `JobExecution.getId()` | ID kỹ thuật duy nhất cho lượt chạy; dùng tra cứu và idempotency |
| `getJobInstance().getJobName()` | Tên job, ví dụ `dailySettlement` |
| `getJobParameters()` | Tham số như `businessDate=2025-05-12` |
| `getStatus()` | `BatchStatus` thực thi |
| `getExitStatus().getExitCode()` | Mã kết thúc, có thể tùy biến |
| `getStartTime()` / `getEndTime()` | Mốc khởi đầu và kết thúc do framework ghi nhận |
| `getAllFailureExceptions()` | Thông tin nguyên nhân lỗi, phục vụ log/quan sát |

**`BatchStatus` và `ExitStatus` khác nhau**:

- `BatchStatus` biểu diễn trạng thái thực thi mà framework quản lý: `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `COMPLETED`, `FAILED`, `ABANDONED`, `UNKNOWN`.
- `ExitStatus` là mã kết thúc có thể được điều chỉnh theo yêu cầu nghiệp vụ, ví dụ `COMPLETED_WITH_WARNINGS`. Mã này đặc biệt hữu ích khi điều khiển step flow.
- Nếu downstream yêu cầu job **thành công về mặt kỹ thuật**, trước hết kiểm tra `BatchStatus.COMPLETED`. Nếu downstream cần phân biệt “có cảnh báo” hay “không có dữ liệu”, xem thêm exit code hoặc số liệu nghiệp vụ.

Ví dụ:

```text
JobExecution id=501
  jobName      = dailySettlement
  businessDate = 2025-05-12
  BatchStatus  = COMPLETED
  ExitStatus   = COMPLETED_WITH_WARNINGS
```

Execution này đã thành công về mặt BatchStatus, nhưng ứng dụng có thể chọn **không phát tín hiệu sẵn sàng xuất báo cáo** khi exit code báo cảnh báo nghiêm trọng. Điều kiện phát tín hiệu phải được quy định theo hợp đồng nghiệp vụ, không suy đoán chỉ dựa trên tên callback.

### Trạng thái cuối và trạng thái đang chạy

```text
STARTING ──────> STARTED ──────> COMPLETED
                    │
                    ├──────────> FAILED
                    │
                    └──> STOPPING ───> STOPPED
```

Sơ đồ chỉ minh họa một số đường đi thường gặp; thực tế có ngoại lệ, ví dụ job dừng/khởi động thất bại hoặc metadata cũ sau khi process chết. Đối với hệ thống phát tín hiệu, `STARTING`, `STARTED` và `STOPPING` **chưa là completion**.

Một consumer có thể nhận sự kiện loại:

- `COMPLETED`: kết quả cuối của execution thành công.
- `FAILED`: execution kết thúc không thành công, thường có thông tin lỗi.
- `STOPPED`: execution đã dừng theo yêu cầu hoặc flow.
- `ABANDONED`: execution được đánh dấu bỏ, thường do thao tác quản trị; cần phân biệt với một kết thúc tự nhiên.
- `UNKNOWN`: không xác định được kết quả đáng tin cậy; không phát “success”.

Nếu mục tiêu là chạy bước tiếp theo **chỉ khi thành công**, không phát tín hiệu “ready” cho `STOPPED`, `FAILED` hay `UNKNOWN`.

## 3. Completion signal trong ngữ cảnh Scheduling

Một Spring Scheduler có thể được cấu hình:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SettlementSchedule {

    private final SettlementLauncher launcher;

    public SettlementSchedule(SettlementLauncher launcher) {
        this.launcher = launcher;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void startDailySettlement() throws Exception {
        launcher.launchForPreviousBusinessDay();
    }
}
```

Để `@Scheduled` hoạt động, ứng dụng cần bật scheduling, chẳng hạn bằng `@EnableScheduling` ở lớp cấu hình. Đoạn này **chỉ mô tả hành động khởi chạy**; nó không cung cấp điều kiện “job đã thành công”. Thời điểm 01:00 không nói lên lúc job hoàn tất, vì job có thể chạy 5 phút, 3 giờ hoặc thất bại.

### 3.1. Launcher đồng bộ và bất đồng bộ

Với `JobLauncher` sử dụng task executor đồng bộ, phương thức `run(...)` thường chỉ trả về khi luồng xử lý job kết thúc. Lúc ấy, caller có thể xem trạng thái trả về.

Với launcher bất đồng bộ, `run(...)` có thể trả một `JobExecution` **đang chạy**, trong khi công việc tiếp tục trên thread khác.

```text
Scheduler                JobLauncher                Job
    |                         |                       |
    |---- run(params) ------->|                       |
    |                         |----- execute() ------>|
    |<-- JobExecution --------|                       |
    |      (STARTING/STARTED nếu async)               |
    |                                                 |
    |                           ... xử lý dữ liệu ...  |
    |                                                 |
    |                         <---- kết thúc ----------|
```

Vì vậy code sau **không an toàn nếu dùng để suy ra job đã xong trong mọi cấu hình**:

```java
JobExecution execution = jobLauncher.run(job, parameters);
sendSuccessSignal(); // Sai: có thể job vẫn đang chạy hoặc đã FAILED.
```

Thay vào đó, hãy đọc `execution.getStatus()` khi xác định rõ launcher đồng bộ, hoặc dùng `afterJob`/metadata monitoring cho trường hợp bất đồng bộ.

### 3.2. Lấy ngày nghiệp vụ ổn định

Batch chạy lúc 01:00 thường xử lý dữ liệu của ngày trước, nhưng ngày này nên được chốt khi launch và truyền vào `JobParameters`:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;

public final class SettlementLauncher {

    private final JobLauncher jobLauncher;
    private final Job settlementJob;
    private final Clock clock;
    private final ZoneId businessZone;

    public SettlementLauncher(
            JobLauncher jobLauncher,
            Job settlementJob,
            Clock clock,
            ZoneId businessZone) {

        this.jobLauncher = jobLauncher;
        this.settlementJob = settlementJob;
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public JobExecution launchForPreviousBusinessDay() throws Exception {
        LocalDate businessDate = LocalDate.now(
                clock.withZone(businessZone)
        ).minusDays(1);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        return jobLauncher.run(settlementJob, parameters);
    }
}
```

Tham số `businessDate` là identifying parameter nên cùng tên job và cùng ngày nghiệp vụ đại diện cho cùng `JobInstance`. Nếu scheduler kích hoạt lặp trong khi lượt này còn chạy, Spring Batch có thể từ chối chạy trùng; nếu instance đã hoàn tất, có thể gặp `JobInstanceAlreadyCompleteException`. Những trường hợp này phải được xử lý theo chính sách điều phối, **không phát một completion signal mới dựa trên lần gọi launch thất bại**.

## 4. Cách đơn giản: `JobExecutionListener.afterJob`

Spring Batch cung cấp `JobExecutionListener` với hai callback:

- `beforeJob(JobExecution)`: được gọi trước khi job thực thi.
- `afterJob(JobExecution)`: được gọi sau khi job kết thúc **dù thành công hay thất bại**.

Đây là điểm mở rộng phù hợp để ghi audit, cập nhật metric hoặc yêu cầu gửi thông báo completion ở **cùng tiến trình đang chạy job**.

### 4.1. Định nghĩa dữ liệu completion signal

```java
import org.springframework.batch.core.BatchStatus;

public record JobCompletionSignal(
        long jobExecutionId,
        String jobName,
        String businessDate,
        BatchStatus batchStatus,
        String exitCode
) {
    public String idempotencyKey() {
        return jobExecutionId + ":finished";
    }
}
```

Khóa `jobExecutionId + ":finished"` dùng để nhận diện **một sự kiện kết thúc của một execution**. Nếu job `FAILED` và được restart, lượt restart có `jobExecutionId` mới, vì vậy phát một sự kiện riêng. Nếu business rule chỉ cho phép gửi một báo cáo thành công cho mỗi ngày, phía consumer còn cần khóa nghiệp vụ theo `jobName + businessDate`.

### 4.2. Tách transport ra khỏi listener

```java
public interface CompletionSignalSink {
    void publish(JobCompletionSignal signal);
}
```

Interface này có thể được triển khai bằng message broker, HTTP, bảng outbox hoặc hệ thống audit. Bằng cách tách sink, test có thể kiểm tra listener mà không gửi email hay gọi API thật.

### 4.3. Listener phát tín hiệu theo trạng thái cuối

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public final class CompletionSignalListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(CompletionSignalListener.class);

    private final CompletionSignalSink sink;

    public CompletionSignalListener(CompletionSignalSink sink) {
        this.sink = sink;
    }

    @Override
    public void afterJob(JobExecution execution) {
        BatchStatus status = execution.getStatus();

        if (status != BatchStatus.COMPLETED
                && status != BatchStatus.FAILED
                && status != BatchStatus.STOPPED) {
            log.warn(
                    "Job ended with nonstandard status {}, executionId={}",
                    status,
                    execution.getId()
            );
            return;
        }

        JobCompletionSignal signal = new JobCompletionSignal(
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getJobParameters().getString("businessDate"),
                status,
                execution.getExitStatus().getExitCode()
        );

        try {
            sink.publish(signal);
        } catch (RuntimeException ex) {
            // Ghi lỗi để hệ thống quan sát/reconcile xử lý.
            // Không giả định có cơ chế giao message bền vững.
            log.error(
                    "Failed to publish completion signal for executionId={}",
                    execution.getId(),
                    ex
            );
        }
    }
}
```

Ở đây `sink.publish(...)` chỉ minh họa thao tác publish. Nếu sink phụ thuộc network, nên có timeout rõ ràng để callback không bị treo. Việc catch lỗi bảo vệ luồng kết thúc job khỏi một lỗi notification đơn lẻ, nhưng **có thể làm mất tín hiệu** nếu không có cơ chế lưu trữ/reconcile; phần sau sẽ giới thiệu giải pháp tin cậy hơn.

**Không dùng `afterStep` để báo toàn job đã xong.** Một job có nhiều step; sau `afterStep`, step tiếp theo có thể chưa chạy, hoặc một nhánh khác có thể thất bại. Đặt tín hiệu ở `afterJob` khi cần kết quả cuối cấp job.

### 4.4. Đăng ký listener vào Job

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SettlementJobConfiguration {

    @Bean
    CompletionSignalListener completionSignalListener(
            CompletionSignalSink sink) {
        return new CompletionSignalListener(sink);
    }

    @Bean
    Job dailySettlementJob(
            JobRepository repository,
            Step validateTransactions,
            Step aggregateTransactions,
            CompletionSignalListener completionSignalListener) {

        return new JobBuilder("dailySettlement", repository)
                .start(validateTransactions)
                .next(aggregateTransactions)
                .listener(completionSignalListener)
                .build();
    }
}
```

`validateTransactions` và `aggregateTransactions` là các step nghiệp vụ giả định đã được khai báo riêng. Đoạn cấu hình này áp dụng kiểu builder của **Spring Batch 5.2.x**. Nếu quên `.listener(completionSignalListener)`, unit test gọi trực tiếp `afterJob` vẫn xanh nhưng listener sẽ không được framework gọi khi chạy job; cần thêm integration test để phát hiện lỗi đăng ký.

## 5. Chỉ báo thành công hay gửi mọi kết quả cuối?

Hai kiểu contract phổ biến:

| Contract | Tín hiệu phát ra | Consumer phù hợp |
|---|---|---|
| `JobFinished` | `COMPLETED`, `FAILED`, `STOPPED` với status kèm theo | Trang vận hành, audit, cảnh báo, metric |
| `JobSucceeded` / `ReportReady` | Chỉ khi `BatchStatus.COMPLETED` và tiêu chí nghiệp vụ đạt | Job downstream, công bố dữ liệu, gửi báo cáo |

Ví dụ listener chỉ gửi `ReportReady` khi thành công:

```java
@Override
public void afterJob(JobExecution execution) {
    if (execution.getStatus() != BatchStatus.COMPLETED) {
        return;
    }
    if (!"COMPLETED".equals(
            execution.getExitStatus().getExitCode())) {
        // Chính sách ví dụ: chỉ chấp nhận hoàn tất không cảnh báo.
        return;
    }

    String businessDate =
            execution.getJobParameters().getString("businessDate");

    reportReadyPublisher.publish(
            execution.getId(),
            businessDate
    );
}
```

Đây là một **chính sách nghiệp vụ minh họa**, không phải mọi job phải kiểm tra exit code bằng `COMPLETED`. Nếu ứng dụng có exit code `COMPLETED_WITH_SKIPS` nhưng vẫn được phép gửi báo cáo, contract cần định nghĩa rõ.

**Tín hiệu “JobFinished” khác “DataReady”.** Batch có thể hoàn tất theo cấu hình nhưng dữ liệu đầu ra chưa qua kiểm tra tổng, checksum hoặc phê duyệt. Nếu hệ thống downstream cần dữ liệu sẵn sàng thực sự, có thể phát `DataReady` chỉ sau khi hoàn tất bước xác nhận chất lượng, chứ không gắn nó trực tiếp với mọi `COMPLETED`.

## 6. Quan sát completion bằng `JobExplorer`

`JobExecutionListener` là callback trong cùng vòng đời job, nhưng scheduler/điều phối có thể chạy trên tiến trình khác. Khi đó, **`JobExplorer` là một cách đọc metadata từ `JobRepository`** để xem job đã kết thúc hay chưa.

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class JobCompletionReader {

    private final JobExplorer explorer;

    public JobCompletionReader(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public JobExecution findExecution(long executionId) {
        JobExecution execution = explorer.getJobExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId: " + executionId
            );
        }

        return execution;
    }

    public boolean hasFinished(long executionId) {
        BatchStatus status = findExecution(executionId).getStatus();

        return status == BatchStatus.COMPLETED
                || status == BatchStatus.FAILED
                || status == BatchStatus.STOPPED
                || status == BatchStatus.ABANDONED;
    }

    public boolean hasSucceeded(long executionId) {
        return findExecution(executionId).getStatus()
                == BatchStatus.COMPLETED;
    }
}
```

`ABANDONED` ở đây được coi là **kết thúc về mặt xử lý vận hành** cho mục đích ngừng chờ; đây không phải dấu hiệu job thực thi thành công. Một ứng dụng có thể quyết định phát loại event riêng `JobAbandoned`, thay vì gom chung với kết thúc tự nhiên.

### 6.1. Poll theo execution ID thay vì đoán theo giờ

Ví dụ trong hệ thống ngoài:

```text
POST /jobs/dailySettlement/launch
→ 202 Accepted
→ { "jobExecutionId": 501 }

GET /jobs/executions/501
→ { "status": "STARTED" }

GET /jobs/executions/501
→ { "status": "COMPLETED", "exitCode": "COMPLETED" }
```

Các endpoint trên là **ví dụ API tùy biến**, không phải REST API mặc định của Spring Batch. Trên client, nên poll cách quãng với timeout và giới hạn số lần. Khi quá thời gian, hãy trả “chưa có kết quả cuối” hoặc trạng thái cần kiểm tra, không tự đổi thành `FAILED` hay `COMPLETED`.

**Không dùng `Thread.sleep(...)` như bằng chứng job đã hoàn tất.** Một giấc ngủ 5 giây không nói lên trạng thái xử lý. Poll metadata theo điều kiện hoặc dùng event có acknowledgment.

### 6.2. Truy vấn theo ngày nghiệp vụ

Nếu muốn biết “job `dailySettlement` cho `businessDate=2025-05-12` đã xong chưa?”, cần phân biệt:

- `JobInstance` đại diện cho công việc logic theo identifying parameters.
- `JobExecution` là từng lượt chạy/restart của instance đó.
- Một ngày có thể có execution `501=FAILED` và execution `509=COMPLETED` sau restart.

Nếu consumer chỉ quan tâm **kết quả mới nhất**, hãy truy vấn last execution của đúng job instance (chẳng hạn bằng `JobExplorer.getLastJobExecution(jobName, jobParameters)` trên phiên bản hỗ trợ). Nếu cần audit đầy đủ, lưu event cho **từng execution**. Tuyệt đối không lấy ngẫu nhiên một execution đã `COMPLETED` trước đó để suy luận scheduler run mới đã xong.

### 6.3. Khi JobRepository báo STARTED quá lâu

Nếu worker/process chết mà không cập nhật trạng thái, metadata có thể còn `STARTED`. Polling một mình không phân biệt “job rất chậm” với “job đã chết”. Cần kết hợp:

- Thông tin sống/chết của worker hoặc container.
- Log và metrics xử lý gần nhất.
- Thời gian heartbeat hoặc progress checkpoint nếu ứng dụng có.
- Quy trình khôi phục trạng thái cũ có kiểm soát.

Không tự coi một execution `STARTED` từ hôm qua là `COMPLETED` chỉ vì giờ chạy đã qua.

## 7. Một completion signal cần chứa những trường gì?

Trong hệ thống có nhiều scheduler và consumer, nên chuẩn hóa payload:

```json
{
  "eventType": "JobFinished",
  "eventVersion": 1,
  "eventId": "dailySettlement:501:finished",
  "jobName": "dailySettlement",
  "jobInstanceId": 80,
  "jobExecutionId": 501,
  "businessDate": "2025-05-12",
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED",
  "summary": {
    "readCount": 12000,
    "writeCount": 12000,
    "skipCount": 0
  }
}
```

Đây là **payload minh họa**, không phải schema có sẵn của Spring Batch. Một event dùng thực tế còn có thể có `occurredAt` theo UTC, correlation ID, môi trường, phiên bản schema và nơi tra cứu log. Các số liệu `readCount`/`writeCount` có thể được tổng hợp từ các `StepExecution`; cần tránh cộng nhầm nếu flow có nhiều step cùng đọc/ghi một bản ghi.

Các nguyên tắc thực tế:

1. **Định danh execution**: dùng `jobExecutionId` kết hợp job/repository/environment nếu ID có thể trùng giữa các môi trường.
2. **Idempotency**: `eventId` hoặc một khóa xác định để consumer nhận cùng sự kiện nhiều lần vẫn xử lý một lần theo ý nghĩa nghiệp vụ.
3. **Status rõ ràng**: ghi cả `BatchStatus` và `ExitStatus`.
4. **Không mang dữ liệu nhạy cảm**: chỉ đưa tham số được phép xuất hiện trong event; `JobParameters` có thể chứa thông tin bảo mật do ứng dụng cấu hình sai.
5. **Version hóa**: thêm `eventVersion` để consumer đọc được các phiên bản payload lâu dài.
6. **Tra cứu nguồn**: kèm ID để quay lại `JobRepository` khi cần đối chiếu, thay vì tin duy nhất vào một message có thể cũ.

## 8. Vì sao publish trực tiếp trong `afterJob` có thể mất tín hiệu?

Ví dụ đơn giản:

```text
Step cuối cùng kết thúc
       |
       v
JobRepository ghi nhận trạng thái kết thúc
       |
       v
afterJob được gọi
       |
       v
HTTP / message broker publish
       |
       v
Consumer nhận "JobFinished"
```

Giữa các bước có thể xảy ra lỗi:

- Job đã hoàn tất trong database nhưng JVM bị kill trước khi publish.
- Broker/HTTP tạm thời lỗi, listener log exception rồi kết thúc.
- Publisher gửi được message nhưng timeout trước khi nhận ACK; retry gửi lại thành **hai message**.
- Consumer xử lý message thành công rồi crash trước khi xác nhận, khiến broker phát lại.
- Một `JobExecution` được restart, tạo execution mới; hệ thống có thể phát thêm event cho lần mới.

Do đó, `afterJob` phù hợp cho **notification best-effort**, log và metric. Nếu completion signal là điều kiện bắt buộc để hệ thống downstream xử lý dữ liệu hoặc phục vụ quy trình tài chính, cần **cơ chế bền vững và idempotent**.

### 8.1. Một mô hình: reconciliation + outbox

Thay vì phụ thuộc duy nhất vào callback, thiết kế một tiến trình đối soát định kỳ đọc execution đã kết thúc từ `JobRepository`, rồi ghi bản ghi tín hiệu vào bảng outbox. Một publisher riêng nhận tín hiệu từ outbox và giao cho message broker/API downstream.

```text
                 Spring Batch Job
                        |
                        v
                 JobRepository
                        |
        +---------------+---------------+
        |                               |
        v                               v
  afterJob (nhắc nhanh)       Reconciler (quét định kỳ)
        |                               |
        +---------------+---------------+
                        |
                        v
                Outbox table
                  (UNIQUE key)
                        |
                        v
             Publisher / dispatcher
                        |
                        v
               Message broker / API
                        |
                        v
            Idempotent downstream
```

Ưu điểm của reconciler: kể cả `afterJob` không chạy hoặc publish thất bại, một job đã có trạng thái cuối trong `JobRepository` vẫn có thể được phát hiện lại.

Mẫu bảng outbox (SQL định hướng, tùy database):

```sql
CREATE TABLE batch_completion_outbox (
    event_id        VARCHAR(160) PRIMARY KEY,
    job_execution_id BIGINT NOT NULL,
    event_type      VARCHAR(40) NOT NULL,
    payload_json    TEXT NOT NULL,
    delivery_status VARCHAR(20) NOT NULL,
    created_at      TIMESTAMP NOT NULL
);
```

Nên dùng khóa unique thể hiện một event logic, ví dụ `(environment, jobExecutionId, eventType)` nếu triển khai nhiều môi trường vào cùng bảng. Producer ghi `event_id` xác định; khi reconcile lặp lại sẽ bỏ qua bản ghi đã có bằng cơ chế upsert/unique constraint có transaction.

Publisher có thể chuyển trạng thái bản ghi từ `PENDING` sang `DELIVERED` sau khi nhận ACK phù hợp. **Không thể suy luận bảo đảm “exactly once” qua database và broker chỉ vì có outbox**: khi crash sau gửi nhưng trước ACK, message có thể giao lặp. Consumer phải kiểm tra `eventId`/business key theo giao dịch nghiệp vụ.

### 8.2. Phân biệt outbox với ghi thêm trong JobRepository

Outbox là một cơ chế **do ứng dụng thiết kế**, không phải tự động được `spring-batch-core` tạo ra. Việc sửa trực tiếp bảng metadata `BATCH_JOB_EXECUTION` hay thêm cột tùy ý vào schema hạ tầng Spring Batch không phải giải pháp khuyến nghị. Đặt outbox vào schema/bảng nghiệp vụ riêng, có cơ chế giao nhận và dọn dữ liệu cũ rõ ràng.

Nếu có yêu cầu transaction cực chặt giữa trạng thái job và việc tạo event, cần thiết kế ranh giới transaction/đối soát cụ thể. Chỉ viết một dòng vào bảng outbox trong `afterJob` **không tự bảo đảm** atomic commit với tất cả dữ liệu Batch metadata và dữ liệu nghiệp vụ.

## 9. Orchestrate job downstream sau completion

Một use case thường gặp:

```text
00:30 Import job
   |
   | only when COMPLETED + validated
   v
01:00 Aggregation job
   |
   | only when COMPLETED
   v
Publish report
```

Có ba lựa chọn kiến trúc:

| Cách | Phù hợp khi | Ghi chú |
|---|---|---|
| **Một Spring Batch job gồm nhiều step** | Các bước nằm trong một workflow logic cùng Batch infrastructure | Dùng `.next(...)` hoặc conditional flow; ít lớp điều phối bên ngoài |
| **Listener kích hoạt job khác** | Workflow đơn giản, cùng tiến trình, mức tin cậy best-effort chấp nhận được | Cần kiểm soát lỗi, launch lại, trùng lặp và không giữ listener quá lâu |
| **Event/outbox + orchestrator** | Các job độc lập, chạy khác tiến trình/nhóm hoặc cần giao nhận bền vững | Dùng correlation ID, khóa idempotency và quan sát trạng thái |

### 9.1. Khi có thể, dùng step flow thay vì tự gửi tín hiệu giữa step

Ví dụ workflow thực sự là hai step của cùng một job:

```java
@Bean
Job importAndAggregate(
        JobRepository repository,
        Step importStep,
        Step aggregateStep) {

    return new JobBuilder("importAndAggregate", repository)
            .start(importStep)
            .next(aggregateStep)
            .build();
}
```

Khi `importStep` không cho phép flow tiếp tục theo kết quả của nó, Batch flow sẽ quyết định bước sau theo cấu hình. Nếu cần rẽ nhánh theo mã kết thúc tùy biến, dùng flow transition như `.on("COMPLETED")`, `.to(...)`, `.from(...)` theo semantics của `ExitStatus`.

### 9.2. Nếu job thực sự độc lập

Ví dụ import job và aggregation job thuộc hai dịch vụ. Consumer nhận `JobFinished`, xác nhận `status=COMPLETED` và điều kiện businessDate đúng, sau đó tạo `JobParameters` cho downstream.

```java
public void onJobFinished(JobCompletionSignal signal) {
    if (signal.batchStatus()
            != org.springframework.batch.core.BatchStatus.COMPLETED) {
        return;
    }

    if (!"dailyImport".equals(signal.jobName())) {
        return;
    }

    // Điều phối aggregation đúng businessDate.
    // Cần idempotency theo jobName + businessDate ở consumer.
    triggerAggregateOnce(signal.businessDate());
}
```

`triggerAggregateOnce(...)` là hàm minh họa của hệ thống điều phối. Không gọi downstream hai lần chỉ vì message được broker giao lại; nên lưu trạng thái trigger theo business key hoặc dựa vào identifying `JobParameters` kết hợp logic xử lý exception của `JobLauncher`.

### 9.3. Scheduler overlap

Nếu cron chạy mỗi giờ nhưng một execution mất 90 phút, có thể có hai execution thuộc hai cửa sổ dữ liệu khác nhau hoặc một lần launch trùng `JobInstance`. Completion signal của lượt trước có thể đến **sau** tín hiệu launch của lượt sau. Consumer không nên giả định **thứ tự nhận event bằng thứ tự các lịch chạy**.

Để xử lý, dùng `businessDate`/`windowStart`/`windowEnd` và khóa điều phối cụ thể. Nếu business flow yêu cầu chạy tuần tự, cần khóa điều phối hoặc giới hạn concurrency có thể quan sát, thay vì suy ra thứ tự từ cron.

## 10. Restart và semantics “job đã hoàn tất”

Một `JobInstance` có thể trải qua nhiều lượt chạy:

```text
JobInstance (dailySettlement, businessDate=2025-05-12)
   |
   +-- JobExecution 501: FAILED
   |      event: JobFinished(501, FAILED)
   |
   +-- JobExecution 509: STOPPED
   |      event: JobFinished(509, STOPPED)
   |
   +-- JobExecution 517: COMPLETED
          event: JobFinished(517, COMPLETED)
          event: ReportReady(2025-05-12)
```

Hai loại sự kiện có khóa khác nhau:

- **Execution-finished event**: khóa theo `jobExecutionId`; mỗi attempt kết thúc có thể tạo một event.
- **Business-result-ready event**: khóa theo `jobName + identifying business parameters`; thường chỉ một sự kiện báo dữ liệu ngày đó đã sẵn sàng, kể cả job đã retry/restart nhiều lần.

Nếu consumer xử lý số liệu tài chính, báo cáo hoặc chuyển tiền, chỉ chống trùng theo `jobExecutionId` có thể **chưa đủ**: hai execution khác nhau có thể vô tình kích hoạt cùng một hành động nghiệp vụ. Thiết kế khóa idempotency phải xuất phát từ nghiệp vụ.

**Không tự dùng một `run.id` mới để “restart” job.** Tham số identifying mới có thể tạo `JobInstance` khác. Restart đúng phải dựa trên job instance và trạng thái đã lưu, với cấu hình reader/writer có thể resume an toàn.

## 11. Kiểm thử completion signal

Có hai mục tiêu cần tách:

1. Listener có phát event đúng với input status không?
2. Job chạy thật có đăng ký listener, kết thúc đúng trạng thái và làm event xuất hiện không?

### 11.1. Unit test listener với sink giả lập

Ví dụ dùng JUnit Jupiter và Mockito, áp dụng Spring Batch 5.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

import static org.mockito.Mockito.mock;

class CompletionSignalListenerTest {

    private final CompletionSignalSink sink =
            mock(CompletionSignalSink.class);

    private final CompletionSignalListener listener =
            new CompletionSignalListener(sink);

    private JobExecution execution(BatchStatus status) {
        JobInstance instance = new JobInstance(7L, "dailySettlement");

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2025-05-12")
                .toJobParameters();

        JobExecution execution = new JobExecution(instance, params);
        execution.setId(501L);
        execution.setStatus(status);
        execution.setExitStatus(
                status == BatchStatus.COMPLETED
                        ? ExitStatus.COMPLETED
                        : ExitStatus.FAILED
        );

        return execution;
    }

    @Test
    void emitsCompletionSignalWhenJobCompleted() {
        JobExecution execution = execution(BatchStatus.COMPLETED);
        ArgumentCaptor<JobCompletionSignal> captor =
                ArgumentCaptor.forClass(JobCompletionSignal.class);

        listener.afterJob(execution);

        verify(sink).publish(captor.capture());

        JobCompletionSignal signal = captor.getValue();
        assertEquals(501L, signal.jobExecutionId());
        assertEquals("dailySettlement", signal.jobName());
        assertEquals("2025-05-12", signal.businessDate());
        assertEquals(BatchStatus.COMPLETED, signal.batchStatus());
        assertEquals("COMPLETED", signal.exitCode());
    }

    @Test
    void emitsFailedStatusAsFinishedNotAsSuccess() {
        listener.afterJob(execution(BatchStatus.FAILED));

        ArgumentCaptor<JobCompletionSignal> captor =
                ArgumentCaptor.forClass(JobCompletionSignal.class);
        verify(sink).publish(captor.capture());

        assertEquals(BatchStatus.FAILED,
                captor.getValue().batchStatus());
    }

    @Test
    void doesNotEmitWhenStatusIsStillRunning() {
        listener.afterJob(execution(BatchStatus.STARTED));

        verify(sink, never()).publish(any());
    }
}
```

Một `@Test` bổ sung nên cho `sink.publish(...)` ném exception và xác nhận listener ghi nhận lỗi theo chính sách đã chọn. Nếu mục tiêu là **delivery bền vững**, test này chưa đủ: cần test outbox/reconcile, retry dispatcher và consumer idempotency.

### 11.2. Integration test chạy toàn job

Unit test gọi `afterJob(...)` trực tiếp sẽ **không phát hiện thiếu `.listener(...)`** trong `JobBuilder`. Dùng `spring-batch-test` để chạy cả job bằng `JobLauncherTestUtils.launchJob(...)`.

Ví dụ lớp test dùng cấu hình riêng, H2 và Spring Boot 3.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.CopyOnWriteArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = CompletionSignalIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class CompletionSignalIntegrationTest {

    @Autowired JobLauncherTestUtils testUtils;
    @Autowired RecordingSink sink;

    @Test
    void afterJobShouldRunOnceForCompletedJob() throws Exception {
        JobExecution execution = testUtils.launchJob();

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(1, sink.events.size());
        assertEquals(execution.getId().longValue(),
                sink.events.get(0).jobExecutionId());
        assertEquals(BatchStatus.COMPLETED,
                sink.events.get(0).batchStatus());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        RecordingSink recordingSink() {
            return new RecordingSink();
        }

        @Bean
        CompletionSignalListener completionListener(RecordingSink sink) {
            return new CompletionSignalListener(sink);
        }

        @Bean
        Step noOpStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager) {

            return new StepBuilder("noOpStep", repository)
                    .tasklet((contribution, chunkContext) ->
                            RepeatStatus.FINISHED, transactionManager)
                    .build();
        }

        @Bean
        Job completionTestJob(
                JobRepository repository,
                Step noOpStep,
                CompletionSignalListener listener) {

            return new JobBuilder("completionTestJob", repository)
                    .start(noOpStep)
                    .listener(listener)
                    .build();
        }
    }

    static class RecordingSink implements CompletionSignalSink {
        final List<JobCompletionSignal> events =
                new CopyOnWriteArrayList<>();

        @Override
        public void publish(JobCompletionSignal event) {
            events.add(event);
        }
    }
}
```

`@SpringBatchTest` cung cấp các tiện ích kiểm thử Batch. Test trên kiểm tra một job thành công, không đưa message ra ngoài và giả định mỗi test có metadata phù hợp để chạy độc lập. Nếu context được dùng lại, bảo đảm job parameters định danh riêng hoặc làm sạch `JobRepository` trước khi chạy lại; nếu không, một `JobInstance` đã hoàn tất có thể bị chặn ở lượt test sau.

Với job bất đồng bộ, `launchJob(...)` hoặc `JobLauncher.run(...)` có thể chưa trả kết quả cuối khi test đọc ngay; khi đó cần cơ chế đợi điều kiện qua `JobExplorer` hoặc test fixture đồng bộ, rồi assert sau khi execution đã thật sự kết thúc.

### 11.3. Test các tình huống quan trọng khác

| Kịch bản | Điều kiện xác nhận |
|---|---|
| Job `COMPLETED` | Phát completion event có đúng execution ID, status và tham số |
| Job `FAILED` | Phát “finished failed” hoặc cảnh báo; **không** phát `ReportReady` |
| Job `STOPPED` | Không phát “ready”; cho phép quy trình restart thích hợp |
| Một step thành công, step sau thất bại | Không phát success signal chỉ vì step đầu `COMPLETED` |
| Callback `afterJob` không đăng ký | Integration test phải phát hiện thiếu event |
| Network lỗi khi publish | Có log/metric và retry/reconciliation; không tuyên bố message đã giao |
| Publisher gửi lại event | Consumer không kích hoạt công việc nghiệp vụ hai lần |
| Restart execution khác ID | Có event kết thúc mới, nhưng `ReportReady` theo businessDate không trùng |
| Scheduler overlap | Hai execution được phân biệt bằng ID và identifying parameters |
| Worker bị kill | Reconciler phát hiện trạng thái terminal nếu metadata đã ghi; nếu còn `STARTED`, đưa vào xử lý recovery |
| Exit code tùy biến | Quy tắc downstream xử lý đúng `COMPLETED_WITH_WARNINGS` hoặc mã do ứng dụng định nghĩa |

## 12. Giám sát và vận hành

Completion signal hữu ích nhất khi đi kèm khả năng quan sát. Hệ thống quản trị nên ghi nhận tối thiểu:

```text
event=batch.job.finished
jobName=dailySettlement
jobExecutionId=501
businessDate=2025-05-12
batchStatus=COMPLETED
exitCode=COMPLETED
signalEventId=dailySettlement:501:finished
publishStatus=PENDING
```

Đây chỉ là dữ liệu mẫu. Trong triển khai thật, nên lấy trạng thái chính thức từ `JobExecution`, không tự gán success dựa trên việc scheduler callback không ném exception.

Các số liệu giám sát hữu ích gồm:

- Số execution kết thúc theo `COMPLETED`, `FAILED`, `STOPPED`.
- Thời gian từ scheduler trigger đến execution terminal.
- Thời gian từ execution terminal đến sự kiện được giao/ACK.
- Số sự kiện outbox còn `PENDING`, số lần retry và số consumer duplicate đã bỏ qua.
- Job nằm ở `STARTED` hoặc `STOPPING` quá lâu so với cửa sổ vận hành.
- Job hoàn thành về mặt kỹ thuật nhưng không tạo kết quả nghiệp vụ mong đợi.

Khi publish event bị lỗi, cảnh báo cần chỉ rõ `jobExecutionId` và `eventId`. Người vận hành có thể đối chiếu metadata và quyết định replay một event cụ thể từ outbox. Tránh thao tác chạy lại toàn bộ job chỉ vì **tín hiệu notification bị mất** nếu dữ liệu nghiệp vụ đã hoàn thành.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Phát success ngay sau `JobLauncher.run()` | Async job còn chạy hoặc sẽ thất bại | Dựa vào `afterJob` hoặc trạng thái terminal trong `JobRepository` |
| Dựa trên `@Scheduled` chạy không exception | Chỉ chứng minh lịch kích hoạt thành công | Đọc `JobExecution` thực sự |
| Dùng `afterStep` để kết luận toàn job | Các step khác chưa chạy hoặc thất bại | Dùng callback cấp job |
| Coi mọi `afterJob` là thành công | `afterJob` cũng chạy với `FAILED` | Kiểm tra `BatchStatus` |
| Chỉ lưu `jobName`, không có execution ID | Nhiều lượt chạy gây nhầm sự kiện | Kèm `jobExecutionId` và `businessDate` |
| Phát thẳng HTTP không có retry/reconcile | Có thể mất tín hiệu nếu service chết | Outbox + reconciler + idempotent consumer |
| Tin rằng outbox tự cho “exactly once” | Duplicate vẫn có thể xảy ra khi crash/retry | Deduplication theo event/business key |
| Dùng ngày hiện tại lúc nhận event | Consumer chạy ngày hôm sau có thể xử lý sai dữ liệu | Lấy ngày từ `JobParameters` đã chốt |
| Luôn kích hoạt downstream khi `COMPLETED` | Có thể thiếu bước kiểm soát chất lượng | Contract `DataReady` hoặc chính sách theo exit code |
| Dùng `Thread.sleep` để đợi hoàn tất | Test chậm và không ổn định | Poll condition với timeout, latch/future hoặc launcher đồng bộ |
| Thử gửi lại bằng cách restart job đã `COMPLETED` | Có thể bị `JobInstanceAlreadyCompleteException` | Replay tín hiệu/outbox, không chạy lại dữ liệu |
| Không version hóa schema event | Consumer có thể lỗi sau khi producer đổi field | Thêm `eventVersion` và xử lý tương thích |

## 14. Bài tập thực hành

Thiết kế hệ thống gồm hai job:

- `importSales` chạy lúc 01:00, nhận identifying parameter `businessDate` và nhập dữ liệu.
- `buildDailyReport` chỉ được kích hoạt khi dữ liệu `importSales` cho đúng ngày đã sẵn sàng.

Yêu cầu:

1. Tạo `JobExecutionListener` cho `importSales` phát event `JobFinished` gồm `jobExecutionId`, `businessDate`, `BatchStatus` và `ExitStatus`.
2. Chạy thử ba trường hợp `COMPLETED`, `FAILED` và `STOPPED`; xác nhận chỉ trường hợp đạt contract mới phát `DataReady`.
3. Tạo consumer nhận `DataReady`, launch `buildDailyReport` đúng ngày nghiệp vụ và chống launch trùng theo khóa `businessDate`.
4. Mô phỏng callback publish thất bại sau khi job đã kết thúc. Dùng bảng outbox và reconciler để event vẫn có thể được gửi lại.
5. Mô phỏng broker giao cùng event hai lần. Xác nhận consumer không tạo hai báo cáo cho cùng ngày.
6. Cho job import thất bại lượt đầu rồi restart thành công. Giải thích vì sao có hai event `JobFinished` nhưng chỉ một sự kiện “báo cáo đã sẵn sàng” theo khóa nghiệp vụ.
7. Viết unit test cho listener và integration test chạy job thật qua `spring-batch-test`, chứng minh listener đã được đăng ký.
8. Chạy với launcher bất đồng bộ để chứng minh giá trị trả về ban đầu của `JobLauncher.run(...)` không phải bằng chứng hoàn tất.

**Câu hỏi tự kiểm tra:** Scheduler log `“Job launched successfully”` và nhận được `JobExecution id=501` ở trạng thái `STARTED`. Có được gửi email “Đối soát thành công” chưa? **Không.** Cần đợi một kết quả cuối được xác nhận, sau đó kiểm tra tiêu chí thành công và khả năng giao thông báo.

## 15. Tài liệu tham khảo

- [Spring Batch 5.2 — Configuring a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html): `JobExecutionListener`, `beforeJob` và `afterJob`.
- [Spring Batch 5.2 — JobExecutionListener API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/JobExecutionListener.html): chữ ký callback và lưu ý trạng thái.
- [Spring Batch 5.2 — Batch Status Versus Exit Status](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html): phân biệt `BatchStatus` và `ExitStatus`.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, trạng thái và metadata.
- [Spring Batch — JobExplorer API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/explore/JobExplorer.html): truy vấn execution và job instance.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils` và integration test.
- [Spring Framework — Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableScheduling`, `@Scheduled` và cấu hình lịch chạy.
