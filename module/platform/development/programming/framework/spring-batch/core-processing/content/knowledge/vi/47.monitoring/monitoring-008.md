# Metadata cho audit trong Spring Batch

Trong hệ thống xử lý theo lô, câu hỏi vận hành không dừng ở việc “batch đã chạy thành công chưa?”. Sau một lần nhập dữ liệu, đối soát, xuất báo cáo hoặc chuyển trạng thái đơn hàng, đội vận hành và người kiểm tra còn cần biết **job nào đã chạy, xử lý kỳ dữ liệu nào, bắt đầu và kết thúc lúc nào, có bao nhiêu bản ghi được đọc/ghi/bỏ qua, lỗi gì xảy ra, và kết quả nào thực sự được tạo ra**.

**Metadata cho audit** là tập thông tin giúp tái dựng lịch sử thực thi batch và liên kết lịch sử đó với dữ liệu nghiệp vụ. Trong **Spring Batch Core Processing**, nền tảng quan trọng nhất là metadata của `JobRepository`: `JobInstance`, `JobExecution`, `StepExecution`, `JobParameters` và `ExecutionContext`. Tuy nhiên, metadata nội bộ của Spring Batch được thiết kế chủ yếu để **vận hành, theo dõi và restart**, không tự động đáp ứng mọi yêu cầu về nhật ký kiểm toán độc lập, chống sửa đổi hay thời hạn lưu trữ.

Bởi vậy nên phân biệt ba lớp thông tin:

| Lớp | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Metadata thực thi Spring Batch | Framework đã chạy những gì và đang ở trạng thái nào? | `JOB_EXECUTION_ID`, thời gian, `BatchStatus`, read/write/skip count |
| Audit nghiệp vụ | Dữ liệu nguồn nào, kỳ nào, ai/yếu tố nào kích hoạt, kết quả nào đã được công nhận? | `businessDate`, `sourceFileId`, checksum, số chứng từ, output artifact |
| Monitoring/observability | Có bất thường ngay lúc này hoặc theo xu hướng không? | Metric duration, alert SLA, tracing, log lỗi |

Một hệ thống hoàn chỉnh thường **liên kết** cả ba bằng `jobExecutionId`, tên job, mã kỳ dữ liệu và correlation ID. Bài này đi từ metadata có sẵn của Spring Batch đến cách xây dựng audit trail đủ ý nghĩa để điều tra một lần chạy.

## 1. Metadata có sẵn trong Spring Batch

Spring Batch lưu trạng thái thực thi trong `JobRepository`. Với repository dùng JDBC, các bảng metadata thường có tiền tố `BATCH_`:

```text
                         BATCH_JOB_INSTANCE
                          (JOB_INSTANCE_ID)
                                 |
                              1 : N
                                 v
                         BATCH_JOB_EXECUTION
                         (JOB_EXECUTION_ID)
                            /          \
                         1 : N         1 : N
                         /                \
                        v                  v
                BATCH_STEP_EXECUTION   BATCH_JOB_EXECUTION_PARAMS
                  (STEP_EXECUTION_ID)    (JobParameters)
                        |
                        v
              BATCH_STEP_EXECUTION_CONTEXT

             BATCH_JOB_EXECUTION_CONTEXT
                (theo JOB_EXECUTION_ID)
```

`BATCH_JOB_EXECUTION_CONTEXT` liên kết trực tiếp với `BATCH_JOB_EXECUTION` và chứa trạng thái dùng ở phạm vi job. `BATCH_STEP_EXECUTION_CONTEXT` liên kết với một step execution và chứa trạng thái ở phạm vi step. Hai bảng context không phải “nhật ký từng thay đổi”: thông thường chúng phản ánh trạng thái được lưu tại các checkpoint gần nhất.

### 1.1. `JobInstance`: định danh công việc logic

Một `JobInstance` được nhận diện bởi **tên job + bộ identifying `JobParameters`**. Ví dụ:

```text
Job name:      dailySettlementJob
businessDate:  2026-11-16   (identifying)
region:        HCM          (identifying)

=> một JobInstance cho cặp kỳ dữ liệu/vùng này
```

Nếu cùng một instance được khởi chạy lại sau lỗi, nó có thể có nhiều `JobExecution`. Nếu vô tình thêm một `runId` ngẫu nhiên dưới dạng identifying parameter ở mỗi lần gọi, framework coi đó là các instance khác nhau, dù cùng dữ liệu nghiệp vụ. Khi audit một kỳ dữ liệu, cần hiểu chính xác cách ứng dụng chọn identifying parameters.

### 1.2. `JobExecution`: từng lần thực thi

`JobExecution` đại diện cho một lần cố gắng chạy job. Thông tin quan trọng bao gồm:

- `JobExecution.getId()`: mã execution, hữu ích để nối log, metric và audit event.
- `getJobInstance()`: tham chiếu đến công việc logic và tên job.
- `getJobParameters()`: tham số của lần thực thi, chẳng hạn `businessDate` hoặc mã tệp nguồn.
- `getCreateTime()`, `getStartTime()`, `getEndTime()`: mốc thời gian của vòng đời thực thi, khi có giá trị.
- `getStatus()`: trạng thái `BatchStatus` như `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPING`, `STOPPED`, `ABANDONED`, `UNKNOWN`.
- `getExitStatus()`: mã/trình bày kết quả exit do job hoặc listener thiết lập; có thể khác về ngữ nghĩa so với `BatchStatus`.
- `getAllFailureExceptions()` hoặc exception ở step: các nguyên nhân thất bại được lưu trong metadata execution khi khả dụng.

**Điểm cần nhớ:** `BatchStatus` là trạng thái vòng đời do framework quản lý. `ExitStatus` mô tả kết quả mà flow/listener có thể sử dụng để điều hướng. Chẳng hạn một step hoàn thành về mặt kỹ thuật nhưng đặt exit code tùy chỉnh để chuyển sang nhánh kiểm tra thủ công. Audit nên ghi cả hai khi cần diễn giải nguyên nhân nghiệp vụ.

### 1.3. `StepExecution`: bằng chứng từng bước xử lý

`StepExecution` chứa trạng thái và các bộ đếm rất hữu ích cho audit:

| Trường/method | Ý nghĩa thông thường |
| --- | --- |
| `getStepName()` | Step đã thực thi |
| `getStatus()` và `getExitStatus()` | Trạng thái và mã kết thúc của step |
| `getStartTime()`, `getEndTime()` | Thời điểm bắt đầu/kết thúc step |
| `getReadCount()` | Số item reader trả về để xử lý |
| `getWriteCount()` | Số item được framework ghi qua writer thành công ở cấp step |
| `getFilterCount()` | Số item mà processor lọc bằng cách trả `null` |
| `getReadSkipCount()` | Số item bị skip do lỗi ở reader |
| `getProcessSkipCount()` | Số item bị skip do lỗi ở processor |
| `getWriteSkipCount()` | Số item bị skip do lỗi ở writer |
| `getCommitCount()` | Số lần commit chunk/transaction được ghi nhận |
| `getRollbackCount()` | Số lần rollback được ghi nhận |
| `getFailureExceptions()` | Lỗi liên quan đến step |

Các bộ đếm mô tả **hoạt động của framework** trong phạm vi step, không tự xác nhận rằng mỗi bản ghi ở hệ thống đích đều đúng. Ví dụ, một writer ghi ra một file tổng hợp có thể chỉ ghi vài dòng output dù reader đọc hàng triệu item. Hoặc writer gọi API bên ngoài nhưng API thực chất từ chối âm thầm: metadata có thể chưa phản ánh chính xác số bản ghi được bên ngoài chấp nhận nếu writer không báo lỗi đúng cách.

### 1.4. `JobParameters`: bộ khóa truy vết kỳ dữ liệu

Spring Batch cho phép tham số identifying và non-identifying. Với audit, cả hai đều có ích nhưng mang vai trò khác nhau:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")        // identifying mặc định
    .addString("region", "HCM")                      // identifying
    .addString("requestedBy", "nightly-scheduler", false)
    .toJobParameters();
```

Trong ví dụ, `businessDate` và `region` tham gia nhận diện `JobInstance`; `requestedBy` chỉ là thuộc tính bổ sung cho execution. Không đặt token, mật khẩu, thông tin định danh khách hàng hoặc nội dung file nhạy cảm trong `JobParameters`, vì chúng có thể được lưu trong repository và xuất hiện trong log, màn hình vận hành.

### 1.5. `ExecutionContext`: checkpoint, không phải audit log bất biến

Job và step có `ExecutionContext` để lưu trạng thái phục vụ restart, chẳng hạn tên file hiện tại, offset hoặc số trang đã đọc:

```java
stepExecution.getExecutionContext().putLong("lastProcessedLine", 5000L);
```

Framework có thể persist context tại các mốc checkpoint. Khi một key bị cập nhật nhiều lần, dữ liệu trước đó thường không còn trong snapshot hiện hành. Vì thế **không dùng `ExecutionContext` như kho lưu toàn bộ audit events**. Cũng không nên nhồi danh sách lớn hoặc dữ liệu nhạy cảm vào context: điều đó làm metadata phình to, tăng rủi ro lộ dữ liệu và gây vấn đề serialization/restart.

## 2. Các bảng metadata JDBC cần biết

Tên cột và một số chi tiết schema thay đổi theo phiên bản Spring Batch và database. Ví dụ sau dựa trên cấu trúc thường gặp ở **Spring Batch 5.x**:

| Bảng | Thông tin điển hình | Công dụng khi audit |
| --- | --- | --- |
| `BATCH_JOB_INSTANCE` | `JOB_INSTANCE_ID`, `JOB_NAME`, `JOB_KEY` | Xác định công việc logic và nhóm các execution cùng instance |
| `BATCH_JOB_EXECUTION` | `JOB_EXECUTION_ID`, `JOB_INSTANCE_ID`, `CREATE_TIME`, `START_TIME`, `END_TIME`, `STATUS`, `EXIT_CODE`, `EXIT_MESSAGE`, `LAST_UPDATED` | Theo dõi mỗi lần chạy và kết quả |
| `BATCH_JOB_EXECUTION_PARAMS` | `JOB_EXECUTION_ID`, `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, `IDENTIFYING` | Giải thích input và identity của job execution |
| `BATCH_STEP_EXECUTION` | `STEP_EXECUTION_ID`, `JOB_EXECUTION_ID`, `STEP_NAME`, `STATUS`, các bộ đếm read/write/skip/commit/rollback | Audit từng công đoạn |
| `BATCH_JOB_EXECUTION_CONTEXT` | `JOB_EXECUTION_ID`, `SHORT_CONTEXT`, `SERIALIZED_CONTEXT` | Snapshot ngữ cảnh phục vụ restart job |
| `BATCH_STEP_EXECUTION_CONTEXT` | `STEP_EXECUTION_ID`, `SHORT_CONTEXT`, `SERIALIZED_CONTEXT` | Snapshot checkpoint của step |

**Không cập nhật thủ công các bảng `BATCH_*` để phục vụ audit.** Chúng thuộc quyền quản lý của Spring Batch. Việc sửa `STATUS`, counter hoặc context trực tiếp bằng SQL có thể làm hỏng restart, tạo lịch sử sai hoặc dẫn tới tình trạng execution không nhất quán. Với nhu cầu audit tùy biến, nên tạo bảng riêng và dùng API/listener của framework.

### 2.1. Truy vấn lịch sử job và step

Một câu truy vấn read-only cho màn hình vận hành hoặc báo cáo audit:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.CREATE_TIME AS job_created_at,
    je.START_TIME  AS job_started_at,
    je.END_TIME    AS job_finished_at,
    je.STATUS      AS job_status,
    je.EXIT_CODE   AS job_exit_code,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS      AS step_status,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.FILTER_COUNT,
    se.READ_SKIP_COUNT,
    se.PROCESS_SKIP_COUNT,
    se.WRITE_SKIP_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = 'dailySettlementJob'
ORDER BY je.JOB_EXECUTION_ID DESC, se.STEP_EXECUTION_ID;
```

Mỗi hàng thể hiện một step execution hoặc một job execution chưa có step. Do phép join một-nhiều, thông tin ở cấp job được lặp lại trên các hàng step; nếu tổng hợp báo cáo, **không được cộng lặp duration hoặc số lần chạy job theo từng hàng**.

Muốn biết tham số `businessDate`, ở schema Spring Batch 5.x có thể truy vấn:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_EXECUTION_PARAMS p
  ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_EXECUTION_ID = :execution_id
  AND p.PARAMETER_NAME IN ('businessDate', 'region');
```

`:execution_id` đại diện cho bind parameter của client/framework SQL, không phải cú pháp parameter được mọi công cụ SQL hỗ trợ nguyên văn. Trong ứng dụng, hãy truyền giá trị bằng prepared statement hoặc `NamedParameterJdbcTemplate` để tránh ghép chuỗi SQL trực tiếp.

Nếu dùng **Spring Batch 4.x, 6.x hoặc schema được tùy biến**, hãy kiểm tra DDL của phiên bản đang triển khai trước khi truy vấn trực tiếp. Ví dụ schema Spring Batch 4.x dùng các cột parameter riêng theo kiểu dữ liệu, khác cấu trúc `PARAMETER_TYPE`/`PARAMETER_VALUE` của 5.x.

### 2.2. Ưu tiên API của framework khi phù hợp

Khi phát triển ứng dụng Spring Batch, có thể dùng `JobExplorer` để đọc metadata thay cho phụ thuộc trực tiếp vào tên bảng:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public class ExecutionLookupService {
    private final JobExplorer jobExplorer;

    public ExecutionLookupService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution find(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Đoạn code dùng package của Spring Batch 5.x. `getJobExecution(...)` có thể trả `null` nếu không tìm thấy. Tùy phiên bản, `JobExplorer` còn cung cấp các phương thức tra cứu instance, execution theo job và các execution đang chạy. Nó giúp viết màn hình audit/monitoring mà không cần truy cập trực tiếp schema, dù vẫn phải quản lý quyền truy cập và volume truy vấn.

## 3. Thiết kế một bản ghi audit có ý nghĩa nghiệp vụ

Metadata runtime trả lời *“Spring Batch làm gì?”*. Audit nghiệp vụ phải bổ sung *“Đây là công việc trên tập dữ liệu nào, vì sao được chạy và dữ liệu kết quả nào được công nhận?”*.

Xét job nhập tệp giao dịch trong một kỳ:

```text
Input:
  businessDate = 2026-11-16
  sourceFileId = bank-feed-20261116-001
  sourceChecksum = sha256:...

Batch:
  jobName = importPaymentsJob
  jobInstanceId = 302
  jobExecutionId = 517
  status = COMPLETED

Result:
  expectedRecords = 10000
  acceptedRecords = 9988
  rejectedRecords = 12
  outputManifestId = batch-output-20261116-001
```

Nên thu thập các nhóm thông tin sau, điều chỉnh theo thực tế:

| Nhóm | Trường gợi ý | Vì sao hữu ích |
| --- | --- | --- |
| Danh tính execution | `jobName`, `jobInstanceId`, `jobExecutionId`, `stepName`, `stepExecutionId` | Liên kết audit với metadata của framework |
| Danh tính kỳ dữ liệu | `businessDate`, `tenantId`, `region`, `windowStart`, `windowEnd` | Truy vết dữ liệu thực tế thuộc kỳ nào |
| Nguồn kích hoạt | `triggerType`, `schedulerName`, `requestedBy`, `correlationId`, `requestId` | Phân biệt lịch tự động, thao tác thủ công và chạy bù |
| Nguồn đầu vào | `sourceSystem`, `sourceFileId`, `objectVersion`, checksum, input count | Chứng minh phiên bản dữ liệu đã được xử lý |
| Mốc thời gian | `scheduledAt`, `startedAt`, `finishedAt`, `eventRecordedAt` | Đo độ trễ, đối chiếu SLA, điều tra downtime |
| Kết quả kỹ thuật | `BatchStatus`, `ExitStatus`, step statuses, read/write/skip counts | Xác định đường thực thi và kết quả framework |
| Kết quả nghiệp vụ | `acceptedCount`, `rejectedCount`, `totalAmount`, `outputManifestId`, checksum đầu ra | Đối soát giữa batch và nghiệp vụ |
| Lỗi/cảnh báo | `errorCode`, `failureCategory`, mã đối soát, đường dẫn artifact lỗi | Điều tra và giải trình |
| Phiên bản xử lý | `appVersion`, `rulesetVersion`, `schemaVersion` | Giải thích cùng input nhưng kết quả khác nhau sau nâng cấp |

**Không nhất thiết lưu toàn bộ trường trên ở mỗi event.** Một event cấp job có thể chứa kết quả tổng hợp, còn event cấp file hoặc step chứa thông tin chi tiết. Điều quan trọng là có khóa liên kết rõ ràng và quy tắc định nghĩa metric thống nhất.

### 3.1. Metadata đủ để xác nhận điều gì?

Giả sử `StepExecution` ghi:

```text
READ_COUNT         = 10000
FILTER_COUNT       = 10
PROCESS_SKIP_COUNT = 2
WRITE_COUNT        = 9988
STATUS             = COMPLETED
```

Các con số này cho thấy cách step xử lý item theo cơ chế Spring Batch. Chúng **không tự chứng minh** số giao dịch được ngân hàng chấp nhận, số tiền đối soát khớp hay tệp đầu ra chưa bị sửa sau khi xuất. Với yêu cầu audit tài chính, ứng dụng còn cần đối chiếu output thực tế, checksum, tổng tiền và dấu vết gửi/nhận từ hệ thống đích.

### 3.2. Audit sự kiện và snapshot

Có hai mô hình bổ sung nhau:

**Snapshot trạng thái hiện tại:** một hàng `batch_run_summary` được update từ `RUNNING` sang `FAILED`/`COMPLETED`. Dễ làm báo cáo trạng thái mới nhất nhưng các giá trị cũ có thể bị ghi đè.

**Append-only audit event:** mỗi thay đổi quan trọng tạo một hàng mới, ví dụ `JOB_REQUESTED`, `JOB_STARTED`, `STEP_COMPLETED`, `JOB_FAILED`, `JOB_COMPLETED`, `OUTPUT_PUBLISHED`. Cách này giúp dựng lại diễn biến theo thời gian và giảm mất lịch sử do cập nhật đè.

```text
2026-11-17 02:00:00  JOB_REQUESTED   businessDate=2026-11-16
2026-11-17 02:00:01  JOB_STARTED     jobExecutionId=517
2026-11-17 02:05:30  STEP_COMPLETED  read=10000, write=9988
2026-11-17 02:05:31  OUTPUT_PUBLISHED manifest=batch-output-...
2026-11-17 02:05:31  JOB_COMPLETED   jobExecutionId=517
```

Nếu triển khai append-only thật sự, nên giới hạn quyền sửa/xóa dữ liệu, quản lý retention và cân nhắc lưu bằng chứng trong hệ thống có chức năng lưu bất biến theo yêu cầu tổ chức. **Một bảng chỉ được ứng dụng `INSERT` chưa tự động trở thành nhật ký chống sửa đổi**: DBA hoặc tài khoản có quyền vẫn có thể thay đổi bản ghi nếu không có kiểm soát bổ sung.

## 4. Ghi nhận audit qua Spring Batch listener

Spring Batch có các callback theo vòng đời job/step. Với **Spring Batch 5.x**, `JobExecutionListener` hỗ trợ `beforeJob` và `afterJob`; `StepExecutionListener` hỗ trợ `beforeStep` và `afterStep`. Đây là nơi thuận tiện để ghi audit cấp job/step sau khi framework đã tạo metadata.

```text
Scheduler / REST / CLI
        |
        v
   JobLauncher
        |
        v
  JobExecution
        |
        +-- beforeJob()  -> audit JOB_STARTED (nếu cần)
        |
        +-- Step A ----- Step B ----- Step C
        |
        +-- afterJob()   -> audit JOB_FINISHED
                             |
                             v
                     bảng audit của ứng dụng
```

Listener phù hợp với **tóm tắt vòng đời**. Khi cần audit một hành động nghiệp vụ chính xác như `PAYMENT_ACCEPTED`, event nên được phát tại nơi hành động đó thực sự được commit/được hệ thống đích xác nhận, không giả định `afterJob()` có đầy đủ bằng chứng.

### 4.1. Định nghĩa bảng audit event riêng

Ví dụ DDL đơn giản, minh họa cho database SQL thông dụng:

```sql
CREATE TABLE batch_audit_event (
    event_id          VARCHAR(100) PRIMARY KEY,
    job_execution_id  BIGINT NOT NULL,
    event_type        VARCHAR(40) NOT NULL,
    event_recorded_at TIMESTAMP NOT NULL,
    job_name          VARCHAR(120) NOT NULL,
    business_date     VARCHAR(10),
    batch_status      VARCHAR(30) NOT NULL,
    exit_code         VARCHAR(100),
    read_count        BIGINT NOT NULL,
    write_count       BIGINT NOT NULL,
    skip_count        BIGINT NOT NULL
);

CREATE INDEX idx_batch_audit_execution
    ON batch_audit_event (job_execution_id);
```

Đây là **bảng riêng của ứng dụng**, không phải bảng `BATCH_*` do Spring Batch quản lý. `event_id` là khóa chống insert trùng cho cùng một sự kiện logic. Một production schema có thể bổ sung `tenant_id`, `trigger_id`, `source_manifest_id`, `output_manifest_id`, `event_version`, quyền truy cập và chiến lược phân vùng dữ liệu.

`TIMESTAMP` không lưu đầy đủ thông tin timezone trong mọi hệ quản trị. Với ứng dụng đa vùng hoặc yêu cầu audit nghiêm ngặt, cần chọn kiểu timestamp thích hợp theo DB và quy ước lưu UTC xuyên suốt hệ thống.

### 4.2. Listener và service ghi audit

Ví dụ sau sử dụng `JdbcTemplate`, Spring transaction và Spring Batch 5.x:

```java
package com.example.batch.audit;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchAuditListener implements JobExecutionListener {

    private final BatchAuditService auditService;

    public BatchAuditListener(BatchAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        auditService.recordFinishedJob(jobExecution);
    }
}
```

Service thực hiện ghi audit trong transaction riêng:

```java
package com.example.batch.audit;

import java.sql.Timestamp;
import java.time.Instant;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchAuditService {

    private final JdbcTemplate jdbcTemplate;

    public BatchAuditService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFinishedJob(JobExecution execution) {
        long readCount = execution.getStepExecutions().stream()
            .mapToLong(StepExecution::getReadCount)
            .sum();

        long writeCount = execution.getStepExecutions().stream()
            .mapToLong(StepExecution::getWriteCount)
            .sum();

        long skipCount = execution.getStepExecutions().stream()
            .mapToLong(step ->
                step.getReadSkipCount()
                + step.getProcessSkipCount()
                + step.getWriteSkipCount())
            .sum();

        String eventId = "job-" + execution.getId() + "-finished";
        String businessDate = execution.getJobParameters()
            .getString("businessDate");

        jdbcTemplate.update("""
            INSERT INTO batch_audit_event (
                event_id, job_execution_id, event_type, event_recorded_at,
                job_name, business_date, batch_status, exit_code,
                read_count, write_count, skip_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            eventId,
            execution.getId(),
            "JOB_FINISHED",
            Timestamp.from(Instant.now()),
            execution.getJobInstance().getJobName(),
            businessDate,
            execution.getStatus().name(),
            execution.getExitStatus().getExitCode(),
            readCount,
            writeCount,
            skipCount
        );
    }
}
```

Gắn listener vào job:

```java
@Bean
Job importPaymentsJob(JobRepository jobRepository,
                      Step importPaymentsStep,
                      BatchAuditListener auditListener) {
    return new JobBuilder("importPaymentsJob", jobRepository)
        .listener(auditListener)
        .start(importPaymentsStep)
        .build();
}
```

Ví dụ minh họa cách tổ chức tách listener và service. `@Transactional(REQUIRES_NEW)` có hiệu lực khi gọi từ một Spring bean khác thông qua proxy, như listener gọi sang `BatchAuditService`. Nó giúp thao tác ghi audit dùng transaction riêng trong ngữ cảnh cấu hình transaction manager phù hợp; không có nghĩa event và mọi side effect của batch được commit nguyên tử với nhau.

**Các giới hạn quan trọng của mẫu trên:**

1. `afterJob()` là callback trong tiến trình. Nếu JVM/Pod bị kill đột ngột, callback có thể **không chạy**. Một hệ thống có yêu cầu audit đầy đủ cần reconciliation job để phát hiện execution kết thúc bất thường hoặc thiếu event.
2. Nếu audit database không khả dụng, `jdbcTemplate.update()` có thể thất bại. Cần chính sách rõ ràng: đánh dấu cảnh báo và thử ghi bù, đẩy qua outbox/queue bền vững, hoặc coi thiếu audit là lỗi nghiêm trọng theo yêu cầu nghiệp vụ. Đừng nuốt lỗi một cách im lặng.
3. `eventId` được tính từ `jobExecutionId` giúp phát hiện ghi lặp. Nếu callback bị chạy lại với cùng execution, `INSERT` thứ hai có thể vi phạm primary key. Trong production, hãy triển khai lệnh insert idempotent/upsert thích hợp với dialect, hoặc xử lý duplicate-key theo đúng hợp đồng.
4. Tổng counter qua mọi `StepExecution` là số tổng hợp **hoạt động step**, có thể bao gồm nhiều giai đoạn xử lý cùng item. Nó không mặc nhiên là số bản ghi nghiệp vụ duy nhất đã được xử lý. Nếu job có nhiều step đọc một record ở các giai đoạn khác nhau, tổng `readCount` có thể lớn hơn số nguồn duy nhất.
5. Việc ghi audit một event `JOB_FINISHED` không tạo lịch sử cho các thay đổi trung gian. Nếu cần audit đầy đủ từng transition hoặc business event, thêm event tại các mốc tương ứng.
6. `JobExecution` của Spring Batch 5.x sử dụng API/package khác một số kiểu của Spring Batch 6.x. Điều chỉnh imports và cấu hình theo major version thực tế; không trộn code của các phiên bản.

### 4.3. Audit ở cấp step

Nếu cần biết chính xác step nào phát sinh skip hoặc output nào được tạo, sử dụng `StepExecutionListener` để ghi kết quả riêng:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepAuditListener implements StepExecutionListener {
    private final StepAuditService auditService;

    public StepAuditListener(StepAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        auditService.recordStepResult(stepExecution);
        return null; // không thay đổi ExitStatus hiện có
    }
}
```

`StepAuditService` ở đây là service ứng dụng do người học triển khai, không phải class có sẵn của Spring Batch. Một event cấp step có thể gồm `stepExecutionId`, `stepName`, `jobExecutionId`, read/write/filter/skip/rollback counts và output artifact tương ứng. Với `afterStep`, trả `null` có nghĩa listener không đề xuất thay đổi exit status của step.

Trong hệ thống cần audit từng item bị từ chối, có thể dùng listener skip hoặc ghi vào bảng rejected-records riêng. Nên ghi **mã lỗi và khóa bản ghi** thay vì sao chép toàn bộ dữ liệu nhạy cảm của item vào log/audit.

## 5. Audit sự kiện nghiệp vụ và tính nhất quán của transaction

Một `JobExecution` hoàn tất chưa chắc bằng việc tác động bên ngoài đã được xác nhận. Hãy xét step gửi thanh toán:

```text
Reader -> Processor -> Payment API -> Database update
```

Nếu Payment API đã nhận yêu cầu nhưng tiến trình chết trước khi database commit, Spring Batch có thể ghi nhận step thất bại hoặc mất cập nhật metadata cuối. Trong khi đó phía Payment API có thể đã thực hiện tác động. Chỉ nhìn `BatchStatus` không đủ để khẳng định một giao dịch đã hay chưa được xử lý.

Với yêu cầu audit thực chất, cần lưu các định danh tương quan như `paymentRequestId`, `idempotencyKey`, mã phản hồi bên ngoài và thời điểm xác nhận. Các thiết kế hữu ích gồm:

- **Transactional outbox:** ghi dữ liệu nghiệp vụ và sự kiện cần phát trong cùng transaction database, sau đó publisher chuyển event ra ngoài; cho phép retry an toàn và đối soát khi publisher lỗi.
- **Idempotency key:** cùng yêu cầu nghiệp vụ có định danh cố định, giúp hệ thống đích nhận ra yêu cầu gửi lại.
- **Inbox/deduplication:** consumer ghi nhận message đã xử lý để tránh áp dụng tác động nhiều lần.
- **Output manifest:** sau khi output được ghi và xác nhận, tạo manifest chứa tên/version/checksum và số bản ghi, liên kết manifest với execution.
- **Reconciliation:** định kỳ so sánh bản ghi audit, metadata batch và dữ liệu đích để phát hiện thiếu hoặc sai lệch.

Không có kỹ thuật nào làm cho **mọi side effect ngoài transaction** tự động rollback cùng `JobRepository`. Audit phải mô tả trung thực trạng thái biết được, kể cả `UNKNOWN`/“đang chờ đối soát”, thay vì suy đoán từ một flag `COMPLETED`.

## 6. Phân biệt trạng thái job và trạng thái kỳ nghiệp vụ

Trạng thái `BatchStatus` là thuộc tính của **một execution**, còn “kỳ ngày 16/11 đã được đối soát xong” là trạng thái nghiệp vụ có thể liên quan đến nhiều execution.

Ví dụ:

```text
businessDate=2026-11-16

  JobInstance #302
      JobExecution #517  FAILED
      JobExecution #519  COMPLETED (restart)

  Audit nghiệp vụ:
      Kỳ 2026-11-16 = SETTLED
      finalExecutionId = 519
      outputManifestId = settlement-20261116-v1
```

Để tạo bảng tổng hợp theo ngày, không nên đếm `COMPLETED` theo từng row execution rồi tự suy ra “mỗi ngày một lần xử lý”. Có thể một kỳ được restart, chạy bù hoặc được xử lý thành nhiều partition. Cần một khóa nghiệp vụ rõ ràng và tiêu chí “đã công nhận kết quả” độc lập với số lần framework đã chạy.

Một bảng tình trạng kỳ dữ liệu có thể chứa:

```text
business_date | region | settlement_status | final_execution_id
2026-11-16    | HCM    | SETTLED           | 519
2026-11-16    | HN     | NEEDS_REVIEW      | 522
```

Bảng này khác metadata Batch: ứng dụng định nghĩa khi nào một kỳ đủ điều kiện `SETTLED`. Có thể dùng workflow phê duyệt, kiểm tra số tiền hoặc đối soát hệ thống ngoài trước khi công nhận kết quả.

## 7. Audit khi retry, skip, fail và restart

### 7.1. Retry

Trong chunk-oriented step, một item có thể được thử nhiều lần do lỗi tạm thời. Metadata cho biết thông tin tổng hợp như rollback count, nhưng không mặc nhiên lưu đầy đủ từng lần gọi API hoặc mỗi lần retry. Nếu cần kiểm toán các lần thử, hãy ghi sự kiện với `attemptNumber` hoặc mã yêu cầu, rồi liên kết với kết quả cuối. Không giả định mỗi lần retry tạo một `JobExecution` mới; retry thường nằm bên trong execution hiện tại.

### 7.2. Skip

Skip count chỉ cho biết số item bị bỏ qua theo cơ chế lỗi. Nếu cần giải thích *vì sao* và *item nào*, lưu vào bảng rejected items riêng:

```text
job_execution_id | step_execution_id | record_key | reason_code
517              | 8301              | PAY-0091   | INVALID_IBAN
517              | 8301              | PAY-0204   | DUPLICATE_REFERENCE
```

Không lưu số tài khoản đầy đủ, dữ liệu cá nhân hoặc payload nhạy cảm nếu chỉ cần mã bản ghi và mã lỗi. Có thể dùng token/hash ổn định phù hợp với chính sách bảo mật để liên kết sang hệ thống nguồn được phân quyền.

### 7.3. Job thất bại

Audit một execution thất bại nên ghi rõ:

- `jobExecutionId` và kỳ nghiệp vụ.
- `BatchStatus=FAILED`, `ExitStatus` và bước gây lỗi nếu xác định được.
- Thời gian thất bại; các bước đã hoàn thành trước đó.
- Các bộ đếm đã được commit/ghi nhận, tệp tạm hoặc dữ liệu trung gian đã sinh.
- Hành động tiếp theo: `RETRY_SCHEDULED`, `RESTART_PENDING`, `MANUAL_REVIEW`, `ABANDONED` theo mô hình riêng của ứng dụng.

Một execution lỗi không đồng nghĩa mọi side effect được rollback. Audit cần mô tả những gì thực sự đã commit hoặc đã được hệ thống ngoài chấp nhận.

### 7.4. Restart

Với restart đúng nghĩa, `JobInstance` có thể được giữ nguyên nhưng `JobExecution` thay đổi. Nên liên kết các event audit bằng `jobInstanceId` hoặc business key và thêm `restartOfExecutionId` khi nghiệp vụ cần truy dấu chuỗi thử nghiệm.

**Tránh thay identifying `JobParameters` chỉ để ép một lần chạy mới** khi mục tiêu là tiếp tục từ checkpoint. Điều đó làm Spring Batch tạo instance khác, mất mối liên hệ restart trong framework và có thể xử lý lại dữ liệu đã commit.

## 8. Bằng chứng về input và output

Để trả lời “batch ngày đó dùng đúng file nào?”, tên file thường chưa đủ: file có thể bị thay thế nhưng giữ nguyên tên.

### 8.1. Manifest đầu vào

Tối thiểu có thể lưu:

```json
{
  "sourceSystem": "bank-feed",
  "sourceObjectId": "payments/2026-11-16/input.csv",
  "sourceVersion": "v-1024",
  "contentSha256": "<hexadecimal-sha256>",
  "byteLength": 487226,
  "businessDate": "2026-11-16",
  "recordCount": 10000
}
```

Giá trị `contentSha256` trong ví dụ là chỗ dành cho hash thực tế được tính từ bytes của file; **không** ghi chuỗi placeholder vào audit production. Nếu file nằm trên object storage có versioning, lưu object key cùng version ID để có thể truy xuất đúng phiên bản nguồn. Hash cho phép phát hiện dữ liệu thay đổi, nhưng không chứng minh người gửi hợp lệ nếu thiếu cơ chế xác thực nguồn hoặc chữ ký phù hợp.

### 8.2. Manifest đầu ra

Khi job ghi file báo cáo hoặc xuất dữ liệu sang hệ thống khác, record audit có thể liên kết đến `outputManifestId`, `outputPath`, số bản ghi, checksum, thời điểm publish và trạng thái xác nhận.

```text
JOB_COMPLETED
  jobExecutionId=519
  businessDate=2026-11-16
  outputManifestId=settlement-20261116-v1
  outputRecordCount=9988
  outputSha256=...
  publishedAt=2026-11-17T02:05:31Z
```

Nếu job ghi nhiều file hoặc partition, dùng manifest liệt kê từng artifact. Nếu output được tạo dở rồi job lỗi, giữ trạng thái `PARTIAL` hoặc `NOT_PUBLISHED` và không gắn nhãn “đã xuất bản” cho file chưa được xác nhận. Audit nên phân biệt **tạo file**, **commit kết quả** và **publish cho bên tiêu thụ**.

## 9. Timestamp và đồng bộ thời gian

Audit thường phải so sánh log giữa scheduler, Spring Batch, database và hệ thống bên ngoài. Thiết lập rõ quy ước thời gian để tránh đọc sai:

- Sử dụng **UTC cho timestamp lưu trữ và trao đổi liên hệ thống** khi có thể; chuyển sang múi giờ nghiệp vụ tại giao diện/report.
- Ghi `businessDate` hoặc business window riêng; **ngày nghiệp vụ không đồng nhất với ngày của `createdAt` hay `startedAt`**.
- Với Java, ưu tiên `Instant` hoặc kiểu thời gian có offset khi truyền event; các field thời gian của Spring Batch có thể dùng `LocalDateTime` tùy phiên bản và không tự mang timezone.
- Đồng bộ đồng hồ host/container; khi có lệch clock, thứ tự timestamp giữa hệ thống có thể không đáng tin tuyệt đối.
- Không suy diễn `END_TIME = null` luôn nghĩa là “đang chạy”: tiến trình có thể chết trước khi cập nhật metadata. Cần đối chiếu trạng thái hạ tầng và heartbeat/health khi thiết kế màn hình vận hành.

Ví dụ mốc thời gian cho batch xử lý dữ liệu **ngày trước đó**:

```text
businessDate = 2026-11-16
scheduledAt  = 2026-11-17T02:00:00+07:00
startedAt    = 2026-11-16T19:00:01Z
finishedAt   = 2026-11-16T19:05:31Z
```

Hai cách ghi `scheduledAt` và `startedAt` cùng mô tả các thời điểm theo hai múi giờ khác nhau; nếu muốn so sánh duration, chuyển về một quy ước thống nhất.

## 10. Audit khác monitoring metrics và logs như thế nào?

| Khía cạnh | Batch metadata | Application log | Metrics/traces | Audit trail |
| --- | --- | --- | --- | --- |
| Mục đích | Framework execution/restart | Chẩn đoán chi tiết | Giám sát hiệu năng và phân tán | Giải trình sự kiện và kết quả |
| Độ chi tiết | Job/step/counters/context | Dòng log tự do | Counter, histogram, span | Event có cấu trúc và khóa nghiệp vụ |
| Vòng đời | Do repository lưu và dọn theo policy | Theo log retention | Theo monitoring backend | Theo retention/kiểm soát audit riêng |
| Tính ổn định schema | Phụ thuộc Spring Batch | Dễ đổi theo log format | Phụ thuộc instrumentation | Nên version schema và kiểm soát thay đổi |
| Giá trị chứng minh | Trạng thái xử lý | Bổ sung nguyên nhân | Dấu hiệu bất thường | Bằng chứng nối sự kiện với dữ liệu nghiệp vụ |

Logs hữu ích nhưng thường không có schema bất biến, có thể bị rotate và không bảo đảm đầy đủ trong trường hợp crash. Metrics hỗ trợ phát hiện SLA chậm hoặc số skip tăng, nhưng thường **không thích hợp lưu mã kỳ dữ liệu/record ID** dưới dạng label vì độ đa dạng giá trị quá lớn gây cardinality cao. Audit nên lưu các định danh chi tiết trong bảng/event store; metrics chỉ dùng nhãn có cardinality thấp như tên job, nhóm kết quả hoặc môi trường.

### Correlation ID

Nên mang một `correlationId` xuyên suốt scheduler → batch launcher → step → API/DB downstream. Khi log, có thể đưa `jobExecutionId` và `correlationId` vào MDC cho đúng thread thực thi. Nhưng batch có thể xử lý song song, dùng async task executor hoặc partitioning, nên MDC không tự truyền giữa các thread. Cần chủ động propagate context theo cơ chế executor/tracing phù hợp.

## 11. Lưu trữ, bảo mật và quyền truy cập metadata

Các bảng `BATCH_*` có thể chứa `JobParameters`, exception message, context và tên tài nguyên. Chúng có thể vô tình lộ đường dẫn nội bộ, ID khách hàng, chuỗi truy vấn hoặc payload nếu ứng dụng ghi thiếu kiểm soát.

### 11.1. Giảm dữ liệu nhạy cảm

- Không đưa password, secret, access token hoặc dữ liệu cá nhân không cần thiết vào `JobParameters`, `ExecutionContext` hay `EXIT_MESSAGE`.
- Ghi `recordKey`/mã tham chiếu hoặc token thay vì toàn bộ payload bị lỗi.
- Redact stack trace và thông điệp lỗi trước khi xuất cho người dùng không đủ quyền.
- Phân loại dữ liệu audit và thiết kế quyền truy cập: vận hành có thể xem trạng thái, bộ phận kiểm toán có thể xem kỳ và kết quả, đội kỹ thuật được phép xem stack trace chi tiết theo quyền.

### 11.2. Quy tắc retention

Không nên coi metadata Spring Batch là kho lưu vĩnh viễn. `JobRepository` lớn dần theo số lần chạy, số step và context; việc lưu mãi có thể làm truy vấn chậm và tăng chi phí backup. Ngược lại, nếu xóa metadata quá sớm, các job chưa hoàn tất có thể mất khả năng restart hoặc chuỗi bằng chứng cần điều tra.

Một chính sách hợp lý cần phân biệt:

1. **Dữ liệu chạy còn cần restart:** giữ nguyên repository và context cho tới khi kết thúc vòng đời nghiệp vụ.
2. **Metadata lịch sử vận hành:** giữ theo SLA vận hành và chính sách housekeeping, có thể trích xuất báo cáo tổng hợp trước khi dọn.
3. **Audit trail và artifact theo nghĩa vụ lưu trữ:** lưu ở kho riêng có phân quyền, retention, backup và cơ chế kiểm tra tính toàn vẹn phù hợp.

Thời hạn cụ thể phụ thuộc yêu cầu pháp lý, hợp đồng và chính sách tổ chức; không có một con số ngày/tháng áp dụng cho mọi batch. Nếu xóa dữ liệu, hãy thực hiện bằng quy trình được thiết kế cho quan hệ giữa job instance, execution, step và context; tránh chạy các lệnh SQL xóa tùy tiện trên repository đang hoạt động.

### 11.3. Độ tin cậy của audit trail

Đối với hệ thống cần mức bảo đảm cao, có thể áp dụng:

- Quyền ghi append-only ở lớp ứng dụng và phân tách quyền đọc, ghi, quản trị.
- Ghi event vào kho lưu trữ bền vững, backup định kỳ và diễn tập khôi phục.
- Trường `eventVersion`, `schemaVersion` để thay đổi hợp đồng audit có kiểm soát.
- Hash/chữ ký hoặc storage có chính sách bất biến nếu cần phát hiện can thiệp.
- Reconciliation định kỳ giữa audit events, JobRepository và dữ liệu nghiệp vụ.

Các biện pháp trên phải được thiết kế như một phần của kiến trúc, vì chỉ thêm một trường `createdAt` hoặc một listener không tạo ra bằng chứng audit chống sửa đổi.

## 12. Phát hiện metadata thiếu hoặc trạng thái không nhất quán

Không phải lỗi nào cũng kết thúc bằng `BatchStatus.FAILED` được ghi sạch vào repository. Một tiến trình có thể mất điện hoặc bị kill trong lúc execution đang `STARTED`; audit callback `afterJob` chưa chạy, `END_TIME` chưa được cập nhật.

Một **reconciliation process** nên định kỳ:

1. Liệt kê các kỳ dữ liệu đáng lẽ phải xử lý từ lịch nghiệp vụ hoặc scheduler.
2. Đối chiếu kỳ đó có `JobInstance`/`JobExecution` nào hay chưa.
3. Kiểm tra các execution quá thời gian dự kiến nhưng vẫn thể hiện `STARTED`/`STARTING`, cùng tình trạng process/worker thực tế.
4. Đối chiếu `JOB_FINISHED` audit event và output manifest; phát hiện event còn thiếu, file chưa publish hoặc dữ liệu đích không khớp.
5. Tạo cảnh báo hoặc nhiệm vụ đối soát thủ công; chỉ restart/rerun theo chính sách đã duyệt.

Ví dụ báo cáo:

| Kỳ dữ liệu | JobExecution cuối | Audit event | Output | Kết luận |
| --- | --- | --- | --- | --- |
| 2026-11-14 | `COMPLETED` | Có `JOB_FINISHED` | Manifest hợp lệ | Đã đối soát |
| 2026-11-15 | `FAILED` | Có `JOB_FINISHED` | Chưa publish | Cần restart hoặc xử lý lỗi |
| 2026-11-16 | `STARTED` quá SLA | Chưa có event cuối | Không rõ | Cần kiểm tra worker, không tự kết luận đã thất bại |
| 2026-11-17 | Không có execution | Không có | Không có | Có thể mất trigger/scheduler |

**Không tự ý sửa hàng `BATCH_JOB_EXECUTION.STATUS` thành `FAILED` để “dọn màn hình monitoring”.** Spring Batch có cơ chế và API vận hành riêng; mọi thao tác phục hồi metadata cần đánh giá ảnh hưởng đến restart.

## 13. Kiểm thử metadata và audit

Với audit, chỉ unit test format của event là chưa đủ. Cần một số integration test chứng minh dữ liệu đã được ghi bền vững và liên kết đúng execution.

### 13.1. Unit test

Kiểm tra logic dựng audit payload từ `JobExecution`/`StepExecution` giả lập hoặc fixture. Ví dụ: `businessDate`, `jobExecutionId`, `readCount`, `writeCount`, `skipCount`, `status` và idempotency event ID được tính đúng.

Unit test nhanh, phù hợp để bao phủ tình huống `JobParameters` thiếu, step không có item hoặc exit code tùy chỉnh. Nó không chứng minh giao dịch SQL hay listener được gắn vào job thật.

### 13.2. Integration test

Chạy job/step thực với database test, rồi kiểm tra:

- `JobExecution` và `StepExecution` tồn tại trong `JobRepository` với ID và trạng thái kỳ vọng.
- Bảng `batch_audit_event` chứa đúng `job_execution_id`, `event_type` và kết quả sau callback.
- Bảng nghiệp vụ/file output có dữ liệu thực như fixture dự kiến.
- Khi job `FAILED`, audit ghi đúng failure status; khi restart, mỗi `JobExecution` có dấu vết riêng và có thể nối về một kỳ nghiệp vụ.
- Ghi trùng một event logic được xử lý idempotent theo thiết kế.
- Nếu service audit tạm thời không khả dụng, hệ thống có cơ chế phát hiện và xử lý thiếu audit như đã định nghĩa.

Ví dụ một assertion sau integration test, sử dụng `JdbcTemplate` và biến `execution` từ `JobLauncherTestUtils` của Spring Batch 5.x:

```java
Long auditRows = jdbcTemplate.queryForObject(
    """
    SELECT COUNT(*)
      FROM batch_audit_event
     WHERE job_execution_id = ?
       AND event_type = 'JOB_FINISHED'
    """,
    Long.class,
    execution.getId()
);

assertThat(auditRows).isEqualTo(1L);
```

Với test cần xác minh nội dung, tiếp tục truy vấn `batch_status`, `business_date`, `read_count`, `write_count`, `skip_count` thay vì chỉ đếm event. Test repository phải nằm trong database dành cho test, không sử dụng dữ liệu production. Khi test restart, giữ metadata và output giữa các lần thực thi của cùng test case rồi cleanup sau khi hoàn tất.

## 14. Các lỗi thiết kế audit thường gặp

| Hiện tượng | Vấn đề thực chất | Cách xử lý |
| --- | --- | --- |
| Chỉ lưu `COMPLETED` và thời gian chạy | Thiếu kỳ dữ liệu, nguồn input và output đã công nhận | Ghi business key, input/output manifest và định danh execution |
| Dùng `ExecutionContext` làm nhật ký tất cả các thao tác | Context là snapshot phục vụ restart và có thể bị cập nhật đè | Lưu events vào audit store riêng |
| Gắn UUID identifying mới cho mọi restart | Tạo `JobInstance` mới, khó nối chuỗi và có thể xử lý trùng | Thiết kế identifying parameters theo kỳ, dùng restart đúng nghĩa |
| Tin rằng `WRITE_COUNT` bằng số giao dịch đích xác nhận | Counter chỉ phản ánh logic writer/framework | Đối chiếu database/output/external acknowledgment |
| Chỉ ghi audit bằng `afterJob` | Crash có thể bỏ qua callback | Thêm reconciliation, event từ điểm commit hoặc outbox khi cần |
| Nuốt exception khi ghi audit | Thiếu dấu vết mà không ai biết | Định nghĩa chính sách alert/retry/reconcile hoặc fail theo yêu cầu |
| Lưu toàn bộ payload lỗi và token trong context | Rủi ro lộ dữ liệu qua metadata/log | Giảm dữ liệu, redaction, phân quyền |
| Xóa metadata ngay sau job | Có thể mất lịch sử và khả năng restart | Tách retention vận hành với audit và giữ dữ liệu cần thiết |
| Dùng `STARTED` lâu là bằng chứng job còn sống | Tiến trình có thể đã chết không kịp cập nhật status | Kiểm tra heartbeat, worker và reconciliation |
| Tổng read count qua nhiều step thành “số record duy nhất” | Cùng item có thể được đọc nhiều lần ở các step | Dùng metric nghiệp vụ ở ranh giới dữ liệu phù hợp |
| Ghi log audit không có correlation ID | Khó nối scheduler, worker, API và batch execution | Truyền business key + execution ID + correlation ID xuyên suốt |
| Truy vấn trực tiếp schema của sai version | Tên cột và kiểu tham số khác giữa các major version | Dùng `JobExplorer` hoặc DDL đúng version |

## 15. Mẫu hồ sơ audit cho một batch execution

Một báo cáo audit dễ đọc thường không phải bản dump các bảng kỹ thuật, mà là một hồ sơ tổng hợp có thể truy về dữ liệu gốc:

```text
Job                     : importPaymentsJob
Business date           : 2026-11-16
Region                  : HCM
Source system           : bank-feed
Source object           : payments/2026-11-16/input.csv (version v-1024)
Source checksum         : sha256:<giá trị băm thực tế>

Job instance ID         : 302
Job execution ID        : 519
Trigger                 : nightly-scheduler
Correlation ID          : import-payments-20261116-hcm
Started at              : 2026-11-16T19:00:01Z
Finished at             : 2026-11-16T19:05:31Z
Batch status            : COMPLETED
Exit code               : COMPLETED

Read count              : 10000
Write count             : 9988
Filter count            : 10
Process skip count      : 2

Business accepted count : 9988
Business rejected count : 12
Output manifest         : settlement-20261116-hcm-v1
Audit event             : job-519-finished
Audit reconciliation    : VERIFIED
```

Các giá trị chỉ minh họa định dạng báo cáo. Trong hệ thống thật, những trường như `Business accepted count`, `Output manifest` hoặc `Audit reconciliation` phải được **tính/đối chiếu từ dữ liệu nghiệp vụ**, không suy ra mặc định từ `BatchStatus`. Chẳng hạn `filterCount` và skip count phản ánh hai cơ chế khác nhau; số rejected nghiệp vụ cần được định nghĩa rõ và có thể không bằng tổng hai bộ đếm này ở mọi job.

Hồ sơ có khóa liên kết giúp người điều tra đi từ một kỳ nghiệp vụ đến `JobExecution`, mở chi tiết từng `StepExecution`, đối chiếu file nguồn/đầu ra và xác nhận lý do một lần restart hoặc chạy bù được thực hiện.

## 16. Nguyên tắc áp dụng

1. **Dùng metadata Spring Batch để biết lịch sử execution và khả năng restart.** Nguồn chính là `JobRepository`, không phải log tự viết thay thế hoàn toàn.
2. **Gắn business key vào metadata đúng cách.** `businessDate`, `region`, input version và identity của job phải nhất quán giữa các lần chạy.
3. **Không nhầm counter với kết quả nghiệp vụ đã đối soát.** Audit kết quả phải dựa trên dữ liệu thực, manifest và xác nhận của hệ thống đích.
4. **Ghi sự kiện audit ngoài các bảng `BATCH_*` khi cần lịch sử nghiệp vụ độc lập.** Dùng listener cho lifecycle; dùng sự kiện tại điểm commit/outbox cho những tác động nghiệp vụ cần bảo đảm cao.
5. **Thiết kế cho trường hợp lỗi và crash.** Có idempotency, quyền truy cập, retention và reconciliation để phát hiện audit event bị thiếu.
6. **Giữ thông tin đủ truy vết nhưng không làm lộ dữ liệu nhạy cảm.** Chọn khóa tham chiếu, mã lỗi và checksum thay cho payload không cần thiết.

Khi được tổ chức đúng, metadata cho audit biến một lần chạy batch từ dòng trạng thái `COMPLETED`/`FAILED` thành một lịch sử có thể kiểm chứng: **dữ liệu nào được xử lý, bằng phiên bản chương trình nào, qua các bước nào, kết quả nào đã được ghi nhận và còn điểm nào phải đối soát**.

## Tài liệu tham khảo

- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng và quan hệ lưu `JobInstance`, `JobExecution`, `StepExecution`, parameters và context.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): định nghĩa job, listeners và các thành phần lifecycle.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): cơ chế repository và quản lý metadata execution.
- [Spring Batch Reference — JobExplorer](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): các API truy vấn metadata Batch.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): phân biệt giám sát execution và tín hiệu runtime.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundary và `@Transactional`.
