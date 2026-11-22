# JPQL truy vấn theo entity và thuộc tính thay vì tên bảng và cột

Trong các ứng dụng Java dùng JPA, dữ liệu được lưu ở bảng và cột của cơ sở dữ liệu quan hệ, nhưng code thường thao tác với **entity class**, **thuộc tính Java** và **association**. JPQL (*Jakarta Persistence Query Language*, trước đây thường gọi *Java Persistence Query Language*) là ngôn ngữ truy vấn hướng đối tượng của JPA: nó cho phép mô tả yêu cầu đọc và thay đổi dữ liệu dựa trên **mô hình entity**, không phải viết trực tiếp SQL dựa trên tên bảng, tên cột hay khóa ngoại.

Ví dụ, nếu Java có entity `SalesOrder` với thuộc tính `orderNumber`, trong khi database có bảng `sales_order` và cột `order_no`, một câu JPQL đúng là:

```java
String jpql = """
    select o
    from SalesOrder o
    where o.orderNumber = :orderNumber
    """;
```

Không phải:

```sql
-- Đây là SQL, không phải JPQL:
SELECT *
FROM sales_order
WHERE order_no = ?;
```

**Nguyên tắc cốt lõi:** Khi viết JPQL, hãy nghĩ “tôi đang truy vấn những **entity nào**, theo **thuộc tính nào**, đi qua **quan hệ nào**?” thay vì “tôi cần join bảng nào bằng cột FK nào?”.

Bài học thuộc chương **JPQL cơ bản** của module *Data Persistence Relational Access ORM JPA*. Nội dung đi từ cách JPA ánh xạ entity sang bảng, cú pháp SELECT/FROM/WHERE, biến định danh, đường dẫn thuộc tính, JOIN theo association, parameter binding, projection, aggregate, sorting, pagination cho tới các lỗi thực tế khi vô tình viết SQL dưới danh nghĩa JPQL.

## 1. So sánh nhanh JPQL và SQL

| Đặc điểm | JPQL | SQL |
|---|---|---|
| Đối tượng được truy vấn | Entity, persistent attribute, association của mô hình JPA | Table, view, column, foreign key của database |
| Tên trong `FROM` | Entity name, ví dụ `SalesOrder` | Tên bảng, ví dụ `sales_order` |
| Thuộc tính trong `WHERE` | `o.orderNumber` | `order_no` |
| Đi qua quan hệ | `o.customer.customerName` hoặc `join o.customer c` | `JOIN customer c ON o.customer_id = c.id` |
| Kết quả phổ biến | Entity managed, scalar, tuple, DTO qua constructor expression | Hàng/cột quan hệ hoặc result set |
| Chuyển thành SQL | JPA provider dịch theo mapping/dialect | SQL được gửi tới DB |
| Tính độc lập DB | Tốt hơn trong phạm vi ngữ nghĩa JPQL chuẩn | Tùy cú pháp SQL dialect |
| Dùng API | `EntityManager.createQuery(...)` | `EntityManager.createNativeQuery(...)` hoặc JDBC |
| `SELECT *` | Không phải cú pháp dùng để chọn toàn bộ entity | Phổ biến, dù không luôn tối ưu |
| Hạn chế | Chỉ truy vấn những gì mô hình JPA diễn đạt được theo JPQL | Có thể dùng tính năng SQL đặc thù DB |

Cùng một ý định truy vấn đơn hàng có mã `SO-001`:

**JPQL:**

```jpql
select o
from SalesOrder o
where o.orderNumber = :orderNumber
```

**SQL minh họa mà provider có thể sinh:**

```sql
SELECT
    o.id,
    o.order_no,
    o.customer_id,
    o.order_status,
    o.placed_at,
    o.total_amount
FROM sales_order o
WHERE o.order_no = ?;
```

JPQL không “bỏ qua database”. JPA provider vẫn dịch truy vấn thành SQL hoặc thao tác cơ sở dữ liệu tương đương; JPQL chỉ giúp code phụ thuộc vào **mô hình entity và mapping** thay vì tên vật lý trong schema.

## 2. Mô hình entity dùng xuyên suốt bài học

Giả sử ứng dụng quản lý khách hàng và đơn hàng:

```text
Java entity model                            Database schema

Customer                                     crm_customer
  id            -------------------------->    customer_id
  customerName  -------------------------->    display_name
  email         -------------------------->    email_address

SalesOrder                                   sales_order
  id            -------------------------->    id
  orderNumber   -------------------------->    order_no
  status        -------------------------->    order_status
  placedAt      -------------------------->    placed_at
  totalAmount   -------------------------->    total_amount
  customer      ---- @ManyToOne ---------->    customer_id (FK)

OrderLine                                    sales_order_line
  id            -------------------------->    id
  productSku    -------------------------->    sku
  quantity      -------------------------->    qty
  unitPrice     -------------------------->    unit_price
  order         ---- @ManyToOne ---------->    order_id (FK)
```

Quan hệ trong Java:

```text
Customer (1) <---> (N) SalesOrder (1) <---> (N) OrderLine
          orders               customer     lines       order
```

### 2.1. Entity Customer

```java
package com.example.shop.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "crm_customer")
public class Customer {

    @Id
    @GeneratedValue
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String customerName;

    @Column(name = "email_address", nullable = false, unique = true)
    private String email;

    @OneToMany(mappedBy = "customer")
    private List<SalesOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getCustomerName() {
        return customerName;
    }

    public String getEmail() {
        return email;
    }

    public List<SalesOrder> getOrders() {
        return orders;
    }
}
```

Ở đây **entity name mặc định** là `Customer`. Tên database table là `crm_customer`, còn persistent attribute là `customerName`, không phải `display_name`.

### 2.2. Entity SalesOrder với entity name tường minh

```java
package com.example.shop.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity(name = "SalesOrder")
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "order_no", nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected SalesOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getPlacedAt() {
        return placedAt;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

Enum:

```java
package com.example.shop.persistence;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

Cần đặc biệt phân biệt:

- `@Entity(name = "SalesOrder")` khai báo **tên entity được dùng trong JPQL**.
- `@Table(name = "sales_order")` khai báo **tên bảng SQL**.
- Field `orderNumber` là **persistent attribute của entity**.
- `@Column(name = "order_no")` ánh xạ attribute đó sang **cột SQL**.
- Field `customer` là **association tới Customer**.
- `@JoinColumn(name = "customer_id")` chỉ định **cột khóa ngoại**; JPQL thường đi qua `o.customer`, không phải `o.customer_id`.

Khi không chỉ định tên trong `@Entity`, tên entity mặc định là tên lớp không bao gồm package, ví dụ `Customer` và `OrderLine`.

### 2.3. Entity OrderLine

```java
package com.example.shop.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "sales_order_line")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "sku", nullable = false)
    private String productSku;

    @Column(name = "qty", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal unitPrice;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    protected OrderLine() {
    }

    public Long getId() {
        return id;
    }

    public String getProductSku() {
        return productSku;
    }

    public int getQuantity() {
        return quantity;
    }

    public SalesOrder getOrder() {
        return order;
    }
}
```

Một số ví dụ về đối chiếu:

| Khái niệm Java/JPQL | Tương ứng SQL |
|---|---|
| `Customer` | `crm_customer` |
| `c.id` | `crm_customer.customer_id` |
| `c.customerName` | `crm_customer.display_name` |
| `SalesOrder` | `sales_order` |
| `o.orderNumber` | `sales_order.order_no` |
| `o.status` | `sales_order.order_status` |
| `o.customer` | Association qua `sales_order.customer_id` |
| `o.lines` | Collection liên quan tới `sales_order_line.order_id` |
| `i.productSku` | `sales_order_line.sku` |
| `i.quantity` | `sales_order_line.qty` |

Khi đã biết mapping, JPQL không cần biết chính xác tên vật lý của bảng và cột.

## 3. Cú pháp JPQL SELECT cơ bản

Mẫu tổng quát:

```jpql
select <biểu thức cần lấy>
from <EntityName> <alias>
where <điều kiện>
order by <biểu thức sắp xếp>
```

Ví dụ:

```jpql
select o
from SalesOrder o
where o.status = :status
order by o.placedAt desc
```

Phân tích:

| Thành phần | Vai trò |
|---|---|
| `select o` | Trả về entity instance được định danh bởi `o` |
| `from SalesOrder o` | Truy vấn entity `SalesOrder`, đặt **identification variable** `o` |
| `where o.status = :status` | Lọc theo **thuộc tính Java `status`** |
| `:status` | Named parameter được bind từ Java |
| `order by o.placedAt desc` | Sắp xếp theo **thuộc tính `placedAt`**, không phải cột `placed_at` |

**Không viết `select *` như SQL.** Với JPQL, muốn trả entity hãy dùng `select o`, nơi `o` là alias của entity. Trong một số truy vấn đơn giản, `SELECT` có thể được lược bỏ tùy cú pháp JPQL/version, nhưng khai báo tường minh giúp người học và công cụ phân tích dễ đọc hơn.

### 3.1. Identification variable không phải tên cột

Trong:

```jpql
select o
from SalesOrder o
```

`o` là biến định danh đại diện cho một entity trong truy vấn. Nó **không phải** bí danh cột hoặc một bảng SQL thật do ứng dụng tự khai báo. Provider dùng alias này để phân tích những path như `o.orderNumber`, `o.customer` và dịch sang SQL tương ứng.

Có thể đặt alias khác:

```jpql
select orderEntity
from SalesOrder orderEntity
where orderEntity.status = :status
```

Miễn cú pháp hợp lệ, ý nghĩa không thay đổi. Thực tế nên chọn alias ngắn nhưng dễ hiểu.

### 3.2. JPQL keywords khác tên entity/attribute

Các từ khóa như `SELECT`, `FROM`, `WHERE` thường có thể viết hoa/thường theo cú pháp JPQL. Nhưng **tên entity và tên persistent attribute phải khớp với mô hình Java và metadata mapping**.

Ví dụ:

```jpql
select o from SalesOrder o where o.orderNumber = :number
```

khác ý nghĩa với:

```jpql
-- Sai nếu entity không có thuộc tính order_no:
select o from SalesOrder o where o.order_no = :number
```

Vì Java dùng `orderNumber` chứ không có persistent attribute `order_no`, provider có thể báo lỗi truy vấn trước khi gửi SQL. Refactor tên field/property ở Java có thể đòi hỏi cập nhật JPQL, dù tên cột database vẫn giữ nguyên.

## 4. Thực thi JPQL bằng EntityManager

JPA cung cấp `EntityManager.createQuery`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;

public List<SalesOrder> findOrdersByStatus(
        EntityManager em,
        OrderStatus status
) {
    TypedQuery<SalesOrder> query = em.createQuery(
        """
        select o
        from SalesOrder o
        where o.status = :status
        order by o.placedAt desc
        """,
        SalesOrder.class
    );

    query.setParameter("status", status);
    return query.getResultList();
}
```

Trong ví dụ:

1. `createQuery` nhận **chuỗi JPQL**, không phải SQL table names.
2. Đối số `SalesOrder.class` khai báo kiểu kết quả khi dùng `TypedQuery<SalesOrder>`.
3. `setParameter("status", status)` bind một Java `OrderStatus`.
4. `getResultList()` trả danh sách; nếu không có kết quả thì trả danh sách rỗng.
5. Khi SELECT entity, các kết quả thường là **managed entity instances** thuộc persistence context của `em` đang hoạt động.

Không truyền giá trị Java `status` bằng cách nối trực tiếp vào chuỗi query. Parameter binding giúp đúng kiểu dữ liệu và hạn chế nguy cơ injection.

### 4.1. Với entity managed, thay đổi có thể được dirty-check

```java
List<SalesOrder> orders = em.createQuery(
    "select o from SalesOrder o where o.status = :status",
    SalesOrder.class
)
.setParameter("status", OrderStatus.NEW)
.getResultList();

// Các SalesOrder là entity được quản lý nếu context còn hoạt động.
// Nếu cập nhật persistent state trong transaction ghi,
// JPA có thể đồng bộ thay đổi qua dirty checking.
```

Điều đó khác DTO projection; DTO không tự được managed. Đừng mặc định rằng mọi thứ trả từ query đều là object chỉ-đọc.

### 4.2. Persistence context có thể giữ entity cũ

Nếu một SalesOrder đã managed trong context, một entity query mới trả về cùng identity sẽ dùng lại managed instance đó. JPQL có thể vẫn thực thi SQL để tìm result set, nhưng không tự đảm bảo mọi field đã managed sẽ được refresh từ database.

Nếu transaction khác cập nhật row trong khi context hiện tại còn sống, cần hiểu transaction isolation, `refresh` và concurrency. JPQL entity query không phải lệnh “bỏ cache cấp một và tải mọi thứ từ đầu” mặc định.

## 5. WHERE: lọc theo thuộc tính entity

JPQL dùng toán tử và biểu thức gần với SQL, nhưng **đường dẫn dữ liệu là đường dẫn thuộc tính Java**.

### 5.1. Bằng, khác, lớn hơn, nhỏ hơn

```jpql
select o
from SalesOrder o
where o.totalAmount >= :minTotal
```

```jpql
select o
from SalesOrder o
where o.status <> :excludedStatus
```

```jpql
select o
from SalesOrder o
where o.placedAt < :cutoff
```

Mỗi tham số được bind kiểu Java tương thích, ví dụ `BigDecimal`, `OrderStatus` và `Instant`.

### 5.2. AND, OR, NOT và dấu ngoặc

```jpql
select o
from SalesOrder o
where
    (o.status = :statusA or o.status = :statusB)
    and o.totalAmount >= :minTotal
```

Dấu ngoặc giúp diễn đạt ưu tiên logic rõ ràng. Nếu bỏ ngoặc khi kết hợp `AND`/`OR`, query có thể trả nhiều hoặc ít đơn hàng hơn mong đợi.

### 5.3. BETWEEN

```jpql
select o
from SalesOrder o
where o.placedAt between :fromTime and :toTime
```

`BETWEEN` thường bao gồm hai biên theo ngữ nghĩa truy vấn. Với khoảng thời gian liên tục, nhiều hệ thống chọn biểu thức **nửa mở**:

```jpql
select o
from SalesOrder o
where o.placedAt >= :fromInclusive
  and o.placedAt < :toExclusive
```

Cách nửa mở tránh khó xử lý mili/micro/nanosecond cuối ngày và hỗ trợ ghép các khoảng thời gian liền nhau mà không chồng lặp.

### 5.4. IN

```jpql
select o
from SalesOrder o
where o.status in :statuses
```

Java:

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o from SalesOrder o
    where o.status in :statuses
    """,
    SalesOrder.class
)
.setParameter(
    "statuses",
    List.of(OrderStatus.NEW, OrderStatus.PAID)
)
.getResultList();
```

Cần xử lý **collection rỗng** trước khi bind; cú pháp SQL sinh ra cho `IN ()` có thể không hợp lệ hoặc có hành vi provider-specific. Nếu tập lọc rỗng có nghĩa không có kết quả, service nên trả danh sách rỗng ngay hoặc dựng query phù hợp.

### 5.5. LIKE

```jpql
select c
from Customer c
where lower(c.customerName) like :pattern
```

Java:

```java
String pattern = "%" + keyword.toLowerCase(Locale.ROOT) + "%";

List<Customer> results = em.createQuery(
    """
    select c from Customer c
    where lower(c.customerName) like :pattern
    """,
    Customer.class
)
.setParameter("pattern", pattern)
.getResultList();
```

`LOWER` và `LIKE` có thể giúp so khớp không phân biệt hoa/thường theo cách thông dụng, nhưng collation, Unicode normalization và khả năng dùng index phụ thuộc database. Để tìm chuỗi có ký tự `%` hoặc `_` được hiểu **theo nghĩa literal**, phải thiết kế escape pattern theo cú pháp được hỗ trợ, không chỉ nối chuỗi tùy ý.

### 5.6. IS NULL

Để tìm đơn hàng chưa có giá trị ở một thuộc tính nullable:

```jpql
select o
from SalesOrder o
where o.placedAt is null
```

Trong entity mẫu `placedAt` được khai báo non-null; ví dụ chỉ minh họa cú pháp. Trong thực tế, áp dụng với thuộc tính thật sự nullable, ví dụ `shippedAt`.

**Không viết**:

```jpql
where o.shippedAt = null
```

SQL/JPQL có logic ba giá trị với `NULL`; dùng `IS NULL` hoặc `IS NOT NULL`.

### 5.7. COALESCE và CASE

JPQL hỗ trợ những biểu thức chuẩn hữu ích:

```jpql
select coalesce(c.customerName, 'Unnamed')
from Customer c
```

```jpql
select
    case
        when o.totalAmount >= :threshold then 'HIGH'
        else 'NORMAL'
    end
from SalesOrder o
```

`COALESCE`, `CASE` và các biểu thức scalar tạo ra **giá trị kết quả**, không tự cập nhật entity.

## 6. Path expression: o.customer.customerName nghĩa là gì?

Đây là khác biệt lớn giữa JPQL và SQL.

Giả sử SalesOrder có:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id")
private Customer customer;
```

và Customer có:

```java
@Column(name = "display_name")
private String customerName;
```

Khi muốn tìm đơn hàng của một khách hàng theo tên:

```jpql
select o
from SalesOrder o
where o.customer.customerName = :customerName
```

Ý nghĩa:

```text
o                         : SalesOrder
o.customer                : association SalesOrder -> Customer
o.customer.customerName   : thuộc tính Customer.customerName
```

Provider biết từ mapping rằng association nối qua FK `sales_order.customer_id` tới `crm_customer.customer_id`. JPQL **không cần nhắc các cột FK**.

SQL tương đương khái niệm:

```sql
SELECT o.*
FROM sales_order o
JOIN crm_customer c
  ON o.customer_id = c.customer_id
WHERE c.display_name = ?;
```

Đây thường là một **implicit join** do path expression qua association có giá trị đơn (single-valued association) tạo ra. Chi tiết SQL provider có thể tối ưu hoặc cấu trúc khác, nhưng ngữ nghĩa Java rõ ràng: đi từ entity `o` qua thuộc tính `customer` rồi tới `customerName`.

### 6.1. Không chấm tiếp vào collection-valued association như một entity đơn

`SalesOrder.lines` là `List<OrderLine>`. Viết:

```jpql
-- Sai kiểu path vì lines là collection:
select o from SalesOrder o
where o.lines.productSku = :sku
```

không đúng cách điều hướng collection trong JPQL. Phải dùng **JOIN** để tạo biến đại diện cho từng phần tử:

```jpql
select distinct o
from SalesOrder o
join o.lines i
where i.productSku = :sku
```

Khi `join o.lines i`, biến `i` là **OrderLine entity** nên `i.productSku` hợp lệ.

### 6.2. Path qua association nullable có thể lọc mất row

Với association nullable, biểu thức:

```jpql
where o.customer.customerName = :name
```

có ngữ nghĩa join tương ứng, thường loại các order không có customer. Nếu cần giữ cả những order không có quan hệ, phải thiết kế `LEFT JOIN` và điều kiện phù hợp:

```jpql
select o
from SalesOrder o
left join o.customer c
where c.customerName = :name or c is null
```

Ở entity mẫu, `customer` có `optional = false` nên ví dụ nullable chỉ có ý nghĩa nếu thiết kế entity được thay đổi cho phép không có customer. Quan trọng là hiểu **kiểu join ảnh hưởng tập kết quả**, không chỉ ảnh hưởng hiệu năng.

## 7. JOIN theo tên association, không viết ON khóa ngoại thủ công

SQL thường có:

```sql
SELECT o.*, c.*
FROM sales_order o
JOIN crm_customer c
  ON o.customer_id = c.customer_id;
```

JPQL tự nhiên hơn:

```jpql
select o
from SalesOrder o
join o.customer c
```

Ở đây:

- `o.customer` là **thuộc tính Java đại diện relationship**.
- `c` là alias cho entity `Customer` qua association.
- Không cần `ON o.customer_id = c.customer_id`.
- `@JoinColumn` trong mapping đã mô tả cách nối FK.

### 7.1. INNER JOIN

```jpql
select o
from SalesOrder o
join o.customer c
where c.email = :email
```

Chỉ giữ những order có association thỏa join và điều kiện. Nếu `customer` bắt buộc thì inner join tương ứng logic mô hình.

### 7.2. LEFT JOIN

```jpql
select c
from Customer c
left join c.orders o
```

Giữ cả khách hàng **không có đơn hàng** ở mức joined rows. Nếu chỉ muốn khách hàng chưa từng có order, có thể viết:

```jpql
select c
from Customer c
left join c.orders o
where o.id is null
```

Hoặc dùng `IS EMPTY`/`NOT EXISTS` tùy nhu cầu.

### 7.3. JOIN với collection

```jpql
select o, i
from SalesOrder o
join o.lines i
where i.quantity >= :minimumQty
```

Kết quả `select o, i` có hai thành phần, thường được trả về qua `Object[]` hoặc `Tuple`. Nếu chỉ muốn entity OrderLine:

```jpql
select i
from SalesOrder o
join o.lines i
where o.orderNumber = :orderNumber
```

Đây là query dựa trên graph association, không phụ thuộc tên `sales_order_line` hay `order_id` trong JPQL.

### 7.4. JOIN ... ON dùng để bổ sung điều kiện join

JPQL hiện đại hỗ trợ `ON` trong association join để đặt điều kiện tham gia join, khác với việc tự diễn đạt FK mapping:

```jpql
select c, o
from Customer c
left join c.orders o on o.status = :paidStatus
```

Nếu muốn **giữ Customer không có order PAID**, đặt điều kiện `o.status` trong `ON` của left join thường khác với đặt nó ở `WHERE`.

So sánh:

```jpql
-- Giữ mọi Customer và join các đơn PAID nếu có:
select c, o
from Customer c
left join c.orders o on o.status = :paidStatus
```

```jpql
-- WHERE có thể loại các Customer không có order PAID:
select c, o
from Customer c
left join c.orders o
where o.status = :paidStatus
```

JPA provider vẫn tự quyết định FK join theo association metadata; `ON` ở đây bổ sung predicate cho join, không thay thế mapping.

### 7.5. Nhiều collection join dễ nhân bản kết quả

Nếu Customer có nhiều SalesOrder và mỗi SalesOrder có nhiều OrderLine:

```jpql
select c
from Customer c
join c.orders o
join o.lines i
```

Một Customer có thể xuất hiện trong nhiều result rows tương ứng các cặp order-line. Đây là hậu quả của quan hệ một-nhiều trong kết quả truy vấn, không phải dữ liệu DB “tạo duplicate customer”.

Nếu chỉ cần các Customer duy nhất:

```jpql
select distinct c
from Customer c
join c.orders o
join o.lines i
where i.productSku = :sku
```

`DISTINCT` nói tới tính duy nhất của kết quả truy vấn. Cách provider diễn giải hoặc đẩy xuống SQL và chi phí loại trùng phụ thuộc phiên bản và query shape.

## 8. Tại sao o.customerId có thể không tồn tại?

Trong một số dự án entity có hai field:

```java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
```

Nhưng **không có**:

```java
private Long customerId;
```

Vậy:

```jpql
-- Sai nếu SalesOrder không có persistent attribute customerId:
select o from SalesOrder o
where o.customerId = :id
```

Trong JPQL dùng:

```jpql
select o
from SalesOrder o
where o.customer.id = :customerId
```

Hoặc so sánh cả entity reference:

```jpql
select o
from SalesOrder o
where o.customer = :customer
```

Java:

```java
Customer customer = em.getReference(
    Customer.class,
    customerId
);

List<SalesOrder> orders = em.createQuery(
    """
    select o from SalesOrder o
    where o.customer = :customer
    """,
    SalesOrder.class
)
.setParameter("customer", customer)
.getResultList();
```

`o.customer.id` có thể được provider tối ưu qua FK mà không nhất thiết join toàn bộ bảng Customer trong mọi trường hợp; đừng suy ra SQL chính xác nếu chưa xem log.

Nếu entity **thực sự** có field persistent `customerId` được ánh xạ phù hợp, JPQL có thể dùng `o.customerId`. Quy tắc là **thuộc tính đã ánh xạ tồn tại hay không**, không phải “trong database có cột customer_id thì JPQL tự tạo customerId”.

## 9. Tên entity, tên class, tên bảng và tên property

Ba khái niệm có thể khác nhau:

```java
@Entity(name = "OrderEntity")
@Table(name = "legacy_tbl_order")
public class SalesOrderRecord {

    @Column(name = "order_number_db")
    private String orderNumber;
}
```

JPQL:

```jpql
select o
from OrderEntity o
where o.orderNumber = :number
```

Không phải:

```jpql
-- Sai nếu entity name được khai báo OrderEntity:
select o from SalesOrderRecord o
```

và cũng không phải:

```jpql
-- Sai kiểu truy vấn JPQL vì dùng SQL table/column:
select o from legacy_tbl_order o
where o.order_number_db = :number
```

| Thành phần | Giá trị trong ví dụ | Được dùng ở đâu? |
|---|---|---|
| Java class | `SalesOrderRecord` | Kiểu Java, compile-time, mapping |
| Entity name | `OrderEntity` | `FROM` của JPQL |
| Table name | `legacy_tbl_order` | SQL/schema |
| Persistent attribute | `orderNumber` | `o.orderNumber` trong JPQL |
| Column name | `order_number_db` | SQL/schema |

### 9.1. Đổi tên cột database chưa chắc phải đổi JPQL

Giả sử migration đổi `order_no` thành `order_code`, còn Java field vẫn là `orderNumber`:

```java
@Column(name = "order_code")
private String orderNumber;
```

Câu JPQL:

```jpql
select o
from SalesOrder o
where o.orderNumber = :number
```

vẫn có thể giữ nguyên. JPA mapping đóng vai trò “lớp dịch” giữa mô hình Java và schema vật lý. Ngược lại, refactor Java field `orderNumber` thành `number` có thể đòi hỏi cập nhật JPQL dù DB column không thay.

### 9.2. Field access và property access

JPA xác định persistent attributes theo access strategy.

**Field access**: `@Id` nằm trên field, tên persistent attribute thường là tên field:

```java
@Id
private Long id;

@Column(name = "display_name")
private String customerName;
```

JPQL dùng `c.customerName`.

**Property access**: `@Id` đặt trên getter, tên persistent property theo JavaBeans:

```java
private Long id;
private String customerName;

@Id
public Long getId() {
    return id;
}

@Column(name = "display_name")
public String getCustomerName() {
    return customerName;
}
```

JPQL vẫn dùng `c.customerName`, không dùng `c.getCustomerName()` hoặc `c.display_name`.

Không gọi method Java tùy ý bên trong JPQL path:

```jpql
-- Không phải cú pháp JPQL gọi method object:
select c from Customer c
where c.getCustomerName() = :name
```

Muốn một thuộc tính xuất hiện trong JPQL, nó phải là **persistent attribute** theo mapping/access strategy, không chỉ là một method tiện ích bất kỳ.

## 10. Named parameters và positional parameters

### 10.1. Named parameters: dễ đọc và bảo trì

```jpql
select o
from SalesOrder o
where o.status = :status
  and o.placedAt >= :fromTime
```

Java:

```java
TypedQuery<SalesOrder> query = em.createQuery(
    """
    select o from SalesOrder o
    where o.status = :status
      and o.placedAt >= :fromTime
    """,
    SalesOrder.class
);

query.setParameter("status", OrderStatus.PAID);
query.setParameter("fromTime", fromInstant);
```

Ưu điểm:

- Dễ thấy mỗi giá trị ứng với điều kiện nào.
- Không phụ thuộc thứ tự tham số trong chuỗi.
- Giảm sai sót khi thêm điều kiện mới.

Lưu ý: trong `setParameter("status", ...)`, tên viết **không có dấu hai chấm**. Ký hiệu `:status` chỉ dùng trong chuỗi JPQL.

### 10.2. Positional parameters: đánh số từ 1

```jpql
select o
from SalesOrder o
where o.status = ?1
  and o.totalAmount >= ?2
```

Java:

```java
em.createQuery(
    """
    select o from SalesOrder o
    where o.status = ?1
      and o.totalAmount >= ?2
    """,
    SalesOrder.class
)
.setParameter(1, OrderStatus.PAID)
.setParameter(2, minimumAmount)
.getResultList();
```

Với JPQL chuẩn, positional parameters thường được biểu diễn bằng `?1`, `?2`…, không phải mặc định dùng dấu `?` không số như nhiều ví dụ JDBC.

### 10.3. Không bind tên entity hoặc tên thuộc tính như dữ liệu

Parameter dành cho **giá trị**, không phải thay thế cấu trúc cú pháp:

```jpql
-- Không hợp lệ để chọn entity name động:
select o from :entityName o
```

```jpql
-- Không hợp lệ để truyền tên property làm path:
select o from SalesOrder o
order by :sortField
```

Nếu client được chọn trường sắp xếp, hãy dùng **whitelist** tên persistent attributes được phép:

```java
String orderBy = switch (sortKey) {
    case "date" -> "o.placedAt";
    case "total" -> "o.totalAmount";
    case "number" -> "o.orderNumber";
    default -> throw new IllegalArgumentException(
        "Trường sắp xếp không hợp lệ"
    );
};

String jpql =
    "select o from SalesOrder o order by " + orderBy;
```

Code này **chỉ nối giá trị cố định từ whitelist**, không nối trực tiếp input tùy ý. Giá trị lọc như email, trạng thái, ngày vẫn phải qua parameter binding.

### 10.4. Tránh JPQL injection

Không nên:

```java
String jpql =
    "select c from Customer c where c.email = '" +
    userInput +
    "'";
```

Dùng:

```java
List<Customer> customers = em.createQuery(
    """
    select c from Customer c
    where c.email = :email
    """,
    Customer.class
)
.setParameter("email", userInput)
.getResultList();
```

Việc bind giúp provider xử lý escaping, typing và cấu trúc query hợp lý, đồng thời tránh giá trị người dùng thay đổi logic JPQL.

## 11. Lấy một entity, nhiều entity và xử lý kết quả

### 11.1. getResultList

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    where o.status = :status
    """,
    SalesOrder.class
)
.setParameter("status", OrderStatus.NEW)
.getResultList();
```

Không có row phù hợp thì thường nhận **danh sách rỗng**, không phải `null`.

### 11.2. getSingleResult

Khi query dự kiến đúng một row:

```java
Customer customer = em.createQuery(
    """
    select c
    from Customer c
    where c.email = :email
    """,
    Customer.class
)
.setParameter("email", email)
.getSingleResult();
```

Cần hiểu:

- `NoResultException` nếu không có kết quả.
- `NonUniqueResultException` nếu nhiều kết quả phù hợp.
- Những exception trên cần được xử lý theo API contract và tình huống nghiệp vụ; không dùng `getSingleResult` cho danh sách nhiều row không xác định.

Một hướng không dựa vào exception cho tình huống không tồn tại:

```java
List<Customer> matches = em.createQuery(
    """
    select c from Customer c
    where c.email = :email
    """,
    Customer.class
)
.setParameter("email", email)
.setMaxResults(1)
.getResultList();

Customer customer = matches.isEmpty() ? null : matches.get(0);
```

Cách này không chứng minh email duy nhất. Dù query trả một result vì `setMaxResults(1)`, database vẫn cần unique constraint nếu nghiệp vụ bắt buộc email unique.

### 11.3. Không lấy nhiều row rồi dùng getSingleResult

```jpql
select o
from SalesOrder o
where o.status = :status
```

Có thể trả hàng trăm đơn. Dùng `getSingleResult()` sẽ không phù hợp. Nếu chỉ muốn đơn mới nhất, thêm `order by` và `setMaxResults(1)`.

## 12. Projection: SELECT entity, field, nhiều field và DTO

JPQL không bắt buộc chỉ trả entity.

### 12.1. Trả toàn bộ entity

```jpql
select o from SalesOrder o
```

Java:

```java
List<SalesOrder> orders = em.createQuery(
    "select o from SalesOrder o",
    SalesOrder.class
).getResultList();
```

Khi query chọn entity, JPA quản lý các instance theo persistence context. Truy vấn entity có thể kéo theo fetch plan và association loading.

### 12.2. Trả một thuộc tính đơn

```jpql
select o.orderNumber
from SalesOrder o
where o.status = :status
```

Java:

```java
List<String> numbers = em.createQuery(
    """
    select o.orderNumber
    from SalesOrder o
    where o.status = :status
    """,
    String.class
)
.setParameter("status", OrderStatus.PAID)
.getResultList();
```

`numbers` là các String, **không phải managed entity**.

### 12.3. Trả nhiều scalar columns

```jpql
select o.id, o.orderNumber, o.totalAmount
from SalesOrder o
```

Java:

```java
List<Object[]> rows = em.createQuery(
    """
    select o.id, o.orderNumber, o.totalAmount
    from SalesOrder o
    """,
    Object[].class
).getResultList();

for (Object[] row : rows) {
    Long id = (Long) row[0];
    String orderNumber = (String) row[1];
    BigDecimal totalAmount = (BigDecimal) row[2];
}
```

Cách này hoạt động nhưng có nhược điểm: phụ thuộc thứ tự và phải cast các giá trị. Nếu muốn kết quả có kiểu rõ ràng, dùng DTO projection hoặc `Tuple`.

### 12.4. DTO constructor expression

Định nghĩa DTO:

```java
package com.example.shop.readmodel;

import java.math.BigDecimal;

public record OrderSummary(
    Long id,
    String orderNumber,
    String customerName,
    BigDecimal totalAmount
) { }
```

Truy vấn:

```jpql
select new com.example.shop.readmodel.OrderSummary(
    o.id,
    o.orderNumber,
    c.customerName,
    o.totalAmount
)
from SalesOrder o
join o.customer c
```

Java:

```java
List<OrderSummary> summaries = em.createQuery(
    """
    select new com.example.shop.readmodel.OrderSummary(
        o.id, o.orderNumber, c.customerName, o.totalAmount
    )
    from SalesOrder o
    join o.customer c
    """,
    OrderSummary.class
).getResultList();
```

Lưu ý:

- JPQL `new` phải dùng **tên class DTO đủ package** theo constructor expression thông thường.
- Constructor (hoặc record canonical constructor) phải khớp số lượng và kiểu tham số.
- `OrderSummary` không có `@Entity` và **không được dirty-check**.
- Entity instances xuất hiện ở các biểu thức khác trong projection vẫn tuân thủ những quy tắc của chúng; đừng coi toàn bộ query DTO là cơ chế tự động khóa mọi entity khỏi context.
- DTO projection thường phù hợp cho API cần một tập cột xác định, giảm nguy cơ lazy loading ngoài ranh giới transaction.

### 12.5. Tuple

Một số ứng dụng dùng `Tuple` để đọc theo alias:

```java
List<Tuple> rows = em.createQuery(
    """
    select o.id as orderId,
           o.orderNumber as orderNumber
    from SalesOrder o
    """,
    Tuple.class
).getResultList();

for (Tuple row : rows) {
    Long id = row.get("orderId", Long.class);
    String number = row.get("orderNumber", String.class);
}
```

`Tuple` cho phép truy cập theo alias/kiểu, nhưng với hợp đồng API ổn định, DTO tường minh thường dễ bảo trì hơn.

## 13. Các hàm aggregate: COUNT, SUM, AVG, MIN, MAX

JPQL hỗ trợ tính toán dữ liệu tổng hợp theo persistent attributes.

### 13.1. COUNT

```jpql
select count(o)
from SalesOrder o
where o.status = :status
```

Java:

```java
Long count = em.createQuery(
    """
    select count(o)
    from SalesOrder o
    where o.status = :status
    """,
    Long.class
)
.setParameter("status", OrderStatus.PAID)
.getSingleResult();
```

`COUNT` thường trả `Long` trong JPQL chuẩn.

### 13.2. SUM

```jpql
select sum(o.totalAmount)
from SalesOrder o
where o.status = :status
```

Với `totalAmount` là `BigDecimal`, kết quả `SUM` có kiểu tương ứng theo quy tắc JPQL, thường là `BigDecimal`. Khi không có dữ liệu phù hợp, `SUM` có thể trả `null`, khác `COUNT` trả 0.

```java
BigDecimal sum = em.createQuery(
    """
    select sum(o.totalAmount)
    from SalesOrder o
    where o.status = :status
    """,
    BigDecimal.class
)
.setParameter("status", OrderStatus.PAID)
.getSingleResult();

BigDecimal safeSum =
    sum != null ? sum : BigDecimal.ZERO;
```

### 13.3. GROUP BY

Đếm đơn hàng theo trạng thái:

```jpql
select o.status, count(o)
from SalesOrder o
group by o.status
```

Đếm đơn của từng khách hàng, kể cả người chưa có đơn:

```jpql
select c.id, c.customerName, count(o)
from Customer c
left join c.orders o
group by c.id, c.customerName
```

Ở đây `c.orders` là association collection; JPQL dùng metadata relationship, không tự viết `sales_order.customer_id = crm_customer.customer_id`.

### 13.4. HAVING

Chỉ lấy khách hàng có ít nhất ba đơn:

```jpql
select c.id, count(o)
from Customer c
join c.orders o
group by c.id
having count(o) >= :minimumOrders
```

Với `JOIN`, người không có đơn sẽ không xuất hiện; trong trường hợp này điều kiện tối thiểu ba đơn nên inner join là hợp lý.

### 13.5. Phân biệt GROUP BY và DISTINCT

- `DISTINCT` loại trùng ở tập kết quả.
- `GROUP BY` gom rows theo key để tính aggregate.
- Một query có thể dùng cả hai trong tình huống phù hợp, nhưng không nên thêm theo thói quen nếu không cần.

## 14. EXISTS, MEMBER OF và collection expressions

Các câu truy vấn dựa trên association có thể diễn đạt bằng nhiều cách.

### 14.1. EXISTS: khách hàng có đơn hàng PAID

```jpql
select c
from Customer c
where exists (
    select o.id
    from SalesOrder o
    where o.customer = c
      and o.status = :status
)
```

Đây là **correlated subquery**: biến `c` ở query ngoài được dùng trong query con.

### 14.2. IS EMPTY: collection không có phần tử

```jpql
select c
from Customer c
where c.orders is empty
```

Truy vấn khách hàng chưa có order. Không cần nhớ tên cột FK trong JPQL.

### 14.3. SIZE: kích thước collection

```jpql
select c
from Customer c
where size(c.orders) >= :minimumOrders
```

Provider có thể dịch thành subquery hoặc join/aggregate phù hợp. Dùng hàm collection thuận tiện về ý nghĩa nhưng nên quan sát SQL khi chạy ở bảng lớn.

### 14.4. MEMBER OF

Với một entity OrderLine `:line`, có thể hỏi phần tử đó có thuộc collection `o.lines` không:

```jpql
select o
from SalesOrder o
where :line member of o.lines
```

Ngữ nghĩa phụ thuộc mapping collection; bind tham số là entity `OrderLine` hợp lệ, không phải một giá trị ID tùy ý nếu mapping đòi hỏi entity reference.

### 14.5. JOIN hay EXISTS?

Với câu hỏi “có ít nhất một dòng hàng SKU X”, có hai cách:

```jpql
select distinct o
from SalesOrder o
join o.lines i
where i.productSku = :sku
```

và:

```jpql
select o
from SalesOrder o
where exists (
    select i.id
    from OrderLine i
    where i.order = o
      and i.productSku = :sku
)
```

Chúng thể hiện cùng ý định trong trường hợp này nhưng có plan khác nhau tùy database/index. `EXISTS` thường tránh việc JOIN tạo nhiều result rows cho cùng order, trong khi `JOIN` hữu ích khi cần lấy hoặc lọc theo phần tử trực tiếp.

**Không có lựa chọn tối ưu tuyệt đối** nếu chưa đo SQL thật, chỉ mục và lượng dữ liệu.

## 15. ORDER BY và pagination

### 15.1. ORDER BY dùng persistent attributes

```jpql
select o
from SalesOrder o
order by o.placedAt desc, o.id desc
```

Không viết `order by placed_at` nếu Java entity chỉ có `placedAt`. Có thể sắp xếp theo thuộc tính của association khi truy vấn join phù hợp:

```jpql
select o
from SalesOrder o
join o.customer c
order by c.customerName asc, o.id asc
```

Thêm tie-breaker như `o.id` giúp thứ tự ổn định hơn khi nhiều row có cùng `placedAt` hoặc cùng `customerName`.

### 15.2. setFirstResult và setMaxResults

JPQL không cần trực tiếp dùng `LIMIT`/`OFFSET` theo SQL dialect. JPA API có:

```java
List<SalesOrder> page = em.createQuery(
    """
    select o
    from SalesOrder o
    order by o.placedAt desc, o.id desc
    """,
    SalesOrder.class
)
.setFirstResult(20)
.setMaxResults(10)
.getResultList();
```

Ví dụ lấy page gồm tối đa 10 row, bắt đầu từ offset 20 theo thứ tự đã quy định.

`setFirstResult` và `setMaxResults` là API JPA; provider dịch thành SQL pagination phù hợp database/dialect.

### 15.3. Tránh pagination không có ORDER BY

```jpql
select o from SalesOrder o
```

nếu kết hợp `setFirstResult`/`setMaxResults` mà không có thứ tự ổn định, thứ tự rows không được đảm bảo theo ý định nghiệp vụ; hai lần đọc có thể trả tập bản ghi khác nhau.

### 15.4. Offset lớn có thể đắt

Nếu cần phân trang sâu, offset tăng cao có thể khiến database phải bỏ qua nhiều rows. Có thể cân nhắc **keyset pagination** dùng tuple thuộc tính sắp xếp và ID:

```jpql
select o
from SalesOrder o
where
    o.placedAt < :lastPlacedAt
    or (
        o.placedAt = :lastPlacedAt
        and o.id < :lastId
    )
order by o.placedAt desc, o.id desc
```

Sau đó `setMaxResults(pageSize)`. Mẫu này giả định `placedAt` và `id` không null và thứ tự đã chọn. Cần thiết kế index và cách xử lý dữ liệu chèn/xóa đồng thời theo use case.

### 15.5. Collection JOIN FETCH và pagination

Không nên mặc định:

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
order by o.placedAt desc
```

kết hợp pagination sẽ tương đương “lấy đúng 10 Order cùng toàn bộ lines” theo mọi provider. Join collection nhân bản SQL rows; provider có thể phải phân trang trong memory hoặc cảnh báo/không hỗ trợ pagination hiệu quả.

Một cách phổ biến:

1. Phân trang ID SalesOrder theo query đơn giản.
2. Query riêng lấy entity và collection liên quan theo nhóm ID.
3. Giữ thứ tự kết quả theo danh sách ID trang ban đầu ở tầng ứng dụng nếu cần.

## 16. JOIN FETCH: khác JOIN thông thường

Hai câu này không có cùng ý nghĩa fetch:

```jpql
select o
from SalesOrder o
join o.customer c
where c.email = :email
```

```jpql
select o
from SalesOrder o
join fetch o.customer
where o.orderNumber = :number
```

**JOIN** dùng relationship trong phép lọc hoặc tạo biến liên kết; nó không bắt buộc phải khởi tạo association trong graph kết quả như fetch join.

**JOIN FETCH** yêu cầu dữ liệu association được tải cùng với entity owner trong fetch plan của query. Với `SalesOrder.customer` là LAZY, fetch join có thể tránh một lần tải association sau này khi use case cần Customer.

### 16.1. Fetch join cho collection

```jpql
select distinct o
from SalesOrder o
left join fetch o.lines
where o.id = :orderId
```

Một SalesOrder có nhiều OrderLine có thể tạo nhiều SQL rows. Provider phải dựng lại object graph và identity, trong khi chi phí dữ liệu có thể lớn.

Cần lưu ý:

- Không fetch join mọi association chỉ vì “muốn tránh LAZY”.
- Với collection lớn, có thể gây row multiplication và tải dữ liệu thừa.
- Fetch join nhiều collections có thể tạo tích Descartes trong SQL hoặc bị provider hạn chế.
- Collection fetch join và pagination cần được xử lý cẩn trọng.
- Không gán alias cho fetch join như một identification variable dùng trong filter theo cách không portable; nếu cần lọc collection, hãy tổ chức join truy vấn/fetch plan thích hợp.

### 16.2. JPQL không tránh N+1 một cách tự động

Ví dụ:

```java
List<SalesOrder> orders = em.createQuery(
    "select o from SalesOrder o",
    SalesOrder.class
).getResultList();

for (SalesOrder o : orders) {
    System.out.println(o.getCustomer().getCustomerName());
}
```

Nếu Customer LAZY chưa được tải và mỗi order trỏ tới Customer khác, các truy cập có thể dẫn tới nhiều SELECT bổ sung. Đây là hiện tượng **N+1**.

Các hướng xử lý:

- `JOIN FETCH` cho những association thực sự cần.
- Entity graph để khai báo fetch plan.
- DTO projection chỉ lấy `c.customerName` mà không cần materialize cả graph.
- Batch fetching/subselect fetching khi provider hỗ trợ và phù hợp.

Đổi JPQL thành SQL native không phải giải pháp tự động cho mọi N+1; cần thiết kế query theo dữ liệu thực sự cần.

## 17. UPDATE và DELETE trong JPQL vẫn dùng entity/attribute

JPQL không chỉ có SELECT. Nó còn có bulk UPDATE và DELETE theo entity mapping.

### 17.1. Bulk UPDATE

```jpql
update SalesOrder o
set o.status = :newStatus
where o.status = :oldStatus
  and o.placedAt < :cutoff
```

Java:

```java
int changed = em.createQuery(
    """
    update SalesOrder o
    set o.status = :newStatus
    where o.status = :oldStatus
      and o.placedAt < :cutoff
    """
)
.setParameter("newStatus", OrderStatus.CANCELLED)
.setParameter("oldStatus", OrderStatus.NEW)
.setParameter("cutoff", cutoff)
.executeUpdate();
```

`executeUpdate()` trả số entity instances/rows bị tác động theo hợp đồng JPA, không phải các entity managed đã được cập nhật trong heap.

### 17.2. Bulk DELETE

```jpql
delete from SalesOrder o
where o.status = :status
  and o.placedAt < :cutoff
```

Không viết:

```sql
DELETE FROM sales_order
WHERE order_status = ?;
```

trong `createQuery`. SQL trên chỉ dùng ở `createNativeQuery`/JDBC.

### 17.3. Cảnh báo đặc biệt với bulk DML

Bulk UPDATE/DELETE:

- Hoạt động trực tiếp qua SQL tương ứng, **không đi qua dirty checking thông thường của từng managed entity**.
- Không tự đồng bộ những entity đã được load trong persistence context.
- Không tự kích hoạt các entity lifecycle callbacks theo từng row như các thao tác entity-level thông thường.
- Không tự cập nhật optimistic version theo mọi quy tắc giống update từng entity; cần kiểm soát `@Version`/concurrency rõ ràng.
- Có giới hạn về association joins và ngữ nghĩa bulk DML; không giả định cú pháp SELECT JOIN áp dụng nguyên xi cho UPDATE/DELETE.
- Có thể đụng FK và cascade DB; entity cascade JPA không được áp dụng như vòng lặp `em.remove(entity)`.

Nếu context đang chứa các SalesOrder có status cũ, sau bulk update chúng có thể **stale**. Cân nhắc flush các thay đổi cần lưu trước bulk operation, rồi clear/refresh hoặc dùng transaction/context khác phù hợp. `clear` sẽ detach toàn bộ managed entities và có thể làm mất pending changes chưa flush.

Bulk JPQL không phải cách đơn giản để “đổi tên cột SQL”; nó vẫn dùng entity/attribute và có hệ quả lifecycle riêng.

## 18. Named Query: đặt JPQL cạnh mô hình entity

JPA hỗ trợ định nghĩa named query:

```java
@Entity(name = "SalesOrder")
@Table(name = "sales_order")
@NamedQuery(
    name = "SalesOrder.findByStatus",
    query = """
        select o
        from SalesOrder o
        where o.status = :status
        order by o.placedAt desc
        """
)
public class SalesOrder {
    // Các persistent attributes đã trình bày.
}
```

Dùng:

```java
List<SalesOrder> orders = em.createNamedQuery(
    "SalesOrder.findByStatus",
    SalesOrder.class
)
.setParameter("status", OrderStatus.PAID)
.getResultList();
```

Ưu điểm:

- Đặt tên truy vấn phục vụ use case.
- Có thể được provider phân tích/kiểm tra sớm hơn tùy cấu hình.
- Không phải lặp nhiều chuỗi query ở khắp code.

Nhược điểm:

- Chuỗi JPQL vẫn cần cập nhật khi refactor tên entity/attribute.
- Query động nhiều bộ lọc có thể khó biểu diễn bằng một named query cố định.

Named query không phải SQL stored procedure và không thay đổi quy tắc **entity name/attribute**.

## 19. JPQL và Criteria API cùng dựa trên mô hình entity

Khi truy vấn có nhiều điều kiện tùy chọn, chuỗi JPQL có thể dài. JPA có Criteria API:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<SalesOrder> cq =
    cb.createQuery(SalesOrder.class);

Root<SalesOrder> root = cq.from(SalesOrder.class);

cq.select(root)
  .where(cb.equal(root.get("status"), OrderStatus.PAID));

List<SalesOrder> results =
    em.createQuery(cq).getResultList();
```

Ở đây `root.get("status")` cũng tham chiếu **persistent attribute** `status`, không phải SQL column `order_status`.

Có thể dùng static metamodel (nếu được generate) để giảm lỗi string khi refactor:

```java
root.get(SalesOrder_.status)
```

`SalesOrder_` là metamodel class do công cụ build/annotation processing tạo ra theo cấu hình dự án, không phải class JPA tự xuất hiện nếu chưa bật generator.

Criteria API và JPQL khác cách diễn đạt, nhưng đều truy vấn **JPA entity model**. Không cần đổi sang native SQL chỉ vì muốn query động.

## 20. Khi nào thật sự cần native SQL?

JPQL phù hợp với rất nhiều truy vấn CRUD, association, lọc/sắp xếp, aggregate và DTO. Nhưng đôi khi cần tính năng database-specific như:

- Window functions đặc thù hoặc truy vấn analytic phức tạp chưa có JPQL portable tương ứng.
- Recursive CTE/hierarchical query tùy DB và phiên bản Jakarta Persistence/provider.
- Hint/chức năng tối ưu riêng của database.
- Query qua bảng chưa ánh xạ thành entity, view hoặc cấu trúc đặc biệt.
- Cú pháp upsert như `ON CONFLICT`/`MERGE` database-specific.
- Một số JSON/array/spatial operations hoặc function đặc thù.
- Bulk data transformation nằm ngoài khả năng JPQL chuẩn.

Khi đó dùng `createNativeQuery`:

```java
List<?> rows = em.createNativeQuery(
    """
    SELECT id, order_no, total_amount
    FROM sales_order
    WHERE order_status = :status
    """
)
.setParameter("status", "PAID")
.getResultList();
```

Trong **native SQL** ở ví dụ này, tên bảng/cột vật lý là đúng vì không còn viết JPQL.

Nếu muốn hydrate entity từ native SQL:

```java
List<SalesOrder> orders = em.createNativeQuery(
    "SELECT * FROM sales_order WHERE order_status = :status",
    SalesOrder.class
)
.setParameter("status", "PAID")
.getResultList();
```

Một số vấn đề cần chú ý:

- Tên bảng/cột và SQL dialect có thể khiến truy vấn kém portable.
- SQL trả về phải có columns đủ để hydrate mapping entity đúng theo yêu cầu provider.
- Association, inheritance, embedded ID và alias phức tạp có thể cần `@SqlResultSetMapping` hoặc mapping chuyên biệt.
- Không dùng parameter binding để thay tên bảng/cột SQL tùy ý.
- Hợp đồng tham số trong native SQL và khả năng bind named parameters có thể có khác biệt portable giữa provider; dùng API phù hợp với môi trường đã chọn.

**Quy tắc:** Khi viết JPQL, dùng entity/attribute. Khi viết native SQL, dùng bảng/cột. Trộn hai mô hình là nguyên nhân của nhiều lỗi query.

## 21. Các lỗi thường gặp và cách đọc thông báo lỗi

### 21.1. Query bảng SQL trong JPQL

```jpql
-- Sai nếu sales_order chỉ là table name:
select o from sales_order o
```

Sửa:

```jpql
select o from SalesOrder o
```

Lỗi có thể được provider diễn đạt như “unknown entity”, “not mapped” hoặc “could not resolve root entity”.

### 21.2. Dùng tên cột thay Java attribute

```jpql
-- Sai nếu entity có field orderNumber:
select o from SalesOrder o
where o.order_no = :number
```

Sửa:

```jpql
select o from SalesOrder o
where o.orderNumber = :number
```

Thông báo thường liên quan “could not resolve attribute/path”.

### 21.3. Quên alias hoặc dùng nhầm alias

```jpql
-- Sai: x chưa được định nghĩa:
select x from SalesOrder o
```

Sửa:

```jpql
select o from SalesOrder o
```

### 21.4. Dùng SQL SELECT *

```jpql
-- Không phải JPQL:
select * from SalesOrder o
```

Sửa:

```jpql
select o from SalesOrder o
```

### 21.5. Join theo khóa ngoại SQL

```jpql
-- Không phải cách diễn đạt association của JPQL:
select o
from SalesOrder o
join crm_customer c on o.customer_id = c.customer_id
```

Sửa:

```jpql
select o
from SalesOrder o
join o.customer c
```

### 21.6. Đi xuyên collection không join

```jpql
-- Sai:
where o.lines.productSku = :sku
```

Sửa:

```jpql
join o.lines i
where i.productSku = :sku
```

### 21.7. So sánh với null bằng dấu bằng

```jpql
-- Sai ý nghĩa:
where o.shippedAt = null
```

Sửa:

```jpql
where o.shippedAt is null
```

### 21.8. Tên enum hoặc kiểu tham số không đúng

```java
query.setParameter("status", "PAID");
```

Nếu persistent attribute `status` là `OrderStatus` enum, việc bind String có thể gây type mismatch hoặc hành vi provider-specific. Ưu tiên:

```java
query.setParameter("status", OrderStatus.PAID);
```

Không tự suy ra vì DB lưu enum thành VARCHAR mà JPQL parameter phải là String. **JPQL xử lý kiểu Java theo mapping**, không kiểu cột vật lý trực tiếp.

### 21.9. Tên property sai chữ hoa/thường

```jpql
-- Không đúng nếu field tên placedAt:
order by o.placed_at
```

Sửa:

```jpql
order by o.placedAt
```

### 21.10. Lấy DTO nhưng khai báo result type là entity

```java
em.createQuery(
    "select o.orderNumber from SalesOrder o",
    SalesOrder.class
);
```

Result expression là `String`, không phải `SalesOrder`. Sửa kiểu query thành `String.class` hoặc sửa `select o` để trả entity.

### 21.11. Quên tham số

```jpql
where o.status = :status
```

Nếu chưa `setParameter("status", ...)`, provider thường báo parameter chưa được bind. Kiểm tra tên parameter và tất cả nhánh dựng truy vấn động.

### 21.12. Gặp N+1 dù đã dùng JPQL

`select o from SalesOrder o` chỉ nói muốn lấy entity order, không bảo đảm tải trước Customer hoặc lines. Chọn fetch plan theo use case, không thay mọi association thành EAGER.

### 21.13. Bulk update xong entity cũ không đổi trong memory

Bulk JPQL cập nhật database mà không cập nhật instance managed đã có. Cần ranh giới context rõ và refresh/clear phù hợp.

### 21.14. Query dùng ID cột mà không có persistent field

`o.customer_id` chỉ hợp lệ nếu thật sự có persistent attribute Java tên `customer_id` (rất ít khi mong muốn); thông thường dùng `o.customer.id` hoặc `o.customer = :customer`.

## 22. Một số lựa chọn thiết kế để JPQL dễ bảo trì

### 22.1. Đặt tên persistent attributes có ý nghĩa

Thay vì dùng tên field gần với SQL schema:

```java
private String order_no;
```

nên ưu tiên Java convention:

```java
@Column(name = "order_no")
private String orderNumber;
```

Lợi ích:

- JPQL theo tên nghiệp vụ rõ ràng.
- Code Java dễ đọc và refactor.
- DB migration có thể độc lập hơn với tên Java.
- Getter, DTO và service thể hiện ý nghĩa thay vì cấu trúc vật lý.

### 22.2. Ánh xạ association, đừng bắt mọi service nhớ FK

Nếu SalesOrder thực sự có quan hệ tới Customer, mapping:

```java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
```

cho phép query `o.customer.email`. Nếu chỉ lưu `Long customerId` và không mapping relationship, JPQL không thể tự đi `o.customer.email`; service phải dùng hai query hoặc join theo mô hình được hỗ trợ.

Không phải mọi FK đều bắt buộc biến thành association. Nhưng nếu application cần thường xuyên điều hướng nghiệp vụ giữa entity, mapping association giúp JPQL biểu đạt đúng domain model.

### 22.3. Không lạm dụng entity graph lớn

Dù JPQL giúp đi qua association, query fetch quá nhiều collection có thể gây Cartesian row explosion, memory pressure và pagination không ổn định.

Khi chỉ cần danh sách order gồm mã, tên khách và tổng tiền, DTO projection thường phù hợp hơn:

```jpql
select new com.example.shop.readmodel.OrderSummary(
    o.id, o.orderNumber, c.customerName, o.totalAmount
)
from SalesOrder o
join o.customer c
```

### 22.4. Đặt query gần nơi sử dụng và kiểm thử

Nếu JPQL nằm trong repository/service, cần integration test thực sự với metadata JPA và schema tương ứng. Khi đổi tên persistent attribute, query string có thể không được trình biên dịch Java phát hiện lỗi. Named query, Criteria metamodel hoặc công cụ kiểm tra query có thể giảm rủi ro.

Không coi một chuỗi JPQL có compile Java thành công là chứng minh query hợp lệ.

### 22.5. Chú ý quyền truy cập dữ liệu

JPQL chỉ tìm entity theo điều kiện được viết. Nó **không tự thêm bộ lọc tenant, ownership hay authorization** trừ khi ứng dụng/provider có cơ chế rõ ràng.

Ví dụ chỉ lấy order của customer mà user có quyền:

```jpql
select o
from SalesOrder o
where o.customer.id = :authorizedCustomerId
  and o.id = :orderId
```

Service phải xác định `authorizedCustomerId` từ authentication/authorization context tin cậy, không nhận tùy ý từ client. Multi-tenancy và soft delete cũng cần được thiết kế ở mapping/query hoặc policy theo yêu cầu.

## 23. Minh họa chuyển từ SQL quen thuộc sang JPQL

### Trường hợp A: Lấy tất cả đơn hàng

SQL:

```sql
SELECT * FROM sales_order;
```

JPQL:

```jpql
select o from SalesOrder o
```

### Trường hợp B: Đơn hàng theo mã

SQL:

```sql
SELECT * FROM sales_order WHERE order_no = ?;
```

JPQL:

```jpql
select o from SalesOrder o
where o.orderNumber = :orderNumber
```

### Trường hợp C: Lọc theo tên khách hàng

SQL:

```sql
SELECT o.*
FROM sales_order o
JOIN crm_customer c ON c.customer_id = o.customer_id
WHERE c.display_name = ?;
```

JPQL:

```jpql
select o
from SalesOrder o
join o.customer c
where c.customerName = :name
```

Hoặc:

```jpql
select o
from SalesOrder o
where o.customer.customerName = :name
```

### Trường hợp D: Lấy đơn chứa SKU

SQL:

```sql
SELECT DISTINCT o.*
FROM sales_order o
JOIN sales_order_line i ON i.order_id = o.id
WHERE i.sku = ?;
```

JPQL:

```jpql
select distinct o
from SalesOrder o
join o.lines i
where i.productSku = :sku
```

### Trường hợp E: Khách hàng chưa có đơn

SQL:

```sql
SELECT c.*
FROM crm_customer c
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_order o
    WHERE o.customer_id = c.customer_id
);
```

JPQL:

```jpql
select c
from Customer c
where c.orders is empty
```

### Trường hợp F: Đếm đơn theo khách

SQL:

```sql
SELECT c.customer_id, COUNT(o.id)
FROM crm_customer c
LEFT JOIN sales_order o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

JPQL:

```jpql
select c.id, count(o)
from Customer c
left join c.orders o
group by c.id
```

### Trường hợp G: Cập nhật trạng thái

SQL:

```sql
UPDATE sales_order
SET order_status = ?
WHERE id = ?;
```

JPQL bulk update:

```jpql
update SalesOrder o
set o.status = :status
where o.id = :id
```

Nhớ rằng bulk JPQL không hoạt động như gọi setter trên entity managed; phải cân nhắc persistence context và version.

## 24. Bài tập thực hành

### Bài 1: Viết JPQL theo tên entity

Có:

```java
@Entity(name = "InventoryItem")
@Table(name = "inv_item")
class ProductItem {
    @Id Long id;
}
```

**Yêu cầu:** Viết JPQL lấy tất cả entity.

**Gợi ý đáp án:**

```jpql
select i from InventoryItem i
```

Không dùng `inv_item` và cũng không tự động dùng `ProductItem` vì entity name đã được override.

### Bài 2: Tên field khác tên cột

```java
@Column(name = "product_sku")
private String sku;
```

**Yêu cầu:** Viết WHERE để lọc SKU.

**Gợi ý đáp án:**

```jpql
where i.sku = :sku
```

Không viết `i.product_sku` nếu không có persistent attribute tên đó.

### Bài 3: Một association ManyToOne

SalesOrder có `Customer customer`, Customer có `String email`.

**Yêu cầu:** Lấy tất cả order của email đã biết.

**Gợi ý đáp án:**

```jpql
select o
from SalesOrder o
join o.customer c
where c.email = :email
```

Hoặc `where o.customer.email = :email` theo path expression.

### Bài 4: Truy vấn collection-valued association

SalesOrder có `List<OrderLine> lines`, OrderLine có `String productSku`.

**Yêu cầu:** Lấy order chứa `productSku` cho trước.

**Gợi ý đáp án:**

```jpql
select distinct o
from SalesOrder o
join o.lines i
where i.productSku = :sku
```

Không viết `o.lines.productSku`.

### Bài 5: Bind enum

`SalesOrder.status` là enum `OrderStatus`.

**Yêu cầu:** Query chỉ lấy order PAID.

**Gợi ý đáp án:**

```java
em.createQuery(
    """
    select o from SalesOrder o
    where o.status = :status
    """,
    SalesOrder.class
)
.setParameter("status", OrderStatus.PAID)
.getResultList();
```

Không cần biến enum thành String chỉ vì DB lưu nó bằng VARCHAR.

### Bài 6: Đếm số order

**Yêu cầu:** Đếm đơn NEW.

**Gợi ý đáp án:**

```jpql
select count(o)
from SalesOrder o
where o.status = :status
```

Trong Java nhận `Long` rồi bind `OrderStatus.NEW`.

### Bài 7: DTO projection

Cần lấy `orderNumber` và `totalAmount`, không cần entity SalesOrder managed.

**Gợi ý:** Tạo DTO/record có constructor tương ứng và dùng:

```jpql
select new com.example.shop.readmodel.OrderAmount(
    o.orderNumber, o.totalAmount
)
from SalesOrder o
```

DTO đó không tham gia dirty checking.

### Bài 8: Phân trang 20 đơn mới nhất

**Yêu cầu:** Lấy 20 đơn đầu tiên theo `placedAt desc`; nếu cùng thời điểm thì ID giảm dần.

**Gợi ý đáp án:**

```java
em.createQuery(
    """
    select o from SalesOrder o
    order by o.placedAt desc, o.id desc
    """,
    SalesOrder.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

Không dùng SQL `LIMIT 20` trực tiếp trong JPQL chuẩn.

### Bài 9: Tìm khách không có order

**Gợi ý đáp án:**

```jpql
select c from Customer c
where c.orders is empty
```

Hoặc dùng `NOT EXISTS` tương ứng.

### Bài 10: Phân biệt JOIN và JOIN FETCH

**Câu hỏi:** `join o.customer c` có chắc khởi tạo Customer association trong graph trả về như `join fetch o.customer` không?

**Gợi ý:** Không. JOIN dùng để liên kết/filter; JOIN FETCH yêu cầu tải association cùng owner theo fetch plan, nhưng cần cân nhắc số row và pagination.

### Bài 11: getSingleResult

Query theo `email` không có kết quả.

**Câu hỏi:** `getSingleResult()` có trả `null` không?

**Gợi ý:** Theo ngữ nghĩa JPA thông thường, nó ném `NoResultException`. Nếu nhiều kết quả, `NonUniqueResultException`. Có thể dùng `getResultList` và xử lý rỗng rõ ràng.

### Bài 12: Lọc trường nullable

Entity có `shippedAt` nullable.

**Yêu cầu:** Lấy order chưa giao.

**Gợi ý đáp án:**

```jpql
select o from SalesOrder o
where o.shippedAt is null
```

Không dùng `= null`.

### Bài 13: Refactor Java attribute

Đổi `orderNumber` thành `number` trong entity, vẫn ánh xạ cột `order_no`.

**Câu hỏi:** JPQL `o.orderNumber` còn hợp lệ không?

**Gợi ý:** Không, nếu thuộc tính đó không còn persistent. Sửa JPQL thành `o.number`; tên cột SQL không quyết định tên path JPQL.

### Bài 14: Bulk update và first-level cache

`Customer` đã load một SalesOrder trong EntityManager. Sau đó chạy bulk JPQL update đổi status.

**Câu hỏi:** Đối tượng SalesOrder trong memory có tự đổi status không?

**Gợi ý:** Không được bảo đảm. Bulk DML không tự đồng bộ managed instances; cần refresh/clear hoặc context mới phù hợp.

### Bài 15: Native SQL hay JPQL?

Có truy vấn:

```sql
SELECT id, order_no FROM sales_order;
```

**Câu hỏi:** Đưa nguyên chuỗi vào `em.createQuery(...)` được không?

**Gợi ý:** Không. `createQuery` nhận JPQL; muốn SQL này dùng `createNativeQuery`, hoặc viết JPQL `select o.id, o.orderNumber from SalesOrder o`.

### Bài 16: Rủi ro injection ở ORDER BY

Client gửi `sortBy="placedAt desc; delete ..."`, code nối thẳng vào query.

**Câu hỏi:** Có thể bind `:sortBy` để thay tên trường không?

**Gợi ý:** Parameter binding dành cho value, không phải identifier/expression syntax. Dùng whitelist các trường hợp cho phép và ghép từ chuỗi cố định đáng tin.

### Bài 17: Kết quả duplicate do join

Một order có 5 lines; query:

```jpql
select o from SalesOrder o join o.lines i
```

**Câu hỏi:** Vì sao kết quả có thể có nhiều dòng cho cùng Order?

**Gợi ý:** Mỗi phần tử collection tạo một joined row; dùng `DISTINCT` khi chỉ cần order duy nhất hoặc `EXISTS` khi chỉ cần kiểm tra có ít nhất một line.

### Bài 18: Query không biết customerId field

SalesOrder có `Customer customer` nhưng không có `Long customerId`.

**Yêu cầu:** Lọc theo Customer ID.

**Gợi ý đáp án:**

```jpql
select o from SalesOrder o
where o.customer.id = :customerId
```

Hoặc bind Customer entity với `where o.customer = :customer`.

## 25. Bảng tra cứu nhanh JPQL cơ bản

| Nhu cầu | JPQL tiêu biểu |
|---|---|
| Lấy toàn bộ entity | `select o from SalesOrder o` |
| Lọc thuộc tính | `where o.orderNumber = :number` |
| Lọc enum | `where o.status = :status` |
| Lọc thời gian | `where o.placedAt >= :fromTime` |
| Lọc null | `where o.shippedAt is null` |
| LIKE | `where lower(c.customerName) like :pattern` |
| Tìm nhiều giá trị | `where o.status in :statuses` |
| Đi qua ManyToOne | `where o.customer.email = :email` |
| Join Customer | `join o.customer c` |
| Join OrderLine | `join o.lines i` |
| Join giữ cả phía không có phần tử | `left join c.orders o` |
| Collection trống | `where c.orders is empty` |
| Kiểm tra liên quan tồn tại | `where exists (select ... )` |
| Trả kết quả duy nhất | `select distinct o ...` |
| Đếm | `select count(o) from SalesOrder o` |
| Nhóm | `group by o.status` |
| Điều kiện trên nhóm | `having count(o) >= :min` |
| Trả DTO | `select new com.example.dto.X(...) ...` |
| Sắp xếp | `order by o.placedAt desc` |
| Tải association | `join fetch o.customer` |
| Bulk update | `update SalesOrder o set o.status = :status ...` |
| Bulk delete | `delete from SalesOrder o where ...` |

## 26. Ghi nhớ cốt lõi

1. **JPQL truy vấn entity và persistent attributes**, không trực tiếp dùng tên bảng/cột SQL.
2. Trong `FROM`, dùng **entity name** của `@Entity` (mặc định là tên class không package nếu không override), ví dụ `SalesOrder`; không dùng `@Table(name = "sales_order")`.
3. Trong `WHERE`, `SELECT` và `ORDER BY`, dùng **tên thuộc tính Java** như `o.orderNumber`; không dùng `order_no` chỉ vì `@Column` ánh xạ như vậy.
4. **JPQL JOIN đi qua association** như `join o.customer c` hay `join o.lines i`; provider biết FK nhờ `@JoinColumn`/`mappedBy`.
5. **Path expression** như `o.customer.customerName` diễn đạt điều hướng trong entity graph; với collection `o.lines`, hãy JOIN để lấy biến phần tử.
6. **Parameter binding** (`:status`, `:id`) dành cho giá trị, giảm lỗi kiểu và injection; không dùng để thay tên field/table động.
7. **SELECT entity** trả managed entities theo persistence context; **SELECT scalar/DTO** không biến các giá trị kết quả thành managed entity.
8. **DISTINCT, GROUP BY, EXISTS, IS EMPTY** giúp diễn đạt yêu cầu theo association mà không phải viết lại FK trong JPQL.
9. **ORDER BY, pagination và fetch plan** phải thiết kế theo lượng dữ liệu thực tế; JOIN FETCH collection có thể nhân bản SQL rows và gây khó với pagination.
10. **Bulk UPDATE/DELETE** cũng dùng entity/attributes, nhưng bypass nhiều cơ chế entity-level thông thường và có thể khiến persistence context stale.
11. Khi cần cú pháp bảng/cột hay tính năng SQL đặc thù DB, dùng **native SQL** một cách có chủ đích qua `createNativeQuery`, không trộn vào `createQuery`.
12. Tên JPQL phụ thuộc metadata mapping và tên property trong Java; **refactor entity attributes cần rà soát query strings**, dù DB schema giữ nguyên.

**Kết luận:** Sự khác biệt nền tảng của JPQL là **“truy vấn đối tượng theo mô hình JPA” thay vì “truy vấn bảng theo schema SQL”**. Một câu `select o from SalesOrder o where o.customer.email = :email` mô tả entity `SalesOrder`, association `customer` và thuộc tính `email`; provider sẽ tìm đúng bảng, cột và khóa ngoại đã được cấu hình trong mapping. Khi quen cách tư duy theo entity/attribute, bạn có thể viết JPQL rõ ràng, dễ bảo trì, tận dụng quan hệ JPA và giảm sự phụ thuộc trực tiếp vào cấu trúc vật lý của cơ sở dữ liệu.
