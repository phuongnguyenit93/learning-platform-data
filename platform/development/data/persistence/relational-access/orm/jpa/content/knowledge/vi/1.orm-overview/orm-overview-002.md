# Khác biệt giữa mô hình đối tượng và mô hình dữ liệu quan hệ

Khi viết ứng dụng Java, ta thường mô tả nghiệp vụ bằng **đối tượng**: một `PurchaseOrder` giữ tham chiếu tới `Customer` và chứa danh sách `OrderLine`. Nhưng cơ sở dữ liệu quan hệ lưu thông tin bằng **bảng, hàng, cột, khóa chính và khóa ngoại**. Cả hai cùng biểu diễn một nghiệp vụ, song chúng có những giả định rất khác nhau về danh tính, quan hệ, cách truy cập và vòng đời dữ liệu.

Sự khác biệt này thường được gọi là **object–relational impedance mismatch** (độ lệch giữa mô hình đối tượng và mô hình quan hệ). Hiểu nó là nền tảng để sử dụng ORM và JPA đúng cách: ORM giúp ánh xạ và đồng bộ hai cách biểu diễn, nhưng không làm các khác biệt về cấu trúc, truy vấn và giao dịch biến mất.

## 1. Hai mô hình nhìn cùng một nghiệp vụ như thế nào?

Giả sử hệ thống bán hàng cần lưu đơn hàng. Trong mã Java, ta muốn thao tác theo ngôn ngữ nghiệp vụ:

```java
PurchaseOrder order = ...;
Customer customer = order.getCustomer();

for (OrderLine line : order.getLines()) {
    System.out.println(line.getProductSku() + ": " + line.getQuantity());
}
```

Ở góc nhìn đối tượng, đơn hàng là một nút trong **đồ thị đối tượng**. Ta đi từ đối tượng này đến đối tượng khác bằng tham chiếu hoặc qua collection:

```text
PurchaseOrder #500
  ├── customer ────────> Customer #1 ("An")
  ├── status: CREATED
  └── lines
       ├── OrderLine #900 ("BOOK-01", quantity = 2)
       └── OrderLine #901 ("PEN-02",  quantity = 1)
```

Cơ sở dữ liệu quan hệ lưu cùng thông tin như sau:

**Bảng `customers`**

| id (PK) | full_name |
| --- | --- |
| 1 | An |

**Bảng `orders`**

| id (PK) | customer_id (FK) | status |
| --- | --- | --- |
| 500 | 1 | CREATED |

**Bảng `order_lines`**

| id (PK) | order_id (FK) | product_sku | quantity |
| --- | --- | --- | --- |
| 900 | 500 | BOOK-01 | 2 |
| 901 | 500 | PEN-02 | 1 |

Không có cột nào trong `orders` thực sự *chứa đối tượng* `Customer` hoặc *chứa danh sách* `OrderLine`. Cơ sở dữ liệu lưu các **giá trị khóa**, và ứng dụng phải sử dụng truy vấn để kết hợp các hàng tương ứng.

Ví dụ, để lấy đơn hàng cùng khách hàng và các dòng hàng bằng SQL:

```sql
SELECT o.id AS order_id,
       c.full_name,
       l.product_sku,
       l.quantity
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
JOIN order_lines AS l ON l.order_id = o.id
WHERE o.id = 500;
```

Truy vấn tạo ra **hai hàng kết quả**, vì đơn hàng có hai dòng hàng. Trong Java, ta thường muốn **một** đối tượng `PurchaseOrder` với collection gồm hai phần tử. Việc tái tạo cấu trúc đối tượng từ kết quả quan hệ là một phần công việc của ORM.

## 2. So sánh các khái niệm cốt lõi

| Góc nhìn | Mô hình đối tượng (Java) | Mô hình quan hệ (SQL) |
| --- | --- | --- |
| Đơn vị mô tả | Class, interface, object | Table, row, column |
| Danh tính | Tham chiếu đối tượng; có thể thêm ID nghiệp vụ | Primary key xác định duy nhất một hàng |
| Trạng thái | Field và thuộc tính trong bộ nhớ | Giá trị lưu trong các cột |
| Quan hệ | Tham chiếu và collection | Foreign key, bảng nối và phép `JOIN` |
| Hành vi | Method, đóng gói, đa hình | Ràng buộc, truy vấn, trigger/procedure nếu có |
| Kế thừa | `extends`, `implements`, phương thức ảo | Không có quan hệ kế thừa class tương đương trực tiếp trong bảng thông thường |
| Truy cập | Điều hướng qua `object.field` hoặc getter | Truy vấn theo tập hợp với `SELECT`, `JOIN`, `WHERE` |
| Thời gian tồn tại | Object có thể được tạo và thu gom trong tiến trình | Hàng được lưu bền vững qua nhiều phiên chạy ứng dụng |
| Thay đổi | Gán field, gọi method, thay đổi collection | `INSERT`, `UPDATE`, `DELETE` trong transaction |
| Quy tắc toàn vẹn | Validation và bất biến nghiệp vụ trong Java | `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, `CHECK`, transaction |

Bảng này là phép đối chiếu để dễ học, **không phải quy tắc “một class luôn bằng một table”**. Một class có thể được ánh xạ vào nhiều bảng; nhiều class có thể dùng chung một bảng; và có những class như DTO hoặc service hoàn toàn không cần ánh xạ vào cơ sở dữ liệu.

## 3. Danh tính đối tượng khác khóa chính

### 3.1. Một hàng có thể tương ứng với nhiều Java object ở các thời điểm khác nhau

Trong Java, `a == b` kiểm tra hai biến có trỏ tới cùng một object hay không. `a.equals(b)` phụ thuộc cách class định nghĩa sự bằng nhau. Trong database, hai lần truy vấn hàng có khóa chính `500` vẫn nói tới cùng một **bản ghi logic**, dù dữ liệu được đọc ở thời điểm khác nhau.

```java
PurchaseOrder a = entityManager1.find(PurchaseOrder.class, 500L);
PurchaseOrder b = entityManager2.find(PurchaseOrder.class, 500L);

// Hai EntityManager/persistence context khác nhau:
// a và b có thể là hai Java object khác nhau,
// mặc dù cùng đại diện cho hàng orders.id = 500.
```

JPA cung cấp **persistence context** để theo dõi entity. Trong *cùng một persistence context*, một identity entity nhất định được biểu diễn bằng một managed instance, giúp tránh tạo nhiều bản sao managed mâu thuẫn của cùng một hàng. Nhưng khi entity trở thành `detached`, hoặc được tải trong context khác, ta không thể dựa vào `==` để so sánh hai bản ghi.

Viết `equals()`/`hashCode()` cho JPA entity cần cân nhắc trạng thái chưa có ID, ID sinh khi lưu, proxy và collection kiểu `Set`. Không nên mặc định lấy tất cả field có thể thay đổi làm tiêu chí định danh. Ngược lại, **value object** như `Money` hoặc `Address` thường được so sánh theo các giá trị cấu thành, vì chúng không có identity độc lập như entity.

### 3.2. Vòng đời khác nhau

Một object Java có thể tồn tại trước khi có hàng SQL; cũng có thể tiếp tục tồn tại sau khi phiên làm việc với database đã đóng. JPA phân biệt các trạng thái thường gặp:

```text
new / transient --persist()--> managed --detach()/clear()/close()--> detached
                         │
                         ├── thay đổi field --> được theo dõi để ghi khi flush
                         └── remove() --> removed --> xóa khi đồng bộ DB
```

- **New/transient:** object đã được tạo nhưng chưa thuộc persistence context.
- **Managed:** JPA theo dõi entity và các thay đổi trong phạm vi persistence context.
- **Detached:** object còn trong bộ nhớ nhưng JPA không tiếp tục tự theo dõi thay đổi trên instance đó.
- **Removed:** entity được đánh dấu xóa và sẽ đồng bộ thao tác xóa với database.

Vì thế, `new PurchaseOrder(...)` chưa tương đương `INSERT`, cũng như gán `order.status = PAID` không nhất thiết lập tức phát `UPDATE`.

## 4. Quan hệ đối tượng khác khóa ngoại và phép JOIN

### 4.1. Tham chiếu không phải foreign key

Trong Java, `order.getCustomer()` trả về tham chiếu tới `Customer`. Trong SQL, cột `orders.customer_id = 1` chỉ là **một giá trị**. Ràng buộc `FOREIGN KEY` đảm bảo giá trị đó trỏ tới hàng hợp lệ (theo chính sách ràng buộc của DB), nhưng không tự tạo object Java hay quyết định khi nào tải dữ liệu.

Điểm khác biệt đáng nhớ:

- Đối tượng diễn đạt **điều hướng**: từ đơn hàng sang khách hàng.
- Database diễn đạt **quan hệ dữ liệu**: tập hàng `orders` nối với tập hàng `customers` theo điều kiện khóa.
- Trong database, ta có thể truy vấn theo cả hai chiều mà không cần khai báo collection ở cả hai phía trong class Java.

Trong JPA, `@ManyToOne` và `@JoinColumn` thường mô tả phía giữ foreign key. Nếu có ánh xạ hai chiều, `mappedBy` chỉ ra phía ngược lại; việc thay đổi collection phía ngược **không tự bảo đảm** foreign key được cập nhật đúng nếu phía sở hữu không được đồng bộ.

### 4.2. Collection không phải một cột bảng

`List<OrderLine>` cho phép một object giữ nhiều phần tử. Trong lược đồ quan hệ chuẩn hóa, mỗi `OrderLine` là một hàng trong `order_lines` có `order_id` trỏ về `orders`.

Một số khác biệt nhỏ nhưng quan trọng:

- Collection Java có thể có thứ tự; hàng trong bảng **không có thứ tự mặc định**. Muốn thứ tự ổn định cần cột vị trí, `ORDER BY`, hoặc ánh xạ thứ tự phù hợp như `@OrderColumn`.
- `Set` trong Java dựa vào quy tắc `equals()` và `hashCode()`; tính duy nhất trong DB dựa vào `PRIMARY KEY`/`UNIQUE`.
- Quan hệ nhiều-nhiều thường cần **bảng nối**, chẳng hạn `student_courses(student_id, course_id)`. Nếu quan hệ mang thuộc tính như `enrolled_at` hay `grade`, nên cân nhắc mô hình hóa chính bản ghi nối thành entity.

### 4.3. Một đồ thị object không đồng nghĩa với một lần truy vấn

`order.getCustomer().getFullName()` trông như truy cập field bình thường. Nhưng khi `customer` được tải trễ, JPA provider có thể phải thực hiện thêm truy vấn. Điều này giải thích vì sao cùng một đoạn mã Java có thể có chi phí I/O rất khác nhau tùy truy vấn và chiến lược tải quan hệ.

## 5. Đóng gói và kế thừa không xuất hiện trực tiếp trong bảng

### 5.1. Hành vi thuộc về object; bảng chủ yếu lưu trạng thái

Class có thể bảo vệ bất biến nghiệp vụ bằng method:

```java
public void changeQuantity(int newQuantity) {
    if (newQuantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }
    this.quantity = newQuantity;
}
```

Database cũng cần ràng buộc tương ứng để bảo vệ dữ liệu trước thao tác từ nhiều ứng dụng hoặc script:

```sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
```

Hai lớp quy tắc phục vụ hai mục đích: object thể hiện và thực thi hành vi nghiệp vụ một cách dễ dùng trong Java; database bảo vệ tính toàn vẹn của dữ liệu được chia sẻ. **Chỉ có validation ở Java không đủ** nếu hệ thống còn đường ghi dữ liệu khác.

### 5.2. Kế thừa không có bản sao hoàn toàn tương ứng trong SQL

Ví dụ Java:

```java
abstract class PaymentMethod { /* ... */ }
class CardPayment extends PaymentMethod { /* ... */ }
class BankTransfer extends PaymentMethod { /* ... */ }
```

Các bảng quan hệ không tự hiểu `extends` hay việc gọi method đa hình. JPA có thể ánh xạ một hệ phân cấp entity bằng một trong các chiến lược phổ biến:

| Chiến lược | Cách lưu | Đánh đổi thường gặp |
| --- | --- | --- |
| `SINGLE_TABLE` | Cả hệ phân cấp vào một bảng, có cột phân biệt kiểu | Truy vấn đơn giản hơn; nhiều cột không áp dụng cho mọi subtype và có thể `NULL` |
| `JOINED` | Bảng cha chứa thuộc tính chung; bảng con chứa thuộc tính riêng | Chuẩn hóa tốt hơn; tải đối tượng con có thể cần `JOIN` |
| `TABLE_PER_CLASS` | Mỗi class thực thể có bảng chứa các thuộc tính cần thiết | Truy vấn đa hình có thể phức tạp và tốn chi phí hợp tập kết quả |

Đây là **quyết định thiết kế lưu trữ**, không phải phép biến đổi cơ học từ `extends` thành `FOREIGN KEY`. Trong nhiều miền nghiệp vụ, composition hoặc các kiểu quan hệ thông thường phù hợp hơn kế thừa entity.

## 6. Khác biệt về kiểu dữ liệu, `null` và cấu trúc lồng nhau

Java hỗ trợ object lồng nhau, enum, collection, kiểu bất biến và các kiểu miền nghiệp vụ. SQL sử dụng kiểu cột và quy tắc lưu trữ của database. Khi ánh xạ cần xác định rõ cách biểu diễn:

| Java | SQL thường gặp | Điều cần chú ý |
| --- | --- | --- |
| `String` | `VARCHAR`, `TEXT` | Giới hạn độ dài, collation, chuẩn hóa dữ liệu |
| `BigDecimal` | `DECIMAL(p, s)` / `NUMERIC` | Chọn precision và scale cho tiền tệ; tránh `double` cho số tiền chính xác |
| `LocalDate` | `DATE` | Chỉ biểu diễn ngày, không gồm múi giờ |
| `LocalDateTime` | `TIMESTAMP` | Không tự mang thông tin timezone; thống nhất cách diễn giải |
| `Instant` | Kiểu timestamp phù hợp DB/provider | Quy ước UTC và cách driver/provider chuyển đổi |
| `enum` | Cột chuỗi hoặc số | `EnumType.STRING` thường ổn định hơn ordinal khi thay đổi thứ tự enum |
| `Address` là value object | Các cột trong bảng chủ, hoặc bảng riêng | Có thể dùng `@Embeddable`/`@Embedded` cho cấu trúc nhúng |
| `List<T>` | Bảng con / bảng nối | Không mặc nhiên lưu thành một trường kiểu danh sách |

**`null` cũng không hoàn toàn giống nhau.** Trong Java, `null` là giá trị tham chiếu đặc biệt; `int` không thể nhận `null` nhưng `Integer` có thể. Trong SQL, `NULL` biểu thị giá trị chưa biết hoặc không có theo cách thiết kế, và phép so sánh dùng **logic ba giá trị**. Chẳng hạn `column = NULL` không đúng để tìm hàng rỗng; phải dùng `column IS NULL`.

Trong JPA, `optional = false` và `@Column(nullable = false)` mô tả ý định ánh xạ, nhưng hệ thống nên có `NOT NULL`/`FOREIGN KEY` thực sự trong schema. Các ràng buộc database mới bảo đảm nhất quán ngay cả khi dữ liệu được cập nhật ngoài JPA.

## 7. Ví dụ ánh xạ bằng JPA: từ class sang bảng

Để nhìn rõ việc ORM làm, ta ánh xạ ví dụ đơn hàng ở phần đầu. Đây là lược đồ quan hệ rút gọn:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_sku VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_lines_order ON order_lines(order_id);
```

Các đoạn Java dưới đây thuộc **những file riêng**; lược bỏ `import` để tập trung vào ánh xạ. Các annotation như `@Entity`, `@Id`, `@ManyToOne` thuộc `jakarta.persistence` (một số dự án JPA cũ dùng package `javax.persistence`).

**`Customer.java`**

```java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {} // JPA cần constructor không tham số

    public String getFullName() {
        return fullName;
    }
}
```

**`OrderStatus.java`**

```java
public enum OrderStatus {
    CREATED, PAID, CANCELLED
}
```

**`PurchaseOrder.java`**

```java
@Entity
@Table(name = "orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(Long id, Customer customer) {
        this.id = id;
        this.customer = customer;
        this.status = OrderStatus.CREATED;
    }

    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.attachTo(this); // đồng bộ phía sở hữu foreign key
    }
}
```

**`OrderLine.java`**

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_sku", nullable = false, length = 50)
    private String productSku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(Long id, String productSku, int quantity) {
        if (quantity <= 0) throw new IllegalArgumentException("quantity");
        this.id = id;
        this.productSku = productSku;
        this.quantity = quantity;
    }

    void attachTo(PurchaseOrder order) { this.order = order; }
    public String getProductSku() { return productSku; }
    public int getQuantity() { return quantity; }
}
```

Từ ví dụ này có thể đọc trực tiếp quy tắc ánh xạ:

| Annotation | Ý nghĩa đối với hai mô hình |
| --- | --- |
| `@Entity` / `@Table` | Class entity đại diện cho dữ liệu được lưu theo ánh xạ của bảng `customers`, `orders`, `order_lines` |
| `@Id` | Thuộc tính dùng làm định danh entity, ánh xạ tới khóa chính trong ví dụ |
| `@Column` | Field Java được lưu trong cột SQL với các thông tin như tên, độ dài, khả năng `NULL` |
| `@ManyToOne` / `@JoinColumn` | Tham chiếu Java `order.customer`/`line.order` liên hệ với khóa ngoại |
| `@OneToMany(mappedBy = "order")` | Collection `order.lines` là phía đối ứng của quan hệ được sở hữu bởi `OrderLine.order` |
| `cascade = ALL` | Một số thao tác vòng đời JPA trên đơn hàng được lan truyền đến các dòng hàng |
| `orphanRemoval = true` | Dòng hàng bị loại khỏi quan hệ sở hữu có thể được xóa khi đồng bộ persistence context |
| `@Enumerated(EnumType.STRING)` | Enum Java được lưu bằng tên chuỗi như `CREATED`, thay vì vị trí số của enum |

Ví dụ dùng **ID được cung cấp thủ công** để dễ theo dõi khóa chính. Trong dự án thật có thể chọn `@GeneratedValue` cùng sequence/identity tương ứng với cấu hình cơ sở dữ liệu. `cascade` của JPA là quy tắc lan truyền thao tác entity; nó **không đồng nghĩa** với `ON DELETE CASCADE` trong foreign key của SQL.

### Một thao tác ghi từ góc nhìn Java và SQL

Trong môi trường dùng `EntityManager` kiểu *resource-local transaction*, một đoạn code minh họa có thể là:

```java
EntityManager em = ...;
em.getTransaction().begin();

Customer customer = em.find(Customer.class, 1L);
PurchaseOrder order = new PurchaseOrder(500L, customer);
order.addLine(new OrderLine(900L, "BOOK-01", 2));
order.addLine(new OrderLine(901L, "PEN-02", 1));

em.persist(order);
em.getTransaction().commit();
```

Ứng dụng xây **một đồ thị object** và yêu cầu JPA lưu `order`. JPA provider chuyển trạng thái entity thành các thao tác SQL tương ứng, thường gồm một `INSERT` cho `orders` và hai `INSERT` cho `order_lines` (thứ tự và thời điểm phát SQL do provider quyết định theo ràng buộc). Nhờ `cascade`, các `OrderLine` mới cũng được lưu. Dữ liệu `Customer #1` đã có sẵn; ta không cần chèn lại khách hàng.

Trong ứng dụng Spring/Jakarta EE, transaction thường do framework/container quản lý, nên cách bắt đầu transaction sẽ khác. Ví dụ trên chỉ dùng để thấy sự chuyển đổi giữa thao tác trên object và thao tác trên hàng SQL.

## 8. Tải dữ liệu: điều hướng object và truy vấn theo tập hợp

Một câu lệnh SQL có thể xử lý hàng nghìn bản ghi theo tập hợp. Ngược lại, code Java có xu hướng lặp qua từng object và lần lượt gọi getter. Nếu không thiết kế cách tải dữ liệu, sự khác biệt này dễ tạo vấn đề hiệu năng.

Xét đoạn:

```java
List<PurchaseOrder> orders = entityManager
    .createQuery("SELECT o FROM PurchaseOrder o", PurchaseOrder.class)
    .getResultList();

for (PurchaseOrder o : orders) {
    System.out.println(o.getCustomer().getFullName());
}
```

Nếu `customer` được tải trễ, kết quả có 100 đơn hàng và các quan hệ chưa được nạp, provider **có thể** tạo một query lấy danh sách đơn hàng rồi phát thêm nhiều query lấy khách hàng. Tình huống này gọi là **N+1 query problem**. Số query thực tế phụ thuộc số khách hàng khác nhau, cache, batching, fetch strategy và provider.

Nếu nghiệp vụ thực sự cần dữ liệu khách hàng của tất cả đơn hàng, có thể chủ động thiết kế truy vấn:

```java
List<PurchaseOrder> orders = entityManager
    .createQuery(
        "SELECT o FROM PurchaseOrder o JOIN FETCH o.customer",
        PurchaseOrder.class
    )
    .getResultList();
```

`JOIN FETCH` yêu cầu JPA tải quan hệ `customer` cùng kết quả đơn hàng. Với trang danh sách chỉ cần mã đơn và tên khách, một **DTO projection** chọn đúng cột cần dùng đôi khi thích hợp hơn tải cả entity. Với collection một-nhiều, fetch join cũng cần cân nhắc nhân số hàng SQL, phân trang và việc loại trùng root entity.

Chiều ngược lại cũng đáng lưu ý: `FetchType.LAZY` không bảo đảm mọi truy cập an toàn sau khi transaction/persistence context đã kết thúc. Nếu provider chưa tải một quan hệ, đọc nó khi context đóng có thể thất bại (Hibernate thường báo `LazyInitializationException`). Nên xác định dữ liệu cần thiết trong ranh giới transaction, thay vì giả định một đồ thị entity luôn được tải đầy đủ.

## 9. Thay đổi object, transaction và dữ liệu đồng thời

Trong Java, đổi field là thao tác trên bộ nhớ; trong database, thay đổi phải đi qua transaction và tuân thủ ràng buộc, khóa và mức cô lập.

### 9.1. Dirty checking và `flush`

Khi entity đang ở trạng thái managed, JPA provider thường theo dõi thay đổi:

```java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 500L);
// Gọi phương thức nghiệp vụ để đổi trạng thái, ví dụ order.markPaid().
// Tại flush/commit, provider đồng bộ thay đổi phù hợp thành SQL UPDATE.
```

**`flush`** là quá trình đồng bộ thay đổi của persistence context xuống database; **`commit`** quyết định transaction được xác nhận bền vững. `flush` không tự có nghĩa là transaction đã commit và không thể rollback. Thời điểm thực thi SQL có thể khác thời điểm Java gọi setter hoặc `persist()`.

### 9.2. Nhiều object có thể cùng sửa một hàng

Hai người dùng có thể mở `orders.id = 500` ở hai transaction khác nhau. Mỗi người giữ một bản Java object rồi cùng cập nhật. Nếu không có cơ chế kiểm soát, lần ghi sau có thể ghi đè thay đổi của lần trước.

Một cách xử lý phổ biến là **optimistic locking** bằng `@Version`:

```java
@Version
@Column(nullable = false)
private long version;
```

Khi dùng trường này, schema cần có cột `version` phù hợp. Provider kiểm tra version khi cập nhật; nếu bản ghi đã thay đổi, transaction có thể nhận lỗi optimistic lock để ứng dụng xử lý xung đột. Đây là ví dụ cho thấy đồng bộ object không thể tách khỏi các quy tắc transaction và concurrency của database.

### 9.3. Ràng buộc database vẫn là tuyến phòng vệ cuối

Ví dụ, kiểm tra `quantity > 0` trong constructor ngăn tạo `OrderLine` sai qua đường code đó, nhưng không ngăn một script SQL ghi `quantity = -5`. `CHECK (quantity > 0)` trong database bảo vệ dữ liệu đối với mọi đường ghi được thực thi dưới ràng buộc. Tương tự, dùng `FOREIGN KEY`, `UNIQUE` và transaction cho các quy tắc cần nhất quán ở cấp lưu trữ.

## 10. Không ánh xạ máy móc mọi khái niệm Java thành bảng

Khi thiết kế mô hình, nên phân biệt vai trò của từng loại object:

| Loại object | Vai trò | Hướng xử lý với JPA |
| --- | --- | --- |
| **Entity** (`Customer`, `PurchaseOrder`) | Có identity, tồn tại và thay đổi theo thời gian | Thường dùng `@Entity`, `@Id`, mapping quan hệ |
| **Value object** (`Address`, `Money`) | Diễn đạt giá trị, thường bất biến, so sánh theo nội dung | Có thể dùng `@Embeddable`, `@Embedded`, `AttributeConverter`, hoặc mapping thích hợp khác |
| **DTO** (`OrderSummary`) | Mang dữ liệu cho API/màn hình, có thể tổng hợp nhiều nguồn | Thường tạo bằng projection/mapping; không nhất thiết là entity |
| **Service** (`CheckoutService`) | Điều phối use case và quy tắc nghiệp vụ | Không là hàng dữ liệu và không cần ánh xạ thành bảng |

Ví dụ `Address` gồm `street`, `city`, `postalCode` có thể là một value object được nhúng vào các cột trong `customers`:

```java
@Embeddable
public class Address {
    private String street;
    private String city;
    private String postalCode;

    protected Address() {}
}

// Bên trong Customer:
@Embedded
private Address shippingAddress;
```

Đây là trường hợp **hai class Java cùng được lưu trong một hàng**, cho thấy quy tắc class ↔ table không luôn là 1–1. Ngược lại, `PurchaseOrder` và `OrderLine` nên tách vì các dòng hàng có số lượng biến đổi và quan hệ một-nhiều rõ ràng.

Cũng cần phân biệt **thực thể nghiệp vụ** với **cấu trúc dữ liệu phục vụ truy vấn**. Đối tượng miền nghiệp vụ có thể tối ưu cho hành vi như `order.addLine(...)`, còn báo cáo doanh thu có thể cần SQL `GROUP BY` hoặc DTO projection. Không nhất thiết ép toàn bộ nghiệp vụ đọc dữ liệu qua một đồ thị entity duy nhất.

## 11. Các lỗi tư duy phổ biến khi mới học ORM

**“Một class phải có đúng một bảng.”** Sai trong nhiều trường hợp: `@Embedded` có thể gom nhiều class vào một hàng; inheritance có nhiều chiến lược; DTO không cần bảng; một entity có thể liên hệ nhiều bảng.

**“Gọi getter chỉ đọc bộ nhớ.”** Không luôn đúng với entity có quan hệ tải trễ. Một getter có thể kích hoạt truy vấn hoặc gặp lỗi khi context không còn khả dụng.

**“Thêm phần tử vào collection thì khóa ngoại tự luôn đúng.”** Với mapping hai chiều, cần giữ nhất quán cả phía collection và phía sở hữu foreign key. Trong ví dụ, `addLine()` vừa thêm vào `lines` vừa đặt `line.order`.

**“`persist()` có nghĩa dữ liệu đã commit.”** `persist()` đưa entity vào cơ chế quản lý vòng đời. SQL có thể được phát vào thời điểm khác; transaction vẫn có thể rollback.

**“Validation Java thay thế được constraint SQL.”** Không nên. Business validation cho thông báo và hành vi rõ ràng; ràng buộc SQL bảo vệ dữ liệu trước mọi tác nhân ghi.

**“Càng tải nhiều quan hệ bằng EAGER càng dễ.”** Tải trước không có kế hoạch có thể làm truy vấn nặng, tải dữ liệu thừa hoặc phát thêm query. Nên thiết kế fetch plan dựa trên từng use case.

**“Entity hoạt động như object độc lập sau khi rời transaction.”** Một detached entity không còn được tự dirty-check; quan hệ chưa tải có thể không truy cập được. Cần hiểu ranh giới persistence context và cách cập nhật entity an toàn.

## 12. Cách suy nghĩ khi chuyển từ thiết kế hướng đối tượng sang schema quan hệ

Hãy dùng các câu hỏi sau theo thứ tự:

1. **Đối tượng nào có identity riêng?** Xác định entity và khóa chính. Những cấu trúc chỉ mô tả giá trị có thể là value object.
2. **Quan hệ có lực lượng bao nhiêu?** Một-một, một-nhiều, nhiều-nhiều; từ đó xác định foreign key hoặc bảng nối.
3. **Dữ liệu nào cần toàn vẹn ở cấp DB?** Đặt `NOT NULL`, `UNIQUE`, `CHECK`, foreign key và quy tắc transaction phù hợp.
4. **Use case cần đọc dữ liệu theo hình dạng nào?** Chọn entity navigation, fetch join, entity graph, projection hoặc truy vấn tổng hợp theo nhu cầu.
5. **Entity được tạo, sửa và xóa theo vòng đời nào?** Cân nhắc transaction, cascade, orphan removal, version và ranh giới sở hữu dữ liệu.
6. **Mô hình có thể phát triển ra sao?** Đổi class có thể kéo theo migration dữ liệu và schema; đổi schema có thể ảnh hưởng query, index, constraint và mapping.

### Bài tập suy luận ngắn

Một ứng dụng quản lý khóa học có `Student`, `Course` và `Enrollment`. Mỗi sinh viên có thể đăng ký nhiều khóa học; mỗi khóa học có nhiều sinh viên. Đăng ký còn có `enrolledAt` và `finalGrade`.

- **Trong Java:** `Student` có thể giữ collection `Enrollment`; mỗi `Enrollment` tham chiếu một `Course` và mang thông tin điểm/ngày đăng ký.
- **Trong SQL:** tạo `students`, `courses`, `enrollments`; bảng `enrollments` có foreign key `student_id`, `course_id` và hai cột nghiệp vụ `enrolled_at`, `final_grade`. Có thể thêm `UNIQUE(student_id, course_id)` nếu mỗi sinh viên chỉ đăng ký một lần cho một khóa học.
- **Trong JPA:** ánh xạ `Enrollment` thành entity riêng thường dễ mở rộng hơn một `@ManyToMany` thuần túy, vì chính mối quan hệ có trạng thái và vòng đời cần quản lý.

Tình huống này minh họa điểm cốt lõi: **mối quan hệ trong object graph không chỉ là một đường nối kỹ thuật**; khi quan hệ có dữ liệu nghiệp vụ, mô hình quan hệ và mô hình đối tượng cần được thiết kế cùng nhau để phản ánh đúng ý nghĩa của nó.

## Kết luận

**Mô hình đối tượng** tập trung vào object có identity, trạng thái, hành vi, đóng gói và tham chiếu trong bộ nhớ. **Mô hình quan hệ** tập trung vào các tập hàng, khóa, ràng buộc, truy vấn và transaction có khả năng lưu trữ lâu dài. JPA/ORM nối hai thế giới bằng mapping, persistence context, quản lý trạng thái và phát SQL; lập trình viên vẫn phải hiểu cách dữ liệu thật được lưu, truy vấn và cập nhật.

Khi nhìn vào một đoạn code như `order.getLines()`, hãy đồng thời tự hỏi: **collection này được lưu ở bảng nào, nối bằng khóa nào, tải bằng query gì, được thay đổi trong transaction nào và được bảo vệ bằng constraint nào?** Trả lời được những câu hỏi ấy là nền tảng để xây dựng ứng dụng Java dùng ORM/JPA vừa đúng nghiệp vụ, vừa nhất quán và có hiệu năng tốt.
