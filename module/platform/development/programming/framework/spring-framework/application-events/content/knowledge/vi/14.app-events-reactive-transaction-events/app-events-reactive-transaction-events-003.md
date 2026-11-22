# TransactionalEventPublisher trong Spring Reactive

TransactionalEventPublisher là delegate chuyên dùng để publish application event trong một reactive transaction. API này có từ Spring Framework 6.1, nằm trong package org.springframework.transaction.reactive.

Điểm đặc biệt của reactive transaction là trạng thái transaction được giữ trong Reactor Context, không dựa vào ThreadLocal như transaction imperative. Vì vậy, khi publish event trong một reactive pipeline, chỉ gọi ApplicationEventPublisher.publishEvent() thông thường có thể không mang theo thông tin transaction mà @TransactionalEventListener cần để đăng ký callback.

TransactionalEventPublisher giải quyết việc đó bằng cách đưa TransactionContext hiện tại làm source của event. Listener có thể dùng @TransactionalEventListener để gắn xử lý vào phase của reactive transaction, chẳng hạn chỉ chạy sau khi commit thành công.

## 1. Vì sao reactive transaction cần TransactionalEventPublisher?

Với transaction imperative dùng PlatformTransactionManager, Spring thường gắn transaction vào thread hiện tại. Listener đồng bộ chạy trong cùng thread có thể nhìn thấy transaction context đó.

Reactive transaction dùng ReactiveTransactionManager và Reactor Context. Pipeline có thể chuyển qua nhiều thread mà transaction vẫn được giữ theo subscriber context. Do đó, một listener không thể dựa vào ThreadLocal của thread hiện tại để tìm reactive transaction.

Từ Spring Framework 6.1, @TransactionalEventListener hỗ trợ cả:

- Transaction imperative do PlatformTransactionManager quản lý.
- Reactive transaction do ReactiveTransactionManager quản lý.

Đối với reactive transaction, TransactionContext phải được đưa vào event instance dưới dạng event source. TransactionalEventPublisher là delegate tiện lợi thực hiện việc này.

Luồng xử lý khái quát:

    Reactive service
          |
          v
    Reactive transaction
    (Reactor Context)
          |
          v
    TransactionalEventPublisher
          |
          | event source = TransactionContext
          v
    ApplicationEventPublisher
          |
          v
    @TransactionalEventListener
          |
          v
    Transaction phase callback
    (BEFORE_COMMIT / AFTER_COMMIT / ...)

TransactionalEventPublisher chỉ hỗ trợ bước publish event có mang transaction context. Nó không tạo transaction, không commit hoặc rollback transaction, và cũng không thay thế transaction manager.

## 2. Package, phiên bản và API

Import class từ package:

~~~java
import org.springframework.transaction.reactive.TransactionalEventPublisher;
~~~

Class được giới thiệu từ Spring Framework 6.1 và có constructor nhận một ApplicationEventPublisher:

~~~java
public TransactionalEventPublisher(
    ApplicationEventPublisher eventPublisher
)
~~~

Có hai overload chính:

| Phương thức | Tham số | Giá trị trả về | Mục đích |
|---|---|---|---|
| publishEvent(Object payload) | Payload nghiệp vụ | Mono<Void> | Tạo PayloadApplicationEvent với TransactionContext làm source |
| publishEvent(Function<TransactionContext, ApplicationEvent>) | Hàm tạo ApplicationEvent từ TransactionContext | Mono<Void> | Tạo custom ApplicationEvent có source là TransactionContext |

Cả hai đều trả về Reactor Mono<Void>. Việc lấy transaction context và publish event được thực hiện khi Mono được subscribe trong reactive context thích hợp.

### publishEvent(Object payload)

Overload này phù hợp khi chỉ cần gửi một payload Java bình thường:

~~~java
Mono<Void> publication =
    transactionalEventPublisher.publishEvent(
        new OrderConfirmedPayload(orderId)
    );
~~~

Delegate lấy TransactionContext hiện tại rồi tạo PayloadApplicationEvent với:

- Source: TransactionContext hiện tại.
- Payload: OrderConfirmedPayload.

Không cần tự viết một lớp kế thừa ApplicationEvent chỉ để gắn transaction context vào event.

**Giới hạn quan trọng:** nếu đối tượng truyền vào đã là một ApplicationEvent, overload này trả về Mono lỗi IllegalArgumentException. API không thể tự bọc một ApplicationEvent có sẵn mà vẫn giữ source transaction theo cách này.

### publishEvent(Function<TransactionContext, ApplicationEvent>)

Dùng overload này khi cần tạo custom event kế thừa ApplicationEvent:

~~~java
Mono<Void> publication =
    transactionalEventPublisher.publishEvent(
        transactionContext ->
            new OrderConfirmedEvent(transactionContext, orderId)
    );
~~~

Hàm nhận TransactionContext và dùng nó làm source của event. Đây là cách phù hợp nếu event có payload riêng, tên loại rõ ràng hoặc cần giữ một hợp đồng event cụ thể.

Nếu không tìm thấy TransactionContext trong Reactor subscriber context hoặc context holder, thao tác lấy context thất bại bằng NoTransactionException. Vì vậy, hãy gọi API này trong reactive transaction pipeline thực sự.

## 3. Đăng ký TransactionalEventPublisher thành Spring bean

Có thể tạo delegate bằng Java configuration:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.reactive.TransactionalEventPublisher;

@Configuration
class TransactionalEventConfiguration {

    @Bean
    TransactionalEventPublisher transactionalEventPublisher(
            ApplicationEventPublisher eventPublisher) {
        return new TransactionalEventPublisher(eventPublisher);
    }
}
~~~

ApplicationContext triển khai ApplicationEventPublisher nên có thể inject abstraction này trực tiếp. Các service nghiệp vụ chỉ cần inject TransactionalEventPublisher.

Không nên tạo một instance mới trong từng phương thức nghiệp vụ nếu ứng dụng đã có bean dùng chung. Delegate giữ reference tới ApplicationEventPublisher; transaction context vẫn được tra cứu tại thời điểm reactive Mono được thực thi.

## 4. Ví dụ: publish custom event trong reactive transaction

Giả sử ứng dụng có reactive repository cập nhật trạng thái đơn hàng. Sau khi cập nhật thành công, service publish OrderConfirmedEvent và listener chỉ xử lý sau commit.

Custom event:

~~~java
import java.util.UUID;
import org.springframework.context.ApplicationEvent;
import org.springframework.transaction.reactive.TransactionContext;

public final class OrderConfirmedEvent extends ApplicationEvent {

    private final UUID orderId;

    public OrderConfirmedEvent(
            TransactionContext transactionContext,
            UUID orderId) {
        super(transactionContext);
        this.orderId = orderId;
    }

    public UUID getOrderId() {
        return orderId;
    }
}
~~~

TransactionContext được dùng làm source. orderId là dữ liệu nghiệp vụ mà listener thực sự cần để xử lý.

Reactive service:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionalEventPublisher;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;
    private final TransactionalEventPublisher eventPublisher;

    public ReactiveOrderService(
            ReactiveOrderRepository orderRepository,
            TransactionalEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Mono<Void> confirm(UUID orderId) {
        return orderRepository.markConfirmed(orderId)
            .then(
                eventPublisher.publishEvent(
                    transactionContext ->
                        new OrderConfirmedEvent(
                            transactionContext,
                            orderId
                        )
                )
            );
    }
}
~~~

ReactiveOrderRepository là repository của ứng dụng; phương thức markConfirmed(UUID) trả về Mono<Void>. Ví dụ giả định service được quản lý bởi ReactiveTransactionManager và repository tham gia cùng reactive transaction.

Các bước xảy ra trong cùng reactive pipeline:

1. Transaction interceptor mở reactive transaction.
2. Repository cập nhật trạng thái đơn hàng.
3. Sau khi cập nhật hoàn tất, publishEvent(Function) lấy TransactionContext từ Reactor Context.
4. Function tạo OrderConfirmedEvent với TransactionContext làm source.
5. ApplicationEventPublisher nhận event.
6. @TransactionalEventListener đăng ký xử lý tại phase đã chọn.
7. Transaction manager hoàn tất commit hoặc rollback và kích hoạt callback tương ứng.

Điểm cần giữ là lời gọi publishEvent() phải được compose vào pipeline bằng then(), flatMap() hoặc operator tương đương. Không tách nó thành một subscription độc lập.

## 5. Nhận event bằng @TransactionalEventListener

Listener có thể khai báo phase mà nó muốn tham gia:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderConfirmationListener {

    private final OrderNotificationService notificationService;

    public OrderConfirmationListener(
            OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        notificationService.sendConfirmation(event.getOrderId());
    }
}
~~~

Vì event source là TransactionContext, Spring có thể liên kết listener với reactive transaction tương ứng. Với AFTER_COMMIT, listener chỉ được kích hoạt sau khi transaction commit thành công.

Các phase được hỗ trợ:

| Phase | Thời điểm xử lý |
|---|---|
| BEFORE_COMMIT | Trước khi transaction commit |
| AFTER_COMMIT | Sau khi commit thành công; mặc định |
| AFTER_ROLLBACK | Sau khi transaction rollback |
| AFTER_COMPLETION | Sau khi transaction hoàn tất, dù commit hay rollback |

Nếu transaction rollback, listener AFTER_COMMIT không chạy. Listener AFTER_ROLLBACK hoặc AFTER_COMPLETION có thể được kích hoạt theo phase đã khai báo.

Nếu event được publish mà không có transaction phù hợp, @TransactionalEventListener mặc định không được gọi. Thuộc tính fallbackExecution = true cho phép xử lý theo fallback khi không có transaction, nhưng nó không thay thế việc truyền TransactionContext cho reactive event.

## 6. Dùng payload thay cho custom ApplicationEvent

Nếu không cần custom event class, có thể dùng overload publishEvent(Object):

~~~java
public record OrderConfirmedPayload(UUID orderId) {}
~~~

Trong service:

~~~java
return orderRepository.markConfirmed(orderId)
    .then(
        eventPublisher.publishEvent(
            new OrderConfirmedPayload(orderId)
        )
    );
~~~

TransactionalEventPublisher tự tạo PayloadApplicationEvent với TransactionContext làm source và OrderConfirmedPayload làm payload.

Listener có thể khai báo kiểu PayloadApplicationEvent tương ứng nếu muốn truy cập cả wrapper và payload:

~~~java
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener
public void on(
        PayloadApplicationEvent<OrderConfirmedPayload> event) {
    UUID orderId = event.getPayload().orderId();
    // Xử lý đơn hàng đã xác nhận.
}
~~~

Cách này hữu ích khi cần phân biệt rõ event wrapper và payload. Nếu ứng dụng cần một event class riêng có tên nghiệp vụ và API getter cụ thể, dùng overload Function(TransactionContext, ApplicationEvent) sẽ dễ đọc hơn.

Không truyền một đối tượng ApplicationEvent vào overload payload. Nếu đã có custom ApplicationEvent, hãy tạo event qua function để TransactionContext được đặt đúng làm source.

## 7. TransactionalEventPublisher không commit transaction

Một nhầm lẫn thường gặp là nghĩ tên TransactionalEventPublisher có nghĩa class này tự quản lý commit. Thực tế:

- ReactiveTransactionManager quản lý transaction.
- TransactionalOperator hoặc @Transactional xác định ranh giới transaction.
- TransactionalEventPublisher lấy TransactionContext và publish event.
- @TransactionalEventListener đăng ký xử lý theo phase.

Mono<Void> trả về từ publishEvent() biểu diễn bước lấy context và hand-off event cho ApplicationEventPublisher. Nó không phải tín hiệu rằng transaction đã commit, và cũng không phải kết quả xác nhận mọi listener sau commit đã hoàn tất.

Vì vậy, không dùng:

~~~java
eventPublisher.publishEvent(payload).subscribe();
~~~

Cách gọi này tạo subscription tách khỏi pipeline hiện tại. Subscription đó có thể không có Reactor transaction context mà publisher cần, và service cũng không còn kiểm soát được thứ tự hoàn tất hoặc lỗi.

Cũng không gọi block() bên trong reactive pipeline để chờ event. Việc block có thể làm nghẽn event loop, phá vỡ mô hình reactive và làm mất transaction context mong đợi.

Hãy compose Mono được trả về:

~~~java
return repository.save(order)
    .then(eventPublisher.publishEvent(payload));
~~~

Nhờ vậy, thao tác publish được thực hiện trong cùng subscription và cùng Reactor Context với các bước nghiệp vụ.

## 8. Khác biệt giữa imperative và reactive event publication

Không phải mọi ứng dụng đều cần TransactionalEventPublisher.

| Nội dung | Imperative transaction | Reactive transaction |
|---|---|---|
| Transaction manager | PlatformTransactionManager | ReactiveTransactionManager |
| Nơi giữ transaction | Thread-bound state | Reactor Context |
| Publisher thông thường | ApplicationEventPublisher thường đủ | Không tự đưa TransactionContext vào event source |
| Cách gắn transaction vào event | Thread context có sẵn cho listener | Dùng TransactionalEventPublisher hoặc tự đưa TransactionContext làm source |
| Listener theo phase | @TransactionalEventListener | @TransactionalEventListener từ Spring 6.1, với event source mang TransactionContext |

Với JDBC/JPA và PlatformTransactionManager, thông thường chỉ cần ApplicationEventPublisher cùng @TransactionalEventListener. TransactionSynchronizationManager imperative có thể đọc transaction gắn với thread.

Với R2DBC hoặc reactive transaction khác, không dùng static TransactionSynchronizationManager của package org.springframework.transaction.support để tìm transaction hiện tại. Hãy dùng API reactive và giữ toàn bộ thao tác tham gia transaction trong cùng Reactor pipeline.

## 9. Phân biệt TransactionalEventPublisher với TransactionalEventListener

Hai tên API gần nhau nhưng đảm nhiệm hai phía khác nhau:

- **TransactionalEventPublisher:** phía phát event; đưa TransactionContext vào event source trong reactive transaction.
- **@TransactionalEventListener:** phía nhận event; chọn phase transaction để xử lý.

Một luồng đầy đủ thường có cả hai:

    Reactive service
        |
        | TransactionalEventPublisher
        v
    Event có TransactionContext source
        |
        v
    ApplicationEventPublisher
        |
        v
    @TransactionalEventListener
        |
        | chờ transaction phase
        v
    AFTER_COMMIT / AFTER_ROLLBACK / ...

Không thay TransactionalEventPublisher bằng @TransactionalEventListener ở phía publisher. Annotation là dành cho phương thức listener, không phải API phát event.

Cũng không nhầm TransactionalEventPublisher với TransactionalOperator. TransactionalOperator tạo ranh giới reactive transaction; TransactionalEventPublisher chỉ publish event gắn với transaction context đang có.

## 10. Xử lý rollback và lỗi

Giả sử service cập nhật đơn hàng rồi publish OrderConfirmedEvent, nhưng một bước tiếp theo trong pipeline thất bại và transaction rollback.

Kết quả mong muốn:

- Dữ liệu database trong transaction được rollback.
- Listener AFTER_COMMIT không chạy.
- Listener AFTER_ROLLBACK có thể chạy nếu được đăng ký.
- Listener AFTER_COMPLETION nhận trạng thái hoàn tất tương ứng.

Ví dụ kiểm tra lỗi sau bước publish:

~~~java
return orderRepository.markConfirmed(orderId)
    .then(eventPublisher.publishEvent(
        tx -> new OrderConfirmedEvent(tx, orderId)
    ))
    .then(Mono.error(
        new IllegalStateException("Force rollback")
    ));
~~~

Đoạn này chỉ là tình huống kiểm thử; không đưa lỗi cố ý vào luồng nghiệp vụ thật. Khi lỗi thoát khỏi reactive transaction pipeline, transaction manager có thể rollback theo quy tắc của nó.

Một lỗi trong listener AFTER_COMMIT xảy ra sau khi transaction đã commit. Không thể rollback dữ liệu đã commit chỉ vì notification hoặc callback thất bại. Nếu cần retry, hãy xây dựng cơ chế phục hồi riêng.

TransactionalEventPublisher cũng không biến event trong bộ nhớ thành message bền vững. Nếu process dừng sau commit nhưng trước khi listener hoàn thành, không có bảo đảm tự động rằng event sẽ được phát lại.

## 11. Khi nào cần transactional outbox?

TransactionalEventPublisher kết hợp @TransactionalEventListener giải quyết việc gắn listener với transaction hiện tại trong một ứng dụng. Nó không bảo đảm giao nhận bền vững qua process restart.

Nếu event phải được gửi tới hệ thống khác và không được phép mất, cân nhắc transactional outbox:

1. Trong cùng reactive transaction, cập nhật dữ liệu nghiệp vụ.
2. Ghi một bản ghi outbox vào database trong cùng transaction.
3. Commit cả dữ liệu nghiệp vụ và bản ghi outbox.
4. Worker đọc các bản ghi outbox chưa gửi.
5. Worker gửi message tới broker hoặc dịch vụ đích.
6. Ghi nhận trạng thái gửi, retry khi lỗi và xử lý duplicate ở consumer.

Outbox lưu ý định phát event trong cùng transaction với thay đổi nghiệp vụ. TransactionalEventPublisher vẫn có thể được dùng để thông báo nội bộ rằng transaction vừa tạo ra một event hoặc để đánh thức một thành phần xử lý; nhưng outbox mới là nơi lưu bền để phục hồi sau sự cố.

Không triển khai outbox cho mọi event nội bộ. Dùng khi yêu cầu giao nhận, retry và phục hồi vượt quá khả năng của event dispatcher trong bộ nhớ.

## 12. Kiểm thử reactive transactional event

Kiểm thử cần dùng ReactiveTransactionManager thật hoặc transaction manager tích hợp với database test. StepVerifier giúp xác nhận reactive pipeline hoàn tất hoặc phát lỗi; TransactionalOperator có thể tạo transaction ranh giới trong test.

Các tình huống nên có:

1. **Commit thành công:** publish event trong transaction; xác nhận listener AFTER_COMMIT được gọi.
2. **Rollback:** publish event rồi làm pipeline thất bại; xác nhận listener AFTER_COMMIT không chạy và listener AFTER_ROLLBACK chạy nếu có.
3. **Không có transaction context:** gọi TransactionalEventPublisher ngoài reactive transaction; xác nhận Mono lỗi NoTransactionException.
4. **Event source:** xác nhận event custom có TransactionContext làm source hoặc payload event được bọc đúng.
5. **Subscription:** xác nhận event chỉ được publish khi Mono được subscribe trong pipeline phù hợp.
6. **Duplicate:** nếu publisher có thể phát cùng nghiệp vụ nhiều lần, xác nhận listener hoặc consumer xử lý idempotent.

Ví dụ khung kiểm thử publication trong transaction:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.reactive.TransactionalEventPublisher;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TransactionalEventPublisherTest {

    private final TransactionalOperator transactionOperator;
    private final TransactionalEventPublisher eventPublisher;

    TransactionalEventPublisherTest(
            TransactionalOperator transactionOperator,
            TransactionalEventPublisher eventPublisher) {
        this.transactionOperator = transactionOperator;
        this.eventPublisher = eventPublisher;
    }

    @Test
    void publishesWithinReactiveTransaction() {
        Mono<Void> work = Mono.defer(() ->
            eventPublisher.publishEvent(
                tx -> new OrderConfirmedEvent(tx, UUID.randomUUID())
            )
        );

        StepVerifier.create(
            transactionOperator.transactional(work)
        ).verifyComplete();
    }
}
~~~

Đây là test integration skeleton. Dự án cần cấu hình ReactiveTransactionManager, TransactionalOperator, Spring context và dependency reactor-test. Nếu muốn kiểm tra callback AFTER_COMMIT thực sự, thêm listener test ghi nhận event vào probe thread-safe rồi assert sau khi StepVerifier xác nhận transaction hoàn tất.

Không dùng transaction manager giả nếu mục tiêu là xác nhận commit/rollback thực tế. Với database reactive, hãy chạy test trên loại database và driver tương thích với cấu hình production.

## 13. Những lỗi thường gặp

**Dùng ApplicationEventPublisher trực tiếp trong reactive transaction rồi mong listener tìm thấy transaction.** Reactor Context không phải ThreadLocal. Với @TransactionalEventListener, hãy đưa TransactionContext vào event source bằng TransactionalEventPublisher.

**Nhầm package.** TransactionalEventPublisher nằm trong org.springframework.transaction.reactive; @TransactionalEventListener nằm trong org.springframework.transaction.event.

**Gọi publishEvent() ngoài reactive transaction.** TransactionContextManager không tìm được context và publisher trả về Mono lỗi NoTransactionException.

**Gọi subscribe() bên trong service.** Subscription độc lập có thể mất Reactor Context và tách lỗi khỏi luồng gọi. Hãy compose Mono được trả về.

**Dùng block() trong reactive pipeline.** Block làm nghẽn thread và phá vỡ mô hình reactive. Dùng then(), flatMap() hoặc operator phù hợp.

**Truyền ApplicationEvent vào overload Object.** Overload này dành cho payload; ApplicationEvent được truyền vào sẽ tạo lỗi. Dùng Function<TransactionContext, ApplicationEvent> cho custom event.

**Cho rằng publisher tự commit transaction.** Transaction manager mới quản lý commit/rollback. Publisher chỉ thực hiện hand-off event có transaction context.

**Cho rằng Mono<Void> nghĩa là listener AFTER_COMMIT đã chạy xong.** Mono chỉ biểu diễn bước publication. Listener transaction-bound chạy ở phase khi transaction hoàn tất.

**Cho rằng event được lưu bền.** Event dispatcher nội bộ không thay thế outbox hoặc message broker.

**Dùng API imperative để đọc reactive transaction.** Dùng reactive transaction APIs và giữ các thao tác trong cùng Reactor Context.

## 14. Quy tắc ghi nhớ

- TransactionalEventPublisher có từ Spring Framework 6.1.
- Package là org.springframework.transaction.reactive.
- Hai overload: publishEvent(Object) và publishEvent(Function<TransactionContext, ApplicationEvent>).
- Cả hai trả về Mono<Void>.
- TransactionContext hiện tại được dùng làm source của ApplicationEvent.
- publishEvent(Object) dành cho payload và không nhận ApplicationEvent đã tạo sẵn.
- Custom ApplicationEvent phải được tạo bằng overload Function.
- Phải gọi trong reactive transaction context; thiếu context dẫn tới NoTransactionException.
- Compose Mono vào pipeline; không tự subscribe hoặc block.
- @TransactionalEventListener chọn phase xử lý; publisher không tự commit.
- Imperative transaction thường không cần TransactionalEventPublisher.
- Event nội bộ không có bảo đảm lưu bền; dùng outbox nếu không được phép mất.

**Ghi nhớ:** TransactionalEventPublisher nối event publication với Reactor transaction context. Dùng nó để event mang đúng source cho @TransactionalEventListener, giữ Mono trong cùng reactive pipeline và để ReactiveTransactionManager quyết định commit hoặc rollback. Khi cần giao nhận bền vững, bổ sung outbox hoặc message broker.

## Tài liệu tham khảo

- [TransactionalEventPublisher — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [TransactionContextManager — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContextManager.html)
- [TransactionContext — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionContext.html)
- [TransactionalEventListener — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Transaction-bound Events — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Reactive Transaction Management — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [ApplicationEventPublisher — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)