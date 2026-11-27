# Event payload không lộ type internal

## Event payload là một phần của hợp đồng module

Trong modular monolith, các module có thể giao tiếp với nhau bằng application event. Module phát sự kiện công bố một điều đã xảy ra; những module quan tâm đăng ký listener để xử lý. Spring Modulith phân tích kiểu event mà listener sử dụng để nhận diện quan hệ phụ thuộc giữa các module.

Vì event type có thể được nhiều module tham chiếu, cả event class và những kiểu xuất hiện trong payload đều trở thành một phần của hợp đồng tích hợp. Nếu payload chứa entity JPA, class trong package internal, enum triển khai hoặc kiểu chỉ có ý nghĩa bên trong module phát event, consumer sẽ bị ràng buộc vào cấu trúc nội bộ đó.

Ví dụ, khi module orders phát OrderCompleted, module inventory chỉ nên phụ thuộc vào dữ liệu công khai cần để xử lý sự kiện. Nó không nên phải biết entity Order, cách module lưu OrderLine, hay enum trạng thái nội bộ mà orders đang sử dụng.

Một payload tốt thể hiện dữ liệu nghiệp vụ mà consumer cần, với các kiểu ổn định và có ý nghĩa rõ ràng.

## Vì sao không đưa type internal vào payload?

Giả sử module orders có cấu trúc:

~~~text
com.acme.shop.orders
├── OrderManagement.java
├── internal
│   ├── Order.java
│   ├── OrderLine.java
│   └── OrderStatus.java
└── events
    └── OrderCompleted.java
~~~

Một cách triển khai dễ gây liên kết là đưa thẳng entity nội bộ vào event:

~~~java
package com.acme.shop.orders.events;

import com.acme.shop.orders.internal.Order;

public record OrderCompleted(Order order) {}
~~~

Consumer nhận event sẽ phải tham chiếu đến Order. Nếu entity có thêm quan hệ JPA, lazy association, trạng thái nội bộ hoặc phương thức phục vụ persistence, những chi tiết đó có thể lan sang consumer. Khi nhóm phát triển đổi entity, consumer có thể phải sửa theo dù hợp đồng nghiệp vụ không thay đổi.

Vấn đề còn có thể ẩn trong các field lồng nhau:

~~~java
public record OrderCompleted(
    UUID orderId,
    OrderStatus status,
    List<OrderLine> lines
) {}
~~~

Dù event class nằm trong package events, payload vẫn để lộ OrderStatus và OrderLine nếu chúng là kiểu nội bộ. Đặt event vào package công khai không tự động biến các kiểu được tham chiếu thành API phù hợp.

## Thiết kế payload bằng kiểu dữ liệu công khai

Hãy định nghĩa payload riêng cho sự kiện. Payload chỉ chứa những dữ liệu mà consumer cần để phản ứng với sự kiện.

Ví dụ, module orders công bố hai record trong package events:

~~~java
package com.acme.shop.orders.events;

import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record OrderCompleted(
    UUID orderId,
    Instant occurredAt,
    List<CompletedOrderLine> lines
) {
    public OrderCompleted {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
        lines = List.copyOf(lines);
    }
}
~~~

Record mô tả từng dòng hàng cũng thuộc hợp đồng công khai:

~~~java
package com.acme.shop.orders.events;

public record CompletedOrderLine(
    String productCode,
    int quantity
) {
    public CompletedOrderLine {
        if (productCode == null || productCode.isBlank()) {
            throw new IllegalArgumentException("productCode must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
~~~

Payload sử dụng UUID, Instant, String, int và record công khai do module sở hữu. Nó không chứa entity hoặc kiểu trong package internal.

List.copyOf tạo bản sao không thể thay đổi của danh sách đầu vào. Record tự tạo accessor và ràng buộc tham chiếu của các field, nhưng tính bất biến của record chỉ là bất biến nông. Nếu field là một object mutable, object đó vẫn có thể bị thay đổi sau khi event được tạo. Vì vậy, hãy ưu tiên kiểu bất biến và sao chép collection khi tạo payload.

## Chuyển đổi từ mô hình nội bộ sang event contract

Module phát event vẫn có thể sử dụng entity và value object nội bộ trong quá trình xử lý nghiệp vụ. Chỉ tại ranh giới phát event, module mới chuyển dữ liệu cần thiết sang payload công khai.

Ví dụ, OrderManagement đọc entity nội bộ rồi tạo event:

~~~java
package com.acme.shop.orders;

import com.acme.shop.orders.events.CompletedOrderLine;
import com.acme.shop.orders.events.OrderCompleted;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderManagement {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderManagement(
        OrderRepository orders,
        ApplicationEventPublisher events,
        Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void complete(UUID orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        order.complete();

        var lines = order.getLines().stream()
            .map(line -> new CompletedOrderLine(
                line.getProduct().getCode(),
                line.getQuantity()
            ))
            .toList();

        events.publishEvent(new OrderCompleted(
            order.getId(),
            clock.instant(),
            lines
        ));
    }
}
~~~

Order, OrderLine và repository vẫn là chi tiết của module orders. Consumer chỉ nhìn thấy OrderCompleted và CompletedOrderLine.

Trong ứng dụng thực tế, tên phương thức, repository và cách lấy dữ liệu sẽ phụ thuộc vào domain model. Điểm cần giữ là phép chuyển đổi diễn ra ở phía module sở hữu dữ liệu, nơi có đủ thông tin để tạo ra hợp đồng công khai.

## Consumer chỉ phụ thuộc vào event contract

Module inventory đăng ký listener bằng các kiểu công khai:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.events.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedListener {

    private final InventoryService inventory;

    OrderCompletedListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        event.lines().forEach(line ->
            inventory.decreaseAvailable(
                line.productCode(),
                line.quantity()
            )
        );
    }
}
~~~

Listener biết mã sản phẩm, số lượng, mã đơn hàng và thời điểm phát sinh sự kiện. Nó không cần biết Order được lưu bằng JPA hay cách OrderLine tính toán số lượng.

Nếu events là package riêng, module orders công bố nó dưới dạng named interface:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Module inventory có thể khai báo phụ thuộc được phép vào named interface đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders::events"
)
package com.acme.shop.inventory;
~~~

Nhờ vậy, hợp đồng event được công bố rõ ràng, còn package orders.internal tiếp tục được giữ kín.

## Chọn dữ liệu payload theo nhu cầu consumer

Payload cần đủ thông tin để consumer thực hiện công việc, nhưng không nên mang toàn bộ object graph của module phát event.

Có hai cách chọn dữ liệu thường gặp:

**Chỉ truyền định danh.** Event chứa orderId, customerId hoặc mã tài nguyên. Consumer dùng API công khai để truy vấn dữ liệu khi cần. Cách này giữ payload nhỏ, nhưng consumer có thể nhận trạng thái hiện tại thay vì trạng thái tại thời điểm event xảy ra. Nếu bản ghi đã thay đổi hoặc bị xóa, dữ liệu truy vấn có thể không còn phản ánh sự kiện ban đầu.

**Truyền snapshot cần thiết.** Event chứa một tập dữ liệu nhỏ phản ánh sự thật tại thời điểm phát event, chẳng hạn mã sản phẩm và số lượng đã đặt. Cách này giúp consumer xử lý theo đúng nội dung sự kiện mà không cần truy vấn ngược. Đổi lại, payload phải được duy trì như một hợp đồng dữ liệu và tránh chứa thông tin không cần thiết.

Hãy chọn theo ý nghĩa nghiệp vụ. Nếu consumer cần biết chính xác những mặt hàng đã hoàn tất trong đơn hàng, payload nên chứa các dòng hàng cần thiết. Nếu consumer chỉ cần xác định đơn hàng nào đã hoàn tất rồi gọi một API truy vấn được công bố, một định danh có thể đủ.

| Dữ liệu | Cách cân nhắc |
|---|---|
| ID nghiệp vụ | Dùng kiểu ổn định như UUID hoặc mã nghiệp vụ đã công bố |
| Thời điểm sự kiện | Dùng Instant hoặc kiểu thời gian công khai có semantics rõ ràng |
| Số lượng | Dùng kiểu số có giới hạn và quy tắc hợp lệ rõ ràng |
| Trạng thái | Dùng enum công khai ổn định hoặc mã trạng thái trong hợp đồng |
| Entity JPA | Không đưa entity hoặc proxy persistence vào payload |
| Value object nội bộ | Chuyển sang kiểu công khai biểu đạt dữ liệu cần thiết |
| Collection | Chỉ chứa các phần tử thuộc hợp đồng công khai và bảo vệ khỏi sửa đổi |

## Tránh rò rỉ type qua các field lồng nhau

Kiểm tra payload không chỉ dừng ở các field trực tiếp. Mỗi kiểu trong cây object của event đều có thể tạo liên kết với module sở hữu kiểu đó.

Ví dụ, các thiết kế sau đều có nguy cơ:

~~~java
public record OrderCompleted(
    Order order,
    InternalOrderStatus status,
    List<OrderLineEntity> lines,
    InternalMoney total
) {}
~~~

Có thể thay bằng các kiểu dữ liệu mô tả rõ hợp đồng:

~~~java
public record OrderCompleted(
    UUID orderId,
    String statusCode,
    List<CompletedOrderLine> lines,
    BigDecimal totalAmount,
    String currencyCode
) {}
~~~

Không nhất thiết mọi field phải là primitive hoặc String. Có thể sử dụng kiểu thư viện phổ biến, bất biến và có semantics rõ ràng như UUID, Instant, BigDecimal, hoặc record công khai của chính module. Điều quan trọng là kiểu đó thuộc hợp đồng mà consumer được phép sử dụng, không phải chi tiết triển khai bị lộ ra ngoài.

Với enum nội bộ, hãy ánh xạ sang một enum công khai nếu tập giá trị là hợp đồng ổn định và được quản lý cùng consumer. Nếu giá trị có thể mở rộng thường xuyên hoặc consumer cần xử lý mã chưa biết, một mã chuỗi ổn định có thể phù hợp hơn. Khi đó, hãy mô tả ý nghĩa và quy tắc xử lý giá trị chưa nhận diện.

## Giữ payload nhỏ và bảo vệ dữ liệu nhạy cảm

Event có thể được nhiều listener, log, hệ thống quan sát hoặc cơ chế lưu publication xử lý. Vì vậy, không nên đưa mọi thông tin có sẵn trong entity vào payload.

Trước khi thêm field, hãy hỏi:

- Consumer nào cần field này?
- Field có cần thiết để xử lý sự kiện hay consumer có thể dùng một API công khai?
- Dữ liệu có chứa email, số điện thoại, địa chỉ, token, thông tin thanh toán hoặc bí mật nội bộ không?
- Có thể dùng định danh hoặc dữ liệu đã giảm thiểu thay cho thông tin nhạy cảm không?

Chỉ đưa dữ liệu cá nhân vào event khi có nhu cầu nghiệp vụ rõ ràng và hệ thống có cách kiểm soát truy cập, lưu trữ, log và thời hạn lưu phù hợp. Không phát token xác thực, thông tin thẻ thanh toán hoặc bí mật cấu hình trong event payload.

Payload cũng nên tránh mang dữ liệu chỉ phục vụ giao diện hoặc persistence, chẳng hạn Hibernate proxy, entity graph, lazy collection hay object chứa session/context của request.

## Duy trì tương thích khi event contract thay đổi

Một khi consumer sử dụng event payload, thay đổi cấu trúc hoặc ý nghĩa của payload có thể ảnh hưởng nhiều module. Hãy xem event như API công khai:

- Giữ tên và ý nghĩa field ổn định; tránh đổi ý nghĩa của field mà vẫn giữ tên cũ.
- Khi bổ sung dữ liệu, xác định giá trị mặc định hoặc cách xử lý khi consumer chưa sử dụng field mới.
- Không xóa hoặc đổi kiểu field khi consumer vẫn phụ thuộc vào nó.
- Nếu ý nghĩa nghiệp vụ thay đổi đáng kể, cân nhắc một event mới với tên thể hiện sự kiện mới.
- Với event được externalize hoặc có thể còn tồn tại qua nhiều lần triển khai, kiểm tra tương thích serialization và chiến lược triển khai producer/consumer.

Không phải event nào cũng cần thêm schemaVersion. Với hợp đồng nội bộ được biên dịch và triển khai cùng nhau, quản lý thay đổi qua API và kiểm tra tích hợp có thể đủ. Khi payload được lưu lâu dài, gửi sang hệ thống khác hoặc các phiên bản consumer chạy đồng thời, versioning tường minh và quy tắc tương thích trở nên quan trọng hơn.

## Kiểm chứng ranh giới module

Có thể dùng ApplicationModules.verify() để kiểm tra các phụ thuộc được thể hiện qua kiểu event và listener:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Nếu consumer import một kiểu trong package nội bộ, kiểm chứng kiến trúc có thể phát hiện vi phạm quyền truy cập module. Nếu payload tham chiếu một kiểu nội bộ, hãy chuyển kiểu đó thành dữ liệu hợp đồng công khai hoặc thay bằng kiểu công khai phù hợp.

Tuy nhiên, verify() không đánh giá ý nghĩa nghiệp vụ của từng field, không phát hiện mọi dữ liệu nhạy cảm và cũng không tự xác nhận khả năng tương thích serialization. Những điều này cần được xem xét trong thiết kế event, review API và test phù hợp.

Một checklist review ngắn cho event payload:

1. Event biểu đạt một sự kiện nghiệp vụ đã xảy ra.
2. Event type và mọi kiểu lồng nhau đều thuộc API công khai của module phát event.
3. Không có entity, proxy, repository type hoặc enum triển khai nội bộ.
4. Payload chỉ chứa dữ liệu consumer thực sự cần.
5. Collection và các field mutable được bảo vệ khỏi thay đổi ngoài ý muốn.
6. Các thay đổi payload có quy tắc tương thích rõ ràng.
7. ApplicationModules.verify() vẫn chạy trong bộ test kiến trúc.

## Bài tập vận dụng

Module orders đang phát event theo cách sau:

~~~java
public record OrderCompleted(
    Order order,
    InternalPaymentStatus paymentStatus
) {}
~~~

Module notifications cần gửi thông báo khi đơn hàng hoàn tất. Module inventory cần mã sản phẩm và số lượng để cập nhật tồn kho.

Hãy thiết kế lại payload để hai consumer không phải tham chiếu đến entity hoặc enum nội bộ. Xác định:

1. Các field nào thực sự cần thiết cho notifications?
2. Các field nào cần thiết cho inventory?
3. Có nên đưa toàn bộ OrderLine vào payload không, hay tạo một record công khai chỉ gồm productCode và quantity?
4. InternalPaymentStatus nên được ánh xạ thành kiểu dữ liệu nào trong hợp đồng công khai?
5. Nếu event nằm trong package orders.events, cần công bố và khai báo phụ thuộc như thế nào?

Một lời giải phù hợp có thể dùng OrderCompleted(UUID orderId, Instant occurredAt, List<CompletedOrderLine> lines, String paymentStatusCode). Chỉ giữ paymentStatusCode nếu consumer thực sự cần trạng thái thanh toán. CompletedOrderLine là record công khai gồm productCode và quantity. Cả hai record nằm trong named interface orders::events; các entity và enum nội bộ vẫn chỉ được sử dụng trong module orders.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể giải thích vì sao payload event là một phần của API module, nhận diện type internal bị lộ trực tiếp hoặc qua field lồng nhau, chuyển mô hình nội bộ thành record công khai phù hợp, chọn giữa định danh và snapshot theo nhu cầu consumer, và kiểm tra phụ thuộc bằng ApplicationModules.verify().

Tài liệu tham khảo:

- [Spring Modulith — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Application Module API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
