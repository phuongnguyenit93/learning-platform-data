# Dependency từ application event listener

Khi một application module phát application event, module khác có thể đăng ký listener để phản ứng với sự kiện đó. Ví dụ, sau khi `order` xác nhận đơn hàng, `shipping` chuẩn bị giao hàng và `notification` gửi email xác nhận. Module phát event không cần gọi trực tiếp từng module tiêu thụ.

Trong module model của Spring Modulith, quan hệ này vẫn là một dependency. Điểm đặc biệt là hướng dependency đi từ **module khai báo listener** đến **module sở hữu và công bố event**. Spring Modulith phân loại quan hệ đó là `EVENT_LISTENER`. Nhờ vậy, dependency graph thể hiện đúng module nào cần hợp đồng event của module nào, dù hai bên không gọi Spring bean của nhau.

## 1. Event listener tạo dependency theo hướng nào?

Giả sử ứng dụng có ba module:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── events
│       └── OrderPlaced.java
├── shipping
│   └── ShippingOrderEvents.java
└── notification
    └── NotifyOnOrderPlaced.java
```

Module `order` phát `OrderPlaced`. Hai module `shipping` và `notification` đăng ký listener cho event đó. Dependency graph có hướng:

```text
shipping ------ EVENT_LISTENER ------> order
notification -- EVENT_LISTENER ------> order
```

Mũi tên bắt đầu từ consumer vì consumer phải biết type event mà nó lắng nghe. Module `order` không cần biết những listener nào đang tồn tại; nó chỉ công bố một sự kiện có ý nghĩa nghiệp vụ.

Điều này khác với bean dependency:

```text
order -------- USES_COMPONENT ------> inventory
```

Ở đây `order` gọi bean của `inventory`, nên `order` phụ thuộc vào component do `inventory` cung cấp. Với event, `shipping` và `notification` phụ thuộc vào hợp đồng event của `order`, còn `order` không phụ thuộc vào các consumer.

## 2. `EVENT_LISTENER` trong Spring Modulith có nghĩa gì?

`DependencyType.EVENT_LISTENER` biểu thị module nguồn phụ thuộc vào module đích bằng cách khai báo event listener cho một event được module đích công bố. Spring Modulith phân biệt loại này với `USES_COMPONENT`, vốn biểu thị dependency qua Spring component và yêu cầu module đích được bootstrap để chạy module nguồn.

Với `EVENT_LISTENER`, module đích không cần được bootstrap chỉ để chạy module nguồn. Module nguồn cần biết hợp đồng event, nhưng không cần gọi một bean của module phát event. Đây là lý do event thường phù hợp cho những hành động phụ mà module phát không cần điều phối trực tiếp.

Ví dụ, `shipping` cần biết rằng đơn hàng đã được đặt để tạo shipment. Nó không cần gọi `OrderManagement` để hỏi module `order` phải làm gì tiếp theo. `OrderPlaced` là hợp đồng đủ để `shipping` thực hiện trách nhiệm riêng.

`EVENT_LISTENER` vẫn là dependency kiến trúc cần được quản lý. Nếu `shipping` lắng nghe event của `order`, việc đổi tên, chuyển package hoặc thay đổi cấu trúc payload của event có thể ảnh hưởng đến `shipping`. Event giảm liên kết điều khiển trực tiếp, nhưng không xóa sự phụ thuộc vào hợp đồng.

## 3. Module phát sở hữu event contract

Một event nên mô tả sự thật nghiệp vụ đã xảy ra, dùng tên ở thì quá khứ và chứa dữ liệu ổn định mà consumer cần. Tránh đưa entity JPA hoặc repository nội bộ vào payload.

Ví dụ, module `order` công bố event:

```java
package com.acme.shop.order.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        Instant occurredAt
) {
}
```

`OrderPlaced` mô tả đơn hàng đã được tạo. Event không cần chứa `Order` entity, `OrderRepository` hoặc toàn bộ aggregate. Consumer chỉ nhận dữ liệu cần thiết để thực hiện công việc của mình.

Nếu package `events` là package con của module `order`, hãy công bố nó bằng Named Interface:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Named Interface làm rõ rằng các event trong package này là hợp đồng được module `order` cung cấp cho module khác. Những package như `order.internal` vẫn là phần triển khai nội bộ.

Nếu event được đặt trực tiếp trong root package `com.acme.shop.order`, nó thuộc API package mặc định của module đóng. Với một nhóm event có nhiều type, package `events` được công bố riêng thường giúp tổ chức hợp đồng rõ hơn.

## 4. Phát event mà không biết consumer

Module `order` sử dụng `ApplicationEventPublisher` để phát event sau khi hoàn tất thay đổi trạng thái nghiệp vụ:

```java
package com.acme.shop.order.internal;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

@Service
class PlaceOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    PlaceOrderService(
            OrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    void place(PlaceOrder command) {
        Order order = Order.create(command);
        orders.save(order);

        events.publishEvent(new OrderPlaced(
                order.id(),
                Instant.now()
        ));
    }
}
```

`ApplicationEventPublisher` là API của Spring Framework. Module `order` không cần inject `ShippingService` hoặc `NotificationService`, cũng không cần duy trì danh sách consumer. Khi có module mới muốn phản ứng với `OrderPlaced`, module đó tự đăng ký listener.

Trong ví dụ, event được phát trong transaction tạo đơn. Thời điểm listener thực thi phụ thuộc annotation listener mà consumer sử dụng. Không nên giả định mọi event listener đều tự động chạy sau commit hoặc bất đồng bộ.

## 5. Module tiêu thụ đăng ký listener

Module `shipping` lắng nghe event qua `@ApplicationModuleListener`:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOrderEvents {

    private final ShippingService shipping;

    ShippingOrderEvents(ShippingService shipping) {
        this.shipping = shipping;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        shipping.prepareShipment(event.orderId());
    }
}
```

Module `notification` có thể đăng ký listener độc lập:

```java
package com.acme.shop.notification;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class NotifyOnOrderPlaced {

    private final NotificationService notifications;

    NotifyOnOrderPlaced(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        notifications.sendOrderConfirmation(event.orderId());
    }
}
```

Hai listener không cần biết nhau. Chúng chỉ cần biết `OrderPlaced`, là event contract do `order` sở hữu. Vì vậy, Spring Modulith ghi nhận hai dependency riêng: `shipping -> order` và `notification -> order`.

## 6. Những listener nào tạo dependency event?

Spring Modulith nhận diện các dạng listener của Spring để xác định module đang tiêu thụ event. Những dạng thường gặp gồm:

| Cách khai báo | Ý nghĩa |
| --- | --- |
| `@EventListener` | Listener ứng dụng Spring thông thường |
| `@TransactionalEventListener` | Listener gắn với phase của transaction |
| `@ApplicationModuleListener` | Shortcut của Spring Modulith cho cách tích hợp module qua event |
| Bean triển khai `ApplicationListener<E>` | Listener theo interface của Spring Framework |

Điều kiện kiến trúc cốt lõi là listener nằm trong một application module và tham chiếu event type được một module khác công bố. Một listener cho event nội bộ trong cùng module không tạo dependency giữa hai module khác nhau.

Không phải cứ gọi `ApplicationEventPublisher.publishEvent()` là tự động tạo một dependency event listener. Dependency này được suy ra từ phía module khai báo listener và type event mà listener nhận. Nếu không có consumer trong module khác, không có cạnh `EVENT_LISTENER` tương ứng.

## 7. So sánh `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`

Các annotation listener khác nhau về thời điểm và transaction semantics. Sự khác nhau đó không làm đổi hướng dependency trong module graph: consumer vẫn phụ thuộc vào module công bố event.

| Listener | Thời điểm xử lý | Đặc điểm |
| --- | --- | --- |
| `@EventListener` | Theo cơ chế event publication mặc định, thường đồng bộ | Dễ dùng cho phản ứng đơn giản; không tự gắn với transaction commit |
| `@TransactionalEventListener` | Mặc định `AFTER_COMMIT` khi có transaction phù hợp | Có thể chọn `BEFORE_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` |
| `@ApplicationModuleListener` | Shortcut cho xử lý event giữa module: bất đồng bộ, sau commit, transaction riêng | Phù hợp cho phản ứng độc lập với transaction của module phát |

`@ApplicationModuleListener` được cung cấp để diễn đạt cách tích hợp module qua event thường dùng. Nó kết hợp cơ chế listener giao dịch với xử lý bất đồng bộ và transaction mới cho listener. Nếu dùng listener này, hãy thiết kế consumer để xử lý lỗi và khả năng một event được gửi xử lý lại.

Vì annotation này bao gồm `@Async`, ứng dụng cần bật xử lý bất đồng bộ của Spring, thường bằng `@EnableAsync` trên lớp cấu hình hoặc lớp ứng dụng. Nếu chưa bật async processing, không nên mặc định rằng listener đang chạy trên executor riêng chỉ vì method có `@ApplicationModuleListener`.

Nếu dùng `@TransactionalEventListener` trực tiếp, listener mặc định chạy ở phase `AFTER_COMMIT`; khi không có transaction, listener không được gọi trừ khi bật `fallbackExecution`. `@EventListener` thông thường không có ràng buộc transaction như vậy.

## 8. Khai báo `allowedDependencies` cho event listener

Vì module tiêu thụ phụ thuộc vào event contract, allowlist cần được khai báo ở module tiêu thụ. Ví dụ, `shipping` chỉ được phép sử dụng Named Interface `events` của `order`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.acme.shop.shipping;
```

Tương tự, `notification` cũng cần khai báo dependency của chính nó:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.acme.shop.notification;
```

Không cần khai báo `shipping` hoặc `notification` trong allowlist của `order` chỉ vì hai module này lắng nghe event. Hướng dependency là từ listener đến event owner.

Nếu consumer còn sử dụng API package gốc của `order`, hãy khai báo thêm dependency đến module `order` tương ứng. `order :: events` chỉ cho phép Named Interface `events`; nó không tự mở package nội bộ hoặc toàn bộ API khác của module.

## 9. Event listener làm giảm coupling nhưng không xóa dependency

So sánh hai cách tích hợp:

**Gọi bean trực tiếp:**

```text
order --inject/call--> shipping.ShippingService
```

Module `order` biết component cụ thể của `shipping`. Khi thêm một consumer khác, code điều phối của `order` có thể phải thay đổi.

**Phát event:**

```text
shipping ------ EVENT_LISTENER ------> order :: events
notification -- EVENT_LISTENER ------> order :: events
```

Module `order` chỉ phát `OrderPlaced`. Consumer mới có thể đăng ký mà không cần sửa `PlaceOrderService`. Tuy nhiên, mỗi consumer vẫn phụ thuộc vào event contract và phải cập nhật khi hợp đồng đó thay đổi.

Vì vậy, event giúp giảm phụ thuộc điều khiển trực tiếp và hỗ trợ mở rộng consumer độc lập. Nó không biến module thành độc lập hoàn toàn. Event type vẫn là API, cần được thiết kế ổn định và quản lý tương thích.

## 10. Dependency event không đồng nghĩa với message broker

Application event mặc định được phát trong Spring ApplicationContext. Các module có thể trao đổi event trong cùng tiến trình mà không cần Kafka, RabbitMQ hoặc một broker bên ngoài.

`EVENT_LISTENER` trong module model mô tả quan hệ giữa application module trong cùng ứng dụng. Nó không tự chứng minh event đã được gửi qua mạng hoặc module consumer chạy trong process riêng.

Nếu cần gửi event ra hệ thống ngoài, đó là một chủ đề khác: event externalization. Khi đó, ứng dụng cần cấu hình broker integration hoặc cơ chế outbox phù hợp, chọn event được externalize và xác định routing. Không nên suy ra khả năng giao tiếp liên tiến trình chỉ từ một cạnh `EVENT_LISTENER`.

## 11. Theo dõi event publication và xử lý lỗi

Với listener giao dịch, Spring Modulith cung cấp Event Publication Registry để ghi nhận publication cho từng listener. Registry ghi entry trong transaction phát event; khi listener hoàn tất thành công, entry được đánh dấu hoàn tất. Nếu listener lỗi, publication chưa hoàn tất có thể được xem xét để phục hồi hoặc gửi xử lý lại theo cấu hình.

Điều này hữu ích khi module `order` đã commit đơn hàng nhưng `shipping` gặp lỗi trong quá trình tạo shipment. Registry cho phép quan sát publication chưa hoàn tất và hỗ trợ quy trình retry. Tuy nhiên, retry có thể khiến listener nhận cùng event nhiều lần. Consumer nên idempotent để không tạo shipment hoặc gửi thông báo trùng lặp.

Registry là cơ chế theo dõi và phục hồi event publication, không thay đổi hướng dependency trong module graph. `shipping` vẫn phụ thuộc vào event contract của `order`.

## 12. Kiểm tra dependency từ event listener

Có thể dùng `ApplicationModules.verify()` để kiểm tra các quy tắc module, bao gồm dependency allowlist, truy cập package nội bộ và chu trình dependency:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesEventListenerDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu `shipping` lắng nghe event trong `order.events`, package này phải được công bố bằng Named Interface hoặc event phải nằm trong API package mặc định. Nếu `shipping` khai báo `allowedDependencies`, dependency `order :: events` cần nằm trong danh sách.

Khi tạo module documentation hoặc xem module arrangement qua Actuator, dependency từ listener module đến event owner có thể được hiển thị với type `EVENT_LISTENER`. Component dependency có thể xuất hiện dưới type `USES_COMPONENT`, giúp phân biệt hai cách tích hợp.

Một test kiến trúc có thể xác nhận dependency graph không vi phạm allowlist, nhưng vẫn nên có test hành vi cho từng listener: event được phát đúng lúc, listener thực hiện đúng phản ứng và lỗi được xử lý theo yêu cầu nghiệp vụ.

## 13. Những lỗi thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Module phát event khai báo phụ thuộc vào tất cả consumer | Đảo ngược hướng dependency | Khai báo dependency ở module listener đến event owner |
| Consumer import event từ package `internal` | Consumer phụ thuộc vào implementation package | Đưa event vào API package hoặc Named Interface |
| Cho rằng event listener không tạo dependency | Consumer vẫn phụ thuộc vào event type và semantics của nó | Quản lý cạnh `EVENT_LISTENER` như dependency kiến trúc |
| Cho rằng `@EventListener` luôn chạy sau commit | Listener thông thường không tự có transaction phase | Dùng `@TransactionalEventListener` hoặc `@ApplicationModuleListener` khi cần semantics tương ứng |
| Cho rằng `EVENT_LISTENER` đồng nghĩa Kafka/RabbitMQ | Đây là quan hệ module trong application context | Cấu hình externalization riêng nếu cần broker |
| Cho rằng publish event bảo đảm consumer xử lý đúng một lần | Listener có thể lỗi và được gửi lại | Thiết kế consumer idempotent, theo dõi publication và xử lý retry |
| Thêm event type vào API nhưng không cập nhật allowlist | Dependency thực tế vượt khỏi hợp đồng đã khai báo | Cho phép đúng module hoặc Named Interface trong `allowedDependencies` |

## 14. Ghi nhớ

Dependency từ application event listener có hướng từ module tiêu thụ đến module công bố event. Spring Modulith biểu diễn quan hệ đó bằng `DependencyType.EVENT_LISTENER`. Module phát event không cần biết consumer; consumer cần biết event contract nên vẫn có một dependency kiến trúc rõ ràng.

Hãy để module phát sở hữu event, công bố type qua package gốc hoặc Named Interface, và để mỗi consumer đăng ký listener trong module của mình. Dùng `allowedDependencies` ở phía consumer để giới hạn hợp đồng được phép sử dụng. Chọn `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener` theo transaction semantics mong muốn; đừng nhầm application event nội bộ với message broker. Cuối cùng, dùng `ApplicationModules.verify()` để kiểm tra boundary và dependency graph, đồng thời kiểm thử hành vi và khả năng phục hồi của listener.

## Tài liệu tham khảo

- [Spring Modulith API — `DependencyType.EVENT_LISTENER`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/DependencyType.html)
- [Spring Modulith API — `ApplicationModuleListener`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html)
- [Spring Modulith Reference — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith Reference — Fundamentals and Application Module Dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
