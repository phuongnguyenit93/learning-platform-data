# Xác định timeout, retry và mức observability trong kiểm thử Spring Modulith

## 1. Chốt ba hợp đồng trước khi viết test

Trong một luồng event-driven, **timeout**, **retry** và **observability** phải được thiết kế cùng nhau. Nếu chỉ đặt `andWaitAtMost(Duration.ofSeconds(30))` để “cho CI đủ thời gian”, test có thể xanh dù listener đã thử lại không kiểm soát, ghi dữ liệu trùng hoặc hoàn tất nhờ event tồn dư. Ngược lại, timeout quá nhỏ khiến một luồng đúng nghiệp vụ thất bại vì connection pool hoặc worker startup trên CI.

Xét module `payments` phát `PaymentCaptured`, module `orders` ghi nhận thanh toán và có thể phát tiếp `OrderPaid`. Một phép kiểm đáng tin phải trả lời **ba câu khác nhau**:

1. **Timeout:** hoạt động nào phải hoàn tất trước mốc nào? Mốc đó là timeout kết nối, một lần gọi remote, cả chiến lược retry, transaction commit, consumer processing, hay tổng thời gian bài test?
2. **Retry:** lỗi nào được thử lại, ai sở hữu việc thử lại, tối đa bao nhiêu lần, dùng lại logical ID nào, và điều kiện nào được coi là đã xử lý xong?
3. **Observability:** test hoặc người vận hành nhìn thấy những tín hiệu nào để phân biệt *chưa nhận event*, *đang retry*, *DB đã commit*, *registry còn incomplete* và *broker chưa ack*?

Bài nằm trong chương **Chọn chiến lược** của học phần `SPRING_MODULITH_VERIFICATION_TESTING`, nơi ta kiểm chứng ranh giới kiến trúc bằng `ApplicationModules` và quy tắc phụ thuộc module; dùng `@ApplicationModuleTest` để thử event, database và tích hợp, rồi đưa các phép kiểm phù hợp vào **CI quality gate** chống phụ thuộc sai/hồi quy.

### 1.1. Định nghĩa hợp đồng có thể kiểm chứng

| Yêu cầu cụ thể | Giá trị ví dụ, không phải chuẩn chung | Bằng chứng test phải thu |
| --- | --- | --- |
| Một lần gọi gateway không được treo vô hạn | Deadline 700 ms/attempt | Client thật cấu hình và tuân thủ deadline, hoặc fake clock/scheduler cho policy test |
| Retry khi lỗi transient | Tối đa 3 attempts, backoff hai lần 150 ms | Attempt count, cùng idempotency key, kết quả terminal |
| Không retry lỗi nghiệp vụ vĩnh viễn | Declined / malformed request | Đúng một attempt, không thay business state thành PAID |
| Order chuyển trạng thái | Chờ tối đa 6 s trong môi trường test minh họa | Public query theo đúng `orderId/eventId` sau commit |
| Lỗi chưa được xử lý | Không được báo PASS chỉ vì đã publish | Terminal failure / incomplete publication / DLQ tùy hợp đồng |
| Chẩn đoán lỗi | Event ID, order ID, listener, attempt, outcome | Logs/traces có correlation; counters/timers không lộ ID nhạy cảm |

Các con số dùng xuyên suốt bài là **ví dụ thiết kế budget**, không phải lời khuyên đặt mọi hệ thống là 700 ms hoặc 6 s.

**Quy tắc ra quyết định:** mỗi timeout phải gắn với một boundary và mỗi retry phải có owner. Observability phải cho biết *boundary nào* đã hết hạn và *attempt nào* đã hoàn tất; nếu không, tăng timeout chỉ làm lỗi khó thấy hơn.

## 2. Tách timeout thành nhiều tầng và tính budget có căn cứ

Một bài test có thể đi qua: Spring command → remote adapter → transaction → Spring event listener → database/registry → eventual-state assertion. Mỗi bước có deadline và hậu quả khác nhau.

| Tầng | Timeout/budget thuộc về ai? | Khi hết hạn cần làm gì? |
| --- | --- | --- |
| **Connect timeout** | HTTP client, JDBC driver, broker client | Báo lỗi kết nối; không kết luận business request bị từ chối |
| **Request/response timeout** | External adapter | Phân biệt server từ chối với **outcome chưa biết** khi client không nhận response |
| **Một attempt** | Caller/gateway policy | Dừng attempt có giới hạn, thu kết quả/error type |
| **Tổng retry** | Policy owner | Không thử vô hạn; trả terminal outcome/reconcile |
| **DB lock/statement/transaction** | Persistence adapter và database | Hiểu rollback/commit và deadlock; kiểm tra state thực |
| **Listener/consumer completion** | Module nhận event | Đánh dấu trạng thái sau commit; ack/registry completion có thể là mốc khác |
| **Test await** | JUnit/`Scenario`/Awaitility | Timeout với last observed state, event IDs và attempt count |
| **CI job** | Pipeline và runner | Fail job/report nếu vượt, thu diagnostics; không coi aborted test là PASS |

### 2.1. Một phép tính budget đơn giản

Giả sử gateway policy cho **tối đa 3 attempts**, mỗi attempt có upper bound 700 ms; giữa attempts có hai lần backoff 150 ms:

```text
Worst-case gateway budget (minh họa):
  3 x 700 ms + 2 x 150 ms = 2 400 ms

Commit DB và publication bookkeeping:  <= 600 ms
Dispatch, scheduling và khoảng trống CI: <= 400 ms

Tổng trước khi observer thấy state: khoảng 3 400 ms

Test await 6 000 ms:
  có khoảng dự phòng, nhưng vẫn phát hiện kẹt vô hạn.
```

Biểu thức thiết kế:

\[
T_{\text{test-await}} >
\sum_{i=1}^{N} T_{\text{attempt},i}
+ \sum_{i=1}^{N-1} T_{\text{backoff},i}
+ T_{\text{commit}}
+ T_{\text{dispatch}}
+ T_{\text{poll-margin}}
\]

Đây là **budget bảo thủ**, không phải chứng minh latency luôn nhỏ hơn tổng trên. Thời gian chờ kết nối pool, thread queue, broker rebalance hoặc resource contention cần được tính nếu có trong đường thực thi. Nếu caller retry và consumer/registry cũng retry **không phối hợp**, số lần thực tế có thể lớn hơn `N` nhiều lần.

### 2.2. Tránh đặt timeout theo kiểu “cái nào cũng 5 giây”

- Một remote call hết hạn không đồng nghĩa toàn transaction đã rollback sạch.
- `Scenario.andWaitAtMost(...)` giới hạn **thời gian test chờ**, không cấu hình timeout HTTP/DB/broker trong ứng dụng.
- Một test kết thúc sau khi state = `PAID` chưa chắc broker producer đã được ack hoặc registry publication đã marked completed.
- CI job timeout phải lớn hơn thời lượng hợp lý của suite, nhưng không thay thế timeout ở từng thao tác.
- Timeout phải được ghi cùng **boundary name, attempt index và last observed state**, không chỉ “timeout after 6s”.

### 2.3. Đồng hồ timeout khác đồng hồ nghiệp vụ

Dùng `Clock.fixed(...)` để kiểm thử deadline của domain (ví dụ payment hết hạn ở `Instant` nào). Với elapsed-time budget, dùng cơ chế monotonic phù hợp của thư viện chờ hoặc `System.nanoTime()`; không tự tạo polling timeout dựa trên business clock đóng băng.

```java
long startedAtNanos = System.nanoTime();

try {
    performOperation();
} finally {
    long elapsedNanos = System.nanoTime() - startedAtNanos;
    // Đưa elapsed vào metrics/logging có đơn vị rõ ràng.
}
```

`System.nanoTime()` thích hợp để đo khoảng thời gian trong JVM; không dùng giá trị tuyệt đối của nó làm timestamp hay correlation ID.

## 3. Quy định owner của retry, loại lỗi và idempotency

**Retry là trách nhiệm nghiệp vụ/hạ tầng có trạng thái**, không phải cứ exception là gọi lại. Retry nằm ở nhiều nơi: HTTP client, service use case, Spring listener, Event Publication Registry, Kafka/RabbitMQ consumer, retry topic/DLQ và đôi khi cả CI test plugin.

### 3.1. Phân loại lỗi trước

| Tình huống | Có thể retry? | Điều kiện bắt buộc |
| --- | --- | --- |
| Kết nối bị từ chối **trước khi request được gửi** | Thường có, nếu dependency chỉ tạm unavailable | Backoff hữu hạn, không retry storm |
| HTTP 429/503 với contract hỗ trợ retry | Có điều kiện | Budget, `Retry-After` nếu có, idempotency |
| Gateway trả “card declined” | **Không** tự động retry | Đây là terminal business outcome |
| Payload invalid, schema mismatch | **Không** tự động retry y hệt | Sửa request/contract trước |
| Read timeout sau khi remote có thể đã xử lý | **Outcome unknown**, không mặc định retry | Query status/reconcile hoặc idempotency key được PSP đảm bảo |
| DB deadlock/serialization conflict | Có điều kiện | Retry **toàn transaction** an toàn, không lặp external charge |
| Listener ném lỗi tạm thời | Có nếu listener retry policy cho phép | Idempotent business effect và retry ownership rõ |
| Registry incomplete publication | Có thể resubmit theo cấu hình | Không coi resubmit là exactly-once processing |

Đừng đổi tất cả lỗi thành một `TransientException`. Đặc biệt, **timeout của response sau một lần charge** có thể là *unknown outcome*, không đồng nghĩa PSP chưa nhận tiền.

### 3.2. Một nơi chịu trách nhiệm retry tại một boundary

Ví dụ nếu HTTP adapter đã retry 3 lần và service cũng retry call adapter 3 lần, một request nghiệp vụ có thể sinh **tới 9 HTTP attempts** (chưa kể broker redelivery). Test unit của service khó nhìn được sự nhân lên này nếu mock ở adapter.

Chọn owner rõ: adapter xử lý transient HTTP theo policy, domain/service quyết định unknown outcome hoặc reconcile; listener/registry đảm bảo redelivery idempotent khi event đã publish. Cần ghi tổng budget xuyên các tầng thay vì chỉ số attempt ở một class.

### 3.3. Identity phải ổn định khi retry cùng logical request

```text
Logical payment: order O-7, idempotency key K-7

Attempt 1: send K-7 -> transient failure
Attempt 2: send K-7 -> success
Attempt 3: không cần gửi

Sai: Attempt 2 tự tạo key K-8; PSP có thể coi là charge mới.
```

Tương tự, cùng một event được replay phải giữ **logical event ID** hoặc idempotency key của nghiệp vụ. Publication record ID trong Event Publication Registry là khái niệm khác; một event có thể có nhiều publication theo listener target.

## 4. Ví dụ Java/JUnit: kiểm chứng retry policy mà không ngủ thật

Để test riêng **quyết định retry**, hãy cô lập network bằng một `RemoteCaptureGateway` port. Demo bên dưới dùng `RetryDelay` để test đếm backoff mà không thật sự `Thread.sleep(...)`. Đây là **mô hình chính sách tối giản** để học, không phải lời khuyên viết lại một thư viện retry production; hệ thống thật có thể dùng Spring Retry, Resilience4j hoặc cơ chế broker/registry.

### 4.1. Các kiểu Java của chính sách minh họa

Mọi kiểu dưới đây có thể đặt trong cùng package test/demo dưới dạng package-private; dự án thực tế nên tách theo module ownership.

```java
import java.math.BigDecimal;
import java.time.Duration;
import java.util.UUID;

record CaptureReceipt(String providerReference) {}

interface RemoteCaptureGateway {
    CaptureReceipt capture(
            UUID orderId,
            BigDecimal amount,
            String idempotencyKey);
}

interface RetryDelay {
    void beforeAttempt(int nextAttempt, Duration backoff);
}

final class TemporaryGatewayUnavailable extends RuntimeException {
    TemporaryGatewayUnavailable(String message) {
        super(message);
    }
}

final class PaymentDeclined extends RuntimeException {
    PaymentDeclined(String message) {
        super(message);
    }
}

final class RetryingCaptureGateway {

    private final RemoteCaptureGateway remote;
    private final RetryDelay delay;
    private final int maxAttempts;
    private final Duration backoff;

    RetryingCaptureGateway(
            RemoteCaptureGateway remote,
            RetryDelay delay,
            int maxAttempts,
            Duration backoff) {

        if (maxAttempts < 1 || backoff.isNegative()) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
        this.remote = remote;
        this.delay = delay;
        this.maxAttempts = maxAttempts;
        this.backoff = backoff;
    }

    CaptureReceipt capture(
            UUID orderId,
            BigDecimal amount,
            String key) {

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                // Cùng logical key trong mọi attempt.
                return remote.capture(orderId, amount, key);
            } catch (TemporaryGatewayUnavailable failure) {
                if (attempt == maxAttempts) {
                    throw failure;
                }
                delay.beforeAttempt(attempt + 1, backoff);
            }
        }
        throw new IllegalStateException("Unreachable");
    }
}
```

`PaymentDeclined` và mọi lỗi ngoài `TemporaryGatewayUnavailable` **không bị catch** nên không retry. `maxAttempts` tính **cả lần thử đầu**, không phải “số lần thử lại”. Code cố ý không xử lý timeout có **unknown outcome**: những lỗi đó cần contract riêng với PSP và reconciliation, không được tùy tiện biến thành `TemporaryGatewayUnavailable`.

### 4.2. JUnit + Mockito: transient, permanent và exhausted budget

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RetryingCaptureGatewayTests {

    @Mock RemoteCaptureGateway remote;
    @Mock RetryDelay delay;

    RetryingCaptureGateway policy;

    @BeforeEach
    void setUp() {
        policy = new RetryingCaptureGateway(
                remote, delay, 3, Duration.ofMillis(150));
    }

    @Test
    void retriesTransientOnceWithSameBusinessKey() {
        UUID orderId = UUID.randomUUID();
        BigDecimal amount = new BigDecimal("125000.00");
        String key = "capture-" + UUID.randomUUID();

        when(remote.capture(orderId, amount, key))
                .thenThrow(new TemporaryGatewayUnavailable("503"))
                .thenReturn(new CaptureReceipt("psp-accepted"));

        CaptureReceipt actual = policy.capture(orderId, amount, key);

        assertThat(actual.providerReference()).isEqualTo("psp-accepted");
        verify(remote, times(2)).capture(orderId, amount, key);
        verify(delay).beforeAttempt(2, Duration.ofMillis(150));
        verifyNoMoreInteractions(delay);
    }

    @Test
    void neverRetriesPermanentDecline() {
        UUID orderId = UUID.randomUUID();
        BigDecimal amount = new BigDecimal("125000.00");
        String key = "capture-" + UUID.randomUUID();

        when(remote.capture(orderId, amount, key))
                .thenThrow(new PaymentDeclined("declined"));

        assertThatThrownBy(() ->
                policy.capture(orderId, amount, key))
                .isInstanceOf(PaymentDeclined.class);

        verify(remote, times(1)).capture(orderId, amount, key);
        verifyNoInteractions(delay);
    }

    @Test
    void failsAfterExactlyThreeAttempts() {
        UUID orderId = UUID.randomUUID();
        BigDecimal amount = new BigDecimal("125000.00");
        String key = "capture-" + UUID.randomUUID();

        when(remote.capture(orderId, amount, key))
                .thenThrow(new TemporaryGatewayUnavailable("unavailable"));

        assertThatThrownBy(() ->
                policy.capture(orderId, amount, key))
                .isInstanceOf(TemporaryGatewayUnavailable.class);

        verify(remote, times(3)).capture(orderId, amount, key);
        verify(delay).beforeAttempt(2, Duration.ofMillis(150));
        verify(delay).beforeAttempt(3, Duration.ofMillis(150));
        verifyNoMoreInteractions(delay);
    }
}
```

**Bằng chứng sau PASS:** policy retry đúng class lỗi, đúng số attempts, dùng **cùng key** và không tạo backoff sau attempt cuối. Test deterministic vì `RetryDelay` là mock, không phụ thuộc tốc độ CI.

**Chưa chứng minh:** HTTP client thực tôn trọng connect/read deadline, PSP thực hỗ trợ idempotency, DB commit, hay broker retry. Các hợp đồng đó cần adapter/transport integration tests riêng.

### 4.3. Đừng test backoff bằng cách đo millisecond của thread

Nếu policy có jitter, kiểm tra **công thức/bounds** bằng seed hoặc nguồn random local, không assert `Thread.sleep(150)` mất **đúng** 150 ms. Timer/scheduler của CI có jitter và contention. Khi dùng thư viện retry production, test config/policy thông qua adapter API tương ứng, không dựa vào implementation details không thuộc hợp đồng.

## 5. `@ApplicationModuleTest`: chờ một event/state đúng ID với timeout hữu hạn

Ở tầng Spring Modulith, timeout quan trọng nhất thường là **thời gian chờ state sau event bất đồng bộ**. Test phải giữ listener và query adapter thật; nếu mock chúng, `Scenario` chỉ xác minh dữ liệu do mock tự dựng.

Ví dụ module `orders` tiêu thụ contract công khai `payments.events.PaymentCaptured`.

### 5.1. Event/read model là API ứng dụng, không phải type của Modulith

```java
// File: com/example/shop/payments/events/PaymentCaptured.java
package com.example.shop.payments.events;

import java.math.BigDecimal;
import java.util.UUID;

public record PaymentCaptured(
        UUID eventId,
        UUID orderId,
        String transactionId,
        BigDecimal amount) {}
```

```java
// File: com/example/shop/orders/OrderPaymentView.java
package com.example.shop.orders;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderPaymentView(
        UUID orderId,
        String status,
        UUID processedEventId,
        String transactionId,
        BigDecimal amount) {

    public boolean paidBy(
            UUID eventId,
            String expectedTransactionId,
            BigDecimal expectedAmount) {

        return "PAID".equals(status)
                && eventId.equals(processedEventId)
                && expectedTransactionId.equals(transactionId)
                && amount != null
                && amount.compareTo(expectedAmount) == 0;
    }
}
```

```java
// File: com/example/shop/orders/OrderQueries.java
package com.example.shop.orders;

import java.util.Optional;
import java.util.UUID;

public interface OrderQueries {
    Optional<OrderPaymentView> paymentOf(UUID orderId);
}
```

```java
// Test-support interface của module orders.
package com.example.shop.orders;

import java.math.BigDecimal;
import java.util.UUID;

interface OrderFixture {
    UUID awaitingPaymentAndCommit(BigDecimal amount);
}
```

Các kiểu này đòi implementation ứng dụng/test infrastructure, schema và listener phù hợp. `awaitingPaymentAndCommit(...)` phải tạo dữ liệu **đã commit**, không chỉ `saveAndFlush(...)` trong transaction chưa kết thúc.

### 5.2. Test module có assertion chống PASS giả

```java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.UUID;

import com.example.shop.payments.events.PaymentCaptured;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class PaymentEventCompletionTests {

    @Autowired OrderFixture fixture;
    @Autowired OrderQueries queries;

    @Test
    void commitsOnlyTheExpectedEventWithinBoundedWait(
            Scenario scenario) {

        BigDecimal amount = new BigDecimal("125000.00");
        UUID orderId = fixture.awaitingPaymentAndCommit(amount);
        UUID eventId = UUID.randomUUID();
        String key = "capture-" + eventId;

        OrderPaymentView before =
                queries.paymentOf(orderId).orElseThrow();

        assertThat(before.status()).isEqualTo("AWAITING_PAYMENT");
        assertThat(before.processedEventId()).isNull();

        scenario.publish(new PaymentCaptured(
                        eventId, orderId, key, amount))
                .andWaitAtMost(Duration.ofSeconds(6))
                .forStateChange(
                        () -> queries.paymentOf(orderId),
                        result -> result.filter(view ->
                                view.paidBy(eventId, key, amount))
                                .isPresent())
                .andVerify(result -> {
                    OrderPaymentView paid = result.orElseThrow();

                    assertThat(paid.orderId()).isEqualTo(orderId);
                    assertThat(paid.processedEventId())
                            .isEqualTo(eventId);
                    assertThat(paid.transactionId()).isEqualTo(key);
                    assertThat(paid.amount())
                            .isEqualByComparingTo(amount);
                });
    }
}
```

Ở đây `andWaitAtMost(6s)` là **budget của assertion**, không phải cấu hình retry/timeout của listener. Predicate chỉ đọc public state bằng `orderId` và so `eventId`/idempotency key; nó không pass nhờ một order `PAID` từ test khác.

**Giới hạn phải nêu rõ:**

- `Scenario.publish(...)` phát **Spring application event**, không tự gửi Kafka/RabbitMQ.
- Nếu listener là `@TransactionalEventListener(phase = AFTER_COMMIT)`, đường publisher cần transaction **thực sự commit**; nếu test-managed transaction rollback hoặc publish không có transaction phù hợp, listener có thể không chạy. Cần dùng một command/fixture publisher đã commit đúng hợp đồng hoặc cấu hình listener tương ứng.
- `OrderQueries` phải đọc state committed mới; nếu nó dùng JPA persistence context giữ entity cũ, retry polling có thể nhìn snapshot stale.
- Đạt `PAID` không chứng minh audit/outbox/broker ack hay Event Publication Registry completion đã xong; những điều đó cần oracle khác.

### 5.3. Đừng dùng timeout làm tiêu chí nghiệp vụ duy nhất

Khi test timeout, nên biết **lần đọc cuối là gì**, event ID nào đang pending và listener có bắt đầu chưa. Timeout không tự phân loại nguyên nhân giữa:

1. Event chưa được dispatch.
2. Transaction publish chưa commit.
3. Listener lỗi/retry.
4. Listener commit rồi, nhưng reader giữ snapshot cũ.
5. Listener hoàn tất state chính nhưng side effect hậu kỳ chưa xong.
6. DB connection pool/lock hoặc thread pool backlog.

Observability ở mục 7 giúp phân biệt các tình huống đó; không giải quyết bằng cách tăng 6 s thành 60 s một cách mù mờ.

## 6. Kiểm thử replay/retry của consumer: chờ **attempt thứ hai**, không chờ state cũ

Đối với event-driven application, delivery thường phải được thiết kế **chịu được redelivery**. Bài test nên thử ít nhất hai câu:

- Lỗi transient có thể được xử lý lại đúng policy mà không bỏ mất event?
- Khi cùng logical event được xử lý **lần hai**, có tránh được receipt/inventory/ledger side effect trùng?

### 6.1. Vì sao kiểm tra `PAID` hai lần là sai?

```java
publisher.publishEvent(event);
await().until(() -> queries.paymentOf(orderId)
        .filter(view -> "PAID".equals(view.status()))
        .isPresent());

publisher.publishEvent(event);

// Sai: state PAID đã có từ attempt 1, nên có thể PASS ngay
// trước khi attempt 2 được consumer xử lý.
await().until(() -> queries.paymentOf(orderId)
        .filter(view -> "PAID".equals(view.status()))
        .isPresent());
```

Một test idempotency phải chờ **tín hiệu attempt 2 đã hoàn tất**, rồi mới assert count của side effect.

### 6.2. Khung JUnit với test probe và publisher commit thật

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;

class PaymentRedeliveryIT {

    // Các kiểu do test/application tự triển khai:
    CommittedPaymentEventPublisher publisher;
    AttemptCompletionProbe attempts;
    PaymentReceiptQueries receipts;
    OrderFixture fixture;

    @Test
    void sameLogicalEventNeverCreatesTwoReceipts() {
        UUID orderId = fixture.awaitingPaymentAndCommit();
        UUID eventId = UUID.randomUUID();
        String key = "capture-" + eventId;

        PaymentCaptured event =
                new PaymentCaptured(eventId, orderId, key, amount);

        // Dùng API test/app publish trong transaction đã commit.
        publisher.publishAndCommit(event);

        await().atMost(Duration.ofSeconds(6))
                .untilAsserted(() ->
                        assertThat(attempts.completed(eventId))
                                .isGreaterThanOrEqualTo(1));

        publisher.publishAndCommit(event); // Giữ cùng logical event ID.

        await().atMost(Duration.ofSeconds(6))
                .untilAsserted(() ->
                        assertThat(attempts.completed(eventId))
                                .isGreaterThanOrEqualTo(2));

        assertThat(receipts.countCommittedByTransaction(key))
                .isEqualTo(1);
    }
}
```

Đây là **khung integration test**, không phải mã có thể copy vào project bất kỳ rồi chạy: `CommittedPaymentEventPublisher`, `AttemptCompletionProbe`, `PaymentReceiptQueries`, `fixture`, `amount` và `PaymentCaptured` phải được triển khai/import theo ứng dụng. Probe cần ghi **completed attempt sau mốc terminal thích hợp**, không chỉ “listener method vừa được gọi”. Nếu mốc probe được ghi trước commit thì count 2 không đủ chứng minh side effect đã bền; lúc đó vẫn phải đọc committed state sau completion.

### 6.3. Test riêng failure → recovery qua Event Publication Registry

Spring Modulith Event Publication Registry có thể lưu trạng thái publication hướng tới listener target và hỗ trợ xử lý lại incomplete publications **theo provider và cấu hình**. Không mặc định rằng framework tự thực hiện ba lần retry với cùng delay như ở mục 4.

Kịch bản kiểm chứng đúng:

1. Dùng database/registry storage **cô lập** với các test khác.
2. Tạo event `E1` và listener target có lỗi transient chủ đích; publish trong transaction đúng.
3. Xác nhận application behavior chưa hoàn tất, publication `E1 + target` được ghi nhận là incomplete theo API/provider phù hợp.
4. Kích hoạt/đợi cơ chế resubmission **thật sự được cấu hình trong ứng dụng**; không bịa tên API retry.
5. Chờ attempt/recovery terminal và trạng thái nghiệp vụ của đúng E1.
6. Assert không có side effect trùng; phân biệt completed row được giữ hay xóa theo retention/provider.
7. Dừng retry worker/test-owned resources an toàn rồi cleanup đúng registry namespace.

**Không xóa toàn bộ publication registry trong `@AfterEach`** nếu worker của test khác còn chạy. Một logical event có thể có nhiều publication theo listener target; không đồng nhất `eventId` với primary key của publication row.

## 7. Xác định mức observability: mỗi trạng thái phải có tín hiệu riêng

Observability tốt không đồng nghĩa ghi log mọi lần poll. Mục tiêu là **phân biệt các trạng thái mà test nhìn thấy giống nhau**.

### 7.1. Bảng tín hiệu tối thiểu của luồng

| Mốc | Log có cấu trúc | Metrics có ích | Trace/span | Oracle test nào xác minh? |
| --- | --- | --- | --- | --- |
| Command được nhận | `orderId`, `correlationId` | Requests by result | Command span | Public API outcome |
| Event published | `eventId`, event type, module | Events published count | Producer span/link | `PublishedEvents` |
| Registry publication created | Event ID, target ID, publication status | Incomplete count theo target | Registry span (nếu instrument) | Provider-aware registry query |
| Listener attempt started | `eventId`, listener, attempt no. | Attempts counter | Consumer span | Attempt probe |
| Transient failure/backoff | Error class, attempt, next eligible time | Retry counter, backoff histogram | Error status | Retry policy / recovery test |
| DB transaction committed | `orderId`, event ID, state | Commit latency | DB span | Public query fresh committed state |
| Broker ack/offset commit | Topic/queue, consumer group, event ID | Ack/retry/DLQ metrics | Transport span | Broker integration test |
| Terminal outcome | Completed/exhausted/dead-letter/reconcile | Outcomes counter, latency histogram | Final span status | State + completion/registry oracle |

Không phải mọi hệ thống có sẵn toàn bộ span/metric trong bảng. **Mức observability cần chọn theo rủi ro**: với unit policy chỉ cần input/attempt count; với after-commit module test cần event/state/attempt; với broker recovery cần ack/offset/DLQ và durable registry.

### 7.2. Correlation phải đi xuyên các boundary

Ba ID không nên bị trộn:

- **Aggregate ID** (`orderId`): business entity bị ảnh hưởng.
- **Logical event/request ID** (`eventId` hoặc `idempotencyKey`): dùng để nhận biết retry/redelivery cùng công việc.
- **Trace/span ID**: dùng liên kết hoạt động quan sát; có thể thay qua mỗi delivery/process và không phải business uniqueness key.

Một record log ví dụ:

```json
{
  "module": "orders",
  "listener": "PaymentCapturedListener",
  "eventId": "E-73",
  "orderId": "O-26",
  "attempt": 2,
  "outcome": "RETRYABLE_FAILURE",
  "errorType": "DatabaseTemporarilyUnavailable",
  "durationMs": 183,
  "traceId": "example-trace-id"
}
```

Đây là **payload log minh họa**, không phải log thu được. Trong ứng dụng thực, dùng structured logging/MDC hoặc context propagation tương ứng; nhớ clear `ThreadLocal/MDC` trong `finally` trên executor worker để không rò correlation của test A sang B.

### 7.3. Metrics không được gắn `eventId` làm label

Một counter/histogram được gắn label `eventId`, `orderId` hoặc `transactionId` sẽ có cardinality rất cao, tăng memory/storage cost và khó vận hành. Hãy dùng nhãn có tập giá trị nhỏ:

- `module=orders`, `listener=payment-captured`.
- `outcome=completed|retryable|permanent|exhausted`.
- `dependency=payment-gateway|postgres|broker`.

Giữ ID cụ thể trong **logs/traces** có kiểm soát quyền truy cập, không đặt vào metric labels; không ghi payload nhạy cảm hoặc thông tin thanh toán thật.

### 7.4. JUnit kiểm chứng instrumented metrics một cách độc lập

Ví dụ một metrics adapter nhỏ với Micrometer:

```java
import io.micrometer.core.instrument.MeterRegistry;

final class ListenerAttemptMetrics {

    private final MeterRegistry registry;

    ListenerAttemptMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void recorded(String outcome) {
        registry.counter(
                "modulith.listener.attempts",
                "listener", "payment-captured",
                "outcome", outcome)
                .increment();
    }
}
```

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ListenerAttemptMetricsTests {

    @Test
    void recordsOutcomesWithoutHighCardinalityLabels() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new ListenerAttemptMetrics(registry);

            metrics.recorded("retryable");
            metrics.recorded("completed");

            double retryable = registry
                    .get("modulith.listener.attempts")
                    .tag("listener", "payment-captured")
                    .tag("outcome", "retryable")
                    .counter().count();

            double completed = registry
                    .get("modulith.listener.attempts")
                    .tag("listener", "payment-captured")
                    .tag("outcome", "completed")
                    .counter().count();

            assertThat(retryable).isEqualTo(1.0);
            assertThat(completed).isEqualTo(1.0);
        }
    }
}
```

Test này kiểm tra **metrics wrapper**, không tự chứng minh listener thật gọi wrapper hoặc trace context truyền qua broker. Đối với integration test, instrument listener thật và dùng test registry/probe có scope riêng; tránh assert global counters trong Spring singleton đã được test khác sử dụng.

## 8. Kiểm thử đường thất bại: timeout và negative assertions phải có terminal signal

Một test failure-path không nên viết:

```java
publisher.publishEvent(event);
assertThat(queries.paymentOf(orderId)).isEmpty();
// Sai: listener có thể chưa chạy hoặc chưa commit.
```

Nếu muốn khẳng định “không có side effect sau lỗi vĩnh viễn”, trước tiên phải chờ **trạng thái terminal** của attempt đó: ví dụ `REJECTED`, completed failure event, DLQ entry hoặc completion probe thuộc đúng event ID. Chỉ khi đó mới assert không có receipt trùng/không có trạng thái `PAID`.

### 8.1. Test cơ chế timeout độc lập với nghiệp vụ

JUnit và Awaitility hỗ trợ kiểm tra thời hạn theo các semantics khác nhau. Ví dụ một test **cố ý kích hoạt timeout của phép chờ** mà không phải làm một test trong suite luôn FAIL:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.awaitility.core.ConditionTimeoutException;
import org.junit.jupiter.api.Test;

class BoundedWaitContractTests {

    @Test
    void reportsTimeoutIfConditionNeverBecomesTrue() {
        var finished = new AtomicBoolean(false);

        assertThatThrownBy(() ->
                await()
                    .pollInterval(Duration.ofMillis(20))
                    .atMost(Duration.ofMillis(300))
                    .untilTrue(finished))
                .isInstanceOf(ConditionTimeoutException.class);
    }
}
```

**Bằng chứng:** test harness dùng bounded wait và có failure type nhận diện được. Nó **không** chứng minh listener nghiệp vụ xử lý timeout chính xác. Muốn kiểm tra listener, đưa vào test fault injection/timeout có event ID riêng và chờ terminal outcome của listener/registry như phần dưới.

### 8.2. `assertTimeout` và `assertTimeoutPreemptively` khác nhau

- `assertTimeout(...)` của JUnit **không cắt ngang** executable khi hết hạn; nó kiểm tra elapsed duration sau khi executable hoàn tất.
- `assertTimeoutPreemptively(...)` chạy executable trong **thread khác** để cắt chờ theo timeout. Trong Spring integration tests có **test-managed transaction gắn thread**, đường này có thể chạy bên ngoài transaction test và commit dữ liệu ngoài ý muốn.
- Với test event/DB, ưu tiên một bounded waiting API như `Scenario.andWaitAtMost(...)` hoặc Awaitility, kèm app timeouts thật và cleanup có ownership, thay vì dựa vào preemptive timeout để “ngắt” toàn test.

Một timeout ở mức test **không tự rollback** remote charge, broker message đã gửi, listener transaction đã commit hoặc registry publication đã ghi bền.

### 8.3. Sau timeout phải xem xét worker vẫn sống

Khi `Scenario` hoặc Awaitility hết hạn, listener async có thể vẫn đang chạy. Nếu teardown ngay lập tức `TRUNCATE` bảng hoặc purge queue chung, test sau có thể nhận data race từ worker cũ. Một failure-path harness tốt cần:

1. Ghi correlation/event ID, attempt count, last observed state.
2. Dừng stimulus mới/test-owned observer đúng lifecycle.
3. Chờ quiescence có giới hạn nếu có API completion.
4. Nếu không thể xác nhận worker đã dừng, **cách ly test namespace/container**, báo cleanup failure và không xóa bừa resource shared.
5. Chỉ cleanup DB/registry/broker theo ownership sau mốc an toàn.

## 9. Chọn bằng chứng tích hợp và quality gate CI cho timeout/retry

Một policy test Mockito như mục 4 đủ cho logic quyết định retry, **không đủ cho transport/transaction semantics**. Hãy chọn test bổ sung đúng nơi rủi ro xuất hiện.

| Mục tiêu | Loại test nên dùng | Oracle | Có cần dependency thật? |
| --- | --- | --- | --- |
| Max attempts, lỗi retryable/permanent, key giữ nguyên | Unit policy test | Mockito call count + terminal exception | Không |
| HTTP connect/read deadlines, status 429/503, header idempotency | Adapter contract test với stub server | Request/response mapping, deadline config | HTTP client thật; stub server thường đủ |
| Event application listener cập nhật order | `@ApplicationModuleTest` + `Scenario` | Public state đúng event ID sau commit | Spring context và storage theo SUT; không nhất thiết broker |
| Database lock/deadlock/statement timeout | PostgreSQL integration | Kết quả transaction, unique/invariant | DB engine thật khi semantics quan trọng |
| Registry incomplete → resubmission → completion | Spring Modulith integration có provider thật | Publication theo event/target + business state | Registry storage/provider thật |
| RabbitMQ ack/requeue/DLQ | Broker integration | Queue + ack/terminal state đúng correlation | RabbitMQ container nếu cần transport thật |
| Kafka consumer group/offset/retry topic | Broker integration | Group/offset, payload, DLQ/retry | Kafka container nếu cần semantics broker |
| Trace/span context xuyên executor/broker | Instrumented integration | Context propagation, span relationship | Có thể cần real executor/broker path |
| Kiểm chứng module graph | `ApplicationModules.of(...).verify()` | Rules/cycles/named interfaces | Không cần Docker |

### 9.1. Không nhầm Spring event với broker delivery

`Scenario.publish(...)` và `PublishedEvents` của Spring Modulith là các công cụ kiểm chứng **Spring application events** trong test context. Chúng không tự chứng minh Kafka topic/partition/offset hay RabbitMQ queue/ack. Nếu production luồng có outbox/broker bridge, cần test adapter/broker integration cho đoạn đó.

Với registry, một event có thể có nhiều publications đến các target; test nên quan sát đúng **event ID + target** và trạng thái dựa trên provider/retention được cấu hình. Không dựa vào global `countIncomplete()` nếu database còn chứa publication của test khác.

### 9.2. Architecture verification vẫn là một gate độc lập

Một bản sửa timeout có thể vô tình khiến `orders` import `payments.internal.PaymentRepository` để query trạng thái, phá boundary mặc dù integration test xanh. Công bố event contract qua named interface và xác minh graph:

```java
// File: com/example/shop/payments/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.payments.events;
```

```java
// File: com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "payments::events")
package com.example.shop.orders;
```

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTests {

    @Test
    void keepsDependenciesWithinDeclaredContracts() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là application class minh họa. `ApplicationModules.verify()` bảo vệ dependency rules, **không** xác minh retry timings hoặc listener commit.

### 9.3. Quy trình CI đề xuất

1. **Architecture + policy unit tests:** nhanh, không Docker; bắt nhầm error classification/max attempts.
2. **Module event tests:** dùng `@ApplicationModuleTest`, bounded wait và event-specific state assertions.
3. **Adapter contract tests:** HTTP timeouts/idempotency headers/status mapping với stub server.
4. **Persistence/registry tests:** DB thật khi transaction/constraint/recovery là trọng tâm.
5. **Broker retry tests:** Kafka/RabbitMQ transport, ack/requeue/DLQ chỉ ở nhóm cần.
6. **Failure injection:** transient→success, permanent→no retry, exhausted→terminal, redelivery→idempotent.
7. **Observability gate:** mỗi failure có mã lỗi, correlation và attempt/terminal signal; metrics labels kiểm soát cardinality.
8. **Isolation gate:** rerun và parallel ở nhóm đủ scope; timeout không để worker/registry/queue cũ nhiễm test khác.
9. **Không nuốt flaky:** test retry ở CI chỉ để điều tra, không thay thế root-cause fix.
10. **Khi dependency thiếu:** báo integration NOT_RUN/FAILED rõ; không biến “Docker không có” thành bằng chứng test PASS.

### 9.4. Report khi test timeout phải có thông tin hành động được

```text
test: PaymentEventCompletionTests.commitsOnlyTheExpectedEvent...
module: orders
eventId: E-73
orderId: O-26
testAwaitBudget: 6s
lastObservedState: AWAITING_PAYMENT
listenerStarted: true
completedAttempts: 1
lastAttemptOutcome: RETRYABLE_FAILURE
registryStatusForTarget: INCOMPLETE
brokerAck: NOT_APPLICABLE (Spring in-process event)
dbTransactionOutcome: UNKNOWN
cleanupQuiescent: NOT_CONFIRMED
classification: listener/retry path needs investigation
```

Đây là **mẫu output**, không phải dữ liệu thật. Nếu thiếu một tín hiệu, ghi **UNKNOWN**, không suy đoán “listener fail” chỉ vì timeout. Không log token, secrets hoặc payload thanh toán thật.

## 10. Checklist review, bài tập kiểm chứng và tài liệu

### 10.1. Checklist timeout, retry và observability

- [ ] Mỗi timeout có **owner/boundary** rõ: connect, request, attempt, retry, listener, test await, CI?
- [ ] Test await budget được suy từ các attempt/backoff/commit/dispatch hợp lý, không chọn ngẫu nhiên?
- [ ] Timeout application được cấu hình riêng, không nhầm `andWaitAtMost` với HTTP/DB timeout?
- [ ] Có phân biệt **permanent failure**, **retryable transient** và **unknown outcome**?
- [ ] Max attempts tính cả lần đầu và có terminal behavior khi exhausted?
- [ ] Backoff/jitter có giới hạn; không nhân retry qua nhiều tầng không kiểm soát?
- [ ] Retry cùng logical request giữ nguyên idempotency key/event ID?
- [ ] Sau redelivery lần 2, test chờ **attempt 2 completed** rồi mới assert không double side effect?
- [ ] `Scenario` lọc đúng `orderId`, `eventId`, transaction key và business amount?
- [ ] Fixture/publisher commit thật khi listener cần `AFTER_COMMIT`?
- [ ] Reader lấy fresh committed state, không assert trên JPA entity cached?
- [ ] Không coi `PublishedEvents` là bằng chứng consumer đã commit hoặc broker đã ack?
- [ ] Registry failure/recovery được kiểm tra theo provider, event ID và listener target?
- [ ] Logs có correlation IDs/attempt/outcome nhưng không lộ secrets?
- [ ] Metrics tags có cardinality thấp; không dùng event/order IDs làm labels?
- [ ] Worker async/quiescence và cleanup được xử lý an toàn khi timeout?
- [ ] Có adapter/broker/Testcontainers test riêng nếu cần chứng minh giao thức thật?
- [ ] CI phân biệt FAIL, UNKNOWN và NOT_RUN, không che flaky bằng retries?
- [ ] `ApplicationModules.verify()` vẫn chặn phụ thuộc sai giữa module?

### 10.2. Bài tập A–I

**Bài A — lập budget:** với 3 attempts × 700 ms, 2 backoffs × 150 ms, 600 ms DB và 400 ms scheduling, tính upper estimate. Giải thích vì sao chờ 6 s trong test có dự phòng nhưng không phải SLA production.

**Bài B — transient policy:** chạy `RetryingCaptureGatewayTests`, thay transient đầu tiên bằng permanent `PaymentDeclined`. Xác minh không có backoff và đúng một attempt.

**Bài C — exhausted attempts:** để remote luôn ném `TemporaryGatewayUnavailable`. Test phải nhận terminal exception sau 3 attempts, chỉ có 2 lần backoff.

**Bài D — unknown payment outcome:** mô phỏng response timeout sau khi request có thể đến PSP. Thảo luận vì sao retry với một key mới có thể double charge và khi nào cần reconcile thay vì retry.

**Bài E — module state:** triển khai `PaymentEventCompletionTests`, cố tình đổi `processedEventId` trong listener sang ID khác. Predicate phải timeout, không pass vì chỉ thấy `PAID`.

**Bài F — after-commit:** viết listener `@TransactionalEventListener(AFTER_COMMIT)`, thử publish trong transaction rollback, rồi publish qua một command commit thật. So sánh tín hiệu completed attempts và state query.

**Bài G — redelivery idempotency:** gửi cùng logical event hai lần, dùng attempt-completion probe để chắc lần hai đã kết thúc. Assertion receipt count phải bằng 1, không chấp nhận “order đã PAID từ lần đầu” làm bằng chứng.

**Bài H — registry/broker:** gây incomplete publication trong registry storage test riêng, kích hoạt resubmission theo cấu hình. Nếu có Kafka/RabbitMQ, chạy một phép kiểm transport ack/DLQ **riêng**; không suy từ Spring event test.

**Bài I — observability + CI:** thêm metric attempt outcome với labels giới hạn, structured logs theo event ID và report timeout chứa last observed state. Thử dừng listener: test phải FAIL có chẩn đoán, không chỉ báo “timeout after 6 s”. Giữ architecture test chạy độc lập Docker.

### 10.3. Tự kiểm tra nhanh

1. **Một test `Scenario` chờ 6 s có bảo đảm HTTP client tự timeout sau 6 s?** Không. Hai budget ở boundary khác nhau.
2. **Gateway trả permanent decline có nên retry vì CI đôi khi chậm?** Không. Retry dựa vào error contract, không dựa vào việc test đỏ.
3. **Response timeout sau charge có chứng minh PSP chưa thu tiền?** Không. Đây có thể là unknown outcome cần idempotency/reconciliation.
4. **Order đã `PAID` có chứng minh redelivery attempt thứ hai hoàn tất?** Không; phải chờ completion signal của attempt 2.
5. **Một `PublishedEvents` PASS có chứng minh registry complete hoặc Kafka ack?** Không, mỗi thứ là một oracle khác nhau.
6. **Tại sao không dùng `eventId` làm metric label?** Vì cardinality rất lớn và gây chi phí vận hành; giữ ID trong logs/traces.
7. **Có nên dùng `assertTimeoutPreemptively` cho Spring test-managed transaction?** Cần rất thận trọng: executable chạy thread khác, transaction context có thể không theo sang.
8. **Cần gì để nói “timeout là lỗi listener”?** Bằng chứng listener started/attempt outcome và transaction/reader status, không chỉ một timeout của polling.

### 10.4. Tài liệu tham khảo

- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario`, `PublishedEvents`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): Event Publication Registry, listener và resubmission.
- [Spring Modulith — Verification](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và dependency rules.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và `AFTER_COMMIT`.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): thread-bound test transactions.
- [JUnit 5 User Guide — Assertions](https://junit.org/junit5/docs/current/user-guide/#writing-tests-assertions): `assertTimeout` và `assertTimeoutPreemptively`.
- [Awaitility — Usage](https://github.com/awaitility/awaitility/wiki/Usage): bounded asynchronous assertions.
- [Mockito — JUnit Jupiter](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/index.html): stubbing và verification.
- [Micrometer — Documentation](https://docs.micrometer.io/micrometer/reference/): counters, timers, tags và instrumentation.
- [Micrometer Observation — Documentation](https://docs.micrometer.io/micrometer/reference/observation.html): observation, spans và context.
- [Testcontainers for Java](https://java.testcontainers.org/): database/broker integration tests.
- [Java SE — System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()): elapsed-time measurement.

**Chốt chiến lược:** timeout chỉ có giá trị khi biết **đang chờ boundary nào**; retry chỉ an toàn khi biết **loại lỗi, owner và idempotency**; observability chỉ đủ khi có thể nối **event → attempt → commit/ack → terminal outcome**. Unit policy tests giúp xác định quyết định retry, module tests kiểm chứng eventual state, và integration tests chứng minh những transaction/transport semantics mà mock không thể thay thế.
