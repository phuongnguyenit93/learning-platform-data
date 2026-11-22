# Phân biệt repository nghiệp vụ và lớp bọc từng bảng

Trong ứng dụng Java dùng JPA, một thiết kế thường thấy là cứ có một bảng thì tạo một repository:

```text
Table customers         → CustomerRepository
Table orders            → OrderRepository
Table order_lines       → OrderLineRepository
Table order_status_logs → OrderStatusLogRepository
Table order_totals      → OrderTotalRepository
```

Nếu mỗi repository chỉ cung cấp `save`, `findById`, `findAll`, `deleteById`, người ta có thể tưởng đã xây dựng một **tầng truy cập dữ liệu đúng nghĩa nghiệp vụ**. Nhưng việc đặt tên `Repository` lên một tập phương thức CRUD chưa nói lên **ranh giới nhất quán**, **quy tắc nghiệp vụ**, **cách một use case tải và lưu một tập dữ liệu**, hay **đối tượng nào được phép thay đổi độc lập**.

Ví dụ một đơn hàng có ba dòng hàng. Nếu `OrderService` tự gọi:

```java
orderTableRepository.insert(orderRow);
orderLineTableRepository.insert(lineRow1);
orderLineTableRepository.insert(lineRow2);
orderLineTableRepository.insert(lineRow3);
orderTotalTableRepository.updateTotal(orderId, total);
```

thì ai chịu trách nhiệm giữ bất biến **“tổng tiền đơn hàng bằng tổng các dòng hàng, không có dòng hàng không thuộc đơn, và không được sửa đơn đã xác nhận”**? Nếu từng wrapper có transaction riêng, trạng thái trung gian có thể trở thành dữ liệu đã commit. Nếu tất cả logic được để ở service và nhiều tầng cùng sửa bảng, những quy tắc này dễ bị phân tán.

Repository theo nghĩa thiết kế miền nghiệp vụ không chỉ bọc SQL cho một bảng. Nó là **cổng truy cập một nhóm đối tượng miền có danh tính và vòng đời rõ**, thường theo **aggregate root**, cung cấp các operation phù hợp với use case và bảo vệ ranh giới lưu/truy xuất. Đối tượng sử dụng repository quan tâm tới **Order cần được xử lý**, chứ không cần tự điều phối các bản ghi `purchase_orders` và `order_lines`.

Bài **“Phân biệt repository nghiệp vụ và lớp bọc từng bảng”**, thuộc chương **Thiết kế Repository** trong chủ đề **Data Persistence Relational Access ORM JPA**, giải thích cách lựa chọn ranh giới repository và vận dụng với JPA/Spring Data JPA. Nội dung bao gồm mô hình aggregate, DAO, repository port/adapter, transactional consistency, lazy fetching, query projection, soft delete, optimistic locking, CQRS read model, testing và các trường hợp **không cần cố dùng repository theo aggregate**.

**Nguyên tắc cốt lõi:** thiết kế interface từ **ngôn ngữ nghiệp vụ và quyền thay đổi dữ liệu**, sau đó để JPA/SQL đảm nhiệm việc lưu trữ. Không suy một repository nghiệp vụ từ mỗi bảng vật lý.

---

## 1. Ba khái niệm thường bị trộn lẫn

Cần phân biệt ít nhất ba loại abstraction:

| Khái niệm | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Table gateway/DAO** | Đọc/ghi dữ liệu của một bảng hoặc nhóm câu SQL | `insertOrderRow`, `updateOrderLineRow` |
| **Repository nghiệp vụ** | Truy cập, lưu, tìm kiếm các aggregate/đối tượng miền được xác định bởi business boundary | `findOrderForChange`, `add`, `findPendingOrders` |
| **JPA persistence context** | Quản lý identity, lifecycle và unit of work của entity instances | `EntityManager.persist`, `find`, dirty checking, `flush` |

Ba khái niệm có thể hợp tác với nhau, nhưng không đồng nhất:

- Một repository nghiệp vụ có thể **dùng JPA EntityManager, nhiều DAO hoặc Spring Data JPA** ở bên trong.
- Một DAO/table gateway có thể rất hữu ích cho SQL reporting hoặc migration.
- `EntityManager` là API kỹ thuật cấp thấp; dùng trực tiếp không tự biến service thành repository nghiệp vụ.
- `JpaRepository<T, ID>` là một framework abstraction cung cấp CRUD cho một entity type; có thể làm **hạ tầng triển khai** một repository nghiệp vụ nhưng không tự đảm bảo aggregate design đúng.

**Đừng đánh giá kiến trúc bằng tên lớp.** Hãy xem trách nhiệm và public contract thực tế.

## 2. Vì sao một bảng không đồng nghĩa một khái niệm nghiệp vụ?

Một **bảng** là cấu trúc quan hệ. Một **entity JPA** là class được ORM ánh xạ. Một **đối tượng/aggregate miền** là đơn vị có identity, lifecycle và invariants nghiệp vụ.

Chúng có thể tương ứng, nhưng không bắt buộc 1:1.

```text
Domain aggregate:
PurchaseOrder
   ├── OrderLine #1
   ├── OrderLine #2
   └── OrderLine #3

Relational storage:
purchase_orders
order_lines
order_line_discounts
order_status_history

JPA object graph:
PurchaseOrder @Entity
   └── List<OrderLine> @OneToMany
         └── optional @Embeddable Money/Address
```

Một aggregate có thể trải nhiều bảng. Ngược lại, một bảng có thể phục vụ nhiều cách đọc hoặc một phần của một mô hình báo cáo mà không phải aggregate root độc lập.

### Ví dụ không nên ép 1:1

- `order_lines` lưu các dòng hàng nằm trong Order; nếu không có vòng đời độc lập, không cần public `OrderLineRepository` cho toàn application.
- `order_status_history` có thể là bảng append-only phục vụ audit và có query adapter riêng, không nhất thiết là aggregate có CRUD thông thường.
- `order_summary_view` là database view cho dashboard, không phải thứ phải `save()` như entity.
- `product` có identity/vòng đời/quy tắc riêng, nên một `ProductRepository` là hợp lý ngay cả khi Order tham chiếu Product.
- Một aggregate có thể lưu trên một bảng duy nhất nếu nghiệp vụ đơn giản.

**Ranh giới repository lấy từ hành vi và tính nhất quán, không phải số lượng bảng.**

## 3. Repository nghiệp vụ trả lời câu hỏi nào?

Trước khi tạo interface, hỏi:

1. Đối tượng nào có **danh tính nghiệp vụ** và được gọi tên trong use case?
2. Những thay đổi nào phải nhất quán với nhau sau một transaction?
3. Thành phần nào là **aggregate root**, đầu mối hợp lệ cho việc thay đổi?
4. Các thành phần con có được tạo/sửa/xóa độc lập không?
5. Người dùng của repository cần những **cách tìm kiếm** nào?
6. Những truy vấn nào chỉ để hiển thị báo cáo, không cần managed entity?
7. Transaction boundary nằm ở application service hay elsewhere?
8. Có yêu cầu tenant/authorization/soft-delete/version không?
9. Có ràng buộc dữ liệu nào phải được database bảo đảm thêm?
10. Nếu thay JPA bằng một backend khác, business use case cần giữ nguyên contract nào?

Nếu interface chỉ trả lời “bảng có các lệnh CRUD gì?”, nó đang thiên về table gateway. Nếu interface trả lời “use case cần tải/lưu aggregate như thế nào để giữ invariants?”, nó gần repository nghiệp vụ.

---

## 4. Aggregate root là gì?

Trong Domain-Driven Design (DDD), **aggregate** là một tập objects có ranh giới nhất quán. **Aggregate root** là đầu mối mà các bên ngoài sử dụng để truy cập và thay đổi aggregate theo rules.

Ví dụ:

```text
         [PurchaseOrder]        ← Aggregate root
          id
          tenantId
          status
          totalAmount
          version
             │
             ├── [OrderLine]    ← Entity con, không sửa tùy tiện từ ngoài
             │       productId
             │       quantity
             │       unitPrice
             │
             └── [OrderLine]
                     productId
                     quantity
                     unitPrice

         [Customer]             ← Aggregate root khác
         [Product]              ← Aggregate root khác
```

Một số invariants ví dụ:

- Không có OrderLine với số lượng `<= 0`.
- Tổng tiền của Order luôn bằng tổng tiền các lines theo quy tắc làm tròn đã thống nhất.
- Không thể thêm dòng hàng sau khi Order đã `CONFIRMED`.
- Không thể confirm một Order trống.
- Không thể đặt OrderLine thuộc tenant khác nếu nghiệp vụ định nghĩa các scoping rules đó.
- Một OrderLine không sống độc lập ngoài PurchaseOrder, nếu đó là quy tắc domain.

Các hành vi thay đổi nội bộ nên đi qua root:

```java
order.addLine(productId, quantity, unitPrice);
order.changeLineQuantity(lineId, quantity);
order.removeLine(lineId);
order.confirm();
```

Thay vì application service gọi `orderLineRepository.save(...)` và cập nhật `order.totalAmount` riêng.

**Đây là mô hình ví dụ**, không phải mọi ứng dụng thương mại đều dùng aggregate giống vậy. Một order có thể chứa hàng nghìn lines; khi đó boundary và consistency/performance trade-off cần thiết kế lại.

## 5. Vì sao aggregate root phù hợp làm đối tượng của repository?

Nếu repository trả về root có khả năng thực thi domain methods:

```java
PurchaseOrder order = orderRepository
    .findByIdForChange(tenantId, orderId)
    .orElseThrow(OrderNotFoundException::new);

order.confirm();
```

thì application layer không phải nhớ hàng loạt câu SQL cho các bảng phụ.

Một transaction phù hợp có thể làm các bước:

1. Repository tìm đúng aggregate root theo tenant.
2. Root áp business invariants khi nhận command.
3. JPA ghi nhận các thay đổi managed entities.
4. Provider flush SQL cho root và owned children theo mapping.
5. DB kiểm tra FK/UNIQUE/CHECK và optimistic version.
6. Transaction commit hoặc rollback cả unit of work.

Repository **không một mình đảm bảo toàn bộ tính nhất quán**. Domain logic, transaction boundary, mappings, database constraints và concurrency policy cùng tham gia.

## 6. Phản ví dụ: CRUD repository theo từng bảng

Thiết kế thuần bảng có thể trông như sau:

```java
interface OrderRowRepository {
    OrderRow insert(OrderRow row);
    void updateStatus(Long id, String status);
    void updateTotal(Long id, BigDecimal total);
}

interface OrderLineRowRepository {
    void insert(OrderLineRow line);
    void updateQuantity(Long lineId, int quantity);
    void delete(Long lineId);
}

interface OrderStatusRowRepository {
    void append(OrderStatusRow row);
}
```

Một service:

```java
void confirmOrder(Long orderId) {
    List<OrderLineRow> lines =
        orderLineRowRepository.findByOrderId(orderId);

    BigDecimal total = lines.stream()
        .map(OrderLineRow::lineTotal)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

    orderRowRepository.updateTotal(orderId, total);
    orderRowRepository.updateStatus(orderId, "CONFIRMED");
    orderStatusRowRepository.append(
        new OrderStatusRow(orderId, "CONFIRMED")
    );
}
```

Điểm yếu có thể xuất hiện:

- Service phải biết bảng nào chứa dữ liệu liên quan.
- Invariants phân tán giữa nhiều services.
- Một caller khác có thể gọi `updateStatus` mà bỏ bước tính total.
- Nếu từng method tự commit, không có atomicity.
- Các hàng có thể bị sửa cạnh tranh giữa lần SELECT lines và UPDATE status.
- Audit rows có thể được ghi khác transaction.
- Code phụ thuộc schema columns, không diễn đạt domain behavior.

**Không phải SQL/DAO là xấu.** Vấn đề là dùng table wrappers làm **contract nghiệp vụ chính** khiến các bất biến khó được bảo vệ ở một nơi.

---

## 7. Một ví dụ repository nghiệp vụ

Contract cho use cases thay đổi Order:

```java
public interface PurchaseOrderRepository {

    Optional<PurchaseOrder> findByIdForChange(
        Long tenantId,
        Long orderId
    );

    void add(PurchaseOrder order);

    boolean existsByOrderNumber(
        Long tenantId,
        String orderNumber
    );
}
```

Đây là một API có nghĩa nghiệp vụ:

- `findByIdForChange` nói rõ mục đích tải aggregate để thay đổi.
- `add` thể hiện tạo một Order mới, không bắt caller insert từng child row.
- `existsByOrderNumber` hỗ trợ validation/giao diện, **không thay unique constraint**.

Không cần public:

```java
void insertIntoOrderLine(...);
void updateOrderTableColumn(...);
void insertOrderStatusHistoryRow(...);
```

Contract cũng không nhất thiết phải phơi `EntityManager`, JPQL string, table names, `JdbcTemplate` hoặc `Pageable` của Spring vào domain layer.

### Có nên luôn dùng `add()` thay `save()`?

Không phải quy tắc tuyệt đối. `save()` có thể chấp nhận được nếu team định nghĩa rõ semantics. Nhưng `add()`/`store()`/`findForChange()` giúp đọc intent hơn trong một số domain.

Quan trọng nhất là **caller không tự ý sửa tables dưới aggregate mà bỏ business rules**.

## 8. Đặt tên theo ngôn ngữ nghiệp vụ

Một số tên hữu ích:

| Tên kỹ thuật chung | Tên diễn đạt mục đích hơn | Khi nào dùng |
| --- | --- | --- |
| `findAll` | `findAwaitingApproval` | Tìm Orders cần duyệt |
| `findById` | `findByIdForChange` | Load aggregate dùng cho command |
| `findByStatus` | `findOverduePayments` | Thể hiện truy vấn nghiệp vụ |
| `updateStatus` | `order.confirm()` | Đặt invariant vào domain method |
| `saveLine` | `order.addLine(...)` | Owned child chỉ thay đổi qua root |
| `delete` | `cancel` hoặc `archive` | Nếu hành động nghiệp vụ không phải xóa vật lý |
| `countAll` | `countPendingApprovals` | Metric được định nghĩa rõ |

Không biến tên phương thức thành một câu văn quá dài hoặc trộn rule tùy hứng. Tên nên phản ánh **khả năng truy cập từ use case** và **trạng thái có ý nghĩa của domain**.

## 9. Repository không phải nơi chứa toàn bộ nghiệp vụ

Một cực đoan khác là đẩy business rules vào repository:

```java
interface PurchaseOrderRepository {
    void validateDiscountsAndCallPaymentGatewayAndSendEmail(
        Long orderId
    );
}
```

Đây không còn là repository chuyên về truy cập aggregate. Nó đang trộn:

- Domain rule.
- External payment integration.
- Email.
- Transaction orchestration.
- Persistence.

Một phân chia dễ hiểu:

```text
Application service:
  điều phối use case / transaction / authorization
       │
       ▼
Domain aggregate:
  kiểm tra và thay đổi invariants
       │
       ▼
Domain repository contract:
  tìm, add, lưu/khôi phục aggregate theo nhu cầu
       │
       ▼
Infrastructure adapter:
  JPA / SQL / caching / database
```

Repository giải quyết **truy cập và lưu trữ**, không thay thế domain methods hoặc application-service orchestration.

---

## 10. Ví dụ JPA entity ánh xạ một aggregate

Giả sử `PurchaseOrder` là root; `OrderLine` chỉ có vòng đời trong Order.

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_no", nullable = false)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.DRAFT;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(Long tenantId, String orderNumber) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.orderNumber = Objects.requireNonNull(orderNumber);
    }

    public void addLine(
            Long productId,
            int quantity,
            BigDecimal unitPrice) {

        ensureDraft();
        OrderLine line = new OrderLine(
            this, productId, quantity, unitPrice
        );

        lines.add(line);
        recalculateTotal();
    }

    public void confirm() {
        ensureDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Cannot confirm an empty order"
            );
        }

        status = OrderStatus.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Order is no longer editable"
            );
        }
    }

    private void recalculateTotal() {
        totalAmount = lines.stream()
            .map(OrderLine::getLineTotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getOrderNumber() { return orderNumber; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Long getVersion() { return version; }
}
```

Ví dụ cần imports `jakarta.persistence.*`, `java.math.BigDecimal`, `java.util.*`. `OrderStatus` là enum `DRAFT, CONFIRMED`. Entity đang cố ý không có setter public cho status/totalAmount/lines để hạn chế đường thay đổi bỏ qua rules.

`OrderLine`:

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    OrderLine(
            PurchaseOrder order,
            Long productId,
            int quantity,
            BigDecimal unitPrice) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        if (unitPrice == null
                || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must be nonnegative"
            );
        }

        this.order = Objects.requireNonNull(order);
        this.productId = Objects.requireNonNull(productId);
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    BigDecimal getLineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }

    public Long getId() { return id; }
    public Long getProductId() { return productId; }
}
```

**Quan trọng:** đây là mapping minh họa, chưa bao gồm mọi rule về currency, tax, discount, rounding, immutable price snapshots và collection synchronization. `orphanRemoval=true` phù hợp khi line thật sự thuộc vòng đời Order; **không dùng cho đối tượng có lifecycle độc lập**.

## 11. Vì sao không cần `OrderLineRepository` ở public domain API?

Nếu chỉ Order được phép thêm/sửa/xóa lines, một repository để bên ngoài gọi:

```java
orderLineRepository.deleteById(lineId);
```

có thể cho phép xóa line khỏi một Order đã CONFIRMED, bỏ qua `order.ensureDraft()` và bỏ việc tính lại total. Những đường ghi khác nhau làm invariants khó kiểm soát.

Thay bằng:

```java
PurchaseOrder order = repository
    .findByIdForChange(tenantId, orderId)
    .orElseThrow();

order.removeLine(lineId);
```

`removeLine` sẽ xác minh trạng thái, xóa phần tử khỏi collection, cập nhật total và để mapping xử lý orphan deletion trong transaction.

Lưu ý code ví dụ trước chưa cài `removeLine`. Một implementation có thể là:

```java
public void removeLine(Long lineId) {
    ensureDraft();

    boolean removed = lines.removeIf(
        line -> Objects.equals(line.getId(), lineId)
    );

    if (!removed) {
        throw new IllegalArgumentException(
            "Unknown line in this order"
        );
    }

    recalculateTotal();
}
```

Đoạn này đặt trong `PurchaseOrder`. Trong production nên xem null IDs của lines mới, equality semantics và chỉ cho phép sửa một line thực sự thuộc Order. Nó minh họa nơi đặt invariant, không đòi mọi ứng dụng phải dùng collection mutation giống hệt.

## 12. Product và Customer là aggregate khác

Đừng kéo cả Product và Customer vào Order bằng `CascadeType.ALL` chỉ vì có association.

```text
PurchaseOrder
    ├── OrderLine (owned child)
    │       └── productId  → Product aggregate riêng
    └── customerId         → Customer aggregate riêng
```

Order thường cần **tham chiếu** Product/Customer nhưng không sở hữu vòng đời của chúng. Khi xóa Order không nên tự xóa Product hoặc Customer.

Có thể lưu ID hoặc dùng `@ManyToOne(fetch=LAZY)` **không cascade remove**, tùy domain model và persistence design. Reference by ID giúp ranh giới rõ, tránh vô tình hydrate/cascade graph qua nhiều aggregates, nhưng cũng có trade-off về type safety và truy vấn. Không phải mọi DDD model đều cấm JPA associations qua aggregates; quan trọng là **không cho phép một aggregate xóa/sửa vòng đời aggregate khác do cascade ngẫu nhiên**.

## 13. Chọn aggregate boundary dựa vào invariant, không phải luôn một object graph khổng lồ

Nếu PurchaseOrder có 300.000 lines, việc luôn load mọi line để sửa metadata sẽ rất tốn bộ nhớ. Khi đó cần hỏi:

- Những rules nào thật sự cần đồng bộ trong cùng transaction?
- Có thể giữ total/invariants bằng DB operations hoặc một aggregate khác không?
- Lines có được chỉnh độc lập trong workflow không?
- Có yêu cầu high-concurrency edits theo line không?
- Có thể tách command model và read model không?
- Có cần eventual consistency giữa bounded contexts không?

DDD aggregate **không đồng nghĩa gom mọi object có quan hệ FK vào một graph để JOIN FETCH**. Ranh giới phải đủ nhỏ để quản lý transactional consistency và concurrency thực tế.

---

## 14. Domain repository port và infrastructure adapter

Một cấu trúc theo ports-and-adapters:

```text
com.example.orders
├── domain/
│   ├── PurchaseOrder.java
│   ├── OrderLine.java
│   ├── OrderStatus.java
│   └── PurchaseOrderRepository.java     ← contract
├── application/
│   └── OrderApplicationService.java
└── infrastructure/
    └── persistence/
        ├── JpaPurchaseOrderRepository.java  ← adapter
        └── SpringDataOrderStore.java        ← JPA plumbing
```

Mũi tên phụ thuộc mong muốn:

```text
Application ──► Domain contract
                    ▲
                    │ implements
Infrastructure/JPA adapter
```

Domain contract không cần biết Spring Data JPA hay table names. Infrastructure module phụ thuộc contract, không ngược lại.

Đây là **một lựa chọn kiến trúc**, không phải yêu cầu của Jakarta Persistence. Với CRUD application nhỏ, có thể dùng Spring Data repository trực tiếp trong application service mà vẫn có chất lượng tốt nếu rules đơn giản.

## 15. Interface repository ở domain layer

```java
package com.example.orders.domain;

import java.util.Optional;

public interface PurchaseOrderRepository {

    Optional<PurchaseOrder> findByIdForChange(
        Long tenantId,
        Long orderId
    );

    void add(PurchaseOrder order);
}
```

Không import:

```java
org.springframework.data.domain.Pageable
org.springframework.data.jpa.repository.JpaRepository
jakarta.persistence.EntityManager
org.hibernate.Session
```

vào **domain port** nếu mục tiêu là tách miền khỏi framework.

Tuy nhiên, nếu `PurchaseOrder` tự dùng JPA annotations như ví dụ trên, domain model vẫn biết mapping metadata ở compile time. Đó là một **pragmatic domain entity** chứ không phải persistence ignorance tuyệt đối. Muốn tách hoàn toàn có thể dùng domain POJO riêng và JPA mapping entity riêng, nhưng phải trả chi phí mapping giữa hai models.

**Không cần thiết kế cùng một mức độ isolation cho mọi dự án.**

## 16. Spring Data JPA làm adapter hạ tầng

Một interface kỹ thuật:

```java
package com.example.orders.infrastructure.persistence;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

interface SpringDataOrderStore
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByIdAndTenantId(
        Long id, Long tenantId
    );
}
```

Adapter triển khai domain port:

```java
package com.example.orders.infrastructure.persistence;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.domain.PurchaseOrderRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public class JpaPurchaseOrderRepository
        implements PurchaseOrderRepository {

    private final SpringDataOrderStore store;

    public JpaPurchaseOrderRepository(
            SpringDataOrderStore store) {
        this.store = store;
    }

    @Override
    public Optional<PurchaseOrder> findByIdForChange(
            Long tenantId,
            Long orderId) {

        return store.findByIdAndTenantId(
            orderId, tenantId
        );
    }

    @Override
    public void add(PurchaseOrder order) {
        store.save(order);
    }
}
```

Với `PurchaseOrder` có generated ID và là entity mới, `JpaRepository.save` thông thường sẽ chọn `persist` theo chính sách phát hiện entity mới của Spring Data JPA; với entity được xem là existing, nó có thể dùng `merge`. **Không đồng nhất `save` với SQL INSERT/UPDATE ngay lập tức hoặc database commit.** Transaction boundary do caller/application service quản lý.

### Vì sao không expose trực tiếp `SpringDataOrderStore`?

Vì nếu application inject một interface kế thừa `JpaRepository`, nó có quyền gọi hàng loạt operations như `deleteAll`, `saveAll`, `findAll`, `getReferenceById`. Trong một domain nhiều invariants, việc đó có thể cho phép bypass use-case contract.

Đặt store ở infrastructure/package-private giúp cô lập operations được phép, còn adapter public contract chỉ expose những method cần. Với package scanning của Spring Data, cần cấu hình tìm repository interfaces đúng package và tương thích visibility của framework/provider hiện hành.

## 17. Có thể bỏ lớp adapter không?

**Có**, nếu yêu cầu hệ thống đơn giản và lợi ích của một port riêng không đáng bằng boilerplate.

Ví dụ:

```java
public interface PurchaseOrderJpaRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByIdAndTenantId(
        Long id, Long tenantId
    );
}
```

Application service dùng trực tiếp có thể phù hợp khi:

- Ứng dụng CRUD nhỏ.
- Domain rules ít.
- Không có nhu cầu thay persistence technology.
- Team cố tình chọn Spring-centric architecture.
- Không có nhiều cách ghi bypass invariants.
- Hệ thống cần phát triển nhanh và dễ bảo trì.

Điều quan trọng là **quyết định có ý thức**. “Repository nghiệp vụ” không nên được hiểu là bắt buộc thêm một interface+adapter cho mọi entity, kể cả nơi chúng chỉ chuyển tiếp CRUD.

## 18. Đừng tạo abstraction chỉ để chuyển tiếp một dòng

Một anti-pattern kiến trúc khác:

```java
@Service
class OrderService {
    OrderRepository repo;

    Order find(Long id) {
        return repo.findById(id).orElseThrow();
    }

    Order save(Order order) {
        return repo.save(order);
    }
}
```

Nếu service không định nghĩa use case, transaction, authorization hoặc business behavior, nó chỉ là pass-through layer. Thêm layer không tạo giá trị chỉ vì sơ đồ kiến trúc có đủ ô.

Một application service hợp lý nên diễn đạt thao tác như:

```java
placeOrder(...)
confirmOrder(...)
cancelOrder(...)
changeOrderLineQuantity(...)
```

và điều phối repository cùng domain methods.

---

## 19. Application service là nơi đặt transaction boundary

Ví dụ Spring:

```java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(
            PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void confirmOrder(
            Long tenantId, Long orderId) {

        PurchaseOrder order = orders
            .findByIdForChange(tenantId, orderId)
            .orElseThrow(OrderNotFoundException::new);

        order.confirm();
        // Managed entity: JPA dirty checking ở flush/commit.
    }

    @Transactional
    public Long placeOrder(
            Long tenantId,
            String orderNumber,
            List<LineCommand> lines) {

        PurchaseOrder order = new PurchaseOrder(
            tenantId, orderNumber
        );

        for (LineCommand line : lines) {
            order.addLine(
                line.productId(),
                line.quantity(),
                line.unitPrice()
            );
        }

        orders.add(order);

        return order.getId();
    }
}
```

Ví dụ giả định `LineCommand` là record với các accessors trên, và `OrderNotFoundException` là custom runtime exception. `@Transactional` method phải được gọi qua Spring proxy để transaction interceptor hoạt động theo proxy-based configuration.

Với `GenerationType.IDENTITY`, ID thường có sau `persist` vì provider cần INSERT để lấy generated key; nhưng **không suy ID được trả về nghĩa transaction commit thành công**. Nếu commit ở proxy boundary thất bại, caller sẽ nhận lỗi; side effects đã phát ra ngoài DB trước commit không tự được hoàn tác.

### Ai gọi `save()` sau `order.confirm()`?

Với managed entity được tải trong transaction, JPA dirty checking thường tự đồng bộ thay đổi ở flush/commit. Một method `save(order)` tường minh có thể không cần cho update đó.

Tuy vậy, team có thể chọn convention gọi `save` cho rõ intent. Đừng nhầm convention này với điều kiện bắt buộc để JPA update managed entity. Và đừng gọi `merge` mù quáng trên stale detached data chỉ để “chắc chắn lưu”.

## 20. Repository không nên tự mở transaction cho từng bảng

Anti-pattern:

```java
void addOrder(OrderRow order) {
    begin();
    insertOrder(order);
    commit();
}

void addLine(OrderLineRow line) {
    begin();
    insertLine(line);
    commit();
}
```

Một use case tạo đơn với ba dòng có thể commit Order rồi lỗi ở Line thứ hai → dữ liệu nửa chừng. Thay vì transaction mỗi table operation, **application use case** thường cần một transaction bao quanh toàn bộ consistency unit.

Trong Spring, repository methods có thể được cấu hình transaction, nhưng khi gọi từ một outer application `@Transactional` với propagation REQUIRED, chúng thường cùng tham gia outer transaction. Cần hiểu propagation và tránh mặc định mỗi repository method có một commit riêng.

Nếu thao tác vượt một transaction dài (ví dụ payment gateway, inventory service ngoài hệ thống), cần mô hình saga/outbox/eventual consistency, không kéo một database transaction xuyên mọi network call.

## 21. Repository load aggregate thế nào?

Một câu hỏi quan trọng là repository khi `findByIdForChange` có cần tải tất cả lines không.

Nếu `order.confirm()` kiểm tra `lines.isEmpty()`, cần bảo đảm operation chạy trong transaction/context còn mở và collection được load khi cần.

Có thể dùng:

```java
@EntityGraph(attributePaths = "lines")
Optional<PurchaseOrder> findByIdAndTenantId(
    Long id, Long tenantId
);
```

hoặc explicit fetch query:

```java
@Query("""
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    WHERE o.id = :id
      AND o.tenantId = :tenantId
    """)
Optional<PurchaseOrder> findForChange(
    @Param("id") Long id,
    @Param("tenantId") Long tenantId
);
```

`@EntityGraph` và `@Query` ở đây thuộc Spring Data JPA. Graph/fetch query có thể tăng SQL row width và làm nhiều lines được materialize; **không có bảo đảm mọi EntityGraph chỉ phát một SQL**.

Với một Order có ít lines và use case cần toàn lines, fetch to-many có thể phù hợp. Với list 1000 Orders và nhiều collections, cách này có thể gây row explosion hoặc pagination problems.

## 22. Repository không phải một graph loader vô hạn

Một số code xem repository là:

```java
Order findOrderWithEverything(Long id);
```

và cố tải:

- Order.
- Lines.
- Product.
- Customer.
- Payments.
- Discounts.
- Shipment.
- Audit log.
- Notifications.
- Returns.

Điều đó thường trộn nhiều aggregates/bounded contexts và tạo chi phí lớn:

- Rất nhiều joins.
- Cartesian product nếu fetch nhiều collections.
- N+1 ở paths không được fetch.
- Heap lớn.
- Lock/transaction duration tăng.
- Identity map chứa nhiều entities không cần.
- Bất biến consistency bị hiểu nhầm là cần cả graph.

**Chỉ tải dữ liệu mà use case thật sự cần để thực hiện đúng rule.** Một repository có thể có nhiều query methods hoặc phối hợp với read model riêng.

---

## 23. CRUD của Spring Data là công cụ, không phải domain model

`JpaRepository<PurchaseOrder, Long>` cung cấp nhiều phương thức hữu ích:

```java
save(entity)
saveAll(entities)
findById(id)
findAll()
existsById(id)
delete(entity)
deleteById(id)
flush()
saveAndFlush(entity)
```

Chúng làm giảm boilerplate, nhưng không tự biết:

- Order có được confirm hay chưa.
- Có được xóa Order đã giao hàng không.
- Tenant có quyền truy cập Order này không.
- Có cần tạo audit event không.
- Có phải giữ total bằng tổng lines không.
- Có cần version check từ HTTP request không.
- Có phải giữ payment state nhất quán không.

Do đó, public use-case API không nên mặc định là danh sách tất cả method của `JpaRepository`. **Tận dụng framework implementation, giới hạn domain capabilities bằng contract và business rules.**

## 24. Khi nào nên có repository riêng cho một entity?

Một entity JPA nên có repository nghiệp vụ riêng nếu nó thực sự là aggregate root hoặc có vòng đời độc lập.

Ví dụ:

```text
Product
  - Catalog manager chỉnh Product
  - Product có identity/availability riêng
  - Product có lifecycle riêng

PurchaseOrder
  - Buyer đặt Order
  - Order có OrderLines và trạng thái riêng
  - Order có version/consistency boundary riêng

Customer
  - Được onboard/update độc lập
  - Có quyền riêng, có thể tồn tại không có Order
```

Ba repository hợp lý:

```java
ProductRepository
PurchaseOrderRepository
CustomerRepository
```

Không phải vì đúng ba bảng, mà vì có **ba aggregate roots** với các use cases khác nhau.

Nếu entity `OrderLine` sau này trở thành đơn vị fulfillment với lifecycle độc lập, cần **đánh giá lại aggregate boundary**. Việc thêm repository mới khi business model thay đổi là bình thường; không cần cố giữ thiết kế ban đầu mãi.

## 25. Khi nào table DAO hợp lý hơn domain repository?

Các trường hợp:

- Báo cáo SQL read-only.
- ETL/import/export dữ liệu lớn.
- Batch reconciliation theo rows.
- Database migration/backfill.
- Reporting/projection từ nhiều bảng.
- Materialized view hoặc summary table.
- Search index ingestion.
- Một stored procedure giàu SQL.
- Legacy module có table-centric workflows rõ.
- Dữ liệu cấu hình đơn giản, gần như chỉ CRUD.
- Internal maintenance tooling cần truy cập bảng có kiểm soát.

Một class `OrderReportDao` với native SQL trả DTO có thể là thiết kế tốt hơn việc ép một `OrderRepository` nạp hàng triệu managed entities rồi tính tổng ở Java.

Vấn đề không phải “DAO là xấu”, mà là **dùng DAO để cho phép mọi caller sửa dữ liệu của một aggregate mà bỏ qua invariants**.

---

## 26. Repository ghi khác repository đọc

Với command side:

```java
PurchaseOrderRepository
    findByIdForChange(...)
    add(...)
```

Với query side:

```java
OrderQueryRepository
    searchOrderSummaries(...)
    findDailySales(...)
    findCustomerOrderHistory(...)
```

Read queries có thể trả DTO/projection và không cần managed aggregate.

```text
Command path
HTTP command → Application service → Aggregate
                                 → Business repository → JPA write

Query path
HTTP query   → Query service → Read repository/DAO
                             → SQL/JPQL projection → DTO
```

Đây là **phân tách command/query ở mức vừa phải**, không bắt buộc triển khai toàn bộ CQRS với event sourcing và hai database. Bạn có thể chỉ cần hai interface dùng chung một database.

## 27. Vì sao read model không nhất thiết theo aggregate root?

Trang dashboard cần:

```text
Order ID
Created time
Customer display name
Order total
Paid amount
Shipment status
```

Dữ liệu có thể nằm ở nhiều aggregates và tables. Nếu dùng `findOrderWithEverything` rồi serialize entities:

- Tải nhiều fields không dùng.
- Tạo managed entities không cần chỉnh sửa.
- Kích hoạt N+1.
- Dễ serialize lazy proxies.
- Tăng memory/GC.
- Phơi domain structure ra API.

Một DTO query trực tiếp có thể phù hợp hơn. Điều này **không phá aggregate boundary**, vì query read-only không sửa invariants của aggregates.

## 28. Ví dụ DTO projection cho danh sách Orders

DTO:

```java
package com.example.orders.application.query;

public record OrderSummary(
    Long id,
    String orderNumber,
    BigDecimal totalAmount,
    OrderStatus status
) {}
```

Spring Data JPA:

```java
public interface OrderQueryStore
        extends Repository<PurchaseOrder, Long> {

    @Query("""
        SELECT new com.example.orders.application.query.OrderSummary(
            o.id,
            o.orderNumber,
            o.totalAmount,
            o.status
        )
        FROM PurchaseOrder o
        WHERE o.tenantId = :tenantId
        ORDER BY o.id DESC
        """)
    List<OrderSummary> findRecent(
        @Param("tenantId") Long tenantId,
        Pageable pageable
    );
}
```

Đây là ví dụ interface projection query cụ thể dùng Spring Data types `Repository` và `Pageable`. Method trả `List` có thể nhận Pageable để áp giới hạn và offset tùy provider/framework; với API cần tổng số records, dùng Page/Count query phù hợp. Không dùng `SELECT o` nếu DTO chỉ cần 4 fields.

Trong một domain port không muốn phụ thuộc Spring, có thể dùng `OrderSearchCriteria` và `Slice<OrderSummary>` thuộc ứng dụng, rồi adapter chuyển sang Spring Pageable.

## 29. Pagination là một phần của contract đọc

Một repository method:

```java
List<PurchaseOrder> findAllConfirmedOrders();
```

có thể gây vấn đề nếu hệ thống có 5 triệu Orders.

Các câu hỏi:

- User thực sự cần bao nhiêu rows?
- Có giới hạn page size?
- ORDER BY có tie-breaker ổn định?
- Dùng OFFSET hay keyset?
- Có cần total count?
- Query chỉ read-only DTO hay managed entities?
- Index có phù hợp WHERE/ORDER BY?
- Có tenant/soft-delete filters?
- Có đọc toàn collection với JOIN FETCH cùng pagination không?

Một repository thiết kế theo use case nên **đặt giới hạn dữ liệu hợp lý**, thay vì mặc định trả toàn bộ bảng.

## 30. Pagination + fetch join to-many không đơn giản

JPQL:

```java
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.id DESC
```

kết hợp `setMaxResults(20)` hoặc Pageable có thể gây vấn đề: mỗi Order có nhiều Lines nên 20 SQL rows không nhất thiết là 20 Orders. Một số phiên bản Hibernate có thể phân trang trong memory hoặc fail khi cấu hình cảnh báo thành exception.

Với list read-only, DTO projection thường tốt hơn. Nếu thật sự cần graph của 20 Orders:

1. Page IDs trước.
2. Fetch Orders/Lines theo tập IDs.
3. Khôi phục thứ tự IDs ở application, vì `IN` không bảo đảm order.
4. Đo số rows/bytes/SQL count.
5. Kiểm tra consistency nếu hai queries chạy trong điều kiện concurrent writes.

Repository business không nên âm thầm trả 20 root entities sau khi DB đã load hàng triệu joined rows.

---

## 31. Repository chịu trách nhiệm tenant scope ở đâu?

Một anti-pattern:

```java
Optional<PurchaseOrder> findById(Long orderId);
```

sau đó service nào cũng tự nhớ:

```java
if (!order.getTenantId().equals(currentTenantId)) {
    throw new ForbiddenException();
}
```

Nếu một caller quên, có nguy cơ truy cập chéo tenant.

Một contract rõ:

```java
Optional<PurchaseOrder> findByIdForChange(
    Long tenantId, Long orderId
);
```

Adapter áp predicate:

```java
findByIdAndTenantId(orderId, tenantId)
```

Tuy nhiên, tenant scope không nhất thiết là toàn bộ authorization: còn quyền sở hữu người dùng, role, trạng thái, organization membership. Có thể đặt checks ở application policy/domain service, và database Row Level Security nếu phù hợp. **Repository tenant-scoped giúp giảm nguy cơ quên filter nhưng không thay toàn bộ authorization.**

## 32. Soft delete cần được mô tả bằng semantics nghiệp vụ

Giả sử Order có `deletedAt`. Khi nghiệp vụ nói “hủy Order”, không nhất thiết đồng nghĩa xóa row:

- Cancelled Order vẫn cần audit.
- Payment đã nhận cần retention.
- Fulfillment vẫn cần biết.
- Fraud/compliance yêu cầu giữ lịch sử.
- Soft-delete có thể là một thao tác quản trị khác.

Đừng dùng bừa:

```java
repository.deleteById(id);
```

nếu operation thực sự là `order.cancel(reason)`.

Repository có thể ẩn các rows soft-deleted trong queries mặc định theo policy, nhưng cần phân biệt:

- `cancel`: business state transition.
- `archive`: retention/read visibility policy.
- `softDelete`: storage policy.
- `delete`: physical deletion.

Khi database có FK/UNIQUE/partial index, những trạng thái này cũng ảnh hưởng data integrity và query performance.

## 33. ID dạng `Long` có đủ diễn đạt domain không?

`Long` thuận tiện cho JPA, nhưng dễ truyền nhầm:

```java
repo.findByIdForChange(customerId, orderId);
```

Một thiết kế có thể dùng value objects:

```java
record TenantId(long value) {}
record OrderId(long value) {}
record ProductId(long value) {}
```

và port:

```java
Optional<PurchaseOrder> findByIdForChange(
    TenantId tenantId,
    OrderId orderId
);
```

Adapter chuyển value objects sang DB types.

Tuy nhiên:

- Dùng custom ID value objects với JPA `@Id` cần mapping/converter/embeddable strategy phù hợp.
- Không thêm quá nhiều types chỉ để thể hiện kiến trúc trong dự án CRUD cực nhỏ.
- Vẫn phải validate tenant/ownership ở boundary.

Ý nghĩa: **interface nghiệp vụ có thể dùng types biểu đạt domain**, thay vì buộc callers biết column/key implementation.

---

## 34. Transaction boundaries không phải repository method boundaries

Một use case confirm Order và tạo audit record:

```java
@Transactional
public void confirmOrder(Long tenantId, Long orderId) {
    PurchaseOrder order = orders
        .findByIdForChange(tenantId, orderId)
        .orElseThrow();

    order.confirm();

    auditRepository.append(
        OrderConfirmedEvent.from(order)
    );
}
```

Nếu cùng database transaction và audit record là dữ liệu cần atomic với Order, transaction của application service bao cả hai operations.

Nhưng nếu `auditRepository` sử dụng DataSource khác hoặc `REQUIRES_NEW`, atomicity không còn tự bảo đảm. Với messaging, dùng outbox/saga nếu cần consistency xuyên hệ thống.

**Repository không tự đảm bảo mọi call ở cùng transaction.** Application architecture phải định nghĩa transaction owner và connection/transaction manager.

## 35. Domain invariants và database constraints bổ trợ nhau

Trong `PurchaseOrder.addLine`:

```java
if (quantity <= 0) {
    throw new IllegalArgumentException(
        "Quantity must be positive"
    );
}
```

Database cũng có thể có:

```sql
ALTER TABLE order_lines
ADD CONSTRAINT ck_order_line_quantity
CHECK (quantity > 0);
```

Lý do cần cả hai:

- Domain method cho lỗi sớm, dễ giải thích.
- Database bảo vệ khi có native SQL, bulk DML, ETL và code legacy.
- Database UNIQUE ngăn race mà `exists` check không giải quyết.
- FK bảo vệ references.
- Optimistic version bảo vệ concurrent updates khi JPA dùng version-aware writes.

**Repository theo aggregate không thay thế ràng buộc database.** Càng nhiều đường viết dữ liệu khác ORM, DB constraints càng quan trọng.

## 36. `existsBy...` trước `save()` không đảm bảo duy nhất

Code:

```java
if (orders.existsByOrderNumber(tenantId, number)) {
    throw new DuplicateOrderNumberException();
}

orders.add(order);
```

Hai transactions có thể cùng thấy “chưa tồn tại” rồi cùng insert. Cần database UNIQUE:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uq_order_tenant_no
UNIQUE (tenant_id, order_no);
```

`existsByOrderNumber` có thể cải thiện UX bằng thông báo sớm, nhưng unique constraint mới là hàng rào ở mức database. Khi race xảy ra, transaction có thể fail ở `flush`/`commit`; application boundary cần translate lỗi thành domain conflict phù hợp.

Không thể coi một pre-check là khóa đồng bộ đáng tin cậy.

## 37. Optimistic locking thuộc ranh giới cập nhật aggregate

Root:

```java
@Version
private Long version;
```

Giả sử:

```text
Transaction A load Order version 3
Transaction B load Order version 3

A confirm Order, commit → version 4
B change Order, flush/commit → stale version conflict
```

JPA provider có thể ném `OptimisticLockException` hoặc wrapper ở flush/commit. Spring có thể dịch sang các exception cạnh tranh tương ứng.

Một repository nghiệp vụ có thể expose version-aware commands hoặc load managed entity rồi để `@Version` bảo vệ writes. Nhưng cần kiểm tra thật:

- Owned child updates có làm root version tăng theo provider/mapping không?
- Bulk JPQL UPDATE có bỏ version checking không?
- Client request đang dựa vào version nào?
- Có optimistic retry trong transaction mới không?
- Business conflict cần trả HTTP 409/412 không?

Không tự suy mọi thay đổi OrderLine chắc chắn làm Order root version tăng trên mọi provider. Nếu invariant cần serializing mọi modifications thuộc aggregate, **thiết kế root version/locking strategy và integration tests phù hợp**.

## 38. Pessimistic locking khi cần

Một operation tranh chấp cao có thể dùng:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("""
    SELECT o
    FROM PurchaseOrder o
    WHERE o.id = :id
      AND o.tenantId = :tenantId
    """)
Optional<PurchaseOrder> findLocked(
    @Param("id") Long id,
    @Param("tenantId") Long tenantId
);
```

Đây là Spring Data JPA annotation và JPA lock mode. Cần transaction active và behavior tùy DB.

Nhược điểm: locks kéo dài, deadlock/timeout, contention. Không đặt `PESSIMISTIC_WRITE` mặc định cho mọi repository method “để an toàn” nếu workloads chủ yếu read-only.

Repository contract có thể đặt tên `findForExclusiveChange` hoặc method tương ứng, nhưng không nên giấu một lock rất đắt trong phương thức có tên vô hại `findById` mà caller không biết.

## 39. Đừng return entity/proxy tùy tiện qua HTTP boundary

Nếu controller trả trực tiếp:

```java
return orderRepository.findById(orderId);
```

JSON serializer có thể:

- Kích hoạt lazy loading.
- Phát N+1.
- Gặp `LazyInitializationException` ngoài transaction.
- Tạo recursion trong bidirectional associations.
- Trả lộ tenant/internal fields.
- Dính optimistic/version metadata không cần.
- Trả graph rất lớn hoặc sensitive.

Repository nghiệp vụ có thể trả managed entity cho application service trong transaction, nhưng API nên tạo **response DTO rõ fields**. Đừng biến entity mappings thành public HTTP contract.

---

## 40. `save()` trong Spring Data JPA thực sự làm gì?

Khi dùng `JpaRepository.save(entity)`, Spring Data JPA thường phân biệt entity mới và entity đã tồn tại theo chiến lược xác định “new” rồi gọi `EntityManager.persist` hoặc `merge`.

Hệ quả:

- `save` không tự nghĩa transaction đã commit.
- `persist` làm entity mới managed.
- `merge` trả managed copy, object passed-in có thể vẫn detached.
- Provider có thể gửi INSERT/UPDATE sớm hoặc chờ flush.
- IDENTITY generation có thể khiến INSERT sớm.
- Version/constraint errors có thể xuất hiện ở flush/commit.
- Với managed entity trong transaction, dirty checking thường đủ.
- Với detached graph từ client, merge mù quáng có thể ghi đè fields không được gửi hoặc stale state.

**Không nên nhận nguyên JSON entity graph từ client rồi `save` trực tiếp** khi domain có invariants/authorization.

## 41. Command DTO và domain behavior

Một API nhận:

```java
public record ConfirmOrderCommand(
    Long tenantId,
    Long orderId,
    Long expectedVersion
) {}
```

Application:

```java
@Transactional
public void confirmOrder(ConfirmOrderCommand command) {
    PurchaseOrder order = repository
        .findByIdForChange(
            command.tenantId(),
            command.orderId()
        )
        .orElseThrow();

    if (!Objects.equals(
            command.expectedVersion(),
            order.getVersion())) {
        throw new StaleOrderException();
    }

    order.confirm();
}
```

Pre-check giúp trả domain conflict sớm. Nhưng **pre-check không thay `@Version`**: giữa lúc check và commit vẫn có transaction khác cập nhật. Database/JPA optimistic version ở flush/commit phải là cơ chế chống lost update cuối cùng.

Các imports/classes custom cần được triển khai. Với web, version có thể truyền qua ETag/If-Match, nhưng phải ánh xạ chính xác tới version của aggregate và trả HTTP semantics phù hợp.

## 42. Không để repository quyết định mọi status transition

Một method:

```java
orderRepository.updateStatus(orderId, "CONFIRMED");
```

đưa logic state transition ra khỏi aggregate. Nó có thể bỏ qua:

- Order không được rỗng.
- Payment rule.
- Total invariant.
- Allowed transitions.
- Domain events.
- Version checking.
- Audit requirement.

Tốt hơn nếu operation domain:

```java
order.confirm();
```

và repository chỉ lưu các changes.

Trong một số workloads rất lớn, bulk status updates có thể được thiết kế như command SQL chuyên dụng; khi đó cần **cố tình tái hiện những invariant/callback/version checks cần thiết** bằng SQL/domain policy. Không xem bulk DML đơn giản là cách thay tự động một method nghiệp vụ.

---

## 43. Bulk JPQL UPDATE là trường hợp vượt qua entity lifecycle

Ví dụ:

```java
@Modifying
@Query("""
    UPDATE PurchaseOrder o
    SET o.status = :status
    WHERE o.tenantId = :tenantId
      AND o.id IN :ids
    """)
int bulkSetStatus(
    @Param("tenantId") Long tenantId,
    @Param("ids") Collection<Long> ids,
    @Param("status") OrderStatus status
);
```

Đây là Spring Data/JPA bulk update. Những khác biệt quan trọng:

- Không gọi domain `order.confirm()` cho từng aggregate.
- Không dùng dirty checking của managed entity theo cách thông thường.
- Lifecycle callbacks có thể không được gọi per entity.
- Có thể không tự check/increment optimistic version.
- Persistence context hiện có có thể chứa stale entities.
- Query có thể vi phạm business transitions nếu chỉ filter ID.
- Số rows thực sự cập nhật cần được kiểm tra.

Nếu nghiệp vụ cho phép mass transition dựa vào điều kiện SQL rõ, cần thiết kế riêng và test invariants/race conditions. **Đừng ẩn bulk update dưới tên “saveOrder” khiến caller tưởng giống managed entity update.**

## 44. Delete và cascade semantics trong aggregate

Nếu `PurchaseOrder` có `orphanRemoval=true` cho Lines, `order.removeLine(...)` có thể xóa owned child row khi flush.

Nhưng `repository.deleteById(orderId)` sẽ xóa root và có thể cascade, tùy mapping/schema; nó không tự kiểm tra business rule “đơn đã giao hàng không được xóa”.

Một contract tốt có thể phân biệt:

```java
void removeDraftOrder(...);
void archiveOrder(...);
void deleteExpiredTemporaryOrder(...);
```

Tuy vậy, không nhất thiết method xóa phải nằm trong repository: nghiệp vụ thường tốt hơn qua `order.cancel()` và persistence of status change. Chỉ physical deletion operations cần một persistence method rõ ràng, có authorization/retention policy và transaction.

## 45. Audit/event logging có thể cần repository khác

Một Order xác nhận có thể tạo `OrderConfirmed` event. Có hai kiểu:

- **Domain event**: mô tả sự kiện nghiệp vụ.
- **Audit/persistence log**: lưu lịch sử hoặc outbox record.

Nếu cần atomicity với update Order, application service/unit of work có thể persist Order và outbox row cùng transaction. Nếu logs là append-only và độc lập, một DAO/event store adapter riêng là hợp lý.

Không buộc audit table thành entity con trong graph của Order chỉ vì foreign key, cũng không gửi message ra network trước commit rồi tin rollback sẽ thu hồi nó.

---

## 46. Repository là collection abstraction nhưng không phải collection thật

Trong DDD, repository thường được mô tả như một collection-like interface cho aggregates:

```java
repository.add(order);
repository.findById(id);
repository.remove(order);
```

Tuy nhiên, database operations có đặc điểm mà in-memory collection không có:

- SQL có latency và lock behavior.
- Query kết quả có thể chưa load associations.
- Transaction có thể rollback.
- Constraints có thể fail ở flush/commit.
- Optimistic conflict có thể xuất hiện.
- Pagination/query timeouts.
- Entity identity tied to persistence context.
- Database có concurrent writers.
- Failover và connection errors.

Không thiết kế interface hứa “instant immutable in-memory collection semantics” nếu implementation phải xử lý DB thực.

Repository abstraction nên **giấu hạ tầng không cần thiết** nhưng không được **che mất các đặc tính correctness/performance quan trọng**.

## 47. Repository không nên trả `Stream<Entity>` vô điều kiện

Một method:

```java
Stream<PurchaseOrder> findAll();
```

có thể yêu cầu giữ EntityManager/transaction/connection mở trong suốt quá trình tiêu thụ stream. Một số JPA implementations có thể materialize toàn bộ results thay vì streaming bounded.

Nếu ứng dụng export triệu Orders, có thể cần:

- Chunked DTO projection.
- Cursor/stream với lifecycle rõ.
- Keyset pagination.
- JDBC batching cho writes.
- Stateless provider APIs khi phù hợp.
- Backpressure/restart checkpoints.
- Không giữ persistence context khổng lồ.

Một repository theo domain không bắt buộc mọi report đi qua managed aggregate entities.

## 48. Transaction outcome vẫn có thể lỗi sau repository return

```java
orders.add(order);
// Method add() hoàn tất nhưng transaction chưa commit.
```

JPA/DB có thể ném lỗi ở flush/commit:

- UNIQUE violation.
- FK/CHECK constraint.
- Optimistic version conflict.
- Lock wait/timeout.
- Connection failure.
- Deferred constraint.

Application service/proxy boundary phải xử lý exception và translate thành domain/API error phù hợp. **Repository không nên tuyên bố “đã lưu vĩnh viễn” chỉ vì gọi `save()` thành công**.

## 49. Phân loại exceptions theo tầng

| Tầng | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Domain rule | `CannotConfirmEmptyOrder` | Trả business validation error |
| Aggregate not found | `OrderNotFound` | 404/hidden by policy |
| Optimistic conflict | `OptimisticLockException` | Conflict/retry policy với transaction mới |
| DB integrity | UNIQUE/FK/CHECK | Translate có chọn lọc; không catch mọi lỗi thành conflict |
| Infrastructure | Connection timeout | Retry có giới hạn/idempotency hoặc failure handling |
| Authorization | Tenant/permission denied | Enforce trước thao tác; không tiết lộ data |

Không để domain layer import mọi exception của Hibernate chỉ để biết "Order bị trùng". Infra adapter/application boundary có thể translate provider-specific failures; với lỗi chỉ xuất hiện khi Spring transaction interceptor commit, translation phải được đặt **ở boundary bao được commit**.

---

## 50. Testing: kiểm tra business invariant không cần DB

Unit test cho aggregate:

```java
@Test
void cannotConfirmEmptyOrder() {
    PurchaseOrder order =
        new PurchaseOrder(7L, "ORD-001");

    assertThrows(
        IllegalStateException.class,
        order::confirm
    );
}
```

Test thêm dòng:

```java
@Test
void orderTotalEqualsSumOfLines() {
    PurchaseOrder order =
        new PurchaseOrder(7L, "ORD-002");

    order.addLine(
        11L, 2, new BigDecimal("10.00")
    );
    order.addLine(
        12L, 3, new BigDecimal("5.00")
    );

    assertEquals(
        0,
        order.getTotalAmount()
             .compareTo(new BigDecimal("35.00"))
    );
}
```

Unit test nhanh và không cần Hibernate. Nó chứng minh domain methods, **không chứng minh cascade/flush/constraint mapping**.

## 51. In-memory fake repository: dùng đúng mục đích

Một fake để unit test application service:

```java
final class FakeOrderRepository
        implements PurchaseOrderRepository {

    private final Map<Long, PurchaseOrder> byId =
        new HashMap<>();

    @Override
    public Optional<PurchaseOrder> findByIdForChange(
            Long tenantId, Long orderId) {

        PurchaseOrder found = byId.get(orderId);

        if (found == null
                || !found.getTenantId().equals(tenantId)) {
            return Optional.empty();
        }

        return Optional.of(found);
    }

    @Override
    public void add(PurchaseOrder order) {
        if (order.getId() == null) {
            throw new UnsupportedOperationException(
                "Fake expects assigned identifiers"
            );
        }

        byId.put(order.getId(), order);
    }
}
```

**Lưu ý:** entity demo dùng `GenerationType.IDENTITY` và ID chưa được gán trước persist, nên fake này **không phù hợp để test placement flow như-is**. Đây là minh họa cho một vấn đề quan trọng: fake muốn mô phỏng behavior identity phải cấp IDs hoặc domain model phải dùng assigned IDs. Đừng viết fake khác semantics rồi coi service test là kiểm chứng repository thực.

Một thiết kế fake đúng hơn có thể:

- Đưa `OrderIdGenerator` vào application/domain và dùng assigned IDs.
- Tạo fake trả ID theo contract port.
- Unit-test operation `confirmOrder` trên Orders đã có ID, còn `placeOrder` integration-test với JPA.
- Dùng test double cho mục tiêu orchestration, không khẳng định mọi persistence behavior.

**Fake repository có thể giúp kiểm thử orchestration; nó không thay JPA integration test.**

## 52. Integration test cho JPA adapter

Với PostgreSQL Testcontainers/Flyway hoặc DB production-like, test:

1. Seed một PurchaseOrder và hai owned Lines.
2. Gọi `repository.add(order)` trong transaction.
3. Commit rồi mở EntityManager mới.
4. `findByIdForChange` và xác minh Order cùng Lines.
5. Test tenant mismatch không tìm thấy Order.
6. Gọi `order.removeLine`, commit, kiểm tra orphan row đã xóa.
7. Test `order.confirm` bảo vệ empty-order invariant.
8. Test UNIQUE(tenant_id,order_no) bằng database constraint.
9. Test optimistic lock với hai independent contexts.
10. Test data sau rollback không bị commit nửa chừng.

Một test `repository.save(order)` rồi `assertNotNull(order.getId())` không chứng minh aggregate đã được commit hoặc mapping children hoạt động.

## 53. Test cascade và orphan removal

Ví dụ:

```java
@Test
void addingOrderPersistsOwnedLines() {
    PurchaseOrder order =
        new PurchaseOrder(7L, "ORD-TEST");

    order.addLine(
        101L, 2, new BigDecimal("12.00")
    );
    order.addLine(
        102L, 1, new BigDecimal("8.00")
    );

    transactionTemplate.executeWithoutResult(status -> {
        orders.add(order);
    });

    // Dùng một transaction/EntityManager mới để query.
    // Assert root row và hai child rows có order_id đúng.
}
```

Ví dụ dùng Spring `TransactionTemplate` và JPA mapping demo. Phần assertion được viết dạng hướng dẫn vì thao tác query/cleanup phụ thuộc test harness. Nên test cả FK ownership và count lines; một test chỉ thấy `order.getLines().size() == 2` trước commit không kiểm tra cascade persistence.

## 54. Test optimistic conflict và state preservation

Seed Order version 0. Hai independent EntityManagers load cùng version:

```text
EM A: load Order v0 ── confirm ── commit v1
EM B: load Order v0 ── change ── flush/commit fails
DB: Order vẫn theo committed state của A
```

Các assertions:

- Failure type thuộc optimistic conflict hoặc đúng wrapper/cause.
- B transaction rollback.
- Context mới đọc state của A.
- Không có audit/outbox row của attempt B được commit.
- Không reuse stale object sau conflict.

Nếu owned child updates không bump root version như mong đợi, cần điều chỉnh versioning/locking strategy rồi test lại.

## 55. Test query projection khác test aggregate behavior

Query read-model test:

```java
List<OrderSummary> rows =
    orderQueryStore.findRecent(
        7L,
        PageRequest.of(0, 20)
    );
```

Nên kiểm tra:

- Tenant scope.
- ORDER BY/page size.
- Đúng fields trong DTO.
- Không phát N+1 khi mapper dùng Customer name.
- Query SQL count theo dữ liệu nhiều Orders.
- Không fetch to-many collections chỉ để trả summary.
- Index/plan khi performance-critical.

Command repository test nhấn mạnh consistency/transactions/invariants. **Không dùng cùng một tiêu chí cho mọi repository method**.

---

## 56. Vai trò của DAO trong kiến trúc có domain repository

Một hệ thống vẫn có thể đồng thời:

```text
Domain:
  PurchaseOrderRepository
  ProductRepository
  CustomerRepository

Read/report:
  OrderSummaryQueryDao
  SalesReportDao
  InventorySnapshotDao

Operations/maintenance:
  LegacyOrderImportDao
  DataRepairDao
  Migration scripts
```

Miễn là:

- Code ghi dữ liệu nghiệp vụ bình thường đi qua domain rules/transaction design.
- Low-level repair/bulk code có quyền hạn kiểm soát và tests.
- Read-only reporting không vô tình trả managed mutable aggregate cho mọi caller.
- Các bộ phận biết rõ consistency/caching/query semantics.
- Không có hai lớp tự ý sửa cùng invariant theo những rules khác nhau.

Repository nghiệp vụ và DAO **không loại trừ nhau**. Chúng phục vụ những loại operation khác nhau.

## 57. Không áp mô hình aggregate repository một cách giáo điều

Các tình huống không cần một abstraction phức tạp:

- Bảng mã tỉnh/thành chỉ đọc.
- Mapping đơn giản `UserPreference` với một key/value.
- MVP nội bộ ít domain rules.
- CRUD admin form không có lifecycle phức tạp.
- Một service chỉ vận hành SQL batch và không có object-oriented domain model hữu ích.
- Analytics pipeline thiên về SQL columnar/OLAP.

Một `JpaRepository<SimpleSetting, Long>` trực tiếp có thể là lựa chọn tốt. Tạo repository interface domain + adapter + assembler + DTO + query spec cho mỗi key/value thường tăng code mà không tạo ra bảo vệ invariant nào đáng kể.

Tập trung vào chi phí thay đổi và mức độ rủi ro của domain, không phải số tầng.

## 58. Dấu hiệu cần tách repository nghiệp vụ khỏi table wrapper

Một số dấu hiệu:

- Nhiều services phải gọi 3–5 repositories để hoàn tất cùng một domain action.
- Một rule như “Order đã xác nhận không sửa lines” được check lặp ở nhiều nơi.
- Multiple callers cập nhật total/status bằng setters tự do.
- DB có nhiều inconsistent rows dù CRUD methods chạy thành công.
- Khi đổi schema cần sửa cả controller/service/business logic.
- Transaction boundaries không rõ.
- Test khó tái tạo aggregate invariant.
- Query list endpoint luôn load toàn entity graph.
- API trả trực tiếp entities với lazy serialization bugs.
- Concurrency conflict không được xử lý.
- Tenant/authorization filter bị lặp và thường bị quên.
- Audit/event writes commit khác transaction quan trọng.

Không phải tất cả dấu hiệu bắt buộc dùng DDD đầy đủ; chúng gợi ý cần **định nghĩa rõ ranh giới hành vi và persistence**.

## 59. Dấu hiệu repository nghiệp vụ bị thiết kế quá mức

Ở cực đối diện:

- Repository chứa hàng chục methods chỉ đổi tên `findAll`/`save`.
- Mỗi entity có cả domain interface, adapter, mapper, Spring store mà không có rule nào.
- Một read-only report phải load aggregate khổng lồ.
- Không ai biết transaction ownership vì mỗi abstraction giấu một lớp.
- Adapter bắt đầu gọi payment gateway/email.
- Repository returns generic `Object` hay `Map<String,Object>` không rõ semantics.
- Mọi việc phải đi qua one-size-fits-all `BaseRepository<T>` siêu tổng quát.
- Khó dùng JPQL/SQL tối ưu vì abstraction cấm query-specific projections.
- Các port giữ nguyên mọi framework types nhưng chỉ đổi package.
- Unit tests dùng fake có semantics khác JPA/DB.
- Tách domain và persistence thành hai models rồi mapping hai chiều không có lợi ích rõ.

Giải pháp thường là **làm interface nhỏ hơn và rõ trách nhiệm**, không tự động thêm nhiều layers nữa.

## 60. `GenericRepository<T, ID>`: tiện nhưng có giới hạn

Một interface:

```java
public interface GenericRepository<T, ID> {
    Optional<T> findById(ID id);
    T save(T entity);
    void delete(T entity);
    List<T> findAll();
}
```

có thể giảm boilerplate, nhưng nó giả định mọi aggregate:

- Có cùng lifecycle.
- Có thể save/delete tùy ý.
- Có query findAll không giới hạn.
- Có cùng concurrency policy.
- Không cần tenant scope.
- Không có business-specific retrieval.

Với domain phức tạp, generic interface dễ phơi operations **không hợp lệ** như xóa một Invoice đã thanh toán hoặc `findAll` hàng triệu rows.

Dùng generic base cho hạ tầng khi phù hợp; **domain port nên chỉ expose operations hợp lệ theo aggregate/use case**.

---

## 61. Bài tập 1: Một bảng, một repository?

Có năm tables gồm Orders, Lines, Payments, StatusHistory và Customers.

**Câu hỏi:** Có nhất thiết tạo năm repository nghiệp vụ không?

**Đáp án:** Không. Cần xác định aggregate roots, lifecycle và consistency boundaries. Lines có thể thuộc Order; Payments có thể là aggregate riêng; StatusHistory có thể là log/read model; Customer là aggregate riêng.

## 62. Bài tập 2: Xóa line khi Order confirmed

Một `OrderLineRepository.deleteById(lineId)` công khai có thể xóa row dù Order đã CONFIRMED.

**Hướng sửa:** Đặt `order.removeLine` kiểm tra `DRAFT`, cập nhật total, rồi lưu qua Order aggregate. DB constraints cũng cần phù hợp.

## 63. Bài tập 3: Mỗi repository tự commit

Service tạo Order, sau đó ba Lines bằng bốn transaction riêng.

**Đáp án:** Có nguy cơ partial commits. Đặt transaction ở application use case nếu cần tính nguyên tử.

## 64. Bài tập 4: Repository gọi email

`OrderRepository.confirmAndEmailCustomer` vừa UPDATE DB vừa gọi SMTP.

**Đáp án:** Trộn persistence và side effects; tách domain/application orchestration và after-commit/outbox strategy.

## 65. Bài tập 5: `save()` trên managed entity

Service load Order trong transaction, gọi `order.confirm()` nhưng không `save()`.

**Đáp án:** Với JPA managed entity và transaction commit, dirty checking thường đồng bộ. `save` không phải bước bắt buộc chỉ vì là Spring Data JPA.

## 66. Bài tập 6: Detached merge

Client gửi nguyên entity JSON cũ rồi controller gọi `repository.save(entity)`.

**Đáp án:** Nguy cơ stale overwrite/authorization/association changes. Dùng command DTO, load managed aggregate, áp business method và optimistic version policy.

## 67. Bài tập 7: Product thuộc Order?

OrderLine có `@ManyToOne Product`.

**Đáp án:** Relationship không có nghĩa Product do Order sở hữu. Không cascade REMOVE tới Product; xác định aggregate boundary.

## 68. Bài tập 8: Read-only dashboard

Dashboard chỉ cần Order ID, customerName và total.

**Đáp án:** Dùng DTO projection/read query repository; không bắt buộc load toàn aggregate cùng Lines.

## 69. Bài tập 9: N+1

Repository list 50 Orders rồi mapper gọi `order.getCustomer().getName()`.

**Đáp án:** Có thể N+1; sửa bằng query projection/to-one JOIN FETCH/EntityGraph phù hợp và đo SQL count.

## 70. Bài tập 10: Collection pagination

`findAll(Pageable)` dùng `JOIN FETCH lines` và trả 20 Orders.

**Đáp án:** Có nguy cơ in-memory pagination/row multiplication; dùng DTO hoặc two-phase IDs + batch fetching có kiểm soát.

## 71. Bài tập 11: Unique orderNo

`existsByOrderNumber` rồi insert Order ở hai threads.

**Đáp án:** Race. Cần UNIQUE(tenant_id,order_no) trong DB và translation unique conflict ở transaction boundary.

## 72. Bài tập 12: Chuyển trạng thái bằng bulk UPDATE

Bulk JPQL update `status=CONFIRMED` cho 10.000 rows.

**Đáp án:** Bypass domain methods/callbacks/version behavior thông thường. Chỉ dùng khi nghiệp vụ chấp nhận và SQL checks/invariants được thiết kế riêng.

## 73. Bài tập 13: Optimistic version trên child

Hai threads sửa hai OrderLines khác nhau, root version có luôn tăng không?

**Đáp án:** Không bảo đảm trên mọi provider/mapping. Nếu invariant cần root-level concurrency protection, test và thiết kế khóa/version tường minh.

## 74. Bài tập 14: Tenant query

`findById(orderId)` trả Order tenant khác.

**Hướng sửa:** Repository contract tenant-scoped, authorization policy và DB protections phù hợp.

## 75. Bài tập 15: Một entity có lifecycle độc lập

OrderLine bắt đầu có workflow fulfillment/returns riêng với quyền cập nhật trực tiếp.

**Đáp án:** Xem xét lại aggregate boundaries và repository cho lifecycle đó; không giữ child ownership chỉ vì schema ban đầu.

## 76. Bài tập 16: DAO có bị cấm?

Sales report cần native SQL GROUP BY qua nhiều tables.

**Đáp án:** Không. Read DAO/SQL projection có thể là abstraction phù hợp và hiệu quả.

## 77. Bài tập 17: Pass-through service

`UserService.save(user) { return userRepo.save(user); }` không có rule/transaction khác.

**Đáp án:** Cân nhắc bỏ layer hoặc thêm đúng use-case responsibilities, không bắt buộc giữ để “đúng kiến trúc”.

## 78. Bài tập 18: Domain port phụ thuộc Pageable

Domain interface import `org.springframework.data.domain.Pageable`.

**Đáp án:** Pragmatic Spring-centric có thể chấp nhận. Nếu muốn framework-independent domain, định nghĩa query criteria/page abstraction riêng hoặc đặt query interface ở application/read layer.

## 79. Bài tập 19: L2/L1 cache khi test

Test `save` rồi `findById` cùng transaction thấy entity.

**Đáp án:** Không chứng minh DB committed state. Commit và đọc bằng context mới, kiểm soát cache nếu cần.

## 80. Bài tập 20: Version conflict

Hai EntityManagers cập nhật Order cùng version cũ.

**Đáp án:** `@Version` có thể ném optimistic conflict ở flush/commit; test DB giữ winner state, retry trong transaction mới nếu policy cho phép.

## 81. Bài tập 21: Physical delete vs cancel

`deleteById` xóa một Order đã thanh toán, phá audit/compliance.

**Đáp án:** Business action `cancel` khác physical delete; đặt rule lifecycle/retention trong domain/application và DB permissions/constraints phù hợp.

## 82. Bài tập 22: Repository trả Stream

Repository stream 1 triệu managed Orders mà không kiểm soát EM/transaction.

**Đáp án:** Resource leak/heap pressure; dùng bounded DTO/query/JDBC streaming đúng lifecycle hoặc chunking.

## 83. Bài tập 23: In-memory fake IDs

Fake repository không gán ID, nhưng real JPA repository dùng `IDENTITY`.

**Đáp án:** Fake không tái hiện creation semantics. Cần điều chỉnh fake/port hoặc kiểm thử create flow ở integration layer.

## 84. Bài tập 24: Repository quá tổng quát

`GenericRepository` expose `deleteAll` và `findAll` cho mọi aggregate.

**Đáp án:** Có nguy cơ operations không hợp lệ, unbounded queries, tenant leaks. Public port nên có capabilities nhỏ theo use cases.

## 85. Bài tập 25: Thiết kế Order feature

**Yêu cầu:** Thiết kế API đặt đơn, sửa số lượng, xác nhận, hủy và trang danh sách Orders.

**Hướng triển khai:**

1. Xác định root `PurchaseOrder` và owned `OrderLine`.
2. Domain methods `addLine`, `changeQuantity`, `confirm`, `cancel`.
3. Domain repository port cho load/write aggregate.
4. Application service làm transaction/authorization.
5. JPA mapping cascade/orphanRemoval chỉ cho owned children.
6. `@Version` và DB UNIQUE/FK/CHECK bảo vệ concurrency/integrity.
7. Product/Customer aggregates có repositories riêng.
8. Query repository/DTO projection cho list/report.
9. Tenant-scoped retrieval và capped pagination.
10. JPA integration tests cho cascade/rollback/optimistic conflict.
11. Tests cho list SQL count/N+1 và fetch strategies.
12. Xem outbox/after-commit nếu có events/payment side effects.

**Không phải bước nào cũng phải tạo một class mới**: số lớp nên phản ánh complexity thực và nhu cầu test/maintainability.

---

## 86. Checklist phân biệt repository nghiệp vụ và lớp bọc từng bảng

Khi đánh giá một thiết kế repository:

1. Tên repository đến từ domain concept hay tên bảng SQL?
2. Có xác định aggregate root không?
3. Có biết entities nào chỉ là owned children không?
4. Owned child có bị sửa tùy tiện từ outside callers không?
5. Business invariants được thực thi ở domain methods hay rải rác trong services?
6. Một use case thay đổi nhiều rows có transaction boundary rõ không?
7. Repository method có tự commit riêng gây partial transaction không?
8. Có tách application orchestration và persistence responsibilities không?
9. Repository có gọi HTTP/email/payment ngoài DB không?
10. Public interface có phơi mọi CRUD operation không cần thiết không?
11. Có dùng `deleteById` cho một business action thực ra là cancel/archive không?
12. Có cần một domain port riêng hay Spring Data repository trực tiếp là đủ?
13. Nếu có domain port, nó có tránh dependency hạ tầng không?
14. Có adapter JPA đủ rõ và không chỉ tăng boilerplate không?
15. Mapping entity có giữ aggregate ownership đúng không?
16. Có tránh cascade remove sang aggregate độc lập không?
17. Có root methods bảo vệ state transitions không?
18. Có biết managed entity dirty checking hoạt động thế nào không?
19. Có tránh `merge` detached graph trực tiếp từ JSON không?
20. Có xác định version/locking policy cho aggregate không?
21. Child updates có thực sự được root version bảo vệ nếu cần không?
22. Có DB UNIQUE/FK/CHECK bảo vệ invariant ở storage không?
23. Có tránh tin `exists` pre-check chống race không?
24. Có tenant/authorization scope trong queries cần thiết không?
25. Có phân biệt soft delete/cancel/archive/physical delete không?
26. Có giới hạn rows và pagination cho list queries không?
27. Có phân biệt query DTO read-only với aggregate command load không?
28. Có kiểm tra fetch plan của `findForChange` không?
29. Có tránh JOIN FETCH nhiều collections cùng pagination không?
30. Có biết EntityGraph không tự bảo đảm một SQL không?
31. Có query/read DAO khi báo cáo không cần managed entities không?
32. Có biết bulk DML bỏ qua entity lifecycle và có thể làm L1 stale không?
33. Có xác định exception/transaction completion boundary không?
34. Có xử lý optimistic conflict trong transaction mới nếu retry hợp lệ không?
35. Có outbox/after-commit policy cho external side effects không?
36. Có domain unit tests không phụ thuộc DB không?
37. Có JPA integration tests cho cascade/orphanRemoval/constraints không?
38. Có readback bằng EntityManager mới sau commit không?
39. Có tests cho tenant isolation và soft-delete behavior không?
40. Có SQL count tests cho read projections/N+1 không?
41. Có fake repository gần đúng semantics của production không?
42. Có tránh hardcode database schema ở application business logic không?
43. Có tránh generic base repository mở quá nhiều operations không?
44. Có đo write/read costs trước khi chia aggregate rất lớn không?
45. Có cho phép DAO/table gateway khi đó thật sự là công cụ phù hợp không?
46. Có phân biệt cách thiết kế DDD với quy tắc bắt buộc của JPA không?
47. Có tránh interface chỉ đổi tên JpaRepository methods nhưng không thêm giá trị không?
48. Có giải thích rõ ownership của một repository trong team không?
49. Có bảo vệ invariants khi có nhiều writer không đi qua ORM không?
50. Nếu schema đổi, business logic có ít bị tác động hơn nhờ abstraction phù hợp không?

Checklist không nhằm ép mọi dự án xây dựng một hệ thống DDD đầy đủ. Nó giúp trả lời câu hỏi **repository này đang bảo vệ một nhu cầu nghiệp vụ rõ ràng hay chỉ là lớp chuyển tiếp CRUD cho một bảng?**

## Kết luận

**Repository nghiệp vụ** và **lớp bọc từng bảng** không chỉ khác nhau ở tên gọi. Chúng khác về thứ được trừu tượng hóa:

- **Table gateway/DAO** tổ chức các thao tác SQL/CRUD quanh cấu trúc lưu trữ; rất hữu ích cho báo cáo, ETL, maintenance và dữ liệu đơn giản.
- **Repository nghiệp vụ** tổ chức việc truy cập/lưu một đối tượng hoặc aggregate root theo ngôn ngữ use case, để callers không tự phối hợp các bảng con và bỏ qua business invariants.
- **EntityManager/JPA provider** là cơ chế kỹ thuật quản lý entity identity, dirty checking, lifecycle, flush và SQL; nó có thể là công cụ bên trong một repository nhưng không tự quyết định aggregate boundary.
- **Spring Data JpaRepository** cung cấp CRUD tiện lợi, có thể làm implementation của repository nghiệp vụ; nó không tự biết những state transition nào hợp lệ hoặc tenant nào được phép truy cập.
- Một aggregate có thể trải nhiều bảng, và một báo cáo có thể đọc nhiều aggregates mà không cần tải managed object graph.
- Transaction, database constraints, optimistic locking và application policy là phần thiết yếu để repository business có thể giữ tính đúng đắn khi nhiều callers đồng thời thao tác.
- Có thể triển khai port/adapter domain tách hạ tầng, hoặc dùng Spring Data JPA trực tiếp ở module CRUD đơn giản; lựa chọn phụ thuộc vào complexity và lợi ích thực tế, không phải giáo điều.
- Đọc dữ liệu tổng hợp nên cân nhắc DTO projections/read DAO; ghi dữ liệu thuộc aggregate phải đi qua invariants thích hợp.
- Không biến tên “Repository” thành tấm màn che một transaction boundary không rõ, một fetch plan kém, hay những lệnh cập nhật bỏ qua domain rules.

Câu hỏi cần nhớ khi thiết kế mỗi repository không phải **“Có bao nhiêu bảng để tạo bấy nhiêu interface?”**, mà là: **“Đối tượng nghiệp vụ nào có vòng đời và invariants cần bảo vệ? Application cần những cách truy cập hợp lệ nào? Và JPA/SQL sẽ hỗ trợ những cách đó mà không làm rò rỉ trách nhiệm lưu trữ lên business code ra sao?”**

Trả lời tốt ba câu hỏi ấy sẽ giúp tầng persistence vừa phù hợp nghiệp vụ, vừa kiểm thử được, vừa giữ quyền tối ưu SQL khi quy mô dữ liệu tăng.
