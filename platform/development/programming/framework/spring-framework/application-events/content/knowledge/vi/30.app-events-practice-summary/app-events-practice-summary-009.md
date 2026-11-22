# Mô phỏng lỗi và retry trong Spring Framework Application Events

Một `ApplicationEventPublisher.publishEvent(...)` không phải là hàng đợi message bền vững và **không tự retry tất cả listener** nếu xử lý gặp lỗi. Trong Spring Framework, listener `@EventListener` thông thường được gọi đồng bộ theo cấu hình mặc định; exception chưa xử lý có thể lan về publisher và làm dừng vòng multicast. Với `@Async @EventListener`, lỗi thường xảy ra trong worker thread nên không đi ngược trực tiếp đến lệnh `publishEvent`. Với `@TransactionalEventListener(AFTER_COMMIT)`, lỗi của listener xảy ra **sau khi transaction nguồn đã commit**, vì vậy không thể dùng rollback nguồn để “thử lại”.

**Mô phỏng lỗi và retry** là thực hành chủ động tạo những tình huống này trong test để chứng minh hệ thống phân biệt lỗi tạm thời, lỗi vĩnh viễn, hết số lần thử, mất phản hồi dù side effect đã xảy ra, và crash/rollback. Mục tiêu là học cách đặt retry **đúng ranh giới**, kiểm tra số attempts, giữ một `eventId` ổn định, tránh side effect lặp và xác định khi nào cần một cơ chế lưu publication bền vững.

Bài này đi từ mô hình đến bộ kiểm thử Java 17+ với **Spring Framework, Spring Retry, JUnit 5**. Bộ kiểm thử gọi `ApplicationEventPublisher` và `@EventListener` thật; giả lập transport lỗi bằng một fake có điều khiển, **không dùng thời gian ngẫu nhiên, mạng thật hoặc `Thread.sleep`**. Những giới hạn về transaction, `@Async`, outbox và Spring Modulith được trình bày riêng để không nhầm retry trong bộ nhớ với độ tin cậy end-to-end.

## 1. Phân biệt lỗi ở các lớp khác nhau

Không phải mọi lần `publishEvent` thất bại đều có cùng nguyên nhân:

| Vị trí lỗi | Ví dụ | Người quan sát lỗi | Ý nghĩa cho retry |
| --- | --- | --- | --- |
| Trước publish | Command validation không hợp lệ | Service/caller | Thường **không** retry cho đến khi sửa dữ liệu |
| Listener đồng bộ | `@EventListener` ném `IllegalStateException` | Publisher, nếu exception chưa bị xử lý | Có thể retry tác vụ cụ thể, tránh publish lại mù |
| Listener bất đồng bộ | `@Async` method ném exception | Async exception handler/worker telemetry | Caller không mặc nhiên biết lỗi; cần state/error channel riêng |
| Listener sau commit | `AFTER_COMMIT` gọi gateway gặp timeout | Callback/worker | Transaction nguồn đã commit; cần retry công việc phụ |
| Khi submit task | Executor bị đầy, `TaskRejectedException` | Có thể xảy ra trên thread gọi submit | Phải xử lý overload; khác lỗi trong thân listener |
| Transport bên ngoài | HTTP 503, timeout, connection reset | Handler/gateway | Có thể retry **nếu** request an toàn và có giới hạn |
| Dữ liệu hoặc quyền | Schema invalid, 400, permission denied vĩnh viễn | Handler/gateway | Thường đưa về permanent failure/quarantine |
| Sau side effect | Gateway đã ghi dữ liệu nhưng ACK timeout | Handler chỉ thấy lỗi/unknown outcome | Retry có thể gây duplicate; cần idempotency/reconcile |
| Sau process crash | Event chỉ nằm trong RAM hoặc executor queue | Không còn worker để báo lỗi | RetryTemplate không đủ; cần durable record/outbox |

**Lưu ý:** `publishEvent` không trả một `Future` tổng hợp kết quả của mọi listener. Một event có thể có nhiều listeners; việc retry **toàn bộ lệnh publish** có thể làm những listeners đã thành công chạy lại, trong khi chỉ một listener bị lỗi.

## 2. Mô hình retry đúng ranh giới

Giả sử một sự kiện `ReceiptRequested(eventId, orderId)` kích hoạt gửi biên nhận. Luồng nên được hiểu như sau:

~~~text
publishEvent(ReceiptRequested)
        |
        +-- @EventListener ReceiptHandler   [một lần dispatch]
                |
                +-- RetryTemplate.execute(...)
                       |
                       +-- attempt 1 -> gateway: transient failure
                       +-- attempt 2 -> gateway: transient failure
                       +-- attempt 3 -> gateway: success
                |
                +-- handler hoàn tất

eventId không đổi giữa các attempts.
Handler invocation count = 1.
Gateway attempt count = 3.
Business side effect count = 1.
~~~

Ta retry **phần công việc có thể lặp an toàn**, không mặc định retry việc phát mọi event trong application context.

Một retry policy tốt phải trả lời:

1. Exception nào được retry? Có kiểm tra cause chain không?
2. Tối đa bao nhiêu **attempts**, tính cả lần đầu?
3. Có backoff/jitter và deadline không?
4. Lỗi nào cần ngừng ngay?
5. Nếu hết attempts, trạng thái được ghi ở đâu? Ai thấy và xử lý?
6. Nếu side effect đã thành công nhưng response bị mất, lần gọi lại có idempotent không?
7. Retry còn hoạt động khi ứng dụng restart hay chỉ tồn tại trong call stack hiện tại?

### Retry không phải replay hay recovery

- **Retry trong lời gọi hiện tại:** `RetryTemplate` hoặc `@Retryable` gọi lại operation trong cùng process.
- **Replay/resubmission:** đưa một logical event/publication chưa hoàn tất trở lại xử lý (thường sau restart).
- **Recovery:** khôi phục công việc thất bại bằng record bền vững, trạng thái/attempts, retry policy và idempotency.
- **Compensation:** thực hiện một nghiệp vụ bù trừ khi side effect đã có và không thể rollback.

Một retry trực tiếp trong RAM không giúp khôi phục một task đã mất sau process crash.

## 3. Spring Framework xử lý lỗi của listener ra sao?

### 3.1. Listener đồng bộ và exception propagation

Khi không cấu hình executor cho multicaster, `SimpleApplicationEventMulticaster` thường gọi listener trên thread của publisher. Ví dụ:

~~~java
@EventListener
public void onReceipt(ReceiptRequested event) {
    throw new IllegalStateException("gateway unavailable");
}
~~~

Đây là **trích đoạn** của một Spring-managed bean, không phải Java file độc lập. Khi exception chưa bị bắt và không có `ErrorHandler` xử lý, nó có thể đi ngược ra khỏi `publisher.publishEvent(...)`:

~~~java
try {
    publisher.publishEvent(new ReceiptRequested("evt-1", "ORD-1"));
} catch (IllegalStateException ex) {
    // Với dispatch đồng bộ mặc định, caller quan sát lỗi ở đây.
}
~~~

Nếu cùng event có nhiều listeners, exception của một listener có thể ngăn những listener lẽ ra được gọi sau nó. `@Order` cho phép ưu tiên invocation nhưng không tự cô lập lỗi hay điều phối retry. `SimpleApplicationEventMulticaster.setErrorHandler(...)` có thể thay đổi việc suppress hoặc propagate exception; không suy từ cấu hình mặc định sang mọi ứng dụng.

### 3.2. Listener @Async và exception propagation

~~~java
@Async("eventsExecutor")
@EventListener
public void onReceiptAsync(ReceiptRequested event) {
    gateway.send(event);
}
~~~

Đây là **trích đoạn**, yêu cầu `@EnableAsync`, bean executor và gateway. Exception ném trong thân listener `@Async` `void` thường được đưa tới `AsyncUncaughtExceptionHandler` hoặc logger; nó **không được ném trực tiếp trở lại caller của `publishEvent`**. Vì thế:

~~~java
publisher.publishEvent(event);
assertDoesNotThrow(...); // Không chứng minh listener async đã thành công.
~~~

Đoạn assert thứ hai chỉ minh họa một **suy luận sai**, không phải test độc lập. Để kiểm thử async, dùng `BlockingQueue`, `CompletableFuture`, latch hoặc Awaitility với timeout, thu kết quả và exception thật.

**Phân biệt:** nếu executor từ chối task **ngay khi submit**, publisher có thể quan sát `TaskRejectedException`; điều đó khác exception phát sinh *sau* khi worker bắt đầu thực thi.

### 3.3. AFTER_COMMIT và rollback

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chạy theo callback sau khi transaction nguồn commit. Nó không chạy khi transaction nguồn rollback; khi không có transaction, mặc định callback không chạy trừ khi `fallbackExecution=true`. Khi xử lý sau commit lỗi, transaction nguồn đã hoàn tất: không có cơ chế “throw exception để rollback commit cũ”.

Nếu callback ghi DB, hãy mở transaction mới cho phần ghi (chẳng hạn `REQUIRES_NEW`/`TransactionTemplate`) vì transactional resources cũ có thể vẫn còn bound ở callback nhưng sẽ không được commit thêm.

## 4. Chọn lỗi retryable và permanent

Một phân loại đơn giản cho bài thực hành:

| Loại lỗi | Ví dụ | Policy thường thích hợp |
| --- | --- | --- |
| **Transient** | Network reset, HTTP 503, DB deadlock/lock timeout, rate limit có hướng dẫn retry | Retry giới hạn, có backoff + jitter và deadline |
| **Permanent** | Payload sai schema, định danh không tồn tại vĩnh viễn, thiếu quyền không thể khắc phục bằng retry | Không retry tự động; lưu lý do, cảnh báo |
| **Unknown outcome** | HTTP timeout sau khi request đã được chấp nhận | Reconcile/idempotency trước khi quyết định retry |
| **Overload** | Executor queue full, downstream saturation | Rate limit/backpressure; tránh retry storm |
| **Bug lập trình** | `NullPointerException` do code sai, invariant bị phá | Sửa code/dữ liệu; không retry vô hạn |

Đừng viết policy “retry mọi `Exception`” chỉ để test màu xanh. Nhiều permanent errors sẽ được lặp lại, làm tăng tải và có thể gây hại. Ngược lại, một lỗi từ API ngoài sau khi **side effect đã thành công** không nên xử lý như “chưa làm gì”.

### Số attempts và backoff

Với `maxAttempts(3)`, nghĩa là **một lần gọi ban đầu và nhiều nhất hai lần retry**, không phải ba retries cộng một initial call. Trong bài lab, dùng `noBackoff()` chỉ để kiểm thử nhanh và xác định chính xác số lần gọi. **Production thường cần exponential backoff + jitter**:

~~~java
// Trích đoạn Spring Retry 2.x, policy dành cho runtime thực:
RetryTemplate retry = RetryTemplate.builder()
    .maxAttempts(5)
    .retryOn(TransientFailure.class)
    .exponentialBackoff(200, 2.0, 5_000, true)
    .build();
~~~

Cần import `org.springframework.retry.support.RetryTemplate` và `TransientFailure` của ứng dụng. Backoff dùng milliseconds; với tham số cuối `true`, chính sách dùng yếu tố ngẫu nhiên để giảm retry đồng loạt. Không đưa backoff thật vào unit test đếm attempts, vì nó làm test chậm/flaky không cần thiết.

## 5. Bài lab đầy đủ: Spring Retry + @EventListener + JUnit 5

Bộ test dùng Java 17+, Spring Framework 6.2, Spring Retry 2.0.x và JUnit Jupiter 5. **Không cần Spring Boot, database, HTTP server hay broker.** Application event được Spring dispatch thật; một fake transport mô phỏng các lỗi có thể dự đoán.

Ta kiểm thử năm tình huống:

1. Transport lỗi hai lần rồi thành công lần thứ ba.
2. Lỗi vĩnh viễn: chỉ một attempt, không retry.
3. Lỗi tạm thời kéo dài: hết ba attempts và exception lan về publisher đồng bộ.
4. Side effect đã được ghi nhận nhưng ACK bị mất: retry gọi transport lần thứ hai, **idempotency key** ngăn side effect lặp.
5. Event khác có ID khác vẫn được xử lý riêng: không lẫn attempt/state giữa events.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'spring-event-fault-retry'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.retry:spring-retry:2.0.13'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-retry` là dependency riêng; **Spring Framework Application Events không tự mang Spring Retry**. Nếu dự án dùng Spring Boot với dependency management, ưu tiên bộ dependency tương thích do Boot quản lý thay vì cố ép phiên bản. `spring-aop` có mặt cho ngữ cảnh triển khai thực tế; lab dùng `RetryTemplate` trực tiếp nên không cần bật `@EnableRetry`.

### 5.3. src/test/java/example/events/RetryEventTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RetryEventTest.Config.class)
class RetryEventTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired FakeGateway gateway;
    @Autowired RetryingListener listener;

    @BeforeEach
    void reset() {
        gateway.reset();
        listener.reset();
    }

    @Test
    void retriesTwoTransientFailuresThenSucceeds() {
        gateway.failFirst("evt-transient", 2);

        publisher.publishEvent(new SendRequested("evt-transient"));

        assertEquals(1, listener.invocations());
        assertEquals(3, gateway.attempts("evt-transient"));
        assertEquals(1, gateway.effects("evt-transient"));
    }

    @Test
    void permanentFailureIsNotRetried() {
        gateway.rejectPermanently("evt-invalid");

        PermanentFailure error = assertThrows(
            PermanentFailure.class,
            () -> publisher.publishEvent(
                new SendRequested("evt-invalid")
            )
        );

        assertEquals("invalid:evt-invalid", error.getMessage());
        assertEquals(1, listener.invocations());
        assertEquals(1, gateway.attempts("evt-invalid"));
        assertEquals(0, gateway.effects("evt-invalid"));
    }

    @Test
    void exhaustedTransientRetriesPropagateFailure() {
        gateway.failFirst("evt-down", 99);

        TransientFailure error = assertThrows(
            TransientFailure.class,
            () -> publisher.publishEvent(
                new SendRequested("evt-down")
            )
        );

        assertEquals("temporary:evt-down", error.getMessage());
        assertEquals(1, listener.invocations());
        assertEquals(3, gateway.attempts("evt-down"));
        assertEquals(0, gateway.effects("evt-down"));
    }

    @Test
    void lostAckDoesNotDuplicateAnIdempotentSideEffect() {
        gateway.loseAckOnceAfterEffect("evt-ack");

        publisher.publishEvent(new SendRequested("evt-ack"));

        assertEquals(1, listener.invocations());
        assertEquals(2, gateway.attempts("evt-ack"));
        assertEquals(1, gateway.effects("evt-ack"));
    }

    @Test
    void eventIdsHaveIndependentRetryState() {
        gateway.failFirst("evt-a", 1);

        publisher.publishEvent(new SendRequested("evt-a"));
        publisher.publishEvent(new SendRequested("evt-b"));

        assertEquals(2, listener.invocations());
        assertEquals(2, gateway.attempts("evt-a"));
        assertEquals(1, gateway.attempts("evt-b"));
        assertEquals(1, gateway.effects("evt-a"));
        assertEquals(1, gateway.effects("evt-b"));
    }

    record SendRequested(String eventId) {}

    static final class TransientFailure extends RuntimeException {
        TransientFailure(String message) {
            super(message);
        }
    }

    static final class PermanentFailure extends RuntimeException {
        PermanentFailure(String message) {
            super(message);
        }
    }

    public static final class FakeGateway {
        private final Map<String, AtomicInteger> calls =
            new ConcurrentHashMap<>();
        private final Map<String, AtomicInteger> failuresLeft =
            new ConcurrentHashMap<>();
        private final Map<String, AtomicInteger> effectCount =
            new ConcurrentHashMap<>();
        private final Set<String> permanentlyInvalid =
            ConcurrentHashMap.newKeySet();
        private final Set<String> loseAckOnce =
            ConcurrentHashMap.newKeySet();
        private final Set<String> completedKeys =
            ConcurrentHashMap.newKeySet();

        void failFirst(String eventId, int count) {
            failuresLeft.put(eventId, new AtomicInteger(count));
        }

        void rejectPermanently(String eventId) {
            permanentlyInvalid.add(eventId);
        }

        void loseAckOnceAfterEffect(String eventId) {
            loseAckOnce.add(eventId);
        }

        void send(String eventId) {
            calls.computeIfAbsent(
                eventId, ignored -> new AtomicInteger()
            ).incrementAndGet();

            if (permanentlyInvalid.contains(eventId)) {
                throw new PermanentFailure("invalid:" + eventId);
            }

            AtomicInteger remaining = failuresLeft.get(eventId);
            if (remaining != null &&
                    remaining.getAndUpdate(
                        n -> n > 0 ? n - 1 : 0
                    ) > 0) {
                throw new TransientFailure("temporary:" + eventId);
            }

            // Mô phỏng sink hỗ trợ idempotency key = eventId.
            if (completedKeys.add(eventId)) {
                effectCount.computeIfAbsent(
                    eventId, ignored -> new AtomicInteger()
                ).incrementAndGet();
            }

            // Request đã thực sự có tác dụng, nhưng ACK "mất".
            if (loseAckOnce.remove(eventId)) {
                throw new TransientFailure("ack-lost:" + eventId);
            }
        }

        int attempts(String eventId) {
            AtomicInteger value = calls.get(eventId);
            return value == null ? 0 : value.get();
        }

        int effects(String eventId) {
            AtomicInteger value = effectCount.get(eventId);
            return value == null ? 0 : value.get();
        }

        void reset() {
            calls.clear();
            failuresLeft.clear();
            effectCount.clear();
            permanentlyInvalid.clear();
            loseAckOnce.clear();
            completedKeys.clear();
        }
    }

    public static final class RetryingListener {
        private final RetryTemplate retry;
        private final FakeGateway gateway;
        private final AtomicInteger listenerCalls = new AtomicInteger();

        RetryingListener(RetryTemplate retry, FakeGateway gateway) {
            this.retry = retry;
            this.gateway = gateway;
        }

        @EventListener
        public void on(SendRequested event) {
            listenerCalls.incrementAndGet();
            retry.execute(context -> {
                gateway.send(event.eventId());
                return null;
            });
        }

        int invocations() {
            return listenerCalls.get();
        }

        void reset() {
            listenerCalls.set(0);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        RetryTemplate retryTemplate() {
            return RetryTemplate.builder()
                .maxAttempts(3)
                .retryOn(TransientFailure.class)
                .noBackoff() // Chỉ dùng để test deterministic.
                .build();
        }

        @Bean
        FakeGateway fakeGateway() {
            return new FakeGateway();
        }

        @Bean
        RetryingListener retryingListener(
                RetryTemplate retryTemplate, FakeGateway gateway) {
            return new RetryingListener(retryTemplate, gateway);
        }
    }
}
~~~

### 5.4. Chạy test và kết quả kỳ vọng

Nếu project có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.RetryEventTest"
~~~

Trên Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.RetryEventTest"
~~~

Đây là bộ test **không có stdout nghiệp vụ cố định**. Khi chạy thành công, JUnit xác minh các kết quả sau:

| Test | Listener calls | Gateway attempts | Side effects thật |
| --- | ---: | ---: | ---: |
| `retriesTwoTransientFailuresThenSucceeds` | 1 | 3 | 1 |
| `permanentFailureIsNotRetried` | 1 | 1 | 0 |
| `exhaustedTransientRetriesPropagateFailure` | 1 | 3 | 0 |
| `lostAckDoesNotDuplicateAnIdempotentSideEffect` | 1 | 2 | 1 |
| `eventIdsHaveIndependentRetryState` | 2 | evt-a: 2; evt-b: 1 | Mỗi event: 1 |

Kết quả không dựa vào thời điểm thread chạy, độ trễ mạng hoặc `Thread.sleep`. `FakeGateway` chứa các kịch bản lỗi được thiết lập rõ trước khi publish. `RetryTemplate` chỉ retry `TransientFailure`; `PermanentFailure` đi qua không retry.

**Mô phỏng mất ACK rất quan trọng:** trong `send`, sink ghi side effect thành công và đánh dấu `completedKeys`; sau đó fake ném `TransientFailure("ack-lost:...")` để mô phỏng client không nhận được xác nhận. Retry sẽ gọi lại transport, nhưng `completedKeys.add(eventId)` trả `false`, nên hiệu ứng nghiệp vụ **chỉ tính một lần**.

**Giới hạn của fake:** `completedKeys` chỉ nằm trong bộ nhớ của JUnit process. Nó minh họa hợp đồng idempotency; không phải bảo đảm bền vững qua restart hay giữa nhiều replica. Production phải dựa vào unique constraint/atomic upsert của DB, idempotency support của gateway hoặc reconciliation phù hợp.

### 5.5. Tại sao không retry bằng publishEvent() lần nữa?

Một anti-pattern thường gặp:

~~~java
for (int i = 0; i < 3; i++) {
    try {
        publisher.publishEvent(new SendRequested(eventId));
        break;
    } catch (RuntimeException ex) {
        // thử phát lại toàn bộ event
    }
}
~~~

Đây là trích đoạn **minh họa rủi ro**, không phải giải pháp khuyến nghị. Nếu event có ba listeners, listener A đã ghi thành công rồi listener B thất bại, việc publish lại sẽ làm **cả A và B** được gọi thêm lần nữa. Người phát event cũng không quan sát được exception trong thân một async listener theo cách này.

Nên retry **operation thuộc handler B** hoặc quản lý publication theo từng `(eventId, handlerId)` bằng registry/outbox. Khi cần phát lại event có chủ đích, từng listener phải được thiết kế idempotent.

## 6. Thực hành mở rộng: @Retryable khác RetryTemplate thế nào?

Spring Retry hỗ trợ cả `RetryTemplate` dạng gọi trực tiếp và `@Retryable` dạng annotation/AOP:

~~~java
// Trích đoạn cần @EnableRetry và bean được gọi qua proxy.
@Service
class ReceiptService {

    @Retryable(
        retryFor = TransientFailure.class,
        maxAttempts = 3
    )
    public void send(ReceiptRequested event) {
        gateway.send(event.eventId());
    }
}
~~~

Đây là trích đoạn **không phải mã của test mục 5**; cần imports `@Service`, `@Retryable`, `TransientFailure`, `ReceiptRequested` và `gateway` do ứng dụng định nghĩa. Cần cấu hình `@EnableRetry` (và AOP dependencies phù hợp).

**Lưu ý self-invocation:** nếu một method trong `ReceiptService` gọi `this.send(...)` ở proxy mode thông thường, retry advice có thể bị bỏ qua. Để dễ kiểm thử, đặt retryable operation ở bean khác được gọi qua Spring proxy, hoặc dùng `RetryTemplate` tường minh như bài lab. Không “gắn annotation rồi đoán” mà không xác minh số attempts thật.

`@Recover` (nếu dùng) có thể thay đổi behavior khi hết attempts; nó có thể xử lý exception thay vì để lỗi truyền ra. Một handler trông như “thành công” nếu `@Recover` âm thầm swallow lỗi, nên cần xác định contract: recovery có thực hiện side effect bù/trả fallback hợp lệ hay chỉ log? Khi kết quả phải là failure, hãy ghi state `FAILED/DEAD` hoặc ném exception theo chính sách, không che giấu.

### Retry và transaction advice

Khi gắn cả `@Retryable` và `@Transactional`, **thứ tự advice quyết định mỗi attempt có một transaction riêng hay toàn bộ retries chia một transaction**. Không dựa vào giả định từ tên annotation; kiểm thử rollback rules và transaction boundary thực tế.

Đối với xử lý có DB writes, một cấu trúc dễ kiểm soát là retry ở **vòng ngoài**, mỗi attempt gọi một service method transactional thông qua proxy hoặc `TransactionTemplate` riêng. Nếu một attempt gặp lỗi và transaction đã `rollbackOnly`, việc retry trong cùng transaction có thể dẫn đến `UnexpectedRollbackException` hoặc trạng thái sai.

Ví dụ ý tưởng (trích đoạn):

~~~java
retryTemplate.execute(context -> {
    transactionalWorker.processOneAttempt(event);
    return null;
});
~~~

`transactionalWorker` cần là một bean thật và `processOneAttempt` phải có transaction contract xác định. Nếu operation là HTTP side effect ngoài DB, transaction nguồn **không rollback được tác dụng đó**; idempotency vẫn cần thiết.

## 7. Mô phỏng lỗi trong @Async @EventListener

Khi listener chạy async, cần chứng minh lỗi bằng một kênh quan sát có timeout. Một thiết kế test-only có thể dùng `BlockingQueue<Outcome>` để bắt kết quả:

~~~java
record Outcome(String eventId, boolean success, Throwable error) {}

@Async("eventsExecutor")
@EventListener
public void onAsync(ReceiptRequested event) {
    try {
        gateway.send(event.eventId());
        outcomes.offer(new Outcome(event.eventId(), true, null));
    } catch (RuntimeException ex) {
        outcomes.offer(new Outcome(event.eventId(), false, ex));
        throw ex; // Lỗi được async exception handling tiếp nhận.
    }
}
~~~

Đây là **trích đoạn**, cần `@EnableAsync`, executor và queue `outcomes` của fixture. Trong JUnit:

~~~java
publisher.publishEvent(new ReceiptRequested("evt-async", "ORD-1"));

Outcome outcome = outcomes.poll(5, TimeUnit.SECONDS);
assertNotNull(outcome, "async listener did not finish");
assertEquals("evt-async", outcome.eventId());
assertFalse(outcome.success());
assertInstanceOf(TransientFailure.class, outcome.error());
~~~

Các đoạn ở mục này là **hướng dẫn ghép vào test fixture riêng**, không phải code độc lập. Không thêm listener async này vào cùng context của `RetryEventTest` vì khi đó cùng event sẽ có thêm listener, làm sai số attempts của lab chính. Đảm bảo event ID độc lập giữa các test, queue được clear và executor được đóng theo Spring context lifecycle.

**Không chỉ chờ `started`:** listener có thể vào method rồi lỗi ở bước sau. Tín hiệu `Outcome` phải được ghi sau khi bước xử lý tương ứng kết thúc hoặc trong catch. Trong production, `BlockingQueue` in-memory không thay thế durable error tracking; nó chỉ là cách test chờ có timeout.

Nếu listener `@Async` trả `void` và không tự bắt exception, cấu hình `AsyncUncaughtExceptionHandler` để log/metrics. `publishEvent` trả về trước khi worker xong **không phải bằng chứng thành công**.

## 8. Mô phỏng transaction rollback và AFTER_COMMIT

Một application service có thể ghi dữ liệu rồi publish event trong transaction. Nếu listener đồng bộ thất bại và exception thoát khỏi service, transaction thường rollback với `RuntimeException` hoặc `Error` theo cấu hình rollback mặc định của Spring 6.x.

~~~text
BEGIN TX
  UPDATE order
  publish Event
      @EventListener gọi gateway -> throw RuntimeException
  exception thoát qua transaction boundary
ROLLBACK TX
~~~

Nhưng nếu listener đã gọi external HTTP API trước khi ném lỗi, side effect bên ngoài **không rollback cùng DB**. Nếu app cần chỉ gửi thông báo khi order commit, chuyển công việc sang after-commit:

~~~java
@Component
class ReceiptAfterCommitListener {

    private final ReceiptWorker worker;

    ReceiptAfterCommitListener(ReceiptWorker worker) {
        this.worker = worker;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderCommitted(OrderCommitted event) {
        worker.process(event);
    }
}
~~~

Đây là **trích đoạn**, cần `ReceiptWorker`, `OrderCommitted` và các imports. Không phải một durable queue. Nếu `worker.process` ném exception, business transaction đã commit; exception từ callback **không thể hoàn tác commit**.

### Kiểm thử transaction boundary đúng cách

- Test **commit thành công**: phát event trong `TransactionTemplate.executeWithoutResult`; sau khi transaction hoàn tất mới assert callback.
- Test **rollback**: sau khi publish, ném `IllegalStateException` trong transaction; `AFTER_COMMIT` không chạy.
- Test **không có transaction**: listener mặc định không chạy (`fallbackExecution=false`).
- Test **exception sau commit**: business row vẫn tồn tại; failure cần được ghi hoặc đưa vào durable queue.
- Nếu listener sau commit tự ghi DB, dùng một transaction mới (`REQUIRES_NEW` hoặc `TransactionTemplate` riêng).
- Nếu listener async, dùng await có timeout sau commit; không assert ngay sau `publishEvent`.

Cẩn thận với `@Transactional` trên **JUnit test method**: Spring TestContext thường rollback test transaction ở cuối method, nên callback `AFTER_COMMIT` có thể không chạy. Hãy chủ động commit bằng `TransactionTemplate` hoặc `TestTransaction.flagForCommit()/end()` khi dùng test-managed transaction.

## 9. Mô phỏng retry bền vững: event chưa hoàn tất sau crash

Spring Retry trong bộ test là **in-process**; nếu JVM chết sau lần thử thứ nhất, không có điều gì bảo đảm hệ thống biết event còn dở dang khi khởi động lại.

Để mô phỏng độ tin cậy, hãy hình dung một **publication ledger** có record cho từng `(event_id, handler_id)`:

~~~text
BEGIN business TX
  UPDATE orders
  INSERT event_publication(
    event_id, handler_id, status='PENDING', attempts=0)
COMMIT

Worker:
  atomic claim PENDING/FAILED đến hạn -> PROCESSING
  -> gọi external sink với idempotency key cố định
      thành công -> SUCCEEDED
      transient -> FAILED + next_attempt_at
      permanent/max attempts -> DEAD
  -> crash? -> lease expiration + recovery/reclaim
~~~

Schema gợi ý:

~~~sql
CREATE TABLE event_publication (
  event_id VARCHAR(80) NOT NULL,
  handler_id VARCHAR(100) NOT NULL,
  status VARCHAR(24) NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMP NULL,
  lease_until TIMESTAMP NULL,
  claimed_by VARCHAR(100) NULL,
  fencing_token BIGINT NOT NULL DEFAULT 0,
  last_error_code VARCHAR(100) NULL,
  PRIMARY KEY (event_id, handler_id)
);
~~~

Đây là **schema thiết kế tham khảo**, không phải bảng Spring Framework tự tạo hay một outbox hoàn chỉnh. Production cần lưu đủ event payload/snapshot hoặc `payload_ref` để worker có thể tái dựng work sau restart.

Ví dụ atomic claim định hướng:

~~~sql
UPDATE event_publication
   SET status='PROCESSING',
       attempts=attempts + 1,
       claimed_by=:worker_id,
       lease_until=:lease_until,
       fencing_token=fencing_token + 1
 WHERE event_id=:event_id
   AND handler_id=:handler_id
   AND status IN ('PENDING','FAILED')
   AND attempts < :max_attempts
   AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP);
~~~

Các `:named_parameters` cần được bind qua `NamedParameterJdbcTemplate` hoặc cơ chế tương đương. Worker chỉ xử lý nếu update được **đúng một row**; không phải hai workers cùng đọc `PENDING` rồi đều gửi side effect.

**Crash simulation** nên bao gồm ít nhất ba điểm:

1. **Trước commit nguồn:** event/outbox row phải rollback cùng nghiệp vụ.
2. **Sau commit nhưng trước worker dispatch:** publication còn `PENDING`, recovery tìm lại được.
3. **Sau side effect nhưng trước khi mark `SUCCEEDED`:** retry có thể xảy ra; sink phải idempotent hoặc được reconcile theo idempotency key.

Một `PROCESSING` có thể bị kẹt nếu worker chết. Cần `lease_until`, staleness detection và `fencing_token` để ngăn worker cũ cập nhật sai trạng thái sau khi worker mới claim. Fencing trong DB không tự loại bỏ tác dụng phụ bên ngoài đã gửi, nên idempotency ở sink vẫn thiết yếu.

**Không gửi lại mọi event mỗi lần restart** mà không xét trạng thái từng handler; điều đó có thể làm các handlers đã thành công tạo side effect lặp.

## 10. Spring Modulith Event Publication Registry

Nếu ứng dụng đã sử dụng Spring Modulith, **Event Publication Registry** có thể lưu publication dành cho transactional event listeners ngay trong transaction nghiệp vụ. Khi handler xử lý thành công, publication được đánh dấu completed; trường hợp thất bại có thể được resubmit qua API tương ứng. Đây là lựa chọn để tránh tự xây toàn bộ tracking/recovery cho application modules.

Một module listener minh họa:

~~~java
@Component
class BillingEventListener {

    @ApplicationModuleListener
    void on(OrderPaid event) {
        billingService.processIdempotently(event);
    }
}
~~~

Đây là **trích đoạn** (cần Spring Modulith dependency/imports và các bean/domain types phù hợp), không thuộc test `RetryEventTest` mục 5. `@ApplicationModuleListener` có ngữ nghĩa transactional và async theo phiên bản Modulith; không suy rằng nó xử lý exactly-once ở external sink.

Ở Spring Modulith **2.x**, lifecycle publication có trạng thái `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED`, `RESUBMITTED`; có cơ chế tìm publication lỗi, tùy chọn resubmit và cấu hình staleness. API `FailedEventPublications`, `IncompleteEventPublications` và `ResubmissionOptions` cần được dùng theo version thực tế.

Ví dụ cấu hình có thể được dùng cho resubmission outstanding publications khi restart:

~~~properties
spring.modulith.events.republish-outstanding-events-on-restart=true
~~~

Cấu hình này là **tùy chọn tùy version và chính sách vận hành**; không bật mà không cân nhắc retry storm, idempotency, dữ liệu lỗi vĩnh viễn, concurrency và thứ tự. Completion mode (`UPDATE`, `DELETE`, `ARCHIVE`) ảnh hưởng việc retention/truy vấn publication, không phải phương án loại bỏ side effect duplicate.

**Registry theo dõi publication**, không thay thế audit ledger nghiệp vụ, không biến HTTP/email thành transaction phân tán và không tự chứng minh external service đã xử lý đúng một lần.

## 11. Thực hành mô phỏng lỗi có hệ thống

Để kiểm thử khả năng chịu lỗi, thay vì chờ môi trường bên ngoài thật sự hỏng, hãy thiết kế **failure injection** trong gateway/service adapter. Có thể tạo các nhánh:

| Kịch bản injection | Cơ chế mô phỏng | Assertion quan trọng |
| --- | --- | --- |
| Transient fail N lần | `failFirst(eventId, N)` | Attempts = N+1 khi N dưới max |
| Permanent failure | `rejectPermanently(eventId)` | Không retry |
| Hết attempts | Fail hơn `maxAttempts` | Exception/state exhausted, không treo |
| ACK mất sau side effect | Lưu effect rồi ném transient | Attempts tăng nhưng effects duy nhất = 1 |
| Consumer async lỗi | Complete future exceptionally / error queue | Test đợi outcome với timeout; publisher không trả lỗi body |
| Worker restart | Persist PENDING trước, khởi động lại worker | Recovery đọc được PENDING và không gửi trùng |
| Transaction rollback | Ném exception trước commit | No committed business/outbox record |
| Poison message | Payload/schema invalid | Quarantine/DEAD, không retry mãi |
| Executor saturation | Bounded queue + worker gate | Rejection được quan sát; policy overload rõ |
| Nhiều listeners | Một listener thành công, một fail | Chỉ retry handler lỗi, không phát lại toàn bộ |
| Concurrent workers | Race claim cùng publication | Chỉ một atomic claim thành công |
| Stale worker | Lease hết, worker mới claim | Fencing token cũ không thể mark completed |

### Test deterministic: kiểm soát nguyên nhân thay vì thời gian

Trong lab, `failFirst` dùng một bộ đếm nên chính xác lần nào ném lỗi, lần nào thành công. Không đợi ngẫu nhiên 1 giây rồi hy vọng lỗi xuất hiện. Khi phải kiểm tra race/async, dùng `CountDownLatch` `started/release` và `CompletableFuture.get(timeout)` để định nghĩa thứ tự nhân quả.

Không mock chính `ApplicationEventPublisher` trong integration test nếu mục tiêu là kiểm chứng Spring dispatch/listener registration; hãy dùng publisher thật và mock/fake **dependency bên ngoài của listener**.

## 12. Retry làm tăng rủi ro gì?

### 12.1. Duplicate side effects

Mất ACK có thể xảy ra sau khi gateway thực thi xong. Retry cùng operation có thể gây trùng email, thanh toán hoặc audit. `eventId` nên là khóa idempotency ổn định; với nhiều handler/sink, thường cần `(eventId, handlerId)` hoặc key được xác định theo action.

Một đoạn logic kiểm tra `SELECT EXISTS` rồi `INSERT` không atomic có thể race. Nên dùng database unique constraint/atomic upsert, hoặc idempotency API của downstream nếu side effect nằm bên ngoài database.

### 12.2. Retry storm

Nếu nhiều instances thấy HTTP 503 và retry ngay lập tức, downstream càng quá tải. Dùng **exponential backoff + jitter**, giới hạn concurrency, circuit breaker khi phù hợp, tôn trọng `Retry-After` nếu đáng tin, và metrics cho retry rate.

### 12.3. Transaction kéo dài

Retry HTTP trong một transaction DB có thể giữ connection/locks trong toàn bộ thời gian backoff. Thường nên commit thay đổi nghiệp vụ/outbox trước, rồi xử lý side effect bên ngoài transaction nguồn; mỗi DB attempt có transaction phù hợp riêng.

### 12.4. “Success” giả vì nuốt lỗi

Nếu listener catch exception rồi chỉ log, registry có thể cho rằng handler đã hoàn tất thành công mặc dù side effect thất bại. Cần phân biệt **best effort có chủ đích** với **work bắt buộc**. Khi kết quả là failure, phải ghi state hoặc ném exception theo contract để cơ chế retry/recovery nhận biết.

### 12.5. Retry không tự tạo ordering guarantee

Nhiều event cùng aggregate có thể được xử lý đảo thứ tự bởi executor/retry. Nếu event `OrderCancelled` đã đến trước lần retry `OrderPaid`, xử lý không kiểm tra version có thể tạo trạng thái ngược. Dùng aggregate version, ordered partition, optimistic locking hoặc orchestration nếu thứ tự thực sự là bất biến nghiệp vụ.

## 13. Logging, metrics và tín hiệu kiểm chứng

Bài test đếm số attempts; trong vận hành cần quan sát tương tự:

| Field / metric | Vai trò |
| --- | --- |
| `event_id` và `handler_id` | Tra một logical work item |
| `attempt` và `max_attempts` | Biết đang retry lần nào |
| `error_code` | Phân loại transient/permanent, đã sanitize |
| `outcome` | `SUCCEEDED`, `FAILED`, `DEAD` |
| `next_attempt_at` | Ngày giờ được retry lại |
| `processing_duration_ms` | Phát hiện latency downstream |
| `oldest_pending_age` | Phát hiện backlog không xử lý |
| `duplicate_suppressed` | Theo dõi idempotency đã ngăn duplicate |
| `retry_count` | Phát hiện retry storm |
| `correlation_id`, `trace_id` | Nối workflow, logs và traces |

Đừng gắn `eventId` làm **metric label** vì cardinality cao; dùng `event_type`, `handler_id`, `outcome` để aggregation. `eventId` phù hợp ở log có cấu trúc và publication registry. Không log raw payload/token/credentials hoặc toàn bộ exception nếu chứa PII.

Một log minh họa:

~~~json
{
  "message": "event_retry_attempt",
  "event_id": "evt-42",
  "handler_id": "send-receipt",
  "attempt": 2,
  "max_attempts": 3,
  "error_code": "HTTP_503",
  "outcome": "FAILED"
}
~~~

Đây là JSON **minh họa schema log**, không phải output thực của test hoặc một JSON encoder được cấu hình ở bài này.

## 14. Những lỗi triển khai thường gặp

**Lỗi 1 — Retry toàn bộ publishEvent:** tạo side effect trùng từ các listeners đã thành công. Retry một operation hoặc publication theo handler.

**Lỗi 2 — Không phân loại exception:** lỗi schema/permission bị retry vô hạn. Chỉ retry transient conditions đã xác định.

**Lỗi 3 — Hiểu sai `maxAttempts`:** ba attempts = ban đầu + hai retries, không phải bốn lần.

**Lỗi 4 — Dùng `Thread.sleep` trong test:** test flaky và chậm. Dùng fake counter, latch và bounded wait.

**Lỗi 5 — Cho rằng `publishEvent` return nghĩa async listener thành công:** phải đợi outcome và error channel thực tế.

**Lỗi 6 — Catch rồi nuốt exception trong handler bắt buộc:** registry/log có thể báo thành công giả; cần persistent failed state.

**Lỗi 7 — Retry transaction đã rollback-only:** không thể làm lành transaction bằng cách gọi operation lại trong cùng scope; mỗi attempt cần boundary phù hợp.

**Lỗi 8 — Dùng `@Retryable` qua self-invocation:** advice bị bỏ qua, chỉ chạy một lần. Gọi qua bean/proxy hoặc dùng `RetryTemplate`.

**Lỗi 9 — Không kiểm tra mất ACK sau side effect:** dễ charge/email/audit trùng. Thiết kế sink idempotent hoặc reconciliation.

**Lỗi 10 — Coi `@TransactionalEventListener(AFTER_COMMIT)` là durable queue:** process có thể chết trước callback; dùng outbox/registry nếu không được mất.

**Lỗi 11 — Không có deadline/backoff:** retry storm và request/transaction kéo dài. Tách retry in-process khỏi deferred retry có lịch.

**Lỗi 12 — Không kiểm tra nhiều event IDs:** dùng chung một global future/counter khiến test đọc nhầm kết quả. Tách state theo eventId/handlerId.

**Lỗi 13 — Không kiểm tra concurrency:** hai workers cùng đọc PENDING rồi xử lý. Dùng atomic claim, lease/fencing và sink idempotency.

**Lỗi 14 — Không có đường xử lý khi hết attempts:** event bị mất âm thầm. Lưu `DEAD` hoặc quarantine, cảnh báo và quy trình replay có kiểm soát.

## 15. Checklist bài thực hành

- [ ] Đã phân biệt lỗi sync listener, async body và executor rejection.
- [ ] Test chạy qua `ApplicationEventPublisher` thật; fake đúng dependency lỗi.
- [ ] Có kịch bản transient, permanent, exhausted, ACK lost và multiple event IDs.
- [ ] Max attempts được assert rõ, gồm cả lần đầu.
- [ ] Lỗi permanent không bị retry, lỗi transient chỉ retry trong giới hạn.
- [ ] Có assertion về **side effect**, không chỉ số lần gọi method.
- [ ] Retry ở handler/operation phù hợp, không publish lại vô điều kiện.
- [ ] Event ID ổn định, sink có idempotency hoặc reconciliation.
- [ ] Test không phụ thuộc wall-clock sleep; async chờ bằng timeout.
- [ ] Với transaction, phân biệt before-commit/after-commit và rollback.
- [ ] Nếu cần restart recovery, có durable publication/outbox và trạng thái attempt.
- [ ] Có bounded queue, overload policy, exponential backoff + jitter ở production.
- [ ] Có log, metrics, alert cho retries, failed/dead và backlog.
- [ ] Đã có policy đối với permanent/poison events và can thiệp thủ công.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** `ApplicationEventPublisher` có tự retry `@EventListener` sau exception không?

Không theo cấu hình chuẩn. Một synchronous exception thường lan về publisher. Retry cần được cấu hình ở operation, listener hoặc hạ tầng publication/worker có chủ đích.

**Câu 2:** Vì sao nên retry `gateway.send(eventId)` thay vì `publishEvent(event)`?

Vì event có thể có nhiều listeners; retry toàn bộ publication gọi lại cả listeners đã thành công, tạo duplicate side effects.

**Câu 3:** `maxAttempts(3)` nghĩa là bao nhiêu retries tối đa?

Ba lần gọi operation tổng cộng: một initial attempt và tối đa hai retries.

**Câu 4:** Nếu fake gateway ném exception sau khi đã ghi effect, có nên gọi lại với event ID mới không?

Không. Nếu là cùng logical event, giữ idempotency key cũ để sink biết đây là retry và tránh side effect lặp.

**Câu 5:** Vì sao không dùng `assertThrows` quanh `publishEvent` để kiểm tra exception của listener `@Async`?

Vì body listener chạy trên worker thread; exception không truyền trực tiếp qua publisher. Hãy dùng observable outcome/error handler với timeout.

**Câu 6:** Retry trong `AFTER_COMMIT` thất bại có rollback transaction nguồn được không?

Không. Transaction nguồn đã commit. Nếu cần đảm bảo không mất công việc phụ, phải lưu ý định xử lý bền vững cùng transaction nguồn hoặc dùng registry/outbox tương đương.

**Câu 7:** Vì sao `@Retryable` có thể không chạy đủ attempts dù đã gắn annotation?

Vì proxy advice có thể bị bỏ qua khi tự gọi method trong cùng bean, hoặc do cấu hình `@EnableRetry`/dependency/transaction advice chưa phù hợp. Kiểm tra attempts trong integration test.

**Câu 8:** Một publication còn `PROCESSING` sau restart có chắc là an toàn để gửi lại ngay không?

Không. Cần kiểm tra lease/staleness, điều phối worker, idempotency ở sink và khả năng side effect đã xảy ra trước crash.

**Ghi nhớ:** mô phỏng lỗi đáng tin không chỉ kiểm tra “retry cuối cùng thành công”, mà còn chứng minh **đúng số attempts, đúng loại lỗi, không trùng side effect, đúng transaction boundary và có đường phục hồi sau sự cố**. Spring Retry xử lý retries trong process; khi cần độ tin cậy sau restart, kết hợp publication registry/outbox, idempotency, retry scheduling và observability.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events, synchronous vs asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Retry 2.0 — RetryTemplateBuilder API](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html)
- [Spring Retry 2.0 — RetryTemplate API](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplate.html)
- [Spring Modulith — Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
