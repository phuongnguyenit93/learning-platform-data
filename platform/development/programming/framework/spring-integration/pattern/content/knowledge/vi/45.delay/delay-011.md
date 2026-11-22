# Kiểm thử thời gian bằng clock kiểm soát

Trong chương **Delay** của **SPRING_INTEGRATION_PATTERN**, nhiều hành vi phụ thuộc thời gian: một message được giữ lại trong Delayer, một retry chờ đến lần thử tiếp theo, một group Aggregator/Resequencer hết hạn, hoặc một yêu cầu chỉ hợp lệ trước deadline. Nếu kiểm thử tất cả bằng `Thread.sleep()` và đo thời gian đồng hồ thực, test thường chậm, khó tái hiện và dễ thất bại ngẫu nhiên trên CI.

**Kiểm thử thời gian bằng clock kiểm soát** nghĩa là biến “bây giờ là lúc nào?” thành một phụ thuộc được cấp cho mã nghiệp vụ. Test có thể cố định hoặc chủ động dịch chuyển thời gian để xác nhận hành vi **trước, đúng và sau** một mốc. Tuy nhiên, chỉ thay `java.time.Clock` **không tự làm bộ lập lịch của Spring Integration Delayer chạy nhanh hơn**. Cần phân biệt đồng hồ nghiệp vụ, scheduler phát message và các ranh giới vận chuyển thực tế.

Bài này hướng dẫn mô hình hóa thời gian, viết `Clock` có thể điều khiển, kiểm thử JUnit không ngủ, đối chiếu với Delayer, và mở rộng sang Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation trong luồng Enterprise Integration Patterns.

> **Nguyên tắc:** Điều kiện nghiệp vụ “đã đến hạn” nên được kiểm tra bằng đồng hồ tiêm vào. Điều kiện “message đã được Delayer giao tới channel” còn phụ thuộc **scheduler, store và dispatcher**; hai điều đó phải được kiểm thử ở những ranh giới khác nhau.

## 1. Vì sao test dùng thời gian thực dễ sai?

Ví dụ một tác vụ chỉ được gửi thông báo sau 5 giây:

```java
// Anti-pattern trong unit test: chậm và phụ thuộc scheduler.
service.scheduleNotification("order-42");
Thread.sleep(5_100);
assertEquals(1, sentNotifications.size());
```

Test này có nhiều điểm yếu:

- Chạy chậm theo thời gian thật, nhân lên theo số test.
- Không kiểm tra rõ **sớm hơn 1 ms**, **đúng hạn** và **sau hạn**.
- Máy CI có thể bận nên callback chưa chạy dù test đã ngủ đủ.
- Một lịch xử lý khác có thể hoàn tất trước khi assertion hoặc tiếp tục sau khi test kết thúc.
- Lệnh ngủ không chứng minh business transaction đã commit, cũng không tạo quan hệ đồng bộ giữa các thread.
- Nếu `service.scheduleNotification()` tạo một tác vụ ở bên ngoài tiến trình, `Thread.sleep` không xác nhận tác vụ đó đã thật sự được lưu bền vững.

Tăng sleep từ 5,1 lên 6 giây chỉ làm test lâu hơn, không đảm bảo loại bỏ flaky. **Muốn test nhanh và đáng tin, hãy thay phụ thuộc thời gian, không kéo dài thời gian đợi.**

## 2. Tách ba câu hỏi về thời gian

Trước khi chọn công cụ, cần biết chính xác hệ thống đang hỏi câu nào:

| Câu hỏi | Ví dụ | Công cụ và phạm vi kiểm thử |
| --- | --- | --- |
| **Bây giờ là lúc nào?** | Thông báo đã đến `notBefore` chưa? | `Clock` tiêm vào domain service; unit test hoàn toàn xác định |
| **Khi nào gọi callback?** | Hẹn giao message sau 2 giây | `TaskScheduler`/scheduler có thể kiểm soát; test lịch và dispatch |
| **Khi nào thao tác khác thật sự hoàn tất?** | Thanh toán đã commit trước khi phát thông báo? | Completion signal, outbox, transaction và idempotency; **không** giải bằng clock |

Đặc biệt cần phân biệt:

- **Thời gian tuyệt đối:** `Instant`, chẳng hạn `2026-11-21T09:00:00Z`, phù hợp để so sánh timestamp hoặc hạn xử lý.
- **Khoảng thời gian:** `Duration.ofSeconds(5)`, dùng tính `dueAt = receivedAt + delay`.
- **Giờ địa phương:** `LocalDateTime` cộng với `ZoneId` để diễn giải “9 giờ sáng Hà Nội”; cần xử lý ngày đổi giờ mùa hè ở những múi giờ có DST.
- **Thời gian đơn điệu/elapsed:** dùng để đo timeout thực thi và hiệu năng. `System.nanoTime()` thường phù hợp để đo elapsed trong JVM hơn việc trừ hai giá trị wall-clock. Nó **không thay thế** `Instant` cho deadline nghiệp vụ.

Một đồng hồ wall-clock có thể bị chỉnh bởi đồng bộ hệ thống hoặc quản trị. Vì vậy không xây dựng bất biến xử lý đồng thời chỉ dựa trên so sánh timestamp.

## 3. Inject `Clock` vào nghiệp vụ

### 3.1. Sai: gọi `Instant.now()` khắp nơi

```java
// Khó test: service tự đọc đồng hồ hệ thống.
boolean readyToSend(Instant notBefore) {
    return !Instant.now().isBefore(notBefore);
}
```

Thời gian test và mã thực thi luôn tiến lên, làm ranh giới đúng hạn khó tái hiện chính xác.

### 3.2. Đúng: truyền `Clock` vào đối tượng

Giả sử một thông báo chỉ được giao trong cửa sổ **[notBefore, expiresAt)**:

- Trước `notBefore`: **WAITING**.
- Tại `notBefore` và trước `expiresAt`: **READY**.
- Tại `expiresAt` hoặc sau đó: **EXPIRED**.

Định nghĩa này là **hợp đồng của ứng dụng**, không phải enum hoặc mặc định của Spring Integration Delayer.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class DeliveryWindowPolicy {

    public enum Decision { WAITING, READY, EXPIRED }

    public record Window(Instant notBefore, Instant expiresAt) {
        public Window {
            Objects.requireNonNull(notBefore, "notBefore");
            Objects.requireNonNull(expiresAt, "expiresAt");
            if (!expiresAt.isAfter(notBefore)) {
                throw new IllegalArgumentException(
                        "expiresAt must be after notBefore");
            }
        }
    }

    private final Clock clock;

    public DeliveryWindowPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Decision evaluate(Window window) {
        Objects.requireNonNull(window);
        Instant now = clock.instant();

        if (!now.isBefore(window.expiresAt())) {
            return Decision.EXPIRED;
        }
        if (now.isBefore(window.notBefore())) {
            return Decision.WAITING;
        }
        return Decision.READY;
    }
}
```

Dùng `Clock.systemUTC()` khi chạy thật, nhưng cấp đồng hồ khác trong test:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock productionClock = Clock.systemUTC();
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-21T09:00:00Z"), ZoneOffset.UTC);

DeliveryWindowPolicy policy = new DeliveryWindowPolicy(testClock);
```

**Lợi ích:** mã nghiệp vụ không phải chờ 1 giây mới đi tới nhánh tiếp theo; test chọn chính xác thời điểm đánh giá, có thể kiểm thử từng mili giây ở biên.

## 4. JUnit: kiểm tra thời điểm trước, tại và sau hạn

Với một cửa sổ từ `09:00:05.000Z` tới trước `09:00:10.000Z`, ta có thể kiểm tra các mốc ngay sát biên:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DeliveryWindowPolicyTest {

    private static final DeliveryWindowPolicy.Window WINDOW =
            new DeliveryWindowPolicy.Window(
                    Instant.parse("2026-11-21T09:00:05Z"),
                    Instant.parse("2026-11-21T09:00:10Z"));

    private static DeliveryWindowPolicy.Decision at(String isoInstant) {
        Clock fixed = Clock.fixed(
                Instant.parse(isoInstant), ZoneOffset.UTC);
        return new DeliveryWindowPolicy(fixed).evaluate(WINDOW);
    }

    @Test
    void waitingImmediatelyBeforeNotBefore() {
        assertEquals(
                DeliveryWindowPolicy.Decision.WAITING,
                at("2026-11-21T09:00:04.999Z"));
    }

    @Test
    void readyExactlyAtNotBefore() {
        assertEquals(
                DeliveryWindowPolicy.Decision.READY,
                at("2026-11-21T09:00:05.000Z"));
    }

    @Test
    void readyImmediatelyBeforeExpiry() {
        assertEquals(
                DeliveryWindowPolicy.Decision.READY,
                at("2026-11-21T09:00:09.999Z"));
    }

    @Test
    void expiredExactlyAtExpiry() {
        assertEquals(
                DeliveryWindowPolicy.Decision.EXPIRED,
                at("2026-11-21T09:00:10.000Z"));
    }
}
```

Các test trên thực thi **ngay lập tức về mặt logic thời gian**: không có `Thread.sleep()`, không phụ thuộc CPU hoặc scheduler. Chúng còn buộc đội phát triển phải xác nhận ranh giới là **bao gồm** `notBefore` và **không bao gồm** `expiresAt`, tránh lỗi off-by-one.

Nhưng nhớ rằng bài test này chỉ chứng minh **hàm quyết định READY/EXPIRED**, không chứng minh Spring Integration đã phát một message đúng lúc.

## 5. Ba cách tạo đồng hồ cho test

| Công cụ | Đặc điểm | Phù hợp |
| --- | --- | --- |
| `Clock.fixed(instant, zone)` | Thời gian không tự chạy | Test một mốc chính xác, boundary và deadline |
| `Clock.offset(base, duration)` | Đọc thời gian từ base cộng offset | So sánh vài thời điểm cố định; hoặc mô phỏng clock lệch |
| `Clock.tick(base, duration)` | Thời gian được làm tròn theo bước | Test nghiệp vụ có độ phân giải thời gian thấp, không phải lập lịch callback |
| `Clock` có thể chỉnh bằng test | Test tự gọi `advance()` | Mô phỏng tuần tự qua các mốc mà không ngủ |

Không nên mặc định `Clock.offset(Clock.systemUTC(), ...)` là hoàn toàn xác định: base vẫn là đồng hồ thật đang chạy. Để có điểm gốc chính xác, dùng `Clock.fixed(...)` hoặc clock điều khiển được.

### 5.1. Tự tạo `MutableClock` cho nhiều bước thời gian

Ví dụ Java 17 sau giữ thời điểm trong `AtomicReference` để test dịch thời gian một cách có chủ đích. Nó không tự đánh thức scheduler; đó là **một nguồn thời gian**, không phải hệ thống hẹn giờ.

```java
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
        this(new AtomicReference<>(Objects.requireNonNull(initial)), zone);
    }

    private MutableClock(
            AtomicReference<Instant> current, ZoneId zone) {
        this.current = Objects.requireNonNull(current);
        this.zone = Objects.requireNonNull(zone);
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

    public void advance(Duration duration) {
        Objects.requireNonNull(duration);
        if (duration.isNegative()) {
            throw new IllegalArgumentException("Do not rewind in this test");
        }
        current.updateAndGet(now -> now.plus(duration));
    }

    public void set(Instant instant) {
        current.set(Objects.requireNonNull(instant));
    }
}
```

Một vài đặc điểm cần chú ý:

- `advance(Duration.ZERO)` giữ nguyên mốc; test chỉ tiến khi chủ động gọi.
- `withZone(...)` cùng chia sẻ nguồn `Instant` nhưng dùng zone khác khi diễn giải lịch.
- `AtomicReference` giúp đọc/ghi `Instant` nguyên tử; **không biến toàn bộ nghiệp vụ thành thread-safe**.
- Không chia sẻ một mutable clock giữa nhiều test chạy song song nếu các test có thể làm lệch thời gian của nhau.
- `set(...)` cho phép tạo test đồng hồ nhảy lùi/nhảy tới; nếu nghiệp vụ không cho phép nhảy lùi, cần có validation ở ranh giới trạng thái chứ không dựa vào clock.

## 6. Kiểm thử một hàng chờ đến hạn bằng clock điều khiển

Một thiết kế dễ test là **tách quyết định đến hạn khỏi hành động phát message**. Trong unit test, một bộ lập lịch thủ công có thể sử dụng `MutableClock` và chỉ thực thi việc phát khi test gọi `drainDue()`.

**Đây là một mô hình kiểm thử thuần Java**, không phải implementation của Spring Integration Delayer. Mục tiêu là kiểm tra semantics: tính `dueAt`, không phát sớm, phát tại hạn, thứ tự các message cùng hạn.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public final class ManualDueQueue {

    private record Pending(
            Instant dueAt, long ordinal, String eventId) {
    }

    private final Clock clock;
    private final PriorityQueue<Pending> pending =
            new PriorityQueue<>(
                    Comparator.comparing(Pending::dueAt)
                            .thenComparingLong(Pending::ordinal));
    private long nextOrdinal;

    public ManualDueQueue(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public void schedule(String eventId, Duration delay) {
        if (eventId == null || eventId.isBlank()
                || delay == null || delay.isNegative()) {
            throw new IllegalArgumentException(
                    "Invalid event or delay");
        }
        pending.add(new Pending(
                clock.instant().plus(delay),
                nextOrdinal++,
                eventId));
    }

    public List<String> drainDue() {
        Instant now = clock.instant();
        List<String> due = new ArrayList<>();

        while (!pending.isEmpty()
                && !pending.peek().dueAt().isAfter(now)) {
            due.add(pending.remove().eventId());
        }
        return due;
    }

    public int pendingCount() {
        return pending.size();
    }
}
```

Ở đây, `dueAt` là thời điểm tuyệt đối tính từ lúc `schedule()` được gọi. Khi `now == dueAt`, message đủ hạn. Trường `ordinal` giúp test lựa chọn thứ tự xác định nếu hai message có cùng `dueAt`.

**Không sử dụng lớp này như scheduler production:** nó không có thread worker, lưu trữ bền vững, transaction, retry, locking đa instance hoặc ACK. Trong production, tất cả những khía cạnh đó phải được thiết kế riêng.

### 6.1. JUnit tiến thời gian mà không ngủ

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class ManualDueQueueTest {

    @Test
    void emitsAtDeadlineAndKeepsDeterministicTieOrder() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-21T09:00:00Z"),
                ZoneOffset.UTC);
        ManualDueQueue queue = new ManualDueQueue(clock);

        queue.schedule("event-A", Duration.ofSeconds(5));
        queue.schedule("event-B", Duration.ofSeconds(5));

        assertEquals(2, queue.pendingCount());
        assertEquals(List.of(), queue.drainDue());

        clock.advance(Duration.ofMillis(4_999));
        assertEquals(List.of(), queue.drainDue());

        clock.advance(Duration.ofMillis(1));
        assertEquals(List.of("event-A", "event-B"),
                queue.drainDue());
        assertEquals(0, queue.pendingCount());

        // drain lặp lại không tự phát lại hai event vừa lấy ra.
        assertEquals(List.of(), queue.drainDue());
    }

    @Test
    void differentDeadlinesReleaseInDeadlineOrder() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-21T09:00:00Z"),
                ZoneOffset.UTC);
        ManualDueQueue queue = new ManualDueQueue(clock);

        queue.schedule("later", Duration.ofSeconds(20));
        queue.schedule("earlier", Duration.ofSeconds(3));

        clock.advance(Duration.ofSeconds(3));
        assertEquals(List.of("earlier"), queue.drainDue());

        clock.advance(Duration.ofSeconds(17));
        assertEquals(List.of("later"), queue.drainDue());
    }
}
```

Kết quả test xác định tuyệt đối về **logic hàng chờ mô phỏng**. Bài test không cần chờ 20 giây thật, nhưng cũng **không xác nhận scheduler thật đã vận hành**, vì ta chỉ gọi `drainDue()` theo ý muốn.

## 7. Delayer trong Spring Integration: clock và scheduler khác nhau

Đây là ranh giới quan trọng nhất khi chuyển từ unit test sang integration test.

Spring Integration Delayer có thể được cấu hình như sau (API và thuộc tính cụ thể cần đối chiếu phiên bản của dự án):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class ScheduledNotificationFlow {

    @Bean
    IntegrationFlow delayedNotifications() {
        return IntegrationFlow.from("acceptedNotifications")
                .delay("notificationDelayGroup",
                        spec -> spec.defaultDelay(5_000L))
                .channel("notificationsDue")
                .get();
    }
}
```

Ý nghĩa: message được tiếp nhận ở `acceptedNotifications` và được Delayer lên lịch chuyển tới `notificationsDue` theo khoảng trễ mặc định đã cấu hình. Hành vi thực tế còn liên quan scheduler, group/message store, thời điểm nhận, timezone và chính sách lỗi/khôi phục.

**Không có quan hệ tự động như sau:**

```text
clock.advance(Duration.ofSeconds(5))
    ≠
Spring Integration Delayer lập tức gọi callback
```

Nếu code nghiệp vụ dùng `Clock` được inject, dịch chuyển clock chỉ thay đổi các lần gọi `clock.instant()`. Một `TaskScheduler` đang sử dụng hệ thống thời gian hoặc thread pool riêng có thể tiếp tục chờ theo thời gian thật.

### 7.1. Ba tầng test nên tách riêng

| Tầng | Phạm vi kiểm chứng | Cách tiến thời gian |
| --- | --- | --- |
| **Unit: chính sách đến hạn** | Cách tính `dueAt`, deadline, expiry, offset, timezone | `Clock.fixed` hoặc `MutableClock.advance` |
| **Component: lập lịch/dispatch** | Khi lịch tới hạn, đúng callback/message được kích hoạt | Scheduler có thể điều khiển, hoặc fake scheduling abstraction do ứng dụng cung cấp |
| **Integration: Spring Integration Delayer thật** | Wiring channel, delay expression, message store, kết quả phát, lỗi, restart | Scheduler/adapter thật hoặc test harness điều khiển được scheduler tương thích phiên bản |

Nếu muốn **virtual time** cho Delayer thật, test phải **kiểm soát scheduler thực sự được endpoint sử dụng**, không chỉ đăng ký một `Clock` bean mà không có endpoint nào tham chiếu. Cần xác minh khả năng thay thế/sử dụng `TaskScheduler` trong phiên bản Spring Integration cụ thể; tên API, khả năng lập lịch lặp và cách xử lý cancellation có thể khác nhau.

Không nên nói “đã kiểm thử Delayer bằng clock giả” nếu test thực tế chỉ gọi `DeliveryWindowPolicy.evaluate()`.

### 7.2. Scheduler giả cần mô phỏng những gì?

Nếu xây dựng một manual/fake scheduler cho integration component, cần hỗ trợ đúng các thao tác mà code được kiểm thử sử dụng:

- Đăng ký tác vụ vào một hàng đợi theo thời điểm `Instant`.
- Chủ động dịch thời gian qua các mốc và chạy **các tác vụ đến hạn**, kể cả tác vụ được sinh ra trong lúc xử lý callback.
- Định nghĩa thứ tự khi nhiều tác vụ trùng deadline.
- Xử lý cancellation, exception, tác vụ lặp lại và trạng thái đã thực hiện khi các tính năng đó được sử dụng.
- Tránh chạy vô hạn khi một callback tự lên lịch lại ngay tại thời điểm hiện tại.
- Xác minh scheduler giả được **inject vào đúng endpoint cần test**, không bị một scheduler mặc định khác thay thế.

Một fake scheduler thiếu hành vi cancellation, fixed-delay hoặc trigger có thể làm test cho kết quả khác production. Vì vậy, **test virtual time nhanh cần đi cùng ít nhất một integration/smoke test với scheduler thật** ở cấu hình gần production.

## 8. Viết integration test Delayer mà không suy đoán thời gian

Khi không có scheduler điều khiển được, vẫn có thể viết integration test thật theo cách ít flaky hơn:

1. Dùng một delay tương đối ngắn cho môi trường test, nhưng không bắt buộc sản phẩm dùng delay ngắn đó.
2. Đưa message có event ID/correlation ID duy nhất vào channel.
3. Đọc đầu ra từ `PollableChannel.receive(timeout)` với **timeout hữu hạn** phù hợp CI.
4. Kiểm tra payload, header, số lần phát và trạng thái exception.
5. Chỉ dùng ranh giới thời gian khi thật sự cần, với **tolerance/độ dư được công bố**.
6. Không dựa vào một lệnh `Thread.sleep(50)` rồi khẳng định callback chắc chắn đã được gọi.

Ví dụ mô tả mẫu assertion ở một integration test đã có `PollableChannel notificationsDue`:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;

// notificationInput được kết nối với flow thực.
// notificationId là ID độc nhất cho test hiện tại.
Message<?> received = notificationsDue.receive(3_000);

assertNotNull(received, "Delayer did not emit within the test deadline");
// Kiểm tra thêm event ID, payload, headers và trạng thái nghiệp vụ.
```

Đoạn này chỉ là **mảnh kiểm thử đặt bên trong test method** với channel đã cấu hình, không phải một test JUnit độc lập. `receive(3_000)` xác nhận một message được nhận **trong cửa sổ chờ**, không tự chứng minh message **không bị phát sớm**.

Để kiểm tra không phát sớm trên scheduler thật, nên so sánh mốc thời gian theo đồng hồ và độ dung sai có thiết kế, kiểm tra cùng điểm đo và tránh biến jitter thành lỗi giả. Với yêu cầu thời gian chính xác đến mili giây, unit/component test dùng clock/scheduler kiểm soát được là nguồn kiểm chứng ranh giới tốt hơn.

## 9. Các trường hợp biên cần thử bằng thời gian ảo

| Trường hợp | Clock trước / sau | Bất biến cần xác minh |
| --- | --- | --- |
| Trước deadline 1 ms | `dueAt - 1 ms` | Không được giao sớm |
| Đúng deadline | `dueAt` | Được chấp nhận theo hợp đồng bao gồm biên |
| Quá deadline 1 ms | `dueAt + 1 ms` | Đã đến hạn, không phải tiếp tục WAITING |
| Delay bằng 0 | `now + Duration.ZERO` | Sẵn sàng theo chính sách; scheduler xử lý đúng zero delay |
| Delay âm | `Duration.ofMillis(-1)` | Reject/định nghĩa rõ chính sách, không âm thầm chuyển |
| Deadline hết hạn | `expiresAt` | Phân biệt `EXPIRED` với `READY` theo quy tắc được công bố |
| Hai message cùng hạn | `A, B` có cùng `dueAt` | Theo thứ tự ổn định **nếu** hợp đồng đòi hỏi |
| Clock nhảy lùi | `now → now - 1 phút` | Không phát sai/trùng; chính sách rõ về thay đổi đồng hồ |
| Clock nhảy tiến | `now → now + 2 giờ` | Xác định cách xử lý tác vụ quá hạn |
| Retry với backoff | Lần 1 fail; tới hạn retry mới thử | Không thử trước thời điểm cho phép |
| Hủy trước thời hạn | Đã schedule rồi cancel | Không phát message đã bị hủy |
| Đến hạn khi ứng dụng tắt | Restart sau `dueAt` | Phục hồi đúng theo chính sách persistent store |
| Đồng thời deadline/expiry | Hai mốc trùng nhau | Quy tắc ưu tiên rõ ràng (ví dụ EXPIRED trước READY) |

**Không chọn các mốc dựa trên thời gian hiện tại của máy developer.** Đặt `Instant` cố định rõ ràng và đánh giá bằng `Clock` do test cung cấp.

### 9.1. Giờ địa phương và daylight saving time

Giả sử yêu cầu nghiệp vụ là “gửi nhắc việc lúc 09:00 theo giờ địa phương của khách hàng”:

- Lưu hoặc truyền `ZoneId` rõ, ví dụ `Asia/Ho_Chi_Minh`, không giả định timezone máy chủ.
- Chuyển thời gian lịch địa phương sang `Instant` theo chính sách; sau đó so sánh bằng `Clock.instant()`.
- Với múi giờ có DST, có những giờ địa phương **không tồn tại** hoặc **xuất hiện hai lần** trong ngày chuyển đổi. Test phải xác định chính sách dời sang thời điểm hợp lệ hoặc chọn offset nào.
- Không lấy “24 giờ” và “ngày mai cùng giờ địa phương” làm một trong mọi múi giờ; `Duration.ofHours(24)` khác `plusDays(1)` quanh ngày đổi DST.

Một cách triển khai cơ bản có thể dùng `ZonedDateTime` và `ZoneId`; chính sách đối với giờ không tồn tại/nhập nhằng phải được thiết kế rõ, không để test phụ thuộc mặc định môi trường.

## 10. Kiểm thử retry/backoff với clock và scheduler kiểm soát

Retry với backoff là một dạng **trì hoãn lần thử tiếp theo**, nhưng không đồng nghĩa Delayer. Một test tốt phải kiểm tra **số attempt**, **thời điểm được phép attempt** và **kết quả cuối**:

```text
T=0s     Thực hiện attempt #1 → lỗi tạm thời
T=2s     Attempt #2 được phép chạy
T=6s     Attempt #3 được phép chạy
T=6s     Thành công → không schedule thêm retry

Test cần assert:
  - attempt không chạy tại T=1.999s;
  - attempt chạy khi scheduler tới T=2s;
  - backoff kế tiếp tính từ đúng mốc quy định;
  - sau thành công không còn tác vụ retry pending.
```

Đừng dùng `Thread.sleep(2_000)` cho mỗi lần retry trong unit test. Tách scheduler hoặc hàm tính `nextAttemptAt` để test bằng clock cố định. Nếu dùng Spring Retry thật, cần xác minh cơ chế backoff/sleep policy của phiên bản thư viện đang sử dụng; **tiêm `Clock` vào service không tự thay thế sleeper của retry library**.

Những trường hợp khác cần thử: attempt giới hạn, lỗi không retryable, cancellation, stop/start endpoint và exception khi lưu lịch retry.

**Lưu ý về idempotency:** Retry chỉ thay đổi *khi nào thử lại*. Nếu lần trước đã commit ở dịch vụ ngoài nhưng phản hồi thất lạc, retry sau 2 giây vẫn có thể tạo hiệu ứng thứ hai. Cần idempotency key hoặc truy vấn outcome, không phải tăng backoff.

## 11. Kiểm thử group timeout và message đến muộn

Trong Aggregator/Resequencer, group có thể chờ đủ số phần mang cùng `correlationId`, hoặc bị xử lý khi timeout. Việc kiểm thử thời gian bao gồm cả **điều kiện release** và **vòng đời của nhóm**.

Ví dụ:

```text
Group G kỳ vọng #1/3, #2/3, #3/3

T=0s    Nhận #1 và #3
T=30s   Chính sách group timeout/expiry được kích hoạt
T=45s   #2 tới muộn sau khi retry xong
```

Test phải xác minh:

1. Ở `T < 30s`, group chưa bị đánh dấu hết hạn nếu đó là hợp đồng.
2. Tại hoặc sau hạn, endpoint xử lý expiry theo policy: partial, discard, fail/recovery hoặc giữ marker.
3. Message `#2` đến sau được phân loại là late arrival, không tự tạo thêm một batch thành công nếu business đã finalization.
4. Duplicate cùng slot và message tới sát timeout không làm release hai lần.
5. `MessageGroupStore` giữ/dọn trạng thái và phối hợp với scheduler đúng như cấu hình.
6. Lỗi/expiry được đưa vào nhánh quản trị phù hợp, không giả định mọi group timeout tự phát `ErrorMessage` lên cùng `errorChannel`.

**Thay `Clock` trong logic kiểm tra deadline của ứng dụng không khiến group timeout nội bộ của Spring Integration tức thì nổ.** Muốn test expiry thật theo virtual time, phải điều khiển scheduler và các phụ thuộc thời gian mà endpoint sử dụng, hoặc chạy integration test với timeout thực được giới hạn và quan sát có dung sai.

Đối với hàng trăm test về chính sách khi hết hạn, có thể test *state machine* thuần Java bằng clock giả. Sau đó dùng một bộ integration test nhỏ kiểm tra wiring và hành vi timer thật trên thư viện đang chạy.

## 12. Test tính đúng đắn thời gian không đồng nghĩa test concurrency

Kiểm soát clock giúp kiểm tra ranh giới thời gian, nhưng **không sửa race condition**. Hai worker có thể cùng thấy `now >= dueAt` rồi cùng phát message, dù đồng hồ được cố định.

Ví dụ:

```text
Worker A: đọc now >= dueAt → true
Worker B: đọc now >= dueAt → true
Worker A: gửi message
Worker B: gửi message
Kết quả: phát hai lần cùng logical event
```

Cần thêm unique constraint, atomic claim, lock/lease, trạng thái `PENDING → CLAIMED → SENT` hoặc idempotency ở downstream. Với nhiều instance, khóa nội bộ một JVM không bảo vệ được database dùng chung.

Một bộ kiểm thử đầy đủ nên kết hợp:

- **Virtual clock** để ép đúng mốc đến hạn.
- **CountDownLatch/barrier** để hai consumer bắt đầu xử lý cùng một tác vụ ở mốc đó.
- **Store bền vững/transaction thực** để kiểm tra chỉ một transition được commit.
- **Fault injection** tại lúc đã claim, lúc publish, trước ACK và sau restart.
- **Quan sát kết quả cuối** ở database, broker hoặc side-effect ledger.

Tránh kết luận “đã sửa race” vì tăng delay làm test đỗ. Delay là cơ chế điều khiển thời điểm, không thay thế quan hệ đồng bộ và tính nguyên tử.

## 13. Ma trận kiểm thử cho Delayer và luồng thông điệp

| Test | Ranh giới | Kỳ vọng |
| --- | --- | --- |
| `notBefore - 1 ms` | Unit business policy | WAITING |
| `notBefore` | Unit business policy | READY |
| `expiresAt - 1 ms` | Unit business policy | READY |
| `expiresAt` | Unit business policy | EXPIRED |
| Hai tác vụ cùng hạn | Unit fake scheduler | Thứ tự ổn định theo hợp đồng mẫu |
| Một tác vụ hạn sớm đặt sau | Unit fake scheduler | Phát theo `dueAt`, không chỉ insertion order |
| Zero/negative delay | Unit policy + scheduler | Zero xử lý đúng, negative bị reject theo hợp đồng |
| Clock nhảy hoặc DST | Unit date-time policy | Giải thích được instant cuối, không lặp vô ý |
| Delayer chuyển message đúng channel | Spring Integration integration | Đúng payload, header, routing và timeout nhận |
| Chưa đến hạn nhưng output có mặt | Component virtual scheduler hoặc integration có dung sai | Phát hiện lỗi phát sớm |
| Scheduler callback thất bại | Integration scheduling | Error/recovery theo cơ chế được cấu hình |
| Application restart trước hạn | Integration + persistent store | Phục hồi hoặc fail có chủ đích |
| Application restart sau hạn | Integration + persistent store | Chính sách catch-up, không phát trùng |
| Retry cần backoff | Retry policy / fake scheduler | Attempt đúng mốc, không retry vô hạn |
| Group hết hạn khi thiếu phần | Aggregator/Resequencer integration | Expiry/partial/fail/recovery đúng policy |
| Message tới sau group timeout | Integration + lifecycle | Late arrival không tạo kết quả thứ hai |
| Hai worker kích hoạt cùng lúc | Concurrency integration | Một side effect nghiệp vụ theo idempotency |
| Transaction commit chậm hơn delay | End-to-end | Không dùng elapsed time để khẳng định commit |

Không cần mọi ca chạy trên scheduler thật. **Số lượng lớn test biên dùng clock giả; số lượng nhỏ test wiring và khôi phục dùng thành phần thật** sẽ cân bằng tốc độ, độ chính xác và khả năng phát hiện lỗi tích hợp.

## 14. Quan sát và chẩn đoán lỗi thời gian

Các trường hữu ích trong log hoặc audit cho message được trì hoãn:

```json
{
  "messageKey": "notification:order-42",
  "correlationId": "order-42:run-3",
  "scheduledAt": "2026-11-21T09:00:00Z",
  "dueAt": "2026-11-21T09:00:05Z",
  "releasedAt": "2026-11-21T09:00:05.147Z",
  "delayPolicy": "notify-after-5s",
  "outcome": "RELEASED"
}
```

Đây là schema **do ứng dụng tự định nghĩa**, không phải bộ header/metric mặc định. Không ghi toàn bộ payload nhạy cảm chỉ để kiểm thử thời gian.

Một số chỉ số cần theo dõi:

| Metric đề xuất | Ý nghĩa |
| --- | --- |
| `scheduledPendingCount` | Tác vụ/message đang chờ tới hạn |
| `oldestOverdueAge` | Thời gian trễ của tác vụ đã quá hạn mà chưa xử lý |
| `scheduleToReleaseLatency` | Thời gian từ lúc nhận lịch tới khi message được phát |
| `releaseLateness` | `releasedAt - dueAt`, dương nếu phát muộn |
| `earlyReleaseCount` | Sự kiện bị phát trước hạn |
| `schedulerExecutionFailureCount` | Callback không được thực hiện thành công |
| `retryAttemptCount` | Mức độ retry và tình trạng backoff |
| `groupExpiryCount` | Group phải xử lý hết hạn |
| `lateArrivalCount` | Message đến sau khi group đã đóng |
| `duplicateSideEffectCount` | Tác động nghiệp vụ lặp do race/replay |

Tên metric trên là gợi ý instrument; không mặc định Spring Integration tạo sẵn đúng tên. Tránh dùng `messageKey` hoặc `correlationId` làm label metric cardinality cao; giữ chúng trong structured log và trace.

Để chẩn đoán một integration test flaky, hãy lưu **dueAt dự kiến, thời gian nhận, scheduler dùng trong test, release policy, clock source, CI load và cửa sổ timeout**. Nếu gặp sai lệch, phân biệt lỗi logic nghiệp vụ với lỗi timer, store hoặc thời gian hệ thống.

## 15. Checklist trước khi kết luận test đạt

1. **Nêu rõ loại thời gian:** absolute timestamp, duration, local schedule hay deadline.
2. **Không gọi `Instant.now()` trong domain code cần test chính xác:** dùng `Clock` được inject.
3. **Kiểm tra biên rõ ràng:** `t-1 ms`, `t`, `t+1 ms` và quy tắc bao gồm/không bao gồm.
4. **Dùng fixed/mutable clock cho unit test:** test không ngủ và không phụ thuộc đồng hồ máy.
5. **Tách clock với scheduler:** dịch `Clock` không đồng nghĩa Delayer callback đã được chạy.
6. **Nếu dùng virtual scheduler, inject vào đúng thành phần:** hỗ trợ những API scheduling thực sự được sử dụng.
7. **Giữ integration test thật:** kiểm tra Spring Integration channel wiring, store, scheduling, lỗi và restart.
8. **Không dùng `Thread.sleep` làm điều kiện đúng:** chờ tín hiệu hoàn tất thực, `receive(timeout)` và assertion có giới hạn.
9. **Chú ý timezone và DST:** lưu `Instant` và `ZoneId` rõ, kiểm tra các mốc địa phương nhập nhằng.
10. **Kiểm tra retry và deadline:** backoff không tự bảo đảm idempotency, timeout không chứng minh mất vĩnh viễn.
11. **Kiểm tra group expiry và late arrival:** không phát batch hoặc tác động cuối hai lần.
12. **Kiểm thử concurrency riêng:** latch, transaction/atomic claim, fault injection ở mốc đến hạn.
13. **Quan sát đúng ranh giới:** lịch được ghi, message được release và business effect được commit là ba giai đoạn khác nhau.
14. **Đo và phân tích flaky:** log clock source, scheduled time, observed time, release jitter và trạng thái các group pending.

**Kết luận:** Kiểm thử thời gian bằng clock kiểm soát giúp chúng ta kiểm tra chính xác một nghiệp vụ **đã đến hạn hay chưa** mà không phải đợi thời gian thật. Với Spring Integration, cần bổ sung một tầng kiểm soát scheduler nếu muốn mô phỏng việc **Delayer thực sự phát message** bằng virtual time. Tách unit test chính sách, component test lập lịch và integration test với endpoint thật giúp bài học về Delay vừa nhanh, vừa xác định, đồng thời không che giấu race condition, lỗi retry hay vấn đề khôi phục thông điệp.

