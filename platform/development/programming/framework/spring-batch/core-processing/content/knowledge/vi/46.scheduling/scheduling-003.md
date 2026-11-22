# Prevent overlapping execution trong Spring Batch Scheduling

Khi một Spring Batch Job được kích hoạt theo lịch, lần chạy trước có thể vẫn đang xử lý khi lịch tiếp theo đến. Nếu hai lần chạy cùng đọc một nguồn dữ liệu, cập nhật cùng bảng, tạo cùng báo cáo hoặc gửi cùng thông báo, hệ thống có thể ghi trùng, tranh chấp khóa và khó khôi phục sau lỗi.

**Prevent overlapping execution** là thiết kế để ngăn những lần thực thi không được phép diễn ra cùng lúc. Trong Spring Batch, cần xác định chính xác phạm vi muốn ngăn chồng lấn: **cùng một `JobInstance`**, **mọi lần chạy của cùng Job**, hay **mọi tiến trình trong một cụm ứng dụng**. Mỗi phạm vi đòi hỏi cơ chế kiểm soát khác nhau.

Bài học thuộc chủ đề *Scheduling* của *Spring Batch Core Processing*. Nội dung bao gồm cơ chế của `JobRepository`, giới hạn của `@Scheduled`, giải pháp cho một JVM và nhiều instance, ví dụ cấu hình khóa phân tán, cách kiểm thử concurrency và các tình huống vận hành.

## 1. Overlapping execution là gì?

Giả sử `settlementJob` tổng hợp các giao dịch chưa quyết toán. Job được đặt lịch mỗi 5 phút, nhưng một lần chạy có thể mất 8 phút:

```text
Thời gian       10:00      10:05      10:08      10:10      10:13
                |----------|----------|----------|----------|
Lịch chạy       A          B                     C

Job A           [-----------------------]
Job B                      [-----------------------]
                                ^^^^^^^
                                A và B chạy chồng lấn
```

Nếu cả A và B cùng chọn các giao dịch có trạng thái `PENDING` rồi cùng ghi kết quả, có thể xảy ra:

- Ghi trùng đơn thanh toán hoặc hai lần gửi cùng một lệnh ra hệ thống bên ngoài.
- Cập nhật chồng lên nhau khiến trạng thái cuối không đúng.
- Hai Job giữ khóa database và chờ lẫn nhau, gây deadlock hoặc timeout.
- Một Job di chuyển/ghi đè file trong khi Job khác vẫn đang đọc.
- Bộ đếm và lịch sử chạy khó hiểu vì nhiều `JobExecution` cùng tồn tại.

Không phải mọi việc chạy đồng thời đều sai. Hai Job xử lý hai tập dữ liệu hoàn toàn độc lập có thể chạy song song hợp lệ. Trước khi thêm khóa, hãy định nghĩa **tài nguyên và phạm vi độc quyền** cần bảo vệ.

## 2. Ba phạm vi chống chạy chồng lấn

| Phạm vi | Ví dụ | Cơ chế phù hợp |
| --- | --- | --- |
| **Cùng `JobInstance`** | Hai lời gọi cùng tên Job và cùng identifying JobParameters. | `JobRepository` của Spring Batch ngăn các `JobExecution` đang chạy cho cùng instance. |
| **Cùng Job, khác `JobInstance`** | `settlementJob` cho cửa sổ 10:00 và 10:05 chạy đồng thời. | Một khóa theo tên Job/tài nguyên dùng chung hoặc cơ chế xếp hàng thực thi. |
| **Nhiều JVM/container/pod** | Hai instance Spring Boot đều có `@Scheduled` và cùng kích hoạt Job. | Khóa phân tán, scheduler có coordination, hoặc một scheduler trung tâm. |

Một nguyên tắc quan trọng:

> **`JobRepository` không tự ngăn mọi lần chạy của cùng tên Job.** Nó kiểm soát trạng thái và tính hợp lệ theo `JobInstance`. Hai bộ identifying parameters khác nhau tạo thành hai JobInstance khác nhau, do đó chúng *có thể* chạy đồng thời.

Ví dụ:

```text
Job: settlementJob

JobInstance X
  parameters: {window=2026-11-16T10:00Z}
  execution:  #101 STARTED

JobInstance Y
  parameters: {window=2026-11-16T10:05Z}
  execution:  #102 STARTED

=> Cả hai cùng STARTED là tình huống có thể xảy ra.
```

Nếu X và Y cùng cập nhật một tài nguyên nghiệp vụ, cần thêm cơ chế độc quyền ở cấp Job/tài nguyên ngoài kiểm tra JobInstance.

## 3. Spring Batch ngăn chạy trùng cùng `JobInstance` như thế nào?

Trong Spring Batch:

- `Job` là định nghĩa quy trình.
- `JobInstance` được xác định bằng **tên Job + identifying JobParameters**.
- `JobExecution` là một lần cố gắng thực thi JobInstance; một instance có thể có nhiều execution trong các lần restart.

Giả sử hai lời gọi:

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .toJobParameters();

jobLauncher.run(settlementJob, params);
```

Nếu một JobExecution của cùng JobInstance còn đang chạy, repository thường từ chối yêu cầu khởi chạy thứ hai bằng `JobExecutionAlreadyRunningException`. Nếu instance đã hoàn thành, thử khởi chạy lại cùng parameters có thể nhận `JobInstanceAlreadyCompleteException`. Nếu instance trước đó thất bại và Job cho phép restart, lần gọi tiếp theo có thể tạo một `JobExecution` mới để restart.

Bảng sau cho thấy ý nghĩa của trạng thái trước đó khi yêu cầu cùng bộ identifying parameters:

| Trạng thái trước đó | Hành vi thường gặp |
| --- | --- |
| `STARTING`, `STARTED` hoặc trạng thái còn đang chạy | Từ chối chạy đồng thời cho cùng JobInstance. |
| `COMPLETED` | Không khởi chạy lại một instance đã hoàn thành. |
| `FAILED`, `STOPPED` | Có thể restart theo cấu hình Job/Step và metadata hiện có. |
| `ABANDONED` hoặc metadata không nhất quán | Cần xử lý theo khả năng restart và quy trình vận hành; không tùy tiện xóa trạng thái. |

Các điều kiện này phụ thuộc vào repository được cấu hình chính xác, giao dịch tạo execution và dữ liệu metadata. Các node muốn phối hợp qua `JobRepository` phải cùng sử dụng một backend nhất quán; một database metadata riêng cho từng node không tạo được bảo vệ chung.

### Vì sao tham số ngẫu nhiên không chống overlap?

Nhiều ví dụ chạy Job dùng:

```java
new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
```

Tham số định danh mới thường tạo **JobInstance mới**. Nó có ích khi muốn mỗi lần chạy độc lập, nhưng đồng thời làm mất khả năng dựa vào khóa JobInstance để nhận diện hai yêu cầu trùng lịch.

Đặc biệt, `RunIdIncrementer` cũng nhằm tạo tham số định danh khác nhau giữa các lần chạy. Nó **không phải cơ chế khóa**. Nếu mục tiêu là ngăn overlap của toàn Job, cần một khóa độc quyền riêng.

Ngược lại, dùng một bộ tham số cố định mãi mãi cũng không phải giải pháp: sau khi JobInstance hoàn thành, lịch tiếp theo có thể bị từ chối vô thời hạn bằng `JobInstanceAlreadyCompleteException`. Thiết kế định danh theo **đơn vị công việc** cần xử lý, như ngày nghiệp vụ hoặc cửa sổ lịch, và tách độc lập logic chống chạy chồng lấn.

## 4. `@Scheduled` có bảo đảm không overlap không?

Spring Framework cho phép kích hoạt tác vụ bằng `@Scheduled`:

```java
@Scheduled(cron = "0 */5 * * * *", zone = "UTC")
public void triggerBatch() {
    // Khởi chạy Job
}
```

Cần phân biệt các cách đặt lịch:

| Kiểu lịch | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `fixedDelay` | Đếm khoảng nghỉ sau khi lần gọi phương thức trước kết thúc. | Có thể hạn chế chồng lấn của **chính lịch gọi đó** khi phương thức chạy đồng bộ. |
| `fixedRate` | Tác vụ được lập lịch với chu kỳ cố định. | Không có bảo đảm độc quyền giữa nhiều lịch, nhiều ứng dụng hoặc lời gọi khác. |
| `cron` | Kích hoạt theo biểu thức thời gian. | Không có cơ chế khóa Job phân tán mặc định. |

Ví dụ:

```java
@Scheduled(fixedDelayString = "PT5M")
public void runAfterPreviousInvocation() {
    jobLauncher.run(job, parameters);
}
```

Nếu bộ khởi chạy Job **đồng bộ**, lời gọi chỉ trở về khi Job đã kết thúc; `fixedDelay` bắt đầu đếm sau đó. Tuy nhiên:

1. Nếu `jobLauncher.run(...)` khởi chạy **bất đồng bộ**, phương thức lịch có thể trở về khi Job vẫn đang chạy. Khoảng `fixedDelay` chỉ đo từ khi phương thức trigger kết thúc, không đo từ khi Job kết thúc.
2. Mỗi pod/application instance có scheduler riêng. Hai pod có thể kích hoạt cùng lịch.
3. Những đường gọi ngoài scheduler (API quản trị, nút chạy thủ công, retry service, Quartz job khác) vẫn có thể khởi chạy cùng Job.
4. Một phương thức có nhiều khai báo `@Scheduled`, hoặc được gọi từ nhiều nơi, có thể tạo ra các lần kích hoạt độc lập.

Vì vậy, lựa chọn `fixedDelay` chỉ xử lý một trường hợp hẹp. Để bảo vệ tài nguyên ở cấp ứng dụng, cần thiết kế rõ cơ chế đồng bộ hóa và vòng đời khóa.

## 5. Cách 1: bảo vệ bằng `AtomicBoolean` trong một JVM

Nếu ứng dụng chắc chắn chỉ có **một process**, và mọi lần kích hoạt Job đều đi qua cùng một đối tượng, cờ nguyên tử là cơ chế đơn giản để bỏ qua trigger mới khi có lần chạy đang hoạt động.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public final class SingleJvmOverlapGuard {

    private final AtomicBoolean running = new AtomicBoolean(false);

    public boolean runIfIdle(Runnable jobAction) {
        if (!running.compareAndSet(false, true)) {
            return false; // Đang có lần chạy khác; bỏ qua trigger.
        }

        try {
            jobAction.run();
            return true;
        } finally {
            // Luôn giải phóng cờ kể cả khi jobAction ném exception.
            running.set(false);
        }
    }
}
```

Sử dụng trong một service:

```java
@Component
class LocalBatchSchedule {

    private final SingleJvmOverlapGuard guard =
            new SingleJvmOverlapGuard();

    @Scheduled(fixedRateString = "PT5M")
    void trigger() {
        boolean executed = guard.runIfIdle(() -> {
            // Bên trong cần gọi launcher đồng bộ hoặc chờ Job kết thúc thật.
            runJobSynchronously();
        });

        if (!executed) {
            // Ghi metric/log skipped: previous execution still active.
        }
    }

    private void runJobSynchronously() {
        // Thực thi Job, xử lý status và lỗi theo yêu cầu ứng dụng.
    }
}
```

**Ưu điểm:** ít phụ thuộc, hành vi rõ ràng và có thể unit test dễ dàng.

**Giới hạn:**

- Cờ chỉ tồn tại trong bộ nhớ của một JVM. Hai pod có hai cờ riêng và đều có thể chạy.
- Nếu code khởi chạy Job rồi trả về ngay do executor bất đồng bộ, `finally` sẽ nhả cờ quá sớm.
- Cờ không tồn tại sau restart process; nó cũng không cung cấp lịch sử bền vững để phục hồi.
- Nếu có nhiều bean/đường chạy tạo guard khác nhau, mỗi guard kiểm soát một phạm vi riêng.

Dùng cách này khi triển khai đơn instance và có quyền kiểm soát chắc chắn tất cả đường khởi chạy. Với production có nhiều replica, cần cơ chế liên node.

## 6. Cách 2: dùng khóa phân tán cho các instance Spring Boot

Một giải pháp phổ biến là **ShedLock**, thư viện bổ sung cơ chế phối hợp khi nhiều instance cùng thực thi các phương thức `@Scheduled`. ShedLock có thể lưu trạng thái khóa trong database chung thông qua JDBC, hoặc backend khác phù hợp.

Ý tưởng:

```text
Spring Boot A -- @Scheduled --> acquire("settlementJobSchedule") --┐
                                                                  ├--> Shared lock table
Spring Boot B -- @Scheduled --> acquire("settlementJobSchedule") --┘

A lấy được khóa => gọi Job, giữ khóa đến khi Job hoàn tất.
B không lấy được khóa => bỏ qua lượt kích hoạt này.
```

Đây là giải pháp **skip khi không lấy được khóa**, không phải hàng đợi tự động giữ mọi trigger để chạy lần lượt. Nếu nghiệp vụ bắt buộc xử lý mọi cửa sổ lịch, cần bổ sung thiết kế lưu trữ backlog/catch-up.

### 6.1. Dependency

Với Spring Boot, thông thường cần các module:

```groovy
dependencies {
    implementation 'net.javacrumbs.shedlock:shedlock-spring'
    implementation 'net.javacrumbs.shedlock:shedlock-provider-jdbc-template'
}
```

Cần quản lý **phiên bản ShedLock tương thích với Spring Framework/Spring Boot của dự án** qua dependency constraints hoặc khai báo phiên bản rõ ràng. Hai dependency ở trên là tên module, không hàm ý Spring Boot BOM mặc định quản lý phiên bản của chúng.

### 6.2. Bảng khóa dùng chung

Ví dụ cấu trúc bảng JDBC trên PostgreSQL:

```sql
CREATE TABLE shedlock (
    name       VARCHAR(64)  NOT NULL PRIMARY KEY,
    lock_until TIMESTAMP    NOT NULL,
    locked_at  TIMESTAMP    NOT NULL,
    locked_by  VARCHAR(255) NOT NULL
);
```

Tất cả instance phải truy cập **cùng bảng khóa** với transaction/permission phù hợp. Không tạo một bảng `shedlock` khác nhau cho từng pod nếu muốn phối hợp toàn cụm.

### 6.3. Đăng ký `LockProvider`

Ví dụ cấu hình Java:

```java
import net.javacrumbs.shedlock.core.LockProvider;
import net.javacrumbs.shedlock.provider.jdbctemplate.JdbcTemplateLockProvider;
import net.javacrumbs.shedlock.spring.annotation.EnableSchedulerLock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableSchedulerLock(defaultLockAtMostFor = "PT45M")
public class BatchSchedulingConfig {

    @Bean
    LockProvider lockProvider(JdbcTemplate jdbcTemplate) {
        return new JdbcTemplateLockProvider(
                JdbcTemplateLockProvider.Configuration.builder()
                        .withJdbcTemplate(jdbcTemplate)
                        .usingDbTime()
                        .build()
        );
    }
}
```

`usingDbTime()` giúp dùng thời gian của database cho việc tính khóa, hạn chế sai lệch đồng hồ giữa các node. Schema trên chỉ là ví dụ cho PostgreSQL; nếu dùng hệ quản trị khác, áp dụng DDL được nhà cung cấp khuyến nghị.

### 6.4. Khóa phương thức chạy theo lịch

Ví dụ Java cho **Spring Batch 5.x / Spring Boot 3.x**, với launcher **đồng bộ** đã được cấu hình trước:

```java
import java.time.Instant;

import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class SettlementSchedule {

    private static final Logger log =
            LoggerFactory.getLogger(SettlementSchedule.class);

    private final JobLauncher syncJobLauncher;
    private final Job settlementJob;

    public SettlementSchedule(
            @Qualifier("syncJobLauncher") JobLauncher syncJobLauncher,
            @Qualifier("settlementJob") Job settlementJob) {
        this.syncJobLauncher = syncJobLauncher;
        this.settlementJob = settlementJob;
    }

    @Scheduled(cron = "0 */5 * * * *", zone = "UTC")
    @SchedulerLock(
            name = "settlementJobSchedule",
            lockAtMostFor = "PT45M"
    )
    public void executeScheduledWindow() {
        // Cùng cửa sổ 5 phút -> cùng identifying parameter
        // trên mọi node có đồng hồ được đồng bộ.
        long fiveMinuteWindow =
                Instant.now().getEpochSecond() / 300L;

        JobParameters parameters = new JobParametersBuilder()
                .addLong("windowIndex", fiveMinuteWindow, true)
                .toJobParameters();

        try {
            JobExecution execution =
                    syncJobLauncher.run(settlementJob, parameters);

            if (execution.getStatus() != BatchStatus.COMPLETED) {
                log.warn("Settlement Job status={}, executionId={}",
                        execution.getStatus(), execution.getId());
            }
        } catch (JobExecutionException ex) {
            // Bao gồm các lỗi điều kiện khởi chạy Job;
            // cần phân loại thêm khi thiết kế retry/alert production.
            log.error("Không khởi chạy được settlementJob", ex);
        }
    }
}
```

Mục đích của hai lớp bảo vệ trong ví dụ là khác nhau:

- `@SchedulerLock` chặn **hai lịch chạy cùng Job cùng lúc trên nhiều node**, kể cả khi hai cửa sổ khác nhau.
- `windowIndex` giúp cùng một cửa sổ có **cùng JobInstance**, tránh xử lý hai lần nếu một trigger bị gọi lại sau khi đã hoàn thành.

Lưu ý cách tạo `windowIndex` này gắn với thời gian thực tế **lúc phương thức chạy**, thích hợp cho lịch đơn giản. Hệ thống có yêu cầu xử lý bù chính xác tất cả cửa sổ bị lỡ cần lưu lịch sử window và truyền *window cần xử lý* một cách tường minh, thay vì luôn lấy cửa sổ hiện tại.

### 6.5. Bảo đảm launcher đồng bộ

Trong Spring Batch 5.x, có thể tạo launcher với `SyncTaskExecutor`:

```java
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;

@Configuration
class SynchronousLauncherConfig {

    @Bean("syncJobLauncher")
    JobLauncher syncJobLauncher(JobRepository jobRepository)
            throws Exception {
        TaskExecutorJobLauncher launcher =
                new TaskExecutorJobLauncher();

        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(new SyncTaskExecutor());
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

Khi `run(...)` được thực thi đồng bộ, phương thức `@SchedulerLock` giữ khóa suốt thời gian Job chạy và chỉ nhả sau khi Job trả về (trừ trường hợp hết thời hạn khóa tối đa).

Nếu launcher thực thi **bất đồng bộ**, `run(...)` có thể trả về khi Job vẫn đang `STARTED`. Khi đó wrapper `@Scheduled` cũng kết thúc, khiến ShedLock nhả khóa trong khi Job vẫn còn xử lý. Để tránh khoảng trống này, phải giữ scope của khóa qua toàn bộ vòng đời thực thi thực tế: dùng launcher đồng bộ, hoặc thiết kế dịch vụ điều phối chờ trạng thái cuối và gia hạn lease phù hợp.

Ở Spring Batch 6.x, API khởi chạy được tổ chức lại; `JobOperator` và cấu hình task executor tương ứng là lựa chọn phù hợp. Nguyên tắc **giữ khóa đến trạng thái cuối** vẫn không đổi.

### 6.6. Hiểu đúng `lockAtMostFor` và `lockAtLeastFor`

- `lockAtMostFor` là **giới hạn tối đa** thời gian khóa có hiệu lực khi process chết hoặc không thể giải phóng khóa. Nếu Job chạy dài hơn thời hạn này, khóa có thể hết hạn **trong khi Job vẫn đang chạy**; một node khác có thể lấy khóa và gây overlap.
- `lockAtLeastFor` (tùy chọn) giữ khóa tối thiểu trong một khoảng, hữu ích cho những task rất ngắn hoặc các node có chênh lệch thời gian nhỏ.
- Hai tham số trên **không thay thế** chính sách timeout, giám sát các job quá lâu và xử lý recovery.

Ví dụ, nếu Job có thể mất tối đa 30 phút theo SLA đáng tin cậy, cấu hình `lockAtMostFor` cần có biên an toàn hợp lý vượt quá 30 phút. Với Job có thời gian chạy không giới hạn, không nên giả vờ một TTL cố định luôn an toàn. Cần cơ chế gia hạn lease, fencing hoặc điều phối bền vững phù hợp hơn.

**Khóa theo thời gian (lease) không đồng nghĩa với độc quyền vĩnh viễn.** Trong hệ thống có rủi ro tạm ngưng JVM, mất kết nối hoặc lease hết hạn, bảo vệ idempotency ở tầng dữ liệu vẫn cần thiết.

## 7. Cách 3: Scheduler có coordination hoặc hàng đợi bền vững

Đối với nhu cầu phức tạp hơn, có thể dùng:

| Giải pháp | Cách điều phối | Khi nào phù hợp |
| --- | --- | --- |
| Quartz với JDBC JobStore và clustering | Các scheduler cùng dùng JobStore, phối hợp trigger trong cụm. | Cần quản lý lịch phức tạp, misfire và độ bền của trigger. |
| Quartz `@DisallowConcurrentExecution` | Chặn chạy đồng thời các lần execute có cùng `JobDetail` / `JobKey` trong phạm vi JobStore phối hợp. | Muốn đảm bảo độc quyền theo một Quartz JobDetail cụ thể. |
| Scheduler trung tâm | Chỉ một bộ điều phối tạo yêu cầu chạy Job. | Cần một điểm kiểm soát rõ ràng, nhiều worker chạy theo nhiệm vụ. |
| Message queue / bảng công việc | Lưu từng cửa sổ cần xử lý và dùng consumer claim/lease công việc. | Không được bỏ qua các lịch kích hoạt ngay cả khi Job trước chạy lâu. |
| Khóa nghiệp vụ ở database | Dùng ràng buộc độc nhất, trạng thái claim, transaction hoặc advisory lock phù hợp DB. | Cần bảo vệ đúng một tài nguyên nghiệp vụ khi có nhiều đường khởi chạy. |

Với Quartz, `@DisallowConcurrentExecution` ngăn overlap **cho cùng định danh JobDetail**, không mặc nhiên khóa mọi JobDetail sử dụng chung một Java class. Việc cấu hình cluster/shared JDBC JobStore cũng quan trọng; mỗi node dùng JobStore riêng sẽ không có bảo đảm độc quyền toàn cụm.

Nếu yêu cầu là **mỗi trigger phải được xử lý đúng một lần**, một mutex kiểu ShedLock có thể chưa đáp ứng vì lượt không lấy được khóa sẽ bị bỏ qua. Khi đó, lưu công việc vào hàng đợi/bảng lịch bền vững và cho các worker claim theo cơ chế giao dịch là thiết kế phù hợp hơn.

## 8. Kiểm tra Job đang chạy bằng `JobExplorer`: dùng để quan sát, không dùng làm khóa

`JobExplorer` có thể truy vấn các execution hiện hành theo tên Job:

```java
Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("settlementJob");
```

Thông tin này rất hữu ích để:

- Hiển thị trạng thái trên dashboard.
- Ghi log/metric xem hiện có bao nhiêu JobExecution đang active.
- Chẩn đoán Job bị treo hoặc metadata chưa được cập nhật.
- Cảnh báo khi Job chạy quá thời gian cho phép.

Tuy nhiên, cách kiểm tra rồi khởi chạy đơn giản có **race condition**:

```text
Node A                           Node B
------                           ------
findRunning(...) -> empty       findRunning(...) -> empty
          |                               |
          +----- cả hai thấy "rảnh" ------+
          |                               |
launch(Job, params A)           launch(Job, params B)
          |                               |
          +---- Có thể cùng chạy ---------+
```

Hai thao tác **đọc trạng thái** và **khởi chạy** không phải một thao tác khóa nguyên tử cho toàn Job. Ngay cả khi query trả về rỗng, một node khác có thể bắt đầu Job trước khi node hiện tại gọi launcher.

Do đó, `JobExplorer` là công cụ quan sát hoặc lớp kiểm tra phụ. Nếu yêu cầu độc quyền toàn Job, cơ chế quyết định phải là lock/claim nguyên tử có phạm vi được bảo vệ rõ ràng.

## 9. Ngăn overlap không có nghĩa bảo đảm xử lý đúng một lần

Có ba khái niệm khác nhau:

| Khái niệm | Câu hỏi | Biện pháp |
| --- | --- | --- |
| **Mutual exclusion** | Có hơn một execution được chạy đồng thời trên cùng tài nguyên không? | Lock phân tán, guard hoặc scheduler coordination. |
| **Deduplication** | Cùng một đơn vị công việc có được nhận diện là trùng không? | Identifying JobParameters, khóa nghiệp vụ, unique constraint. |
| **Idempotency** | Nếu một tác vụ bị gọi lại, dữ liệu cuối có còn đúng không? | Upsert, khóa duy nhất, trạng thái xử lý, outbox/inbox, xử lý retry có kiểm soát. |

Ví dụ một thanh toán được gửi sang hệ thống ngoài:

1. Job gửi yêu cầu thành công.
2. Process chết trước khi metadata Spring Batch được cập nhật `COMPLETED`.
3. Sau restart, Job thử gửi lại cùng yêu cầu.
4. Khóa chống overlap có thể đã được giải phóng sau crash; yêu cầu vẫn bị lặp **theo thời gian**, dù không hề có hai Job chạy đồng thời.

Vì vậy, với nghiệp vụ quan trọng, hãy mang theo **idempotency key** (ví dụ ID thanh toán) và lưu trạng thái xử lý hoặc dùng hợp đồng idempotent của hệ thống đích. Khóa lịch giúp tránh chạy chồng lấn, nhưng không thể một mình cung cấp bảo đảm “exactly once” cho side effect ngoài transaction của JobRepository.

## 10. Chính sách khi một trigger đến trong lúc Job đang chạy

Khi một lịch kích hoạt mới gặp Job đang hoạt động, phải có hành vi nghiệp vụ được thống nhất:

### 10.1. Skip trigger mới

- Đơn giản, phù hợp nếu Job kế tiếp luôn quét mọi dữ liệu còn tồn đọng.
- Cần metric/log ghi nhận đã skip.
- Nếu mỗi lịch đại diện một cửa sổ dữ liệu riêng, việc skip có thể làm mất một cửa sổ nếu không có catch-up.

### 10.2. Xếp hàng, chạy sau

- Lưu mỗi cửa sổ vào bảng nhiệm vụ với unique key.
- Worker claim một nhiệm vụ và xử lý đến kết thúc.
- Khi Job đang bận, nhiệm vụ mới được giữ trong hàng đợi.
- Cần xử lý trường hợp worker chết, lease hết hạn, retry và dead-letter.

### 10.3. Coalesce: gộp nhiều trigger thành một lần xử lý

- Ví dụ Job đồng bộ catalog đọc mọi thay đổi chưa xử lý, không cần chạy riêng cho từng phút.
- Chỉ lưu cờ “có việc mới” hoặc thời điểm cần xử lý gần nhất.
- Sau Job hiện tại, nếu còn thay đổi thì lập một lượt chạy mới.

### 10.4. Cho phép chạy song song có giới hạn

- Nếu dữ liệu có partition/key độc lập, mỗi partition có thể có khóa riêng.
- Ví dụ `settlementJob:merchant=123` và `settlementJob:merchant=456` chạy đồng thời, nhưng hai job cho merchant 123 thì không.
- Khóa phải gắn với **tài nguyên xung đột thật**, tránh khóa toàn hệ thống gây nghẽn không cần thiết.

Thiết kế lock key thường quyết định nhiều hơn việc chọn thư viện: khóa quá rộng gây chậm; khóa quá hẹp không chặn được xung đột thực tế.

## 11. Xử lý Job kẹt trạng thái `STARTED` sau sự cố

Nếu process dừng đột ngột giữa khi chạy:

- `JobExecution` trong repository có thể vẫn mang trạng thái `STARTED` dù worker không còn tồn tại.
- Một yêu cầu cùng JobInstance có thể bị từ chối do repository cho rằng execution trước vẫn đang chạy.
- Khóa phân tán có TTL có thể hết hạn để node khác lấy khóa, nhưng **metadata của JobInstance và trạng thái business data phải được xử lý riêng**.

Không nên tự động xóa hàng `BATCH_JOB_EXECUTION` để “gỡ kẹt” rồi chạy lại. Làm vậy có thể mất thông tin restart, checkpoint và audit.

Quy trình phục hồi nên gồm:

1. Xác minh process/worker của execution cũ thật sự không còn hoạt động.
2. Kiểm tra JobExecution, StepExecution và ExecutionContext còn lưu.
3. Đánh giá step có restartable và side effect có idempotent hay không.
4. Theo quy trình vận hành, cập nhật trạng thái hoặc thực hiện restart bằng API/cơ chế phù hợp của hệ thống.
5. Ghi lại execution ID, nguyên nhân sự cố và kết quả xử lý để phục vụ audit.

Nếu hai node không nhìn thấy cùng JobRepository, kết luận về trạng thái “đang chạy” không còn tin cậy. Cấu hình data source cho metadata và lock provider phải được hiểu và kiểm tra trong toàn bộ cụm.

## 12. Kiểm thử chống overlap một cách xác định

Một test chỉ khởi chạy Job hai lần liên tiếp chưa chắc kiểm tra được overlap: lần đầu có thể kết thúc trước khi lần hai bắt đầu. Muốn chứng minh cơ chế độc quyền, cần **giữ lần đầu đang thực thi** rồi kích hoạt lần hai.

### 12.1. Unit test guard trong một JVM

Ví dụ JUnit Jupiter với `SingleJvmOverlapGuard` ở mục 5:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SingleJvmOverlapGuardTest {

    @Test
    void shouldSkipSecondRunWhileFirstIsActive() throws Exception {
        SingleJvmOverlapGuard guard = new SingleJvmOverlapGuard();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Boolean> first = pool.submit(() ->
                    guard.runIfIdle(() -> {
                        entered.countDown();
                        try {
                            if (!release.await(5, TimeUnit.SECONDS)) {
                                throw new IllegalStateException(
                                        "Timed out waiting for test");
                            }
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    })
            );

            assertThat(entered.await(3, TimeUnit.SECONDS))
                    .as("Lần chạy đầu phải vào vùng được bảo vệ")
                    .isTrue();

            boolean second = guard.runIfIdle(() -> {
                throw new AssertionError(
                        "Lần hai không được thực thi khi đang bận");
            });

            assertThat(second).isFalse();

            release.countDown();
            assertThat(first.get(5, TimeUnit.SECONDS)).isTrue();

            boolean third = guard.runIfIdle(() -> {});
            assertThat(third)
                    .as("Sau khi lần đầu kết thúc, khóa phải được nhả")
                    .isTrue();
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Test này xác nhận cả ba trạng thái:

1. Lần đầu đang giữ guard.
2. Lần hai bị bỏ qua, công việc không được chạy.
3. Lần đầu hoàn tất thì một lượt mới được phép chạy.

`CountDownLatch` giúp điều khiển ranh giới concurrency; timeout tránh test treo vô hạn. Đây là test cho cơ chế **một JVM**, chưa đủ để kết luận khóa phân tán hoạt động chính xác.

### 12.2. Integration test cho `JobRepository` và cùng `JobInstance`

Kịch bản:

1. Tạo Job test có Tasklet dừng tại `CountDownLatch` sau khi bắt đầu.
2. Khởi chạy Job trên một thread hoặc qua async launcher với identifying parameters cố định.
3. Chờ Tasklet báo đã vào vùng xử lý.
4. Từ một thread khác, gọi launcher **cùng Job và cùng identifying parameters**.
5. Xác nhận repository từ chối lần khởi chạy thứ hai, ví dụ `JobExecutionAlreadyRunningException`.
6. Mở latch, chờ Job đầu tiên hoàn thành và đối chiếu trạng thái cuối.
7. Dọn metadata và dữ liệu test sau khi tất cả worker đã dừng.

Điểm cần lưu ý: nếu lần hai dùng tham số khác, test không còn kiểm tra cơ chế từ chối **cùng JobInstance**. Đó là kịch bản khác và cần global guard/lock nếu muốn ngăn overlap.

### 12.3. Integration test cho khóa phân tán

Test dùng **hai application context hoặc hai tiến trình** chia sẻ cùng database lock:

```text
Context A                      Shared DB                 Context B
---------                      ---------                 ---------
@Scheduled / manual call  ----> lock: acquired
                                                          |
                                                   lock: rejected
    |
 Job đang chờ latch
    |
  mở latch
    |
 Job COMPLETED  -------------> lock released
                                                          |
                                                   trigger lại -> acquired
```

Nên kiểm tra:

- Trong khoảng A giữ khóa, B **không chạy nội dung Job**.
- Sau khi A kết thúc và khóa được giải phóng, một trigger hợp lệ mới có thể chạy.
- Cùng lock key được dùng ở cả hai node và cả hai node trỏ tới cùng backend.
- Nếu giả lập Job lâu hơn `lockAtMostFor`, phải xác định được nguy cơ lease hết hạn trong lúc Job vẫn chạy.
- Nếu khóa được giải phóng khi lời gọi async launcher vừa trả về, test phải phát hiện khả năng B chạy overlap.

Lưu ý `@SchedulerLock` có thể dựa trên Spring proxy; gọi trực tiếp một phương thức `this.executeScheduledWindow()` từ cùng bean có thể bỏ qua cơ chế intercept tùy cách cấu hình. Khi test, hãy gọi qua Spring-managed bean/proxy hoặc kích hoạt scheduler thực tế để kiểm tra đúng đường thực thi production.

### 12.4. Assert trạng thái dữ liệu

Đếm số lần Job được submit chưa đủ. Với nghiệp vụ ghi đơn hàng, nên xác nhận:

```java
assertThat(orderRepository.count()).isEqualTo(expectedCount);
assertThat(orderRepository.countDistinctBusinessKeys())
        .isEqualTo(expectedCount);
```

`countDistinctBusinessKeys()` là phương thức repository minh họa do dự án định nghĩa. Test nên dùng query thực tế để xác nhận không có bản ghi nghiệp vụ trùng và không có lần gửi side effect thứ hai.

## 13. Quan sát vận hành: log, metrics và alert

Để phát hiện overlap hoặc Job bị kẹt, nên ghi nhận:

| Trường/metric | Ý nghĩa |
| --- | --- |
| `jobName` và `jobExecutionId` | Xác định chính xác execution đang xử lý. |
| `jobInstanceId` hoặc identifying parameters | Phân biệt chạy trùng một instance với hai công việc khác nhau. |
| `scheduledWindow` | Đối chiếu lịch kích hoạt và cửa sổ dữ liệu nghiệp vụ. |
| `trigger_result` = started/skipped/failed | Hiểu trigger nào đã được chạy, bỏ qua hoặc lỗi. |
| `lock_key` và kết quả acquire | Xác định tài nguyên bị khóa và nguyên nhân skip. |
| `job_duration` | Chọn ngưỡng cảnh báo và giới hạn lease. |
| `BatchStatus`, `ExitStatus`, failure exceptions | Phân biệt Job thất bại với trigger bị từ chối. |
| `concurrent_execution_count` | Cảnh báo khi vượt mức concurrency cho phép. |

**Skipped trigger** khác **failed Job**. Khi không lấy được khóa, không nhất thiết có `JobExecution` mới trong `JobRepository` để xem trạng thái. Scheduler cần log/metric riêng cho sự kiện skip.

Cảnh báo vận hành hữu ích: một Job chạy lâu hơn bình thường, liên tục skip nhiều cửa sổ, metadata `STARTED` quá lâu hoặc khối lượng backlog tăng cao. Những tín hiệu này giúp phát hiện cấu hình lịch không phù hợp với thời gian xử lý thực tế.

## 14. Những sai lầm thường gặp

### Dùng `run.id` ngẫu nhiên và nghĩ Spring Batch sẽ chặn trùng

Mỗi tham số ngẫu nhiên thường tạo một JobInstance mới. `JobRepository` không ngăn hai instance khác nhau cùng chạy. Muốn khóa toàn Job, dùng distributed lock hoặc một cơ chế điều phối duy nhất.

### Chỉ đọc `JobExplorer.findRunningJobExecutions(...)` rồi chạy

Hai node có thể cùng thấy repository rảnh. Kiểm tra-để-rồi-chạy không phải mutex nguyên tử. Dùng lock/claim ở nơi bảo vệ concurrency.

### Chỉ dùng `synchronized` hoặc `AtomicBoolean` khi deploy nhiều pod

Các biện pháp này chỉ khóa trong phạm vi một JVM. Chúng không chia sẻ trạng thái với pod khác. Nếu cần cluster exclusivity, dùng một backend chung.

### Dùng ShedLock nhưng launcher async

`@SchedulerLock` thường giữ khóa trong thời gian **phương thức được bọc** thực thi. Nếu launcher trả về trước khi Job kết thúc, khóa có thể được nhả sớm. Cần giữ khóa đến trạng thái cuối hoặc đổi sang synchronous launcher trong phần scheduler.

### Đặt `lockAtMostFor` quá ngắn

Khi TTL hết mà Job vẫn đang xử lý, node khác có thể lấy khóa. Phải căn cứ thời gian chạy tối đa đáng tin cậy, có chính sách cho Job quá lâu và theo dõi timeout.

### Quên xử lý cửa sổ bị skip

Nếu mỗi cửa sổ 5 phút có dữ liệu riêng và một trigger bị skip vì khóa bận, không có gì bảo đảm cửa sổ đó được chạy bù tự động. Xây dựng backlog/catch-up nếu nghiệp vụ không cho phép mất khoảng thời gian.

### Khóa cả Job dù dữ liệu độc lập

Một lock toàn cục có thể làm throughput giảm mạnh. Với dữ liệu có partition thực sự độc lập, dùng lock theo partition/key nghiệp vụ để cho phép concurrency an toàn.

### Xóa metadata hoặc sửa trạng thái để “mở khóa” vội vàng

Metadata `JobRepository` dùng cho restart và audit. Thao tác can thiệp phải dựa vào quy trình recovery, xác nhận Job cũ đã dừng và hiểu tính idempotent của nghiệp vụ.

### Tưởng không overlap tức là không bao giờ gửi trùng

Crash sau khi side effect thành công vẫn có thể dẫn đến retry gửi lại. Thiết kế unique business key, idempotency và transaction/outbox phù hợp là lớp bảo vệ khác với scheduler lock.

## 15. Bài tập thực hành

Bạn có `dailyReportJob` tạo báo cáo doanh thu, bình thường mất 2 phút nhưng đôi khi kéo dài 12 phút. Hệ thống có 3 pod Spring Boot; mỗi pod đều có `@Scheduled(cron = "0 */5 * * * *")`.

**Yêu cầu:** tại mọi thời điểm chỉ có một `dailyReportJob` đang xuất báo cáo cho cùng tài nguyên đầu ra, nhưng không được làm mất dữ liệu của những khung giờ chưa được xử lý.

Triển khai theo các bước:

1. Xác định công việc theo `businessDate`/`windowStart` và đặt identifying JobParameters nhất quán trên các pod.
2. Tạo `JobRepository` dùng chung để Spring Batch nhận diện đúng JobInstance.
3. Tạo khóa phân tán theo tên Job hoặc tên tài nguyên báo cáo; cấu hình backend khóa dùng chung và chọn lease phù hợp thời gian chạy.
4. Bảo đảm phạm vi khóa bao trùm **toàn bộ** quá trình thực thi Job, kể cả khi Job kéo dài 12 phút.
5. Lưu những cửa sổ chưa xử lý trong bảng backlog hoặc thiết kế báo cáo có thể gộp xử lý, tùy hợp đồng nghiệp vụ.
6. Dùng latch tạo Job chạy lâu; kích hoạt lịch trên hai node và chứng minh chỉ một node vào phần xử lý được bảo vệ.
7. Khi Job A kết thúc, kích hoạt lượt tiếp theo; xác nhận backlog được xử lý mà không có file/bản ghi trùng.
8. Giả lập process chết giữa chừng; kiểm tra chính sách lease, recovery metadata, restart và tính idempotent của đầu ra.

Câu hỏi tự đánh giá: nếu bạn giữ nguyên tất cả cấu hình nhưng đổi launcher đồng bộ thành bất đồng bộ, điều gì xảy ra với thời điểm nhả khóa? Nếu mỗi pod dùng database ShedLock khác nhau, kết quả sẽ ra sao? Nếu một window bị skip, hệ thống sẽ xử lý bù bằng cơ chế nào?

## Tài liệu tham khảo

- [Spring Batch – Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): khởi chạy Job, JobParameters, JobInstance và JobExecution.
- [Spring Batch – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): vai trò repository trong lưu và kiểm soát metadata.
- [Spring Batch – Job Restart](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): quản lý metadata và điều kiện restart.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, fixed delay/rate và executor.
- [ShedLock – Documentation](https://github.com/lukas-krecan/ShedLock): cơ chế distributed lock, JDBC provider, `lockAtMostFor` và `lockAtLeastFor`.
- [Quartz – `DisallowConcurrentExecution`](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/DisallowConcurrentExecution.html): giới hạn concurrency theo Quartz JobDetail.

