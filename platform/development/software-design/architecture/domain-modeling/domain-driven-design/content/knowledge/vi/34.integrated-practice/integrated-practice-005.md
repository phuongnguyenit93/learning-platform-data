# Triển khai ca sử dụng đặt hàng bằng Java với cổng repository

Ca sử dụng đặt hàng là một bài thực hành tốt để kết nối các khái niệm cốt lõi của Domain-Driven Design (DDD). Người mua gửi yêu cầu; ứng dụng lấy thông tin sản phẩm và giá; mô hình miền tạo một Order hợp lệ; repository lưu Aggregate; sau khi transaction commit, sự kiện OrderPlaced có thể được chuyển đến các context liên quan.

Bài thực hành này xây dựng luồng đó bằng Java theo kiến trúc phân lớp/hexagonal. Trọng tâm là Repository Port: domain định nghĩa hợp đồng lưu và khôi phục Aggregate, còn infrastructure cung cấp adapter dùng JPA. Application Service điều phối use case và phụ thuộc vào các port, không phụ thuộc vào bảng hoặc framework persistence.

Ví dụ sử dụng modular monolith với Sales và Catalog là hai module trong cùng ứng dụng. Catalog cung cấp snapshot sản phẩm qua một query port. Sales sở hữu Order Aggregate và repository của nó. Chính sách thuế, tồn kho, thanh toán và vận chuyển được giữ ngoài phạm vi cốt lõi để bài tập tập trung vào việc đặt hàng và lưu Aggregate. Khi áp dụng vào hệ thống thật, các chính sách này cần được bổ sung theo quy tắc đã xác nhận với chuyên gia nghiệp vụ.

## 1. Mục tiêu và phạm vi use case

Use case cần đạt hành vi sau:

1. Người mua gửi danh sách sản phẩm và số lượng muốn mua.
2. Ứng dụng lấy snapshot thông tin bán của từng sản phẩm từ Catalog.
3. Hệ thống từ chối nếu sản phẩm không tồn tại hoặc không được phép bán.
4. Domain tạo Order với các dòng hàng hợp lệ và tổng tiền được tính từ snapshot giá.
5. Order được lưu qua OrderRepository.
6. Sự kiện OrderPlaced được ghi vào outbox trong cùng transaction với Order.
7. Ứng dụng trả về OrderId và tổng tiền đã ghi nhận.

Các giả định nghiệp vụ của ví dụ:

- Một Order phải có ít nhất một dòng hàng.
- Mỗi dòng có ProductId, tên sản phẩm tại thời điểm đặt, số lượng dương và đơn giá không âm.
- Các dòng trong một Order phải dùng cùng loại tiền.
- Đơn giá được chụp tại thời điểm đặt hàng; thay đổi giá Catalog sau đó không làm thay đổi Order đã tạo.
- Order mới được tạo ở trạng thái PLACED.
- Sales sở hữu Order và quyết định tạo Order.
- Catalog sở hữu Product và chính sách sản phẩm có được phép bán hay không.

Đây là các giả định để triển khai bài học, không phải quy tắc đúng cho mọi hệ thống thương mại. Hãy xác nhận chúng trước khi dùng trong sản phẩm thật.

## 2. Xác định ranh giới và trách nhiệm

DDD không bắt đầu bằng việc tạo một lớp Order. Ta cần biết ai sở hữu khái niệm và quyết định.

| Thành phần | Trách nhiệm | Owner |
|---|---|---|
| Product | Thông tin sản phẩm và khả năng bán | Catalog |
| Product selling snapshot | Dữ liệu sản phẩm cần tại thời điểm đặt | Catalog công bố qua query port |
| Order | Cam kết mua được ghi nhận | Sales |
| OrderLine | Một dòng hàng thuộc Order | Sales Order Aggregate |
| Money | Giá trị tiền và loại tiền | Sales domain |
| OrderRepository | Lưu/khôi phục Order Aggregate | Sales domain |
| OrderPlaced | Fact một Order đã được tạo | Sales domain |
| Outbox | Lưu thông điệp cần phát sau commit | Sales infrastructure |

~~~mermaid
flowchart LR
    Buyer[Người mua] --> Sales[Sales Context]
    Sales -->|Product query port| Catalog[Catalog Context]
    Sales -->|OrderRepository port| SalesDB[(Sales database)]
    Sales -->|Outbox port| Outbox[(Outbox table)]
    Outbox --> Publisher[Outbox publisher]
    Publisher --> Consumers[Context liên quan]
~~~

Catalog không trả Product Aggregate để Sales sửa trực tiếp. Nó trả snapshot tối thiểu cần cho giao dịch. Sales không lưu trực tiếp vào bảng Catalog. Repository chỉ làm việc với Aggregate mà Sales sở hữu.

## 3. Cấu trúc package đề xuất

Một cấu trúc package theo module có thể như sau:

~~~text
com.example.shop
├── catalog
│   └── api
│       ├── ProductCatalog.java
│       └── ProductForSale.java
└── sales
    ├── domain
    │   ├── model
    │   │   ├── Order.java
    │   │   ├── OrderLine.java
    │   │   ├── OrderId.java
    │   │   ├── CustomerId.java
    │   │   ├── ProductId.java
    │   │   ├── Money.java
    │   │   ├── OrderStatus.java
    │   │   └── OrderPlaced.java
    │   └── port
    │       └── OrderRepository.java
    ├── application
    │   ├── PlaceOrderCommand.java
    │   ├── PlaceOrderHandler.java
    │   ├── PlaceOrderResult.java
    │   └── port
    │       └── OutboxPort.java
    └── infrastructure
        ├── persistence
        │   ├── JpaOrderRepository.java
        │   ├── SpringDataOrderRepository.java
        │   ├── OrderJpaEntity.java
        │   ├── OrderLineJpaEntity.java
        │   └── OrderMapper.java
        └── messaging
            ├── JpaOutboxAdapter.java
            └── OutboxJpaEntity.java
~~~

Hướng phụ thuộc:

~~~text
sales.application ------> sales.domain
sales.infrastructure --> sales.application / sales.domain
catalog.api -----------> contract được Sales sử dụng

sales.domain -X-> JPA / Spring / database
sales.application -X-> sales.infrastructure
~~~

Domain định nghĩa port repository. Infrastructure implement port đó. Đây là Dependency Inversion: chính sách nghiệp vụ không phụ thuộc chi tiết lưu trữ.

## 4. Thiết kế các Value Object

### 4.1. OrderId, CustomerId và ProductId

ID có kiểu riêng giúp tránh truyền nhầm một String hoặc UUID giữa các khái niệm.

~~~java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "value");
    }

    public static OrderId newId() {
        return new OrderId(UUID.randomUUID());
    }
}

public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("CustomerId is required");
        }
    }
}

public record ProductId(String value) {
    public ProductId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("ProductId is required");
        }
    }
}
~~~

Các record này bất biến và so sánh theo giá trị. Nếu hệ thống có nhiều tenant, cần xác định ID duy nhất toàn cục hay chỉ duy nhất trong tenant; không nên để phạm vi định danh trở thành giả định ngầm.

### 4.2. Money

Không dùng BigDecimal rời rạc ở mọi nơi nếu tiền là khái niệm có quy tắc. Money kết hợp amount với currency và bảo vệ phép cộng giữa các loại tiền.

~~~java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount cannot be negative");
        }
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money multiply(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        return new Money(
            amount.multiply(BigDecimal.valueOf(quantity)),
            currency
        );
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}
~~~

Ví dụ chưa áp dụng rounding vì chính sách làm tròn phụ thuộc loại tiền, thuế, chiết khấu và quy định kế toán. Hệ thống thật cần xác định scale và rounding mode ở một nơi có ownership rõ ràng.

### 4.3. OrderLine

OrderLine là một thành phần thuộc Order Aggregate. Bài học dùng record bất biến để lưu snapshot sản phẩm và giá tại thời điểm đặt.

~~~java
public record OrderLine(
    ProductId productId,
    String productName,
    int quantity,
    Money unitPrice
) {
    public OrderLine {
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(productName, "productName");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (productName.isBlank()) {
            throw new IllegalArgumentException("Product name is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }

    public Money lineTotal() {
        return unitPrice.multiply(quantity);
    }
}
~~~

Snapshot giúp Order giữ lại thông tin giao dịch. Nếu Catalog đổi tên sản phẩm hoặc giá bán vào ngày hôm sau, hóa đơn và lịch sử Order vẫn có thể diễn giải đúng giao dịch ban đầu.

## 5. Thiết kế Domain Event

OrderPlaced là một fact: Order đã được tạo trong Sales. Nó không phải command yêu cầu một module khác tạo Order.

~~~java
public interface DomainEvent {
    UUID eventId();
    Instant occurredAt();
}

public record OrderPlaced(
    UUID eventId,
    OrderId orderId,
    CustomerId customerId,
    Money total,
    Instant occurredAt
) implements DomainEvent {
    public OrderPlaced {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(total);
        Objects.requireNonNull(occurredAt);
    }
}
~~~

Event có ID riêng để hỗ trợ deduplication khi được đưa ra ngoài. Domain Event có thể chứa kiểu miền nội bộ; trước khi công bố cho context khác, integration layer nên chuyển đổi nó thành integration contract có version và payload phù hợp.

## 6. Xây dựng Order Aggregate Root

Order là Aggregate Root vì nó bảo vệ invariant của toàn bộ đơn hàng. Bên ngoài không được thêm dòng hàng trực tiếp vào collection nội bộ hoặc tự sửa tổng tiền.

~~~java
public enum OrderStatus {
    PLACED
}
~~~

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;
    private final Money total;
    private final OrderStatus status;
    private final Instant placedAt;
    private final List<DomainEvent> domainEvents;

    private Order(
        OrderId id,
        CustomerId customerId,
        List<OrderLine> lines,
        Money total,
        OrderStatus status,
        Instant placedAt,
        List<DomainEvent> domainEvents
    ) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.lines = List.copyOf(lines);
        this.total = Objects.requireNonNull(total);
        this.status = Objects.requireNonNull(status);
        this.placedAt = Objects.requireNonNull(placedAt);
        this.domainEvents = new ArrayList<>(domainEvents);
    }

    public static Order place(
        OrderId id,
        CustomerId customerId,
        List<OrderLine> lines,
        Instant now
    ) {
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("An order must have at least one line");
        }

        Money total = lines.get(0).lineTotal();
        for (int i = 1; i < lines.size(); i++) {
            total = total.add(lines.get(i).lineTotal());
        }

        OrderPlaced event = new OrderPlaced(
            UUID.randomUUID(),
            id,
            customerId,
            total,
            now
        );

        return new Order(
            id,
            customerId,
            lines,
            total,
            OrderStatus.PLACED,
            now,
            List.of(event)
        );
    }

    public static Order reconstitute(
        OrderId id,
        CustomerId customerId,
        List<OrderLine> lines,
        Money storedTotal,
        OrderStatus status,
        Instant placedAt
    ) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Persisted order has no lines");
        }

        Money calculated = lines.get(0).lineTotal();
        for (int i = 1; i < lines.size(); i++) {
            calculated = calculated.add(lines.get(i).lineTotal());
        }

        if (!calculated.currency().equals(storedTotal.currency())
            || calculated.amount().compareTo(storedTotal.amount()) != 0) {
            throw new IllegalArgumentException("Persisted order total is inconsistent");
        }

        return new Order(
            id,
            customerId,
            lines,
            storedTotal,
            status,
            placedAt,
            List.of()
        );
    }

    public OrderId id() { return id; }
    public CustomerId customerId() { return customerId; }
    public List<OrderLine> lines() { return lines; }
    public Money total() { return total; }
    public OrderStatus status() { return status; }
    public Instant placedAt() { return placedAt; }
    public List<DomainEvent> domainEvents() {
        return List.copyOf(domainEvents);
    }
}
~~~

Hai factory có hai mục đích khác nhau:

- place tạo một Order mới từ hành vi nghiệp vụ và ghi nhận Domain Event.
- reconstitute khôi phục Order đã tồn tại từ persistence, không phát lại event lịch sử.

Đây là điểm quan trọng khi dùng Repository. Đọc một Aggregate đã lưu không được tạo ra một event OrderPlaced mới.

Trong ứng dụng thực tế, có thể dùng một kiểu Result hoặc exception nghiệp vụ riêng thay vì IllegalArgumentException. Ví dụ giữ đơn rỗng là lỗi validation của command hay vi phạm invariant của domain cần được thống nhất trong thiết kế.

## 7. Repository Port thuộc về domain

Repository là abstraction để lưu và truy xuất Aggregate Root. Nó không phải một bản sao tổng quát của Spring Data JpaRepository.

~~~java
public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(OrderId orderId);
}
~~~

Hợp đồng này có ý nghĩa nghiệp vụ: Sales có thể lưu hoặc khôi phục Order. Nó không để lộ tên bảng, kiểu Entity JPA, query SQL hay công nghệ database.

Một số nguyên tắc:

- Repository thường được định nghĩa cho Aggregate Root.
- Không tạo repository riêng cho từng Value Object hoặc Entity con nếu chúng không có vòng đời độc lập.
- Consumer không được sửa trực tiếp collection nội bộ của Aggregate.
- Implementation của repository nằm ở infrastructure.
- Interface nên thể hiện nhu cầu của domain/application, không sao chép toàn bộ API CRUD của ORM.

## 8. Phân biệt Repository Port và Product Query Port

Use case đặt hàng cần hai loại dữ liệu khác nhau:

1. Lưu Order do Sales sở hữu.
2. Đọc thông tin sản phẩm do Catalog sở hữu.

OrderRepository là repository port của Aggregate Sales. ProductCatalog là một query port để ứng dụng Sales yêu cầu snapshot từ Catalog.

~~~java
public record ProductForSale(
    String productId,
    String name,
    BigDecimal unitPrice,
    String currencyCode
) {
}

public interface ProductCatalog {
    Map<String, ProductForSale> findForSale(Set<String> productIds);
}
~~~

Port này thuộc public API của Catalog hoặc application boundary do hai module thống nhất. Contract dùng kiểu dữ liệu trung lập, không import ProductId hay Money nội bộ của Sales. Khi nhận snapshot, Sales chuyển dữ liệu đó thành Value Object thuộc model của mình. Nó cũng không trả JPA Entity của Catalog.

Nếu sản phẩm không tồn tại hoặc không được phép bán, Catalog có thể không trả về sản phẩm đó. Sales phải kiểm tra tập kết quả và từ chối yêu cầu nếu thiếu bất kỳ sản phẩm nào.

## 9. Định nghĩa command và kết quả use case

Command biểu diễn yêu cầu của caller. Nó không phải domain entity.

~~~java
public record PlaceOrderItem(
    String productId,
    int quantity
) {
    public PlaceOrderItem {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("productId is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}

public record PlaceOrderCommand(
    String customerId,
    List<PlaceOrderItem> items
) {
    public PlaceOrderCommand {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("items must not be empty");
        }
    }
}

public record PlaceOrderResult(
    String orderId,
    String status,
    BigDecimal total,
    String currency
) {
}
~~~

Command xác thực cấu trúc đầu vào cơ bản. Aggregate vẫn phải bảo vệ invariant của chính nó, vì không phải mọi caller đều đi qua cùng một HTTP controller.

## 10. Outbox Port

Nếu OrderPlaced phải được chuyển đến các context khác, chỉ lưu Order rồi publish event trực tiếp sẽ tạo ra một khoảng lỗi:

- Database commit thành công nhưng broker không nhận event.
- Broker nhận event nhưng transaction lưu Order rollback.

Transactional Outbox ghi Order và thông điệp cần phát trong cùng database transaction.

~~~java
public interface OutboxPort {
    void append(List<DomainEvent> events);
}
~~~

Port này nằm ở application boundary của Sales. Adapter infrastructure sẽ chuyển Domain Event thành outbox record. Publisher đọc các record chưa gửi và chuyển thành integration event sau commit.

Không phải mọi ứng dụng đều cần outbox ngay từ phiên bản đầu. Nếu event chỉ dùng nội bộ trong cùng transaction và không có consumer bất đồng bộ, có thể bắt đầu đơn giản hơn. Khi cần đảm bảo giao thông điệp, outbox là một lựa chọn đáng cân nhắc.

## 11. Triển khai PlaceOrderHandler

Application Service điều phối use case. Nó không tự tính toán lại invariant bên ngoài Aggregate và không biết Order được lưu bằng JPA hay JDBC.

~~~java
public final class PlaceOrderHandler {
    private final ProductCatalog productCatalog;
    private final OrderRepository orderRepository;
    private final OutboxPort outbox;
    private final Clock clock;

    public PlaceOrderHandler(
        ProductCatalog productCatalog,
        OrderRepository orderRepository,
        OutboxPort outbox,
        Clock clock
    ) {
        this.productCatalog = productCatalog;
        this.orderRepository = orderRepository;
        this.outbox = outbox;
        this.clock = clock;
    }

    public PlaceOrderResult handle(PlaceOrderCommand command) {
        CustomerId customerId = new CustomerId(command.customerId());

        Set<String> requestedIds = command.items().stream()
            .map(PlaceOrderItem::productId)
            .collect(Collectors.toSet());

        Map<String, ProductForSale> products =
            productCatalog.findForSale(requestedIds);

        if (!products.keySet().containsAll(requestedIds)) {
            throw new ProductNotAvailableException(
                "One or more products are unavailable"
            );
        }

        List<OrderLine> lines = command.items().stream()
            .map(item -> {
                ProductForSale product = products.get(item.productId());

                return new OrderLine(
                    new ProductId(product.productId()),
                    product.name(),
                    item.quantity(),
                    new Money(
                        product.unitPrice(),
                        Currency.getInstance(product.currencyCode())
                    )
                );
            })
            .toList();

        Order order = Order.place(
            OrderId.newId(),
            customerId,
            lines,
            clock.instant()
        );

        orderRepository.save(order);
        outbox.append(order.domainEvents());

        return new PlaceOrderResult(
            order.id().value().toString(),
            order.status().name(),
            order.total().amount(),
            order.total().currency().getCurrencyCode()
        );
    }
}
~~~

Handler thực hiện đúng vai trò điều phối:

1. Chuyển ID từ command thành Value Object.
2. Lấy snapshot sản phẩm từ Catalog.
3. Kiểm tra sản phẩm được phép bán.
4. Tạo OrderLine từ snapshot.
5. Gọi factory nghiệp vụ của Order.
6. Lưu Aggregate qua repository port.
7. Ghi Domain Event vào outbox port.
8. Trả kết quả cho caller.

Nếu một sản phẩm không tồn tại, handler dừng trước khi tạo và lưu Order. Không nên tạo Order một phần rồi mới phát hiện thiếu sản phẩm.

## 12. Đặt transaction ở application boundary

Order và outbox cần được ghi trong cùng transaction nếu hệ thống cam kết rằng mỗi Order được lưu thành công phải có thông điệp outbox tương ứng.

Use case thuần Java ở trên không phụ thuộc Spring. Một adapter hoặc decorator có thể mở transaction:

~~~java
@Service
public class TransactionalPlaceOrder {
    private final PlaceOrderHandler handler;

    public TransactionalPlaceOrder(PlaceOrderHandler handler) {
        this.handler = handler;
    }

    @Transactional
    public PlaceOrderResult handle(PlaceOrderCommand command) {
        return handler.handle(command);
    }
}
~~~

Lỗi sản phẩm không thể bán là một kết quả nghiệp vụ của use case. Ví dụ có thể biểu diễn bằng exception riêng để inbound adapter ánh xạ sang response phù hợp:

~~~java
public final class ProductNotAvailableException extends RuntimeException {
    public ProductNotAvailableException(String message) {
        super(message);
    }
}
~~~

Cả OrderRepository adapter và Outbox adapter phải tham gia cùng transaction manager/database transaction. Nếu chúng ghi vào hai database độc lập, annotation Transactional đơn giản không thể tự bảo đảm atomicity.

Nếu ProductCatalog gọi qua mạng đến service bên ngoài, không nên giữ transaction database mở trong suốt network call. Có thể lấy quote/snapshot trước, sau đó mở transaction để tạo Order và outbox; hoặc dùng quy trình nghiệp vụ có trạng thái nếu giá/khả năng bán cần được giữ chỗ.

## 13. Xây dựng persistence adapter bằng JPA

### 13.1. Spring Data repository là chi tiết infrastructure

~~~java
public interface SpringDataOrderRepository
    extends JpaRepository<OrderJpaEntity, UUID> {
}
~~~

Interface này không phải domain repository port. Nó chỉ là công cụ infrastructure để thao tác với entity persistence.

### 13.2. Persistence Entity

~~~java
@Entity
@Table(name = "sales_orders")
public class OrderJpaEntity {
    @Id
    private UUID id;

    @Column(nullable = false)
    private String customerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false, precision = 19, scale = 4)
    private BigDecimal totalAmount;

    @Column(nullable = false, length = 3)
    private String currencyCode;

    @Column(nullable = false)
    private Instant placedAt;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLineJpaEntity> lines = new ArrayList<>();

    protected OrderJpaEntity() {
    }

    public OrderJpaEntity(
        UUID id,
        String customerId,
        OrderStatus status,
        BigDecimal totalAmount,
        String currencyCode,
        Instant placedAt
    ) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.totalAmount = totalAmount;
        this.currencyCode = currencyCode;
        this.placedAt = placedAt;
    }

    public void addLine(OrderLineJpaEntity line) {
        lines.add(line);
        line.setOrder(this);
    }

    public UUID getId() { return id; }
    public String getCustomerId() { return customerId; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public String getCurrencyCode() { return currencyCode; }
    public Instant getPlacedAt() { return placedAt; }
    public List<OrderLineJpaEntity> getLines() { return lines; }
}
~~~

~~~java
@Entity
@Table(name = "sales_order_lines")
public class OrderLineJpaEntity {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private OrderJpaEntity order;

    @Column(nullable = false)
    private String productId;

    @Column(nullable = false)
    private String productName;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false, precision = 19, scale = 4)
    private BigDecimal unitPriceAmount;

    @Column(nullable = false, length = 3)
    private String currencyCode;

    protected OrderLineJpaEntity() {
    }

    public OrderLineJpaEntity(
        String productId,
        String productName,
        int quantity,
        BigDecimal unitPriceAmount,
        String currencyCode
    ) {
        this.productId = productId;
        this.productName = productName;
        this.quantity = quantity;
        this.unitPriceAmount = unitPriceAmount;
        this.currencyCode = currencyCode;
    }

    void setOrder(OrderJpaEntity order) {
        this.order = order;
    }

    public String getProductId() { return productId; }
    public String getProductName() { return productName; }
    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPriceAmount() { return unitPriceAmount; }
    public String getCurrencyCode() { return currencyCode; }
}
~~~

JPA Entity phục vụ mapping và persistence. Nó không được trả về từ OrderRepository port. Trong ứng dụng thật, cần cân nhắc cách ánh xạ enum, precision, index, constraint và versioning schema.

### 13.3. Mapper chuyển đổi hai mô hình

~~~java
@Component
public class OrderMapper {
    public OrderJpaEntity toEntity(Order order) {
        OrderJpaEntity entity = new OrderJpaEntity(
            order.id().value(),
            order.customerId().value(),
            order.status(),
            order.total().amount(),
            order.total().currency().getCurrencyCode(),
            order.placedAt()
        );

        for (OrderLine line : order.lines()) {
            entity.addLine(new OrderLineJpaEntity(
                line.productId().value(),
                line.productName(),
                line.quantity(),
                line.unitPrice().amount(),
                line.unitPrice().currency().getCurrencyCode()
            ));
        }

        return entity;
    }

    public Order toDomain(OrderJpaEntity entity) {
        List<OrderLine> lines = entity.getLines().stream()
            .map(line -> new OrderLine(
                new ProductId(line.getProductId()),
                line.getProductName(),
                line.getQuantity(),
                new Money(
                    line.getUnitPriceAmount(),
                    Currency.getInstance(line.getCurrencyCode())
                )
            ))
            .toList();

        Money total = new Money(
            entity.getTotalAmount(),
            Currency.getInstance(entity.getCurrencyCode())
        );

        return Order.reconstitute(
            new OrderId(entity.getId()),
            new CustomerId(entity.getCustomerId()),
            lines,
            total,
            entity.getStatus(),
            entity.getPlacedAt()
        );
    }
}
~~~

Mapper là nơi chuyển đổi giữa domain model và persistence model. Đừng đặt annotation JPA lên Aggregate chỉ để tiết kiệm một lớp mapping nếu điều đó khiến domain phụ thuộc framework hoặc buộc model phải chiều theo cấu trúc bảng.

### 13.4. Adapter thực thi Repository Port

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderRepository repository;
    private final OrderMapper mapper;

    public JpaOrderRepository(
        SpringDataOrderRepository repository,
        OrderMapper mapper
    ) {
        this.repository = repository;
        this.mapper = mapper;
    }

    @Override
    public void save(Order order) {
        repository.save(mapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId orderId) {
        return repository.findById(orderId.value())
            .map(mapper::toDomain);
    }
}
~~~

Dependency direction được đảo ngược: application gọi OrderRepository, còn JpaOrderRepository thực hiện hợp đồng đó. Nếu sau này chuyển sang JDBC hoặc database khác, domain và use case không cần thay đổi chỉ vì công nghệ lưu trữ đổi.

## 14. Lưu outbox trong cùng transaction

Outbox Entity là chi tiết infrastructure. Nó có thể chứa event ID, event type, schema version, payload JSON, occurred time, published time và retry metadata.

~~~java
@Entity
@Table(
    name = "sales_outbox",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_sales_outbox_event_id",
        columnNames = "event_id"
    )
)
public class OutboxJpaEntity {
    @Id
    private UUID eventId;

    @Column(nullable = false)
    private String eventType;

    @Column(nullable = false)
    private int schemaVersion;

    @Column(nullable = false, columnDefinition = "text")
    private String payload;

    @Column(nullable = false)
    private Instant occurredAt;

    private Instant publishedAt;

    protected OutboxJpaEntity() {
    }

    // Constructor và accessors được lược bỏ.
}
~~~

Adapter serialize từng Domain Event thành payload. Publisher chạy riêng, đọc record chưa publish, gửi message rồi đánh dấu published. Vì publisher có thể gửi lại khi gặp lỗi không rõ broker đã nhận hay chưa, consumer phải idempotent.

Không đánh dấu event đã publish trước khi broker xác nhận. Với hệ thống có throughput cao, cần batch, lock/claim strategy, retry backoff và dead-letter handling.

## 15. Lắp ghép dependency trong composition root

Composition root tạo các adapter và truyền chúng vào application handler. Spring có thể làm phần lắp ghép:

~~~java
@Configuration
public class SalesConfiguration {
    @Bean
    PlaceOrderHandler placeOrderHandler(
        ProductCatalog productCatalog,
        OrderRepository orderRepository,
        OutboxPort outboxPort,
        Clock clock
    ) {
        return new PlaceOrderHandler(
            productCatalog,
            orderRepository,
            outboxPort,
            clock
        );
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Spring tìm implementation của OrderRepository và OutboxPort trong infrastructure. Application không cần tự tạo JpaOrderRepository hoặc biết tên bean cụ thể.

Dùng Clock injection giúp test thời gian ổn định và tránh gọi trực tiếp Instant.now() ở mọi nơi trong domain/application.

## 16. Adapter HTTP gọi use case

Controller là inbound adapter. Nó chuyển HTTP request thành command, gọi use case và chuyển kết quả thành response.

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final TransactionalPlaceOrder placeOrder;

    public OrderController(TransactionalPlaceOrder placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResponse> place(
        @RequestBody PlaceOrderRequest request
    ) {
        PlaceOrderCommand command = new PlaceOrderCommand(
            request.customerId(),
            request.items().stream()
                .map(item -> new PlaceOrderItem(
                    item.productId(),
                    item.quantity()
                ))
                .toList()
        );

        PlaceOrderResult result = placeOrder.handle(command);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(new PlaceOrderResponse(
                result.orderId(),
                result.status(),
                result.total(),
                result.currency()
            ));
    }
}
~~~

Trong ứng dụng thật, cần exception handler chuyển lỗi validation, sản phẩm không khả dụng và lỗi xung đột thành HTTP response phù hợp. Không trả stack trace hoặc chi tiết database cho client.

## 17. Kiểm thử Domain Model

Domain test nên nhanh, không khởi động Spring và không cần database.

~~~java
class OrderTest {
    private final Currency vnd = Currency.getInstance("VND");
    private final Instant now = Instant.parse("2026-11-18T09:00:00Z");

    @Test
    void places_order_and_calculates_total_from_lines() {
        Order order = Order.place(
            OrderId.newId(),
            new CustomerId("CUS-1"),
            List.of(
                new OrderLine(
                    new ProductId("P-1"),
                    "Keyboard",
                    2,
                    new Money(new BigDecimal("100000"), vnd)
                ),
                new OrderLine(
                    new ProductId("P-2"),
                    "Mouse",
                    1,
                    new Money(new BigDecimal("50000"), vnd)
                )
            ),
            now
        );

        assertEquals(OrderStatus.PLACED, order.status());
        assertEquals(0, new BigDecimal("250000").compareTo(order.total().amount()));
        assertEquals(2, order.lines().size());
        assertEquals(1, order.domainEvents().size());
        assertInstanceOf(OrderPlaced.class, order.domainEvents().get(0));
    }

    @Test
    void rejects_order_without_lines() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Order.place(
                OrderId.newId(),
                new CustomerId("CUS-1"),
                List.of(),
                now
            )
        );
    }

    @Test
    void rejects_lines_with_different_currencies() {
        OrderLine vndLine = new OrderLine(
            new ProductId("P-1"),
            "Keyboard",
            1,
            new Money(new BigDecimal("100000"), Currency.getInstance("VND"))
        );
        OrderLine usdLine = new OrderLine(
            new ProductId("P-2"),
            "Mouse",
            1,
            new Money(new BigDecimal("10"), Currency.getInstance("USD"))
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> Order.place(
                OrderId.newId(),
                new CustomerId("CUS-1"),
                List.of(vndLine, usdLine),
                now
            )
        );
    }
}
~~~

Các test này bảo vệ invariant và hành vi của Aggregate. So sánh BigDecimal bằng compareTo giúp tránh lỗi do scale khác nhau như 250000 và 250000.00.

## 18. Kiểm thử Application Use Case bằng fake ports

Application test không cần JPA. Dùng fake để kiểm tra việc điều phối giữa ProductCatalog, OrderRepository và OutboxPort.

~~~java
class PlaceOrderHandlerTest {
    private final InMemoryOrderRepository orders = new InMemoryOrderRepository();
    private final RecordingOutbox outbox = new RecordingOutbox();
    private final ProductCatalog catalog = ids -> Map.of(
        "P-1",
        new ProductForSale(
            "P-1",
            "Keyboard",
            new BigDecimal("100000"),
            "VND"
        )
    );

    @Test
    void saves_order_and_records_event() {
        PlaceOrderHandler handler = new PlaceOrderHandler(
            catalog,
            orders,
            outbox,
            Clock.fixed(
                Instant.parse("2026-11-18T09:00:00Z"),
                ZoneOffset.UTC
            )
        );

        PlaceOrderResult result = handler.handle(
            new PlaceOrderCommand(
                "CUS-1",
                List.of(new PlaceOrderItem("P-1", 2))
            )
        );

        assertEquals("PLACED", result.status());
        assertEquals(0, new BigDecimal("200000").compareTo(result.total()));
        assertEquals(1, orders.savedOrders().size());
        assertEquals(1, outbox.events().size());
    }

    @Test
    void does_not_save_order_when_product_is_missing() {
        ProductCatalog emptyCatalog = ids -> Map.of();
        PlaceOrderHandler handler = new PlaceOrderHandler(
            emptyCatalog,
            orders,
            outbox,
            Clock.systemUTC()
        );

        assertThrows(
            ProductNotAvailableException.class,
            () -> handler.handle(
                new PlaceOrderCommand(
                    "CUS-1",
                    List.of(new PlaceOrderItem("P-404", 1))
                )
            )
        );

        assertTrue(orders.savedOrders().isEmpty());
        assertTrue(outbox.events().isEmpty());
    }
}
~~~

Fake repository lưu Aggregate vào collection trong bộ nhớ. RecordingOutbox ghi lại event được truyền vào. Các fake này không thay thế integration test, nhưng giúp kiểm tra application orchestration mà không cần boot toàn ứng dụng.

Các fake tối thiểu có thể triển khai như sau:

~~~java
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<OrderId, Order> store = new HashMap<>();

    @Override
    public void save(Order order) {
        store.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(store.get(id));
    }

    List<Order> savedOrders() {
        return List.copyOf(store.values());
    }
}

final class RecordingOutbox implements OutboxPort {
    private final List<DomainEvent> recorded = new ArrayList<>();

    @Override
    public void append(List<DomainEvent> events) {
        recorded.addAll(events);
    }

    List<DomainEvent> events() {
        return List.copyOf(recorded);
    }
}
~~~

Trong test adapter JPA ở phần tiếp theo, TestOrders.validOrder() là một fixture tạo Order hợp lệ dùng chung cho test. Các import và cấu hình test được lược bỏ để tập trung vào hành vi.

## 19. Kiểm thử Persistence Adapter

Repository adapter cần được kiểm tra với database thật hoặc database test tương thích. Mục tiêu là xác nhận mapping hai chiều không làm mất dữ liệu và Aggregate được khôi phục đúng.

Các trường hợp nên có:

- Save một Order có nhiều dòng hàng.
- Đọc lại bằng OrderId.
- Xác minh CustomerId, trạng thái, thời điểm và tổng tiền.
- Xác minh ProductId, tên snapshot, số lượng và đơn giá từng dòng.
- Xác minh domainEvents rỗng sau reconstitution.
- Kiểm tra constraint và cascade theo đúng ownership.
- Kiểm tra rollback nếu lưu Order hoặc outbox thất bại.

Ví dụ kiểm thử dạng integration:

~~~java
@DataJpaTest
class JpaOrderRepositoryTest {
    @Autowired
    SpringDataOrderRepository springDataRepository;

    @Autowired
    OrderMapper mapper;

    @Test
    void saves_and_reconstitutes_order() {
        Order order = TestOrders.validOrder();

        springDataRepository.save(mapper.toEntity(order));

        OrderJpaEntity stored = springDataRepository
            .findById(order.id().value())
            .orElseThrow();

        Order restored = mapper.toDomain(stored);

        assertEquals(order.id(), restored.id());
        assertEquals(order.customerId(), restored.customerId());
        assertEquals(order.status(), restored.status());
        assertEquals(0, order.total().amount().compareTo(restored.total().amount()));
        assertEquals(order.lines().size(), restored.lines().size());
        assertTrue(restored.domainEvents().isEmpty());
    }
}
~~~

Test này minh họa mapper và Spring Data repository. Để kiểm tra adapter đầy đủ, nên gọi trực tiếp JpaOrderRepository và cấu hình transaction/database test tương ứng.

## 20. Kiểm tra dependency bằng Architecture Test

Một test kiến trúc có thể bảo vệ nguyên tắc domain không phụ thuộc JPA hoặc Spring:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class SalesArchitectureTest {
    @ArchTest
    static final ArchRule domain_must_not_depend_on_jpa =
        noClasses()
            .that().resideInAPackage("..sales.domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "jakarta.persistence..",
                "org.springframework.."
            );

    @ArchTest
    static final ArchRule application_must_not_depend_on_infrastructure =
        noClasses()
            .that().resideInAPackage("..sales.application..")
            .should().dependOnClassesThat()
            .resideInAPackage("..sales.infrastructure..");
}
~~~

Nếu một lập trình viên thêm annotation JPA vào Order hoặc inject JpaRepository vào handler, test kiến trúc sẽ phát hiện dependency bị đảo ngược.

## 21. Luồng hoàn chỉnh từ request đến database

~~~mermaid
sequenceDiagram
    participant Client
    participant Controller
    participant Handler as PlaceOrderHandler
    participant Catalog as ProductCatalog port
    participant Order as Order Aggregate
    participant Repo as OrderRepository port
    participant Outbox as OutboxPort
    participant DB as Database

    Client->>Controller: POST /orders
    Controller->>Handler: PlaceOrderCommand
    Handler->>Catalog: findForSale(productIds)
    Catalog-->>Handler: Product snapshots
    Handler->>Order: Order.place(...)
    Order-->>Handler: Order + OrderPlaced
    Handler->>Repo: save(order)
    Handler->>Outbox: append(domainEvents)
    Repo->>DB: INSERT order + lines
    Outbox->>DB: INSERT outbox event
    DB-->>Handler: commit
    Handler-->>Controller: PlaceOrderResult
    Controller-->>Client: 201 Created
~~~

Trong triển khai thực tế, repository và outbox cùng tham gia một transaction. Publisher gửi event sau commit; consumer xử lý duplicate an toàn.

## 22. Những sai lầm thường gặp khi triển khai Repository Port

### Để domain phụ thuộc Spring Data

Nếu Order import JpaRepository hoặc annotation JPA, domain đang phụ thuộc persistence. Hãy giữ interface port ở phía domain và adapter ở infrastructure.

### Tạo GenericRepository cho mọi loại object

Một generic CRUD repository thường làm mất ý nghĩa nghiệp vụ và khuyến khích lưu từng bảng thay vì lưu Aggregate Root. Thiết kế repository theo Aggregate cần được lưu và truy xuất.

### Đặt repository implementation trong domain

Domain chỉ nên định nghĩa hợp đồng cần thiết. SQL, JPA, mapping và connection thuộc infrastructure.

### Trả JPA Entity cho application

Application sẽ phụ thuộc vào persistence model và có thể sửa dữ liệu mà không đi qua invariant của Aggregate. Repository nên trả domain Aggregate.

### Lưu từng OrderLine qua repository riêng

Nếu OrderLine không có lifecycle độc lập, lưu Aggregate Root cùng các thành phần của nó. Không để caller tự phối hợp nhiều repository để tạo một Order.

### Tính tổng tiền ở controller

Controller chỉ chuyển request thành command. Tổng tiền phải được tính từ OrderLine trong domain để mọi entry point đều bảo vệ cùng invariant.

### Phát event trước khi transaction commit

Consumer có thể nhận event cho một Order chưa được lưu. Dùng outbox hoặc cơ chế after-commit phù hợp.

### Khôi phục Aggregate nhưng phát lại event tạo mới

Reconstitution phải khôi phục trạng thái lịch sử và không phát OrderPlaced lần nữa.

### Đọc Catalog trực tiếp từ bảng của Catalog

Điều đó phá ownership giữa module. Dùng query port hoặc contract do Catalog công bố.

## 23. Các vấn đề cần nghĩ đến trước khi đưa vào production

Bài thực hành tập trung vào luồng cơ bản. Hệ thống thật cần xem xét thêm:

- **Idempotency:** Client retry POST do timeout có thể tạo hai Order. Dùng idempotency key và unique constraint phù hợp.
- **Concurrency:** Nhiều request có thể cùng tiêu thụ một giới hạn tài nguyên. Cần transaction, optimistic/pessimistic locking hoặc constraint theo invariant.
- **Price quote:** Giá có thể hết hạn giữa lúc đọc Catalog và lưu Order. Có thể cần quote ID, expiry hoặc xác nhận giá.
- **Inventory:** Đặt Order không đồng nghĩa hàng đã được giữ. Reservation thuộc context và quy tắc riêng.
- **Tax/discount:** Cần snapshot các thành phần thương mại đã chốt và chính sách làm tròn.
- **Outbox delivery:** Publisher cần retry, monitoring, deduplication và xử lý message lỗi.
- **Security:** CustomerId không nên được tin chỉ vì client gửi lên; cần xác định danh tính từ security context.
- **Data retention:** Snapshot đơn hàng cần tuân thủ chính sách lưu trữ và quyền riêng tư.
- **Observability:** Log và trace cần OrderId, correlation ID và tên use case.

Không nên đưa tất cả cơ chế này vào bài toán ban đầu nếu chưa cần. Hãy bổ sung khi yêu cầu và rủi ro thực tế đã rõ.

## 24. Bài tập mở rộng

Hãy triển khai thêm các chức năng sau theo cùng ranh giới:

1. Thêm địa chỉ giao hàng dạng snapshot vào Order.
2. Thêm discount và lưu commercial terms tại thời điểm đặt.
3. Thêm hành vi hủy đơn với invariant chỉ cho phép hủy ở trạng thái hợp lệ.
4. Tạo Domain Event OrderCancelled.
5. Thêm idempotency key để retry request không tạo Order trùng.
6. Thêm optimistic locking nếu Order có thể được cập nhật đồng thời.
7. Viết adapter JDBC thay cho JPA mà không sửa domain.
8. Viết integration test xác nhận Order và Outbox rollback cùng nhau.
9. Thêm consumer tạo FulfillmentOrder từ integration event.
10. Xác định API contract giữa Sales và Fulfillment.

Với mỗi thay đổi, hãy trả lời: Aggregate nào sở hữu quy tắc? Repository port có cần thay đổi không? Dữ liệu nào là snapshot? Transaction boundary nằm ở đâu? Test nào bảo vệ hành vi?

## 25. Checklist hoàn thành ca sử dụng đặt hàng

- [ ] Bounded Context Sales và ownership của Order đã rõ.
- [ ] Order được mô hình hóa thành Aggregate Root.
- [ ] OrderLine và Money có invariant phù hợp.
- [ ] ID được biểu diễn bằng Value Object.
- [ ] Giá và tên sản phẩm được snapshot theo chính sách.
- [ ] Order tự tính tổng tiền từ các dòng hàng.
- [ ] Repository Port được định nghĩa phía domain.
- [ ] Application Handler phụ thuộc vào port, không phụ thuộc JPA.
- [ ] Catalog được truy cập qua query contract.
- [ ] JPA Entity được giữ trong infrastructure.
- [ ] Mapper chuyển đổi persistence model và domain model.
- [ ] Reconstitution không phát lại domain event.
- [ ] Order và Outbox được ghi trong cùng transaction khi cần.
- [ ] Controller chỉ chuyển đổi giao thức thành command.
- [ ] Domain test bảo vệ invariant.
- [ ] Application test dùng fake ports để kiểm tra orchestration.
- [ ] Integration test xác nhận mapping và transaction.
- [ ] Architecture test bảo vệ dependency direction.
- [ ] Idempotency, concurrency và các chính sách production đã được đánh giá.

## Kết luận

Ca sử dụng đặt hàng cho thấy Repository Port là ranh giới giữa mô hình nghiệp vụ và chi tiết lưu trữ. Order Aggregate bảo vệ invariant; Value Object làm rõ ý nghĩa của ID và tiền; Application Handler điều phối use case; OrderRepository định nghĩa hợp đồng lưu trữ; JpaOrderRepository và mapper hiện thực hợp đồng ở infrastructure.

Cách tổ chức này giúp đổi JPA sang JDBC hoặc thay database mà không phải viết lại quy tắc nghiệp vụ. Nó cũng giữ cho application không thao tác trực tiếp với bảng hoặc Entity persistence. Khi cần phát sự kiện, Outbox Port và transaction boundary giúp bảo đảm Order cùng thông điệp được ghi nhận nhất quán.

Điểm quan trọng nhất không phải là số lượng lớp. Đó là mỗi quyết định có một owner rõ, invariant được bảo vệ tại Aggregate, và mọi chi tiết kỹ thuật đi qua hợp đồng phù hợp. Khi các ranh giới này rõ ràng, một ca sử dụng thực tế có thể được triển khai, kiểm thử và tiến hóa mà không làm domain model phụ thuộc vào công nghệ lưu trữ.

