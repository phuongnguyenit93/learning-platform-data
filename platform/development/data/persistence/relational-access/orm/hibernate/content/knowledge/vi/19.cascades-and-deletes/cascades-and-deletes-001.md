# Cascade truyền thao tác vòng đời khác với tải dữ liệu liên quan

Trong JPA/Hibernate, một entity có thể tham chiếu đến nhiều entity khác. Ví dụ, một đơn hàng chứa các dòng hàng, mỗi dòng hàng tham chiếu đến một sản phẩm. Khi gọi `persist(order)`, ta có muốn lưu luôn các dòng hàng mới không? Khi gọi `remove(order)`, ta có muốn xóa các dòng hàng thuộc đơn không? Khi tải `order`, ta có muốn Hibernate lập tức truy vấn toàn bộ dòng hàng và sản phẩm không?

Đây là **hai nhóm quyết định khác nhau**:

- **Cascade** xác định một thao tác vòng đời được gọi trên entity nguồn có được truyền tiếp sang các entity liên quan hay không.
- **Fetch strategy** xác định dữ liệu liên quan được tải khi nào và theo kế hoạch nào.

Ví dụ, một quan hệ có thể dùng `cascade = CascadeType.PERSIST` nhưng `fetch = FetchType.LAZY`. Điều đó có nghĩa thao tác persist có thể lan sang entity liên quan khi JPA áp dụng quy tắc cascade, còn việc đọc collection vẫn được trì hoãn cho đến khi cần. Ngược lại, một association có thể được fetch EAGER mà không có cascade persist hay remove nào.

Bài học thuộc chương **Cascade và xóa** của module *Data Persistence Relational Access ORM Hibernate*, sử dụng Jakarta Persistence (`jakarta.persistence.*`), Hibernate ORM và SQL minh họa. Trọng tâm là hiểu đúng **cascade truyền thao tác vòng đời khác với tải dữ liệu liên quan**, tránh nhầm cascade với eager loading, tránh xóa nhầm entity dùng chung và phân biệt cascade ORM với `ON DELETE CASCADE` ở database.

## 1. Mô hình ví dụ: đơn hàng và các dòng hàng

Một đơn hàng có nhiều dòng hàng. Mỗi dòng hàng thuộc về đúng một đơn hàng và tham chiếu tới một sản phẩm có thể được dùng ở nhiều đơn khác nhau.

~~~text
PurchaseOrder
  id
  orderCode
     |
     | 1 - N
     v
OrderLine
  id
  quantity
  unitPrice
     |
     | N - 1
     v
Product
  id
  sku
  name
~~~

Các quy tắc vòng đời:

- Dòng hàng là một phần cấu thành đơn hàng. Khi tạo đơn hàng mới, các dòng hàng mới thường được lưu cùng đơn.
- Khi xóa đơn hàng, các dòng hàng của chính đơn đó thường cũng phải được xóa.
- Sản phẩm là dữ liệu dùng chung. Xóa một đơn hàng không được xóa sản phẩm vì những đơn khác có thể vẫn tham chiếu tới nó.
- Khi chỉ xem danh sách đơn hàng, có thể chưa cần tải toàn bộ dòng hàng và thông tin sản phẩm.

Các quy tắc trên gợi ý cascade và fetch khác nhau trên từng association. Không nên áp dụng một cấu hình chung cho mọi quan hệ chỉ vì chúng đều là object reference.

## 2. Hai nhóm annotation giải quyết hai câu hỏi khác nhau

| Nhóm | API/annotation | Câu hỏi được trả lời |
| --- | --- | --- |
| Cascade | `CascadeType.PERSIST` | Persist entity nguồn có truyền thao tác persist tới entity liên quan không? |
| Cascade | `CascadeType.MERGE` | Merge entity nguồn có truyền thao tác merge tới entity liên quan không? |
| Cascade | `CascadeType.REMOVE` | Remove entity nguồn có truyền thao tác remove tới entity liên quan không? |
| Cascade | `CascadeType.REFRESH` | Refresh entity nguồn có truyền thao tác refresh tới entity liên quan không? |
| Cascade | `CascadeType.DETACH` | Detach entity nguồn có truyền thao tác detach tới entity liên quan không? |
| Cascade | `CascadeType.ALL` | Có áp dụng tất cả các cascade operation được định nghĩa không? |
| Fetch | `FetchType.LAZY` | Có thể trì hoãn tải association cho đến khi cần không? |
| Fetch | `FetchType.EAGER` | Association phải được tải theo yêu cầu fetch của mapping không? |
| Fetch plan | `JOIN FETCH`, Entity Graph | Truy vấn cụ thể cần tải association nào? |

**Không có `CascadeType.FIND` hay `CascadeType.LOAD` trong enum CascadeType chuẩn của JPA.** Việc gọi `find` để tải entity không tự động truyền một thao tác “find cascade” qua mọi association. Việc association được nạp theo LAZY/EAGER và fetch plan mới quyết định dữ liệu liên quan cần được tải.

Cũng không có nghĩa cascade luôn không tạo query. Một thao tác cascade có thể buộc provider duyệt hoặc khởi tạo association để thực hiện thao tác vòng đời. Điểm khác biệt là **cascade không phải chỉ thị fetch dữ liệu khi đọc entity**.

## 3. Các giá trị `CascadeType` trong Jakarta Persistence

Enum `jakarta.persistence.CascadeType` có những giá trị sau:

| Giá trị | Thao tác được truyền | Ý nghĩa điển hình |
| --- | --- | --- |
| `PERSIST` | `EntityManager.persist` | Lưu entity mới liên quan cùng entity nguồn |
| `MERGE` | `EntityManager.merge` | Hợp nhất trạng thái entity liên quan khi merge nguồn |
| `REMOVE` | `EntityManager.remove` | Xóa entity liên quan khi remove nguồn |
| `REFRESH` | `EntityManager.refresh` | Làm mới trạng thái entity liên quan từ database |
| `DETACH` | `EntityManager.detach` | Tách entity liên quan khỏi persistence context |
| `ALL` | Tất cả năm thao tác trên | Tương đương khai báo đầy đủ các cascade type đó |

Ví dụ khai báo chọn lọc:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    }
)
private List<OrderLine> lines = new ArrayList<>();
~~~

`cascade` nhận một tập hợp thao tác vòng đời. Nó **không nói** rằng collection này phải được SELECT ngay khi nạp `PurchaseOrder`.

### `CascadeType.ALL` bao gồm những gì?

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Có thể hiểu:

~~~java
cascade = {
    CascadeType.PERSIST,
    CascadeType.MERGE,
    CascadeType.REMOVE,
    CascadeType.REFRESH,
    CascadeType.DETACH
}
~~~

`ALL` là tiện ích gom tất cả các cascade operation, không phải “bật tất cả tính năng ORM”. Nó không tự bao gồm eager loading, fetch join, orphan removal, locking hoặc database foreign key cascade.

Chỉ dùng `ALL` khi vòng đời của entity liên quan thực sự phụ thuộc vào entity nguồn ở tất cả những thao tác đó. Nếu chỉ cần persist và merge, khai báo đúng hai giá trị sẽ diễn đạt ý định chính xác hơn.

## 4. `FetchType.LAZY` và `FetchType.EAGER` quyết định thời điểm tải

Fetch strategy nói về **lấy trạng thái association**, không phải lan truyền persist/remove.

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "product_id")
private Product product;
~~~

Khi Hibernate tải `OrderLine`, nó có thể biết `product_id` và tạo một reference/proxy tới `Product` mà chưa đọc toàn bộ thông tin sản phẩm. Khi ứng dụng truy cập một thuộc tính cần trạng thái, provider có thể khởi tạo reference.

Với collection:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

Hibernate có thể tải đơn hàng trước và trì hoãn query lấy các dòng hàng cho đến khi collection được truy cập.

Ngược lại:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.EAGER)
private List<OrderLine> lines = new ArrayList<>();
~~~

`EAGER` yêu cầu provider tải association theo fetch requirement. Provider có thể dùng join hoặc query bổ sung; EAGER **không đảm bảo luôn chỉ một SQL**.

### Mặc định fetch của các quan hệ JPA

| Association | Fetch mặc định theo JPA |
| --- | --- |
| `@ManyToOne` | `EAGER` |
| `@OneToOne` | `EAGER` |
| `@OneToMany` | `LAZY` |
| `@ManyToMany` | `LAZY` |

Với `@ManyToOne` và `@OneToOne`, LAZY là một gợi ý fetch theo chuẩn JPA; khả năng trì hoãn chính xác có thể phụ thuộc provider, mapping và bytecode enhancement. Với collection, LAZY là lựa chọn thông dụng để tránh tải toàn bộ danh sách không cần thiết.

**Đừng dùng CascadeType để sửa một vấn đề fetch.** Nếu trang danh sách đơn hàng đang tải quá nhiều sản phẩm, hãy xem fetch type, entity graph hoặc query fetch join. Đổi `cascade = PERSIST` thành `cascade = ALL` không phải cách tối ưu truy vấn.

## 5. Một association có thể LAZY nhưng vẫn có cascade

Đây là cấu hình hoàn toàn hợp lệ:

~~~java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.LAZY,
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    }
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Ý nghĩa:

- Khi **đọc** một đơn hàng, collection `lines` có thể chưa được tải.
- Khi gọi **persist** trên đơn hàng, thao tác persist có thể lan sang các dòng hàng liên quan theo quy tắc cascade.
- Khi gọi **merge** trên đơn hàng detached, thao tác merge có thể lan sang các dòng hàng liên quan.
- Không có yêu cầu rằng collection phải EAGER chỉ vì có cascade.

Tuy vậy, một thao tác cascade cụ thể có thể cần duyệt trạng thái association. Nếu collection là lazy và chưa được khởi tạo, provider có thể phải tải nó để xử lý một số operation, đặc biệt khi cần biết những entity nào phải remove, refresh, merge hoặc detach. Câu hỏi đúng không phải “cascade có phát SQL không?” mà là **operation đang được cascade cần những entity/state nào để hoàn thành?**

## 6. Entity đầy đủ cho ví dụ đơn hàng

**`Product.java`:**

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = Objects.requireNonNull(sku);
        this.name = Objects.requireNonNull(name);
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
~~~

**`PurchaseOrder.java`:**

~~~java
package com.example.shop.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
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

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY,
        cascade = {
            CascadeType.PERSIST,
            CascadeType.MERGE,
            CascadeType.REMOVE
        },
        orphanRemoval = true
    )
    @OrderBy("id ASC")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode) {
        this.orderCode = Objects.requireNonNull(orderCode);
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line);
        lines.add(line);
        line.attachTo(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.detachFromOrder();
        }
    }
}
~~~

**`OrderLine.java`:**

~~~java
package com.example.shop.domain;

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
    private Product product;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false, precision = 15, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public OrderLine(Product product, int quantity, BigDecimal unitPrice) {
        this.product = Objects.requireNonNull(product);
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        this.quantity = quantity;
        this.unitPrice = Objects.requireNonNull(unitPrice);
    }

    void attachTo(PurchaseOrder order) {
        this.order = Objects.requireNonNull(order);
    }

    void detachFromOrder() {
        this.order = null;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public Product getProduct() {
        return product;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

Đây là ví dụ mô hình domain: `PurchaseOrder.lines` là inverse side vì có `mappedBy = "order"`, còn `OrderLine.order` là owning side chứa FK `order_id`. Cascade được cấu hình trên collection của đơn hàng để thao tác vòng đời có thể lan từ aggregate root tới các dòng hàng. **Owning side vẫn quyết định giá trị FK được ghi.**

`Product` không có cascade từ `OrderLine.product` vì sản phẩm là entity dùng chung, có vòng đời độc lập. Xóa một dòng hàng không được xóa sản phẩm.

Ví dụ dùng `orphanRemoval = true` và cột FK không nullable. Provider phải xử lý orphan theo ngữ nghĩa delete; khi triển khai với mapping phức tạp, hãy xác nhận SQL và thứ tự thao tác phù hợp schema. Không tự đặt `order = null` trên một child rồi lưu như thể cột FK chắc chắn cho phép NULL.

## 7. Persist cascade: lưu aggregate cùng entity mới

Không có cascade persist:

~~~java
PurchaseOrder order = new PurchaseOrder("ORD-100");

OrderLine line = new OrderLine(
    product,
    2,
    new BigDecimal("150000.00")
);

order.addLine(line);

em.persist(order);
~~~

Nếu `PurchaseOrder.lines` không có `CascadeType.PERSIST`, việc persist root không tự động yêu cầu persist dòng hàng mới. Khi flush, provider có thể báo lỗi vì một entity mới đang được tham chiếu bởi managed entity mà chưa được persist, hoặc gặp tình huống transient association tùy mapping.

Với cascade persist:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
~~~

khi gọi:

~~~java
em.persist(order);
~~~

thao tác persist được truyền sang các `OrderLine` liên quan theo cascade mapping. Hibernate có thể lên lịch insert cho đơn và các dòng hàng khi flush, sắp xếp SQL theo dependency/identifier generation.

SQL minh họa:

~~~sql
INSERT INTO purchase_orders(order_code)
VALUES ('ORD-100');

INSERT INTO order_lines(order_id, product_id, quantity, unit_price)
VALUES (101, 7, 2, 150000.00);
~~~

Thứ tự thực tế phụ thuộc ID generation và mapping. Nếu dùng `IDENTITY`, Hibernate có thể cần insert parent sớm để lấy ID; với sequence, việc cấp ID có thể diễn ra trước các insert. Không nên dựa vào thứ tự SQL minh họa như một cam kết chung.

### Persist cascade không có nghĩa load cascade

Giả sử đơn hàng đã được lưu. Khi tải:

~~~java
PurchaseOrder loaded =
    em.find(PurchaseOrder.class, 101L);
~~~

`cascade = PERSIST` không khiến `lines` tự động tải. Collection vẫn theo `fetch = LAZY`. Cascade persist chỉ mô tả thao tác **persist**, không phải thao tác **find**.

## 8. Persist cascade trên association LAZY có phải tải collection?

Cần phân biệt hai trường hợp.

**Trường hợp A — object graph mới đã có trong bộ nhớ:**

~~~java
PurchaseOrder order = new PurchaseOrder("ORD-101");
order.addLine(new OrderLine(product, 1, new BigDecimal("90000.00")));
order.addLine(new OrderLine(otherProduct, 3, new BigDecimal("25000.00")));

em.persist(order);
~~~

Hibernate nhìn thấy những child object đã được gắn vào collection trong memory và có thể cascade persist chúng. Không cần chạy một SELECT để tải những child mới chưa tồn tại trong database.

**Trường hợp B — collection lazy của một entity cũ chưa được khởi tạo:**

~~~java
PurchaseOrder existing = em.find(PurchaseOrder.class, 101L);
// existing.lines có thể chưa initialized.
~~~

Chỉ vì association có cascade persist không có nghĩa Hibernate phải tải mọi dòng hàng ngay khi `find` root. Khi một operation cụ thể yêu cầu duyệt collection hoặc cần xác định entity liên quan, provider có thể phải khởi tạo nó. Việc đó phụ thuộc operation, trạng thái collection và provider.

**Fetch strategy vẫn là chỉ dẫn tải; cascade vẫn là quy tắc lan truyền operation.** Hai cơ chế phối hợp trong lúc thực thi nhưng không thay thế nhau.

## 9. Merge cascade: hợp nhất một object graph detached

`merge` thường được dùng khi ứng dụng nhận một entity detached hoặc một object graph từ một context trước và cần hợp nhất trạng thái vào context hiện tại.

~~~java
PurchaseOrder detached = obtainDetachedOrder();

PurchaseOrder managed = em.merge(detached);
~~~

Nếu association `lines` có `CascadeType.MERGE`, thao tác merge trên root được truyền sang những child liên quan theo mapping. JPA trả về **managed instance** tương ứng:

~~~java
PurchaseOrder managed = em.merge(detached);

System.out.println(managed == detached); // Không nên giả định true.
~~~

Object truyền vào vẫn có thể detached; phải sử dụng giá trị trả về từ `merge` để tiếp tục thao tác trong context hiện tại.

### Merge cascade không phải cơ chế lưu tự động mỗi lần child thay đổi

Nếu `OrderLine` đã managed trong cùng persistence context và ứng dụng thay đổi `quantity`, dirty checking có thể đồng bộ child theo vòng đời managed bình thường. Không cần gọi `merge` chỉ vì muốn lưu một field.

`CascadeType.MERGE` có ý nghĩa khi thao tác **merge nguồn** cần lan sang trạng thái của entity liên quan. Nó không phải “bật theo dõi thay đổi” cho collection; managed entities đã được dirty checking theo mapping.

### Cẩn trọng với detached graph thiếu dữ liệu

Nếu API nhận một object `PurchaseOrder` chỉ chứa ID và một phần field, rồi gọi `merge` với cascade MERGE, trạng thái các association/field không có trong payload có thể không phản ánh trạng thái thật trong database. Có thể gây ghi đè hoặc thay đổi graph ngoài ý muốn.

Một cách thường rõ hơn là:

1. Nạp managed aggregate trong transaction.
2. Kiểm tra quyền và quy tắc nghiệp vụ.
3. Áp dụng những thay đổi được phép lên managed entity.
4. Để dirty checking đồng bộ.

Không merge một object graph thiếu dữ liệu như thể nó là bản sao đầy đủ của aggregate.

## 10. Remove cascade: xóa entity con theo entity cha

Nếu dòng hàng chỉ có ý nghĩa trong một đơn hàng, khi xóa đơn ta có thể muốn xóa các dòng hàng cùng lúc:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Thao tác:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.remove(order);
~~~

có thể truyền thao tác remove tới các entity `OrderLine` liên quan. Hibernate sẽ thực hiện các thao tác delete phù hợp để bảo đảm ràng buộc quan hệ.

SQL minh họa:

~~~sql
DELETE FROM order_lines WHERE order_id = 101;
DELETE FROM purchase_orders WHERE id = 101;
~~~

SQL thực tế có thể là nhiều câu lệnh delete cho từng entity, batch delete hoặc cách khác tùy Hibernate và database. Nếu mapping cần entity callbacks, version checks hoặc cascade qua nhiều tầng, provider có thể phải nạp trạng thái liên quan trước khi xóa.

### Cascade REMOVE có phải xóa trực tiếp hàng FK ở database?

Không nhất thiết. `CascadeType.REMOVE` là **ngữ nghĩa vòng đời entity của ORM**. Hibernate quản lý việc remove các entity liên quan và có thể phát SQL tương ứng. Nó khác với ràng buộc database `ON DELETE CASCADE`, sẽ giải thích ở phần sau.

### Phạm vi portable của REMOVE

Theo hướng dẫn của Jakarta Persistence, ứng dụng portable nên áp dụng `CascadeType.REMOVE` cho quan hệ `@OneToOne` và `@OneToMany`. Áp dụng REMOVE cascade lên `@ManyToOne` hoặc `@ManyToMany` không portable và thường nguy hiểm về mô hình vì entity đích có thể được chia sẻ.

Ví dụ, xóa một `OrderLine` không nên xóa `Product`. Product có thể đang được hàng nghìn đơn hàng khác sử dụng.

## 11. Vì sao không cascade REMOVE tới entity dùng chung?

Giả sử nhiều đơn hàng tham chiếu cùng sản phẩm:

~~~text
Order 101 ── OrderLine A ──┐
                           ├── Product 7
Order 102 ── OrderLine B ──┘
~~~

Nếu cấu hình:

~~~java
@ManyToOne(cascade = CascadeType.REMOVE)
private Product product;
~~~

thì khi xóa một `OrderLine`, thao tác remove có thể lan sang `Product`. Điều này có thể xóa sản phẩm mà `Order 102` vẫn đang tham chiếu, gây vi phạm FK hoặc mất dữ liệu dùng chung.

Quy tắc thiết kế:

- **Composition/ownership vòng đời:** child tồn tại vì parent; cascade persist/remove thường phù hợp.
- **Shared reference:** entity có vòng đời độc lập, nhiều parent có thể tham chiếu; thường không cascade remove.
- **Many-to-many:** xóa một phía thường chỉ cần xóa hàng liên kết, không xóa entity ở phía còn lại.

Không đánh giá cascade chỉ bằng hướng của Java reference. Hãy hỏi **entity đích có thể tồn tại độc lập hoặc được dùng bởi đối tượng khác không?**

## 12. `CascadeType.ALL` không đồng nghĩa “cascade mọi thứ”

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Cấu hình này có thể hợp lý nếu dòng hàng thực sự thuộc vòng đời của đơn. Nhưng `ALL` bao gồm cả:

- `PERSIST`: lưu child cùng parent.
- `MERGE`: merge child cùng parent.
- `REMOVE`: xóa child cùng parent.
- `REFRESH`: refresh child cùng parent.
- `DETACH`: detach child cùng parent.

Không có `FIND` hay fetch EAGER trong danh sách đó.

### REFRESH cascade có thể làm mất thay đổi chưa flush

~~~java
em.refresh(order);
~~~

Nếu cascade REFRESH được cấu hình, thao tác refresh có thể truyền sang entity liên quan. Trạng thái Java chưa được lưu của những entity được refresh có thể bị thay bằng dữ liệu database. Đây không phải cách “reload nhẹ” vô hại nếu ứng dụng đang có thay đổi pending.

### DETACH cascade ảnh hưởng persistence context

~~~java
em.detach(order);
~~~

Nếu cascade DETACH được cấu hình, các entity liên quan cũng có thể bị tách khỏi context. Khi không có cascade, entity con có thể vẫn managed tùy trạng thái và mapping; không nên suy luận từ việc detach parent rằng toàn bộ object graph tự detached.

Vì vậy chỉ dùng `ALL` khi tất cả năm hành vi đều đúng với lifecycle aggregate. Nếu chỉ cần persist/merge/remove, liệt kê đúng các operation sẽ giúp code dễ hiểu và ít tác dụng phụ hơn.

## 13. `orphanRemoval` khác cascade REMOVE

Hai cơ chế có liên quan đến xóa child nhưng kích hoạt trong tình huống khác nhau.

**Cascade REMOVE:**

~~~java
em.remove(order);
~~~

Khi remove parent, thao tác remove được truyền tới child liên quan nếu có cascade REMOVE.

**Orphan removal:**

~~~java
order.removeLine(line);
~~~

Khi một entity child đang được quản lý bị loại khỏi quan hệ one-to-one/one-to-many được đánh dấu `orphanRemoval = true`, provider áp dụng remove cho child orphan khi đồng bộ phù hợp, thường tại flush.

| Tiêu chí | `CascadeType.REMOVE` | `orphanRemoval = true` |
| --- | --- | --- |
| Kích hoạt chính | Gọi remove trên entity nguồn | Child bị loại khỏi association |
| Ví dụ | Xóa đơn hàng thì xóa dòng hàng | Bỏ một dòng khỏi đơn thì xóa dòng đó |
| Phạm vi association portable | Nên dùng với OneToOne/OneToMany | OneToOne/OneToMany |
| Thao tác xóa child | Có | Có |
| Có đồng nghĩa fetch EAGER? | Không | Không |
| Có thay thế FK constraint? | Không | Không |

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE,
        CascadeType.REMOVE
    },
    orphanRemoval = true,
    fetch = FetchType.LAZY
)
private List<OrderLine> lines = new ArrayList<>();
~~~

- `cascade REMOVE` xử lý khi đơn hàng bị remove.
- `orphanRemoval` xử lý khi dòng hàng bị tách khỏi đơn.
- `fetch LAZY` vẫn cho phép collection được tải trì hoãn.

Orphan removal phù hợp với entity child có vòng đời phụ thuộc parent. Không dùng nếu dòng hàng có thể được chuyển sang parent khác hoặc cần tồn tại độc lập sau khi bị gỡ khỏi collection.

### Cập nhật cả hai phía quan hệ

Trong quan hệ hai chiều, helper nên giữ object graph nhất quán:

~~~java
public void addLine(OrderLine line) {
    lines.add(line);
    line.attachTo(this);
}

public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.detachFromOrder();
    }
}
~~~

Ở ví dụ trên, owning side `OrderLine.order` được cập nhật trong helper. Việc child bị orphan sẽ được provider xử lý theo `orphanRemoval`. Cần bảo đảm thao tác phù hợp với FK nullable và cách mapping của ứng dụng.

## 14. Cascade và owning side là hai khái niệm riêng

Trong quan hệ hai chiều:

~~~java
// Parent / inverse side
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderLine> lines;

// Child / owning side
@ManyToOne
@JoinColumn(name = "order_id")
private PurchaseOrder order;
~~~

- **Owning side** là phía xác định cập nhật FK hoặc join table.
- **Cascade** xác định thao tác vòng đời được truyền qua association.
- **Fetch** xác định thời điểm/chiến lược tải association.

Ba yếu tố có thể cấu hình độc lập.

Ví dụ, cascade PERSIST đặt trên collection inverse side vẫn có thể truyền thao tác persist tới child; nhưng để FK được ghi đúng, child phải tham chiếu parent ở owning side.

Sai:

~~~java
order.getLines().add(line);
// Nhưng line.order vẫn null.
~~~

Đúng qua helper:

~~~java
order.addLine(line);
~~~

Không phải cứ đặt cascade ở owning side mới cascade được, và cũng không phải cascade tự sửa quan hệ hai chiều. **Cascade không thay thế việc đồng bộ object graph.**

## 15. Tải association bằng fetch plan, không phải cascade

Giả sử chỉ muốn đọc đơn hàng cùng các dòng hàng:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
~~~

Nếu `lines` là LAZY, collection có thể chưa được tải. Muốn lấy cùng dữ liệu trong một query, có thể dùng JPQL fetch join:

~~~java
PurchaseOrder order = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

`JOIN FETCH` yêu cầu provider lấy association trong truy vấn đó. `distinct` thường được dùng để tránh kết quả root trùng lặp ở mức entity khi join collection, tùy provider/query semantics.

Không cần thêm `CascadeType.ALL` hay `CascadeType.PERSIST` để query này tải collection. Fetch join và cascade là hai cơ chế khác nhau.

### Tải cả product cho từng line

Nếu màn hình cần tên sản phẩm:

~~~java
PurchaseOrder order = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines line " +
    "left join fetch line.product " +
    "where o.id = :id",
    PurchaseOrder.class
)
.setParameter("id", orderId)
.getSingleResult();
~~~

Query yêu cầu nạp root, collection và product theo một fetch plan. Nó không thay đổi lifecycle cascade của các entity.

### Entity Graph

JPA cho phép mô tả fetch graph:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

Subgraph<OrderLine> lineGraph =
    graph.addSubgraph("lines");

lineGraph.addAttributeNodes("product");

Map<String, Object> hints = Map.of(
    "jakarta.persistence.fetchgraph",
    graph
);

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    hints
);
~~~

Cần import `jakarta.persistence.EntityGraph`, `jakarta.persistence.Subgraph` và `java.util.Map`. Entity graph mô tả association cần fetch cho lần load này; nó không bật cascade persist/remove và không sửa mapping vòng đời toàn cục.

## 16. LAZY có thể trì hoãn query, nhưng không có nghĩa không bao giờ query

Một association LAZY có thể được đại diện bằng proxy hoặc persistent collection chưa initialized:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, 101L);

// Chưa nhất thiết có SELECT order_lines.
List<OrderLine> lines = order.getLines();

// Truy cập collection có thể khởi tạo nó.
int size = lines.size();
~~~

Nếu persistence context đã đóng trước khi collection được tải:

~~~java
em.close();
order.getLines().size();
~~~

Hibernate có thể ném `LazyInitializationException` vì không còn session để truy vấn. Đây là vấn đề **fetch lifecycle/context**, không phải cascade.

Nếu API cần dữ liệu sau khi đóng context, hãy fetch đúng dữ liệu trong transaction và chuyển sang DTO/projection. Đừng bật CascadeType.ALL với hy vọng collection sẽ được tải trước khi context đóng.

### EAGER cũng không có nghĩa “một JOIN duy nhất”

`FetchType.EAGER` là yêu cầu về trạng thái association được tải khi entity được fetch. Provider có thể dùng join, secondary select hoặc chiến lược khác. Một số mapping EAGER nhiều tầng còn tạo nhiều SQL và nguy cơ N+1.

Nếu cần kiểm soát query cho use case, dùng entity graph, fetch join hoặc DTO query thay vì dựa vào EAGER toàn cục.

## 17. Cascade REMOVE có thể làm collection LAZY được khởi tạo

Đây là điểm tinh tế: cascade không phải fetch instruction, nhưng khi **thực thi một operation cần áp dụng lên từng entity liên quan**, provider có thể phải biết các entity đó là ai.

Ví dụ:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, 101L);
em.remove(order);
~~~

Nếu có `cascade = CascadeType.REMOVE` trên `lines` và collection chưa được khởi tạo, Hibernate có thể cần tải dòng hàng để thực hiện cascade remove theo entity lifecycle, gọi callbacks hoặc xử lý version/association. SQL có thể gồm SELECT trước các DELETE tùy mapping và phiên bản.

Do đó không thể khẳng định:

> “Cascade REMOVE không ảnh hưởng việc tải dữ liệu vì cascade và fetch hoàn toàn độc lập.”

Cách diễn đạt đúng hơn:

- **Cấu hình cascade không yêu cầu eager-load association mỗi lần đọc entity.**
- **Khi một cascade operation được gọi**, provider có thể phải duyệt association và phát SQL để thực hiện operation.
- Việc operation đó cần tải entity hay có thể tối ưu thành bulk/database cascade phụ thuộc mapping và provider.

Đây là lý do phải xem SQL thực tế cho thao tác xóa một aggregate lớn.

## 18. Cascade ORM khác với `ON DELETE CASCADE` ở database

Hai cách có tên gần giống nhưng hoạt động ở hai tầng khác nhau.

### Cascade ORM

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
private List<OrderLine> lines;
~~~

Khi gọi `em.remove(order)`, ORM áp dụng remove tới các entity liên quan theo mapping. Hibernate có thể quản lý lifecycle event, callbacks, version và các thao tác SQL cần thiết.

### Database foreign key cascade

~~~sql
ALTER TABLE order_lines
ADD CONSTRAINT fk_order_lines_order
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE;
~~~

Khi một hàng parent bị database xóa, database tự xóa những hàng child có FK tham chiếu theo ràng buộc. Cơ chế này hoạt động ở tầng database, kể cả khi lệnh delete đến từ ứng dụng không dùng Hibernate.

| Tiêu chí | JPA/Hibernate cascade REMOVE | SQL `ON DELETE CASCADE` |
| --- | --- | --- |
| Được khai báo ở đâu | Association mapping qua `cascade` | Foreign key constraint trong database |
| Được kích hoạt bởi | ORM remove operation trên entity nguồn | SQL DELETE parent tại database |
| Có cần ORM biết child entities? | ORM cascade semantics có thể phải duyệt/nạp child | Database xử lý FK nội bộ |
| Entity callbacks/lifecycle | ORM có thể áp dụng callbacks theo entity remove | DB cascade không gọi JPA callbacks cho từng child |
| Writer ngoài Hibernate | Không tự áp dụng nếu writer không dùng ORM cascade | Vẫn hoạt động vì nằm trong FK |
| Cache/persistence context | ORM có thể đồng bộ entity lifecycle trong context | DB xóa hàng mà context/cache khác có thể chưa biết |
| Tạo DDL FK cascade? | Không nên giả định chỉ vì khai báo JPA cascade | Có trong định nghĩa constraint |

**`CascadeType.REMOVE` không tự đồng nghĩa schema đã có `ON DELETE CASCADE`.** Cần kiểm tra DDL thực tế.

### Hibernate `@OnDelete`

Hibernate có annotation riêng:

~~~java
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "order_id")
@OnDelete(action = OnDeleteAction.CASCADE)
private PurchaseOrder order;
~~~

`@OnDelete` là Hibernate-specific và liên quan hành vi/ràng buộc FK mà provider quản lý. Cú pháp đặt annotation và tác dụng cụ thể cần đối chiếu phiên bản Hibernate. Nó không phải annotation chuẩn Jakarta Persistence, và không nên coi nó thay thế toàn bộ lifecycle semantics của cascade ORM.

Nếu dùng DB cascade, phải hiểu tác động lên cache, entity đang managed và callback. Một transaction khác hoặc native SQL có thể xóa child mà persistence context hiện tại vẫn giữ object cũ.

## 19. Cascade và quan hệ Many-to-Many

Ví dụ bài viết có nhiều tag, một tag được dùng trong nhiều bài:

~~~text
Article A ──┬── Tag Java
            └── Tag ORM

Article B ──┬── Tag Java
            └── Tag Database
~~~

Xóa `Article A` thường chỉ nên xóa các hàng trong join table kết nối A với tag. Những tag Java/ORM có thể vẫn được bài khác dùng.

Mapping:

~~~java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
~~~

Không nên vội thêm `cascade = CascadeType.ALL`. Đặc biệt, cascade REMOVE trên ManyToMany không portable theo khuyến nghị JPA và có nguy cơ xóa entity `Tag` dùng chung.

Nếu chỉ muốn thêm hoặc gỡ một tag khỏi bài, ORM cần đồng bộ join table; không cần xóa bản ghi Tag. Với quan hệ many-to-many có lifecycle phức tạp hoặc thuộc tính riêng trên liên kết, nên cân nhắc biến join table thành entity trung gian, ví dụ `ArticleTag`, để kiểm soát vòng đời rõ hơn.

## 20. Cascade và Many-to-One: cẩn thận với entity dùng chung

`ManyToOne` thường trỏ tới entity có vòng đời độc lập:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "product_id")
private Product product;
~~~

Một `Product` có thể được nhiều `OrderLine` tham chiếu. Cấu hình sau thường sai:

~~~java
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.ALL
)
@JoinColumn(name = "product_id")
private Product product;
~~~

Tại sao?

- Persist một dòng hàng có thể truyền persist tới Product đã tồn tại hoặc detached, gây trạng thái không phù hợp.
- Remove một dòng hàng có thể truyền remove tới Product.
- Product có thể được dùng bởi nhiều đơn hàng khác.
- Refresh/detach cũng bị lan theo ALL dù không phải lúc nào đó là ý định.

Thường nên để Product được quản lý độc lập:

~~~java
Product product = em.getReference(Product.class, productId);

OrderLine line = new OrderLine(
    product,
    quantity,
    price
);

order.addLine(line);
~~~

Chỉ khi entity đích thực sự thuộc vòng đời của source mới cân nhắc cascade phù hợp.

## 21. Cascade REFRESH và DETACH dùng khi nào?

### REFRESH

~~~java
em.refresh(order);
~~~

`refresh` đọc lại trạng thái entity từ database. Nếu association có `CascadeType.REFRESH`, thao tác refresh có thể lan sang các entity liên quan.

Dùng khi cần bỏ trạng thái local chưa lưu và nạp lại dữ liệu DB theo semantics refresh. Không gọi refresh tùy tiện trong lúc có thay đổi pending vì dữ liệu chưa flush có thể bị ghi đè.

### DETACH

~~~java
em.detach(order);
~~~

`detach` tách một entity khỏi persistence context. Nếu cascade DETACH được khai báo, thao tác có thể lan tới entity liên quan.

Điều này có ích trong một số mô hình quản lý context/bộ nhớ, nhưng `em.clear()` đã detach toàn bộ entity managed trong context. Đừng thêm DETACH vào ALL chỉ vì muốn “tải nhẹ hơn”; nó không phải fetch mode và không tự giảm số query khi đọc association.

## 22. Cascade khi entity liên quan đang ở trạng thái nào?

Cascade operation tương tác với vòng đời JPA. Không phải mọi trạng thái của entity đích đều có ý nghĩa giống nhau.

| Trạng thái entity liên quan | Ví dụ | Điều cần hiểu |
| --- | --- | --- |
| New/transient | Child vừa được tạo bằng `new OrderLine(...)` | PERSIST cascade có thể đưa child vào persistence context |
| Managed | Child đã được nạp trong context | Dirty checking theo dõi thay đổi; cascade operation tương ứng vẫn có thể áp dụng |
| Detached | Child đến từ context cũ đã đóng | MERGE cascade có thể hợp nhất trạng thái; PERSIST không phải thay thế MERGE |
| Removed | Child đã được đánh dấu xóa | Không nên tái sử dụng như entity đang hoạt động; trạng thái và lỗi phụ thuộc thao tác |
| Proxy/uninitialized | Reference LAZY tới entity có ID | Operation cascade cần trạng thái có thể buộc khởi tạo; không được suy luận entity tồn tại chỉ từ proxy |

### PERSIST không phải MERGE

- `persist(newEntity)` yêu cầu quản lý một entity mới.
- `merge(detachedEntity)` sao chép trạng thái vào managed instance tương ứng và trả instance managed.
- Nếu child detached và cần merge cùng parent, cấu hình MERGE mới thể hiện ý định đó.
- Không gọi persist lên detached entity như cách “lưu lại”; JPA có thể ném `EntityExistsException` hoặc lỗi persistence tương ứng.

### Cascade không làm entity được lưu ngay lập tức

Sau `persist(root)`, các entity liên quan có thể đã được đánh dấu managed nhưng SQL thường được thực thi khi flush. Không đồng nhất “cascade operation đã áp dụng” với “database đã commit”.

## 23. Cascade không tự động đi qua mọi object reference

Chỉ những association được mapping và có cascade operation tương ứng mới tham gia propagation.

Ví dụ:

~~~java
@Entity
public class PurchaseOrder {
    @OneToMany(cascade = CascadeType.PERSIST)
    private List<OrderLine> lines;

    @ManyToOne
    private Customer customer;
}
~~~

Khi gọi `persist(order)`:

- `lines` có PERSIST cascade nên thao tác có thể lan sang các dòng hàng.
- `customer` không có PERSIST cascade nên không tự động lan persist tới Customer qua mapping đó.
- Nếu `customer` là một entity detached/new chưa được quản lý mà không có cascade phù hợp, provider có thể báo lỗi khi đồng bộ.

Cascade không tự đi theo một field Java bất kỳ không phải association persistent. Một thuộc tính kiểu `Long customerId` chỉ là scalar; JPA không tự suy ra rằng cần gọi persist một Customer từ giá trị ID đó.

### Cascade direction theo association

Cascade được cấu hình trên **attribute association cụ thể**. Nếu muốn thao tác từ parent tới child, khai báo cascade trên association mà parent dùng để tham chiếu child. Không giả định thao tác tự lan ngược từ child về parent chỉ vì hai object có tham chiếu hai chiều.

Trong mapping bidirectional, có thể đặt cascade trên owning side hoặc inverse side tùy ý nghĩa thao tác; owning side quyết định cập nhật FK, còn cascade metadata quyết định propagation. Thiết kế nên đặt cascade ở phía thể hiện rõ quyền sở hữu vòng đời.

## 24. Không nhầm cascade với database trigger hoặc FK action

Ba cơ chế có thể cùng tồn tại nhưng không giống nhau:

1. **ORM cascade:** Hibernate/JPA truyền thao tác lifecycle qua association.
2. **Database FK action:** database tự xử lý child rows khi parent row bị delete/update theo constraint.
3. **Trigger:** database chạy logic được định nghĩa trên sự kiện insert/update/delete.

Ví dụ trigger có thể ghi audit row khi xóa đơn hàng; FK ON DELETE CASCADE có thể xóa các dòng hàng. Cascade REMOVE của ORM có thể gọi lifecycle callback và phát SQL child deletes.

Nếu cả ba cùng tham gia, phải xác định thứ tự và tránh xử lý trùng. Đặc biệt, trigger hoặc database cascade có thể làm database thay đổi mà persistence context không biết. Cần chiến lược refresh/clear/cache invalidation thích hợp sau bulk/native SQL hoặc thao tác ngoài ORM.

## 25. Cascade REMOVE có thể ảnh hưởng hiệu năng xóa

Một đơn hàng có 10.000 dòng hàng. Nếu cascade REMOVE phải xử lý từng entity child:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
em.remove(order);
~~~

Hibernate có thể cần tải collection và phát nhiều thao tác delete. Điều này có thể tốn:

- SELECT để tìm child entities.
- Bộ nhớ cho entity state/collection.
- Entity lifecycle callbacks.
- Nhiều SQL DELETE hoặc batch DELETE.
- Thời gian giữ lock và transaction dài hơn.

Nếu schema có FK `ON DELETE CASCADE`, database có thể xóa các child rows trực tiếp khi xóa parent, giảm việc ORM phải materialize từng child. Nhưng cách kết hợp DB cascade với Hibernate cascade và cache cần được thiết kế theo provider/version.

Không chọn DB cascade chỉ vì muốn xóa nhanh nếu nghiệp vụ yêu cầu callback, audit logic hoặc kiểm tra trên từng child entity. Có thể dùng một câu lệnh bulk delete có điều kiện nếu semantics phù hợp, nhưng bulk delete bỏ qua lifecycle tracking thông thường và cần xử lý cache/context.

### Batch processing

Nếu xóa lượng lớn dữ liệu, hãy cân nhắc:

- Chia transaction theo batch nếu nghiệp vụ cho phép.
- Dùng JDBC batch hoặc cơ chế bulk DML phù hợp.
- Xem FK/index và lock contention.
- Tránh giữ hàng trăm nghìn managed entities trong một persistence context.
- Định nghĩa rõ callback/audit nào phải được giữ.

Đây là quyết định về semantics và hiệu năng, không có một cascade setting phù hợp cho mọi quy mô.

## 26. Xóa bằng bulk JPQL khác cascade REMOVE

JPA có bulk delete:

~~~java
int deleted = em.createQuery(
    "delete from OrderLine l where l.order.id = :orderId"
)
.setParameter("orderId", orderId)
.executeUpdate();
~~~

Đây là bulk DML. Nó không tương đương gọi `em.remove(line)` cho từng entity:

- Cascade REMOVE của từng entity không tự được áp dụng như khi gọi remove trên entity root.
- Entity lifecycle callbacks cho từng child không chạy theo cách remove entity thông thường.
- Managed objects đã có trong persistence context có thể trở nên stale.
- Version/cascade/orphan semantics không tự được thực thi như thao tác entity-by-entity.

Nếu bulk delete rồi tiếp tục dùng các `OrderLine` đã managed, cần xử lý context, ví dụ flush trước nếu cần đồng bộ pending changes và clear/refresh phù hợp sau đó. `clear()` tác động tất cả entity trong context nên cần cân nhắc.

**Bulk delete không phải lối tắt tương đương cascade remove.** Chỉ dùng khi chủ đích là DML theo tập dữ liệu và chấp nhận lifecycle semantics khác.

## 27. Lỗi thường gặp khi ghép cascade và fetch

| Triệu chứng | Nhầm lẫn/nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thêm PERSIST cascade nhưng collection vẫn LAZY khi đọc | Cascade không phải fetch | Dùng entity graph/fetch join nếu cần tải |
| Association EAGER nhưng child không tự persist | Fetch không phải cascade | Khai báo PERSIST nếu vòng đời cần lan |
| Xóa parent làm mất entity dùng chung | Cascade REMOVE đặt trên quan hệ shared | Bỏ REMOVE; xác định ownership |
| Persist root báo transient child | Thiếu PERSIST cascade hoặc persist child rõ ràng | Chọn cascade phù hợp với aggregate |
| Merge parent nhưng child không nhận trạng thái | Thiếu MERGE cascade hoặc merge graph sai | Xem trạng thái child và cascade mapping |
| LAZY collection phát SELECT khi remove parent | Cascade REMOVE cần duyệt child | Quan sát SQL; đánh giá DB cascade/bulk strategy |
| Xóa child khỏi collection nhưng DB vẫn còn | Không có orphanRemoval hoặc owning side không đồng bộ | Dùng orphanRemoval phù hợp và helper cập nhật hai phía |
| Xóa parent lỗi FK | Không cascade, không DB ON DELETE CASCADE và child vẫn tồn tại | Chọn chiến lược xóa phù hợp constraint |
| Xóa bài viết làm mất tag dùng chung | Cascade REMOVE trên ManyToMany | Chỉ xóa join rows/entity link |
| Thêm ALL gây lỗi detached entity | ALL bao gồm PERSIST/MERGE/REMOVE/REFRESH/DETACH | Chỉ khai báo operation thực sự cần |
| JSON serialization gây query/lazy exception | Fetch state không phù hợp boundary | Trả DTO, fetch đúng dữ liệu trong transaction |
| Bulk delete xong entity cũ vẫn còn trong context | Bulk DML không đồng bộ managed state | Flush/clear/refresh có chủ đích |
| Database cascade xóa row nhưng cache vẫn còn | ORM không biết mọi thay đổi do DB thực hiện | Cache invalidation/clear và transaction boundary |
| Thay inverse collection nhưng FK không đổi | Owning side chưa được cập nhật | Đồng bộ phía chứa FK |
| Cascade ALL bị gọi refresh làm mất sửa đổi | REFRESH cũng được cascade | Không dùng ALL nếu không muốn refresh lan |

## 28. Cách chọn cascade theo mô hình domain

Không có quy tắc “mọi OneToMany đều ALL”. Hãy quyết định theo vòng đời thực:

| Mô hình | Cascade thường cân nhắc | Lý do |
| --- | --- | --- |
| Order → OrderLine, child chỉ thuộc một order | PERSIST, MERGE, REMOVE; thường kết hợp orphanRemoval | Child thuộc aggregate root |
| BlogPost → Comment, comment phụ thuộc post | PERSIST, MERGE, REMOVE; orphanRemoval nếu gỡ comment đồng nghĩa xóa | Vòng đời comment gắn với post |
| Invoice → InvoiceLine | PERSIST, REMOVE, có thể MERGE | Dòng hóa đơn không tồn tại độc lập |
| OrderLine → Product | Thường không cascade REMOVE/PERSIST | Product là entity dùng chung |
| Employee → Department | Thường không cascade REMOVE | Department có vòng đời độc lập và nhiều employee |
| Article ↔ Tag ManyToMany | Thường tránh REMOVE; có thể cân nhắc PERSIST theo quy trình tạo tag | Tag dùng chung; xóa association không xóa tag |
| User → UserProfile OneToOne độc quyền | Có thể ALL hoặc PERSIST/MERGE/REMOVE | Profile có thể thuộc vòng đời user |
| Parent → AuditRecord độc lập | Tùy yêu cầu retention; có thể không cascade remove | Audit có thể phải tồn tại sau khi parent bị xóa |

Bảng chỉ là gợi ý. Quy tắc thực tế phụ thuộc quyền sở hữu dữ liệu, retention, compliance và khả năng entity được tham chiếu từ nơi khác.

## 29. Một bài toán thiết kế: aggregate root và ranh giới cascade

Trong mô hình domain-driven design, **aggregate root** là điểm vào được dùng để quản lý invariant của một nhóm entity/value object. Cascade thường phù hợp khi thao tác từ root cần truyền tới các entity con thuộc cùng aggregate.

Ví dụ:

~~~text
PurchaseOrder (aggregate root)
  ├── OrderLine
  ├── OrderLine
  └── OrderLine

Product (aggregate khác/shared)
Customer (aggregate khác/shared)
~~~

Một service tạo đơn:

~~~java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    PurchaseOrder order = new PurchaseOrder(command.orderCode());

    for (CreateLineCommand line : command.lines()) {
        Product product = productRepository
            .getReferenceById(line.productId());

        order.addLine(new OrderLine(
            product,
            line.quantity(),
            line.unitPrice()
        ));
    }

    PurchaseOrder managed = orderRepository.save(order);
    return managed.getId();
}
~~~

Giả định repository và command types đã được định nghĩa. Nếu `PurchaseOrder.lines` có PERSIST cascade, root save/persist có thể truyền thao tác persist tới các dòng hàng mới. Product reference chỉ dùng để gắn FK và không bị persist/remove cascade từ dòng hàng.

Điều này thể hiện **ranh giới vòng đời**: đơn hàng quản lý dòng hàng; đơn hàng không sở hữu vòng đời sản phẩm hay khách hàng.

### Cascade không thay thế validation aggregate

Trước khi persist, service vẫn phải xác minh:

- Người dùng có quyền đặt hàng với customer không?
- Product có được phép bán không?
- Quantity và unit price có hợp lệ không?
- Có đủ tồn kho không?
- Đơn hàng có đáp ứng các invariant không?

Cascade chỉ truyền lifecycle operation; nó không tự thực hiện quy tắc nghiệp vụ.

## 30. Quan sát SQL để thấy cascade và fetch khác nhau

Trong môi trường phát triển, bật SQL log phù hợp phiên bản Hibernate. Ví dụ Spring Boot + Hibernate 6:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Không bật bind parameter TRACE trong production nếu log có thể chứa PII hoặc dữ liệu nhạy cảm.

### Thử nghiệm A — Tải parent với LAZY collection

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, 101L);
~~~

Nếu collection chưa được yêu cầu, SQL có thể chỉ lấy `purchase_orders`. `cascade = PERSIST` hoặc `REMOVE` không làm query đọc collection tự động chạy ở thao tác find này.

### Thử nghiệm B — Truy cập collection

~~~int count = order.getLines().size();
~~~

Collection LAZY có thể được khởi tạo bằng SELECT.

### Thử nghiệm C — Persist aggregate mới

~~~PurchaseOrder order = new PurchaseOrder("ORD-200");
order.addLine(new OrderLine(productRef, 2, price));
em.persist(order);
~~~

PERSIST cascade có thể làm Hibernate lên lịch insert child. Đây là propagation của lifecycle operation, không phải eager fetch.

### Thử nghiệm D — Remove aggregate

~~~PurchaseOrder order = em.find(PurchaseOrder.class, 101L);
em.remove(order);
~~~

REMOVE cascade có thể yêu cầu provider duyệt child; có thể thấy SELECT và DELETE tùy mapping. Không nên giả định cascade remove không bao giờ khởi tạo collection.

Số SQL chính xác phụ thuộc ID generator, cache, batching, collection state, database cascade và phiên bản provider. Hãy đọc SQL theo **mục đích operation**, không suy luận từ một annotation đơn lẻ.

## 31. Bài tập tình huống

**Bài 1 — Cascade persist và fetch lazy**

`PurchaseOrder.lines` có `cascade=PERSIST` và `fetch=LAZY`. Khi gọi `find(PurchaseOrder.class,id)`, các dòng hàng có bắt buộc được tải ngay không?

**Đáp án:** Không. PERSIST cascade không phải fetch instruction. Collection vẫn theo fetch strategy, thường được trì hoãn.

**Bài 2 — EAGER nhưng không cascade**

`PurchaseOrder.customer` dùng `fetch=EAGER` nhưng không có cascade PERSIST. Khi persist một order tham chiếu một Customer mới chưa được persist, EAGER có tự lưu Customer không?

**Đáp án:** Không. EAGER nói về tải dữ liệu; nó không truyền thao tác persist.

**Bài 3 — Xóa một OrderLine**

`OrderLine.product` tham chiếu Product dùng chung. Có nên cascade REMOVE từ line sang product không?

**Đáp án:** Thường không. Product có thể được các dòng hàng khác sử dụng. Xóa line chỉ nên xóa association/line theo nghiệp vụ.

**Bài 4 — Gỡ child khỏi collection**

Một dòng hàng bị loại khỏi `PurchaseOrder.lines`. Muốn xóa row child theo hành vi association, nên xem cơ chế nào?

**Đáp án:** `orphanRemoval=true` trên OneToMany/OneToOne, đồng thời cập nhật owning side. Cascade REMOVE chủ yếu truyền khi remove parent.

**Bài 5 — Cascade ALL có gồm FIND không?**

**Đáp án:** Không. `ALL` bao gồm PERSIST, MERGE, REMOVE, REFRESH và DETACH; không có CascadeType.FIND.

**Bài 6 — Cascade REMOVE và ON DELETE CASCADE**

Nếu JPA mapping có `cascade=REMOVE`, database chắc chắn có FK `ON DELETE CASCADE` không?

**Đáp án:** Không. Cascade ORM và database FK action là hai cấu hình độc lập.

**Bài 7 — Xóa Article có xóa Tag không?**

Một Article có nhiều Tag và Tag được chia sẻ. Có nên dùng cascade REMOVE trên ManyToMany?

**Đáp án:** Không nên. Thường chỉ xóa hàng join table. Tag vẫn tồn tại để Article khác dùng; REMOVE cascade trên ManyToMany cũng không portable theo khuyến nghị JPA.

**Bài 8 — Merge parent detached**

Một graph detached chứa Order và các OrderLine đã thay đổi. Muốn merge cả graph, cần chú ý gì?

**Đáp án:** Cần MERGE cascade trên association phù hợp và dùng managed instance mà `em.merge` trả về. Phải bảo đảm graph detached đầy đủ/đúng nghiệp vụ để không ghi đè dữ liệu ngoài ý muốn.

**Bài 9 — Cascade remove làm phát SELECT**

Collection là LAZY nhưng xóa parent lại thấy SELECT child. Điều đó có mâu thuẫn không?

**Đáp án:** Không. Fetch LAZY không yêu cầu load khi đọc bình thường; cascade REMOVE có thể cần duyệt child để áp dụng lifecycle operation.

**Bài 10 — Sửa inverse side**

Chỉ thêm OrderLine vào collection `PurchaseOrder.lines` nhưng không gán `OrderLine.order`. FK có chắc được cập nhật không?

**Đáp án:** Không. Phía chứa FK là owning side và phải được đồng bộ.

**Bài 11 — Bulk delete**

Dùng JPQL `delete from OrderLine ...` có áp dụng callback/cascade REMOVE của từng entity không?

**Đáp án:** Không theo lifecycle entity thông thường. Bulk DML bỏ qua cơ chế remove từng managed entity; cần xử lý context/cache và semantics riêng.

**Bài 12 — Cascade DETACH**

Có `CascadeType.DETACH` trên collection. Khi gọi `em.detach(order)`, điều gì có thể xảy ra?

**Đáp án:** Thao tác detach có thể lan tới child entities được mapping cascade. Đây không phải thao tác tải hoặc xóa database.

## 32. Bảng quyết định nhanh

| Mục tiêu | Cơ chế cần xem | Không nên nhầm với |
| --- | --- | --- |
| Persist parent và child mới cùng nhau | `CascadeType.PERSIST` | `FetchType.EAGER` |
| Merge graph detached | `CascadeType.MERGE` | Dirty checking của entity managed |
| Remove child khi remove parent | `CascadeType.REMOVE` | `ON DELETE CASCADE` |
| Xóa child khi gỡ khỏi collection | `orphanRemoval=true` | Chỉ cascade persist |
| Tải association khi truy vấn | LAZY/EAGER, entity graph, fetch join | Cascade operation |
| Xóa hàng child ở tầng DB | FK `ON DELETE CASCADE` | JPA lifecycle callbacks |
| Chỉ xóa liên kết ManyToMany | Đồng bộ join table | Xóa entity đích |
| Làm mới graph | `CascadeType.REFRESH` | Fetch EAGER mặc định |
| Detach graph | `CascadeType.DETACH` | Đóng transaction hoặc xóa entity |
| Tránh N+1 | Fetch plan, batch fetching, projection | Thêm `CascadeType.ALL` |

## 33. Nguyên tắc thiết kế cần ghi nhớ

1. **Cascade truyền thao tác vòng đời, fetch quyết định thời điểm tải dữ liệu.** Hai cơ chế có thể cùng xuất hiện trên một association nhưng giải quyết câu hỏi khác nhau.
2. **Không có CascadeType.FIND hoặc CascadeType.LOAD trong JPA.** Gọi find không tự cascade thao tác tìm kiếm qua mọi quan hệ.
3. **LAZY vẫn có thể kết hợp PERSIST/MERGE/REMOVE cascade.** Nhưng một operation cascade có thể cần provider duyệt hoặc tải association để hoàn thành.
4. **Cascade theo ranh giới sở hữu vòng đời.** Child thuộc parent thường có cascade phù hợp; entity dùng chung như Product/Tag thường không cascade REMOVE.
5. **Owning side quyết định FK; cascade quyết định propagation.** Hai phía của quan hệ hai chiều cần được đồng bộ trong object graph.
6. **orphanRemoval khác cascade REMOVE.** Một cái xử lý child bị gỡ khỏi association; cái kia truyền thao tác remove từ parent.
7. **Cascade ORM khác FK ON DELETE CASCADE.** Một bên quản lý entity lifecycle; một bên do database thực hiện.
8. **Bulk DML không tương đương remove/persist từng entity.** Callbacks, cascade và persistence context có thể không được đồng bộ như thao tác entity thông thường.
9. **ALL không phải lựa chọn mặc định.** Nó gồm PERSIST, MERGE, REMOVE, REFRESH và DETACH; chỉ dùng khi tất cả đều đúng với vòng đời domain.
10. **Dùng fetch plan cho use case đọc.** Entity graph, join fetch và DTO projection giúp tải đúng dữ liệu mà không phải thay cascade mapping.

Khi thiết kế một association, hãy tự hỏi theo thứ tự: **entity nào sở hữu vòng đời của entity nào, operation nào cần lan truyền, và dữ liệu nào cần được tải ở use case hiện tại?** Trả lời riêng ba câu hỏi đó sẽ giúp cascade, orphan removal và fetch strategy phối hợp đúng, tránh xóa nhầm dữ liệu dùng chung cũng như tránh truy vấn không cần thiết.
