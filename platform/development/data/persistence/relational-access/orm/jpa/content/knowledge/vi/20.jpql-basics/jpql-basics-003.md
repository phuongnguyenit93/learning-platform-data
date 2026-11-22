# Chọn entity, thuộc tính và nhiều biểu thức kết quả

Trong JPQL (*Jakarta Persistence Query Language*), mệnh đề `SELECT` không chỉ quyết định **những hàng nào được trả về** mà còn quyết định **kiểu dữ liệu Java của từng phần tử kết quả**. Một truy vấn có thể trả về một entity đang được JPA quản lý, một giá trị đơn như `String` hoặc `Long`, hoặc một hàng gồm nhiều biểu thức như ID, tên khách hàng và tổng tiền. Nếu muốn kết quả có cấu trúc rõ ràng, có thể dùng *constructor expression* để tạo DTO thay vì thao tác với mảng vị trí.

Ba dạng cần phân biệt:

~~~jpql
-- Chọn toàn bộ entity:
SELECT o
FROM PurchaseOrder o

-- Chọn một thuộc tính:
SELECT o.totalAmount
FROM PurchaseOrder o

-- Chọn nhiều biểu thức:
SELECT o.id, o.status, o.totalAmount
FROM PurchaseOrder o
~~~

Ba câu truy vấn có cùng nguồn `PurchaseOrder` nhưng **không có cùng kiểu trả về**. Câu đầu trả entity `PurchaseOrder`, câu thứ hai trả các giá trị `BigDecimal`, câu thứ ba thường trả từng hàng dưới dạng `Object[]`. Nếu không nắm quy tắc này, ứng dụng dễ gặp `ClassCastException`, sai thứ tự cột, tải dư dữ liệu hoặc hiểu nhầm rằng projection cũng là entity managed.

Bài học này đi từ cú pháp chọn entity, thuộc tính và nhiều biểu thức, đến `TypedQuery`, `Object[]`, DTO constructor, aggregate, `DISTINCT`, join, phân trang, xử lý kết quả rỗng và những lựa chọn phù hợp cho code ứng dụng thực tế.

---

## 1. JPQL SELECT làm việc với mô hình entity, không phải cột SQL trực tiếp

Giả sử database có:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(200) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(15, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_code VARCHAR(40) NOT NULL,
    quantity INT NOT NULL
);
~~~

Tạo mô hình JPA:

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false)
    private String email;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Trạng thái đơn:

~~~java
package com.example.sales.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Entity đơn hàng:

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void changeStatus(OrderStatus newStatus) {
        this.status = newStatus;
    }
}
~~~

Entity dòng hàng:

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public String getProductCode() {
        return productCode;
    }
}
~~~

Những ví dụ phía sau giả định các entity được khai báo như trên và một `EntityManager em` đang hợp lệ. Entity constructors được rút gọn vì bài tập trung vào đọc bằng JPQL; trong ứng dụng đầy đủ, cần phương thức tạo entity, validation và transaction phù hợp.

### 1.1. Dữ liệu minh họa

Giả sử có hai khách hàng:

| Customer ID | fullName |
|---:|---|
| 1 | An |
| 2 | Bình |

Và ba đơn:

| Order ID | Customer | status | totalAmount |
|---:|---|---|---:|
| 101 | An | NEW | 120000 |
| 102 | An | PAID | 300000 |
| 103 | Bình | PAID | 180000 |

Đơn 101 có hai dòng hàng; đơn 102 có một dòng; đơn 103 chưa có dòng trong dữ liệu giả định.

Trong JPQL, ta dùng **tên entity và tên thuộc tính Java**:

~~~jpql
SELECT o.totalAmount
FROM PurchaseOrder o
WHERE o.status = :status
~~~

Không dùng tên cột vật lý như `total_amount` trong đường thuộc tính:

~~~sql
-- Đây là SQL, không phải JPQL:
SELECT total_amount
FROM purchase_orders
WHERE status = 'PAID';
~~~

Một câu JPQL sai nếu entity khai báo `totalAmount` nhưng viết:

~~~jpql
-- SAI: dùng tên cột SQL thay vì tên thuộc tính Java.
SELECT o.total_amount
FROM PurchaseOrder o
~~~

JPA provider chuyển JPQL theo mô hình object sang SQL theo mapping của entity và database dialect.

### 1.2. Alias trong FROM

~~~jpql
SELECT o
FROM PurchaseOrder o
~~~

`o` là *identification variable* (bí danh) đại diện cho các phần tử kiểu `PurchaseOrder`. Sau `FROM`, dùng `o.id`, `o.status`, `o.customer` để truy cập thuộc tính và association.

Các câu đều cùng ý nghĩa về alias nếu đặt tên nhất quán:

~~~jpql
SELECT orderEntity
FROM PurchaseOrder orderEntity

SELECT p
FROM PurchaseOrder p
~~~

Tên alias không phải tên bảng hoặc tên cột. Nên chọn ngắn, rõ nghĩa và tránh nhầm với từ khóa.

---

## 2. Chọn toàn bộ entity: SELECT o

Dạng cơ bản:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();
~~~

Ý nghĩa:

- `SELECT o` chọn phần tử entity `PurchaseOrder`.
- `PurchaseOrder.class` khai báo kiểu kết quả mong đợi cho `TypedQuery`.
- Mỗi phần tử `orders` là một entity instance do persistence context quản lý khi truy vấn được thực hiện trong context đang hoạt động.
- Entity identity được bảo đảm nhất quán trong cùng persistence context.

### 2.1. Truy vấn theo trạng thái

~~~java
List<PurchaseOrder> paid = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE o.status = :status
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
~~~

Đây là truy vấn kiểu entity, có filter và order. Sử dụng `:status` giúp giữ giá trị bên ngoài câu JPQL, tránh nối chuỗi từ input người dùng.

Cụm `ORDER BY o.createdAt DESC, o.id DESC` cung cấp thứ tự ổn định hơn khi nhiều đơn có cùng thời điểm tạo; rất hữu ích cho phân trang.

### 2.2. Kết quả entity là managed — không phải DTO

Trong một transaction:

~~~java
PurchaseOrder order = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE o.id = :id
        """,
        PurchaseOrder.class
    )
    .setParameter("id", 101L)
    .getSingleResult();

order.changeStatus(OrderStatus.PAID);
~~~

Nếu `order` đang managed, JPA dirty checking có thể đồng bộ thay đổi trạng thái khi flush/commit. Không cần thêm `persist(order)` chỉ vì entity được tải bằng JPQL thay vì `find()`.

Ngược lại, nếu truy vấn chỉ chọn `o.status` và nhận một giá trị enum, đổi biến enum Java hoặc gán giá trị khác vào biến đó **không có tác dụng cập nhật entity**.

### 2.3. SELECT entity không có nghĩa luôn tải toàn bộ quan hệ

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
~~~

Entity root được tải theo fetch plan của mapping, nhưng quan hệ `o.lines` được khai báo `LAZY`. Query không mặc định kéo toàn bộ dòng hàng.

Tương tự, nếu `o.customer` lazy, truy cập `order.getCustomer().getFullName()` ở ngoài persistence context có thể gặp lỗi lazy loading tùy provider. Việc chọn entity root khác với yêu cầu projection nhiều cột hoặc fetch toàn bộ object graph.

### 2.4. Cùng identity trong một persistence context

~~~java
PurchaseOrder byFind =
    em.find(PurchaseOrder.class, 101L);

PurchaseOrder byQuery = em.createQuery(
        """
        SELECT o FROM PurchaseOrder o
        WHERE o.id = :id
        """,
        PurchaseOrder.class
    )
    .setParameter("id", 101L)
    .getSingleResult();

System.out.println(byFind == byQuery); // true
~~~

Ví dụ giả định entity 101 tồn tại. Cùng context, JPA không quản lý hai instance khác nhau cho cùng entity identity.

Điều này không có nghĩa câu JPQL chắc chắn không thực hiện SQL: JPQL vẫn có thể truy vấn database, nhưng kết quả entity được gắn với managed instance đang có.

---

## 3. Chọn một thuộc tính: SELECT o.totalAmount

Khi màn hình chỉ cần giá trị tổng tiền, không nhất thiết phải tải `PurchaseOrder`.

~~~java
List<BigDecimal> amounts = em.createQuery(
        """
        SELECT o.totalAmount
        FROM PurchaseOrder o
        ORDER BY o.id
        """,
        BigDecimal.class
    )
    .getResultList();
~~~

Kết quả dự kiến theo dữ liệu minh họa:

~~~text
120000
300000
180000
~~~

Ở đây:

- Mỗi hàng có đúng **một biểu thức select**.
- Giá trị trả về là `BigDecimal` do field `totalAmount` có kiểu đó.
- Không có instance `PurchaseOrder` trong result list chỉ bởi truy vấn này.
- Không thể gọi phương thức của entity như `amount.changeStatus(...)` trên scalar result.
- Nếu mục tiêu chỉ là hiển thị tổng tiền, scalar projection có thể giảm dữ liệu được chuyển và số entity được materialize.

### 3.1. Chọn ID

~~~java
List<Long> ids = em.createQuery(
        "SELECT o.id FROM PurchaseOrder o",
        Long.class
    )
    .getResultList();
~~~

Kết quả:

~~~text
101
102
103
~~~

Nếu `@Id` trong `PurchaseOrder` có kiểu `Long`, từng phần tử là Long. Nếu ID là UUID hoặc khóa ghép, kiểu kết quả sẽ khác tương ứng.

### 3.2. Chọn enum

~~~java
List<OrderStatus> statuses = em.createQuery(
        "SELECT o.status FROM PurchaseOrder o",
        OrderStatus.class
    )
    .getResultList();
~~~

Result là các giá trị của enum Java:

~~~text
NEW
PAID
PAID
~~~

Annotation `@Enumerated(EnumType.STRING)` quy định cách lưu vào database, không làm JPQL scalar result trở thành `String`. Vì field Java có kiểu `OrderStatus`, projection thường mang cùng kiểu Java đó.

Nếu muốn hiển thị chữ “Đã thanh toán”, nên định dạng ở tầng view/DTO theo quy tắc ứng dụng, không giả định enum có thể cast sang String.

### 3.3. Chọn một thuộc tính của entity liên kết

~~~java
List<String> customerNames = em.createQuery(
        """
        SELECT o.customer.fullName
        FROM PurchaseOrder o
        ORDER BY o.id
        """,
        String.class
    )
    .getResultList();
~~~

Ở đây `o.customer.fullName` là đường điều hướng quan hệ `@ManyToOne` rồi đến basic attribute. Provider có thể tạo JOIN ngầm trong SQL.

Kết quả có thể lặp:

~~~text
An
An
Bình
~~~

Vì có ba Order, không phải hai Customer. **Số hàng kết quả được quyết định bởi nguồn truy vấn và phép join/filter, không phải bởi số giá trị scalar khác nhau.**

### 3.4. Chọn trực tiếp entity ở đầu quan hệ

~~~java
List<Customer> customers = em.createQuery(
        """
        SELECT o.customer
        FROM PurchaseOrder o
        """,
        Customer.class
    )
    .getResultList();
~~~

Ở đây biểu thức `o.customer` có kiểu **entity Customer**, không phải String hoặc foreign-key Long. Kết quả có thể chứa cùng Customer nhiều lần theo nhiều Order, dù trong cùng persistence context các tham chiếu cùng identity vẫn trỏ tới một managed Customer tương ứng.

Nếu muốn danh sách Customer không trùng, dùng `DISTINCT` phù hợp:

~~~jpql
SELECT DISTINCT o.customer
FROM PurchaseOrder o
~~~

### 3.5. Chọn thuộc tính với WHERE

~~~java
List<String> names = em.createQuery(
        """
        SELECT c.fullName
        FROM Customer c
        WHERE c.email LIKE :pattern
        ORDER BY c.fullName ASC
        """,
        String.class
    )
    .setParameter("pattern", "%@example.com")
    .getResultList();
~~~

Cần phân biệt:

- `WHERE` chọn các hàng thỏa điều kiện.
- `SELECT` chọn các giá trị được trả về từ mỗi hàng.
- `ORDER BY` xác định thứ tự hàng kết quả.

Ba chức năng riêng, dù có thể dùng cùng hoặc khác đường thuộc tính.

---

## 4. Chọn nhiều biểu thức: SELECT o.id, o.status, o.totalAmount

Khi một hàng có **nhiều mục chọn**, mỗi result row không còn là `Long`, `String` hay `PurchaseOrder` đơn lẻ. Với kiểu xử lý JPQL phổ biến, mỗi hàng được trả dưới dạng **`Object[]`**, chứa các giá trị theo thứ tự biểu thức trong SELECT.

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o.id, o.status, o.totalAmount
        FROM PurchaseOrder o
        ORDER BY o.id
        """,
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    Long id = (Long) row[0];
    OrderStatus status = (OrderStatus) row[1];
    BigDecimal amount = (BigDecimal) row[2];

    System.out.printf(
        "Order %d: %s, %s%n",
        id,
        status,
        amount
    );
}
~~~

Bảng vị trí:

| Vị trí trong mảng | Biểu thức JPQL | Kiểu Java |
|---:|---|---|
| `row[0]` | `o.id` | `Long` |
| `row[1]` | `o.status` | `OrderStatus` |
| `row[2]` | `o.totalAmount` | `BigDecimal` |

**Vị trí được tính từ 0**, theo đúng thứ tự các biểu thức trong mệnh đề SELECT. Nếu sửa câu JPQL từ:

~~~jpql
SELECT o.id, o.status, o.totalAmount
~~~

thành:

~~~jpql
SELECT o.status, o.id, o.totalAmount
~~~

thì code cast `row[0]` sang Long sẽ sai. Đây là điểm yếu lớn của việc trả projection bằng `Object[]`.

### 4.1. Có bắt buộc dùng Object[].class không?

Nếu dùng API không khai báo kiểu:

~~~java
List<?> rawRows = em.createQuery(
    "SELECT o.id, o.status FROM PurchaseOrder o"
).getResultList();
~~~

Các hàng nhiều mục chọn trong trường hợp này thường là `Object[]`. Tuy nhiên dùng `TypedQuery<Object[]>` làm kiểu kết quả tường minh giúp code rõ hơn và tránh raw `Query` trong Java.

Một lỗi điển hình:

~~~java
// Sai: mỗi hàng có hai biểu thức, không phải một PurchaseOrder.
List<PurchaseOrder> orders = em.createQuery(
        "SELECT o.id, o.status FROM PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();
~~~

Việc ép kiểu resultClass không biến hai scalar expressions thành entity. Provider thường từ chối vì mismatch hoặc phát sinh lỗi ở lúc tạo/thực thi query.

### 4.2. Chọn một scalar với dấu phẩy thì sao?

~~~jpql
SELECT o.id FROM PurchaseOrder o
~~~

có một biểu thức nên kết quả là `Long`.

~~~jpql
SELECT o.id, o.status FROM PurchaseOrder o
~~~

có hai biểu thức nên kết quả là một hàng nhiều giá trị.

Sự khác biệt không nằm ở “có câu FROM hay không”, mà nằm ở **số lượng mục được chọn** và dạng select clause.

### 4.3. Có thể chọn biểu thức tính toán

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o.id,
               o.totalAmount * :taxRate,
               o.totalAmount + (o.totalAmount * :taxRate)
        FROM PurchaseOrder o
        """,
        Object[].class
    )
    .setParameter("taxRate", new BigDecimal("0.10"))
    .getResultList();
~~~

Ví dụ minh họa arithmetic expression trong JPQL. Các kiểu số và khả năng đánh giá expression phụ thuộc các toán hạng và provider/DBMS. Trong domain tiền tệ, nên lưu ý precision, scale, rounding và chính sách thuế thay vì lấy biểu thức minh họa này làm công thức hóa đơn production.

Một expression trong SELECT có thể là:

- Path như `o.id`, `o.totalAmount`.
- Hàm chuẩn hoặc hàm provider hỗ trợ, ví dụ `UPPER(c.fullName)`, `CONCAT(...)`.
- Phép toán, biểu thức `CASE`, `COALESCE`.
- Hàm tổng hợp như `COUNT(o)`, `SUM(o.totalAmount)`.
- Entity-valued expression, ví dụ `o` hoặc `o.customer`.
- Constructor expression `NEW ...`.

Kiểu của **mỗi expression** quyết định phần tử tương ứng trong kết quả nhiều mục chọn.

---

## 5. Kết hợp entity và scalar trong cùng hàng

JPQL cho phép chọn **entity cùng một hoặc nhiều thuộc tính** trong cùng một kết quả:

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o, c.fullName
        FROM PurchaseOrder o
        JOIN o.customer c
        ORDER BY o.id
        """,
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    PurchaseOrder order = (PurchaseOrder) row[0];
    String customerName = (String) row[1];

    System.out.println(
        order.getId() + " - " + customerName
    );
}
~~~

Trong mỗi hàng:

- `row[0]` là entity `PurchaseOrder` được JPA quản lý trong context đang hoạt động.
- `row[1]` là scalar `String`, không phải một entity.
- Sửa `order.changeStatus(...)` có thể được dirty checking đồng bộ trong transaction.
- Gán lại `customerName = "Tên mới"` chỉ thay đổi biến Java, không cập nhật `Customer.fullName`.

### 5.1. Chọn hai entity

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o, c
        FROM PurchaseOrder o
        JOIN o.customer c
        """,
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    PurchaseOrder order = (PurchaseOrder) row[0];
    Customer customer = (Customer) row[1];
}
~~~

Cả hai phần tử là entity-valued results. Nếu đang trong một persistence context, chúng có thể là managed entities, nhưng vẫn là **hai phần tử của một `Object[]`**, không phải một entity ghép.

### 5.2. Chọn ID của association khác chọn association

So sánh:

~~~jpql
SELECT o.customer.id
FROM PurchaseOrder o
~~~

Kết quả là `Long` (vì `Customer.id` là Long).

~~~jpql
SELECT o.customer
FROM PurchaseOrder o
~~~

Kết quả là entity `Customer`.

~~~jpql
SELECT o.customer.fullName
FROM PurchaseOrder o
~~~

Kết quả là `String`.

Đường dẫn có cùng tiền tố `o.customer` nhưng **điểm kết thúc path** quyết định kiểu biểu thức.

### 5.3. Có nên chọn cả entity và từng field của nó?

~~~jpql
SELECT o, o.id, o.status
FROM PurchaseOrder o
~~~

Câu này hợp lệ về ý tưởng kết hợp entity và scalar, nhưng nếu caller đã cần toàn bộ entity `o`, việc thêm `o.id`, `o.status` có thể chỉ làm kết quả phức tạp hơn mà không mang lại lợi ích rõ ràng.

Chỉ làm vậy khi có use case cụ thể, chẳng hạn entity cùng một aggregate hoặc một chỉ số phụ không nằm trong entity. Nếu cần vài field để dựng response, DTO projection thường thích hợp hơn.

---

## 6. DTO projection bằng constructor expression: SELECT NEW

`Object[]` dễ viết nhưng dễ sai vị trí và ép kiểu. Trong code ứng dụng dài hạn, một cách phổ biến là dùng **constructor expression**:

~~~jpql
SELECT NEW com.example.sales.dto.OrderSummary(
    o.id,
    c.fullName,
    o.status,
    o.totalAmount
)
FROM PurchaseOrder o
JOIN o.customer c
~~~

JPQL yêu cầu tên class DTO phù hợp với class được provider có thể khởi tạo; cách portable là sử dụng **tên lớp đầy đủ có package** trong `NEW`.

### 6.1. Khai báo DTO bằng record

~~~java
package com.example.sales.dto;

import com.example.sales.domain.OrderStatus;
import java.math.BigDecimal;

public record OrderSummary(
    Long orderId,
    String customerName,
    OrderStatus status,
    BigDecimal totalAmount
) {}
~~~

Truy vấn:

~~~java
List<OrderSummary> results = em.createQuery(
        """
        SELECT NEW com.example.sales.dto.OrderSummary(
            o.id,
            c.fullName,
            o.status,
            o.totalAmount
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        ORDER BY o.id
        """,
        OrderSummary.class
    )
    .getResultList();

for (OrderSummary dto : results) {
    System.out.println(
        dto.orderId() + ": " + dto.customerName()
    );
}
~~~

Record có canonical constructor với các tham số phù hợp và phù hợp cho projection trong các provider Jakarta Persistence hiện đại hỗ trợ cơ chế gọi constructor thông thường. Nếu dự án sử dụng JPA/Hibernate phiên bản cũ, cần xác minh khả năng sử dụng record và cách provider dựng đối tượng; có thể thay bằng POJO với public constructor tương ứng.

### 6.2. DTO bằng class bình thường

~~~java
package com.example.sales.dto;

import com.example.sales.domain.OrderStatus;
import java.math.BigDecimal;

public final class OrderSummary {
    private final Long orderId;
    private final String customerName;
    private final OrderStatus status;
    private final BigDecimal totalAmount;

    public OrderSummary(
        Long orderId,
        String customerName,
        OrderStatus status,
        BigDecimal totalAmount
    ) {
        this.orderId = orderId;
        this.customerName = customerName;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public Long getOrderId() {
        return orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
~~~

Class này có public constructor khớp đúng thứ tự/kiểu biểu thức ở `SELECT NEW`.

### 6.3. Điều kiện để constructor expression hoạt động

Cần chú ý:

1. Tên class DTO trong JPQL phải được phân giải được; dùng fully qualified class name là cách an toàn.
2. Số tham số của constructor phải khớp số biểu thức trong `NEW(...)`.
3. Thứ tự tham số phải khớp thứ tự expression.
4. Kiểu tham số phải tương thích với kiểu Java của expression, kể cả `Long`, `BigDecimal`, enum, `Instant` và nullable fields.
5. Provider phải có thể truy cập constructor phù hợp.
6. DTO không tự trở thành entity managed vì được tạo bởi JPQL `NEW`.

Ví dụ lỗi:

~~~jpql
SELECT NEW com.example.sales.dto.OrderSummary(
    o.id,
    o.totalAmount,
    c.fullName,
    o.status
)
FROM PurchaseOrder o
JOIN o.customer c
~~~

Trong DTO ở trên, constructor cần `Long, String, OrderStatus, BigDecimal`, nhưng thứ tự JPQL lại là `Long, BigDecimal, String, OrderStatus`. Provider có thể báo không tìm thấy constructor phù hợp.

### 6.4. DTO projection có lifecycle JPA không?

Một DTO như `OrderSummary`:

- Không được quản lý như entity `PurchaseOrder`.
- Không được dirty checking để tự lưu thay đổi.
- Không có `@Id` hay persistence identity.
- Không cần giữ persistence context mở chỉ để truy cập các field đã được truyền đầy đủ vào constructor.
- Phù hợp cho response API, bảng thống kê, báo cáo, danh sách read-only.

Nếu constructor expression chứa một **entity** làm tham số, entity object truyền vào có semantics JPA riêng; nhưng bản thân DTO vẫn không phải managed entity.

Ví dụ:

~~~java
public record OrderWithCustomer(
    PurchaseOrder order,
    String customerName
) {}
~~~

và:

~~~jpql
SELECT NEW com.example.sales.dto.OrderWithCustomer(
    o,
    c.fullName
)
FROM PurchaseOrder o
JOIN o.customer c
~~~

Trong trường hợp này DTO không managed, nhưng `o` bên trong DTO có thể là managed entity nếu context đang hoạt động. Đây không phải projection thuần scalar: cần xét serialization, lazy loading và ranh giới transaction.

### 6.5. Khi nào chọn DTO thay vì entity?

Ưu tiên DTO khi:

- Màn hình chỉ cần một tập trường xác định.
- Không cần sửa entity và dirty checking.
- Cần truyền dữ liệu sang API boundary mà không rò rỉ entity graph.
- Cần kết hợp field từ nhiều entity.
- Cần tạo tổng hợp/bảng báo cáo mà không có entity tương ứng.
- Muốn type-safe hơn so với cast `Object[]` thủ công.

Ưu tiên chọn entity khi:

- Đang thực hiện use case cần thay đổi trạng thái domain.
- Cần business method và quan hệ managed phù hợp.
- Cần làm việc với entity identity trong cùng transaction.
- Fetch plan đã được thiết kế để tránh tải dữ liệu quá mức.

---

## 7. Chọn nhiều biểu thức bằng Tuple

Một cách khác để đọc nhiều biểu thức là `Tuple` của JPA. `Tuple` cho phép truy cập theo vị trí hoặc alias, giúp tránh một phần lỗi nhớ chỉ số của `Object[]`.

### 7.1. JPQL Tuple trong cấu hình có hỗ trợ

Một số phiên bản/provider JPA hỗ trợ tạo `Tuple` trực tiếp từ JPQL:

~~~java
import jakarta.persistence.Tuple;

List<Tuple> rows = em.createQuery(
        """
        SELECT o.id AS orderId,
               o.totalAmount AS amount
        FROM PurchaseOrder o
        ORDER BY o.id
        """,
        Tuple.class
    )
    .getResultList();

for (Tuple row : rows) {
    Long id = row.get("orderId", Long.class);
    BigDecimal amount =
        row.get("amount", BigDecimal.class);
}
~~~

Việc hỗ trợ **string-based JPQL `Tuple.class`** và chi tiết alias có thể khác nhau giữa các phiên bản/spec/provider. Nếu môi trường không hỗ trợ cách này, không cố cast `Object[]` thành `Tuple`; hãy dùng **CriteriaQuery<Tuple>** theo API JPA hoặc constructor DTO để có lựa chọn rõ ràng.

### 7.2. CriteriaQuery<Tuple>

Đây là cách biểu diễn Tuple qua Criteria API:

~~~java
import jakarta.persistence.Tuple;
import jakarta.persistence.criteria.*;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> query = cb.createTupleQuery();

Root<PurchaseOrder> order =
    query.from(PurchaseOrder.class);

query.multiselect(
    order.get("id").alias("orderId"),
    order.get("totalAmount").alias("amount")
);

query.orderBy(cb.asc(order.get("id")));

List<Tuple> rows = em.createQuery(query).getResultList();

for (Tuple row : rows) {
    Long id = row.get("orderId", Long.class);
    BigDecimal amount =
        row.get("amount", BigDecimal.class);
}
~~~

`Tuple` không phải entity; nó chỉ là một cấu trúc chứa các mục select.

### 7.3. Tuple có type-safe hoàn toàn không?

Không. Dù dùng:

~~~java
row.get("orderId", Long.class)
~~~

lỗi alias hoặc kiểu không phù hợp có thể chỉ xuất hiện khi chạy. Criteria với JPA static metamodel có thể cải thiện phần kiểm tra đường thuộc tính, nhưng `Tuple` vẫn cần cấu hình alias/kiểu chính xác.

So với `Object[]`:

| Cách lấy kết quả | Ưu điểm | Hạn chế |
|---|---|---|
| `Object[]` | Đơn giản, tiện cho ví dụ và query ngắn | Phụ thuộc vị trí, nhiều cast, khó refactor |
| `Tuple` | Có thể đọc bằng alias và kiểu | Alias/type vẫn kiểm tra runtime; mức hỗ trợ JPQL trực tiếp tùy provider |
| `SELECT NEW DTO` | Kết quả có kiểu chuyên biệt, dễ dùng qua nhiều tầng | Cần constructor khớp; thay đổi SELECT phải đi cùng DTO |
| Entity | Managed identity và business methods | Có thể tải dư; không phù hợp cho report chỉ cần vài field |

Với một endpoint thường xuyên sử dụng cùng projection, constructor DTO thường dễ bảo trì hơn mảng Object[].

---

## 8. DISTINCT: chọn kết quả không trùng

Giả sử muốn tên tất cả khách hàng đã từng có đơn hàng:

~~~java
List<String> names = em.createQuery(
        """
        SELECT o.customer.fullName
        FROM PurchaseOrder o
        """,
        String.class
    )
    .getResultList();
~~~

Với dữ liệu minh họa:

~~~text
An
An
Bình
~~~

Thêm `DISTINCT`:

~~~java
List<String> names = em.createQuery(
        """
        SELECT DISTINCT o.customer.fullName
        FROM PurchaseOrder o
        """,
        String.class
    )
    .getResultList();
~~~

Kết quả về mặt giá trị:

~~~text
An
Bình
~~~

**Lưu ý:** distinct tên không đồng nghĩa distinct khách hàng. Nếu hai khách khác nhau cùng tên “An”, việc `SELECT DISTINCT c.fullName` sẽ gộp họ thành một chuỗi duy nhất. Nếu cần phân biệt khách hàng, hãy chọn entity/ID hoặc DTO chứa ID.

### 8.1. DISTINCT entity root khi JOIN collection

Giả sử Order 101 có hai OrderLine:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        JOIN o.lines l
        WHERE l.productCode = :sku
        """,
        PurchaseOrder.class
    )
    .setParameter("sku", "BOOK-101")
    .getResultList();
~~~

Nếu một Order có nhiều dòng phù hợp điều kiện, join có thể tạo nhiều hàng trung gian cho cùng Order. `DISTINCT` giúp diễn đạt ý định trả **các Order duy nhất**.

Chi tiết khử trùng lặp giữa SQL và entity materialization có thể khác theo provider/version, đặc biệt khi fetch join collection. Không suy ra `DISTINCT` luôn loại bỏ chi phí join ở database hoặc tự tối ưu mọi tình huống phân trang.

### 8.2. DISTINCT với nhiều scalar expressions

~~~jpql
SELECT DISTINCT o.status, o.totalAmount
FROM PurchaseOrder o
~~~

Mỗi **cặp** `(status, totalAmount)` được xét để loại trùng, không phải từng cột độc lập.

Ví dụ:

~~~text
(PAID, 300000)
(PAID, 300000)
(NEW, 300000)
~~~

Sau DISTINCT:

~~~text
(PAID, 300000)
(NEW, 300000)
~~~

Không nên mong `DISTINCT` chỉ gộp theo `status` nhưng vẫn lấy tùy ý `totalAmount`; nếu cần một hàng mỗi status với số tiền tổng cộng, dùng `GROUP BY` và aggregate.

### 8.3. DISTINCT và ORDER BY

Kết hợp `DISTINCT` với `ORDER BY` có những hạn chế về expression được dùng để sắp xếp theo quy tắc JPQL/provider/SQL dialect. Với projection đặc biệt, nên ưu tiên sắp theo giá trị được chọn hoặc đảm bảo truy vấn tương thích với DBMS thực tế. Không mặc định một truy vấn DISTINCT chọn vài scalar có thể ORDER BY bất kỳ cột không nằm trong select list trên mọi DBMS.

---

## 9. JOIN ảnh hưởng đến kết quả được chọn như thế nào?

JPQL JOIN cho phép kết hợp các đối tượng liên quan qua association:

~~~jpql
SELECT o.id, c.fullName
FROM PurchaseOrder o
JOIN o.customer c
~~~

`JOIN o.customer c` điều hướng thuộc tính `customer` của `PurchaseOrder` chứ không viết điều kiện khóa ngoại bằng tên cột SQL như:

~~~sql
-- SQL:
FROM purchase_orders o
JOIN customers c ON o.customer_id = c.id
~~~

JPA provider dựa trên mapping `@ManyToOne` để biết cách join.

### 9.1. JOIN không quyết định kiểu trả về — SELECT mới quyết định

Cùng `FROM/JOIN`:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
~~~

trả `PurchaseOrder`.

~~~jpql
SELECT c.fullName
FROM PurchaseOrder o
JOIN o.customer c
~~~

trả `String`.

~~~jpql
SELECT o.id, c.fullName
FROM PurchaseOrder o
JOIN o.customer c
~~~

trả nhiều mục, thường `Object[]`.

~~~jpql
SELECT NEW com.example.sales.dto.OrderSummary(
    o.id, c.fullName, o.status, o.totalAmount
)
FROM PurchaseOrder o
JOIN o.customer c
~~~

trả `OrderSummary`.

Do đó khi debug kiểu kết quả, hãy bắt đầu ở **SELECT clause** thay vì chỉ nhìn FROM hoặc JOIN.

### 9.2. INNER JOIN và LEFT JOIN

Nếu association có thể null, `INNER JOIN` thường loại các hàng không có đối tượng liên quan, trong khi `LEFT JOIN` giữ hàng phía trái và đặt phần liên quan bằng null.

Trong mô hình Order–Customer ở ví dụ, `customer` được khai báo `optional = false` nên mỗi Order hợp lệ phải có Customer. Để minh họa LEFT JOIN rõ hơn, dùng collection `o.lines` có thể rỗng:

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o.id, l.productCode
        FROM PurchaseOrder o
        LEFT JOIN o.lines l
        ORDER BY o.id
        """,
        Object[].class
    )
    .getResultList();
~~~

Với Order có hai dòng, sẽ xuất hiện hai hàng cho cùng Order. Với Order chưa có dòng, LEFT JOIN có thể trả một hàng mà `productCode` là null.

Ví dụ khái niệm:

| Order ID | productCode |
|---:|---|
| 101 | BOOK-101 |
| 101 | BOOK-102 |
| 102 | BOOK-103 |
| 103 | null |

Nếu dùng `JOIN o.lines l` (inner join), Order 103 không có dòng sẽ không xuất hiện.

### 9.3. Số lượng hàng có thể tăng do join collection

Nếu một Order có 5 dòng, câu:

~~~jpql
SELECT o.id, l.productCode
FROM PurchaseOrder o
JOIN o.lines l
~~~

có thể trả 5 hàng cho Order đó. Đây là điều đúng: mỗi hàng đại diện một tổ hợp `Order × OrderLine`.

Nếu mục tiêu là **mỗi Order một hàng** với số lượng dòng, nên dùng aggregate:

~~~jpql
SELECT o.id, COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
GROUP BY o.id
~~~

Kết quả của một Order không có line là count bằng 0, thay vì phải nhận một `Object[]` có `productCode = null` và tự đếm.

### 9.4. FETCH JOIN dùng cho entity graph, không phải scalar projection

Ví dụ tải Order cùng lines:

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        """,
        PurchaseOrder.class
    )
    .getResultList();
~~~

`JOIN FETCH` được dùng để tải association như một phần fetch plan của entity được chọn. Nó **khác** với một phép join thông thường phục vụ scalar projection:

~~~jpql
SELECT o.id, l.productCode
FROM PurchaseOrder o
JOIN o.lines l
~~~

Không dùng `JOIN FETCH` một cách máy móc khi `SELECT NEW DTO(...)` hoặc chỉ chọn scalar, vì fetch join có các quy tắc về owner entity được trả và có thể gây lỗi provider hoặc làm query khó hiểu. Với DTO, `JOIN` thông thường là lựa chọn đúng hơn.

---

## 10. Hàm và biểu thức trong SELECT

Ngoài property paths, JPQL cho phép chọn các biểu thức tính toán hoặc hàm.

### 10.1. CONCAT, UPPER và LOWER

~~~java
List<String> labels = em.createQuery(
        """
        SELECT CONCAT(c.fullName, ' <', c.email, '>')
        FROM Customer c
        ORDER BY c.fullName
        """,
        String.class
    )
    .getResultList();
~~~

Ví dụ dùng nhiều tham số cho `CONCAT`; khả năng diễn giải cụ thể phụ thuộc phiên bản chuẩn/provider. Với yêu cầu portable nhất qua nhiều phiên bản JPA cũ, có thể dùng lồng `CONCAT(CONCAT(...), ...)` hoặc xử lý định dạng nhãn ở tầng Java.

Hàm chuẩn khác:

~~~jpql
SELECT UPPER(c.fullName)
FROM Customer c
~~~

~~~jpql
SELECT LOWER(c.email)
FROM Customer c
~~~

Kết quả thường là `String`.

### 10.2. COALESCE

Khi một biểu thức có thể null, `COALESCE` chọn giá trị đầu tiên không null:

~~~jpql
SELECT COALESCE(c.email, 'unknown@example.com')
FROM Customer c
~~~

Trong schema minh họa, `email` được NOT NULL nên COALESCE không cần thiết. Với field thực sự tùy chọn, nó có ích cho projection và báo cáo.

Không dùng `COALESCE` như cách che giấu dữ liệu không hợp lệ mà nghiệp vụ cần phát hiện.

### 10.3. CASE WHEN

Ví dụ tạo nhãn theo trạng thái:

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o.id,
               CASE
                   WHEN o.status = :paid THEN 'Đã thanh toán'
                   WHEN o.status = :cancelled THEN 'Đã hủy'
                   ELSE 'Đang xử lý'
               END
        FROM PurchaseOrder o
        """,
        Object[].class
    )
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("cancelled", OrderStatus.CANCELLED)
    .getResultList();
~~~

Mỗi hàng có:

- `row[0]`: Long.
- `row[1]`: String nhãn hiển thị.

Nếu cần đa ngôn ngữ và thông điệp thay đổi theo locale, thường nên trả enum/state rồi dịch ở presentation layer. Câu CASE chỉ là ví dụ biểu thức chọn kết quả.

### 10.4. Phép toán số học

~~~jpql
SELECT o.id,
       o.totalAmount,
       o.totalAmount * 2
FROM PurchaseOrder o
~~~

Cách dùng biểu thức số học nên tương thích kiểu dữ liệu và độ chính xác. Với `BigDecimal`, các đặc điểm precision, scale và phép toán của database có thể ảnh hưởng tới kiểu/giá trị trả về.

### 10.5. Biểu thức và tên thuộc tính Java

Không viết tên cột SQL trong các expression:

~~~jpql
-- Không đúng với tên property đã khai báo:
SELECT o.total_amount
FROM PurchaseOrder o
~~~

Dùng:

~~~jpql
SELECT o.totalAmount
FROM PurchaseOrder o
~~~

Nếu cần các hàm SQL riêng DBMS, JPA có `FUNCTION(...)` hoặc các extension provider, nhưng phần đó làm giảm tính portable và không phải điều kiện để hiểu lựa chọn cơ bản trong SELECT.

---

## 11. Hàm tổng hợp: COUNT, SUM, AVG, MIN, MAX

JPQL hỗ trợ aggregate expressions khi muốn trả một giá trị tổng hợp thay vì từng entity.

### 11.1. COUNT trả Long

~~~java
Long count = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o",
        Long.class
    )
    .getSingleResult();
~~~

Với ba Order trong ví dụ, kết quả là `3L`. **COUNT theo JPQL có kiểu kết quả Long**, không phải Integer, dù kết quả nhỏ.

Sai:

~~~java
// Không nên ép count về Integer.
Integer count = (Integer) em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o"
).getSingleResult();
~~~

Điều này có thể gây ClassCastException.

### 11.2. SUM trên BigDecimal

~~~java
BigDecimal total = em.createQuery(
        """
        SELECT SUM(o.totalAmount)
        FROM PurchaseOrder o
        WHERE o.status = :status
        """,
        BigDecimal.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
~~~

Với đơn 102 = 300000 và 103 = 180000, tổng là 480000.

Tuy nhiên, nếu không có hàng phù hợp, `SUM(...)` có thể trả `null`, trong khi `COUNT(...)` trả 0. Khi cần giá trị mặc định:

~~~java
BigDecimal totalOrZero = em.createQuery(
        """
        SELECT COALESCE(
            SUM(o.totalAmount),
            :zero
        )
        FROM PurchaseOrder o
        WHERE o.status = :status
        """,
        BigDecimal.class
    )
    .setParameter("zero", BigDecimal.ZERO)
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
~~~

Cần chọn kiểu parameter `:zero` tương thích với aggregate expression và xác minh trên provider đang dùng.

### 11.3. AVG thường trả Double

~~~java
Double average = em.createQuery(
        """
        SELECT AVG(o.totalAmount)
        FROM PurchaseOrder o
        """,
        Double.class
    )
    .getSingleResult();
~~~

Theo quy tắc aggregate type của JPQL, `AVG` thường trả `Double`, kể cả khi thuộc tính nguồn là kiểu số khác. Khi cần độ chính xác kế toán, hãy thiết kế rõ việc làm tròn và cách tính trung bình thay vì mặc định dùng Double cho dữ liệu tiền.

### 11.4. MIN và MAX

~~~java
BigDecimal maxTotal = em.createQuery(
        "SELECT MAX(o.totalAmount) FROM PurchaseOrder o",
        BigDecimal.class
    )
    .getSingleResult();
~~~

`MIN`/`MAX` trả giá trị kiểu tương ứng với biểu thức đầu vào khi có hàng phù hợp. Với tập rỗng, chúng có thể trả null.

Bảng tổng quan:

| Expression | Kiểu kết quả JPQL phổ biến | Khi không có giá trị phù hợp |
|---|---|---|
| `COUNT(o)` | `Long` | 0 |
| `SUM(o.totalAmount)` khi BigDecimal | `BigDecimal` | null |
| `AVG(o.totalAmount)` | `Double` | null |
| `MIN(o.totalAmount)` | `BigDecimal` | null |
| `MAX(o.totalAmount)` | `BigDecimal` | null |

Với `SUM` trên một số kiểu số nguyên hoặc floating point, quy tắc kiểu trả về của JPA có thể khác kiểu field nguồn. Không ép kiểu theo cảm tính; dùng kiểu phù hợp với chuẩn và kiểm tra provider/version.

---

## 12. Chọn nhiều aggregate cùng lúc

Muốn một hàng có số đơn và tổng tiền:

~~~java
Object[] result = em.createQuery(
        """
        SELECT COUNT(o), SUM(o.totalAmount)
        FROM PurchaseOrder o
        """,
        Object[].class
    )
    .getSingleResult();

Long orderCount = (Long) result[0];
BigDecimal sum = (BigDecimal) result[1];
~~~

Ở đây câu SELECT có hai expressions nên kết quả là `Object[]`, dù chỉ trả **một hàng tổng hợp**.

Đừng nhầm:

- **Số hàng** kết quả: một hàng.
- **Số biểu thức** trong hàng: hai.
- **Kiểu Java** của hàng: `Object[]`.

Nếu muốn DTO:

~~~java
package com.example.sales.dto;

import java.math.BigDecimal;

public record OrderTotals(
    Long orderCount,
    BigDecimal totalAmount
) {}
~~~

JPQL:

~~~java
OrderTotals totals = em.createQuery(
        """
        SELECT NEW com.example.sales.dto.OrderTotals(
            COUNT(o),
            SUM(o.totalAmount)
        )
        FROM PurchaseOrder o
        """,
        OrderTotals.class
    )
    .getSingleResult();
~~~

Khi bảng không có Order, `orderCount` có thể bằng 0L và `totalAmount` là null. DTO/service cần xử lý semantics này nếu caller muốn tổng bằng 0.

---

## 13. GROUP BY: một hàng kết quả cho mỗi nhóm

Ví dụ cần bảng tổng số đơn và doanh thu theo trạng thái:

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o.status,
               COUNT(o),
               SUM(o.totalAmount)
        FROM PurchaseOrder o
        GROUP BY o.status
        ORDER BY o.status
        """,
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    OrderStatus status = (OrderStatus) row[0];
    Long count = (Long) row[1];
    BigDecimal total = (BigDecimal) row[2];

    System.out.println(status + ": " + count + ", " + total);
}
~~~

Với dữ liệu minh họa:

| status | COUNT(o) | SUM(totalAmount) |
|---|---:|---:|
| NEW | 1 | 120000 |
| PAID | 2 | 480000 |

Không có nhóm CANCELLED nếu không có đơn CANCELLED, trừ khi câu truy vấn lấy tập trạng thái bên ngoài rồi LEFT JOIN/ghép kết quả theo cách phù hợp.

### 13.1. Chọn thuộc tính không aggregate cần GROUP BY phù hợp

Một truy vấn chưa đầy đủ:

~~~jpql
SELECT c.fullName, COUNT(o)
FROM PurchaseOrder o
JOIN o.customer c
~~~

Nếu muốn một hàng cho mỗi tên khách hàng, phải dùng GROUP BY hợp lệ:

~~~jpql
SELECT c.fullName, COUNT(o)
FROM PurchaseOrder o
JOIN o.customer c
GROUP BY c.fullName
~~~

Nhưng nếu hai khách trùng tên, chúng bị gộp thành một nhóm. Muốn nhóm theo khách hàng riêng biệt, dùng identity:

~~~jpql
SELECT c.id, c.fullName, COUNT(o)
FROM PurchaseOrder o
JOIN o.customer c
GROUP BY c.id, c.fullName
ORDER BY c.id
~~~

Các biểu thức non-aggregate trong SELECT cần tuân thủ các quy tắc GROUP BY của JPQL/DBMS. Không giả định database sẽ chọn đại một giá trị của cột chưa được group.

### 13.2. DTO aggregate theo khách hàng

DTO:

~~~java
package com.example.sales.dto;

import java.math.BigDecimal;

public record CustomerOrderStats(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal totalAmount
) {}
~~~

Query:

~~~java
List<CustomerOrderStats> stats = em.createQuery(
        """
        SELECT NEW com.example.sales.dto.CustomerOrderStats(
            c.id,
            c.fullName,
            COUNT(o),
            SUM(o.totalAmount)
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        GROUP BY c.id, c.fullName
        ORDER BY c.id
        """,
        CustomerOrderStats.class
    )
    .getResultList();
~~~

Một DTO có thể kết hợp hai scalar fields với hai aggregate expressions; không cần tạo entity `CustomerOrderStats` chỉ để nhận báo cáo.

### 13.3. HAVING lọc nhóm, WHERE lọc hàng

Ví dụ chỉ hiển thị khách hàng có ít nhất hai đơn:

~~~jpql
SELECT c.id, c.fullName, COUNT(o)
FROM PurchaseOrder o
JOIN o.customer c
GROUP BY c.id, c.fullName
HAVING COUNT(o) >= :minimumOrders
~~~

Khác biệt:

- `WHERE` lọc các hàng trước khi nhóm.
- `GROUP BY` tạo các nhóm.
- `HAVING` lọc nhóm dựa vào aggregate/điều kiện nhóm.
- `SELECT` quyết định giá trị cuối cùng trong từng hàng kết quả.

Đừng sử dụng alias của constructor DTO như một entity path ở WHERE/HAVING. Các thành phần aggregate phải được biểu diễn đúng theo cú pháp JPQL.

### 13.4. LEFT JOIN để giữ nhóm có số lượng 0

Nếu muốn liệt kê mọi Customer kể cả chưa có Order:

~~~jpql
SELECT c.id, c.fullName, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id, c.fullName
ORDER BY c.id
~~~

Lúc này Customer không có đơn vẫn có thể xuất hiện với `COUNT(o) = 0`.

Nếu thay `COUNT(o)` bằng `COUNT(*)` thì cần kiểm tra cú pháp hỗ trợ và ngữ nghĩa với LEFT JOIN; trong JPQL portable, `COUNT(o)` biểu đạt rõ việc đếm non-null entity o, nên phù hợp cho số đơn.

---

## 14. getResultList(), getSingleResult() và kiểu kết quả

Chọn entity, scalar hay nhiều mục **không quyết định** API truy xuất một hay nhiều hàng. Số lượng hàng do query thực sự trả về.

### 14.1. getResultList() cho 0..N hàng

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE o.status = :status
        """,
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.CANCELLED)
    .getResultList();
~~~

Nếu không có đơn CANCELLED, `getResultList()` trả **danh sách rỗng**, không trả null.

Với scalar:

~~~java
List<Long> ids = em.createQuery(
        """
        SELECT o.id
        FROM PurchaseOrder o
        WHERE o.status = :status
        """,
        Long.class
    )
    .setParameter("status", OrderStatus.CANCELLED)
    .getResultList();
~~~

Tương tự, nếu không có hàng, kết quả là danh sách rỗng.

### 14.2. getSingleResult() cho đúng một hàng

~~~java
PurchaseOrder order = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE o.id = :id
        """,
        PurchaseOrder.class
    )
    .setParameter("id", 101L)
    .getSingleResult();
~~~

Nếu query trả:

- 0 hàng: `getSingleResult()` thông thường ném `NoResultException`.
- Đúng 1 hàng: trả phần tử đó.
- Nhiều hơn 1 hàng: ném `NonUniqueResultException`.

Vì vậy `getSingleResult()` khác với `EntityManager.find()`: `find()` trả `null` khi không tìm thấy PK, còn `getSingleResult()` theo quy tắc trên báo không có hàng bằng exception.

Có thể dùng `getResultStream().findFirst()` hoặc API `getSingleResultOrNull()` ở những phiên bản JPA hỗ trợ khi thích hợp, nhưng cần hiểu thứ tự và semantics trước khi coi kết quả đầu tiên là đủ. Ví dụ `findFirst()` trên query không ORDER BY có thể chọn một hàng không ổn định.

### 14.3. Aggregate chỉ tạo một hàng kết quả?

Với câu:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
~~~

`COUNT` không có `GROUP BY` trả một giá trị tổng hợp, kể cả khi bảng trống (0).

Nhưng:

~~~jpql
SELECT o.status, COUNT(o)
FROM PurchaseOrder o
GROUP BY o.status
~~~

trả **nhiều hàng** — một hàng cho mỗi nhóm status hiện diện. Không dùng `getSingleResult()` cho truy vấn nhóm nếu không bảo đảm chỉ có một nhóm.

### 14.4. Projection nhiều biểu thức và getSingleResult()

~~~java
Object[] result = em.createQuery(
        """
        SELECT o.id, o.totalAmount
        FROM PurchaseOrder o
        WHERE o.id = :id
        """,
        Object[].class
    )
    .setParameter("id", 101L)
    .getSingleResult();
~~~

Kết quả là `Object[]` dù chỉ một Order được trả. Số lượng hàng bằng 1 không biến nhiều biểu thức thành một scalar.

---

## 15. Type-safe query và việc ép kiểu

Sử dụng `TypedQuery<T>` giúp Java biết kiểu **của mỗi hàng**:

~~~java
TypedQuery<PurchaseOrder> q1 = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

TypedQuery<BigDecimal> q2 = em.createQuery(
    "SELECT o.totalAmount FROM PurchaseOrder o",
    BigDecimal.class
);

TypedQuery<Object[]> q3 = em.createQuery(
    "SELECT o.id, o.status FROM PurchaseOrder o",
    Object[].class
);

TypedQuery<OrderSummary> q4 = em.createQuery(
    """
    SELECT NEW com.example.sales.dto.OrderSummary(
        o.id, c.fullName, o.status, o.totalAmount
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    """,
    OrderSummary.class
);
~~~

Tương ứng:

| JPQL SELECT | Kiểu của một result row | TypedQuery |
|---|---|---|
| `SELECT o` | `PurchaseOrder` | `TypedQuery<PurchaseOrder>` |
| `SELECT o.id` | `Long` | `TypedQuery<Long>` |
| `SELECT o.totalAmount` | `BigDecimal` | `TypedQuery<BigDecimal>` |
| `SELECT o.id, o.status` | `Object[]` | `TypedQuery<Object[]>` |
| `SELECT NEW ...OrderSummary(...)` | `OrderSummary` | `TypedQuery<OrderSummary>` |
| `SELECT COUNT(o)` | `Long` | `TypedQuery<Long>` |
| `SELECT c.id, COUNT(o) ... GROUP BY...` | `Object[]` | `TypedQuery<Object[]>` |

### 15.1. TypedQuery không tự kiểm tra toàn bộ JPQL lúc biên dịch Java

Java compiler biết `q2` trả `BigDecimal`, nhưng JPQL truyền vào `createQuery(...)` vẫn là **chuỗi**. Nếu sai tên entity/field hoặc constructor signature, lỗi có thể chỉ phát sinh khi khởi tạo/thực thi query.

Vì vậy:

- Dùng IDE/tooling có hiểu JPQL nếu có.
- Dùng integration tests cho các query quan trọng.
- Nếu cần type-safe path hơn, cân nhắc Criteria API và JPA static metamodel hoặc các query DSL tương thích.
- Không dựa hoàn toàn vào generic type để tin rằng JPQL có cú pháp và kiểu đúng.

### 15.2. Không dùng raw Query tùy tiện

~~~java
Query raw = em.createQuery(
    "SELECT o.id FROM PurchaseOrder o"
);

Object result = raw.getSingleResult();
~~~

Cách này có thể sử dụng nhưng caller phải cast. Với query có kiểu rõ, `TypedQuery<Long>` diễn đạt intent tốt hơn.

---

## 16. Phân trang và sắp xếp projection

Danh sách Order có thể rất lớn. JPQL cho phép phân trang bằng API query:

~~~java
List<OrderSummary> page = em.createQuery(
        """
        SELECT NEW com.example.sales.dto.OrderSummary(
            o.id,
            c.fullName,
            o.status,
            o.totalAmount
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        OrderSummary.class
    )
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Ở đây:

- `setFirstResult(0)` bắt đầu từ phần tử đầu tiên theo chỉ số 0.
- `setMaxResults(20)` giới hạn tối đa 20 phần tử.
- `ORDER BY` giúp thứ tự ổn định; thêm `o.id` làm tie-breaker khi thời điểm tạo trùng nhau.
- Constructor projection lấy những trường cần thiết cho danh sách, thay vì buộc tải toàn bộ entity graph.

### 16.1. Vì sao tránh collection FETCH JOIN khi phân trang?

Nếu query fetch join `o.lines`, một Order có nhiều dòng làm số hàng SQL trung gian tăng. Provider có thể phải xử lý distinct/deduplication trong bộ nhớ hoặc sinh warning/hạn chế phân trang chính xác.

Với màn hình danh sách đơn, **DTO projection của Order và Customer** thường dễ phân trang hơn. Nếu cần chi tiết nhiều dòng cho một Order, có thể query riêng hoặc dùng chiến lược fetch phù hợp ở use case chi tiết.

### 16.2. Query COUNT riêng cho tổng số phần tử

Để hiển thị tổng số Order PAID:

~~~java
Long totalRows = em.createQuery(
        """
        SELECT COUNT(o)
        FROM PurchaseOrder o
        WHERE o.status = :status
        """,
        Long.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
~~~

Một trang kết quả và một tổng số hàng thường là hai query riêng. Cần hiểu tính nhất quán thời điểm đọc nếu các transaction khác đang thêm/xóa Order giữa hai câu query; transaction isolation quyết định mức độ nhất quán quan sát được.

---

## 17. Chọn biểu thức NULL và cách đọc kết quả

Không phải mọi scalar projection đều có giá trị khác null. Ví dụ với `LEFT JOIN`:

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o.id, l.productCode
        FROM PurchaseOrder o
        LEFT JOIN o.lines l
        """,
        Object[].class
    )
    .getResultList();
~~~

Nếu Order không có dòng:

~~~java
Long orderId = (Long) row[0];
String productCode = (String) row[1]; // Có thể null.
~~~

Cast null sang reference type Java không gây ClassCastException, nhưng sử dụng `productCode.length()` mà không kiểm tra sẽ gây `NullPointerException`.

### 17.1. Primitive DTO constructor có thể gặp null

Giả sử DTO có constructor nhận `long` hoặc `double`, nhưng biểu thức JPQL có thể null. Provider không thể truyền null vào primitive parameter theo cách bình thường.

Khi projection có thể thiếu giá trị, ưu tiên wrapper types phù hợp (`Long`, `Double`) hoặc `COALESCE` có semantics rõ ràng.

Ví dụ:

~~~java
public record OptionalProductLabel(
    Long orderId,
    String productCode
) {}
~~~

Còn:

~~~java
public record CountByOrder(
    Long orderId,
    Long lineCount
) {}
~~~

Với `COUNT(l)` và LEFT JOIN, lineCount là 0L khi không có dòng, không phải null.

### 17.2. NULL trong aggregate

Không có bản ghi phù hợp:

- `COUNT(...)` → 0L.
- `SUM(...)`, `AVG(...)`, `MIN(...)`, `MAX(...)` → thường null.

Không dùng `new BigDecimal(...)` trực tiếp từ một kết quả aggregate có thể null trước khi kiểm tra.

---

## 18. Viết code rõ ràng khi cần nhiều cột

Có ba cách triển khai một use case hiển thị danh sách đơn:

### 18.1. Cách A — chọn entity

~~~java
List<PurchaseOrder> orders = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        ORDER BY o.createdAt DESC
        """,
        PurchaseOrder.class
    )
    .getResultList();
~~~

**Ưu điểm:** Có entity và business methods, dùng tiếp trong transaction.

**Nhược điểm:** Nếu chỉ cần bốn field để hiển thị, có thể tải nhiều state hơn cần thiết; truy cập `o.customer.fullName` có thể tạo thêm SQL tùy fetch.

### 18.2. Cách B — chọn Object[]

~~~java
List<Object[]> rows = em.createQuery(
        """
        SELECT o.id, c.fullName, o.status, o.totalAmount
        FROM PurchaseOrder o
        JOIN o.customer c
        """,
        Object[].class
    )
    .getResultList();
~~~

**Ưu điểm:** Nhanh để thử query, không cần class DTO.

**Nhược điểm:** Phụ thuộc vị trí và cast, khó đọc ở service lớn, dễ lỗi khi đổi thứ tự expression.

### 18.3. Cách C — constructor DTO

~~~java
List<OrderSummary> rows = em.createQuery(
        """
        SELECT NEW com.example.sales.dto.OrderSummary(
            o.id, c.fullName, o.status, o.totalAmount
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        """,
        OrderSummary.class
    )
    .getResultList();
~~~

**Ưu điểm:** Return type rõ nghĩa, thuận tiện cho API, giảm rò rỉ entity graph và lỗi cast ở tầng sử dụng.

**Nhược điểm:** Cần bảo trì DTO constructor cùng query và phải kiểm tra provider có hỗ trợ kiểu DTO cụ thể.

### 18.4. Lựa chọn theo mục tiêu

| Mục tiêu | Lựa chọn thường phù hợp |
|---|---|
| Sửa trạng thái một Order trong transaction | Entity `SELECT o` hoặc `find()` |
| Lấy danh sách ID | Scalar `SELECT o.id` |
| Lấy danh sách tổng tiền | Scalar `SELECT o.totalAmount` |
| Báo cáo ad hoc ngắn | `Object[]` hoặc Tuple |
| API danh sách với 4–8 trường cố định | Constructor DTO |
| Báo cáo nhóm theo khách và trạng thái | Aggregate + GROUP BY + DTO/Object[] |
| Cần object graph có association | Entity query và fetch plan rõ ràng |
| Query phức tạp cần type-safe path | Criteria API/static metamodel hoặc query DSL |

---

## 19. Các lỗi thường gặp

### Lỗi 1 — Dùng tên bảng/cột SQL trong JPQL

~~~jpql
-- Sai nếu entity name là PurchaseOrder:
SELECT total_amount FROM purchase_orders
~~~

Sửa:

~~~jpql
SELECT o.totalAmount FROM PurchaseOrder o
~~~

### Lỗi 2 — Dùng TypedQuery<Entity> cho nhiều scalar

~~~java
em.createQuery(
    "SELECT o.id, o.status FROM PurchaseOrder o",
    PurchaseOrder.class
);
~~~

Không thể giả định hai biểu thức tạo ra một `PurchaseOrder`.

Sửa:

~~~java
em.createQuery(
    "SELECT o.id, o.status FROM PurchaseOrder o",
    Object[].class
);
~~~

hoặc `SELECT NEW` DTO tương ứng.

### Lỗi 3 — Cast COUNT thành Integer

~~~java
Integer count = (Integer) em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o"
).getSingleResult();
~~~

Sai kiểu; COUNT chuẩn trả Long.

### Lỗi 4 — Đổi thứ tự SELECT nhưng không đổi vị trí mảng

Nếu JPQL đổi `SELECT o.id, o.status` thành `SELECT o.status, o.id`, các cast `row[0]`/`row[1]` phải đổi tương ứng. DTO sẽ khiến sai thứ tự/kiểu được phát hiện rõ hơn.

### Lỗi 5 — Cho rằng scalar projection là managed entity

~~~java
BigDecimal total = em.createQuery(
    "SELECT o.totalAmount FROM PurchaseOrder o",
    BigDecimal.class
).getSingleResult();
~~~

`total` là giá trị, không phải một entity managed. Việc thay biến Java không cập nhật `PurchaseOrder`.

### Lỗi 6 — SELECT NEW nhưng constructor không khớp

Tên class sai package, thiếu constructor, thứ tự/kiểu tham số không phù hợp đều có thể khiến query thất bại.

### Lỗi 7 — JOIN collection rồi tưởng mỗi Order chỉ có một hàng

~~~jpql
SELECT o.id, l.productCode
FROM PurchaseOrder o
JOIN o.lines l
~~~

Một Order có N lines có thể tạo N hàng. Nếu cần một hàng mỗi Order, dùng DISTINCT/aggregate hoặc cấu trúc projection phù hợp.

### Lỗi 8 — Không phân biệt JOIN và JOIN FETCH

JOIN để lọc/kết hợp dữ liệu; FETCH JOIN để nạp association cho entity query. Không tự thêm FETCH vào projection scalar/DTO.

### Lỗi 9 — Dùng DISTINCT trên tên rồi nghĩ đã khử trùng khách hàng

Hai Customer cùng tên có thể bị gộp. Dùng entity identity/ID khi cần phân biệt cá thể.

### Lỗi 10 — Không có ORDER BY khi phân trang

Nếu không có thứ tự rõ, các trang có thể bị xáo trộn khi database chọn plan khác hoặc có dữ liệu thay đổi. Dùng ORDER BY ổn định, ưu tiên tie-breaker duy nhất.

### Lỗi 11 — Dùng getSingleResult cho query có thể trả nhiều hàng

Nếu có nhiều Order phù hợp, `NonUniqueResultException`. Nếu không có hàng, `NoResultException`. Chọn API theo cardinality kỳ vọng thực tế.

### Lỗi 12 — Không xử lý NULL trong LEFT JOIN hoặc aggregate

Scalar String ở phía optional có thể null; SUM/AVG/MIN/MAX có thể null trên tập không có giá trị. Dùng wrapper/COALESCE hoặc kiểm tra đúng ngữ nghĩa.

### Lỗi 13 — Cho rằng TypedQuery bảo đảm query đúng lúc compile

JPQL string vẫn có thể sai field, alias hoặc constructor. Generic Java không thay validation runtime/integration test.

### Lỗi 14 — Gửi entity trực tiếp ra JSON API vì SELECT o rất tiện

Entity có thể chứa association lazy, vòng tham chiếu hai chiều và các field không muốn expose. Dùng DTO/projection theo hợp đồng API.

### Lỗi 15 — Giả định SQL của projection giống SQL SELECT *

JPA provider tạo SQL dựa trên mapping và expression, có thể thêm join/column để phục vụ semantics. Không suy luận chỉ từ cú pháp JPQL mà bỏ qua SQL log/plan, nhất là với aggregate, joins và fetch behavior.

---

## 20. Thực hành theo từng bước

Giả sử yêu cầu xây trang “Danh sách đơn đã thanh toán” hiển thị: ID, tên khách hàng, tổng tiền và ngày tạo.

### Bước 1: Chỉ ra loại kết quả

Đây là **read-only list** với vài thuộc tính của Order và Customer. Không cần entity managed để chỉnh sửa trong màn hình này.

### Bước 2: Chọn DTO

~~~java
package com.example.sales.dto;

import java.math.BigDecimal;
import java.time.Instant;

public record PaidOrderRow(
    Long orderId,
    String customerName,
    BigDecimal totalAmount,
    Instant createdAt
) {}
~~~

### Bước 3: Viết JPQL SELECT NEW

~~~java
TypedQuery<PaidOrderRow> query = em.createQuery(
        """
        SELECT NEW com.example.sales.dto.PaidOrderRow(
            o.id,
            c.fullName,
            o.totalAmount,
            o.createdAt
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        WHERE o.status = :paid
        ORDER BY o.createdAt DESC, o.id DESC
        """,
        PaidOrderRow.class
    );

query.setParameter("paid", OrderStatus.PAID);
query.setFirstResult(0);
query.setMaxResults(20);

List<PaidOrderRow> page = query.getResultList();
~~~

### Bước 4: Thêm query count khi cần tổng trang

~~~java
Long total = em.createQuery(
        """
        SELECT COUNT(o)
        FROM PurchaseOrder o
        WHERE o.status = :paid
        """,
        Long.class
    )
    .setParameter("paid", OrderStatus.PAID)
    .getSingleResult();
~~~

### Bước 5: Đọc kết quả theo field DTO

~~~java
for (PaidOrderRow row : page) {
    System.out.println(
        row.orderId()
        + " | " + row.customerName()
        + " | " + row.totalAmount()
        + " | " + row.createdAt()
    );
}
~~~

Không còn phải nhớ `row[0]` đến `row[3]`, không cần tải collection lines, và DTO có dạng phù hợp để chuyển sang response API.

### Bước 6: Khi cần sửa đơn, dùng query entity riêng

Một use case cập nhật trạng thái:

~~~java
@Transactional
public void cancelOrder(Long id) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);

    if (order == null) {
        throw new IllegalArgumentException(
            "Không tìm thấy đơn hàng"
        );
    }

    order.changeStatus(OrderStatus.CANCELLED);
}
~~~

Ví dụ giả định có business validation trạng thái ở tầng phù hợp; mục đích là cho thấy **projection để đọc** và **entity managed để ghi** là hai nhu cầu khác nhau. Không tải DTO rồi kỳ vọng JPA dirty checking tự lưu giá trị đã sửa trong DTO.

---

## 21. Bài tập vận dụng

### Bài tập 1 — Xác định kiểu kết quả

Cho bốn JPQL:

~~~jpql
SELECT o FROM PurchaseOrder o
SELECT o.id FROM PurchaseOrder o
SELECT o.id, o.status FROM PurchaseOrder o
SELECT COUNT(o) FROM PurchaseOrder o
~~~

Hãy xác định Java type thích hợp của từng result row và khai báo `TypedQuery<T>` tương ứng.

**Gợi ý:** `PurchaseOrder`, `Long`, `Object[]`, `Long`.

### Bài tập 2 — Object[] với ba biểu thức

Viết JPQL trả `o.id`, `o.status` và `o.totalAmount`. Viết vòng for lấy dữ liệu bằng đúng vị trí và kiểu của `Object[]`.

**Gợi ý:** thứ tự `SELECT` quyết định `row[0]`/`row[1]`/`row[2]`.

### Bài tập 3 — Constructor DTO

Tạo `OrderSummary(Long id, String customerName, BigDecimal amount)` và dùng `SELECT NEW` trả một DTO cho mỗi Order.

**Gợi ý:** tên class đầy đủ và constructor phải khớp số lượng, thứ tự, kiểu tham số.

### Bài tập 4 — Trùng giá trị khi chọn scalar

Với ba Order: hai thuộc Customer An, một thuộc Customer Bình. Truy vấn:

~~~jpql
SELECT o.customer.fullName FROM PurchaseOrder o
~~~

trả bao nhiêu hàng? Để lấy tên không trùng, cần thêm gì? Nếu hai Customer trùng tên, DISTINCT tên có phản ánh hai khách hàng riêng biệt không?

### Bài tập 5 — JOIN collection

Một Order có hai lines, Order khác không có line. So sánh kết quả của:

~~~jpql
SELECT o.id, l.productCode
FROM PurchaseOrder o JOIN o.lines l
~~~

và:

~~~jpql
SELECT o.id, l.productCode
FROM PurchaseOrder o LEFT JOIN o.lines l
~~~

**Gợi ý:** INNER JOIN bỏ Order không có line, LEFT JOIN giữ Order và trả phần line bằng null.

### Bài tập 6 — COUNT và SUM

Viết query trả cùng lúc tổng số Order và tổng `totalAmount`. Kiểu mỗi thành phần là gì? Nếu bảng trống, COUNT và SUM có cùng kết quả mặc định không?

### Bài tập 7 — GROUP BY theo khách hàng

Viết JPQL một hàng mỗi Customer: `customerId`, `customerName` và số Order. Đảm bảo khách chưa có Order vẫn xuất hiện với 0.

**Gợi ý:** bắt đầu từ `Customer c LEFT JOIN c.orders o`, `COUNT(o)`, `GROUP BY c.id, c.fullName`.

### Bài tập 8 — Chọn entity hay DTO?

Một màn hình chỉ hiển thị ID, tên khách, tổng tiền. Một service khác cần xác nhận Order đã giao và sửa trạng thái.

Hãy lựa chọn SELECT entity hoặc DTO cho từng use case, giải thích vai trò persistence context và dirty checking.

### Bài tập 9 — Phân trang

Viết query lấy 25 đơn PAID mới nhất, sắp theo `createdAt DESC` và `id DESC`. Vì sao không nên bỏ `ORDER BY`?

### Bài tập 10 — Null ở LEFT JOIN

Viết DTO chứa Order ID và productCode của một line. Khi Order không có line, `productCode` có thể mang giá trị gì? Điều gì xảy ra nếu DTO gọi `productCode.length()` mà không kiểm tra?

### Bài tập 11 — Sai kiểu COUNT

Một developer viết:

~~~java
TypedQuery<Integer> q = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Integer.class
);
~~~

Hãy xác định nguyên nhân không phù hợp và sửa thành kiểu đúng.

### Bài tập 12 — Tuple và Criteria

Dùng `CriteriaQuery<Tuple>` để chọn `id` và `totalAmount` của PurchaseOrder với alias `orderId`, `amount`. Đọc từng giá trị bằng `Tuple.get(alias, type)`.

---

## 22. Ghi nhớ

- **JPQL SELECT quyết định kiểu của từng hàng kết quả**: entity, scalar hay nhiều biểu thức.
- `SELECT o` trả **entity**; entity được quản lý bởi persistence context trong phạm vi thích hợp và có thể tham gia dirty checking.
- `SELECT o.id` hoặc `SELECT o.totalAmount` trả **giá trị thuộc tính** đúng kiểu Java của expression, không phải entity.
- `SELECT o.id, o.status` có **nhiều mục chọn**; dạng kết quả phổ biến là `Object[]` với vị trí đúng theo thứ tự SELECT.
- Có thể trộn entity và scalar trong một `Object[]`, ví dụ `SELECT o, c.fullName`; phần entity có semantics JPA riêng.
- **`SELECT NEW fully.qualified.Dto(...)`** tạo DTO projection với constructor khớp kiểu/thứ tự; DTO không tự được JPA quản lý.
- `Tuple` hỗ trợ đọc nhiều expression theo alias/vị trí; tính hỗ trợ Tuple cho JPQL string cần xét phiên bản/provider, còn `CriteriaQuery<Tuple>` là lựa chọn rõ ràng qua Criteria API.
- **`JOIN` không tự quyết định kiểu trả về**. SELECT mới quyết định; JOIN collection có thể nhân số hàng.
- **`DISTINCT` loại trùng theo kết quả được chọn**, không thay thế việc xác định identity nghiệp vụ.
- `COUNT` trả `Long`; aggregate khác có quy tắc kiểu/null riêng; nhiều aggregate trong cùng SELECT vẫn là kết quả nhiều mục.
- `GROUP BY` và `HAVING` dùng cho báo cáo theo nhóm; muốn nhóm theo Customer duy nhất nên dùng ID chứ không chỉ tên.
- `getResultList()` trả danh sách (có thể rỗng); `getSingleResult()` yêu cầu một hàng và có thể ném exception.
- Dùng `TypedQuery<T>` theo kiểu của **một result row**, không phải theo entity trong mệnh đề FROM.
- Với API read-only và phân trang, DTO projection thường thuận lợi; với use case thay đổi trạng thái, cần managed entity và transaction.

**Kết luận:** Trong JPQL, hãy bắt đầu bằng câu hỏi **“Mỗi hàng kết quả của tôi cần biểu diễn điều gì?”** Nếu cần một thực thể có identity và vòng đời, chọn entity. Nếu chỉ cần một giá trị, chọn thuộc tính/biểu thức scalar. Nếu cần nhiều giá trị, có thể dùng `Object[]` cho thao tác ngắn hoặc `Tuple`/DTO để code rõ ràng hơn. Hiểu đúng kiểu kết quả của `SELECT` giúp truy vấn chính xác, giảm dữ liệu thừa và tránh nhầm lẫn giữa read model với managed entity.
