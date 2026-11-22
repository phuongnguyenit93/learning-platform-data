# Clock của scheduler và ý nghĩa thời gian sử dụng

> **Chủ đề:** Spring Framework – concurrency  
> **Nhóm:** TaskScheduler  
> **Tư tưởng cốt lõi:** `TaskScheduler` có một `java.time.Clock` để xác định “bây giờ” khi tính lịch. Nhưng **thời điểm tuyệt đối** (`Instant`), **khoảng thời gian** (`Duration`), **múi giờ lịch dân sự** (`ZoneId`) và **thời gian thực thi/đợi của thread pool** không phải một thứ. Chọn đúng loại thời gian và hiểu ranh giới của `getClock()`/`setClock()` giúp tránh chạy cron sai giờ, test chập chờn và nhầm rằng chỉ cần đổi clock là đã tạo được một scheduler ảo.

Bài học lấy **Spring Framework 6.2.x + Java 17** làm bối cảnh. Ví dụ chạy độc lập có kết quả xác định; ví dụ Spring Context phân biệt **clock dùng để tính toán lịch** với **executor thật sự chạy task**. Các cú pháp minh họa không độc lập được ghi rõ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `TaskScheduler#getClock()` trả gì và `ThreadPoolTaskScheduler#setClock(Clock)` dùng cho mục đích gì.
2. Phân biệt `Clock`, `Instant`, `Duration`, `LocalDateTime`, `ZonedDateTime`, `ZoneId` và `System.nanoTime()` theo đúng đơn vị và ngữ nghĩa.
3. Hiểu vì sao `schedule(task, Instant)` khác `scheduleAtFixedRate(task, Duration)` và `scheduleWithFixedDelay(task, Duration)`.
4. Dự đoán ngày giờ của một `CronTrigger` khi dùng clock có múi giờ mặc định hoặc khi chỉ định `ZoneId` rõ ràng.
5. Nhận ra rủi ro do timezone server, DST, thay đổi đồng hồ hệ điều hành và task chạy chậm/lỡ lần kích hoạt.
6. Dùng `Clock.fixed`/`Clock.offset` để kiểm thử phép **tính lịch** mà không ngủ và không đợi cron thật.
7. Cấu hình bean `ThreadPoolTaskScheduler` do Spring container quản lý và quan sát kết quả schedule một lần bằng `ScheduledFuture`.
8. Phân biệt “ảo hóa giờ” trong test với một **virtual-time scheduler có quyền điều khiển hàng đợi**; không gán cho `setClock` năng lực không được API cam kết.
9. Thiết kế logging, metrics, deadline và chính sách nhiều instance cho scheduled jobs.

## 2. Vì sao scheduler cần Clock?

Một scheduler phải trả lời nhiều loại câu hỏi:

- “**Bây giờ** là thời điểm nào?” — dùng một nguồn thời gian để ra quyết định.
- “Chạy vào **09:00 sáng theo giờ Việt Nam**?” — lịch theo múi giờ dân sự, có quy tắc chuyển sang thời điểm tuyệt đối.
- “Chạy vào đúng **Instant 2026-01-01T02:00:00Z**?” — đã có timestamp tuyệt đối.
- “Lặp lại **mỗi 10 giây**?” — khoảng thời gian, không phải một giờ trong ngày.
- “Chạy tiếp **5 giây sau khi lần trước hoàn thành**?” — khoảng chờ tính từ completion, khác lịch cố định.
- “Job đã trễ **bao nhiêu ms** so với lịch?” — so sánh thời điểm thực tế với planned time.
- “Job thật sự chiếm CPU hoặc đợi I/O **bao lâu**?” — đo elapsed time, thường cần nguồn monotonic.

Nếu chỉ dùng `LocalDateTime.now()` hoặc `System.currentTimeMillis()` rải khắp code, kết quả có thể thay đổi giữa môi trường test/dev/prod, khó mô phỏng đồng hồ và dễ dựa vào timezone mặc định ngoài ý muốn. Một `Clock` được inject giúp tách phần tính toán “hiện tại là khi nào” khỏi việc gọi đồng hồ hệ thống trực tiếp.

### 2.1. Clock là một đối tượng cung cấp thời gian, không phải worker thread

`java.time.Clock` cung cấp chủ yếu:

~~~java
Instant instant();
ZoneId getZone();
Clock withZone(ZoneId zone);
~~~

`Clock` **không** có lệnh “chạy task”, không tạo thread, không quản lý queue hay job state. Một `Clock.fixed(...)` luôn báo cùng một `Instant`; điều đó có ích cho test phép tính thời gian, **không** làm CPU/OS và `ScheduledThreadPoolExecutor` tự động tiến theo clock giả lập.

### 2.2. TaskScheduler quản lý quyết định đặt lịch và thực thi

Spring `org.springframework.scheduling.TaskScheduler` là một interface để gửi `Runnable` theo một thời điểm hoặc một quy luật kích hoạt. Nó có thể sử dụng clock để hiểu thời điểm hiện tại và cung cấp clock cho `TriggerContext` khi tính thời điểm kích hoạt tiếp theo.

Bảng phân vai:

| Thành phần | Trả lời câu hỏi nào? | Không tự đảm bảo |
| --- | --- | --- |
| `Clock` | Hiện tại là Instant nào? Zone mặc định là gì? | Không chạy task, không quản lý thread |
| `TaskScheduler` | Gửi/chạy Runnable khi nào theo Instant, Duration, Trigger? | Không bảo đảm chạy chính xác từng mili-giây |
| `Trigger` | Lần kích hoạt kế tiếp nên là Instant nào? | Không tự thực thi task |
| `TriggerContext` | Clock, lần scheduled/actual/completion trước là gì? | Không lưu job bền qua restart |
| `ThreadPoolTaskScheduler` | Triển khai TaskScheduler trên scheduled executor | Không tự tạo điều phối “chỉ chạy một lần toàn cụm” |
| `ScheduledFuture<?>` | Theo dõi/cancel execution theo contract | Không phải lịch sử nghiệp vụ bền vững |

## 3. TaskScheduler API: Clock nằm ở đâu?

Với Spring 6.2.x, các phương thức chính của `TaskScheduler` có ý nghĩa tương đương:

~~~java
Clock getClock();

ScheduledFuture<?> schedule(
        Runnable task, Instant startTime);

ScheduledFuture<?> schedule(
        Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);
~~~

Đây là **bảng chữ ký minh họa từ interface**, không phải một file Java độc lập.

- `getClock()`: clock mà scheduler dùng cho mục đích schedule; trong interface có default method.
- `schedule(task, Instant)`: một lần theo **thời điểm tuyệt đối**; nếu thời điểm đã qua, implementation thông thường chạy càng sớm càng tốt.
- `schedule(task, Trigger)`: trigger chọn các `Instant` lần sau dựa trên `TriggerContext`, phù hợp với cron và rule tùy biến.
- `scheduleAtFixedRate`: diễn đạt **nhịp bắt đầu theo chu kỳ**, tùy số worker và thời lượng task mà lần chạy thực tế có thể muộn.
- `scheduleWithFixedDelay`: diễn đạt **thời gian chờ sau khi lần trước hoàn thành** trước khi khởi động lần kế tiếp.

API `TaskScheduler` không nên bị nhầm với `TaskExecutor`: `TaskExecutor.execute` nhận task chạy theo cơ chế executor, không cung cấp một `Instant`/`Trigger` để quyết định tương lai.

### 3.1. Clock mặc định

Javadoc của `TaskScheduler#getClock()` nói clock dùng cho mục đích scheduling; default clock là clock hệ thống của timezone mặc định. `ThreadPoolTaskScheduler` công bố:

~~~java
Clock getClock();
void setClock(Clock clock);
~~~

Trong `ThreadPoolTaskScheduler`, mặc định là tương đương `Clock.systemDefaultZone()` trừ khi cấu hình khác. **Không** cho rằng mọi `TaskScheduler` tùy biến luôn dùng cùng mặc định: hãy kiểm tra class thực tế và cấu hình của app.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class SchedulerConfig {
    @Bean("businessScheduler")
    ThreadPoolTaskScheduler businessScheduler() {
        ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
        s.setPoolSize(2);
        s.setClock(Clock.systemUTC());
        s.setThreadNamePrefix("business-schedule-");
        return s;
    }
}
~~~

Đây là **snippet Spring**, cần imports cho `@Configuration`, `@Bean`, `ThreadPoolTaskScheduler` và `Clock`. Khi là bean, Spring khởi tạo/hủy scheduled executor theo lifecycle. `Clock.systemUTC()` làm clock có zone UTC, chứ không tự bắt buộc tất cả cron trong hệ thống phải chạy UTC: mỗi `CronTrigger` có thể chỉ định zone riêng và annotation `@Scheduled` cũng có thuộc tính `zone`.

### 3.2. Clock của scheduler không đồng nghĩa timezone của mọi business event

Giả sử người dùng có lịch “09:00 sáng tại Hà Nội”. Đó là một quy tắc theo `ZoneId.of("Asia/Ho_Chi_Minh")`. Nếu scheduler dùng `Clock.systemUTC()`, **vẫn có thể** chạy theo 09:00 giờ Việt Nam bằng cách chỉ định zone cho cron. Múi giờ của clock là **mặc định khi không có zone rõ ràng**, không phải một hạn chế bắt buộc của lịch.

Ngược lại, một `Clock.systemDefaultZone()` trên máy chủ ở UTC không thể tự suy rằng người dùng muốn 09:00 giờ Việt Nam. Khi yêu cầu là lịch theo địa phương, hãy lưu zone hợp lệ theo business identity; đừng dựa vào timezone của pod/node.

## 4. Phân biệt sáu khái niệm thời gian

### 4.1. Instant — một điểm tuyệt đối trên timeline

`Instant` biểu diễn một điểm trên timeline UTC. Ví dụ:

~~~text
2026-01-01T02:00:00Z
~~~

Đó là cùng một **thời điểm thực** khi hiển thị:

~~~text
2026-01-01 09:00 tại Asia/Ho_Chi_Minh (+07:00)
2026-01-01 02:00 tại UTC
~~~

Tạo `Instant`:

~~~java
Instant when = Instant.parse("2026-01-01T02:00:00Z");
scheduler.schedule(job, when);
~~~

**Snippet**: `scheduler` và `job` phải được khai báo. Sử dụng `Instant` cho ý nghĩa “chạy tại đúng thời điểm tuyệt đối này”.

### 4.2. Duration — một khoảng thời gian

`Duration.ofSeconds(10)` biểu diễn một **độ dài 10 giây**, không chứa ngày, giờ địa phương hay timezone:

~~~java
Duration period = Duration.ofSeconds(10);
scheduler.scheduleAtFixedRate(job, period);
~~~

**Snippet**: không nói “10 giờ sáng” hay “mỗi ngày lúc 09:00”. Nếu muốn lịch 09:00 địa phương mỗi ngày, dùng cron/zone; đừng mặc định `Duration.ofHours(24)` tương đương một ngày theo lịch ở mọi timezone.

### 4.3. LocalDateTime — thời gian dân sự thiếu zone

`LocalDateTime.of(2026, 1, 1, 9, 0)` nghĩa là “09:00 trên một lịch địa phương” **chưa có thông tin nó nằm ở đâu**. Vì vậy, nó không thể tự xác định một `Instant` nếu không chọn `ZoneId` hoặc offset:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 1, 1, 9, 0);
ZoneId city = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = local.atZone(city).toInstant();
~~~

**Snippet Java 17**. Dùng `LocalDateTime` cho form input kiểu “ngày/giờ”, sau đó **bắt buộc** kết hợp với zone được xác thực trước khi gửi vào `schedule(..., Instant)`.

### 4.4. ZonedDateTime — local date/time + ZoneId

`ZonedDateTime` mang thông tin quy tắc timezone đầy đủ: offset theo mùa, DST nếu có, chuyển đổi theo lịch sử/chính sách. Dùng `ZoneId.of("America/New_York")` sẽ khác `ZoneOffset.of("-05:00")` trong giai đoạn mùa hè vì New York có DST còn fixed offset thì không.

### 4.5. Clock — “now” có thể thay thế được

`Instant.now(clock)` và `LocalDate.now(clock)` giúp viết code test có kết quả xác định:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

Instant now = Instant.now(clock);
LocalDate today = LocalDate.now(clock);
~~~

**Snippet**: đồng hồ luôn báo mốc đã chọn. Không có thread tự chạy khi bạn gọi `clock.instant()`. `Clock.withZone(...)` tạo một clock cùng timeline nhưng khác zone trình bày/diễn giải; nó không tự “đẩy giờ” lên 7 tiếng nếu hiện tại vẫn là cùng Instant.

### 4.6. System.nanoTime — đo thời gian trôi qua

Nếu mục tiêu là đo “job đã chạy bao lâu”, dùng:

~~~java
long startNanos = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    recordDuration(elapsedNanos);
}
~~~

Đây là **snippet** với `doWork` và `recordDuration` do ứng dụng cung cấp. `System.nanoTime()` dành cho chênh lệch thời gian trong cùng một JVM, không phải Unix timestamp và không được serialize làm schedule time. Đừng convert `nanoTime()` thành ngày/giờ UTC.

## 5. Java 17 chạy độc lập: một Instant, hai timezone và Clock.fixed

Tạo tệp **`ClockSemanticsDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ClockSemanticsDemo {
    public static void main(String[] args) {
        Instant base = Instant.parse("2026-01-01T00:00:00Z");
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock vietnamClock = Clock.fixed(base, hcm);
        Clock utcClock = vietnamClock.withZone(ZoneOffset.UTC);

        System.out.println("instant = " + vietnamClock.instant());
        System.out.println("same instant = "
                + vietnamClock.instant().equals(utcClock.instant()));
        System.out.println("HCM date = " + LocalDate.now(vietnamClock));
        System.out.println("HCM local = "
                + LocalDateTime.now(vietnamClock));
        System.out.println("UTC local = "
                + LocalDateTime.now(utcClock));

        ZonedDateTime nineAm = ZonedDateTime.of(
                LocalDate.of(2026, 1, 1),
                LocalTime.of(9, 0),
                hcm);
        System.out.println("09 HCM in UTC = " + nineAm.toInstant());

        Duration wait = Duration.between(
                vietnamClock.instant(), nineAm.toInstant());
        System.out.println("until 09 HCM = " + wait);

        Clock shifted =
                Clock.offset(vietnamClock, Duration.ofMinutes(30));
        System.out.println("offset instant = " + shifted.instant());
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac ClockSemanticsDemo.java
java ClockSemanticsDemo
~~~

**Stdout xác định**:

~~~text
instant = 2026-01-01T00:00:00Z
same instant = true
HCM date = 2026-01-01
HCM local = 2026-01-01T07:00
UTC local = 2026-01-01T00:00
09 HCM in UTC = 2026-01-01T02:00:00Z
until 09 HCM = PT2H
offset instant = 2026-01-01T00:30:00Z
~~~

Điểm cần thấy:

1. `vietnamClock` và `utcClock` có **cùng Instant** mặc dù `getZone()` khác nhau.
2. Local time 07:00 tại Việt Nam chính là 00:00 UTC ở ví dụ này.
3. 09:00 giờ Việt Nam là 02:00 UTC cùng ngày; số `Instant` không cộng 7 giờ lần nữa khi schedule.
4. `Duration.between` cho một khoảng chờ **2 giờ** từ now đến lúc chạy.
5. `Clock.offset` dịch mốc do clock báo thêm 30 phút để **test tính toán**, không thực sự trôi 30 phút trên hệ điều hành.

**Không phải Spring demo:** đây là ví dụ Java SE thuần để hiểu các kiểu thời gian. Ví dụ Spring Context ở mục 11 dùng `TaskScheduler` thật và `CronTrigger` trên clock cố định để test **calculation**.

## 6. TriggerContext: clock truyền vào phép tính lần chạy sau

Spring `Trigger` có phương thức:

~~~java
Instant nextExecution(TriggerContext triggerContext);
~~~

`TriggerContext` cung cấp:

~~~java
Clock getClock();
Instant lastScheduledExecution();
Instant lastActualExecution();
Instant lastCompletion();
~~~

Những phương thức này có vai trò khác nhau:

- **`getClock()`:** “hiện tại/zone” để tính lần tiếp theo, nhất là khi chưa có lịch sử.
- **`lastScheduledExecution()`:** thời điểm đã định schedule ở lần trước; không nhất thiết là lúc worker thực sự vào `run()`.
- **`lastActualExecution()`:** lúc task thực sự bắt đầu ở lần trước.
- **`lastCompletion()`:** lúc task hoàn thành ở lần trước.

Tại sao cần phân biệt? Một task dự kiến chạy 09:00 nhưng pool bận đến 09:03 mới bắt đầu, hoàn thành 09:05. Lịch tiếp theo dựa trên **scheduled 09:00** có thể khác lịch dựa trên **completion 09:05**.

~~~text
09:00      09:03           09:05
  |          |               |
planned    actual          completed
  |          |               |
lastScheduledExecution()    lastCompletion()
             |
      lastActualExecution()
~~~

Sơ đồ là **một kịch bản minh họa**, không phải giả định mọi job đều muộn 3 phút.

### 6.1. CronTrigger dùng clock và lịch sử

Với `CronTrigger`, Spring lấy clock/zone trong trigger context khi cần. Nếu không cung cấp zone riêng cho cron, việc tính lịch dựa trên timezone của clock trong `TriggerContext`. Nếu truyền `ZoneId` rõ ràng trong constructor, zone đó được dùng để diễn giải cron.

Cron thông thường có 6 trường:

~~~text
second minute hour day-of-month month day-of-week
0      0      9    *            *     *
~~~

Biểu thức `"0 0 9 * * *"` tức 09:00 mỗi ngày trong timezone đang được dùng; nó **không tự có UTC**.

### 6.2. Context không tự lưu trạng thái bền vững

`SimpleTriggerContext` là holder đơn giản dùng trong tính toán/test. Một scheduler thật theo dõi execution context cho trigger trong runtime của nó. Nếu process restart, các thông tin in-memory trước đó có thể mất; đừng suy scheduler có lịch sử công việc bền vững hoặc replay tất cả missed fires sau deploy. Nếu nghiệp vụ cần lịch sử/leader election/persistence, cần giải pháp job scheduler bền vững có storage phù hợp.

## 7. CronTrigger và tác động của timezone

Giả sử biểu thức:

~~~text
0 0 9 * * *
~~~

Nếu dùng clock mặc định của scheduler đang ở **UTC**, nó diễn giải thành 09:00 UTC (tức 16:00 tại Việt Nam cho ngày trong ví dụ). Nếu dùng timezone **Asia/Ho_Chi_Minh**, nó diễn giải thành 09:00 Việt Nam (02:00 UTC).

Một cách rõ ràng:

~~~java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
CronTrigger businessNine = new CronTrigger(
        "0 0 9 * * *", vietnam);

scheduler.schedule(
        () -> sendDailyReport(),
        businessNine);
~~~

Đây là **Spring snippet**, cần import `ZoneId`, `CronTrigger`, `TaskScheduler` và nghiệp vụ `sendDailyReport()`. Zone được khai báo tường minh nên lịch không bị thay đổi chỉ vì timezone của container khác.

### 7.1. Có nên chỉnh systemDefaultZone của JVM?

Chỉnh `user.timezone` cho cả JVM có thể ảnh hưởng logging, serialization, database client, cron mặc định và code gọi `LocalDate.now()`. Nếu một job cần chạy theo giờ Việt Nam, cách an toàn hơn là **chỉ định ZoneId của job hoặc scheduler** thay vì thay đổi timezone toàn process mà không đánh giá các subsystem khác.

Với multi-tenant, mỗi tenant có zone riêng, nên lưu zone theo tenant. Một global scheduler clock dùng UTC vẫn hoàn toàn có thể schedule từng cron theo zone khác nhau.

### 7.2. Asia/Ho_Chi_Minh và DST

Trong giai đoạn hiện tại, `Asia/Ho_Chi_Minh` có offset UTC+07 và không có chu kỳ DST thường niên. Nhưng một lịch toàn cầu phải xét zone có DST như `America/New_York`.

- **Spring forward (gap):** một local time như 02:30 có thể **không tồn tại** trong ngày chuyển DST.
- **Fall back (overlap):** một local time như 01:30 có thể xuất hiện **hai lần** theo hai offset.
- Cron theo local clock cần có business policy về bỏ qua, chạy một lần hay xử lý hai occurrence. Hành vi cụ thể phụ thuộc thuật toán trigger/version và lịch sử; không suy rằng mọi cron engine có cùng cách xử lý DST.
- `ZoneOffset.of("-05:00")` chỉ là offset cố định; nó **không giữ quy tắc DST của New York** qua các tháng.

Với báo cáo tài chính “một lần mỗi ngày”, thiết kế dedup theo **business date + zone + job key** quan trọng không kém việc chọn cron đúng. Nếu mất một lịch do downtime/DST, cần biết có backfill hay không.

## 8. Clock.fixed trong test: nên đặt ở đâu?

Khi kiểm thử “cron 09:00 Việt Nam sẽ chạy vào Instant nào”, bạn **không cần mở thread scheduler**. Tạo `Clock.fixed` rồi đưa vào một `SimpleTriggerContext`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

SimpleTriggerContext context = new SimpleTriggerContext(fixed);
CronTrigger trigger = new CronTrigger("0 0 9 * * *");

Instant next = trigger.nextExecution(context);
// Kết quả kỳ vọng: 2026-01-01T02:00:00Z
~~~

Đây là **Spring snippet**, cần imports `Clock`, `Instant`, `ZoneId`, `SimpleTriggerContext` và `CronTrigger`. Vì `context` có clock cố định đang báo 07:00 tại Việt Nam, cron 09:00 của cùng ngày tính ra **02:00Z**. Không cần sleep hoặc đợi đến 09:00 thực.

### 8.1. Test zone explicit khác zone của clock

~~~java
Clock fixedHcm = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

SimpleTriggerContext ctx = new SimpleTriggerContext(fixedHcm);

Instant localNine = new CronTrigger(
        "0 0 9 * * *").nextExecution(ctx);

Instant utcNine = new CronTrigger(
        "0 0 9 * * *",
        ZoneId.of("UTC")).nextExecution(ctx);
~~~

**Snippet**. Kỳ vọng `localNine = 2026-01-01T02:00:00Z` và `utcNine = 2026-01-01T09:00:00Z`. Hai cron có cùng chuỗi nhưng zone khác → hai `Instant` khác nhau.

### 8.2. Vì sao không set Clock.fixed trực tiếp lên scheduler thật rồi đợi nó chạy?

Đây là lỗi thiết kế test thường gặp:

~~~java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setClock(Clock.fixed(testInstant, ZoneId.of("UTC")));
scheduler.initialize();
scheduler.schedule(() -> doWork(), testInstant.plusSeconds(10));
// Sai nếu kỳ vọng gọi Clock.offset() sẽ tự khiến task chạy.
~~~

Đây là **snippet phản ví dụ**; cần `testInstant` và `doWork`, và phải shutdown scheduler nếu đã khởi tạo. Sau khi đã schedule, **underlying scheduled executor** vẫn quản lý delayed tasks theo cơ chế thời gian thực của JVM. Đổi biến Clock trong test không có nghĩa queue của scheduler có thể được đẩy tới tương lai theo yêu cầu. `Clock.fixed` không tự tiến; `Clock.offset(...)` tạo **clock mới**, không làm clock cũ hoặc queue tự cập nhật.

**Quy tắc:** unit test thuần **tính toán trigger** dùng fixed clock; test execution thực dùng scheduler thật + synchronization (future/latch), hoặc dùng **virtual scheduler/test harness** có khả năng điều khiển advancement của queue một cách rõ ràng.

## 9. schedule(Runnable, Instant): biến “lúc nào” thành task

Một lời gọi:

~~~java
Instant start = Instant.now(clock).plusSeconds(30);
ScheduledFuture<?> future = scheduler.schedule(job, start);
~~~

**Snippet**: `clock`, `scheduler` và `job` là dependency đã khai báo. Hàm `schedule` nhận **Instant tuyệt đối**, không nhận một timestamp tính theo timezone của máy.

### 9.1. Khi Instant đã ở trong quá khứ

Theo Javadoc Spring, nếu `startTime` đã qua, task được chạy **ngay khi có thể** chứ không được quay về quá khứ. “Ngay khi có thể” không đồng nghĩa ngay lập tức trên caller, vì còn scheduling và worker availability.

Trong demo Spring Context ở mục 11, ta cố ý đặt `Instant.now(clock).minusSeconds(1)` và đợi `ScheduledFuture.get(timeout)` để kiểm tra task thật sự hoàn thành.

### 9.2. Thay đổi giờ hệ điều hành

Khi ứng dụng schedule một Instant trong tương lai, implementation có thể chuyển nó thành delay dựa vào clock hiện tại tại thời điểm đặt lịch. Executor nền có thể dựa trên một bộ đếm elapsed time tương đối. Vì thế, thay đổi wall-clock **sau khi task đã được đưa vào queue** không nhất thiết làm thời gian chờ đã tính trước được điều chỉnh theo đúng mức đổi. Điều này phụ thuộc implementation và kiểu trigger (one-shot hay phải tính lịch lại).

**Không dựa vào** giả định “scheduler luôn chạy đúng hh:mm:ss dù NTP hoặc admin chỉnh đồng hồ hệ thống” cho những yêu cầu chính xác tuyệt đối; cân nhắc đồng bộ clock, đo schedule lag và xử lý late/missed triggers theo business policy.

## 10. Fixed rate, fixed delay và cron: ý nghĩa thời gian khác nhau

| Hình thức | Tham số thời gian | Cách hiểu | Phụ thuộc timezone? |
| --- | --- | --- | --- |
| `schedule(task, Instant)` | `Instant` | Một execution dự định tại timestamp tuyệt đối | Không để xác định timestamp; có thể phụ thuộc clock khi tính delay |
| `scheduleAtFixedRate(task, Duration)` | `Duration` | Lặp theo nhịp/period từ thời điểm bắt đầu | Không phải quy luật giờ địa phương |
| `scheduleWithFixedDelay(task, Duration)` | `Duration` | Đợi một khoảng sau khi task trước hoàn thành | Không phải quy luật giờ địa phương |
| `schedule(task, Trigger)` với `CronTrigger` | Chuỗi cron + `ZoneId` | Tính các giờ/ngày dân sự rồi đổi sang `Instant` | Có, nếu biểu thức chứa lịch/giờ địa phương |
| `@Scheduled(cron=..., zone=...)` | Cron + zone | Lịch declarative trong Spring | Có, theo zone được chọn |
| `@Scheduled(fixedDelayString=...)` | Thời lượng | Sau khi hoàn thành, chờ delay | Không phải cron địa phương |

### 10.1. Fixed rate

Ví dụ:

~~~java
scheduler.scheduleAtFixedRate(
        () -> pollMetrics(),
        Duration.ofSeconds(10));
~~~

**Snippet**, `scheduler` và `pollMetrics()` thuộc ứng dụng. Mục tiêu là nhịp khoảng 10 giây giữa các **thời điểm bắt đầu theo lịch**. Nếu task chạy 15 giây hoặc pool bão hòa, execution có thể bị trễ; không được ngầm hứa scheduler tạo thêm thread vô hạn để thực hiện đúng từng tick.

Với `ThreadPoolTaskScheduler` dựa trên `ScheduledThreadPoolExecutor`, các lần execution của **cùng một periodic task** không chạy đè lên nhau theo contract JDK; những lần chạy muộn có thể nối tiếp sát nhau. Với **nhiều task/annotation khác nhau**, chúng có thể chồng lấp nếu pool có worker và workload cho phép.

### 10.2. Fixed delay

~~~java
scheduler.scheduleWithFixedDelay(
        () -> pollMetrics(),
        Duration.ofSeconds(10));
~~~

**Snippet**. Nếu một lần chạy bắt đầu 09:00, mất 5 giây và hoàn thành 09:00:05, lần sau **không** bắt đầu trước khoảng 09:00:15 theo ý nghĩa fixed delay. Nếu lần trước mất 20 giây thì lần sau càng muộn. Đây là cơ chế phù hợp khi muốn “nghỉ” giữa các lần hoàn thành.

### 10.3. Cron

~~~java
scheduler.schedule(
        () -> generateDailySummary(),
        new CronTrigger(
                "0 0 9 * * *",
                ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

**Snippet**. Cron biểu diễn **09:00 theo lịch của zone**, không phải cứ đúng 24 giờ kể từ lần chạy trước. Khi DST áp dụng ở zone khác, một “ngày dân sự” có thể dài 23 hoặc 25 giờ tính theo elapsed time.

### 10.4. Sơ đồ minh họa

Giả sử task mất 7 giây và period/delay được cấu hình là 5 giây:

~~~text
fixed-rate target:  00s  05s  10s  15s  20s ...
task run 1:         [---------7s---------]
task run 2:                    [---------7s---------]
=> start thực tế có thể trễ lịch, tùy pool/implementation

fixed-delay:
task run 1:         [---------7s---------]
chờ:                                  [---5s---]
task run 2:                                     [---------7s---------]
=> khoảng chờ đo từ completion
~~~

Sơ đồ chỉ minh họa quan hệ, không phải kết quả timing cứng của một môi trường cụ thể. Để kiểm chứng, hãy ghi `scheduled/actual/completion` và đo chênh lệch.

## 11. Spring Context demo Java 17: clock thật để chạy, clock cố định để tính lịch

Ví dụ sau **chạy được** chỉ với `spring-context`, không cần Spring Boot/Web server. Nó chứng minh:

1. `ThreadPoolTaskScheduler` là Spring bean được container quản lý.
2. `setClock(Clock.systemUTC())` làm scheduler công bố zone UTC.
3. Một one-shot task có `Instant` trong quá khứ được chạy càng sớm càng tốt; `ScheduledFuture.get` đồng bộ hóa kết quả.
4. `SimpleTriggerContext(Clock.fixed(...))` tính cron 09:00 theo timezone Việt Nam mà **không khởi chạy worker**.
5. Cron với zone UTC rõ ràng tạo `Instant` khác, dù cùng biểu thức.

### 11.1. Cấu trúc dự án

~~~text
spring-clock-demo/
├── pom.xml
└── src/main/java/demo/SchedulerClockDemo.java
~~~

Tệp **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-clock-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **`src/main/java/demo/SchedulerClockDemo.java`**:

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.scheduling.support.SimpleTriggerContext;

public class SchedulerClockDemo {

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean("businessScheduler")
        ThreadPoolTaskScheduler businessScheduler() {
            ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
            s.setPoolSize(1);
            s.setClock(Clock.systemUTC());
            s.setThreadNamePrefix("clock-demo-");
            return s; // Spring gọi initialize và destroy.
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            TaskScheduler scheduler =
                    context.getBean("businessScheduler", TaskScheduler.class);

            System.out.println("scheduler zone = "
                    + scheduler.getClock().getZone());

            // Mốc đã qua -> one-shot task chạy ASAP, không in từ worker.
            Instant past = scheduler.getClock().instant().minusSeconds(1);
            ScheduledFuture<?> future = scheduler.schedule(() -> { }, past);
            if (future == null) {
                throw new IllegalStateException("no task scheduled");
            }
            future.get(5, TimeUnit.SECONDS);
            System.out.println("past task done = " + future.isDone());

            Clock fixed = Clock.fixed(
                    Instant.parse("2026-01-01T00:00:00Z"),
                    ZoneId.of("Asia/Ho_Chi_Minh"));

            SimpleTriggerContext triggerContext =
                    new SimpleTriggerContext(fixed);

            CronTrigger defaultZoneCron =
                    new CronTrigger("0 0 9 * * *");
            CronTrigger utcCron =
                    new CronTrigger(
                            "0 0 9 * * *",
                            ZoneId.of("UTC"));

            System.out.println("HCM nine = "
                    + defaultZoneCron.nextExecution(triggerContext));
            System.out.println("UTC nine = "
                    + utcCron.nextExecution(triggerContext));
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SchedulerClockDemo
~~~

**Stdout do class demo in khi chạy thành công**, không tính log riêng của Maven/Spring:

~~~text
scheduler zone = Z
past task done = true
HCM nine = 2026-01-01T02:00:00Z
UTC nine = 2026-01-01T09:00:00Z
~~~

### 11.2. Vì sao stdout không phụ thuộc thời gian hệ thống?

- Zone `Z` đến từ `Clock.systemUTC()`, không đến từ default timezone của máy.
- `past` được tính bằng scheduler clock thật rồi lùi 1 giây; tại thời điểm schedule, nó đã thuộc quá khứ. `future.get(5, TimeUnit.SECONDS)` chờ task hoàn tất rồi mới kiểm tra `isDone`; timeout là guard khi môi trường có vấn đề.
- Hai phép tính cron dùng `Clock.fixed` tại thời điểm 2026-01-01T00:00Z và zone rõ ràng. Chúng không dựa vào current date; không cần chờ đến một giờ thật.
- `CronTrigger` không được gửi tới scheduler để chạy; chỉ hỏi `nextExecution` với context giả lập nên kết quả deterministic.
- Context tự hủy `ThreadPoolTaskScheduler` theo vòng đời Spring khi đóng; không bỏ lại một executor tự tạo chưa shutdown.

**Điều không chứng minh:** `Clock.fixed` không làm cho one-shot task chạy ở một “thời gian giả”. One-shot task ở ví dụ dùng `Clock.systemUTC` **thật**, còn fake clock chỉ để kiểm tra việc tính cron.

## 12. @Scheduled và múi giờ của ứng dụng

Spring `@Scheduled` cho phép khai báo lịch ở method bean, nếu đã bật `@EnableScheduling`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableScheduling
class SchedulingConfiguration {
}
~~~

~~~java
@Component
class DailyReportJob {

    @Scheduled(
            cron = "0 0 9 * * *",
            zone = "Asia/Ho_Chi_Minh")
    public void runDaily() {
        generateDailyReport();
    }
}
~~~

Đây là **hai class snippet Spring**, cần imports `@Configuration`, `@EnableScheduling`, `@Component`, `@Scheduled` và method `generateDailyReport`. Nếu hệ thống có nhiều bean `TaskScheduler`, phải cấu hình lựa chọn scheduler theo hợp đồng của Spring; không tin rằng annotation tự dùng đúng bean bạn muốn.

### 12.1. Khi có @Scheduled(zone = ...)

`@Scheduled(cron = ..., zone = "Asia/Ho_Chi_Minh")` nêu timezone cho cách tính **cron expression**. Vì thế chạy trên máy chủ UTC hay Asia/Singapore vẫn có cùng quy tắc lịch 09:00 Việt Nam, với điều kiện clock/timezone database và system configuration hoạt động nhất quán.

### 12.2. Khi bỏ zone

~~~java
@Scheduled(cron = "0 0 9 * * *")
public void runDaily() { /* business code */ }
~~~

**Snippet**. Lịch sẽ dùng timezone mặc định của scheduler/clock theo cơ chế Spring, vì thế môi trường deploy khác nhau có thể diễn giải giờ 09:00 khác nhau. Nếu business yêu cầu một zone xác định, hãy ghi thẳng `zone` hoặc cấu hình clock/trigger một cách rõ ràng.

### 12.3. Fixed delay và fixed rate không phải cron địa phương

~~~java
@Scheduled(fixedDelay = 10, timeUnit = TimeUnit.SECONDS)
public void pollAfterCompletion() { /* poll */ }

@Scheduled(fixedRate = 10, timeUnit = TimeUnit.SECONDS)
public void pollOnCadence() { /* poll */ }
~~~

Đây là **method snippets**, yêu cầu imports và cấu hình Spring. Chúng là khoảng thời gian tương đối, không có “giờ 09:00 theo một timezone”. `zone` là thông số của cron, không phải một công tắc biến fixed-rate thành wall-clock calendar schedule.

**Lưu ý về Spring MVC/Boot:** `@EnableScheduling` cần được bật ở application context thích hợp. Nếu bạn chỉ thêm method annotation nhưng không kích hoạt scheduling hoặc bean không được container quản lý, task sẽ không chạy. Spring Boot có thể auto-configure scheduler theo điều kiện cụ thể; đừng giả định mọi ứng dụng Boot mặc nhiên dùng pool size hoặc timezone như nhau.

## 13. Clock.systemUTC và zone business: chiến lược thực tế

Một thiết kế dễ lý giải là:

- **Clock chung của scheduler** có zone UTC (`Clock.systemUTC()`), tránh phụ thuộc timezone của container.
- Mỗi rule cron của business có **ZoneId explicit**, ví dụ `Asia/Ho_Chi_Minh`, `Europe/Berlin`, `America/New_York`.
- Tất cả planned/actual/completion timestamps lưu/log ở **Instant UTC**.
- UI chuyển từ Instant sang local datetime theo zone của user/tenant.
- Đối với thao tác “hôm nay của tenant”, dùng `LocalDate.now(clock.withZone(tenantZone))` hoặc chuyển từ Instant, chứ không dùng `LocalDate.now()` mặc định.
- Kiểm thử fixed clock và timezone boundary độc lập với scheduler thật.

Ví dụ chuyển từ business date/time sang Instant:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 1, 1);
LocalTime time = LocalTime.of(9, 0);

ZonedDateTime target = ZonedDateTime.of(date, time, zone);
Instant triggerAt = target.toInstant();
// triggerAt = 2026-01-01T02:00:00Z
~~~

**Snippet**, cần import các type `java.time`. Mỗi lịch có thể lưu `zoneId` để xử lý DST theo quy tắc tương ứng. Không lưu mỗi một offset hiện tại cho lịch “09:00 mỗi ngày” tại nơi có DST.

### Clock cho business code có nên là scheduler.getClock()?

Nếu muốn application nhất quán, có thể inject một `Clock` bean vào service tính “ngày hôm nay” và vào scheduler configuration. Tuy nhiên, ranh giới ownership cần rõ:

- Clock của scheduler quyết định những phép tính scheduling mà implementation sử dụng.
- Business clock có thể cùng nguồn nhưng **được inject tường minh** thay vì tự truy cập scheduler ở mọi service.
- Test có thể thay business clock trong unit test mà không cần đổi scheduler thật.
- Nếu hai clock khác nhau, phải có lý do rõ và log/metric phân biệt, tránh dùng business clock fixed trong production.

Ví dụ:

~~~java
@Bean
Clock appClock() {
    return Clock.systemUTC();
}

@Bean
ThreadPoolTaskScheduler taskScheduler(Clock appClock) {
    ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
    s.setClock(appClock);
    s.setPoolSize(2);
    return s;
}
~~~

Đây là **Spring configuration snippet** trong class `@Configuration`, chưa phải file độc lập. Các bean dùng clock chung trong production; test chọn fake business clock hoặc trực tiếp test trigger context, tùy mục đích.

## 14. Wall clock khác elapsed-time clock

**Wall clock** (`Clock.systemUTC()`, `Clock.systemDefaultZone()`, `Instant.now()`) dùng để gắn thời điểm vào lịch dân sự và timestamp có thể lưu. Nó có thể bị điều chỉnh bởi NTP, cấu hình hệ thống, môi trường ảo hoặc thao tác quản trị. Vì vậy, hai lần đọc wall clock có thể cách nhau không đúng số nanosecond đã trôi.

**Elapsed-time / monotonic source** như `System.nanoTime()` dùng để so sánh khoảng thời gian trong JVM. Số trả về không phải “nanos kể từ 1970” và không thể đem sang process khác so sánh thành một timestamp.

### 14.1. Đừng dùng Clock để tự đo thời lượng chính xác

Không nên tính elapsed runtime nhạy cảm bằng:

~~~java
long startMs = System.currentTimeMillis();
doWork();
long elapsedMs = System.currentTimeMillis() - startMs;
~~~

Snippet này có thể bị ảnh hưởng khi đồng hồ hệ thống được chỉnh trong lúc làm việc. Nên đo chênh thời gian bằng `System.nanoTime()` khi phù hợp, hoặc Micrometer `Timer`/metric library dùng clock/monotonic mechanism của nó.

### 14.2. JDK scheduled executor sử dụng cơ chế trì hoãn tương đối

`ScheduledThreadPoolExecutor` của JDK sử dụng delayed tasks, tính toán theo bộ đếm elapsed-time thích hợp cho timeouts/delays (ví dụ `System.nanoTime` bên dưới). Việc thiết lập Spring `Clock` cho scheduler có thể ảnh hưởng cách chọn/so sánh **Instant lúc tạo lịch**, nhưng không đồng nghĩa thay đổi cơ chế thời gian của queue executor thành một “đồng hồ có thể điều khiển” bằng `Clock.fixed`.

Hệ quả vận hành: nếu hệ điều hành nhảy giờ, one-shot đã được chuyển thành delay và trigger phải tính lần kế tiếp **có thể phản ứng khác nhau**. Đừng suy đoán một chính sách catch-up/skip chung cho tất cả implementation; hãy test trên loại scheduler đang dùng.

## 15. CronTrigger: lenient và fixed execution

Một khái niệm không trực tiếp nằm trong `Clock` nhưng quan trọng khi hỏi “thời gian sử dụng” là **mốc làm căn cứ cho lần tiếp theo**.

Với Spring 6.2.x, `CronTrigger` thông thường dùng semantics **lenient execution**: lần kế tiếp có thể dựa trên thời điểm **completion** của lần trước, vì thế những mốc cron bị lỡ trong khi task còn chạy có thể bị bỏ qua.

Spring cũng có `CronTrigger.forFixedExecution(expression)` (khả dụng trong Spring 6.1.3+) để tính theo thời điểm **scheduled** của lần trước, nhằm xử lý các mốc cron đã lỡ theo chính sách fixed execution. Cả hai đều cần xem xét trường hợp process down, pool bão hòa và yêu cầu chạy bù:

~~~java
CronTrigger lenient =
        new CronTrigger("0 */5 * * * *");

CronTrigger fixed =
        CronTrigger.forFixedExecution("0 */5 * * * *");
~~~

Đây là **snippet**. Hai trigger có thể cho các chuỗi `nextExecution` khác nhau khi một job mất nhiều thời gian. Đây **không** có nghĩa một Spring scheduler in-memory trở thành job store bền vững sau restart.

### 15.1. Phân biệt “skip một tick” và “đảm bảo không mất job”

Một báo cáo cần chạy **mỗi 5 phút** có thể chấp nhận skip nếu hệ thống bận. Một nghiệp vụ tính cước cần xử lý **mỗi billing period** không thể chỉ dựa vào cron fire count. Nên lưu business key theo kỳ, trạng thái xử lý và idempotency trong DB/job store, để recovery/backfill có thể kiểm tra.

### 15.2. Clock giả không tự quyết định catch-up

Dù thay clock, một trigger vẫn cần **execution context/history** và policy. `Clock.fixed` giúp bạn test lúc “now” nhưng không tự tạo record `lastCompletion` hay replay lần chạy chưa diễn ra. Unit test cần cung cấp `SimpleTriggerContext.update(lastScheduled, lastActual, lastCompletion)` khi test mốc lịch sử.

## 16. Test TriggerContext với lịch sử thời gian

Giả sử đã có:

~~~text
lastScheduled = 2026-01-01T02:00:00Z
lastActual    = 2026-01-01T02:02:00Z
lastComplete  = 2026-01-01T02:04:00Z
~~~

Các mốc lần trước khác nhau vì pool trễ 2 phút và task chạy thêm 2 phút. Khi test, cần làm rõ trigger dựa vào **lastScheduled** hay **lastCompletion**.

Ví dụ `SimpleTriggerContext`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T02:10:00Z"),
        ZoneId.of("UTC"));

SimpleTriggerContext c = new SimpleTriggerContext(fixed);
c.update(
        Instant.parse("2026-01-01T02:00:00Z"),
        Instant.parse("2026-01-01T02:02:00Z"),
        Instant.parse("2026-01-01T02:04:00Z"));

System.out.println(c.lastScheduledExecution());
System.out.println(c.lastActualExecution());
System.out.println(c.lastCompletion());
~~~

Đây là **snippet**, cần imports `Clock`, `Instant`, `ZoneId` và `SimpleTriggerContext`. Ba dòng in chính là ba `Instant` ở trên, không phụ thuộc vào clock thật.

Nếu test `CronTrigger.forFixedExecution` với `lastScheduled`, có thể xuất hiện next instant trước thời điểm clock hiện tại, nhằm xử lý những lần schedule bị lỡ; không nhất thiết đồng nghĩa task sẽ chạy “đúng giờ trong quá khứ”. Scheduler thật phải quyết định cách thực hiện các mốc đã qua.

## 17. Giờ mùa hè (DST): kiểm thử theo từng quy tắc local time

Thử suy luận về một cron chạy lúc 02:30 địa phương mỗi ngày tại New York. Ngày Spring DST bắt đầu có thể không tồn tại 02:30. Một ví dụ Java 17 kiểm tra **tính hợp lệ của local time**:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime nonexistent =
        LocalDateTime.of(2026, 3, 8, 2, 30);

int offsets =
        ny.getRules().getValidOffsets(nonexistent).size();

System.out.println("valid offsets = " + offsets);
~~~

Đây là **snippet**. Với timezone database hiện hành phù hợp lịch chuyển DST tại New York ngày 2026-03-08, output là:

~~~text
valid offsets = 0
~~~

Điều đó chứng minh **02:30 là một local time không hợp lệ** trong ngày gap; không tự nói cho ta `CronTrigger` sẽ bỏ qua, chuyển sang 03:30 hay thực hiện lịch theo policy khác. Để xác nhận behavior của cron trong version bạn triển khai, test `nextExecution` trên fixed context quanh transition.

Trong ngày DST kết thúc có thể có **2 offset hợp lệ** cho một local time trong khoảng overlap. Nếu yêu cầu của doanh nghiệp là “chạy tối đa một lần cho mỗi ngày địa phương”, cần dedup bằng `(tenantId, businessDate, jobType)` hoặc key tương đương bất kể scheduler có phát ra một hay hai lần.

### 17.1. Đừng tính “ngày kế tiếp” bằng 24 giờ nếu là calendar schedule

~~~java
Instant next = previous.plus(Duration.ofHours(24));
~~~

**Snippet** trên có ý nghĩa “sau đúng 24 giờ elapsed”, không luôn là “09:00 ngày mai ở local timezone”. Với calendar rule, chuyển sang `ZonedDateTime` theo `ZoneId`, điều chỉnh ngày theo lịch và test DST.

### 17.2. ZoneId và ZoneOffset

- `ZoneId.of("Europe/Berlin")`: quy tắc thời gian theo Berlin, có DST trong nhiều giai đoạn.
- `ZoneOffset.of("+01:00")`: offset cố định, không tự chuyển thành +02:00 vào mùa hè.
- `ZoneId.of("Asia/Ho_Chi_Minh")`: tên vùng theo timezone database, giúp diễn giải lịch sử/quy tắc phù hợp; khác khái niệm một chuỗi cố định `"+07:00"` về mặt biểu diễn và khả năng xử lý quy tắc theo vùng.

## 18. Đồng hồ thay đổi giữa các lần tính: những gì được và không được cam kết

### 18.1. Thay Clock sau khi scheduler đã hoạt động

`ThreadPoolTaskScheduler#setClock(...)` là cấu hình Spring cho scheduler. Tuy nhiên, không nên tự cập nhật clock ở runtime để “chuyển timezone một job” mà chưa đánh giá tasks đang pending, cách tính delay, trigger context đã tạo và các cấu hình `@Scheduled`. Đặt một zone explicit cho mỗi cron hoặc tái cấu hình job qua lifecycle được quản lý sẽ dễ dự đoán hơn.

### 18.2. Thay zone không thay Instant

`clock.withZone(otherZone)` không thay thời điểm thật được trả bởi `Clock.fixed`; với các hệ thống clock dùng cùng nguồn, zone mới thay cách diễn giải lịch địa phương. Nhưng nếu bạn gọi `LocalDate.now(clock)` hoặc một cron không chỉ định zone, kết quả **có thể thay đổi**.

### 18.3. Thay giờ hệ thống không đồng nghĩa thay duration đang đợi

Nếu một delayed job đã được enqueue bằng relative delay, việc chỉnh wall-clock về quá khứ không nhất thiết khiến job phải đợi lâu thêm bằng đúng mức điều chỉnh. Ngược lại, một cron sẽ tính các lần tiếp theo từ clock/zone và lịch sử trigger; hành vi có thể thay đổi ở lần tính kế tiếp.

### 18.4. Không lấy thời điểm thực thi là bảo đảm SLA

`schedule(job, startTime)` diễn đạt **thời điểm dự định**, không phải một hard real-time guarantee. Lúc task bắt đầu thực phụ thuộc:

- Worker có sẵn hay bận.
- Queue/delayed tasks và chính sách prioritization.
- CPU/GC pause, I/O, lock và scheduler overhead.
- OS scheduling, virtualization, shutdown/pause.
- Lỗi trong task hoặc error handler.
- Clock synchronization và thay đổi wall time.

Cần thiết kế “làm gì nếu muộn 2 phút?” thành business policy, không chỉ dựa vào cron expression.

## 19. Tính thời gian trễ lịch và độ dài task

Có ba timestamp thường hữu ích:

~~~text
plannedAt   = lastScheduledExecution
startedAt   = lastActualExecution
finishedAt  = lastCompletion

scheduleLag = startedAt - plannedAt
taskDuration = finishedAt - startedAt
~~~

Ở lớp observability, nên lưu `plannedAt`, `startedAt`, `finishedAt` dưới dạng `Instant`, và dùng monotonic timer cho thời lượng thực thi khi cần chính xác. Nếu mốc đo bằng các clock không đồng bộ giữa các máy, chênh lệch có thể sai; cùng JVM và clock nhất quán dễ lý giải hơn.

Ví dụ:

~~~text
plannedAt  = 09:00:00
startedAt  = 09:00:03
finishedAt = 09:00:07

schedule lag = 3 seconds
run duration = 4 seconds
~~~

Khi theo dõi CronTrigger, **mốc dự định và thực tế** có thể khác nhau; chỉ log “job started 09:00:03” không đủ để biết nó trễ bao nhiêu. Cần giữ planned time trong metadata/callback hoặc đo thông qua `TriggerContext`/scheduler instrumentation phù hợp.

### Metrics nên có

| Metric | Diễn giải |
| --- | --- |
| `scheduler_trigger_lag_seconds` | Thời gian từ planned đến actual |
| `scheduler_run_duration_seconds` | Thời lượng task thực thi |
| `scheduler_execution_errors_total` | Tổng lần task thất bại |
| `scheduler_missed_or_skipped_total` | Mốc bị bỏ/lỡ theo quy tắc business |
| `scheduler_queue_wait_seconds` | Thời gian chờ worker/queue nếu đo được |
| `scheduler_active_threads` | Mức sử dụng worker của scheduler |
| `job_business_date`/job key | Có xử lý trùng/mất một kỳ nghiệp vụ không |

Tránh gắn label chứa jobId ngẫu nhiên/userId cho từng metric Prometheus khi cardinality quá lớn. Lưu chi tiết ID trong logs/traces/job store, metrics dùng label có giới hạn.

## 20. Tác động của pool size, lỗi và lifecycle

### 20.1. Clock đúng nhưng scheduler pool vẫn có thể nghẽn

`ThreadPoolTaskScheduler` dựa trên scheduled thread pool. Pool size mặc định thường là 1 nếu không cấu hình khác. Với task chạy lâu, các trigger khác có thể trễ dù `Clock` và cron đúng.

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
    s.setPoolSize(4);
    s.setClock(Clock.systemUTC());
    s.setThreadNamePrefix("scheduled-");
    return s;
}
~~~

**Snippet Spring configuration**. `setPoolSize(4)` cho tối đa số scheduler threads theo cấu hình đó; không tạo guarantee 4 job/giây hoặc exactly-once.

### 20.2. Task thất bại

Trong lịch periodic, một exception không được xử lý có thể ảnh hưởng các lần thực thi sau tùy implementation/error handler. `ThreadPoolTaskScheduler#setErrorHandler(...)` cho phép cấu hình chiến lược xử lý exception; phải log có job key và phân loại nghiệp vụ, không chỉ dựa vào thời gian sẽ chữa lỗi.

Không coi lỗi periodic task là lý do để tự retry vô hạn ngay trong scheduler thread. Nếu cần retry, đặt budget, backoff và idempotency rõ ràng; cron tick và retry của cùng kỳ nghiệp vụ có thể trùng nhau.

### 20.3. Cancellation và shutdown

`ScheduledFuture.cancel(...)` thay đổi lịch đã được lên, nhưng không đảm bảo task I/O đang chạy ngừng ngay hoặc rollback side effect đã tạo. Cấu hình executor cần có shutdown policy, quản lý queue và cơ chế graceful shutdown khi context đóng.

Nếu ứng dụng cần lưu ý định scheduling qua deploy/restart, một Spring scheduler in-memory không đủ làm durable scheduler; phải persist job plans / state hoặc dùng giải pháp phù hợp. Clock đúng không thay thế persistence.

### 20.4. Clock giả trên live scheduler và resource leak

Không tạo mỗi request một `ThreadPoolTaskScheduler` mới chỉ để có clock theo user. Dùng một scheduler được container quản lý và mỗi job mang zone/trigger rõ ràng; tạo nhiều scheduler per request có thể tăng thread count và khiến shutdown phức tạp.

## 21. Nhiều instance/pod: clock thống nhất chưa có nghĩa job chỉ chạy một lần

Giả sử service có **3 replicas**, mỗi replica đều bật:

~~~java
@Scheduled(cron = "0 0 9 * * *", zone = "Asia/Ho_Chi_Minh")
public void chargeDaily() {
    processBilling();
}
~~~

Đây là **Spring snippet**.

Kết quả có thể là **3 job invocation** ở thời điểm 09:00 nếu cả ba replica đều chạy scheduler riêng. Việc cấu hình `Clock.systemUTC()` đồng nhất không giải quyết duplicate. Khi job có side effect:

- Dùng leader election/distributed coordination khi cần một worker active.
- Dùng durable job store với claim atomic, lease/fencing token và recovery khi node chết.
- Thiết kế idempotency theo business key (ví dụ tenant + ngày tính phí + loại tác vụ) để duplicate không gây phát hành hóa đơn lần hai.
- Quan sát clock skew giữa các pod và external store.
- Không dựa chỉ vào một distributed lock có TTL mà quên trường hợp worker cũ vẫn chạy sau khi lease hết.

**Clock đồng nhất giúp diễn giải lịch giống nhau; cơ chế ownership mới quyết định ai được phép thực thi side effect.**

## 22. Kiểm thử scheduler đúng lớp

### 22.1. Unit test pure time conversion

Với `Clock.fixed`, assert:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

assertEquals(
        Instant.parse("2026-01-01T00:00:00Z"),
        fixed.instant());

assertEquals(
        LocalDate.of(2026, 1, 1),
        LocalDate.now(fixed));
~~~

Đây là **JUnit 5 snippet**, cần import JUnit assertions và các type `java.time`. Không cần scheduler hay thread.

### 22.2. Unit test CronTrigger bằng fixed SimpleTriggerContext

~~~java
SimpleTriggerContext ctx =
        new SimpleTriggerContext(Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")));

Instant next = new CronTrigger("0 0 9 * * *")
        .nextExecution(ctx);

assertEquals(
        Instant.parse("2026-01-01T02:00:00Z"),
        next);
~~~

Đây là **Spring + JUnit 5 snippet**, không tạo task chạy thật. Test nên thêm `CronTrigger` có explicit zone UTC, ngày cuối tháng, DST gap/overlap và trigger context có lịch sử.

### 22.3. Test scheduled execution thật bằng Future hoặc CountDownLatch

~~~java
ScheduledFuture<?> done = scheduler.schedule(
        () -> doSmallWork(),
        scheduler.getClock().instant().minusSeconds(1));

done.get(5, TimeUnit.SECONDS);
assertTrue(done.isDone());
~~~

Đây là **snippet integration test** với scheduler đã chạy và `doSmallWork` deterministic. Không sleep một khoảng rồi đoán task chắc đã chạy. Timeout đủ lớn là guard, không phải phần xác định logic.

### 22.4. Không dùng Clock.fixed như một test scheduler điều khiển queue

Một bài test kiểu “setClock(fixed), schedule(job, now+1h), advance Clock.offset(fixed,+1h), assert job ran” là sai: `Clock.offset` tạo **một object Clock khác**, không tự cập nhật clock của executor hoặc kéo dài/thu ngắn queue deadline đã tính trước.

Muốn test scheduling với **virtual time**, dùng scheduler/test harness được thiết kế cho việc advance thời gian, hoặc tách `Trigger.nextExecution` thành pure function kiểm thử độc lập. Với Spring `TaskScheduler` trên JDK scheduled executor thật, phải chờ sự kiện thực tế hoặc thử một mốc đã qua.

### 22.5. Test môi trường timezone khác nhau

Chạy test trong JVM default timezone khác nhau (ví dụ UTC và Asia/Ho_Chi_Minh) để xác minh những business cron có `ZoneId` explicit không đổi ý nghĩa. Đừng chỉ test trên laptop developer rồi triển khai lên container UTC và bất ngờ lệch 7 tiếng.

### 22.6. Kiểm thử độ trễ và capacity

Dùng pool nhỏ để tạo contention có kiểm soát; đo `actual - planned`. Kiểm tra task dài hơn period, shutdown, pause/resume, exception, cancellation, missed fires và multiple instances. Không dùng độ chính xác 1 ms làm assertion cứng trong CI khi mục tiêu là test logic ngày/giờ.

## 23. Lỗi phổ biến cần tránh

**Lỗi 1 — “Clock của scheduler là một cái đồng hồ ảo để chạy task tùy ý.”** Sai. `Clock` chỉ cung cấp “now/zone”; thread pool và delayed queue có cơ chế thực thi riêng.

**Lỗi 2 — “Đổi Clock.fixed rồi tick thêm một giờ là cron tự nổ.”** Sai. Fixed clock không tự tiến và việc tạo Clock.offset không điều khiển executor đã schedule.

**Lỗi 3 — “Instant.parse(...Z) là 09:00 giờ Việt Nam nếu ghi 09:00Z.”** Sai. 09:00Z là 16:00 tại Việt Nam ở ví dụ UTC+7; cần chuyển local time/zone thành Instant đúng.

**Lỗi 4 — “LocalDateTime đã là thời điểm tuyệt đối.”** Sai. Nó chưa có timezone.

**Lỗi 5 — “ZoneOffset là ZoneId có DST.”** Sai. Offset cố định khác vùng quy tắc IANA.

**Lỗi 6 — “Cron 09:00 luôn là 09:00 địa phương của người dùng.”** Sai nếu không đặt `zone`/`ZoneId` theo business rule.

**Lỗi 7 — “Clock.systemUTC và Clock.systemDefaultZone khác nhau về thời gian thực đang trôi.”** Thông thường chúng cùng nguồn giờ thực, khác timezone dùng để diễn giải lịch. Đừng nhầm đổi zone với dịch Instant.

**Lỗi 8 — “Fixed rate 24 giờ = 09:00 mỗi ngày bất chấp DST.”** Sai ở zone có DST và với yêu cầu ngày lịch.

**Lỗi 9 — “Fixed delay đo từ lúc bắt đầu.”** Sai: fixed delay đo từ **completion** của execution trước.

**Lỗi 10 — “Fixed rate có nghĩa mọi lần thực thi bắt đầu đúng một giây tuyệt đối.”** Sai khi pool bận, task chậm hoặc OS scheduling trễ.

**Lỗi 11 — “CronTrigger chỉ cần biểu thức là biết timezone.”** Sai khi không có context/explicit zone; múi giờ của scheduler/clock quan trọng.

**Lỗi 12 — “Nếu schedule() nhận quá khứ, nó sẽ bỏ job.”** Không theo Javadoc Spring cho one-shot Instant: task được chạy càng sớm càng tốt.

**Lỗi 13 — “Đo elapsed runtime bằng System.currentTimeMillis chắc chắn chính xác.”** Sai khi wall-clock bị chỉnh; dùng monotonic source cho chênh lệch thời gian.

**Lỗi 14 — “NanoTime là Unix timestamp nanosecond.”** Sai. Nó chỉ thích hợp so sánh chênh lệch trong JVM.

**Lỗi 15 — “Một scheduler bean đảm bảo cron chỉ chạy một lần trên cluster.”** Sai. Mỗi instance thường có scheduler riêng, cần coordination/idempotency.

**Lỗi 16 — “@Scheduled return xong nghĩa đã chắc chắn ghi nghiệp vụ bền.”** Không nếu task spawn fire-and-forget, DB transaction/queue chưa commit hoặc process crash.

**Lỗi 17 — “TaskScheduler clock của mọi implementation giống nhau.”** Không có gì bảo đảm mọi adapter/custom scheduler có cùng behavior; kiểm tra đúng class/version.

**Lỗi 18 — “Chuyển Clock sang UTC sẽ tự sửa mọi cron.”** Không nếu các CronTrigger đã chỉ định timezone riêng hoặc business code tự dùng system default time.

**Lỗi 19 — “Mỗi CronTrigger đều replay tất cả mốc bỏ lỡ.”** Không. Lenient/fixed execution và restart persistence là những vấn đề riêng.

**Lỗi 20 — “Có Clock.fixed thì không cần cleanup scheduler trong test.”** Sai. Nếu test tạo `ThreadPoolTaskScheduler` thật, vẫn phải shutdown/đóng context.

## 24. Bài tập tự kiểm tra

**Câu 1.** `Clock.fixed(2026-01-01T00:00:00Z, Asia/Ho_Chi_Minh)` thì `LocalTime.now(clock)` là mấy giờ?

**Đáp án:** 07:00, vì Việt Nam UTC+7 tại thời điểm nêu. `clock.instant()` vẫn là 00:00Z.

**Câu 2.** Cron `"0 0 9 * * *"` với `SimpleTriggerContext` dùng clock trên sẽ cho lần đầu là Instant nào?

**Đáp án:** 2026-01-01T02:00:00Z. Local 09:00 HCM = UTC 02:00.

**Câu 3.** Nếu vẫn cùng clock nhưng CronTrigger được tạo với `ZoneId.of("UTC")` thì kết quả?

**Đáp án:** 2026-01-01T09:00:00Z. Explicit zone của trigger được ưu tiên khi tính cron.

**Câu 4.** `scheduleAtFixedRate(job, Duration.ofHours(24))` có tương đương “09:00 sáng theo giờ New York mỗi ngày” không?

**Đáp án:** không. Fixed rate lặp theo 24 giờ elapsed, còn business cron 09:00 phụ thuộc calendar/DST.

**Câu 5.** `ThreadPoolTaskScheduler#setClock(Clock.fixed(...))` có làm một delayed queue tự chạy sau khi test tạo một `Clock.offset(...)` mới không?

**Đáp án:** không. Clock không kiểm soát virtual-time advancement của underlying executor. Test trigger calculation riêng, hoặc dùng test scheduler có virtual time thật.

**Câu 6.** Một task dự kiến 09:00, thực bắt đầu 09:02 và kết thúc 09:04. Ba giá trị trong `TriggerContext` là gì?

**Đáp án:** `lastScheduledExecution≈09:00`, `lastActualExecution≈09:02`, `lastCompletion≈09:04`, nếu đó là một lần execution đã được ghi nhận đầy đủ.

**Câu 7.** Cron của một job được khai báo trên ba pod cùng zone. Lúc 09:00 có chắc chỉ một lần business effect không?

**Đáp án:** không. Các pod có thể cùng chạy; cần claim/leader/idempotency theo business key.

**Câu 8.** Vì sao không đo job duration bằng `Instant.now()` nếu cần elapsed chính xác?

**Đáp án:** wall-clock có thể bị chỉnh; dùng `System.nanoTime()` hoặc Timer phù hợp để đo elapsed trong JVM.

**Câu 9.** `@Scheduled(cron="0 0 9 * * *", zone="Asia/Ho_Chi_Minh")` chạy trên server UTC có bị đổi thành 09:00 UTC không?

**Đáp án:** không, zone đã được chỉ định cho cron. 09:00 Việt Nam ở ví dụ chuyển thành 02:00 UTC.

**Câu 10.** Một scheduler đặt one-shot task vào một `Instant` đã quá khứ. Điều gì xảy ra?

**Đáp án:** theo Spring `TaskScheduler`, task được thực thi sớm nhất có thể thay vì chạy ngược thời gian. Vẫn phụ thuộc worker và tình trạng hệ thống.

## 25. Checklist trước khi triển khai

- [ ] Phân biệt timestamp tuyệt đối (`Instant`), calendar local time (`LocalDateTime + ZoneId`), relative duration (`Duration`).
- [ ] Xác định `TaskScheduler` implementation và giá trị `getClock()` thực tế.
- [ ] Với lịch business địa phương, dùng `ZoneId` explicit, không dựa vào timezone máy chủ.
- [ ] Cron có 6 trường đúng cú pháp Spring, trong đó trường đầu là giây.
- [ ] Với DST zone, đã định nghĩa xử lý gap/overlap và dedup theo kỳ nghiệp vụ.
- [ ] Fixed rate/delay đã được chọn theo ý nghĩa thời gian, không nhầm chúng là cron.
- [ ] Clock inject cho tính toán, test bằng `Clock.fixed`/`SimpleTriggerContext` khi cần tính lịch.
- [ ] Không kỳ vọng `Clock.fixed` tự tiến hoặc điều khiển delayed queue của scheduler thật.
- [ ] Có deadline và timeout theo nghiệp vụ; chấp nhận scheduler không hard real-time.
- [ ] Đo schedule lag và runtime, dùng monotonic source cho elapsed duration.
- [ ] Pool size, error handler, cancellation và shutdown được cấu hình rõ.
- [ ] Không đánh đồng Clock config với đảm bảo exactly-once toàn cụm.
- [ ] Có quy trình backfill/recovery khi restart hoặc missed firings.
- [ ] Kết quả unit test không phụ thuộc giờ hiện tại, timezone của laptop, `Thread.sleep` hay lịch cron phải chạy thật.
- [ ] Integration test có future/latch và timeout, luôn dọn scheduler bean/executor sau test.
- [ ] Logs/metrics lưu planned/actual/completion timestamps rõ ràng, không dùng `nanoTime` làm Unix timestamp.

## 26. Tổng kết

**`Clock` trả lời “bây giờ là khi nào, trong timezone nào?”; `TaskScheduler` quyết định “task nào sẽ được đặt lịch và thực thi ở mốc nào?”.** Một `Instant` là timestamp tuyệt đối; một `Duration` là khoảng thời gian; `ZoneId` xác định cách diễn giải lịch dân sự. `TriggerContext` mang clock và lịch sử lần chạy để `CronTrigger` tính mốc tiếp theo.

Với Spring 6.2.x, `ThreadPoolTaskScheduler` có `getClock()` và `setClock(Clock)`. Cấu hình clock UTC giúp tránh phụ thuộc timezone server cho các phép tính mặc định; đặt zone rõ cho cron theo địa phương là cách biểu đạt business rule chắc chắn hơn. Để test logic thời gian, dùng `Clock.fixed` và hỏi `CronTrigger.nextExecution(SimpleTriggerContext)`; **không** coi Clock là công tắc điều khiển queue thời gian ảo của executor.

Trong production, luôn xem cả task duration, worker capacity, DST, crash/restart, cluster duplication, idempotency và observability. **Đúng clock chưa đủ để job chạy đúng một lần, đúng hạn, đúng nghiệp vụ.**

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 Javadoc — `TaskScheduler`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework 6.2 Javadoc — `ThreadPoolTaskScheduler` (getClock/setClock): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
- Spring Framework 6.2 Javadoc — `TriggerContext`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TriggerContext.html
- Spring Framework 6.2 Javadoc — `CronTrigger`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html
- Spring Framework 6.2 Javadoc — `SimpleTriggerContext`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/SimpleTriggerContext.html
- Spring Framework 6.2 Javadoc — `@Scheduled`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Java SE 17 Javadoc — `Clock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java SE 17 Javadoc — `Instant`, `Duration`, `ZoneId`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html
- Java SE 17 Javadoc — `ScheduledThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
