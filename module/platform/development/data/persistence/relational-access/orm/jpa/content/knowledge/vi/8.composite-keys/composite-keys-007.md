# Định danh dẫn xuất từ entity liên quan trong JPA

## 1. Định danh dẫn xuất là gì?

Trong **Jakarta Persistence (JPA)**, mỗi entity cần có một định danh (*primary key*) để provider phân biệt các bản ghi và quản lý chúng trong persistence context. Khóa chính thông thường có thể do entity tự sở hữu, chẳng hạn `Product.id` kiểu `Long`. Nhưng có những entity mà **toàn bộ hoặc một phần khóa chính được lấy từ khóa của entity khác mà nó tham chiếu**.

Cách tổ chức này gọi là **định danh dẫn xuất** (*derived identity*).

Hai tình huống tiêu biểu:

1. **Khóa chính dùng chung:** bảng `account_profiles` có khóa chính `account_id`, đồng thời `account_id` là khóa ngoại đến `accounts.id`. Một hồ sơ thuộc đúng một tài khoản và có cùng ID với tài khoản đó.
2. **Khóa ghép chứa khóa của entity cha:** dòng đơn hàng được xác định bằng cặp `(order_id, line_no)`. `order_id` đến từ entity `SalesOrder`, còn `line_no` là số thứ tự dòng trong đơn.

Sơ đồ:

```text
accounts                          account_profiles
+----------+                    +----------------+
| id (PK)  |<-------------------| account_id (PK, FK)
| username |                    | display_name   |
+----------+                    +----------------+

sales_orders                      sales_order_lines
+----------+                    +------------------+
| id (PK)  |<-------------------| order_id (PK, FK) |
| customer |                    | line_no  (PK)     |
+----------+                    | quantity         |
                                +------------------+

Khóa chính của dòng đơn = (ID đơn hàng, số thứ tự dòng)
```

Điểm quan trọng là **mối quan hệ tới entity liên quan tham gia cấu thành danh tính** của entity phụ thuộc. Đây là một lựa chọn mô hình dữ liệu: không phải bất kỳ quan hệ `@ManyToOne` hoặc `@OneToOne` nào cũng là định danh dẫn xuất.

Trong JPA, cách ánh xạ được dùng nhiều nhất là:

- **`@EmbeddedId` + `@MapsId`**: tạo đối tượng khóa ghép riêng và cho quan hệ cung cấp một phần/toàn bộ khóa.
- **`@IdClass`**: thể hiện các thành phần khóa trực tiếp trên entity; thành phần khóa có thể là một quan hệ đã được đánh dấu `@Id`.
- **`@Id` + `@MapsId`**: rất thuận tiện khi dependent entity có khóa đơn **dùng chung** với parent entity, điển hình `@OneToOne`.

Bài học dùng API `jakarta.persistence` của Jakarta Persistence hiện đại. Trong các ứng dụng JPA cũ, import có thể là `javax.persistence`. Các ví dụ sử dụng entity và quan hệ theo đặc tả JPA; cú pháp DDL có thể cần điều chỉnh theo hệ quản trị cơ sở dữ liệu.

## 2. Phân biệt định danh độc lập và định danh dẫn xuất

### 2.1. Định danh độc lập

Entity `Comment` có khóa chính riêng `id` và khóa ngoại `post_id`:

```text
comments
+------------------+
| id      (PK)     |
| post_id (FK)     |
| content          |
+------------------+
```

Ánh xạ thường gặp:

```java
@Entity
public class Comment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;

    protected Comment() {}
}
```

`Comment` có `id` độc lập, nên `post_id` **không nằm trong khóa chính**. Dù không có `Post` thì một `Comment` có thể không hợp lệ về mặt nghiệp vụ, nhưng đây vẫn **không phải ánh xạ derived identity**.

### 2.2. Định danh dẫn xuất

Đối với `OrderLine`:

```text
order_lines
+---------------------------+
| order_id (PK, FK)          |
| line_number (PK)           |
| product_name              |
| quantity                  |
+---------------------------+

PRIMARY KEY (order_id, line_number)
FOREIGN KEY (order_id) REFERENCES orders(id)
```

Không có `id` độc lập cho từng dòng. Dòng số 1 của đơn 100 và dòng số 1 của đơn 101 là **hai entity khác nhau**, vì khóa đầy đủ lần lượt là `(100, 1)` và `(101, 1)`.

Nếu trong database đã có `(100, 1)`, không thể thêm một dòng khác có cùng cặp giá trị dù tên sản phẩm khác nhau, vì ràng buộc `PRIMARY KEY` sẽ từ chối.

### 2.3. Một tiêu chí để nhận diện

Hãy hỏi: **Một phần hoặc toàn bộ giá trị khóa chính của entity phụ thuộc có phải được xác định từ khóa của entity khác qua quan hệ không?**

- Nếu **có**, đó là tình huống cần xem xét derived identity.
- Nếu **không**, quan hệ có thể chỉ là một foreign key thông thường.

Derived identity mô tả **cách xây dựng khóa**, không mặc nhiên mô tả cascade, thời điểm load, cách xóa hay có được phép đổi parent. Những cơ chế đó cần được cấu hình hoặc xử lý riêng.

## 3. Nền tảng: khóa ghép trong JPA

### 3.1. Khóa ghép chứa những gì?

Với dòng đơn hàng, ID gồm hai thành phần:

```text
SalesOrderLineId
  orderId: Long
  lineNumber: Integer
```

Điều kiện thông dụng của lớp khóa ghép là:

- Có constructor không tham số với khả năng truy cập phù hợp.
- Hiện thực `Serializable` theo quy định JPA đối với lớp khóa chính.
- Có `equals()` và `hashCode()` nhất quán với phép bằng nhau của các giá trị khóa.
- Những thành phần khóa sử dụng kiểu hợp lệ và tương ứng với mapping entity.
- Khóa là **giá trị ổn định**, tránh sửa sau khi entity đã được quản lý/lưu trữ.

**Hai cơ chế khai báo khóa ghép chuẩn:**

| Cơ chế | Hình dạng entity | Hình dạng lớp khóa |
|---|---|---|
| `@EmbeddedId` | Có một field kiểu ID class, ví dụ `SalesOrderLineId id`. | Lớp `@Embeddable` chứa `orderId`, `lineNumber`. |
| `@IdClass` | Có nhiều thuộc tính `@Id` ngay trên entity. | Lớp khóa chứa thuộc tính **trùng tên** với các thuộc tính ID của entity, có kiểu theo quy tắc của JPA. |

Định danh dẫn xuất có thể được ánh xạ bằng cả hai cơ chế. Phần tiếp theo bắt đầu với `@EmbeddedId` vì nó diễn đạt cặp khóa khá trực quan.

### 3.2. Entity cha phải có khóa hợp lệ

Ví dụ entity cha `SalesOrder`:

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "sales_orders")
@SequenceGenerator(
    name = "sales_order_gen",
    sequenceName = "sales_order_seq",
    allocationSize = 1
)
public class SalesOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "sales_order_gen"
    )
    private Long id;

    @Column(name = "customer_name", nullable = false, length = 120)
    private String customerName;

    protected SalesOrder() {
        // Constructor không tham số cho JPA.
    }

    public SalesOrder(String customerName) {
        if (customerName == null || customerName.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng không hợp lệ");
        }
        this.customerName = customerName;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerName() {
        return customerName;
    }
}
```

Ở đây `SalesOrder` có định danh độc lập `Long id`, do sequence database cấp. Mỗi `SalesOrderLine` có thể dùng giá trị này làm **thành phần khóa** của chính nó.

## 4. Ví dụ trung tâm: `@EmbeddedId` kết hợp `@MapsId`

### 4.1. Tạo lớp khóa ghép `SalesOrderLineId`

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class SalesOrderLineId implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_no")
    private Integer lineNumber;

    protected SalesOrderLineId() {
        // Constructor cho JPA.
    }

    public SalesOrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof SalesOrderLineId that)) {
            return false;
        }
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

Hai phần của khóa:

- `orderId`: ID của `SalesOrder` mà dòng đơn tham chiếu.
- `lineNumber`: số thứ tự dòng **trong một đơn hàng**.

`@Embeddable` ở đây dùng cho một giá trị ID nhúng, không tạo entity độc lập. Không được tự gọi `em.persist(lineId)` vì nó **không phải entity**.

Các trường khóa thường được xem là giá trị bất biến sau khi đã gán. Không nên cung cấp setter công khai cho phép đổi `orderId` hoặc `lineNumber` của một entity đang persistent.

### 4.2. Tạo entity phụ thuộc `SalesOrderLine`

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "sales_order_lines")
public class SalesOrderLine {

    @EmbeddedId
    private SalesOrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "product_name", nullable = false, length = 150)
    private String productName;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    protected SalesOrderLine() {
        // Constructor cho JPA.
    }

    public SalesOrderLine(
            SalesOrder order,
            int lineNumber,
            String productName,
            int quantity
    ) {
        this.order = Objects.requireNonNull(order);
        if (lineNumber <= 0) {
            throw new IllegalArgumentException("Số dòng phải dương");
        }
        if (productName == null || productName.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không hợp lệ");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        // Thành phần orderId sẽ được JPA đồng bộ từ order.id.
        this.id = new SalesOrderLineId(null, lineNumber);
        this.productName = productName;
        this.quantity = quantity;
    }

    public SalesOrderLineId getId() {
        return id;
    }

    public SalesOrder getOrder() {
        return order;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        this.quantity = newQuantity;
    }
}
```

Dòng quan trọng nhất:

```java
@MapsId("orderId")
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private SalesOrder order;
```

Ý nghĩa:

1. `@ManyToOne`: nhiều dòng đơn hàng có thể thuộc cùng một đơn.
2. `@JoinColumn(name = "order_id")`: cột liên kết tới khóa của `SalesOrder`.
3. `@MapsId("orderId")`: **quan hệ `order` cung cấp phần `orderId` của khóa ghép `SalesOrderLineId`**.
4. `@EmbeddedId`: khóa chính của `SalesOrderLine` là toàn bộ cặp `(orderId, lineNumber)`.

Như vậy `order_id` là **một cột vật lý** nhưng đồng thời đóng vai trò **foreign key** và **một phần primary key**. Không cần tạo thêm một cột `sales_order_id` thứ hai chỉ để ánh xạ quan hệ.

### 4.3. Cơ chế `@MapsId("orderId")`

Phần giá trị nằm trong dấu ngoặc của `@MapsId` là **tên thuộc tính trong ID class**, không phải tên SQL column và không phải tên field quan hệ.

```text
SalesOrderLine
   |
   +-- id: SalesOrderLineId
   |       +-- orderId: Long       <---+
   |       +-- lineNumber: Integer    |
   |                                  |
   +-- order: SalesOrder              |
           +-- id: Long --------------+
                @MapsId("orderId")
```

Trong ví dụ:

- `"orderId"` đúng vì `SalesOrderLineId` có field tên `orderId`.
- `"order_id"` **không đúng** ở vị trí này vì đó là tên cột SQL.
- `"order"` không đúng nếu ID class không có thuộc tính `order`.

Khi gán một `SalesOrder` cho `SalesOrderLine.order`, provider có trách nhiệm dùng khóa của parent làm thành phần tương ứng trong derived identity. Thời điểm đồng bộ giá trị này vào đối tượng ID trong bộ nhớ có thể bị trì hoãn đến khi provider thực hiện thao tác persistence/flush cần thiết. Vì vậy không nên đọc `line.getId().getOrderId()` trên object mới và giả định nó đã có giá trị ngay sau constructor.

### 4.4. Quan hệ và khóa ghép có phải khai báo trùng column không?

Hai vị trí sau cùng mô tả cột `order_id`:

```java
// Bên trong SalesOrderLineId:
@Column(name = "order_id")
private Long orderId;

// Bên trong SalesOrderLine:
@MapsId("orderId")
@JoinColumn(name = "order_id")
private SalesOrder order;
```

Đây là mapping có chủ đích: `@MapsId` liên kết thành phần ID với quan hệ tương ứng, tránh coi chúng là hai thuộc tính độc lập cùng ghi một column. Nếu bỏ `@MapsId` trong khi vẫn có cả hai mapping, provider có thể báo **repeated column mapping** hoặc khiến ứng dụng phải tự đồng bộ các giá trị `orderId` và `order.id` một cách mong manh.

## 5. Cấu trúc bảng SQL tương ứng

Ví dụ DDL cho database có hỗ trợ sequence:

```sql
CREATE SEQUENCE sales_order_seq
    START WITH 1
    INCREMENT BY 1;

CREATE TABLE sales_orders (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(120) NOT NULL
);

CREATE TABLE sales_order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    quantity INTEGER NOT NULL,

    CONSTRAINT pk_sales_order_lines
        PRIMARY KEY (order_id, line_no),

    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES sales_orders(id)
);
```

Ví dụ giả sử:

```text
sales_orders
+-----+---------------+
| id  | customer_name |
+-----+---------------+
| 301 | Khách An      |
| 302 | Khách Bình    |
+-----+---------------+

sales_order_lines
+----------+---------+--------------+----------+
| order_id | line_no | product_name | quantity |
+----------+---------+--------------+----------+
| 301      | 1       | Sổ tay       | 2        |
| 301      | 2       | Bút chì      | 5        |
| 302      | 1       | Tập giấy     | 1        |
+----------+---------+--------------+----------+
```

Tập khóa của `sales_order_lines` là:

```text
(301, 1)
(301, 2)
(302, 1)
```

`(301, 1)` và `(302, 1)` không trùng khóa vì khác `order_id`. Trái lại, hai dòng có cùng `(301, 1)` sẽ vi phạm primary key.

Ràng buộc foreign key bảo đảm một `order_id` phải tham chiếu một đơn hàng tồn tại (trừ khi schema được thiết kế khác, nhưng với derived identity mẫu này cột khóa phải có giá trị). Đây là bảo đảm của database, không chỉ của code Java.

## 6. Lưu entity có định danh dẫn xuất

### 6.1. Thứ tự persist entity cha và entity con

Với `SalesOrder` dùng khóa do sequence cấp, ta cần tạo parent rồi tạo các dòng phụ thuộc:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        SalesOrder order = new SalesOrder("Khách An");
        em.persist(order);

        // Bảo đảm provider đã cấp định danh cho parent.
        em.flush();

        SalesOrderLine first = new SalesOrderLine(
                order, 1, "Sổ tay", 2
        );
        SalesOrderLine second = new SalesOrderLine(
                order, 2, "Bút chì", 5
        );

        em.persist(first);
        em.persist(second);

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Ví dụ trên dùng **`RESOURCE_LOCAL`** và giả định `EntityManagerFactory emf` đã được khởi tạo cho persistence unit chứa hai entity. `em.flush()` được dùng để làm rõ bước cấp ID của parent trong ví dụ; nó **không phải commit**. Với provider và chiến lược sinh ID thích hợp, parent có thể đã có ID ngay khi `persist`; do đó không phải luồng nào cũng bắt buộc gọi flush trước khi tạo child.

Chú ý:

- Không cần tự sinh `orderId` trong mã nghiệp vụ bằng `MAX(id) + 1`.
- `SalesOrderLine.order` phải trỏ tới parent phù hợp.
- `SalesOrderLineId.lineNumber` phải được gán, vì JPA chỉ dẫn xuất **`orderId`** từ quan hệ; nó không tự biết số dòng nghiệp vụ.
- `em.persist(line)` không tự tạo `SalesOrder` nếu không có cấu hình cascade tương ứng và parent chưa được quản lý.
- Toàn bộ đơn và dòng nên nằm trong **một transaction** khi nghiệp vụ yêu cầu tính nguyên tử.

### 6.2. Gán ID của parent bằng tay có cần không?

Một cách dễ sai là duy trì hai nguồn dữ liệu:

```java
line.getId().setOrderId(123L);
line.setOrder(otherOrder);
```

Giả sử `otherOrder.id = 999` thì `id.orderId` và `order.id` mâu thuẫn. `@MapsId` được thiết kế để quan hệ cung cấp thành phần ID và tránh sự lệch nhau đó.

Trong constructor ở trên, khóa nhúng được khởi tạo với `orderId = null` và có `lineNumber`. Provider sẽ dùng `order.id` để xác định phần khóa tương ứng khi lưu. Nếu parent đã có ID và muốn một đối tượng khóa hoàn chỉnh trước khi lưu, mã có thể tính `new SalesOrderLineId(order.getId(), lineNumber)`, nhưng vẫn cần giữ quan hệ `order` nhất quán. Không nên sử dụng khóa ghép chưa hoàn chỉnh để làm key trong `HashMap` hoặc phần tử `HashSet` rồi thay đổi các phần khóa sau đó.

### 6.3. Entity được lưu hay chưa khác với khóa đã được cấp

Sau `persist`, một provider có thể đã cấp ID cho parent và child trong bộ nhớ, nhưng transaction vẫn có thể rollback vì lỗi ràng buộc hoặc lỗi nghiệp vụ khác. **Có ID không có nghĩa bản ghi đã commit**.

Sequence còn có thể tạo khoảng trống ID sau rollback. Derived identity của child vì thế cần được hiểu là **định danh phụ thuộc vào parent**, không phải dấu xác nhận giao dịch thành công.

## 7. Tra cứu entity có khóa dẫn xuất

### 7.1. Dùng `EntityManager.find` với đầy đủ khóa ghép

Khi biết `orderId` và `lineNumber`:

```java
SalesOrderLineId key = new SalesOrderLineId(301L, 2);

SalesOrderLine line =
        em.find(SalesOrderLine.class, key);
```

`EntityManager.find` cần **đối tượng ID class đầy đủ**, không phải chỉ `orderId`:

```java
// Không đủ để định danh một dòng:
em.find(SalesOrderLine.class, 301L);
```

Vì một đơn có nhiều dòng, `301L` chưa xác định duy nhất `SalesOrderLine` nào.

### 7.2. JPQL truy cập các thành phần khóa

Với `@EmbeddedId`:

```java
List<SalesOrderLine> lines = em.createQuery(
    """
    SELECT l
    FROM SalesOrderLine l
    WHERE l.id.orderId = :orderId
    ORDER BY l.id.lineNumber
    """,
    SalesOrderLine.class
)
.setParameter("orderId", 301L)
.getResultList();
```

Truy vấn qua quan hệ cũng có thể dùng:

```java
List<SalesOrderLine> lines = em.createQuery(
    "SELECT l FROM SalesOrderLine l WHERE l.order.id = :orderId",
    SalesOrderLine.class
)
.setParameter("orderId", 301L)
.getResultList();
```

Hai dạng thể hiện hai góc nhìn:

- `l.id.orderId`: duyệt theo cấu trúc khóa nhúng của child.
- `l.order.id`: duyệt theo quan hệ và ID của parent.

Chúng cùng hướng tới khóa đơn hàng, nhưng SQL provider sinh ra có thể khác tùy metadata và tối ưu truy vấn. JPQL dùng **tên thuộc tính Java**, không dùng tên SQL `order_id` trực tiếp.

### 7.3. Criteria API

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<SalesOrderLine> query =
        cb.createQuery(SalesOrderLine.class);

Root<SalesOrderLine> line = query.from(SalesOrderLine.class);

query.select(line).where(
    cb.equal(line.get("id").get("orderId"), 301L)
);

List<SalesOrderLine> result =
        em.createQuery(query).getResultList();
```

Trong codebase lớn, có thể sử dụng **static metamodel** để tránh viết tên thuộc tính dạng chuỗi, nhưng cơ chế khóa dẫn xuất không thay đổi.

## 8. Dẫn xuất toàn bộ khóa: `@OneToOne` và `@MapsId` không có tham số

Trường hợp phổ biến khác là **shared primary key one-to-one**. Mỗi tài khoản có tối đa một hồ sơ; ID của hồ sơ là chính ID của tài khoản.

### 8.1. Entity `Account`

```java
package com.example.accounts;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String username;

    protected Account() {}

    public Account(String username) {
        this.username = username;
    }

    public Long getId() {
        return id;
    }
}
```

### 8.2. Entity `AccountProfile` dùng khóa của `Account`

```java
package com.example.accounts;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "account_profiles")
public class AccountProfile {

    @Id
    @Column(name = "account_id")
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private Account account;

    @Column(name = "display_name", nullable = false, length = 100)
    private String displayName;

    protected AccountProfile() {}

    public AccountProfile(Account account, String displayName) {
        this.account = Objects.requireNonNull(account);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public Long getId() {
        return id;
    }

    public Account getAccount() {
        return account;
    }
}
```

Điểm khác ví dụ khóa ghép:

- `AccountProfile` có **khóa đơn** `Long id`.
- `@MapsId` **không có giá trị `value`** nghĩa là quan hệ `account` ánh xạ **toàn bộ định danh** của `AccountProfile`.
- `AccountProfile` **không dùng `@GeneratedValue`** trên ID của nó; giá trị đến từ `Account.id`.
- `@JoinColumn(name = "account_id")` đồng thời định nghĩa cột khóa ngoại và khóa chính ở bảng hồ sơ.

Một sơ đồ SQL tương ứng:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL
);

CREATE TABLE account_profiles (
    account_id BIGINT PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,

    CONSTRAINT fk_profile_account
        FOREIGN KEY (account_id)
        REFERENCES accounts(id)
);
```

Cú pháp `IDENTITY` là minh họa và có thể khác ở database thực tế. Điểm chính là `account_profiles.account_id` **vừa PK vừa FK**.

### 8.3. Lưu cha và dependent

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Account account = new Account("nguyen.an");
        em.persist(account);
        em.flush();

        AccountProfile profile =
                new AccountProfile(account, "Nguyễn An");
        em.persist(profile);

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Nếu `account.getId()` là `800L`, sau khi provider đồng bộ ID cho profile, `profile.getId()` tương ứng `800L`. `profile` không thể có một ID khác độc lập với `account`.

Cấu trúc bảng bảo đảm một account chỉ có **tối đa một** row profile vì `account_id` là primary key. Nó **không tự bảo đảm mọi account bắt buộc có một profile**: vẫn có thể tồn tại tài khoản chưa có hàng trong `account_profiles`. Nếu nghiệp vụ đòi hỏi cả hai luôn được tạo, hãy đặt thao tác tạo account/profile trong cùng transaction và kiểm soát quá trình ghi.

## 9. `@MapsId` có tham số và không tham số khác nhau

| Tình huống | Khóa của child | Annotation quan hệ | Ý nghĩa |
|---|---|---|---|
| Dòng đơn có `(orderId, lineNumber)` | `@EmbeddedId SalesOrderLineId` | `@MapsId("orderId")` + `@ManyToOne` | Parent cung cấp **một thành phần** của khóa ghép. |
| Hồ sơ dùng chung `accountId` | `@Id Long id` | `@MapsId` + `@OneToOne` | Parent cung cấp **toàn bộ** khóa đơn của child. |
| Entity có khóa ghép chứa toàn bộ khóa ghép của parent | ID class của child chứa thành phần ID tương ứng | `@MapsId` theo quy tắc dẫn xuất được phép | Parent có thể cung cấp toàn bộ một nhóm thành phần khóa, tùy cấu trúc ID. |

Giá trị `"orderId"` trong `@MapsId("orderId")` là tên field/property của **`@EmbeddedId`**. Khi không có tham số, `@MapsId` chỉ ra mối quan hệ cung cấp toàn bộ ID tương ứng thay vì chỉ một thuộc tính con được chỉ định.

Chọn đúng biến thể theo **cấu trúc khóa đã thiết kế**, không đặt `@MapsId` theo cảm tính trên mọi quan hệ.

## 10. Cách thay thế: định danh dẫn xuất với `@IdClass`

Không phải mọi ứng dụng đều muốn một field `@EmbeddedId`. JPA cho phép định nghĩa khóa bằng `@IdClass`.

### 10.1. Lớp `SalesOrderLineKey`

```java
package com.example.orders;

import java.io.Serializable;
import java.util.Objects;

public class SalesOrderLineKey implements Serializable {

    // Tên phải khớp thuộc tính ID "order" của entity.
    // Kiểu là kiểu khóa chính của SalesOrder (Long).
    private Long order;

    private Integer lineNumber;

    public SalesOrderLineKey() {}

    public SalesOrderLineKey(Long order, Integer lineNumber) {
        this.order = order;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof SalesOrderLineKey that)) {
            return false;
        }
        return Objects.equals(order, that.order)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(order, lineNumber);
    }
}
```

Điểm dễ nhầm: nếu entity có thuộc tính ID là **quan hệ tên `order` kiểu `SalesOrder`**, lớp ID dùng **thuộc tính tên `order` kiểu `Long`** (tức kiểu khóa đơn của `SalesOrder`), chứ không cần chứa một object `SalesOrder`.

### 10.2. Entity minh họa `@IdClass`

Để tách biệt hai ví dụ khi đặt chung project, entity sau ánh xạ tới bảng ví dụ `sales_order_lines_idclass`:

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "sales_order_lines_idclass")
@IdClass(SalesOrderLineKey.class)
public class SalesOrderLineByIdClass {

    @Id
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Id
    @Column(name = "line_no")
    private Integer lineNumber;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    protected SalesOrderLineByIdClass() {}

    public SalesOrderLineByIdClass(
            SalesOrder order, int lineNumber, int quantity
    ) {
        this.order = order;
        this.lineNumber = lineNumber;
        this.quantity = quantity;
    }
}
```

Khai báo này cho biết:

- `@IdClass(SalesOrderLineKey.class)` định nghĩa lớp đại diện khóa ghép.
- `@Id` được đặt trên **quan hệ `order`** và trên thuộc tính `lineNumber`.
- Với derived identity, thành phần khóa trong ID class có **cùng tên thuộc tính `order`**, nhưng kiểu là **kiểu khóa chính của parent** (`Long`).
- JPA ánh xạ `SalesOrderLineByIdClass.order` đến cột `order_id`, vừa khóa ngoại vừa một phần khóa chính.

Cấu trúc bảng dự kiến:

```sql
CREATE TABLE sales_order_lines_idclass (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    quantity INTEGER NOT NULL,

    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES sales_orders(id)
);
```

Tra cứu theo ID class:

```java
SalesOrderLineKey key =
        new SalesOrderLineKey(301L, 2);

SalesOrderLineByIdClass line =
        em.find(SalesOrderLineByIdClass.class, key);
```

### 10.3. So sánh hai cách ánh xạ

| Khía cạnh | `@EmbeddedId + @MapsId` | `@IdClass` với quan hệ `@Id` |
|---|---|---|
| Cách lưu khóa trong entity | Một thuộc tính `id` có lớp `@Embeddable`. | Các thành phần khóa xuất hiện thành thuộc tính trên entity. |
| Khai báo quan hệ trong khóa | `@MapsId("orderId")` cho biết phần nào của embedded ID đến từ parent. | Quan hệ được đánh dấu `@Id`; ID class có thuộc tính tên tương ứng. |
| Lấy thành phần khóa trong JPQL | Thường qua `l.id.orderId`. | Thường qua `l.order.id` và `l.lineNumber`. |
| Cách dựng khóa để gọi `find` | `new SalesOrderLineId(orderId, lineNumber)`. | `new SalesOrderLineKey(orderId, lineNumber)`. |
| Ưu điểm | ID class biểu diễn khóa ghép rõ ràng, dễ chuyển qua boundary. | Đọc trực tiếp các thành phần trên entity, không cần `entity.getId().get...`. |
| Điểm cần chú ý | Đồng bộ ID và quan hệ qua `@MapsId`; tên trong `value` phải khớp embedded ID. | Quy tắc khớp tên và kiểu ID class của quan hệ rất dễ nhầm. |

Cả hai đều là ánh xạ derived identity hợp lệ theo mô hình được JPA hỗ trợ. Nên chọn **một phong cách nhất quán cho một kiểu entity**, tránh khai báo `@EmbeddedId` và `@IdClass` đồng thời trên cùng entity theo cách không có chủ đích.

## 11. Nhiều entity cha cùng tham gia khóa ghép

Ví dụ một lượt đăng ký học (`Enrollment`) được xác định bằng cặp **(student_id, course_id)**. Khóa này **đều được dẫn xuất từ hai entity liên quan**.

Giả sử:

- `Student.id` là `Long`.
- `Course.id` là `Long`.
- `Enrollment` có thêm một thuộc tính nghiệp vụ `enrolledAt`.

### 11.1. Lớp khóa nhúng

```java
@Embeddable
public class EnrollmentId implements Serializable {

    private Long studentId;
    private Long courseId;

    protected EnrollmentId() {}

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = studentId;
        this.courseId = courseId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EnrollmentId that)) return false;
        return Objects.equals(studentId, that.studentId)
                && Objects.equals(courseId, that.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
```

Trong file thực tế cần các import phù hợp, gồm `jakarta.persistence.Embeddable`, `java.io.Serializable` và `java.util.Objects`.

### 11.2. Entity có hai `@MapsId`

```java
@Entity
@Table(name = "enrollments")
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    @MapsId("studentId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @MapsId("courseId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "course_id", nullable = false)
    private Course course;

    @Column(name = "enrolled_at", nullable = false)
    private LocalDate enrolledAt;

    protected Enrollment() {}

    public Enrollment(Student student, Course course, LocalDate enrolledAt) {
        this.student = Objects.requireNonNull(student);
        this.course = Objects.requireNonNull(course);
        this.enrolledAt = Objects.requireNonNull(enrolledAt);

        // ID của hai parent sẽ được ánh xạ vào khóa.
        this.id = new EnrollmentId(null, null);
    }
}
```

Ví dụ dùng các entity `Student` và `Course` đã có khóa `Long id`, và các import tương ứng cho JPA/`LocalDate`/`Objects`.

Cột `student_id` và `course_id` tạo thành **primary key**, đồng thời là hai **foreign key** độc lập. Đây là ví dụ của một *association entity* có thể thay thế bảng liên kết thuần túy khi bản ghi liên kết còn có dữ liệu như `enrolledAt`, trạng thái hoặc điểm số.

```sql
CREATE TABLE enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at DATE NOT NULL,

    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
```

Một học viên có thể tham gia nhiều khóa học, một khóa học có nhiều học viên. Nhưng một cặp `(student_id, course_id)` chỉ được lưu **một lần**, trừ khi nghiệp vụ thay đổi thiết kế khóa (ví dụ bổ sung kỳ học hoặc lần đăng ký).

## 12. Vòng đời parent và dependent entity

### 12.1. Parent cần được xác định trước khi lưu dependent

Với derived identity, khóa của child phụ thuộc vào khóa của parent. Vì vậy một dependent entity thường **không thể được persist hợp lệ** nếu chưa gắn với parent tương ứng.

Ví dụ lỗi:

```java
SalesOrderLine line =
        new SalesOrderLine(null, 1, "Sổ tay", 2);
```

Constructor ở phần 4 sẽ từ chối `order == null`. Nếu không có kiểm tra này, JPA/database vẫn không thể xây dựng `order_id` hợp lệ khi khóa cha không xác định.

Một trường hợp khác:

```java
SalesOrder order = new SalesOrder("Khách An");
SalesOrderLine line = new SalesOrderLine(order, 1, "Sổ tay", 2);

em.persist(line);
```

Nếu `order` là một entity mới chưa được lưu và quan hệ **không có cascade persist**, việc lưu `line` có thể thất bại vì parent chưa managed/chưa có ID hợp lệ. Cách đơn giản là:

```java
em.persist(order);
em.persist(line);
```

hoặc tổ chức cascade đúng theo vòng đời nghiệp vụ. Khi parent dùng chiến lược sinh khóa như `IDENTITY`, provider có thể cần thực thi INSERT parent trước khi có ID, và provider sẽ quản lý thứ tự SQL theo mapping/transaction.

### 12.2. `@MapsId` không đồng nghĩa với `cascade`

`@MapsId` nói rằng quan hệ đóng góp **giá trị khóa chính**. Nó **không tự cấp quyền cascade**.

Muốn persist parent và child thông qua một aggregate, có thể khai báo quan hệ từ parent đến child:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<SalesOrderLine> lines = new ArrayList<>();
```

Khi đó helper trên parent có thể tạo dòng và cập nhật cả hai phía:

```java
public void addLine(String productName, int quantity) {
    int nextLineNumber = lines.size() + 1;
    SalesOrderLine line = new SalesOrderLine(
        this, nextLineNumber, productName, quantity
    );
    lines.add(line);
}
```

Đây là **minh họa cách tổ chức aggregate**, không phải thuật toán cấp số dòng phù hợp với mọi nghiệp vụ: nếu đã xóa dòng giữa hoặc cho phép chỉnh sửa số dòng, dùng `lines.size() + 1` có thể dẫn đến trùng `line_no`. Hệ thống thực tế nên quyết định một cơ chế cấp số dòng ổn định theo vòng đời đơn hàng.

Nếu cần dùng `CascadeType.REMOVE` hoặc `orphanRemoval = true`, phải cân nhắc ý nghĩa xóa và ràng buộc nghiệp vụ. Đặc biệt, không nên bật cascade remove từ child lên parent: xóa một dòng đơn **không được tự xóa cả đơn hàng**.

### 12.3. Ai là phía sở hữu quan hệ?

Với quan hệ hai chiều:

```text
SalesOrder.lines  (@OneToMany(mappedBy = "order"))
SalesOrderLine.order (@ManyToOne + @JoinColumn + @MapsId)
```

Phía `SalesOrderLine.order` là **owning side** của quan hệ. Nó điều khiển foreign key `order_id`. Chỉ thêm một object vào collection `SalesOrder.lines` mà không gán `line.order` có thể làm hai phía object graph không nhất quán.

Một helper đúng cần bảo đảm cả collection phía parent và tham chiếu phía child nhất quán. Với derived identity, tính nhất quán đó còn liên quan đến **khóa chính**.

### 12.4. Có thể đổi parent sau khi lưu không?

Thông thường, **không nên chuyển một dependent entity đã persistent sang parent khác** nếu quan hệ đó nằm trong khóa chính.

Ví dụ `SalesOrderLine` đang có khóa `(301, 2)`; chuyển `order` sang đơn 302 sẽ làm khóa thành `(302, 2)`. Đó là **thay đổi danh tính**, không chỉ sửa một foreign key thông thường. JPA không bảo đảm việc thay primary key của entity managed là thao tác cập nhật bình thường.

Thiết kế an toàn là xem định danh như **bất biến sau khi persist**. Nếu nghiệp vụ thực sự muốn chuyển dòng sang đơn khác, có thể cần xóa dependent cũ và tạo dependent mới dưới parent đích, trong transaction được thiết kế phù hợp, đồng thời xét ràng buộc unique/FK và lịch sử nghiệp vụ.

## 13. `equals()`, `hashCode()` và tính ổn định của khóa

Lớp khóa như `SalesOrderLineId` và `SalesOrderLineKey` cần định nghĩa `equals()`/`hashCode()` dựa trên **tất cả thành phần khóa**.

Ví dụ:

```java
new SalesOrderLineId(301L, 1)
        .equals(new SalesOrderLineId(301L, 1)); // true

new SalesOrderLineId(301L, 1)
        .equals(new SalesOrderLineId(302L, 1)); // false
```

Hai khóa chỉ bằng nhau nếu cả `orderId` và `lineNumber` tương ứng bằng nhau.

Một nguy cơ với khóa dẫn xuất là **parent chưa được cấp ID** khi ID object được tạo:

```java
SalesOrderLineId key =
        new SalesOrderLineId(null, 1);

Set<SalesOrderLineId> keys = new HashSet<>();
keys.add(key);

// Sau đó nếu key.orderId bị thay đổi từ null thành 301L,
// hashCode cũng thay đổi -> HashSet có thể không tìm thấy key.
```

Không nên thêm ID chưa ổn định vào `HashSet` hoặc dùng nó làm `HashMap` key rồi thay đổi các thành phần khóa. Nên đợi khóa được xác định đầy đủ hoặc dùng một object giá trị mới bất biến để làm key tại ranh giới ứng dụng phù hợp.

**Không bắt buộc entity luôn `equals/hashCode` y hệt ID class.** Việc viết `equals/hashCode` cho entity có định danh sinh tự động cần cân nhắc trạng thái transient/managed/detached và proxy. Với ID class, yêu cầu về equality theo khóa rõ ràng hơn; đừng dùng quan hệ `SalesOrder` và toàn bộ object graph để tính `hashCode` của ID class khi theo quy tắc derived `@IdClass` chỉ cần kiểu ID của parent.

## 14. Vấn đề tải dữ liệu và hiệu năng

Derived identity không tự quyết định fetch strategy:

```java
@MapsId("orderId")
@ManyToOne(fetch = FetchType.LAZY, optional = false)
private SalesOrder order;
```

`FetchType.LAZY` ở đây thể hiện ý định trì hoãn tải đối tượng parent khi provider hỗ trợ. Trong JPA, fetch của quan hệ to-one có thể phụ thuộc provider và các trường hợp cụ thể; vì vậy không nên giả định cứ khai báo LAZY là mọi truy cập đều không tạo thêm SQL.

Một truy vấn lấy hàng trăm `SalesOrderLine` rồi gọi `line.getOrder().getCustomerName()` cho từng dòng có thể gặp **N+1 queries** nếu parent được tải riêng rẽ. Khi nghiệp vụ cần parent, có thể dùng `JOIN FETCH` hoặc entity graph phù hợp:

```java
List<SalesOrderLine> lines = em.createQuery(
    """
    SELECT l
    FROM SalesOrderLine l
    JOIN FETCH l.order
    WHERE l.id.orderId = :orderId
    ORDER BY l.id.lineNumber
    """,
    SalesOrderLine.class
)
.setParameter("orderId", 301L)
.getResultList();
```

Ngược lại, nếu chỉ cần khóa `orderId` và `lineNumber` để trả về DTO, không nhất thiết tải toàn bộ parent. Khóa nhúng đã chứa thông tin định danh mà nhiều truy vấn có thể dùng trực tiếp.

Đối với database, chỉ mục composite primary key thường có thứ tự cột `(order_id, line_no)`. Các truy vấn lọc theo `order_id` có thể tận dụng thứ tự khóa trong nhiều RDBMS; nếu thường xuyên tìm theo `line_no` độc lập, cần đánh giá chỉ mục phụ theo workload thực tế. Không nên thêm index chỉ vì nhìn thấy `@MapsId`; đánh giá từ truy vấn và kế hoạch thực thi.

## 15. Khi nào derived identity là lựa chọn hợp lý?

### 15.1. Những trường hợp phù hợp

**Shared primary key one-to-one:** thông tin phụ mở rộng cho entity chính như `AccountProfile`, `CustomerPreferences` hoặc dữ liệu phân tách để giới hạn truy cập, với vòng đời gắn sát parent.

**Thực thể con được đánh số cục bộ:** `OrderLine(orderId, lineNumber)`, `InvoiceLine(invoiceId, lineNumber)` hoặc `DocumentVersion(documentId, versionNumber)`, nếu số thứ tự chỉ có ý nghĩa trong parent.

**Bảng liên kết có thuộc tính riêng:** `Enrollment(studentId, courseId)`, `Membership(userId, groupId)` hoặc `ProjectAssignment(projectId, employeeId)` có thêm thời gian, trạng thái, vai trò.

### 15.2. Những trường hợp nên cân nhắc khóa độc lập

Có thể dùng khóa sinh riêng `Long id` + unique constraint trên cặp business columns nếu:

- Child thường xuyên được chuyển qua parent khác.
- Nhiều bảng khác tham chiếu đến child và khóa ghép khiến foreign key lan truyền nhiều cột.
- Giao diện/API cần identifier ngắn, ổn định và không phụ thuộc quan hệ.
- Thiết kế muốn phân biệt **technical identity** với **business uniqueness**.
- Dữ liệu liên kết có thể tồn tại qua nhiều phiên bản/mối quan hệ và việc đổi parent là nghiệp vụ thường xuyên.

Ví dụ thay thế:

```sql
CREATE TABLE sales_order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,

    CONSTRAINT uq_order_line
        UNIQUE (order_id, line_no),

    FOREIGN KEY (order_id)
        REFERENCES sales_orders(id)
);
```

Trong mô hình này, `id` là khóa độc lập và cặp `(order_id, line_no)` là **business unique key**, không phải primary key. Hai cách có lợi ích và trade-off khác nhau; lựa chọn dựa trên vòng đời định danh và cách hệ thống tham chiếu dữ liệu.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `@MapsId("order_id")` không tìm thấy thuộc tính | Dùng tên **SQL column** thay cho tên field `orderId` trong embedded ID. | Đổi thành `@MapsId("orderId")`. |
| Provider báo trùng ánh xạ cột `order_id` | Ánh xạ riêng cả scalar ID và association mà không xác định quan hệ derived identity đúng. | Sử dụng `@MapsId` và mapping nhất quán. |
| Lưu child thất bại vì parent transient | Parent chưa persist, cascade chưa được cấu hình. | Persist parent trước hoặc cấu hình cascade phù hợp. |
| Khóa con có `orderId = null` khi mới khởi tạo | Parent chưa được cấp ID hoặc provider chưa đồng bộ derived ID. | Đợi thao tác persistence/flush phù hợp; không dùng khóa chưa ổn định như khóa collection. |
| Duplicate key với `(order_id, line_no)` | Tạo hai dòng cùng số thứ tự trong một đơn. | Có cơ chế cấp/kiểm tra số dòng duy nhất trong parent, giữ PK DB. |
| `@IdClass` báo sai kiểu/thiếu thuộc tính | ID class không trùng tên với các thuộc tính ID của entity; quan hệ `order` bị khai báo kiểu `SalesOrder` trong key thay vì kiểu ID `Long`. | Dùng cùng tên `order` và kiểu `Long` với parent khóa đơn. |
| `EntityManager.find` trả null dù parent tồn tại | Chỉ truyền parent ID hoặc dùng sai thành phần composite key. | Truyền toàn bộ `SalesOrderLineId(orderId, lineNumber)`. |
| Đổi `line.order` trên entity managed rồi mapping lỗi | Thay đổi quan hệ làm thay primary key của child. | Xem PK là bất biến; nếu cần chuyển, tạo entity mới và xử lý dependent cũ. |
| Xóa parent bị lỗi foreign key | Child còn tham chiếu parent; cascade/remove chưa được thiết kế. | Xác định quy tắc xóa và transaction; xử lý child trước hoặc cấu hình cascade phù hợp. |
| Số dòng trong collection và `line.order` lệch nhau | Chỉ cập nhật phía inverse của quan hệ hai chiều. | Helper duy trì cả hai phía, đặc biệt owning side. |
| Query tải hàng trăm line kéo theo nhiều query parent | N+1 từ lazy/eager association theo cách sử dụng. | Dùng `JOIN FETCH`/entity graph khi cần parent, hoặc truy vấn DTO. |
| HashMap/HashSet không tìm được key sau persist | `hashCode` đổi khi ID dẫn xuất từ null sang giá trị đã cấp. | Chỉ dùng key ổn định, không sửa key sau khi đưa vào hash collection. |
| Child có `@GeneratedValue` riêng dù dùng shared PK | Cấu hình hai nguồn cấp ID xung đột. | Với shared PK `@MapsId`, lấy ID từ parent; bỏ generator độc lập của child. |

### 16.1. Vì sao không chỉ dùng `insertable = false, updatable = false`?

Một cách cũ đôi khi thấy:

```java
@EmbeddedId
private SalesOrderLineId id;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(
    name = "order_id",
    insertable = false,
    updatable = false
)
private SalesOrder order;
```

Cấu hình này biến association thành một ánh xạ **chỉ đọc cột** theo góc nhìn ghi SQL, trong khi mã phải tự gán `id.orderId` cho đúng. Nó có thể dùng cho vài yêu cầu legacy, nhưng **không biểu đạt trực tiếp** rằng khóa được dẫn xuất từ quan hệ như `@MapsId`.

Nếu mục tiêu là derived identity chuẩn, `@MapsId("orderId")` thường rõ nghĩa hơn, tránh duy trì đồng thời `order` và `id.orderId` như hai nguồn dữ liệu rời rạc.

### 16.2. Vì sao không thêm `@GeneratedValue` vào `lineNumber`?

`lineNumber` là số thứ tự **bên trong một parent**, không phải ID độc lập toàn hệ thống. Các generator chuẩn như `SEQUENCE` thường cấp số trên phạm vi sequence database, không tự hiểu cần bắt đầu từ 1 cho từng `order_id`.

Nếu nghiệp vụ bắt buộc đánh số dòng theo đơn, ứng dụng cần cơ chế riêng nhất quán dưới điều kiện cạnh tranh, chẳng hạn khi mọi sửa dòng được thực hiện trong transaction giữ khóa parent hoặc theo cấu trúc aggregate đã quy định. Không nên gắn `@GeneratedValue` lên một phần khóa ghép và mong provider tự cấp số dòng cục bộ theo parent.

## 17. Tình huống thực hành: mở rộng một đơn hàng

Giả sử đơn `SalesOrder` có ID `501` và đã lưu:

```text
(order_id, line_no) = (501, 1)
(order_id, line_no) = (501, 2)
```

Muốn thêm dòng số 3:

```java
SalesOrder order = em.find(SalesOrder.class, 501L);

SalesOrderLine next = new SalesOrderLine(
        order,
        3,
        "Bìa hồ sơ",
        10
);

em.persist(next);
```

Khi transaction commit thành công, bảng có thêm khóa `(501, 3)`. Nếu một transaction khác cũng cố lưu `(501, 3)` cùng lúc, **ràng buộc primary key** bảo vệ database khỏi hai hàng có cùng composite key; một transaction có thể thất bại với lỗi ràng buộc.

Nếu sau đó muốn sửa số lượng của dòng số 2:

```java
SalesOrderLineId id =
        new SalesOrderLineId(501L, 2);

SalesOrderLine line =
        em.find(SalesOrderLine.class, id);

if (line != null) {
    line.changeQuantity(7);
}
```

Trong một transaction phù hợp, JPA dirty checking có thể đồng bộ `quantity` xuống database. **Khóa `(501,2)` không đổi**; đây là cập nhật thuộc tính nghiệp vụ thông thường.

Nếu muốn xóa dòng số 1:

```java
SalesOrderLine oldLine = em.find(
        SalesOrderLine.class,
        new SalesOrderLineId(501L, 1)
);

if (oldLine != null) {
    em.remove(oldLine);
}
```

Sau khi xóa, các dòng còn lại **không bắt buộc đánh số lại**; việc đánh số lại có thể vô tình thay đổi khóa chính. Nếu giao diện cần hiển thị dòng theo thứ tự liên tiếp, có thể tính số thứ tự hiển thị riêng, còn `lineNumber` làm định danh ổn định cho bản ghi.

## 18. Câu hỏi tự kiểm tra

**1. Khi nào một entity có derived identity?**  
Khi khóa chính của nó được xác định toàn bộ hoặc một phần từ khóa chính của entity khác mà nó tham chiếu qua quan hệ.

**2. `@MapsId("orderId")` lấy tên `orderId` ở đâu?**  
Đó là tên thành phần trong khóa nhúng `SalesOrderLineId`, không phải tên SQL column `order_id`.

**3. `@EmbeddedId` có cần `equals/hashCode` không?**  
Lớp khóa ghép cần định nghĩa equality và hash code nhất quán với các phần khóa, đồng thời đáp ứng các yêu cầu khóa ID của JPA như `Serializable`.

**4. `@MapsId` có tự động persist parent chưa được quản lý?**  
Không. `@MapsId` nói về ánh xạ định danh. Cascade và transaction/lifecycle là các cơ chế riêng cần được thiết kế phù hợp.

**5. Shared primary key one-to-one cần `@GeneratedValue` trên child không?**  
Thông thường không. Child dùng `@MapsId` để nhận ID từ parent; parent là nguồn tạo khóa.

**6. Với `@IdClass`, tại sao thuộc tính `order` trong ID class là `Long` trong khi entity giữ `SalesOrder order`?**  
Vì đó là quy tắc derived identity: thuộc tính khóa trong ID class tương ứng với relationship dùng **kiểu định danh của entity được tham chiếu**.

**7. Có thể tìm dòng đơn bằng `em.find(SalesOrderLine.class, 501L)` không?**  
Không. `SalesOrderLine` có khóa ghép, nên phải truyền một `SalesOrderLineId` chứa đủ `orderId` và `lineNumber`.

**8. Nếu đổi parent của child đang managed thì sao?**  
Đó có thể là thay đổi khóa chính của child. JPA không bảo đảm việc đổi primary key của entity persistent được xử lý như một update thông thường; nên thiết kế khóa ổn định và tạo child mới khi cần thay đổi quan hệ định danh.

**9. Vì sao `(501,1)` và `(502,1)` không trùng khóa?**  
Vì khóa là một **cặp** gồm ID parent và số dòng; hai cặp khác thành phần `orderId`.

**10. Entity phụ thuộc có bắt buộc dùng `@MapsId` mới là derived identity?**  
Không. `@IdClass` với quan hệ được đánh dấu `@Id` cũng là một cách biểu diễn định danh dẫn xuất. `@MapsId` đặc biệt rõ ràng khi dùng `@EmbeddedId` hoặc shared primary key.

## 19. Tổng kết

**Định danh dẫn xuất từ entity liên quan** cho phép một entity xây dựng khóa chính bằng cách sử dụng khóa của entity mà nó phụ thuộc. Đây là cơ chế quan trọng khi mô hình hóa **khóa ghép**, **dòng chi tiết trong aggregate**, **entity liên kết có thuộc tính riêng** và **quan hệ một-một dùng chung khóa chính**.

Ba hình thức cần ghi nhớ:

```java
// 1. Khóa ghép + parent đóng góp một phần khóa:
@EmbeddedId
private SalesOrderLineId id;

@MapsId("orderId")
@ManyToOne
private SalesOrder order;
```

```java
// 2. Shared primary key, child lấy toàn bộ khóa từ parent:
@Id
private Long id;

@MapsId
@OneToOne
private Account account;
```

```java
// 3. Khóa ghép bằng @IdClass,
// relationship là một phần của định danh:
@IdClass(SalesOrderLineKey.class)
@Entity
public class SalesOrderLineByIdClass {

    @Id
    @ManyToOne
    private SalesOrder order;

    @Id
    private Integer lineNumber;

    protected SalesOrderLineByIdClass() {}
}
```

Dù chọn cách nào, cần giữ nhất quán **thuộc tính khóa Java ↔ quan hệ JPA ↔ các cột PK/FK trong SQL**. Quan hệ dẫn xuất quyết định danh tính của child, nên phải được thiết lập đúng trước khi lưu, và không nên thay đổi sau khi entity đã persistent. Transaction, cascade, ràng buộc khóa chính và khóa ngoại của database sẽ hỗ trợ duy trì tính toàn vẹn của mô hình này.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API: `@MapsId`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/mapsid)
- [Jakarta Persistence API: `@EmbeddedId`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/embeddedid)
- [Jakarta Persistence API: `@IdClass`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/idclass)
