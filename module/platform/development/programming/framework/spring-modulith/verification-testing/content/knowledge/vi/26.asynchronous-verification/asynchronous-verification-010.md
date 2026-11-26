# Kiểm tra retry mà không kéo dài toàn bộ test suite

> **Chương:** Async verification  
> **Module:** `SPRING_MODULITH_VERIFICATION_TESTING`  
> **Trọng tâm:** Chứng minh chính sách retry của consumer Spring Modulith hoạt động đúng **mà không bắt mọi JUnit test chờ exponential backoff bằng thời gian thật**. Nội dung tập trung vào failure injection, backoff deterministic, retry budget, kiểm chứng listener sau commit, idempotency và phân tầng quality gate CI.

## 1. Định nghĩa đúng điều cần kiểm tra khi nói “retry hoạt động”

**Vấn đề:** Consumer `shipping` xử lý sự kiện `OrderPlaced(orderId)` và gọi dịch vụ tạo nhãn vận chuyển. API này có thể trả lỗi tạm thời (429/503/network timeout), lỗi vĩnh viễn (payload sai/4xx không retry được) hoặc thành công. Production sử dụng chính sách:

- Tối đa **3 lần gọi** cho **một lần xử lý** (`maxAttempts = 3`, tính cả lần đầu).
- Sau lần thất bại tạm thời thứ nhất chờ 100 ms, sau lần thứ hai chờ 200 ms, giới hạn tối đa 500 ms.
- **Không chờ sau lần thử cuối** vì không còn lần thử nào.
- Lỗi vĩnh viễn được chuyển ra ngay, không retry.
- Nếu retry hết lượt: phải giữ exception hoặc outcome FAILED phù hợp để cơ chế ngoài (publication recovery, dead-letter, workflow state) quyết định tiếp.
- Nếu đã tạo nhãn thành công: ghi business effect theo `orderId` một cách idempotent.

Đối với bài học này, các con số là **hợp đồng minh họa**, không phải thông số Spring Modulith mặc định.

### Vì sao test retry dễ kéo dài suite?

Một test kiểu sau chỉ tình cờ chứng minh workflow đã có kết quả:

~~~java
@Test
void eventually_issues_label() throws Exception {
    placeOrderAndMakeGatewayFailTwice();

    Thread.sleep(5_000);

    assertThat(labelWasCreated()).isTrue();
}
~~~

Nó **luôn chậm ít nhất 5 giây**, không khẳng định đúng số lần gọi, không phân biệt loại lỗi và vẫn có thể flaky khi CI bận. Nhiều test tương tự cộng dồn thời gian và che dấu retry sai chính sách.

Thay vào đó, đặt câu hỏi theo **bằng chứng cần thu**:

| Mệnh đề | Oracle đúng | Có cần chờ thời gian thật? |
| --- | --- | --- |
| 503 hai lần rồi thành công | Kết quả success, số lần gọi = 3 | **Không** |
| Backoff tăng 100 → 200 ms | Danh sách duration được yêu cầu | **Không** |
| Hết 3 lần vẫn fail | Exception cuối, số lần gọi = 3, chỉ 2 backoff | **Không** |
| 400 không retry | Một lần gọi, không pause | **Không** |
| Interrupt trong backoff | Worker ngừng theo policy và giữ interrupt | **Không** |
| `OrderPlaced` được publish | `PublishedEvents` đúng payload | **Không** |
| Consumer sau commit thật sự xử lý | Public business state sau T2 commit | **Có chờ eventual**, nhưng giới hạn ngắn, không sleep cố định |
| Publication pending được replay sau restart | Persistent adapter + recovery outcome | **Có thể tốn hơn**; chỉ ở reliability suite chuyên biệt |
| Retry không tạo side effect trùng | Unique key/idempotent business oracle | Không phải chờ nguyên backoff, cần test concurrency/replay |

**Mục tiêu học tập:** Sau bài học, bạn có thể thiết kế test có thể phân biệt lỗi retry policy, lỗi scheduling, lỗi transaction và lỗi event publication registry mà không buộc toàn bộ suite mô phỏng mỗi giây chờ production.

## 2. Tách ba lớp retry trước khi viết test

Trong ứng dụng modular, cùng một event có thể được thử lại ở nhiều tầng:

~~~mermaid
flowchart TD
    E["OrderPlaced đã commit T1"] --> M["@ApplicationModuleListener"]
    M --> Q["Tạo/duy trì work item PENDING trong T2"]
    Q --> W["Worker processing: gọi LabelGateway"]
    W --> X{"Gateway outcome"}
    X -- "Transient" --> B["Backoff + lần thử tiếp theo"]
    B --> W
    X -- "Success" --> S["Ghi nhãn READY bằng short transaction"]
    X -- "Exhausted/permanent" --> F["FAILED / retry pending theo policy"]
    F --> R["Recovery / replay theo contract"]
~~~

**Đừng coi các lớp retry này là một:**

1. **Call-level retry:** Cùng một lần worker thực thi có nhiều lần gọi `LabelGateway.createLabel`. Đây là nơi kiểm tra `maxAttempts`, backoff và phân loại exception.
2. **Workflow retry:** Một work item PENDING được lên lịch chạy lại về sau, có thể sau restart. Cần kiểm tra durable state, `nextAttemptAt`, terminal outcome và không duplicate.
3. **Event publication replay:** Event Publication Registry có thể theo dõi một publication chưa completed và cho phép resubmit tùy adapter/configuration/version. Đây là một lần **handler invocation mới**, không nhất thiết là “lần thứ tư” của retry gateway.

**Bẫy nhân số lượt:** Nếu mỗi handler invocation gọi gateway tối đa 3 lần, và registry replay handler 3 lần, tổng gateway calls **có thể lên tới 9** trong một kịch bản. Chỉ assert “tối đa 3 lần” tại cấp global event là sai khi hợp đồng chỉ áp dụng per-invocation. Cần idempotency và budget ở đúng lớp.

### Phân tầng test để tránh kéo dài suite

| Test type | Nội dung | Môi trường | Cách tiết kiệm thời gian |
| --- | --- | --- | --- |
| Unit policy | Max attempts, delay cap, transient/permanent | Không Spring | Fake `WaitStrategy`; không ngủ |
| Unit state machine | PENDING → RETRY_WAIT → READY/FAILED | In-memory | Fake clock/scheduler |
| `@ApplicationModuleTest` | Producer publish đúng event | Module bootstrap | Không đợi consumer ngoài scope |
| Worker integration | Gateway fake + DB state/idempotency | Spring/JPA | Fake wait, assert calls và committed state |
| Cross-module integration | `@ApplicationModuleListener` và T1/T2 | Spring + DB | `Awaitility` bounded, chỉ một vài kịch bản |
| Recovery Testcontainers | Pending publication, restart/resubmit | DB persistent | Một nhóm CI riêng, không sao chép vào mọi unit test |
| Critical E2E | API cuối thấy terminal outcome | Web/container | Chỉ vài happy/failure paths bắt buộc |

**Nguyên tắc thiết kế:** Thay vì chỉnh ngưỡng Awaitility xuống quá nhỏ để “tăng tốc”, loại bỏ **thời gian chờ giả lập không cần thiết ở tầng logic** và chỉ dùng thời gian thật tại boundary async cần chứng minh.

## 3. Thiết kế retry core với thời gian chờ có thể thay thế

Mục này tạo một retry executor **thuần Java**, không phụ thuộc Spring context. Nó chấp nhận `WaitStrategy` để production có thể chờ thực, còn test chỉ **ghi nhận duration được yêu cầu**.

### RetryPolicy: đếm lần thử và backoff

**`src/main/java/com/example/shop/shipping/internal/retry/RetryPolicy.java`**

~~~java
package com.example.shop.shipping.internal.retry;

import java.time.Duration;
import java.util.Objects;

public record RetryPolicy(
        int maxAttempts,
        Duration firstDelay,
        Duration maxDelay) {

    public RetryPolicy {
        Objects.requireNonNull(firstDelay);
        Objects.requireNonNull(maxDelay);

        if (maxAttempts < 1
                || firstDelay.isZero()
                || firstDelay.isNegative()
                || maxDelay.compareTo(firstDelay) < 0) {
            throw new IllegalArgumentException(
                    "Invalid retry attempts/delays");
        }
    }

    /**
     * failedAttempt = 1 nghĩa là lần gọi thứ nhất vừa thất bại.
     * Không gọi hàm này khi đã hết maxAttempts.
     */
    public Duration delayAfter(int failedAttempt) {
        if (failedAttempt < 1 || failedAttempt >= maxAttempts) {
            throw new IllegalArgumentException(
                    "No retry after attempt " + failedAttempt);
        }

        Duration current = firstDelay;

        for (int i = 1; i < failedAttempt; i++) {
            // Tránh nhân 2 vượt cap và tránh overflow Duration.
            if (current.compareTo(maxDelay.dividedBy(2)) >= 0) {
                return maxDelay;
            }
            current = current.multipliedBy(2);
        }

        return current.compareTo(maxDelay) > 0
                ? maxDelay
                : current;
    }
}
~~~

Định nghĩa ở đây: `maxAttempts` **tính cả lần đầu**. Nếu `maxAttempts=3`, có thể có **ba calls nhưng chỉ hai delays**. Ví dụ `firstDelay=100ms` và `maxDelay=500ms` cho chuỗi yêu cầu chờ **100ms, 200ms**. Nếu nhiều lần hơn, delay tăng dần cho đến cap.

Policy này cố ý **không có jitter** để phép thử ranh giới dễ xác định. Nếu production thêm jitter, kiểm tra thuật toán với nguồn ngẫu nhiên được inject/seed thay vì so sánh số mili giây thực chạy trên CI.

### WaitStrategy: ranh giới thay thế thời gian thật

**`src/main/java/com/example/shop/shipping/internal/retry/WaitStrategy.java`**

~~~java
package com.example.shop.shipping.internal.retry;

import java.time.Duration;

@FunctionalInterface
public interface WaitStrategy {
    void waitFor(Duration delay) throws InterruptedException;
}
~~~

**`src/main/java/com/example/shop/shipping/internal/retry/ThreadWaitStrategy.java`**

~~~java
package com.example.shop.shipping.internal.retry;

import java.time.Duration;

public final class ThreadWaitStrategy implements WaitStrategy {

    @Override
    public void waitFor(Duration delay)
            throws InterruptedException {
        Thread.sleep(delay.toMillis());
    }
}
~~~

`ThreadWaitStrategy` là adapter **minh họa cho synchronous call-level retry**, không phải lựa chọn mặc định tốt nhất trong mọi Spring listener. Khi backoff dài hoặc có throughput cao, **không giữ transaction JPA mở trong lúc sleep**; tách scheduling khỏi transaction và dùng durable work item/`TaskScheduler` hay queue phù hợp. Đặc biệt, `@ApplicationModuleListener` thường chạy trong transaction riêng: không đặt backoff production kéo dài vào handler transaction đó chỉ vì unit test sử dụng code này.

### RetryExecutor: chỉ retry lỗi có phân loại

**`src/main/java/com/example/shop/shipping/internal/retry/RetryExecutor.java`**

~~~java
package com.example.shop.shipping.internal.retry;

import java.util.Objects;
import java.util.function.Supplier;

public final class RetryExecutor {

    private final RetryPolicy policy;
    private final WaitStrategy waitStrategy;

    public RetryExecutor(
            RetryPolicy policy,
            WaitStrategy waitStrategy) {
        this.policy = Objects.requireNonNull(policy);
        this.waitStrategy = Objects.requireNonNull(waitStrategy);
    }

    public <T> T run(Supplier<T> operation) {
        Objects.requireNonNull(operation);

        for (int attempt = 1; ; attempt++) {
            try {
                return operation.get();
            } catch (TransientGatewayFailure failure) {
                if (attempt >= policy.maxAttempts()) {
                    // Giữ lỗi cuối; không ngủ sau lần thử cuối.
                    throw failure;
                }

                try {
                    waitStrategy.waitFor(policy.delayAfter(attempt));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new RetryInterruptedFailure(
                            "Retry interrupted after attempt "
                                    + attempt,
                            interrupted);
                }
            }
            // IllegalArgumentException, auth/permanent failures,
            // Error... không bị bắt để retry.
        }
    }

    public static final class TransientGatewayFailure
            extends RuntimeException {
        public TransientGatewayFailure(String message) {
            super(message);
        }
    }

    public static final class RetryInterruptedFailure
            extends RuntimeException {
        public RetryInterruptedFailure(
                String message,
                Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Phân loại lỗi là **quyết định nghiệp vụ**: timeout, rate limit/503 có thể transient; invalid credentials, invalid payload thường không nên retry vô hạn. Chỉ bắt `TransientGatewayFailure`, không bắt tất cả `RuntimeException`. Các retry sau mất kết nối có thể gặp tình huống remote đã xử lý request nhưng response bị mất; **idempotency key bằng `orderId`** là cần thiết để tránh nhãn trùng.

### Ranh giới cần lưu ý

- `Thread.sleep(Duration.toMillis())` làm tròn phần nhỏ hơn 1 ms; với policy thời gian nano giây, dùng implementation precision phù hợp hoặc scheduler. Ví dụ giả định delays theo milliseconds.
- Retry executor đồng bộ giữ thread trong quá trình chờ; với job có delay tính bằng phút, nên dùng scheduling bất đồng bộ/durable thay vì một thread chờ.
- Retry executor không tự kiểm soát Spring transaction, không định nghĩa retry registry, không bảo đảm exactly-once.
- Mỗi lời gọi `run` có budget riêng. Nếu handler bị replay nhiều lần, cần giới hạn/recovery policy ở cấp workflow và idempotency.

## 4. JUnit 5 kiểm tra đầy đủ hành vi retry mà không ngủ

**`src/test/java/com/example/shop/shipping/internal/retry/RetryExecutorTest.java`**

~~~java
package com.example.shop.shipping.internal.retry;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import com.example.shop.shipping.internal.retry.RetryExecutor.RetryInterruptedFailure;
import com.example.shop.shipping.internal.retry.RetryExecutor.TransientGatewayFailure;

class RetryExecutorTest {

    private static final RetryPolicy POLICY = new RetryPolicy(
            3,
            Duration.ofMillis(100),
            Duration.ofMillis(500));

    @Test
    void transient_twice_then_success_without_real_wait() {
        var waits = new ArrayList<Duration>();
        var calls = new AtomicInteger();

        var retry = new RetryExecutor(
                POLICY,
                waits::add); // Giá trị return của List.add bị bỏ qua.

        String result = retry.run(() -> {
            if (calls.incrementAndGet() <= 2) {
                throw new TransientGatewayFailure("503");
            }
            return "LABEL-OK";
        });

        assertThat(result).isEqualTo("LABEL-OK");
        assertThat(calls.get()).isEqualTo(3);
        assertThat(waits).containsExactly(
                Duration.ofMillis(100),
                Duration.ofMillis(200));
    }

    @Test
    void exhaustion_throws_on_third_call_without_third_delay() {
        List<Duration> waits = new ArrayList<>();
        AtomicInteger calls = new AtomicInteger();

        var retry = new RetryExecutor(POLICY, waits::add);

        assertThatThrownBy(() -> retry.run(() -> {
            calls.incrementAndGet();
            throw new TransientGatewayFailure("503");
        })).isInstanceOf(TransientGatewayFailure.class)
          .hasMessage("503");

        assertThat(calls.get()).isEqualTo(3);
        assertThat(waits).containsExactly(
                Duration.ofMillis(100),
                Duration.ofMillis(200));
    }

    @Test
    void permanent_failure_is_not_retried() {
        var waits = new ArrayList<Duration>();
        var calls = new AtomicInteger();

        var retry = new RetryExecutor(POLICY, waits::add);

        assertThatThrownBy(() -> retry.run(() -> {
            calls.incrementAndGet();
            throw new IllegalArgumentException("invalid payload");
        })).isInstanceOf(IllegalArgumentException.class);

        assertThat(calls.get()).isEqualTo(1);
        assertThat(waits).isEmpty();
    }

    @Test
    void backoff_is_capped_without_wall_clock_assertion() {
        var policy = new RetryPolicy(
                5,
                Duration.ofMillis(100),
                Duration.ofMillis(250));

        assertThat(policy.delayAfter(1))
                .isEqualTo(Duration.ofMillis(100));
        assertThat(policy.delayAfter(2))
                .isEqualTo(Duration.ofMillis(200));
        assertThat(policy.delayAfter(3))
                .isEqualTo(Duration.ofMillis(250));
        assertThat(policy.delayAfter(4))
                .isEqualTo(Duration.ofMillis(250));

        assertThatThrownBy(() -> policy.delayAfter(5))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

**Điểm quan trọng:** `waits::add` là một method reference cho functional interface có return `void`; Java cho phép bỏ qua return boolean của `List.add` trong ngữ cảnh này. Nếu muốn rõ ràng hơn, dùng `delay -> { waits.add(delay); }`.

### Vì sao test này nhanh mà không mất bằng chứng?

Bởi vì nó assert **lệnh yêu cầu chờ bao lâu**, không đo **thread thực sự bị pause bao lâu**. Các phép thử phân biệt:

- Đúng 3 calls khi fail hai lần, thành công lần thứ ba.
- Đúng 2 delays, không delay thừa sau success/exhaustion.
- Lỗi permanent không retry.
- Giới hạn exponential backoff có áp dụng cap.

**Không viết `assertThat(System.nanoTime() - start).isLessThan(...)` để chứng minh thuật toán.** Đo thời gian chạy là nhiễu của CI; phép đo đúng ở đây là sequence do policy phát ra.

### Kiểm tra interruption riêng, không lây interrupt sang test khác

Một `WaitStrategy` giả có thể ném `InterruptedException`. `RetryExecutor` phải set interrupt flag rồi ném `RetryInterruptedFailure`. Vì thao tác này đặt interrupt flag trên thread đang chạy, **nên thực hiện trong một test-owned worker thread** để không làm bẩn thread của JUnit. Pseudocode:

~~~java
ExecutorService pool = Executors.newSingleThreadExecutor();

try {
    Future<Boolean> f = pool.submit(() -> {
        var retry = new RetryExecutor(
                POLICY,
                delay -> {
                    throw new InterruptedException("cancel");
                });

        try {
            retry.run(() -> {
                throw new TransientGatewayFailure("503");
            });
            return false;
        } catch (RetryInterruptedFailure expected) {
            return Thread.currentThread().isInterrupted();
        }
    });

    assertThat(f.get(2, TimeUnit.SECONDS)).isTrue();
} finally {
    pool.shutdownNow();
    assertThat(pool.awaitTermination(
            2, TimeUnit.SECONDS)).isTrue();
}
~~~

Cần imports Java concurrency, JUnit và AssertJ. Test này chỉ kiểm tra interruption policy, không phải một retry timer chạy lâu.

## 5. Test thời gian bằng virtual scheduling thay vì clock thật

`WaitStrategy` có tác dụng khi **call-level retry đang đồng bộ**. Nếu production dùng delayed tasks (khuyến khích cho backoff dài), test nên thay đồng hồ/scheduler, **không làm production worker sleep hàng phút để kiểm tra một trạng thái**.

### Mô hình state machine với thời điểm được inject

~~~text
PENDING (attempts=0)
   -> RUNNING (attempts=1)
   -> Transient error
   -> RETRY_WAIT (attempts=1, nextAttemptAt = now + 100ms)
   -> Clock advance 100ms (ảo)
   -> RUNNING (attempts=2)
   -> Transient error
   -> RETRY_WAIT (attempts=2, nextAttemptAt = now + 200ms)
   -> Clock advance 200ms (ảo)
   -> RUNNING (attempts=3)
   -> Success -> READY
~~~

Các thành phần nên tách:

| Thành phần | Production | Test |
| --- | --- | --- |
| `Clock` | `Clock.systemUTC()` | `Clock.fixed(...)` hoặc `Clock.offset(...)` |
| Delayed execution | `TaskScheduler`/durable queue | Manual scheduler/virtual-time driver |
| Backoff policy | Duration + jitter theo cấu hình | Deterministic jitter/seed nếu có |
| Gateway | HTTP client thật | Scripted fake: 503, 503, OK |
| Work state | DB PENDING/RETRY_WAIT/READY/FAILED | Query state, assert version/attempt count |
| Event publication | Spring events + registry theo config | Producer test + targeted integration |

### Virtual-time assertion mẫu

~~~java
// Pseudocode: TestClock/TestScheduler/WorkDriver là
// abstractions được thiết kế trong dự án, không có sẵn
// như API mặc định của Spring Modulith.
var clock = new TestClock("2026-01-01T00:00:00Z");
var scheduler = new TestScheduler(clock);
var gateway = scriptedGateway(503, 503, "LABEL-OK");

var worker = new WorkDriver(clock, scheduler, gateway, policy);
worker.start(orderId);

assertThat(worker.attempts(orderId)).isEqualTo(1);
assertThat(worker.nextAttemptAt(orderId))
        .isEqualTo(clock.instant().plusMillis(100));

scheduler.advanceBy(Duration.ofMillis(100));
assertThat(worker.attempts(orderId)).isEqualTo(2);

scheduler.advanceBy(Duration.ofMillis(200));
assertThat(worker.status(orderId)).isEqualTo(READY);
assertThat(worker.attempts(orderId)).isEqualTo(3);
~~~

Đây là **pseudocode test design** để thể hiện cơ chế, chưa copy/paste chạy độc lập. Điểm cốt lõi: kiểm tra **thời điểm do scheduler lên kế hoạch** và **thứ tự state transitions**, không đợi real 300ms trong mỗi test.

### Không nhầm các cơ chế virtual time

- Inject `java.time.Clock` **chỉ** làm code đọc thời gian hiện tại theo clock giả. Nó **không tự làm `Thread.sleep`, `TaskScheduler` hoặc Spring `@Scheduled` chạy nhanh hơn**.
- Virtual-time của Reactor (ví dụ `StepVerifier.withVirtualTime`) chỉ hữu ích với pipeline tương thích và scheduler được điều khiển đúng cách; không tự điều khiển JUnit, JDBC hoặc Spring application events.
- Nếu production framework chỉ có scheduler thật, test backoff policy bằng pure Java và giữ **một** targeted integration smoke test thực cho scheduling, thay vì cố giả “ảo hóa” cả ứng dụng.
- Tránh assertions kiểu “retry thứ hai phải chạy trong đúng 100 ± 2 ms” trên shared CI; có thể thử timing theo khoảng rộng ở smoke test khi thật sự có SLA, nhưng không dùng nó kiểm tra thuật toán core.

## 6. Thiết kế Spring Modulith: listener nhận việc, worker mới retry

Không nên biến `@ApplicationModuleListener` thành chỗ giữ transaction JPA mở trong nhiều giây để `Thread.sleep` giữa các lần gọi remote:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    // Phản mẫu nếu transaction của listener bao cả backoff dài:
    String labelRef = retry.run(
            () -> remoteGateway.issue(event.orderId()));
    receipts.save(new Receipt(event.orderId(), labelRef));
}
~~~

`@ApplicationModuleListener` trong cấu hình Spring Modulith thông dụng xử lý **sau transaction producer commit**, bất đồng bộ và trong transaction mới. Nếu mỗi lần retry ngủ ngay trong listener, hệ thống có thể giữ connection/lock/T2 lâu hơn cần thiết. Test fake wait sẽ che chi phí này nếu production architecture không được review.

### Đặt ba trách nhiệm đúng chỗ

~~~mermaid
sequenceDiagram
    participant O as orders T1
    participant L as shipping listener T2
    participant D as Work-item database
    participant S as Worker/Scheduler
    participant G as LabelGateway

    O->>O: publish OrderPlaced(id)
    O->>O: COMMIT T1
    O-->>L: @ApplicationModuleListener AFTER_COMMIT
    L->>D: create PENDING if absent
    L->>D: COMMIT T2
    Note over L,S: Event đã được nhận, nhãn chưa nhất thiết READY
    S->>D: claim PENDING job
    S->>G: issue(id, idempotencyKey)
    G-->>S: transient 503
    S->>S: schedule backoff / retry
    S->>G: issue(id, same key)
    G-->>S: LABEL-OK
    S->>D: short transaction mark READY
~~~

- **Event ingress:** `OrderPlaced` công khai được gửi tới consumer `shipping`; listener ghi một work item `PENDING`. Listener không cần retry remote API ngay.
- **Retry orchestration:** Một worker xử lý những item đến hạn, áp dụng `RetryPolicy` của mục 3 và giao tiếp external gateway. Với backoff tính bằng giây/phút, scheduler nên lưu `nextAttemptAt`, không giữ thread/DB transaction ngủ.
- **State persistence:** Một bean khác ghi `READY` hoặc trạng thái lỗi với **transaction ngắn**, keyed by `orderId`. Không gộp remote call và DB update vào một transaction dài.

### Public API và internal ports minh họa

**`src/main/java/com/example/shop/orders/OrderPlaced.java`**

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

**`src/main/java/com/example/shop/shipping/LabelStatus.java`**

~~~java
package com.example.shop.shipping;

public enum LabelStatus {
    NOT_FOUND,
    PENDING,
    RETRY_WAIT,
    READY,
    FAILED
}
~~~

**`src/main/java/com/example/shop/shipping/LabelStatusQueries.java`**

~~~java
package com.example.shop.shipping;

import java.util.UUID;

public interface LabelStatusQueries {
    LabelStatus stateFor(UUID orderId);
}
~~~

**`src/main/java/com/example/shop/shipping/internal/LabelGateway.java`**

~~~java
package com.example.shop.shipping.internal;

import java.util.UUID;

public interface LabelGateway {
    String issue(UUID orderId, String idempotencyKey);
}
~~~

**`src/main/java/com/example/shop/shipping/internal/PendingLabelCommands.java`**

~~~java
package com.example.shop.shipping.internal;

import java.util.UUID;

public interface PendingLabelCommands {
    void createPendingIfAbsent(UUID orderId);
}
~~~

**`src/main/java/com/example/shop/shipping/internal/LabelStateWriter.java`**

~~~java
package com.example.shop.shipping.internal;

import java.util.UUID;

public interface LabelStateWriter {
    void markReady(UUID orderId, String labelReference);
}
~~~

Đây là **các port dùng làm contract cho ví dụ**, cần adapter JPA và schema thật. `createPendingIfAbsent` phải chịu duplicate delivery (unique key, conditional insert/upsert), không chỉ `existsById` rồi `save` vì hai listener đồng thời có thể cùng nhìn thấy absent.

### Listener ngắn, không backoff

**`src/main/java/com/example/shop/shipping/internal/OrderPlacedListener.java`**

~~~java
package com.example.shop.shipping.internal;

import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

import com.example.shop.orders.OrderPlaced;

@Component
class OrderPlacedListener {

    private final PendingLabelCommands pending;

    OrderPlacedListener(PendingLabelCommands pending) {
        this.pending = pending;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        pending.createPendingIfAbsent(event.orderId());
    }
}
~~~

### Worker không có outer @Transactional bao remote calls

**`src/main/java/com/example/shop/shipping/internal/LabelWorkProcessor.java`**

~~~java
package com.example.shop.shipping.internal;

import java.util.UUID;

import org.springframework.stereotype.Service;
import com.example.shop.shipping.internal.retry.RetryExecutor;

@Service
class LabelWorkProcessor {

    private final LabelGateway gateway;
    private final LabelStateWriter writer;
    private final RetryExecutor retries;

    LabelWorkProcessor(
            LabelGateway gateway,
            LabelStateWriter writer,
            RetryExecutor retries) {
        this.gateway = gateway;
        this.writer = writer;
        this.retries = retries;
    }

    // Một lượt worker processing; không mở transaction dài.
    void process(UUID id) {
        String key = id.toString();

        String labelReference = retries.run(
                () -> gateway.issue(id, key));

        // Adapter writer triển khai @Transactional ngắn,
        // ghi READY có unique orderId.
        writer.markReady(id, labelReference);
    }
}
~~~

**Giới hạn:** `LabelWorkProcessor.process` chưa phải durable scheduler. Production cần định nghĩa claim/reclaim work item, trạng thái `RETRY_WAIT`, terminal `FAILED` và xử lý crash. Khi `retries.run` ném sau khi exhausted, caller/scheduler phải cập nhật outcome theo policy. Có thể dùng synchronous short retry cho transient 503, nhưng không nên giữ một worker thread chờ backoff dài chỉ vì API này có `WaitStrategy`.

## 7. Cross-module integration test nhanh nhưng vẫn kiểm tra DB commit

Một **integration test có trọng tâm** nên giữ các thành phần Spring thực (producer, event handoff, consumer listener, repository, transaction) nhưng thay hai thứ gây chi phí/lỗi không liên quan: **external provider** và **backoff chờ thời gian thật**.

Giả định dự án có public `OrderCommands.place(customerId)` trả UUID, và implementations của `LabelStatusQueries`, `PendingLabelCommands`, `LabelStateWriter`, `RetryExecutor` tương ứng các ports mục 6. Ví dụ dưới đây là **khung tích hợp cần ghép vào dự án**, không phải toàn bộ ứng dụng độc lập.

**`src/test/java/com/example/shop/shipping/internal/LabelRetryIntegrationTest.java`**

~~~java
package com.example.shop.shipping.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import com.example.shop.ShopApplication;
import com.example.shop.orders.OrderCommands;
import com.example.shop.shipping.LabelStatus;
import com.example.shop.shipping.LabelStatusQueries;
import com.example.shop.shipping.internal.retry.RetryExecutor;
import com.example.shop.shipping.internal.retry.RetryExecutor.TransientGatewayFailure;
import com.example.shop.shipping.internal.retry.RetryPolicy;

@SpringBootTest(
        classes = ShopApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(LabelRetryIntegrationTest.FakeConfig.class)
class LabelRetryIntegrationTest {

    @Autowired OrderCommands orders;
    @Autowired LabelStatusQueries labels;
    @Autowired LabelWorkProcessor worker;
    @Autowired ScriptedGateway gateway;

    @Test
    void transient_twice_then_ready_after_commit() {
        UUID id = orders.place("CUS-" + UUID.randomUUID());

        // @ApplicationModuleListener xử lý sau commit T1.
        // Chờ work item trong T2; không assert tức thời.
        await()
                .atMost(Duration.ofSeconds(4))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(() ->
                        assertThat(labels.stateFor(id))
                                .isEqualTo(LabelStatus.PENDING));

        // Chạy một lượt worker bằng tay (không đợi timer).
        worker.process(id);

        // Mark READY được ghi trong transaction ngắn.
        assertThat(labels.stateFor(id))
                .isEqualTo(LabelStatus.READY);
        assertThat(gateway.callsFor(id)).isEqualTo(3);
        assertThat(gateway.keysFor(id))
                .containsExactly(
                        id.toString(),
                        id.toString(),
                        id.toString());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeConfig {

        @Bean
        @Primary
        RetryExecutor zeroWaitRetryExecutor() {
            return new RetryExecutor(
                    new RetryPolicy(
                            3,
                            Duration.ofMillis(100),
                            Duration.ofMillis(500)),
                    ignoredDelay -> {
                        // Không ngủ thời gian thật trong test.
                    });
        }

        @Bean
        @Primary
        ScriptedGateway scriptedGateway() {
            return new ScriptedGateway();
        }
    }

    static final class ScriptedGateway implements LabelGateway {

        private final ConcurrentHashMap<UUID, AtomicInteger> counts =
                new ConcurrentHashMap<>();
        private final ConcurrentHashMap<
                UUID, ConcurrentLinkedQueue<String>> keys =
                new ConcurrentHashMap<>();

        @Override
        public String issue(UUID id, String idempotencyKey) {
            keys.computeIfAbsent(
                    id, ignored -> new ConcurrentLinkedQueue<>())
                    .add(idempotencyKey);

            int attempt = counts.computeIfAbsent(
                    id, ignored -> new AtomicInteger())
                    .incrementAndGet();

            if (attempt <= 2) {
                throw new TransientGatewayFailure("503");
            }
            return "LABEL-" + id;
        }

        int callsFor(UUID id) {
            var count = counts.get(id);
            return count == null ? 0 : count.get();
        }

        ConcurrentLinkedQueue<String> keysFor(UUID id) {
            return keys.getOrDefault(
                    id, new ConcurrentLinkedQueue<>());
        }
    }
}
~~~

### Test này nhanh ở đâu, và không chứng minh điều gì?

- `FakeConfig` cung cấp `RetryExecutor` dùng **zero-wait strategy** nhưng **giữ nguyên số lần retry và delay policy** (delay policy đã có unit tests ở mục 4).
- `ScriptedGateway` luôn ném transient hai lần đầu rồi success; assert **3 gateway calls** và **cùng idempotency key** trong cả ba attempts.
- `Awaitility` chỉ đợi event hậu commit tạo work item `PENDING`. Nó không ngủ cố định một khoảng giả định.
- `worker.process(id)` được gọi trực tiếp, nên test **không xác minh scheduler production tự kích hoạt đúng giờ**. Thêm **một targeted scheduling smoke test** có trigger/clock được kiểm soát cho điều đó.
- `labels.stateFor(id) == READY` nên thực hiện query mới sau writer transaction commit; nếu adapter dùng asynchronous save, chuyển sang Awaitility bounded.
- `@Primary` chỉ thay bean đúng nếu wiring không bị qualifier/bean resolution khác chi phối. Kiểm tra cấu hình dependency thật.
- Cần **tắt/đóng băng scheduler tự động** trong profile test hoặc dùng controlled scheduler để nó không claim PENDING trước khi test kiểm tra. Không mặc định property `shipping.scheduler.enabled=false` tồn tại nếu dự án chưa định nghĩa.

**Không gắn outer `@Transactional` lên method test**: nó có thể giữ T1 chưa commit và ngăn listener `AFTER_COMMIT`. Test này chủ đích kiểm chứng publication → PENDING transaction, rồi worker → READY transaction.

### So sánh ba phép thử tách rời

| Test | Mệnh đề | Cách chạy nhanh |
| --- | --- | --- |
| Producer `@ApplicationModuleTest` với `PublishedEvents` | `OrderPlaced` đúng ID/payload | Không bootstrap consumer |
| Listener integration | T1 commit → one PENDING work item | Awaitility bounded sau commit |
| Worker retry integration | 503, 503, OK → one READY, 3 calls | Scripted gateway + zero wait |

**Không dùng `PublishedEvents` để kết luận retry đã hoàn tất.** Nó chỉ xác nhận producer đã publish event; cả label attempts và DB outcome nằm ở các ranh giới khác.

## 8. Event Publication Registry, recovery và idempotency: test đúng tầng

Spring Modulith có Event Publication Registry cùng persistence adapters; khi handler thất bại, publication **có thể còn chưa completed** tùy adapter/version/configuration, và được resubmit qua cơ chế được hỗ trợ. Đây là **replay một handler invocation**, khác với call-level retry của `RetryExecutor`.

### Ranh giới registry trong thiết kế bài này

`@ApplicationModuleListener` chỉ ghi `PENDING` và return. Registry có thể ghi nhận publication **đã được xử lý bởi listener**, nhưng external label vẫn chưa READY. Do vậy:

- **Registry completed** chứng minh event đã được listener xử lý theo semantics của registry.
- **Work item PENDING** chứng minh yêu cầu được ghi bền để scheduler có thể xử lý.
- **Label READY** chứng minh bước tạo nhãn đã hoàn tất theo business oracle.
- **Retry exhaustion** không tự quyết định registry status nếu lỗi xảy ra ở worker **sau khi listener đã return**.

### Đừng chờ maintenance timer nhiều phút trong JUnit

Với recovery test, hãy dùng **trigger resubmit rõ ràng theo API thật của version đang dùng**, không `Thread.sleep` một khoảng bằng production recovery interval.

~~~java
// Pseudocode: không phải API tên chuẩn mọi phiên bản
// Spring Modulith. Cần adapter/registry được cấu hình thật.
UUID id = publishAndForceListenerFailure();

assertThat(publications.pendingFor(id))
        .as("Failed listener publication is recoverable")
        .isTrue();

disableFailureInjection();

// Gọi cơ chế resubmit được hỗ trợ thay vì đợi timer.
recovery.resubmitIncomplete();

await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() -> {
            assertThat(workItems.existsFor(id)).isTrue();
            assertThat(publications.pendingFor(id)).isFalse();
        });
~~~

`pendingFor` và `resubmitIncomplete` ở trên là **pseudocode interfaces**, không được tuyên bố có chữ ký đó trong mọi Spring Modulith version. Nếu adapter không hỗ trợ trigger thủ công, dùng profile test với interval nhỏ cho **duy nhất** recovery test, không áp dụng cho mọi unit test.

### Một retry không đồng nghĩa một external effect

~~~text
Attempt 1: POST /labels key=orderId
           provider đã tạo LABEL-42
           response thất lạc -> local timeout

Attempt 2: POST /labels key=orderId
           provider trả lại LABEL-42 theo idempotency key

Local DB: chỉ một row READY (orderId)
~~~

Trong fake provider, tạo map `idempotencyKey → labelRef`; khi cùng key gửi lại, trả label cũ. Assert **một external label** và **một DB row**. Nếu chỉ assert `gateway.callsFor(id) == 2`, bạn chưa chứng minh không sinh duplicate effect.

### Các lỗi reliability dễ bị che

| Hiện tượng | Rủi ro |
| --- | --- |
| Inner retry 3 lần, outer registry replay 3 lần | Có thể 9 remote calls nếu không giới hạn cross-layer |
| T1 commit nhưng listener fail | Publication pending nếu adapter theo dõi; cần recovery |
| Listener ghi PENDING rồi return | Registry completed nhưng label vẫn chưa READY |
| Worker fail sau 2 attempts | Work item cần RETRY_WAIT/FAILED policy riêng |
| Provider đã xử lý request nhưng client timeout | Cần idempotency key/reconciliation |
| Hai workers claim cùng PENDING item | Cần claim atomic, unique constraints, concurrency test |

Không khẳng định exactly-once delivery chỉ từ một test READY. **Exactly-once business effect** phải được bảo vệ bằng idempotency, unique key, xử lý duplicate và test replay.

## 9. Ngân sách CI: nhóm nhiều test không ngủ, ít test có scheduler thật

Không có “một timeout chuẩn” cho tất cả. Chọn oracle và thời hạn theo lớp:

| Nhóm | Bằng chứng | Chi phí chờ hợp lý |
| --- | --- | --- |
| Unit retry | Calls, delays, classification, exhaustion | Không real sleep |
| Unit state machine | PENDING/RETRY_WAIT, `nextAttemptAt` | Clock/scheduler ảo |
| Module publication | Event producer đúng | Không chờ consumer |
| Worker + DB integration | READY/FAILED/idempotency | Fake gateway, zero-wait |
| Cross-module IT | Listener sau commit và T2 visible | Awaitility bounded |
| Scheduler smoke | Đúng job được trigger khi due | Delay test profile nhỏ |
| Registry/DB recovery | Persisted publication, restart/resubmit | Stage chuyên biệt |
| E2E | Client nhìn terminal state | Vài case quan trọng |

### Khi nào dùng duration thật?

Chỉ khi mệnh đề cần chứng minh là **integration với scheduler thực** hoặc một latency target. Ngay cả khi đó, không assert “thực thi chính xác tại 100 ms” trên CI có scheduling jitter; dùng cửa sổ đủ rộng và báo event/attempt timeline. Thuật toán exponential backoff đã được unit test bằng history.

### Các tầng timeout không thay thế nhau

~~~text
per-call gateway timeout
    -> retry policy maxAttempts
    -> scheduled work item deadline
    -> Awaitility atMost cho business terminal state
    -> JUnit @Timeout cho test method
    -> CI job timeout
~~~

`Awaitility.atMost` **không cancel worker** khi hết hạn. Nếu test thất bại, giữ diagnostics: `orderId`, attempt count, failure classification, `nextAttemptAt`, last gateway error, DB state, registry state. Không xóa PENDING publication hoặc work item chỉ để suite xanh.

### Quality gate gắn kiến trúc và behavior

~~~mermaid
flowchart LR
    P["Pull request"] --> U["Retry unit + virtual time"]
    U --> A["ApplicationModules.verify"]
    A --> M["@ApplicationModuleTest publication"]
    M --> I["Fast worker & listener integration"]
    I --> S["Targeted scheduler smoke"]
    S --> G{"Gates bắt buộc đạt?"}
    G -- "Có" --> OK["Merge/release policy"]
    G -- "Không" --> FIX["Sửa retry/timing/transaction"]
    I --> R["Registry recovery stage khi cần"]
~~~

**Architecture test độc lập:**

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithBoundaryTest {

    @Test
    void modules_respect_public_apis() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`shipping` import public `orders.OrderPlaced`, không truy cập `orders.internal.persistence`. `verify()` phát hiện dependency cycle/truy cập ngoài module API theo cấu hình, **không** kiểm tra retry attempts. Giữ cả hai quality gates thay vì dùng một E2E test lớn để thay thế.

### Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Phép kiểm phù hợp |
| --- | --- | --- |
| Retry unit chạy nhiều giây | Dùng production `Thread.sleep` | Fake `WaitStrategy` |
| 3 calls nhưng có 3 delays | Chờ cả sau last attempt | Assert history đúng 2 durations |
| 400 vẫn retry | Catch quá rộng | Permanent-failure test |
| 503 chỉ gọi một lần | Retry config/proxy/classifier sai | Count attempts, bean wiring |
| Backoff cap sai | Phép nhân overflow/giới hạn sai | Policy unit test |
| `Clock.fixed` mà scheduler vẫn đợi thật | Clock không virtualize scheduler | Controlled scheduler/manual advance |
| Producer `PublishedEvents` xanh, label không READY | Listener/worker khác scope | Cross-module IT |
| Label READY nhưng registry pending | Replay khác call-level outcome | Registry state riêng |
| Registry completed nhưng label PENDING | Listener chỉ ghi work item | Đúng boundary; test worker |
| Test PENDING flaky | Scheduler thật claim quá nhanh | Pause scheduler trong test |
| Test timeout sau Spring event | Outer test `@Transactional` rollback T1 | Cho producer commit thật |
| CI chỉ fail khi parallel | Fake/shared data/UUID bị trùng | Test-scoped state, correlation ID |
| Provider tạo hai nhãn | Mất idempotency key | Provider fake/history, unique DB key |

## 10. Bài thực hành và checklist

### Bài thực hành có trọng tâm

1. **Transient + success:** Script 503, 503, OK. Assert đúng 3 calls và danh sách delays `[100ms, 200ms]` nhưng không dùng sleep trong test.
2. **Exhaustion:** Script 503 mãi; assert exception cuối và không đợi sau attempt thứ ba.
3. **Permanent failure:** Script invalid payload/401 cấu hình sai; assert 1 call, 0 delays.
4. **Policy cap:** Dùng 5 attempts, cap 250 ms; assert delay sequence `[100ms, 200ms, 250ms, 250ms]`.
5. **Virtual scheduler:** Dùng fake clock + controlled due-job driver; kiểm tra `nextAttemptAt` và state transitions. Đừng nghĩ `Clock.fixed` tự chạy timer.
6. **Listener và transaction:** Commit `OrderPlaced`, Awaitility đợi một PENDING work item, rồi gọi worker với fake gateway; xác nhận READY trên public query.
7. **Duplicate event/idempotency:** Gửi lại cùng event và mô phỏng response lost sau provider side effect; kiểm tra chỉ một label reference và một DB row.
8. **Registry recovery:** Inject listener failure, query pending publication, trigger resubmit theo API thực của version; không đợi maintenance interval.
9. **CI:** Đưa unit retry, module publication, integration listener/worker và scheduler smoke/recovery theo risk gate. Đo thời gian suite trước/sau khi bỏ sleeps cố định.

### Checklist trước khi merge

- [ ] `maxAttempts` được xác định rõ là số lần gọi **tính cả lần đầu**.
- [ ] Có test transient failure → success và exhausted outcome.
- [ ] Có test permanent fail-fast, unexpected exception và interruption.
- [ ] Không delay sau last attempt/success; assert số waits riêng số calls.
- [ ] Backoff/cap/jitter được kiểm tra bằng data deterministic.
- [ ] Unit tests không cần chờ production `Thread.sleep`.
- [ ] `Clock` giả không bị coi là scheduler ảo nếu chưa inject scheduler.
- [ ] Listener `@ApplicationModuleListener` không giữ transaction mở xuyên backoff dài.
- [ ] Work item `PENDING` được tạo idempotently sau T1 commit.
- [ ] Worker gateway retry và DB writer transaction có ranh giới riêng.
- [ ] Cross-module test có Awaitility bounded, không sleep cố định.
- [ ] Test profile kiểm soát scheduler để không race với driver manual.
- [ ] `PublishedEvents` không bị nhầm với completion của worker.
- [ ] Retry ở cấp gateway, work item, registry được phân biệt.
- [ ] Idempotency key không đổi qua mọi attempts và replays.
- [ ] External effect không nhân đôi khi response thất lạc.
- [ ] Recovery test dùng đúng adapter/version/API, không bịa API.
- [ ] Test data, fake counts và retry queues cô lập giữa các test.
- [ ] Scheduler smoke còn tồn tại, dù phần lớn tests dùng virtual time.
- [ ] `ApplicationModules.verify()` và quality gate CI vẫn được chạy.
- [ ] Khi timeout có diagnostic về attempt, state, failure và publication.

**Ghi nhớ:** Kiểm tra retry nhanh không phải bỏ qua backoff, mà là **đổi thời gian thành dữ liệu có thể kiểm chứng** bằng `WaitStrategy`, fake clock hoặc controlled scheduler. Dùng unit tests cho số lần thử/phân loại lỗi, targeted integration cho event sau commit và state READY, reliability suite cho registry/recovery và idempotency. Như vậy vừa ngăn hồi quy retry của Spring Modulith vừa **không kéo dài toàn bộ test suite**.


