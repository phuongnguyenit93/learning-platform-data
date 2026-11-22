# Test execution events khác với sự kiện nghiệp vụ

Trong một ứng dụng Spring, cả framework kiểm thử lẫn mã nghiệp vụ đều có thể phát sự kiện qua `ApplicationContext` và xử lý bằng `@EventListener`. Vì cùng dùng cơ chế sự kiện của Spring nên hai loại này dễ bị nhầm lẫn. Tuy nhiên, chúng biểu đạt hai việc hoàn toàn khác nhau:

- **Test execution event** mô tả một mốc trong vòng đời chạy test, chẳng hạn Spring chuẩn bị test instance hoặc sắp gọi phương thức `@Test`.
- **Sự kiện nghiệp vụ (business/domain event)** mô tả một sự việc có ý nghĩa đối với nghiệp vụ, chẳng hạn đơn hàng đã được tạo hoặc khoản thanh toán đã được xác nhận.

Điểm phân biệt quan trọng nhất là **ai phát sự kiện và sự kiện đang nói về điều gì**. Một sự kiện có thể được truyền qua cùng event bus của Spring nhưng vẫn thuộc về hai ngữ cảnh khác nhau.

## 1. Test execution event là gì?

Spring TestContext Framework quản lý phần tích hợp giữa test framework như JUnit và các tính năng của Spring như dependency injection, `ApplicationContext`, transaction test hoặc quản lý context. Trong quá trình đó, Spring gọi các callback của `TestExecutionListener` tại những thời điểm xác định trong vòng đời test.

`TestExecutionListener` nhận một đối tượng `TestContext`, qua đó có thể truy cập thông tin của lần kiểm thử hiện tại, ví dụ:

- Lớp test và phương thức test đang chạy.
- Test instance đã được tạo và chuẩn bị hay chưa.
- `ApplicationContext` gắn với test.
- Exception phát sinh trong lần test, nếu có.
- Các thuộc tính tạm thời gắn với `TestContext`.

Các callback này là hook dành cho **hạ tầng kiểm thử**. Chúng hữu ích khi cần thiết lập trạng thái, ghi nhận thời gian, thu thập thông tin hoặc dọn dẹp tài nguyên quanh quá trình chạy test.

Spring định nghĩa các callback chính sau:

| Callback | Thời điểm và mục đích |
|---|---|
| `beforeTestClass` | Trước khi các phương thức test của một lớp bắt đầu chạy. |
| `prepareTestInstance` | Sau khi test instance được tạo; Spring có thể thực hiện dependency injection và chuẩn bị instance. |
| `beforeTestMethod` | Trước phần lifecycle method `@BeforeEach` và trước khi thực thi test method. |
| `beforeTestExecution` | Ngay trước phần thân của phương thức `@Test`, sau các phương thức `@BeforeEach`. |
| `afterTestExecution` | Ngay sau phần thân của phương thức `@Test`, trước các phương thức `@AfterEach`. |
| `afterTestMethod` | Sau các phương thức `@AfterEach`, khi lần test method đã kết thúc. |
| `afterTestClass` | Sau khi các phương thức test của lớp đã hoàn tất. |

Với JUnit Jupiter, trình tự khái quát quanh một test method như sau:

```text
Tạo test instance
    ↓
prepareTestInstance
    ↓
beforeTestMethod
    ↓
@BeforeEach
    ↓
beforeTestExecution
    ↓
@Test
    ↓
afterTestExecution
    ↓
@AfterEach
    ↓
afterTestMethod
```

Ở cấp lớp, `beforeTestClass` và `afterTestClass` bao quanh các lần chạy test của lớp. Chi tiết tích hợp có thể phụ thuộc test framework và extension đang sử dụng, nhưng sự khác nhau giữa `beforeTestMethod` với `beforeTestExecution` vẫn rất hữu ích: callback thứ nhất bao gồm cả giai đoạn chuẩn bị test method, còn callback thứ hai đánh dấu sát thời điểm bắt đầu thân test.

Ví dụ, nếu muốn đo riêng thời gian thực thi thân phương thức `@Test`, hãy bắt đầu đo ở `beforeTestExecution` và kết thúc ở `afterTestExecution`. Nếu đo từ `beforeTestMethod` đến `afterTestMethod`, kết quả sẽ bao gồm cả phần setup và teardown của test method.

## 2. Từ TestExecutionListener callback đến Test execution event

Có hai cách phổ biến để phản ứng với vòng đời test:

1. Cài đặt trực tiếp `TestExecutionListener` và override callback cần dùng.
2. Lắng nghe các event mà Spring phát vào `ApplicationContext` tương ứng với những callback đó.

Từ Spring Framework 5.2, `EventPublishingTestExecutionListener` cung cấp cách thứ hai. Listener này chuyển các callback của TestContext thành những event có kiểu cụ thể, sau đó phát chúng vào `ApplicationContext` của test. Các event thường gặp gồm:

| Event | Callback tương ứng |
|---|---|
| `BeforeTestClassEvent` | `beforeTestClass` |
| `PrepareTestInstanceEvent` | `prepareTestInstance` |
| `BeforeTestMethodEvent` | `beforeTestMethod` |
| `BeforeTestExecutionEvent` | `beforeTestExecution` |
| `AfterTestExecutionEvent` | `afterTestExecution` |
| `AfterTestMethodEvent` | `afterTestMethod` |
| `AfterTestClassEvent` | `afterTestClass` |

Trong cấu hình TestContext mặc định, Spring đăng ký `EventPublishingTestExecutionListener`. Vì vậy, khi test sử dụng Spring `ApplicationContext`, một bean có thể lắng nghe các event này bằng `@EventListener`.

Ví dụ: ghi log ngay trước khi thân test được thực thi.

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.event.BeforeTestExecutionEvent;

@Component
class TestLifecycleLogger {

    @EventListener
    void onBeforeTestExecution(BeforeTestExecutionEvent event) {
        TestContext testContext = event.getTestContext();

        System.out.printf(
            "Starting %s#%s%n",
            testContext.getTestClass().getSimpleName(),
            testContext.getTestMethod().getName()
        );
    }
}
```

Bean `TestLifecycleLogger` phải được đăng ký trong `ApplicationContext` mà test đang sử dụng, ví dụ qua component scan hoặc `@Import`. Event chứa `TestContext`, vì vậy listener có thể biết lớp và phương thức test đang chạy.

Nếu cần làm việc trực tiếp với callback, có thể viết một `TestExecutionListener`. Ví dụ sau lưu thời điểm bắt đầu vào `TestContext` rồi tính thời gian ở callback kết thúc:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.TestExecutionListener;

public class TestBodyTimer implements TestExecutionListener {

    private static final String START_TIME =
        TestBodyTimer.class.getName() + ".startTime";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Long start = (Long) testContext.removeAttribute(START_TIME);
        if (start == null) {
            return;
        }

        long elapsedNanos = System.nanoTime() - start;
        System.out.printf(
            "%s#%s took %d ms%n",
            testContext.getTestClass().getSimpleName(),
            testContext.getTestMethod().getName(),
            elapsedNanos / 1_000_000
        );
    }
}
```

Đăng ký listener tùy chỉnh trên lớp test và giữ các listener mặc định của Spring:

```java
@SpringJUnitConfig(TestConfig.class)
@TestExecutionListeners(
    listeners = TestBodyTimer.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderServiceTests {
    // Các test method
}
```

`MERGE_WITH_DEFAULTS` quan trọng khi muốn bổ sung listener tùy chỉnh mà vẫn giữ các listener mặc định, trong đó có listener phục vụ tích hợp và event publishing của Spring.

## 3. Sự kiện nghiệp vụ là gì?

Sự kiện nghiệp vụ mô tả một sự thật hoặc thay đổi có ý nghĩa trong miền nghiệp vụ. Ví dụ:

- `OrderPlaced`: khách hàng đã đặt đơn hàng.
- `PaymentConfirmed`: khoản thanh toán đã được xác nhận.
- `AccountLocked`: tài khoản đã bị khóa theo một quy tắc nghiệp vụ.

Sự kiện loại này được phát ra bởi logic ứng dụng khi một hành động nghiệp vụ xảy ra. Trong Spring, mã ứng dụng thường dùng `ApplicationEventPublisher` để công bố sự kiện; listener có thể dùng `@EventListener` hoặc `@TransactionalEventListener` để xử lý.

Ví dụ về một sự kiện đơn hàng:

```java
import java.util.UUID;

public record OrderPlaced(UUID orderId) {
}
```

Service phát sự kiện sau khi lưu đơn hàng:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    OrderService(
        OrderRepository orderRepository,
        ApplicationEventPublisher eventPublisher
    ) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void placeOrder(Order order) {
        Order savedOrder = orderRepository.save(order);
        eventPublisher.publishEvent(new OrderPlaced(savedOrder.getId()));
    }
}
```

Một thành phần khác có thể nhận sự kiện để thực hiện công việc liên quan:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class InventoryListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void onOrderPlaced(OrderPlaced event) {
        // Xử lý nghiệp vụ tồn kho sau khi transaction tạo đơn đã commit.
    }
}
```

`@TransactionalEventListener` cho phép gắn việc xử lý event với một giai đoạn của transaction. Trong ví dụ, listener chỉ xử lý sau khi transaction commit thành công. Điều này có ý nghĩa nghiệp vụ: hệ thống không nên cập nhật tồn kho theo một đơn hàng mà transaction tạo đơn đã rollback.

`OrderPlaced` không phụ thuộc vào JUnit hay Spring TestContext. Sự kiện này vẫn có ý nghĩa khi ứng dụng chạy thật, dù không có test nào đang thực thi.

## 4. So sánh hai loại sự kiện

| Tiêu chí | Test execution event | Sự kiện nghiệp vụ |
|---|---|---|
| Nguồn phát | Spring TestContext Framework thông qua `TestExecutionListener` và `EventPublishingTestExecutionListener`. | Service, domain model hoặc thành phần ứng dụng khi một việc nghiệp vụ xảy ra. |
| Ý nghĩa | Mô tả tiến trình chạy test: chuẩn bị instance, bắt đầu test method, kết thúc test method. | Mô tả một sự thật nghiệp vụ: đơn hàng được đặt, thanh toán được xác nhận. |
| Vòng đời | Gắn với lần chạy test và test class. | Gắn với hành vi của ứng dụng, độc lập với việc có chạy test hay không. |
| Dữ liệu chính | `TestContext`, test class, test method, test instance và thông tin thực thi test. | Dữ liệu nghiệp vụ cần thiết như mã đơn hàng, mã giao dịch hoặc trạng thái thay đổi. |
| Người tiêu thụ điển hình | Test infrastructure, listener hỗ trợ test, logging hoặc đo thời gian test. | Các thành phần nghiệp vụ, xử lý hậu sự kiện hoặc tích hợp với hệ thống khác. |
| Khi nào xuất hiện | Khi Spring TestContext chạy các callback tương ứng và phát event vào context. | Khi logic ứng dụng chủ động phát event do một hành động nghiệp vụ. |
| Có nên dùng trong production? | Không. Đây là cơ chế thuộc hạ tầng kiểm thử. | Có, nếu sự kiện đó là một phần thiết kế của ứng dụng. |

Một khác biệt dễ bỏ sót: test execution event có thể được phát vào `ApplicationContext`, nhưng điều đó không biến nó thành sự kiện nghiệp vụ. `ApplicationContext` chỉ là cơ chế truyền và phân phối event. Ý nghĩa của event được quyết định bởi loại event, nguồn phát và thời điểm phát.

## 5. Kiểm thử sự kiện nghiệp vụ bằng Spring Test

Khi viết test cho `OrderService`, mục tiêu thường là xác nhận hành động đặt hàng phát ra đúng sự kiện `OrderPlaced`. Ta đang kiểm thử hợp đồng của ứng dụng, không phải kiểm thử callback `beforeTestExecution`.

Spring cung cấp `@RecordApplicationEvents` và `ApplicationEvents` để ghi nhận các event được phát trong quá trình chạy test. Có thể dùng chúng để kiểm tra event theo kiểu:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Test
    void publishesOrderPlaced(ApplicationEvents events) {
        orderService.placeOrder(new Order(/* dữ liệu test */));

        assertThat(events.stream(OrderPlaced.class)).hasSize(1);
    }
}
```

`ApplicationEvents` cho phép lọc các event theo kiểu, nhờ đó test tập trung vào hợp đồng cần xác nhận. Trong test thực tế, nên kiểm tra thêm nội dung quan trọng của event, chẳng hạn `orderId`, thay vì chỉ đếm số lượng.

Lưu ý rằng `ApplicationEvents` ghi nhận event được phát vào context; việc ghi nhận một event không chứng minh mọi listener đã xử lý xong hoặc mọi thay đổi dữ liệu phụ đã được commit. Nếu cần kiểm tra hành vi của `@TransactionalEventListener`, phải thiết kế test phù hợp với ranh giới transaction và thời điểm commit/rollback.

## 6. Chọn đúng cơ chế cho từng mục đích

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Ghi log trước khi thân test chạy | `BeforeTestExecutionEvent` hoặc `TestExecutionListener.beforeTestExecution`. |
| Đo riêng thời gian thân test | Cặp `beforeTestExecution` và `afterTestExecution`. |
| Chuẩn bị dữ liệu hoặc tài nguyên dùng chung quanh mỗi test | `TestExecutionListener`, hoặc lifecycle annotation của JUnit/Spring phù hợp với phạm vi cần xử lý. |
| Xác nhận service phát ra `OrderPlaced` | `@RecordApplicationEvents` và `ApplicationEvents`, hoặc một test listener được cấu hình riêng. |
| Thực hiện công việc sau khi đơn hàng được tạo | Sự kiện nghiệp vụ như `OrderPlaced` và listener ứng dụng. |
| Chỉ xử lý khi transaction đã commit | `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. |

Một vài nguyên tắc giúp tránh nhầm lẫn:

1. **Không dùng test execution event để biểu diễn nghiệp vụ.** `AfterTestMethodEvent` chỉ nói rằng một test method đã kết thúc; nó không có nghĩa đơn hàng, thanh toán hay giao dịch trong ứng dụng đã hoàn tất.
2. **Không đặt logic production vào listener chỉ tồn tại để phục vụ test.** Nếu một hành động cần xảy ra khi `OrderPlaced` được phát, hãy phát và xử lý sự kiện nghiệp vụ ngay trong thiết kế ứng dụng.
3. **Chọn callback đúng với phần thời gian cần quan sát.** `beforeTestMethod` và `afterTestMethod` bao quanh setup/teardown; `beforeTestExecution` và `afterTestExecution` tập trung sát thân phương thức test.
4. **Không suy luận rằng `@EventListener` đồng nghĩa với business event.** Annotation này xử lý event trong `ApplicationContext`; event được lắng nghe có thể là event kiểm thử, event kỹ thuật hoặc event nghiệp vụ.
5. **Tách mục tiêu của test.** Một test có thể kiểm tra ứng dụng phát đúng business event; một test khác có thể kiểm tra hạ tầng đo thời gian test. Hai mục tiêu có thể dùng chung Spring event mechanism nhưng không nên trộn ý nghĩa.

Khi đọc một event trong ứng dụng Spring, hãy xác định nguồn phát trước: nếu event được tạo bởi TestContext quanh `@Test`, đó là test execution event; nếu event được tạo bởi logic ứng dụng để diễn đạt một sự thật nghiệp vụ, đó là business/domain event. Cách phân loại này giúp chọn đúng listener, đúng thời điểm xử lý và đúng phạm vi kiểm thử.
