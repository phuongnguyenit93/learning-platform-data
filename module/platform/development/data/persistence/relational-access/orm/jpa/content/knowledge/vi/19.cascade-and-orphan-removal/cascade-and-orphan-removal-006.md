# Đánh giá phạm vi và rủi ro của `CascadeType.ALL` trong JPA

## 1. Vấn đề: một annotation có thể tác động tới cả đồ thị entity

Trong Jakarta Persistence (JPA), một entity thường có quan hệ với các entity khác. Ví dụ:

```text
Customer
   |
   | đặt
   v
PurchaseOrder
   |
   | có nhiều
   v
OrderLine --------> CatalogProduct
          tham chiếu
```

Một `PurchaseOrder` *sở hữu vòng đời* các `OrderLine` của nó: khi xóa đơn thật sự, các dòng hàng thường không còn ý nghĩa độc lập. Nhưng `CatalogProduct` là dữ liệu danh mục có thể được nhiều đơn hàng sử dụng; xóa đơn **không được xóa sản phẩm**. `Customer` cũng thường tồn tại độc lập với một đơn hàng cụ thể.

JPA hỗ trợ **cascade** để truyền thao tác persistence từ một entity sang các entity được tham chiếu qua quan hệ. Cấu hình:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
```

có nghĩa những thao tác JPA được định nghĩa trong `CascadeType.ALL` có thể được lan truyền từ `PurchaseOrder` tới các `OrderLine` liên quan.

Điều này hữu ích khi hai entity thuộc cùng một vòng đời nghiệp vụ. Nhưng đặt `cascade = CascadeType.ALL` tùy tiện lên các quan hệ khác có thể dẫn đến:

- Xóa ngoài ý muốn các entity **được chia sẻ**.
- Sao chép state cũ từ entity detached vào managed instance.
- Làm mất chỉnh sửa chưa lưu khi refresh cả graph.
- Detach những entity mà code phía sau vẫn kỳ vọng được dirty checking.
- Persist nhầm một entity đã có hoặc đang detached.
- Phát rất nhiều câu SQL và kéo dài transaction.
- Gặp lỗi ràng buộc foreign key, unique hoặc optimistic locking ở thời điểm flush/commit.

**Nguyên tắc trung tâm:** chọn cascade theo **hướng và vòng đời sở hữu thực sự của quan hệ**, không theo số lượng entity có tham chiếu nhau.

Bài học này tập trung đánh giá đầy đủ phạm vi `CascadeType.ALL`, rủi ro của từng thao tác, sự khác biệt với `orphanRemoval` và cách quyết định dùng `ALL` hay chỉ một vài cascade cụ thể.

## 2. Cascade là gì và không phải là gì?

### 2.1. Một thao tác được khởi phát trên một entity

Giả sử:

```java
em.persist(order);
```

Đây là thao tác `persist` khởi phát từ `order`. Nếu quan hệ `order.lines` có `cascade = PERSIST`, provider còn thực hiện thao tác persist trên các `OrderLine` được liên kết và đủ điều kiện theo quy tắc JPA.

Tương tự:

```java
em.remove(order);
```

Nếu `order.lines` có `cascade = REMOVE`, thao tác remove được lan tới các dòng hàng liên quan.

Cascade đi theo **đường liên kết mà annotation cấu hình**, không tự tìm tất cả những bảng SQL có foreign key đến entity.

### 2.2. Cascade không đồng nghĩa quan hệ sở hữu khóa ngoại

Phân biệt:

- **Owning side của quan hệ JPA:** bên quyết định cách ánh xạ foreign key/join table, ví dụ `OrderLine.order` có `@ManyToOne @JoinColumn`.
- **Hướng cascade:** bên được cấu hình truyền thao tác, ví dụ `PurchaseOrder.lines` có `cascade = ALL`.
- **Aggregate ownership của domain:** entity nào có trách nhiệm quản lý vòng đời và invariant của entity khác.

Ba khái niệm có liên quan nhưng không đồng nhất.

Trong quan hệ hai chiều:

```java
// Trong PurchaseOrder: phía inverse.
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
private List<OrderLine> lines;

// Trong OrderLine: phía owning giữ FK.
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private PurchaseOrder order;
```

`PurchaseOrder.lines` là phía **inverse** về metadata FK nhưng vẫn có thể là nơi thích hợp để khai báo cascade từ **aggregate root** tới các dòng phụ thuộc.

### 2.3. Cascade không tự đặt fetch mode

`CascadeType.ALL` **không có nghĩa tự chuyển tất cả quan hệ sang EAGER**. `fetch` quyết định chiến lược tải dữ liệu, còn `cascade` quyết định truyền các thao tác persistence được hỗ trợ.

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    fetch = FetchType.LAZY
)
private List<OrderLine> lines;
```

Cấu hình này hoàn toàn có thể hợp lệ: collection được yêu cầu tải lazy, trong khi các thao tác persist/merge/remove/refresh/detach được cascade theo metadata.

### 2.4. Cascade cũng không tự là `orphanRemoval`

`CascadeType.REMOVE` truyền `remove` khi **xóa entity nguồn**. Còn `orphanRemoval = true` xử lý trường hợp **entity đích bị tách khỏi quan hệ** được cấu hình.

Hai hành vi liên quan nhưng có điều kiện kích hoạt khác nhau. Phần 13 sẽ phân biệt chi tiết.

## 3. `CascadeType.ALL` thực sự bao gồm những thao tác nào?

`CascadeType` chuẩn của Jakarta Persistence gồm các giá trị:

- `PERSIST`
- `MERGE`
- `REMOVE`
- `REFRESH`
- `DETACH`
- `ALL`

`CascadeType.ALL` về ý nghĩa bao gồm **năm thao tác đầu**:

```java
cascade = CascadeType.ALL
```

tương đương về tập thao tác cascade với:

```java
cascade = {
    CascadeType.PERSIST,
    CascadeType.MERGE,
    CascadeType.REMOVE,
    CascadeType.REFRESH,
    CascadeType.DETACH
}
```

Bảng ý nghĩa:

| Cascade | Khi thao tác bắt đầu từ entity nguồn | Rủi ro cần đánh giá |
|---|---|---|
| `PERSIST` | Truyền thao tác persist tới entity đích phù hợp. | Cố persist entity tham chiếu đã tồn tại/detached; lưu object ngoài ý muốn. |
| `MERGE` | Truyền merge state tới entity đích. | Sao chép state detached đã cũ; ghi đè thuộc tính; xung đột version. |
| `REMOVE` | Truyền remove tới entity đích. | Xóa dữ liệu dùng chung; xóa hàng loạt; lỗi foreign key. |
| `REFRESH` | Truyền refresh xuống entity đích. | Làm mất thay đổi local chưa được đồng bộ. |
| `DETACH` | Truyền detach tới entity đích. | Những sửa đổi sau detach không còn được dirty checking tự động ghi. |
| `ALL` | Bao gồm toàn bộ năm cơ chế trên. | Chấp nhận tất cả lợi ích **và** tất cả rủi ro của năm thao tác. |

Đặc biệt, `ALL` **không có nghĩa “tự động làm mọi thứ liên quan tới object graph”**: nó không bao gồm một cơ chế tùy ý như tự gọi `find`, tự load mọi LAZY relationship khi đọc, hay tự gửi event sau commit. Nó chỉ là tập cascade operation được định nghĩa.

### 3.1. Vì sao mặc định không cascade?

Đối với các relationship mapping thông thường, nếu không khai báo `cascade`, mặc định không cascade các thao tác trên. Điều này giúp hành vi độc lập là lựa chọn an toàn trước khi developer cố ý truyền thao tác.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Không có cascade ở đây là một thiết kế hợp lý: xóa một order không làm thay đổi vòng đời `Customer`.

## 4. Hiểu hướng lan truyền qua đồ thị entity

Cascade **có hướng**. Từ entity nguồn, provider đi theo những relationship được khai báo cascade tương ứng.

Giả sử:

```text
                       cascade ALL
          PurchaseOrder -------------> OrderLine
                 |
                 | không cascade
                 v
               Customer

          OrderLine -----------------> CatalogProduct
                    không cascade
```

Khi gọi:

```java
em.remove(order);
```

với giả định `order` đang managed, thao tác remove đi từ order tới các `OrderLine` qua cạnh có `REMOVE`. Nó **không** tự đi tới `Customer` hoặc `CatalogProduct` qua các cạnh không bật cascade.

### 4.1. Cascade có thể lan nhiều tầng

Một chuỗi khác:

```text
Project --ALL--> Task --ALL--> Comment
```

Nếu `em.remove(project)`, thao tác có thể lan tới task, rồi từ task tới comment. Vì vậy, review rủi ro phải xem **đồ thị cascade có thể tới đâu**, không chỉ nhìn một annotation trên field đầu tiên.

### 4.2. Hướng ngược không tự xảy ra

Có cascade ở:

```java
// Project.tasks
@OneToMany(mappedBy = "project", cascade = CascadeType.ALL)
private List<Task> tasks;
```

không mặc nhiên cho phép xóa `Task` làm xóa `Project`. Hướng ngược chỉ xảy ra nếu quan hệ từ `Task` tới `Project` cũng cấu hình cascade liên quan.

**Nguy cơ lớn:** đặt `CascadeType.ALL` ở cả hai hướng cho “đồng bộ” thường khiến graph khó dự đoán, nhất là khi có entity dùng chung. Không cần đặt cascade đối xứng chỉ vì relationship là bidirectional.

## 5. Tư duy aggregate ownership trước khi chọn `ALL`

Một cách đánh giá hiệu quả là coi entity chính như **aggregate root** — nơi quản lý vòng đời của các đối tượng phụ thuộc.

Ví dụ đơn hàng:

```text
PurchaseOrder  [aggregate root]
    |
    +--> OrderLine #1  [phụ thuộc order]
    |
    +--> OrderLine #2  [phụ thuộc order]

PurchaseOrder --> Customer        [entity độc lập]
OrderLine     --> CatalogProduct  [entity chia sẻ]
```

Dù cả `Customer` và `CatalogProduct` đều có foreign key/reference trong object graph, chúng **không thuộc sở hữu vòng đời** của một `PurchaseOrder`.

Các câu hỏi then chốt:

1. Nếu xóa entity nguồn, entity đích có cần bị xóa theo không?
2. Entity đích có thể tồn tại hợp lệ khi entity nguồn không còn không?
3. Có entity khác đang tham chiếu entity đích không?
4. Entity đích có ID, lịch sử, quyền hoặc thao tác quản trị độc lập không?
5. Có chấp nhận merge/refresh/detach đồng thời toàn bộ entity đích với entity nguồn không?
6. Khi tạo entity nguồn, những entity đích có thực sự đều là **new** không?

Nếu câu trả lời chỉ ủng hộ **persist cùng nhau** nhưng không ủng hộ **remove cùng nhau**, không nên chọn `ALL` chỉ vì thuận tiện khi gọi `em.persist(parent)`.

## 6. Một ví dụ tương đối an toàn: `PurchaseOrder` và `OrderLine`

### 6.1. Entity dùng chung: `CatalogProduct`

`CatalogProduct` có identity và vòng đời độc lập với đơn hàng. Một sản phẩm có thể được tham chiếu bởi nhiều đơn.

```java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "catalog_products")
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @Column(name = "sku", nullable = false, unique = true, length = 64)
    private String sku;

    @Column(name = "product_name", nullable = false, length = 160)
    private String productName;

    protected CatalogProduct() {}

    public CatalogProduct(String sku, String productName) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (productName == null || productName.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không hợp lệ");
        }
        this.sku = sku.trim();
        this.productName = productName.trim();
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
```

`CatalogProduct` được tạo và quản lý qua quy trình riêng. Khi tạo order line, ta **tham chiếu** sản phẩm đã tồn tại, không có ý định persist/merge/remove sản phẩm theo vòng đời order line.

### 6.2. Entity phụ thuộc: `OrderLine`

```java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private CatalogProduct product; // KHÔNG cascade.

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    @Column(
        name = "unit_price",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal unitPrice;

    protected OrderLine() {}

    OrderLine(
            PurchaseOrder order,
            CatalogProduct product,
            int quantity,
            BigDecimal unitPrice
    ) {
        this.order = Objects.requireNonNull(order, "order");
        this.product = Objects.requireNonNull(product, "product");
        changeQuantity(quantity);

        Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Đơn giá không được âm");
        }
        this.unitPrice = unitPrice;
    }

    void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        this.quantity = newQuantity;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public Long getId() {
        return id;
    }

    public CatalogProduct getProduct() {
        return product;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(
            BigDecimal.valueOf(quantity)
        );
    }
}
```

Điểm mấu chốt:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private CatalogProduct product;
```

**Không có `cascade = ALL` ở quan hệ tới sản phẩm**. Việc một dòng đơn tham chiếu `CatalogProduct` là điều kiện của dữ liệu; không có nghĩa dòng đơn sở hữu quyền tạo, ghi đè hoặc xóa sản phẩm.

Cũng **không cascade REMOVE từ line lên order**. Nếu xóa một dòng riêng lẻ, điều đó không được xóa toàn bộ đơn.

### 6.3. Aggregate root: `PurchaseOrder`

```java
package com.example.shop;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    public enum Status {
        DRAFT, PLACED, CANCELLED
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @Column(name = "order_number",
            nullable = false, unique = true, length = 64)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 16)
    private Status status;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true,
        fetch = FetchType.LAZY
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(String orderNumber) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException(
                "Mã đơn hàng không hợp lệ"
            );
        }

        this.orderNumber = orderNumber.trim();
        this.status = Status.DRAFT;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(
            CatalogProduct product,
            int quantity,
            BigDecimal unitPrice
    ) {
        requireDraft();
        lines.add(
            new OrderLine(this, product, quantity, unitPrice)
        );
    }

    public void removeLine(OrderLine line) {
        requireDraft();
        Objects.requireNonNull(line, "line");

        if (!lines.remove(line)) {
            throw new IllegalArgumentException(
                "Dòng hàng không thuộc đơn"
            );
        }

        // Cập nhật owning side của quan hệ trong object graph.
        // Với orphanRemoval, dòng bị tách sẽ được xử lý xóa.
        line.detachFromOrder();
    }

    public BigDecimal totalAmount() {
        return lines.stream()
                .map(OrderLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public void place() {
        requireDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Không thể đặt đơn không có dòng hàng"
            );
        }

        this.status = Status.PLACED;
    }

    private void requireDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException(
                "Chỉ được sửa đơn ở trạng thái DRAFT"
            );
        }
    }
}
```

Cấu hình quan trọng:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true,
    fetch = FetchType.LAZY
)
private List<OrderLine> lines;
```

**Vì sao `ALL` có thể phù hợp ở đây?**

- `OrderLine` được tạo từ `PurchaseOrder.addLine()`.
- Mỗi dòng chỉ thuộc một đơn và không có vòng đời độc lập theo quy tắc của ví dụ.
- Xóa hẳn đơn thường đi kèm xóa dòng.
- Khi merge trạng thái aggregate từ một nguồn đáng tin cậy, cần xử lý các dòng phụ thuộc cùng aggregate — tuy nhiên vẫn phải đánh giá rủi ro merge detached graph.
- Domain method quản lý hai phía quan hệ và kiểm soát trạng thái cho phép sửa.

**Vì sao vẫn cần thận trọng?**

`CascadeType.ALL` làm việc theo JPA semantics, không kiểm tra trạng thái `DRAFT`/`PLACED` khi `em.remove(order)`. Nếu hệ thống phải giữ order để đối soát, service không nên gọi remove chỉ vì khách hàng bấm “Hủy đơn”.

Cơ chế cascade **không thay thế business invariant** hoặc cơ chế phân quyền.

### 6.4. Lưu ý về `List`

Trong ví dụ, collection `lines` dùng `List` nhưng không có `@OrderColumn`. Điều đó **không bảo đảm thứ tự dòng sau khi tải lại**. Nếu cần thứ tự ổn định, hãy thiết kế `lineNumber`, `@OrderColumn` hoặc thứ tự truy vấn có chủ đích.

Với một `OrderLine` mới chưa có ID, không nên viết `equals()/hashCode()` chỉ dựa vào `id == null` rồi coi mọi object mới giống nhau. Ví dụ này dùng object identity mặc định và chỉ nhận đối tượng line hiện có trong collection khi remove; application service phải tải aggregate để có đúng object thuộc collection.

## 7. Schema tương ứng: cascade JPA không thay cấu trúc FK

DDL minh họa:

```sql
CREATE TABLE catalog_products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    row_version BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL UNIQUE,
    product_name VARCHAR(160) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    row_version BIGINT NOT NULL,
    order_number VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(16) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(15, 2) NOT NULL,

    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id),

    CONSTRAINT fk_order_line_product
        FOREIGN KEY (product_id)
        REFERENCES catalog_products(id)
);
```

Trong schema này:

- `order_lines.order_id` tham chiếu order.
- `order_lines.product_id` tham chiếu product.
- `CatalogProduct` **không thuộc vòng đời** của `OrderLine`.
- `CascadeType.ALL` là metadata JPA trên quan hệ Java; không có cột SQL tên `cascade_all`.
- Các câu `DELETE` do JPA thực hiện khi cascade REMOVE phải tôn trọng ràng buộc FK.

DDL trên cố tình **không dùng `ON DELETE CASCADE`** để thấy rõ sự khác nhau với cascade do JPA điều phối.

### 7.1. Hình dung một lần xóa đơn

Giả sử:

```text
purchase_orders:
  id=200

order_lines:
  id=1, order_id=200, product_id=10
  id=2, order_id=200, product_id=20

catalog_products:
  id=10 ("Sách Java")
  id=20 ("Bút")
```

Gọi `em.remove(order200)` từ managed order, với `cascade = ALL` trên `lines`:

```text
PurchaseOrder#200
      |
      +-- remove OrderLine#1
      |
      +-- remove OrderLine#2
      |
      +-- remove PurchaseOrder#200

CatalogProduct#10: vẫn tồn tại
CatalogProduct#20: vẫn tồn tại
```

Provider quyết định thứ tự SQL phù hợp metadata và FK. Không nên viết test cứng rằng tất cả provider luôn phát đúng ba câu DELETE và theo đúng thứ tự nhật ký; điều cần xác nhận là **kết quả dữ liệu**.

## 8. Persist graph: lợi ích và giới hạn của `PERSIST`

### 8.1. Tạo order và các dòng trong cùng transaction

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    CatalogProduct book =
            em.find(CatalogProduct.class, bookId);
    CatalogProduct pen =
            em.find(CatalogProduct.class, penId);

    if (book == null || pen == null) {
        throw new IllegalArgumentException(
            "Sản phẩm không tồn tại"
        );
    }

    PurchaseOrder order = new PurchaseOrder("PO-2026-001");

    order.addLine(
        book,
        2,
        new BigDecimal("120000.00")
    );
    order.addLine(
        pen,
        3,
        new BigDecimal("15000.00")
    );

    em.persist(order); // PERSIST lan từ order tới các line.
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Trong ví dụ dùng resource-local transaction, import `jakarta.persistence.*` và `java.math.BigDecimal` theo môi trường thực tế.

Ta **không gọi `em.persist(book)` hoặc `em.persist(pen)`**, vì chúng đã là các entity danh mục tồn tại trước đó, đã được tìm trong context hiện tại. Ta cũng không gọi `em.persist(line)` riêng vì `PurchaseOrder.lines` có cascade PERSIST.

### 8.2. Cascade PERSIST không có nghĩa “save mọi thứ”

Một lỗi nguy hiểm:

```java
@ManyToOne(cascade = CascadeType.ALL)
private CatalogProduct product;
```

Nếu một `OrderLine` mới liên kết tới object `CatalogProduct` đã tồn tại nhưng detached, cascade PERSIST có thể khiến provider cố persist entity đã có identity, dẫn đến lỗi liên quan tới detached entity hoặc duplicate key.

Quan trọng hơn, đây là sai lầm mô hình: việc tạo đơn hàng **không có nghĩa yêu cầu tạo/sở hữu vòng đời sản phẩm**.

Với reference đến entity đã tồn tại, service thường dùng:

```java
CatalogProduct product =
        em.getReference(CatalogProduct.class, productId);
```

hoặc `em.find(...)` khi cần xác nhận sự tồn tại và đọc dữ liệu. `getReference` có thể trả proxy/reference chưa query ngay; nếu ID không tồn tại, lỗi có thể xuất hiện khi truy cập hoặc khi database kiểm tra FK.

### 8.3. Chỉ cần persist cùng nhau chưa chắc cần `ALL`

Nếu đơn và dòng phải được tạo cùng lúc nhưng sau đó có vòng đời độc lập, có thể chỉ cần:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

Không có `REMOVE` trong mapping này. Khi delete order, application phải quản lý các dòng/FK theo quy tắc riêng; đó là hệ quả có chủ đích nếu không muốn tự động xóa child.

## 9. MERGE: rủi ro lớn khi làm việc với detached graph

### 9.1. `merge` không làm object gốc thành managed

Khi entity đã detached:

```java
PurchaseOrder detachedOrder = ...;

PurchaseOrder managedOrder = em.merge(detachedOrder);
```

`em.merge(...)` trả về **managed instance** phù hợp với ngữ cảnh hiện tại. Object `detachedOrder` truyền vào **không tự trở thành managed**.

Nếu quan hệ `detachedOrder.lines` có `CascadeType.MERGE` hoặc `ALL`, provider sẽ xử lý merge của các entity liên quan theo semantics JPA.

### 9.2. Nguy cơ sao chép state cũ

Giả sử:

```text
09:00   UI tải Order#200
        lines:
          - Line#1 quantity=2
          - Line#2 quantity=3

09:05   User B sửa Line#2 quantity=5 và commit

09:10   User A gửi lại toàn bộ detached Order graph
        còn Line#2 quantity=3
```

Nếu service đơn giản:

```java
em.merge(detachedOrder);
```

thì state cũ từ graph có thể được sao chép vào managed graph và gây cập nhật ngoài ý muốn nếu không có cơ chế concurrency control thích hợp.

`@Version` trên entity cập nhật có thể phát hiện một số trường hợp xung đột. Nhưng **không nên giả định version ở root luôn tăng khi mọi child được thay đổi độc lập** trong mọi provider/mapping.

### 9.3. Detached graph không đầy đủ

Một API có thể chỉ gửi:

```json
{
  "id": 200,
  "status": "DRAFT",
  "lines": [
    { "id": 1, "quantity": 2 }
  ]
}
```

Trong khi database đang có Line#1 và Line#2. Nếu code biến payload thành một detached entity có collection chỉ chứa Line#1 rồi gọi merge, cách diễn giải sự vắng mặt của Line#2 có thể gây hậu quả không mong muốn, đặc biệt khi mapping có `orphanRemoval = true` và state collection được xem là một thay đổi.

Không nên coi một JSON DTO **thiếu field** tương đương một entity graph đầy đủ có thể merge an toàn.

### 9.4. Cách dùng command DTO rõ ràng hơn

Một use case sửa số lượng dòng hàng nên nhận:

```java
public record ChangeLineQuantityCommand(
    Long orderId,
    Long lineId,
    int quantity,
    Long expectedVersion
) {}
```

Trong service:

```java
@Transactional
public void changeQuantity(ChangeLineQuantityCommand command) {
    PurchaseOrder order = repository.findByIdWithLines(
        command.orderId()
    );

    if (!Objects.equals(
            order.getVersion(),
            command.expectedVersion()
    )) {
        throw new ConcurrentModificationException(
            "Đơn đã thay đổi"
        );
    }

    order.changeLineQuantity(
        command.lineId(),
        command.quantity()
    );
}
```

Đây là phác thảo tầng application: giả sử `repository.findByIdWithLines` trả managed entity và `PurchaseOrder.changeLineQuantity` đã được bổ sung với guard trạng thái hợp lệ. Ví dụ dùng Spring `@Transactional` hoặc transaction boundary tương đương, `Objects` và `ConcurrentModificationException` từ Java.

**Lợi ích:** service tải aggregate hiện tại rồi áp dụng **hành động có chủ đích**, thay vì merge toàn bộ entity graph từ client.

Nếu nghiệp vụ cần bảo vệ cả aggregate trước sửa child, cân nhắc chiến lược lock/version ở root như phần 17.

## 10. REMOVE: thao tác có nguy cơ cao nhất khi lạm dụng `ALL`

### 10.1. Từ một thao tác xóa có thể trở thành nhiều thao tác xóa

```java
em.remove(order);
```

Nếu `PurchaseOrder.lines` có `CascadeType.REMOVE`, provider phải xử lý remove cho các line liên quan.

Điều này tốt khi line là dữ liệu phụ thuộc hoàn toàn vào order. Nhưng nếu cascade đi sang một entity dùng chung, hiệu ứng có thể nguy hiểm.

### 10.2. Anti-pattern: child cascade REMOVE lên parent

Ví dụ:

```java
@Entity
public class OrderLine {

    @ManyToOne(
        cascade = CascadeType.ALL
    )
    @JoinColumn(name = "product_id")
    private CatalogProduct product;
}
```

Khi:

```java
em.remove(orderLine);
```

cascade REMOVE theo chiều `OrderLine → CatalogProduct` có thể cố **xóa sản phẩm danh mục** được tham chiếu. Các đơn hàng khác cũng dùng product này.

Các kết quả có thể là:

- Database từ chối xóa vì foreign key từ những dòng khác còn tham chiếu product.
- Nếu schema và graph cho phép, dữ liệu product bị xóa ngoài ý định.
- Một chuỗi cascade khác mở rộng việc xóa sang những entity liên quan.
- Transaction thất bại ở flush/commit thay vì đúng lúc code gọi `remove`.

Không nên cho rằng “có FK nên database luôn cứu được”. Các ràng buộc có thể khác, có thể có `ON DELETE CASCADE` hoặc các quan hệ chưa đủ constraint. Đúng nhất là **không cấu hình cascade REMOVE tới entity không thuộc vòng đời nguồn**.

### 10.3. Tại sao `@ManyToOne` hầu như không thích hợp với `ALL`?

`@ManyToOne` thường biểu diễn nhiều entity con cùng tham chiếu **một đối tượng chung**, như:

- Nhiều đơn hàng thuộc một customer.
- Nhiều order line tham chiếu cùng product.
- Nhiều nhân viên thuộc một department.
- Nhiều hóa đơn cùng một currency.
- Nhiều bài viết do một author tạo.

Nếu xóa một “bên nhiều” mà xóa luôn “bên một”, graph sẽ bị đảo ngược quan hệ sở hữu nghiệp vụ.

Quy tắc thực tế: `@ManyToOne` thường **không cascade**, trừ khi có một trường hợp đặc biệt được chứng minh về vòng đời và semantics của tất cả các thao tác được chọn. Với `CascadeType.REMOVE` trên những quan hệ không phải one-to-one/one-to-many, còn có **vấn đề tính di động theo đặc tả JPA**; không nên áp dụng.

## 11. `@ManyToMany(cascade = ALL)` và nguy cơ xóa đối tượng dùng chung

Một ví dụ quen thuộc là `User` và `Role`:

```text
User A ----+--> Role ADMIN
           |
User B ----+--> Role ADMIN
           |
User C --------> Role VIEWER
```

Mỗi role có thể được chia sẻ bởi nhiều users. Quan hệ SQL dùng bảng liên kết:

```text
users                 user_roles                 roles
id | username         user_id | role_id           id | name
1  | alice            1       | 10                10 | ADMIN
2  | bob              2       | 10                20 | VIEWER
3  | carol            3       | 20
```

Sai về vòng đời:

```java
@ManyToMany(cascade = CascadeType.ALL)
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
private Set<Role> roles = new HashSet<>();
```

Nếu gọi `em.remove(userA)`, cascade REMOVE có thể cố xóa `Role ADMIN` — role mà `User B` vẫn sử dụng. Điều này hoàn toàn khác với yêu cầu hợp lý là **chỉ xóa dòng liên kết** giữa `User A` và `Role ADMIN`.

### 11.1. Mapping thường phù hợp hơn

```java
@ManyToMany
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
private Set<Role> roles = new HashSet<>();
```

Không cascade REMOVE tới `Role`.

Khi gỡ role khỏi user:

```java
user.getRoles().remove(role);
```

provider có thể đồng bộ **join table** theo owning side và mapping hiện tại. `Role` vẫn tồn tại.

Khi xóa user, các hàng join table liên quan phải được xử lý để thỏa ràng buộc SQL; điều đó **không có nghĩa phải xóa entity Role**.

### 11.2. Lưu ý về đặc tả

`CascadeType.REMOVE` được thiết kế phù hợp cho những quan hệ một-một và một-nhiều có vòng đời phụ thuộc. Việc áp dụng cascade REMOVE lên các loại association khác, bao gồm `@ManyToMany`, **không được xem là lựa chọn portable theo hướng dẫn của JPA**.

Vì `ALL` bao gồm `REMOVE`, đặt `ALL` trên `@ManyToMany` đặc biệt cần tránh.

### 11.3. Many-to-many có giá trị quan hệ riêng

Nếu bảng liên kết còn có trạng thái, thời gian gán role, người cấp quyền hoặc lịch sử, có thể thiết kế một **association entity** riêng:

```text
User --OneToMany--> UserRoleAssignment --ManyToOne--> Role
```

Khi đó có thể cascade từ `User` đến `UserRoleAssignment` nếu assignment thuộc vòng đời User, nhưng **không cascade REMOVE từ assignment đến Role**.

## 12. `@OneToOne`: khi nào `ALL` hợp lý, khi nào nguy hiểm?

Một-một không tự đồng nghĩa vòng đời phụ thuộc.

### 12.1. Phù hợp: profile là thành phần của account

Giả sử:

- Mỗi `Account` có một `AccountPreferences`.
- Preferences không được dùng chung.
- Khi account bị xóa vĩnh viễn, preferences cũng bị xóa.
- Mã ứng dụng tạo và quản lý preferences thông qua account.

Có thể cân nhắc:

```java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private AccountPreferences preferences;
```

Phía owning chứa FK:

```java
@OneToOne(optional = false)
@JoinColumn(
    name = "account_id",
    nullable = false,
    unique = true
)
private Account account;
```

Mapping phải cùng phản ánh một relationship, và helper cần cập nhật cả hai phía. `ALL` hợp lý **chỉ khi cả năm thao tác cascade** đều được chấp nhận.

### 12.2. Không phù hợp: các entity có identity/vòng đời riêng

Ví dụ `Person` và `Passport` có thể liên hệ một-một trong một mô hình đơn giản, nhưng passport thường có vòng đời pháp lý, lịch sử và quy tắc thu hồi/đổi riêng.

Xóa một `Person` trong database không nhất thiết cho phép tự xóa mọi dữ liệu hộ chiếu. Lúc này cascade REMOVE hoặc `ALL` có thể vi phạm yêu cầu lưu trữ và đối soát.

Tương tự, `User` và `PaymentAccount`, `Employee` và `PayrollRecord`, `Patient` và `MedicalRecord` có thể liên kết một-một nhưng không nên tự động suy ra quyền xóa dữ liệu đi kèm.

**Cardinality 1–1 chỉ nói về số lượng tham chiếu; aggregate ownership mới trả lời được về cascade.**

## 13. `orphanRemoval` không phải một phần của `CascadeType.ALL`

### 13.1. Hai kích hoạt khác nhau

Với:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Có hai tình huống:

**A. Xóa toàn bộ parent**

```java
em.remove(order);
```

Cascade REMOVE từ `ALL` truyền remove từ order tới các line liên quan.

**B. Bỏ một child khỏi collection**

```java
order.removeLine(line);
```

`orphanRemoval = true` khiến một line đã persistent bị tách khỏi quan hệ owner được xử lý xóa khi đồng bộ theo quy tắc JPA.

Bảng phân biệt:

| Hành động | `cascade = REMOVE`, không orphanRemoval | `orphanRemoval = true` |
|---|---|---|
| Gọi `em.remove(parent)` | Truyền remove tới child liên quan. | Cũng có semantics xóa dependent khi parent bị remove theo quy tắc orphan removal; không bắt buộc khai báo `REMOVE` riêng chỉ cho trường hợp này. |
| Gỡ child khỏi `parent.children` | **Không tự xóa child chỉ vì có REMOVE**. | Child đã persistent bị tách khỏi association có thể được đánh dấu xóa. |
| Đổi một thuộc tính khác của parent | Không tự xóa child. | Không tự xóa nếu child vẫn thuộc association. |
| Gọi `em.remove(child)` riêng | Xóa child theo lời gọi trực tiếp, nếu managed. | Không cần orphanRemoval để thao tác trực tiếp này xảy ra. |

### 13.2. `orphanRemoval` chỉ áp dụng cho quan hệ thích hợp

Theo mô hình JPA chuẩn, `orphanRemoval` là thuộc tính của `@OneToOne` và `@OneToMany`; **không có `orphanRemoval` trên `@ManyToMany`** hoặc `@ManyToOne`.

Nếu phần tử có thể được chia sẻ hoặc chuyển owner một cách thường xuyên, orphan removal dễ không phù hợp. Mục đích của nó là **xóa entity phụ thuộc khi bị tách khỏi quan hệ sở hữu**.

### 13.3. Tránh “reparent” một orphan được quản lý như một entity độc lập

Một đoạn code dễ gây nhầm:

```java
orderA.removeLine(line);
orderB.addExistingLine(line);
```

Khi đã dùng `orphanRemoval = true`, việc gỡ line có thể khiến nó được xem là orphan cần xóa. JPA không dành orphan removal cho trường hợp “tháo khỏi A để tái sử dụng nguyên entity ở B” như thao tác di chuyển thông thường.

Nếu nghiệp vụ cần chuyển dòng qua đơn khác, thường nên thiết kế rõ: tạo line mới trong B, điều chỉnh order cũ, lưu lịch sử và constraint; hoặc thay đổi mô hình để line có vòng đời độc lập nếu việc chuyển là thao tác chính.

### 13.4. Orphan mới, detached, hoặc đã removed

Quy tắc orphan removal tập trung vào **entity đích đã persistent và bị tách khỏi relationship**. Không nên dựa vào orphan removal để thực hiện remove cho những object target mới/transient, detached hoặc đã removed trong mọi tình huống.

Ví dụ, tạo một `OrderLine` mới rồi bỏ nó khỏi collection trước khi persist order không phải một thao tác “DELETE row đã tồn tại”; nó có thể đơn giản là object chưa từng được lưu.

### 13.5. Tại sao `ALL` và `orphanRemoval` thường đi cùng nhau?

Trong một aggregate phụ thuộc vòng đời:

- `ALL` cho phép persist, merge, remove, refresh, detach các child cùng parent.
- `orphanRemoval = true` cho phép xóa child khi nó bị gỡ khỏi collection.

Nhưng **đây không phải cặp annotation bắt buộc**. Nếu chỉ muốn tạo child cùng parent và xóa orphan, có thể cân nhắc:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Cần xác nhận semantics vòng đời và các thao tác merge/refresh/detach mà hệ thống cần; không tự chọn `ALL` chỉ vì copy được từ ví dụ.

## 14. Không đánh đồng cascade JPA với `ON DELETE CASCADE` của database

Hai cơ chế ở những tầng khác nhau:

```text
Java / JPA
   em.remove(order)
       |
       +-- cascade=REMOVE
       |       |
       |       +-- provider quản lý remove của OrderLine
       |
       v
  SQL DELETE ... trong transaction

Database
   FOREIGN KEY order_id REFERENCES purchase_orders(id)
       ON DELETE CASCADE
       |
       +-- database tự xóa hàng child khi xóa parent row
```

So sánh:

| Tiêu chí | JPA `CascadeType.REMOVE` | SQL `ON DELETE CASCADE` |
|---|---|---|
| Ai điều phối? | JPA provider dựa trên association metadata. | Database dựa trên foreign key constraint. |
| Kích hoạt bởi | Một thao tác remove được truyền qua graph JPA. | Một SQL DELETE ở bảng được tham chiếu. |
| Có thể tác động tới entity lifecycle callbacks? | Provider xử lý lifecycle cho entity bị remove theo semantics JPA. | SQL DB không chạy JPA callbacks cho các row tự xóa. |
| Áp dụng khi gọi bulk JPQL DELETE/native DELETE? | Bulk operations không dùng entity-by-entity cascade theo cách `em.remove`. | FK với `ON DELETE CASCADE` vẫn áp dụng khi SQL DELETE thực thi. |
| Có làm managed entity khác tự cập nhật? | Do provider/context quản lý theo thao tác. | Không tự cập nhật mọi managed object đã tải trong JPA context. |
| Có thay thế cho business authorization? | Không. | Không. |

Một số provider có extension cho phép phối hợp JPA mapping với DB-level delete, nhưng đó không phải đồng nghĩa mọi `CascadeType.ALL` tạo `ON DELETE CASCADE` trong SQL.

### 14.1. Không khai báo cả hai mà không hiểu hậu quả

Nếu database có `ON DELETE CASCADE` và provider cũng đang cố remove từng child, việc phối hợp phải được hiểu theo implementation. Có thể có SQL/row-count behavior, callback hoặc cache invalidation khác với kỳ vọng.

Cần chọn kiến trúc nhất quán, đặc biệt khi muốn audit hoặc lifecycle callbacks cho từng child.

## 15. Nguy cơ từ `REFRESH`: mất pending changes trong toàn graph

`CascadeType.REFRESH` thường ít được chú ý vì ví dụ cascade hay chỉ nói tới persist/remove. Nhưng nó cũng nằm trong `ALL`.

Giả sử:

```java
PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);
line.changeQuantity(7);

// Chưa flush/commit.
em.refresh(order);
```

Nếu quan hệ `order.lines` có cascade REFRESH, provider có thể refresh những `OrderLine` được liên kết cùng order. State `quantity = 7` chưa được đồng bộ có thể bị **ghi đè bởi state đọc lại từ database**.

Điều này có thể gây lỗi khó chẩn đoán trong wizard nhiều bước khi service gọi `refresh(order)` với ý định “lấy lại tổng quan order”, nhưng vô tình làm mất dữ liệu đang sửa ở các child.

### 15.1. Chọn cascade REFRESH khi nào?

Chỉ nên cho phép khi hành vi mong muốn là: **làm mới parent đồng thời làm mới các child có vòng đời phụ thuộc, chấp nhận bỏ state local chưa lưu**.

Nếu refresh child không phải một yêu cầu nghiệp vụ, cân nhắc tránh `ALL` và chọn cascade cụ thể:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    }
)
private List<OrderLine> lines;
```

### 15.2. Refresh không phải công cụ ngăn lost update

`refresh` làm mới state theo semantics transaction hiện tại, nhưng không thay thế `@Version` và xử lý conflict. Một transaction khác vẫn có thể cập nhật sau khi refresh và trước khi commit.

## 16. Nguy cơ từ `DETACH`: thay đổi không còn được theo dõi

`CascadeType.DETACH` cũng nằm trong `ALL`.

Ví dụ:

```java
PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

OrderLine line = order.getLines().get(0);

em.detach(order);

// Khi cascade DETACH đi theo quan hệ,
// line cũng có thể bị detach theo.
line.changeQuantity(9);

// Không nên giả định thay đổi này tự được lưu.
```

Một managed entity được dirty checking trong persistence context thích hợp. Sau detach, việc sửa object Java **không tự được đồng bộ** tới database.

### 16.1. Phân biệt `detach` với `clear`

- `em.detach(order)` yêu cầu detach một entity, và có thể cascade theo các cạnh có `DETACH`.
- `em.clear()` detach **tất cả managed entities** trong context; hành vi này không cần từng cạnh có `CascadeType.DETACH`.

Không nên viết:

```java
em.detach(order);
line.changeQuantity(9);
tx.commit(); // Mong line vẫn managed và tự update.
```

nếu mapping đã cascade DETACH tới line.

### 16.2. DETACH không bảo đảm dữ liệu không còn tồn tại trong memory

Detach chỉ ngừng quản lý persistence; object Java vẫn có thể được giữ bởi biến, collection hoặc HTTP session. Nó không phải xóa dữ liệu và không bảo đảm object đã được reload khi được sử dụng lại.

## 17. `@Version` và transaction giúp giảm rủi ro nhưng không cứu mọi cascade sai

### 17.1. Optimistic locking cho entity bị cập nhật

`@Version` trên `PurchaseOrder` hoặc `CatalogProduct` giúp provider phát hiện một số trường hợp state stale khi update/delete trong transaction.

Ví dụ:

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Nếu một transaction khác đã cập nhật entity và version thay đổi, provider có thể báo `OptimisticLockException` ở flush/commit. Nhưng version **không biến việc xóa nhầm một entity hoàn toàn hợp lệ thành thao tác an toàn**.

Nếu code đặt `cascade = ALL` từ `OrderLine` sang `CatalogProduct` và xóa product đang không có xung đột version, `@Version` không thể biết business không muốn xóa sản phẩm. Quy tắc vòng đời vẫn phải đúng.

### 17.2. Root version và sửa child

Khi chỉ sửa `OrderLine`, đừng mặc định mọi provider/mapping đều tăng version của `PurchaseOrder`. Nếu invariant của aggregate phụ thuộc vào việc “đặt đơn” không được xảy ra đồng thời với “thêm dòng”, service có thể cần một chiến lược khóa root rõ ràng.

Ví dụ:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId
);

em.lock(
    order,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);

// Tiếp theo mới thực hiện hành động thay đổi child
// thuộc cùng một use case.
```

Hoặc đánh giá `PESSIMISTIC_WRITE` với transaction ngắn nếu cạnh tranh cao. Các import và transaction phải phù hợp JPA. `OPTIMISTIC_FORCE_INCREMENT` không nên dùng tràn lan; nó là lựa chọn concurrency cho một phạm vi invariant cụ thể.

### 17.3. Lỗi cascade có thể xuất hiện muộn

Một thao tác:

```java
em.remove(order);
```

có thể chỉ tạo thay đổi trong persistence context; SQL thực thi tại `flush()` hoặc `commit()`. Khi đó provider mới phát hiện:

- FK tới child khác chưa được xử lý.
- Unique/check constraint.
- Optimistic lock conflict.
- Lock timeout hoặc deadlock.
- Dữ liệu đã đổi từ transaction khác.

Do đó service cần kiểm soát **toàn bộ transaction boundary**, không chỉ catch exception ngay tại `em.remove`.

## 18. Cascade không thay thế transaction nguyên tử

Giả sử:

```java
em.persist(order); // cascade persist các line.
```

Nếu các entity được ghi trong một transaction database phù hợp, commit hoặc rollback bảo vệ tính nguyên tử của những thao tác ghi trong phạm vi transaction đó. Cascade chỉ xác định **những entity nào nhận operation**.

Một cấu trúc resource-local:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = ...;
    em.persist(order);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

**`flush()` không phải `commit()`.** Kể cả provider đã thực thi INSERT/DELETE cho các child ở flush, rollback vẫn có thể hủy transaction theo semantics của database.

### 18.1. Rollback không tự sửa lại object Java

Nếu entity Java đã bị thay đổi rồi transaction rollback:

```text
Database: rollback về state đã commit trước đó
Java object: có thể còn state đã sửa hoặc đã được đánh dấu removed
```

Không nên tái sử dụng bừa bãi graph từ transaction thất bại. Đóng EntityManager của unit of work lỗi và nạp lại bằng context mới là chiến lược rõ ràng.

## 19. Cẩn thận với bulk JPQL và native SQL

JPA cascade entity-by-entity được áp dụng khi thực hiện các thao tác persistence trên managed entities theo semantics JPA.

Nhưng:

```java
em.createQuery(
    "DELETE FROM PurchaseOrder o WHERE o.status = :status"
)
.setParameter("status", PurchaseOrder.Status.CANCELLED)
.executeUpdate();
```

là **JPQL bulk DELETE**. Bulk operations không xử lý entity lifecycle cascade giống `em.remove(order)` trên từng managed entity.

Hậu quả:

- `CascadeType.REMOVE` không tự chạy như vòng lặp gọi `em.remove` cho từng root.
- Child rows có FK tới order có thể chặn DELETE nếu database không có quy tắc cascade SQL phù hợp.
- Nếu database có `ON DELETE CASCADE`, child có thể bị xóa bởi DB, nhưng các JPA entity callbacks và managed state không tự được đồng bộ như xóa entity thông thường.
- Managed entities đã load trong persistence context có thể trở thành stale.

Nếu xóa hàng loạt bằng JPQL/native SQL, phải **thiết kế riêng** constraint, thứ tự delete, archive/audit, cache invalidation và transaction. Không được cho rằng thêm `CascadeType.ALL` ở entity mapping là đủ.

### 19.1. Bulk UPDATE cũng có thể bỏ qua invariant

```java
em.createQuery(
    "UPDATE PurchaseOrder o SET o.status = :status"
)
.setParameter("status", PurchaseOrder.Status.CANCELLED)
.executeUpdate();
```

không tự gọi `PurchaseOrder.cancel()` để kiểm tra domain rule, và cũng không tự thực thi entity-by-entity lifecycle callbacks theo cách update managed entity.

Nếu domain yêu cầu kiểm tra trạng thái đơn trước khi hủy, bulk UPDATE cần một chiến lược riêng, thay vì lấy cascade làm lớp bảo vệ.

## 20. Đánh giá số lượng SQL và phạm vi xóa

Một quan hệ:

```java
@OneToMany(mappedBy = "project", cascade = CascadeType.ALL)
private List<Task> tasks;
```

có thể có 50.000 task. Một thao tác `em.remove(project)` có thể kích hoạt xử lý rất nhiều entity/row tùy provider và mapping.

Nguy cơ:

- Tải và quản lý nhiều đối tượng trong persistence context.
- Nhiều câu `DELETE`/`UPDATE` hoặc batch SQL.
- Transaction dài, tăng thời gian giữ lock.
- Lock contention và timeout.
- Memory pressure khi graph quá lớn.
- Không đáp ứng deadline của một HTTP request.
- Tác động tới second-level cache và lifecycle callbacks nếu được dùng.

Đừng chọn `ALL` chỉ vì ví dụ 3 dòng chạy nhanh. Cần phân biệt aggregate nhỏ có vòng đời phụ thuộc với cây dữ liệu lớn cần xóa/archive theo job chuyên biệt.

### 20.1. Khi nào nên cân nhắc xử lý xóa theo lô?

Nếu việc xóa một parent đồng nghĩa phải xóa rất nhiều child, có thể cần:

- Quy trình xác nhận quyền và phạm vi dữ liệu trước khi xóa.
- Archive/soft delete nếu dữ liệu phải được giữ.
- Transaction chia lô có kiểm soát khi nghiệp vụ cho phép.
- Bulk SQL/JDBC hoặc DB cascade được thiết kế riêng, hiểu rõ khác biệt lifecycle/cache.
- Cơ chế job async ở hệ thống ứng dụng thực tế thay vì giữ HTTP request lâu.
- Monitoring, audit và phương án khôi phục.

Các phương án này phải được lựa chọn **theo invariant và transaction boundaries**; không được đổi một thao tác atomic thành nhiều batch commit nếu nghiệp vụ không cho phép trạng thái trung gian.

## 21. Cascade và soft delete / audit

Một đơn hàng có thể ở trạng thái:

```text
DRAFT -> PLACED -> PAID -> CANCELLED/REFUNDED
```

Những trạng thái đó là **business lifecycle**, khác `EntityManager.remove()`.

Nếu hệ thống phải giữ đơn để đối soát, một service nên gọi domain method:

```java
order.cancel(reason);
```

rồi commit state mới, **không gọi `em.remove(order)`**.

`CascadeType.REMOVE` không tự hiểu “xóa mềm” hay “hủy” theo nghiệp vụ. Nó truyền thao tác remove theo JPA semantics. Một provider có thể hỗ trợ extension để biến remove thành SQL UPDATE theo soft-delete mapping, nhưng đó là hành vi **phụ thuộc provider và cấu hình**, không phải ý nghĩa mặc định của `CascadeType.ALL`.

### 21.1. Audit record không nên bị cascade remove theo aggregate gốc

Nếu `OrderAuditLog` hoặc `PaymentRecord` cần lưu lâu hơn `PurchaseOrder`, cấu hình:

```java
@OneToMany(cascade = CascadeType.ALL)
private List<OrderAuditLog> auditLogs;
```

có thể gây mất dữ liệu lịch sử khi xóa order. Khi có retention policy hoặc yêu cầu pháp lý, **độ phụ thuộc trong navigation** không chứng minh ownership lifecycle.

Một bảng audit có thể chỉ giữ business identifier hoặc FK với chính sách giữ/xóa rõ ràng. Không mặc định cascade REMOVE từ entity nghiệp vụ tới tất cả log.

## 22. `@ElementCollection` không cần `CascadeType.ALL`

Một `@ElementCollection` lưu tập các giá trị basic hoặc embeddable thuộc owner:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tags",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

Các phần tử `String` không phải entity có `@Id` và không dùng `CascadeType` như relationship tới `@Entity`. JPA đồng bộ element collection như một phần state của owner.

Đừng thay `@ElementCollection` bằng `@OneToMany(cascade = ALL)` chỉ để “tự lưu mọi phần tử” nếu phần tử thực sự chỉ là giá trị không có entity identity.

Ngược lại, nếu một phần tử cần identity/vòng đời độc lập và được nhiều owner tham chiếu, nó có thể phải là entity và cascade cần được đánh giá theo ownership.

## 23. Có thể chọn cascade khác nhau cho từng quan hệ

Một aggregate có thể có nhiều kiểu liên kết:

```text
PurchaseOrder
   |
   +--> OrderLine          : lifecycle dependent
   |
   +--> Customer           : shared/independent
   |
   +--> DeliveryAddress    : value object
   |
   +--> PaymentTransaction : independently reconciled
```

Ánh xạ gợi ý:

```java
// Order -> line: phụ thuộc vòng đời.
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;

// Order -> customer: tồn tại độc lập.
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;

// Order -> deliveryAddress: embeddable value.
@Embedded
private DeliveryAddress deliveryAddress;

// Order -> transactions: cần giữ lịch sử và đối soát.
@OneToMany(mappedBy = "order")
private List<PaymentTransaction> transactions;
```

Đây là sơ đồ ý tưởng, không phải toàn bộ code của một entity hoàn chỉnh; các kiểu `Customer`, `DeliveryAddress`, `PaymentTransaction` cần mapping tương ứng.

Nhận xét:

- Có thể `ALL` cho `lines`.
- Không cascade tới `customer`.
- `deliveryAddress` là embeddable, không cần cascade entity operations.
- `transactions` có thể phải được xử lý bởi service thanh toán riêng; không tự cascade REMOVE.

### 23.1. Cascade là quyết định theo **từng cạnh** của graph

Đừng hỏi “entity PurchaseOrder có cần CascadeType.ALL không?”. Hãy hỏi:

> Trên **quan hệ PurchaseOrder.lines**, có nên truyền PERSIST, MERGE, REMOVE, REFRESH và DETACH theo hướng PurchaseOrder → OrderLine không?

Sau đó đặt **cùng câu hỏi độc lập cho mỗi quan hệ khác**.

Cách đánh giá từng cạnh giúp tránh kéo cascade sang entity dùng chung chỉ vì cùng xuất hiện trong object graph.

## 24. Ma trận quyết định dùng `ALL` hay cascade chọn lọc

| Quan hệ | Ownership thường gặp | Cascade gợi ý cần xem xét | Vì sao |
|---|---|---|---|
| Order → OrderLine | Child thuộc vòng đời order. | `ALL` hoặc tập chọn lọc; `orphanRemoval=true` nếu xóa dòng khi tách. | Tạo/xóa child cùng aggregate thường hợp lý. |
| OrderLine → Order | Order độc lập, một order có nhiều line. | Thường **không cascade**. | Xóa một line không được xóa order. |
| OrderLine → Product | Product thuộc catalog, dùng chung. | Thường **không cascade**. | Không được xóa/merge product theo line. |
| Order → Customer | Customer tồn tại độc lập. | Thường **không cascade**. | Xóa order không được xóa customer. |
| User → Roles (`ManyToMany`) | Roles dùng chung. | Thường **không REMOVE/ALL**. | Xóa user chỉ cần xử lý link, không xóa role. |
| Account → Preferences (`OneToOne`) | Preferences phụ thuộc account. | Có thể `ALL` + orphanRemoval. | Nếu mọi thao tác đều nên đi theo account. |
| Person → Passport | Cả hai có identity/lifecycle riêng. | Thường chọn lọc hoặc không cascade. | Phải xét quy tắc lưu giữ/pháp lý. |
| Post → AuditLog | Audit có retention độc lập. | Thường **không REMOVE/ALL**. | Không tự xóa lịch sử cùng post. |
| Project → Task | Có thể phụ thuộc hoặc độc lập. | Phụ thuộc yêu cầu thực tế. | Task có thể được chuyển project, có workflow riêng. |
| Folder → File | File có thể dùng chung hoặc sở hữu riêng. | Phụ thuộc model; tránh `ALL` nếu shared. | Xóa folder không nhất thiết được xóa file dùng chung. |

Bảng là **hướng phân tích**, không phải công thức bắt buộc. Quan hệ có cùng annotation có thể mang ownership khác nhau trong hai hệ thống.

### 24.1. Nếu chỉ cần tạo và cập nhật cùng nhau

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<OrderLine> lines;
```

Không có cascade REMOVE, REFRESH, DETACH. Đây có thể hợp lý khi child không được tự động xóa theo parent nhưng cần persist/merge cùng nhau. Tuy nhiên, nếu child thực sự phụ thuộc và FK không-null, service vẫn phải xác định **cách xóa parent hợp lệ**.

### 24.2. Nếu chỉ cần tạo child mới

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

Cấu hình này hẹp hơn nhiều so với `ALL`. Nó không ngầm cho phép merge/refresh/detach/remove child khi thao tác trên parent.

### 24.3. Khi nào nên chọn không cascade?

Với reference độc lập:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "product_id")
private CatalogProduct product;
```

Không có cascade là lựa chọn đúng trong nhiều mô hình: sản phẩm được tạo, cập nhật và xóa qua service danh mục, không qua vòng đời order.

## 25. Không dùng cascade để giải quyết quan hệ hai chiều không nhất quán

Đặt `cascade = ALL` **không làm JPA tự sửa mọi object graph thiếu liên kết owning side**.

Ví dụ sai:

```java
PurchaseOrder order = new PurchaseOrder("PO-001");
OrderLine line = ...;

// Chỉ thêm vào order.lines,
// nhưng line.order vẫn null.
order.getLines().add(line);
```

Khi `OrderLine.order` là owning side có FK NOT NULL, việc không gán owner có thể khiến INSERT lỗi hoặc giá trị FK sai. Cascade PERSIST chỉ truyền operation; nó **không thay business helper thiết lập quan hệ đúng**.

Mẫu helper:

```java
public void addLine(
        CatalogProduct product,
        int quantity,
        BigDecimal price
) {
    requireDraft();

    OrderLine line = new OrderLine(
        this,
        product,
        quantity,
        price
    );

    lines.add(line);
}
```

Tạo child với `order = this` rồi thêm vào collection giúp hai phía nhất quán.

Tương tự, với orphanRemoval, cần gỡ child khỏi collection và xử lý owning side phù hợp để object graph đúng nghĩa “không còn thuộc parent”.

## 26. Những trường hợp dễ tạo vòng cascade nguy hiểm

### 26.1. Cascade cả hai hướng trong một quan hệ hai chiều

```java
// Trong Parent:
@OneToMany(mappedBy = "parent", cascade = CascadeType.ALL)
private List<Child> children;

// Trong Child: nguy hiểm.
@ManyToOne(cascade = CascadeType.ALL)
private Parent parent;
```

Đặt `ALL` từ Child lên Parent là không cần thiết để đồng bộ FK và có thể dẫn đến thao tác remove từ child đi tới parent. Provider phải xử lý graph traversal theo semantics của nó, nhưng **business effect vẫn sai** nếu xóa child có thể xóa parent và các sibling child.

### 26.2. Cascade từ nhiều entity tới một entity dùng chung

```text
OrderLine A --ALL--> Product X
OrderLine B --ALL--> Product X
OrderLine C --ALL--> Product X
```

Một entity dùng chung có thể bị thao tác remove hoặc refresh/merge từ nhiều nguồn không liên quan. Việc xóa một owner nhỏ có thể tác động tới dữ liệu của owner khác.

### 26.3. Cascade qua nhiều cấp child-dependent

```text
Customer --ALL--> Order --ALL--> Line
```

Ngay cả nếu Order → Line là hợp lý, Customer → Order có thể **không hợp lý** vì xóa customer sẽ xóa đơn và toàn bộ lịch sử. Xét từng cấp, không suy luận “đã là 1–N thì ALL”.

## 27. Migration: review rủi ro khi thêm `ALL` vào hệ thống đang chạy

Giả sử code hiện tại:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
```

Một developer thêm:

```java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.ALL
)
private List<PurchaseOrder> orders;
```

Chỉ một thay đổi annotation nhưng có thể làm nhiều use case cũ đổi semantics:

- `em.remove(customer)` giờ có thể lan tới toàn bộ order.
- `em.merge(customerDetachedGraph)` có thể merge các orders và child graphs.
- `em.refresh(customer)` có thể refresh cả orders.
- `em.detach(customer)` có thể detach orders.
- `em.persist(customer)` có thể cố persist các orders nằm trong graph khi không phải tất cả đều new.

Đây là **thay đổi hành vi runtime có rủi ro cao**, kể cả schema SQL không đổi.

### 27.1. Đánh giá trước khi thay annotation

Các câu hỏi cần rà soát:

1. Entity đích có tồn tại độc lập không?
2. Có nhiều parent đang cùng tham chiếu child không?
3. Use case nào đang gọi `remove`, `merge`, `refresh`, `detach` trên source?
4. Source có được load và truyền dưới dạng detached graph từ UI/cache/session không?
5. Có callback, audit, soft delete hoặc retention policy liên quan không?
6. Database có các FK khác trỏ tới entity đích không?
7. Graph lớn tới đâu, khi cascade DELETE có thể tác động bao nhiêu hàng?
8. Có optimistic locking/version ở đúng ranh giới invariant không?
9. Có job bulk SQL hoặc ứng dụng khác đang ghi cùng bảng không?
10. Có cần backup, migration, rollout và khả năng hoàn tác cấu hình không?

### 27.2. Đừng chỉ xem SQL schema

Một ràng buộc FK trong database không cho biết toàn bộ semantics của cascade JPA. Sự thay đổi `cascade=ALL` có thể làm provider phát thêm nhiều lệnh `DELETE` hoặc merge state từ graph mà trước đây không được đụng tới.

Cần kiểm tra các code path sử dụng EntityManager, repository remove/delete, detached merge, refresh, detach và transaction boundary. Việc đó là nhiệm vụ review code thực tế của dự án; bài học chỉ mô tả tiêu chí đánh giá.

## 28. Kiểm thử rủi ro cascade bằng integration test

Do cascade quyết định dữ liệu được ghi/xóa thực sự, **integration test có database** quan trọng hơn chỉ kiểm tra annotation tồn tại.

Giả định môi trường thử nghiệm có:

- `PurchaseOrder`, `OrderLine`, `CatalogProduct` như phần 6.
- `EntityManagerFactory emf` tạo từ persistence unit thử nghiệm.
- JUnit 5.
- Database cô lập và được khởi tạo theo fixture phù hợp.

### 28.1. Persist order đồng thời lưu các line

```java
@Test
void persistOrderCascadesToLines() {
    EntityManager em = emf.createEntityManager();
    Long orderId;

    try {
        EntityTransaction tx = em.getTransaction();
        tx.begin();

        CatalogProduct product =
                em.find(CatalogProduct.class, existingProductId);

        PurchaseOrder order =
                new PurchaseOrder("PO-TEST-CASCADE-001");

        order.addLine(
            product,
            2,
            new BigDecimal("90000.00")
        );

        em.persist(order);
        tx.commit();
        orderId = order.getId();
    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();
    try {
        PurchaseOrder reloaded = verify.find(
            PurchaseOrder.class,
            orderId
        );

        assertNotNull(reloaded);
        assertEquals(1, reloaded.getLines().size());
    } finally {
        verify.close();
    }
}
```

Kiểm tra yêu cầu nghiệp vụ **cùng persist child**. Không cần assert provider phát bao nhiêu câu INSERT.

### 28.2. Xóa order không được xóa product

```java
@Test
void removingOrderDoesNotRemoveSharedProduct() {
    EntityManager em = emf.createEntityManager();

    try {
        EntityTransaction tx = em.getTransaction();
        tx.begin();

        PurchaseOrder order =
                em.find(PurchaseOrder.class, existingOrderId);

        em.remove(order);
        tx.commit();
    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();
    try {
        assertNull(
            verify.find(PurchaseOrder.class, existingOrderId)
        );

        assertNotNull(
            verify.find(CatalogProduct.class, existingProductId)
        );
    } finally {
        verify.close();
    }
}
```

Test này quan trọng vì nếu một người vô tình thêm `cascade = ALL` vào `OrderLine.product`, use case xóa đơn có thể phá lifecycle sản phẩm. Dữ liệu fixture phải bảo đảm order đang test có line tham chiếu `existingProductId`.

### 28.3. Orphan removal chỉ xóa dòng bị tách

```java
@Test
void removingOneLineKeepsOrderAndOtherLines() {
    EntityManager em = emf.createEntityManager();
    Long removedLineId;
    Long keptLineId;

    try {
        EntityTransaction tx = em.getTransaction();
        tx.begin();

        PurchaseOrder order = em.find(
            PurchaseOrder.class,
            existingDraftOrderId
        );

        OrderLine removed = order.getLines().get(0);
        OrderLine kept = order.getLines().get(1);

        removedLineId = removed.getId();
        keptLineId = kept.getId();

        order.removeLine(removed);
        tx.commit();
    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        assertNull(verify.find(OrderLine.class, removedLineId));
        assertNotNull(verify.find(OrderLine.class, keptLineId));
        assertNotNull(
            verify.find(PurchaseOrder.class, existingDraftOrderId)
        );
    } finally {
        verify.close();
    }
}
```

Fixture phải có ít nhất hai dòng trong `existingDraftOrderId`. Test kiểm tra **orphanRemoval** không xóa nhầm parent hoặc sibling.

### 28.4. Test rủi ro `REFRESH`

Một test có thể:

1. Mở transaction, load order và line.
2. Sửa quantity trong managed line nhưng chưa flush.
3. Gọi `em.refresh(order)` khi quan hệ cấu hình `CascadeType.REFRESH`.
4. Xác nhận state local được thay thế bởi state database theo semantics provider.
5. Rollback/cleanup transaction thử nghiệm.

Test này cho thấy cascade REFRESH **không luôn là thao tác đọc vô hại**.

### 28.5. Test rủi ro `DETACH`

Một test có thể:

1. Load order và line trong persistence context.
2. Gọi `em.detach(order)`.
3. Kiểm tra `em.contains(order) == false`; với cascade DETACH, kiểm tra trạng thái line phù hợp.
4. Sửa line sau detach.
5. Commit một transaction mà không merge lại và đọc lại trong context mới.
6. Xác nhận sửa đổi trên detached instance **không tự được persist**.

### 28.6. Test xung đột phiên bản

Hai transaction độc lập cùng sửa entity cần có cơ chế @Version/lock; test cần xác nhận không ghi đè âm thầm khi version stale. Nếu business invariant bao phủ cả child collection, cần test xung đột trên root/child theo chiến lược locking thực tế.

Các ví dụ test dùng JUnit `@Test` và assertions, cần import tương ứng cùng `jakarta.persistence.*`, `java.math.BigDecimal`. Không nên copy nguyên các biến fixture như `existingOrderId` vào production mà không khởi tạo chúng.

## 29. Những lỗi thường gặp khi dùng `CascadeType.ALL`

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Xóa order làm product bị xóa hoặc cố bị xóa | Có `ALL/REMOVE` từ line đến product. | Bỏ cascade lên entity shared. |
| Xóa một child làm parent và sibling bị ảnh hưởng | Cascade REMOVE từ child về parent. | Chỉ cascade theo hướng ownership thật sự. |
| Xóa user gây lỗi FK trên roles | `ManyToMany(cascade=ALL)` cố xóa shared Role. | Không REMOVE/ALL role; chỉ quản lý join table. |
| Persist aggregate báo “detached entity passed to persist” | PERSIST cascade tới entity đã tồn tại/detached. | Chỉ cascade tới new owned child; reference entity tồn tại phải được liên kết hợp lệ. |
| Merge detached graph làm mất dữ liệu | Cascade MERGE sao chép stale state hoặc collection không đầy đủ. | DTO/command, load managed aggregate, kiểm tra version và apply thay đổi rõ ràng. |
| Refresh parent làm mất sửa đổi child | `ALL` bao gồm REFRESH. | Chỉ refresh có chủ đích hoặc bỏ REFRESH khỏi tập cascade. |
| Sau detach parent, sửa child không được lưu | `ALL` bao gồm DETACH. | Dùng lifecycle đúng; không giả định child vẫn managed. |
| Bỏ một line khỏi collection nhưng DB vẫn còn line | Chỉ có cascade REMOVE, không orphanRemoval hoặc chưa cập nhật owning side đúng. | Dùng `orphanRemoval=true` nếu child phải bị xóa khi tách, cập nhật cả hai phía. |
| Bỏ khỏi collection nhưng entity dùng chung bị xóa | Orphan removal dùng cho entity không có ownership độc quyền. | Không dùng orphan removal với child cần chia sẻ/chuyển owner. |
| Delete parent bị vi phạm FK | Có entity khác còn tham chiếu target; cascade graph hoặc DB constraint chưa phù hợp. | Xác định phạm vi xóa và FK; không tự mở rộng `ALL`. |
| Có `cascade=ALL` nhưng bulk DELETE không xóa child | Bulk JPQL/native delete không chạy entity-by-entity cascade. | Thiết kế bulk SQL/DB constraints riêng. |
| Đã xóa DB row bằng SQL ngoài JPA nhưng entity trong context còn sống | Cache/context không tự invalidated bởi SQL ngoài. | Quản lý `clear`/evict và transaction phù hợp. |
| Cascade DELETE chạy quá lâu | Graph rất lớn hoặc provider phải xử lý nhiều child. | Đánh giá batch, archive, DB cascade chuyên biệt hoặc workflow xóa khác. |
| Entity callbacks/audit không chạy như mong đợi | Dùng DB ON DELETE CASCADE hoặc bulk SQL thay JPA remove. | Chọn cơ chế xóa phù hợp yêu cầu audit/callback. |
| Thêm ALL khiến xóa customer xóa toàn bộ orders | Cascade theo quan hệ 1–N nhưng domain không sở hữu lifecycle. | Không cascade REMOVE trên lịch sử order. |
| Đặt ALL ở hai phía của cùng quan hệ | Nhầm cascade đối xứng với đồng bộ FK. | Giữ hướng cascade từ aggregate root đến dependent. |
| EntityManager merge trả state lạ nhưng object đầu vào vẫn không managed | Hiểu nhầm semantics merge. | Dùng returned managed instance; tránh merge client graph. |
| Thêm dòng hàng từ UI nhưng bị mất sau reload | Chỉ sửa inverse collection, quên field FK owning side. | Helper cập nhật cả hai phía quan hệ. |
| Rollback nhưng object Java vẫn hiển thị state đã sửa | Rollback DB không tự khôi phục toàn bộ object trong memory. | Dùng context mới khi cần tiếp tục. |
| `@Version` vẫn không ngăn xóa nhầm | Version kiểm soát concurrency, không kiểm soát quyền sở hữu nghiệp vụ. | Sửa cascade graph và authorization/domain invariant. |
| Dùng `CascadeType.ALL` để sửa lỗi lazy loading | Nhầm cascade với fetch. | Thiết kế query, fetch join/entity graph và transaction hợp lý. |

## 30. Một quy trình ra quyết định theo từng operation

Thay vì chọn `ALL` hoặc không theo cảm tính, xét từng thao tác trong cả năm.

### 30.1. PERSIST

Hỏi: **Entity đích có thường được tạo mới cùng entity nguồn không?**

- Có, child mới thuộc aggregate → cân nhắc `PERSIST`.
- Không, entity đích đã tồn tại như Customer/Product → thường không cascade.

### 30.2. MERGE

Hỏi: **Có thực sự muốn sao chép state của entity đích khi merge source detached không?**

- Có, graph đầy đủ và đáng tin cậy, có version/guard → có thể cân nhắc `MERGE`.
- Không, chỉ nhận command/DTO hoặc entity đích độc lập → thường không cascade.

### 30.3. REMOVE

Hỏi: **Xóa source có được phép xóa hẳn target không?**

- Có, target chỉ sống cùng source và không có retention riêng → cân nhắc `REMOVE`.
- Không, target được chia sẻ hoặc có lịch sử riêng → **không cascade REMOVE**.

### 30.4. REFRESH

Hỏi: **Làm mới source có nên bỏ mọi chỉnh sửa local chưa lưu trên target không?**

- Có, việc refresh toàn graph là chủ đích → cân nhắc `REFRESH`.
- Không hoặc chưa rõ → không cần vội thêm REFRESH.

### 30.5. DETACH

Hỏi: **Detach source có nên làm target ngừng được theo dõi không?**

- Có, lifecycle quản lý hai object gắn chặt và context cần detach cả graph → cân nhắc `DETACH`.
- Không, code vẫn cần cập nhật target managed → tránh cascade DETACH không cần thiết.

**Chỉ khi cả năm câu hỏi đều được trả lời rõ ràng theo hướng chấp nhận** thì `CascadeType.ALL` mới thực sự phản ánh chủ ý.

## 31. Các tình huống luyện phân tích

### Tình huống A: khách hàng và đơn hàng

Một khách hàng có 200 đơn đã thanh toán. Thiết kế:

```java
@OneToMany(mappedBy = "customer", cascade = CascadeType.ALL)
private List<PurchaseOrder> orders;
```

**Rủi ro:** nếu xóa customer để xử lý yêu cầu đóng tài khoản, `REMOVE` có thể lan tới 200 đơn và toàn bộ dữ liệu chi tiết. Hệ thống cần giữ hóa đơn/đối soát có thể vi phạm retention.

**Hướng thiết kế:** đánh giá quy trình ẩn danh hóa, soft-delete, bảo quản đơn lịch sử và tách lifecycle. Không tự cascade REMOVE chỉ vì quan hệ là một-nhiều.

### Tình huống B: bài viết và thẻ

Một `Post` có nhiều `Tag`, các tag được nhiều bài viết dùng. `Post.tags` là `@ManyToMany`.

**Rủi ro:** `CascadeType.ALL` có thể khiến xóa post cố xóa cả tag được chia sẻ.

**Hướng thiết kế:** không cascade REMOVE lên Tag. Chỉ xử lý liên kết post-tag và để Tag có vòng đời quản lý riêng.

### Tình huống C: đơn hàng và dòng hàng

Dòng hàng không có ý nghĩa nếu không có đơn, không được chia sẻ, và service quản lý sửa dòng qua aggregate root.

**Kết luận:** `ALL + orphanRemoval` có thể phù hợp nếu chấp nhận cả MERGE/REFRESH/DETACH lan xuống line. Nếu thực tế chỉ cần PERSIST + REMOVE, chọn tập hẹp hơn.

### Tình huống D: tài khoản và thiết lập giao diện

Preferences chỉ tồn tại với một account; không được chia sẻ; xóa account đồng nghĩa xóa preferences.

**Kết luận:** `@OneToOne(cascade = ALL, orphanRemoval = true)` là một ứng viên hợp lý. Vẫn cần xem chính sách xóa account và liệu refresh/detach/merge toàn graph có thật sự mong muốn.

### Tình huống E: nhân viên và phòng ban

Một nhân viên thuộc một phòng ban, nhiều nhân viên cùng phòng.

**Kết luận:** `@ManyToOne Department` thường không cascade. Xóa nhân viên không được xóa phòng ban. Khi cần chuyển phòng, sửa FK/quan hệ theo transaction và invariant riêng.

### Tình huống F: thư mục và file

Mỗi file có thể thuộc nhiều collection hoặc được chia sẻ bởi nhiều user. Xóa thư mục chỉ nên xóa liên kết hoặc trạng thái tham chiếu.

**Kết luận:** không giả định file là dependent entity chỉ vì được chứa trong collection; `ALL` có thể dẫn đến xóa dữ liệu mà user khác đang sử dụng.

### Tình huống G: order có payment history

`Order` có nhiều `PaymentTransaction` đã được ghi nhận và đối soát. Khi order bị hủy, dữ liệu thanh toán vẫn phải lưu.

**Kết luận:** không cascade REMOVE tùy tiện từ order sang payment history; dùng trạng thái nghiệp vụ, retention và quy trình hoàn tiền riêng.

## 32. Câu hỏi tự kiểm tra

**1. `CascadeType.ALL` bao gồm những gì?**

Gồm `PERSIST`, `MERGE`, `REMOVE`, `REFRESH` và `DETACH`. Không phải chỉ persist và remove.

**2. Có bắt buộc bật cascade trên cả hai chiều của quan hệ bidirectional không?**

Không. Cascade có hướng và độc lập với việc đồng bộ owning/inverse side. Thường lan từ aggregate root tới dependent, không phải cả hai chiều.

**3. Một `@ManyToOne` từ OrderLine tới Product có nên dùng `ALL` không?**

Thường không, vì Product độc lập và có thể được nhiều OrderLine dùng chung. `ALL` bao gồm REMOVE/MERGE/REFRESH/DETACH không phù hợp vòng đời.

**4. Vì sao `@ManyToMany(cascade = ALL)` nguy hiểm?**

Các entity đích thường dùng chung. Cascade REMOVE có thể cố xóa entity chung thay vì chỉ xóa hàng trong join table, đồng thời không phải lựa chọn portable cho REMOVE theo JPA.

**5. `CascadeType.REMOVE` có tự xóa child khi xóa nó khỏi collection không?**

Không chỉ vì remove khỏi collection. Trường hợp đó là mục tiêu của `orphanRemoval = true` khi child thuộc vòng đời parent.

**6. `orphanRemoval = true` có nằm trong `CascadeType.ALL` không?**

Không. Đây là một thuộc tính riêng của `@OneToOne`/`@OneToMany`.

**7. Vì sao `CascadeType.MERGE` cần được đánh giá cẩn thận?**

Nó có thể sao chép state của detached graph đã cũ vào managed graph, gây ghi đè dữ liệu nếu không có version và application command semantics phù hợp.

**8. `CascadeType.REFRESH` có thể làm mất dữ liệu không?**

Có thể làm mất pending local changes của các child được refresh khi nó lan từ parent qua cascade.

**9. `CascadeType.DETACH` làm gì?**

Khi detach parent, nó có thể detach các target theo cạnh được cấu hình, khiến thay đổi tiếp theo trên chúng không tự được JPA theo dõi.

**10. Cascade JPA có tương đương SQL `ON DELETE CASCADE` không?**

Không. JPA cascade truyền entity operations trong persistence context; SQL ON DELETE CASCADE là ràng buộc database khi xóa row.

**11. Bulk JPQL DELETE có gọi cascade REMOVE như `em.remove(entity)` không?**

Không theo cơ chế entity-by-entity thông thường. Cần thiết kế FK/DB cascade hoặc xử lý bulk phù hợp.

**12. Có `@Version` thì lỡ cascade REMOVE tới Product có an toàn chưa?**

Chưa. `@Version` bảo vệ concurrency, không thể hiểu policy “đơn hàng không được xóa sản phẩm dùng chung”.

**13. Vì sao xóa Order có thể cần xóa Line nhưng không xóa Customer?**

Line là dependent theo aggregate; Customer là entity độc lập được nhiều order tham chiếu và có vòng đời riêng.

**14. `fetch = LAZY` có làm CascadeType.ALL chỉ hoạt động khi collection đã được đọc trước không?**

Không nên hiểu cascade qua fetch kiểu đó. Cascade operations được xác định theo mapping/persistence semantics; provider có thể phải truy cập dữ liệu liên quan để thực thi operation. LAZY và cascade giải quyết hai vấn đề khác nhau.

**15. Nếu một aggregate chỉ cần tạo child mới cùng parent, nên chọn gì?**

Cân nhắc `CascadeType.PERSIST` thay vì `ALL`, nếu không muốn tự động merge/remove/refresh/detach child.

**16. Sau khi `em.remove(order)` gọi thành công thì database chắc chắn đã xóa chưa?**

Chưa. SQL có thể được thực thi ở flush/commit, và transaction vẫn có thể rollback. Chỉ coi kết quả bền vững sau commit thành công.

**17. Muốn bỏ một child persistent và xóa nó khỏi DB khi tách khỏi parent, tính năng gì phù hợp?**

`orphanRemoval = true` trên `@OneToMany` hoặc `@OneToOne` nếu child có ownership/lifecycle phụ thuộc như thiết kế.

**18. Vì sao không nên nhận một detached graph thiếu các field từ REST rồi `merge` toàn bộ?**

Vì graph không đầy đủ hoặc stale có thể làm thay đổi/xóa dữ liệu ngoài ý muốn. Nên nhận command DTO, load managed aggregate và áp dụng thay đổi có chủ đích.

## 33. Tổng kết: `ALL` phải được chứng minh bằng vòng đời, không phải sự tiện tay

`CascadeType.ALL` là công cụ mạnh để quản lý **đồ thị entity có vòng đời gắn chặt**. Khi đúng phạm vi, nó giúp tạo aggregate trong một transaction, xóa dependent entities và duy trì object graph theo thao tác JPA.

Nhưng vì `ALL` bao gồm **PERSIST, MERGE, REMOVE, REFRESH và DETACH**, một annotation ngắn có thể vô tình:

- Xóa entity dùng chung.
- Persist/merge những object không thuộc quyền quản lý của source.
- Ghi đè detached state cũ.
- Xóa pending changes khi refresh.
- Ngừng dirty checking khi detach.
- Phát sinh tác động nhiều tầng trên graph lớn.

Mẫu phù hợp khi child thuộc vòng đời parent:

```java
// Aggregate root:
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Mẫu phù hợp cho entity dùng chung:

```java
// Reference không sở hữu lifecycle:
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private CatalogProduct product;
```

Mẫu chọn lọc khi chỉ cần vài thao tác:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<OrderLine> lines;
```

Một câu hỏi nên được đặt trước mọi `cascade = CascadeType.ALL`:

> **Nếu ai đó gọi `remove`, `merge`, `refresh` hoặc `detach` trên entity nguồn, có chắc muốn operation đó lan tới toàn bộ target theo quan hệ này không?**

Nếu chưa chắc, **chọn cascade hẹp hơn theo từng operation** và xác định rõ ràng transaction, orphan removal, ownership và database constraints. Đó là cách khai thác lợi ích của JPA cascade mà không biến quan hệ Java thành nguồn rủi ro dữ liệu.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `CascadeType`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/cascadetype)
- [Jakarta Persistence API — `@OneToMany`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/onetomany)
- [Jakarta Persistence API — `@ManyToOne`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/manytoone)
- [Jakarta Persistence API — `@ManyToMany`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/manytomany)
- [Jakarta Persistence API — `@OneToOne`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/onetoone)
