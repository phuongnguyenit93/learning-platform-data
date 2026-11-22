# Audit lần launch của Spring Batch Job từ scheduler

## 1. Bài toán: biết mỗi lần scheduler đã yêu cầu chạy job như thế nào

Trong hệ thống chạy batch theo lịch, câu hỏi vận hành thường không chỉ là “job đã thành công chưa?” mà còn là:

- 01:00 hôm nay scheduler **có phát yêu cầu chạy** hay không?
- Yêu cầu đến từ cron, người vận hành, thao tác chạy bù hay scheduler bên ngoài?
- Scheduler yêu cầu xử lý kỳ dữ liệu nào và gửi tham số gì?
- Yêu cầu đó được Spring Batch chấp nhận, bị từ chối vì job đã hoàn tất, bị từ chối vì đang chạy hay thất bại trước khi tạo execution?
- Nếu được chấp nhận, yêu cầu tương ứng với `JobExecution` nào? Execution đó cuối cùng `COMPLETED` hay `FAILED`?
- Khi nhận hai trigger cho cùng kỳ, hệ thống đã ghi nhận cả hai yêu cầu và xử lý trùng ra sao?

Đó là nội dung của **audit lần launch**: lưu lại dấu vết mỗi lần một thành phần chủ động yêu cầu Spring Batch khởi chạy job, bao gồm cả trường hợp **không có JobExecution nào được tạo**.

Bài học thuộc nhóm *Scheduling* trong *Spring Batch Core Processing*. Sau khi học, bạn có thể thiết kế mô hình audit, triển khai một lớp điều phối gọi `JobLauncher`, liên kết audit với metadata của Spring Batch, phân biệt kết quả khởi chạy với kết quả xử lý và kiểm thử các kịch bản trùng lịch, restart, thất bại hoặc mất kết nối.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC và PostgreSQL. Các ý tưởng vẫn áp dụng khi dùng Quartz, Kubernetes CronJob hoặc công cụ điều phối khác.

## 2. Ba tầng sự kiện cần phân biệt

Một **scheduler trigger** là sự kiện thời gian hoặc thao tác phát lệnh; một **launch attempt** là lần ứng dụng gọi cơ chế khởi chạy; một **JobExecution** là lần thực thi đã được Spring Batch ghi nhận.

```text
                  Lịch cron 01:00 / yêu cầu chạy thủ công
                                 |
                                 v
                           Trigger event
                                 |
                                 v
                    Launch attempt (audit_id)
                    status = REQUESTED
                                 |
                                 v
                       JobLauncher.run(...)
                             /       \
                            /         \
                       Bị từ chối   Được chấp nhận
                           |           |
                           v           v
                   Audit rejection  JobExecution ID
                                       |
                                       v
                                   Job / Steps
                                       |
                                       v
                              COMPLETED / FAILED
                                       |
                                       v
                           Audit kết quả thực thi
```

Ví dụ scheduler gửi lại đúng tham số của một `JobInstance` đã hoàn tất. Spring Batch thường ném `JobInstanceAlreadyCompleteException`. **Có launch attempt nhưng không có JobExecution mới**. Nếu chỉ quan sát các bảng `BATCH_JOB_EXECUTION`, bạn có thể bỏ sót yêu cầu bị từ chối này.

Ngược lại, một lần launch hợp lệ có thể tạo một `JobExecution` rồi thực thi thất bại do dữ liệu. Khi đó **launch đã được chấp nhận**, nhưng **job thất bại**. Nếu hệ thống audit chỉ lưu một cờ `success=true/false`, hai sự kiện sẽ bị nhầm lẫn.

| Cấp độ | Đối tượng quan sát | Ví dụ |
| --- | --- | --- |
| Trigger | Một lần lịch đến hạn hoặc một yêu cầu vận hành | Cron 01:00, lệnh backfill cho ngày D |
| Launch attempt | Một lần ứng dụng yêu cầu chạy job | Yêu cầu được ghi nhận, được chấp nhận hoặc bị từ chối |
| JobInstance | Một kỳ xử lý logic | `dailySalesJob` + `businessDate=D` |
| JobExecution | Một lần thực thi của instance | Lần đầu `FAILED`, lần restart `COMPLETED` |
| StepExecution | Tình trạng và số đếm từng step | Đọc 5.000 bản ghi, ghi 4.990 bản ghi |

Một `JobInstance` có thể có nhiều `JobExecution` do restart. Một JobInstance cũng có thể gắn với nhiều launch attempt, kể cả các attempt bị từ chối. Vì vậy không được dùng `jobInstanceId` hoặc `jobExecutionId` làm khóa duy nhất của bản ghi audit yêu cầu launch.

## 3. Tận dụng metadata Spring Batch nhưng bổ sung thông tin scheduler

Spring Batch lưu metadata trong các bảng chuẩn như:

- `BATCH_JOB_INSTANCE`: tên job và danh tính instance.
- `BATCH_JOB_EXECUTION`: thời điểm, trạng thái, kết quả của mỗi execution.
- `BATCH_JOB_EXECUTION_PARAMS`: tham số được gắn với execution, bao gồm cờ identifying.
- `BATCH_STEP_EXECUTION`: tình trạng thực thi từng step.
- Các bảng execution context: trạng thái cần thiết để restart và phục hồi.

Metadata rất hữu ích để trả lời **job đã chạy gì**. Tuy nhiên, chúng không đủ để trả lời toàn bộ câu hỏi **scheduler đã cố gắng launch gì**.

Ví dụ một job đã `COMPLETED` và scheduler phát yêu cầu giống hệt vào ngày hôm sau: Batch từ chối; repository không nhất thiết tạo thêm execution. Từ metadata execution thuần túy, bạn không thể biết có thêm trigger nào bị từ chối.

Bảng audit bổ sung các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `audit_id` | ID duy nhất cho **mỗi lần yêu cầu launch** |
| `trigger_source` | `SCHEDULED`, `MANUAL`, `BACKFILL`, `EXTERNAL`... |
| `trigger_key` | Mã kỳ lịch hoặc mã sự kiện, có thể trùng giữa các lần gửi lại |
| `job_name` | Tên Job Spring Batch |
| `business_date` | Kỳ nghiệp vụ yêu cầu xử lý, làm ví dụ cho identifying parameter |
| `requested_at` | Thời điểm ứng dụng nhận/yêu cầu launch |
| `launch_outcome` | `REQUESTED`, `ACCEPTED`, `ALREADY_RUNNING`, `ALREADY_COMPLETED`... |
| `job_execution_id` | ID JobExecution khi được tạo; có thể `NULL` |
| `launch_error_code` | Mã phân loại lỗi khi chưa thể xác nhận launch |
| `batch_status` / `exit_code` | Kết quả thực thi cuối cùng, nếu đã biết |
| `updated_at` | Thời điểm bản ghi audit được cập nhật gần nhất |

Các thông tin khác có thể bổ sung theo nhu cầu: `scheduler_name`, `tenant_id`, `environment`, `requested_by`, `correlation_id`, `scheduled_at`, `received_at`, `hostname` và `trace_id`.

**Không đồng nhất `scheduled_at` với `requested_at`.** Scheduler có thể đến hạn lúc 01:00 nhưng ứng dụng nhận sự kiện muộn lúc 01:04. Khi dùng `@Scheduled` đơn giản, phương thức được gọi không tự nhận một “planned fire time” có thẩm quyền; đừng tạo giá trị scheduled_at giả từ đồng hồ hiện tại. Nếu nguồn là Quartz hoặc một scheduler bên ngoài cung cấp thời điểm theo lịch, hãy ghi riêng giá trị đó.

## 4. Thiết kế trạng thái audit

Nên tách **kết quả gửi yêu cầu** khỏi **trạng thái xử lý job**.

### 4.1. Launch outcome

| Outcome | Ý nghĩa |
| --- | --- |
| `REQUESTED` | Đã ghi nhận yêu cầu trước khi gọi `JobLauncher` |
| `ACCEPTED` | `JobLauncher` trả về `JobExecution` hợp lệ |
| `ALREADY_COMPLETED` | Yêu cầu trùng instance đã hoàn tất |
| `ALREADY_RUNNING` | Một execution của cùng instance đang hoạt động |
| `RESTART_REJECTED` | Không thể restart instance theo cấu hình/trạng thái |
| `INVALID_PARAMETERS` | `JobParameters` không hợp lệ theo job |
| `LAUNCH_ERROR` | Có lỗi khi gọi launcher; cần xác minh có execution được tạo hay chưa |

`LAUNCH_ERROR` cố ý mang ý nghĩa **chưa xác định chắc kết quả tạo execution**. Trong một số lỗi hạ tầng hoặc timeout, phía gọi không thể suy ra chính xác repository đã ghi JobExecution hay chưa. Tránh ghi “chưa chạy” khi không có bằng chứng.

### 4.2. Batch status

`batch_status` chỉ có ý nghĩa khi có execution, ví dụ `STARTING`, `STARTED`, `COMPLETED`, `FAILED` hoặc `STOPPED`. `ExitStatus` có thể có exit code tùy biến riêng, nên nên giữ cả hai trường nếu cần điều tra luồng Batch.

Ví dụ:

| Audit ID | Launch outcome | JobExecution ID | Batch status |
| --- | --- | --- | --- |
| A-001 | `ACCEPTED` | 5001 | `COMPLETED` |
| A-002 | `ALREADY_COMPLETED` | `NULL` | `NULL` |
| A-003 | `ACCEPTED` | 5002 | `FAILED` |
| A-004 | `ACCEPTED` | 5003 | `COMPLETED` |
| A-005 | `LAUNCH_ERROR` | `NULL` | `NULL` |

Nếu A-003 và A-004 cùng tên job và cùng tham số định danh, chúng có thể là hai execution của **cùng JobInstance**. A-002 là một lần launch bị từ chối, nên không có execution mới để liên kết.

## 5. Mối quan hệ giữa trigger_key, audit_id và identifying parameters

Ba loại khóa này phục vụ ba mục đích khác nhau:

1. **`audit_id`:** một UUID được tạo cho mỗi lần ứng dụng cố gắng launch. Hai lần gửi cùng trigger vẫn có hai audit ID.
2. **`trigger_key`:** định danh sự kiện lịch hoặc kỳ dự kiến. Một event được gửi lặp có thể giữ cùng trigger key để phục vụ đối soát.
3. **`businessDate` (identifying parameter):** xác định JobInstance của Spring Batch, chẳng hạn ngày mà job thực sự phải xử lý.

Ví dụ một scheduler gửi hai lần yêu cầu xử lý cùng ngày:

```text
trigger_key = daily-sales:2026-11-15
businessDate = 2026-11-15

Attempt #1:
  audit_id = 4bc...
  launch_outcome = ACCEPTED
  jobExecutionId = 5001

Attempt #2:
  audit_id = 0d7...
  launch_outcome = ALREADY_COMPLETED
  jobExecutionId = NULL
```

Không đặt ràng buộc `UNIQUE(trigger_key)` trên bảng **audit attempt** nếu mục tiêu là ghi lại mọi lần yêu cầu. Có thể xây dựng một bảng riêng lưu **sự kiện lịch đã tiếp nhận** với unique constraint để deduplicate trigger đầu vào, nhưng đó là trách nhiệm khác.

Để liên kết execution với audit, thêm `auditId` như **non-identifying parameter**:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", businessDate.toString(), true)
    .addString("auditId", auditId, false)
    .toJobParameters();
```

Nếu `auditId` được đánh dấu identifying, mỗi lần scheduler gửi lại sẽ vô tình tạo JobInstance mới; khi đó không còn kiểm tra được cơ chế chống chạy trùng/restart cho cùng ngày.

## 6. Kiến trúc audit đáng tin cậy

Một quy trình tối thiểu:

```text
Scheduler
   |
   v
LaunchCoordinator
   |
   +--> 1. Ghi REQUESTED vào audit DB
   |          |
   |          v
   |       COMMIT
   |
   +--> 2. JobLauncher.run(job, params có auditId)
   |          |
   |          +--> Bị từ chối --> cập nhật launch outcome
   |          |
   |          +--> Trả JobExecution --> lưu execution ID
   |                                      |
   |                                      v
   |                            JobExecutionListener
   |                                      |
   |                                      v
   |                            Lưu BatchStatus cuối
   |
   v
Truy vấn & cảnh báo vận hành
```

**Ghi REQUESTED trước khi launch** là điểm quan trọng. Nếu chỉ ghi audit sau khi `JobLauncher.run(...)` trả về thành công, tất cả các lần bị từ chối hoặc lỗi trước khi trả về sẽ không được ghi nhận.

Trong ứng dụng có transaction, các thao tác ghi audit nên dùng **transaction ngắn, độc lập** với giao dịch xử lý chunk. Nếu audit được ghi trong một giao dịch lớn rồi bị rollback cùng lỗi job, chính bản ghi cần phục vụ điều tra lỗi có thể biến mất.

Tuy nhiên, hai hệ thống lưu metadata và audit không tạo thành một atomic transaction duy nhất trong ví dụ này. Sau khi repository tạo execution nhưng trước khi cập nhật audit, process có thể chết. Vì thế cần một bước **reconciliation** dựa trên `auditId` đã được lưu trong JobParameters.

## 7. Cấu trúc bảng audit (PostgreSQL)

Ví dụ lưu một dòng cho mỗi lần launch attempt:

```sql
CREATE TABLE batch_launch_audit (
    audit_id          VARCHAR(36) PRIMARY KEY,
    trigger_key       VARCHAR(160),
    trigger_source    VARCHAR(32) NOT NULL,
    job_name          VARCHAR(100) NOT NULL,
    business_date     DATE NOT NULL,
    requested_at      TIMESTAMPTZ NOT NULL,

    launch_outcome    VARCHAR(32) NOT NULL,
    job_execution_id  BIGINT,
    launch_error_code VARCHAR(80),

    batch_status      VARCHAR(20),
    exit_code         VARCHAR(128),
    updated_at        TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_batch_launch_audit_job_date
    ON batch_launch_audit (job_name, business_date, requested_at);

CREATE INDEX idx_batch_launch_audit_trigger
    ON batch_launch_audit (trigger_key);

CREATE INDEX idx_batch_launch_audit_execution
    ON batch_launch_audit (job_execution_id);
```

Ở schema này, `job_execution_id` có thể `NULL` khi launch bị từ chối hoặc chưa xác minh được kết quả. Không bắt buộc tạo foreign key sang bảng metadata Batch: audit có thể có thời hạn lưu trữ hoặc chiến lược backup khác với metadata vận hành.

Vì audit chỉ chứa một khóa nghiệp vụ mẫu `business_date`, hệ thống nhiều loại job có thể dùng bảng khác tổng quát hơn: `identifying_params_json`, `tenant_id`, `dataset_key` và version schema. Nếu lưu JSON tham số, chỉ lưu những trường được cho phép; loại bỏ mật khẩu, access token và dữ liệu cá nhân không cần thiết.

## 8. Triển khai AuditStore bằng JdbcTemplate

Ví dụ một repository riêng thực hiện ba thao tác: ghi yêu cầu, ghi kết quả launch và ghi trạng thái cuối. Các phương thức public được gọi **từ bean khác**, để `@Transactional(REQUIRES_NEW)` có hiệu lực qua Spring proxy.

```java
import java.sql.Date;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;

import org.springframework.batch.core.BatchStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class LaunchAuditStore {

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public LaunchAuditStore(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordRequested(
            String auditId,
            String triggerKey,
            String source,
            String jobName,
            LocalDate businessDate,
            Instant requestedAt) {

        jdbc.update(
            "INSERT INTO batch_launch_audit (" +
            "audit_id, trigger_key, trigger_source, job_name, " +
            "business_date, requested_at, launch_outcome, updated_at" +
            ") VALUES (?, ?, ?, ?, ?, ?, 'REQUESTED', ?)",
            auditId,
            triggerKey,
            source,
            jobName,
            Date.valueOf(businessDate),
            Timestamp.from(requestedAt),
            Timestamp.from(requestedAt)
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordLaunchOutcome(
            String auditId,
            String outcome,
            Long executionId,
            String errorCode) {

        jdbc.update(
            "UPDATE batch_launch_audit SET " +
            "launch_outcome = ?, job_execution_id = ?, " +
            "launch_error_code = ?, updated_at = ? " +
            "WHERE audit_id = ?",
            outcome,
            executionId,
            errorCode,
            Timestamp.from(clock.instant()),
            auditId
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFinished(
            String auditId,
            BatchStatus batchStatus,
            String exitCode) {

        jdbc.update(
            "UPDATE batch_launch_audit SET " +
            "batch_status = ?, exit_code = ?, updated_at = ? " +
            "WHERE audit_id = ?",
            batchStatus.name(),
            exitCode,
            Timestamp.from(clock.instant()),
            auditId
        );
    }
}
```

Ví dụ giả định ứng dụng có một `JdbcTemplate` và transaction manager đúng với datasource lưu audit. Nếu ứng dụng dùng nhiều datasource/transaction manager, cần chỉ rõ transaction manager tương ứng trong cấu hình `@Transactional`.

Bảng audit được tạo bằng migration trước khi scheduler hoạt động. Trong thiết kế **audit bắt buộc**, nếu `recordRequested` thất bại, ứng dụng không được khởi chạy job tiếp vì khi đó không còn bảo đảm ghi nhận được ý định launch. Tùy yêu cầu nghiệp vụ, hệ thống khác có thể chọn policy best-effort, nhưng phải ghi rõ ý nghĩa và rủi ro của lựa chọn đó.

## 9. Lớp điều phối launch và ghi kết quả

Tạo một service tập trung, sử dụng chung cho cron, backfill và lệnh chạy thủ công. Mỗi lần gọi sinh một `auditId`, lưu yêu cầu trước, thêm `auditId` vào JobParameters với cờ non-identifying, sau đó gọi launcher.

```java
import java.time.Clock;
import java.time.LocalDate;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BatchLaunchCoordinator {

    private static final Logger log =
        LoggerFactory.getLogger(BatchLaunchCoordinator.class);

    private final JobLauncher launcher;
    private final Job dailySalesJob;
    private final LaunchAuditStore auditStore;
    private final Clock clock;

    public BatchLaunchCoordinator(
            JobLauncher launcher,
            @Qualifier("dailySalesJob") Job dailySalesJob,
            LaunchAuditStore auditStore,
            Clock clock) {

        this.launcher = launcher;
        this.dailySalesJob = dailySalesJob;
        this.auditStore = auditStore;
        this.clock = clock;
    }

    public String launch(
            LocalDate businessDate,
            String source,
            String triggerKey) {

        String auditId = UUID.randomUUID().toString();

        // 1. Lưu trước khi gọi launcher.
        auditStore.recordRequested(
            auditId,
            triggerKey,
            source,
            dailySalesJob.getName(),
            businessDate,
            clock.instant()
        );

        // 2. auditId là non-identifying.
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("auditId", auditId, false)
            .toJobParameters();

        try {
            // 3. Repository quyết định tạo mới, restart hay từ chối.
            JobExecution execution =
                launcher.run(dailySalesJob, parameters);

            // Có thể trả về trước khi job kết thúc nếu launcher async.
            auditStore.recordLaunchOutcome(
                auditId,
                "ACCEPTED",
                execution.getId(),
                null
            );

            log.info(
                "Batch launch accepted: auditId={}, executionId={}",
                auditId,
                execution.getId()
            );

        } catch (JobInstanceAlreadyCompleteException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "ALREADY_COMPLETED", null, null
            );

        } catch (JobExecutionAlreadyRunningException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "ALREADY_RUNNING", null, null
            );

        } catch (JobRestartException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "RESTART_REJECTED",
                null, ex.getClass().getSimpleName()
            );

        } catch (JobParametersInvalidException ex) {
            auditStore.recordLaunchOutcome(
                auditId, "INVALID_PARAMETERS",
                null, ex.getClass().getSimpleName()
            );

        } catch (Exception ex) {
            // Không khẳng định chắc execution đã được tạo hay chưa.
            auditStore.recordLaunchOutcome(
                auditId, "LAUNCH_ERROR",
                null, ex.getClass().getSimpleName()
            );

            log.error("Cannot confirm batch launch: auditId={}",
                      auditId, ex);
            throw new IllegalStateException(
                "Batch launch outcome is uncertain: " + auditId, ex
            );
        }

        return auditId;
    }
}
```

**Vì sao bắt riêng các ngoại lệ?** Cùng một lời gọi launcher, Spring Batch có thể từ chối do instance đã thành công, đang chạy, restart không hợp lệ hoặc tham số sai. Audit phải thể hiện đúng nguyên nhân để người vận hành phân biệt lỗi lịch, trigger trùng và lỗi cấu hình.

Đoạn code là ví dụ về luồng xử lý chính. Trong production, lỗi **ghi kết quả audit sau khi launcher đã tạo execution** phải được giám sát riêng. Nếu cập nhật audit thất bại, không được mặc nhiên coi job chưa chạy, và không được tự động phát lại với bộ tham số định danh mới. Reconciliation qua metadata Batch là cần thiết.

Cũng cần phân biệt tính **idempotent của JobInstance** với **idempotent của đầu ra nghiệp vụ**. Khi restart, writer vẫn cần transaction/khóa độc nhất hoặc cơ chế ghi an toàn để không nhân đôi dữ liệu đã xử lý.

## 10. Kết nối scheduler với coordinator

Với cron hàng ngày, ứng dụng có thể cấu hình:

```yaml
spring:
  batch:
    job:
      enabled: false

app:
  scheduling:
    cron: "0 10 1 * * *"
    zone: "Asia/Ho_Chi_Minh"
```

Trong đó `spring.batch.job.enabled=false` ngăn Spring Boot tự chạy job qua startup runner; lịch chạy sẽ do component sử dụng `@Scheduled` phát yêu cầu. Bật scheduling trong ứng dụng:

```java
import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Tạo scheduler:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailySalesScheduler {

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final BatchLaunchCoordinator coordinator;
    private final Clock clock;

    public DailySalesScheduler(
            BatchLaunchCoordinator coordinator,
            Clock clock) {
        this.coordinator = coordinator;
        this.clock = clock;
    }

    @Scheduled(
        cron = "${app.scheduling.cron}",
        zone = "${app.scheduling.zone}"
    )
    public void scheduledDailySales() {
        // Lúc 01:10 hôm nay, xử lý giao dịch ngày hôm qua.
        LocalDate businessDate =
            LocalDate.now(clock.withZone(BUSINESS_ZONE)).minusDays(1);

        coordinator.launch(
            businessDate,
            "SCHEDULED",
            "daily-sales:" + businessDate
        );
    }
}
```

Khi kích hoạt lại cùng ngày, `trigger_key` giữ nguyên nhưng `auditId` mới được tạo. Nhờ đó audit ghi lại từng lần yêu cầu, trong khi JobInstance vẫn được nhận diện theo `businessDate`.

Nếu business zone được thay đổi bằng cấu hình, logic tính `businessDate` cũng phải đọc cùng cấu hình, không cố định khác múi giờ với cron. Dùng `Clock` cho phép test hành vi gần nửa đêm mà không phụ thuộc đồng hồ thật.

### Lưu ý về trigger_source

Một API chạy bù có thể gọi:

```java
coordinator.launch(
    LocalDate.parse("2026-11-11"),
    "BACKFILL",
    "backfill-request-783:2026-11-11"
);
```

Nếu API có người dùng xác thực, nên lấy `requested_by` từ authentication context ở server, không tin một giá trị tự khai do client tự gửi. Đối với scheduler bên ngoài, lấy `trigger_key` từ event ID hoặc lịch thực tế mà hệ thống đó cung cấp.

## 11. Ghi trạng thái kết thúc bằng JobExecutionListener

Tại thời điểm `JobLauncher.run(...)` trả về, job có thể vẫn đang chạy nếu dùng launcher bất đồng bộ. Vì vậy không nên cập nhật `batch_status=COMPLETED` chỉ vì lời gọi không ném exception.

Có thể dùng `JobExecutionListener` để ghi trạng thái cuối:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class LaunchAuditJobListener
        implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(LaunchAuditJobListener.class);

    private final LaunchAuditStore auditStore;

    public LaunchAuditJobListener(LaunchAuditStore auditStore) {
        this.auditStore = auditStore;
    }

    @Override
    public void afterJob(JobExecution execution) {
        String auditId =
            execution.getJobParameters().getString("auditId");

        if (auditId == null) {
            log.warn(
                "No auditId on JobExecution {}",
                execution.getId()
            );
            return;
        }

        try {
            auditStore.recordFinished(
                auditId,
                execution.getStatus(),
                execution.getExitStatus().getExitCode()
            );

        } catch (Exception ex) {
            // Không để mất hoàn toàn tín hiệu lỗi audit.
            log.error(
                "Cannot store final job status: auditId={}, executionId={}",
                auditId,
                execution.getId(),
                ex
            );
            // Cần metric/cảnh báo và reconciliation sau đó.
        }
    }
}
```

Đăng ký listener vào job:

```java
@Bean("dailySalesJob")
Job dailySalesJob(
        JobRepository jobRepository,
        Step dailySalesStep,
        LaunchAuditJobListener auditListener) {

    return new JobBuilder("dailySalesJob", jobRepository)
        .start(dailySalesStep)
        .listener(auditListener)
        .build();
}
```

Giả sử `dailySalesStep` đã được định nghĩa trong cấu hình Batch. Cùng một job phải dùng tên ổn định để Spring Batch xác định instance qua tham số định danh.

### Một race condition hợp lệ

Với launcher đồng bộ, listener `afterJob()` có thể cập nhật `batch_status` **trước khi** lời gọi `launcher.run(...)` trả về và coordinator ghi `launch_outcome=ACCEPTED`. Code ở trên cập nhật **hai nhóm cột khác nhau**, nên kết quả cuối vẫn được giữ.

Với launcher bất đồng bộ, chiều ngược lại thường xảy ra: audit được chuyển sang `ACCEPTED` trước, sau đó listener cập nhật kết quả thực thi. Trong khoảng giữa, `batch_status` có thể vẫn `NULL`. Đây là trạng thái chưa có kết quả cuối, không phải lỗi dữ liệu.

Nếu cần một audit không thể sửa đổi vì yêu cầu tuân thủ, hãy lưu sự kiện append-only trong bảng riêng, ví dụ `LAUNCH_REQUESTED`, `LAUNCH_ACCEPTED`, `EXECUTION_FINISHED`. Bảng trạng thái tổng hợp có thể được xây từ những sự kiện đó. Ví dụ trong bài sử dụng một dòng cập nhật trạng thái cho dễ minh họa.

## 12. Một chuỗi sự kiện mẫu

Job `dailySalesJob` chạy theo `businessDate=2026-11-15`, lần đầu thành công.

```text
01:10:00  Cron phát trigger daily-sales:2026-11-15
01:10:00  Audit A1: REQUESTED
01:10:01  JobLauncher tạo JobExecution 8001
01:10:01  Audit A1: ACCEPTED, job_execution_id=8001
01:10:32  Job hoàn tất
01:10:32  Audit A1: batch_status=COMPLETED
```

Một thao tác bấm “run now” cho cùng ngày:

```text
02:00:00  Người vận hành gửi request cùng businessDate
02:00:00  Audit A2: REQUESTED
02:00:00  JobLauncher từ chối:
          JobInstanceAlreadyCompleteException
02:00:00  Audit A2: ALREADY_COMPLETED
          job_execution_id=NULL
```

Nếu lần đầu lỗi và sau đó restart:

```text
01:10  Audit B1: ACCEPTED -> Execution 8101 -> FAILED
01:30  Audit B2: ACCEPTED -> Execution 8102 -> COMPLETED

B1, B2 có audit_id khác nhau.
Execution 8101, 8102 khác ID nhưng cùng JobInstance.
```

Đây là lý do báo cáo vận hành nên hiển thị **số lần yêu cầu launch**, **số lần được chấp nhận** và **số execution thành công**, thay vì gộp tất cả thành một số “lần chạy”.

## 13. Xử lý crash, timeout và đối soát dữ liệu audit

Bởi ghi audit và tạo JobExecution không nằm trong một transaction nguyên tử duy nhất, có những cửa sổ lỗi cần xem xét:

| Thời điểm lỗi | Audit quan sát được | Điều thực sự có thể đã xảy ra |
| --- | --- | --- |
| Ghi `REQUESTED` thất bại | Không có bản ghi audit | Với policy fail-closed, launcher chưa được gọi |
| Sau khi ghi `REQUESTED`, trước khi gọi launcher | `REQUESTED` tồn tại lâu | Chưa gửi yêu cầu; có thể process chết |
| Trong khi launcher đang làm việc | `REQUESTED` hoặc `LAUNCH_ERROR` | Không chắc execution đã được tạo |
| Sau khi execution được tạo, trước khi ghi `ACCEPTED` | `REQUESTED` kéo dài | Job có thể đang chạy hoặc đã hoàn tất |
| Sau khi ghi `ACCEPTED`, process lỗi | `ACCEPTED`, chưa có trạng thái cuối | Cần đọc JobRepository để biết execution đã kết thúc hay chưa |
| Listener không cập nhật được audit | Có execution hoàn tất nhưng audit thiếu `batch_status` | Phải lấy lại kết quả từ metadata |

Vì JobParameters có `auditId` non-identifying, có thể phục hồi liên kết từ `BATCH_JOB_EXECUTION_PARAMS` và `BATCH_JOB_EXECUTION` nếu cần. Ngoài ra có thể tra qua `JobExplorer` với job name, ngày nghiệp vụ và danh sách executions.

Trong thiết kế vận hành, một tiến trình reconciliation định kỳ có thể:

1. Tìm audit `REQUESTED` hoặc `LAUNCH_ERROR` quá thời gian chờ hợp lý.
2. Tra metadata Batch theo `auditId` và kỳ nghiệp vụ.
3. Nếu tìm thấy execution, liên kết lại execution ID và trạng thái.
4. Nếu không có bằng chứng execution, phân loại `UNKNOWN` hoặc chờ điều tra; không tự nhận định job chắc chắn chưa chạy chỉ từ timeout.
5. Gửi cảnh báo đối với audit thiếu kết quả hoặc kỳ lịch đã đến hạn mà không có execution thành công.

Không nên tự retry theo kiểu thay tham số định danh chỉ để “chắc chắn chạy được”. Điều đó có thể bỏ qua bảo vệ JobInstance và gây xử lý trùng.

## 14. Audit trong môi trường nhiều scheduler và nhiều replica

Mỗi replica có `@Scheduled` đều có thể đến hạn cùng lúc:

```text
           Cron 01:10
         /     |      \
    Replica A  B       C
       |       |       |
     Audit A  Audit B  Audit C
       |       |       |
       +-------+-------+
               |
        Shared JobRepository
               |
       Cùng businessDate
```

Nếu repository được cấu hình và chia sẻ đúng, các lần launch cho cùng instance có thể cho một execution hợp lệ và các yêu cầu khác bị từ chối vì đang chạy hoặc đã hoàn tất. Audit vẫn nên ghi **cả ba lần cố gắng**, để thấy scheduler đã phát trùng.

Tuy nhiên, JobRepository không giải quyết tất cả yêu cầu chỉ có **một trigger trên toàn cluster**. Tùy hệ thống, có thể dùng Quartz JDBC JobStore, distributed lock, một scheduler leader hoặc scheduler bên ngoài. Audit giúp đánh giá cơ chế điều phối có thực sự tránh phát trùng hay không.

Khi nhiều kỳ dữ liệu khác nhau được xử lý đồng thời, chúng thường là nhiều JobInstance khác nhau. Cần kiểm tra tài nguyên đích, lịch chồng nhau và ràng buộc business key ngoài metadata Batch.

## 15. Quan sát qua log, trace và dashboard

Audit trong database nên đi cùng log có cấu trúc và metric. Mỗi dòng log liên quan đến một lần launch cần có khóa tương quan rõ ràng:

```text
event=launch.requested
job=dailySalesJob
auditId=3fe...
triggerSource=SCHEDULED
triggerKey=daily-sales:2026-11-15
businessDate=2026-11-15
```

Sau khi được chấp nhận:

```text
event=launch.accepted
auditId=3fe...
jobExecutionId=8001
```

Khi kết thúc:

```text
event=job.finished
auditId=3fe...
jobExecutionId=8001
batchStatus=COMPLETED
exitCode=COMPLETED
```

Nếu ứng dụng sử dụng MDC hoặc hệ thống distributed tracing, có thể gắn `auditId` vào context để lần theo yêu cầu từ scheduler tới launcher. Với luồng bất đồng bộ, cần truyền correlation context qua thread hoặc ghi `auditId` vào JobParameters để liên kết lại; không giả định ThreadLocal MDC tự đi qua mọi executor.

Metric hữu ích gồm:

- Số lần launch attempt theo job, source và outcome.
- Tỷ lệ trigger bị từ chối vì `ALREADY_RUNNING` hoặc `ALREADY_COMPLETED`.
- Số execution `FAILED`, `COMPLETED`, `STOPPED`.
- Thời gian từ khi lịch đến hạn đến khi launch, nếu nguồn cung cấp `scheduled_at`.
- Số kỳ nghiệp vụ chưa có execution thành công trước hạn SLA.
- Số bản ghi audit `REQUESTED`/`LAUNCH_ERROR` chưa được đối soát.

**Không đưa toàn bộ `auditId`, UUID hoặc business key có cardinality rất lớn làm nhãn metric** nếu nền tảng metric không phù hợp. Những giá trị này nên nằm trong log, trace hoặc bảng audit; metric ưu tiên nhãn phân nhóm ổn định như job name, source và outcome.

## 16. Bảo mật, thời gian lưu và phạm vi audit

Một bản ghi audit có thể được dùng để truy vết thao tác vận hành, nên cần thiết kế chính sách lưu trữ:

- Lưu timestamp có múi giờ hoặc sử dụng UTC thống nhất; lưu business zone riêng khi cần giải thích lịch.
- Chỉ lưu identifying parameters đã được phép hiển thị. Tránh mật khẩu, token, số thẻ, payload chứa dữ liệu cá nhân hoặc exception message có dữ liệu nhạy cảm.
- Với launch thủ công, lấy identity người yêu cầu từ server-side authentication, không tin trường `requestedBy` do client tự khai.
- Chỉ hệ thống điều phối và dịch vụ Batch được quyền ghi; người quan sát nên chỉ có quyền đọc phù hợp.
- Xác định thời hạn lưu audit, cách archive và yêu cầu truy xuất; tách retention của audit với retention metadata nếu cần.
- Nếu audit phải có tính bất biến hoặc là bằng chứng pháp lý, sử dụng append-only storage/event log và cơ chế kiểm soát thay đổi; không xem bảng cập nhật trạng thái ở ví dụ như một nhật ký bất biến.

Audit trạng thái khởi chạy không thay thế audit **tác động nghiệp vụ**. Một JobExecution `COMPLETED` không bảo đảm writer không gửi thông điệp trùng ra hệ thống ngoài; cần thêm kiểm tra transaction, khóa idempotency và dữ liệu đầu ra.

## 17. Kiểm thử audit lần launch

Nên có cả **unit test** đối với coordinator và **integration test** sử dụng JobRepository cùng database audit thật. Test scheduler không cần chờ đúng giờ cron: gọi trực tiếp method hoặc coordinator với `Clock.fixed(...)`.

### 17.1. Test yêu cầu được chấp nhận

Với mock launcher và audit store, ta kiểm tra đúng tham số và cờ identifying:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class BatchLaunchCoordinatorTest {

    @Test
    void acceptedLaunchHasAuditCorrelation() throws Exception {
        JobLauncher launcher = mock(JobLauncher.class);
        Job job = mock(Job.class);
        JobExecution execution = mock(JobExecution.class);
        LaunchAuditStore auditStore = mock(LaunchAuditStore.class);

        when(job.getName()).thenReturn("dailySalesJob");
        when(execution.getId()).thenReturn(101L);
        when(launcher.run(eq(job), any(JobParameters.class)))
            .thenReturn(execution);

        Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T01:10:00Z"),
            ZoneOffset.UTC
        );

        BatchLaunchCoordinator service =
            new BatchLaunchCoordinator(
                launcher, job, auditStore, clock
            );

        String auditId = service.launch(
            LocalDate.parse("2026-11-15"),
            "SCHEDULED",
            "daily-sales:2026-11-15"
        );

        ArgumentCaptor<JobParameters> captor =
            ArgumentCaptor.forClass(JobParameters.class);

        verify(launcher).run(eq(job), captor.capture());

        JobParameters params = captor.getValue();

        assertEquals(
            "2026-11-15",
            params.getString("businessDate")
        );
        assertTrue(
            params.getParameter("businessDate").isIdentifying()
        );
        assertEquals(auditId, params.getString("auditId"));
        assertFalse(
            params.getParameter("auditId").isIdentifying()
        );

        InOrder order = inOrder(auditStore, launcher);
        order.verify(auditStore).recordRequested(
            eq(auditId),
            eq("daily-sales:2026-11-15"),
            eq("SCHEDULED"),
            eq("dailySalesJob"),
            eq(LocalDate.parse("2026-11-15")),
            any(Instant.class)
        );
        order.verify(launcher).run(
            eq(job), any(JobParameters.class)
        );
        order.verify(auditStore).recordLaunchOutcome(
            auditId, "ACCEPTED", 101L, null
        );
    }
}
```

Điểm chính của test là xác nhận thứ tự: **ghi `REQUESTED` trước khi gọi launcher**, sau đó mới cập nhật outcome. Nó cũng xác minh `auditId` không thay đổi danh tính JobInstance.

### 17.2. Test launch bị từ chối

Dùng mock `JobLauncher` ném `JobInstanceAlreadyCompleteException` hoặc `JobExecutionAlreadyRunningException`. Khẳng định:

- Mỗi yêu cầu có một bản ghi audit riêng với outcome tương ứng.
- Không ghi một execution ID giả khi launcher bị từ chối.
- Yêu cầu bị từ chối vẫn có `job_name`, `source`, `business_date` và `requested_at`.
- Không đánh dấu `batch_status=FAILED` cho một attempt không có JobExecution.

Trong integration test, chạy job thật một lần đến `COMPLETED`, sau đó dùng lại identifying parameters để phát yêu cầu thứ hai. Bảng audit phải có hai dòng, trong khi Batch metadata chỉ có một JobExecution.

### 17.3. Test restart sau thất bại

Cho execution đầu `FAILED` rồi launch lại với cùng `businessDate`:

| Lần | audit_id | JobInstance | JobExecution | BatchStatus cuối |
| --- | --- | --- | --- | --- |
| 1 | Khác nhau | Cùng ID | Execution X | `FAILED` |
| 2 | Khác nhau | Cùng ID | Execution Y | `COMPLETED` |

Khẳng định cả hai attempt được `ACCEPTED` và có execution ID khác nhau; cả hai execution thuộc cùng JobInstance. Đây là điểm phân biệt audit launch với lịch sử một instance.

### 17.4. Test lỗi ghi audit, crash và async launcher

Các kịch bản cần xem xét thêm:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Không ghi được `REQUESTED` | Với policy bắt buộc, launcher không được gọi |
| Lỗi ghi `ACCEPTED` sau khi launcher chạy | Audit còn thiếu kết quả nhưng JobExecution vẫn phải có khả năng đối soát |
| Launcher bị timeout/hạ tầng lỗi | Outcome không khẳng định chắc job chưa được tạo |
| Launcher async | Có trạng thái tạm `ACCEPTED`, sau đó trạng thái cuối cập nhật bởi listener |
| Cùng trigger đến trên hai node | Mỗi attempt có audit ID; chỉ execution hợp lệ được chạy với cùng identifying parameters |
| Scheduler không hề kích hoạt | Không có audit attempt; phát hiện bằng kiểm tra lịch dự kiến và absence-of-success |
| Đồng hồ gần ranh giới ngày | Kỳ nghiệp vụ được tính đúng theo zone, audit thời điểm nhất quán |

Với test concurrency, dùng cơ chế đồng bộ như `CountDownLatch` để bảo đảm execution đầu đang chạy trước khi gửi attempt thứ hai; tránh đoán thời gian bằng `Thread.sleep`.

## 18. Truy vấn phục vụ điều tra

### 18.1. Xem mọi attempt của một kỳ

```sql
SELECT
    audit_id,
    trigger_source,
    trigger_key,
    requested_at,
    launch_outcome,
    job_execution_id,
    batch_status,
    exit_code
FROM batch_launch_audit
WHERE job_name = 'dailySalesJob'
  AND business_date = DATE '2026-11-15'
ORDER BY requested_at, audit_id;
```

Truy vấn có thể trả về nhiều dòng dù Spring Batch chỉ có một JobInstance. Đó là hành vi mong muốn khi audit mọi lần scheduler cố gắng launch.

### 18.2. Tìm yêu cầu chưa có kết quả rõ ràng

```sql
SELECT
    audit_id,
    job_name,
    business_date,
    requested_at,
    launch_outcome
FROM batch_launch_audit
WHERE launch_outcome IN ('REQUESTED', 'LAUNCH_ERROR')
  AND requested_at < CURRENT_TIMESTAMP - INTERVAL '15 minutes'
ORDER BY requested_at;
```

Khoảng 15 phút chỉ là ví dụ; cần chỉnh theo SLA, loại job và kiểu launcher. Các bản ghi tìm được là **ứng viên cần đối soát**, không tự động chứng minh job không chạy.

### 18.3. Thống kê launch outcome theo ngày

```sql
SELECT
    business_date,
    launch_outcome,
    COUNT(*) AS attempts
FROM batch_launch_audit
WHERE job_name = 'dailySalesJob'
GROUP BY business_date, launch_outcome
ORDER BY business_date, launch_outcome;
```

Báo cáo này giúp phát hiện tần suất `ALREADY_RUNNING` tăng cao (có thể lịch chồng hoặc nhiều node cùng phát), `INVALID_PARAMETERS` tăng sau một lần deploy hoặc nhiều `LAUNCH_ERROR` trùng thời điểm hạ tầng gặp sự cố.

## 19. Những lỗi thiết kế thường gặp

| Vấn đề | Hậu quả | Hướng giải quyết |
| --- | --- | --- |
| Chỉ audit sau `JobLauncher.run` thành công | Mất dấu vết các yêu cầu bị từ chối | Ghi `REQUESTED` trước launcher |
| Chỉ đọc `BATCH_JOB_EXECUTION` | Không thấy những trigger không tạo execution | Có bảng launch attempt riêng |
| Dùng `jobExecutionId` làm audit primary key | Không lưu được attempt bị từ chối | Tạo `auditId` riêng |
| Đưa `auditId` vào identifying parameters | Restart/trùng lịch biến thành instance mới | Đánh dấu `auditId` non-identifying |
| Coi `ACCEPTED` là job đã thành công | Báo cáo sai khi job thất bại hoặc chạy async | Theo dõi `BatchStatus` cuối riêng |
| Ghi audit trong cùng giao dịch lớn rồi rollback | Mất dữ liệu audit khi job thất bại | Transaction ghi audit độc lập |
| Audit update lỗi thì launch lại với UUID định danh mới | Có nguy cơ xử lý trùng kỳ nghiệp vụ | Giữ business key, đối soát metadata |
| Gắn raw JobParameters hoặc exception message | Rò rỉ token, thông tin cá nhân | Allowlist trường và mã lỗi chuẩn |
| Chỉ giữ audit trạng thái `ACCEPTED` | Không phát hiện scheduler không chạy | So sánh với danh sách kỳ dự kiến |
| Gắn `auditId` làm metric tag | Cardinality metric quá cao | Giữ auditId trong log/trace/audit DB |
| Xóa audit cùng lúc dọn Batch metadata | Mất lịch sử điều tra | Quy định retention riêng |
| Có nhiều replica nhưng không quan sát trigger trùng | Khó thấy lỗi điều phối | Lưu source, trigger key, audit outcome |

## 20. Bài tập thực hành

Hãy xây dựng một job `dailySettlementJob` chạy mỗi ngày lúc 02:00, xử lý giao dịch của ngày trước đó và lưu metadata vào Spring Batch repository. Tạo bảng `batch_launch_audit` và một coordinator tương tự ví dụ.

Thực hiện bốn tình huống: lần launch đầu hoàn tất; trigger cùng kỳ gửi lại và bị từ chối; execution đầu thất bại rồi restart thành công; lỗi ghi kết quả audit sau khi repository tạo execution. Với mỗi trường hợp, kiểm tra số dòng audit, outcome, JobInstance ID, JobExecution ID và BatchStatus cuối.

Sau đó giả lập hai scheduler cùng phát trigger cho một ngày. Hãy viết truy vấn thống kê số attempt theo `trigger_key` và phát cảnh báo nếu có một kỳ lịch phát nhiều yêu cầu không mong đợi. Cuối cùng, tạo một tác vụ reconciliation tìm các bản ghi `REQUESTED` quá hạn và liên kết lại kết quả từ metadata Batch dựa trên `auditId`.

## 21. Kết luận

Audit lần launch giúp phân biệt ba việc rất khác nhau: **scheduler đã yêu cầu chạy**, **Spring Batch có chấp nhận yêu cầu hay không** và **job cuối cùng đã xử lý thành công hay chưa**. Vì nhiều yêu cầu có thể bị từ chối mà không tạo JobExecution, hệ thống cần ghi riêng một audit record cho từng attempt, trước khi gọi `JobLauncher`. Sử dụng `auditId` non-identifying để liên kết với metadata, theo dõi trạng thái cuối bằng listener và có cơ chế reconciliation cho lỗi hạ tầng sẽ tạo nên một lịch sử thực thi đáng tin cậy, phục vụ kiểm thử, vận hành và điều tra sự cố.
