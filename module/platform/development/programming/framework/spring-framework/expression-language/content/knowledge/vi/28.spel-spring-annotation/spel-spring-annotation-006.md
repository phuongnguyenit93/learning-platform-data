# SpEL trong @Scheduled và giá trị cấu hình

## 1. Tổng quan

Spring Framework cho phép khai báo lịch chạy cho một method bằng annotation `@Scheduled`. Giá trị lịch có thể được viết trực tiếp trong code hoặc lấy từ cấu hình bên ngoài như `application.properties`, `application.yml`, biến môi trường và các PropertySource khác.

Trong cấu hình annotation, hai cú pháp thường gặp là:

| Cú pháp | Vai trò | Ví dụ |
|---|---|---|
| `${...}` | Property placeholder: lấy giá trị từ cấu hình bên ngoài. | `${jobs.cleanup.cron}` |
| `#{...}` | SpEL expression: đánh giá biểu thức, đọc bean/property hoặc gọi method được phép. | `#{@jobScheduleProperties.syncRate}` |

Có thể dùng property placeholder để thay đổi lịch theo môi trường triển khai mà không sửa source code. Với các thuộc tính dạng String của `@Scheduled`, Spring cũng hỗ trợ SpEL để tính hoặc lấy giá trị từ bean trong ApplicationContext.

Ví dụ:

```java
@Scheduled(cron = "${jobs.report.cron}")
public void generateReport() {
    // ...
}
```

Ví dụ dùng SpEL với một giá trị khoảng thời gian:

```java
@Scheduled(fixedDelayString = "#{@jobScheduleProperties.cleanupDelay}")
public void cleanup() {
    // ...
}
```

Để annotation được xử lý, ứng dụng phải bật scheduling và method phải nằm trên một Spring-managed bean.

## 2. Bật @Scheduled bằng @EnableScheduling

Đặt `@EnableScheduling` trên một class cấu hình:

```java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
```

Spring đăng ký cơ chế xử lý các method có `@Scheduled` và tạo task tương ứng trong ApplicationContext. Nếu thiếu `@EnableScheduling` (hoặc cấu hình XML tương đương), annotation không tự làm cho method chạy theo lịch.

Ví dụ một bean có scheduled method:

```java
@Component
public class ReportJob {

    @Scheduled(fixedDelay = 5000)
    public void generateReport() {
        // Tạo báo cáo.
    }
}
```

Method được gọi bởi scheduler của Spring. Thông thường method có kiểu trả về `void` và không nhận tham số. Nếu method có giá trị trả về trong trường hợp đồng bộ, giá trị đó bị bỏ qua.

Các dependency mà job cần nên được inject vào bean qua constructor hoặc cơ chế dependency injection thông thường.

## 3. Các loại trigger trong @Scheduled

Với task lặp lại, `@Scheduled` cung cấp ba kiểu trigger chính:

| Thuộc tính | Ý nghĩa | Cách tính khoảng thời gian |
|---|---|---|
| `fixedRate` | Chạy theo chu kỳ cố định. | Từ thời điểm bắt đầu lần chạy này đến thời điểm bắt đầu lần kế tiếp. |
| `fixedDelay` | Chạy sau một khoảng nghỉ cố định. | Từ lúc lần chạy trước hoàn tất đến lúc lần kế tiếp bắt đầu. |
| `cron` | Chạy theo lịch ngày/giờ. | Theo các trường giây, phút, giờ, ngày, tháng và thứ. |

Ví dụ fixed rate 5 giây:

```java
@Scheduled(fixedRate = 5, timeUnit = TimeUnit.SECONDS)
public void pollQueue() {
    // Kiểm tra queue.
}
```

Ví dụ fixed delay 5 giây:

```java
@Scheduled(fixedDelay = 5, timeUnit = TimeUnit.SECONDS)
public void refreshCache() {
    // Làm mới cache.
}
```

Nếu thời gian xử lý mỗi lần chạy thay đổi, hai kiểu có ý nghĩa khác nhau. Fixed rate duy trì nhịp theo thời điểm bắt đầu; fixed delay luôn đợi đủ khoảng delay sau khi lần trước kết thúc.

### 3.1. Initial delay

Với fixed rate hoặc fixed delay, có thể đặt thời gian chờ trước lần chạy đầu tiên:

```java
@Scheduled(
    initialDelay = 10,
    fixedRate = 30,
    timeUnit = TimeUnit.SECONDS
)
public void synchronize() {
    // ...
}
```

Trong ví dụ, lần chạy đầu tiên bắt đầu sau 10 giây; các lần tiếp theo theo fixed rate 30 giây.

Một task chỉ chạy một lần sau thời gian chờ có thể chỉ khai báo initial delay:

```java
@Scheduled(initialDelay = 60_000)
public void runOnceAfterStartup() {
    // ...
}
```

Không kết hợp `initialDelay` với cron trigger. Initial delay chỉ áp dụng cho fixed rate và fixed delay.

## 4. Lấy cron expression từ application.properties

Đặt cron expression trong file cấu hình:

```properties
jobs.report.cron=0 0 2 * * MON-FRI
```

Dùng placeholder trong annotation:

```java
@Scheduled(cron = "${jobs.report.cron}")
public void generateDailyReport() {
    // ...
}
```

Khi Spring xử lý scheduled method, placeholder được phân giải thành giá trị cấu hình. Cùng một artifact có thể dùng lịch khác nhau trong từng môi trường thông qua profile hoặc PropertySource.

Ví dụ:

```properties
# application.properties
jobs.report.cron=0 0 2 * * MON-FRI
```

```properties
# application-dev.properties
jobs.report.cron=0 */10 * * * *
```

```properties
# application-prod.properties
jobs.report.cron=0 0 2 * * MON-FRI
```

Nếu active profile là `dev`, lịch báo cáo chạy mỗi 10 phút. Trong production, lịch chạy lúc 02:00 vào các ngày trong tuần.

Cần xác nhận profile và nguồn cấu hình thực tế đã được nạp. Nếu property không tồn tại và không có default value, placeholder có thể không được phân giải và việc khởi tạo scheduled task sẽ thất bại.

## 5. Default value và vô hiệu hóa cron task

Placeholder hỗ trợ giá trị mặc định sau dấu `:`:

```java
@Scheduled(cron = "${jobs.cleanup.cron:-}")
public void cleanupExpiredData() {
    // ...
}
```

Nếu `jobs.cleanup.cron` không được cấu hình, placeholder trả về `-`.

Spring định nghĩa `Scheduled.CRON_DISABLED` với giá trị `-` để vô hiệu hóa cron trigger. Cách này hữu ích khi muốn bật/tắt task từ cấu hình mà không thay đổi code.

Ví dụ:

```properties
# Tắt task
jobs.cleanup.cron=-
```

```properties
# Bật task lúc 01:30 mỗi ngày
jobs.cleanup.cron=0 30 1 * * *
```

Giá trị `-` là sentinel dành cho cron trigger; không dùng nó như một khoảng delay hợp lệ cho fixed rate hoặc fixed delay.

Trong Spring Framework, cron disabled sentinel được hỗ trợ từ 5.1. Khi dùng phiên bản cũ hơn, kiểm tra tài liệu đúng phiên bản trước khi dựa vào hành vi này.

## 6. Cú pháp cron của Spring

Cron expression của Spring dùng sáu trường theo thứ tự:

```text
second minute hour day-of-month month day-of-week
```

| Trường | Phạm vi phổ biến | Ví dụ |
|---|---|---|
| Giây | 0–59 | `0` |
| Phút | 0–59 | `30` |
| Giờ | 0–23 | `2` |
| Ngày trong tháng | 1–31 | `1` |
| Tháng | 1–12 hoặc JAN–DEC | `*` |
| Ngày trong tuần | 0–7 hoặc MON–SUN | `MON-FRI` |

Ví dụ:

| Cron | Ý nghĩa |
|---|---|
| `0 0 2 * * *` | 02:00 mỗi ngày. |
| `0 */5 * * * *` | Mỗi 5 phút, tại giây 0. |
| `0 0 9-17 * * MON-FRI` | Mỗi giờ từ 09:00 đến 17:00, thứ Hai đến thứ Sáu. |
| `0 30 8 1 * *` | 08:30 ngày đầu tiên mỗi tháng. |
| `0 0 0 * * SUN` | 00:00 mỗi Chủ nhật. |

Spring cron có thêm một số ký hiệu và macro như `L`, `W`, `#`, `@daily`, `@hourly`, `@weekly`, `@monthly` và `@yearly`.

Ví dụ:

```java
@Scheduled(cron = "@daily")
public void dailyTask() {
    // Chạy lúc nửa đêm mỗi ngày.
}
```

Cron có thể đọc khó khi chứa nhiều trường. Hãy ghi chú ý nghĩa của lịch và kiểm tra expression bằng `CronExpression.parse(...)` trong Java hoặc bằng test trước khi triển khai.

## 7. Thiết lập timezone cho cron

Thuộc tính `zone` xác định múi giờ dùng để diễn giải cron expression:

```java
@Scheduled(
    cron = "${jobs.report.cron}",
    zone = "${jobs.report.zone:Asia/Ho_Chi_Minh}"
)
public void generateReport() {
    // ...
}
```

Cấu hình:

```properties
jobs.report.cron=0 0 8 * * MON-FRI
jobs.report.zone=Asia/Ho_Chi_Minh
```

Job chạy lúc 08:00 theo giờ Việt Nam vào ngày làm việc. Nếu không chỉ định zone, scheduler dùng timezone mặc định của nó.

Dùng Zone ID hợp lệ, chẳng hạn `UTC`, `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`. Đừng giả định timezone của máy chủ giống timezone của nghiệp vụ. Khi ứng dụng chạy ở nhiều môi trường hoặc nhiều vùng địa lý, cấu hình zone tường minh giúp lịch dễ dự đoán hơn.

Thuộc tính `timeUnit` không áp dụng cho cron expression.

## 8. Dùng fixedDelayString và fixedRateString với placeholder

Các thuộc tính số nguyên `fixedDelay`, `fixedRate` và `initialDelay` nhận giá trị số trong annotation. Khi cần lấy giá trị từ cấu hình, dùng các biến thể String:

- `fixedDelayString`
- `fixedRateString`
- `initialDelayString`

Ví dụ:

```properties
jobs.cache.fixed-delay=PT30S
jobs.sync.fixed-rate=10s
jobs.sync.initial-delay=5s
```

```java
@Scheduled(fixedDelayString = "${jobs.cache.fixed-delay}")
public void refreshCache() {
    // ...
}

@Scheduled(
    fixedRateString = "${jobs.sync.fixed-rate}",
    initialDelayString = "${jobs.sync.initial-delay}"
)
public void synchronize() {
    // ...
}
```

Các thuộc tính String này hỗ trợ Spring property placeholders và SpEL expressions. Giá trị khoảng thời gian có thể dùng số nguyên (mặc định milliseconds nếu không đổi timeUnit), định dạng Duration ISO-8601 như `PT30S`, hoặc simple duration như `10s` theo hỗ trợ của phiên bản Spring đang dùng.

Nếu dùng số nguyên và muốn đơn vị khác milliseconds, có thể đặt `timeUnit`:

```java
@Scheduled(
    fixedDelayString = "${jobs.cache.delay:30}",
    timeUnit = TimeUnit.SECONDS
)
public void refreshCache() {
    // ...
}
```

Nếu chuỗi là Duration có đơn vị tường minh như `30s` hoặc ISO-8601 `PT30S`, `timeUnit` không được dùng để ghi đè đơn vị trong Duration đó.

## 9. Dùng SpEL để lấy giá trị từ bean cấu hình

SpEL hữu ích khi giá trị schedule cần được lấy từ một bean Spring thay vì chỉ đọc một property đơn giản.

Ví dụ bean giữ cấu hình:

```java
@Component("jobScheduleProperties")
@ConfigurationProperties(prefix = "jobs")
public class JobScheduleProperties {

    private String cleanupDelay = "PT30S";

    public String getCleanupDelay() {
        return cleanupDelay;
    }

    public void setCleanupDelay(String cleanupDelay) {
        this.cleanupDelay = cleanupDelay;
    }
}
```

Scheduled method tham chiếu bean bằng SpEL:

```java
@Component
public class CleanupJob {

    @Scheduled(
        fixedDelayString = "#{@jobScheduleProperties.cleanupDelay}"
    )
    public void cleanup() {
        // ...
    }
}
```

Trong biểu thức:

- `#{...}` yêu cầu đánh giá SpEL.
- `@jobScheduleProperties` tham chiếu bean có tên đó trong ApplicationContext.
- `.cleanupDelay` đọc property từ bean.
- Kết quả phải có định dạng duration mà `@Scheduled` chấp nhận.

Có thể gọi method được phép trên bean:

```java
@Scheduled(
    fixedRateString = "#{@jobScheduleProperties.getSyncRate()}"
)
public void synchronize() {
    // ...
}
```

Với cấu hình đơn giản, `${jobs.sync.rate}` thường dễ hiểu và dễ vận hành hơn. Dùng SpEL khi thật sự cần đọc bean, gọi method hoặc tính giá trị theo biểu thức.

## 10. Kết hợp property placeholder và SpEL

Hai cú pháp có mục tiêu khác nhau:

- Placeholder lấy một giá trị đã cấu hình.
- SpEL tính hoặc truy cập giá trị thông qua expression context.

Ví dụ lấy duration từ bean:

```java
@Scheduled(fixedDelayString = "#{@scheduleSettings.cleanupDelay}")
public void cleanup() {
    // ...
}
```

Ví dụ cron lấy trực tiếp từ cấu hình:

```java
@Scheduled(cron = "${jobs.cleanup.cron:-}")
public void cleanupExpiredData() {
    // ...
}
```

Đối với cron, cách thông dụng là dùng placeholder để lấy cron string từ cấu hình và dùng `-` để tắt trigger. Với fixed rate, fixed delay và initial delay dạng String, annotation Javadoc nêu rõ hỗ trợ cả placeholder lẫn SpEL.

Không đặt `${...}` và `#{...}` lồng nhau tùy tiện nếu chưa hiểu thứ tự phân giải của context. Nếu expression phức tạp, hãy đưa logic tính toán vào một bean cấu hình có tên rõ ràng và để annotation chỉ đọc một property đơn giản.

## 11. Thời điểm giá trị được phân giải

Các giá trị annotation được phân giải khi Spring xử lý và đăng ký scheduled method trong quá trình khởi tạo ApplicationContext. Sau đó scheduler sử dụng trigger đã được tạo.

Điều này có nghĩa việc thay đổi một property hoặc giá trị bean sau khi task đã được đăng ký không tự động bảo đảm lịch hiện tại được tính lại. Ví dụ, cập nhật `jobs.cleanup.cron` trong nguồn cấu hình không mặc nhiên thay thế trigger đã đăng ký.

Nếu yêu cầu là thay đổi lịch trong lúc ứng dụng đang chạy, hãy dùng cơ chế scheduling lập trình như `SchedulingConfigurer`, `TaskScheduler` và quản lý `ScheduledFuture`/task đăng ký để hủy và tạo lại lịch theo cấu hình mới.

Không nên nhầm SpEL trong annotation với một expression được đánh giá lại ở mỗi lần method chạy. Trong trường hợp thông thường, expression cung cấp metadata để đăng ký lịch; scheduler không đánh giá lại annotation trước mỗi invocation.

## 12. Chọn fixed rate, fixed delay hay cron

Chọn trigger theo ý nghĩa công việc:

| Nhu cầu | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Poll queue theo chu kỳ cố định | Fixed rate | Duy trì nhịp theo thời điểm bắt đầu. |
| Đợi xử lý xong rồi nghỉ một khoảng | Fixed delay | Khoảng nghỉ được tính sau khi lần trước hoàn tất. |
| Chạy lúc 02:00 mỗi ngày | Cron | Lịch gắn với thời điểm trên đồng hồ. |
| Chạy trong giờ hành chính các ngày làm việc | Cron | Diễn đạt lịch theo ngày/giờ rõ ràng. |
| Chờ một lúc sau startup rồi chạy một lần | Initial delay | Không cần trigger lặp. |
| Bật/tắt lịch bằng profile/config | Placeholder trong cron hoặc duration string | Không cần sửa code giữa môi trường. |

Nếu method có thể chạy lâu hơn chu kỳ, hãy xem xét scheduler, khả năng overlap và tính idempotent của công việc. Fixed rate không có nghĩa công việc chắc chắn kết thúc trước lần bắt đầu kế tiếp trong mọi cấu hình scheduler.

## 13. Cấu hình scheduler và nhiều scheduled method

Nếu ứng dụng có nhiều task hoặc task có thời gian chạy dài, có thể cấu hình TaskScheduler riêng:

```java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {

    @Bean
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.initialize();

        return scheduler;
    }
}
```

Từ Spring Framework 6.1, thuộc tính `scheduler` của `@Scheduled` có thể chọn scheduler bean hoặc qualifier:

```java
@Scheduled(
    fixedRateString = "${jobs.metrics.rate:10s}",
    scheduler = "metricsScheduler"
)
public void collectMetrics() {
    // ...
}
```

Khi có nhiều annotation `@Scheduled` trên cùng method (annotation có thể lặp lại), mỗi khai báo tạo một trigger riêng. Các lịch có thể chồng lấp hoặc gọi method gần như đồng thời. Hãy kiểm tra để tránh vô tình đăng ký hai lịch trùng nhau.

Nếu dùng `SimpleAsyncTaskScheduler` cùng virtual threads, tài liệu Spring hiện hành khuyến nghị fixed rate và cron thay cho fixed delay vì fixed-delay tasks hoạt động trên một scheduler thread duy nhất trong cấu hình đó.

## 14. Quy tắc và giới hạn của method được schedule

Một scheduled method đồng bộ thông thường:

- Không nhận tham số.
- Thường trả về `void`; giá trị trả về đồng bộ bị bỏ qua.
- Phải nằm trên bean do Spring quản lý.
- Cần tránh tạo nhiều instance của cùng bean có thể khiến cùng một lịch được đăng ký nhiều lần.
- Cần xử lý exception, log và trạng thái công việc bên trong method theo nhu cầu ứng dụng.

Spring Framework 6.1 trở lên còn hỗ trợ một số method reactive trả về Publisher hoặc kiểu có thể được chuyển thành Publisher. Publisher được tạo một lần, sau đó scheduler đăng ký subscription theo trigger. Đây là hành vi khác với method đồng bộ thông thường; cần bảo đảm Publisher hỗ trợ nhiều subscription liên tiếp và hiểu cách lỗi được ghi log.

## 15. Kiểm thử giá trị cấu hình và cron expression

Không nên chờ lịch chạy thật trong unit test để phát hiện lỗi cấu hình. Có thể kiểm tra cron expression trực tiếp:

```java
@Test
void reportCronIsValid() {
    CronExpression cron =
            CronExpression.parse("0 0 2 * * MON-FRI");

    assertNotNull(cron);
}
```

Có thể kiểm tra giá trị duration bằng cách parse:

```java
@Test
void cleanupDelayHasExpectedDuration() {
    Duration delay = Duration.parse("PT30S");

    assertEquals(Duration.ofSeconds(30), delay);
}
```

Đối với property placeholder, kiểm tra từng profile hoặc test context với PropertySource tương ứng. Đảm bảo property bắt buộc có mặt hoặc có default value hợp lệ.

Đối với SpEL bean reference, khởi tạo test ApplicationContext có bean cấu hình cần thiết và kiểm tra expression được phân giải thành duration hợp lệ.

Các tình huống nên kiểm thử:

- Property không được khai báo.
- Placeholder có default value.
- Cron expression sai số trường hoặc sai giá trị.
- Cron disabled sentinel `-`.
- Zone ID không hợp lệ hoặc không đúng với nghiệp vụ.
- Duration âm, bằng 0 hoặc sai định dạng.
- SpEL tham chiếu bean không tồn tại.
- SpEL đọc property không tồn tại hoặc trả về giá trị không thể parse thành duration.
- Hai trigger vô tình được khai báo cùng một method.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Method không chạy | Chưa bật `@EnableScheduling` hoặc bean không được Spring quản lý. | Kiểm tra cấu hình scheduling và component scan. |
| Placeholder không được phân giải | Thiếu property hoặc PropertySource/profile chưa nạp. | Kiểm tra key, profile và default value. |
| Cron task bị tắt | Giá trị cron là `-`. | Kiểm tra cấu hình môi trường và bật cron expression hợp lệ nếu cần. |
| Cron expression không hợp lệ | Sai số trường, thứ tự hoặc giá trị. | Dùng định dạng sáu trường của Spring và kiểm tra bằng CronExpression. |
| Job chạy lệch giờ | Zone không được đặt hoặc timezone máy chủ khác timezone nghiệp vụ. | Cấu hình `zone` tường minh bằng Zone ID. |
| Fixed delay khác kỳ vọng | Nhầm khoảng nghỉ sau khi hoàn tất với fixed rate. | Chọn đúng fixedDelay/fixedRate theo thời điểm cần đo. |
| Duration string không parse được | Dùng đơn vị hoặc format không được hỗ trợ. | Dùng integer với timeUnit, simple duration hoặc ISO-8601 hợp lệ. |
| `#{...}` không đánh giá được | Bean không tồn tại, sai tên hoặc expression không trả về giá trị duration hợp lệ. | Kiểm tra bean name, property/method và kiểu kết quả. |
| Đổi property nhưng lịch không đổi | Task đã được đăng ký với trigger đã phân giải. | Dùng API scheduling lập trình để hủy và đăng ký lại task. |
| Method chạy nhiều lần | Có nhiều trigger, nhiều bean instance hoặc nhiều cấu hình schedule. | Kiểm tra repeatable annotation và vòng đời bean. |
| Job chồng lấp | Thời gian xử lý dài hơn chu kỳ hoặc có nhiều trigger. | Kiểm tra scheduler, concurrency và tính idempotent. |

## 17. Quy trình cấu hình @Scheduled

1. Bật `@EnableScheduling` trong cấu hình Spring.
2. Xác định method thuộc bean Spring nào và method không nhận tham số.
3. Chọn cron, fixed rate hay fixed delay theo yêu cầu thời gian.
4. Nếu lịch phụ thuộc môi trường, đặt giá trị trong application properties/YAML hoặc nguồn cấu hình tương ứng.
5. Dùng `${...}` để đọc property và đặt default value khi task có thể tắt.
6. Dùng `fixedRateString`, `fixedDelayString`, `initialDelayString` khi cần placeholder hoặc SpEL cho duration.
7. Dùng `#{...}` để đọc một bean cấu hình khi thực sự cần biểu thức.
8. Với cron, xác định sáu trường và timezone.
9. Kiểm tra default, disabled sentinel, duration format và profile.
10. Nếu lịch phải thay đổi lúc runtime, dùng TaskScheduler/SchedulingConfigurer để quản lý việc đăng ký lại task.
11. Kiểm tra scheduler pool, khả năng overlap và log thực thi.
12. Viết test cho expression, property và trigger thay vì chỉ chờ job chạy trong môi trường thật.

## 18. Ghi nhớ

- `@EnableScheduling` bật xử lý annotation `@Scheduled`.
- `${...}` lấy property từ cấu hình; `#{...}` đánh giá SpEL.
- `fixedDelayString`, `fixedRateString` và `initialDelayString` hỗ trợ placeholder và SpEL.
- Dùng placeholder để externalize cron; giá trị `-` tắt cron trigger.
- Spring cron có sáu trường: giây, phút, giờ, ngày trong tháng, tháng và ngày trong tuần.
- `zone` quyết định timezone của cron.
- Fixed rate đo giữa các thời điểm bắt đầu; fixed delay đo từ lúc lần trước hoàn tất.
- Initial delay áp dụng cho fixed rate/fixed delay; cron không hỗ trợ initial delay.
- Giá trị annotation được phân giải khi task được đăng ký; thay đổi config không tự động reschedule task đang chạy.
- Dùng TaskScheduler/SchedulingConfigurer khi cần quản lý lịch động.
- Kiểm tra profile, property, duration, cron, timezone, scheduler và khả năng chạy chồng lấp.

## Tài liệu tham khảo

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — @Scheduled](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)
- [Spring Framework Javadoc — ScheduledAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/ScheduledAnnotationBeanPostProcessor.html)
- [Spring Framework Javadoc — CronExpression](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronExpression.html)
- [Spring Framework Javadoc — TaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
