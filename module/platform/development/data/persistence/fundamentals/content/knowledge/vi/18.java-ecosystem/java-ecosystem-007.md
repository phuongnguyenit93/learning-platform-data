# Ánh xạ đối tượng–quan hệ và những khác biệt mô hình cần giải quyết

Ứng dụng Java thường tổ chức dữ liệu thành **đối tượng**: một đơn hàng có khách hàng, các dòng hàng, phương thức kiểm tra trạng thái và quy tắc nghiệp vụ. Cơ sở dữ liệu quan hệ lại lưu dữ liệu thành **bảng, hàng, cột, khóa chính, khóa ngoại và ràng buộc**. Hai mô hình cùng mô tả nghiệp vụ nhưng khác nhau về cách biểu diễn, vòng đời, danh tính và truy cập dữ liệu.

**Ánh xạ đối tượng–quan hệ** (*Object–Relational Mapping, ORM*) là tập kỹ thuật nối hai mô hình đó: biến hàng dữ liệu thành đối tượng Java, biến thay đổi ở đối tượng thành câu lệnh SQL và theo dõi danh tính/vòng đời trong phạm vi làm việc. Trong hệ sinh thái Java, **Jakarta Persistence (JPA)** định nghĩa một API/chuẩn ánh xạ, còn **Hibernate ORM** là một hiện thực được sử dụng rộng rãi. ORM không loại bỏ SQL hoặc các đặc tính của cơ sở dữ liệu; nó tạo một lớp trừu tượng và đồng thời đưa ra những đánh đổi cần được hiểu rõ.

Bài thuộc chương **Hệ sinh thái Java** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Bối cảnh là thiết kế lớp persistence bền vững cho Java: hiểu mô hình dữ liệu, truy vấn, chỉ mục, giao dịch, cô lập, kiểm soát đồng thời, thay đổi schema và hiệu năng. Trọng tâm ở đây không phải ghi nhớ annotation, mà là **nhận diện những khác biệt giữa mô hình đối tượng và mô hình quan hệ, rồi lựa chọn cách xử lý có kiểm chứng**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích *object–relational impedance mismatch* — sự không khớp giữa mô hình đối tượng và mô hình quan hệ.
2. Ánh xạ entity, khóa chính, khóa ngoại, quan hệ một–nhiều và value object vào các bảng quan hệ.
3. Phân biệt **định danh đối tượng**, **định danh hàng trong DB**, **đẳng thức nghiệp vụ** và **vòng đời entity**.
4. Giải thích sự khác nhau giữa đồ thị đối tượng và kết quả JOIN, cũng như hệ quả của lazy loading và N+1 queries.
5. Hiểu phạm vi persistence context, dirty checking, flush, commit và giới hạn của cascade.
6. Dùng transaction, ràng buộc DB và optimistic locking để bảo vệ dữ liệu khi có truy cập đồng thời.
7. Nhận diện các vấn đề ánh xạ kiểu dữ liệu, null, inheritance, collection, migration và điều kiện truy vấn.
8. Quyết định khi nào ORM phù hợp, khi nào cần truy vấn/projection chuyên biệt hoặc JDBC/SQL rõ ràng.

## 2. Vì sao hai mô hình không khớp hoàn toàn?

### 2.1. Mô hình đối tượng Java

Trong Java, có thể biểu diễn đơn hàng như một tập đối tượng có tham chiếu qua lại:

~~~text
PurchaseOrder object
  id: Long
  customer: Customer object
  status: OrderStatus
  items: List<OrderItem object>
  totalAmount: BigDecimal

Customer object
  id: Long
  displayName: String

OrderItem object
  sku: String
  quantity: int
  unitPrice: BigDecimal
  order: PurchaseOrder object
~~~

Trong bộ nhớ:

- Một đối tượng có **identity theo tham chiếu**, ví dụ phép so sánh `a == b`.
- Đồ thị tham chiếu có thể chứa vòng: `order.items[0].order == order`.
- Collection có thể là `List`, `Set` hoặc `Map`, với quy tắc thứ tự/trùng lặp khác nhau.
- Phương thức đối tượng có thể bảo vệ bất biến và che giấu trạng thái bên trong.
- Đối tượng có thể được tạo bằng `new` mà chưa tồn tại trong database.

### 2.2. Mô hình quan hệ

Với database quan hệ, dữ liệu thường được lưu như:

~~~text
customers
+----+--------------+
| id | display_name |
+----+--------------+
|  7 | Minh         |
+----+--------------+

purchase_orders
+----+-------------+---------+--------------+---------+
| id | customer_id | status  | total_amount | version |
+----+-------------+---------+--------------+---------+
| 42 |           7 | CREATED |       250.00 |       0 |
+----+-------------+---------+--------------+---------+

order_items
+-----+----------+---------+----------+------------+
| id  | order_id | sku     | quantity | unit_price |
+-----+----------+---------+----------+------------+
| 101 |       42 | BOOK-01 |        2 |     125.00 |
+-----+----------+---------+----------+------------+
~~~

Quan hệ giữa các hàng không phải tham chiếu đối tượng: `purchase_orders.customer_id` chứa **giá trị khóa ngoại** trỏ đến `customers.id`; `order_items.order_id` trỏ đến `purchase_orders.id`. Muốn truy vấn thông tin từ nhiều bảng có thể cần `JOIN` hoặc nhiều câu `SELECT`.

Bảng so sánh:

| Đặc tính | Đối tượng Java | Database quan hệ |
|---|---|---|
| Định danh | Tham chiếu đối tượng, hoặc ID miền | Giá trị khóa chính/khóa duy nhất |
| Quan hệ | Tham chiếu và collection | Khóa ngoại, JOIN, bảng nối |
| Đơn vị thao tác | Đối tượng và phương thức | Hàng/bộ hàng, SQL statement |
| Vòng đời | Tạo bằng `new`, GC, thay đổi trạng thái | `INSERT`, `UPDATE`, `DELETE`, transaction |
| Tính duy nhất | Logic ứng dụng, `equals/hashCode` | `PRIMARY KEY`, `UNIQUE` |
| Giá trị thiếu | `null`, `Optional`, trạng thái trong domain | `NULL` và logic ba giá trị trong SQL |
| Kế thừa | Class/interface, polymorphism | Không có inheritance như Java; cần chiến lược bảng |
| Tải dữ liệu | Theo tham chiếu đã có trong memory | Truy vấn SQL, network I/O, bộ nhớ đệm |
| Đồng thời | Nhiều thread và object trong JVM | Nhiều transaction/connection, khóa và MVCC |
| Truy vấn | Traversal qua object graph | Lọc, JOIN, tổng hợp, sort trên tập hàng |

**Impedance mismatch** chính là khoảng cách giữa những giả định tự nhiên ở hai cột. ORM hỗ trợ ánh xạ nhưng người thiết kế phải quyết định ngữ nghĩa nào cần giữ và chi phí nào có thể chấp nhận.

## 3. Ví dụ tự chứa: một đơn hàng qua bảng và entity

### 3.1. Thiết kế schema trước

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE customers (
    id           BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);

CREATE TABLE purchase_orders (
    id           BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id  BIGINT NOT NULL REFERENCES customers(id),
    status       VARCHAR(24) NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL CHECK (total_amount >= 0),
    version      BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    id         BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id   BIGINT NOT NULL REFERENCES purchase_orders(id),
    sku        VARCHAR(64) NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT uq_order_item_sku UNIQUE (order_id, sku)
);

CREATE INDEX idx_purchase_orders_customer
    ON purchase_orders (customer_id);

CREATE INDEX idx_order_items_order
    ON order_items (order_id);
~~~

Một số đặc điểm cố ý:

- `PRIMARY KEY` và `FOREIGN KEY` bảo vệ định danh/tham chiếu ngay cả khi dữ liệu được ghi ngoài ORM.
- `CHECK` và `NOT NULL` bảo vệ các quy tắc có thể biểu diễn trên một hàng.
- `UNIQUE (order_id, sku)` quy định một đơn không có hai dòng riêng biệt cho cùng SKU; thay đổi nếu nghiệp vụ cho phép trùng.
- Index trên khóa ngoại hỗ trợ một số JOIN và truy vấn theo cha, nhưng việc DBMS tự tạo index cho khóa ngoại phụ thuộc hệ quản trị. Trong PostgreSQL, tạo foreign key không mặc nhiên tạo index trên cột tham chiếu ở phía con.
- `total_amount` được lưu như một giá trị tổng; ứng dụng phải giữ nó đồng bộ với các dòng hàng, hoặc thiết kế bỏ cột tổng nếu có thể tính khi đọc. Không nên chỉ dựa vào annotation để cho rằng bất biến này được DBMS bảo vệ.

### 3.2. Biểu diễn trong Jakarta Persistence

Các đoạn Java dưới đây minh họa **một tập entity tối giản**. Dự án thật cần import, cấu hình persistence provider, repository, dependency và kiểm thử; dùng `jakarta.persistence.*` theo hệ Jakarta Persistence hiện đại.

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;
import java.math.BigDecimal;

@Entity
@Table(name = "customers")
public class CustomerEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected CustomerEntity() {}

    public CustomerEntity(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
}
~~~

~~~java
public enum OrderStatus {
    CREATED, CONFIRMED, CANCELLED
}
~~~

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrderEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private CustomerEntity customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private OrderStatus status = OrderStatus.CREATED;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    private List<OrderItemEntity> items = new ArrayList<>();

    protected PurchaseOrderEntity() {}

    public PurchaseOrderEntity(CustomerEntity customer) {
        this.customer = customer;
    }

    public void addItem(String sku, int quantity, BigDecimal unitPrice) {
        if (quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order item");
        }
        OrderItemEntity item =
            new OrderItemEntity(this, sku, quantity, unitPrice);
        items.add(item);
        totalAmount = totalAmount.add(
            unitPrice.multiply(BigDecimal.valueOf(quantity))
        );
    }

    public Long getId() { return id; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public List<OrderItemEntity> getItems() {
        return List.copyOf(items);
    }
}
~~~

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(
    name = "order_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_order_item_sku",
        columnNames = {"order_id", "sku"}
    )
)
public class OrderItemEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrderEntity order;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItemEntity() {}

    OrderItemEntity(
            PurchaseOrderEntity order,
            String sku,
            int quantity,
            BigDecimal unitPrice) {
        this.order = order;
        this.sku = sku;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }
}
~~~

**Điều cần hiểu sau ví dụ:**

1. `@Entity` nói đây là loại đối tượng được persistence provider quản lý; `@Table` xác định tên bảng.
2. `@Id` là định danh persistent của entity; `@GeneratedValue(IDENTITY)` minh họa DB cấp ID theo cơ chế identity.
3. `@ManyToOne` và `@JoinColumn` ánh xạ tham chiếu `customer` thành giá trị cột `customer_id`.
4. `@OneToMany(mappedBy = "order")` ánh xạ collection các dòng hàng; phía `OrderItemEntity.order` là **phía sở hữu quan hệ** qua khóa ngoại.
5. `cascade = ALL` cho phép một số thao tác persist/merge/remove từ đơn lan đến các dòng hàng, không phải mặc nhiên áp dụng tới khách hàng.
6. `orphanRemoval = true` thể hiện chính sách xóa một dòng hàng khi nó bị loại khỏi quan hệ được quản lý; chỉ nên chọn nếu dòng hàng thực sự thuộc vòng đời của đơn.
7. `@Version` là trường phiên bản hỗ trợ optimistic locking, **không phải khóa DB hoặc transaction manager**.
8. `@Column` mô tả ánh xạ và có thể tham gia sinh schema, nhưng trong production các ràng buộc thật phải được tạo/duy trì bằng schema migration có kiểm soát.
9. Phương thức `addItem` cập nhật cả collection, tham chiếu chiều ngược lại và tổng tiền; nếu bổ sung phương thức xóa/sửa dòng thì cũng phải bảo vệ tính nhất quán tương tự.

Ví dụ minh họa một lựa chọn thiết kế, không phải cấu trúc duy nhất hợp lệ. Với hệ thống lớn có thể tách domain model khỏi persistence entity để tránh đưa annotation và lifecycle ORM vào miền nghiệp vụ.

## 4. Danh tính: `==`, `equals()` và khóa chính không đồng nghĩa

Một trong những khác biệt dễ gây lỗi nhất là **identity**.

### 4.1. Định danh của đối tượng trong bộ nhớ

Trong Java:

~~~java
CustomerEntity a = new CustomerEntity("Minh");
CustomerEntity b = new CustomerEntity("Minh");

System.out.println(a == b); // false: hai instance khác nhau
~~~

Hai object có nội dung giống nhau nhưng là hai tham chiếu khác nhau. Nếu không override `equals()`, phép bằng về object thông thường cũng không xem chúng là cùng entity.

### 4.2. Định danh trong database

Trong mô hình quan hệ, `customers.id = 7` xác định một hàng. Trong **một persistence context**, JPA quản lý identity map cho một loại entity và ID nhất định: tải lại cùng entity thường được trả về cùng instance được quản lý trong phạm vi đó.

Nhưng ở **hai persistence context khác nhau**:

~~~text
Context A: CustomerEntity(id=7) -> Java object A
Context B: CustomerEntity(id=7) -> Java object B

Cùng hàng DB; có thể là hai instance Java khác nhau.
~~~

Vì vậy `a == b` không đáng tin để so sánh entity đến từ những session/transaction khác nhau.

### 4.3. Bẫy `equals()` và `hashCode()` với ID sinh tự động

Entity mới chưa persist có thể có `id == null`. Sau khi insert, DB cấp ID. Nếu `hashCode()` phụ thuộc trực tiếp vào ID, mã băm của object có thể thay đổi trong lúc object đang nằm trong `HashSet`/`HashMap`, làm hỏng khả năng tìm kiếm theo khóa.

Những lựa chọn phổ biến có đánh đổi:

- Dùng **business key bất biến và thật sự duy nhất** để định nghĩa đẳng thức nếu miền có khóa như vậy.
- Dùng ID persistent với cách xử lý đối tượng mới và hash code nhất quán, được kiểm chứng với proxy và vòng đời entity.
- Không override `equals/hashCode` cho những entity mà ứng dụng không cần đẳng thức xuyên persistence context; sử dụng ID tại ranh giới service/DTO.

Không nên copy một công thức `equals/hashCode` dùng cho mọi entity. Cần xét **ID được gán lúc nào**, proxy của provider, kế thừa, collection sử dụng và ngữ nghĩa miền.

## 5. Quan hệ: tham chiếu và collection khác khóa ngoại và JOIN

### 5.1. Khóa ngoại quyết định quan hệ persistent

Trong ví dụ, DB lưu `order_items.order_id`. Phía `OrderItemEntity.order` sở hữu phép ánh xạ khóa ngoại. `PurchaseOrderEntity.items` là mặt nhìn ngược được khai báo bằng `mappedBy`.

Khi quan hệ hai chiều được duy trì trong bộ nhớ, hai phía phải thống nhất:

~~~java
// Phương thức addItem trong PurchaseOrderEntity:
OrderItemEntity item =
    new OrderItemEntity(this, sku, quantity, unitPrice);
items.add(item);
~~~

Nếu chỉ thêm một đối tượng vào collection nhưng phía giữ khóa ngoại không được thiết lập, trạng thái memory có thể không đúng với trạng thái sẽ được ghi. Thiết kế helper method ở aggregate root giúp ngăn lỗi này.

**Quan hệ hai chiều không phải bắt buộc.** Nếu ứng dụng chỉ đi từ item về order, một quan hệ một chiều có thể đơn giản và ít trạng thái phải đồng bộ hơn.

### 5.2. `List` có bắt buộc lưu thứ tự không?

Một `List<OrderItemEntity>` trong Java có thứ tự quan sát được; bảng SQL **không có thứ tự dòng mặc định** khi truy vấn không có `ORDER BY`. Trong ORM:

- `@OrderBy` thường yêu cầu sắp xếp khi tải collection theo thuộc tính của entity.
- `@OrderColumn` có thể ánh xạ **vị trí** của phần tử vào một cột riêng để duy trì thứ tự danh sách.
- Không khai báo chiến lược thứ tự phù hợp thì không nên dựa vào thứ tự hàng khi đọc từ DB.

Nếu thứ tự là yêu cầu nghiệp vụ (ví dụ vị trí dòng trên hóa đơn), hãy biểu diễn nó bằng cột rõ ràng và ràng buộc/điều kiện truy vấn phù hợp, thay vì mong DB trả thứ tự insert.

### 5.3. Quan hệ nhiều–nhiều có thể cần bảng liên kết thành entity

Quan hệ `Student ↔ Course` có thể biểu diễn bằng bảng nối `enrollments(student_id, course_id)`. Nhưng nếu quan hệ có thêm `enrolled_at`, `grade`, `status`, nó không còn chỉ là một liên kết vô danh.

Khi bảng nối có **dữ liệu/nghiệp vụ riêng**, thường nên mô hình thành entity `Enrollment` với khóa và thuộc tính rõ ràng, thay vì dùng `@ManyToMany` thuần rồi khó truy cập thuộc tính quan hệ.

Một điểm nữa: **cascade remove** theo nhiều–nhiều phải được xem rất cẩn thận. Xóa một enrollment không có nghĩa xóa luôn một course mà các student khác đang tham gia.

### 5.4. Aggregate và quyền sở hữu vòng đời

Không phải mọi entity có foreign key đều nên bị xóa theo cascade. Trong ví dụ:

- `OrderItem` thường có vòng đời phụ thuộc `PurchaseOrder` nên cascade và orphan removal có thể phù hợp.
- `Customer` tồn tại độc lập với đơn nên **không** nên xóa customer chỉ vì xóa một order.

Ranh giới aggregate theo Domain-Driven Design là quyết định của miền nghiệp vụ; nó **không đồng nhất tự động** với bảng, foreign key hoặc annotation cascade. ORM chỉ thực thi quy tắc ánh xạ đã khai báo, không tự biết vòng đời nghiệp vụ của đối tượng.

## 6. Vòng đời entity và persistence context

ORM có một tầng trạng thái không hiện diện trực tiếp trong schema: **entity lifecycle**.

| Trạng thái (JPA) | Ý nghĩa | Hệ quả |
|---|---|---|
| **New / transient** | Tạo bằng `new`, chưa được persistence context quản lý | Chưa có bản ghi DB tương ứng từ lần tạo này |
| **Managed** | Đang được `EntityManager` quản lý | Thay đổi thuộc tính persistent có thể được phát hiện và đồng bộ |
| **Detached** | Trước đó được quản lý nhưng đã rời context | Sửa object không tự ghi vào DB |
| **Removed** | Entity được đánh dấu xóa trong context | `DELETE` có thể được phát ra khi flush theo quy tắc provider |

Ví dụ:

~~~java
PurchaseOrderEntity order = new PurchaseOrderEntity(customer);
// Mới tạo; chưa là managed entity.

entityManager.persist(order);
// Entity được quản lý; INSERT có thể chưa xảy ra ngay.

entityManager.flush();
// Đồng bộ những thay đổi cần thiết xuống DB qua SQL.
// Chưa đồng nghĩa với COMMIT.
~~~

### 6.1. Dirty checking

Khi một entity đang **managed** được sửa:

~~~java
PurchaseOrderEntity order =
    entityManager.find(PurchaseOrderEntity.class, orderId);

// Ví dụ một phương thức miền thay đổi trạng thái:
order.confirm();
~~~

persistence provider có thể theo dõi thay đổi (*dirty checking*) và phát `UPDATE` khi flush, thay vì yêu cầu gọi `repository.update` cho mọi field. Phương thức `confirm()` chỉ là ví dụ API miền; muốn chạy thực tế phải được định nghĩa trong entity.

**Không suy ra rằng câu `UPDATE` được gửi ngay khi setter chạy.** Thời điểm flush phụ thuộc flush mode, provider, câu truy vấn tiếp theo và ranh giới transaction.

### 6.2. Flush không phải commit

Phân biệt:

- **Flush:** provider đồng bộ thay đổi trong persistence context với database bằng các thao tác SQL cần thiết.
- **Commit:** transaction hoàn tất, các thay đổi được chấp nhận bền vững theo hợp đồng giao dịch của DBMS.

~~~text
BEGIN transaction
  entityManager.persist(order)
  entityManager.flush()       -> SQL INSERT có thể đã chạy
  xảy ra lỗi nghiệp vụ
ROLLBACK                      -> INSERT bị rollback
~~~

Vì vậy việc thấy SQL trong log **không chứng minh** nghiệp vụ đã commit. Ngược lại, vi phạm unique/foreign key có thể chỉ được DB báo tại flush hoặc commit, không nhất thiết ngay tại dòng mã `persist()`.

### 6.3. Detached và `merge()`

Một entity được tải trong transaction trước, sau đó mang ra khỏi persistence context, là một object **detached**. Sửa nó không tự được lưu.

`EntityManager.merge(detached)` tạo hoặc tìm một **instance managed** tương ứng rồi sao chép trạng thái có thể merge theo quy tắc JPA; **giá trị trả về** là instance managed, còn object truyền vào vẫn không tự biến thành managed.

Đây là nguồn lỗi phổ biến khi ứng dụng sửa entity ở ngoài transaction rồi merge dữ liệu cũ, vô tình ghi đè thay đổi đồng thời. Cần thiết kế API cập nhật có ngữ nghĩa rõ ràng, optimistic locking và kiểm tra trường nào thực sự được phép sửa.

### 6.4. Persistence context khác database transaction

Một persistence context quản lý identity map và tập entity; một transaction quản lý atomicity/consistency với DBMS. Trong các mô hình transaction-scoped thường gặp, hai phạm vi có quan hệ gần nhau nhưng **không phải cùng một khái niệm**.

Không giữ một `EntityManager` không an toàn luồng rồi chia sẻ cho nhiều request. `EntityManagerFactory` được thiết kế dùng chung, còn `EntityManager` cần theo vòng đời và mô hình đồng thời do framework/container quản lý.

## 7. Lazy loading, eager loading và vấn đề N+1

Với mô hình đối tượng, code có thể truy cập:

~~~java
for (PurchaseOrderEntity order : orders) {
    System.out.println(order.getCustomer().getDisplayName());
}
~~~

Nhưng `order.getCustomer()` không nhất thiết chỉ là một truy cập bộ nhớ. Nếu thuộc tính chưa được tải, provider có thể phải gửi SQL bổ sung.

### 7.1. Ví dụ N+1

Giả sử service tải 100 đơn bằng một câu SQL; sau đó vòng lặp cần tên khách hàng của từng đơn.

~~~text
1 query:  SELECT ... FROM purchase_orders
N query: SELECT ... FROM customers WHERE id = ?

Tổng có thể gần 101 query cho 100 đơn.
~~~

Nếu nhiều đơn cùng trỏ tới một customer, first-level cache có thể giúp giảm số query; vì vậy con số là minh họa về dạng vấn đề, không phải số query bắt buộc.

N+1 thường làm tăng lượt đi mạng, thời gian phản hồi và tải DB. Chỉ nhìn một method Java hoặc tổng số entity trong bộ nhớ không đủ để phát hiện; cần đo **SQL thực tế**.

### 7.2. Kiểm soát fetch theo use case

Các phương án tùy nhu cầu:

- **Fetch join** khi cần tải một đối tượng và quan hệ liên quan trong một truy vấn.
- **Entity graph** để yêu cầu provider tải các quan hệ cụ thể theo một phương án truy cập.
- **DTO projection** khi API chỉ cần vài trường, tránh vật thể hóa toàn bộ entity graph.
- **Batch fetching** khi provider hỗ trợ gom nhiều lần tải quan hệ vào ít query hơn.
- **Query chuyên biệt** bằng SQL/JPQL/DSL nếu báo cáo cần tổng hợp hoặc nhiều JOIN tối ưu.

Ví dụ JPQL để lấy một đơn với dòng hàng:

~~~java
PurchaseOrderEntity order = entityManager.createQuery(
    """
    select distinct o
    from PurchaseOrderEntity o
    left join fetch o.items
    where o.id = :orderId
    """,
    PurchaseOrderEntity.class
).setParameter("orderId", orderId)
 .getSingleResult();
~~~

Ở đây `fetch join` tải `items` cùng truy vấn; `distinct` thể hiện ý định không lặp entity cha ở kết quả JPQL. Hành vi loại trùng, SQL phát ra và số hàng nhận về phụ thuộc provider/phiên bản; phải quan sát SQL thật.

### 7.3. Fetch join collection và pagination

Một đơn có nhiều item sẽ xuất hiện ở **nhiều dòng kết quả SQL** sau JOIN. Nếu áp dụng `LIMIT/OFFSET` trực tiếp trên những dòng đó, database có thể cắt ngang collection hoặc số lượng đơn thực tế không đúng.

Vì vậy **phân trang danh sách entity cha kèm fetch join collection** cần đặc biệt thận trọng. Một chiến lược phổ biến:

1. Truy vấn một trang **ID đơn hàng** theo điều kiện và thứ tự xác định.
2. Tải chi tiết cho tập ID ấy bằng truy vấn khác với fetch cần thiết.
3. Khôi phục thứ tự của trang theo kết quả ở bước một.

Provider có thể phát cảnh báo hoặc chọn phân trang trong bộ nhớ ở một số tình huống; không dựa vào hành vi này như tối ưu mặc định.

### 7.4. Lazy loading ngoài persistence context

Ví dụ một controller nhận entity rồi truy cập `order.getItems()` sau khi transaction/persistence context đã đóng. Nếu collection chưa được khởi tạo, provider có thể báo lỗi lazy initialization.

Giải pháp thường bền vững hơn:

- Xây DTO của response **trong application service/transaction hợp lệ**.
- Tải trước đúng những quan hệ cần dùng bằng query/projection/entity graph.
- Không phụ thuộc vào việc giữ persistence context mở xuyên tới tầng HTTP view chỉ để lazy loading hoạt động.

Một số ứng dụng bật cơ chế *Open Session in View*, nhưng cách này có thể che các truy vấn N+1 tại view/controller và kéo dài phụ thuộc persistence ra ngoài ranh giới nghiệp vụ. Nếu dùng, phải hiểu rõ đánh đổi.

## 8. Ánh xạ kiểu dữ liệu: không chỉ là chọn class tương ứng

Các kiểu ở Java và DBMS không đồng nhất một–một.

### 8.1. Tiền: `BigDecimal` và `NUMERIC`

Java `double` là số dấu phẩy động nhị phân, không đại diện chính xác nhiều phân số thập phân như `0.1`. Với tiền, thường dùng `BigDecimal` và `NUMERIC(p, s)`/`DECIMAL(p, s)`.

~~~java
BigDecimal price = new BigDecimal("125.00");
BigDecimal quantity = BigDecimal.valueOf(2);
BigDecimal total = price.multiply(quantity);
~~~

Tránh `new BigDecimal(0.1)` nếu muốn biểu diễn chính xác chuỗi thập phân `0.1`. Đồng thời phải quy định rõ **currency, scale, rounding** và các giới hạn cột. `BigDecimal.equals` xét cả scale (`1.0` không equals `1.00`), còn `compareTo` so sánh giá trị số; cần chọn theo ngữ nghĩa.

### 8.2. Thời gian và múi giờ

Java có `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime` và các kiểu khác. Database có `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` hoặc các ngữ nghĩa tương tự không hoàn toàn giống nhau giữa DBMS.

Ví dụ:

- **Ngày sinh** thường là `LocalDate` và cột `DATE`, không cần thời điểm UTC.
- **Thời điểm tạo đơn** nên có ngữ nghĩa thời điểm tuyệt đối; `Instant` có thể phù hợp nếu provider/driver và DBMS ánh xạ đúng.
- **Giờ hẹn tại địa phương** có thể cần thêm timezone ID và quy tắc DST, không chỉ một `Instant`.

Với PostgreSQL, `timestamptz` lưu giá trị theo nghĩa thời điểm chứ không giữ nguyên timezone name do caller gửi. Hãy quy định timezone ở API và DB, kiểm tra mapping của driver/provider, đặc biệt khi đổi DBMS.

### 8.3. `NULL`, kiểu nguyên thủy và `Optional`

Cột SQL `NULL` biểu thị không có giá trị theo ngữ nghĩa ba giá trị; `WHERE col = NULL` không hoạt động như phép bằng Java mà thường cần `IS NULL`.

Trong Java:

- `int`/`long` không biểu diễn được null; `Integer`/`Long` có thể.
- `@Column(nullable = false)` diễn tả yêu cầu ánh xạ/schema nhưng không thay thế ràng buộc `NOT NULL` thực tế trên DB.
- `Optional<T>` hữu ích ở API/service khi biểu diễn kết quả có thể không tồn tại; không mặc định mọi provider hỗ trợ `Optional` như persistent field theo cùng cách.
- Giá trị rỗng và `NULL` khác nhau, cần quyết định rõ ở miền nghiệp vụ.

### 8.4. Enum, JSON và value object

`@Enumerated(EnumType.STRING)` giúp lưu tên enum dễ đọc hơn ordinal. Tuy nhiên, **đổi tên hằng enum** có thể khiến dữ liệu cũ không còn ánh xạ được; phải lên kế hoạch migration hoặc dùng mã trạng thái ổn định được chuyển đổi có chủ đích.

Nếu dùng `EnumType.ORDINAL`, thay đổi thứ tự khai báo enum có thể khiến dữ liệu cũ mang nghĩa sai. Đây là lý do cần rất cẩn thận với lưu enum bằng chỉ số.

Với *value object* như địa chỉ, có thể dùng `@Embeddable` và `@Embedded` để lưu các thuộc tính vào cột của hàng chủ:

~~~java
@Embeddable
public class AddressValue {
    @Column(name = "street")
    private String street;

    @Column(name = "city")
    private String city;

    protected AddressValue() {}

    public AddressValue(String street, String city) {
        this.street = street;
        this.city = city;
    }
}
~~~

~~~java
@Embedded
private AddressValue shippingAddress;
~~~

Đây là minh họa cục bộ. Khi một entity có hai địa chỉ (giao hàng/thanh toán) cần `@AttributeOverrides` hoặc thiết kế ánh xạ khác để tránh xung đột tên cột.

JSON/JSONB có thể hữu ích cho trường linh hoạt, nhưng không phải câu trả lời mặc định cho mọi mối quan hệ. Nếu thuộc tính cần query, JOIN, ràng buộc, thống kê và tiến hóa schema rõ ràng, hãy cân nhắc mô hình quan hệ bình thường trước.

## 9. Kế thừa Java không tương đương kế thừa bảng

Java cho phép:

~~~text
Payment
  |- CardPayment
  |- BankTransfer
~~~

Database quan hệ không có một cơ chế đa hình tương đương class hierarchy cho mọi hệ quản trị. ORM thường cung cấp các chiến lược:

| Chiến lược | Cách lưu khái quát | Đánh đổi |
|---|---|---|
| `SINGLE_TABLE` | Các subtype ở cùng một bảng, có discriminator | Truy vấn đa hình đơn giản hơn, nhưng nhiều cột chỉ dùng cho subtype và `NULL` |
| `JOINED` | Bảng cha + bảng cho từng subtype | Chuẩn hóa hơn, nhưng query có thể cần JOIN |
| `TABLE_PER_CLASS` | Mỗi concrete subclass có bảng riêng | Truy vấn đa hình có thể cần UNION và khó tối ưu tùy provider |

Không nên chọn chỉ vì sơ đồ class đẹp. Cần xem truy vấn chính, ràng buộc dữ liệu, khả năng migration, số subtype và tải thực tế.

Trong nhiều hệ thống, **composition hoặc enum trạng thái + value object** có thể đơn giản hơn inheritance. Nhưng nếu subtype thật sự có hành vi và bất biến khác nhau, inheritance có thể có ý nghĩa. Quyết định thuộc mô hình nghiệp vụ và truy vấn, không phải bản thân ORM.

## 10. Transaction, dirty checking và kiểm soát đồng thời

### 10.1. ORM không thay thế transaction

Nếu service thực hiện:

~~~text
Đọc đơn -> thay trạng thái -> cập nhật tồn kho -> ghi audit
~~~

mà mỗi repository dùng transaction riêng, thất bại ở bước cuối vẫn có thể để lại dữ liệu commit một phần. ORM ánh xạ object thành SQL, **không xác định tự động ranh giới nguyên tử của nghiệp vụ**.

Với Spring, thường đặt transaction ở application service:

~~~java
@Service
public class ConfirmOrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public ConfirmOrderService(
            OrderRepository orders, InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirm(long orderId) {
        PurchaseOrderEntity order = orders.loadForBusinessOperation(orderId);
        int reserved = inventory.reserveFor(order);
        if (reserved != 1) {
            throw new IllegalStateException("Insufficient inventory");
        }
        order.confirm();
        // Entity đang managed: provider flush các thay đổi khi thích hợp.
    }
}
~~~

Đây là **khung thiết kế**, cần định nghĩa repository, method `confirm()` và các bất biến miền. Để các thay đổi commit/rollback cùng nhau, tất cả phải tham gia đúng một transaction manager và cùng phạm vi tài nguyên có khả năng giao dịch. Annotation không tự biến hai database hay message broker thành một transaction.

### 10.2. Optimistic locking với `@Version`

Hai transaction có thể tải cùng hàng `purchase_orders.id = 42` khi `version = 7`:

~~~text
T1 đọc (status=CREATED, version=7)
T2 đọc (status=CREATED, version=7)
T1 đổi status=CONFIRMED, commit -> version thành 8
T2 đổi status=CANCELLED, cố commit theo version=7 -> conflict
~~~

Với `@Version`, provider thường tạo câu UPDATE có điều kiện phiên bản tương tự:

~~~sql
UPDATE purchase_orders
SET status = 'CONFIRMED',
    version = 8
WHERE id = 42
  AND version = 7;
~~~

Câu SQL chỉ để **minh họa ý tưởng**; SQL thực, số lần cập nhật và thời điểm version tăng phụ thuộc provider. Nếu không có hàng nào khớp version cũ, JPA có thể ném `OptimisticLockException` hoặc framework có thể chuyển thành loại ngoại lệ tương ứng. Transaction phải được xử lý rollback; nếu nghiệp vụ cho phép, lần retry phải đọc lại dữ liệu và đánh giá lại quyết định.

`@Version` bảo vệ các cập nhật entity mà provider thực thi với cơ chế version phù hợp; nó **không tự giải quyết** những bất biến liên hàng hoặc mọi câu SQL update chạy bên ngoài ORM.

### 10.3. Bulk update và native SQL cần được xem riêng

JPQL bulk update/delete hoặc SQL native có thể cập nhật trực tiếp dữ liệu mà không đi qua dirty checking và vòng đời entity như khi sửa một managed entity. Persistence context có thể còn giữ đối tượng **cũ**, và bulk operation có thể không tự tăng/cân nhắc version theo cách của entity update thông thường.

Sau một bulk update, có thể cần `flush` trước và `clear`/`refresh` theo đúng quy tắc của provider, cũng như thiết kế version/concurrency cho câu SQL. Không dùng `@Version` như bằng chứng rằng tất cả đường ghi ngoài ORM sẽ được kiểm soát tự động.

### 10.4. Cascade không tạo transaction mới

`CascadeType.PERSIST` hoặc `ALL` quy định **lan truyền thao tác entity**. Nó không có nghĩa là mỗi child có transaction riêng và cũng không thay thế `commit/rollback`.

Ví dụ `persist(order)` cùng cascade có thể ghi các `order_items` trong **một transaction**; nếu một dòng vi phạm `UNIQUE (order_id, sku)` thì transaction có thể thất bại và các ghi trước rollback theo quy tắc DB. Cascade **không hủy bỏ ràng buộc DB**.

## 11. Truy vấn theo nhu cầu sử dụng, không theo hình dạng object graph

### 11.1. Entity không nhất thiết là DTO API

Nếu màn hình chỉ cần ID đơn, tên khách hàng và tổng tiền, tải cả entity đơn và tất cả collection có thể lãng phí. Có thể dùng DTO projection:

~~~java
public record OrderSummary(
    Long orderId,
    String customerName,
    BigDecimal totalAmount
) {}
~~~

~~~java
List<OrderSummary> summaries = entityManager.createQuery(
    """
    select new com.example.OrderSummary(
        o.id, c.displayName, o.totalAmount
    )
    from PurchaseOrderEntity o
    join o.customer c
    where o.status = :status
    """,
    OrderSummary.class
).setParameter("status", OrderStatus.CONFIRMED)
 .getResultList();
~~~

Tên package `com.example.OrderSummary` chỉ mang tính minh họa; JPQL constructor expression cần tên class/constructor phù hợp với dự án. Việc projection giúp rõ dữ liệu cần đọc và giảm gắn kết tầng API với lifecycle của entity.

### 11.2. Query SQL vẫn có chi phí và cần chỉ mục

ORM sinh SQL không miễn phí. Một truy vấn có `WHERE customer_id = ? ORDER BY id DESC LIMIT 20` vẫn cần cân nhắc chỉ mục, độ chọn lọc, số dòng, JOIN và kế hoạch thực thi.

Các bước thực tế:

1. Thu thập SQL/JPQL thật của một API có vấn đề hiệu năng.
2. Xác định số query và số hàng trả về, có N+1 hoặc tải dư quan hệ không.
3. Đo kế hoạch bằng công cụ DBMS như `EXPLAIN (ANALYZE, BUFFERS)` trên PostgreSQL ở môi trường phù hợp.
4. Điều chỉnh fetch plan, projection, index hoặc chia nhỏ công việc theo độ ưu tiên.
5. Kiểm tra lại độ trễ p95/p99, CPU/I/O DB, thời gian giữ connection và correctness.

**Không sửa N+1 chỉ bằng cách đặt mọi quan hệ thành EAGER**: điều đó có thể tạo đồ thị dữ liệu lớn, nhiều JOIN không cần thiết hoặc N+1 ở chỗ khác. Fetch strategy nên là quyết định theo use case.

## 12. Schema migration và hợp đồng dữ liệu

### 12.1. Annotation không thay thế quản lý schema

ORM có thể hỗ trợ tự tạo/cập nhật schema trong môi trường phát triển, nhưng production cần quy trình migration có kiểm soát. Ví dụ:

~~~text
Phiên bản 1:
  purchase_orders.status VARCHAR(24)

Phiên bản 2:
  thêm purchase_orders.currency CHAR(3) NOT NULL
~~~

Thêm ngay cột `NOT NULL` lên bảng đã có hàng có thể thất bại hoặc cần giá trị mặc định/backfill. Một quy trình thường an toàn hơn:

1. **Expand:** thêm cột dưới hình thức tương thích với ứng dụng cũ, nếu có thể.
2. **Backfill:** cập nhật dữ liệu hiện tại, giới hạn tải và kiểm tra chất lượng.
3. **Deploy:** cho ứng dụng mới ghi/đọc trường phù hợp với cả giai đoạn chuyển tiếp.
4. **Contract:** sau khi dữ liệu và mọi instance ứng dụng sẵn sàng, siết `NOT NULL`, loại bỏ mapping/cột cũ.

Chi tiết DDL, lock và khả năng chạy online phụ thuộc DBMS. Không nên mặc định `schema auto-update` của ORM tự chọn thứ tự chuyển đổi an toàn.

### 12.2. Ràng buộc database vẫn là hàng rào cuối

Mã Java có thể kiểm tra `quantity > 0`, nhưng một batch import, migration, SQL trực tiếp hoặc dịch vụ khác cũng có thể ghi dữ liệu. Các quy tắc có thể thực thi ở DB cần được biểu diễn bằng:

- `PRIMARY KEY` và `UNIQUE` cho danh tính/duy nhất.
- `FOREIGN KEY` cho tham chiếu.
- `NOT NULL` và `CHECK` cho các điều kiện phù hợp.
- Các chính sách transaction/locking phù hợp cho bất biến cần đồng thời.

ORM và database **cùng bảo vệ tính đúng đắn**, nhưng ở các lớp khác nhau. Khi ràng buộc DB báo lỗi, service phải phân loại ngoại lệ theo DBMS/driver, rollback đúng transaction, không coi mọi vi phạm là lỗi tạm thời đáng retry.

### 12.3. Mô hình object có thể thay đổi nhanh hơn schema

Đổi tên field Java chưa chắc phải đổi tên cột; có thể duy trì ánh xạ bằng `@Column(name=...)`. Ngược lại, đổi tên/độ dài/kiểu cột SQL có thể ảnh hưởng nhiều client và dữ liệu đã lưu.

Hãy có hợp đồng ánh xạ rõ ràng, kiểm thử migration và dữ liệu cũ, tránh coupling không cần thiết giữa tên class và tên bảng/cột. Đây là một phần của tiến hóa schema bền vững, không chỉ là thao tác refactor Java.

## 13. Khi nào ORM phù hợp, khi nào cần SQL rõ ràng?

| Nhu cầu | ORM/JPA có thể phù hợp | Khi nên cân nhắc cách khác |
|---|---|---|
| CRUD có domain entity và quy tắc vòng đời | Có identity map, change tracking, mapping quan hệ | Domain rất đơn giản hoặc cần ít trừu tượng |
| Nhiều association có quản lý aggregate | Cascade và lazy/eager theo nhu cầu | Object graph quá rộng, truy vấn cần tối ưu đặc thù |
| Danh sách API đọc ít cột | DTO projection qua JPQL/Criteria | SQL chuyên biệt/DSL dễ kiểm soát hơn |
| Báo cáo tổng hợp nhiều bảng | JPQL/Criteria có thể đáp ứng một phần | SQL thuần/DSL với CTE, window function hoặc tính năng vendor |
| Batch cập nhật hàng triệu bản ghi | Bulk operations nếu quản lý context đúng | JDBC batch/SQL bulk để tránh tạo hàng triệu object |
| Tính di động giữa DBMS | JPA tạo một lớp trừu tượng chung | Khác biệt DB vẫn tồn tại về isolation, locking, SQL, data types |
| Tối ưu query plan đặc biệt | Có thể dùng native query | JDBC, jOOQ hoặc thư viện SQL-centric có thể rõ ràng hơn |
| Cần transaction phức tạp | Dùng transaction manager cùng ORM | Nhiều nguồn tài nguyên cần chiến lược phối hợp riêng |

**JDBC** cho quyền kiểm soát SQL và lifecycle connection trực tiếp nhưng cần tự map result set, transaction và nhiều chi tiết khác. **MyBatis** hoặc các mapper SQL-centric giúp giữ SQL rõ ràng cùng cơ chế ánh xạ; **jOOQ** cung cấp DSL mạnh cho SQL (tùy cấu hình/phiên bản). **Jakarta Persistence/Hibernate** phù hợp khi lợi ích identity management, object mapping và unit of work vượt chi phí trừu tượng.

Không cần chọn duy nhất một công cụ cho mọi use case. Có thể dùng ORM cho phần ghi nghiệp vụ, projection/SQL trực tiếp cho báo cáo, miễn là ranh giới transaction, first-level cache và đường ghi đồng thời được thiết kế nhất quán.

## 14. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Coi entity Java là bản sao y nguyên của hàng DB | Bỏ qua lifecycle, proxy, cache và transaction | Phân biệt model miền, entity persistence và schema |
| Trộn tham chiếu object với khóa ngoại | Quan hệ hai chiều không đồng bộ | Chỉ định owning side và dùng helper method |
| Dùng `equals/hashCode` phụ thuộc ID chưa cấp | Hash collection hoạt động sai sau persist | Thiết kế identity/equality có xét lifecycle |
| Đặt mọi quan hệ `EAGER` | Tải dữ liệu thừa, JOIN phình to hoặc N+1 | Fetch theo use case bằng projection/entity graph |
| Trả entity trực tiếp ra JSON API | Lazy loading ngoài transaction, vòng tham chiếu | Dùng DTO rõ hợp đồng dữ liệu |
| Gọi `persist()` rồi nghĩ DB đã commit | Sai ranh giới atomicity | Phân biệt persist, flush, commit |
| Sửa entity detached rồi mong ORM tự lưu | Thay đổi không được ghi | Quản lý persistence context/merge rõ ràng |
| Dùng cascade remove cho mọi quan hệ | Xóa nhầm đối tượng có vòng đời độc lập | Thiết kế ownership theo nghiệp vụ |
| Dùng `double` cho tiền | Sai số biểu diễn và phép tính | `BigDecimal` + NUMERIC, quy định scale/rounding |
| Dùng `EnumType.ORDINAL` rồi sắp lại enum | Dữ liệu cũ đổi nghĩa | Mã trạng thái ổn định, migration |
| Tin `@Version` bảo vệ mọi SQL ghi | Bulk SQL có thể bỏ qua version check | Thiết kế concurrency cho mọi đường ghi |
| Dùng ORM auto-update schema ở production | Migration thiếu kiểm soát/khó rollback | Migration phiên bản có expand/backfill/contract |

## 15. Bài tập tự kiểm tra

### Bài 1. Khác biệt identity

Hai transaction riêng tải `CustomerEntity` có `id = 7`. Một object ở transaction A và object khác ở B. Vì sao `a == b` có thể false dù cùng hàng DB?

**Gợi ý:** `==` kiểm tra cùng tham chiếu Java, không kiểm tra khóa chính. Identity map của JPA có phạm vi persistence context, không phải toàn JVM.

### Bài 2. Owning side của quan hệ

`OrderItemEntity` có `@ManyToOne` với `@JoinColumn(name = "order_id")`; `PurchaseOrderEntity` có `@OneToMany(mappedBy = "order")`. Nếu chỉ thêm item vào collection nhưng không gán `item.order`, điều gì có thể sai?

**Gợi ý:** Phía sở hữu quan hệ chưa có khóa ngoại. Cần cập nhật cả hai phía trong bộ nhớ hoặc thiết kế quan hệ một chiều rõ ràng.

### Bài 3. N+1 queries

Service tải 100 đơn rồi lặp qua từng đơn để lấy tên khách hàng. SQL log cho thấy 1 query lấy orders và gần 100 query lấy customers. Giải pháp nào phù hợp nếu API chỉ trả ID đơn, tên khách và tổng tiền?

**Gợi ý:** DTO projection với JOIN để lấy đúng ba cột; cũng có thể cân nhắc fetch join/entity graph nếu thật sự cần entity. Đo SQL thật sau thay đổi.

### Bài 4. Flush và commit

`entityManager.persist(order)` rồi `flush()` đã phát SQL INSERT, sau đó service ném lỗi và transaction rollback. Có phải order đã tồn tại bền vững không?

**Gợi ý:** Không. Flush đồng bộ SQL trong transaction; chỉ commit thành công mới hoàn tất thay đổi theo hợp đồng DBMS.

### Bài 5. Đơn hàng bị cập nhật đồng thời

T1 và T2 cùng tải đơn ở version 3. T1 xác nhận và commit làm version tăng. T2 cố hủy theo version cũ. `@Version` giúp gì?

**Gợi ý:** Provider có thể phát hiện update không khớp version và báo optimistic locking conflict; service cần rollback/đọc lại trước khi quyết định retry.

### Bài 6. Collection có thứ tự

UI yêu cầu hiện dòng hàng theo thứ tự người dùng đã kéo thả. Java đang dùng `List`, database chỉ có bảng `order_items` không có cột vị trí. Kết quả truy vấn có bảo đảm thứ tự không?

**Gợi ý:** Không. Cần một cột biểu diễn vị trí và ánh xạ/quy tắc `ORDER BY` phù hợp, hoặc cơ chế `@OrderColumn` khi thích hợp.

### Bài 7. Thay đổi enum

Bảng lưu `status = 'CONFIRMED'` thông qua `EnumType.STRING`. Developer đổi enum `CONFIRMED` thành `APPROVED` mà không migration. Nguy cơ?

**Gợi ý:** Dữ liệu cũ có thể không còn ánh xạ được. Cần kế hoạch tương thích/migration hoặc ánh xạ mã ổn định.

### Bài 8. Bulk update bên ngoài ORM

Ứng dụng tải entity vào persistence context, sau đó chạy một native SQL cập nhật bảng đó. Khi đọc lại object managed trong cùng context, giá trị có chắc phản ánh thay đổi vừa ghi không?

**Gợi ý:** Không. Cache cấp persistence context có thể còn dữ liệu cũ; cần flush/clear/refresh thích hợp và thiết kế version/concurrency khi trộn đường ghi.

### Bài 9. Kế thừa trong domain

Java có ba subclass của `Payment`. Có bắt buộc tạo một bảng cho mỗi subclass?

**Gợi ý:** Không. Có chiến lược single table, joined, table per class hoặc composition; chọn theo truy vấn, ràng buộc và tiến hóa schema.

### Bài 10. Trách nhiệm của ORM

Một service dùng ORM đúng mọi annotation nhưng hai repository tự commit riêng cho thao tác chuyển tiền. Có bảo đảm trừ và cộng được commit cùng nhau không?

**Gợi ý:** Không. ORM xử lý ánh xạ, không tự đoán transaction boundary nghiệp vụ. Application service/transaction manager phải điều phối một transaction có phạm vi phù hợp.

## 16. Ghi nhớ

- **Đối tượng và quan hệ là hai mô hình khác nhau.** ORM nối chúng qua ID, khóa ngoại, mapping và persistence context, nhưng không xóa khác biệt về identity, collection, null, kế thừa, kiểu dữ liệu và vòng đời.
- **Entity không phải chỉ là POJO được lưu tự động.** Managed/detached, dirty checking, flush, commit và proxy/lazy loading quyết định khi nào SQL chạy và khi nào thay đổi thực sự bền vững.
- **Quan hệ cần định nghĩa ownership rõ ràng.** Khóa ngoại, mappedBy, cascade và orphan removal phải khớp vòng đời nghiệp vụ, tránh xóa/ghi thiếu dữ liệu.
- **Fetch là quyết định hiệu năng.** Đo N+1, chọn projection hoặc fetch plan theo từng use case, tránh trả entity graph vô hạn qua API.
- **Không bỏ qua DBMS.** Ràng buộc, index, transaction, isolation, optimistic locking, query plan và schema migration vẫn cần được thiết kế/đo riêng.
- **ORM là công cụ, không phải kiến trúc mặc định cho mọi câu SQL.** Kết hợp JPA với SQL-centric access khi phù hợp, nhưng thống nhất transaction và concurrency trên mọi đường ghi.

Một lớp persistence Java bền vững không bắt đầu từ số lượng annotation mà từ sự hiểu biết chính xác về **đối tượng trong bộ nhớ, dữ liệu trong bảng, ranh giới transaction và chi phí truy vấn thực tế**. Khi những khác biệt mô hình được giải quyết có chủ đích, ORM mới phát huy vai trò giảm mã lặp mà không che khuất tính đúng đắn và hiệu năng của cơ sở dữ liệu.
