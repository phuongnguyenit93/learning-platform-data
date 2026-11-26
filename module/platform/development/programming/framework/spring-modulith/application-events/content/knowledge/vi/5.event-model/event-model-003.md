# Sự kiện ứng dụng (Application Event) trong Spring Modulith

## 1. Sự kiện ứng dụng là gì?

Trong một ứng dụng Spring Boot, **application event** là một đối tượng mang thông tin rằng một sự việc đáng quan tâm đã xảy ra. Một thành phần **publisher** công bố đối tượng đó vào cơ chế sự kiện của Spring; các thành phần **listener** đã đăng ký có thể nhận và xử lý.

Trong Spring Modulith, application event còn là phương tiện quan trọng để **giao tiếp giữa các module nghiệp vụ mà không cần gọi trực tiếp service của nhau**. Ví dụ:

- Module `orders` tạo đơn hàng thành công rồi công bố `OrderPlaced`.
- Module `notifications` nghe `OrderPlaced` để gửi thông báo.
- Module `loyalty` nghe cùng sự kiện để cộng điểm.
- Module `audit` ghi nhận dấu vết nghiệp vụ.

Publisher không cần biết ba module tiêu thụ tồn tại hay có bao nhiêu listener. Các module nhận biết sự kiện thông qua **hợp đồng event** được công khai từ module phát hành.

~~~mermaid
flowchart LR
    A["orders<br/>Tạo đơn thành công"] -->|"publish OrderPlaced"| E(("Spring<br/>Application Event"))
    E --> N["notifications<br/>Gửi thông báo"]
    E --> L["loyalty<br/>Cộng điểm"]
    E --> U["audit<br/>Ghi lịch sử"]
~~~

Điểm cần nhớ: **application event của Spring là cơ chế sự kiện trong phạm vi ứng dụng**. Nó không mặc nhiên đi qua Kafka/RabbitMQ, không mặc nhiên chạy bất đồng bộ và không tự bảo đảm được giao lại sau khi ứng dụng dừng. Các thuộc tính này phụ thuộc vào loại listener và hạ tầng được cấu hình.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Diễn giải cấu trúc và ý nghĩa của một application event.
2. Phân biệt event với command, lời gọi service và thông điệp integration event.
3. Thiết kế event bất biến, đủ dữ liệu nhưng không lộ chi tiết nội bộ module.
4. Công bố sự kiện qua `ApplicationEventPublisher` và chọn loại listener theo ngữ nghĩa transaction.
5. Giải thích vì sao Spring Modulith bổ sung `@ApplicationModuleListener` và Event Publication Registry.
6. Xác định giới hạn về retry, tính nhất quán, thứ tự xử lý và idempotency.
7. Kiểm thử và quan sát luồng sự kiện theo ranh giới nghiệp vụ.

## 2. Event thể hiện sự thật nghiệp vụ, không phải mệnh lệnh

Cách đặt tên giúp phân biệt ý định:

| Tên | Loại | Ý nghĩa |
| --- | --- | --- |
| `PlaceOrder` | Command | Yêu cầu hệ thống tạo đơn hàng. |
| `OrderPlaced` | Event | Đơn hàng đã được tạo. |
| `SendOrderConfirmation` | Command | Yêu cầu một thành phần gửi xác nhận. |
| `PaymentCompleted` | Event | Thanh toán đã hoàn thành. |
| `CancelOrder` | Command | Yêu cầu hủy đơn hàng. |
| `OrderCancelled` | Event | Đơn hàng đã được hủy. |

**Command** thường có bên chịu trách nhiệm thực hiện và trả lời thành công/thất bại. **Event** mô tả một sự thật đã được xác lập và có thể được nhiều bên quan tâm xử lý. Vì vậy nên đặt tên event theo hành động đã xảy ra, chẳng hạn `OrderPlaced`, thay vì `SendEmailEvent`: cách đặt tên thứ hai gắn event với tác vụ của consumer.

Ví dụ luồng nghiệp vụ:

~~~text
Khách hàng --> PlaceOrder (command)
  orders --> kiểm tra quy tắc và lưu đơn
  orders --> OrderPlaced (event)
    notifications --> gửi xác nhận
    loyalty       --> xét điều kiện cộng điểm
    audit         --> lưu nhật ký
~~~

Không phải mọi thao tác đều nên dùng event. Nếu cần kết quả tức thì để quyết định một giao dịch có được tiếp tục, lời gọi đồng bộ qua API công khai hoặc quy trình điều phối rõ ràng thường thích hợp hơn.

### Sự kiện ứng dụng, sự kiện miền và sự kiện tích hợp

Đây là các **khái niệm thiết kế** có thể chồng lấn, không phải ba lớp sự kiện Java bắt buộc tách riêng:

| Khái niệm | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Domain event** | Sự thật có ý nghĩa trong mô hình nghiệp vụ. | `OrderPlaced` khẳng định đơn hàng được tạo. |
| **Application event** | Cơ chế công bố và tiếp nhận thông tin trong một ứng dụng Spring. | Đối tượng `OrderPlaced` được gửi qua `ApplicationEventPublisher`. |
| **Integration event** | Hợp đồng phục vụ trao đổi giữa các hệ thống hoặc tiến trình. | Thông điệp `OrderPlacedV1` chuyển qua broker cho dịch vụ vận chuyển. |

Một `OrderPlaced` có thể vừa là domain event xét theo ngữ nghĩa, vừa là application event xét theo cách công bố trong Spring. Nếu cần đưa ra ngoài tiến trình, cần thiết kế hợp đồng tích hợp, serialisation, versioning và cơ chế vận chuyển tương ứng; **không suy ra việc phát ra broker chỉ vì đã gọi `publishEvent`**.

## 3. Mô hình dữ liệu của một event

Một event tốt nên là một **giá trị bất biến** mô tả sự kiện trong quá khứ. `record` của Java phù hợp với dạng dữ liệu này:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {
}
~~~

Ý nghĩa từng thành phần:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `eventId` | Định danh duy nhất của sự kiện. | Hữu ích khi log, trace và chống xử lý trùng. |
| `orderId` | Định danh đối tượng nghiệp vụ liên quan. | Consumer có thể liên hệ tới đúng đơn hàng. |
| `customerId` | Dữ liệu liên quan cần thiết cho trường hợp sử dụng. | Chỉ đưa vào khi có lý do rõ ràng; tránh thông tin nhạy cảm không cần thiết. |
| `occurredAt` | Thời điểm sự việc nghiệp vụ diễn ra. | Khác với thời điểm listener nhận hoặc xử lý event. |

Không phải event nào cũng bắt buộc có đúng bốn trường này. Một event tối giản có thể chỉ gồm `orderId`; hệ thống cần idempotency hoặc theo dõi nhiều lần thay đổi trạng thái có thể bổ sung `eventId`, version hay timestamp theo yêu cầu.

### Các đặc tính mong muốn

- **Bất biến sau khi phát:** listener khác nhau đọc cùng một thông tin, không thể sửa nội dung để ảnh hưởng lẫn nhau.
- **Tên và ngữ nghĩa rõ ràng:** `OrderPlaced` chỉ được công bố khi điều kiện tạo đơn đã được thỏa mãn theo nghiệp vụ.
- **Đủ dữ liệu cần thiết:** consumer không buộc phải truy cập trực tiếp repository nội bộ của publisher.
- **Payload nhỏ và ổn định:** không truyền đối tượng JPA entity, lazy proxy hay toàn bộ đồ thị aggregate.
- **An toàn để lưu/phát lại:** tránh tham chiếu tới kết nối, luồng, Spring bean hoặc đối tượng không thể serialise nếu dùng persistent registry.
- **Có định danh phục vụ đối soát:** khi nghiệp vụ có nguy cơ xử lý trùng, dùng một khóa nghiệp vụ ổn định hoặc `eventId` nhất quán.

Lựa chọn field là một phần thiết kế hợp đồng. Việc thêm/bỏ/đổi kiểu field có thể ảnh hưởng đến tất cả listener và các event còn được lưu để xử lý lại.

### Event đại diện cho một thời điểm

Giả sử đơn hàng được tạo lúc 10:00 và sửa địa chỉ lúc 10:05. Listener xử lý `OrderPlaced` lúc 10:07. Nếu listener chỉ có `orderId` rồi đọc entity hiện tại, dữ liệu nó thấy có thể khác dữ liệu tại thời điểm tạo đơn. Điều này không nhất thiết sai: nhiều consumer chỉ cần trạng thái mới nhất. Nhưng nếu cần lịch sử chính xác, event phải chứa dữ liệu bất biến của thời điểm xảy ra hoặc sử dụng cơ chế snapshot/version được thiết kế cụ thể.

**Câu hỏi thiết kế:** consumer cần biết *sự kiện đã xảy ra* hay cần *ảnh chụp trạng thái tại thời điểm xảy ra*? Trả lời câu hỏi này trước khi chọn payload.

## 4. Nơi sở hữu event và ranh giới module

Với Spring Modulith theo cấu hình phát hiện module mặc định, mỗi package con trực tiếp dưới package ứng dụng có thể là một application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── events/
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal/
│       └── OrderService.java
├── notifications/
│   └── internal/
│       └── OrderPlacedListener.java
└── loyalty/
    └── internal/
        └── LoyaltyListener.java
~~~

`orders` là chủ sở hữu của `OrderPlaced`, vì orders quyết định khi nào một đơn được tạo. Listener đặt ở module **chịu trách nhiệm phản ứng**, chẳng hạn notifications hoặc loyalty.

Nếu event ở package con `orders.events`, có thể khai báo một **named interface** để công khai hợp đồng:

~~~java
// File: com/example/shop/orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Module notifications có thể giới hạn phụ thuộc được phép trong `notifications/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.notifications;
~~~

Lúc đó consumer phụ thuộc vào `OrderPlaced` qua hợp đồng được công bố, chứ không truy cập `orders.internal.OrderRepository` hoặc `orders.internal.OrderService`.

Nếu module rất nhỏ, cũng có thể đặt `OrderPlaced` trực tiếp vào package gốc `orders`, vốn thuộc API mặc định của module. Named interface là lựa chọn có chủ đích khi cần tách rõ các nhóm hợp đồng.

## 5. Cơ chế Spring Application Event

Spring cung cấp hai thành phần chính:

- **`ApplicationEventPublisher`**: interface để công bố một event.
- **`@EventListener`** và các biến thể listener: nhận sự kiện theo loại đối tượng và cấu hình tương ứng.

Một event Spring không nhất thiết phải kế thừa `ApplicationEvent`: có thể công bố một đối tượng Java thông thường, ví dụ `record OrderPlaced`.

~~~java
applicationEventPublisher.publishEvent(
        new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                customerId,
                Instant.now()
        )
);
~~~

Bản thân `publishEvent` là tín hiệu công bố để cơ sở hạ tầng Spring xử lý. **Không nên diễn giải giá trị trả về của hàm này như một cam kết rằng mọi consumer đã xử lý thành công.** Thời điểm thực thi, đồng bộ/bất đồng bộ và xử lý lỗi phụ thuộc loại listener, transaction và cấu hình event multicaster.

### Luồng cơ bản với listener đồng bộ

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API
    participant O as OrdersService
    participant P as ApplicationEventPublisher
    participant L as @EventListener

    C->>O: placeOrder()
    O->>P: publishEvent(OrderPlaced)
    P->>L: on(OrderPlaced)
    L-->>P: Hoàn tất xử lý
    P-->>O: Trả về
    O-->>C: orderId
~~~

Sơ đồ trên mô tả cấu hình Spring mặc định với **`@EventListener` đồng bộ**, không phải hành vi chung của mọi listener. Trong trường hợp này, listener có thể chạy ngay trong lời gọi publish và lỗi của listener có thể lan ngược tới publisher.

Ví dụ:

~~~java
package com.example.shop.audit.internal;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    @EventListener
    void on(OrderPlaced event) {
        System.out.println("Order created: " + event.orderId());
    }
}
~~~

Dùng `@EventListener` thuần có thể phù hợp khi cần phản ứng ngay trong tiến trình và hiểu rõ tác động của lỗi đến transaction. Không nên làm một tác dụng phụ khó hoàn tác (ví dụ gửi email thật) trong listener đồng bộ chạy trước khi transaction tạo đơn commit.

## 6. Ví dụ hoàn chỉnh: từ nghiệp vụ tạo đơn đến sự kiện

### 6.1. Publisher nằm trong module orders

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderPlaced;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public UUID placeOrder(CreateOrderRequest request) {
        Order order = Order.create(request);
        orders.save(order);

        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now()
        );

        publisher.publishEvent(event);
        return order.getId();
    }
}
~~~

`OrderRepository`, `Order` và `CreateOrderRequest` là các kiểu nghiệp vụ cần được định nghĩa trong dự án thật; đoạn mã minh họa vị trí và cách phối hợp publish với transaction.

Điều quan trọng:

1. **`OrderService` quyết định phát event** sau khi đã thực hiện thao tác tạo đơn hợp lệ.
2. Event được phát trong phương thức có `@Transactional` và gắn với tiến trình lưu đơn.
3. Module orders không cần import `NotificationService` hay `LoyaltyService`.
4. Nếu transaction tạo đơn rollback, các listener **chỉ chạy sau commit** sẽ không xử lý event của transaction đó.

Chú ý mục 4 không áp dụng cho `@EventListener` đồng bộ thông thường: listener loại này có thể đã chạy trước khi transaction rollback.

### 6.2. Listener sau commit ở module notifications

~~~java
package com.example.shop.notifications.internal;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final NotificationService notificationService;

    OrderPlacedListener(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        notificationService.sendConfirmation(
                event.eventId(),
                event.orderId(),
                event.customerId()
        );
    }
}
~~~

`NotificationService` là service của module notifications, có thể sử dụng email gateway hoặc kênh thông báo khác. API của nó trong ví dụ chỉ là minh họa, cần bổ sung implementation và quản lý idempotency.

`@ApplicationModuleListener` được Spring Modulith thiết kế cho giao tiếp giữa các module: listener hoạt động **bất đồng bộ**, xử lý sau khi transaction phát hành commit, và có transaction riêng cho phần xử lý của nó.

Do đó, trong ví dụ này, tạo đơn thành công không đồng nghĩa email đã được gửi xong tại thời điểm `placeOrder()` trả về. Cách hiểu đúng là đơn hàng đã được xác lập và các hành vi hậu xử lý có thể đang diễn ra.

### 6.3. Một event có nhiều consumer

Module loyalty có thể đăng ký listener khác:

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyListener {

    private final LoyaltyService loyaltyService;

    LoyaltyListener(LoyaltyService loyaltyService) {
        this.loyaltyService = loyaltyService;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        loyaltyService.awardPointsForOrder(
                event.eventId(), event.orderId()
        );
    }
}
~~~

Thêm loyalty không làm thay đổi `OrderService`. Tuy nhiên, thứ tự xử lý giữa listener notifications và loyalty **không được ngầm xem là cố định**, đặc biệt khi chúng chạy bất đồng bộ. Không dùng thứ tự listener để mô hình hóa một chuỗi nghiệp vụ bắt buộc.

## 7. Chọn loại listener theo yêu cầu transaction

Ba cách thường gặp:

| Cơ chế | Khi nào xử lý? | Đặc tính cần lưu ý |
| --- | --- | --- |
| `@EventListener` | Thông thường ngay khi event được công bố, đồng bộ với lời gọi publish theo cấu hình mặc định. | Có thể chạy khi transaction chưa commit; exception có thể ảnh hưởng publisher. |
| `@TransactionalEventListener` | Theo phase của transaction, mặc định `AFTER_COMMIT`. | Listener chỉ được kích hoạt khi transaction đi qua phase tương ứng; nếu không có transaction, mặc định không chạy. |
| `@ApplicationModuleListener` | Sau commit, bất đồng bộ, với transaction riêng. | Phù hợp tác vụ hậu xử lý giữa các module; cần quan sát lỗi, retry và idempotency. |

Có thể chỉ rõ phase bằng Spring Framework:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void on(OrderPlaced event) {
    // Chỉ được kích hoạt sau commit của transaction phát hành.
}
~~~

Các phase thường gặp của `@TransactionalEventListener` gồm `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`. Không nên hiểu `AFTER_COMMIT` là một transaction ghi cơ sở dữ liệu mới tự động: việc ghi dữ liệu ở listener sau commit cần transaction riêng phù hợp, vì transaction gốc đã kết thúc về mặt commit.

**Trường hợp không có transaction:** theo mặc định, `@TransactionalEventListener` không xử lý event nếu không có transaction hoạt động; `fallbackExecution = true` có thể thay đổi hành vi này khi có lý do cụ thể. Đây là nguồn gây nhầm lẫn khi test một publisher không được chạy dưới transaction.

### Câu chuyện rollback

Giả sử `placeOrder()` lưu đơn, phát `OrderPlaced`, rồi ném exception làm transaction rollback:

- Một `@EventListener` đồng bộ **có thể đã chạy**, vì nó được gọi ngay khi publish.
- `@TransactionalEventListener(AFTER_COMMIT)` **không xử lý** event của transaction đã rollback.
- `@ApplicationModuleListener` cũng chỉ xử lý khi transaction phát hành commit thành công theo cơ chế trên.

Vì vậy, với việc gửi email xác nhận đơn đã lưu, chọn listener sau commit sẽ sát nghĩa nghiệp vụ hơn.

## 8. Đường đi của sự kiện trong Spring Modulith

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as Khách hàng
    participant Orders as orders
    participant DB as CSDL orders
    participant Registry as Publication Registry
    participant Notify as notifications
    participant Loyalty as loyalty

    Client->>Orders: placeOrder()
    Orders->>DB: Lưu đơn trong transaction
    Orders->>Registry: Theo dõi publication nếu đã cấu hình registry
    Note over Orders,Registry: Công bố OrderPlaced trong transaction
    Orders->>DB: Commit transaction
    Orders-->>Client: orderId
    par Các listener độc lập sau commit
        Registry-->>Notify: Deliver OrderPlaced
        Notify->>Notify: Gửi thông báo
        Notify-->>Registry: Hoàn tất nếu thành công
    and
        Registry-->>Loyalty: Deliver OrderPlaced
        Loyalty->>Loyalty: Ghi điểm
        Loyalty-->>Registry: Hoàn tất nếu thành công
    end
~~~

Sơ đồ là mô hình **logic** khi cấu hình cơ chế registry/lưu trữ phù hợp. Cách giao event nội bộ và thứ tự kỹ thuật chính xác còn phụ thuộc phiên bản, transaction manager và cấu hình; registry không phải một message broker.

Ở mô hình này, có hai kiểu thành công cần tách biệt:

- **Thành công nghiệp vụ gốc:** transaction tạo đơn đã commit.
- **Thành công xử lý phụ trợ:** từng listener đã hoàn tất phần việc của mình.

Một listener thất bại sau commit không làm đơn hàng đã commit biến mất. Điều này tạo điều kiện cho module tách biệt, đồng thời buộc ứng dụng phải có cách kiểm tra và khôi phục các tác vụ hậu xử lý quan trọng.

## 9. Event Publication Registry và ranh giới độ tin cậy

Spring Modulith bổ sung **Event Publication Registry** để theo dõi việc công bố sự kiện đến các **transactional event listener**. Với backend lưu trữ được cấu hình, registry có thể ghi nhận publication chưa hoàn tất và đánh dấu hoàn tất khi listener xử lý thành công.

Ví dụ cần phân biệt bốn mức:

| Mức | Điều có thể kỳ vọng | Điều không được suy ra |
| --- | --- | --- |
| `publishEvent` đơn thuần | Spring phát event tới cơ chế listener trong ứng dụng. | Sự kiện chắc chắn được lưu bền vững hoặc listener đã chạy xong. |
| Listener sau commit | Tránh thực hiện tác vụ hậu xử lý khi transaction phát hành rollback. | Tác vụ đó chắc chắn thành công một lần duy nhất. |
| Registry có persistence | Có trạng thái publication để kiểm tra và hỗ trợ recovery theo cấu hình. | Bất kỳ lỗi ngoài tiến trình nào cũng tự được xử lý mà không cần chính sách. |
| Listener có idempotency | Có thể từ chối hoặc bỏ qua tác dụng phụ đã thực hiện trước đó. | Mọi hệ thống bên ngoài đều hỗ trợ giao dịch nguyên tử. |

### Vì sao vẫn cần idempotency?

Xét kịch bản:

1. Orders commit đơn hàng và publication được ghi nhận.
2. Listener notifications gửi email thành công.
3. Ứng dụng dừng trước khi publication được đánh dấu hoàn tất.
4. Sau khi khôi phục, publication còn dang dở có thể được phát lại.
5. Nếu thiếu chống trùng, khách hàng nhận hai email.

Với loyalty, cùng lỗi có thể gây **cộng điểm hai lần**, ảnh hưởng trực tiếp tài sản của khách hàng. Consumer phải có một khóa nhất quán để kiểm tra lần xử lý trước, ví dụ:

~~~text
deduplication key = (consumer_name, event_id)

notifications : (send-order-confirmation, eventId)
loyalty       : (award-points, eventId)
~~~

Khi thiết kế idempotency trong cơ sở dữ liệu, nên dùng unique constraint hoặc cơ chế ghi nhận nguyên tử thích hợp. Nếu tác dụng phụ ở dịch vụ ngoài (email, webhook, thanh toán), cần xem dịch vụ đó có hỗ trợ idempotency key hay không; ghi nhận trong database riêng và gọi dịch vụ ngoài vẫn có cửa sổ lỗi cần tính đến.

**Registry không đồng nghĩa với bảo đảm exactly-once cho mọi tác dụng phụ.** Có thể phải xử lý lại event, do đó consumer cần chịu được việc giao trùng.

### Retry và recovery

Một số lỗi chỉ tạm thời: timeout, kết nối tới SMTP thất bại, downstream overload. Các lỗi khác là lỗi dữ liệu hoặc hợp đồng không thể tự hồi phục.

Khi ứng dụng triển khai retry/recovery cần xác định:

- Lỗi nào được thử lại và lỗi nào cần can thiệp thủ công?
- Có giới hạn số lần, khoảng chờ và backoff không?
- Sau khởi động lại, ai kích hoạt xử lý những publication chưa hoàn tất?
- Làm sao tra cứu từng publication, event ID, listener và lỗi gần nhất?
- Tác dụng phụ có idempotent để an toàn khi replay không?

Cơ chế phát lại publication cụ thể phụ thuộc các tùy chọn Spring Modulith và persistence được cấu hình. Không coi việc chỉ thêm annotation vào listener là đã có đầy đủ chiến lược retry đáng tin cậy.

## 10. Thứ tự, độ trễ và tính nhất quán

Sự kiện trong Spring Modulith mở đường cho **eventual consistency** giữa các module khi dùng listener bất đồng bộ sau commit.

Ví dụ: đơn hàng vừa được tạo, API trả `orderId`, nhưng thông báo chưa gửi hoặc điểm thưởng chưa được ghi ngay. Nếu giao diện yêu cầu trạng thái, có thể hiển thị:

~~~text
Order: CREATED
Confirmation: PENDING
Loyalty points: PENDING
~~~

Sau khi các listener hoàn tất, trạng thái phụ trợ có thể chuyển thành `SENT` và `AWARDED`. Đây chỉ là cách mô hình trạng thái gợi ý; hệ thống thực tế có thể lưu các trạng thái này tại module sở hữu từng hành vi.

Những giả định dễ gây lỗi:

1. **Mọi listener chạy theo thứ tự khai báo:** sai với xử lý bất đồng bộ; không xây logic dựa vào điều này.
2. **Event sẽ không bao giờ bị lặp:** có thể sai khi retry, replay hoặc publisher phát lại.
3. **Event luôn đến ngay tức thì:** có thể có độ trễ do thread pool, lỗi phụ thuộc hoặc recovery.
4. **Publisher biết consumer đã thành công:** với listener sau commit bất đồng bộ, kết quả xử lý có vòng đời riêng.
5. **Một event thay thế được transaction xuyên module:** event chỉ mang thông tin, không tự tạo atomic transaction cho nhiều thao tác độc lập.

Nếu nghiệp vụ yêu cầu chuỗi ràng buộc như “thanh toán xong mới giao hàng”, có thể dùng các event trạng thái và module điều phối rõ ràng, nhưng phải thiết kế quy trình, trạng thái và cơ chế bù trừ phù hợp; không dựa vào thứ tự chạy ngẫu nhiên của listener.

## 11. Kiểm thử sự kiện ứng dụng

Một chương trình kiểm thử tốt cần kiểm tra **publisher**, **consumer**, **transaction semantics** và **tình huống lỗi**.

### 11.1. Kiểm thử publisher

Spring Modulith hỗ trợ `@ApplicationModuleTest` để chạy kiểm thử theo phạm vi module và `PublishedEvents` để quan sát event đã được phát.

Ví dụ minh họa:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderEventTests {

    @Autowired
    OrderService orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        // Giả sử fixture đã chuẩn bị yêu cầu hợp lệ trong test.
        var request = TestOrders.validCreateRequest();
        var orderId = orders.placeOrder(request);

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }
}
~~~

`TestOrders` là fixture minh họa, cần định nghĩa trong mã kiểm thử của dự án. Phần `PublishedEvents` xác minh sự kiện đúng loại chứa đúng `orderId`; bài test này **không tự chứng minh** rằng các listener bất đồng bộ đã xử lý hoàn tất.

Khi đơn hàng phải commit, có thể kết hợp kiểm thử transaction để xác nhận event đi kèm trạng thái nghiệp vụ hợp lệ.

### 11.2. Kiểm thử consumer

Kiểm thử listener của notifications nên xác minh:

- Event hợp lệ tạo đúng yêu cầu gửi thông báo.
- Cùng event được giao lại không tạo tác dụng phụ trùng.
- Lỗi downstream được ghi nhận và publication không bị đánh dấu hoàn tất giả.
- Listener không cần import service/repository nội bộ của orders.

Với listener bất đồng bộ, dùng cơ chế chờ có điều kiện hoặc kiểm thử thích hợp; không dùng một khoảng sleep tùy ý rồi mặc định đã xử lý xong.

### 11.3. Kiểm thử rollback và recovery

Hai tình huống có giá trị cao:

- **Rollback:** nghiệp vụ tạo đơn phát event nhưng transaction thất bại; listener sau commit không được tạo tác dụng phụ.
- **Partial failure:** listener thực hiện một phần công việc rồi lỗi; phát lại phải cho ra kết quả nghiệp vụ hợp lệ, không nhân đôi tác dụng phụ.

Nếu dùng Event Publication Registry, cần kiểm tra trực tiếp trạng thái publication với persistence thực tế, rồi xác minh cơ chế recovery được lựa chọn. Không chỉ mock `ApplicationEventPublisher` và suy ra mức bảo đảm giao sự kiện.

### 11.4. Kiểm tra ranh giới module

Có thể bổ sung kiểm thử kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTest {

    @Test
    void verifiesDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm thử này giúp phát hiện việc một module import vào package nội bộ không được phép của module khác. Event contract phải ở API được công khai phù hợp; thay đổi Java visibility không đủ để quyết định ranh giới kiến trúc.

## 12. Quan sát sự kiện trong vận hành

Khi xảy ra lỗi “đơn đã tạo nhưng không nhận được email”, log chỉ có `OrderService.placeOrder` là chưa đủ. Cần có dữ liệu nối từ publisher đến từng consumer:

| Tín hiệu | Câu hỏi có thể trả lời |
| --- | --- |
| `eventId`, `eventType`, `orderId` | Đang nói về sự kiện của đơn nào? |
| `publisherModule` | Module nào tạo event? |
| `listenerName` / consumer | Consumer nào đã xử lý hoặc còn tồn đọng? |
| Thời điểm publish, bắt đầu và kết thúc | Event bị chậm ở công đoạn nào? |
| Số lần thử, exception, trạng thái hoàn tất | Sự kiện lỗi hay đang retry? |
| Số publication chưa hoàn tất | Có backlog bất thường hay không? |

Log mẫu do ứng dụng tự thiết kế:

~~~text
event=OrderPlaced eventId=e-123 orderId=o-123 publisher=orders status=PUBLISHED
event=OrderPlaced eventId=e-123 listener=notifications status=FAILED attempt=1
event=OrderPlaced eventId=e-123 listener=notifications status=COMPLETED attempt=2
event=OrderPlaced eventId=e-123 listener=loyalty status=COMPLETED attempt=1
~~~

Đây là **định dạng minh họa**, không phải output tự động mặc định của Spring Modulith. Có thể tích hợp logging, metrics, tracing hoặc công cụ quan sát module tùy hệ thống. Cần tránh ghi payload chứa dữ liệu nhạy cảm vào log chỉ để thuận tiện gỡ lỗi.

Thực tế nên cảnh báo khi publication chưa hoàn tất quá lâu, số lần retry tăng liên tục hoặc consumer có độ trễ bất thường. Mục tiêu là nhìn thấy **trạng thái xử lý của từng listener**, thay vì chỉ biết publisher đã gọi `publishEvent`.

## 13. Các sai lầm phổ biến

### 13.1. Dùng event để gọi một hành động cụ thể

~~~java
publisher.publishEvent(new SendEmailToCustomer(...));
~~~

Tên này mô tả một yêu cầu thực thi, không mô tả sự thật nghiệp vụ. Nếu nhiều module cần phản ứng khi đặt hàng, sử dụng `OrderPlaced` giúp các consumer tự quyết định hành vi. Dù vậy, command dưới dạng message có thể vẫn hợp lý trong các mô hình messaging khác; điều quan trọng là hiểu đúng ý nghĩa và trách nhiệm.

### 13.2. Truyền entity còn quản lý bởi JPA

~~~java
publisher.publishEvent(new OrderPlaced(orderEntity));
~~~

Khi consumer xử lý sau commit hoặc trên luồng khác, entity có thể đã detached, trường lazy không truy cập được hoặc trạng thái đã thay đổi. Nên công bố DTO/record bất biến với dữ liệu cần thiết.

### 13.3. Gửi email trong listener đồng bộ trước commit

Nếu transaction rollback sau khi email được gửi, khách hàng nhận xác nhận cho đơn không tồn tại. Dùng listener sau commit khi tác vụ chỉ hợp lệ sau khi nghiệp vụ chính hoàn tất.

### 13.4. Không có chính sách xử lý lỗi

Vì publisher ít phụ thuộc consumer hơn, sự cố của consumer có thể khó phát hiện nếu thiếu quan sát. Cần ghi nhận publication, định nghĩa retry/recovery và cảnh báo các event tồn đọng khi đó là tác vụ quan trọng.

### 13.5. Nhầm event với bảo đảm xử lý đúng một lần

Retry có thể phát lại cùng event. Idempotency thuộc trách nhiệm consumer và hệ thống tích hợp; không được suy ra exactly-once chỉ từ `@ApplicationModuleListener` hoặc registry.

### 13.6. Sửa event contract không đánh giá bên nghe

Event là API giữa module. Đổi tên trường hoặc thay đổi ý nghĩa `occurredAt` có thể phá vỡ listener và những publication được lưu từ phiên bản cũ. Cần xem consumer, phương thức serialize của persistence và kịch bản nâng cấp trước khi thay đổi.

## 14. Bài thực hành đề xuất

Xây dựng luồng **xác nhận đơn hàng** gồm `orders`, `notifications` và `loyalty`:

1. Khai báo record `OrderPlaced(eventId, orderId, customerId, occurredAt)` trong API module `orders`.
2. Từ service `placeOrder()` trong transaction, lưu đơn và công bố event qua `ApplicationEventPublisher`.
3. Viết hai `@ApplicationModuleListener`, một để gửi thông báo và một để cộng điểm.
4. Kiểm tra transaction rollback: không được gửi xác nhận cho đơn bị rollback.
5. Cố tình cho listener gửi thông báo thất bại, quan sát trạng thái publication nếu đã cấu hình registry.
6. Thực hiện phát lại theo cơ chế recovery của ứng dụng và kiểm tra idempotency.
7. Viết kiểm thử module cho publisher/consumer và kiểm tra phụ thuộc bằng `ApplicationModules.verify()`.

Trả lời các câu hỏi sau:

- Một event vừa là domain event vừa là application event được không? Vì sao?
- Vì sao `@EventListener` và `@ApplicationModuleListener` có thể cho kết quả khác nhau khi transaction rollback?
- Tại sao `publishEvent` hoàn tất không đồng nghĩa tất cả consumer đã hoàn tất?
- Nếu email gửi thành công nhưng chưa đánh dấu publication hoàn tất, lúc replay cần làm gì?
- Nếu loyalty phải đợi notifications xong mới được cộng điểm, có nên dựa vào thứ tự listener không? Phải thiết kế lại luồng thế nào?

**Ghi nhớ:** Application event là một **hợp đồng thông báo sự thật đã xảy ra** được Spring công bố và phân phối trong tiến trình ứng dụng. Spring Modulith khai thác cơ chế này để các module giao tiếp qua ranh giới nghiệp vụ rõ ràng: publisher sở hữu sự kiện, consumer tự phản ứng. Muốn giao sự kiện đáng tin cậy cần kết hợp thiết kế event bất biến, listener đúng transaction, registry/persistence khi cần, retry có kiểm soát, idempotency, kiểm thử và observability.

