# Misfire và missed schedule trong Spring Batch

## 1. Bài toán: một lịch đến hạn nhưng batch không chạy

Trong hệ thống xử lý theo lô, một job thường được kích hoạt vào thời điểm cố định: mỗi 5 phút, 02:00 hằng ngày, đầu tháng hoặc cuối kỳ kế toán. Tuy nhiên, ứng dụng có thể đang triển khai, scheduler bị dừng, worker thread cạn kiệt, cơ sở dữ liệu tạm mất kết nối hoặc lần chạy trước chưa kết thúc. Khi đến thời điểm dự kiến mà job không khởi chạy, ta gặp vấn đề **missed schedule**.

Giả sử hệ thống chốt doanh thu mỗi ngày vào 02:00 theo múi giờ Việt Nam:

```text
Ngày 10, 02:00  -> reportJob COMPLETED
Ngày 11, 02:00  -> ứng dụng tắt, không có execution
Ngày 12, 02:00  -> ứng dụng vẫn tắt
Ngày 13, 09:00  -> ứng dụng khởi động lại
```

Sau khi khởi động lại, hệ thống cần biết có phải xử lý ngày 11, 12, 13 hay chỉ tạo một báo cáo mới nhất. Nếu khởi chạy hàng loạt, cần bảo vệ database khỏi quá tải và ngăn lặp kết quả. Nếu bỏ qua, phải bảo đảm đúng yêu cầu nghiệp vụ.

**Misfire** và **missed schedule** có liên quan nhưng không đồng nghĩa:

- **Missed schedule** là tình huống nghiệp vụ: một mốc lịch đã đến hạn nhưng yêu cầu công việc tương ứng chưa được thực hiện đầy đủ. Khái niệm này áp dụng với Spring `@Scheduled`, Quartz, Kubernetes CronJob hoặc scheduler khác.
- **Misfire** là khái niệm của scheduler, đặc biệt là **Quartz**: trigger bị trễ quá điều kiện mà JobStore nhận diện, dẫn tới áp dụng một *misfire instruction* như bỏ qua hoặc kích hoạt ngay.
- **Failed job** là trạng thái của một lần chạy Spring Batch đã được tạo nhưng kết thúc `BatchStatus.FAILED`. Một missed schedule có thể **không tạo bất kỳ `JobExecution` nào**.

Spring Batch chịu trách nhiệm tổ chức job/step, transaction, metadata, checkpoint và restart. Spring Batch **không tự cung cấp một cron scheduler bền vững**. Lớp lập lịch cần được cấu hình qua Spring Scheduling, Quartz hoặc orchestrator bên ngoài.

Mục tiêu sau bài học: xác định đúng lịch bị lỡ, hiểu Quartz misfire policy, chọn skip/fire once/backfill, kết nối scheduler với Spring Batch bằng tham số định danh ổn định, và kiểm thử khôi phục lịch an toàn.

Ví dụ dùng Java 17+, Spring Framework 6.x, Spring Boot 3.x, Spring Batch 5.x và Quartz 2.x; các dự án dùng phiên bản khác cần đối chiếu API và metadata schema của phiên bản đó.

---

## 2. Ba loại trạng thái cần phân biệt

### 2.1. Slot lịch khác với `JobExecution`

Một **slot** là một kỳ công việc theo lịch nghiệp vụ, ví dụ thời điểm 02:00 ngày 12/11/2026. Scheduler có thể kích hoạt một lần hoặc nhiều lần, còn Spring Batch có thể tạo nhiều `JobExecution` nếu cần restart:

```text
Business schedule slot
  2026-11-12T02:00:00+07:00
            |
            v
Scheduler / Quartz trigger
            |
            v
JobLauncher + identifying JobParameters
            |
            v
Spring Batch JobInstance #71
            |
            +-- JobExecution #241 -> FAILED
            |
            +-- JobExecution #242 -> COMPLETED (restart)
```

| Khía cạnh | Câu hỏi | Nơi cần quan sát |
| --- | --- | --- |
| Business slot | Một kỳ đã đến hạn có được xử lý đủ chưa? | Ledger slot hoặc trạng thái orchestration riêng |
| Scheduler | Trigger nào phải fire, có bị trễ, pause hoặc misfire không? | Quartz JobStore, logs/metrics scheduler |
| Spring Batch | Job nào đã bắt đầu, thành công/thất bại, checkpoint thế nào? | `JobRepository`, `JobExplorer`, bảng `BATCH_*` |
| Kết quả nghiệp vụ | Báo cáo, file, bản ghi hoặc sự kiện đã đúng và không trùng chưa? | CSDL nghiệp vụ, hệ thống đích, reconciliation |

Nếu scheduler chết trước khi gửi lệnh chạy, **`JobRepository` không thể tự ghi một `FAILED` cho slot chưa được launch**. Vì thế, chỉ giám sát `BatchStatus.FAILED` là không đủ để phát hiện lịch bị bỏ lỡ.

### 2.2. Thuật ngữ vận hành

| Tình huống | Dấu hiệu | Cách xử lý chính |
| --- | --- | --- |
| Missed schedule | Đến hạn nhưng không có kết quả cho slot | Skip/coalesce/backfill theo chính sách |
| Delayed trigger | Có fire nhưng trễ so với thời điểm danh nghĩa | Kiểm tra scheduler lag |
| Job failure | `JobExecution` có `FAILED` | Sửa lỗi và restart đúng `JobInstance` |
| Stop | `JobExecution` chuyển `STOPPED` theo yêu cầu | Quyết định restart có kiểm soát |
| Overlap | Slot mới đến khi job trước còn chạy | Admission control, queue, skip hoặc concurrency |
| Duplicate launch | Hai launcher xử lý cùng một slot | Unique key, khóa/claim và job parameters |
| Quartz misfire | Trigger trễ đủ mức để Quartz áp dụng misfire instruction | Kiểm tra trigger policy và JobStore |

Một lần downtime có thể gây ra misfire của Quartz, từ đó tạo Batch execution muộn; execution vẫn có thể thất bại riêng vì dữ liệu kinh doanh không hợp lệ.

---

## 3. Nguyên nhân lịch bị lỡ

### 3.1. Lỗi và downtime

- Scheduler/process/Pod dừng khi đến giờ.
- Deploy/rolling restart kéo dài qua mốc cron.
- Scheduler hoặc JobStore tạm mất kết nối.
- Quartz thread pool hết worker; trigger đến hạn nhưng chưa được lấy ra thực thi.
- Scheduler đang pause/standby hoặc một Quartz instance trong cluster bị chết.
- Quartz job bị giới hạn concurrency, lần chạy trước kéo dài.
- Tắc nghẽn ở tầng launch Spring Batch, hết connection pool hoặc transaction không thể khởi tạo.
- Timezone thay đổi, đồng hồ node không đồng bộ hoặc lịch cron chạm thời điểm chuyển daylight saving time.

### 3.2. Công việc chạy lâu hơn chu kỳ

```text
10:00  slot A -> bắt đầu; kết thúc 10:12
10:05  slot B -> đến hạn trong khi A còn chạy
10:10  slot C -> đến hạn trong khi A còn chạy
10:15  slot D -> đến hạn
```

Nếu cho chạy song song, các job có thể cạnh tranh dữ liệu đầu vào/đầu ra. Nếu không cho song song, backlog sẽ tăng; tùy scheduler, các fire time đang chờ có thể trở thành misfire.

Giải pháp cần dựa trên nhu cầu nghiệp vụ: có được bỏ qua slot B và C không, có được gộp chúng không, hay phải xếp hàng xử lý tất cả? Tăng worker thread không tự giải quyết vấn đề dữ liệu trùng hay transaction contention.

### 3.3. Cron và timezone

Mỗi lịch phải chỉ rõ timezone. Với một cron 02:30 ở vùng có DST, ngày chuyển sang giờ mùa hè có thể không tồn tại 02:30; ngày quay lại giờ tiêu chuẩn có thể có hai mốc 02:30 theo hai offset khác nhau.

Nên định nghĩa rõ:

- **Nominal scheduled instant**: thời điểm lịch dự kiến theo timezone và phiên bản cron.
- **Business date**: kỳ dữ liệu mà job xử lý. Với báo cáo ngày N−1, business date khác ngày kích hoạt.
- **Actual fire time**: lúc scheduler thực sự gọi job.
- **Batch start/completion time**: thời điểm `JobExecution` bắt đầu và kết thúc.

Các giá trị này không nên dùng thay thế lẫn nhau.

---

## 4. Quartz nhận diện misfire như thế nào?

Quartz định nghĩa `JobDetail`, `Trigger` và `Scheduler`. Trigger mô tả mốc fire, còn JobStore có trách nhiệm lưu trạng thái lịch. Khi trigger lẽ ra phải fire nhưng bị trễ, Quartz có thể coi đó là misfire và áp dụng instruction được chọn.

### 4.1. `misfireThreshold`

Cấu hình Quartz điển hình:

```properties
org.quartz.jobStore.misfireThreshold=60000
```

Đơn vị là mili giây; giá trị mặc định phổ biến là **60.000 ms**, tức 60 giây. Một trigger trễ dưới ngưỡng không nhất thiết đi vào đường xử lý misfire; trigger trễ đủ lâu có thể được JobStore xác định là misfire và điều chỉnh next fire time theo policy.

```text
Expected fire: 02:00:00
Scheduler ready: 02:00:08
Threshold: 60s

=> Trễ 8 giây; không mặc định coi là misfire.

Expected fire: 02:00:00
Scheduler ready: 02:07:00
Threshold: 60s

=> Trễ 7 phút; có thể áp dụng misfire instruction.
```

Ngưỡng này **không phải timeout của Spring Batch**, không phải SLA nghiệp vụ, không thay đổi `retryLimit` và không tự restart các execution `FAILED`.

### 4.2. `RAMJobStore` và JDBC JobStore

| Quartz JobStore | Qua được restart JVM? | Ghi chú |
| --- | --- | --- |
| `RAMJobStore` | Không giữ trigger cũ khi JVM chết | Dùng cho demo/test hoặc lịch không cần persistence |
| JDBC JobStore | Giữ được trigger, nếu DB tồn tại và cấu hình phù hợp | Thích hợp cho downtime recovery và cluster |

Quartz JDBC dùng các bảng như `QRTZ_JOB_DETAILS`, `QRTZ_TRIGGERS`, `QRTZ_CRON_TRIGGERS`. Spring Batch JDBC lưu `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` trong các bảng `BATCH_*`.

Hai bộ bảng có thể nằm trong cùng database vật lý, nhưng:

- `QRTZ_*` biết trigger và scheduler state.
- `BATCH_*` biết những lần chạy Batch đã được tạo.
- Cả hai **không tự bảo đảm** mọi ngày nghiệp vụ đã có output hợp lệ.

### 4.3. Khi nào misfire xảy ra?

Những tình huống thường làm trigger trễ: scheduler downtime, quá ít thread, các trigger bị pause, giới hạn concurrency hoặc JobStore không truy cập được. Khi node sống lại, trigger còn tồn tại trong JDBC JobStore là điều kiện để Quartz khôi phục được lịch cũ.

Nếu dùng RAMJobStore, một lần restart JVM có thể khiến toàn bộ trigger trước đó biến mất; việc bean Java đăng ký một trigger mới lúc startup không chứng minh Quartz nhớ các slot đã lỡ.

---

## 5. Ba misfire policy chính cho Quartz `CronTrigger`

### 5.1. Bỏ qua: `DoNothing`

`CronScheduleBuilder.withMisfireHandlingInstructionDoNothing()` yêu cầu Quartz bỏ qua fire time đã lỡ và tính fire time cron phù hợp tiếp theo trong tương lai.

Ví dụ: ứng dụng tắt ba ngày rồi khởi động lại 09:00. Với lịch 02:00 mỗi ngày, những ngày cũ bị bỏ qua; trigger tiếp theo là 02:00 ngày sau.

Phù hợp: dọn cache, đồng bộ trạng thái có thể được cập nhật ở kỳ kế tiếp, tác vụ cũ không còn giá trị.

### 5.2. Fire một lần: `FireAndProceed`

`withMisfireHandlingInstructionFireAndProceed()` yêu cầu Quartz kích hoạt một lần sớm nhất có thể sau khi nhận diện misfire, sau đó tiếp tục cron tương lai.

Ví dụ lịch 02:00 bị lỡ ngày 11, 12 và 13, scheduler khởi động lại 09:00 ngày 13. Một lần fire sau resume **không tương đương ba báo cáo riêng cho ngày 11, 12 và 13**.

Phù hợp: refresh snapshot, đồng bộ trạng thái mới nhất, công việc cần một lần xử lý tổng sau gián đoạn.

Quartz `CronTrigger` khi dùng `SMART_POLICY` thông thường diễn giải thành hành vi fire once now cho misfire. Nếu nghiệp vụ quan trọng, hãy khai báo instruction tường minh.

### 5.3. Không chỉnh lịch khi misfire: `IgnoreMisfires`

`withMisfireHandlingInstructionIgnoreMisfires()` cho Quartz bỏ qua cơ chế điều chỉnh misfire, tiếp tục đánh giá fire time theo lịch trigger. Khi backlog lớn, nhiều fire có thể xảy ra sát nhau và làm tăng tải; số lượng/tốc độ thực tế còn phụ thuộc vào trigger, JobStore, concurrency và tài nguyên.

**Không dùng IgnoreMisfires như một bảo đảm exactly-once cho mọi slot lịch sử.** Quartz không thay thế sổ cái nghiệp vụ ghi nhận slot nào đã chạy thành công.

### 5.4. Bảng quyết định

Giả sử scheduler tắt từ tối ngày 10 đến 09:00 ngày 13; cron 02:00 hằng ngày:

| Policy | Kết quả điển hình sau phục hồi | Rủi ro |
| --- | --- | --- |
| `DoNothing` | Bỏ lịch ngày 11–13, chờ ngày 14 | Mất kỳ kinh doanh nếu cần mỗi ngày |
| `FireAndProceed` | Fire một lần gần 09:00 ngày 13, rồi chờ ngày 14 | Một lần không tạo đủ 3 báo cáo |
| `IgnoreMisfires` | Có thể fire liên tục các thời điểm đang chờ | Dồn tải và trùng side effect |
| Backfill theo từng slot | Tạo yêu cầu cho 11, 12, 13 theo ledger | Cần logic bổ sung ngoài CronTrigger |

Lựa chọn cuối phải xuất phát từ contract: **mỗi slot có giá trị độc lập hay chỉ cần kết quả cập nhật mới nhất?**

### 5.5. Cấu hình Java Quartz `CronTrigger`

```java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobDetail;
import org.quartz.TriggerBuilder;

CronTrigger invoiceTrigger = TriggerBuilder.newTrigger()
    .withIdentity("dailyInvoice", "finance")
    .forJob(jobDetail)
    .withSchedule(
        CronScheduleBuilder
            .cronSchedule("0 0 2 * * ?")
            .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
            .withMisfireHandlingInstructionFireAndProceed()
    )
    .build();
```

`0 0 2 * * ?` là biểu thức Quartz chạy lúc **02:00 hằng ngày**. Quartz cron có trường giây ở đầu và `?` biểu thị không chỉ định day-of-month/day-of-week tương ứng.

Đổi sang bỏ lịch bị lỡ:

```java
.withMisfireHandlingInstructionDoNothing()
```

Hoặc chỉ khi hiểu rõ backlog:

```java
.withMisfireHandlingInstructionIgnoreMisfires()
```

Các lời gọi rút gọn là **lựa chọn thay thế** instruction đang có trong ví dụ, không phải các instruction nên kết hợp cùng nhau.

### 5.6. `SimpleTrigger` dùng chính sách khác

`SimpleTrigger` mô tả lịch theo repeat interval/count; các instruction như `FIRE_NOW`, `RESCHEDULE_NEXT_WITH_EXISTING_COUNT` và `RESCHEDULE_NOW_WITH_REMAINING_REPEAT_COUNT` có semantics riêng, đặc biệt ảnh hưởng số lần repeat còn lại. Không lấy instruction của `CronTrigger` rồi áp dụng mặc định cho `SimpleTrigger`.

Khi một job cứ mỗi N phút phải tạo đúng N kết quả tương ứng khoảng thời gian, cần phân biệt “repeat count của Quartz” với “số business slots còn thiếu” trong thiết kế nghiệp vụ.

---

## 6. `@Scheduled` khác Quartz misfire ra sao?

Spring Framework cung cấp `@Scheduled` cho các công việc theo cron, `fixedRate` hoặc `fixedDelay`:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InvoiceSchedule {

    private final InvoiceBatchLauncher launcher;

    public InvoiceSchedule(InvoiceBatchLauncher launcher) {
        this.launcher = launcher;
    }

    @Scheduled(
        cron = "0 0 2 * * *",
        zone = "Asia/Ho_Chi_Minh"
    )
    public void runDaily() {
        launcher.launchDueInvoices();
    }
}
```

Ví dụ cần cấu hình `@EnableScheduling` và có bean `InvoiceBatchLauncher` do ứng dụng tự viết. Callback định kỳ chỉ là cơ chế kích hoạt, không tự sinh ra đầy đủ execution cho các kỳ từng bị bỏ lỡ.

**Điểm quan trọng:**

- `@Scheduled` mặc định không cung cấp persistent trigger history tương đương Quartz JDBC JobStore.
- Khi JVM dừng qua một số cron fire times, callback cũ thường không tự được chạy bù khi JVM khởi động.
- Trễ vì scheduler thread bận khác với lịch bị lỡ qua shutdown.
- Nếu yêu cầu đủ từng business date, method `@Scheduled` nên gọi một **reconciler** kiểm tra các slot chưa xử lý trong bảng trạng thái bền vững.

### 6.1. `fixedRate`, `fixedDelay` và cron

```java
@Scheduled(fixedRateString = "PT5M")
public void runEveryFiveMinutes() { /* ... */ }

@Scheduled(fixedDelayString = "PT5M")
public void runFiveMinutesAfterFinish() { /* ... */ }

@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runAtTwoAM() { /* ... */ }
```

| Cơ chế | Cách nghĩ về lịch | Lưu ý |
| --- | --- | --- |
| `fixedRate` | Khoảng cách đều giữa mốc kích hoạt theo nhịp scheduler | Thread bận vẫn gây trễ; semantics thực tế phụ thuộc scheduler |
| `fixedDelay` | Đợi khoảng cố định **sau khi lần trước kết thúc** | Không tạo mốc wall-clock cố định |
| `cron` | Mốc giờ/ngày trong timezone cụ thể | Cần xét DST, downtime, overlap và định nghĩa business date |

Không nên suy diễn rằng `@Scheduled(fixedRate)` tự xếp hàng vô hạn các lần bị bỏ qua trong lúc ứng dụng tắt.

### 6.2. Khi nào `@Scheduled` là đủ?

Cho tác vụ nhẹ và **best effort** như dọn bộ nhớ cache hoặc refresh snapshot, bỏ qua một vài fire có thể chấp nhận. Với báo cáo kế toán, doanh thu theo ngày, billing hoặc xuất dữ liệu phải đủ các kỳ lịch sử, nên có Quartz JDBC/other orchestrator và **persistent schedule-slot ledger**.

---

## 7. Cấu hình Quartz JDBC cùng Spring Batch

### 7.1. Dependency

Ví dụ Gradle Groovy DSL, project đã dùng Spring Boot BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-quartz'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

H2 dành cho integration test, PostgreSQL là một ví dụ production database. Nếu application dùng database khác, thay driver và cấu hình tương ứng.

### 7.2. Cấu hình JDBC JobStore bền vững

Ví dụ `application.yml` cho môi trường có migration tạo sẵn bảng Quartz và Spring Batch:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/batch_ops
    username: batch_user
    password: replace-with-secret-in-deployment

  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    properties:
      org.quartz.scheduler.instanceName: financeScheduler
      org.quartz.scheduler.instanceId: AUTO
      org.quartz.jobStore.isClustered: true
      org.quartz.jobStore.misfireThreshold: 60000
      org.quartz.threadPool.threadCount: 10

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
```

Giải thích:

- `spring.quartz.job-store-type=jdbc` yêu cầu Quartz dùng JDBC JobStore thay cho RAMJobStore theo cơ chế auto-configuration của Spring Boot.
- `spring.quartz.jdbc.initialize-schema=never` và `spring.batch.jdbc.initialize-schema=never` giả định Flyway/Liquibase hoặc migration khác đã tạo đúng các bảng `QRTZ_*` và `BATCH_*`.
- `org.quartz.jobStore.misfireThreshold` là ngưỡng xử lý misfire; `threadCount` chỉ là ví dụ cần cân theo tải.
- `isClustered=true` dùng khi nhiều instance Quartz thực sự chia sẻ **một JDBC JobStore** với cấu hình cluster đúng. Single-node có thể không cần clustered mode.
- `spring.batch.job.enabled=false` ngăn Boot tự chạy Batch job lúc startup khi scheduler sẽ điều khiển lịch.

Không bật `spring.quartz.jdbc.initialize-schema=always` thiếu kiểm soát trong production: một số script khởi tạo schema Quartz đi kèm có thao tác tạo lại bảng, có thể làm mất trigger đã persist. Với production, ưu tiên migrations được quản lý rõ ràng.

Nếu ứng dụng có nhiều datasource, xác định rõ datasource nào phục vụ Quartz (`@QuartzDataSource` theo cấu hình Boot) và datasource nào phục vụ Batch (`@BatchDataSource` hoặc cấu hình Batch tương ứng phiên bản).

### 7.3. Đăng ký Quartz `JobDetail` và `CronTrigger`

```java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DailyInvoiceQuartzConfig {

    @Bean
    JobDetail invoiceJobDetail() {
        return JobBuilder.newJob(InvoiceQuartzBridge.class)
            .withIdentity("invoiceLauncher", "finance")
            .storeDurably()
            .build();
    }

    @Bean
    Trigger invoiceCronTrigger(JobDetail invoiceJobDetail) {
        return TriggerBuilder.newTrigger()
            .withIdentity("invoice2AM", "finance")
            .forJob(invoiceJobDetail)
            .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0 2 * * ?")
                .inTimeZone(
                    TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                .withMisfireHandlingInstructionFireAndProceed())
            .build();
    }
}
```

Bean `InvoiceQuartzBridge` cần triển khai `org.quartz.Job`. Các job/trigger đã được lưu trong JDBC JobStore có thể tồn tại qua deploy; việc thay đổi cấu hình bean không đồng nghĩa tự cập nhật tất cả trigger đã persist. Cần chính sách đồng bộ schedule khi triển khai.

### 7.4. Bridge Quartz → Batch

Quartz job cần gọi Spring Batch `JobLauncher` với identifying parameters **theo slot ổn định**, thay vì UUID ngẫu nhiên mỗi lần fire.

Ví dụ cấu hình cho Quartz job đọc ApplicationContext từ SchedulerContext qua Spring Boot customizer:

```java
import org.springframework.boot.autoconfigure.quartz.SchedulerFactoryBeanCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class QuartzContextBridgeConfig {

    @Bean
    SchedulerFactoryBeanCustomizer contextKey() {
        return factory ->
            factory.setApplicationContextSchedulerContextKey(
                "springApplicationContext");
    }
}
```

Quartz job adapter:

```java
import java.time.Instant;
import org.quartz.DisallowConcurrentExecution;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.context.ApplicationContext;

@DisallowConcurrentExecution
public class InvoiceQuartzBridge implements org.quartz.Job {

    @Override
    public void execute(JobExecutionContext quartzContext)
            throws JobExecutionException {
        try {
            ApplicationContext app =
                (ApplicationContext) quartzContext.getScheduler()
                    .getContext().get("springApplicationContext");

            JobLauncher launcher = app.getBean(JobLauncher.class);
            Job batchJob = app.getBean("invoiceBatchJob", Job.class);

            Instant nominalFire =
                quartzContext.getScheduledFireTime().toInstant();

            JobParameters parameters = new JobParametersBuilder()
                .addString("schedule.key",
                    quartzContext.getTrigger().getKey().toString(),
                    true)
                .addLong("scheduled.at.epoch.ms",
                    nominalFire.toEpochMilli(), true)
                .addString("quartz.fire.id",
                    quartzContext.getFireInstanceId(), false)
                .toJobParameters();

            launcher.run(batchJob, parameters);
        } catch (Exception e) {
            // Không yêu cầu refireImmediately nếu chưa xác định
            // lệnh launch đầu tiên có thực sự tạo JobExecution hay chưa.
            throw new JobExecutionException(
                "Cannot launch invoiceBatchJob", e);
        }
    }
}
```

Đây là ví dụ cách nối infrastructure; cần có bean `invoiceBatchJob`, JobRepository và cấu hình JobStore. Vì `JobLauncher` có thể dùng async executor, phương thức `execute` của Quartz **không nhất thiết đợi Batch hoàn tất**. Nếu yêu cầu không overlap đến khi Batch job kết thúc, phải có cơ chế admission control bổ sung theo instance/slot.

**Lưu ý `getScheduledFireTime()`:** Quartz trả về thời điểm dự kiến của lần trigger đang được thực thi. Khi policy `FireAndProceed` đã điều chỉnh fire time vì misfire, thông tin này không bảo đảm truy hồi tất cả nominal slots bị mất trước đó. Các nghiệp vụ cần đủ từng slot phải dựng danh sách từ lịch gốc và ledger.

### 7.5. Giới hạn của `@DisallowConcurrentExecution`

Annotation `@DisallowConcurrentExecution` ngăn Quartz chạy đồng thời những executions của **cùng JobDetail/JobKey**. Nó không ngăn một REST API khác launch cùng Spring Batch job, không ngăn hai JobDetails có JobKey khác nhau cùng thao tác trên cùng dữ liệu, và không giữ khóa trong suốt Batch execution nếu launcher trả về bất đồng bộ.

Do đó, với job quan trọng, cần thêm bảo vệ ở tầng dữ liệu: claim slot, unique constraint, idempotent writer hoặc distributed lock có lifecycle đúng.

---

## 8. Các chiến lược xử lý missed schedule

Một policy phải được xác định từ mục tiêu kinh doanh trước khi cấu hình Quartz hoặc `@Scheduled`.

| Chiến lược | Ý nghĩa | Ví dụ | Đánh đổi |
| --- | --- | --- | --- |
| **SKIP** | Bỏ slot quá hạn, chờ lịch tiếp theo | Dọn cache | Không có kết quả lịch sử |
| **FIRE_ONCE** | Chạy một lần sau khi hệ thống sẵn sàng | Refresh snapshot mới nhất | Bỏ các kỳ riêng lẻ |
| **COALESCE** | Gộp nhiều slot thành một đơn vị xử lý tổng | Đồng bộ toàn bộ thay đổi kể từ mốc cuối | Cần logic theo watermark |
| **BACKFILL** | Khởi chạy từng slot thiếu | Báo cáo doanh thu ngày, đối soát | Phải kiểm soát backlog/tải |
| **MANUAL_REVIEW** | Đánh dấu slot thiếu và chờ người vận hành quyết định | Chuyển tiền, thao tác có tác động lớn | Cần quy trình phê duyệt |

### 8.1. SKIP

Nếu một job chỉ làm sạch cache, chạy trễ hôm nay có thể không mang ý nghĩa. Mỗi lần chạy tương lai xử lý được trạng thái hiện hành. Cấu hình Quartz `DoNothing` có thể đáp ứng.

### 8.2. FIRE_ONCE / COALESCE

Job “đồng bộ tất cả đơn hàng mới từ checkpoint cuối” có thể thực hiện một lượt ngay sau khi kết nối trở lại. Tuy nhiên, kết quả chỉ đúng nếu checkpoint đủ để bù thay đổi và source giữ dữ liệu đủ lâu.

Đừng mặc định mọi job dùng `LocalDate.now()` là coalesce hợp lệ. Nếu report phải tính riêng từng ngày, một lần tính ngày hiện tại không tạo ra các report quá khứ.

### 8.3. BACKFILL

Nếu một ngày cần một kết quả định danh riêng, hãy tạo **slot ledger** và một reconciler xác định các slot chưa hoàn thành. Có thể đặt:

- Tối đa 3 slot được khởi động trong mỗi lượt quét.
- Tối đa 1 Batch execution hoạt động cho cùng tenant và job.
- Slot quá cũ phải được review thủ công.
- Backlog được sắp xếp từ cũ đến mới, trừ khi nghiệp vụ có thứ tự khác.
- Không launch lại slot đã được Batch xác nhận `COMPLETED`.

Những con số là ví dụ, cần tính theo runtime thực tế, quota downstream và SLA.

### 8.4. MANUAL_REVIEW

Với nghiệp vụ có side effect khó đảo ngược, như gửi lệnh chi tiền, “chạy bù tự động ngay lập tức” không nhất thiết an toàn. Cần đối chiếu việc đã phát lệnh ở hệ thống đích, áp dụng idempotency key và có thể cần phê duyệt trước khi replay.

---

## 9. Persistent slot ledger cho yêu cầu phải xử lý đủ các kỳ

### 9.1. Vì sao phải có ledger?

Quartz lưu trigger; Spring Batch lưu execution; cả hai không tự cung cấp một bảng “tất cả kỳ doanh thu tháng này phải có báo cáo đã duyệt”. Một bảng riêng giúp ghi trạng thái của **từng slot**, kể cả slot mà scheduler chưa từng fire.

Ví dụ schema SQL tham khảo:

```sql
CREATE TABLE batch_schedule_slot (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_name VARCHAR(120) NOT NULL,
    schedule_key VARCHAR(120) NOT NULL,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    business_date DATE NOT NULL,
    status VARCHAR(24) NOT NULL,
    batch_execution_id BIGINT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claimed_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_error VARCHAR(1000),
    CONSTRAINT uq_batch_slot UNIQUE (
        job_name, schedule_key, scheduled_at
    )
);
```

DDL trên là mô hình logic; kiểu identity/timestamp cần điều chỉnh theo SQL dialect. Với cùng một job có nhiều tenant hoặc cron version, `schedule_key` nên xác định chính xác lịch/tenant.

Các trạng thái có thể là `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED` hoặc trạng thái domain khác.

### 9.2. Vòng đời slot

```text
Expected slot
     |
     v
PENDING --------- claim một lần ---------> RUNNING
                                             |
                                   +---------+----------+
                                   |                    |
                                   v                    v
                           Batch COMPLETED         Batch FAILED
                                   |                    |
                                   v                    v
                              COMPLETED               FAILED
                                                        |
                                                   retry/restart
```

Trạng thái slot không phải `BatchStatus`: một node có thể chết khi ledger đang `RUNNING` dù Batch đã `COMPLETED`. Reconciler cần kiểm tra kết quả thật trước khi thay đổi trạng thái.

### 9.3. Claim một slot an toàn giữa nhiều node

Quy trình:

1. Sinh các expected slots theo cron/business calendar và timezone trong một khoảng có giới hạn.
2. Insert-if-absent để tạo các slot thiếu, dựa trên unique constraint.
3. Chọn các slot đủ điều kiện `PENDING` theo thứ tự.
4. Claim bằng transaction/conditional update hoặc database locking phù hợp.
5. Chỉ node claim thành công mới launch Batch.
6. Lưu `JobExecution ID` và theo dõi terminal status.
7. Reconcile trạng thái nếu process chết trước/sau launch.

Ví dụ conditional update:

```sql
UPDATE batch_schedule_slot
SET status = 'RUNNING',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id = :slotId
  AND status = 'PENDING';
```

Chỉ caller nhận affected row count = 1 mới có quyền xử lý slot đó. Nếu hai node chỉ `SELECT status='PENDING'` rồi launch trước khi claim, cả hai có thể tạo yêu cầu trùng.

### 9.4. Stable identifying `JobParameters`

Định danh một `JobInstance` từ slot phải **ổn định** qua retry/restart:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("schedule.key", scheduleKey, true)
    .addLong("scheduled.at.epoch.ms",
        scheduledAt.toEpochMilli(), true)
    .addString("business.date",
        businessDate.toString(), true)
    .addString("correlation.id", traceId, false)
    .toJobParameters();
```

`traceId` chỉ phục vụ tracing nên là non-identifying. Nếu UUID/timestamp hiện tại luôn được thêm là identifying, mỗi lần gửi lệnh tạo một `JobInstance` mới, đánh mất khả năng dựa vào execution cũ để restart an toàn.

Khi slot đã có `FAILED` execution, nên kiểm tra và restart **cùng `JobInstance`**. Khi slot đã `COMPLETED`, chỉ cần reconcile ledger/đầu ra, không tạo instance mới để “chạy cho chắc”.

---

## 10. Tính các ngày cần backfill

### 10.1. Phân biệt ngày hiện tại và ngày dữ liệu

Giả sử slot ngày 16 chạy 02:00 để tổng hợp **business date ngày 15**:

```text
scheduled_at: 2026-11-16T02:00:00+07:00
businessDate: 2026-11-15
timezone:     Asia/Ho_Chi_Minh
now:          2026-11-16T09:00:00+07:00
```

Khi scheduler resume lúc 09:00, cần xử lý business date 15 nếu chưa có kết quả. Nếu resume lúc 01:00, slot 02:00 vẫn chưa đến hạn. Đừng lấy `LocalDate.now()` bên trong Batch reader cho mọi lần chạy bù, vì backfill có thể xử lý dữ liệu của nhiều ngày trước.

### 10.2. Planner đơn giản theo watermark

Với lịch mỗi ngày phải có một kết quả và không có lỗ hổng giữa các ngày hoàn thành, có thể tính khoảng ngày chưa làm:

```java
import java.time.LocalDate;
import java.util.List;

public final class DailyBackfillPlanner {

    private DailyBackfillPlanner() { }

    public static List<LocalDate> dueDates(
            LocalDate lastCompletedDate,
            LocalDate latestDueDate,
            long maxPerPoll) {

        if (maxPerPoll <= 0 ||
            !lastCompletedDate.isBefore(latestDueDate)) {
            return List.of();
        }

        return lastCompletedDate.plusDays(1)
            .datesUntil(latestDueDate.plusDays(1))
            .limit(maxPerPoll)
            .toList();
    }
}
```

JUnit 5:

```java
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DailyBackfillPlannerTest {

    @Test
    void returnsOldestThreeMissingDates() {
        List<LocalDate> actual =
            DailyBackfillPlanner.dueDates(
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 14),
                3);

        assertEquals(List.of(
            LocalDate.of(2026, 11, 11),
            LocalDate.of(2026, 11, 12),
            LocalDate.of(2026, 11, 13)
        ), actual);
    }

    @Test
    void doesNotReturnFutureOrCompletedDates() {
        assertEquals(List.of(),
            DailyBackfillPlanner.dueDates(
                LocalDate.of(2026, 11, 14),
                LocalDate.of(2026, 11, 14),
                3));
    }
}
```

Đây chỉ là bài toán liên tiếp theo watermark; **không đủ nếu ngày 11 đã xong, 12 lỗi và 13 lại xong**. Với dữ liệu có lỗ hổng, phải dựa trên trạng thái từng slot trong ledger thay vì chỉ dùng lastCompletedDate.

### 10.3. Reconciler hoạt động như thế nào?

Một reconciler có thể được đánh thức bởi Quartz hoặc `@Scheduled(fixedDelay)`:

```text
Scheduler tick / service startup
          |
          v
Enumerate expected slots <= now
          |
          v
Insert missing slots (unique key)
          |
          v
Query uncompleted slots
          |
          v
Claim with transaction + quota
          |
          v
For each claimed slot:
   - no Batch instance -> launch first execution
   - existing FAILED -> restart if valid
   - existing STARTED -> monitor/reconcile
   - existing COMPLETED -> mark slot complete
          |
          v
Observe Batch status + business result
```

Khi thời gian biểu thay đổi, cần version hóa schedule hoặc lưu cron/timezone có hiệu lực tại thời điểm mỗi slot. Không nên dùng cron mới để suy lại tất cả slot quá khứ.

---

## 11. Phân biệt launch mới, restart và reconcile

### 11.1. Slot chưa từng được launch

```text
Nominal slot: 2026-11-11T02:00+07:00
Ledger: PENDING
Batch JobRepository: không có JobInstance cho slot
```

Ứng dụng cần launch **lần đầu** với identifying parameters xác định bởi slot. Không có `JobExecution ID` nên không thể gọi `JobOperator.restart`.

### 11.2. Slot có execution `FAILED`

```text
Nominal slot: 2026-11-12T02:00+07:00
JobInstance #52
JobExecution #701 FAILED
```

Sau khi sửa lỗi và xác nhận an toàn, trong Spring Batch 5.x có thể:

```java
Long newExecutionId = jobOperator.restart(701L);
```

Framework tạo `JobExecution` mới cho **cùng `JobInstance`**, bỏ qua step đã hoàn tất theo cấu hình mặc định và khôi phục checkpoint của step phải chạy lại nếu stream/repository hỗ trợ. Reconciler cập nhật liên kết slot với execution mới.

### 11.3. Slot có Batch `COMPLETED` nhưng ledger còn `RUNNING`

Có thể process chết sau Batch commit nhưng trước cập nhật ledger:

```text
Batch JobExecution: COMPLETED
Business output:   already written
Slot ledger:       RUNNING
```

Không tạo `JobInstance` mới bằng UUID chỉ để chạy lại. Cần đối chiếu `JobExplorer` và dữ liệu nghiệp vụ, sau đó reconcile ledger sang `COMPLETED` nếu kết quả đúng.

### 11.4. Quartz retry không đồng nghĩa Batch restart

Quartz `JobExecutionException` có các cờ như `refireImmediately`. Nếu một Quartz job launch Batch nhưng bị timeout khi trả kết quả, Quartz không nhất thiết biết Batch đã tạo execution hay chưa. Refire vô điều kiện dễ gây duplicate launch.

Chính sách an toàn: một business slot có khóa ổn định; sau lỗi giao tiếp, tìm trạng thái Batch instance/execution và quyết định launch/restart/reconcile cho đúng.

---

## 12. Concurrency, clustering và idempotency

### 12.1. Khi một job kéo dài quá mốc lịch kế tiếp

| Chính sách | Hành vi |
| --- | --- |
| Allow overlap | Hai slot chạy đồng thời, chỉ khi dữ liệu/hạ tầng hỗ trợ |
| Queue/backfill sequential | Slot mới ở `PENDING` cho đến khi slot cũ hoàn tất |
| Skip | Bỏ slot mới nếu công việc cũ đã đủ theo hợp đồng |
| Coalesce | Gộp backlog thành lần chạy cập nhật trạng thái hiện hành |
| Manual | Đòi quyết định vận hành khi kỳ cũ vẫn đang chạy |

`@DisallowConcurrentExecution` chỉ giới hạn Quartz executions có cùng `JobKey`; nếu `JobLauncher` dùng async executor hoặc có caller khác, Batch jobs vẫn có thể overlap. Để ngăn overlap thực sự, cần admission control tại tầng slot/JobInstance và đầu ra.

### 12.2. Quartz cluster

Với JDBC JobStore dùng chung:

- Quartz nodes phải có scheduler name tương thích và instance ID riêng.
- Đồng hồ của các node cần đồng bộ.
- Database và connection pool phải chịu được tải trigger acquisition.
- JobStore schema/version phải phù hợp.
- Job/adapter phải idempotent trước các tình huống failover và lỗi mạng.

Quartz có `JobDetail.requestsRecovery()` để phục hồi execution của Quartz job sau khi node gặp sự cố; đây là cơ chế khác với **Spring Batch restart từ checkpoint**. Cần kiểm tra Batch metadata để không tạo side effect lặp.

### 12.3. Không có exactly-once tự động cho mọi hệ thống ngoài

Một step có thể:

```text
1. Gửi thông báo sang API bên ngoài -> thành công
2. Ghi trạng thái SENT xuống database -> chưa commit
3. Process chết trước metadata checkpoint
4. Restart -> gửi lại thông báo
```

Spring Batch không thể tự bảo đảm exactly-once cho API không tham gia cùng transaction. Với các nghiệp vụ này nên dùng idempotency key dựa trên slot + business record ID, unique constraint, upsert hoặc transactional outbox, tùy hạ tầng.

---

## 13. Kiểm thử misfire và missed schedule

Nên có nhiều mức test, vì chỉ kiểm tra một cron string không đủ để chứng minh hệ thống xử lý downtime đúng.

### 13.1. Unit test cấu hình Quartz policy

Ví dụ cần `org.quartz.Job` test fixture có tên `NoopQuartzJob`:

```java
import org.junit.jupiter.api.Test;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.TriggerBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class QuartzPolicyTest {

    @Test
    void skipsLateCronFireTimes() {
        JobDetail jobDetail =
            JobBuilder.newJob(NoopQuartzJob.class)
                .withIdentity("noop", "test")
                .build();

        CronTrigger trigger = TriggerBuilder.newTrigger()
            .forJob(jobDetail)
            .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0 2 * * ?")
                .withMisfireHandlingInstructionDoNothing())
            .build();

        assertEquals(
            CronTrigger.MISFIRE_INSTRUCTION_DO_NOTHING,
            trigger.getMisfireInstruction());
    }
}
```

Kết quả test này chứng minh instruction được cấu hình, **không chứng minh Quartz đã thực thi misfire trên JDBC JobStore**.

### 13.2. Integration test misfire trên Quartz

Một test thực cần:

1. Tạo Quartz JDBC JobStore và schema đúng phiên bản trong một database test.
2. Đặt `misfireThreshold` đủ nhỏ và trigger có fire time quá hạn một khoảng kiểm soát được.
3. Cho scheduler tạm standby/pause hoặc tạo trigger đang trễ theo fixture, rồi resume.
4. Ghi nhận số lần Quartz `Job.execute` thực sự được gọi.
5. So sánh `DoNothing` và `FireAndProceed`, phân biệt nominal và actual fire time.
6. Kiểm tra Batch adapter chỉ tạo những request theo policy nghiệp vụ.

Những test dùng `Thread.sleep` và so thời gian chính xác đến milliseconds thường flaky trên CI. Ưu tiên tách unit test policy khỏi integration test Quartz; dùng time window/timeout rõ ràng và không đưa ra kết luận dựa trên một lần poll trước khi scheduler xử lý xong.

### 13.3. Integration test Spring Batch restart

Thiết lập job hai step:

```text
prepareStep -> COMPLETED
importStep  -> FAILED sau khi vài chunk đã commit

Sau khi lỗi được xử lý:
  restart cùng JobInstance
  prepareStep thường bị bỏ qua
  importStep mở lại với checkpoint đã persist
  job -> COMPLETED
```

Test cần kiểm tra:

- Hai `JobExecution` khác ID nhưng cùng `JobInstance`.
- `JobExplorer` đọc được trạng thái và execution context đã lưu.
- Reader thật nhận checkpoint tương ứng ở `ItemStream.open`.
- Không mất hoặc nhân đôi bản ghi nghiệp vụ.
- Slot ledger chuyển `COMPLETED` sau khi Batch execution kết thúc.

### 13.4. Test không có execution và test ledger stale

Hai ca dễ bị bỏ quên:

**Không có Batch execution**: scheduler tắt qua lịch 11/11, ledger có slot `PENDING` nhưng JobRepository chưa có instance; reconciler phải launch lần đầu.

**Batch đã hoàn tất, ledger stale**: job `COMPLETED` nhưng node chết trước khi update ledger; reconciler phải cập nhật slot từ metadata/đầu ra hiện hữu và không launch lại.

Đây là các ca kiểm thử quan trọng để chứng minh không có “lỗ hổng giữa hai hệ thống metadata”.

### 13.5. Test backlog nhiều ngày

```text
Cron: mỗi ngày 02:00
Last completed slot: ngày 10
Resume: ngày 13 lúc 09:00
Policy: BACKFILL
Max slots per poll: 2
```

Kỳ vọng:

- Poll 1: claim ngày 11 và 12, để ngày 13 chờ.
- Poll 2 sau khi hoàn tất: claim ngày 13.
- Mỗi nominal slot chỉ ánh xạ tới một `JobInstance`.
- Cả ba slot cuối cùng ở `COMPLETED`.
- Nếu poll lại, không có execution nghiệp vụ mới cho slot đã hoàn tất.

Nếu resume vào 01:00 ngày 13, slot 02:00 ngày 13 chưa đến hạn và phải đợi đến đúng giờ.

---

## 14. Observability: đo lịch đến hạn và lịch thật sự hoàn thành

Một hệ thống có nhiều `JobExecution COMPLETED` chưa chắc có đủ các kỳ lịch. Nên đo cả scheduler lẫn dữ liệu nghiệp vụ.

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `scheduler_trigger_lag_seconds` | Khoảng cách actual fire time − scheduled fire time |
| `batch_due_slots_total` | Số slot đã đến hạn |
| `batch_uncompleted_slots_total` | Số slot đến hạn chưa hoàn tất |
| `batch_oldest_pending_age_seconds` | Tuổi slot còn thiếu lâu nhất |
| `batch_active_executions` | Số execution đang chạy |
| `batch_failed_executions_total` | Số execution `FAILED` |
| `batch_backfill_completed_total` | Tổng slot được chạy bù thành công |

Đây là **tên metric minh họa**, ứng dụng cần tự thu thập hoặc ánh xạ từ telemetry sẵn có.

Ví dụ bốn thời điểm:

```text
scheduled_at = 2026-11-16T02:00:00+07:00
triggered_at = 2026-11-16T02:07:00+07:00
started_at   = 2026-11-16T02:08:00+07:00
completed_at = 2026-11-16T02:20:00+07:00
```

- Scheduler delay = 7 phút.
- Batch start delay = 8 phút.
- Batch execution duration = 12 phút.
- End-to-end delay so với mốc lịch = 20 phút.

Chỉ theo dõi batch duration 12 phút sẽ không phát hiện startup trễ.

### 14.1. Runbook khi scheduler phục hồi

1. Xác định đúng schedule, timezone và khoảng downtime.
2. Đọc trạng thái Quartz trigger hoặc thông tin `@Scheduled`/scheduler đang dùng.
3. Liệt kê **tất cả business slots** đến hạn nhưng chưa có kết quả.
4. Phân loại slot: chưa launch, `RUNNING`, Batch `FAILED`, Batch `COMPLETED` nhưng ledger stale.
5. Sửa nguyên nhân hạ tầng và xác minh không có node cũ còn đang xử lý.
6. Áp dụng policy SKIP, FIRE_ONCE, COALESCE, BACKFILL hoặc MANUAL.
7. Giới hạn concurrency/quota, dùng job parameters ổn định, kiểm tra side effect.
8. Giám sát cho tới khi backlog đạt mức chấp nhận được và đối soát output.

Khi có Batch execution `STARTED` nhưng process đã chết, cần quy trình xác minh/recovery trạng thái metadata của phiên bản Spring Batch tương ứng; không tự chỉnh SQL status bằng suy đoán để ép restart.

---

## 15. Những lỗi cấu hình và thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Không có callback bù sau downtime | `@Scheduled` không có persistent misfire history | Xây ledger hoặc dùng persistent scheduler |
| Quartz restart mất trigger | RAMJobStore hoặc JDBC schema bị reset | JDBC JobStore + migration |
| Chỉ chạy một lần sau khi bỏ ba ngày | `FireAndProceed` | Nếu cần từng ngày, backfill bằng ledger |
| Không chạy bù kỳ nào | `DoNothing` | Đúng nếu SKIP; không hợp cho báo cáo đủ kỳ |
| Nhiều fire dồn dập | IgnoreMisfires + backlog | Giới hạn tải và xác định policy nghiệp vụ |
| Trùng output sau retry trigger | Mỗi fire tạo identifying UUID mới | Stable slot keys + idempotent writer |
| Slot `RUNNING` mãi dù Batch đã xong | Node chết trước cập nhật ledger | Reconcile từ `JobExplorer` |
| Batch `FAILED` nhưng launch job mới | Không restart instance cũ | Kiểm tra status và dùng cùng identifying params |
| Quartz chạy chồng trong cluster | Khác JobKey, job async, launcher ngoài | Claim slot và distributed admission |
| Lịch chạy lệch giờ | Timezone/DST thay đổi | Explicit `ZoneId`, kiểm thử mốc DST |
| Quartz tables biến mất khi deploy | Schema initialize chạy lại script xóa/tạo | Migration được kiểm soát |
| Không có alert dù bỏ lịch | Chỉ alert `BatchStatus.FAILED` | So expected-vs-completed slots |
| Restart không có checkpoint | Metadata DB không bền vững, `ItemStream` không lưu state | JDBC `JobRepository` và stream contract |

**Gợi ý chẩn đoán nhanh:** nếu một slot không có `JobExecution`, ưu tiên xem scheduler và admission logic. Nếu đã có `JobExecution` nhưng `FAILED`, ưu tiên xem lỗi Batch, checkpoint, transaction và restartability. Hai nhánh có cơ chế phục hồi khác nhau.

---

## 16. Bài thực hành

### Bài 1 — Quan sát `@Scheduled` khi application shutdown

Tạo một Spring Boot app có `@Scheduled(cron = "0 * * * * *", zone = "Asia/Ho_Chi_Minh")`. Dừng ứng dụng qua hai mốc phút rồi chạy lại.

Yêu cầu: ghi nhận callback có được chạy bù không; chỉ ra lý do cần lưu expected slots nếu muốn phục hồi từng phút.

### Bài 2 — Hai CronTrigger với misfire instruction khác nhau

Tạo một trigger dùng `DoNothing`, một trigger dùng `FireAndProceed`; dùng Quartz JDBC JobStore trong test, cho scheduler tạm không xử lý trigger qua ngưỡng misfire.

Yêu cầu: đo actual fire, scheduled fire, số lần kích hoạt và giải thích vì sao một lần fire không bảo đảm đủ báo cáo theo ngày.

### Bài 3 — Planner backfill có quota

Dùng `DailyBackfillPlanner` để chọn tối đa ba ngày còn thiếu. Bổ sung ledger cho trường hợp có lỗ hổng ngày 12 khi ngày 11 và 13 đã hoàn tất.

Yêu cầu: test thứ tự slot, giới hạn quota, không tạo slot tương lai và không claim trùng khi hai reconciler chạy đồng thời.

### Bài 4 — Quartz bridge sang Spring Batch

Tạo `invoiceBatchJob` nhận `scheduled.at.epoch.ms` và `business.date`. Kích hoạt bridge hai lần cho cùng nominal slot.

Yêu cầu: chứng minh chỉ một logical `JobInstance` được dùng; xử lý rõ tình huống execution đã `COMPLETED`, `STARTED` hoặc `FAILED`.

### Bài 5 — Sự cố sau Batch commit

Cho Batch hoàn tất nhưng cố ý không cập nhật slot ledger. Sau đó chạy reconciler.

Yêu cầu: đọc metadata và kết quả nghiệp vụ, đưa slot về `COMPLETED`; khẳng định không launch một execution mới chỉ để sửa ledger.

### Bài 6 — Chọn policy theo nghiệp vụ

Đề xuất SKIP/FIRE_ONCE/COALESCE/BACKFILL/MANUAL cho:

- Dọn cache mỗi 10 phút.
- Báo cáo doanh thu từng ngày.
- Đồng bộ snapshot sản phẩm.
- Gửi lệnh chuyển tiền cuối tháng.

Lý giải số slot cần giữ, SLA, timezone, concurrency, idempotency key và cách xử lý sau 72 giờ downtime.

---

## 17. Kết luận kiến trúc

```text
Quartz / @Scheduled / orchestrator
              |
              v
Policy + persistent schedule-slot ledger
              |
              v
Stable identifying JobParameters per slot
              |
              v
Spring Batch JobLauncher / JobOperator
              |
              v
JobRepository + JobExplorer
              |
       +------+---------+
       |                |
   COMPLETED          FAILED
       |                |
       v                v
 Reconcile slot     Diagnose and restart
       |
       v
 Verify business output
```

Điểm then chốt là **misfire thuộc scheduler, còn missed schedule thuộc yêu cầu xử lý nghiệp vụ**. Quartz có thể bỏ lịch, fire một lần hoặc xử lý trigger trễ theo instruction, nhưng không tự biết mỗi ngày có cần một báo cáo độc lập. Spring Batch có thể restart execution thất bại bằng metadata, nhưng không tự liệt kê những slot chưa bao giờ được launch.

Nếu một kỳ nghiệp vụ phải được xử lý chính xác, hãy định danh slot ổn định, ghi sổ cái bền vững, reconcile trạng thái giữa scheduler và JobRepository, giới hạn backfill, và kiểm tra output cuối cùng.

## 18. Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, `TaskScheduler`, cron, fixed rate và fixed delay.
- [Spring Boot — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html): auto-configuration, JobStore, schema initialization và trigger registration.
- [Quartz 2.3 — CronTrigger Tutorial](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html): cú pháp cron và misfire instructions.
- [Quartz 2.3 — SimpleTrigger Tutorial](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/simpletriggers.html): repeat interval/count và misfire policies.
- [Quartz — Configuration Reference](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/): JobStore, thread pool và misfire threshold.
- [Spring Batch — Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): job parameters, job instance/execution và restart.
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobOperator`, `JobExplorer`, operations.
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): bảng `BATCH_*`.
