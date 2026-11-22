# Clock, scheduler và kiểm thử tác vụ theo thời gian

Trong ứng dụng Spring Boot, nhiều hành vi chỉ đúng tại **một thời điểm cụ thể**: đơn hàng hết hạn sau 15 phút, token không còn hợp lệ khi chạm mốc expiry, báo cáo chạy lúc 09:00 theo múi giờ kinh doanh, tác vụ quét dữ liệu được kích hoạt mỗi phút, hoặc công việc không được xử lý hai lần dù hai scheduler cùng gọi. Các bài kiểm thử loại này thường khó ổn định khi chúng gọi thẳng `Instant.now()`, dùng `Thread.sleep(...)`, phụ thuộc vào giờ máy CI hoặc để `@Scheduled` tự chạy trong mọi `@SpringBootTest`.

Bài Knowledge này tập trung vào **Clock, scheduler và kiểm thử tác vụ theo thời gian**, thuộc nhóm **Bất đồng bộ và lịch chạy** của module **Spring Boot – testing**. Điểm quan trọng nhất là phân biệt **thời gian nghiệp vụ** với **thời điểm scheduler đánh thức công việc**. Ta có thể thay `java.time.Clock` để kiểm quyết định “đã đến hạn chưa?” một cách tức thì, nhưng **không thể giả định thay Clock bean sẽ khiến Spring @Scheduled tự nhảy tới tương lai**. Cách test bền vững là tách logic xử lý thành service có thể gọi trực tiếp, unit test bằng clock kiểm soát được, rồi dành một số ít integration/smoke tests có timeout hữu hạn cho scheduler thực.

Ví dụ dùng **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2.x, JUnit Jupiter 5, Spring Scheduling và Awaitility**. Project minh họa gồm một hàng đợi tác vụ *in-memory* để quan sát semantics; nó **không phải hệ thống scheduler phân tán hoặc persistence production**. Với dữ liệu thật, cần database/queue, transaction, idempotency và phối hợp nhiều replica phù hợp.

## 1. Mục tiêu học tập

- Hiểu khác nhau giữa `Instant`, `LocalDateTime`, `ZonedDateTime`, `ZoneId`, `Duration` và `Clock`.
- Biết inject `Clock` thay vì gọi `Instant.now()`/`LocalDateTime.now()` rải rác trong domain code.
- Sử dụng `Clock.fixed(...)`, `Clock.offset(...)` và mutable test clock để kiểm trước/đúng/sau deadline.
- Chọn đúng ranh giới so sánh `dueAt <= now` và kiểm “đúng giây”, “trước 1 nano giây” thay vì chờ.
- Phân biệt `fixedRate`, `fixedDelay`, `initialDelay` và cron sáu trường của Spring.
- Đặt `zone` cho cron và biết nguy cơ DST, múi giờ hệ điều hành, đồng hồ CI.
- Hiểu `@EnableScheduling`, `@Scheduled`, `TaskScheduler`, `ThreadPoolTaskScheduler` và `@Async` giải quyết những vấn đề khác nhau.
- Thiết kế task adapter mỏng để test service mà không kích hoạt lịch chạy thật.
- Tránh scheduler tự chạy ngoài ý muốn khi Spring TestContext cache hoặc các test classes chạy cùng suite.
- Viết test xác định thời gian bằng pure JUnit, test wiring `Clock` bằng `@SpringBootTest`, kiểm cron bằng `CronExpression`.
- Viết smoke test `@Scheduled` với **bounded eventual assertion** thay vì `Thread.sleep(...)`.
- Kiểm idempotency/concurrency khi hai lần kích hoạt cùng nhận một job đến hạn.
- Biết rủi ro scheduler chạy trên nhiều pods, retry sau crash, clock skew và side effects.
- Xác định đâu là **time simulation** và đâu là **real scheduler execution** trong báo cáo kết quả.

## 2. Hai loại đồng hồ không được đánh đồng

Có ít nhất hai “thời gian” đang hoạt động:

| Vai trò | Ví dụ | Quyết định gì? | Kiểm thử nên làm gì? |
|---|---|---|---|
| **Business clock** | `Clock` được inject vào service | Task đến hạn, token expired, thời gian hiệu lực | Dùng `Clock.fixed`/mutable clock, gọi service trực tiếp |
| **Scheduling clock / executor** | `TaskScheduler`, scheduled executor, container runtime | Khi nào thread được đánh thức để gọi method | Một vài smoke tests/controlled scheduler tests |
| **Monotonic elapsed time** | `System.nanoTime()`, timer metrics | Mất bao lâu cho thao tác | Đo duration, không làm timestamp nghiệp vụ |
| **External system clock** | DB server, Redis TTL, Kafka timestamp | Thời gian do backend kiểm soát | Test backend thực; Java Clock không điều khiển nó |
| **Distributed node clocks** | NTP/VM/pod time | Quan hệ thời gian giữa nhiều máy | Clock skew, lease, tolerance và monotonic guards |

**Ví dụ quan trọng:** Một bean `Clock.fixed(Instant.parse("2030-01-01T00:00:00Z"), UTC)` khiến `Instant.now(clock)` trả năm 2030. Nó **không mặc nhiên** khiến `@Scheduled(fixedRate=1000)` chạy nhanh hơn 1.000 lần hay tạo 30 năm các lần gọi lập lịch. `TaskScheduler` có phương thức `getClock()` riêng; `ThreadPoolTaskScheduler` có thể được cấu hình `setClock(...)`, nhưng một bean `Clock` độc lập không tự động thay thế scheduling clock của mọi executor.

### 2.1. Phân tích một luồng đúng

```text
Real wall-clock / Spring TaskScheduler
        |
        | @Scheduled mỗi 1 phút
        v
CleanupTick.tick()
        |
        | gọi method trực tiếp, không chứa business logic
        v
DueTaskService.processDue()
        |
        | Instant cutoff = injected Clock.instant()
        v
TaskStore.markDue(cutoff)
        |
        | mark task có dueAt <= cutoff, chưa completed
        v
side effect / persistence

Unit test chỉ cần gọi DueTaskService.processDue()
với Clock.fixed hoặc MutableClock.
Smoke test mới cần chờ scheduler gọi CleanupTick.tick().
```

Nhờ tách này, hàng chục kịch bản boundary thời gian có thể chạy trong vài mili giây mà không yêu cầu mỗi kịch bản phải đợi scheduler chạy thật.

## 3. Vì sao `Instant.now()` trực tiếp làm test flaky?

Một service:

```java
// PHẢN VÍ DỤ: kết quả phụ thuộc thời gian thực của máy.
public boolean expired(Instant expiresAt) {
    return !expiresAt.isAfter(Instant.now());
}
```

sẽ khó test ở mốc chính xác, đặc biệt nếu test tạo `expiresAt` từ một lần `now()` và service gọi `now()` lần khác. Dù cách nhau vài microseconds, “đúng deadline” và “trước deadline” có thể lẫn lộn.

Sửa:

```java
public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant expiresAt) {
        return !expiresAt.isAfter(clock.instant());
    }
}
```

Đây là snippet Java cần `java.time.Clock` và `Instant`, không phải file demo độc lập. Khi dùng `Clock.fixed`, cả test và service thấy cùng một instant. Muốn kiểm tương lai, thay Clock hoặc tiến mutable clock — **không ngủ**.

### 3.1. Chốt một `now` cho một lần xử lý

Khi xử lý 1.000 tasks, không nên gọi `clock.instant()` bên trong từng so sánh nếu quy tắc mong **một cutoff nhất quán**. Service nên lấy:

```java
Instant cutoff = clock.instant();
return store.markDue(cutoff);
```

Mọi task trong đợt được xét theo cùng thời điểm. Nếu cần thời gian khác nhau cho từng phần, hãy diễn đạt contract rõ và test được. Đây là một quyết định về business semantics, không chỉ tối ưu hiệu năng.

## 4. Chọn kiểu thời gian đúng cho nghiệp vụ

| Kiểu | Đại diện | Dùng cho |
|---|---|---|
| `Instant` | Điểm thời gian UTC trên timeline | Deadline, expiry, createdAt, event timestamp |
| `Duration` | Khoảng thời gian elapsed | TTL 15 phút, timeout, retry delay |
| `LocalDate` | Ngày lịch không có giờ/múi giờ | Ngày báo cáo, kỳ kế toán |
| `LocalDateTime` | Giờ địa phương **không kèm zone/offset** | Input giờ họp trước khi gắn business zone |
| `ZonedDateTime` | Giờ lịch với timezone rules | “09:00 mỗi ngày tại Hà Nội”, DST |
| `OffsetDateTime` | Timestamp kèm UTC offset | API/event serialization khi có offset |
| `ZoneId` | Time zone với lịch sử DST | Scheduling theo địa phương |
| `Clock` | Nguồn cung cấp `Instant`/`ZoneId` | Dependency inject cho domain time |

**Lưu Instant trong data store** khi đại diện một deadline tuyệt đối; chỉ chuyển sang ZonedDateTime để tính giờ lịch hoặc hiển thị. Đừng lưu `LocalDateTime` rồi mặc định “UTC hay Asia/Ho_Chi_Minh tùy máy chạy” — điều này dễ gây lỗi khi chuyển CI/cloud region.

**Hai bài toán khác nhau:**

- “15 phút từ lúc tạo”: `createdAt.plus(Duration.ofMinutes(15))`.
- “Mỗi ngày lúc 09:00 giờ Hà Nội”: tính theo `ZoneId.of("Asia/Ho_Chi_Minh")` hoặc cron có zone, không đồng nghĩa cộng 24 giờ nếu business zone có DST trong tương lai/địa điểm khác.

## 5. Ba loại Clock thực tế cho test

### 5.1. `Clock.systemUTC()`

Dùng cho production khi cần timestamp tuyệt đối trong app:

```java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

Điều này không khắc phục clock skew giữa nhiều nodes; nó chỉ cho một nguồn time có thể thay thế trong code Java.

### 5.2. `Clock.fixed(...)`

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-08T00:00:00Z"),
        ZoneOffset.UTC);

assertEquals(
        Instant.parse("2026-11-08T00:00:00Z"),
        fixed.instant());
```

Đây là snippet với imports `Clock`, `Instant`, `ZoneOffset` và `assertEquals`. Đọc `fixed.instant()` bao nhiêu lần cũng cho cùng giá trị. Hữu ích cho expiry, boundary, timezone serialization và các phép tính nghiệp vụ.

### 5.3. `Clock.offset(...)`

```java
Clock future = Clock.offset(
        fixed, Duration.ofHours(2));
```

Tạo một góc nhìn offset so với clock gốc. Nếu clock gốc là fixed thì future cũng không trôi. Nếu clock gốc là system clock, future vẫn trôi theo hệ thống với độ lệch đã cho.

### 5.4. Mutable test Clock

Trong test cần mô phỏng các mốc “trước → đúng → sau”, một `MutableClock` nhỏ dùng `AtomicReference<Instant>` giúp thay giờ mà không chờ. Test helper của project ở mục 22 đảm bảo `withZone(...)` chia sẻ cùng instant state, không vô tình tạo một timeline khác.

**Không đưa MutableClock vào production** chỉ vì tiện test. Business code nên phụ thuộc interface chuẩn `Clock`, test quản lý loại clock thay thế.

## 6. Ranh giới đúng hạn: `isAfter`, `isBefore` và `equals`

Nếu task phải được xử lý khi **`now >= dueAt`**, hãy dùng:

```java
boolean due = !dueAt.isAfter(now);
```

Bảng chân trị:

| `now` | `dueAt` | `now >= dueAt`? |
|---|---|---:|
| 09:59:59.999999999 | 10:00:00 | Không |
| 10:00:00.000000000 | 10:00:00 | Có |
| 10:00:00.000000001 | 10:00:00 | Có |

**Đừng test bằng cách ngủ đến gần 10 giờ thật.** Đặt Clock tại 09:59:59.999999999 rồi advance một nano giây. Test các trường hợp “đúng ranh giới” có khả năng bắt off-by-one mà test chỉ dùng timestamps cách nhau vài phút có thể bỏ sót.

Nếu business contract dùng `now > dueAt` (quá hạn *sau* thời điểm), thay logic/test tương ứng. **Không âm thầm đổi dấu so sánh để làm test xanh.**

## 7. Tại sao `Thread.sleep` gần như luôn là phương án test yếu?

```java
// PHẢN VÍ DỤ: chờ 1 giây rồi hi vọng @Scheduled đã chạy.
Thread.sleep(1000);
assertTrue(taskCompleted);
```

Lệnh này không có bằng chứng scheduler thực sự đã chạy. CI có thể bận, GC pause kéo dài, Docker chậm, thread pool có backlog hoặc method ném exception. Ngược lại, thời gian chờ 1 giây cho mỗi test làm cả suite rất chậm.

**Chọn theo loại test:**

- Business deadline: **Clock.fixed/MutableClock**, không ngủ.
- Async completion: **Awaitility** với condition + timeout hữu hạn.
- Kích hoạt một lần: **CountDownLatch** và `await(timeout)`.
- Reactive virtual time: `StepVerifier.withVirtualTime` cho những publishers dùng Reactor schedulers thích hợp, **không** tự điều khiển Spring `@Scheduled`.
- Long-running scheduling semantics: một số ít end-to-end tests hoặc controlled scheduler test riêng.

Mục tiêu của timeout hữu hạn là có **failure diagnostic** khi job không chạy, không phải xóa mọi yếu tố thời gian khỏi smoke test.

## 8. Spring Scheduling: bật `@EnableScheduling` có ý nghĩa gì?

Spring xử lý `@Scheduled` khi annotation processing cho scheduling được bật, thường với `@EnableScheduling`:

```java
@SpringBootApplication
@EnableScheduling
public class SchedulerLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                SchedulerLessonApplication.class, args);
    }
}
```

Đây là file thật trong ví dụ ở mục 17. Khi `@EnableScheduling` có mặt, Spring tìm các beans có `@Scheduled` và đăng ký những tasks tương ứng. **Không phải cứ có annotation @Scheduled trong classpath là task tự chạy nếu scheduling chưa bật đúng trong context.**

### 8.1. Vì sao test bị nhiễu?

Một `@SpringBootTest` dựng context đầy đủ có thể khởi động scheduling infrastructure. Nếu scheduled bean hoạt động trong test, nó có thể:

- Xóa rows mà test khác chưa assert.
- Gửi email/message thật nếu dùng wrong profile.
- Cập nhật cache hoặc in logs trong lúc test chạy.
- Gây race khó tái hiện do timing khác nhau giữa local/CI.
- Tồn tại trong cached ApplicationContext và tiếp tục chạy giữa các test methods/classes.

**Giải pháp demo:** Tách scheduled adapter thành bean chỉ tồn tại khi property `demo.cleanup.enabled=true`; mặc định **false**. Các tests nghiệp vụ không cần scheduler thì giữ false. Chỉ một smoke test riêng mới bật true và đặt interval ngắn.

Trong hệ thống thật, scheduler enablement phải theo môi trường và policy rõ ràng; “test mặc định tắt job” không có nghĩa quên kiểm scheduler wiring.

## 9. `fixedDelay`, `fixedRate` và `initialDelay`

| Cấu hình | Định nghĩa | Phù hợp | Bẫy |
|---|---|---|---|
| `fixedDelay` | Khoảng trễ tính từ **khi lần trước kết thúc** tới khi lần sau bắt đầu | Polling/cleanup, ít overlap trong cùng task | Chạy lâu làm giảm nhịp |
| `fixedRate` | Nhịp định kỳ theo **thời điểm bắt đầu dự kiến** | Sampling/heartbeat có yêu cầu nhịp | Khi quá tải có thể trễ/backlog; không bảo đảm real-time |
| `initialDelay` | Chờ trước lần thực thi đầu của fixedDelay/fixedRate | Cho app warm-up | Không áp dụng như “delay mọi lần” |
| `cron` | Tính lần kế theo lịch calendar | Báo cáo 09:00, ban đêm | Zone/DST/calendar semantics |
| `TaskScheduler.schedule(task, Instant)` | Chạy một task gần thời điểm đã cho | Tác vụ one-shot trong một JVM | Restart/crash có thể mất task |

Ví dụ:

```java
@Scheduled(fixedDelay = 5, timeUnit = TimeUnit.SECONDS)
public void pollAfterCompletion() { /* ... */ }

@Scheduled(fixedRate = 10, timeUnit = TimeUnit.SECONDS)
public void sampleEveryTenSeconds() { /* ... */ }
```

Snippets cần `Scheduled` và `TimeUnit`, không phải file runnable độc lập.

**Không hiểu fixedRate = “chắc chắn có một execution đúng mỗi 10 giây”.** OS scheduling, CPU, GC, execution time, queue và thread pool có thể khiến job trễ. Nếu method có `@Async`, một số biến thể còn chạy overlap, nên phải có business idempotency/locking.

## 10. `@Scheduled` trong Spring 6.2: chu kỳ, property và scheduler qualifier

Bài demo dùng:

```java
@Scheduled(
    fixedDelayString = "${demo.cleanup.fixed-delay-ms:60000}",
    initialDelayString = "${demo.cleanup.initial-delay-ms:1000}",
    timeUnit = TimeUnit.MILLISECONDS)
public void tick() {
    service.processDue();
}
```

Nhờ placeholders, test có thể đặt `100` milliseconds mà production giữ 60.000 milliseconds nếu bật scheduling. Trong Spring 6.2, `@Scheduled.timeUnit` áp dụng cho fixed delay/rate/initial delay và hỗ trợ values parse theo duration formats; **cron không dùng timeUnit**.

Spring `@Scheduled.scheduler` có thể chỉ định qualifier hoặc bean name của `TaskScheduler`/`ScheduledExecutorService` khi ứng dụng có nhiều scheduler. Đừng tạo hai beans rồi giả định Spring chọn đúng bằng thứ tự component scan.

Lưu ý Spring `@Scheduled` method thường không nhận arguments; return value bình thường không phải kết quả để JUnit assert trực tiếp. Đưa logic vào service method trả kết quả là cách dễ test hơn.

## 11. Cron sáu trường và múi giờ

Cron expression Spring dạng:

```text
second minute hour day-of-month month day-of-week
0      0      9    *            *     MON-FRI
```

Ví dụ:

```java
@Scheduled(
    cron = "0 0 9 * * MON-FRI",
    zone = "Asia/Ho_Chi_Minh")
public void weekdayReport() { /* ... */ }
```

Ý nghĩa: chạy 09:00 vào thứ Hai–Sáu theo giờ Việt Nam, khi ứng dụng/scheduler hoạt động và không bị delay bởi tải/điều kiện khác. **Cron không phải cơ chế bảo đảm exactly once**: nếu app down lúc 09:00, Spring `@Scheduled` thường không tự “catch up” đầy đủ các lần lỡ như durable job scheduler.

### 11.1. Disable cron bằng placeholder

```java
@Scheduled(
    cron = "${demo.report.cron:-}",
    zone = "Asia/Ho_Chi_Minh")
public void report() { /* ... */ }
```

Dấu `-` là `Scheduled.CRON_DISABLED` cho cron expression; pattern này phù hợp khi cần bật/tắt lịch qua config. Không tự suy diễn cách này áp dụng cho `fixedRateString`/`fixedDelayString` (chúng có parsing khác).

### 11.2. CronExpression cho unit test calendar

```java
CronExpression expression =
        CronExpression.parse("0 0 9 * * MON-FRI");

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime saturday =
        ZonedDateTime.of(
                2026, 11, 7, 12, 0, 0, 0, zone);

ZonedDateTime next = expression.next(saturday);
// 2026-11-09 09:00 tại Asia/Ho_Chi_Minh (thứ Hai).
```

Đây là snippet; file `CronCalendarTest` có assertion runnable. Test calendar ở mức `CronExpression` **không khởi động scheduler**, vì ta đang kiểm **cách tính lịch** chứ không phải executor thread.

## 12. DST: giờ địa phương có lúc không tồn tại hoặc xuất hiện hai lần

Không phải mọi múi giờ đều có ngày đúng 24 tiếng:

- Khi chuyển sang DST, một khoảng giờ có thể **bị nhảy qua** (nonexistent local time).
- Khi lùi DST, một khoảng giờ có thể **xuất hiện hai lần** (ambiguous local time).
- Cron chạy lúc 02:30 tại một zone có DST cần được kiểm cả transition dates.
- Một job chạy ngày cuối tháng, ngày 29/02 hoặc holiday cũng cần calendar contract rõ.

Ví dụ 2026 ở `America/New_York`: ngày 08/03 chuyển từ 01:59 sang 03:00 theo giờ địa phương. `ZonedDateTime` + `ZoneId` phản ánh timezone rules này.

**Không ghi expected “chạy đúng một lần lúc 02:30” nếu 02:30 không tồn tại hôm ấy.** Hãy xác định policy: skip, next valid instant, hay bù job; test logic scheduling/cron/operational scheduler đúng policy. Không coi `Clock.systemDefaultZone()` trên máy CI ở UTC là timezone nghiệp vụ.

### 12.1. Tránh so local times cho expiry tuyệt đối

Nếu token được cấp tại `Instant` T và hết hạn sau 15 phút, tính `T.plus(Duration.ofMinutes(15))`. Đừng chuyển sang local time rồi cộng 15 phút và giả định DST không ảnh hưởng. Với billing calendar “ngày thứ N của tháng”, cần logic theo `LocalDate`/`ZonedDateTime` riêng.

## 13. Java `Clock` không phải timer/executor

`Clock.fixed` **không** thực thi Runnable, không tạo thread và không thông báo deadline. Nó chỉ trả một `Instant` theo cách được chỉ định.

Ngược lại, `TaskScheduler` có APIs:

```java
// Snippet: TaskScheduler scheduler và Runnable action.
ScheduledFuture<?> future = scheduler.schedule(
        action, Instant.now().plusSeconds(10));
```

Scheduler có clock và underlying executor riêng. Một service `Clock` cố định tại 2030 không đồng nghĩa `scheduler.schedule(..., timeFromFixedClock)` sẽ đợi thời gian mô phỏng; scheduling có thể dùng clock/OS scheduling thực. Spring `TaskScheduler.getClock()` cho biết clock scheduler dùng; `ThreadPoolTaskScheduler.setClock(...)` có thể cấu hình clock cho scheduling calculations, nhưng **thay đổi clock mà không đổi hệ executor/trigger semantics không tự đem tới virtual-time scheduler đáng tin**.

**Hướng test:** Unit-test calculation của desired instant; nếu cần chứng minh fire/wakeup đúng, dùng scheduler test chuyên biệt với controlled clock/executor hoặc bounded smoke test trên runtime thật. Không làm 100 unit tests đợi timers.

## 14. Thiết kế test pyramid cho thời gian

| Cấp test | Chạy với gì? | Tín hiệu tin cậy |
|---|---|---|
| Pure Java unit | `Clock.fixed`/MutableClock | Deadline boundary, idempotency, business rule |
| Calendar unit | `CronExpression`/`ZonedDateTime` | Next trigger, zone, DST |
| Spring context wiring | `@SpringBootTest` + `@Primary Clock` | Bean Clock được inject; scheduler disabled |
| Scheduled smoke | `@SpringBootTest` bật `@Scheduled` + Awaitility | Tick thật cuối cùng xử lý overdue record |
| Full persistence integration | Testcontainers + DB transaction | Atomic claim/lease và rows across instances |
| Multi-instance/distributed | Hai app replicas/worker processes | Duplicate prevention/failover/retry |
| Real production-like observation | Metrics/logs/traces/timezone config | Drift, SLA, missed runs, operational safety |

**Phần lớn kịch bản “tác vụ có đúng hạn?” thuộc cấp pure Java unit.** Chỉ một số ít smoke tests dành cho “lịch có thực sự được đăng ký, scheduler có gọi adapter không?”. Những lỗi ở distributed locking/database không thể chứng minh bằng một in-memory map trong một JVM.

## 15. Project runnable: mục tiêu của demo

Ta tạo một application với các tác vụ `TimedTask`:

- `id`: định danh duy nhất trong store.
- `dueAt`: một `Instant` tuyệt đối.
- `completed`: đã được xử lý hay chưa.
- `TaskStore`: lưu trong `ConcurrentHashMap`, chuyển `completed=false → true` atomically theo từng key.
- `DueTaskService`: lấy **một snapshot** `clock.instant()` rồi xét tasks đến hạn.
- `CleanupTick`: adapter mỏng có `@Scheduled`; chỉ tồn tại khi `demo.cleanup.enabled=true`.
- `Clock` production: `systemUTC`, test override thành fixed Clock.
- `ScheduledTickSmokeTest`: dùng Awaitility và timeout 5 giây để xác minh scheduler chạy thật.

Cây thư mục:

```text
clock-scheduler-testing/
  settings.gradle
  build.gradle
  src/main/java/com/example/timetest/
    SchedulerLessonApplication.java
    TimeConfiguration.java
    TimedTask.java
    TaskStore.java
    DueTaskService.java
    CleanupTick.java
  src/test/java/com/example/timetest/
    MutableClock.java
    DueTaskServiceTest.java
    CronCalendarTest.java
    DueTaskSpringIntegrationTest.java
    ScheduledTickSmokeTest.java
```

**Không có persistence production**. Khi JVM dừng, tasks trong `ConcurrentHashMap` biến mất. Demo này cố tình minh họa test time/callback boundary; hệ thống công việc quan trọng cần DB/job queue để phục hồi và phối hợp nhiều replicas.

## 16. Gradle settings và dependency

**`settings.gradle`**

```groovy
rootProject.name = 'clock-scheduler-testing'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` mang nền tảng Spring context/scheduling; không cần HTTP stack hoặc DB. `spring-boot-starter-test` mang JUnit, AssertJ/Mockito và Spring Test; explicit `awaitility` để smoke test không phụ thuộc tình cờ vào transitive dependency. Spring Boot BOM quản lý version của các dependency trong ví dụ. Nếu dự án dùng Maven, dùng tương đương `spring-boot-starter`, `spring-boot-starter-test` và `awaitility` dưới `test` scope, cùng JUnit Platform tương thích.

**Java 17+** là tối thiểu; không cần virtual threads của Java 21. Nếu production dùng Boot/Spring phiên bản khác, kiểm annotation/package và behavior tương ứng trước khi copy.

## 17. Application bootstrap và Clock bean

**`src/main/java/com/example/timetest/SchedulerLessonApplication.java`**

```java
package com.example.timetest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class SchedulerLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SchedulerLessonApplication.class, args);
    }
}
```

**`src/main/java/com/example/timetest/TimeConfiguration.java`**

```java
package com.example.timetest;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

`Clock.systemUTC()` giúp business code không phụ thuộc default timezone của host. Khi test muốn control time, tạo bean `@Primary Clock` trong test config; không dùng `ReflectionTestUtils` thay mutable field hoặc mock static `Instant.now()`.

`@EnableScheduling` vẫn kích hoạt scheduling infrastructure trong context; việc **có hay không có** job bean `CleanupTick` do property `demo.cleanup.enabled` quyết định, như mục 20.

## 18. Domain record và in-memory store

**`src/main/java/com/example/timetest/TimedTask.java`**

```java
package com.example.timetest;

import java.time.Instant;
import java.util.Objects;

public record TimedTask(
        String id, Instant dueAt, boolean completed) {

    public TimedTask {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(dueAt, "dueAt");
    }
}
```

**`src/main/java/com/example/timetest/TaskStore.java`**

```java
package com.example.timetest;

import java.time.Instant;
import java.util.Optional;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class TaskStore {

    private final ConcurrentHashMap<String, TimedTask> tasks =
            new ConcurrentHashMap<>();

    public void put(TimedTask task) {
        Objects.requireNonNull(task, "task");
        tasks.put(task.id(), task);
    }

    public Optional<TimedTask> find(String id) {
        return Optional.ofNullable(tasks.get(id));
    }

    public int markDue(Instant cutoff) {
        Objects.requireNonNull(cutoff, "cutoff");
        AtomicInteger transitions = new AtomicInteger();

        for (String id : tasks.keySet()) {
            tasks.computeIfPresent(id, (key, current) -> {
                if (current.completed()
                        || current.dueAt().isAfter(cutoff)) {
                    return current;
                }

                transitions.incrementAndGet();
                return new TimedTask(
                        current.id(), current.dueAt(), true);
            });
        }
        return transitions.get();
    }

    public void clear() {
        tasks.clear();
    }
}
```

**Vì sao dùng `computeIfPresent`?** Trong `ConcurrentHashMap`, remapping theo một key được thực hiện atomically với các thao tác update tương ứng. Hai callers kiểm cùng task có thể không cùng chuyển `false → true`: caller thứ hai nhìn task completed và không đánh dấu lại. Bài test concurrency kiểm trường hợp này trong **một JVM**.

**Giới hạn quan trọng:** Iteration qua `tasks.keySet()` là weakly consistent khi có concurrent inserts/deletes; một task vừa được thêm có thể chỉ được thấy ở tick sau. Counter `transitions` mô tả transitions trong lần quét, không phải durable event count. `TaskStore.put` có thể overwrite ID cũ; production phải dùng DB unique constraint và claim protocol đúng. `clear()` chỉ dùng cho test isolation trong demo, **không** phải thao tác xóa production database.

### 18.1. Vấn đề của side effects

Trong demo, chuyển boolean completed là side effect. Thực tế có thể phải gửi email, chuyển tiền hoặc publish message; `markDue` và external side effect có thể nằm ở hai resource managers khác nhau. **Đánh dấu completed trước khi gửi** có thể làm mất việc nếu gửi fail; **gửi rồi đánh dấu** có thể gửi lặp khi crash. Cần idempotency key/outbox/retry policy phù hợp và test độc lập. Một in-memory atomic map không chứng minh exactly once end-to-end.

## 19. Service: business clock là nguồn quyết định deadline

**`src/main/java/com/example/timetest/DueTaskService.java`**

```java
package com.example.timetest;

import java.time.Clock;
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class DueTaskService {

    private final Clock clock;
    private final TaskStore store;

    public DueTaskService(Clock clock, TaskStore store) {
        this.clock = clock;
        this.store = store;
    }

    public int processDue() {
        Instant cutoff = clock.instant();
        return store.markDue(cutoff);
    }
}
```

Business method không có `@Scheduled`. Test có thể gọi trực tiếp. Mọi lần `processDue()` nhận một `cutoff` duy nhất, nên nếu xử lý 10.000 tasks kéo dài qua deadline mới, tất cả được xét theo cùng snapshot. Điều này bảo đảm một “batch time” rõ ràng.

**Tại sao method trả int?** Để test số **state transitions** mà invocation thực sự thực hiện. Scheduler adapter có thể log/metric riêng, nhưng test không phải verify một void method đã được gọi rồi suy ra dữ liệu đúng. Test core sẽ assert cả `int` và trạng thái `TimedTask.completed`.

## 20. Scheduled adapter: tách lịch chạy khỏi nghiệp vụ

**`src/main/java/com/example/timetest/CleanupTick.java`**

```java
package com.example.timetest;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "demo.cleanup",
        name = "enabled",
        havingValue = "true")
public class CleanupTick {

    private final DueTaskService service;
    private final AtomicInteger executions = new AtomicInteger();

    public CleanupTick(DueTaskService service) {
        this.service = service;
    }

    @Scheduled(
            fixedDelayString =
                    "${demo.cleanup.fixed-delay-ms:60000}",
            initialDelayString =
                    "${demo.cleanup.initial-delay-ms:1000}",
            timeUnit = TimeUnit.MILLISECONDS)
    public void tick() {
        service.processDue();
        executions.incrementAndGet();
    }

    public int executions() {
        return executions.get();
    }
}
```

Trong demo, nếu property `demo.cleanup.enabled` không được đặt, `CleanupTick` **không được tạo** (vì `matchIfMissing` mặc định false), nên không có job periodic này chạy. Smoke test bật true để kiểm Spring scheduling wiring. Trên production, phải chọn cadence thích hợp và đặt quan sát lỗi.

**Không đưa `@Scheduled` lên `DueTaskService.processDue()`**: làm vậy test business vô tình phải nạp scheduled infrastructure, khó isolate và có nguy cơ gọi song song. Adapter mỏng giúp test wiring riêng.

### 20.1. Nếu task ném exception?

Trong nhiều scheduler setups, exception trong periodic task được error handler ghi log và lần chạy sau có thể vẫn được lên lịch. **Không giả định exception sẽ làm JUnit test fail** vì nó xảy ra trên scheduler thread khác. Smoke test cần quan sát state/event thực, và production cần logging/metrics/alerts, retry/dead-letter handling khi phù hợp.

### 20.2. Dừng scheduling trong tests thường

Có thể dùng:

```properties
demo.cleanup.enabled=false
```

trong test-specific configuration. Không chỉ dựa vào `@DirtiesContext` sau khi job đã chạy gây side effect. Nếu có nhiều scheduled beans khác, kiểm toàn bộ và áp policy enablement chung; test chỉ bật chính job đang muốn smoke.

## 21. MutableClock helper cho unit tests

**`src/test/java/com/example/timetest/MutableClock.java`**

```java
package com.example.timetest;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(
                Objects.requireNonNull(initial, "initial")), zone);
    }

    private MutableClock(
            AtomicReference<Instant> current, ZoneId zone) {
        this.current = current;
        this.zone = Objects.requireNonNull(zone, "zone");
    }

    public void advance(Duration amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.isNegative()) {
            throw new IllegalArgumentException(
                    "Clock advance cannot be negative");
        }
        current.updateAndGet(now -> now.plus(amount));
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableClock(current, newZone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }
}
```

`MutableClock` dùng `AtomicReference<Instant>` để thao tác đổi thời gian an toàn về mặt visibility giữa threads trong test. `withZone` tạo một Clock view cùng instant state nhưng zone khác, phù hợp hợp đồng `Clock`. Nó **không tạo timer/executor** và không tự kích hoạt scheduled bean; bạn vẫn phải gọi `service.processDue()` hoặc cho scheduler đánh thức.

Nếu test không cần advance, ưu tiên `Clock.fixed` thay vì helper tự viết. MutableClock có giá trị khi một kịch bản cần kiểm nhiều mốc liên tiếp.

## 22. Pure JUnit: kiểm trước/đúng/sau hạn và idempotency

**`src/test/java/com/example/timetest/DueTaskServiceTest.java`**

```java
package com.example.timetest;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DueTaskServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-11-08T10:00:00Z");

    private MutableClock clock;
    private TaskStore store;
    private DueTaskService service;

    @BeforeEach
    void setUp() {
        clock = new MutableClock(NOW, ZoneOffset.UTC);
        store = new TaskStore();
        service = new DueTaskService(clock, store);
    }

    @Test
    void beforeDeadlineDoesNotCompleteTask() {
        store.put(new TimedTask(
                "a", NOW.plusNanos(1), false));

        assertEquals(0, service.processDue());
        assertFalse(store.find("a").orElseThrow().completed());
    }

    @Test
    void exactlyAtDeadlineCompletesTask() {
        store.put(new TimedTask("a", NOW, false));

        assertEquals(1, service.processDue());
        assertTrue(store.find("a").orElseThrow().completed());
    }

    @Test
    void advancingOneNanosecondCrossesBoundary() {
        store.put(new TimedTask(
                "a", NOW.plusNanos(1), false));

        assertEquals(0, service.processDue());

        clock.advance(Duration.ofNanos(1));

        assertEquals(1, service.processDue());
        assertTrue(store.find("a").orElseThrow().completed());
    }

    @Test
    void repeatedTickDoesNotProcessCompletedTaskTwice() {
        store.put(new TimedTask(
                "due", NOW.minusSeconds(10), false));

        assertEquals(1, service.processDue());
        assertEquals(0, service.processDue());
        assertTrue(store.find("due").orElseThrow().completed());
    }

    @Test
    void onlyTasksDueByOneSnapshotAreChanged() {
        store.put(new TimedTask(
                "past", NOW.minusSeconds(1), false));
        store.put(new TimedTask(
                "exact", NOW, false));
        store.put(new TimedTask(
                "future", NOW.plusSeconds(1), false));

        assertEquals(2, service.processDue());
        assertTrue(store.find("past").orElseThrow().completed());
        assertTrue(store.find("exact").orElseThrow().completed());
        assertFalse(store.find("future").orElseThrow().completed());
    }

    @Test
    void twoConcurrentInvocationsClaimOnlyOnce()
            throws Exception {

        store.put(new TimedTask("shared", NOW, false));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first =
                    pool.submit(service::processDue);
            Future<Integer> second =
                    pool.submit(service::processDue);

            assertEquals(
                    1, first.get() + second.get());
            assertTrue(
                    store.find("shared").orElseThrow().completed());
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void changingZoneDoesNotChangeInstant() {
        Clock vietnam = clock.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(NOW, vietnam.instant());
        assertEquals(
                ZoneId.of("Asia/Ho_Chi_Minh"),
                vietnam.getZone());
    }
}
```

Có **7 JUnit tests**. Không có `Thread.sleep`; các test dùng NOW cố định hoặc mutable clock. Mốc 1 nanosecond được kiểm chính xác. Concurrency test chỉ chứng minh in-memory `ConcurrentHashMap` xử lý hai calls trong **một JVM**, chưa chứng minh multi-pod/database exactly once. `shutdownNow()` giải phóng executor ở cuối dù assertion lỗi.

Một lưu ý: `Future.get()` không timeout trong ví dụ pure Java (tasks rất ngắn và executor do test kiểm soát); nếu test này được dùng để stress race/lock code có khả năng deadlock, hãy dùng `future.get(2, TimeUnit.SECONDS)` để không làm treo suite. Smoke test thực bên dưới luôn có timeout hữu hạn.

## 23. Calendar tests: cron và daylight saving

**`src/test/java/com/example/timetest/CronCalendarTest.java`**

```java
package com.example.timetest;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CronCalendarTest {

    @Test
    void weekdayNineAmAfterSaturdayFallsOnMonday() {
        CronExpression expression =
                CronExpression.parse("0 0 9 * * MON-FRI");

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime saturday =
                ZonedDateTime.of(
                        2026, 11, 7, 12, 0, 0, 0, zone);

        ZonedDateTime next = expression.next(saturday);

        assertEquals(
                ZonedDateTime.of(
                        2026, 11, 9, 9, 0, 0, 0, zone),
                next);
    }

    @Test
    void springForwardSkipsLocalTwoAmHour() {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime justBefore =
                ZonedDateTime.of(
                        2026, 3, 8, 1, 59, 0, 0, zone);

        ZonedDateTime nextMinute =
                justBefore.plusMinutes(1);

        assertEquals(3, nextMinute.getHour());
        assertEquals(0, nextMinute.getMinute());
    }
}
```

Test đầu có **dữ liệu lịch cố định**: thứ Bảy 07/11/2026 lúc 12:00 giờ Việt Nam → cron weekday 09:00 tiếp theo là thứ Hai 09/11/2026. Test thứ hai chứng minh DST gap ở New York, chứ **không** tự kết luận Spring @Scheduled sẽ skip hay bù trigger theo cách business yêu cầu.

Khi cron phụ thuộc business zone, hãy truyền `ZonedDateTime` theo zone đó vào `CronExpression.next`. Test trường hợp cuối tháng, năm nhuận, DST overlap/gap nếu business chạy ở khu vực có chuyển giờ.

## 24. Spring integration: Clock override nhưng không chạy job

**`src/test/java/com/example/timetest/DueTaskSpringIntegrationTest.java`**

```java
package com.example.timetest;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        properties = "demo.cleanup.enabled=false")
@Import(DueTaskSpringIntegrationTest.FixedTestClock.class)
class DueTaskSpringIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTestClock {

        @Bean
        @Primary
        Clock fixedTestClock() {
            return Clock.fixed(
                    Instant.parse("2026-04-01T12:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    @Autowired
    TaskStore store;

    @Autowired
    DueTaskService service;

    @Autowired
    Clock clock;

    @Autowired(required = false)
    CleanupTick tick;

    @BeforeEach
    void resetOnlyDemoStore() {
        store.clear();
    }

    @Test
    void serviceUsesPrimaryFixedClockBean() {
        Instant cutoff =
                Instant.parse("2026-04-01T12:00:00Z");

        assertEquals(cutoff, clock.instant());

        store.put(new TimedTask(
                "before", cutoff.minusNanos(1), false));
        store.put(new TimedTask(
                "exact", cutoff, false));
        store.put(new TimedTask(
                "after", cutoff.plusNanos(1), false));

        assertEquals(2, service.processDue());
        assertTrue(
                store.find("before").orElseThrow().completed());
        assertTrue(
                store.find("exact").orElseThrow().completed());
        assertEquals(
                false,
                store.find("after").orElseThrow().completed());
    }

    @Test
    void scheduledAdapterIsAbsentWhenDisabled() {
        assertNull(tick);
    }
}
```

Hai tests kiểm Spring bean wiring:

- `@Primary Clock` fixed được chọn khi inject vào `DueTaskService`, thay cho `Clock.systemUTC` của production config.
- `demo.cleanup.enabled=false` làm `CleanupTick` không có trong context, tránh scheduled thread thay đổi state khi đang assert business logic.
- `store.clear()` dọn **chỉ in-memory store thuộc demo**. Với Redis/database shared thật, không dùng `clear all` mà phải scope theo test owner.
- `@SpringBootTest` không test real network; project không có HTTP server.

**Lưu ý:** Cấu hình fixed Clock cho business service không đổi scheduling Clock. Nếu một scheduled bean khác vẫn được bật, nó vẫn có thể chạy theo wall-clock ngay trong test; phải quản lý mọi scheduled beans của app, không chỉ một.

## 25. Smoke test bật scheduler thật và chờ bounded

**`src/test/java/com/example/timetest/ScheduledTickSmokeTest.java`**

```java
package com.example.timetest;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "demo.cleanup.enabled=true",
        "demo.cleanup.initial-delay-ms=100",
        "demo.cleanup.fixed-delay-ms=100"
})
class ScheduledTickSmokeTest {

    @Autowired
    TaskStore store;

    @Autowired
    CleanupTick tick;

    @BeforeEach
    void beforeEach() {
        store.clear();
    }

    @AfterEach
    void afterEach() {
        store.clear();
    }

    @Test
    void aRealScheduledTickEventuallyProcessesOverdueTask() {
        String id = "smoke-" + UUID.randomUUID();

        store.put(new TimedTask(
                id, Instant.now().minusSeconds(30), false));

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(25))
                .untilAsserted(() -> {
                    assertTrue(
                            store.find(id)
                                    .orElseThrow()
                                    .completed());
                    assertTrue(tick.executions() > 0);
                });
    }
}
```

**Có 1 smoke test**:

1. Spring Boot context bật `@EnableScheduling` và tạo bean `CleanupTick` vì property true.
2. Scheduler thực chạy `tick()` với fixed delay 100 ms và initial delay 100 ms (ở demo test).
3. `DueTaskService` dùng system UTC business clock; task có `dueAt` cách wall-clock hiện tại 30 giây trong quá khứ.
4. Awaitility poll trạng thái task tối đa **5 giây**, fail nếu scheduler không bao giờ xử lý.
5. Test kiểm thêm `tick.executions() > 0` để biết callback đã được gọi.
6. `@AfterEach` dọn demo store; scheduling context có thể còn chạy cho đến khi context teardown, nhưng không có tác vụ persistence bên ngoài.

**Smoke test có timing thực**, vì mục đích là chứng minh Spring đã wiring scheduler và callback hoạt động. Nó không chứng minh “tick chạy chính xác mỗi 100 ms”, không chứng minh scheduling SLA production, và không nên bị nhân lên thành hàng trăm tests. Nếu CI chậm, điều chỉnh timeout theo SLA test có chủ đích; đừng tăng vô hạn hoặc chuyển sang sleep cứng.

### 25.1. Tránh shared context giữa các test groups

`DueTaskSpringIntegrationTest` dùng property `demo.cleanup.enabled=false` và imported fixed Clock; `ScheduledTickSmokeTest` dùng property true. Spring TestContext xem chúng là context configurations khác, nên không phải cố tình share một scheduler đang chạy trong tests business. Nếu dự án có nhiều test classes sử dụng cùng property true, scheduler có thể chạy khi context cache còn sống; hãy tách suites hoặc bật scheduling có chọn lọc.

## 26. Tổng số tests và lệnh chạy

| Class | Số `@Test` | Điều bảo vệ |
|---|---:|---|
| `DueTaskServiceTest` | 7 | Deadline boundaries, idempotency, concurrency trong JVM, zone |
| `CronCalendarTest` | 2 | Weekday cron, DST gap |
| `DueTaskSpringIntegrationTest` | 2 | Inject Clock fixed, tắt adapter định kỳ |
| `ScheduledTickSmokeTest` | 1 | Scheduler thật gọi callback, eventual completion |
| **Tổng** | **12** | Time logic và scheduling wiring ở các lớp riêng |

Lệnh:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Dự kiến `BUILD SUCCESSFUL` nếu Java 17, Spring Boot 3.5.16, dependencies và build environment phù hợp. **Đây là kết quả dự kiến từ mã được rà soát, không phải tuyên bố đã chạy Gradle trên repository của người học.** Không có stdout nghiệp vụ cố định; số tick có thể lớn hơn 1 và khác nhau mỗi run. JUnit report thường ở `build/reports/tests/test/index.html`.

Nếu bạn tạo project mới chưa có Gradle wrapper, cần tạo wrapper bằng Gradle/IDE trước khi chạy. Không cần Docker, PostgreSQL hay mạng HTTP vì demo dùng in-memory store.

## 27. Cách debug khi test thời gian thất bại

Hỏi theo thứ tự:

1. **Business clock nào đang dùng?** Có bean `Clock.systemUTC` hay fixed test bean được @Primary chọn?
2. **Cutoff được tính thế nào?** Đơn vị seconds/millis/nanos, inclusive/exclusive?
3. **Task lưu ở đâu?** In-memory store, DB hay queue; có dữ liệu test trước còn lại?
4. **Có @EnableScheduling không?** Scheduled bean có thật sự trong Spring context?
5. **Property enablement đúng chưa?** Có `demo.cleanup.enabled=true` trên smoke context không?
6. **Fixed delay/initial delay parse đúng chưa?** Có nhầm milliseconds/seconds?
7. **Có TaskScheduler bean hay executor riêng?** Qualifier/thread pool/queue/backlog?
8. **Task có ném exception không?** Error handler có log mà không fail JUnit thread?
9. **Có concurrent methods/replicas không?** Cùng task ID có bị xử lý hai lần?
10. **CI timezone/DST có ảnh hưởng không?** Logic dùng `Instant` hay `LocalDateTime.now()`?
11. **Mock/await đang chờ điều gì?** Condition có quan sát đúng side effect không?
12. **Có task chạy sau test cleanup không?** Context cache/scheduler lifecycle còn sống?

**Không bắt đầu bằng “tăng sleep lên 10 giây”.** Đầu tiên xác định test đang kiểm business time hay scheduling wakeup, sau đó dùng công cụ phù hợp.

## 28. Scheduler error handling, retries và idempotency

Một job có thể chạy lần đầu, lỗi sau nửa chừng, rồi chạy lại. Hệ thống có thể còn nhiều nodes và nhiều executor threads. Chính sách vận hành cần trả lời:

- Nếu task timeout, có retry không? Mỗi lần retry có backoff/jitter và hạn mức không?
- Nếu processing gửi message thành công rồi commit DB fail, lần sau có gửi trùng không?
- Nếu handler ném exception, scheduled tick tiếp theo có chạy hay đã bị cancel?
- Nếu task chạy lâu hơn fixedRate, có concurrent executions không theo cấu hình executor/@Async?
- Nếu app restart, job chưa xử lý có còn trong DB không?
- Nếu hai nodes đều đến mốc 09:00, node nào sở hữu job?
- Nếu time trên node A nhanh hơn node B 2 giây, query due dựa vào clock nào?
- Có idempotency key, outbox/unique constraint hoặc database claim giúp tránh double execution không?

**Idempotency của demo:** `TaskStore.markDue` chỉ chuyển false→true một lần theo key trong cùng JVM. **Không** chứng minh đúng một lần side effect bên ngoài. Với database, thường cần atomic claim:

```sql
-- Snippet ý tưởng PostgreSQL; điều chỉnh cho schema thật.
UPDATE scheduled_jobs
SET status = 'CLAIMED'
WHERE id = :id
  AND status = 'PENDING'
  AND due_at <= :cutoff;
```

Chỉ worker có `affectedRows=1` mới tiếp tục xử lý. Nhưng ngay cả khi claim atomic, vẫn phải xử lý crash giữa claim và side effect bằng lease expiration, idempotency hoặc outbox. Đừng coi `@Scheduled` tự cung cấp distributed locking.

## 29. Nhiều replicas: scheduler có thể gọi lặp

Nếu chạy hai pods cùng bật `@Scheduled(cron=...)`, **thông thường cả hai** sẽ đăng ký và kích hoạt method theo lịch của riêng mình. Spring Scheduling cơ bản không phải scheduler cluster-aware có leader election hoặc durable job leasing.

Các chiến lược thực tế:

- **Chỉ một replica chuyên chạy scheduler:** deployment riêng hoặc leader election, nhưng cần failover.
- **Distributed lock:** DB/Redis lock có TTL/lease và fencing token nếu cần; đo/kiểm clock skew và failure modes.
- **Database atomic claiming:** query/claim tasks theo status+dueAt với transaction/isolation phù hợp.
- **Quartz clustered JDBC job store:** dùng khi cần scheduling durable/cluster semantics; test với DB thật.
- **Managed external scheduler/queue:** cron từ platform hoặc message delivery; vẫn cần idempotency.
- **Idempotent handler/outbox:** bảo vệ side effect dù có retry/lặp.

**Test đúng cấp:** Chạy hai worker processes hoặc hai application contexts nối cùng test DB, kích hoạt cùng due task, assert chỉ một atomic claim hoặc một idempotent external side effect theo contract. **Hai calls tới ConcurrentHashMap của demo không đủ** cho multi-process.

### 29.1. Lock TTL và clock skew

Nếu lock dựa trên đồng hồ của từng node, drift có thể khiến cả hai nghĩ lease đã hết hạn. Có thể dùng timestamp từ DB/server, monotonic lease mechanism và fencing token. Khi test, mô phỏng hai clocks lệch nhau và crash/restart, không chỉ chạy happy path với cùng `Clock.fixed`.

## 30. Trạng thái lịch chạy và DST trong production

Một số thuật ngữ không đồng nhất:

- **Scheduled-at:** thời điểm business cần chạy.
- **Started-at:** thời điểm thực tế executor bắt đầu callback.
- **Completed-at:** thời điểm handler xong.
- **Next scheduled execution:** trigger tính lại từ cron/fixed delay/rate.
- **Misfire:** một lần chạy dự kiến bị lỡ (server down/đang quá tải).
- **Catch-up/backfill:** xử lý các lần đã bỏ lỡ sau khi service hồi phục.

`@Scheduled` đơn giản không cung cấp đầy đủ durable misfire policy như một persistent scheduler. Với bảng jobs dựa trên `due_at`, mỗi tick query `due_at <= now` có thể **quét bù** các tasks chưa xử lý, nhưng cần giới hạn batch size, idempotency và tránh catch-up storm.

Cron 09:00 theo timezone business là lịch local; dù hai lần 09:00 ở hai nơi có UTC instant khác nhau. Trong kiểm thử, freeze `Instant` và dùng ZoneId rõ ràng cho calendar. Với DST overlap/skip, định nghĩa behavior mong muốn trước khi assert.

## 31. `@Async` không làm `@Scheduled` thành job được quản lý tự động

`@Scheduled` quyết định *khi nào gọi*; `@Async` quyết định *có chuyển thực thi sang executor khác không* khi bean/method đi qua proxy đúng. Kết hợp hai annotation có thể gây overlap, mất context hoặc khó thấy exception.

Ví dụ phản mô hình:

```java
// PHẢN VÍ DỤ: scheduler callback tiếp tục khi side effect async còn chạy.
// Không có idempotency/locking thì nhiều jobs có thể overlap.
@Scheduled(fixedRate = 1000)
public void trigger() {
    asyncService.doWork();
}
```

Trong production:

- Định nghĩa run ownership/atomic claim.
- Không assume async `void` exception ném về thread gọi.
- Test futures/CompletionStage với deadline thay vì sleep.
- Kiểm context propagation của SecurityContext/MDC/tracing.
- Không tắt scheduler và nghĩ async workers tự bị hủy nếu tasks còn chạy.
- Dùng dedicated executor capacity/queue/rejection policy phù hợp.

Một smoke test callback được gọi **không chứng minh async job đã hoàn thành**; cần await đúng completion state.

## 32. Reactor virtual time khác Spring Scheduler clock

Reactor Test có:

```java
// Snippet, cần reactor-test và Reactor publisher dùng virtual scheduler.
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
```

Trong bối cảnh đúng, `StepVerifier.withVirtualTime` kiểm một publisher dùng Reactor `VirtualTimeScheduler` mà không chờ 24 giờ thật. Nhưng điều này **không tự làm**:

- Spring `@Scheduled` chạy một ngày tương lai.
- PostgreSQL/Redis TTL nhảy thời gian.
- Java `ScheduledExecutorService` thường trở thành virtual.
- Một API bên ngoài thay đổi timestamp.
- Mọi custom scheduler đang được cung cấp trước khi StepVerifier cài virtual time đều tuân theo.

Khi test reactive code, tạo publisher **bên trong supplier** của `withVirtualTime` để các operator chọn virtual scheduler đúng. Đây là snippet về khái niệm; project runnable không thêm Reactor Test dependency vì focus của bài là Spring Scheduling và `java.time.Clock`.

## 33. Kiểm thật hạn sử dụng và định kỳ trong database

Một hệ thống dùng MongoDB TTL index hay Redis EXPIRE có **backend expiration clock** độc lập Java `Clock`. Freeze business Clock không làm Mongo TTL monitor/Redis server chạy trước.

Mô hình tốt:

1. Unit test xác minh service **ghi expiresAt/TTL** đúng theo Clock.
2. Repository/integration test xác minh field/index/TTL được cấu hình đúng.
3. Một số ít backend expiry tests dùng bounded eventual wait, không đòi xóa ngay đúng mili-giây.
4. Cleanup data theo test owner dù TTL chưa hết, không dùng expiry như teardown duy nhất.
5. Với long retention policy, test “ngày 30” bằng fixed Clock của domain thay vì CI ngủ 30 ngày.

Nếu scheduler định kỳ đọc bảng jobs, ưu tiên test SQL query `due_at <= cutoff` với real DB và fixed cutoff; smoke scheduling chỉ đảm bảo job kích hoạt phương thức đúng.

## 34. Các lỗi hay gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| Test timeout sau `Thread.sleep(1000)` | Scheduler bận/không chạy đúng nhịp | Await condition có deadline, đọc logs |
| DueAt đúng giờ nhưng test thất bại ngẫu nhiên | Dùng `now()` nhiều lần | Inject fixed Clock, snapshot cutoff |
| Off-by-one ở deadline | `isAfter/isBefore` sai | Test trước/đúng/sau 1ns |
| Local pass, CI fail ở 09:00 | System default zone khác | `Instant` + `ZoneId` explicit |
| Cron weekday sai | Nhầm Spring cron 6 fields/Unix 5 fields | `CronExpression.parse` + calendar tests |
| Job chạy gấp đôi trên Kubernetes | Mỗi pod có `@Scheduled` | Distributed claim/lock, idempotency |
| Bật fixed Clock nhưng job không chạy sớm | Business Clock khác scheduler clock | Gọi service trực tiếp trong unit test |
| Test khác bị xóa fixture | Scheduled bean còn chạy trong context | Disable job property ở tests thường |
| `@Scheduled` không chạy | Thiếu `@EnableScheduling` hoặc bean không được tạo | Xem annotation, conditional property |
| Job vẫn chạy sau một test class | Spring context cache còn sống | Separate contexts/disable job |
| Scheduled method ném lỗi nhưng JUnit xanh | Exception xảy ra background thread | Assert hậu điều kiện, alert/metrics |
| Sự kiện async hoàn thành sau assertion | Không await actual completion | Awaitility/future/latch có timeout |
| Test đúng code nhưng vào giờ DST nhảy | Giờ local không tồn tại/ambiguous | ZonedDateTime/CronExpression/DST cases |
| `Instant` bị serialize thiếu offset | LocalDateTime thay Instant | Giữ absolute timestamp/ISO 8601 |
| Test “exactly once” xanh trong JVM nhưng prod gửi trùng | Không có distributed lock/outbox | Integration với hai workers/backend |
| Tiến MutableClock nhưng DB TTL không xóa | Backend clock độc lập | Test backend expiry riêng |
| Identity tasks biến mất sau restart | Store chỉ in-memory | Durable job table/queue |
| Test disabled job nhưng vẫn thấy tick | Bean khác scheduling vẫn bật | Inventory tất cả scheduled components |
| FixedRate job overlap khi @Async | Caller không await worker, shared state | Atomic claim/idempotency/capacity |

## 35. Bài tập thực hành

### Bài A — Clock cố định

Deadline `2026-11-08T10:00:00Z`. Viết test ở 09:59:59.999999999, 10:00:00 và 10:00:00.000000001. Theo contract `dueAt <= now`, kỳ vọng thế nào?

**Đáp án:** Không, có, có. Dùng `Clock.fixed`/MutableClock và `Instant`, không dùng sleep.

### Bài B — Business Clock vs scheduler

Bạn @Primary một bean `Clock.fixed(Instant.parse("2030-01-01T00:00:00Z"), UTC)` rồi mong `@Scheduled(fixedDelay=5000)` chạy tức thì 10 năm lần tick. Vì sao sai?

**Đáp án:** Business Clock và TaskScheduler clock/executor độc lập nếu không được liên kết cụ thể; Clock không tạo timers. Test process method trực tiếp; smoke scheduler riêng.

### Bài C — FixedDelay vs FixedRate

Một job chạy 7 giây; `fixedDelay=5s` khác `fixedRate=5s` thế nào?

**Đáp án:** FixedDelay đợi 5 giây **sau** khi lần trước kết thúc; fixedRate nhắm nhịp theo start times, nhưng backlog/executor/overlap semantics phụ thuộc cấu hình và không hứa chạy đúng mỗi 5 giây trong tải nặng.

### Bài D — Cron timezone

Cron `0 0 9 * * MON-FRI` đặt `zone=Asia/Ho_Chi_Minh`. Một CI host đặt timezone UTC. Có nên assert callback ở 09:00 UTC không?

**Đáp án:** Không. Cron dùng business zone explicit; kiểm next occurrence bằng ZonedDateTime/ZoneId.

### Bài E — DST

Job cron 02:30 hằng ngày tại New York. Ngày DST spring-forward 02:30 local không tồn tại. Bạn có thể bảo đảm một callback đúng 02:30 hôm ấy chỉ với @Scheduled không?

**Đáp án:** Không. Định nghĩa misfire/DST policy và dùng trigger/calendar tests, cần scheduler durable nếu contract yêu cầu catch-up.

### Bài F — Test suite bị nhiễu

`@SpringBootTest` khởi động cả CleanupTick và một repository test. Trong lúc assertion, scheduled tick dọn row. Sửa thế nào?

**Đáp án:** Conditional scheduling disabled trong tests thường; test service bằng direct invocation, smoke bật riêng. Không kéo dài sleep.

### Bài G — Cùng job hai lần

Hai threads cùng gọi `processDue()` trên TaskStore. Có thể cùng chuyển task false→true không? Test của demo bảo vệ điều gì, chưa bảo vệ điều gì?

**Đáp án:** Theo computeIfPresent per key chỉ một transition trong JVM; chưa chứng minh exactly once khi nhiều JVM/DB/external side effect.

### Bài H — Multi-pod

Hai Spring Boot pods cùng bật `@Scheduled(cron=...)`. Vì sao báo cáo gửi hai lần? Hãy đề xuất DB claim, distributed lock hoặc durable scheduler.

### Bài I — Quartz/misfire

Ứng dụng tắt từ 08:55 đến 09:15, cron 09:00. Sau restart Spring `@Scheduled` có tự chạy bù lần 09:00 không?

**Đáp án:** Không mặc định cung cấp durable catch-up/misfire guarantees. Nếu yêu cầu, dùng persisted jobs/Quartz/DB job table và policy riêng.

### Bài J — Test timeout

Một test async chỉ dùng `Thread.sleep(500)` rồi kiểm status. Khi CI tải nặng fail. Thay bằng gì?

**Đáp án:** Awaitility `await().atMost(...).untilAsserted(...)` hoặc `CountDownLatch.await(timeout)`, chờ theo condition chứ không đoán tốc độ.

### Bài K — Redis TTL

Bạn inject Clock cố định ngày mai nhưng Redis EXPIRE vẫn dựa server time. Unit test domain và integration test TTL phải khác nhau ra sao?

**Đáp án:** Unit test expected TTL/expiresAt; integration test backend thực và chờ eventual expiry nếu contract yêu cầu.

### Bài L — Future.get

Hai futures được test đồng thời, một future deadlock; `get()` không timeout làm suite treo. Cách cải tiến?

**Đáp án:** `get(duration, TimeUnit)` và `finally shutdownNow`; failure nên hữu hạn. Trong demo pure unit threads rất ngắn; production-grade concurrency regression test cần deadline.

### Bài M — NTP clock skew

Một node fast 2 giây claim jobs, node khác slow 2 giây cho rằng lease còn hiệu lực. Test multi-node nên mô phỏng điều gì?

**Đáp án:** Clock skew, lease/fencing, server-time source, crash/restart và duplicate side effects.

### Bài N — Đo performance

Một dev dùng `Instant.now(clock)` để đo CPU elapsed time của method. Điều gì sai nếu Clock cố định trong test?

**Đáp án:** Duration có thể bằng 0 dù method chạy; dùng monotonic timer `System.nanoTime()`/Micrometer Timer cho elapsed runtime, không dùng business Clock.

## 36. Checklist code review

- [ ] Mọi business deadline/expiry dựa trên inject `Clock` hoặc rõ nguồn thời gian.
- [ ] Production Clock dùng `systemUTC`/zone theo policy, không phụ thuộc default host ngầm.
- [ ] Deadline lưu dưới dạng `Instant` nếu là mốc tuyệt đối.
- [ ] Kiểm trước/đúng/sau deadline, gồm ranh giới một nanosecond.
- [ ] Service chốt một cutoff cho một batch khi business contract yêu cầu.
- [ ] Unit tests không `sleep` để chờ đến deadline.
- [ ] Mutable Clock chỉ dùng trong test, `withZone` có semantics đúng.
- [ ] Cron được kiểm sáu trường, có `ZoneId`/`zone` explicit.
- [ ] Có cases DST/holiday/month-end khi domain phụ thuộc lịch.
- [ ] `fixedRate`/`fixedDelay`/`initialDelay` được chọn theo semantics thật.
- [ ] `@EnableScheduling` và `@Scheduled` được bật có chủ đích.
- [ ] Scheduled adapter mỏng, business method gọi trực tiếp được.
- [ ] Scheduler mặc định disabled hoặc isolated trong các tests không liên quan.
- [ ] Không nhầm thay `Clock` thành đẩy nhanh TaskScheduler/executor.
- [ ] Smoke test scheduling có bounded wait/timeout và assert side effect thật.
- [ ] Không suy số lần tick hoặc exact execution millisecond từ smoke test.
- [ ] Không để scheduled context từ test khác làm bẩn fixtures.
- [ ] Task concurrency/idempotency được kiểm trong JVM và ngoài JVM đúng nhu cầu.
- [ ] Multi-replica scheduler có distributed ownership hoặc claim nếu side effects không được lặp.
- [ ] Có retry/backoff/lease/recovery policy cho tasks critical.
- [ ] Job persistence tồn tại qua restart nếu contract yêu cầu.
- [ ] Ngoại lệ trên scheduled thread được metrics/log/alert đúng, không bị nuốt im lặng.
- [ ] Với async, test chờ completion thực, không chỉ callback được gọi.
- [ ] Reactive virtual time chỉ áp dụng tới Reactor operators/schedulers tương ứng.
- [ ] Backend TTL/DB/server clocks được test ở boundary riêng.
- [ ] Test fixtures/cleanup scoped, không xóa database shared vì scheduler tick.
- [ ] Timezone, UTC offsets, calendar rules được ghi rõ trong API/test contracts.
- [ ] Dùng monotonic timers cho elapsed time, không dựa vào fixed business Clock.
- [ ] Kết luận QA nêu rõ code được review hay đã chạy test thật.

**Kết luận:** **Clock là công cụ kiểm soát thời gian nghiệp vụ; scheduler là công cụ kích hoạt phương thức theo lịch.** Khi tách hai trách nhiệm, phần lớn kiểm thử deadline trở nên hoàn toàn xác định với `Clock.fixed` và mutable test clock. `@Scheduled`, `fixedRate`, `fixedDelay` và cron vẫn cần kiểm wiring ở một số ít smoke tests có timeout, còn các trường hợp multi-instance, DB claiming, retry và “exactly once” phải được kiểm ở hạ tầng đúng cấp. Không thay thế một thiết kế có ranh giới rõ bằng `Thread.sleep(...)` hoặc kỳ vọng mỗi JVM/CI chạy đúng một nhịp không có jitter.

### Tài liệu tham khảo chính thức

- Java 17 — `java.time.Clock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java 17 — `Instant`, `Duration`, `ZonedDateTime`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html
- Spring Framework 6.2 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — `@Scheduled` Javadoc, fixedDelay/fixedRate/cron/timeUnit: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Spring Framework 6.2 — `TaskScheduler` getClock/schedule: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework 6.2 — `CronExpression`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronExpression.html
- Spring Boot 3.5 — Task Scheduling and Pool Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Integration Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- JUnit Jupiter — Lifecycle, parallel execution và timeouts: https://junit.org/junit5/docs/current/user-guide/
- Awaitility — Condition-based asynchronous testing: https://github.com/awaitility/awaitility/wiki/Usage
