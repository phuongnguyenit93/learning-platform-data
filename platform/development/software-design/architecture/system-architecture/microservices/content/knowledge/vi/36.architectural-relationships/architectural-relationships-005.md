# Áp dụng Hexagonal, Clean và Onion Architecture bên trong từng Microservice

Microservices chia hệ thống thành những dịch vụ có trách nhiệm nghiệp vụ và vòng đời tương đối độc lập. Tuy nhiên, việc tách ứng dụng thành nhiều service không tự làm code bên trong từng service dễ bảo trì. Một service vẫn có thể bị phụ thuộc chặt vào Spring MVC, JPA, database schema, message broker hoặc nhà cung cấp bên ngoài. Khi framework hoặc cách lưu trữ thay đổi, logic nghiệp vụ cũng phải thay theo; khi kiểm thử, nhóm phải dựng nhiều hạ tầng chỉ để xác nhận một quy tắc đơn giản.

**Hexagonal Architecture, Clean Architecture và Onion Architecture** là ba cách tổ chức mã nguồn nhằm giữ phần nghiệp vụ cốt lõi độc lập với chi tiết kỹ thuật. Cả ba đều nhấn mạnh hướng phụ thuộc đi vào trong, dùng abstraction để bảo vệ domain/application khỏi framework và hạ tầng. Chúng có cách diễn đạt và điểm nhấn khác nhau, nhưng có thể kết hợp trong một Microservice nếu ranh giới được định nghĩa rõ.

Bài viết tập trung vào cách áp dụng các tư tưởng này **bên trong từng service** bằng Java và Spring: Order Service, Inventory Service hoặc Payment Service có thể sở hữu domain model riêng, use case riêng, các cổng giao tiếp và adapter riêng. API, database và broker là chi tiết bên ngoài; chúng không được quyết định cấu trúc nghiệp vụ cốt lõi.

Bài học thuộc nhóm **Quan hệ kiến trúc** trong chủ đề kiến trúc hệ thống Microservices.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Hexagonal, Clean và Onion Architecture cùng những điểm chung và khác biệt.
- Phân biệt domain, application/use case, port, adapter và infrastructure.
- Hiểu dependency rule và vì sao source code phải phụ thuộc hướng vào trong.
- Thiết kế inbound port, outbound port và adapter cho một Microservice Java.
- Tổ chức Spring Boot package để domain không phụ thuộc Spring/JPA/Web.
- Đặt transaction boundary ở application use case và persistence adapter đúng cách.
- Kiểm thử domain/use case mà không cần khởi động database hoặc web server.
- Áp dụng kiến trúc vào REST, messaging, scheduled job và tích hợp bên ngoài.
- Nhận diện các anti-pattern như service layer chỉ chuyển tiếp, interface dư thừa, domain anemic và framework leakage.
- Chọn mức abstraction phù hợp, tránh biến kiến trúc thành nhiều lớp ceremony.
- Refactor dần service hiện có mà không cần rewrite toàn bộ.

## 2. Vì sao cần kiến trúc bên trong một Microservice?

Giả sử Order Service xử lý việc tạo đơn. Một controller nhận JSON, gọi repository JPA, cập nhật trạng thái và gọi HTTP sang Payment. Nếu mọi thứ đặt trong một lớp:

~~~text
OrderController
  |
  +--> validate request
  +--> calculate total
  +--> query database
  +--> reserve inventory
  +--> call payment gateway
  +--> update order
  +--> publish event
~~~

Lớp này chịu trách nhiệm cho HTTP, nghiệp vụ, persistence, tích hợp mạng và messaging. Khi thay framework, test trở nên khó; khi thêm consumer từ Kafka, logic có thể bị sao chép; khi Payment timeout, xử lý trạng thái nghiệp vụ lẫn với code HTTP.

Một cách tổ chức có ranh giới:

~~~text
REST Controller ----+
                    |
Message Listener ---+--> Application Use Case
                    |          |
Scheduled Job ------+          v
                               Domain
                                  |
                                  v
                           Outbound Ports
                                  |
                    +-------------+-------------+
                    |             |             |
                JPA Adapter   HTTP Adapter   Broker Adapter
                    |             |             |
                 Database    External API    Message Broker
~~~

Các adapter là nơi chuyển đổi giao thức và công nghệ. Use case điều phối công việc; domain bảo vệ quy tắc nghiệp vụ. Nếu sau này có thêm GraphQL, Kafka consumer hoặc batch job, chúng có thể gọi cùng use case thay vì viết lại logic.

## 3. Ba kiến trúc có điểm chung nào?

### 3.1. Hexagonal Architecture

Hexagonal Architecture, còn gọi là Ports and Adapters, mô tả ứng dụng như một lõi có thể tương tác với thế giới bên ngoài qua các **port**. Adapter hiện thực cách kết nối cụ thể: REST, CLI, message listener, JPA, HTTP client hoặc file system.

Hình lục giác chỉ là biểu tượng cho nhiều hướng tương tác; không có nghĩa ứng dụng phải có đúng sáu interface.

~~~text
               REST Controller
                     |
                     v
              Inbound Port
                     |
       +---------------------------+
       |      Application Core     |
       |       Domain Model        |
       |       Use Cases           |
       +---------------------------+
          |          |          |
          v          v          v
       DB Port    Payment Port  Event Port
          |          |          |
          v          v          v
       JPA Adapter HTTP Adapter Broker Adapter
          |          |          |
          v          v          v
       Database   Payment API  Message Broker
~~~

Ý tưởng chính:

- Core định nghĩa những capability cần từ bên ngoài thông qua port.
- Adapter chuyển đổi request/response hoặc message sang mô hình nội bộ.
- Adapter có thể thay đổi mà không buộc domain biết implementation.
- Nhiều adapter có thể cùng gọi một inbound port.

### 3.2. Clean Architecture

Clean Architecture mô tả các vòng/lớp đồng tâm. Dependency source code phải hướng vào trung tâm. Các lớp ngoài biết lớp trong; lớp trong không biết tên framework, database hay UI.

~~~text
+---------------------------------------------+
| Frameworks & Drivers                        |
| Spring MVC, JPA, Kafka, DB, HTTP clients     |
|   +-------------------------------------+   |
|   | Interface Adapters                   |   |
|   | Controllers, Presenters, Gateways    |   |
|   |   +-----------------------------+   |   |
|   |   | Application Business Rules  |   |   |
|   |   | Use Cases                   |   |   |
|   |   |   +---------------------+   |   |   |
|   |   |   | Enterprise Rules    |   |   |   |
|   |   |   | Entities / Domain   |   |   |   |
|   |   |   +---------------------+   |   |   |
|   |   +-----------------------------+   |   |
|   +-------------------------------------+   |
+---------------------------------------------+
       Dependencies point toward the center
~~~

Tên gọi có thể khác nhau giữa các tài liệu và cách triển khai. Điều quan trọng là các business rules không phụ thuộc chi tiết bên ngoài; interface adapters chuyển đổi giữa format bên ngoài và mô hình use case/domain.

### 3.3. Onion Architecture

Onion Architecture đặt domain model ở trung tâm. Các lớp bao quanh chứa domain services, application services, interface và infrastructure. Các phụ thuộc hướng về lõi; domain không biết persistence, UI hoặc framework.

~~~text
+------------------------------------------+
| Infrastructure                           |
| Spring, JPA, REST, Broker, External APIs |
|   +----------------------------------+   |
|   | Application Services              |   |
|   | Use cases / coordination           |   |
|   |   +--------------------------+     |   |
|   |   | Domain Services          |     |   |
|   |   | Domain Model / Entities  |     |   |
|   |   | Value Objects            |     |   |
|   |   +--------------------------+     |   |
|   +----------------------------------+   |
+------------------------------------------+
       Source dependencies point inward
~~~

Onion thường nhấn mạnh domain model và domain behavior ở trung tâm. Application services điều phối use case, còn infrastructure nằm ngoài cùng.

## 4. So sánh Hexagonal, Clean và Onion

| Khía cạnh | Hexagonal | Clean | Onion |
|---|---|---|---|
| Hình ảnh chính | Core, ports và adapters | Vòng/lớp đồng tâm | Các lớp bao quanh domain |
| Điểm nhấn | Giao tiếp qua port, thay adapter | Dependency rule, use case và boundary | Domain model ở trung tâm |
| Core | Application/domain core | Entities và use cases | Domain model/domain services |
| Integration | Port được adapter hiện thực | Interface adapters/gateways | Interface/repository ở vòng trong, implementation bên ngoài |
| Framework | Adapter/driver bên ngoài | Frameworks & drivers ở ngoài cùng | Infrastructure ở ngoài cùng |
| Mục tiêu | Core không phụ thuộc giao thức cụ thể | Business rules không phụ thuộc chi tiết | Domain không phụ thuộc infrastructure |
| Dùng chung | Dependency inversion, testability, separation | Dependency inversion, testability, separation | Dependency inversion, testability, separation |

Không có quy tắc bắt buộc phải chọn một trong ba và cấm hai mô hình còn lại. Một service có thể dùng port/adapter theo Hexagonal, tổ chức package theo lớp Clean và đặt domain ở trung tâm theo tư tưởng Onion.

**Điều cần tránh là trộn tên gọi mà không có dependency rule rõ ràng.** Nếu Domain import Spring Data JPA, hoặc use case phụ thuộc trực tiếp RestClient, service vẫn bị coupling dù package có tên domain/application/infrastructure.

## 5. Dependency Rule: nguyên tắc quan trọng nhất

Quy tắc cốt lõi: **source code dependency hướng từ ngoài vào trong**.

- Controller biết use case/inbound port.
- Use case biết domain model và outbound port.
- Domain không biết Controller, JPA, Spring, Kafka hay HTTP.
- Persistence adapter biết domain/application port để cung cấp implementation.
- HTTP adapter biết outbound port để gọi external system.
- Framework được sử dụng ở composition root để nối các thành phần.

~~~text
Outer layer ---> Inner layer

REST Adapter ---> Application Port
JPA Adapter  ---> Repository Port
HTTP Adapter ---> Payment Port

Domain -X-> Spring/JPA/HTTP/Kafka
~~~

Mũi tên thể hiện hướng phụ thuộc source code. Luồng dữ liệu runtime có thể đi qua lại: use case gọi outbound port và adapter thực hiện lời gọi ra ngoài. Điều đó không làm thay đổi dependency source code.

### 5.1. Dependency Inversion Principle

Dependency Inversion Principle (DIP) nói rằng module cấp cao không nên phụ thuộc trực tiếp module cấp thấp; cả hai nên phụ thuộc abstraction. Abstraction không nên phụ thuộc chi tiết; chi tiết nên phụ thuộc abstraction.

Trong ví dụ:

- Order use case cần kiểm tra hoặc giữ hàng.
- Nó định nghĩa InventoryPort với phương thức cần thiết.
- HTTP adapter hiện thực port bằng cách gọi Inventory Service.
- Test có thể thay adapter bằng fake implementation.

Order không cần biết HTTP client, URL, header, serialization hoặc Spring Cloud.

### 5.2. Không phải cứ tạo interface là áp dụng DIP

Nếu interface chỉ lặp lại một class implementation và không tạo ranh giới có ý nghĩa, nó có thể tăng boilerplate. Port nên thể hiện nhu cầu của application/domain và được đặt ở phía sở hữu nhu cầu đó. Adapter là chi tiết triển khai.

## 6. Ví dụ xuyên suốt: Order Service

Giả sử Order Service có use case PlaceOrder:

1. Nhận yêu cầu tạo đơn.
2. Xác thực dữ liệu và tính tổng theo snapshot giá đáng tin cậy.
3. Lưu order PENDING.
4. Gửi yêu cầu giữ hàng đến Inventory.
5. Yêu cầu Payment authorization.
6. Xác nhận hoặc hủy đơn theo kết quả.
7. Phát event cho các consumer.

Để tập trung vào kiến trúc bên trong service, ví dụ này mô tả Order Service như một ứng dụng riêng. Inventory và Payment vẫn là các service độc lập, có database và contract riêng. Order không truy cập database của chúng.

### 6.1. Package structure

~~~text
order-service/
  src/main/java/com/example/order/
    OrderApplication.java

    domain/
      model/
        Order.java
        OrderId.java
        OrderLine.java
        Money.java
        OrderStatus.java
      service/
        OrderPricingPolicy.java
      event/
        OrderPlaced.java

    application/
      port/
        in/
          PlaceOrderUseCase.java
          GetOrderUseCase.java
        out/
          OrderRepository.java
          InventoryPort.java
          PaymentPort.java
          OrderEventPublisher.java
      command/
        PlaceOrderCommand.java
      result/
        PlaceOrderResult.java
      service/
        PlaceOrderService.java

    adapter/
      in/
        web/
          OrderController.java
          PlaceOrderRequest.java
          OrderResponse.java
        messaging/
          OrderCommandListener.java
      out/
        persistence/
          JpaOrderRepositoryAdapter.java
          OrderJpaEntity.java
          SpringDataOrderRepository.java
        inventory/
          InventoryHttpAdapter.java
        payment/
          PaymentHttpAdapter.java
        messaging/
          OutboxOrderEventPublisher.java

    config/
      OrderConfiguration.java
~~~

Cấu trúc này thể hiện Hexagonal khá rõ:

- adapter/in là inbound adapters.
- application/port/in là use cases mà bên ngoài gọi.
- application/port/out là capability mà application cần.
- adapter/out là outbound adapters.
- domain chứa model và business rules.

Có thể đổi tên package thành core, usecase, infrastructure hoặc theo convention của dự án. Đừng tạo quá nhiều package rỗng chỉ để khớp hình vẽ.

## 7. Domain model thuần Java

Domain model chứa quy tắc nghiệp vụ và invariant. Ví dụ:

~~~java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
~~~

~~~java
public record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Order ID is required");
        }
    }
}
~~~

~~~java
public record Money(long amountMinor, String currency) {
    public Money {
        if (amountMinor < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Currency is required");
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(
            Math.addExact(amountMinor, other.amountMinor),
            currency
        );
    }
}
~~~

~~~java
public record OrderLine(
    String sku,
    int quantity,
    Money unitPrice
) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }

    public Money subtotal() {
        return new Money(
            Math.multiplyExact(unitPrice.amountMinor(), quantity),
            unitPrice.currency()
        );
    }
}
~~~

Order aggregate bảo vệ quy tắc của nó:

~~~java
public final class Order {
    private final OrderId id;
    private final String customerId;
    private final List<OrderLine> lines;
    private final Money total;
    private OrderStatus status;

    private Order(
            OrderId id,
            String customerId,
            List<OrderLine> lines,
            Money total,
            OrderStatus status) {
        this.id = id;
        this.customerId = customerId;
        this.lines = List.copyOf(lines);
        this.total = total;
        this.status = status;
    }

    public static Order pending(
            OrderId id,
            String customerId,
            List<OrderLine> lines) {

        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("Customer is required");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Order must contain items");
        }

        Money total = lines.stream()
            .map(OrderLine::subtotal)
            .reduce((left, right) -> left.add(right))
            .orElseThrow();

        return new Order(
            id, customerId, lines, total, OrderStatus.PENDING
        );
    }

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Only pending orders can be confirmed"
            );
        }
        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status == OrderStatus.CONFIRMED) {
            throw new IllegalStateException(
                "Confirmed order requires cancellation workflow"
            );
        }
        if (status == OrderStatus.CANCELLED) {
            return;
        }
        status = OrderStatus.CANCELLED;
    }

    public OrderId id() { return id; }
    public String customerId() { return customerId; }
    public List<OrderLine> lines() { return lines; }
    public Money total() { return total; }
    public OrderStatus status() { return status; }
}
~~~

Đây là domain model minh họa. Ứng dụng thực tế cần quyết định chính sách tiền tệ, snapshot giá, thuế, discount, shipment và transition chi tiết. Domain không import JPA annotation hoặc Spring stereotype.

### 7.1. Vì sao không đặt @Entity trực tiếp vào domain?

Có dự án chọn JPA entity làm domain model để giảm mapping. Đây là một trade-off hợp lệ nếu nhóm chấp nhận framework coupling và thiết kế entity vẫn bảo vệ invariant. Tuy nhiên, nếu mục tiêu là domain độc lập theo Hexagonal/Clean/Onion, nên tách persistence representation khỏi domain model.

Không có một quy tắc bắt buộc cho mọi ứng dụng; điều cần rõ là nhóm đang chấp nhận coupling nào và nó ảnh hưởng khả năng test/refactor ra sao.

## 8. Inbound Port: application use case

Inbound port mô tả hành vi mà application cung cấp cho bên ngoài. REST controller, message listener hoặc scheduled job đều có thể gọi cùng use case.

~~~java
public interface PlaceOrderUseCase {
    PlaceOrderResult execute(PlaceOrderCommand command);
}
~~~

Command là kiểu dữ liệu của application:

~~~java
public record PlaceOrderCommand(
    String customerId,
    List<PlaceOrderLineCommand> lines
) {}

public record PlaceOrderLineCommand(
    String sku,
    int quantity,
    long unitPriceMinor,
    String currency
) {}
~~~

Result cũng thuộc application boundary:

~~~java
public record PlaceOrderResult(
    String orderId,
    String status,
    long totalMinor,
    String currency
) {}
~~~

Command không nhất thiết giống request JSON. Controller chịu trách nhiệm map API DTO thành command; một message listener có thể map event/command khác vào cùng use case. Nhờ đó application không phụ thuộc REST.

### 8.1. Use case không phải controller

Controller xử lý HTTP concerns như path, header, status code, validation format và serialization. Use case xử lý hành vi nghiệp vụ. Nếu controller tự tính tổng, gọi repository và điều phối Payment, ranh giới application bị phá.

## 9. Outbound Port: các capability application cần

Order use case cần lưu order và có thể gọi Inventory/Payment:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    Optional<Order> findByIdempotencyKey(String key);
    void save(Order order);
}
~~~

~~~java
public interface InventoryPort {
    ReservationResult reserve(
        ReserveInventoryRequest request
    );
}
~~~

~~~java
public interface PaymentPort {
    AuthorizationResult authorize(
        AuthorizePaymentRequest request
    );
}
~~~

~~~java
public interface OrderEventPublisher {
    void publish(OrderPlaced event);
}
~~~

Các kiểu ReserveInventoryRequest, AuthorizationResult và event contract phải được định nghĩa rõ trong application/contract boundary. Tránh đưa class của HTTP client hoặc DTO nội bộ của service bên ngoài vào domain.

### 9.1. Port do consumer sở hữu

Order cần capability giữ hàng, nên Order định nghĩa interface theo nhu cầu của nó. Inventory adapter hiện thực interface. Cách này giúp Order không bị ép phụ thuộc vào mô hình object hoặc SDK của Inventory.

Nếu interface được đặt trong shared library do provider kiểm soát và mọi consumer phải nâng version cùng nhau, lợi ích đảo chiều phụ thuộc có thể bị mất.

## 10. Application Service điều phối use case

Ví dụ đơn giản:

~~~java
@Service
public class PlaceOrderService implements PlaceOrderUseCase {
    private final OrderRepository orders;
    private final OrderIdGenerator ids;

    public PlaceOrderService(
            OrderRepository orders,
            OrderIdGenerator ids) {
        this.orders = orders;
        this.ids = ids;
    }

    @Override
    @Transactional
    public PlaceOrderResult execute(PlaceOrderCommand command) {
        Order order = Order.pending(
            ids.next(),
            command.customerId(),
            command.lines().stream()
                .map(line -> new OrderLine(
                    line.sku(),
                    line.quantity(),
                    new Money(
                        line.unitPriceMinor(),
                        line.currency()
                    )
                ))
                .toList()
        );

        orders.save(order);

        return new PlaceOrderResult(
            order.id().value(),
            order.status().name(),
            order.total().amountMinor(),
            order.total().currency()
        );
    }
}
~~~

Ví dụ này chỉ tạo Order trong transaction local. Khi có Inventory/Payment, nên thiết kế workflow và transaction boundary rõ ràng. Không giữ transaction database trong lúc chờ HTTP request đến service khác. Một cách phù hợp là ghi order/saga/outbox cùng nhau rồi dispatch command sau commit, hoặc dùng orchestration bất đồng bộ.

### 10.1. Application service và domain service

Application service điều phối use case: tải aggregate, gọi domain behavior, lưu thay đổi và tương tác qua port. Domain service chứa quy tắc nghiệp vụ không thuộc tự nhiên về một entity/value object cụ thể.

Không đẩy toàn bộ nghiệp vụ vào application service như một script gọi repository liên tục; cũng không đưa orchestration HTTP/broker vào domain service.

## 11. Inbound Adapter: REST Controller

Controller chuyển đổi HTTP request thành application command:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
class OrderController {
    private final PlaceOrderUseCase placeOrder;

    OrderController(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody PlaceOrderRequest request) {

        PlaceOrderResult result = placeOrder.execute(
            new PlaceOrderCommand(
                request.customerId(),
                request.items().stream()
                    .map(item -> new PlaceOrderLineCommand(
                        item.sku(),
                        item.quantity(),
                        item.unitPriceMinor(),
                        item.currency()
                    ))
                    .toList()
            )
        );

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new OrderResponse(
                result.orderId(),
                result.status(),
                result.totalMinor(),
                result.currency()
            ));
    }
}
~~~

Request/response DTO thuộc adapter/web:

~~~java
public record PlaceOrderRequest(
    String customerId,
    List<PlaceOrderItemRequest> items
) {}

public record PlaceOrderItemRequest(
    String sku,
    int quantity,
    long unitPriceMinor,
    String currency
) {}

public record OrderResponse(
    String orderId,
    String status,
    long totalMinor,
    String currency
) {}
~~~

Trong ứng dụng thương mại thật, unit price không nên tin từ client; ví dụ giữ field này để tập trung minh họa mapping. API adapter nên lấy giá đã được xác thực qua Pricing/Catalog capability hoặc nhận snapshot đã được backend ký/xác minh.

### 11.1. Một use case có nhiều inbound adapter

~~~text
REST Controller -------+
Kafka Command Listener -+--> PlaceOrderUseCase
Admin CLI --------------+
Scheduled Job ----------+
~~~

Mỗi adapter có format và authentication riêng, nhưng cùng gọi application behavior. Không tạo một use case mới chỉ vì đầu vào đến từ Kafka thay vì HTTP nếu ý nghĩa nghiệp vụ giống nhau.

## 12. Outbound Adapter: JPA persistence

Domain repository port:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Adapter dùng Spring Data JPA:

~~~java
interface SpringDataOrderRepository
        extends JpaRepository<OrderJpaEntity, String> {
}
~~~

Persistence entity:

~~~java
@Entity
@Table(name = "orders")
class OrderJpaEntity {
    @Id
    private String id;

    private String customerId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    private long totalMinor;

    private String currency;

    protected OrderJpaEntity() {}

    static OrderJpaEntity fromDomain(Order order) {
        OrderJpaEntity entity = new OrderJpaEntity();
        entity.id = order.id().value();
        entity.customerId = order.customerId();
        entity.status = order.status();
        entity.totalMinor = order.total().amountMinor();
        entity.currency = order.total().currency();
        return entity;
    }

    Order toDomain() {
        // Reconstruct the aggregate using persisted state.
        // The real mapper must also load order lines and versions.
        return Order.reconstitute(
            new OrderId(id),
            customerId,
            status,
            new Money(totalMinor, currency)
        );
    }
}
~~~

Adapter:

~~~java
@Repository
class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringDataOrderRepository repository;

    JpaOrderRepositoryAdapter(SpringDataOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return repository.findById(id.value())
            .map(OrderJpaEntity::toDomain);
    }

    @Override
    public void save(Order order) {
        repository.save(OrderJpaEntity.fromDomain(order));
    }
}
~~~

Các đoạn mapping là minh họa; phương thức reconstitute cần được thiết kế trong domain và persistence mapper phải lưu/load toàn bộ aggregate, bao gồm order lines, version và các trường bắt buộc. Không đưa repository Spring Data ra ngoài adapter.

### 12.1. Mapping có phải lúc nào cũng cần?

Mapping giữa domain và persistence tạo thêm code nhưng cho phép thay schema/ORM mà không rò rỉ chi tiết vào domain. Nếu service nhỏ, model đơn giản và team chấp nhận coupling, có thể dùng JPA entity làm domain entity. Cần ghi rõ trade-off và tránh trộn lẫn hai cách tùy tiện trong cùng một aggregate.

## 13. Outbound Adapter: HTTP client tới Inventory

Port:

~~~java
public interface InventoryPort {
    ReservationResult reserve(ReserveInventoryRequest request);
}
~~~

Adapter:

~~~java
@Component
class InventoryHttpAdapter implements InventoryPort {
    private final RestClient client;

    InventoryHttpAdapter(RestClient.Builder builder) {
        this.client = builder
            .baseUrl("http://inventory-service")
            .build();
    }

    @Override
    public ReservationResult reserve(ReserveInventoryRequest request) {
        return client.post()
            .uri("/api/v1/reservations")
            .header("Idempotency-Key", request.idempotencyKey())
            .body(request)
            .retrieve()
            .body(ReservationResult.class);
    }
}
~~~

Trong production cần cấu hình connect/read/response timeout, authentication, error mapping, tracing, retry có giới hạn và idempotency. Adapter chịu trách nhiệm chuyển lỗi HTTP thành kết quả/application exception ổn định. Domain không nên xử lý RestClientResponseException.

Base URL phải đến từ cấu hình tin cậy/service discovery, không lấy trực tiếp từ dữ liệu client.

## 14. Cấu hình Spring và composition root

Spring dependency injection nối port với adapter:

~~~java
@Configuration
class OrderConfiguration {
    @Bean
    PlaceOrderUseCase placeOrderUseCase(
            OrderRepository orders,
            OrderIdGenerator ids) {
        return new PlaceOrderService(orders, ids);
    }
}
~~~

Nếu adapter được đánh dấu @Component/@Repository, Spring có thể tự tạo bean. Có thể dùng constructor injection và bean configuration rõ ràng. **Composition root** là nơi framework tạo object graph; domain không cần tự tìm dependency từ ApplicationContext.

Không dùng static service locator hoặc gọi ApplicationContext.getBean() bên trong domain. Điều đó che giấu dependency và làm test khó hơn.

### 14.1. Package dependency và module enforcement

Với service lớn, có thể dùng Java modules, Gradle modules hoặc ArchUnit để kiểm tra:

- domain không import adapter/infrastructure.
- application không import web/JPA/broker client.
- adapter có thể import application/domain.
- dependency giữa bounded context đi qua contract được công bố.

Kiểm tra tự động hữu ích khi nhiều team cùng sửa code và package convention có nguy cơ bị phá dần.

## 15. Hexagonal, Clean và Onion khi áp dụng vào Spring Boot

Có thể ánh xạ các khái niệm như sau:

| Khái niệm | Package ví dụ | Công nghệ điển hình |
|---|---|---|
| Domain/Entities | domain.model | Java thuần |
| Domain services | domain.service | Java thuần |
| Application/use cases | application.service | Java, có thể dùng Spring ở boundary |
| Inbound ports | application.port.in | Interface + command/result |
| Outbound ports | application.port.out | Interface |
| Inbound adapters | adapter.in.web/messaging | Spring MVC, Kafka listener |
| Outbound adapters | adapter.out.persistence/http | Spring Data JPA, RestClient |
| Configuration | config | Spring DI/composition root |

Đây là cách tổ chức tương thích cả ba tư tưởng, không phải mapping duy nhất. Clean Architecture có thể gọi lớp application là use cases và interface adapters; Onion có thể gọi application services/domain services theo cách khác; Hexagonal gọi port/adapter.

## 16. Transaction boundary: đặt ở đâu?

Transaction nên gắn với **use case và dữ liệu do service sở hữu**. Ví dụ PlaceOrder lưu order và outbox trong cùng Order DB transaction. Khi gọi service khác, không nên giữ transaction đó mở trong lúc chờ network.

~~~text
Order Service transaction:
  save Order
  save Saga state
  save Outbox command
  COMMIT
       |
       v
Outbox relay publishes command
       |
       v
Inventory Service transaction
  reserve stock
  save Reservation
  save Outbox event
  COMMIT
~~~

Mỗi service giữ transaction cục bộ. Workflow nhiều service có thể dùng saga và compensation. Application use case có thể được đánh dấu @Transactional ở lớp application service; annotation là framework concern nhưng được dùng tại boundary để định nghĩa transaction scope.

### 16.1. Không để transaction lan qua port

Một port có thể gọi service ngoài nhưng không nên làm transaction database của Order bao trùm một network call lâu. Timeout không rollback side effect đã xảy ra ở Inventory/Payment. Dùng outbox, idempotency và saga để xử lý kết quả phân tán.

## 17. Domain events và integration events

Domain event thể hiện điều đã xảy ra trong domain, ví dụ OrderConfirmed. Integration event là contract được công bố ra ngoài context/service. Chúng có thể có nội dung gần nhau nhưng không nhất thiết là cùng một class.

~~~text
Domain action
    |
    v
Order domain event
    |
    v
Application maps to integration event
    |
    v
Outbox / Broker
~~~

Giữ domain event không phụ thuộc Kafka headers hoặc schema registry. Adapter/publisher chuyển đổi sang integration contract. Điều này giúp domain không cần biết broker, partition hoặc serialization format.

### 17.1. Outbox trong kiến trúc hướng port/adapter

Application use case có thể phụ thuộc OutboxPort hoặc một abstraction tương tự; persistence adapter ghi outbox cùng transaction với aggregate. Publisher adapter gửi message đến broker. Chi tiết CDC/polling nằm ngoài domain.

## 18. Testing theo ranh giới kiến trúc

Một lợi ích lớn của Hexagonal/Clean/Onion là kiểm thử domain và use case mà không cần khởi động toàn bộ Spring context.

### 18.1. Domain unit test

~~~java
@Test
void confirmsOnlyPendingOrder() {
    Order order = Order.pending(
        new OrderId("order-1"),
        "customer-1",
        List.of(
            new OrderLine(
                "SKU-1",
                2,
                new Money(1000, "VND")
            )
        )
    );

    order.confirm();

    assertEquals(OrderStatus.CONFIRMED, order.status());
}
~~~

~~~java
@Test
void rejectsEmptyOrder() {
    assertThrows(
        IllegalArgumentException.class,
        () -> Order.pending(
            new OrderId("order-2"),
            "customer-1",
            List.of()
        )
    );
}
~~~

Test domain không cần Spring, database hoặc broker. Đây là dấu hiệu tốt cho thấy business rules có thể được kiểm tra độc lập.

### 18.2. Application use case test với fake port

~~~java
final class FakeOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(orders.get(id.value()));
    }

    @Override
    public void save(Order order) {
        orders.put(order.id().value(), order);
    }
}
~~~

Một fake InventoryPort có thể trả reservation thành công hoặc từ chối. Test use case kiểm tra Order xử lý đúng kết quả mà không cần chạy service Inventory thật.

Không nên dùng mock cho mọi object chỉ để tăng số lượng test. Fake phù hợp khi cần mô phỏng contract; integration test phải xác nhận adapter thật hoạt động.

### 18.3. Adapter integration test

- JPA adapter với Testcontainers/database tương thích.
- REST adapter với MockWebServer/WireMock hoặc test server phù hợp.
- Kafka adapter với broker test container hoặc embedded test infrastructure phù hợp.
- JSON/schema serialization tests.
- Security/authentication tests ở boundary.

### 18.4. Architecture tests

Có thể dùng ArchUnit để bảo vệ dependency direction:

~~~java
@AnalyzeClasses(packages = "com.example.order")
class ArchitectureTest {

    @ArchTest
    static final ArchRule domainMustNotDependOnSpring =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "org.springframework..",
                "jakarta.persistence.."
            );

    @ArchTest
    static final ArchRule domainMustNotDependOnAdapters =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("..adapter..");
}
~~~

Cú pháp và imports cần điều chỉnh theo phiên bản ArchUnit/project. Có thể bổ sung rule cho application không phụ thuộc adapter, và adapter không truy cập trực tiếp package nội bộ của service khác.

## 19. Test một workflow nhiều service

Unit test domain không thể chứng minh toàn bộ luồng Order–Inventory–Payment. Cần các tầng test:

1. Domain tests: invariant của Order/Reservation/Payment.
2. Use case tests: điều phối theo kết quả port.
3. Adapter tests: mapping HTTP/DB/message.
4. Contract tests: producer/consumer tương thích.
5. Integration tests: các service và broker hoạt động cùng nhau.
6. Workflow tests: saga hoàn tất, compensation, duplicate, timeout.
7. Resilience tests: dependency chậm/mất, restart, backlog.

Một số case quan trọng:

- Inventory từ chối thì không gọi Payment.
- Payment decline thì release reservation.
- Payment timeout nhưng gateway đã authorize thì reconciliation tìm ra kết quả.
- Outbox publisher restart vẫn gửi event.
- Duplicate event không tạo side effect trùng.
- Event cũ không làm trạng thái Order lùi.
- Database adapter rollback đúng khi invariant thất bại.

## 20. Khi nào nên dùng mỗi kiến trúc?

### 20.1. Hexagonal phù hợp khi

- Service có nhiều cách vào: REST, message, CLI, scheduled job.
- Service có nhiều dependency ra: DB, broker, external APIs.
- Cần thay adapter hoặc fake dependency trong test.
- Ranh giới giữa core và công nghệ bên ngoài cần được nhìn rõ.

### 20.2. Clean Architecture phù hợp khi

- Use case phức tạp, cần phân biệt enterprise rules và application rules.
- Nhiều adapter cần gọi cùng use case.
- Team cần dependency policy rõ để bảo vệ business logic.
- Cần cấu trúc dễ hiểu cho dự án lớn hoặc nhiều nhóm.

### 20.3. Onion Architecture phù hợp khi

- Domain model và business invariants là phần có giá trị/độ phức tạp cao.
- Cần domain-centric design và giữ infrastructure ngoài cùng.
- Domain service, aggregate và value objects có vai trò rõ.
- Muốn thay persistence/framework mà không ảnh hưởng domain core.

### 20.4. Có thể kết hợp

Một service có thể dùng:

- Onion để đặt domain model ở trung tâm.
- Clean để diễn đạt các lớp và dependency rule.
- Hexagonal để định nghĩa port/adapter tại các điểm giao tiếp.

Không cần tạo ba bộ lớp riêng cho ba tên gọi. Một cấu trúc nhất quán với domain/application/ports/adapters/infrastructure thường đủ để thể hiện cả ba.

## 21. Khi nào không cần nhiều lớp abstraction?

Không phải mọi CRUD service đều cần nhiều interface, mapper, factory và package.

Nếu service chỉ có một use case đơn giản, một database và ít quy tắc, có thể dùng cấu trúc gọn:

~~~text
product/
  ProductController
  ProductService
  ProductRepository
  ProductEntity
~~~

Khi domain bắt đầu có quy tắc phức tạp, nhiều inbound/outbound adapters hoặc yêu cầu test độc lập, có thể tiến hóa sang:

~~~text
product/
  domain/
  application/
  adapter/
  config/
~~~

Đừng tạo port cho mọi class chỉ để theo hình mẫu. Abstraction nên bảo vệ một ranh giới có lý do: một external dependency, một capability, một contract hoặc một điểm biến đổi có khả năng thay đổi.

## 22. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Domain import Spring/JPA | Framework thay đổi kéo domain theo | Giữ domain thuần nếu cần độc lập |
| Controller chứa nghiệp vụ | Logic khó tái sử dụng từ message/job | Gọi inbound use case |
| Application service chỉ gọi repository không có use case rõ | Thêm lớp nhưng không tăng boundary | Đặt tên theo hành vi nghiệp vụ |
| Interface cho mọi class | Boilerplate và indirection | Chỉ tạo port tại boundary có ý nghĩa |
| Domain model chỉ có getter/setter | Business rules trôi vào service | Đưa invariant/behavior về aggregate |
| JPA entity lộ ra API | Persistence schema thành public contract | DTO và mapping ở adapter |
| Use case phụ thuộc RestClient | Application biết chi tiết HTTP | Định nghĩa outbound port |
| Adapter chứa business policy | Logic bị khóa vào framework | Chuyển quy tắc về domain/application |
| Shared repository giữa service | Phá data ownership | Mỗi service sở hữu persistence riêng |
| Dùng ApplicationContext như service locator | Dependency ẩn, test khó | Constructor injection |
| Transaction bao trùm network call | Lock lâu, không rollback side effect | Local transaction + saga/outbox |
| Tạo ba bộ layer cho ba kiến trúc | Lặp code và khái niệm | Kết hợp nguyên tắc, một cấu trúc |
| Mapper quá phức tạp cho CRUD nhỏ | Chi phí bảo trì không tương xứng | Chọn mức abstraction theo độ phức tạp |
| Test chỉ bằng mock | Adapter thật có thể sai contract | Bổ sung integration/contract tests |

## 23. Refactor service hiện có theo từng bước

Không cần rewrite toàn bộ để áp dụng dependency direction.

### Bước 1 — Chọn một use case

Ví dụ PlaceOrder hoặc ReserveInventory. Đừng di chuyển tất cả package cùng lúc.

### Bước 2 — Xác định domain rules

Tách quy tắc như quantity phải dương, chỉ confirm khi PENDING, tổng tiền cùng currency vào domain model.

### Bước 3 — Tách request/response DTO

Không dùng trực tiếp JPA entity làm API contract. Đặt mapping trong controller/adapter.

### Bước 4 — Đưa orchestration vào application use case

Controller chỉ parse/auth/validate input ở boundary rồi gọi use case. Use case điều phối domain và các port.

### Bước 5 — Tách outbound dependency

Nếu use case gọi RestClient hoặc Spring Data trực tiếp, định nghĩa port phù hợp rồi chuyển implementation sang adapter.

### Bước 6 — Đặt transaction boundary

Giữ transaction cho dữ liệu của service. Không giữ DB transaction khi gọi service ngoài.

### Bước 7 — Bổ sung test

Bắt đầu với domain test và use case test. Sau đó thêm adapter integration tests và contract tests.

### Bước 8 — Kiểm tra dependency

Dùng code review hoặc ArchUnit để chặn import từ domain/application ra adapter/infrastructure.

### Bước 9 — Chuyển các entry point khác

Message listener, scheduled job hoặc admin endpoint nên gọi cùng use case nếu hành vi nghiệp vụ giống nhau.

### Bước 10 — Tiến hóa khi có bằng chứng

Nếu một adapter trở nên phức tạp, chia module riêng. Nếu service quá đơn giản, giữ cấu trúc gọn. Kiến trúc cần phản ánh nhu cầu hiện tại và hướng thay đổi hợp lý.

## 24. Quan hệ giữa kiến trúc bên trong service và Microservices

Hexagonal/Clean/Onion giải quyết **cách tổ chức bên trong một service**. Chúng không tự quyết định:

- Nên chia bao nhiêu Microservice.
- Bounded context nào thuộc service nào.
- Service có database riêng hay không.
- Giao tiếp nên dùng REST, gRPC hay event.
- Saga, consistency hoặc data ownership toàn hệ thống.
- Cách deploy, autoscale hoặc phân vùng hạ tầng.

Các quyết định đó thuộc system architecture, domain design và vận hành. Tuy nhiên, một service có core độc lập sẽ dễ thực hiện contract, test và thay đổi adapter hơn.

~~~text
Microservice A                  Microservice B
+--------------------+          +--------------------+
| Domain A           |          | Domain B           |
| Application A     |--API---->| Application B     |
| Ports/Adapters A   |          | Ports/Adapters B   |
| Database A         |          | Database B         |
+--------------------+          +--------------------+
~~~

Mỗi service tự sở hữu core và adapter của mình. Không dùng chung domain entity hoặc repository nội bộ xuyên service. Contract giữa service là interface công khai; domain model bên trong có thể khác nhau.

## 25. Ví dụ áp dụng cho Inventory Service

Inventory có invariant quan trọng: số lượng khả dụng không được âm. Domain model có thể định nghĩa hành vi reserve:

~~~java
public final class Stock {
    private final String sku;
    private int available;
    private int reserved;

    public Stock(String sku, int available, int reserved) {
        if (available < 0 || reserved < 0) {
            throw new IllegalArgumentException("Stock cannot be negative");
        }
        this.sku = sku;
        this.available = available;
        this.reserved = reserved;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (available < quantity) {
            throw new InsufficientStockException(sku);
        }
        available -= quantity;
        reserved += quantity;
    }

    public void release(int quantity) {
        if (quantity <= 0 || reserved < quantity) {
            throw new IllegalStateException("Invalid release quantity");
        }
        reserved -= quantity;
        available += quantity;
    }
}
~~~

Use case:

~~~java
public interface ReserveStockUseCase {
    ReservationResult reserve(ReserveStockCommand command);
}
~~~

Outbound repository port:

~~~java
public interface StockRepository {
    Stock loadForUpdate(String sku);
    void save(Stock stock);
}
~~~

Application service:

~~~java
@Service
class ReserveStockService implements ReserveStockUseCase {
    private final StockRepository stocks;

    ReserveStockService(StockRepository stocks) {
        this.stocks = stocks;
    }

    @Override
    @Transactional
    public ReservationResult reserve(ReserveStockCommand command) {
        Stock stock = stocks.loadForUpdate(command.sku());
        stock.reserve(command.quantity());
        stocks.save(stock);

        return new ReservationResult(
            command.reservationId(),
            command.sku(),
            command.quantity(),
            "RESERVED"
        );
    }
}
~~~

Code trên minh họa dependency structure. Repository adapter phải thực hiện locking/optimistic versioning phù hợp với database để hai request đồng thời không cùng đọc một available quantity rồi ghi đè. Domain invariant cần được bảo vệ cả ở mức transaction/persistence concurrency; chỉ có Java method không tự giải quyết race condition phân tán.

## 26. Ví dụ áp dụng cho Payment Service

Payment Service có thể dùng:

- Domain: Payment, Money, PaymentStatus, Authorization, Refund.
- Application: AuthorizePayment, CapturePayment, VoidAuthorization, RefundPayment.
- Inbound adapters: REST controller, message listener.
- Outbound ports: PaymentRepository, PaymentGateway, EventPublisher.
- Outbound adapters: JPA, gateway HTTP/SDK, outbox/broker.

PaymentGateway port:

~~~java
public interface PaymentGateway {
    GatewayAuthorization authorize(AuthorizationRequest request);
    GatewayResult capture(String reference, Money amount);
    GatewayResult voidAuthorization(String reference);
    GatewayResult refund(String reference, Money amount);
}
~~~

Application use case phụ thuộc port này, không biết provider nào được dùng. Adapter xử lý authentication, idempotency headers, timeout, response mapping và lỗi provider.

Nếu gateway timeout sau khi đã xử lý authorization, domain/application phải biểu diễn trạng thái UNKNOWN và reconciliation; không biến mọi timeout thành DECLINED. Đây là business behavior, không phải chi tiết HTTP.

## 27. Clean boundary với Spring Security

Authentication và authorization thường diễn ra ở adapter/boundary:

- Spring Security filter xác thực token.
- Adapter lấy principal/claims cần thiết.
- Application nhận actor/tenant context rõ ràng.
- Domain áp dụng quy tắc nghiệp vụ liên quan quyền nếu đó là invariant của domain.

Không để domain đọc SecurityContextHolder hoặc lấy username từ thread-local. Điều đó khiến domain phụ thuộc Spring Security và khó test. Có thể truyền actorId/tenantId như một input rõ ràng của use case.

Cũng không đưa mọi quyết định authorization vào controller; một số quy tắc quyền sở hữu tài nguyên cần được kiểm tra trong application/domain để không bị bỏ qua khi use case được gọi từ message listener hoặc batch job.

## 28. Validation ở lớp nào?

Phân biệt ba loại:

| Loại validation | Ví dụ | Nơi phù hợp |
|---|---|---|
| Transport/input shape | JSON thiếu field, format sai | API adapter |
| Application precondition | Caller có quyền thực hiện use case, idempotency key hợp lệ | Application/boundary |
| Domain invariant | Quantity phải dương, order không confirm hai lần | Domain |

Không đặt tất cả validation vào Bean Validation annotation của request DTO rồi nghĩ domain luôn an toàn. Use case có thể được gọi từ nhiều inbound adapter; domain phải bảo vệ invariant quan trọng của nó.

## 29. Cấu hình và framework leakage

Một số chi tiết thường rò vào core:

- Spring Page/Pageable.
- HttpStatus/ResponseEntity.
- JPA Page/EntityManager.
- Kafka ConsumerRecord.
- Provider-specific SDK response.
- Framework exception.
- Servlet request/session.
- ApplicationContext hoặc static utility giữ state.

Nếu use case nhận Pageable của Spring Data, core đã biết framework. Có thể định nghĩa PageRequest/PageResult thuần Java và adapter map sang Spring Data. Không cần tránh mọi class thư viện bằng mọi giá; chỉ giữ dependency ngoài ở ranh giới có lý do.

### 29.1. Composition root là nơi framework được biết đến

Spring Boot main application và configuration có thể biết toàn bộ adapter/bean. Đó là vai trò của composition root: tạo object graph. Core không nên tự khởi tạo adapter hoặc truy cập framework container.

## 30. Lựa chọn giữa REST và Messaging không phụ thuộc Hexagonal

Hexagonal cho phép inbound/outbound adapter dùng bất kỳ giao thức nào. Quyết định REST/gRPC/message broker cần dựa trên semantics:

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Query cần phản hồi ngay | REST/gRPC |
| Command cần kết quả tức thì | REST/gRPC với timeout và idempotency |
| Workflow dài hoặc eventual consistency | Messaging |
| Fan-out nhiều consumer | Event broker |
| Streaming liên tục | Streaming protocol/broker |
| Scheduled operation | Scheduler adapter gọi use case |

Dù chọn giao thức nào, application port vẫn thể hiện capability nghiệp vụ; adapter thực hiện giao thức. Không để REST DTO trở thành domain model chỉ vì REST là inbound adapter đầu tiên.

## 31. Những câu hỏi thiết kế trước khi tạo port

Trước khi tạo interface, hãy hỏi:

1. Đây có phải boundary giữa core và một external technology không?
2. Ai sở hữu nhu cầu này: application hay provider?
3. Có nhiều implementation hoặc test fake có giá trị không?
4. Contract có thể diễn đạt bằng ngôn ngữ nghiệp vụ không?
5. Interface có làm lộ DTO/framework của adapter không?
6. Thay implementation có thể giữ use case không đổi không?
7. Port có quá rộng, chứa nhiều capability không liên quan không?
8. Interface có chỉ lặp lại một method mà không tạo boundary có ý nghĩa không?

Port tốt thường nhỏ và biểu đạt đúng nhu cầu. Ví dụ Order cần reserve inventory, không cần một InventoryService interface có 40 method cho toàn bộ chức năng của Inventory.

## 32. Checklist áp dụng trong một Microservice

### Domain và application

- [ ] Domain model chứa invariant và behavior quan trọng.
- [ ] Domain không phụ thuộc Spring, JPA, HTTP hoặc broker.
- [ ] Application use case được đặt tên theo hành vi nghiệp vụ.
- [ ] Application điều phối domain và các port.
- [ ] Command/result không phụ thuộc transport DTO.
- [ ] Quy tắc nghiệp vụ không bị nhúng vào controller/adapter.

### Ports và adapters

- [ ] Inbound port thể hiện capability của service.
- [ ] Outbound port thể hiện nhu cầu của application/domain.
- [ ] Port do phía sử dụng capability định nghĩa khi phù hợp.
- [ ] Adapter thực hiện mapping và xử lý protocol/framework.
- [ ] Adapter không chứa business policy cốt lõi.
- [ ] Có thể thay adapter bằng fake/test implementation ở use case test.

### Persistence và giao dịch

- [ ] Service sở hữu database và repository của nó.
- [ ] Persistence entity không vô tình trở thành public API.
- [ ] Mapping domain/persistence có quy ước rõ.
- [ ] Transaction nằm ở use case/local boundary hợp lý.
- [ ] Không giữ DB transaction trong lúc chờ network call.
- [ ] Concurrency control bảo vệ invariant khi có nhiều request đồng thời.

### Spring và vận hành

- [ ] Spring DI/composition root nối các adapter và use case.
- [ ] Không dùng service locator trong domain.
- [ ] Security context được chuyển thành input rõ ràng.
- [ ] Timeout, retry, idempotency và error mapping nằm ở boundary phù hợp.
- [ ] Logs, metrics, tracing và health checks tuân thủ platform conventions.
- [ ] Có runbook, versioning và migration policy.

### Kiểm thử và bảo vệ kiến trúc

- [ ] Domain có unit tests không cần Spring context.
- [ ] Application có tests bằng fake ports.
- [ ] Persistence/HTTP/broker adapters có integration tests.
- [ ] API/event contract có compatibility tests.
- [ ] Có workflow tests cho các lỗi phân tán.
- [ ] Architecture tests bảo vệ dependency direction khi phù hợp.

## 33. Bài tập thực hành A: phân loại lớp

Với Order Service, phân loại các thành phần sau:

- Order aggregate.
- PlaceOrderUseCase.
- PlaceOrderRequest.
- OrderController.
- OrderRepository port.
- JpaOrderRepositoryAdapter.
- PaymentGateway port.
- ExternalPaymentGatewayAdapter.
- SpringDataOrderRepository.
- OrderConfirmed integration event.
- Kafka listener.

Giải thích mỗi thành phần thuộc domain, application, inbound adapter, outbound adapter hay contract boundary. Nêu lý do và hướng dependency.

## 34. Bài tập thực hành B: refactor một service bị coupling

Cho một OrderService hiện tại:

~~~java
@Service
class OrderService {
    private final OrderJpaRepository repository;
    private final RestClient paymentClient;

    OrderService(
            OrderJpaRepository repository,
            RestClient paymentClient) {
        this.repository = repository;
        this.paymentClient = paymentClient;
    }

    @Transactional
    Order create(OrderEntity entity) {
        repository.save(entity);
        paymentClient.post()
            .uri("/payments")
            .body(entity)
            .retrieve()
            .toBodilessEntity();
        return entity.toDomain();
    }
}
~~~

Nhiệm vụ:

1. Xác định framework/database/network coupling.
2. Định nghĩa PlaceOrderUseCase và command/result.
3. Tạo domain Order với invariant phù hợp.
4. Định nghĩa OrderRepository và PaymentPort.
5. Chuyển JPA/HTTP thành adapters.
6. Quyết định transaction boundary và cách tránh giữ transaction khi gọi Payment.
7. Thêm outbox/saga nếu workflow có side effect phân tán.
8. Viết unit tests cho domain/use case và adapter integration tests.
9. Thêm architecture rule để ngăn domain import infrastructure.

Đoạn code ban đầu chỉ là tình huống minh họa, không phải một implementation đầy đủ.

## 35. Bài tập thực hành C: chọn kiến trúc cho service nhỏ

Một service chỉ có ba endpoint CRUD, một bảng database và ít business rules. Team đề xuất triển khai đủ 6 layer, 15 port và 20 mapper.

Hãy đánh giá:

- Boundary nào thật sự cần abstraction?
- Có cần domain model độc lập hay entity đơn giản đủ dùng?
- Adapter nào có khả năng thay đổi?
- Test nào có giá trị nhất?
- Chi phí bảo trì của các interface có vượt lợi ích không?
- Có thể bắt đầu gọn rồi tiến hóa khi domain phức tạp không?

Không có điểm cộng tự động cho số lớp hoặc số interface. Chất lượng nằm ở việc boundary giúp thay đổi và kiểm thử dễ hơn.

## 36. Kết luận

Hexagonal, Clean và Onion Architecture đều hướng tới việc **bảo vệ domain/application khỏi các chi tiết bên ngoài**. Hexagonal làm rõ ports và adapters; Clean nhấn mạnh dependency rule và các lớp use case/interface adapters/frameworks; Onion đặt domain model ở trung tâm với các lớp phụ thuộc hướng vào trong. Một Microservice có thể kết hợp những tư tưởng này bằng cấu trúc domain, application, inbound/outbound ports, adapters và infrastructure nhất quán.

Trong Java/Spring, Controller, Spring Data JPA, RestClient và Kafka listener nên là adapter. Use case điều phối hành vi ứng dụng. Domain giữ invariant và business rules. Outbound port mô tả capability mà application cần; adapter thực hiện kết nối đến database hoặc service ngoài. Spring DI nối các thành phần ở composition root.

Không cần tạo abstraction cho mọi class. Chỉ xây boundary khi nó bảo vệ một phần nghiệp vụ khỏi thay đổi bên ngoài, giúp test có ý nghĩa hoặc cho phép thay implementation. Khi dependency direction rõ, từng Microservice có thể tiến hóa nội bộ độc lập hơn, trong khi contract giữa các service vẫn ổn định và dễ kiểm chứng.