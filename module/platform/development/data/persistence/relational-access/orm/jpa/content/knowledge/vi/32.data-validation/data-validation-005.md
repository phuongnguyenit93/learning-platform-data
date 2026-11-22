# Kiểm tra quan hệ và cấu trúc đối tượng trước khi lưu trong JPA

Khi lưu dữ liệu bằng **Jakarta Persistence (JPA)**, một đối tượng thường không tồn tại độc lập. Nó có thể tham chiếu đến entity khác qua `@ManyToOne`, chứa danh sách con qua `@OneToMany`, dùng value objects qua `@Embedded` và có nhiều quy tắc nghiệp vụ trải rộng trên toàn bộ **đồ thị đối tượng** (*object graph*).

Ví dụ, lệnh tạo một đơn hàng có thể trông hợp lệ khi nhìn riêng từng trường: mã khách hàng không rỗng, số lượng lớn hơn 0, giá không âm. Tuy nhiên, đối tượng vẫn có thể **không hợp lệ về cấu trúc** nếu dòng hàng trỏ tới một đơn khác, hai dòng trùng cùng sản phẩm khi chính sách không cho phép, sản phẩm thuộc tenant khác, khách hàng không tồn tại hoặc đơn hàng ở trạng thái `SUBMITTED` nhưng không có dòng nào.

Do đó, kiểm tra trước khi lưu không thể chỉ dừng ở `@NotNull` trên vài thuộc tính đơn lẻ.

> **Nguyên tắc chính:** Kiểm tra một object graph theo từng tầng: **hình dạng dữ liệu đầu vào → ràng buộc từng object → tính nhất quán của quan hệ → bất biến của aggregate → sự tồn tại/trạng thái trong database → ràng buộc giao dịch và tính đồng thời**. Mỗi tầng giải quyết một loại lỗi khác nhau; không một annotation nào thay thế tất cả.

Bài học thuộc chương **Kiểm tra dữ liệu** trong module **Data Persistence Relational Access ORM JPA**. Nội dung sử dụng ví dụ `PurchaseOrder`, `OrderLine`, `Product` và `Customer` để trình bày cách xây dựng, kiểm tra và lưu graph đúng; phân biệt `@Valid` với JPA cascade; kiểm tra hai chiều, ownership, orphan removal, DTO, validation groups, custom validators, transaction, concurrency và cơ chế kiểm thử.

---

## 1. “Cấu trúc đối tượng hợp lệ” nghĩa là gì?

Giả sử API nhận yêu cầu tạo đơn:

```json
{
  "customerId": 501,
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 202, "quantity": 1}
  ]
}
```

Để lưu được một đơn hàng đúng, hệ thống cần xác nhận nhiều nhóm điều kiện.

| Nhóm | Ví dụ câu hỏi | Nơi kiểm tra phù hợp |
| --- | --- | --- |
| Input shape | `items` có null không, `quantity` có dương không? | DTO validation |
| Field constraints | `reference` không rỗng, `unitPrice` không âm? | Bean Validation, domain constructors |
| Quan hệ bắt buộc | Mỗi OrderLine có Product và PurchaseOrder chưa? | JPA mapping, Bean Validation |
| Tính nhất quán hai chiều | `line.order == order` và `order.lines.contains(line)` cùng đúng? | Aggregate methods, graph validator |
| Bất biến aggregate | `SUBMITTED` order phải có ít nhất một line? | Domain method/class-level validation |
| Tồn tại dữ liệu | Customer#501, Product#101 có trong database? | Transactional service + FK |
| Business eligibility | Customer bị khóa, Product ngừng bán, sai tenant? | Domain/application service |
| Tính duy nhất | Mỗi sản phẩm có tối đa một dòng trong đơn? | Domain + DB unique constraint |
| Đồng thời | Product vừa hết hàng hoặc bị thay giá sau khi kiểm tra? | Transactions, version/locking, atomic SQL |
| Lưu trữ cuối cùng | Có bản ghi tham chiếu tới row không tồn tại? | Database FK/NOT NULL/CHECK |

Một graph **hợp lệ ở Java** chưa chắc hợp lệ khi commit: transaction khác có thể thay đổi dữ liệu sau khi ứng dụng kiểm tra. Ngược lại, một graph **lưu được xuống database** chưa chắc đáp ứng toàn bộ nghiệp vụ nếu database không có mọi ràng buộc domain.

### 1.1. Cấu trúc dữ liệu khác cú pháp dữ liệu

`@NotBlank` kiểm tra một chuỗi. Nó không thể tự khẳng định:

- Một `OrderLine` thuộc đúng `PurchaseOrder`.
- Mỗi Product chỉ xuất hiện một lần.
- Tổng tiền khớp các dòng.
- Khách hàng và sản phẩm thuộc cùng tenant.
- Đơn ở trạng thái hợp lệ trước thao tác submit.

Những điều kiện này cần kiểm tra **quan hệ giữa các thuộc tính hoặc giữa các entities**.

### 1.2. Kiểm tra sớm và bảo vệ muộn

Lý tưởng là phát hiện lỗi ngay khi tạo/cập nhật aggregate, trước khi gửi SQL. Nhưng **database constraint vẫn là lớp bảo vệ cuối cùng** đối với những điều kiện nó có thể biểu đạt, nhất là khi có nhiều writer hoặc request cạnh tranh.

Không lựa chọn “validate ở Java **hoặc** constraint ở DB”; phần lớn hệ thống cần **cả hai**.

## 2. Mô hình ví dụ: đơn hàng và các quan hệ

Ta dùng graph:

```text
                   +--------------------+
                   | Customer           |
                   | id, tenantId       |
                   | active             |
                   +--------------------+
                          ^
                          | ManyToOne
                          |
+-------------------------------------------------+
| PurchaseOrder                                   |
| id, tenantId, status, createdAt, version        |
| customer : Customer                             |
| lines : List<OrderLine>                         |
+-------------------------------------------------+
                     | 1
                     | OneToMany
                     v *
           +-------------------------+
           | OrderLine               |
           | id, quantity, unitPrice |
           | order : PurchaseOrder   |
           | product : Product       |
           +-------------------------+
                          |
                          | ManyToOne
                          v
                   +---------------------+
                   | Product             |
                   | id, tenantId, sku   |
                   | active, unitPrice   |
                   +---------------------+
```

**Nghiệp vụ giả định:**

1. Mỗi PurchaseOrder thuộc đúng một Customer.
2. PurchaseOrder có thể ở trạng thái `DRAFT` khi chưa có lines; `SUBMITTED` cần ít nhất một line.
3. Mỗi OrderLine thuộc đúng một PurchaseOrder và tham chiếu một Product đang hợp lệ.
4. Một Product chỉ được xuất hiện một lần trong cùng PurchaseOrder; nếu người dùng thêm lần nữa, nghiệp vụ gộp quantity hoặc từ chối.
5. Product và Customer phải thuộc tenant của PurchaseOrder.
6. `quantity >= 1`, `unitPrice >= 0`.
7. Giá trên dòng là **snapshot giá tại thời điểm tạo đơn**, không tin giá do client tự gửi.
8. Không cho sửa các dòng sau khi đơn đã SUBMITTED theo policy ví dụ.
9. Xóa một OrderLine khỏi aggregate phải phù hợp `orphanRemoval` và transaction.

Những giả định này tạo ra một ví dụ nhất quán để bàn về **kiểm tra cấu trúc trước khi persist**. Hệ thống khác có thể có quy tắc khác, chẳng hạn cho phép trùng Product theo lot/đơn vị tính.

## 3. Đừng bắt đầu bằng việc lưu DTO như entity

Một request DTO là dữ liệu từ ranh giới hệ thống; nó không phải một graph JPA đã hợp lệ.

Ví dụ:

```java
package com.example.orders.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public record CreateOrderRequest(
    @NotNull Long customerId,
    @NotEmpty List<@NotNull @Valid LineRequest> items
) {
    public record LineRequest(
        @NotNull Long productId,
        @Min(1) int quantity
    ) {}
}
```

Đây là **validation của request shape**:

- `customerId` phải được cung cấp.
- `items` không rỗng.
- Mỗi phần tử `items` không null.
- Mỗi `productId` không null.
- Mỗi `quantity` ít nhất 1.

Nó **không chứng minh** ID tương ứng tồn tại trong database hay Product đang active.

### 3.1. Vì sao không bind JSON trực tiếp vào entity?

Nếu HTTP request được deserialize trực tiếp thành `PurchaseOrder` hoặc `OrderLine`, client có thể cố gửi:

```json
{
  "id": 999,
  "status": "SUBMITTED",
  "version": 17,
  "customer": {"id": 501},
  "lines": [
    {
      "id": 700,
      "order": {"id": 123},
      "product": {"id": 101},
      "unitPrice": "0.01"
    }
  ]
}
```

Rủi ro gồm:

- **Mass assignment:** client sửa field nội bộ không được phép.
- Client giả mạo `version` hoặc `status`.
- Client đưa ID child đã thuộc order khác.
- Client gửi trạng thái quan hệ hai chiều không nhất quán.
- Client tự quyết định giá thay vì server xác định.
- `merge()` một graph detached không đầy đủ có thể dẫn tới hiệu ứng ngoài ý muốn.

Nên dùng **command/DTO có những field được phép nhận**, rồi xây dựng aggregate trong service.

### 3.2. Request validation là bước đầu, không phải kết luận

Một request đi qua `@Valid` có thể vẫn tham chiếu Product#101 đã bị xóa hoặc bị khóa. Những điều kiện liên quan tới DB phải được kiểm tra trong transaction theo nhu cầu.

## 4. Mapping JPA phải thể hiện đúng quan hệ

Ví dụ các entity dùng Jakarta Persistence và Jakarta Bean Validation. Các đoạn code được tách theo class và giả định chạy trên Java hỗ trợ `record` khi sử dụng request record.

### 4.1. Customer

```java
package com.example.orders.domain;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @NotBlank
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public boolean isActive() {
        return active;
    }
}
```

### 4.2. Product

```java
package com.example.orders.domain;

import jakarta.persistence.*;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @NotBlank
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @NotBlank
    @Column(nullable = false, length = 80)
    private String sku;

    @NotNull
    @DecimalMin("0.00")
    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal unitPrice;

    @Column(nullable = false)
    private boolean active;

    @Version
    private Long version;

    protected Product() {}

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public boolean isActive() {
        return active;
    }
}
```

Một Product là aggregate/đối tượng dữ liệu khác với Order. OrderLine **tham chiếu** Product, chứ không sở hữu lifecycle của Product; không đặt `CascadeType.REMOVE` từ OrderLine sang Product.

### 4.3. OrderStatus

```java
package com.example.orders.domain;

public enum OrderStatus {
    DRAFT,
    SUBMITTED,
    CANCELLED
}
```

### 4.4. PurchaseOrder — root aggregate

```java
package com.example.orders.domain;

import jakarta.persistence.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status = OrderStatus.DRAFT;

    @NotNull
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    private Long version;

    @Valid
    @OneToMany(
        mappedBy = "order",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
            String tenantId,
            Customer customer,
            Instant createdAt) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId");
        }

        this.tenantId = tenantId;
        this.customer = Objects.requireNonNull(customer);
        this.createdAt = Objects.requireNonNull(createdAt);
    }

    public void addLine(Product product, int quantity) {
        requireDraft();
        Objects.requireNonNull(product, "product");

        if (quantity < 1) {
            throw new IllegalArgumentException("quantity");
        }

        if (product.getId() == null) {
            throw new IllegalArgumentException(
                "Product must already exist"
            );
        }

        boolean duplicate = lines.stream().anyMatch(line ->
            product.getId().equals(line.getProduct().getId())
        );

        if (duplicate) {
            throw new IllegalArgumentException(
                "Product already exists in this order"
            );
        }

        OrderLine line = new OrderLine(
            this,
            product,
            quantity,
            product.getUnitPrice()
        );

        lines.add(line);
    }

    public void removeLine(OrderLine line) {
        requireDraft();
        if (lines.remove(line)) {
            line.detachFromOrder();
        }
    }

    public void submit() {
        requireDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Submitted order requires a line"
            );
        }

        if (customer == null || !customer.isActive()) {
            throw new IllegalStateException(
                "Customer is not eligible"
            );
        }

        for (OrderLine line : lines) {
            if (line.getOrder() != this) {
                throw new IllegalStateException(
                    "Broken order-line association"
                );
            }
            if (line.getProduct() == null ||
                    !line.getProduct().isActive()) {
                throw new IllegalStateException(
                    "Inactive or missing product"
                );
            }
        }

        status = OrderStatus.SUBMITTED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Order cannot be edited now"
            );
        }
    }

    public Long getId() { return id; }

    public String getTenantId() { return tenantId; }

    public Customer getCustomer() { return customer; }

    public OrderStatus getStatus() { return status; }

    public Instant getCreatedAt() { return createdAt; }

    public Long getVersion() { return version; }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

Các phương thức `addLine()`, `removeLine()` và `submit()` là **cổng thay đổi graph** thay vì để caller tự sửa List hay foreign key.

### 4.5. OrderLine — entity con

```java
package com.example.orders.domain;

import jakarta.persistence.*;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(
    name = "order_lines",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_product",
        columnNames = {"order_id", "product_id"}
    )
)
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Min(1)
    @Column(nullable = false)
    private int quantity;

    @NotNull
    @DecimalMin("0.00")
    @Column(
        name = "unit_price",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal unitPrice;

    protected OrderLine() {}

    OrderLine(
            PurchaseOrder order,
            Product product,
            int quantity,
            BigDecimal unitPrice) {

        this.order = Objects.requireNonNull(order);
        this.product = Objects.requireNonNull(product);

        if (quantity < 1) {
            throw new IllegalArgumentException("quantity");
        }

        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice");
        }

        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public Long getId() { return id; }

    public PurchaseOrder getOrder() { return order; }

    public Product getProduct() { return product; }

    public int getQuantity() { return quantity; }

    public BigDecimal getUnitPrice() { return unitPrice; }
}
```

`OrderLine.order` là **owning side** của quan hệ `@OneToMany(mappedBy="order")`; cột `order_id` thuộc bảng `order_lines`.

### 4.6. Mapping không thay thế toàn bộ kiểm tra nghiệp vụ

Ngay cả khi:

```java
@ManyToOne(optional = false)
@JoinColumn(nullable = false)
private Product product;
```

thì hệ thống vẫn cần xác định:

- Product có tồn tại không?
- Có đúng tenant không?
- Đang active không?
- User có quyền chọn Product không?
- Product có được phép bán theo rule thời điểm hiện tại không?

Mapping mô tả quan hệ với JPA/database; nó không tự xác định đầy đủ eligibility của Product.

## 5. Thứ tự xây dựng object graph trước khi persist

Một quy trình dễ kiểm soát:

```text
HTTP DTO
   |
   v
Validate request fields
   |
   v
BEGIN TRANSACTION
   |
   v
Resolve Customer và Products
   |
   v
Check tenant / active / eligibility
   |
   v
new PurchaseOrder(...)
   |
   +-- addLine(productA, 2)
   +-- addLine(productB, 1)
   |
   v
Validate structure + aggregate invariants
   |
   v
em.persist(order)
   |
   v
flush / commit
```

### 5.1. Vì sao xây graph trước khi persist?

Nó giúp phát hiện những lỗi **thuộc trách nhiệm ứng dụng** trước khi bắt đầu gửi INSERT hoặc để provider cascade vào một graph còn dang dở.

Ví dụ không nên:

```java
PurchaseOrder order = new PurchaseOrder(...);
em.persist(order);

// Sau đó mới bắt đầu gắn quan hệ theo cách tùy tiện
// và kỳ vọng mọi bước đều luôn hợp lệ.
```

JPA có thể tự flush trước một query trong cùng transaction; với `GenerationType.IDENTITY`, persist có thể cần INSERT sớm để có ID. Vì vậy “sẽ bổ sung đủ field trước commit” không phải lúc nào cũng tránh được lỗi flush/constraint giữa chừng.

### 5.2. Không nhất thiết phải có ID trước khi validate

Một entity mới dùng `@GeneratedValue` thường có `id == null` trước khi lưu.

Không nên bắt buộc:

```java
if (order.getId() == null) {
    throw new ValidationException("Invalid order");
}
```

cho một đơn hàng đang được tạo. Một graph **transient** có thể hợp lệ về domain trước khi được cấp ID. Chỉ kiểm tra ID trong những use case thực sự yêu cầu entity đã tồn tại.

## 6. Quan hệ hai chiều: cập nhật cả hai phía

Với:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

và:

```java
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
```

ta có hai tham chiếu trong memory biểu diễn cùng một quan hệ:

```text
PurchaseOrder.lines contains OrderLine#X
            ↕
OrderLine#X.order == PurchaseOrder
```

### 6.1. Lỗi: thêm vào collection nhưng không set owning side

Sai:

```java
order.getLines().add(line);
// line.order vẫn null.
```

Ngay cả khi collection thay đổi, phía sở hữu FK vẫn thiếu reference. Provider có thể INSERT child với `order_id = NULL` hoặc xử lý quan hệ không như mong đợi, dẫn tới constraint violation.

### 6.2. Lỗi: chỉ set owning side, bỏ inverse side

Sai ở mức object graph:

```java
line.setOrder(order);
// order.lines vẫn không chứa line.
```

Phía FK có thể đúng, nhưng object graph trong memory không còn nhất quán. Một service tính tổng từ `order.lines` có thể bỏ sót line dù `line.order` đã trỏ tới order.

### 6.3. Dùng một helper bảo đảm đồng bộ

Mẫu:

```java
public void addLine(Product product, int quantity) {
    OrderLine line = new OrderLine(
        this,
        product,
        quantity,
        product.getUnitPrice()
    );
    lines.add(line);
}
```

Constructor gắn `line.order = this`, rồi helper gắn line vào `order.lines`.

Tránh expose public setters cho cả hai phía nếu caller có thể phá invariant bằng việc gọi một phía riêng lẻ.

### 6.4. Tại sao không chỉ rely on @Valid?

`@Valid` có thể phát hiện `line.order == null` nếu OrderLine được validate theo graph và có `@NotNull`, nhưng **không tự thêm line vào List, không sửa FK ownership, và không tự kiểm tra equality `line.order == order`**.

Để kiểm tra đúng **tính nhất quán hai chiều**, cần helper/domain invariant hoặc custom graph validator.

## 7. @Valid và CascadeType không cùng mục đích

Đây là hai annotation dễ bị hiểu nhầm nhất.

```java
@Valid
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

Trong đó:

- **`@Valid`** thuộc **Jakarta Bean Validation**, diễn đạt ý định kiểm tra ràng buộc trên object graph được tham chiếu khi có validation cascade tương ứng.
- **`cascade = CascadeType.PERSIST`** thuộc **JPA**, diễn đạt ý định lan truyền thao tác persist tới những child entities liên quan.

### 7.1. Bảng phân biệt

| Trường hợp | `@Valid` | `CascadeType.PERSIST` |
| --- | --- | --- |
| Kiểm tra `@Min(1)` trong OrderLine khi root được validate | Có thể có, theo validation traversal | Không phải chức năng chính |
| Tự INSERT OrderLine mới khi persist PurchaseOrder | Không | Có, khi mapping và lifecycle phù hợp |
| Tự sửa `line.order` | Không | Không |
| Tự kiểm tra Product có tồn tại trong DB | Không | Không |
| Tự xóa OrderLine bị bỏ khỏi List | Không | Không; cần xem `orphanRemoval`/remove |
| Tự kiểm tra cùng tenant | Không, nếu không có constraint logic tương ứng | Không |
| Lan truyền `merge()` | Không | `CascadeType.MERGE` là cơ chế riêng |

### 7.2. Thiếu cascade dù @Valid vẫn có

```java
@Valid
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Có thể validate children thành công nhưng provider không được yêu cầu persist transient children cùng order. Kết quả có thể là children không được insert hoặc phát sinh exception tùy cách graph được quản lý.

### 7.3. Có cascade dù thiếu @Valid

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

JPA có thể persist children. Nhưng khi ứng dụng gọi `validator.validate(order)`, nếu không có `@Valid` tại đường dẫn thích hợp, các constraints của children **không tự được duyệt chỉ vì có cascade persist**.

**Hai cơ chế phải được thiết kế độc lập.**

### 7.4. Tránh cascade từ OrderLine sang Product

Không dùng:

```java
@ManyToOne(cascade = CascadeType.ALL)
private Product product;
```

nếu Product có lifecycle riêng và không thuộc sở hữu OrderLine. Khi remove OrderLine, cascade REMOVE tới Product có thể gây lỗi nặng hoặc xóa dữ liệu dùng chung.

Quan hệ tham chiếu và quan hệ sở hữu lifecycle là hai việc khác nhau.

## 8. Jakarta Bean Validation trên entity fields

Một số annotations phổ biến:

| Constraint | Ý nghĩa |
| --- | --- |
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi không null và có nội dung khác whitespace |
| `@NotEmpty` | Chuỗi/collection/map/array không rỗng theo contract |
| `@Size(min=..., max=...)` | Kích thước chuỗi/collection trong khoảng |
| `@Min`, `@Max` | Ngưỡng số nguyên/số theo contract |
| `@DecimalMin`, `@DecimalMax` | Ngưỡng số thập phân, phù hợp BigDecimal |
| `@Positive`, `@PositiveOrZero` | Số dương hoặc không âm |
| `@Pattern` | Kiểm tra biểu thức chính quy trên chuỗi |
| `@Past`, `@Future` | Ràng buộc thời gian |
| `@Valid` | Yêu cầu cascade validation vào giá trị liên quan |

### 8.1. @NotNull trên relationship

```java
@NotNull
@ManyToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Có **ba lớp ý nghĩa**:

1. `@NotNull`: một Bean Validation constraint trên reference.
2. `optional = false`: JPA metadata cho quan hệ không tùy chọn.
3. `nullable = false`: metadata cho join column ở database/schema.

Không khẳng định ba annotation là bản sao hoàn toàn của nhau. Kết hợp chúng giúp biểu đạt intention ở nhiều tầng, nhưng **FK database** vẫn cần bảo đảm tham chiếu tới một row tồn tại.

### 8.2. Giá trị primitive và null

```java
@Min(1)
private int quantity;
```

`int` không thể null; khi mới tạo, giá trị mặc định 0 sẽ không hợp lệ với `@Min(1)`.

Nếu request dùng wrapper:

```java
@NotNull
@Min(1)
private Integer quantity;
```

thì vừa phát hiện missing value, vừa phát hiện số bé hơn 1. Chọn kiểu theo contract đầu vào và mapping entity phù hợp.

### 8.3. @NotBlank không áp cho Long ID

`@NotBlank` dành cho `CharSequence`. Đừng dùng nó trên `Long customerId`. Dùng `@NotNull` và nếu cần `@Positive` trên ID field thuộc DTO.

### 8.4. @Size không xác nhận nội dung child graph

```java
@Size(min = 1)
private List<OrderLine> lines;
```

chỉ kiểm tra kích thước List. Nó không đảm bảo mỗi phần tử không null, line có Product hợp lệ hoặc `line.order` đúng owner.

Có thể kết hợp:

```java
@Valid
private List<@NotNull @Valid OrderLine> lines;
```

nhưng cũng phải hiểu các quy tắc validation traversal của Jakarta Validation, quan hệ JPA và các invariant phụ thuộc giữa các phần tử.

## 9. Explicit Validator trước persist

Có thể validate một graph trước khi gọi `em.persist()` bằng Jakarta Validation:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import java.util.Set;

Set<ConstraintViolation<PurchaseOrder>> errors =
    validator.validate(order);

if (!errors.isEmpty()) {
    throw new ConstraintViolationException(
        "Order graph is invalid",
        errors
    );
}
```

Trong Spring, `Validator` có thể được inject theo Jakarta Validation integration phù hợp. Trong Java SE, có thể tạo `ValidatorFactory`:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {

    Validator validator = factory.getValidator();

    // Validate object graph đã xây dựng hoàn chỉnh.
    validator.validate(order);
}
```

### 9.1. Ưu điểm của explicit validation

- Phát hiện field lỗi **trước thao tác SQL**.
- Dễ chuyển violations thành lỗi API có cấu trúc.
- Có thể chọn **validation groups** theo use case.
- Có thể kiểm tra object còn transient, chưa có database ID.
- Có thể gọi trong unit tests mà không cần khởi tạo EntityManager.

### 9.2. Những điều explicit Validator không tự làm

Nó không tự:

- Kiểm tra customerId/productId trong database.
- Xác nhận uniqueness dưới tranh chấp đồng thời.
- Sửa quan hệ hai chiều.
- Persist transient children.
- Khóa database rows.
- Commit transaction.
- Thay thế database constraints.

Nên kết hợp explicit Bean Validation với domain checks và transaction logic.

### 9.3. ConstraintViolationException có thể bị nhầm

Hai exception khác nhau có tên tương tự:

- `jakarta.validation.ConstraintViolationException`: ràng buộc Bean Validation thất bại.
- Các exception database/provider về constraint violation: lỗi unique, FK, check, not-null khi SQL chạy.

Phải phân biệt nơi lỗi xảy ra và chuẩn hóa cách trả lỗi API; không bắt mọi exception có chuỗi “constraint violation” rồi giả định cùng nguyên nhân.

## 10. Tự động tích hợp Bean Validation với JPA lifecycle

Trong môi trường có Bean Validation provider được tích hợp và validation mode phù hợp, JPA có thể thực hiện Bean Validation khi xử lý các lifecycle events như **pre-persist** và **pre-update**.

Ví dụ cấu hình:

```xml
<persistence-unit name="ordersPU">
    <validation-mode>AUTO</validation-mode>
</persistence-unit>
```

Đoạn này là phần tử minh họa trong `persistence.xml`, không phải toàn bộ file.

Các chế độ tổng quát:

| Mode | Ý nghĩa |
| --- | --- |
| `AUTO` | Kích hoạt tích hợp theo khả năng hiện diện của Bean Validation provider và semantics JPA |
| `CALLBACK` | Yêu cầu tích hợp callback validation phù hợp; thiếu provider tương ứng có thể gây lỗi bootstrap |
| `NONE` | Không sử dụng automatic Bean Validation lifecycle integration |

### 10.1. Phát hiện lỗi ở flush hoặc commit

Một đoạn:

```java
em.persist(order);

// Provider có thể validate trong quá trình lifecycle.
em.flush();

// Commit vẫn là transaction boundary cuối cùng.
tx.commit();
```

Nếu automatic validation thất bại, exception có thể xuất hiện khi persist/flush/commit tùy lifecycle/provider và thời điểm thực thi. **Không dựa vào một điểm ném lỗi duy nhất.**

### 10.2. Validation groups mặc định

Automatic lifecycle validation thường áp dụng những nhóm theo cấu hình JPA; mặc định pre-persist và pre-update dùng `Default` group, còn pre-remove không tự thực hiện validation theo kiểu mặc định đó.

Các properties có thể cấu hình danh sách groups cho từng mốc, ví dụ:

```properties
jakarta.persistence.validation.group.pre-persist=\
com.example.orders.validation.SubmissionChecks

jakarta.persistence.validation.group.pre-update=\
com.example.orders.validation.SubmissionChecks
```

Đây là ví dụ tên property theo Jakarta Persistence; phải cấu hình theo cách bootstrap/provider đang sử dụng và **chỉ đặt groups phù hợp toàn persistence unit**. Không nên áp `SubmissionChecks` cho mọi entity update nếu phần lớn cập nhật thuộc trạng thái DRAFT.

### 10.3. Không dựa vào automatic validation để kiểm tra mọi graph đang nằm trong DB

JPA/Bean Validation tích hợp có cơ chế quyết định thuộc tính nào được traverse, đặc biệt với lazy associations. Trên một managed entity đã được nạp, một collection `LAZY` chưa khởi tạo không nhất thiết được đi qua và validate toàn bộ theo cách người dùng tưởng tượng.

Nếu một nghiệp vụ yêu cầu chắc chắn xác minh **toàn bộ các lines của order**, hãy chủ động tải đúng dữ liệu và gọi một domain validator thích hợp trong transaction, thay vì giả định automatic flush validation sẽ duyệt mọi quan hệ tùy ý.

## 11. Validation groups theo trạng thái DRAFT và SUBMITTED

Không phải một entity luôn phải đạt cùng bộ ràng buộc trong mọi trạng thái.

Ví dụ:

- Order ở `DRAFT` có thể chưa có lines.
- Order ở `SUBMITTED` bắt buộc có ít nhất một line.
- Một order draft có thể chưa có shipping address, nhưng submit bắt buộc phải có.

Nếu đặt:

```java
@NotEmpty
private List<OrderLine> lines;
```

trên mọi order và để Default group kiểm tra khi persist, điều đó có thể **cấm cả DRAFT rỗng**, trái business contract.

### 11.1. Định nghĩa group dùng khi submit

```java
package com.example.orders.validation;

import jakarta.validation.groups.Default;

public interface SubmissionChecks extends Default {
}
```

Group kế thừa `Default` trong ví dụ để những Default constraints cơ bản cũng được xét khi validate `SubmissionChecks`.

### 11.2. Gắn constraint theo group

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;

@NotEmpty(
    groups = SubmissionChecks.class,
    message = "Submitted order needs at least one line"
)
@Valid
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Với code đầy đủ ở trên, thêm annotation này tại field `lines` trong `PurchaseOrder` và giữ các JPA mapping flags đã chọn.

### 11.3. Explicit validate khi submit

```java
Set<ConstraintViolation<PurchaseOrder>> errors =
    validator.validate(order, SubmissionChecks.class);

if (!errors.isEmpty()) {
    throw new ConstraintViolationException(errors);
}

order.submit();
```

Trong thiết kế thực tế, `order.submit()` có thể được gọi **trước** validation để xác lập trạng thái `SUBMITTED`, rồi validate group theo trạng thái đích trong cùng service trước flush.

Một trình tự rõ hơn:

```text
Construct DRAFT graph
    |
Check domain transition rules
    |
order.submit()
    |
validator.validate(order, SubmissionChecks.class)
    |
persist/flush/commit
```

Không chỉ đặt constraint theo `SubmissionChecks` rồi giả định JPA automatic validation ở `Default` luôn chạy group này.

### 11.4. Không biến group thành workflow engine

Nếu có hàng chục trạng thái và nhóm ràng buộc chồng chéo, group model có thể trở nên khó hiểu. Những chuyển trạng thái phức tạp nên được đặt trong domain methods/services, Bean Validation hỗ trợ các field/rule checks đơn giản.

## 12. Class-level constraint cho bất biến nhiều thuộc tính

Field-level annotations phù hợp ràng buộc độc lập. Nhưng một số quy tắc cần so sánh **nhiều fields**:

> Nếu Order đã SUBMITTED thì lines phải không rỗng, mỗi line phải trỏ về đúng order, và không được có hai lines cùng Product.

Có thể dùng **class-level custom constraint**.

### 12.1. Annotation @ConsistentOrderGraph

```java
package com.example.orders.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ConsistentOrderGraphValidator.class)
public @interface ConsistentOrderGraph {

    String message() default
        "Order graph is not structurally consistent";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

### 12.2. ConstraintValidator

```java
package com.example.orders.validation;

import com.example.orders.domain.OrderLine;
import com.example.orders.domain.OrderStatus;
import com.example.orders.domain.PurchaseOrder;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.util.HashSet;
import java.util.Set;

public class ConsistentOrderGraphValidator
        implements ConstraintValidator<
            ConsistentOrderGraph, PurchaseOrder> {

    @Override
    public boolean isValid(
            PurchaseOrder order,
            ConstraintValidatorContext context) {

        if (order == null) {
            // Null root được kiểm tra riêng bằng @NotNull.
            return true;
        }

        if (order.getLines() == null) {
            return false;
        }

        if (order.getStatus() == OrderStatus.SUBMITTED
                && order.getLines().isEmpty()) {
            return false;
        }

        Set<Long> products = new HashSet<>();

        for (OrderLine line : order.getLines()) {
            if (line == null || line.getOrder() != order) {
                return false;
            }

            if (line.getProduct() == null
                    || line.getProduct().getId() == null) {
                return false;
            }

            if (!products.add(
                    line.getProduct().getId())) {
                return false;
            }
        }

        return true;
    }
}
```

Gắn lên PurchaseOrder:

```java
@Entity
@ConsistentOrderGraph
public class PurchaseOrder {
    // ...
}
```

### 12.3. Giới hạn của validator này

Validator kiểm tra **graph đã có trong memory**. Nó không xác nhận:

- Product ID đang tồn tại trong database.
- Product vẫn active ở thời điểm commit.
- Cùng product/tenant hợp lệ.
- Một writer khác không insert duplicate trong transaction cạnh tranh.
- Collection lazy chưa được load có dữ liệu đầy đủ hay không.

Nếu validator được gọi trên entity managed có collection LAZY chưa khởi tạo, việc duyệt collection có thể kích hoạt SQL/N+1 hoặc tác động performance đáng kể. Nên gọi validator này **chủ đích trên aggregate đã được nạp đúng phạm vi**, thay vì mặc định cho mọi update bất kể use case.

### 12.4. Tránh database query trong ConstraintValidator

Không nên tiêm EntityManager vào custom validator rồi gọi SELECT cho từng line một cách ngầm định. Điều đó:

- Có thể tạo N+1.
- Có thể bị gọi ngoài transaction mong muốn.
- Phụ thuộc lifecycle/traversal của validator.
- Không loại trừ race giữa SELECT và commit.
- Gây khó dự đoán khi validation được framework kích hoạt tự động.

Các kiểm tra liên quan database nên được đặt ở transactional application service/domain repository với fetch plan rõ.

### 12.5. Dùng context để chỉ ra đường dẫn lỗi

Nếu cần cung cấp lỗi chi tiết ở trường `lines`:

```java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "Order lines must be consistent"
    )
    .addPropertyNode("lines")
    .addConstraintViolation();

return false;
```

Đây là cách tùy biến violation path trong Jakarta Validation; có thể thực hiện khi validator phát hiện rule failure.

## 13. Những chu trình tham chiếu trong graph

JPA quan hệ hai chiều tạo chu trình:

```text
Order -> lines -> OrderLine -> order -> Order -> ...
```

Nếu tự viết hàm duyệt tất cả fields recursively mà không có quy tắc dừng:

```java
validate(order.getLines());
validate(line.getOrder());
validate(order.getLines());
...
```

có thể gặp infinite recursion hoặc `StackOverflowError`.

### 13.1. Bean Validation có cơ chế xử lý object graph

Jakarta Bean Validation có semantics cascade validation và tránh vòng lặp tham chiếu vô hạn trong một lượt validation; không nên tự thay thế bằng một hàm reflection đệ quy ngây thơ.

### 13.2. Thiết kế hướng từ aggregate root xuống children

Với Order:

```text
Validate PurchaseOrder root
    |
    +-- scalar constraints
    |
    +-- @Valid lines
           |
           +-- OrderLine constraints
```

Không tự gắn `@Valid` lên mọi chiều của mọi quan hệ.

Ví dụ nên tránh nếu không có nhu cầu rõ:

```java
@Valid
@ManyToOne
private PurchaseOrder order;
```

trong OrderLine, đồng thời PurchaseOrder đã có `@Valid` trên lines. Mặc dù Bean Validation có cơ chế tránh cycle, việc cấu hình tràn lan vẫn có thể gây traversal phức tạp và tăng chi phí.

### 13.3. Đường dẫn traversal là một quyết định kiến trúc

Nếu Product là aggregate riêng, OrderLine thường chỉ cần:

```java
@NotNull
@ManyToOne
private Product product;
```

Không tự cascade validate toàn bộ Product và những associations của Product mỗi lần Order được validate.

Product eligibility (tenant/active/price) là một **application/domain check chủ đích**, không phải một cuộc duyệt graph không giới hạn.

## 14. Object graph chứa entity transient, managed, detached

Trạng thái JPA của từng object trong graph ảnh hưởng khả năng lưu.

| Trạng thái | Đặc điểm | Rủi ro khi lưu graph |
| --- | --- | --- |
| **Transient/new** | Chưa được quản lý, chưa có row | Thiếu cascade PERSIST, FK null, không có ID |
| **Managed** | Được quản lý trong persistence context | Dirty changes/flush, lazy relationships, version |
| **Detached** | Từng persistent nhưng không còn managed | `merge` copy state cũ/thiếu fields, optimistic conflicts |
| **Removed** | Đã được đánh dấu xóa trong context | Không phù hợp khi dùng lại như reference hợp lệ |

### 14.1. New child và cascade persist

`PurchaseOrder` mới có `OrderLine` mới. Nếu `@OneToMany(cascade=PERSIST)`, khi persist order, JPA có thể lan truyền persist tới lines.

Nếu không cấu hình cascade, phải persist children có chủ đích, đúng ownership/transaction; đừng trông chờ `@Valid` tự thực hiện việc đó.

### 14.2. Reference đến Product đã tồn tại

OrderLine nên tham chiếu một `Product` đã có và thuộc domain phù hợp. Một cách lấy Product:

```java
Product product = em.find(Product.class, productId);

if (product == null) {
    throw new IllegalArgumentException(
        "Product not found"
    );
}
```

Cách này cho phép đọc `active`, `tenantId`, `unitPrice` để xác thực.

### 14.3. Không nhầm getReference với xác minh tồn tại

```java
Product product =
    em.getReference(Product.class, productId);
```

có thể trả reference/proxy mà **không truy vấn database ngay**. Nó không phải bảo đảm row chắc chắn tồn tại, và truy cập data sau đó có thể ném `EntityNotFoundException` nếu row không có.

Nếu nghiệp vụ cần “Product phải tồn tại và active” trước khi tạo OrderLine, thường phải tải/xác minh dữ liệu, đồng thời vẫn giữ FK/transaction bảo vệ khi commit.

### 14.4. Detached graph và merge không phải PATCH

Nếu client gửi lại một `PurchaseOrder` detached với `lines` rỗng vì UI không truyền children, rồi gọi:

```java
em.merge(detachedOrder);
```

với `orphanRemoval = true`, việc copy graph state có thể có tác động xóa/orphan các lines đang tồn tại, tùy state/mapping và merge behavior.

**Không coi một payload thiếu collection là ý định “giữ nguyên collection” nếu tự động merge toàn bộ entity graph.** Dùng DTO/commands tường minh để thay đổi đúng trường/quan hệ.

## 15. Quan hệ sở hữu và orphanRemoval

Ở ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Khi một line tồn tại đã bị gỡ khỏi quan hệ sở hữu, JPA có thể xóa row child tương ứng theo `orphanRemoval` khi flush.

### 15.1. removeLine nên duy trì hai phía

```java
public void removeLine(OrderLine line) {
    requireDraft();

    if (lines.remove(line)) {
        line.detachFromOrder();
    }
}
```

Không chỉ gọi `lines.clear()` từ controller mà không hiểu tác động xóa dữ liệu.

### 15.2. Không chuyển orphan sang parent khác một cách tùy tiện

Giả sử line đã thuộc Order A và bị remove với orphanRemoval. Nếu ngay sau đó gắn cùng line vào Order B, lifecycle orphan removal có thể dẫn tới behavior khó dự đoán hoặc không phù hợp semantics ownership.

Nếu nghiệp vụ muốn **chuyển dòng hàng** giữa orders, cần thiết kế operation riêng, quản lý entity lifecycle/ownership một cách rõ ràng; nhiều trường hợp tạo child mới và xóa child cũ dễ kiểm soát hơn.

### 15.3. Validation không tự xử lý orphan lifecycle

`@NotNull` trên `OrderLine.order` không làm JPA biết “line bị bỏ khỏi List thì cần DELETE”. Đó là công việc của ownership, `orphanRemoval` và lifecycle operations.

### 15.4. orphanRemoval không thay thế authorization

Một người dùng không có quyền xóa line vẫn có thể kích hoạt logic nếu ứng dụng cho phép chỉnh graph tùy tiện. Quyền thao tác phải được kiểm tra ở service trước khi gọi `removeLine()`.

## 16. Tránh Product trùng trong cùng Order

Giả sử input:

```json
{
  "items": [
    {"productId": 101, "quantity": 2},
    {"productId": 101, "quantity": 3}
  ]
}
```

Có hai hướng nghiệp vụ hợp lệ:

- **Từ chối duplicate**.
- **Gộp thành một OrderLine với quantity=5**.

Bài ví dụ chọn **từ chối**.

### 16.1. Kiểm tra ở DTO

```java
Set<Long> seen = new HashSet<>();

for (CreateOrderRequest.LineRequest item :
        request.items()) {

    if (!seen.add(item.productId())) {
        throw new IllegalArgumentException(
            "Duplicate productId: " + item.productId()
        );
    }
}
```

Cách này phát hiện lỗi sớm trước khi load Product.

### 16.2. Kiểm tra ở aggregate

`PurchaseOrder.addLine()` tiếp tục kiểm tra duplicate, kể cả khi caller không đến từ HTTP API.

**Không chỉ dựa vào DTO validator**, vì entity còn có thể được tạo qua batch import, message consumer hoặc unit tests.

### 16.3. Unique constraint ở database

Mapping:

```java
@Table(
    name = "order_lines",
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"order_id", "product_id"}
    )
)
```

DDL tương ứng:

```sql
ALTER TABLE order_lines
ADD CONSTRAINT uq_order_product
UNIQUE (order_id, product_id);
```

Nếu hai writers cạnh tranh hoặc đường ghi ngoài JPA bỏ qua validation Java, unique constraint vẫn ngăn hai rows cùng `(order_id, product_id)`.

### 16.4. Vì sao Java check không đủ dưới concurrency?

Hai transactions có thể cùng kiểm tra “chưa có Product#101 trong Order#500”, rồi cả hai insert. Không transaction nào nhìn thấy row chưa commit của bên kia ở thời điểm check.

Unique constraint hoặc locking/transaction isolation thích hợp mới có thể bảo vệ invariant trước các writers đồng thời.

## 17. Kiểm tra tenant, ownership và authorization

Một object reference không null chưa chắc **được phép tham chiếu**.

Ví dụ:

```text
Order.tenantId = "tenant-A"
Customer#501.tenantId = "tenant-A"
Product#101.tenantId = "tenant-B"
```

Nếu chỉ validate `@NotNull Product`, graph vẫn có thể được lưu trong khi vi phạm ranh giới tenant.

### 17.1. Check domain ở service

```java
if (!tenantId.equals(customer.getTenantId())) {
    throw new IllegalArgumentException(
        "Customer belongs to another tenant"
    );
}

if (!tenantId.equals(product.getTenantId())) {
    throw new IllegalArgumentException(
        "Product belongs to another tenant"
    );
}
```

### 17.2. Đừng tin tenantId từ HTTP body một cách mặc định

Tenant của request nên được xác định từ authentication/authorization context đáng tin. Nếu client tự gửi `tenantId`, application phải đối chiếu với quyền của caller.

### 17.3. Database FK không luôn bảo vệ cross-tenant

FK chỉ trên `product_id` có thể cho phép một order tenant-A tham chiếu Product tenant-B, trừ khi schema có invariant tenant tương ứng (chẳng hạn composite FK theo tenant+ID hoặc cơ chế DB isolation khác).

Không suy “có FK nên mọi quan hệ nghiệp vụ đều hợp lệ”.

### 17.4. Listener không phải authorization boundary

Không nên đặt toàn bộ kiểm tra quyền người dùng trong `@PrePersist`. Callback có thể chạy trong batch job không có HTTP user context hoặc ở thời điểm khác; authorization thuộc application/service boundary.

## 18. Chọn dữ liệu và kiểm tra trong transaction

Một CreateOrder service không nên:

1. Query Product ngoài transaction.
2. Chờ lâu.
3. Tạo và lưu Order ở một transaction khác.
4. Khẳng định Product vẫn active và giá chưa đổi.

Một số điều kiện nghiệp vụ phụ thuộc **thời điểm** và cần được đánh giá trong transaction phù hợp.

### 18.1. Ví dụ service với Spring

```java
package com.example.orders.application;

import com.example.orders.api.CreateOrderRequest;
import com.example.orders.domain.*;
import jakarta.persistence.*;
import jakarta.validation.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

@Service
public class OrderCreationService {

    @PersistenceContext
    private EntityManager em;

    private final Validator validator;
    private final Clock clock;

    public OrderCreationService(
            Validator validator,
            Clock clock) {
        this.validator = validator;
        this.clock = clock;
    }

    @Transactional
    public Long create(
            String trustedTenantId,
            CreateOrderRequest request) {

        requireValidRequest(request);

        Customer customer =
            em.find(Customer.class, request.customerId());

        if (customer == null ||
                !customer.isActive() ||
                !trustedTenantId.equals(customer.getTenantId())) {
            throw new IllegalArgumentException(
                "Customer is not eligible"
            );
        }

        PurchaseOrder order = new PurchaseOrder(
            trustedTenantId,
            customer,
            Instant.now(clock)
        );

        Set<Long> productIds = new HashSet<>();

        for (CreateOrderRequest.LineRequest item :
                request.items()) {

            if (!productIds.add(item.productId())) {
                throw new IllegalArgumentException(
                    "Duplicate product: " + item.productId()
                );
            }

            Product product =
                em.find(Product.class, item.productId());

            if (product == null ||
                    !product.isActive() ||
                    !trustedTenantId.equals(
                        product.getTenantId())) {
                throw new IllegalArgumentException(
                    "Product is not eligible"
                );
            }

            // Giá snapshot lấy từ server-side Product.
            order.addLine(product, item.quantity());
        }

        // Business transition phải áp luật hiện hành.
        order.submit();

        Set<ConstraintViolation<PurchaseOrder>> errors =
            validator.validate(order);

        if (!errors.isEmpty()) {
            throw new ConstraintViolationException(errors);
        }

        em.persist(order);

        // Giúp phát hiện SQL/constraints trước khi trả ID;
        // commit vẫn có thể thất bại khi kết thúc method.
        em.flush();

        return order.getId();
    }

    private void requireValidRequest(
            CreateOrderRequest request) {

        if (request == null) {
            throw new IllegalArgumentException("request");
        }

        Set<ConstraintViolation<CreateOrderRequest>> errors =
            validator.validate(request);

        if (!errors.isEmpty()) {
            throw new ConstraintViolationException(errors);
        }
    }
}
```

**Giả định:** ứng dụng cung cấp một Spring bean `Clock`, `Validator` được tích hợp, và service được gọi thông qua transaction proxy. Các entities/DTO đã được định nghĩa ở những đoạn trước.

### 18.2. Điều service này kiểm soát

- DTO được validate trước khi truy xuất entity.
- Customer và Product phải có trong database.
- Tenant và active state được kiểm tra có chủ đích.
- Products trùng được từ chối.
- Giá lấy từ Product hiện hành trong persistence context, không từ body.
- Object graph được xây bằng aggregate methods.
- `submit()` xác nhận invariant của aggregate.
- Bean Validation kiểm tra fields và child graph.
- `persist(order)` cascade tới OrderLine nhờ mapping.
- `flush()` để database kiểm tra FK/unique/not-null/check sớm hơn commit.

### 18.3. Điều service chưa thể bảo đảm một mình

Một Product có thể bị thay đổi bởi transaction khác sau `em.find`. Tùy invariant, cần `@Version`, lock mode, isolation, FK/check constraint hoặc một protocol ghi nhất quán.

Ví dụ nếu nghiệp vụ cần **giá không được thay đổi trong khi đặt đơn**, chỉ đọc giá trong transaction chưa chắc đủ. Có thể dùng version/snapshot semantics rõ hơn hoặc lock Product theo policy phù hợp; chính sách giá cần xác định bởi sản phẩm.

### 18.4. Vì sao phải kiểm tra ở thời điểm nghiệp vụ?

Không nên chuyển một cách máy móc toàn bộ kiểm tra trong service sang `@PrePersist` của PurchaseOrder, vì callback không phải nơi tốt để query Customer/Products và điều phối transaction.

## 19. Đọc nhiều referenced entities: tránh N+1 query

Ví dụ service ở trên gọi:

```java
for (LineRequest line : request.items()) {
    Product p = em.find(Product.class, line.productId());
}
```

Với số lines nhỏ, cách này dễ hiểu. Nhưng một đơn có hàng trăm products có thể tạo nhiều SQL SELECT.

### 19.1. Lấy danh sách ID trước

```java
Set<Long> ids = request.items().stream()
    .map(CreateOrderRequest.LineRequest::productId)
    .collect(java.util.stream.Collectors.toSet());
```

Sau đó có thể query theo IDs:

```jpql
SELECT p
FROM Product p
WHERE p.id IN :ids
  AND p.tenantId = :tenantId
```

Và dựng Map theo ID để đối chiếu **đúng số sản phẩm được yêu cầu**:

```java
Map<Long, Product> byId = products.stream()
    .collect(Collectors.toMap(
        Product::getId,
        Function.identity()
    ));
```

Các imports `java.util.Map`, `java.util.function.Function` và `java.util.stream.Collectors` cần được thêm theo cấu trúc class thực tế.

### 19.2. Không suy tất cả IDs tồn tại vì query trả nonempty

Nếu request có 100 IDs nhưng query chỉ trả 99 products, có một ID không tồn tại/không thuộc tenant/filter.

Phải kiểm tra:

```java
if (byId.size() != ids.size()) {
    throw new IllegalArgumentException(
        "Some products are missing or not allowed"
    );
}
```

Sau đó mới dùng từng Product để tạo line.

### 19.3. Query IN không tự giữ thứ tự request

Nếu thứ tự lines theo request có ý nghĩa hiển thị, hãy **duyệt request.items()** và lấy Product từ Map, thay vì dựa vào thứ tự SQL trả khi dùng `IN`.

### 19.4. Batching là tối ưu, không phải thay validation

Một query lấy 99/100 products vẫn phải báo thiếu/không được phép. Tối ưu SQL không được làm mất kiểm tra cấu trúc graph.

## 20. Quan hệ và giá trị suy ra: totalAmount

Một PurchaseOrder thường có tổng tiền:

\[
\text{totalAmount} = \sum_{line \in lines} line.quantity \times line.unitPrice
\]

Nếu entity lưu một field `totalAmount`, phải giữ nó nhất quán với children.

### 20.1. Tính bằng BigDecimal

```java
public BigDecimal calculateTotal() {
    return lines.stream()
        .map(line -> line.getUnitPrice().multiply(
            BigDecimal.valueOf(line.getQuantity())
        ))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
}
```

Dùng `BigDecimal` cho tiền tệ thay vì `double` để tránh sai số floating-point trong các phép tính cần độ chính xác thập phân.

### 20.2. Nếu lưu totalAmount trong database

Có thể cần:

- Recalculate khi add/remove/update lines.
- Constraint/domain check trước submit.
- Quy tắc rounding/currency scale.
- Đảm bảo các đường bulk SQL và external writers không bỏ qua maintenance.
- Versioning/concurrency cho aggregate nếu nhiều transactions sửa lines.

Không đơn giản tin giá trị total do client gửi hoặc do một callback `@PrePersist` tính từ collection mà không hiểu lifecycle/cascade.

### 20.3. @AssertTrue trên một getter không phải giải pháp toàn năng

```java
@AssertTrue
public boolean isTotalConsistent() {
    return storedTotal.compareTo(calculateTotal()) == 0;
}
```

Có thể dùng cho invariant cục bộ khi toàn bộ lines đã được load và graph đủ dữ liệu. Nhưng nếu association LAZY chưa khởi tạo, getter có thể gây query hoặc sai giả định dữ liệu. Không nên dùng một validator luôn traverse rất lớn trên mọi persistence update.

## 21. Kiểm tra ở thời điểm cập nhật graph đang managed

Không chỉ tạo mới mới cần validation. Một order đã tồn tại có thể được sửa:

- Thay quantity.
- Thêm line.
- Xóa line.
- Chuyển status.
- Đổi Customer nếu nghiệp vụ cho phép.

### 21.1. Load aggregate đúng phạm vi

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

Query này có thể dùng cho **một order cụ thể** để nạp lines trước khi kiểm tra/đổi graph. Không tự ghép collection fetch join với pagination của danh sách orders.

### 21.2. Không cho caller sửa List tùy tiện

```java
public List<OrderLine> getLines() {
    return Collections.unmodifiableList(lines);
}
```

Giới hạn public mutation giúp buộc các thay đổi đi qua `addLine/removeLine`, nơi bảo vệ hai chiều và quy tắc trạng thái.

### 21.3. EntityManager vẫn có quyền quản lý collection

Getter trả unmodifiable view chỉ là **API encapsulation của domain model**. JPA provider quản lý field persistent qua access strategy đã chọn. Nó không đồng nghĩa collection bất biến ở database; trong entity vẫn có methods thay đổi đúng cách.

### 21.4. Kiểm tra trước khi xóa child

Nếu `orphanRemoval=true`, remove line có thể dẫn tới DELETE. Vì vậy service phải:

- Kiểm tra order còn DRAFT.
- Xác thực caller có quyền thay đổi.
- Kiểm tra line thật sự thuộc order đó.
- Đảm bảo thao tác xóa không làm vi phạm rule của trạng thái hiện tại.

Một câu `order.getLines().remove(line)` vô điều kiện không đủ.

## 22. Validation với merge và detached graphs

Trong nhiều ứng dụng, HTTP/serialization làm graph trở thành detached, sau đó code gọi `merge`.

### 22.1. merge copy state, không phải “kiểm tra rồi update phần được gửi”

```java
PurchaseOrder managed =
    em.merge(detachedOrder);
```

`merge` trả một managed instance theo JPA semantics; object detached ban đầu không tự trở thành managed. State được copy/merge có thể làm thay đổi quan hệ tùy cascade và graph được truyền.

### 22.2. Partial graph nguy hiểm

Nếu DTO chỉ sửa `reference` nhưng được chuyển thành detached PurchaseOrder với `lines=[]` và gọi merge, có thể khiến hệ thống hiểu đó là thay đổi collection.

Dùng lệnh rõ:

```java
public record ChangeOrderReference(
    Long orderId,
    Long expectedVersion,
    String newReference
) {}
```

Rồi:

```text
@Transactional:
  find managed order
  check authorization + expectedVersion
  changeReference()
  validate transition/aggregate
  flush/commit
```

Không đưa toàn bộ graph thiếu fields vào merge nếu muốn PATCH một field.

### 22.3. @Version không kiểm tra mọi business invariant

`@Version` giúp phát hiện stale updates của entity mang version. Nếu invariant liên quan cả set các children hoặc nhiều bảng, phải thiết kế transaction/locking phù hợp. Không suy có version trên root thì tất cả concurrent inserts vào bảng con luôn bị phát hiện, nếu không có cập nhật version root/constraint đúng.

## 23. Kiểm tra child có thuộc đúng parent không?

Một API nhận `orderId` và `lineId` để xóa line.

Sai:

```java
OrderLine line = em.find(OrderLine.class, lineId);
em.remove(line);
```

nếu không xác nhận line thuộc order đang được thao tác và user có quyền trên order.

### 23.1. Cách rõ ràng hơn

Trong transaction:

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

if (order == null) {
    throw new EntityNotFoundException();
}

// Load hoặc kiểm tra line trong graph của order.

OrderLine target = order.getLines().stream()
    .filter(line -> lineId.equals(line.getId()))
    .findFirst()
    .orElseThrow(() ->
        new IllegalArgumentException(
            "Line does not belong to this order"
        )
    );

order.removeLine(target);
```

Cần xác thực authorization trước khi thực hiện mutation.

### 23.2. Kiểm tra membership bằng query

Với graph rất lớn, có thể lấy child bằng query có cả parent ID:

```jpql
SELECT l
FROM OrderLine l
WHERE l.id = :lineId
  AND l.order.id = :orderId
```

Như vậy query thể hiện rõ quan hệ ownership mà client không được tự giả định.

### 23.3. Tránh dùng equals/hashCode sai

Nếu `OrderLine.equals()` dựa vào generated ID khi ID còn null, hai transient lines có thể bị xem là bằng nhau nếu implementation không cẩn thận.

Các helper kiểm tra graph cần có chiến lược entity equality phù hợp. Với ví dụ, List thao tác object references và không override equals; logic duplicate Product dùng Product ID đã được kiểm tra không null.

## 24. Database constraints là lớp bảo vệ cuối

Một schema minh họa:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    active BOOLEAN NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    version BIGINT,
    CONSTRAINT ck_product_price
        CHECK (unit_price >= 0)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    version BIGINT
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,
    CONSTRAINT ck_order_line_quantity CHECK (quantity >= 1),
    CONSTRAINT ck_order_line_price CHECK (unit_price >= 0),
    CONSTRAINT uq_order_product UNIQUE (order_id, product_id)
);

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);
```

DDL minh họa dùng cú pháp gần PostgreSQL. Schema production cần khớp database/dialect, migrations, index strategy và policy domain. Ví dụ không tự triển khai ràng buộc cross-tenant bằng composite FK.

### 24.1. Những gì DB kiểm tra tốt

- NOT NULL.
- FOREIGN KEY existence.
- UNIQUE combinations.
- CHECK constraint trên một row.
- Transaction atomicity.
- Một số invariants đặc thù qua constraint/index/triggers theo DBMS.

### 24.2. Những gì DB không tự biết từ mapping

- User có quyền thao tác không.
- Product có đang bán cho tenant đó theo domain rules không.
- Một thao tác chuyển trạng thái có được phép không.
- Client thực sự muốn thêm/xóa dòng nào.
- Giá snapshot được xác định theo thời điểm nào.

### 24.3. Check trước INSERT không loại trừ race

```text
T1: SELECT product -> exists
T2: DELETE product, COMMIT
T1: INSERT order_line referencing deleted product
```

T1 có thể thất bại ở FK, tùy transaction isolation/locks. Java validation sớm không bảo đảm dữ liệu vẫn hiện diện tới commit.

**Giữ FK và xử lý lỗi database**, đồng thời dùng isolation/locking khi nghiệp vụ yêu cầu.

## 25. Transaction và concurrency: “validate rồi lưu” chưa chắc atomic

Một transaction có thể kiểm tra điều kiện:

```text
T1: available = 10
T2: available = 10
T1: order requests 7
T2: order requests 7
```

Nếu hai transactions chỉ dựa vào validation “available >= 7” trước khi ghi, chúng có thể cùng chấp nhận giữ 7 dù tổng 14 > 10.

### 25.1. Các chiến lược bảo vệ invariant

Tùy nghiệp vụ:

- `@Version` để phát hiện stale updates.
- `PESSIMISTIC_WRITE` khi cần lock trước.
- Atomic conditional UPDATE với điều kiện tồn kho.
- Database constraint.
- Transaction isolation phù hợp.
- Aggregate root versioning.
- Queue/serialization theo resource key.

### 25.2. Ví dụ atomic conditional update

```sql
UPDATE inventory
SET available = available - :qty
WHERE product_id = :productId
  AND available >= :qty;
```

Sau statement, phải kiểm tra affected row count: 1 biểu thị điều kiện được thỏa và update đã thực thi, 0 biểu thị không thể giữ theo điều kiện đó hoặc row không tồn tại. Đây là SQL illustration, không phải query tự phát sinh từ Bean Validation.

### 25.3. Đừng query database từ custom Bean Validation cho mọi dòng

Một `@ValidProductAvailability` validator thực hiện một SELECT cho từng OrderLine không tự loại bỏ race và có thể gây N+1. Hãy đặt bước kiểm tra/giữ tồn kho tại service trong transaction với policy concurrency rõ.

### 25.4. @Version trên Order chưa đủ bảo vệ mọi Product

Nếu hai Orders mới khác nhau cùng tham chiếu Product#101, version của từng Order không tự phát hiện hai requests cùng tiêu thụ tồn kho của Product. Invariant thuộc resource Product/Inventory phải được bảo vệ ở nơi tương ứng.

## 26. Thời điểm gọi validation trong workflow

Một luồng nên tách:

```text
Phase A: Parse + validate request DTO
    |
Phase B: Resolve referenced entities
    |
Phase C: Build aggregate graph
    |
Phase D: Validate graph/domain rules
    |
Phase E: Persist/merge/remove
    |
Phase F: Flush + database constraints
    |
Phase G: Commit transaction
```

### 26.1. Những lỗi nên bắt sớm

- Field null/trống.
- Quantity âm/0.
- Trùng Product IDs trong request.
- Không có lines khi yêu cầu submit.
- Parent-child backlink bị sai.
- Tenant mismatch có thể xác định khi load entities.

### 26.2. Những lỗi có thể chỉ lộ ở flush/commit

- Foreign key bị xóa đồng thời.
- Unique constraint bị tranh chấp.
- Optimistic lock conflict.
- Transaction deadlock/timeout.
- Constraint bị trigger/procedure thay đổi.
- Database connection/commit failure.

**Đừng trả API success chỉ vì `validator.validate(...)` trả set rỗng.** Persistence vẫn phải commit thành công.

### 26.3. Flush không thay thế commit

```java
em.persist(order);
em.flush();
```

có thể giúp phát hiện nhiều lỗi SQL sớm, nhưng transaction vẫn có thể rollback hoặc fail ở commit. Khi dùng Spring `@Transactional`, commit thường xảy ra sau khi thân service method kết thúc.

## 27. Xử lý lỗi validation rõ ràng

Một API có thể phân biệt:

| Lỗi | Nguồn | HTTP xử lý thường gặp |
| --- | --- | --- |
| Dữ liệu request thiếu/sai format | DTO validation | 400 |
| Graph không hợp lệ về field/domain | Validation/domain exception | 400 hoặc 422 theo contract |
| Customer/Product không tồn tại | Service/reference lookup | 404 hoặc lỗi domain phù hợp |
| Không có quyền tham chiếu một resource | Authorization | 403/404 theo chính sách bảo mật |
| Trùng product line | Domain hoặc DB unique | 409 hoặc 400 tùy contract |
| Version conflict | JPA optimistic locking | 409 |
| Constraint từ DB | Persistence exception | Phân loại; không expose raw SQL |
| Deadlock/lock timeout | DB/provider | Retry có kiểm soát hoặc lỗi tạm thời |

Đây là **quy ước API thường dùng**, không phải JPA tự quyết định HTTP status.

### 27.1. Đọc đường dẫn field từ ConstraintViolation

```java
for (ConstraintViolation<?> violation : errors) {
    String path =
        violation.getPropertyPath().toString();

    String message = violation.getMessage();

    // Chuyển thành lỗi API có kiểm soát.
}
```

Ví dụ path:

```text
items[1].quantity
lines[2].product
reference
```

Tên path thực tế phụ thuộc validation target/container element constraints.

### 27.2. Không trả stack trace hoặc SQL nguyên bản cho client

DB constraint errors có thể chứa tên bảng, cột, SQL và dữ liệu nhạy cảm. Chuẩn hóa thành thông báo có chủ đích; ghi log nội bộ phù hợp với yêu cầu bảo mật.

### 27.3. Không swallow exception trong transaction

Sai:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    log.warn("Will continue");
}
tx.commit();
```

Sau lỗi persistence, transaction có thể đã rollback-only/không thể commit. Phải rollback theo transaction policy thay vì tiếp tục với object graph có state không chắc chắn.

## 28. Validation trước remove khác validation trước persist

Một graph khi tạo có thể cần đủ fields, nhưng khi xóa có thể cần quy tắc khác:

- Không xóa Order đã thanh toán.
- Không xóa Product còn đang được tham chiếu nếu nghiệp vụ cấm.
- Không xóa Customer đang có đơn đang xử lý.
- Khi remove Order, child entities nào sẽ được xóa/còn giữ?

Đó là **business rules của operation**, không chỉ field constraints.

### 28.1. @PreRemove không phải nơi duy nhất kiểm tra quyền xóa

`@PreRemove` có thể chạy khi JPA xử lý remove, nhưng user authorization và những kiểm tra phụ thuộc nhiều aggregate nên được thực hiện ở service.

### 28.2. JPA cascade REMOVE khác orphanRemoval

- `CascadeType.REMOVE`: propagate `remove(parent)` đến children phù hợp.
- `orphanRemoval=true`: child rời relationship sở hữu có thể bị xóa.
- `@Valid`: validation traversal, không tự xóa.
- DB `ON DELETE CASCADE`: ràng buộc/tác động SQL ở database, không phải cùng một cơ chế với JPA cascade.

### 28.3. Không để validation mặc định cản trở xóa do trạng thái đã cũ

Một entity legacy có field sai constraint mới vẫn có thể cần được xóa. Validation groups/policies nên tính tới lifecycle operations, thay vì bắt buộc mọi pre-remove đi qua bộ kiểm tra dành cho create/submit.

## 29. Quan hệ to-one và to-many có đặc điểm kiểm tra khác nhau

### 29.1. @ManyToOne

Ví dụ OrderLine → Product:

- Reference không null.
- ID tồn tại.
- FK đúng.
- Tenant/ownership phù hợp.
- Không cascade REMOVE tới shared Product.
- Dữ liệu Product đủ mới cho rule nghiệp vụ.

### 29.2. @OneToOne

Ví dụ Order → ShippingAddressEntity:

- Có cần bắt buộc 1:1 không?
- Ai sở hữu FK?
- Unique constraint đã phản ánh uniqueness chưa?
- Đối tượng mới có được cascade persist không?
- Một Address có thể được gắn hai Orders không?
- Nếu optional, null có hợp lệ theo trạng thái không?

### 29.3. @OneToMany

Ví dụ Order → Lines:

- Collection có thể rỗng không?
- List có thể chứa null không?
- Duplicate theo business key được chấp nhận không?
- Mỗi child có backlink đúng parent không?
- Cascade persist/merge/remove có đúng ownership không?
- orphanRemoval có phù hợp không?
- Collection có quá lớn để validate toàn bộ trên mỗi update không?

### 29.4. @ManyToMany

Ví dụ Student ↔ Courses:

- Quan hệ có duplicate entries không?
- Join table có unique pair constraint không?
- Cả hai entity types có lifecycle độc lập không?
- Cascade REMOVE có thể gây xóa shared entity không?
- Quan hệ có metadata như enrolledAt, grade không? Nếu có, thường nên tạo **association entity** thay vì ManyToMany trực tiếp.

### 29.5. @Embedded và @ElementCollection

Value objects và element collections cũng là một phần cấu trúc aggregate:

- `@Embedded` ShippingAddress: zip/country/city có nhất quán?
- `@ElementCollection` tags: số lượng/duplicate hợp lệ?
- `@Valid` có cần traverse các embedded objects?
- Value object có được tạo bất biến và validate ở constructor/factory không?

Không giới hạn “object graph” chỉ ở các association giữa entity classes.

## 30. Trường hợp @Embedded: kiểm tra value object

Ví dụ ShippingAddress:

```java
@Embeddable
public class ShippingAddress {

    @NotBlank
    private String country;

    @NotBlank
    private String city;

    @NotBlank
    private String street;

    protected ShippingAddress() {}

    public ShippingAddress(
            String country,
            String city,
            String street) {

        if (country == null || country.isBlank()
                || city == null || city.isBlank()
                || street == null || street.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid shipping address"
            );
        }

        this.country = country;
        this.city = city;
        this.street = street;
    }
}
```

Trong Order:

```java
@Valid
@Embedded
private ShippingAddress shippingAddress;
```

Nếu ShippingAddress chỉ bắt buộc khi `SUBMITTED`, có thể dùng domain transition check hoặc class-level constraint; đừng đặt `@NotNull` ở Default group rồi làm cho draft không thể tồn tại nếu draft được phép thiếu địa chỉ.

### 30.1. @Embedded không phải entity con độc lập

Một embeddable không có identity/lifecycle riêng như `OrderLine` entity. Nó được lưu trong cấu trúc của owner theo mapping. Việc kiểm tra nội dung của nó thường phù hợp với validation từ aggregate root.

### 30.2. Đối tượng bất biến giúp giảm trạng thái lỗi

Nếu Address chỉ có thể được tạo qua constructor/factory xác minh dữ liệu, nhiều trạng thái không hợp lệ không thể tồn tại trong code application thông thường. Tuy vậy, JPA cần construction/mapping phù hợp và database data legacy vẫn có thể sai; Bean Validation/DB constraints vẫn hữu ích.

## 31. Tại sao không validate toàn bộ database graph mỗi lần save?

Một `PurchaseOrder` có thể tham chiếu:

```text
Order
  -> Customer
      -> all Orders
           -> all Lines
                -> Product
                    -> Categories
                         -> Products
```

Nếu gắn `@Valid` trên mọi association, một validation có thể trở thành phép duyệt graph rộng không cần thiết.

### 31.1. Xác định validation boundary

Với Order creation:

- Validate Order root.
- Validate OrderLines mới do Order sở hữu.
- Kiểm tra Customer/Product references bằng business queries có chủ đích.
- Không cascade validate toàn bộ Customer orders hoặc Product categories.

### 31.2. Tránh việc query lén trong validator

Nếu class-level constraint đọc `order.getCustomer().getOrders()` hoặc `product.getInventoryBalances()` mà các association LAZY, validation có thể tạo nhiều SQL phụ.

### 31.3. Giữ cost của validation đo được

Trong production, nên quan sát:

- Số field/objects được validate.
- Độ sâu object graph.
- Số SQL phát sinh khi validate.
- p95 latency của endpoint.
- Dung lượng heap khi xử lý collection lớn.
- Những validators có query hay external I/O.

Một graph validator đúng logic nhưng tải 50.000 associations mỗi lần cập nhật tên Order vẫn là thiết kế cần điều chỉnh.

## 32. Unit test và integration test nên chia tầng

### 32.1. Unit test cho domain methods

Có thể tạo transient Order/Product/Customer fixture rồi kiểm tra:

- `addLine` tạo child có parent đúng.
- Duplicate Product bị từ chối.
- Quantity 0 bị từ chối.
- Không thể submit Order rỗng.
- Không thể sửa lines sau submit.
- `removeLine` loại khỏi List và cập nhật owning side.
- Tenant validation logic của service/domain đúng với dữ liệu giả lập phù hợp.

Unit tests không cần database để kiểm tra những invariant thuần Java.

### 32.2. Unit test cho Bean Validation

Tạo `Validator` bằng implementation chuẩn đã chọn, validate Order graph có child quantity sai, rồi xác nhận violation phù hợp.

Không chỉ unit test method `new OrderLine(...)` nếu kỳ vọng tự động validation trong JPA; hai cơ chế khác nhau.

### 32.3. Integration test cho JPA mapping và DB constraints

Dùng provider và DBMS gần production:

1. Persist một Order với hai Lines.
2. Commit transaction.
3. Mở EntityManager mới.
4. Query Order/Lines.
5. Xác nhận `line.order.id == order.id`.
6. Xác nhận `order_id` và `product_id` đúng.
7. Thử insert duplicate `(order_id, product_id)` và xác nhận DB từ chối.
8. Thử Product reference không hợp lệ và xác nhận FK.
9. Thử remove Line với orphanRemoval, commit và xác minh row bị xóa.
10. Kiểm tra auto Bean Validation nếu dự án bật `validation-mode` tương ứng.

### 32.4. Integration test concurrency

Hai transactions đồng thời:

- Cùng thêm một Product vào một Order.
- Cùng reserve inventory Product.
- Một transaction xóa Product trong khi transaction khác tạo OrderLine.
- Một transaction update version trong khi transaction còn lại sửa Order.

Xác nhận constraint/locking/transaction cuối đúng, không chỉ “Validator báo pass”.

### 32.5. Một bảng test cases

| Test case | Kỳ vọng |
| --- | --- |
| DTO thiếu customerId | Request validation fail |
| DTO items rỗng | Fail nếu API tạo submitted order |
| Dòng quantity=0 | Validation/domain rejection |
| Product ID không tồn tại | Service reject và/hoặc DB FK bảo vệ |
| Product của tenant khác | Service reject |
| Product inactive | Service reject |
| Duplicate Product trong request | Reject hoặc merge theo policy |
| Child.order null khi graph cần đủ | Graph/domain validation fail |
| Child.order trỏ Order khác | Graph validator fail |
| Order DRAFT không lines | Hợp lệ nếu domain cho phép |
| Order SUBMITTED không lines | Domain/group validation fail |
| Orphan line bị remove | DB DELETE đúng theo lifecycle |
| Payload partial thiếu lines | Không vô tình xóa children |
| Two writers insert same Product line | Unique constraint ngăn duplicate |
| Update Order khi version cũ | Optimistic conflict đúng |
| Bulk UPDATE ngoài entity path | Có chiến lược audit/validation riêng |
| LAZY collection chưa load | Không giả định auto validation đã duyệt toàn graph |

### 32.6. Test phải xem kết quả sau commit

Một transaction có thể `flush()` thành công rồi commit thất bại vì nguyên nhân khác. Integration test nên xác nhận database state trong EntityManager/transaction mới sau khi transaction đã kết thúc.

## 33. Các lỗi phổ biến khi kiểm tra object graph

### Lỗi 1 — Chỉ dùng @NotNull rồi kết luận quan hệ hợp lệ

Reference khác null không có nghĩa row tồn tại, đúng tenant, active hoặc thuộc parent.

### Lỗi 2 — Nghĩ @Valid tự persist child

`@Valid` là validation cascade, không phải JPA `CascadeType.PERSIST`.

### Lỗi 3 — Nghĩ cascade=PERSIST tự validate child

Cascade lifecycle không thay thế explicit/cascaded Bean Validation.

### Lỗi 4 — Chỉ thêm child vào parent.lines

Owning side `line.order` có thể vẫn null và FK sai.

### Lỗi 5 — Chỉ sửa line.order

Inverse side collection có thể không nhất quán trong memory.

### Lỗi 6 — Cho controller sửa collection trực tiếp

Dễ phá invariant, orphanRemoval hoặc business state transition.

### Lỗi 7 — Cho rằng generated ID phải có trước persist

Transient graph có thể hợp lệ dù `@GeneratedValue` ID còn null.

### Lỗi 8 — Nhận giá và trạng thái từ client để tạo entity

Có thể dẫn tới mass assignment và sai rule giá/authorization.

### Lỗi 9 — getReference được dùng như phép kiểm tra tồn tại

Proxy/reference có thể không truy vấn DB ngay.

### Lỗi 10 — Không kiểm tra duplicates theo business key

`List` cho phép duplicates; JPA không tự hiểu Product chỉ được có một line.

### Lỗi 11 — Chỉ kiểm tra duplicate bằng SELECT

Hai transactions có thể cùng thấy chưa tồn tại. Cần unique constraint hoặc strategy concurrency.

### Lỗi 12 — Dùng @NotEmpty cho collection ở mọi trạng thái

Có thể làm DRAFT không hợp lệ dù nghiệp vụ cho phép draft rỗng.

### Lỗi 13 — Gắn @Valid trên mọi association hai chiều

Có thể gây traversal rộng, lazy loading và chi phí khó đo.

### Lỗi 14 — Custom validator query DB cho từng child

Dẫn tới N+1, phụ thuộc context và vẫn không ngăn race.

### Lỗi 15 — Không phân biệt Bean Validation exception với SQL constraint violation

Cần phân loại/chuẩn hóa lỗi từ các tầng khác nhau.

### Lỗi 16 — Dùng merge cho partial DTO

Thiếu collection field có thể bị hiểu là state muốn cập nhật/xóa children.

### Lỗi 17 — Cascade REMOVE từ OrderLine sang shared Product

Có thể xóa/tác động dữ liệu không thuộc aggregate.

### Lỗi 18 — Coi orphanRemoval là validation rule

Orphan removal điều khiển lifecycle xóa child, không xác định business permission.

### Lỗi 19 — Cho rằng validation pass là commit thành công

SQL/FK/unique/concurrency/transaction vẫn có thể thất bại.

### Lỗi 20 — Bỏ qua database constraints vì đã validate Java

External writers và concurrent transactions có thể vượt qua phép kiểm tra của ứng dụng.

### Lỗi 21 — Đặt tất cả business rules trong @PrePersist

Callback không phù hợp để query nhiều aggregate, thực hiện network I/O hoặc điều phối transactions.

### Lỗi 22 — Chỉ kiểm tra object fields, bỏ tenant/ownership

Có thể tạo cross-tenant references hoặc IDOR.

### Lỗi 23 — Không xử lý dirty L1 sau bulk update

JPQL bulk DML không tự đồng bộ managed entities đã load giống entity-level updates.

### Lỗi 24 — Không xác định semantics của Product price snapshot

Nếu client tự điền unitPrice hoặc Product thay giá giữa các bước, tổng tiền có thể không đúng rule business.

### Lỗi 25 — Chỉ unit test object graph, không kiểm thử mapping

Java graph đúng chưa chắc FK, cascade, orphanRemoval, uniqueness và flush/commit hoạt động như dự đoán.

## 34. Bài tập thực hành

### Bài 1 — Chọn tầng validation

Request có `quantity = -2`.

**Đáp án:** DTO `@Min(1)` và domain constructor/method nên chặn sớm; DB CHECK tiếp tục bảo vệ dữ liệu nếu có writer khác.

### Bài 2 — Product tồn tại?

`productId != null` nhưng Product đã bị xóa.

**Đáp án:** `@NotNull` trên ID không kiểm tra DB. Service cần resolve Product theo use case; DB FK là lớp bảo vệ cuối.

### Bài 3 — Sai quan hệ hai chiều

`order.lines.contains(line) == true` nhưng `line.order == null`.

**Đáp án:** Graph không nhất quán; dùng helper cập nhật cả hai phía. Với `mappedBy="order"`, phía `line.order` sở hữu FK.

### Bài 4 — Chỉ có @Valid

Order có lines mới, mapping `@OneToMany` không cascade persist.

**Đáp án:** `@Valid` không tự insert children. Cần cấu hình cascade phù hợp hoặc persist từng child có chủ đích.

### Bài 5 — Chỉ có CascadeType.PERSIST

Order có child quantity=0, không có `@Valid` trên đường traversal.

**Đáp án:** Cascade persist không đảm bảo explicit root Bean Validation tự kiểm tra child. Constructor/domain rules, `@Valid` hoặc DB CHECK phải bảo vệ.

### Bài 6 — Trùng Product

Order có hai lines cùng `productId=101` trong khi rule chỉ cho một.

**Đáp án:** Kiểm tra bằng Set ở request và aggregate, đồng thời UNIQUE(order_id, product_id) ở DB.

### Bài 7 — Draft rỗng

Order DRAFT không lines có được persist không?

**Đáp án:** Phụ thuộc domain. Nếu DRAFT được phép rỗng, không đặt Default `@NotEmpty` cấm mọi insert; dùng group hoặc rule khi submit.

### Bài 8 — Submitted rỗng

Order ở trạng thái SUBMITTED nhưng lines rỗng.

**Đáp án:** Domain transition hoặc class-level/group validation phải từ chối. DB constraints đơn hàng khó biểu đạt yêu cầu “ít nhất một row con” chỉ bằng CHECK trên parent.

### Bài 9 — Tenant mismatch

Order tenant A tham chiếu Product tenant B.

**Đáp án:** Service/domain phải kiểm tra; DB cần schema phù hợp nếu muốn bảo vệ cả cross-tenant reference ở constraint level.

### Bài 10 — getReference

`em.getReference(Product.class, 999L)` trả object.

**Đáp án:** Không chứng minh Product#999 tồn tại. Cần kiểm tra theo yêu cầu và FK.

### Bài 11 — Partial update

Payload chỉ chứa `reference`, hệ thống merge một detached Order với `lines=[]`.

**Đáp án:** Nguy cơ làm mất/đổi collection. Load managed Order và áp field change tường minh.

### Bài 12 — Orphan removal

User xóa một dòng khi Order đã SUBMITTED.

**Đáp án:** Phải kiểm tra business transition/authorization trước khi remove; orphanRemoval không tự biết thao tác xóa bị cấm.

### Bài 13 — Race với uniqueness

Hai requests cùng thêm Product#101 vào Order#500.

**Đáp án:** Java validation không đủ dưới concurrency. UNIQUE constraint và transaction/version/locking strategy bảo vệ cuối.

### Bài 14 — LAZY graph

Một graph validator gọi `order.getLines()` trên 1.000 orders LAZY chưa khởi tạo.

**Đáp án:** Có nguy cơ N+1/hiệu năng; cần giới hạn validation boundary và fetch plan đúng use case.

### Bài 15 — Giá snapshot

Client truyền unitPrice thấp hơn giá Product đang bán.

**Đáp án:** Không tin giá client. Service xác định giá theo chính sách domain và lưu snapshot đã được xác nhận.

### Bài 16 — Bulk update

Một JPQL bulk UPDATE thay status của 1.000 Orders.

**Đáp án:** Không mặc định lifecycle callbacks/Bean Validation của từng managed entity chạy. Phải thiết kế validation/audit/transaction và persistence context/cache riêng.

### Bài 17 — Transaction fail sau validation

`validator.validate(order)` trả set rỗng, `em.flush()` gặp FK violation.

**Đáp án:** Validation Java không thay DB constraints. Rollback và trả lỗi phù hợp, không coi order đã lưu.

### Bài 18 — @Embedded

ShippingAddress có city rỗng.

**Đáp án:** Có thể validate bằng `@NotBlank` trên embedded object, `@Valid` khi cần cascade, constructor/factory và DB constraints theo mapping.

## 35. Câu hỏi tự kiểm tra

**1. Object graph validation khác field validation ra sao?**

Graph validation kiểm tra cả quan hệ giữa objects, child collections và invariant của aggregate, không chỉ từng giá trị đơn lẻ.

**2. @NotNull trên @ManyToOne có bảo đảm row tham chiếu tồn tại không?**

Không. Nó kiểm tra reference không null; FK/service/database đảm nhận các phần khác.

**3. optional=false và nullable=false khác @NotNull thế nào?**

Chúng thuộc JPA relationship/schema metadata; `@NotNull` thuộc Bean Validation.

**4. @Valid có thực hiện SQL INSERT child không?**

Không.

**5. CascadeType.PERSIST có tự sửa hai phía quan hệ không?**

Không.

**6. Trong bidirectional OneToMany/ManyToOne, phía nào thường sở hữu FK?**

Phía `@ManyToOne` có `@JoinColumn`, trong ví dụ là `OrderLine.order`.

**7. Vì sao nên có addLine/removeLine helpers?**

Để bảo đảm parent/child references và business invariants luôn được thay đổi nhất quán.

**8. Khi nào @NotEmpty trên lines có thể sai?**

Khi DRAFT order được phép không có line nhưng constraint mặc định cấm mọi trường hợp.

**9. Tại sao cần validation groups?**

Để chọn bộ constraints phù hợp với use case/trạng thái, chẳng hạn validate khi submit.

**10. Class-level constraint phù hợp điều kiện gì?**

Quy tắc phụ thuộc nhiều fields/children của cùng object, ví dụ consistency hoặc duplicate product IDs.

**11. Tại sao không query database trong mỗi custom validator?**

Dễ N+1, phụ thuộc context và không giải quyết race ở commit.

**12. @Valid ở hai chiều association có thể gây vấn đề gì?**

Graph traversal phức tạp, performance/lazy loading và boundary khó kiểm soát; Bean Validation có cycle handling nhưng không thay thiết kế scope.

**13. getReference() có chắc truy vấn DB ngay không?**

Không.

**14. @GeneratedValue ID null trước persist có nhất thiết là graph lỗi không?**

Không; transient aggregate hợp lệ có thể chưa có database ID.

**15. orphanRemoval dùng cho mục đích gì?**

Xử lý lifecycle xóa child khi bị rời quan hệ sở hữu theo mapping.

**16. Tại sao không cascade REMOVE từ OrderLine sang Product?**

Product dùng chung, có lifecycle độc lập và không thuộc ownership của line.

**17. Vì sao DTO an toàn hơn deserialize trực tiếp thành entity?**

Giới hạn fields client được sửa, tránh graph giả và merge side effects.

**18. Validation pass có bảo đảm commit pass không?**

Không. DB constraints và concurrency có thể vẫn lỗi.

**19. Unique constraint bảo vệ điều gì Java check không bảo đảm?**

Những inserts cạnh tranh hoặc writers bypass Java validation.

**20. Khi nào @Version cần thiết?**

Khi cần phát hiện stale updates theo concurrency policy của entity; không thay mọi invariant nhiều hàng.

**21. Product active=true trong service có luôn đúng tới commit không?**

Không tự động; cần transaction/isolation/locking/version theo rule nghiệp vụ.

**22. JPQL bulk UPDATE có gọi @PreUpdate từng entity không?**

Không theo managed entity lifecycle thông thường.

**23. Khi Bean Validation tích hợp JPA, lỗi có thể xuất hiện ở đâu?**

Trong lifecycle persist/update, flush hoặc commit tùy provider và transaction boundary.

**24. @Valid trên Order.lines có chắc validate mọi Line trong DB chưa load không?**

Không nên suy vậy; traversal/lazy state/fetch plan quyết định dữ liệu có sẵn để validate.

**25. Vì sao cần kiểm tra tenant khi liên kết Product?**

Một FK hợp lệ không đồng nghĩa Product thuộc đúng tenant hoặc caller có quyền.

**26. Có nên dùng class-level validator để gọi payment gateway không?**

Không. External calls thuộc workflow riêng và có transaction/idempotency concerns.

**27. Điều gì khác nhau giữa Bean Validation violation và SQL constraint violation?**

Một lỗi phát sinh từ validation metadata/objects, lỗi kia từ ràng buộc database khi SQL thực thi.

**28. Vì sao nên kiểm thử với database thật?**

Để xác minh owning side, cascade, FK, UNIQUE, CHECK, orphanRemoval, flush/commit và concurrency.

**29. Khi nào dùng @Embedded?**

Để ánh xạ value object thuộc owner; có thể kết hợp `@Valid` để kiểm tra những fields bên trong.

**30. Nguyên tắc quan trọng nhất là gì?**

Xây object graph qua domain methods, validate đúng tầng và boundary, rồi để transaction và DB constraints bảo vệ tính toàn vẹn khi lưu thực sự.

## 36. Kịch bản tổng hợp: xác nhận đơn hàng với nhiều lớp validation

Một quy trình nghiệp vụ có yêu cầu:

- Client chỉ được gửi customerId, Product IDs và quantity.
- Customer/Product phải tồn tại, active và đúng tenant.
- OrderLine phải có parent đúng.
- Không có Product duplicate.
- Order chỉ được submit nếu không rỗng.
- Giá lấy từ server.
- Transaction phải bảo vệ consistency khi dữ liệu thay đổi đồng thời.
- Client không được tạo hai order giống nhau khi retry request không chắc đã commit.

### 36.1. Luồng khuyến nghị

```text
POST /orders
    |
    v
Authentication + tenant/permission context
    |
    v
DTO validation
    |
    +-- customerId != null
    +-- items not empty
    +-- quantity >= 1
    +-- distinct product IDs
    |
    v
BEGIN TRANSACTION
    |
    v
Find Customer + Products
    |
    +-- exists
    +-- same tenant
    +-- active / eligible
    |
    v
Construct PurchaseOrder (DRAFT)
    |
    +-- addLine() sets OrderLine.order
    +-- Product refs are existing, not cascaded
    +-- price snapshot from server
    |
    v
order.submit()
    |
    +-- at least 1 line
    +-- associations consistent
    +-- allowed status transition
    |
    v
Bean Validation (root + @Valid children)
    |
    v
em.persist(order)
    |
    +-- cascade PERSIST to new lines
    |
    v
flush
    |
    +-- foreign keys
    +-- NOT NULL / CHECK
    +-- UNIQUE(order_id, product_id)
    |
    v
COMMIT
    |
    +-- success -> response
    |
    +-- failure -> rollback and
                   classified error/retry policy
```

### 36.2. Idempotency của request

Nếu caller timeout sau khi server có thể đã commit và gửi lại request, quá trình “validate và tạo đơn” có thể chạy lần thứ hai. Vì vậy một hệ thống thực tế có thể cần **idempotency key** hoặc business request ID có unique constraint để tránh tạo đơn trùng.

Đây là yêu cầu khác với kiểm tra graph một lượt; tuy nhiên nó rất quan trọng để tính toàn vẹn khi lưu trong môi trường HTTP retry.

### 36.3. Kiểm tra tất cả children không đồng nghĩa lock cả Product catalog

Có thể xác nhận Product active và giá theo snapshot ở mức phù hợp use case, trong khi checkout/inventory có thể yêu cầu rule mạnh hơn. Không tùy tiện pessimistic-lock tất cả Product rows chỉ vì dùng `@Valid` trên OrderLine.

### 36.4. Hậu điều kiện sau commit

- PurchaseOrder có Customer đúng tenant.
- Mỗi OrderLine thuộc đúng Order qua FK.
- Không có Product duplicate theo business key.
- Quantity/price tuân thủ constraints.
- Order SUBMITTED có lines hợp lệ.
- Không có partial inserts nếu transaction rollback.
- Những concurrent operations không phá invariant đã được DB/transaction bảo vệ.
- Dữ liệu API trả về phản ánh transaction đã thành công, không chỉ object trong memory.

## 37. Kết luận

**Kiểm tra quan hệ và cấu trúc đối tượng trước khi lưu** trong JPA là nhiệm vụ có nhiều tầng. `@NotNull` và `@Valid` rất hữu ích, nhưng không tự sửa quan hệ hai chiều, không persist children, không truy vấn đảm bảo external references, không bảo vệ uniqueness dưới concurrency và không thay thế transaction hay database constraints.

Một chiến lược vững chắc là:

1. **Nhận dữ liệu qua DTO/command**, không cho client tự dựng hoặc merge entity graph tùy ý.
2. **Dựng aggregate qua methods có kiểm soát** như `addLine()`/`removeLine()`; bảo đảm cả owning và inverse sides nhất quán.
3. **Tách rõ `@Valid` và JPA cascade**: validation traversal không phải lifecycle propagation.
4. **Dùng field constraints, validation groups và class-level validators** cho quy tắc phù hợp với object graph đang có trong memory.
5. **Giới hạn graph traversal** để tránh lazy loading/N+1 và không validate cả những aggregate liên quan không cần thiết.
6. **Resolve và kiểm tra referenced entities** trong transactional service: existence, tenant, authorization, status, price policy.
7. **Giữ FK, UNIQUE, CHECK và NOT NULL ở database** để chặn lỗi mà Java checks không thể bảo đảm khi concurrent.
8. **Chọn transaction/version/locking strategy đúng invariant** thay vì coi việc validate trước persist là bảo đảm atomic.
9. **Cẩn trọng với merge partial graphs, orphanRemoval và bulk DML**, vì chúng có thể bỏ qua hoặc thay đổi những giả định validation thông thường.
10. **Kiểm thử cả object graph lẫn persistence thực**, bao gồm flush, commit, concurrency và trường hợp dữ liệu không hợp lệ.

Kết quả cần hướng tới không chỉ là “Bean Validation trả về không có lỗi”, mà là **một graph nhất quán về mặt domain, được JPA ánh xạ đúng và được database lưu bền vững mà không phá invariant khi nhiều request cùng hoạt động**.
