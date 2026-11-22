# Phân biệt tải ngay và tải chậm ở mức ánh xạ trong JPA

Trong ứng dụng dùng **Jakarta Persistence (JPA)**, việc gọi `EntityManager.find()` hoặc thực thi một truy vấn trả về entity không đồng nghĩa mọi thông tin liên quan đến entity đều được nạp từ cơ sở dữ liệu ngay lập tức. Một đối tượng có thể tham chiếu tới khách hàng, danh mục, các dòng đơn hàng và nhiều tập hợp khác. Nếu luôn tải tất cả quan hệ, một thao tác đơn giản có thể kéo theo hàng nghìn bản ghi không cần thiết. Nếu trì hoãn mọi dữ liệu, ứng dụng có thể phát sinh nhiều câu SQL phụ hoặc lỗi khi truy cập quan hệ sau khi persistence context đã đóng.

JPA cho phép điều khiển **thời điểm yêu cầu nạp thuộc tính hoặc association** bằng `FetchType.EAGER` và `FetchType.LAZY` tại mức khai báo mapping:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

Và một mapping khác:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
~~~

Hai cách này có **ý nghĩa khác nhau về kế hoạch tải**, nhưng không thể hiểu đơn giản “EAGER = JOIN một SQL” và “LAZY = luôn chỉ một SQL”. JPA quyết định **cần nạp dữ liệu gì**, còn số câu SQL, JOIN, batch, cache và thời điểm phát SQL cụ thể phụ thuộc query, persistence context, provider và cấu hình.

Bài học làm rõ:

- Ý nghĩa thực tế của `EAGER`, `LAZY` và **default** trên từng loại mapping.
- Mối quan hệ giữa **fetch timing** (thời điểm nạp) và **fetch strategy** (JOIN, SELECT phụ, batch).
- Cách to-one proxy, lazy collection và basic attribute hoạt động, cùng các giới hạn tính portable.
- Tương tác với transaction, managed/detached state, serialization, `LazyInitializationException` và N+1 queries.
- Cách chọn mapping mặc định hợp lý rồi điều chỉnh fetch plan theo từng use case bằng `JOIN FETCH`, entity graph và DTO projection.
- Cách quan sát, kiểm thử và tối ưu tải dữ liệu trong dự án thực tế.

## 1. Vì sao kế hoạch tải quan trọng?

Giả sử ứng dụng bán hàng có:

~~~text
Customer ──────< PurchaseOrder ──────< OrderLine >────── Product >──── Category
  1                    N               1     N             1              1
~~~

Một màn hình chỉ liệt kê:

~~~text
Order ID | Ngày đặt | Trạng thái
~~~

không cần tải ngay Customer, toàn bộ OrderLine, Product và Category. Nhưng màn hình chi tiết đơn hàng lại cần tên khách, từng dòng hàng và SKU.

Nếu mapping luôn EAGER:

~~~text
Tìm 100 đơn hàng
    |
    +-- Tải 100 Customer hoặc nhiều association
    |
    +-- Tải hàng trăm OrderLine
    |
    +-- Tải Product và Category tương ứng
    |
    v
Chi phí SQL, bộ nhớ, I/O, serialization tăng
~~~

Nếu mapping LAZY nhưng service không thiết kế truy vấn phù hợp:

~~~text
SELECT 100 đơn hàng
    |
    v
Vòng lặp getCustomer().getName()
    |
    +-- SQL lấy Customer 1
    +-- SQL lấy Customer 2
    +-- ...
    +-- SQL lấy Customer N
    |
    v
N+1 query và độ trễ lớn
~~~

Do đó, **tải đúng dữ liệu, đúng lúc và đúng số lần** là một bài toán thiết kế. Annotation mapping cung cấp chính sách mặc định; query và service quyết định dữ liệu cần cho một use case cụ thể.

## 2. Ba khái niệm phải tách biệt

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Fetch timing** | Association được yêu cầu nạp ngay hay được phép hoãn? | `FetchType.EAGER`, `FetchType.LAZY` |
| **Fetch strategy** | Provider lấy dữ liệu bằng SQL nào? | JOIN trong một câu, SELECT phụ, batch select |
| **Fetch plan** | Use case này cần những thuộc tính/association nào? | Mapping defaults, `JOIN FETCH`, entity graph |

### EAGER không có nghĩa JOIN

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
~~~

Provider có thể nạp Customer:

1. Bằng JOIN trong SQL tải PurchaseOrder.
2. Bằng SELECT thứ hai dựa trên customer_id.
3. Thông qua entity đã được quản lý trong persistence context hoặc cache khi phù hợp.

Mục đích của EAGER là **đảm bảo thuộc tính/association được eager fetch theo quy tắc JPA**, không cam kết một số round-trip SQL cố định.

### LAZY không có nghĩa “chắc chắn không nạp”

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

LAZY là **hint** rằng dữ liệu có thể được tải khi cần. Provider có thể chủ động nạp trong một số tình huống, ví dụ query đã fetch join association, entity graph yêu cầu nạp, implementation không hỗ trợ hoãn thuộc tính đó, hoặc dữ liệu đã có sẵn.

**Kết luận đầu tiên:** FetchType mô tả **chính sách tải**, không phải lệnh trực tiếp “JOIN hay SELECT” và cũng không phải thước đo số SQL.

## 3. FetchType trong Jakarta Persistence

Hai giá trị chính của enum:

~~~java
import jakarta.persistence.FetchType;

FetchType.EAGER;
FetchType.LAZY;
~~~

### FetchType.EAGER

Là **yêu cầu tải ngay** đối với thuộc tính/association trong phạm vi đặc tả áp dụng. Khi ứng dụng nhận entity ở trạng thái phù hợp, dữ liệu được khai báo EAGER cần có sẵn theo nghĩa fetch.

Nhưng EAGER không cam kết:

- Dùng một câu SQL duy nhất.
- Dùng JOIN thay vì SELECT phụ.
- Không truy cập cache.
- Tải cả những association khác mà EAGER association tham chiếu gián tiếp theo một độ sâu vô hạn.
- Tăng hiệu năng cho mọi use case.

### FetchType.LAZY

Là **gợi ý tải trì hoãn**; provider được phép không tải ngay dữ liệu của attribute/association cho đến khi ứng dụng cần. Chất lượng và mức độ hỗ trợ LAZY khác nhau giữa collection, to-one và basic attributes.

LAZY không cam kết:

- Luôn trả proxy.
- Luôn phát một SELECT khi gọi getter.
- Bất cứ provider nào cũng có thể trì hoãn mọi to-one hoặc basic field.
- Truy cập sau khi EntityManager đóng vẫn hoạt động.
- Tự động tránh N+1 queries.

### Cùng một entity có thể trộn hai loại fetch

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;

@Basic(fetch = FetchType.EAGER)
private String referenceCode;
~~~

Những annotation chỉ khai báo **chính sách riêng của từng thuộc tính**, không chuyển toàn bộ entity thành một chế độ EAGER hoặc LAZY duy nhất.

## 4. Bảng default fetch tại mức mapping

Đây là kiến thức rất quan trọng khi đọc một entity không khai báo `fetch = ...`.

| Annotation | Default | Bản chất |
| --- | --- | --- |
| `@Basic` | **EAGER** | Basic field |
| `@ManyToOne` | **EAGER** | To-one association |
| `@OneToOne` | **EAGER** | To-one association |
| `@OneToMany` | **LAZY** | To-many collection |
| `@ManyToMany` | **LAZY** | To-many collection |
| `@ElementCollection` | **LAZY** | Collection các basic/embeddable values |

Ví dụ:

~~~java
@ManyToOne
private Customer customer; // Mặc định EAGER.

@OneToMany(mappedBy = "order")
private List<OrderLine> lines; // Mặc định LAZY.
~~~

Chỉ nhìn vào hai association đều không ghi `fetch` mà kết luận chúng giống nhau là **sai**.

### @Id, @Version và @Transient

Khóa chính và version đóng vai trò định danh/quản lý trạng thái entity; chúng không được xem là các association có thể mặc định LAZY theo cách `@ManyToOne` hay `@OneToMany`. Thuộc tính `@Transient` không được JPA lưu vào database, nên không có câu hỏi “JPA fetch từ DB lúc nào?” theo cơ chế persistent attribute.

### @Lob và @Basic(fetch = LAZY)

Một field lớn:

~~~java
@Lob
@Basic(fetch = FetchType.LAZY)
private String fullDescription;
~~~

không đồng nghĩa JPA bảo đảm CLOB/text sẽ luôn chỉ được nạp khi gọi getter. Lazy basic attribute có thể cần bytecode enhancement hoặc hỗ trợ đặc biệt của provider. **LAZY trên basic field chỉ nên coi là tối ưu có điều kiện, phải kiểm chứng**.

## 5. Mô hình entity xuyên suốt

Ta dùng một ứng dụng bán hàng với các quan hệ:

~~~text
Customer
    id
    name
    email
       |
       | 1
       |
       | N
PurchaseOrder
    id
    placedAt
    status
    customer_id
       |
       | 1
       |
       | N
OrderLine
    id
    quantity
    order_id
    product_id
       |
       | N
       |
       | 1
Product
    id
    sku
    name
    price
    category_id
       |
       | N
       |
       | 1
Category
    id
    code
    name
~~~

Nhu cầu đọc thường gặp:

- **Danh sách đơn:** chỉ cần Order ID, ngày, trạng thái.
- **Chi tiết đơn:** cần Customer name và danh sách OrderLine.
- **Bảng giao vận:** cần Order ID, Customer name, Product SKU, quantity.
- **Danh mục sản phẩm:** cần Product name và Category code.
- **Thống kê:** có thể chỉ cần COUNT/SUM, không cần nạp bất kỳ entity graph đầy đủ.

Cùng một mapping nhưng các nhu cầu tải khác nhau. Đó là lý do mapping defaults và query-level fetch plan phải được thiết kế tách biệt.

## 6. Entity Customer

~~~java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.FetchType;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    @OneToMany(
        mappedBy = "customer",
        fetch = FetchType.LAZY
    )
    private List<PurchaseOrder> orders =
        new ArrayList<>();

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
~~~

`orders` là một collection-valued association. Theo JPA, `@OneToMany` mặc định LAZY; ở đây viết tường minh để người đọc nhận thấy lựa chọn.

Khi tải Customer chỉ để đọc tên, không cần tải mọi PurchaseOrder của Customer. Với khách hàng có hàng nghìn đơn, EAGER collection có thể tạo tải dữ liệu rất lớn hoặc phát sinh nhiều câu SQL.

## 7. Entity PurchaseOrder với hai association LAZY

~~~java
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
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private OrderStatus status;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY,
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines =
        new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Instant getPlacedAt() {
        return placedAt;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }
}
~~~

Enum:

~~~java
package com.example.shop;

public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

### Những điểm cần tách biệt

- `customer` là quan hệ **many-to-one**, default JPA vốn EAGER, nhưng ở đây **chọn LAZY tường minh**.
- `lines` là quan hệ **one-to-many**, default LAZY và vẫn khai báo LAZY.
- `cascade = CascadeType.ALL` điều khiển **lan truyền thao tác vòng đời** như persist/remove, không điều khiển fetch timing.
- `orphanRemoval = true` điều khiển xử lý phần tử bị xóa khỏi quan hệ sở hữu tương ứng, **không có nghĩa eager load**.
- `optional = false` mô tả quan hệ cần có ở mức JPA; `@JoinColumn(nullable=false)` hướng đến ràng buộc FK cột SQL, không quyết định EAGER/LAZY.

**Đừng nhầm `CascadeType.ALL` với “tải tất cả dữ liệu”.** Hai thuộc tính này giải quyết hai vấn đề khác nhau.

## 8. Entity OrderLine

~~~java
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

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    protected OrderLine() {
    }

    public Long getId() {
        return id;
    }

    public int getQuantity() {
        return quantity;
    }

    public Product getProduct() {
        return product;
    }

    public void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Ở đây:

- Khi nạp OrderLine không nhất thiết nạp PurchaseOrder ngược lại.
- Khi nạp OrderLine không nhất thiết nạp Product đầy đủ.
- Khi ứng dụng cần Product SKU, phải đảm bảo Product được nạp trong fetch plan phù hợp hoặc truy cập khi persistence context còn hoạt động.

## 9. Entity Product và Category

~~~java
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

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
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

    public BigDecimal getPrice() {
        return price;
    }

    public Category getCategory() {
        return category;
    }
}
~~~

~~~java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.FetchType;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String name;

    @OneToMany(
        mappedBy = "category",
        fetch = FetchType.LAZY
    )
    private List<Product> products =
        new ArrayList<>();

    protected Category() {
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public List<Product> getProducts() {
        return products;
    }
}
~~~

Nhìn vào hai hướng của cùng quan hệ:

~~~text
Product.category -> ManyToOne(fetch=LAZY)
Category.products -> OneToMany(fetch=LAZY)
~~~

**Fetch type được khai báo cho từng phía association.** Nó không bắt buộc đối xứng. Nếu Product.category là EAGER, điều đó không suy ra Category.products cũng EAGER. Hai điều khiển phục vụ hai đường truy cập khác nhau.

## 10. EAGER trên @ManyToOne: default dễ bị bỏ quên

Xét một mapping không ghi `fetch`:

~~~java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

JPA hiểu tương đương:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Nếu truy vấn:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
~~~

thì provider phải đáp ứng yêu cầu EAGER cho Customer, nhưng có thể dùng:

~~~sql
SELECT ... FROM purchase_orders;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
-- Có thể tiếp tục với nhiều customer_id khác.
~~~

**EAGER không đồng nghĩa một JOIN duy nhất.** Ngay cả khi code Java không gọi `getCustomer()`, việc có association EAGER có thể làm provider phải lấy thêm dữ liệu để hoàn tất việc nạp Order.

### Có phải luôn một câu SELECT phụ trên mỗi Order?

Không. Nếu 100 Order cùng tham chiếu 5 Customer, identity map/cache hoặc batch fetching có thể giảm số truy vấn. Provider cũng có thể chọn JOIN. N+1 là **nguy cơ**, không phải công thức chắc chắn với mọi query.

### Khi nào nên đổi default?

Với entity thường được truy vấn cho nhiều màn hình, một lựa chọn phổ biến là khai báo rõ `fetch = FetchType.LAZY` cho các `@ManyToOne` không cần thiết trong mọi trường hợp, rồi fetch theo từng use case. Nhưng luôn cần xác nhận khả năng lazy to-one của provider/bytecode configuration.

## 11. EAGER trên @OneToOne: những tình huống riêng

`@OneToOne` cũng mặc định EAGER:

~~~java
@OneToOne
private UserProfile profile;
~~~

Tương đương chính sách:

~~~java
@OneToOne(fetch = FetchType.EAGER)
private UserProfile profile;
~~~

Một entity User có thể chỉ cần email, không cần toàn bộ UserProfile. Với profile có dữ liệu lớn, EAGER có thể gây I/O không cần.

Chuyển sang:

~~~java
@OneToOne(
    mappedBy = "user",
    fetch = FetchType.LAZY
)
private UserProfile profile;
~~~

có thể **không đơn giản** như chuyển một collection sang LAZY. Đặc biệt ở phía inverse `mappedBy` và association nullable, provider có thể phải truy vấn để biết **có profile hay không** trước khi trả object, hoặc cần bytecode enhancement để trì hoãn.

### Phía sở hữu và phía inverse

Giả sử:

~~~java
// UserProfile là phía sở hữu FK.
@OneToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "user_id")
private User user;
~~~

Trong mapping một-một, vị trí FK, optionality, shared primary key (`@MapsId`) và cách provider triển khai proxy ảnh hưởng khả năng LAZY.

Không có quy tắc portable “thêm LAZY vào OneToOne là luôn không query cho đến lúc truy cập”. **Hãy đo SQL và kiểm thử đúng phía association.**

## 12. LAZY trên collection: hoạt động thường gặp

Với:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

một tình huống thường gặp:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

// Có thể mới lấy purchase_orders.

List<OrderLine> lines = order.getLines();

// Tùy provider, mới nhận collection wrapper.
// Truy cập nội dung thường kích hoạt nạp:
for (OrderLine line : lines) {
    System.out.println(line.getQuantity());
}
~~~

Provider có thể dùng một lazy collection wrapper chứa thông tin entity owner và chiến lược truy xuất. Việc **lấy reference collection** chưa chắc đã tải các phần tử; việc duyệt nó thường khiến SQL được phát nếu chưa loaded.

### Những thao tác có thể kích hoạt lazy loading

- `iterator()`, `forEach(...)`, `stream()`.
- `size()`, `isEmpty()` hoặc `contains(...)` trong nhiều provider/configuration.
- Truy cập phần tử theo index.
- `toArray()`, `toString()`, logging sâu.
- JSON serialization hoặc object mapping framework đọc toàn bộ collection.

**Không giả định `size()` luôn chỉ truy vấn COUNT rẻ**. Một số extension như Hibernate extra-lazy có thể tối ưu riêng lẻ; đó không phải bảo đảm chung của JPA.

## 13. LAZY trên to-one: proxy và bytecode enhancement

Với:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

provider có thể biết khóa ngoại `customer_id` của Order nhưng chưa có toàn bộ Customer:

~~~text
PurchaseOrder#100
   customer_id = 7
   |
   v
Customer reference/proxy có identity 7
   |
   +-- getName() -> có thể phải SELECT Customer#7
~~~

Một proxy là object đại diện cho entity có identity đã biết, nhưng dữ liệu thuộc tính có thể được lấy sau. Trong một số mô hình, provider có thể dùng bytecode enhancement thay vì một proxy subclass theo cách truyền thống.

### Không viết code lệ thuộc tên class proxy

Ví dụ:

~~~java
customer.getClass() == Customer.class
~~~

có thể không đúng khi object là proxy subclass của Hibernate. Nên thiết kế business logic dựa trên entity identity, type semantics và API được provider khuyến nghị nếu thật sự cần nhận diện class thực.

### Getter lấy ID có cần SQL không?

Một số provider/proxy có thể trả identifier mà không initialization toàn entity. Tuy nhiên, không coi “`customer.getId()` chắc chắn không SELECT” là một bảo đảm portable trên mọi kiểu to-one và implementation. Nếu chỉ cần customerId trong danh sách, query projection theo path/id có thể rõ ràng hơn.

### Những giới hạn thực tế

- Provider phải biết identity hoặc dùng cơ chế instrumentation thích hợp.
- Một số entity final, method final hoặc cấu trúc bytecode có thể làm proxy subclass gặp hạn chế tùy provider.
- To-one phía inverse của `@OneToOne` có thể cần truy vấn để xác định null.
- Entity đã detached không thể mặc định fetch dữ liệu mới từ context đã đóng.

Đặc biệt với LAZY to-one, **kiểm chứng trong môi trường build thật** quan trọng hơn chỉ đọc annotation.

## 14. @Basic(fetch = LAZY): trường lớn và giới hạn portable

Giả sử Product có mô tả HTML lớn:

~~~java
@Lob
@Basic(fetch = FetchType.LAZY)
@Column(name = "full_description")
private String fullDescription;
~~~

Mong muốn là trang catalog chỉ lấy id/sku/name/price, còn mô tả lớn chỉ nạp ở trang chi tiết. Nhưng JPA định nghĩa LAZY đối với basic field như một **hint**, và một số provider cần bytecode enhancement để biết khi nào field được đọc.

### Một tình huống gây bất ngờ

~~~java
Product product = em.find(Product.class, id);
// Dù @Basic(fetch=LAZY), SQL có thể vẫn lấy full_description.
~~~

Nếu không có enhancement hoặc provider không hỗ trợ lazy basic theo mapping, cột có thể được tải ngay.

### Các cách thiết kế khác

1. **DTO projection** chỉ chọn các cột cần cho danh sách.
2. Tách mô tả rất lớn sang entity riêng như `ProductContent` và dùng association phù hợp.
3. Dùng provider-supported bytecode enhancement để hỗ trợ lazy basic attribute.
4. Thiết kế query truy cập LOB tách khỏi query trang danh sách.

### Tách entity không có nghĩa OneToOne LAZY được bảo đảm

Nếu dùng:

~~~java
@OneToOne(fetch = FetchType.LAZY)
private ProductContent content;
~~~

thì vẫn cần kiểm tra giới hạn lazy one-to-one đã trình bày. Đôi khi thiết kế query DTO cho content ID hoặc dùng truy vấn repository riêng là cách dễ kiểm soát hơn.

## 15. LAZY của @ManyToMany và @ElementCollection

### Many-to-many

Ví dụ Product có nhiều Tag:

~~~java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "product_tags",
    joinColumns = @JoinColumn(name = "product_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
~~~

`@ManyToMany` mặc định LAZY. Một query danh sách Product không cần tự tải mọi Tag. Khi duyệt `product.getTags()`, provider có thể load collection thông qua bảng liên kết.

Với nhiều Product và mỗi Product có nhiều Tag, nguy cơ N+1 vẫn tồn tại nếu code duyệt tags trong vòng lặp.

### ElementCollection

Ví dụ Product có tập từ khóa kiểu String:

~~~java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "product_keywords",
    joinColumns = @JoinColumn(name = "product_id")
)
@Column(name = "keyword")
private Set<String> keywords = new HashSet<>();
~~~

`@ElementCollection` cũng mặc định LAZY. Tuy nhiên, các phần tử của element collection là basic/embeddable values, **không phải entity có identity độc lập** như Tag.

### Không trộn fetch với cascade

Many-to-many có thể có cấu hình cascade riêng, nhưng cascade và fetch vẫn là hai trục độc lập. Tương tự, element collection được quản lý theo owner entity nhưng việc tải collection không đồng nghĩa việc persist/update trên owner đã xảy ra.

## 16. LAZY, EAGER và vòng đời persistence context

Khi `EntityManager` còn mở và entity đang managed, provider có thể lazy-load association theo cơ chế được hỗ trợ. Khi context đóng hoặc entity bị detach, dữ liệu chưa được nạp có thể không còn đường truy cập database.

~~~text
Transaction / Persistence Context đang hoạt động
    |
    +-- SELECT Order
    |      lines: chưa loaded
    |
    +-- order.getLines().iterator()
    |      -> provider có thể SELECT OrderLine
    |
    +-- DTO được tạo từ dữ liệu đã cần
    |
    v
close EntityManager / detach
    |
    +-- Truy cập field đã loaded: thường vẫn có dữ liệu trong object
    |
    +-- Truy cập field LAZY chưa loaded:
           không được bảo đảm có thể nạp thêm
~~~

### LAZY không đồng nghĩa đang có transaction

EntityManager mở nhưng không có transaction ghi active có thể vẫn có những hành vi đọc lazy tùy provider và cấu hình. **Đừng dựa vào hành vi đó làm hợp đồng nghiệp vụ**. Thiết kế đọc dữ liệu trong transaction/boundary rõ ràng rồi chuyển thành DTO là cách dễ kiểm soát hơn.

### Detached entity

~~~java
PurchaseOrder order = em.find(
    PurchaseOrder.class, id);

em.detach(order);
// Hoặc em.close(), hoặc em.clear().

order.getLines().size(); // Có thể thất bại nếu lines chưa nạp.
~~~

Việc `detach()` không tự động fetch tất cả LAZY associations. Detached chỉ nói entity không còn được persistence context quản lý.

## 17. LazyInitializationException: lỗi cụ thể của Hibernate

Một ví dụ quen thuộc:

~~~java
public PurchaseOrder loadOrder(Long id) {
    EntityManager em = emf.createEntityManager();
    try {
        return em.find(PurchaseOrder.class, id);
    } finally {
        em.close();
    }
}

// Bên ngoài service:
PurchaseOrder order = loadOrder(100L);
int lineCount = order.getLines().size();
~~~

Nếu collection chưa initialized và Hibernate không còn session phù hợp, có thể gặp:

~~~text
org.hibernate.LazyInitializationException:
failed to lazily initialize a collection ...
~~~

**`LazyInitializationException` là exception của Hibernate, không phải exception chuẩn áp dụng cho mọi JPA provider.** Provider khác có thể có exception/hành vi khác; một số trường hợp association đã loaded từ trước nên không lỗi.

### Không nên xử lý bằng cách đơn giản đổi mọi quan hệ sang EAGER

Đổi:

~~~java
@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
~~~

có thể che lỗi khi trả một Order, nhưng gây tải dữ liệu lớn ở mọi truy vấn khác, thậm chí N+1 hoặc phát sinh cartesian product khi nhiều collection được fetch.

Giải pháp bền vững là **xác định dữ liệu use case cần, fetch trước khi kết thúc boundary rồi trả DTO phù hợp**.

## 18. Tại sao EAGER không giải quyết được N+1?

Giả sử mapping:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Customer customer;
~~~

Truy vấn:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    PurchaseOrder.class)
  .setParameter("status", OrderStatus.PAID)
  .getResultList();
~~~

JPA chỉ yêu cầu Customer được eager fetched. Một provider có thể thực hiện:

~~~sql
SELECT o.* FROM purchase_orders o WHERE o.status = 'PAID';
SELECT c.* FROM customers c WHERE c.id = ?;
SELECT c.* FROM customers c WHERE c.id = ?;
-- ...
~~~

Với một query root cộng nhiều SELECT phụ, đây là dạng **N+1** về round trips.

### N+1 cũng xảy ra với LAZY

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

Nếu code:

~~~java
for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

thì mỗi Customer chưa loaded có thể kích hoạt SELECT phụ.

### Kết luận

| Mapping | Có thể phát sinh N+1? | Khi nào? |
| --- | --- | --- |
| To-one EAGER | Có | Provider chọn secondary SELECT để thỏa EAGER |
| To-one LAZY | Có | Code truy cập quan hệ của nhiều root entities |
| To-many LAZY | Có | Duyệt collection của nhiều root entities |
| To-many EAGER | Có hoặc còn tốn hơn | Provider nạp nhiều collection và graph khi query root |

**LAZY/EAGER không phải nút bật/tắt N+1**. Cần chọn fetch plan theo use case và xem SQL thật.

## 19. Tính số SQL: đừng chỉ nhìn chú thích

Ví dụ lấy 100 PurchaseOrder và hiển thị Customer name:

~~~java
List<PurchaseOrder> orders = findOrders();
for (PurchaseOrder order : orders) {
    render(order.getCustomer().getName());
}
~~~

Một kịch bản có thể là:

~~~text
1 SELECT danh sách Order
N SELECT lấy Customer khác nhau
--------------------------------
~1 + N SELECT
~~~

Nhưng **N không nhất thiết bằng 100**:

- Nhiều Order cùng trỏ một Customer nên identity map giúp reuse.
- Customer đã managed trước đó.
- Second-level cache có thể trả data khi được bật và hợp lệ.
- Provider có batch fetching hoặc JOIN.
- Query có thể dùng entity graph để nạp sẵn Customer.

Vì vậy, một báo cáo hiệu năng chỉ nói “LAZY gây N+1” mà không có thống kê SQL thực tế là chưa đủ. Hãy đo **số statement, số round trips, thời gian DB, kích thước result và số entity/collection được materialize**.

## 20. First-level cache không phải lazy fetch plan

Persistence context là identity map theo entity class và primary key. Trong cùng context:

~~~java
Customer a = em.find(Customer.class, 7L);
Customer b = em.find(Customer.class, 7L);

System.out.println(a == b); // true
~~~

Nhưng một danh sách PurchaseOrder:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
~~~

không có nghĩa JPA đã nạp mọi Customer/OrderLine chỉ vì Order đang managed. Identity map giúp **định danh và reuse những entity đã nạp**, không tự định nghĩa association nào sẽ được fetch.

### Second-level cache khác first-level cache

Second-level cache là cơ chế vượt phạm vi một persistence context, phụ thuộc provider/configuration. Nó có thể giảm SQL khi truy cập cùng Customer, nhưng không sửa được một thiết kế cần tải graph quá lớn hoặc query join nhân hàng.

### Query cache khác cache entity

Một số provider có query cache. Nó có thể giữ thông tin kết quả truy vấn theo chính sách riêng, không đồng nghĩa mọi LAZY collection đã initialized hoặc dữ liệu luôn mới nhất. Không dùng cache như giải pháp thay thế fetch plan có ngữ nghĩa rõ.

## 21. Mapping-level fetch và query-level fetch plan

Một mapping thường nên phản ánh **mặc định dùng chung**:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

Nhưng hai use case khác nhau cần:

~~~text
Danh sách đơn:
  Order.id, Order.placedAt, Order.status
  -> Không cần nạp Customer và lines.

Chi tiết một đơn:
  Order, Customer, lines, SKU của mỗi Product
  -> Cần lên kế hoạch fetch cho đường truy cập cụ thể.
~~~

Nếu chỉ dựa vào mapping LAZY, service chi tiết có thể phát nhiều query. Nếu đổi mapping sang EAGER để phục vụ chi tiết, service danh sách lại chịu chi phí không cần.

**Chiến lược khuyến nghị:** mapping defaults đủ tiết kiệm, còn query-level fetch plan biểu đạt use case đọc cụ thể.

Các công cụ:

- `JOIN FETCH` trong JPQL.
- Entity graph bằng `@NamedEntityGraph` hoặc `EntityManager.createEntityGraph()`.
- DTO constructor projection hoặc Criteria constructor projection.
- Batch fetching, subselect fetching theo extension của provider.
- Hai bước truy vấn: page IDs trước, nạp graph/DTO sau.

## 22. JPQL JOIN FETCH: yêu cầu nạp association cho query

Một query bình thường:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.id = :id
~~~

không nêu rõ cần Customer. Với `@ManyToOne(fetch=LAZY)`, Customer có thể chưa loaded.

Fetch join:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.id = :id
~~~

Java:

~~~java
PurchaseOrder order = em.createQuery(
        "SELECT o " +
        "FROM PurchaseOrder o " +
        "JOIN FETCH o.customer " +
        "WHERE o.id = :id",
        PurchaseOrder.class)
    .setParameter("id", id)
    .getSingleResult();

String customerName = order.getCustomer().getName();
~~~

Khi câu query trả Order, quan hệ Customer được yêu cầu fetch theo query dù mapping của Order.customer là LAZY.

### JOIN FETCH và JOIN thông thường khác nhau

~~~jpql
SELECT o
FROM PurchaseOrder o JOIN o.customer c
WHERE c.name LIKE :pattern
~~~

JOIN này giúp **lọc** theo Customer, nhưng không nhất thiết yêu cầu provider initialized Customer như fetch join.

Trong khi:

~~~jpql
SELECT o
FROM PurchaseOrder o JOIN FETCH o.customer
~~~

yêu cầu **fetch** Customer.

**Một JOIN để lọc không mặc nhiên thay thế JOIN FETCH.**

## 23. LEFT JOIN FETCH khi association có thể thiếu

Nếu Product.category nullable:

~~~jpql
SELECT p
FROM Product p
LEFT JOIN FETCH p.category
WHERE p.id = :id
~~~

thì Product không có Category vẫn có thể xuất hiện. Ngược lại:

~~~jpql
SELECT p
FROM Product p
JOIN FETCH p.category
WHERE p.id = :id
~~~

với inner join có thể loại Product không có Category.

### Chọn JOIN theo tính optional của quan hệ

| Tình huống | Ý nghĩa thường muốn |
| --- | --- |
| Quan hệ bắt buộc, FK không nullable | `JOIN FETCH` có thể phù hợp |
| Quan hệ có thể null, muốn giữ root | `LEFT JOIN FETCH` |
| Muốn lọc root chỉ có association | INNER JOIN thể hiện điều kiện đó |
| Muốn lấy mọi root kể cả không có association | LEFT JOIN |

Không coi `LEFT JOIN FETCH` mặc định là tối ưu cho mọi trường hợp; query plan và index vẫn phụ thuộc DBMS.

## 24. Fetch join collection: một Order có nhiều OrderLine

Khi cần chi tiết một Order cùng lines:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
~~~

Ý nghĩa SQL có thể gần như:

~~~text
Order#100 + Line#1
Order#100 + Line#2
Order#100 + Line#3
~~~

Một Order bị lặp ở **nhiều hàng JDBC** vì quan hệ một–nhiều, rồi provider phải materialize một Order root với collection lines.

### Vì sao DISTINCT thường xuất hiện?

Với query trả entity root, `DISTINCT` biểu diễn mong muốn tránh root trùng trong kết quả. Cách provider xử lý SQL DISTINCT và khử trùng entity root thay đổi theo provider/phiên bản. Hibernate ở một số phiên bản có cơ chế khử trùng kết quả fetch join riêng, nhưng **không nên dựa vào behavior vendor làm một quy tắc JPQL chung**.

### Fetch join collection không miễn phí

Một Order có 500 OrderLine sẽ tạo 500 hàng join; các cột Order lặp lại ở mỗi hàng SQL. Chi phí dữ liệu truyền và materialize có thể lớn hơn việc query hai lần (Order riêng, Lines riêng) tùy tình huống.

### Không dùng fetch join collection vô tội vạ trong danh sách

Nếu trang có 100 Order, mỗi Order 20 Lines:

~~~text
100 Orders × 20 Lines = 2.000 joined rows
~~~

Với nhiều collection, số hàng có thể tăng theo **tích số lượng phần tử**, gây cartesian multiplication.

## 25. Fetch join và pagination là một bẫy phổ biến

Giả sử:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "ORDER BY o.id",
        PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Người viết mong 20 Order với toàn bộ Lines, nhưng phép JOIN collection làm số **hàng SQL** lớn hơn số Order root. Đặt LIMIT/OFFSET trực tiếp trên các hàng join có thể cắt mất collection hoặc làm pagination root sai.

Provider có thể:

- Áp pagination trong memory sau khi tải nhiều hàng.
- Tạo SQL phức tạp để bảo vệ root pagination trong một số trường hợp.
- Cảnh báo hoặc không cho phép mô hình này.

Không có quy tắc portable rằng câu trên luôn lấy hiệu quả đúng 20 root entities với collection hoàn chỉnh.

### Phương án hai bước

**Bước 1: lấy ID của Order trên một trang.**

~~~java
List<Long> ids = em.createQuery(
        "SELECT o.id FROM PurchaseOrder o " +
        "WHERE o.status = :status " +
        "ORDER BY o.placedAt DESC, o.id DESC",
        Long.class)
    .setParameter("status", OrderStatus.PAID)
    .setFirstResult(page * size)
    .setMaxResults(size)
    .getResultList();
~~~

**Bước 2: nạp các Order cho tập ID với fetch plan phù hợp.**

~~~java
if (ids.isEmpty()) {
    return List.of();
}

List<PurchaseOrder> result = em.createQuery(
        "SELECT DISTINCT o " +
        "FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "WHERE o.id IN :ids",
        PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
~~~

SQL bước hai không nhất thiết giữ thứ tự `ids`; cần sắp lại theo thứ tự ID của bước một nếu UI yêu cầu.

### Lưu ý về consistency

Hai query riêng có thể thấy trạng thái dữ liệu khác nhau khi transaction khác cập nhật, tùy isolation/snapshot. Với báo cáo cần snapshot nhất quán, transaction boundary và mức cô lập cần được xác định thêm.

## 26. Entity graph: điều chỉnh fetch mà không đổi mapping

Entity graph cho phép khai báo những association cần fetch cho một truy vấn hoặc một lần `find()`.

Ví dụ một use case muốn PurchaseOrder cùng Customer:

~~~java
import jakarta.persistence.EntityGraph;
import java.util.Map;

EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    id,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Điểm mạnh:

- Không phải thay `fetch=LAZY` trên mapping chung.
- Có thể định nghĩa các graph khác nhau cho danh sách/chi tiết/biên tập.
- Provider sử dụng graph để xây fetch plan phù hợp.

**Graph không cam kết một câu SQL duy nhất**. Provider có thể nạp những attribute bằng JOIN hoặc secondary SELECT, và có thể fetch thêm dữ liệu theo ngữ nghĩa/spec/provider cho phép.

### Hai chuẩn hint

| Hint | Ý nghĩa dự kiến |
| --- | --- |
| `jakarta.persistence.fetchgraph` | Những attribute trong graph được coi là EAGER; attribute không được liệt kê được coi là LAZY theo graph semantics |
| `jakarta.persistence.loadgraph` | Attribute trong graph được coi là EAGER; attribute không nêu tiếp tục theo default của mapping |

Ở JPA 2.x namespace cũ, tên hint thường bắt đầu bằng `javax.persistence.` thay vì `jakarta.persistence.`.

### Một lưu ý đặc biệt

Ngay cả với fetch graph, provider được phép fetch thêm state ngoài graph trong những trường hợp phù hợp. Vì vậy **fetchgraph không phải một lệnh projection “chỉ SELECT chính xác các cột này”**; nếu chỉ cần chính xác một số field, dùng DTO projection.

## 27. Entity graph có subgraph

Một màn hình chi tiết đơn cần:

~~~text
PurchaseOrder
  ├── Customer
  └── OrderLine collection
        └── Product
~~~

Có thể định nghĩa graph:

~~~java
import jakarta.persistence.EntityGraph;
import jakarta.persistence.Subgraph;

EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");
Subgraph<OrderLine> lineGraph =
    graph.addSubgraph("lines");
lineGraph.addAttributeNodes("product");

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    id,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

Ở đây:

- Customer được yêu cầu tải.
- Collection lines được yêu cầu tải.
- Mỗi OrderLine yêu cầu Product.
- Product.category không được chỉ định trong graph; nó không tự trở thành dữ liệu cần thiết của màn hình.

### Có cần mọi màn hình chi tiết dùng graph sâu như vậy?

Không. Nếu màn hình không cần toàn bộ Product entity mà chỉ cần SKU, query DTO theo các association có thể rẻ hơn. Entity graph sâu có thể tạo nhiều JOIN/SELECT và nhiều managed entities.

### Subgraph không thay mapping vĩnh viễn

Một query khác chỉ nạp Order ID và status vẫn có thể sử dụng mapping defaults LAZY. Entity graph chỉ biểu đạt nhu cầu tải trong **operation cụ thể**.

## 28. @NamedEntityGraph: khai báo kế hoạch tải tái sử dụng

Thay vì tạo graph động mọi lần, có thể đặt metadata trên entity:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = {
        @NamedAttributeNode("customer")
    }
)
@Entity
public class PurchaseOrder {
    // Các trường mapping đã định nghĩa trước đó.
}
~~~

Đây là phần annotation bổ sung vào PurchaseOrder của mục 7, **không phải tạo lại class thứ hai** trong source project.

Lấy graph bằng tên:

~~~java
EntityGraph<?> graph = em.getEntityGraph(
    "PurchaseOrder.withCustomer");

List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        PurchaseOrder.class)
    .setParameter("status", OrderStatus.PAID)
    .setHint("jakarta.persistence.loadgraph", graph)
    .getResultList();
~~~

### Vì sao chọn loadgraph trong ví dụ?

`loadgraph` bổ sung những attribute trong graph vào kế hoạch tải nhưng giữ các mapping defaults cho thuộc tính không liệt kê. Nếu entity vẫn có nhiều EAGER attributes mặc định, chúng có thể tiếp tục được nạp.

Với `fetchgraph`, các thuộc tính không liệt kê được xem là LAZY theo graph semantics nhưng vẫn có sự linh hoạt của provider. Vì vậy cần thử nghiệm và không coi graph là bảo đảm tuyệt đối “xóa EAGER khỏi SQL”.

### Spring Data JPA @EntityGraph

Nếu dùng Spring Data JPA, repository có annotation `org.springframework.data.jpa.repository.EntityGraph`:

~~~java
@EntityGraph(attributePaths = {"customer"})
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Đây là **extension Spring Data**, không phải annotation `jakarta.persistence.NamedEntityGraph`. Với ứng dụng JPA thuần, dùng graph và query hints theo API chuẩn.

## 29. DTO projection: không nạp entity khi chỉ cần vài field

Màn hình danh sách:

~~~text
Order ID | placedAt | status | Customer name
~~~

Không cần managed PurchaseOrder và Customer đầy đủ nếu chỉ đọc.

DTO:

~~~java
package com.example.shop.dto;

import com.example.shop.OrderStatus;
import java.time.Instant;

public record OrderListRow(
        Long id,
        Instant placedAt,
        OrderStatus status,
        String customerName) {
}
~~~

JPQL:

~~~java
List<OrderListRow> rows = em.createQuery(
        "SELECT NEW com.example.shop.dto.OrderListRow(" +
        "o.id, o.placedAt, o.status, c.name) " +
        "FROM PurchaseOrder o " +
        "JOIN o.customer c " +
        "WHERE o.status = :status " +
        "ORDER BY o.placedAt DESC, o.id DESC",
        OrderListRow.class)
    .setParameter("status", OrderStatus.PAID)
    .setMaxResults(50)
    .getResultList();
~~~

### Vì sao cách này có lợi?

- Chỉ trả các scalar cần cho màn hình.
- Không phụ thuộc lazy initialization ở tầng JSON serializer.
- Không tự nạp OrderLine collection.
- Dữ liệu trả về là DTO immutable, không bị dirty checking ngoài ý định.
- Có thể phân trang trực tiếp theo root Order rows nếu query không JOIN collection nhiều giá trị.

### DTO không phải entity

`OrderListRow` không được EntityManager quản lý. Thay đổi dữ liệu DTO không tạo SQL UPDATE tự động.

### DTO không mặc nhiên ít SQL trong mọi trường hợp

Một DTO query có nhiều JOIN/subquery phức tạp vẫn có thể chậm. Nhưng khi chỉ cần vài cột, nó giúp tránh nạp entity graph không cần thiết và làm contract đọc dữ liệu rõ hơn.

## 30. Một service chi tiết đơn hàng không lệ thuộc lazy sau khi trả về

Thay vì trả entity tới controller và hy vọng serializer tự nạp dữ liệu:

~~~java
public PurchaseOrder getDetails(Long id) {
    return em.find(PurchaseOrder.class, id);
}
~~~

hãy xác định dữ liệu chi tiết rồi trả DTO.

Ví dụ:

~~~java
package com.example.shop.dto;

import java.time.Instant;

public record OrderHeader(
        Long orderId,
        String customerName,
        Instant placedAt) {
}
~~~

~~~java
package com.example.shop.dto;

public record OrderLineSummary(
        Long lineId,
        String productSku,
        int quantity) {
}
~~~

~~~java
package com.example.shop.dto;

import java.util.List;

public record OrderDetail(
        OrderHeader header,
        List<OrderLineSummary> lines) {
}
~~~

Service:

~~~java
import com.example.shop.dto.OrderHeader;
import com.example.shop.dto.OrderLineSummary;
import com.example.shop.dto.OrderDetail;
import jakarta.persistence.EntityManager;
import java.util.List;

public OrderDetail getOrderDetail(
        EntityManager em, Long orderId) {

    OrderHeader header = em.createQuery(
            "SELECT NEW com.example.shop.dto.OrderHeader(" +
            "o.id, c.name, o.placedAt) " +
            "FROM PurchaseOrder o JOIN o.customer c " +
            "WHERE o.id = :id",
            OrderHeader.class)
        .setParameter("id", orderId)
        .getSingleResult();

    List<OrderLineSummary> lines = em.createQuery(
            "SELECT NEW com.example.shop.dto.OrderLineSummary(" +
            "l.id, p.sku, l.quantity) " +
            "FROM OrderLine l JOIN l.product p " +
            "WHERE l.order.id = :id " +
            "ORDER BY l.id ASC",
            OrderLineSummary.class)
        .setParameter("id", orderId)
        .getResultList();

    return new OrderDetail(header, List.copyOf(lines));
}
~~~

### Một lợi ích kiến trúc

Màn hình chi tiết nhận một `OrderDetail` gồm DTO đã dựng trong lúc query chạy. Không có getter của entity lazy cần được gọi sau khi service return.

### Nhược điểm và trade-off

- Hai câu query thay vì một.
- Nếu cần snapshot thống nhất giữa header và lines, transaction isolation phải bảo đảm điều đó.
- Dữ liệu có thể thay đổi giữa hai câu SELECT dưới READ COMMITTED.
- Với rất nhiều lines, service vẫn cần pagination/streaming phù hợp.

Chọn một truy vấn JOIN FETCH hay hai query DTO là quyết định dựa trên use case, cardinality và consistency, không có một lựa chọn đúng cho mọi trường hợp.

## 31. Tại sao không trả entity trực tiếp ra JSON?

Ví dụ controller trả:

~~~java
return ResponseEntity.ok(orderEntity);
~~~

Với association lazy và bidirectional:

~~~text
Order -> Customer -> orders -> Customer -> ...
Order -> lines -> Order -> ...
~~~

Serializer có thể:

- Gọi `getCustomer()` và `getLines()` ngoài transaction.
- Gây lazy initialization error khi context đã đóng.
- Kích hoạt hàng loạt SELECT ngoài dự kiến nếu context vẫn mở.
- Đi vòng quan hệ hai chiều gây recursion/stack overflow.
- Vô tình lộ những field không nên công khai.

### Cách xử lý đúng

Thiết kế API DTO:

~~~text
Persistence entity -> service fetch/projection -> API DTO -> JSON
~~~

DTO chỉ chứa các thông tin được định nghĩa trong contract trả về; không có proxy/lazy collection bị kéo theo.

### @JsonIgnore không thay fetch plan

Các annotation serializer như `@JsonIgnore` có thể tránh đọc một field khi serialize, nhưng chúng **không thay đổi mapping EAGER**, không tự tối ưu JOIN và không giải quyết tất cả truy vấn N+1 trong service. Đây là công cụ trình bày JSON, không phải công cụ tải JPA.

## 32. Open Session in View (OSIV): vì sao không phải giải pháp chung?

Một số ứng dụng web để persistence context/session mở tới cuối quá trình render response. Điều này có thể cho phép serializer truy cập lazy association sau khi service đã return.

~~~text
HTTP request
   |
   v
Service kết thúc transaction
   |
   v
JSON serialization truy cập LAZY
   |
   +-- Có thể phát SELECT lúc render response
   |
   v
Close EntityManager cuối request
~~~

OSIV có thể làm lỗi lazy initialization biến mất trong một số tình huống, nhưng có nhược điểm:

- SQL xảy ra ở tầng view/serializer, khó quan sát và kiểm soát.
- Có thể phát sinh N+1 ngoài thời điểm service thực hiện truy vấn.
- Các truy vấn phát sau transaction chính có thể đọc snapshot khác.
- Ranh giới unit of work và trách nhiệm layer bị mờ.
- Tăng thời gian sử dụng persistence context/connection tùy cấu hình.

**Không coi OSIV là lý do để bỏ qua thiết kế fetch plan.** Với API và nghiệp vụ rõ ràng, DTO/projection trong transaction boundary thường dễ kiểm soát hơn.

## 33. EAGER trên collection: vì sao phải thận trọng?

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "order",
    fetch = FetchType.EAGER
)
private List<OrderLine> lines;
~~~

Với một Order duy nhất và chỉ vài OrderLine, EAGER có thể đơn giản. Nhưng với trang danh sách hàng trăm Order, hậu quả có thể là:

- Tải tất cả lines mà UI chưa dùng.
- SQL SELECT phụ trên mỗi Order.
- JOIN nhân số hàng theo kích thước collection.
- Tăng thời gian hydration, bộ nhớ, GC.
- Phức tạp khi fetch nhiều collection đồng thời.
- Khó “gỡ” fetch ở query cụ thể vì mapping EAGER là yêu cầu tải.

### Multiple collection EAGER

Giả sử một Order có:

~~~text
10 lines
8 adjustments
5 notes
~~~

JOIN fetch cả ba có thể tạo:

~~~text
10 × 8 × 5 = 400 JDBC rows
~~~

cho một Order nếu SQL tạo tích các collection. Con số là ví dụ cardinality, không khẳng định mọi provider luôn JOIN cả ba collection; nhưng rủi ro cartesian product là thực tế.

### Hibernate MultipleBagFetchException

Hibernate có giới hạn khi đồng thời fetch nhiều bag-valued collections trong một số cấu hình/truy vấn, có thể ném `MultipleBagFetchException`. Đây là **exception riêng Hibernate**, không phải thuật ngữ portable của JPA. Không đổi bừa List sang Set chỉ để né exception nếu semantics collection trong domain không phải tập hợp.

### Hướng xử lý

Thường giữ to-many LAZY mặc định, rồi nạp có mục đích:

- Một association bằng JOIN FETCH khi số lượng hợp lý.
- Query thứ hai cho association lớn.
- Entity graph có chọn lọc.
- Batch/subselect fetching theo provider.
- DTO projection cho màn hình chỉ đọc.

## 34. Batch fetching: giảm N+1 mà không đổi LAZY thành EAGER

Giả sử đang giữ 100 Order managed và cần Customer name. Thay vì SELECT từng Customer, một provider có thể nạp nhiều Customer IDs trong một batch:

~~~text
SELECT orders ...

SELECT customers WHERE id IN (1,2,...,32)
SELECT customers WHERE id IN (33,...,64)
SELECT customers WHERE id IN (65,...,96)
SELECT customers WHERE id IN (97,...)
~~~

Đây là chiến lược **batch fetching**, khác với việc đổi mapping sang EAGER.

### Hibernate-specific: @BatchSize

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 32)
private Customer customer;
~~~

Hoặc một số cấu hình Hibernate có property `hibernate.default_batch_fetch_size`. Những cơ chế này **không thuộc API chuẩn JPA** và mức hỗ trợ/cú pháp có thể thay đổi theo Hibernate version.

### Khi nào batch fetching hữu ích?

- Có nhiều lazy associations cùng loại được truy cập trong một persistence context.
- JOIN FETCH sẽ gây quá nhiều hàng do collection fan-out.
- Muốn giữ mapping LAZY nhưng tối ưu pattern truy cập hàng loạt.

### Không coi batch fetching luôn nhanh nhất

Batch size quá lớn có thể tạo IN-list lớn, vượt giới hạn bind của DBMS hoặc làm SQL plan xấu. Batch size nhỏ lại phát nhiều round trips. Hãy đo hiệu năng trên dữ liệu đại diện.

## 35. Subselect fetching và các chiến lược riêng của provider

Một số provider, điển hình Hibernate, có thể fetch các collection bằng subselect dựa trên tập entity owners vừa được truy vấn.

Sơ đồ:

~~~text
SELECT Orders WHERE status='PAID'
   |
   v
N Order được quản lý
   |
   v
Khi cần lines:
SELECT Lines WHERE order_id IN
  (kết quả/subquery liên quan Orders đã tải)
~~~

Hibernate có các cấu hình như `@Fetch(FetchMode.SUBSELECT)`, nhưng đây là extension riêng. Không viết `@Fetch` rồi tuyên bố tất cả JPA providers hỗ trợ.

### So sánh chiến lược

| Chiến lược | Đặc điểm | Rủi ro thường gặp |
| --- | --- | --- |
| JOIN fetch | Nạp cùng một truy vấn theo association | Nhân hàng, pagination collections |
| SELECT phụ | Nạp riêng khi cần | N+1 nếu gọi nhiều lần |
| Batch fetch | Gom nhiều IDs vào query | Batch size và IN-list |
| Subselect fetch | Nạp collection cho tập owners theo subquery | Query lớn, phụ thuộc provider |
| DTO projection | Chỉ nạp field cần đọc | Không có managed entity/lifecycle |

Mỗi cách giải một vấn đề khác nhau. **FetchType.LAZY không chọn một chiến lược cố định** trong bảng này.

## 36. @EntityGraph không phải là SELECT projection

Một nhầm lẫn là nghĩ:

~~~java
graph.addAttributeNodes("customer");
~~~

có nghĩa SQL sẽ chỉ trả đúng các cột của PurchaseOrder và Customer. Nhưng nếu query trả **PurchaseOrder entity**, JPA vẫn cần persistent state cần thiết để materialize entity, và provider có thể nạp thêm thuộc tính theo mapping/implementation.

### Entity graph

Trả entity:

~~~java
PurchaseOrder managedOrder = em.find(
    PurchaseOrder.class, id,
    Map.of("jakarta.persistence.fetchgraph", graph));
~~~

### DTO projection

Trả scalar vào DTO:

~~~jpql
SELECT NEW com.example.shop.dto.OrderListRow(
    o.id, o.placedAt, o.status, c.name
)
FROM PurchaseOrder o JOIN o.customer c
~~~

| Câu hỏi | Entity graph | DTO projection |
| --- | --- | --- |
| Muốn managed entity? | Có | Không |
| Cần nạp association theo use case? | Có | Chỉ những field biểu diễn trong query |
| Dirty checking trên entity? | Có, khi entity managed | Không |
| Kiểm soát cột projection? | Không phải mục tiêu chính | Có |
| Phù hợp API danh sách chỉ đọc? | Có thể | Thường rất phù hợp |
| Phù hợp thao tác tiếp trên entity? | Phù hợp | Cần nạp entity riêng |

Đừng chọn entity graph nếu mục tiêu thực sự là giảm SELECT xuống một vài scalar và tuyệt đối không cần managed entity.

## 37. Query trả entity đã managed và vấn đề freshness

Trong cùng persistence context:

~~~java
PurchaseOrder first = em.find(
    PurchaseOrder.class, id);

PurchaseOrder again = em.createQuery(
        "SELECT o FROM PurchaseOrder o WHERE o.id=:id",
        PurchaseOrder.class)
    .setParameter("id", id)
    .getSingleResult();

System.out.println(first == again); // true
~~~

EntityManager phải duy trì **một managed instance cho cùng entity identity** trong context.

Nhưng điều này không có nghĩa:

- Query thứ hai tự refresh mọi field từ DB.
- Mọi association LAZY tự initialized.
- Mapping EAGER giúp transaction thấy write chưa commit của transaction khác.

### Fetch timing khác freshness

`LAZY/EAGER` mô tả **khi nào cần nạp dữ liệu association**. **Freshness** phụ thuộc vào context cache, transaction snapshot/isolation, explicit `refresh()` và cơ chế cache ngoài.

Ví dụ Customer đã managed với tên cũ có thể được reuse trong một query mới, dù SQL của transaction khác đã cập nhật tên. Đừng giải quyết vấn đề stale data bằng cách chỉ đổi LAZY sang EAGER.

## 38. fetch type, transaction và isolation là ba trục độc lập

Giả sử:

~~~text
Transaction A:
  LOAD Order
  Customer LAZY chưa nạp

Transaction B:
  UPDATE Customer.name
  COMMIT

Transaction A:
  order.getCustomer().getName()
~~~

Tên được đọc theo giá trị nào?

Điều đó còn phụ thuộc:

- Transaction A dùng READ COMMITTED hay snapshot/repeatable-read?
- Customer đã ở persistence context/cache của A chưa?
- Database nào và cơ chế MVCC/locking ra sao?
- Provider có lazy-load bằng query riêng ở thời điểm truy cập không?

**LAZY không cam kết dữ liệu luôn mới hơn EAGER**, cũng như EAGER không cam kết snapshot nhất quán hơn LAZY.

### Flush mode không phải fetch mode

`FlushModeType.AUTO` hoặc `COMMIT` liên quan đến **đồng bộ thay đổi JPA ra database** trước query/commit. `FetchType.EAGER/LAZY` liên quan đến **đọc/nạp association và attribute**.

Không nhầm:

~~~text
Fetch = đọc dữ liệu gì và lúc nào.
Flush = đồng bộ pending changes của context ra DB lúc nào.
Commit = xác nhận transaction.
Isolation = transaction khác có thể nhìn thấy gì.
~~~

## 39. EAGER/LAZY và cascade khác nhau hoàn toàn

Một mapping:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    fetch = FetchType.LAZY,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

khai báo ba nhóm hành vi:

| Tùy chọn | Công dụng |
| --- | --- |
| `cascade = ALL` | Lan truyền các thao tác lifecycle được định nghĩa |
| `fetch = LAZY` | Gợi ý nạp collection theo nhu cầu |
| `orphanRemoval = true` | Loại bỏ entity con theo ngữ nghĩa orphan của association |

**Không có quan hệ suy diễn trực tiếp**:

- Cascade ALL **không có nghĩa** fetch EAGER.
- LAZY **không ngăn** cascade remove khi ứng dụng xóa root, theo quy tắc JPA.
- Orphan removal **không có nghĩa** collection phải EAGER ở mọi SELECT.

Provider có thể phải nạp/thực thi SQL thêm khi cascade/remove, nhưng đó là chi phí thực hiện thao tác lifecycle, không phải một lý do để đổi mapping fetch globally.

## 40. EAGER/LAZY và optional/nullable không giống nhau

Hai mapping:

~~~java
@ManyToOne(
    fetch = FetchType.LAZY,
    optional = false
)
@JoinColumn(nullable = false)
private Customer customer;
~~~

và:

~~~java
@ManyToOne(
    fetch = FetchType.LAZY,
    optional = true
)
@JoinColumn(nullable = true)
private Customer customer;
~~~

khác nhau về **tính bắt buộc của association**, không phải chính sách fetch. Cả hai đều yêu cầu LAZY.

### nullable association có thể trả null

Với:

~~~java
Customer customer = order.getCustomer();
~~~

Nếu FK thực sự NULL và mapping optional, Java có thể trả null mà không cần một entity instance. Nếu FK không NULL, provider có thể trả proxy/reference rồi chỉ nạp full Customer khi truy cập cần.

### Trường hợp @OneToOne inverse

Khi FK nằm ở bảng bên kia, provider có thể cần SQL để biết “association tồn tại hay không”; do đó `optional = true` kết hợp `fetch = LAZY` trên inverse one-to-one có thể khó tối ưu mà không có enhancement.

Không diễn giải `optional=false` là “bắt buộc EAGER” hay `optional=true` là “bắt buộc LAZY”.

## 41. N+1 có thể bị kích hoạt bởi toString, equals và logging

Một đoạn tưởng vô hại:

~~~java
logger.info("Order = {}", order);
~~~

nếu `PurchaseOrder.toString()` truy cập:

~~~java
customer.getName()
lines.size()
~~~

thì việc ghi log có thể kích hoạt SELECT hoặc lỗi lazy initialization khi context đã đóng.

Tương tự:

- Lombok `@Data` hoặc auto-generated `toString` có thể kéo toàn bộ association.
- `equals()/hashCode()` duyệt collection hoặc association có thể phát SQL, gây recursion hoặc hành vi khó đoán.
- Debugger/IDE inspection đôi khi hiển thị property bằng cách gọi getter và vô tình initialize lazy state.

### Một toString an toàn hơn

~~~java
@Override
public String toString() {
    return "PurchaseOrder{id=" + id +
           ", status=" + status + "}";
}
~~~

Không đưa Customer, lines, Product, Category vào toString mặc định chỉ để tiện debug.

### equals/hashCode cần chiến lược entity identity

Chiến lược equals/hashCode phụ thuộc khóa chính được sinh ra, khóa nghiệp vụ, proxy và lifecycle. Dù chọn chiến lược nào, **không dùng toàn bộ lazy object graph** làm dữ liệu so sánh mặc định.

## 42. Sử dụng PersistenceUnitUtil.isLoaded()

JPA cung cấp API kiểm tra trạng thái loaded:

~~~java
import jakarta.persistence.PersistenceUnitUtil;

PersistenceUnitUtil util =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil();

PurchaseOrder order =
    em.find(PurchaseOrder.class, id);

boolean linesLoaded =
    util.isLoaded(order, "lines");

boolean entityLoaded =
    util.isLoaded(order);
~~~

`PersistenceUnitUtil.isLoaded(entity, attributeName)` cho biết trạng thái load theo contract của JPA provider. Đây là cách portable hơn khi không muốn phụ thuộc trực tiếp vào API riêng Hibernate.

### Không nên dùng nó như một lời hứa LAZY luôn false lúc đầu

Ngay cả khi mapping LAZY:

~~~java
@OneToMany(fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

provider có thể nạp lines sẵn do fetch join, graph, cache hoặc strategy đặc thù. Vì vậy test không nên mặc định mọi LAZY association luôn `isLoaded == false` ngay sau `find()` trên mọi provider.

### Hibernate-specific API

Hibernate còn có các API như:

~~~java
org.hibernate.Hibernate.isInitialized(order.getLines());
~~~

Đây là extension Hibernate, không phải API chuẩn JPA. Nếu dự án hướng portability, ưu tiên JPA API và quan sát SQL.

## 43. Chẩn đoán N+1 qua SQL thực tế

Một quy trình:

1. Bật logging SQL trong môi trường phát triển/test phù hợp.
2. Chuẩn bị fixture có đủ nhiều Order, Customer, lines.
3. Gọi đúng use case thay vì chỉ gọi repository method mà không duyệt kết quả.
4. Đếm số SELECT và round trips.
5. Quan sát JOIN, IN-list, query plan, amount of data.
6. Chạy lại với JOIN FETCH, entity graph hoặc DTO.
7. So sánh thời gian, bộ nhớ và số hàng trả về.

### Vì sao phải chạy đúng use case?

Với LAZY collection, `getResultList()` có thể chỉ phát một SELECT, nhưng serialization sau đó mới phát N SELECT. Một benchmark dừng ngay sau query sẽ **không đo được chi phí thật** của màn hình.

### Đo bằng statistics của provider

Hibernate có statistics như `SessionFactory.getStatistics()` trong các phiên bản/cấu hình tương ứng, có thể đếm prepared statements và entity/collection fetches. Đây là API riêng provider; muốn dùng trong test cần bật statistics và reset/isolated measurement phù hợp.

### Không chạy SQL logging nhạy cảm bừa bãi trên production

Bind parameters có thể chứa dữ liệu khách hàng, token hoặc business identifiers. Ghi log chỉ ở môi trường phù hợp hoặc mask dữ liệu theo chính sách bảo mật.

## 44. Kiểm thử fetch plan trên database thật

Một integration test có thể kiểm tra những đặc tính đã được use case yêu cầu:

~~~java
EntityManager em = emf.createEntityManager();
try {
    PurchaseOrder order = em.createQuery(
            "SELECT o FROM PurchaseOrder o " +
            "JOIN FETCH o.customer " +
            "WHERE o.id = :id",
            PurchaseOrder.class)
        .setParameter("id", orderId)
        .getSingleResult();

    PersistenceUnitUtil util =
        emf.getPersistenceUnitUtil();

    if (!util.isLoaded(order, "customer")) {
        throw new AssertionError(
            "Customer phải được fetch");
    }
} finally {
    em.close();
}
~~~

Đây là phần minh họa kiểm tra **kết quả fetch đã yêu cầu**, không phải đầy đủ một test JUnit. Test thực tế còn cần transaction/fixture phù hợp với DBMS, provider và chính sách persistence unit.

### Điều nên kiểm tra

- Query danh sách không vô ý kéo hàng nghìn lines.
- Query chi tiết trả đủ data cần dùng trước khi đóng context.
- Độ lớn SQL result và số SELECT không vượt ngưỡng regression chấp nhận.
- Không có N+1 khi serialize DTO hoặc render view.
- Pagination theo Order root đúng số phần tử, không bị JOIN collection cắt trang.
- Associations nullable xử lý đúng.
- Không phụ thuộc OSIV để đọc dữ liệu sau service.

### Điều không nên khẳng định tuyệt đối

Không viết một test portable rằng “mapping LAZY bắt buộc đúng 0 SELECT phụ khi load root”, vì LAZY là hint. Muốn giới hạn cụ thể số SQL, test phải gắn với **provider/cấu hình cụ thể** và được xem là kiểm thử hiệu năng/SQL plan chứ không phải yêu cầu chung của đặc tả JPA.

## 45. Các lỗi thường gặp khi phân biệt EAGER và LAZY

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Tải Order khiến Customer được load ngay | `@ManyToOne` default EAGER | Khai báo LAZY nếu phù hợp, đo provider |
| Tải User khiến Profile được load ngay | `@OneToOne` default EAGER | Xem LAZY/enhancement/to-one inverse |
| Lấy 100 Orders phát rất nhiều SELECT | EAGER secondary selects hoặc LAZY traversal | Query fetch plan/DTO/batch |
| LAZY nhưng getter gây SELECT | Truy cập attribute chưa loaded | Fetch có chủ đích trong boundary |
| LazyInitializationException | Hibernate context đã đóng trước lúc truy cập | Nạp dữ liệu/DTO trước khi trả |
| Đổi collection sang EAGER làm query chậm | To-many graph quá lớn | Giữ LAZY, fetch theo use case |
| JOIN FETCH nhưng một Product không có Category biến mất | Dùng INNER JOIN cho nullable association | Dùng LEFT JOIN FETCH |
| Có JOIN c.customer nhưng vẫn SELECT Customer | JOIN lọc không nhất thiết là fetch join | Dùng JOIN FETCH/graph/DTO |
| Graph có Customer nhưng SQL vẫn nhiều statement | Graph không bảo đảm một SQL | Đo SQL strategy của provider |
| fetchgraph vẫn nạp thêm dữ liệu | Provider được fetch thêm theo spec | DTO nếu cần projection chính xác |
| @Basic(fetch=LAZY) vẫn lấy cột LOB | Provider thiếu hỗ trợ/enhancement | DTO/split entity hoặc enhancement |
| To-one LAZY vẫn query sớm | Proxy/enhancement/inverse one-to-one | Xem FK, optional, provider behavior |
| getLines().size() gây load hàng trăm dòng | Collection lazy wrapper không extra-lazy | COUNT query riêng nếu chỉ cần số lượng |
| Query page + JOIN FETCH lines trả sai trang | Collection JOIN nhân rows | Page root IDs trước, fetch sau |
| Hai collections fetch đồng thời tạo hàng nhân | Cartesian product/multiple bag | Tách query/graph hoặc batch |
| Object đã managed nhưng field đọc cũ | Identity map không tự refresh | Refresh/isolation/context mới |
| Clear rồi sửa entity không ghi DB | Entity detached sau clear | Nạp managed entity mới |
| JSON serializer phát SELECT ngoài service | Serializer duyệt association | Dùng API DTO, đóng rõ boundary |
| toString của entity làm query bất ngờ | toString chạm LAZY fields | Chỉ log ID/basic fields |
| Cascade ALL được hiểu là EAGER | Lẫn lifecycle với fetch | Tách hai khái niệm |
| @JsonIgnore tưởng sẽ giảm SQL EAGER | Serializer annotation không đổi fetch | Thiết kế fetch plan của JPA |
| OSIV che mất vấn đề N+1 | Truy vấn xảy ra ở tầng view | DTO/query fetch trong service |
| Kiểm tra isLoaded luôn false khi LAZY | LAZY chỉ là hint; graph/cache có thể load | Test theo contract, đo SQL |
| Thuộc tính sort/filter gây JOIN thừa | Criteria builder tạo association joins | Chỉ JOIN khi cần, xem SQL |
| Fetch quá nhiều khi báo cáo COUNT | Nạp entity thay vì aggregate | Query COUNT/SUM scalar |

## 46. Một phương pháp chọn mapping cho dự án mới

Khi thiết kế entity mới, có thể theo các bước:

1. **Xác định cardinality:** to-one hay to-many; nullable hay bắt buộc.
2. **Nhận biết default JPA:** to-one EAGER, to-many LAZY, Basic EAGER.
3. **Đánh giá use cases:** bao nhiêu màn hình dùng association? Mỗi lần dùng có cần toàn bộ đối tượng không?
4. **Cân nhắc khai báo LAZY trên to-one:** thường phù hợp với domain nhiều association, nhưng phải kiểm tra provider.
5. **Giữ collections LAZY theo mặc định**, trừ khi có lý do rõ và nhỏ về cardinality.
6. **Tách fetch plan theo truy vấn:** list, detail, report, export có nhu cầu khác nhau.
7. **Dùng DTO cho read-only endpoints** khi chỉ cần một vài trường.
8. **Kiểm soát transaction boundary:** tạo DTO khi dữ liệu còn truy cập được, không đẩy lazy entity tới serializer.
9. **Đo N+1 và row multiplication:** query counts chỉ là một thước đo; xem cả amount of data và latency.
10. **Chú ý pagination và nhiều collection:** không fetch join tập lớn rồi limit bừa.
11. **Tách cascade/orphanRemoval khỏi fetch:** xem từng annotation theo trách nhiệm.
12. **Viết integration tests trên provider thật:** nhất là lazy basic và inverse one-to-one.

### Có nên đặt tất cả association LAZY không?

Đây có thể là **điểm xuất phát tốt** trong nhiều domain nhưng không phải luật cứng:

- To-one LAZY không phải luôn được hỗ trợ trì hoãn hoàn hảo.
- Một số entity nhỏ, bắt buộc và luôn được dùng chung có thể phù hợp EAGER.
- Một mapping EAGER có thể gây chi phí lớn khi entity được truy vấn từ nhiều use cases.
- Có thể dùng graph/fetch join để chọn EAGER theo truy vấn thay vì đặt mặc định global.

**Quyết định nên dựa trên workload và khả năng implementation, không chỉ dựa trên một khẩu hiệu.**

## 47. Bài tập thực hành

### Bài 1 — Mặc định của @ManyToOne

Với:

~~~java
@ManyToOne
private Customer customer;
~~~

JPA mặc định là EAGER hay LAZY?

**Gợi ý:** EAGER. Nếu muốn gợi ý tải chậm, khai báo `fetch = FetchType.LAZY`.

### Bài 2 — Mặc định của @OneToMany

Với:

~~~java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
~~~

Mặc định là gì?

**Gợi ý:** LAZY.

### Bài 3 — EAGER và JOIN

Một `@ManyToOne(fetch=EAGER)` có bắt buộc dùng SQL JOIN không?

**Gợi ý:** không. Provider có thể dùng SELECT phụ hoặc chiến lược khác để đáp ứng eager fetch.

### Bài 4 — LAZY là hint

Nếu khai báo `@Basic(fetch=LAZY)` trên một String LOB, có thể khẳng định mọi provider đều tránh tải cột này ở lần SELECT đầu không?

**Gợi ý:** không; cần hỗ trợ/enhancement phù hợp, hãy đo SQL.

### Bài 5 — N+1 với LAZY

Trang có 100 Order, code duyệt `order.getCustomer().getName()`. Vì sao vẫn có thể phát nhiều query dù LAZY đã khai báo?

**Gợi ý:** mỗi Customer chưa loaded có thể cần SELECT riêng. Thiết kế JOIN FETCH, entity graph hoặc DTO.

### Bài 6 — N+1 với EAGER

Nếu đổi customer sang EAGER, N+1 có chắc biến mất?

**Gợi ý:** không. Provider vẫn có thể nạp Customer bằng secondary SELECTs.

### Bài 7 — Lỗi sau khi EntityManager đóng

Service trả PurchaseOrder entity detached, controller gọi `getLines().size()` và gặp Hibernate LazyInitializationException. Vì sao?

**Gợi ý:** collection chưa initialized, không còn session/persistence context để nạp thêm.

### Bài 8 — JOIN và JOIN FETCH

Hai JPQL:

~~~jpql
SELECT o FROM PurchaseOrder o JOIN o.customer c
~~~

~~~jpql
SELECT o FROM PurchaseOrder o JOIN FETCH o.customer
~~~

Khác nhau gì về mục tiêu?

**Gợi ý:** JOIN thông thường dùng relationship cho điều kiện/traversal; JOIN FETCH yêu cầu nạp association.

### Bài 9 — INNER vs LEFT

Product.category nullable. Truy vấn `JOIN FETCH p.category` có thể bỏ Product nào?

**Gợi ý:** Product không có Category. Dùng `LEFT JOIN FETCH` nếu muốn giữ.

### Bài 10 — Pagination với collection

Vì sao `setMaxResults(20)` trên query `LEFT JOIN FETCH o.lines` có thể rủi ro?

**Gợi ý:** một Order tạo nhiều hàng JDBC, limit ở row level có thể không tương ứng 20 Order root.

### Bài 11 — Entity graph

Mapping `Order.customer` là LAZY, nhưng một use case muốn tải Customer ngay. Có thể dùng công cụ nào mà không sửa mapping global?

**Gợi ý:** `JOIN FETCH` hoặc entity graph chứa attribute `customer`.

### Bài 12 — fetchgraph và loadgraph

Khác biệt của `jakarta.persistence.fetchgraph` và `jakarta.persistence.loadgraph` là gì?

**Gợi ý:** cả hai yêu cầu nạp attribute trong graph; fetchgraph xem attribute không chỉ định là LAZY theo graph semantics, loadgraph giữ mapping defaults cho các attribute còn lại, trong giới hạn provider được fetch thêm.

### Bài 13 — DTO

API danh sách chỉ cần Order ID, status và Customer name. Có cần return managed Order + managed Customer không?

**Gợi ý:** không bắt buộc. Dùng JPQL constructor projection trả DTO.

### Bài 14 — @ElementCollection

Tập keywords String được ánh xạ bằng `@ElementCollection`. Fetch mặc định là gì?

**Gợi ý:** LAZY.

### Bài 15 — Cascade

`cascade=CascadeType.ALL` có làm `lines` trở thành EAGER không?

**Gợi ý:** không. Cascade quản lý lifecycle operations, FetchType quản lý fetch timing.

### Bài 16 — One-to-one inverse

Vì sao `@OneToOne(mappedBy="user",fetch=LAZY)` có thể vẫn cần SQL khi đọc User?

**Gợi ý:** provider có thể phải xác định có UserProfile hay không, đặc biệt nullable và không có enhancement.

### Bài 17 — isLoaded

`PersistenceUnitUtil.isLoaded(order,"lines")` có dùng để kiểm tra tình trạng loaded không? Nếu `lines` được khai báo LAZY, kết quả có bắt buộc false lúc đầu?

**Gợi ý:** có API kiểm tra; không bắt buộc false vì LAZY chỉ là hint và query có thể đã fetch.

### Bài 18 — toString

Vì sao tự động sinh toString chứa Customer và lines có thể làm ứng dụng phát SQL lúc ghi log?

**Gợi ý:** toString truy cập lazy association.

### Bài 19 — Collection fetch graph

Một graph lấy Order + lines + Product để hiển thị chi tiết. Có nên dùng cùng graph đó cho API phân trang 50.000 Order?

**Gợi ý:** không mặc định; graph sâu tạo nhiều rows/entities và có thể phá hiệu quả pagination.

### Bài 20 — Batch fetching

Giữ `@ManyToOne(fetch=LAZY)`, có thể giảm SELECT bằng cách nạp nhiều Customer theo ID trong một query không?

**Gợi ý:** có, batch fetching hoặc thiết kế query-level fetch phù hợp; `@BatchSize` là Hibernate-specific.

### Bài 21 — Transaction isolation

LAZY association chỉ được truy cập sau khi một transaction khác commit. Có bảo đảm nó luôn thấy giá trị mới nhất không?

**Gợi ý:** không; còn phụ thuộc snapshot, isolation, first-level/second-level cache và thời điểm fetch.

### Bài 22 — Phân biệt first-level cache

Một Customer đã managed trong EntityManager. Nếu hai Order tham chiếu cùng Customer, JPA có cần tạo hai managed Customer instances độc lập không?

**Gợi ý:** không; identity map giữ cùng entity identity trong context.

### Bài 23 — Đếm collection

Muốn hiển thị số OrderLine của mỗi Order, có nên nạp `order.getLines()` cho 1.000 Order rồi gọi size() không?

**Gợi ý:** thường không. Dùng JPQL `COUNT`/GROUP BY hoặc projection theo nhu cầu.

### Bài 24 — Lỗi do serializer

Một API trả entity trực tiếp, serializer đi qua relationship hai chiều và gây recursion. Có thể giải quyết bền vững bằng cách nào?

**Gợi ý:** dùng DTO biểu diễn schema API rõ ràng; serializer annotations chỉ là biện pháp riêng, không thay fetch plan.

## 48. Bảng ghi nhớ nhanh

| Tình huống | Điều nên nhớ |
| --- | --- |
| `@ManyToOne` không ghi fetch | Default **EAGER** |
| `@OneToOne` không ghi fetch | Default **EAGER** |
| `@OneToMany` không ghi fetch | Default **LAZY** |
| `@ManyToMany` không ghi fetch | Default **LAZY** |
| `@ElementCollection` không ghi fetch | Default **LAZY** |
| `@Basic` không ghi fetch | Default **EAGER** |
| EAGER có bảo đảm một JOIN? | **Không** |
| LAZY có bảo đảm không SQL trước getter? | **Không**, là hint |
| EAGER tự ngăn N+1? | **Không** |
| LAZY tự ngăn N+1? | **Không** |
| Lazy collection sau detach | Có thể không thể initialize |
| Hibernate LazyInitializationException | Exception riêng Hibernate |
| Muốn nạp Customer trong một query | `JOIN FETCH o.customer` hoặc graph |
| Chỉ muốn filter theo Customer | `JOIN o.customer c`, không mặc định fetch |
| Muốn giữ root khi association nullable | `LEFT JOIN FETCH` khi phù hợp |
| Phân trang root có to-many fetch join | Tránh trực tiếp; page IDs rồi fetch |
| Chỉ cần vài cột cho API | Ưu tiên DTO projection |
| Muốn kiểm tra attribute đã loaded | `PersistenceUnitUtil.isLoaded(entity, attr)` |
| LAZY basic LOB | Có thể cần bytecode enhancement |
| Inverse lazy @OneToOne | Cần xem provider/optional/bytecode |
| @JsonIgnore | Không thay JPA fetch plan |
| CascadeType.ALL | Không có nghĩa EAGER |
| Query-level fetch graph | Điều chỉnh theo use case, không đổi mapping global |
| FetchType và transaction isolation | Khái niệm độc lập |
| N+1 | Đo SQL/round trips trong **toàn use case** |

## Kết luận

**Tải ngay (EAGER) và tải chậm (LAZY) ở mức ánh xạ JPA** là hai chính sách về thời điểm nạp thuộc tính hoặc association, **không phải hai chiến lược SQL cố định**. `EAGER` là yêu cầu tải dữ liệu theo hợp đồng JPA, nhưng có thể được thực hiện bằng JOIN, SELECT phụ hoặc cache; `LAZY` là gợi ý trì hoãn và không phải lúc nào cũng được provider hiện thực giống nhau, đặc biệt với basic field và một số one-to-one associations.

Hãy nhớ các mặc định: **`@ManyToOne` và `@OneToOne` EAGER; `@OneToMany`, `@ManyToMany` và `@ElementCollection` LAZY; `@Basic` EAGER**. Dùng LAZY phù hợp giúp tránh tải graph không cần thiết, nhưng không tự loại bỏ N+1. Nếu use case cần association, hãy chọn fetch plan riêng bằng `JOIN FETCH`, entity graph, batch fetching hoặc DTO projection; đồng thời xem JOIN cardinality, pagination và giới hạn persistence context.

Một thiết kế tốt tách bạch **mapping defaults**, **fetch plan của từng truy vấn**, **transaction/persistence context lifecycle** và **khả năng nhìn thấy dữ liệu của database**. Khi chỉ nạp những gì nghiệp vụ cần, kiểm soát serialization và đo SQL thực tế, ứng dụng JPA vừa tránh lỗi lazy loading ngoài ý muốn vừa giảm được chi phí I/O, bộ nhớ và độ trễ.
