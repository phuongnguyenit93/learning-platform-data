# Phân biệt `INNER JOIN` và `LEFT JOIN` trong truy vấn đối tượng với JPQL

## 1. Vấn đề: truy vấn quan hệ đối tượng không chỉ là nối hai bảng

Trong mô hình **Data Persistence / Relational Access / ORM / JPA**, dữ liệu được lưu ở các bảng quan hệ nhưng mã Java làm việc với **entity** và các thuộc tính quan hệ giữa entity. **JPQL** (*Jakarta Persistence Query Language*) cho phép truy vấn theo tên entity, tên thuộc tính Java và đường dẫn quan hệ thay vì viết trực tiếp tên bảng/cột SQL.

Giả sử ứng dụng bán hàng có các entity:

```text
Customer
  id
  name
  orders: List<PurchaseOrder>
           |
           | @OneToMany
           v
PurchaseOrder
  id
  status
  total
  customer: Customer
           |
           | @ManyToOne
           v
        Customer
```

Yêu cầu A: **Liệt kê những khách hàng đã có ít nhất một đơn hàng.**

Yêu cầu B: **Liệt kê tất cả khách hàng, kể cả những người chưa từng đặt hàng.**

Hai yêu cầu chỉ khác vài chữ, nhưng cách join phù hợp là khác nhau:

```sql
-- A: chỉ lấy khách hàng có order.
SELECT DISTINCT c
FROM Customer c
INNER JOIN c.orders o

-- B: giữ cả khách hàng chưa có order.
SELECT DISTINCT c
FROM Customer c
LEFT JOIN c.orders o
```

Đoạn trên dùng cú pháp **JPQL**, dù khối code được trình bày để dễ so sánh với SQL; các tên `Customer`, `PurchaseOrder`, `orders` là **tên trong mô hình entity**, không nhất thiết trùng tên bảng SQL.

Điểm quyết định:

- **`INNER JOIN`**: chỉ giữ những kết hợp có một phần tử quan hệ phù hợp ở phía được join.
- **`LEFT JOIN`**: giữ mọi bản ghi ở phía bên trái; nếu không có đối tượng phù hợp ở phía bên phải, các biểu thức thuộc về alias phải nhận giá trị **`NULL`** trong kết quả truy vấn.
- Tuy nhiên, một điều kiện trong **`WHERE`** áp lên alias phải có thể làm các hàng được bảo toàn bởi LEFT JOIN bị loại bỏ.
- Khi join một **collection**, một entity ở bên trái có thể xuất hiện **nhiều lần trong các hàng kết hợp**. `DISTINCT`, `GROUP BY`, `COUNT` và phân trang đều cần được suy nghĩ cẩn thận.

Bài học này xây dựng một ví dụ có dữ liệu cố định, đi từ cú pháp cơ bản tới các tình huống thực tế như lọc đơn theo trạng thái, tìm khách hàng không có đơn, thống kê số đơn, fetch join, truy vấn Criteria và tránh lỗi hiệu năng.

---

## 2. Dữ liệu mẫu để quan sát sự khác biệt

Ta có bốn khách hàng:

| `Customer.id` | `Customer.name` |
|---:|---|
| 1 | An |
| 2 | Bình |
| 3 | Chi |
| 4 | Dũng |

Và bốn đơn hàng:

| `PurchaseOrder.id` | `customer_id` | `status` | `total` |
|---:|---:|---|---:|
| 101 | 1 | PAID | 300000 |
| 102 | 1 | DRAFT | 100000 |
| 103 | 3 | CANCELLED | 70000 |
| 104 | 4 | PAID | 250000 |

Đồ thị dữ liệu:

```text
Customer#1 An
  +-- PurchaseOrder#101 [PAID]
  +-- PurchaseOrder#102 [DRAFT]

Customer#2 Bình
  +-- (không có đơn)

Customer#3 Chi
  +-- PurchaseOrder#103 [CANCELLED]

Customer#4 Dũng
  +-- PurchaseOrder#104 [PAID]
```

**Bình không có order**. Đây chính là bản ghi giúp nhìn thấy khác biệt giữa INNER JOIN và LEFT JOIN.

Nếu chỉ nhìn hai bảng từ góc độ SQL:

```text
customers                     purchase_orders
+----+------+                 +-----+-------------+-----------+
| id | name |                 | id  | customer_id | status    |
+----+------+                 +-----+-------------+-----------+
| 1  | An   |                 | 101 | 1           | PAID      |
| 2  | Bình |                 | 102 | 1           | DRAFT     |
| 3  | Chi  |                 | 103 | 3           | CANCELLED |
| 4  | Dũng |                 | 104 | 4           | PAID      |
+----+------+                 +-----+-------------+-----------+
```

Số hàng bên trái là 4, số hàng bên phải là 4. Nhưng kết quả JOIN **không chỉ phụ thuộc số hàng của mỗi bảng**; nó phụ thuộc vào các cặp bản ghi thỏa mãn điều kiện nối.

---

## 3. Mô hình entity dùng trong toàn bài

### 3.1. Enum trạng thái đơn hàng

```java
package com.example.jpql;

public enum OrderStatus {
    DRAFT,
    PAID,
    CANCELLED
}
```

Dùng `@Enumerated(EnumType.STRING)` để ánh xạ enum theo tên, tránh lệ thuộc thứ tự khai báo của các hằng enum.

### 3.2. Entity `Customer`

```java
package com.example.jpql;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false, length = 120)
    private String name;

    @OneToMany(
        mappedBy = "customer",
        fetch = FetchType.LAZY,
        cascade = CascadeType.PERSIST
    )
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
        // Constructor không tham số dành cho JPA.
    }

    public Customer(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name.trim();
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<PurchaseOrder> getOrders() {
        return Collections.unmodifiableList(orders);
    }

    public void addOrder(PurchaseOrder order) {
        if (order == null) {
            throw new IllegalArgumentException("Order không hợp lệ");
        }
        if (order.getCustomer() != null
                && order.getCustomer() != this) {
            throw new IllegalStateException(
                "Order đã thuộc customer khác"
            );
        }

        if (!orders.contains(order)) {
            orders.add(order);
        }
        order.assignCustomer(this);
    }
}
```

Điểm cần nắm:

- Entity name mặc định là `Customer`.
- Thuộc tính `orders` là **collection-valued relationship**.
- `mappedBy = "customer"` nói rằng trường `PurchaseOrder.customer` là owning side của quan hệ.
- `cascade = PERSIST` chỉ dùng để đơn giản hóa dữ liệu demo khi tạo customer và các order mới; bài học này không yêu cầu `CascadeType.ALL`.
- `getOrders()` trả một view chỉ đọc để code bên ngoài không tùy tiện phá tính nhất quán giữa hai phía của quan hệ.

### 3.3. Entity `PurchaseOrder`

```java
package com.example.jpql;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(
        name = "total_amount",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
        // Constructor không tham số dành cho JPA.
    }

    public PurchaseOrder(OrderStatus status, BigDecimal total) {
        this.status = Objects.requireNonNull(status, "status");
        this.total = Objects.requireNonNull(total, "total");
        if (total.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá trị đơn hàng không được âm"
            );
        }
    }

    void assignCustomer(Customer owner) {
        this.customer = Objects.requireNonNull(owner, "owner");
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

Quan hệ từ phía order:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Cột `customer_id` nằm ở **bảng order**, tham chiếu khóa chính của bảng customer. Trong ví dụ, mọi order phải có customer.

### 3.4. DDL tham khảo

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    customer_id BIGINT NOT NULL,

    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
```

DDL chỉ minh họa một dialect có cú pháp identity phù hợp. Tên cột SQL là `customer_id`; trong JPQL, ta dùng **`o.customer` hoặc `c.orders`** để mô tả association, không viết trực tiếp điều kiện `c.id = o.customer_id` nếu đang truy vấn qua entity relationship.

---

## 4. Cú pháp JOIN cơ bản trong JPQL

Một truy vấn JPQL thường bắt đầu bằng:

```sql
SELECT c
FROM Customer c
```

Trong đó:

- `Customer` là tên entity.
- `c` là identification variable/alias cho entity `Customer`.
- `c.orders` là một **relationship path expression** từ customer đến collection đơn hàng.

Có thể mở rộng bằng:

```sql
SELECT c, o
FROM Customer c
JOIN c.orders o
```

Ở đây:

- `JOIN c.orders` yêu cầu nối qua association đã khai báo trên `Customer`.
- `o` là alias của từng `PurchaseOrder` được join.
- `SELECT c, o` trả về **cặp giá trị** cho từng kết hợp phù hợp, không chỉ customer.

Hai cách diễn đạt INNER JOIN:

```sql
FROM Customer c JOIN c.orders o
```

```sql
FROM Customer c INNER JOIN c.orders o
```

Chúng có ý nghĩa INNER JOIN tương đương; từ `INNER` có thể được viết tường minh để dễ đọc.

LEFT JOIN:

```sql
FROM Customer c LEFT JOIN c.orders o
```

hoặc:

```sql
FROM Customer c LEFT OUTER JOIN c.orders o
```

`LEFT JOIN` và `LEFT OUTER JOIN` thể hiện cùng ý nghĩa left outer join.

**JPQL sử dụng tên entity/thuộc tính Java, không bắt buộc dùng tên bảng SQL.** Provider chuyển truy vấn JPQL thành SQL phù hợp metadata quan hệ và dialect.

## 5. `INNER JOIN`: chỉ giữ customer có ít nhất một order

Truy vấn:

```sql
SELECT c.id, c.name, o.id
FROM Customer c
INNER JOIN c.orders o
ORDER BY c.id, o.id
```

Kết quả từ dữ liệu mẫu:

| `c.id` | `c.name` | `o.id` |
|---:|---|---:|
| 1 | An | 101 |
| 1 | An | 102 |
| 3 | Chi | 103 |
| 4 | Dũng | 104 |

**Không có Bình** vì `Customer#2` không có phần tử nào trong `orders` để tạo một cặp kết hợp.

Từ góc nhìn phép quan hệ:

```text
c          o
---------  ----------------------
An         Order 101
An         Order 102
Bình       không có phần tử để nối -> loại khỏi kết quả
Chi        Order 103
Dũng       Order 104
```

### 5.1. INNER JOIN không đồng nghĩa “một customer xuất hiện một lần”

`An` có hai order nên xuất hiện **hai lần trong các hàng kết hợp**. `INNER JOIN` không tự gom thành một customer duy nhất.

Nếu mục tiêu là danh sách customer **không trùng**:

```sql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
ORDER BY c.id
```

Kết quả entity logic:

```text
Customer#1 An
Customer#3 Chi
Customer#4 Dũng
```

`DISTINCT` giúp diễn đạt rõ yêu cầu loại bỏ kết quả trùng. Tùy JPQL/provider, việc giảm trùng ở SQL hoặc ở bước xây danh sách entity có thể được triển khai khác nhau; không nên suy ra số SQL rows chỉ từ số entity trong danh sách.

### 5.2. Dùng INNER JOIN khi nào?

Các tình huống thông dụng:

- Lấy khách hàng **đã từng đặt đơn**.
- Lấy đơn hàng **có ít nhất một dòng chi tiết**.
- Lấy người dùng **có role phù hợp**.
- Lấy sản phẩm **có bản ghi đánh giá**.
- Chỉ lấy những bản ghi có một association cần thiết trong kết quả.

Nhưng khi chỉ cần kiểm tra tồn tại, `EXISTS` cũng là một lựa chọn tốt; xem phần 14 để tránh join nhân bản nhiều rows không cần thiết.

## 6. `LEFT JOIN`: giữ cả customer không có order

Truy vấn:

```sql
SELECT c.id, c.name, o.id
FROM Customer c
LEFT JOIN c.orders o
ORDER BY c.id, o.id
```

Kết quả:

| `c.id` | `c.name` | `o.id` |
|---:|---|---:|
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Bình | `null` |
| 3 | Chi | 103 |
| 4 | Dũng | 104 |

Khác biệt duy nhất so với ví dụ INNER là **Bình vẫn được giữ**. Khi không có order, alias `o` không biểu diễn một entity thực tế, và projection `o.id` trả về `null`.

```text
LEFT JOIN:

Customer         Order
--------------------------
An               101
An               102
Bình             NULL  <-- được bảo toàn
Chi              103
Dũng             104
```

### 6.1. LEFT JOIN không ép mỗi customer đúng một hàng

`LEFT JOIN` giữ mọi customer, nhưng nếu customer có **nhiều order** thì mỗi order vẫn tạo một hàng kết hợp. Với ví dụ:

- 1 An → 2 hàng.
- 1 Bình → 1 hàng với `o = null`.
- 1 Chi → 1 hàng.
- 1 Dũng → 1 hàng.

Tổng cộng **5 hàng** chứ không phải 4. Nếu dùng `SELECT DISTINCT c`, tập entity customer còn 4 phần tử.

### 6.2. Từ trái sang phải là lựa chọn có chủ đích

`FROM Customer c LEFT JOIN c.orders o` nghĩa là **bảo toàn Customer**.

Không nên suy luận rằng chỉ đảo alias là đủ:

```sql
FROM PurchaseOrder o LEFT JOIN o.customer c
```

Truy vấn này bảo toàn **PurchaseOrder**, không bảo toàn Customer. Một customer không có order vẫn không xuất hiện vì chính nó không nằm ở phía bên trái của truy vấn.

Trong mô hình hiện tại `PurchaseOrder.customer` bắt buộc có giá trị, nên với quan hệ này `LEFT JOIN` và `INNER JOIN` có thể cho cùng tập order nếu database thực sự bảo vệ FK/NOT NULL. Nếu quan hệ `customer` là tùy chọn, LEFT JOIN sẽ giữ cả order chưa gắn customer, còn INNER JOIN loại chúng.

### 6.3. Khi nào cần LEFT JOIN?

Các yêu cầu điển hình:

- Danh sách **mọi khách hàng** và đơn gần đây nếu có.
- Danh sách **mọi phòng ban**, kèm nhân viên nếu có.
- Danh sách **mọi khóa học**, kể cả khóa chưa có học viên.
- Báo cáo **mọi sản phẩm**, kể cả sản phẩm chưa được đánh giá.
- Tìm những entity **chưa có** một quan hệ được tạo.
- Hiển thị dashboard với số lượng bằng 0 khi không có phần tử liên quan.

## 7. So sánh nhanh hai loại JOIN

| Tiêu chí | `INNER JOIN` | `LEFT JOIN` |
|---|---|---|
| Có giữ parent không có child? | **Không.** | **Có.** |
| Khi một parent có 3 child | Thường tạo 3 kết hợp. | Thường tạo 3 kết hợp. |
| Khi một parent có 0 child | Tạo 0 kết hợp. | Tạo 1 hàng với alias child `null`. |
| Mục tiêu thường gặp | Chỉ những entity có association phù hợp. | Giữ toàn bộ nguồn, kể cả association thiếu. |
| Có thể đếm child = 0 qua `COUNT(child)`? | Parent không có child bị loại khỏi tập. | Có thể hiển thị parent với count = 0. |
| Có nguy cơ trùng parent trong kết quả? | Có, khi join collection. | Có, khi join collection. |
| Bị ảnh hưởng bởi `WHERE` trên alias child? | Có. | Có; `WHERE` có thể làm mất hàng được bảo toàn. |
| Có quyết định fetch LAZY/EAGER? | Không. | Không. |

Một cách nhớ:

```text
INNER JOIN: "Cần có đối tượng ở cả hai phía."

LEFT JOIN:  "Giữ mọi đối tượng phía trái;
             phía phải có thì nối, không có thì NULL."
```

Tuy nhiên, khi thêm điều kiện lọc vào truy vấn, phải suy nghĩ **điều kiện đó được áp tại bước JOIN hay tại bước WHERE**.

---

## 8. Bẫy quan trọng nhất: `LEFT JOIN` cộng `WHERE` có thể mất khách hàng không có order

Xét yêu cầu: **Hiển thị tất cả khách hàng và các đơn đã thanh toán, nếu có**.

Một truy vấn rất dễ được viết:

```sql
SELECT c.name, o.id
FROM Customer c
LEFT JOIN c.orders o
WHERE o.status = :status
ORDER BY c.id, o.id
```

với:

```java
.setParameter("status", OrderStatus.PAID)
```

Kết quả:

| Customer | Order |
|---|---|
| An | 101 |
| Dũng | 104 |

**Bình bị loại, và Chi cũng bị loại.** Vì sao?

Sau LEFT JOIN, ta có các kết hợp:

```text
An   -> 101 [PAID]
An   -> 102 [DRAFT]
Bình -> NULL
Chi  -> 103 [CANCELLED]
Dũng -> 104 [PAID]
```

Khi `WHERE o.status = PAID` được áp dụng:

- An + 101: đúng → giữ.
- An + 102: sai → bỏ.
- Bình + NULL: biểu thức so sánh với NULL không phải TRUE → bỏ.
- Chi + 103: sai → bỏ.
- Dũng + 104: đúng → giữ.

Như vậy, dù cú pháp viết `LEFT JOIN`, **điều kiện WHERE bắt buộc alias phía phải phải có status PAID** khiến các customer không có đơn PAID bị loại.

### 8.1. Kết luận về `WHERE`

`WHERE` chỉ giữ những hàng mà điều kiện là **TRUE** theo logic ba giá trị SQL/JPQL. Biểu thức với `NULL` thường có thể cho `UNKNOWN`, và kết quả đó không được giữ.

**Không phải cứ thấy từ khóa LEFT JOIN thì mọi parent luôn hiện diện trong kết quả cuối cùng.** Cần xem toàn bộ `WHERE`, `HAVING` và các phép nối khác.

## 9. `ON`: giới hạn child được join mà vẫn giữ parent

Để giữ tất cả customer nhưng chỉ nối các order PAID, dùng `ON` trong association join:

```sql
SELECT c.id, c.name, o.id
FROM Customer c
LEFT JOIN c.orders o ON o.status = :status
ORDER BY c.id, o.id
```

Giả sử tham số `:status = OrderStatus.PAID`, kết quả:

| `c.id` | `c.name` | `o.id` |
|---:|---|---:|
| 1 | An | 101 |
| 2 | Bình | `null` |
| 3 | Chi | `null` |
| 4 | Dũng | 104 |

**Đây mới là kết quả theo yêu cầu.**

Giải thích:

- Với An, có Order#101 thỏa `PAID` nên nối vào; Order#102 không thỏa nên không xuất hiện.
- Với Bình, không có order nào thỏa; LEFT JOIN vẫn giữ customer với `o = null`.
- Với Chi, có order nhưng order đó không thỏa `PAID`; LEFT JOIN vẫn giữ customer với `o = null`.
- Với Dũng, Order#104 thỏa nên nối vào.

### 9.1. `ON` và `WHERE` tác động ở hai giai đoạn khác nhau

```text
FROM Customer c
LEFT JOIN c.orders o ON o.status = PAID
        |
        v
Ghép customer với những order thỏa điều kiện JOIN.
Nếu không có order thỏa, vẫn giữ customer với o = NULL.
        |
        v
WHERE (nếu có)
        |
        v
Lọc các hàng kết hợp đã hình thành.
```

Bảng so sánh:

| Truy vấn | Bình (không có order) | Chi (chỉ có CANCELLED) |
|---|---|---|
| `LEFT JOIN c.orders o` | Giữ với o = null. | Giữ với order 103. |
| `LEFT JOIN c.orders o WHERE o.status = PAID` | Bỏ. | Bỏ. |
| `LEFT JOIN c.orders o ON o.status = PAID` | Giữ với o = null. | Giữ với o = null. |
| `INNER JOIN c.orders o ON o.status = PAID` | Bỏ. | Bỏ. |

### 9.2. `ON` là phần cú pháp của JPQL hiện đại

`ON` cho association join được hỗ trợ từ JPA 2.1 và tồn tại trong Jakarta Persistence. Nếu codebase dùng một provider quá cũ hoặc một ngôn ngữ truy vấn có khác biệt cú pháp, cần kiểm tra phiên bản được hỗ trợ.

Trong JPQL, điều kiện join được xây dựng **từ relationship path**:

```sql
LEFT JOIN c.orders o ON o.status = :status
```

Không cần tự viết lại điều kiện FK `c.id = o.customer_id`; provider biết cách nối qua metadata `@OneToMany`/`@ManyToOne`.

### 9.3. `ON` không sửa được mọi điều kiện phía sau

Truy vấn:

```sql
SELECT c
FROM Customer c
LEFT JOIN c.orders o ON o.status = :status
WHERE o.total > :minimum
```

vẫn loại các parent không có order PAID, vì `WHERE o.total > :minimum` yêu cầu một child phù hợp. Nếu muốn parent vẫn xuất hiện với thống kê thỏa điều kiện, hãy đưa predicate phù hợp vào `ON` và dùng projection/aggregate đúng mục tiêu.

## 10. Vì sao `WHERE o.status = :status OR o IS NULL` chưa hẳn đúng?

Một mẹo hay gặp:

```sql
SELECT c
FROM Customer c
LEFT JOIN c.orders o
WHERE o.status = :status OR o IS NULL
```

Thoạt nhìn có vẻ đã giữ lại các hàng không có order. Nhưng hãy kiểm tra **Chi**:

- Chi có Order#103.
- LEFT JOIN **không tạo** hàng `(Chi, null)`, vì đã có một order phù hợp điều kiện nối cơ bản.
- Hàng thực tế là `(Chi, Order#103)`.
- `o.status = PAID` sai; `o IS NULL` cũng sai.
- **Chi vẫn bị loại**, dù yêu cầu là giữ mọi customer kể cả không có order PAID.

Mẹo `OR o IS NULL` chỉ cứu được parent **không có bất kỳ child nào trong phép nối ban đầu**; nó không cứu parent **có child nhưng không child nào thỏa bộ lọc**.

Đây là lý do dùng:

```sql
LEFT JOIN c.orders o ON o.status = :status
```

khi mục tiêu là *giữ mọi customer, chỉ nối child theo điều kiện*.

## 11. INNER JOIN với `ON` có khác gì đưa điều kiện vào `WHERE`?

Với INNER JOIN trên association:

```sql
SELECT c, o
FROM Customer c
INNER JOIN c.orders o ON o.status = :status
```

và:

```sql
SELECT c, o
FROM Customer c
INNER JOIN c.orders o
WHERE o.status = :status
```

thường tương đương về **tập kết quả** nếu chỉ xét cùng một predicate và không có thêm thành phần ảnh hưởng khác. Vì INNER JOIN vốn chỉ giữ các cặp thỏa.

Ngược lại, với **LEFT JOIN**, vị trí predicate quyết định liệu các parent không có child thỏa có được bảo toàn hay không. Đây là sự khác biệt quan trọng nhất khi lựa chọn `ON` hay `WHERE`.

### 11.1. Ví dụ thêm điều kiện lọc parent

```sql
SELECT c.name, o.id
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
WHERE c.name LIKE :prefix
```

Ở đây:

- `ON o.status = :paid` lọc child nhưng giữ parent.
- `WHERE c.name LIKE :prefix` lọc **chính parent** theo tên.

Nếu `:prefix = 'A%'`, chỉ An được giữ; đó là yêu cầu lọc parent có chủ đích, không phải lỗi LEFT JOIN.

## 12. `INNER JOIN` mặc định và implicit join khi điều hướng quan hệ

Không phải mọi join trong JPQL đều được viết bằng từ khóa `JOIN`.

Xét một đơn hàng có thuộc tính:

```java
@ManyToOne(fetch = FetchType.LAZY)
private SalesAgent assignedAgent;
```

`assignedAgent` có thể bằng `null` nếu chưa phân công nhân viên.

Một truy vấn như:

```sql
SELECT o
FROM PurchaseOrder o
WHERE o.assignedAgent.name = :agentName
```

đi qua **single-valued association** `assignedAgent` để lấy `name`. Theo semantics path navigation của JPQL, dạng điều hướng association này có thể dẫn tới **implicit join với inner-join semantics**, làm các order không có agent bị loại.

Để diễn đạt rõ hơn:

```sql
SELECT o
FROM PurchaseOrder o
JOIN o.assignedAgent a
WHERE a.name = :agentName
```

Nếu cần **giữ các order chưa được phân công**, viết LEFT JOIN tường minh:

```sql
SELECT o.id, a.name
FROM PurchaseOrder o
LEFT JOIN o.assignedAgent a
ORDER BY o.id
```

Khi `assignedAgent = null`, `a.name` là `null`, order vẫn hiện diện.

### 12.1. Phân biệt association path với basic/embedded path

- `o.assignedAgent.name`: đi qua **entity association**; có thể tạo implicit join.
- `o.total`: thuộc tính basic, không cần join entity.
- `c.address.city` nếu `address` là `@Embedded`: path truy cập field nhúng trong cùng entity mapping, không mặc nhiên là join entity khác.

Không nên giải thích mọi dấu chấm trong JPQL là một INNER JOIN.

### 12.2. Collection-valued path cần alias khi truy cập phần tử

Đường dẫn `c.orders` biểu diễn cả collection. Không thể lấy thuộc tính `status` của một tập hợp bằng kiểu cú pháp chung:

```sql
-- Không phải cách viết hợp lệ cho collection:
SELECT c FROM Customer c WHERE c.orders.status = :status
```

Thay bằng:

```sql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :status
```

Alias `o` biểu diễn **một phần tử** của collection trong từng hàng kết hợp, nên `o.status` có nghĩa rõ ràng.

---

## 13. Truy vấn danh sách entity và nguy cơ kết quả lặp

### 13.1. Chọn parent từ phép join collection

```java
List<Customer> customers = em.createQuery(
    """
    SELECT c
    FROM Customer c
    JOIN c.orders o
    ORDER BY c.id
    """,
    Customer.class
).getResultList();
```

Về phép nối logic, An xuất hiện hai lần vì có hai order. Tùy provider và dạng truy vấn, danh sách entity kết quả có thể được xử lý trùng khác nhau; **không nên dựa vào việc provider tự khử trùng** để biểu diễn yêu cầu nghiệp vụ.

Khi muốn mỗi customer xuất hiện đúng một lần:

```java
List<Customer> customers = em.createQuery(
    """
    SELECT DISTINCT c
    FROM Customer c
    JOIN c.orders o
    ORDER BY c.id
    """,
    Customer.class
).getResultList();
```

### 13.2. `DISTINCT` trên tuple không giống `DISTINCT` trên entity

So sánh:

```sql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
```

và:

```sql
SELECT DISTINCT c.id, o.id
FROM Customer c
JOIN c.orders o
```

Ở câu thứ nhất, hai kết hợp của An cùng hướng tới **một entity Customer** nên muốn khử trùng Customer.

Ở câu thứ hai, hai tuple `(1,101)` và `(1,102)` **khác nhau**, nên cả hai vẫn được giữ. `DISTINCT` ở projection áp dụng cho **toàn bộ kết quả được chọn**, không chỉ một cột theo suy đoán.

### 13.3. `SELECT c, o` trả về cái gì trong Java?

```java
List<Object[]> rows = em.createQuery(
    """
    SELECT c, o
    FROM Customer c
    LEFT JOIN c.orders o
    ORDER BY c.id, o.id
    """,
    Object[].class
).getResultList();

for (Object[] row : rows) {
    Customer customer = (Customer) row[0];
    PurchaseOrder order = (PurchaseOrder) row[1];

    String orderLabel =
            order == null ? "(không có)" : order.getId().toString();

    System.out.println(customer.getName() + " / " + orderLabel);
}
```

Với Bình, `row[0]` là một `Customer`; `row[1]` là `null`. Code phải xử lý trường hợp vắng child; nếu gọi `order.getId()` trực tiếp sẽ ném `NullPointerException`.

### 13.4. DTO giúp biểu diễn kết quả ổn định

Thay vì trả entity graph ra API, có thể dùng DTO:

```java
package com.example.jpql;

public record CustomerOrderRow(
    Long customerId,
    String customerName,
    Long orderId
) {}
```

JPQL constructor expression:

```java
List<CustomerOrderRow> rows = em.createQuery(
    """
    SELECT NEW com.example.jpql.CustomerOrderRow(
        c.id,
        c.name,
        o.id
    )
    FROM Customer c
    LEFT JOIN c.orders o
    ORDER BY c.id, o.id
    """,
    CustomerOrderRow.class
).getResultList();
```

Constructor phải có kiểu tham số phù hợp với các biểu thức được chọn. Với LEFT JOIN, `orderId` của customer không có order có thể là `null`; sử dụng `Long` thay vì primitive `long`.

---

## 14. Tìm customer không có order: LEFT JOIN + `IS NULL`

Yêu cầu: **Khách hàng chưa có đơn hàng nào**.

Truy vấn:

```sql
SELECT c
FROM Customer c
LEFT JOIN c.orders o
WHERE o.id IS NULL
ORDER BY c.id
```

Kết quả từ dữ liệu mẫu: **Bình**.

Giải thích:

- Nếu customer có ít nhất một order, LEFT JOIN tạo các hàng với `o.id` khác null.
- Nếu customer không có order, LEFT JOIN tạo một hàng với `o = null`, do đó `o.id IS NULL` đúng.

**Chú ý:** ví dụ giả định `PurchaseOrder.id` là khóa chính không null theo mapping. Nếu kiểm tra một field child vốn có thể null, điều kiện `o.someNullableField IS NULL` có thể giữ cả child thật với field null, gây sai ý nghĩa “không có child”.

### 14.1. Cách viết bằng `IS EMPTY`

JPQL có cú pháp kiểm tra collection:

```sql
SELECT c
FROM Customer c
WHERE c.orders IS EMPTY
ORDER BY c.id
```

Cách này thường ngắn gọn hơn nếu mục tiêu chỉ là kiểm tra **collection rỗng**, không cần projection dữ liệu order.

### 14.2. Cách viết bằng `NOT EXISTS`

Một lựa chọn khác:

```sql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
)
ORDER BY c.id
```

`NOT EXISTS` có thể phù hợp khi yêu cầu phủ định phức tạp hoặc khi muốn tránh nhân bản row của parent. Cách SQL thực thi và hiệu năng cần đo theo dữ liệu, index và query plan; không có kết luận chung rằng `LEFT JOIN ... IS NULL` luôn nhanh hơn `NOT EXISTS` hoặc ngược lại.

### 14.3. Tìm customer không có order PAID

Yêu cầu khác với “không có bất kỳ order nào”:

```sql
SELECT c
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
WHERE o.id IS NULL
ORDER BY c.id
```

Với `:paid = PAID`, kết quả:

```text
Bình: không có order
Chi: chỉ có order CANCELLED
```

An và Dũng bị loại vì đã có order PAID.

Cũng có thể viết bằng correlated NOT EXISTS:

```sql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
ORDER BY c.id
```

Đây là một ví dụ quan trọng: khi phủ định một loại child cụ thể, phải đặt điều kiện `status` **trong tập child cần xem xét**, không chỉ thêm `OR o IS NULL` vào WHERE một cách máy móc.

## 15. `EXISTS` khi chỉ cần biết association có tồn tại

Yêu cầu: **Chỉ lấy customer có ít nhất một order PAID**.

Cách INNER JOIN:

```sql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :paid
```

Cách `EXISTS`:

```sql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
```

Cả hai biểu diễn yêu cầu từ dữ liệu mẫu: An và Dũng.

`EXISTS` thể hiện trực tiếp câu hỏi “có tồn tại ít nhất một order hay không?”. Nó không cần tạo nhiều kết hợp ở projection parent rồi khử trùng. Database optimizer có thể chuyển truy vấn thành semi-join hoặc chiến lược khác tùy dialect và chỉ số.

Khi chỉ cần một giá trị boolean “có hay không”, đừng tự động dùng `JOIN FETCH` để tải cả collection; làm vậy có thể tốn bộ nhớ mà không giúp trả lời yêu cầu.

---

## 16. Đếm order cho mọi customer: LEFT JOIN + `COUNT` + `GROUP BY`

Yêu cầu báo cáo:

> Hiển thị tên mọi khách hàng và số đơn họ đã đặt, kể cả khách hàng có **0 đơn**.

JPQL:

```sql
SELECT c.id, c.name, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id, c.name
ORDER BY c.id
```

Kết quả:

| Customer | `COUNT(o)` |
|---|---:|
| An | 2 |
| Bình | 0 |
| Chi | 1 |
| Dũng | 1 |

### 16.1. Vì sao `COUNT(o)` trả 0 cho Bình?

LEFT JOIN giữ một hàng kết hợp `(Bình, null)`, nhưng `COUNT(o)` **không đếm giá trị null**. Do đó số order của Bình là 0.

Cẩn thận với:

```sql
SELECT c.id, COUNT(c)
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id
```

`COUNT(c)` đếm biểu thức `c` không-null trong các hàng kết hợp. Bình vẫn có **một hàng** được bảo toàn, nên `COUNT(c)` của Bình là 1, **không phải số đơn**.

Tương tự ở SQL:

- `COUNT(*)` đếm **hàng kết quả**, kể cả hàng đã được bảo toàn với child null.
- `COUNT(child.id)` đếm các child thực sự có giá trị ID.
- `COUNT(DISTINCT child.id)` hữu ích khi một phép join khác khiến cùng child xuất hiện lặp.

### 16.2. Constructor DTO cho kết quả đếm

```java
package com.example.jpql;

public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {}
```

Truy vấn:

```java
List<CustomerOrderCount> counts = em.createQuery(
    """
    SELECT NEW com.example.jpql.CustomerOrderCount(
        c.id,
        c.name,
        COUNT(o)
    )
    FROM Customer c
    LEFT JOIN c.orders o
    GROUP BY c.id, c.name
    ORDER BY c.id
    """,
    CustomerOrderCount.class
).getResultList();
```

Kết quả của JPQL `COUNT` có kiểu `Long`. DTO nhận `Long orderCount` là lựa chọn phù hợp.

### 16.3. Nếu dùng INNER JOIN để đếm thì sao?

```sql
SELECT c.id, c.name, COUNT(o)
FROM Customer c
JOIN c.orders o
GROUP BY c.id, c.name
ORDER BY c.id
```

Kết quả sẽ **không có Bình**. Vì trước khi `GROUP BY` thực hiện, INNER JOIN đã loại customer không có order. Không có group để hiển thị count 0.

**Muốn báo cáo bao gồm số 0, LEFT JOIN thường là lựa chọn trực tiếp nhất.**

## 17. Đếm chỉ order PAID nhưng vẫn giữ mọi customer

Yêu cầu:

> Mỗi khách hàng có bao nhiêu đơn PAID, kể cả khi số lượng bằng 0?

Cách rõ nghĩa:

```sql
SELECT c.id, c.name, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
GROUP BY c.id, c.name
ORDER BY c.id
```

Với `:paid = OrderStatus.PAID`:

| Customer | Số đơn PAID |
|---|---:|
| An | 1 |
| Bình | 0 |
| Chi | 0 |
| Dũng | 1 |

**Đừng chuyển predicate PAID xuống WHERE**:

```sql
-- Không phù hợp nếu muốn giữ những customer có 0 order PAID:
SELECT c.id, c.name, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o
WHERE o.status = :paid
GROUP BY c.id, c.name
```

Câu trên loại Bình và Chi trước khi nhóm nên không có hàng đếm 0 cho họ.

### 17.1. Tổng tiền các đơn PAID

```sql
SELECT c.id, c.name, SUM(o.total)
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
GROUP BY c.id, c.name
ORDER BY c.id
```

Khác với `COUNT`, khi không có giá trị `o.total` nào để cộng, `SUM(o.total)` thường trả **null**, không phải 0. Có thể diễn đạt mong muốn bằng `COALESCE`:

```sql
SELECT c.id, c.name, COALESCE(SUM(o.total), 0)
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
GROUP BY c.id, c.name
ORDER BY c.id
```

Khi dùng DTO với `BigDecimal`, cần bảo đảm kiểu literal số trong `COALESCE` được provider/database xử lý tương thích; với ứng dụng yêu cầu portability cao, kiểm tra kiểu kết quả của expression trong provider đang dùng hoặc xử lý `null` thành `BigDecimal.ZERO` ở tầng DTO.

### 17.2. Số parent có child và số child là hai chỉ số khác nhau

```sql
SELECT COUNT(DISTINCT c)
FROM Customer c
JOIN c.orders o
```

đếm **số khách hàng có ít nhất một order**, tức 3 trong dữ liệu mẫu.

Trong khi:

```sql
SELECT COUNT(o)
FROM Customer c
JOIN c.orders o
```

đếm **số order được join**, tức 4.

Chọn phép đếm theo **đại lượng nghiệp vụ thật sự**; không chọn theo số dòng JPQL nhìn có vẻ ngắn hơn.

---

## 18. `JOIN` thường và `JOIN FETCH` là hai mục đích khác nhau

Một câu hỏi thường gặp:

> Tôi đã viết `JOIN c.orders o` rồi, vậy `customer.getOrders()` chắc chắn đã được tải chưa?

**Không nên giả định như vậy.**

### 18.1. JOIN thông thường dùng để tạo kết hợp cho truy vấn

```sql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :paid
```

Join ở đây phục vụ việc **lọc customer** theo order. JPQL không yêu cầu một join thường phải khởi tạo đầy đủ thuộc tính collection `c.orders` của entity được trả về.

Nếu `orders` có `fetch = LAZY`, collection vẫn có thể được tải về sau tùy provider, persistence context và nhu cầu truy cập.

### 18.2. `JOIN FETCH` yêu cầu tải association cùng entity nguồn

```sql
SELECT DISTINCT c
FROM Customer c
JOIN FETCH c.orders
```

Đây là **inner fetch join**: truy vấn nhắm tới việc lấy customer **cùng orders**. Vì là INNER JOIN, customer không có order — Bình — có thể bị loại khỏi kết quả.

`LEFT JOIN FETCH`:

```sql
SELECT DISTINCT c
FROM Customer c
LEFT JOIN FETCH c.orders
```

là **left fetch join**: có thể trả về cả Bình và yêu cầu nạp collection order của những customer kết quả.

### 18.3. So sánh bốn kiểu diễn đạt

| JPQL | Giữ customer không có order? | Có yêu cầu fetch collection? |
|---|---|---|
| `JOIN c.orders o` | Không. | Không. |
| `LEFT JOIN c.orders o` | Có. | Không. |
| `JOIN FETCH c.orders` | Không. | Có. |
| `LEFT JOIN FETCH c.orders` | Có. | Có. |

Fetch strategy của entity mapping và quyết định provider có thể còn tác động tới SQL phụ, nhưng khác biệt về **mục đích truy vấn** vẫn là như vậy.

### 18.4. Fetch join không nên bị dùng để lọc nội dung collection một cách tùy tiện

Một ý tưởng dễ gây nhầm:

```sql
-- Không phải kiểu JPQL fetch join portable nên sao chép tùy ý:
SELECT c
FROM Customer c
LEFT JOIN FETCH c.orders o
WHERE o.status = :paid
```

Trong JPQL chuẩn, fetch join có những hạn chế về identification variable của phía được fetch; alias và điều kiện lọc phần tử trực tiếp trên fetch join không phải mô hình portable để tạo “collection chỉ chứa các order PAID”. Một số provider có extension, nhưng hành vi có thể dẫn đến **collection bị nạp thiếu một phần** mà code tưởng là toàn bộ.

Nếu cần **lọc customer** theo order PAID nhưng vẫn load **toàn bộ** orders:

- Dùng truy vấn xác định customer ID phù hợp.
- Sau đó fetch collection cần thiết cho các ID đó, hoặc dùng entity graph/batch fetching phù hợp.
- Nếu chỉ cần order PAID trong API, dùng DTO projection từ join có predicate thay vì cố tạo entity collection không đầy đủ.

### 18.5. `JOIN FETCH` có thể làm số hàng SQL tăng

An có hai đơn, do đó SQL join để fetch collection có thể trả hai hàng cho An. Provider phải tập hợp chúng thành entity Customer và collection tương ứng.

Hệ quả:

- Kết quả SQL có thể lớn hơn số Customer.
- Khi fetch nhiều collection 1–N cùng lúc, số hàng có thể **nhân bội**.
- Có thể làm tiêu tốn memory và thời gian truyền dữ liệu.
- `DISTINCT` không luôn giúp giảm toàn bộ số hàng SQL khi các cột child khác nhau.

`JOIN FETCH` là công cụ tối ưu theo **nhu cầu đọc cụ thể**, không phải lựa chọn mặc định mọi lúc.

## 19. Phân trang với JOIN và JOIN FETCH

### 19.1. Một vấn đề cơ bản: phân trang theo row hay theo parent?

Giả sử truy vấn:

```sql
SELECT c
FROM Customer c
LEFT JOIN c.orders o
ORDER BY c.id
```

được áp `setMaxResults(2)`. Về mặt phép join, An xuất hiện ở hai hàng đầu tiên:

```text
(An, 101)
(An, 102)
(Bình, NULL)
(Chi, 103)
(Dũng, 104)
```

Nếu giới hạn ở tầng SQL row trước khi khử trùng entity, một trang có thể chỉ thể hiện An chứ không phải hai customer. Provider/JPA có thể xử lý các chi tiết phân trang và khử trùng khác nhau tùy truy vấn, nhưng **không nên suy luận phân trang collection join tương đương phân trang tập parent**.

### 19.2. Collection fetch join và pagination đặc biệt cần cẩn thận

Một truy vấn dạng:

```java
em.createQuery(
    """
    SELECT DISTINCT c
    FROM Customer c
    LEFT JOIN FETCH c.orders
    ORDER BY c.id
    """,
    Customer.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

có thể dẫn tới kết quả phân trang không như mong đợi, provider xử lý trong bộ nhớ hoặc cảnh báo, vì mỗi customer có thể tạo nhiều SQL rows.

### 19.3. Chiến lược hai bước thường dễ kiểm soát hơn

**Bước 1:** Chọn trang customer theo ID, không fetch join collection:

```java
List<Long> pageIds = em.createQuery(
    """
    SELECT c.id
    FROM Customer c
    ORDER BY c.id
    """,
    Long.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
```

**Bước 2:** Tải những customer đó cùng collection:

```java
List<Customer> customers = em.createQuery(
    """
    SELECT DISTINCT c
    FROM Customer c
    LEFT JOIN FETCH c.orders
    WHERE c.id IN :ids
    """,
    Customer.class
)
.setParameter("ids", pageIds)
.getResultList();
```

Cần lưu ý:

- Nếu `pageIds` rỗng, trả empty result, không tự tạo `IN ()` vì một số database không hỗ trợ cú pháp đó.
- Truy vấn `IN :ids` không bảo đảm giữ nguyên thứ tự của danh sách ID đầu vào. Sắp xếp lại theo `pageIds` hoặc thêm `ORDER BY` phù hợp.
- Nếu các transaction khác thay dữ liệu giữa hai query, kết quả có thể không phản ánh một snapshot tuyệt đối nhất quán; chọn isolation/transaction phù hợp yêu cầu.
- Nếu trang quá lớn, cân nhắc giới hạn kích thước `IN` và batch fetching.

### 19.4. Khi chỉ cần thống kê, đừng fetch cả graph

Nếu màn hình chỉ cần số đơn, truy vấn `COUNT(o) GROUP BY c` thường nhẹ hơn tải hàng nghìn `PurchaseOrder` rồi gọi `customer.getOrders().size()` ở Java. Phải chọn giữa **entity graph** và **projection** theo dữ liệu thực sự cần hiển thị.

---

## 20. N+1 queries: JOIN lọc dữ liệu không nhất thiết đã giải quyết vấn đề

Giả sử:

```java
List<Customer> customers = em.createQuery(
    "SELECT c FROM Customer c",
    Customer.class
).getResultList();

for (Customer c : customers) {
    System.out.println(c.getOrders().size());
}
```

Với `orders` LAZY, provider có thể phát:

```sql
SELECT * FROM customers; -- 1 query

SELECT * FROM purchase_orders WHERE customer_id = 1;
SELECT * FROM purchase_orders WHERE customer_id = 2;
SELECT * FROM purchase_orders WHERE customer_id = 3;
SELECT * FROM purchase_orders WHERE customer_id = 4;
-- Có thể thành N query bổ sung.
```

Đây là một dạng **N+1 query problem**.

Một ý tưởng chỉ thay bằng:

```sql
SELECT DISTINCT c
FROM Customer c
LEFT JOIN c.orders o
```

không có `FETCH` thì **không đảm bảo collection được khởi tạo**. Để tải orders một cách có chủ đích, dùng `LEFT JOIN FETCH`, entity graph, batch fetching hoặc một DTO query tùy mục tiêu.

### 20.1. `LEFT JOIN FETCH` không phải lúc nào cũng tối ưu hơn

Khi mỗi customer có hàng trăm order:

- Một SQL fetch join có thể trả nhiều rows.
- Cần bộ nhớ lớn để tái tạo object graph.
- Không phù hợp với một API chỉ muốn hiển thị tên và tổng số order.
- Có thể gây khó khăn với phân trang.

Đôi khi một aggregate query với LEFT JOIN + COUNT, hoặc hai query có batch fetch, là lựa chọn tốt hơn.

### 20.2. Mục tiêu phải được phát biểu trước truy vấn

| Mục tiêu | Loại truy vấn gợi ý |
|---|---|
| Lọc customer có order | `INNER JOIN` + `DISTINCT`, hoặc `EXISTS`. |
| Giữ mọi customer, kèm order ID nếu có | `LEFT JOIN` + DTO tuple. |
| Đếm order, gồm customer có 0 | `LEFT JOIN` + `COUNT(o)` + `GROUP BY`. |
| Trả entity Customer đã tải orders | `LEFT JOIN FETCH` nếu cần cả customer không có order. |
| Chọn 20 customer trên một trang, có orders | Phân trang ID trước, fetch associations sau. |
| Kiểm tra không có order PAID | `NOT EXISTS` hoặc `LEFT JOIN ... ON ... WHERE o.id IS NULL`. |

## 21. Criteria API: `JoinType.INNER` và `JoinType.LEFT`

JPQL có thể được xây dựng bằng Criteria API để tạo truy vấn động. Khác biệt INNER/LEFT vẫn giữ nguyên.

### 21.1. Criteria INNER JOIN

```java
import jakarta.persistence.criteria.*;
import java.util.List;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Customer> query =
        cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

Join<Customer, PurchaseOrder> order =
        customer.join("orders", JoinType.INNER);

query.select(customer)
        .distinct(true)
        .where(cb.equal(
            order.get("status"),
            OrderStatus.PAID
        ));

List<Customer> customers =
        em.createQuery(query).getResultList();
```

Tương đương về ý nghĩa với:

```sql
SELECT DISTINCT c
FROM Customer c
INNER JOIN c.orders o
WHERE o.status = :paid
```

Nếu một customer không có order PAID, customer đó không nằm trong kết quả.

### 21.2. Criteria LEFT JOIN và đếm orders

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Tuple> query =
        cb.createTupleQuery();

Root<Customer> customer = query.from(Customer.class);

Join<Customer, PurchaseOrder> order =
        customer.join("orders", JoinType.LEFT);

query.multiselect(
        customer.get("id").alias("customerId"),
        customer.get("name").alias("customerName"),
        cb.count(order).alias("orderCount")
);

query.groupBy(
        customer.get("id"),
        customer.get("name")
);

query.orderBy(cb.asc(customer.get("id")));

List<Tuple> rows = em.createQuery(query).getResultList();

for (Tuple row : rows) {
    Long id = row.get("customerId", Long.class);
    String name = row.get("customerName", String.class);
    Long count = row.get("orderCount", Long.class);

    System.out.println(id + " " + name + " " + count);
}
```

Ý nghĩa giống JPQL LEFT JOIN + COUNT. Để có số đếm 0, `cb.count(order)` đếm các giá trị order không-null, không phải số hàng sau join.

### 21.3. Criteria `Join.on(...)` thay cho predicate WHERE ở join ngoài

Muốn giữ mọi customer nhưng chỉ join order PAID:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> query = cb.createTupleQuery();

Root<Customer> customer = query.from(Customer.class);

Join<Customer, PurchaseOrder> order =
        customer.join("orders", JoinType.LEFT);

order.on(
    cb.equal(order.get("status"), OrderStatus.PAID)
);

query.multiselect(
    customer.get("id").alias("customerId"),
    cb.count(order).alias("paidOrders")
);

query.groupBy(customer.get("id"));

List<Tuple> counts = em.createQuery(query).getResultList();
```

`order.on(...)` gắn predicate vào **join condition**, giúp giữ customer không có order thỏa.

Nếu thay bằng:

```java
query.where(
    cb.equal(order.get("status"), OrderStatus.PAID)
);
```

thì đó là **WHERE predicate**, có nguy cơ loại các customer có 0 order PAID như đã phân tích.

### 21.4. Cẩn thận khi dùng Criteria `fetch()`

Criteria API cũng có:

```java
customer.fetch("orders", JoinType.LEFT);
```

Khác với `customer.join(...)`:

- `fetch` yêu cầu tải association.
- `join` tạo đường dẫn join cho predicate/projection.
- Không nên ép kiểu `Fetch` sang `Join` để dùng alias/filter nếu điều đó phụ thuộc provider.
- Với collection fetch join, vẫn có rủi ro trùng parent rows và pagination như JPQL.

## 22. Nối nhiều quan hệ liên tiếp: đặt đúng LEFT ở mỗi tầng

Xét một mô hình mở rộng:

```text
Customer
  |
  +-- orders
         |
         +-- lines
                |
                +-- product
```

Một truy vấn:

```sql
SELECT c, o, l
FROM Customer c
LEFT JOIN c.orders o
INNER JOIN o.lines l
```

có thể **không giữ được customer không có order**, vì sau LEFT JOIN đầu tiên, alias `o` của Bình là null; INNER JOIN tiếp theo yêu cầu `o.lines` có phần tử phù hợp.

Để giữ những parent thiếu association ở các tầng:

```sql
SELECT c, o, l
FROM Customer c
LEFT JOIN c.orders o
LEFT JOIN o.lines l
```

Khi đó:

- Customer không có order vẫn có thể được giữ với `o = null` và `l = null`.
- Order không có line vẫn có thể được giữ với `l = null`.
- Order có nhiều line tạo thêm nhiều rows.

### 22.1. Một INNER JOIN phía sau có thể phá hiệu ứng giữ null trước đó

Đây là bẫy khi query có nhiều lớp:

```text
Customer --LEFT--> Order --INNER--> Line
```

Không thể chỉ đọc từ khóa LEFT đầu tiên rồi kết luận “mọi customer chắc chắn được giữ”. Phải xem **toàn chuỗi join**, điều kiện `ON`/`WHERE` và sự tồn tại của quan hệ ở mỗi bước.

### 22.2. Nhiều collection có thể nhân bội hàng

Nếu một customer có:

- 3 orders.
- 4 addresses trong một collection độc lập.

Truy vấn:

```sql
SELECT c, o, a
FROM Customer c
LEFT JOIN c.orders o
LEFT JOIN c.addresses a
```

có thể tạo **3 × 4 = 12 kết hợp** cho customer đó khi cả hai collection đều có nhiều phần tử.

Hậu quả:

- `COUNT(o)` có thể đếm order bị lặp theo số address.
- `COUNT(a)` có thể đếm address bị lặp theo số order.
- `SUM(o.total)` có thể bị nhân bội.
- Fetch join nhiều collections có thể tăng mạnh số rows.

Giải pháp tùy use case:

- Đếm `COUNT(DISTINCT o)` khi phù hợp.
- Dùng query riêng cho từng collection.
- Dùng subquery/aggregation đúng grain dữ liệu.
- Chỉ fetch associations thật sự cần thiết.

**Không cho rằng `LEFT JOIN` là cách an toàn để nối càng nhiều collection càng tốt.**

## 23. INNER/LEFT JOIN với `@ManyToMany` và `@ElementCollection`

### 23.1. Ví dụ người dùng và vai trò

```java
@ManyToMany
@JoinTable(
    name = "user_roles",
    joinColumns = @JoinColumn(name = "user_id"),
    inverseJoinColumns = @JoinColumn(name = "role_id")
)
private Set<Role> roles = new HashSet<>();
```

Để tìm user có role nào đó:

```sql
SELECT DISTINCT u
FROM AppUser u
JOIN u.roles r
WHERE r.name = :roleName
```

Để liệt kê **mọi user** và số role:

```sql
SELECT u.id, COUNT(r)
FROM AppUser u
LEFT JOIN u.roles r
GROUP BY u.id
```

Dù quan hệ dùng join table SQL, JPQL vẫn tham chiếu **`u.roles`**; provider tự nối qua bảng liên kết.

### 23.2. Ví dụ `@ElementCollection`

Một customer có nhiều email phụ:

```java
@ElementCollection
@CollectionTable(
    name = "customer_other_emails",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "email")
private Set<String> otherEmails = new HashSet<>();
```

JPQL:

```sql
SELECT c.id, e
FROM Customer c
LEFT JOIN c.otherEmails e
```

Với customer không có email phụ, `e` có thể là null trong một hàng được bảo toàn. `e` là **giá trị cơ bản** `String`, không phải entity có `id`.

Cũng có thể join collection embeddable:

```java
@ElementCollection
private Set<AddressValue> addresses;
```

```sql
SELECT c
FROM Customer c
JOIN c.addresses a
WHERE a.city = :city
```

Alias `a` là phần tử embeddable và `a.city` là thuộc tính của nó. Cần phân biệt JOIN element collection với JOIN giữa các entity có identity độc lập.

### 23.3. `Map` với key/value

Giả sử:

```java
@ElementCollection
@CollectionTable(name = "customer_labels")
@MapKeyColumn(name = "label_key")
@Column(name = "label_value")
private Map<String, String> labels = new HashMap<>();
```

JPQL có thể join vào map:

```sql
SELECT c.id, KEY(m), VALUE(m)
FROM Customer c
LEFT JOIN c.labels m
```

Trong đó:

- `KEY(m)` truy cập Map key.
- `VALUE(m)` truy cập Map value.
- Với customer không có map entry, biểu thức thuộc alias join có thể null.

Không thể suy ra kết quả Map có thứ tự ổn định chỉ vì query có LEFT JOIN; nếu cần thứ tự, dùng `ORDER BY` tường minh trên key/value phù hợp.

## 24. INNER/LEFT JOIN khi mối quan hệ đơn trị có thể null

Không phải mọi association là collection.

Ví dụ:

```java
@Entity
public class SupportTicket {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "assignee_id")
    private SupportAgent assignee;
}
```

Nếu ticket chưa có agent, `assignee` bằng null.

### 24.1. INNER JOIN

```sql
SELECT t.id, a.name
FROM SupportTicket t
INNER JOIN t.assignee a
```

Chỉ lấy ticket đã có assignee phù hợp. Ticket chưa được phân công sẽ bị loại.

### 24.2. LEFT JOIN

```sql
SELECT t.id, a.name
FROM SupportTicket t
LEFT JOIN t.assignee a
```

Lấy mọi ticket, kể cả ticket chưa có agent; các ticket đó trả `a.name = null`.

Ở đây, vì `assignee` là **single-valued association**, mỗi ticket tối đa có một agent, nên JOIN không tự nhân bản ticket theo collection này. Điều đó khác với `Customer.orders` một-nhiều.

### 24.3. Khi FK bắt buộc, INNER và LEFT có thể giống kết quả

Nếu `@ManyToOne(optional = false)` đi cùng FK `NOT NULL` và dữ liệu thỏa toàn vẹn tham chiếu, mỗi order đều có customer. Trong trường hợp đó:

```sql
FROM PurchaseOrder o JOIN o.customer c
```

và:

```sql
FROM PurchaseOrder o LEFT JOIN o.customer c
```

có thể cho tập order giống nhau. Nhưng đây là hệ quả của **constraint và dữ liệu**, không phải hai loại JOIN luôn đồng nghĩa.

---

## 25. `JOIN ... ON` không dùng để thay thế tùy tiện relationship mapping

Trong SQL thuần, ta quen viết:

```sql
SELECT c.*, o.*
FROM customers c
LEFT JOIN purchase_orders o
  ON o.customer_id = c.id;
```

Trong JPQL khi có association:

```sql
SELECT c, o
FROM Customer c
LEFT JOIN c.orders o
```

Provider đã biết điều kiện join từ `mappedBy`, `@JoinColumn` và mapping. `ON` trong JPQL thường bổ sung **điều kiện hạn chế join**:

```sql
LEFT JOIN c.orders o ON o.status = :paid
```

chứ không cần lặp lại FK.

### 25.1. Nếu hai entity không có association thì sao?

Ví dụ `Customer` và `ExternalEvent` không được liên kết bằng relationship field. Không thể tùy tiện giả định mọi JPQL version/provider đều chấp nhận cú pháp SQL-style:

```sql
-- Không nên coi đây là portable JPQL cho mọi phiên bản:
FROM Customer c LEFT JOIN ExternalEvent e ON e.customerCode = c.code
```

Khả năng entity/range joins không dựa trên association phụ thuộc phiên bản Jakarta Persistence và provider. Với mức portability cơ bản, có thể:

- Khai báo association mapping nếu đó là quan hệ domain thực sự.
- Dùng nhiều range variables với điều kiện WHERE cho một **inner/cross join** tương đương khi phù hợp.
- Dùng native SQL, database view hoặc DTO/query riêng khi thật sự cần outer join giữa những nguồn không có association.
- Kiểm tra chính xác khả năng của phiên bản JPQL/provider đang dùng.

Ví dụ điều kiện kết hợp nhiều root:

```sql
SELECT c, e
FROM Customer c, ExternalEvent e
WHERE e.customerCode = c.code
```

Cách này có ý nghĩa giống một cross join được lọc thành các cặp phù hợp; nó **không bảo toàn customer không có event** như LEFT JOIN.

### 25.2. Entity name không phải table name

```java
@Entity(name = "Buyer")
@Table(name = "customers")
public class Customer {
    // ...
}
```

Khi đó query dùng entity name `Buyer`:

```sql
SELECT b
FROM Buyer b
LEFT JOIN b.orders o
```

chứ không dùng `FROM customers` nếu đó chỉ là tên bảng SQL. Tương tự, `b.orders` là tên thuộc tính Java, không phải `purchase_orders`.

## 26. Null semantics: tại sao một so sánh tưởng đơn giản có thể loại hàng?

SQL và JPQL có khái niệm **NULL** biểu diễn thiếu giá trị và dùng logic ba giá trị trong predicate:

- TRUE.
- FALSE.
- UNKNOWN.

Khi LEFT JOIN không tìm được child, những biểu thức truy cập alias child thường là null. Biểu thức:

```sql
o.status = :paid
```

trên hàng `o = null` không phải TRUE, mà là UNKNOWN trong ngữ nghĩa so sánh với null. Điều kiện `WHERE` chỉ giữ TRUE.

### 26.1. `IS NULL` khác `= NULL`

Đúng:

```sql
WHERE o.id IS NULL
```

Không nên viết:

```sql
WHERE o.id = NULL
```

vì `= NULL` không kiểm tra giá trị thiếu theo logic SQL/JPQL như mong muốn.

### 26.2. `COALESCE` trong projection

Ví dụ:

```sql
SELECT c.name, COALESCE(o.status, :fallback)
FROM Customer c
LEFT JOIN c.orders o
```

Với Bình, có thể sử dụng giá trị fallback trong projection. Khi dùng enum, phải bảo đảm type của `:fallback` và expression tương thích với provider.

Nhưng:

```sql
WHERE COALESCE(o.status, :fallback) = :paid
```

là một **predicate lọc kết quả**, và có thể tiếp tục thay đổi parent nào được giữ. `COALESCE` không tự biến mọi LEFT JOIN + WHERE thành logic “giữ tất cả”.

### 26.3. `NULL` của field child khác `NULL` do không có child

Một order có thật có thể có field tùy chọn null. Khi truy vấn:

```sql
WHERE o.optionalNote IS NULL
```

kết quả có thể chứa:

1. Customer không có order, nên alias `o` null.
2. Customer có order nhưng `optionalNote` null.

Nếu mục tiêu là “không có order”, kiểm tra khóa chính không-null của child `o.id IS NULL` hoặc dùng `IS EMPTY`/`NOT EXISTS`. Không kiểm tra một field tùy chọn bất kỳ.

## 27. `ORDER BY` trên thuộc tính child cũng cần nghĩ tới null và trùng hàng

Truy vấn:

```sql
SELECT c.name, o.id
FROM Customer c
LEFT JOIN c.orders o
ORDER BY c.name, o.id
```

là một cách để kết quả dễ kiểm tra. Tuy nhiên, SQL dialect khác nhau có thể sắp xếp `NULL` trước hoặc sau theo quy tắc mặc định.

Nếu ứng dụng cần thứ tự nhất quán, phải định nghĩa đủ tiêu chí sắp xếp phù hợp và kiểm tra mức hỗ trợ của database/provider; không dựa vào thứ tự trả hàng ngẫu nhiên.

### 27.1. `ORDER BY o.id` có thể lặp customer

Dù `SELECT DISTINCT c`, việc sắp xếp theo thuộc tính `o.id` khi một customer có nhiều order có thể tạo xung đột về ngữ nghĩa: customer An có hai giá trị `o.id`, vậy thứ tự duy nhất của An nên theo order nào?

Với danh sách **customer duy nhất**, nên chọn tiêu chí sắp xếp thuộc customer (`c.id`, `c.name`) hoặc một aggregate xác định rõ (`MAX(o.createdAt)` nếu mô hình có timestamp). Không tùy tiện `ORDER BY` một field child đa trị để sắp xếp parent.

## 28. Truy vấn nhiều điều kiện: thứ tự tư duy giúp tránh lỗi

Giả sử yêu cầu:

> Trả mọi khách hàng có tên bắt đầu bằng “A”, kèm các order PAID có tổng tiền trên 200000, nếu có.

Một cách diễn đạt:

```sql
SELECT c.name, o.id, o.total
FROM Customer c
LEFT JOIN c.orders o
    ON o.status = :paid
   AND o.total > :minimum
WHERE c.name LIKE :prefix
ORDER BY c.id, o.id
```

Tham số:

```java
.setParameter("paid", OrderStatus.PAID)
.setParameter("minimum", new BigDecimal("200000.00"))
.setParameter("prefix", "A%")
```

Diễn giải từng bước:

1. `FROM Customer c` tạo tập customer gốc.
2. `LEFT JOIN c.orders o ON ...` chỉ nối những order **vừa PAID vừa đủ tổng tiền**.
3. Customer không có order thỏa vẫn có một hàng với `o = null`.
4. `WHERE c.name LIKE :prefix` lọc danh sách customer theo yêu cầu tên.
5. `ORDER BY` định nghĩa thứ tự kết quả.

Nếu chuyển `o.total > :minimum` vào WHERE, những customer không có order đủ điều kiện sẽ bị loại, không còn đúng yêu cầu *kèm order nếu có*.

### 28.1. Hỏi hai câu trước khi viết predicate

- Predicate này lọc **parent nào được phép xuất hiện**? Nếu có, nó thường thuộc `WHERE`.
- Hay predicate này chỉ xác định **child nào được nối, còn parent vẫn phải xuất hiện**? Nếu có, nó thường thuộc `ON` của LEFT JOIN.

Cách phân biệt này không bao phủ mọi truy vấn phức tạp, nhưng giúp tránh phần lớn lỗi JOIN khi xây dashboard/report.

---

## 29. Hiệu năng: loại JOIN ảnh hưởng nhưng không quyết định toàn bộ tốc độ

Không có quy tắc phổ quát rằng `INNER JOIN` luôn nhanh hơn `LEFT JOIN` trong mọi database, hoặc ngược lại. Query optimizer có thể:

- Chọn hash join, nested loop hoặc merge join.
- Đảo thứ tự thao tác trong giới hạn semantics cho phép.
- Loại bỏ join không cần thiết.
- Biến đổi một LEFT JOIN thành INNER JOIN khi predicate WHERE bảo đảm không thể giữ row null.
- Dùng index scan hoặc full scan tùy kích thước dữ liệu.

Vì vậy, chọn INNER/LEFT trước hết theo **kết quả nghiệp vụ**, sau đó đo và tối ưu bằng query plan thực tế.

### 29.1. Index cho foreign key

Trong mô hình khách hàng–đơn hàng, đường join thường qua:

```sql
purchase_orders.customer_id = customers.id
```

Index trên `purchase_orders.customer_id` thường có ích khi lấy orders theo customer:

```sql
CREATE INDEX ix_orders_customer_id
ON purchase_orders(customer_id);
```

Không phải mọi RDBMS tự tạo index cho foreign key; cần kiểm tra schema. Nếu đã có composite index bắt đầu bằng `customer_id`, thêm index trùng lặp có thể không cần thiết.

### 29.2. Index cho bộ lọc child

Nếu thường truy vấn:

```sql
LEFT JOIN c.orders o ON o.status = :paid
```

ở mức SQL, có thể đánh giá index kết hợp như:

```sql
CREATE INDEX ix_orders_customer_status
ON purchase_orders(customer_id, status);
```

Nhưng lựa chọn thứ tự cột index phụ thuộc query pattern, độ chọn lọc, nhóm dữ liệu và database optimizer. Không tự kết luận index ghép này luôn tốt hơn index theo `status` hoặc theo `customer_id`.

### 29.3. Phân biệt SQL rows và Java entity objects

Một query LEFT JOIN có thể trả hàng nghìn SQL rows cho vài chục parent. Khi projection trả entity, persistence context thường giữ **một managed object cho một entity identity**. Điều đó không làm chi phí truyền/hydrate xử lý các hàng JOIN biến mất.

Đối với API danh sách nhiều dữ liệu:

- Chỉ select những field cần dùng bằng DTO projection.
- Tránh fetch join collection không liên quan.
- Tránh join nhiều collections độc lập.
- Xem query plan thực tế và thời gian thực thi.
- Kiểm soát giới hạn trang và kích thước response.

### 29.4. Kiểm soát N+1 riêng với việc chọn INNER/LEFT

Một query JPQL dùng `JOIN` để lọc có thể vẫn gặp N+1 khi code sau đó truy cập collection LAZY. Ngược lại, fetch join có thể loại N+1 ở use case cụ thể nhưng tạo vấn đề số SQL rows lớn. Cần tối ưu theo workload, không chỉ tìm một từ khóa JOIN “tốt nhất”.

## 30. Một ví dụ thực hành với dữ liệu cố định

### 30.1. Tạo dữ liệu bằng JPA

Giả sử `EntityManagerFactory emf` đã cấu hình cho persistence unit dùng resource-local transaction và entity `Customer`, `PurchaseOrder`.

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer an = new Customer("An");
    an.addOrder(new PurchaseOrder(
        OrderStatus.PAID,
        new BigDecimal("300000.00")
    ));
    an.addOrder(new PurchaseOrder(
        OrderStatus.DRAFT,
        new BigDecimal("100000.00")
    ));

    Customer binh = new Customer("Bình");
    // Không có order.

    Customer chi = new Customer("Chi");
    chi.addOrder(new PurchaseOrder(
        OrderStatus.CANCELLED,
        new BigDecimal("70000.00")
    ));

    Customer dung = new Customer("Dũng");
    dung.addOrder(new PurchaseOrder(
        OrderStatus.PAID,
        new BigDecimal("250000.00")
    ));

    em.persist(an);
    em.persist(binh);
    em.persist(chi);
    em.persist(dung);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Các ID trong database sẽ do generator cấp và **không nhất thiết là 1,2,3,4**. Những ID được dùng ở phần đầu bài chỉ là dữ liệu bảng minh họa dễ theo dõi.

### 30.2. Chạy truy vấn INNER JOIN

```java
EntityManager em = emf.createEntityManager();

try {
    List<Customer> result = em.createQuery(
        """
        SELECT DISTINCT c
        FROM Customer c
        JOIN c.orders o
        ORDER BY c.name
        """,
        Customer.class
    ).getResultList();

    for (Customer c : result) {
        System.out.println(c.getName());
    }
} finally {
    em.close();
}
```

Kỳ vọng tên:

```text
An
Chi
Dũng
```

### 30.3. Chạy truy vấn LEFT JOIN

```java
EntityManager em = emf.createEntityManager();

try {
    List<Customer> result = em.createQuery(
        """
        SELECT DISTINCT c
        FROM Customer c
        LEFT JOIN c.orders o
        ORDER BY c.name
        """,
        Customer.class
    ).getResultList();

    for (Customer c : result) {
        System.out.println(c.getName());
    }
} finally {
    em.close();
}
```

Kỳ vọng tên:

```text
An
Bình
Chi
Dũng
```

### 30.4. Chạy phép đếm PAID bằng ON

```java
EntityManager em = emf.createEntityManager();

try {
    List<Object[]> counts = em.createQuery(
        """
        SELECT c.name, COUNT(o)
        FROM Customer c
        LEFT JOIN c.orders o ON o.status = :paid
        GROUP BY c.id, c.name
        ORDER BY c.name
        """,
        Object[].class
    )
    .setParameter("paid", OrderStatus.PAID)
    .getResultList();

    for (Object[] row : counts) {
        String name = (String) row[0];
        Long paidCount = (Long) row[1];

        System.out.println(name + ": " + paidCount);
    }
} finally {
    em.close();
}
```

Kỳ vọng:

```text
An: 1
Bình: 0
Chi: 0
Dũng: 1
```

Cần chú ý các ví dụ test/seed trong hệ thống thật phải có cơ chế dọn dữ liệu, tránh phụ thuộc thứ tự identity được cấp, và dùng database/schema test cô lập.

## 31. Integration tests: kiểm tra cả trường hợp không có quan hệ

Một truy vấn JOIN không nên chỉ được test trên dữ liệu có đầy đủ child, vì khi đó INNER và LEFT đôi khi cho cùng kết quả nên lỗi bị che khuất.

### 31.1. Test INNER JOIN loại customer không có order

Với fixture như phần 30:

```java
@Test
void innerJoinReturnsOnlyCustomersWithOrders() {
    List<String> names = em.createQuery(
        """
        SELECT DISTINCT c.name
        FROM Customer c
        JOIN c.orders o
        ORDER BY c.name
        """,
        String.class
    ).getResultList();

    assertEquals(
        List.of("An", "Chi", "Dũng"),
        names
    );
}
```

### 31.2. Test LEFT JOIN giữ customer không có order

```java
@Test
void leftJoinKeepsCustomersWithoutOrders() {
    List<String> names = em.createQuery(
        """
        SELECT DISTINCT c.name
        FROM Customer c
        LEFT JOIN c.orders o
        ORDER BY c.name
        """,
        String.class
    ).getResultList();

    assertEquals(
        List.of("An", "Bình", "Chi", "Dũng"),
        names
    );
}
```

### 31.3. Test ON giữ customer không có order PAID

```java
@Test
void leftJoinOnConditionKeepsZeroPaidCount() {
    List<Object[]> rows = em.createQuery(
        """
        SELECT c.name, COUNT(o)
        FROM Customer c
        LEFT JOIN c.orders o ON o.status = :paid
        GROUP BY c.id, c.name
        ORDER BY c.name
        """,
        Object[].class
    )
    .setParameter("paid", OrderStatus.PAID)
    .getResultList();

    Map<String, Long> counts = new LinkedHashMap<>();

    for (Object[] row : rows) {
        counts.put((String) row[0], (Long) row[1]);
    }

    assertEquals(1L, counts.get("An"));
    assertEquals(0L, counts.get("Bình"));
    assertEquals(0L, counts.get("Chi"));
    assertEquals(1L, counts.get("Dũng"));
}
```

Các test dùng JUnit 5 `@Test` và `Assertions.assertEquals`; cùng `List`, `Map`, `LinkedHashMap` trong `java.util`.

**Điều quan trọng ở fixture:** có cả customer **không có order** (Bình) và customer **có order nhưng không có order PAID** (Chi). Nếu thiếu Chi, một truy vấn sai kiểu `LEFT JOIN ... WHERE o.status = PAID OR o IS NULL` có thể vẫn vượt test.

### 31.4. Test các edge case khác

Khi domain có nhiều association, nên kiểm tra:

- Parent có 0, 1 và nhiều child.
- Child có trạng thái khác điều kiện `ON`.
- Quan hệ single-valued có `null`.
- Nhiều quan hệ liên tiếp, trong đó association giữa chặng là null.
- Join hai collection tạo row multiplication.
- Thống kê `COUNT` bằng 0.
- Truy vấn phân trang không bị lặp parent ngoài mong đợi.
- Kết quả DTO cho alias child null không gây NPE.
- Join fetch có thật đáp ứng nhu cầu tải collection, không dựa vào việc provider tự động load ở một tình huống tình cờ.

## 32. Các lỗi thường gặp khi dùng INNER/LEFT JOIN

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Customer chưa có order biến mất | Dùng INNER JOIN thay vì LEFT JOIN. | Dùng LEFT JOIN nếu muốn giữ mọi customer. |
| Đã dùng LEFT JOIN nhưng customer chưa có order vẫn biến mất | `WHERE o.status = ...` loại các hàng có o = null. | Đưa bộ lọc child vào `ON` nếu phải giữ parent. |
| Thêm `OR o IS NULL` vẫn mất customer chỉ có order CANCELLED | LEFT JOIN không sinh hàng null khi đã có child không khớp điều kiện WHERE. | Dùng `LEFT JOIN ... ON status=...` hoặc `NOT EXISTS`. |
| Customer bị lặp nhiều lần | Join từ một parent tới nhiều child tạo nhiều hàng. | Dùng `DISTINCT c` nếu muốn parent duy nhất hoặc dùng aggregate phù hợp. |
| `DISTINCT c.id, o.id` vẫn có nhiều hàng cho một customer | DISTINCT xét toàn tuple, các order ID khác nhau. | Chọn đúng projection; chỉ `DISTINCT c` nếu cần entity duy nhất. |
| Báo cáo đếm order của customer trống thành 1 | Dùng `COUNT(c)` hoặc `COUNT(*)` sau LEFT JOIN. | Dùng `COUNT(o)` hoặc `COUNT(o.id)`. |
| Báo cáo mất các customer có 0 đơn PAID | Lọc `o.status` trong WHERE trước GROUP BY. | Dùng predicate ở `ON` của LEFT JOIN. |
| `SUM` không trả 0 cho customer không có order | SQL aggregate SUM trên tập toàn null trả null. | Dùng `COALESCE` hoặc xử lý null ở DTO. |
| `c.orders.status` không hợp lệ | `orders` là collection, không phải single-valued object. | `JOIN c.orders o` rồi dùng `o.status`. |
| JPQL báo không nhận diện `purchase_orders` | Dùng tên bảng SQL thay entity name. | Dùng `PurchaseOrder` và property path Java. |
| JPQL báo không nhận diện `customer_id` | Dùng tên FK column SQL trong JPQL path. | Dùng `o.customer` hoặc `c.orders`. |
| `SELECT c, o` gây NPE khi đọc order | Alias phía phải có thể null trong LEFT JOIN. | Xử lý null ở Java/DTO. |
| Join để lọc nhưng truy cập collection vẫn phát N+1 | JOIN thường không buộc fetch association. | Dùng fetch join/entity graph/batch/DTO tùy use case. |
| INNER FETCH JOIN làm mất customer chưa có order | INNER JOIN semantics vẫn áp dụng với fetch. | Dùng `LEFT JOIN FETCH` nếu cần giữ customer trống. |
| Dùng alias/predicate trên fetch join làm collection thiếu dữ liệu | Fetch join chuẩn có hạn chế; provider extension có thể load collection không đầy đủ. | Tách query lọc và query fetch; DTO nếu chỉ cần child đã lọc. |
| Phân trang join fetch trả ít parent hơn pageSize | JOIN collection nhân SQL rows, giới hạn row và entity khác nhau. | Phân trang parent ID rồi fetch trong bước hai. |
| Kết quả count/sum lớn bất thường | Join nhiều collections làm nhân bội kết hợp. | DISTINCT đúng chỗ, subquery, aggregate riêng hoặc query riêng. |
| Một INNER JOIN ở tầng sau làm mất parent của LEFT JOIN trước | Path tiếp theo yêu cầu object phía trước phải tồn tại. | Dùng LEFT JOIN xuyên suốt những association cần bảo toàn. |
| Lọc entity có association null bằng path traversal làm mất hàng | Implicit join có inner semantics. | Dùng LEFT JOIN tường minh khi cần giữ null. |
| `WHERE child.field IS NULL` chọn cả row có child | Field đó có thể null dù child tồn tại. | Kiểm tra child ID không-null hoặc dùng `NOT EXISTS`/`IS EMPTY`. |
| Chỉ đổi INNER sang LEFT mà báo cáo vẫn sai | Sai grain, predicate hoặc projection/aggregation. | Phân tích hàng trung gian trước khi GROUP BY, WHERE và DISTINCT. |
| JPQL custom ON không chạy ở provider cũ | Phiên bản JPQL/provider không hỗ trợ cú pháp mong muốn. | Kiểm tra phiên bản, dùng subquery/portable mapping hoặc native SQL. |
| Query chạy chậm khi LEFT JOIN nhiều child | Graph lớn, thiếu index, fetch không cần thiết. | Dùng projection, index FK, phân trang đúng grain và đo execution plan. |

## 33. Quy trình chọn loại JOIN trong một use case

Trước khi viết JPQL, trả lời lần lượt:

**Bước 1 — Entity nào là tập gốc?**

Ví dụ `Customer` là tập gốc nếu cần liệt kê mọi khách hàng. `PurchaseOrder` là tập gốc nếu cần liệt kê mọi đơn hàng.

**Bước 2 — Có phải giữ entity gốc ngay cả khi quan hệ trống không?**

- Không → `INNER JOIN` có thể phù hợp.
- Có → bắt đầu với `LEFT JOIN`.

**Bước 3 — Predicate đang lọc parent hay child được nối?**

- Lọc parent → thường `WHERE c...`.
- Chỉ chọn những child liên quan nhưng vẫn giữ parent → thường `ON o...` khi LEFT JOIN.

**Bước 4 — Kết quả là entity, tuple hay thống kê?**

- Parent duy nhất → `SELECT DISTINCT c` hoặc `EXISTS`.
- Parent-child rows → `SELECT c, o` / DTO.
- Đếm → `COUNT(child)` và `GROUP BY`.
- Kiểm tra không tồn tại → `IS EMPTY` hoặc `NOT EXISTS`.

**Bước 5 — Có cần nạp collection vào entity không?**

- Chỉ lọc/đếm → JOIN thường hoặc subquery.
- Cần entity graph đầy đủ → `JOIN FETCH`/entity graph theo use case.

**Bước 6 — Có phân trang hoặc join nhiều collections không?**

Nếu có, phân tích row multiplication. Không mặc định `setMaxResults` trên collection join fetch sẽ phân trang parent chính xác.

**Bước 7 — Kiểm thử với quan hệ trống và child không thỏa điều kiện.**

Hai trường hợp này là test quan trọng nhất để phân biệt LEFT JOIN đúng và một phép lọc vô tình biến nó thành INNER JOIN.

## 34. Bài tập ngắn có lời giải

### Bài 1: Chỉ lấy khách hàng đã có đơn hàng

**Yêu cầu:** không lấy Bình; mỗi customer một lần.

```sql
SELECT DISTINCT c
FROM Customer c
INNER JOIN c.orders o
```

Kết quả: An, Chi, Dũng.

### Bài 2: Lấy mọi customer và mọi order, kể cả customer trống

```sql
SELECT c, o
FROM Customer c
LEFT JOIN c.orders o
ORDER BY c.id, o.id
```

Kết quả: 5 hàng kết hợp, có `(Bình, null)`.

### Bài 3: Mọi customer và chỉ order PAID nếu có

```sql
SELECT c, o
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
ORDER BY c.id, o.id
```

Với `PAID`: An–101, Bình–null, Chi–null, Dũng–104.

### Bài 4: Chỉ customer có order PAID

```sql
SELECT DISTINCT c
FROM Customer c
JOIN c.orders o
WHERE o.status = :paid
```

Kết quả: An, Dũng.

### Bài 5: Customer chưa từng có order

```sql
SELECT c
FROM Customer c
WHERE c.orders IS EMPTY
```

Kết quả: Bình.

### Bài 6: Customer chưa có **bất kỳ order PAID** nào

```sql
SELECT c
FROM Customer c
WHERE NOT EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
)
```

Kết quả: Bình, Chi.

### Bài 7: Đếm order cho mọi customer

```sql
SELECT c.name, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o
GROUP BY c.id, c.name
```

Kết quả: An 2, Bình 0, Chi 1, Dũng 1.

### Bài 8: Đếm order PAID cho mọi customer

```sql
SELECT c.name, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
GROUP BY c.id, c.name
```

Kết quả: An 1, Bình 0, Chi 0, Dũng 1.

### Bài 9: Tải customer cùng toàn bộ orders, vẫn giữ customer trống

```sql
SELECT DISTINCT c
FROM Customer c
LEFT JOIN FETCH c.orders
```

Chọn `LEFT JOIN FETCH` vì mục tiêu là **nạp collection** và vẫn có customer không có order. Tránh dùng trực tiếp cho trang dữ liệu lớn mà chưa phân tích pagination.

### Bài 10: Ticket chưa có nhân viên xử lý

Giả sử `SupportTicket.assignee` là association tùy chọn.

```sql
SELECT t
FROM SupportTicket t
LEFT JOIN t.assignee a
WHERE a.id IS NULL
```

Chỉ lấy ticket chưa có assignee. Có thể dùng phép kiểm tra path trực tiếp `t.assignee IS NULL` khi provider/JPQL mapping hỗ trợ theo loại association; điểm chính vẫn là **không dùng INNER JOIN** nếu cần tìm quan hệ vắng mặt.

## 35. Câu hỏi tự kiểm tra

**1. `JOIN` không ghi `INNER` hay `LEFT` có nghĩa gì?**

Trong JPQL association join, `JOIN` không có từ chỉ loại là **inner join**.

**2. `LEFT JOIN` có luôn cho một hàng trên mỗi parent không?**

Không. Nó giữ mỗi parent ít nhất một hàng khi không có child phù hợp, nhưng parent có nhiều child có thể tạo nhiều hàng kết hợp.

**3. Vì sao Bình không xuất hiện với `INNER JOIN c.orders`?**

Vì Bình không có order, nên không có cặp customer–order nào thỏa quan hệ để giữ lại.

**4. Với `LEFT JOIN c.orders o`, alias `o` là gì khi customer không có order?**

Nó biểu diễn phía phải không tồn tại trong hàng được bảo toàn; các biểu thức như `o.id` cho giá trị null.

**5. Vì sao `WHERE o.status = PAID` có thể khiến LEFT JOIN mất Bình?**

Vì so sánh thuộc tính của alias null không cho TRUE, nên WHERE loại hàng được bảo toàn.

**6. Sửa thế nào để mọi customer vẫn xuất hiện và chỉ nối order PAID?**

`LEFT JOIN c.orders o ON o.status = :paid`.

**7. Vì sao thêm `OR o IS NULL` vào WHERE vẫn không giữ Chi?**

Vì Chi có order CANCELLED nên LEFT JOIN tạo hàng có `o` không null, nhưng không thỏa PAID; không có hàng null thay thế.

**8. INNER JOIN và LEFT JOIN có làm Hibernate/JPA provider luôn fetch collection không?**

Không. JOIN thường phục vụ truy vấn; cần `JOIN FETCH` hoặc fetch plan tương ứng khi thực sự muốn nạp association.

**9. Muốn fetch orders và giữ Bình, dùng `JOIN FETCH` hay `LEFT JOIN FETCH`?**

Dùng `LEFT JOIN FETCH c.orders`.

**10. Vì sao `COUNT(c)` có thể trả 1 cho Bình khi LEFT JOIN?**

Vì hàng chứa customer Bình vẫn tồn tại dù alias order null; `COUNT(c)` đếm customer không-null, không phải số order.

**11. Dùng biểu thức nào để đếm số order chính xác khi left join?**

`COUNT(o)` hoặc `COUNT(o.id)`, và `GROUP BY` theo parent.

**12. `SELECT DISTINCT c, o` có bảo đảm mỗi customer chỉ xuất hiện một lần không?**

Không. Hai tuple có cùng customer nhưng khác order vẫn khác nhau. Nếu muốn parent duy nhất, chọn projection parent và khử trùng đúng mục tiêu.

**13. Khi join hai collections độc lập, điều gì có thể xảy ra?**

Row multiplication: số kết hợp có thể bằng tích số phần tử giữa hai collection của cùng parent, làm méo COUNT/SUM và tăng chi phí.

**14. `c.orders.status` là cú pháp phù hợp để lọc status không?**

Không, vì `orders` là collection-valued relationship. Cần `JOIN c.orders o` rồi truy cập `o.status`.

**15. Khi nào `NOT EXISTS` có thể phù hợp hơn JOIN?**

Khi chỉ muốn kiểm tra có hoặc không có child thỏa điều kiện, không cần dữ liệu child trong projection.

**16. `JOIN c.orders o` có phải JOIN bảng `purchase_orders` theo tên SQL không?**

JPQL join qua **association property `orders`** trong metadata JPA; provider quyết định tên bảng/cột SQL thực tế.

**17. Một INNER JOIN ở tầng sau có thể làm mất parent đã được LEFT JOIN bảo toàn trước đó không?**

Có. Ví dụ `LEFT JOIN c.orders o JOIN o.lines l` có thể loại parent không có order hoặc order không có line.

**18. Có nên dùng collection JOIN FETCH rồi phân trang trực tiếp không?**

Cần rất thận trọng; join làm nhân số SQL rows, có thể khiến pagination không tương ứng số parent. Thường phân trang parent ID rồi fetch riêng.

## 36. Tổng kết

**`INNER JOIN` và `LEFT JOIN` trong JPQL khác nhau ở việc có bảo toàn entity bên trái khi association không có phần tử phù hợp hay không.**

Hai mẫu cơ bản:

```sql
-- Chỉ những khách hàng có order:
SELECT DISTINCT c
FROM Customer c
INNER JOIN c.orders o
```

```sql
-- Tất cả khách hàng, kể cả chưa có order:
SELECT DISTINCT c
FROM Customer c
LEFT JOIN c.orders o
```

Khi có điều kiện ở phía child, nhớ phân biệt:

```sql
-- Chỉ khách hàng có order PAID:
SELECT DISTINCT c
FROM Customer c
LEFT JOIN c.orders o
WHERE o.status = :paid
```

với:

```sql
-- Giữ mọi khách hàng, chỉ nối order PAID nếu có:
SELECT c, o
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
```

Đây là **sự khác biệt dễ gây lỗi nhất** trong các báo cáo cần giữ parent với số đếm bằng 0.

Những nguyên tắc nên nhớ:

1. **INNER JOIN loại parent không có child phù hợp; LEFT JOIN giữ parent đó với alias child null.**
2. **WHERE trên alias child có thể loại hàng null**, khiến LEFT JOIN không còn giữ tất cả parent trong kết quả cuối.
3. **ON giới hạn child được nối nhưng giữ parent** khi dùng LEFT JOIN.
4. **Join collection có thể tạo nhiều rows cho một parent**; chọn `DISTINCT`, `COUNT(child)`, `GROUP BY` hoặc `EXISTS` theo đúng yêu cầu.
5. **JOIN và JOIN FETCH khác mục đích**. Fetch join yêu cầu nạp association, nhưng phải cẩn trọng khi phân trang và join nhiều collections.
6. **JPQL join theo entity association**, không phải tên bảng SQL; implicit join khi đi qua association cũng có thể mang inner semantics.
7. **Kiểm thử parent không có child và parent chỉ có child không thỏa filter**. Đây là hai trường hợp giúp xác nhận ý nghĩa của LEFT JOIN + ON/WHERE.

Câu hỏi cốt lõi trước khi chọn:

> **Nếu một entity phía trái không có đối tượng quan hệ thỏa điều kiện, yêu cầu nghiệp vụ có muốn nó vẫn xuất hiện không?**

Nếu câu trả lời là **không**, hãy nghĩ đến `INNER JOIN` hoặc `EXISTS`. Nếu câu trả lời là **có**, hãy nghĩ đến **`LEFT JOIN`**, và đặc biệt kiểm tra các predicate `ON`/`WHERE` để không làm mất những bản ghi cần giữ.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence 3.1 — Query Language](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html#query-language)
- [Jakarta Persistence API — `EntityManager`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Jakarta Persistence API — `JoinType`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/jointype)
- [Jakarta Persistence API — Criteria `Join`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/join)
