# Domain event sau mutation trong Spring for GraphQL

Một GraphQL mutation thường thay đổi trạng thái nghiệp vụ, chẳng hạn tạo đơn hàng, xác nhận thanh toán hoặc cập nhật hồ sơ. Sau khi thay đổi được lưu thành công, ứng dụng có thể cần thông báo cho các thành phần khác: gửi email, cập nhật read model, phát message lên broker hoặc báo cho client đang theo dõi subscription.

Domain event giúp mô tả một sự kiện nghiệp vụ đã xảy ra. Khi mutation chạy trong transaction, event cần được xử lý theo đúng kết quả commit hoặc rollback. Spring cung cấp **ApplicationEventPublisher** để phát event trong ứng dụng và **@TransactionalEventListener** để ràng buộc listener với một phase của transaction. Với yêu cầu phát message ra hệ thống ngoài mà không được mất event khi process dừng, nên cân nhắc **Transactional Outbox**.

## 1. Domain event là gì?

Domain event là một sự kiện mô tả một sự thật nghiệp vụ đã xảy ra, thường đặt tên ở thì quá khứ:

- OrderPlaced: đơn hàng đã được tạo.
- PaymentCaptured: khoản thanh toán đã được ghi nhận.
- AccountEmailChanged: email tài khoản đã thay đổi.
- BookPublished: sách đã được xuất bản.

Event mô tả điều đã xảy ra, không phải lệnh yêu cầu một thành phần khác làm việc gì. Ví dụ, OrderPlaced mô tả đơn hàng đã được tạo; SendOrderEmail là một command hoặc hành động của listener.

Một domain event tốt thường:

- Bất biến sau khi được tạo.
- Chứa ID và dữ liệu tối thiểu cần cho consumer xử lý.
- Có event ID duy nhất để truy vết và chống xử lý trùng.
- Có thời điểm xảy ra và, khi cần, aggregate ID/version.
- Không phụ thuộc vào GraphQL request object hoặc HTTP context.
- Không mang theo entity JPA đang được quản lý hay object có lazy relationship.

Ví dụ:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        Long orderId,
        String customerId,
        Instant occurredAt) {
}
~~~

Event là một fact. Consumer có thể dùng nó để gửi thông báo, cập nhật projection hoặc phát integration event.

## 2. Domain event, Spring application event và integration event

Ba khái niệm thường được dùng cùng nhau nhưng có phạm vi khác nhau:

| Khái niệm | Phạm vi | Ví dụ |
| --- | --- | --- |
| Domain event | Mô hình nghiệp vụ trong bounded context | OrderPlaced, PaymentCaptured |
| Spring application event | Cơ chế dispatch event trong cùng Spring ApplicationContext | ApplicationEventPublisher.publishEvent(orderPlaced) |
| Integration event | Hợp đồng message được chia sẻ giữa các service | commerce.order-placed.v1 |

Một domain event có thể được phát bằng Spring application event. Listener trong cùng ứng dụng nhận event đó và thực hiện công việc nội bộ.

Khi cần gửi thông tin sang service khác, nên ánh xạ domain event thành integration event có schema/version ổn định. Không nên mặc định gửi thẳng class domain nội bộ lên Kafka/RabbitMQ vì class đó có thể chứa kiểu dữ liệu, entity hoặc chi tiết triển khai không phù hợp làm hợp đồng liên service.

## 3. Mutation là điểm vào của transaction nghiệp vụ

Spring for GraphQL ánh xạ mutation root field bằng @MutationMapping. Controller nên nhận input, gọi application service và trả kết quả GraphQL:

~~~graphql
type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}

input PlaceOrderInput {
    customerId: ID!
    productId: ID!
    quantity: Int!
}

type Order {
    id: ID!
    status: String!
}
~~~

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMutationController {

    private final PlaceOrderService placeOrderService;

    public OrderMutationController(PlaceOrderService placeOrderService) {
        this.placeOrderService = placeOrderService;
    }

    @MutationMapping
    public Order placeOrder(@Argument("input") PlaceOrderInput input) {
        return placeOrderService.place(input);
    }
}
~~~

Transaction thường được đặt ở application service để bao trọn use case:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public PlaceOrderService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Order place(PlaceOrderInput input) {
        Order order = Order.place(
                input.customerId(),
                input.productId(),
                input.quantity());

        Order saved = orderRepository.save(order);

        eventPublisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                saved.getCustomerId(),
                Instant.now()));

        return saved;
    }
}
~~~

Ví dụ giả định Order là aggregate root có các accessor tương ứng, repository tham gia cùng transaction manager và input đã được validate trước khi vào service.

Khi method @Transactional kết thúc bình thường, transaction interceptor commit transaction trước khi trả quyền điều khiển về caller. Nếu method ném runtime exception và transaction được đánh dấu rollback, dữ liệu thay đổi sẽ bị rollback theo cấu hình transaction.

## 4. Transaction boundary trong GraphQL

GraphQL không định nghĩa sẵn transaction semantics. Ứng dụng quyết định mỗi mutation chạy trong transaction riêng hay một nhóm mutation dùng chung transaction.

Spring for GraphQL khuyến nghị transaction per controller method là một cách đơn giản, rõ ràng. Có thể đặt @Transactional ở method @MutationMapping hoặc ở service được method đó gọi. Service layer thường phù hợp hơn vì cùng use case có thể được gọi từ REST, scheduler hoặc message consumer.

Cần nhớ:

- Transaction của method mutation kết thúc khi method đó trả về qua Spring transaction proxy.
- Việc resolve các nested fields trong GraphQL response diễn ra sau đó và không tự động nằm trong transaction của mutation method.
- Một GraphQL request có thể chứa nhiều top-level mutation fields; không mặc định rằng tất cả chúng nằm trong một transaction duy nhất.
- Nếu nhiều bước phải atomic cùng nhau, tạo một mutation/application service thực hiện toàn bộ use case trong một transaction rõ ràng.

Với service dùng transaction proxy, callback AFTER_COMMIT chạy trong quá trình transaction hoàn tất trước khi lời gọi service trả về controller. Nếu listener chạy đồng bộ, thời gian listener có thể làm tăng latency của mutation. Nếu listener ném exception, GraphQL response có thể báo lỗi dù dữ liệu đã commit; client cần idempotency để tránh tạo lại thao tác khi retry. Dùng @Async hoặc outbox khi cần tách thời gian xử lý, nhưng hãy chọn cơ chế dựa trên yêu cầu độ tin cậy.

Không nên mở một transaction đồng bộ kéo dài trên toàn bộ GraphQL request chỉ để giữ mọi field resolver trong cùng transaction. Field resolution có thể phân tán và chạy bất đồng bộ, khiến transaction dài, giữ connection và lock lâu hơn cần thiết.

## 5. Vì sao publish event ngay trong mutation chưa đủ?

Nếu gọi broker trực tiếp trước khi database commit, hai hệ thống có thể không nhất quán:

~~~java
@Transactional
public Order place(PlaceOrderInput input) {
    Order saved = orderRepository.save(Order.place(input));

    // Rủi ro: broker nhận event nhưng transaction database sau đó rollback.
    messageBroker.publish(new OrderPlacedMessage(saved.getId()));

    return saved;
}
~~~

Nếu message được gửi thành công nhưng database rollback, consumer có thể xử lý một đơn hàng chưa từng được commit.

Nếu đợi commit xong mới gửi broker, vẫn còn một khoảng trống:

1. Database commit thành công.
2. Process dừng trước khi gửi message.
3. Dữ liệu đã tồn tại nhưng hệ thống downstream không nhận được event.

Đây là dual-write problem: một use case phải ghi vào database và gửi message sang hệ thống khác, nhưng hai thao tác không nằm trong cùng một transaction nguyên tử.

Với event nội bộ trong cùng process, @TransactionalEventListener giúp chờ transaction hoàn tất. Với message liên service cần độ tin cậy cao, transactional outbox giải quyết khoảng trống giữa database commit và publish.

## 6. Phát Spring application event bằng ApplicationEventPublisher

ApplicationEventPublisher là API của Spring để chuyển event tới các listener phù hợp:

~~~java
@Service
public class PlaceOrderService {

    private final ApplicationEventPublisher eventPublisher;

    public PlaceOrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Order place(PlaceOrderInput input) {
        Order order = saveOrder(input);

        eventPublisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now()));

        return order;
    }
}
~~~

Lệnh publishEvent chuyển event tới Spring event multicaster. Bản thân lời gọi này không phải thao tác commit và cũng không bảo đảm event được lưu bền vững. Cách listener được thực thi phụ thuộc cấu hình multicaster; cấu hình mặc định thường gọi listener đồng bộ, nhưng ứng dụng có thể cấu hình executor hoặc dùng @Async.

Không nên xem ApplicationEventPublisher như message broker. Event chỉ tồn tại trong cơ chế dispatch của ứng dụng hiện tại, không tự được lưu vào database, không tự retry sau khi process restart và không tự truyền sang instance khác.

## 7. Dùng @TransactionalEventListener với AFTER_COMMIT

Nếu listener chỉ được chạy khi mutation commit thành công, dùng @TransactionalEventListener:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPlacedListener {

    private final OrderNotificationService notificationService;

    public OrderPlacedListener(OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        notificationService.sendOrderConfirmation(
                event.orderId(),
                event.customerId());
    }
}
~~~

AFTER_COMMIT là phase mặc định, nên có thể viết ngắn:

~~~java
@TransactionalEventListener
public void on(OrderPlaced event) {
    notificationService.sendOrderConfirmation(event);
}
~~~

Khi event được publish trong một transaction đang hoạt động:

1. Spring đăng ký listener với transaction hiện tại.
2. Listener chưa chạy ngay tại thời điểm publishEvent.
3. Nếu transaction commit thành công, listener được gọi ở AFTER_COMMIT.
4. Nếu transaction rollback, listener AFTER_COMMIT không được gọi.

Đây là cách phù hợp cho side effect chỉ được phép xảy ra sau khi dữ liệu nghiệp vụ đã commit, ví dụ gửi email xác nhận hoặc làm mới cache nội bộ.

## 8. Các phase của TransactionalEventListener

Annotation @TransactionalEventListener hỗ trợ bốn phase:

| Phase | Thời điểm | Trường hợp sử dụng |
| --- | --- | --- |
| BEFORE_COMMIT | Ngay trước khi transaction commit | Kiểm tra hoặc bổ sung công việc cần hoàn tất trước commit. |
| AFTER_COMMIT | Sau khi commit thành công | Gửi thông báo, cập nhật cache hoặc phát tín hiệu sau khi dữ liệu đã được lưu. |
| AFTER_ROLLBACK | Sau khi transaction rollback | Ghi nhận rollback, giải phóng tài nguyên ngoài transaction hoặc phát tín hiệu thất bại. |
| AFTER_COMPLETION | Sau khi transaction hoàn tất, dù commit hay rollback | Cleanup hoặc audit cần chạy ở cả hai kết quả. |

Ví dụ listener chỉ ghi nhận rollback:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlacementAttempted(
        UUID attemptId,
        Long orderId,
        Instant attemptedAt) {
}

@Component
public class OrderRollbackListener {

    private final AuditService auditService;

    public OrderRollbackListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void on(OrderPlacementAttempted event) {
        auditService.recordOrderPlacementRolledBack(event.orderId());
    }
}
~~~

Ở ví dụ này, OrderPlacementAttempted biểu diễn lần thử tạo đơn hàng và được publish trong transaction. Listener AFTER_ROLLBACK nhận event đó nếu transaction rollback. Không nên dùng tên OrderPlaced cho một lần thử đã rollback vì đơn hàng chưa thực sự được tạo thành công.

BEFORE_COMMIT không phù hợp để gửi email hoặc publish message không thể thu hồi. Nếu side effect bên ngoài đã xảy ra rồi transaction rollback, hệ thống lại rơi vào trạng thái không nhất quán.

## 9. Điều gì xảy ra nếu không có transaction?

Mặc định, @TransactionalEventListener không chạy nếu event được publish khi không có transaction đang hoạt động. Spring không thể bảo đảm phase AFTER_COMMIT nếu không có transaction để theo dõi.

Có thể bật fallbackExecution:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void on(OrderPlaced event) {
    // Chạy theo fallback khi event được publish ngoài transaction.
}
~~~

Khi bật fallbackExecution, listener được gọi ngay theo fallback nếu không có transaction. Nhưng listener không còn được bảo đảm chạy sau commit của một transaction.

Chỉ bật fallbackExecution khi nghiệp vụ chấp nhận event được xử lý cả trong lẫn ngoài transaction. Nếu event biểu diễn một thay đổi dữ liệu bắt buộc phải commit trước khi consumer chạy, hãy giữ mặc định false và bảo đảm event luôn được publish bên trong transaction phù hợp.

## 10. Listener AFTER_COMMIT không thể rollback dữ liệu đã commit

Sau khi AFTER_COMMIT chạy, transaction gốc đã commit. Nếu listener ném exception, transaction đã commit không thể quay lại trạng thái trước đó.

Điều này tạo ra một tình huống cần xử lý cẩn thận:

- Đơn hàng đã được lưu.
- Listener gửi email hoặc gọi service ngoài thất bại.
- GraphQL mutation có thể đã commit dữ liệu, dù listener đồng bộ ném lỗi làm response của request bị ảnh hưởng.
- Client có thể retry mutation và tạo thao tác trùng nếu API không có idempotency.

Vì vậy, listener nên phân loại và xử lý lỗi rõ ràng. Với side effect best-effort, có thể log/metrics và retry theo chính sách riêng. Với side effect quan trọng không được mất, dùng outbox thay vì phụ thuộc duy nhất vào callback trong process.

Một điểm khác: sau AFTER_COMMIT, tài nguyên transaction có thể vẫn còn được bind trong quá trình cleanup. Nếu listener cần ghi thêm dữ liệu database, thao tác đó không tự được commit trong transaction đã hoàn tất.

## 11. Ghi database từ listener sau commit

Nếu listener cần thực hiện một lần ghi database mới, hãy gọi một service mở transaction độc lập:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final OrderProjectionRepository repository;

    public OrderProjectionService(OrderProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateProjection(OrderPlaced event) {
        repository.save(OrderProjection.from(event));
    }
}
~~~

Listener:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionService projectionService;

    public OrderProjectionListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        projectionService.updateProjection(event);
    }
}
~~~

REQUIRES_NEW yêu cầu Spring mở transaction mới cho thao tác ghi projection. Đặt method transactional ở một bean khác giúp lời gọi đi qua Spring proxy. Không gọi một method REQUIRES_NEW bằng self-invocation trong cùng object rồi kỳ vọng proxy áp dụng propagation.

Nếu projection update là việc bắt buộc phải hoàn thành cuối cùng, vẫn cần retry hoặc outbox để không mất công việc khi listener thất bại.

## 12. Xử lý listener bất đồng bộ bằng @Async

Một listener có thể thực hiện công việc lâu như gửi email, gọi HTTP hoặc tạo báo cáo. Có thể kết hợp @Async với @TransactionalEventListener:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AsyncOrderNotificationListener {

    private final OrderNotificationService notificationService;

    public AsyncOrderNotificationListener(
            OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        notificationService.sendOrderConfirmation(event);
    }
}
~~~

Bật async execution:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Khi kết hợp hai annotation:

- Event chỉ đủ điều kiện được dispatch sau khi transaction commit.
- Listener được thực thi trên executor theo cấu hình async.
- Công việc không giữ thread xử lý mutation trong suốt thời gian gửi email.
- Exception trong async listener không thể rollback transaction đã commit.
- Cần cấu hình executor, queue capacity, shutdown behavior và error handling.

Với method @Async trả void, exception không được trả về caller; hãy cấu hình AsyncUncaughtExceptionHandler hoặc cơ chế quan sát tương ứng để không mất lỗi trong executor.

Không mặc định dùng executor không giới hạn. Khi tải tăng, queue không giới hạn có thể làm bộ nhớ tăng liên tục. Dùng thread pool và queue có giới hạn, metrics cho queue/rejection và chính sách retry phù hợp.

## 13. Event payload nên chứa gì?

Listener thường chạy sau khi transaction gốc đã kết thúc, và nếu async thì có thể chạy ở thread khác. Vì vậy event nên chứa dữ liệu đủ để consumer làm việc mà không phụ thuộc persistence context của request.

Nên dùng:

~~~java
public record OrderPlaced(
        UUID eventId,
        Long orderId,
        String customerId,
        String orderNumber,
        Instant occurredAt) {
}
~~~

Hạn chế truyền entity JPA:

~~~java
// Không nên truyền entity đang được quản lý sang listener async.
public record OrderPlaced(OrderEntity order) {
}
~~~

Lý do:

- Entity có thể detached khi listener chạy.
- Lazy relationship có thể không còn truy cập được.
- Consumer có thể vô tình kích hoạt query database ngoài transaction ban đầu.
- Entity mutable có thể bị thay đổi sau khi event được tạo.
- Serialization entity dễ kéo theo graph dữ liệu lớn hoặc vòng tham chiếu.

Nếu listener cần thêm dữ liệu, truyền ID rồi đọc lại qua service có transaction riêng. Với event tích hợp, hãy tạo DTO/contract riêng và chỉ công bố các trường được phép.

## 14. Domain event sau mutation không phải GraphQL Subscription

Spring application event và GraphQL Subscription là hai cơ chế khác nhau:

| Cơ chế | Vai trò |
| --- | --- |
| Domain event | Ghi nhận một sự thật nghiệp vụ đã xảy ra trong ứng dụng. |
| @TransactionalEventListener | Chạy listener theo kết quả transaction. |
| Message broker | Phân phối event giữa process hoặc service. |
| GraphQL Subscription | Giữ luồng response cho client theo thời gian. |

Một listener có thể chuyển domain event thành tín hiệu cho Subscription publisher, nhưng việc đó cần một publisher/transport riêng. ApplicationEventPublisher không tự biến event thành GraphQL response.

Nếu dùng Reactor Sinks để bridge event vào subscription, cần lưu ý sink trong bộ nhớ thường chỉ hoạt động trong một instance, không replay bền vững và có thể mất event khi process restart. Với nhiều instance hoặc yêu cầu replay, hãy dùng broker/pub-sub hoặc event store phù hợp và lọc dữ liệu theo quyền của từng subscriber.

## 15. Giới hạn của AFTER_COMMIT khi gửi message ra ngoài

Giả sử listener AFTER_COMMIT gửi event lên Kafka:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publish(OrderPlaced event) {
    kafkaTemplate.send("orders", event.orderId().toString(), event);
}
~~~

Cách này bảo đảm không gửi khi transaction rollback. Tuy nhiên, nó chưa bảo đảm event không bị mất:

1. Database commit thành công.
2. Process crash trước khi listener gửi Kafka.
3. Không còn transaction nào ghi lại việc cần publish.
4. Downstream không bao giờ nhận event đó.

Nếu listener gửi Kafka rồi process crash trước khi ghi nhận thành công ở một hệ thống khác, retry còn có thể tạo duplicate. Callback AFTER_COMMIT không phải durable queue.

Dùng cách này cho thông báo best-effort có thể chấp nhận được. Với integration event quan trọng, nên lưu event trong cùng database transaction với aggregate.

## 16. Transactional Outbox giải quyết dual-write

Transactional Outbox lưu event vào một bảng outbox trong cùng transaction với thay đổi nghiệp vụ:

~~~mermaid
flowchart TD
    A[GraphQL mutation] --> B[Application service]
    B --> C[Begin database transaction]
    C --> D[Save aggregate]
    D --> E[Insert outbox event row]
    E --> F{Commit transaction}
    F -->|Rollback| G[Aggregate và outbox cùng rollback]
    F -->|Commit| H[Outbox row sẵn sàng]
    H --> I[Outbox publisher / CDC]
    I --> J[Message broker]
    J --> K[Consumer]
    K --> L[Idempotent processing]
~~~

Nếu aggregate được lưu thành công thì outbox row cũng được commit. Nếu transaction rollback thì cả hai cùng rollback. Worker hoặc CDC connector đọc outbox sau commit và gửi event ra broker.

Ví dụ bảng outbox:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    aggregate_version BIGINT,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE,
    attempts INTEGER NOT NULL DEFAULT 0
);
~~~

Kiểu JSONB và UUID phụ thuộc database; điều chỉnh kiểu cột cho hệ quản trị đang dùng.

## 17. Ghi aggregate và outbox trong cùng transaction

Service có thể tạo integration event và lưu outbox row cùng với aggregate:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public PlaceOrderService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order place(PlaceOrderInput input) {
        Order order = orderRepository.save(Order.place(input));

        OrderPlacedIntegrationEvent event = new OrderPlacedIntegrationEvent(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now());

        outboxRepository.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId().toString(),
                "OrderPlaced",
                serialize(event),
                event.occurredAt()));

        return order;
    }

    private String serialize(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException exception) {
            throw new IllegalStateException("Cannot serialize outbox event", exception);
        }
    }
}
~~~

Ví dụ giả định repository và entity có các method tương ứng. Nếu serialization thất bại, runtime exception làm transaction rollback, nên không có order được commit mà thiếu outbox row.

Đoạn code dùng namespace Jackson 2 (com.fasterxml.jackson). Nếu ứng dụng dùng Jackson 3, hãy dùng ObjectMapper/serializer tương ứng với dependency đang cấu hình; nguyên tắc transaction không thay đổi.

Có thể dùng domain event nội bộ rồi map sang integration event trước khi ghi outbox. Nên lưu event type và schema version rõ ràng để consumer có thể xử lý khi payload thay đổi theo thời gian.

## 18. Outbox publisher và delivery semantics

Một background worker định kỳ hoặc CDC connector đọc các outbox row chưa publish:

~~~java
import java.util.List;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class OutboxSchedulingConfiguration {
}

@Component
class OutboxPublisher {

    private final OutboxService outboxService;
    private final MessagePublisher messagePublisher;

    OutboxPublisher(OutboxService outboxService, MessagePublisher messagePublisher) {
        this.outboxService = outboxService;
        this.messagePublisher = messagePublisher;
    }

    @Scheduled(fixedDelay = 1000)
    public void publishPendingEvents() {
        List<OutboxEvent> batch = outboxService.claimPendingBatch(100);

        for (OutboxEvent event : batch) {
            try {
                messagePublisher.publish(event);
                outboxService.markPublished(event.eventId());
            }
            catch (Exception exception) {
                outboxService.recordFailure(
                        event.eventId(),
                        exception.getClass().getSimpleName());
            }
        }
    }
}
~~~

Đây là khung minh họa. Trong môi trường nhiều worker, claimPendingBatch phải có cơ chế khóa/claim an toàn để hai worker không xử lý cùng một row đồng thời. Việc publish và markPublished cũng cần được thiết kế cho tình huống process dừng giữa hai thao tác.

Nếu broker nhận event nhưng process crash trước khi đánh dấu row đã publish, worker có thể gửi lại event. Vì vậy transactional outbox thường cung cấp at-least-once delivery, không tự bảo đảm exactly-once end-to-end.

Các consumer cần idempotent:

- Dùng eventId duy nhất.
- Lưu eventId đã xử lý trong inbox/processed-event table.
- Đặt unique constraint để ngăn xử lý cùng event nhiều lần.
- Gộp việc ghi trạng thái consumer và đánh dấu event đã xử lý trong cùng transaction.
- Chỉ thực hiện side effect khi event chưa được xử lý.

Nếu thứ tự event quan trọng, lưu aggregateVersion hoặc sequence number và publish theo thứ tự của từng aggregate. Không chỉ dựa vào timestamp vì nhiều event có thể có cùng thời điểm hoặc worker có thể publish lệch thứ tự.

## 19. Reactive transaction và transactional event

Với transaction đồng bộ dùng PlatformTransactionManager, Spring theo dõi transaction bằng thread-bound context. Với reactive transaction, trạng thái transaction nằm trong Reactor Context, không phải ThreadLocal.

Từ Spring Framework 6.1, @TransactionalEventListener hỗ trợ cả reactive transaction. Tuy nhiên, transaction context phải được đưa vào event source. Spring cung cấp TransactionalEventPublisher để thực hiện việc đó.

Ví dụ cấu hình publisher:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.reactive.TransactionalEventPublisher;

@Configuration
public class ReactiveEventConfiguration {

    @Bean
    TransactionalEventPublisher transactionalEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        return new TransactionalEventPublisher(applicationEventPublisher);
    }
}
~~~

Reactive service:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactivePlaceOrderService {

    private final ReactiveOrderRepository orderRepository;
    private final TransactionalEventPublisher eventPublisher;

    public ReactivePlaceOrderService(
            ReactiveOrderRepository orderRepository,
            TransactionalEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Mono<Order> place(PlaceOrderInput input) {
        return orderRepository.save(Order.place(input))
                .flatMap(order -> eventPublisher.publishEvent(
                                new OrderPlaced(
                                        UUID.randomUUID(),
                                        order.getId(),
                                        order.getCustomerId(),
                                        Instant.now()))
                        .thenReturn(order));
    }
}
~~~

Đảm bảo method reactive thực sự chạy trong transaction được quản lý bởi ReactiveTransactionManager. Phải compose Mono do publishEvent trả về vào pipeline; không gọi subscribe() thủ công hoặc bỏ qua publisher Mono. Nếu dùng ApplicationEventPublisher trực tiếp trong reactive pipeline, Reactor transaction context không tự được truyền như thread-bound transaction.

## 20. Kiểm thử domain event theo transaction

Kiểm thử nên xác nhận event được phát đúng khi commit và không phát khi rollback.

Các kịch bản quan trọng:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Mutation/service commit thành công | Listener AFTER_COMMIT nhận event đúng một lần trong test đồng bộ. |
| Transaction rollback | Listener AFTER_COMMIT không được gọi. |
| Event được publish ngoài transaction | Listener không chạy nếu fallbackExecution=false. |
| Listener AFTER_ROLLBACK | Chạy khi transaction rollback. |
| Listener ghi DB sau commit | Ghi bằng transaction độc lập nếu cần commit thay đổi mới. |
| Outbox insert và aggregate save | Cùng commit hoặc cùng rollback. |
| Publisher gửi thành công rồi crash trước khi mark | Có thể gửi duplicate; consumer phải idempotent. |
| Async listener thất bại | Transaction gốc vẫn đã commit; lỗi cần được quan sát và xử lý riêng. |

Ví dụ integration test cho commit:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PlaceOrderEventTests {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    RecordingOrderPlacedListener recordingListener;

    @Test
    void publishesEventAfterServiceTransactionCommits() {
        Order order = placeOrderService.place(validInput());

        assertThat(recordingListener.events())
                .extracting(OrderPlaced::orderId)
                .contains(order.getId());
    }
}
~~~

Test này không đặt @Transactional ở cấp test. Transaction do service mở được commit khi method service trả về qua proxy, nên listener AFTER_COMMIT có thể chạy trước assertion. Nếu test class hoặc test method có transaction riêng, transaction test thường rollback khi kết thúc; assertion trong method có thể chạy trước commit và listener chưa được gọi. Khi đó hãy kết thúc transaction test một cách tường minh bằng TestTransaction hoặc thiết kế test không bọc transaction ngoài.

Với listener async, không assert ngay lập tức rằng event đã được xử lý; dùng Awaitility hoặc cơ chế đồng bộ trong test để đợi kết quả có giới hạn thời gian. Không dùng Thread.sleep cố định làm đồng bộ.

## 21. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Listener chạy dù mutation rollback | Dùng @EventListener hoặc gửi broker ngay trong transaction | Dùng @TransactionalEventListener(AFTER_COMMIT) cho listener cần commit thành công. |
| Listener không chạy | Event được publish ngoài transaction và fallbackExecution=false | Kiểm tra transaction boundary; chỉ bật fallback nếu nghiệp vụ chấp nhận. |
| Email được gửi nhưng order không tồn tại | Gửi side effect trước khi transaction commit | Chờ AFTER_COMMIT hoặc dùng outbox. |
| Order đã commit nhưng broker không nhận event | Process dừng sau commit trước khi publish | Dùng transactional outbox hoặc CDC. |
| Listener ghi DB nhưng thay đổi không được commit | Ghi sau AFTER_COMMIT vào resource của transaction đã hoàn tất | Gọi service dùng REQUIRES_NEW. |
| GraphQL trả lỗi nhưng order đã được lưu | Listener đồng bộ ném lỗi sau commit | Xử lý lỗi listener; dùng async/outbox khi phù hợp và thiết kế mutation idempotent. |
| Listener async không có tenant/user context | ThreadLocal hoặc request context không tự truyền sang executor | Đưa metadata cần thiết vào event payload một cách có kiểm soát. |
| Event consumer xử lý trùng | Broker/outbox retry có thể giao lại event | Dùng eventId và idempotent consumer/inbox. |
| Event đến sai thứ tự | Nhiều worker hoặc partition không giữ thứ tự aggregate | Dùng aggregate version/sequence và partition/claim phù hợp. |
| Test không thấy AFTER_COMMIT listener | Test đang chạy trong transaction rollback cuối test | Không bọc transaction test hoặc commit rõ ràng trước assertion. |
| Reactive listener không thấy transaction | Dùng thread-bound assumption trong Reactor pipeline | Dùng TransactionalEventPublisher từ Spring 6.1 và truyền transaction context đúng cách. |

## 22. Checklist thiết kế domain event sau mutation

1. Đặt transaction boundary rõ ràng ở application service hoặc mutation method.
2. Tạo event mô tả fact nghiệp vụ đã xảy ra, dùng payload bất biến.
3. Phát event trong transaction đang ghi aggregate.
4. Dùng @TransactionalEventListener(AFTER_COMMIT) cho listener chỉ chạy khi commit thành công.
5. Hiểu rõ BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION.
6. Giữ fallbackExecution=false nếu event bắt buộc phải gắn với transaction.
7. Không gửi email/broker trước commit.
8. Không truyền JPA entity hoặc request context mutable vào async listener.
9. Dùng REQUIRES_NEW nếu listener sau commit cần ghi database mới.
10. Dùng @Async có executor và error handling phù hợp cho công việc dài.
11. Dùng transactional outbox cho integration event không được phép mất.
12. Thiết kế consumer idempotent và xử lý duplicate/order.
13. Với reactive transaction từ Spring 6.1, dùng TransactionalEventPublisher để đưa Reactor transaction context vào event.
14. Kiểm thử cả commit, rollback, no-transaction, async failure và outbox retry.
15. Không nhầm Spring application event với GraphQL Subscription hoặc message broker.

Domain event giúp mutation công bố một sự thật nghiệp vụ mà không buộc controller biết mọi thành phần cần phản ứng. Transaction boundary bảo đảm event chỉ được xử lý theo kết quả commit phù hợp; @TransactionalEventListener là lựa chọn đơn giản cho listener trong process. Khi cần chuyển event ra broker với độ tin cậy cao, transactional outbox kết hợp idempotent consumer sẽ xử lý cả rollback, process crash và duplicate delivery.

Tài liệu tham khảo:
- [Spring for GraphQL — Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html#data.transaction)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [AWS Prescriptive Guidance — Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
