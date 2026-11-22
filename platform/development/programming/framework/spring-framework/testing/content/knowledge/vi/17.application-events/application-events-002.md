# Ghi nhận loại sự kiện, payload và số lần xuất hiện

Trong ứng dụng Spring, một thành phần có thể phát sự kiện để thông báo rằng một việc đã xảy ra. Thành phần phát sự kiện không cần gọi trực tiếp từng thành phần quan tâm đến việc đó. Ví dụ, `OrderService` phát `OrderPlacedEvent` sau khi tạo đơn hàng; listener kiểm toán, gửi thông báo hoặc cập nhật một phần dữ liệu khác có thể lắng nghe sự kiện này.

Khi kiểm thử luồng đó, ta thường cần trả lời ba câu hỏi:

- **Loại sự kiện:** ứng dụng đã phát đúng loại sự kiện cần thiết chưa?
- **Payload:** sự kiện mang đúng dữ liệu nghiệp vụ chưa?
- **Số lần xuất hiện:** một thao tác đã phát sự kiện đúng số lần chưa?

Spring TestContext cung cấp `@RecordApplicationEvents` và `ApplicationEvents` để ghi nhận các application event được phát trong quá trình chạy một test. Nhờ đó, test có thể kiểm tra sự kiện thực tế mà không phải tự viết một listener chỉ để thu thập dữ liệu.

## 1. Phân biệt loại sự kiện và payload

Một application event là thông điệp được gửi qua `ApplicationEventPublisher`. Loại sự kiện cho biết **điều gì đã xảy ra**; payload chứa **thông tin cụ thể của lần xảy ra đó**.

Ví dụ, `OrderPlacedEvent` là loại sự kiện. `orderId` và `total` là dữ liệu đi kèm sự kiện. Khi kiểm thử, chỉ xác nhận rằng có một sự kiện `OrderPlacedEvent` là chưa đủ: sự kiện có thể mang nhầm mã đơn hàng hoặc tổng tiền. Ngược lại, chỉ kiểm tra một giá trị payload mà không lọc loại sự kiện có thể khiến test vô tình đọc một sự kiện khác có cấu trúc tương tự.

Spring hỗ trợ hai cách biểu diễn thường gặp:

1. Một lớp sự kiện kế thừa `ApplicationEvent`. Khi đó, lớp cụ thể chính là kiểu của sự kiện và có thể được truy vấn trực tiếp.
2. Một đối tượng thông thường, chẳng hạn Java `record`, được truyền vào `publishEvent(Object)`. Spring bọc đối tượng đó trong `PayloadApplicationEvent`; dữ liệu gốc được lấy qua `getPayload()`.

Nên thống nhất cách biểu diễn trong một luồng nghiệp vụ để test dễ đọc và ít phải xử lý trường hợp đặc biệt.

## 2. Phát một sự kiện từ ứng dụng

Ví dụ dưới đây dùng lớp sự kiện kế thừa `ApplicationEvent`. Các trường `orderId` và `total` là payload mà listener và test cần kiểm tra.

```java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEvent;

public final class OrderPlacedEvent extends ApplicationEvent {

    private final String orderId;
    private final BigDecimal total;

    public OrderPlacedEvent(Object source, String orderId, BigDecimal total) {
        super(source);
        this.orderId = orderId;
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Service phát sự kiện thông qua `ApplicationEventPublisher`:

```java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher eventPublisher;

    public OrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void placeOrder(String orderId, BigDecimal total) {
        // Thực hiện nghiệp vụ tạo đơn hàng tại đây.
        eventPublisher.publishEvent(
            new OrderPlacedEvent(this, orderId, total)
        );
    }
}
```

Listener có thể nhận đúng kiểu sự kiện bằng `@EventListener`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        // Ghi nhận event.getOrderId() và event.getTotal().
    }
}
```

## 3. Bật bộ ghi nhận sự kiện trong Spring Test

Đặt `@RecordApplicationEvents` trên lớp test dùng Spring TestContext. Spring sẽ cung cấp đối tượng `ApplicationEvents` để truy vấn các sự kiện được phát trong phạm vi từng lần chạy test.

```java
import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@RecordApplicationEvents
class OrderServiceEventTests {

    @Autowired
    private OrderService orderService;

    @Autowired
    private ApplicationEvents applicationEvents;

    @Test
    void publishesOrderPlacedWithExpectedPayloadOnce() {
        orderService.placeOrder("ORD-208", new BigDecimal("250000.00"));

        List<OrderPlacedEvent> publishedEvents = applicationEvents
            .stream(OrderPlacedEvent.class)
            .toList();

        assertThat(publishedEvents).hasSize(1);

        OrderPlacedEvent event = publishedEvents.get(0);
        assertThat(event.getOrderId()).isEqualTo("ORD-208");
        assertThat(event.getTotal()).isEqualByComparingTo("250000.00");
    }
}
```

Trong ví dụ này:

- `@SpringBootTest` khởi tạo application context để test gọi service thật.
- `@RecordApplicationEvents` bật việc ghi nhận event cho test.
- `applicationEvents.stream(OrderPlacedEvent.class)` chỉ lấy các event thuộc kiểu `OrderPlacedEvent`.
- `hasSize(1)` kiểm tra số lần phát; các assertion tiếp theo kiểm tra payload.

Nếu chỉ quan tâm số lần phát, có thể đếm trực tiếp:

```java
long count = applicationEvents.stream(OrderPlacedEvent.class).count();
assertThat(count).isEqualTo(1L);
```

Khi một thao tác hợp lệ phải phát nhiều sự kiện cùng loại, hãy kiểm tra số lượng mong đợi và dữ liệu của từng sự kiện. Ví dụ, sau khi xử lý một lô gồm ba đơn hàng, test có thể xác nhận có ba `OrderPlacedEvent` và tập `orderId` tương ứng với ba đơn hàng đầu vào. Việc kiểm tra cả số lượng lẫn dữ liệu giúp phát hiện trường hợp thiếu event, phát trùng event hoặc phát event cho sai đối tượng.

## 4. Ghi nhận payload dạng Java object hoặc record

Không bắt buộc phải tạo lớp kế thừa `ApplicationEvent`. Spring cho phép phát một object bất kỳ:

```java
import java.math.BigDecimal;

public record OrderPlaced(String orderId, BigDecimal total) {
}
```

```java
eventPublisher.publishEvent(
    new OrderPlaced("ORD-208", new BigDecimal("250000.00"))
);
```

Với object không kế thừa `ApplicationEvent`, Spring tạo `PayloadApplicationEvent` để chứa payload. Vì vậy, khi dùng `ApplicationEvents`, hãy lọc wrapper rồi lấy payload bên trong:

```java
import org.springframework.context.PayloadApplicationEvent;

List<OrderPlaced> payloads = applicationEvents
    .stream(PayloadApplicationEvent.class)
    .map(PayloadApplicationEvent::getPayload)
    .filter(OrderPlaced.class::isInstance)
    .map(OrderPlaced.class::cast)
    .toList();

assertThat(payloads).hasSize(1);
assertThat(payloads.get(0).orderId()).isEqualTo("ORD-208");
assertThat(payloads.get(0).total())
    .isEqualByComparingTo("250000.00");
```

Điểm cần nhớ là kiểu wrapper được ghi nhận ở tầng application event, còn kiểu `OrderPlaced` là kiểu payload nghiệp vụ. Nếu test truy vấn `PayloadApplicationEvent.class`, hãy kiểm tra tiếp kiểu payload để tránh đếm nhầm payload khác.

## 5. Đếm theo loại sự kiện và kiểm tra nhiều lần phát

`ApplicationEvents` có thể trả về toàn bộ event trong lần chạy test hoặc chỉ các event thuộc một kiểu. Khi kiểm tra số lần xuất hiện, nên lọc theo loại sự kiện cụ thể:

```java
long orderPlacedCount = applicationEvents
    .stream(OrderPlacedEvent.class)
    .count();

long orderCancelledCount = applicationEvents
    .stream(OrderCancelledEvent.class)
    .count();

assertThat(orderPlacedCount).isEqualTo(1L);
assertThat(orderCancelledCount).isZero();
```

Việc kiểm tra một loại event không xuất hiện cũng hữu ích. Chẳng hạn, khi tạo đơn hàng thành công, hệ thống phải phát `OrderPlacedEvent` và không được phát `OrderCancelledEvent`.

Nếu cần xem các event theo thứ tự phát, có thể lấy stream không truyền kiểu:

```java
var allEvents = applicationEvents.stream().toList();
```

Chỉ nên khẳng định thứ tự khi thứ tự đó là một phần của hợp đồng nghiệp vụ. Với listener chạy bất đồng bộ, thứ tự xử lý có thể khác thứ tự phát.

## 6. Sự kiện được phát khác với listener đã xử lý

Đây là ranh giới quan trọng khi thiết kế assertion:

- `ApplicationEvents` ghi nhận application event được phát vào context.
- Nó không phải bộ đếm số lần từng listener được gọi.
- Một event có thể được nhiều listener nhận; số event được phát vẫn là một.
- Một listener có thể thất bại khi xử lý dù event đã được phát thành công.

Vì vậy, hãy tách hai mục tiêu kiểm thử:

**Kiểm tra hợp đồng phát event:** dùng `@RecordApplicationEvents` để xác nhận kiểu, payload và số lần phát như các ví dụ phía trên.

**Kiểm tra hành vi của listener:** xác nhận kết quả mà listener tạo ra, chẳng hạn bản ghi kiểm toán được lưu, thông báo được đưa vào hàng đợi hoặc một collaborator được gọi với dữ liệu đúng. Nếu mục tiêu là kiểm tra riêng listener, có thể phát event trực tiếp trong test và kiểm tra hiệu ứng của listener.

Không suy ra rằng listener đã chạy thành công chỉ vì `applicationEvents.stream(...).count()` trả về số lượng mong đợi.

## 7. Các tình huống cần chú ý

### Event listener chạy bất đồng bộ

Listener mặc định xử lý đồng bộ với luồng phát event, trừ khi được cấu hình chạy bất đồng bộ, chẳng hạn bằng `@Async` cùng cấu hình hỗ trợ async. Với listener bất đồng bộ, test có thể nhìn thấy event đã được phát trước khi listener hoàn thành. Khi kiểm tra hiệu ứng của listener, hãy chờ điều kiện hoàn tất bằng cơ chế chờ có giới hạn thời gian; không dùng `Thread.sleep()` cố định vì dễ gây test chậm và thiếu ổn định.

### Listener gắn với transaction

`@TransactionalEventListener` có thể chỉ xử lý event ở một transaction phase, thường là `AFTER_COMMIT`. Nếu test chạy trong transaction được rollback ở cuối test, listener chờ commit có thể không được gọi. Cần thiết kế test để transaction thực sự commit khi muốn kiểm tra hành vi sau commit. Việc bộ ghi nhận thấy event đã được phát không chứng minh rằng transaction đã commit hoặc listener sau commit đã chạy.

### Nhiều event cùng loại

Đừng chỉ kiểm tra `hasSize(1)` khi nghiệp vụ có thể phát nhiều event. Hãy xác nhận danh sách payload hoặc các định danh ổn định để biết event nào đã xuất hiện. Ngược lại, nếu hợp đồng yêu cầu đúng một event, kiểm tra số lượng chính xác giúp phát hiện phát trùng.

### Event của framework xuất hiện trong context

Application context có thể phát các event phục vụ vòng đời hoặc hạ tầng Spring. Tránh đếm toàn bộ event rồi giả định tất cả đều thuộc nghiệp vụ đang kiểm tra. Hãy lọc theo kiểu event hoặc kiểu payload cần xác nhận.

### Dữ liệu so sánh

Với `BigDecimal`, nên dùng assertion so sánh theo giá trị như `isEqualByComparingTo` nếu scale không phải một phần của hợp đồng. Với payload phức tạp, ưu tiên kiểm tra các trường nghiệp vụ quan trọng thay vì phụ thuộc vào `toString()` hoặc biểu diễn nội bộ của object.

## 8. Quy trình chọn assertion phù hợp

| Mục tiêu kiểm thử | Cách ghi nhận | Assertion cần có |
|---|---|---|
| Có phát đúng loại event | `stream(EventType.class)` | Danh sách có event mong đợi |
| Payload đúng | Lấy event rồi đọc các trường; với object thông thường, lấy `PayloadApplicationEvent.getPayload()` | So sánh các trường nghiệp vụ |
| Phát đúng một lần | Đếm stream theo loại event | Số lượng bằng `1` |
| Không phát event ngoài ý muốn | Đếm stream của loại event đó | Số lượng bằng `0` |
| Listener xử lý thành công | Kiểm tra kết quả hoặc collaborator của listener | Hiệu ứng nghiệp vụ đúng |
| Listener bất đồng bộ hoàn tất | Chờ điều kiện hoàn tất có timeout | Hiệu ứng xuất hiện trước timeout |

Khi viết test, hãy bắt đầu từ hợp đồng của thao tác: thao tác đó phải phát event nào, mang dữ liệu nào và phát bao nhiêu lần. Sau đó chọn cách truy vấn tương ứng từ `ApplicationEvents`. Cách làm này giúp test phát hiện rõ ba nhóm lỗi thường gặp: sai loại event, sai payload và sai số lần phát.

## 9. Ghi nhớ

`@RecordApplicationEvents` bật bộ ghi nhận sự kiện cho test Spring TestContext; `ApplicationEvents` cung cấp stream để lọc và đếm event. Với lớp kế thừa `ApplicationEvent`, truy vấn trực tiếp theo kiểu lớp đó. Với object hoặc record thông thường, kiểm tra `PayloadApplicationEvent` rồi đọc payload. Cuối cùng, luôn phân biệt việc **event đã được phát** với việc **listener đã xử lý thành công**: hai điều này cần những assertion riêng.
