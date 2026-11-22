# Giới hạn thao tác an toàn bên trong callback theo đặc tả JPA

Trong Java Persistence API (JPA), **lifecycle callback** là một method được persistence provider gọi khi một entity được nạp, chuẩn bị lưu, cập nhật hoặc xóa. Các annotation `@PrePersist`, `@PostPersist`, `@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove` và `@PostLoad` giúp đặt những công việc nhỏ gần với vòng đời của entity.

Tuy nhiên, **callback không phải một application service thu nhỏ**. Nó chạy bên trong quy trình provider quản lý persistence context, identity, cascade, dirty checking, SQL ordering và flush. Nếu callback tự gọi `EntityManager`, chạy truy vấn, truy cập một entity khác hoặc sửa quan hệ giữa các entities, chương trình có thể phụ thuộc behavior riêng của Hibernate/EclipseLink, phát SQL bất ngờ hoặc gặp reentrant persistence operations.

Nguyên tắc quan trọng về tính portable trong đặc tả JPA là:

> Một lifecycle callback không nên gọi các thao tác `EntityManager` hoặc query, không nên truy cập những entity instances khác, và không nên thay đổi relationships trong cùng persistence context. Callback được phép sửa **non-relationship state của chính entity** được callback.

Đây là giới hạn cốt lõi khi thiết kế callback. Một provider có thể cho phép một số trường hợp vượt giới hạn đó, nhưng **chạy được trên một provider không đồng nghĩa được JPA bảo đảm portable**.

Bài học tập trung vào việc phân biệt thao tác an toàn/không an toàn, giải thích thời điểm callbacks chạy, cách làm việc với basic fields, generated IDs, `@Version`, `@Transient`, lỗi, rollback và những giải pháp tốt hơn cho tác vụ liên quan nhiều entities hoặc hệ thống ngoài database.

---

## 1. Callback được kích hoạt ở giai đoạn nào?

| Callback | Mốc JPA | Tác vụ cục bộ thường phù hợp |
|---|---|---|
| `@PrePersist` | Trước hoạt động persist/INSERT tương ứng | Điền `createdAt`, chuẩn hóa basic field |
| `@PostPersist` | Sau khi INSERT/persist operation tương ứng được thực thi | Quan sát giá trị generated ID nếu có |
| `@PreUpdate` | Trước database UPDATE tương ứng | Điền `updatedAt`, kiểm tra scalar invariant |
| `@PostUpdate` | Sau database UPDATE tương ứng | Quan sát state; không mặc định đã commit |
| `@PreRemove` | Trước thao tác remove/DELETE tương ứng | Kiểm tra scalar state cục bộ |
| `@PostRemove` | Sau thao tác remove/DELETE tương ứng | Không coi như after-commit event |
| `@PostLoad` | Sau khi entity được load hoặc refresh theo lifecycle | Tính derived `@Transient` value |

Một method có thể dùng chung logic cho nhiều sự kiện:

```java
@PrePersist
@PreUpdate
void normalizeCode() {
    if (code != null) {
        code = code.trim().toUpperCase(Locale.ROOT);
    }
}
```

**Lưu ý:** JPA callback diễn ra theo lifecycle của entity chứ không phải theo số lần người dùng gọi setter, số HTTP requests hoặc số lần application service được gọi.

### 1.1. Callback không phải field-change observer

```java
order.setDescription("Updated description");
```

Dòng trên không có nghĩa `@PreUpdate` được gọi ngay lập tức. Provider thường đánh giá dirty state rồi quyết định cần UPDATE khi flush.

### 1.2. Callback không phải after-commit hook

`@PostPersist`, `@PostUpdate` và `@PostRemove` không có nghĩa database transaction đã commit. Chúng có thể chạy trước khi phát hiện một lỗi constraint khác, optimistic locking conflict hoặc sự cố khiến transaction rollback.

### 1.3. Thời điểm flush không cố định một điểm

Provider có thể đồng bộ SQL tại `em.flush()`, khi commit hoặc trước một số JPQL operations theo flush mode. Không nên viết code phụ thuộc một câu SQL luôn được thực thi ngay sau một setter, hoặc callback PostUpdate luôn là bước cuối của transaction.

---

## 2. Mô hình entity minh họa

Giả sử ứng dụng bán hàng có entity `CatalogCategory`:

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.Locale;

@Entity
@Table(name = "catalog_category")
public class CatalogCategory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String code;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected CatalogCategory() {}

    public CatalogCategory(
            String code,
            String displayName) {
        this.code = code;
        this.displayName = displayName;
    }

    @PrePersist
    void beforeInsert() {
        normalizeLocalState();

        Instant now = Instant.now();
        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
    }

    @PreUpdate
    void beforeUpdate() {
        normalizeLocalState();
        updatedAt = Instant.now();
    }

    private void normalizeLocalState() {
        if (code != null) {
            code = code.trim().toUpperCase(Locale.ROOT);
        }

        if (displayName != null) {
            displayName = displayName.trim();
        }
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getDisplayName() { return displayName; }
}
```

Hai callbacks chỉ sửa basic fields của **chính entity đang nhận sự kiện**. Chúng không gọi EntityManager, repository, HTTP client, không truy cập association và không thay đổi quan hệ.

Đây là ví dụ tương đối phù hợp với phạm vi mà đặc tả hướng tới. Nhưng ngay cả với kiểu callback này, ứng dụng vẫn cần xác định time source, constraint ở DB và cách xử lý những đường cập nhật không chạy JPA callbacks.

---

## 3. Bảng ranh giới: An toàn, có điều kiện và nên tránh

| Thao tác bên trong callback | Phân loại | Giải thích |
|---|---|---|
| Chuẩn hóa String thuộc entity hiện tại | Thường phù hợp | Thay basic/non-relationship state |
| Điền `createdAt` hoặc `updatedAt` | Thường phù hợp | Không phụ thuộc entity khác |
| Kiểm tra `quantity > 0` | Có thể phù hợp | Local scalar invariant |
| Tính `@Transient` value từ basic fields | Thường phù hợp | Không query hoặc lazy-load |
| Ghi debug log ngắn | Có thể chấp nhận | Không coi là sự kiện sau commit |
| Ném unchecked exception vì state sai | Có thể | Transaction có thể rollback |
| Gọi `em.persist()` | Nên tránh | Nested persistence operation |
| Gọi `em.merge()` hoặc `em.remove()` | Nên tránh | Có thể đổi action graph |
| Gọi `em.flush()` | Nên tránh | Reentrant flush |
| Chạy JPQL/Criteria/native SQL query | Nên tránh | Query có thể tự flush, load thêm entities |
| Gọi Spring Data repository để query | Nên tránh | Vẫn là persistence operation gián tiếp |
| Đọc một `Customer` managed khác | Nên tránh | Vượt phạm vi entity hiện tại |
| Thêm `OrderLine` vào `@OneToMany` | Nên tránh | Thay relationship graph |
| Gán lại `@ManyToOne customer` | Nên tránh | Thay association |
| Truy cập lazy collection trong PostLoad | Nên tránh | SQL/N+1/recursive callbacks |
| Gọi payment provider qua HTTP | Không phù hợp | Side effect ngoài DB transaction |
| Publish Kafka/RabbitMQ message | Không phù hợp nếu cần commit consistency | Message không rollback với DB |
| Tạo thread hay async task | Nên tránh | Không mang transaction/context bảo đảm |
| Tự tăng field `@Version` | Sai trách nhiệm | Version do provider quản lý |

Điểm phân loại “nên tránh” không chỉ là gợi ý style. Đó là cách duy trì behavior trong phạm vi có thể dựa vào theo JPA. Khi chủ đích sử dụng extension của vendor, cần tài liệu hóa và kiểm thử version/provider cụ thể.

---

## 4. Vì sao EntityManager trong callback là nguy hiểm?

Provider có thể đang thực hiện:

```text
Service sửa managed entity
           |
           v
Provider bắt đầu flush
           |
           v
Duyệt dirty managed entities
           |
           v
Gọi @PreUpdate
           |
           v
Callback chạy JPQL query
           |
           v
Query lại yêu cầu flush/load objects
           |
           v
Nested / reentrant persistence work
```

Tùy provider, việc này có thể gây:

- Reentrant flush hoặc recursion.
- SQL INSERT/UPDATE/DELETE sắp xếp không như dự kiến.
- Entity graph bị thay đổi sau khi provider đã quyết định cascade.
- Phát sinh SELECT trong lúc transaction đang nắm nhiều locks.
- Dirty checking và snapshot không nhất quán theo provider.
- Exception chỉ xảy ra lúc flush/commit, khó truy tìm nguyên nhân.
- Behavior khác nhau sau khi nâng Hibernate/EclipseLink.

### 4.1. Anti-pattern: Query để tạo order number

```java
@PrePersist
void assignOrderNumber() {

    Long count = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o",
        Long.class
    ).getSingleResult();

    orderNumber = "ORD-" + (count + 1);
}
```

Sai ở hai mức: callback gọi EntityManager/query và concurrency logic không an toàn. Hai transactions cùng COUNT có thể chọn cùng order number.

**Thay thế:** dùng database sequence, allocator có locking phù hợp, application-generated business key và UNIQUE constraint. Đặt logic ở service/infrastructure trước khi persist.

### 4.2. Anti-pattern: Persist AuditLog từ listener

```java
public class AuditListener {

    @PersistenceContext
    private EntityManager em;

    @PostUpdate
    public void onUpdate(Object target) {
        em.persist(
            new AuditLog(target.toString())
        );
    }
}
```

Việc persist một entity khác ngay trong callback tạo thêm persistence work tại một điểm mà provider đang xử lý lifecycle của entity gốc.

**Thay thế:** application service tạo audit record trong cùng transaction hoặc chọn auditing framework/integration có contract rõ ràng.

### 4.3. Không “lách” bằng repository

```java
@PreRemove
void checkReferences() {
    long count = productRepository.countByCategoryId(id);
}
```

Dù không có biến `EntityManager`, repository vẫn dùng JPA operations. Phạm vi callback không thay đổi chỉ vì truy vấn được che sau một abstraction.

---

## 5. Giới hạn truy cập các entity instances khác

Một entity `PurchaseOrder` có:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Callback sau không chỉ đụng state của chính Order:

```java
@PostLoad
void initializeCustomerName() {
    customerName =
        customer.getDisplayName();
}
```

Nó đọc state của `Customer` và có thể kích hoạt lazy loading.

### 5.1. N+1 trong callback

Nếu load 100 Orders, PostLoad gọi Customer getter cho mỗi Order có thể tạo nhiều SQL phụ. Khi cache warm, test có thể không lộ vấn đề; khi cache cold, số queries tăng theo số entity.

### 5.2. Recursive loading

Nếu Customer có PostLoad đọc Orders, các callbacks có thể tạo chuỗi load phụ thuộc lẫn nhau trong khi provider chưa hoàn tất graph initialization.

### 5.3. Thay thế bằng DTO projection

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    String customerName
) {}
```

```java
List<OrderSummary> items = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderSummary(
        o.id, o.orderNumber, c.displayName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    """,
    OrderSummary.class
).getResultList();
```

Service/repository quyết định dữ liệu cần đọc. Callback không cần tự load Customer.

### 5.4. EntityGraph cũng thuộc tầng truy vấn

Nếu cần managed Order và Customer, service có thể dùng `JOIN FETCH` hoặc `EntityGraph` khi load. Đừng để entity callback tự quyết định fetch plan bằng lazy getter.

---

## 6. Không thay relationships từ callback

Giả sử:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Không nên:

```java
@PrePersist
void addDefaultLine() {
    lines.add(new OrderLine(...));
}
```

Cũng không nên:

```java
@PrePersist
void selectCustomer() {
    customer = someOtherManagedCustomer;
}
```

Vì các thao tác này làm thay đổi association graph, owning/inverse relationship state hoặc cascade targets đúng lúc provider đang chuẩn bị persistence operations.

### 6.1. Làm graph trước persist

```java
@Transactional
public void createOrder(PlaceOrderCommand command) {

    Customer customer = em.find(
        Customer.class,
        command.customerId()
    );

    PurchaseOrder order =
        PurchaseOrder.createFor(customer);

    for (OrderLineInput input : command.lines()) {
        order.addLine(
            OrderLine.create(input)
        );
    }

    em.persist(order);
}
```

Domain method quản lý hai phía quan hệ trong giai đoạn application code. Khi gọi `persist`, graph đã được chuẩn bị.

### 6.2. Không dựa vào cascade để hợp thức hóa thay graph

`cascade = PERSIST` không có nghĩa callback được phép thêm children khi provider đã bắt đầu cascade. Hãy thiết kế transaction/service boundary và entity helper methods trước lifecycle callback.

### 6.3. Không chỉ owning side mới là relationship mutation

Thêm child vào inverse collection, đổi một `@ManyToOne`, remove phần tử khỏi `@ManyToMany` hoặc thay `@ElementCollection` đều cần được xem xét trong phạm vi association mapping. Khi có nghi vấn, thực hiện trước callback trong domain/service.

---

## 7. Thay đổi non-relationship state của chính entity

Đây là vùng phù hợp nhất để dùng callback.

### 7.1. Chuẩn hóa String

```java
@Entity
public class ProductTag {

    @Id
    private Long id;

    @Column(nullable = false)
    private String tagCode;

    @PrePersist
    @PreUpdate
    void normalizeCode() {
        if (tagCode != null) {
            tagCode = tagCode.trim()
                .toUpperCase(Locale.ROOT);
        }
    }
}
```

### 7.2. Điền giá trị mặc định

```java
@PrePersist
void assignDefaultStatus() {
    if (status == null) {
        status = OrderStatus.DRAFT;
    }
}
```

Đây là basic/enum state cục bộ. Tuy vậy, nếu `status` là business state quan trọng, factory/constructor có thể là nơi rõ ràng hơn để gán default trước persist.

### 7.3. Kiểm tra scalar invariant

```java
@PrePersist
@PreUpdate
void validateQuantity() {
    if (quantity <= 0) {
        throw new IllegalStateException(
            "Quantity must be positive"
        );
    }
}
```

Callback có thể phát hiện sai state, nhưng validation ở service và DB `CHECK (quantity > 0)` vẫn cần vì bulk/native SQL không mặc định gọi callbacks.

### 7.4. Tính transient derived field

```java
@PostLoad
void computeLineTotal() {
    lineTotal = quantity.multiply(unitPrice);
}
```

Nếu `quantity` và `unitPrice` là basic values, phép tính không cần truy cập entity khác.

### 7.5. Non-relationship không đồng nghĩa luôn tốt

Một phép tính hash rất nặng hoặc network-backed normalization tuy chỉ gán String vào entity vẫn có chi phí lớn, behavior không deterministic và phụ thuộc external systems. Callback nên nhanh, nhỏ, dự đoán được và không có I/O bên ngoài.

---

## 8. @PrePersist: Những gì có thể tin cậy

Ví dụ:

```java
@PrePersist
void beforeInsert() {
    if (createdAt == null) {
        createdAt = Instant.now();
    }
}
```

### 8.1. IDENTITY ID có thể chưa được cấp

Với `GenerationType.IDENTITY`, database thường tạo ID ở thao tác INSERT. Trước INSERT, `@PrePersist` có thể chưa thấy ID đã được sinh.

Không viết:

```java
@PrePersist
void wrong() {
    orderNumber = "ORD-" + id;
}
```

và giả định `id` đã có.

### 8.2. Generation strategy khác có timing khác

Với SEQUENCE hoặc application-assigned ID, provider có thể biết key sớm hơn. Nhưng một callback portable không nên dựa vào giả định chung rằng mọi generated keys đều sẵn ở PrePersist.

### 8.3. Không persist child mới từ PrePersist

Nếu entity cần default lines, tạo chúng trong factory hoặc domain method trước khi gọi `em.persist`.

### 8.4. Không giả định invocation order giữa nhiều entity instances

Khi persist một graph có parent/children, callbacks của các instances có thể chịu cascade/provider ordering. Đừng xây invariant rằng parent callback phải tự hoàn tất việc query/update child trước callback child.

---

## 9. @PostPersist: Đã có INSERT chưa chắc đã commit

`@PostPersist` là callback gắn với thao tác persist sau SQL tương ứng, không phải một sự kiện sau khi transaction hoàn tất.

```text
BEGIN
    persist(PurchaseOrder)
    flush -> INSERT PurchaseOrder
    @PostPersist(PurchaseOrder)
    INSERT PaymentAttempt -> lỗi UNIQUE
ROLLBACK
```

Nếu callback gửi email ngay khi được gọi, email vẫn có thể đến người dùng dù Order bị rollback.

### 9.1. Generated ID có thể truy cập sau insert

Một ID do database sinh thường có thể được provider cung cấp tại PostPersist theo lifecycle semantics. Nhưng **có ID không chứng minh đã commit**.

### 9.2. Không publish OrderCreated ở đây

```java
@PostPersist
void wrong() {
    messageBroker.publish(
        new OrderCreatedEvent(id)
    );
}
```

Thông báo qua broker không rollback cùng database. Dùng outbox hoặc một integration after-commit nếu yêu cầu độ bền thấp hơn.

### 9.3. Ghi log có thể khác business event

Một log debug ngắn về lifecycle có thể hữu ích, nhưng không dùng nó làm durable audit ledger hoặc xác nhận đơn hàng đã thành công.

---

## 10. @PreUpdate: Không phải callback của mọi setter

```java
@PreUpdate
void beforeUpdate() {
    updatedAt = Instant.now();
}
```

Provider quyết định khi nào phải UPDATE row. Một setter không kích hoạt PreUpdate ngay lập tức.

### 10.1. Entity clean không bắt buộc gọi PreUpdate

Nếu chỉ `find` rồi commit, không có dirty state, application không nên kỳ vọng PreUpdate được gọi để tự cập nhật `updatedAt`.

### 10.2. New entity được persist rồi sửa

Trong cùng transaction, một new entity được persist, sau đó thay field trước SQL INSERT, provider có thể ghi final state trực tiếp qua INSERT. Không dựa vào việc PreUpdate chắc chắn cũng xuất hiện.

### 10.3. Timing của dirty checking phụ thuộc provider

Callback được phép sửa non-relationship state, nhưng không nên khẳng định một SQL statement được sinh với đúng số lần hoặc đúng thời điểm field dirty trên mọi providers.

### 10.4. Heartbeat không nên nằm ở PreUpdate

Nếu yêu cầu là cập nhật `lastViewedAt` sau mỗi read, PreUpdate không phù hợp. Một read có thể không làm entity dirty, và mỗi request không có nghĩa có UPDATE.

### 10.5. Không truy vấn DB trong PreUpdate để xác minh quan hệ

Validation liên quan Customer, Inventory, Payment hoặc số child cần được thực hiện trước ở service dưới transaction/locking phù hợp.

---

## 11. @PostUpdate: Không phải điểm commit

Sai:

```java
@PostUpdate
void updateSearchIndex() {
    searchClient.index(this);
}
```

Search index có thể được cập nhật trong khi DB transaction vẫn chưa commit. Một constraint failure sau đó có thể rollback DB và để lại search document không tồn tại/không đồng bộ.

### 11.1. Callback không biết domain intent

Một SQL UPDATE có thể do đổi description, version hoặc state khác. Chỉ vì PostUpdate chạy không có nghĩa một domain event như `OrderPaid` hay `StockReserved` đã xảy ra.

### 11.2. Network I/O làm kéo dài transaction

Search indexing, HTTP hoặc broker calls có thể giữ database transaction và row locks mở lâu hơn. Điều này tăng latency, contention và nguy cơ timeout.

---

## 12. @PreRemove: Kiểm tra cục bộ, không xóa graph thủ công

Một callback có thể kiểm tra basic state nếu thực sự cần:

```java
@PreRemove
void validateRemoval() {
    if (protectedRecord) {
        throw new IllegalStateException(
            "Protected record cannot be removed"
        );
    }
}
```

Nhưng không nên dùng callback để query các Products tham chiếu Category:

```java
@PreRemove
void wrong() {
    long count = em.createQuery(
        "SELECT COUNT(p) FROM Product p " +
        "WHERE p.category = :category",
        Long.class
    )
    .setParameter("category", this)
    .getSingleResult();
}
```

### 12.1. Thay thế bằng service và DB constraints

Service thực hiện check references nếu cần phản hồi nghiệp vụ sớm, sau đó remove trong transaction. Foreign key constraint bảo vệ khỏi race khi writer khác thêm reference sau bước kiểm tra.

### 12.2. Đừng gọi em.remove(child) từ callback

Cascade REMOVE/orphanRemoval và relationship modifications phải được thiết kế ở mapping và domain/service code, không tự thao tác EntityManager trong lifecycle hook.

---

## 13. @PostRemove: Delete vẫn có thể rollback

Một PostRemove callback có thể diễn ra sau thao tác DELETE của entity, nhưng transaction vẫn có thể rollback.

Sai:

```java
@PostRemove
void removeStoredFile() {
    objectStorage.delete(fileKey);
}
```

Nếu database rollback, record có thể vẫn tồn tại nhưng file đã bị xóa vĩnh viễn.

**Thay thế:** lưu outbox record hoặc deferred cleanup command trong transaction, sau commit thực hiện remote delete idempotently.

---

## 14. @PostLoad: Khi nào phù hợp?

```java
@Entity
public class InvoiceLine {

    @Id
    private Long id;

    private BigDecimal quantity;

    private BigDecimal unitPrice;

    @Transient
    private BigDecimal computedTotal;

    @PostLoad
    void afterLoad() {
        computedTotal =
            quantity.multiply(unitPrice);
    }
}
```

Callback chỉ đọc basic fields của InvoiceLine và ghi một transient field của chính entity.

### 14.1. Không duyệt lazy associations

Không nên:

```java
@PostLoad
void wrong() {
    computedTotal = lines.stream()
        .map(OrderLine::getTotal)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
}
```

Nếu `lines` là `@OneToMany`, callback truy cập other entities và có thể khởi tạo lazy collection.

### 14.2. Derived field có thể stale

Nếu quantity được thay đổi sau PostLoad, `computedTotal` không tự được tính lại. Nếu value luôn phải đồng bộ, một getter tính trực tiếp hoặc domain method có thể rõ hơn.

### 14.3. Không bảo đảm mỗi find đều có PostLoad

Nếu entity đã managed trong L1, find cùng identity thường trả instance cũ; không có load mới thì không có lý do PostLoad phải chạy lại.

### 14.4. Refresh khác PostLoad

`em.refresh(entity)` có thể nạp lại state và kích hoạt lifecycle events phù hợp, nhưng refresh có thể ghi đè pending changes. Không gọi refresh chỉ để “ép callback hoạt động”.

---

## 15. Entity callback và entity listener khác nhau ở đâu?

Callback có thể nằm ngay trong entity:

```java
@Entity
public class ProductLabel {

    @Id
    private Long id;

    private String label;

    @PrePersist
    void onCreate() {
        if (label != null) {
            label = label.strip();
        }
    }
}
```

Hoặc trong listener riêng:

```java
public class NameListener {

    @PrePersist
    public void beforeCreate(Object entity) {
        if (entity instanceof Normalizable n) {
            n.normalize();
        }
    }
}
```

```java
public interface Normalizable {
    void normalize();
}
```

```java
@Entity
@EntityListeners(NameListener.class)
public class ProductLabel implements Normalizable {

    @Id
    private Long id;

    private String label;

    @Override
    public void normalize() {
        if (label != null) {
            label = label.strip();
        }
    }
}
```

### 15.1. Chữ ký callback phải theo JPA

Entity callback method không nhận tham số, thường trả `void`; entity listener callback nhận entity instance. Callback không phải static/final tùy giới hạn chữ ký chuẩn. Không thiết kế callback trả DTO, entity mới hoặc query result cho provider sử dụng.

### 15.2. Listener nên stateless

Không lưu entity đang xử lý vào mutable field `currentEntity` trong listener, vì callback instances có thể được provider tái sử dụng và việc đồng thời hóa có thể khác nhau.

### 15.3. Callback ordering

JPA định nghĩa thứ tự đối với default listeners, superclass/entity-listener callbacks, entity callbacks và metadata exclusions. Nhưng **không nên dựa vào một thứ tự tiện lợi giữa callbacks của nhiều entity instances** để thực hiện cross-entity business invariant.

### 15.4. Listener injection có thể phụ thuộc environment

Trong một số môi trường Jakarta EE/CDI, entity listeners thỏa điều kiện có thể được hỗ trợ injection. Trong Java SE hoặc Spring/provider integration khác, behavior phải được kiểm chứng. Kể cả inject được repository, điều đó không làm query bên trong callback trở nên portable.

---

## 16. @Version và optimistic locking

Một entity có:

```java
@Version
private long version;
```

Field này do JPA provider quản lý để hỗ trợ optimistic locking.

Không nên:

```java
@PreUpdate
void wrong() {
    version++;
}
```

Tự tăng version có thể phá điều kiện concurrency kiểm tra của provider.

### 16.1. Muốn tăng root revision khi sửa child?

Service có thể load root managed và gọi `em.lock(root, LockModeType.OPTIMISTIC_FORCE_INCREMENT)` trong transaction nếu domain contract yêu cầu. Không gọi EntityManager từ child callback.

### 16.2. Callback validation không thay @Version

Dù PreUpdate kiểm tra quantity, một writer khác vẫn có thể sửa dữ liệu đồng thời. Optimistic/pessimistic locking, constraints và isolation policy là vấn đề riêng.

---

## 17. Merge và detached entity

`em.merge(detached)` thường copy state của detached object vào một managed instance. Không giả định chính detached instance trở thành managed, hoặc callback chắc chắn được chạy trên object caller đang giữ.

### 17.1. Merge có thể liên quan nhiều lifecycle paths

Nếu input đại diện cho new entity, merge có thể dẫn đến persist semantics trên managed copy. Nếu existing entity không dirty, có thể không có SQL UPDATE. Không mặc định mọi merge luôn tạo PostUpdate.

### 17.2. Không merge lại từ callback

```java
@PreUpdate
void wrong() {
    em.merge(this);
}
```

Đây là nested persistence operation và nằm ngoài phạm vi nên thực hiện trong callback.

### 17.3. Dữ liệu detached không nên được “sửa ngầm”

Nếu client gửi một detached snapshot có basic field sai, validate ở DTO/command boundary. Không phụ thuộc callback trên managed copy sẽ cập nhật reference detached mà caller còn dùng.

---

## 18. RuntimeException và transaction rollback

Một callback có thể ném unchecked exception:

```java
@PrePersist
@PreUpdate
void validate() {
    if (quantity <= 0) {
        throw new IllegalStateException(
            "Quantity must be positive"
        );
    }
}
```

JPA có quy tắc xử lý runtime exceptions từ lifecycle callback; transaction có thể bị đánh dấu rollback và persistence operation thất bại.

### 18.1. Lỗi có thể xuất hiện muộn

Nếu provider gọi PreUpdate khi flush/commit, service code đã chạy qua nhiều dòng trước khi exception xuất hiện. Error handler phải bao phủ transaction boundary, không chỉ setter.

### 18.2. Không nuốt exception rồi tiếp tục

Nếu kiểm tra invariant thất bại mà callback catch và chỉ ghi log, DB update có thể tiếp tục. Với điều kiện bắt buộc, không biến lỗi thành success.

### 18.3. Không retry trong cùng transaction đã thất bại

Sau rollback-only/failure, phải rollback và tạo transaction/context mới nếu workflow cần retry, sau đó tải lại state và revalidate invariant.

---

## 19. Audit timestamps: Trường hợp phổ biến nhưng có giới hạn

```java
@MappedSuperclass
public abstract class AuditableEntity {

    @Column(
        name = "created_at",
        nullable = false,
        updatable = false
    )
    private Instant createdAt;

    @Column(
        name = "updated_at",
        nullable = false
    )
    private Instant updatedAt;

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();

        if (createdAt == null) {
            createdAt = now;
        }

        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

### 19.1. Vì sao phù hợp?

Callback chỉ sửa basic state của entity hiện tại. Không query database, không thao tác relationship.

### 19.2. Không bảo đảm updatedAt đổi khi không dirty

Nếu entity không cần SQL UPDATE, PreUpdate không bắt buộc được gọi.

### 19.3. Application clock khác DB clock

`Instant.now()` phụ thuộc system clock của JVM; nhiều nodes có thể lệch nhau. Với audit cần thời gian authoritative của database, cân nhắc DB-generated timestamp hoặc cơ chế khác có contract rõ.

### 19.4. Bulk SQL bỏ qua callback

Một native SQL job sửa row có thể không cập nhật `updatedAt` theo listener. Nếu mọi writers phải duy trì field, đặt policy tại DB trigger hoặc buộc mọi writer tham gia.

### 19.5. Audit actor phức tạp hơn audit time

Một callback lấy `SecurityContextHolder` hoặc request ThreadLocal có thể thất bại trong batch/async processing. Nếu cần `createdBy`/`updatedBy`, application service có thể truyền actor vào entity hoặc dùng auditing integration phù hợp.

---

## 20. Bean Validation và database constraints

Một số invariant không cần callback riêng:

```java
@Entity
public class OrderLine {

    @Id
    private Long id;

    @Min(1)
    private int quantity;

    @NotNull
    private BigDecimal unitPrice;
}
```

Database:

```sql
ALTER TABLE order_line
ADD CONSTRAINT ck_order_line_quantity
CHECK (quantity > 0);
```

### 20.1. Vai trò của từng lớp

- Request validation: phát hiện input sai sớm.
- Domain methods: giữ business state transitions hợp lệ.
- Bean Validation: ràng buộc khai báo cho attributes/objects.
- Lifecycle callback: normalize/kiểm tra local state khi JPA xử lý entity.
- Database constraint: bảo vệ mọi writers, kể cả native/external SQL.

### 20.2. Callback không thay cross-entity validation

Điều kiện như “Customer đang active”, “Inventory còn hàng” hoặc “không có Product tham chiếu Category” cần service/repository/transaction và constraints/locks phù hợp. Không query DB từ callback để làm cross-aggregate validation.

---

## 21. Không dùng callback cho network side effects

Những operation không nên thực hiện trong callback:

- Gửi email, SMS, push notification.
- Gọi HTTP/gRPC service khác.
- Charge/refund payment.
- Publish broker event.
- Ghi/xóa file cloud storage.
- Update search index từ mạng.
- Trigger workflow dài.
- Tạo thread, background job hoặc async task.

### 21.1. Vì sao không an toàn?

```text
BEGIN
    UPDATE Order
    @PostUpdate -> send email
    INSERT khác -> lỗi UNIQUE
ROLLBACK
Email đã gửi không được rollback
```

Ngoài ra, callback có thể chạy lại khi transaction được retry, gây duplicate notifications.

### 21.2. Không giữ network call trong flush

Một HTTP call chậm bên trong callback có thể giữ DB connection/row locks trong khi provider chờ. Điều này gây contention và làm latency khó đoán.

### 21.3. Log debug không phải business event

Log đơn giản phục vụ chẩn đoán có thể được chấp nhận, nhưng vẫn không chứng minh commit. Không dùng log callback làm audit ledger hoặc thông báo “đơn hàng đã lưu thành công”.

---

## 22. Thay thế 1: Application service

Application service sở hữu transaction, có đủ bối cảnh nghiệp vụ và được phép điều phối nhiều repositories/entities.

```java
@Service
public class OrderApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void addLine(
            long orderId,
            AddLineCommand command) {

        PurchaseOrder order = em.find(
            PurchaseOrder.class,
            orderId
        );

        Product product = em.find(
            Product.class,
            command.productId()
        );

        order.addLine(
            OrderLine.create(
                product,
                command.quantity()
            )
        );
    }
}
```

Relationships được cập nhật qua domain method **trước khi provider thực thi callback**. Nếu cần khóa, service quyết định dùng `@Version`, `PESSIMISTIC_WRITE` hoặc conditional SQL phù hợp.

Callback của các entities chỉ nên xử lý concern cục bộ như chuẩn hóa một basic field.

---

## 23. Thay thế 2: Transactional outbox

Khi cần phát `OrderCreated` event chỉ cho Order đã commit, transactional outbox là pattern thường phù hợp hơn lifecycle callback.

```text
@Transactional service
         |
         +--- persist(PurchaseOrder)
         |
         +--- persist(OutboxMessage)
         |
         v
       COMMIT
         |
         v
Outbox publisher đọc committed rows
         |
         v
Publish broker (retry/idempotency)
```

Ví dụ:

```java
@Transactional
public void placeOrder(PlaceOrderCommand command) {

    PurchaseOrder order =
        orderFactory.create(command);

    em.persist(order);

    OutboxMessage event =
        OutboxMessage.orderCreated(
            order.getBusinessKey(),
            command.requestId()
        );

    em.persist(event);
}
```

### 23.1. Vì sao outbox an toàn hơn PostPersist?

Hai records nằm trong cùng database transaction; nếu rollback, cả Order và OutboxMessage đều không được commit. Publisher xử lý outbox sau commit.

### 23.2. Không có exactly-once mặc định

Publisher có thể send thành công rồi crash trước khi đánh dấu sent. Consumer cần idempotency/event ID, và hệ thống cần retry/replay policy.

### 23.3. Đừng tạo outbox bằng callback gọi EntityManager

Dù outbox là pattern đúng, gọi `em.persist(outbox)` từ `@PostPersist` vẫn là nested persistence operation không portable. Outbox creation thuộc service transaction.

---

## 24. Thay thế 3: Spring after-commit listener

Một ứng dụng Spring có thể publish application event trong service:

```java
@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void approveOrder(long orderId) {
        // Load, validate, mutate Order.
        events.publishEvent(
            new OrderApprovedEvent(orderId)
        );
    }
}
```

Listener:

```java
@Component
public class NotificationHandler {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onCommitted(OrderApprovedEvent event) {
        // Send notification theo delivery policy.
    }
}
```

`@TransactionalEventListener` là **Spring transaction event integration**, không phải JPA lifecycle callback.

### 24.1. Lợi ích

Handler gắn với transaction phase sau commit, tránh thông báo thành công khi transaction rollback thông thường.

### 24.2. Giới hạn

Nếu process crash sau DB commit nhưng trước khi handler xử lý, event có thể mất. Với yêu cầu độ bền cao, dùng transactional outbox.

### 24.3. Ghi DB trong after-commit

Nếu after-commit handler cần tiếp tục ghi DB, phải mở transaction mới phù hợp. Không giả định transaction vừa commit vẫn là transaction active cho writes mới.

---

## 25. Callback và transaction boundary

### 25.1. RESOURCE_LOCAL

```java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    em.persist(order);

    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
```

Callback có thể chạy trong persist/flush/commit path. Exception tại callback có thể xuất hiện khi commit.

### 25.2. JTA/Spring-managed transaction

Transaction do container/framework sở hữu. Callback không nên tự bắt đầu/commit transaction khác hay gọi `getTransaction()` để quản lý EntityManager.

### 25.3. PostLoad có thể xảy ra trên read path

Không giả định mọi callback đều chạy cùng security principal, cùng HTTP request thread hoặc một writable transaction. Nếu logic cần actor, truyền từ application service hoặc dùng audited integration có contract rõ.

---

## 26. Bulk JPQL và native SQL không đi qua cùng lifecycle

JPQL bulk update:

```java
int affected = em.createQuery(
    """
    UPDATE CatalogCategory c
    SET c.archived = true
    WHERE c.id IN :ids
    """
)
.setParameter("ids", ids)
.executeUpdate();
```

Không mặc định gọi `@PreUpdate`/`@PostUpdate` trên từng entity row như khi thay đổi managed instances.

Native SQL:

```sql
UPDATE catalog_category
SET archived = TRUE
WHERE id = 10;
```

cũng không tự gọi entity callback của JPA. Tương tự các scripts, ETL hoặc JDBC services khác không nằm trong lifecycle callback mechanism.

### 26.1. Hệ quả

- Không dùng callback làm data integrity layer duy nhất.
- Dùng DB constraints cho invariant áp dụng cho mọi writers.
- Thiết kế auditing/invalidation bao phủ những đường ghi ngoài JPA.
- Nhận biết persistence context có thể stale sau bulk DML.

---

## 27. Kiểm thử lifecycle callback

Một bộ integration tests nên có:

### 27.1. Test PrePersist

Tạo Category với code chưa normalize, persist/commit và đọc lại trong EntityManager mới. Xác nhận giá trị basic fields được lưu đúng. Không giả định IDENTITY ID đã sẵn tại PrePersist.

### 27.2. Test PreUpdate

Load managed entity, sửa basic field, flush/commit, đọc lại `updatedAt`. Test thêm trường hợp entity clean; không viết assertion buộc PreUpdate chạy khi không cần SQL UPDATE.

### 27.3. Test PostLoad

Load entity trong context mới, xác nhận derived transient field. Sau đó sửa basic field và xem derived value có stale không.

### 27.4. Test rollback

Trigger callback rồi gây một lỗi constraint sau đó, rollback và đọc dữ liệu bằng EM mới. Xác nhận external side effects không được dùng làm dấu hiệu transaction thành công.

### 27.5. Test merge

Merge detached instance, xem managed copy và state thực sự được lưu. Đừng giả định detached input nhận cùng callback state.

### 27.6. Test bulk DML

Dùng JPQL bulk UPDATE và xác nhận invariant vẫn được DB constraints bảo vệ; không phụ thuộc callback được gọi cho từng row.

### 27.7. Test SQL/N+1

Query nhiều entities với instrumentation SQL. Một PostLoad callback không nên tự mở lazy associations làm số queries tăng không dự đoán được.

### 27.8. Test provider portability

Nếu project cần chạy trên Hibernate và EclipseLink, kiểm thử invocation và transaction semantics trên cả hai. Không coi một unit test mock EntityManager là bằng chứng behavior portable.

---

## 28. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng giải quyết |
|---|---|---|
| `@PreUpdate` không chạy sau setter | Callback không là setter observer | Validate ở domain/service |
| `@PostPersist` gửi email cho record rollback | PostPersist không phải after-commit | Outbox/after-commit |
| Callback gọi repository rồi lỗi flush | Nested persistence operations | Query ở service |
| `@PostLoad` tạo N+1 | Truy cập lazy association | Projection/fetch plan |
| ID null trong PrePersist | IDENTITY chưa sinh khi INSERT | Chọn key strategy phù hợp |
| Callback thêm child gây cascade khác dự kiến | Sửa relationship khi provider xử lý | Xây graph trước persist |
| Callback sửa `@ManyToOne` | Relationship mutation | Domain method/service |
| Tăng tay `@Version` gây optimistic lỗi | Provider sở hữu version | Để JPA tăng |
| Listener inject Repository nhưng vẫn lỗi | Injection không xóa giới hạn callback | Đưa DB operation lên service |
| SecurityContext null trong batch | Phụ thuộc request ThreadLocal | Truyền actor rõ |
| `updatedAt` không đổi khi entity clean | PreUpdate chỉ có thể chạy khi UPDATE | Không dùng như last-viewed |
| Native SQL bỏ qua validation | Không gọi JPA callbacks | DB constraints |
| Bulk DELETE không gọi PreRemove từng entity | Bulk DML bypass lifecycle | Service/constraints |
| Exception chỉ xuất hiện tại commit | Flush deferred | Handle transaction boundary |
| Retry gửi message trùng | Callback có external side effect | Outbox/idempotency |
| PostLoad derived total bị stale | Không tính lại sau setter | Derived getter/domain method |
| Listener có mutable shared state | Không stateless | Stateless listener |
| Thứ tự parent-child callback khác provider | Phụ thuộc graph ordering | Domain/service orchestration |

---

## 29. Bài tập thực hành

### Bài 1. Chuẩn hóa code

`@PrePersist` trim/uppercase String của chính entity.

**Đáp án:** Thường nằm trong phạm vi portable non-relationship state.

### Bài 2. Audit entity mới

`@PreUpdate` gọi `em.persist(new AuditLog(...))`.

**Đáp án:** Không nên. Dùng application service hoặc auditing framework có integration đúng.

### Bài 3. PostLoad đọc Customer

Callback gọi `customer.getDisplayName()`.

**Đáp án:** Truy cập entity khác/lazy association. Dùng DTO projection hoặc service mapping.

### Bài 4. Thêm OrderLine

`@PrePersist` thêm OrderLine vào Order.lines.

**Đáp án:** Sửa relationship trong callback không nên; xây graph trước persist.

### Bài 5. Điền updatedAt

`@PreUpdate` điền basic timestamp.

**Đáp án:** Có thể phù hợp, nhưng callback không bảo đảm chạy cho clean entity.

### Bài 6. Publish Kafka từ PostUpdate

**Đáp án:** Sai transaction semantics; DB có thể rollback. Dùng transactional outbox.

### Bài 7. Tạo orderNumber từ IDENTITY ID

Làm trong `@PrePersist`.

**Đáp án:** ID có thể chưa được sinh. Chọn database sequence/application key strategy phù hợp.

### Bài 8. PostPersist đồng nghĩa commit?

**Đáp án:** Không. Transaction có thể rollback sau PostPersist.

### Bài 9. Callback ném IllegalStateException

**Đáp án:** Transaction có thể rollback; exception có thể lộ tại flush/commit.

### Bài 10. JPQL bulk UPDATE

Bulk update 1.000 rows, có gọi PreUpdate 1.000 lần không?

**Đáp án:** Không theo per-entity managed lifecycle. Không dựa callback cho integrity của bulk DML.

### Bài 11. Tăng `@Version`

Callback làm `version++`.

**Đáp án:** Không. Version thuộc trách nhiệm provider.

### Bài 12. Listener inject Repository

**Đáp án:** Khả năng injection không làm query trong callback trở nên portable.

### Bài 13. Tính transient total ở PostLoad

**Đáp án:** Có thể phù hợp với basic fields, nhưng total có thể stale nếu quantity đổi sau load.

### Bài 14. Delete cloud file trong PostRemove

**Đáp án:** Không an toàn khi DB rollback. Dùng outbox/idempotent external cleanup.

### Bài 15. Spring AFTER_COMMIT

`@TransactionalEventListener(AFTER_COMMIT)` có phải JPA callback?

**Đáp án:** Không; đó là Spring transaction event mechanism.

### Bài 16. Script JDBC

Một script update DB trực tiếp.

**Đáp án:** JPA callbacks không mặc định chạy. DB constraints/audit writer policy cần bao phủ.

### Bài 17. Query trong PreRemove

Service muốn biết Category có Product con không.

**Đáp án:** Query ở service, dùng FK constraints và concurrency control; không query trong callback.

### Bài 18. ThreadLocal principal

Callback lấy SecurityContext trong background job.

**Đáp án:** Không portable/không ổn định. Service truyền actor hoặc dùng auditing integration được kiểm chứng.

### Bài 19. Thứ tự parent/child callbacks

**Đáp án:** Không thiết kế cross-entity invariant phụ thuộc callback ordering giữa instances.

### Bài 20. Logging trong PostUpdate

**Đáp án:** Có thể phục vụ debug nhưng không là bằng chứng commit thành công.

---

## 30. Checklist khi quyết định tạo lifecycle callback

1. Logic có chỉ liên quan **non-relationship state của chính entity** không?
2. Có thật sự cần callback hay một domain method dễ hiểu hơn?
3. Có gọi EntityManager hoặc query operations?
4. Có gọi repository gián tiếp?
5. Có đọc một managed entity khác?
6. Có khởi tạo lazy association?
7. Có thay `@ManyToOne`/`@OneToMany` hoặc collection membership?
8. Có tự persist/remove một entity khác?
9. Có gọi flush/clear/refresh/merge từ callback?
10. Có phụ thuộc IDENTITY ID trong PrePersist?
11. Có phụ thuộc PreUpdate chạy trên entity clean?
12. Có coi PostPersist/PostUpdate/PostRemove là after-commit?
13. Có network/email/broker side effect?
14. Có tự tăng `@Version`?
15. Có phụ thuộc callback chạy exactly once?
16. Có mutable shared state trong listener?
17. Có dựa vào CDI/Spring injection không được kiểm chứng?
18. Có dùng ThreadLocal actor/transaction assumptions?
19. Có validation trước service/Bean Validation/DB constraints?
20. Có xử lý exception tại flush/commit boundary?
21. Có external writers/bulk DML bỏ qua callbacks?
22. Có test rollback, merge, lazy loading?
23. Có cần outbox hoặc after-commit integration?
24. Có test behavior trên provider/DB production?
25. Có tài liệu hóa vendor-specific exceptions nếu buộc sử dụng?

---

## 31. Sơ đồ chọn đúng tầng

```text
                 Một entity cần xử lý lifecycle
                              |
                              v
                    Chỉ basic state của
                    chính entity đó?
                       /          \
                     Không        Có
                      |            |
                      v            v
              Application service  Có thay relationships?
                                     /         \
                                   Có          Không
                                    |            |
                                    v            v
                                  Service     Có query/EM/
                                              external side effects?
                                                /      \
                                              Có        Không
                                               |          |
                                               v          v
                                         Service/outbox  Callback
                                                         có thể phù hợp
                                                              |
                                                              v
                                                    Test flush/rollback/
                                                    provider behavior
```

Nếu mục đích là normalize String hoặc điền timestamp, callback thường là một extension point hợp lý. Nếu là xây graph, truy vấn DB, quyết định business policy dựa trên entities khác hoặc phát notification cho committed transaction, hãy dùng service/domain/event/outbox.

---

## 32. Tổng kết

1. **Lifecycle callback không phải application service** và không nên điều phối persistence operations.
2. **Ranh giới portable chủ yếu cho phép thay non-relationship state của chính entity**.
3. **Tránh EntityManager/query/repository calls**, kể cả khi query bị che sau service abstraction.
4. **Tránh truy cập entity instances khác, lazy loading và relationship mutations**.
5. **PrePersist có thể chạy trước khi IDENTITY ID được cấp**.
6. **PreUpdate không phải field-change listener** và không đảm bảo chạy cho clean entity.
7. **PostPersist/PostUpdate/PostRemove không phải after-commit hooks**; rollback vẫn có thể xảy ra.
8. **@PostLoad phù hợp với local derived state**, nhưng không nên load associations và derived field có thể stale sau setter.
9. **@Version do JPA provider quản lý**, không được tùy tiện tăng từ callback.
10. **Validation phải có nhiều lớp**: service/domain, Bean Validation, DB constraints.
11. **Bulk JPQL và native SQL không bảo đảm per-entity callbacks**.
12. **Runtime exceptions có thể làm transaction rollback**, và lỗi có thể chỉ xuất hiện khi flush/commit.
13. **Dùng application service cho cross-entity operations, relationship construction và locking**.
14. **Dùng transactional outbox hoặc after-commit integration cho external side effects**, với idempotency/retry phù hợp.
15. **Kiểm thử thực tế trên JPA provider đang dùng**, gồm dirty checking, rollback, merge, lazy loading và SQL count.

Một callback JPA đáng tin cậy thường **nhỏ, cục bộ, không truy vấn và không làm thay đổi graph**. Khi cần phối hợp nhiều entities hoặc hệ thống khác, việc đưa logic lên application service và transaction-aware integration không chỉ giúp portable hơn mà còn tránh các lỗi chỉ xuất hiện khi provider flush, transaction commit hay rollback.
