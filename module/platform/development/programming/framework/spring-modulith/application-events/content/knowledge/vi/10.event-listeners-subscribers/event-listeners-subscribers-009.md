# Phạm vi bean listener trong Spring Modulith

## 1. Vì sao phải hiểu phạm vi của listener?

Trong một ứng dụng Spring Modulith, module **Orders** có thể phát sự kiện `OrderConfirmed`, còn module **Notifications** và **Reporting** đăng ký listener để xử lý hậu quả. Vì Spring dùng bean để quản lý listener, cách bean được đăng ký, tạo ra, chia sẻ và hủy ảnh hưởng trực tiếp đến độ tin cậy của giao tiếp giữa các module.

Cụm từ **“phạm vi bean listener”** dễ bị hiểu theo một nghĩa duy nhất. Trên thực tế, có ít nhất ba chiều cần tách bạch:

1. **Bean scope:** Spring tạo và sử dụng instance của listener theo vòng đời nào: `singleton`, `prototype`, request, session hay scope tùy chỉnh?
2. **ApplicationContext scope:** Listener nằm trong Spring context nào, và nó có thể nhận sự kiện được phát ở context nào?
3. **Module boundary:** Bean/listener thuộc module nghiệp vụ nào, contract event nằm ở API công khai nào và module khác được phép phụ thuộc những gì?

Ba chiều này liên quan nhưng không đồng nghĩa. Một singleton listener có thể nhận nhiều event; một event được gửi tới nhiều singleton listener; một listener nằm ở package `notifications.internal` vẫn có thể lắng nghe contract công khai `orders.OrderConfirmed` khi các bean cùng được khởi tạo trong ứng dụng.

Trong **SPRING_MODULITH_APPLICATION_EVENTS**, hiểu đúng phạm vi bean giúp giảm coupling giữa các module mà không tạo lỗi khi dùng listener bất đồng bộ, giao dịch sau commit, Event Publication Registry và retry.

### Mục tiêu bài học

Sau bài này, bạn sẽ có thể:

- Giải thích tại sao singleton là lựa chọn phổ biến cho event listener.
- Nhận diện tác hại của mutable state trong singleton listener khi có nhiều event hoặc nhiều luồng.
- Đánh giá rủi ro khi dùng `prototype`, `request` hoặc `session` scope cho listener.
- Xác minh listener được phát hiện qua component scanning và được đăng ký trong `ApplicationContext`.
- Phân biệt scope của bean với ranh giới application module.
- Thiết kế `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener` phù hợp transaction và asynchronous execution.
- Kiểm thử trường hợp listener thiếu, bị đăng ký hai lần, lỗi do scope và xử lý trùng.

## 2. Mô hình ba lớp phạm vi

Hãy hình dung một ứng dụng có các module:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderConfirmed.java
│   └── internal
│       └── OrderApplicationService.java
├── notifications
│   └── internal
│       ├── OrderConfirmedListener.java
│       └── NotificationService.java
└── reporting
    └── internal
        └── OrderReportingListener.java
~~~

Cả hai listener đều có thể nhận `OrderConfirmed` khi được đăng ký trong cùng ứng dụng, dù mỗi listener thuộc một module khác nhau.

~~~mermaid
flowchart TB
    subgraph Context["Spring ApplicationContext"]
        P["Orders publisher"] --> E(("OrderConfirmed event"))
        E --> N["Notifications listener bean"]
        E --> R["Reporting listener bean"]
    end
    N --> NS["Notifications-owned state"]
    R --> RS["Reporting-owned state"]
~~~

| Lớp phạm vi | Câu hỏi cần trả lời | Cơ chế chính |
| --- | --- | --- |
| **Bean** | Một instance listener tồn tại trong bao lâu, có được chia sẻ không? | `@Scope`, bean definition và container lifecycle |
| **Context** | Event phát ở đâu được giao cho listener nào? | `ApplicationContext` và `ApplicationEventMulticaster` |
| **Module** | Listener được phép import type nào từ module khác? | Spring Modulith module model, API package và `@NamedInterface` |

**Điểm mấu chốt:** annotation `@Scope("singleton")` không biến listener thành toàn cục trên nhiều JVM. Tương tự, đặt listener trong một module Spring Modulith không tạo một event bus riêng biệt cho module đó nếu tất cả dùng chung Spring application context.

## 3. Singleton: scope mặc định và phổ biến nhất

Trong Spring, bean không khai báo scope thường có scope **singleton**. Container duy trì một instance cho **mỗi bean definition trong mỗi container**; tất cả những nơi phụ thuộc cùng bean definition sẽ thường dùng chung instance đó.

Ví dụ:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmedListener {

    private final NotificationService notifications;

    OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @EventListener
    void on(OrderConfirmed event) {
        notifications.scheduleConfirmation(event.orderId());
    }
}
~~~

Listener này thường chỉ có một instance trong ứng dụng. Nó có thể được gọi **nhiều lần** cho nhiều đơn hàng; số lần gọi không đồng nghĩa số instance được tạo. Annotation `@EventListener` không tự tạo một bean cho mỗi event.

### 3.1. Vì sao singleton phù hợp?

Một listener lý tưởng là thành phần điều phối **không giữ state nghiệp vụ riêng trong field mutable**:

- Dependency như `NotificationService` và repository được inject khi khởi tạo.
- Dữ liệu của mỗi event nằm trong **biến cục bộ** của lời gọi phương thức.
- Trạng thái xử lý bền vững được lưu trong cơ sở dữ liệu của module nhận.
- Transaction được gắn với từng lần xử lý thay vì gắn với cả vòng đời bean.

Một singleton listener có thể nhận và ủy quyền rất nhiều sự kiện mà không cần tạo bean mới liên tục.

### 3.2. Singleton không tự đồng nghĩa thread-safe

Ví dụ dễ gây lỗi:

~~~java
@Component
class UnsafeOrderListener {

    private UUID currentOrderId;
    private int processedCount;

    @EventListener
    void on(OrderConfirmed event) {
        currentOrderId = event.orderId();
        processedCount++;
        // Một invocation khác có thể ghi đè currentOrderId ngay lúc này.
        performWork(currentOrderId);
    }
}
~~~

`currentOrderId` và `processedCount` được chia sẻ giữa mọi invocation của cùng instance. Khi listener chạy bất đồng bộ hoặc publisher hoạt động từ nhiều thread, có thể xảy ra race condition, lost update hoặc đọc sai order ID. Kể cả khi listener đồng bộ theo mặc định, **nhiều publisher thread có thể cùng gọi vào một singleton listener**.

Cách an toàn hơn:

~~~java
@Component
class OrderConfirmedListener {

    private final NotificationService notifications;

    OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @EventListener
    void on(OrderConfirmed event) {
        UUID orderId = event.orderId();  // Biến cục bộ theo invocation.
        notifications.scheduleConfirmation(orderId);
    }
}
~~~

Không nên biến `processedCount++` thành `AtomicInteger` rồi xem đó là giải pháp idempotency. Đếm an toàn trong một JVM vẫn không bảo vệ được xử lý trùng khi ứng dụng restart hoặc chạy nhiều instance. Trạng thái xử lý event cần được quản lý theo quy tắc nghiệp vụ ở nơi lưu trữ phù hợp.

## 4. Prototype: instance mới không phải lời giải mặc định

Spring hỗ trợ `prototype` scope: mỗi lần yêu cầu bean từ container, Spring có thể tạo instance mới. Có thể khai báo:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class PrototypeOrderListener {

    @EventListener
    void on(OrderConfirmed event) {
        // Minh họa scope; không phải mô hình khuyến nghị.
    }
}
~~~

Cần hiểu một số giới hạn trước khi dùng:

- `@Scope("prototype")` không định nghĩa một hàng đợi hoặc một worker riêng cho từng event.
- Nó **không bảo đảm** event chỉ được xử lý một lần, theo thứ tự hay trong transaction riêng.
- Khi một prototype được inject trực tiếp vào singleton, dependency thường được resolve tại thời điểm tạo singleton, nên không tự động tạo instance mới mỗi lần singleton dùng dependency.
- Việc một listener method được phát hiện và Spring resolve bean instance lúc phân phối event còn phụ thuộc cơ chế adapter/proxy của listener; không nên thiết kế business logic dựa trên giả định “mỗi event chắc chắn có một listener object mới”.
- Spring không tự quản lý trọn vòng đời hủy của prototype như với singleton; tài nguyên mở trong instance có thể cần quản lý rõ.

**Khuyến nghị thực hành:** giữ listener singleton và chuyển công việc có state theo từng lần xử lý vào method-local state, transactional service hoặc một job/worker chuyên trách. `prototype` chỉ nên dùng khi có lý do kỹ thuật rõ ràng và đã kiểm chứng lifecycle theo cấu hình của phiên bản Spring sử dụng.

### Một lỗi phổ biến khi inject prototype

~~~java
@Component
class HandlerCoordinator {

    private final PrototypeHandler handler;

    HandlerCoordinator(PrototypeHandler handler) {
        this.handler = handler; // Prototype này được resolve khi coordinator tạo.
    }

    void process(OrderConfirmed event) {
        handler.handle(event); // Không tự động đổi handler cho từng event.
    }
}
~~~

Nếu thật sự cần một object mới mỗi lần xử lý, có thể sử dụng factory hoặc `ObjectProvider<PrototypeHandler>` để yêu cầu instance mới theo ý định. Nhưng đó là chiến lược vòng đời object, **không thay thế** transaction và cơ chế giao event của Spring Modulith.

## 5. Request và session scope: vì sao thường không phù hợp?

Trong ứng dụng web, Spring có thể cung cấp các bean mang scope như `request` hoặc `session`. Chúng hữu ích với dữ liệu gắn với một HTTP request hoặc phiên người dùng, nhưng thường là lựa chọn **rủi ro** cho event listener chạy sau commit hoặc bất đồng bộ.

Ví dụ không khuyến nghị:

~~~java
@Component
@RequestScope
class RequestOrderListener {

    @EventListener
    void on(OrderConfirmed event) {
        // Xử lý event phụ thuộc vào HTTP request đang hoạt động.
    }
}
~~~

Các vấn đề có thể xuất hiện:

1. Event có thể được phát từ scheduled job, message consumer hoặc batch processing, **không có HTTP request**.
2. `@ApplicationModuleListener` thường chạy trên thread bất đồng bộ sau commit; request context gắn với thread web ban đầu không tự tồn tại ở thread listener.
3. Khi request kết thúc, bean request-scoped không còn vòng đời phù hợp để xử lý event có thể được retry sau đó.
4. Scoped proxy có thể giúp inject type vào singleton nhưng **không tạo một request scope đang hoạt động** lúc method được gọi.
5. Session scope không phù hợp nếu event nghiệp vụ cần chạy độc lập với phiên đăng nhập, hoặc được xử lý trong backend worker.

Một lỗi điển hình là `ScopeNotActiveException` khi Spring cố resolve bean request-scoped mà không có request attributes phù hợp.

### Thay thế bằng dữ liệu event hoặc service độc lập request

Nếu listener cần nhận dạng actor thao tác, hãy công bố **metadata nghiệp vụ được phép truyền** theo contract:

~~~java
public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        UUID confirmedByUserId,
        Instant occurredAt
) {}
~~~

Sau đó listener dùng `confirmedByUserId` để kiểm tra quyền hoặc truy vấn qua API phù hợp nếu cần. Tránh mang `HttpServletRequest`, `HttpSession`, `SecurityContext` mutable hay đối tượng servlet vào payload.

Không gửi thông tin nhạy cảm không cần thiết như session token, access token hoặc toàn bộ request header. Trường dữ liệu actor phải có lý do nghiệp vụ và phù hợp quy tắc bảo mật.

## 6. ApplicationContext là phạm vi phân phối event

Spring `ApplicationEventPublisher` phát sự kiện qua cơ chế của Spring application context. Với ứng dụng có một context duy nhất, các listener hợp lệ được đăng ký trong context đó có thể nhận event tương ứng với type/condition.

Nhưng một hệ thống có thể có **nhiều context**:

- Context cha và con trong một số cấu hình web hoặc test.
- Một context khác được tạo riêng cho một phần ứng dụng.
- Nhiều application instance chạy ở những JVM khác nhau.
- Context khởi tạo để thực thi test thay vì toàn bộ production application.

**Sự kiện trong một context không tự truyền qua mạng tới context trong JVM khác.** Với quan hệ cha-con của Spring, event phát ở child context có thể được propagate lên parent context; hướng ngược lại không được bảo đảm tương tự. Điều này có thể dẫn tới một listener parent nhận event từ child ngoài dự kiến nếu kiến trúc dùng context hierarchy.

~~~mermaid
flowchart LR
    C["Child ApplicationContext"] -->|"Có thể propagate lên"| P["Parent ApplicationContext"]
    P -.->|"Không tự propagate xuống"| C
    A["Instance A JVM"] -.->|"Không có transport mặc định"| B["Instance B JVM"]
~~~

### 6.1. Bean singleton cũng chỉ singleton theo context

Hai Spring contexts khác nhau có thể tạo hai instance độc lập cho cùng loại `OrderConfirmedListener` nếu mỗi context có bean definition tương ứng. Vì vậy, câu “listener là singleton” **không có nghĩa** chỉ có đúng một listener trong toàn deployment.

Nếu ứng dụng chạy 3 instance, mỗi instance có context và bean listener riêng. Với Spring application events thuần túy, mỗi publisher phát event **trong instance của nó**; các listener trong instance khác không tự nhận event đó.

Muốn consumer liên tiến trình cần thêm broker, outbox hoặc event externalization phù hợp với kiến trúc tích hợp.

### 6.2. Listener có thực sự được đăng ký?

Spring phát hiện bean theo component scanning, `@Bean` definitions, auto-configuration và điều kiện kích hoạt. `@EventListener` thường được xử lý ở giai đoạn Spring chuẩn bị context bằng cơ chế đăng ký listener method.

Những tình huống khiến listener không được gọi:

- Class chưa được quét vì nằm ngoài package scan.
- Thiếu `@Component`, `@Bean` hoặc một cơ chế đăng ký bean khác.
- Bean bị loại bởi `@Profile` hoặc `@ConditionalOnProperty`.
- Event được publish trong context khác hoặc trước khi listener sẵn sàng.
- Event type, method signature hoặc condition không khớp.
- Transactional listener chờ `AFTER_COMMIT`, nhưng event được phát ngoài transaction hoặc transaction bị rollback.
- Listener đang chờ asynchronous execution, nhưng người kiểm thử kiểm tra state quá sớm.

Không nên kết luận “event bus hỏng” khi thực tế **không có listener bean** hoặc event chưa đến giai đoạn xử lý.

## 7. Spring Modulith module boundary không phải bean scope

Spring Modulith khuyến khích mỗi module nghiệp vụ có API công khai rõ ràng. Bean của Notifications có thể là singleton và nằm trong `notifications.internal`; điều này **không đồng nghĩa** Orders được phép gọi thẳng bean đó.

Ví dụ:

~~~text
com.acme.shop
├── orders
│   ├── OrderConfirmed.java          <-- public contract
│   └── internal
│       └── OrderApplicationService.java
├── notifications
│   └── internal
│       └── OrderConfirmedListener.java
└── reporting
    └── internal
        └── OrderReportingListener.java
~~~

- Orders phát `OrderConfirmed` và không phụ thuộc trực tiếp vào internal service của Notifications.
- Notifications import `com.acme.shop.orders.OrderConfirmed` để lắng nghe một event contract hợp lệ.
- Listener nhận event rồi cập nhật state **do Notifications sở hữu**.
- Nếu event contract nằm trong subpackage `orders.events`, có thể công bố package đó bằng `@NamedInterface` tùy cấu trúc module.

Ví dụ đặt annotation cho package công khai có tên:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Quyền truy cập Java qua `public` không đủ để chứng minh dependency đúng kiến trúc Spring Modulith. Hãy dùng kiểm tra mô hình module để xác định phụ thuộc được cho phép.

### 7.1. Event không cần listener bean ở module publisher

Một publisher không phải tự inject listener hoặc tạo bean consumer:

~~~java
events.publishEvent(new OrderConfirmed(eventId, orderId, occurredAt));
~~~

Nếu thêm một module mới quan tâm `OrderConfirmed`, module đó chỉ cần đăng ký listener phù hợp khi được đưa vào ứng dụng. Publisher không cần thay đổi code để gọi thêm consumer.

Việc subscription là quan hệ giữa **contract event** và **listener method**, không phải quan hệ gọi trực tiếp tới một đối tượng service cụ thể.

## 8. Ví dụ đầy đủ: từ publisher tới singleton listener

Giả sử type event được công bố trong module Orders:

~~~java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Application service trong Orders quản lý transaction và phát event:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        if (order.isConfirmed()) {
            return;
        }

        order.confirm(); // Kiểm tra quy tắc domain, đổi state hợp lệ.
        orders.save(order);

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                order.getId(),
                Instant.now(clock)
        ));
    }
}
~~~

Ví dụ giả định đã có `Order`, `OrderRepository` và bean `Clock`. Với transaction JPA, ứng dụng cần thiết lập entity/state đúng để tránh phát event cho một lần chuyển trạng thái bị từ chối; nếu có request đồng thời cần optimistic locking, khóa hoặc constraint theo quy tắc nghiệp vụ.

Notifications đăng ký listener:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmedListener {

    private final NotificationService notifications;

    public OrderConfirmedListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        notifications.scheduleConfirmationIfAbsent(
                event.orderId(),
                event.eventId()
        );
    }
}
~~~

Ở đây:

- `@Component` tạo bean trong context khi class được quét.
- Không khai báo `@Scope` nên bean mặc định singleton.
- `@ApplicationModuleListener` cung cấp cơ chế listener sau commit, bất đồng bộ, với transaction xử lý mới.
- `notifications` là dependency ổn định; sự kiện cụ thể được truyền qua tham số method.
- `scheduleConfirmationIfAbsent` là phương thức nghiệp vụ giả định, cần triển khai idempotency và lưu trữ có constraint phù hợp.

Trong ví dụ, class và method được khai báo `public` để việc áp dụng proxy/AOP cho `@Async` và `@Transactional` rõ ràng, tránh phụ thuộc vào chi tiết proxy hoặc visibility của từng phiên bản Spring. Có thể giữ implementation ở package `notifications.internal` để bảo vệ ranh giới module.

**Phạm vi singleton không làm event trở thành synchronous hoặc asynchronous.** Chính annotation, cấu hình executor và phase transaction quyết định thời điểm listener xử lý.

## 9. Bean scope và thời điểm thực thi là hai vấn đề riêng

Ba kiểu lắng nghe quan trọng:

| Cách lắng nghe | Thời điểm điển hình | Ảnh hưởng đến listener singleton |
| --- | --- | --- |
| `@EventListener` | Với multicaster mặc định, gọi đồng bộ khi `publishEvent` | Cùng một instance có thể được gọi bởi các thread publisher khác nhau |
| `@TransactionalEventListener` | Mặc định `AFTER_COMMIT` của transaction | Thường chạy sau commit; annotation không tự tạo transaction ghi mới và không tự async |
| `@ApplicationModuleListener` | Sau commit, bất đồng bộ và transaction riêng theo Spring Modulith | Cùng một bean singleton có thể nhận nhiều invocation trên executor threads |

~~~mermaid
sequenceDiagram
    autonumber
    actor Client
    participant O as Orders
    participant DB as DB Orders
    participant P as Publisher
    participant N as Singleton listener
    Client->>O: confirm(orderId)
    O->>DB: Change Order = CONFIRMED (TX)
    O->>P: publish OrderConfirmed
    O->>DB: COMMIT
    P-->>N: AFTER_COMMIT + asynchronous
    N->>N: Process event (new TX)
~~~

### 9.1. Một instance, nhiều invocation

Hãy tưởng tượng hai đơn hàng được xác nhận gần như đồng thời:

~~~text
Thread executor-1: listener.on(OrderConfirmed(A))
Thread executor-2: listener.on(OrderConfirmed(B))
                 \_______________________/
                     cùng singleton bean
~~~

Nếu listener chỉ dùng dependency stateless và biến cục bộ, việc xử lý có thể song song mà không ghi đè state riêng. Nếu lưu `currentOrderId` trong field, hai lời gọi có thể làm hỏng dữ liệu. Dù có `synchronized` để chặn race, việc serialize tất cả event có thể gây nghẽn và không giải quyết duplicate giữa nhiều instance.

### 9.2. Request context không theo listener thread

Một listener bất đồng bộ không nên gọi trực tiếp `RequestContextHolder.currentRequestAttributes()` hoặc giả định `SecurityContextHolder` trên thread request đã được truyền sang thread xử lý. Nếu cần context propagation, phải cấu hình và kiểm thử cơ chế cụ thể, đồng thời phân biệt thông tin nghiệp vụ phải lưu bền với thông tin request chỉ có hiệu lực trong một HTTP call.

### 9.3. Phase sau commit và ghi dữ liệu

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` được kích hoạt sau commit, nhưng transaction resources của publisher có thể vẫn còn gắn trong một phần vòng đời callback. Khi listener cần ghi dữ liệu độc lập, dùng transaction mới phù hợp. `@ApplicationModuleListener` hỗ trợ kiểu xử lý này.

Không nên dùng `@EventListener` đồng bộ để gửi email hoặc gọi API không thể rollback khi publisher chưa commit, nếu email chỉ có ý nghĩa sau một thay đổi DB đã xác nhận.

## 10. Đăng ký một listener: @Component, @Bean và cấu hình điều kiện

Hai phương thức đăng ký bean phổ biến là dùng stereotype annotation hoặc factory method. Chỉ nên chọn **một cách** cho một listener logic.

### 10.1. Đăng ký bằng @Component

~~~java
@Component
class OrderConfirmedListener {

    @EventListener
    void on(OrderConfirmed event) {
        // ...
    }
}
~~~

### 10.2. Đăng ký bằng @Bean

~~~java
@Configuration
class NotificationListenerConfiguration {

    @Bean
    OrderConfirmedListener orderConfirmedListener(
            NotificationService notifications
    ) {
        return new OrderConfirmedListener(notifications);
    }
}
~~~

Ở phương án `@Bean`, class `OrderConfirmedListener` không cần thêm `@Component`. Nếu vô tình khai báo cả hai, có thể tồn tại nhiều bean definition/listener độc lập và mỗi event bị xử lý nhiều lần, tùy cách đặt tên và cấu hình bean của ứng dụng.

Bean được đăng ký không có nghĩa mọi listener logic đều chỉ được gọi một lần: có thể có nhiều bean cùng loại hoặc nhiều phương thức `@EventListener` phù hợp với cùng event.

### 10.3. Điều kiện kích hoạt bean

Ví dụ muốn chỉ bật listener tại môi trường có tính năng thông báo:

~~~java
@Component
@ConditionalOnProperty(
        prefix = "notifications",
        name = "order-events.enabled",
        havingValue = "true",
        matchIfMissing = true
)
class OrderConfirmedListener {
    // ...
}
~~~

Khi property không thỏa, Spring có thể **không tạo bean này**, do đó sẽ không có subscriber tương ứng. Không nên coi đó là “listener tồn tại nhưng đang tạm ngừng” trong mô hình publication registry: publication tracking gắn với listener thực sự được đăng ký tại thời điểm phát event.

Nếu bật lại listener sau này, Spring application events thông thường **không tự phát lại tất cả event cũ**. Cần quy trình backfill/replay riêng khi đó là yêu cầu nghiệp vụ.

`@Profile` và các điều kiện configuration khác có tác động tương tự: việc triển khai một module mới không bảo đảm bean listener sẽ được kích hoạt trong mọi profile.

## 11. Lazy initialization và vòng đời ApplicationContext

Cơ chế phát hiện `@EventListener` hoạt động thông qua Spring container khi context được dựng và các bean definitions được xử lý. Điều này khác việc tự gọi một phương thức Java trên object.

Một số điều cần lưu ý:

- **Bean definition có tồn tại** không đồng nghĩa bean instance đã được tạo xong theo cách bạn tưởng. Với lazy bean, Spring có thể trì hoãn khởi tạo instance.
- **Listener method registration** và **instance resolution khi gọi** là hai giai đoạn khác nhau; proxy, scope và AOP có thể làm vòng đời thực tế phức tạp.
- Không nên tự tay tạo `new OrderConfirmedListener(...)` rồi mong object đó được `@EventListener` tự đăng ký. Nó cần được Spring quản lý và được event infrastructure phát hiện.
- Đăng ký bean động sau khi context đã refresh không mặc nhiên khiến mọi annotated listener method được quét lại. Với trường hợp plugin runtime động, cần thiết kế explicit registration hoặc bootstrap riêng và kiểm thử hành vi.
- Không coi event là cơ chế lưu trữ lịch sử mặc định. Listener khởi tạo sau khi event đã phát không tự được bù mọi event đã bỏ lỡ.

### Khởi động và tắt ứng dụng

Nếu phát event rất sớm trong bootstrap hoặc trong quá trình shutdown, một số listener có thể chưa đăng ký hoặc dependency có thể đang đóng. Event nghiệp vụ cần tính bền vững thường nên được phát trong transaction khi ứng dụng đã sẵn sàng, với cơ chế registry/outbox phù hợp; còn nhu cầu “run at startup” có thể dùng lifecycle hook phù hợp như `ApplicationReadyEvent`, `ApplicationRunner` hoặc cơ chế riêng.

Các hook lifecycle không thay thế event contract nghiệp vụ, và một listener cho `ApplicationReadyEvent` không tự là một consumer của `OrderConfirmed`.

## 12. Phân biệt phạm vi bean và phạm vi transaction

Một listener singleton tồn tại qua nhiều transaction; transaction không phải thuộc tính “gắn vĩnh viễn” vào bean đó.

Ví dụ:

~~~text
listener singleton
   |
   +-- on(event A) -> transaction A -> commit
   |
   +-- on(event B) -> transaction B -> rollback
   |
   +-- on(event C) -> transaction C -> commit
~~~

Với `@ApplicationModuleListener`, mỗi lần xử lý được tổ chức theo chính sách transaction của listener. Nếu event A và B chạy đồng thời, chúng phải quản lý trạng thái riêng và đồng bộ qua database khi cần.

Các tình huống quan trọng:

| Trường hợp | Điều gì xảy ra? |
| --- | --- |
| Publisher transaction rollback | Listener `AFTER_COMMIT` không xử lý như một lần commit thành công |
| Publisher commit, listener thất bại | Commit của publisher không bị đảo ngược |
| Listener được retry | Cùng bean singleton có thể được gọi lại; không tự nhớ lần xử lý trước theo cách bền vững |
| Publisher không có transaction | `@TransactionalEventListener` mặc định bỏ qua event, trừ khi cấu hình `fallbackExecution` |
| Listener cần lưu state | Dùng transaction ghi phù hợp của module nhận; không giữ state trong field singleton |

Đừng gộp “scope của bean” với “scope của transaction”. Một bean singleton vẫn có thể tham gia hàng nghìn transaction độc lập và nhận nhiều event bị retry.

## 13. Event Publication Registry theo dõi publication, không theo bean instance

Spring Modulith **Event Publication Registry** giúp theo dõi việc phân phối event tới transactional listener khi ứng dụng cấu hình backend publication phù hợp. Publication chưa hoàn thành có thể được quan sát và xử lý lại theo cơ chế được cấu hình.

Registry có thể hỗ trợ sự tin cậy trong các tình huống:

- Orders đã commit `OrderConfirmed` nhưng Notifications gặp lỗi.
- Tiến trình bị dừng khi listener đang xử lý.
- Listener cần được gọi lại sau sự cố.
- Các module phải biết publication nào tồn đọng để theo dõi vận hành.

Điều được theo dõi là **publication cần xử lý bởi một listener đích** theo cơ chế đăng ký, chứ không phải “instance của singleton đã từng thấy event”. Sau khi ứng dụng restart, instance bean cũ đã mất nhưng publication chưa hoàn thành vẫn có thể được khôi phục từ storage.

### 13.1. Vì sao vẫn cần idempotency?

Một tình huống điển hình:

~~~mermaid
sequenceDiagram
    autonumber
    participant R as Registry
    participant N as Listener singleton
    participant DB as Notifications DB
    R->>N: OrderConfirmed(E1)
    N->>DB: Tạo email job và COMMIT
    Note over N,R: Ứng dụng lỗi trước khi publication được đánh dấu completed
    R-->>N: Retry OrderConfirmed(E1)
    N->>DB: Kiểm tra E1 / business key, không tạo job trùng
~~~

Nếu listener lưu một `Set<UUID> processedEvents` trong field singleton để ghi nhớ ID đã xử lý, tập hợp đó sẽ **mất khi restart**, không được chia sẻ giữa các instance và không đảm bảo transaction với dữ liệu nghiệp vụ. Nó không phải cơ chế deduplication đáng tin cậy.

Hãy đặt unique constraint trên event ID hoặc business key thích hợp; ghi nhận việc đã xử lý cùng thay đổi state của consumer trong một transaction. Với email/API ngoài DB, có thể cần idempotency key hoặc durable job/outbox để giảm nguy cơ side effect trùng.

### 13.2. Không có listener bean thì sao?

Khi listener chưa được register do thiếu component scan hoặc property bị tắt, registry không tự suy đoán “ở tương lai sẽ có một subscriber mới” để tạo publication cho nó. Vì vậy, feature flag và khả năng bật/tắt listener là **quyết định phân phối dữ liệu**, không chỉ là tối ưu khởi tạo bean.

Khi thay đổi tên bean/listener method hoặc loại bỏ listener đang có pending publication, cần đánh giá khả năng khôi phục và tương thích theo cách registry nhận dạng listener của phiên bản Spring Modulith đang sử dụng. Không nên đổi tên bừa rồi giả định mọi publication cũ tự được xử lý đúng.

## 14. Phạm vi bean trong triển khai nhiều instance

Giả sử ứng dụng Spring Modulith được scale lên ba pod:

~~~text
Pod A: ApplicationContext A -> singleton OrderConfirmedListener A
Pod B: ApplicationContext B -> singleton OrderConfirmedListener B
Pod C: ApplicationContext C -> singleton OrderConfirmedListener C
~~~

Có **ba singleton instance**, mỗi instance thuộc container của pod đó. Spring application event trong Pod A không tự broadcast sang Pod B/C. Nếu mỗi pod có nhiều executor threads, mỗi singleton còn phải chịu xử lý đồng thời trong pod của mình.

Khi một hệ thống dùng persistence của publication registry và nhiều instance cùng truy cập, các chính sách chọn/claim/khôi phục pending publication phải được thiết kế theo phiên bản thư viện và storage cụ thể để tránh hai instance xử lý cùng một publication không mong muốn. Kể cả có coordination, listener vẫn nên idempotent.

Nếu muốn một consumer ngoài ứng dụng nhận thông tin, cần **integration event** qua cơ chế externalization, outbox và/hoặc broker phù hợp. Bean scope không tạo được đảm bảo giao event giữa các máy chủ.

## 15. Các lỗi phổ biến liên quan đến listener bean scope

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Event được publish nhưng listener không chạy | Bean không được scan, property/profile tắt, context khác | Kiểm tra bean definition, component scan, context và condition |
| Listener chạy hai lần cho một lần publish | Hai bean definitions, hai method đăng ký hoặc xử lý retry | Kiểm tra số bean và method; thêm idempotency |
| Lỗi `ScopeNotActiveException` | Dùng request-scoped dependency trong async listener không có HTTP request | Dùng singleton listener và truyền metadata cần thiết qua event |
| Sai `orderId` khi chạy tải cao | Singleton listener giữ mutable field | Dùng biến cục bộ và state bền vững |
| Listener không chạy trong integration test | Transaction test tự rollback; phase `AFTER_COMMIT` | Dùng transaction thực sự commit và chờ điều kiện |
| Chỉ lỗi khi deploy nhiều instance | Dựa vào field/cache trong một singleton JVM | Dùng database constraint, idempotency, coordination |
| Listener mới không nhận event cũ | Event chưa được lưu như lịch sử cho listener mới | Backfill/replay có kiểm soát |
| Listener chạy trước khi dữ liệu Orders commit | Dùng `@EventListener` đồng bộ trong transaction publisher | Dùng transactional listener khi cần phản ứng sau commit |
| Listener fail nhưng Orders vẫn thành công | Listener chạy sau commit trong transaction riêng | Thiết kế eventual consistency, retry và theo dõi publication |
| Dùng `@Scope("prototype")` nhưng vẫn trùng side effect | Scope object không giải quyết duplicate event | Dedup theo event ID/business key tại persistence |

### Quy trình chẩn đoán

1. Xác nhận đúng loại event và method signature listener.
2. Xác nhận bean listener thật sự có trong context được dùng để publish.
3. Xác nhận bean definition duy nhất theo ý định; kiểm tra component scan, `@Bean` và auto-configuration.
4. Xác nhận transaction phase, rollback và executor nếu bất đồng bộ.
5. Xác nhận scope/proxy của các dependency được inject vào listener.
6. Xác nhận publication registry nếu cần khôi phục; kiểm tra trạng thái pending/failed.
7. Xác nhận logic xử lý có idempotent và không giữ state nghiệp vụ trong field.

## 16. Kiểm thử phạm vi bean và đăng ký listener

Cần kiểm thử **cả wiring** lẫn **hành vi qua transaction**, vì kiểm tra bean tồn tại chưa đủ chứng minh listener được nhận event đúng.

### 16.1. Kiểm tra module boundary

Spring Modulith cung cấp mô hình phân tích module:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void moduleDependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Bài test này kiểm tra các quy tắc dependency mà Spring Modulith hỗ trợ; nó không xác minh bean scope hoặc xử lý event đúng nghiệp vụ.

### 16.2. Kiểm tra bean hiện diện

Ví dụ trong một integration test có đầy đủ Spring context:

~~~java
@SpringBootTest
class ListenerWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void exactlyOneListenerBeanIsRegistered() {
        String[] names = context.getBeanNamesForType(
                OrderConfirmedListener.class
        );

        assertThat(names).hasSize(1);
    }
}
~~~

Đoạn test giả định các import JUnit, Spring Boot Test và AssertJ đã có; class listener có thể đặt package visibility thích hợp để test truy cập. Một bean tồn tại **chưa đủ** chứng minh `@EventListener` đã được nhận diện; test tiếp theo nên publish event và quan sát side effect.

### 16.3. Kiểm tra xử lý sau commit

Một kịch bản phù hợp:

1. Trong transaction Orders, xác nhận đơn và publish `OrderConfirmed`.
2. **Commit transaction** thay vì để test rollback mặc định.
3. Chờ có một notification job trong DB bằng điều kiện kiểm tra với timeout hữu hạn.
4. Publish lại cùng `eventId` hoặc mô phỏng retry và xác minh vẫn có đúng một job.
5. Cho listener ném lỗi một lần, kiểm tra publication chưa hoàn thành theo backend registry đã cấu hình.
6. Retry/republication; xác minh job và trạng thái publication cuối cùng nhất quán.

`@ApplicationModuleTest` và hỗ trợ `Scenario` có thể hữu ích khi kiểm thử module và listener bất đồng bộ. Cần chọn bootstrap mode/dependencies phù hợp để listener và publisher cần thiết nằm trong test application context.

### 16.4. Kiểm tra luồng concurrency

Chạy hai lời gọi xác nhận cho hai đơn khác nhau, hoặc publish nhiều event đồng thời, rồi kiểm tra kết quả cuối:

- Mọi job phải gắn đúng `orderId`.
- Không có dữ liệu của event A xuất hiện trong job của event B.
- Không có side effect trùng cho cùng event ID.
- Lỗi riêng của một listener không ghi đè state các event khác.

Không nên dùng `Thread.sleep(...)` cố định để giả lập tính bất đồng bộ. Chờ điều kiện đầu ra với timeout, dùng fixture có tính cô lập và kiểm tra kết quả được lưu bền.

## 17. Bài tập thực hành

### Bài tập 1 — Phân tích listener có field mutable

Cho đoạn code:

~~~java
@Component
class AuditListener {

    private UUID lastId;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        lastId = event.orderId();
        auditService.record(lastId);
    }
}
~~~

Hãy giải thích vì sao `lastId` không an toàn khi hai event được xử lý đồng thời và viết lại method sao cho không giữ state theo event ở field. Nếu cần audit bền vững, thiết kế transaction và unique constraint theo event ID.

### Bài tập 2 — Chọn bean scope

Đội phát triển đề xuất ba cách cho listener gửi email:

- `@Scope("singleton")` với injected `NotificationService`.
- `@Scope("prototype")` và field mutable chứa request đang xử lý.
- `@RequestScope` để lấy thông tin user từ `HttpServletRequest`.

Chọn cách phù hợp nhất cho listener sau commit, giải thích lỗi có thể xảy ra với hai cách còn lại và nêu cách truyền thông tin user an toàn qua event contract.

### Bài tập 3 — Chẩn đoán listener không chạy

Trong test, `events.publishEvent(new OrderConfirmed(...))` trả về bình thường nhưng không tạo notification job. Hãy kiểm tra lần lượt bean registration, context, transaction phase, transaction có commit không, executor, profile và publication status.

### Bài tập 4 — Hai pod, một publication

Application chạy hai pod. Sau khi Orders commit event, pod đầu bị crash sau khi ghi notification job nhưng trước khi publication completed. Pod khác khôi phục event. Hãy thiết kế idempotency sao cho vẫn chỉ có một job, không dựa vào biến `Set<UUID>` trong singleton bean.

### Bài tập 5 — Di chuyển event contract

Ban đầu `OrderConfirmed` nằm trong `orders.internal` và Notifications import trực tiếp. Hãy chuyển event sang API công khai của Orders hoặc `@NamedInterface` phù hợp, giữ listener trong module Notifications và viết kiểm tra `ApplicationModules.verify()`.

## 18. Checklist trước khi đưa listener vào production

- [ ] Class listener được Spring quản lý và đăng ký trong đúng `ApplicationContext`.
- [ ] Bean scope được chọn có chủ đích; singleton listener không giữ mutable state theo event.
- [ ] Mọi dependency request/session-scoped có được đánh giá với async listener không có HTTP request.
- [ ] Event contract thuộc API module phù hợp, không rò rỉ entity hoặc repository nội bộ.
- [ ] Phân biệt rõ `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`.
- [ ] Listener cập nhật state trong transaction thích hợp và có quy tắc xử lý khi publisher rollback.
- [ ] Có idempotency bền vững theo `eventId` hoặc business key; không dựa vào cache field trong JVM.
- [ ] Đã xác minh listener không bị khai báo trùng hoặc vô tình bị loại bởi profile/property.
- [ ] Nếu dùng registry, đã xác định cách quan sát và khôi phục publication chưa hoàn thành.
- [ ] Integration test commit transaction, chờ kết quả bất đồng bộ và kiểm tra duplicate/concurrency.
- [ ] Có log/metrics giúp nhận biết listener nào nhận event, lỗi ở đâu và trạng thái publication ra sao.

## 19. Ghi nhớ

**Phạm vi bean listener** quyết định vòng đời object; **ApplicationContext** quyết định phạm vi phân phối sự kiện; **module boundary** quyết định hợp đồng và dependency hợp lệ. Ba khía cạnh này phải được thiết kế cùng nhau để giao tiếp event giữa các module Spring Modulith vừa tách biệt vừa đáng tin cậy.

Singleton là lựa chọn mặc định phù hợp cho đa số listener khi bean không giữ mutable state theo event. Event được truyền qua tham số method, các tác vụ có state giao cho service/repository của module nhận. `@ApplicationModuleListener` giúp xử lý bất đồng bộ sau commit trong transaction riêng; Event Publication Registry hỗ trợ theo dõi và khôi phục publication, còn idempotency, retry và quan sát vận hành bảo đảm kết quả nghiệp vụ không bị nhân đôi khi listener được gọi lại.

Một listener được khởi tạo thành công chưa đủ để chứng minh luồng sự kiện chính xác. Cần xác nhận wiring, phase transaction, module boundary, concurrency, rollback và trạng thái cuối cùng qua test.
