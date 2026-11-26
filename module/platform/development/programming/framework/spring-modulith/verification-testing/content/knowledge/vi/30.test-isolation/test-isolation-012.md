# Thiết kế test có thể chạy lại nhiều lần trong Spring Modulith

## 1. Tiêu chuẩn kiểm chứng: cùng test, nhiều lượt, cùng kết luận

Một bài test `PaymentCapturedScenarioTests` chạy một lần PASS nhưng lần hai FAIL vì trùng `transactionId`, hoặc lần hai PASS ngay vì order đã là `PAID` trước khi publish event. Trong cả hai trường hợp, kết quả đều **không đáng tin**.

Tiêu chuẩn của bài:

> Mỗi lượt chạy tự tạo tiền đề, gửi stimulus của chính nó, quan sát đúng hậu điều kiện đã commit, và không để lại trạng thái khiến lượt sau thay đổi kết luận.

Không yêu cầu UUID, timestamp hạ tầng hoặc thứ tự scheduling bất đồng bộ giống hệt nhau giữa các lần. Điều cần ổn định là **hợp đồng nghiệp vụ, invariant và cách test xác minh chúng**.

Bài thuộc chương *Test isolation* của học phần `SPRING_MODULITH_VERIFICATION_TESTING`. Mục tiêu của học phần là kiểm chứng ranh giới kiến trúc Spring Modulith bằng `ApplicationModules` và quy tắc phụ thuộc, kiểm thử `@ApplicationModuleTest` với event, database, tích hợp; sau đó đưa các phép kiểm vào CI quality gate để ngăn phụ thuộc sai và hồi quy.

Điểm cần phân biệt ngay:

| Hành động | Ý nghĩa | Không được suy ra |
| --- | --- | --- |
| **Lặp JUnit test** | Chạy lại một kịch bản độc lập với fixture riêng | Không có nghĩa phải gửi lại cùng logical event ID |
| **Rerun test task/build** | Khởi chạy lại cùng test trong JVM/CI run mới | Không có nghĩa external DB/broker đã sạch |
| **Retry test khi FAIL** | Chạy lại một test lỗi để chẩn đoán hoặc che flaky | Lần sau PASS không chứng minh lần trước đúng |
| **Replay/redelivery event** | Giao lại **cùng logical event** tới consumer | Không giống tạo event mới cho mỗi lượt test |

Với repeated tests, hãy luôn đặt câu hỏi: **nếu event của lượt hiện tại không được xử lý, test có thể vẫn xanh nhờ dữ liệu lượt trước không?** Nếu có, oracle của test chưa đủ mạnh.

## 2. Năm điều kiện cho mỗi lượt chạy

| Mốc | Điều kiện cần có | Cách chứng minh |
| --- | --- | --- |
| **Baseline mới** | Aggregate thuộc lượt hiện tại, state xuất phát đúng | `orderId` mới, `AWAITING_PAYMENT`, `processedEventId == null` |
| **Stimulus riêng** | Event và transaction key không va chạm với lượt khác | Ghi `eventId`, `transactionId` của lượt này |
| **Outcome đúng** | Consumer xử lý đúng logical event | Query theo `orderId`, match `eventId`, transaction và amount |
| **Completion đủ mạnh** | Những side effect phải dọn không còn đang ghi | Commit visible, completion/ack/registry target tương ứng |
| **Release an toàn** | Lượt tiếp không bị data/resource của lượt này ảnh hưởng | Cleanup theo owner hoặc môi trường/schema riêng |

Một test chỉ có bước outcome thường pass giả. Một test có baseline và outcome nhưng không xử lý completion/release có thể pass trước khi listener, retry worker hoặc broker observer của lượt cũ hoàn tất.

### 2.1. Không đồng nhất deterministic input với ID cố định

Có thể giữ amount, Clock và business rule giống nhau ở mọi lượt. Nhưng **identity** của order, event và transaction độc lập cần khác nhau nếu cùng database/broker.

```java
UUID orderId = UUID.randomUUID();
UUID eventId = UUID.randomUUID();
String transactionId = "CAPTURE-" + eventId;
```

UUID có thể khác giữa các lần mà kết luận vẫn xác định: test luôn dùng **chính ID vừa tạo** cho fixture, event và assertion. Không dựa vào việc `orderId == 1` hoặc `eventId` giống giá trị hôm trước.

## 3. Anti-pattern: dùng một ID suốt các repetitions

Ví dụ cố ý sai:

```java
import java.util.UUID;
import org.junit.jupiter.api.RepeatedTest;

class BrokenRepeatabilityTests {

    private static final UUID ORDER_ID =
            UUID.fromString("00000000-0000-0000-0000-000000000001");

    @RepeatedTest(3)
    void createsOrderWithSharedId() {
        repository.save(new Order(ORDER_ID, "AWAITING_PAYMENT"));
        // Lần sau có thể gặp unique constraint,
        // ghi đè row hoặc đọc lại trạng thái PAID cũ.
    }
}
```

`Order` và `repository` là thành phần ví dụ do ứng dụng triển khai. Nếu lần đầu commit row và chưa cleanup, lần thứ hai có thể fail vì unique key. Nếu repository dùng upsert, lỗi còn có thể bị che.

Hướng sửa:

```java
@RepeatedTest(3)
void createsFreshOrder() {
    UUID orderId = UUID.randomUUID();
    fixture.createAndCommit(orderId);

    assertThat(queries.findById(orderId)).isPresent();

    // Resource scope chịu trách nhiệm teardown đúng ID.
}
```

**Đổi ID mới chỉ giải quyết trùng key.** Còn phải đảm bảo baseline được kiểm tra, query trả state của đúng ID và dữ liệu/worker của lượt cũ không gây nhiễm.

### 3.1. Không tạo unique ID từ clock đã đóng băng

```java
String id = "ORDER-" + clock.instant().toEpochMilli();
```

Nếu business clock được `Clock.fixed(...)`, mọi lượt sẽ tạo ID giống nhau. Ngay cả clock thật cũng có thể có hai lời gọi trong một mili-giây. Giữ timestamp như metadata và dùng ID generator có hợp đồng uniqueness phù hợp.

## 4. JUnit `@RepeatedTest`: một ví dụ Java chạy được

JUnit Jupiter cung cấp `@RepeatedTest(n)` cùng `RepetitionInfo`. Mặc định Jupiter tạo test object mới theo `PER_METHOD`, nhưng điều này **không làm mới** Spring context, database, static fields hay external broker.

Ví dụ unit test tự chứa dưới đây lặp 32 lần với input có seed độc lập theo từng lượt:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.SplittableRandom;

import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.RepetitionInfo;
import org.junit.jupiter.api.Test;

class PaymentDeadlineRepeatabilityTests {

    private static final Instant DEADLINE =
            Instant.parse("2026-11-26T10:00:00Z");

    record PaymentDeadlinePolicy(Clock clock) {
        boolean expired(Instant deadline) {
            return clock.instant().isAfter(deadline);
        }
    }

    @RepeatedTest(
            value = 32,
            name = "deadline check {currentRepetition}/{totalRepetitions}")
    void checksGeneratedOffset(RepetitionInfo repetition) {
        long seed = 20261126L + repetition.getCurrentRepetition();

        // Mỗi invocation có PRNG mới; không tiêu thụ static Random.
        var random = new SplittableRandom(seed);
        long deltaMillis = random.nextLong(-1000, 1001);
        Clock clock = Clock.fixed(
                DEADLINE.plusMillis(deltaMillis),
                ZoneOffset.UTC);

        boolean actual =
                new PaymentDeadlinePolicy(clock).expired(DEADLINE);

        assertThat(actual)
                .as("repetition=%s seed=%s delta=%s",
                        repetition.getCurrentRepetition(),
                        seed, deltaMillis)
                .isEqualTo(deltaMillis > 0);
    }

    @Test
    void exactlyAtDeadlineIsNotExpired() {
        var policy = new PaymentDeadlinePolicy(
                Clock.fixed(DEADLINE, ZoneOffset.UTC));

        assertThat(policy.expired(DEADLINE)).isFalse();
    }
}
```

Các bằng chứng repeatability:

- Một repetition không tiêu thụ random state của repetition trước.
- Seed và input gây lỗi có thể ghi lại.
- Business clock không phụ thuộc lúc máy CI chạy.
- Điều kiện tại chính deadline được kiểm tra riêng, không hy vọng random chọn được số 0.
- Không cần Spring context/DB để xác minh domain policy.

Một phép thử 32 lần **không phải** property-based testing đầy đủ, không tự shrink lỗi và không bao phủ mọi interleaving của worker. Nó kiểm tra cách thiết kế một lần gọi có thể tái hiện, không chứng minh toàn bộ hệ thống không có race.

### 4.1. Repetition có thể chạy đồng thời không?

Khi JUnit parallel execution được bật với chính sách tương ứng, nhiều invocation có thể chạy concurrent. Giai đoạn đầu hãy lặp **tuần tự** để bắt state leak, sau đó thử concurrent như một test isolation khác. Không dùng `static int currentRepetition` để tính số lượt, bởi nó vừa chứa mutable state vừa có thể race.

## 5. Đặt fixture trong scope của từng invocation

Một lỗi thường gặp:

```java
static UUID sharedOrderId;

@BeforeAll
static void seedOnceForTheWholeClass() {
    sharedOrderId = fixture.createOrderAndCommit();
}
```

Order đã `PAID` ở lượt đầu không còn baseline `AWAITING_PAYMENT` cho lượt sau. Nếu muốn kiểm thử cùng một workflow nhiều bước, hãy viết **một scenario nhiều pha có chủ đích**, không gọi nó là repeated independent test.

Thay vào đó, dùng một handle quản lý **từng case**:

```java
// Test-support API do dự án tự định nghĩa.
import java.math.BigDecimal;
import java.util.UUID;

interface RepeatableOrderCase extends AutoCloseable {

    UUID orderId();

    void createAwaitingPaymentAndCommit(BigDecimal amount);

    void trackEvent(UUID eventId);

    // Quiescence + dọn dữ liệu thuộc riêng case hoặc báo lỗi.
    @Override
    void close();
}

interface RepeatableOrderCaseFactory {
    RepeatableOrderCase openCase();
}
```

Một implementation đúng cần:

1. Cấp `orderId` mới khi mở case, ghi ownership ngay trước side effect.
2. Nếu setup fail sau khi đã tạo một phần resource, factory phải rollback hoặc dọn phần đã sở hữu.
3. Commit fixture trước khi listener ở thread/transaction khác đọc.
4. Nhận `eventId` trước publish để biết các callback cần chờ.
5. Dọn theo ID hoặc hủy namespace riêng, không `deleteAll()` DB dùng chung.
6. Không stop listener/executor production do Spring context quản lý.
7. Nếu không thể xác nhận worker quiescent, báo teardown failure và cách ly tài nguyên còn sót thay vì xóa bừa.

`RepeatableOrderCase` **không có sẵn trong Spring Modulith**. Nó là một API test-support minh họa cách gói ownership. Lợi ích của `AutoCloseable` là Java vẫn gọi `close()` khi assertion trong `try-with-resources` ném exception thông thường. Điều đó chưa chứng minh deletion đã commit hoặc worker đã dừng; implementation vẫn phải xử lý.

## 6. Ví dụ `@ApplicationModuleTest` lặp 25 lần, không pass giả

Giả sử module `payments` công bố `PaymentCaptured`, module `orders` xử lý rồi cập nhật trạng thái. Các kiểu public dưới đây là **API của ứng dụng ví dụ**, không phải Spring Modulith tự sinh; mỗi kiểu public phải nằm trong file Java riêng.

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
// File: com/example/shop/orders/PaymentStatus.java
package com.example.shop.orders;

public enum PaymentStatus {
    AWAITING_PAYMENT, PAID, REJECTED
}
```

```java
// File: com/example/shop/orders/OrderPaymentView.java
package com.example.shop.orders;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderPaymentView(
        UUID orderId,
        PaymentStatus status,
        UUID lastEventId,
        String transactionId,
        BigDecimal capturedAmount) {

    public boolean paidFor(
            UUID expectedEvent,
            String expectedTransaction,
            BigDecimal expectedAmount) {

        return status == PaymentStatus.PAID
                && expectedEvent.equals(lastEventId)
                && expectedTransaction.equals(transactionId)
                && capturedAmount != null
                && capturedAmount.compareTo(expectedAmount) == 0;
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

Test lặp:

```java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.UUID;

import com.example.shop.payments.events.PaymentCaptured;

import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.RepetitionInfo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class PaymentCaptureRepeatabilityTests {

    @Autowired RepeatableOrderCaseFactory cases;
    @Autowired OrderQueries queries;

    @RepeatedTest(25)
    void eachRepetitionHasItsOwnPayment(
            Scenario scenario, RepetitionInfo repetition) {

        BigDecimal amount = new BigDecimal("125000.00");

        try (RepeatableOrderCase current = cases.openCase()) {
            UUID orderId = current.orderId();
            current.createAwaitingPaymentAndCommit(amount);

            OrderPaymentView baseline =
                    queries.paymentOf(orderId).orElseThrow();
            assertThat(baseline.status())
                    .as("baseline repetition %s",
                            repetition.getCurrentRepetition())
                    .isEqualTo(PaymentStatus.AWAITING_PAYMENT);
            assertThat(baseline.lastEventId()).isNull();

            UUID eventId = UUID.randomUUID();
            String transactionId = "TX-" + eventId;
            current.trackEvent(eventId);

            scenario.publish(new PaymentCaptured(
                            eventId, orderId, transactionId, amount))
                    .andWaitAtMost(Duration.ofSeconds(8))
                    .forStateChange(
                            () -> queries.paymentOf(orderId),
                            state -> state.filter(view ->
                                    view.paidFor(
                                            eventId, transactionId, amount))
                                    .isPresent())
                    .andVerify(state -> {
                        OrderPaymentView paid = state.orElseThrow();

                        assertThat(paid.orderId()).isEqualTo(orderId);
                        assertThat(paid.status())
                                .isEqualTo(PaymentStatus.PAID);
                        assertThat(paid.lastEventId())
                                .isEqualTo(eventId);
                        assertThat(paid.transactionId())
                                .isEqualTo(transactionId);
                        assertThat(paid.capturedAmount())
                                .isEqualByComparingTo(amount);
                    });
        }
    }
}
```

### 6.1. Các giả định triển khai phải xác minh

- `RepeatableOrderCaseFactory` là test bean được đăng ký trong context và tạo scope riêng cho mỗi invocation.
- Fixture thật sự commit row `AWAITING_PAYMENT` trước khi trả về. `saveAndFlush(...)` trong transaction chưa commit không đủ.
- Listener của `orders` được bootstrap trong phạm vi module test, đọc đúng event contract và ghi state trong transaction hợp lệ.
- `OrderQueries` đọc dữ liệu **đã commit mới**; không trả về một JPA entity cached trước stimulus.
- Với `@TransactionalEventListener(AFTER_COMMIT)`, transaction phát event phải commit theo hợp đồng. Không mặc định mọi path publish đều thỏa yêu cầu này.
- `RepeatableOrderCase.close()` chờ hoàn tất phần work sẽ bị cleanup; nếu không chứng minh được quiescence, phải báo lỗi và cô lập môi trường.
- Timeout 8 giây là ví dụ, cần điều chỉnh dựa trên độ trễ thực và trách nhiệm test.

### 6.2. Vì sao assertion này phát hiện reuse dữ liệu?

Từng repetition tự tạo `orderId` và `eventId`, kiểm tra baseline, rồi chỉ hoàn thành khi state khớp **đúng event ID, transaction ID và amount**. Nếu listener không chạy ở lượt 12, một order `PAID` từ lượt 11 không thể làm predicate của lượt 12 đúng.

Ngược lại, assertion:

```java
assertThat(orderRepository.findAll())
        .anyMatch(order -> order.getStatus() == PAID);
```

có thể pass nhờ lượt trước. Nếu test đang kiểm tra public behavior của module, nên đọc qua `OrderQueries` và đúng ID, không import repository `internal` của module khác.

### 6.3. Lượt thứ 26 trở đi

`@RepeatedTest(25)` chỉ kiểm tra 25 invocations trong một lần chạy JUnit. Khi khởi động Gradle lần hai, static state JVM có thể mất nhưng database/broker còn. Test cần vẫn độc lập với auto-increment, registry publication pending, Kafka offsets và state của external service.

## 7. Lặp test khác replay một logical event

Phân biệt rõ identity:

| Scenario | Aggregate | Logical event | Kết quả mong đợi |
| --- | --- | --- | --- |
| Repetition 1 | O1 | E1 | O1 được xử lý theo E1 |
| Repetition 2 | O2 | E2 | O2 độc lập O1 |
| Replay lần hai của E1 **trong repetition 1** | O1 | **Vẫn E1** | Không tạo side effect kép |
| Event nghiệp vụ mới trên cùng aggregate | O1 | E3 mới | Theo trạng thái/domain contract |

Một test idempotency có thể phát **cùng E1** hai lần, nhưng phải chờ **lần redelivery thứ hai hoàn tất** trước khi assert không có receipt mới. Chỉ nhìn `O1.status == PAID` đã có từ lần đầu có thể pass trước khi listener lần hai chạy.

Khung kiểm tra có chủ đích:

```java
PaymentCaptured event = new PaymentCaptured(
        eventId, orderId, transactionId, amount);

publisher.publishEvent(event);
awaitBusinessCompletion(eventId);

publisher.publishEvent(event);
awaitDeliveryAttemptCompleted(eventId, 2);

assertThat(receipts.countByTransaction(transactionId)).isEqualTo(1);
```

`publisher`, `awaitBusinessCompletion`, `awaitDeliveryAttemptCompleted` và `receipts` là test harness của ứng dụng. Không suy rằng `Scenario` chờ trạng thái `PAID` lần đầu chứng minh lần hai đã được xử lý.

**Test retry plugin không kiểm chứng idempotency**: một lần rerun test có thể tạo event ID mới, không phải redelivery cùng logical event.

## 8. Kiểm soát Clock, random và cấu hình theo đúng scope

Đầu vào của repeated test nên xác định, nhưng không dùng một singleton mutable chung.

| Nguồn | Rủi ro qua nhiều lượt | Cách thiết kế |
| --- | --- | --- |
| `Instant.now()` trực tiếp | Deadline thay đổi theo CI/timezone | Inject `Clock` và tạo thời điểm cố định cho test rule |
| `static Random(42)` | Lượt sau nhận phần tiếp theo của chuỗi random | Generator instance mới mỗi repetition, ghi seed |
| Adjustable clock singleton | Lượt 2 đọc thời gian được lượt 1 sửa | Clock immutable hoặc scope/context riêng |
| System property global | Lượt 1 đổi property, bean lượt 2 bind sai | `@TestPropertySource`/`@ActiveProfiles` theo class |
| Timestamp-based ID | Frozen clock tạo ID trùng | ID generator đúng uniqueness contract |
| Static counter/mock recorder | Assertion đếm cả lượt trước | Event-specific IDs, recorder scoped |

Ví dụ clock test:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class FixedBusinessClockConfiguration {

    @Bean
    @Primary
    Clock businessClock() {
        return Clock.fixed(
                Instant.parse("2026-11-26T10:00:00Z"),
                ZoneOffset.UTC);
    }
}
```

Import bean cấu hình này vào test khi cần:

```java
@ApplicationModuleTest
@Import(FixedBusinessClockConfiguration.class)
class DeadlineModuleTests {
    // Kiểm tra rule thời gian dưới clock đã xác định.
}
```

Cần xác minh service thật sự inject bean Clock đã tạo. JPA auditing, SQL `CURRENT_TIMESTAMP`, Kafka timestamp và scheduler có thể có nguồn thời gian riêng. Đồng hồ nghiệp vụ cố định cũng **không** dùng để đo timeout polling nếu nó không tiến triển.

## 9. Giao dịch: rollback không dọn hết side effect

Một repeated test trên DB dễ bị nhiễm vì listener/fixture có transaction ngoài test-managed transaction.

| State | Rollback của test method có dọn được? | Hành động khi rerun |
| --- | --- | --- |
| Entity chỉ ghi trong test-managed transaction và rollback | Thường có | Vẫn kiểm tra cache/async |
| Fixture `REQUIRES_NEW` commit | Không | Xóa theo ID bằng transaction được commit |
| Listener `@Async` transaction riêng | Không | Chờ completion, cleanup sau khi worker dừng |
| `@TransactionalEventListener(AFTER_COMMIT)` | Có thể không chạy nếu publisher rollback | Publish trong transaction commit theo contract |
| Event Publication Registry đã ghi bền | Không thể mặc định | Provider-aware cleanup hoặc schema riêng |
| Broker message đã gửi | Không | Queue/topic/group namespace và lifecycle riêng |

Ví dụ test fixture dùng `TransactionTemplate`:

```java
import java.util.UUID;

import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

final class OrderFixtureWriter {

    private final TransactionTemplate transactions;
    private final OrderRepository repository;

    OrderFixtureWriter(
            PlatformTransactionManager manager,
            OrderRepository repository) {
        this.transactions = new TransactionTemplate(manager);
        this.repository = repository;
    }

    void createAndCommit(UUID orderId) {
        transactions.executeWithoutResult(status ->
                repository.save(Order.awaitingPayment(orderId)));
    }
}
```

`OrderRepository`/`Order` là code ứng dụng minh họa. Với `TransactionTemplate` mặc định `PROPAGATION_REQUIRED`, callback **chỉ tự commit khi không có surrounding transaction**. Nếu test method đã có một test-managed transaction đang mở, template có thể tham gia transaction đó và không commit trước khi trả về. Khi listener cần đọc baseline từ thread khác, phải định nghĩa propagation rõ, không dùng `saveAndFlush(...)` thay cho commit.

### 9.1. Query cũng có thể là nguyên nhân fail ở lượt N

Một JPA entity đã load trước stimulus có thể giữ state cũ trong persistence context. Supplier cho `Scenario` nên đọc state mới bằng public query API có transaction/snapshot phù hợp:

```java
// Không nên poll trên entity đã cache trước stimulus:
Order cached = repository.findById(orderId).orElseThrow();
() -> cached.getStatus();

// Dùng query API đọc state committed mới:
() -> queries.paymentOf(orderId);
```

Nếu query adapter vẫn dùng persistence context lâu sống, gọi lại method có thể chưa đủ. Khi `Scenario` timeout nhưng database thực sự đã cập nhật, hãy chẩn đoán snapshot và transaction của reader trước khi tăng timeout.

## 10. Event Publication Registry có thể “sống qua” repetition

Spring Modulith Event Publication Registry có thể theo dõi publication tới từng listener target qua provider được cấu hình. Lượt trước bị lỗi có thể để lại incomplete publication rồi bị resubmit trong lượt sau.

```text
Repetition 7:
  E7 -> listener lỗi
  Registry giữ publication E7 / orders target.

Repetition 8:
  E8 -> listener đang xử lý
  Retry/resubmission worker đồng thời nhận E7.
  Global event count / shared read model có thể sai.
```

Biện pháp:

1. Ghi `eventId` và listener target thuộc mỗi repetition.
2. Không assert tổng incomplete publications toàn DB nếu storage còn dùng chung.
3. Khi kiểm thử failure/recovery, giữ publication qua nhiều pha **trong cùng scenario**.
4. Cô lập registry DB/schema cho test recovery có resubmission quét toàn bộ.
5. Chờ đúng completion của event/target trước khi cleanup.
6. Không `TRUNCATE` registry dùng chung trong `@AfterEach`.
7. Không giả định một event chỉ có đúng một publication hoặc completed row luôn được lưu/xóa giống nhau ở mọi provider.

`PublishedEvents` kiểm tra producer publication; Event Publication Registry kiểm tra tracking/durability; public query API kiểm tra business state. Một nguồn không thay thế bằng chứng của nguồn khác.

## 11. Kafka và RabbitMQ không khởi động lại chỉ vì test chạy lại

Một integration test có thể chạy trong JVM mới nhưng broker giữ messages/offsets từ lượt trước.

### 11.1. Kafka

| Resource | Failure mode khi rerun | Biện pháp |
| --- | --- | --- |
| Topic | Records của run trước còn | Topic/namespace riêng theo suite khi cần |
| Consumer group | Offset đã commit, observer không đọc như mong đợi | Group test riêng, assignment/offset đúng |
| Retry/DLT | Message lỗi cũ tiếp tục được xử lý | Cô lập retry topics, cleanup đúng owner |
| Producer async | Send chưa hoàn tất lúc teardown | Chờ send result/ack theo contract |
| Message payload | Test đọc message của case khác | Correlation/event ID filter |

`auto.offset.reset=earliest` không reset một group đã có committed offset hợp lệ. Observer dùng **cùng consumer group** với business consumer có thể tranh partition; nếu mục tiêu quan sát outbound message, dùng group riêng và chờ assignment phù hợp trước stimulus.

### 11.2. RabbitMQ

Queue bền có thể chứa message chưa ack, consumer mới có thể nhận redelivery từ test trước. Hai observer trên cùng queue chia message theo semantics consumer, không mặc nhiên nhận hai bản sao.

Nên cấp queue riêng cho test observer/namespace, theo dõi correlation ID, quản lý ack/nack/requeue và DLQ. Không purge một queue chung để “bắt đầu sạch” khi test khác hoặc worker cũ vẫn hoạt động.

### 11.3. Testcontainers có giảm rò state không?

Có thể, nếu ownership và lifecycle rõ. Một PostgreSQL/Kafka/RabbitMQ container static theo class **vẫn giữ dữ liệu trong các repetitions của class**. Nếu cần thử recovery hoặc phá topology, dùng schema/container riêng. Tránh cached Spring context giữ datasource/client trỏ đến container đã dừng sau class khác.

Đừng dùng container mới mỗi method chỉ để che static/singleton state leak trong JVM. Nên có cả **shared-context repetitions** và **fresh-environment reruns** để kiểm tra hai loại rủi ro.

## 12. Spring context cache, fake singleton và global recorder

`@ApplicationModuleTest` có thể tái sử dụng Spring `ApplicationContext` theo TestContext cache. Khi đó một fake bean mutable không có `static` vẫn có thể ghi nhớ event từ repetition trước.

```java
@Component
class RecordingNotificationPort implements NotificationPort {

    private final List<UUID> seen = new CopyOnWriteArrayList<>();

    @Override
    public void send(UUID eventId) {
        seen.add(eventId);
    }

    boolean saw(UUID eventId) {
        return seen.contains(eventId);
    }
}
```

`NotificationPort` là port của ứng dụng ví dụ. `seen.size() == 1` chỉ đúng nếu fake reset an toàn theo scope; khi context được reuse, test có thể nhận 2, 3, 25. Filter theo `eventId` hữu ích hơn, nhưng vẫn cần release entries sau khi callback liên quan xong.

Tránh những anti-pattern:

- Static dedup set làm nguồn sự thật nghiệp vụ; crash/restart hay nhiều JVM sẽ có kết quả khác.
- Static PRNG/clock/counter mutate xuyên test.
- Static listener/subscription giữ reference tới context cũ.
- Re-stub/reset cùng mock bean trong lúc một repetition khác còn dùng nó.
- `System.setProperty(...)` giữa methods rồi mong `@ConfigurationProperties` đã bind được cập nhật.
- `@DirtiesContext` tràn lan chỉ để che state thuộc test fixture.

`@DirtiesContext` chỉ loại Spring context khỏi cache; nó **không tự reset** static fields, database rows, Event Publication Registry hay broker offsets. Chọn mức isolation theo resource thật.

## 13. Khi một lượt FAIL, lượt sau phải không bị nhiễm

Một repeated test tốt không chỉ lặp happy path:

```text
Repetition 12:
  Commit order O12
  Publish event E12
  Scenario timeout -> test FAIL
  Listener E12 vẫn còn đang làm việc

Repetition 13:
  Commit O13, publish E13
  Retry E12 chạy đồng thời và gây side effect không liên quan.
```

Nếu test dùng `try-with-resources` để close case scope:

- `close()` phải được gọi trên đường assertion failure thông thường.
- Implementation phải đợi/điều phối **đúng event IDs** và side effects cần dọn.
- Đạt state `PAID` chưa chắc broker send, audit hoặc registry completion đã xong.
- Nếu không thể xác nhận quiescence, dừng cleanup nguy hiểm, báo failure và cô lập môi trường.
- Không stop executor/listener production thuộc Spring context chỉ để cứu một case.
- Không dùng `Thread.sleep(...)` làm bằng chứng worker đã hoàn tất.
- Không nuốt exception cleanup chỉ vì assertion gốc đã FAIL.

**Giới hạn:** JVM process chết đột ngột có thể không chạy `close()`/`@AfterEach`. Với resource bền, nên có job namespace, TTL/janitor hoặc container lifecycle do CI quản lý để thu hồi tài nguyên còn sót.

### 13.1. Cleanup theo ID chứ không global delete

```java
// Sai khi nhiều tests cùng database:
@AfterEach
void cleanup() {
    orderRepository.deleteAll();
}
```

Nếu test A cleanup sau assertion FAIL trong khi B đang chạy, A có thể xóa order của B. Hướng đúng là xóa **IDs test A sở hữu** trong transaction được commit và chỉ khi work của A đã quiescent, hoặc hủy schema/container riêng của A.

## 14. Chạy lại bằng Gradle để tránh kết quả giả do up-to-date

`@RepeatedTest` lặp trong một execution của Jupiter. Để tìm rò state xuyên JVM/Gradle runs, cần thực thi test task nhiều lần:

```bash
./gradlew test --tests "com.example.shop.orders.PaymentCaptureRepeatabilityTests" --rerun-tasks
./gradlew test --tests "com.example.shop.orders.PaymentCaptureRepeatabilityTests" --rerun-tasks
./gradlew test --tests "com.example.shop.orders.PaymentCaptureRepeatabilityTests" --rerun-tasks
```

Đây chỉ là lệnh minh họa; bài học **không** chạy Gradle. `--rerun-tasks` tránh trường hợp task được coi up-to-date rồi không thực hiện. Nếu dự án có task `integrationTest` riêng, phải chọn đúng task chứa test.

Cần thử hai điều kiện khác nhau:

- **Fresh infrastructure:** mỗi Gradle run có DB/broker test mới, giúp chứng minh fixture và app config khởi tạo sạch.
- **Intentionally shared test infrastructure:** nhiều runs dùng cùng test DB/broker theo ownership rõ, giúp tìm residue/registry/offset; không được trỏ tới production.

Không báo “test chạy 3 lần PASS” nếu Gradle thực tế đã skip 2 lần do cache/up-to-date.

## 15. Ma trận repeatability nên chạy trong CI

| Phép kiểm | JVM/context | DB/broker | Loại lỗi phát hiện |
| --- | --- | --- | --- |
| `@RepeatedTest(25)` tuần tự | Context có thể reuse | Giữ trong class | Mutable bean/static, fixture reuse |
| Lặp cùng class trong full suite | Context cache xuyên class | Chung | Cross-class pollution |
| Chạy Gradle lại với container mới | JVM mới | Mới | Khởi tạo/test contract deterministic |
| Chạy Gradle lại với DB test chung | JVM mới | Có chủ đích chung | Durable residue, registry, offsets |
| JUnit random order, parallel OFF | Có thể reuse | Chung | Polluter/victim order dependency |
| JUnit parallel | Context/bean có thể dùng chung | Chung | Race, cleanup interference |
| Nhiều Gradle forks/CI jobs | JVM độc lập | Có thể chung | Cross-process resource collisions |
| Failure injection rồi rerun | Tùy harness | Isolated | Teardown/recovery sau lỗi |

Một seed random order không cố định interleaving của worker async hoặc broker. Một test PASS khi lặp 25 lần trong cùng class cũng có thể FAIL khi class A chạy trước nó: đó là **order dependency khác** cần test randomize thứ tự class và tìm polluter.

### 15.1. Giới hạn số repetitions như thế nào?

Không có con số chuẩn. Với unit logic, lặp nhiều lần rẻ nhưng **boundary test và property-based invariant** vẫn có giá trị lớn hơn việc tăng con số vô hạn. Với module/broker tests, vài lượt có fixture/namespace đúng có thể hữu ích hơn hàng trăm lượt dùng resource sai. Với concurrency bug, dùng gate/latch và invariant cụ thể thay vì trông chờ “chạy 1.000 lần may ra trúng race”.

## 16. Kiểm tra đúng oracle mỗi lần

| Assertion | Khả năng lặp lại đáng tin? | Lý do |
| --- | --- | --- |
| Query theo `orderId` và `lastEventId == eventId` | Tốt | Chứng minh outcome của đúng lượt |
| `transactionId` và `amount` khớp | Tốt | Ràng buộc business event hiện tại |
| `receipt.countByTransaction(id) == 1` sau completion | Tốt cho idempotency | Xác minh không double effect |
| `PublishedEvents.ofType(...).matching(...orderId)` | Tốt cho producer | Không thay thế consumer state |
| `findAll().anyMatch(PAID)` | Yếu | Có thể đọc bản ghi của lượt trước |
| `events.size() > 0` | Yếu | Recorder singleton có event cũ |
| `orderId == 1` | Yếu | Phụ thuộc DB sequence |
| `Kafka offset == 0` | Yếu | Phụ thuộc topic/group |
| `Instant.now() == savedTimestamp` | Yếu | Clock, precision và scheduling |
| `Thread.sleep(500); assertReady()` | Yếu | Không bảo đảm commit/handler completion |

Dùng `Scenario.andWaitAtMost(...).forStateChange(...).andVerify(...)` để chờ outcome đúng event. Nhưng nếu listener còn gửi event downstream sau lúc state đạt `PAID`, teardown resource downstream cần **một completion signal khác**, không được suy từ state một cách máy móc.

## 17. Không phá ranh giới kiến trúc để setup/cleanup nhanh

Giả sử `orders` nhận event contract từ `payments.events` qua named interface:

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

Một test của `orders` không nên import `payments.internal.PaymentRepository` để reset payment data trước mỗi repetition. Dùng public API đúng ownership, fixture trong module sở hữu hoặc integration-test infrastructure được cấp quyền quản trị DB/schema trong scope test.

Kiểm chứng cấu trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifiesDeclaredDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là Spring Boot application class ví dụ. `ApplicationModules.verify()` phát hiện dependency sai, **không** tự phát hiện state leakage. Repeated test PASS cũng **không** hợp thức hóa phụ thuộc trái boundary. Cả architecture và behavior tests đều thuộc CI quality gate của `SPRING_MODULITH_VERIFICATION_TESTING`.

## 18. Nếu repetition N FAIL: thu bằng chứng gì?

| Triệu chứng | Nguồn cần nghi | Kiểm chứng ngay |
| --- | --- | --- |
| Lượt 1 PASS, lượt 2 lỗi unique key | ID/transaction key cố định | Query row hiện có và ID fixture |
| Baseline lượt 2 đã là `PAID` | Reuse aggregate hoặc fixture bẩn | Assert before status/lastEventId |
| Timeout khi lượt tăng | Async backlog, DB pool, leak listener | Queue depth, active tasks, pool waits |
| Event lượt trước xuất hiện lượt sau | Registry retry/subscription/singleton recorder | Correlation/target IDs, lifecycle |
| Chỉ FAIL khi JVM restart | DB/broker state bền, registry pending | So fresh và shared environment |
| Chỉ FAIL khi parallel | Shared fake, locks, global cleanup | So sequential/concurrent timeline |
| JPA query mãi thấy state cũ | Persistence context/snapshot | Reader transaction và fresh query |
| Kafka không nhận event mới | Consumer group/offset | Assignment/offset trước publish |
| RabbitMQ nhận event cũ | Unacked/requeue | Queue/correlation/ack |
| Test PASS sau khi thêm retry | Flaky bị che, chưa sửa root cause | Giữ seed, failure trace và trạng thái trước retry |

Quy trình điều tra:

1. Ghi **repetition index, seed, orderId, eventId, transactionId** và last observed state.
2. Chạy test riêng, tuần tự trong cùng JVM/context.
3. Xác minh baseline mỗi lượt trước stimulus.
4. Kiểm tra static/singleton state, DB committed rows, registry incomplete, broker offsets và async task completion.
5. Thay đúng một yếu tố isolation mỗi lần rồi replay.
6. Thêm regression case với oracle theo ID và bounded wait; không đổi seed hoặc tăng timeout chỉ để chuyển đỏ thành xanh.

Report nên dùng ID/metadata giả, không dump secret hoặc toàn bộ environment variables.

## 19. CI quality gate cho repeatability

Một quality gate thực dụng:

1. **Architecture:** `ApplicationModules.of(...).verify()`.
2. **Domain unit tests:** deterministic Clock/PRNG per invocation, boundary và business invariant.
3. **Repeated module tests:** `@RepeatedTest` với `@ApplicationModuleTest`, fixture mới, baseline và event-specific state.
4. **Persistence:** fixture commit, fresh reader, scoped cleanup sau handler completion.
5. **Registry/recovery:** incomplete publication và resubmission test trong storage cô lập.
6. **Broker:** Kafka/RabbitMQ topic/group/queue/ack và Testcontainers lifecycle.
7. **Order sweep:** randomize thứ tự tuần tự, ghi seed; không trộn cùng lúc với parallel.
8. **Parallel suite:** chạy riêng trên nhóm đủ isolation và giới hạn pool/forks.
9. **Cross-run:** lặp Gradle task thật sự, có cả môi trường sạch và shared-test resources có chủ đích.
10. **Failure-path:** một invocation FAIL không để dữ liệu/tác vụ phá invocation tiếp theo.
11. **Diagnostics:** iteration/seed/IDs, transaction/commit/ack timeline, cleanup outcome.
12. **Không che flaky:** test retries chỉ để thu bằng chứng, không làm root cause biến mất.

Một test báo PASS phải chứng minh **event của chính lượt đó** tạo outcome đúng. Một pipeline chỉ nhìn “lần thử cuối PASS” trong khi những lần trước fail là bằng chứng không đủ.

## 20. Checklist trước khi merge

- [ ] Mỗi invocation có precondition và fixture riêng, không dùng dữ liệu từ lần trước.
- [ ] Aggregate/event/transaction IDs đúng scope; không lấy ID chỉ từ frozen timestamp.
- [ ] Baseline `AWAITING_PAYMENT` và null event ID được assert trước publish.
- [ ] Predicate `Scenario` kiểm tra đúng event/transaction/amount đã commit.
- [ ] Test không thể PASS nếu event của lượt hiện tại không được xử lý.
- [ ] Fixture đã commit trước listener/reader khác transaction cần đọc.
- [ ] Reader không dựa vào JPA entity được cache từ trước stimulus.
- [ ] Timeout hữu hạn; không dùng sleep thay completion signal.
- [ ] Random/clock/test configuration ổn định và không dùng chung mutable singleton.
- [ ] Không dùng static counter/recorder/dedup làm oracle toàn cục.
- [ ] Cleanup handle được gọi cả khi assertion FAIL.
- [ ] Không xóa DB hoặc registry khi worker còn có thể ghi vào nó.
- [ ] Cleanup theo owner/ID/namespace, không global `TRUNCATE` trên shared resource.
- [ ] Registry incomplete publications không replay nhầm sang repetition tiếp.
- [ ] Kafka group/offset và RabbitMQ queue/ack có namespace/correlation phù hợp.
- [ ] Testcontainers và Spring context cache có lifecycle tương thích.
- [ ] Có test lặp trong cùng JVM và rerun ở JVM mới theo scope đã công bố.
- [ ] Sequential order dependency và concurrent race được thử **riêng**.
- [ ] Khi fail có repetition index, seed, IDs và cleanup outcome để reproduce.
- [ ] `ApplicationModules.verify()` vẫn kiểm tra module boundaries.

## 21. Bài tập thực hành

**Bài A — fixed ID:** tạo bài `@RepeatedTest(3)` với `orderId` cố định và fixture commit; quan sát unique-key/stale-state. Sửa bằng ID mới và cleanup scope.

**Bài B — domain seed:** chạy `PaymentDeadlineRepeatabilityTests`, ghi seed/delta của một repetition. Thử thay `SplittableRandom` local bằng static mutable RNG và giải thích phụ thuộc thứ tự.

**Bài C — singleton recorder:** tạo fake bean chứa `List<Event>`. Lặp 10 lần và assert global count; chỉ ra kết luận sai. Sửa bằng event ID-scoped observations và lifecycle rõ.

**Bài D — module behavior:** triển khai `PaymentCaptureRepeatabilityTests` ở mục 6, thực hiện 25 repetitions với cùng Spring context. Kiểm tra baseline và exact event-specific outcome từng lượt.

**Bài E — false positive:** đổi oracle thành `findAnyPaidOrder().isPresent()`, seed một order `PAID` từ lượt trước. Chứng minh test PASS sai; sửa qua public query theo ID.

**Bài F — transaction/JPA:** dùng fixture đã flush nhưng chưa commit, listener async cần đọc order. Quan sát timeout rồi sửa transaction boundary; kiểm tra reader fresh state.

**Bài G — failure tail:** ở một repetition có chủ đích, khiến listener fail hoặc chậm. Kiểm tra teardown không xóa DB trước khi worker quiescent; lần sau phải không bị event cũ ảnh hưởng.

**Bài H — Event Publication Registry:** để incomplete publication trong registry test riêng, thử resubmission qua restart. Chờ đúng event/target completion rồi hủy environment.

**Bài I — Kafka/RabbitMQ:** chạy integration test hai lần trên broker test dùng chung. Quan sát offset/requeue; sửa bằng group/queue namespace và correlation ID.

**Bài J — Gradle rerun:** chạy cùng test task ba lần với `--rerun-tasks`; so sánh fresh container và shared DB/broker test. Không kết luận PASS nếu task không thực thi.

**Bài K — order/parallel:** chạy repeated tests trong suite random order, sau đó chạy parallel có kiểm soát. Phân biệt polluter/victim với race giữa hai worker.

**Bài L — architecture:** thử tạo import `payments.internal.*` từ `orders` trong nhánh học tập, kiểm tra `ApplicationModules.verify()` phát hiện rồi hoàn nguyên.

**Tiêu chí đạt:** kết luận của cùng test ổn định qua nhiều lượt, một lượt thất bại không làm nhiễm lượt khác, các side effects có owner, và CI có bằng chứng tách biệt cho repeatability, order dependency, race và ranh giới kiến trúc.

## 22. Ghi nhớ và tài liệu tham khảo

**Test có thể chạy lại nhiều lần phải lặp chính phép kiểm, không lặp lại dữ liệu của lượt trước.** Mỗi lượt cần fixture mới, identity riêng, stimulus chính xác, state sau commit và teardown an toàn. `@RepeatedTest` giúp phát hiện state leakage trong cùng JVM; chạy lại Gradle và Testcontainers/DB/broker theo nhiều scope làm lộ state bền; idempotency của cùng logical event là một test riêng.

Trong học phần `SPRING_MODULITH_VERIFICATION_TESTING`, kết hợp `@ApplicationModuleTest`, `Scenario` và `ApplicationModules.verify()` để CI bảo vệ đồng thời hành vi, isolation và dependency boundaries.

Tài liệu tham khảo:

- [JUnit 5 — Repeated Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-repeated-tests): `@RepeatedTest`, `RepetitionInfo` và lifecycle.
- [JUnit 5 — Test Instance Lifecycle](https://junit.org/junit5/docs/current/user-guide/#writing-tests-test-instance-lifecycle): `PER_METHOD`, `PER_CLASS`.
- [JUnit 5 — Parallel Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution): concurrent tests và isolation.
- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario` và `PublishedEvents`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): listener, Event Publication Registry và retry.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và module boundaries.
- [Spring Framework — TestContext Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context reuse.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): transaction boundaries trong test.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): rerun tasks và test filtering.
- [Testcontainers for Java](https://java.testcontainers.org/): lifecycle database/broker test.
- [Java SE — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): business time trong tests.
- [Java SE — SplittableRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SplittableRandom.html): PRNG với seed.
