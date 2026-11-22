# ApplicationEventPublisher và sự kiện nghiệp vụ trong ứng dụng

Trong một ứng dụng Spring Boot, một thao tác nghiệp vụ thường dẫn đến nhiều phản ứng khác nhau. Khi một đơn hàng được tạo, hệ thống có thể lưu đơn, cập nhật số liệu, tạo thông báo, ghi audit và kích hoạt những bước xử lý tiếp theo. Nếu service tạo đơn hàng gọi trực tiếp tất cả service liên quan, nó sẽ ngày càng có nhiều dependency và phải biết chi tiết của những chức năng nằm ngoài trách nhiệm chính.

Spring cung cấp `ApplicationEventPublisher` để một thành phần **phát hành sự kiện** và các thành phần khác **lắng nghe sự kiện** đó. Service phát hành chỉ cần mô tả điều đã xảy ra, ví dụ `OrderPlacedEvent`; các listener quyết định có cần phản ứng hay không.

Cơ chế này rất hữu ích để tách những phản ứng phụ khỏi luồng nghiệp vụ cốt lõi. Nhưng cần hiểu ranh giới: **application event là cơ chế thông báo bên trong Spring ApplicationContext; nó không mặc nhiên là message broker, hàng đợi bền vững hay một giao dịch phân tán**. Theo cấu hình mặc định thông thường, listener chạy đồng bộ trong thread phát sự kiện. Muốn xử lý sau commit, chạy bất đồng bộ hoặc bảo đảm giao sự kiện khi ứng dụng crash, cần chọn cơ chế bổ sung phù hợp.

Bài học đi từ cách phát và nhận event cơ bản đến giao dịch, concurrency, độ tin cậy, kiểm thử và các lỗi thiết kế thường gặp.

## 1. Sự kiện nghiệp vụ là gì?

Một **sự kiện nghiệp vụ** (*business event*) mô tả một sự việc đã xảy ra trong miền ứng dụng:

- Đơn hàng đã được đặt: `OrderPlacedEvent`.
- Thanh toán đã thành công: `PaymentSucceededEvent`.
- Tài khoản đã được kích hoạt: `AccountActivatedEvent`.
- Tài liệu đã được phê duyệt: `DocumentApprovedEvent`.
- Báo cáo đã được tạo: `ReportGeneratedEvent`.

Tên sự kiện thường ở **thì quá khứ**, vì nó thông báo một sự thật đã xảy ra. Đây là điểm khác với một command:

| Loại thông điệp | Ví dụ | Ý nghĩa |
|---|---|---|
| Command | `PlaceOrderCommand` | Yêu cầu thực hiện hành động đặt hàng |
| Event | `OrderPlacedEvent` | Việc đặt hàng đã xảy ra |
| Query | `FindOrderQuery` | Yêu cầu đọc thông tin |
| Result | `PlaceOrderResult` | Kết quả của một thao tác cụ thể |

Command thường có một nơi chịu trách nhiệm thực hiện và có thể thất bại. Event có thể được nhiều listener nhận vì chúng quan tâm đến cùng một sự việc đã xảy ra.

### Trước và sau khi dùng event

Cách gọi trực tiếp nhiều dependency:

~~~text
CheckoutService
  |-- OrderRepository
  |-- EmailService
  |-- AuditService
  |-- MetricsService
  +-- LoyaltyService
~~~

Khi có yêu cầu mới, `CheckoutService` thường phải thay đổi để gọi thêm service.

Cách phát sự kiện:

~~~text
                 OrderRepository
                       ^
                       |
CheckoutService ---- lưu đơn
       |
       | publishEvent(OrderPlacedEvent)
       v
 ApplicationEventPublisher
       |
       +--> OrderAuditListener
       |
       +--> OrderMetricsListener
       |
       +--> OrderNotificationListener
       |
       +--> LoyaltyListener
~~~

Service đặt hàng biết rằng cần lưu đơn và phát `OrderPlacedEvent`. Các listener được đăng ký độc lập để xử lý phản ứng tương ứng.

Tuy nhiên, việc bỏ đi dependency trực tiếp không tự động làm hệ thống đơn giản hơn: người bảo trì vẫn phải hiểu **ai đang lắng nghe sự kiện** và phản ứng nào là bắt buộc. Vì thế, chỉ dùng event khi có lý do rõ ràng để tách các thành phần.

## 2. ApplicationEventPublisher là gì?

`ApplicationEventPublisher` là interface của Spring trong package:

~~~java
org.springframework.context.ApplicationEventPublisher
~~~

Nó công bố thao tác phát hành sự kiện:

~~~java
void publishEvent(Object event);
~~~

Spring hỗ trợ cả đối tượng Java thông thường và các lớp kế thừa `ApplicationEvent`.

Ví dụ:

~~~java
public record OrderPlacedEvent(
        Long orderId,
        String customerId,
        Instant occurredAt
) {}
~~~

Tạo và phát:

~~~java
publisher.publishEvent(
        new OrderPlacedEvent(
                order.getId(),
                order.getCustomerId(),
                Instant.now()
        )
);
~~~

Không cần tự implement event bus hoặc giữ danh sách listener trong service. Spring ApplicationContext xử lý việc chuyển sự kiện tới các listener phù hợp.

### Publish event không đồng nghĩa đã xử lý thành công

`publishEvent(event)` là thao tác **bàn giao sự kiện cho cơ chế phát sự kiện**. Nó không bảo đảm mọi listener đã chạy xong trong mọi cấu hình, vì multicaster có thể dùng executor, listener có thể bất đồng bộ hoặc cơ chế khác có thể áp dụng.

Trong cấu hình thông thường với `SimpleApplicationEventMulticaster` không có executor, các listener đồng bộ được gọi ngay trong thread phát sự kiện. Nhưng không nên viết logic nghiệp vụ phụ thuộc một cách ngầm định vào khả năng này nếu sau đó hệ thống có thể cấu hình async.

## 3. Một ví dụ Spring Boot cơ bản

Giả sử ứng dụng có chức năng đặt hàng. Ta cần lưu đơn hàng, sau đó phát sự kiện để các thành phần khác nhận biết.

### 3.1. Định nghĩa event bất biến

~~~java
package com.example.shop.events;

import java.time.Instant;

public record OrderPlacedEvent(
        Long orderId,
        String customerId,
        Instant occurredAt
) {}
~~~

`record` của Java giúp event có dữ liệu được truyền qua constructor và các field không bị gán lại sau khi tạo. Các object được truyền vào record vẫn có thể mutable; nếu payload chứa collection hoặc object mutable, cần sao chép phòng vệ khi cần tính bất biến thực sự.

Nội dung event chỉ gồm dữ liệu mà listener cần. Thường nên mang ID và các giá trị ổn định thay vì đính kèm cả entity JPA đang được quản lý.

### 3.2. Service phát sự kiện

~~~java
package com.example.shop.order;

import com.example.shop.events.OrderPlacedEvent;
import java.time.Clock;
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;
    private final Clock clock;

    public CheckoutService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher,
            Clock clock
    ) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
        this.clock = clock;
    }

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        Order order = Order.from(command);
        Order savedOrder = orderRepository.save(order);

        eventPublisher.publishEvent(
                new OrderPlacedEvent(
                        savedOrder.getId(),
                        savedOrder.getCustomerId(),
                        Instant.now(clock)
                )
        );

        return savedOrder.getId();
    }
}
~~~

Các kiểu `Order`, `OrderRepository` và `PlaceOrderCommand` là thành phần nghiệp vụ của ứng dụng. Ví dụ giả định dự án đã cấu hình persistence và một bean `Clock`, chẳng hạn:

~~~java
@Configuration
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

`CheckoutService` chỉ cần một interface Spring là `ApplicationEventPublisher`. Nó không biết có bao nhiêu listener và cũng không cần import những service xử lý audit hoặc thông báo.

**Lưu ý về giao dịch:** vì `publishEvent` được gọi bên trong phương thức `@Transactional`, event thông thường được phát **trước lúc giao dịch hoàn tất**. Listener đồng bộ có thể chạy trong transaction hiện tại. Điều này không có nghĩa đơn hàng đã commit thành công; phần sau sẽ giải thích `@TransactionalEventListener`.

### 3.3. Listener nhận sự kiện

~~~java
package com.example.shop.audit;

import com.example.shop.events.OrderPlacedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    private final OrderAuditRepository auditRepository;

    public OrderAuditListener(OrderAuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        auditRepository.record(
                event.orderId(),
                event.customerId(),
                event.occurredAt()
        );
    }
}
~~~

Spring tìm method có `@EventListener` trên bean đã được đăng ký. Khi một event đúng kiểu được phát, listener adapter gọi method tương ứng.

Điều kiện cơ bản để ví dụ hoạt động:

- `CheckoutService` và `OrderAuditListener` phải là Spring bean.
- Cấu hình component scanning phải tìm thấy chúng.
- Method `onOrderPlaced` phải có kiểu tham số phù hợp với event.
- Sự kiện được phát qua publisher của ApplicationContext tương ứng.

### 3.4. Thêm listener khác mà không sửa CheckoutService

~~~java
@Component
public class OrderMetricsListener {

    private final OrderMetrics metrics;

    public OrderMetricsListener(OrderMetrics metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        metrics.incrementPlacedOrders();
    }
}
~~~

Khi có thêm nhu cầu cập nhật thống kê, ta đăng ký listener mới. `CheckoutService` vẫn phát một sự kiện như trước.

Đây là điểm mạnh của event: **mở rộng phản ứng đối với một sự việc mà không buộc nơi phát biết từng consumer**.

## 4. Sự kiện phải kế thừa ApplicationEvent không?

Không bắt buộc.

### Cách hiện đại: dùng POJO hoặc record

~~~java
public record AccountActivatedEvent(
        UUID accountId,
        Instant activatedAt
) {}
~~~

Phát sự kiện:

~~~java
publisher.publishEvent(
        new AccountActivatedEvent(accountId, Instant.now())
);
~~~

Listener nhận bằng `@EventListener`:

~~~java
@EventListener
public void onActivated(AccountActivatedEvent event) {
    // ...
}
~~~

Spring có thể bọc POJO event bên trong `PayloadApplicationEvent` khi cần tương tác với cơ chế listener truyền thống. Người viết code thông thường không phải tự tạo wrapper đó.

### Cách kế thừa ApplicationEvent

~~~java
public class AccountActivatedSpringEvent
        extends ApplicationEvent {

    private final UUID accountId;

    public AccountActivatedSpringEvent(
            Object source,
            UUID accountId
    ) {
        super(source);
        this.accountId = accountId;
    }

    public UUID getAccountId() {
        return accountId;
    }
}
~~~

Cách này cần cung cấp `source` trong constructor. Nó hữu ích khi làm việc với API hoặc thư viện cũ dựa trên `ApplicationEvent`.

### So sánh

| Cách mô tả | Ưu điểm | Lưu ý |
|---|---|---|
| Record/POJO | Ít coupling với Spring, nhỏ gọn, dễ dùng trong domain | Thường lắng nghe bằng `@EventListener` |
| Kế thừa `ApplicationEvent` | Tương thích API listener truyền thống | Class phụ thuộc Spring và cần `source` |
| `PayloadApplicationEvent<T>` | Wrapper khi Spring cần biểu diễn payload | Thường không cần tạo trực tiếp |

Với sự kiện nghiệp vụ mới trong Spring Boot, record hoặc class bất biến thông thường là một lựa chọn dễ hiểu.

## 5. @EventListener hoạt động ra sao?

`@EventListener` thuộc package:

~~~java
org.springframework.context.event.EventListener
~~~

Annotation đánh dấu method nhận sự kiện. Spring xác định kiểu event dựa trên tham số method:

~~~java
@Component
public class PaymentListeners {

    @EventListener
    public void onPaymentSucceeded(PaymentSucceededEvent event) {
        // Xử lý thanh toán thành công.
    }

    @EventListener
    public void onPaymentFailed(PaymentFailedEvent event) {
        // Xử lý thanh toán thất bại.
    }
}
~~~

Mỗi method cần có contract phù hợp. Khi sử dụng annotation theo cách thông thường, một method nhận một tham số event. Listener cũng có thể khai báo kiểu event bằng thuộc tính annotation trong một số trường hợp, chẳng hạn method không nhận tham số và chỉ cần phản ứng; nhưng đối với nghiệp vụ, truyền event vào tham số thường rõ ràng hơn.

### Listener nhận event theo kiểu

Spring có thể chuyển một event tới nhiều listener. Nếu không có listener phù hợp, việc phát một event hợp lệ thường không gây lỗi chỉ vì không ai lắng nghe.

Điều này có hai mặt: rất thuận tiện khi một phản ứng là tùy chọn, nhưng nếu một hành động là bắt buộc để hoàn thành use case, không nên dựa vào việc “chắc chắn có listener” mà không có cách kiểm chứng.

### @EventListener có điều kiện

Annotation hỗ trợ thuộc tính `condition` dùng biểu thức SpEL. Ví dụ ý tưởng:

~~~java
@EventListener(condition = "#root.event.totalCents() >= 100000")
public void onLargeOrder(LargeOrderPlacedEvent event) {
    // Chỉ xử lý đơn đạt ngưỡng.
}
~~~

Ví dụ giả định `LargeOrderPlacedEvent` là record có phương thức `totalCents()`. Biểu thức điều kiện được đánh giá khi listener adapter xử lý event, không phải khi ứng dụng đăng ký bean.

Chỉ nên dùng điều kiện SpEL ngắn, dễ hiểu. Với quy tắc nghiệp vụ phức tạp, gọi một policy/service có kiểu trong thân listener sẽ dễ kiểm thử và bảo trì hơn.

### @Order của listener

~~~java
@Component
public class OrderedOrderListeners {

    @Order(10)
    @EventListener
    public void first(OrderPlacedEvent event) {
        // ...
    }

    @Order(20)
    @EventListener
    public void second(OrderPlacedEvent event) {
        // ...
    }
}
~~~

Thứ tự có thể có tác dụng khi các listener được thực thi tuần tự bởi multicaster và cơ chế ordering tương ứng. Không nên dùng `@Order` để tạo phụ thuộc nghiệp vụ bắt buộc giữa các listener, đặc biệt nếu một listener chạy async hoặc được chuyển sang message broker.

Nếu bước B phải chờ kết quả của A, nên thể hiện quan hệ đó bằng lời gọi trực tiếp, một orchestration service hoặc một chuỗi event với trạng thái rõ ràng.

## 6. ApplicationListener: cách nhận event theo interface

Ngoài `@EventListener`, Spring có interface:

~~~java
org.springframework.context.ApplicationListener<E extends ApplicationEvent>
~~~

Ví dụ:

~~~java
@Component
public class ContextRefreshedLogger
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println(
                "Context refreshed: "
                        + event.getApplicationContext().getId()
        );
    }
}
~~~

Cách này thường gặp ở framework integration hoặc khi muốn listener là một class có contract rõ.

Đối với business event là POJO/record, `@EventListener` thường tiện hơn. Không thể dùng `ApplicationListener<OrderPlacedEvent>` theo kiểu trên nếu `OrderPlacedEvent` không kế thừa `ApplicationEvent`, vì generic bound của interface yêu cầu event subtype phù hợp.

### Listener dưới dạng bean và listener được đăng ký sớm

Listener nghiệp vụ thông thường là bean nên chỉ hoạt động sau khi bean registration đã sẵn sàng. Một số startup event như `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` xảy ra trước khi context tạo bean; chúng cần listener được đăng ký từ sớm qua `SpringApplication.addListeners(...)` hoặc cơ chế bootstrap tương ứng.

Không nên mong một `@Component` chứa `@EventListener` nhận được mọi event bootstrap rất sớm. Điều này khác với event nghiệp vụ phát sau khi ứng dụng đã chạy.

## 7. Đồng bộ là hành vi mặc định thông thường

Theo mặc định, Spring ApplicationContext thường dùng `SimpleApplicationEventMulticaster` với cách gọi listener đồng bộ. Khi service phát event, các listener thông thường chạy trong thread phát sự kiện.

Ví dụ:

~~~java
@Service
public class RegistrationService {

    private final ApplicationEventPublisher publisher;

    public RegistrationService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void register(UUID accountId) {
        System.out.println("A. Before publish");

        publisher.publishEvent(
                new AccountActivatedEvent(accountId, Instant.now())
        );

        System.out.println("C. After publish");
    }
}
~~~

Listener:

~~~java
@Component
public class RegistrationLogger {

    @EventListener
    public void onActivated(AccountActivatedEvent event) {
        System.out.println("B. In listener");
    }
}
~~~

Với một listener đồng bộ và multicaster mặc định, thứ tự in có thể là:

~~~text
A. Before publish
B. In listener
C. After publish
~~~

Phát event không tự tạo thread mới. Nếu listener gọi HTTP chậm hoặc truy vấn database lâu, lời gọi `publishEvent` cũng có thể mất thời gian và ảnh hưởng response.

### Tác động đến lỗi và transaction

Giả sử listener đồng bộ ném một unchecked exception và không có `ErrorHandler` đặc biệt trên multicaster. Exception có thể truyền ngược tới lời gọi `publishEvent`. Nếu lời gọi đang ở trong một phương thức `@Transactional` và exception làm phương thức thất bại theo quy tắc rollback, transaction có thể rollback.

Điều này có thể phù hợp khi listener là một phần bắt buộc của quy trình; cũng có thể là lỗi thiết kế nếu một dịch vụ gửi email thất bại lại làm hủy giao dịch tạo đơn hàng.

Không nên giả định listener “chạy tách biệt” chỉ vì được gọi qua event publisher. **Event giúp giảm coupling về người gọi; nó không mặc nhiên cách ly thời gian chạy, lỗi hay transaction.**

## 8. Ví dụ lỗi thường gặp: gửi email trước khi giao dịch commit

Xét service:

~~~java
@Service
public class CheckoutService {

    @Transactional
    public void placeOrder(PlaceOrderCommand command) {
        Order order = orderRepository.save(
                Order.from(command)
        );

        publisher.publishEvent(
                new OrderPlacedEvent(
                        order.getId(),
                        order.getCustomerId(),
                        Instant.now()
                )
        );

        // Có thể còn thao tác DB khác gây lỗi.
        updateInventory(order);
    }
}
~~~

Listener thường:

~~~java
@Component
public class ConfirmationEmailListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        emailSender.sendConfirmation(event.orderId());
    }
}
~~~

Nếu listener chạy đồng bộ tại thời điểm `publishEvent`, email có thể được gửi **trước khi transaction commit**. Sau đó `updateInventory` có thể thất bại, transaction rollback, nhưng email đã được gửi ra ngoài. Hệ thống sẽ thông báo có đơn hàng dù đơn hàng không tồn tại trong database như dự đoán.

Đây là lý do cần phân biệt:

- **Một event đã được publish** trong code.
- **Giao dịch database đã commit** thành công.
- **Side effect bên ngoài đã hoàn tất** và có thể kiểm chứng.

Ba trạng thái này không đồng nhất.

## 9. @TransactionalEventListener: chọn thời điểm theo transaction

Spring có `@TransactionalEventListener` để gắn listener với giai đoạn transaction. Annotation này thuộc package:

~~~java
org.springframework.transaction.event.TransactionalEventListener
~~~

Ví dụ gửi thông báo sau khi transaction commit:

~~~java
@Component
public class ConfirmationNotificationListener {

    private final NotificationService notificationService;

    public ConfirmationNotificationListener(
            NotificationService notificationService
    ) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterOrderCommitted(OrderPlacedEvent event) {
        notificationService.sendOrderConfirmation(
                event.orderId()
        );
    }
}
~~~

`AFTER_COMMIT` cũng là phase mặc định của `@TransactionalEventListener`. Listener được gắn vào transaction synchronization và chỉ chạy khi transaction liên quan commit thành công.

Điểm quan trọng: `@TransactionalEventListener` giải quyết **thời điểm xử lý so với transaction**, không tự biến event thành message bền vững hoặc bất đồng bộ.

### Các phase phổ biến

| Phase | Khi nào callback được gọi? | Trường hợp cân nhắc |
|---|---|---|
| `BEFORE_COMMIT` | Trước khi transaction commit | Kiểm tra hoặc cập nhật trạng thái phải nằm trong cùng transaction, nếu phù hợp |
| `AFTER_COMMIT` | Sau khi commit thành công | Phản ứng sau khi dữ liệu được xác nhận |
| `AFTER_ROLLBACK` | Khi transaction rollback | Dọn trạng thái tạm hoặc ghi nhận thất bại, có lưu ý về persistence |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, bất kể commit hay rollback | Cleanup/telemetry cần biết transaction đã hoàn tất |

Thời điểm callback còn phụ thuộc transaction manager và cơ chế synchronization. Đừng giả định mọi cách quản lý transaction trong ứng dụng đều có cùng ranh giới thread.

### Không có transaction thì sao?

Mặc định, một `@TransactionalEventListener` được gọi trong bối cảnh **không có transaction đang hoạt động** sẽ không thực thi callback theo phase.

Nếu muốn listener vẫn chạy khi không có transaction, có thể dùng:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void onPlaced(OrderPlacedEvent event) {
    // ...
}
~~~

Khi không có transaction, fallback cho phép listener xử lý ngay mà không đợi một commit không tồn tại. Vì vậy, chỉ bật `fallbackExecution = true` khi semantics này thực sự chấp nhận được.

### Cảnh báo về truy cập database trong AFTER_COMMIT

Sau commit, một số transaction resource có thể vẫn còn gắn với thread trong khoảng thời gian callback chạy. Nếu listener cố thực hiện thêm database write bằng transaction propagation mặc định, thao tác đó có thể tham gia resource của transaction đã hoàn tất nhưng không được commit như mong đợi.

Nếu callback sau commit cần ghi dữ liệu mới một cách chắc chắn, hãy xem xét một transaction riêng:

~~~java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAfterCommit(Long orderId) {
        auditRepository.recordCommittedOrder(orderId);
    }
}
~~~

Listener gọi service khác qua Spring proxy:

~~~java
@Component
public class CommittedOrderAuditListener {

    private final AuditWriter auditWriter;

    public CommittedOrderAuditListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener
    public void onPlaced(OrderPlacedEvent event) {
        auditWriter.recordAfterCommit(event.orderId());
    }
}
~~~

`REQUIRES_NEW` mở transaction độc lập khi lời gọi được proxy xử lý đúng. Đặt annotation lên một phương thức rồi gọi nó nội bộ trong cùng class có thể không đi qua transaction proxy. Cũng cần cân nhắc rằng write mới sau commit có lỗi thì giao dịch đặt hàng gốc đã commit và không thể tự rollback theo lỗi đó.

### Giao dịch reactive

Với reactive transaction do `ReactiveTransactionManager` quản lý, transaction context thường nằm trong Reactor context thay vì ThreadLocal. Spring Framework hiện đại hỗ trợ transactional event listener cho reactive transaction khi **transaction context được mang theo trong event source/payload theo cơ chế hỗ trợ**, chẳng hạn qua `TransactionalEventPublisher`.

Không nên giả định `publishEvent` thông thường ở một reactive pipeline luôn có thể truy cập cùng transaction context theo cách của imperative thread-bound transaction. Khi dùng WebFlux/R2DBC, hãy kiểm tra contract phiên bản Spring và chọn cơ chế phát transactional event đúng cho reactive context.

## 10. @Async và @EnableAsync: xử lý listener bất đồng bộ

Một listener có thể chậm vì gửi email, gọi API hoặc xử lý file. Spring hỗ trợ phương thức async qua `@Async`.

Bật async support:

~~~java
@Configuration
@EnableAsync
public class AsyncEventConfiguration {

    @Bean("businessEventExecutor")
    public Executor businessEventExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("business-event-");
        executor.initialize();

        return executor;
    }
}
~~~

Dùng listener:

~~~java
@Component
public class AsyncOrderNotificationListener {

    private final EmailSender emailSender;

    public AsyncOrderNotificationListener(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    @Async("businessEventExecutor")
    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        emailSender.sendConfirmation(event.orderId());
    }
}
~~~

`@Async` yêu cầu xử lý qua cơ chế Spring async/proxy tương ứng. Listener có thể được thực thi trong thread của executor được chọn, khiến thread phát sự kiện không cần chờ toàn bộ công việc hoàn tất.

### Async làm thay đổi gì?

| Khía cạnh | Listener đồng bộ | Listener `@Async` |
|---|---|---|
| Thread thường dùng | Thread phát event | Thread executor |
| Publisher chờ listener? | Thường chờ | Thường không chờ completion |
| Exception | Có thể truyền về publisher | Thường được xử lý ở executor/async error handler |
| ThreadLocal transaction | Có thể có khi cùng thread | Không được tự động truyền sang thread khác |
| Thứ tự hoàn tất | Theo hành vi gọi đồng bộ | Có thể thay đổi theo scheduling |
| Crash sau publish | Vẫn có thể mất event/công việc | Vẫn có thể mất công việc đang chờ |

`@Async` là công cụ về **concurrency và latency**, không phải bảo đảm giao hàng bền vững.

### Chú ý lỗi trong @Async void listener

Phương thức `void` chạy async không trả exception trực tiếp về publisher. Lỗi cần được ghi log, theo dõi và xử lý theo cơ chế `AsyncUncaughtExceptionHandler` hoặc chiến lược khác. Không nên bỏ qua lỗi chỉ vì request gốc đã trả thành công.

Nếu cần retry, backpressure hoặc độ tin cậy cao, cần chọn executor và cơ chế retry có giới hạn; với nghiệp vụ quan trọng, một hàng đợi/message broker bền vững thường phù hợp hơn.

### Async và transaction

Nếu `@Async @EventListener` nhận event ngay khi service đang trong transaction, listener có thể chạy trên thread khác **trước khi transaction commit**. Nó không chia sẻ ThreadLocal transaction của publisher. Listener có thể không nhìn thấy dữ liệu mới hoặc thấy trạng thái chưa nhất quán.

Nếu cần xử lý sau commit rồi mới gửi việc sang executor, có thể kết hợp `@TransactionalEventListener(phase = AFTER_COMMIT)` với `@Async`, với điều kiện cơ chế async và transaction của dự án được cấu hình đúng. Cách này vẫn không bảo đảm durable delivery nếu process crash sau commit nhưng trước khi task hoàn thành.

## 11. Khi nào nên dùng event và khi nào gọi service trực tiếp?

Event không phải lúc nào cũng tốt hơn method call. Hãy phân biệt **bước bắt buộc để hoàn thành use case** với **phản ứng mở rộng sau khi sự việc xảy ra**.

Ví dụ, khi tạo đơn hàng:

- Xác thực giá và quyền mua có thể là bước bắt buộc.
- Giảm tồn kho theo quy tắc nhất quán có thể là một phần của transaction chính hoặc một workflow được điều phối rõ ràng.
- Gửi email xác nhận thường là phản ứng sau khi đơn hàng commit.
- Cập nhật dashboard thống kê có thể chạy độc lập hoặc eventual consistent.

Nếu một bước phải hoàn tất trước khi trả kết quả thành công, gọi service trực tiếp trong orchestration thường rõ hơn:

~~~java
@Transactional
public Long placeOrder(PlaceOrderCommand command) {
    pricingPolicy.validate(command);
    inventoryService.reserve(command.items());

    Order saved = orderRepository.save(
            Order.from(command)
    );

    publisher.publishEvent(
            new OrderPlacedEvent(
                    saved.getId(),
                    saved.getCustomerId(),
                    Instant.now()
            )
    );

    return saved.getId();
}
~~~

Nếu `inventoryService.reserve(...)` là yêu cầu bắt buộc, để nó xuất hiện trực tiếp trong use case giúp người đọc thấy quy trình và xử lý thất bại có chủ đích. Event phù hợp cho các consumer cần biết “đơn hàng đã đặt”, không bắt buộc phải cùng quyết định kết quả chính của lời gọi.

### Bảng lựa chọn

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Một bước bắt buộc phải thành công trước khi trả kết quả | Gọi service trực tiếp / orchestration |
| Nhiều consumer nội bộ muốn biết một sự việc | Application event |
| Chỉ chạy phản ứng khi transaction commit | `@TransactionalEventListener` |
| Công việc có thể chạy chậm nhưng không yêu cầu bền vững | `@Async` hoặc executor phù hợp |
| Event phải được giao ngay cả khi process crash | Transactional outbox / message broker + relay |
| Giao tiếp giữa nhiều service/ứng dụng | Message broker, API hoặc integration event |
| Một chuỗi bước dài cần retry/compensation | Workflow/saga có trạng thái |

### Tránh giấu dependency bắt buộc

Nếu `PlaceOrder` chỉ đúng khi listener A đã chạy và tạo một bản ghi phụ, nhưng code không thể hiện được quan hệ đó, event đã làm mờ luồng nghiệp vụ. Hãy đặt quan hệ bắt buộc vào service điều phối hoặc một transaction workflow rõ ràng; dùng event cho phần có thể tách biệt về mặt trách nhiệm.

## 12. Event payload nên chứa gì?

Một event tốt nên đủ thông tin để listener biết sự việc nào đã xảy ra, nhưng không mang theo toàn bộ trạng thái nhạy cảm hoặc object có vòng đời khó kiểm soát.

Ví dụ:

~~~java
public record OrderPlacedEvent(
        UUID eventId,
        Long orderId,
        String customerId,
        Instant occurredAt,
        String correlationId
) {}
~~~

Ý nghĩa:

- `eventId`: nhận diện duy nhất một lần phát sự kiện; hữu ích cho trace hoặc deduplication nếu event được chuyển ra ngoài.
- `orderId`: ID đối tượng nghiệp vụ.
- `customerId`: tham chiếu khách hàng, nếu listener cần.
- `occurredAt`: thời điểm sự việc được ghi nhận.
- `correlationId`: liên kết log/trace của cùng một luồng công việc.

Không phải event nào cũng cần đủ năm trường. Hãy chỉ thêm dữ liệu có ý nghĩa cho consumer.

### Vì sao nên tránh mang trực tiếp JPA entity?

Ví dụ dễ gây lỗi:

~~~java
public record OrderPlacedEvent(Order order) {}
~~~

Nếu listener chạy sau transaction hoặc async, `Order` có thể:

- Không còn gắn với persistence context.
- Có lazy association chưa được load, dẫn tới lỗi.
- Bị thay đổi mutable sau khi event được phát.
- Chứa dữ liệu nhạy cảm ngoài nhu cầu listener.
- Mang proxy hoặc state gắn với ORM làm tăng coupling.

Thường nên mang ID và các giá trị ổn định. Listener có thể tải dữ liệu cần thiết trong transaction riêng hoặc đọc từ payload đã được chuẩn hóa.

### Event là snapshot hay thông báo cần truy vấn?

Có hai kiểu phổ biến:

- **Reference event:** chứa ID; listener tự truy vấn trạng thái mới nhất.
- **Fact snapshot:** chứa những giá trị quan trọng tại thời điểm sự việc xảy ra.

Nếu listener cần biết **giá tại lúc đặt hàng**, việc chỉ đọc trạng thái hiện tại sau này có thể không chính xác khi đơn đã được cập nhật. Khi đó nên đưa giá trị bất biến liên quan vào event hoặc dùng bản ghi lịch sử phù hợp.

Nếu event chỉ dùng để kích hoạt một bước tra cứu, ID có thể đủ. Hãy xác định semantics này trước khi thiết kế payload.

## 13. Lỗi của listener ảnh hưởng publisher thế nào?

Với multicaster đồng bộ mặc định, exception từ listener có thể truyền về publisher. Ví dụ:

~~~java
@Component
public class FailingListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        throw new IllegalStateException("Audit unavailable");
    }
}
~~~

Nếu `publishEvent` xảy ra bên trong `@Transactional` và exception không được xử lý, transaction gốc có thể rollback theo quy tắc rollback của Spring.

Một vấn đề khác là **listener nào đã chạy trước khi lỗi xuất hiện**. Nếu listener đầu đã gửi HTTP request ra ngoài rồi listener sau ném exception, rollback database không hoàn tác request bên ngoài.

### Có thể cấu hình ErrorHandler cho multicaster?

`SimpleApplicationEventMulticaster` cho phép cấu hình `ErrorHandler` và executor trong những trường hợp muốn tùy chỉnh cách xử lý listener. Đây là extension point cấp hạ tầng và cần cân nhắc tác động toàn ứng dụng.

Ví dụ khái niệm:

~~~java
@Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
public ApplicationEventMulticaster applicationEventMulticaster() {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();

    multicaster.setErrorHandler(error -> {
        // Ghi log / đo lỗi theo chiến lược đã thống nhất.
    });

    return multicaster;
}
~~~

Đăng ký multicaster tùy chỉnh thay đổi cách event được phân phối trong context, nên chỉ thực hiện khi thật sự cần. Nếu error handler chỉ ghi log và nuốt exception, caller có thể không nhận ra listener bị lỗi. Với công việc bắt buộc, đây có thể là hành vi không phù hợp.

Hãy chọn chiến lược lỗi dựa trên semantics nghiệp vụ, không đơn thuần để loại bỏ exception khỏi log.

### Phát sự kiện không có hàng đợi retry mặc định

`ApplicationEventPublisher` không tự lưu một “pending event” vào database để chạy lại khi lỗi. Nếu listener thất bại, Spring không mặc nhiên đảm bảo phát lại sau khi ứng dụng restart. Đây là giới hạn nền tảng cần nhớ.

## 14. Transactional outbox: khi sự kiện phải được giao đáng tin cậy

Giả sử sau khi đơn hàng commit, hệ thống **bắt buộc** gửi thông tin sang dịch vụ vận chuyển. Nếu chỉ dùng:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendToShipping(OrderPlacedEvent event) {
    shippingClient.createShipment(event.orderId());
}
~~~

có một khoảng rủi ro: transaction database đã commit, nhưng process có thể crash trước hoặc trong lúc callback gọi dịch vụ vận chuyển. Event chỉ nằm trong bộ nhớ nên không có một bản ghi bền vững để tự động xử lý lại.

Một giải pháp phổ biến là **transactional outbox**.

### Luồng outbox

~~~text
PlaceOrder transaction
        |
        +--> INSERT order
        |
        +--> INSERT outbox_event
        |
        +--> COMMIT cùng transaction
                    |
                    v
              Outbox table
                    |
                    v
              Relay / Worker
                    |
              publish tới broker
                    |
                    v
             Consumer xử lý
                    |
              acknowledge / retry
~~~

Dữ liệu đơn hàng và outbox record được lưu **trong cùng transaction database**. Nếu transaction rollback, cả hai cùng rollback. Nếu commit, bản ghi outbox vẫn tồn tại để worker gửi tiếp kể cả sau khi process restart.

### Ví dụ lưu outbox trong transaction

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final Clock clock;

    public CheckoutService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            Clock clock
    ) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.clock = clock;
    }

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        Order saved = orderRepository.save(
                Order.from(command)
        );

        OutboxMessage message = OutboxMessage.orderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                Instant.now(clock)
        );

        outboxRepository.save(message);

        return saved.getId();
    }
}
~~~

Các kiểu `OutboxRepository` và `OutboxMessage` là abstraction minh họa; dự án cần định nghĩa bảng, schema, serialization, retry và trạng thái giao hàng.

Một worker riêng đọc các bản ghi chưa gửi, gửi sang broker và cập nhật trạng thái. Nếu gửi thành công nhưng worker crash trước khi đánh dấu đã gửi, bản ghi có thể được phát lại. Vì vậy **consumer cần idempotent hoặc có cơ chế deduplication theo eventId**.

Outbox thường cung cấp khả năng tiến tới **at-least-once delivery** khi relay, broker và consumer được thiết kế đúng; không tự bảo đảm exactly-once toàn hệ thống.

### Có thể kết hợp application event với outbox không?

Có. Một application event có thể giúp thông báo cho các thành phần nội bộ rằng một outbox record mới xuất hiện, để đánh thức relay nhanh hơn. Nhưng **outbox record mới là nguồn sự thật bền vững**. Nếu event trong bộ nhớ bị mất, worker định kỳ vẫn phải có khả năng quét outbox để xử lý các bản ghi còn lại.

## 15. Event nội bộ và integration event

Không nên đồng nhất sự kiện trong ApplicationContext với message trao đổi giữa các microservice.

| Tiêu chí | Application event | Integration event |
|---|---|---|
| Phạm vi | Một Spring ApplicationContext/JVM theo cơ chế local | Qua ranh giới process/service |
| Transport mặc định | Event multicaster trong bộ nhớ | Broker, HTTP hoặc transport đã chọn |
| Serialization | Thường không cần | Thường cần schema/serialization |
| Delivery khi crash | Không bền vững mặc định | Tùy broker/producer/consumer và persistence |
| Transaction coordination | Có thể dùng transactional listener local | Cần outbox hoặc cơ chế đảm bảo nhất quán |
| Coupling | Thông qua class/type trong cùng ứng dụng | Thông qua message contract và version |

Một application event có thể được chuyển thành integration event, nhưng đó là bước thiết kế riêng. Không nên đưa thẳng entity hoặc object chứa Spring proxy qua mạng.

### Versioning sự kiện bên ngoài

Khi một event được gửi sang hệ thống khác, payload trở thành hợp đồng tích hợp. Cần cân nhắc:

- Event name và schema version.
- Khả năng thêm field không phá consumer cũ.
- Event ID và idempotency key.
- Timestamp và quy tắc timezone.
- Correlation/causation ID nếu có.
- Chính sách dữ liệu nhạy cảm.
- Dead-letter queue hoặc chiến lược xử lý message lỗi.

Những yếu tố này thường không cần thiết cho một listener local đơn giản, nhưng rất quan trọng khi vượt ra ngoài một Spring context.

## 16. ApplicationEventPublisher trong quan hệ với transaction và thread

Có thể tóm tắt các lựa chọn:

| Thiết kế | Thời điểm thông thường | Thread | Đảm bảo khi crash |
|---|---|---|---|
| `@EventListener` mặc định | Ngay lúc publish | Thread publisher | Không |
| `@Async @EventListener` | Có thể xử lý sau khi submit | Thread executor | Không |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công | Thường callback transaction thread | Không |
| `@Async @TransactionalEventListener(AFTER_COMMIT)` | Submit công việc sau commit | Thread executor | Không |
| Outbox + relay | Sau khi outbox commit và relay chạy | Worker/process riêng | Có bản ghi bền vững để retry |

Bảng này mô tả các cấu hình thường gặp; nếu có custom `ApplicationEventMulticaster` hoặc transaction manager đặc biệt, semantics thực tế có thể khác. Hãy kiểm tra cách event được phân phối trong ứng dụng đang chạy.

### Không phụ thuộc vào ThreadLocal một cách ngầm định

Một listener async không tự nhận transaction hoặc request context từ thread publisher. Nếu cần thông tin như user ID hoặc correlation ID, hãy đưa giá trị cần thiết vào event payload hoặc dùng cơ chế context propagation phù hợp.

Không nên trông chờ `SecurityContextHolder`, MDC hoặc transaction context tự xuất hiện trong thread mới. Spring có một số executor decorator và công cụ propagation, nhưng chúng cần được cấu hình rõ ràng.

### Thread safety của event payload

Một event được chuyển sang thread khác nên có payload an toàn để chia sẻ. Record chỉ làm tham chiếu field không đổi; nếu field chứa `List` mutable, byte array hoặc entity mutable, listener có thể thấy state thay đổi khi đang xử lý.

Ưu tiên immutable value objects, ID, primitive/value types và immutable copies khi cần.

## 17. Event ordering và nhiều ApplicationContext

Các listener cùng nhận một event nhưng không nên dựa vào một thứ tự “tự nhiên” không được khai báo.

Trong chế độ synchronous, `@Order` có thể xác định thứ tự gọi khi multicaster dùng order comparator. Nhưng khi listener dùng `@Async`, thứ tự hoàn tất của task không còn được bảo đảm theo thứ tự submit. Nếu event đi qua broker, thứ tự còn phụ thuộc partition, consumer group và quy tắc delivery.

### Event không phải workflow engine

Giả sử ba listener lần lượt cần:

1. Tạo hóa đơn.
2. Sau đó tạo vận đơn.
3. Sau đó thông báo khách hàng.

Nếu B cần kết quả của A và C cần kết quả của B, không nên chỉ đăng ký cả ba trên cùng event rồi hy vọng `@Order` giải quyết workflow. Dùng orchestration service hoặc các event thể hiện rõ trạng thái từng bước:

~~~text
OrderPlaced
     |
     v
InvoiceCreated
     |
     v
ShipmentCreated
     |
     v
CustomerNotified
~~~

Nếu quá trình dài và có thể thất bại từng bước, cần lưu trạng thái, retry và cơ chế bù trừ phù hợp.

### Parent/child ApplicationContext

Trong một số ứng dụng phức tạp có nhiều ApplicationContext theo quan hệ cha-con, event từ child có thể được truyền lên parent theo cơ chế Spring. Listener ở parent có thể nhận event phát từ child. Điều này đôi khi gây hành vi listener chạy nhiều lần nếu cùng một listener hoặc cấu hình được đăng ký ở nhiều context.

Khi gặp duplicate event handling, hãy kiểm tra cả số context và nơi bean listener được đăng ký, bên cạnh việc kiểm tra số lần publisher gọi `publishEvent`.

## 18. Sự kiện trong giai đoạn khởi động: liên hệ với runner

Chương này thuộc nhóm “Sự kiện và runner”, nên cần phân biệt event nghiệp vụ với startup event và runner.

`ApplicationRunner` và `CommandLineRunner` được Spring Boot gọi sau khi ApplicationContext đã refresh thành công, trước khi phát `ApplicationReadyEvent` trong luồng startup thông thường. Có thể phát event nghiệp vụ từ runner nếu runner thực sự thực hiện một tác vụ cần thông báo:

~~~java
@Component
public class DemoSeedRunner implements ApplicationRunner {

    private final SeedService seedService;

    public DemoSeedRunner(SeedService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seedDemoData();
    }
}
~~~

Nếu `seedDemoData()` tạo một đối tượng nghiệp vụ thành công và muốn thông báo, nó có thể publish event trong service. Không cần để runner biết mọi listener.

### ApplicationReadyEvent là sự kiện lifecycle

~~~java
@Component
public class ReadinessListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Thực hiện việc phù hợp sau khi ứng dụng sẵn sàng.
    }
}
~~~

`ApplicationReadyEvent` có nghĩa startup đã đi tới mốc sẵn sàng. Nó khác `OrderPlacedEvent` vì không mô tả một hành vi nghiệp vụ cụ thể.

Nếu công việc mất nhiều thời gian hoặc có thể thất bại, hãy cân nhắc nó thuộc startup bắt buộc, post-start task, scheduler hay workflow bền vững. Không nên biến mọi công việc nền thành listener của `ApplicationReadyEvent` chỉ để “chạy một lần”.

### Sự kiện startup rất sớm

Những event như `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` xảy ra trước khi bean listener thông thường có thể được đăng ký. Khi muốn xử lý chúng, đăng ký listener từ sớm với `SpringApplication` hoặc cơ chế bootstrap thích hợp.

Event nghiệp vụ được publish sau khi ApplicationContext đã sẵn sàng thường không gặp giới hạn này.

## 19. Kiểm thử việc phát sự kiện và listener

Có thể kiểm thử ở nhiều tầng:

- **Unit test service:** xác nhận service publish đúng event.
- **Unit test listener:** gọi method listener với event giả và kiểm tra hành vi.
- **Spring context test:** xác nhận event được chuyển tới listener.
- **Transaction integration test:** xác nhận `AFTER_COMMIT` chỉ chạy sau commit thật.
- **Outbox integration test:** xác nhận business data và outbox record được lưu cùng transaction.

### Unit test publisher bằng Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    OrderRepository orderRepository;

    @Mock
    ApplicationEventPublisher publisher;

    @Mock
    Clock clock;

    @Test
    void publishesEventAfterSavingOrder() {
        // Arrange orderRepository và Clock.
        // Gọi CheckoutService.placeOrder(...).
        // Verify publisher.publishEvent(...) bằng ArgumentCaptor.
    }
}
~~~

Ví dụ là skeleton minh họa; các mock, dữ liệu và assertion cụ thể phụ thuộc API của dự án. Unit test này không tự kiểm tra Spring listener dispatch hoặc transaction commit.

### Ghi nhận event trong Spring test

Spring Test cung cấp `@RecordApplicationEvents` cùng interface `ApplicationEvents`. Ví dụ:

~~~java
@SpringBootTest
@RecordApplicationEvents
class CheckoutEventsIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    ApplicationEvents applicationEvents;

    @Test
    void publishesOrderPlacedEvent() {
        Long orderId = checkoutService.placeOrder(
                new PlaceOrderCommand(/* dữ liệu hợp lệ */)
        );

        boolean found = applicationEvents
                .stream(OrderPlacedEvent.class)
                .anyMatch(event ->
                        event.orderId().equals(orderId)
                );

        assertTrue(found);
    }
}
~~~

`@RecordApplicationEvents` thuộc Spring Test context event support. Ví dụ này giả định repository, persistence và command hợp lệ đã được cấu hình trong test.

Chú ý: nếu test method được đánh dấu `@Transactional` và Spring Test rollback transaction vào cuối test, listener `AFTER_COMMIT` sẽ không chạy vì commit không xảy ra. Muốn kiểm tra callback sau commit, hãy dùng test điều khiển transaction và commit thực sự hoặc một integration test không bao toàn bộ method trong rollback transaction.

### Kiểm thử thời điểm AFTER_COMMIT

Một tình huống cần xác nhận:

1. Bắt đầu transaction, lưu order, publish event.
2. Chưa commit: callback `AFTER_COMMIT` chưa được gọi.
3. Commit: callback được gọi.
4. Lặp lại với rollback: callback `AFTER_COMMIT` không được gọi.

Có thể dùng `TransactionTemplate` với transaction manager thật để chủ động kiểm soát transaction và assertion. Đây là loại test hữu ích khi side effect chỉ được phép chạy sau khi database commit.

### Kiểm thử async

Không nên dùng `Thread.sleep(...)` cố định rồi cho rằng listener chắc đã chạy. Dùng cơ chế đồng bộ trong test như latch, future, awaitility hoặc quan sát trạng thái có timeout được kiểm soát. Nếu test chỉ cần kiểm tra logic listener, gọi method trực tiếp như một unit test sẽ đơn giản hơn.

## 20. Lỗi thường gặp với ApplicationEventPublisher

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `@EventListener` không chạy | Listener không phải Spring bean hoặc nằm ngoài component scan | Kiểm tra bean registration và package scan |
| Publish không gây lỗi nhưng không có phản ứng | Không có listener đúng kiểu hoặc condition listener không match | Kiểm tra event type và `@EventListener(condition)` |
| Email được gửi dù transaction rollback | Listener thông thường chạy trước commit | Dùng `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox |
| Transaction rollback khi listener thất bại | Listener đồng bộ ném exception trong luồng transaction | Quyết định lại ranh giới trách nhiệm và lỗi |
| `@TransactionalEventListener` không chạy | Event được publish ngoài transaction, `fallbackExecution` mặc định false | Kiểm tra transaction boundary và proxy |
| Listener async không thấy dữ liệu mới | Task chạy trước commit hoặc trên thread không chia sẻ transaction | Xử lý sau commit, tải dữ liệu trong transaction mới |
| Listener xử lý hai lần | Publish hai lần, context hierarchy, retry hoặc duplicate delivery | Dùng event ID/log và kiểm tra nguồn phát |
| Mất event sau restart | Event chỉ nằm trong bộ nhớ | Outbox và delivery mechanism bền vững |
| Listener sau commit ghi DB không thấy dữ liệu được lưu | Dùng resource transaction đã hoàn tất hoặc transaction boundary sai | Dùng service transaction mới như `REQUIRES_NEW` khi phù hợp |
| Thứ tự listener sai kỳ vọng | Async, ordering hoặc multicaster tùy chỉnh | Không dùng ordering để thay thế workflow |
| LazyInitializationException trong listener | Truy cập entity JPA sau transaction | Chuyển payload sang ID/immutable snapshot |
| Lỗi listener bị mất dấu | Async void method không truyền lỗi về publisher | Logging, monitoring, error handling và retry |

### Tránh vòng lặp event vô hạn

Một listener có thể publish sự kiện khác. Nếu listener của `AEvent` publish lại `AEvent` mà không có điều kiện dừng, hệ thống có thể đệ quy hoặc tạo chuỗi công việc liên tục.

~~~text
AEvent --> Listener A
  ^            |
  |            |
  +-- publish AEvent
~~~

Khi cần event chain, hãy xác định sự kiện đầu vào, sự kiện đầu ra và trạng thái chuyển đổi. Đặt tên event theo các bước nghiệp vụ khác nhau và thiết kế cơ chế ngăn lặp/retry vô hạn.

### Không gắn side effect quan trọng vào “fire-and-forget” mà thiếu theo dõi

Nếu yêu cầu phải gửi thông báo hoặc cập nhật một hệ thống khác, cần cơ chế retry, monitoring và lưu trạng thái phù hợp. `@Async` giúp giảm độ trễ của publisher, nhưng không cung cấp bảo đảm tác vụ hoàn thành.

## 21. Quy trình thiết kế event nghiệp vụ

Một quy trình thực dụng khi thêm event mới:

1. **Xác định sự việc đã xảy ra.** Tên event ở dạng quá khứ, ví dụ `OrderPlacedEvent`.
2. **Chỉ rõ publisher.** Service nào có quyền kết luận sự việc đã xảy ra và ở thời điểm nào?
3. **Xác định transaction boundary.** Publish trong transaction hay sau commit? Có side effect nào cần đợi commit?
4. **Thiết kế payload.** Dùng dữ liệu bất biến, ID và thông tin thực sự cần.
5. **Phân loại consumer.** Bắt buộc đồng bộ, sau commit, async hay cần giao bền vững?
6. **Đặt listener theo trách nhiệm.** Audit, metrics, notifications và integration adapter nên có ranh giới riêng.
7. **Quy định lỗi.** Listener thất bại có ảnh hưởng use case chính không? Ai retry và ghi nhận trạng thái?
8. **Kiểm soát concurrency.** Event có được xử lý nhiều lần hoặc song song không?
9. **Ghi nhận observability.** Event ID, correlation ID, log phù hợp và metrics giúp điều tra.
10. **Kiểm thử đúng semantics.** Bao gồm commit/rollback, duplicate delivery và lỗi ở consumer nếu liên quan.

### Ví dụ lựa chọn cho đơn hàng

| Phản ứng sau khi đặt đơn | Mức quan trọng | Thiết kế gợi ý |
|---|---|---|
| Lưu đơn hàng | Cốt lõi | Thao tác repository trong transaction |
| Xác thực và giữ tồn kho bắt buộc | Cốt lõi | Service/orchestration có transaction strategy rõ |
| Audit trong cùng database và cùng transaction | Tùy invariant | Gọi trực tiếp hoặc listener đồng bộ có chủ đích |
| Cập nhật metrics best effort | Không chặn giao dịch | Listener độc lập; xử lý lỗi rõ ràng |
| Gửi email sau commit | Có thể trì hoãn | Transactional listener; outbox nếu cần bảo đảm |
| Đồng bộ dịch vụ giao vận | Thường cần retry | Outbox + broker/worker + idempotent consumer |
| Cập nhật dashboard tìm kiếm | Eventual consistency chấp nhận được | Listener/queue phù hợp với độ tin cậy yêu cầu |

## 22. Những nguyên tắc cần nhớ

- **`ApplicationEventPublisher.publishEvent` thông báo sự kiện trong Spring context.** Nó không phải message broker hoặc outbox.
- **Sự kiện nghiệp vụ nên mô tả điều đã xảy ra.** Tên ở quá khứ và payload chứa những dữ liệu có nghĩa với consumer.
- **`@EventListener` là cách phổ biến để nhận POJO/record event.** Listener cần là bean do Spring quản lý.
- **Listener mặc định thường đồng bộ.** Lỗi và độ trễ của listener có thể ảnh hưởng thread publisher.
- **`@TransactionalEventListener` giúp chọn phase của transaction.** `AFTER_COMMIT` là mặc định, nhưng không bảo đảm durable delivery.
- **Không có transaction thì listener transactional thường không chạy**, trừ khi bật fallback phù hợp.
- **`@Async` chuyển việc xử lý sang executor.** Nó không bảo đảm commit, retry hay persistence.
- **Outbox thích hợp khi cần không mất sự kiện sau commit.** Consumer cần idempotency vì có thể nhận trùng.
- **Không dùng event để che bước bắt buộc của use case.** Gọi service trực tiếp nếu kết quả bước đó quyết định thành công của thao tác.
- **Tránh phát JPA entity mutable vào listener async/sau commit.** Dùng ID và immutable snapshot.
- **Thứ tự listener không thay thế orchestration.** Với workflow có phụ thuộc, dùng bước có trạng thái rõ ràng.
- **Kiểm thử cả event delivery lẫn transaction semantics.** Test ghi nhận event chưa đủ để xác nhận listener sau commit.
- **Gắn observability với event quan trọng.** Event ID, correlation ID, metrics và log giúp xác định consumer nào thất bại.

## Kết luận

`ApplicationEventPublisher` cho phép một Spring Boot service phát sự kiện mà không cần biết tất cả thành phần sẽ phản ứng. `@EventListener` giúp đăng ký consumer theo kiểu event, còn `@TransactionalEventListener` cung cấp cơ chế ràng buộc phản ứng với phase của transaction. Với nhu cầu giảm độ trễ, `@Async` có thể đưa listener sang executor riêng.

Điểm cần cân nhắc khi thiết kế là **mức độ bắt buộc và độ tin cậy của phản ứng**. Application event thích hợp cho phối hợp nội bộ và mở rộng các phản ứng quanh sự việc nghiệp vụ. Nếu một bước là bắt buộc trước khi trả kết quả, hãy biểu diễn nó trong orchestration. Nếu một event phải được xử lý kể cả sau khi process crash, hãy dùng outbox, broker và cơ chế retry/idempotency. Khi hiểu đúng transaction, thread và delivery semantics, hệ thống sự kiện sẽ giúp code rõ ràng và dễ mở rộng mà không tạo ra những phụ thuộc ẩn khó vận hành.
