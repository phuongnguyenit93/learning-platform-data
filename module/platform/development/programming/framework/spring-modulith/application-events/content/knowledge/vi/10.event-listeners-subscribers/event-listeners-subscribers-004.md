# Đăng ký listener trong Spring Modulith Application Events

## 1. Đăng ký listener là gì?

Trong một ứng dụng Spring Boot, **event listener** là thành phần nhận thông báo khi một application event được công bố. Với Spring Modulith, listener còn đóng vai trò **subscriber của một sự kiện nghiệp vụ đến từ module khác**: module phát hành chỉ công bố sự kiện, còn module đăng ký listener tự xử lý phần việc thuộc trách nhiệm của mình.

Ví dụ, khi module `orders` tạo đơn thành công, nó phát `OrderPlaced`. Module `notifications` cần gửi email xác nhận, module `loyalty` cần tính điểm. Mỗi module tự đăng ký listener cho `OrderPlaced` mà không yêu cầu `orders` gọi service của chúng.

~~~mermaid
flowchart LR
    P["orders<br/>ApplicationEventPublisher"] --> E(("OrderPlaced"))
    E --> N["notifications<br/>@ApplicationModuleListener"]
    E --> L["loyalty<br/>@ApplicationModuleListener"]
    E --> A["audit<br/>@EventListener"]
~~~

Cần phân biệt ba khâu:

1. **Định nghĩa event contract:** kiểu dữ liệu và ý nghĩa của `OrderPlaced`.
2. **Đăng ký listener:** để Spring phát hiện một bean có phương thức xử lý `OrderPlaced`.
3. **Công bố event:** publisher gọi `ApplicationEventPublisher.publishEvent(...)` để hạ tầng Spring giao tới các listener phù hợp.

Trong trường hợp dùng annotation, **việc đăng ký thường là khai báo phương thức trên một Spring bean**, không phải tự gọi `subscribe("OrderPlaced", callback)` hay viết danh sách listener trong `OrderService`.

Bài này thuộc chương **Listener và subscriber** của `SPRING_MODULITH_APPLICATION_EVENTS`, tập trung vào thao tác đăng ký listener đúng cách, cách chọn annotation theo transaction, bảo vệ ranh giới module và những điều kiện cần để tiếp nhận, retry, kiểm thử, quan sát sự kiện đáng tin cậy.

## 2. Spring phát hiện và kết nối listener như thế nào?

Với cách đăng ký bằng annotation, Spring xử lý hai trách nhiệm riêng:

- **Bean registration:** tạo một bean trong `ApplicationContext` qua component scanning hoặc khai báo `@Bean`.
- **Event listener registration:** cơ chế xử lý annotation event của Spring nhận diện các phương thức `@EventListener` (và các annotation tương ứng) trên bean, đăng ký phương thức phù hợp để được gọi khi event được publish.

~~~mermaid
sequenceDiagram
    autonumber
    participant Boot as Spring Boot
    participant Ctx as ApplicationContext
    participant Listener as Bean OrderPlacedListener
    participant Publisher as OrderService

    Boot->>Ctx: Khởi tạo context, scan cấu hình
    Ctx->>Listener: Tạo bean
    Ctx->>Ctx: Nhận diện phương thức có annotation listener
    Publisher->>Ctx: publishEvent(new OrderPlaced(...))
    Ctx-->>Listener: Giao event theo kiểu và chính sách listener
~~~

Nếu một lớp có `@EventListener` nhưng **không trở thành Spring bean**, phương thức đó thông thường sẽ không được Spring đăng ký làm listener. Tương tự, nếu bean nằm ngoài phạm vi component scan và không có cấu hình nhập vào context, Spring sẽ không phát hiện nó.

Ví dụ cơ bản:

~~~java
package com.acme.shop.audit.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    @EventListener
    void on(OrderPlaced event) {
        System.out.println("Placed order: " + event.orderId());
    }
}
~~~

`@Component` làm lớp trở thành ứng viên bean; `@EventListener` đánh dấu phương thức nhận sự kiện. Kiểu tham số `OrderPlaced` cho Spring biết loại sự kiện cần xử lý.

**Lưu ý:** ví dụ trên dùng `@EventListener` thông thường. Với cấu hình mặc định, phương thức này được gọi **đồng bộ khi publish**, có thể trước khi transaction tạo đơn commit. Đây chưa phải lựa chọn lý tưởng cho tác vụ gửi email sau commit.

## 3. Đặt listener trong module sở hữu hành vi phản ứng

Giả sử cấu trúc ứng dụng dùng package theo nghiệp vụ:

~~~text
com/acme/shop/
├── ShopApplication.java
├── orders/
│   ├── events/
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal/
│       ├── OrderService.java
│       └── OrderRepository.java
├── notifications/
│   ├── package-info.java
│   └── internal/
│       ├── OrderConfirmationListener.java
│       └── ConfirmationSender.java
├── loyalty/
│   ├── package-info.java
│   └── internal/
│       └── AwardPointsListener.java
└── audit/
    └── internal/
        └── OrderAuditListener.java
~~~

Với cấu hình phát hiện module mặc định, `orders`, `notifications`, `loyalty` và `audit` là các application module. Module `orders` **sở hữu sự thật `OrderPlaced`**, nên event contract thuộc API của `orders`. Module `notifications` **sở hữu việc gửi thông báo**, nên listener gửi email nằm trong module `notifications`.

Các module nhận sự kiện chỉ nên import **hợp đồng công khai**; không truy cập `orders.internal.OrderRepository` để sửa hoặc đọc dữ liệu nội bộ một cách tùy tiện.

Để xuất `orders.events` như named interface:

~~~java
// com/acme/shop/orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Để giới hạn phụ thuộc mà module `notifications` được phép dùng:

~~~java
// com/acme/shop/notifications/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.acme.shop.notifications;
~~~

`allowedDependencies` ở đây quy định **module notifications được phép phụ thuộc vào named interface events của orders**. Nó **không tự đăng ký listener**; việc đăng ký vẫn đến từ Spring bean và annotation listener.

Nếu event được đặt ngay tại package gốc `orders` (API mặc định của module), không cần `@NamedInterface` chỉ để sử dụng kiểu event đó. Cách tổ chức `orders.events` hữu ích khi module có nhiều nhóm API và muốn kiểm soát rõ quyền truy cập.

## 4. Xây dựng event contract để listener có thể nhận

Event không nhất thiết phải kế thừa `ApplicationEvent`. Một Java record chứa dữ liệu bất biến có thể dùng làm Spring application event:

~~~java
package com.acme.shop.orders.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

Các field trong ví dụ mang vai trò:

| Field | Nghĩa | Tại sao listener cần |
| --- | --- | --- |
| `eventId` | Định danh **lần xảy ra** sự kiện. | Trace, đối soát, chống xử lý trùng khi replay. |
| `orderId` | Định danh đơn hàng được tạo. | Liên kết tác vụ phụ với đơn hàng. |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra. | Dùng dữ kiện lịch sử, đo độ trễ xử lý. |

Các field `eventId` và `occurredAt` là lựa chọn thiết kế, **không phải yêu cầu bắt buộc của `ApplicationEventPublisher`**. Event tối giản `record OrderPlaced(UUID orderId) {}` cũng hợp lệ. Tuy nhiên nếu cần event publication registry, retry hoặc theo dõi nhiều consumer, một `eventId` ổn định thường rất có ích.

Tránh dùng entity JPA mutable làm event payload. Listener bất đồng bộ có thể chạy sau transaction tạo đơn, khi entity đã detached hoặc dữ liệu đã thay đổi. Nếu cần tên và giá đã chốt tại thời điểm mua, hãy thiết kế snapshot bất biến trong event thay vì để listener lấy dữ liệu nội bộ hoặc đọc giá hiện tại.

## 5. Publisher công bố sự kiện từ module orders

Phương thức nghiệp vụ có thể phát sự kiện sau khi tạo trạng thái hợp lệ:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand request) {
        Order order = Order.create(request);
        Order persisted = orders.save(order);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                persisted.getId(),
                clock.instant()
        ));
        return persisted.getId();
    }
}
~~~

`OrderRepository`, `Order` và `PlaceOrderCommand` là các kiểu nghiệp vụ minh họa cần được định nghĩa trong ứng dụng thực tế. Ví dụ cũng cần một `Clock` bean và giả định ID ổn định đã có sau khi lưu entity.

Điểm quan trọng: `OrderService` không import hoặc gọi `OrderConfirmationListener`. Publisher chỉ biết `ApplicationEventPublisher` và event contract thuộc module của mình. Thêm một consumer mới không đòi hỏi sửa lời gọi publish.

Với `@Transactional`, phương thức tạo đơn diễn ra trong transaction. Nếu dùng listener **sau commit**, listener chỉ phản ứng khi transaction đó commit thành công. Nhưng `publishEvent(...)` **không tự buộc tất cả listener chạy sau commit**: loại annotation trên listener quyết định hành vi tương ứng.

## 6. Cách 1 — Đăng ký bằng `@EventListener`

Đây là API cơ bản của Spring Framework:

~~~java
package com.acme.shop.audit.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class LogOrderPlaced {

    @EventListener
    void on(OrderPlaced event) {
        System.out.printf(
                "Order %s placed at %s%n",
                event.orderId(),
                event.occurredAt()
        );
    }
}
~~~

Khi Spring bean này đã được đăng ký trong `ApplicationContext`, listener có thể nhận `OrderPlaced` do ứng dụng publish.

### Đặc điểm của `@EventListener`

- Theo cấu hình mặc định, listener chạy **đồng bộ trong luồng công bố event**.
- Nếu publisher đang ở trong transaction, listener có thể chạy **trước khi transaction commit**.
- Exception của listener đồng bộ thông thường có thể lan ngược tới publisher, dẫn tới phương thức nghiệp vụ thất bại và transaction rollback.
- Nếu xử lý lâu, nó có thể làm tăng thời gian của lời gọi publisher.
- Có thể bổ sung `@Async` khi đã cấu hình xử lý bất đồng bộ phù hợp, nhưng **`@Async` không tự mang ngữ nghĩa after-commit**.

Vì vậy `@EventListener` thường phù hợp cho phản ứng nội bộ ngắn, cần chạy ngay và được thiết kế rõ quan hệ lỗi với publisher. Đối với gửi email hoặc gọi hệ thống ngoài chỉ hợp lệ sau khi đơn đã lưu, nên cân nhắc listener gắn với transaction.

### Listener có thể nhận nhiều kiểu event không?

Có thể khai báo nhiều phương thức, mỗi phương thức nhận một kiểu:

~~~java
@Component
class OrderAuditListener {

    @EventListener
    void onPlaced(OrderPlaced event) {
        // Audit việc tạo đơn hàng.
    }

    @EventListener
    void onCancelled(OrderCancelled event) {
        // Audit việc hủy đơn hàng.
    }
}
~~~

`OrderCancelled` là một hợp đồng khác do module orders công bố; đoạn mã chỉ minh họa cách đăng ký nhiều loại event trên một bean. Không cần `instanceof` hoặc tự dispatch theo tên chuỗi nếu có thể dùng các handler có tham số cụ thể.

## 7. Cách 2 — Đăng ký bằng `@TransactionalEventListener`

Nếu listener chỉ được chạy khi transaction tạo đơn **commit thành công**, Spring Framework cung cấp `@TransactionalEventListener`:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class SendOrderConfirmationAfterCommit {

    private final ConfirmationSender sender;

    SendOrderConfirmationAfterCommit(ConfirmationSender sender) {
        this.sender = sender;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        sender.sendForOrder(event.orderId());
    }
}
~~~

Trong ví dụ, listener không được kích hoạt ở phase `AFTER_COMMIT` nếu transaction phát hành rollback. **`AFTER_COMMIT` là phase mặc định** của `@TransactionalEventListener`; ghi rõ phase giúp người đọc nhận biết ý định.

Có những phase khác như `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Chọn phase theo ngữ nghĩa tác vụ; không phải event nào cũng cần cùng một phase.

### Có bắt buộc phải có transaction khi publish không?

Theo mặc định, **có** đối với `@TransactionalEventListener`. Nếu event được publish khi không có transaction đang hoạt động, listener transactional **không được kích hoạt** theo hành vi mặc định. Có thể cấu hình `fallbackExecution = true` khi có lý do rõ ràng, nhưng điều đó cũng thay đổi kỳ vọng về việc listener cần chờ commit.

Ví dụ rủi ro:

~~~java
// Nếu phương thức gọi không có transaction hoạt động,
// listener @TransactionalEventListener mặc định không chạy.
events.publishEvent(new OrderPlaced(
        UUID.randomUUID(), orderId, Instant.now()
));
~~~

Khi kiểm thử listener sau commit, cần xác minh transaction thực tế của publisher. Đặt `@Transactional` vào một phương thức bị gọi **nội bộ cùng object (self-invocation)** có thể không kích hoạt proxy transaction trong cơ chế AOP thông thường; chỉ nhìn annotation trên source là chưa đủ.

### Việc ghi DB trong listener sau commit

`AFTER_COMMIT` có nghĩa transaction phát hành **đã commit**. Đừng tự giả định listener sẽ có một transaction ghi dữ liệu mới. Khi listener cần lưu dữ liệu, hãy cấp một transaction riêng phù hợp, ví dụ gọi một service khác có `@Transactional(propagation = REQUIRES_NEW)`.

~~~java
@Service
class NotificationDeliveryService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordDelivery(UUID orderId) {
        // Ghi nhận trạng thái giao thông báo trong transaction mới.
    }
}
~~~

Đoạn minh họa yêu cầu import `Service`, `Transactional`, `Propagation`, `UUID` và repository tương ứng. `REQUIRES_NEW` hữu ích khi cần transaction độc lập, nhưng không làm side effect email bên ngoài trở thành một giao dịch nguyên tử cùng database.

## 8. Cách 3 — Đăng ký bằng `@ApplicationModuleListener`

Spring Modulith cung cấp `@ApplicationModuleListener` dành cho giao tiếp event giữa các application module.

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmationListener {

    private final ConfirmationSender sender;

    OrderConfirmationListener(ConfirmationSender sender) {
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        sender.sendForOrder(event.eventId(), event.orderId());
    }
}
~~~

`ConfirmationSender` là service nội bộ của module notifications, cần được cung cấp implementation trong ứng dụng thực tế.

Với cơ chế Spring Modulith, `@ApplicationModuleListener` là annotation kết hợp các ý nghĩa chính:

- **Transactional event listener:** phản ứng sau commit của transaction phát hành.
- **Asynchronous execution:** xử lý bất đồng bộ, tách khỏi request tạo đơn.
- **Transaction riêng:** sử dụng transaction riêng cho listener (thông qua cấu hình transaction của annotation, với propagation `REQUIRES_NEW`).

Lợi ích là module notifications có thể xử lý việc gửi thông báo mà không buộc transaction tạo đơn chờ kết quả gửi email. Nếu listener gặp lỗi sau khi transaction orders đã commit, lỗi đó **không rollback lại đơn hàng đã commit**.

Tuy nhiên `@ApplicationModuleListener` **không tự bảo đảm đã giao thành công hoặc chỉ có đúng một lần thực hiện side effect**. Việc lưu publication, replay và idempotency cần cơ chế hạ tầng và thiết kế riêng được nêu ở các phần sau.

### Một sự kiện, nhiều listener độc lập

Module loyalty có thể đăng ký cùng `OrderPlaced`:

~~~java
package com.acme.shop.loyalty.internal;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class AwardPointsListener {

    private final LoyaltyService loyalty;

    AwardPointsListener(LoyaltyService loyalty) {
        this.loyalty = loyalty;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        loyalty.awardForOrder(event.eventId(), event.orderId());
    }
}
~~~

Cả `OrderConfirmationListener` và `AwardPointsListener` cùng nhận loại event `OrderPlaced`, nhưng không nên giả định chúng chạy **đúng một thứ tự cố định**. Nếu loyalty chỉ được cộng điểm sau khi một nghiệp vụ khác hoàn tất, phải mô hình hóa sự kiện/trạng thái phụ thuộc đúng nghĩa, không dựa vào thứ tự xử lý giữa hai listener bất đồng bộ.

## 9. So sánh ba kiểu đăng ký listener

| Khía cạnh | `@EventListener` | `@TransactionalEventListener` | `@ApplicationModuleListener` |
| --- | --- | --- | --- |
| Nền tảng | Spring Framework | Spring Framework | Spring Modulith |
| Điều kiện transaction | Không bắt buộc | Mặc định cần transaction | Thiết kế cho transaction sau commit |
| Thời điểm xử lý | Thông thường ngay khi publish | Mặc định ở `AFTER_COMMIT` | Sau commit |
| Bất đồng bộ | Không mặc định; có thể cấu hình riêng | Không mặc định chỉ nhờ annotation này | Có ngữ nghĩa bất đồng bộ |
| Transaction mới cho xử lý | Không mặc định | Không mặc định | Có transaction riêng |
| Trường hợp phù hợp | Phản ứng đồng bộ, ngắn | Công việc gắn với phase của transaction | Hậu xử lý giao tiếp giữa module |
| Sai lầm phổ biến | Tưởng luôn sau commit | Publish ngoài transaction mà không nhận event | Tưởng có exactly-once side effects |

Đây là cách hành vi thường được sử dụng trong Spring Boot/Spring Modulith. Kết quả cụ thể còn phụ thuộc cấu hình Spring transaction, asynchronous execution, event multicaster và các hạ tầng liên quan.

**Không cần đặt cả `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener` lên cùng một handler.** Hãy chọn annotation phản ánh thời điểm và kiểu xử lý mong muốn, sau đó kiểm chứng bằng test transaction.

## 10. `@Component` và `@Bean`: hai cách tạo listener bean

Để annotation listener có hiệu lực, object chứa phương thức cần được Spring quản lý.

### Cách A. Component scanning

~~~java
@Component
class OrderConfirmationListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Xử lý sau commit.
    }
}
~~~

Nếu bean thuộc package được scan và dependency phù hợp, Spring sẽ tạo bean và đăng ký listener. Đây thường là cách gọn nhất.

### Cách B. Đăng ký tường minh bằng `@Bean`

Khi muốn quản lý rõ việc tạo object hoặc cấu hình dependency, có thể khai báo bean bằng `@Configuration`:

~~~java
package com.acme.shop.notifications.internal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class NotificationConfiguration {

    @Bean
    OrderConfirmationListener orderConfirmationListener(
            ConfirmationSender sender
    ) {
        return new OrderConfirmationListener(sender);
    }
}
~~~

Trong cách B, lớp `OrderConfirmationListener` vẫn chứa phương thức annotation listener nhưng **không cần thêm `@Component`**. Chọn một cơ chế đăng ký cho mỗi bean để tránh vô tình tạo **hai instance của cùng listener**, dẫn đến hành vi xử lý hai lần.

Ví dụ B giả định `OrderConfirmationListener` cùng package và có constructor nhận `ConfirmationSender`. Khi kết hợp các ví dụ, cần giữ một phương thức tạo bean thực sự, không copy cả A và B rồi bật đồng thời.

### Không tự tạo listener bằng `new` trong publisher

~~~java
// Không đúng với cách đăng ký listener qua Spring bean:
OrderConfirmationListener listener =
        new OrderConfirmationListener(sender);
events.publishEvent(event);
~~~

Nếu instance tự tạo không được đăng ký vào `ApplicationContext`, Spring không mặc nhiên biết nó là subscriber. Tách publisher khỏi quy trình tạo consumer chính là một lợi ích của application event.

## 11. Nhận event theo kiểu và cấu hình method

Với cách đơn giản nhất, **kiểu tham số của phương thức** quyết định loại event listener nhận:

~~~java
@EventListener
void on(OrderPlaced event) {
    // Nhận OrderPlaced.
}
~~~

Có thể đăng ký bằng cách khai báo loại event trong annotation, nhưng nếu đã dùng một tham số cụ thể thì thường không cần:

~~~java
@EventListener(classes = OrderPlaced.class)
void onOrderPlaced() {
    // Được kích hoạt cho OrderPlaced mà không nhận payload.
}
~~~

Kiểu không có tham số phù hợp nếu listener chỉ cần biết có event xảy ra. Khi cần xử lý theo `orderId`, nên dùng phương thức nhận `OrderPlaced` rõ ràng.

**Các lựa chọn cần hiểu đúng:**

- `@EventListener(condition = "...")` có thể lọc bằng biểu thức SpEL theo dữ liệu event. Nếu điều kiện sai, listener bị bỏ qua theo thiết kế.
- Một kiểu event kế thừa/triển khai kiểu cha có thể liên quan đến việc dispatch cho listener đăng ký kiểu cha; không nên mặc định chỉ có kết quả khớp tên class chính xác trong mọi trường hợp.
- `@Order` có thể ảnh hưởng thứ tự các listener đồng bộ trong phạm vi cơ chế dispatch tương ứng, nhưng **không phải bảo đảm thứ tự hoàn thành** giữa các listener bất đồng bộ.
- Với bean có Spring AOP proxy, cần bảo đảm phương thức listener có thể được hạ tầng truy cập và sử dụng qua proxy. Tránh phương thức `private`, lời gọi qua self-invocation hoặc kiểu bean/proxy không phù hợp khi trông chờ transaction/async behavior.

Đối với giao tiếp module, một phương thức rõ nghĩa như `on(OrderPlaced event)` thường dễ đọc và dễ kiểm thử hơn một listener tổng quát nhận `Object` rồi tự phân nhánh.

## 12. Vòng đời transaction khi một listener được đăng ký

Xét ví dụ đơn hàng:

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as Client
    participant Order as orders / publisher
    participant DB as Orders DB
    participant Event as Spring event infrastructure
    participant Notify as notifications / listener
    participant Loyalty as loyalty / listener

    Client->>Order: placeOrder()
    Order->>DB: Lưu đơn trong transaction
    Order->>Event: publishEvent(OrderPlaced)
    alt Transaction COMMIT
        Order->>DB: COMMIT
        Event-->>Notify: Kích hoạt listener sau commit
        Event-->>Loyalty: Kích hoạt listener sau commit
        Notify->>Notify: Gửi xác nhận
        Loyalty->>Loyalty: Cộng điểm
    else Transaction ROLLBACK
        Order->>DB: ROLLBACK
        Note over Notify,Loyalty: Không kích hoạt listener AFTER_COMMIT
    end
~~~

Sơ đồ là minh họa về **điều kiện kích hoạt**, không cam kết thời điểm chính xác của callback so với HTTP response hoặc thứ tự xử lý giữa notifications và loyalty.

Nếu cả hai listener đều `@ApplicationModuleListener`, những kết quả sau đều có thể xảy ra sau khi orders commit:

- Notifications thành công, loyalty thành công.
- Notifications lỗi, loyalty thành công.
- Notifications thành công, loyalty lỗi.
- Cả hai gặp lỗi phụ trợ.

Vì mỗi consumer có trách nhiệm riêng, **thành công của publisher không đồng nghĩa toàn bộ subscriber đã xử lý xong**. Việc đăng ký listener phải đi kèm cách quan sát kết quả và chính sách phục hồi.

## 13. Event Publication Registry hỗ trợ listener ra sao?

Spring Modulith cung cấp **Event Publication Registry** để theo dõi việc giao sự kiện tới các **transactional event listener**. Khi cấu hình integration lưu trữ thích hợp, registry có thể ghi nhận publication đang chờ và đánh dấu hoàn tất cho từng consumer khi listener xử lý thành công.

Điều này đặc biệt quan trọng khi listener được đăng ký theo mô hình sau commit và bất đồng bộ:

~~~text
orders commits OrderPlaced
    ├── notifications.on(OrderPlaced): FAILED
    └── loyalty.on(OrderPlaced): COMPLETED
~~~

Nếu notifications thất bại, hệ thống cần biết rằng một publication chưa hoàn tất. Khi đã cấu hình persistence và cơ chế recovery/republication phù hợp, publication còn dang dở có thể được xử lý lại mà không phải hủy đơn hàng đã commit.

Cần phân biệt các mức bảo đảm:

| Thành phần | Có thể cung cấp | Không tự bảo đảm |
| --- | --- | --- |
| Bean có `@EventListener` | Đăng ký handler nhận event trong context. | Lưu event bền vững, giao lại sau lỗi. |
| `@TransactionalEventListener` | Gắn xử lý với phase giao dịch. | Một transaction mới và retry tự động cho mọi lỗi. |
| `@ApplicationModuleListener` | Xử lý sau commit, bất đồng bộ, transaction riêng. | Side effect được thực hiện đúng một lần. |
| Event Publication Registry có storage | Theo dõi publication chưa hoàn tất/đã hoàn tất và hỗ trợ phục hồi. | Tự phát lại trong mọi cấu hình mà không cần cơ chế recovery phù hợp. |
| Idempotency của consumer | Tránh thực hiện tác dụng phụ trùng theo khóa phù hợp. | Biến hệ thống email/broker/DB ngoài thành một transaction chung. |

**Không nên coi `publishEvent()` trả về là bằng chứng listener hoàn tất.** Với publisher và consumer dùng transaction khác nhau, kết quả cần được kiểm tra ở đúng nơi xử lý.

### Danh tính listener cũng cần ổn định

Khi có publication đã lưu để phát lại, ứng dụng phải quản lý việc thay đổi tên bean, phương thức hoặc loại event một cách cẩn thận. Tùy hạ tầng và phiên bản, những thông tin liên quan đến listener có thể được dùng để định danh publication đang chờ. Đổi tên/refactor listener khi còn publication chưa hoàn tất cần được kiểm thử với persistence thực tế trước khi triển khai.

## 14. Retry và idempotency tại subscriber

Một failure window điển hình:

1. `orders` commit `OrderPlaced(eventId = E-1)`.
2. Listener notifications gửi email thành công.
3. Ứng dụng dừng trước khi ghi nhận listener hoàn tất.
4. Publication chưa hoàn tất được phát lại.
5. Listener notifications có thể nhận cùng `E-1` lần thứ hai.

Nếu listener chỉ gọi `sendEmail()` mỗi lần nhận, khách hàng có thể nhận email trùng. Giải pháp là **idempotency**: nhận diện một tác dụng phụ đã thực hiện với khóa ổn định, ví dụ `(consumerName, eventId)` hoặc `(orderId, notificationType)`.

Ví dụ một bảng theo dõi xử lý:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Nếu tác dụng phụ là cập nhật dữ liệu **cùng cơ sở dữ liệu**, có thể đặt việc ghi dấu `consumed_events` và thay đổi nghiệp vụ trong một transaction. Dùng unique constraint và xử lý cạnh tranh nguyên tử, tránh kiểm tra `exists` rồi `insert` tách rời giữa các luồng.

Với email, webhook hoặc thanh toán ở hệ thống ngoài, transaction database **không bao trùm** side effect bên ngoài. Nếu đánh dấu đã xử lý trước khi email được gửi nhưng gửi thất bại, lần retry bị bỏ qua sẽ gây mất thông báo. Cần thiết kế cơ chế gửi/đối soát, tận dụng idempotency key của bên ngoài nếu có, hoặc chấp nhận và xử lý trường hợp at-least-once theo nhu cầu nghiệp vụ.

**Đăng ký listener thành công mới đảm bảo có nơi nhận event; xử lý an toàn khi giao lại là một trách nhiệm khác.**

## 15. Những nguyên nhân khiến listener không được gọi

Nếu đã publish nhưng không thấy handler chạy, kiểm tra theo thứ tự:

| Dấu hiệu | Khả năng gây ra | Cách kiểm tra |
| --- | --- | --- |
| Handler không bao giờ được gọi. | Lớp listener không là Spring bean hoặc ngoài component scan. | Kiểm tra context, `@Component` hoặc `@Bean`, vị trí package. |
| `@EventListener` không chạy. | Event được publish trong một `ApplicationContext` khác hoặc kiểu event không khớp. | Kiểm tra context phát/nhận, lớp event thực tế và method signature. |
| `@TransactionalEventListener` không chạy. | Publisher không có transaction đang hoạt động; mặc định không fallback. | Kiểm tra transaction boundary, self-invocation, `fallbackExecution`. |
| Listener chỉ chạy khi commit, không chạy khi rollback. | Handler đăng ký ở phase `AFTER_COMMIT`. | Đây có thể là hành vi đúng; test riêng rollback. |
| Handler chạy nhưng lỗi xuất hiện trong luồng async. | `@ApplicationModuleListener` hoặc `@Async` thực thi ngoài luồng publisher. | Kiểm tra log exception, registry/recovery, executor. |
| Hai lần xử lý cùng event. | Có hai bean listener, hai handler, hoặc publication được giao lại. | Kiểm tra bean registration, eventId và cơ chế retry/idempotency. |
| Không nhận một số event cụ thể. | Có điều kiện `condition` hoặc listener nhận loại khác. | Đối chiếu điều kiện SpEL và kiểu tham số/annotation. |
| Sau deploy không đọc được publication cũ. | Event schema/class/package hoặc serializer thay đổi. | Kiểm tra persisted event, compatibility và listener còn hỗ trợ. |
| Đăng ký qua AOP proxy không hoạt động như mong đợi. | Method không được proxy/adapter truy cập phù hợp. | Xem kiểu proxy, visibility và vị trí annotation. |

Với listener sau commit, không chỉ kiểm tra “có `@Transactional` trong source” mà phải xác nhận **transaction thực sự hoạt động tại lúc publish**.

### Bẫy `@Transactional` khi self-invocation

~~~java
@Service
class OrderFacade {

    void handleRequest() {
        createOrder(); // Gọi nội bộ cùng object.
    }

    @Transactional
    void createOrder() {
        // Có thể không đi qua proxy transaction theo cơ chế AOP mặc định.
    }
}
~~~

Trong cấu hình proxy thông thường của Spring, lời gọi nội bộ này không kích hoạt interceptor của `@Transactional`. Nếu publisher phát event ở đường đi đó, listener transactional có thể không nhận được event như kỳ vọng. Cần tổ chức ranh giới transaction qua bean/phương thức được gọi thông qua proxy phù hợp hoặc dùng cơ chế transaction rõ ràng.

## 16. Thứ tự listener, lỗi và hiệu năng

### Listener đồng bộ

Nếu có nhiều `@EventListener` đồng bộ, thời gian xử lý và lỗi của từng listener có thể ảnh hưởng lời gọi publisher. Có thể dùng `@Order` để điều chỉnh thứ tự dispatch trong các trường hợp phù hợp, nhưng không nên dựa vào nó như một giải pháp điều phối nghiệp vụ lâu dài.

### Listener bất đồng bộ

Với `@ApplicationModuleListener`, các consumer có thể xử lý song song; chúng không được ngầm xem là chạy theo đúng thứ tự đăng ký hoặc thứ tự xuất hiện trong source. Listener nào lỗi cần được theo dõi và phục hồi độc lập.

Nếu thông báo phải đợi nghiệp vụ thanh toán hoàn tất, hãy nghe event biểu thị **thanh toán đã hoàn tất** hoặc xây quy trình điều phối trạng thái rõ ràng. Không để `notifications` dựa vào giả định listener của `payments` luôn chạy trước.

### Không để listener thành một công việc vô hạn

Listener nên có ranh giới trách nhiệm rõ:

- Xử lý đúng một tác vụ nghiệp vụ của module mình.
- Chỉ truy cập API công khai của module khác khi có lý do.
- Có timeout/điều kiện xử lý lỗi hợp lý cho dịch vụ phụ thuộc.
- Ghi log và trạng thái theo eventId, orderId và consumer.
- Chịu được retry/replay theo chính sách đã công bố.
- Không giữ transaction mở lâu vì thao tác ngoài hệ thống nếu tránh được.

Các listener bất đồng bộ cũng tiêu thụ tài nguyên executor; khi tải cao cần cấu hình, quan sát hàng đợi và đánh giá khả năng mở rộng theo nhu cầu. Annotation listener không tự giải quyết vấn đề backpressure.

## 17. Kiểm thử đăng ký listener

Mục tiêu kiểm thử là **Spring thật sự phát hiện bean, kết nối handler, tôn trọng transaction và giao event đúng loại**.

### 17.1. Kiểm thử publisher phát đúng event

Spring Modulith hỗ trợ `@ApplicationModuleTest` và `PublishedEvents` để quan sát các event đã publish trong một module test.

Ví dụ minh họa:

~~~java
@ApplicationModuleTest
class OrderModuleTests {

    @Autowired
    OrderService orderService;

    @Test
    void publishesOrderPlaced(PublishedEvents published) {
        var request = OrderTestFixtures.validOrder();
        UUID orderId = orderService.placeOrder(request);

        assertThat(published.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .hasSize(1);
    }
}
~~~

Ví dụ cần các import JUnit, AssertJ, `@Autowired`, Spring Modulith testing API và fixture `OrderTestFixtures` do dự án xây dựng. `PublishedEvents` xác minh **event đã được publish**, không tự chứng minh các listener bất đồng bộ đã hoàn tất.

### 17.2. Kiểm thử listener được phát hiện trong context

Một integration test thực tế nên khởi tạo Spring context có bean `OrderConfirmationListener`, publisher thử `OrderPlaced` và xác minh tác dụng phụ ở `ConfirmationSender` hoặc trạng thái consumer.

Nếu dùng `@EventListener` đồng bộ, có thể kiểm tra kết quả ngay sau publish trong điều kiện phù hợp. Nếu dùng `@ApplicationModuleListener`, cần chờ có điều kiện một cách xác định (ví dụ qua công cụ kiểm thử bất đồng bộ) và bảo đảm transaction phát hành đã commit.

**Không gọi trực tiếp `new OrderConfirmationListener(...).on(event)` rồi coi đó là bằng chứng Spring đã đăng ký listener.** Cách đó chỉ test logic method, bỏ qua component scanning và event infrastructure.

### 17.3. Kiểm thử commit/rollback

Tình huống quan trọng:

1. Publisher mở transaction, lưu đơn, publish `OrderPlaced` và commit.
2. Listener `@ApplicationModuleListener` xử lý sau commit.
3. Publisher mở transaction khác, publish rồi rollback.
4. Listener sau commit **không xử lý** publication bị rollback.

Khi tạo test transaction, chú ý các annotation giao dịch ở test framework có thể tự rollback cuối test. Nếu test vừa publish vừa chờ listener after-commit mà test transaction vẫn chưa commit, listener chưa có điều kiện được kích hoạt. Cần commit rõ ràng hoặc dùng luồng nghiệp vụ tạo transaction thật trong test.

### 17.4. Kiểm thử lỗi và replay

Khi Event Publication Registry có persistence và recovery được cấu hình:

- Cố tình gây lỗi ở listener.
- Xác minh publication tương ứng còn chưa hoàn tất.
- Kích hoạt cơ chế recovery của ứng dụng.
- Kiểm tra listener xử lý lại được và đánh dấu hoàn tất.
- Phát lại cùng `eventId` để chứng minh tác dụng phụ không bị nhân đôi.

Các test này cần storage và cấu hình tương ứng; unit test mock publisher không đủ xác nhận khả năng phục hồi sau sự cố.

### 17.5. Kiểm tra ranh giới module

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTest {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm thử kiến trúc giúp phát hiện listener import implementation nội bộ của module khác, hoặc tạo phụ thuộc không được khai báo. `ApplicationModules.verify()` không kiểm tra toàn bộ logic xử lý event hay tự chứng minh delivery reliability; đó là trách nhiệm của các test hành vi và vận hành.

## 18. Quan sát hệ thống khi đã đăng ký nhiều listener

Khi người dùng báo “đơn đã tạo nhưng chưa nhận email”, cần phân biệt listener **không được đăng ký**, **chưa được kích hoạt**, **đang chờ** hay **đã xử lý rồi nhưng side effect gặp lỗi**.

Một bộ thông tin quan sát hữu ích:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `eventType`, `eventId` | Xác định sự kiện đang theo dõi. |
| `publisherModule`, `consumerModule` | Biết module nào phát/nhận. |
| `listenerName` | Tìm handler cụ thể xử lý. |
| `publishedAt`, `startedAt`, `finishedAt` | Đo thời gian chờ và thời gian thực thi. |
| `publicationStatus` | Biết publication chưa hoàn tất hay đã hoàn tất khi dùng registry. |
| `attempt`, `errorCategory` | Chẩn đoán retry và lỗi lặp. |
| `executorQueueDepth` nếu có | Theo dõi tải xử lý bất đồng bộ. |

Ví dụ log **do ứng dụng tự thiết kế**, không phải output mặc định được Spring Modulith tạo ra:

~~~text
event=OrderPlaced id=E-101 listener=notifications status=STARTED
event=OrderPlaced id=E-101 listener=notifications status=FAILED reason=MAIL_TIMEOUT
event=OrderPlaced id=E-101 listener=loyalty status=COMPLETED
event=OrderPlaced id=E-101 listener=notifications status=COMPLETED attempt=2
~~~

Không nên log toàn bộ event chứa dữ liệu nhạy cảm. Nếu dùng Event Publication Registry, theo dõi publication chưa hoàn tất kéo dài để phát hiện subscriber bị kẹt thay vì chỉ dựa vào log `publishEvent`.

## 19. Quy trình chọn và đăng ký listener

~~~mermaid
flowchart TD
    A["Có một event nghiệp vụ cần phản ứng"] --> B{"Phản ứng chỉ hợp lệ sau khi transaction commit?"}
    B -->|"Không"| C["Cân nhắc @EventListener đồng bộ"]
    B -->|"Có"| D{"Muốn xử lý module sau commit và bất đồng bộ?"}
    D -->|"Có"| E["@ApplicationModuleListener"]
    D -->|"Không hoặc cần phase riêng"| F["@TransactionalEventListener"]
    C --> G["Tạo Spring bean và đăng ký handler đúng kiểu"]
    E --> G
    F --> G
    G --> H["Kiểm thử bean discovery, publish, commit/rollback"]
    H --> I{"Cần phục hồi tác vụ thất bại?"}
    I -->|"Có"| J["Cấu hình registry/storage/recovery và idempotency"]
    I -->|"Không"| K["Quan sát lỗi và giới hạn chấp nhận"]
    J --> L["Kiểm tra delivery/replay trong môi trường phù hợp"]
    K --> L
~~~

Quy trình trên là một công cụ ra quyết định. Thực tế, việc có cần transaction riêng, async executor, registry và retry phụ thuộc mức quan trọng của side effect và kiến trúc triển khai.

## 20. Bài tập thực hành

Xây dựng ba module `orders`, `notifications`, `loyalty` với các yêu cầu:

1. Module `orders` có event contract `OrderPlaced(eventId, orderId, occurredAt)` nằm trong API được công khai.
2. `OrderService.placeOrder()` có transaction, lưu đơn rồi publish `OrderPlaced`.
3. Module `notifications` đăng ký `@ApplicationModuleListener` để gửi xác nhận sau commit.
4. Module `loyalty` đăng ký một `@ApplicationModuleListener` khác để cộng điểm.
5. Dùng `@NamedInterface("events")` và `allowedDependencies = "orders::events"` để không cho listener truy cập `orders.internal`.
6. Viết test xác nhận Spring context có hai handler được đăng ký và cả hai xử lý `OrderPlaced` hợp lệ.
7. Tạo transaction rollback sau publish; xác nhận không handler after-commit nào gây side effect.
8. Gây lỗi tạm thời trong notifications; khi có Event Publication Registry với storage/recovery phù hợp, kiểm tra trạng thái publication và thực hiện phát lại.
9. Kiểm chứng cùng `eventId` được giao lại không làm gửi email hoặc cộng điểm hai lần.
10. Theo dõi log/metric riêng của từng listener và xác nhận không dựa vào thứ tự hoàn thành giữa notifications và loyalty.

**Câu hỏi tự kiểm tra:** Vì sao thêm `@ApplicationModuleListener` vào một lớp không phải Spring bean vẫn có thể không tạo subscriber? Nếu publisher không có transaction, `@TransactionalEventListener` mặc định sẽ làm gì? Tại sao `@Order` không đủ để điều phối các listener bất đồng bộ? Registry và idempotency giải quyết hai vấn đề khác nhau ra sao?

**Ghi nhớ:** Đăng ký listener trong Spring Modulith là việc tạo một **Spring bean có phương thức xử lý đúng loại event và đúng ngữ nghĩa giao dịch**. `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener` phục vụ những tình huống khác nhau; chọn đúng annotation giúp module giao tiếp rõ ràng, bảo vệ ranh giới nghiệp vụ. Để listener đáng tin cậy trong vận hành, phải kiểm thử bean registration, transaction, rollback, publication tracking, recovery, idempotency và khả năng quan sát.

