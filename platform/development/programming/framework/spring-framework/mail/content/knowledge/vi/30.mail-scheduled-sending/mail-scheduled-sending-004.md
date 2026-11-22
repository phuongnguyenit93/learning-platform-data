# Quartz hoặc scheduler ngoài cho lịch bền vững

Ứng dụng Spring Framework Mail thường bắt đầu bằng một thao tác đơn giản: khi người dùng xác nhận đơn hàng, service gọi `JavaMailSender.send(...)`. Nhưng nhiều thông báo cần được gửi **vào một thời điểm trong tương lai**, chẳng hạn email nhắc lịch hẹn trước 24 giờ, thông báo gia hạn hợp đồng vào 08:00 sáng theo múi giờ khách hàng, hoặc báo cáo hàng tuần gửi đúng ngày làm việc. Nếu chỉ lưu một thời điểm trong biến Java hoặc dùng `Thread.sleep(...)`, việc khởi động lại ứng dụng, deploy, crash, scale nhiều instance hay thay đổi giờ mùa hè có thể khiến lịch chạy sai hoặc mất hẳn.

Chủ đề **“Quartz hoặc scheduler ngoài cho lịch bền vững”** thuộc chương **Lập lịch gửi** của **Spring Framework Mail** giải quyết câu hỏi: **Làm thế nào lưu được ý định gửi, khôi phục lịch sau khi tiến trình ngừng hoạt động và xử lý các lần kích hoạt một cách có kiểm soát?**

Ta sẽ đi từ nhu cầu và bảo đảm thực tế của hệ thống lập lịch đến cấu hình **Quartz với JDBC JobStore**, cách tạo `JobDetail`/`Trigger`, xử lý **misfire**, **cluster**, **time zone/DST**, và thiết kế **transactional outbox**. Bài cũng giới thiệu scheduler ngoài như cron ở hạ tầng, Kubernetes CronJob, dịch vụ cloud scheduler hay workflow engine, so sánh ưu/nhược điểm, trình bày mô hình idempotency và chiến lược kiểm thử.

**Điểm cốt lõi:** *Lịch được lưu bền vững* không đồng nghĩa *email được giao đúng một lần*. Quartz hoặc scheduler ngoài có thể kích hoạt công việc; chính ứng dụng vẫn phải quản lý notification, SMTP submission, retry và các kết quả không chắc chắn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt “chạy một method theo thời gian” với “quản lý lịch bền vững”.
2. Giải thích các thành phần `Scheduler`, `Job`, `JobDetail`, `Trigger` và `JobStore` của Quartz.
3. Cấu hình Quartz dùng **JDBC JobStore** trong Spring Boot thay vì mặc định chỉ lưu trong memory.
4. Đăng ký lịch một lần hoặc lặp theo cron, có ID và múi giờ rõ ràng.
5. Phân biệt **Quartz JobDetail durability** với **tính bền vững của cả hệ thống lịch**.
6. Xử lý trường hợp ứng dụng ngừng chạy lúc lịch đến hạn và cần quyết định chạy bù hay bỏ qua.
7. Vận hành nhiều application instances an toàn với cluster configuration và dữ liệu chung.
8. Dùng lịch để **tạo notification/outbox entry một cách idempotent** thay vì gửi SMTP trực tiếp trong transaction.
9. So sánh Quartz nội bộ với scheduler ngoài theo yêu cầu hạ tầng, quyền truy cập, độ bền và vận hành.
10. Test lịch, restart, duplicate trigger, timezone, cancel/reschedule, lỗi SMTP và khả năng khôi phục.

## 2. “Lịch bền vững” thực sự cần bảo đảm điều gì?

Một hệ thống lịch gửi email tốt nên trả lời những câu hỏi:

- **Định nghĩa lịch lưu ở đâu?** Memory, database của Quartz hay dịch vụ bên ngoài?
- **Ứng dụng restart thì lịch còn không?** Định nghĩa và next-fire time phải được khôi phục.
- **Hai instance cùng chạy có kích hoạt trùng không?** Có cơ chế phân phối/claim nào?
- **Đến hạn nhưng worker đang down thì sao?** Chạy bù, bỏ qua hay tạo cảnh báo?
- **Giờ gửi được diễn giải ở múi giờ nào?** Có xét DST và quy tắc lịch?
- **Người dùng hủy hoặc sửa lịch thì sao?** Lịch cũ có còn fire?
- **Email bị SMTP lỗi thì scheduler xử lý ra sao?** Retry bằng cùng job hay queue/outbox?
- **Crash sau SMTP accepted nhưng trước DB commit thì sao?** Có thể gửi trùng không?
- **Có biết ai đã sửa lịch và công việc nào đã được thực hiện không?**

Một yêu cầu mẫu:

> Gửi email nhắc cuộc hẹn lúc 09:00 theo múi giờ của người nhận, vào ngày trước cuộc hẹn; nếu ứng dụng down 30 phút, phải có quyết định rõ có chạy bù hay không; nếu lịch bị hủy, không gửi; nếu job được kích hoạt lại, không tạo hai notification giống nhau.

Chỉ dùng một `@Scheduled` không lưu định nghĩa lịch ở database sẽ **không tự đáp ứng** tất cả những yêu cầu này.

## 3. Phân biệt schedule, occurrence, notification và attempt

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Schedule** | Nhắc gia hạn mỗi ngày 5 hằng tháng | Quy tắc chạy trong tương lai |
| **Occurrence** | Lần đến hạn 2026-12-05 lúc 09:00 | Một lần kích hoạt logic của schedule |
| **Notification** | Email nhắc gia hạn cho khách hàng A của occurrence đó | Ý định gửi nghiệp vụ |
| **Submission attempt** | Lần thử gửi qua SMTP provider X | Một lần giao thông điệp cho provider |
| **Provider delivery event** | Delivered/bounced/deferred | Bằng chứng bất đồng bộ về kết quả sau submission |

Một schedule lặp tạo nhiều occurrences; một occurrence có thể tạo nhiều notifications nếu danh sách recipients lớn; một notification có thể cần nhiều attempts. Vì vậy:

```text
Schedule S-100
     |
     +-- Occurrence O-1 (plannedAt=2026-12-05T02:00Z)
     |      |
     |      +-- Notification N-A -> Attempt 1 -> SMTP
     |      +-- Notification N-B -> Attempt 1 -> SMTP
     |
     +-- Occurrence O-2 (plannedAt=2027-01-05T02:00Z)
            |
            +-- Notification N-A2 -> Attempt 1 -> SMTP
```

**Không sử dụng một biến boolean `isSent` cho toàn schedule lặp.** Lần tháng này có thể đã submit nhưng tháng sau vẫn phải được tạo. Ngược lại, nhiều lần gọi job cho cùng một planned occurrence không được tạo notification trùng.

## 4. Vì sao @Scheduled chưa đủ cho một số yêu cầu?

Spring hỗ trợ:

```java
@Scheduled(cron = "0 0 9 * * MON-FRI", zone = "Asia/Ho_Chi_Minh")
public void sendDailySummary() {
    // ...
}
```

Đây là công cụ hữu ích cho tác vụ định kỳ đơn giản; tuy nhiên khi lịch do người dùng tạo/sửa/hủy và cần phân phối trên nhiều instance, có các hạn chế nếu chỉ dựa vào annotation:

- Cron expression thường gắn với code/config và không tự trở thành mỗi bản ghi schedule bền vững.
- Mỗi instance có thể tự chạy method nếu cùng bật scheduling.
- Không mặc định ghi từng occurrence bền vững.
- Không tự tạo idempotency key cho notification.
- Khi ứng dụng down vào thời điểm cần chạy, không tự có chính sách chạy bù theo business.
- Không có cơ chế cluster claim/job persistence tương đương Quartz JDBC JobStore chỉ bằng `@Scheduled`.

Điều này **không có nghĩa `@Scheduled` luôn sai**. Với một worker poll database mỗi vài giây để tìm các notification đến hạn, `@Scheduled` vẫn có thể phù hợp **nếu chính database đảm bảo việc lưu lịch, claim và idempotency**. Khi ấy độ bền nằm ở database và logic worker, không nằm trong annotation.

## 5. Các lựa chọn kiến trúc

| Lựa chọn | Nơi giữ lịch | Phù hợp nhất khi | Điểm cần bổ sung |
| --- | --- | --- | --- |
| `@Scheduled` đơn giản | Code/config, runtime | Job định kỳ đơn giản, không yêu cầu lịch động riêng | DB claim, idempotency nếu chạy đa instance |
| **Quartz RAMJobStore** | Memory process | Demo, test, lịch có thể tạo lại | Mất state khi restart |
| **Quartz JDBC JobStore** | Database Quartz | Lịch động, cron/one-shot, cluster, misfire | Schema/DB ops, idempotent notification |
| **DB due-time + polling worker** | Database ứng dụng | Lịch một lần quy mô lớn, business-oriented | Claim/lease, index, backfill |
| **Scheduler ngoài** | Nền tảng cloud/cron/Kubernetes | Hạ tầng quản lý lịch, gọi HTTP/queue theo giờ | Secure ingress, dedupe, target HA |
| **Workflow engine** | State/event store của engine | Chuỗi thời gian dài, chờ sự kiện/timeout nhiều bước | Learning curve, engine ops, activity idempotency |
| **Provider send-at feature** | Provider mail | Email chỉ cần gửi sau một thời điểm, tính năng được hỗ trợ | Vendor limits, cancel semantics, feedback |

Không có giải pháp thắng trong mọi trường hợp. Độ chính xác đến mức giây, số lượng schedules, quyền sửa lịch, vùng triển khai, quota và SLA sẽ quyết định nên đặt trách nhiệm ở đâu.

## 6. Quartz gồm những khái niệm nào?

Quartz có các thành phần chủ đạo:

| Thành phần | Chức năng |
| --- | --- |
| `Scheduler` | Quản lý registration, pause/resume và thực thi |
| `Job` | Lớp thực hiện hành động khi trigger fire |
| `JobDetail` | Mô tả job, identity và `JobDataMap` |
| `Trigger` | Quy tắc **khi nào** job được kích hoạt |
| `SimpleTrigger` | Lịch một lần hoặc khoảng lặp đơn giản |
| `CronTrigger` | Lịch lặp theo biểu thức cron |
| `JobStore` | Lưu job/trigger state |
| `RAMJobStore` | Bộ nhớ trong process |
| `JDBC JobStore` | Lưu vào SQL database, hỗ trợ persistence và cluster khi cấu hình đúng |
| `JobDataMap` | Dữ liệu cấu hình nhỏ gắn với job/trigger |
| `JobListener` / `TriggerListener` | Quan sát lifecycle của job/trigger |

Một sơ đồ:

```text
Order reminder schedule
         |
         v
JobDetail: ReminderDispatchJob
         |
         +-- key = "reminder-123"
         +-- data = scheduleId
         |
         v
Trigger: fireAt / cron + time zone
         |
         v
Quartz Scheduler
         |
         v
Quartz JobStore (RAM or JDBC)
         |
         v
ReminderDispatchJob.execute(context)
         |
         v
Business outbox / SMTP worker
```

Một `JobDetail` không phải chính email. `Trigger` cũng không chứa đầy đủ workflow gửi. Chúng là các cơ chế để **kích hoạt đúng công việc** theo lịch.

## 7. “Durable Job” khác “lịch được lưu bền vững”

Trong Quartz, `JobBuilder.storeDurably()` có ý nghĩa hẹp: **giữ `JobDetail` ngay cả khi không còn trigger liên kết**.

```java
JobDetail job = JobBuilder.newJob(ReminderDispatchJob.class)
        .withIdentity("reminder", "mail")
        .storeDurably()
        .build();
```

Đừng hiểu `storeDurably()` là tự động ghi lịch xuống database. Khi `RAMJobStore` được dùng, job “durable” vẫn biến mất khi JVM restart. Muốn **persist job/trigger state qua restart**, cần một JobStore có persistence, chẳng hạn **Quartz JDBC JobStore**.

Ngược lại, khi đã dùng JDBC JobStore, trigger và job được ghi vào database theo thiết kế. `storeDurably()` chỉ cần khi bạn muốn JobDetail tồn tại độc lập với trigger, không phải một “nút bật” độ bền cho mọi schedule.

## 8. Quartz cluster giúp gì và không giúp gì?

Khi nhiều application instances chia sẻ **cùng Quartz JDBC JobStore** và cấu hình clustering:

```text
App instance A ---+
                  |
App instance B ---+--> Shared Quartz DB
                  |       |
App instance C ---+       +--> Trigger acquisition/locks
                          |
                          v
                    One job firing claimed by node
```

Quartz phối hợp việc lấy trigger qua database để tránh mọi node tự thực thi cùng một scheduled firing theo cách độc lập.

Tuy nhiên:

- Job có thể bị recover/re-execute trong các tình huống failover tùy cấu hình.
- SMTP là side effect ngoài transaction Quartz.
- Nếu job đã gọi SMTP nhưng node crash trước khi ghi kết quả, cluster không thể biết thư đã được submit hay chưa.
- Misfire có thể tạo một execution chạy bù.
- Hai logical schedules khác nhau vẫn có thể tạo cùng notification nếu business model không dedupe.

Do đó, **cluster scheduling không tự tạo exactly-once email delivery**. Cần idempotency ở tầng occurrence/outbox và tracking SMTP attempt.

## 9. Mô hình khuyến nghị: scheduler kích hoạt, outbox sở hữu gửi

Thiết kế dễ kiểm soát hơn việc gửi trực tiếp trong `Job.execute`:

```text
Quartz hoặc External Scheduler
              |
              v
      Due occurrence event
              |
              v
     Application transaction
       - validate schedule
       - insert occurrence (idempotent)
       - insert notification/outbox
              |
              v
            COMMIT
              |
              v
       Mail outbox worker
              |
              v
       Compose MimeMessage
              |
              v
       JavaMailSender.send()
              |
              v
    Store submission outcome
```

Lợi ích:

1. Quartz Job có thể thực thi nhanh, không giữ scheduler thread trong SMTP I/O dài.
2. Một trigger bị gọi lại có thể được dedupe bằng unique key trong database.
3. Outbox tồn tại qua restart, có owner retry rõ ràng.
4. Business transaction để tạo notification được tách khỏi SMTP.
5. Lịch có thể bị hủy/sửa mà không phải hủy những SMTP transaction đang chạy một cách mơ hồ.
6. Logs và metrics tách **đã kích hoạt lịch**, **đã tạo thông báo**, **đã submit SMTP** và **đã giao thư**.

### Điều không nên làm mặc định

```java
public void execute(JobExecutionContext context) {
    // Không nên gửi trực tiếp rồi giả định Quartz sẽ xử lý
    // mọi retry, idempotency và delivery cho mình.
    mailSender.send(...);
}
```

Gửi trực tiếp vẫn có thể phù hợp cho demo hoặc công việc không quan trọng, nhưng cần thiết kế riêng cơ chế lỗi, retry, timeout và kết quả mơ hồ. Với email nghiệp vụ quan trọng, việc có outbox giúp phân tách trách nhiệm đáng kể.

## 10. Cấu hình phụ thuộc Spring Boot

Trong dự án Spring Boot sử dụng Quartz, dependency thường gồm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

`spring-boot-starter-quartz` tích hợp Quartz với application context. `spring-boot-starter-jdbc` và driver phục vụ datasource cho JDBC JobStore; nếu ứng dụng đã có DataSource/JPA, dependencies thực tế có thể khác. Hãy dùng dependency management tương thích của dự án, không trộn version Quartz/Spring thủ công một cách tùy tiện.

Trong ứng dụng hiện đại Spring Boot 3.x, Spring Mail dùng `jakarta.mail`. Các đoạn Quartz `Job`/`Trigger` không phụ thuộc namespace mail, còn composer MIME cần nhất quán với phiên bản Spring Framework.

## 11. RAMJobStore: hữu ích khi nào?

Để phát triển nhanh hoặc test không cần persistence:

```yaml
spring:
  quartz:
    job-store-type: memory
```

Scheduler có thể giữ job và trigger trong memory. Khi process dừng, state này không còn, trừ khi bạn có cơ chế đăng ký lại từ nguồn bền vững của ứng dụng.

RAMJobStore phù hợp để:

- Demo Quartz API.
- Unit/integration test kiểm tra trigger logic.
- Chạy tác vụ tạm thời có thể mất hoặc tái tạo được.

Nó **không phải** đáp án mặc định cho lịch người dùng đã đặt và kỳ vọng còn sau deploy/restart.

## 12. JDBC JobStore: nền tảng của lịch được persist

Với PostgreSQL ví dụ:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/mail_app
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    overwrite-existing-jobs: false
    properties:
      org.quartz.scheduler.instanceName: MailScheduleCluster
      org.quartz.scheduler.instanceId: AUTO
      org.quartz.jobStore.isClustered: true
      org.quartz.jobStore.clusterCheckinInterval: 20000
      org.quartz.jobStore.misfireThreshold: 60000
      org.quartz.jobStore.tablePrefix: QRTZ_
      org.quartz.threadPool.threadCount: 5
```

Cấu hình trên là **ví dụ cho môi trường đã có Quartz tables và muốn chạy cluster**. Cần khai báo datasource phù hợp, có các bảng Quartz đúng version và bảo đảm **tất cả instances dùng chung database/tablePrefix/instanceName với instance ID duy nhất**. Ứng dụng dùng nhiều datasource có thể cần chỉ rõ datasource của Quartz, ví dụ theo cơ chế Spring Boot/`@QuartzDataSource` tương ứng.

### Tại sao `initialize-schema: never` trong production?

Quartz cần bộ bảng thường có tiền tố `QRTZ_`. Với Spring Boot, cấu hình tự khởi tạo schema có thể chạy script tạo bảng; một số script tiêu chuẩn có thể **xóa và tạo lại bảng**, nguy hiểm với job đã persist. Không dùng cơ chế drop/recreate bảng tự động ở mỗi lần production startup.

Thay vào đó:

1. Chọn script schema Quartz **đúng database và version**.
2. Đưa schema vào migration đã review (Flyway/Liquibase hoặc quy trình DBA).
3. Áp dụng migration có kiểm soát trước khi start scheduler.
4. Để Spring Boot dùng những bảng đã tồn tại.
5. Backup và kiểm soát quyền database theo môi trường.

Không cho rằng chỉ đặt `job-store-type: jdbc` là đủ nếu Quartz schema chưa được tạo hoặc chưa tương thích.

## 13. Những lưu ý khi dùng Quartz JDBC trong cluster

| Cấu hình hoặc điều kiện | Vì sao quan trọng? |
| --- | --- |
| Shared database | Các node cần nhìn cùng job/trigger state |
| Cùng `instanceName` | Các node tham gia đúng logical scheduler |
| `instanceId=AUTO` hoặc ID duy nhất | Tránh hai node dùng cùng scheduler instance ID |
| `jobStore.isClustered=true` | Bật cơ chế phối hợp cluster của JDBC JobStore |
| Quartz tables đúng schema | Cần cho persistence, locks và triggers |
| Đồng bộ đồng hồ máy chủ | Clock skew lớn làm sai fire time và failure detection |
| DB connection pool đủ | Scheduler cần kết nối để đọc/ghi trigger |
| Quyền database phù hợp | JobStore cần cập nhật trạng thái và lock |
| Backup/migration plan | Không xóa lịch đã đăng ký khi nâng cấp |
| Job idempotent | Recovery và xử lý lỗi không tạo side effect trùng |

**Không dùng hai cluster Quartz khác nhau cùng thao tác lên một tập bảng với ý định độc lập**, hoặc cho một số instance chạy non-clustered trên cùng bảng của clustered instances. Cấu hình không nhất quán có thể gây lỗi trigger acquisition và nguy cơ hành vi không mong đợi.

Khi dùng một database cho nhiều ứng dụng khác nhau, phải thiết kế phạm vi `instanceName`, table prefix hoặc datasource tách biệt phù hợp; không dựa vào `JobKey` trùng tên để phân vùng dữ liệu mà thiếu thiết kế.

## 14. Viết Quartz Job chỉ tạo occurrence/outbox

Một `Job` nên nhận một schedule ID và **ủy quyền cho service** xử lý idempotency. Không đưa raw SMTP credentials, attachment bytes hoặc toàn bộ object `MimeMessage` vào `JobDataMap`.

```java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

@DisallowConcurrentExecution
public class MailOccurrenceJob implements Job {

    private ScheduleDispatchService dispatchService;

    // Dành cho cơ chế dependency injection của Quartz JobFactory.
    public void setDispatchService(
            ScheduleDispatchService dispatchService
    ) {
        this.dispatchService = dispatchService;
    }

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {

        try {
            String id = context.getMergedJobDataMap()
                    .getString("scheduleId");
            UUID scheduleId = UUID.fromString(id);

            Date plannedFireTime = context.getScheduledFireTime();
            if (plannedFireTime == null) {
                throw new IllegalStateException(
                        "No scheduled fire time"
                );
            }

            Instant plannedAt = plannedFireTime.toInstant();

            dispatchService.materializeOccurrence(
                    scheduleId,
                    plannedAt
            );
        } catch (RuntimeException failure) {
            throw new JobExecutionException(
                    "Failed to materialize mail occurrence",
                    failure
            );
        }
    }
}
```

`ScheduleDispatchService` là service **do ứng dụng tự định nghĩa**. Job đọc `scheduleId` và `scheduledFireTime` từ Quartz rồi gọi service; service mới là nơi kiểm tra schedule còn hiệu lực, tạo occurrence và outbox trong database.

### Dependency injection trong Quartz Job

Quartz tạo `Job` instance qua `JobFactory`. Muốn tiêm `ScheduleDispatchService`, cần cấu hình JobFactory có khả năng tích hợp với Spring container hoặc dùng cơ chế được Spring Boot phiên bản dự án hỗ trợ.

Ví dụ setter ở trên thể hiện một khả năng injection; **nó không tự chạy nếu bạn chưa cấu hình job factory gọi setter**. Một cách phổ biến hơn là constructor/field injection khi đã có `JobFactory` hỗ trợ autowiring và phiên bản Boot tương ứng. Nên xác nhận cơ chế inject bằng một integration test với application context.

Trong ví dụ độc lập với DI, job có thể lấy một service bridge được cấu hình sẵn từ `SchedulerContext`; tuy nhiên, đừng lạm dụng lookup toàn cục hoặc lưu Spring beans trong `JobDataMap` persistent.

## 15. JobDataMap nên giữ định danh nhỏ và có thể serialize

Ví dụ tốt:

```java
.usingJobData("scheduleId", scheduleId.toString())
```

Ví dụ không nên:

```java
// Không nên gắn cả object nghiệp vụ và payload lớn vào store.
JobDataMap data = new JobDataMap();
data.put("customerEntity", customerEntity);
data.put("mimeMessage", mimeMessage);
data.put("pdfBytes", hugePdfByteArray);
```

Lý do:

- Persistence của JobStore có thể cần serialize giá trị JobDataMap.
- Class Java có thể đổi giữa các lần deploy.
- Entity JPA có lazy references và không có lifecycle bền vững như job record.
- Attachment bytes làm tăng kích thước database/heap và chi phí backup.
- Dữ liệu recipient/token/PII có thể đi vào Quartz tables.
- Nếu job data bị xem như bản snapshot bất biến nhưng thực tế stale, email gửi sai.

Ưu tiên một `scheduleId`, `tenantId` dạng ID opaque hoặc một số string/scalar nhỏ. Tra dữ liệu nghiệp vụ từ một store được kiểm soát tại thời điểm materialization.

### Có nên lưu toàn bộ email nội dung trong lịch?

Tùy yêu cầu. Nếu email là hóa đơn đã phát hành, nội dung có thể cần được snapshot/version để không thay đổi sau đó. Nhưng snapshot đó nên nằm ở hệ thống quản lý notification/content hoặc immutable storage, **không nhất thiết nằm trong Quartz JobDataMap**.

## 16. Đăng ký một lịch gửi một lần bằng SimpleTrigger

Giả sử ứng dụng có `scheduleId` và `plannedAt` là một `Instant` hợp lệ trong tương lai:

```java
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.SimpleScheduleBuilder;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

import java.time.Instant;
import java.util.Date;
import java.util.UUID;

public final class OneTimeMailScheduler {

    private final Scheduler quartz;

    public OneTimeMailScheduler(Scheduler quartz) {
        this.quartz = quartz;
    }

    public void schedule(
            UUID scheduleId,
            Instant plannedAt
    ) throws Exception {

        JobKey jobKey = JobKey.jobKey(
                "mail-" + scheduleId,
                "mail-once"
        );

        JobDetail detail = JobBuilder
                .newJob(MailOccurrenceJob.class)
                .withIdentity(jobKey)
                .usingJobData(
                        "scheduleId",
                        scheduleId.toString()
                )
                .build();

        Trigger trigger = TriggerBuilder.newTrigger()
                .withIdentity(
                        "fire-" + scheduleId,
                        "mail-once"
                )
                .forJob(detail)
                .startAt(Date.from(plannedAt))
                .withSchedule(
                        SimpleScheduleBuilder.simpleSchedule()
                                .withMisfireHandlingInstructionFireNow()
                )
                .build();

        quartz.scheduleJob(detail, trigger);
    }
}
```

`SimpleScheduleBuilder` với misfire `FireNow` là một **chính sách được chọn có chủ đích cho ví dụ**. Không phải mọi email nhắc lịch quá hạn đều nên chạy ngay. Với những thông báo có thời hạn giá trị, business service có thể quyết định bỏ occurrence đã stale ngay cả khi Quartz fire.

### Tránh đăng ký lại cùng JobKey

`quartz.scheduleJob(detail, trigger)` có thể báo lỗi nếu một job/trigger identity đã tồn tại. Không dùng logic “nếu có thì xóa rồi tạo lại” tự động, vì có thể làm mất trigger đang chờ hoặc thay đổi lịch ngoài ý muốn.

Một API tạo lịch nên:

1. Ghi schedule nghiệp vụ và version trước.
2. Dùng `JobKey`/`TriggerKey` ổn định.
3. Phân biệt **create**, **update**, **cancel**.
4. Có optimistic locking hoặc một cơ chế concurrency control phù hợp.
5. Khi tồn tại, xác định đó là idempotent retry của cùng yêu cầu hay conflict thật.
6. Không cho các request song song ghi đè lịch mà không có phiên bản.

Quartz có API `checkExists`, `rescheduleJob`, `unscheduleJob` và `deleteJob`. Nhưng **check-then-create không tự atomic** nếu nhiều caller cùng chạy; cần xử lý `ObjectAlreadyExistsException` hoặc thiết kế một owner cho schedule registration.

## 17. Lịch lặp bằng CronTrigger

Ví dụ: chạy lúc **09:00 sáng từ thứ Hai đến thứ Sáu**, theo múi giờ Việt Nam.

```java
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

import java.time.ZoneId;
import java.util.TimeZone;

ZoneId zoneId = ZoneId.of("Asia/Ho_Chi_Minh");

JobDetail job = JobBuilder.newJob(MailOccurrenceJob.class)
        .withIdentity("daily-report-" + scheduleId, "mail-cron")
        .usingJobData("scheduleId", scheduleId.toString())
        .build();

Trigger trigger = TriggerBuilder.newTrigger()
        .withIdentity("daily-fire-" + scheduleId, "mail-cron")
        .forJob(job)
        .startNow()
        .withSchedule(
                CronScheduleBuilder
                        .cronSchedule("0 0 9 ? * MON-FRI")
                        .inTimeZone(TimeZone.getTimeZone(zoneId))
                        .withMisfireHandlingInstructionDoNothing()
        )
        .build();

quartz.scheduleJob(job, trigger);
```

Quartz cron thường có sáu trường bắt buộc:

```text
seconds minutes hours day-of-month month day-of-week [year]

   0      0     9        ?          *      MON-FRI
```

`?` nghĩa là không chỉ định cụ thể ở trường ngày tương ứng khi biểu thức đang chọn theo trường ngày còn lại. Đừng sao chép một biểu thức cron năm trường của hệ thống Unix rồi tin rằng Quartz sẽ hiểu y hệt. Spring `@Scheduled` cron và Quartz cron cũng có khác biệt cú pháp/tính năng giữa các phiên bản.

### Vì sao dùng `ZoneId.of(...)` trước?

`ZoneId.of("Asia/Ho_Chi_Minh")` kiểm tra ID múi giờ theo rules của Java. Nếu nhận timezone từ user, không nên đưa thẳng chuỗi bất kỳ vào `TimeZone.getTimeZone(String)` vì API đó có thể fallback ngoài ý muốn đối với ID không hợp lệ.

### Khi phải chạy bù lịch ngày làm việc

Ví dụ đang chọn `withMisfireHandlingInstructionDoNothing()`, nghĩa là bạn chấp nhận **bỏ các lần fire đã bị lỡ** theo cách xử lý misfire của CronTrigger. Nếu báo cáo mỗi ngày bắt buộc có đủ, nên có một **backfill/reconciliation theo business date** và occurrence key, thay vì giả định Quartz sẽ phát lại từng ngày đã bị lỡ.

## 18. Sự khác nhau giữa SimpleTrigger và CronTrigger

| Nhu cầu | Trigger thích hợp | Lưu ý |
| --- | --- | --- |
| Gửi một email lúc 14:00 ngày X | `SimpleTrigger` với `startAt` | Phù hợp lịch one-shot |
| Gửi mỗi 15 phút | Simple repeat hoặc cron | Cần quyết định fixed interval vs wall-clock |
| Gửi lúc 09:00 mỗi thứ Hai | `CronTrigger` | Có timezone |
| Gửi ngày 1 mỗi tháng | `CronTrigger` | Kiểm soát timezone/misfire |
| Gửi theo lịch nghỉ lễ | Cron + calendar hoặc business planner | Cron không tự biết mọi ngày nghỉ |
| Gửi nhắc trước cuộc hẹn 24 giờ | Tính `Instant` rồi one-shot | Phải cập nhật/hủy khi appointment đổi |
| Chuỗi “sau sự kiện A thì chờ 3 ngày” | Schedule động hoặc workflow engine | Có thể cần state machine |

Trước khi chọn trigger, hãy hỏi liệu nghiệp vụ muốn **khoảng cách thời gian thực** (ví dụ 24 giờ kể từ sự kiện) hay **giờ trên đồng hồ địa phương** (ví dụ 09:00 mỗi ngày). Hai ý nghĩa có thể khác nhau qua DST.

## 19. @DisallowConcurrentExecution không phải idempotency

Annotation:

```java
@DisallowConcurrentExecution
public class MailOccurrenceJob implements Job {
    // ...
}
```

giúp Quartz không thực thi đồng thời nhiều instance của **cùng JobDetail/JobKey** theo quy tắc Quartz.

Nhưng:

- Hai JobKeys khác nhau có thể cùng tạo notification cho một recipient.
- Một job có thể fire lần nữa sau khi lần trước hoàn thành.
- Một trigger được retry/recovered có thể lặp lại side effect.
- Scheduler ngoài không biết annotation này.
- SMTP accepted rồi crash không thể bị rollback.

Chỉ dựa vào annotation không ngăn được một occurrence bị insert hai lần. **Unique constraint trên occurrence business key vẫn là lớp bảo vệ cần có.**

## 20. Misfire là gì?

**Misfire** xảy ra khi Quartz nhận ra một trigger đã lỡ thời điểm cần fire theo các ngưỡng/cơ chế của nó, ví dụ process down, thread pool bận, database unavailable, hoặc scheduler pause.

```text
09:00  Trigger should fire
08:58  App stopped
09:00  No worker available
09:30  App restarted
        |
        v
Quartz detects missed fire
        |
        v
Apply misfire instruction
```

Một số chính sách thường dùng cho `CronTrigger`:

| Policy | Ý nghĩa khái quát | Phù hợp |
| --- | --- | --- |
| Smart policy (mặc định) | Quartz chọn cách xử lý theo loại trigger | Chỉ khi đã hiểu behavior của type |
| `withMisfireHandlingInstructionFireAndProceed()` | Thực hiện một lần ngay rồi tiếp tục lịch | Nhắc việc cần chạy bù một lần |
| `withMisfireHandlingInstructionDoNothing()` | Bỏ những firing đã lỡ, chờ lịch tương lai | Digest/nhắc lịch quá hạn không còn giá trị |
| Ignore misfire policy | Bỏ qua cơ chế misfire chuẩn | Cần hiểu nguy cơ backlog và burst |

Với `SimpleTrigger`, bộ misfire instructions khác `CronTrigger` và phụ thuộc kiểu lặp. Không dùng tên instruction của CronTrigger cho SimpleTrigger.

### “Fire once now” không tự replay mọi occurrence

Nếu một cron job mỗi 5 phút bị down hai giờ, một chính sách “fire once now” **không mặc định tạo 24 email cho 24 thời điểm đã lỡ**. Nó có thể kích hoạt **một lần chạy bù**, còn việc backfill 24 periods phải do domain planner đảm nhiệm nếu cần.

### Không để misfire gây mail storm

Giả sử 50.000 tenant có lịch gửi vào cùng đầu giờ. Sau downtime, chạy bù tất cả ngay có thể:

- Vượt SMTP quota.
- Chiếm toàn bộ Quartz worker threads.
- Tăng queue backlog, CPU và memory.
- Gây cảnh báo spam/rate limit.
- Gửi những thông báo đã hết giá trị.

Nên có policy về giới hạn tuổi occurrence, batch size, rate limiting và pacing cho việc khôi phục. Misfire instruction chỉ quyết định **khi Quartz kích hoạt**, không giải quyết tổng tải và nghiệp vụ gửi bù.

## 21. Chính sách nghiệp vụ cho lịch đã quá hạn

Một lần fire trễ không phải lúc nào cũng nên được xử lý giống nhau:

| Loại email | Ví dụ | Khi lỡ 3 giờ | Gợi ý policy |
| --- | --- | --- | --- |
| OTP hoặc mã xác thực | Mã hết hạn sau 5 phút | Không còn tác dụng | Bỏ qua, tạo mã mới khi có yêu cầu |
| Nhắc cuộc hẹn | Nhắc trước 1 ngày | Có thể vẫn hữu ích | Kiểm tra cuộc hẹn còn tương lai |
| Báo cáo định kỳ | Tổng hợp ngày làm việc | Có thể cần backfill | Dùng business period ID |
| Hóa đơn | Phát hành theo kỳ thanh toán | Không nên mất | Tạo occurrence/outbox idempotent |
| Marketing campaign | Gửi trong khung giờ cho phép | Có thể không còn hợp lệ | Kiểm tra window, consent, suppression |
| Cảnh báo bảo mật | Phát hiện bất thường | Có thể cần thông báo càng sớm càng tốt | Kiểm tra dữ liệu, độ ưu tiên, deadline |

Một policy tổng quát:

```text
Quartz fires occurrence
      |
      v
Does schedule exist and active?
      |
      +-- No -> skip/audit
      |
      v
Is planned time still eligible?
      |
      +-- Too old -> SKIPPED_STALE
      |
      v
Has this logical occurrence been materialized?
      |
      +-- Yes -> no-op (idempotent)
      |
      v
Create outbox notification(s)
```

Quartz có thể quyết định “fire now”, nhưng **business service phải quyết định gửi email hay không** dựa trên tình trạng sự kiện thực tế, thời hạn nội dung và recipient eligibility.

## 22. Time zone: lưu Instant và diễn giải giờ địa phương

Có hai loại ý định lịch thường gặp:

**A. Gửi tại một thời điểm tuyệt đối.**

> Gửi đúng lúc 2026-12-05T02:00:00Z.

Nên lưu `Instant` hoặc một timestamp UTC tương đương.

**B. Gửi theo giờ địa phương của người nhận.**

> Gửi lúc 09:00 ngày làm việc, theo Europe/Berlin.

Nên lưu ít nhất:

- Quy tắc cron/local date-time.
- `ZoneId` IANA, ví dụ `Europe/Berlin`.
- Chính sách DST khi local time không tồn tại hoặc lặp lại.
- Phiên bản/ý nghĩa business rule.

Ví dụ chuyển local date-time thành instant:

```java
import java.time.*;

LocalDate date = LocalDate.of(2026, 12, 5);
LocalTime time = LocalTime.of(9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime scheduledLocal = ZonedDateTime.of(
        date, time, zone
);
Instant plannedAt = scheduledLocal.toInstant();
```

`Instant` thích hợp cho **one-shot scheduling**. CronTrigger lại mô tả một quy tắc lặp và time zone nên sẽ cần giữ `ZoneId` để các lần tương lai vẫn diễn ra lúc 09:00 địa phương.

## 23. Daylight Saving Time (DST): một giờ có thể không tồn tại hoặc lặp hai lần

Ở một số múi giờ có chuyển đổi DST:

- Khi đồng hồ **nhảy tiến**, một số local times không tồn tại.
- Khi đồng hồ **quay lùi**, một số local times xuất hiện hai lần với hai UTC offsets.

Ví dụ: lịch “02:30 mỗi ngày” tại một múi giờ có DST có thể không có một firing 02:30 vào ngày chuyển đổi mùa xuân, hoặc gặp giờ lặp trong ngày chuyển đổi mùa thu.

**Không tự cộng 24 giờ vào Instant rồi khẳng định vẫn là 09:00 địa phương hôm sau.** Nếu business muốn “mỗi ngày lúc 09:00 giờ địa phương”, hãy tính lần kế tiếp theo quy tắc local time + `ZoneId` và để scheduler dùng timezone đó.

### Quy tắc nên được quyết định trước

Với local time không tồn tại:

- Bỏ qua occurrence?
- Chạy tại thời điểm hợp lệ tiếp theo?
- Chuyển sang một giờ khác theo policy?

Với giờ lặp:

- Chạy một lần trong ngày?
- Chạy ở offset trước hay offset sau?
- Có trường hợp nghiệp vụ thực sự cần hai lần không?

Quartz/CronTrigger có behavior riêng cho DST theo implementation. Nếu sản phẩm yêu cầu semantics cực kỳ chính xác, hãy **lưu business occurrence theo local date + policy** và kiểm thử qua các ngày DST; không chỉ nhìn cron expression rồi suy đoán.

## 24. Lưu giờ người nhận hay giờ người tạo lịch?

Một câu hỏi có thể làm thay đổi nội dung nghiệp vụ:

> Email được gửi lúc 09:00 theo múi giờ nào?

Các lựa chọn khác nhau:

- Theo múi giờ cố định của tổ chức.
- Theo múi giờ khách hàng tại thời điểm tạo schedule.
- Theo múi giờ khách hàng hiện tại mỗi lần thực thi.
- Theo múi giờ của cửa hàng/địa điểm.

Ví dụ khách hàng chuyển từ Hà Nội sang Berlin. Nếu yêu cầu là “09:00 giờ địa phương của khách hàng **hiện tại**”, cần cập nhật hoặc tái tính lịch khi timezone của khách hàng đổi. Nếu yêu cầu là “09:00 giờ của chi nhánh”, không nên dùng timezone profile.

Chọn một policy, lưu rõ trong schedule record và audit khi thay đổi. Không dựa vào default timezone của JVM hoặc container.

## 25. Cơ sở dữ liệu nghiệp vụ cho schedule và occurrence

Quartz JDBC tables quản lý job/trigger state; ứng dụng thường vẫn cần **business schedule tables** để quản lý owner, consent, template và kết quả.

Schema PostgreSQL minh họa:

```sql
CREATE TABLE mail_schedule (
    schedule_id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    schedule_kind VARCHAR(20) NOT NULL,
    cron_expression VARCHAR(120),
    zone_id VARCHAR(100) NOT NULL,
    one_shot_at TIMESTAMPTZ,
    state VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    template_key VARCHAR(100) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mail_schedule_occurrence (
    schedule_id UUID NOT NULL
        REFERENCES mail_schedule(schedule_id),
    planned_fire_at TIMESTAMPTZ NOT NULL,
    materialized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    result VARCHAR(30) NOT NULL,
    PRIMARY KEY (schedule_id, planned_fire_at)
);

CREATE TABLE mail_outbox (
    notification_id UUID PRIMARY KEY,
    schedule_id UUID NOT NULL,
    planned_fire_at TIMESTAMPTZ NOT NULL,
    recipient_id UUID NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (schedule_id, planned_fire_at, recipient_id)
);
```

Đây là **schema giảng dạy**. Trong production cần thêm foreign keys/indices, tenancy scope, data retention, attempt records, constraints cho `state`, chiến lược partition và quản lý migration.

### Vì sao occurrence có khóa duy nhất?

`PRIMARY KEY (schedule_id, planned_fire_at)` bảo đảm một logical schedule occurrence không bị insert hai lần trong cùng phạm vi khóa.

`UNIQUE(schedule_id, planned_fire_at, recipient_id)` bảo vệ từng notification recipient trong occurrence. Nếu hai worker cùng materialize do recovery/retry, transaction phải có logic idempotent insert.

### Trường hợp schedule được sửa cùng thời điểm?

Nếu business cho phép hủy/thay đổi lịch và tạo lại một lần gửi cùng `planned_fire_at`, cần xác định liệu occurrence cũ được xem là cùng event hay một **schedule revision** mới. Có thể đưa `schedule_version` vào business key, nhưng điều đó cho phép nhiều notification có cùng thời điểm nếu version thay đổi.

Không tự thêm revision vào khóa để “giải quyết conflict” nếu sản phẩm **không được phép gửi lại** khi sửa lịch. Đây là quyết định nghiệp vụ, không đơn thuần là kỹ thuật index.

## 26. Materialize occurrence bằng transaction idempotent

Khi Quartz Job hoặc scheduler ngoài kích hoạt, service nên:

1. Bắt đầu transaction.
2. Khóa hoặc đọc schedule với concurrency control phù hợp.
3. Kiểm tra `state=ACTIVE`, version và business eligibility.
4. Kiểm tra mốc thời gian có thuộc quy tắc/chính sách còn hiệu lực.
5. Insert một occurrence theo unique key.
6. Nếu occurrence đã tồn tại, **không insert outbox trùng**.
7. Insert một hoặc nhiều notification theo recipient, mỗi cái có unique business key.
8. Commit transaction.
9. Để mail worker lấy outbox và gửi riêng.

Ví dụ PostgreSQL:

```sql
INSERT INTO mail_schedule_occurrence (
    schedule_id, planned_fire_at, result
)
VALUES (
    :scheduleId, :plannedAt, 'MATERIALIZED'
)
ON CONFLICT (schedule_id, planned_fire_at)
DO NOTHING
RETURNING schedule_id;
```

Nếu query trả **không có dòng**, occurrence có thể đã được materialize trước đó. Nếu có dòng, transaction hiện tại sở hữu lần tạo mới và có thể insert các outbox records liên quan.

### Tại sao tạo occurrence và outbox trong cùng transaction?

Giả sử:

```text
INSERT occurrence -> COMMIT
process crashes
INSERT outbox never happens
```

Nếu lần sau chỉ nhìn occurrence tồn tại rồi bỏ qua, email sẽ không được tạo. Cần **cùng transaction** hoặc một state machine có khả năng resume việc materialize thiếu, không để một commit giữa chừng tạo “đã xử lý” giả.

Một quy trình transactional minh họa:

```text
BEGIN
  SELECT schedule FOR UPDATE
  IF inactive/stale: record skip per policy; COMMIT
  INSERT occurrence ON CONFLICT DO NOTHING RETURNING ...
  IF inserted:
      INSERT outbox for recipients
COMMIT
```

Không gửi SMTP bên trong transaction này. SMTP side effect không thể rollback cùng database.

## 27. Java service cho idempotent occurrence

Ví dụ phân tách trách nhiệm:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Service
public class ScheduleDispatchService {

    private final MailScheduleRepository schedules;
    private final MailOccurrenceRepository occurrences;
    private final MailOutboxRepository outbox;

    public ScheduleDispatchService(
            MailScheduleRepository schedules,
            MailOccurrenceRepository occurrences,
            MailOutboxRepository outbox
    ) {
        this.schedules = schedules;
        this.occurrences = occurrences;
        this.outbox = outbox;
    }

    @Transactional
    public void materializeOccurrence(
            UUID scheduleId,
            Instant plannedAt
    ) {
        MailSchedule schedule = schedules.lockById(scheduleId);

        if (!schedule.isActive()
                || !schedule.allowsFireAt(plannedAt)) {
            return;
        }

        boolean inserted = occurrences.insertIfAbsent(
                scheduleId, plannedAt
        );

        if (!inserted) {
            return; // duplicate logical firing
        }

        for (UUID recipientId : schedule.recipientIds()) {
            outbox.insertIfAbsent(
                    UUID.randomUUID(),
                    scheduleId,
                    plannedAt,
                    recipientId,
                    schedule.templateKey(),
                    schedule.templateVersion()
            );
        }
    }
}
```

`MailScheduleRepository`, `MailOccurrenceRepository`, `MailOutboxRepository` và `MailSchedule` là **abstractions do ứng dụng tự xây**, không phải API sẵn có của Spring/Quartz. Method `insertIfAbsent` nên dựa vào **unique constraint thực trong database**, không chỉ query `exists` rồi `insert`.

### Lưu ý transaction và exception

Tùy công nghệ persistence, một lỗi SQL uniqueness có thể làm transaction bị đánh dấu rollback-only. Dùng `ON CONFLICT DO NOTHING` hoặc một operation tương đương với contract rõ ràng thường dễ giữ atomicity hơn `catch DuplicateKeyException` rồi tiếp tục sử dụng cùng transaction một cách tùy tiện.

Các transaction materialize phải đủ ngắn. Đừng render PDF lớn, gọi object storage chậm hoặc gửi SMTP trong lúc giữ row lock của schedule.

## 28. Planned time dùng làm idempotency key có ổn không?

Với Quartz, `context.getScheduledFireTime()` phản ánh thời điểm trigger dự kiến cho một execution theo mô hình Quartz.

```java
Instant plannedAt =
        context.getScheduledFireTime().toInstant();
```

Giá trị này có ích khi mỗi lần fire đúng một business occurrence. Tuy nhiên, cần đánh giá:

- Misfire fire-once-now có thể đại diện cho một lần chạy bù, **không phải toàn bộ lịch sử các mốc đã lỡ**.
- Reschedule hoặc time zone update có thể thay đổi planned fire times.
- Recovery/job refire có thể có semantics khác với một regular firing.
- Một business period “báo cáo tháng 10” không nhất thiết được định danh bằng UTC timestamp của trigger.

Với báo cáo theo tháng, một khóa như `scheduleId + periodYearMonth` có thể đúng hơn. Với nhắc lịch one-shot, `scheduleId + appointmentVersion` hoặc một `occurrenceId` được tạo khi lịch đăng ký có thể phù hợp.

**Idempotency key phải đại diện cho sự kiện nghiệp vụ**, không chỉ copy một timestamp mà không hiểu cách thay đổi lịch.

## 29. Reconciliation: xử lý lịch bị lỡ dù Quartz đã chạy lại

Quartz xử lý trigger state và misfires, nhưng ứng dụng vẫn nên có một job đối soát:

```text
Reconciliation worker
       |
       v
Scan eligible schedules / business periods
       |
       v
Compute expected logical occurrences
       |
       v
Compare with mail_schedule_occurrence
       |
       +-- Exists -> no-op
       |
       +-- Missing -> materialize idempotently
       |
       v
Outbox resumes sending
```

Ví dụ một báo cáo bắt buộc được tạo mỗi ngày theo business calendar, nhưng cluster down ba ngày. Quartz misfire có thể chỉ đưa ra một callback; reconciliation mới phát hiện **ba business periods chưa được materialize** và tạo lại theo policy, có giới hạn.

Đối soát cần:

- Giới hạn lookback window.
- Phân biệt schedule đã hủy, paused và stale.
- Áp dụng lịch ngày nghỉ, DST, thời hạn nghiệp vụ.
- Không tạo hàng triệu occurrence trong một giao dịch.
- Có backpressure và quota SMTP.
- Ghi audit lý do backfill.

## 30. Hủy lịch: hủy Quartz trigger chưa đủ

Một API hủy lịch có thể:

1. Cập nhật `mail_schedule.state=CANCELED` trong database nghiệp vụ.
2. Ghi audit người thực hiện và thời điểm.
3. Gọi `quartz.unscheduleJob(triggerKey)` hoặc `deleteJob(jobKey)` tùy contract.
4. Đảm bảo job nếu vẫn fire do race **kiểm tra state trước materialize**.
5. Xác định xử lý các outbox notifications đã được tạo trước đó.

Nếu chỉ xóa trigger:

```text
Trigger already acquired by Quartz node A
User calls unschedule on node B
Node A executes job that was already acquired
```

chưa chắc loại bỏ được công việc đang chạy. **Business state trong database là lớp quyết định cuối**.

### Hủy cả email đã vào outbox?

Cần phân biệt:

- Schedule bị hủy nhưng notification chưa materialize.
- Notification đã materialize, đang `PENDING`.
- Notification đang `PROCESSING` hoặc đã được SMTP provider accepted.

Ở trạng thái sau cùng, ứng dụng **không thể thu hồi SMTP email đã submit** bằng cách unschedule Quartz. Một cancellation policy có thể ngăn những notification `PENDING`, nhưng với `SUBMITTED` chỉ có thể ghi nhận lịch sử và hỗ trợ downstream policy khi provider cho phép.

## 31. Reschedule an toàn

Quartz cung cấp `rescheduleJob(TriggerKey, Trigger)` để thay trigger theo định danh. Nhưng sửa lịch gửi một email còn liên quan:

- Version của schedule nghiệp vụ.
- Mốc thời gian đã materialize.
- Notifications đang chờ.
- Business data/template snapshot.
- Race giữa trigger cũ và update.
- Audit người đổi lịch.

Một quy trình:

```text
User requests new date/time
       |
       v
Check version and authorization
       |
       v
Update business schedule (version++)
       |
       v
Reschedule Quartz trigger
       |
       v
Reconciliation verifies alignment
```

**Database nghiệp vụ và Quartz JobStore có thể không commit trong cùng một transaction**, tùy cấu hình. Nếu update business schedule thành công rồi reschedule Quartz thất bại, cần retry/reconcile, không để “UI đã đổi lịch” nhưng Quartz còn trigger cũ mà không có biện pháp phát hiện.

Một cách khác là lưu business schedule làm source of truth, sau đó một registrar worker idempotent cập nhật Quartz. Nhờ đó một lỗi ngắn ở Quartz không làm mất ý định thay lịch.

## 32. Race giữa hủy lịch và Job.execute

Tình huống:

```text
Worker A: reads schedule ACTIVE
User B: cancels schedule
Worker A: inserts outbox notification
```

Nếu business yêu cầu **hủy là không tạo thêm notification sau commit**, phải dùng concurrency control trong database để quy định thứ tự hợp lệ.

Ví dụ:

- Service materialize khóa schedule row bằng `SELECT ... FOR UPDATE`.
- API cancel cũng cập nhật row với locking/version check.
- Nếu cancel commit trước, materialization đọc `CANCELED` và bỏ qua.
- Nếu materialization commit trước, notification đã được tạo; API cancel phải xử lý notification pending theo policy.

Không nên hứa “click cancel nghĩa là chắc chắn email chưa bao giờ được gửi” khi worker đã bắt đầu SMTP I/O trước đó.

## 33. Lập lịch email có attachment hoặc nội dung biến đổi

Email sẽ gửi sau hai tháng có thể phụ thuộc:

- Template đã đổi.
- Giá/đơn hàng đã được điều chỉnh.
- Recipient thay đổi địa chỉ.
- Attachment file hết hạn.
- Token trong URL bị hết hạn.
- Quyền nhận mail/consent thay đổi.

Cần xác định chiến lược:

| Loại dữ liệu | Quy tắc gợi ý |
| --- | --- |
| Thông tin hóa đơn đã phát hành | Snapshot/version bất biến |
| Lịch hẹn tương lai | Kiểm tra trạng thái mới nhất khi materialize |
| Marketing consent | Kiểm tra eligibility ngay trước submission |
| Token reset/OTP | Tạo sát thời điểm gửi với TTL hợp lệ |
| Template | Lưu version hoặc policy dùng phiên bản mới nhất |
| Attachment | Immutable storage key/version, kiểm tra tồn tại |
| Recipient | Lưu recipient ID, giải quyết địa chỉ theo policy |

Đừng serialize sẵn một `MimeMessage` chứa OTP ngắn hạn rồi cất nó trong Quartz JobDataMap vài tuần. Việc lưu lịch và việc tạo nội dung gửi nên được tách để dữ liệu có vòng đời phù hợp.

## 34. Scheduler ngoài là gì?

**Scheduler ngoài** là một dịch vụ hoặc thành phần vận hành **bên ngoài tiến trình ứng dụng gửi mail**. Nó giữ lịch hoặc kích hoạt tác vụ theo thời gian rồi gọi một endpoint, phát message vào queue hoặc khởi chạy một worker.

Ví dụ theo nhóm:

- **Cron ở hệ điều hành hoặc máy chủ quản lý tác vụ:** chạy script/command định kỳ.
- **Kubernetes CronJob:** tạo Kubernetes Job/Pod theo lịch cron của cluster.
- **Cloud-managed scheduler:** nền tảng cloud giữ lịch và gửi HTTP/queue event đến target.
- **Workflow orchestration engine:** chạy chuỗi công việc bền vững với timer/wait state.
- **Enterprise job scheduler:** hệ thống trung tâm có audit, dependency, RBAC và vận hành.

Điểm chung là **lịch không phụ thuộc vào việc một instance ứng dụng mail sống liên tục**. Nhưng scheduler ngoài chỉ giúp kích hoạt theo quy tắc riêng của nó; phần còn lại vẫn là trách nhiệm ứng dụng:

```text
External Scheduler
     |
     +-- HTTP request / Queue message / Batch job
     |
     v
Application Scheduler Receiver
     |
     v
Validate request + map schedule
     |
     v
Idempotent occurrence/outbox insert
     |
     v
Mail Worker -> JavaMailSender
```

**Không nên gán lịch bền vững cho một cron script nằm trên một máy mà không có backup và monitoring.** Lịch chỉ bền vững nếu chính hệ thống scheduler và cấu hình của nó có cơ chế lưu trữ/khôi phục, và target cũng xử lý retry đúng.

## 35. Một scheduler ngoài thường có ba kiểu gọi

### A. Gọi HTTP endpoint

```text
Cloud Scheduler
     |
     v
POST /internal/schedules/tick
     |
     v
Application creates due outbox notifications
```

Thuận tiện khi ứng dụng cung cấp HTTP API, nhưng cần authentication, request integrity, timeout, retry policy và idempotency.

### B. Phát queue message

```text
Managed Scheduler
     |
     v
Message queue/topic
     |
     v
Worker consumer
     |
     v
Occurrence/outbox service
```

Queue bền vững có thể giúp tách scheduler khỏi thời gian xử lý business, nhưng cần nắm acknowledgment, at-least-once delivery, duplicate và poison-message handling của queue.

### C. Khởi tạo batch worker

```text
Kubernetes CronJob
     |
     v
Pod runs "claim due schedules" command
     |
     v
Database transaction
     |
     v
Outbox rows
```

Hữu ích khi một job định kỳ chỉ cần quét database và kết thúc. Không nên để mỗi batch pod cố gửi hàng chục nghìn email đồng bộ mà không có quota/backpressure.

## 36. Đừng tạo một cloud schedule cho mỗi email mà không xét quota

Có hai mô hình phổ biến:

**Per-notification schedule**:

```text
Email 1 -> Schedule 1
Email 2 -> Schedule 2
...
Email 100000 -> Schedule 100000
```

**Shared tick + due-time database**:

```text
External scheduler calls every minute
             |
             v
      Application scans DB
             |
             v
       Due notifications
```

Per-notification schedule có thể phù hợp khi số lượng lịch ít, mỗi lịch cần lifecycle riêng và provider cho phép. Với số lượng lớn, cần kiểm tra:

- Quota số schedules/region/account.
- API rate limits khi create/update/cancel.
- Chi phí lưu lịch và mỗi invocation.
- Độ chính xác/độ trễ được nền tảng cam kết.
- Thời gian tối thiểu giữa đăng ký và fire.
- Retention/cancellation semantics.
- Cách phục hồi nếu tạo lịch ở provider thành công nhưng database ứng dụng commit thất bại.

Mô hình shared tick thường đơn giản hơn khi hệ thống đã có **notification table với `due_at` và index**. Scheduler ngoài lúc ấy chỉ bảo đảm có worker định kỳ quét, còn schedule source of truth nằm trong database ứng dụng.

## 37. Dùng external tick để gọi due-time scanner

Một kiến trúc:

```text
External Scheduler (e.g. every 1 minute)
                  |
                  v
       POST /internal/mail-schedules/tick
                  |
                  v
          Verify caller identity
                  |
                  v
        Dispatch due scanner task
                  |
                  v
     SELECT due schedules in batches
                  |
                  v
       Claim + materialize outbox
                  |
                  v
         Mail outbox workers
```

Endpoint nên làm ít việc: xác thực, kiểm tra request, ghi signal hoặc kích hoạt process ngắn, rồi trả acknowledgment. Nếu việc quét hàng triệu schedules tốn vài phút, có thể chuyển công việc cho worker/queue có durability thay vì giữ HTTP connection mở.

### Endpoint minh họa trong Spring Boot

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/mail-schedules")
public class MailScheduleTickController {

    private final SchedulerCallerVerifier verifier;
    private final DueScheduleDispatcher dispatcher;

    public MailScheduleTickController(
            SchedulerCallerVerifier verifier,
            DueScheduleDispatcher dispatcher
    ) {
        this.verifier = verifier;
        this.dispatcher = dispatcher;
    }

    @PostMapping("/tick")
    public ResponseEntity<Void> tick(
            @RequestHeader HttpHeaders headers,
            @RequestBody byte[] rawBody
    ) {
        // Authn/authz + request integrity theo
        // contract cụ thể của scheduler ngoài.
        verifier.verifyOrThrow(headers, rawBody);

        // Nên enqueue/persist một tick task hoặc
        // kích hoạt worker có admission control.
        dispatcher.requestDueScan();

        return ResponseEntity.accepted().build();
    }
}
```

`SchedulerCallerVerifier` và `DueScheduleDispatcher` là interfaces **do ứng dụng tự thiết kế**. Code trên không tự xác thực chỉ vì có `verifyOrThrow`; cần hiện thực nó theo tài liệu của nền tảng gọi, cấu hình security filter và bảo đảm `requestDueScan()` không mất task trước khi phản hồi thành công.

### Chọn HTTP status cẩn thận

- Nếu một request bị từ chối do không có quyền: không trả `2xx`.
- Nếu đã ghi một durable work item: có thể trả `202 Accepted` theo contract.
- Nếu database/queue không thể tiếp nhận tick: trả lỗi thích hợp để scheduler có cơ hội retry.
- Nếu tick duplicate: có thể trả thành công idempotently.
- Nếu có challenge/handshake riêng của provider: xử lý theo contract tương ứng.

**Không trả `202` rồi khởi chạy một fire-and-forget thread không có durable state**, vì process có thể chết trước khi worker thực hiện.

## 38. Bảo vệ endpoint scheduler ngoài

Endpoint nội bộ có thể bị truy cập từ mạng không tin cậy nếu cấu hình firewall/routing sai. Một request giả mạo có thể kích hoạt hàng loạt notifications.

Các cơ chế thường cân nhắc:

1. Identity token được provider phát hành, audience và issuer phù hợp.
2. mTLS giữa scheduler và target.
3. Signature/HMAC trên raw request theo contract.
4. Service account/IAM chỉ có quyền trigger đúng target.
5. Private network endpoint hoặc allowlist như một lớp bổ sung.
6. Rate limit và request body size limit.
7. Replay protection bằng timestamp/nonce khi giao thức hỗ trợ.
8. Audit scheduler caller và schedule scope.
9. Không log JWT, OAuth token, HMAC secret hay raw request credentials.
10. Key rotation và expiration phù hợp.

Không nhận một `scheduleId` bất kỳ từ HTTP rồi thực thi nếu caller chưa được cấp quyền trên schedule ấy. Nếu endpoint là một shared tick, có thể **không cần cho caller chỉ định recipient hoặc schedule ID nào cả**; worker tự quét dữ liệu đã được phép trong database.

### Chữ ký phải kiểm trên đúng bytes

Khi external scheduler dùng signature trên HTTP body, verify raw body theo thuật toán/chuỗi canonical mà nền tảng quy định. Không tự parse JSON, sắp xếp lại property và reserialize rồi so chữ ký nếu provider ký raw bytes.

## 39. External scheduler có thể giao trùng hoặc muộn

Một scheduler managed có thể retry invocation khi target timeout hoặc trả lỗi. Nó cũng có thể có jitter/độ trễ do hạ tầng.

```text
09:00:00  Scheduler sends tick T
09:00:03  Application writes outbox, but response lost
09:01:00  Scheduler retries tick T
09:01:05  Application receives same logical work again
```

Nếu materialization dùng **unique business occurrence key**, tick lặp lại chỉ là một lần thử lại no-op đối với những notification đã được tạo. Nếu code “nhận tick => send SMTP ngay”, request retry có thể gửi hai lần.

Không được nhầm “scheduler có retry” với “ứng dụng đã có exactly-once execution”. Thực tế nên thiết kế receiver/worker **idempotent** và lưu audit của logical occurrence.

### Độ chính xác của thời gian

Cron của hạ tầng không nhất thiết kích hoạt đúng từng giây; một số nền tảng có cửa sổ hoặc jitter. Nếu SLA yêu cầu email đúng 09:00:00 ± vài mili giây, một pipeline có database, queue, template rendering và SMTP bên ngoài **không thể cam kết độ chính xác đó** chỉ vì scheduler trigger đúng giờ.

Nên xác định SLO thực tế: “notification được materialize trong vòng X phút sau due time”, “SMTP submission p95 trong Y phút”, rồi đo bằng timestamp.

## 40. Kubernetes CronJob: hữu ích nhưng không phải outbox

Một Kubernetes CronJob có thể chạy mỗi phút để gọi một batch worker:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mail-schedule-tick
spec:
  schedule: "*/1 * * * *"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 120
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 2
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: tick
              image: example.internal/mail-schedule-worker:stable
              args: ["--mode=scan-due"]
```

YAML là cấu hình minh họa; image, RBAC, secrets, resources, securityContext và cách truy cập database phải được cấu hình theo cluster thật.

Các điểm cần hiểu:

- `schedule` là cron theo semantics Kubernetes.
- `concurrencyPolicy: Forbid` ngăn một số overlap Jobs do cùng CronJob controller quản lý, **không phải lock database toàn cluster**.
- Một controller có thể tạo job muộn hoặc bỏ qua khi quá hạn theo policy.
- Nếu process chạy xong nhưng update status thất bại, lần sau vẫn có thể xử lý lại.
- Nếu nhiều CronJobs khác nhau quét cùng bảng, concurrencyPolicy của từng CronJob không bảo vệ chéo.
- Không mặc định CronJob cho phép đảm bảo mỗi giờ chỉ có một side effect SMTP.

Tùy phiên bản Kubernetes và tính năng được hỗ trợ, CronJob có thể có `timeZone`. Nếu không quy định, cron sẽ được diễn giải theo timezone của controller/cluster theo cấu hình; tránh phụ thuộc default khi yêu cầu gửi theo giờ người nhận. Với lịch cá nhân theo nhiều timezone, thường nên để business DB lập kế hoạch từng occurrence.

## 41. CronJob Forbid và Replace không thay transaction/idempotency

`concurrencyPolicy` thường có các lựa chọn như `Allow`, `Forbid` và `Replace`:

| Policy | Ý nghĩa ở tầng Kubernetes Job | Rủi ro trong email |
| --- | --- | --- |
| Allow | Có thể có nhiều job instances overlap | Cần DB claim để tránh xử lý trùng |
| Forbid | Tránh overlap thuộc CronJob đó | Một lần bị bỏ có thể cần backfill |
| Replace | Dừng job cũ và khởi chạy job mới | Dừng trong lúc SMTP I/O có thể để lại outcome UNKNOWN |

**Đừng dùng Replace cho mail worker quan trọng mà không xử lý trạng thái mơ hồ.** Một pod bị dừng sau khi server nhận DATA nhưng trước khi lưu `SUBMITTED` có thể khiến lần sau gửi lại cùng notification.

## 42. Cloud scheduler và message queue

Một scheduler ngoài có thể phát một event nhỏ:

```json
{
  "eventType": "MAIL_DUE_SCAN",
  "triggerId": "scheduler-tick-demo-001",
  "scheduledFor": "2026-12-05T02:00:00Z"
}
```

Đây là **payload ví dụ do ứng dụng định nghĩa**, không phải schema chung của một dịch vụ cloud cụ thể. Provider có thể có event envelope, ID và retry policy riêng.

Consumer nên:

1. Xác thực nguồn queue/topic theo IAM.
2. Parse/validate schema version.
3. Ghi hoặc sử dụng idempotency key thích hợp.
4. Scan due schedules theo transaction/claim.
5. Acknowledge queue message **sau khi đã xử lý bền vững ở mức cần thiết**.
6. Khi lỗi, áp dụng retry/DLQ policy đã định nghĩa.

Nếu scanner chỉ dùng message như một “tín hiệu hãy quét DB”, việc phát trùng tick thường an toàn khi DB claim/idempotency đúng. Đây là lợi thế của shared tick so với việc chứa toàn bộ recipient/attachment trong scheduler message.

## 43. Dùng database scanner mà không cần Quartz

Nếu tất cả lịch là one-shot hoặc đã được lưu thành `due_at` trong application database, có thể không cần Quartz.

```text
mail_notification:
  id, due_at, status, recipient_id, payload_reference

Worker:
  poll eligible due rows
  claim rows safely
  process each notification
  update outcome
```

Một truy vấn PostgreSQL tiêu biểu:

```sql
SELECT notification_id
FROM mail_notification
WHERE status = 'PENDING'
  AND due_at <= now()
ORDER BY due_at, notification_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

**Đây chỉ là phần chọn rows trong một transaction**, chưa phải worker hoàn chỉnh. Phải update claim state/lease **trước khi commit** để worker khác không chọn lại, sau đó xử lý SMTP ngoài transaction.

Nếu dùng cách:

```text
SELECT ... FOR UPDATE SKIP LOCKED
COMMIT
send SMTP
UPDATE status
```

mà không ghi claim bền vững trước commit, lock mất ngay sau commit và worker khác có thể chọn cùng row. Cần state machine `PENDING -> PROCESSING`, lease token, owner và timeout/reclaim.

### Chỉ mục hỗ trợ due scan

```sql
CREATE INDEX ix_mail_notification_due
    ON mail_notification (due_at, notification_id)
    WHERE status = 'PENDING';
```

Index giúp worker tìm công việc đến hạn khi bảng lớn. Tùy database và workload, có thể cần partition/retention hoặc chỉ mục theo tenant/priority. Không quét full table mỗi giây khi có hàng triệu thông báo.

## 44. Cơ chế claim/lease ở database

Một worker lấy `notificationId` và cập nhật:

```text
status       = PROCESSING
claimed_by   = worker-17
lease_until  = now + configuredDuration
attempt_id   = UUID
```

Sau khi commit, worker gửi SMTP và ghi outcome trong transaction riêng. Nếu worker crash, một reconciler có thể tìm những leases quá hạn.

Nhưng lease timeout **không chứng minh SMTP chưa được submit**. Khi worker biến mất sau DATA, lần reclaim có thể gặp outcome `UNKNOWN`. Do đó:

- Ghi `attemptId` trước khi SMTP I/O.
- Ghi stage/evidence hợp lý.
- Không auto resend nếu không có policy với rủi ro duplicate.
- Có tách trạng thái notification và trạng thái attempt.
- Nếu provider có API query thì reconcile theo ID phù hợp.

Claim/lease giải quyết **concurrent workers**, không tự giải quyết **exactly-once SMTP side effect**.

## 45. Quartz so với scanner database: chọn khi nào?

**Quartz JDBC** đáng cân nhắc khi:

- Có nhiều cron rules động và lifecycle độc lập.
- Muốn trigger, calendars, misfire và cluster features có sẵn.
- Đội ngũ có thể quản trị Quartz schema và database contention.
- Số schedule đủ phù hợp với năng lực lưu trữ và vận hành.

**DB due scanner** có thể đơn giản hơn khi:

- Mỗi notification đã có `due_at` rõ ràng.
- Số lượng bản ghi one-shot rất lớn.
- Cần idempotency và state machine sát nghiệp vụ.
- Một shared tick hoặc `@Scheduled` chỉ cần “đánh thức” worker.
- Không cần chức năng cron phức tạp ở từng record.

Hai lựa chọn có thể kết hợp: **Quartz quản lý cron/one-shot triggers, database ứng dụng quản lý occurrences và outbox**. Không nên giữ hai nguồn lịch không đồng bộ mà không có reconciliation.

## 46. Khi nào dùng workflow engine?

Một chuỗi nghiệp vụ:

```text
Payment failed
   |
   v
Wait 1 day
   |
   +-- payment recovered? -> cancel reminder
   |
   v
Send reminder 1
   |
   v
Wait 3 days
   |
   +-- payment recovered? -> stop
   |
   v
Send reminder 2
```

Đây không chỉ là cron; nó là **workflow có state, timers và điều kiện hủy**. Một workflow engine bền vững có thể phù hợp hơn Quartz nếu mỗi instance workflow có nhiều bước, signal, timeout và recovery logic.

Dù engine có cơ chế retry activity, **SMTP send vẫn là side effect**. Mọi activity có thể được thực hiện lại do failure; cần outbox/idempotency và trạng thái outcome như khi dùng Quartz.

Không chọn một workflow engine lớn chỉ để gửi một báo cáo lúc 09:00 nếu Quartz hoặc due scanner đã đáp ứng đầy đủ.

## 47. Tính năng gửi sau của nhà cung cấp email

Một số email providers có API để **schedule send** hoặc “send at” ngay trên nền tảng của họ. Khi đó:

```text
Application
    |
    +-- Submit message + desired send time
    |
    v
Provider queue holds future send
    |
    v
Provider submits at scheduled time
    |
    v
Recipient mail server
```

Ưu điểm có thể có:

- Không cần vận hành Quartz cho từng email.
- Provider có hạ tầng giữ lịch theo contract riêng.
- Giao diện API có thể hỗ trợ cancel hoặc status.

Nhưng cần kiểm tra:

- Khoảng thời gian tối đa được đặt lịch.
- Độ chính xác khi phát hành.
- Quota số scheduled messages.
- Giá thành và giới hạn message size.
- Cách sửa/hủy sau khi scheduling.
- Khả năng lấy lại provider ID hoặc delivery events.
- Chính sách nếu user unsubscribe giữa lúc schedule và send.
- Khả năng chuyển provider mà không làm trùng schedule.

Không mặc định SMTP `JavaMailSender` có một method chuẩn `sendAt(...)` dùng được với mọi provider. Những tính năng hẹn giờ thường là **API riêng của provider** hoặc cơ chế do ứng dụng xây.

### Khi nào nên giữ lịch tại ứng dụng?

Nếu yêu cầu thay đổi theo dữ liệu nghiệp vụ (người dùng hủy cuộc hẹn, hóa đơn điều chỉnh, consent thay đổi), lịch trong database ứng dụng giúp xác định trạng thái cuối tốt hơn. Một scheduler của provider vẫn có thể dùng nhưng phải đồng bộ cancel/update và xử lý event delivery theo contract.

## 48. Scheduler kích hoạt khác SMTP submission khác delivery

Ba trạng thái cần được tách:

```text
SCHEDULED
    |
    v
OCCURRENCE_MATERIALIZED
    |
    v
OUTBOX_PENDING
    |
    v
SMTP_SUBMITTED
    |
    v
REMOTE_DELIVERED / BOUNCED / DEFERRED (nếu có feedback)
```

Một Quartz Job thành công chỉ chứng minh job **đã chạy hết phần việc nó được giao**. Nếu phần việc là insert outbox, nó không chứng minh SMTP đã được gọi. Một HTTP scheduler nhận `202 Accepted` cũng không chứng minh thư đã được gửi.

### Ví dụ trạng thái một occurrence

| Mốc | Dữ liệu | Điều được xác nhận |
| --- | --- | --- |
| 09:00 | Quartz trigger fired | Scheduler attempted to run job |
| 09:00:02 | Occurrence inserted | Business occurrence materialized |
| 09:00:03 | Outbox committed | Notification request durable |
| 09:01:10 | SMTP transport returns success | Message submitted to provider/relay |
| 09:01:45 | Provider delivers to receiving MTA | Remote delivery evidence, nếu có |

Không đặt `email_delivered=true` ở mốc 09:00:02 hoặc 09:01:10 nếu sản phẩm đang nói về delivery tới mailbox server.

## 49. Gửi email từ outbox worker

Một worker có thể load notification đã đến hạn rồi dựng email:

```java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import jakarta.mail.internet.MimeMessage;

public final class ScheduledMailSubmitter {

    private final JavaMailSender sender;
    private final NotificationRepository repository;
    private final MailContentRenderer renderer;

    public ScheduledMailSubmitter(
            JavaMailSender sender,
            NotificationRepository repository,
            MailContentRenderer renderer
    ) {
        this.sender = sender;
        this.repository = repository;
        this.renderer = renderer;
    }

    public void submit(UUID notificationId) throws Exception {
        NotificationWork work =
                repository.loadClaimedWork(notificationId);

        RenderedMail content = renderer.render(work);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("notify@example.org");
        helper.setTo(work.recipientEmail());
        helper.setSubject(content.subject());
        helper.setText(
                content.plainText(),
                content.safeHtml()
        );

        // Business policy/recipient eligibility checked
        // before sending and attempt persisted separately.
        sender.send(message);
    }
}
```

`NotificationRepository`, `NotificationWork`, `MailContentRenderer` và `RenderedMail` là components do ứng dụng định nghĩa. Code rút gọn chỉ minh họa ranh giới **compose -> SMTP send**; hệ thống thật phải lưu attempt, phân loại lỗi, outcome, recipient policy, cleanup và timeout.

Đừng gửi trong một `@Transactional` method kéo dài từ lúc load notification đến khi SMTP trả phản hồi. Dùng transactions ngắn cho claim/record outcome để không giữ database lock qua network I/O.

## 50. Lỗi SMTP có được Quartz tự thử lại không?

Quartz có cơ chế Job execution failures và một số khả năng refire theo `JobExecutionException`, nhưng **không nên dùng cơ chế ấy thay thế hoàn toàn mail retry policy**.

Ví dụ Quartz job gọi SMTP trực tiếp và ném `JobExecutionException` có thể làm job được thực thi lại theo cấu hình. Vấn đề:

- Lỗi mạng sau DATA có thể mang kết quả `UNKNOWN`.
- Người nhận đã được server chấp nhận có thể nhận email trùng.
- Một `MimeMessage` có nhiều recipient có thể thành công một phần.
- Retry liên tục trong Quartz thread pool có thể chiếm hết worker.
- Dữ liệu/attachment có thể hết hạn giữa các lần thử.

Thay vì “hễ SMTP exception là refire ngay”, nên:

1. Materialize outbox từ Quartz.
2. Để mail worker phân loại submission outcome.
3. Chỉ retry các trường hợp policy cho phép.
4. Lưu `attemptId` và thời điểm thử tiếp.
5. Thực hiện rate limit/backoff ngoài Quartz schedule chính.

### Một retry policy minh họa

| Lỗi | Chính sách có thể phù hợp |
| --- | --- |
| Không kết nối được trước SMTP submission | Retry có giới hạn/backoff |
| SMTP `450` tạm thời trước DATA | Retry theo code/stage |
| SMTP `550` recipient vĩnh viễn | Không retry mù; sửa dữ liệu hoặc suppression |
| Authentication/permission sai | Alert/cấu hình lại; không retry liên tục |
| Timeout sau dấu kết thúc DATA | `UNKNOWN`, reconcile trước resend nếu có thể |
| Provider đang `DEFERRED` | Chờ provider lifecycle theo contract |
| Attachment không còn tồn tại | Fail/rebuild theo dữ liệu bất biến và policy |
| Schedule đã hủy | Không tạo thông báo mới; xử lý pending theo policy |

**Không coi mọi SMTP exception là chắc chắn message chưa được gửi.**

## 51. Backoff không nên chặn Quartz scheduler thread

Một anti-pattern:

```java
public void execute(JobExecutionContext context) {
    while (true) {
        try {
            sender.send(message);
            return;
        } catch (Exception ex) {
            Thread.sleep(60000);
        }
    }
}
```

Trong ví dụ này, job giữ một Quartz worker thread qua nhiều lần chờ, không có max attempts, không phân loại lỗi, không lưu state bền vững và có thể gửi trùng.

Thiết kế tốt hơn:

```text
Attempt failed at 09:00
      |
      v
Persist RETRY_WAIT + nextAttemptAt = 09:05
      |
      v
Release worker/thread
      |
      v
Future due scan claims it at 09:05
```

Sử dụng `next_attempt_at` ở database và poller/outbox scheduler thay vì ngủ trong một Java thread. Nếu queue có delayed-message feature, có thể dùng như phần triển khai nhưng vẫn cần durable attempt state và idempotency.

## 52. Cron jobs và campaign email số lượng lớn

Một trigger cron có thể có ý nghĩa “bắt đầu chiến dịch lúc 09:00”. Nó **không có nghĩa** phải gửi toàn bộ 200.000 email ngay trong một `Job.execute`.

```text
09:00 Quartz fire
      |
      v
Create campaign occurrence
      |
      v
Materialize recipients in bounded batches
      |
      v
Durable outbox queue
      |
      +-- Worker 1
      +-- Worker 2
      +-- Worker 3
      |
      v
SMTP/API rate limits and backpressure
```

Những giới hạn cần xác định:

- Số recipients mỗi batch.
- Kích thước MIME trung bình và tối đa.
- SMTP account/provider quota.
- Số connections/workers.
- Memory/CPU/disk băng thông.
- Recipient consent/suppression tại thời điểm gửi.
- Độ trễ tối đa từ lịch đến submission.

Một scheduler thread chỉ nên enqueue/claim có giới hạn, không tự ôm một chiến dịch lớn cho tới khi gửi xong toàn bộ.

## 53. Hàng đợi bền vững không đồng nghĩa gửi đúng một lần

Với outbox hoặc message broker:

```text
Consumer reads notification
       |
       v
SMTP accepts message
       |
       v
Process crashes before ack
       |
       v
Broker redelivers notification
```

Đây là cửa sổ duplicate tồn tại ngay cả khi schedule/queue đều bền vững.

Cần có:

- Một owner cho từng notification.
- Attempt ID được ghi trước SMTP.
- Trạng thái `PROCESSING/SUBMITTED/UNKNOWN`.
- Lease, reclaim và reconciliation có kiểm soát.
- Không tự gửi lại khi không xác định được outcome.
- Provider-specific idempotency API nếu được hỗ trợ và đúng scope.

Không dựa vào header `Message-ID` để khẳng định SMTP relay sẽ tự deduplicate. Standard SMTP không cung cấp giao kèo exactly-once delivery chung.

## 54. Test 1: job và trigger có được persist qua restart?

Một integration test quan trọng cần dùng **JDBC JobStore**, không phải RAMJobStore:

1. Tạo Quartz schema test trong PostgreSQL hoặc database được hỗ trợ.
2. Start scheduler instance A với JDBC JobStore.
3. Đăng ký `JobDetail` và trigger sẽ fire trong tương lai.
4. Shutdown instance A trước `plannedAt`.
5. Start scheduler instance B dùng cùng database, đúng cluster/instance identity.
6. Chờ tới giờ fire bằng một điều kiện có timeout hữu hạn.
7. Xác nhận occurrence/outbox được tạo theo business key.
8. Không cần gửi email thật.

Test này chứng minh Quartz persistence/recovery của **lịch**, và ứng dụng materialize occurrence sau restart, trong phạm vi scenario đã dựng.

### Không gọi RAMJobStore test là restart persistence test

Nếu test tạo scheduler mới với RAMJobStore và tự đăng ký lại toàn bộ trigger từ code, sự kiện vẫn có thể fire. Nhưng điều đó không chứng minh **Quartz đã persist trạng thái** qua restart; nó chỉ chứng minh logic bootstrap của ứng dụng.

Hai kiểu test có mục tiêu khác nhau, cần được đặt tên chính xác.

## 55. Test 2: hai scheduler nodes dùng chung database

Một bài test cluster:

```text
Quartz node A ----+
                  |
                  +---- Shared QRTZ tables
                  |
Quartz node B ----+
                  |
                  v
             One planned firing
                  |
                  v
         Idempotent occurrence insert
```

Mục tiêu:

- Cùng job/trigger state được chia sẻ.
- Hai node có instance IDs khác nhau, cùng logical cluster.
- Một logical occurrence chỉ tạo một occurrence row và tập outbox notification duy nhất.
- Nếu xảy ra recovery hoặc duplicate invocation, database idempotency vẫn ngăn tạo thêm notification trùng.

Đừng kết luận cluster tuyệt đối không bao giờ gọi job hai lần trong mọi failure mode chỉ từ một test happy path.

## 56. Test 3: misfire khi scheduler down

Kịch bản:

```text
09:00 planned fire
08:55 scheduler stopped
09:20 scheduler started again
```

Test hai chính sách:

**A. `DoNothing`** — với báo cáo không còn giá trị khi đã lỡ:

- Không tạo notification tại 09:20 chỉ để bù.
- Lịch tương lai vẫn hoạt động.
- Có metric/audit về missed trigger nếu business cần.

**B. `FireAndProceed`** — với thông báo nên chạy bù một lần:

- Scheduler khởi động lại và kích hoạt một lần phù hợp behavior.
- Business service kiểm tra lịch còn active và occurrence còn eligible.
- Database không tạo duplicate nếu invocation lặp.
- Không khẳng định mọi missed firing đã được phát lại.

Nếu muốn backfill mỗi ngày đã lỡ, thêm test cho business reconciliation tạo từng `businessPeriod` thiếu.

## 57. Test 4: dùng cùng occurrence ID hai lần

Không cần Quartz thật cho test idempotency:

```java
UUID scheduleId = fixedScheduleId();
Instant plannedAt =
        Instant.parse("2026-12-05T02:00:00Z");

dispatchService.materializeOccurrence(
        scheduleId, plannedAt);
dispatchService.materializeOccurrence(
        scheduleId, plannedAt);

assertEquals(
        1,
        occurrenceRepository.countByScheduleAndTime(
                scheduleId, plannedAt)
);
assertEquals(
        expectedRecipients,
        outboxRepository.countByScheduleAndTime(
                scheduleId, plannedAt)
);
```

Các repository/helper được giả định trong test. Với concurrency test, chạy hai transactions song song trong một database thật có unique constraints; unit test gọi hai lần tuần tự không chứng minh không có race condition.

## 58. Test 5: time zone và DST

Những trường hợp nên có:

| Scenario | Điều cần kiểm tra |
| --- | --- |
| One-shot ở múi giờ Việt Nam | UTC instant đúng với local time |
| Cron 09:00 theo Europe/Berlin | Các occurrences quanh thời điểm DST phù hợp policy |
| Local time không tồn tại | Bỏ qua/dịch giờ theo chính sách |
| Local time bị lặp | Không tạo hai emails nếu business chỉ cần một lần/ngày |
| User thay múi giờ | Schedule mới hoặc version đúng theo yêu cầu |
| JVM default timezone thay đổi | Job vẫn dùng zone đã lưu |
| Time zone ID sai | Validation fail thay vì âm thầm fallback |
| One-shot vào quá khứ | Reject hoặc xử lý misfire/stale theo policy |

Để test `CronTrigger`, có thể dùng API tính `nextFireTime` và so sánh những mốc cụ thể với expected local date/zone, thay vì phải ngủ đến ngày DST thật.

## 59. Test 6: hủy lịch sát giờ fire

Một test concurrency có thể dùng hai threads/transactions:

```text
Thread A: claims schedule/starts materialization
Thread B: cancels schedule
Thread A: attempts to insert outbox
```

Yêu cầu:

- Có một thứ tự commit hợp lệ được định nghĩa.
- Nếu cancellation commit trước materialization, không tạo outbox mới.
- Nếu materialization commit trước cancellation, cancellation policy xử lý outbox đang pending.
- Không thể hứa thu hồi email đã gửi SMTP.
- Audit cho biết cancellation có hiệu lực từ lúc nào.

Khi test, dùng latch/barrier để điều khiển thời điểm thay vì `Thread.sleep` tùy ý. Kiểm tra bằng database state, không chỉ assert số lần gọi mock.

## 60. Test 7: external scheduler gọi trùng

Một scheduler ngoài gửi cùng logical tick hai lần:

```text
POST tick-100 -> 202 Accepted
POST tick-100 -> 202 Accepted
```

Kỳ vọng:

- Endpoint xác thực cả hai requests.
- Tick được nhận idempotently.
- Scanner có thể chạy lại nhưng database không tạo duplicate occurrences/outbox.
- Không có hai SMTP attempts chỉ do tick bị gửi trùng.
- Nếu một callback lỗi trước durable acknowledgment, provider có cơ hội retry theo contract.

Với shared due scan, có thể một tick thứ hai chạy song song tick thứ nhất; cần database claim/unique key để an toàn, không chỉ dựa vào dedupe request ID.

## 61. Test 8: lỗi SMTP sau khi lịch đã fire

Kịch bản:

1. Quartz Job fire và materialize outbox thành công.
2. Worker gửi message tới SMTP test server.
3. Server trả `450` hoặc ngắt kết nối trước khi nhận DATA.
4. Attempt ghi `RETRY_WAIT` nếu policy cho phép.
5. Schedule occurrence vẫn chỉ tồn tại **một**.
6. Retry submission sinh **attempt mới**, không phải occurrence mới.

Test khác mô phỏng SMTP đã nhận DATA nhưng mất final reply. Kỳ vọng record `UNKNOWN` và không retry mù; lịch không được ghi nhầm thành failed/missing.

Điều này khẳng định **job scheduling retry** khác với **email submission retry**.

## 62. Test 9: cron trigger có backfill đầy đủ hay không?

Ví dụ business yêu cầu gửi báo cáo cho mỗi ngày làm việc; hệ thống ngừng hoạt động từ thứ Hai đến thứ Tư.

Nếu chỉ dùng Quartz cron “fire once now”, bạn có thể nhận một execution lúc hệ thống khôi phục, trong khi business kỳ vọng ba báo cáo riêng.

Test phải xác định:

1. `expectedBusinessPeriods` là những ngày nào.
2. Mỗi ngày có một `occurrenceKey` riêng.
3. Reconciliation tạo những periods thiếu nhưng chưa hết hạn.
4. Không tạo hai occurrence của cùng ngày nếu Quartz cũng fire trễ.
5. Có giới hạn số báo cáo backfill đồng thời.
6. Có audit và notification status cho từng ngày.

Không nên đặt tên test `replaysAllMissedCronTriggers()` nếu implementation chỉ dùng misfire fire-once-now. Khi business cần replay đầy đủ, đó phải là một **kế hoạch backfill riêng**.

## 63. Test 10: hạ tầng scheduler ngoài đang down

Với shared tick + database:

```text
09:00 tick not delivered
09:01 tick not delivered
09:02 tick delivered
       |
       v
Scanner finds every eligible due record <= current time
       |
       v
Materializes missing outbox with idempotency
```

Điểm quan trọng là **scanner dùng `due_at <= now()`**, không chỉ tìm các records có `due_at == exactly 09:02`. Như vậy một tick bị lỡ không làm mất tất cả những thông báo đã đến hạn.

Nếu quá nhiều công việc dồn lại, worker xử lý theo batch, priority, retry/backpressure, tránh khởi tạo một transaction khổng lồ. Với thông báo quá hạn, vẫn cần xét stale/eligibility policy.

## 64. SLO: “đúng giờ” nên đo thế nào?

Một email scheduled có ít nhất bốn timestamp:

| Timestamp | Ý nghĩa |
| --- | --- |
| `planned_at` | Giờ nghiệp vụ muốn thực hiện |
| `materialized_at` | Giờ occurrence/outbox được tạo |
| `smtp_submitted_at` | Giờ SMTP transport có kết quả accepted |
| `remote_delivered_at` | Giờ provider báo remote delivery, nếu có |

Từ đó:

```text
Scheduling lateness
  = materialized_at - planned_at

Submission delay
  = smtp_submitted_at - materialized_at

End-to-end submission lateness
  = smtp_submitted_at - planned_at

Remote delivery latency
  = remote_delivered_at - smtp_submitted_at
```

**Không tính remote delivery latency khi thiếu provider feedback rồi gán nó bằng 0.** Điều đó làm số liệu đẹp giả.

Ví dụ một SLO nghiệp vụ:

> 99% những notification transactional đủ điều kiện và có due time hợp lệ được **materialize trong vòng 2 phút** sau planned time; 95% được **SMTP submitted trong vòng 5 phút** sau planned time.

Hai ngưỡng chỉ là **ví dụ minh họa**, không phải chuẩn cho mọi ứng dụng. Cần chọn theo giá trị thông báo, năng lực SMTP và thời gian retry được chấp nhận.

## 65. Metrics quan trọng cho Quartz

| Metric gợi ý | Đơn vị | Điều phản ánh |
| --- | --- | --- |
| `mail.schedule.active` | schedules | Số lịch đang active |
| `mail.schedule.misfires` | count | Số tình huống trigger misfire theo nguồn đo |
| `mail.schedule.job.failures` | count | Lỗi khi materialize occurrence |
| `mail.schedule.fire.lag` | seconds | Độ trễ planned vs actual start |
| `mail.schedule.materialize.duration` | milliseconds | Thời gian transaction tạo occurrence/outbox |
| `mail.schedule.occurrence.duplicates` | count | Những invocation trùng bị idempotency ngăn |
| `mail.outbox.pending` | notifications | Công việc chờ submit |
| `mail.outbox.oldest.age` | seconds | Tuổi yêu cầu chờ lâu nhất |
| `mail.smtp.submission.duration` | milliseconds | Thời gian sender thực hiện SMTP |
| `mail.smtp.submitted` | count | Attempts được quan sát submit thành công |
| `mail.smtp.unknown` | count | Attempts có outcome mơ hồ |

Đây là tên metric **do ứng dụng có thể định nghĩa**, không phải toàn bộ metric mặc định của Quartz/Spring. Nếu dùng Micrometer/Actuator cần kiểm tra phiên bản và cấu hình observation của từng component.

### Bảo vệ metrics labels

Cho phép một số labels hữu hạn:

- `schedule_type`: once/cron.
- `scheduler_backend`: quartz/external/db-poll.
- `result`: materialized/skipped/duplicate/error.
- `provider_route`: giá trị allowlist đã cấu hình.
- `message_class`: transactional/bulk.

Không đưa `recipientEmail`, subject, attachment filename, raw `scheduleId` của hàng triệu users hoặc token vào metric label. Cardinality cao gây áp lực cho monitoring và có nguy cơ lộ dữ liệu.

## 66. Logging và audit

Một log cấu trúc hợp lý:

```text
event=scheduled_mail_occurrence
scheduleId=S-416-001
occurrenceId=O-416-20261205
plannedAt=2026-12-05T02:00:00Z
actualStartAt=2026-12-05T02:00:03Z
policy=FIRE_IF_ELIGIBLE
materializationResult=CREATED
outboxCount=3
```

Đừng log:

- Full recipient To/Cc/Bcc.
- OTP, reset token, magic link.
- Raw `MimeMessage` hoặc attachment.
- SMTP password, cloud scheduler token.
- Toàn bộ `JobDataMap` nếu có dữ liệu không an toàn.

Audit cần trả lời:

1. Ai tạo/sửa/hủy schedule?
2. Quy tắc/zone/version khi materialize là gì?
3. Occurrence nào bị skip do stale/cancel?
4. Ai hoặc cơ chế nào yêu cầu backfill?
5. Có bao nhiêu notification được materialize?
6. Attempt SMTP nào thuộc từng notification?

Không dùng nhật ký scheduler để suy ra remote delivery nếu chưa có provider feedback.

## 67. Dashboard theo ba tầng

### A. Scheduler health

```text
Quartz nodes / external scheduler heartbeat
  - active nodes
  - due triggers
  - misfires and fire lag
  - job execution failures
  - DB latency / lock contention
```

### B. Occurrence/outbox health

```text
Business schedule materialization
  - expected vs created occurrences
  - duplicate prevented
  - canceled/stale skipped
  - outbox pending and age
  - dispatch throughput
```

### C. Mail transport health

```text
SMTP workers
  - submission success/failure/UNKNOWN
  - retries and backoff
  - provider throttling
  - remote delivery events (when available)
```

Nếu dashboard chỉ hiển thị “Quartz Job SUCCESS”, người vận hành có thể bỏ sót việc outbox chưa được worker xử lý hoặc SMTP provider đang từ chối mọi email.

## 68. Alerts nên đánh theo sự cố thực

Ví dụ:

| Điều kiện | Ý nghĩa cần điều tra |
| --- | --- |
| Không có scheduler heartbeat | Scheduler có thể down |
| Fire lag p95 tăng | DB locks, thiếu worker, cluster state |
| Misfire burst tăng | Downtime/overload hoặc chính sách threshold |
| Outbox pending age tăng | Mail workers/SMTP throttling |
| Materialization failure liên tục | DB/schema/data/business validation |
| Duplicate insert attempts tăng mạnh | Trigger retry/recovery/misconfiguration |
| UNKNOWN SMTP attempts tăng | Network interruptions, timeouts |
| Recipient suppression tăng | Nguồn danh sách hoặc provider feedback |

Không tự động restart scheduler liên tục vì một cron job thất bại do recipient sai dữ liệu. Phải phân biệt **hạ tầng scheduling** với **lỗi nội dung nghiệp vụ** và **lỗi SMTP**.

## 69. Runbook khi lịch không chạy

**Bước 1 — Xác minh schedule state.**

- Schedule có đang `ACTIVE` không?
- Đã bị hủy/paused hay hết hiệu lực?
- Quy tắc cron/zone có hợp lệ?
- Trigger còn trong Quartz JobStore không?

**Bước 2 — Xem planned fire time.**

- `nextFireTime` có đúng theo lịch mong đợi?
- Có ảnh hưởng DST hay timezone default?
- Có misfire và policy bỏ qua firing?
- Có chỉnh lịch gần đây không?

**Bước 3 — Kiểm tra scheduler runtime.**

- Instance có start không?
- JDBC connection và Quartz tables có sẵn không?
- Cluster nodes có instance ID duy nhất và chung config không?
- Quartz thread pool có bận lâu do job?
- Database lock/latency có tăng?

**Bước 4 — Kiểm tra materialization.**

- Occurrence đã được insert chưa?
- Có bị dedupe do key trùng không?
- Schedule active/eligible khi job chạy không?
- Outbox có bản ghi không?

**Bước 5 — Kiểm tra mail worker.**

- Outbox có được claim không?
- Có lỗi template, attachment hoặc recipient policy?
- SMTP đã submit chưa?
- Có unknown outcome hoặc provider throttling?

**Bước 6 — Quyết định backfill.**

- Có được phép gửi bù không?
- Occurrence đã quá hạn hay không?
- Có chặn duplicate bằng unique key?
- Backfill bao nhiêu một batch và qua route nào?
- Có đủ quota và audit?

Tránh “sửa nhanh” bằng cách tạo trigger mới rồi cho gửi ngay khi chưa biết occurrence/outbox có tồn tại; có thể tạo email trùng.

## 70. Runbook khi email gửi trùng

Khi một khách hàng báo nhận hai bản của cùng thông báo:

1. Tìm `notificationId`, không chỉ so Subject.
2. Xem có hai **business occurrences** hay chỉ một occurrence nhưng hai attempts.
3. Nếu có hai occurrences: kiểm tra schedule key, version, misfire/backfill và unique constraint.
4. Nếu chỉ một occurrence: kiểm tra outbox claim, lease timeout, broker redelivery.
5. Xem SMTP failure stage, đặc biệt mất phản hồi sau DATA.
6. Kiểm tra failover giữa providers có gửi lại attempt `UNKNOWN` không.
7. Kiểm tra retry advice/worker có hai owners không.
8. Nếu provider có delivered events, dùng chúng như bằng chứng bổ sung, không giả định event count bằng số email thật hiển thị.
9. Đánh giá biện pháp ngăn resend trong future policy.

Đừng sửa bằng cách xóa tất cả retry. Một số lỗi tạm thời cần retry; vấn đề là **retry đúng đối tượng và đúng trạng thái**.

## 71. Runbook khi Quartz job mất sau deploy

Các nguyên nhân phổ biến:

- Đang dùng RAMJobStore, không phải JDBC persistence.
- Production startup đã chạy schema reset.
- Trỏ sang database/schema/tablePrefix khác sau deploy.
- Bootstrap code xóa và đăng ký lại jobs theo cấu hình mặc định.
- Cluster configuration/instanceName thay đổi.
- Job/trigger identity thay đổi khi đổi tên bean/class hoặc tenant ID.
- Migration chưa được áp dụng đúng.

Cách điều tra:

1. Kiểm tra JobStore được scheduler thực sự sử dụng.
2. Kiểm tra QRTZ tables có job/trigger records dự kiến không.
3. Kiểm tra migration logs và JDBC URL.
4. Kiểm tra schedule nghiệp vụ có còn trong source of truth không.
5. Chạy registrar/reconciliation có idempotency để đồng bộ lại trigger.

Không reset toàn bộ Quartz tables để “chạy lại từ đầu” nếu chúng chứa lịch của người dùng.

## 72. Cân nhắc multi-tenant và quyền truy cập

Khi nhiều tenants cùng dùng một scheduler:

- Mỗi schedule phải có owner/tenant scope.
- API sửa/hủy chỉ thao tác lên schedule được phép.
- Idempotency key phải không va chạm giữa tenants.
- JobKey/group nên có quy ước naming có giới hạn.
- Database queries/worker claim phải tuân thủ data isolation.
- Có quota số schedules và tần suất fire mỗi tenant.
- Có rate limit email theo tenant/provider.
- Không để một tenant tạo cron mỗi giây gây starve các tenant khác.
- Không nhúng tenant secrets vào JobDataMap.

Với worker xử lý multi-tenant, cần kiểm soát tenant context **tại thời điểm claim và load dữ liệu**, không tin một header do caller cung cấp nếu chưa được xác thực.

### Quota và fairness

Một tenant tạo 100.000 triggers cùng 09:00 có thể chiếm nhiều scheduler threads và làm trễ lịch của tenant khác. Giới hạn lịch và chia batch theo tenant/priority giúp hệ thống công bằng hơn. Quartz thread pool size chỉ là một yếu tố; outbox pacing và SMTP quota cũng cần được thiết kế.

## 73. Bảo mật của Quartz JobStore

JDBC JobStore có thể lưu JobDataMap và schedule metadata, vốn có khả năng chứa dữ liệu nghiệp vụ.

Khuyến nghị:

- Chỉ đưa opaque IDs và scalar data cần thiết vào `JobDataMap`.
- Dùng database user có quyền tối thiểu cho Quartz tables.
- Không dùng chung credentials DB production không cần thiết.
- Bật encryption at rest và backup protection theo chính sách.
- Không chia sẻ Quartz tables giữa các nhóm không tin cậy.
- Giới hạn quyền đọc schedule và correlation identifiers.
- Đảm bảo những migration Quartz có review vì có thể ảnh hưởng toàn bộ lịch.
- Không in secrets hay raw job data vào lỗi scheduler.

Nếu nhiều ứng dụng cùng dùng cluster tables, cần một mô hình ownership rõ ràng; mọi node có quyền cập nhật trigger state đều có thể tác động đến lịch của cluster.

## 74. Chi phí vận hành của Quartz và scheduler ngoài

| Yếu tố | Quartz JDBC trong ứng dụng | Scheduler ngoài |
| --- | --- | --- |
| Quản lý lịch | Ứng dụng chủ động quản lý DB/Quartz | Một phần do nền tảng scheduler quản lý |
| Hạ tầng database | Cần Quartz schema, backup, migration | Có thể không cần DB Quartz, nhưng vẫn cần business store |
| Cluster/failover | Cấu hình và vận hành Quartz nodes | Phụ thuộc SLO/contract của nền tảng |
| Lịch động mỗi user | Hỗ trợ, cần kiểm soát scale | Phụ thuộc quota/API schedule |
| Lịch đơn giản định kỳ | Được | Thường thuận tiện |
| Cron/timezone/misfire | Tính năng Quartz và business policy | Phụ thuộc dịch vụ, cần xác minh |
| Trigger delivery | Trong process/app cluster | HTTP, queue hoặc batch invocation |
| Security | DB permissions, app auth | IAM/signature/network policy |
| Side effect SMTP exactly-once | Không tự bảo đảm | Cũng không tự bảo đảm |
| Lock-in | Quartz APIs/schema | Cloud/provider platform API |
| Observability | Ứng dụng tự tích hợp metrics | Có nền tảng log/metrics; vẫn cần application outcomes |

Đừng chỉ so sánh chi phí một lượt trigger. Tổng chi phí còn gồm DB storage, vận hành, monitoring, backup, quota API, sự cố và độ khó của reconciliation.

## 75. Decision guide cho ba tình huống

### Tình huống A: một triệu thông báo one-shot có due_at

Nếu database đã lưu mọi `notification.due_at`, một due scanner + durable outbox thường trực tiếp và dễ scaling hơn việc tạo một Quartz JobDetail cho từng notification, tùy workload thực tế. Quartz vẫn có thể quản lý một job tick/trigger chung.

### Tình huống B: mỗi tổ chức có lịch gửi báo cáo tuần theo timezone riêng

Quartz JDBC JobStore với `CronTrigger` riêng cho từng schedule có thể phù hợp, nhất là khi cần dynamic pause/resume, cron calendar và cluster. Cần validation timezone/DST, idempotent occurrence và giới hạn schedules.

### Tình huống C: chuỗi email nhiều bước phụ thuộc trạng thái hợp đồng

Một workflow engine hoặc outbox state machine có timers có thể phù hợp hơn một cron trigger đơn lẻ, vì việc hủy/chờ/điều kiện là phần chính của business process.

Đây là các định hướng thiết kế, không phải kết luận hiệu năng khi chưa biết số schedules, tần suất, database và SLA của hệ thống.

## 76. Đăng ký lịch từ API: validate trước khi ghi

Một API tạo schedule thường nhận:

```json
{
  "scheduleType": "CRON",
  "cronExpression": "0 0 9 ? * MON-FRI",
  "zoneId": "Asia/Ho_Chi_Minh",
  "templateKey": "weekly-summary",
  "recipientGroupId": "group-demo-01"
}
```

Payload trên là **ví dụ hợp đồng nghiệp vụ**, không phải cấu hình có sẵn của Quartz. Trước khi lưu:

1. Xác thực user và quyền trên `recipientGroupId`.
2. Kiểm tra `scheduleType` được hỗ trợ.
3. Parse cron theo cú pháp Quartz, không dùng regex tự chế để xác minh đầy đủ.
4. Validate `ZoneId.of(...)` và policy DST.
5. Tính trước một số `nextFireTimes` để phát hiện lịch không hợp lệ hoặc quá dày.
6. Kiểm tra quota số schedules, tần suất và rate limit tenant.
7. Kiểm tra template tồn tại, được phép dùng và có version policy.
8. Xác định lịch one-shot trong quá khứ có bị từ chối không.
9. Thiết lập optimistic version và idempotency key của API create.
10. Lưu audit và lên kế hoạch đăng ký Quartz sau commit hoặc bằng một registrar retryable.

### Cron hợp cú pháp nhưng không hợp nghiệp vụ

Một cron “mỗi giây” có thể hợp cú pháp Quartz nhưng vượt quota SMTP hoặc mục đích “báo cáo tuần”. Do đó phải có **validation về tần suất**, không chỉ `CronExpression.isValidExpression(...)`.

Ví dụ:

```java
import org.quartz.CronExpression;

String cron = "0 0 9 ? * MON-FRI";
if (!CronExpression.isValidExpression(cron)) {
    throw new IllegalArgumentException(
            "Cron expression is invalid"
    );
}

ZoneId zoneId = ZoneId.of(requestedZoneId);
```

Validation về “lịch quá dày” có thể tính những lần fire kế tiếp trong một khoảng quan sát, giới hạn số events dự kiến và reject theo policy. Không cố suy tần suất chính xác bằng cách đếm số dấu `*`.

## 77. Không để đăng ký Quartz và business DB lệch lâu dài

Một tình huống:

```text
Application saves mail_schedule ACTIVE
     |
     v
Quartz scheduleJob(...) fails due to DB outage
     |
     v
Business DB says ACTIVE, but no Quartz trigger
```

Nếu hai stores không chia sẻ một transaction được bảo đảm, cần cơ chế đồng bộ:

- `mail_schedule.registration_status`: `PENDING/REGISTERED/ERROR`.
- Worker registrar chạy idempotently.
- So sánh schedule version/trigger key.
- Reconcile những lịch active thiếu trigger.
- Alert nếu registration lag vượt SLA.
- Không xóa schedule business chỉ vì Quartz tạm lỗi nếu user đã được thông báo nó sẽ được tiếp nhận sau.

Ngược lại, trigger có thể đã được tạo nhưng business commit thất bại. Job khi fire phải kiểm tra schedule business tồn tại và active; một reconciliation khác có thể xóa orphan triggers sau khi có đủ bằng chứng.

**Source of truth phải được định nghĩa rõ:** nếu lịch được chỉnh trong UI của ứng dụng, business DB thường nên là nguồn chính; Quartz JobStore là runtime execution projection được đồng bộ.

## 78. Không biến Quartz Job thành một transaction khổng lồ

Một job làm tất cả:

```text
Load 50,000 recipients
Render 50,000 PDFs
Send 50,000 emails
Commit one giant transaction
```

sẽ gặp nhiều vấn đề:

- Quartz worker thread bận hàng chục phút/giờ.
- Database locks/connection bị giữ lâu.
- Timeout hoặc restart làm khó recovery.
- Không biết recipient nào đã submit.
- Một lỗi ở recipient thứ 49.999 có thể khiến logic retry gửi lại cả batch.
- Heap/disk băng thông có thể bị quá tải.

Tốt hơn:

```text
Quartz fire
   |
   v
Create campaign occurrence
   |
   v
Materialize recipient notifications in bounded chunks
   |
   v
Outbox workers with rate/backpressure
   |
   v
Persist outcomes individually
```

Chia batch không đồng nghĩa mất khả năng tổng hợp kết quả: có thể lưu `campaignOccurrenceId` để báo cáo số created/submitted/failed/unknown và audit từng recipient.

## 79. Một checklist kỹ thuật trước khi go-live với Quartz JDBC

### A. Scheduler persistence

- [ ] Quartz đang dùng JDBC JobStore ở môi trường cần lịch bền vững.
- [ ] Quartz tables được tạo bằng migration đúng database/version.
- [ ] Không tự động drop/recreate schema ở mỗi production startup.
- [ ] Cluster nodes dùng chung cấu hình, DB và instance IDs duy nhất.
- [ ] DB connection pool, backup và monitoring được thiết lập.
- [ ] Đồng hồ các nodes được đồng bộ.
- [ ] JobDataMap chỉ chứa định danh và scalar dữ liệu phù hợp.
- [ ] Registrar có idempotency và xử lý create/update/cancel.

### B. Trigger semantics

- [ ] One-shot và recurring schedules được phân biệt.
- [ ] Cron expression đã validate theo cú pháp Quartz.
- [ ] Time zone IANA được lưu và kiểm tra.
- [ ] Có policy DST cho local time không tồn tại/lặp lại.
- [ ] Có policy misfire rõ với từng loại thông báo.
- [ ] Có quy tắc xử lý occurrences stale.
- [ ] Có reconciliation/backfill khi cần đủ business periods.
- [ ] Không chọn “FireNow cho tất cả” nếu gây mail storm.

### C. Business correctness

- [ ] Schedule có owner/tenant authorization.
- [ ] Có schedule version và audit update/cancel.
- [ ] Có occurrence key đại diện đúng logical event.
- [ ] Database có unique constraints chống duplicate.
- [ ] Occurrence và outbox được commit atomically.
- [ ] Job luôn kiểm tra state/eligibility trước materialize.
- [ ] Data/template/attachment có snapshot/version policy.
- [ ] Không gửi SMTP trong transaction tạo occurrence.

### D. Mail reliability

- [ ] Notification và attempts có IDs độc lập.
- [ ] Outbox worker có claim/lease và retry/backoff.
- [ ] Timeout/partial SMTP results được phân loại.
- [ ] Không retry mù `UNKNOWN`.
- [ ] Có quota/rate limit/backpressure.
- [ ] Có SMTP test server và provider feedback khi cần.
- [ ] Không coi “Quartz Job SUCCESS” là “email delivered”.

## 80. Checklist nếu dùng scheduler ngoài

### Khả năng của nền tảng

- [ ] Đã xác minh độ bền schedule, retry, jitter và timing window.
- [ ] Đã hiểu giới hạn số lịch và invocation quota.
- [ ] Có timezone/DST semantics hoặc business planner phù hợp.
- [ ] Có cơ chế update/cancel với contract rõ.
- [ ] Có quy trình backup hoặc recovery cấu hình lịch.

### An toàn endpoint hoặc queue

- [ ] Xác thực nguồn trigger bằng IAM/token/mTLS/signature phù hợp.
- [ ] Giới hạn request size, rate và allowed schedule scope.
- [ ] Không tin tùy ý recipient/SMTP config từ request ngoài.
- [ ] Chỉ trả success sau durable acceptance.
- [ ] Có idempotency khi scheduler retry callback.
- [ ] Queue consumer có acknowledgment, retry và dead-letter policy.

### Worker và dữ liệu

- [ ] Có database due scan theo `due_at <= now()` hoặc business occurrence planner.
- [ ] Có claim/unique constraints chống nhiều workers xử lý trùng.
- [ ] Có xử lý missed ticks và backlog.
- [ ] Có outbox state/retry/UNKNOWN handling.
- [ ] Có metrics tách trigger acceptance và SMTP submission.

## 81. Bài tập 1 — Restart làm mất lịch

Ứng dụng đăng ký lịch gửi báo cáo thứ Hai 09:00 bằng Quartz, nhưng sau redeploy lịch biến mất.

**Câu hỏi:** Bước kiểm tra đầu tiên là gì?

**Gợi ý:** xác nhận JobStore đang dùng. Nếu là RAMJobStore, lịch chỉ nằm trong memory. Nếu là JDBC, kiểm tra URL/schema/tablePrefix, migration, auto schema initialization và bootstrap code.

## 82. Bài tập 2 — Hai instances gửi cùng email

Hai pod có cùng `@Scheduled` method, mỗi pod gọi `JavaMailSender.send(...)`.

**Câu hỏi:** Vì sao gửi trùng?

**Gợi ý:** mỗi instance có một scheduler riêng theo code; annotation không tự tạo cluster claim. Có thể dùng Quartz JDBC cluster hoặc shared DB due scanner; vẫn phải có unique occurrence/outbox.

## 83. Bài tập 3 — Job bị fire hai lần sau failover

Node A bắt đầu materialize, node bị restart, node B chạy lại logic.

**Gợi ý:** `@DisallowConcurrentExecution` không phải idempotency. Đặt unique constraint trên logical occurrence và ghi occurrence/outbox trong một transaction.

## 84. Bài tập 4 — Lỡ ba ngày báo cáo

Cron mỗi ngày đã bị down ba ngày, Quartz chỉ fire once sau recovery.

**Câu hỏi:** Làm sao tạo đủ ba bản báo cáo?

**Gợi ý:** reconciliation dựa trên business calendar và logical period keys, không giả định misfire tự phát lại từng historical trigger.

## 85. Bài tập 5 — Hủy lịch ngay trước giờ gửi

User bấm cancel lúc Quartz đã acquire trigger.

**Gợi ý:** unschedule chỉ là thao tác tầng trigger. Business schedule state và database locking quyết định có materialize không; notification đã được SMTP submit thì không thể thu hồi bằng Quartz.

## 86. Bài tập 6 — Một cron ở Europe/Berlin chạy sai vào DST

Khách yêu cầu email lúc 02:30 hằng ngày; một ngày chuyển DST không có 02:30.

**Gợi ý:** định nghĩa chính sách cho giờ không tồn tại/lặp lại, kiểm thử đúng ngày chuyển DST, không lấy UTC timestamp cộng 24 giờ rồi nghĩ luôn giữ local time.

## 87. Bài tập 7 — External tick bị gửi hai lần

Cloud scheduler không nhận acknowledgment, retry HTTP callback. Scanner chạy hai lần.

**Gợi ý:** durable idempotency ở database occurrence/outbox, không dùng chỉ một biến `boolean processed` trong JVM. Nếu hai scans chạy đồng thời, cần claim/unique constraint trong database.

## 88. Bài tập 8 — SMTP timeout sau DATA

Lịch chạy đúng, worker gửi xong MIME bytes nhưng không nhận final `250`.

**Gợi ý:** scheduler không nên tự fire lại chỉ vì JavaMailSender báo lỗi. SMTP outcome có thể là `UNKNOWN`; cần attempt ledger, reconciliation và retry policy ngăn duplicate.

## 89. Bài tập 9 — Một tenant tạo hàng nghìn schedules mỗi giây

Quartz DB tăng nhanh, jobs fire chồng nhau và mail workers quá tải.

**Gợi ý:** quota theo tenant, rate limiting khi tạo schedules, minimum interval, bounded materialization, ưu tiên notification, worker backpressure và giám sát database/thread pool.

## 90. Bài tập 10 — File attachment đã bị xóa trước giờ gửi

Một lịch hẹn ba tháng sau chứa đường dẫn tới file tạm chỉ sống 24 giờ.

**Gợi ý:** không lưu file temp short-lived làm dependency của schedule dài hạn. Dùng immutable storage reference/version, kiểm tra còn quyền truy cập và có policy khi file không còn.

## 91. Các nguyên tắc then chốt

1. **Quartz JDBC hoặc scheduler ngoài giữ lịch bền vững; SMTP send là một side effect độc lập.**
2. **Quartz JobDetail `storeDurably()` không thay thế JDBC JobStore.**
3. **Chọn trigger theo semantics nghiệp vụ:** one-shot `Instant`, cron theo local time/zone hoặc business period.
4. **Misfire policy là quyết định sản phẩm**, không có một lựa chọn đúng cho mọi email.
5. **Quartz cluster giảm rủi ro nhiều nodes cùng acquire trigger**, nhưng không tự tạo exactly-once email.
6. **Logical occurrence key + database unique constraint** là lớp chống materialize trùng quan trọng.
7. **Tạo occurrence và outbox atomically**, không commit nửa chừng rồi coi là đã xử lý.
8. **Scheduler job nên ngắn**, để outbox worker chịu trách nhiệm SMTP.
9. **Đừng ngủ trong Quartz worker để retry SMTP**; dùng lịch retry được lưu ở database.
10. **Khi hủy hoặc sửa lịch, cần state/version và reconciliation**, không chỉ gọi Quartz API.
11. **External scheduler invocation cũng có thể muộn/lặp/mất**, cần secure ingress và idempotency.
12. **Database due scanner có thể đơn giản hơn Quartz** khi chỉ có nhiều one-shot notifications với `due_at`.
13. **DST/timezone phải là một phần của contract**, không dựa vào JVM default.
14. **SMTP `SUBMITTED` khác `DELIVERED`**, và timeout sau DATA có thể tạo `UNKNOWN`.
15. **Observability phải tách giờ đến hạn, giờ materialize, giờ submit và remote delivery**.

## 92. Tài liệu tham khảo

- **Quartz Scheduler:** https://www.quartz-scheduler.org/documentation/
- **Spring Boot — Quartz Scheduler:** https://docs.spring.io/spring-boot/reference/io/quartz.html
- **Spring Framework — Task Execution and Scheduling:** https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- **Spring Framework — Email Integration:** https://docs.spring.io/spring-framework/reference/integration/email.html

Khi triển khai, cần đối chiếu tài liệu đúng **Quartz/Spring Boot version** của dự án, đặc biệt về JDBC JobStore integration, JobFactory, cluster properties, misfire behavior và schema migration. Ví dụ code trong bài dùng repository/service do ứng dụng định nghĩa để minh họa kiến trúc; những components ấy không tự có chỉ vì thêm starter Quartz.

## 93. Kết luận

Để lập lịch gửi email bền vững trong Spring Framework Mail, hãy **tách quyết định *khi nào cần làm việc* khỏi việc *thực sự submit email***. Quartz với JDBC JobStore phù hợp khi ứng dụng cần lịch động, `CronTrigger`, `SimpleTrigger`, misfire management và chạy đa node. Scheduler ngoài phù hợp khi hạ tầng có sẵn dịch vụ lịch có thể gọi HTTP/queue hoặc chạy worker định kỳ. Với nhiều notification one-shot đã có `due_at`, một database scanner có claim/lease và unique constraints đôi khi đơn giản hơn cả hai.

Thành phần quyết định độ tin cậy lâu dài không chỉ là scheduler mà là **mô hình dữ liệu nghiệp vụ**: schedule có owner, version và timezone; occurrence có logical key; outbox được ghi atomically; mail worker có attempt state, retry/backoff, backpressure và xử lý kết quả SMTP mơ hồ. Hủy, sửa, misfire hay phục hồi sau downtime đều cần reconciliation và kiểm thử. Không sử dụng một lần job thực thi thành công để kết luận email đã tới Inbox.

Khi tổ chức đúng các ranh giới **schedule → occurrence → outbox notification → SMTP attempt → provider delivery feedback**, ứng dụng có thể bảo toàn lịch qua restart, scale an toàn, phát hiện và xử lý lịch bị lỡ, giảm nguy cơ gửi trùng và cung cấp bằng chứng rõ ràng cho người vận hành về mỗi giai đoạn của vòng đời email.
