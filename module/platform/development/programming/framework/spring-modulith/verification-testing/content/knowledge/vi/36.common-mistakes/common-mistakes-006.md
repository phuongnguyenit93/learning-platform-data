# Không kiểm tra event sau transaction commit

> **Phạm vi:** Bài thuộc `SPRING_MODULITH_VERIFICATION_TESTING`, tập trung vào kiểm chứng ranh giới kiến trúc và hành vi tích hợp của Spring Modulith. Lỗi cần khắc phục ở đây là **test chỉ nhìn thấy event được phát trong transaction nhưng không xác nhận listener đã thực thi thành công sau khi transaction commit**. Các ví dụ dùng Java 17+, JUnit Jupiter, Spring Boot, Spring Modulith và cơ sở dữ liệu giao dịch.

Trong hệ thống đặt hàng, module `orders` phát `OrderPaid` khi thanh toán thành công. Module `receipts` nhận event bằng `@ApplicationModuleListener` và ghi biên lai. Test chỉ xác nhận `OrderPaid` đã được publish vẫn có thể xanh khi listener không được gọi, ghi DB thất bại, hoặc ứng dụng dừng trước khi xử lý xong. Cần phân biệt ba mốc:

```text
Transaction của orders: BEGIN -> UPDATE order -> publish OrderPaid -> COMMIT
                                                         |
                                  nếu COMMIT thành công: AFTER_COMMIT
                                                         |
                                  listener của receipts (bất đồng bộ)
                                                         |
                                  transaction mới -> INSERT receipt -> COMMIT
```

**Hợp đồng cần kiểm chứng:** trước commit không được có tác dụng phụ cần chờ commit; sau commit thành công, tác dụng phụ cuối cùng phải quan sát được bằng một truy vấn độc lập; sau rollback thì không được xử lý; khi listener lỗi phải có cơ chế quan sát và khôi phục rõ ràng. `ApplicationModules.verify()` phát hiện vi phạm phụ thuộc tĩnh giữa module, nhưng **không chứng minh** hợp đồng runtime này.

## 1. Chỉ assert `PublishedEvents` rồi kết luận listener đã chạy

**Triệu chứng:** test kiểm tra đúng một `OrderPaid` và được báo thành công, nhưng bảng `receipts` vẫn trống. `PublishedEvents` và `AssertablePublishedEvents` ghi nhận sự kiện được publish trong lúc test chạy; chúng không thay thế assertion về kết quả **sau commit** của consumer.

Ví dụ dưới đây là phép kiểm chứng hữu ích cho *producer*, nhưng chưa đủ cho luồng tích hợp:

```java
// Đặt trong test của module orders; checkout và dữ liệu đầu vào là fixture ứng dụng.
@Test
void emitsOrderPaid(PublishedEvents events) {
    UUID orderId = givenUnpaidOrder();
    checkout.pay(orderId);

    assertThat(events.ofType(OrderPaid.class)
            .matching(OrderPaid::orderId, orderId))
            .hasSize(1);
}
```

Nếu đổi `@ApplicationModuleListener` thành listener không được scan, hoặc listener luôn ném exception sau commit, assertion trên vẫn có thể đúng. Tách hai mục tiêu: test producer khẳng định *event có loại, khóa tương quan và payload đúng*; test consumer khẳng định *kết quả cuối cùng đã được commit*. Đừng dùng `verify(mockListener).on(...)` làm bằng chứng duy nhất vì lời gọi mock không khẳng định transaction ghi dữ liệu đã thành công.

## 2. Dùng `@Transactional` cho test rồi để Spring Test tự rollback

Spring Test thường rollback transaction của test có `@Transactional` ở cuối phương thức. Khi đó `@TransactionalEventListener` với pha mặc định `AFTER_COMMIT` không được gọi. `repository.flush()` hoặc `saveAndFlush()` chỉ đẩy SQL xuống DB trong transaction hiện tại, **không phải commit**.

Kiểm tra có chủ đích bằng `TestTransaction` nếu muốn giữ cấu trúc test có `@Transactional`:

```java
@Test
@Transactional
void doesNotHandleEventUntilActualCommit() {
    UUID orderId = UUID.randomUUID();
    events.publishEvent(new OrderPaid(orderId, new BigDecimal("120.00")));

    assertThat(receipts.findById(orderId)).isEmpty();

    TestTransaction.flagForCommit();
    TestTransaction.end(); // kích hoạt commit và callback AFTER_COMMIT

    await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
        assertThat(receipts.findById(orderId)).isPresent());
}
```

Ở ví dụ này, `events` là `ApplicationEventPublisher` và `receipts` là repository thật của module nhận event. Import `TestTransaction` từ `org.springframework.test.context.transaction`; `await()` từ Awaitility. Dọn dữ liệu bằng fixture riêng sau test, vì đã commit thì dữ liệu **không còn** được rollback tự động. Không nên gắn `@Transactional` lên cả lớp test và mặc định mọi event sẽ có `AFTER_COMMIT`.

## 3. Không kiểm tra đúng loại listener, đúng pha và transaction đang hoạt động

`@EventListener` xử lý đồng bộ theo mặc định tại thời điểm publish, nên có thể chạy **trước** commit. `@TransactionalEventListener` mặc định chạy ở `TransactionPhase.AFTER_COMMIT`. Nếu không có transaction đang hoạt động, transactional listener mặc định **bỏ qua event** (trừ khi bật `fallbackExecution = true`). `@ApplicationModuleListener` của Modulith là lối viết gọn cho listener bất đồng bộ, sau commit, trong transaction `REQUIRES_NEW`.

```java
// Phù hợp với consumer cần tồn tại độc lập với transaction của orders.
@Component
class ReceiptListener {

    private final ReceiptRepository receipts;

    ReceiptListener(ReceiptRepository receipts) {
        this.receipts = receipts;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        receipts.save(new Receipt(event.orderId(), event.paidAmount()));
    }
}
```

**Kiểm chứng:** phát event trong một transaction chưa kết thúc và khẳng định chưa có biên lai, sau đó commit và chờ biên lai xuất hiện (mục 2). Thêm test phát event **ngoài transaction** để chứng minh chính sách mặc định là không xử lý; nếu nghiệp vụ cho phép phát ngoài transaction, phải thiết kế và test `fallbackExecution` hoặc ranh giới transaction tường minh. Đừng bật `fallbackExecution` chỉ để làm test xanh vì nó thay đổi ngữ nghĩa sản xuất.

## 4. Test producer nhưng không khởi động đúng module chứa consumer

`@ApplicationModuleTest` mặc định bootstrap module chứa lớp test (`STANDALONE`). Test đặt dưới `example.orders` có thể kiểm tra publish `OrderPaid` nhưng hoàn toàn không khởi tạo bean `ReceiptListener` ở `example.receipts`. Tăng bootstrap mode một cách mù quáng cũng dễ che dấu coupling giữa module.

Với consumer, đặt test trong chính package của module `receipts` và publish event thuộc public API của module `orders`. Hãy giữ event ở một API hoặc named interface hợp lệ để vượt qua kiểm chứng phụ thuộc kiến trúc.

```java
// File example/orders/OrderPaid.java — event là hợp đồng công khai.
package example.orders;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderPaid(UUID orderId, BigDecimal paidAmount) {}
```

```java
// File example/receipts/Receipt.java (rút gọn để thấy side effect cần assert).
package example.receipts;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

@Entity
class Receipt {
    @Id
    private UUID orderId;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal paidAmount;

    protected Receipt() {}

    Receipt(UUID orderId, BigDecimal paidAmount) {
        this.orderId = orderId;
        this.paidAmount = paidAmount;
    }

    UUID getOrderId() { return orderId; }
    BigDecimal getPaidAmount() { return paidAmount; }
}

interface ReceiptRepository extends JpaRepository<Receipt, UUID> {}
```

Trong dự án thật, có thể dùng `@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)` khi bean của module đang test thực sự cần direct dependencies; nhưng đó không phải điều kiện bắt buộc để consumer nhận một event type từ module khác. Kiểm tra log bootstrap hoặc bean hiện diện trong context trước khi quy một test xanh cho luồng liên module.

## 5. Assert ngay sau `publishEvent()` dù listener chạy bất đồng bộ

`@ApplicationModuleListener` mang `@Async`; để xử lý thực sự bất đồng bộ, context cần bật async execution (ví dụ `@EnableAsync`). Nếu không, handler có thể chạy đồng bộ trong callback sau commit, làm test bỏ qua tình huống concurrency của production. Khi async đã bật, thứ tự chạy của test thread và thread listener không được đảm bảo. `assertThat(receipts.findById(id)).isPresent()` ngay sau publish có thể thất bại ngẫu nhiên trên CI hoặc xanh do chạy nhanh trên máy cá nhân. `Thread.sleep(1000)` vừa làm suite chậm vừa không tạo ràng buộc đúng về trạng thái.

Sử dụng `Scenario` của `spring-modulith-starter-test` để kích hoạt **transaction thực sự commit** rồi chờ trạng thái quan sát được. Đây là test consumer hoàn chỉnh cho ví dụ đã nêu (đặt trong package `example.receipts`):

```java
package example.receipts;

import static org.assertj.core.api.Assertions.assertThat;
import example.orders.OrderPaid;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class ReceiptAfterCommitTests {

    @Autowired ReceiptRepository receipts;

    @Test
    void createsDurableReceiptAfterCommit(Scenario scenario) {
        UUID orderId = UUID.randomUUID();
        BigDecimal amount = new BigDecimal("120.00");

        scenario.publish(new OrderPaid(orderId, amount))
            .andCleanup(() -> receipts.deleteById(orderId))
            .andWaitAtMost(Duration.ofSeconds(5))
            .andWaitForStateChange(() -> receipts.findById(orderId).orElse(null))
            .andVerify(receipt -> {
                assertThat(receipt.getOrderId()).isEqualTo(orderId);
                assertThat(receipt.getPaidAmount())
                    .isEqualByComparingTo(amount);
            });
    }
}
```

`Scenario.publish(...)` tạo một transaction mới cho stimulus và commit để giao event tới transactional listener, kể cả khi method test đang nằm trong transaction khác. `andWaitForStateChange` chờ một kết quả khác `null`; trong ví dụ này là entity được đọc từ DB **sau** transaction consumer. `andCleanup` dọn bản ghi đã commit; nếu có Event Publication Registry, cần có cơ chế reset dữ liệu registry trong test database. Không dùng kết quả của `Scenario` để suy rằng dữ liệu đã được tự rollback.

## 6. Chỉ chờ một event thứ cấp mà không kiểm tra dữ liệu được commit

Giả sử listener phát tiếp `ReceiptGenerated` ngay sau `receipts.save(...)`. Test dùng:

```java
scenario.publish(new OrderPaid(orderId, amount))
    .andWaitForEventOfType(ReceiptGenerated.class)
    .matching(event -> event.orderId().equals(orderId))
    .toArrive();
```

Đây là kiểm tra **có event thứ cấp**, không chắc đó là xác nhận commit thành công của transaction ghi receipt: event có thể được publish khi transaction xử lý listener còn đang mở. Khi hợp đồng là "receipt tồn tại bền vững", hãy chờ `ReceiptRepository.findById(...)` như mục 5, đồng thời kiểm tra payload `amount` và khóa `orderId`. Nếu cần cả hai tín hiệu, kiểm tra event thứ cấp ở một test riêng; test lưu trữ phải đi qua truy vấn ở transaction/persistence context độc lập. Với JPA, tránh assert bằng entity vẫn nằm trong first-level cache của transaction phát event.

## 7. Ghi database trong callback `AFTER_COMMIT` mà không mở transaction mới

Ở callback sau commit, transaction của publisher đã kết thúc, nhưng tài nguyên JDBC/JPA vẫn có thể tạm thời gắn với thread. Một lệnh `save(...)` tưởng như thành công có thể không được commit sau đó. Đây là lỗi rất dễ lọt qua unit test mock repository hoặc test chỉ `verify(repository).save(...)`.

```java
// Dễ sai khi handler cần ghi DB:
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPaid event) {
    receipts.save(new Receipt(event.orderId(), event.paidAmount()));
}

// Cách tường minh nếu không dùng @ApplicationModuleListener:
@Async
@Transactional(propagation = Propagation.REQUIRES_NEW)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void onSafely(OrderPaid event) {
    receipts.save(new Receipt(event.orderId(), event.paidAmount()));
}
```

Hai method trên là **hai phương án minh họa loại trừ nhau**, không đăng ký cả hai trong cùng hệ thống vì sẽ xử lý trùng event. Kiểm chứng đúng bằng test DB thật: sau khi producer commit, đọc biên lai bằng repository/connection mới; sau đó khởi tạo một transaction đọc mới và xác nhận dữ liệu còn tồn tại. `@ApplicationModuleListener` (mục 3) đóng gói sẵn `@Async` + `REQUIRES_NEW` + `@TransactionalEventListener` cho trường hợp phổ biến.

## 8. Không có test rollback để chặn side effect phát sinh trước commit

Luồng sau commit phải đáp ứng điều kiện phủ định: nếu transaction gốc rollback, listener không được tạo receipt. Test chỉ có đường thành công không phát hiện việc ai đó vô tình thay `@TransactionalEventListener` bằng `@EventListener`, làm gửi email/ghi bản ghi sớm rồi transaction gốc thất bại.

```java
@Test
@Transactional
void rollbackMustNotCreateReceipt() {
    UUID orderId = UUID.randomUUID();
    events.publishEvent(new OrderPaid(orderId, new BigDecimal("120.00")));

    TestTransaction.flagForRollback();
    TestTransaction.end();

    await().during(Duration.ofMillis(400))
        .atMost(Duration.ofSeconds(2))
        .untilAsserted(() ->
            assertThat(receipts.findById(orderId)).isEmpty());
}
```

Test trên cần bean thật, transaction manager và môi trường DB giống các test trong mục 2. `during(...)` yêu cầu trạng thái "không có receipt" giữ nguyên trong một khoảng quan sát; tăng ngưỡng theo thời gian xử lý thực tế để tránh kết luận âm tính quá sớm. Nếu side effect là HTTP/email, dùng fake adapter hoặc recorder đo lượt gọi, nhưng giữ transactional listener thật. `Scenario.publish(...)` **không dùng cho test rollback** vì chính nó tạo transaction và commit stimulus.

## 9. Listener ném exception sau commit nhưng không kiểm tra publication còn thiếu

Khi commit của `orders` đã xong, lỗi `receipts` không thể rollback ngược thanh toán. Nếu chỉ assert trạng thái đơn hàng, suite vẫn xanh dù receipt không được tạo. Với `spring-modulith-starter-jpa` hoặc `spring-modulith-starter-jdbc`, Event Publication Registry lưu publication cho từng transactional listener trong transaction ban đầu và đánh dấu hoàn tất khi listener xử lý thành công. Bản ghi lỗi/chưa hoàn tất giúp phát hiện sự kiện cần retry; starter test **không** tự thay thế starter lưu registry.

Một kịch bản tích hợp nên dùng gateway giả có thể điều khiển kết quả: lần đầu cố ý ném exception, lần sau trả thành công. Sau khi phát `OrderPaid` và commit, xác minh publication chưa hoàn tất **đúng event/đúng listener**, và không có receipt; sau khi retry, chờ receipt xuất hiện và kiểm tra publication đã hoàn tất. Phần quan sát ban đầu có thể viết:

```java
// Trong test tích hợp có event publication starter và bean registry thật:
@Autowired EventPublicationRegistry publications;

void assertStillIncomplete(UUID orderId) {
    await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
        assertThat(publications.findIncompletePublications())
            .anyMatch(publication ->
                publication.getEvent() instanceof OrderPaid event
                    && event.orderId().equals(orderId)));
}
```

`EventPublicationRegistry` ở `org.springframework.modulith.events.core`; `findIncompletePublications()` cần được lọc theo event ID vì những test khác có thể tạo publication. Từ Spring Modulith 2.0 có `FailedEventPublications.resubmit(ResubmissionOptions.defaults())` và trạng thái `PUBLISHED`, `PROCESSING`, `FAILED`, `COMPLETED`, `RESUBMITTED`. Không khẳng định mọi publication chưa hoàn tất đều là `FAILED` ngay lập tức: listener có thể đang chạy. Cấu hình tự republish khi khởi động là **tùy chọn**, không mặc định; khi kiểm chứng phải xác định rõ cơ chế retry thật của ứng dụng.

## 10. Không kiểm chứng redelivery và consumer có xử lý lặp an toàn

Giữa lúc ghi tác dụng phụ và đánh dấu publication thành công, tiến trình có thể chết. Khi retry, cùng một event có thể được giao lại. Hệ thống không nên giả định exactly-once chỉ vì event được phát một lần từ producer. Ví dụ tạo receipt, ghi nhận theo khóa nghiệp vụ cố định `orderId` và đặt ràng buộc duy nhất ở DB; nếu gửi yêu cầu ra dịch vụ ngoài, dùng idempotency key hoặc bảng outbox/inbox tương ứng.

Thiết kế test gồm hai lượt xử lý cùng `OrderPaid(orderId, amount)`: lượt đầu tạo receipt; lượt tiếp theo mô phỏng replay thông qua cơ chế resubmit hoặc publication lần hai, **chờ listener hoàn thành** rồi assert:

```java
// Assertion sau khi cả hai lượt giao event đã kết thúc:
assertThat(receipts.findById(orderId)).isPresent();
assertThat(receipts.countByOrderId(orderId)).isEqualTo(1);
assertThat(externalGateway.callsFor(orderId)).isEqualTo(1);
```

`countByOrderId` và `callsFor` là API fixture/adapter cần tạo trong ứng dụng đang kiểm tra; đoạn trên mô tả assertion, không phải API có sẵn của Spring Modulith. Kiểm tra thêm trường hợp một listener thành công còn listener khác lỗi: registry theo dõi **publication của từng listener**, không cho phép kết luận "event xử lý xong" chỉ vì một consumer đã ghi được dữ liệu. Đối với HTTP/email, kết quả bền vững phải được đo ở ranh giới adapter, không dùng số lần gọi method nội bộ làm chỉ báo duy nhất.

## 11. Bỏ qua kiểm thử commit khi chạy quality gate trong CI

Test chỉ chạy trên mock/in-memory không hỗ trợ transaction thật có thể bỏ sót lifecycle `AFTER_COMMIT`, transaction riêng của consumer hoặc lỗi serialization trong event registry. Hãy có một nhóm integration test dùng transaction manager và database thực tế phù hợp (ví dụ Testcontainers cho DB production), với dữ liệu độc lập cho mỗi lần chạy. Các trường hợp tối thiểu:

| Tình huống | Bằng chứng bắt buộc |
| --- | --- |
| Producer commit | Một `OrderPaid` có đúng ID, amount; receipt xuất hiện **sau commit** |
| Producer rollback | Không có receipt và không có external side effect |
| Phát ngoài transaction | Listener không chạy theo cấu hình mặc định, hoặc hành vi fallback được nêu rõ |
| Listener chạy chậm | Test chờ có deadline, không dùng `sleep` |
| Listener lỗi | Receipt chưa có; publication chưa hoàn tất/FAILED theo lifecycle đang dùng |
| Retry/redelivery | Side effect xuất hiện cuối cùng một lần theo khóa idempotency |
| Hai consumer | Kết quả và publication của **từng** consumer được kiểm tra độc lập |

Chặn merge nếu nhóm test sau commit thất bại. Với dự án Maven dùng JUnit Jupiter và Surefire đã cấu hình, có thể chạy riêng bài test ví dụ bằng:

```bash
mvn -B -Dtest=ReceiptAfterCommitTests test
```

Trong pipeline đầy đủ, chạy cả test kiến trúc `ApplicationModules.verify()` và suite tích hợp giao dịch. Test kiến trúc phát hiện dependency sai; test sau commit phát hiện sai lệch runtime. Hai lớp kiểm chứng bổ sung nhau nhưng không thay thế nhau.

### Checklist đọc kết quả test

- **Chứng cứ commit:** có mốc commit của transaction producer; `flush` không được coi là commit.
- **Chứng cứ listener:** listener thật trong application context của đúng module; phase `AFTER_COMMIT` và transaction của consumer được xác nhận.
- **Chứng cứ side effect:** truy vấn mới thấy dữ liệu đã commit hoặc adapter đích xác nhận; không chỉ nhìn vào `PublishedEvents`.
- **Chứng cứ phủ định:** rollback và không có transaction đều có kỳ vọng tường minh.
- **Chứng cứ phục hồi:** lỗi có thể quan sát được, retry có giới hạn và consumer idempotent.

### Tài liệu đối chiếu

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario`, commit stimulus, `andWaitForStateChange` và cleanup.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `@ApplicationModuleListener`, `PublishedEvents`, Event Publication Registry và retry.
- [Spring Framework — TransactionalEventListener](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): thời điểm xử lý, transaction bị rollback và `fallbackExecution`.

> **Giới hạn của ví dụ:** các đoạn `ReceiptAfterCommitTests` và entity là cấu trúc mẫu để ghép vào ứng dụng có JPA, Spring Modulith và transaction manager. Các snippet có tên fixture như `givenUnpaidOrder()`, `countByOrderId()` hoặc `externalGateway` cần hiện thực theo domain thật; chúng minh họa tiêu chí assertion. Chưa chạy build của một ứng dụng cụ thể ở bước soạn học liệu này.
