# Lọc sự kiện hạ tầng để tập trung vào hợp đồng nghiệp vụ

Khi kiểm thử một thành phần Spring có phát sự kiện, mục tiêu thường là xác nhận một hành động nghiệp vụ đã công bố đúng sự kiện, với đúng dữ liệu và đúng số lần. Tuy nhiên, một `ApplicationContext` có thể phát nhiều loại sự kiện trong suốt vòng đời của nó. Ngoài sự kiện do nghiệp vụ tạo ra, bài kiểm thử còn có thể gặp sự kiện mô tả trạng thái của Spring, vòng đời request hoặc hoạt động kỹ thuật khác.

Nếu kiểm tra tổng số sự kiện trong context, bài kiểm thử sẽ phụ thuộc vào những chi tiết không thuộc hợp đồng nghiệp vụ. Cách ổn định hơn là truy vấn đúng loại sự kiện cần xác nhận bằng `ApplicationEvents.stream(Class<T>)`, hoặc gom các sự kiện nghiệp vụ qua một kiểu chung do ứng dụng định nghĩa. Việc lọc này chỉ giới hạn dữ liệu mà bài kiểm thử quan sát; nó không thay đổi cơ chế phát hoặc phân phối sự kiện trong ứng dụng.

## 1. Phân biệt sự kiện nghiệp vụ và sự kiện hạ tầng

Spring cung cấp cơ chế publish/subscribe thông qua `ApplicationEventPublisher` và các listener trong `ApplicationContext`. Một sự kiện có thể là một lớp kế thừa `ApplicationEvent`, hoặc một object bất kỳ được publish làm payload. Spring chuyển payload phù hợp thành `PayloadApplicationEvent` để đưa qua cơ chế event chung.

Hai nhóm sự kiện có mục đích khác nhau:

| Nhóm | Điều sự kiện mô tả | Ví dụ |
|---|---|---|
| Nghiệp vụ | Một sự thật hoặc kết quả có ý nghĩa với quy tắc của ứng dụng | `OrderPlaced`, `PaymentAuthorized`, `InventoryReserved` |
| Hạ tầng | Trạng thái hoặc hoạt động kỹ thuật của môi trường chạy | `ContextRefreshedEvent`, `ContextClosedEvent`, `RequestHandledEvent` |

Sự kiện nghiệp vụ thường trả lời câu hỏi “điều gì đã xảy ra trong miền nghiệp vụ?”. Tên sự kiện nên mô tả một sự thật đã xảy ra, chẳng hạn `OrderPlaced`, thay vì mô tả lệnh kỹ thuật như `SaveOrderCommand`. Payload nên chứa dữ liệu cần thiết để người nhận hiểu sự kiện, ví dụ mã đơn hàng và tổng tiền; tránh đưa các đối tượng phụ thuộc hạ tầng như `HttpServletRequest`, `EntityManager` hoặc repository vào hợp đồng.

Sự kiện hạ tầng vẫn có ích. Một listener có thể cần phản ứng khi context được refresh, hoặc hệ thống quan sát có thể cần biết request đã hoàn tất. Nhưng các sự kiện đó thường không phải điều mà bài kiểm thử `OrderService` cần xác nhận. Bài kiểm thử nên tập trung vào sự kiện nghiệp vụ mà service cam kết phát ra.

## 2. Vì sao kiểm tra toàn bộ danh sách sự kiện dễ gây brittle

Giả sử một bài kiểm thử gọi `OrderService.placeOrder()` rồi xác nhận context chỉ phát đúng một sự kiện:

```java
assertThat(applicationEvents.stream()).hasSize(1);
```

Khẳng định này trộn hai loại hợp đồng:

- Hợp đồng của `OrderService`: khi đặt đơn thành công, ứng dụng phát `OrderPlaced`.
- Chi tiết của môi trường kiểm thử: trong cùng khoảng thời gian, không có listener, thành phần Spring hoặc thành phần phụ nào phát thêm sự kiện.

Hợp đồng thứ hai có thể thay đổi khi cấu hình test, thư viện, listener hoặc cách khởi tạo context thay đổi. Bài kiểm thử có thể thất bại dù `OrderService` vẫn làm đúng điều nó phải làm.

Ví dụ, context có các sự kiện vòng đời như `ContextRefreshedEvent` hoặc sự kiện request như `RequestHandledEvent`. Chúng có thể xuất hiện trong cùng môi trường kiểm thử nhưng không phải kết quả nghiệp vụ của thao tác đặt hàng. Kiểm tra tổng số sự kiện khiến bài kiểm thử phụ thuộc vào những sự kiện đó.

Thay vào đó, hãy hỏi một câu hẹp và rõ: “Có bao nhiêu `OrderPlaced` được phát trong lần thực thi này?”.

## 3. Ghi nhận sự kiện bằng `@RecordApplicationEvents`

Spring TestContext Framework cung cấp hai thành phần để quan sát sự kiện:

- `@RecordApplicationEvents`: yêu cầu Spring ghi lại các sự kiện được publish trong `ApplicationContext` trong quá trình thực thi một test.
- `ApplicationEvents`: API cho phép truy vấn các sự kiện đã ghi nhận.

Với JUnit Jupiter, có thể khai báo `ApplicationEvents` như một tham số của phương thức test hoặc lifecycle method. Đây là cách phù hợp vì đối tượng này có phạm vi theo từng phương thức test. Không đưa `ApplicationEvents` vào constructor của lớp test.

Ví dụ sau dùng một payload dạng record. `OrderPlaced` không cần kế thừa `ApplicationEvent`:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(OrderServiceTests.TestConfig.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Test
    void publishesOrderPlaced(
            @Autowired OrderService service,
            ApplicationEvents applicationEvents) {

        UUID orderId = UUID.randomUUID();
        BigDecimal total = new BigDecimal("125.00");

        service.placeOrder(orderId, total);

        List<OrderPlaced> published =
                applicationEvents.stream(OrderPlaced.class).toList();

        assertThat(published).hasSize(1);
        assertThat(published.get(0).orderId()).isEqualTo(orderId);
        assertThat(published.get(0).total()).isEqualByComparingTo("125.00");
    }

    @Configuration(proxyBeanMethods = false)
    @Import(OrderService.class)
    static class TestConfig {
    }
}

record OrderPlaced(UUID orderId, BigDecimal total) {
}

class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    void placeOrder(UUID orderId, BigDecimal total) {
        // Thực hiện các bước nghiệp vụ cần thiết trước khi phát sự kiện.
        eventPublisher.publishEvent(new OrderPlaced(orderId, total));
    }
}
```

`@SpringJUnitConfig` kích hoạt Spring TestContext cho JUnit Jupiter và nạp cấu hình test. `@RecordApplicationEvents` bật bộ ghi sự kiện. Tham số `ApplicationEvents` được Spring cung cấp cho test hiện tại. Sau khi gọi service, `stream(OrderPlaced.class)` chỉ trả về các event hoặc payload có kiểu `OrderPlaced`.

Vì vậy, dù context có ghi nhận thêm `ContextRefreshedEvent`, `RequestHandledEvent` hoặc một event hạ tầng khác, truy vấn trên vẫn chỉ tập trung vào payload `OrderPlaced`. Test xác nhận cả số lượng lẫn dữ liệu của hợp đồng nghiệp vụ.

## 4. Chọn bộ lọc theo hợp đồng cần kiểm tra

### 4.1. Chỉ có một loại sự kiện cần xác nhận

Ưu tiên truy vấn trực tiếp theo kiểu sự kiện:

```java
List<OrderPlaced> orderEvents =
        applicationEvents.stream(OrderPlaced.class).toList();

assertThat(orderEvents).hasSize(1);
assertThat(orderEvents.get(0).orderId()).isEqualTo(expectedOrderId);
```

`stream(Class<T>)` nhận kiểu của event hoặc payload. Điều này hữu ích khi ứng dụng publish record hoặc POJO, bởi bài test không cần tự bóc `PayloadApplicationEvent`.

Nếu một nhánh nghiệp vụ không được phép phát sự kiện, hãy kiểm tra trực tiếp sự kiện đó:

```java
assertThat(applicationEvents.stream(OrderPlaced.class)).isEmpty();
```

Khẳng định này diễn đạt rõ điều cần bảo vệ: trong tình huống hiện tại không có đơn hàng nào được đặt thành công.

### 4.2. Có nhiều sự kiện nghiệp vụ cùng thuộc một nhóm

Khi nhiều event cần được quan sát như một nhóm, ứng dụng có thể định nghĩa marker interface. Đây là quy ước của miền ứng dụng, không phải một interface bắt buộc của Spring:

```java
interface BusinessEvent {
}

record OrderPlaced(UUID orderId) implements BusinessEvent {
}

record PaymentAuthorized(UUID orderId, String authorizationId)
        implements BusinessEvent {
}
```

Test có thể truy vấn cả nhóm bằng kiểu chung:

```java
List<BusinessEvent> businessEvents =
        applicationEvents.stream(BusinessEvent.class).toList();

assertThat(businessEvents).hasSize(2);
assertThat(businessEvents)
        .anyMatch(OrderPlaced.class::isInstance)
        .anyMatch(PaymentAuthorized.class::isInstance);
```

Do `ApplicationEvents.stream(Class<T>)` hỗ trợ cả event và payload theo kiểu được yêu cầu, marker interface có thể được triển khai bởi các payload nghiệp vụ. Các event hạ tầng của Spring không triển khai marker interface đó nên không xuất hiện trong danh sách này.

Chỉ nên thêm marker interface khi nhóm sự kiện thực sự có ý nghĩa trong thiết kế ứng dụng. Nếu test chỉ cần kiểm tra `OrderPlaced`, truy vấn trực tiếp `OrderPlaced.class` đơn giản và chính xác hơn.

### 4.3. Lọc theo dữ liệu của một sự kiện

Sau khi lọc theo kiểu, có thể tiếp tục lọc theo thuộc tính nghiệp vụ:

```java
List<OrderPlaced> highValueOrders = applicationEvents
        .stream(OrderPlaced.class)
        .filter(event -> event.total().compareTo(new BigDecimal("1000")) >= 0)
        .toList();
```

Đây là lọc dữ liệu quan sát trong test. Nó phù hợp khi test cần xác nhận một nhóm sự kiện theo điều kiện cụ thể, nhưng không nên biến thành một bộ lọc phức tạp lặp lại ở nhiều test. Nếu nhiều test phải diễn đạt cùng một hợp đồng, hãy cân nhắc tạo helper nhỏ có tên theo nghiệp vụ.

## 5. Khi nào dùng `stream()` không có tham số

`applicationEvents.stream()` trả về toàn bộ `ApplicationEvent` đã ghi nhận. API này hữu ích khi cần chẩn đoán vì sao một event không xuất hiện, hoặc muốn xem context đã phát những loại event nào trong test.

Ví dụ, có thể liệt kê kiểu của các event đã ghi nhận khi debug:

```java
applicationEvents.stream()
        .map(event -> event.getClass().getName())
        .forEach(System.out::println);
```

Tuy nhiên, không nên biến danh sách này thành hợp đồng ổn định của một service nghiệp vụ. Đặc biệt, tránh các khẳng định như:

```java
assertThat(applicationEvents.stream()).hasSize(3);
```

trừ khi chính số lượng và tập hợp toàn bộ event là yêu cầu được định nghĩa rõ cho bài test đó. Phần lớn test service chỉ cần xác nhận một hoặc một vài loại event cụ thể.

Nếu event được publish dưới dạng POJO, Spring có thể biểu diễn nó bên trong bằng `PayloadApplicationEvent`. Không nên viết test phụ thuộc vào lớp wrapper nội bộ này. Hãy dùng `stream(OrderPlaced.class)` để truy vấn payload theo kiểu nghiệp vụ.

## 6. Lọc trong test khác với lọc listener khi chạy ứng dụng

Hai thao tác này có mục đích khác nhau:

| Thao tác | Nơi áp dụng | Tác động |
|---|---|---|
| `applicationEvents.stream(OrderPlaced.class)` | Bài test | Chỉ chọn các event/payload cần quan sát và assertion |
| Listener nhận một kiểu event cụ thể | Ứng dụng đang chạy | Quy định listener có nhận và xử lý kiểu event đó hay không |
| Điều kiện của `@EventListener` | Ứng dụng đang chạy | Quy định listener xử lý event dựa trên điều kiện của phương thức |
| `@TransactionalEventListener` | Ứng dụng đang chạy | Gắn thời điểm xử lý listener với một phase của transaction |

Lọc bằng `ApplicationEvents` không ngăn event được publish và không ngăn listener khác nhận event. Nó chỉ làm cho bài test tập trung vào phần cần xác nhận. Không nên thay đổi publisher hoặc xóa listener khỏi context chỉ để danh sách event trong test ngắn hơn.

Nếu yêu cầu là listener chỉ xử lý một loại event, hãy kiểm tra cấu hình listener hoặc hành vi của listener. Nếu yêu cầu là listener chỉ chạy sau khi transaction commit, hãy kiểm tra đúng ranh giới transaction và phase tương ứng. Truy vấn event đã publish không tự chứng minh listener đã hoàn tất xử lý.

## 7. Phạm vi ghi nhận và các trường hợp cần chú ý

### Vòng đời của `ApplicationEvents`

`ApplicationEvents` đại diện cho các event được phát trong quá trình thực thi một test method. Với JUnit Jupiter, nên nhận nó qua tham số của `@Test`, `@BeforeEach` hoặc `@AfterEach`:

```java
@Test
void verifiesOrderEvent(ApplicationEvents applicationEvents) {
    // Gọi hành động cần kiểm thử và truy vấn event tại đây.
}
```

Không inject `ApplicationEvents` vào constructor của lớp test vì đối tượng này chỉ tồn tại trong lifecycle của test method hiện tại.

Nếu `@BeforeEach` hoặc một bước chuẩn bị khác cũng publish event, các event đó có thể làm nhiễu phần quan sát của test. Có thể tổ chức lại test để hành động cần kiểm thử bắt đầu sau bước chuẩn bị, hoặc gọi `applicationEvents.clear()` tại ranh giới rõ ràng trước khi thực hiện hành động:

```java
applicationEvents.clear();
service.placeOrder(orderId, total);

assertThat(applicationEvents.stream(OrderPlaced.class)).hasSize(1);
```

`clear()` xóa các event đã ghi nhận trước thời điểm gọi; những truy vấn tiếp theo chỉ thấy event được ghi sau đó. Không cần gọi `clear()` theo thói quen trong mọi test vì recorder đã được quản lý theo từng test method.

### Cấu hình TestExecutionListener

Spring đăng ký `ApplicationEventsTestExecutionListener` mặc định. Nếu test tự khai báo `@TestExecutionListeners` và thay thế danh sách listener mặc định, hãy bảo đảm listener ghi nhận application events vẫn được đăng ký. Nếu thiếu listener này, việc thêm `@RecordApplicationEvents` có thể không cung cấp dữ liệu như mong đợi.

### Event gắn với transaction

`ApplicationEvents` ghi nhận việc publish event. Điều đó khác với việc một listener có `@TransactionalEventListener` đã chạy ở phase mong muốn. Ví dụ, listener dùng `AFTER_COMMIT` chỉ xử lý sau khi transaction commit. Một test đang chạy trong transaction sẽ rollback theo cơ chế mặc định có thể không tạo ra commit cần thiết để listener chạy.

Khi kiểm thử hành vi sau commit, hãy tạo ranh giới transaction phù hợp và xác nhận kết quả ở phía listener hoặc hệ thống nhận. Không suy ra listener đã chạy chỉ từ việc `stream(OrderPlaced.class)` trả về một event.

### Event bất đồng bộ

Nếu ứng dụng cấu hình việc xử lý event bằng executor, thời điểm listener hoàn thành có thể khác thời điểm publisher trả về. Hãy chờ điều kiện quan sát được của listener trước khi assertion kết quả bất đồng bộ. Không giả định thứ tự hoàn thành của các listener bất đồng bộ là thứ tự publish, trừ khi ứng dụng có cơ chế bảo đảm thứ tự đó và hợp đồng yêu cầu kiểm tra nó.

## 8. Những cách kiểm thử nên tránh

| Cách làm | Vấn đề | Cách diễn đạt tốt hơn |
|---|---|---|
| Đếm tất cả event trong context | Phụ thuộc event hạ tầng và cấu hình test | Đếm `stream(OrderPlaced.class)` |
| So sánh toàn bộ danh sách event với một danh sách cố định | Dễ hỏng khi thêm listener hoặc thành phần Spring | Chỉ kiểm tra các event thuộc hợp đồng nghiệp vụ |
| Lọc theo tên package hoặc tên lớp dạng chuỗi | Dễ bỏ sót event khi refactor package/class | Truy vấn theo kiểu event hoặc marker interface |
| Kiểm tra `PayloadApplicationEvent` như chi tiết bắt buộc | Phụ thuộc cách Spring bọc payload | Truy vấn payload trực tiếp bằng `stream(Class<T>)` |
| Cho rằng event đã publish đồng nghĩa listener đã xử lý xong | Bỏ qua transaction phase và xử lý bất đồng bộ | Kiểm tra riêng publication và kết quả xử lý của listener |
| Thêm điều kiện runtime chỉ để làm test ít event hơn | Thay đổi hành vi ứng dụng vì nhu cầu quan sát của test | Lọc ở `ApplicationEvents` trong test |

Một test tốt mô tả được hành vi bằng ngôn ngữ nghiệp vụ. Ví dụ, “đơn hàng hợp lệ phát đúng một `OrderPlaced`” rõ ràng và bền vững hơn “context phát tổng cộng một event”.

## 9. Quy trình chọn bộ lọc

Khi viết test cho một luồng event, có thể đi theo trình tự sau:

1. Xác định sự thật nghiệp vụ mà hành động phải công bố, ví dụ `OrderPlaced`.
2. Bật `@RecordApplicationEvents` trên test class.
3. Nhận `ApplicationEvents` trong test method.
4. Truy vấn trực tiếp bằng `stream(OrderPlaced.class)`.
5. Kiểm tra số lượng và các trường dữ liệu có ý nghĩa với người nhận event.
6. Nếu nhiều event thực sự thuộc một nhóm nghiệp vụ, cân nhắc marker interface và truy vấn theo kiểu chung.
7. Chỉ dùng `stream()` toàn bộ khi cần chẩn đoán, không dùng tổng số event làm assertion mặc định.
8. Nếu yêu cầu liên quan đến listener, transaction hoặc async, kiểm tra riêng hành vi ở ranh giới tương ứng.

## 10. Tài liệu tham khảo

- [Spring Framework Reference — Application Events in the TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html): cách bật ghi nhận event và truy vấn bằng `ApplicationEvents`.
- [Spring Framework Reference — `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html): phạm vi và cách dùng annotation.
- [Spring Framework Javadoc — `ApplicationEvents`](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html): chữ ký `stream()`, `stream(Class<T>)` và `clear()`.

Điểm cốt lõi của kỹ thuật này là để bài test quan sát đúng hợp đồng mà thành phần nghiệp vụ công bố. Hãy lọc theo kiểu event hoặc payload nghiệp vụ trước khi assertion; để các event hạ tầng tiếp tục phục vụ vòng đời và hoạt động kỹ thuật của Spring mà không chi phối kết quả kiểm thử service.
