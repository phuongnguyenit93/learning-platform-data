# Tách logic nghiệp vụ khỏi framework và hạ tầng hiện có

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện sự phụ thuộc giữa logic nghiệp vụ, framework, runtime và hạ tầng trong một ứng dụng Java hiện có.
- Giải thích vì sao cần tách domain logic khỏi HTTP framework, SDK cloud, database driver và cơ chế triển khai.
- Thiết kế domain layer, application layer và adapter bằng nguyên tắc Dependency Inversion.
- Áp dụng Ports and Adapters (Hexagonal Architecture) để giữ use case độc lập với công nghệ triển khai.
- Chuyển một endpoint hoặc batch job hiện có thành Java function mà không đưa chi tiết serverless vào domain model.
- Tách transaction, persistence, messaging và external API thành các port có thể thay thế.
- Quản lý event contract, idempotency và outbox khi chuyển từ xử lý đồng bộ sang bất đồng bộ.
- Lập kế hoạch migration theo từng lát chức năng, kiểm thử tương đương và chuyển traffic an toàn.

## 1. Vì sao phải tách logic nghiệp vụ trước khi di chuyển sang serverless?

Một ứng dụng Java truyền thống thường được xây dựng quanh một framework web, application server hoặc bộ thư viện hạ tầng. Controller nhận HTTP request, gọi service, service dùng ORM, database client, message broker và các SDK bên ngoài. Theo thời gian, logic nghiệp vụ có thể phụ thuộc trực tiếp vào annotation, transaction API, entity persistence, HTTP session hoặc class của nhà cung cấp cloud.

Khi di chuyển sang serverless, runtime và cách kích hoạt ứng dụng thay đổi. Một function có thể được gọi bởi HTTP, message, schedule hoặc event từ dịch vụ cloud. Nếu business logic phụ thuộc chặt vào framework cũ, nhóm phải viết lại nhiều phần chỉ để thay entry point và adapter. Việc đó làm migration dài hơn, tăng nguy cơ sai lệch nghiệp vụ và khiến hệ thống mới khó kiểm thử.

Mục tiêu là giữ các quy tắc nghiệp vụ ổn định trong khi thay đổi cách nhận request, lưu dữ liệu, gửi message và triển khai. Domain không cần biết nó đang chạy trong servlet container, AWS Lambda, Google Cloud Run functions hay một test JVM.

### 1.1. Ví dụ về coupling

Một service có thể trộn lẫn nhiều trách nhiệm:

~~~java
@Service
public class OrderService {

    @Autowired
    private OrderRepository repository;

    @Autowired
    private SqsClient sqsClient;

    @Transactional
    public OrderEntity createOrder(CreateOrderRequest request) {
        if (request.getItems().isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Order must contain items");
        }

        OrderEntity order = new OrderEntity();
        order.setCustomerId(request.getCustomerId());
        order.setStatus("CREATED");
        repository.save(order);

        sqsClient.sendMessage(builder -> builder
                .queueUrl(System.getenv("ORDER_QUEUE_URL"))
                .messageBody(order.getId().toString()));

        return order;
    }
}
~~~

Đoạn code này gắn nghiệp vụ với nhiều chi tiết kỹ thuật:

- `@Service`, `@Autowired` và `@Transactional` thuộc framework.
- `OrderEntity` có thể là persistence entity của ORM.
- `SqsClient` là SDK cụ thể của AWS.
- `ResponseStatusException` và `HttpStatus` thuộc HTTP layer.
- `System.getenv` lấy cấu hình trực tiếp từ runtime.
- Service tự quyết định queue URL và cách publish message.

Nếu chuyển service này sang một function trên nền tảng khác, nhóm phải thay nhiều dòng code dù quy tắc tạo đơn hàng không đổi. Unit test cũng cần nhiều mock và cấu hình framework hơn mức cần thiết.

### 1.2. Mục tiêu sau khi tách

Một thiết kế tách lớp có thể như sau:

~~~mermaid
flowchart TD
    A[HTTP adapter / Event adapter] --> B[Application use case]
    B --> C[Domain model and rules]
    B --> D[Repository port]
    B --> E[Event publisher port]
    D --> F[Database adapter]
    E --> G[Queue or event adapter]
    A --> H[Request/response mapping]
~~~

Domain chứa quy tắc nghiệp vụ và không phụ thuộc framework. Application layer điều phối use case và gọi các port. Adapter chuyển đổi giao thức hoặc công nghệ thành các lời gọi port.

Khi chuyển sang serverless, có thể thay HTTP adapter bằng function handler, thay persistence adapter bằng database client phù hợp hoặc thay event publisher bằng dịch vụ messaging khác. Use case vẫn giữ nguyên nếu semantics nghiệp vụ không đổi.

### 1.3. Không phải mọi abstraction đều cần thiết

Tách logic không có nghĩa tạo interface cho mọi class hoặc xây dựng một framework nội bộ phức tạp. Hãy tạo boundary tại nơi có lý do thay đổi độc lập:

- Domain rule cần kiểm thử mà không có database.
- Database có thể đổi engine hoặc cách truy cập.
- HTTP endpoint có thể được thay bằng event trigger.
- Message broker hoặc cloud provider có thể thay đổi.
- Clock, ID generator hoặc external API cần giả lập trong test.

Một class thuần tính toán, không có dependency ngoài và không cần thay thế, có thể chỉ là một class Java bình thường. Abstraction chỉ hữu ích khi nó bảo vệ một boundary có ý nghĩa.

## 2. Nhận diện dependency và ranh giới nghiệp vụ

Trước khi sửa code, hãy lập bản đồ các thành phần và xác định phần nào mô tả nghiệp vụ, phần nào là chi tiết triển khai.

### 2.1. Phân loại thành phần

| Thành phần hiện có | Loại | Hướng xử lý khi tách |
|---|---|---|
| Quy tắc tính giá, trạng thái đơn hàng | Domain | Giữ trong domain model/service thuần Java |
| Quy trình tạo đơn, hủy đơn | Application use case | Giữ trong application layer |
| REST controller, servlet | Inbound adapter | Chuyển request sang command/use case |
| Lambda handler hoặc Functions Framework handler | Inbound adapter | Chỉ parse event, validate contract và gọi use case |
| JPA repository/ORM | Outbound adapter | Implement repository port |
| SQS, Pub/Sub, Kafka client | Outbound adapter | Implement event/message port |
| Cloud SDK, storage client | Outbound adapter | Ẩn sau port khi domain/use case cần |
| Transaction manager | Infrastructure | Đặt ranh giới transaction rõ ràng |
| Environment variables, secret manager | Configuration adapter | Đưa cấu hình vào object cấu hình có kiểu |
| HTTP status và framework exception | Delivery adapter | Map application result/error sang protocol |

### 2.2. Tìm dependency bị ẩn

Ngoài các import dễ thấy, coupling thường xuất hiện qua:

- Annotation làm thay đổi lifecycle hoặc transaction.
- Static singleton và global mutable state.
- Environment variable được đọc từ nhiều class.
- Entity ORM được trả trực tiếp ra API.
- Exception framework được ném từ business service.
- Clock hoặc UUID generator được gọi trực tiếp khiến test khó lặp lại.
- Thread, executor hoặc scheduler do framework quản lý.
- Callback của cloud SDK nằm trong domain logic.
- Transaction mở ở controller hoặc bị phụ thuộc vào request thread.
- Message được publish trước khi transaction database commit.

Hãy tìm những dependency này trong call graph. Một class có ít import vẫn có thể phụ thuộc framework qua static helper hoặc runtime context.

### 2.3. Xác định domain boundary bằng ngôn ngữ nghiệp vụ

Domain boundary nên dựa trên khái niệm và quy tắc của nghiệp vụ. Ví dụ, một order có thể có trạng thái `DRAFT`, `CONFIRMED`, `PAID`, `CANCELLED`; chuyển trạng thái phải tuân theo điều kiện rõ ràng.

Đừng để tên trạng thái chỉ là chuỗi tùy ý được gán từ controller hoặc database. Dùng enum/value object và phương thức domain để bảo vệ invariant.

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    PAID,
    CANCELLED
}
~~~

~~~java
public final class Order {

    private final OrderId id;
    private final CustomerId customerId;
    private final java.util.List<OrderLine> items;
    private OrderStatus status;

    public Order(OrderId id, CustomerId customerId, OrderStatus status) {
        this(id, customerId, status, java.util.List.of());
    }

    private Order(
            OrderId id,
            CustomerId customerId,
            OrderStatus status,
            java.util.List<OrderLine> items) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.items = java.util.List.copyOf(items);
    }

    public static Order create(
            OrderId id,
            CustomerId customerId,
            java.util.List<OrderLine> items) {
        if (items.isEmpty()) {
            throw new InvalidOrderException("Order must contain items");
        }
        return new Order(id, customerId, OrderStatus.DRAFT, items);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException(
                    "Only a draft order can be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public void markPaid() {
        if (status != OrderStatus.CONFIRMED) {
            throw new InvalidOrderStateException(
                    "Only a confirmed order can be paid");
        }
        status = OrderStatus.PAID;
    }

    public OrderId id() {
        return id;
    }

    public CustomerId customerId() {
        return customerId;
    }

    public OrderStatus status() {
        return status;
    }

    public java.util.List<OrderLine> items() {
        return items;
    }

    public record OrderLine(String productId, int quantity) {
        public OrderLine {
            if (productId == null || productId.isBlank() || quantity < 1) {
                throw new InvalidOrderException("Invalid order line");
            }
        }
    }
}
~~~

Domain model không cần biết order được lưu bằng JPA, DynamoDB, Firestore hay một REST service. Nó chỉ bảo vệ các quy tắc và trạng thái hợp lệ.

## 3. Kiến trúc Ports and Adapters

Ports and Adapters, còn gọi là Hexagonal Architecture, tổ chức ứng dụng quanh use case và các boundary. Port mô tả điều ứng dụng cần hoặc cung cấp. Adapter chuyển đổi một công nghệ cụ thể sang contract của port.

### 3.1. Inbound port và outbound port

- **Inbound port:** use case mà bên ngoài có thể yêu cầu ứng dụng thực hiện, ví dụ `CreateOrderUseCase`.
- **Inbound adapter:** nhận lệnh từ HTTP, message, CLI, scheduler hoặc function trigger.
- **Outbound port:** dependency mà application cần, ví dụ `OrderRepository`, `PaymentGateway`, `DomainEventPublisher`.
- **Outbound adapter:** triển khai port bằng JPA, JDBC, SQS, Pub/Sub, HTTP client hoặc cloud SDK.

~~~mermaid
flowchart TB
    subgraph Inbound
      A[HTTP handler]
      B[CloudEvent handler]
      C[Scheduled trigger]
    end
    subgraph Application
      D[CreateOrderUseCase]
      E[OrderRepository port]
      F[EventPublisher port]
      G[Domain model]
    end
    subgraph Outbound
      H[JDBC adapter]
      I[Pub/Sub adapter]
      J[Payment API adapter]
    end
    A --> D
    B --> D
    C --> D
    D --> G
    D --> E
    D --> F
    E --> H
    F --> I
    D --> J
~~~

Các adapter nằm ngoài application core. Domain và use case không import class từ adapter. Chiều phụ thuộc trong source code hướng vào contract của application/domain.

### 3.2. Dependency Inversion Principle

Dependency Inversion Principle (DIP) yêu cầu module cấp cao không phụ thuộc trực tiếp module cấp thấp; cả hai phụ thuộc vào abstraction. Abstraction không nên phụ thuộc chi tiết; chi tiết triển khai phụ thuộc abstraction.

Trong migration:

- Use case cần lưu order, vì vậy định nghĩa `OrderRepository`.
- Database adapter implement `OrderRepository`.
- Use case cần phát domain event, vì vậy định nghĩa `DomainEventPublisher`.
- Messaging adapter implement `DomainEventPublisher`.

Application không cần import `SqsClient`, `PubSubTemplate` hoặc `EntityManager`. Các implementation cụ thể được nối vào khi khởi tạo ứng dụng.

### 3.3. Cấu trúc package Java gợi ý

~~~text
order-service/
└── src/main/java/com/example/orders/
    ├── domain/
    │   ├── model/
    │   ├── event/
    │   └── exception/
    ├── application/
    │   ├── port/in/
    │   ├── port/out/
    │   ├── service/
    │   └── command/
    ├── adapter/
    │   ├── in/http/
    │   ├── in/function/
    │   ├── in/messaging/
    │   └── out/
    │       ├── persistence/
    │       ├── messaging/
    │       └── payment/
    └── bootstrap/
        └── ApplicationConfiguration.java
~~~

Package là cách tổ chức, không phải quy tắc bắt buộc. Project nhỏ có thể dùng module/package đơn giản hơn. Điều quan trọng là domain/application không bị kéo ngược vào adapter.

## 4. Thiết kế domain và application layer

Domain layer mô tả thực thể, value object, invariant và domain service. Application layer điều phối use case, transaction, authorization context và các port cần thiết.

### 4.1. Domain model thuần Java

Domain model nên dùng kiểu dữ liệu phản ánh khái niệm nghiệp vụ. Tránh phụ thuộc `HttpServletRequest`, `ResponseEntity`, ORM entity hoặc cloud event.

Ví dụ value object:

~~~java
import java.util.Objects;
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }

    public static OrderId newId() {
        return new OrderId(UUID.randomUUID());
    }
}
~~~

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
~~~

Value object giúp gom validation vào nơi tạo dữ liệu, giảm việc truyền chuỗi và số không có ý nghĩa rõ ràng. Với tiền tệ, tránh dùng `double`; dùng `BigDecimal` và currency cụ thể.

### 4.2. Application command và result

Command mô tả yêu cầu của use case. Nó không phải HTTP DTO hay message envelope.

~~~java
import java.util.List;

public record CreateOrderCommand(
        String customerId,
        List<CreateOrderItem> items,
        String idempotencyKey) {

    public CreateOrderCommand {
        items = List.copyOf(items);
    }
}

public record CreateOrderItem(
        String productId,
        int quantity) {}
~~~

Result mô tả kết quả use case:

~~~java
public record CreateOrderResult(
        String orderId,
        String status) {}
~~~

HTTP adapter có thể map JSON sang command và map result sang JSON response. Event adapter có thể map CloudEvent data sang cùng command nếu semantics phù hợp. Command không nên chứa `HttpRequest`, `CloudEvent`, `APIGatewayProxyRequestEvent` hoặc SDK-specific type.

### 4.3. Định nghĩa inbound port

~~~java
public interface CreateOrderUseCase {
    CreateOrderResult create(CreateOrderCommand command);
}
~~~

Use case có contract rõ ràng và có thể được gọi từ nhiều entry point. Không để controller hoặc function handler gọi trực tiếp repository nếu thao tác đó thuộc quy trình nghiệp vụ.

### 4.4. Định nghĩa outbound ports

~~~java
import java.util.Optional;

public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(OrderId id);
    boolean existsByIdempotencyKey(String key);
    void recordIdempotencyKey(String key, OrderId orderId);
}
~~~

~~~java
public interface OrderEventPublisher {
    void publish(OrderCreated event);
}
~~~

~~~java
public interface IdGenerator {
    OrderId newOrderId();
}
~~~

Port nên mô tả nhu cầu của ứng dụng. Đừng sao chép nguyên API của SDK vào interface; nếu port chỉ có các method `sendMessage(softwareVendorRequest)` hoặc `save(EntityManager)`, abstraction vẫn bị dính công nghệ.

### 4.5. Implement use case

~~~java
public final class CreateOrderService implements CreateOrderUseCase {

    private final OrderRepository orders;
    private final OrderEventPublisher events;
    private final IdGenerator ids;

    public CreateOrderService(
            OrderRepository orders,
            OrderEventPublisher events,
            IdGenerator ids) {
        this.orders = orders;
        this.events = events;
        this.ids = ids;
    }

    @Override
    public CreateOrderResult create(CreateOrderCommand command) {
        validate(command);

        if (orders.existsByIdempotencyKey(command.idempotencyKey())) {
            // Trong ứng dụng thật, đọc lại và trả về kết quả đã lưu.
            throw new DuplicateOrderRequestException();
        }

        java.util.List<Order.OrderLine> lines = command.items().stream()
                .map(item -> new Order.OrderLine(item.productId(), item.quantity()))
                .toList();

        Order order = Order.create(
                ids.newOrderId(),
                new CustomerId(command.customerId()),
                lines);

        orders.save(order);
        orders.recordIdempotencyKey(command.idempotencyKey(), order.id());
        events.publish(new OrderCreated(order.id(), order.customerId()));

        return new CreateOrderResult(
                order.id().value().toString(),
                order.status().name());
    }

    private void validate(CreateOrderCommand command) {
        if (command.items().isEmpty()) {
            throw new InvalidOrderException("Order must contain items");
        }
        if (command.idempotencyKey() == null
                || command.idempotencyKey().isBlank()) {
            throw new InvalidOrderException("Idempotency key is required");
        }
    }
}
~~~

Đây là ví dụ cấu trúc để minh họa dependency inversion. Trong production, việc lưu order, idempotency key và phát event cần transaction/outbox phù hợp; không nên giả định ba lời gọi riêng lẻ tự động nguyên tử. Kiểm tra key trước khi ghi cũng chưa đủ để chống hai request đồng thời; cần unique constraint hoặc thao tác claim nguyên tử trong persistence adapter. Phần event publication được thiết kế chi tiết ở phần sau.

## 5. Tách persistence và transaction khỏi use case

Persistence adapter chuyển đổi giữa domain model và database schema. Domain object không nên buộc phải mang annotation ORM hoặc kế thừa base class của framework persistence.

### 5.1. Domain model và persistence entity

Một JPA entity có thể có field, constructor và lifecycle phục vụ ORM. Domain model có thể có invariant và hành vi nghiệp vụ khác. Hai mô hình có thể giống nhau trong ứng dụng nhỏ, nhưng khi coupling bắt đầu cản migration, hãy tách chúng bằng mapper.

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {

    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private String customerId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected OrderJpaEntity() {}

    // getters/setters for ORM
}
~~~

Adapter thực hiện mapping:

~~~java
import java.util.Optional;

public final class JpaOrderRepository implements OrderRepository {

    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderRepository(
            SpringDataOrderRepository repository,
            OrderMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return repository.findById(id.value())
                .map(mapper::toDomain);
    }

    @Override
    public boolean existsByIdempotencyKey(String key) {
        return repository.existsByIdempotencyKey(key);
    }

    @Override
    public void recordIdempotencyKey(String key, OrderId orderId) {
        repository.insertIdempotencyRecord(key, orderId.value());
    }
}
~~~

Ví dụ giả định `SpringDataOrderRepository` cung cấp các method truy vấn/ghi idempotency record tương ứng. `SpringDataOrderRepository`, JPA entity và transaction framework chỉ xuất hiện trong adapter. Khi chuyển sang JDBC, DynamoDB hoặc Firestore, có thể thay adapter và mapper mà không sửa domain rules.

### 5.2. Đặt transaction boundary ở application

Transaction là một phần của orchestration use case nhưng API transaction cụ thể là hạ tầng. Có một số cách:

- Dùng application service được framework quản lý transaction nhưng giữ annotation trong adapter/decorator.
- Định nghĩa port `UnitOfWork` hoặc transaction runner nếu ứng dụng cần điều khiển transaction độc lập.
- Để repository adapter quản lý transaction khi thao tác chỉ thuộc một repository và semantics rõ ràng.

Không mở transaction quá rộng quanh toàn bộ function invocation nếu use case còn gọi HTTP API hoặc chờ message. Transaction dài giữ connection/lock, tăng chi phí và dễ timeout. Chỉ bao transaction quanh thao tác database cần tính nguyên tử.

### 5.3. Ví dụ transaction runner

~~~java
public interface TransactionRunner {
    <T> T inTransaction(java.util.concurrent.Callable<T> work);
}
~~~

Application có thể dùng port này nếu transaction là một boundary cần điều khiển. Adapter triển khai bằng transaction manager của framework hoặc cơ chế của database.

Tuy nhiên, không nên tạo transaction abstraction quá chung để bao cả database, queue và HTTP API. Một transaction database không thể tự bảo đảm atomicity với hệ thống bên ngoài.

### 5.4. Transaction và serverless

Trong serverless, execution environment có thể bị dừng bất kỳ lúc nào sau invocation. Không giữ transaction qua nhiều invocation hoặc qua một workflow dài. Với công việc nhiều bước, lưu trạng thái bền vững và dùng orchestration/state machine hoặc saga phù hợp.

Một use case nên xác định rõ:
- Phần nào cần commit cùng nhau trong một database transaction.
- Phần nào là side effect bên ngoài.
- Nếu side effect thất bại sau commit, hệ thống phục hồi ra sao.
- Nếu function bị timeout sau commit, invocation lại có thể an toàn không.

## 6. Tách message và event contract

Chuyển một ứng dụng sang serverless thường kéo theo chuyển từ gọi đồng bộ sang event-driven. Không để domain model phụ thuộc envelope cụ thể của SQS, Pub/Sub, Eventarc hoặc Kafka.

### 6.1. Domain event và integration event

**Domain event** diễn tả điều có ý nghĩa trong domain, ví dụ `OrderConfirmed`. Nó có thể chứa domain identifier và dữ kiện nghiệp vụ cần thiết.

**Integration event** là contract công bố cho hệ thống khác. Nó cần schema/version, event ID, occurred time, source và dữ liệu tương thích. Một domain event có thể được map sang một hoặc nhiều integration event.

~~~java
public record OrderConfirmed(
        OrderId orderId,
        CustomerId customerId) {}
~~~

~~~java
public record OrderConfirmedV1(
        String eventId,
        String orderId,
        String customerId,
        String occurredAt,
        int schemaVersion) {}
~~~

Adapter messaging chịu trách nhiệm serialize integration event thành định dạng và metadata mà broker yêu cầu. Domain không nên import `SqsEvent`, `PubSubMessage`, `CloudEvent` hoặc class tương tự.

### 6.2. Outbox pattern để tránh mất event

Nếu use case lưu order trong database rồi publish message trực tiếp, có một khoảng lỗi:

1. Database commit thành công.
2. Function bị dừng trước khi publish.
3. Order đã tồn tại nhưng consumer không nhận event.

Nếu publish trước database commit, consumer có thể nhận event cho dữ liệu chưa được commit hoặc transaction cuối cùng rollback.

Outbox pattern giải quyết bằng cách ghi domain data và event record vào cùng transaction database:

~~~mermaid
flowchart TD
    A[Application use case] --> B[Database transaction]
    B --> C[Save order]
    B --> D[Insert outbox event]
    C --> E[Commit]
    D --> E
    E --> F[Outbox publisher]
    F --> G[Message broker]
    G --> H[Consumer function]
~~~

Publisher riêng đọc outbox chưa gửi, publish message và đánh dấu trạng thái. Publisher có thể chạy bằng scheduled function hoặc worker. Nếu publish thành công nhưng worker chết trước khi đánh dấu sent, event có thể được gửi lại; consumer vẫn cần idempotency.

### 6.3. Port cho outbox

Application có thể định nghĩa port ghi event cùng transaction với aggregate:

~~~java
public interface OrderRepository {
    void save(Order order);
    void appendOutboxEvent(OrderCreated event);
}
~~~

Hoặc định nghĩa một port persistence transaction rõ hơn để đảm bảo cả hai thao tác dùng chung transaction. Cách chọn phụ thuộc database và module boundary; điều quan trọng là contract thể hiện tính nguyên tử cần thiết.

Không để application gọi hai adapter độc lập rồi hy vọng chúng dùng cùng transaction. Transaction phải được bảo đảm bởi implementation và được kiểm thử.

### 6.4. Versioning event contract

Event được nhiều consumer sử dụng cần tương thích ngược. Một số nguyên tắc:

- Thêm field optional thường an toàn hơn đổi tên/xóa field.
- Không thay đổi ý nghĩa của field đã công bố.
- Dùng schema version khi có thay đổi không tương thích.
- Consumer bỏ qua field chưa biết nếu contract cho phép.
- Giữ identifier ổn định và phân biệt event ID với aggregate ID.
- Kiểm thử consumer với payload của version cũ.
- Không serialize trực tiếp domain object thành integration event vì domain refactor có thể làm hỏng contract.

### 6.5. Idempotency ở consumer

Consumer function có thể nhận lại cùng message. Dùng event ID hoặc business operation ID làm idempotency key, lưu trạng thái bền vững và bảo đảm thao tác ghi an toàn khi chạy lặp.

Không dùng cache trong RAM hoặc static set làm nơi chống duplicate. Instance có thể bị thu hồi và nhiều instance có thể nhận cùng message gần như đồng thời.

## 7. Tạo inbound adapter cho HTTP function

HTTP function là adapter tiếp nhận giao thức. Nó đọc request, xác thực định dạng, map sang command và chuyển kết quả use case thành response.

### 7.1. Handler mỏng

~~~java
public final class CreateOrderHttpHandler {

    private final CreateOrderUseCase useCase;
    private final CreateOrderRequestMapper mapper;

    public CreateOrderHttpHandler(
            CreateOrderUseCase useCase,
            CreateOrderRequestMapper mapper) {
        this.useCase = useCase;
        this.mapper = mapper;
    }

    public HttpResult handle(HttpRequestData request) {
        CreateOrderCommand command = mapper.toCommand(request);
        CreateOrderResult result = useCase.create(command);
        return HttpResult.created(mapper.toResponse(result));
    }
}
~~~

Ở đây `HttpRequestData` và `HttpResult` có thể là DTO nội bộ của adapter hoặc kiểu framework cụ thể. Chúng không đi qua application boundary. Adapter kiểm tra method, header, authentication context, content type và payload size trước khi gọi use case.

### 7.2. Map exception sang HTTP

Domain không nên ném `ResponseStatusException`. Adapter map exception nghiệp vụ sang status code:

| Lỗi application/domain | HTTP mapping ví dụ |
|---|---|
| Input không hợp lệ | 400 |
| Resource không tồn tại | 404 |
| Xung đột trạng thái | 409 |
| Không xác thực | 401 |
| Không có quyền | 403 |
| Dependency tạm thời lỗi | 503 |
| Lỗi không dự kiến | 500 |

Đây là contract của API; có thể khác theo sản phẩm. Không trả stack trace hoặc thông tin database cho client. Ghi log an toàn kèm request ID và correlation ID.

### 7.3. Một use case có thể có nhiều inbound adapter

Cùng `CreateOrderUseCase` có thể được gọi từ:
- REST endpoint trong ứng dụng cũ.
- HTTP function sau migration.
- Message consumer nếu nghiệp vụ cho phép tạo order từ event.
- CLI hoặc admin tool.
- Test trực tiếp.

Nhiều adapter không có nghĩa mọi giao thức phải được hỗ trợ. Chỉ tạo adapter khi có use case thực tế và contract rõ ràng.

## 8. Tạo inbound adapter cho serverless event

Event handler nhận CloudEvent hoặc message envelope từ runtime, kiểm tra loại event và chuyển payload thành command. Handler không nên chứa toàn bộ quy tắc nghiệp vụ.

### 8.1. Adapter cho CloudEvents

~~~java
public final class OrderEventFunction
        implements com.google.cloud.functions.CloudEventsFunction {

    private final ConfirmOrderUseCase useCase;
    private final OrderEventMapper mapper;

    public OrderEventFunction(
            ConfirmOrderUseCase useCase,
            OrderEventMapper mapper) {
        this.useCase = useCase;
        this.mapper = mapper;
    }

    @Override
    public void accept(io.cloudevents.CloudEvent event) throws Exception {
        if (!"com.example.order.confirmed-request".equals(event.getType())) {
            return;
        }

        ConfirmOrderCommand command = mapper.toCommand(event);
        useCase.confirm(command);
    }
}
~~~

Đây là ví dụ adapter. Trong triển khai thực tế, Functions Framework có thể tạo entry point theo cấu hình runtime; cần bảo đảm cách dependency injection và lifecycle phù hợp với runtime đang dùng.

Handler nên:
- Kiểm tra event type và schema version.
- Kiểm tra event ID/source.
- Validate payload và tenant/resource scope.
- Chuyển đổi sang command.
- Gọi use case.
- Ném lỗi theo semantics của trigger nếu muốn nền tảng retry.
- Ghi log event ID và correlation ID.

### 8.2. Không đưa CloudEvent vào domain

Không định nghĩa domain method kiểu:

~~~java
// Không nên
public void confirm(io.cloudevents.CloudEvent event) { ... }
~~~

Thay vào đó, adapter map event data thành command/domain value object. Như vậy domain không phụ thuộc transport và có thể nhận cùng lệnh từ HTTP, queue hoặc test.

### 8.3. Trigger khác nhau, use case có thể giống nhau

Một yêu cầu từ HTTP và một yêu cầu từ message có thể dẫn đến cùng một use case, nhưng semantics không nhất thiết giống nhau:

- HTTP thường cần response ngay và deadline ngắn.
- Message consumer có ack/redelivery semantics.
- Scheduled invocation có thể chạy lặp theo lịch.
- Storage event có payload và idempotency key riêng.

Adapter chịu trách nhiệm xử lý semantics giao thức. Application use case chỉ nhận command có ý nghĩa nghiệp vụ và trả result hoặc lỗi application.

## 9. Composition root và dependency injection

Tách port/adapter chỉ có tác dụng khi có nơi nối implementation cụ thể. Composition root là điểm khởi tạo application và wiring dependency.

### 9.1. Wiring thuần Java

~~~java
public final class ApplicationConfiguration {

    public CreateOrderUseCase createOrderUseCase(
            OrderRepository repository,
            OrderEventPublisher publisher,
            IdGenerator idGenerator) {
        return new CreateOrderService(
                repository, publisher, idGenerator);
    }
}
~~~

Ở runtime có DI framework, container có thể tạo adapter và use case. Với function nhỏ, có thể khởi tạo dependency bằng factory hoặc dependency injection thủ công. Chọn cách phù hợp với startup time, lifecycle và testability.

### 9.2. Tách cấu hình khỏi business logic

Không đọc environment variable trực tiếp trong domain hoặc use case. Đưa cấu hình vào typed configuration:

~~~java
public record OrderServiceConfig(
        String queueName,
        int maxItemsPerOrder,
        java.time.Duration paymentTimeout) {}
~~~

Configuration adapter đọc environment variable, parameter store hoặc secret manager rồi tạo object này. Use case nhận các giá trị cần thiết qua constructor hoặc policy object.

Secret nên được lấy từ secret manager và cấp bằng runtime identity. Không nhúng secret vào source, artifact hoặc event payload.

### 9.3. Lifecycle và cold start

Serverless runtime có thể tái sử dụng execution environment. Dependency dùng chung như HTTP client hoặc SDK client có thể được tạo một lần nếu thread-safe và không giữ state theo request.

Không lưu user, tenant, request context hoặc transaction state trong mutable static field. Không chạy truy vấn database hoặc gọi API ngoài trong static initializer nếu thao tác có thể thất bại hoặc kéo dài cold start.

### 9.4. Không để framework chiếm domain

Framework vẫn có thể được dùng trong adapter/bootstrap. Mục tiêu không phải loại bỏ Spring, Quarkus, Micronaut hay Functions Framework khỏi toàn bộ project. Mục tiêu là giới hạn dependency của chúng ở lớp phù hợp, để business rules không cần biết framework đang chạy.

## 10. Kiểm thử sau khi tách lớp

Tách domain và use case khỏi framework giúp kiểm thử nhanh hơn. Mỗi tầng có mục tiêu kiểm thử khác nhau.

### 10.1. Unit test domain

Domain test kiểm tra invariant và chuyển trạng thái mà không cần container, database hoặc cloud credentials.

~~~java
@Test
void onlyDraftOrderCanBeConfirmed() {
    Order order = new Order(
            new OrderId(UUID.randomUUID()),
            new CustomerId("customer-1"),
            OrderStatus.DRAFT);

    order.confirm();

    assertEquals(OrderStatus.CONFIRMED, order.status());
}
~~~

~~~java
@Test
void paidOrderCannotBeConfirmedAgain() {
    Order order = new Order(
            new OrderId(UUID.randomUUID()),
            new CustomerId("customer-1"),
            OrderStatus.PAID);

    assertThrows(
            InvalidOrderStateException.class,
            order::confirm);
}
~~~

### 10.2. Unit test application service

Mock các outbound port để kiểm tra orchestration, không cần mock framework internals:

~~~java
@Test
void createOrderPersistsOrderAndPublishesEvent() {
    OrderRepository repository = mock(OrderRepository.class);
    OrderEventPublisher publisher = mock(OrderEventPublisher.class);
    IdGenerator ids = () -> new OrderId(UUID.fromString(
            "00000000-0000-0000-0000-000000000001"));

    CreateOrderUseCase useCase =
            new CreateOrderService(repository, publisher, ids);

    CreateOrderCommand command = new CreateOrderCommand(
            "customer-1",
            List.of(new CreateOrderItem("product-1", 2)),
            "request-key-123");

    CreateOrderResult result = useCase.create(command);

    assertEquals("DRAFT", result.status());
    verify(repository).save(any(Order.class));
    verify(publisher).publish(any(OrderCreated.class));
}
~~~

Test này minh họa cách cô lập application layer. Với implementation dùng outbox, test cần xác minh event record được ghi trong cùng transaction với aggregate, và integration test phải kiểm tra transaction rollback/commit.

### 10.3. Contract test cho adapter

- HTTP adapter: method, status, headers, validation, authentication và error mapping.
- Event adapter: event type, schema version, missing field, duplicate event và retry behavior.
- Persistence adapter: mapping, query, transaction và unique constraint.
- Messaging adapter: serialization, attributes, ordering hoặc delivery contract nếu có.
- External API adapter: timeout, status mapping, retry và idempotency header.

### 10.4. Integration test

Chạy adapter với database hoặc broker test thật khi semantics của hạ tầng quan trọng. Test container hoặc emulator có thể hữu ích, nhưng cần biết khác biệt với dịch vụ production. Không coi unit test mock là bằng chứng rằng IAM, network, trigger hoặc serialization đã được cấu hình đúng.

## 11. Lộ trình migration từng bước

Không cần tách toàn bộ hệ thống trong một lần. Chọn một use case có boundary rõ, làm cho nó độc lập với framework, sau đó thay adapter và triển khai từng phần.

### 11.1. Bước 1: lập bản đồ và chọn use case

Ghi lại:
- Entry point hiện tại.
- Call graph của nghiệp vụ.
- Dependency database, queue, cache và API.
- Transaction boundary.
- Side effect và event contract.
- Quy tắc authorization.
- SLO, throughput và latency.
- Các hành vi phụ thuộc framework.

Chọn use case có đầu vào/đầu ra rõ và ít shared mutable state. Tránh bắt đầu bằng một quy trình lớn có nhiều transaction phân tán.

### 11.2. Bước 2: tạo characterization tests

Trước khi refactor, ghi lại hành vi hiện tại bằng test và fixture. Bao gồm cả trường hợp thành công, validation, xung đột trạng thái và lỗi dependency.

Characterization test bảo vệ semantics cũ khi tách code. Nếu behavior hiện tại có bug đã biết, ghi nhận quyết định sửa hoặc giữ lại; đừng vô tình thay đổi nghiệp vụ trong lúc migration hạ tầng.

### 11.3. Bước 3: trích domain model

Chuyển invariant, value object và domain service sang class thuần Java. Loại bỏ HTTP status, ORM entity và cloud SDK khỏi domain. Giữ mapper ở adapter để chuyển dữ liệu cũ sang domain object.

### 11.4. Bước 4: định nghĩa use case và ports

Tạo inbound port cho thao tác nghiệp vụ và outbound ports cho các dependency thực sự cần thay thế/kiểm soát. Dùng constructor injection để thể hiện dependency. Không để use case tự tìm implementation bằng static service locator.

### 11.5. Bước 5: chuyển infrastructure thành adapter

Viết adapter cho database, messaging, cache, payment API và clock/ID provider. Giữ transaction boundary rõ. Nếu cần publish event sau commit, thiết kế outbox thay vì gọi broker tùy tiện từ domain service.

### 11.6. Bước 6: tạo serverless adapter

Viết HTTP function hoặc event function thật mỏng. Adapter xử lý:
- Parse protocol.
- Authentication/authorization context.
- Validate transport contract.
- Mapping sang command.
- Gọi use case.
- Mapping result/error.
- Logging và correlation.

Không đưa business rules vào handler chỉ vì function là entry point mới.

### 11.7. Bước 7: shadow, canary hoặc strangler migration

Tùy hệ thống, có thể:
- Chạy logic mới ở chế độ shadow và so sánh kết quả mà không phát side effect.
- Chuyển một tỷ lệ traffic nhỏ qua function mới.
- Route theo tenant, customer hoặc operation type.
- Dùng strangler pattern để thay từng capability.
- Giữ rollback path đến implementation cũ trong thời gian chuyển đổi.

Không để cả hệ thống cũ và mới cùng thực hiện side effect thật nếu không có idempotency/ownership rõ. Shadow execution nên chặn publish, payment hoặc ghi dữ liệu trùng.

### 11.8. Bước 8: quan sát và mở rộng

So sánh:
- Business result và data consistency.
- Error rate, latency p95/p99.
- Retry, duplicate và queue age.
- Database connections và throughput.
- Cold start và duration.
- Cost per successful operation.
- IAM, network và audit logs.

Tăng traffic theo từng bước khi metrics ổn định. Có rollback criteria và owner rõ ràng trước khi chuyển 100%.

### 11.9. Bước 9: loại bỏ đường cũ có kiểm soát

Sau khi traffic chuyển hoàn toàn và dữ liệu được đối soát:
- Dừng route cũ.
- Gỡ scheduled job hoặc listener trùng.
- Thu hồi permission không còn dùng.
- Xóa config/secret cũ sau khi xác minh dependency.
- Cập nhật runbook, dashboard và ownership.
- Lưu contract và migration decision để hỗ trợ vận hành.

Không xóa adapter cũ trước khi chắc chắn không còn consumer, batch hoặc job nào gọi nó.

## 12. Những lỗi thường gặp khi tách framework và hạ tầng

- **Chỉ đổi entry point nhưng business service vẫn phụ thuộc SDK:** function mới vẫn khó kiểm thử và gắn chặt cloud provider.
- **Đưa framework annotation vào domain:** domain model tiếp tục phụ thuộc lifecycle hoặc persistence framework.
- **Dùng persistence entity làm API contract:** schema database thay đổi có thể làm hỏng client.
- **Tạo abstraction giống hệt SDK:** port vẫn phơi bày vendor type nên không tạo boundary thực sự.
- **Tạo quá nhiều interface:** code tăng phức tạp nhưng không có khả năng thay thế hoặc test rõ ràng.
- **Để handler gọi repository trực tiếp:** use case bị bỏ qua và quy tắc nghiệp vụ dễ bị lặp giữa các adapter.
- **Để domain ném HTTP exception:** domain bị ràng buộc với một delivery protocol.
- **Publish message trước khi database commit:** consumer có thể xử lý event cho dữ liệu chưa tồn tại bền vững.
- **Lưu order và outbox ở hai transaction khác nhau:** có thể mất event hoặc tạo event không hợp lệ.
- **Chia nhỏ transaction sai cách:** dữ liệu có thể ở trạng thái trung gian mà không có saga/recovery.
- **Chuyển sang event nhưng không version contract:** consumer cũ có thể lỗi khi producer thay schema.
- **Giả định exactly-once:** redelivery vẫn có thể tạo side effect trùng nếu consumer không idempotent.
- **Dùng mutable static field cho request state:** dữ liệu có thể rò giữa invocation trên cùng instance.
- **Di chuyển toàn bộ hệ thống cùng lúc:** phạm vi lớn khiến khó xác định regression và rollback.
- **Shadow traffic có side effect thật:** hệ thống mới và cũ có thể tạo hai đơn hàng hoặc hai giao dịch.
- **Bỏ qua authorization khi thay adapter:** identity của function có thể khác identity của ứng dụng cũ.
- **Không so sánh behavior trước/sau:** code mới có thể compile nhưng thay đổi quy tắc nghiệp vụ.

## 13. Checklist kiến trúc trước khi deploy

- [ ] Domain model không import HTTP, ORM hoặc cloud SDK.
- [ ] Application use case có contract rõ và được gọi qua inbound port.
- [ ] Outbound port mô tả nhu cầu nghiệp vụ, không sao chép nguyên SDK.
- [ ] Adapter chứa mapping và chi tiết protocol/database/broker.
- [ ] Dependency được inject qua constructor hoặc composition root.
- [ ] Cấu hình và secret không được đọc trực tiếp trong domain.
- [ ] Transaction boundary được xác định và không giữ qua network call dài.
- [ ] Event publication dùng outbox hoặc cơ chế bảo đảm phù hợp.
- [ ] Consumer có idempotency và xử lý redelivery.
- [ ] HTTP DTO, persistence entity và integration event được tách khi cần.
- [ ] Event contract có schema/version và compatibility strategy.
- [ ] Function handler mỏng và chỉ xử lý transport concerns.
- [ ] Runtime identity có quyền tối thiểu cho adapter.
- [ ] Cold start và client lifecycle không giữ request state dùng chung.
- [ ] Unit test domain/application chạy không cần cloud credentials.
- [ ] Contract/integration test xác minh adapter và transaction.
- [ ] Có characterization test để bảo vệ behavior cũ.
- [ ] Shadow/canary không tạo side effect trùng.
- [ ] Có metric, trace, rollback criteria và data reconciliation.
- [ ] Adapter cũ chỉ bị gỡ sau khi xác nhận không còn consumer.

## 14. Tự kiểm tra

**Câu 1.** Vì sao không nên để domain service import HTTP framework hoặc cloud SDK?

**Gợi ý trả lời:** Domain mô tả quy tắc nghiệp vụ ổn định. Nếu nó phụ thuộc framework hoặc SDK, thay runtime, transport hoặc cloud provider sẽ buộc sửa nghiệp vụ và làm test khó hơn. Adapter nên chuyển đổi công nghệ sang contract của application.

**Câu 2.** Inbound port và outbound port khác nhau thế nào?

**Gợi ý trả lời:** Inbound port mô tả use case mà ứng dụng cung cấp cho bên ngoài gọi. Outbound port mô tả dependency mà ứng dụng cần, như repository hoặc event publisher. Adapter triển khai hoặc gọi các port đó bằng công nghệ cụ thể.

**Câu 3.** Vì sao không nên publish event trực tiếp trước khi database commit?

**Gợi ý trả lời:** Consumer có thể nhận event trước khi dữ liệu được commit hoặc trong khi transaction sau đó rollback. Outbox ghi aggregate và event record trong cùng transaction, rồi publisher gửi event sau commit.

**Câu 4.** Khi chuyển sang serverless, vì sao function handler nên mỏng?

**Gợi ý trả lời:** Handler chịu trách nhiệm protocol, parse, validation và mapping. Business rules nằm trong use case/domain để có thể dùng lại từ HTTP, event, schedule và test mà không phụ thuộc trigger.

**Câu 5.** Vì sao cần characterization test trước khi refactor?

**Gợi ý trả lời:** Test ghi lại behavior hiện tại để phát hiện thay đổi ngoài ý muốn khi tách lớp. Nó giúp phân biệt refactor cấu trúc với thay đổi nghiệp vụ.

**Bài tập tình huống:** Một ứng dụng Spring Boot có endpoint tạo đơn hàng. Controller gọi service; service dùng JPA entity, gọi payment API và publish message lên SQS trong cùng phương thức có `@Transactional`. Nhóm muốn chuyển chức năng này sang Java function trên một nền tảng serverless khác. Hãy đề xuất domain model, application use case, inbound/outbound ports, adapter, transaction/outbox, idempotency và kế hoạch rollout.

**Gợi ý:** Tạo domain `Order` với invariant và value object; định nghĩa `CreateOrderUseCase`, `OrderRepository`, `PaymentGateway` và port ghi outbox. HTTP/function adapter map request sang command. Persistence adapter map domain sang entity/schema; payment adapter gọi API với idempotency key ổn định. Ghi order và outbox trong cùng transaction, publisher riêng gửi integration event; consumer idempotent. Bảo vệ behavior bằng characterization test, sau đó shadow không side effect, canary theo tenant hoặc tỷ lệ traffic, đối soát kết quả và giữ rollback path trước khi loại bỏ endpoint cũ.

## Kết luận

Di chuyển sang serverless sẽ dễ kiểm soát hơn khi business logic không phụ thuộc framework và hạ tầng hiện tại. Domain giữ các invariant và quy tắc nghiệp vụ; application layer điều phối use case qua các port; adapter xử lý HTTP, event, database, messaging và cloud SDK. Dependency Inversion giúp thay runtime hoặc provider mà không phải viết lại nghiệp vụ. Transaction, outbox, event versioning và idempotency bảo vệ dữ liệu khi chuyển sang xử lý bất đồng bộ. Migration nên đi theo từng use case, có characterization test, contract test, canary và rollback criteria để giữ behavior trong suốt quá trình thay đổi.
