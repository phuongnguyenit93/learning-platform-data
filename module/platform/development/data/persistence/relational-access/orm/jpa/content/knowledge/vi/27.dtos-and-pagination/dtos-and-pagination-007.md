# Đánh giá phân trang khi truy vấn có JOIN và DISTINCT

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** DTO và phân trang

Phân trang giúp ứng dụng truy xuất từng phần của một tập dữ liệu thay vì tải toàn bộ kết quả. Với một truy vấn đơn giản chỉ lấy entity gốc, việc giới hạn số bản ghi bằng `setFirstResult()` và `setMaxResults()` khá dễ hiểu. Nhưng khi câu truy vấn có `JOIN`, nhất là quan hệ **một-nhiều** hoặc **nhiều-nhiều**, số dòng SQL có thể lớn hơn rất nhiều số entity mà ứng dụng muốn hiển thị.

Thêm `DISTINCT` đôi khi giải quyết việc lặp entity, nhưng **không bảo đảm** mọi cách kết hợp `JOIN`, `JOIN FETCH`, `ORDER BY` và phân trang đều đúng hoặc hiệu quả. Vấn đề quan trọng nhất là xác định **đơn vị đang được phân trang**:

- Một dòng SQL sau JOIN?
- Một entity gốc (`PurchaseOrder`)?
- Một hàng DTO chứa các giá trị của cả parent và child?
- Một nhóm dữ liệu sau `GROUP BY`?
- Hay một aggregate có collection con phải được tải đầy đủ?

Bài học này giúp đánh giá đúng truy vấn trước khi đưa vào `Page`, `Slice`, pagination offset hoặc keyset. Những ví dụ dùng Jakarta Persistence (JPA), JPQL, SQL minh họa và Spring Data JPA. Chúng được tổ chức quanh nghiệp vụ danh sách đơn hàng, tìm đơn theo SKU, và màn hình chi tiết cần cả các dòng đơn hàng.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **dòng kết quả SQL** với **entity gốc duy nhất** và **hàng DTO**.
2. Giải thích vì sao `JOIN` qua collection tạo ra nhiều dòng cho cùng một entity.
3. Phân biệt `JOIN` thông thường và `JOIN FETCH` về mục tiêu và kết quả tải association.
4. Mô tả `DISTINCT` trong SQL và `SELECT DISTINCT entity` trong JPQL.
5. Nhận diện tình huống `DISTINCT` không khử trùng lặp theo khóa entity gốc, nhất là khi projection chứa field child.
6. Giải thích tại sao phân trang trên tập SQL rows rồi mới loại trùng entity có thể tạo **trang thiếu phần tử, lặp root qua nhiều trang hoặc mất child**.
7. Biết giới hạn của `setFirstResult()`/`setMaxResults()` khi dùng collection fetch join.
8. Xây dựng truy vấn dữ liệu và truy vấn `COUNT(DISTINCT ...)` nhất quán.
9. Dùng `EXISTS` khi chỉ cần kiểm tra “có ít nhất một child phù hợp”, tránh nhân dòng không cần thiết.
10. Viết chiến lược **hai bước: lấy IDs của root trên một trang rồi tải graph theo IDs đó**.
11. Hiểu tại sao `WHERE id IN :ids` không tự giữ thứ tự của IDs.
12. Dùng DTO projection cho danh sách không cần toàn bộ entity graph.
13. Chọn `Page` hoặc `Slice` trong Spring Data JPA dựa trên nhu cầu tổng số trang.
14. Thiết kế `ORDER BY` ổn định với khóa phụ duy nhất để tránh kết quả ngẫu nhiên khi nhiều bản ghi có cùng giá trị sort.
15. Nhận biết vấn đề khi sort theo thuộc tính của collection, chẳng hạn một đơn hàng có nhiều SKU.
16. Phân biệt offset pagination và keyset/seek pagination cùng tác động của dữ liệu thay đổi đồng thời.
17. Biết đo SQL, số hàng, memory, query plan và tính đúng đắn thay vì chỉ nhìn số dòng JPQL.
18. Tự thiết kế kiểm thử với dữ liệu có một parent, nhiều children, không có child và nhiều child cùng khớp bộ lọc.

## 2. Ba lớp kết quả phải phân biệt

Xét mô hình:

```text
PurchaseOrder
    |
    +-- OrderLine A
    +-- OrderLine B
    +-- OrderLine C
```

Với SQL JOIN:

```sql
SELECT o.id, o.order_number, l.id, l.sku
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
WHERE o.id = 1001;
```

Database có thể trả:

| order_id | order_number | line_id | sku |
|---:|---|---:|---|
| 1001 | ORD-1001 | 501 | SKU-A |
| 1001 | ORD-1001 | 502 | SKU-B |
| 1001 | ORD-1001 | 503 | SKU-C |

Ở đây có:

- **3 SQL rows**.
- **1 Order gốc duy nhất**, ID = 1001.
- **3 OrderLine khác nhau**.
- Nếu projection là `(orderId, sku)` thì có **3 DTO rows khác nhau**.

Một câu “truy vấn trả ba bản ghi” không đủ chính xác cho việc thiết kế phân trang. Phải biết **ba của cái gì**.

### 2.1. Root entity khác với dòng JOIN

`PurchaseOrder#1001` có cùng primary key trong ba SQL rows. JPA có identity map, nên cùng root ID trong một persistence context sẽ đại diện cho cùng managed entity identity. Tuy nhiên, một JPQL query không có DISTINCT và có JOIN to-many vẫn có thể trả về **nhiều vị trí trong danh sách kết quả cùng trỏ tới entity instance đó**.

Ví dụ:

```text
Result List:
  [Order#1001, Order#1001, Order#1001]
```

Điều này khác việc JPA tạo ba managed Order instances độc lập. Danh sách có thể lặp **tham chiếu tới cùng instance**, trong khi persistence context duy trì identity của entity.

### 2.2. Một hàng DTO là một đơn vị riêng

Nếu query chọn:

```jpql
SELECT NEW demo.dto.OrderLineRow(
    o.id,
    o.orderNumber,
    l.sku
)
FROM PurchaseOrder o
JOIN o.lines l
```

mỗi dòng child tạo một projection riêng. Hai dòng DTO có cùng `orderId` nhưng SKU khác nhau **không phải bản ghi trùng** theo ý nghĩa của projection.

Vì vậy, trước khi thêm DISTINCT, cần xác định DTO đang đại diện **Order** hay **OrderLine**.

### 2.3. Một nhóm sau GROUP BY cũng là đơn vị riêng

Nếu query:

```jpql
SELECT o.id, COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
GROUP BY o.id
```

thì mỗi hàng kết quả đại diện cho **một nhóm Order**, không phải một dòng JOIN. Pagination có thể áp dụng cho các nhóm này nếu ORDER BY và COUNT được thiết kế đúng.

---

## 3. Dữ liệu mẫu minh họa lỗi phân trang

Giả sử bảng `purchase_orders` có năm đơn hàng:

| Order ID | Mã đơn | Thời điểm tạo |
|---:|---|---|
| 1001 | ORD-1001 | 2026-11-01 09:00 |
| 1002 | ORD-1002 | 2026-11-02 09:00 |
| 1003 | ORD-1003 | 2026-11-03 09:00 |
| 1004 | ORD-1004 | 2026-11-04 09:00 |
| 1005 | ORD-1005 | 2026-11-05 09:00 |

Các dòng đơn hàng:

| Line ID | Order ID | SKU | Số lượng |
|---:|---:|---|---:|
| 501 | 1001 | A-01 | 2 |
| 502 | 1001 | B-01 | 1 |
| 503 | 1001 | C-01 | 4 |
| 504 | 1002 | B-02 | 3 |
| 505 | 1004 | A-02 | 1 |
| 506 | 1004 | A-03 | 2 |
| 507 | 1005 | C-02 | 1 |

**Order 1003 không có Line.** Đây là dữ liệu rất quan trọng để kiểm tra khác biệt giữa `JOIN` và `LEFT JOIN`.

Nếu JOIN hai bảng theo thứ tự Order ID, Line ID:

```sql
SELECT
    o.id AS order_id,
    l.id AS line_id
FROM purchase_orders o
LEFT JOIN order_lines l
    ON l.order_id = o.id
ORDER BY o.id ASC, l.id ASC;
```

kết quả có tám SQL rows:

| Vị trí SQL | order_id | line_id |
|---:|---:|---:|
| 1 | 1001 | 501 |
| 2 | 1001 | 502 |
| 3 | 1001 | 503 |
| 4 | 1002 | 504 |
| 5 | 1003 | NULL |
| 6 | 1004 | 505 |
| 7 | 1004 | 506 |
| 8 | 1005 | 507 |

Nhưng chỉ có **5 Orders duy nhất**.

---

## 4. Lỗi căn bản: LIMIT/OFFSET chia SQL rows, không tự chia root entities

Giả sử muốn trang kích thước 2, tức **mỗi trang hiển thị tối đa hai Orders**.

Một truy vấn SQL JOIN thông thường với phân trang trực tiếp:

```sql
SELECT
    o.id AS order_id,
    l.id AS line_id
FROM purchase_orders o
LEFT JOIN order_lines l
    ON l.order_id = o.id
ORDER BY o.id, l.id
LIMIT 2 OFFSET 0;
```

Trang SQL đầu tiên:

```text
(1001, 501)
(1001, 502)
```

Nếu Java biến hai dòng thành hai Order unique bằng Map/Set sau khi query, trang chỉ còn:

```text
[Order#1001]
```

Mặc dù page size được yêu cầu là 2, chỉ nhận **1 root Order**.

Trang SQL thứ hai:

```sql
LIMIT 2 OFFSET 2
```

cho:

```text
(1001, 503)
(1002, 504)
```

sau khi khử trùng lặp trong page:

```text
[Order#1001, Order#1002]
```

Order#1001 xuất hiện ở **cả hai trang**.

Đây là nguyên nhân phổ biến của ba lỗi:

1. **Trang thiếu số lượng root** so với kích thước yêu cầu.
2. **Một root xuất hiện lặp ở nhiều trang**.
3. **Thống kê tổng số trang sai** nếu đếm SQL rows thay vì root Orders.

### 4.1. Tại sao khử trùng lặp trong Java sau pagination không đủ?

Vì `LIMIT/OFFSET` đã được áp dụng vào **dòng kết quả trước bước deduplication ở Java**. Phần dữ liệu bị cắt đã mất khỏi truy vấn hiện tại; Java không thể “đoán” những Orders khác cần điền vào trang mà không thực hiện truy vấn bổ sung.

Không nên dùng:

```java
List<PurchaseOrder> raw = query
    .setFirstResult(page * size)
    .setMaxResults(size)
    .getResultList();

List<PurchaseOrder> unique =
    raw.stream().distinct().toList();
```

như một “giải pháp chung” cho phân trang JOIN to-many. Nó chỉ loại trùng **sau khi page boundaries đã được xác định sai**.

### 4.2. Bài học về thứ tự các phép toán

Một cách hình dung:

```text
SAI VỚI ROOT PAGINATION:

JOIN parent-child
    |
    v
SQL rows bị nhân
    |
    v
LIMIT/OFFSET trên SQL rows
    |
    v
Java DISTINCT theo root
    |
    v
Trang thiếu/lặp root

ĐÚNG THEO Ý ĐỊNH:

Lọc các root đủ điều kiện
    |
    v
Đảm bảo mỗi root có một vị trí logic
    |
    v
ORDER BY ổn định
    |
    v
LIMIT/OFFSET trên root
    |
    v
Fetch graph/DTO nếu cần
```

---

## 5. JOIN to-one khác JOIN to-many

Không phải mọi JOIN đều làm tăng số lượng root rows.

### 5.1. JOIN qua ManyToOne

Giả sử mỗi `PurchaseOrder` thuộc đúng một `Customer`:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Query:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.customer c
WHERE c.displayName LIKE :namePrefix
ORDER BY o.id
```

Với dữ liệu toàn vẹn và một Customer duy nhất cho mỗi Order, JOIN này thường tạo **một row cho mỗi Order phù hợp**. Đây là cardinality **nhiều Order → một Customer**; bản thân to-one JOIN không nhân Order thành nhiều rows.

Điều cần kiểm tra vẫn gồm:

- `INNER JOIN` có thể loại Orders không có Customer nếu mapping cho phép null.
- Điều kiện trên Customer có thể loại Orders.
- Thêm một JOIN to-many khác trong cùng query vẫn gây nhân rows.
- Các cấu hình provider hoặc query đặc biệt có thể làm số SQL khác, dù logical result cardinality không đổi.

### 5.2. JOIN qua OneToMany

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
ORDER BY o.id
```

Một Order có nhiều Lines phù hợp sẽ xuất hiện nhiều lần ở mức SQL row. Ví dụ Order#1004 có hai dòng `A-02` và `A-03`, đều phù hợp tiền tố `A-%`.

### 5.3. JOIN qua ManyToMany

Quan hệ nhiều-nhiều cũng thường nhân root rows:

```text
Article#1
   +-- Tag#A
   +-- Tag#B
   +-- Tag#C
```

Một query JOIN tags và lọc theo nhiều Tag có thể trả Article#1 qua nhiều dòng. Vấn đề root pagination là tương tự OneToMany.

### 5.4. LEFT JOIN không bảo đảm một row/root

`LEFT JOIN` giữ parent khi không có child phù hợp, nhưng nếu parent có nhiều children thì vẫn tạo nhiều rows. Không thể sửa multiplication chỉ bằng cách đổi `JOIN` thành `LEFT JOIN`.

---

## 6. Entity mapping tối thiểu cho ví dụ

Ví dụ dùng Jakarta Persistence và Java có các entity `Customer`, `PurchaseOrder`, `OrderLine`.

### 6.1. Customer

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

    protected Customer() {
    }

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

### 6.2. PurchaseOrder

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

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

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String orderNumber,
            LocalDateTime createdAt,
            Customer customer) {

        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.createdAt = Objects.requireNonNull(createdAt);
        this.customer = Objects.requireNonNull(customer);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line);
        lines.add(line);
    }
}
```

### 6.3. OrderLine

```java
package demo.domain;

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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false, length = 60)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(PurchaseOrder order, String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        this.order = order;
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

**Ghi chú:** đây là mô hình rút gọn phục vụ JPQL. Khi tạo dữ liệu, hãy persist Customer trước, persist Order tham chiếu Customer đã managed, rồi persist từng Line. `PurchaseOrder.addLine()` chỉ thêm Line vào collection; owning side FK là `OrderLine.order`. Không có cascade PERSIST nên việc thêm vào list **không tự persist Line**.

### 6.4. Schema tương ứng

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);

CREATE INDEX idx_orders_created_id
    ON purchase_orders(created_at, id);

CREATE INDEX idx_lines_order_id
    ON order_lines(order_id);

CREATE INDEX idx_lines_sku_order
    ON order_lines(sku, order_id);
```

DDL mang tính minh họa; một số DBMS có cú pháp IDENTITY khác. Index cần được đánh giá trên workload thật, không coi mọi index đề xuất là tối ưu sẵn.

---

## 7. DISTINCT trong SQL: khử trùng lặp theo toàn bộ cột SELECT

SQL `DISTINCT` áp dụng trên **tổ hợp tất cả biểu thức được SELECT**.

Ví dụ:

```sql
SELECT DISTINCT o.id, o.order_number
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku LIKE 'A-%'
ORDER BY o.id;
```

Với dữ liệu mẫu, có hai Orders khớp:

```text
1001, ORD-1001
1004, ORD-1004
```

Mặc dù Order#1004 có hai Lines khớp, cặp `(id, order_number)` là giống nhau nên SQL DISTINCT có thể loại bản sao.

### 7.1. Thêm child field vào SELECT làm thay đổi đơn vị distinct

Đổi query thành:

```sql
SELECT DISTINCT
    o.id,
    o.order_number,
    l.sku
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku LIKE 'A-%'
ORDER BY o.id, l.sku;
```

Kết quả:

| order_id | order_number | sku |
|---:|---|---|
| 1001 | ORD-1001 | A-01 |
| 1004 | ORD-1004 | A-02 |
| 1004 | ORD-1004 | A-03 |

`DISTINCT` không loại hai hàng của Order#1004 vì `l.sku` khác nhau.

**Cốt lõi:** SQL DISTINCT không có nghĩa “chọn duy nhất theo primary key của bảng đầu tiên” khi projection chứa giá trị khác nhau từ bảng con.

### 7.2. DISTINCT không biến một projection child thành projection parent

Nếu API muốn danh sách Orders, projection chứa `l.sku` ở mức mỗi Line là sai hạt dữ liệu. Thêm DISTINCT không sửa được mô hình dữ liệu đó. Phải chọn:

- Một row cho mỗi Order.
- Một row cho mỗi OrderLine.
- Hoặc một row cho mỗi Order với các child được tổng hợp hoặc tải riêng.

---

## 8. DISTINCT trong JPQL với entity gốc

JPQL có cú pháp:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
ORDER BY o.id
```

Khi `SELECT DISTINCT o`, mục tiêu là trả các `PurchaseOrder` **không trùng trong kết quả truy vấn**. Provider xử lý identity của entity khi materialize results; SQL có thể dùng DISTINCT hoặc provider thực hiện khử trùng lặp phù hợp.

### 8.1. Vì sao JPQL SELECT DISTINCT entity hữu ích?

Một Order có hai Lines thỏa điều kiện chỉ nên xuất hiện một lần trong danh sách Orders. `SELECT DISTINCT o` thể hiện ý định này ở mức JPQL.

Không nên nhầm với:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
```

Trong query không có DISTINCT, result list có thể chứa nhiều vị trí cùng entity gốc.

### 8.2. DISTINCT JPQL không phải phép màu hiệu năng

Ngay cả khi result list trả duy nhất root entities:

- SQL JOIN vẫn có thể tạo nhiều rows trung gian.
- Provider/database vẫn phải xử lý phép join, filter, sort và distinct.
- Query có thể cần temporary sort/hash cho DISTINCT.
- Fetching các associations khác vẫn có thể tạo SQL phụ.
- Pagination vẫn phải được xét theo kế hoạch SQL thực tế, đặc biệt với collection fetch joins.

### 8.3. Hibernate và xử lý DISTINCT

Một số phiên bản Hibernate có tối ưu, thay đổi cách phát SQL DISTINCT hoặc khử duplicate root từ fetch join. Không nên phụ thuộc vào một thuộc tính/hint của đúng phiên bản Hibernate nếu bài toán yêu cầu tính portable Jakarta Persistence.

**Kết luận về tính chuẩn:** `SELECT DISTINCT entity` mô tả ngữ nghĩa kết quả cần duy nhất; nhưng không đủ để cam kết một SQL plan cụ thể, không đủ để bảo đảm collection fetch join phân trang đúng.

---

## 9. DISTINCT trên DTO projection không giống DISTINCT entity

Ví dụ một DTO chứa Order và Line:

```java
package demo.dto;

public record OrderSkuRow(
    Long orderId,
    String orderNumber,
    String sku
) {}
```

JPQL:

```jpql
SELECT DISTINCT NEW demo.dto.OrderSkuRow(
    o.id,
    o.orderNumber,
    l.sku
)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
```

Khi SKU khác nhau, các DTO khác nhau. Order#1004 vẫn có hai hàng `A-02` và `A-03`. Nếu cùng SKU trùng lặp nhưng quantity khác nhau và DTO không chọn quantity, DISTINCT có thể chỉ còn một hàng theo các giá trị được SELECT; điều đó lại có thể làm mất thông tin chi tiết.

### 9.1. Cần xác định DTO hạt dữ liệu

| DTO | Một row đại diện | DISTINCT theo những gì? |
|---|---|---|
| `OrderListRow(id, number)` | Một Order | ID và number |
| `OrderSkuRow(id, number, sku)` | Một cặp Order/SKU | ID, number, SKU |
| `OrderLineRow(orderId, lineId, sku)` | Một Line | Line ID và giá trị chọn |
| `OrderStatsRow(orderId, count, total)` | Một nhóm Order | Kết quả tổng hợp theo Order |

Nếu màn hình hiển thị 20 Orders trên một trang, DTO chứa child SKU riêng từng dòng thường không phải hạt dữ liệu phù hợp.

### 9.2. Không dựa vào equals() của DTO để sửa phân trang

Record Java có `equals()` theo các component values. Nhưng `stream().distinct()` sau khi SQL LIMIT/OFFSET không sửa được boundary của trang. Nó chỉ lọc tiếp trên số hàng đã bị giới hạn.

---

## 10. Khi nào SELECT DISTINCT root rồi phân trang có thể phù hợp?

Một ví dụ JPQL lọc Orders theo child nhưng **không fetch collection**:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
ORDER BY o.createdAt DESC, o.id DESC
```

Có thể dùng:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    JOIN o.lines l
    WHERE l.sku LIKE :prefix
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class)
    .setParameter("prefix", "A-%")
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Ở đây không có `JOIN FETCH o.lines`. Provider có thể đưa phép DISTINCT tới SQL và pagination phù hợp với số root entities trong những trường hợp query rõ ràng như trên.

**Tuy nhiên:** cần kiểm tra SQL phát ra, đặc biệt khi query có projection phức tạp, ORDER BY trên các biểu thức không thuộc root, nhiều JOIN hoặc provider extensions. Nếu pagination correctness là yêu cầu quan trọng, bạn vẫn nên ưu tiên cách tránh nhân root rows ngay từ predicate, ví dụ `EXISTS`.

### 10.1. Có phải mọi JOIN đều cần DISTINCT?

Không.

- JOIN to-one không tự nhân root nếu foreign key trỏ đúng một entity.
- `EXISTS` lọc theo child mà không cần tạo root duplicate.
- Query aggregate `GROUP BY` đã xác định một row cho mỗi nhóm.
- Một query đã chọn đúng scalar values và không bị nhân không cần DISTINCT.

Thêm DISTINCT vô điều kiện có thể làm query khó tối ưu mà không tăng tính đúng.

---

## 11. JOIN FETCH khác JOIN thường

JPQL JOIN thường:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

Mục đích là dùng association `lines` để **lọc, ghép hoặc tính toán**. Nó không bắt buộc provider khởi tạo toàn bộ `o.lines` như một fetch join.

JPQL JOIN FETCH:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

Mục đích là yêu cầu **tải association lines cùng root** cho use case. Nếu Order có ba Lines, SQL join có thể sinh ba rows để dựng một Order với collection ba Line.

### 11.1. JOIN thường có thể dùng khi phân trang

Nếu JOIN chỉ lọc và kết quả root đã được distinct đúng cách, database có thể paginate tập root.

### 11.2. JOIN FETCH collection thay đổi bài toán

Khi fetch một collection to-many, provider phải dựng **tập children đầy đủ theo fetch plan** cho từng root. Một LIMIT/OFFSET trên SQL rows có thể cắt giữa những children của một root, dẫn đến một collection **không đầy đủ**.

Đó là vấn đề nghiêm trọng hơn việc trang chỉ thiếu số Order.

### 11.3. Vì sao không thể đơn giản đặt LIMIT vào SQL fetch join?

Ví dụ Order#1001 có ba Lines, nhưng SQL `LIMIT 2` chỉ đưa về hai Line đầu. Nếu provider coi collection đã loaded, ứng dụng có thể tưởng Order chỉ có hai Lines trong khi DB có ba.

Provider cần tránh hiểu sai như vậy; vì thế việc áp dụng phân trang với collection fetch join có các giới hạn/chiến lược khác nhau.

---

## 12. Collection FETCH JOIN cộng pagination: điểm cần đặc biệt thận trọng

Trong JPA, việc áp dụng `setFirstResult()` hoặc `setMaxResults()` cho query có fetch join qua collection **không có hành vi được bảo đảm portable như một root pagination thông thường**. Cần đọc quy tắc của provider và kiểm tra thực tế.

Ví dụ:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    ORDER BY o.id
    """,
    PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

**Không nên sử dụng query này làm chiến lược mặc định cho API phân trang production.**

### 12.1. Những hành vi có thể gặp

Tùy provider/version/configuration:

1. Query bị từ chối hoặc phát cảnh báo.
2. Provider tải nhiều SQL rows rồi **phân trang trong bộ nhớ** theo root entities.
3. Provider dùng cách xử lý riêng để tránh collection bị cắt, với chi phí SQL/memory có thể cao.
4. Các extension riêng DB/provider cố xử lý pagination theo một chiến lược khác.

Không có bảo đảm chung rằng SQL sẽ luôn có `LIMIT 20` trên đúng tập root Orders và collection vẫn đầy đủ.

### 12.2. In-memory pagination có gì nguy hiểm?

Giả sử có 500.000 Orders, trung bình mỗi Order có 10 Lines. Nếu provider phải tải rất nhiều rows mới phân trang trong Java:

```text
Database có thể phải xử lý một lượng
tới hàng triệu joined rows

Provider/ứng dụng:
  materialize hoặc duyệt lượng dữ liệu lớn
  deduplicate root
  chọn 20 Orders cho page

API cuối cùng:
  trả chỉ 20 Orders
```

Response nhỏ không có nghĩa query ít tốn tài nguyên. Bộ nhớ, GC, network bandwidth và database load có thể rất lớn.

### 12.3. Hibernate-specific warning và cấu hình fail-fast

Hibernate ORM có thể cảnh báo khi collection fetch được dùng cùng pagination và có setting để coi tình huống này là lỗi, thường được biết tới dưới tên:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Đây là **cấu hình Hibernate**, không phải thuộc tính Jakarta Persistence chuẩn. Tên/chế độ hỗ trợ cần được xác minh với version Hibernate thực tế.

Trong dự án quan trọng, fail-fast hữu ích vì phát hiện query nguy hiểm thay vì âm thầm phân trang trong memory.

### 12.4. Tăng DISTINCT không giải quyết tận gốc

`SELECT DISTINCT o LEFT JOIN FETCH o.lines` vẫn phải lấy các hàng con để dựng collection. Nếu SQL SELECT có các cột Line khác nhau, SQL DISTINCT trên toàn bộ hàng không làm các hàng đó trùng nhau. Vì thế DISTINCT không tự biến collection fetch join thành root pagination có `LIMIT` an toàn.

---

## 13. Cách đúng thường gặp: phân trang IDs trước, fetch collection sau

Một giải pháp thực tế là chia rõ **quyết định root nào thuộc trang** và **tải các child của root đã chọn**.

```text
BƯỚC 1: Xác định root IDs đúng thứ tự
  - Filter
  - Không nhân root hoặc DISTINCT đúng hạt dữ liệu
  - ORDER BY ổn định
  - LIMIT/OFFSET hoặc keyset

          [1005, 1004, 1003, 1002]

BƯỚC 2: Load đầy đủ association của 4 IDs
  - WHERE o.id IN :pageIds
  - LEFT JOIN FETCH o.lines
  - Không áp dụng pagination lên collection fetch

BƯỚC 3: Khôi phục thứ tự IDs của Bước 1
  - Map theo ID
  - Duyệt pageIds để xây danh sách cuối
```

### 13.1. Bước 1: chỉ lấy IDs

Ví dụ danh sách tất cả Orders:

```jpql
SELECT o.id
FROM PurchaseOrder o
ORDER BY o.createdAt DESC, o.id DESC
```

Java:

```java
List<Long> ids = em.createQuery(
    """
    SELECT o.id
    FROM PurchaseOrder o
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    Long.class)
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize)
    .getResultList();
```

Kết quả page chỉ gồm IDs của Orders. Không JOIN to-many nên mỗi Order tương ứng một hàng.

### 13.2. Bước 2: fetch collection cho đúng IDs

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Java:

```java
List<PurchaseOrder> fetched = em.createQuery(
    """
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    WHERE o.id IN :ids
    """,
    PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
```

**Không có `setFirstResult`/`setMaxResults` ở bước 2.** Kích thước root set đã bị giới hạn ở bước 1.

### 13.3. Bước 3: khôi phục thứ tự

`IN :ids` **không bảo đảm** database trả rows theo thứ tự của Java List IDs. Ví dụ page IDs là `[1005,1004,1003]` nhưng query fetch có thể trả `[1003,1005,1004]`.

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

Cần import `java.util.Map`, `HashMap`, `ArrayList`, `List`. Khôi phục thứ tự theo IDs là bước quan trọng nếu API phải giữ đúng `ORDER BY` của trang.

### 13.4. Không coi hai truy vấn luôn nhìn cùng một snapshot

Nếu có transaction khác xóa/thêm/sửa Orders giữa bước 1 và bước 2, kết quả fetch có thể khác danh sách ID ban đầu. Ví dụ Order#1004 bị xóa sau khi ID được chọn. Khi đó `byId.get(1004)` có thể null.

Nếu yêu cầu nhất quán mạnh, cần thiết kế transaction isolation, snapshot consistency và policy xử lý dữ liệu thay đổi. Hai bước giúp **đúng hạt dữ liệu phân trang**, nhưng không tự biến các truy vấn thành một snapshot bất biến trên mọi DB.

---

## 14. Hai bước khi lọc theo thuộc tính OrderLine

Một API thường gặp:

> Lấy mỗi Order một lần nếu có **ít nhất một Line** có SKU bắt đầu bằng `A-`, sắp xếp theo thời gian tạo.

Một cách viết JOIN:

```jpql
SELECT DISTINCT o.id
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :skuPrefix
ORDER BY o.createdAt DESC, o.id DESC
```

Bước 1 có thể sử dụng DISTINCT để khử lặp ID. Nhưng một cách dễ diễn đạt hơn là `EXISTS`.

### 14.1. Bước IDs dùng EXISTS

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :skuPrefix
)
ORDER BY o.createdAt DESC, o.id DESC
```

Đây là một **semi-join về mặt logic**: chỉ hỏi có tồn tại ít nhất một Line phù hợp không. Một Order có hai hoặc hai mươi Lines phù hợp vẫn chỉ xuất hiện **một lần** trong root query.

### 14.2. SQL minh họa

```sql
SELECT o.id
FROM purchase_orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.sku LIKE 'A-%'
)
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20 OFFSET 0;
```

Tùy optimizer, database có thể biến EXISTS thành semi-join hoặc một kế hoạch khác. Không mặc định rằng EXISTS luôn nhanh hơn JOIN DISTINCT, nhưng nó **diễn đạt đúng bài toán tồn tại child** và tránh phải tạo result tuples riêng ở mức logic.

### 14.3. Query count tương ứng

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

Ở query này, mỗi Order được xét một lần; không cần `COUNT(DISTINCT o.id)` chỉ để chữa multiplication vì EXISTS không nhân root.

### 14.4. Trường hợp điều kiện phải áp dụng cho cùng một child

Nếu yêu cầu:

> Tìm Orders có ít nhất một Line **SKU A** và **quantity >= 2** trên cùng một dòng.

`EXISTS` nên chứa hai điều kiện trong **cùng subquery**:

```jpql
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :skuPrefix
      AND l.quantity >= :minQuantity
)
```

Đừng tách thành hai EXISTS nếu nghiệp vụ đòi hỏi **một Line đồng thời thỏa cả hai điều kiện**. Hai EXISTS riêng có thể được thỏa bởi hai Lines khác nhau.

---

## 15. Tổng số bản ghi: COUNT(*) khác COUNT(DISTINCT root)

Một API kiểu Page thường cần:

- Nội dung trang.
- Tổng số root Orders phù hợp.
- Tổng số trang.
- Cờ có trang kế tiếp.

Nếu query data có JOIN to-many:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

count query sai:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

Với dữ liệu mẫu `A-%`:

```text
Matched Line rows:
  Order#1001 - A-01
  Order#1004 - A-02
  Order#1004 - A-03

COUNT(o) = 3
Số Orders thực = 2
```

### 15.1. COUNT(DISTINCT o.id)

Một count query đúng về hạt root:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

Kết quả là 2.

Có thể dùng:

```jpql
SELECT COUNT(DISTINCT o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

trong những context/provider cho phép đếm entity distinct; dùng `o.id` thường làm ý định khóa định danh rõ hơn, nhất là khi muốn tương ứng với SQL COUNT DISTINCT primary key.

### 15.2. Đừng viết COUNT theo DTO row

Nếu data query trả mỗi Order một lần, count phải đếm Orders. Nếu data query trả mỗi OrderLine một lần, count phải đếm Lines. Không tự chọn COUNT DISTINCT root cho mọi API chỉ vì có JOIN.

**Count đúng phải có cùng đơn vị với nội dung trang.**

### 15.3. Sự khác biệt COUNT(*), COUNT(l) và COUNT(DISTINCT o.id)

| Biểu thức | Với JOIN to-many và nhiều Lines | Ý nghĩa |
|---|---|---|
| `COUNT(o)` | Có thể lớn hơn số Orders | Đếm các dòng JOIN có root |
| `COUNT(l)` | Đếm các Lines non-null trong nhóm/truy vấn | Có thể bằng số dòng child phù hợp |
| `COUNT(DISTINCT o.id)` | Đếm Orders duy nhất | Phù hợp root pagination |
| `COUNT(o)` với EXISTS | Mỗi Order một lần | Phù hợp nếu lọc chỉ bằng EXISTS |

Với `LEFT JOIN`, `COUNT(o)` còn có thể đếm hàng parent không có child, trong khi `COUNT(l)` không đếm child NULL. Hãy hiểu rõ semantics trước khi dùng.

---

## 16. Count query phải giữ đúng bộ lọc

Giả sử data query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
JOIN o.customer c
WHERE l.sku LIKE :skuPrefix
  AND c.displayName LIKE :customerPrefix
  AND o.createdAt >= :fromDate
```

Count query phải giữ **tương đương cùng điều kiện**:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
JOIN o.customer c
WHERE l.sku LIKE :skuPrefix
  AND c.displayName LIKE :customerPrefix
  AND o.createdAt >= :fromDate
```

Nếu bỏ `customerPrefix` hoặc `fromDate` ở count query, `totalElements` sai dù nội dung trang đúng.

### 16.1. Không dùng FETCH JOIN trong count query

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

không phải thiết kế phù hợp. `FETCH` dùng để tải association của entity được chọn; COUNT không chọn entity root để nhận association.

Hãy dùng JOIN thường nếu cần điều kiện, hoặc bỏ JOIN nếu count không phụ thuộc child.

### 16.2. Không đưa ORDER BY không cần thiết vào count query

COUNT tổng số không cần sắp xếp. `ORDER BY` trong query count vừa không phục vụ kết quả, vừa có thể không hợp lệ hoặc làm DB tốn công.

### 16.3. Giữ cùng chính sách quyền truy cập

Nếu danh sách chỉ được phép thấy Orders của một tenant/customer, count query phải có **cùng tenant filter**. Sai totalElements không chỉ là lỗi UX; nó có thể để lộ thông tin về dữ liệu ngoài quyền của người dùng.

---

## 17. LEFT JOIN, WHERE và điều kiện ON: có thể làm mất root

Giả sử muốn lấy **mọi Orders**, kèm Lines có SKU bắt đầu `A-` nếu có.

Query:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN o.lines l
WHERE l.sku LIKE :prefix
```

không giữ Orders không có Line phù hợp, vì `l.sku` sẽ NULL ở hàng không ghép được và predicate WHERE không TRUE. Nó thực tế hoạt động như lọc các Orders có Line phù hợp.

Nếu muốn giữ cả Orders không có Line khớp, cần thiết kế:

```jpql
SELECT o, l
FROM PurchaseOrder o
LEFT JOIN o.lines l
    ON l.sku LIKE :prefix
```

Nhưng query này trả **từng cặp `(Order, Line)`**, và một Order có nhiều Lines phù hợp vẫn tạo nhiều rows.

### 17.1. Lọc bằng WHERE và giữ tất cả root là hai yêu cầu khác nhau

- “Chỉ lấy Orders có Line A” → `EXISTS`/INNER JOIN lọc root.
- “Lấy tất cả Orders, nếu có Line A thì kèm theo thông tin Line đó” → LEFT JOIN/DTO thích hợp, cần xét cardinality.
- “Lấy Orders và toàn bộ Lines, dù điều kiện trên một Line được dùng để chọn Orders” → hai bước IDs lọc bằng EXISTS, rồi fetch tất cả Lines.

Phải làm rõ nghiệp vụ trước khi chọn JOIN hoặc DISTINCT.

### 17.2. Không lọc collection được fetch như collection đầy đủ

Một số provider có extension cho phép viết điều kiện ngay trên fetch join hoặc alias của fetch join, ví dụ chỉ lấy các Lines khớp SKU. Điều đó có thể khiến collection `order.lines` trông đã loaded nhưng **chỉ chứa một phần các Lines**, trái ý nghĩa thông thường của association.

Nếu cần toàn bộ collection của Orders thỏa một điều kiện child, an toàn hơn là:

1. Chọn root IDs bằng EXISTS có điều kiện.
2. Fetch toàn bộ `o.lines` của IDs đó ở query riêng.

Nếu chỉ cần các Lines thỏa filter để trả DTO, hãy tạo DTO/projection riêng cho filtered Lines thay vì đánh dấu collection entity đã nạp “đầy đủ”.

---

## 18. ORDER BY ổn định là điều kiện của phân trang đúng

Giả sử sort theo `createdAt DESC`:

```jpql
ORDER BY o.createdAt DESC
```

Nếu hai Orders có cùng `createdAt`, thứ tự của chúng **không được xác định duy nhất** bởi ORDER BY này. Database có thể trả thứ tự khác giữa hai lần truy vấn hoặc sau khi kế hoạch SQL thay đổi.

### 18.1. Thêm khóa phụ duy nhất

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

`id` là unique nên giúp xác định thứ tự trong tập kết quả tại một thời điểm. Với root pagination, khóa phụ ổn định giúp giảm nguy cơ thiếu/lặp khi nhiều bản ghi có cùng ngày.

### 18.2. DISTINCT cộng ORDER BY trên child

Một câu nguy hiểm về mặt nghiệp vụ:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
ORDER BY l.sku
```

Một Order có nhiều SKU. Vậy nó phải được sắp theo SKU nào?

```text
Order#1001: A-01, B-01, C-01
Order#1004: A-02, A-03
```

Không có định nghĩa rõ ràng cho một sort key duy nhất trên mỗi Order. Ngoài ra, một số database hạn chế `ORDER BY` với `SELECT DISTINCT` nếu biểu thức ORDER BY không được chọn. Vì vậy query có thể bị từ chối, tạo SQL không portable hoặc cho thứ tự không như mong đợi.

### 18.3. Định nghĩa aggregate sort key

Nếu yêu cầu nghiệp vụ là:

> Sắp xếp Order theo SKU nhỏ nhất của nó.

Hãy biểu diễn rõ bằng aggregate:

```jpql
SELECT o.id, MIN(l.sku)
FROM PurchaseOrder o
LEFT JOIN o.lines l
GROUP BY o.id
ORDER BY MIN(l.sku), o.id
```

Nếu yêu cầu là “SKU lớn nhất” dùng `MAX(l.sku)`. Nếu muốn sort theo thời điểm Line mới nhất, dùng `MAX(l.createdAt)` trong mô hình có thuộc tính createdAt.

**Không có một thứ tự đúng duy nhất** khi sort root theo thuộc tính của collection; phải định nghĩa aggregation hoặc quy tắc chọn child cụ thể.

---

## 19. GROUP BY: một row mỗi root nhưng cần tính toán đúng

Giả sử màn hình danh sách Order cần số Lines:

```jpql
SELECT
    o.id,
    o.orderNumber,
    COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
GROUP BY o.id, o.orderNumber
ORDER BY o.id
```

Query tạo **một nhóm mỗi Order**, nên mỗi dòng projection là một Order và số Lines tương ứng.

### 19.1. Không cần DISTINCT nếu GROUP BY đã tạo đúng hạt dữ liệu

Nếu chỉ có một row/group per root, thêm `DISTINCT` có thể không mang lại ý nghĩa mới. Trước khi thêm, xác định các field trong GROUP BY có thực sự làm một Order thành nhiều nhóm không.

### 19.2. GROUP BY thiếu field cần thiết

Nếu DTO chọn:

```text
orderId, orderNumber, customerName, COUNT(lines)
```

thì group cần bao gồm các state-valued path expressions tương ứng với những field ngoài aggregate theo quy tắc JPQL/provider.

Ví dụ:

```jpql
SELECT
    o.id,
    o.orderNumber,
    c.displayName,
    COUNT(l)
FROM PurchaseOrder o
JOIN o.customer c
LEFT JOIN o.lines l
GROUP BY o.id, o.orderNumber, c.displayName
ORDER BY o.id
```

Đừng dựa vào việc một SQL dialect cho phép group chỉ theo primary key rồi kết luận mọi JPQL provider đều portable.

### 19.3. Grouping theo nhiều collections dễ nhân số liệu

Nếu Order đồng thời JOIN `lines` và `payments`:

```text
Order#1001:
  3 Lines
  2 Payments

JOIN cả hai collections:
  có thể tạo 3 × 2 = 6 rows
```

`COUNT(l)` có thể bị nhân lên, và `SUM(payment.amount)` cũng có thể bị cộng lặp. `COUNT(DISTINCT l.id)` chỉ sửa được một phần đếm, không tự sửa được mọi tổng số tiền.

Giải pháp có thể là các aggregate queries độc lập, subqueries thích hợp, database view hoặc DTO từ nhiều truy vấn. Đừng dùng DISTINCT như thuốc chữa chung cho mọi join multiplication.

---

## 20. Thiết kế DTO danh sách một row cho mỗi Order

Một màn hình Order list có thể chỉ cần:

- Order ID.
- Order number.
- CreatedAt.
- Tên Customer.

Định nghĩa:

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

JPQL:

```jpql
SELECT NEW demo.dto.OrderListRow(
    o.id,
    o.orderNumber,
    o.createdAt,
    c.displayName
)
FROM PurchaseOrder o
JOIN o.customer c
ORDER BY o.createdAt DESC, o.id DESC
```

Vì `o.customer` là quan hệ to-one, query có thể trả một row cho mỗi Order, không cần JOIN Lines hay DISTINCT.

### 20.1. Vì sao DTO projection có lợi?

- Chỉ lấy dữ liệu cần hiển thị.
- Không materialize toàn bộ entity graph và lazy collections.
- Không phải serializing JPA proxies.
- Query rõ hạt dữ liệu: một DTO/Order.
- Dễ tạo page ổn định theo root.
- Giảm nguy cơ collection fetch join kết hợp pagination.

Tuy nhiên, DTO không tự giải quyết JOIN to-many nếu projection vẫn chứa child field. Phải thiết kế **đúng cardinality**.

### 20.2. DTO không nhất thiết cần SELECT DISTINCT

Trong projection to-one ở trên, nếu mapping/database đảm bảo mỗi Order có đúng một Customer, mỗi Order đã là một row. `DISTINCT` có thể tạo thêm chi phí mà không khử bản ghi nào.

---

## 21. DTO cho collection: chọn cách trả dữ liệu

Một API chi tiết Order có thể muốn:

```text
Order:
  id
  orderNumber
  lines:
    - sku, quantity
    - sku, quantity
```

Có ba cách chính.

### 21.1. Cách A — Fetch graph sau khi page IDs

Lấy đúng root IDs, sau đó `LEFT JOIN FETCH o.lines` cho IDs đó, chuyển managed entities thành DTO trong transaction/context.

Phù hợp khi số Orders trên một page nhỏ và mỗi Order có collection vừa phải.

### 21.2. Cách B — Query flat OrderLine rows rồi group trong Java

Bước 1 lấy root Order list page (một row/root). Bước 2 query:

```jpql
SELECT NEW demo.dto.OrderLineRow(
    l.order.id,
    l.id,
    l.sku,
    l.quantity
)
FROM OrderLine l
WHERE l.order.id IN :ids
ORDER BY l.order.id, l.id
```

Giả định DTO:

```java
public record OrderLineRow(
    Long orderId,
    Long lineId,
    String sku,
    int quantity
) {}
```

Nhóm các Lines theo `orderId` rồi gắn vào `OrderDetailsRow` trong Java. Cách này không cần materialize collection entity graph và cho phép kiểm soát chính xác cột child.

### 21.3. Cách C — Database-specific aggregation

Một số database hỗ trợ JSON aggregation hoặc array aggregation để trả danh sách Lines trên một row Order. Cách này có thể hiệu quả trong report nhưng là **SQL/dialect-specific**; không phải một mẫu JPQL portable chung.

Khi chọn cách nào, hãy căn cứ vào số child, nhu cầu caching, pagination, serialization và tính portable.

---

## 22. Ví dụ hoàn chỉnh: hai bước root IDs rồi OrderDetails DTO

Ta xây một service với hợp đồng:

> Trả tối đa `pageSize` Orders theo `createdAt DESC, id DESC`, mỗi Order kèm các Lines đầy đủ, không phân trang SQL JOIN rows.

DTOs:

```java
package demo.dto;

import java.util.List;

public record OrderLineView(
    Long id,
    String sku,
    int quantity
) {}

public record OrderDetailsView(
    Long id,
    String orderNumber,
    String customerName,
    List<OrderLineView> lines
) {}
```

Hai record trên phải đặt vào các source files riêng nếu cả hai là public top-level types trong Java.

### 22.1. Service Java dùng EntityManager

```java
package demo.service;

import demo.domain.OrderLine;
import demo.domain.PurchaseOrder;
import demo.dto.OrderDetailsView;
import demo.dto.OrderLineView;

import jakarta.persistence.EntityManager;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class OrderPageReader {

    public List<OrderDetailsView> readPage(
            EntityManager em,
            int pageIndex,
            int pageSize) {

        if (pageIndex < 0 || pageSize <= 0) {
            throw new IllegalArgumentException(
                "Invalid page request");
        }

        long first = (long) pageIndex * pageSize;

        if (first > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Offset exceeds JPA pagination range");
        }

        // 1. Page IDs: một row cho mỗi Order.
        List<Long> ids = em.createQuery(
            """
            SELECT o.id
            FROM PurchaseOrder o
            ORDER BY o.createdAt DESC, o.id DESC
            """,
            Long.class)
            .setFirstResult((int) first)
            .setMaxResults(pageSize)
            .getResultList();

        if (ids.isEmpty()) {
            return List.of();
        }

        // 2. Fetch toàn bộ Lines của các Orders thuộc trang.
        List<PurchaseOrder> fetched = em.createQuery(
            """
            SELECT DISTINCT o
            FROM PurchaseOrder o
            LEFT JOIN FETCH o.lines
            WHERE o.id IN :ids
            """,
            PurchaseOrder.class)
            .setParameter("ids", ids)
            .getResultList();

        // 3. Tạo index theo primary key; IN không giữ thứ tự.
        Map<Long, PurchaseOrder> byId = new HashMap<>();

        for (PurchaseOrder order : fetched) {
            byId.put(order.getId(), order);
        }

        // 4. Trả DTO theo đúng thứ tự trang IDs ban đầu.
        List<OrderDetailsView> result = new ArrayList<>();

        for (Long id : ids) {
            PurchaseOrder order = byId.get(id);

            if (order == null) {
                // Có thể có concurrent delete giữa hai bước.
                continue;
            }

            List<OrderLineView> lineViews = new ArrayList<>();

            for (OrderLine line : order.getLines()) {
                lineViews.add(new OrderLineView(
                    line.getId(),
                    line.getSku(),
                    line.getQuantity()
                ));
            }

            result.add(new OrderDetailsView(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getDisplayName(),
                lineViews
            ));
        }

        return result;
    }
}
```

**Lưu ý quan trọng về code:** mapping `PurchaseOrder.customer` đang LAZY; dòng `getCustomer().getDisplayName()` có thể phát sinh SELECT phụ. Nếu màn hình cần tên Customer cho mọi Order, cần mở rộng fetch plan bước 2, ví dụ thêm `JOIN FETCH o.customer` (to-one) hoặc dùng projection/tải Customer có chủ đích. Đo SQL để tránh N+1 ở chỗ tưởng đã tối ưu.

### 22.2. Tối ưu bước fetch: to-one cộng một to-many

Query bước 2 có thể được thiết kế:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Trong mô hình Customer bắt buộc, `JOIN FETCH o.customer` phù hợp. Đây là một to-one cộng một to-many; không có pagination tại bước 2. Tuy nhiên, số rows SQL vẫn tăng theo số Lines, nên page size và collection size vẫn phải được giới hạn phù hợp.

### 22.3. Thứ tự Lines bên trong collection

Query bước 2 không tự bảo đảm thứ tự của `order.lines`. Nếu API cần sắp theo Line ID hoặc SKU, có thể:

- Khai báo `@OrderBy("id ASC")` hoặc một ordering mapping thích hợp.
- Sắp xếp `lineViews` trong Java theo quy tắc rõ.
- Dùng DTO query child với `ORDER BY` tường minh.

**Thứ tự root Orders và thứ tự Lines là hai thứ tự độc lập.**

### 22.4. Vì sao không gọi paginated JOIN FETCH ngay?

Vì root pagination được giải quyết từ đầu ở query IDs. Fetch query không phải chịu `LIMIT` trên joined rows, nên không gặp vấn đề cắt collection khi SQL chỉ trả hai dòng của một Order có ba Lines.

---

## 23. Hoàn chỉnh với totalElements

Nếu API còn cần tổng số Orders, nên có count query **đếm root**:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
```

Với bộ lọc theo SKU dùng EXISTS:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :prefix
)
```

Nếu dùng JOIN to-many:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

### 23.1. Kết quả trang gồm những gì?

Một cấu trúc ứng dụng:

```java
public record PageResult<T>(
    List<T> content,
    int pageIndex,
    int pageSize,
    long totalElements
) {
    public long totalPages() {
        if (totalElements == 0) {
            return 0;
        }
        return (totalElements + pageSize - 1) / pageSize;
    }
}
```

Với `pageSize > 0`, công thức trên cho số trang làm tròn lên. Khi tổng số cực lớn, có thể viết công thức tránh overflow hoặc dùng phép tính `(totalElements / pageSize) + ...`; ví dụ tập trung vào pagination semantics.

### 23.2. COUNT là một truy vấn riêng

Trong phần lớn thiết kế, nội dung page và total count được lấy bằng các statement riêng. Hai truy vấn có thể nhìn thấy hai snapshot khác nhau nếu concurrent writes xảy ra và isolation cho phép.

Vì vậy, totalElements là số lượng theo **thời điểm/trạng thái quan sát được**, không phải lời hứa tuyệt đối rằng mọi page sau đó vẫn giữ nguyên tổng đó.

---

## 24. Spring Data JPA: Page và countQuery tường minh

Spring Data JPA giúp làm pagination bằng `Pageable` và `Page<T>`, nhưng framework không thể tự hiểu mọi ngữ nghĩa đặc biệt của JOIN, DISTINCT, GROUP BY và fetch join.

### 24.1. Truy vấn trả entity root theo child filter

Một repository method:

```java
package demo.repository;

import demo.domain.PurchaseOrder;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

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
    Page<PurchaseOrder> findOrdersHavingSku(
        @Param("prefix") String prefix,
        Pageable pageable
    );
}
```

Vì `EXISTS` không tạo duplicate root results, count query dùng `COUNT(o)` là phù hợp.

Gọi:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<PurchaseOrder> page =
    repository.findOrdersHavingSku("A-%", pageable);
```

Cần import `PageRequest` và `Sort` của Spring Data. Sort keys là **persistent properties** của entity và được Spring Data chuyển vào query theo cơ chế tương ứng.

### 24.2. Khi dùng JOIN DISTINCT

Nếu query data là:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

count query tương ứng thường cần:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
```

Đừng để auto-derived count query là một giả định không được kiểm tra trong trường hợp JPQL phức tạp. Spring Data có khả năng sinh count cho nhiều query, nhưng query phức tạp JOIN/DISTINCT/GROUP BY nên được xác nhận hoặc khai báo `countQuery` tường minh.

### 24.3. Vì sao không dùng @Query fetch join collection cho Page?

Một method:

```java
@Query("""
    SELECT DISTINCT o
    FROM PurchaseOrder o
    LEFT JOIN FETCH o.lines
    """)
Page<PurchaseOrder> findAllWithLines(Pageable pageable);
```

có nguy cơ phân trang trong memory, warning/error provider hoặc count query không phù hợp. Không nên coi `Pageable` là công cụ tự sửa fetch-join cardinality.

Thay bằng chiến lược page IDs/projections, hoặc lấy Page<DTO> không cần materialize to-many collection, rồi tải child theo IDs.

### 24.4. Spring @EntityGraph có tự giải quyết không?

Không. Nếu dùng `@EntityGraph(attributePaths="lines")` để fetch collection trong một query có `Pageable`, vấn đề cardinality của to-many fetch vẫn cần được xét. Một entity graph giúp khai báo fetch plan, **không biến collection thành to-one**.

---

## 25. Page và Slice trong Spring Data JPA

`Page<T>` thường cung cấp:

- `getContent()`.
- `getNumber()`.
- `getSize()`.
- `getTotalElements()`.
- `getTotalPages()`.
- Thông tin còn trang tiếp theo hay không.

`Slice<T>` tập trung vào nội dung của một đoạn và việc **có đoạn kế tiếp hay không**, thường không cần tổng số bản ghi toàn bộ, vì vậy có thể tránh count query trong những trường hợp phù hợp.

### 25.1. Chọn Page khi nào?

- Giao diện cần số trang cụ thể như 1/20.
- API phải báo totalElements.
- Report muốn có tổng số root hiện tại.
- Chi phí count query chấp nhận được.

### 25.2. Chọn Slice khi nào?

- Giao diện “Load more”.
- Không cần totalElements.
- Count query rất tốn kém.
- Muốn biết có thêm dữ liệu theo thứ tự hiện tại.

### 25.3. Slice không tự sửa JOIN multiplication

Nếu Slice query JOIN to-many trả nhiều SQL rows/root, framework vẫn cần đảm bảo content là các **root unique** theo semantics mong muốn. Việc bỏ totalCount không giải quyết trang có duplicate root hoặc collection fetch join.

Một Slice tốt vẫn phải dựa trên query cho **một hàng/root** hoặc chiến lược paging IDs.

---

## 26. Criteria API: distinct root và countDistinct

Không bắt buộc viết JPQL String; có thể dùng JPA Criteria API.

### 26.1. Data query theo OrderLine

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root = cq.from(PurchaseOrder.class);

Join<PurchaseOrder, OrderLine> lines =
    root.join("lines");

cq.select(root)
  .distinct(true)
  .where(cb.like(lines.get("sku"), "A-%"))
  .orderBy(
      cb.desc(root.get("createdAt")),
      cb.desc(root.get("id"))
  );

List<PurchaseOrder> orders = em.createQuery(cq)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Cần imports `jakarta.persistence.criteria.CriteriaBuilder`, `CriteriaQuery`, `Root`, `Join`. Trong ứng dụng thực tế, static metamodel có thể thay chuỗi field names để an toàn refactor.

### 26.2. Count query tương ứng

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

Root<PurchaseOrder> countRoot =
    countQuery.from(PurchaseOrder.class);

Join<PurchaseOrder, OrderLine> countLines =
    countRoot.join("lines");

countQuery.select(
    cb.countDistinct(countRoot.get("id"))
);

countQuery.where(
    cb.like(countLines.get("sku"), "A-%")
);

Long total = em.createQuery(countQuery).getSingleResult();
```

Tương tự JPQL, data query và count query cần cùng predicate/filter semantics.

### 26.3. Criteria join không tự là fetch join

`root.join("lines")` là join để dựng predicate/result. Nếu muốn fetch association, Criteria API có `root.fetch("lines", JoinType.LEFT)`, nhưng **fetch collection cộng pagination vẫn có giới hạn tương tự JPQL JOIN FETCH**.

Không dùng Criteria API như cách né quy tắc cardinality.

---

## 27. EXISTS thay JOIN khi chỉ cần lọc root

Đây là một nguyên tắc rất hữu ích:

> Nếu ứng dụng chỉ cần biết một root có **ít nhất một child thỏa điều kiện**, một truy vấn `EXISTS` thường biểu diễn nhu cầu rõ hơn JOIN + DISTINCT.

### 27.1. Bằng JOIN

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity >= :minQuantity
```

### 27.2. Bằng EXISTS

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.quantity >= :minQuantity
)
```

Về mặt root qualification, hai cách có thể cho cùng tập Orders với các giả định tương ứng. Nhưng EXISTS tránh yêu cầu kết quả trung gian phải chứa một row cho từng Line match ở mô hình logic.

### 27.3. NOT EXISTS cho trường hợp không có child

Muốn tìm Orders **không có Line**:

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

Order#1003 trong dữ liệu mẫu sẽ phù hợp.

Một cách khác dùng LEFT JOIN + IS NULL:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN o.lines l
WHERE l.id IS NULL
```

Nhưng cần cẩn thận khi thêm các điều kiện join hoặc nhiều associations. NOT EXISTS thường thể hiện ý nghĩa phủ định “không có child nào” rõ ràng hơn.

---

## 28. Một root có nhiều child phù hợp: các trường hợp khó

Giả sử tìm Orders có SKU A và sort theo thời điểm tạo giảm dần. Order#1004 có hai Lines A. Với `EXISTS`, Order#1004 chỉ có một vị trí trong danh sách.

Nhưng nếu yêu cầu:

> Lấy Orders có ít nhất hai Lines SKU A.

Dùng aggregate/having hoặc correlated subquery thích hợp:

```jpql
SELECT o.id, COUNT(l)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
GROUP BY o.id
HAVING COUNT(l) >= :minimumMatches
ORDER BY o.id
```

Query trả một row mỗi root group thỏa điều kiện. Nếu cần list Orders, có thể page IDs theo tập root đủ điều kiện rồi fetch Orders/Lines.

### 28.1. COUNT DISTINCT child khi có nhiều joins

Nếu query JOIN thêm association khác khiến Line rows bị nhân, `COUNT(l)` có thể không còn là số Lines duy nhất. Khi nghiệp vụ cần đếm distinct Lines:

```jpql
COUNT(DISTINCT l.id)
```

Nhưng phải hiểu nguồn multiplication. COUNT DISTINCT không tự sửa SUM tiền hoặc bộ lọc sai.

### 28.2. Một row root nhưng có nhiều giá trị sort của child

Nếu sort theo child property, phải chọn quy tắc:

- `MIN(l.sku)`.
- `MAX(l.sku)`.
- `MAX(l.createdAt)` nếu có timestamp child.
- Số child phù hợp `COUNT(l)`.
- Hoặc một “representative child” được xác định bằng nghiệp vụ.

Không có `DISTINCT` nào tự quyết định “lấy giá trị child nào để sort root”.

---

## 29. Keyset/seek pagination: tránh offset lớn

Offset pagination thường dùng:

```sql
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
```

Database có thể phải duyệt/sắp xếp hoặc bỏ qua lượng lớn root rows trước khi lấy trang sâu. Với dữ liệu lớn, hiệu năng và tính ổn định khi concurrent inserts/deletes có thể trở thành vấn đề.

Keyset pagination dùng giá trị cuối của page trước làm cursor.

### 29.1. Ví dụ sort key duy nhất

Thứ tự:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

Giả sử bản ghi cuối page là:

```text
createdAt = 2026-11-04T09:00
id        = 1004
```

Trang tiếp theo:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE
    o.createdAt < :lastCreatedAt
    OR (
        o.createdAt = :lastCreatedAt
        AND o.id < :lastId
    )
ORDER BY o.createdAt DESC, o.id DESC
```

Dùng `setMaxResults(pageSize)`, không cần OFFSET lớn. Cặp `(createdAt,id)` xác định vị trí tiếp tục trong thứ tự giảm dần.

### 29.2. Khi có filter theo child

Kết hợp EXISTS:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :prefix
)
AND (
    o.createdAt < :lastCreatedAt
    OR (
        o.createdAt = :lastCreatedAt
        AND o.id < :lastId
    )
)
ORDER BY o.createdAt DESC, o.id DESC
```

Đây là query vẫn có **một row cho mỗi Order**, thuận lợi cho keyset. Bước fetch graph theo IDs thực hiện tương tự chiến lược hai bước.

### 29.3. Cần chú ý NULL và hướng sort

Nếu sort key có NULL, biểu thức so sánh `<`/`>` có ba-valued logic. Cần định nghĩa vị trí NULL, normalization hoặc keyset predicate phù hợp. Nếu sort có nhiều hướng ASC/DESC trộn nhau, điều kiện cursor phải thay đổi tương ứng.

### 29.4. Keyset không tự tạo snapshot bất biến

Nếu dữ liệu thay đổi giữa hai request, keyset có thể ổn định hơn offset với một số kiểu insert/delete trước vị trí cursor, nhưng không bảo đảm snapshot tuyệt đối; đặc biệt nếu sort keys của bản ghi bị sửa.

Khi yêu cầu duyệt toàn bộ dữ liệu tại một thời điểm xác định, cần snapshot/version/policy phù hợp hoặc export job riêng.

---

## 30. Offset pagination: rủi ro dữ liệu thay đổi giữa các trang

Giả sử page size 2, thứ tự IDs:

```text
Ban đầu: [105, 104, 103, 102, 101]

Page 0 OFFSET 0:
  [105, 104]
```

Giữa hai request, một Order mới ID 106 được tạo và đứng đầu:

```text
Mới: [106, 105, 104, 103, 102, 101]
```

Page 1 OFFSET 2:

```text
[104, 103]
```

Order#104 bị lặp dù query không JOIN. Đây là **vấn đề inherent của offset pagination với dữ liệu biến động**, khác lỗi join multiplication.

### 30.1. Hai loại lặp cần phân biệt

| Loại lặp | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Lặp root do JOIN to-many | Một root tạo nhiều SQL rows trước pagination | DISTINCT root đúng cách, EXISTS, 2-step page IDs |
| Lặp root do dữ liệu thay đổi giữa requests | OFFSET dựa trên vị trí bị xê dịch sau insert/delete/update | Keyset cursor, snapshot/policy phù hợp |

Sửa JOIN không giải quyết đồng thời pagination drift do concurrent writes.

---

## 31. DISTINCT và ORDER BY: giới hạn SQL/JPQL

Một query có `DISTINCT` đôi khi gặp lỗi database:

```text
ORDER BY expression must appear in select list
```

hoặc giới hạn tương đương theo SQL dialect. Điều này thường liên quan đến việc `ORDER BY` một biểu thức không tương thích với tập columns DISTINCT.

Ví dụ:

```sql
SELECT DISTINCT o.id, o.order_number
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
ORDER BY l.sku;
```

Tại sao DB khó quyết định? Order#1001 có nhiều `l.sku` khác nhau. Chọn một row duy nhất theo `o.id` không tự xác định `l.sku` nào dùng để sắp.

### 31.1. Không thêm child column vào SELECT chỉ để qua lỗi

Nếu thêm `l.sku` để thỏa quy tắc ORDER BY, DISTINCT sẽ khử theo `(o.id,o.orderNumber,l.sku)`, và root lại bị lặp.

Thay vào đó cần sửa **ngữ nghĩa sort**:

```sql
SELECT o.id, MIN(l.sku) AS sort_sku
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
GROUP BY o.id
ORDER BY MIN(l.sku), o.id;
```

Hoặc sort theo thuộc tính root duy nhất, hoặc tách root page và child query.

### 31.2. DISTINCT cũng có chi phí database

`DISTINCT` có thể dùng hash aggregate hoặc sort/unique, cần memory/temp space và xử lý nhiều rows. Nếu dữ liệu join to-many lớn, chi phí này đáng kể.

Đừng đưa DISTINCT như một keyword “bảo hiểm” vào mọi query. Hãy xác nhận vì sao dữ liệu bị trùng và muốn khử trùng theo hạt nào.

---

## 32. Hai bước fetch cần xử lý giới hạn IN list

Bước 2 dùng:

```jpql
WHERE o.id IN :ids
```

với page size 20–100 thường đơn giản. Nhưng một page cực lớn có thể gặp:

- Giới hạn số bind parameters hoặc kích thước SQL.
- Query plan không tối ưu cho IN quá dài.
- Bộ nhớ lớn khi fetch hàng nghìn roots và collections.
- Response API quá nặng.
- Giới hạn transport/serialization.

### 32.1. Vì sao page size cần giới hạn?

Nếu client tự do yêu cầu `pageSize=100000`, chiến lược hai bước vẫn có thể làm server quá tải. Nên có max page size được cấu hình theo use case.

### 32.2. Chia IN list có phải luôn đúng?

Có thể chia IDs thành các batches nhỏ để fetch, nhưng cần:

- Không thay đổi tập root IDs và thứ tự trang.
- Không vô tình trả duplicate entities.
- Tập hợp kết quả theo ID rồi sắp lại.
- Đảm bảo transaction/consistency policy.
- Cân nhắc query count tăng.

Không chia theo kiểu mỗi Order một query nếu có thể fetch theo batch; làm vậy có thể tái tạo N+1.

---

## 33. Multiple collection fetch: vấn đề khác DISTINCT

Giả sử `PurchaseOrder` còn có collection `payments`:

```text
Order#1001:
  lines    = 20
  payments = 10
```

Query fetch cả hai:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.payments
WHERE o.id IN :ids
```

SQL JOIN có thể tạo **20 × 10 = 200 rows cho một Order**. Với nhiều roots, số rows tăng rất nhanh.

Một số Hibernate mappings còn có giới hạn fetch đồng thời nhiều bag collections (`MultipleBagFetchException` trong các trường hợp phù hợp), đây là chi tiết provider-specific.

**Dù đã phân trang IDs trước, bước fetch có thể vẫn quá nặng khi fetch nhiều to-many collections.**

Cách khác:

1. Fetch root và một collection cần thiết.
2. Fetch collection thứ hai bằng query batch theo IDs.
3. Dùng DTO child query riêng.
4. Tránh một JOIN khổng lồ tạo Cartesian multiplication.

DISTINCT chỉ xử lý duplicate root ở kết quả, không loại bỏ chi phí xử lý tất cả tổ hợp rows.

---

## 34. N+1 vẫn có thể xuất hiện sau khi sửa pagination

Nếu đã page IDs rồi fetch Orders và Lines, nhưng DTO builder gọi:

```java
order.getCustomer().getDisplayName();
```

với Customer LAZY chưa được fetch, mỗi Order có Customer khác nhau có thể phát sinh SELECT bổ sung.

### 34.1. Kết hợp một to-one và một to-many khi phù hợp

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Không có pagination trực tiếp tại bước này. Fetch Customer to-one không nhân root thêm theo cardinality mapping; fetch Lines nhân rows theo collection, nhưng số roots đã được giới hạn.

### 34.2. Không thay mọi association thành EAGER

Đổi static mapping sang EAGER có thể làm các query khác tải thừa. Với API danh sách, cân nhắc DTO projection; với API chi tiết, chọn fetch plan riêng.

### 34.3. SQL log là nguồn kiểm chứng

Một query “chỉ có hai JPQL statements” vẫn có thể phát nhiều SQL SELECTs vì lazy associations trong lúc map DTO. Cần đo toàn bộ use case tới khi response đã được tạo, không chỉ hai lời gọi `createQuery`.

---

## 35. DTO aggregate bằng nhiều queries

Một thiết kế khác không sử dụng fetch join:

**Query 1:** page một DTO mỗi Order:

```jpql
SELECT NEW demo.dto.OrderListRow(
    o.id,
    o.orderNumber,
    o.createdAt,
    c.displayName
)
FROM PurchaseOrder o
JOIN o.customer c
ORDER BY o.createdAt DESC, o.id DESC
```

**Query 2:** lấy Lines cho IDs có trong page:

```jpql
SELECT NEW demo.dto.OrderLineRow(
    l.order.id,
    l.id,
    l.sku,
    l.quantity
)
FROM OrderLine l
WHERE l.order.id IN :ids
ORDER BY l.order.id, l.id
```

Sau đó Java group:

```java
Map<Long, List<OrderLineRow>> linesByOrder = new HashMap<>();

for (OrderLineRow line : lineRows) {
    linesByOrder
        .computeIfAbsent(
            line.orderId(),
            ignored -> new ArrayList<>()
        )
        .add(line);
}
```

Cách này có những ưu điểm:

- Không cần managed entity graph cho màn hình đọc.
- Chọn đúng columns.
- Không gặp pagination trên collection fetch join.
- Có thể group child theo root.
- Kiểm soát thứ tự parent và child riêng.

Hạn chế:

- Có ít nhất hai SQL queries.
- Cần tự xây DTO chứa nested lines.
- Phải kiểm soát consistency nếu dữ liệu thay đổi giữa các queries.
- Nếu API cần thay đổi managed graph, DTO read model không thay thế transaction write model.

**Số query ít nhất không đồng nghĩa hiệu năng tối ưu nhất.**

---

## 36. Kiểm thử tính đúng của pagination

Khi có JOIN/DISTINCT, kiểm thử không nên chỉ kiểm tra “page có trả data” hay “SQL chạy được”.

### 36.1. Bộ dữ liệu kiểm thử tối thiểu

Phải có:

1. Parent không có child.
2. Parent có đúng một child.
3. Parent có nhiều children.
4. Parent có nhiều children **cùng thỏa filter**.
5. Parent có children nhưng **không child nào thỏa filter**.
6. Hai parents cùng giá trị sắp xếp.
7. Một parent có child thuộc nhiều điều kiện khác nhau.
8. Nhiều roots đủ để có ít nhất ba trang.

### 36.2. Các invariant quan trọng

Nếu bài toán là một row mỗi Order:

- Một Order không xuất hiện nhiều lần trong cùng một page.
- Một Order không xuất hiện ở hai pages khi dataset cố định và thứ tự không đổi.
- Tổng hợp tất cả pages cho đúng tập root Orders.
- Tổng số elements bằng số Orders thỏa filter, không bằng số Lines.
- Page size được hiểu theo **Orders**, không phải joined rows.
- Thứ tự đúng theo ORDER BY, có khóa phụ duy nhất.
- Parent không có child chỉ bị loại khi nghiệp vụ thực sự yêu cầu.
- Nếu trả collection, collection của mỗi Order phải đầy đủ theo fetch contract, không bị cắt vì LIMIT.
- Query không tải lượng dữ liệu bất thường cho page nhỏ.

### 36.3. Không kiểm thử chỉ bằng một Order có một Line

Nếu mỗi Order chỉ có một Line, JOIN to-many không làm nhân rows và test dễ tạo cảm giác an toàn giả. Phải có Order có ít nhất ba Lines và page size nhỏ hơn số Lines để tái hiện vấn đề.

---

## 37. Bài thực hành A — Tái hiện trang thiếu/lặp root

1. Tạo dữ liệu phần 3.
2. Chạy SQL `LEFT JOIN` Order–Line.
3. Ghi lại tám SQL rows và năm Orders duy nhất.
4. Phân trang SQL theo size 2.
5. Ghi page 0 gồm hai rows Order#1001.
6. Ghi page 1 có Order#1001 và Order#1002.
7. Thử deduplicate ở Java sau pagination.
8. Giải thích vì sao page 0 chỉ còn một root và Order#1001 vẫn lặp qua pages.
9. So sánh với query page IDs theo Order ID.
10. Kết luận rằng lỗi đến từ **thứ tự JOIN → LIMIT/OFFSET → DISTINCT Java**.

## 38. Bài thực hành B — SQL DISTINCT theo projection

Chạy hai SQL queries:

```sql
SELECT DISTINCT o.id, o.order_number
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku LIKE 'A-%';
```

và:

```sql
SELECT DISTINCT o.id, o.order_number, l.sku
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
WHERE l.sku LIKE 'A-%';
```

Yêu cầu:

1. Đếm SQL rows của từng query.
2. Giải thích vì sao Order#1004 một lần trong query đầu.
3. Giải thích vì sao Order#1004 hai lần trong query sau.
4. Xác định hạt dữ liệu của từng projection.
5. Kết luận vì sao thêm DISTINCT chưa chắc tạo một row/Order.

## 39. Bài thực hành C — JPQL DISTINCT và countDistinct

1. Chạy `SELECT o FROM PurchaseOrder o JOIN o.lines l WHERE ...`.
2. Ghi số phần tử result list và số Order IDs khác nhau.
3. Thêm `SELECT DISTINCT o`.
4. Chạy `COUNT(o)` trên cùng JOIN.
5. Chạy `COUNT(DISTINCT o.id)`.
6. So sánh tổng của Page theo đúng root count.
7. Kiểm tra SQL do provider sinh; đừng giả định provider luôn có cùng chiến lược DISTINCT.
8. Giải thích khi nào có thể bỏ DISTINCT nhờ EXISTS.

## 40. Bài thực hành D — JOIN FETCH và phân trang

1. Tạo 100 Orders, mỗi Order có 3–20 Lines.
2. Chạy `LEFT JOIN FETCH o.lines` và phân trang size 10.
3. Bật SQL logging và provider warnings.
4. Quan sát có warning về in-memory pagination hoặc không.
5. Nếu dùng Hibernate, thử cấu hình fail-fast dành cho collection fetch pagination trong dự án test.
6. Không đổi dữ liệu production chỉ để tạo lỗi.
7. Dùng chiến lược page IDs rồi fetch collection.
8. So sánh số SQL rows, số Orders trả về, bộ nhớ và thời gian.
9. Xác nhận mọi Order có Lines đầy đủ theo dữ liệu nền.

## 41. Bài thực hành E — EXISTS thay JOIN DISTINCT

Bài toán: “Orders có ít nhất một Line với SKU bắt đầu A”.

1. Viết query JOIN DISTINCT.
2. Viết query EXISTS.
3. Chạy hai query trên cùng dữ liệu.
4. So sánh tập Order IDs.
5. So sánh count tương ứng: COUNT DISTINCT cho JOIN và COUNT(o) cho EXISTS.
6. Kiểm tra execution plans trên database đang dùng.
7. Thử Order có 50 Lines cùng match.
8. Giải thích vì sao EXISTS vẫn biểu diễn một lần/root về mặt logic.
9. Thử NOT EXISTS để tìm Orders không có Lines.

## 42. Bài thực hành F — Hai bước và thứ tự IN

1. Query page IDs theo `createdAt DESC, id DESC`.
2. Fetch Orders và Lines với `WHERE o.id IN :ids`.
3. Ghi thứ tự results thực tế của query fetch.
4. Tạo `Map<Long, PurchaseOrder>`.
5. Duyệt IDs ban đầu để khôi phục thứ tự.
6. Chuyển sang DTO.
7. So sánh kết quả với API page mong đợi.
8. Thử page không có IDs và xác nhận không chạy query `IN ()` không hợp lệ.
9. Thử page size quá lớn để thấy cần giới hạn page size.
10. Bổ sung `JOIN FETCH o.customer` nếu DTO cần Customer name.

## 43. Bài thực hành G — Spring Data Page và Slice

1. Viết repository `Page<PurchaseOrder>` dùng EXISTS.
2. Khai báo `countQuery` tường minh.
3. Gọi `PageRequest.of(0, 2, Sort...)`.
4. Kiểm tra `getContent()`, `getTotalElements()`, `getTotalPages()`.
5. Đổi data query sang JOIN DISTINCT và countQuery sang COUNT DISTINCT.
6. Cố ý dùng count thường trong test để thấy totalElements bị sai.
7. Thử `Slice<PurchaseOrder>` khi không cần totalElements.
8. Giải thích vì sao Slice không sửa lỗi duplicate root do JOIN.
9. Không kết hợp collection fetch join với Pageable mà không đánh giá provider.

## 44. Bài thực hành H — Sort theo child

1. Tạo Order có Lines SKU `A-01`, `B-01` và `C-01`.
2. Thử `SELECT DISTINCT o JOIN o.lines l ORDER BY l.sku`.
3. Giải thích không có một SKU duy nhất của root.
4. Định nghĩa yêu cầu rõ: “sort theo SKU nhỏ nhất”.
5. Viết `GROUP BY o.id ORDER BY MIN(l.sku), o.id`.
6. Chạy trên Order không có Line.
7. Kiểm tra vị trí NULL trong ORDER BY theo DBMS.
8. Quyết định chính sách “Orders không Line đứng trước hay sau”.
9. Nếu cần nhất quán across DBMS, dùng CASE sort rank hoặc một normalization rõ ràng.

## 45. Bài thực hành I — Offset và keyset khi dữ liệu biến động

1. Tạo 30 Orders, sort theo `createdAt DESC, id DESC`.
2. Lấy page 0 bằng offset.
3. Insert một Order mới đứng trước trang đầu.
4. Lấy page 1 bằng offset.
5. Ghi nhận nguy cơ duplicate hoặc missing root.
6. Thực hiện lại với keyset cursor `(createdAt,id)`.
7. So sánh kết quả trong tình huống có insert.
8. Thử update sort key của một Order giữa hai requests.
9. Giải thích vì sao keyset giảm một số rủi ro drift nhưng không tạo snapshot bất biến.

## 46. Bài thực hành J — Nhiều collections

1. Mở rộng Order có `payments` hoặc `shipments`.
2. Tạo 10 Lines và 5 Payments cho một Order.
3. Fetch join cả hai collection trong một query thử.
4. Ghi số SQL rows trung gian.
5. Xác định nguy cơ Cartesian multiplication.
6. Nếu Hibernate báo lỗi fetch nhiều bag collections, ghi nhận đây là giới hạn provider/mapping cụ thể.
7. Tách thành queries độc lập.
8. So sánh bộ nhớ, SQL rows và total time.
9. Không dùng DISTINCT để suy rằng 50 SQL rows đã biến mất trước khi database xử lý chúng.

---

## 47. Checklist trước khi đưa JOIN + DISTINCT pagination vào production

| Câu hỏi | Điều cần xác định |
|---|---|
| Đơn vị của một trang là gì? | Order, Line, DTO tuple hay group |
| Một root có thể tạo nhiều rows qua JOIN không? | Kiểm tra cardinality to-many |
| Có JOIN FETCH collection không? | Cẩn trọng với `setFirstResult`/`setMaxResults` |
| DISTINCT đang khử theo gì? | Entity root hay toàn bộ tuple của SELECT |
| Có child field trong DTO projection không? | Có thể một DTO cho mỗi child |
| Count query đếm đúng đơn vị không? | COUNT DISTINCT root hoặc EXISTS |
| Có filter dùng child không? | EXISTS có thể phù hợp hơn JOIN |
| JOIN LEFT có bị WHERE loại null rows không? | Kiểm tra ON vs WHERE |
| Có ORDER BY duy nhất/ổn định không? | Thêm ID tie-breaker |
| Có sort theo thuộc tính collection không? | Định nghĩa MIN/MAX/COUNT hoặc child được chọn |
| Có nhiều collections được fetch không? | Nguy cơ Cartesian explosion |
| Có phân trang bằng SQL LIMIT trên fetch join không? | Có thể cắt collection hoặc in-memory pagination |
| Có cần child đầy đủ không? | Page IDs rồi fetch graph hoặc query child DTO |
| Query fetch theo IN giữ thứ tự không? | Không; cần khôi phục theo page IDs |
| Page size có giới hạn không? | Tránh IN quá dài và graph quá lớn |
| Có cần totalElements không? | Page hay Slice |
| Count query có cùng permission/tenant filters? | Tránh sai số và rò rỉ thông tin |
| Dữ liệu có thể thay đổi giữa hai queries không? | Isolation/snapshot policy |
| Dữ liệu thay đổi giữa các trang không? | Offset drift/keyset |
| Lazy to-one có gây N+1 khi map DTO? | Cần fetch plan đúng |
| Có benchmark trên DB thật chưa? | EXPLAIN, SQL count, rows, time, memory |
| Có test parent 0/1/n children? | Bắt buộc để lộ lỗi |
| Có kiểm tra phiên bản JPA/provider không? | Không dựa mù vào behavior riêng Hibernate |

---

## 48. Các sai lầm thường gặp

### 48.1. “Có DISTINCT rồi thì JOIN FETCH collection phân trang an toàn”

Không. DISTINCT root không giải quyết đầy đủ việc SQL LIMIT/OFFSET cắt giữa các children và không loại chi phí materialize joined rows.

### 48.2. “Một trang yêu cầu 20 tức chắc chắn trả 20 Orders”

Không nếu query đang paginate SQL rows rồi khử trùng lặp ở Java. Kết quả có thể chỉ còn 1–19 unique roots dù còn nhiều Orders đủ điều kiện.

### 48.3. “DISTINCT có nghĩa duy nhất theo bảng đầu tiên”

SQL DISTINCT xét toàn bộ projection. Nếu SELECT có child fields khác nhau, một Order vẫn có nhiều result tuples.

### 48.4. “Đếm bằng COUNT(o) luôn đúng”

Sai với JOIN to-many tạo nhiều matches cho cùng root. Nếu nội dung page là Orders, thường cần COUNT DISTINCT root hoặc EXISTS-based count.

### 48.5. “Spring Data tự sinh count đúng với mọi JOIN”

Không nên mặc định như vậy. Với query phức tạp, hãy đọc/định nghĩa countQuery và xác minh kết quả.

### 48.6. “LEFT JOIN giữ tất cả parent trong mọi trường hợp”

Không nếu WHERE chứa predicate trên child khiến null-extended rows bị loại. Cần phân biệt yêu cầu filter root với yêu cầu hiển thị optional child.

### 48.7. “JOIN FETCH chỉ làm SQL nhanh hơn JOIN”

JOIN FETCH thay đổi fetch plan/lifecycle của association khi dựng entity, không chỉ là SQL optimization. Có thể rất tốn kém với collection lớn.

### 48.8. “JOIN bình thường cũng tự fetch collection”

Không. JOIN thường có thể được dùng để lọc mà association vẫn chưa được loaded theo fetch plan.

### 48.9. “Để ORDER BY l.sku rồi DISTINCT o là đã có thứ tự Order đúng”

Một Order có nhiều SKU. Phải định nghĩa sort key duy nhất cho mỗi Order; thêm DISTINCT không tự chọn child để sort.

### 48.10. “IN :ids giữ nguyên thứ tự của List IDs”

SQL không có bảo đảm như vậy nếu không có ORDER BY phù hợp. Thường cần re-order trong Java.

### 48.11. “Đã chia hai bước thì không còn N+1”

Có thể vẫn còn N+1 với các to-one LAZY khác khi map DTO. Kiểm tra toàn bộ fetch plan.

### 48.12. “Hai bước tự bảo đảm snapshot nhất quán”

Không. Isolation và concurrent writes vẫn quan trọng.

### 48.13. “Một SQL tốt hơn hai SQL”

Không chắc. Một SQL JOIN khổng lồ có thể tốn nhiều hơn hai queries nhỏ: một để page IDs, một để fetch child của page.

### 48.14. “Page size lớn làm tăng throughput vô hạn”

Không. Graph size, parameter limits, serializer, memory và DB rows có thể tăng rất mạnh.

### 48.15. “Slice bỏ COUNT nên mọi vấn đề biến mất”

Slice giúp tránh tổng số elements trong một số use cases; duplicate root và collection fetch pagination vẫn cần xử lý riêng.

### 48.16. “COUNT DISTINCT sửa luôn SUM khi JOIN nhiều collections”

Không. Tổng tiền có thể bị nhân lên do join multiplication; phải thiết kế aggregate theo hạt dữ liệu đúng.

### 48.17. “Chỉ test một child mỗi parent là đủ”

Không. Test phải có nhiều child cùng match, parent không child và nhiều trang để phát hiện lỗi cardinality.

---

## 49. Tóm tắt lựa chọn giải pháp

| Bài toán | Cách tiếp cận phù hợp |
|---|---|
| Page Orders không cần child | Query root với ORDER BY ổn định |
| Page Orders cần tên Customer (to-one) | JOIN to-one + DTO projection hoặc fetch plan rõ |
| Lọc Orders nếu có một Line khớp | EXISTS + root pagination |
| Lọc Orders bằng JOIN to-many | SELECT DISTINCT root + COUNT DISTINCT, đo SQL |
| Page Orders và toàn bộ Lines | Page IDs trước, fetch Lines theo IDs sau |
| Page Orders với nested DTO Lines | Page root DTO rồi query Line DTO theo IDs |
| Page Orders có nhiều collections | Tránh fetch tất cả to-many trong một JOIN |
| Page cần totalElements | COUNT đúng hạt root; Page |
| Chỉ cần “load more” | Slice hoặc keyset, không nhất thiết COUNT |
| Sort theo child | Định nghĩa MIN/MAX/COUNT/representative child |
| Trang sâu, dataset lớn | Cân nhắc keyset và index theo sort key |
| Dữ liệu thay đổi liên tục | Hiểu offset drift, snapshot/consistency policy |
| Query JOIN FETCH + Pageable | Tránh mặc định; kiểm tra giới hạn provider |
| API danh sách đơn giản | Ưu tiên DTO projection thay vì graph quá lớn |

### Sơ đồ quyết định

```text
                    CẦN PHÂN TRANG
                           |
                           v
              Một phần tử là gì?
                           |
             +-------------+-------------+
             |                           |
        ROOT ENTITY                  CHILD / DTO ROW
             |                           |
             v                           v
   Có JOIN qua to-many?          Có thể page trực tiếp
             |                   theo đơn vị DTO row
        +----+----+
        |         |
       Không      Có
        |         |
        v         v
    Root query   JOIN chỉ để lọc root?
    ổn định       |
              +---+---+
              |       |
             Có      Không, cần child
              |       |
              v       v
          Dùng EXISTS  Page IDs trước
          hoặc DISTINCT   |
          root + COUNT    v
              |       Fetch child/DTO
              |       theo IDs của page
              |           |
              +-----+-----+
                    |
                    v
             ORDER BY ổn định
             + count nếu cần
                    |
                    v
              ĐO SQL VÀ TEST
```

## 50. Câu hỏi ôn tập

1. Vì sao một Order có ba Lines tạo ba SQL rows khi JOIN?
2. Một SQL row, một managed entity instance và một DTO row có giống nhau không?
3. Tại sao một `List<PurchaseOrder>` có thể chứa nhiều vị trí cùng trỏ đến một managed Order?
4. SQL DISTINCT khử trùng lặp dựa trên cột nào?
5. Tại sao thêm `l.sku` vào SELECT DISTINCT khiến Order có thể xuất hiện nhiều lần?
6. `SELECT DISTINCT o` khác `SELECT DISTINCT NEW OrderSkuRow(...)` ở mức hạt dữ liệu thế nào?
7. Vì sao phân trang SQL rows trước rồi deduplicate Java có thể tạo trang thiếu root?
8. Vì sao Order có thể xuất hiện ở hai pages dù dataset không đổi?
9. JOIN to-one có luôn nhân root rows không?
10. LEFT JOIN to-many có luôn trả một row mỗi parent không?
11. JOIN thường và JOIN FETCH khác nhau ở đâu?
12. Vì sao pagination trực tiếp trên collection fetch join có vấn đề portable?
13. Tại sao Hibernate có thể phân trang collection fetch trong bộ nhớ?
14. Vì sao `DISTINCT` không tự làm collection fetch join an toàn với `LIMIT`?
15. Khi filter root theo child, EXISTS khác JOIN DISTINCT như thế nào?
16. Nếu Order có 20 Lines match, EXISTS tạo bao nhiêu vị trí root logic?
17. `COUNT(o)` khi JOIN Lines khác `COUNT(DISTINCT o.id)` ở đâu?
18. Tại sao count query cần cùng filters và quyền truy cập với data query?
19. Có nên dùng FETCH JOIN trong count query không?
20. Khi nào `COUNT(o)` với EXISTS là đủ?
21. Tại sao `LEFT JOIN ... WHERE l.sku LIKE :prefix` có thể loại Orders không có Line?
22. Khi nào cần dùng JOIN ON thay vì WHERE?
23. Vì sao sort DISTINCT root theo `l.sku` không có nghĩa duy nhất?
24. Làm sao sort Order theo SKU nhỏ nhất của children?
25. Vì sao ORDER BY nên có ID làm tie-breaker?
26. Chiến lược lấy IDs rồi fetch graph gồm những bước nào?
27. Vì sao query `WHERE id IN :ids` không giữ thứ tự List IDs?
28. Hai queries có luôn nhìn cùng snapshot không?
29. Vì sao fetch Customer LAZY trong DTO builder vẫn có thể gây N+1?
30. Tại sao fetch nhiều collections có thể gây Cartesian explosion?
31. Page khác Slice ở thông tin tổng số bản ghi thế nào?
32. Slice có sửa duplicate root của JOIN không?
33. Khi dùng Spring Data, khi nào nên định nghĩa countQuery tường minh?
34. Criteria `distinct(true)` có làm collection fetch pagination portable không?
35. Khi nào dùng DTO projection thay vì entity graph?
36. Khi nào nên query child DTO riêng rồi group trong Java?
37. Offset pagination có nguy cơ gì khi insert Order mới giữa hai request?
38. Keyset pagination với `(createdAt,id)` giải quyết được những vấn đề nào?
39. Keyset có bảo đảm snapshot bất biến không?
40. Vì sao một API page size 20 vẫn có thể đọc hàng triệu SQL rows?
41. Những dữ liệu kiểm thử nào phải có để phát hiện lỗi JOIN + pagination?
42. Vì sao không thể chỉ dựa vào SQL query count để kết luận hiệu năng?
43. JOIN qua nhiều collections ảnh hưởng thế nào đến COUNT và SUM?
44. Khi totalElements sai, bạn sẽ kiểm tra JOIN, DISTINCT hay WHERE trước?
45. Nếu API trả một row cho mỗi Line thay vì mỗi Order, COUNT DISTINCT root có còn phù hợp không?

---

## 51. Ghi nhớ cuối bài

```text
JOIN to-many:
    1 root --> N SQL rows

DISTINCT entity:
    diễn đạt yêu cầu duy nhất root
    nhưng không tự giải quyết mọi pagination/fetch problem

JOIN FETCH collection + LIMIT/OFFSET:
    có thể cắt collection, phát warning/error
    hoặc buộc provider phân trang trong memory

CÁCH ỔN ĐỊNH CHO ROOT PAGE:
    1. Xác định root đủ điều kiện
    2. Chọn một row cho mỗi root
       (EXISTS hoặc DISTINCT đúng hạt)
    3. ORDER BY ổn định với unique tie-breaker
    4. Page root IDs / root DTO
    5. Fetch child của IDs nếu thực sự cần
    6. Khôi phục thứ tự root IDs
    7. COUNT đúng root nếu cần tổng số
    8. Quan sát SQL và kiểm thử dữ liệu nhiều children
```

**Nguyên tắc trọng tâm:** không đánh giá một query phân trang chỉ bằng việc nó có `JOIN` hay `DISTINCT`. Phải xác định **đơn vị của một phần tử trên trang**, **JOIN có nhân root rows hay không**, **DISTINCT đang khử theo giá trị nào**, và **pagination được áp dụng trước hay sau khi bảo đảm duy nhất root**. Với collection fetch, cách thường đáng tin cậy hơn là **phân trang IDs trước, tải graph sau**; với lọc theo child, `EXISTS` thường thể hiện đúng ý định; với màn hình danh sách, DTO projection giúp kiểm soát dữ liệu tải. Cuối cùng, luôn thêm thứ tự ổn định và đo trên provider/database thật, vì tính đúng của phân trang và hiệu năng SQL là hai yêu cầu phải được kiểm chứng riêng.

