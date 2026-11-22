# @RecordApplicationEvents và ApplicationEvents

Spring Framework có cơ chế application event để các thành phần trong ứng dụng thông báo một sự kiện mà không cần gọi trực tiếp từng thành phần quan tâm. Khi kiểm thử, đôi khi điều cần xác nhận chính là một thao tác đã phát ra đúng sự kiện, đúng loại và mang đúng dữ liệu. Spring Test cung cấp `@RecordApplicationEvents` và `ApplicationEvents` để thực hiện việc đó ngay trong test context.

Tính năng ghi nhận application event này có từ Spring Framework 5.3. Ví dụ bên dưới dùng JUnit Jupiter và Spring TestContext Framework.

## 1. Hai thành phần làm gì?

- `@RecordApplicationEvents` đặt trên lớp kiểm thử để bật việc ghi nhận các application event được publish trong quá trình chạy từng test method.
- `ApplicationEvents` là API cho phép test đọc các event đã được ghi nhận. API cung cấp stream để lấy toàn bộ event hoặc lọc theo kiểu event.

Hai thành phần phối hợp với nhau: annotation bật cơ chế ghi nhận; đối tượng `ApplicationEvents` cung cấp dữ liệu để assertion. Chúng không tự publish event và cũng không thay thế các listener trong ứng dụng.

## 2. Ôn lại cơ chế application event

Một thành phần có thể publish event thông qua `ApplicationEventPublisher`. Thành phần khác trong cùng application context có thể nhận event bằng `ApplicationListener` hoặc phương thức có `@EventListener`.

Ví dụ, dịch vụ xử lý đơn hàng có thể phát ra `OrderSubmitted` sau khi nhận đơn. Một listener khác có thể dùng event đó để ghi audit hoặc gửi thông báo. Dịch vụ xử lý đơn hàng không cần biết listener nào đang đăng ký.

```java
public class OrderSubmitted extends ApplicationEvent {

    private final String orderId;

    public OrderSubmitted(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

Dịch vụ publish event:

```java
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void submit(String orderId) {
        // Thực hiện xử lý đơn hàng tại đây.
        eventPublisher.publishEvent(new OrderSubmitted(this, orderId));
    }
}
```

Spring cũng cho phép publish một object bất kỳ bằng `publishEvent(Object)`. Với object không kế thừa `ApplicationEvent`, Spring bọc object đó trong `PayloadApplicationEvent` trước khi dispatch.

## 3. Bật ghi nhận bằng @RecordApplicationEvents

Đặt annotation trên lớp test có sử dụng Spring TestContext:

```java
@SpringJUnitConfig(OrderServiceTests.Config.class)
@RecordApplicationEvents
class OrderServiceTests {
    // Các dependency và test method nằm ở đây.
}
```

Trong ví dụ này:

- `@SpringJUnitConfig` cấu hình Spring TestContext cho JUnit Jupiter. Annotation này kết hợp việc nạp application context và tích hợp `SpringExtension`.
- `@RecordApplicationEvents` yêu cầu Spring Test ghi nhận application event trong lúc thực thi các test method của lớp.
- `ApplicationEvents` có thể được inject vào test class bằng `@Autowired`.

Nếu dùng Spring Boot, có thể đặt `@RecordApplicationEvents` cùng `@SpringBootTest`. Với cấu hình JUnit Jupiter khác, cần bảo đảm test đang chạy qua Spring TestContext, chẳng hạn thông qua `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`.

Thông thường không cần tự đăng ký test execution listener cho tính năng này; Spring TestContext xử lý việc ghi nhận khi annotation được khai báo.

## 4. Đọc event bằng ApplicationEvents

Ví dụ test hoàn chỉnh:

```java
import java.util.List;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OrderServiceTests.Config.class)
@RecordApplicationEvents
class OrderServiceTests {

    @Autowired
    private OrderService orderService;

    @Autowired
    private ApplicationEvents applicationEvents;

    @Test
    void recordsEventPublishedWhenOrderIsSubmitted() {
        orderService.submit("A-42");

        List<OrderSubmitted> publishedEvents = applicationEvents
                .stream(OrderSubmitted.class)
                .collect(Collectors.toList());

        assertEquals(1, publishedEvents.size());
        assertEquals("A-42", publishedEvents.get(0).getOrderId());
    }

    @Configuration
    static class Config {

        @Bean
        OrderService orderService(ApplicationEventPublisher eventPublisher) {
            return new OrderService(eventPublisher);
        }
    }
}
```

Luồng kiểm thử diễn ra như sau:

1. Spring tạo application context cho test class và bật cơ chế ghi nhận event.
2. Test gọi `orderService.submit("A-42")`.
3. `OrderService` publish một `OrderSubmitted` vào application context.
4. `ApplicationEvents` cung cấp các event đã ghi nhận có kiểu `OrderSubmitted`.
5. Test kiểm tra số lượng event và giá trị `orderId`.

`stream(OrderSubmitted.class)` trả về stream đã lọc theo kiểu event. Cách này thường rõ ràng hơn việc lấy mọi event rồi tự kiểm tra kiểu bằng `instanceof`.

## 5. Các cách truy vấn thường dùng

`ApplicationEvents` cung cấp `stream()` để duyệt tất cả event và `stream(Class<T>)` để lấy event theo kiểu. Vì kết quả là Java Stream, có thể dùng các thao tác Stream quen thuộc.

Đếm số event:

```java
long count = applicationEvents.stream(OrderSubmitted.class).count();
assertEquals(1, count);
```

Kiểm tra có event thỏa điều kiện:

```java
boolean hasExpectedOrder = applicationEvents
        .stream(OrderSubmitted.class)
        .anyMatch(event -> "A-42".equals(event.getOrderId()));

assertEquals(true, hasExpectedOrder);
```

Lấy event đầu tiên:

```java
OrderSubmitted event = applicationEvents
        .stream(OrderSubmitted.class)
        .findFirst()
        .orElseThrow(() -> new AssertionError("OrderSubmitted was not published"));

assertEquals("A-42", event.getOrderId());
```

Lấy toàn bộ event để kiểm tra nhiều thuộc tính:

```java
List<OrderSubmitted> events = applicationEvents
        .stream(OrderSubmitted.class)
        .collect(Collectors.toList());
```

Mỗi lần cần truy vấn, hãy tạo stream mới từ `ApplicationEvents`. Một Java Stream chỉ được tiêu thụ một lần; không lưu stream rồi dùng lại cho nhiều assertion.

## 6. Kiểm tra event dạng payload

Khi ứng dụng publish một object không kế thừa `ApplicationEvent`, Spring biểu diễn nó dưới dạng `PayloadApplicationEvent`. Vì vậy, nếu cần kiểm tra payload, hãy đọc payload từ wrapper:

```java
List<Object> payloads = applicationEvents
        .stream(PayloadApplicationEvent.class)
        .map(PayloadApplicationEvent::getPayload)
        .collect(Collectors.toList());
```

Cần import:

```java
import org.springframework.context.PayloadApplicationEvent;
```

Nếu chỉ quan tâm một payload cụ thể, có thể lọc tiếp theo kiểu hoặc giá trị của payload. Với event class kế thừa `ApplicationEvent`, truy vấn trực tiếp bằng `stream(MyEvent.class)` thường đơn giản hơn.

## 7. Phạm vi và thời điểm ghi nhận

Việc ghi nhận gắn với quá trình thực thi test method. Spring TestContext quản lý vòng đời của dữ liệu event cho từng method, do đó các event của một test không nên được xem là dữ liệu dùng chung để cộng dồn giữa nhiều test method.

Một vài hệ quả cần nhớ:

- Event được publish trong lúc test method chạy có thể được truy vấn qua `ApplicationEvents` của test đó.
- Event phát sinh khi application context đang khởi tạo thường xảy ra trước giai đoạn ghi nhận của test method, vì vậy không nên dùng API này để kiểm tra event khởi động context.
- Hãy truy vấn event trong test method tương ứng, nơi thao tác phát sinh event được thực hiện.
- Nếu test dùng nhiều application context, hãy bảo đảm thao tác và `ApplicationEvents` đang được kiểm tra thuộc đúng context.

Cơ chế này ghi nhận event được publish trong application context. Nó không thay đổi cách Spring dispatch event và không tự thực thi listener.

## 8. Ghi nhận event khác với kiểm tra listener

Có hai câu hỏi kiểm thử khác nhau:

1. **Thành phần đã publish đúng event chưa?** Dùng `@RecordApplicationEvents` và `ApplicationEvents` để kiểm tra loại event, số lần publish và dữ liệu của event.
2. **Listener đã xử lý event đúng chưa?** Kiểm tra kết quả hoặc side effect do listener tạo ra, chẳng hạn bản ghi audit, trạng thái đã cập nhật hoặc lời gọi tới collaborator.

Việc tìm thấy một event trong `ApplicationEvents` chứng minh event đã được publish và ghi nhận trong context. Điều đó tự nó không chứng minh mọi listener đã xử lý thành công. Nếu listener dùng `@Async`, phần xử lý có thể hoàn tất sau khi lời gọi publish kết thúc; khi kiểm tra side effect bất đồng bộ, test cần cơ chế chờ hoặc đồng bộ phù hợp.

## 9. Khi nào nên dùng?

Tính năng này hữu ích khi event là một phần trong hợp đồng của thành phần đang kiểm thử:

- Một service phải publish event sau khi hoàn tất một thao tác nghiệp vụ.
- Một command phải phát ra đúng một event hoặc không phát event khi dữ liệu không hợp lệ.
- Event phải mang đúng mã đối tượng, trạng thái hoặc thông tin nghiệp vụ.
- Một luồng xử lý có nhiều event và test cần xác nhận event quan trọng đã xuất hiện.

Không cần ghi nhận event trong mọi test. Nếu mục tiêu chỉ là kiểm tra giá trị trả về của một phương thức và event không thuộc hành vi cần bảo đảm, assertion trực tiếp trên kết quả thường dễ hiểu hơn.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy event trong stream | Thiếu `@RecordApplicationEvents` hoặc test không chạy qua Spring TestContext | Thêm annotation và kiểm tra cấu hình Spring test |
| Stream không có event mong đợi | Test chưa gọi đúng thao tác publish hoặc đang truy vấn sai kiểu event | Kiểm tra đường đi của thao tác và dùng đúng event class |
| Không tìm thấy POJO event theo class của payload | Spring bọc object trong `PayloadApplicationEvent` | Truy vấn wrapper rồi lấy `getPayload()` |
| Test thấy nhiều event hơn dự kiến | Context còn phát sinh các event khác trong lúc test | Lọc theo kiểu event cụ thể và kiểm tra điều kiện nghiệp vụ |
| Có event nhưng listener chưa tạo side effect | Đang kiểm tra việc publish thay vì kết quả xử lý của listener; listener có thể chạy bất đồng bộ | Assertion trên kết quả listener và chờ hoàn tất nếu cần |

## 11. Checklist khi viết test

- Test class đã dùng Spring TestContext và có `@RecordApplicationEvents`.
- `ApplicationEvents` được inject từ đúng test context.
- Test thực hiện thao tác có khả năng publish event trước khi truy vấn stream.
- Assertion lọc theo event class cụ thể khi có thể.
- Test kiểm tra cả số lượng lẫn dữ liệu quan trọng của event.
- Nếu cần xác nhận listener, test kiểm tra side effect của listener riêng.
- Không giữ hoặc tái sử dụng một Java Stream sau khi đã terminal operation.

## 12. Ghi nhớ

`@RecordApplicationEvents` bật ghi nhận application event trong Spring TestContext cho từng test method. `ApplicationEvents` cho phép truy vấn những event đó bằng Java Stream. Kết hợp hai API này giúp test xác nhận một thao tác đã publish đúng event và đúng dữ liệu, đồng thời giữ rõ ranh giới giữa kiểm tra việc publish event và kiểm tra logic xử lý của listener.

