# Giữ ranh giới giao dịch tại nơi điều phối nghiệp vụ phù hợp

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Thiết kế Repository

Một yêu cầu đặt hàng thường không chỉ gọi một repository: hệ thống phải kiểm tra quyền, tìm sản phẩm, trừ hàng tồn, tạo đơn hàng, ghi sự kiện và trả kết quả. Nếu từng repository tự mở và **commit transaction độc lập**, khi bước cuối lỗi, những bước đầu có thể đã commit: tồn kho giảm nhưng thiếu đơn hàng, hoặc đơn đã tạo mà outbox chưa có sự kiện.

Giải pháp không phải đơn giản là “gắn @Transactional cho mọi method”. Quyết định **giao dịch bắt đầu ở đâu, chứa những thay đổi nào, kết thúc khi nào và rollback những gì** phải gắn với **đơn vị công việc nghiệp vụ**.

Trong ứng dụng JPA:

- **Domain object** bảo vệ invariants như “không bán vượt số lượng hàng còn”.
- **Repository** cung cấp thao tác đọc/ghi entity, query và chuyển đổi persistence details.
- **Application service/use-case coordinator** điều phối những thao tác phải cùng thành công, thường là nơi **sở hữu transaction boundary**.
- **Transaction manager** điều khiển begin, commit, rollback theo Spring/JTA/JPA resource-local.
- **Database** bảo đảm atomicity/isolation/durability trong phạm vi transaction nó quản lý.
- **External systems** như email, payment gateway hay Kafka không tự tham gia local database transaction; chúng cần outbox, idempotency hoặc workflow phân tán.

**Nguyên tắc:** *Repository biết cách lưu; nơi điều phối nghiệp vụ biết những thao tác nào phải cùng thành công.* Đặt transaction boundary theo business invariant, không theo số lần gọi save().

## 1. Vì sao vị trí transaction boundary quan trọng?

### 1.1. Bài toán đặt hàng qua nhiều repositories

~~~text
PlaceOrder command
      |
      v
Kiểm tra tenant và quyền đặt hàng
      |
      v
Đọc tồn kho (StockRepository)
      |
      v
Giữ chỗ 2 sản phẩm (ProductStock.reserve)
      |
      v
Tạo đơn hàng (OrderRepository)
      |
      v
Ghi outbox event (OutboxRepository)
      |
      v
COMMIT transaction
      |
      v
Trả kết quả
~~~

Đối với quy tắc “đã trừ tồn kho thì phải có đơn tương ứng”, ba thay đổi database phải cùng transaction:

1. UPDATE stock;
2. INSERT purchase_order;
3. INSERT outbox_message.

Nếu outbox INSERT thất bại, stock/order **không được commit riêng lẻ**.

### 1.2. Thiết kế sai: repository tự commit mỗi thao tác

~~~text
StockRepository.reserve()
  BEGIN → UPDATE stock → COMMIT

OrderRepository.create()
  BEGIN → INSERT order → COMMIT

OutboxRepository.append()
  BEGIN → INSERT outbox → FAIL → ROLLBACK

Kết quả:
  Stock giảm ✓
  Order có ✓
  Outbox thiếu ✗
~~~

**Lưu ý Spring:** Nhiều methods @Transactional(REQUIRED) không nhất thiết có nhiều commits nếu chúng tham gia một transaction bao ngoài. Sai lầm này xảy ra khi thực sự **không có outer transaction** hoặc từng method mở transaction độc lập.

### 1.3. Thiết kế đúng: transaction tại use case

~~~text
PlaceOrderService.placeOrder()
  |
  | BEGIN
  |   StockRepository.find(...)
  |   ProductStock.reserve(...)
  |   OrderRepository.save(...)
  |   OutboxRepository.save(...)
  | COMMIT
  |
  v
Response
~~~

Nếu một thao tác ghi lỗi trước commit, transaction rollback, kể cả những INSERT/UPDATE đã flush.

### 1.4. Business unit of work không luôn bằng HTTP request

- GET catalog có thể dùng một read transaction ngắn hoặc projection query.
- POST placeOrder có một DB transaction chứa writes phải atomic.
- POST exportReport có thể chỉ tạo job; worker chạy transactions riêng.
- Một payment workflow kéo dài vài phút/giờ không thể giữ một DB transaction mở.
- Một message consumer có thể xử lý **một message** trong một transaction với idempotency.

Boundary được xác định bởi **business consistency requirement**, không bởi HTTP verb.

## 2. Phân vai Domain, Repository, Coordinator và Transaction Manager

### 2.1. Domain giữ business invariants

~~~java
public void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "Số lượng phải dương"
        );
    }

    if (available < quantity) {
        throw new InsufficientStockException();
    }

    available -= quantity;
}
~~~

Domain method biết quy tắc tồn kho, không cần EntityManager, commit hoặc gửi email.

### 2.2. Repository sở hữu truy cập dữ liệu

~~~java
public interface StockRepository {
    Optional<ProductStock> findByTenantAndSku(
        String tenantId,
        String sku
    );
}
~~~

JPA implementation:

~~~java
return em.createQuery(
    """
    select s
    from ProductStock s
    where s.tenantId = :tenant
      and s.sku = :sku
    """,
    ProductStock.class
)
.setParameter("tenant", tenantId)
.setParameter("sku", sku)
.getResultStream()
.findFirst();
~~~

Repository biết query/mapping, không cần biết rằng khi đặt hàng còn phải ghi outbox.

### 2.3. Application service điều phối nguyên tử

~~~java
@Transactional
public OrderReceipt place(PlaceOrderCommand command) {
    authorization.requirePermission("ORDER_PLACE");

    ProductStock stock = stocks.findForOrder(
        authorization.currentTenant(),
        command.sku()
    );

    stock.reserve(command.quantity());

    PurchaseOrder order = orders.save(
        PurchaseOrder.place(command)
    );

    outbox.append(OrderPlacedEvent.from(order));

    return OrderReceipt.from(order);
}
~~~

Các method và types như findForOrder, PlaceOrderCommand là minh họa nghiệp vụ; không phải JPA API chuẩn. Điểm quan trọng: transaction bao quanh các DB changes cần atomic.

### 2.4. Transaction Manager thực hiện cơ chế

- **Jakarta Persistence resource-local:** EntityTransaction.begin/commit/rollback.
- **Spring:** @Transactional, TransactionTemplate và PlatformTransactionManager.
- **JTA:** UserTransaction hoặc container-managed transactions.

Application logic có thể chọn boundary qua annotation hoặc một transaction decorator. Repository không nên độc lập commit khi đang tham gia use case cần atomicity.

### 2.5. Sơ đồ kiến trúc

~~~text
HTTP / CLI / Queue Listener
          |
          v
Application Use Case
 - authorization
 - domain orchestration
 - transaction boundary
          |
     +----+--------------+
     |                   |
     v                   v
Domain entities      Repository ports
 - invariants            |
 - transitions           v
                    JPA adapters
                    - EntityManager
                    - JPQL / Criteria
                    - mapping / queries
                           |
                           v
                        Database
          ^
          |
   Transaction manager
   begin / commit / rollback
~~~

Application service không nhất thiết import JPA. Nếu dùng Spring @Transactional, nó phụ thuộc Spring transaction abstraction; nếu cần core thuần Java, transaction boundary có thể nằm trong decorator/use-case executor.

## 3. Ranh giới transaction theo business invariant

### 3.1. Một repository vẫn có thể cần transaction

Một Product update có thể nạp entity, check version, gọi domain method và ghi audit. Dù chỉ một repository, nếu mọi thay đổi cần atomic, vẫn dùng một transaction.

### 3.2. Nhiều repositories không mặc nhiên cần transaction lớn

Trang dashboard đọc catalog, số liệu tháng và recommendations. Nếu business chấp nhận snapshots khác nhau, có thể không cần một transaction bao toàn bộ những queries; nếu báo cáo đòi read-consistency, cần chọn isolation/snapshot phù hợp.

### 3.3. Boundary quá hẹp

Khi mỗi repository tự commit, lỗi bước sau để lại một phần thay đổi đã commit; service không thể “rollback các commits trước” bằng em.clear.

### 3.4. Boundary quá rộng

Đừng giữ transaction mở trong khi:
- Gọi payment gateway;
- Đợi HTTP API bên ngoài;
- Đọc file hàng GB;
- Tạo báo cáo hàng chục phút;
- Chờ người dùng xác nhận;
- Sleep/backoff giữa retry attempts.

Database có thể giữ connection, locks, snapshots và transaction logs rất lâu. Boundary nên là **đoạn DB atomic ngắn nhất thỏa business rule**.

### 3.5. Một workflow có thể gồm nhiều giao dịch

Đặt hàng:
1. Transaction A tạo Order + reservation + outbox.
2. Worker gọi dịch vụ vận chuyển.
3. Transaction B ghi trackingId và trạng thái.
4. Nếu vận chuyển lỗi, có retry hoặc compensation.

Đó là workflow dài, không phải một local ACID transaction.

### 3.6. Hỏi gì trước khi chọn boundary?

1. Những DB writes nào phải cùng commit/rollback?
2. Invariants nào cần giữ tới transaction end?
3. Có chung DB/transaction manager hay không?
4. Có remote API/message broker/email không?
5. Có yêu cầu consistent read snapshot không?
6. Caller cần kết quả đã commit hay chỉ accepted job?
7. Có chấp nhận partial success và resume không?

## 4. Persistence context và transaction không phải một khái niệm

### 4.1. EntityManager quản lý trạng thái đối tượng

JPA EntityManager gắn với persistence context: quản lý entity identity, dirty checking, cascades và các thay đổi đang chờ. Transaction quản lý việc database có **commit hay rollback** những thay đổi ấy.

~~~text
EntityManager / Persistence Context
  |
  +-- ProductStock (managed)
  +-- PurchaseOrder (new/managed)
  +-- OutboxMessage (new/managed)
  |
  v
flush → SQL INSERT/UPDATE
  |
  +-- rollback → DB khôi phục trạng thái trước tx
  |
  +-- commit   → changes bền vững
~~~

### 4.2. persist/save không đồng nghĩa commit

~~~java
em.persist(order);
~~~

đưa entity vào context; một số ID strategies có thể khiến SQL INSERT chạy sớm, nhưng **không tự commit**. Tương tự, Spring Data repository.save() trong outer transaction thường tham gia transaction đó, chứ không commit riêng.

### 4.3. flush đồng bộ SQL nhưng không kết thúc giao dịch

~~~java
em.persist(order);
em.flush(); // Chưa phải COMMIT.
~~~

Nếu outbox INSERT sau đó lỗi, transaction có thể rollback cả order và stock. Flush giúp phát hiện lỗi sớm, nhưng không bảo đảm mọi deferred constraint/commit-time error đều đã xuất hiện.

### 4.4. clear khác rollback

~~~java
em.flush();
em.clear();
~~~

Clear detach managed entities; không rollback database transaction. Nếu flush đã lỗi và DB transaction bị đánh dấu aborted/rollback-only, clear **không phục hồi** transaction để tiếp tục ghi.

### 4.5. @Version giúp phát hiện stale updates

~~~java
@Version
private Long version;
~~~

Hai transactions có thể đọc ProductStock version=5. Nếu một transaction commit thành version=6, transaction còn lại có thể gặp **OptimisticLockException** ở flush/commit. Application phải rollback/reload/recompute intent theo policy; không retry stale entity trong cùng transaction.

### 4.6. Database constraints là tuyến bảo vệ cuối

UNIQUE(tenant_id, request_key), UNIQUE(tenant_id, sku), NOT NULL, CHECK, FOREIGN KEY bảo vệ data integrity ngay cả khi app có validation. Một pre-check thấy SKU chưa tồn tại có thể bị race; constraint violation có thể phát sinh ở flush hoặc commit.

## 5. Một ví dụ xuyên suốt: đặt hàng trong một transaction

Ta thiết kế use case tạo đơn bán hàng và giữ chỗ tồn kho. Ba thay đổi trong cùng PostgreSQL database:
- Cập nhật ProductStock;
- Thêm PurchaseOrder;
- Thêm OutboxMessage để publisher xử lý sau commit.

Các class Java dùng Jakarta Persistence và Spring. Tên packages/libraries minh họa, cần bổ sung imports và cấu hình DB/migrations tương ứng.

### 5.1. Entity ProductStock

~~~java
package com.example.order.persistence;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(
    name = "product_stocks",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_stock_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class ProductStock {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Version
    private Long version;

    @Column(
        name = "tenant_id",
        nullable = false,
        updatable = false
    )
    private String tenantId;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int available;

    protected ProductStock() {}

    public ProductStock(
            String tenantId,
            String sku,
            int initialAvailable) {

        this.tenantId = Objects.requireNonNull(tenantId);
        this.sku = Objects.requireNonNull(sku);

        if (initialAvailable < 0) {
            throw new IllegalArgumentException("stock");
        }

        this.available = initialAvailable;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }

        if (available < quantity) {
            throw new InsufficientStockException();
        }

        available -= quantity;
    }

    public int getAvailable() {
        return available;
    }

    public Long getVersion() {
        return version;
    }

    public String getSku() {
        return sku;
    }

    public String getTenantId() {
        return tenantId;
    }
}
~~~

**InsufficientStockException** là domain exception ứng dụng tự định nghĩa. Khi ProductStock là managed entity trong một transaction, đổi available bằng reserve() được JPA dirty checking ghi xuống DB lúc flush/commit.

### 5.2. Entity PurchaseOrder

~~~java
package com.example.order.persistence;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(
    name = "purchase_orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_request",
        columnNames = {"tenant_id", "request_key"}
    )
)
public class PurchaseOrder {

    @Id
    @Column(nullable = false)
    private UUID id;

    @Version
    private Long version;

    @Column(
        name = "tenant_id",
        nullable = false,
        updatable = false
    )
    private String tenantId;

    @Column(
        name = "request_key",
        nullable = false,
        updatable = false
    )
    private String requestKey;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    protected PurchaseOrder() {}

    public static PurchaseOrder place(
            String tenantId,
            String requestKey,
            String sku,
            int quantity,
            Instant createdAt) {

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }

        PurchaseOrder order = new PurchaseOrder();
        order.id = UUID.randomUUID();
        order.tenantId = Objects.requireNonNull(tenantId);
        order.requestKey = Objects.requireNonNull(requestKey);
        order.sku = Objects.requireNonNull(sku);
        order.quantity = quantity;
        order.status = OrderStatus.PLACED;
        order.createdAt = Objects.requireNonNull(createdAt);
        return order;
    }

    public UUID getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getRequestKey() { return requestKey; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public OrderStatus getStatus() { return status; }
}

enum OrderStatus {
    PLACED,
    CANCELLED
}
~~~

Business requestKey dùng để chống duplicate request. **UNIQUE(tenant_id, request_key)** phải có thật trong schema migration. Domain/API còn cần xác minh request trùng key có cùng intent; không được dùng cùng key cho hai payload khác nhau rồi coi kết quả giống nhau.

### 5.3. OutboxMessage là một record giao dịch trong DB

~~~java
package com.example.order.persistence;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(name = "outbox_messages")
public class OutboxMessage {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String aggregateType;

    @Column(nullable = false)
    private String aggregateId;

    @Column(nullable = false)
    private String eventType;

    @Lob
    @Column(nullable = false)
    private String payload;

    @Column(nullable = false)
    private Instant occurredAt;

    protected OutboxMessage() {}

    public OutboxMessage(
            UUID id,
            String aggregateType,
            String aggregateId,
            String eventType,
            String payload,
            Instant occurredAt) {

        this.id = Objects.requireNonNull(id);
        this.aggregateType =
            Objects.requireNonNull(aggregateType);
        this.aggregateId =
            Objects.requireNonNull(aggregateId);
        this.eventType = Objects.requireNonNull(eventType);
        this.payload = Objects.requireNonNull(payload);
        this.occurredAt =
            Objects.requireNonNull(occurredAt);
    }
}
~~~

Payload phải được tạo từ **event DTO đã chọn fields và versioned schema**. Không serialize nguyên managed JPA entity vào payload vì rủi ro data leakage/lazy graph.

### 5.4. Repositories Spring Data JPA

~~~java
package com.example.order.persistence;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
import java.util.UUID;

public interface StockJpaRepository
        extends JpaRepository<ProductStock, Long> {

    Optional<ProductStock> findByTenantIdAndSku(
        String tenantId, String sku
    );
}

public interface OrderJpaRepository
        extends JpaRepository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findByTenantIdAndRequestKey(
        String tenantId,
        String requestKey
    );
}

public interface OutboxJpaRepository
        extends JpaRepository<OutboxMessage, UUID> {}
~~~

Nếu repository classes nằm trong Spring-managed application, Spring Data implementations thường có transaction metadata cho các CRUD methods. Tuy nhiên **outer application transaction** vẫn nên điều phối atomicity của toàn bộ use case. Query methods tự khai báo có transaction behavior khác CRUD methods tùy cấu hình, cần quan sát cụ thể.

### 5.5. Command và result DTO

~~~java
public record PlaceOrderCommand(
    String sku,
    int quantity,
    String requestKey
) {}

public record OrderReceipt(
    UUID orderId,
    String status
) {}
~~~

Thực tế cần Bean Validation hoặc domain validation cho SKU/quantity/requestKey trước DB operation; user/tenant IDs không nên được tin trực tiếp từ request DTO.

### 5.6. PlaceOrderService điều phối một transaction

~~~java
package com.example.order.application;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.util.UUID;

@Service
public class PlaceOrderService {

    private final StockJpaRepository stocks;
    private final OrderJpaRepository orders;
    private final OutboxJpaRepository outbox;
    private final TenantAccess tenantAccess;
    private final EventPayloadSerializer serializer;
    private final Clock clock;

    public PlaceOrderService(
            StockJpaRepository stocks,
            OrderJpaRepository orders,
            OutboxJpaRepository outbox,
            TenantAccess tenantAccess,
            EventPayloadSerializer serializer,
            Clock clock) {

        this.stocks = stocks;
        this.orders = orders;
        this.outbox = outbox;
        this.tenantAccess = tenantAccess;
        this.serializer = serializer;
        this.clock = clock;
    }

    @Transactional
    public OrderReceipt place(PlaceOrderCommand command) {
        String tenantId = tenantAccess.require(
            "ORDER_PLACE"
        );

        validate(command);

        // Nếu đã xử lý request này trước đó,
        // chỉ trả kết quả cũ khi intent tương ứng.
        var previous = orders.findByTenantIdAndRequestKey(
            tenantId,
            command.requestKey()
        );

        if (previous.isPresent()) {
            PurchaseOrder old = previous.get();
            requireSameIntent(old, command);

            return new OrderReceipt(
                old.getId(),
                old.getStatus().name()
            );
        }

        ProductStock stock = stocks
            .findByTenantIdAndSku(tenantId, command.sku())
            .orElseThrow(ProductNotFoundException::new);

        stock.reserve(command.quantity());

        PurchaseOrder order = PurchaseOrder.place(
            tenantId,
            command.requestKey(),
            command.sku(),
            command.quantity(),
            clock.instant()
        );

        orders.save(order);

        String payload = serializer.orderPlaced(order);

        outbox.save(new OutboxMessage(
            UUID.randomUUID(),
            "PurchaseOrder",
            order.getId().toString(),
            "OrderPlacedV1",
            payload,
            clock.instant()
        ));

        // Stock là managed; không bắt buộc save(stock).
        // DB commit xảy ra tại Spring transaction proxy.
        return new OrderReceipt(
            order.getId(),
            order.getStatus().name()
        );
    }

    private void validate(PlaceOrderCommand command) {
        if (command == null
                || command.sku() == null
                || command.sku().isBlank()
                || command.requestKey() == null
                || command.requestKey().isBlank()
                || command.quantity() <= 0) {

            throw new IllegalArgumentException(
                "Invalid PlaceOrderCommand"
            );
        }
    }

    private void requireSameIntent(
            PurchaseOrder previous,
            PlaceOrderCommand command) {

        if (!previous.getSku().equals(command.sku())
                || previous.getQuantity()
                    != command.quantity()) {
            throw new IdempotencyKeyConflictException();
        }
    }
}
~~~

**TenantAccess**, **EventPayloadSerializer** và các custom exception classes là application abstractions cần implement; code này minh họa cấu trúc service. Authorization nên xảy ra với identity đã xác thực, không tin tenant do client cung cấp.

Điều quan trọng là toàn bộ DB actions diễn ra **trong một transaction**:
- Stock reserve làm managed entity dirty;
- PurchaseOrder được persist;
- OutboxMessage được persist;
- Nếu một thao tác hoặc commit fail, toàn transaction rollback theo Spring transaction rules;
- Publisher ngoài transaction chỉ xử lý outbox records đã commit.

### 5.7. Hai request cùng requestKey

Pre-check findByTenantIdAndRequestKey không ngăn race:
1. A thấy requestKey chưa có;
2. B cũng thấy requestKey chưa có;
3. A và B cùng xử lý;
4. Một transaction commit;
5. Transaction kia có thể bị UNIQUE constraint từ chối.

Không bắt database constraint rồi cố tiếp tục cùng transaction lỗi. Bên ngoài transaction boundary có thể mở **transaction mới** để đọc lại requestKey, xác nhận same intent và trả kết quả đã commit theo idempotency policy.

### 5.8. Hai request khác requestKey nhưng tranh stock

Nếu hai transactions cùng đọc available=3 và đều muốn reserve 2, code đơn giản chỉ check available trong Java không đủ nếu DB isolation/versioning không bảo vệ lost update. **@Version** có thể giúp phát hiện một transaction stale và rollback, sau đó retry toàn use case (nếu an toàn) hoặc trả insufficient stock theo dữ liệu mới.

Một lựa chọn khác là pessimistic lock/atomic conditional UPDATE. Những quyết định này thuộc concurrency strategy, không phải reason để chuyển commit về StockRepository.

### 5.9. Không xuất thông điệp sự kiện trực tiếp giữa transaction

Sai:

~~~java
orders.save(order);
emailSender.sendOrderConfirmation(order); // Remote call.
outbox.save(message);
~~~

Nếu DB rollback sau khi email đã gửi, khách hàng nhận xác nhận cho đơn không tồn tại. Dùng outbox hoặc after-commit dispatch có policy rõ; outbox thường đáng tin hơn khi cần delivery sau crash.

## 6. Ai có thể sở hữu transaction boundary?

“Đặt transaction tại application service” là lựa chọn phổ biến, nhưng mục tiêu sâu hơn là **transaction thuộc về nơi biết rõ unit of work**. Những tổ chức code khác nhau có thể thực hiện mục tiêu đó.

### 6.1. Spring application service với @Transactional

~~~java
@Service
public class TransferService {

    @Transactional
    public TransferReceipt transfer(TransferCommand command) {
        // 1. Authorization
        // 2. Load accounts
        // 3. Domain transfer
        // 4. Save transfer record
        // 5. Outbox event
        // Commit sau khi proxy invocation hoàn thành.
    }
}
~~~

Ưu điểm: dễ đọc và ít boilerplate. Hạn chế: application service phụ thuộc Spring annotation, proxy semantics và Spring transaction manager configuration.

### 6.2. Một use-case executor/decorator

Khi application core không muốn phụ thuộc framework:

~~~java
public interface PlaceOrderUseCase {
    OrderReceipt place(PlaceOrderCommand command);
}
~~~

Core implementation điều phối business logic; infrastructure decorator bọc transaction:

~~~java
public final class TransactionalPlaceOrder
        implements PlaceOrderUseCase {

    private final PlaceOrderUseCase delegate;
    private final UnitOfWork unitOfWork;

    public TransactionalPlaceOrder(
            PlaceOrderUseCase delegate,
            UnitOfWork unitOfWork) {
        this.delegate = delegate;
        this.unitOfWork = unitOfWork;
    }

    @Override
    public OrderReceipt place(PlaceOrderCommand command) {
        return unitOfWork.inTransaction(
            () -> delegate.place(command)
        );
    }
}
~~~

Với interface:

~~~java
public interface UnitOfWork {
    <T> T inTransaction(Supplier<T> work);
}
~~~

**Supplier** thuộc java.util.function. Implementation UnitOfWork có thể dùng TransactionTemplate, JTA hoặc JPA resource-local. Decorator là nơi kỹ thuật mở/đóng giao dịch, còn use case vẫn sở hữu **semantic scope**: toàn bộ delegate.place là một business transaction.

### 6.3. TransactionTemplate cho điều phối tường minh

~~~java
public OrderReceipt place(PlaceOrderCommand command) {
    return transactionTemplate.execute(status -> {
        return orderCoordinator.placeInsideTransaction(command);
    });
}
~~~

TransactionTemplate mở/nhập transaction theo PlatformTransactionManager/propagation được cấu hình; commit/rollback ở cuối callback. Nếu có transaction ngoài, propagation mặc định REQUIRED có thể tham gia nó, không phải luôn mở transaction mới.

### 6.4. JTA/container-managed transaction

Trong ứng dụng Jakarta EE, transaction có thể do container quản lý; @Transactional của Jakarta Transactions (khác package Spring) có semantics riêng. Một unit of work có thể dùng JTA transaction manager nếu các resources được cấu hình đúng.

Không viết resource-local EntityTransaction.begin() bên trong JTA/container-managed transaction như thể hai cơ chế là một.

### 6.5. Batch step, message handler hoặc scheduler

Đôi khi nơi điều phối là:
- Spring Batch chunk writer/step;
- Message handler xử lý một command;
- Scheduled job xử lý một partition;
- Command handler trong CQRS;
- Use-case facade gọi nhiều domain/repository services.

Điều đúng là **sở hữu transaction theo một đơn vị công việc có thể nhận diện**, không bắt buộc class luôn mang tên Service.

### 6.6. Repository có thể có transaction metadata không?

Có. Một repository CRUD method cần transaction khi gọi độc lập, và Spring Data JPA có thể cấu hình CRUD transaction defaults. Tuy nhiên khi phối hợp nhiều repositories, **transaction ở caller cao hơn** giúp gộp các bước vào một commit.

Không đưa mặc định @Transactional lên repository rồi bỏ qua việc xác định business boundary ở application orchestration.

## 7. Spring @Transactional hoạt động như thế nào?

### 7.1. Spring proxy mở và kết thúc transaction

Trong Spring proxy-based setup thường gặp:

~~~text
Controller
   |
   v
Spring proxy của PlaceOrderService
   |
   +-- BEGIN / join transaction
   |
   v
PlaceOrderService.place() body
   |
   +-- Repository calls + managed changes
   |
   v
Return OrderReceipt
   |
   v
Spring transaction interceptor
   |
   +-- FLUSH/COMMIT hoặc ROLLBACK
   |
   v
Caller nhận result hoặc exception
~~~

**Commit xảy ra sau khi thân method return**, trong proxy transaction interceptor. Vì vậy catch block bên trong method body không nhất thiết bắt được exception chỉ xuất hiện lúc commit.

### 7.2. @Transactional mặc định

Trong Spring imperative transaction management:
- Propagation mặc định thường là REQUIRED;
- Isolation mặc định là DEFAULT, tức dùng lựa chọn của transaction manager/database;
- readOnly mặc định false;
- Timeout default theo transaction manager;
- RuntimeException và Error thường kích hoạt rollback mặc định;
- Checked Exception không tự rollback theo default rules, trừ khi cấu hình bổ sung.

Cần nhớ đó là **Spring transaction behavior**, không phải mặc định của Jakarta Persistence nói chung. Nâng cấp Spring có thể có options mới; điều quan trọng là biết rule của project.

### 7.3. REQUIRED tham gia transaction của caller

~~~java
@Transactional
public void placeOrder() {
    stockService.reserve();
    orderService.create();
}
~~~

Nếu reserve() và create() là Spring beans có methods @Transactional(REQUIRED) được gọi qua proxy, chúng **tham gia outer transaction**, không mỗi method commit độc lập.

Nếu outer method không có transaction, mỗi inner call có thể mở và commit transaction riêng, tạo partial commit risk.

### 7.4. TransactionManager phải đúng datasource

Nếu project có nhiều EntityManagerFactory hoặc datasources:
- Xác định transaction manager được chọn;
- Repositories nào gắn với persistence unit nào;
- Outer @Transactional có thực sự bao cả hai thao tác DB không;
- Nếu hai DB khác transaction managers, **một local transaction manager không tự atomic trên cả hai DB**.

Một annotation @Transactional không phải phép màu tạo distributed transaction trên mọi resource.

### 7.5. Không dùng @Transactional trên interface rồi bỏ qua runtime model

Spring có thể nhận transaction metadata từ interface hoặc implementation tùy cấu hình/proxy mode; behavior còn phụ thuộc version và enhancement mode. Quy ước rõ ràng thường là đặt annotation trên **concrete service methods/classes** ở nơi Spring thực sự quản lý.

### 7.6. Public method và proxy semantics

Với proxy mode, external calls tới proxied methods được intercept. Một lời gọi trực tiếp qua this hoặc new Service() có thể bypass proxy. Vì vậy không dựa vào chỉ việc method được annotate để suy transaction đã hoạt động.

### 7.7. Transaction context thường theo thread

Spring imperative/JPA transaction context thường gắn với thread hiện tại. Gọi @Async, CompletableFuture, thread pool hoặc scheduler trong method không tự mang transaction/JPA EntityManager sang thread mới.

Không share EntityManager giữa threads; không mong một Future chạy ở thread khác cùng tham gia transaction chỉ vì được tạo bên trong @Transactional method.

### 7.8. Reactive và imperative transactions khác nhau

Reactive transaction management trong Spring dùng Reactor context thay vì thread-bound imperative context. JPA EntityManager là API blocking/imperative. Không coi @Transactional reactive + JPA là tương đương Spring Data JPA imperative transaction; nếu dùng reactive stack, cần thiết kế resource/transaction model phù hợp.

## 8. Những lỗi proxy khiến transaction không ở nơi mong muốn

### 8.1. Self-invocation

~~~java
@Service
class OrderApplicationService {

    public void handle(PlaceOrderCommand cmd) {
        place(cmd); // Gọi trên cùng object.
    }

    @Transactional
    public void place(PlaceOrderCommand cmd) {
        // ...
    }
}
~~~

Trong proxy-based Spring, handle() gọi trực tiếp place() trên this có thể **không đi qua transaction interceptor**. Transaction của place không được mở chỉ vì có annotation.

Khắc phục:
- Đặt transaction annotation trên public method được caller bên ngoài gọi;
- Tách method transactional sang Spring bean khác và gọi qua proxy;
- Dùng TransactionTemplate cho explicit boundary;
- Dùng weaving mode phù hợp khi project đã chọn/kiểm thử.

### 8.2. Tự tạo service bằng new

~~~java
OrderApplicationService service =
    new OrderApplicationService(...);

service.place(command);
~~~

Object không phải Spring-managed proxy; transaction advice không chạy. Với Spring, inject bean do container quản lý.

### 8.3. Methods private/final và proxy restrictions

Proxy/JDK/CGLIB có những hạn chế về interceptability. Một method private hoặc final không thể được intercept theo cách proxy class-based thông thường; JDK interface proxy yêu cầu gọi qua interface. Hãy thiết kế transactional entrypoint rõ và test thật, không dựa vào một annotation đặt trên helper private.

### 8.4. Annotation trên helper thấp tầng không sửa outer orchestration

Một use case:

~~~java
public void checkout() {
    inventoryRepository.reduce(); // tx #1
    orderRepository.create();      // tx #2
}
~~~

Nếu outer checkout không transactional, chỉ gắn @Transactional lên hai methods không tạo all-or-nothing. Cần boundary bao **toàn checkout** nếu invariant yêu cầu cùng commit.

### 8.5. @Async bên trong transaction

~~~java
@Transactional
public void place(...) {
    orders.save(order);
    asyncEmailSender.send(order);
}
~~~

Một async task có thể chạy trước commit và không cùng transaction. Nó có thể thấy DB state chưa committed hoặc gửi email dù transaction rollback. Hãy dùng outbox/after-commit policy thay vì dựa vào thứ tự của thread scheduling.

### 8.6. Lazy response serialization sau transaction

Nếu service trả JPA entity, controller serializer có thể truy cập lazy fields sau transaction. Bật Open Session in View không phải lý do đặt transaction rộng đến tận response serialization. Thay bằng DTO/projection mapped trong read unit of work với fetch plan thích hợp.

### 8.7. Test transaction thật thay vì chỉ tìm annotation

Test cần chứng minh hai repository updates cùng rollback khi một bước fail, không chỉ dùng reflection assert @Transactional có mặt. Annotation có thể tồn tại nhưng không được proxy intercept trong runtime path thực tế.

## 9. Rollback rules: lỗi nào phải hủy unit of work?

### 9.1. Spring mặc định rollback đối với unchecked exceptions

~~~java
@Transactional
public void place(...) {
    stock.reserve(quantity);
    orders.save(order);

    throw new IllegalStateException("unexpected");
}
~~~

Nếu exception vượt qua transactional proxy, transaction thường rollback. Đây là default rollback rule Spring cho RuntimeException.

### 9.2. Checked exception cần policy rõ

~~~java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void place(...) throws BusinessCheckedException {
    // ...
}
~~~

Theo Spring defaults truyền thống, checked exception không tự kích hoạt rollback nếu không có rollback rule phù hợp. Nếu use case ném checked exception sau khi thay đổi DB và nghiệp vụ yêu cầu tất cả rollback, cấu hình rollbackFor hoặc xử lý transaction programmatically.

Spring cho phép cấu hình rollback rules toàn cục ở một số phiên bản; đừng chỉ dựa vào tên checked/unchecked nếu project có custom configuration.

### 9.3. Không bắt rồi nuốt exception

~~~java
@Transactional
public OrderReceipt place(...) {
    stock.reserve(2);

    try {
        orders.save(order);
    } catch (DataAccessException ex) {
        log.warn("Order save failed", ex);
    }

    return new OrderReceipt(...);
}
~~~

Code này có thể trả một result thành công trong khi transaction đã rollback-only hoặc database lỗi. Không dùng catch-and-continue khi state chưa biết.

Nếu cần map technical exception sang domain/application failure, giữ cause và **throw** exception phù hợp để transaction manager rollback.

### 9.4. Catch rồi throw custom exception

~~~java
try {
    orders.save(order);
} catch (DataIntegrityViolationException ex) {
    throw new OrderConflictException(ex);
}
~~~

Nếu OrderConflictException extends RuntimeException và lỗi thật xảy ra bên trong try, Spring thường rollback. Nhưng có lỗi **chỉ xuất hiện ở commit** sau khi method body đã return, nên catch ở đây không bắt được mọi constraint violation. Error mapping cần có outer boundary phù hợp.

### 9.5. Set rollback-only khi cố ý không throw ngay

Trong một số flows Spring có thể:

~~~java
TransactionAspectSupport.currentTransactionStatus()
    .setRollbackOnly();
~~~

Nhưng đây là Spring-specific API và phụ thuộc đang ở transaction được interceptor quản lý. Dùng khi cần chủ động đánh dấu rollback trong một protocol rõ ràng; không biến thành thói quen cho mọi repository. Một đường điều phối dễ hiểu thường throw application exception và để boundary rollback.

### 9.6. UnexpectedRollbackException

Nếu một inner REQUIRED participant đánh dấu shared transaction rollback-only, nhưng outer method bắt lỗi rồi return như success, tại outer commit Spring có thể ném **UnexpectedRollbackException**.

~~~text
Outer transaction BEGIN
  Inner REQUIRED:
    failure → mark rollback-only
  Outer:
    catches failure
    returns "success"
Outer commit:
  rollback instead → UnexpectedRollbackException
~~~

Không coi UnexpectedRollbackException là lỗi thứ hai không liên quan; nó thường phản ánh việc code cố commit một transaction đã bị đánh dấu rollback-only.

### 9.7. Trạng thái JPA context sau flush error

Nếu flush fail (UNIQUE, FK, deadlock, optimistic conflict):
- Transaction có thể rollback-only;
- DB transaction có thể bị abort;
- Managed entity state có thể không còn phản ánh DB state có thể commit;
- Một lần em.clear không khôi phục transaction;
- Nếu retry, cần transaction và context mới.

Không tiếp tục vòng lặp ghi trong transaction lỗi chỉ vì đã bắt được exception.

### 9.8. Error không tự chứng minh transaction đã rollback

Một connection loss gần COMMIT có thể làm caller không biết DB đã commit hay chưa. Với operation quan trọng, reconciliation/idempotency quyết định hướng xử lý. Không blind retry payment hoặc order chỉ vì JDBC exception xuất hiện.

## 10. Propagation: khi method giao dịch gọi method giao dịch khác

Spring định nghĩa propagation để quyết định lời gọi mới **tham gia**, **mở mới**, **tạm ngưng** hay **yêu cầu** transaction. Chọn propagation không chỉ là tối ưu kỹ thuật; nó thay đổi atomicity của business workflow.

### 10.1. REQUIRED: mặc định phổ biến

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void placeOrder(...) {
    // ...
}
~~~

- Nếu đã có transaction, method tham gia.
- Nếu chưa có, transaction mới được mở.

Đây thường là lựa chọn cho repository/application service participants nằm bên trong một use case transaction lớn.

### 10.2. REQUIRES_NEW: transaction độc lập

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAttempt(...) {
    // ...
}
~~~

- Tạm đình chỉ transaction hiện tại nếu có;
- Mở transaction mới;
- Commit/rollback riêng;
- Sau đó quay lại transaction ngoài.

Điều này **có thể phá all-or-nothing** nếu dùng nhầm:

~~~text
Outer PlaceOrder tx A:
  reserve stock
  REQUIRES_NEW create order tx B → COMMIT B
  outbox fails → ROLLBACK A

Order đã commit nhưng stock reserve bị rollback.
~~~

Đó là một dữ liệu không nhất quán nếu mô hình yêu cầu đơn hàng và stock cùng atomic.

### 10.3. REQUIRES_NEW cũng tăng áp lực connection pool

Một outer transaction có thể đang giữ JDBC connection; khi inner REQUIRES_NEW bắt đầu có thể cần connection khác. Nếu nhiều threads đều giữ outer connections và chờ inner connections, pool starvation hoặc deadlock-like resource contention có thể xảy ra.

Dùng REQUIRES_NEW **chỉ khi commit độc lập là ý định nghiệp vụ thật**, ví dụ audit attempt được phép tồn tại dù main transaction rollback. Đối với security/audit có yêu cầu lưu bền vững, cân nhắc semantics, failure modes, consistency và capacity.

### 10.4. NESTED: savepoint, không mặc nhiên transaction commit độc lập

~~~java
@Transactional(propagation = Propagation.NESTED)
public void attemptOptionalStep(...) {
    // ...
}
~~~

Với transaction manager hỗ trợ savepoints, NESTED có thể tạo nested scope rollback về savepoint trong một physical transaction. Khi outer transaction rollback, nested work đã “thành công” vẫn rollback cùng outer.

- **NESTED khác REQUIRES_NEW**;
- Không phải mọi JPA transaction manager/provider setup hỗ trợ savepoint cho mọi thao tác JPA;
- Một số state của persistence context sau JDBC savepoint rollback có thể không tự đồng bộ;
- Cần integration test theo đúng PlatformTransactionManager/driver.

Không dùng NESTED như một lối tắt để bỏ qua JPA flush exceptions rồi tiếp tục nếu EntityManager/context không còn usable.

### 10.5. MANDATORY

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void appendOutbox(...) {
    // ...
}
~~~

Yêu cầu transaction đã tồn tại; nếu không có sẽ lỗi. Có thể hữu ích ở một adapter/method **không được phép chạy độc lập**, ví dụ ghi outbox bắt buộc cùng transaction business.

Nhưng @Transactional(MANDATORY) trên tất cả repository methods không tự xác định nghiệp vụ hay hỗ trợ các read-only callers. Cần cân nhắc contract và framework.

### 10.6. SUPPORTS

Nếu caller có transaction thì tham gia, nếu không thì thực thi không có transaction thực theo manager semantics.

Có thể phù hợp một số read operations, nhưng không dùng cho writes cần atomicity nếu thiếu transaction.

### 10.7. NOT_SUPPORTED và NEVER

- **NOT_SUPPORTED:** chạy không có transaction, tạm ngưng transaction đang tồn tại.
- **NEVER:** từ chối nếu có transaction.

Một remote/long-running task đôi khi cần tách khỏi DB transaction, nhưng không nên gọi NOT_SUPPORTED trong một service ghi nhiều DB tables cần atomic chỉ để tránh lock.

### 10.8. Bảng so sánh propagation

| Propagation | Khi caller không có tx | Khi caller có tx | Vấn đề chính |
|---|---|---|---|
| REQUIRED | Mở tx | Tham gia tx | Phù hợp atomic use case |
| REQUIRES_NEW | Mở tx | Độc lập, suspend outer | Phá atomicity nếu lạm dụng |
| NESTED | Tạo tx khi phù hợp | Savepoint nếu manager hỗ trợ | Không phải commit độc lập |
| MANDATORY | Lỗi | Tham gia | Dành cho participant bắt buộc |
| SUPPORTS | Không cần tx | Tham gia | Writes có thể thiếu tx |
| NOT_SUPPORTED | Không có tx | Suspend outer | Break transactional scope |
| NEVER | Chạy không tx | Lỗi | Ngăn tham gia transaction |

### 10.9. Propagation thay đổi khái niệm “success”

Một inner REQUIRES_NEW commit rồi outer rollback: inner success vẫn còn trong DB. Một inner NESTED scope thành công rồi outer rollback: thay đổi nested thường vẫn bị rollback. Vì vậy cần ghi rõ **commit scope** trong code review, không chỉ thấy một annotation.

### 10.10. Không lạm dụng REQUIRES_NEW để “sửa” rollback-only

Nếu outer transaction bị lỗi, mở REQUIRES_NEW và tiếp tục commit một vài records không tự bảo đảm business consistency. Có thể phù hợp với incident log hoặc compensation intent, nhưng phải là một phần của failure workflow được thiết kế, không dùng tùy tiện để làm cho lỗi biến mất.

## 11. Isolation: transaction boundary đúng vẫn chưa đủ cho concurrency

Local ACID transaction bảo đảm atomicity trong một DB, nhưng **isolation level** quyết định tương tác giữa concurrent transactions. Đặt đúng boundary chưa tự chống lost updates, write skew, phantom rows hoặc duplicate requests.

### 11.1. Một ví dụ lost update

Tồn kho ban đầu available=3.

~~~text
Tx A                            Tx B
----                            ----
Read stock=3                    Read stock=3
Reserve 2 → local=1             Reserve 2 → local=1
UPDATE stock=1                  UPDATE stock=1
COMMIT                          COMMIT
~~~

Nếu không có concurrency control phù hợp, database có thể kết thúc available=1 dù đã nhận hai đơn tổng cộng 4 món, vi phạm quy tắc tồn kho.

### 11.2. @Version giúp phát hiện stale write

~~~java
@Version
private Long version;
~~~

Provider thường gắn version vào UPDATE condition/dirty checking, và một transaction stale có thể fail optimistic lock. Khi fail, rollback toàn use case: order/outbox cũng không commit.

**Không chỉ retry riêng câu UPDATE stock** nếu business decision đã dựa vào dữ liệu cũ. Khi retry cần reread stock, kiểm tra lại điều kiện và ghi đơn trong **transaction mới**.

### 11.3. Pessimistic lock

Một repository có thể dùng JPA LockModeType:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("""
    select s
    from ProductStock s
    where s.tenantId = :tenantId
      and s.sku = :sku
    """)
Optional<ProductStock> lockForOrder(
    @Param("tenantId") String tenantId,
    @Param("sku") String sku
);
~~~

Pessimistic lock có thể giảm concurrent modifications cho một row, nhưng:
- Cần transaction active;
- Có thể gây lock waits/deadlocks;
- Timeout semantics khác nhau theo DB/provider;
- Không thay permission/tenant checks;
- Long transaction giữ locks lâu hơn;
- Không tự bảo vệ multi-row invariants thiếu khóa cần thiết.

### 11.4. Atomic conditional UPDATE

Một chiến lược khác là update có predicate:

~~~sql
UPDATE product_stocks
SET available = available - :qty,
    version = version + 1
WHERE tenant_id = :tenant
  AND sku = :sku
  AND available >= :qty;
~~~

Sau đó kiểm tra affected row count. Đây là SQL mẫu DB-specific nếu thực hiện bằng native query; khi chạy ngoài managed entity lifecycle phải cân nhắc **@Version, persistence context stale và các đường ghi khác**.

Dù chọn locking strategy nào, transaction ở nơi điều phối cần bao cả phần tạo đơn/outbox liên quan.

### 11.5. Spring isolation settings

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void placeOrder(...) {
    // ...
}
~~~

Isolation.READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE, v.v. chỉ có ý nghĩa theo transaction manager và database thực tế; không giả định cùng isolation name có mọi hiện tượng giống nhau trên các DBMS.

Khi method REQUIRED tham gia existing transaction, việc đặt isolation mới trên inner method **không mặc nhiên nâng isolation của physical transaction**.

### 11.6. Isolation.DEFAULT và database defaults

Spring Isolation.DEFAULT dùng lựa chọn của transaction manager/database, không nhất thiết READ_COMMITTED ở mọi DB. Đừng ghi nhận một default isolation chung khi chưa biết configured DB.

### 11.7. SERIALIZABLE không loại bỏ nhu cầu retry

Isolation mạnh hơn có thể khiến database từ chối một transaction bằng serialization failure. Application cần rollback và cân nhắc **bounded retry toàn business unit of work** từ state mới, nếu operation idempotent/safe.

### 11.8. Đọc nhiều rows và write skew

Một invariant “ít nhất một bác sĩ trực” có thể bị phá nếu hai transactions độc lập cùng đọc thấy hai bác sĩ đang trực rồi mỗi transaction tắt một người; row-level @Version riêng từng entity không nhất thiết ngăn trường hợp mỗi transaction sửa hai rows khác nhau.

Cần domain-specific concurrency strategy:
- SERIALIZABLE và retry;
- Lock shared coordination row;
- Database constraints/aggregate design;
- Atomic SQL/optimistic strategy cho tập liên quan.

Một transaction boundary đúng vẫn cần isolation/locking phù hợp.

### 11.9. Lock ordering

Hai transactions cập nhật nhiều ProductStocks theo thứ tự khác nhau có thể deadlock:

~~~text
Tx A: lock SKU-A → chờ SKU-B
Tx B: lock SKU-B → chờ SKU-A
~~~

Nên lock rows theo **thứ tự ổn định**, giữ transaction ngắn, hạn chế remote calls và dùng bounded retry nếu DB báo deadlock.

### 11.10. Transaction boundary và tenant isolation

Trong multi-tenant application, query trong transaction phải scope đúng tenant. @Transactional không tự bảo đảm row-level authorization. Một transaction có thể atomic nhưng vẫn cập nhật nhầm dữ liệu tenant khác nếu repository query thiếu filter.

## 12. Read transactions, consistency và DTO

### 12.1. Đọc một entity

Một simple GET có thể dùng:

~~~java
@Transactional(readOnly = true)
public ProductView getProduct(
        String tenantId, Long productId) {

    Product product = products
        .findByIdAndTenantId(productId, tenantId)
        .orElseThrow(ProductNotFoundException::new);

    return new ProductView(
        product.getId(),
        product.getName(),
        product.getPrice()
    );
}
~~~

DTO được tạo trong transactional read boundary; không để controller serialize lazy JPA entity graph ngoài transaction.

### 12.2. readOnly là hint, không phải authorization

Spring @Transactional(readOnly=true) là một hint/cấu hình cho framework/transaction manager; mức enforce có thể khác theo DB/provider. Đừng coi nó là security control hoặc cam kết mọi write đều bị từ chối ở mọi hệ.

### 12.3. Khi cần snapshot nhất quán

Một báo cáo:
1. Query tổng tiền đơn;
2. Query số đơn;
3. Query danh sách chi tiết.

Nếu ba queries cần cùng snapshot, phải chọn transaction/isolation hoặc reporting snapshot strategy phù hợp. Không chỉ gắn readOnly rồi kỳ vọng các queries cùng nhìn thấy dữ liệu từ một thời điểm trên mọi isolation level.

### 12.4. Read consistency khác strong consistency của toàn hệ

Nếu báo cáo tổng hợp từ hai databases/microservices, một local JPA read transaction không tự tạo snapshot nhất quán xuyên hai resources. Cần chọn consistency model, event lag reconciliation hoặc distributed transaction mechanism nếu thật sự cần.

### 12.5. Query DTO projection giảm footprint

Một read service có thể query trực tiếp DTO/projection thay vì load toàn entity graph, giảm N+1 và tránh leak fields không cần. Nhưng tenant/permission filters vẫn cần trong query.

### 12.6. Không kéo read transaction xuyên remote calls

Nếu một REST endpoint đọc DB rồi gọi recommendation service mất vài giây, có thể tách DB read phase ngắn và remote call bên ngoài transaction nếu consistency model cho phép. Không giữ connection/snapshot trong lúc chờ remote service chỉ để tiết kiệm một lời gọi service.

### 12.7. Read-modify-write khác read-only query

Một use case đọc stock rồi trừ stock là **write transaction** dù bắt đầu bằng SELECT. Không đánh dấu readOnly=true cho workflow đó chỉ vì phần đầu là read.

### 12.8. Open Session in View không định nghĩa use-case transaction

OSIV có thể giữ persistence context mở qua view/serialization, nhưng transaction có thể đã kết thúc. Nó không thay @Transactional ở nơi điều phối và có thể gây queries ngoài unit of work, N+1 hoặc lazy loading không kiểm soát. DTO mapping trong read boundary thường rõ hơn.

## 13. JPA resource-local: application tự đặt begin/commit/rollback

Nếu không dùng Spring/JTA, ứng dụng có thể tạo EntityManager và tự quản lý EntityTransaction. Điều này giúp thấy trực tiếp **transaction boundary** bao quanh nhiều repository operations.

### 13.1. Một unit of work với EntityManager dùng chung

~~~java
public OrderReceipt placeResourceLocal(
        EntityManagerFactory emf,
        PlaceOrderCommand command,
        String authorizedTenantId,
        EventPayloadSerializer serializer,
        Clock clock) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        ProductStock stock = em.createQuery(
            """
            select s
            from ProductStock s
            where s.tenantId = :tenant
              and s.sku = :sku
            """,
            ProductStock.class
        )
        .setParameter("tenant", authorizedTenantId)
        .setParameter("sku", command.sku())
        .getSingleResult();

        stock.reserve(command.quantity());

        PurchaseOrder order = PurchaseOrder.place(
            authorizedTenantId,
            command.requestKey(),
            command.sku(),
            command.quantity(),
            clock.instant()
        );
        em.persist(order);

        em.persist(new OutboxMessage(
            UUID.randomUUID(),
            "PurchaseOrder",
            order.getId().toString(),
            "OrderPlacedV1",
            serializer.orderPlaced(order),
            clock.instant()
        ));

        em.flush();
        tx.commit();

        return new OrderReceipt(
            order.getId(),
            order.getStatus().name()
        );
    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
~~~

Đoạn code yêu cầu resource-local persistence unit, classes/imports tương ứng và các custom business exceptions; **không thay thế** validation, authorization, idempotency handling hoặc retry policy. Mục đích chính là nhìn thấy:
- **Một EntityManager** theo unit of work;
- **Một transaction** bao cả stock/order/outbox;
- **Một commit**;
- **Rollback khi lỗi**;
- **Đóng EntityManager** trong finally.

### 13.2. Không tạo EntityManager độc lập mỗi repository call rồi tự commit

Sai về consistency nếu các writes phải atomic:

~~~java
public void reserveStock() {
    EntityManager em = emf.createEntityManager();
    em.getTransaction().begin();
    // update stock
    em.getTransaction().commit();
    em.close();
}

public void saveOrder() {
    EntityManager em = emf.createEntityManager();
    em.getTransaction().begin();
    // insert order
    em.getTransaction().commit();
    em.close();
}
~~~

Đây là hai transactions riêng, dù cùng datasource. Cần **cùng unit-of-work context/transaction** cho atomic workflow.

### 13.3. Repository có thể nhận EntityManager từ UnitOfWork

Một kiến trúc resource-local có thể:
1. UnitOfWork mở EntityManager;
2. Tạo repository adapters gắn vào EntityManager đó;
3. Application use case gọi adapters;
4. UnitOfWork flush/commit/rollback;
5. Đóng context.

Không để từng adapter tự quyết định commit nếu outer use case phải phối hợp atomicity.

### 13.4. Không share EntityManager giữa threads

JPA EntityManager không thread-safe. Mỗi request/job attempt cần transaction/context phù hợp. Không giữ một static EntityManager rồi dùng chung cho toàn app.

### 13.5. Resource-local không phải JTA

Với JTA-managed EntityManager, gọi em.getTransaction().begin() không hợp lệ theo JPA semantics; transaction do container/JTA transaction manager quản lý. Chọn đúng một mô hình dựa trên deployment.

### 13.6. Đừng auto-commit sau mọi repository operation

Nếu adapter tự kiểm tra “không có transaction thì begin + commit” ở mỗi save, một use case quên outer boundary sẽ chạy partial commits mà không báo lỗi rõ. Một transaction port/MANDATORY contract hoặc guardrail ở use-case invocation giúp phát hiện misuse sớm.

## 14. JTA và nhiều persistence units/databases

### 14.1. Một local database transaction có phạm vi cụ thể

Nếu StockRepository dùng DataSource A và OrderRepository dùng DataSource B, transaction manager gắn với A không tự rollback SQL trên B. Một @Transactional trên service có thể khiến developer tưởng mọi DB write được bảo vệ, nhưng thực tế phụ thuộc transaction infrastructure.

### 14.2. JTA/XA cho distributed atomic transactions

Trong các hệ có XA-capable resources, JTA có thể điều phối distributed transaction theo cơ chế chuẩn bị/commit (ví dụ two-phase commit). Nhưng cần:
- XA-capable JDBC datasources/resource managers;
- Transaction manager hỗ trợ;
- Recovery logs;
- Timeout/resource enlistment đúng;
- Vận hành in-doubt transactions;
- Hiểu overhead và failure modes.

JTA không tự biến HTTP payment gateway hoặc một API SaaS thành XA participant.

### 14.3. Hai EntityManagerFactories với hai local managers

~~~text
PlaceOrderService @Transactional(managerA)
  |
  +-- Stock JPA (DB A)  → nằm trong tx A
  |
  +-- Order JPA (DB B)  → có thể dùng tx B khác
~~~

Không suy đồng nhất atomicity. Nếu cần thay đổi trên hai DB mà không có distributed transaction, cân nhắc redesign ownership, outbox, saga hoặc eventual consistency.

### 14.4. Một database với nhiều schemas vẫn cần xác minh scope

Hai repositories có thể dùng hai schemas trong cùng database nhưng khác datasources/EntityManagerFactories. Atomicity thực tế phụ thuộc connection/transaction manager và cách enlist resources, không chỉ việc hai JDBC URLs cùng host.

### 14.5. Nơi điều phối có thể sở hữu một saga thay vì một transaction

Khi workflow thực sự bao nhiều services/databases, một **saga/workflow coordinator** quản lý các steps, compensations và idempotency; mỗi step có **local transaction** riêng ở service owner tương ứng.

Đó vẫn là “đặt boundary nơi điều phối phù hợp”, nhưng boundary được tổ chức ở **cấp step**, không giữ một database transaction qua mọi bước.

## 15. Repository contract nên thể hiện điều gì?

### 15.1. Repository không nên biến thành lớp điều phối nghiệp vụ

Một interface tốt:

~~~java
public interface PurchaseOrderRepository {
    Optional<PurchaseOrder> findByRequestKey(
        String tenantId,
        String requestKey
    );

    PurchaseOrder save(PurchaseOrder order);
}
~~~

Nó mô tả đọc/ghi aggregate. Nó không cần gọi StockRepository, gửi email, định tuyến payment, hoặc commit một transaction cho cả workflow.

### 15.2. Tránh repository tự commit trong helper

Sai:

~~~java
public void saveAndCommit(PurchaseOrder order) {
    em.persist(order);
    em.flush();
    em.getTransaction().commit();
}
~~~

Một helper như vậy phá khả năng orchestration cùng Stock/Outbox, và còn không hợp lệ nếu em do container-managed/JTA/Spring quản lý.

### 15.3. Tên saveAndFlush không nói commit

Spring Data JPA có saveAndFlush, nhưng **flush không phải commit**. Nó có thể giúp đưa SQL tới DB sớm để phát hiện constraint error, song vẫn nằm trong active transaction và có thể rollback.

### 15.4. Spring Data default transactions

Spring Data JPA repositories thường có default transaction configuration cho inherited CRUD methods, trong khi query methods tự khai báo có thể cần @Transactional riêng nếu transaction semantics yêu cầu.

Trong một transaction tại application service, repository call thường tham gia outer transaction nếu propagation tương ứng. Không dựa vào defaults của từng repository để đạt multi-repository atomicity.

### 15.5. Transaction annotations không phải domain semantics

Một method:

~~~java
@Transactional
public void saveOrder(PurchaseOrder order) {
    // ...
}
~~~

nói về transaction mechanism, nhưng không tự cho biết **business invariant nào yêu cầu atomic**. Use-case coordinator là nơi viết và document mục tiêu “stock reserve + order + outbox cùng commit”.

### 15.6. Repository có thể giữ atomic SQL primitive

Có những thao tác dữ liệu thực sự cần atomic ở một statement, ví dụ:

~~~java
int decrementIfAvailable(
    String tenantId,
    String sku,
    int quantity
);
~~~

Repository adapter có thể implement bằng conditional UPDATE, nhưng điều đó **không chuyển quyền sở hữu outer transaction** từ use-case coordinator sang repository. Primitive atomic giúp bảo vệ một invariant cục bộ; coordinator vẫn gắn nó với Order và Outbox trong transaction chung.

### 15.7. Repository trả gì khi lỗi?

Một repository có thể propagate JPA/provider exception để infrastructure boundary dịch thành stable application failure. Không nên:
- Catch mọi exception rồi trả Optional.empty;
- Trả null khi database unavailable;
- Tự rollback outer transaction rồi tiếp tục như thành công;
- Thay SQL integrity violation bằng một NoResultException giả.

Để application quyết định recovery, phân biệt **business missing result** với **persistence failure**.

### 15.8. Repository port và @Transactional

Nếu domain/application core dùng repository interface thuần Java, có thể tránh đưa @Transactional annotation xuống port. Transaction boundary ở application adapter/decorator theo use case.

Trong Spring Data JPA application trực tiếp dùng repository interfaces, transaction metadata có thể vẫn hiện diện. Điều quan trọng là không để các annotations tạo ra các **commits không mong muốn** và không giả định annotations bên trong tự đủ cho toàn workflow.

## 16. Outbox: giữ DB atomic, đưa side effect ra ngoài transaction

### 16.1. Tại sao gửi message ngay trong transaction nguy hiểm?

~~~java
@Transactional
public OrderReceipt place(...) {
    orders.save(order);
    kafkaTemplate.send("orders", event); // Không phải DB COMMIT.
    return receipt;
}
~~~

Nếu Kafka nhận message rồi DB rollback, consumer có thể xử lý một Order không tồn tại. Ngược lại DB commit nhưng broker send fail khiến workflow thiếu event.

### 16.2. Transactional outbox

~~~text
PlaceOrder transaction
  |
  +-- UPDATE stock
  +-- INSERT order
  +-- INSERT outbox
  |
  COMMIT
        |
        v
Publisher đọc outbox rows đã commit
        |
        v
Gửi Kafka / message broker
        |
        v
Mark published / retries
~~~

Outbox row cùng transaction với entity changes bảo đảm **khi database commit, intent phát event cũng được lưu**. Publisher có thể gửi lại sau crash.

### 16.3. Outbox không bảo đảm message chỉ được gửi một lần

Một publisher:
1. Gửi message thành công;
2. Crash trước khi mark outbox row published;
3. Restart;
4. Gửi lại message.

Consumer cần idempotency/deduplication theo eventId. Outbox thường mang lại **at-least-once delivery**, không tự bảo đảm exactly-once processing qua mọi hệ.

### 16.4. Không xuất JPA entity trong payload

Dùng event DTO:

~~~java
public record OrderPlacedEventV1(
    UUID eventId,
    UUID orderId,
    String tenantId,
    String sku,
    int quantity,
    Instant occurredAt
) {}
~~~

Phải chọn fields theo trust boundary của consumer, tránh dữ liệu nhạy cảm không cần và version event schema. Outbox không tự cấp quyền hoặc bảo vệ PII.

### 16.5. Publisher không giữ transaction nơi đặt hàng mở

Publisher chạy sau commit trong workflow riêng. Không chờ Kafka acknowledgement trong PlaceOrder @Transactional method, vì điều đó kéo dài DB transaction và làm failure coupling phức tạp.

### 16.6. Có thể dùng after-commit callback không?

Spring có transaction synchronization/transactional event listener theo phase. Sau commit có thể dispatch một notification không quá quan trọng, nhưng có failure gap:
- DB commit thành công;
- Process crash trước khi callback gửi message.

Nếu yêu cầu **durable event delivery**, outbox tốt hơn một in-memory after-commit callback đơn thuần.

### 16.7. Không xử lý outbox như lệnh gọi repository commit độc lập

Nếu OutboxRepository tự REQUIRES_NEW và commit trước/khác với Order transaction, outbox row có thể tồn tại mà order chưa được commit hoặc bị rollback. Bản chất outbox là **cùng atomic transaction**, không phải chỉ có một bảng tên outbox.

## 17. Workflow dài, Saga và compensation

### 17.1. Không giữ local transaction trong khi gọi hệ thống ngoài

Một order fulfillment flow:

~~~text
PlaceOrder
   |
   v
DB transaction A:
  reserve stock
  create order PENDING_PAYMENT
  write outbox
  COMMIT
   |
   v
Payment worker gọi payment gateway
   |
   +-- Thành công:
   |      DB transaction B:
   |        mark PAID
   |        write outbox
   |        COMMIT
   |
   +-- Thất bại:
          DB transaction C:
            release stock reservation
            mark PAYMENT_FAILED
            write outbox
            COMMIT
~~~

Ở đây mỗi local transaction giữ invariant của một step. Toàn workflow không ACID trong một transaction, nhưng có state machine và compensation.

### 17.2. Compensation không giống rollback

Nếu transaction A đã commit, không thể gọi tx.rollback() trong transaction C để hủy A. Compensation là **business action mới** như release reservation hoặc refund, và cũng có thể fail/retry.

Cần xem:
- Compensation có idempotent không;
- Có xảy ra sau một trạng thái mới không;
- Có audit đầy đủ không;
- Có tránh hoàn tiền hai lần không;
- Có xử lý manual intervention không.

### 17.3. Saga orchestration và choreography

- **Orchestration:** một workflow coordinator điều phối steps, lưu state/retries, kích hoạt compensation.
- **Choreography:** các services phản ứng với events và local state transitions.

Cả hai đều cần local transaction ownership rõ ở từng service; không dùng một @Transactional xuyên service calls để giả định distributed atomicity.

### 17.4. Step status cần bền vững

Nếu worker gửi payment request rồi crash trước khi nhận response, outcome có thể không rõ. Cần paymentId/idempotency key, query provider status, retries có giới hạn và reconciliation. Một local DB transaction không thể loại bỏ ambiguity của network.

### 17.5. Transaction boundary của outbox consumer

Consumer xử lý OrderPaid event:
1. Kiểm tra eventId đã xử lý chưa;
2. Load Order/tenant scope;
3. Áp domain transition nếu hợp lệ;
4. Save state;
5. Ghi processed-event marker/outbox khác nếu cần;
6. Commit;
7. Ack message theo broker policy.

Nếu ack trước commit, message có thể mất khi DB fail. Nếu commit trước ack rồi process crash, message có thể được giao lại. **Idempotency** xử lý duplicate delivery.

### 17.6. Không chạy external side effects trong JPA lifecycle callbacks

@PrePersist/@PostPersist/@PostUpdate có thể chạy trước commit hoặc khi flush; chúng không phải signal chắc chắn database đã commit. Gửi email/payment từ entity listener có thể tạo side effect ngay cả khi transaction rollback. Dùng domain events + outbox/after-commit workflow phù hợp.

### 17.7. Transaction decorator cho workflow steps

Một application core có thể expose:
- PlaceOrderUseCase (local transaction A);
- RecordPaymentResultUseCase (local transaction B);
- ReleaseReservationUseCase (local transaction C).

Mỗi use case có transaction decorator/annotation riêng. Saga coordinator không cần giữ một transaction mở trong suốt thời gian chờ payment.

## 18. Batch jobs: transaction per chunk khi nghiệp vụ cho phép

### 18.1. Một transaction cho toàn bộ 1 triệu rows có thể quá dài

JPA persistence context giữ managed entities; database transaction giữ locks/log/snapshot theo DB semantics. Một import 1 triệu ProductUpdates trong một @Transactional method có thể tiêu thụ nhiều memory, kéo dài transaction và làm rollback tốn kém.

### 18.2. Chunk-oriented processing

~~~text
Job coordinator (không có outer tx kéo dài)
   |
   +-- Chunk#1 → transaction A → commit
   |
   +-- Chunk#2 → transaction B → commit
   |
   +-- Chunk#3 → transaction C → rollback nếu lỗi
   |
   +-- checkpoint / resume
~~~

Đây là **partial commit by design**. Nếu business yêu cầu all-or-nothing toàn file, chiến lược này không phù hợp nếu không có staging/finalization hoặc compensation model khác.

### 18.3. Spring service tách thành coordinator và writer

~~~java
@Service
public class ImportCoordinator {

    private final ProductChunkWriter writer;

    public ImportCoordinator(ProductChunkWriter writer) {
        this.writer = writer;
    }

    public long run(Iterator<ProductInput> source, int chunkSize) {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize");
        }

        long committed = 0;

        while (source.hasNext()) {
            List<ProductInput> chunk = new ArrayList<>();

            while (source.hasNext()
                    && chunk.size() < chunkSize) {
                chunk.add(source.next());
            }

            committed += writer.writeChunk(chunk);
        }

        return committed;
    }
}
~~~

Writer ở bean khác:

~~~java
@Service
public class ProductChunkWriter {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int writeChunk(List<ProductInput> inputs) {
        for (ProductInput input : inputs) {
            em.persist(Product.from(input));
        }

        em.flush();
        return inputs.size();
    }
}
~~~

Ví dụ giả định Product.from(input) được định nghĩa theo domain/validation. Khi gọi qua Spring proxy và **không có outer transaction đang hoạt động**, mỗi writeChunk invocation có thể commit transaction riêng.

### 18.4. @Transactional ở coordinator sẽ đổi semantics

Nếu coordinator.run cũng @Transactional(REQUIRED), từng writer.writeChunk(REQUIRED) có thể **tham gia transaction coordinator** thay vì commit từng chunk, trái kỳ vọng.

Không chỉ nhìn mỗi annotation ở writer; cần xác định physical transaction thật và test partial commits.

### 18.5. TransactionTemplate cho mỗi chunk

Một coordinator có thể dùng TransactionTemplate.execute mỗi chunk thay vì gọi bean @Transactional. Nhưng propagation REQUIRED vẫn có thể join outer transaction nếu đã tồn tại. Chọn transaction policy theo business và bảo đảm caller không bọc một outer transaction không mong muốn.

### 18.6. flush/clear không tạo commit-per-chunk

~~~java
em.persist(...);
em.flush();
em.clear();
~~~

vẫn là một transaction nếu không có commit/transaction boundary mới. Flush chỉ đồng bộ pending SQL, clear detach managed entities. Không trình bày chúng như checkpoint bền vững.

### 18.7. Checkpoint và idempotency

Đối với chunk imports dài:
- Có importRunId và chunkId;
- Checkpoint sau commit hoặc trong cùng DB transaction;
- Unique constraints chống duplicate;
- File/source version cố định;
- Xử lý commit outcome unknown;
- Quarantine row invalid;
- Retry transient failures trong transaction mới.

Một exception ở chunk thứ 20 không tự rollback 19 chunks đã commit trước đó.

### 18.8. Spring Batch có transaction ownership riêng

Spring Batch hỗ trợ item reader/processor/writer và chunk transaction boundaries theo step configuration. Khi dùng framework này, phải hiểu nó đang sở hữu **transaction của chunk**, tránh thêm một outer @Transactional không hợp lý hoặc REQUIRES_NEW làm lệch skip/retry semantics.

## 19. Message handlers: transaction và acknowledgment

### 19.1. Một message là một unit of work khả dĩ

~~~text
Receive OrderRequested event
  |
  v
Validate source + eventId
  |
  v
BEGIN DB transaction
  - check processed-event key
  - reserve stock
  - create order
  - insert outbox
  - mark event processed
COMMIT
  |
  v
ACK broker message
~~~

Một message có thể được giao lại sau crash. Cần **idempotency theo event ID**, không chỉ transaction.

### 19.2. Ack trước commit có nguy cơ mất dữ liệu

Nếu consumer ack rồi DB commit fail, message có thể đã biến mất khỏi broker nhưng effect không có trong database.

### 19.3. Ack sau commit có thể sinh duplicate delivery

Nếu DB commit rồi process crash trước ack, broker giao lại. Dùng UNIQUE(processed_event_id) hoặc equivalent dedupe check trong cùng DB transaction.

### 19.4. Broker transaction không tự đồng bộ với JPA transaction

Kafka transaction hoặc AMQP acknowledgment có semantics riêng. Không mặc định một Spring @Transactional annotation tự atomic cả Kafka và database, trừ khi có coordination được cấu hình và hiểu rõ guarantees/failure windows.

### 19.5. Error retry policy

- Invalid message payload/business permanent failure → reject/quarantine/DLQ theo policy;
- Deadlock/serialization → bounded retry trong transaction mới;
- Database unavailable → retry with backoff;
- Commit outcome unknown → check processed marker;
- Duplicate event ID → trả/ack theo idempotent behavior.

Đừng catch mọi exception rồi ack như success.

### 19.6. Không mở transaction khi chờ message tiếp theo

Một worker nhận message không nên mở DB transaction rồi chờ queue để gom đủ items. Hãy xác định batch size/time window trước hoặc theo broker policy; mở transaction khi đã sẵn sàng xử lý một unit of work.

## 20. Cross-aggregate orchestration và DDD

### 20.1. Aggregate boundary không tự trùng transaction boundary

Trong DDD, aggregate bảo vệ invariants nội bộ. Một transaction đôi khi nên sửa **một aggregate**, nhưng một use case như stock reservation + order có thể buộc phối hợp nhiều aggregates/tables tùy thiết kế.

Không có quy tắc “mỗi Repository phải là một transaction” áp dụng tuyệt đối. Hãy xem consistency requirement và service ownership thực tế.

### 20.2. Domain service khác application service

- **Domain service:** xử lý quy tắc nghiệp vụ không thuộc riêng một entity, thường không điều khiển persistence transaction.
- **Application service:** điều phối use case, authorization, repositories, transaction, domain events.

Tên classes có thể khác nhau, nhưng trách nhiệm rõ giúp không đưa transaction manager vào domain rules.

### 20.3. Khi nên chia transaction thay vì ép nhiều aggregates cùng ghi

Nếu hai bounded contexts có database riêng hoặc ownership khác nhau, việc ép chúng vào một transaction có thể tăng coupling. Có thể chọn eventual consistency và workflow events nếu business cho phép.

### 20.4. Khi không được chia transaction

Nếu quy tắc là “mỗi ledger transfer phải ghi hai bút toán cân bằng và một transaction record” trong cùng ledger DB, hai legs nên nằm trong một atomic unit. Commit debit trước credit thường sai, kể cả khi gọi hai repository.

### 20.5. Giao dịch chuyển tiền ví dụ

~~~java
@Transactional
public TransferReceipt transfer(TransferCommand cmd) {
    authorization.requireTransfer(cmd);

    Account debit = accounts.lockById(cmd.fromId());
    Account credit = accounts.lockById(cmd.toId());

    debit.withdraw(cmd.amount());
    credit.deposit(cmd.amount());

    Transfer transfer = transfers.save(
        Transfer.record(cmd)
    );

    outbox.append(TransferRecorded.from(transfer));
    return TransferReceipt.from(transfer);
}
~~~

Đây là conceptual example; cần implement locking order, tenant checks, money/currency invariants, idempotency keys, legal requirements và reconciliation. Tất cả database writes cần atomic nếu business định nghĩa một ledger transfer như vậy.

### 20.6. Tránh để repository gọi repository vì “tiện”

Một OrderRepository tự gọi StockRepository và PaymentRepository sẽ dần trở thành application service trá hình, làm boundary mơ hồ và khó test. Nếu thực sự cần orchestration, đặt nó ở use-case coordinator và để repositories chuyên trách persistence.

### 20.7. Không biến application service thành nơi chứa mọi domain rule

Application service nên gọi domain methods như stock.reserve(), account.withdraw(), order.place() thay vì tự sửa public entity fields. Transaction ownership không đồng nghĩa business invariants đều phải nằm trong service.

## 21. Security và multi-tenancy trong transactional use case

### 21.1. Transaction không tự cấp quyền

Một @Transactional method có thể atomic nhưng vẫn sai security nếu load Product theo ID mà không lọc tenant. Authorization phải áp trước và trong các repository queries cần thiết.

### 21.2. Tenant context đáng tin

Tenant ID cần đến từ authenticated principal/service identity đã kiểm chứng, không chỉ từ JSON hoặc path parameter. DTO input không nên chứa những internal owner fields mà caller không được sửa.

### 21.3. Tenant-scoped repository methods

~~~java
Optional<ProductStock> findByTenantIdAndSku(
    String tenantId,
    String sku
);
~~~

Dù ProductStock#123 tồn tại, caller thuộc tenant khác không được quyền thay available. Query scoping giúp giảm IDOR/BOLA risks.

### 21.4. Không check quyền quá muộn

Sai flow:
1. Load và sửa managed ProductStock;
2. Persist PurchaseOrder;
3. Gửi event;
4. Cuối cùng mới check tenant permission.

Ngay cả nếu exception dẫn đến rollback, external side effects trước đó có thể đã xảy ra. Thực hiện authorization trước các side effects và đảm bảo DB predicates đúng scope.

### 21.5. Check đúng mọi foreign references

Đặt hàng có customerId, productSku, warehouseId: mỗi reference cần được kiểm tra theo tenant/ownership/business visibility. Một transaction không thay kiểm tra FK thuộc đúng tenant.

### 21.6. Dùng unique constraints có tenant scope

~~~sql
UNIQUE (tenant_id, request_key)
~~~

giúp cùng một requestKey của hai tenants không gây conflict lẫn nhau nếu business cho phép. Nhưng schema còn phải bảo vệ cross-tenant relations; một foreign key chỉ dùng product_id mà không bảo đảm tenant có thể chưa đủ cho tenant isolation.

### 21.7. Audit theo actor server-side

createdBy, approvedBy hoặc transferredBy phải lấy từ authenticated context, không từ raw request. Nếu audit event cần atomic với write, lưu trong cùng transaction hoặc dùng outbox. Audit logs bên ngoài DB có failure semantics riêng.

### 21.8. Read-only không phải permission

@Transactional(readOnly=true) không có nghĩa caller chỉ được đọc dữ liệu của mình, và @Version không ngăn unauthorized update. Authorization là trách nhiệm riêng.

## 22. Exception translation: đặt đúng vị trí để không phá transaction

### 22.1. Các tầng lỗi

~~~text
Database constraint/deadlock
        |
        v
SQLException / driver
        |
        v
JPA provider exception
        |
        v
PersistenceException / RollbackException
        |
        v
Spring DataAccessException (nếu translation)
        |
        v
Application error category
        |
        v
HTTP/message retry policy
~~~

Một lỗi database có thể xuất hiện tại persist, flush hoặc commit. Transaction boundary cần propagate failure đúng để rollback.

### 22.2. Repository không nên đổi mọi lỗi thành “not found”

Sai:

~~~java
public Optional<ProductStock> find(...) {
    try {
        return query(...);
    } catch (RuntimeException failure) {
        return Optional.empty();
    }
}
~~~

Một connection timeout sẽ bị che thành “SKU không tồn tại”. Dữ liệu sai hoặc outage không được phép trở thành business empty result.

### 22.3. Spring DataIntegrityViolationException không luôn là trùng key

Nó có thể đại diện UNIQUE, FK, NOT NULL, CHECK và những integrity violations khác. Không catch mọi DataIntegrityViolationException rồi luôn ném DuplicateOrderException.

### 22.4. JPA OptimisticLockException khác unique violation

Optimistic conflict thường là stale entity version; không xử lý bằng cách tìm SKU trùng. Retry cần reload state và reapply business command trong transaction mới.

### 22.5. Commit-time exception cần outer error handler

Nếu Spring proxy ném exception khi commit sau khi method body return, catch ở service body không bắt được. HTTP controller advice, application interceptor hoặc transaction decorator bao outer call có thể phân loại failure phù hợp.

### 22.6. Đọc root cause ở infrastructure boundary

SQLException SQLState, vendor codes và provider-specific constraint names có thể hữu ích. Nhưng domain/application error contract nên ổn định như:
- INSUFFICIENT_STOCK;
- DUPLICATE_REQUEST;
- ORDER_CONFLICT;
- OPTIMISTIC_CONFLICT;
- TRANSIENT_TRANSACTION_FAILURE;
- DATABASE_UNAVAILABLE.

Không đưa PostgreSQL SQLState hoặc Hibernate class vào mọi domain service.

### 22.7. Retry nằm ngoài transaction lỗi

Nếu deadlock/serialization failure xảy ra:
1. Transaction A rollback;
2. Backoff ngoài transaction;
3. Bắt đầu transaction B với context mới;
4. Reread state;
5. Reapply business intent;
6. Commit nếu hợp lệ.

Không retry stock.reserve() nhiều lần trong một EntityManager/context đã bị lỗi.

### 22.8. Idempotency xử lý commit outcome chưa rõ

Nếu connection đứt đúng lúc commit, không thể chắc DB chưa tạo Order. Trước khi retry, tra cứu requestKey/eventId từ committed state trong transaction khác. Không chỉ dựa vào việc caller nhận SQLException để phát một order/payment mới.

## 23. Hiệu năng và độ dài của transaction

### 23.1. Transaction nên ngắn nhưng đủ nhất quán

Mục tiêu không phải luôn làm transaction nhỏ nhất có thể mà là **nhỏ nhất đáp ứng business invariant**. Cắt transaction quá nhỏ làm partial commits, quá rộng làm tăng connection/lock contention.

### 23.2. Những tài nguyên có thể bị giữ trong transaction dài

- JDBC connection;
- Row/table locks tùy SQL và isolation;
- MVCC snapshot/version visibility;
- Transaction logs/undo/WAL;
- Persistence context/managed entities;
- Dirty-checking snapshots;
- Pending SQL batches;
- Timeouts/deadlock exposure;
- Thread/worker capacity trong imperative application.

Không mặc định tất cả database giữ mọi loại lock tới commit theo cùng cách, nhưng long transactions thường cần được đo và tối ưu.

### 23.3. Đừng gọi network dưới database transaction nếu không bắt buộc

~~~java
@Transactional
public void place(...) {
    stock.reserve(2);
    remotePricingService.calculate(...); // Có thể chậm.
    orders.save(order);
}
~~~

Nếu price calculation được phép độc lập và không yêu cầu snapshot held locks, có thể:
1. Tính/validate dữ liệu trước transaction;
2. Mở transaction;
3. Reload/recheck current state quan trọng;
4. Ghi DB;
5. Commit;
6. Chạy side effects sau commit/outbox.

Không giữ stock row lock trong lúc chờ một service ở mạng khác.

### 23.4. Pre-validation ngoài transaction có thể stale

Đưa tất cả validation ra trước transaction không phải lúc nào đúng: một pre-check stock.available=3 có thể thay đổi trước khi transaction bắt đầu. Input format validation có thể thực hiện ngoài transaction; **state-dependent checks** cần chạy lại trong transaction hoặc dựa trên atomic predicates/locking.

### 23.5. JDBC batching và flush/clear khác commit

Trong JPA bulk import, flush/clear sau 500 entities có thể giảm persistence context memory. Nhưng nếu một @Transactional method bao toàn file, toàn bộ vẫn là một DB transaction; locks và rollback scope không nhỏ đi.

Hibernate JDBC batch size là một optimization riêng, không tự định nghĩa unit of work.

### 23.6. N+1 đọc dữ liệu bên trong write transaction

Nếu PlaceOrderService nạp Product, Category, Supplier bằng lazy getters trong vòng lặp, mỗi relation có thể gây SQL SELECT, kéo dài transaction. Dùng fetch plans/projections/queries có chủ đích để giảm thời gian giữ locks.

### 23.7. Connection pool và REQUIRES_NEW

Số concurrent transactions, transaction durations và REQUIRES_NEW nested connections tác động trực tiếp đến pool saturation. Khi outer thread giữ một connection và chờ inner connection, tăng REQUIRES_NEW vô tội vạ có thể làm toàn hệ thống chờ.

### 23.8. Timeout không phải một loại duy nhất

Các lớp timeout thường gặp:
- Pool connection acquisition timeout;
- JDBC query/statement timeout;
- Database lock timeout;
- Database statement timeout;
- Spring transaction timeout;
- HTTP request deadline;
- Downstream network timeout.

Một timeout không tự cho biết đã rollback, đã commit hay cần retry. Ghi nhận layer và transaction outcome.

### 23.9. Log transaction boundary bằng dữ liệu có cấu trúc

Một log event nội bộ có thể có:
- useCase=placeOrder;
- transactionScope=orderPlacement;
- attempt=1;
- outcome=COMMITTED/ROLLED_BACK/UNKNOWN nếu xác minh được;
- durationMs;
- SQLState/error category khi lỗi;
- traceId/requestId;
- tenant code đã được giảm nhạy cảm nếu cần.

Không log raw password/payment info/entire entity graph. Đừng ghi outcome=COMMITTED trước khi transaction manager báo commit thực sự thành công.

### 23.10. Những metrics đáng đo

| Metric | Công dụng |
|---|---|
| transaction_duration_ms p50/p95/p99 | Xem transaction quá dài |
| db_connection_acquire_ms | Pool starvation |
| db_lock_wait_ms | Lock contention |
| transaction_rollback_total{category} | Sự cố/invariant failures |
| optimistic_lock_conflict_total | Concurrent stale writes |
| deadlock_total | Lock ordering vấn đề |
| sql_statement_count | N+1 và query overhead |
| outbox_pending_count | Event publisher lag |
| idempotency_conflict_total | Duplicate/mismatched requests |
| unknown_commit_outcome_total | Cần reconciliation |
| retry_attempts_total | Retry storm |
| batch_chunk_commit_total | Partial progress |

Tránh metric labels có cardinality cực lớn như requestKey/orderId/rawSql.

## 24. Anti-pattern và vì sao sai

| Anti-pattern | Hậu quả có thể xảy ra | Cách thay thế |
|---|---|---|
| Mỗi repository.save tự commit | Partial DB state | Use-case transaction |
| Chỉ @Transactional trên từng repo | Không gộp workflow khi không có outer tx | Coordinator boundary |
| @Transactional đặt trên private helper | Proxy không intercept như kỳ vọng | Public entrypoint/decorator |
| this.method() self-invocation | Bypass Spring transaction proxy | Bean khác/TransactionTemplate |
| new Service() thay Spring bean | Không được advice/proxy | Inject managed bean |
| REQUIRES_NEW ở mọi save | Commit riêng và pool exhaustion | REQUIRED trong outer tx |
| Dùng NESTED như independent commit | Hiểu sai savepoint | NESTED chỉ khi manager hỗ trợ |
| Bắt PersistenceException rồi return success | Rollback-only bị che | Propagate/translate failure |
| Catch commit exception chỉ trong method body | Lỗi commit có thể xảy ra ngoài catch | Outer error boundary |
| Mọi SQLException đều retry | Permanent constraint errors vẫn fail | Classify + bounded retry |
| Retry trên cùng EntityManager bị lỗi | Context/DB tx không usable | Rollback, transaction mới |
| Retry stale @Version snapshot | Ghi đè hoặc fail lặp | Reload/recompute business intent |
| Suy flush là commit | Báo thành công sớm | Return after transactional proxy |
| Dùng em.clear thay rollback | DB changes vẫn chưa được hủy | Transaction manager rollback |
| Email/API call trong transaction | Long locks/side effects khi rollback | Outbox/after-commit |
| Kafka send trước DB commit | Event cho state không tồn tại | Outbox và idempotent consumers |
| OutboxRepository REQUIRES_NEW | Outbox/order không atomic | Cùng business transaction |
| Cố JPA @Transactional qua HTTP calls | Không có local distributed ACID | Saga/workflow |
| JTA config chưa rõ mà nghĩ multi-DB atomic | Partial commits | XA hoặc redesign |
| @Transactional(readOnly=true) cho write | Provider/DB khác behavior | Write transaction rõ |
| OSIV làm transaction boundary | Queries ngoài use case | DTO trong read transaction |
| Query missing tenant filter | Atomic nhưng unauthorized | Tenant-scoped queries |
| Kiểm tra stock ngoài tx rồi ghi | Race/lost update | Recheck/lock/atomic SQL |
| Không có @Version/lock/constraint | Concurrent writes sai invariant | Concurrency controls |
| @Version là bằng chứng không cần idempotency | Request có thể gửi lại | Unique request key + reconciliation |
| Catch DB error rồi Optional.empty | Outage thành “không tồn tại” | Typed errors |
| @Transactional trên test rồi luôn rollback | Không test commit path thật | Separate transaction integration tests |
| Batch flush/clear coi như checkpoints | Rows chưa commit | Transaction-per-chunk/checkpoints |
| ACK message trước DB COMMIT | Message loss | Ack theo outcome + idempotency |
| ACK sau commit nhưng không dedupe | Duplicate processing | Processed-event marker |
| Remote call trong row lock transaction | Tăng contention/timeout | Tách workflow steps |
| Commit transaction rồi ghi checkpoint ngoài DB vô điều kiện | Crash gap | Atomic checkpoint/reconciliation |
| Nhầm permission với transaction | Unauthorized atomic write | Auth + resource scoping |
| Chỉ dựa vào happy-path unit tests | Bỏ qua rollback edge cases | Integration tests fault injection |

### 24.1. Transaction annotation không thay architecture

Một codebase có thể có đầy @Transactional nhưng vẫn có:
- Outer transaction không tồn tại;
- Propagation không như mong muốn;
- DB resources không cùng manager;
- External events gửi trước commit;
- Retry trong context lỗi;
- Authorization sai tenant;
- Concurrency race.

Bởi vậy review phải xuất phát từ **use-case state transitions và commit/rollback scope**, không đếm annotations.

### 24.2. Repository không nên quyết định gửi email

Nếu ProductRepository.save vừa INSERT vừa gửi notification, side effect không phải transactionally atomic với DB; data access layer bị ghép với workflow, khó test và khó đổi publisher. Tách event intent vào application/outbox.

### 24.3. Catch rồi “khôi phục” bằng một save mới là nguy hiểm

Nếu Order INSERT fail do UNIQUE, transaction có thể đã rollback-only. Gọi repository.save(existing) trong catch không đảm bảo có thể commit. Với duplicate idempotent request, **kết thúc transaction lỗi**, rồi đọc lại state trong transaction mới.

### 24.4. Không dùng logic trả về boolean để che lỗi DB

Một repository save thất bại mà trả false như “không tìm thấy” sẽ làm service khó phân biệt:
- Business conflict;
- Connection failure;
- Constraint mismatch;
- Optimistic lock failure.

Có thể định nghĩa result/exception categories rõ, nhưng không nuốt lỗi hạ tầng.

## 25. Kiểm thử ranh giới transaction: phải quan sát database sau commit/rollback

### 25.1. Unit test service logic chưa đủ

Mock StockRepository, OrderRepository và OutboxRepository có thể chứng minh thứ tự calls và business branches. Nhưng mocks **không chứng minh**:
- Transaction thật đã mở;
- Các repositories join cùng physical transaction;
- Database rollback tất cả writes;
- Constraint violation xuất hiện ở commit;
- @Version tránh lost updates;
- REQUIRES_NEW đang commit riêng.

Cần integration tests với JPA provider và database thật hoặc môi trường tương đương.

### 25.2. Test atomicity cho PlaceOrder

Dùng PostgreSQL/Testcontainers hoặc DB như production. Setup ProductStock.available=10.

Scenario thành công:
1. Gọi PlaceOrderService.place với quantity=2;
2. Chờ method invocation qua Spring proxy hoàn tất;
3. Mở read transaction/context mới;
4. Assert available=8;
5. Assert PurchaseOrder tồn tại;
6. Assert OutboxMessage tương ứng tồn tại.

Scenario lỗi:
1. Tạo điều kiện khiến outbox persist/flush/commit thất bại (constraint/controlled fault);
2. Gọi PlaceOrderService.place;
3. Assert propagated exception;
4. Context/transaction mới đọc DB;
5. Assert stock vẫn 10;
6. Assert không có Order;
7. Assert không có Outbox record.

Cần bảo đảm fault injection xảy ra **trước commit** của same transaction, không dùng một mock ném exception sau khi DB đã commit rồi kết luận rollback được.

### 25.3. Test repository không commit sớm

Một outer transaction:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    stock.reserve(2);
    orders.save(order);
    outbox.save(message);

    status.setRollbackOnly();
});
~~~

Sau đó query DB trong transaction mới, tất cả thay đổi phải không tồn tại. Code snippet yêu cầu context/repository operations phù hợp và fixtures thật; không giả định biến stock nạp trước transaction mà chưa managed.

### 25.4. Test @Transactional proxy path

Một test gọi service từ Spring context bằng injected bean và kiểm tra atomicity thực. Không tự new service. Với self-invocation regression, dùng hai paths:
- Gọi transactional method qua proxy → transaction như mong đợi;
- Gọi this.transactionalMethod() từ class khác method trên cùng object → behavior có thể khác.

Mục tiêu là phát hiện transaction boundary bị bypass do code refactor.

### 25.5. Test checked-exception rollback rules

Tạo operation thay đổi DB rồi ném custom checked exception. So sánh:
- @Transactional default rollback rules;
- @Transactional(rollbackFor = CustomCheckedException.class).

Assert DB state sau invocation. Không kết luận chỉ từ việc exception được throw; cần nhìn commit outcome.

### 25.6. Test rollback-only và UnexpectedRollbackException

Một inner REQUIRED participant gặp lỗi, đánh dấu transaction rollback-only; outer catch rồi return. Assert outer transaction không commit và caller nhận rollback signal phù hợp. Test giúp phát hiện kiểu “nuốt lỗi rồi trả success”.

### 25.7. Test REQUIRES_NEW khác REQUIRED

Scenario:
- Outer tx sửa stock;
- Inner method REQUIRES_NEW ghi audit;
- Outer rollback.

Assert audit tồn tại nếu inner commit thành công và contract cho phép, trong khi stock rollback. Nếu dùng REQUIRED thay, cả audit và stock rollback. **Đây là ví dụ về semantics**, không khuyến nghị dùng REQUIRES_NEW cho audit ở mọi hệ.

### 25.8. Test NESTED chỉ trên transaction manager hỗ trợ

Nếu project dùng JDBC/DataSourceTransactionManager và savepoints, có thể test rollback nested scope không rollback toàn outer; với JPA provider cần xem persistence context state sau savepoint. Không dựa vào tên NESTED để assume cùng behavior trên mọi manager.

### 25.9. Test constraint violation tại flush và commit

Một SQL constraint:
- Có thể fail tại em.flush();
- Có thể fail tại commit, đặc biệt deferred constraints;
- Có thể bị wrapper trong RollbackException hoặc Spring translation.

Test outer invocation boundary và assert final database state, tránh hard-code một số tầng getCause cố định.

### 25.10. Test concurrency với hai EntityManagers

Tạo stock available=3. Hai transactions load stock cùng version và cùng reserve 2; cho một commit trước rồi transaction khác flush/commit:
- Nếu @Version hoạt động, một transaction stale phải fail hoặc retry theo policy;
- Không được tạo hai đơn thành công mà stock chỉ giảm một lần;
- Sau rollback, cả Order/Outbox của transaction fail không tồn tại.

Dùng two EntityManagers/transactions/connections độc lập và CountDownLatch/Barrier khi cần, không chia sẻ EntityManager giữa threads hoặc dựa vào Thread.sleep đoán timing.

### 25.11. Test idempotency key

Gọi place() hai lần cùng tenant/requestKey và cùng intent:
- Kết quả không tạo hai Orders;
- Stock chỉ reserve một lần;
- Outbox event cho một business operation không bị nhân đôi từ request-level duplicate;
- RequestKey same nhưng intent khác phải báo conflict.

Đồng thời test concurrent requests với cùng key, không chỉ sequential duplicate.

### 25.12. Test outbox rollback

Nếu Stock.reserve ném InsufficientStockException:
- Không có Order;
- Không có outbox;
- Stock giữ nguyên.

Nếu outbox insert fail:
- Stock rollback;
- Order rollback;
- Không có outbox mới.

Đừng chỉ assert exception type mà bỏ DB state.

### 25.13. Test saga state machine

Nếu external payment thất bại sau khi Order đã commit:
- Không gọi rollback transaction PlaceOrder đã kết thúc;
- Chạy compensation/mark failed trong transaction mới;
- Kiểm tra idempotent release reservation;
- Replay cùng payment event không làm release hai lần.

### 25.14. Test consumer ACK policy

Với message consumer:
- Fail trước commit → message được retry theo broker policy, DB không có effect;
- Commit trước ACK rồi process crash → retry duplicate không ghi effect hai lần;
- Duplicate eventId → dedupe marker không tạo new order.

### 25.15. Test @DataJpaTest có thể che commit-time bugs

Spring Boot @DataJpaTest thường chạy tests trong transaction rollback sau test (tùy cấu hình). Nó hữu ích để test repository/mapping nhưng **không chứng minh một service method tự commit** khi test còn một outer transaction.

Dùng integration test không bị outer test transaction bao trùm, hoặc explicitly control test transactions/commits/verify in new context theo framework. Nếu cần test commit constraints, phải thực sự thực hiện commit theo test setup.

### 25.16. Test read consistency

Với report cần nhiều queries same snapshot, thử concurrent writer giữa hai queries và kiểm chứng isolation policy theo target DB. @Transactional(readOnly=true) một mình không đủ để suy snapshot semantics khi default isolation thay đổi.

### 25.17. Test datasource ownership

Với nhiều persistence units/datasources, tạo lỗi ở resource B sau khi resource A đã ghi. Xác minh transaction manager/distributed transaction configuration thực sự đáp ứng business requirement. Nếu không, document eventual consistency/compensation thay vì tuyên bố atomicity.

### 25.18. Test rollback có side effects ngoài DB

Với thiết kế outbox:
- Force rollback PlaceOrder;
- Assert không có outbox committed;
- Publisher không phát event.

Nếu code trực tiếp gửi email trước commit, test có thể phát hiện email mock nhận call dù DB rollback — đây là dấu hiệu kiến trúc sai.

## 26. Bài tập thực hành

Với mỗi bài tập, hãy nêu: **transaction boundary**, **những rows cần cùng commit/rollback**, **propagation/isolation nếu cần**, **các side effects ngoài DB**, **cách phục hồi** và **cách kiểm thử kết quả đã commit**. Không chỉ đặt @Transactional rồi coi là đủ.

### Bài 1. Hai repositories không có outer transaction

Một service gọi StockRepository.reduce(), sau đó OrderRepository.save(). Mỗi method được @Transactional(REQUIRED) và caller không có transaction. Nếu OrderRepository.save lỗi, stock có thể đã commit không? Hãy đặt transaction boundary lại.

### Bài 2. Ba writes và outbox

Đặt hàng cần UPDATE stock, INSERT order, INSERT outbox. Vẽ một unit of work và giải thích vì sao OutboxRepository không nên REQUIRES_NEW nếu outbox đại diện cùng operation.

### Bài 3. Flush khác commit

~~~java
em.persist(order);
em.flush();
throw new RuntimeException("failure");
~~~

Trong một outer @Transactional method, Order có nhất thiết tồn tại sau request không? Nêu sự khác biệt giữa SQL đã chạy và transaction đã commit.

### Bài 4. Clear không rollback

Developer gọi em.flush(); em.clear(); rồi cố tiếp tục sau một DB constraint exception. Clear có biến transaction đang lỗi trở lại usable không? Đề xuất xử lý đúng.

### Bài 5. Repository contract

Thiết kế StockRepository port chỉ chứa findByTenantAndSku và một atomic decrement method nếu cần. Nó có nên gọi PaymentGateway không? Có nên tự commit mọi write không?

### Bài 6. Domain vs application service

Viết trách nhiệm của ProductStock.reserve() so với PlaceOrderService.place(). Bên nào kiểm tra quantity dương, bên nào điều phối order+outbox transaction?

### Bài 7. Spring proxy

Một method @Transactional trong Spring service được gọi trực tiếp từ controller qua injected bean. Vẽ trình tự proxy begin → body → commit → return.

### Bài 8. Self-invocation

~~~java
public void handle() {
    this.place();
}

@Transactional
public void place() {}
~~~

Vì sao transaction advice có thể không chạy? Đề xuất tách bean hoặc TransactionTemplate.

### Bài 9. Object tự new

Một unit test gọi new PlaceOrderService(...).place() rồi thấy @Transactional annotation trong code. Điều đó chứng minh transaction chạy không? Tại sao integration test nên gọi Spring bean/proxy thật?

### Bài 10. Private @Transactional method

Một service gắn @Transactional trên private method do public method gọi. Với Spring proxy mode, có vấn đề gì? Đặt annotation ở đâu?

### Bài 11. Checked exception

Service ghi một row rồi ném IOException. Theo Spring default rollback rules truyền thống, điều gì có thể xảy ra? Sửa bằng rollbackFor hoặc transaction-specific policy.

### Bài 12. Catch rồi trả success

Service catch DataIntegrityViolationException và return “Order created”. Hãy phân tích rollback-only state và trường hợp UnexpectedRollbackException tại outer commit.

### Bài 13. Exception chỉ xuất hiện ở commit

Một UNIQUE constraint được phát hiện ở transaction commit, không ở orders.save(). Catch quanh orders.save có đủ không? Vị trí nào có thể map lỗi thành ApiError sau transaction proxy?

### Bài 14. REQUIRED bên trong REQUIRED

PlaceOrderService @Transactional(REQUIRED) gọi StockService và OrderService đều @Transactional(REQUIRED). Bao nhiêu physical transactions thường được dùng với cùng transaction manager/datasource? Ai sở hữu commit?

### Bài 15. Không có outer transaction

Giống Bài 14 nhưng bỏ @Transactional khỏi PlaceOrderService. Nếu StockService và OrderService được gọi qua proxies, chúng có thể commit riêng không? Dữ liệu sai thế nào khi bước thứ hai fail?

### Bài 16. REQUIRES_NEW cho Order

Outer PlaceOrder tx A reserve stock; inner OrderService REQUIRES_NEW commit order; outer fail. Hãy mô tả DB state và vì sao có thể vi phạm invariant.

### Bài 17. REQUIRES_NEW cho audit

Một operation thất bại nhưng business cần lưu audit attempt độc lập. REQUIRES_NEW có thể hợp lý không? Nêu điều kiện, security, rollback policy và pool resources cần kiểm tra.

### Bài 18. Connection pool với REQUIRES_NEW

16 requests cùng giữ 16 connections trong outer transactions, mỗi request mở REQUIRES_NEW. Pool max=16. Điều gì có thể xảy ra? Thiết kế capacity/architecture thay thế.

### Bài 19. NESTED và savepoint

So sánh nested rollback-to-savepoint với REQUIRES_NEW commit độc lập. Nếu outer rollback sau nested success, nested changes còn tồn tại không? Trên JPA, cần kiểm tra compatibility gì?

### Bài 20. MANDATORY ở OutboxAdapter

Tại sao một appendOutbox method dùng propagation MANDATORY có thể giúp phát hiện caller quên transaction? Khi nào không nên áp MANDATORY tùy tiện?

### Bài 21. SUPPORTS và write

Một write method có SUPPORTS. Caller không có transaction, JPA em.persist chạy thế nào? Có thể ném TransactionRequiredException không? Chọn contract phù hợp hơn.

### Bài 22. NOT_SUPPORTED ở remote call

Use case cần gọi external pricing API. Khi nào nên đặt call ngoài DB transaction thay vì dùng NOT_SUPPORTED trong một transaction đang giữ locks? Điều gì có thể stale khi quay lại DB?

### Bài 23. Read-only transaction

Một @Transactional(readOnly=true) service chỉ query Products rồi map DTO. readOnly có tự xác nhận user có quyền đọc Product không? Nó có bảo đảm DB từ chối mọi write trên mọi provider không?

### Bài 24. Read snapshot

Report chạy ba SELECTs cần cùng snapshot, nhưng DB default isolation là READ_COMMITTED. Cần xem consistency requirement và isolation thế nào? readOnly=true có tự tạo snapshot đồng nhất không?

### Bài 25. Lost update tồn kho

Stock.available=3. Hai users cùng reserve 2. Nếu không có locking/versioning, kết quả có thể sai như thế nào? Đề xuất @Version hoặc conditional UPDATE.

### Bài 26. Optimistic conflict

A và B load ProductStock version=5; B commit trước, A flush fail. Có nên retry riêng stock.reserve() trên context A không? Cần rollback/reload/order/outbox thế nào?

### Bài 27. Pessimistic lock

Viết JPA query dùng LockModeType.PESSIMISTIC_WRITE và tenant filter. Nêu lock wait/deadlock/timeout và vì sao transaction nên ngắn.

### Bài 28. Write skew

Hai doctors đều đang trực; hai transactions tắt hai người khác nhau dựa trên đọc “vẫn còn người trực”. Row-level @Version riêng có chắc ngăn vi phạm không? Nêu lock/serializable/constraint solutions.

### Bài 29. Deadlock order

Tx A khóa SKU-A rồi SKU-B, Tx B khóa SKU-B rồi SKU-A. Vẽ wait-for cycle và đề xuất lock ordering cố định.

### Bài 30. Isolation.DEFAULT

Một service dùng Isolation.DEFAULT. Có thể kết luận đó là READ_COMMITTED trên mọi DB không? Những config nào cần tra?

### Bài 31. Multi-tenancy

Một PlaceOrderService @Transactional nhưng StockRepository tìm theo SKU không lọc tenant. Hệ thống có atomicity không? Có security correctness không? Đề xuất query scoping và cross-tenant tests.

### Bài 32. Hai DataSources

StockRepository dùng DataSource A, OrderRepository dùng DataSource B. Service @Transactional chỉ dùng transactionManagerA. Có thể chắc cả hai rollback cùng nhau không? Nêu JTA/XA hoặc eventual-consistency design.

### Bài 33. Hai schemas cùng database

Hai repositories dùng hai EntityManagerFactories cho hai schemas. Có thể suy atomicity chỉ từ việc chung database host không? Cần xác minh physical transaction/data source binding nào?

### Bài 34. Email trước commit

PlaceOrderService gửi email xác nhận ngay sau orders.save, rồi outbox insert fail và DB rollback. Khách hàng nhận gì? Đề xuất transactional outbox hoặc after-commit policy.

### Bài 35. Outbox publisher crash

Publisher gửi Kafka thành công rồi crash trước khi đánh dấu outbox row published. Sau restart gửi lại. Consumer phải làm gì để không xử lý trùng?

### Bài 36. Saga payment

PlaceOrder transaction A commit trạng thái PENDING_PAYMENT. Payment gateway trả failure. Có thể gọi rollback() để hủy A không? Thiết kế compensation/release stock trong transaction mới.

### Bài 37. Unknown payment outcome

Worker gửi payment request, network timeout trước khi nhận acknowledgment. Retry ngay có thể gây charge trùng không? Dùng provider idempotency key và reconciliation thế nào?

### Bài 38. Batch 100.000 rows

Một method @Transactional import toàn file, flush/clear mỗi 500. Nó tạo bao nhiêu database commits? Nếu mục tiêu partial commit per chunk, phải đổi architecture thế nào?

### Bài 39. Spring Batch và transaction ownership

Một Spring Batch step đã quản lý transaction per chunk, writer lại dùng REQUIRES_NEW. Những sai lệch nào có thể xuất hiện trong skip/retry/checkpoint semantics?

### Bài 40. Message acknowledgment

Consumer ACK broker trước DB commit rồi service fail. Message có nguy cơ mất không? ACK sau commit nhưng crash trước ACK dẫn đến vấn đề gì? Dùng processed-event marker.

### Bài 41. Idempotency key

Hai requests cùng tenant/requestKey và cùng intent tới đồng thời. Pre-check đều không thấy row. Database cần UNIQUE gì? Bên thua race nên reconcile bằng transaction mới như thế nào?

### Bài 42. Idempotency key bị tái dùng sai

RequestKey cũ đã tạo Order SKU-A qty=2; request mới dùng cùng key với SKU-B qty=5. Có nên trả Order cũ như thể cùng intent không? Thiết kế mismatch conflict.

### Bài 43. Commit outcome unknown

Database đã nhận COMMIT Order nhưng connection đứt trước acknowledgement. Caller gặp SQLException. Có thể khẳng định Order chưa được tạo không? Dùng requestKey/transaction status reconciliation.

### Bài 44. Repository che lỗi

StockRepository catch mọi RuntimeException rồi return Optional.empty(). Khi DB unavailable, PlaceOrderService báo “SKU không tồn tại”. Hãy sửa error contract và phân loại exception.

### Bài 45. Unit test mocks

Một test mock repositories verify save(stock), save(order), save(outbox) đã gọi. Test này có chứng minh rollback atomic không? Thiết kế một integration test phá outbox insert trước commit.

### Bài 46. Test outer transaction

Dùng TransactionTemplate mở transaction, ghi stock+order+outbox, gọi status.setRollbackOnly. Query DB bằng new transaction. Expected state là gì?

### Bài 47. @DataJpaTest rollback mặc định

Một @DataJpaTest chạy trong rollback-only test transaction. Vì sao nó có thể không kiểm tra được service commit semantics? Thiết kế test không có outer tx để quan sát real commit.

### Bài 48. Test checked exception rollback

Cùng một service có checked BusinessException sau INSERT; chạy với @Transactional mặc định và rollbackFor. Kiểm tra DB state sau invocation, không chỉ exception class.

### Bài 49. Test concurrent @Version

Dùng hai EntityManagers/transactions và CountDownLatch để tạo conflict trên stock. Vì sao không share cùng EntityManager giữa threads? Cần assert Order/Outbox của transaction thua thế nào?

### Bài 50. Thiết kế hoàn chỉnh

Thiết kế PlaceOrder workflow:
1. Authenticated tenant/permission;
2. Request validation;
3. Idempotency key;
4. Stock lock/version policy;
5. Domain reserve;
6. PurchaseOrder persist;
7. Outbox append cùng transaction;
8. Spring/JPA transaction boundary ở use-case coordinator;
9. Propagation để repositories tham gia;
10. Rollback trên checked/unchecked failures;
11. Retry bounded cho deadlock/serialization;
12. Reconcile commit outcome unknown;
13. Async publisher/consumer idempotency;
14. HTTP error DTO;
15. Integration tests atomically verifying DB state.

Giải thích vì sao **Repository không nên tự commit ba phần**, vì sao **side effects ngoài DB không nằm trong một local transaction**, và cách chứng minh consistency bằng tests.

## 27. Bảng tra cứu: đặt transaction boundary ở đâu?

| Nghiệp vụ | Boundary thường phù hợp | Vì sao |
|---|---|---|
| Tạo Product đơn giản | CreateProduct use case | Validation + một write |
| Tạo Order, trừ stock, ghi outbox | PlaceOrder use case | Cần atomic nhiều DB writes |
| Chuyển tiền giữa hai accounts cùng DB | TransferFunds use case | Debit/credit/ledger cùng commit |
| Đọc Product detail | Read use case ngắn | Scope/DTO và lazy fetching |
| Report cần multi-query snapshot | Report read transaction với isolation phù hợp | Consistent data view |
| Dashboard chấp nhận eventual consistency | Các read calls ngắn | Không cần tx dài |
| Gửi email sau khi Order commit | Outbox worker/after-commit | Email không nằm trong DB tx |
| Thanh toán qua external API | Saga step local transactions | HTTP payment không tham gia local ACID |
| Import 1 triệu rows, all-or-nothing | Một transaction hoặc staging/finalization | Business không chấp nhận partial commit |
| Import 1 triệu rows, cho phép resume | Transaction-per-chunk | Partial progress + checkpoint |
| Xử lý một queue message | Message handler local transaction | State + processed-event marker atomic |
| Batch step do Spring Batch điều phối | Chunk transaction của step | Framework quản lý retry/skip |
| Đọc rồi cập nhật stock | Write use case với lock/version | Chống race/lost update |
| Đồng bộ hai services với DB khác nhau | Workflow/saga hoặc XA nếu cần | Không thể giả định single local tx |
| Ghi audit bắt buộc cùng Order | Cùng Order transaction | Audit row không tách biệt |
| Ghi audit attempt kể cả khi Order rollback | Độc lập có chủ đích | Cần separate transaction/policy |
| Gọi external pricing service | Ngoài write transaction nếu có thể | Không giữ DB locks lúc chờ network |
| Tạo scheduled export job | Transaction tạo job record | Worker xử lý dữ liệu riêng |
| Xóa một aggregate có cascade | Delete use case transaction | Entity/related rows cần consistency |
| Invalidate external cache | After-commit/outbox workflow | Tránh cache side effect trước commit |

### 27.1. Không có quy tắc “mọi service method đều transaction”

Một service read-only gọn, một scheduler coordinator hay một network orchestration có thể **không** cần @Transactional bao toàn method. Chọn transaction ở đoạn có database state consistency requirement.

### 27.2. Không có quy tắc “repository không bao giờ @Transactional”

Spring Data repositories có thể có transaction metadata/defaults, và một standalone repository operation có thể cần transaction. Bài học nhấn mạnh rằng **nơi điều phối nghiệp vụ phải xác định outer atomic unit khi phối hợp nhiều operations**, không phải mọi annotation ở data layer đều sai.

### 27.3. Một transaction có thể bao nhiều repositories nhưng không bao mọi hệ thống

Nếu Order, Stock và Outbox nằm cùng DB/transaction manager, một local transaction thường phù hợp. Nếu PaymentGateway hoặc email ở mạng ngoài, local transaction không có rollback authority với chúng. Đừng nhầm transaction scope với application call graph scope.

## 28. Checklist thiết kế Repository và transaction ownership

### 28.1. Business consistency và ownership

1. **Use case được đặt tên rõ chưa?** Ví dụ PlaceOrder, TransferFunds, CancelOrder.
2. **Các invariants cần atomic đã được liệt kê chưa?**
3. **Những database writes nào phải cùng commit hoặc rollback?**
4. **Những bước nào thuộc external side effect?**
5. **Có chỉ rõ commit boundary trước khi báo thành công không?**
6. **Có xác định khi nào cho phép partial success không?**
7. **Có người/step sở hữu transaction scope rõ ràng không?**
8. **Có tránh để repository tự quyết định workflow của nghiệp vụ khác không?**
9. **Có tránh cắt transaction theo số lần repository.save không?**
10. **Có tránh transaction quá rộng bao cả remote network calls không?**

### 28.2. Domain và Repository boundaries

11. **Domain methods có tự bảo vệ invariants không?**
12. **Domain có tránh tự mở/commit transaction không?**
13. **Repository interface có tập trung vào query/persistence primitive không?**
14. **Repository có tránh gọi email/payment/Kafka trực tiếp không?**
15. **Repository có tránh tự close EntityManager do container quản lý không?**
16. **Repository có tránh commit trong helper saveAndCommit không?**
17. **Có phân biệt em.persist/save với transaction commit không?**
18. **Có phân biệt em.flush với commit không?**
19. **Có biết em.clear không phải rollback không?**
20. **Có tránh nuốt persistence error thành Optional.empty không?**
21. **Có stable application error categories khi cần không?**
22. **Có kiểm tra database constraints tương ứng business invariants không?**

### 28.3. Spring proxy và transaction configuration

23. **@Transactional đặt ở public/use-case entrypoint thực sự được proxy gọi chưa?**
24. **Có tránh self-invocation làm bypass proxy không?**
25. **Có tránh tự new Spring service rồi kỳ vọng advice không?**
26. **Có hiểu commit sau method body tại transaction interceptor không?**
27. **Có xem checked-exception rollback policy không?**
28. **Custom exception có được propagate theo rollback rule không?**
29. **Có tránh catch lỗi rồi return success khi tx rollback-only không?**
30. **Có hiểu UnexpectedRollbackException khi inner đánh dấu rollback-only không?**
31. **Có xác định PlatformTransactionManager đúng datasource không?**
32. **Có kiểm tra Spring Data CRUD/query transaction defaults không?**
33. **Có hiểu REQUIRED sẽ join existing tx không?**
34. **Có test thực tế runtime proxy path không?**

### 28.4. Propagation và nested calls

35. **Mỗi REQUIRES_NEW có thật sự cần independent commit không?**
36. **Có biết REQUIRES_NEW có thể giữ outer connection và cần inner connection không?**
37. **Có tránh REQUIRES_NEW phá stock/order/outbox atomicity không?**
38. **Có hiểu NESTED thường dựa trên savepoint và manager support không?**
39. **Nếu dùng NESTED/JPA, có test persistence context sau rollback-to-savepoint không?**
40. **Có dùng MANDATORY ở participant cần transaction khi phù hợp không?**
41. **Có tránh SUPPORTS ở writes bắt buộc atomic không?**
42. **Có tránh NOT_SUPPORTED/NEVER khiến một write rơi khỏi unit of work không?**
43. **Có phân biệt propagation config ở method với physical tx thực tế không?**

### 28.5. Isolation và concurrency

44. **Có xác định DB isolation thực tế thay vì giả định Isolation.DEFAULT không?**
45. **Có hiểu inner REQUIRED không tự đổi isolation của outer tx không?**
46. **Có @Version/pessimistic locks/atomic SQL khi nhiều writers tranh dữ liệu không?**
47. **Có chống lost updates khi trừ stock không?**
48. **Có xem write skew/phantom nếu invariant xuyên nhiều rows không?**
49. **Có thứ tự lock ổn định để giảm deadlock không?**
50. **Có giảm thời gian giữ locks bằng cách tách remote calls không?**
51. **Có policy retry toàn transaction khi serialization failure không?**
52. **Có tránh retry stale entity trong context đã lỗi không?**
53. **Có database UNIQUE cho requestKey/business key không?**

### 28.6. Multi-tenant và authorization

54. **Tenant lấy từ authenticated context chứ không từ request tùy ý không?**
55. **Repository read/write queries có tenant scope không?**
56. **Có kiểm tra quyền của product/customer/warehouse references không?**
57. **Có tránh dùng @Transactional làm thay authorization không?**
58. **Có tránh dùng readOnly làm security permission không?**
59. **Audit actor được gán từ server identity không?**
60. **Unique constraints và FK có phù hợp multi-tenant model không?**
61. **Có negative tests cho cross-tenant updates không?**

### 28.7. External side effects và distributed workflows

62. **Có tránh gửi email/event trước DB commit không?**
63. **Outbox record có cùng transaction với business writes không?**
64. **OutboxRepository có tránh commit REQUIRES_NEW không phù hợp không?**
65. **Publisher có thể retry sau crash không?**
66. **Consumer có idempotent eventId handling không?**
67. **Có hiểu after-commit callbacks có crash gap không?**
68. **Workflow payment/shipping có saga/step boundaries không?**
69. **Compensation được định nghĩa thành business action mới không?**
70. **Có tránh giả định một local @Transactional atomic qua HTTP/multi-DB không?**
71. **Nếu cần XA/JTA, infrastructure và recovery logs đã được thiết kế không?**
72. **Có handling cho unknown commit/payment outcome không?**

### 28.8. Batch, messages và operational controls

73. **Nếu batch commit-per-chunk, coordinator có tránh outer tx dài không?**
74. **Có phân biệt flush/clear với transaction-per-chunk không?**
75. **Checkpoint/idempotency có gắn với committed state không?**
76. **Có thể resume khi crash sau commit nhưng trước checkpoint không?**
77. **Message ACK/NACK policy có xét DB commit outcome không?**
78. **Có processed-event marker chống duplicate delivery không?**
79. **Retry có bounded attempts và backoff ngoài transaction không?**
80. **Có phân loại permanent data error và transient DB error không?**
81. **Có metrics transaction duration/lock wait/pool pressure không?**
82. **Có tránh log raw SQL/PII/secrets không?**

### 28.9. Integration testing

83. **Có test success path stock/order/outbox cùng commit không?**
84. **Có test fail outbox làm rollback stock/order không?**
85. **Có test em.flush rồi rollback không để lại persisted row không?**
86. **Có test service method được gọi qua Spring proxy không?**
87. **Có test self-invocation regression không?**
88. **Có test checked exception rollbackFor không?**
89. **Có test UnexpectedRollbackException/rollback-only không?**
90. **Có test REQUIRES_NEW vs REQUIRED physical commits không?**
91. **Có test NESTED manager/savepoint support nếu dùng không?**
92. **Có test @Version concurrent updates không?**
93. **Có test idempotency key sequential và concurrent không?**
94. **Có test commit-time constraint failure ở outer boundary không?**
95. **Có test report read consistency với isolation đúng DB không?**
96. **Có test tenant-scoped queries và BOLA không?**
97. **Có test outbox consumer duplicate delivery không?**
98. **Có test saga compensation idempotent không?**
99. **Có test rollback không gửi external event trước commit không?**
100. **Có test trên DB/transaction manager gần production, không chỉ mock hoặc @DataJpaTest tự rollback không?**

## 29. Cây quyết định: chọn transaction ở đâu?

~~~text
                 Một use case cần truy cập dữ liệu
                              |
                              v
                    Có thay đổi DB không?
                       /            \
                     Không          Có
                       |             |
                       v             v
                Read-only query    Writes có cần
                hoặc read tx        cùng atomic?
                ngắn nếu cần       /         \
                                Có           Không
                                 |            |
                                 v            v
                       Cùng một DB/tx     Có thể chia
                       manager?          steps/chunks?
                         /      \            |
                       Có       Không        v
                       |          |      Mỗi step
                       v          v      transaction riêng
                Use-case tx   JTA/XA nếu phù hợp,
                bắt đầu       hoặc saga/outbox
                |
                v
      Authorize + validate input
                |
                v
      Load managed entities đúng tenant
                |
                v
      Domain methods / concurrency control
                |
                v
      Repository writes (không tự commit)
                |
                v
      Outbox trong cùng transaction
                |
                v
      COMMIT / ROLLBACK theo rules
                |
                +-- Success → trả committed result
                |
                +-- Permanent failure → business error
                |
                +-- Transient failure → rollback + new tx retry
                |
                +-- Unknown outcome → reconcile/idempotency
~~~

### 29.1. Một điểm quyết định quan trọng

Nếu có remote payment, email hay message broker, đừng vẽ một mũi tên “same transaction” đi xuyên qua chúng trừ khi thật sự có transaction protocol chung với documented guarantees. Thông thường nên chuyển sang **durable intent/outbox và workflow steps**.

### 29.2. Nếu business không cho phép partial success

Khi mọi rows cần atomic nhưng dataset quá lớn để một transaction thực hiện an toàn, cân nhắc staging:
1. Import từng chunk vào staging, có job ID;
2. Validate toàn bộ staging;
3. Chạy một finalization transaction chuyển/áp dữ liệu theo consistency policy;
4. Publish kết quả sau commit;
5. Dọn staging theo retention.

Staging/finalization không tự miễn phí: final merge vẫn có thể lớn, locks và concurrency cần được thiết kế. Nhưng nó cho phép tách *nhập dữ liệu lâu* khỏi *công bố state nhất quán* trong một số workflows.

## 30. Các câu hỏi review pull request

Khi review một PR thay đổi repository hoặc thêm @Transactional, nên hỏi:

1. Người dùng nghĩ operation này thành công ở thời điểm nào?
2. Có field/record nào có thể bị commit dù operation báo thất bại không?
3. Transaction được mở ở service/proxy/transaction manager nào?
4. Các repository calls có thực sự dùng cùng EntityManagerFactory/transaction manager không?
5. Một lời gọi inner REQUIRES_NEW có commit thứ gì không phụ thuộc outer không?
6. Lỗi checked exception có thể dẫn đến commit trái ý định không?
7. Catch block có che một transaction rollback-only không?
8. Constraint/optimistic error có xuất hiện sau khi method body return không?
9. Có network call giữa lúc giữ DB lock không?
10. Side effects có thể xuất hiện dù DB rollback không?
11. Có unique/idempotency constraints để chống duplicate requests không?
12. Có retry toàn transaction mới, thay vì retry SQL trong context lỗi không?
13. Multi-tenant query có lọc đúng scope không?
14. Test có thực sự commit và kiểm tra DB từ transaction mới không?
15. Nếu đổi database/provider/driver, semantics nào là JPA/Spring contract và semantics nào là DB-specific?

Một PR có thể rất ít dòng nhưng thay đổi propagation từ REQUIRED sang REQUIRES_NEW, làm đổi hoàn toàn atomicity. Những thay đổi như vậy cần review như **business consistency change**, không đơn thuần refactor.

## 31. Tổng kết

**Giữ ranh giới giao dịch tại nơi điều phối nghiệp vụ phù hợp** nghĩa là đặt quyết định commit/rollback ở nơi hiểu **đơn vị công việc**, không để các repository tự chia workflow thành nhiều commits ngoài ý muốn.

### 31.1. Cặp đối chiếu cần nhớ

Không phù hợp nếu yêu cầu là atomic:

~~~text
StockRepo.commit()
OrderRepo.commit()
OutboxRepo.commit()
~~~

Phù hợp:

~~~text
PlaceOrderUseCase transaction:
  - reserve stock
  - persist order
  - persist outbox
COMMIT tất cả hoặc ROLLBACK tất cả
~~~

### 31.2. Repository, domain và application service có trách nhiệm khác nhau

- **Repository:** Đọc/ghi aggregate, query và lưu entity theo persistence technology.
- **Domain:** Kiểm tra và thực hiện business state transitions.
- **Application service/coordinator:** Chọn trình tự use case, transaction scope, authorization và event intent.
- **Transaction manager:** Begin, commit, rollback và propagation.
- **Database:** Constraints, locking, isolation và durability.
- **Workflow/outbox:** Điều phối những bước ngoài local DB transaction.

### 31.3. Những điều @Transactional không tự giải quyết

- Không thay database UNIQUE/FK/CHECK;
- Không bảo đảm quyền truy cập đúng tenant;
- Không thay @Version/locking khi có concurrent writes;
- Không tự tạo atomicity qua nhiều local transaction managers/databases;
- Không rollback email/payment đã gửi;
- Không tự bảo đảm event exactly-once;
- Không ngăn self-invocation hoặc proxy bypass;
- Không tự xử lý commit outcome unknown;
- Không làm retries an toàn nếu thiếu idempotency;
- Không biến flush thành commit.

### 31.4. Công thức tư duy khi thiết kế

~~~text
1. Xác định một business unit of work.
2. Liệt kê writes/invariants cần atomic.
3. Đặt transaction tại coordinator của unit đó.
4. Để repositories tham gia cùng transaction.
5. Thực hiện authorization và domain validation.
6. Dùng DB constraints và concurrency control.
7. Không giữ transaction qua remote work.
8. Lưu outbox intent cùng business changes.
9. Propagate lỗi để rollback đúng.
10. Test trạng thái DB sau commit/rollback thực.
11. Với workflow dài, chia thành local transactions + saga.
12. Với retry/unknown outcome, dùng idempotency/reconciliation.
~~~

**Kết luận:** Transaction là hợp đồng nhất quán của nghiệp vụ, không chỉ là annotation của ORM. Một thiết kế Repository tốt khiến việc đọc/ghi dữ liệu rõ ràng, nhưng chính **use-case coordinator** mới biết những thay đổi nào phải cùng tồn tại. Khi boundary đúng, provider/JPA có thể flush/dirty-check như bình thường, database commit/rollback toàn bộ đơn vị công việc, còn những side effects ngoài DB được xử lý bằng workflow phù hợp. Nhờ đó hệ thống dễ kiểm thử, chống partial writes, phục hồi tốt và giữ được các business invariants khi số lượng repositories hoặc tích hợp bên ngoài tăng lên.

















