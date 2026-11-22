# Chạy lại sau failure trong Spring Batch Scheduling

## 1. Vì sao cần cơ chế chạy lại sau failure?

Một Job batch có thể chạy tự động lúc 02:00 hằng ngày để nhập đơn hàng, chốt giao dịch, đối soát hoặc tổng hợp báo cáo. Trong một lần chạy, kết nối cơ sở dữ liệu có thể bị ngắt, API bên ngoài hết thời gian chờ, message broker tạm thời không sẵn sàng hoặc một bản ghi dữ liệu sai khiến Job kết thúc với trạng thái `FAILED`.

Nếu hệ thống chỉ có lịch `@Scheduled` khởi chạy Job vào ngày hôm sau, lô dữ liệu lỗi hôm trước có thể bị bỏ quên. Nếu hệ thống lập tức tạo JobInstance mới để “chạy lại”, các dữ liệu đã commit có thể bị xử lý hai lần. Do đó, **chạy lại sau failure** là một bài toán phối hợp giữa **JobRepository**, **chính sách retry/restart** và **bộ lập lịch**.

Sau bài này, bạn sẽ hiểu và thực hiện được:

- Phân biệt retry bên trong một Step, restart một JobInstance thất bại và chạy JobInstance mới.
- Quyết định lỗi nào có thể chạy lại tự động và lỗi nào phải dừng để xử lý thủ công.
- Lập lịch chạy lại dựa trên JobExecution đã `FAILED`, với khoảng chờ, giới hạn số lần và ghi nhận lịch sử.
- Dùng `JobOperator` hoặc `JobLauncher` đúng mục đích mà không tạo nhầm JobInstance mới.
- Bảo đảm checkpoint, transaction và idempotency khi một Job đã commit một phần dữ liệu.
- Tránh hai scheduler hoặc hai worker cùng khởi chạy lại một JobInstance.
- Thiết kế kiểm thử cho tình huống lỗi, phục hồi, downtime và lỗi lặp lại.

Bối cảnh là **Spring Batch Core Processing**, trong đó việc chạy theo lịch có thể được thực hiện bởi Spring Scheduling, Quartz, Kubernetes CronJob, Airflow hoặc một hệ thống điều phối bên ngoài. Quy tắc về JobInstance và JobRepository không đổi dù bộ lập lịch khác nhau.

## 2. Ba khái niệm không thể đánh đồng

| Khái niệm | Phạm vi | Khi nào dùng? | Metadata |
| --- | --- | --- | --- |
| **Retry trong Step** | Một item, chunk hoặc thao tác của Step ở **cùng JobExecution** | Lỗi tạm thời như timeout có thể thành công sau vài lần thử ngay lập tức | JobExecution hiện tại tiếp tục chạy; skip/retry count phản ánh xử lý. |
| **Restart Job** | Tạo **JobExecution mới cho cùng JobInstance** | Job đã `FAILED`/`STOPPED` và cần tiếp tục lô cũ | JobRepository giữ lịch sử execution và ExecutionContext phục vụ khôi phục. |
| **Chạy JobInstance mới** | Tên Job hoặc identifying JobParameters khác | Xử lý kỳ/ngày/lô nghiệp vụ mới | Tạo JobInstance mới; không dùng checkpoint của lô thất bại trước. |

Ví dụ Job `dailySettlement` chạy với identifying parameter `businessDate=2026-11-16`. Sau 30 phút, Job thất bại khi đã commit phần đầu:

~~~text
Job: dailySettlement
Identifying parameters: businessDate=2026-11-16
                 |
                 v
           JobInstance #12
             /         \
            /           \
 JobExecution #91    JobExecution #92
       FAILED          COMPLETED
     02:00-02:30      restart lúc 02:45
~~~

Lần 02:45 phải tạo **JobExecution #92 cho JobInstance #12**. Nếu thêm identifying parameter `run.id=2` hoặc thay `businessDate`, Spring Batch xem đó là JobInstance khác và có thể xử lý lại toàn bộ dữ liệu.

### JobInstance và JobParameters

Trong Spring Batch, danh tính JobInstance được xác định bởi **tên Job** và **các identifying JobParameters**. Ví dụ dùng Spring Batch 5.x:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("requestedBy", "nightly-scheduler", false)
        .toJobParameters();
~~~

Tham số `businessDate` định danh lô; `requestedBy` chỉ mô tả nơi gọi và không làm thay đổi identity của JobInstance. Để restart, giữ nguyên identity. Một `JobExecution` mới được tạo khi framework tiếp tục JobInstance đã lỗi.

### Khi nào `launchJob` với cùng tham số là restart?

Ở Spring Batch 5.x, `JobLauncher.run(job, parameters)` sẽ tra cứu JobInstance theo tham số. Nếu instance cũ đã `FAILED` và cho phép restart, framework có thể tạo execution mới để chạy tiếp; nếu instance đã `COMPLETED`, Spring Batch sẽ từ chối chạy lại với cùng identifying parameters.

Tuy nhiên, ở tầng vận hành **nên dùng `JobOperator.restart(failedExecutionId)`** khi mục đích rõ ràng là khôi phục lô đã lỗi. Cách này thể hiện ý định và tránh việc caller vô tình truyền bộ tham số mới. Riêng lịch chạy lô mới nên dùng `JobLauncher.run` hoặc API start của phiên bản tương ứng.

## 3. Điều gì xảy ra khi Job thất bại giữa chừng?

Giả sử một Step đọc năm bản ghi theo thứ tự `1,2,3,4,5`, mỗi chunk gồm hai item. Processor gây lỗi không được cấu hình skip/retry tại item `3`:

~~~text
Execution đầu:
   đọc [1,2] -> write [1,2] -> COMMIT
   đọc [3]   -> processor throw -> ROLLBACK chunk hiện tại
   JobExecution = FAILED
   đích đã commit = [1,2]
   checkpoint sau bản ghi 2

Execution restart:
   mở reader từ checkpoint đã lưu
   đọc [3,4] -> write [3,4] -> COMMIT
   đọc [5]   -> write [5]   -> COMMIT
   JobExecution = COMPLETED
   đích cuối = [1,2,3,4,5]
~~~

Điều này chỉ đúng nếu Job được thiết kế restartable:

- Reader lưu `ExecutionContext` hoặc sử dụng chiến lược truy vấn các bản ghi chưa hoàn thành.
- Thứ tự đọc ổn định (ví dụ `ORDER BY id` với nguồn dữ liệu phù hợp) hoặc checkpoint dựa trên khóa nghiệp vụ.
- Writer ghi dữ liệu trong ranh giới transaction đúng; chunk chưa commit phải rollback.
- Những side effect nằm ngoài transaction như gọi HTTP, gửi email hoặc ghi sang message broker có cơ chế **idempotency**.
- JobRepository và bảng metadata `BATCH_*` còn nguyên, không bị xóa sau failure.

**Restart không có nghĩa là tự động “exactly once”.** Nếu writer đã gửi yêu cầu thanh toán qua HTTP và response bị mất, framework có thể cho rằng chunk thất bại rồi gọi lại sau restart. Hệ thống đích phải hỗ trợ idempotency key hoặc có cơ chế đối soát để không thanh toán hai lần.

## 4. Chính sách lỗi: tự động chạy lại hay xử lý thủ công?

Một scheduler không nên restart mọi Job `FAILED` vô điều kiện. Cần phân loại lỗi và định nghĩa chính sách vận hành.

| Nhóm lỗi | Ví dụ | Hành vi khuyến nghị |
| --- | --- | --- |
| **Lỗi tạm thời** | Timeout mạng, 503, database mất kết nối ngắn | Có thể tự động restart sau cooldown/backoff, trong giới hạn số lần. |
| **Lỗi dữ liệu** | Schema CSV sai, thiếu trường bắt buộc, bản ghi không hợp lệ | Dừng và báo người phụ trách; sửa dữ liệu trước restart. |
| **Lỗi cấu hình** | Thiếu secret, sai URL, thiếu quyền truy cập | Không tự restart liên tục; cần sửa cấu hình. |
| **Lỗi tài nguyên** | Disk full, hết bộ nhớ, thiếu quota | Đánh giá tài nguyên/khả năng phục hồi trước khi thử lại. |
| **Lỗi code** | NullPointerException, logic nghiệp vụ sai | Sửa, triển khai phiên bản phù hợp rồi đánh giá tương thích checkpoint. |
| **Lỗi sau side effect ngoài transaction** | API đã nhận lệnh nhưng Step báo timeout | Đối soát/idempotency trước khi tự động retry/restart. |
| **Lỗi do operator chủ động stop** | Bảo trì theo kế hoạch | Không tự động restart nếu chưa được cho phép. |

Có thể đưa chính sách vào cấu hình:

~~~yaml
batch:
  recovery:
    enabled: true
    max-executions-per-instance: 3
    initial-delay: 5m
    max-delay: 1h
    scan-interval: 1m
    eligible-jobs:
      - dailySettlement
      - importOrders
~~~

Đây là **cấu hình minh họa do ứng dụng tự định nghĩa**, không phải các thuộc tính Spring Batch tích hợp sẵn. Ứng dụng phải hiện thực logic đọc các giá trị này, lưu kế hoạch chạy lại và áp dụng chính sách.

**Max executions = 3** có nghĩa là tổng cộng một lần chạy đầu và tối đa hai lần restart. Nếu cần cho phép ba lần restart, giới hạn tổng execution sẽ là bốn.

## 5. Backoff, cooldown và giới hạn số lần

Nếu database đang lỗi trong 20 phút, restart liên tục sau mỗi giây sẽ làm tăng tải và khiến sự cố nặng hơn. Một kế hoạch phục hồi nên có:

- **Initial delay:** đợi một khoảng tối thiểu sau failure trước khi thử lần đầu.
- **Exponential backoff:** khoảng chờ tăng theo số lần thất bại, ví dụ 5, 10, 20, 40 phút.
- **Jitter:** cộng/trừ chút ngẫu nhiên để nhiều Job không cùng đánh thức và gọi một hệ thống đang yếu.
- **Maximum delay:** chặn khoảng chờ tăng vô hạn.
- **Maximum attempts:** khi chạm ngưỡng thì chuyển sang trạng thái chờ xử lý thủ công, gửi cảnh báo.
- **Time window/expiry:** bỏ qua tự động restart nếu lô quá cũ hoặc business cutoff đã qua.

Ví dụ với initial delay 5 phút và nhân đôi sau mỗi lần thất bại:

| Execution vừa lỗi | Thời điểm tiếp theo (nếu được cho phép) |
| --- | --- |
| Lần 1, 02:10 | Sớm nhất 02:15 |
| Lần 2, 02:16 | Sớm nhất 02:26 |
| Lần 3, 02:28 | Sớm nhất 02:48 |
| Vượt ngưỡng | Không tự restart; cảnh báo/đối soát |

Công thức minh họa:

~~~text
delay(n) = min(maxDelay, initialDelay * 2^(n-1)) + jitter

n = số lần thất bại đã xảy ra với JobInstance này
~~~

**Backoff của scheduler khác retry policy bên trong Step.** Một Step có thể retry cùng item ba lần trong một execution rồi mới đánh dấu Job `FAILED`. Chính sách scheduler sau đó mới quyết định có tạo execution mới hay không. Nếu không giới hạn cả hai tầng, tổng số lần gọi một API bên ngoài có thể lớn hơn dự kiến.

## 6. Thiết kế luồng scheduling và recovery

Một kiến trúc phù hợp gồm hai luồng riêng:

1. **Lịch chạy lô mới:** tạo JobInstance cho kỳ nghiệp vụ mới, chẳng hạn ngày 17/11.
2. **Lịch khôi phục lô lỗi:** tra cứu JobInstance đã `FAILED`, áp dụng chính sách, rồi restart cùng instance.

~~~text
        Nightly schedule (02:00)
                   |
                   v
       launch(Job, businessDate=D)
                   |
                   v
              JobRepository
                   |
          +--------+---------+
          |                  |
      COMPLETED            FAILED
          |                  |
          v                  v
       Finished        Failure classifier
                             |
              +--------------+--------------+
              |                             |
       Not retryable                  Retryable
              |                             |
              v                             v
         Alert/manual           Durable recovery plan
                                    (dueAt, attempts)
                                           |
                                           v
                                  Recovery scheduler
                                           |
                                           v
                                 Re-read JobRepository
                                           |
                               still FAILED & eligible?
                                  /             \
                                no               yes
                                |                 |
                                v                 v
                           reconcile      JobOperator.restart
                                                  |
                                                  v
                                          JobExecution mới
                                                  |
                                         monitor final state
~~~

Điểm cần nhấn mạnh: **bộ lập lịch chỉ quyết định khi nào và có nên yêu cầu restart; chính Spring Batch và JobRepository quyết định JobInstance/Step nào được thực thi lại**. Nếu ứng dụng có nhiều scheduler, phải có cơ chế phối hợp để không hai scheduler cùng xử lý một kế hoạch restart.

## 7. Lịch chạy Job mới bằng Spring Scheduling

Ví dụ dưới đây dùng **Spring Boot 3.x + Spring Batch 5.2.x**, Java 17+, với `JobLauncher`. Giả định đã cấu hình JDBC JobRepository và đã bật scheduling qua `@EnableScheduling`.

~~~java
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyImportSchedule {

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher jobLauncher;
    private final Job dailyImportJob;

    public DailyImportSchedule(
            JobLauncher jobLauncher,
            @Qualifier("dailyImportJob") Job dailyImportJob) {
        this.jobLauncher = jobLauncher;
        this.dailyImportJob = dailyImportJob;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
    public void runDailyBatch() throws Exception {
        LocalDate businessDate = LocalDate.now(BUSINESS_ZONE);

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        jobLauncher.run(dailyImportJob, params);
    }
}
~~~

Trong cấu hình ứng dụng:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchApplication {
    public static void main(String[] args) {
        org.springframework.boot.SpringApplication.run(
            BatchApplication.class, args);
    }
}
~~~

Lịch `0 0 2 * * *` chạy lúc 02:00 mỗi ngày theo timezone đã chỉ định. Với một identifying parameter là `businessDate`, hai yêu cầu chạy trong cùng ngày dùng chung identity của JobInstance.

Một số điểm cần lưu ý:

- `@Scheduled` chỉ tạo trigger trong process Spring hiện tại. Nếu ứng dụng tắt đúng giờ 02:00, trigger có thể bị bỏ lỡ; khi khởi động lại nó không tự “bù” lần đã mất. Cần logic catch-up, persistent scheduler hoặc lưu lịch công việc bền vững.
- Khi triển khai **nhiều instance ứng dụng**, mỗi instance có thể kích hoạt cùng `@Scheduled`. Sử dụng điều phối leader, distributed lock hoặc scheduler tập trung nếu chỉ muốn một trigger.
- Nếu Job dùng executor bất đồng bộ, `JobLauncher.run` có thể trả về khi Job còn đang chạy; không mặc định xem “không ném exception” là `COMPLETED`.
- Khi Job hôm qua vẫn `FAILED`, việc chạy theo businessDate hôm nay tạo **lô mới**. Phải có cơ chế recovery riêng để không bỏ quên lô hôm qua.
- Nếu Job đã `COMPLETED` với identity đó, launcher từ chối lần chạy trùng; không sinh `run.id` ngẫu nhiên chỉ để tránh lỗi.
- Nếu nghiệp vụ chốt số liệu cho **ngày trước**, hãy tính `businessDate` từ quy tắc nghiệp vụ (ví dụ hôm qua) thay vì mặc định ngày hiện tại. Cron là thời gian kích hoạt, chưa chắc là kỳ dữ liệu.

## 8. Restart Job FAILED qua JobOperator

Đối với Spring Batch 5.2.x, `JobOperator.restart(long executionId)` là thao tác rõ nghĩa để tạo execution mới từ một JobExecution đã lỗi.

~~~java
import java.util.Comparator;
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class FailureRestartService {

    private static final int MAX_EXECUTIONS = 3;

    private final JobExplorer jobExplorer;
    private final JobOperator jobOperator;

    public FailureRestartService(
            JobExplorer jobExplorer,
            JobOperator jobOperator) {
        this.jobExplorer = jobExplorer;
        this.jobOperator = jobOperator;
    }

    public long restartLatestFailedExecution(long failedExecutionId)
            throws Exception {

        JobExecution failed =
                jobExplorer.getJobExecution(failedExecutionId);

        if (failed == null) {
            throw new IllegalArgumentException(
                "Unknown execution: " + failedExecutionId);
        }

        JobInstance instance = failed.getJobInstance();
        List<JobExecution> history =
                jobExplorer.getJobExecutions(instance);

        JobExecution latest = history.stream()
                .max(Comparator.comparingLong(JobExecution::getId))
                .orElseThrow();

        if (!latest.getId().equals(failedExecutionId)) {
            throw new IllegalStateException(
                "A newer execution already exists for this instance");
        }

        if (latest.getStatus() != BatchStatus.FAILED) {
            throw new IllegalStateException(
                "Only FAILED execution can use auto recovery");
        }

        if (history.size() >= MAX_EXECUTIONS) {
            throw new IllegalStateException(
                "Execution budget exhausted");
        }

        // Cần được gọi chỉ khi lỗi đã được xác nhận retryable
        // và thời điểm nextAttemptAt đã đến.
        return jobOperator.restart(failedExecutionId);
    }
}
~~~

**Mục đích của service:** minh họa lớp bảo vệ trước khi restart, với ID cụ thể và giới hạn tổng execution. Nó không tự phân loại lỗi, kiểm deadline hay lưu lịch; những điều kiện đó phải được xử lý ở tầng recovery policy trước khi gọi. Các lời gọi đọc trạng thái rồi restart không phải transaction nguyên tử: nếu một node khác restart cùng lúc, framework có thể ném lỗi do execution đang chạy hoặc instance đã đổi trạng thái. Đó là **xung đột hợp lệ** cần bắt và đối soát.

### Khi một Job có nhiều lần thất bại

Giả sử:

~~~text
JobInstance #70:
  #200 FAILED     02:02
  #201 FAILED     02:12
  #202 FAILED     02:40
~~~

Nếu max executions = 3, policy không cho chạy lần thứ tư tự động. Khi có thay đổi cấu hình hoặc được người vận hành phê duyệt, có thể cân nhắc một policy mới. Không xóa lịch sử JobRepository để “reset” bộ đếm: việc đó sẽ phá hỏng identity, checkpoint và audit trail.

## 9. Đưa yêu cầu restart vào lịch tự động

Ở môi trường đơn giản, một `@Scheduled` có thể quét metadata để tìm JobInstance có execution mới nhất `FAILED`. Tuy nhiên, cách quét tự động **mọi lỗi** dễ chạy lại các Job không nên retry. Hệ thống sản xuất nên quản lý một **bảng kế hoạch khôi phục bền vững**, chỉ đưa các lỗi đã được phân loại retryable vào hàng đợi.

### 9.1. Bảng kế hoạch khôi phục

Ví dụ schema ý tưởng:

~~~sql
CREATE TABLE batch_recovery_plan (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_instance_id BIGINT NOT NULL,
    failed_execution_id BIGINT NOT NULL,
    state VARCHAR(24) NOT NULL,
    attempt_count INTEGER NOT NULL,
    next_attempt_at TIMESTAMP NOT NULL,
    lease_until TIMESTAMP,
    last_error VARCHAR(1000),
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_recovery_instance UNIQUE (job_instance_id)
);
~~~

Các trạng thái tự định nghĩa có thể gồm:

| Trạng thái plan | Ý nghĩa |
| --- | --- |
| `PENDING` | Đã phân loại lỗi và có lịch retry. |
| `CLAIMED` | Một worker đã giữ lease và đang thực hiện yêu cầu restart. |
| `WAITING` | Đã restart, chờ kết quả JobExecution mới. |
| `DONE` | JobInstance đã hoàn thành hoặc plan đã được xử lý. |
| `PARKED` | Không còn đủ điều kiện tự động retry; chờ vận hành. |

**Đây là bảng nghiệp vụ của cơ chế recovery**, không thuộc schema `BATCH_*` mặc định của Spring Batch. Trạng thái authoritative của JobExecution vẫn nằm trong JobRepository. Bảng plan giúp lưu **khi nào thử lại, ai giữ lease, giới hạn retry và quyết định của chính sách**.

Nếu source database có timezone khác với JVM, lưu `next_attempt_at` theo UTC hoặc kiểu có timezone, và quy ước rõ cách so sánh khi quét.

### 9.2. Thuật toán scheduler

~~~text
every 60 seconds:
    claims = acquireDuePlans(now, limit = 20)

    for each plan:
        latest = JobExplorer.getJobExecutions(plan.jobInstance)
                            .maxBy(executionId)

        if latest.status == COMPLETED:
            markPlanDone()
            continue

        if latest.status == STARTED / STARTING / STOPPING:
            markPlanWaitingOrReconcile()
            continue

        if latest.status != FAILED:
            parkOrReclassify()
            continue

        if retryBudgetExhausted or deadlineExpired:
            parkPlanAndAlert()
            continue

        if failureNotApprovedAsRetryable:
            parkPlanAndAlert()
            continue

        if not dueYet:
            releaseClaimUntil(nextAttemptAt)
            continue

        newId = JobOperator.restart(latest.id)

        recordNewExecutionId(newId)
        markPlanWaiting()
~~~

Một số thao tác cần được transaction hóa ở **bảng plan**, đặc biệt là claim lease và chuyển trạng thái. Nếu nhiều worker chạy đồng thời, chỉ một worker được phép claim plan tại một thời điểm. Có thể dùng conditional update theo state và version, hoặc `SELECT ... FOR UPDATE SKIP LOCKED` nếu database hỗ trợ. Cú pháp SQL, isolation và chiến lược lock phụ thuộc loại database.

**Không giữ database transaction/row lock suốt lúc Job chạy nhiều phút hoặc nhiều giờ.** Claim plan trong transaction ngắn, sau đó thực thi Job và cập nhật trạng thái plan theo kết quả. Lease có hạn giúp worker khác thu hồi một plan nếu worker sở hữu chết, nhưng thu hồi phải đọc lại JobRepository trước khi restart để tránh chạy trùng.

### 9.3. Bộ quét theo lịch

Ở Spring Scheduling, phương thức poller có thể được tổ chức như sau:

~~~java
import java.util.List;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class RecoveryPoller {

    private final RecoveryPlanStore planStore;
    private final FailureRestartService restartService;

    public RecoveryPoller(
            RecoveryPlanStore planStore,
            FailureRestartService restartService) {
        this.planStore = planStore;
        this.restartService = restartService;
    }

    @Scheduled(fixedDelay = 60_000L)
    public void processDuePlans() {

        // claimDuePlans phải sử dụng khóa hoặc compare-and-set
        // trong database để tránh nhiều node cùng claim.
        List<RecoveryPlan> plans = planStore.claimDuePlans(20);

        for (RecoveryPlan plan : plans) {
            try {
                long newExecutionId =
                        restartService.restartLatestFailedExecution(
                            plan.failedExecutionId());

                planStore.markWaiting(
                    plan.id(), newExecutionId);

            } catch (Exception error) {
                // Phân loại lỗi: retryable, race/conflict hoặc fatal.
                // Re-read JobRepository trước khi quyết định requeue.
                planStore.recordFailure(plan.id(), error);
            }
        }
    }
}
~~~

`RecoveryPlanStore` và `RecoveryPlan` là **abstraction ứng dụng cần tự triển khai** trên bảng `batch_recovery_plan`; Spring Batch không cung cấp sẵn hai type này. Đoạn code thể hiện trách nhiệm của scheduler, không phải ví dụ copy nguyên trạng là build được nếu chưa khai báo các type này.

Trong một triển khai hoàn chỉnh:

- `claimDuePlans` chỉ lấy plan đến giờ và cấp lease nguyên tử.
- `markWaiting` lưu execution ID mới, không báo thành công chỉ vì thao tác restart được chấp nhận.
- `recordFailure` phân loại lỗi; nếu Job đã được node khác restart, cập nhật plan theo execution mới thay vì tăng attempts sai.
- Một listener hoặc reconciler đọc `JobRepository` để biết JobExecution mới nhất đã `COMPLETED` hay `FAILED`, rồi cập nhật `DONE`, `PENDING` hoặc `PARKED`.
- Nếu process chết **sau khi restart thành công nhưng trước khi markWaiting**, lần poll kế tiếp phải đọc lịch sử JobExecution và xác định execution mới; không gọi restart lại từ failedExecutionId cũ.

### 9.4. Có cần dùng JobExecutionListener không?

`JobExecutionListener.afterJob` có thể phát hiện Job `FAILED` và yêu cầu tạo recovery plan:

~~~java
@Override
public void afterJob(JobExecution execution) {
    if (execution.getStatus() == BatchStatus.FAILED) {
        // Chỉ ghi một sự kiện recovery / upsert plan.
        // Không restart trực tiếp vô hạn trong callback này.
        recoveryService.registerFailure(execution);
    }
}
~~~

Điểm mạnh là phản ứng nhanh sau failure. Tuy nhiên, nếu tiến trình chết đột ngột thì `afterJob` có thể **không chạy**. Ngoài ra, việc ghi event/plan và cập nhật metadata có thể nằm ở các transaction khác nhau.

Vì vậy, thiết kế đáng tin cậy thường kết hợp:

1. Listener tạo tín hiệu sớm khi có thể.
2. Scheduler hoặc reconciler định kỳ quét JobRepository để phát hiện execution lỗi mà listener không kịp ghi plan.
3. Unique constraint theo JobInstance và logic upsert idempotent để không sinh plan trùng.

Đừng dùng listener để gọi `JobOperator.restart` ngay lập tức mỗi khi Job fail: lỗi cố định có thể tạo vòng lặp không giới hạn, lấn át backoff và che giấu nguyên nhân sự cố.

## 10. Restart, stop và recovery khi tiến trình chết

Không phải mọi lần chạy không thành công đều để lại trạng thái `FAILED`. Khi ứng dụng bị kill đột ngột hoặc mất điện, JobRepository có thể còn ghi `STARTED` dù tiến trình thực đã chết.

| Trạng thái JobExecution mới nhất | Có tự động restart ngay? | Giải thích |
| --- | --- | --- |
| `FAILED` | Có thể, sau khi policy cho phép | Phải kiểm retryable, deadline, backoff và số lần. |
| `STOPPED` | Thường cần chính sách/cho phép rõ | Có thể là một lệnh dừng bảo trì có chủ đích. |
| `COMPLETED` | Không | Cùng JobInstance đã hoàn tất. |
| `STARTED`, `STARTING` | Không | Có thể Job còn chạy, hoặc metadata bị stale sau crash. |
| `STOPPING` | Không | Đợi dừng hoàn toàn trước khi xét restart. |
| `ABANDONED` | Không | Đã bị từ bỏ, không restart theo cơ chế thông thường. |
| `UNKNOWN` | Không | Cần kiểm tra metadata/tính nhất quán. |

Với tiến trình chết bất thường:

~~~text
Monitor phát hiện execution vẫn STARTED
               |
               v
Xác minh process/pod cũ thực sự không còn chạy
               |
               v
Kiểm tra dữ liệu đã commit, side effect, checkpoint
               |
               v
Sửa trạng thái theo cơ chế recovery của phiên bản
               |
               v
Áp dụng chính sách để restart/đối soát/abandon
~~~

**Spring Batch 6.x** có `JobOperator.recover(JobExecution)` để xử lý execution đang `STARTED` nhưng bị kẹt sau shutdown đột ngột. Chỉ dùng sau khi chắc chắn không còn worker cũ đang chạy. Với **Spring Batch 5.2.x**, quy trình xử lý trạng thái stale cần dựa vào API và runbook phù hợp của phiên bản; không tùy tiện sửa trực tiếp cột `STATUS` trong `BATCH_JOB_EXECUTION`. Không nhầm recover với restart: recover xử lý metadata execution cũ; restart tạo execution mới cho JobInstance.

## 11. Scheduling trong hệ thống nhiều instance

Một ứng dụng Spring Boot có thể có ba replica:

~~~text
Pod A: @Scheduled 02:00 --> start dailyImport(D)
Pod B: @Scheduled 02:00 --> start dailyImport(D)
Pod C: @Scheduled 02:00 --> start dailyImport(D)
                         |
                         v
                   JobRepository
                   shared JDBC DB
~~~

Chung metadata store giúp framework nhận diện cùng JobInstance và chống một số tình huống chạy trùng, nhưng **không thay cho thiết kế điều phối scheduler**. Hai node có thể cùng đọc một failure và cùng quyết định restart trước khi bất kỳ node nào thực sự bắt đầu.

Các biện pháp thường dùng:

- **Một scheduler owner/leader** duy nhất cho lịch khởi chạy, hoặc scheduler tập trung bên ngoài ứng dụng.
- **Distributed lock/lease** cho recovery plan; claim atomically trước khi gọi JobOperator.
- **Unique constraint** trên business key và JobInstance; không dùng timestamp mới để vượt qua xung đột.
- **Idempotent writer** và cơ chế đối soát nếu hệ thống ngoài transaction có thể nhận side effect trùng.
- **Theo dõi execution ID mới** để biết lô nào đang chạy, thay vì chỉ dựa vào một boolean cờ `processing` trong bộ nhớ.
- **Đọc lại metadata** khi bắt lỗi xung đột, vì một node khác có thể đã restart thành công.

Nếu dùng Kubernetes CronJob, cần hiểu `concurrencyPolicy` chỉ điều khiển các Job thuộc chính CronJob đó, không tự bảo đảm độc quyền với scheduler khác cùng ghi JobRepository. Khi cần catch-up các lịch bị bỏ lỡ trong downtime, cần cấu hình cơ chế phù hợp của Quartz, Airflow hoặc bộ điều phối đã chọn.

## 12. Thiết kế nghiệp vụ an toàn khi restart

### 12.1. Idempotency

Trong hệ thống thanh toán, phép ghi có thể dựa trên khóa duy nhất:

~~~sql
CREATE TABLE settlement_result (
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (business_date, order_id)
);
~~~

Nếu một Job restart và vô tình cố ghi lại cùng cặp `(business_date, order_id)`, database sẽ phát hiện trùng. Tùy nghiệp vụ, có thể áp dụng upsert idempotent hoặc bỏ qua dữ liệu đã xác nhận hoàn tất, thay vì làm Job thất bại vĩnh viễn do vi phạm khóa. Phải xác định rõ hành vi khi giá trị cùng khóa nhưng amount khác nhau: không được âm thầm ghi đè kết quả đã chốt nếu không có quy tắc điều chỉnh.

Với HTTP, hãy tạo idempotency key **ổn định theo nghiệp vụ** như `settlement:2026-11-16:order-101`; đừng dùng JobExecution ID vì execution ID thay đổi khi restart.

### 12.2. Checkpoint và nguồn dữ liệu biến động

Reader lưu offset có thể hoạt động đúng nếu nguồn không đổi giữa các execution. Nhưng nếu có bản ghi được chèn/xóa trước offset, restart có thể bỏ sót hoặc đọc lại item. Với nguồn biến động, cân nhắc snapshot đầu vào, truy vấn theo khóa tăng dần, bảng staging, version hoặc trạng thái xử lý từng item.

### 12.3. Transaction và retry limit

Khi Step dùng `chunk(100)`, một lỗi ở item 250 thường khiến chunk hiện tại rollback trong transaction thích hợp, trong khi hai chunk trước đã commit. Scheduler không thể tự rollback hai chunk đã commit. Vì vậy, test và runbook cần xác định rõ **đơn vị khôi phục**: chunk, item, partition hoặc toàn Job.

Nếu Step có `retryLimit(3)` và scheduler cho tối đa ba JobExecution, một item có thể được thử nhiều lần qua các execution. Không suy luận tổng số lần gọi hệ thống ngoài chỉ từ `max-executions-per-instance`.

## 13. Metrics, audit và cảnh báo

Một hệ thống recovery dễ vận hành cần trả lời được:

- JobInstance nào đang thất bại và identifying JobParameters là gì?
- Execution nào fail gần nhất; Step nào fail; ExitStatus và exception là gì?
- Lỗi được phân loại retryable hay fatal theo rule nào?
- Đã thử tự động bao nhiêu lần và lần tiếp theo dự kiến lúc nào?
- Có worker nào đang giữ lease hay JobExecution mới đang chạy không?
- Lô đã hoàn thành chưa, dữ liệu đã đối soát chưa?

Các metric có thể gồm:

~~~text
batch_job_failures_total{job="dailySettlement"}
batch_job_restarts_total{job="dailySettlement",result="accepted"}
batch_job_recovery_exhausted_total{job="dailySettlement"}
batch_job_recovery_pending{job="dailySettlement"}
batch_job_recovery_oldest_pending_seconds{job="dailySettlement"}
batch_job_last_success_timestamp_seconds{job="dailySettlement"}
~~~

Đây là **tên metric gợi ý do ứng dụng tự định nghĩa**, không phải mặc định Spring Batch sinh đủ các metric này. Tránh đưa tham số cardinality cao như executionId, orderId hoặc businessDate của từng item vào label metric; các thông tin đó nên nằm trong log/trace/audit.

Khi hết số lần hoặc quá hạn nghiệp vụ, gửi cảnh báo với tên Job, business key, execution ID mới nhất, nhóm lỗi và liên kết tới dashboard/runbook. Không ghi credentials, token hoặc dữ liệu nhạy cảm từ JobParameters vào log.

## 14. Kiểm thử kịch bản chạy lại sau failure

Kiểm thử theo lịch cần đi xa hơn việc gọi `restart` một lần rồi assert status `COMPLETED`. Một bộ test nên bao phủ:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Lỗi tạm thời, sau đó hồi phục | Scheduler đợi đúng delay và restart cùng JobInstance; lần sau COMPLETED. |
| Lỗi dữ liệu không retryable | Không tạo JobExecution mới; plan chuyển PARKED và phát cảnh báo. |
| Lỗi liên tiếp | Delay tăng theo backoff; không vượt tổng execution budget. |
| Restart sau khi đã commit một chunk | Dữ liệu cuối đầy đủ, không trùng; read/checkpoint đúng. |
| JobInstance đã COMPLETED | Scheduler không tạo lại lô cũ hoặc ghi side effect mới. |
| Lần sau thay identifying parameter | Tạo JobInstance mới theo đúng nghiệp vụ, không gọi đó là restart. |
| Scheduler bị downtime qua giờ cron | Hệ thống catch-up hoặc reconciliation phát hiện lô còn thiếu, theo chính sách. |
| Hai scheduler cùng nhận plan | Chỉ một worker claim; trường hợp race không tạo side effect trùng. |
| Crash sau khi gửi restart nhưng chưa ack plan | Reconcile phát hiện execution mới và không restart lại từ execution ID cũ. |
| Execution vẫn STARTED sau mất điện | Không tự restart; cần xác minh worker đã chết và recovery metadata an toàn. |
| Stop có chủ đích | Không auto-restart khi state STOPPED nếu policy yêu cầu phê duyệt. |
| Writer gọi HTTP rồi mất response | Cùng idempotency key qua nhiều lần thử; không nhân đôi tác động. |

### 14.1. Kiểm thử với đồng hồ kiểm soát được

Tránh phụ thuộc vào `Thread.sleep(60000)` để kiểm backoff. Tách một thành phần tạo `nextAttemptAt` từ `Clock` (có thể inject) và kiểm bằng `Clock.fixed` hoặc `Clock.offset`.

Ví dụ hàm thuần để tính delay:

~~~java
import java.time.Duration;

public final class RecoveryBackoff {

    private RecoveryBackoff() {}

    public static Duration delayAfterFailure(int failureCount) {
        if (failureCount < 1) {
            throw new IllegalArgumentException("failureCount >= 1");
        }

        long minutes = 5L;
        for (int i = 1; i < failureCount; i++) {
            minutes = Math.min(minutes * 2, 60L);
        }

        return Duration.ofMinutes(minutes);
    }
}
~~~

Kỳ vọng lần lỗi thứ nhất đợi 5 phút, lần thứ hai 10 phút, lần thứ ba 20 phút, trần 60 phút. Jitter có thể thêm ở thành phần scheduler, nhưng test cần inject nguồn random có thể kiểm soát.

### 14.2. Kiểm thử restart bằng JobRepository thật

Một integration test nên sử dụng `spring-batch-test` và JDBC JobRepository:

~~~java
// Pseudocode cho Spring Batch 5.x:
// launchJob(params) lần một tạo JobExecution FAILED.
// Dùng cùng identity qua JobOperator.restart(failedExecutionId).
// JobRepository sau đó phải có 1 JobInstance và 2 JobExecution.
// Step đã COMPLETED không chạy lại theo mặc định.
// Kiểm dữ liệu nghiệp vụ: không thiếu, không trùng.

JobExecution first = jobLauncherTestUtils.launchJob(params);
assertEquals(BatchStatus.FAILED, first.getStatus());

long restartedExecutionId = jobOperator.restart(first.getId());

JobExecution second =
        jobExplorer.getJobExecution(restartedExecutionId);

// Nếu chạy async, phải chờ trạng thái cuối bằng cơ chế đồng bộ test.
assertEquals(first.getJobInstance().getInstanceId(),
             second.getJobInstance().getInstanceId());
~~~

Khi Job chạy bất đồng bộ, không nên assert `COMPLETED` ngay sau lời gọi restart. Dùng điều kiện chờ với timeout hợp lý và đọc lại repository. Không xóa bảng `BATCH_*` giữa lần fail và restart vì làm mất checkpoint và identity.

Đối với test scheduling, tách việc **quyết định đến giờ cần chạy** khỏi việc **thật sự gửi lệnh restart**. Unit test cho phép tính backoff, phân loại lỗi và eligibility; integration test xác minh JobOperator/JobRepository và dữ liệu.

## 15. Khác biệt Spring Batch 5.2.x và 6.x

Các quy tắc cốt lõi về JobInstance, JobExecution và checkpoint vẫn giữ nguyên. Tuy nhiên, API thực thi thay đổi giữa các dòng phiên bản:

| Nghiệp vụ | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Start Job từ code | `JobLauncher.run(Job, JobParameters)` | `JobOperator.start(Job, JobParameters)` là API điều hành chủ đạo. |
| Restart JobExecution cũ | `JobOperator.restart(long executionId)` trả execution ID | `JobOperator.restart(JobExecution)` trả JobExecution mới. |
| Tra cứu execution | `JobExplorer.getJobExecution(id)` | Dùng `JobRepository.getJobExecution(id)` trong mô hình API mới. |
| Stop | `JobOperator.stop(long executionId)` | `JobOperator.stop(JobExecution)`. |
| Recover metadata stale STARTED | Cần runbook phù hợp với 5.2 | `JobOperator.recover(JobExecution)` sau xác minh worker đã chết. |
| Test launcher | `JobLauncherTestUtils.launchJob(params)` | `JobOperatorTestUtils.startJob(params)`. |

Với Spring Batch 6.x, `@EnableBatchProcessing` mặc định có thể tạo resourceless infrastructure. Bài test restart và các lịch phục hồi thực tế cần **JDBC JobRepository**, schema `BATCH_*` và database tồn tại đủ lâu cho mọi execution của cùng JobInstance. Hãy cấu hình repository JDBC theo tài liệu của đúng phiên bản Batch/Boot.

Ví dụ start/restart ở 6.x:

~~~java
// Giả định đã inject JobOperator, JobRepository và Job.
JobExecution first = jobOperator.start(job, parameters);

// Khi biết execution bị FAILED và đủ điều kiện khôi phục:
JobExecution previous =
        jobRepository.getJobExecution(failedExecutionId);
JobExecution resumed = jobOperator.restart(previous);
~~~

Đây là hai ngữ cảnh sử dụng độc lập; không gọi restart khi `first` vẫn chạy. Với scheduler, luôn kiểm trạng thái persisted và chính sách trước khi restart.

## 16. Những sai lầm thường gặp

**Dùng lịch ngày hôm sau để “tự chữa” lô ngày hôm trước.** Cron ngày mới thường dùng businessDate khác, nên tạo JobInstance khác; lô cũ vẫn FAILED. Cần discovery/recovery riêng.

**Mỗi lần lỗi thêm một timestamp định danh vào JobParameters.** Việc này bỏ qua restart semantics và có thể làm xử lý trùng dữ liệu. Dùng same identity và restart JobExecution phù hợp.

**Restart ngay trong `afterJob` không giới hạn số lần.** Lỗi cấu hình hoặc dữ liệu cố định sẽ gây vòng lặp thất bại liên tục. Chuyển sang durable plan có backoff, budget và alert.

**Xem trạng thái `STARTED` sau crash là `FAILED`.** Process có thể vẫn chạy; restart khi chưa xác minh có thể khiến cùng lô được xử lý hai lần. Phải điều tra và recover metadata theo quy trình.

**Cho rằng stop là rollback tất cả dữ liệu.** Chỉ chunk chưa commit mới có thể rollback theo transaction; phần đã commit vẫn còn và phải được tôn trọng khi restart.

**Chỉ dựa vào `@Scheduled` cho hệ thống yêu cầu catch-up.** Spring Scheduling không tự lưu mọi trigger đã bị bỏ lỡ khi ứng dụng ngừng. Phải đối soát kỳ nghiệp vụ và dùng persistent scheduler hoặc queue nếu yêu cầu.

**Dùng JobRepository như một hàng đợi retry hoàn chỉnh.** Repository lưu metadata execution; nó không tự cung cấp đủ policy, backoff, deadline, claim lease và nhóm lỗi nghiệp vụ. Các phần đó thuộc recovery service/scheduler.

**Xóa metadata để cho phép chạy lại.** Làm mất lịch sử, checkpoint và thông tin chặn trùng; có thể gây mất/trùng dữ liệu. Chỉ cleanup `BATCH_*` trong database test cô lập và giữa các test độc lập.

## 17. Bài tập thực hành

### Bài 1 — Chạy theo lịch với businessDate

Tạo Job `dailyImportJob` và một `@Scheduled` chạy lúc 02:00. Dùng businessDate là identifying parameter. Giả lập Job thất bại ở ngày D nhưng đến ngày D+1 cron vẫn chạy lô mới; kiểm tra trong JobRepository thấy **hai JobInstance riêng**, một FAILED và một đang chạy hoặc COMPLETED.

### Bài 2 — Tự động restart có backoff

Tạo bảng `batch_recovery_plan` với `job_instance_id`, `failed_execution_id`, `next_attempt_at`, `state` và số lần thử. Tạo scheduler quét plan đến hạn; dùng JobOperator để restart execution cuối. Mô phỏng một lỗi tạm thời, xác minh một instance có hai JobExecution và Job cuối COMPLETED.

### Bài 3 — Chặn vòng lặp lỗi cố định

Cho processor luôn ném một exception do dữ liệu sai. Đặt tổng execution budget bằng 3. Xác nhận sau ba execution thất bại, plan chuyển PARKED và không phát sinh execution thứ tư dù scheduler vẫn chạy.

### Bài 4 — Hai scheduler cạnh tranh

Chạy hai worker cùng đọc một plan sắp đến hạn. Triển khai claim transaction với unique constraint/lease rồi chứng minh chỉ một worker gửi lệnh restart thành công. Nếu có race, worker còn lại phải đọc lại trạng thái và đối soát.

### Bài 5 — Crash giữa restart và ack

Giả lập JobOperator đã tạo execution mới nhưng recovery worker chết trước khi cập nhật plan. Khi worker khác lấy lại lease, nó phải đọc JobRepository, nhận ra execution mới và **không** restart lại từ failedExecutionId cũ.

### Bài 6 — Writer ngoài transaction

Gọi một HTTP mock với idempotency key ổn định theo businessDate và orderId. Cho HTTP server đã ghi thành công nhưng client timeout. Restart Job và xác minh mock server chỉ ghi hiệu lực nghiệp vụ một lần.

### Bài 7 — Đối soát sau downtime

Cho ứng dụng scheduler ngừng hoạt động qua hai ngày. Khi khởi động lại, triển khai reconciler so sánh các kỳ nghiệp vụ bắt buộc với các JobInstance đã tồn tại, rồi tạo đúng lô bị thiếu và lên kế hoạch phục hồi các lô FAILED. Không sinh các JobInstance trùng.

## 18. Tài liệu tham khảo

- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html)
- [Spring Batch — Advanced Metadata Usage / JobOperator](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/launch/JobOperator.html)

