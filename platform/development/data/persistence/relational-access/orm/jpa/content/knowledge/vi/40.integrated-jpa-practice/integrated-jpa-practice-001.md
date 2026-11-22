# Thiết kế mô hình khách hàng, đơn hàng, chi tiết và sản phẩm

> **Module:** Data Persistence Relational Access ORM JPA  
> **Chương:** Thực hành tổng hợp  
> **Đề bài:** Thiết kế mô hình khách hàng, đơn hàng, chi tiết và sản phẩm

Một hệ thống bán hàng có bốn đối tượng cốt lõi: **khách hàng** (*Customer*), **đơn hàng** (*Order*), **chi tiết đơn hàng** (*OrderItem/OrderLine*) và **sản phẩm** (*Product*). Nếu chỉ nhìn giao diện, ta có thể nghĩ đơn hàng đơn giản là một danh sách sản phẩm. Nhưng khi thiết kế bằng Jakarta Persistence (JPA), cần trả lời thêm những câu hỏi quan trọng:

- Khách hàng nào sở hữu đơn hàng?
- Một sản phẩm xuất hiện trong nhiều đơn ra sao?
- Số lượng và giá đơn vị thuộc sản phẩm hay chi tiết đơn?
- Vì sao không ánh xạ đơn hàng với sản phẩm trực tiếp bằng `@ManyToMany`?
- Giá và tên sản phẩm sau này thay đổi thì lịch sử giao dịch có bị thay đổi không?
- Xóa chi tiết đơn hàng có được xóa sản phẩm không?
- Hai khách cùng mua sản phẩm cuối cùng cần transaction và locking như thế nào?
- Làm sao truy vấn danh sách đơn, chi tiết đơn, tổng tiền mà không gặp N+1 hoặc sai pagination?
- Những bất biến nào thuộc domain, constraint nào thuộc DB, hành vi nào cần kiểm thử thực tế?

Bài thực hành này xây dựng một mô hình xuyên suốt: yêu cầu nghiệp vụ → ERD → entities/value objects → JPA mappings → schema SQL → use-case service → repository/read model → transaction/concurrency → kiểm thử. Đích đến không chỉ là làm `em.persist()` chạy được, mà là **giữ dữ liệu giao dịch đúng đắn theo thời gian**.

Các ví dụ dùng `jakarta.persistence.*`, Java `BigDecimal`, JUnit 5 và Spring `@Transactional`; phần DDL minh họa bằng PostgreSQL. Chính sách về thuế, khuyến mãi, hoàn tiền, vận chuyển và nhiều kho được để ở phần mở rộng. Các snippet có thể chia thành những file Java tương ứng trong dự án.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chuyển yêu cầu bán hàng thành bốn thực thể với trách nhiệm rõ ràng.
2. Vẽ ERD và đánh dấu cardinality 1:N/N:1.
3. Biết tại sao `OrderItem` là entity riêng, không chỉ là bảng nối vô danh.
4. Phân biệt khóa chính kỹ thuật với business key như SKU và orderNumber.
5. Xác định owning side, inverse side và `mappedBy` trong JPA.
6. Quyết định cascade và orphanRemoval theo vòng đời nghiệp vụ.
7. Không cascade REMOVE tới Customer hoặc Product dùng chung.
8. Dùng Money/BigDecimal thay vì double cho giá bán.
9. Lưu snapshot giá, SKU và tên sản phẩm trên OrderItem.
10. Xây domain invariants cho quantity, currency, trùng sản phẩm và trạng thái đơn.
11. Phân biệt CustomerOrder aggregate root với Product catalog.
12. Tạo mapping `@ManyToOne`, `@OneToMany`, `@Embedded`, `@Version` đúng vai trò.
13. Viết migration SQL gồm primary keys, foreign keys, UNIQUE, CHECK và indexes.
14. Dùng transaction cho tạo đơn và đặt đơn.
15. Hiểu optimistic locking, concurrency và vấn đề oversell.
16. Biết giới hạn của `@Version` trên root khi chỉ sửa child collections.
17. Thiết kế API/repository đọc danh sách đơn bằng DTO.
18. Tránh N+1 và collection-fetch pagination sai.
19. Biết vì sao nên vô hiệu hóa Product/Customer thay vì xóa lịch sử.
20. Kiểm thử domain không DB và mapping với `flush/clear/find`.
21. Kiểm thử tồn kho dưới hai transactions cạnh tranh.
22. Giải thích được các lựa chọn thiết kế và hướng mở rộng sau này.

---

## 2. Yêu cầu nghiệp vụ của bài thực hành

Giả sử hệ thống bán sách và phụ kiện:

1. Một khách có ID, email duy nhất, tên và trạng thái hoạt động.
2. Một sản phẩm có ID, SKU duy nhất, tên, giá hiện tại, số lượng tồn và trạng thái hoạt động.
3. Một khách có thể tạo nhiều đơn hàng.
4. Mỗi đơn thuộc đúng một khách.
5. Đơn mới ở trạng thái `DRAFT` và có thể tạm thời rỗng.
6. Một đơn có nhiều dòng hàng; mỗi dòng thuộc đúng một đơn.
7. Một dòng tham chiếu đúng một sản phẩm và số lượng lớn hơn 0.
8. Một sản phẩm có thể nằm trong nhiều đơn.
9. Trong phiên bản bài này, một sản phẩm chỉ có **một dòng trên mỗi đơn**; muốn mua thêm thì đổi quantity.
10. Khi thêm sản phẩm vào đơn, dòng hàng lưu giá, SKU và tên ở thời điểm thêm.
11. Đơn đã `PLACED` không được âm thầm thay đổi item/quantity/price.
12. Không được place đơn rỗng.
13. Khi place, tồn kho bị trừ; không được âm.
14. Nếu một sản phẩm thiếu hàng, không được commit một phần thay đổi của đơn.
15. Khách bị vô hiệu hóa không được tạo đơn mới.
16. Sản phẩm ngừng bán không được thêm vào đơn mới.
17. Lịch sử đơn vẫn phải đọc được sau khi catalog hoặc profile thay đổi.

### 2.1. Những điều chưa giải quyết

Bài chưa triển khai thuế, giảm giá, shipper, payment gateway, hoàn tiền, đa kho, giá theo thời điểm checkout, địa chỉ giao hàng hay xóa dữ liệu cá nhân theo chính sách cụ thể. Đây là các use case bổ sung, không nên âm thầm đoán rồi nhét tất cả vào một `Order` entity.

### 2.2. Quy tắc phải viết trước annotation

Nếu chưa biết đơn có cho phép nhiều dòng cùng sản phẩm hay không, việc thêm UNIQUE(order_id,product_id) có thể sai ngay từ đầu. Nếu chưa quyết định giá được khóa ở thời điểm thêm hay lúc checkout, không thể thiết kế item price snapshot hoàn chỉnh.

---

## 3. Sơ đồ ERD

```text
+--------------------+
|      customers     |
+--------------------+
| PK id              |
| UQ email           |
| display_name       |
| active             |
| version            |
+----------+---------+
           |
           | 1
           | N
+----------v---------+
|   customer_orders  |
+--------------------+
| PK id              |
| UQ order_number    |
| FK customer_id     |
| status             |
| created_at         |
| placed_at          |
| version            |
+----------+---------+
           |
           | 1
           | N
+----------v---------+         +---------------------+
|     order_items    |   N:1   |       products      |
+--------------------+-------->+---------------------+
| PK id              |         | PK id               |
| FK order_id        |         | UQ sku              |
| FK product_id      |         | name                |
| line_number        |         | price_amount        |
| quantity           |         | price_currency      |
| unit_amount        |         | stock_quantity      |
| unit_currency      |         | active              |
| sku_snapshot       |         | version             |
| name_snapshot      |         +---------------------+
+--------------------+

UNIQUE(order_id, product_id)
UNIQUE(order_id, line_number)
```

### 3.1. Cardinality

| Quan hệ | Ý nghĩa | FK |
|---|---|---|
| Customer 1:N CustomerOrder | Một khách có nhiều đơn; mỗi đơn thuộc một khách | customer_orders.customer_id |
| CustomerOrder 1:N OrderItem | Một đơn có nhiều dòng; mỗi dòng thuộc một đơn | order_items.order_id |
| Product 1:N OrderItem | Một sản phẩm xuất hiện ở nhiều dòng thuộc nhiều đơn | order_items.product_id |

### 3.2. Quan hệ Order–Product có vẻ N:N

Nhìn theo business, nhiều Orders chứa nhiều Products. Nhưng mối liên hệ có **quantity, unitPrice, snapshot, lineNumber**, nên cần entity trung gian `OrderItem`.

### 3.3. Vì sao chọn customer_orders thay vì order?

`ORDER` là một SQL keyword phổ biến; tên bảng `customer_orders` tránh phải quote identifier và giảm rủi ro portability.

---

## 4. Tại sao không dùng @ManyToMany trực tiếp?

Một mapping ban đầu:

```java
@ManyToMany
private Set<Product> products = new HashSet<>();
```

chỉ biểu diễn rằng Order có Product nào. Nó không diễn đạt:

- Mua bao nhiêu đơn vị?
- Giá từng đơn vị khi mua là bao nhiêu?
- Thứ tự dòng hiển thị là gì?
- Tên/SKU trên hóa đơn cũ là gì?
- Có discount/tax/warehouse khác nhau trên từng dòng không?

Vì vậy nên thiết kế:

```text
CustomerOrder --< OrderItem >-- Product
```

### 4.1. OrderItem là association entity

Nó có ID/lifecycle và dữ liệu riêng. `order_id`, `product_id` định danh quan hệ; `quantity` và `unitPrice` định nghĩa giao dịch.

### 4.2. Composite key hay surrogate key?

Có thể dùng `@EmbeddedId(orderId,productId)` nếu một sản phẩm duy nhất trong mỗi đơn. Bài chọn `OrderItem.id Long` riêng và DB UNIQUE(order_id,product_id). Điều này đơn giản khi tham chiếu/đổi policy sau này.

### 4.3. Nếu sau này cho phép hai dòng cùng Product

Ví dụ cùng SKU nhưng được lấy từ hai kho hoặc có chiết khấu khác nhau: phải thay domain duplicate policy và UNIQUE constraint. Không chỉ xóa validate Java mà quên migration.

---

## 5. Xác định aggregate root và vòng đời

```text
Customer --------------------.
  independent                |
                             v
                        CustomerOrder
                        aggregate root
                             |
                       owns lifecycle
                             |
                             v
                          OrderItem
                             |
                        references
                             |
                             v
                          Product
                         independent
```

### 5.1. Customer và Product tồn tại độc lập

Xóa một OrderItem không được xóa Product. Xóa một Order không được xóa Customer. Không đặt cascade REMOVE vào hai reference này.

### 5.2. OrderItem phụ thuộc Order

Dòng hàng không có ý nghĩa ngoài Order trong mô hình. `CascadeType.ALL` và `orphanRemoval=true` trên `CustomerOrder.items` phù hợp khi chỉ thay đổi qua aggregate methods.

### 5.3. Domain ownership khác association owning side

JPA owning side là phía ghi khóa ngoại; ở OrderItem, các field `order`/`product` với `@ManyToOne` giữ FK. Business lifecycle ownership lại thuộc CustomerOrder, không thuộc Product.

### 5.4. Aggregate không thay transaction

Nó bảo vệ bất biến nội bộ, còn cập nhật tồn kho của Product và chuyển trạng thái Order phải được phối hợp bằng transaction.

---

## 6. Khóa chính, business key và trạng thái xóa

| Entity | PK | Business key | Ghi chú |
|---|---|---|---|
| Customer | Long IDENTITY | email normalized | Email có thể thay đổi |
| Product | Long IDENTITY | SKU | Catalog reference ổn định |
| CustomerOrder | Long IDENTITY | orderNumber | Dùng đối soát/idempotency |
| OrderItem | Long IDENTITY | orderId+productId theo policy | UNIQUE ở DB |

### 6.1. Không dùng email làm PK

Email thay đổi sẽ khó chịu khi có hàng nghìn Orders tham chiếu. Surrogate ID ít biến động hơn.

### 6.2. Không hard-code ID=1 trong test

Sequence/IDENTITY không bảo đảm liên tục, đặc biệt khi có transaction rollback hoặc test chạy song song.

### 6.3. Customer/Product nên deactivate

Giữ foreign keys và lịch sử đơn. `active=false` cấm giao dịch mới theo domain policy, không xóa giao dịch cũ. Quyền xóa/ẩn danh PII cần một chính sách riêng.

### 6.4. Idempotency không chỉ là UNIQUE

`UNIQUE(order_number)` bảo vệ trùng mã, nhưng API tạo đơn còn phải quy định response khi request cùng idempotency key được gửi lại sau timeout; không tạo thêm một đơn mới chỉ vì client retry.

---

## 7. Value object Money và BigDecimal

Không dùng `double` làm nguồn số tiền chính xác. Một Money gồm amount và currency.

```java
package demo.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

@Embeddable
public class Money {

    @Column(name = "amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency", nullable = false,
            length = 3)
    private String currency;

    protected Money() {}

    public Money(BigDecimal amount, String currency) {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Negative money not allowed");
        }

        String code =
            currency.trim().toUpperCase(Locale.ROOT);

        Currency.getInstance(code);

        this.amount = amount.setScale(
            2, RoundingMode.UNNECESSARY);
        this.currency = code;
    }

    public static Money zero(String currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other);

        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currency mismatch");
        }

        return new Money(
            amount.add(other.amount), currency);
    }

    public Money times(int positiveQuantity) {
        if (positiveQuantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        return new Money(
            amount.multiply(
                BigDecimal.valueOf(positiveQuantity)),
            currency
        );
    }

    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }

    @Override
    public boolean equals(Object value) {
        if (this == value) return true;
        if (!(value instanceof Money other)) return false;
        return amount.equals(other.amount)
            && currency.equals(other.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currency);
    }
}
```

### 7.1. Chính sách scale trong bài

Ví dụ chọn 2 chữ số thập phân; một số tiền tệ như VND hoặc hệ thống tính thuế cần scale/rounding khác. Không áp scale=2 cho mọi domain mà chưa có yêu cầu nghiệp vụ.

### 7.2. Money có equality theo giá trị

Hai Money `10.0 USD` và `10.00 USD` trở thành cùng scale 2, nên bằng nhau qua `equals`. Entity với generated ID có equality/identity concerns khác.

### 7.3. Không cộng nhầm currency

`10 USD + 10 EUR` không phải `20 USD`. Order trong ví dụ buộc mọi Items có cùng currency; một hệ đa tiền tệ cần tỷ giá và snapshot conversion cụ thể.

### 7.4. JPA @Embeddable không tự xác minh schema

Unit test `Money.plus` chứng minh phép tính. Integration test `persist/flush/clear/find` chứng minh amount/currency được lưu đúng.

---

## 8. Entity Customer

```java
package demo.shop.domain;

import jakarta.persistence.*;
import java.util.Locale;
import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email",
            nullable = false, unique = true, length = 254)
    private String email;

    @Column(name = "display_name",
            nullable = false, length = 150)
    private String displayName;

    @Column(name = "active", nullable = false)
    private boolean active;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Customer() {}

    public Customer(String email, String displayName) {
        Objects.requireNonNull(email);

        String normalized = email.trim()
            .toLowerCase(Locale.ROOT);

        if (normalized.isBlank()
                || !normalized.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email");
        }
        if (displayName == null
                || displayName.isBlank()) {
            throw new IllegalArgumentException(
                "Display name required");
        }

        this.email = normalized;
        this.displayName = displayName.trim();
        this.active = true;
    }

    public void deactivate() {
        active = false;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Display name required");
        }
        displayName = newName.trim();
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }
    public boolean isActive() { return active; }
    public long getVersion() { return version; }
}
```

### 8.1. Vì sao không bắt buộc có `Customer.orders`?

Quan hệ đã tồn tại nhờ `CustomerOrder.customer`. Một list Orders trên Customer có thể kéo hàng nghìn records vào persistence context; với trang lịch sử nên query/paginate từ CustomerOrder repository.

### 8.2. Validate email ở ví dụ chỉ tối thiểu

`contains("@")` không phải email validator production. Hệ thật cần policy về Unicode, case, normalization và uniqueness/collation của database. Không coi logic minh họa này là chuẩn xác thực đầy đủ.

### 8.3. Deactivate thay vì remove

Khách không được tạo Order mới khi inactive, nhưng Order lịch sử vẫn cần hiển thị. Khi có nghĩa vụ xóa dữ liệu cá nhân, thiết kế anonymization hoặc tách PII khỏi records phù hợp.

---

## 9. Entity Product

```java
package demo.shop.domain;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku",
            nullable = false, unique = true, length = 80)
    private String sku;

    @Column(name = "name",
            nullable = false, length = 200)
    private String name;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(name = "price_amount",
                nullable = false, precision = 19, scale = 2)),
        @AttributeOverride(
            name = "currency",
            column = @Column(name = "price_currency",
                nullable = false, length = 3))
    })
    private Money currentPrice;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Column(name = "active", nullable = false)
    private boolean active;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Product() {}

    public Product(String sku, String name,
                   Money price, int stockQuantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU required");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                "Name required");
        }
        if (stockQuantity < 0) {
            throw new IllegalArgumentException(
                "Stock cannot be negative");
        }

        this.sku = sku.trim();
        this.name = name.trim();
        this.currentPrice = Objects.requireNonNull(price);
        this.stockQuantity = stockQuantity;
        this.active = true;
    }

    public void changePrice(Money price) {
        currentPrice = Objects.requireNonNull(price);
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Name required");
        }
        name = newName.trim();
    }

    public void deactivate() {
        active = false;
    }

    public void reserveStock(int quantity) {
        if (!active) {
            throw new IllegalStateException(
                "Product is inactive");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }
        if (stockQuantity < quantity) {
            throw new IllegalStateException(
                "Insufficient stock");
        }

        stockQuantity -= quantity;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public Money getCurrentPrice() {
        return currentPrice;
    }
    public int getStockQuantity() {
        return stockQuantity;
    }
    public boolean isActive() { return active; }
    public long getVersion() { return version; }
}
```

### 9.1. Product mô tả catalog hiện tại

Giá và tên có thể thay đổi. Lịch sử OrderItem không được tính dựa vào currentPrice/name khi hiển thị hóa đơn.

### 9.2. Không ánh xạ Product.orderItems nếu không cần

Lịch sử bán sản phẩm có thể được query qua OrderItem; tránh collection lớn không cần thiết trên Product.

### 9.3. Tồn kho là mô hình đơn giản

`stockQuantity` minh họa sản phẩm tại một kho và trừ khi đặt đơn. Hệ thống thật có thể có InventoryItem/StockReservation/Warehouse và ledger để xử lý nhiều kho, returns, holds hoặc expiry.

### 9.4. @Version quan trọng

Nếu mọi thay đổi tồn kho đi qua versioned JPA updates, provider có thể phát hiện stale concurrent modifications. Nhưng phải bảo đảm các writers native SQL/batch jobs không bỏ qua versioning contract.

---

## 10. Enum trạng thái đơn hàng

```java
package demo.shop.domain;

public enum OrderStatus {
    DRAFT,
    PLACED
}
```

```text
     create
       |
       v
     DRAFT
       |  add/change/remove items
       |
       |  place, validate, reserve stock
       v
     PLACED
       |  immutable item history
       v
  future flows: shipment/payment/cancel
```

### 10.1. DRAFT được rỗng, PLACED không được rỗng

Đó là domain invariant. Một CHECK trên một row Order không đủ để đếm child rows đơn giản; cần domain/service/transaction rules và test phù hợp.

### 10.2. Vì sao chưa thêm CANCELLED?

Hủy một đơn đã đặt có thể phải nhập lại tồn, hủy thanh toán và vận chuyển. Thêm enum mà không định nghĩa transition/compensation dễ phá dữ liệu.

### 10.3. EnumType.STRING

Lưu `"DRAFT"` và `"PLACED"` thay vì ordinal giúp dễ kiểm lịch sử và migrations hơn, nhưng khi đổi tên enum vẫn cần data migration.

---

## 11. Entity OrderItem

```java
package demo.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(
    name = "order_items",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uq_item_product",
            columnNames = {"order_id", "product_id"}),
        @UniqueConstraint(
            name = "uq_item_line",
            columnNames = {"order_id", "line_number"})
    }
)
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private CustomerOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(name = "line_number", nullable = false)
    private int lineNumber;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "sku_snapshot",
            nullable = false, length = 80)
    private String skuSnapshot;

    @Column(name = "name_snapshot",
            nullable = false, length = 200)
    private String nameSnapshot;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(name = "unit_amount",
                nullable = false, precision = 19, scale = 2)),
        @AttributeOverride(
            name = "currency",
            column = @Column(name = "unit_currency",
                nullable = false, length = 3))
    })
    private Money unitPrice;

    protected OrderItem() {}

    OrderItem(CustomerOrder order, Product product,
              int lineNumber, int quantity) {
        if (order == null || product == null) {
            throw new IllegalArgumentException(
                "Order/product required");
        }
        if (lineNumber <= 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                "Line number and quantity must be positive");
        }
        if (!product.isActive()) {
            throw new IllegalStateException(
                "Product unavailable");
        }

        this.order = order;
        this.product = product;
        this.lineNumber = lineNumber;
        this.quantity = quantity;
        this.skuSnapshot = product.getSku();
        this.nameSnapshot = product.getName();
        this.unitPrice = product.getCurrentPrice();
    }

    void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }
        quantity = newQuantity;
    }

    void unlinkFromOrder() {
        order = null;
    }

    public Money lineTotal() {
        return unitPrice.times(quantity);
    }

    public Long getId() { return id; }
    public CustomerOrder getOrder() { return order; }
    public Product getProduct() { return product; }
    public int getLineNumber() { return lineNumber; }
    public int getQuantity() { return quantity; }
    public String getSkuSnapshot() {
        return skuSnapshot;
    }
    public String getNameSnapshot() {
        return nameSnapshot;
    }
    public Money getUnitPrice() { return unitPrice; }
}
```

### 11.1. Chụp dữ liệu giao dịch

`unitPrice`, `skuSnapshot` và `nameSnapshot` được lưu trên OrderItem khi tạo dòng. Product giá/tên mới không sửa các trường snapshot.

### 11.2. Product không có cascade

`OrderItem.product` là reference dùng chung. Không đặt `CascadeType.ALL` hoặc `REMOVE` trên `@ManyToOne Product`.

### 11.3. Phía nào ghi FK?

`OrderItem.order` và `OrderItem.product` với `@JoinColumn` là owning sides của hai associations.

### 11.4. Vì sao có lineNumber?

Để đơn hàng có thứ tự dòng ổn định do domain quyết định. UNIQUE(order_id,line_number) bảo vệ trạng thái tại DB; `@OrderBy("lineNumber ASC")` ở parent hỗ trợ đọc đúng thứ tự.

### 11.5. Không có setter đổi giá sau tạo

Nếu muốn repricing ở DRAFT, thiết kế một domain method với policy rõ. Không để controller tùy ý sửa OrderItem.unitPrice, đặc biệt sau PLACED.

---

## 12. Entity CustomerOrder

```java
package demo.shop.domain;

import jakarta.persistence.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "customer_orders")
public class CustomerOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number",
            nullable = false, unique = true, length = 80)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "placed_at")
    private Instant placedAt;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true)
    @OrderBy("lineNumber ASC")
    private List<OrderItem> items =
        new ArrayList<>();

    protected CustomerOrder() {}

    public CustomerOrder(
            String orderNumber,
            Customer customer,
            Instant createdAt) {

        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException(
                "Order number required");
        }

        this.customer =
            Objects.requireNonNull(customer);

        if (!customer.isActive()) {
            throw new IllegalStateException(
                "Inactive customer cannot create order");
        }

        this.orderNumber = orderNumber.trim();
        this.createdAt =
            Objects.requireNonNull(createdAt);
        this.status = OrderStatus.DRAFT;
    }

    public OrderItem addItem(
            Product product, int quantity) {

        requireDraft();
        Objects.requireNonNull(product);

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        if (!items.isEmpty()
            && !items.get(0).getUnitPrice()
                .getCurrency()
                .equals(product.getCurrentPrice()
                    .getCurrency())) {
            throw new IllegalArgumentException(
                "Mixed currencies are not allowed");
        }

        for (OrderItem existing : items) {
            Product previous = existing.getProduct();

            if (previous == product
                || (previous.getId() != null
                    && previous.getId().equals(
                        product.getId()))) {
                throw new IllegalArgumentException(
                    "Product already in order");
            }
        }

        int next = items.stream()
            .mapToInt(OrderItem::getLineNumber)
            .max()
            .orElse(0) + 1;

        OrderItem item =
            new OrderItem(this, product, next, quantity);

        items.add(item);
        return item;
    }

    public void changeQuantity(
            OrderItem item, int quantity) {
        requireDraft();
        requireOwned(item);
        item.changeQuantity(quantity);
    }

    public void removeItem(OrderItem item) {
        requireDraft();
        requireOwned(item);
        items.remove(item);
        item.unlinkFromOrder();
    }

    public void assertReadyToPlace() {
        requireDraft();
        if (items.isEmpty()) {
            throw new IllegalStateException(
                "Cannot place empty order");
        }
    }

    public void place(Instant now) {
        assertReadyToPlace();
        placedAt = Objects.requireNonNull(now);
        status = OrderStatus.PLACED;
    }

    public Money total() {
        if (items.isEmpty()) {
            throw new IllegalStateException(
                "Empty order has no currency");
        }

        String currency =
            items.get(0).getUnitPrice().getCurrency();

        Money sum = Money.zero(currency);
        for (OrderItem item : items) {
            sum = sum.plus(item.lineTotal());
        }
        return sum;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only DRAFT orders may change");
        }
    }

    private void requireOwned(OrderItem item) {
        if (item == null || !items.contains(item)) {
            throw new IllegalArgumentException(
                "Item not in this order");
        }
    }

    public Long getId() { return id; }
    public String getOrderNumber() {
        return orderNumber;
    }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getPlacedAt() { return placedAt; }
    public long getVersion() { return version; }
    public List<OrderItem> getItems() {
        return Collections.unmodifiableList(items);
    }
}
```

### 12.1. Vì sao thao tác trên Item đi qua Order?

Để kiểm DRAFT, duplicate Product, currency và owned-child rules tại một nơi. Không để caller sửa collection trực tiếp.

### 12.2. Vì sao số dòng tính bằng max+1?

Nếu dòng 2 bị xóa, `items.size()+1` có thể tái sử dụng số 2 khi đã có dòng số 3 và vi phạm UNIQUE(order_id,line_number). Max+1 tránh một số va chạm. Nếu cần reorder, thêm domain operation riêng.

### 12.3. @OrderBy khác @OrderColumn

`@OrderBy("lineNumber ASC")` sort bằng thuộc tính OrderItem; `@OrderColumn` lưu một persistent list index. Đừng dùng chúng như nhau.

### 12.4. DRAFT có thể rỗng

Phù hợp giỏ hàng đang chỉnh. Nhưng không được đặt đơn với danh sách rỗng.

### 12.5. total() dựa snapshot

Không đọc Product.currentPrice khi tính tiền lịch sử.

### 12.6. Lưu ý về domain methods trong một model JPA

`@Entity` class có Java behavior bình thường; unit test có thể gọi các methods mà không boot provider. Integration tests riêng chứng minh mapping/cascade đúng.

---

## 13. Bảng quan hệ owning side và cascade

| Association | Mapping | Owning side của FK | Lifecycle |
|---|---|---|---|
| Order → Customer | ManyToOne + customer_id | CustomerOrder | Không cascade Customer |
| Item → Order | ManyToOne + order_id | OrderItem | Order quản lý Item |
| Order → Items | OneToMany(mappedBy="order") | Inverse | Cascade ALL + orphanRemoval |
| Item → Product | ManyToOne + product_id | OrderItem | Không cascade Product |

### 13.1. Đồng bộ hai phía

Khi `addItem()` tạo child, constructor set `item.order=this`, rồi parent thêm vào List. Khi gỡ, parent xóa khỏi List và child unlink. Đây là pattern tránh in-memory graph lệch với FK owning side.

### 13.2. Cascade không đồng nghĩa ON DELETE CASCADE

JPA cascade là entity lifecycle behavior; database FK ON DELETE CASCADE là SQL engine behavior. Chúng không thay thế nhau và có thể dẫn tới tác động khác nếu cấu hình không chủ đích.

### 13.3. Không xóa đơn lịch sử tùy tiện

Có `CascadeType.ALL` cho Item không có nghĩa service phải cho phép `em.remove(order)` ở mọi trạng thái. Domain retention và audit policy cần kiểm trước.

---

## 14. Schema PostgreSQL và migration

Ví dụ một versioned migration:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY
       PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_customers_email UNIQUE(email)
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY
       PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price_amount NUMERIC(19,2) NOT NULL,
    price_currency VARCHAR(3) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_products_sku UNIQUE(sku),
    CONSTRAINT ck_products_price
       CHECK (price_amount >= 0),
    CONSTRAINT ck_products_stock
       CHECK (stock_quantity >= 0)
);

CREATE TABLE customer_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY
       PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    placed_at TIMESTAMP(6) WITH TIME ZONE,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_orders_number UNIQUE(order_number),
    CONSTRAINT fk_orders_customer
       FOREIGN KEY (customer_id)
       REFERENCES customers(id),
    CONSTRAINT ck_orders_status
       CHECK (status IN ('DRAFT','PLACED')),
    CONSTRAINT ck_orders_placed_at
       CHECK (
         (status='DRAFT' AND placed_at IS NULL)
         OR
         (status='PLACED' AND placed_at IS NOT NULL)
       )
);

CREATE TABLE order_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY
       PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    sku_snapshot VARCHAR(80) NOT NULL,
    name_snapshot VARCHAR(200) NOT NULL,
    unit_amount NUMERIC(19,2) NOT NULL,
    unit_currency VARCHAR(3) NOT NULL,

    CONSTRAINT fk_items_order
       FOREIGN KEY (order_id)
       REFERENCES customer_orders(id),

    CONSTRAINT fk_items_product
       FOREIGN KEY (product_id)
       REFERENCES products(id),

    CONSTRAINT uq_items_product
       UNIQUE(order_id,product_id),

    CONSTRAINT uq_items_line
       UNIQUE(order_id,line_number),

    CONSTRAINT ck_items_quantity
       CHECK (quantity > 0),

    CONSTRAINT ck_items_line
       CHECK (line_number > 0),

    CONSTRAINT ck_items_price
       CHECK (unit_amount >= 0)
);

CREATE INDEX idx_orders_customer_created
  ON customer_orders(customer_id,created_at DESC,id DESC);

CREATE INDEX idx_items_order_id
  ON order_items(order_id);

CREATE INDEX idx_items_product_id
  ON order_items(product_id);
```

### 14.1. Chỉ là PostgreSQL DDL

MySQL/Oracle/SQL Server/H2 có identity, timestamp, boolean và DDL khác. Kiểm thử migrations trên engine sẽ triển khai, không ép một SQL migration vendor-specific chạy trên mọi embedded DB.

### 14.2. Constraints bổ sung domain rules

Domain cấm quantity<=0, stock âm và price âm; database CHECK bảo vệ dữ liệu khỏi các writer bypass Java API. UNIQUE bảo vệ race/duplicate từ các transactions.

### 14.3. Constraint không thể thay mọi quy tắc

CHECK trên một row Order không tự kiểm đơn PLACED có ít nhất một child trong bảng OrderItems. Domain/service/transaction logic vẫn cần. Nếu nhiều external writers, có thể cần trigger hoặc thiết kế DB contract bổ sung.

### 14.4. FK không xóa lịch sử theo cascade

Không đặt ON DELETE CASCADE từ orders tới customers/products. References giữ toàn vẹn giao dịch; deactivate là policy của ví dụ.

### 14.5. Không sửa schema production tự động bằng Hibernate update

Nếu dùng Flyway/Liquibase, nên chạy migrations rồi cấu hình Hibernate validate:

```properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
```

Hibernate validate có giới hạn, không bảo đảm kiểm mọi index/CHECK, nên vẫn cần DB-specific assertions.

---

## 15. Luồng tạo dữ liệu cơ sở

Trong một transaction JPA:

```java
Customer customer =
    new Customer("buyer@example.com", "Nguyen An");

Product book = new Product(
    "BOOK-101", "JPA Handbook",
    new Money(new BigDecimal("19.50"), "USD"),
    12);

Product mouse = new Product(
    "MOUSE-20", "Wireless Mouse",
    new Money(new BigDecimal("25.00"), "USD"),
    6);

em.persist(customer);
em.persist(book);
em.persist(mouse);
em.flush();

Long customerId = customer.getId();
Long bookId = book.getId();
Long mouseId = mouse.getId();
```

### 15.1. Product và Customer được persist riêng

Không rely vào cascade từ CustomerOrder để sinh Customer/Product mới. Chúng có lifecycle độc lập, thường được quản lý bằng service khác.

### 15.2. ID có thể được cấp ở các thời điểm khác nhau

Với IDENTITY, INSERT có thể xảy ra sớm để lấy generated ID. Đừng viết tests phụ thuộc ID cụ thể hoặc SQL timing nếu không phải contract.

---

## 16. Tạo đơn và thêm OrderItems

```java
Customer managedCustomer =
    em.find(Customer.class, customerId);

CustomerOrder order = new CustomerOrder(
    "ORD-2026-0001",
    managedCustomer,
    Instant.parse("2026-11-15T03:00:00Z")
);

Product managedBook =
    em.find(Product.class, bookId);

Product managedMouse =
    em.find(Product.class, mouseId);

order.addItem(managedBook, 2);
order.addItem(managedMouse, 1);

em.persist(order);
em.flush();
```

Dữ liệu logic:

| Line | Product SKU | Qty | Giá snapshot | Thành tiền |
|---|---|---:|---:|---:|
| 1 | BOOK-101 | 2 | 19.50 USD | 39.00 USD |
| 2 | MOUSE-20 | 1 | 25.00 USD | 25.00 USD |
| | **Tổng** | | | **64.00 USD** |

### 16.1. Persist parent cascades Items

`@OneToMany(cascade=ALL)` trên CustomerOrder có thể persist children. Kiểm bằng `flush/clear/find` chứ không chỉ thấy List có 2 entries.

### 16.2. Foreign keys đúng ownership

OrderItem constructor đặt `order` và `product`; ORM ghi `order_id` và `product_id` theo owning sides.

### 16.3. Currency rule

Cả hai Products dùng USD. Nếu Product thứ hai dùng EUR, `addItem` từ chối theo single-currency policy.

---

## 17. Tại sao snapshot cần thiết?

Giả sử sau khi Order đã có dòng BOOK-101:

```java
managedBook.changePrice(
    new Money(new BigDecimal("29.00"), "USD"));

managedBook.rename("JPA Handbook 2nd Edition");
em.flush();
```

Giá và tên catalog đổi. Nhưng OrderItem của đơn trước vẫn phải giữ:

```text
skuSnapshot   = BOOK-101
nameSnapshot  = JPA Handbook
unitPrice     = 19.50 USD
```

### 17.1. Nếu chỉ có FK Product?

Màn hình lịch sử sẽ hiển thị tên và giá **mới**, dù khách mua với dữ liệu **cũ**. Total có thể thay đổi sau mỗi lần catalog update.

### 17.2. Khi nào snapshot được chụp?

Bài chọn **lúc thêm item vào DRAFT**. Nếu nghiệp vụ yêu cầu xác nhận giá lại lúc đặt, phải thêm explicit repricing/quote-confirmation step thay vì tự động cập nhật không kiểm soát.

### 17.3. Không để nameSnapshot tự đồng bộ

Snapshot là dữ liệu lịch sử bất biến theo contract. Nếu muốn sửa lỗi chính tả hoặc chứng từ đã xuất, cần audit/correction workflow riêng, không âm thầm ghi đè.

---

## 18. Từ DRAFT sang PLACED

`CustomerOrder.place(now)` kiểm:

- Đơn còn DRAFT.
- Có ít nhất một OrderItem.
- Thời gian đặt đơn hợp lệ/không null.
- Status chuyển PLACED.

Nhưng tồn kho ở Product cần service phối hợp trong cùng transaction.

```text
create DRAFT
   |
   v
add/change/remove Items
   |
   v
place request
   |
   +--> Validate ownership/status/items
   |
   +--> Reserve stock for every Product
   |
   +--> Mark Order PLACED
   |
   +--> Flush / commit transaction
   |
   +--> On any failure: rollback all changes
```

### 18.1. Vì sao không trừ stock khi chỉ thêm item?

DRAFT có thể là giỏ hàng người dùng bỏ dở. Bài chọn trừ khi place. Hệ thống cần “hold inventory” trước payment có thể dùng StockReservation entity và thời hạn giữ hàng.

### 18.2. Không cho sửa PLACED

Chỉnh quantity sau place mà không điều chỉnh stock sẽ phá dữ liệu. Domain methods phải bảo vệ state; application service không tự sửa JPA fields bằng reflection/direct setters.

---

## 19. Application service với @Transactional

Một service minh họa:

```java
package demo.shop.application;

import demo.shop.domain.*;

import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import jakarta.persistence.PersistenceContext;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

@Service
public class OrderApplicationService {

    @PersistenceContext
    private EntityManager em;

    private final Clock clock;

    public OrderApplicationService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    @Transactional
    public Long createDraft(
            Long customerId, String orderNumber) {

        Customer customer =
            em.find(Customer.class, customerId);

        if (customer == null || !customer.isActive()) {
            throw new IllegalArgumentException(
                "Customer unavailable");
        }

        CustomerOrder order = new CustomerOrder(
            orderNumber, customer, Instant.now(clock));

        em.persist(order);
        em.flush();

        return order.getId();
    }

    @Transactional
    public void addItem(
            Long orderId, Long productId, int quantity) {

        CustomerOrder order =
            em.find(CustomerOrder.class, orderId);

        Product product =
            em.find(Product.class, productId);

        if (order == null || product == null) {
            throw new IllegalArgumentException(
                "Order or product not found");
        }

        // Bảo vệ root version cả khi chỉ thêm child.
        em.lock(
            order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);

        order.addItem(product, quantity);
    }

    @Transactional
    public void place(Long orderId) {

        CustomerOrder order = em.createQuery(
            """
            SELECT DISTINCT o
            FROM CustomerOrder o
            LEFT JOIN FETCH o.items
            WHERE o.id = :id
            """,
            CustomerOrder.class
        )
        .setParameter("id", orderId)
        .getSingleResult();

        order.assertReadyToPlace();

        for (OrderItem item : order.getItems()) {
            // To-one Product có thể cần thêm SELECT.
            // Có thể tối ưu fetch plan nếu Items nhiều.
            item.getProduct().reserveStock(
                item.getQuantity());
        }

        order.place(Instant.now(clock));
        em.flush();
    }
}
```

### 19.1. @Transactional không phải một JPA annotation

Đây là Spring transaction boundary. Một method gọi qua Spring proxy được áp transaction; tạo service bằng `new` không tự có proxy behavior.

### 19.2. Clock giúp test deterministic

```java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
```

Trong test có thể inject `Clock.fixed(...)`.

### 19.3. Domain + application responsibilities

Order biết mình có được place hay không; Product biết stock còn đủ không; service phối hợp writes nguyên tử và kiểm access rights.

### 19.4. Authorization chưa được thể hiện

Snippet chỉ demo persistence. Hệ thật phải xác minh principal/tenant được tạo/sửa/xem Order theo Customer, không tin một `orderId` bất kỳ từ client.

### 19.5. Flushing không đồng nghĩa committing

`em.flush()` có thể làm lỗi SQL/optimistic lock xuất hiện sớm, nhưng transaction vẫn cần commit. Lỗi deferred constraints có thể xảy ra lúc commit.

---

## 20. Concurrent purchases và @Version

Giả sử chỉ còn 1 sản phẩm trong kho. Hai transactions cùng load `stock=1` và `version=5`.

```text
Tx A: read Product stock=1, version=5
Tx B: read Product stock=1, version=5

Tx A: reserveStock(1), stock=0
Tx B: reserveStock(1), stock=0

Tx A: UPDATE ... WHERE id=? AND version=5
Tx A: commit, version becomes 6

Tx B: UPDATE ... WHERE id=? AND version=5
Tx B: stale version -> optimistic conflict
Tx B: rollback Order and Product changes
```

### 20.1. @Version cần được mọi writer tôn trọng

Các write paths dùng native SQL/bulk JPQL có thể bỏ qua automatic version checking. Nếu job kho cập nhật stock trực tiếp, phải có cơ chế đồng bộ/locking/version policy chung.

### 20.2. Không chỉ dựa vào CHECK stock>=0

Một lost-update race có thể làm hai đơn “đặt thành công” trong khi stock cuối cùng bằng 0. CHECK chỉ chặn số âm, không chứng minh không oversell nếu các writers làm overwrite. Version/locking/atomic update mới giải quyết concurrency contract.

### 20.3. Một lựa chọn khác: pessimistic lock

Có thể load Product bằng `LockModeType.PESSIMISTIC_WRITE` để khóa row trước check. Với nhiều sản phẩm, nên lấy locks theo thứ tự Product ID ổn định để giảm deadlocks. Kiểm trên DBMS mục tiêu.

### 20.4. Một lựa chọn khác: conditional UPDATE

```sql
UPDATE products
SET stock_quantity = stock_quantity - :qty,
    version = version + 1
WHERE id = :id
  AND active = TRUE
  AND stock_quantity >= :qty;
```

Affected rows = 1 nghĩa stock được trừ; 0 nghĩa không đủ hàng, inactive hoặc không có Product. Nhưng bulk/native update cần xử lý sync với managed entities và versioned JPA state; không trộn bừa với first-level cache.

### 20.5. Retry đúng cách

Khi optimistic conflict xảy ra, rollback transaction, tạo persistence context mới, load lại trạng thái và retry use case có giới hạn nếu phù hợp. Không tiếp tục làm việc trên context/transaction đã lỗi.

---

## 21. Root @Version và sửa collection con

`@Version` trên CustomerOrder thường giúp bảo vệ cập nhật chính row Order. Nhưng khi chỉ sửa `OrderItem.quantity` hoặc thêm Item (owning FK ở child), **không nên mặc định** root version tự tăng trong mọi provider/mapping.

### 21.1. Tại sao phải quan tâm?

Hai clients cùng đọc Order DRAFT phiên bản 3. A sửa quantity, B thêm Product. Nếu cả hai writes không chạm root version, ứng dụng có thể không phát hiện hai thao tác dựa trên một trạng thái cũ.

### 21.2. OPTIMISTIC_FORCE_INCREMENT

Một cách biểu diễn aggregate-level locking:

```java
em.lock(
    order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
```

Nó yêu cầu version của Order được tăng theo provider/transaction semantics, giúp phát hiện concurrent edits. Phải có integration test để xác minh behavior của stack cụ thể.

### 21.3. Không phải mọi thao tác đều cần lock giống nhau

Đọc đơn có thể dùng read-only query. Place vừa sửa Order vừa sửa Products, cần hợp đồng concurrency rõ. Các child-edit APIs có thể dùng ETag/version optimistic checks.

---

## 22. Truy vấn danh sách Orders của Customer

Đừng tải `Customer.orders` thành collection khổng lồ chỉ để hiển thị 20 đơn. Dùng JPQL projection/repository query.

```java
package demo.shop.readmodel;

import demo.shop.domain.OrderStatus;
import java.time.Instant;

public record OrderCard(
    Long id,
    String orderNumber,
    OrderStatus status,
    Instant createdAt,
    Long itemCount
) {}
```

JPQL:

```jpql
SELECT NEW demo.shop.readmodel.OrderCard(
    o.id,
    o.orderNumber,
    o.status,
    o.createdAt,
    COUNT(i.id)
)
FROM CustomerOrder o
LEFT JOIN o.items i
WHERE o.customer.id = :customerId
GROUP BY
    o.id,
    o.orderNumber,
    o.status,
    o.createdAt
ORDER BY o.createdAt DESC, o.id DESC
```

### 22.1. Vì sao không fetch Items?

Danh sách chỉ cần Order data và itemCount. ORM không cần hydrate toàn bộ Item entities.

### 22.2. Count itemCount khác tổng quantity và total

`COUNT(i.id)` đếm dòng, không phải số đơn vị hay tiền. `SUM(quantity)` cũng không bằng số dòng. API phải gọi tên trường đúng.

### 22.3. Pagination

Áp pagination ở parent/group level, không trên fetch join rows. Với query phức tạp, có thể query page Order IDs trước rồi aggregate counts theo IDs.

### 22.4. Authorization

`customerId` trong WHERE phải được xác minh gắn với authenticated principal hoặc quyền quản trị. Query đúng về SQL chưa đủ để bảo vệ dữ liệu.

---

## 23. Truy vấn chi tiết một Order

Một JPQL fetch đúng một collection:

```jpql
SELECT DISTINCT o
FROM CustomerOrder o
LEFT JOIN FETCH o.items
WHERE o.id = :orderId
```

Đối với order detail, `getItems()` đã initialized; dùng Item snapshot fields để dựng response. Nếu cần Product hiện tại, có thể fetch to-one hoặc dùng truy vấn riêng.

### 23.1. Không cần Product để hiển thị lịch sử

`item.getSkuSnapshot()`, `getNameSnapshot()` và `getUnitPrice()` đã đủ; đọc `getProduct().getName()` vừa có thể gây N+1, vừa hiển thị tên mới sai nghiệp vụ.

### 23.2. Tránh trả entity trực tiếp từ controller

Quan hệ hai chiều Order ↔ Item có thể gây vòng lặp serialization; LAZY associations có thể gây lỗi khi transaction đóng. Map sang DTO trong service.

### 23.3. Tránh fetch join nhiều sibling collections

Nếu sau này Order có cả Items và Shipments, JOIN FETCH cả hai có thể nhân rows theo `items × shipments` hoặc gặp Hibernate multiple-bag limitation. Chọn fetch plan theo cardinality.

---

## 24. Phân trang đúng với Order + Items

Sai về ý tưởng:

```jpql
SELECT o
FROM CustomerOrder o
LEFT JOIN FETCH o.items
ORDER BY o.createdAt DESC
```

rồi áp `setMaxResults(20)` và mong 20 Orders mà không xét collection fetch. Provider có thể cảnh báo, paginate trong memory hoặc không thể áp SQL LIMIT trực tiếp vào parent count.

**Giải pháp hai pha:**

1. Query page IDs:

```jpql
SELECT o.id
FROM CustomerOrder o
WHERE o.customer.id = :customerId
ORDER BY o.createdAt DESC, o.id DESC
```

2. Fetch graph cho đúng page IDs:

```jpql
SELECT DISTINCT o
FROM CustomerOrder o
LEFT JOIN FETCH o.items
WHERE o.id IN :orderIds
```

3. Phục hồi thứ tự Java list theo `orderIds` — SQL `IN` không giữ order mặc định.
4. Viết count query riêng cho parent Orders:

```jpql
SELECT COUNT(o)
FROM CustomerOrder o
WHERE o.customer.id = :customerId
```

### 24.1. Tránh N+1

Nếu DTO list chỉ cần counts, dùng COUNT/GROUP BY, không gọi `order.getItems().size()` trong vòng lặp trên nhiều Orders. Với detail đơn, fetch một collection đúng use case.

### 24.2. Stable sort

`ORDER BY createdAt DESC, id DESC` có ID tie-breaker khi nhiều Orders cùng timestamp.

---

## 25. DTO cho API

```java
package demo.shop.readmodel;

import demo.shop.domain.OrderStatus;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderItemResponse(
    Long id,
    int lineNumber,
    String sku,
    String name,
    int quantity,
    BigDecimal unitAmount,
    String currency,
    BigDecimal lineTotal
) {}

public record OrderResponse(
    Long id,
    String orderNumber,
    OrderStatus status,
    Instant createdAt,
    Instant placedAt,
    BigDecimal totalAmount,
    String currency,
    List<OrderItemResponse> items
) {}
```

Các public records nên được đặt ở các file tương ứng khi dùng Java source thật.

### 25.1. DTO bảo vệ contract

Chọn đúng fields client được phép đọc; không expose toàn bộ entity graph, internal version, Customer email hoặc Product stock nếu không cần.

### 25.2. Dùng snapshots khi dựng item response

`sku` và `name` lấy từ `OrderItem.skuSnapshot/nameSnapshot`, không lấy từ Product hiện tại.

### 25.3. Decimal serialization

Nếu API cần số tiền chính xác, phải thống nhất cách biểu diễn BigDecimal/currency và xử lý phía JavaScript/client; không dựa trên floating-point arithmetic cho business totals.

---

## 26. Index theo workload

Các indexes trong migration hỗ trợ:

- Tìm Customer bằng email.
- Tìm Product bằng SKU.
- Tìm Order bằng orderNumber.
- Danh sách Orders theo customer/createdAt/id.
- Load Items theo order_id.
- Thống kê Items theo product_id.

### 26.1. FK không phải lúc nào tự có index

Một số DBMS không tự tạo index cho mọi referencing FK column; thiết kế index theo queries/joins thật.

### 26.2. Đừng đánh giá chỉ từ annotations

Dùng `EXPLAIN` hoặc execution plan trên target DB khi data đủ lớn. Index cải thiện access, không tự sửa query N+1 hoặc row multiplication.

---

## 27. Customer/Product ngừng hoạt động

### 27.1. Customer deactivate

Dùng `customer.deactivate()`; Orders trước đó vẫn giữ customer_id.

### 27.2. Product deactivate

Không thêm vào Order mới. OrderItem cũ vẫn có product_id và snapshots.

### 27.3. Hard delete cần policy

Không chỉ gọi `em.remove(product)` khi có Items. FK có thể chặn; nếu muốn xóa catalog nhưng giữ lịch sử cần cơ chế retention/anonymization, snapshot-only refs hoặc thiết kế schema tương ứng.

### 27.4. Không cascade delete lịch sử

`CascadeType.REMOVE` từ OrderItem→Product hoặc Customer→Orders có thể phá dữ liệu giao dịch hàng loạt.

---

## 28. Order total và derived data

`CustomerOrder.total()` cộng `OrderItem.lineTotal()` theo unit-price snapshots:

\[
Total = \sum_{i=1}^{n} Quantity_i \times UnitPriceSnapshot_i
\]

Với Order ví dụ:

\[
2 \times 19.50 + 1 \times 25.00
= 64.00\ \mathrm{USD}
\]

### 28.1. Có nên lưu total_amount trong CustomerOrder?

Nếu list/report dùng nhiều, có thể lưu total snapshot. Nhưng điều đó tạo **dữ liệu dẫn xuất cần đồng bộ** khi Items chỉnh trong DRAFT. Với mô hình đơn giản, tính từ Items giúp tránh drift. Một Order đã PLACED có thể cần immutable recorded totals, discount/tax snapshots theo yêu cầu hóa đơn.

### 28.2. Không dùng Product.currentPrice để tính

Giá hiện tại biến động; total giao dịch lịch sử phải dựa trên snapshot.

### 28.3. Currency là thành phần của số tiền

Một Order hỗn hợp currencies không thể chỉ SUM amount và coi là total. Chọn policy một currency hoặc snapshot tỷ giá.

---

## 29. Kiểm thử quy tắc miền không DB

```java
package demo.shop.domain;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.*;

class CustomerOrderDomainTest {

    static Money usd(String value) {
        return new Money(
            new BigDecimal(value), "USD");
    }

    static Customer customer() {
        return new Customer(
            "buyer@example.com", "Buyer");
    }

    static Product product(String sku,
                           String price, int stock) {
        return new Product(
            sku, sku, usd(price), stock);
    }

    @Test
    void cannotPlaceEmptyOrder() {
        CustomerOrder order = new CustomerOrder(
            "ORD-01", customer(), Instant.EPOCH);

        assertThrows(
            IllegalStateException.class,
            () -> order.place(Instant.EPOCH));

        assertEquals(
            OrderStatus.DRAFT, order.getStatus());
    }

    @Test
    void historicalTotalUsesSnapshotPrice() {
        CustomerOrder order = new CustomerOrder(
            "ORD-02", customer(), Instant.EPOCH);

        Product book = product(
            "BOOK", "19.50", 10);

        Product mouse = product(
            "MOUSE", "25.00", 10);

        order.addItem(book, 2);
        order.addItem(mouse, 1);

        book.changePrice(usd("99.00"));

        assertEquals(
            usd("64.00"), order.total());
    }

    @Test
    void rejectsDuplicateProduct() {
        CustomerOrder order = new CustomerOrder(
            "ORD-03", customer(), Instant.EPOCH);

        Product book = product(
            "BOOK", "10.00", 10);

        order.addItem(book, 1);

        assertThrows(
            IllegalArgumentException.class,
            () -> order.addItem(book, 2));
    }

    @Test
    void placedOrderCannotBeEdited() {
        CustomerOrder order = new CustomerOrder(
            "ORD-04", customer(), Instant.EPOCH);

        Product book = product(
            "BOOK", "10.00", 10);

        OrderItem item = order.addItem(book, 1);
        order.place(Instant.EPOCH);

        assertThrows(
            IllegalStateException.class,
            () -> order.removeItem(item));
    }

    @Test
    void cannotReserveMoreThanStock() {
        Product p = product("P", "2.00", 1);

        assertThrows(
            IllegalStateException.class,
            () -> p.reserveStock(2));

        assertEquals(1, p.getStockQuantity());
    }
}
```

### 29.1. Unit tests chứng minh

State transitions, price snapshot, duplicate Product policy và stock check trong memory.

### 29.2. Unit tests không chứng minh

JPA FK/cascade, generated IDs, database constraints, concurrency hay transaction rollback. Đó là phần của integration tests.

---

## 30. JPA round-trip test

Một test dùng `EntityManager` thật:

```java
@Test
void persistsOrderAndItems() {
    Customer customer =
        new Customer("c@example.com", "Customer");

    Product product = new Product(
        "SKU-001", "Book",
        new Money(new BigDecimal("10.00"), "USD"),
        5
    );

    em.persist(customer);
    em.persist(product);

    CustomerOrder order = new CustomerOrder(
        "ORD-ROUNDTRIP",
        customer,
        Instant.parse("2026-11-15T00:00:00Z")
    );

    OrderItem item = order.addItem(product, 2);

    em.persist(order);
    em.flush();

    Long orderId = order.getId();
    Long itemId = item.getId();

    assertNotNull(orderId);
    assertNotNull(itemId);

    em.clear();

    CustomerOrder loaded =
        em.find(CustomerOrder.class, orderId);

    assertNotNull(loaded);
    assertEquals(1, loaded.getItems().size());

    OrderItem restored =
        loaded.getItems().get(0);

    assertEquals(
        "SKU-001", restored.getSkuSnapshot());

    assertEquals(
        new Money(new BigDecimal("10.00"), "USD"),
        restored.getUnitPrice());

    assertEquals(
        orderId, restored.getOrder().getId());
}
```

### 30.1. Vì sao flush/clear/find?

`em.find` trong cùng persistence context có thể trả object đã managed, không chứng minh round-trip. Clear loại khỏi first-level cache; nếu cần chắc chắn DB physical columns, dùng thêm SQL assertions/cache instrumentation.

### 30.2. Có thể dùng @DataJpaTest

Spring Boot slice thường rollback test transaction sau test. Đừng nhầm rollback mặc định với đã test commit visibility. Nếu cần concurrency/multiple transactions, dùng harness phù hợp.

### 30.3. Dùng target DBMS

H2 có thể chạy smoke tests, nhưng migrations/locking/numeric precision/identity behavior cần kiểm PostgreSQL (hoặc DBMS triển khai) bằng Testcontainers/CI.

---

## 31. Test orphanRemoval

Quy trình:

1. Persist Customer, Product và Order với một Item.
2. Flush, lưu IDs.
3. Clear persistence context.
4. Find managed Order.
5. Gỡ Item qua `order.removeItem(item)` khi Order còn DRAFT.
6. Flush rồi clear.
7. `em.find(OrderItem.class,itemId)` phải null.
8. `em.find(Product.class,productId)` phải vẫn tồn tại.
9. `em.find(Customer.class,customerId)` phải vẫn tồn tại.

### 31.1. Test Java List giảm size không đủ

Nó không chứng minh DB DELETE orphan row. Cần chạy provider thực, flush/clear và query lại.

### 31.2. Test rule khi PLACED riêng

Unit test phải chứng minh `removeItem` ném lỗi khi Order không còn DRAFT.

---

## 32. Test snapshot sau catalog update

Đây là một trong những kiểm thử quan trọng nhất:

1. Persist Product giá 19.50 USD, tên "JPA Book".
2. Tạo Order và Item snapshot giá/tên.
3. Flush/commit.
4. Transaction khác đổi Product price thành 22.00, tên thành "JPA Book 2".
5. Reload Item từ database.
6. Assert Item.unitPrice=19.50 và nameSnapshot="JPA Book".
7. Reload Product để assert catalog price=22.00, name="JPA Book 2".

Nếu code chỉ tính total từ Product.currentPrice, test sẽ phát hiện số tiền lịch sử bị trôi.

---

## 33. Test cạnh tranh tồn kho

Kịch bản:

```text
Product #1: stock=1, version=0

Transaction A:
  load Product #1
  reserveStock(1)

Transaction B:
  load Product #1
  reserveStock(1)

Transaction A:
  flush/commit succeeds

Transaction B:
  flush/commit optimistic conflict
  rollback

Final DB:
  Product stock=0
  exactly one successful placed order
```

### 33.1. Cần hai persistence contexts/transactions

Hai `em.find(Product.class,id)` trong cùng EntityManager thường trả cùng managed instance, không mô phỏng hai clients độc lập.

### 33.2. Seed phải đã commit

Nếu data seed chưa commit trong test-level rollback transaction, transaction B có thể không nhìn thấy Product. Dùng explicit transactions/TestTransaction/TransactionTemplate phù hợp.

### 33.3. Kiểm đúng root cause

Không bắt mọi RuntimeException rồi coi test pass; kiểm optimistic locking conflict theo provider/DB stack và state cuối.

### 33.4. Transaction thua phải rollback Order status

Không được có Order PLACED nếu tồn kho không được trừ thành công.

---

## 34. Test database constraints

| Constraint | Negative test |
|---|---|
| customers.email UNIQUE | Hai customers cùng normalized email |
| products.sku UNIQUE | Hai Products cùng SKU |
| orders.order_number UNIQUE | Hai Orders cùng orderNumber |
| items(order_id,product_id) UNIQUE | Hai dòng cùng product trong một Order |
| items.quantity > 0 | Insert quantity=0 |
| products.stock_quantity >= 0 | Update stock=-1 |
| products.price_amount >= 0 | Insert price âm |
| item FK product_id | Item trỏ Product không tồn tại |
| item FK order_id | Item trỏ Order không tồn tại |
| order status/placedAt CHECK | PLACED nhưng placed_at null |

### 34.1. Bypass domain validation khi kiểm DB constraint

Nếu Product constructor đã cấm giá âm, có thể dùng native SQL trong isolated test để kiểm CHECK riêng; không sửa domain code cho phép giá âm chỉ để tạo fixture.

### 34.2. PostgreSQL SQL error làm transaction bị aborted

Rollback trước test assertions tiếp theo; kiểm SQLState/constraint name thay vì catch exception chung.

### 34.3. Annotation không tự tạo constraint trong migration-driven schema

`@Column(unique=true)` là metadata; khi production dùng migrations, phải có UNIQUE SQL thực tế.

---

## 35. Kiểm soát quyền và API

Các endpoints gợi ý:

```text
POST   /orders
POST   /orders/{id}/items
PATCH  /orders/{id}/items/{itemId}
DELETE /orders/{id}/items/{itemId}
POST   /orders/{id}/place
GET    /orders/{id}
GET    /customers/{id}/orders?page=0&size=20
GET    /products?active=true
```

### 35.1. Không tin client-provided IDs mù quáng

Service phải xác minh người dùng có quyền tạo/đọc/sửa Order theo authenticated customer/tenant. Một Order ID hợp lệ không đồng nghĩa có quyền truy cập.

### 35.2. Không cho client tự gửi giá thành tiền

Request thêm Item nên chứa productId và quantity; backend xác định unitPrice từ catalog theo price policy. Nếu client tự gửi total mà không kiểm lại, dễ sai hoặc bị lợi dụng.

### 35.3. Chống yêu cầu lặp

`POST /orders` và `POST /orders/{id}/place` cần idempotency semantics rõ. Order number UNIQUE là một lớp dữ liệu, nhưng chưa đủ giải quyết timeout/retry across requests.

### 35.4. Không trả managed entities

Dùng DTO response để kiểm soát serialization, bảo mật, lazy loading và lịch sử snapshot.

---

## 36. Các thay đổi nghiệp vụ và tác động đến thiết kế

| Yêu cầu mới | Hướng thiết kế |
|---|---|
| Voucher/giảm giá | Snapshot discount per item/order |
| Thuế VAT | Snapshot tax rate/amount với rounding policy |
| Nhiều currency | Exchange rate snapshot và rule chuyển đổi |
| Thanh toán | Payment entity, state machine, idempotency |
| Giao nhiều kiện | Shipment/ShipmentItem và allocation |
| Nhiều kho | Inventory/Warehouse/Reservation |
| Hủy sau PLACED | Compensation/restock/refund workflow |
| Trả hàng | Return/Refund records, không sửa lịch sử gốc |
| Guest checkout | Customer reference optional hoặc guest snapshot theo policy |
| Xóa PII | Anonymization/retention architecture |
| Một Product nhiều dòng | Thay unique và duplicate rule |
| Product soft delete | active flag/catalog status |
| Order total cache | Denormalized snapshot + consistency policy |
| Multi-tenant | Tenant key, authorization, composite indexes |

### 36.1. Đừng chỉ thêm column rồi bỏ qua migration

Mỗi thay đổi schema cần data/backfill/rollout plan, nhất là khi production đã có Orders lịch sử.

---

## 37. Lộ trình thực hành

1. Ghi rõ use cases và các invariants trước khi viết JPA.
2. Vẽ ERD với bốn entities, cardinalities và PK/FK.
3. Đặt business keys/UNIQUE theo policy.
4. Viết Money value object và domain unit tests.
5. Viết Customer/Product với active và version.
6. Viết OrderItem chứa quantity/price/name/SKU snapshots.
7. Viết CustomerOrder làm aggregate root.
8. Định nghĩa DRAFT/PLACED và các operations cho Items.
9. Viết migration SQL và indexes.
10. Seed Customers/Products/Orders.
11. Viết service tạo DRAFT, thêm/sửa/gỡ Items và place.
12. Thêm optimistic/pessimistic concurrency policy.
13. Viết DTO list/detail queries, phân trang đúng parent.
14. Kiểm thử mapping/constraints trên DB target.
15. Thử đồng thời hai khách mua sản phẩm cuối cùng.
16. Viết một trang giải thích trade-offs và hướng mở rộng.

---

## 38. Bài tập A — Vẽ ERD

Cho Customer A có 3 Orders; Order #1 có 2 Items, Order #2 có 5 Items, Order #3 rỗng. Product P xuất hiện ở cả Order #1 và #2.

Yêu cầu:

1. Vẽ cardinality.
2. Xác định bảng và foreign keys.
3. Giải thích vì sao Product P không bị xóa khi Order #1 xóa Item.
4. Giải thích Order #3 có thể DRAFT nhưng không thể PLACED.
5. Chỉ ra nơi lưu quantity và unit price snapshot.

---

## 39. Bài tập B — Chuyển ManyToMany sang OrderItem

Một developer viết `@ManyToMany Set<Product>` trong Order.

1. Nêu thiếu dữ liệu gì.
2. Tạo entity OrderItem.
3. Chọn surrogate ID hay composite key và giải thích.
4. Thiết lập FK order_id, product_id.
5. Thêm quantity, lineNumber và snapshots.
6. Thiết kế UNIQUE per Order/Product.
7. Xác định owning side và cascade.

---

## 40. Bài tập C — Giá lịch sử

1. Tạo Product giá 10 USD.
2. Tạo Order DRAFT và mua 2.
3. Xác nhận Item snapshot 10.
4. Đổi catalog price thành 20.
5. Order total phải giữ 20 USD, không thành 40.
6. Flush/clear/find, kiểm lại.
7. Giải thích khi nào có thể reprice DRAFT.
8. Đề xuất snapshot discount/tax nếu có.

---

## 41. Bài tập D — Cascade và orphanRemoval

1. Persist Order có hai Items.
2. Kiểm Item IDs được sinh qua cascade.
3. Reload Order từ persistence context mới.
4. Gỡ một Item khi DRAFT.
5. Flush/clear.
6. Item đã gỡ không còn trong DB.
7. Product và Customer vẫn tồn tại.
8. Thử xóa Item khi PLACED và xác nhận domain từ chối.
9. Phân biệt cascade REMOVE và DB ON DELETE CASCADE.

---

## 42. Bài tập E — Stock concurrency

1. Product có stock=2.
2. Order A place mua 2, thành công.
3. Order B mua 1 phải thất bại.
4. Kiểm A PLACED, B vẫn DRAFT, stock=0.
5. Lặp với hai transactions đọc stock=1 cùng lúc.
6. Dùng @Version chống lost update.
7. Dùng PESSIMISTIC_WRITE trong thí nghiệm khác.
8. Đo behavior trên PostgreSQL Testcontainers.
9. Đảm bảo rollback transaction thua.
10. Đề xuất retry policy.

---

## 43. Bài tập F — Domain negative cases

1. Customer email rỗng bị từ chối.
2. Product SKU rỗng bị từ chối.
3. Money âm bị từ chối.
4. Quantity 0 hoặc âm bị từ chối.
5. Trùng Product trong cùng Order bị từ chối.
6. Trộn currency bị từ chối.
7. Place đơn rỗng bị từ chối.
8. Sửa PLACED Order bị từ chối.
9. Thêm Product inactive bị từ chối.
10. Tạo Order cho Customer inactive bị từ chối.
11. Sau exception, object state vẫn đúng.

---

## 44. Bài tập G — DB constraints

1. Insert hai Products cùng SKU.
2. Insert hai Orders cùng orderNumber.
3. Insert Item quantity=0 bằng native SQL.
4. Insert Product stock=-1 bằng native SQL.
5. Insert Item có order_id không tồn tại.
6. Insert hai Item rows trùng (order_id,product_id).
7. Kiểm đúng constraint/root cause.
8. Rollback failed transaction và cleanup.
9. So sánh domain validation với DB guardrails.

---

## 45. Bài tập H — Query và pagination

1. Seed 100 Orders, mỗi Order 5 Items.
2. Query 20 Orders một trang.
3. Dùng DTO itemCount thay vì load all Items.
4. Viết order detail query fetch một collection.
5. Quan sát số SQL statements.
6. Thử JOIN FETCH Items với pagination và ghi rủi ro.
7. Chuyển sang ID-first two-phase fetch.
8. Reorder results theo page IDs.
9. Dùng count query riêng.
10. Đảm bảo không lộ Orders của Customer khác.

---

## 46. Bài tập I — Chống duplicate request

1. Client gửi POST create order.
2. Server commit nhưng response bị timeout.
3. Client retry cùng idempotency key.
4. Thiết kế server trả lại Order đã tạo.
5. DB UNIQUE bảo vệ trùng orderNumber.
6. Kiểm race khi hai requests cùng idempotency key.
7. Định nghĩa trạng thái request pending/completed nếu cần.
8. Giải thích khác biệt giữa uniqueness và idempotency.

---

## 47. Bài tập J — Migration mở rộng

Yêu cầu mới cho phép cùng Product có nhiều dòng theo warehouse.

1. Phân tích UNIQUE(order_id,product_id) hiện tại.
2. Đề xuất thêm warehouse_id.
3. Định nghĩa unique mới theo nghiệp vụ.
4. Thay domain duplicate policy.
5. Viết versioned migration.
6. Test upgrade với Orders cũ có data.
7. Kiểm snapshots không thay đổi.
8. Đánh giá backward compatibility khi rolling deploy.

---

## 48. Bài tập K — API DTO

1. Thiết kế CreateOrderRequest.
2. Thiết kế AddItemRequest chỉ gồm productId và quantity.
3. Thiết kế OrderCard/OrderResponse.
4. Hiển thị Product snapshots từ Item.
5. Không expose JPA entity graph trực tiếp.
6. Kiểm authorization theo authenticated Customer.
7. Định nghĩa out-of-stock, conflict và not-found errors.
8. Xử lý stale optimistic version.
9. Đặt transaction boundary cho writes.

---

## 49. Bài tập L — Báo cáo thiết kế

Một bài nộp nên có:

- ERD và bảng cardinality.
- Domain rules, state machine.
- Code Money/Customer/Product/Order/Item.
- JPA mappings và owning sides.
- Migrations SQL, FK/UNIQUE/CHECK.
- Service đặt đơn với concurrency policy.
- DTO queries và pagination strategy.
- Unit tests và JPA round-trip tests.
- Test price snapshot.
- Test hai transactions tranh tồn kho.
- Tài liệu giải thích vì sao không dùng @ManyToMany trực tiếp.

---

## 50. Những lỗi phổ biến

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| @ManyToMany trực tiếp | Thiếu quantity/price | OrderItem entity |
| Tính total từ Product.currentPrice | Lịch sử tiền đổi | Snapshot unit price |
| Không snapshot tên/SKU | Hóa đơn cũ đổi theo catalog | Item snapshots |
| Cascade REMOVE Product | Xóa catalog dùng chung | Không cascade Product |
| Cascade REMOVE Customer | Mất khách/hồ sơ lịch sử | Không cascade Customer |
| Không set owning side order | FK sai/NULL | Constructor/helper |
| Cho sửa PLACED | Sai lịch sử và tồn kho | State machine |
| Dùng double cho tiền | Sai số | BigDecimal/Money |
| Không kiểm currency | Tổng tiền vô nghĩa | Single currency/FX policy |
| Chỉ @Transactional cho stock | Oversell có thể xảy ra | Version/locks |
| Root @Version nhưng child edits không có policy | Concurrent edits lost | Force increment/locks |
| Chỉ CHECK stock>=0 | Không đủ chống lost update | Concurrency contract |
| Chỉ @Column(unique=true) nhưng quên migration | Production không có UNIQUE | DDL migration |
| items.size()+1 line number | Va chạm sau xóa | max+1/ordering policy |
| Fetch tất cả Items khi list Orders | Overfetch/N+1 | DTO query |
| Paginate collection fetch | Page sai/in-memory | Page IDs trước |
| Không ORDER BY tie-breaker | Trang không ổn định | createdAt + id |
| Trả entities qua REST | Cyclic JSON/LAZY | DTO |
| Xóa Product khi ngừng bán | FK/history issues | Deactivate |
| Test chỉ in-memory | Không chứng minh SQL | flush/clear/find |
| Test chỉ H2 create-drop | Che migration lỗi | Target DB+Flyway |
| Catch mọi RuntimeException khi concurrency | False green | Kiểm root cause |
| API tin customerId tùy ý | Lộ dữ liệu | Authorization |

---

## 51. Checklist trước khi hoàn thành

| Tiêu chí | Đánh giá |
|---|---|
| Đúng bốn entities Customer, CustomerOrder, OrderItem, Product? | Có |
| Cardinality và foreign keys rõ? | Có |
| OrderItem có business fields? | Có |
| Không dùng @ManyToMany để bỏ qua quantity/price? | Có |
| Product/Customer được dùng chung, không cascade REMOVE? | Có |
| Order quản lý vòng đời Items? | Có |
| Owning side order/product được set đúng? | Có |
| Money có amount và currency? | Có |
| Giá/SKU/tên được snapshot? | Có |
| DRAFT/PLACED invariants rõ? | Có |
| Chỉ DRAFT có quyền sửa Items? | Có |
| Không trùng Product theo policy? | Domain + UNIQUE |
| Quantity và stock đúng? | Domain + DB |
| Place và stock trong một transaction? | Có |
| Đồng thời đặt đơn được xử lý bằng version/lock? | Có |
| Root version policy cho child edits? | Có |
| Không dùng generated ID làm timestamp? | Có |
| Migrations là nguồn schema production? | Có |
| List endpoint dùng DTO/page? | Có |
| Detail fetch theo nhu cầu? | Có |
| Không paginate trực tiếp trên to-many fetch? | Có |
| Unit tests bảo vệ domain? | Có |
| Integration tests có flush/clear/find? | Có |
| Snapshot test sau price change? | Có |
| Concurrency test hai transactions? | Có |
| API kiểm authorization? | Có |
| Idempotency policy rõ? | Có |
| Hướng mở rộng tax/shipping/payment đã được nêu? | Có |

---

## 52. Những ngộ nhận cần tránh

### 52.1. “Quan hệ N:N thì cứ gắn @ManyToMany”

Không nếu mối quan hệ mang quantity, price và snapshot. OrderItem là một entity.

### 52.2. “Product.currentPrice chính là giá đơn hàng”

Không. Giá trên OrderItem là giá giao dịch theo policy thời điểm chụp.

### 52.3. “Cascade ALL mọi nơi tiện hơn”

Có thể xóa Customer/Product dùng chung. Cascade phải theo lifecycle ownership.

### 52.4. “mappedBy là phía viết FK”

Không. Đây là inverse side; OrderItem.order giữ `order_id`.

### 52.5. “@Version trên Order tự bắt mọi thay đổi Item”

Không luôn luôn. Cần aggregate concurrency policy cho child-only updates.

### 52.6. “@Transactional tự chống oversell”

Không. Transaction cho atomicity, nhưng race cần version/lock/conditional update.

### 52.7. “CHECK stock>=0 đủ chống bán quá kho”

Không nếu lost updates khiến hai giao dịch đều thành công trên cùng snapshot cũ.

### 52.8. “OrderItem chỉ cần product_id, không cần snapshot”

Không. Catalog thay đổi; dữ liệu giao dịch phải ổn định.

### 52.9. “Cùng Product không bao giờ được ở hai dòng”

Đó là policy của phiên bản bài này. Với nhiều warehouse/discount, policy có thể đổi và cần migration.

### 52.10. “Một Order mới lúc nào cũng phải có Items”

Bài cho phép DRAFT rỗng, chỉ PLACED phải có Items.

### 52.11. “Xóa Product inactive là bình thường”

Có thể phá FK/history. Deactivate thường phù hợp hơn cho transactional records.

### 52.12. “JPA entity là response DTO hoàn chỉnh”

Không. Entity graph có lazy loads, cycles, fields nội bộ và có thể rò dữ liệu.

### 52.13. “Flush là commit”

Không. Flush đồng bộ SQL nhưng transaction có thể rollback.

### 52.14. “H2 test pass là đủ cho PostgreSQL production”

Không. Dialect/migrations/concurrency/constraints cần test target DBMS.

---

## 53. Câu hỏi ôn tập

1. Bốn thực thể chính của mô hình là gì?
2. Customer–Order, Order–Item và Item–Product có cardinality gì?
3. Vì sao OrderItem không chỉ là join table?
4. Khi nào @ManyToMany trực tiếp là không phù hợp?
5. Quantity và unitPrice thuộc entity nào?
6. Vì sao Product.price không dùng tính total của Order cũ?
7. Vì sao nên snapshot SKU và Product name?
8. Một Customer có thể có nhiều Orders nhưng Customer.orders có bắt buộc không?
9. Vì sao Product không có cascade REMOVE từ Item?
10. Vì sao Customer không có cascade REMOVE từ Order?
11. Phía nào ghi order_id?
12. mappedBy="order" có vai trò gì?
13. Cascade và orphanRemoval khác database ON DELETE CASCADE thế nào?
14. Surrogate ID khác composite key trên Item ở đâu?
15. UNIQUE(order_id,product_id) thể hiện business policy gì?
16. Khi nào phải thay unique này?
17. Vì sao lineNumber không dựa items.size()+1?
18. @OrderBy khác @OrderColumn ra sao?
19. BigDecimal/Money giải quyết vấn đề gì?
20. Vì sao Money phải có currency?
21. Có nên dùng scale 2 cho mọi loại tiền không?
22. DRAFT rỗng có hợp lệ không?
23. PLACED rỗng có hợp lệ không?
24. Vì sao không sửa Item sau khi place?
25. Place cần thay đổi những entities nào?
26. Vì sao phải cùng transaction khi trừ stock?
27. Hai khách cùng mua sản phẩm cuối cùng gây race thế nào?
28. @Version trên Product phát hiện xung đột ra sao?
29. Root @Version có đủ cho child-only edits không?
30. Khi nào dùng OPTIMISTIC_FORCE_INCREMENT?
31. Khi nào chọn PESSIMISTIC_WRITE?
32. SQL conditional stock update có ưu điểm gì?
33. Tại sao native bulk writes phải tuân version policy?
34. Business key orderNumber khác ID kỹ thuật ra sao?
35. Idempotency khác UNIQUE constraint thế nào?
36. Vì sao nên deactivate Product?
37. Vì sao nên deactivate Customer?
38. Cần permission checks nào ở API?
39. Vì sao không nhận total từ client rồi tin ngay?
40. Vì sao list Orders nên dùng DTO/COUNT?
41. N+1 xuất hiện khi nào?
42. Vì sao pagination trên collection fetch nguy hiểm?
43. Page IDs trước giải quyết vấn đề gì?
44. SQL IN có bảo đảm thứ tự input IDs không?
45. Vì sao cần ORDER BY id tie-breaker?
46. JPA integration test khác domain unit test ra sao?
47. Vì sao cần flush/clear/find?
48. Cần test gì khi Product đổi giá?
49. Concurrent stock test cần bao nhiêu persistence contexts?
50. Khi thêm payment/warehouse/discount, schema và invariants nào cần đổi?

---

## 54. Tổng kết

| Quyết định | Lý do |
|---|---|
| CustomerOrder là aggregate root | Bảo vệ vòng đời đơn và Items |
| OrderItem entity riêng | Có quantity, lineNumber, price snapshots |
| Customer/Product độc lập | Dùng chung, không cascade REMOVE |
| @ManyToOne phía Item giữ FK | Quan hệ hai chiều mapping chính xác |
| Money với BigDecimal | Tính tiền có currency, tránh double |
| Snapshot giá/tên/SKU | Giữ lịch sử bất biến khi catalog đổi |
| DRAFT/PLACED state machine | Không sửa giao dịch đã chốt |
| Stock reserve trong transaction | Atomic Order + Product updates |
| @Version/locking | Phát hiện tranh chấp tồn kho |
| UNIQUE/CHECK/FK ở DB | Bảo vệ tất cả write paths |
| DTO cho list/detail | Giảm overfetch, tránh serialization issues |
| ID-first pagination | Phân trang parent đúng |
| Flyway/Liquibase migrations | Kiểm soát schema production |
| Domain + JPA + concurrency tests | Chứng minh đúng nhiều tầng |

### Sơ đồ quyết định

```text
                 THIẾT KẾ ĐƠN HÀNG
                         |
                         v
             Quan hệ Order--Product có
              quantity/price/snapshot?
                    /          \
                  CÓ           KHÔNG
                   |              |
                   v              v
            OrderItem entity    Xét N:N
                   |
                   v
           Ai sở hữu lifecycle?
                   |
                   v
          CustomerOrder aggregate
          cascade/orphanRemoval Item
                   |
                   v
         Product và Customer độc lập
         KHÔNG cascade REMOVE
                   |
                   v
           Snapshot price/name/SKU
                   |
                   v
            DRAFT ---- place ----> PLACED
                         |
                         v
             Transaction + stock update
                         |
                         v
                Version/lock policy
                         |
                         v
             DB FK/UNIQUE/CHECK/indexes
                         |
                         v
                DTO queries + tests
```

**Nguyên tắc cuối bài:** Thiết kế JPA nên xuất phát từ **nghiệp vụ và tính bất biến của lịch sử giao dịch**. Customer và Product là những thực thể độc lập; CustomerOrder quản lý vòng đời của OrderItems; mỗi OrderItem mang quantity, price và dữ liệu snapshot nên không thể thay bằng @ManyToMany thuần túy. Các quan hệ cần owning sides/FKs đúng, cascade chỉ trong aggregate phù hợp, và database constraints để bảo vệ dữ liệu từ mọi write path. Việc đặt đơn phải kết hợp domain validation, transaction, optimistic/pessimistic concurrency strategy và tests trên DB thực. Cuối cùng, chọn DTO/pagination/fetch plan đúng cho từng màn hình thay vì tải cả object graph một cách mặc định.

