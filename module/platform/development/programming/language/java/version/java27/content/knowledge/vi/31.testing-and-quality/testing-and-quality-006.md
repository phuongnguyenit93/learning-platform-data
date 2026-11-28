# Kiểm thử thời gian, cancellation và hành vi đồng thời có thể tái lập

Các lỗi liên quan thời gian và lập trình đồng thời thường không xuất hiện theo một thứ tự cố định. Một test có thể chạy tốt trên máy cá nhân nhưng thất bại ngẫu nhiên trong CI vì scheduler thay đổi thứ tự thực thi, thời gian chờ quá ngắn, đồng hồ hệ thống được điều chỉnh, tác vụ đã bị đánh dấu hủy nhưng vẫn tiếp tục chạy, hoặc test quên giải phóng thread.

Bài học trong chương **Kiểm thử và chất lượng** của module **Java 27 và các kiến thức liên quan** tập trung vào ba năng lực:

1. **Kiểm thử thời gian**: kiểm tra deadline, TTL, retry, debounce và các mốc thời gian mà không phụ thuộc vào việc đồng hồ ngoài đời đã chạy bao lâu.
2. **Kiểm thử cancellation**: phân biệt *request cancel*, *trạng thái Future bị cancel*, *tín hiệu interrupt* và *tác vụ thực sự dừng, giải phóng tài nguyên*.
3. **Kiểm thử đồng thời có thể tái lập**: điều khiển các điểm đồng bộ bằng latch, barrier, future hoặc scheduler giả; kiểm tra điều kiện đúng thay vì đoán thứ tự chạy dựa trên `Thread.sleep()`.

Các API Java SE 27 như `Clock`, `Instant`, `Duration`, `System.nanoTime()`, `ExecutorService`, `Future`, `CompletableFuture`, `CountDownLatch`, `CyclicBarrier`, `Phaser`, `Thread.ofVirtual()` và `ScheduledExecutorService` vẫn phù hợp. Các ví dụ unit test dùng **JUnit Jupiter 6.x**, là thư viện kiểm thử bên ngoài JDK; cần khai báo dependency bằng build tool của dự án. Không yêu cầu Java Preview.

> **Mục tiêu quan trọng:** giảm nguồn ngẫu nhiên trong unit test, đồng thời giữ một lớp integration/stress tests để kiểm tra những lỗi thực sự phụ thuộc scheduling. “Có thể tái lập” không có nghĩa luôn tái tạo được mọi race condition bằng cách chạy một lần.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **wall-clock time**, **elapsed time**, **scheduler delay** và **test timeout**.
- Tiêm `Clock` hoặc `InstantSource` vào business logic và kiểm tra đúng tại ranh giới hết hạn.
- Kiểm thử tác vụ được hẹn giờ bằng một **manual/virtual scheduler** có thể chủ động tiến thời gian.
- Biết khi nào `System.nanoTime()` là lựa chọn phù hợp hơn `Instant.now()`.
- Dùng `@Timeout`, `assertTimeout` và `assertTimeoutPreemptively` có ý thức về thread mode và cleanup.
- Phân biệt `Future.cancel(true)`, `CompletableFuture.cancel(true)` và `Thread.interrupt()`.
- Kiểm tra tác vụ hủy có thực sự kết thúc và các resource đã được đóng.
- Dùng `CountDownLatch` để buộc một thread đạt tới điểm xác định trước khi phát tín hiệu cho thread khác.
- Dùng `CyclicBarrier` / `Phaser` khi cần đồng bộ theo nhiều lượt, thay vì tái sử dụng latch đã mở.
- Không đồng nhất kiểm thử tính đúng đắn đồng thời với benchmark hiệu năng hoặc stress test.
- Thiết kế teardown có deadline và thu thập thông tin chẩn đoán khi một test bị treo.
- Viết những test hiện hành cho virtual threads mà không phụ thuộc carrier-thread identity hay thứ tự scheduling.

## 2. Bốn ý nghĩa của “thời gian” trong kiểm thử

### 2.1. Bảng phân biệt

| Loại thời gian | Ví dụ | Nguồn Java điển hình | Cách kiểm thử |
|---|---|---|---|
| **Wall clock** | Phiên đăng nhập hết hạn lúc 09:00 UTC | `Instant.now(clock)`, `Clock` | Dùng `Clock.fixed` / `Clock.offset` |
| **Elapsed time** | Một thao tác đã chờ 250 ms | `System.nanoTime()` | Tiêm time source đơn điệu giả hoặc test bounded wait |
| **Scheduler delay** | Gửi reminder sau 5 phút | `ScheduledExecutorService.schedule` | Tiêm scheduler có `advanceBy` |
| **Test timeout** | Không cho test treo quá 10 giây | JUnit `@Timeout` / `Future.get(timeout)` | Dùng guard ngoài, không dùng làm logic nghiệp vụ |

Những mục tiêu này không thể thay thế nhau. Tiêm một `Clock.fixed` giúp business logic thấy một `Instant` cố định, nhưng **không làm cho `ScheduledExecutorService` tự chạy công việc sau 5 phút ảo**. Ngược lại, `Future.get(1, SECONDS)` chỉ giới hạn thời gian caller chờ kết quả, không sửa mốc hết hạn của một token.

### 2.2. Không dùng Thread.sleep làm điều kiện đúng của test

~~~java
// Dễ flaky: phụ thuộc scheduler và tải CI.
startAsyncWork();
Thread.sleep(100);
assertEquals("DONE", service.status());
~~~

Nếu công việc cần 120 ms do máy CI chậm, test thất bại dù chức năng đúng. Nếu test chạy nhanh, nó cũng có thể âm thầm che lỗi race khi tình cờ thread đã hoàn tất.

Thay bằng **tín hiệu có quan hệ nhân quả**:

~~~java
// Hàm minh họa: worker gọi done.countDown()
// sau khi cập nhật xong trạng thái.
CountDownLatch done = new CountDownLatch(1);
startAsyncWork(done);

assertTrue(done.await(5, TimeUnit.SECONDS));
assertEquals("DONE", service.status());
~~~

Đoạn này là mẫu cấu trúc; `startAsyncWork` và `service` được định nghĩa trong ứng dụng. Timeout 5 giây đóng vai trò **giới hạn bảo vệ khi lỗi**; sự kiện `countDown` mới xác lập rằng công việc đã đạt mốc cần kiểm tra.

### 2.3. Phân biệt “không ngủ” với “không block”

Một test dùng `CountDownLatch.await` vẫn **block có chủ đích** để đợi tín hiệu. Điều này phù hợp nếu có deadline và thread khác thật sự phát tín hiệu. Mục tiêu không phải xóa mọi thao tác chờ; mục tiêu là đợi **đúng điều kiện** thay vì đợi một khoảng thời gian ngẫu nhiên rồi hy vọng điều kiện đã đúng.

## 3. Clock và InstantSource: kiểm tra deadline bằng thời gian giả

### 3.1. Tránh gọi thời gian hệ thống trực tiếp trong business logic

~~~java
final class ExpirationPolicy {
    boolean validUntil(java.time.Instant deadline) {
        return java.time.Instant.now().isBefore(deadline);
    }
}
~~~

Mã trên khó test tại ranh giới nano-giây vì `Instant.now()` luôn thay đổi. Dùng dependency injection với `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

record Permit(Instant expiresAt) {}

final class PermitPolicy {
    private final Clock clock;

    PermitPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    boolean isActive(Permit permit) {
        return Instant.now(clock).isBefore(permit.expiresAt());
    }
}
~~~

Với policy này:

- Trước `expiresAt` → permit còn hiệu lực.
- Đúng bằng `expiresAt` → hết hiệu lực.
- Sau `expiresAt` → hết hiệu lực.

Quyết định dùng `isBefore` thay vì `!isAfter` là quyết định **nghiệp vụ**; test phải phản ánh contract đó.

### 3.2. JUnit kiểm tra ba mốc ranh giới

Lưu class production `PermitPolicy` và record `Permit` như ở trên. Test `PermitPolicyTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class PermitPolicyTest {
    @Test
    void expiresExactlyAtDeadline() {
        Instant deadline =
                Instant.parse("2030-01-01T00:00:00Z");

        Clock atDeadline = Clock.fixed(deadline, ZoneOffset.UTC);
        Permit permit = new Permit(deadline);

        Clock before = Clock.offset(
                atDeadline, Duration.ofNanos(-1));
        Clock after = Clock.offset(
                atDeadline, Duration.ofNanos(1));

        assertTrue(new PermitPolicy(before).isActive(permit));
        assertFalse(new PermitPolicy(atDeadline).isActive(permit));
        assertFalse(new PermitPolicy(after).isActive(permit));
    }
}
~~~

Test không cần `Thread.sleep` và không phụ thuộc múi giờ của máy CI vì sử dụng `Instant` UTC. Mọi lần chạy đều quan sát các mốc như nhau, miễn implementation theo đúng contract.

### 3.3. Clock là nguồn wall-clock, không phải scheduler

Các phương thức phù hợp gồm `Clock.fixed(instant, zone)`, `Clock.offset(base, duration)` và `Clock.systemUTC()`. Với use case chỉ cần thời điểm chứ không cần zone, `InstantSource` cũng là abstraction hiện hành nhẹ hơn `Clock`.

Không nhầm `Clock.offset` với tua nhanh thời gian của tất cả thread trong JVM. Nó chỉ thay kết quả khi code gọi **instance Clock cụ thể đó**. Những API gọi trực tiếp `Instant.now()` hoặc timer thật không bị ảnh hưởng.

### 3.4. Testing múi giờ và DST

Nếu nghiệp vụ là “ngày cuối cùng của tháng tại múi giờ người dùng” thì `LocalDate`, `ZonedDateTime` và `ZoneId` có thể quan trọng hơn chỉ một `Instant`.

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock fixed = Clock.fixed(
        java.time.Instant.parse("2030-04-30T17:00:00Z"),
        zone);

LocalDate businessDate = LocalDate.now(fixed);
~~~

Với nghiệp vụ ở vùng có Daylight Saving Time, cần thêm test những thời điểm đồng hồ địa phương bị lặp hoặc nhảy qua giờ. Đừng chỉ đổi timezone máy bằng `TimeZone.setDefault` trong test chạy song song: đó là global state có thể gây nhiễu test khác.

## 4. Elapsed time: System.nanoTime không phải Instant.now

### 4.1. Vì sao dùng nanoTime cho khoảng thời gian?

`System.nanoTime()` được thiết kế để đo thời gian trôi qua, không đại diện cho một thời điểm lịch cụ thể. Hai kết quả chỉ có ý nghĩa khi lấy **hiệu** giữa chúng trong cùng hệ đo.

~~~java
long started = System.nanoTime();
performWork();
long elapsed = System.nanoTime() - started;
~~~

`started` không phải epoch timestamp; không chuyển trực tiếp nó thành `Instant`. Độ chính xác timer và scheduling thực tế vẫn phụ thuộc runtime/OS.

Wall clock có thể thay đổi do đồng bộ đồng hồ hoặc quản trị hệ thống. Vì vậy, khi tính **timeout theo thời gian trôi qua**, nguồn đơn điệu như `nanoTime` thường phù hợp hơn việc trừ hai lần `System.currentTimeMillis`.

### 4.2. Tạo Ticker có thể giả lập

`Clock` thường dùng cho business instants; nếu kiểm tra elapsed-time logic, có thể tiêm một `LongSupplier` cho time source:

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.function.LongSupplier;

final class ElapsedDeadline {
    private final LongSupplier ticker;
    private final long started;
    private final long budgetNanos;

    ElapsedDeadline(LongSupplier ticker, Duration budget) {
        this.ticker = Objects.requireNonNull(ticker);
        Objects.requireNonNull(budget);

        if (budget.isNegative()) {
            throw new IllegalArgumentException("negative budget");
        }

        this.budgetNanos = budget.toNanos();
        this.started = ticker.getAsLong();
    }

    boolean expired() {
        return ticker.getAsLong() - started >= budgetNanos;
    }
}
~~~

Production tạo bằng `new ElapsedDeadline(System::nanoTime, duration)`. Test có thể điều khiển con số:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class ElapsedDeadlineTest {
    @Test
    void expiresAfterSyntheticElapsedTime() {
        AtomicLong nanos = new AtomicLong(10_000L);

        ElapsedDeadline deadline = new ElapsedDeadline(
                nanos::get, Duration.ofMillis(50));

        assertFalse(deadline.expired());

        nanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(49));
        assertFalse(deadline.expired());

        nanos.addAndGet(TimeUnit.MILLISECONDS.toNanos(1));
        assertTrue(deadline.expired());
    }
}
~~~

Ở đây test **không chờ 50 ms thật**. Đây là một đơn vị logic có thể kiểm chứng chính xác.

### 4.3. Lưu ý về tràn số và contract

`Duration.toNanos()` có thể ném `ArithmeticException` nếu duration quá lớn; ví dụ trên giả định timeout hữu hạn trong giới hạn `long`. Khi dùng `nanoTime()`, mẫu hiệu số hoạt động như một phép đo elapsed-time trong khoảng thời gian hợp lý; không thiết kế deadline kéo dài hàng thế kỷ dựa trên nó.

Nếu nhiều thread cùng đọc/ghi `AtomicLong` giả, việc tăng giá trị sẽ thread-safe, nhưng **không** khiến code chạy theo một scheduling order xác định. Đó là hai tính chất khác nhau.

## 5. Scheduler giả để kiểm thử timer mà không chờ thật

### 5.1. Vì sao Clock.fixed không đủ cho delayed task?

Mã như:

~~~java
scheduler.schedule(task, 5, TimeUnit.MINUTES);
~~~

phụ thuộc **scheduler**. Tiêm `Clock.fixed` vào business logic không làm scheduler thật thực hiện callback tức thì. Muốn test retry/backoff/reminder, nên tiêm một interface hẹn giờ.

### 5.2. Abstraction nhỏ cho ứng dụng

~~~java
import java.time.Duration;

@FunctionalInterface
interface TimerScheduler {
    void schedule(Runnable task, Duration delay);
}
~~~

Production adapter có thể ủy quyền cho `ScheduledExecutorService`:

~~~java
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

record ExecutorTimerScheduler(
        ScheduledExecutorService executor)
        implements TimerScheduler {

    public void schedule(Runnable task, Duration delay) {
        if (delay.isNegative()) {
            throw new IllegalArgumentException("negative delay");
        }
        executor.schedule(
                task, delay.toNanos(), TimeUnit.NANOSECONDS);
    }
}
~~~

Lưu ý: adapter trên bỏ qua `ScheduledFuture<?>` của việc schedule. Với nghiệp vụ yêu cầu **hủy một timer**, interface nên trả lại handle cancellation để test được logic đó, thay vì bỏ qua. Ví dụ kế tiếp chỉ kiểm tra thời điểm chạy, không kiểm thử việc cancel timer.

### 5.3. Ví dụ đầy đủ: manual scheduler trong JUnit

Lưu `ManualSchedulerTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.Comparator;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ManualSchedulerTest {

    interface TimerScheduler {
        void schedule(Runnable action, Duration delay);
    }

    static final class ManualScheduler implements TimerScheduler {
        private record Job(long whenNanos,
                           long sequence,
                           Runnable action) {}

        private final PriorityQueue<Job> queue =
                new PriorityQueue<>(
                        Comparator.comparingLong(Job::whenNanos)
                                .thenComparingLong(Job::sequence));

        private long currentNanos;
        private long nextSequence;

        @Override
        public void schedule(Runnable action, Duration delay) {
            Objects.requireNonNull(action);
            Objects.requireNonNull(delay);

            if (delay.isNegative()) {
                throw new IllegalArgumentException("negative delay");
            }

            long due = Math.addExact(
                    currentNanos, delay.toNanos());
            queue.add(new Job(due, nextSequence++, action));
        }

        void advanceBy(Duration duration) {
            Objects.requireNonNull(duration);
            if (duration.isNegative()) {
                throw new IllegalArgumentException("negative duration");
            }

            long target = Math.addExact(
                    currentNanos, duration.toNanos());

            while (!queue.isEmpty()
                    && queue.peek().whenNanos() <= target) {

                Job next = queue.remove();
                currentNanos = next.whenNanos();
                next.action().run();
            }

            currentNanos = target;
        }

        int queuedTasks() {
            return queue.size();
        }
    }

    static final class Reminder {
        private final TimerScheduler scheduler;
        private final AtomicInteger sent = new AtomicInteger();

        Reminder(TimerScheduler scheduler) {
            this.scheduler = scheduler;
        }

        void remindAfter(Duration delay) {
            scheduler.schedule(sent::incrementAndGet, delay);
        }

        int sentCount() {
            return sent.get();
        }
    }

    @Test
    void reminderRunsAtExactDeadline() {
        ManualScheduler scheduler = new ManualScheduler();
        Reminder reminder = new Reminder(scheduler);

        reminder.remindAfter(Duration.ofMinutes(5));

        scheduler.advanceBy(Duration.ofMinutes(4));
        assertEquals(0, reminder.sentCount());
        assertEquals(1, scheduler.queuedTasks());

        scheduler.advanceBy(Duration.ofMinutes(1));
        assertEquals(1, reminder.sentCount());
        assertEquals(0, scheduler.queuedTasks());
    }
}
~~~

Test này không khởi động thread hoặc timer thật. `ManualScheduler` định nghĩa thứ tự hai công việc có cùng thời điểm bằng `sequence`. Nếu một callback lại schedule thêm một công việc trong cùng khoảng `advanceBy`, scheduler sẽ tiếp tục xử lý theo thứ tự đã khai báo.

**Giới hạn có chủ đích:** manual scheduler này chỉ dành cho test **đơn luồng**. Nó không mô phỏng race giữa các callback, không kiểm chứng thread safety của `ScheduledThreadPoolExecutor`, không có chính sách hủy hoặc fixed-rate scheduling. Đó là nội dung của integration/concurrency tests khác.

### 5.4. Test một retry/backoff policy bằng scheduler

Có thể dùng cùng interface cho quy trình:

~~~text
Attempt 1 --thất bại--> schedule +100 ms
Attempt 2 --thất bại--> schedule +200 ms
Attempt 3 --thành công--> không schedule nữa
~~~

Thay vì đợi 300 ms thật, test gọi `advanceBy(99 ms)`, `advanceBy(1 ms)` rồi kiểm tra số lần attempt; tương tự cho mốc 200 ms. Đây là **logic-time testing**, thích hợp cho retry budget, debounce và TTL refresh.

Các điều kiện như retry tối đa, jitter seed, idempotency và cancellation phải được thiết kế rõ. Nếu ứng dụng sử dụng exponential backoff với random jitter, nên tiêm nguồn random có seed/sequence kiểm soát được vào test, không phụ thuộc vào một chuỗi random thực.

## 6. JUnit timeout: assertTimeout, preemptive và @Timeout

### 6.1. JUnit Jupiter là thư viện ngoài JDK

Những annotation/assertions dưới đây đến từ `org.junit.jupiter.api`. Cần có phiên bản JUnit Jupiter 6.x tương thích với build system; Java SE không tự chứa JUnit.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class TimeoutExamples {
    @Test
    void smallCalculationFinishes() {
        assertTimeout(Duration.ofSeconds(2), () -> {
            int sum = 1 + 2;
            assertEquals(3, sum);
        });
    }
}
~~~

### 6.2. assertTimeout không ngắt preemptive

`assertTimeout(duration, executable)` thực thi trên **thread gọi assertion**, rồi đánh giá giới hạn thời gian. Nếu executable bị kẹt trong một lời gọi không bao giờ kết thúc, `assertTimeout` không có khả năng tự dừng nó ở đúng deadline.

Nó hợp với phép tính hữu hạn có thể đo; không phải **watchdog có khả năng giải phóng tài nguyên** cho một deadlock.

### 6.3. assertTimeoutPreemptively dùng thread khác

~~~java
assertTimeoutPreemptively(
        Duration.ofSeconds(2),
        () -> potentiallyBlockingOperation());
~~~

`assertTimeoutPreemptively` chạy executable trong **thread khác** và có thể báo thất bại sớm khi vượt timeout. Tuy nhiên, việc yêu cầu interrupt **không bảo đảm** công việc đang chạy thực sự dừng ngay.

Đặc biệt, với các framework sử dụng `ThreadLocal` cho transaction, security context hoặc request context, code chạy trong thread khác có thể **không nằm trong cùng transaction** với thread test. Ví dụ một test dựa vào rollback tự động của framework có thể vô tình ghi dữ liệu thật dù assertion bị timeout.

Vì thế, **không thay mọi `assertTimeout` bằng `assertTimeoutPreemptively`**. Ưu tiên API có deadline/cancellation chủ động, test không block vô hạn và ranh giới test-runner bảo vệ khi có lỗi.

### 6.4. @Timeout và ThreadMode

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class BoundedConcurrencyTest {
    @Test
    @Timeout(
            value = 10,
            unit = TimeUnit.SECONDS,
            threadMode = Timeout.ThreadMode.SAME_THREAD)
    void finishesWithinGuard() {
        // Test đồng thời phải có timeout ở từng await/get
        // và dọn tài nguyên trong finally.
    }
}
~~~

`@Timeout` áp dụng cho test/lifecycle methods theo scope của annotation. Thread modes gồm `SAME_THREAD`, `SEPARATE_THREAD`, `INFERRED`. Với `SAME_THREAD`, test chạy trên thread test và khi hết hạn framework cố gửi interrupt. Với `SEPARATE_THREAD`, test chạy ở một thread khác và có các lưu ý `ThreadLocal` tương tự preemptive timeout. `INFERRED` theo cấu hình JUnit.

**Đặt timeout có khoảng dự phòng hợp lý.** Giới hạn quá thấp so với tải CI sẽ khiến test flaky. Timeout chỉ là lớp bảo vệ chống treo, không nên là điều kiện thành công duy nhất.

### 6.5. Timeout nhiều lớp

~~~text
Business deadline:     500 ms (ngữ nghĩa ứng dụng)
Future.get(timeout):   2 s   (giới hạn caller chờ)
JUnit @Timeout:        10 s  (guard khi test lỗi)
CI job timeout:        lớn hơn (chống treo toàn process)
~~~

Những con số trên chỉ là ví dụ phân tầng; giá trị thực phụ thuộc test suite. Một test không nên đợi hết JUnit timeout mới quyết định cleanup vì thread con có thể còn chạy sau đó.

## 7. Cancellation: bốn sự kiện khác nhau

### 7.1. Cancel không phải kill thread

Khi gọi `future.cancel(true)`, phải phân biệt:

1. Caller **yêu cầu hủy**.
2. Future có thể chuyển sang trạng thái **cancelled**.
3. Implementation có thể **interrupt thread** đang chạy để yêu cầu nó ngừng.
4. **Task thật sự kết thúc** và giải phóng tài nguyên.

Bốn sự kiện này không nhất thiết xảy ra tức thời hoặc đồng thời.

~~~mermaid
flowchart TD
    A[Caller requests cancel] --> B{Future implementation}
    B --> C[Future marked cancelled]
    B --> D[May interrupt running thread]
    D --> E{Task cooperates?}
    E -->|Có| F[Task exits and cleans up]
    E -->|Không| G[Task may keep running]
    C --> H[Caller observes CancellationException]
~~~

Một assertion như `assertTrue(future.isCancelled())` **không chứng minh** công việc đã dừng và không còn giữ connection, lock hoặc file.

### 7.2. Future.cancel(true) là cơ chế hợp tác

Theo `Future`, flag `mayInterruptIfRunning` cho phép implementation cố interrupt khi biết thread đang thực thi. Không có bảo đảm tổng quát rằng mọi implementation hoặc mọi loại I/O sẽ phản ứng lập tức.

`cancel(false)` thường muốn tránh ngắt một task đã chạy; nó có thể ngăn task chưa bắt đầu. Nhưng ngay cả `cancel(true)` cũng không bảo đảm thread exit nếu code không hợp tác.

### 7.3. Task phải xử lý InterruptedException

Một worker chờ trong `CountDownLatch.await()`, `BlockingQueue.take()` hoặc `Thread.sleep()` có thể nhận `InterruptedException`. Thông thường, nếu method không thể truyền exception lên caller, hãy khôi phục interrupt status và **thoát**:

~~~java
void runWorker(BlockingQueue<String> queue) {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String item = queue.take();
            process(item);
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    } finally {
        closeWorkerResources();
    }
}
~~~

Ở snippet này, `process` và `closeWorkerResources` là hàm giả định của ứng dụng. Nếu `process` chặn vô hạn ở một API không hỗ trợ interruption, yêu cầu cancel vẫn có thể không giúp task thoát. Cần thiết kế timeout/cancel trực tiếp ở lớp I/O và đóng tài nguyên theo hợp đồng.

Không catch `InterruptedException` rồi lặp lại công việc vô hạn như thể không có tín hiệu dừng.

### 7.4. Thread.interrupted() và isInterrupted()

- `Thread.currentThread().isInterrupted()` **đọc** trạng thái interrupt.
- `Thread.interrupted()` kiểm tra **và xóa** interrupted status của thread hiện tại.

Việc vô ý dùng `Thread.interrupted()` trong vòng kiểm tra có thể tiêu thụ tín hiệu rồi làm cancellation logic sai. Khi bắt `InterruptedException`, nhiều blocking methods đã xóa trạng thái interrupt; nếu không propagate exception, khôi phục trạng thái bằng `Thread.currentThread().interrupt()` thường phù hợp.

## 8. Ví dụ JUnit đầy đủ: kiểm thử Future cancellation

Test sau cố định điểm worker **đã bắt đầu** trước khi yêu cầu cancel. Không dùng sleep để đoán worker đã chạy chưa.

Lưu `CancellationTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class CancellationTest {

    @Test
    @Timeout(value = 10, unit = TimeUnit.SECONDS)
    void cancellationInterruptsCooperativeWorker() throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch neverRelease = new CountDownLatch(1);
        CountDownLatch observedInterrupt = new CountDownLatch(1);

        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> work = executor.submit(() -> {
                entered.countDown();

                try {
                    neverRelease.await();
                } catch (InterruptedException interrupted) {
                    observedInterrupt.countDown();
                    Thread.currentThread().interrupt();
                }
            });

            assertTrue(entered.await(3, TimeUnit.SECONDS),
                    "Worker must reach the synchronization point");

            assertTrue(work.cancel(true));
            assertTrue(work.isCancelled());

            assertThrows(CancellationException.class, work::get);

            assertTrue(observedInterrupt.await(3, TimeUnit.SECONDS),
                    "The worker should observe interruption");
        } finally {
            // Cleanup ngay cả khi một assertion thất bại.
            neverRelease.countDown();
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(
                    3, TimeUnit.SECONDS));
        }
    }
}
~~~

### 8.1. Các assertion kiểm tra điều gì?

- `entered.await(...)` xác nhận worker **đã đi đến** mốc `countDown()`.
- `work.cancel(true)` yêu cầu hủy một `Future` do `ExecutorService.submit` tạo.
- `isCancelled()` và `CancellationException` xác minh **trạng thái future**.
- `observedInterrupt.await(...)` xác minh **worker đã xử lý InterruptedException**.
- `awaitTermination(...)` xác minh executor không còn task đang chạy sau cleanup.

Đây là test dựa trên behavior của executor chuẩn cụ thể, **không phải bằng chứng mọi `Future` implementation trên thế giới luôn interrupt**. Nếu tác vụ không hợp tác, test sẽ thất bại ở assertion chờ interrupt/termination thay vì đợi vô hạn.

### 8.2. Tại sao dùng hai latch khác nhau?

`entered` là mốc “task đã bắt đầu”; `neverRelease` giữ task ở một blocking point; `observedInterrupt` là bằng chứng quan sát được rằng task đã phản ứng với cancellation.

Chỉ có `entered` không đảm bảo worker đang ở `await()` tại microsecond caller gọi cancel, nhưng vì code chờ ngay sau `countDown`, interruption xảy ra trước hoặc trong `await` đều dẫn đến `InterruptedException` được xử lý.

### 8.3. Teardown không nên che mất lỗi chính

Ví dụ ưu tiên ngắn gọn nên đặt assertion `awaitTermination` trong `finally`. Trong dự án lớn, exception phát sinh ở cleanup có thể **che lỗi assertion gốc**. Nên dùng test fixture hoặc pattern ghi lại lỗi cleanup như suppressed, đồng thời thu thập thông tin task còn chạy để chẩn đoán. Quan trọng nhất là **không bỏ cleanup**.

## 9. CompletableFuture.cancel khác Future của ExecutorService

### 9.1. Không giả định mayInterruptIfRunning thực sự có tác dụng

Với `CompletableFuture`, cancellation được xem như một dạng **exceptional completion**. Theo contract của Java SE 27, `cancel(mayInterruptIfRunning)` **không dùng tham số này để điều khiển interruption** của computation ở lớp dưới.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

class CompletableFutureCancellationTest {
    @Test
    void cancelChangesCompletionState() {
        CompletableFuture<String> value = new CompletableFuture<>();

        assertTrue(value.cancel(true));
        assertTrue(value.isCancelled());
        assertTrue(value.isCompletedExceptionally());

        assertThrows(CancellationException.class, value::join);
    }
}
~~~

Test chứng minh future bị hủy và `join` phản ánh trạng thái đó. Nó **không** chứng minh có một thread thực tế bị interrupt.

### 9.2. Timeout của CompletableFuture cũng là completion

~~~java
CompletableFuture<String> result = fetchAsync();

CompletableFuture<String> timed =
        result.orTimeout(2, TimeUnit.SECONDS);
~~~

`orTimeout` hoàn tất **chính `CompletableFuture` được gọi** một cách bất thường với `TimeoutException` nếu chưa xong đúng hạn. Nó trả **this**, không phải một future độc lập. `completeOnTimeout` tương tự nhưng đặt giá trị fallback khi timeout.

Vì vậy, nếu `result` được chia sẻ, timeout đặt lên nó có thể ảnh hưởng những caller khác. Và dù future hoàn tất bởi timeout, request HTTP/SQL hoặc computation phía dưới có thể vẫn đang chạy.

### 9.3. Future.get(timeout) không có nghĩa cancel

~~~java
try {
    String value = future.get(500, TimeUnit.MILLISECONDS);
} catch (java.util.concurrent.TimeoutException timeout) {
    // Caller ngừng chờ; task vẫn có thể tiếp tục chạy.
}
~~~

`get(timeout)` chỉ giới hạn **thời gian caller chờ**. Nếu hợp đồng yêu cầu bỏ công việc, hãy có thao tác cancellation và cleanup thích hợp sau đó; không tự hiểu `TimeoutException` đồng nghĩa task bị hủy.

### 9.4. Test completion trực tiếp: không cần executor thật

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

class CompletionStageTest {
    @Test
    void dependentStageWaitsForExplicitCompletion() {
        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> upper =
                source.thenApply(String::toUpperCase);

        assertFalse(upper.isDone());

        source.complete("ready");

        assertEquals("READY", upper.join());
    }
}
~~~

Đây là **kiểm thử propagation trạng thái**. Nó không test scheduling, không cần thread hay sleep, và rất phù hợp cho business pipeline không cần tính đồng thời thật trong unit test.

Nếu cần test callback scheduling, hãy tiêm một `Executor` kiểm soát được. Đừng mặc định `thenApplyAsync` luôn chạy trên thread mới: callback được executor quyết định; một direct executor có thể chạy ngay trong thread caller.

## 10. Kiểm thử đồng thời có thể tái lập bằng CountDownLatch

### 10.1. Phân biệt causal order và scheduler order

Hãy xác định điều kiện cần thiết:

~~~text
Worker starts
    |
    v
Worker reaches barrier ------- test sees "entered"
    |
    | Test performs assertions
    v
Test releases worker ---------- worker continues
    |
    v
Worker reports completion
~~~

Một test **điều khiển mốc đồng bộ** thường ổn định hơn test viết:

~~~java
// Không đáng tin cậy:
Thread.sleep(200);
assertTrue(workerProbablyStarted);
~~~

### 10.2. CountDownLatch là one-shot gate

~~~java
CountDownLatch ready = new CountDownLatch(1);
CountDownLatch go = new CountDownLatch(1);
~~~

`ready.countDown()` phát tín hiệu; `ready.await()` đợi cho đến khi count bằng zero. Sau khi latch đã mở, nó không thể quay lại trạng thái đóng. Nếu cần nhiều giai đoạn, dùng `CyclicBarrier`, `Phaser` hoặc một giao thức stage/future có hợp đồng rõ ràng.

### 10.3. Happens-before và visibility

Theo contract `CountDownLatch`, các hành động của một thread **trước `countDown`** happens-before các hành động sau một `await` thành công ở thread khác.

Điều này giúp test đọc trạng thái được công bố trước tín hiệu một cách đúng đắn. Nhưng nó không cấp quyền đọc/ghi tùy tiện mọi object shared trước và sau đó: code vẫn phải bảo vệ invariant bằng atomic, lock, volatile hoặc mô hình publish phù hợp.

### 10.4. Khi đợi một latch có timeout

~~~java
assertTrue(ready.await(5, TimeUnit.SECONDS),
        "The worker did not reach the expected state");
~~~

Deadline có thể thất bại do CI quá tải. Chọn giá trị có headroom, ghi đủ ngữ cảnh vào failure message, và không dùng vài mili-giây làm giới hạn mặc định cho scheduling có OS threads thật.

## 11. Ví dụ JUnit đầy đủ: nhiều thread bắt đầu có kiểm soát

Lưu `ConcurrentCounterTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class ConcurrentCounterTest {

    @Test
    @Timeout(value = 15, unit = TimeUnit.SECONDS)
    void incrementsAreVisibleAfterAllWorkersComplete()
            throws Exception {

        int workers = 4;
        int iterations = 10_000;
        AtomicInteger counter = new AtomicInteger();

        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);

        ExecutorService executor =
                Executors.newFixedThreadPool(workers);

        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                tasks.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();

                    for (int n = 0; n < iterations; n++) {
                        counter.incrementAndGet();
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(5, TimeUnit.SECONDS),
                    "Every worker must reach the start gate");

            start.countDown();

            for (Future<?> task : tasks) {
                task.get(5, TimeUnit.SECONDS);
            }

            assertEquals(workers * iterations, counter.get());
        } finally {
            start.countDown();
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(
                    5, TimeUnit.SECONDS));
        }
    }
}
~~~

### 11.1. Vì sao số worker trong pool quan trọng?

Nếu đặt `workers = 8` nhưng dùng pool chỉ có 4 thread, rồi chờ latch `ready` đạt 0 trước khi mở `start`, 4 task đầu chiếm hết 4 worker và đợi gate; 4 task tiếp chưa được chạy để count down. Kết quả là **deadlock trong chính test harness**.

Trong ví dụ, pool size bằng số task chờ ở gate. Không dùng common pool mặc định mà không biết mức parallelism khi cần tất cả các task phải đến điểm barrier.

### 11.2. Test này chứng minh điều gì?

Với `AtomicInteger`, kết quả cuối phải bằng `4 × 10.000` nếu cả bốn task hoàn tất bình thường. `Future.get` cũng mang quan hệ memory consistency giúp caller quan sát kết quả sau task.

Nhưng **không** nên kết luận rằng chạy thành công một lần chứng minh một implementation counter tự viết bằng `value++` luôn đúng. Race có thể không xuất hiện trong một lịch chạy cụ thể. Stress repetition làm tăng cơ hội tìm lỗi, còn correctness của thuật toán phải dựa thêm vào thiết kế đồng bộ/JMM và các kiểm thử chuyên biệt.

### 11.3. Nếu test thất bại

Khi một `Future.get` ném `ExecutionException`, cần kiểm tra `getCause()` để phân biệt lỗi code bên trong với timeout/cancellation. Không ghi log rồi bỏ qua exception khiến test báo xanh.

Với task chưa hoàn tất, `get(timeout)` giúp test thất bại có giới hạn; `shutdownNow` cố yêu cầu dừng, nhưng vẫn cần thiết kế task phản ứng với interrupt để teardown không kẹt.

## 12. CyclicBarrier và Phaser: kiểm tra nhiều pha

### 12.1. Chọn primitive đúng mục đích

| Công cụ | Đặc điểm | Hữu ích khi |
|---|---|---|
| `CountDownLatch` | One-shot, giảm count đến zero | Worker đã sẵn sàng, hoàn tất hoặc test mở gate một lần |
| `CyclicBarrier` | Nhóm số lượng cố định rendezvous rồi tái dùng | Các thread phải gặp nhau ở mỗi vòng |
| `Phaser` | Nhiều phase, đăng ký/hủy participant linh hoạt | Pipeline đồng thời có nhiều lượt hoặc participants động |
| `CompletableFuture` | Stage kết quả/ngoại lệ và dependency | Thử nghiệm pipeline bất đồng bộ theo kết quả |
| `BlockingQueue` | Trao đổi dữ liệu có backpressure | Producer–consumer, xác minh handoff |
| `Semaphore` | Giới hạn số quyền truy cập | Kiểm tra max concurrent permits |

Không có primitive nào làm scheduler của OS hoàn toàn deterministic. Chúng cho phép xây dựng **một phần thứ tự bắt buộc** cần thiết cho test.

### 12.2. Ví dụ hai thread gặp nhau bằng CyclicBarrier

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class BarrierTest {
    @Test
    void bothParticipantsReachRendezvous() throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);

        Thread worker = Thread.ofVirtual().start(() -> {
            try {
                barrier.await(3, TimeUnit.SECONDS);
            } catch (Exception exception) {
                throw new RuntimeException(exception);
            }
        });

        try {
            barrier.await(3, TimeUnit.SECONDS);
            worker.join(java.time.Duration.ofSeconds(3));
            assertFalse(worker.isAlive());
        } finally {
            worker.interrupt();
            worker.join(java.time.Duration.ofSeconds(3));
        }
    }
}
~~~

Đây là ví dụ ngắn để giới thiệu primitive. **Lỗi xảy ra trong thread con** có thể không tự làm test JUnit thất bại nếu test không thu nhận exception đó. Với production-quality tests, nên dùng `Future`, `CompletableFuture` hoặc một `AtomicReference<Throwable>` để truyền exception từ worker về test và assert.

### 12.3. Thận trọng khi barrier bị phá vỡ

Nếu một participant timeout hoặc bị interrupt, `CyclicBarrier` có thể ở trạng thái broken và các thread khác nhận `BrokenBarrierException`. Test phải coi đó là tín hiệu lỗi thật và dọn worker; không catch rồi giả vờ thành công.

`Phaser` thích hợp khi participants đăng ký/hủy theo thời gian. Trong mã test nên dùng timeout của `awaitAdvanceInterruptibly(phase, timeout, unit)` hoặc guard ngoài; `arriveAndAwaitAdvance` không tự có timeout để test khỏi treo khi participant thiếu.

## 13. Virtual threads: kiểm tra đúng hành vi, không kiểm tra carrier

### 13.1. Test cùng các contract đồng thời

Java 27 hỗ trợ virtual threads ổn định. `Thread.ofVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` phù hợp cho I/O concurrency, nhưng **không** làm data race hoặc deadlock tự biến mất.

~~~java
Thread worker = Thread.ofVirtual().start(() -> {
    // Công việc có thể chờ I/O theo contract.
});
worker.join();
~~~

Trong test, nên dùng `join(Duration)` hoặc cơ chế wait bounded phù hợp, và có cleanup. Không viết assertion bắt buộc virtual thread phải chạy trên một carrier thread hoặc OS thread nhất định; scheduler có thể thay đổi.

### 13.2. Cancellation vẫn là hợp tác

~~~java
Thread worker = Thread.ofVirtual().start(() -> {
    try {
        blockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
});
~~~

Ví dụ này giả định `blockingOperation` khai báo `InterruptedException`. Cách tác vụ phản ứng với interruption vẫn là vấn đề contract; virtual thread không biến mọi loại I/O thành cancellable.

### 13.3. ExecutorService.close có thể chờ

`ExecutorService` hiện hành triển khai `AutoCloseable` và `close()` đợi task kết thúc. Với code application bình thường, `try`-with-resources thường hợp lý.

**Nhưng trong test hủy tác vụ bị treo**, chỉ viết:

~~~java
try (var executor =
             java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> waitWithoutCancellation());
}
~~~

có thể khiến test **kẹt khi close** nếu task không bao giờ kết thúc. Đây là snippet tình huống xấu, không phải mẫu nên sao chép; `waitWithoutCancellation` là hàm giả định.

Hãy thiết kế task có stop signal, cleanup và timeout riêng. Khi kiểm thử hủy, việc chờ teardown nên được giới hạn; `shutdownNow` chỉ yêu cầu ngắt và không cam kết mọi task tự động dừng.

### 13.4. ThreadLocal và preemptive test timeout

Nếu đang test transaction framework hoặc code dùng `ThreadLocal`, JUnit `SEPARATE_THREAD` / `assertTimeoutPreemptively` có thể làm ngữ cảnh thực thi khác production. Không bỏ qua test behavior chỉ vì một preemptive timeout làm test “nhanh và xanh”.

## 14. Những race condition cần thử ở ranh giới

### 14.1. Cancellation xảy ra cùng lúc với completion

Một task có thể hoàn tất gần như đồng thời khi caller yêu cầu hủy. Theo `CompletableFuture`, khi cạnh tranh giữa `complete`, `completeExceptionally` và `cancel`, chỉ một thay đổi terminal state giành thắng.

Vì vậy, test không nên cứng nhắc rằng `cancel` **phải** thắng trong mọi lịch:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();

// Nếu hai thread đồng thời complete("ok") và cancel(true),
// test phải chấp nhận một trạng thái terminal hợp lệ,
// không áp đặt winner nếu không có thứ tự nhân quả bắt buộc.
~~~

Nếu business rule yêu cầu “cancel đã được chấp nhận thì callback không còn phát side effect”, cần có trạng thái/cancellation token do ứng dụng quản lý và test đúng contract đó, không chỉ dựa `isCancelled`.

### 14.2. Timeout tới đúng khi kết quả đã sẵn sàng

Kiểm thử các trường hợp:

- Result sẵn trước deadline.
- Result hoàn tất **đúng** deadline.
- Timeout xảy ra trước rồi result đến sau.
- Cancellation xảy ra trước rồi callback attempt completion.
- Task ném exception khi đang được cancel.
- Cleanup gặp lỗi sau khi task đã chuyển terminal state.

Thứ tự xử lý chính xác cần được định nghĩa. Với deadline theo `Instant`, có thể assert ranh giới bằng `Clock.fixed`. Với deadline do scheduler thực thi, manual scheduler có thể sắp xếp events cùng timestamp bằng sequence số thứ tự; test nên nêu rõ policy tie-break này.

### 14.3. Chạy task sau khi future đã cancelled

Ở một số thiết kế, cancellation của `CompletableFuture` không ngắt computation đang chạy. Vì vậy callback nguồn hoặc side effect có thể vẫn xảy ra sau khi consumer quan sát future đã cancel.

Test nên phân biệt hai khẳng định:

1. “Future không trả kết quả cho người chờ nữa.”
2. “Không còn side effect nào chạy trong hệ thống.”

Khẳng định thứ hai cần cơ chế quản lý lifetime/cancellation thực tế; nó mạnh hơn rất nhiều so với `future.isCancelled()`.

## 15. Thu thập lỗi từ thread con và tránh false green

### 15.1. Exception trong thread không tự làm JUnit test fail

~~~java
Thread worker = Thread.ofVirtual().start(() -> {
    throw new IllegalStateException("worker failed");
});

worker.join();
~~~

Một exception không bắt trong worker có thể được báo qua uncaught-exception handler, nhưng `join()` không ném lại exception đó cho test. Nếu chỉ gọi `join` rồi kết thúc test, có nguy cơ **test xanh giả**.

### 15.2. Ưu tiên Future.get để propagate lỗi

~~~java
try (var executor =
             java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {
    java.util.concurrent.Future<Integer> task =
            executor.submit(() -> {
                throw new IllegalStateException("worker failed");
            });

    org.junit.jupiter.api.Assertions.assertThrows(
            java.util.concurrent.ExecutionException.class,
            () -> task.get(3, java.util.concurrent.TimeUnit.SECONDS));
}
~~~

Ở ví dụ này, task không treo và `get` có deadline. Trong test cần xác định **cause** nếu muốn kiểm tra đúng ngoại lệ nghiệp vụ.

### 15.3. Kiểm tra cause chính xác

~~~java
ExecutionException failure = assertThrows(
        ExecutionException.class,
        () -> task.get(3, TimeUnit.SECONDS));

assertInstanceOf(IllegalStateException.class,
        failure.getCause());
~~~

Đây là snippet trong class có `task` và imports tương ứng. Không dùng `assertThrows(Exception.class, ...)` quá rộng rồi coi tất cả lỗi worker đều là mong đợi. `TimeoutException`, `CancellationException` và `ExecutionException` mang ý nghĩa khác nhau.

### 15.4. Thu thập exception bằng CompletableFuture

~~~java
CompletableFuture<String> response = new CompletableFuture<>();
response.completeExceptionally(
        new IllegalArgumentException("bad request"));

CompletionException failure = assertThrows(
        CompletionException.class,
        response::join);

assertInstanceOf(IllegalArgumentException.class,
        failure.getCause());
~~~

Khi dùng `join`, exception hoàn tất bất thường có thể được bọc trong `CompletionException` (trừ những trường hợp như `CancellationException`). Điều cần test là contract lỗi và cause, không phải thông điệp stack trace phụ thuộc implementation.

## 16. Mức độ deterministic và công cụ chuyên sâu

### 16.1. Ba tầng test có vai trò khác nhau

| Tầng | Kỹ thuật | Đặc tính |
|---|---|---|
| **Unit logic** | Clock giả, scheduler giả, future hoàn tất chủ động | Rất tái lập; test ranh giới business |
| **Concurrency integration** | Latch/barrier, bounded executor, real threads, I/O fake | Kiểm tra thread interaction trong những schedule đã dựng |
| **Stress / concurrency correctness research** | Repeat, randomized scheduling, jcstress, fault injection | Tăng độ bao phủ interleavings nhưng không đảm bảo duyệt hết |

Đối với thuật toán lock-free, atomic field và quy tắc Java Memory Model phức tạp, một JUnit test “chạy đúng 1000 lần” vẫn chưa chứng minh thuật toán đúng. **jcstress** là dự án của OpenJDK chuyên hỗ trợ nghiên cứu outcome concurrency và JMM; phù hợp bổ sung khi cần kiểm chứng những tình huống nhiều interleavings.

### 16.2. RepeatedTest không phải chứng minh correctness

~~~java
@org.junit.jupiter.api.RepeatedTest(100)
void repeatedConcurrencyScenario() {
    // Mỗi invocation vẫn phải có setup/teardown độc lập.
}
~~~

Repeat có thể giúp lộ lỗi hiếm, nhưng vẫn phụ thuộc scheduler của máy chạy. Nếu một race chỉ lộ trên architecture khác hoặc khi JIT tối ưu khác, 100 lượt trên cùng laptop không đủ đảm bảo.

### 16.3. Khi nào cần fault injection?

Nên thêm test có kiểm soát cho:

- Worker ném exception **trước** khi countDown.
- Cancellation đến khi task đang chờ lock hoặc I/O.
- Executor từ chối task vì đã shutdown.
- Timeout đến khi hệ thống đang flush/commit.
- Một trong nhiều nhánh async thất bại trong khi nhánh còn lại vẫn chạy.
- Retry callback chạy hai lần do event duplicate hoặc giao thức at-least-once.

Fault injection chủ động tạo điều kiện hiếm; nó đáng tin hơn việc đợi scheduler tình cờ tạo ra lỗi tương tự.

## 17. Thiết kế fixture và teardown an toàn

### 17.1. Mỗi test sở hữu resource của mình

Một test concurrency nên xác định:

- Ai tạo executor, thread, socket, temporary file?
- Ai mở khóa/latch khi assertion thất bại?
- Ai đóng tài nguyên?
- Bao lâu thì cleanup bị xem là không thành công?
- Test khác có thể nhìn thấy state còn lại không?

Đặc biệt, đừng dùng **một static executor** bị chia sẻ giữa các test nếu mỗi test tùy ý `shutdownNow` nó. Điều này tạo phụ thuộc thứ tự test.

### 17.2. Dùng try/finally quanh giao thức chặn

~~~java
CountDownLatch release = new CountDownLatch(1);
ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    Future<?> task = executor.submit(() -> {
        release.await();
        return null;
    });

    // Các bước test có thể ném AssertionError.
} finally {
    release.countDown();
    executor.shutdownNow();
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Worker did not terminate");
    }
}
~~~

Snippet dùng trong method `throws Exception`; không phải class đầy đủ. `release.countDown()` quan trọng vì nó bảo đảm worker có đường thoát nếu logic chính fail.

### 17.3. Không dùng busy-wait vô hạn

~~~java
// Tránh:
while (!state.isReady()) {
    // burn CPU; không timeout
}
~~~

Nếu ứng dụng phải polling state vì không có tín hiệu, dùng bounded polling với deadline đơn điệu và backoff phù hợp; nhưng cho unit test, nên cải thiện API để expose `Future`/latch/event khi có thể.

### 17.4. Kiểm soát parallel test execution

JUnit có thể chạy test song song khi dự án bật cấu hình parallel execution. Các test dùng global locale/timezone, static singleton hoặc shared database state có thể tác động lẫn nhau.

Ưu tiên test fixtures riêng, dependency injection và scope resource độc lập. Nếu bắt buộc sử dụng global state, cần áp dụng cơ chế isolation/serialization phù hợp với JUnit; không giải quyết bằng việc chèn thêm `Thread.sleep`.

## 18. Diagnostics khi concurrency test bị treo hoặc flaky

### 18.1. Thu thập thông tin hữu ích

Khi một test treo trong CI, trước khi chỉ tăng timeout:

1. Ghi **JDK vendor/build**, OS, CPU quota, số workers và test seed (nếu có).
2. Ghi trạng thái latch/phaser, active threads và executor queue nếu API hỗ trợ.
3. Thu thread dump của JVM khi test còn đang treo.
4. Xem có worker đợi một lock hoặc signal mà không thread nào còn khả năng phát không.
5. Xem exception trong thread con có bị nuốt.
6. Kiểm tra teardown còn giữ một executor hoặc resource không thể đóng.

### 18.2. jcmd và ThreadMXBean

HotSpot JDK có các diagnostic commands trong `jcmd` để quan sát thread dump; hỗ trợ cụ thể khác nhau theo bản JDK.

~~~bash
jcmd -l
jcmd <pid> Thread.print
~~~

Đây là lệnh chẩn đoán, không chạy trong mọi unit test bình thường. Trong môi trường container/CI, attach permissions có thể bị hạn chế và command có thể khác ở các VM implementations khác HotSpot.

`ThreadMXBean` của `java.lang.management` cũng hỗ trợ quan sát thông tin thread và deadlock với một số loại lock. Không mặc định rằng mọi dạng deadlock logic (chờ socket, latch không bao giờ mở, queue thiếu producer) sẽ hiện ra như monitor deadlock do `findDeadlockedThreads` phát hiện.

### 18.3. Phân biệt timeout test và deadlock thực

Một test timeout do CI bị pause 5 giây không nhất thiết có deadlock. Một hệ thống bị treo do tương tác lock có thể diễn ra ngay cả khi CPU gần 0%.

Cần kết hợp thread states, stack traces, lock owner, latches và các dependency bên ngoài. Không xem việc tăng timeout từ 5 giây lên 60 giây là cách sửa root cause khi nhiều test đều treo tại cùng một điểm.

## 19. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `Thread.sleep(100)` để đợi event | Test flaky theo máy/CI | Dùng latch, future, callback signal |
| Gọi `Instant.now()` trực tiếp trong logic TTL | Khó test biên hết hạn | Inject `Clock` hoặc `InstantSource` |
| Tưởng `Clock.fixed` khiến timer chạy | Scheduler thật vẫn chờ | Inject scheduler giả, `advanceBy` |
| Dùng `currentTimeMillis` để đo thời gian trôi qua | Wall clock có thể bị điều chỉnh | Dùng `System.nanoTime` hoặc ticker |
| Dùng `System.nanoTime` như epoch timestamp | Sai ý nghĩa | Chỉ dùng hiệu hai mẫu |
| Dùng `assertTimeout` như hard stop | Code có thể vẫn treo | API deadline + outer watchdog |
| Dùng `assertTimeoutPreemptively` cho test transaction | Sai thread-local transaction context | Chọn thread mode cẩn trọng |
| Timeout JUnit cực ngắn | CI tải cao báo lỗi giả | Timeout bảo vệ có headroom |
| Gọi `Future.get(timeout)` rồi nghĩ đã cancel | Worker vẫn có thể chạy | Cancel/cleanup riêng khi cần |
| Gọi `CompletableFuture.cancel(true)` rồi đợi interrupt | CF không dùng flag để interrupt công việc | Cancellation token/I/O cancel thật |
| Chỉ assert `future.isCancelled()` | Chưa chứng minh worker dừng | Theo dõi interruption/termination |
| Nuốt `InterruptedException` | Task bỏ qua yêu cầu dừng | Propagate hoặc restore + exit |
| Dùng `Thread.interrupted()` tưởng chỉ đọc flag | Vô tình xóa flag | Cân nhắc `isInterrupted()` |
| Worker ném exception nhưng test chỉ `join()` thread | Test xanh giả | `Future.get`/outcome channel |
| Pool nhỏ hơn số task đang chờ start barrier | Deadlock trong test | Pool đủ workers hoặc thiết kế gate khác |
| Không mở release latch trong `finally` | Worker treo sau assertion fail | Cleanup trong `finally` |
| Dùng `ExecutorService.close` với task không hợp tác | Test có thể chờ mãi | Thiết kế stop signal + bounded teardown |
| Assert thứ tự scheduling tùy ý | Test flaky | Assert causal ordering, không scheduler order |
| Manual scheduler bị dùng làm test race | Không có concurrency thực | Bổ sung integration/stress tests |
| Dùng `@RepeatedTest` như bằng chứng không có data race | Không bao phủ mọi interleaving | Lý luận JMM + jcstress khi cần |
| Chia sẻ static executor/clock mutable giữa tests | Phụ thuộc thứ tự chạy | Fixture riêng, isolation |
| Chỉ tăng timeout khi test treo | Giấu root cause | Thu thread dump/diagnostics |

## 20. Checklist thiết kế một concurrency test đáng tin

1. **Contract:** test xác minh giá trị cuối, ordering, cancellation, cleanup hay deadline?
2. **Clock:** logic wall-clock có thể tiêm `Clock`/`InstantSource` thay thời gian thật không?
3. **Elapsed:** logic đo thời lượng có dùng một time source monotonic có thể fake không?
4. **Scheduler:** tác vụ hẹn giờ có thể tiến thời gian chủ động không?
5. **Causal synchronization:** dùng latch/barrier/future signal thay `sleep` chưa?
6. **Điều kiện chờ:** mọi `await`/`get` có timeout bảo vệ phù hợp?
7. **Pool capacity:** số worker đủ để những task phải đến barrier có thể thực sự chạy?
8. **Data visibility:** latch, lock, atomic và publication đúng Java Memory Model?
9. **Cancellation:** test state của future **và** việc worker giải phóng resource, không đánh đồng?
10. **Interrupt:** code bắt `InterruptedException` có propagate hoặc restore-and-exit?
11. **Terminal races:** outcome khi completion tranh với timeout/cancel có được đặc tả?
12. **Error propagation:** exception ở worker có trở về test qua `Future.get`/completion stage?
13. **Virtual threads:** test không phụ thuộc carrier identity?
14. **Cleanup:** kể cả assertion fail, latch được mở và executor/task được shutdown?
15. **No global leaks:** không giữ static mutable state, zone/time hoặc active threads qua test khác?
16. **JUnit thread mode:** preemptive timeout có thể thay đổi ThreadLocal/transaction không?
17. **Stress tier:** đã phân biệt deterministic unit, integration và JMM stress?
18. **Diagnostics:** có đủ log/seed/thread dump khi CI fail?
19. **Measurement:** test timing có so sánh đúng clock, tránh ngưỡng độ trễ quá sát?
20. **Dependency status:** ví dụ chỉ dùng JDK stable + JUnit Jupiter hiện hành, không vô tình dùng preview/legacy API?

## 21. Câu hỏi tự kiểm tra

1. Vì sao `Thread.sleep(100)` không chứng minh một task đã hoàn tất?
2. `Clock.fixed` kiểm soát được những lời gọi API nào và không kiểm soát được scheduler nào?
3. Nếu permit hết hạn đúng tại `Instant deadline`, test nên xét mấy trường hợp ranh giới?
4. Khi nào nên chọn `System.nanoTime` thay `Instant.now`?
5. Vì sao một giá trị `nanoTime()` không thể được xem như Unix epoch nanoseconds?
6. Lợi ích của `LongSupplier`/ticker trong unit test thời gian trôi qua là gì?
7. Manual scheduler có thể phát hiện data race giữa hai executor worker thực không?
8. Khác nhau giữa `assertTimeout` và `assertTimeoutPreemptively` về thread và khả năng dừng?
9. Vì sao `@Timeout(threadMode = SEPARATE_THREAD)` có thể nguy hiểm với transaction dựa vào `ThreadLocal`?
10. `Future.get(timeout)` có tự động gọi `cancel` khi quá hạn không?
11. `Future.cancel(true)` có bảo đảm mọi code native/I/O dừng ngay không?
12. `CompletableFuture.cancel(true)` có bảo đảm interrupt một task đang chạy không?
13. Vì sao test cancellation cần một latch ghi nhận worker đã phản ứng với interrupt?
14. `CountDownLatch` khác `CyclicBarrier` về khả năng tái sử dụng?
15. Vì sao pool bốn thread với tám task chờ ở start gate có thể deadlock test?
16. Sau `CountDownLatch.countDown` và `await` thành công có quan hệ happens-before nào?
17. Vì sao chỉ `Thread.join` không bảo đảm JUnit nhìn thấy exception ở worker?
18. `ExecutorService.close()` có thể là vấn đề khi task không hợp tác cancellation như thế nào?
19. Với cuộc đua giữa `complete` và `cancel`, test nên assert winner hay assert một tập outcome hợp lệ?
20. Tại sao 1000 lần `@RepeatedTest` pass vẫn không chứng minh một thuật toán lock-free đúng?
21. Khi một concurrency test treo trong CI, những dữ liệu nào nên thu trước khi tăng timeout?
22. Virtual threads làm thay đổi những quy tắc nào về thread scheduling và **không** làm thay đổi những quy tắc nào về data race/cancellation?

## 22. Tài liệu tham khảo chính thức và hiện hành

- [Java SE 27 API — Clock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html): injecting clock, `fixed`, `offset` và unit test phụ thuộc ngày giờ.
- [Java SE 27 API — InstantSource](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/InstantSource.html): nguồn instant có thể được tiêm độc lập với timezone.
- [Java SE 27 API — Instant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html): ranh giới thời điểm và so sánh chính xác.
- [Java SE 27 API — Duration](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Duration.html): biểu diễn timeout/delay với đơn vị rõ ràng.
- [Java SE 27 API — System](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html): `nanoTime()` và `currentTimeMillis()`.
- [Java SE 27 API — Future](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `get(timeout)`, trạng thái cancellation và memory consistency.
- [Java SE 27 API — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancellation là exceptional completion, timeout và dependent actions.
- [Java SE 27 API — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, `shutdownNow`, `awaitTermination`, lifecycle và `close`.
- [Java SE 27 API — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): scheduling delay và `ScheduledFuture`.
- [Java SE 27 API — CountDownLatch](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot barrier, memory effects, bounded await.
- [Java SE 27 API — CyclicBarrier](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): rendezvous giữa các thread, broken barrier.
- [Java SE 27 API — Phaser](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Phaser.html): nhiều pha với participants linh hoạt.
- [Java SE 27 API — Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html): interruption, virtual threads và bounded join.
- [Java SE 27 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread diagnostics và deadlock inspection.
- [Java SE 27 JLS — Chapter 17, Threads and Locks](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-17.html): Java Memory Model, happens-before và data races.
- [JUnit Jupiter 6.1.3 — Timeouts](https://docs.junit.org/6.1.3/writing-tests/timeouts.html): `@Timeout`, `ThreadMode`, test lifecycle và cấu hình timeout.
- [JUnit Jupiter 6.1.3 — Assertions](https://docs.junit.org/6.1.3/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html): `assertTimeout`, `assertTimeoutPreemptively`, `assertThrows` và `assertInstanceOf`.
- [OpenJDK jcstress](https://openjdk.org/projects/code-tools/jcstress/): bộ công cụ concurrency stress tests cho các outcome theo Java Memory Model.

**Ghi chú phạm vi:** các ví dụ minh họa cơ chế, chưa phải bộ test đã chạy trên ứng dụng thật. Chúng chỉ dựa trên API Java SE 27 ổn định và JUnit Jupiter 6.x; một số snippet chỉ là cấu trúc cần đặt trong class có import thích hợp, còn các class test được nêu rõ có thể được đưa vào dự án đã khai báo JUnit để kiểm thử. Không sử dụng Structured Concurrency preview hoặc những API đã bị loại bỏ.
