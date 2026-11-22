# Mapping status sang monitoring

Trong Spring Batch, trạng thái Job và Step cho biết vòng đời thực thi của một lần chạy. Hệ thống monitoring cần chuyển những trạng thái này thành tín hiệu vận hành dễ hiểu để dashboard, cảnh báo và quy trình hỗ trợ có thể trả lời các câu hỏi: Job đang chạy hay đã kết thúc, kết quả có thành công không, có bị dừng có chủ đích không, có lỗi cần xử lý không và tiến độ có đang bị đình trệ không.

Việc mapping cần phân biệt **BatchStatus**, **ExitStatus** và kết quả nghiệp vụ. Ba khái niệm này có liên quan nhưng không đồng nghĩa. Nếu chỉ nhìn một giá trị trạng thái, monitoring có thể báo thành công khi dữ liệu đầu ra không đạt yêu cầu hoặc báo lỗi trong khi Job chỉ đang chờ dừng theo yêu cầu vận hành.

## 1. Vì sao cần mapping status?

Spring Batch lưu trạng thái thực thi trong JobRepository. Các trạng thái này phục vụ điều phối Job, restart và theo dõi tiến độ. Monitoring thường cần một mô hình đơn giản hơn để biểu diễn vòng đời trên dashboard và tạo cảnh báo.

Ví dụ, dashboard có thể cần các nhóm:

- **Queued / Pending:** Job đã được yêu cầu nhưng chưa bắt đầu thực thi. Đây thường là trạng thái của scheduler hoặc hệ thống điều phối bên ngoài, không phải BatchStatus.
- **Starting:** Job đang khởi tạo.
- **Running:** Job đang thực thi.
- **Stop requested:** Đã yêu cầu dừng nhưng Job chưa kết thúc.
- **Succeeded:** Job đã hoàn tất theo trạng thái kỹ thuật.
- **Failed:** Job kết thúc do lỗi.
- **Stopped:** Job đã dừng theo yêu cầu hoặc điều kiện flow.
- **Abandoned:** Execution được đánh dấu không tiếp tục.
- **Unknown / Needs investigation:** Không xác định được trạng thái đáng tin cậy.

Mapping thống nhất giúp:

- Dashboard hiển thị cùng một cách hiểu cho nhiều Job.
- Alert chỉ phát khi trạng thái cần người vận hành can thiệp.
- Theo dõi thời gian chạy, thời gian chờ và thời gian xử lý.
- Tách lỗi kỹ thuật khỏi kết quả nghiệp vụ.
- Đối chiếu JobExecution với scheduler, message broker và hệ thống đích.
- Xây dựng báo cáo SLA và lịch sử chạy.

Không nên thay đổi trạng thái gốc trong JobRepository chỉ để làm dashboard dễ hiển thị. Hãy giữ trạng thái Spring Batch và tạo lớp mapping ở tầng monitoring.

## 2. Phân biệt BatchStatus và ExitStatus

Spring Batch lưu hai loại trạng thái quan trọng cho JobExecution và StepExecution:

| Thuộc tính | Ý nghĩa | Dùng để |
| --- | --- | --- |
| **BatchStatus** | Trạng thái vòng đời thực thi do Spring Batch quản lý | Biết Job/Step đang chạy, đã hoàn tất, thất bại hay dừng |
| **ExitStatus** | Mã kết quả dùng cho flow và mô tả kết quả thực thi | Chọn transition và biểu diễn kết quả chi tiết |

BatchStatus là enum có các giá trị thường gặp:

- STARTING
- STARTED
- STOPPING
- STOPPED
- COMPLETED
- FAILED
- ABANDONED
- UNKNOWN

ExitStatus là đối tượng có exit code và mô tả. Các code mặc định thường gặp gồm COMPLETED, EXECUTING, FAILED, NOOP, STOPPED và UNKNOWN. Ứng dụng cũng có thể tạo exit code tùy chỉnh để mô tả kết quả nghiệp vụ.

Ví dụ, một Step có thể kết thúc với BatchStatus COMPLETED nhưng ExitStatus là một mã tùy chỉnh như COMPLETED_WITH_SKIPS. Điều đó có nghĩa Step đã hoàn tất về mặt thực thi, nhưng đã có một số item bị bỏ qua.

Ngược lại, flow có thể xử lý nhánh Step thất bại bằng recovery Step rồi kết thúc Job theo một trạng thái khác. Vì vậy, cần xem cả JobExecution và các StepExecution liên quan.

### Không dùng ExitStatus thay cho BatchStatus

BatchStatus trả lời câu hỏi “execution đang ở trạng thái vòng đời nào?”. ExitStatus trả lời câu hỏi “execution kết thúc với mã kết quả nào và flow nên đi theo nhánh nào?”.

Monitoring nên lưu cả hai trường:

~~~text
job_execution_id = 8124
batch_status     = COMPLETED
exit_code        = COMPLETED_WITH_SKIPS
exit_description = 12 records were skipped
~~~

Nếu chỉ map exit code COMPLETED_WITH_SKIPS thành FAILED, dashboard có thể thể hiện sai vòng đời thực thi. Nếu chỉ map BatchStatus COMPLETED thành thành công nghiệp vụ, dashboard có thể bỏ qua việc có 12 bản ghi bị loại.

## 3. Mapping BatchStatus sang trạng thái vận hành

Một mapping cơ bản có thể dùng như sau:

| BatchStatus | Trạng thái monitoring gợi ý | Ý nghĩa vận hành |
| --- | --- | --- |
| STARTING | STARTING | Job/Step đang khởi tạo và chuẩn bị tài nguyên |
| STARTED | RUNNING | Execution đang thực thi |
| STOPPING | STOP_REQUESTED | Đã yêu cầu dừng, đang chờ kết thúc an toàn |
| STOPPED | STOPPED | Execution đã dừng; có thể cần restart hoặc thao tác vận hành |
| COMPLETED | SUCCEEDED | Execution hoàn tất về mặt kỹ thuật |
| FAILED | FAILED | Execution thất bại; cần xem exception và khả năng restart |
| ABANDONED | ABANDONED | Execution được đánh dấu không tiếp tục |
| UNKNOWN | UNKNOWN | Không thể xác định trạng thái đáng tin cậy |

Đây là mapping vận hành tham khảo. Tùy nghiệp vụ, COMPLETED có thể cần được kết hợp với ExitStatus, skip count hoặc kiểm tra dữ liệu đầu ra trước khi gọi là SUCCESS.

### Pending không phải BatchStatus

Một Job nằm trong scheduler queue nhưng chưa được JobLauncher gọi chưa có JobExecution đang chạy. Nếu dashboard cần hiển thị PENDING, trạng thái này phải đến từ scheduler, API nhận yêu cầu hoặc bảng điều phối của ứng dụng.

Không tạo một JobExecution giả chỉ để biểu diễn Job đang chờ. Hãy liên kết trạng thái pending bên ngoài với JobParameters hoặc business request ID khi Job thực sự được khởi chạy.

## 4. Mapping bằng Java

Có thể chuyển BatchStatus sang enum riêng của ứng dụng:

~~~java
public enum OperationalStatus {
    STARTING,
    RUNNING,
    STOP_REQUESTED,
    STOPPED,
    SUCCEEDED,
    FAILED,
    ABANDONED,
    UNKNOWN
}
~~~

Hàm mapping:

~~~java
public OperationalStatus mapStatus(BatchStatus status) {
    return switch (status) {
        case STARTING -> OperationalStatus.STARTING;
        case STARTED -> OperationalStatus.RUNNING;
        case STOPPING -> OperationalStatus.STOP_REQUESTED;
        case STOPPED -> OperationalStatus.STOPPED;
        case COMPLETED -> OperationalStatus.SUCCEEDED;
        case FAILED -> OperationalStatus.FAILED;
        case ABANDONED -> OperationalStatus.ABANDONED;
        case UNKNOWN -> OperationalStatus.UNKNOWN;
    };
}
~~~

Ví dụ dùng Java switch expression. Nếu dự án dùng Java version cũ hơn, có thể viết switch statement hoặc if/else tương đương.

Hàm này chỉ map trạng thái vòng đời. Nó chưa kết luận kết quả nghiệp vụ. Có thể xây dựng thêm một hàm đánh giá kết quả dựa trên ExitStatus, skip count, business validation và dữ liệu đầu ra.

## 5. Mapping kết quả kỹ thuật sang kết quả nghiệp vụ

Một Job có thể hoàn tất về mặt kỹ thuật nhưng kết quả nghiệp vụ cần được phân loại chi tiết hơn.

Ví dụ:

| BatchStatus | ExitStatus | Skip count | Kết quả monitoring có thể dùng |
| --- | --- | ---: | --- |
| COMPLETED | COMPLETED | 0 | SUCCEEDED |
| COMPLETED | COMPLETED_WITH_SKIPS | 12 | SUCCEEDED_WITH_WARNINGS |
| COMPLETED | NO_DATA | 0 | COMPLETED_NO_DATA |
| FAILED | FAILED | bất kỳ | FAILED |
| STOPPED | STOPPED | bất kỳ | STOPPED |
| UNKNOWN | UNKNOWN | không xác định | NEEDS_INVESTIGATION |

Các exit code như COMPLETED_WITH_SKIPS hoặc NO_DATA là quy ước ứng dụng, không phải mặc định bắt buộc của Spring Batch. Hãy định nghĩa code nhất quán và ghi rõ ý nghĩa trong tài liệu vận hành.

Ví dụ hàm phân loại:

~~~java
public String mapBusinessOutcome(
        JobExecution execution,
        long totalSkipCount) {

    if (execution.getStatus() == BatchStatus.FAILED) {
        return "FAILED";
    }

    if (execution.getStatus() == BatchStatus.STOPPED) {
        return "STOPPED";
    }

    if (execution.getStatus() == BatchStatus.UNKNOWN) {
        return "NEEDS_INVESTIGATION";
    }

    if (execution.getStatus() == BatchStatus.COMPLETED
            && totalSkipCount > 0) {
        return "SUCCEEDED_WITH_WARNINGS";
    }

    if (execution.getStatus() == BatchStatus.COMPLETED
            && "NO_DATA".equals(
                    execution.getExitStatus().getExitCode())) {
        return "COMPLETED_NO_DATA";
    }

    if (execution.getStatus() == BatchStatus.COMPLETED) {
        return "SUCCEEDED";
    }

    return "IN_PROGRESS";
}
~~~

Đây là logic minh họa. Thứ tự điều kiện phải phản ánh quy tắc nghiệp vụ của Job. Nếu Job có recovery flow hoặc custom ExitStatus, cần xác định rõ trạng thái nào được xem là thành công, cảnh báo hay thất bại nghiệp vụ.

Không nên dùng skip count duy nhất để kết luận chất lượng dữ liệu. Có Job cho phép skip một số lỗi nhất định; Job khác phải thất bại nếu chỉ một item bị skip. Có thể cần kiểm tra tỷ lệ rejected, loại lỗi hoặc kết quả đối soát trước khi publish dữ liệu.

## 6. Job status và Step status có thể khác nhau

Một Job gồm nhiều Step. Mỗi StepExecution có BatchStatus và ExitStatus riêng. Trạng thái cuối của JobExecution được xác định theo flow và kết quả thực thi của Job.

Ví dụ flow có recovery:

~~~text
importStep -> FAILED
      |
      v
recordFailureStep -> COMPLETED
      |
      v
flow kết thúc theo nhánh đã cấu hình
~~~

Nếu flow xử lý nhánh lỗi rồi kết thúc bình thường, Job có thể có trạng thái khác với Step đã thất bại. Vì thế, dashboard cấp Job không đủ để chẩn đoán.

Nên hiển thị:

- Job BatchStatus và ExitStatus.
- Danh sách StepExecution cùng trạng thái.
- Step thất bại đầu tiên hoặc Step gây ra nhánh lỗi.
- Recovery Step đã chạy hay chưa.
- Exception gốc và thông tin failure.
- Số item đọc, ghi, filter và skip.

### Không chỉ lấy StepExecution cuối cùng

Step cuối cùng có thể là Step tổng hợp hoặc recovery. Step này COMPLETED không có nghĩa mọi Step trước đó đều thành công. Hãy kiểm tra toàn bộ StepExecution thuộc JobExecution và quy tắc flow đã dùng.

## 7. Thu thập trạng thái qua JobExecutionListener

JobExecutionListener cung cấp callback trước và sau Job:

~~~java
public class JobMonitoringListener implements JobExecutionListener {

    private final MonitoringPublisher publisher;

    public JobMonitoringListener(MonitoringPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        publisher.publishStarted(
                jobExecution.getId(),
                jobExecution.getJobInstance().getJobName());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        publisher.publishFinished(
                jobExecution.getId(),
                jobExecution.getStatus().name(),
                jobExecution.getExitStatus().getExitCode(),
                jobExecution.getStartTime(),
                jobExecution.getEndTime());
    }
}
~~~

Đăng ký listener vào Job:

~~~java
return new JobBuilder("dailyImportJob", jobRepository)
        .start(importStep)
        .listener(jobMonitoringListener)
        .build();
~~~

Listener phù hợp để phát sự kiện bắt đầu và kết thúc, ghi log có cấu trúc hoặc cập nhật hệ thống monitoring. Tuy nhiên, afterJob chỉ chạy khi Job kết thúc theo lifecycle của framework; nó không phải heartbeat liên tục cho một Job đang chạy.

Nếu publisher gọi hệ thống ngoài và thất bại, không nên để lỗi gửi metric hoặc thông báo làm thay đổi kết quả nghiệp vụ ngoài ý muốn. Có thể dùng logging, outbox hoặc một cơ chế phát sự kiện có retry riêng.

## 8. Thu thập trạng thái ở cấp Step

StepExecutionListener giúp theo dõi từng Step:

~~~java
public class StepMonitoringListener implements StepExecutionListener {

    private final MonitoringPublisher publisher;

    public StepMonitoringListener(MonitoringPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        publisher.publishStepStarted(
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName(),
                stepExecution.getId());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        publisher.publishStepFinished(
                stepExecution.getJobExecutionId(),
                stepExecution.getStepName(),
                stepExecution.getStatus().name(),
                stepExecution.getExitStatus().getExitCode(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount());

        return null;
    }
}
~~~

Trả về null trong afterStep giữ nguyên ExitStatus hiện tại. Nếu listener trả về ExitStatus khác, framework có thể kết hợp hoặc thay đổi kết quả của Step tùy quy tắc listener. Vì vậy, listener monitoring chỉ nên quan sát và không tự ý thay đổi ExitStatus.

Đối với Step chạy lâu, beforeStep và afterStep chỉ cho biết điểm bắt đầu/kết thúc. Để hiển thị tiến độ liên tục, có thể polling JobRepository bằng JobExplorer, phát metric theo chunk hoặc cập nhật heartbeat từ thành phần xử lý phù hợp.

## 9. Dùng JobExplorer để đọc trạng thái

JobExplorer là API chỉ đọc để tra cứu metadata của JobInstance, JobExecution và StepExecution. Nó phù hợp cho dashboard hoặc service monitoring không nên trực tiếp sửa JobRepository.

Ví dụ lấy một JobExecution:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    log.info(
            "job={}, status={}, exitCode={}, start={}, end={}",
            execution.getJobInstance().getJobName(),
            execution.getStatus(),
            execution.getExitStatus().getExitCode(),
            execution.getStartTime(),
            execution.getEndTime());
}
~~~

Lấy thông tin từng Step:

~~~java
if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, exitCode={}, read={}, write={}, skips={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus().getExitCode(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount());
    }
}
~~~

Với một Job name, có thể tra cứu các execution đang chạy bằng API phù hợp của JobExplorer, chẳng hạn findRunningJobExecutions(jobName). Khi xây dựng dashboard lịch sử, nên phân trang theo JobInstance/JobExecution thay vì tải toàn bộ lịch sử vào bộ nhớ.

Không dùng JobExplorer để sửa trạng thái. Các thao tác stop/restart thuộc JobOperator hoặc API điều phối phù hợp và phải tuân thủ quyền vận hành.

## 10. Monitoring bằng Micrometer metrics

Spring Batch hỗ trợ tích hợp Micrometer để ghi nhận metrics cho Job và Step. Trong các phiên bản có instrumentation tương ứng, có thể quan sát timer cho thời gian thực thi Job và Step, thường được đăng ký với các meter name như spring.batch.job và spring.batch.step.

Metrics giúp theo dõi:

- Thời gian thực thi Job/Step.
- Số lần chạy theo Job hoặc Step.
- Trạng thái kết thúc nếu được gắn làm tag.
- Xu hướng thời gian xử lý giữa các lần chạy.
- Khối lượng item và skip count qua counter tùy cấu hình hoặc metric bổ sung của ứng dụng.

Tên meter, tag và mức độ chi tiết có thể khác theo phiên bản Spring Batch, Micrometer registry và cấu hình observability. Hãy kiểm tra meter thực tế trong registry thay vì giả định mọi tag đều tồn tại.

### Metrics tiêu chuẩn và metrics nghiệp vụ

Metrics framework cung cấp cho biết execution mất bao lâu. Ứng dụng thường cần thêm metrics nghiệp vụ:

| Metric | Ý nghĩa |
| --- | --- |
| items_read_total | Tổng item đã đọc |
| items_written_total | Tổng item đã ghi |
| items_skipped_total | Tổng item/lỗi bị skip |
| chunk_commit_total | Số chunk commit |
| chunk_rollback_total | Số chunk rollback |
| job_duration_seconds | Thời gian Job chạy |
| job_last_success_timestamp | Thời điểm Job thành công gần nhất |
| rejected_ratio | Tỷ lệ bản ghi bị loại |
| queue_lag_seconds | Độ trễ của message nếu Job đọc queue |

Các tên trên là ví dụ quy ước ứng dụng, không phải tất cả đều là metric có sẵn của Spring Batch. Cần định nghĩa unit, counter/gauge/timer và reset semantics nhất quán.

### Tránh cardinality quá cao

Không nên dùng JobExecution ID, order ID, customer ID hoặc message ID làm tag metric. Mỗi giá trị riêng có thể tạo một time series mới và làm monitoring backend tăng cardinality rất nhanh.

Tag phù hợp thường là Job name, Step name, environment, status hoặc loại nguồn dữ liệu với số lượng giá trị hữu hạn. ID chi tiết nên nằm trong log hoặc trace.

## 11. Logging có cấu trúc

Log giúp điều tra một execution cụ thể. Nên ghi các trường có thể tìm kiếm và tương quan:

- jobName
- jobInstanceId
- jobExecutionId
- stepName
- stepExecutionId
- batchStatus
- exitCode
- startTime và endTime
- readCount, writeCount, skipCount
- exceptionType và errorCode
- correlationId hoặc businessRunId nếu có

Ví dụ log:

~~~java
log.info(
        "batch_job_finished jobName={} jobExecutionId={} status={} exitCode={} durationMs={}",
        jobExecution.getJobInstance().getJobName(),
        jobExecution.getId(),
        jobExecution.getStatus(),
        jobExecution.getExitStatus().getExitCode(),
        durationMillis);
~~~

Không ghi toàn bộ JobParameters nếu chúng có thể chứa token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Chỉ log các identifying values đã được phê duyệt và cần cho đối soát.

Log bắt đầu, kết thúc và lỗi nên dùng event name ổn định để hệ thống log aggregation có thể lọc. Không dùng nội dung message tự do làm nhãn phân loại duy nhất.

## 12. Event và trạng thái gần thời gian thực

Dashboard cần trạng thái gần thời gian thực có thể nhận sự kiện từ listener hoặc polling JobExplorer.

Một event có thể mang cấu trúc:

~~~json
{
  "eventType": "JOB_FINISHED",
  "jobName": "dailyImportJob",
  "jobExecutionId": 8124,
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED_WITH_SKIPS",
  "readCount": 10000,
  "writeCount": 9988,
  "skipCount": 12,
  "occurredAt": "2026-11-15T10:30:00Z"
}
~~~

Event nên có execution ID và thời điểm phát để consumer có thể xử lý trùng hoặc đến sai thứ tự. Ví dụ, event STARTED có thể đến sau event FINISHED do mạng hoặc queue; dashboard cần tránh ghi đè trạng thái cuối bằng event cũ.

Có thể lưu event vào outbox cùng transaction metadata hoặc dữ liệu nghiệp vụ nếu cần bảo đảm phát sự kiện. Nếu publish trực tiếp từ listener, cần chấp nhận khả năng publish thất bại hoặc được gửi lại và thiết kế consumer idempotent.

Polling JobExplorer đơn giản hơn nhưng cần kiểm soát tần suất để tránh tải metadata repository. Chọn chu kỳ polling dựa trên yêu cầu freshness và quy mô số Job.

## 13. Thiết kế dashboard cho Job và Step

Một dashboard hữu ích nên thể hiện cả trạng thái hiện tại và xu hướng:

### Tổng quan Job

- Số Job đang chạy.
- Số Job thành công, thất bại và dừng trong khoảng thời gian.
- Job chưa có lần thành công gần nhất trong SLA.
- Job chạy lâu hơn ngưỡng dự kiến.
- Tỷ lệ thành công theo Job name.

### Chi tiết JobExecution

- Job name và JobExecution ID.
- JobInstance ID và identifying parameters đã được làm sạch.
- BatchStatus và ExitStatus.
- Thời gian bắt đầu, kết thúc và duration.
- Danh sách StepExecution cùng trạng thái.
- Failure exception và stack trace có kiểm soát.
- Read/write/filter/skip counts.
- Checkpoint hoặc tiến độ nếu ứng dụng có cung cấp.

### Chi tiết Step

- Step name và status.
- Read, process, write và skip counts.
- Commit và rollback counts.
- Thời gian thực thi.
- Partition hoặc worker nếu Step có phân tán.
- Lỗi gần nhất và số lần retry nếu có metric.

Không nên chỉ hiển thị một đèn xanh/đỏ cho toàn Job. Một Job COMPLETED_WITH_SKIPS có thể cần cảnh báo màu vàng, còn một Job STOPPED có thể là hành động có chủ đích.

## 14. Alerting theo trạng thái và thời gian

Alert nên dựa trên trạng thái cùng ngữ cảnh, không chỉ dựa trên một giá trị enum:

| Điều kiện | Hành động gợi ý |
| --- | --- |
| Job FAILED | Cảnh báo đội vận hành, đính kèm JobExecution ID và Step lỗi |
| Job UNKNOWN | Cảnh báo mức cao vì trạng thái cần đối soát |
| Job STOPPED ngoài lịch bảo trì | Cảnh báo hoặc yêu cầu xác nhận |
| Job STOPPING quá lâu | Kiểm tra worker, transaction và thao tác shutdown |
| Job STARTED vượt SLA | Kiểm tra tiến độ, lock, queue lag và heartbeat |
| Job COMPLETED nhưng skip ratio vượt ngưỡng | Cảnh báo chất lượng dữ liệu |
| Không có lần thành công trong cửa sổ SLA | Cảnh báo lịch chạy bị bỏ lỡ hoặc Job liên tục lỗi |
| Queue backlog tăng liên tục | Kiểm tra throughput worker và khả năng tiêu thụ |

### Phân biệt Job chạy lâu với Job bị treo

Một Job STARTED lâu không nhất thiết bị treo. Nó có thể đang xử lý một tập dữ liệu lớn hoặc chờ I/O. Cần kết hợp:

- Thời gian chạy so với SLA lịch sử.
- lastUpdated hoặc heartbeat do ứng dụng phát.
- Tiến độ read/write/commit count.
- Queue lag hoặc worker activity.
- Database lock và query duration.
- Log của Step gần nhất.

Nếu status không thay đổi nhưng read/write count vẫn tăng, Job có thể đang hoạt động. Nếu status không đổi, không có heartbeat và không có tiến độ trong một khoảng thời gian dài, có thể cần điều tra.

Không tự động kill Job chỉ vì vượt một ngưỡng thời gian chung. Một số Job có thời lượng tự nhiên dài; dùng SLA riêng theo Job và cơ chế stop an toàn.

## 15. STOPPING, STOPPED và yêu cầu dừng

STOPPING nghĩa là yêu cầu dừng đã được ghi nhận nhưng execution chưa hoàn tất quá trình dừng. STOPPED là trạng thái đã dừng.

Khi người vận hành yêu cầu dừng Job, dashboard nên thể hiện rõ:

1. Ai hoặc hệ thống nào yêu cầu dừng.
2. Thời điểm yêu cầu.
3. JobExecution ID.
4. Trạng thái hiện tại STOPPING hay đã STOPPED.
5. Step/chunk nào đang hoàn tất hoặc rollback.
6. Job có thể restart tiếp hay cần xử lý thủ công.

Không map STOPPED thành FAILED một cách mặc định. Job có thể được dừng có chủ đích để chờ phê duyệt, bảo trì hoặc thay đổi dữ liệu nguồn.

Ngược lại, không map STOPPED thành SUCCEEDED. Đây là một trạng thái dừng riêng và cần được thể hiện đúng trong monitoring.

## 16. FAILED, ABANDONED và UNKNOWN

Ba trạng thái này cần cách xử lý khác nhau:

**FAILED:** Job/Step kết thúc do lỗi. Có thể cần xem exception, xác định khả năng restart và kiểm tra side effect đã commit.

**ABANDONED:** Execution được đánh dấu không tiếp tục. Đây không phải trạng thái thành công; monitoring nên giữ lịch sử và yêu cầu thao tác vận hành nếu cần.

**UNKNOWN:** Framework hoặc repository không thể xác định trạng thái đáng tin cậy. Không nên tự map UNKNOWN thành FAILED hoặc COMPLETED. Cần cảnh báo và đối soát metadata trước khi restart.

Với UNKNOWN, tránh khởi chạy một execution khác với cùng business input khi chưa biết execution trước đã commit dữ liệu đến đâu. Điều đó có thể tạo xử lý trùng.

## 17. Mapping trạng thái trong hệ thống nhiều tầng

Một hệ thống thực tế có thể có scheduler, API nhận yêu cầu, Spring Batch manager, worker và hệ thống monitoring. Mỗi tầng có lifecycle riêng:

~~~text
Scheduler
  PENDING / SCHEDULED
       |
       v
API / Orchestrator
  ACCEPTED
       |
       v
Spring Batch JobExecution
  STARTING -> STARTED -> COMPLETED / FAILED / STOPPED
       |
       v
Worker StepExecution
  STARTING -> STARTED -> COMPLETED / FAILED
       |
       v
Monitoring
  Operational status + business outcome + metrics
~~~

Không gộp mọi trạng thái thành một enum duy nhất nếu các tầng có semantics khác nhau. Nên lưu:

- Orchestration status: trạng thái yêu cầu/scheduler.
- Batch status: trạng thái JobExecution.
- Step status: trạng thái từng StepExecution.
- Business outcome: kết quả nghiệp vụ được ứng dụng đánh giá.

Một yêu cầu có thể ACCEPTED nhưng chưa có JobExecution. JobExecution có thể STARTED trong khi một worker đang chờ resource. Job có thể COMPLETED nhưng business outcome là REJECTED nếu kiểm tra cuối cùng phát hiện dữ liệu không đạt yêu cầu.

## 18. Restart và monitoring

Monitoring nên cung cấp đủ thông tin để người vận hành quyết định có thể restart hay không:

- JobInstance ID và identifying JobParameters.
- JobExecution ID thất bại.
- BatchStatus và ExitStatus.
- StepExecution thất bại.
- Checkpoint và tiến độ đã commit.
- Dữ liệu đầu ra đã ghi.
- Side effect ngoài transaction đã thực hiện.
- Nguyên nhân lỗi và cách khắc phục.

JobOperator có thể hỗ trợ các thao tác stop/restart theo API tương ứng. Không nên để dashboard tự restart mọi Job FAILED mà không kiểm tra tính an toàn, giới hạn restart và trạng thái dữ liệu.

Nếu JobExecution FAILED, cùng JobInstance có thể được restart khi Job cho phép và các điều kiện restart được đáp ứng. Nếu JobExecution COMPLETED, cùng identifying parameters thường không thể tạo một lần chạy mới cho cùng instance. Nếu status UNKNOWN, cần điều tra trước khi thao tác.

## 19. Những lỗi thường gặp

### Chỉ theo dõi BatchStatus

BatchStatus không thể hiện đầy đủ kết quả nghiệp vụ. Kết hợp ExitStatus, skip count và validation output.

### Chỉ theo dõi ExitStatus

ExitStatus có thể là mã tùy chỉnh. Dùng BatchStatus để biết lifecycle và ExitStatus để hiểu kết quả/flow.

### Map mọi COMPLETED thành thành công nghiệp vụ

Job có thể hoàn tất với skip hoặc recovery. Xây dựng business outcome riêng nếu cần.

### Map STOPPED thành FAILED

STOPPED có thể là yêu cầu dừng có chủ đích. Hiển thị riêng và giữ thông tin người yêu cầu dừng.

### Map UNKNOWN thành thành công hoặc thất bại

UNKNOWN nghĩa là chưa xác định được trạng thái. Cảnh báo và đối soát trước khi restart.

### Chỉ xem JobExecution cuối cùng

Một recovery Step có thể hoàn tất sau khi Step nghiệp vụ thất bại. Kiểm tra tất cả StepExecution và flow transition.

### Dùng listener để thay đổi ExitStatus khi chỉ muốn ghi metrics

Listener trả về ExitStatus có thể tác động kết quả Step. Listener monitoring nên giữ nguyên trạng thái nếu không có yêu cầu nghiệp vụ.

### Tạo metric tag từ execution ID hoặc item ID

Cardinality tăng rất nhanh và làm monitoring backend quá tải. Đưa ID chi tiết vào log/trace, dùng tag có tập giá trị giới hạn.

### Coi Job STARTED lâu là bị treo

Kiểm tra tiến độ, heartbeat, SLA và hoạt động worker trước khi cảnh báo hoặc dừng Job.

### Gửi event không có idempotency

Message monitoring có thể đến trùng hoặc sai thứ tự. Gắn execution ID, event time và sequence/version để consumer xử lý đúng.

## 20. Quy trình xây dựng status mapping

Khi thiết kế monitoring cho Spring Batch, hãy xác định:

1. Cần theo dõi JobExecution, StepExecution hay cả hai?
2. BatchStatus nào được map thành trạng thái vận hành nào?
3. Pending/queued đến từ scheduler hay API nào?
4. ExitStatus mặc định và custom exit code có ý nghĩa gì?
5. Khi Job COMPLETED nhưng có skip, business outcome là gì?
6. Recovery flow có thể làm Job hoàn tất sau một Step FAILED không?
7. Listener nào phát sự kiện bắt đầu, kết thúc và lỗi?
8. JobExplorer được dùng để polling hoặc truy vấn lịch sử ra sao?
9. Micrometer metrics nào có sẵn và metric nghiệp vụ nào cần bổ sung?
10. Log có correlation ID và execution ID đủ để điều tra không?
11. Alert nào dựa trên trạng thái, SLA, heartbeat hoặc chất lượng dữ liệu?
12. Dashboard có phân biệt STOPPED, ABANDONED và UNKNOWN không?
13. Quy trình restart có kiểm tra JobInstance, checkpoint và side effect không?

Nên kiểm thử mapping với mọi BatchStatus, các ExitStatus tùy chỉnh, Job có recovery Step, Job có skip, Job bị stop và execution có trạng thái UNKNOWN. Kiểm tra cả dashboard, alert và log để bảo đảm các hệ thống diễn giải cùng một trạng thái theo cùng quy tắc.

## Kết luận

Mapping status sang monitoring cần giữ riêng BatchStatus, ExitStatus, trạng thái Step và kết quả nghiệp vụ. BatchStatus mô tả vòng đời execution; ExitStatus mô tả mã kết quả và flow; business outcome phản ánh quy tắc dữ liệu của ứng dụng. Có thể thu thập trạng thái bằng JobExecutionListener, StepExecutionListener, JobExplorer và Micrometer, sau đó kết hợp log có cấu trúc, metrics, event và alert theo SLA. Cần hiển thị riêng STOPPING, STOPPED, ABANDONED và UNKNOWN, kiểm tra các StepExecution khi có recovery flow và tránh kết luận thành công nghiệp vụ chỉ từ BatchStatus COMPLETED.
