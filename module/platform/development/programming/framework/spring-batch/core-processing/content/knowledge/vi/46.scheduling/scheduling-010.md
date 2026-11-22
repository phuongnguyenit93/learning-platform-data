# Run window và deadline trong Spring Batch

Trong vận hành batch, lịch chạy lúc 01:00 chưa trả lời được điều gì xảy ra nếu nguồn dữ liệu giao trễ, scheduler khởi động lại lúc 02:00 hoặc job vẫn xử lý khi hệ thống báo cáo bắt đầu phục vụ người dùng. Để điều khiển tình huống này, cần xác định **run window** (khoảng thời gian được phép bắt đầu hoặc thực thi) và **deadline** (hạn cuối mà kết quả phải sẵn sàng).

Bài học thuộc **Spring Batch Core Processing → Scheduling**, trình bày cách mô hình hóa thời gian, kiểm tra run window trước khi start, phối hợp Spring Batch với scheduler, xử lý yêu cầu đến muộn, giới hạn restart, giám sát deadline và kiểm thử theo mốc thời gian. Các ví dụ dùng Java 17, Spring Boot 3.x, Spring Batch 5.x, JUnit 5 và múi giờ `Asia/Ho_Chi_Minh`.

## 1. Phân biệt lịch kích hoạt, run window và deadline

Giả sử `dailyReportJob` tạo báo cáo cho một ngày nghiệp vụ. Đội vận hành thống nhất:

| Mốc | Giờ địa phương | Vai trò |
| --- | --- | --- |
| Planned start | 01:00 | Scheduler phát yêu cầu chạy đầu tiên |
| Window open | 01:00 | Được phép bắt đầu nếu dữ liệu sẵn sàng |
| Latest start / start cutoff | 02:30 | Từ mốc này không bắt đầu lần chạy mới |
| Finish deadline | 04:00 | Báo cáo phải hoàn thành và sẵn sàng sử dụng |
| Downstream consumption | 05:00 | Dịch vụ downstream bắt đầu đọc báo cáo |

```text
01:00                02:30                  04:00        05:00
  |--------------------|----------------------|------------|
  ^                    ^                      ^            ^
  window open          start cutoff           deadline     consumers
  |<-- allowed start -->|

  launch 01:15 ────────── finished 02:45            => đúng hạn
  launch 02:15 ────────────────── finished 04:10    => trễ deadline
  request 02:45                                     => không start mới
```

Theo quy ước của bài này, cửa sổ cho phép **khởi chạy** là `[01:00, 02:30)`: bao gồm 01:00, không bao gồm 02:30. Một phiên chạy đã bắt đầu lúc 02:15 có thể tiếp tục sau 02:30, vì **start cutoff không phải thời điểm buộc dừng job**.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Trigger time | Khi nào scheduler gửi yêu cầu? | 01:00 |
| Run window | Khi nào được nhận yêu cầu start? | `[01:00, 02:30)` |
| Data readiness | Đầu vào đã đủ, ổn định chưa? | File upstream đã báo `READY` |
| Start cutoff | Khi nào ngừng cố gắng start? | 02:30 |
| Finish deadline | Muộn nhất khi nào output phải dùng được? | 04:00 |
| Execution timeout | Một execution có thể chạy tối đa bao lâu? | 90 phút từ lúc bắt đầu |
| SLA/SLO | Mức độ đáp ứng hạn cam kết? | Ví dụ 99% ngày có kết quả trước 04:00 |

**Timeout tương đối** không phải **deadline tuyệt đối**: timeout 90 phút tính từ lúc job bắt đầu, còn deadline 04:00 cố định theo ngày vận hành. Nếu job khởi chạy muộn, timeout vẫn còn nhưng kết quả có thể đã vượt deadline. Khi định nghĩa deadline, cần làm rõ trạng thái `COMPLETED` đã đủ chưa, hay còn phải commit database, xác nhận file đầu ra hoặc publish dữ liệu cho downstream.

## 2. Spring Batch phối hợp với scheduler như thế nào?

Spring Batch quản lý `Job`, `Step`, transaction, retry, restart và metadata trong `JobRepository`. Nó không thay thế toàn bộ chức năng lập lịch và điều phối theo thời gian. Các lựa chọn thường gặp:

- **Spring `@Scheduled`**: ứng dụng đang chạy tự phát trigger theo cron; đơn giản khi lịch ít và ứng dụng có vòng đời dài.
- **Quartz**: trigger bền vững, misfire policy và lịch phức tạp khi được cấu hình phù hợp.
- **Cron / Windows Task Scheduler**: khởi động một tiến trình `java -jar` theo lịch.
- **Kubernetes CronJob hoặc orchestrator**: tạo workload định kỳ và quản lý mức độ đồng thời, retry ở tầng điều phối.

Luồng nên có bước kiểm tra chính sách ngay **lúc nhận yêu cầu khởi chạy**:

```text
Scheduler ──> Launch request(t, scheduledDate)
                      |
                      v
                RunWindowPolicy
                   |          |
            outside window    in window
                   |          |
               skip/alert     v
                          Data readiness
                           |        |
                       NOT READY   READY
                           |        |
                        wait/retry  v
                              JobLauncher
                                  |
                                  v
                               Spring Batch
                                  |
                                  v
                           Deadline monitor
```

Một cron expression chỉ mô tả thời điểm **đáng lẽ trigger được phát**. Nếu hệ thống gặp sự cố, yêu cầu có thể đến trễ. Vì vậy không thể dựa vào việc “cron chỉ chạy lúc 01:00” để kết luận job luôn bắt đầu trong run window.

## 3. Ngày nghiệp vụ, timezone và cửa sổ vắt qua nửa đêm

### 3.1. Xác định múi giờ nghiệp vụ

Không để ngày nghiệp vụ phụ thuộc vào timezone mặc định của container hoặc laptop. Ví dụ:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate scheduledDate = LocalDate.of(2026, 11, 16);

Instant open = scheduledDate.atTime(1, 0)
        .atZone(zone).toInstant();
Instant cutoff = scheduledDate.atTime(2, 30)
        .atZone(zone).toInstant();
Instant deadline = scheduledDate.atTime(4, 0)
        .atZone(zone).toInstant();
```

`Instant` là một thời điểm trên trục UTC, thích hợp để so sánh và lưu log; `ZonedDateTime` cho biết ý nghĩa giờ địa phương theo một vùng cụ thể. Ngày `2026-11-16` lúc 01:00 tại `Asia/Ho_Chi_Minh` tương ứng `2026-11-15T18:00:00Z`.

**Scheduled date không nhất thiết là business date.** Ví dụ scheduler chạy 01:00 ngày 16/11 để xử lý doanh thu của ngày 15/11:

```java
LocalDate scheduledDate = LocalDate.now(zone);
LocalDate businessDate = scheduledDate.minusDays(1);
```

Chỉ dùng `minusDays(1)` nếu đó thực sự là hợp đồng dữ liệu của job. Với thao tác backfill, phải truyền `businessDate` mục tiêu cụ thể, không tự lấy ngày hiện tại.

### 3.2. Run window băng qua ngày

Một job khác được phép bắt đầu từ 23:00 ngày D đến 02:00 ngày D+1. So sánh giờ bằng biểu thức `time >= 23:00 && time < 02:00` sẽ sai. Thay vào đó, tạo **hai mốc ngày-giờ đầy đủ**:

```java
Instant start = businessDate.atTime(23, 0)
        .atZone(zone).toInstant();

Instant end = businessDate.plusDays(1).atTime(2, 0)
        .atZone(zone).toInstant();

boolean allowed = !now.isBefore(start) && now.isBefore(end);
```

Ở đây `now` là `Instant`. Nếu hệ thống vận hành ở vùng có giờ mùa hè (DST), một giờ địa phương có thể bị bỏ qua hoặc lặp lại; cần định nghĩa cách xử lý riêng. `Asia/Ho_Chi_Minh` hiện không áp dụng DST nhưng code đa quốc gia vẫn nên sử dụng `ZoneId` thay cho offset cố định theo giả định.

## 4. Mô hình hóa run window thành policy riêng

Thay vì rải điều kiện thời gian vào tasklet, service và script, có thể tạo một đối tượng **thuần logic thời gian**. Policy nhận thời điểm thực tế cùng ngày của cửa sổ, trả về quyết định có được bắt đầu hay không và deadline tương ứng.

File `RunWindowPolicy.java`:

```java
package com.example.batch.schedule;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.springframework.stereotype.Component;

@Component
public class RunWindowPolicy {

    public static final ZoneId ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    public record Decision(
            boolean allowed,
            String reason,
            Instant finishDeadline) {}

    public Decision evaluate(
            Instant requestedAt, LocalDate scheduledDate) {

        Instant open = scheduledDate.atTime(1, 0)
                .atZone(ZONE).toInstant();
        Instant cutoff = scheduledDate.atTime(2, 30)
                .atZone(ZONE).toInstant();
        Instant deadline = scheduledDate.atTime(4, 0)
                .atZone(ZONE).toInstant();

        if (requestedAt.isBefore(open)) {
            return new Decision(
                    false, "BEFORE_WINDOW", deadline);
        }
        if (!requestedAt.isBefore(cutoff)) {
            return new Decision(
                    false, "START_CUTOFF_PASSED", deadline);
        }
        return new Decision(true, "IN_WINDOW", deadline);
    }
}
```

Các ranh giới được xác định rõ: đúng 01:00 được phép start, đúng 02:30 không còn được phép start. `scheduledDate` gắn với lịch, không bắt buộc trùng `businessDate` mà job sẽ đọc.

Việc tách policy giúp sử dụng cùng quy tắc ở API khởi chạy, scheduler nội bộ hoặc hệ thống điều phối bên ngoài. Các điều kiện khác như **upstream đã sẵn sàng**, **còn đủ ngân sách thời gian** và **có quyền chạy bù** có thể được bổ sung thành các bước quyết định riêng.

## 5. Tích hợp `@Scheduled` và `JobLauncher`

Với Spring Framework, cron trong `@Scheduled` dùng sáu trường: **giây, phút, giờ, ngày trong tháng, tháng, ngày trong tuần**. Để thử khởi chạy mỗi 15 phút trong hai giờ 01 và 02:

```java
@Scheduled(
    cron = "0 0,15,30,45 1-2 * * *",
    zone = "Asia/Ho_Chi_Minh")
```

Biểu thức này phát trigger lúc 01:00, 01:15, ..., 02:45. Policy phần 4 sẽ từ chối yêu cầu lúc 02:30 và 02:45. Trigger lặp lại hữu ích khi dữ liệu nguồn đến muộn hoặc khi job cần restart, nhưng phải chống xử lý trùng.

Nếu ứng dụng dùng `@Scheduled` làm cơ chế khởi chạy, nên tắt runner tự động của Spring Boot:

```properties
spring.batch.job.enabled=false
```

Nếu không, Boot có thể tự chạy job ngay khi application context khởi tạo, đồng thời scheduler tiếp tục gọi theo lịch.

### 5.1. Sử dụng `Clock` để test được thời gian

```java
package com.example.batch.schedule;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Lấy `Instant` từ đồng hồ rồi diễn giải theo `RunWindowPolicy.ZONE` để xác định ngày lịch; trong test thay bằng `Clock.fixed(...)`.

### 5.2. Scheduler thực sự gọi Spring Batch

Giả sử application context có bean `Job` mang tên `dailyReportJob`:

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
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
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ScheduledDailyReport {

    private static final Logger log =
            LoggerFactory.getLogger(ScheduledDailyReport.class);

    private final JobLauncher launcher;
    private final Job dailyReportJob;
    private final RunWindowPolicy policy;
    private final Clock clock;

    public ScheduledDailyReport(
            JobLauncher launcher,
            @Qualifier("dailyReportJob") Job dailyReportJob,
            RunWindowPolicy policy,
            Clock clock) {
        this.launcher = launcher;
        this.dailyReportJob = dailyReportJob;
        this.policy = policy;
        this.clock = clock;
    }

    @Scheduled(
        cron = "0 0,15,30,45 1-2 * * *",
        zone = "Asia/Ho_Chi_Minh")
    public void launchWithinWindow() {
        Instant now = clock.instant();
        LocalDate scheduledDate =
                LocalDate.ofInstant(now, RunWindowPolicy.ZONE);

        RunWindowPolicy.Decision decision =
                policy.evaluate(now, scheduledDate);
        if (!decision.allowed()) {
            log.info("Skip launch: date={}, reason={}",
                    scheduledDate, decision.reason());
            return;
        }

        // Nếu job xử lý ngày trước, thay bằng
        // scheduledDate.minusDays(1) theo hợp đồng nghiệp vụ.
        LocalDate businessDate = scheduledDate;

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("region", "VN", true)
                .toJobParameters();

        try {
            JobExecution execution =
                    launcher.run(dailyReportJob, parameters);

            log.info("Job execution: id={}, date={}, status={}",
                    execution.getId(), businessDate,
                    execution.getStatus());

            if (execution.getStatus() == BatchStatus.FAILED) {
                log.error("Batch execution failed: id={}",
                        execution.getId());
            }
        } catch (JobInstanceAlreadyCompleteException e) {
            log.info("Already completed: {}", businessDate);
        } catch (JobExecutionAlreadyRunningException e) {
            log.info("Already running: {}", businessDate);
        } catch (JobRestartException
                | JobParametersInvalidException e) {
            log.error("Could not start batch: {}", businessDate, e);
        }
    }
}
```

Bật scheduling:

```java
@SpringBootApplication
@EnableScheduling
public class ReportBatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportBatchApplication.class, args);
    }
}
```

Các import là `org.springframework.boot.autoconfigure.SpringBootApplication`, `org.springframework.boot.SpringApplication` và `org.springframework.scheduling.annotation.EnableScheduling`.

Ví dụ này cố ý giữ hai **identifying parameters** `businessDate` và `region` ổn định cho cùng ngày/khu vực. Nếu thêm `run.id` ngẫu nhiên ở mỗi trigger, mọi lần có thể tạo `JobInstance` mới và xử lý lặp. Khi dùng `JobRepository` bền vững:

- Instance `COMPLETED` thường không chạy lại; launcher ném `JobInstanceAlreadyCompleteException`.
- Một execution của cùng instance còn đang chạy có thể bị từ chối bằng `JobExecutionAlreadyRunningException`.
- Instance `FAILED` có thể được **restart** bằng cùng identifying parameters nếu job cho phép.

Không nên restart tự động vô hạn: cần chính sách phân loại lỗi, số lần restart tối đa, khoảng cách giữa các lần thử và ngân sách thời gian còn lại.

**Giới hạn của ví dụ:** `JobLauncher` có thể được cấu hình đồng bộ hoặc bất đồng bộ. Với launcher bất đồng bộ, `run(...)` có thể trả về khi job vẫn `STARTING`/`STARTED`; trạng thái cuối cùng phải được theo dõi riêng. Một scheduled method chạy lâu cũng có thể chiếm thread của scheduler. Cấu hình pool hoặc kiến trúc dispatch cần phù hợp với runtime thực tế.

`launchWithinWindow()` chỉ chặn **start ngoài cửa sổ**. Nó chưa giám sát việc job hoàn thành trước 04:00; deadline cần một cơ chế bổ sung.

## 6. Kiểm tra còn đủ thời gian trước khi khởi chạy

Ngoài start cutoff, vận hành có thể đưa vào *latest safe start*: thời điểm bắt đầu muộn nhất còn đủ ngân sách để hoàn tất trước deadline.

Ví dụ với deadline 04:00:

| Thành phần | Ngân sách |
| --- | ---: |
| Runtime dự kiến theo giới hạn thiết kế | 75 phút |
| Retry/recovery dự trù | 15 phút |
| Dự phòng publish và downstream | 10 phút |
| **Tổng** | **100 phút** |

Theo giả định đó, start sau 02:20 sẽ không còn đủ 100 phút đến 04:00. Dù start cutoff hành chính là 02:30, chính sách bảo đảm ngân sách cần chọn mốc sớm hơn.

```text
remaining_budget = finish_deadline - now
required_budget = expected_runtime + retry_budget + safety_margin

Cho phép start khi:
  trong run window
  AND upstream READY
  AND remaining_budget >= required_budget
```

Ví dụ Java:

```java
Duration requiredBudget = Duration.ofMinutes(100);
Instant lastSafeStart = finishDeadline.minus(requiredBudget);
boolean enoughTime = !now.isAfter(lastSafeStart);
```

Ở đây `finishDeadline` và `now` là `Instant`. Logic này có thể thêm vào `RunWindowPolicy` và trả `INSUFFICIENT_TIME_BEFORE_DEADLINE` khi không đủ ngân sách. Hãy chọn runtime ước lượng từ số liệu vận hành thật, có dự phòng cho dữ liệu đột biến và retry.

Tuy vậy, ngân sách đủ **không bảo đảm** job chắc chắn hoàn thành đúng hạn: database có thể treo, I/O có thể chậm hoặc dữ liệu nguồn có thể phát sinh lỗi. Cần theo dõi deadline thực tế.

## 7. Giám sát deadline và xử lý quá hạn

Đặt mốc 04:00 chỉ có ý nghĩa khi xác định được **điều kiện hoàn thành** và **hành động khi chưa hoàn thành**.

### 7.1. Soft deadline và hard deadline

| Chính sách | Ví dụ | Hành động |
| --- | --- | --- |
| Soft deadline | 03:30 chưa có output | Cảnh báo, đánh giá ETA, vẫn cho chạy |
| Hard deadline | 04:00 chưa có output được chấp nhận | Ghi nhận SLA breach, ngăn publish hoặc yêu cầu dừng có kiểm soát |
| Data cutoff | Không nhận dữ liệu nguồn mới sau 04:00 | Đóng snapshot, xử lý phần còn lại theo quy tắc |

**Deadline không mặc nhiên đồng nghĩa với kill JVM.** Dừng process cưỡng bức có thể khiến file xuất hoặc giao dịch bên ngoài ở trạng thái dở dang. Với hệ thống yêu cầu dữ liệu toàn vẹn, có thể đánh dấu bản kết quả trễ rồi tiếp tục job, dùng dữ liệu dự phòng hoặc gửi yêu cầu graceful stop tùy hợp đồng nghiệp vụ.

Một deadline monitor thường cần:

1. Xác định đúng `JobInstance` theo job name và identifying parameters của ngày nghiệp vụ.
2. Đọc `JobExecution` mới nhất và trạng thái các step từ `JobExplorer` hoặc nguồn giám sát.
3. Kiểm tra cả **output đã commit/publish** hay chưa, thay vì chỉ nhìn `BatchStatus.COMPLETED`.
4. Khi đến deadline, phát metric/alert với `scheduledDate`, `businessDate`, `executionId`, `deadlineAt`, thời gian trễ và kết quả.
5. Nếu chính sách cần dừng, gửi stop request rồi theo dõi đến khi execution thực sự kết thúc.

Spring Batch cung cấp `JobOperator` để quản trị execution. Ví dụ:

```java
// executionId được lấy từ JobRepository / JobExplorer
// sau khi xác định đúng phiên thực thi cần dừng.
boolean stopRequested = jobOperator.stop(executionId);
```

Lời gọi này là **yêu cầu dừng**, không phải lời cam kết step dừng tức khắc. Tasklet đang block lâu hoặc chunk đang xử lý I/O có thể chỉ phản hồi khi tới điểm dừng thích hợp. `stop(...)` còn có thể trả về `false` hoặc ném exception tùy trạng thái execution.

Nếu nghiệp vụ cần deadline cứng, nên thiết kế:

- Timeout cho các kết nối/HTTP/SQL và xử lý I/O.
- Chunk và transaction có độ dài kiểm soát được, hỗ trợ stop/restart.
- Output tạm; chỉ **publish bản hoàn chỉnh** cho downstream.
- Idempotency, checkpoint và kế hoạch tiếp tục sau lỗi.
- Quy tắc fallback khi không thể hoàn thành đúng hạn.

### 7.2. Quan sát metadata và metric

Các trường log hoặc metric hữu ích:

```text
jobName=dailyReportJob
businessDate=2026-11-16
scheduledAt=2026-11-16T01:00:00+07:00
actualStartedAt=2026-11-16T01:15:12+07:00
finishedAt=2026-11-16T03:47:02+07:00
deadlineAt=2026-11-16T04:00:00+07:00
batchStatus=COMPLETED
outputPublished=true
deadlineMet=true
```

Ví dụ truy vấn metadata (schema mặc định Spring Batch):

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailyReportJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Trong môi trường thật cần lọc tiếp theo tham số nhận diện hoặc dùng `JobExplorer`, vì cùng một job có thể có nhiều instance cho các ngày khác nhau. Metric có thể gồm `scheduled_to_start_delay`, `duration`, `deadline_breaches`, `data_freshness` và `remaining_budget_at_launch`.

## 8. Run window khi dùng external scheduler

### 8.1. Cron chạy executable JAR

Với cron hoặc hệ thống điều phối chỉ khởi chạy tiến trình, ứng dụng có thể dùng cơ chế tự chạy job của Spring Boot:

```bash
#!/usr/bin/env bash
set -euo pipefail

BUSINESS_DATE="$1"
exec java -jar /opt/batch/report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  "businessDate=$BUSINESS_DATE" \
  region=VN
```

Ở cách này `spring.batch.job.enabled=true` (hoặc không bị tắt), vì Boot cần tự chạy job khi JVM startup. Cron trigger chỉ nêu **khi nào gửi yêu cầu**; kiểm tra data readiness, run window và deadline vẫn phải do script, ứng dụng hoặc orchestrator bảo đảm.

Để scheduler biết job thất bại, process exit code phải phản ánh đúng kết quả batch. `JobExecution` có `FAILED` không đảm bảo trong mọi cấu hình JVM đều trả exit code khác 0; nên có cơ chế `ExitCodeGenerator`, launcher hoặc kiểm tra trạng thái repository phù hợp.

### 8.2. Kubernetes CronJob

Ví dụ khung YAML:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-report
spec:
  schedule: "0 1 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 5400
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: report
              image: example/report-batch:1.0
              args:
                - "--spring.batch.job.name=dailyReportJob"
                - "businessDate=2026-11-16"
                - "region=VN"
```

Đây là **khung minh họa**, cần thay image và cách xác định `businessDate` động trước khi dùng trong sản xuất. Đặc biệt:

- Cron Kubernetes thường dùng **năm trường**, khác Spring `@Scheduled` sáu trường.
- `timeZone` cần phiên bản Kubernetes hỗ trợ trường đó.
- `concurrencyPolicy: Forbid` tránh chạy chồng các Job từ cùng CronJob, không ngăn job do hệ thống bên ngoài khởi chạy.
- `startingDeadlineSeconds: 5400` giới hạn độ trễ khởi chạy cho một **scheduled occurrence**, không phải cam kết hoàn tất trước 04:00.
- `activeDeadlineSeconds` nếu đặt trong `jobTemplate.spec` là timeout **tính từ lúc Kubernetes Job hoạt động**, không trực tiếp biểu diễn deadline tuyệt đối của ngày nghiệp vụ.
- `backoffLimit` và pod restart có thể khiến JAR được gọi lại với cùng `JobParameters`. Phải phối hợp với restart và idempotency của Spring Batch.

Muốn giám sát mốc 04:00, vẫn cần một chính sách hoặc monitor đọc được ngày nghiệp vụ và trạng thái output.

## 9. Đến muộn, restart và backfill

### 9.1. Yêu cầu đến muộn nhưng còn trong cửa sổ

Trigger dự kiến 01:00 nhưng đến lúc 01:40. Nếu dữ liệu đã `READY` và còn đủ ngân sách tới deadline, policy có thể cho start. Cần ghi cả thời điểm dự kiến và thời điểm thật để phân biệt **scheduler delay** với **job runtime**.

### 9.2. Yêu cầu đến sau start cutoff

Scheduler phục hồi lúc 03:00 khi cutoff là 02:30. Không tự động đưa yêu cầu này vào đường chạy bình thường. Nên đánh dấu `MISSED_WINDOW`, cảnh báo và để orchestration quyết định xử lý bù hoặc chuyển sang kế hoạch dự phòng.

### 9.3. Job chạy qua cutoff

Job bắt đầu 02:15 và vẫn đang xử lý lúc 02:40 **không tự động vi phạm start window**. Chỉ khi vượt deadline hoàn thành (hoặc timeout/điều kiện riêng) thì mới vi phạm quy tắc tương ứng.

### 9.4. Restart một instance thất bại

Giả sử job bắt đầu 01:00 và `FAILED` lúc 01:20. Nếu được phép restart, có thể launch lại lúc 01:30 bằng **cùng identifying `JobParameters`** để Spring Batch sử dụng metadata và checkpoint:

```text
JobInstance(date=2026-11-16, region=VN)
├── JobExecution #1: FAILED
└── JobExecution #2: COMPLETED   (restart cùng instance)
```

Nếu thay bằng `run.id` identifying mới, Spring Batch có thể tạo một instance khác và xử lý dữ liệu từ đầu. Vì thế cần tách rõ **restart** với **run lại một instance mới**. Retry trong một execution lại là cơ chế khác với restart.

### 9.5. Backfill ngoài lịch thông thường

Ví dụ ngày 16/11 mới phát hiện phải xử lý lại dữ liệu ngày 10/11. Đây là **backfill có chủ đích**, không phải một scheduled trigger đến muộn. Nên có đường vận hành riêng với `businessDate` được truyền tường minh, quyền kích hoạt phù hợp, nhật ký lý do và quy tắc tránh ghi đè kết quả đã phát hành.

Không sửa đồng hồ hệ thống hay xóa metadata `BATCH_*` chỉ để “lọt qua” run window hoặc chạy lại một job đã hoàn thành.

## 10. Kiểm thử ranh giới thời gian bằng JUnit 5

Không nên để bài test phải chờ đến 01:00 thật. Vì `RunWindowPolicy` nhận `Instant`, có thể truyền trực tiếp những thời điểm xác định. Khi test scheduler, dùng `Clock.fixed` để mô phỏng giờ.

Ví dụ `RunWindowPolicyTest.java`:

```java
package com.example.batch.schedule;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class RunWindowPolicyTest {

    private final RunWindowPolicy policy = new RunWindowPolicy();
    private final LocalDate date = LocalDate.of(2026, 11, 16);

    @Test
    void rejectsBeforeWindow() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T17:59:59Z"), date);
        assertThat(d.allowed()).isFalse();
        assertThat(d.reason()).isEqualTo("BEFORE_WINDOW");
    }

    @Test
    void permitsExactlyAtOpening() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T18:00:00Z"), date);
        assertThat(d.allowed()).isTrue();
    }

    @Test
    void rejectsAtStartCutoff() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T19:30:00Z"), date);
        assertThat(d.allowed()).isFalse();
        assertThat(d.reason()).isEqualTo("START_CUTOFF_PASSED");
    }

    @Test
    void computesDeadline() {
        var d = policy.evaluate(
                Instant.parse("2026-11-15T19:00:00Z"), date);
        assertThat(d.finishDeadline()).isEqualTo(
                Instant.parse("2026-11-15T21:00:00Z"));
    }
}
```

Các `Instant` trên ứng với các mốc giờ `Asia/Ho_Chi_Minh`: 00:59:59, 01:00, 02:30 và 04:00 của ngày 16/11/2026.

Giả lập đồng hồ khi cần test `ScheduledDailyReport`:

```java
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-15T18:15:00Z"),
        ZoneOffset.UTC
);
```

Có thể mock `JobLauncher` để xác nhận chỉ gọi `run(...)` khi policy cho phép. Với integration test dùng `JobRepository`, kiểm tra thêm `JobInstance`/`JobExecution` để chắc rằng trigger trùng không tạo đợt xử lý ngoài ý muốn.

| Kịch bản | Thời điểm / trạng thái | Kỳ vọng |
| --- | --- | --- |
| Trước cửa sổ | 00:59:59 | Từ chối start |
| Đúng lúc mở | 01:00:00 | Cho phép nếu upstream sẵn sàng |
| Giữa cửa sổ | 01:45 | Có thể start nếu đủ ngân sách |
| Ngay trước cutoff | 02:29:59 | Chưa bị chặn bởi cutoff, nhưng phải xét deadline |
| Đúng cutoff | 02:30:00 | Từ chối start mới |
| Hoàn thành trước hạn | 03:59:59 | Đúng hạn nếu output được chấp nhận |
| Hoàn thành sau hạn | 04:00:01 | Ghi nhận trễ deadline |
| Cùng instance đã `COMPLETED` | Trigger tiếp theo | Không chạy lại như instance mới |
| Instance `FAILED` | Trong cửa sổ | Restart nếu chính sách cho phép |
| Scheduler phục hồi muộn | 03:15 | Ghi missed window, không start tự động |

Với hệ thống ở vùng DST, cần bổ sung ca test ngày đổi giờ, vì thời điểm cron và thời lượng cửa sổ có thể không giống ngày thông thường.

## 11. Các lỗi thiết kế dễ gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Job chạy hai lần trong cùng ngày | Mỗi trigger tạo `run.id` ngẫu nhiên | Dùng identifying parameters ổn định |
| Job chạy ngay khi service khởi động | Boot startup runner và `@Scheduled` cùng bật | Đặt `spring.batch.job.enabled=false` cho cách dùng `@Scheduled` |
| Job start sau cutoff | Chỉ tin cron, không kiểm tra thời gian thực tế | Đánh giá policy tại thời điểm launch |
| Job kết thúc quá hạn dù timeout chưa hết | Dùng timeout tương đối thay cho deadline tuyệt đối | Giám sát deadline theo ngày nghiệp vụ |
| Không restart từ checkpoint | Đổi identifying parameters hoặc mất metadata | Giữ định danh instance và repository bền vững |
| Báo cáo sai ngày | Nhầm scheduled date với business date | Định nghĩa ngày nghiệp vụ tường minh |
| Job bị kill, output dang dở | Dừng tiến trình cưỡng bức khi đến hạn | Dùng graceful stop và publish output an toàn |
| Hai tầng tự retry liên tục | Orchestrator retry và Spring Batch restart không có ngân sách chung | Giới hạn tổng số lượt, thời gian và điều kiện retry |
| Nhiều replica đều kích hoạt cron | Mỗi replica có `@Scheduled` riêng | Một bộ điều phối hoặc cơ chế khóa/định danh dùng chung |
| `COMPLETED` nhưng downstream chưa dùng được | Chỉ kiểm tra BatchStatus | Định nghĩa “done” gắn với commit/publish |

## 12. Bài thực hành

Hãy thiết kế lịch cho `dailyReportJob` với run window `[01:00, 02:30)`, finish deadline 04:00 và timezone `Asia/Ho_Chi_Minh`:

1. Viết `RunWindowPolicy` và kiểm tra bốn mốc biên 00:59:59, 01:00:00, 02:29:59, 02:30:00 bằng JUnit 5.
2. Thêm điều kiện data readiness: chỉ start nếu file hoặc bảng dữ liệu upstream đã ở trạng thái `READY`.
3. Cấu hình scheduler chạy kiểm tra mỗi 15 phút. Truyền `businessDate` làm identifying parameter ổn định để trigger trùng không tạo xử lý độc lập ngoài ý muốn.
4. Mô phỏng job `FAILED` lúc 01:20 rồi restart lúc 01:30. Xác định những tham số phải giữ nguyên để restart cùng `JobInstance`.
5. Thêm ngân sách 100 phút. Giải thích vì sao tại 02:21 cần từ chối start dù chưa tới cutoff 02:30.
6. Thiết kế monitor tại 04:00: nếu job vẫn `STARTED` hoặc output chưa publish, ghi SLA breach và kích hoạt phương án xử lý đã chọn.
7. Thử triển khai bằng Kubernetes CronJob; phân biệt `startingDeadlineSeconds`, `activeDeadlineSeconds` và mốc nghiệp vụ 04:00.
8. Tạo trường hợp backfill dữ liệu của một ngày cũ trong giờ hành chính, với ngày nghiệp vụ tường minh và kiểm soát ghi dữ liệu trùng.

Trong scheduling Spring Batch, **run window trả lời khi nào được phép bắt đầu**, còn **deadline xác định khi nào kết quả phải sẵn sàng**. Kết hợp hai quy tắc với `JobParameters`, `JobRepository`, restart, timezone và quan sát output thực tế giúp hệ thống chạy ổn định khi scheduler đến trễ, dữ liệu nguồn thay đổi hoặc một lần xử lý thất bại.
