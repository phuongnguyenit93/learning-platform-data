# Tách truy vấn đếm và truy vấn lấy nội dung trang

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** DTO và phân trang

Khi xây API danh sách, ứng dụng thường cần trả về một nhóm bản ghi theo thứ tự nhất định, ví dụ 20 đơn hàng mới nhất. Một số giao diện còn cần thông tin “có tất cả bao nhiêu đơn hàng?”, “có bao nhiêu trang?”, hoặc “đang ở trang mấy?”. Hai nhu cầu này dẫn đến **hai loại truy vấn có mục tiêu khác nhau**:

1. **Truy vấn lấy nội dung trang** (*content/data query*): chọn đúng các bản ghi và cột cần hiển thị, áp dụng bộ lọc, sắp xếp và giới hạn số hàng theo trang.
2. **Truy vấn đếm** (*count query*): tính số **phần tử logic** thỏa cùng điều kiện, nhưng không cần trả chi tiết từng phần tử, không cần sắp xếp và thường không cần các JOIN chỉ phục vụ hiển thị.

Tách hai truy vấn giúp ứng dụng kiểm soát rõ ngữ nghĩa phân trang, tối ưu từng mục đích và tránh các sai lầm rất thường gặp như đếm số dòng sau `JOIN` thay vì số entity gốc, dùng `FETCH JOIN` trong count query, đếm không khớp bộ lọc của trang, hoặc thực hiện một phép `COUNT` quá tốn kém khi giao diện chỉ cần biết “còn trang tiếp theo không?”.

Điểm cần ghi nhớ từ đầu: **hai câu query không cần giống hệt nhau về cú pháp, nhưng phải nhất quán về ý nghĩa của tập phần tử được đếm và được hiển thị.** Nếu nội dung trang đại diện mỗi dòng là một đơn hàng, tổng số phần tử cũng phải là số **đơn hàng**, không phải số dòng đơn, số khách hàng hoặc số tổ hợp JOIN.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích trách nhiệm riêng của content query và count query trong một API phân trang.
2. Thiết kế hai query cùng bộ lọc nhưng khác `SELECT`, `ORDER BY`, `FETCH` và pagination.
3. Hiểu quan hệ giữa `pageIndex`, `pageSize`, `totalElements` và `totalPages`.
4. Dùng `TypedQuery.setFirstResult()`/`setMaxResults()` để lấy nội dung trang và `COUNT` để tính tổng.
5. Dùng DTO projection chỉ lấy những giá trị cần thiết trong content query.
6. Phân biệt `COUNT(o)`, `COUNT(l)` và `COUNT(DISTINCT o.id)` khi có JOIN to-many.
7. Dùng `EXISTS` để lọc root theo child mà không nhân số root result rows.
8. Biết vì sao count query không nên giữ `ORDER BY` hay `JOIN FETCH` của content query.
9. Xử lý count query khi content query có `GROUP BY` hoặc `HAVING`.
10. Khai báo `@Query(value=..., countQuery=...)` trong Spring Data JPA.
11. Phân biệt `Page<T>`, `Slice<T>` và `List<T>` về nhu cầu đếm.
12. Viết chiến lược page IDs rồi fetch graph khi cần collection của entity gốc.
13. Đánh giá chi phí `COUNT`, lựa chọn bỏ hoặc trì hoãn count khi không cần thiết.
14. Nhận diện ảnh hưởng của cập nhật đồng thời và transaction isolation lên tổng đếm.
15. Sắp xếp ổn định bằng khóa phụ duy nhất và nhận biết giới hạn của offset pagination.
16. Viết kiểm thử bảo đảm tổng đếm khớp đúng dữ liệu sau filter và JOIN.

## 2. Định nghĩa một “phần tử trang” trước khi viết SQL

Trước khi bàn đến `COUNT`, cần trả lời: **Một phần tử trong kết quả trang đại diện điều gì?**

Xét quan hệ:

```text
Customer 1 -------- N PurchaseOrder
PurchaseOrder 1 --- N OrderLine
```

Một API có thể trả:

- **Order list:** mỗi phần tử là một `PurchaseOrder`.
- **Order line list:** mỗi phần tử là một `OrderLine`.
- **Customer summary:** mỗi phần tử là một `Customer`, kèm số đơn của khách.
- **Order–SKU tuple:** mỗi phần tử là một cặp `(Order, SKU)`.
- **Monthly report:** mỗi phần tử là một nhóm theo tháng.

Với `JOIN`, số dòng SQL có thể lớn hơn số Order. Ví dụ:

```text
Order#1001:
  Line#501
  Line#502
  Line#503

JOIN Order + Line:
  (1001,501)
  (1001,502)
  (1001,503)
```

Một Order tạo ba dòng JOIN nhưng chỉ là **một phần tử** nếu API hiển thị danh sách Orders. Ngược lại, nếu API hiển thị từng Line, ba dòng có thể là ba phần tử hợp lệ.

### 2.1. Content và count phải dùng cùng hạt dữ liệu

| Loại danh sách | Một phần tử content | Đếm đúng |
|---|---|---|
| Danh sách Order | Một Order | Số Order thỏa filter |
| Danh sách Line | Một Line | Số Line thỏa filter |
| Danh sách Customer | Một Customer | Số Customer thỏa filter |
| Danh sách SKU theo Order | Một cặp Order/SKU | Số cặp duy nhất theo projection |
| Báo cáo theo tháng | Một nhóm tháng | Số nhóm tháng |
| Báo cáo theo Order và trạng thái | Một nhóm (Order, status) | Số nhóm tương ứng |

**Tách query** không có nghĩa chỉ đổi `SELECT o` thành `SELECT COUNT(o)` một cách máy móc. Đó là một bước **thiết kế hợp đồng dữ liệu**, đặc biệt khi có JOIN và aggregation.

## 3. Kết quả Page có những gì?

Một trang điển hình gồm:

```json
{
  "content": [
    {"id": 1005, "orderNumber": "ORD-1005"},
    {"id": 1004, "orderNumber": "ORD-1004"}
  ],
  "pageIndex": 0,
  "pageSize": 2,
  "totalElements": 5,
  "totalPages": 3,
  "hasNext": true
}
```

Ý nghĩa:

- `content`: những phần tử thực tế trong trang.
- `pageIndex`: số trang, thường bắt đầu từ 0 ở API lập trình.
- `pageSize`: số phần tử tối đa được yêu cầu mỗi trang.
- `totalElements`: tổng số phần tử **thỏa filter**, không chỉ số phần tử trong trang hiện tại.
- `totalPages`: số trang cần để duyệt tất cả phần tử với page size đã chọn.
- `hasNext`: có trang tiếp theo hay không theo metadata hiện tại.

Với `totalElements=5` và `pageSize=2`:

```text
Page 0: 2 phần tử
Page 1: 2 phần tử
Page 2: 1 phần tử

totalPages = ceil(5 / 2) = 3
```

### 3.1. Công thức phân trang

Với page index bắt đầu từ 0:

```text
offset = pageIndex * pageSize
limit  = pageSize
```

Ví dụ page 2 size 20:

```text
offset = 2 * 20 = 40
limit  = 20
```

Nếu tổng là 0, tổng số trang thường là 0 theo convention phổ biến. Nếu tổng là 41 và size 20, có 3 trang.

### 3.2. Tính totalPages trong Java

```java
public static long totalPages(long totalElements, int pageSize) {
    if (totalElements < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("Invalid pagination");
    }

    if (totalElements == 0) {
        return 0L;
    }

    // Tránh cộng (pageSize - 1) vào totalElements, có thể overflow.
    return 1L + (totalElements - 1L) / pageSize;
}
```

`COUNT` trong JPQL thường trả `Long`. Không nên ép tổng số bản ghi thành `int` khi hệ thống có thể vượt `Integer.MAX_VALUE`.

## 4. Mô hình ví dụ xuyên suốt

Ta xây hệ thống bán hàng đơn giản:

```text
Customer
  id: Long
  displayName: String

PurchaseOrder
  id: Long
  orderNumber: String
  createdAt: LocalDateTime
  status: OrderStatus
  customer: Customer
  lines: List<OrderLine>

OrderLine
  id: Long
  order: PurchaseOrder
  sku: String
  quantity: int
```

### 4.1. Entity Customer

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    protected Customer() {}

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
}
```

### 4.2. Trạng thái Order

```java
package demo.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

### 4.3. Entity PurchaseOrder

```java
package demo.domain;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
            String orderNumber,
            LocalDateTime createdAt,
            OrderStatus status,
            Customer customer) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.createdAt = Objects.requireNonNull(createdAt);
        this.status = Objects.requireNonNull(status);
        this.customer = Objects.requireNonNull(customer);
    }

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public OrderStatus getStatus() { return status; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }
}
```

### 4.4. Entity OrderLine

```java
package demo.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false, length = 60)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(PurchaseOrder order, String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }
        this.order = order;
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
```

Mô hình không bật cascade persist; khi tạo dữ liệu phải lưu Customer và Order rồi lưu Line riêng, hoặc bổ sung cascade theo nghiệp vụ. Việc thiếu cascade không làm thay đổi cách viết các truy vấn đọc trong bài.

### 4.5. Schema minh họa

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    customer_id BIGINT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

DDL minh họa cho hệ quản trị hỗ trợ cú pháp identity tương ứng. Trong production cần migration, indexes, constraint và data type theo DBMS triển khai.

### 4.6. Dữ liệu mẫu

| Order ID | Order number | Status | Customer | Lines |
|---:|---|---|---|---|
| 1001 | ORD-1001 | PAID | An | A-01, A-02, B-01 |
| 1002 | ORD-1002 | NEW | An | B-02 |
| 1003 | ORD-1003 | PAID | Bình | Không có |
| 1004 | ORD-1004 | PAID | Chi | A-03, A-04 |
| 1005 | ORD-1005 | CANCELLED | Chi | C-01 |

Giả sử `createdAt` tăng theo thứ tự ID để dễ quan sát. Với filter status = PAID, ta có **3 Orders**: 1001, 1003 và 1004. Nếu thêm điều kiện có ít nhất một Line SKU A, chỉ còn **2 Orders**: 1001 và 1004, dù chúng có **4 Lines SKU A**.

---

## 5. Truy vấn nội dung trang tối giản

Yêu cầu: lấy Orders PAID mới nhất, mỗi trang tối đa 2 Orders.

JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :paid
ORDER BY o.createdAt DESC, o.id DESC
```

Java:

```java
int pageIndex = 0;
int pageSize = 2;

List<PurchaseOrder> content = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.status = :paid
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class)
    .setParameter("paid", OrderStatus.PAID)
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize)
    .getResultList();
```

Trong dữ liệu mẫu, page 0 dự kiến có Orders 1004 và 1003; page 1 có Order 1001.

### 5.1. Giới hạn của đoạn code ngắn

`pageIndex * pageSize` được tính bằng `int`. Nếu client gửi những số lớn, phép nhân có thể overflow trước khi gọi JPA. Khi làm ứng dụng thật, validate page size và tính offset bằng `long` trước khi ép sang `int`, như ví dụ service ở phần sau.

### 5.2. Content query tập trung vào gì?

Content query chịu trách nhiệm:

- Chọn đúng entity hoặc DTO.
- Lọc theo business criteria.
- Xác định thứ tự rõ ràng.
- Giới hạn phần tử của trang.
- Đáp ứng fetch plan đủ dùng.
- Tránh nhân root rows ngoài ý muốn.

Nó **không bắt buộc** phải có chức năng tính `totalElements`. Tổng số cần một phép đếm logic riêng.

---

## 6. Truy vấn đếm tối giản

Đếm Orders PAID:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :paid
```

Java:

```java
Long totalElements = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.status = :paid
    """,
    Long.class)
    .setParameter("paid", OrderStatus.PAID)
    .getSingleResult();
```

Với dữ liệu mẫu, `totalElements = 3`.

**Chú ý những khác biệt có chủ đích** so với content query:

| Thành phần | Content query | Count query |
|---|---|---|
| `SELECT` | `o` hoặc DTO fields | `COUNT(o)` |
| `FROM` | Root `PurchaseOrder` | Cùng root |
| `WHERE` | `o.status = :paid` | Giữ cùng điều kiện |
| `ORDER BY` | Có, để định nghĩa trang | Không cần |
| `setFirstResult` | Có | Không |
| `setMaxResults` | Có | Không |
| Fetch association | Theo dữ liệu màn hình cần | Không fetch để hiển thị |
| Giá trị trả | `List<PurchaseOrder>`/DTO | `Long` |

Nếu ai đó sao chép toàn bộ content query và chỉ thay từ khóa SELECT, có thể giữ nhiều JOIN hoặc ORDER BY không cần cho count, gây lãng phí hay lỗi cú pháp.

### 6.1. Vì sao COUNT không cần ORDER BY?

`COUNT` trả về một số. Sắp xếp các Order trước khi đếm không thay đổi kết quả tổng. Trong một số hệ quản trị, `ORDER BY` còn có thể không hợp lệ trong query chỉ trả aggregate scalar, hoặc tạo công việc không cần.

### 6.2. Vì sao COUNT không áp dụng LIMIT/OFFSET?

`totalElements` là số phần tử thỏa filter **trong toàn bộ tập**, không phải số phần tử của trang hiện tại.

Nếu bạn đếm chỉ 20 phần tử được phân trang, `totalElements` sẽ luôn tối đa 20 và `totalPages` sai.

### 6.3. Vì sao COUNT không cần SELECT các thuộc tính DTO?

Để đếm Orders, database không cần trả `orderNumber`, `createdAt` hoặc `customerName` cho Java. Count query có thể ít dữ liệu truyền hơn và kế hoạch thực thi khác với content query.

---

## 7. Tách hai query nhưng giữ cùng bộ lọc

Một hợp đồng trang có hai bất biến:

1. **Content:** chỉ chứa phần tử thuộc tập kết quả theo business filter.
2. **Count:** là kích thước của **cùng tập logic** đó, tại snapshot quan sát tương ứng.

Giả sử content query lọc theo:

```jpql
WHERE o.status = :paid
  AND o.createdAt >= :fromTime
  AND o.customer.id = :customerId
```

Count phải áp dụng **tương đương ba điều kiện**, không được vô tình bỏ một điều kiện.

Sai:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :paid
```

Count này đếm cả đơn của khách khác hoặc trước `fromTime`.

Đúng:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :paid
  AND o.createdAt >= :fromTime
  AND o.customer.id = :customerId
```

### 7.1. Cùng semantics không nhất thiết cùng cú pháp

Ví dụ content query có:

```jpql
JOIN o.customer c
WHERE c.id = :customerId
```

Count có thể biểu đạt tương đương:

```jpql
WHERE o.customer.id = :customerId
```

miễn là semantics đối với optional/null associations, join và bộ lọc đúng như yêu cầu.

Đặc biệt với `LEFT JOIN` hoặc một association nullable, đổi JOIN thành path navigation có thể thay đổi tập kết quả. Không “tối ưu” bằng cách bỏ JOIN mà chưa chứng minh hai query tương đương.

### 7.2. Tenant, soft-delete và phân quyền là bộ lọc bắt buộc

Nếu content query chỉ trả Orders của tenant hiện tại:

```jpql
WHERE o.tenantId = :tenantId
  AND o.deleted = false
```

count query cũng phải tôn trọng cùng logic đó. Không đúng nếu nội dung trang đã lọc theo quyền nhưng count vẫn đếm dữ liệu của tất cả tenants.

Sai khác ở count không chỉ gây lỗi giao diện mà còn có thể **rò rỉ sự tồn tại hoặc quy mô dữ liệu** ngoài quyền.

---

## 8. Một DTO trang cho danh sách đọc

Danh sách thường không cần toàn bộ managed entity. Có thể dùng DTO chỉ chứa cột cần hiển thị.

```java
package demo.dto;

import java.time.LocalDateTime;

public record OrderListRow(
    Long id,
    String orderNumber,
    LocalDateTime createdAt,
    String customerName
) {}
```

Content query:

```jpql
SELECT NEW demo.dto.OrderListRow(
    o.id,
    o.orderNumber,
    o.createdAt,
    c.displayName
)
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.status = :paid
ORDER BY o.createdAt DESC, o.id DESC
```

Java:

```java
List<OrderListRow> rows = em.createQuery(
    """
    SELECT NEW demo.dto.OrderListRow(
        o.id, o.orderNumber, o.createdAt, c.displayName
    )
    FROM PurchaseOrder o
    JOIN o.customer c
    WHERE o.status = :paid
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    OrderListRow.class)
    .setParameter("paid", OrderStatus.PAID)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Count query:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :paid
```

### 8.1. Vì sao COUNT có thể bỏ JOIN Customer?

Trong mô hình hiện tại, `PurchaseOrder.customer` là to-one, `optional=false` và database có FK NOT NULL. Content query JOIN Customer chỉ để lấy `displayName`. Nếu tất cả Orders hợp lệ đều có Customer, JOIN này không ảnh hưởng tập root đủ điều kiện khi chỉ lọc theo `o.status`. Vì vậy count không cần JOIN Customer.

Nếu quan hệ optional và content query dùng INNER JOIN loại Orders thiếu Customer, count bỏ JOIN sẽ **không còn tương đương**. Khi đó cần sửa content thành LEFT JOIN nếu nghiệp vụ muốn giữ Orders không Customer, hoặc giữ điều kiện tồn tại Customer trong count.

### 8.2. DTO constructor phải khớp type

`SELECT NEW` cần class/record có constructor phù hợp các đối số `Long`, `String`, `LocalDateTime`, `String`. Không trộn kiểu từ CASE/aggregate gây mismatch, và không dùng primitive cho field có thể NULL nếu constructor không hỗ trợ.

### 8.3. Count không tạo entity hoặc DTO

Count query không trả managed `PurchaseOrder` hoặc `OrderListRow`. Nó trả giá trị số `Long`. Việc tách giúp tránh load/thực thể hóa những object không cần cho thống kê tổng.

---

## 9. JOIN to-one và JOIN to-many có ảnh hưởng khác nhau

### 9.1. JOIN to-one thường không nhân root

`PurchaseOrder.customer` là `@ManyToOne`: một Order chỉ có một Customer. Query:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.displayName LIKE :namePrefix
```

trong mô hình quan hệ hợp lệ sẽ có tối đa một hàng ghép với một Order (dù có thể loại Order do không match). Vì vậy count thường có thể là:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.displayName LIKE :namePrefix
```

không cần DISTINCT chỉ vì có JOIN to-one.

### 9.2. JOIN to-many có thể nhân root

`PurchaseOrder.lines` là `@OneToMany`. Query:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
```

Nếu Order#1001 có hai Lines A-01, A-02 cùng match, Order#1001 có thể xuất hiện nhiều lần trong query result list (hoặc SQL rows), dù JPA giữ identity của cùng root instance.

### 9.3. Data query DISTINCT root

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
ORDER BY o.createdAt DESC, o.id DESC
```

Khi API muốn một Order một lần, `DISTINCT o` diễn đạt mục tiêu duy nhất root.

Nhưng count phải hiểu hạt dữ liệu đó, không chỉ đếm join rows.

---

## 10. COUNT(DISTINCT) với JOIN to-many

Dữ liệu mẫu:

```text
Order#1001: A-01, A-02, B-01
Order#1004: A-03, A-04
```

Với prefix `A-%`:

```text
JOIN matching rows:
  (Order#1001, A-01)
  (Order#1001, A-02)
  (Order#1004, A-03)
  (Order#1004, A-04)

Số JOIN rows = 4
Số Order gốc = 2
```

Count sai:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
```

Kết quả về mặt logic là 4.

Count đúng theo Orders:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
```

Kết quả là 2.

### 10.1. COUNT(o), COUNT(l), COUNT(DISTINCT o.id)

| Biểu thức | Với JOIN Order–Line | Đếm đơn vị nào? |
|---|---|---|
| `COUNT(o)` | Số dòng JOIN có Order non-null | Có thể lặp root |
| `COUNT(l)` | Số Line non-null trong các dòng JOIN | Số Lines match |
| `COUNT(DISTINCT o.id)` | Số Order IDs duy nhất | Số Orders |
| `COUNT(o)` với EXISTS thay JOIN | Mỗi Order một lần | Số Orders |

Nếu API trả một row cho mỗi Line, đếm Line là đúng; dùng COUNT DISTINCT Order sẽ **đếm sai hạt dữ liệu**. Hãy chọn công thức theo contract của content query.

### 10.2. Với LEFT JOIN cũng có bẫy

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
LEFT JOIN o.lines l
```

Một Order có ba Lines có thể xuất hiện ba lần; Order không có Lines vẫn tạo một dòng có `l` NULL và được `COUNT(o)` đếm. Tổng không phải số Orders.

Tương phản:

```jpql
SELECT COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
```

không đếm Line NULL, nên trả số Lines ghép được, không phải số Orders.

### 10.3. COUNT DISTINCT có thể đắt hơn COUNT thường

Để loại trùng IDs, database có thể cần hash/unique/sort trên nhiều joined rows. Với table lớn, đây có thể là cost đáng kể. Nếu chỉ cần điều kiện tồn tại child, `EXISTS` thường giúp truy vấn rõ nghĩa và tránh join multiplication ở mức logic.

---

## 11. EXISTS: lọc root theo child mà không nhân số dòng gốc

Yêu cầu:

> Lấy mỗi Order đúng một lần nếu nó có **ít nhất một OrderLine** có SKU bắt đầu bằng `A-`.

Content query:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :skuPrefix
)
ORDER BY o.createdAt DESC, o.id DESC
```

Count query:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :skuPrefix
)
```

Ở đây mỗi root `Order` chỉ được xét một lần ở outer query. Một Order có mười Lines match cũng **không nhân root**.

### 11.1. Vì sao EXISTS diễn đạt bài toán đúng hơn?

`EXISTS` trả TRUE nếu subquery có ít nhất một hàng. Với yêu cầu "có bất kỳ Line match", thông tin quan trọng là sự tồn tại, không phải số lượng Lines.

Đối chiếu:

```text
JOIN + DISTINCT:
  tạo tập kết quả ghép theo Lines
  rồi loại duplicate Orders

EXISTS:
  hỏi từng Order có Line phù hợp hay không
  không cần trả một hàng cho mỗi Line
```

Database optimizer có thể biến EXISTS thành semi-join hoặc kế hoạch thực thi khác. Không kết luận EXISTS **luôn** nhanh hơn JOIN DISTINCT trên mọi DBMS. Nhưng nó làm **semantics của bộ lọc** dễ đọc và nhất quán với count.

### 11.2. Dùng cùng predicate cho data và count

Nếu điều kiện là:

```jpql
l.sku LIKE :skuPrefix
AND l.quantity >= :minimumQuantity
```

cả content và count phải áp dụng hai điều kiện trong cùng EXISTs subquery nếu nghiệp vụ yêu cầu một Line đồng thời thỏa cả hai.

Không được viết một query có thêm `quantity`, query kia quên điều kiện này.

### 11.3. NOT EXISTS

Muốn Order không có bất kỳ Line:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE NOT EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
)
ORDER BY o.id
```

Count tương ứng:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE NOT EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
)
```

Không cần JOIN to-many chỉ để biết tập con rỗng.

---

## 12. Không sao chép JOIN FETCH vào count query

Một content query cho màn hình chi tiết có thể dùng:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Trong đó `JOIN FETCH` là yêu cầu tải association của root entity được chọn.

Count query **không được viết theo kiểu**:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

vì `FETCH` có ý nghĩa gắn với việc tải association của entity gốc trong kết quả; còn `COUNT(o)` chỉ trả một số. Đây có thể là query không hợp lệ hoặc dẫn tới provider error.

Count đơn giản nếu không có điều kiện trên Lines:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
```

Count khi lọc root theo Lines:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :skuPrefix
)
```

### 12.1. Fetch plan là trách nhiệm của content, không phải count

Content có thể cần:

- `JOIN FETCH` một association.
- JPA Entity Graph.
- DTO projection.
- Các cột của Customer.
- Dữ liệu child từ query thứ hai.

Count thường chỉ cần xác định **root nào thỏa filter**; không cần materialize những association để hiển thị.

### 12.2. EAGER mapping vẫn có thể ảnh hưởng performance

Static association EAGER có thể khiến query trả entities tải thêm dữ liệu. Một count aggregate scalar thông thường không cần dựng đầy đủ entity graph như content. Do đó tách count giúp tránh chi phí mapping/fetch không liên quan, nhưng chi phí chính của count vẫn có thể là scan/joins/filter của DB.

---

## 13. Collection fetch join cộng pagination: không phải một content query an toàn mặc định

Ví dụ:

```java
List<PurchaseOrder> page = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Một Order có nhiều Lines tạo nhiều SQL rows. Nếu LIMIT/OFFSET áp trực tiếp vào rows, provider có nguy cơ cắt giữa collection của một Order. Các JPA providers có giới hạn/chiến lược khác nhau; Hibernate có thể cảnh báo và áp dụng pagination trong memory hoặc fail-fast theo cấu hình.

**Tách count query thôi chưa đủ** nếu content query vẫn paginate một collection fetch join không an toàn.

### 13.1. Hai vấn đề khác nhau

| Vấn đề | Dấu hiệu | Cách giải quyết |
|---|---|---|
| Count đếm sai do JOIN to-many | totalElements lớn hơn số root | COUNT DISTINCT hoặc EXISTS |
| Content paginate collection fetch join | Trang chậm, SQL nhiều rows, warning/in-memory pagination | Page root IDs rồi fetch graph sau |

Hai lỗi có thể xảy ra cùng lúc. Sửa COUNT DISTINCT không tự sửa việc phân trang collection.

### 13.2. Không nên xem DISTINCT là giải pháp toàn diện

`DISTINCT` có thể loại duplicate root ở kết quả, nhưng không làm các hàng `(Order, Line)` khác nhau trở thành cùng một SQL row khi fetch collection; database/provider vẫn phải xử lý dữ liệu children.

---

## 14. Ba truy vấn khi muốn page root và tải collection đầy đủ

Khi API cần **nội dung root**, **toàn bộ Lines thuộc root trong trang**, và **totalElements**, một thiết kế thường rõ ràng gồm:

1. **Count query:** đếm số roots thỏa filter.
2. **Page IDs query:** lấy đúng root IDs thuộc trang với thứ tự ổn định.
3. **Fetch query:** lấy Orders và Lines theo IDs đó, **không áp dụng pagination trên JOIN FETCH collection**.

Sơ đồ:

```text
FILTER NGHIỆP VỤ
       |
       +-- COUNT(root) hoặc COUNT DISTINCT(root.id)
       |       |
       |       +--> totalElements
       |
       +-- SELECT root.id
               WHERE cùng filter
               ORDER BY ổn định
               LIMIT/OFFSET
                       |
                       +--> pageIds
                               |
                               v
                     SELECT DISTINCT root
                     JOIN FETCH associations
                     WHERE root.id IN :ids
                               |
                               v
                    Khôi phục thứ tự pageIds
                               |
                               v
                         content DTO
```

### 14.1. Page IDs

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :paid
ORDER BY o.createdAt DESC, o.id DESC
```

Java:

```java
List<Long> ids = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.status = :paid
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class)
    .setParameter("paid", OrderStatus.PAID)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
```

Đây là root page query **không nhân rows** vì không JOIN to-many.

### 14.2. Fetch theo IDs

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Java:

```java
List<PurchaseOrder> fetched = ids.isEmpty()
    ? List.of()
    : em.createQuery(
        """
        SELECT DISTINCT o
        FROM PurchaseOrder o
        JOIN FETCH o.customer
        LEFT JOIN FETCH o.lines
        WHERE o.id IN :ids
        """,
        PurchaseOrder.class)
        .setParameter("ids", ids)
        .getResultList();
```

**Không gọi `setFirstResult` hoặc `setMaxResults` trên fetch query này**. Độ lớn tập roots đã được giới hạn qua `ids`.

### 14.3. Khôi phục thứ tự root

`WHERE o.id IN :ids` không bảo đảm kết quả trả đúng thứ tự của Java List `ids`. Có thể dùng:

```java
Map<Long, PurchaseOrder> byId = new HashMap<>();

for (PurchaseOrder order : fetched) {
    byId.put(order.getId(), order);
}

List<PurchaseOrder> ordered = new ArrayList<>();

for (Long id : ids) {
    PurchaseOrder order = byId.get(id);
    if (order != null) {
        ordered.add(order);
    }
}
```

Trong code chạy thật cần import `java.util.Map`, `HashMap`, `List`, `ArrayList`.

### 14.4. Hai query đọc có thể thấy dữ liệu thay đổi

Nếu transaction khác xóa Order sau bước IDs nhưng trước bước fetch, `byId.get(id)` có thể không tìm thấy. Kế hoạch hai bước xử lý tốt **cardinality**, nhưng không tự tạo snapshot bất biến; cần isolation/policy phù hợp nếu API đòi hỏi consistency mạnh.

### 14.5. Page size không nên vô hạn

Danh sách `ids` quá dài tạo nhiều bind parameters và graph lớn. Ứng dụng nên giới hạn page size, ví dụ 20–100 tùy use case, metrics và kích thước association, thay vì cho phép client tự yêu cầu hàng chục nghìn root kèm toàn bộ children.

---

## 15. Một service EntityManager đầy đủ: nội dung DTO và tổng đếm

Ví dụ dưới đây cho danh sách Orders theo trạng thái với DTO đơn giản, **không fetch collection**.

### 15.1. DTO cho kết quả

```java
package demo.dto;

import java.util.List;

public record PageResult<T>(
    List<T> content,
    int pageIndex,
    int pageSize,
    long totalElements
) {
    public PageResult {
        if (pageIndex < 0 || pageSize <= 0 || totalElements < 0) {
            throw new IllegalArgumentException("Invalid page metadata");
        }
        content = List.copyOf(content);
    }

    public long totalPages() {
        return totalElements == 0
            ? 0
            : 1 + (totalElements - 1) / pageSize;
    }

    public boolean hasNext() {
        return ((long) pageIndex + 1L) < totalPages();
    }
}
```

### 15.2. Service đọc trang

```java
package demo.service;

import demo.domain.OrderStatus;
import demo.dto.OrderListRow;
import demo.dto.PageResult;

import jakarta.persistence.EntityManager;
import java.util.List;
import java.util.Objects;

public final class OrderPageQueryService {

    public PageResult<OrderListRow> findByStatus(
            EntityManager em,
            OrderStatus status,
            int pageIndex,
            int pageSize) {

        Objects.requireNonNull(em);
        Objects.requireNonNull(status);

        if (pageIndex < 0 || pageSize <= 0 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page request");
        }

        long offsetLong = (long) pageIndex * pageSize;

        if (offsetLong > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Offset too large");
        }

        // Truy vấn 1: chỉ đếm Order gốc.
        Long total = em.createQuery(
            """
            SELECT COUNT(o)
            FROM PurchaseOrder o
            WHERE o.status = :status
            """,
            Long.class)
            .setParameter("status", status)
            .getSingleResult();

        // Truy vấn 2: chỉ lấy những cột cần hiển thị.
        List<OrderListRow> rows = em.createQuery(
            """
            SELECT NEW demo.dto.OrderListRow(
                o.id,
                o.orderNumber,
                o.createdAt,
                c.displayName
            )
            FROM PurchaseOrder o
            JOIN o.customer c
            WHERE o.status = :status
            ORDER BY o.createdAt DESC, o.id DESC
            """,
            OrderListRow.class)
            .setParameter("status", status)
            .setFirstResult((int) offsetLong)
            .setMaxResults(pageSize)
            .getResultList();

        return new PageResult<>(
            rows, pageIndex, pageSize, total);
    }
}
```

**Giả định quan trọng:** mỗi Order có Customer bắt buộc và hợp lệ, nên JOIN Customer trong content không loại thêm root nào so với count. Nếu mapping cho phép thiếu Customer, phải điều chỉnh cả semantics của content và count.

### 15.3. Tại sao code không return sớm khi count bằng 0?

Có thể chọn tối ưu bỏ content query khi `total=0` trong những hệ thống chấp nhận semantics đó. Nhưng nếu có concurrent insert giữa count và content, chạy content có thể cho kết quả khác. Đoạn code chạy hai query một cách nhất quán về cấu trúc, không khẳng định chúng cùng snapshot.

Trong production, bạn có thể cân nhắc:

- Count trước rồi bỏ content nếu tổng 0.
- Content trước rồi mới count khi cần.
- Dùng Slice không count.
- Dùng snapshot transaction/isolation phù hợp.

Sự lựa chọn phụ thuộc yêu cầu consistency và hiệu năng.

---

## 16. Đếm trước hay lấy content trước?

Không có thứ tự tuyệt đối đúng cho mọi ứng dụng.

### 16.1. Count trước

```text
COUNT -> CONTENT -> RESPONSE
```

Ưu điểm:

- Có thể xác định ngay tổng số.
- Nếu tổng 0, có thể bỏ content query theo policy.
- Dễ xây PageResult.

Hạn chế:

- Count rất nặng có thể trì hoãn hiển thị những bản ghi đầu tiên.
- Dữ liệu có thể thay đổi giữa count và content.
- Với trang sâu vượt tổng, có thể tối ưu bỏ query content nếu phù hợp.

### 16.2. Content trước

```text
CONTENT -> COUNT -> RESPONSE
```

Ưu điểm:

- Có thể sớm có các phần tử cần trả.
- Trong một số giao diện, nếu chỉ cần biết có trang sau thì có thể bỏ count hoàn toàn.
- Framework có thể áp dụng một số tối ưu dựa trên số phần tử đã nhận.

Hạn chế:

- Nếu cần totalElements chính xác, vẫn phải chạy count.
- Không thể suy tổng chính xác từ một page đầy nếu chưa biết còn các pages sau.
- Dữ liệu có thể thay đổi trước khi count.

### 16.3. Đừng tự suy total bằng công thức thiếu cơ sở

Sai:

```java
long total = pageIndex * pageSize + content.size();
```

Công thức này chỉ cho biết một **cận dưới** của số bản ghi theo giả định trang hợp lệ, không phải tổng đầy đủ nếu còn trang tiếp. Trong một số tình huống chắc chắn không còn trang sau (ví dụ kết quả trang cuối không đầy với query/cardinality đúng), có thể suy tổng dưới những điều kiện cụ thể; nhưng không biến suy luận đó thành quy tắc chung.

Nếu content query JOIN to-many làm phần tử bị loại trùng sau pagination, ngay cả “page không đầy” cũng không đủ để suy là trang cuối.

---

## 17. Spring Data JPA: Page<T> và hai truy vấn

Spring Data JPA cung cấp `Pageable` và `Page<T>`:

```java
Pageable request = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
```

Repository có thể trả:

```java
Page<PurchaseOrder> page =
    repository.findByStatus(OrderStatus.PAID, request);
```

`Page` thường chứa content và total metadata. Spring Data có cơ chế tạo/thực thi count query hoặc tối ưu số lần đếm tùy loại query, kết quả content và phiên bản framework. **Không nên giả định một Page method luôn phát chính xác hai câu SQL trong mọi trường hợp**. Ngoài ra lazy associations có thể gây thêm SQL khi map entity ra response.

### 17.1. Derived query đơn giản

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
```

Với derived query đơn giản, Spring Data thường có thể xây content/count tương ứng.

### 17.2. Khi cần @Query tường minh

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT o
            FROM PurchaseOrder o
            WHERE o.status = :status
            """,
        countQuery = """
            SELECT COUNT(o)
            FROM PurchaseOrder o
            WHERE o.status = :status
            """
    )
    Page<PurchaseOrder> findPageByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable
    );
}
```

Cần import:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
```

Cặp query mô tả rõ:

- `value`: tập Orders để lấy trang.
- `countQuery`: tổng Orders thỏa cùng status.

### 17.3. DTO projection với countQuery

```java
@Query(
    value = """
        SELECT NEW demo.dto.OrderListRow(
            o.id, o.orderNumber, o.createdAt, c.displayName
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        WHERE o.status = :status
        """,
    countQuery = """
        SELECT COUNT(o)
        FROM PurchaseOrder o
        WHERE o.status = :status
        """
)
Page<OrderListRow> findOrderRows(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

`Pageable` cung cấp giới hạn và sort; Java caller nên dùng sort theo các property được ánh xạ và có unique tie-breaker. Với JPQL constructor expression phức tạp, xác minh cách Spring Data áp dụng dynamic sort trên query thực tế, nhất là khi có alias/computed sort.

### 17.4. Khi nào nên khai báo countQuery?

Nên cân nhắc tường minh khi content query có:

- `JOIN` qua collection.
- `DISTINCT`.
- `GROUP BY`/`HAVING`.
- Constructor DTO projection phức tạp.
- `JOIN FETCH` hoặc `@EntityGraph`.
- Subquery phức tạp.
- Native SQL.
- Điều kiện quyền/tenant/soft-delete khó tự suy ra.

Spring Data có khả năng derive count cho nhiều truy vấn, nhưng không nên xem đó là bảo đảm tự động cho mọi JPQL phức tạp.

---

## 18. Spring Data JPA với EXISTS và countQuery tương ứng

Truy vấn lọc Orders có ít nhất một Line SKU A:

```java
@Query(
    value = """
        SELECT o
        FROM PurchaseOrder o
        WHERE EXISTS (
            SELECT l.id
            FROM OrderLine l
            WHERE l.order = o
              AND l.sku LIKE :prefix
        )
        """,
    countQuery = """
        SELECT COUNT(o)
        FROM PurchaseOrder o
        WHERE EXISTS (
            SELECT l.id
            FROM OrderLine l
            WHERE l.order = o
              AND l.sku LIKE :prefix
        )
        """
)
Page<PurchaseOrder> findByLineSku(
    @Param("prefix") String prefix,
    Pageable pageable
);
```

Gọi:

```java
Pageable pageable = PageRequest.of(
    0, 20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<PurchaseOrder> page =
    repository.findByLineSku("A-%", pageable);
```

Với dữ liệu mẫu, tổng Orders thỏa prefix là **2**, không phải 4 Lines.

### 18.1. So sánh cách dùng JOIN DISTINCT

Nếu content query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

count query phù hợp:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

Không dùng `COUNT(o)` với JOIN to-many khi một Order có thể có nhiều Lines match.

### 18.2. COUNT DISTINCT root khác COUNT DISTINCT child

`COUNT(DISTINCT l.id)` đếm số Lines khác nhau. Nếu API Page là Orders, đây vẫn là đơn vị sai. Thay `l.id` bằng `o.id` hoặc dùng EXISTS để đếm root.

---

## 19. Page và Slice: không phải giao diện nào cũng cần count

Trong Spring Data:

- `Page<T>` cung cấp tổng số phần tử và tổng số trang.
- `Slice<T>` tập trung vào đoạn kết quả và khả năng còn đoạn tiếp theo, thường **không yêu cầu truy vấn đếm toàn bộ**.
- `List<T>` với `Pageable` có thể chỉ lấy nội dung, không có tổng metadata.

### 19.1. Khi nên dùng Page

Giao diện cần:

```text
Trang 3 / 125
Tổng cộng 2.489 đơn hàng
```

Khi đó count có giá trị thật sự, dù có thêm chi phí.

### 19.2. Khi nên dùng Slice

Giao diện “Tải thêm” chỉ cần biết:

```text
Đã nhận 20 Orders.
Có thêm không?
```

Một chiến lược phổ biến là truy vấn **pageSize + 1** phần tử:

```java
List<OrderListRow> fetched = query
    .setFirstResult(offset)
    .setMaxResults(pageSize + 1)
    .getResultList();

boolean hasNext = fetched.size() > pageSize;

List<OrderListRow> content = hasNext
    ? fetched.subList(0, pageSize)
    : fetched;
```

Đây là chiến lược thường dùng để xác định `hasNext` mà không cần `COUNT(*)`, nhưng chỉ đúng khi query đang trả **đúng một row cho mỗi phần tử logic**. Nếu JOIN to-many gây duplicate root, lấy size+1 SQL rows vẫn có thể đưa ra kết luận sai.

### 19.3. Ví dụ Spring Slice

```java
Slice<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
```

Spring Data có thể thực thi chiến lược phù hợp để biết `hasNext`. Không kỳ vọng `Slice` có `getTotalElements()` hoặc `getTotalPages()` như `Page`.

### 19.4. Vì sao không phải luôn chạy COUNT?

Một count query trên bảng lớn có filter phức tạp và JOIN có thể rất tốn tài nguyên, đặc biệt khi user không cần tổng chính xác. **Không thực hiện công việc chỉ vì framework có API thuận tiện**; chọn contract phù hợp.

---

## 20. Phân trang trong ứng dụng phải có ORDER BY ổn định

Content query:

```jpql
SELECT o
FROM PurchaseOrder o
ORDER BY o.createdAt DESC
```

nếu nhiều Orders có cùng `createdAt`, thứ tự giữa chúng không xác định đầy đủ. Điều này có thể tạo lặp/thiếu khi đổi page hoặc khi execution plan thay đổi.

Nên thêm khóa phụ unique:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

### 20.1. Count query có cần ORDER BY này không?

**Không.** Count chỉ trả một số, không cần thứ tự.

Tách hai query cho phép:

- Content giữ `ORDER BY createdAt DESC, id DESC`.
- Count bỏ `ORDER BY` hoàn toàn.

### 20.2. Unique sort key không tạo snapshot giữa requests

Nếu có Order mới được chèn ở đầu danh sách giữa lúc tải page 0 và page 1, offset có thể dịch chuyển, khiến một Order xuất hiện ở cả hai trang. Đây là rủi ro của offset pagination với dữ liệu biến động, **khác với sai count query**.

Muốn giảm drift ở các feed liên tục thay đổi, cân nhắc keyset/seek pagination hoặc snapshot policy, tùy yêu cầu.

### 20.3. Count luôn phải tương ứng với bộ lọc, không tương ứng với cursor

Với offset Page tổng count là toàn bộ tập thỏa filter. Với keyset cursor API, nhiều thiết kế không trả totalElements; nếu vẫn trả tổng thì cần định nghĩa rõ count là toàn tập theo filter hay chỉ phần còn lại sau cursor. Không trộn hai khái niệm.

---

## 21. COUNT query với GROUP BY và HAVING

Đây là trường hợp phức tạp hơn vì content query không còn trả từng root entity mà có thể trả **một nhóm**.

Ví dụ:

> Liệt kê khách hàng cùng số Order đã tạo, chỉ gồm những khách có ít nhất 2 Orders.

Content query:

```jpql
SELECT
    c.id,
    c.displayName,
    COUNT(o)
FROM Customer c
LEFT JOIN PurchaseOrder o ON o.customer = c
GROUP BY c.id, c.displayName
HAVING COUNT(o) >= :minimumOrders
ORDER BY COUNT(o) DESC, c.id ASC
```

Mỗi row ở đây đại diện cho **một Customer group**, không phải một Order.

### 21.1. Không dùng COUNT(o) đơn giản để đếm số groups

Sai:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
```

Câu này đếm tổng số Orders, không đếm số Customers đạt ngưỡng.

Sai theo mục đích group count:

```jpql
SELECT COUNT(c)
FROM Customer c
```

Câu này đếm tất cả Customers, kể cả khách không đạt `minimumOrders`.

### 21.2. Một cách portable: correlated subquery trong WHERE

Nếu có mapping từ Order về Customer như trên:

```jpql
SELECT COUNT(c)
FROM Customer c
WHERE (
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.customer = c
) >= :minimumOrders
```

Câu này đếm Customers thỏa yêu cầu “có ít nhất minimumOrders Orders”, nhất quán với nhóm mà content query trả.

**Lưu ý:** JPQL subqueries trong `WHERE` và `HAVING` là công cụ phù hợp; không mặc định dùng một subquery trong `FROM` theo chuẩn JPQL thông thường.

### 21.3. Count có thể vẫn đắt

Correlated aggregate cho từng Customer có thể tạo execution plan nặng trên một số DBMS. Optimizer có thể rewrite, nhưng hiệu năng cần đo. Với report phức tạp, một native SQL query đếm các groups qua derived table hoặc một reporting view có thể thích hợp hơn, chấp nhận phụ thuộc DBMS.

### 21.4. Nếu nội dung có nhiều GROUP BY keys

Ví dụ nhóm theo `(customer, year)` hoặc `(orderStatus, month)`. Lúc này một Customer có thể tạo nhiều groups. Count phải đếm **các nhóm**, không chỉ COUNT DISTINCT Customer.

Có thể:

- Dùng native SQL với subquery/CTE để đếm số rows của grouped result.
- Thiết kế bảng tổng hợp/report view.
- Dùng query riêng mô tả đúng group qualification.
- Sử dụng cách lấy toàn bộ group keys để đếm chỉ khi tập dữ liệu nhỏ và đã chấp nhận chi phí.

Không lấy `getResultList().size()` của toàn bộ report lớn chỉ để giả làm count nếu database có thể làm việc đó hiệu quả hơn.

---

## 22. HAVING trong content, WHERE khác hẳn trong count

`WHERE` lọc các rows trước khi nhóm. `HAVING` lọc groups sau khi aggregation.

Ví dụ:

```jpql
SELECT c.id, COUNT(o)
FROM Customer c
LEFT JOIN PurchaseOrder o ON o.customer = c
WHERE c.active = true
GROUP BY c.id
HAVING COUNT(o) >= 2
```

(`c.active` là thuộc tính giả định trong mô hình mở rộng; entity ví dụ tối giản ở trên chưa khai báo field này.)

Count tương ứng phải:

1. Chỉ xét Customers active.
2. Chỉ đếm Customers có ít nhất hai Orders theo cùng điều kiện.

```jpql
SELECT COUNT(c)
FROM Customer c
WHERE c.active = true
  AND (
      SELECT COUNT(o)
      FROM PurchaseOrder o
      WHERE o.customer = c
  ) >= 2
```

Nếu content nhóm theo cả Customer và một thuộc tính khác, công thức phải được thiết kế lại. Đây không phải công thức tự động cho mọi `GROUP BY`, mà minh họa **chuyển điều kiện trên groups thành điều kiện xác định root/group được đếm**.

---

## 23. DISTINCT trong content: count phải giữ ý nghĩa unique

Một content query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity >= :minQuantity
```

trả Orders duy nhất. Count hợp lệ:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity >= :minQuantity
```

Nhưng nếu content projection:

```jpql
SELECT DISTINCT o.id, l.sku
FROM PurchaseOrder o
JOIN o.lines l
```

thì mỗi tuple `(orderId, sku)` là một phần tử. `COUNT(DISTINCT o.id)` sẽ **không đếm số tuples**.

### 23.1. DISTINCT theo toàn projection

SQL DISTINCT áp dụng cho toàn bộ các biểu thức trong SELECT. Với DTO có `o.id` và `l.sku`, cùng Order nhưng hai SKU khác nhau vẫn là hai rows.

### 23.2. Nhiều cột DISTINCT có thể khó biểu đạt trong JPQL count

Một số DBMS hỗ trợ `COUNT(DISTINCT (a,b))` hoặc cách viết riêng; không phải mọi biến thể đều portable qua JPQL. Nếu API phân trang một tập các tổ hợp nhiều cột, cần thiết kế câu count theo nhóm/derived table hoặc giải pháp vendor-specific phù hợp.

### 23.3. Đừng chọn entity root cho content nếu thực sự muốn tuples

Hãy định nghĩa DTO và key logic rõ ràng. Count phải theo chính đơn vị DTO, không mặc định entity root.

---

## 24. COUNT trên JOIN nhiều collections: nguy cơ nhân hàng

Giả sử Order có hai collections:

```text
Order#1001:
  3 Lines
  2 Payments
```

Một query JOIN cả hai:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
JOIN o.payments p
```

có thể tạo 3 × 2 = 6 dòng cho cùng Order.

Khi content chỉ muốn một Order:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
JOIN o.payments p
```

có thể đếm root duy nhất, nhưng database vẫn phải thực hiện joins đủ để xác định filter.

### 24.1. EXISTS cho nhiều điều kiện độc lập

Nếu business yêu cầu:

> Order phải có **ít nhất một Line A** và **ít nhất một Payment thành công**.

Có thể dùng hai EXISTS:

```jpql
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :prefix
)
AND EXISTS (
    SELECT p.id
    FROM Payment p
    WHERE p.order = o
      AND p.status = :successful
)
```

Đây là ví dụ trên **mô hình mở rộng có entity Payment**. Khi hai điều kiện áp vào hai collections độc lập, dùng hai EXISTS thể hiện logic “có ít nhất một trong mỗi collection” và tránh nhân rows chỉ để lọc root.

### 24.2. DISTINCT không sửa mọi aggregate

Nếu content còn muốn `SUM(p.amount)`, JOIN Lines với Payments có thể làm mỗi payment bị lặp nhiều lần. `COUNT(DISTINCT o.id)` chỉ sửa **count roots**, không tự sửa số tiền bị cộng lặp trong content.

Cần kiểm soát hạt dữ liệu của từng phép aggregate: aggregate riêng, query riêng, CTE/native SQL, hoặc DTO composition có chủ đích.

---

## 25. LEFT JOIN và điều kiện lọc: count rất dễ khác content

Một câu thường gặp:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN o.lines l
WHERE l.sku LIKE :prefix
```

Mặc dù có LEFT JOIN, predicate ở WHERE với `l.sku` sẽ loại các rows mà `l` NULL. Vì vậy Orders không có Line phù hợp không xuất hiện.

Nếu count query bỏ JOIN:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
```

nó đếm cả Orders không thỏa prefix, sai semantics.

### 25.1. Dùng EXISTS nếu chỉ cần những Orders có Line match

Content:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :prefix
)
```

Count cùng EXISTS.

### 25.2. Nếu muốn giữ Orders không có child

Có thể dùng `LEFT JOIN` với điều kiện ở `ON` tùy use case:

```jpql
SELECT o, l
FROM PurchaseOrder o
LEFT JOIN o.lines l ON l.sku LIKE :prefix
```

Nhưng query trả **pairs (Order, Line)** và có thể có nhiều rows/Order. Không dùng cách này như root pagination mặc định nếu Order có nhiều Lines match.

### 25.3. Khác biệt null và optional association

Khi viết lại count từ content, đừng tự ý đổi `LEFT JOIN` sang `JOIN` hoặc bỏ một join optional mà chưa xem nó có loại roots hay không. Tập phần tử logic của hai query phải nhất quán.

---

## 26. Count query với điều kiện tìm kiếm tùy chọn

API có thể nhận:

```text
status: PAID hoặc null (không lọc)
customerNamePrefix: String hoặc null
createdFrom: LocalDateTime hoặc null
skuPrefix: String hoặc null
```

Một cách biểu diễn trong JPQL là:

```jpql
WHERE (:status IS NULL OR o.status = :status)
  AND (:createdFrom IS NULL OR o.createdAt >= :createdFrom)
```

Nhưng với nhiều điều kiện, công thức “tham số null hoặc predicate” có thể khiến query khó tối ưu. Khi optional conditions nhiều và có JOIN/EXISTS, thường nên tạo dynamic predicates nhất quán bằng Criteria API, Specification hoặc một query builder.

### 26.1. Không chỉ copy-paste chuỗi WHERE rồi sửa tay

Nếu content query và count query mỗi nơi có một chuỗi WHERE dài, một thay đổi yêu cầu có thể được cập nhật một nơi mà quên nơi kia.

Có thể tập trung business predicates ở một function dựng query, rồi dùng lại logic cho hai root contexts.

### 26.2. Đừng tái sử dụng Predicate object giữa hai CriteriaQuery roots

Trong Criteria API, `Predicate` thường gắn với `Root`/`Join` của query cụ thể. Không nên tạo predicate từ data query rồi gắn nguyên object đó vào count query với root khác.

Hãy tái sử dụng **logic xây predicate**, tạo predicate riêng cho root của mỗi query.

---

## 27. Criteria API: dựng content và count với cùng filter logic

Giả sử muốn filter Orders theo status và thời điểm tạo.

Hàm helper nhận đúng Root và CriteriaBuilder:

```java
private static Predicate[] predicates(
        CriteriaBuilder cb,
        Root<PurchaseOrder> root,
        OrderStatus status,
        LocalDateTime fromTime) {

    List<Predicate> filters = new ArrayList<>();

    if (status != null) {
        filters.add(
            cb.equal(root.get("status"), status));
    }

    if (fromTime != null) {
        filters.add(
            cb.greaterThanOrEqualTo(
                root.get("createdAt"), fromTime));
    }

    return filters.toArray(Predicate[]::new);
}
```

Imports:

```java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;
import jakarta.persistence.criteria.Predicate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
```

### 27.1. Content query

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> dataQuery =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> dataRoot =
    dataQuery.from(PurchaseOrder.class);

dataQuery
    .select(dataRoot)
    .where(predicates(
        cb, dataRoot, status, fromTime))
    .orderBy(
        cb.desc(dataRoot.get("createdAt")),
        cb.desc(dataRoot.get("id"))
    );

List<PurchaseOrder> content =
    em.createQuery(dataQuery)
        .setFirstResult(offset)
        .setMaxResults(pageSize)
        .getResultList();
```

### 27.2. Count query

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

Root<PurchaseOrder> countRoot =
    countQuery.from(PurchaseOrder.class);

countQuery
    .select(cb.count(countRoot))
    .where(predicates(
        cb, countRoot, status, fromTime));

Long total = em.createQuery(countQuery)
    .getSingleResult();
```

### 27.3. Vì sao cách này tốt?

- Cùng business filter logic.
- Hai Criteria roots khác nhau được xây riêng.
- Count không cần ORDER BY.
- Nếu content bổ sung fetch association chỉ để hiển thị, count không tự kéo theo fetch.
- Có thể mở rộng với `cb.exists(subquery)` cho child filter.

### 27.4. Cảnh giác khi helper tự thêm JOIN

Nếu helper tạo JOIN to-many cho filter, count vẫn có thể cần `cb.countDistinct(countRoot.get("id"))` hoặc nên rewrite bằng EXISTS. Không phải cứ dùng lại predicate là count tự đúng.

---

## 28. Spring Data Specification và count

Spring Data JPA `Specification<T>` có thể giúp tái sử dụng điều kiện truy vấn. Tuy nhiên, một specification vừa tạo predicates vừa **gọi root.fetch(...)** hay sửa `query.orderBy(...)` có thể gây vấn đề khi framework dùng nó cho count.

Ví dụ về cách suy nghĩ:

```text
Specification phục vụ filter:
   status == PAID
   createdAt >= fromTime
   tenantId == currentTenant
   EXISTS Line SKU prefix

Content query:
   dùng filter + sort + fetch plan/DTO

Count query:
   dùng filter + count root
   không dùng fetch association chỉ phục vụ hiển thị
```

### 28.1. Không đặt fetch join bừa bãi trong Specification chung

Một anti-pattern:

```java
return (root, query, cb) -> {
    root.fetch("lines", JoinType.LEFT);
    return cb.equal(root.get("status"), status);
};
```

Nếu specification được dùng để dựng count query, `fetch` có thể khiến count query không hợp lệ. Một số code cố kiểm tra `query.getResultType()` rồi bỏ fetch khi là Long; cách này phụ thuộc implementation/lifecycle và dễ trở nên khó bảo trì.

Tốt hơn là tách rõ **filter specification** và **fetch plan của data query**, dùng entity graph/projection hoặc custom query khi cần.

### 28.2. Count specification riêng

Một số phiên bản Spring Data JPA cung cấp API cho phép dùng count specification khác content specification. Nếu lựa chọn đó được dùng, hai specification phải vẫn tương đương về **bộ lọc**, dù khác fetch/joins phục vụ tính toán.

Tên và overload API có thể thay đổi theo phiên bản Spring Data đang dùng; hãy kiểm tra tài liệu version của dự án trước khi áp dụng.

---

## 29. Native SQL: content và count phải có contract rõ

Trong Spring Data JPA, có thể khai báo native query với `countQuery` riêng.

```java
@Query(
    value = """
        SELECT o.id, o.order_number, o.created_at
        FROM purchase_orders o
        WHERE o.order_status = :status
        ORDER BY o.created_at DESC, o.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM purchase_orders o
        WHERE o.order_status = :status
        """,
    nativeQuery = true
)
Page<OrderNativeView> findNativePage(
    @Param("status") String status,
    Pageable pageable
);
```

`OrderNativeView` ở đây là interface projection giả định với getters/aliases tương ứng; đoạn code minh họa cấu trúc native `value/countQuery`, không phải một repository hoàn chỉnh có đầy đủ projection đã định nghĩa.

### 29.1. Native SQL có thể hữu ích cho count nhóm

Nếu content query là grouped report:

```sql
SELECT
    o.customer_id,
    EXTRACT(YEAR FROM o.created_at) AS year_bucket,
    COUNT(*) AS order_count
FROM purchase_orders o
GROUP BY o.customer_id, EXTRACT(YEAR FROM o.created_at)
HAVING COUNT(*) >= 2
ORDER BY year_bucket DESC, o.customer_id ASC
LIMIT ? OFFSET ?;
```

Một count query dạng derived table:

```sql
SELECT COUNT(*)
FROM (
    SELECT
        o.customer_id,
        EXTRACT(YEAR FROM o.created_at)
    FROM purchase_orders o
    GROUP BY o.customer_id, EXTRACT(YEAR FROM o.created_at)
    HAVING COUNT(*) >= 2
) grouped_rows;
```

sẽ đếm **số groups**, không đếm Orders.

Nhưng cú pháp năm, derived tables và pagination khác giữa DBMS, nên đây là SQL minh họa, không phải portable JPQL. Nếu cần báo cáo lớn, có thể cân nhắc reporting view hoặc materialized aggregation theo nền tảng.

### 29.2. Không ghép input vào SQL

Dù dùng JPQL hay native query, hãy bind parameters. Không tạo `WHERE status = '...userInput...'` bằng nối chuỗi trực tiếp.

---

## 30. Tại sao count query có thể chậm hơn content query?

Nhiều người kỳ vọng `COUNT(*)` luôn nhẹ. Thực tế:

- Content query với `LIMIT 20` có thể dừng sau khi tìm đủ 20 phần tử theo index.
- Count query phải xác định **tổng số phần tử thỏa filter**, có thể phải xét rất nhiều rows.
- Với `COUNT(DISTINCT)`, database phải loại duplicate keys.
- Với `EXISTS`/subquery phức tạp, optimizer có thể phải duyệt nhiều index/table.
- Với điều kiện tìm kiếm text không hỗ trợ index hiệu quả, count có thể tốn gần bằng scan toàn bộ vùng dữ liệu.
- Với phân quyền/tenant filter phức tạp, count phải thực hiện nhiều phép điều kiện.
- Với transaction isolation hoặc concurrent writes, database có thể chịu thêm chi phí MVCC/locking tùy hệ quản trị.

### 30.1. Một ví dụ quan sát

```text
CONTENT:
  ORDER BY created_at DESC
  LIMIT 20
  -> có thể dùng index và lấy sớm 20 roots

COUNT:
  WHERE status='PAID'
  -> phải biết toàn bộ số Orders PAID
  -> có thể quét nhiều index entries/rows
```

Đây chỉ là khả năng tối ưu, không phải kết luận cố định cho mọi DBMS.

### 30.2. Count có thể trở thành bottleneck của API

Một endpoint trả 20 DTO nhỏ có thể tốn 50 ms để lấy content nhưng 900 ms để count. Khi đó, tổng thời gian API bị chi phối bởi count, dù người dùng chỉ cần trang đầu.

### 30.3. Không tối ưu mù quáng bằng cách bỏ filter

Count nhanh hơn nhưng bỏ `status`, `tenantId` hoặc một điều kiện nghiệp vụ sẽ **không còn đúng**. Các tối ưu hợp lệ phải giữ semantics hoặc thay đổi API contract rõ ràng.

---

## 31. Tối ưu count query theo nhu cầu thật

### 31.1. Bỏ JOIN chỉ phục vụ projection

Nếu data query JOIN Customer chỉ để hiển thị tên và quan hệ là bắt buộc, count có thể chỉ cần Order root và business filters.

### 31.2. Thay JOIN to-many bằng EXISTS

Nếu query chỉ cần xác định root có child match, EXISTS có thể tránh duplicate join rows và không cần COUNT DISTINCT.

### 31.3. Không giữ ORDER BY trong count

Thứ tự không ảnh hưởng một số tổng.

### 31.4. Dùng index thích hợp

Ví dụ:

```sql
CREATE INDEX idx_orders_status_created_id
ON purchase_orders(order_status, created_at, id);

CREATE INDEX idx_lines_order_sku
ON order_lines(order_id, sku);
```

Index có thể phục vụ lọc/sort hoặc EXISTS, nhưng hiệu quả phụ thuộc thứ tự cột, distribution, pattern LIKE, DBMS optimizer và workload. Với `LIKE '%text%'`, index B-tree thường không giúp theo cách giống prefix search.

### 31.5. Xem query plan

Đo trên DB thật bằng `EXPLAIN`/execution plan tương ứng, chú ý:

- Scan loại nào.
- Số rows đọc và rows trả.
- Sort/hash/temp space.
- Join order.
- Cardinality estimates.
- Thời gian database và network.
- Cache hit rate.
- Số lần gọi query mỗi request.

### 31.6. Bỏ total count nếu UI không dùng

Nếu giao diện chỉ cần “Load more”, hãy cân nhắc `Slice` hoặc cursor. Không cần trả totalElements bằng 0 như một giá trị giả; hãy định nghĩa response schema riêng không có trường total nếu không tính.

---

## 32. “Đếm xấp xỉ” có thay được count chính xác?

Một số database cung cấp số rows ước lượng từ thống kê hoặc metadata. Tuy nhiên, số đó thường **không phản ánh chính xác** mọi filter JOIN/tenant/permission.

Nếu ứng dụng dùng số xấp xỉ:

- Nói rõ đó là estimate.
- Không đưa vào `Page.totalElements` như thể chính xác nếu contract không cho phép.
- Không dùng estimate cho logic nghiệp vụ, billing hoặc kiểm tra quyền.
- Đặt TTL/caching policy và thống nhất cách cập nhật.

Nếu muốn total chính xác, dùng count đúng filter ở snapshot hợp lý. Nếu chỉ cần hiển thị “khoảng 1 triệu bản ghi”, hãy thiết kế một API contract khác với count estimate.

### 32.1. Cached count

Với tập dữ liệu ít thay đổi hoặc dashboard không yêu cầu real-time, có thể cache count theo filter phổ biến. Nhưng cache key phải bao gồm tenant/role/status/date filters tương ứng; invalidation và stale-data tolerance phải được định nghĩa.

### 32.2. Không cache count toàn hệ thống rồi dùng cho mọi filter

Một số nguyên tổng tất cả Orders không thể dùng làm totalElements cho query riêng Orders của Customer hoặc tenant. Đó là sai semantics.

---

## 33. Hai truy vấn không tự bảo đảm snapshot nhất quán

Giả sử count chạy tại thời điểm T1:

```text
COUNT(PAID Orders) = 100
```

Giữa T1 và T2, transaction khác commit một Order PAID mới.

Content query chạy tại T2:

```text
SELECT PAID Orders ORDER BY ... LIMIT 20
```

Nó có thể nhìn thấy Order mới. Khi đó `content` và `totalElements` phản ánh hai thời điểm khác nhau.

### 33.1. Khi nào vấn đề này chấp nhận được?

Với danh sách tìm kiếm bình thường, một mức chênh lệch nhỏ giữa total và content có thể được chấp nhận. Giao diện thường phải xử lý dữ liệu liên tục thay đổi, đặc biệt khi người dùng chuyển trang sau vài giây.

### 33.2. Khi nào cần nhất quán mạnh?

Ví dụ:

- Xuất báo cáo kiểm toán tại một thời điểm.
- Duyệt batch chính xác một tập đối tượng.
- Tạo snapshot nghiệp vụ để đối soát.
- Một workflow cần bảo đảm count và content cùng tập records.

Khi đó, có thể dùng transaction isolation có snapshot phù hợp, snapshot marker, report job, hoặc lưu danh sách IDs tại một thời điểm.

### 33.3. @Transactional(readOnly=true) không đồng nghĩa snapshot cố định

Spring `@Transactional(readOnly = true)` cung cấp transaction boundary và hint read-only, nhưng **không tự đặt isolation level thành snapshot/serializable**. Ở các database dùng `READ COMMITTED`, hai statements trong cùng transaction vẫn có thể nhìn thấy các committed changes khác nhau tùy DBMS.

Muốn bảo đảm snapshot, cần hiểu isolation cụ thể và cách database triển khai MVCC/locking.

### 33.4. Count và content không nên được dùng để điều khiển cập nhật quan trọng

`totalElements=10` không có nghĩa sẽ vẫn có chính xác 10 rows khi transaction ghi bắt đầu. Với logic nghiệp vụ đòi hỏi tính nguyên tử, cần constraint/lock/transaction và kiểm tra tại thời điểm ghi, không dựa vào metadata của trang đọc.

---

## 34. Offset pagination và lặp bản ghi giữa các request

Ngay cả khi count và content được viết chính xác, offset pagination trên dữ liệu thay đổi vẫn có rủi ro.

Giả sử:

```text
Lúc T1:
Orders: [105, 104, 103, 102, 101]
Page 0 size 2: [105, 104]
```

Một Order mới #106 được chèn ở đầu trước khi client tải page 1.

```text
Lúc T2:
Orders: [106, 105, 104, 103, 102, 101]
Page 1 OFFSET 2: [104, 103]
```

Order#104 lặp lại giữa hai trang. Đây **không phải lỗi count query**. Nó là một hệ quả của phân trang dựa trên vị trí khi tập dữ liệu biến động.

### 34.1. Keyset/seek pagination

Với thứ tự:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

có thể lấy trang tiếp theo sau một cursor `(lastCreatedAt,lastId)`:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
  AND (
      o.createdAt < :lastCreatedAt
      OR (
          o.createdAt = :lastCreatedAt
          AND o.id < :lastId
      )
  )
ORDER BY o.createdAt DESC, o.id DESC
```

Dùng `setMaxResults(pageSize + 1)` nếu cần xác định hasNext mà không chạy count.

### 34.2. Keyset không giải quyết mọi concurrency

Nếu sort keys bị cập nhật, một record vẫn có thể dịch chuyển giữa các lượt. Cursor cũng cần định nghĩa chính sách với NULL sort keys, nhiều chiều ASC/DESC và filter thay đổi. Khi yêu cầu snapshot bất biến, cần giải pháp snapshot riêng.

### 34.3. Count và keyset có thể không cần đi cùng nhau

Nhiều API cursor-based trả:

```text
items
nextCursor
hasNext
```

và không có `totalElements`. Đây là lựa chọn có chủ đích để tránh count nặng, không phải thiếu chức năng.

---

## 35. Đọc totalElements từ Page không đồng nghĩa count luôn được gọi

Một số tối ưu của Spring Data JPA có thể suy ra total trong những tình huống nhất định dựa trên số content đã nhận, hoặc bỏ count khi có đủ bằng chứng. Chính sách này phụ thuộc phiên bản framework và cách query trả kết quả.

### 35.1. Đừng dựa vào số SQL count đúng bằng một

Một test:

```java
assertEquals(2, sqlStatementsCount);
```

để chứng minh “Spring Data Page luôn dùng một SELECT và một COUNT” có thể quá cứng. Nếu ORM tải thêm EAGER associations, phát lazy SELECTs, hoặc framework bỏ count theo optimization, số statement khác.

Nên kiểm tra những invariant cốt lõi:

- `content` đúng phần tử.
- `totalElements` đúng theo hạt dữ liệu.
- `totalPages` đúng.
- Không phát sinh collection fetch pagination không kiểm soát.
- SQL count không chứa các JOIN/fetch không cần thiết ngoài filter.

### 35.2. Tối ưu suy total có thể nguy hiểm khi result list đã bị deduplicate sau pagination

Nếu content query JOIN to-many nhưng provider/filter Java loại duplicate sau SQL LIMIT, một page có thể ít hơn pageSize mà **không phải trang cuối**. Suy total chỉ vì content ngắn sẽ sai. Vì vậy, content query phải đúng cardinality trước khi dựa vào bất kỳ count-skip heuristic nào.

---

## 36. Thiết kế một bộ lọc dùng chung

Một cách tránh lệch filter giữa count và content là đưa điều kiện nghiệp vụ vào một object riêng.

```java
public record OrderSearch(
    OrderStatus status,
    Long customerId,
    LocalDateTime createdFrom,
    String skuPrefix
) {}
```

Sau đó tạo một helper dựng predicates từ `OrderSearch`:

```text
OrderSearch
    |
    +-- build predicates for data root
    |
    +-- build predicates for count root
```

Đặc điểm thiết kế:

1. Cùng input filter object.
2. Mỗi query có Root/Join riêng.
3. Các điều kiện mandatory như tenant/soft-delete không bị bỏ.
4. Data query có sort và projection riêng.
5. Count query có COUNT và bỏ sort/fetch.
6. Tập dữ liệu test xác nhận hai cách xây query cùng một root qualification.

### 36.1. Tránh dùng String concat lặp lại

Việc ghép JPQL strings thủ công ở nhiều nơi dễ mất đồng bộ. Nếu query dài, có thể dùng Criteria/Specification/QueryDSL hoặc một repository abstraction đã được dự án lựa chọn.

### 36.2. Không biến một Predicate object thành “shared state” giữa queries

Criteria API predicates tham chiếu tới Root/Join cụ thể. Khi dựng count query với Root khác, phải tạo predicates mới từ cùng logic; không lấy đối tượng predicate của query trước gắn lại bất chấp context.

### 36.3. Cần kiểm thử cả query data và count

Chỉ test filter builder một lần không đủ nếu content/count được dựng bằng hai code paths khác nhau. Tạo dữ liệu có các trường hợp biên rồi so khớp tổng của count với tập root unique của content khi không áp dụng pagination trong môi trường thử nghiệm.

---

## 37. Lỗi thường gặp khi tách query

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `totalElements` lớn hơn số Orders thực | JOIN to-many nhân rows | COUNT DISTINCT root hoặc EXISTS |
| `totalElements` nhỏ hơn số Orders thỏa filter | Count thiếu JOIN/điều kiện optional | Giữ root qualification tương đương |
| Count không khớp content khi có `LEFT JOIN` | WHERE/ON làm semantics khác | Phân tích null-extended rows |
| Spring báo lỗi count query có fetch | Sao chép `JOIN FETCH` vào COUNT | Bỏ FETCH; JOIN thường chỉ khi cần filter |
| Count query chậm bất thường | JOIN/sort/distinct không cần hoặc scan lớn | EXPLAIN, viết lại predicate, index |
| Page không có đủ phần tử nhưng vẫn còn dữ liệu | Phân trang SQL JOIN rows rồi deduplicate | Page root IDs / EXISTS / DISTINCT root đúng |
| `Pageable` trên fetch collection chạy chậm | In-memory pagination hoặc nhiều SQL rows | Hai bước IDs rồi fetch |
| Data và count khác status/date filter | Copy-paste WHERE không đồng bộ | Tái sử dụng filter model/builder |
| Total count không áp dụng tenant filter | Sai logic quyền | Áp dụng mandatory filters ở cả hai |
| DTO constructor không khớp | Kiểu projection sai | Khớp constructor types |
| COUNT trả `Long` nhưng code cast `Integer` | Hiểu sai kiểu result | Dùng Long |
| Grouped report count sai | Đếm rows nguồn thay vì groups | Đếm nhóm bằng query tương đương |
| Có duplicate qua các trang dù query không JOIN | Offset drift do concurrent inserts | Keyset/snapshot policy |
| Count và content khác nhau tức thì | Hai SQL quan sát các snapshots khác | Transaction/isolation phù hợp |
| COUNT chạy dù UI chỉ cần “Load more” | Chọn Page sai nhu cầu | Dùng Slice/cursor |
| JOIN to-one bị bỏ khỏi count gây sai | Nội dung lọc/loại root qua JOIN đó | Chứng minh tương đương trước khi bỏ |
| IN :ids trả thứ tự ngẫu nhiên | Không có ORDER BY tương ứng | Map theo ID và khôi phục thứ tự |
| COUNT DISTINCT không sửa SUM sai | Join nhiều collections nhân aggregate | Tách aggregate theo hạt dữ liệu |
| Count cached sai cho tenant khác | Cache key thiếu filter/tenant | Thiết kế cache key và invalidation |
| Trang sâu chậm | Offset lớn phải bỏ qua nhiều rows | Keyset/index phù hợp |

---

## 38. Bài thực hành A — Hai query cơ bản

1. Tạo năm Orders theo dữ liệu mẫu.
2. Filter `status=PAID`.
3. Viết content query lấy page size 2, sort theo `createdAt DESC,id DESC`.
4. Viết count query chỉ dùng `COUNT(o)`.
5. Chạy page 0, ghi hai Orders 1004 và 1003.
6. Chạy page 1, ghi Order 1001.
7. Xác nhận totalElements=3 và totalPages=2.
8. Bỏ `ORDER BY` khỏi count query và giải thích tại sao.
9. Không áp dụng `setMaxResults(2)` vào count.
10. Đổi status sang CANCELLED, đối chiếu total=1.

## 39. Bài thực hành B — DTO và bỏ JOIN khỏi count

1. Tạo `OrderListRow` với id, number, createdAt, customerName.
2. Content query JOIN to-one Customer để chọn displayName.
3. Count query chỉ từ PurchaseOrder với status filter.
4. Xác nhận total đúng khi mọi Order có Customer bắt buộc.
5. Giả lập mô hình optional Customer trong dự án thử.
6. Dùng INNER JOIN content và so sánh count khi bỏ JOIN.
7. Dùng LEFT JOIN content nếu cần giữ Orders thiếu Customer.
8. Viết lại count tương đương semantics mới.
9. Giải thích vì sao “bỏ JOIN khỏi count” không luôn hợp lệ.

## 40. Bài thực hành C — JOIN DISTINCT và COUNT DISTINCT

1. Tạo Order#1001 có hai Lines A và Order#1004 có hai Lines A.
2. Viết content query JOIN Lines theo prefix `A-%`.
3. Đếm rows của query không DISTINCT.
4. Thêm `SELECT DISTINCT o`.
5. Chạy `COUNT(o)` với JOIN.
6. Chạy `COUNT(DISTINCT o.id)`.
7. So sánh tổng 4 JOIN rows với 2 Orders.
8. Giải thích vì sao COUNT DISTINCT là đúng cho root page.
9. Đổi content projection thành `(o.id,l.sku)` và giải thích tại sao root count không còn là tuple count.

## 41. Bài thực hành D — EXISTS thay JOIN

1. Viết query lấy Orders có ít nhất một Line A bằng JOIN DISTINCT.
2. Viết lại query bằng EXISTS.
3. Chạy cùng dữ liệu và so sánh tập Order IDs.
4. Viết count query COUNT(o) dùng cùng EXISTS.
5. Tạo thêm 100 Lines A cho một Order.
6. Xác nhận count vẫn đếm Order một lần.
7. Ghi execution plans và số rows processed.
8. Không kết luận EXISTS luôn nhanh hơn JOIN; phân tích theo index và data distribution.
9. Thêm điều kiện quantity trên **cùng một Line** và kiểm tra cả data/count.

## 42. Bài thực hành E — Spring Data @Query countQuery

1. Viết repository method trả `Page<PurchaseOrder>`.
2. Khai báo `value` JPQL dùng EXISTS.
3. Khai báo `countQuery` tương ứng.
4. Dùng `PageRequest.of(0,2,Sort...)`.
5. Kiểm tra `getContent`, `getTotalElements` và `getTotalPages`.
6. Cố ý bỏ một filter trong countQuery của dự án test.
7. Quan sát metadata sai, rồi sửa.
8. Thử DTO constructor projection với countQuery đơn giản.
9. Ghi SQL và biết rằng số statements phụ thuộc framework/provider.

## 43. Bài thực hành F — Page, Slice và List

1. Xây một endpoint trả `Page<OrderListRow>` với totalElements.
2. Xây một endpoint “Load more” trả `Slice<OrderListRow>`.
3. So sánh API response fields.
4. Chạy trên dữ liệu nhiều trang, kiểm tra hasNext.
5. Nếu tự hiện thực Slice, dùng pageSize+1 với query một row/root.
6. Không suy hasNext từ SQL rows bị JOIN nhân.
7. Đo chi phí count query của Page trên dataset lớn.
8. Giải thích khi nào total count không đáng công tính.
9. Xem Count query có bị framework bỏ qua trong những trường hợp tối ưu hay không.

## 44. Bài thực hành G — Grouped report

1. Mở rộng Customer–Order với ít nhất hai khách có 3 Orders, một khách có 1 Order, một khách không có Order.
2. Viết grouped content query `GROUP BY Customer`, `HAVING COUNT(o) >= 2`.
3. Xác định mỗi content row là một Customer group.
4. Thử `COUNT(o)` trên Order và thấy nó không phải số groups.
5. Viết correlated subquery đếm Customers có số Orders đạt ngưỡng.
6. Chạy cùng filter và so sánh.
7. Mở rộng group theo `(customer,status)` và phân tích vì sao COUNT Customers không đủ.
8. Cân nhắc native SQL derived-table count cho grouped report phức tạp.

## 45. Bài thực hành H — Content với collection

1. Tạo nhiều Orders, mỗi Order có từ 0 đến 10 Lines.
2. Chạy content query dùng `LEFT JOIN FETCH o.lines` cộng pagination.
3. Quan sát warning hoặc pagination behavior theo provider.
4. Viết count query chuẩn độc lập.
5. Chứng minh sửa count không tự sửa collection fetch pagination.
6. Dùng ba bước: count root, page root IDs, fetch collection theo IDs.
7. Khôi phục thứ tự root theo page IDs.
8. Kiểm tra mọi Order có collection đầy đủ.
9. Đo SQL rows và memory so với một JOIN FETCH có pagination.

## 46. Bài thực hành I — Criteria API

1. Tạo object filter chứa status, fromTime.
2. Viết helper nhận `CriteriaBuilder`, `Root` và trả các predicates.
3. Dựng content query với orderBy và pagination.
4. Dựng count query với Root riêng, không orderBy.
5. Xác nhận kết quả hai query consistent.
6. Thêm JOIN to-many vào filter.
7. Sửa count bằng countDistinct hoặc EXISTS.
8. Đảm bảo helper không reuse Predicate object thuộc query khác.
9. Thử trường hợp tất cả filters null.
10. Thêm filter tenant bắt buộc ở cả hai query.

## 47. Bài thực hành J — Concurrency và count chênh content

1. Mở hai EntityManagers trên DB test.
2. EM A thực hiện count Orders PAID.
3. EM B insert một Order PAID và commit.
4. EM A thực hiện content query trong một ngữ cảnh cho phép nhìn committed change mới.
5. Ghi sự khác nhau giữa total và tập content.
6. Thử transaction isolation khác nếu DB hỗ trợ.
7. Không coi `@Transactional(readOnly=true)` là bảo đảm snapshot.
8. Phân biệt vấn đề snapshot mismatch với JOIN multiplication.
9. Đề xuất contract “total tại thời điểm truy vấn” hoặc snapshot job tùy nghiệp vụ.

## 48. Bài thực hành K — EXPLAIN và tối ưu count

1. Tạo dữ liệu nhiều Orders và Lines.
2. Đặt index phù hợp cho status, createdAt, order_id, sku.
3. Đo content query limit 20.
4. Đo count cùng filter.
5. Đo count dùng JOIN DISTINCT.
6. Đo count dùng EXISTS.
7. So sánh execution plans, rows scanned, sort/hash cost.
8. Không chỉ so sánh Java execution time trong một lần chạy.
9. Thử cùng query trên dữ liệu phân phối khác.
10. Quyết định có nên dùng Slice thay Page cho giao diện này.

---

## 49. Checklist trước khi triển khai

| Câu hỏi | Cần xác nhận |
|---|---|
| Một content element là entity, DTO tuple hay group? | Xác định hạt dữ liệu |
| totalElements có đếm cùng hạt đó không? | Không nhầm root với child |
| Data và count có cùng mandatory filters không? | Status, tenant, soft-delete, quyền |
| Có optional filters không? | Cùng logic null/date/search |
| Có JOIN to-many trong content không? | Cần DISTINCT hoặc EXISTS/root page |
| Count có JOIN to-many không? | COUNT DISTINCT đúng root nếu cần |
| Có thể dùng EXISTS thay JOIN chỉ để lọc không? | Giảm duplicate logic |
| Data JOIN to-one chỉ để lấy tên không? | Count có thể bỏ khi không đổi eligibility |
| Có LEFT JOIN/INNER JOIN làm mất root không? | Không tùy tiện bỏ JOIN |
| Có FETCH JOIN ở count không? | Không |
| Có ORDER BY ở count không? | Bỏ nếu không cần |
| Có group/having không? | Đếm groups, không đếm source rows |
| Có sort ổn định cho data không? | Thêm ID tie-breaker |
| Có collection fetch join + Pageable không? | Cân nhắc root IDs first |
| Có các DTO fields cần load không? | Chỉ chọn cột cần |
| Page size đã giới hạn chưa? | Tránh offset/graph quá lớn |
| Offset có thể overflow không? | Tính long, validate |
| UI có thật sự cần totalElements không? | Page hay Slice/cursor |
| COUNT có quá nặng không? | EXPLAIN, indexes, query rewrite |
| Có concurrent writes không? | Snapshot/consistency policy |
| Cache count có đúng filter key không? | Không rò rỉ cross-tenant |
| Có test dữ liệu 0/1/n Lines không? | Bắt duplicate cases |
| Có nhiều groups không? | Kiểm tra count grouped result |
| Có SQL logs và query plans chưa? | Đánh giá thực tế |
| Có kiểm tra framework/provider version không? | Không dựa hành vi không portable |

---

## 50. Câu hỏi ôn tập

1. Vì sao một API Page thường cần cả content query và count query?
2. Một phần tử trong page có thể đại diện các đơn vị nào?
3. Tại sao số SQL rows sau JOIN không luôn bằng số Orders?
4. Content query và count query phải nhất quán ở khía cạnh nào?
5. Hai query có cần có cùng `SELECT` không?
6. Vì sao count query không cần `ORDER BY`?
7. Vì sao count query không nên có `JOIN FETCH`?
8. Vì sao count query không áp dụng `setFirstResult`/`setMaxResults` như content?
9. JPQL `COUNT` thường trả Java type nào?
10. Khi nào `COUNT(o)` trên Order root đúng?
11. Khi nào JOIN to-many làm `COUNT(o)` đếm quá?
12. `COUNT(DISTINCT o.id)` khác `COUNT(l)` ở ý nghĩa nào?
13. Vì sao `COUNT(DISTINCT o.id)` không đúng cho trang mỗi dòng là một OrderLine?
14. Vì sao EXISTS giúp lọc root theo child?
15. Một Order có 100 Lines match thì EXISTS làm count root tăng bao nhiêu?
16. Khi nào COUNT cần giữ JOIN Customer?
17. Vì sao bỏ một filter tenant khỏi count query là lỗi nghiêm trọng?
18. DTO projection ảnh hưởng thế nào đến nội dung được lấy về?
19. Vì sao JOIN to-one dùng để hiển thị có thể được bỏ ở count trong một số mô hình?
20. Vì sao count query phải đếm groups nếu content dùng GROUP BY?
21. Vì sao `COUNT(Customer)` không luôn đếm số grouped rows theo `(Customer,Month)`?
22. Khi nào correlated count subquery có thể giải quyết grouped count?
23. Native SQL derived-table count giải quyết gì?
24. Spring Data JPA dùng `countQuery` khi nào?
25. `Page` khác `Slice` thế nào?
26. Có phải Page method luôn chạy chính xác một COUNT SQL không?
27. Khi nào một query pageSize+1 đủ cho “hasNext”?
28. Vì sao pageSize+1 sai nếu query bị JOIN to-many nhân root?
29. Tại sao content cần ORDER BY có unique tie-breaker?
30. Offset pagination có thể lặp Order giữa requests khi nào?
31. Keyset pagination có cần totalElements không?
32. Tại sao count query có thể chậm hơn content query LIMIT 20?
33. Vì sao index không tự bảo đảm COUNT nhanh?
34. Tại sao chỉ cải thiện COUNT không sửa được collection fetch join pagination?
35. Chiến lược count + page IDs + fetch graph gồm những bước nào?
36. Vì sao `WHERE id IN :ids` không tự giữ thứ tự?
37. Hai câu SELECT trong cùng read-only transaction có luôn thấy cùng snapshot không?
38. Khi nào cần consistency mạnh giữa count và content?
39. Vì sao dùng Criteria API vẫn phải dựng root/predicates riêng cho count?
40. Nếu Specification gọi `root.fetch("lines")`, vì sao count query có thể lỗi?
41. Trong native query, count cần phù hợp projection nào?
42. Nếu có hai collections được JOIN, COUNT DISTINCT có tự sửa SUM tiền bị nhân không?
43. Nên kiểm thử những trường hợp parent/child nào?
44. Trong giao diện “Load more”, làm sao tránh count rất tốn?
45. Tại sao một count estimate không thể âm thầm thay totalElements chính xác?

---

## 51. Bảng ghi nhớ

| Nhu cầu | Content query | Count query |
|---|---|---|
| Danh sách Order theo status | `SELECT o ... WHERE status ... ORDER BY ...` + pagination | `SELECT COUNT(o) ... WHERE status ...` |
| Danh sách DTO có Customer name | `SELECT NEW ... JOIN o.customer` | `COUNT(o)` nếu JOIN Customer không đổi tập root |
| Lọc Orders theo Lines dùng JOIN | `SELECT DISTINCT o JOIN o.lines ...` | `COUNT(DISTINCT o.id) JOIN ...` |
| Lọc Orders theo Lines dùng EXISTS | `SELECT o WHERE EXISTS(...)` | `COUNT(o) WHERE EXISTS(...)` |
| Danh sách Order kèm toàn bộ Lines | Page IDs rồi fetch associations | Count roots độc lập |
| Dashboard mỗi Customer một row | GROUP BY Customer | Đếm Customers thỏa cùng điều kiện nhóm |
| Dashboard mỗi nhóm (Customer,Month) | GROUP BY nhiều keys | Đếm số groups tương ứng |
| Không cần tổng, chỉ cần hasNext | `LIMIT pageSize+1` trên một row/root | Có thể bỏ |
| Page với tổng số trang | Chọn nội dung theo thứ tự ổn định | Count chính xác theo contract |
| Keyset/cursor feed | Chọn sau cursor | Thường không cần count |

### Sơ đồ quyết định

```text
            API CẦN DANH SÁCH
                    |
                    v
        Đơn vị một phần tử là gì?
          /                    \
       ROOT                    DTO/GROUP
        |                         |
        v                         v
    Có JOIN to-many?       Xác định hạt dữ liệu
       /    \               và số groups/tuples
      /      \
    Không    Có
      |       |
      |       +-- Chỉ filter child?
      |              |
      |           Ưu tiên EXISTS
      |           hoặc DISTINCT root
      |              |
      |              v
      |          COUNT root đúng
      |
      v
  CONTENT QUERY
   - SELECT entity/DTO
   - WHERE business filters
   - ORDER BY ổn định
   - LIMIT/OFFSET hoặc cursor
        |
        +----------------------+
                               |
                       UI cần total?
                         /      \
                       Có       Không
                       |          |
                       v          v
                  COUNT QUERY     Slice / cursor
                  - cùng filter   - hasNext
                  - đúng hạt      - không cần COUNT
                  - bỏ ORDER BY
                  - không FETCH
                       |
                       v
                   PAGE RESPONSE
```

**Nguyên tắc cuối bài:** một truy vấn lấy nội dung trang cần **chọn, sắp xếp và giới hạn những phần tử cụ thể**; một truy vấn đếm cần **tính số phần tử logic thỏa cùng bộ lọc**. Vì thế hãy **tách trách nhiệm**: không mang những FETCH JOIN, ORDER BY, projection fields và pagination của data query sang count query một cách máy móc; đồng thời không được bỏ các điều kiện ảnh hưởng eligibility của phần tử. Với JOIN to-many, dùng COUNT DISTINCT đúng root hoặc EXISTS; với grouped report, phải đếm groups; và khi UI không cần tổng, cân nhắc Slice/cursor để khỏi thực hiện phép đếm đắt đỏ không cần thiết. Luôn kiểm thử dữ liệu có nhiều children và đo SQL trên database thật để bảo đảm **tính đúng** và **hiệu năng** của cả hai truy vấn.

