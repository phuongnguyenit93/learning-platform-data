# Time zone của schedule trong Spring Batch

## 1. Vì sao múi giờ là một phần của lịch chạy batch?

Trong hệ thống batch, yêu cầu “chạy lúc 02:15 mỗi ngày” còn thiếu một thông tin quyết định: **02:15 ở múi giờ nào?** Nếu máy phát triển đặt giờ Việt Nam, máy production chạy UTC, còn dữ liệu nghiệp vụ thuộc thị trường New York, cùng một cron expression có thể kích hoạt tại ba thời điểm tuyệt đối khác nhau.

Ví dụ: một job đối soát đơn hàng phải chạy **02:15 sáng theo giờ Việt Nam** và xử lý giao dịch của **ngày nghiệp vụ hôm trước**. Khi quy định này được thực hiện rõ ràng:

- 02:15 ngày 16/11/2026 tại `Asia/Ho_Chi_Minh` là 19:15 UTC ngày 15/11/2026.
- Tham số nghiệp vụ của job là `businessDate=2026-11-15`.
- Dù JVM/host/container đặt múi giờ UTC, lần chạy vẫn được lên lịch theo giờ Việt Nam.
- Khi cần chạy bù, ta vẫn có thể xác định chính xác ngày dữ liệu cần xử lý.

Nếu không xác định múi giờ một cách tường minh, các lỗi thường gặp là job chạy lệch giờ sau deploy, ngày báo cáo lệch một ngày, job bị gọi hai lần trong thời điểm chuyển giờ mùa hè, hoặc dữ liệu bị bỏ sót khi dịch chuyển lịch.

Bài học thuộc *Spring Batch Core Processing → Scheduling* và tập trung vào **Time zone của schedule**: cách hiểu, cấu hình, kiểm thử và vận hành lịch chạy của một Spring Batch job.

**Mục tiêu học tập**

1. Phân biệt thời điểm tuyệt đối, giờ địa phương, offset và múi giờ vùng.
2. Cấu hình `@Scheduled(cron = ..., zone = ...)` với Spring Framework để chạy Spring Batch job theo giờ nghiệp vụ.
3. Tạo `JobParameters` xác định đúng ngày dữ liệu, giữ tính idempotent và restart.
4. Hiểu giờ bị thiếu/giờ lặp do daylight saving time (DST).
5. Thiết kế kiểm thử chủ động bằng `java.time`, `Clock` và `CronExpression`.
6. Nhận biết giới hạn của scheduler trong ứng dụng, tình huống chạy đa instance và nhu cầu chạy bù.

Các ví dụ chính dùng **Java 17+, Spring Boot 3.x, Spring Framework 6.x và Spring Batch 5.x**. API của Spring Framework có thể được dùng ở Spring Batch 6.x khi chọn bộ phiên bản Spring Boot/Spring Framework tương thích.

---

## 2. Spring Batch và scheduler là hai trách nhiệm khác nhau

**Spring Batch** cung cấp các thành phần quản lý thực thi: `Job`, `Step`, `JobLauncher`, `JobRepository`, `JobParameters`, checkpoint, retry và restart. Bản thân một `Job` không tự hiểu yêu cầu “02:15 mỗi ngày theo giờ Việt Nam”.

**Scheduler** quyết định lúc nào gửi yêu cầu chạy job. Scheduler có thể là:

- `@Scheduled` cùng `@EnableScheduling` của Spring Framework.
- Quartz Scheduler với cron trigger và time zone xác định.
- Kubernetes CronJob với `spec.timeZone` (ở các phiên bản Kubernetes hỗ trợ).
- Apache Airflow, một enterprise scheduler hoặc hệ thống điều phối chạy batch.
- Một ứng dụng riêng phát sự kiện và gọi job qua API.

Luồng trách nhiệm:

```text
                  Chính sách nghiệp vụ
           "02:15 Asia/Ho_Chi_Minh mỗi ngày"
                            │
                            ▼
                      Scheduler
                (tính thời điểm kích hoạt)
                            │
                            ▼
                JobLauncher / JobOperator
             (truyền Job + JobParameters)
                            │
                            ▼
                   Spring Batch Job
              ┌─────────────┴─────────────┐
              ▼                           ▼
          JobRepository            Reader / Processor /
        lưu metadata                Writer, transaction
              │                           │
              └─────────────┬─────────────┘
                            ▼
               Trạng thái và dữ liệu đầu ra
```

Một lịch chạy đúng cần cả hai tầng:

- **Khi nào kích hoạt:** cron, time zone, lịch nghỉ, giờ chạy và cơ chế bù lần chạy lỡ.
- **Chạy cho dữ liệu nào:** business date, kỳ kế toán, vùng dữ liệu, tham số nhận dạng `JobInstance`.

Việc đến đúng thời điểm chưa bảo đảm job xử lý đúng ngày dữ liệu. Một job chạy lúc 00:05 có thể cần xử lý ngày trước đó; một job chạy lúc 22:00 có thể chuẩn bị dữ liệu cho ngày hôm sau. Quy tắc này phải được biểu diễn trong `JobParameters` hoặc trong một lớp chính sách nghiệp vụ tách biệt.

---

## 3. Các kiểu thời gian Java cần nắm

Java `java.time` có nhiều kiểu biểu diễn thời gian. Chọn nhầm kiểu thường gây lỗi schedule.

| Kiểu | Biểu diễn | Ví dụ | Nên dùng ở đâu? |
|---|---|---|---|
| `Instant` | Một thời điểm tuyệt đối trên trục UTC | `2026-11-15T19:15:00Z` | Log thời điểm, lưu sự kiện kích hoạt, so sánh thời gian |
| `LocalDate` | Ngày lịch không kèm giờ hoặc múi giờ | `2026-11-15` | Ngày nghiệp vụ, partition key, tên báo cáo |
| `LocalTime` | Giờ trong ngày không kèm ngày hoặc múi giờ | `02:15` | Giờ nghiệp vụ được yêu cầu |
| `LocalDateTime` | Ngày và giờ đồng hồ, **không xác định một instant duy nhất** | `2026-11-16T02:15` | Giao diện nhập lịch trước khi áp `ZoneId` |
| `ZoneOffset` | Độ lệch cố định so với UTC | `+07:00` | Biểu diễn offset tại một thời điểm |
| `ZoneId` | Quy tắc múi giờ của một vùng | `Asia/Ho_Chi_Minh` | Chính sách lịch chạy theo địa điểm |
| `ZonedDateTime` | Local date/time kết hợp múi giờ và offset được giải quyết | `2026-11-16T02:15+07:00[Asia/Ho_Chi_Minh]` | Tính lịch, hiển thị giờ theo thị trường |
| `OffsetDateTime` | Ngày, giờ và offset, không mang toàn bộ quy tắc vùng | `2026-11-16T02:15+07:00` | Giao tiếp hệ thống khi hợp đồng dùng offset |
| `Clock` | Nguồn cung cấp thời gian có thể thay thế trong test | `Clock.systemUTC()` | Tách logic khỏi đồng hồ thực của máy |

### 3.1. ZoneId khác ZoneOffset

`ZoneOffset.of("+07:00")` biểu diễn một offset cố định. `ZoneId.of("Asia/Ho_Chi_Minh")` biểu diễn khu vực với các quy tắc thời gian trong cơ sở dữ liệu IANA time zone (tzdb).

Với các thị trường có daylight saving time, offset có thể thay đổi theo mùa:

- `America/New_York` có thể là UTC−05:00 hoặc UTC−04:00 tùy thời điểm.
- `Europe/Berlin` có thể là UTC+01:00 hoặc UTC+02:00.
- `Asia/Ho_Chi_Minh` hiện thường là UTC+07:00 và không chuyển DST theo lịch hiện hành.

Nếu nghiệp vụ yêu cầu “09:00 theo giờ New York”, hãy dùng `ZoneId.of("America/New_York")`. Một offset cố định `-05:00` sẽ khiến giờ local mùa hè lệch một giờ.

### 3.2. Một instant có thể thuộc hai ngày lịch khác nhau

```java
Instant instant = Instant.parse("2026-11-15T19:15:00Z");

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime inVietnam = instant.atZone(vietnam);
ZonedDateTime inUtc = instant.atZone(ZoneOffset.UTC);

System.out.println(inVietnam);
// 2026-11-16T02:15+07:00[Asia/Ho_Chi_Minh]

System.out.println(inUtc);
// 2026-11-15T19:15Z

System.out.println(inVietnam.toLocalDate());
// 2026-11-16

System.out.println(inUtc.toLocalDate());
// 2026-11-15
```

**Đây là một thời điểm duy nhất**, nhưng ngày lịch theo hai múi giờ khác nhau. Gọi `LocalDate.now()` mà không chỉ định `ZoneId` có thể tạo sai `businessDate` trên server dùng timezone khác máy phát triển.

### 3.3. LocalDateTime không đủ để xác định lúc chạy

`LocalDateTime.of(2026, 11, 16, 2, 15)` chỉ nói “ngày 16 lúc 02:15”. Phải kết hợp một múi giờ mới chuyển thành `Instant`:

```java
LocalDateTime local = LocalDateTime.of(2026, 11, 16, 2, 15);
ZonedDateTime scheduled = local.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

Instant actualInstant = scheduled.toInstant();
// 2026-11-15T19:15:00Z
```

Ở vùng có DST, một số `LocalDateTime` không tồn tại hoặc tồn tại hai lần. Vấn đề này được phân tích ở phần riêng bên dưới.

---

## 4. Cron expression và múi giờ trong @Scheduled

Spring Framework hỗ trợ lịch cron qua annotation `@Scheduled`.

```java
@Scheduled(cron = "0 15 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runDailyBatch() {
    // Gửi yêu cầu chạy job.
}
```

Trong cú pháp Spring, cron thường gồm **6 trường**, có thêm giây ở đầu:

```text
┌──────────── giây (0)
│ ┌────────── phút (15)
│ │ ┌──────── giờ (2)
│ │ │ ┌────── ngày trong tháng (*)
│ │ │ │ ┌──── tháng (*)
│ │ │ │ │ ┌── thứ trong tuần (*)
│ │ │ │ │ │
0 15 2 * * *
```

Một số ví dụ:

| Cron Spring | Ý nghĩa | Múi giờ cần áp |
|---|---|---|
| `0 15 2 * * *` | 02:15 mỗi ngày | `Asia/Ho_Chi_Minh` nếu batch cho Việt Nam |
| `0 0 9 * * MON-FRI` | 09:00 thứ Hai–thứ Sáu | Múi giờ của thị trường |
| `0 30 23 L * *` | 23:30 ngày cuối cùng của tháng | Múi giờ kỳ kế toán |
| `0 0 0 1 * *` | 00:00 ngày đầu mỗi tháng | Múi giờ dùng để xác định tháng |
| `0 0 12 * * SUN` | 12:00 Chủ nhật | Múi giờ địa phương của nghiệp vụ |

Lưu ý: Spring sử dụng sáu trường cron, trong khi biểu thức cron UNIX truyền thống thường chỉ có năm trường. Không copy biểu thức từ `crontab` sang `@Scheduled` mà không kiểm tra số trường. Quartz có quy ước thêm và cách diễn giải day-of-week riêng; cũng không nên sao chép máy móc giữa các scheduler.

### 4.1. Ý nghĩa của zone

Theo Javadoc Spring Framework, `zone` là múi giờ dùng để diễn giải **cron expression**. Khi bỏ trống, scheduler sẽ sử dụng múi giờ mặc định của nó.

```java
// Đúng giờ 02:15 tại Việt Nam, bất kể JVM đặt UTC hay New York:
@Scheduled(cron = "0 15 2 * * *", zone = "Asia/Ho_Chi_Minh")

// Phụ thuộc vào múi giờ mặc định của scheduler:
@Scheduled(cron = "0 15 2 * * *")
```

Đặt cấu hình explicit là cách ổn định hơn trong container, CI và nhiều môi trường deploy. Không phụ thuộc vào múi giờ hệ điều hành hoặc tham số `-Duser.timezone` để biểu diễn một quy tắc nghiệp vụ.

### 4.2. Zone áp dụng cho cron, không phải mọi kiểu lịch

`@Scheduled` còn có `fixedRate` và `fixedDelay`:

```java
@Scheduled(fixedRate = 60_000)  // khoảng 60 giây giữa những lần bắt đầu
public void poll() {}

@Scheduled(fixedDelay = 60_000) // đợi 60 giây sau lần chạy trước hoàn tất
public void retryPoll() {}
```

Những kiểu này dựa trên **khoảng thời gian**, không diễn đạt “mỗi ngày vào 02:15 ở một múi giờ”. Đặc biệt:

- `fixedRate = 86_400_000` không đồng nghĩa “cứ mỗi ngày lúc 02:15 theo giờ địa phương” ở nơi có DST.
- Một ngày lịch có thể kéo dài 23 hoặc 25 giờ khi chuyển DST.
- Nếu yêu cầu là giờ địa phương theo lịch, hãy dùng cron cùng `zone` hoặc scheduler hỗ trợ calendar trigger.
- Nếu yêu cầu là cứ 10 phút polling, sử dụng fixed rate/delay thường hợp lý hơn.

### 4.3. Cấu hình cron từ application.yml

Thay vì cố định lịch trong source code, có thể dùng placeholder:

```yaml
app:
  batch:
    schedule:
      cron: "0 15 2 * * *"
      zone: "Asia/Ho_Chi_Minh"

spring:
  batch:
    job:
      enabled: false
```

Sau đó:

```java
@Scheduled(
    cron = "${app.batch.schedule.cron}",
    zone = "${app.batch.schedule.zone}"
)
public void submitDailyJob() {
    // ...
}
```

`spring.batch.job.enabled=false` tránh để Spring Boot tự khởi chạy batch job vào lúc ứng dụng khởi động, nhờ vậy bạn chủ động chỉ khởi chạy qua schedule hoặc cơ chế điều phối đã thiết kế. Giá trị `"-"` cho cron được Spring hỗ trợ như một trigger bị vô hiệu hóa; hữu ích khi tắt lịch theo môi trường:

```yaml
app:
  batch:
    schedule:
      cron: "-"
      zone: "Asia/Ho_Chi_Minh"
```

Việc vô hiệu lịch **không xóa job definition** và cũng không ngăn các lần chạy thủ công qua API điều khiển khác.

---

## 5. Ví dụ thực hành: Spring Batch chạy theo giờ Việt Nam

### 5.1. Yêu cầu

Hệ thống thương mại cần một job `dailyImportJob`:

- Chạy lúc **02:15 mỗi ngày theo `Asia/Ho_Chi_Minh`**.
- Xử lý đơn hàng của **ngày lịch trước ngày chạy** ở Việt Nam.
- Ghi thời điểm yêu cầu chạy dưới dạng UTC `Instant` để quan sát.
- Cùng một ngày nghiệp vụ chỉ tương ứng với một `JobInstance`.
- Có thể nhận diện yêu cầu chạy trùng nếu schedule bị gọi lặp.
- Logic ngày nghiệp vụ phải kiểm thử được mà không cần đợi đồng hồ thật.

Giả sử `dailyImportJob` là một bean `Job` đã được cấu hình trong ứng dụng Spring Batch, và class ứng dụng có cơ chế quét component thông thường của Spring Boot.

### 5.2. Dependency

Ví dụ Gradle với Spring Boot 3.x và Spring Batch 5.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    // Dùng với JobRepository JDBC nếu ứng dụng chọn H2 cho demo/test.
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Dự án sản xuất nên dùng database metadata được vận hành bền vững, không dựa vào H2 in-memory để bảo đảm lịch sử restart sau khi tắt ứng dụng.

### 5.3. Bean Clock và ZoneId

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.ZoneId;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class ScheduleConfiguration {

    @Bean
    Clock batchClock() {
        return Clock.systemUTC();
    }

    @Bean
    ZoneId businessZone(
            @Value("${app.batch.schedule.zone}") String zoneName) {
        return ZoneId.of(zoneName);
    }
}
```

Có hai chủ ý thiết kế:

1. `Clock.systemUTC()` cho ta thời điểm tuyệt đối, độc lập timezone mặc định của máy.
2. `ZoneId.of(zoneName)` kiểm tra cú pháp mã vùng ngay lúc nạp bean; một zone không hợp lệ sẽ báo lỗi sớm. Tránh im lặng rơi về GMT nếu dùng một số API `TimeZone` theo chuỗi không hợp lệ.

Đồng thời, chính giá trị cấu hình `app.batch.schedule.zone` cũng được tham chiếu bởi `@Scheduled`. Như vậy trigger và quy tắc tính ngày dữ liệu dùng cùng một múi giờ.

### 5.4. Component lên lịch chạy job

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

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
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyImportScheduler {

    private static final Logger log =
            LoggerFactory.getLogger(DailyImportScheduler.class);

    private final JobLauncher jobLauncher;
    private final Job dailyImportJob;
    private final Clock clock;
    private final ZoneId businessZone;

    public DailyImportScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailyImportJob") Job dailyImportJob,
            Clock batchClock,
            ZoneId businessZone) {
        this.jobLauncher = jobLauncher;
        this.dailyImportJob = dailyImportJob;
        this.clock = batchClock;
        this.businessZone = businessZone;
    }

    @Scheduled(
        cron = "${app.batch.schedule.cron}",
        zone = "${app.batch.schedule.zone}"
    )
    public void launch() {
        Instant requestedAt = clock.instant();
        LocalDate businessDate =
                businessDateFor(requestedAt, businessZone);

        JobParameters parameters = new JobParametersBuilder()
                // Identifying: một JobInstance cho mỗi businessDate.
                .addString("businessDate", businessDate.toString(), true)
                // Chỉ phục vụ quan sát; không thay đổi JobInstance.
                .addString("scheduleZone", businessZone.getId(), false)
                .addString("requestedAtUtc", requestedAt.toString(), false)
                .toJobParameters();

        try {
            JobExecution execution =
                    jobLauncher.run(dailyImportJob, parameters);

            log.info("Submitted dailyImportJob: businessDate={}, "
                    + "jobExecutionId={}, status={}",
                    businessDate, execution.getId(),
                    execution.getStatus());

        } catch (JobExecutionAlreadyRunningException ex) {
            log.info("dailyImportJob already running for {}",
                    businessDate);

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info("dailyImportJob already completed for {}",
                    businessDate);

        } catch (JobRestartException | JobParametersInvalidException ex) {
            log.error("Cannot start dailyImportJob for {}",
                    businessDate, ex);
            throw new IllegalStateException(
                    "Unable to launch dailyImportJob", ex);
        }
    }

    static LocalDate businessDateFor(
            Instant requestedAt, ZoneId businessZone) {
        // Chính sách ví dụ: mỗi đêm xử lý dữ liệu của hôm trước.
        return requestedAt.atZone(businessZone)
                .toLocalDate()
                .minusDays(1);
    }
}
```

**Phân tích:**

- `@Scheduled(cron, zone)` chỉ điều khiển **thời điểm gọi** phương thức `launch()`.
- `requestedAt` được lấy dưới dạng `Instant` từ `Clock`, thuận tiện cho log, đo trễ và unit test.
- `businessDateFor(...)` chuyển instant sang ngày lịch ở **múi giờ nghiệp vụ**, sau đó lùi một ngày theo chính sách.
- `businessDate` được đánh dấu `identifying=true`, vì trong bài toán này mỗi ngày cần một `JobInstance` riêng.
- `requestedAtUtc` là tham số non-identifying. Nếu đưa thời điểm hiện tại vào identifying parameters, mỗi lần scheduler gọi lại sẽ tạo một `JobInstance` mới, đánh mất khả năng phát hiện chạy trùng theo ngày.
- Khi một instance đã `COMPLETED`, Spring Batch không cho chạy lại cùng instance như một lượt mới. Trong ví dụ, trường hợp đó được log là yêu cầu trùng đã hoàn tất.
- Khi cùng instance đang chạy, một yêu cầu mới thường nhận `JobExecutionAlreadyRunningException` theo repository transaction/isolation được cấu hình.
- Nếu instance trước đó `FAILED` và job restartable, một lời gọi với cùng identifying parameters có thể là một lần **restart**, không phải tự động được bỏ qua. Muốn restart có người duyệt, cần tách chính sách đó ra khỏi lịch tự động.
- `JobLauncher.run(...)` có thể chạy đồng bộ hoặc bất đồng bộ theo cấu hình launcher. Trạng thái nhận ngay sau lời gọi chưa chắc là trạng thái hoàn tất. Muốn biết kết quả cuối cùng phải đọc `JobExecution`/repository sau khi job kết thúc.

Ví dụ chọn `businessDate = ngày hôm trước` là **quy tắc nghiệp vụ**, không phải hành vi mặc định của Spring Batch. Với job dữ liệu hiện tại, thay phần tính toán cho phù hợp.

### 5.5. Ngày chạy và ngày dữ liệu khác nhau

Tại thời điểm:

```text
UTC instant:      2026-11-15T19:15:00Z
Asia/Ho_Chi_Minh: 2026-11-16 02:15 (+07:00)
Schedule fires:   2026-11-16 theo giờ Việt Nam
businessDate:     2026-11-15
```

Nếu máy chạy ở UTC và code dùng `LocalDate.now().minusDays(1)`, tại cùng instant đó có thể nhận `businessDate=2026-11-14`. Đây là lỗi lệch ngày dù cron trigger vẫn chạy đúng. Vì thế **timezone của trigger và timezone xác định ngày dữ liệu cần được thiết kế cùng nhau**.

### 5.6. Truyền businessDate vào ItemReader/StepScope

Trong job, reader có thể nhận tham số bằng late binding:

```java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['businessDate']}") String date) {

    String inputFile = "/data/orders-" + date + ".csv";

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "amount")
            .targetType(Order.class)
            .build();
}
```

Đoạn này minh họa việc dùng date làm khóa chọn resource; nó giả định dự án đã khai báo `Order` và các import Spring Batch tương ứng. Trong production cần xử lý file không tồn tại, encoding, header, retry và xác thực dữ liệu theo hợp đồng.

Nếu input path được truyền trực tiếp qua `JobParameters` thay vì suy ra từ ngày, vẫn nên log rõ **ngày nghiệp vụ** tương ứng để tránh nhầm lẫn giữa ngày kích hoạt và ngày dữ liệu.

---

## 6. DST: giờ biến mất và giờ lặp lại

DST (daylight saving time, chuyển giờ mùa hè) là nguyên nhân khiến không thể đồng nhất “một ngày lịch” với “24 giờ liên tiếp” ở mọi múi giờ.

### 6.1. Spring-forward: một giờ địa phương không tồn tại

Tại `America/New_York`, ngày **08/03/2026** chuyển sang DST. Đồng hồ địa phương nhảy từ khoảng `01:59:59` lên `03:00:00`.

Do đó, local time `2026-03-08 02:30` **không tồn tại** ở vùng đó:

```text
America/New_York, 08/03/2026

01:59:59 (UTC−05:00)
       │
       ▼  chuyển DST
03:00:00 (UTC−04:00)

02:30:00 không xuất hiện
```

Cron `0 30 2 * * *` có thể không có một lần kích hoạt đúng “02:30 địa phương” vào ngày này; hành vi bỏ qua hoặc bù phụ thuộc scheduler, phiên bản và chính sách misfire.

Nếu nghiệp vụ yêu cầu **chính xác một lần mỗi ngày** bất kể DST, cần viết rõ policy: bỏ qua ngày đó, chuyển sang 03:00, chuyển sang giờ khác, hay chạy bù. Không thể giả định cron tự bảo đảm “mỗi ngày đúng một lần”.

### 6.2. Fall-back: một giờ địa phương xuất hiện hai lần

Tại `America/New_York`, ngày **01/11/2026**, đồng hồ chuyển từ DST về giờ chuẩn. Khoảng `01:00–01:59` xuất hiện hai lần với hai offset:

```text
America/New_York, 01/11/2026

01:30 (UTC−04:00)  ← lần thứ nhất
...
01:59:59 (UTC−04:00)
       │
       ▼  chuyển về giờ chuẩn
01:00 (UTC−05:00)
...
01:30 (UTC−05:00)  ← lần thứ hai
```

Một cron chạy `01:30` theo giờ địa phương phải có chính sách xử lý trường hợp ambiguous này. Một số trigger/scheduler có thể coi hai occurrence là hai instant khác nhau; kết quả thực tế còn tùy logic “next firing”, trigger type và phiên bản. Không mặc định mọi scheduler sẽ gọi đúng hai lần hoặc đúng một lần nếu chưa test.

### 6.3. Kiểm tra giờ local bằng ZoneRules

Java cho phép xác nhận một local time có 0, 1 hay 2 offset hợp lệ:

```java
ZoneId newYork = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
List<ZoneOffset> gapOffsets =
        newYork.getRules().getValidOffsets(gap);
// gapOffsets.size() == 0: thời điểm local không tồn tại.

LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
List<ZoneOffset> overlapOffsets =
        newYork.getRules().getValidOffsets(overlap);
// overlapOffsets.size() == 2: thời điểm local tồn tại hai lần.
```

Import:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
```

Các giá trị này phụ thuộc quy tắc tzdb phù hợp với mốc năm đã chọn. Khi yêu cầu lịch chạy tương lai, cơ sở dữ liệu time zone của JDK/container cần được cập nhật khi luật múi giờ thay đổi.

### 6.4. Quy tắc nào phù hợp với business batch?

| Yêu cầu nghiệp vụ | Chính sách nên cân nhắc |
|---|---|
| “Xử lý đúng một lần mỗi ngày nghiệp vụ” | Dùng `businessDate` làm khóa duy nhất, lưu lịch sử, reconcile những ngày chưa xử lý |
| “Chạy lúc 02:30 địa phương” | Định nghĩa hành vi với ngày có DST gap; có thể chuyển sang giờ an toàn hơn |
| “Chạy đúng 24 giờ một lần” | Dùng interval/instant phù hợp, không đồng nhất với một giờ địa phương cố định |
| “Xử lý mọi kỳ giờ, kể cả giờ lặp” | Dùng khóa gồm business period và offset/instant, không chỉ `LocalDateTime` |
| “Không được chạy song song” | Cần cơ chế điều phối/lock và chính sách khi job kéo dài qua lần trigger tiếp theo |
| “Báo cáo ngày theo New York” | Tạo business date từ `America/New_York`, không từ timezone của server |

Nếu chọn chạy vào `04:00` tại vùng có DST vì giờ đó thường không nằm trong khoảng đổi giờ, rủi ro gap/overlap giảm; tuy nhiên vẫn cần kiểm tra quy tắc khu vực và chính sách nghiệp vụ, không coi đó là giải pháp chung cho mọi quốc gia.

---

## 7. Kịch bản lệch ngày do timezone

### 7.1. Server UTC, lịch Việt Nam

Một ứng dụng đặt `@Scheduled(cron = "0 15 2 * * *")` không có `zone`. Khi chạy ở máy phát triển với timezone Việt Nam, nó kích hoạt 02:15 Việt Nam. Khi triển khai container mặc định UTC, cron có thể kích hoạt 02:15 UTC, tức 09:15 Việt Nam.

Nếu yêu cầu là 02:15 Việt Nam, hãy dùng:

```java
@Scheduled(cron = "0 15 2 * * *", zone = "Asia/Ho_Chi_Minh")
```

Đừng “chữa” bằng cách cộng/trừ 7 giờ thủ công trong cron ở mọi môi trường. Cách đó khó quản lý khi có nhiều thị trường hoặc thay đổi chính sách timezone.

### 7.2. “Ngày hôm qua” phụ thuộc múi giờ nào?

Giả sử `Instant` là `2026-11-15T19:15:00Z`:

| Phương pháp | Ngày trước đó thu được |
|---|---|
| `LocalDate.now(ZoneOffset.UTC).minusDays(1)` | `2026-11-14` |
| `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh")).minusDays(1)` | `2026-11-15` |
| `Instant.parse(...).atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate().minusDays(1)` | `2026-11-15` |

Dòng cuối phù hợp nhất để test vì không cần đồng hồ thực. Hai dòng trên chỉ cho kết quả minh họa nếu được gọi **chính xác ở instant đã giả định**.

### 7.3. Kỳ kế toán không nhất thiết bằng LocalDate

Một số ngành có cut-off 17:00, ngày giao dịch bắt đầu từ 18:00 hoặc kỳ bán hàng qua đêm. Trong trường hợp đó, hàm:

```java
instant.atZone(zone).toLocalDate()
```

chỉ xác định **ngày lịch**, chưa chắc là **ngày nghiệp vụ**. Có thể cần một `BusinessCalendar` hoặc `BusinessDateResolver` theo cửa sổ nghiệp vụ, lịch nghỉ, vùng khách hàng và cut-off riêng.

Ví dụ, nếu ngày nghiệp vụ chuyển tại 06:00 thay vì 00:00, hàm chính sách có thể là:

```java
static LocalDate businessDateAtSixAm(
        Instant instant, ZoneId zone) {
    ZonedDateTime local = instant.atZone(zone);
    return local.toLocalTime().isBefore(LocalTime.of(6, 0))
            ? local.toLocalDate().minusDays(1)
            : local.toLocalDate();
}
```

Quy tắc này khác với chính sách “02:15 xử lý ngày hôm trước” ở ví dụ trước; chỉ áp dụng khi hợp đồng nghiệp vụ quy định cut-off 06:00.

---

## 8. JobParameters, JobInstance và xử lý chạy trùng

Time zone không chỉ quyết định **khi nào** job chạy mà còn tác động đến **định danh lần xử lý**.

### 8.1. Identifying parameters

Trong Spring Batch, một `JobInstance` được xác định bởi tên `Job` và tập identifying `JobParameters`. Với job đối soát mỗi ngày:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedAtUtc",
                "2026-11-15T19:15:00Z", false)
        .toJobParameters();
```

Tham số `businessDate` nhận dạng instance; thời điểm thực tế gọi job chỉ phục vụ audit.

Nếu code thay đổi thành:

```java
.addString("requestedAtUtc",
        Instant.now().toString(), true)
```

thì mỗi lần gọi với instant khác nhau có thể tạo một instance mới. Việc chạy trùng cùng ngày sẽ không còn bị nhận diện bởi khóa `businessDate` đơn giản.

### 8.2. Khi nào cần thêm zone/region vào khóa?

Nếu một job xử lý cho **nhiều thị trường**, business date `2026-11-15` ở Việt Nam và New York có thể chỉ đến hai bộ dữ liệu khác nhau. Khi đó khóa định danh nên bao gồm thị trường:

```java
new JobParametersBuilder()
        .addString("market", "VN", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("scheduleZone", "Asia/Ho_Chi_Minh", false)
        .toJobParameters();
```

Việc đưa `scheduleZone` vào identifying hay không phải quyết định theo hợp đồng nghiệp vụ. Nếu hai vùng khác nhau cùng xử lý một bộ dữ liệu, nên dùng business key ổn định (như `market`); đổi tên múi giờ cấu hình không nên vô tình tạo instance mới và xử lý dữ liệu lặp.

### 8.3. Job chạy kéo dài qua ngày hôm sau

Lịch kích hoạt job vào 02:15 mỗi ngày, nhưng job ngày đầu mất 28 giờ. Ngày tiếp theo, scheduler sẽ tiếp tục phát lời gọi theo lịch nếu không có chính sách chặn. Với identifying businessDate khác nhau, Spring Batch có thể tạo hai `JobInstance` khác nhau và cho phép chạy đồng thời.

Do đó, **khóa duy nhất theo ngày không tự cấm chạy song song giữa hai ngày nghiệp vụ**. Nếu không được phép xử lý chồng lấn, cần cơ chế khóa ở tầng điều phối, queue một worker, Quartz clustered scheduler hoặc giải pháp vận hành tương đương.

### 8.4. Restart và replay

Khi job ngày 15 thất bại và được restart ngày 17, phải truyền lại `businessDate=2026-11-15`. Không tính `LocalDate.now(zone).minusDays(1)` tại thời điểm restart, vì như vậy job có thể nhảy sang ngày 16 và tạo một `JobInstance` khác.

Thực hành tốt:

- Khi chạy tự động, xác định ngày nghiệp vụ cho **kỳ được lên lịch**.
- Lưu tham số identifying trong metadata của lần chạy.
- Khi restart, sử dụng lại định danh nghiệp vụ của instance thất bại.
- Khi backfill, truyền rõ từng ngày dữ liệu còn thiếu.
- Nếu một kỳ cần chạy lại từ đầu sau `COMPLETED`, phải có quy trình reprocess riêng được định nghĩa rõ thay vì tùy tiện đổi tham số để lách kiểm soát trùng.

---

## 9. Scheduled time, actual time và business time

Ba mốc thường bị gộp vào nhau:

| Mốc | Ý nghĩa | Lưu ở đâu? |
|---|---|---|
| `scheduledAt` | Thời điểm scheduler **dự kiến** gọi job | Cơ chế trigger/audit của scheduler |
| `requestedAt` hoặc `actualTriggerAt` | Thời điểm ứng dụng thực sự gửi yêu cầu | Log/metric hoặc non-identifying parameter |
| `businessDate` / `businessPeriod` | Kỳ dữ liệu mà job xử lý | Identifying JobParameters |

Ví dụ scheduler dự kiến 02:15 nhưng máy quá tải nên method chạy 02:17. Với job xử lý ngày hôm trước, cả hai có thể cùng ngày nghiệp vụ. Tuy nhiên, nếu job chạy sát nửa đêm hoặc bị trễ qua ngày hôm sau, tính business date từ `Instant.now()` lúc được chạy sẽ có thể **lệch kỳ**.

Nếu yêu cầu của hệ thống là xử lý **đúng mọi occurrence** của lịch (bao gồm occurrence bị trễ hoặc chạy bù), cần một scheduler có lưu planned fire time hoặc một hàng đợi các kỳ dữ liệu phải xử lý. Chọn `businessDate` từ kỳ được gán, không suy ngược mù quáng từ thời gian xử lý thật.

Mẫu mô hình tốt cho hệ thống lớn:

```text
Schedule occurrence:
  scheduleId      = dailyImport-VN
  plannedFireAt   = 2026-11-15T19:15:00Z
  zone            = Asia/Ho_Chi_Minh
  businessDate    = 2026-11-15

Request at:
  actualRequestAt = 2026-11-15T19:17:12Z

Batch identity:
  jobName         = dailyImportJob
  identifying     = businessDate=2026-11-15
```

Mô hình này cho phép giám sát độ trễ trigger, xác định kỳ dữ liệu và đối soát các lần chạy còn thiếu.

---

## 10. Scheduler dừng, misfire và chạy bù

### 10.1. @Scheduled không phải lịch bền vững

Với `@Scheduled` trong tiến trình Spring, khi ứng dụng tắt hoặc restart, những lần kích hoạt xảy ra trong lúc downtime thường **không được lưu để tự động phát lại**. Nếu máy tắt từ 02:00 tới 03:00, lịch 02:15 có thể bị lỡ.

Một lần deploy lại lúc 03:00 không tự chứng minh job cho ngày hôm trước đã chạy. Do đó, nếu yêu cầu là “không bao giờ thiếu kỳ nghiệp vụ”, cần có thêm cơ chế:

1. Lưu định danh những kỳ cần xử lý, ví dụ mỗi businessDate.
2. Truy vấn lịch sử qua `JobExplorer`/repository hoặc sổ kiểm soát nghiệp vụ.
3. Xác định kỳ chưa `COMPLETED`.
4. Gửi job chạy bù có tham số identifying tương ứng.
5. Đối soát output của từng kỳ.

### 10.2. Xử lý missed executions theo chính sách

| Chính sách | Phù hợp khi | Hệ quả cần cân nhắc |
|---|---|---|
| Bỏ qua lần trigger bị lỡ | Dữ liệu stale không còn giá trị, ví dụ poll cache | Có thể không xử lý một kỳ |
| Chạy một lần khi hệ thống hồi phục | Yêu cầu lấy trạng thái gần nhất | Có thể không bù đủ những kỳ đã lỡ |
| Chạy tất cả kỳ thiếu | Đối soát, thanh toán, báo cáo, nhập dữ liệu theo ngày | Cần queue, businessDate ổn định và giới hạn concurrency |
| Gộp các kỳ thiếu thành một job | Công việc hỗ trợ xử lý dồn | Phải chứng minh kết quả tương đương xử lý từng kỳ |
| Đưa vào hàng chờ người vận hành phê duyệt | Công việc tác động tài chính hoặc dữ liệu khó đảo ngược | Phải có quy trình kiểm tra và restart rõ ràng |

Quartz cung cấp cơ chế trigger và misfire handling phong phú hơn `@Scheduled` cơ bản. Tuy nhiên chính sách default của một Quartz trigger không tự động trở thành đáp án đúng cho mọi nghiệp vụ; cần cấu hình và test hành vi cụ thể.

### 10.3. CronTrigger lenient và fixed execution

Ở các phiên bản Spring Framework có các factory method tương ứng, `CronTrigger` phân biệt:

- **Lenient execution:** lập lịch dựa trên lần hoàn tất trước, có thể bỏ qua một số firing khi công việc chạy lâu.
- **Fixed execution:** lập lịch dựa trên thời điểm dự kiến, có thể tạo lần chạy bù cho firing bị trễ.

Ví dụ tên API của Spring Framework 6.1.3 trở lên:

```java
CronTrigger lenient =
        CronTrigger.forLenientExecution("0 15 2 * * *");

CronTrigger fixed =
        CronTrigger.forFixedExecution("0 15 2 * * *");
```

Hai factory trên minh họa chính sách lập lịch của `CronTrigger` trong các phiên bản tương ứng; khi dùng múi giờ riêng, cần cấu hình `TaskScheduler`/clock hoặc trigger cho đúng zone, và kiểm tra API phiên bản. Chúng **không thay thế** lưu lịch bền vững sau process crash hoặc hệ thống phân phối nhiều node. Đừng coi fixed execution là chính sách tự động “mỗi ngày đúng một job nghiệp vụ” khi chưa có idempotency ở tầng Spring Batch.

---

## 11. Ứng dụng chạy nhiều instance: lịch có thể bị kích hoạt trùng

Giả sử deploy ứng dụng với 3 replica và mỗi replica đều có `@EnableScheduling` cùng phương thức `@Scheduled`:

```text
             02:15 tại Asia/Ho_Chi_Minh
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
        Replica A    Replica B    Replica C
            │            │            │
            └────────────┼────────────┘
                         ▼
                  JobRepository
```

Mỗi replica có thể cố gọi `JobLauncher.run(...)`. `JobRepository` giúp bảo vệ việc tạo execution cho cùng `JobInstance` theo giao dịch và mức isolation phù hợp, nhưng không nên biến bảo vệ này thành cơ chế điều phối lịch duy nhất:

- Các replica vẫn có thể phát nhiều yêu cầu.
- Nếu identifying parameters khác nhau, Spring Batch có thể xem chúng là các instance khác nhau và cùng chạy.
- Side effect ngoài transaction batch (HTTP, file, email, message) không tự được bảo đảm exactly-once.
- Node chết sau khi bắt đầu side effect có thể khiến restart lặp lại một phần thao tác.

Các giải pháp phù hợp gồm một scheduler chủ, distributed lock đáng tin cậy, Quartz clustering với persistent job store hoặc scheduler bên ngoài phát một yêu cầu đến service batch. Dù chọn giải pháp nào, job vẫn cần **idempotency theo business key** và cơ chế recovery.

### Khi nào cần ngăn chạy đồng thời?

Một số công việc có thể xử lý các businessDate khác nhau song song, ví dụ import file mỗi ngày độc lập. Một số khác bắt buộc tuần tự, ví dụ cập nhật số dư tổng hợp có phụ thuộc kỳ trước.

Vì vậy phải trả lời riêng:

- Có chặn **trùng cùng businessDate** không?
- Có chặn **hai businessDate khác nhau chạy chồng lấn** không?
- Có giới hạn số batch cùng chạy trên một database không?
- Khi một job vượt quá thời lượng lịch, scheduler sẽ queue, skip hay báo lỗi?

Múi giờ là phần xác định occurrence, còn concurrency là chính sách điều phối và bảo toàn dữ liệu.

---

## 12. Quartz: time zone của CronTrigger

Khi ứng dụng cần trigger bền vững, chạy cluster hoặc misfire policy chi tiết, Quartz thường được dùng cùng Spring Batch.

Ví dụ thiết lập time zone cho Quartz cron schedule:

```java
import java.util.TimeZone;

import org.quartz.CronScheduleBuilder;

CronScheduleBuilder schedule = CronScheduleBuilder
        .cronSchedule("0 15 2 * * ?")
        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
```

Ở ví dụ Quartz, `?` thể hiện “không chỉ định giá trị” cho một trường day-of-month/day-of-week. Đây là cú pháp Quartz, có những khác biệt với Spring cron. Đừng sao chép một expression giữa hai thư viện mà không kiểm tra.

Nếu job cần timezone từ config:

```java
ZoneId zoneId = ZoneId.of(configuredZone); // validate trước
TimeZone quartzZone = TimeZone.getTimeZone(zoneId);

CronScheduleBuilder schedule = CronScheduleBuilder
        .cronSchedule(configuredCron)
        .inTimeZone(quartzZone);
```

Tầng tích hợp Quartz → Spring Batch cần quyết định cách ánh xạ **planned fire time**, **trigger identity** và **businessDate** thành `JobParameters`. Nếu ghi non-identifying `requestedAt` thay planned time, phải bảo đảm quy trình chạy bù không lệch kỳ. Quartz clustering/persistent store cũng cần cấu hình database và lock đúng; chỉ tạo `CronScheduleBuilder` chưa giải quyết được những vấn đề đó.

---

## 13. Múi giờ trong Kubernetes CronJob và scheduler ngoài

Spring Batch có thể chạy mỗi lần như một process/job riêng dưới sự điều phối của Kubernetes CronJob thay vì duy trì `@Scheduled` trong ứng dụng.

Ví dụ minh họa Kubernetes CronJob với time zone rõ ràng:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-import
spec:
  schedule: "15 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: daily-import
              image: example/daily-import:1.0
```

**Điểm cần phân biệt:**

- Kubernetes cron `"15 2 * * *"` thường là **5 trường** (phút, giờ, ngày tháng, tháng, thứ), khác Spring `@Scheduled` có 6 trường.
- `timeZone` chỉ đạo cách hiểu lịch kích hoạt của Kubernetes CronJob ở các version hỗ trợ trường này.
- `concurrencyPolicy: Forbid` điều tiết concurrency **của CronJob Kubernetes đó**, không thay thế khóa dữ liệu hoặc idempotency trong Spring Batch.
- Một missed schedule có thể bị xử lý theo quy tắc của Kubernetes, bao gồm `startingDeadlineSeconds` và lịch sử controller; cần kiểm tra semantics của cluster đang dùng.
- Container cần nhận đúng **ngày dữ liệu được lên lịch**. Không coi ngày hiện tại trong pod luôn bằng businessDate mong đợi nếu pod bị tạo/chạy trễ.

Khi điều phối ở bên ngoài, thường nên bỏ hoặc vô hiệu hóa `@Scheduled` nội bộ để tránh hai scheduler cùng kích hoạt một job.

---

## 14. Kiểm thử timezone của schedule mà không đợi đến 02:15

Một bộ test tốt kiểm tra logic thời gian bằng dữ liệu cố định, sau đó kiểm thử tích hợp riêng luồng Spring Batch nếu cần.

### 14.1. Kiểm tra cron tiếp theo bằng CronExpression

Spring Framework cung cấp `org.springframework.scheduling.support.CronExpression`. Ta có thể cho cron tính occurrence tiếp theo trong một `ZonedDateTime` cụ thể.

```java
package com.example.batch.schedule;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.ZoneId;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

class CronZoneTest {

    @Test
    void nextFireIsTwoFifteenInVietnam() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        CronExpression cron =
                CronExpression.parse("0 15 2 * * *");

        ZonedDateTime reference = ZonedDateTime.of(
                2026, 11, 15, 23, 0, 0, 0, zone);

        ZonedDateTime next = cron.next(reference);

        assertEquals(ZonedDateTime.of(
                2026, 11, 16, 2, 15, 0, 0, zone), next);
    }
}
```

`CronExpression.next(...)` sử dụng đối tượng temporal được truyền vào để tính thời điểm tiếp theo. Khi truyền `ZonedDateTime` trong múi giờ Việt Nam, phép tính mang đúng bối cảnh múi giờ. Đây là **unit test biểu thức cron**, chưa chứng minh toàn bộ scheduler runtime sẽ xử lý missed trigger theo chính sách nào.

### 14.2. Kiểm tra mapping Instant → businessDate

```java
package com.example.batch.schedule;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

class BusinessDatePolicyTest {

    @Test
    void selectsPreviousDateInBusinessZone() {
        Instant fireAt =
                Instant.parse("2026-11-15T19:15:00Z");
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        LocalDate businessDate =
                DailyImportScheduler.businessDateFor(fireAt, zone);

        assertEquals(LocalDate.of(2026, 11, 15), businessDate);
    }

    @Test
    void instantMayBelongToDifferentLocalDates() {
        Instant sameInstant =
                Instant.parse("2026-11-15T19:15:00Z");

        assertEquals(LocalDate.of(2026, 11, 16),
                sameInstant.atZone(
                        ZoneId.of("Asia/Ho_Chi_Minh"))
                        .toLocalDate());

        assertEquals(LocalDate.of(2026, 11, 15),
                sameInstant.atZone(ZoneId.of("UTC"))
                        .toLocalDate());
    }
}
```

Phương thức `DailyImportScheduler.businessDateFor` trong ví dụ ở phần 5 có phạm vi package-private; test trên nằm cùng package. Có thể tách chính sách này thành bean riêng nếu nhiều job cùng sử dụng.

### 14.3. Kiểm tra DST gap và overlap

```java
package com.example.batch.schedule;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDateTime;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

class DaylightSavingTest {

    private final ZoneId zone =
            ZoneId.of("America/New_York");

    @Test
    void springForwardHasNoTwoThirtyAm() {
        LocalDateTime local =
                LocalDateTime.of(2026, 3, 8, 2, 30);

        assertEquals(0,
                zone.getRules().getValidOffsets(local).size());
    }

    @Test
    void fallBackHasTwoOneThirtyAmInstants() {
        LocalDateTime local =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        assertEquals(2,
                zone.getRules().getValidOffsets(local).size());
    }
}
```

Các test này chứng minh đặc tính của timezone và mốc thời gian. Nếu ứng dụng sử dụng Quartz hoặc một loại `CronTrigger` cụ thể, cần có thêm integration test để xác định **chính sách thực thi thực tế** của scheduler đó trong ngày chuyển DST.

### 14.4. Kiểm thử với Clock.fixed

Khi service dùng `Clock` từ dependency injection, có thể thay thế đồng hồ thời gian thực bằng một giá trị cố định:

```java
Clock fakeClock = Clock.fixed(
        Instant.parse("2026-11-15T19:15:00Z"),
        ZoneOffset.UTC);

Instant requestedAt = fakeClock.instant();

LocalDate businessDate =
        DailyImportScheduler.businessDateFor(
                requestedAt,
                ZoneId.of("Asia/Ho_Chi_Minh"));

assertEquals(LocalDate.of(2026, 11, 15), businessDate);
```

Ưu điểm: test không phụ thuộc giờ máy CI, không phải `Thread.sleep`, không flake ở sát nửa đêm. Có thể dùng Mockito để mock `JobLauncher` và assert `JobParameters` chứa đúng `businessDate`, đồng thời xác minh `requestedAtUtc` là non-identifying.

### 14.5. Tình huống test nên bao phủ

| Tình huống | Điều cần xác nhận |
|---|---|
| Server chạy UTC, nghiệp vụ giờ Việt Nam | Occurrence và businessDate vẫn theo `Asia/Ho_Chi_Minh` |
| Giờ sát 00:00 UTC nhưng đã sang ngày mới ở Việt Nam | Không lấy nhầm ngày từ JVM default zone |
| Ngày đổi tháng/đổi năm | Lùi ngày bằng `LocalDate.minusDays(1)` cho kết quả đúng |
| DST gap | Chính sách với giờ không tồn tại được định nghĩa rõ |
| DST overlap | Chính sách chống xử lý trùng kỳ dữ liệu được áp dụng |
| Cron config sai | Ứng dụng báo lỗi sớm thay vì chạy tại giờ bất ngờ |
| ZoneId config sai | Phát hiện cấu hình không hợp lệ khi khởi động |
| Chạy trùng cùng businessDate | Không tạo thêm instance đã `COMPLETED`; xử lý exception phù hợp |
| Chạy lại instance `FAILED` | Restart dùng cùng identifying businessDate |
| Scheduler lỡ một ngày do downtime | Cơ chế backfill có thể nhận diện và xử lý kỳ còn thiếu |
| Job kéo dài tới ngày hôm sau | Chính sách xử lý concurrency rõ ràng |
| Nhiều vùng nghiệp vụ | Mỗi vùng có định danh, time zone và calendar thích hợp |

---

## 15. Thiết kế quan sát và chẩn đoán lỗi timezone

Khi vận hành, nên ghi các trường thời gian với ý nghĩa rõ ràng:

```text
jobName= dailyImportJob
scheduleZone= Asia/Ho_Chi_Minh
cron= 0 15 2 * * *
businessDate= 2026-11-15
requestedAtUtc= 2026-11-15T19:15:00Z
observedLocal= 2026-11-16T02:15+07:00[Asia/Ho_Chi_Minh]
jobExecutionId= 123456
batchStatus= STARTED
```

Nếu scheduler có planned fire time, lưu thêm `plannedFireAtUtc` và tính độ trễ:

```text
scheduleDelay = actualRequestAt - plannedFireAtUtc
```

Không nên chỉ log chuỗi như `"02:15:00"` hoặc `"2026-11-16 02:15"` mà không có timezone. Chúng thiếu thông tin để xác định instant khi điều tra hệ thống nhiều khu vực hoặc ngày chuyển DST.

### Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| Job chạy lệch 7 giờ khi deploy container | `@Scheduled` không có `zone`, mặc định scheduler thay đổi | Cấu hình `zone = "Asia/Ho_Chi_Minh"` rõ ràng |
| Job tạo file cho sai ngày | Tính `businessDate` bằng `LocalDate.now()` theo zone mặc định | Chuyển `Instant` sang `ZoneId` nghiệp vụ trước khi lấy ngày |
| Job không chạy vào một ngày DST | Local trigger time nằm trong DST gap | Định nghĩa chính sách và chọn giờ/trigger phù hợp |
| Job chạy trùng khi đổi DST | Local time overlap, scheduler/trigger tạo nhiều firing | Thiết kế business key và idempotency |
| Mỗi deploy tạo một instance mới dù cùng ngày | Dùng timestamp identifying parameter | Chỉ dùng các tham số nghiệp vụ ổn định làm identifying |
| Job không chạy bù sau khi máy tắt | `@Scheduled` không lưu missed firing bền vững | Reconciliation/backfill hoặc persistent scheduler |
| Ba replica cùng gọi job | Mỗi replica có scheduler riêng | Distributed coordination hoặc scheduler duy nhất |
| UI hiển thị lịch sử lệch giờ | Parse database timestamp thiếu quy ước timezone | Chuẩn hóa `Instant`/offset và format hiển thị theo user zone |
| Scheduler và job chọn hai múi giờ khác nhau | Trigger dùng zone A, `LocalDate.now()` dùng zone B | Một nguồn cấu hình zone dùng cho cả trigger và business policy |
| Không tìm thấy job khi restart | Tính lại businessDate từ thời điểm restart | Lưu và truyền lại identifying parameters gốc |

### Tách thời gian của DB và thời gian nghiệp vụ

Database metadata Spring Batch lưu các mốc như start/end/update time, nhưng kiểu cột và cách lưu/đọc theo hệ quản trị DB, JDBC driver và cấu hình framework. Không suy luận rằng một `LocalDateTime` lấy từ metadata đã có múi giờ UTC nếu hệ thống chưa xác nhận quy ước đó.

Khi ứng dụng tự lưu audit event, có thể chọn `Instant` hoặc timestamp-with-offset theo hợp đồng dữ liệu. Khi hiển thị, chuyển sang `ZoneId` của người vận hành hoặc thị trường, đồng thời giữ định danh instant cho việc đối soát.

### Cập nhật tzdb

IANA timezone rules có thể thay đổi theo quyết định của quốc gia. Đối với những lịch chạy nhiều năm hoặc thị trường thường thay đổi chính sách DST, cần cập nhật JDK/container tương ứng. Thay đổi tzdb có thể làm các occurrence tương lai thay đổi; nên kiểm tra lịch quan trọng sau khi nâng cấp runtime.

---

## 16. Khi nào nên chọn @Scheduled, Quartz hoặc scheduler ngoài?

| Lựa chọn | Điểm mạnh | Giới hạn cần thiết kế |
|---|---|---|
| Spring `@Scheduled(cron, zone)` | Đơn giản, ít dependency, đủ dùng cho job nội bộ nhỏ | Không có persistent missed schedule mặc định, nhiều replica có thể cùng kích hoạt |
| Quartz | Trigger, calendar, misfire policy, có thể dùng persistent store/cluster | Cần cấu hình vận hành, DB, mapping sang `JobParameters` |
| Kubernetes CronJob | Tách lịch khỏi tiến trình app, tích hợp quản lý pod/job | Cú pháp cron khác Spring, có quy tắc missed schedule và concurrency riêng |
| Orchestrator như Airflow | Workflow nhiều bước, lịch sử, backfill, dependency | Hạ tầng lớn hơn, phải nhất quán timezone và businessDate giữa orchestrator và Spring Batch |
| Scheduler doanh nghiệp | Quản lý nhiều hệ thống, SLA và lịch nghiệp vụ | Cần kiểm soát mapping tham số và khả năng quan sát end-to-end |

Tùy nhu cầu, một ứng dụng Spring Batch có thể khởi chạy từ REST API hoặc command line và giao toàn bộ scheduling cho hệ điều phối bên ngoài. Với thiết kế đó, job nên được xây dựng để **nhận ngày/kỳ dữ liệu từ tham số** và có thể chạy lại an toàn, không phụ thuộc thời gian hiện tại trong JVM.

---

## 17. Bài tập thực hành

### Bài 1 — Chuyển múi giờ

Cho `Instant.parse("2026-11-15T19:15:00Z")`. Viết chương trình in ra:

- Giờ UTC.
- Giờ tại `Asia/Ho_Chi_Minh`.
- Ngày lịch ở cả hai vùng.
- Ngày nghiệp vụ cần xử lý nếu policy là “ngày hôm trước theo giờ Việt Nam”.

Giải thích vì sao các ngày có thể khác nhau dù instant là một.

### Bài 2 — Job chạy theo múi giờ cấu hình

Đặt `app.batch.schedule.cron = "0 15 2 * * *"` và `app.batch.schedule.zone = "Asia/Ho_Chi_Minh"`. Viết bean dùng `@EnableScheduling` và `@Scheduled` để gọi một Spring Batch `Job` nhận `businessDate`. Kiểm tra bằng `CronExpression` thay vì chờ đến 02:15 thực tế.

### Bài 3 — Thử với New York

Chuyển zone thành `America/New_York` và schedule lúc `02:30`. Dùng `ZoneRules` chứng minh ngày 08/03/2026 thiếu `02:30`. Sau đó lập quy tắc nghiệp vụ sẽ làm gì ở ngày đó.

### Bài 4 — Chạy trùng

Giả lập scheduler gọi job hai lần với cùng `businessDate` nhưng `requestedAtUtc` khác nhau. So sánh kết quả khi `requestedAtUtc` là identifying và non-identifying parameter. Giải thích vì sao cách thứ hai thường phù hợp hơn cho job “mỗi ngày một kỳ”.

### Bài 5 — Chạy lại ngày cũ

Giả sử job ngày 15 thất bại, nhưng đến ngày 17 mới restart. Thiết kế lệnh gọi job để **vẫn xử lý businessDate=2026-11-15**. Không sử dụng `LocalDate.now(zone).minusDays(1)` cho yêu cầu restart.

### Bài 6 — Mất một occurrence

Một ứng dụng `@Scheduled` bị tắt từ 01:55 đến 02:40 vào ngày 16/11/2026. Hãy thiết kế bước đối soát xác định job cho ngày nghiệp vụ 15/11 đã có `JobExecution` hoàn tất hay chưa, và quy trình backfill nếu thiếu.

### Bài 7 — Triển khai hai replica

Deploy cùng ứng dụng `@Scheduled` trên hai pod. Xác định điều gì xảy ra nếu cả hai gọi `JobLauncher.run(...)` lúc 02:15; thiết kế một chính sách scheduler ownership và kiểm soát trùng theo business key.

---

## 18. Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskScheduler`, `CronTrigger`, `@EnableScheduling` và `@Scheduled`.
- [Spring Framework — Javadoc @Scheduled (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html): cú pháp cron 6 trường, thuộc tính `zone` và cron vô hiệu hóa bằng `"-"`.
- [Spring Framework — CronExpression](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronExpression.html): parse và tính occurrence kế tiếp với `ZonedDateTime`.
- [Spring Framework — CronTrigger](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html): cron trigger, lenient/fixed execution và scheduler clock.
- [Spring Batch — Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): quan hệ `Job`, `JobInstance`, `JobExecution`, `JobParameters`.
- [Spring Batch — Configuring a JobLauncher](https://docs.spring.io/spring-batch/reference/job/configuring-launcher.html): khởi chạy job.
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata, instance và giao dịch repository.
- [Java SE — ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): định danh vùng giờ và quy tắc múi giờ.
- [Java SE — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): gap/overlap và offsets hợp lệ.
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): `schedule`, `timeZone`, concurrency và missed schedules.

Múi giờ của schedule là **quy tắc xác định khi nào job được yêu cầu chạy**; còn ngày/kỳ dữ liệu mà job xử lý là **định danh nghiệp vụ** phải được tính và lưu tường minh. Thiết kế bền vững kết hợp `ZoneId`, `Instant`, `Clock`, `@Scheduled(zone)` hoặc scheduler tương đương, cùng `JobParameters` ổn định, cơ chế xử lý trùng và chạy bù. Khi đó việc triển khai lên máy UTC, đổi vùng kinh doanh, restart job hoặc đi qua ngày DST không còn khiến hệ thống âm thầm xử lý sai kỳ dữ liệu.
