# Kiểm thử đồ thị dùng chung để tránh xóa dữ liệu ngoài ý muốn

Trong JPA, `cascade` và `orphanRemoval` quyết định các thao tác lên một entity có thể lan truyền tới những entity khác trong **đồ thị đối tượng** (*object graph*). Hai cơ chế này rất thuận tiện khi entity con thực sự thuộc vòng đời của entity cha. Tuy nhiên, nếu đồ thị có những entity **dùng chung** (*shared entities*), một cấu hình xóa thiếu cẩn trọng có thể xóa cả dữ liệu mà những entity khác vẫn đang sử dụng.

Ví dụ: hai đơn hàng có những dòng hàng khác nhau, nhưng cùng tham chiếu đến một sản phẩm. Nếu xóa một đơn hàng, hệ thống cần xóa những dòng hàng của đơn đó, **không được xóa sản phẩm** vì sản phẩm vẫn thuộc danh mục và còn được các đơn hàng khác tham chiếu.

Bài **“Kiểm thử đồ thị dùng chung để tránh xóa dữ liệu ngoài ý muốn”** thuộc chương **Cascade và orphanRemoval** trong chủ đề **Data Persistence Relational Access ORM JPA**. Trọng tâm không chỉ là biết chọn annotation, mà còn xây dựng các **integration test có cấu trúc đồ thị đủ khó** để phát hiện cấu hình cascade xóa sai, orphan removal không đúng đối tượng và những lỗi bị che khuất bởi persistence context.

Sau bài học, người học có thể:

- Xác định entity nào **sở hữu vòng đời**, entity nào chỉ **được tham chiếu hoặc dùng chung**.
- Phân biệt xóa root entity, xóa entity con và chỉ gỡ một liên kết.
- Dựng fixture có ít nhất **hai root dùng chung một target** để kiểm thử tác động của `CascadeType.REMOVE`, `CascadeType.ALL` và `orphanRemoval`.
- Viết integration test xác nhận cả **dữ liệu phải bị xóa** và **dữ liệu bắt buộc phải còn**.
- Dùng `flush()`, `clear()`, transaction mới và truy vấn kiểm chứng để không bị first-level cache đánh lừa.
- Kiểm thử ranh giới rollback, database constraints, truy cập đồng thời và các thay đổi mapping về sau.

Ví dụ dùng Jakarta Persistence (`jakarta.persistence`), Java 17+ và JUnit Jupiter (JUnit 5). Các đoạn code là mẫu thiết kế để đưa vào dự án có persistence unit, migration và test database phù hợp.

## 1. Vấn đề cốt lõi: liên kết không đồng nghĩa sở hữu vòng đời

Xét hai loại mối quan hệ:

1. **Đơn hàng – dòng hàng:** mỗi `OrderLine` thuộc một `PurchaseOrder`. Xóa đơn hàng có thể cần xóa các dòng hàng của nó. Một dòng hàng bị gỡ khỏi đơn hàng có thể bị xóa theo `orphanRemoval = true`.
2. **Dòng hàng – sản phẩm:** mỗi `OrderLine` tham chiếu một `Product` thuộc danh mục dùng chung. Xóa dòng hàng **không được xóa Product** vì sản phẩm có thể được nhiều dòng hàng của nhiều đơn khác cùng sử dụng.

Đồ thị minh họa:

```text
  PurchaseOrder A                         PurchaseOrder B
        │                                        │
        │ sở hữu dòng hàng                       │ sở hữu dòng hàng
        ▼                                        ▼
    OrderLine A1                              OrderLine B1
        │                                        │
        └───────────────┐         ┌──────────────┘
                        ▼         ▼
                     Product P
                 (entity dùng chung)


  PurchaseOrder A
        │
        ▼
    OrderLine A2
        │
        ▼
     Product Q
  (sản phẩm khác)
```

Khi xóa `PurchaseOrder A`, kết quả nghiệp vụ mong muốn:

```text
BỊ XÓA:
  PurchaseOrder A
  OrderLine A1
  OrderLine A2

PHẢI CÒN:
  PurchaseOrder B
  OrderLine B1
  Product P
  Product Q
```

Đặc biệt, **Product Q vẫn phải còn ngay cả khi sau khi xóa A không có dòng hàng nào còn tham chiếu nó**. Việc không còn được tham chiếu bởi OrderLine không làm Product trở thành một entity con thuộc vòng đời Order.

Chính tình huống Product Q giúp một bài test phát hiện việc xóa sai mà foreign key không nhất thiết ngăn được: nếu không có hàng nào khác tham chiếu Q, một cascade REMOVE sai có thể xóa Q hoàn toàn thành công, không xuất hiện lỗi DB.

### Quy tắc quan trọng

**Cascade REMOVE và orphan removal phải đi theo ownership của vòng đời, không đơn giản đi theo hướng của quan hệ JPA hoặc việc một entity có chứa tham chiếu tới entity khác.**

Một entity có field `product` không có nghĩa nó được quyền xóa Product. Một entity là owning side của foreign key cũng không có nghĩa nó là chủ sở hữu vòng đời của target.

## 2. Phân biệt cascade và orphanRemoval

### Cascade: lan truyền thao tác EntityManager

Một association có thể khai báo:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.REMOVE}
)
private List<OrderLine> lines = new ArrayList<>();
```

Điều này cho phép `persist(order)` lan truyền persist tới các `OrderLine`; `remove(order)` lan truyền remove tới những dòng hàng liên quan.

Các cascade chuẩn thông dụng:

| Cascade | Tác dụng cốt lõi | Câu hỏi nghiệp vụ |
| --- | --- | --- |
| `PERSIST` | Lan truyền thao tác persist | Khi tạo cha có tự tạo con không? |
| `MERGE` | Lan truyền merge | Có chủ đích đồng bộ detached graph không? |
| `REMOVE` | Lan truyền remove | Xóa cha có được xóa target không? |
| `REFRESH` | Lan truyền refresh | Có làm mới state entity liên quan không? |
| `DETACH` | Lan truyền detach | Có tách các entity liên quan khỏi context không? |
| `ALL` | Bao gồm tất cả cascade chuẩn | Có thực sự muốn **mọi** thao tác kể cả REMOVE lan truyền? |

Với entity dùng chung, đặc biệt cẩn trọng với `REMOVE` và `ALL`.

### Orphan removal: xóa entity con bị gỡ khỏi quan hệ sở hữu

`orphanRemoval = true` được hỗ trợ trên `@OneToOne` và `@OneToMany` theo ngữ nghĩa của JPA.

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Nếu một `OrderLine` persistent bị loại khỏi relationship sở hữu, nó có thể được xóa khi provider đồng bộ persistence context. Đây không phải `CascadeType.REMOVE`: orphan removal có thể phát sinh **khi gỡ con khỏi quan hệ mà không xóa cha**.

Hai trường hợp:

```java
em.remove(order);       // Xóa cha: cascade REMOVE nếu được khai báo.
order.removeLine(line); // Gỡ con: orphanRemoval xử lý line nếu khai báo.
```

Khi dùng `orphanRemoval = true`, JPA còn có ngữ nghĩa xóa các target khi root bị remove trên quan hệ sở hữu phù hợp. Tuy vậy, để diễn đạt rõ lifecycle của các dòng hàng qua những thao tác khác nhau, ví dụ dưới đây dùng cấu hình cụ thể và kiểm thử hành vi cần thiết.

### So sánh theo thao tác

| Thao tác | Cascade REMOVE | orphanRemoval |
| --- | --- | --- |
| `em.remove(order)` | Có thể lan truyền remove tới OrderLine | Cơ chế xóa target phụ thuộc association, ngữ nghĩa ownership |
| `order.removeLine(line)` khi order vẫn sống | Không tự kích hoạt chỉ vì gỡ một phần tử | Có thể xóa OrderLine bị orphan |
| Gỡ tham chiếu tới Product dùng chung | Không nên xóa Product | Không nên dùng orphanRemoval trên Product dùng chung |
| Xóa root có entity target đang được root khác dùng | Nguy cơ xóa nhầm target | Nguy cơ nếu mô hình nhầm target dùng chung thành con sở hữu |

**Không áp dụng orphan removal chỉ vì collection có chữ “children” trong code.** Hãy hỏi entity bị loại khỏi collection có thật sự phải kết thúc vòng đời hay không.

## 3. Phân loại cạnh trong đồ thị trước khi viết test

Một mô hình dễ kiểm thử khi mỗi cạnh được phân loại theo semantics.

| Cạnh | Cardinality | Ownership vòng đời | Cấu hình gợi ý | Khi gỡ/xóa |
| --- | --- | --- | --- | --- |
| `PurchaseOrder → OrderLine` | OneToMany | Order sở hữu dòng hàng | Cascade PERSIST/REMOVE, orphanRemoval true khi phù hợp | Xóa dòng hàng thuộc Order |
| `OrderLine → Product` | ManyToOne | Không: Product độc lập | Không cascade REMOVE/ALL | Chỉ loại tham chiếu/dòng hàng, giữ Product |
| `Playlist ↔ Song` | ManyToMany | Song độc lập, dùng chung | Không cascade REMOVE/ALL tới Song | Xóa hàng join, giữ Song |
| `Employee → Department` | ManyToOne | Department độc lập, nhiều Employee dùng | Không cascade REMOVE | Xóa Employee không xóa Department |
| `Customer → Address` | Tùy mô hình | Phụ thuộc Address có độc lập/dùng chung không | Chỉ cascade remove khi thực sự độc quyền vòng đời | Thiết kế theo ownership thực tế |
| `Account → Profile` | OneToOne | Có thể phụ thuộc hoặc độc lập | Xét quy tắc nghiệp vụ | Không suy từ OneToOne rằng luôn cần orphan removal |

Đặc biệt với ManyToOne và ManyToMany, áp dụng `CascadeType.REMOVE` có thể không portable theo quy tắc JPA và tiềm ẩn xóa nhầm shared targets. Với `@ManyToMany`, hãy mặc định hai phía là các entity có vòng đời độc lập, chỉ dùng cascade khi nghiệp vụ chứng minh được điều ngược lại và provider/đặc tả cho phép.

## 4. Lập mô hình test bằng ba loại entity

Ví dụ gồm `Product`, `PurchaseOrder` và `OrderLine`. Ý định thiết kế:

- Product là danh mục sản phẩm tồn tại độc lập.
- PurchaseOrder sở hữu vòng đời của OrderLine.
- OrderLine tham chiếu Product nhưng không sở hữu vòng đời Product.
- Nhiều OrderLine có thể tham chiếu cùng Product.
- Một OrderLine chỉ thuộc một PurchaseOrder.

Schema minh họa:

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,

    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),

    CONSTRAINT fk_lines_product
        FOREIGN KEY (product_id) REFERENCES products(id),

    CONSTRAINT ck_lines_quantity CHECK (quantity > 0)
);
```

Cú pháp `GENERATED BY DEFAULT AS IDENTITY` là minh họa; khi dùng PostgreSQL, MySQL hoặc database khác, cần chỉnh DDL theo dialect. Trong dự án production, constraint cũng có thể được quản lý bằng migration độc lập.

Ở schema này, foreign key giữ tính toàn vẹn tham chiếu; nó **không diễn đạt toàn bộ quy tắc vòng đời**. Ví dụ nếu chỉ có một OrderLine trỏ Product Q, database có thể cho phép xóa cả OrderLine và Product Q dù nghiệp vụ yêu cầu giữ Product Q. Vì vậy **constraint cần nhưng chưa đủ: integration test phải khẳng định dữ liệu còn lại**.

## 5. Entity Product: không phụ thuộc OrderLine

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String sku;

    protected Product() {}

    public Product(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku");
        }
        this.sku = sku.trim();
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
```

Entity Product không cần collection `orderLines` chỉ để làm test. Nếu muốn điều hướng ngược, có thể khai báo inverse `@OneToMany(mappedBy = "product")`, nhưng **không đặt cascade REMOVE từ Product tới OrderLine hoặc ngược lại nếu nó làm trái vòng đời nghiệp vụ**.

Product có identity riêng, có thể tồn tại ngay cả khi chưa có đơn hàng.

## 6. Entity PurchaseOrder: sở hữu vòng đời OrderLine

```java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @OneToMany(
        mappedBy = "order",
        cascade = {CascadeType.PERSIST, CascadeType.REMOVE},
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(String orderNumber) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("orderNumber");
        }
        this.orderNumber = orderNumber.trim();
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public OrderLine addLine(Product product, int quantity) {
        OrderLine line = new OrderLine(this, product, quantity);
        lines.add(line);
        return line;
    }

    public void removeLine(OrderLine line) {
        if (line != null && lines.remove(line)) {
            line.detachFromOrder();
        }
    }
}
```

Giải thích mapping:

- `mappedBy = "order"` trỏ đến field `OrderLine.order`; phía `OrderLine` sở hữu foreign key `order_id`.
- Cascade `PERSIST` cho phép persist Order cùng các dòng hàng mới.
- Cascade `REMOVE` cho phép xóa Order cùng các dòng hàng của nó.
- `orphanRemoval = true` cho phép gỡ một OrderLine khỏi Order và xóa entity dòng hàng đó nếu đúng vòng đời.
- Không có cascade từ Order tới Product vì không có association trực tiếp Order–Product trong ví dụ này.

Dùng `CascadeType.ALL` trên Order–OrderLine cũng có thể hợp lý nếu dòng hàng thật sự có vòng đời hoàn toàn phụ thuộc Order, nhưng đoạn code cố ý khai báo **đúng thao tác cần thiết** để tránh lan truyền không cần thiết.

## 7. Entity OrderLine: tham chiếu Product dùng chung, tuyệt đối không cascade xóa Product

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

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
    private Product product;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    OrderLine(PurchaseOrder order, Product product, int quantity) {
        if (order == null || product == null) {
            throw new IllegalArgumentException("Missing association");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }

        this.order = order;
        this.product = product;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public Product getProduct() {
        return product;
    }

    public int getQuantity() {
        return quantity;
    }

    void detachFromOrder() {
        this.order = null;
    }
}
```

Chú ý dòng:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id", nullable = false)
private Product product;
```

**Không có `cascade = CascadeType.REMOVE` và không có `cascade = CascadeType.ALL`.**

Đây là quyết định bảo vệ Product dùng chung. Xóa OrderLine phải xóa **dòng hàng** chứ không xóa **sản phẩm**.

Method `detachFromOrder()` đặt reference Java về null để đồng bộ object graph khi gỡ dòng hàng. Vì mapping `order_id` được khai báo bắt buộc, thao tác này chỉ được dùng cùng workflow orphan removal để xóa line, không phải để giữ một OrderLine persistent không có Order. Tùy provider và ràng buộc, thứ tự SQL khi xóa orphan cần được kiểm thử trên DB thực tế; nếu provider cố update FK về null trước DELETE, sẽ gặp lỗi và mapping/service cần được điều chỉnh cho phù hợp.

## 8. Anti-pattern: cascade REMOVE chạy qua cạnh dùng chung

Đoạn sau rất nguy hiểm:

```java
// SAI về ownership của vòng đời:
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.ALL
)
@JoinColumn(name = "product_id")
private Product product;
```

`CascadeType.ALL` bao gồm `REMOVE`. Nếu khi xóa OrderLine, provider lan truyền remove sang Product, hệ thống có thể cố xóa sản phẩm dùng chung.

Giả sử Product P còn được OrderLine B1 tham chiếu. Nếu database có foreign key, thao tác xóa Product P có thể gây constraint violation. Nhờ đó dữ liệu không bị xóa, nhưng nghiệp vụ xóa đơn hàng thất bại.

Nguy hiểm hơn, Product Q chỉ còn tham chiếu bởi OrderLine A2. Nếu xóa Order A và A2 trước, cascade remove sai có thể xóa Product Q mà database **không còn foreign key nào cản**, dẫn tới mất sản phẩm hợp lệ khỏi danh mục.

Vì vậy test cần phát hiện cả hai tình huống:

1. **Target đang được root khác dùng:** thao tác xóa không được hủy target hoặc làm root khác hỏng.
2. **Target không còn liên kết sau thao tác:** vẫn phải giữ target nếu đó là entity có vòng đời độc lập.

Chỉ kiểm tra “không có foreign key exception” không đủ. Có những lỗi xóa nhầm diễn ra **hoàn toàn hợp lệ ở SQL** nhưng sai về nghiệp vụ.

## 9. Vì sao test phải có đồ thị dùng chung thực sự?

Một fixture quá đơn giản:

```text
Order A ──► Line A1 ──► Product P
```

không chứng minh được quy tắc sản phẩm dùng chung. Với một root duy nhất, test có thể đi qua những trường hợp thuận lợi: xóa Order, xóa Line, xóa luôn Product rồi vẫn commit thành công. Nếu assertion chỉ kiểm tra Order không còn, test sẽ **xanh dù Product bị xóa sai**.

Fixture tốt hơn:

```text
             Product P (shared)
                 ▲      ▲
                 │      │
Order A ─► Line A1      Line B1 ◄─ Order B
    │
    └────► Line A2 ────► Product Q
                           (không còn ai dùng
                            sau khi Order A bị xóa)
```

Fixture này kiểm thử hai invariant độc lập:

- **Invariant A:** Product P phải còn vì Order B vẫn dùng.
- **Invariant B:** Product Q cũng phải còn vì Product không thuộc vòng đời của OrderLine.

Cùng lúc kiểm tra thêm:

- Order A bị xóa.
- Line A1 và A2 bị xóa.
- Order B vẫn tồn tại.
- Line B1 vẫn tồn tại.
- B1 vẫn tham chiếu Product P.

Một test có đủ các assertion sẽ phát hiện việc xóa nhầm target, mất liên kết, cascade không chạy, orphan không xóa hoặc rollback do constraint.

## 10. Thiết kế fixture có ID rõ ràng và dữ liệu cô lập

Ta tạo hai Order dùng chung Product P và một Product Q khác.

Ví dụ logic fixture:

```java
Product shared = new Product("P-SHARED");
Product independent = new Product("P-INDEPENDENT");

PurchaseOrder first = new PurchaseOrder("ORDER-A");
PurchaseOrder second = new PurchaseOrder("ORDER-B");

OrderLine lineA1 = first.addLine(shared, 2);
OrderLine lineA2 = first.addLine(independent, 1);
OrderLine lineB1 = second.addLine(shared, 3);

em.persist(shared);
em.persist(independent);
em.persist(first);
em.persist(second);

// Cascade PERSIST từ Order tới OrderLine.
// Không cascade persist/remove tới Product.
```

Khi flush và commit thành công, database có:

| Entity | ID giả định | Liên kết |
| --- | ---: | --- |
| Product P | 100 | Dùng chung |
| Product Q | 200 | Độc lập |
| Order A | 10 | Có A1 và A2 |
| Order B | 20 | Có B1 |
| Line A1 | 1000 | Order A → Product P |
| Line A2 | 1001 | Order A → Product Q |
| Line B1 | 2000 | Order B → Product P |

Các ID chỉ minh họa; test thực tế phải lấy ID từ entity sau khi persist/flush, không hardcode ID giả định.

Khi các test chạy song song hoặc dùng lại một database, sử dụng order number và SKU riêng cho từng fixture (ví dụ kết hợp UUID), tránh test nọ ảnh hưởng test kia.

Một quy tắc quan trọng: **fixture phải được commit trước khi bắt đầu thao tác xóa cần kiểm thử**, và kết quả phải được đọc lại trong một persistence context mới. Nếu tất cả nằm trong một persistence context vừa tạo vừa xóa, first-level cache có thể che giấu tình trạng DB.

## 11. Khung JUnit integration test dùng EntityManagerFactory

Ví dụ sau giả định dự án có persistence unit test tên `integration-test`, entity mappings đã đăng ký và test database đã được chuẩn bị schema.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import java.util.UUID;
import java.util.function.Function;

import static org.junit.jupiter.api.Assertions.*;

class SharedGraphDeletionIT {

    private static EntityManagerFactory emf;

    @BeforeAll
    static void openFactory() {
        emf = Persistence.createEntityManagerFactory("integration-test");
    }

    @AfterAll
    static void closeFactory() {
        if (emf != null) {
            emf.close();
        }
    }

    private static <T> T inTransaction(
            Function<EntityManager, T> operation) {

        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();
            T result = operation.apply(em);
            em.getTransaction().commit();
            return result;
        } catch (RuntimeException ex) {
            if (em.getTransaction().isActive()) {
                try {
                    em.getTransaction().rollback();
                } catch (RuntimeException rollbackEx) {
                    ex.addSuppressed(rollbackEx);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }

    private static <T> T readFresh(
            Function<EntityManager, T> operation) {

        EntityManager em = emf.createEntityManager();

        try {
            return operation.apply(em);
        } finally {
            em.close();
        }
    }

    // Các test và seedGraph() sẽ được bổ sung ở phần kế tiếp.
}
```

Trong môi trường Spring/JTA, transaction thường do framework/container quản lý thay vì gọi `em.getTransaction()`. Các helper trên chỉ minh họa một cách kiểm soát **resource-local transactions** độc lập giữa bước thiết lập dữ liệu và bước kiểm chứng.

Lợi ích của việc mỗi giai đoạn có `EntityManager` mới:

1. Fixture được commit rồi mới kiểm thử xóa.
2. Thao tác xóa thực thi trong transaction riêng.
3. Assertion được đọc từ context mới, không dựa vào managed object cũ.
4. Exception/constraint xuất hiện ở flush hoặc commit được nhìn thấy.
5. Mỗi test có thể tự tạo dữ liệu có ID và SKU riêng.

Không dùng shared `EntityManager` static cho các test chạy song song: EntityManager không được xem là tài nguyên thread-safe để nhiều thread tự ý chia sẻ.

## 12. Định nghĩa GraphIds và tạo fixture đã commit

Trong class test, thêm record chứa định danh để không phải giữ các entity managed qua transaction:

```java
record GraphIds(
    Long orderAId,
    Long orderBId,
    Long sharedProductId,
    Long independentProductId,
    Long lineA1Id,
    Long lineA2Id,
    Long lineB1Id
) {}
```

Method tạo fixture:

```java
private GraphIds seedGraph() {
    return inTransaction(em -> {
        String suffix = UUID.randomUUID().toString();

        Product shared =
            new Product("SHARED-" + suffix);
        Product independent =
            new Product("INDEPENDENT-" + suffix);

        em.persist(shared);
        em.persist(independent);

        PurchaseOrder orderA =
            new PurchaseOrder("ORDER-A-" + suffix);
        PurchaseOrder orderB =
            new PurchaseOrder("ORDER-B-" + suffix);

        OrderLine lineA1 = orderA.addLine(shared, 2);
        OrderLine lineA2 = orderA.addLine(independent, 1);
        OrderLine lineB1 = orderB.addLine(shared, 3);

        em.persist(orderA);
        em.persist(orderB);

        // Đảm bảo các IDENTITY ID được tạo trước khi đóng transaction.
        em.flush();

        return new GraphIds(
            orderA.getId(),
            orderB.getId(),
            shared.getId(),
            independent.getId(),
            lineA1.getId(),
            lineA2.getId(),
            lineB1.getId()
        );
    });
}
```

`em.flush()` ở đây giúp làm rõ thời điểm identity được cấp và SQL cần thiết được đồng bộ, nhưng bản thân nó chưa commit. Helper `inTransaction` mới commit trước khi trả dữ liệu ra bên ngoài.

Các đối tượng entity không thoát ra khỏi helper; test chỉ nhận IDs. Điều này giúp tránh việc dùng nhầm một object detached từ context fixture.

### SQL kiểm tra fixture

Có thể dùng query trực tiếp hoặc JPQL:

```sql
SELECT order_id, product_id, quantity
FROM order_lines
WHERE order_id IN (?, ?);
```

Để xác nhận cả hai Order dùng chung Product P:

```sql
SELECT product_id, COUNT(DISTINCT order_id)
FROM order_lines
GROUP BY product_id
HAVING COUNT(DISTINCT order_id) > 1;
```

Điểm quyết định là fixture phải có **ít nhất một Product được hai Order khác nhau cùng dùng**. Nếu không, bài test không thực sự kiểm thử đồ thị dùng chung.

## 13. Test 1: xóa một root, target dùng chung phải còn

Mục tiêu:

- Xóa Order A.
- Hai dòng hàng thuộc A bị xóa.
- Order B và dòng hàng của B vẫn còn.
- Product P và Product Q đều còn.

JUnit test:

```java
@Test
void removingOneOrderDoesNotDeleteSharedProducts() {
    GraphIds ids = seedGraph();

    inTransaction(em -> {
        PurchaseOrder orderA =
            em.find(PurchaseOrder.class, ids.orderAId());

        assertNotNull(orderA);

        em.remove(orderA);
        em.flush();

        return null;
    });

    readFresh(em -> {
        assertNull(
            em.find(PurchaseOrder.class, ids.orderAId())
        );

        assertNotNull(
            em.find(PurchaseOrder.class, ids.orderBId())
        );

        assertNull(
            em.find(OrderLine.class, ids.lineA1Id())
        );
        assertNull(
            em.find(OrderLine.class, ids.lineA2Id())
        );
        assertNotNull(
            em.find(OrderLine.class, ids.lineB1Id())
        );

        assertNotNull(
            em.find(Product.class, ids.sharedProductId())
        );
        assertNotNull(
            em.find(Product.class, ids.independentProductId())
        );

        return null;
    });
}
```

Test có cả assertion **bị xóa** và **không bị xóa**. Nếu vô tình thêm cascade REMOVE từ `OrderLine.product`, test có thể thất bại vì:

- Provider cố xóa Product P trong khi B1 còn tham chiếu, gây foreign key violation; hoặc
- Provider xóa Product Q thành công nhưng assertion `find(Product Q) != null` thất bại; hoặc
- Một cấu hình khác làm thay đổi graph sai ngoài mong đợi.

### Vì sao cần assertion Product Q?

Giả sử chỉ kiểm tra Product P còn. Database FK có thể từ chối cascade xóa P do B1 tham chiếu. Test sẽ thất bại, điều đó tốt; nhưng không bao phủ một bug nguy hiểm hơn là **xóa nhầm một Product không có tham chiếu còn lại mà không phát lỗi**.

Product Q chứng minh rằng **Product được giữ vì vòng đời độc lập, không phải chỉ vì đang có FK bảo vệ từ dòng hàng khác**.

### Đừng chỉ assert không có exception

Đoạn sau là test quá yếu:

```java
assertDoesNotThrow(() -> deleteOrder(orderAId));
```

Vì operation có thể xóa Order, Line và cả Product nhưng commit hoàn toàn thành công. Phải đọc lại DB để kiểm chứng **những entity bắt buộc phải giữ**.

## 14. Test 2: gỡ một dòng hàng, orphanRemoval chỉ xóa OrderLine

Ở test này, Order A vẫn tồn tại, nhưng một dòng hàng được gỡ khỏi collection.

```java
@Test
void removingOneLineDeletesOnlyTheOrphanLine() {
    GraphIds ids = seedGraph();

    inTransaction(em -> {
        PurchaseOrder orderA =
            em.find(PurchaseOrder.class, ids.orderAId());

        OrderLine lineA1 =
            em.find(OrderLine.class, ids.lineA1Id());

        assertNotNull(orderA);
        assertNotNull(lineA1);

        orderA.removeLine(lineA1);
        em.flush();

        return null;
    });

    readFresh(em -> {
        assertNotNull(
            em.find(PurchaseOrder.class, ids.orderAId())
        );
        assertNotNull(
            em.find(PurchaseOrder.class, ids.orderBId())
        );

        assertNull(
            em.find(OrderLine.class, ids.lineA1Id())
        );
        assertNotNull(
            em.find(OrderLine.class, ids.lineA2Id())
        );
        assertNotNull(
            em.find(OrderLine.class, ids.lineB1Id())
        );

        assertNotNull(
            em.find(Product.class, ids.sharedProductId())
        );
        assertNotNull(
            em.find(Product.class, ids.independentProductId())
        );

        return null;
    });
}
```

Test xác nhận `orphanRemoval` đang tác động đúng đối tượng: **OrderLine A1**, không phải `Product P`.

### Vì sao dùng entity persistent chứ không gỡ một object mới vừa tạo?

Orphan removal có ngữ nghĩa dành cho entity bị gỡ khỏi quan hệ sở hữu. Với các entity new chưa từng được persistent và với thao tác chuyển/reassign một orphan giữa các owner, các chi tiết lifecycle có thể khác nhau hoặc không portable. Nếu mục tiêu là kiểm chứng xóa một dòng hàng **đã lưu**, fixture nên commit OrderLine trước, rồi gỡ trong transaction mới.

### Hai phía quan hệ phải được đồng bộ

`PurchaseOrder.lines` là phía inverse của `@OneToMany(mappedBy = "order")`, còn `OrderLine.order` sở hữu FK. Helper `removeLine()` cập nhật collection và reference để object graph không mâu thuẫn.

Nếu test chỉ xóa khỏi inverse collection mà không sửa owner side trong một mapping không có orphanRemoval, thay đổi DB có thể không như mong đợi. Vì vậy nên kiểm thử chính API domain được ứng dụng sử dụng, không dùng reflection để sửa field qua mặt helper.

## 15. Test 3: xóa cả hai Order vẫn không được xóa Product

Sau khi xóa cả Order A và Order B, không còn OrderLine nào tham chiếu Product P. Nhưng nếu Product là danh mục độc lập, Product P vẫn phải còn.

```java
@Test
void deletingAllOrdersStillKeepsProductCatalog() {
    GraphIds ids = seedGraph();

    inTransaction(em -> {
        PurchaseOrder orderA =
            em.find(PurchaseOrder.class, ids.orderAId());
        PurchaseOrder orderB =
            em.find(PurchaseOrder.class, ids.orderBId());

        em.remove(orderA);
        em.remove(orderB);
        em.flush();

        return null;
    });

    readFresh(em -> {
        assertNull(
            em.find(PurchaseOrder.class, ids.orderAId())
        );
        assertNull(
            em.find(PurchaseOrder.class, ids.orderBId())
        );

        assertNull(
            em.find(OrderLine.class, ids.lineA1Id())
        );
        assertNull(
            em.find(OrderLine.class, ids.lineA2Id())
        );
        assertNull(
            em.find(OrderLine.class, ids.lineB1Id())
        );

        assertNotNull(
            em.find(Product.class, ids.sharedProductId())
        );
        assertNotNull(
            em.find(Product.class, ids.independentProductId())
        );

        return null;
    });
}
```

Đây là test rất có giá trị vì nó chứng minh Product còn tồn tại **không phụ thuộc việc các OrderLine còn liên kết**. Nếu mapping sai làm cascade remove tới Product khi xóa Order cuối cùng, test có thể phát hiện mất dữ liệu mà không có foreign key ngăn lại.

Cũng cần xác nhận trong mô hình sản phẩm có chính sách archive hoặc soft delete: nếu nghiệp vụ không cho phép xóa Product đang có lịch sử giao dịch, test phải thể hiện chính sách cụ thể, không chỉ kiểm tra số lượng hàng.

## 16. Test 4: kiểm tra số lượng dòng hàng theo Product

Các assertion từng ID rất rõ ràng, nhưng query aggregate giúp kiểm tra số liên kết còn lại, đặc biệt khi graph lớn.

Một helper:

```java
private long countLinesForProduct(
        EntityManager em, Long productId) {

    return em.createQuery(
        "SELECT COUNT(l) FROM OrderLine l " +
        "WHERE l.product.id = :productId",
        Long.class
    )
    .setParameter("productId", productId)
    .getSingleResult();
}
```

Test xóa Order A:

```java
@Test
void remainingOrderKeepsItsSharedProductLink() {
    GraphIds ids = seedGraph();

    inTransaction(em -> {
        PurchaseOrder orderA =
            em.find(PurchaseOrder.class, ids.orderAId());
        em.remove(orderA);
        return null;
    });

    readFresh(em -> {
        assertEquals(
            1L,
            countLinesForProduct(em, ids.sharedProductId())
        );

        assertEquals(
            0L,
            countLinesForProduct(em, ids.independentProductId())
        );

        assertNotNull(
            em.find(Product.class, ids.sharedProductId())
        );
        assertNotNull(
            em.find(Product.class, ids.independentProductId())
        );

        return null;
    });
}
```

Ở đây:

- Product P có đúng một dòng hàng còn lại (B1).
- Product Q có zero dòng hàng còn lại.
- Cả hai Product vẫn tồn tại.

Bộ assertion này chặt hơn việc chỉ kiểm tra có hay không một Product, vì nó còn bảo vệ **tính đúng của các cạnh trong graph**.

### Đừng nhầm row count với object count trong cache

Nếu chỉ gọi `orderB.getLines().size()` trên một object từng được load trước khi xóa Order A và sau đó tiếp tục sử dụng object ấy, collection trong persistence context có thể chưa phản ánh chính xác kết quả DB theo thời điểm mong muốn. Dùng `EntityManager` mới và query COUNT trực tiếp là cách giảm nguy cơ test bị first-level cache che giấu.

## 17. Test 5: Product không được xóa khi chỉ gỡ association

Một thay đổi nghiệp vụ có thể cho phép thay sản phẩm trong một dòng hàng hoặc xóa một association riêng. Điểm quan trọng: **xóa reference không đồng nghĩa xóa target**.

Với `OrderLine.product` là ManyToOne bắt buộc, không được đặt product về null rồi giữ lại line trong DB vì sẽ vi phạm `product_id NOT NULL`. Thay vì vậy, nghiệp vụ có thể thay Product A bằng Product B:

```java
public void replaceProduct(Product newProduct) {
    if (newProduct == null) {
        throw new IllegalArgumentException("newProduct");
    }
    this.product = newProduct;
}
```

Nếu bổ sung method vào `OrderLine`, test có thể:

1. Tạo Product P và Q.
2. Lấy managed Line A1 đang tham chiếu P.
3. Gọi `lineA1.replaceProduct(Q)`.
4. Commit transaction.
5. Dùng context mới xác nhận A1 tham chiếu Q.
6. Xác nhận cả P và Q đều còn tồn tại.

Ví dụ:

```java
@Test
void replacingProductReferenceDoesNotDeleteOldProduct() {
    GraphIds ids = seedGraph();

    inTransaction(em -> {
        OrderLine line =
            em.find(OrderLine.class, ids.lineA1Id());
        Product replacement =
            em.find(Product.class, ids.independentProductId());

        line.replaceProduct(replacement);
        return null;
    });

    readFresh(em -> {
        OrderLine updated =
            em.find(OrderLine.class, ids.lineA1Id());

        assertEquals(
            ids.independentProductId(),
            updated.getProduct().getId()
        );

        assertNotNull(
            em.find(Product.class, ids.sharedProductId())
        );
        assertNotNull(
            em.find(Product.class, ids.independentProductId())
        );

        return null;
    });
}
```

Test này giả định `replaceProduct` được bổ sung vào `OrderLine`. Nó giúp phát hiện việc nhầm **đổi foreign key** với **xóa entity ở đầu kia**.

## 18. Một test có thể “xanh giả” nếu không kiểm tra sau commit

Giả sử có test:

```java
em.getTransaction().begin();

PurchaseOrder order = em.find(PurchaseOrder.class, id);
em.remove(order);

assertNull(em.find(PurchaseOrder.class, id));

em.getTransaction().rollback();
```

Test trên chưa chứng minh database cuối cùng đã xóa Order hoặc giữ Product đúng.

Các vấn đề:

- `find()` trong cùng context có thể chịu ảnh hưởng trạng thái removed ngay trong bộ nhớ.
- SQL DELETE có thể chưa được gửi.
- Transaction bị rollback nên xóa không được commit.
- Product dùng chung có thể không được truy vấn.
- Không có xác nhận trạng thái cuối cùng của DB.

Mẫu tốt:

```text
SETUP:
  Transaction 1: seed graph → COMMIT

ACTION:
  Transaction 2: remove root → FLUSH → COMMIT

ASSERT:
  EntityManager/context mới:
    kiểm tra row phải mất
    kiểm tra row phải giữ
    kiểm tra liên kết phải còn
```

Khi test hành vi rollback, lại cần một kịch bản khác:

```text
SETUP: commit fixture
ACTION: remove → flush → rollback
ASSERT: context mới thấy graph như trước
```

Không được trộn hai mục đích rồi kết luận từ một assertion.

## 19. Test 6: rollback thao tác xóa phải giữ cả graph

Nếu thao tác xóa bị rollback, database phải không commit những thay đổi của transaction đó. Test riêng:

```java
@Test
void rollbackOfDeleteKeepsOrdersLinesAndProducts() {
    GraphIds ids = seedGraph();

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        PurchaseOrder orderA =
            em.find(PurchaseOrder.class, ids.orderAId());

        em.remove(orderA);
        em.flush();

        em.getTransaction().rollback();
    } finally {
        em.close();
    }

    readFresh(verify -> {
        assertNotNull(
            verify.find(PurchaseOrder.class, ids.orderAId())
        );
        assertNotNull(
            verify.find(PurchaseOrder.class, ids.orderBId())
        );

        assertNotNull(
            verify.find(OrderLine.class, ids.lineA1Id())
        );
        assertNotNull(
            verify.find(OrderLine.class, ids.lineA2Id())
        );
        assertNotNull(
            verify.find(OrderLine.class, ids.lineB1Id())
        );

        assertNotNull(
            verify.find(Product.class, ids.sharedProductId())
        );
        assertNotNull(
            verify.find(Product.class, ids.independentProductId())
        );

        return null;
    });
}
```

Việc `flush()` trước `rollback()` làm test có ý nghĩa rõ: các câu SQL DELETE cần thiết có thể đã được gửi, nhưng không được commit.

### Không dùng entity cũ để assert sau rollback

Không nên kiểm tra `orderA.getLines()` của instance đã bị remove trong transaction lỗi rồi kết luận về database. Rollback không tự khôi phục mọi thay đổi collection và state của Java objects. Test phải đọc lại trong context mới.

## 20. Nếu foreign key vi phạm thì test phải làm gì?

Với mapping sai:

```java
@ManyToOne(cascade = CascadeType.REMOVE)
private Product product;
```

khi xóa một OrderLine tham chiếu Product dùng chung, provider có thể cố xóa Product đó. Nếu một OrderLine khác vẫn tham chiếu Product, DB có thể từ chối với foreign key violation.

Điều đó có thể cho thấy constraint hoạt động, nhưng **không có nghĩa mapping đúng**.

Đừng sửa bằng cách:

```sql
ALTER TABLE order_lines DROP CONSTRAINT fk_lines_product;
```

vì như vậy có thể biến lỗi rõ ràng thành silent data loss.

Cách sửa là:

- Bỏ cascade remove khỏi association tới Product dùng chung.
- Giữ foreign key để bảo vệ referential integrity.
- Thiết kế test để xác nhận xóa Order và Line thành công nhưng Product vẫn còn.
- Kiểm tra dữ liệu đã tồn tại và xử lý hậu quả nếu hệ thống trước đây đã xóa sai.

Nếu application dùng soft delete cho Product, test cần xác nhận trạng thái `deleted` của Product vẫn đúng, không chỉ rằng hàng chưa bị xóa vật lý.

## 21. Trường hợp ManyToMany: Playlist dùng chung Song

Mô hình khác rất dễ mắc lỗi:

```text
Playlist A ── song 1 ─┐
                       ├── Song S (dùng chung)
Playlist B ── song 1 ─┘
```

Mapping đúng theo hướng đơn giản:

```java
@Entity
@Table(name = "playlists")
public class Playlist {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "playlist_songs",
        joinColumns = @JoinColumn(name = "playlist_id"),
        inverseJoinColumns = @JoinColumn(name = "song_id")
    )
    private Set<Song> songs = new HashSet<>();

    protected Playlist() {}

    public void addSong(Song song) {
        songs.add(song);
    }

    public void removeSong(Song song) {
        songs.remove(song);
    }
}

@Entity
@Table(name = "songs")
public class Song {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    protected Song() {}
}
```

Ở đây **không khai báo CascadeType.REMOVE hoặc CascadeType.ALL từ Playlist tới Song**.

Khi xóa Playlist A, các hàng nối của A cần được loại bỏ theo mapping/SQL phù hợp. Song S vẫn tồn tại và Playlist B vẫn liên kết đến Song S.

### Anti-pattern ManyToMany

```java
// Nguy hiểm khi Song là entity dùng chung:
@ManyToMany(cascade = CascadeType.ALL)
private Set<Song> songs;
```

Nếu cascade REMOVE lan tới Song, xóa Playlist A có thể cố xóa Song S mà Playlist B đang dùng. Thêm cascade ALL để tránh gọi `persist(song)` không phải lý do hợp lệ, vì ALL có cả REMOVE.

### Test cần có những điều kiện gì?

1. Tạo Song S.
2. Tạo Playlist A và B, cả hai chứa S.
3. Commit fixture.
4. Xóa Playlist A hoặc gọi `playlistA.removeSong(S)`.
5. Commit.
6. Từ context mới xác nhận Playlist B còn.
7. Xác nhận Song S còn.
8. Xác nhận association B–S còn.
9. Xác nhận hàng nối A–S đã bị xóa.
10. Nếu xóa Playlist A, xác nhận không còn hàng playlist A.

Đặc biệt, nếu Song S không còn nằm trong playlist nào, vẫn cần giữ Song nếu nó là một mục thư viện độc lập. Test thêm trường hợp “xóa playlist cuối cùng” để phát hiện cascade sai nhưng không bị foreign key chặn.

### SQL minh họa

```sql
-- Bảng nối:
CREATE TABLE playlist_songs (
    playlist_id BIGINT NOT NULL,
    song_id BIGINT NOT NULL,
    PRIMARY KEY (playlist_id, song_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
    FOREIGN KEY (song_id) REFERENCES songs(id)
);

-- Gỡ một liên kết:
DELETE FROM playlist_songs
WHERE playlist_id = ? AND song_id = ?;
```

SQL xóa liên kết không phải:

```sql
DELETE FROM songs WHERE id = ?;
```

**Trong ManyToMany, xóa khỏi collection thường có nghĩa xóa link row, không phải xóa target entity.**

## 22. Nếu bảng nối là entity riêng: orphanRemoval phải nhắm đúng association entity

Giả sử playlist cần thứ tự phát, thời điểm thêm và người thêm. Khi đó `PlaylistSong` trở thành association entity:

```text
Playlist 1 ─── * PlaylistSong * ─── 1 Song
                    │
                    ├── position
                    └── addedAt
```

Mô hình:

- `Playlist` sở hữu vòng đời các `PlaylistSong`.
- `PlaylistSong` tham chiếu `Song` dùng chung.
- Xóa một playlist entry phải xóa **PlaylistSong**, không xóa **Song**.

Mapping:

```java
// Trong Playlist:
@OneToMany(
    mappedBy = "playlist",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<PlaylistSong> entries = new ArrayList<>();

// Trong PlaylistSong:
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "playlist_id", nullable = false)
private Playlist playlist;

@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "song_id", nullable = false)
private Song song;
```

Test khi remove một entry:

| Đối tượng | Kết quả cần assert |
| --- | --- |
| Playlist A | Còn |
| PlaylistSong A–S | Bị xóa |
| Song S | Còn |
| PlaylistSong B–S | Còn |
| Playlist B | Còn |

Nếu dùng `CascadeType.ALL` trên `PlaylistSong.song`, ta lại tạo rủi ro xóa Song dùng chung. Test phải bảo vệ **đúng đường ranh giữa association entity được sở hữu và target được chia sẻ**.

## 23. Kiểm thử “gỡ khỏi một collection” và “xóa cha” là hai use case khác nhau

Nếu chỉ kiểm thử:

```java
em.remove(order);
```

ta mới kiểm tra việc xóa root và cascade REMOVE.

Còn thao tác:

```java
order.removeLine(line);
```

khi Order vẫn tồn tại kiểm tra orphan removal. Không được suy từ việc test xóa Order pass rằng orphan removal khi gỡ một line đã đúng.

Vì vậy mỗi relationship sở hữu cần ít nhất hai loại test:

**Test xóa root:**

- Xóa Order.
- Các line thuộc Order bị xóa.
- Shared Product còn.

**Test gỡ child:**

- Giữ Order.
- Gỡ một Line.
- Chỉ Line đó bị xóa.
- Các Line còn lại và Product liên quan vẫn còn.

Nếu nghiệp vụ cho phép chuyển child giữa hai parent, phải kiểm thử riêng case chuyển chủ. Nhưng với `orphanRemoval = true`, việc tái gán một entity đã orphan trong cùng transaction không có ngữ nghĩa portable để “cứu” entity khỏi bị xóa. Nếu child cần chuyển chủ thường xuyên, mô hình orphan removal có thể không phù hợp; cần thiết kế thao tác chuyển owner và lifecycle rõ ràng.

## 24. Test phân biệt xóa relationship và xóa target

Bộ test nên có những tên thể hiện rõ kỳ vọng:

```java
void removingOrderRemovesItsLinesButKeepsProducts()

void removingOneLineRemovesOnlyThatLine()

void removingPlaylistFromSongDoesNotRemoveSong()

void deletingLastReferenceStillKeepsIndependentProduct()

void rollingBackRootDeletionRestoresDatabaseGraph()
```

Tên test như `testDelete()` hoặc `testCascade()` quá chung, khiến người đọc không biết đang bảo vệ quy tắc nào.

Một tên có cấu trúc:

```text
[When action]_[What is deleted]_[What must survive]
```

Ví dụ:

```java
void deletingOrderRemovesOwnedLinesAndPreservesCatalogProducts()
```

Tên đó ghi lại trực tiếp ranh giới ownership.

## 25. Đừng dùng lazy collection cũ để xác nhận DB state

JPA quản lý entity trong persistence context theo identity map. Nếu kiểm thử xóa và xác nhận trên những object đã load trong cùng context, có thể vô tình quan sát **state Java đang nhớ**, không phải dữ liệu đã commit.

Ví dụ chưa đủ tin cậy:

```java
PurchaseOrder orderA = em.find(PurchaseOrder.class, aId);
PurchaseOrder orderB = em.find(PurchaseOrder.class, bId);

em.remove(orderA);

assertTrue(orderB.getLines().size() > 0);
```

Assertion này không chứng minh commit thành công, Product không bị xóa hoặc join/foreign key trong DB còn nguyên. `orderB.getLines()` còn có thể là collection lazy được load trước đó.

Một vòng kiểm chứng tốt hơn:

```text
1. Persist fixture và commit.
2. Kết thúc context fixture.
3. Mở context mới, thực hiện thao tác xóa, flush và commit.
4. Kết thúc context thao tác.
5. Mở context mới, dùng find/query kiểm tra.
```

Có thể dùng `em.clear()` sau flush để buộc context tải lại state, nhưng với những test cần chứng minh **trạng thái đã commit**, cách mở một EntityManager mới sau commit rõ ràng hơn. `clear()` trước commit có thể làm mất pending changes nếu chưa flush.

### Query trực tiếp

Ngoài `find`, có thể dùng:

```java
Long count = em.createQuery(
    "SELECT COUNT(p) FROM Product p WHERE p.id = :id",
    Long.class
).setParameter("id", productId)
 .getSingleResult();

assertEquals(1L, count);
```

Nếu cần chứng minh một hàng DB tồn tại độc lập với mapping của Product, có thể dùng native query hoặc JDBC với schema test, nhưng phải cân nhắc flush/cache và transaction. Tránh kiểm tra state từ cùng context đang có pending deletes rồi coi đó là kết quả bền vững.

## 26. Spring `@DataJpaTest`: cần biết mặc định rollback

Trong Spring Boot, `@DataJpaTest` là công cụ tiện lợi để kiểm thử repository và mapping. Tuy nhiên, nhiều cấu hình test dùng transaction và **rollback sau mỗi test** để cô lập dữ liệu.

Điều này có lợi cho test tốc độ nhanh, nhưng với mục tiêu **khẳng định hiệu ứng sau commit**, phải cẩn thận. Một test có thể assert trên persistence context trong transaction rồi kết thúc bằng rollback; nó chưa chứng minh xóa đã commit.

Ví dụ kiểu test repository:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private TestEntityManager testEntityManager;

    // Các test kiểm tra mapping trong test transaction.
}
```

Đây chỉ là skeleton; Spring Data JPA là framework bên ngoài chuẩn Jakarta Persistence. Khi cần kiểm tra kết quả sau commit có thể:

- Sử dụng `TestTransaction` trong ngữ cảnh test được Spring hỗ trợ để kết thúc transaction và mở transaction mới có chủ đích.
- Tách setup/action/verification thành các transaction riêng qua `TransactionTemplate` hoặc service test thích hợp.
- Sử dụng integration test không được bao bọc bởi một transaction rollback mặc định, và tự quản lý cleanup dữ liệu.
- Khởi tạo database cô lập cho test và kiểm chứng từ một transaction/context khác.

Điểm cần đạt là **hành vi transaction thực tế được kiểm thử**, không chỉ thấy assertion xanh trong một graph chưa commit.

### Không lạm dụng `@Rollback(false)`

Tắt rollback mặc định có thể khiến dữ liệu test tồn tại và làm các test sau phụ thuộc thứ tự. Nếu muốn commit, cần một chiến lược cleanup/database isolation rõ ràng. Với Testcontainers, mỗi test có thể dùng transaction riêng và dữ liệu được cô lập theo cấu hình phù hợp; không mặc định container tự reset toàn bộ database giữa mỗi test.

## 27. H2 hay database thật cho kiểm thử cascade?

H2 hoặc database in-memory có thể rất hữu ích để phát hiện lỗi mapping cơ bản và chạy test nhanh. Tuy nhiên, với hành vi xóa dữ liệu, nên có thêm integration test trên **RDBMS giống production** hoặc môi trường tương đương vì:

- Foreign key enforcement và DDL có thể khác.
- Tên constraint và thứ tự thực thi DML có thể khác.
- Transaction isolation và locking khác.
- Cơ chế constraint deferrable khác.
- Trigger, cascade DB và soft delete khác.
- Dialect của Hibernate/JPA provider ảnh hưởng SQL.

Ví dụ dùng Testcontainers để chạy PostgreSQL trong test là một hướng triển khai; bài này không buộc dự án phải chọn một phiên bản thư viện cụ thể. Điều quan trọng là test đang kiểm chứng **dữ liệu đã được commit trên DB áp dụng constraint thực tế**.

### Test database phải bật foreign key

Một test chạy trên cấu hình DB không thực thi FK có thể bỏ qua lỗi cascade nguy hiểm. Cần xác minh constraint:

```sql
SELECT *
FROM information_schema.table_constraints
WHERE table_name = 'order_lines';
```

Cú pháp truy vấn metadata phụ thuộc RDBMS. Trong môi trường test, sử dụng migration tương đương production giúp tránh khác biệt giữa JPA auto-DDL và schema thật.

**Nhưng nhớ:** FK không thay thế assertion Product còn tồn tại. Một Product độc lập không còn được OrderLine nào tham chiếu vẫn có thể bị xóa nhầm mà DB không báo lỗi.

## 28. Cần kiểm thử cả database cascade và JPA cascade

Hai loại cascade dễ bị nhầm:

**JPA cascade:**

```java
@OneToMany(cascade = CascadeType.REMOVE)
private List<OrderLine> lines;
```

Đây là lan truyền **EntityManager.remove** qua object graph.

**Database cascade:**

```sql
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE
```

Đây là quy tắc của database khi một hàng parent bị xóa.

Hai cơ chế không đồng nghĩa:

- JPA cascade liên quan tới lifecycle của managed entities, callbacks và persistence context.
- DB cascade diễn ra ở SQL engine, không nhất thiết làm JPA cập nhật ngay các managed objects đã tải.
- DB cascade có thể xóa hàng mà JPA không hề load entity tương ứng.
- Một ứng dụng dùng native SQL DELETE có thể đi qua DB cascade mà bỏ qua JPA cascade.
- Một provider có extension hỗ trợ DB-level on-delete behavior, nhưng đó không phải `CascadeType.REMOVE` chuẩn.

Bộ test cần dùng **cùng đường thao tác mà ứng dụng thực sự dùng**. Nếu service xóa bằng JPA `remove()`, test điều đó. Nếu một job dùng native SQL DELETE và DB-level cascade, cần test riêng tác động của job. Không dùng test đường này để chứng minh đường kia.

## 29. Kiểm thử soft delete và audit retention

Trong một số hệ thống, Product và Order không bị xóa vật lý mà được đánh dấu `deleted` hoặc `archived`.

Ví dụ:

```java
@Column(name = "archived", nullable = false)
private boolean archived;
```

Khi đó test không chỉ kiểm tra:

```java
assertNotNull(em.find(Product.class, productId));
```

vì Product có thể còn hàng nhưng đã bị đánh dấu archived sai hoặc bị filter loại khỏi truy vấn nghiệp vụ.

Cần kiểm tra chính invariant:

- Product tồn tại vật lý nếu policy giữ lịch sử.
- Product không bị đánh dấu archived/deleted ngoài ý muốn.
- Giá, SKU và các thuộc tính quan trọng không bị sửa bởi cascade/merge sai.
- Order còn lại vẫn tham chiếu Product đúng.
- Audit history vẫn đầy đủ.

Nếu dùng provider extension cho soft delete, một lệnh `remove()` có thể trở thành SQL UPDATE cờ xóa thay vì DELETE. Do đó, assertion phải dựa trên quy tắc nghiệp vụ, không chỉ kỳ vọng số câu DELETE.

## 30. Những lỗi thiết kế test phổ biến

### Lỗi 1: Fixture không có entity dùng chung

Chỉ tạo một OrderLine cho một Product. Test có thể không phát hiện cascade sai khi target không được root khác tham chiếu.

**Cách khắc phục:** tạo ít nhất hai root độc lập cùng tham chiếu target, đồng thời một target độc lập không còn liên kết sau thao tác.

### Lỗi 2: Chỉ assert root bị xóa

`assertNull(find(Order A))` chưa đủ. Product, Order B, Line B1 và các liên kết của B cũng phải được kiểm tra.

### Lỗi 3: Không commit fixture

Nếu vừa tạo graph vừa xóa trong cùng transaction rồi rollback, test không chứng minh cơ chế xóa graph đã persist.

**Cách khắc phục:** commit fixture trước và lấy IDs để thao tác trong transaction mới.

### Lỗi 4: Xác minh trong cùng persistence context

First-level cache có thể trả object đã tải hoặc state đã sửa, không chứng minh DB đã commit đúng.

**Cách khắc phục:** dùng EntityManager mới ở bước kiểm tra.

### Lỗi 5: Chỉ tin vào FK violation

FK có thể chặn xóa shared Product P, nhưng không chặn việc xóa độc lập Product Q sau khi không còn tham chiếu. Cần assert Q còn.

### Lỗi 6: Dùng `CascadeType.ALL` cho tất cả association

ALL bao gồm REMOVE. Dùng nó trên cạnh tham chiếu tới shared target có thể gây xóa sai.

### Lỗi 7: Dùng orphanRemoval cho target dùng chung

Orphan removal thể hiện target thuộc vòng đời owner; không phù hợp với shared Product/Song/Department thông thường.

### Lỗi 8: Chỉ test xóa root, không test gỡ child

Orphan removal khi remove khỏi collection và cascade remove khi xóa root là hai workflow khác nhau. Cần test riêng.

### Lỗi 9: Không kiểm tra SQL/constraint thực tế

Một mapping có thể đi qua nhiều INSERT/DELETE/UPDATE tùy provider. Nếu test lỗi, xem SQL, không chỉ exception stack trace.

### Lỗi 10: Test dùng mock repository thay vì DB thật

Mock có thể trả `null` sau `delete()` theo cách test tự cấu hình nhưng không phát hiện cascade sang Product hoặc FK violation. Với chủ đề này, **integration test với JPA provider và database** là cần thiết.

### Lỗi 11: Dữ liệu test cố định gây trùng giữa các lần chạy

Dùng chung `"ORDER-A"`, `"P-SHARED"` trong database không được reset có thể gây unique constraint hoặc làm test phụ thuộc thứ tự.

**Cách khắc phục:** tạo mã riêng theo test, cô lập transaction/database và cleanup phù hợp.

### Lỗi 12: Test mặc định rollback nhưng kết luận về commit

Test rollback mặc định vẫn có thể assert đúng state JPA tạm thời, nhưng chưa xác nhận dữ liệu sau commit.

### Lỗi 13: Gộp test rollback và test delete success

Nếu cùng test vừa rollback vừa kiểm tra xóa thành công, kỳ vọng có thể mâu thuẫn. Tách test thành hai mục đích.

### Lỗi 14: Giả định thứ tự SQL DELETE cố định

Provider có thể batch, order statements hoặc dùng DB cascade khác nhau. Hãy kiểm tra invariant cuối cùng; chỉ assert SQL cụ thể khi đó là requirement riêng.

## 31. Kiểm thử concurrency khi hai root dùng chung target

Dữ liệu dùng chung còn tạo rủi ro khi các transaction chạy đồng thời:

```text
Transaction A                          Transaction B
delete Order A                         cập nhật Product P
       │                                    │
       │                                    │
       └───────── Product P dùng chung ─────┘
```

Nếu mapping sai cascade REMOVE tới Product P, transaction A có thể cố xóa Product trong khi B đang sử dụng hoặc cập nhật. Kết quả phụ thuộc lock, FK, transaction isolation và provider.

Bộ test tối thiểu phải bảo đảm xóa Order A **không có ý định xóa Product**. Sau đó có thể xây thêm test concurrency riêng cho yêu cầu mạnh hơn:

- Transaction A xóa Order A.
- Transaction B đọc/sửa Product P hoặc thêm OrderLine B2 tham chiếu P.
- Commit theo thứ tự đã xác định.
- Kiểm tra P còn và các OrderLine hợp lệ.
- Quan sát optimistic/pessimistic lock, deadlock hoặc constraint behavior.

### Không dùng `Thread.sleep()` để đoán thứ tự

Test cạnh tranh cần cơ chế đồng bộ có kiểm soát như latches/barriers và timeout. Dùng sleep ngẫu nhiên dễ khiến test lúc xanh lúc đỏ.

Với concurrency test, nên chạy trên DB và transaction manager phù hợp production. In-memory DB có thể xử lý lock khác đáng kể.

### Khi nào nên kỳ vọng conflict?

Nếu hai transaction cùng muốn cập nhật một entity versioned, `@Version` có thể giúp phát hiện optimistic locking conflict. Nhưng xóa Order A và sửa Product P không nên mặc nhiên xung đột nếu chỉ có association tham chiếu và không ai xóa Product.

Đừng tạo xung đột giả bằng cascade không đúng rồi cố xử lý bằng retry; phải sửa ownership trước.

## 32. Mutation test: cố tình cài bug rồi xem test có phát hiện không

Một kỹ thuật hữu ích để đánh giá **sức mạnh của test** là thay đổi mapping có chủ đích trên nhánh thử nghiệm (không áp dụng vào production) và xem test có thất bại.

Ví dụ mutation:

```java
// Mapping đúng:
@ManyToOne(fetch = FetchType.LAZY)
private Product product;

// Mapping bị sửa sai có chủ đích:
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.ALL
)
private Product product;
```

Sau mutation, test `removingOneOrderDoesNotDeleteSharedProducts` hoặc `deletingAllOrdersStillKeepsProductCatalog` cần thất bại, vì xóa Product là sai.

Nếu test vẫn xanh, hãy hỏi:

- Fixture có thật sự tạo shared Product không?
- Có assert Product tồn tại sau commit không?
- Có assert Product độc lập Q tồn tại không?
- Có đọc từ context mới không?
- Có đang chạy trên schema FK không đúng không?
- Có phải action xóa chưa được flush/commit không?
- Có phải provider không chạy đường cascade mà test tưởng đang kiểm thử không?

Đây là một dạng kiểm chứng chất lượng test trong thực hành phát triển. **Trong quy trình viết tài liệu này, không thực thi mutation test hay Content QA**; phần này mô tả cách người học có thể áp dụng trong dự án của mình.

## 33. Một ma trận kiểm thử tham khảo

| Ca kiểm thử | Action | Được phép xóa | Bắt buộc còn |
| --- | --- | --- | --- |
| Xóa một Order | `remove(Order A)` | A, A1, A2 | B, B1, P, Q |
| Gỡ một OrderLine | `A.removeLine(A1)` | A1 | A, A2, B, B1, P, Q |
| Xóa cả hai Order | Remove A rồi B | A, B, A1, A2, B1 | P, Q |
| Đổi Product của Line | `A1.replaceProduct(Q)` | Không xóa entity nào | A, B, mọi Line, P, Q |
| Xóa một Playlist | `remove(Playlist A)` | Playlist A, link rows của A | Playlist B, shared Song |
| Gỡ Song khỏi Playlist | `A.removeSong(S)` | Link A–S | Playlist A, B, Song S, link B–S |
| Gỡ association entity | `Playlist.removeEntry(entry)` | Entry bị gỡ | Song, các entry khác |
| Rollback xóa Order | `remove(A)` rồi rollback | Không commit xóa nào | Toàn bộ graph ban đầu |
| Xóa root cuối cùng | Remove mọi Order | Order/Line tương ứng | Product danh mục độc lập |
| Xóa trong concurrency | Remove A, B vẫn dùng P | A/Line của A | P, B và liên kết B–P |

Ma trận là một cách biến yêu cầu nghiệp vụ thành những test có tên, setup và assertion cụ thể. Không nhất thiết một test phải kiểm tra mọi tình huống; chia theo ý định giúp lỗi được định vị rõ hơn.

## 34. Nguyên tắc tránh xóa nhầm trước cả khi chạy test

Test là tuyến bảo vệ quan trọng, nhưng mapping và domain design đúng mới là nền tảng.

### 34.1. Cascade theo lifecycle ownership

- `PurchaseOrder → OrderLine`: thường có thể cascade PERSIST/REMOVE.
- `OrderLine → Product`: không cascade REMOVE tới Product.
- `Playlist ↔ Song`: không cascade REMOVE giữa các entity độc lập.
- `Employee → Department`: xóa Employee không xóa Department.
- Association entity `Enrollment`: xóa Enrollment không xóa Student hoặc Course.

### 34.2. Orphan removal chỉ cho entity phụ thuộc

`orphanRemoval = true` phù hợp khi loại khỏi parent là kết thúc vòng đời child. Nó không phải cơ chế “tự dọn mọi object không còn xuất hiện trong collection”.

### 34.3. FK và UNIQUE được khai báo đúng

Constraints bảo vệ referential integrity và tính duy nhất. Không xóa FK để tránh lỗi cascade; lỗi đó có thể là dấu hiệu mapping sai.

### 34.4. Không suy ownership từ owning side của JPA

`@ManyToOne` thường sở hữu foreign key; điều đó không có nghĩa child có quyền xóa entity target. Owning side của association và ownership vòng đời là hai khái niệm khác nhau.

### 34.5. Domain methods giữ hai phía nhất quán

Khi quan hệ hai hướng, helper thêm/gỡ child phải cập nhật cả collection và reference thích hợp. Nếu không, persistence context có thể chứa graph mâu thuẫn với ý định nghiệp vụ.

### 34.6. Mỗi thao tác xóa là một transaction rõ ràng

Nhờ vậy test có thể xác định kết quả commit/rollback; ứng dụng có thể chuyển constraint violation thành lỗi nghiệp vụ phù hợp.

### 34.7. Test “còn” quan trọng ngang test “mất”

Trong những graph dùng chung, bảo vệ shared target thường là mục tiêu cao hơn việc xóa root cho thành công. Mỗi test xóa nên hỏi thêm: **“Những entity nào tuyệt đối không được thay đổi?”**

## 35. Bài tập thực hành

### Bài tập 1: Nhận diện cạnh dùng chung

Một ứng dụng có:

```text
Invoice 1 ──► InvoiceLine A ──► TaxRate R
Invoice 2 ──► InvoiceLine B ──► TaxRate R
```

**Câu hỏi:** Khi xóa Invoice 1, nên cascade xóa gì?

**Đáp án:** Có thể xóa InvoiceLine A nếu nó thuộc vòng đời Invoice 1. Không nên xóa TaxRate R vì Invoice 2 còn tham chiếu và TaxRate là dữ liệu dùng chung.

### Bài tập 2: Test cần tối thiểu những assertion nào?

Hai Order dùng chung Product P. Xóa Order A.

**Gợi ý đáp án:** Assert A và các Line của A bị xóa; assert B, các Line của B, Product P còn; assert liên kết B–P còn. Thêm Product Q không còn tham chiếu để xác nhận Product độc lập cũng được giữ.

### Bài tập 3: Gỡ khỏi collection có đồng nghĩa xóa entity không?

```java
playlist.getSongs().remove(song);
```

**Câu hỏi:** Có nên xóa `Song` khỏi DB?

**Đáp án:** Không, nếu Song là thư viện dùng chung. Chỉ xóa row liên kết Playlist–Song. Không cấu hình cascade REMOVE tới Song.

### Bài tập 4: OrphanRemoval đặt ở đâu?

Một `PurchaseOrder` sở hữu những `OrderLine`. Mỗi Line tham chiếu `Product` dùng chung.

**Câu hỏi:** Đặt `orphanRemoval = true` ở Order.lines hay ở Line.product?

**Đáp án:** Nếu nghiệp vụ yêu cầu dòng hàng bị gỡ sẽ bị xóa, đặt trên `Order.lines` (OneToMany). Không có orphanRemoval chuẩn trên ManyToOne và Product không thuộc vòng đời Line.

### Bài tập 5: Vì sao FK chưa đủ?

Product Q chỉ được OrderLine A2 tham chiếu; xóa Order A cùng A2 rồi mapping sai cũng xóa Product Q.

**Câu hỏi:** Tại sao DB có thể không báo lỗi?

**Đáp án:** Sau khi A2 bị xóa, không còn FK trỏ Q, nên xóa Q có thể hợp lệ về referential integrity nhưng trái quy tắc nghiệp vụ. Cần assertion Product Q vẫn tồn tại.

### Bài tập 6: Test chạy trong một transaction rollback mặc định

Một test dùng `@DataJpaTest` tạo graph, xóa Order rồi kiểm tra trong cùng EntityManager, sau đó framework rollback.

**Câu hỏi:** Test đã chứng minh xóa sau commit đúng chưa?

**Đáp án:** Chưa. Cần kiểm chứng trong một transaction/context mới sau commit khi mục tiêu là kết quả đã commit, đồng thời tổ chức cleanup phù hợp.

### Bài tập 7: Entity graph sau rollback

Test gọi `remove(Order A)` rồi rollback nhưng tiếp tục dùng `orderA.getLines()` để suy ra DB còn bao nhiêu Line.

**Câu hỏi:** Có đáng tin không?

**Đáp án:** Không. Java object graph không tự được phục hồi sau rollback. Mở context mới và query DB để kiểm tra.

### Bài tập 8: Mapping sai trên ManyToMany

```java
@ManyToMany(cascade = CascadeType.ALL)
private Set<Song> songs;
```

Playlist A và B cùng chứa Song S.

**Câu hỏi:** Lỗi tiềm ẩn là gì?

**Đáp án:** `ALL` bao gồm `REMOVE`; xóa Playlist A có thể cố xóa Song S, gây FK violation hoặc mất dữ liệu nếu constraint không ngăn. Không cascade remove tới shared Song.

### Bài tập 9: Association entity có trạng thái

`Enrollment` nối Student và Course, có field `grade`, `status`.

**Câu hỏi:** Khi gỡ Enrollment khỏi Student, entity nào được xóa?

**Đáp án:** Nếu Enrollment thuộc vòng đời quan hệ đăng ký và mapping cho phép, có thể xóa Enrollment. Student và Course độc lập phải còn.

### Bài tập 10: Test mutation

Thêm tạm `cascade = REMOVE` vào association `OrderLine.product`.

**Câu hỏi:** Test nào phải thất bại?

**Đáp án:** Test xóa Order nhưng vẫn giữ shared Product, và đặc biệt test xóa Order cuối cùng mà vẫn giữ Product độc lập. Nếu không thất bại, fixture/assertion chưa đủ mạnh hoặc không chạy đúng đường xóa.

### Bài tập 11: Native SQL và DB cascade

Một batch job dùng native SQL xóa Order, còn API dùng `EntityManager.remove`.

**Câu hỏi:** Một bộ test JPA remove đã đủ chưa?

**Đáp án:** Chưa. Hai đường thực thi có thể kích hoạt cascade khác nhau. Cần integration test riêng cho native SQL/DB cascade và kiểm tra shared targets.

### Bài tập 12: Soft delete

Product không bị xóa vật lý nhưng có cờ `archived`.

**Câu hỏi:** Assert `find(Product) != null` đã đủ bảo vệ Product chưa?

**Đáp án:** Chưa. Product có thể vẫn có hàng nhưng bị archived ngoài ý muốn. Cần assert trạng thái nghiệp vụ, association còn lại và các field quan trọng.

## 36. Checklist cuối cùng khi thiết kế test đồ thị dùng chung

Trước khi đưa một thay đổi cascade/orphanRemoval vào production, hãy tự hỏi:

1. **Entity nào là root nghiệp vụ?** `PurchaseOrder`, `Playlist` hay một aggregate khác?
2. **Entity nào thực sự phụ thuộc vòng đời root?** `OrderLine`, `PlaylistSong` hoặc association entity?
3. **Entity nào dùng chung?** `Product`, `Song`, `Department`, `TaxRate`?
4. **Có ít nhất hai root cùng tham chiếu một target trong fixture chưa?**
5. **Có target không còn reference sau xóa nhưng vẫn phải giữ không?**
6. **Có test xóa root và test gỡ child riêng không?**
7. **Mapping có cascade REMOVE/ALL trên cạnh tới shared target không?**
8. **Có orphanRemoval trên quan hệ target thực sự thuộc độc quyền owner không?**
9. **Helper có đồng bộ owning/inverse side không?**
10. **Database có FK/UNIQUE/NOT NULL tương ứng không?**
11. **Test có commit transaction xóa không?**
12. **Assertion có chạy trong EntityManager/context mới không?**
13. **Có kiểm tra đủ cả entity bị xóa, entity phải còn và association còn không?**
14. **Có test xóa target cuối cùng không còn được tham chiếu mà vẫn phải giữ không?**
15. **Có test rollback độc lập với test delete success không?**
16. **Có test soft delete hoặc provider-specific delete behavior nếu áp dụng không?**
17. **Có test đường native SQL/DB cascade nếu ứng dụng thực sự sử dụng không?**
18. **Có kiểm chứng trên DB tương đương production không?**
19. **Có phân loại lỗi FK thành mapping sai thay vì vội tắt constraint không?**
20. **Nếu thay đổi mapping cascade, test có phát hiện mutation xóa sai không?**

Bộ câu hỏi này biến một thay đổi annotation tưởng như nhỏ thành một thay đổi có thể đánh giá được bằng **invariant trên database sau transaction**.

## Kết luận

Kiểm thử `cascade` và `orphanRemoval` không chỉ nhằm chứng minh entity cần xóa đã biến mất. Trong đồ thị JPA có entity dùng chung, yêu cầu quan trọng hơn thường là **chứng minh những entity không được xóa vẫn tồn tại, đồng thời những liên kết còn lại vẫn đúng**.

Một fixture tốt nên có ít nhất **hai root dùng chung một target** và một target độc lập không còn được tham chiếu sau khi xóa root. Bộ test cần phân biệt xóa root với orphan removal khi gỡ child, kiểm tra kết quả sau **commit** từ persistence context mới, và khẳng định cả hai mặt **“phải mất”** và **“phải còn”**.

Trong mô hình đơn hàng, `PurchaseOrder` có thể sở hữu vòng đời `OrderLine`, nhưng `OrderLine` **không sở hữu vòng đời `Product`**. Trong mô hình playlist, xóa liên kết tới Song chỉ nên xóa hàng nối hoặc association entity, không xóa Song dùng chung. Foreign key bảo vệ dữ liệu khỏi một số cách xóa sai, nhưng không thay thế được assertion về ownership nghiệp vụ.

Khi chuẩn bị một test xóa dữ liệu, hãy hỏi bốn câu: **“Tôi đang xóa entity hay chỉ xóa liên kết? Entity đích có được root khác sử dụng không? Điều gì phải còn ngay cả khi không còn tham chiếu nào? Tôi đã kiểm tra trạng thái đã commit trong context mới chưa?”**. Trả lời được những câu hỏi đó sẽ giúp phát hiện sớm cascade sai, orphan removal sai và hạn chế nguy cơ mất dữ liệu ngoài ý muốn.
