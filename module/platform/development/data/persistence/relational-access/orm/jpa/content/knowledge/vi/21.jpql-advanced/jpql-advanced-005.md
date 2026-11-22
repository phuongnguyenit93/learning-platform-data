# Liên kết truy vấn con với dữ liệu của truy vấn ngoài

## 1. Correlated subquery giải quyết bài toán gì?

Trong JPQL (*Jakarta Persistence Query Language*), một **truy vấn con** (*subquery*) là câu truy vấn được đặt bên trong điều kiện của một truy vấn khác. Có những truy vấn con tự hoạt động độc lập; cũng có truy vấn con cần **sử dụng dữ liệu của từng dòng đang được xét ở truy vấn ngoài**. Trường hợp thứ hai được gọi là **correlated subquery**, hay **truy vấn con có tương quan**.

Ví dụ nghiệp vụ: **Lấy các khách hàng đã có ít nhất một đơn hàng thanh toán thành công**.

Một biểu thức JPQL rõ nghĩa là:

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paidStatus
)
ORDER BY c.id
```

Điểm quyết định nằm ở:

```jpql
o.customer = c
```

- `o` là biến định danh của `PurchaseOrder` **bên trong** truy vấn con.
- `c` là biến định danh của `Customer` **ở truy vấn ngoài**.
- Truy vấn con tham chiếu `c`, do đó có tương quan với dòng Customer đang được xét.
- `EXISTS` nhận giá trị true khi tồn tại **ít nhất một** Order phù hợp với chính Customer đó.

Nhìn dưới góc độ logic:

```text
Duyệt từng Customer c trong truy vấn ngoài:
    Có tồn tại PurchaseOrder o sao cho:
       o.customer = c
       và o.status = PAID
    hay không?

    Nếu CÓ: chọn Customer c.
    Nếu KHÔNG: loại Customer c.
```

Đây là một mô hình rất phổ biến trong chương **JPQL nâng cao** của JPA. Nó xuất hiện khi cần:

- Kiểm tra **tồn tại** hoặc **không tồn tại** dữ liệu liên quan.
- So sánh từng entity với **số lượng**, **giá trị lớn nhất**, **nhỏ nhất** hoặc **trung bình của nhóm mà nó thuộc về**.
- Lọc những bản ghi không có quan hệ thỏa điều kiện (*anti-join*).
- Tìm entity đạt **giá trị cực đại/cực tiểu trong từng nhóm**.
- Diễn đạt các điều kiện kiểu **“mọi phần tử liên quan đều thỏa”**, **“ít nhất một phần tử thỏa”**, hoặc **“không có phần tử nào vi phạm”**.
- Tránh nhân bản hàng của truy vấn ngoài do `JOIN` trên collection, nhất là khi có phân trang.

Bài học tập trung vào **liên kết dữ liệu giữa hai phạm vi truy vấn**: cách tham chiếu alias bên ngoài, phạm vi hiệu lực của alias, các toán tử `EXISTS`/`NOT EXISTS`/`IN`/so sánh scalar, cách dùng Criteria API `correlate` và cách lựa chọn cách diễn đạt vừa chính xác vừa phù hợp hiệu năng.

## 2. Phân biệt subquery độc lập và subquery có tương quan

### 2.1. Subquery độc lập

Giả sử cần lấy sản phẩm có giá lớn hơn giá trung bình **toàn bộ catalog**:

```jpql
SELECT p
FROM Product p
WHERE p.price > (
    SELECT AVG(p2.price)
    FROM Product p2
)
```

Truy vấn con:

```jpql
SELECT AVG(p2.price) FROM Product p2
```

không tham chiếu `p` ở bên ngoài, nên kết quả của nó **không phụ thuộc một Product cụ thể**. Đây là một truy vấn con không tương quan.

Trong JPQL, `AVG` trả về giá trị kiểu số thích hợp (về mặt kết quả aggregate là `Double` theo quy định chuẩn), kể cả khi field gốc là `BigDecimal`. Khi dùng các aggregate trong tính toán tiền tệ, phải chủ động đánh giá độ chính xác và kiểu dữ liệu.

### 2.2. Subquery có tương quan

Yêu cầu thay đổi: lấy sản phẩm có giá cao hơn **giá trung bình các sản phẩm trong chính danh mục của nó**.

```jpql
SELECT p
FROM Product p
WHERE p.price > (
    SELECT AVG(p2.price)
    FROM Product p2
    WHERE p2.category = p.category
)
```

Truy vấn con phụ thuộc `p.category` của Product đang được xét ở ngoài. Mỗi Product thuộc danh mục khác nhau có thể được so với một giá trị trung bình khác nhau.

```text
Product P1, category = Keyboards
    -> tính AVG(price) của các Product trong Keyboards

Product P2, category = Mice
    -> tính AVG(price) của các Product trong Mice

Product P3, category = Keyboards
    -> so với AVG cùng nhóm Keyboards
```

**Đây là cách hiểu logic**, không khẳng định database phải chạy subquery riêng từng dòng. Bộ tối ưu SQL có thể chuyển một correlated subquery thành phép join/aggregate, dùng index hoặc chiến lược thực thi khác.

### 2.3. Bảng phân biệt

| Khía cạnh | Subquery không tương quan | Correlated subquery |
|---|---|---|
| Có tham chiếu alias từ query ngoài? | Không | **Có** |
| Kết quả phụ thuộc hàng ngoài? | Không về mặt logic | **Có thể có** |
| Ví dụ | So giá với AVG toàn bộ Product | So giá với AVG trong cùng Category |
| Cách nối hai phạm vi | Không cần | Điều kiện như `o.customer = c` |
| Tác dụng điển hình | Một ngưỡng/tập kết quả dùng chung | Tồn tại, cực trị, đếm, tính theo từng nhóm |
| Số lần SQL thực thi | Do optimizer quyết định | Cũng do optimizer quyết định |

**Quy tắc nhận diện nhanh:** Nếu trong query con xuất hiện một alias chỉ được định nghĩa ở query ngoài, đó là dấu hiệu trực tiếp của **correlation**.

## 3. Mô hình entity dùng trong bài

Ta dùng một hệ thống bán hàng nhỏ:

```text
Customer 1 -------- n PurchaseOrder 1 -------- n OrderLine
                         |                           |
                         | status, totalAmount        |
                         | placedAt                   |
                         v                           v
                       Customer                    Product
                                                   |
                                                   n
                                                   |
                                                   1
                                                 Category
```

Quan hệ được biểu diễn ở mức Java:

- `PurchaseOrder.customer`: `@ManyToOne` tới Customer.
- `Customer.orders`: `@OneToMany(mappedBy = "customer")`.
- `OrderLine.order`: `@ManyToOne` tới PurchaseOrder.
- `PurchaseOrder.lines`: `@OneToMany(mappedBy = "order")`.
- `OrderLine.product`: `@ManyToOne` tới Product.
- `Product.category`: `@ManyToOne` tới Category.

### 3.1. Entity Customer

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(name = "region_code", nullable = false)
    private String regionCode;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {}

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
    public String getRegionCode() { return regionCode; }
}
```

`Customer.orders` cho phép dùng collection path khi viết Criteria API tương quan. Ví dụ JPQL có thể chọn cách đi qua collection hoặc trực tiếp so sánh `PurchaseOrder.customer = c`.

### 3.2. Enum trạng thái và entity đơn hàng

```java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getPlacedAt() { return placedAt; }
}
```

### 3.3. Product, Category và OrderLine

Các ánh xạ quan trọng (phần code tập trung vào các trường được dùng trong truy vấn):

```java
@Entity
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false)
    private String name;

    protected Category() {}
}
```

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {}
}
```

```java
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

    protected OrderLine() {}
}
```

Trong ba đoạn rút gọn này cần import `jakarta.persistence.*`, `java.math.BigDecimal` tương ứng. Entity có constructor không tham số cho JPA; các constructor nghiệp vụ/validation không bắt buộc để hiểu phần JPQL và được lược bớt.

### 3.4. Sơ đồ bảng SQL

```sql
-- Ví dụ lược đồ theo cú pháp PostgreSQL.
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    region_code VARCHAR(64) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(24) NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    placed_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    category_id BIGINT REFERENCES categories(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
```

Câu JPQL dùng **tên entity/thuộc tính Java** như `PurchaseOrder` và `o.customer`, không dùng tên bảng/cột SQL như `purchase_orders` hoặc `customer_id`. Những bảng này giúp hình dung cách provider dịch quan hệ sang SQL.

### 3.5. Dữ liệu mẫu dùng để suy luận

Giả sử có bốn Customer:

| Customer ID | Tên | Vùng |
|---:|---|---|
| 1 | An | HCM |
| 2 | Bình | HCM |
| 3 | Chi | HN |
| 4 | Dũng | DN |

Và các Order:

| Order ID | Customer ID | Status | Total amount |
|---:|---:|---|---:|
| 101 | 1 | PAID | 400000 |
| 102 | 1 | CANCELLED | 100000 |
| 103 | 2 | PAID | 800000 |
| 104 | 2 | PAID | 900000 |
| 105 | 4 | NEW | 300000 |

Customer **Chi** chưa có đơn nào. Đây là dữ liệu giả định cho ví dụ; các cột thời gian và dòng đơn hàng có thể được bổ sung trong thí nghiệm.

## 4. Phạm vi alias: cơ chế tạo tương quan

### 4.1. Alias của truy vấn ngoài

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
)
```

- `c` được khai báo bởi `FROM Customer c` ở query ngoài.
- `o` được khai báo bởi `FROM PurchaseOrder o` ở subquery.
- Trong subquery, tham chiếu `c` được phân giải từ **phạm vi bao ngoài**.
- Ngược lại, `o` chỉ có ý nghĩa bên trong subquery, không thể được dùng tùy ý trong `SELECT` của query ngoài.

Khi có nhiều tầng truy vấn con, alias có thể tham chiếu một phạm vi bao ngoài phù hợp. Tuy nhiên, nên đặt tên alias **khác nhau và có ý nghĩa** để tránh che khuất tên (*shadowing*).

### 4.2. Một correlation predicate phải khớp nghiệp vụ

Ví dụ:

```jpql
WHERE o.customer = c
```

là so sánh entity association với alias Customer. Có thể viết theo khóa:

```jpql
WHERE o.customer.id = c.id
```

nếu hai khóa là cách định danh tương ứng. Trong nhiều trường hợp, **so sánh association trực tiếp** giúp biểu đạt quan hệ của object model rõ hơn; provider sẽ quyết định SQL/FK cần thiết. Với `c` là entity hiện tại, hai điều kiện có thể mang ý nghĩa cùng một quan hệ nhưng SQL tạo ra và các tình huống null/identity cần được xét theo mapping.

Không chỉ viết:

```jpql
WHERE o.status = :status
```

rồi coi đó là truy vấn tương quan. Nếu query con không tham chiếu Customer, điều kiện `EXISTS` chỉ trả true/false dựa trên **toàn bộ đơn hàng**, và kết quả có thể chọn **mọi Customer** khi hệ thống có một Order phù hợp.

### 4.3. Ví dụ sai: thiếu điều kiện nối

```jpql
-- Sai với yêu cầu "mỗi Customer có Order PAID không?".
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.status = :paidStatus
)
```

Nếu database có bất kỳ Order PAID nào, query con sẽ có ít nhất một hàng đối với **mọi Customer**, bao gồm cả Chi và Dũng.

Cách sửa:

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paidStatus
)
```

**Điều kiện liên kết tới alias ngoài chính là “mấu chốt tương quan”.**

### 4.4. Đặt alias trùng tên gây khó hiểu

Tránh:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE ...
)
```

Việc tái sử dụng `o` ở subquery có thể che khuất alias ngoài, khiến người đọc khó biết trường nào thuộc bản ghi nào. Dùng `outerOrder` và `candidate`:

```jpql
SELECT outerOrder
FROM PurchaseOrder outerOrder
WHERE EXISTS (
    SELECT candidate.id
    FROM PurchaseOrder candidate
    WHERE candidate.customer = outerOrder.customer
      AND candidate.id <> outerOrder.id
)
```

Query này tìm những Order mà Customer của chúng còn ít nhất một Order **khác ID**.

## 5. `EXISTS`: có ít nhất một hàng liên quan

### 5.1. Semantics

`EXISTS (subquery)` trả **true nếu subquery có ít nhất một dòng kết quả**, không quan trọng giá trị được chọn là bao nhiêu. Do vậy các ví dụ thường dùng:

```jpql
SELECT o.id
```

hoặc:

```jpql
SELECT 1
```

trong subquery. Điều kiện thực sự nằm ở `WHERE` của subquery.

Lấy Customer đã có Order PAID:

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :status
)
ORDER BY c.id
```

Dùng với JPA:

```java
import jakarta.persistence.EntityManager;
import java.util.List;

List<Customer> customers = em.createQuery(
        "SELECT c FROM Customer c " +
        "WHERE EXISTS (" +
        "  SELECT o.id FROM PurchaseOrder o " +
        "  WHERE o.customer = c AND o.status = :status" +
        ") ORDER BY c.id",
        Customer.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
```

Với dữ liệu mẫu, kết quả là **An (ID 1)** và **Bình (ID 2)**. Chi chưa có Order; Dũng chỉ có Order NEW.

### 5.2. EXISTS khác JOIN khi có nhiều dòng con

Một cách khác:

```jpql
SELECT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :status
```

Nếu Bình có hai Order PAID, phép JOIN có thể tạo **hai dòng logic ứng với cùng Bình** trước khi xử lý kết quả. Khi chọn entity, provider có thể có các cơ chế quản lý identity, nhưng không nên giả định kết quả list và phân trang luôn tránh nhân bản theo cách mong muốn.

Thêm `DISTINCT`:

```jpql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :status
```

có thể giải quyết trùng kết quả logic, song có thể phát sinh công việc DISTINCT ở SQL. `EXISTS` diễn đạt trực tiếp câu hỏi “có ít nhất một không?”, do đó thường phù hợp hơn khi **chỉ cần xác minh điều kiện liên quan mà không cần lấy cột của Order**.

### 5.3. EXISTS không yêu cầu lấy toàn bộ Order

```jpql
SELECT c FROM Customer c
WHERE EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c
)
```

được dùng để **lọc Customer**, không trả các Order làm kết quả riêng. Vì vậy, không nên đánh đồng nó với fetch join hoặc thao tác tải `c.orders`. Sau query, truy cập `c.getOrders()` khi collection LAZY vẫn có thể phát sinh SELECT bổ sung.

**Correlated subquery phục vụ filtering; fetching là vấn đề riêng.**

### 5.4. EXISTS trong điều kiện nhiều nhánh

```jpql
SELECT c
FROM Customer c
WHERE c.regionCode = :region
  AND EXISTS (
      SELECT o.id
      FROM PurchaseOrder o
      WHERE o.customer = c
        AND o.status = :status
        AND o.totalAmount >= :minimum
  )
```

Query chọn Customer **trong một vùng nhất định** và có **ít nhất một Order** vừa PAID vừa đạt tổng tiền tối thiểu. Hai điều kiện Order được đặt **trên cùng alias `o`**, nên chúng phải cùng đúng trên một Order.

Điều này khác:

```jpql
WHERE EXISTS (
    SELECT o1.id FROM PurchaseOrder o1
    WHERE o1.customer = c AND o1.status = :status
)
AND EXISTS (
    SELECT o2.id FROM PurchaseOrder o2
    WHERE o2.customer = c AND o2.totalAmount >= :minimum
)
```

Dạng hai EXISTS cho phép một Order thỏa status, còn Order **khác** thỏa amount. Đây là khác biệt logic quan trọng khi yêu cầu nghiệp vụ nói “**cùng một** bản ghi liên quan” hay “**hai điều kiện tồn tại độc lập**”.

## 6. `NOT EXISTS`: không có hàng liên quan phù hợp

### 6.1. Tìm Customer chưa có Order PAID

```jpql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :status
)
ORDER BY c.id
```

Với `status = PAID`, kết quả là **Chi (ID 3)** và **Dũng (ID 4)**:

- Chi không có Order nào.
- Dũng có Order NEW nhưng không có Order PAID.
- An và Bình bị loại vì có ít nhất một Order PAID.

`NOT EXISTS` diễn đạt **không có phần tử liên quan thỏa điều kiện**, không yêu cầu Customer hoàn toàn chưa có Order.

### 6.2. Tìm Customer chưa có bất kỳ Order

Bỏ ràng buộc status:

```jpql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
)
```

Với dữ liệu mẫu, **chỉ Chi** phù hợp. Đừng nhầm câu hỏi “không có Order PAID” với “không có Order”.

### 6.3. Anti-join bằng LEFT JOIN

Có thể biểu diễn “không có Order nào” bằng:

```jpql
SELECT c
FROM Customer c
LEFT JOIN c.orders o
WHERE o.id IS NULL
```

Nhưng nếu cần lọc theo status cụ thể, phải chú ý vị trí điều kiện. Cách viết:

```jpql
SELECT c
FROM Customer c
LEFT JOIN c.orders o
WHERE o.status <> :paidStatus
```

**không tương đương** “không có Order PAID”. Customer có cả Order PAID và CANCELLED vẫn có một dòng CANCELLED thỏa `<>` nên có thể bị chọn nhầm.

`NOT EXISTS` gắn điều kiện ở subquery thường chính xác và dễ đọc hơn:

```jpql
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paidStatus
)
```

### 6.4. Dùng NOT EXISTS thay cho NOT IN khi có null

Giả sử subquery có thể trả một tập ID chứa `NULL`. Điều kiện `x NOT IN (subquery)` chịu ảnh hưởng của logic ba giá trị và có thể trả rất ít hàng ngoài dự đoán. `NOT EXISTS` với predicate tương quan tường minh thường tránh được vấn đề “NULL trong tập loại trừ”.

Ví dụ tìm Customer không có Order trả phí:

```jpql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c AND o.status = :paid
)
```

Nó trực tiếp xét sự hiện diện của một hàng Order phù hợp, không yêu cầu tạo tập ID rồi phủ định phép membership.

Tuy nhiên, `NOT EXISTS` cũng có thể cần **xử lý null bên trong điều kiện con** nếu nghiệp vụ coi status null là “không PAID” hay “không hợp lệ”. Đừng xem `NOT EXISTS` là cách tự động giải quyết mọi vấn đề null.

## 7. Correlated scalar subquery: đếm các hàng liên quan

### 7.1. Tìm Customer có ít nhất hai Order PAID

Thay vì chỉ hỏi “có ít nhất một”, ta cần tính **số lượng**:

```jpql
SELECT c
FROM Customer c
WHERE (
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
) >= :minimumCount
ORDER BY c.id
```

`COUNT` trả về kiểu `Long` theo JPA. Binding:

```java
List<Customer> frequentCustomers = em.createQuery(
        "SELECT c FROM Customer c " +
        "WHERE (" +
        " SELECT COUNT(o) FROM PurchaseOrder o " +
        " WHERE o.customer = c AND o.status = :paid" +
        ") >= :minimumCount " +
        "ORDER BY c.id",
        Customer.class
    )
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("minimumCount", 2L)
    .getResultList();
```

Với dữ liệu mẫu, **Bình** có hai Order PAID, còn An có một nên bị loại.

### 7.2. COUNT khi không có Order

Nếu Customer không có Order thỏa điều kiện, `COUNT(o)` trong subquery aggregate không GROUP BY trả về **0**. Do đó:

```jpql
WHERE (
    SELECT COUNT(o) FROM PurchaseOrder o
    WHERE o.customer = c
) = 0
```

có thể diễn đạt “không có Order” giống `NOT EXISTS`.

Tuy nhiên, khi **chỉ cần kiểm tra tồn tại/không tồn tại**, `EXISTS`/`NOT EXISTS` thường biểu đạt ý định sát hơn và có thể cho optimizer cơ hội dừng tìm sau khi thấy hàng đầu tiên. `COUNT` đòi hỏi semantics tổng hợp; không nên mặc định nó nhanh bằng EXISTS.

### 7.3. Điều kiện ít nhất và chính xác

Có thể dùng:

```jpql
-- Chính xác ba Order:
WHERE (
    SELECT COUNT(o) FROM PurchaseOrder o
    WHERE o.customer = c
) = 3

-- Nhiều hơn năm Order:
WHERE (
    SELECT COUNT(o) FROM PurchaseOrder o
    WHERE o.customer = c
) > 5

-- Không vượt quá hai Order:
WHERE (
    SELECT COUNT(o) FROM PurchaseOrder o
    WHERE o.customer = c
) <= 2
```

Hãy xác định **đếm tất cả Order** hay **chỉ Order thỏa trạng thái/khung thời gian**. Mọi predicate trong subquery sẽ ảnh hưởng con số được đếm.

### 7.4. COUNT với quan hệ nhiều-nhiều hoặc join nhiều tầng

Nếu subquery join thêm nhiều collection:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.customer = c
```

mỗi Order có nhiều OrderLine có thể xuất hiện nhiều lần trong kết quả join, nên `COUNT(o)` đếm **dòng join**, không phải mặc định đếm Order duy nhất.

Nếu cần số Order riêng:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE o.customer = c
```

Hoặc thiết kế một `EXISTS` lồng nhau để tránh nhân bản Order ngay từ đầu. **Đặt DISTINCT theo đúng đại lượng nghiệp vụ**, không thêm theo thói quen.

## 8. Tìm bản ghi cực đại/cực tiểu trong từng nhóm

### 8.1. Lấy đơn hàng có tổng tiền cao nhất của mỗi Customer

Một mẫu correlated subquery điển hình:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.totalAmount = (
    SELECT MAX(o2.totalAmount)
    FROM PurchaseOrder o2
    WHERE o2.customer = o.customer
)
ORDER BY o.customer.id, o.id
```

Diễn giải:

1. Với từng Order `o` bên ngoài, lấy Customer của Order đó.
2. Trong subquery, tìm `MAX(totalAmount)` của **mọi Order có cùng Customer**.
3. Chọn `o` nếu tổng tiền của nó bằng giá trị cực đại ấy.

Với dữ liệu mẫu:

- An: Order 101 tổng 400000 lớn hơn 102 tổng 100000.
- Bình: Order 104 tổng 900000 lớn hơn 103 tổng 800000.
- Dũng: Order 105 tổng 300000 là Order duy nhất.
- Chi không có Order nên không xuất hiện ở truy vấn ngoài.

Kết quả: **101, 104, 105**.

### 8.2. Tie: nhiều hàng cùng cực đại

Nếu Customer có hai Order cùng tổng tiền lớn nhất, điều kiện `= MAX(...)` sẽ trả về **cả hai**, vì cả hai đều khớp cực đại.

Đây có thể là đúng nếu nghiệp vụ yêu cầu “mọi Order đồng hạng cao nhất”. Nếu nghiệp vụ cần **duy nhất một Order mỗi Customer**, phải đặt quy tắc tie-breaker, ví dụ ID lớn nhất trong các Order có totalAmount cực đại.

Một cách diễn đạt không cần scalar MAX là `NOT EXISTS` với thứ tự vượt trội:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE NOT EXISTS (
    SELECT competitor.id
    FROM PurchaseOrder competitor
    WHERE competitor.customer = o.customer
      AND (
          competitor.totalAmount > o.totalAmount
          OR (
              competitor.totalAmount = o.totalAmount
              AND competitor.id > o.id
          )
      )
)
ORDER BY o.customer.id
```

Nó chọn Order mà **không tồn tại Order cùng Customer** có số tiền lớn hơn, hoặc bằng tiền nhưng ID lớn hơn. Với `totalAmount` không null và ID duy nhất, mỗi Customer có Order sẽ có đúng một kết quả.

Nếu totalAmount có thể null, phải xác định rõ quy tắc xếp hạng null; phép `>`/`=` với null không tạo TRUE. Trong mapping ví dụ, totalAmount đã được khai báo `nullable=false` nên trường hợp này được loại tại ràng buộc dữ liệu.

### 8.3. Cực đại có điều kiện

Nếu chỉ muốn Order PAID lớn nhất của mỗi Customer:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :paid
  AND o.totalAmount = (
      SELECT MAX(o2.totalAmount)
      FROM PurchaseOrder o2
      WHERE o2.customer = o.customer
        AND o2.status = :paid
  )
```

Phải có **cùng điều kiện trạng thái ở query ngoài và trong subquery**. Nếu chỉ lọc PAID bên trong nhưng không lọc ngoài, một Order CANCELLED tình cờ có cùng số tiền với cực đại PAID có thể bị chọn.

### 8.4. MAX/MIN và nhóm rỗng

`MAX`/`MIN` trên tập rỗng trả về null theo semantics aggregate. So sánh:

```jpql
o.totalAmount = (SELECT MAX(...) ...)
```

với null không cho TRUE. Khi truy vấn ngoài là Order thì mỗi Order ít nhất nằm trong tập cùng Customer của nó nếu không có điều kiện loại trừ; nhưng khi subquery có filter mạnh hơn, nhóm có thể rỗng. Hãy xét trường hợp này rõ ràng.

## 9. Correlated subquery với thời gian và điều kiện “gần nhất”

### 9.1. Lấy những Order có thời điểm mới nhất của Customer

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.placedAt = (
    SELECT MAX(o2.placedAt)
    FROM PurchaseOrder o2
    WHERE o2.customer = o.customer
)
```

Với cùng timestamp, nhiều Order có thể được chọn. Nếu cần một bản ghi duy nhất, áp dụng tie-breaker bằng ID hoặc một khóa thứ tự ổn định.

### 9.2. Lấy Order PAID mới nhất trong một khung thời gian

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :paid
  AND o.placedAt >= :fromInclusive
  AND o.placedAt < :toExclusive
  AND NOT EXISTS (
      SELECT newer.id
      FROM PurchaseOrder newer
      WHERE newer.customer = o.customer
        AND newer.status = :paid
        AND newer.placedAt >= :fromInclusive
        AND newer.placedAt < :toExclusive
        AND (
            newer.placedAt > o.placedAt
            OR (
                newer.placedAt = o.placedAt
                AND newer.id > o.id
            )
        )
  )
```

Điều này tìm Order PAID “mới nhất” **trong đúng cửa sổ thời gian** và dùng ID để phá hòa.

Lưu ý:

- `[fromInclusive, toExclusive)` là khoảng nửa mở, thường thích hợp với dữ liệu timestamp.
- `Instant` đại diện thời điểm tuyệt đối; khoảng ngày lịch nên được quy đổi theo timezone nghiệp vụ trước khi truyền tham số.
- Không dùng `BETWEEN` với `23:59:59` làm cận ngày cuối nếu database có độ chính xác dưới giây.
- Khi số Order nhiều, query tìm bản ghi “mới nhất theo nhóm” cần đo execution plan; các giải pháp native SQL/window functions có thể phù hợp hơn tùy hệ quản trị.

## 10. `IN` và truy vấn con liên kết dữ liệu ngoài

### 10.1. IN với subquery tương quan

`IN` kiểm tra một giá trị thuộc tập mà subquery trả về:

```jpql
SELECT c
FROM Customer c
WHERE c.id IN (
    SELECT o.customer.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
```

Ở đây `o.customer = c` tạo tương quan. Câu query đúng về mục đích “Customer có Order PAID”, nhưng trong trường hợp này `EXISTS` rõ nghĩa hơn:

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
```

Khi dùng `IN`, phải bảo đảm **kiểu của biểu thức bên trái tương thích với kiểu phần tử do subquery trả về**. Ví dụ `c.id` là `Long`, còn `SELECT o.customer.id` cũng là `Long`.

### 10.2. Subquery trả về nhiều hàng và scalar subquery khác nhau

- `IN (subquery)` chấp nhận tập nhiều giá trị.
- `EXISTS (subquery)` chỉ cần ít nhất một hàng.
- Biểu thức scalar trong so sánh như `= (SELECT MAX(...))` phải trả một giá trị xác định phù hợp.
- Nếu viết `= (SELECT o.id ... )` mà subquery trả **nhiều hàng**, database/provider có thể ném lỗi vì subquery scalar không duy nhất.

Chọn `EXISTS` hoặc `IN` khi logic chỉ cần “một trong các hàng”, thay vì ép một subquery nhiều hàng thành scalar.

### 10.3. Không nhầm alias tương quan với việc trả dữ liệu

Truy vấn con có thể tham chiếu `c`, nhưng nó **không phải một phép trả tập Order vào field Customer**. Nó chỉ được dùng để tính điều kiện. Muốn đọc các đơn hàng, dùng truy vấn Order riêng, DTO projection hoặc fetch plan thích hợp.

## 11. `ALL`, `ANY` và `SOME` với subquery

JPQL còn có các bộ lượng từ:

- `ALL (subquery)`: điều kiện so sánh phải đúng với **mọi** giá trị trả về.
- `ANY (subquery)` hoặc `SOME (subquery)`: điều kiện đúng với **ít nhất một** giá trị trả về.

Ví dụ muốn tìm Order có tổng tiền lớn hơn **mọi Order khác của cùng Customer**:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.totalAmount > ALL (
    SELECT other.totalAmount
    FROM PurchaseOrder other
    WHERE other.customer = o.customer
      AND other.id <> o.id
)
```

Đọc đúng logic: Order `o` lớn hơn **tất cả** Order còn lại của Customer. Nếu có hai Order đồng hạng cực đại, cả hai đều thất bại điều kiện `> ALL` vì không lớn hơn đối thủ bằng tiền.

**Trường hợp tập rỗng rất quan trọng:**

- Với một Order là Order **duy nhất** của Customer, subquery “Order khác” rỗng; `> ALL (empty set)` là true theo logic lượng từ.
- `> ANY (empty set)` là false vì không có phần tử nào để chứng minh.
- Khi tập kết quả chứa null, logic ba giá trị có thể khiến biểu thức không cho TRUE như mong đợi.

Các phép lượng từ giúp diễn đạt quy tắc tổng quát nhưng có thể khó đọc. Khi muốn “không có hàng vi phạm”, `NOT EXISTS` nhiều khi trực tiếp và dễ kiểm soát null hơn.

## 12. Diễn đạt điều kiện “mọi phần tử đều thỏa”

### 12.1. Bài toán: mọi Order của Customer đều PAID

Ta muốn chọn Customer sao cho **không có Order nào khác PAID**:

```jpql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status <> :paid
)
```

Logic:

```text
"Với mọi Order o của Customer c, status = PAID"

tương đương:

"Không tồn tại Order o của Customer c mà status != PAID"
```

Đây là quy tắc phủ định tồn tại (*universal quantification through NOT EXISTS*).

### 12.2. Vấn đề “đúng rỗng” (vacuous truth)

Customer **Chi** không có Order, nên **không có Order nào vi phạm điều kiện PAID**. Do đó query `NOT EXISTS` bên trên **cũng chọn Chi**.

Đó không phải bug của JPQL; đó là hệ quả logic của phát biểu “mọi phần tử của tập rỗng đều thỏa điều kiện”.

Nếu nghiệp vụ thực sự muốn:

> Chỉ chọn những Customer **có ít nhất một Order** và **tất cả Order đều PAID**,

phải thêm `EXISTS`:

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT anyOrder.id
    FROM PurchaseOrder anyOrder
    WHERE anyOrder.customer = c
)
AND NOT EXISTS (
    SELECT invalidOrder.id
    FROM PurchaseOrder invalidOrder
    WHERE invalidOrder.customer = c
      AND invalidOrder.status <> :paid
)
```

Với dữ liệu mẫu, **chỉ Bình** phù hợp: có hai Order và cả hai PAID. An có CANCELLED; Dũng có NEW; Chi không có Order.

### 12.3. Status null cần định nghĩa riêng

Mapping ví dụ có `status nullable=false`, nên cú pháp:

```jpql
invalidOrder.status <> :paid
```

đủ để nhận biết Order không PAID khi giá trị và tham số đều không null.

Nếu schema legacy cho phép status null và nghiệp vụ coi null là không hợp lệ, phải viết:

```jpql
AND (
    invalidOrder.status <> :paid
    OR invalidOrder.status IS NULL
)
```

Nếu bỏ `IS NULL`, phép `NULL <> PAID` cho UNKNOWN và Order trạng thái null có thể **không được xem là hàng vi phạm**, khiến Customer bị chọn nhầm.

### 12.4. Chứng minh không có phần tử vi phạm

Mẫu tổng quát:

```text
Mọi item liên quan đều thỏa P(item)

⟺ NOT EXISTS (
       một item liên quan mà NOT P(item)
   )
```

Trong SQL/JPQL có NULL, phép `NOT P` phải được định nghĩa đúng theo logic ba giá trị. Nếu tính chất P bao gồm trường nullable, nên bổ sung điều kiện `IS NULL` phù hợp quy tắc nghiệp vụ.

## 13. Hai tầng tương quan: “khách hàng đã mua mọi sản phẩm bắt buộc”

Một bài toán nâng cao: Cho tập ID sản phẩm bắt buộc, tìm Customer **đã mua đủ tất cả sản phẩm trong tập đó** qua các Order PAID.

Đây là bài toán *relational division*, có thể biểu diễn bằng hai tầng `NOT EXISTS`:

```jpql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT p.id
    FROM Product p
    WHERE p.id IN :requiredProductIds
      AND NOT EXISTS (
          SELECT l.id
          FROM OrderLine l
          JOIN l.order o
          WHERE o.customer = c
            AND o.status = :paid
            AND l.product = p
      )
)
```

Đọc từ trong ra ngoài:

1. Với mỗi Customer `c`, xem từng Product `p` thuộc danh sách bắt buộc.
2. Inner `NOT EXISTS` kiểm tra **Customer chưa từng có dòng mua Product p trong một Order PAID**.
3. Outer `NOT EXISTS` yêu cầu **không tồn tại Product bắt buộc nào bị thiếu**.
4. Nếu không thiếu sản phẩm bắt buộc nào, chọn Customer.

`c` thuộc phạm vi query ngoài cùng; `p` thuộc phạm vi subquery Product; cả hai được tham chiếu trong subquery OrderLine ở tầng sâu nhất.

### 13.1. Tại sao phải dùng hai tầng?

Nếu chỉ viết `EXISTS` cho OrderLine có Product trong `:requiredProductIds`, Customer chỉ cần mua **một sản phẩm** trong danh sách để thỏa. Nhưng yêu cầu là **tất cả sản phẩm**, nên phải kiểm tra **không có sản phẩm bắt buộc nào còn thiếu**.

### 13.2. Danh sách bắt buộc rỗng

`p.id IN :requiredProductIds` với collection rỗng không có hành vi portable đáng tin cậy giữa các provider/database. Đồng thời, về mặt logic “đã mua mọi sản phẩm trong tập rỗng” là đúng với mọi Customer.

Service phải quyết định rõ:

- Nếu tập bắt buộc rỗng và yêu cầu mang nghĩa toán học: có thể chọn mọi Customer (kèm bộ lọc khác nếu có).
- Nếu API không chấp nhận tập rỗng: trả lỗi validation.
- Nếu nghiệp vụ muốn chỉ Customer từng có Order: thêm điều kiện EXISTS độc lập.

**Không truyền một collection rỗng vào `IN` rồi mặc định provider sẽ áp dụng quy tắc mong muốn.**

### 13.3. Chú ý tính nhất quán kiểu dữ liệu

`requiredProductIds` phải có phần tử kiểu tương thích với `Product.id`, ở ví dụ là `Collection<Long>`. `:paid` là `OrderStatus.PAID`, không phải tùy tiện là String `"PAID"` chỉ vì database lưu enum dạng STRING.

## 14. Correlation với nhiều điều kiện từ query ngoài

Subquery có thể tham chiếu **nhiều thuộc tính** của alias bên ngoài, không chỉ ID:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT peer.id
    FROM PurchaseOrder peer
    WHERE peer.customer = o.customer
      AND peer.id <> o.id
      AND peer.placedAt > o.placedAt
      AND peer.totalAmount > o.totalAmount
)
```

Query tìm Order `o` mà có một Order khác của cùng Customer **được đặt muộn hơn và có tổng tiền lớn hơn**.

Không thể thay toàn bộ điều kiện này bằng “Order có một đơn nào đó của Customer” nếu ý nghĩa nghiệp vụ đòi đồng thời so cả thời gian lẫn số tiền của **cùng một đối thủ `peer`**.

Ví dụ tương quan theo một giá trị chuỗi từ query ngoài:

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.placedAt >= :start
      AND o.placedAt < :end
)
AND c.regionCode IN :regions
```

`c.regionCode` là bộ lọc riêng ở query ngoài, còn điều kiện thời gian nằm ở subquery. Chọn nơi đặt predicate theo đối tượng mà nó mô tả, và đảm bảo nhiều điều kiện trên một quan hệ có cùng alias khi yêu cầu “cùng một hàng”.

## 15. JPQL cho phép đặt subquery ở đâu?

### 15.1. Vị trí portable: WHERE và HAVING

Trong JPQL chuẩn, **subquery được hỗ trợ trong các mệnh đề `WHERE` và `HAVING`**.

Ví dụ `WHERE`:

```jpql
SELECT c FROM Customer c
WHERE EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c
)
```

Ví dụ `HAVING`, so sánh số Order của Customer ở từng vùng với một ngưỡng thông qua subquery:

```jpql
SELECT c.regionCode, COUNT(c)
FROM Customer c
GROUP BY c.regionCode
HAVING COUNT(c) > (
    SELECT COUNT(otherCustomer)
    FROM Customer otherCustomer
    WHERE otherCustomer.regionCode = :comparisonRegion
)
```

Ví dụ thứ hai là một subquery trong HAVING nhưng không tương quan với nhóm bên ngoài; có thể thêm correlation theo thuộc tính nhóm khi biểu thức phù hợp. Quan trọng hơn là **vị trí** của subquery được hỗ trợ.

### 15.2. Không mặc định subquery trong FROM là JPQL chuẩn

Nhiều người quen SQL viết:

```sql
SELECT t.customer_id
FROM (
    SELECT customer_id, COUNT(*) AS order_count
    FROM purchase_orders
    GROUP BY customer_id
) t
WHERE t.order_count > 3;
```

Đây là derived table trong `FROM` của SQL, **không phải cú pháp JPQL portable**. Trong JPQL, có thể dùng correlated scalar subquery:

```jpql
SELECT c
FROM Customer c
WHERE (
    SELECT COUNT(o) FROM PurchaseOrder o
    WHERE o.customer = c
) > 3
```

Nếu cần `FROM (subquery)`, lateral joins, CTE hoặc window functions, có thể cần native SQL hay tiện ích đặc thù provider. Không được khẳng định extension của một ORM là khả năng chuẩn của mọi JPA implementation.

### 15.3. Subquery trong SELECT

Một số provider hỗ trợ subquery trong `SELECT` như phần mở rộng ngôn ngữ, nhưng không nên coi đó là JPQL portable. Nếu muốn trả về Customer cùng tổng số Order dưới dạng DTO, có thể dùng một truy vấn `LEFT JOIN ... GROUP BY` phù hợp:

```jpql
SELECT c.id, c.fullName, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id, c.fullName
```

Cần cân nhắc phân trang, constructor projection và quy tắc GROUP BY theo kiểu dữ liệu/provider. Nếu cần một projection quá phức tạp, native SQL hoặc nhiều truy vấn chuyên dụng có thể rõ ràng hơn.

## 16. Cách dịch logic correlated subquery sang SQL

### 16.1. JPQL dùng association

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
```

Một SQL tương ứng về logic:

```sql
SELECT c.*
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM purchase_orders o
    WHERE o.customer_id = c.id
      AND o.status = ?
);
```

JPQL liên kết qua **`o.customer = c`**; SQL dùng foreign key `o.customer_id = c.id`. Provider chọn câu SQL thực tế theo mapping và dialect, có thể khác về alias, parameter, join hoặc câu SELECT.

### 16.2. Correlation là logic, không có nghĩa database “chạy N truy vấn”

Nhìn vào:

```text
for each Customer c:
    run subquery for c
```

là một cách hiểu **ngữ nghĩa**. Database có thể:

- Dùng semi-join/anti-join để kiểm tra EXISTS/NOT EXISTS.
- Dùng index `purchase_orders(customer_id, status)`.
- Khử tương quan (*decorrelation*) để biến biểu thức thành join/aggregate.
- Dùng nested-loop, hash join hoặc chiến lược khác.
- Thực thi subquery lặp theo hàng ngoài nếu optimizer thấy phù hợp.

**Một correlated subquery trong một câu JPQL không tự động bằng hiện tượng N+1 truy vấn JDBC.** N+1 thường được dùng cho việc ORM tải từng quan hệ LAZY bằng nhiều SQL riêng sau truy vấn gốc. Nhưng correlated subquery có thể **tốn CPU/IO** nếu thiếu index hoặc database không tối ưu được; vẫn phải đo thực tế.

### 16.3. EXISTS và JOIN: ưu/nhược

| Mục tiêu | `EXISTS` | `JOIN` |
|---|---|---|
| Chỉ hỏi có hàng liên quan không | Rất tự nhiên | Có thể cần DISTINCT nếu 1-n |
| Cần cột/thuộc tính của entity liên quan trong kết quả | Không trực tiếp trả chúng | Phù hợp hơn |
| Muốn tránh nhân bản root do nhiều child | Có lợi thế ngữ nghĩa | Phải xử lý multiplicity |
| Lọc theo điều kiện nhiều thuộc tính cùng child | Đặt trong một subquery | Đặt trên cùng alias join |
| Đọc/fetch toàn bộ collection | Không phải chức năng của EXISTS | Có thể dùng fetch join khi phù hợp |
| Tốc độ | Phụ thuộc optimizer/data/index | Cũng phụ thuộc optimizer/data/index |

Không có quy tắc tuyệt đối “EXISTS luôn nhanh hơn JOIN” hoặc ngược lại. Trên một hệ quản trị, optimizer có thể chuyển cả hai thành kế hoạch gần giống nhau.

## 17. Index và hiệu năng

### 17.1. Index cho điều kiện nối và filter

Với:

```jpql
WHERE EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
```

các cột SQL liên quan là `purchase_orders.customer_id` và `purchase_orders.status`. Một index thường đáng cân nhắc:

```sql
CREATE INDEX ix_purchase_orders_customer_status
    ON purchase_orders (customer_id, status);
```

Index này hỗ trợ tìm Order của một Customer theo status. Nếu workload chủ yếu lọc status trước, độ chọn lọc và kế hoạch thực tế có thể dẫn đến index khác. **Không tự động tạo index cho mọi tổ hợp cột**; hãy đo.

### 17.2. Index cho cực trị và thời gian

Với “Order mới nhất của mỗi Customer”:

```sql
CREATE INDEX ix_orders_customer_placed_at
    ON purchase_orders (customer_id, placed_at);
```

Nếu query có tie-breaker bằng ID, có thể cân nhắc index bao gồm ID theo khả năng database. Với “Order lớn nhất theo tổng tiền”, index `(customer_id, total_amount)` có thể hữu ích.

Trật tự cột của composite index ảnh hưởng đến cách lọc và sắp xếp. Hãy kiểm tra `EXPLAIN`/execution plan trên hệ quản trị đang dùng, không dựa vào quy tắc máy móc.

### 17.3. Khi COUNT hoặc MAX tương quan rất đắt

Nếu query ngoài có hàng triệu Customer, mỗi Customer có nhiều Order, một câu `COUNT` tương quan có thể tạo kế hoạch tốn kém nếu thiếu index/optimizer kém. Có thể so sánh với:

```jpql
SELECT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :paid
GROUP BY c
HAVING COUNT(o) >= :minimumCount
```

Đây là một cách diễn đạt khác, nhưng `GROUP BY c` ở một số provider/database có thể được triển khai khác nhau; để portable/chủ động, có thể group theo ID và các field cần thiết hoặc dùng projection chuyên biệt.

Cần lưu ý `JOIN` nội bộ loại Customer không có Order; điều này phù hợp với điều kiện `COUNT >= 1` nhưng không nhất thiết tương đương khi lọc `COUNT = 0`.

### 17.4. SQL quan sát và benchmark

Khi tối ưu, nên:

1. Bật SQL logging trong môi trường phát triển/thử nghiệm phù hợp.
2. Quan sát SQL mà ORM thực sự phát ra và các tham số.
3. Xem execution plan trong database.
4. Đo với phân bố dữ liệu thực tế: số Customer, số Order/Customer, status, độ chọn lọc.
5. Đo cả truy vấn root lẫn truy cập association LAZY sau đó.
6. So sánh `EXISTS`/`JOIN`/`GROUP BY`/native SQL khi có nhu cầu hiệu năng cụ thể.
7. Kiểm tra ảnh hưởng của phân trang và thứ tự ổn định.

Tối ưu hóa nên dựa trên **khả năng truy xuất dữ liệu thực**, không chỉ số lượng dòng JPQL.

## 18. Criteria API: tạo correlated subquery bằng Java

JPQL dạng chuỗi thuận tiện cho query tĩnh. Khi bộ lọc được tạo động, JPA Criteria API cho phép diễn đạt cấu trúc truy vấn và dùng **`Subquery.correlate(...)`** để chỉ rõ tương quan giữa query con và nguồn bên ngoài.

### 18.1. Correlation tường minh từ Root

Entity `Customer` có:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
```

Ta muốn lấy Customer có ít nhất một Order PAID:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.Root;
import jakarta.persistence.criteria.Subquery;
import java.util.List;

CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

// Correlated subquery: chọn một hằng số khi có Order phù hợp.
Subquery<Integer> subquery = query.subquery(Integer.class);

// Tạo một root tương quan với Customer ở query ngoài.
Root<Customer> correlatedCustomer =
    subquery.correlate(customer);

Join<Customer, PurchaseOrder> order =
    correlatedCustomer.join("orders");

subquery.select(cb.literal(1))
    .where(cb.equal(
        order.get("status"),
        OrderStatus.PAID
    ));

query.select(customer)
    .where(cb.exists(subquery))
    .orderBy(cb.asc(customer.get("id")));

List<Customer> result =
    em.createQuery(query).getResultList();
```

Ý nghĩa:

- `query.from(Customer.class)` tạo root của query ngoài.
- `query.subquery(Integer.class)` tạo đối tượng subquery có phần chọn là `Integer`.
- `subquery.correlate(customer)` tạo nguồn tương quan từ root Customer của query ngoài.
- `correlatedCustomer.join("orders")` duyệt các Order của đúng Customer đó.
- `cb.exists(subquery)` kiểm tra subquery có hàng phù hợp.
- `OrderStatus.PAID` được so sánh với thuộc tính enum Java, provider xử lý mapping enum.

Cách này biểu đạt quan hệ theo object model và tận dụng quan hệ `Customer.orders`. Nó không yêu cầu ứng dụng chạy nhiều lệnh tìm Order bằng Java.

### 18.2. Một cách khác: tham chiếu Outer Root trong predicate

Có thể xây subquery với một root Order mới rồi so sánh với root Customer ngoài:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

Subquery<Integer> subquery = query.subquery(Integer.class);
Root<PurchaseOrder> order =
    subquery.from(PurchaseOrder.class);

subquery.select(cb.literal(1))
    .where(
        cb.equal(order.get("customer"), customer),
        cb.equal(order.get("status"), OrderStatus.PAID)
    );

query.select(customer)
    .where(cb.exists(subquery));

List<Customer> result =
    em.createQuery(query).getResultList();
```

Đây là hình thức tương ứng trực tiếp với JPQL:

```jpql
WHERE EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c AND o.status = :paid
)
```

Hai cách đều tạo **correlated subquery**:

1. `subquery.correlate(customer)` tạo root tương quan tường minh rồi join collection.
2. `subquery.from(PurchaseOrder.class)` tạo root mới và dùng predicate nối `order.customer` với root bên ngoài.

Nên chọn cách dễ đọc, phù hợp metadata association, và kiểm tra SQL sinh ra khi tối ưu.

### 18.3. Criteria NOT EXISTS

Lấy Customer chưa có Order PAID:

```java
query.select(customer)
    .where(cb.not(cb.exists(subquery)));
```

Đây là đối ngẫu của `EXISTS`, không phải phép xóa dữ liệu hay lệnh kiểm tra entity có được quản lý trong persistence context không.

### 18.4. Criteria correlated COUNT

Lấy Customer có ít nhất hai Order PAID:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Customer> cq =
    cb.createQuery(Customer.class);

Root<Customer> customer = cq.from(Customer.class);

Subquery<Long> paidCount = cq.subquery(Long.class);
Root<PurchaseOrder> order =
    paidCount.from(PurchaseOrder.class);

paidCount.select(cb.count(order))
    .where(
        cb.equal(order.get("customer"), customer),
        cb.equal(order.get("status"), OrderStatus.PAID)
    );

cq.select(customer)
    .where(cb.ge(paidCount, 2L));

List<Customer> customers =
    em.createQuery(cq).getResultList();
```

`cb.count(order)` trả `Expression<Long>`, nên `Subquery<Long>` phù hợp. `cb.ge(paidCount, 2L)` diễn đạt điều kiện số lượng tối thiểu.

### 18.5. Criteria với tham số thay vì hằng số

Trong query có thể tái sử dụng, tạo parameter expression:

```java
ParameterExpression<OrderStatus> paid =
    cb.parameter(OrderStatus.class, "paidStatus");

subquery.where(
    cb.equal(order.get("customer"), customer),
    cb.equal(order.get("status"), paid)
);

TypedQuery<Customer> typed =
    em.createQuery(query);

typed.setParameter("paidStatus", OrderStatus.PAID);
List<Customer> result = typed.getResultList();
```

Đoạn này là biến thể của **cách tạo root Order và predicate correlation** ở mục 18.2; cần import `jakarta.persistence.TypedQuery` và `jakarta.persistence.criteria.ParameterExpression`. Không chèn nguyên chuỗi người dùng vào query để tạo giá trị điều kiện; bind tham số có kiểu sẽ rõ ràng và an toàn hơn.

### 18.6. Correlate một Join đã có

Criteria API còn cung cấp các overload `Subquery.correlate(...)` cho `Join`/`CollectionJoin`/`SetJoin`/`ListJoin`/`MapJoin` trong tình huống cần lấy **nguồn tương quan từ join của query ngoài**. Chỉ sử dụng khi cấu trúc query thực sự cần:

- Nếu điều kiện con chỉ cần Customer, tương quan root thường đơn giản.
- Nếu query ngoài đã có một join tới một phần tử cụ thể, việc correlate join có thể giúp giữ mối liên hệ với đúng join đó.
- Không thêm join dư vào query ngoài: nó có thể đổi multiplicity và phân trang.

Đừng nhầm `correlate` với `@OneToMany` hoặc `CascadeType`; `correlate` là thao tác **xây query**, không tác động vòng đời entity.

## 19. Correlated subquery và phân trang

### 19.1. EXISTS giúp giữ một hàng ứng với một root

Query:

```jpql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
ORDER BY c.id
```

không thêm một Order vào phần `FROM` của query ngoài, nên mỗi Customer root không bị nhân bản trực tiếp do join nhiều Order. Đây là một lợi thế khi phân trang danh sách Customer.

```java
List<Customer> page = em.createQuery(
        "SELECT c FROM Customer c " +
        "WHERE EXISTS (" +
        " SELECT o.id FROM PurchaseOrder o " +
        " WHERE o.customer = c AND o.status = :paid" +
        ") ORDER BY c.id",
        Customer.class
    )
    .setParameter("paid", OrderStatus.PAID)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

`ORDER BY c.id` giúp thứ tự ổn định khi không có cập nhật đồng thời làm thay đổi tập kết quả. Với bộ dữ liệu thay đổi nhanh, keyset pagination hoặc snapshot phù hợp có thể cần thiết.

### 19.2. Count query để phân trang

Nếu UI cần tổng số Customer thỏa điều kiện:

```jpql
SELECT COUNT(c)
FROM Customer c
WHERE EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
```

Kết quả count được tính trên **Customer root**, không phải số Order PAID. Đó là điểm cần phân biệt với `COUNT(o)` trong subquery.

### 19.3. EXISTS không tự động fetch collection

Khi trang Customer được lấy bằng EXISTS, `c.orders` vẫn có thể LAZY. Nếu sau đó code lặp 20 Customer rồi gọi `getOrders()`, có thể xuất hiện N+1 SELECT do fetch.

Không chữa N+1 bằng cách thêm collection fetch join vào mọi query có phân trang. Có thể dùng:

1. Query root Customer theo filter và phân trang.
2. Query các Order cần hiển thị theo tập customer IDs của trang, hoặc dùng DTO projection.
3. Ghép kết quả trong service theo quy tắc rõ ràng.

Lựa chọn phụ thuộc màn hình và provider; **lọc, phân trang và fetch** là ba trách nhiệm khác nhau.

## 20. Đồng thời, snapshot và ý nghĩa kết quả

Correlated subquery được thực thi trong **góc nhìn dữ liệu của transaction/query hiện tại**.

Ví dụ:

```jpql
SELECT c FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id FROM PurchaseOrder o
    WHERE o.customer = c AND o.status = :paid
)
```

Một transaction khác có thể tạo một Order PAID ngay sau khi query này đọc dữ liệu. Do đó, kết quả “Customer hiện chưa có Order PAID” **không phải một khóa nghiệp vụ vĩnh viễn**.

Nếu dùng điều kiện này để quyết định một thao tác ghi nhạy cảm, có thể cần transaction isolation, optimistic/pessimistic locking, unique constraint hoặc quy tắc đồng thời khác để bảo vệ bất biến dữ liệu.

Truy vấn đọc tương quan **không thay thế constraint DB**. Kể cả query kiểm tra không tồn tại thành công, hai transaction vẫn có thể đồng thời thấy “chưa có” rồi cùng cố tạo bản ghi. Ràng buộc unique/lock đúng cách mới bảo vệ kết quả dưới concurrency.

## 21. Các lỗi tư duy và cú pháp thường gặp

| Lỗi | Biểu hiện/hậu quả | Cách hiểu hoặc sửa |
|---|---|---|
| Quên điều kiện nối tới alias ngoài | EXISTS đúng với mọi Customer nếu toàn DB có Order phù hợp | Thêm `o.customer = c` |
| Tái sử dụng tên alias ở nhiều phạm vi | Dễ che khuất alias ngoài hoặc đọc sai scope | Đặt `c`, `outerOrder`, `candidate` khác nhau |
| Dùng `JOIN` để hỏi tồn tại, quên multiplicity | Khách có nhiều Order xuất hiện nhiều dòng join | Dùng EXISTS khi chỉ cần boolean; hoặc DISTINCT đúng mục tiêu |
| Đặt hai điều kiện ở hai EXISTS khác nhau dù cần cùng Order | Một Order đạt status, Order khác đạt amount vẫn được chọn | Gộp predicate vào một subquery/alias |
| Dùng `NOT IN` với tập có NULL | Kết quả loại trừ có thể rỗng bất ngờ | Xử lý NULL hoặc dùng NOT EXISTS tương quan |
| Dùng `NOT EXISTS` để nói “mọi Order PAID” nhưng quên Customer không có Order | Chọn cả Customer không có Order | Thêm một EXISTS nếu yêu cầu ít nhất một Order |
| Status nullable nhưng dùng `<> :paid` như thể NULL là không hợp lệ | NULL không tạo TRUE trong comparison | Thêm `IS NULL` nếu nghiệp vụ coi là vi phạm |
| Dùng `= (SELECT o.id ...)` khi con có nhiều hàng | Lỗi scalar subquery trả nhiều giá trị | Dùng IN/EXISTS hoặc aggregate |
| Dùng `COUNT` để hỏi “có ít nhất một” | Có thể làm nhiều việc hơn cần thiết | Dùng EXISTS khi phù hợp |
| Đếm `COUNT(o)` sau join nhiều Line | Đếm dòng join, không phải Order duy nhất | `COUNT(DISTINCT o.id)` hoặc cấu trúc khác |
| Dùng MAX rồi giả định chỉ có một kết quả | Hai Order cùng cực đại có thể cùng được chọn | Thêm tie-breaker nếu cần |
| Đặt filter PAID chỉ ở MAX subquery | Query ngoài có thể lấy CANCELLED trùng giá | Lọc điều kiện nhất quán ở cả hai phạm vi |
| Coi correlated subquery luôn là N+1 JDBC | Đánh giá hiệu năng sai | Kiểm tra SQL/plan; có thể decorrelate |
| Coi EXISTS luôn nhanh hơn JOIN | Lựa chọn không dựa dữ liệu | Benchmark với index/optimizer thực |
| Dùng tên bảng/cột SQL trong JPQL | Provider báo lỗi truy vấn hoặc mapping | Dùng entity và Java properties |
| Dùng subquery trong FROM/SELECT và cho rằng portable | Không hợp JPQL chuẩn ở các vị trí này | Dùng WHERE/HAVING hoặc native SQL/extension có chủ đích |
| Nhầm query để lọc với fetch entity liên quan | Gặp lazy-loading/N+1 sau query | Thiết kế fetch plan/DTO riêng |
| Không xử lý danh sách IN rỗng | Khác nhau giữa DB/provider; lỗi IN () | Chọn semantics API trước khi bind |
| Tạo nhiều join ngoài không cần | Nhân bản root, phân trang sai | Đưa điều kiện existence vào subquery |
| Dùng subquery có tương quan làm ràng buộc duy nhất khi ghi đồng thời | Race condition | Constraint, transaction/lock phù hợp |

## 22. Một quy trình suy luận khi viết correlated subquery

Trước khi viết JPQL, hãy trả lời các câu hỏi:

1. **Root cần trả về là entity nào?** Customer, Order hay Product? Đó là `FROM` ở truy vấn ngoài.
2. **Dữ liệu liên quan là gì?** Order của Customer, Line của Order hay Product cùng Category?
3. **Quan hệ giữa root và hàng con là gì?** Ví dụ `o.customer = c`; đây là điều kiện correlation.
4. **Cần kiểm tra tồn tại hay tính một giá trị?** Dùng `EXISTS/NOT EXISTS` cho existence; `COUNT/MAX/MIN/AVG` cho aggregate.
5. **Nhiều điều kiện phải đúng trên cùng hàng con không?** Nếu có, đặt chúng trên cùng alias subquery.
6. **Tập quan hệ rỗng được xử lý thế nào?** Đặc biệt với `NOT EXISTS`, `ALL`, `COUNT`.
7. **Có nullable field hoặc tập IN chứa null không?** Định nghĩa phép so sánh và `IS NULL` theo nghiệp vụ.
8. **Có thể có tie khi tìm MAX/MIN không?** Nếu cần duy nhất một row, thêm tie-breaker ổn định.
9. **Truy vấn có join nhiều hàng khiến root bị nhân bản không?** Cân nhắc EXISTS/COUNT DISTINCT.
10. **Có cần dữ liệu child để hiển thị?** Nếu chỉ lọc, EXISTS có thể đủ; nếu cần hiển thị, thiết kế projection/fetch riêng.
11. **Có ràng buộc thời gian, trạng thái, vùng không?** Đặt predicate ở đúng phạm vi và bind tham số có kiểu.
12. **Hiệu năng đã được đo chưa?** Kiểm tra index cho khóa liên kết và execution plan, không suy đoán chỉ từ cú pháp.

Câu hỏi quan trọng nhất: **“Phần dữ liệu nào của dòng ngoài khiến subquery phải thay đổi theo dòng đó?”** Nếu không xác định được, có thể query chưa thực sự tương quan với mục tiêu.

## 23. Bài thực hành

### Bài 1 — Phân biệt tương quan và không tương quan

Viết hai truy vấn:

1. Chọn Order có `totalAmount` lớn hơn AVG của **tất cả** Order.
2. Chọn Order có `totalAmount` lớn hơn AVG của các Order có **cùng Customer**.

Chỉ ra alias được định nghĩa ở mỗi phạm vi và biểu thức nào tạo tương quan trong query thứ hai.

### Bài 2 — Customer có Order PAID

Dùng dữ liệu mẫu với An, Bình, Chi, Dũng. Viết `EXISTS` để lấy Customer có ít nhất một Order PAID; sau đó bỏ `o.customer = c` và dự đoán kết quả sai.

Giải thích vì sao query con không tương quan tạo ra một điều kiện chung cho mọi Customer.

### Bài 3 — NOT EXISTS và logic phủ định

Viết hai query:

1. Customer chưa có Order PAID.
2. Customer chưa có **bất kỳ** Order.

Dự đoán khác biệt kết quả giữa Chi và Dũng; giải thích tại sao điều kiện `o.status = :paid` thay đổi tập phủ định.

### Bài 4 — Hai EXISTS độc lập

Yêu cầu A: Customer có **một Order** vừa PAID vừa có `totalAmount >= 500000`.

Yêu cầu B: Customer có **ít nhất một Order PAID** và **ít nhất một Order totalAmount >= 500000`**, có thể là hai Order khác nhau.

Viết mỗi yêu cầu bằng số `EXISTS` phù hợp. Tạo dữ liệu sao cho A và B cho kết quả khác nhau.

### Bài 5 — COUNT theo Customer

Viết correlated scalar subquery để lấy Customer có ít nhất hai Order PAID. Bind `OrderStatus.PAID` và `Long minimumCount`.

Thử đổi điều kiện thành `COUNT = 0` và so sánh với `NOT EXISTS`. Nếu thêm JOIN tới `OrderLine`, giải thích khi nào cần `COUNT DISTINCT`.

### Bài 6 — Lấy Order lớn nhất từng Customer

Viết query dùng `MAX(o2.totalAmount)` tương quan với `o.customer`. Thêm một Customer có hai Order cùng cực đại và quan sát cả hai có thể được chọn.

Sau đó dùng `NOT EXISTS` với điều kiện `competitor.totalAmount > o.totalAmount OR (...)` và tie-breaker ID để chọn một Order duy nhất.

### Bài 7 — Mọi Order đều PAID

Viết `NOT EXISTS` kiểm tra không có Order với status khác PAID. Quan sát Customer không có Order vẫn được chọn.

Thêm `EXISTS` để yêu cầu Customer có ít nhất một Order; bổ sung `IS NULL` nếu schema status cho phép null và null phải bị coi là trạng thái vi phạm.

### Bài 8 — Mua đủ mọi Product trong danh sách

Cho danh sách `requiredProductIds` gồm ba Product. Viết hai tầng `NOT EXISTS` để chỉ chọn Customer đã có OrderLine mua đủ ba Product trong Order PAID.

Thử biến thể chỉ có một Product, danh sách trùng ID, danh sách rỗng và Product không có trong DB; xác định semantics mong muốn của API và tác động lên query.

### Bài 9 — Criteria API correlate

Viết lại query Customer có Order PAID bằng:

1. `Subquery.correlate(customerRoot)` rồi `join("orders")`.
2. `Subquery.from(PurchaseOrder.class)` rồi `cb.equal(order.get("customer"), customerRoot)`.

So sánh JPQL/SQL sinh ra, tính đúng đắn và sự khác nhau về cách xây query trong Criteria API.

### Bài 10 — JPQL vs JOIN/GROUP BY

Viết hai truy vấn cho Customer có ít nhất hai Order PAID:

- Correlated `COUNT` trong `WHERE`.
- `JOIN c.orders o GROUP BY ... HAVING COUNT(o) >= 2`.

Chạy trên dữ liệu thực tế, so sánh số dòng, tính đúng đắn, SQL plan và tác động của index `(customer_id, status)`. Không tự kết luận bản nào nhanh hơn trước khi đo.

### Bài 11 — Phân trang và N+1

Viết query có `EXISTS` để lấy trang 20 Customer có Order PAID, sắp xếp theo `c.id`. Sau đó thử truy cập `c.orders` với collection LAZY cho từng Customer.

Quan sát SQL và đề xuất thiết kế lấy Order cho các Customer của trang bằng truy vấn thứ hai hoặc DTO projection. Giải thích vì sao correlated subquery không đồng nghĩa đã fetch relation.

### Bài 12 — Concurrency

Hai transaction cùng kiểm tra “Customer chưa có Order PAID” rồi cùng tạo Order PAID. Giải thích vì sao `NOT EXISTS` ở thời điểm đọc không ngăn được race condition.

Đề xuất cách ràng buộc nghiệp vụ tại database/transaction, tùy yêu cầu có cho phép nhiều Order PAID hay không.

## 24. Ghi nhớ cốt lõi

**Truy vấn con có tương quan trong JPQL là subquery tham chiếu dữ liệu của query ngoài**, ví dụ `o.customer = c`. Nhờ đó, mỗi Customer, Order hoặc Product có thể được đánh giá theo đúng các hàng liên quan tới nó, thay vì theo một tập dữ liệu chung không phụ thuộc root.

Khi cần hỏi **có ít nhất một** hoặc **không có** hàng liên quan, ưu tiên suy nghĩ bằng `EXISTS`/`NOT EXISTS`. Khi cần so sánh với **số lượng** hay **cực trị của nhóm**, sử dụng correlated scalar subquery với `COUNT`, `MAX`, `MIN` hoặc các aggregate phù hợp. Với điều kiện **“mọi phần tử đều thỏa”**, mẫu `NOT EXISTS` cho “không có phần tử vi phạm” rất hữu ích, nhưng phải nhớ trường hợp tập rỗng và quy tắc null.

JPQL chuẩn đặt subquery ở **`WHERE` và `HAVING`**; Criteria API cho phép tạo tương quan tường minh qua `Subquery.correlate(...)` hoặc predicate nối root bên ngoài. Luôn phân biệt correlation với fetch, EXISTS với JOIN có thể nhân bản root, tie ở MAX/MIN, và logic đúng với hiệu năng thực tế. **Một câu query chính xác bắt đầu từ việc xác định root, quan hệ tới dữ liệu con và điều kiện nối đúng phạm vi alias.**
