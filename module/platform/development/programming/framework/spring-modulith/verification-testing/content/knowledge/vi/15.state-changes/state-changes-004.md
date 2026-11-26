# Tránh kiểm tra state ngay sau khi kích hoạt bất đồng bộ trong Spring Modulith

## 1. Vấn đề: sự kiện đã phát, trạng thái chưa chắc đã đổi

Trong ứng dụng Spring Modulith, một hành động ở module này có thể kích hoạt công việc tại module khác thông qua **application event**. Ví dụ: module `payments` thông báo thanh toán thành công; module `orders` lắng nghe sự kiện và chuyển đơn hàng từ `AWAITING_PAYMENT` sang `PAID`. Khi listener chạy bất đồng bộ hoặc sau khi transaction commit, lệnh phát sự kiện có thể kết thúc **trước** lúc dữ liệu mới được lưu.

Nếu test kiểm tra trạng thái ngay sau lệnh kích hoạt, kết quả phụ thuộc vào việc thread của listener chạy nhanh hay chậm. Test có thể pass ở máy lập trình viên nhưng fail khi máy CI bận, database chậm, hay quá trình scheduling thay đổi.

Đây là chủ đề *State change* của `SPRING_MODULITH_VERIFICATION_TESTING`: kiểm chứng hành vi module qua `@ApplicationModuleTest`, sự kiện, database và tích hợp; kết hợp `ApplicationModules` và quy tắc phụ thuộc để bảo vệ kiến trúc bằng quality gate trong CI.

Sau bài học, bạn có thể:

- Nhận diện **race condition** khi assertion chạy trước công việc bất đồng bộ.
- Phân biệt sự kiện được publish, listener được gọi, transaction được commit và trạng thái có thể truy vấn.
- Sử dụng `Scenario.andWaitForStateChange(...)` để đợi đúng kết quả nghiệp vụ.
- Thiết kế nguồn đọc, `Predicate`, timeout và dữ liệu test nhằm giảm flaky test.
- Chẩn đoán lỗi khi đã chờ nhưng vẫn không thấy trạng thái mong đợi.
- Đưa kiểm thử trạng thái vào CI cùng phép kiểm chứng ranh giới module.

## 2. Vì sao assertion ngay sau stimulus gây flaky test?

Đoạn code sau trông hợp lý nhưng chứa một giả định sai nếu việc xử lý event là bất đồng bộ:

```java
@Test
void paymentMarksOrderAsPaidImmediately() {
    UUID orderId = fixture.createAwaitingPaymentAndCommit();

    eventPublisher.publishEvent(new PaymentCaptured(orderId, "TX-001"));

    // Rủi ro: thread listener có thể chưa cập nhật/commit.
    assertThat(orderQueries.statusOf(orderId)).contains(OrderStatus.PAID);
}
```

Các lớp `PaymentCaptured`, `OrderQueries`, `OrderStatus`, `fixture` là thành phần nghiệp vụ minh họa, không phải class Spring Modulith tạo sẵn.

Thứ tự công việc có thể xảy ra:

```mermaid
sequenceDiagram
    participant Test
    participant Bus as ApplicationEventPublisher
    participant Worker as Async event listener
    participant DB as Database
    Test->>Bus: publishEvent(PaymentCaptured)
    Bus-->>Test: lệnh publish trả về
    Bus-->>Worker: giao công việc để xử lý
    Test->>DB: SELECT status
    DB-->>Test: AWAITING_PAYMENT
    Note over Test: Assertion PAID thất bại
    Worker->>DB: UPDATE status = PAID; COMMIT
```

Hình trên là **một thứ tự thực thi có thể xảy ra**, không phải thứ tự được hệ thống bảo đảm. Trên máy nhanh, listener cũng có thể commit trước lượt `SELECT`; khi đó chính bài test này lại pass. Vì kết quả phụ thuộc lịch chạy thread, bài test không ổn định.

**Phân biệt bốn mốc:**

| Mốc quan sát | Điều chứng minh được | Điều chưa chứng minh được |
| --- | --- | --- |
| `publishEvent(...)` đã trả về | Lệnh publish đã hoàn tất theo cơ chế dispatch hiện tại. | Listener bất đồng bộ đã kết thúc hay chưa. |
| Listener đã được gọi | Handler bắt đầu chạy. | Transaction ghi dữ liệu đã commit. |
| Handler ghi `save(...)` | Thao tác ghi đã được yêu cầu trong transaction. | Consumer đã thấy dữ liệu đã commit. |
| API đọc trả `PAID` | Trạng thái mong đợi có thể quan sát qua đúng đường đọc. | Các bất biến khác đã đúng, nếu test chưa kiểm tra chúng. |

Với listener đồng bộ, không chạy sau commit và hoàn tất việc cập nhật trước khi publish trả về, assertion tức thì **có thể** phù hợp. Bài này tập trung vào các luồng không có bảo đảm đó: `@Async`, `@TransactionalEventListener`, xử lý nền, read model cập nhật chậm và các hoạt động xuyên module.

## 3. Tránh sửa bằng `Thread.sleep(...)`

Một cách sửa thường thấy là chờ một khoảng thời gian cố định:

```java
eventPublisher.publishEvent(new PaymentCaptured(orderId, "TX-002"));
Thread.sleep(1000);
assertThat(orderQueries.statusOf(orderId)).contains(OrderStatus.PAID);
```

Cách này vẫn không tạo ra bảo đảm:

- Nếu listener mất 50 ms, test vẫn mất thêm 1 giây.
- Nếu listener mất 1,2 giây trên CI, test vẫn fail.
- Nếu listener lỗi hoặc transaction rollback, ngủ lâu hơn cũng không làm trạng thái đạt yêu cầu.
- Một thời gian ngủ cố định không mô tả **điều kiện hoàn tất** của nghiệp vụ.

Giải pháp đúng là **poll theo điều kiện**: định kỳ đọc trạng thái thực tế, kết thúc ngay khi đạt kỳ vọng, và thất bại khi quá thời hạn. Spring Modulith cung cấp `Scenario` để diễn đạt mô hình này trong kiểm thử module.

## 4. Sử dụng `Scenario.andWaitForStateChange(...)`

Một scenario thường gồm ba bước:

```java
scenario.publish(new PaymentCaptured(orderId, "TX-003"))
        .andWaitForStateChange(
                () -> orderQueries.statusOf(orderId),
                state -> state.filter(s -> s == OrderStatus.PAID).isPresent())
        .andVerify(state -> assertThat(state).contains(OrderStatus.PAID));
```

**Ý nghĩa các bước:**

1. `publish(...)` kích hoạt event làm đầu vào của bài test.
2. `Supplier` trong `andWaitForStateChange(...)` **đọc lại** state theo ID của kịch bản. `Predicate` trả `true` **chỉ khi** trạng thái thực sự là `PAID`; nếu chưa, scenario tiếp tục đợi trong giới hạn.
3. `andVerify(...)` thực hiện assertion trên kết quả đã thỏa điều kiện. Nếu hết timeout trước khi predicate đúng, test thất bại.

Sự khác biệt nằm ở câu hỏi được test đặt ra: thay vì “ngay sau khi gọi thì có phải `PAID` không?”, test hỏi “**trong thời gian được cho phép, trạng thái có tiến đến `PAID` không?**”.

### 4.1. Ví dụ `@ApplicationModuleTest` tự chứa

Giả định module `orders` công bố một API đọc trạng thái, có fixture tạo dữ liệu đã commit, và có listener xử lý `PaymentCaptured` được đưa vào Spring test context. Ví dụ dưới đây sử dụng `Scenario` do Spring Modulith cung cấp làm tham số phương thức test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class PaymentStateChangeTests {

    @Autowired OrderQueries orderQueries;
    @Autowired OrderFixture fixture;

    @Test
    void capturedPaymentEventuallyChangesOrderState(Scenario scenario) {
        UUID orderId = fixture.createAwaitingPaymentAndCommit();

        // Điều kiện đầu vào phải được kiểm chứng trước khi phát event.
        assertThat(orderQueries.statusOf(orderId))
                .contains(OrderStatus.AWAITING_PAYMENT);

        scenario.publish(new PaymentCaptured(orderId, "TX-004"))
                .andWaitForStateChange(
                        () -> orderQueries.statusOf(orderId),
                        state -> state.filter(s -> s == OrderStatus.PAID)
                                      .isPresent())
                .andVerify(state ->
                        assertThat(state).contains(OrderStatus.PAID));
    }
}
```

Giả định các thành phần ứng dụng cung cấp hợp đồng sau (các khai báo `public` đặt trong những file Java riêng khi áp dụng thực tế):

```java
public enum OrderStatus {
    AWAITING_PAYMENT, PAID, PAYMENT_FAILED
}

public record PaymentCaptured(UUID orderId, String transactionId) {}

public interface OrderQueries {
    Optional<OrderStatus> statusOf(UUID orderId);
}

public interface OrderFixture {
    UUID createAwaitingPaymentAndCommit();
}
```

`OrderFixture` không phải API của Spring Modulith: dự án tự triển khai để tạo bản ghi đơn hàng ở `AWAITING_PAYMENT` và **commit** trước khi test bắt đầu scenario. Không sử dụng một bản ghi còn nằm trong transaction của test rồi kỳ vọng một listener `AFTER_COMMIT` đã chạy.

Ví dụ này là kịch bản minh họa, cần thay bằng các kiểu nghiệp vụ và bean của dự án; nó chỉ chạy khi event handler và hạ tầng database liên quan hiện diện trong test context. Nếu listener thuộc module khác, cần cấu hình phạm vi `@ApplicationModuleTest` phù hợp hoặc dùng kiểm thử tích hợp với phạm vi rộng hơn.

### 4.2. Tại sao cần predicate chỉ rõ `PAID`?

`statusOf(...)` trả về `Optional<OrderStatus>`. Ngay ở trạng thái bắt đầu, `Optional.of(AWAITING_PAYMENT)` đã là một giá trị **có mặt**. Nếu chỉ chờ `isPresent()` hoặc dựa vào điều kiện mặc định của overload một tham số, scenario có thể dừng trước khi trạng thái đổi.

```java
// Không đủ: bản ghi đã tồn tại từ trước.
state -> state.isPresent()

// Đúng mục tiêu: trạng thái đã thực sự đổi thành PAID.
state -> state.filter(s -> s == OrderStatus.PAID).isPresent()
```

`andVerify(...)` không biến điều kiện `isPresent()` thành phép chờ `PAID`: khi predicate đã trả `true`, callback assertion sẽ chạy ngay, và có thể thấy giá trị cũ. Vì thế, **điều kiện chờ phải mang ý nghĩa nghiệp vụ**, không chỉ kiểm tra sự tồn tại kỹ thuật.

## 5. Hiểu đúng ba kiểu xử lý event

### 5.1. Listener đồng bộ

`@EventListener` thông thường chạy đồng bộ theo cơ chế phát event mặc định của Spring. Khi handler cập nhật trạng thái và hoàn tất trước lúc `publishEvent` trả về, assertion tức thì có thể đúng. Tuy nhiên, sự bảo đảm này sẽ biến mất nếu sau này listener chuyển sang executor bất đồng bộ hoặc công việc thực tế được giao cho queue.

### 5.2. Listener bất đồng bộ với `@Async`

`@Async` cho phép listener thực thi trên thread khác nếu cơ chế async đã được bật và bean được Spring quản lý. Lệnh publish có thể trả về trước khi listener làm xong. Trong test tích hợp, nên quan sát state cuối thay vì giả định thread khác chạy ngay.

```java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;

@Async
@EventListener
public void on(PaymentCaptured event) {
    orderApplicationService.markPaid(event.orderId(), event.transactionId());
}
```

Đây là phần thân phương thức listener minh họa nằm trong một Spring bean. Service `markPaid(...)` phải có transaction/commit phù hợp; `@Async` cần cấu hình hỗ trợ async, ví dụ `@EnableAsync` trong ứng dụng. Trên thread khác, context transaction của caller không tự động truyền theo.

### 5.3. Listener chạy sau commit

Với `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, listener chỉ được kích hoạt theo pha commit của transaction chứa sự kiện. Nó có thể kết hợp với `@Async`, làm khoảng thời gian từ khi bắt đầu hành vi đến lúc trạng thái mới quan sát được càng rõ ràng.

```java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// Phương thức nằm trong bean do Spring quản lý.
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(PaymentCaptured event) {
    // Service bean riêng có @Transactional để cập nhật và commit dữ liệu.
    orderApplicationService.markPaid(event.orderId(), event.transactionId());
}
```

Điểm cần nhớ: `AFTER_COMMIT` yêu cầu sự kiện được phát trong transaction thực sự commit; khi không có transaction, listener mặc định không chạy, trừ khi ứng dụng cấu hình `fallbackExecution`. Thao tác ghi của listener nên có transaction riêng, rõ ràng (ví dụ một service `@Transactional` được gọi qua proxy Spring), thay vì dựa vào transaction đã kết thúc của publisher.

Trong một kịch bản `Scenario.publish(...)`, hãy kiểm tra chính xác transaction và cấu hình listener mà phiên bản Spring Modulith/dự án sử dụng; không áp dụng suy luận “publish đã trả về thì after-commit listener đã commit” cho mọi trường hợp.

| Kiểu xử lý | Có thể dùng assertion tức thì? | Chiến lược kiểm thử state |
| --- | --- | --- |
| Đồng bộ, lưu state xong trước khi trả về | Có, nếu đó là hợp đồng được bảo đảm. | Assertion trực tiếp hoặc `Scenario` tùy mức tích hợp. |
| `@Async @EventListener` | Không có bảo đảm state mới đã commit. | `Scenario.andWaitForStateChange(...)`. |
| `@TransactionalEventListener(AFTER_COMMIT)` | Phải tính tới thời điểm commit. | Đảm bảo giao dịch commit rồi chờ kết quả có thể đọc. |
| Event qua broker/outbox hoặc read model async | Hoàn thành publish không đồng nghĩa consumer đã cập nhật. | Poll public read API/read model với timeout phù hợp. |

## 6. Đọc state qua nguồn dữ liệu thật, không qua object cũ

Ngay cả khi sử dụng `andWaitForStateChange`, test vẫn có thể sai nếu `Supplier` không thực sự lấy state mới. Ví dụ:

```java
// Rủi ro: entity lấy từ trước và giữ nguyên reference.
Order cachedOrder = orderRepository.findById(orderId).orElseThrow();

scenario.publish(new PaymentCaptured(orderId, "TX-005"))
        .andWaitForStateChange(cachedOrder::isPaid, paid -> paid);
```

Nếu listener khác thread cập nhật database, `cachedOrder` không tự được làm mới. `Supplier` lặp lại cùng phương thức trên **cùng object** nên có thể mãi nhìn thấy trạng thái cũ. Cách làm phù hợp hơn:

```java
scenario.publish(new PaymentCaptured(orderId, "TX-005"))
        .andWaitForStateChange(
                () -> orderQueries.statusOf(orderId),
                state -> state.filter(s -> s == OrderStatus.PAID).isPresent())
        .andVerify(state -> assertThat(state).contains(OrderStatus.PAID));
```

`Supplier` tốt cần:

- Đọc lại từ một repository, projection hoặc query service đáng tin cậy.
- Chỉ đọc, không ghi thêm dữ liệu, không phát lại event trong mỗi lượt poll.
- Truy vấn theo `orderId`/correlation ID riêng của bài test.
- Nhìn thấy dữ liệu **đã commit**, không bị khóa trong một persistence context cũ.
- Đủ nhẹ để gọi lại nhiều lần mà không làm nghẽn database.

### 6.1. Trường hợp đặc biệt: JPA và transaction của test

Một test có `@Transactional` bao quanh toàn phương thức có thể giữ `EntityManager`/persistence context hoặc snapshot dữ liệu từ trước. Gọi lại `repository.findById(id)` trong cùng context đôi khi vẫn trả về entity đang được quản lý, không phải trạng thái đã commit bởi listener khác. Tùy isolation level, một transaction đọc kéo dài cũng có thể không thấy update từ thread khác.

Với kiểm thử bất đồng bộ, nên tổ chức fixture và phép đọc sao cho dữ liệu ban đầu đã commit, listener xử lý trong transaction phù hợp, rồi query có thể nhìn thấy commit mới. Một query projection chuyên biệt hoặc query service với transaction đọc rõ ràng thường dễ kiểm soát hơn việc giữ entity JPA. Không tùy tiện `EntityManager.clear()` trong phép poll nếu thao tác đó có nguy cơ ảnh hưởng dữ liệu chưa flush của test.

## 7. Đặt giới hạn thời gian chờ phù hợp

Đợi theo điều kiện không có nghĩa là đợi mãi. Khi cần giới hạn thời gian chờ, Spring Modulith cung cấp cách cấu hình scenario trước khi chọn state change:

```java
import java.time.Duration;

scenario.publish(new PaymentCaptured(orderId, "TX-006"))
        .andWaitAtMost(Duration.ofSeconds(5))
        .forStateChange(
                () -> orderQueries.statusOf(orderId),
                state -> state.filter(s -> s == OrderStatus.PAID).isPresent())
        .andVerify(state -> assertThat(state).contains(OrderStatus.PAID));
```

Con số 5 giây là ví dụ. Giới hạn cần dựa vào đặc điểm runtime, database, môi trường CI và yêu cầu của kịch bản. Timeout quá ngắn gây false negative khi hạ tầng chậm; timeout quá dài làm lỗi thật tốn thời gian mới được báo. Nếu listener không chạy, dữ liệu không commit hoặc predicate không thể trở thành `true`, việc tăng timeout sẽ không khắc phục nguyên nhân.

`Scenario` dùng cơ chế chờ có điều kiện, giúp test kết thúc sớm khi trạng thái đạt. Trong dự án không có `Scenario`, có thể dùng cơ chế await/poll tương đương (chẳng hạn Awaitility) với cùng nguyên tắc: xác định rõ state reader, điều kiện đích, timeout và assertion. Không cần tự viết vòng lặp ngủ thủ công cho kiểm thử này.

### 7.1. Xử lý trạng thái thất bại kết thúc sớm

Một luồng thanh toán có thể chuyển sang `PAYMENT_FAILED`, là trạng thái kết thúc không thể tiếp tục đạt `PAID` trong kịch bản hiện tại. Nếu chỉ đợi `PAID`, test sẽ timeout và khó phân biệt với listener chưa chạy. Có thể chờ **một trong hai trạng thái kết thúc**, rồi assert chỉ trạng thái thành công:

```java
scenario.publish(new PaymentCaptured(orderId, "TX-007"))
        .andWaitForStateChange(
                () -> orderQueries.statusOf(orderId),
                state -> state.filter(s -> s == OrderStatus.PAID
                                        || s == OrderStatus.PAYMENT_FAILED)
                              .isPresent())
        .andVerify(state -> assertThat(state).contains(OrderStatus.PAID));
```

`PAYMENT_FAILED` lúc này cho phép **kết thúc chờ**, nhưng assertion vẫn **thất bại** như mong đợi. Chỉ áp dụng nếu đó thật sự là terminal state; nếu nghiệp vụ còn retry từ `PAYMENT_FAILED` sang `PAID`, đừng dừng sớm theo trạng thái lỗi tạm thời.

## 8. State change, event arrival và kết quả ổn định là ba mục tiêu khác nhau

Trong kiểm thử Spring Modulith, cần chọn bằng chứng đúng với hợp đồng:

| Kỳ vọng của bài test | Phép quan sát phù hợp | Ranh giới của kết luận |
| --- | --- | --- |
| Một event loại `OrderPaid` xuất hiện | Cơ chế đợi event của `Scenario`, ví dụ `andWaitForEventOfType(...)`. | Event tồn tại chưa chứng minh database/read model đã commit. |
| Đơn hàng chuyển thành `PAID` trong khoảng chờ | `andWaitForStateChange(...)` với predicate đúng. | Một lần đọc `PAID` không chứng minh state không bao giờ đổi lại. |
| Mã thanh toán, thời điểm và trạng thái nhất quán | Đọc aggregate/projection đầy đủ các trường và kiểm tra invariant. | Phải đọc dữ liệu cùng snapshot đáng tin cậy. |
| Consumer khác nhìn thấy trạng thái mới | Poll public query API hoặc read model của consumer. | Có thể đạt sau khi database gốc đã cập nhật. |

Đừng nhầm “listener đã nhận event” với “công việc đã hoàn tất”. Ngoài ra, `Predicate` trả `true` tại một thời điểm không bảo đảm trạng thái giữ nguyên mãi sau đó. Khi nghiệp vụ yêu cầu tính bền vững, hãy chọn dấu hiệu kết thúc đã commit hoặc bổ sung test kiểm chứng invariant và các chuyển trạng thái sau đó.

## 9. Tránh test sai phạm ranh giới module

Để kiểm tra state xuyên module, tốt nhất dùng một API truy vấn được module sở hữu công khai. Ví dụ test module `payments` muốn biết trạng thái đơn hàng nên truy vấn `OrderQueries.statusOf(orderId)` do module `orders` cung cấp, thay vì import `orders.internal.OrderRepository`.

`@ApplicationModuleTest` khởi tạo test context theo phạm vi module và các phụ thuộc được cấu hình; vì vậy cần bảo đảm event handler, adapter và database cần thiết thực sự được đưa vào kịch bản. Một test timeout do thiếu listener trong context không chứng minh listener production chậm.

Kiểm thử hành vi không tự bắt hết phụ thuộc kiến trúc sai. Kết hợp phép xác minh ranh giới:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTests {

    @Test
    void verifyModuleDependencies() {
        ApplicationModules.of(MySpringBootApplication.class).verify();
    }
}
```

Thay `MySpringBootApplication.class` bằng application class thật. Các quy tắc `@ApplicationModule(allowedDependencies = ...)` và `@NamedInterface` (nếu dùng) cho phép diễn tả bề mặt phụ thuộc được phép. Quality gate cần chạy cả **test kiến trúc** lẫn **test hành vi/state change** để ngăn sai ranh giới và hồi quy khi refactor listener, transaction hoặc event contract.

## 10. Cách điều tra một scenario timeout hoặc fail ngẫu nhiên

| Triệu chứng | Nguyên nhân khả dĩ | Việc nên làm |
| --- | --- | --- |
| Assertion ngay sau publish lúc pass lúc fail. | Race giữa test thread và async listener. | Thay bằng chờ trạng thái thực với timeout, bỏ `Thread.sleep`. |
| `andWaitForStateChange` dừng sớm nhưng `andVerify` thấy `AWAITING_PAYMENT`. | Predicate quá rộng hoặc chỉ kiểm tra `Optional.isPresent`. | Chờ cụ thể `status == PAID`. |
| Timeout nhưng log báo listener đã ghi `PAID`. | Transaction chưa commit, cache, JPA persistence context cũ, sai ID, read replica trễ. | Đối chiếu DB với giá trị supplier và transaction thực tế. |
| Không thấy listener chạy. | Test context không chứa listener, chưa bật async, hoặc `AFTER_COMMIT` chưa có commit. | Kiểm tra bootstrap/module dependencies, async config và transaction boundary. |
| Test chạy được một mình, fail khi song song. | Dùng chung ID, fixture trùng hoặc dữ liệu test ảnh hưởng nhau. | Tạo ID riêng, cô lập dữ liệu và cleanup thích hợp. |
| Test timeout khi trạng thái đã là `PAYMENT_FAILED`. | Predicate không xem lỗi terminal là một kết quả kết thúc. | Chờ terminal state rồi assert kỳ vọng nếu nghiệp vụ cho phép. |
| Test pass nhưng `paymentReference` rỗng. | Chỉ kiểm tra enum, bỏ qua invariant. | Đọc projection/aggregate chứa đủ dữ liệu và assert các trường liên quan. |

Khi điều tra, nên lưu **business ID/correlation ID**, thời điểm phát event, log listener/commit và giá trị cuối supplier quan sát được. Nếu database đúng mà supplier vẫn sai, tìm ở nguồn đọc hoặc transaction. Nếu database không đổi, kiểm tra đường phát/nhận sự kiện và lỗi của handler. Những dữ kiện này hữu ích hơn việc tăng số lần chạy lại test để hy vọng pass.

## 11. Đưa vào CI quality gate

Một chuỗi kiểm chứng cơ bản cho pull request:

1. Xác minh ranh giới module bằng `ApplicationModules.of(...).verify()` và các quy tắc phụ thuộc hiện có.
2. Chạy `@ApplicationModuleTest` cho đường event dẫn đến cập nhật trạng thái được lưu.
3. Chạy các test tích hợp cần thiết với database/broker/test infrastructure được cấu hình ổn định.
4. Bảo đảm timeout hoặc assertion fail làm bước CI thất bại; không dùng retry vô điều kiện để che flaky test.
5. Theo dõi thời gian test và log khi vượt timeout, để sửa nguyên nhân của race condition hoặc visibility.

Ví dụ dự án Gradle có cấu hình các test JUnit trong task `test`:

```bash
./gradlew test
```

Nếu dự án có task riêng cho integration test, quality gate phải chạy thêm task đó. Lệnh minh họa trên không có nghĩa mọi integration test đều mặc nhiên chạy trong `test`.

## 12. Bài tập thực hành

**Bài 1 — tái hiện race condition:** tạo listener xử lý bất đồng bộ và fixture `AWAITING_PAYMENT`. Viết assertion `PAID` ngay sau publish; chạy nhiều lần trong môi trường test có scheduling thay đổi để quan sát lý do nó có thể fail. Sau đó dùng `Scenario.andWaitForStateChange(...)` với predicate chính xác và so sánh độ ổn định.

**Bài 2 — bỏ `Thread.sleep`:** lấy test chờ cố định 2 giây rồi assert. Chuyển thành chờ theo điều kiện với giới hạn tối đa hợp lý. Giải thích vì sao test chạy nhanh hơn khi listener hoàn tất sớm và báo lỗi rõ hơn khi listener không hoàn tất.

**Bài 3 — transaction và state cũ:** thử giữ `Order` entity trước event, gọi `cachedOrder::isPaid` trong supplier, rồi đổi sang `OrderQueries.statusOf(id)`. Khảo sát tác động của transaction và JPA persistence context đối với khả năng nhìn thấy commit.

**Bài 4 — terminal failure:** tạo tình huống handler trả trạng thái `PAYMENT_FAILED`. Cho predicate dừng ở `PAID` hoặc `PAYMENT_FAILED`, đồng thời `andVerify` chỉ chấp nhận `PAID`. Đọc thông báo test thất bại để phân biệt thất bại nghiệp vụ với timeout.

**Bài 5 — quality gate:** bổ sung phép `ApplicationModules.verify()` vào suite, kiểm tra module gọi qua public query API, và xác nhận lỗi dependency hoặc state change khiến CI thất bại.

**Tiêu chí hoàn thành:** test nêu rõ trạng thái đầu và đích, không kiểm tra ngay khi không có bảo đảm đồng bộ, không dùng `Thread.sleep`, đọc state đã commit qua đúng ranh giới module, có timeout hữu hạn và phát hiện được cả lỗi hành vi lẫn vi phạm kiến trúc.

## 13. Ghi nhớ và tài liệu tham khảo

Trong luồng bất đồng bộ, **thời điểm phát event và thời điểm trạng thái có thể quan sát là hai mốc khác nhau**. Assertion tức thì làm bài test phụ thuộc lịch thread; ngủ cố định chỉ che giấu vấn đề. Hãy định nghĩa kết quả nghiệp vụ, đọc lại state qua API phù hợp, đợi đúng điều kiện bằng `Scenario.andWaitForStateChange(...)`, và thất bại rõ ràng khi quá timeout.

Tài liệu tham khảo:

- [Spring Modulith Reference — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario` và kiểm thử thay đổi state.
- [Spring Modulith Javadoc — `Scenario.When`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/Scenario.When.html): các lựa chọn chờ state và cấu hình thời gian chờ.
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và phụ thuộc giữa module.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): hành vi của `@TransactionalEventListener`, các pha commit và giao dịch.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): xử lý `@Async` và cấu hình executor.
