# Thiết kế phân trang theo khóa bằng điều kiện JPQL hoặc Criteria

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** DTO và phân trang

Trong một ứng dụng JPA, danh sách đơn hàng, lịch sử giao dịch, thông báo, bản ghi audit hay dòng dữ liệu của một feed thường phải được chia thành những phần nhỏ để giao diện tải nhanh. Cách phổ biến là phân trang theo **vị trí** (*offset pagination*), nhưng với tập dữ liệu lớn hoặc thay đổi liên tục, bỏ qua rất nhiều dòng ở các trang sâu vừa có thể tốn chi phí, vừa dễ khiến một bản ghi xuất hiện lặp hoặc bị bỏ qua giữa các yêu cầu.

**Phân trang theo khóa** (*keyset pagination*, còn gọi là *seek pagination* hoặc *cursor-based pagination*) sử dụng **giá trị khóa sắp xếp của phần tử cuối trang trước** để xác định điểm bắt đầu của trang tiếp theo. Thay vì hỏi “bỏ qua 20.000 bản ghi rồi lấy 20”, truy vấn hỏi “lấy tối đa 20 bản ghi đứng **sau** khóa (thời điểm, ID) đã biết theo thứ tự của danh sách”.

Trong JPQL hoặc Criteria API, ý tưởng được biểu diễn bằng các điều kiện so sánh `<`, `>`, `=` kết hợp `AND` và `OR` theo **thứ tự từ điển** của các khóa sắp xếp.

Ví dụ, với:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

và phần tử cuối trang trước có:

```text
createdAt = 2026-11-05T09:00:00
id        = 1005
```

thì truy vấn trang tiếp theo phải lọc:

```jpql
WHERE
    o.createdAt < :lastCreatedAt
    OR (
        o.createdAt = :lastCreatedAt
        AND o.id < :lastId
    )
```

Điểm cốt lõi không chỉ là viết đúng một biểu thức. Muốn keyset pagination **đúng và bền vững**, phải thiết kế thứ tự toàn phần, khóa phụ duy nhất, filter bất biến giữa các trang, kiểu dữ liệu của cursor, hướng duyệt, chính sách với `NULL`, transaction/concurrency và fetch plan phù hợp với JPA.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khác biệt giữa **offset** và **keyset/seek pagination**.
2. Hiểu vì sao `ORDER BY` cần thứ tự xác định và một **unique tie-breaker** như primary key.
3. Xây đúng điều kiện seek cho một khóa `id ASC` hoặc `id DESC`.
4. Xây đúng điều kiện seek cho bộ khóa `(createdAt, id)`, bao gồm khi nhiều bản ghi có cùng `createdAt`.
5. Diễn đạt thứ tự từ điển nhiều khóa bằng `OR` của các prefix-equality predicates trong JPQL.
6. Viết cùng điều kiện bằng Criteria API: `CriteriaBuilder.lessThan()`, `greaterThan()`, `equal()`, `and()`, `or()`.
7. Định nghĩa DTO/cursor và thực hiện `pageSize + 1` để tính `hasNext` mà không cần `COUNT(*)`.
8. Lấy cursor từ **phần tử cuối cùng được trả** chứ không phải bản ghi “đọc thêm”.
9. Viết truy vấn **lùi về trang trước** với điều kiện và thứ tự ngược phù hợp.
10. Hiểu cách sửa phép so sánh khi các khóa sắp xếp có **chiều ASC/DESC hỗn hợp**.
11. Kiểm soát `NULL`, collation, timestamp precision và các giá trị khóa có thể thay đổi.
12. Giữ mọi business/tenant/permission filters nhất quán giữa các lượt gọi.
13. Dùng `EXISTS` khi lọc entity gốc theo collection để tránh nhân dòng.
14. Chọn DTO projection hoặc hai bước page IDs rồi fetch graph nếu cần các associations.
15. Thiết kế cursor có version, filter fingerprint, tính toàn vẹn và giới hạn thời gian sử dụng.
16. Hiểu keyset giảm một số vấn đề offset nhưng **không tự bảo đảm snapshot bất biến** khi dữ liệu bị cập nhật đồng thời.
17. Đánh giá index, execution plan, latency, SQL rows và correctness.
18. Biết những trường hợp keyset không thay thế được một API yêu cầu nhảy tới trang số N tùy ý.

## 2. Offset pagination và keyset pagination

### 2.1. Offset: vị trí của hàng trong kết quả

JPQL:

```java
List<PurchaseOrder> page = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    ORDER BY o.createdAt DESC, o.id DESC
    """,
    PurchaseOrder.class)
    .setFirstResult(10_000)
    .setMaxResults(20)
    .getResultList();
```

Tương đương ý tưởng SQL:

```sql
SELECT ...
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 10000;
```

Database phải xác định thứ tự rồi bỏ qua những dòng đứng trước phạm vi trang. Tùy index/query plan, offset lớn có thể làm tăng chi phí đọc/duyệt/sắp xếp. Không khẳng định mọi DBMS luôn quét bảng toàn phần, nhưng số dòng phải đi qua trước trang thường tăng theo offset.

### 2.2. Keyset: tiếp tục sau một bộ khóa

JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE
    o.createdAt < :lastCreatedAt
    OR (
        o.createdAt = :lastCreatedAt
        AND o.id < :lastId
    )
ORDER BY o.createdAt DESC, o.id DESC
```

Java chỉ dùng:

```java
.setMaxResults(20)
```

mà **không cần `setFirstResult(10000)`**. Cursor chứa bộ khóa phần tử cuối đã xem.

### 2.3. Hai cách có hợp đồng khác nhau

| Tiêu chí | Offset pagination | Keyset pagination |
|---|---|---|
| Thông tin tiếp tục | `pageIndex` và `pageSize` | Cursor chứa sort-key cuối |
| Cách định vị | Bỏ qua N vị trí | Lọc các khóa đứng sau cursor |
| Trang rất sâu | Có thể ngày càng tốn | Có thể seek hiệu quả với index phù hợp |
| Nhảy trực tiếp đến trang 100 | Tự nhiên | Không tự nhiên nếu chưa có cursor |
| Dữ liệu thêm trước trang đã xem | Có thể dịch offset, gây lặp | Thường bền vững hơn khi sort key ổn định |
| Dữ liệu xóa/sửa sort key | Có thể ảnh hưởng | Vẫn có thể ảnh hưởng |
| Tổng số phần tử | Thường dùng cùng Page/COUNT | Thường không bắt buộc |
| Điều kiện sort | Cần ổn định | **Cần ổn định và đủ thông tin để seek** |
| Có thể dùng index cho cursor? | Có thể dùng cho ORDER BY, vẫn cần bỏ qua vị trí | Thường thuận lợi nếu index khớp filter/sort |
| Thích hợp | Quản trị, trang số cụ thể, tập nhỏ/vừa | Feed, history, infinite scroll, dữ liệu lớn |

**Điểm quan trọng:** keyset là chiến lược dựa trên **thứ tự dữ liệu**, không chỉ là đổi tên `pageIndex` thành `cursor`.

---

## 3. Dữ liệu ví dụ: danh sách đơn hàng

Ta dùng mô hình:

```text
Customer
  id: Long
  displayName: String

PurchaseOrder
  id: Long
  orderNumber: String
  createdAt: LocalDateTime
  status: OrderStatus
  tenantId: Long
  customer: Customer

OrderLine
  id: Long
  order: PurchaseOrder
  sku: String
  quantity: int
```

Lý do chọn `(createdAt, id)`:

- `createdAt` là thuộc tính nghiệp vụ thích hợp để sắp “mới nhất trước”.
- Nhiều Orders có thể được tạo trong cùng thời điểm.
- `id` là duy nhất, giúp phân biệt những Orders cùng timestamp.
- Chúng ta có thể dùng hai giá trị này làm cursor.

### 3.1. Dữ liệu mẫu có trùng thời điểm

| ID | createdAt | status | tenant |
|---:|---|---|---:|
| 110 | 2026-11-08 10:00:00 | PAID | 1 |
| 109 | 2026-11-08 10:00:00 | PAID | 1 |
| 108 | 2026-11-07 15:00:00 | NEW | 1 |
| 107 | 2026-11-07 15:00:00 | PAID | 1 |
| 106 | 2026-11-07 15:00:00 | PAID | 1 |
| 105 | 2026-11-06 08:30:00 | PAID | 1 |
| 104 | 2026-11-05 12:00:00 | PAID | 2 |
| 103 | 2026-11-05 12:00:00 | PAID | 1 |
| 102 | 2026-11-04 09:00:00 | PAID | 1 |
| 101 | 2026-11-03 09:00:00 | CANCELLED | 1 |

Giả sử filter:

```text
tenantId = 1
status = PAID
ORDER BY createdAt DESC, id DESC
```

thì tập hợp có thứ tự:

```text
[110, 109, 107, 106, 105, 103, 102]
```

Với page size 3:

```text
Page đầu:
  [110, 109, 107]

Cursor từ Order#107:
  (2026-11-07 15:00:00, 107)

Page tiếp:
  [106, 105, 103]

Cursor từ Order#103:
  (2026-11-05 12:00:00, 103)

Page cuối:
  [102]
```

Order#108 bị loại vì status NEW; Order#104 bị loại vì tenant 2. Hai giá trị filter phải được áp dụng nhất quán ở **mọi lần gọi tiếp theo**.

---

## 4. Mô hình JPA dùng trong ví dụ

### 4.1. Enum trạng thái

```java
package demo.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

### 4.2. Customer

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

### 4.3. PurchaseOrder

```java
package demo.domain;

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

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private Long tenantId;

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
            Long tenantId,
            OrderStatus status,
            Customer customer) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
        this.createdAt = Objects.requireNonNull(createdAt);
        this.tenantId = Objects.requireNonNull(tenantId);
        this.status = Objects.requireNonNull(status);
        this.customer = Objects.requireNonNull(customer);
    }

    public Long getId() { return id; }

    public String getOrderNumber() { return orderNumber; }

    public LocalDateTime getCreatedAt() { return createdAt; }

    public Long getTenantId() { return tenantId; }

    public OrderStatus getStatus() { return status; }

    public Customer getCustomer() { return customer; }

    public List<OrderLine> getLines() { return lines; }
}
```

Trường `createdAt` được đánh dấu `updatable=false` để thể hiện ý định “thời điểm tạo không thay đổi”. Đây chỉ là một phần của chính sách; cần bảo vệ việc bất biến thông qua domain/database khi nghiệp vụ đòi hỏi, và hiểu rằng SQL ngoài ORM vẫn có thể cập nhật cột nếu database không chặn.

### 4.4. OrderLine

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

    protected OrderLine() {}

    public OrderLine(PurchaseOrder order, String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
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

### 4.5. DDL minh họa

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    tenant_id BIGINT NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

Cú pháp tạo identity tùy DBMS. Các ví dụ keyset không phụ thuộc cách sinh ID cụ thể, miễn ID là giá trị **duy nhất, so sánh được và ổn định**.

---

## 5. Trường hợp đơn giản nhất: keyset theo ID

Giả sử danh sách sắp theo ID tăng:

```jpql
SELECT o
FROM PurchaseOrder o
ORDER BY o.id ASC
```

Trang đầu:

```java
List<PurchaseOrder> firstPage = em.createQuery(
    "SELECT o FROM PurchaseOrder o ORDER BY o.id ASC",
    PurchaseOrder.class)
    .setMaxResults(20)
    .getResultList();
```

Sau khi lấy phần tử cuối ID = 120, trang tiếp:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.id > :lastId
ORDER BY o.id ASC
```

Java:

```java
List<PurchaseOrder> next = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.id > :lastId
    ORDER BY o.id ASC
    """,
    PurchaseOrder.class)
    .setParameter("lastId", 120L)
    .setMaxResults(20)
    .getResultList();
```

### 5.1. Với ID giảm dần

Nếu:

```jpql
ORDER BY o.id DESC
```

thì “sau cursor” là IDs **nhỏ hơn**:

```jpql
WHERE o.id < :lastId
ORDER BY o.id DESC
```

### 5.2. Bảng nhớ dấu so sánh

| Sắp xếp một khóa | Đi tiếp sau khóa cuối |
|---|---|
| `id ASC` | `id > :lastId` |
| `id DESC` | `id < :lastId` |

Không đổi sang `>=` hoặc `<=` theo thói quen: khi dùng so sánh bao gồm bằng, phần tử cuối trang cũ thường xuất hiện lại ở trang mới.

### 5.3. Khi nào chỉ ID đủ?

Sắp theo ID phù hợp nếu business yêu cầu đúng thứ tự ID. Nhưng **ID tăng không nhất thiết đồng nghĩa thời gian tạo tăng** ở mọi kiến trúc:

- Batch import có thể tạo dữ liệu cũ với ID mới.
- UUID ngẫu nhiên không mang thứ tự thời gian.
- Hệ thống phân tán có thể sinh khóa khác thứ tự commit.
- Sequence/identity và transaction commit order không đồng nghĩa tuyệt đối.

Nếu giao diện cần “mới nhất theo thời điểm tạo”, phải sắp theo timestamp phù hợp, rồi dùng ID làm tie-breaker.

---

## 6. Một timestamp không đủ làm cursor

Giả sử sort:

```jpql
ORDER BY o.createdAt DESC
```

và có ba Orders cùng `createdAt = 2026-11-07T15:00:00`:

```text
Order#108
Order#107
Order#106
```

Page size = 2 có thể trả 108 và 107. Nếu cursor chỉ lưu timestamp cuối:

```jpql
WHERE o.createdAt < :lastCreatedAt
```

Order#106 bị bỏ qua vì có timestamp **bằng** cursor.

Nếu sửa thành:

```jpql
WHERE o.createdAt <= :lastCreatedAt
```

Orders 108 và 107 có thể được trả lại ở trang tiếp.

### 6.1. Cần thứ tự toàn phần

Thêm primary key:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

Với mỗi Order, cặp `(createdAt,id)` là duy nhất vì ID duy nhất. Cursor phải lưu **cả hai giá trị**.

### 6.2. Cursor không phải “chỉ lưu ngày”

Cursor tương ứng **đúng điểm đã dừng trong thứ tự**. Nếu thứ tự là (timestamp DESC, id DESC), chỉ giữ timestamp là mất thông tin giữa các bản ghi đồng thời điểm.

### 6.3. Tie-breaker phải ổn định

Một khóa phụ là unique nhưng liên tục đổi giá trị có thể khiến phần tử dịch chuyển trong danh sách. Dùng primary key bất biến thường phù hợp hơn một thuộc tính thứ tự dễ đổi.

---

## 7. Điều kiện keyset hai khóa DESC/DESC

Với:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

ta cần phần tử `o` đứng **sau** cursor `(lastCreatedAt,lastId)` khi:

1. `o.createdAt` **nhỏ hơn** `lastCreatedAt`; **hoặc**
2. Timestamp **bằng nhau**, nhưng `o.id` **nhỏ hơn** `lastId`.

JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE
    o.createdAt < :lastCreatedAt
    OR (
        o.createdAt = :lastCreatedAt
        AND o.id < :lastId
    )
ORDER BY o.createdAt DESC, o.id DESC
```

Hình dung:

```text
ORDER BY createdAt DESC, id DESC

  2026-11-08 10:00  ID 110
  2026-11-08 10:00  ID 109
  2026-11-07 15:00  ID 108
  2026-11-07 15:00  ID 107  <-- CURSOR
  --------------------------------------
  2026-11-07 15:00  ID 106  <-- thuộc trang sau
  2026-11-06 08:30  ID 105
  2026-11-05 12:00  ID 104
```

Điều kiện thứ nhất chọn các ngày cũ hơn; điều kiện thứ hai chọn IDs nhỏ hơn **trong cùng timestamp**.

### 7.1. Luôn đặt parentheses rõ ràng

Sai hoặc dễ hiểu nhầm:

```jpql
WHERE o.status = :status
  AND o.createdAt < :lastCreatedAt
  OR o.createdAt = :lastCreatedAt AND o.id < :lastId
```

Do ưu tiên toán tử, vế sau `OR` có thể không bị giới hạn bởi `o.status = :status`. Điều này có thể làm lộ một Order sai status vào trang.

Đúng:

```jpql
WHERE o.status = :status
  AND (
      o.createdAt < :lastCreatedAt
      OR (
          o.createdAt = :lastCreatedAt
          AND o.id < :lastId
      )
  )
```

Nếu còn tenant filter:

```jpql
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND (
      o.createdAt < :lastCreatedAt
      OR (
          o.createdAt = :lastCreatedAt
          AND o.id < :lastId
      )
  )
```

**Business filters luôn ở ngoài toàn bộ seek predicate.**

---

## 8. Điều kiện keyset hai khóa ASC/ASC

Với:

```jpql
ORDER BY o.createdAt ASC, o.id ASC
```

đi tới phần tử sau theo thứ tự tăng, nên:

```jpql
WHERE
    o.createdAt > :lastCreatedAt
    OR (
        o.createdAt = :lastCreatedAt
        AND o.id > :lastId
    )
```

### 8.1. Bảng hai khóa đồng chiều

| ORDER BY | Predicate “sau cursor” |
|---|---|
| `createdAt ASC, id ASC` | `createdAt > cursorTime OR (createdAt = cursorTime AND id > cursorId)` |
| `createdAt DESC, id DESC` | `createdAt < cursorTime OR (createdAt = cursorTime AND id < cursorId)` |

Không tự đảo dấu vì “trang tiếp” theo cách đếm 1,2,3. Dấu so sánh phải xuất phát từ **chiều sắp xếp của từng khóa**.

---

## 9. Điều kiện keyset với chiều ASC/DESC hỗn hợp

Ví dụ nghiệp vụ muốn:

```jpql
ORDER BY o.priority ASC,
         o.createdAt DESC,
         o.id ASC
```

Ở đây `priority` là số nguyên không NULL trong một entity mở rộng, biểu diễn thứ tự ưu tiên nghiệp vụ. Giả sử cursor gồm `(lastPriority,lastCreatedAt,lastId)`.

Để đi sau cursor:

1. Priority lớn hơn → vì priority ASC.
2. Hoặc priority bằng và createdAt nhỏ hơn → vì timestamp DESC.
3. Hoặc priority và timestamp đều bằng, ID lớn hơn → vì ID ASC.

JPQL:

```jpql
WHERE
    o.priority > :lastPriority
    OR (
        o.priority = :lastPriority
        AND o.createdAt < :lastCreatedAt
    )
    OR (
        o.priority = :lastPriority
        AND o.createdAt = :lastCreatedAt
        AND o.id > :lastId
    )
```

Đây là cách viết mở rộng của **lexicographic comparison** cho nhiều cột.

### 9.1. Mẫu tổng quát

Với khóa sort `k1, k2, ..., kn`, để chọn các hàng đứng sau cursor:

```text
(k1 after cursor.k1)

OR
(k1 = cursor.k1 AND k2 after cursor.k2)

OR
(k1 = cursor.k1 AND k2 = cursor.k2
    AND k3 after cursor.k3)

...

OR
(k1 = ... = cursor.kn-1 AND kn after cursor.kn)
```

Trong đó:

- Với sort `ASC`, “after” dùng `>`.
- Với sort `DESC`, “after” dùng `<`.

### 9.2. Enum có dùng dấu lớn/nhỏ trực tiếp được không?

Không nên giả định phép so sánh thứ tự `>`/`<` trên enum là JPQL portable tương tự Integer. Nếu UI cần sort nghiệp vụ cố định như ACTIVE trước SUSPENDED, nên chọn một **sortable scalar key** rõ ràng (ví dụ `priorityRank` số nguyên) hoặc một biểu thức CASE được thiết kế, và nhất quán giữa ORDER BY/cursor/predicate.

Nếu dùng CASE sort rank, seek predicate cũng phải dùng **chính biểu thức rank tương ứng**, dẫn đến query phức tạp hơn và có thể ảnh hưởng index. Không sắp bằng một biểu thức rồi seek bằng biểu thức khác.

---

## 10. Vì sao tuple comparison không phải giải pháp JPQL portable mặc định?

Trong một số DBMS, SQL có thể diễn đạt:

```sql
WHERE (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
```

Tuy nhiên:

- Row-value/tuple comparison có mức hỗ trợ khác giữa dialects.
- JPQL portable không cung cấp một cú pháp so sánh tuple tổng quát tương đương cho mọi provider.
- Một tuple comparison đơn giản không biểu diễn đúng mọi trường hợp **chiều ASC/DESC hỗn hợp** nếu không biến đổi khóa.
- Cách xử lý `NULL` còn phức tạp hơn.

Vì vậy, với JPQL/Criteria cần tính portable, biểu thức `OR + AND + =` là cách rõ ràng và trực tiếp.

Nếu database cụ thể hỗ trợ tuple comparison hiệu quả và dự án chấp nhận native SQL, có thể kiểm tra một implementation riêng. Nhưng phải ghi rõ phụ thuộc DBMS và test semantics.

---

## 11. Truy vấn đầu tiên không có cursor

Khởi đầu một danh sách mới, ứng dụng chưa có khóa cuối. Cách đơn giản nhất là dùng **một query riêng** không có seek predicate:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
  AND o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

Với `:tenantId = 1`, `:status = PAID` và `setMaxResults(3)`, ta nhận:

```text
[110, 109, 107]
```

Khi đã có cursor:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND (
      o.createdAt < :lastCreatedAt
      OR (
          o.createdAt = :lastCreatedAt
          AND o.id < :lastId
      )
  )
ORDER BY o.createdAt DESC, o.id DESC
```

Trả:

```text
[106, 105, 103]
```

### 11.1. Có thể dùng một query với optional cursor không?

Có thể bắt gặp:

```jpql
WHERE
    (:lastCreatedAt IS NULL OR
       o.createdAt < :lastCreatedAt OR
       (o.createdAt = :lastCreatedAt AND o.id < :lastId))
```

Nhưng cách này dễ tạo:

- Type inference/binding vấn đề với tham số NULL.
- Predicate `OR` phức tạp khó tối ưu hơn.
- Mơ hồ nếu cursor có timestamp NULL hợp lệ.
- Nhu cầu không rõ: chỉ timestamp NULL hay cả cursor không tồn tại?

Đối với keyset có yêu cầu hiệu năng, thường nên **xây query khác nhau khi không có cursor và khi có cursor**, hoặc dùng Criteria để chỉ thêm predicate khi cursor != null.

---

## 12. Cursor cần mang những dữ liệu gì?

Một cursor cơ bản có thể là:

```java
package demo.dto;

import java.time.LocalDateTime;

public record OrderCursor(
    LocalDateTime createdAt,
    Long id
) {}
```

Không chỉ lưu:

```text
id
```

nếu thứ tự chính là timestamp. Không chỉ lưu:

```text
createdAt
```

nếu timestamp có thể trùng.

### 12.1. DTO hiển thị phải có đủ sort-key để sinh cursor

```java
package demo.dto;

import java.time.LocalDateTime;

public record OrderCard(
    Long id,
    String orderNumber,
    LocalDateTime createdAt,
    String customerName
) {}
```

Trường `createdAt` có thể không cần hiển thị trên UI, nhưng query/projection vẫn cần chọn nó để xây cursor chính xác. API có thể không trả riêng timestamp trong item nếu đặt trong opaque cursor, nhưng backend phải giữ được giá trị sau khi đọc từ database.

### 12.2. Nên dùng giá trị nhận về từ database

Nếu entity có timestamp precision thấp hơn Java, ví dụ database lưu mili-giây nhưng ứng dụng tạo nanosecond, không được xây cursor từ **thời gian do caller tự dự đoán**. Hãy lấy cursor từ dữ liệu thực sự được query và mapping trả về.

Nếu serialization làm tròn hoặc cắt microsecond/nanosecond, lần truy vấn sau có thể so sánh với một mốc khác mốc đã sắp, dẫn đến lặp/bỏ hàng. Cursor encode cần giữ đủ precision của sortable key.

---

## 13. Lấy pageSize + 1 để biết hasNext

Với cursor-based API, nhiều giao diện không cần biết tổng số Orders, chỉ cần:

- Items của trang.
- Có còn items sau trang này không?
- Cursor để lấy tiếp.

Thay vì chạy `COUNT(*)`, query **tối đa pageSize+1 rows**:

```text
pageSize = 3
maxResults = 4

Database/provider trả:
  [110, 109, 107, 106]

Content gửi cho client:
  [110, 109, 107]

hasNext:
  true (vì đọc được phần tử thứ tư)

nextCursor:
  lấy từ Order#107
  KHÔNG lấy từ Order#106
```

### 13.1. Vì sao cursor không lấy từ bản ghi thứ tư?

Nếu cursor dùng Order#106 (bản ghi chỉ đọc để peek nhưng chưa trả), lần sau sẽ yêu cầu các khóa **nhỏ hơn Order#106**, khiến Order#106 bị bỏ qua hoàn toàn.

Phải dùng **phần tử cuối cùng thực sự được đưa vào content**, tức Order#107.

### 13.2. Nếu số rows <= pageSize?

`hasNext = false` theo kết quả của query ở thời điểm quan sát. Nếu query lấy được chính xác pageSize rows nhưng không thêm được row thứ pageSize+1, đó cũng là trang cuối theo snapshot/visibility tại thời điểm đó.

Tuy nhiên, dữ liệu mới có thể xuất hiện sau request; hasNext không phải cam kết mọi thời điểm tương lai.

### 13.3. Không dùng count nếu UI không cần

Keyset page phù hợp với infinite scroll: thay vì báo `totalElements` có thể trả `nextCursor` hoặc `null`. Nếu giao diện cần tổng chính xác, có thể chạy count **riêng**, nhưng việc đếm không làm thay đổi seek predicate và có chi phí riêng.

---

## 14. Triển khai JPQL hoàn chỉnh: OrderCard và KeysetSlice

Ta định nghĩa kiểu trả trang:

```java
package demo.dto;

import java.util.List;
import java.util.Objects;

public record KeysetSlice<T>(
    List<T> content,
    boolean hasNext,
    OrderCursor nextCursor
) {
    public KeysetSlice {
        content = List.copyOf(Objects.requireNonNull(content));
        if (!hasNext && nextCursor != null) {
            throw new IllegalArgumentException(
                "nextCursor must be null when hasNext is false");
        }
        if (hasNext && (content.isEmpty() || nextCursor == null)) {
            throw new IllegalArgumentException(
                "Next cursor required for nonempty next page");
        }
    }
}
```

Service đọc trang:

```java
package demo.service;

import demo.domain.OrderStatus;
import demo.dto.KeysetSlice;
import demo.dto.OrderCard;
import demo.dto.OrderCursor;

import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;

import java.util.List;
import java.util.Objects;

public final class OrderSeekReader {

    private static final int MAX_PAGE_SIZE = 100;

    public KeysetSlice<OrderCard> next(
            EntityManager em,
            Long tenantId,
            OrderStatus status,
            OrderCursor after,
            int pageSize) {

        Objects.requireNonNull(em, "em");
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(status, "status");

        if (pageSize <= 0 || pageSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "Invalid page size");
        }

        if (after != null &&
                (after.createdAt() == null || after.id() == null)) {
            throw new IllegalArgumentException(
                "Incomplete cursor");
        }

        String selectAndFilter = """
            SELECT NEW demo.dto.OrderCard(
                o.id,
                o.orderNumber,
                o.createdAt,
                c.displayName
            )
            FROM PurchaseOrder o
            JOIN o.customer c
            WHERE o.tenantId = :tenantId
              AND o.status = :status
            """;

        String seekClause = after == null
            ? ""
            : """
              AND (
                  o.createdAt < :lastCreatedAt
                  OR (
                      o.createdAt = :lastCreatedAt
                      AND o.id < :lastId
                  )
              )
              """;

        String orderClause = """
            ORDER BY o.createdAt DESC, o.id DESC
            """;

        TypedQuery<OrderCard> query = em.createQuery(
            selectAndFilter + seekClause + orderClause,
            OrderCard.class
        );

        query.setParameter("tenantId", tenantId);
        query.setParameter("status", status);

        if (after != null) {
            query.setParameter("lastCreatedAt", after.createdAt());
            query.setParameter("lastId", after.id());
        }

        List<OrderCard> fetched = query
            .setMaxResults(pageSize + 1)
            .getResultList();

        boolean hasNext = fetched.size() > pageSize;

        List<OrderCard> content = hasNext
            ? List.copyOf(fetched.subList(0, pageSize))
            : List.copyOf(fetched);

        OrderCursor nextCursor = null;

        if (hasNext) {
            OrderCard last = content.get(content.size() - 1);
            nextCursor = new OrderCursor(
                last.createdAt(),
                last.id()
            );
        }

        return new KeysetSlice<>(
            content, hasNext, nextCursor
        );
    }
}
```

### 14.1. Vì sao dùng DTO projection?

Query chọn:

```jpql
SELECT NEW demo.dto.OrderCard(
    o.id, o.orderNumber, o.createdAt, c.displayName
)
```

chỉ trả dữ liệu cần hiển thị và làm cursor. Không cần materialize collection `o.lines` hoặc trả managed entity ra controller/serializer.

### 14.2. Vì sao JOIN Customer không làm nhân root?

`o.customer` là to-one, nên trong mô hình Customer bắt buộc và FK hợp lệ, mỗi Order ghép với đúng một Customer. Nếu JOIN một collection `o.lines` thì có thể nhận nhiều rows/Order; lúc đó `pageSize+1` sẽ không còn đúng theo root item trừ khi xử lý cardinality.

### 14.3. Tại sao dùng hai chuỗi query?

Khi `after == null`, không có seek clause và không set cursor parameters. Khi có cursor, thêm điều kiện chính xác với tham số typed. Điều này tránh predicate tùy chọn `:cursor IS NULL OR ...`, thường rõ và dễ tối ưu hơn.

### 14.4. Vì sao code không đếm tổng?

Hợp đồng `KeysetSlice` chỉ có `content`, `hasNext` và `nextCursor`. Nếu ứng dụng cần totalElements, định nghĩa riêng một count query với **cùng business filter** và quyết định khi nào cần gọi. Không nên tính tổng chỉ vì DTO Page truyền thống luôn có trường đó.

### 14.5. Hạn chế của đoạn code

Code tập trung vào thuật toán truy vấn, không bao gồm:

- Mã hóa và ký cursor phía HTTP.
- Tenant ID từ security context.
- Timeout/authorization.
- Transaction boundary của framework.
- Khả năng thay đổi dữ liệu giữa requests.
- Sort options động hoặc nullable timestamps.

Những phần này được trình bày ở các mục tiếp theo.

---

## 15. Sơ đồ toàn bộ luồng keyset API

```text
Client GET /orders?status=PAID&limit=3
             |
             v
        Không có cursor
             |
             v
    Query ORDER BY createdAt DESC, id DESC
         maxResults = 4
             |
             v
   SQL: [110, 109, 107, 106]
             |
             +-- content = [110, 109, 107]
             |
             +-- peek #106 => hasNext=true
             |
             +-- cursor = khóa của #107
             |
             v
     Response + nextCursor
             |
             v
Client GET /orders?status=PAID&cursor=...
             |
             v
Decode/validate cursor (time,id,filter...)
             |
             v
 WHERE time < cursor.time
    OR (time = cursor.time AND id < cursor.id)
             |
             v
   SQL: [106, 105, 103, 102]
             |
             +-- content = [106,105,103]
             |
             +-- cursor = khóa #103
             |
             v
         Tiếp tục...
```

Đây là một API có **tính tuần tự theo cursor**, không phải API “chuyển trực tiếp đến trang số 1.000” chỉ bằng một page index.

---

## 16. Criteria API: biểu diễn cùng điều kiện bằng CriteriaBuilder

Khi filters động, Criteria API giúp xây query từ các biểu thức typed của JPA thay vì ghép chuỗi JPQL thủ công.

Imports chính:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
```

### 16.1. Phần cốt lõi của seek predicate

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

Path<LocalDateTime> createdAt =
    root.get("createdAt");

Path<Long> id = root.get("id");

Predicate timeBefore = cb.lessThan(
    createdAt,
    cursor.createdAt()
);

Predicate sameTimeAndSmallerId = cb.and(
    cb.equal(createdAt, cursor.createdAt()),
    cb.lessThan(id, cursor.id())
);

Predicate seek = cb.or(
    timeBefore,
    sameTimeAndSmallerId
);
```

Nó tương đương:

```jpql
createdAt < :lastCreatedAt
OR (createdAt = :lastCreatedAt AND id < :lastId)
```

### 16.2. Thêm business filter

```java
Predicate tenantFilter =
    cb.equal(root.get("tenantId"), tenantId);

Predicate statusFilter =
    cb.equal(root.get("status"), status);

cq.select(root)
  .where(cb.and(
      tenantFilter,
      statusFilter,
      seek
  ))
  .orderBy(
      cb.desc(createdAt),
      cb.desc(id)
  );
```

Phân trang theo khóa:

```java
List<PurchaseOrder> rows = em.createQuery(cq)
    .setMaxResults(pageSize + 1)
    .getResultList();
```

Không gọi `setFirstResult(...)` trên một keyset query. Mục tiêu là **lọc bằng khóa**, không bỏ qua vị trí.

---

## 17. Criteria API hoàn chỉnh với DTO projection

Ta có thể dùng `CriteriaBuilder.construct()` để tạo DTO thay vì trả entity.

```java
public KeysetSlice<OrderCard> nextWithCriteria(
        EntityManager em,
        Long tenantId,
        OrderStatus status,
        OrderCursor cursor,
        int pageSize) {

    if (pageSize <= 0 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid size");
    }

    if (cursor != null &&
            (cursor.createdAt() == null || cursor.id() == null)) {
        throw new IllegalArgumentException("Invalid cursor");
    }

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<OrderCard> cq =
        cb.createQuery(OrderCard.class);

    Root<PurchaseOrder> order =
        cq.from(PurchaseOrder.class);

    Join<PurchaseOrder, Customer> customer =
        order.join("customer", JoinType.INNER);

    Path<LocalDateTime> createdAt =
        order.get("createdAt");

    Path<Long> id =
        order.get("id");

    List<Predicate> filters = new ArrayList<>();

    filters.add(
        cb.equal(order.get("tenantId"), tenantId));

    filters.add(
        cb.equal(order.get("status"), status));

    if (cursor != null) {
        Predicate seek = cb.or(
            cb.lessThan(createdAt, cursor.createdAt()),
            cb.and(
                cb.equal(createdAt, cursor.createdAt()),
                cb.lessThan(id, cursor.id())
            )
        );
        filters.add(seek);
    }

    cq.select(cb.construct(
        OrderCard.class,
        id,
        order.get("orderNumber"),
        createdAt,
        customer.get("displayName")
    ));

    cq.where(filters.toArray(Predicate[]::new));

    cq.orderBy(
        cb.desc(createdAt),
        cb.desc(id)
    );

    List<OrderCard> fetched = em.createQuery(cq)
        .setMaxResults(pageSize + 1)
        .getResultList();

    boolean hasNext = fetched.size() > pageSize;

    List<OrderCard> content = hasNext
        ? List.copyOf(fetched.subList(0, pageSize))
        : List.copyOf(fetched);

    OrderCursor next = null;
    if (hasNext) {
        OrderCard last = content.get(content.size() - 1);
        next = new OrderCursor(last.createdAt(), last.id());
    }

    return new KeysetSlice<>(content, hasNext, next);
}
```

Để biên dịch phương thức này trong một class, cần imports `Customer`, `PurchaseOrder`, `OrderStatus`, `OrderCard`, `OrderCursor`, `KeysetSlice` và các imports Criteria/JDK đã nêu. Đoạn code thể hiện toàn bộ flow lọc/seek/projection; transaction và REST encoding được quản lý ở tầng bao quanh.

### 17.1. Vì sao Criteria phù hợp filter động?

Nếu `status`, `fromTime`, `customerId` là tùy chọn, chỉ cần thêm predicates tương ứng:

```java
if (status != null) {
    filters.add(cb.equal(order.get("status"), status));
}

if (fromTime != null) {
    filters.add(
        cb.greaterThanOrEqualTo(
            createdAt,
            fromTime
        )
    );
}
```

Trong code mẫu, `tenantId` là filter bắt buộc; không được bỏ nó chỉ vì UI không gửi. Tenant phải được lấy từ authentication/authorization context đáng tin cậy, không đơn thuần tin vào query parameter từ client.

### 17.2. Không dùng Criteria để “quên” thứ tự

Nếu xây seek predicate bằng `createdAt DESC, id DESC` nhưng `cq.orderBy(...)` chỉ sort theo createdAt, bạn lại tạo trường hợp đồng timestamp có thứ tự không xác định. Cả **ORDER BY và predicate** phải dùng cùng sort keys và directions.

### 17.3. Typed path giúp tránh lẫn kiểu

`Path<LocalDateTime>` và `Path<Long>` làm rõ kiểu so sánh. Khi dự án sử dụng JPA static metamodel, có thể thay chuỗi `"createdAt"` bằng generated metamodel attributes để tăng an toàn khi refactor. Đó là cải tiến bảo trì, không thay đổi thuật toán.

---

## 18. So sánh JPQL và Criteria API

| Khía cạnh | JPQL | Criteria API |
|---|---|---|
| Dạng biểu diễn | Chuỗi query dễ đọc | Cấu trúc biểu thức Java |
| Seek predicate | `OR/AND/</=` trong JPQL | `cb.or/and/lessThan/equal` |
| Filters động | Ghép fragment hoặc nhiều query variants | Thêm `Predicate` vào danh sách |
| DTO | `SELECT NEW ...` | `cb.construct(...)` |
| Type safety | Provider validate khi parse/query | Generic types và metamodel hỗ trợ thêm |
| Dễ xem query logic | Thường trực quan với query tĩnh | Có thể dài hơn khi nhiều predicates |
| Dễ tạo nhiều sort variants | Cần kiểm soát string fragments | Xây `Order` và seek predicates tương ứng |
| SQL cuối cùng | Provider tạo | Provider tạo |
| Có tự cải thiện hiệu năng? | Không | Không |
| Có tránh được N+1? | Không tự động | Không tự động |

**Lựa chọn theo tính phức tạp của query và tiêu chuẩn dự án**, không phải vì Criteria “luôn nhanh hơn” JPQL. Provider cuối cùng vẫn dịch hai API sang SQL.

---

## 19. Điều kiện seek nhiều cột trong Criteria

Với `priority ASC, createdAt DESC, id ASC`, code tương đương:

```java
Path<Integer> priority = root.get("priority");
Path<LocalDateTime> createdAt = root.get("createdAt");
Path<Long> id = root.get("id");

Predicate branch1 = cb.greaterThan(
    priority,
    cursor.priority()
);

Predicate branch2 = cb.and(
    cb.equal(priority, cursor.priority()),
    cb.lessThan(createdAt, cursor.createdAt())
);

Predicate branch3 = cb.and(
    cb.equal(priority, cursor.priority()),
    cb.equal(createdAt, cursor.createdAt()),
    cb.greaterThan(id, cursor.id())
);

Predicate seek = cb.or(
    branch1,
    branch2,
    branch3
);

cq.where(cb.and(businessFilter, seek));

cq.orderBy(
    cb.asc(priority),
    cb.desc(createdAt),
    cb.asc(id)
);
```

Đoạn này dùng entity/cursor **mở rộng** có `priority`. Nó minh họa thuật toán chung, không phải code biên dịch độc lập với entity `PurchaseOrder` ở phần 4.

### 19.1. Một cách tránh lỗi khi có nhiều sort options

Nếu API cho client tự chọn bất kỳ sort field/direction nào, việc sinh seek predicate trở nên phức tạp. Cần:

1. **Allowlist** các sort keys hợp lệ.
2. Mỗi sort key có Java/SQL type và direction rõ.
3. Cursor chứa đúng các giá trị của sort keys được chọn.
4. ORDER BY và seek predicate được dựng từ **cùng một mô tả sort**.
5. Unique tie-breaker luôn được thêm cuối nếu chưa có.
6. Thay đổi sort options khiến cursor cũ không còn hợp lệ.
7. Null semantics và collation phải được định nghĩa cho từng field.

Không cho client truyền một chuỗi JPQL tự do rồi nối trực tiếp vào ORDER BY.

---

## 20. Truy vấn lùi về trang trước

Một số giao diện có nút **Previous**. Với danh sách chuẩn:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

giả sử trang hiện tại bắt đầu tại Order có khóa `(firstCreatedAt, firstId)`. Các phần tử **đứng trước** khóa đó có timestamp lớn hơn, hoặc cùng timestamp với ID lớn hơn:

```jpql
WHERE
    o.createdAt > :firstCreatedAt
    OR (
        o.createdAt = :firstCreatedAt
        AND o.id > :firstId
    )
```

Nhưng để lấy **những phần tử gần trang hiện tại nhất** rồi ghép thành một trang trước, thường cần đảo chiều ORDER BY khi truy vấn:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND (
      o.createdAt > :firstCreatedAt
      OR (
          o.createdAt = :firstCreatedAt
          AND o.id > :firstId
      )
  )
ORDER BY o.createdAt ASC, o.id ASC
```

Sau đó:

1. Lấy tối đa `pageSize+1` rows.
2. Xác định còn phần tử ở xa hơn về phía trước hay không.
3. Chỉ giữ `pageSize` phần tử gần cursor nhất.
4. **Đảo ngược danh sách đó** trong Java để response vẫn theo `createdAt DESC, id DESC`.

### 20.1. Ví dụ cụ thể

Danh sách chính:

```text
[110, 109, 108, 107, 106, 105, 104, 103, 102]
```

Đang xem trang:

```text
[106, 105, 104]
```

Phần tử đầu là #106. Truy vấn trước cursor #106 với sort ngược ASC sẽ tìm những phần tử gần nhất:

```text
[107, 108, 109, 110, ...]
```

Với page size 3 và một phần tử extra:

```text
fetched   = [107, 108, 109, 110]
content   = [107, 108, 109]
reversed  = [109, 108, 107]
```

Đó là trang ngay trước trang hiện tại trong thứ tự chính.

### 20.2. Vì sao không chỉ đổi dấu mà vẫn ORDER BY DESC?

Nếu truy vấn những rows `> firstCursor` nhưng giữ DESC, DB sẽ trả từ **đầu danh sách** trước, có thể không phải trang liền kề hiện tại. Sort ngược để lấy các phần tử **gần boundary nhất**.

### 20.3. Cursor cho cả hai chiều

Một response hỗ trợ điều hướng hai chiều có thể mang:

- `prevCursor` từ **phần tử đầu** của content.
- `nextCursor` từ **phần tử cuối** của content.
- `hasPrevious` và `hasNext` được tính theo các query boundaries tương ứng.

Nếu chỉ xây API "Load more" một chiều, không cần phức tạp hóa với backward pagination.

---

## 21. Những phép so sánh với NULL cần chính sách riêng

Một khó khăn lớn của keyset là sort key nullable. Ví dụ:

```java
private LocalDateTime shippedAt; // null nếu chưa giao.
```

Nếu muốn:

```jpql
ORDER BY o.shippedAt DESC
```

các database có thể đặt NULL trước hoặc sau tùy dialect/order direction. Đồng thời:

```jpql
WHERE o.shippedAt < :lastShippedAt
```

không chọn các rows có `shippedAt=NULL`, vì phép so sánh với NULL cho kết quả UNKNOWN.

### 21.1. Cách dễ nhất: chọn sort key NOT NULL

Khi có thể, dùng:

```text
createdAt NOT NULL
id NOT NULL UNIQUE
```

Điều này làm seek predicate đơn giản, có thể dùng index trực tiếp và tránh phải xử lý nhiều nhánh null.

### 21.2. Nếu bắt buộc sort nullable: quy định NULL placement

Ví dụ **NULLS LAST**:

```jpql
ORDER BY
    CASE WHEN o.shippedAt IS NULL THEN 1 ELSE 0 END ASC,
    o.shippedAt DESC,
    o.id DESC
```

Thứ tự logic là:

1. Nhóm `shippedAt IS NOT NULL`, theo shippedAt DESC và ID DESC.
2. Nhóm `shippedAt IS NULL`, theo ID DESC.

Cursor phải ghi nhận **nhóm NULL/non-NULL** cùng key cần thiết.

### 21.3. Seek khi cursor đang ở nhóm không NULL

Với `lastShippedAt != null`:

```jpql
WHERE
    o.shippedAt < :lastShippedAt
    OR (
        o.shippedAt = :lastShippedAt
        AND o.id < :lastId
    )
    OR o.shippedAt IS NULL
```

Điều kiện này chọn các bản ghi non-null đứng sau cursor rồi đến nhóm null ở cuối.

### 21.4. Seek khi cursor thuộc nhóm NULL

Với `lastShippedAt == null`:

```jpql
WHERE o.shippedAt IS NULL
  AND o.id < :lastId
```

Không đưa `:lastShippedAt=null` vào `o.shippedAt < :lastShippedAt` rồi mong so sánh hoạt động.

### 21.5. Lưu ý với filter và thứ tự

Nếu query còn `o.tenantId = :tenantId`, cả hai dạng seek trên phải được đặt trong `AND (...)` cùng filter. Đồng thời ORDER BY phải giống nhau ở mọi trang.

### 21.6. Hiệu năng của CASE sort rank

`CASE WHEN shippedAt IS NULL THEN ...` có thể khiến database phải tính biểu thức và khó dùng trực tiếp index đơn giản. Có thể cân nhắc persisted rank, expression index hoặc một normalization key phù hợp với DBMS nếu workload đòi hỏi; không phải mọi database tối ưu giống nhau.

---

## 22. Sort theo chuỗi: collation và normalization

Giả sử:

```jpql
ORDER BY c.displayName ASC, c.id ASC
```

Cursor sẽ chứa `(displayName, id)`. Nhưng thứ tự String do database quyết định dựa trên collation:

- Phân biệt hoa/thường hay không.
- Phân biệt dấu tiếng Việt hay không.
- Normalization Unicode.
- Locale.
- Whitespace và trailing spaces.
- So sánh giá trị binary hay linguistic.

### 22.1. Cursor phải dùng cùng semantics với ORDER BY

Nếu database ORDER BY dùng collation không phân biệt hoa/thường, nhưng ứng dụng so sánh String bằng Java `String.compareTo()` để dựng cursor logic, kết quả có thể khác. Trong JPQL, hãy để database thực hiện các phép so sánh theo cùng expression/collation của query.

### 22.2. CASE normalization cần nhất quán

Nếu sort bằng:

```jpql
ORDER BY LOWER(c.displayName) ASC, c.id ASC
```

seek predicate cũng phải dùng **LOWER(c.displayName)** tương ứng:

```jpql
WHERE LOWER(c.displayName) > :lastNormalizedName
   OR (
       LOWER(c.displayName) = :lastNormalizedName
       AND c.id > :lastId
   )
```

Cursor phải lấy hoặc tính giá trị normalized tương thích với database. Java lowercase theo default locale có thể không giống database LOWER/collation; khi độ chính xác quan trọng, cân nhắc sortable normalized column do hệ thống kiểm soát.

### 22.3. Chuỗi có thể thay đổi

Nếu người dùng sửa tên Customer trong lúc phân trang theo tên, vị trí Customer trong danh sách có thể dịch chuyển. Keyset không tự ngăn lỗi đó. Cần đánh giá khóa sort có ổn định đủ theo nghiệp vụ không.

---

## 23. Timestamp precision, timezone và serializing cursor

Với `LocalDateTime`, DB thường lưu timestamp không kèm timezone. Hệ thống cần quy định timestamp đó đại diện timezone nào, chẳng hạn UTC convention cho createdAt.

### 23.1. Không dùng giờ client để thay thế thời gian database lưu

Sai về logic cursor:

```java
OrderCursor cursor = new OrderCursor(
    LocalDateTime.now(), lastOrder.getId());
```

Mốc `now()` không nhất thiết bằng `lastOrder.createdAt`. Dùng nó có thể bỏ hàng hoặc trả trùng.

Đúng:

```java
OrderCursor cursor = new OrderCursor(
    lastOrder.getCreatedAt(),
    lastOrder.getId());
```

### 23.2. Giữ đầy đủ precision

Nếu DB lưu microsecond nhưng JSON encoder chỉ giữ giây:

```text
DB:     2026-11-05T09:00:00.123456
Cursor: 2026-11-05T09:00:00
```

thì seek ở lượt tiếp theo không còn đúng mốc đã dùng cho ORDER BY. Hãy dùng format hỗ trợ precision cần thiết hoặc một token opaque bảo toàn giá trị typed.

### 23.3. Timezone chuyển đổi

Nếu API dùng `OffsetDateTime` hoặc `Instant` thay vì `LocalDateTime`, phải thống nhất database/JDBC/JSON conversion. Không trộn local time của người dùng với UTC key mà không chuyển đổi rõ.

### 23.4. Không dùng thời gian như unique key

Ngay cả microsecond timestamp có thể trùng do batch insert, clock resolution hoặc sự kiện đồng thời. ID tie-breaker vẫn cần.

---

## 24. Cursor ở tầng HTTP: không nên chỉ là String tùy tiện

Một API có thể nhận:

```http
GET /api/orders?status=PAID&limit=20&cursor=eyJ2IjoxLC4uLn0
```

Token có thể encode:

```json
{
  "version": 1,
  "direction": "next",
  "sort": "createdAt:desc,id:desc",
  "lastCreatedAt": "2026-11-07T15:00:00.000000",
  "lastId": 107,
  "tenantId": 1,
  "filterFingerprint": "some-server-computed-digest"
}
```

Đây chỉ là **nội dung logic minh họa**; không nên trả `tenantId` hay filter metadata nhạy cảm dưới dạng Base64 JSON rõ nếu không phù hợp chính sách bảo mật.

### 24.1. Base64 không phải cơ chế chống sửa

Một cursor mã hóa Base64 dễ bị decode và chỉnh sửa. Nếu backend tin vào tenantId, sort order hoặc filter từ token mà không xác minh, người dùng có thể thử đổi cursor để xem vùng dữ liệu không được phép.

Thường nên:

- Chỉ lấy tenant/authorization từ identity context đáng tin.
- Kiểm tra cursor version, types và bounds.
- Ràng buộc cursor với filter/sort/direction hiện tại.
- Ký HMAC hoặc dùng cơ chế authenticated encryption khi cần chống tamper/che nội dung.
- Dùng secret server-side với cơ chế rotate keys.
- Đặt TTL nếu cursor không nên tồn tại vô hạn.
- Giới hạn kích thước token và trường hợp invalid input.

### 24.2. Filter fingerprint

Nếu page đầu dùng:

```text
tenant=1
status=PAID
skuPrefix=A-
orderBy=createdAt DESC,id DESC
```

lần tiếp không được đổi `status` thành NEW nhưng giữ cursor cũ mà giả định kết quả vẫn là tiếp nối của cùng danh sách.

Một cách xử lý:

1. Chuẩn hóa bộ lọc/sort của request.
2. Tính một fingerprint (hoặc lưu chúng trong signed cursor).
3. So sánh với fingerprint của cursor.
4. Nếu khác, báo cursor không phù hợp và yêu cầu bắt đầu phiên duyệt mới.

### 24.3. Có cần encode toàn bộ filter?

Không nhất thiết. API có thể bắt client gửi filter ở mỗi request và token chỉ mang fingerprint. Nhưng server phải kiểm tra fingerprint được tính từ **bộ lọc đã xác thực**, không từ tham số tenant mà client tự khai báo.

### 24.4. Version hóa cursor

Khi thay đổi thứ tự sort hoặc cấu trúc dữ liệu, cursor cũ có thể không tương thích. Field `version` giúp server từ chối hoặc xử lý backward compatibility rõ ràng, thay vì âm thầm đọc sai.

---

## 25. Không phân trang trên child JOIN rows nếu item là entity gốc

Một API có yêu cầu:

> Tìm Orders có ít nhất một Line SKU bắt đầu bằng `A-`, rồi keyset theo `(createdAt,id)`.

Sai khi vô tình nhân root:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
ORDER BY o.createdAt DESC, o.id DESC
```

Một Order có nhiều Lines cùng match có thể xuất hiện nhiều lần trong result list. Khi lấy `pageSize+1`, số rows không còn tương ứng số Orders, khiến `hasNext` và cursor sai.

### 25.1. Dùng EXISTS thay JOIN để filter root

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND EXISTS (
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

Với first page, bỏ seek clause tương tự phần trước.

`EXISTS` xác định root có child match mà không tạo một hàng root cho từng child trong logical outer query.

### 25.2. Tính đúng khi một Order có nhiều Lines phù hợp

```text
Order#1001:
  A-01
  A-02
  A-03

EXISTS:
  Điều kiện TRUE một lần cho Order#1001.

Không cần xuất 3 root rows.
```

### 25.3. EXISTS không cam kết luôn nhanh hơn JOIN DISTINCT

Database có thể optimize EXISTS thành semi-join hoặc kế hoạch khác. Cần đo EXPLAIN, selectivity, indexes và số rows. Nhưng với yêu cầu “có ít nhất một child”, EXISTS thường là cách diễn đạt rõ **hạt dữ liệu root**.

### 25.4. Khi có nhiều điều kiện child

Nếu một Line phải vừa có SKU A, vừa quantity >= 2:

```jpql
AND EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :prefix
      AND l.quantity >= :minQuantity
)
```

Đừng tách thành hai EXISTS nếu nghiệp vụ bắt buộc **cùng một Line** thỏa cả hai điều kiện; hai EXISTS riêng có thể chọn hai Lines khác nhau.

---

## 26. Kết hợp Criteria API và EXISTS

Một Criteria subquery:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<OrderCard> cq =
    cb.createQuery(OrderCard.class);

Root<PurchaseOrder> order =
    cq.from(PurchaseOrder.class);

Subquery<Long> subquery =
    cq.subquery(Long.class);

Root<OrderLine> line =
    subquery.from(OrderLine.class);

subquery.select(line.get("id"));

subquery.where(
    cb.equal(line.get("order"), order),
    cb.like(line.get("sku"), skuPrefix)
);

Predicate hasMatchingLine = cb.exists(subquery);
```

Cần import:

```java
import jakarta.persistence.criteria.Subquery;
```

Sau đó thêm vào `filters`:

```java
filters.add(hasMatchingLine);
```

và giữ seek predicate tương ứng trên `order.createdAt`/`order.id`.

### 26.1. Vì sao không tạo JOIN to-many rồi distinct sau pagination?

Nếu Criteria query JOIN Lines và trả root bị lặp, việc loại trùng bằng Java `distinct()` sau `setMaxResults(pageSize+1)` có thể khiến `hasNext` sai hoặc trang ngắn không đúng. Hãy thiết kế query tạo **mỗi root đúng một vị trí logic** ngay từ đầu.

### 26.2. Criteria Root của subquery và outer query

`line` là Root của subquery; `order` là Root của outer query. Điều kiện `line.order = order` tạo correlation. Không thay cả hai bằng những Root không liên hệ rồi vô tình kiểm tra sự tồn tại của **bất kỳ Line nào trong database**.

---

## 27. Keyset cho DTO đơn giản: tránh fetch graph không cần thiết

Nếu UI chỉ cần:

```text
orderId
orderNumber
createdAt
customerName
```

DTO projection là cách tự nhiên:

```jpql
SELECT NEW demo.dto.OrderCard(
    o.id,
    o.orderNumber,
    o.createdAt,
    c.displayName
)
FROM PurchaseOrder o
JOIN o.customer c
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND (
      o.createdAt < :lastCreatedAt
      OR (
          o.createdAt = :lastCreatedAt
          AND o.id < :lastId
      )
  )
ORDER BY o.createdAt DESC, o.id DESC
```

### 27.1. Không cần SELECT cả entity cho chỉ vài cột

Nếu trả `PurchaseOrder` managed entity rồi serialize, lazy associations có thể gây N+1 hoặc lỗi sau khi context đóng. DTO giúp kiểm soát dữ liệu tải và giữ được cursor keys.

### 27.2. Nếu cần collection, không ghép JOIN FETCH trực tiếp với page limit

Ví dụ:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.createdAt DESC, o.id DESC
```

rồi `setMaxResults(pageSize+1)` có thể gặp **collection fetch pagination** không portable: một Order có nhiều Lines làm nhiều SQL rows và có nguy cơ in-memory pagination/cảnh báo/chi phí lớn.

### 27.3. Keyset không tự chữa vấn đề collection fetch

Dù có điều kiện seek đúng, nếu page limit áp lên JOIN rows rồi mới dựng root, vẫn có thể cắt collection hoặc khiến số root trên trang sai. Hãy tách bước root page khỏi bước fetch collection.

---

## 28. Hai bước: keyset IDs rồi fetch graph

Khi API cần mỗi Order kèm đầy đủ OrderLines:

**Bước 1: lấy IDs** của root đúng thứ tự keyset.

```jpql
SELECT o.id, o.createdAt
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND (
      o.createdAt < :lastCreatedAt
      OR (
          o.createdAt = :lastCreatedAt
          AND o.id < :lastId
      )
  )
ORDER BY o.createdAt DESC, o.id DESC
```

Giới hạn ở `pageSize + 1`. Kết quả là pairs `(id, createdAt)` đủ để dựng cursor.

**Bước 2: chỉ fetch những Orders thuộc content**, bỏ row extra dùng để peek:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.customer
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

**Bước 3: sắp lại root theo thứ tự IDs** của bước 1:

```java
Map<Long, PurchaseOrder> byId = new HashMap<>();

for (PurchaseOrder order : fetched) {
    byId.put(order.getId(), order);
}

List<PurchaseOrder> ordered = new ArrayList<>();

for (Long id : pageIds) {
    PurchaseOrder order = byId.get(id);
    if (order != null) {
        ordered.add(order);
    }
}
```

### 28.1. Vì sao cần khôi phục thứ tự?

SQL `WHERE id IN (...)` không cam kết trả rows theo thứ tự IDs trong Java List. Với keyset, thứ tự phản hồi là hợp đồng quan trọng để cursor tiếp tục đúng. Phải dùng `ORDER BY` phù hợp hoặc reorder theo danh sách page IDs.

### 28.2. Không fetch row extra

Nếu query pageSize+1 lấy 21 IDs nhưng chỉ trả 20 Orders, bước 2 chỉ nên fetch 20 IDs của content; Order thứ 21 chỉ dùng để xác định hasNext. Fetch nó không tăng tính đúng mà có thể tốn thêm child data.

### 28.3. Cần xử lý danh sách IDs rỗng

Không nên gửi JPQL `WHERE id IN :ids` với `ids=[]` nếu provider/database không hỗ trợ cú pháp rỗng. Nếu bước 1 không có IDs, trả content rỗng, hasNext=false.

### 28.4. Hai query có thể thấy thay đổi giữa chừng

Một Order có thể bị xóa/đổi status sau bước 1 và trước bước 2. Query thứ hai có thể thiếu Order theo danh sách ID. Cần transaction isolation hoặc policy nhất quán phù hợp với use case; keyset two-step không tự tạo snapshot.

---

## 29. Tách truy vấn child DTO thay vì JOIN FETCH

Một giải pháp khác là giữ content là DTO root và query children riêng:

**Root page query:**

```jpql
SELECT NEW demo.dto.OrderCard(
    o.id,
    o.orderNumber,
    o.createdAt,
    c.displayName
)
FROM PurchaseOrder o
JOIN o.customer c
WHERE ...
ORDER BY o.createdAt DESC, o.id DESC
```

**Child query:**

```jpql
SELECT NEW demo.dto.OrderLineCard(
    l.order.id,
    l.id,
    l.sku,
    l.quantity
)
FROM OrderLine l
WHERE l.order.id IN :ids
ORDER BY l.order.id, l.id
```

Ví dụ DTO:

```java
package demo.dto;

public record OrderLineCard(
    Long orderId,
    Long lineId,
    String sku,
    int quantity
) {}
```

Sau đó Java group `OrderLineCard` theo `orderId` và gắn vào DTO nested của mỗi Order.

### 29.1. Lợi ích

- Không materialize toàn bộ entity graph.
- Không phát sinh collection fetch pagination.
- Chỉ lấy cột DTO cần thiết.
- Có thể thêm các aggregate (line count, total) theo nhu cầu.
- Một truy vấn child có thể fetch tất cả Lines cho một page root, tránh N+1.

### 29.2. Chi phí

- Có thêm SQL statement.
- Phải group/reorder ở application.
- Phải có policy consistency giữa các statements.
- Không phù hợp nếu caller cần managed entity graph để cập nhật trong cùng unit of work.

**Không tối ưu bằng số query thấp nhất một cách máy móc**: hai query vừa và đúng dữ liệu có thể tốt hơn một JOIN fetch cực lớn.

---

## 30. Index phù hợp với filter và ORDER BY

Giả sử keyset query luôn:

```jpql
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND (o.createdAt < :time OR
       (o.createdAt = :time AND o.id < :id))
ORDER BY o.createdAt DESC, o.id DESC
```

Một index có thể cân nhắc:

```sql
CREATE INDEX idx_order_tenant_status_time_id
ON purchase_orders (
    tenant_id,
    order_status,
    created_at DESC,
    id DESC
);
```

Ý tưởng:

- `tenant_id` và `order_status` là equality filters.
- `created_at` và `id` theo sort/seek key.
- Database có thể sử dụng index để tìm vùng sau cursor rồi đọc số rows cần thiết.

### 30.1. Index có bảo đảm luôn được dùng không?

Không. Optimizer có thể chọn plan khác dựa trên:

- Phân phối tenant/status.
- Cardinality và selectivity.
- Số rows còn lại sau cursor.
- Table statistics.
- Row width và index coverage.
- JOIN và additional WHERE predicates.
- DBMS version và hint/configuration.

Dùng `EXPLAIN`/execution plan thực tế trên database triển khai.

### 30.2. Composite index có thứ tự cột quan trọng

Nếu query lọc tenant/status bằng equality, đặt chúng trước sort keys thường là một hướng khởi đầu hợp lý. Nhưng nếu status có nhiều giá trị hoặc query filters động, index tối ưu có thể khác.

### 30.3. DESC trong index có portable không?

Cú pháp, khả năng scan ngược và cách tối ưu composite direction khác nhau giữa DBMS. SQL DDL ở đây chỉ là minh họa; cần kiểm tra engine cụ thể.

### 30.4. Offset và keyset cùng có thể dùng index

Không nên nói offset “không thể dùng index”. Nó có thể dùng index để duyệt thứ tự, nhưng vẫn phải bỏ qua số vị trí tăng theo offset. Keyset cố giảm việc bỏ qua đó bằng predicate điều hướng.

---

## 31. Hiệu năng và kế hoạch thực thi

Một so sánh nên đo:

| Đại lượng | Ý nghĩa |
|---|---|
| SQL duration | Thời gian DB xử lý query |
| Rows examined | Số rows/index entries DB cần xem |
| Rows returned | Số rows thực sự truyền về |
| Sort/temporary operations | Có phải sort/hash ngoài index? |
| Round trips | Có bao nhiêu SQL statements do JPA tạo? |
| Memory/GC | Có materialize entity graph lớn không? |
| Latency endpoint | Tổng thời gian từ request tới DTO |
| Correctness | Có duplicate/missing IDs khi tập dữ liệu tĩnh? |
| Concurrent behavior | Khi insert/update/delete, behavior có đáp ứng hợp đồng? |

### 31.1. Một JOIN lớn có thể làm keyset kém hiệu quả

Nếu query root chỉ trả 20 Orders nhưng JOIN fetch 20.000 Lines, số rows SQL vẫn rất lớn. Keyset chỉ xử lý **chọn root theo thứ tự**, không tự hạn chế số child của root.

### 31.2. OR predicate có thể vẫn đắt

`createdAt < :time OR (createdAt = :time AND id < :id)` là biểu thức portable rõ, nhưng optimizer phải xử lý OR. Một số database có thể tận dụng composite index tốt, số khác cần rewrite hoặc native tuple comparison để cải thiện. Đo plan trước khi chọn implementation riêng.

### 31.3. Môi trường benchmark phải kiểm soát cache

Nếu persistence context đã chứa tất cả Customers hoặc second-level cache đã nóng, số SQL/time khác với request lạnh. Benchmark nên có cả trường hợp cold/warm phù hợp, dữ liệu đủ lớn và cấu hình provider thực.

---

## 32. Dữ liệu thay đổi đồng thời: keyset giúp gì và không giúp gì?

Giả sử danh sách ban đầu:

```text
[110, 109, 108, 107, 106, 105, 104]
```

Page 1:

```text
[110, 109, 108]
cursor = 108
```

Trước khi tải page 2, Order#111 mới được insert ở đầu:

```text
[111, 110, 109, 108, 107, 106, 105, 104]
```

**Offset page 2** (OFFSET 3) có thể trả lại #108. **Keyset** với `id < 108` (nếu sort ID DESC) vẫn bắt đầu #107, nên không lặp #108 chỉ do insert đứng trước cursor.

### 32.1. Bảo vệ khỏi drift do insert trước cursor

Đây là lợi ích lớn của keyset trong feeds: vị trí trang được xác định bằng khóa đã thấy thay vì “bỏ qua N rows hiện tại”.

### 32.2. Nhưng nếu bản ghi chuyển khóa sort?

Nếu Order#105 đổi `createdAt` lên thời điểm mới hơn cursor, nó có thể chuyển từ vùng “chưa xem” sang vùng “đã qua”. Lần seek tiếp có thể không bao giờ thấy nó.

Nếu Order#109 đã xem rồi đổi `createdAt` xuống cũ hơn cursor, có thể thấy nó một lần nữa ở page sau.

**Keyset không bảo đảm mỗi entity xuất hiện đúng một lần khi sort keys thay đổi.**

### 32.3. Soft delete, status changes, tenant membership

Nếu Order đổi `status=PAID` thành CANCELLED giữa các requests, nó có thể biến mất khỏi tập filter; nếu đổi ngược lại, có thể xuất hiện muộn. Nếu có quyền truy cập thay đổi, server phải luôn xác minh lại authorization ở mỗi request.

### 32.4. Snapshot nếu yêu cầu duyệt bất biến

Với xuất báo cáo, batch processing hoặc đối soát cần nhất quán:

- Một snapshot transaction thích hợp trong một job không quá dài.
- Một phiên bản dataset hoặc snapshot ID.
- Một bảng danh sách IDs cần xử lý.
- Một filter theo `createdAt <= :snapshotBoundary` nếu business logic và thứ tự đảm bảo điều kiện này đủ; nhưng không tự ngăn updates/deletes.
- Policy idempotency/dedup khi xử lý.

Không thể chỉ thêm một timestamp vào cursor rồi khẳng định đã có snapshot bất biến.

---

## 33. “High-water mark” và điều kiện thời điểm

Một API feed có thể chọn một **giới hạn trên** tại lượt đầu:

```jpql
WHERE o.createdAt <= :upperBoundary
```

Sau đó giữ điều kiện này ở các lần seek để không thêm Orders mới hơn giới hạn.

Tuy nhiên:

- Nếu Order mới được insert muộn nhưng gán `createdAt` trước upperBoundary, nó vẫn có thể xuất hiện.
- Existing Orders có thể bị xóa hoặc đổi status.
- `createdAt` không đồng nghĩa commit timestamp.
- Nếu timestamp có thể update, điều kiện không cố định tập bản ghi.
- Replica lag có thể ảnh hưởng visibility.

High-water mark chỉ là một **giới hạn theo khóa**; có thể hữu ích nhưng không tương đương database snapshot hay transaction isolation.

### 33.1. Khi nào hữu ích?

Nếu dữ liệu append-only, createdAt bất biến và commit/arrival semantics được quản lý, upperBoundary giúp giữ một mốc để lướt feed hữu hạn. Cần ghi rõ các giả định đó trong API contract.

---

## 34. Khi nào cần totalElements cùng cursor?

Một số giao diện vẫn muốn hiện:

```text
Đang hiển thị 20/10.000 giao dịch
```

Khi đó, có thể chạy count riêng:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
  AND o.status = :status
```

### 34.1. Count toàn tập hay count phần còn lại?

Phải chọn semantics:

- **Tổng của toàn tập theo filter**: count không chứa seek predicate.
- **Số bản ghi còn sau cursor**: count thêm seek predicate.
- **Tổng tại snapshot đầu**: cần snapshot policy đủ mạnh hoặc count cache gắn đúng snapshot.

Không tự gọi số còn lại là `totalElements` mà không ghi rõ.

### 34.2. Count không bắt buộc cho hasNext

`pageSize+1` có thể xác định còn rows ngay sau current page mà không cần COUNT toàn bảng.

### 34.3. Count có thể rất tốn kém

Nếu page đầu lấy 20 rows nhanh nhờ index nhưng count phải xét hàng triệu rows, API bị chậm vì metadata hiển thị không cần thiết. Với infinite scroll, cursor/slice thường phù hợp hơn count chính xác.

---

## 35. REST response và ví dụ cursor

Một response:

```json
{
  "items": [
    {
      "id": 110,
      "orderNumber": "ORD-110",
      "createdAt": "2026-11-08T10:00:00"
    },
    {
      "id": 109,
      "orderNumber": "ORD-109",
      "createdAt": "2026-11-08T10:00:00"
    },
    {
      "id": 107,
      "orderNumber": "ORD-107",
      "createdAt": "2026-11-07T15:00:00"
    }
  ],
  "hasNext": true,
  "nextCursor": "opaque-signed-token"
}
```

Backend parse token thành `OrderCursor(createdAt,id)`, xác minh version/filter/tenant/sort, rồi gọi JPA query tương ứng.

### 35.1. Không bắt client tự tạo cursor từ item bất kỳ

Nếu API hỗ trợ cursor opaque, client chỉ nên dùng token server trả. Nếu client được phép truyền một cursor thô, server vẫn cần validate và áp dụng permission filter, vì cursor không phải authorization token.

### 35.2. Invalid cursor là lỗi input, không phải lỗi JPA ngẫu nhiên

Ví dụ:

- Thiếu ID.
- Timestamp sai format.
- Phiên bản cursor không được hỗ trợ.
- Cursor đã hết hạn.
- Sort khác request.
- Fingerprint filter khác.
- Token bị sửa hoặc signature sai.

Nên trả lỗi HTTP phù hợp (ví dụ 400 Bad Request cho cursor không hợp lệ) theo API contract, không để lỗi `IllegalArgumentException` của provider lộ chi tiết hệ thống.

### 35.3. HTTP stateless

Cursor giúp client tiếp tục mà không cần server nhớ pageIndex theo session. Tuy nhiên, server vẫn có thể chọn server-side cursor/session nếu cần snapshot hoặc dataset lớn không thể encode an toàn trong một token. Đó là một quyết định kiến trúc khác.

---

## 36. Spring Data JPA và keyset

Trong Spring Data JPA, `Pageable` truyền thống thường gắn với offset/page index. Bạn có thể viết custom repository/service sử dụng `EntityManager` với `setMaxResults` và seek predicates như các ví dụ trên.

Một số phiên bản Spring Data có API Scroll/Window và keyset scrolling để hỗ trợ cơ chế này ở mức framework. **Khả năng và tên API phụ thuộc phiên bản Spring Data**, nên không nên viết code giả định mọi project Spring Data JPA đều có cùng interface.

### 36.1. Custom repository minh bạch

Một custom repository method:

```java
public interface OrderSeekRepository {
    KeysetSlice<OrderCard> nextPage(
        Long tenantId,
        OrderStatus status,
        OrderCursor after,
        int pageSize
    );
}
```

Implementation có `@PersistenceContext EntityManager` và gọi method JPQL/Criteria đã mô tả.

### 36.2. Service giữ transaction read-only

```java
@Service
public class OrderFeedService {

    private final OrderSeekRepository repository;

    public OrderFeedService(OrderSeekRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public KeysetSlice<OrderCard> getNext(
            Long tenantId,
            OrderStatus status,
            OrderCursor cursor,
            int size) {

        return repository.nextPage(
            tenantId, status, cursor, size);
    }
}
```

Cần import `@Service` của Spring và `@Transactional` tương ứng. Đừng coi `readOnly=true` là bảo đảm mọi lần request cùng snapshot; đó là hint/transaction intent, isolation phải được cấu hình và hiểu riêng.

### 36.3. Khi nào dùng framework scrolling API?

Nếu phiên bản/framework đã hỗ trợ keyset scrolling với contract phù hợp, có thể dùng để giảm boilerplate. Nhưng cần xác minh:

- Sort keys cần được projection trả đầy đủ.
- Unique tie-breaker được bổ sung.
- Cách xử lý NULL.
- Có hỗ trợ joins/projections/associations đang dùng không.
- Cursor binding theo filters/security.
- Chiều before/after có đúng nhu cầu không.
- Chính sách giới hạn size và SQL logs.

Hiểu nguyên lý JPQL/Criteria giúp chẩn đoán hành vi framework và tránh dùng API “đúng tên” nhưng query vẫn không đúng hạt dữ liệu.

---

## 37. Keyset và cache

JPA first-level cache có thể giữ entity đã tải trong cùng persistence context. Second-level cache và query cache có thể ảnh hưởng SQL quan sát được.

Nếu dùng DTO projection:

- Provider thường không cần materialize toàn bộ entity graphs.
- Những columns được query có thể được lấy trực tiếp từ database.
- Kết quả cursor vẫn chịu ảnh hưởng của transaction visibility và database state.

Nếu dùng entity query:

- Một entity đã managed có thể giữ state cũ trong context dài.
- Query ordering/qualification có thể dựa vào database nhưng object state đã giữ trong context có thể không được refresh như người dùng tưởng.
- Cần transaction/context lifecycle phù hợp, không để một persistence context sống lâu vô lý cho nhiều request.

### 37.1. Không xây cursor từ object stale sai thứ tự

Nếu timestamp hoặc sort key bị thay đổi trong database nhưng managed entity đang giữ giá trị cũ, cursor dựng từ state cũ có thể không phản ánh đúng vị trí mà SQL vừa dùng để sort. DTO projection trực tiếp các key columns hoặc context mới thường dễ kiểm soát hơn trong API đọc.

### 37.2. Query cache không thay thế consistency policy

Cache có thể giúp hoặc làm phức tạp tính mới của dữ liệu. Keyset chỉ là phương pháp điều hướng theo sort key, không tự invalidates caches.

---

## 38. Chỉ số duy nhất, tính bất biến và dữ liệu đặc biệt

### 38.1. ID phải unique và so sánh được

Với `Long id`, việc so sánh lớn/nhỏ tương đối đơn giản. Với UUID:

- UUID ngẫu nhiên có thể được database lưu/so sánh theo thứ tự binary hoặc text khác nhau.
- JPQL portable không bảo đảm mọi provider hỗ trợ `>`/`<` trên UUID như số.
- Khi cần seek, hãy chọn một sortable unique key hoặc chiến lược vendor-specific được kiểm thử.

Một opaque identifier không có thứ tự ổn định/portable **không tự trở thành keyset tie-breaker hợp lệ**.

### 38.2. Primary key chỉ bất biến theo kỳ vọng

JPA primary key của entity thường không nên thay đổi sau persist. Database/application phải tuân thủ quy tắc đó. Nếu đổi khóa định danh, cursor đã phát có thể mất ý nghĩa.

### 38.3. Soft-delete

Nếu `deleted=false` là điều kiện filter, cần áp dụng ở mọi trang. Nếu một Order bị soft-delete sau khi đã xem, nó biến mất; đó là thay đổi tập dữ liệu hợp lệ theo business semantics.

### 38.4. Thiếu unique tie-breaker

Nếu có hai Orders cùng createdAt và cùng priority, nhưng không có ID trong sort, **thứ tự không được xác định hoàn toàn**. Không thể xây một cursor duy nhất từ những giá trị bằng nhau mà không có nguy cơ skip/duplicate.

---

## 39. Keyset khi sort theo giá trị của collection

Giả sử muốn danh sách Orders sort theo SKU nhỏ nhất trong các Lines.

Sai về ngữ nghĩa:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
ORDER BY l.sku ASC, o.id ASC
```

Một Order có nhiều SKU; không có một `l.sku` duy nhất đại diện cho Order trong ORDER BY. SQL DISTINCT và việc phân trang sẽ khó đảm bảo root order đúng.

### 39.1. Định nghĩa một aggregate sort key

Ví dụ:

```jpql
SELECT o.id, MIN(l.sku)
FROM PurchaseOrder o
LEFT JOIN o.lines l
GROUP BY o.id
ORDER BY MIN(l.sku) ASC, o.id ASC
```

Mỗi root có một group/giá trị `MIN(l.sku)`. Cursor sẽ cần giá trị MIN và ID, đồng thời xử lý NULL khi Order không có Line.

### 39.2. Aggregate key có thể thay đổi

Nếu một Line mới với SKU nhỏ hơn được thêm vào Order, `MIN(l.sku)` thay đổi, Order di chuyển vị trí giữa requests. Keyset không ngăn được việc di chuyển đó.

### 39.3. Khi nào nên tách thành report table?

Với query nhóm rất lớn, keyset theo aggregate có thể cần native SQL, reporting view hoặc materialized summary keyed by Order. Cân nhắc cập nhật/consistency của summary trước khi chọn.

---

## 40. Keyset với JOIN DISTINCT và GROUP BY

Keyset phải áp dụng trên **một row cho mỗi phần tử logic**.

Nếu content query có `GROUP BY` theo Customer và muốn seek theo `totalSpent DESC, customerId DESC`, cursor phải chứa:

```text
(totalSpent, customerId)
```

Và condition phải được áp dụng ở vị trí phù hợp với aggregate (thường là `HAVING`) hoặc outer query trên grouped result trong native SQL.

Ví dụ khái niệm:

```text
SELECT Customer + SUM(Order.amount)
GROUP BY Customer
HAVING SUM(Order.amount) < :lastTotal
   OR (SUM(Order.amount) = :lastTotal
       AND Customer.id < :lastId)
ORDER BY SUM(Order.amount) DESC, Customer.id DESC
```

Tính hỗ trợ của expressions trong HAVING, type của SUM và query plan phụ thuộc provider/database. Nếu dùng JPQL portable với report phức tạp, cần thử thực tế. Không giả định chỉ viết `WHERE SUM(...) < ...`, vì aggregate thông thường không được đặt như vậy trong WHERE.

### 40.1. Đếm groups nếu cần tổng

Nếu API cần tổng số phần tử của grouped report, `COUNT(o)` trên Order source không phải số groups. Đây là bài toán count riêng, có thể cần query tương đương hoặc native SQL derived-table count.

### 40.2. Keyset không bắt buộc phải dùng entity roots

Keyset cũng có thể phân trang DTO groups, miễn:

- Mỗi row/group có bộ sort keys xác định.
- Có unique tie-breaker giữa groups.
- Cursor chứa đủ key values.
- Predicate dùng đúng ngữ nghĩa group result.
- SQL/JPQL provider hỗ trợ biểu thức cần thiết.

---

## 41. Khi nào keyset không phù hợp?

Không có một chiến lược phân trang tốt nhất cho mọi giao diện.

### 41.1. Cần nhảy trực tiếp tới trang số N

Một back-office UI cần:

```text
Trang 1, 2, 3, ... 500
Nhảy đến trang 320
```

Offset pagination thường tự nhiên hơn vì client biết pageIndex. Keyset cần cursor của một phần tử nằm gần ranh giới đó, nên không hỗ trợ nhảy tùy ý nếu không có thêm index/cursor map.

### 41.2. Sort theo dữ liệu không ổn định

Nếu order theo “điểm nóng” được cập nhật mỗi giây, phần tử có thể di chuyển qua cursor nhiều lần. Keyset không tự đảm bảo không lặp/mất trong một feed dùng mutable ranking.

### 41.3. Sort theo biểu thức khó so sánh portable

Một sort trên JSON field, full-text relevance, vendor-specific function hoặc UUID có thể không dễ biểu diễn bằng `<`/`>` trong JPQL. Native SQL có thể phù hợp hơn, nhưng cần xác nhận semantics và index.

### 41.4. Yêu cầu total exact và phân trang trang số

Khi UX chủ yếu là Page 1/100 với totalElements chính xác, keyset vẫn có thể dùng nhưng không tự thay thế nhu cầu COUNT và direct page navigation. Đánh giá giá trị thực tế trước khi tăng complexity.

### 41.5. Dataset nhỏ

Nếu vài trăm rows và trang sâu hiếm, offset có thể đơn giản, đủ nhanh và dễ bảo trì. Không nên xây hệ thống cursor ký HMAC phức tạp khi lợi ích không đáng kể.

---

## 42. Phân biệt lỗi thuật toán với lỗi triển khai

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lặp phần tử cuối ở trang sau | Dùng `<=`/`>=` | Dùng so sánh strict |
| Bỏ mất phần tử cùng timestamp | Cursor chỉ chứa timestamp | Thêm unique tie-breaker |
| Trả Order sai status/tenant | Thiếu parentheses quanh `OR` | AND toàn bộ seek predicate với filters |
| Trang sau bắt đầu sai | Dấu so sánh ngược chiều sort | ASC dùng `>`, DESC dùng `<` |
| Trang sau bỏ một item | Cursor lấy từ row extra peek | Cursor lấy từ last content item |
| hasNext sai | Query JOIN to-many nhân root rows | EXISTS hoặc page root keys trước |
| SQL ORDER BY chỉ có createdAt | Ties không xác định | Thêm ID |
| Sort hỗn hợp trả sai | Dùng cùng dấu cho mọi sort keys | Dựng lexicographic predicate theo từng direction |
| NULL rows biến mất | `<`/`>` với NULL trả UNKNOWN | Explicit null groups/branches |
| Query lặp/mất sau đổi tên | Sort key mutable/collation khác | Stable sort key hoặc snapshot policy |
| Cursor sau serialization sai | Mất timestamp precision | Encode đầy đủ values |
| Cursor dùng lại với filter mới | Không bind filter/sort | Fingerprint và validate |
| Cursor bị sửa | Chỉ Base64 không ký | HMAC/authenticated encoding |
| Khách xem được tenant khác | Tin vào tenantId trong cursor/request | Server-side authorization filter |
| Query chậm ở trang sâu | Thiếu composite index hoặc plan xấu | EXPLAIN và index theo sort/filter |
| N+1 dù keyset đúng | Lazy association khi map DTO | DTO projection/fetch plan |
| Collection bị thiếu | Limit trên collection fetch join | Page IDs rồi fetch collection |
| Page trước trả items quá xa | Reverse predicate nhưng không đảo ORDER BY | Reverse sort khi query backward |
| IN query đảo thứ tự items | `IN` không giữ order | Reorder theo page IDs |
| Thay đổi dataset gây trùng | Mutable keys/concurrency | Snapshot/idempotent processing |
| Test pass nhưng production sai | Tập test không có ties | Thêm nhiều rows cùng timestamp |
| Cursor lỗi với UUID | Không có sortable comparison portable | Chọn key phù hợp hoặc native strategy |

---

## 43. Bài thực hành A — Keyset đơn khóa

1. Tạo 30 Orders với IDs từ 1 đến 30.
2. Query `ORDER BY id DESC`, `setMaxResults(5)`.
3. Ghi năm IDs đầu.
4. Lấy last ID làm cursor.
5. Query `WHERE id < :lastId`.
6. Tiếp tục cho tới khi hết kết quả.
7. Gộp tất cả pages và xác nhận không có duplicate/missing IDs với dataset tĩnh.
8. Thử dùng `<=` và quan sát phần tử cuối bị lặp.
9. Đổi sort sang `id ASC` và dùng `>`.

## 44. Bài thực hành B — Timestamp trùng nhau

1. Tạo 10 Orders; ít nhất 5 Orders cùng `createdAt`.
2. Query sort chỉ `createdAt DESC`.
3. Chia page size 2.
4. Dùng cursor timestamp-only và quan sát nguy cơ bỏ những rows cùng timestamp.
5. Đổi sort thành `createdAt DESC,id DESC`.
6. Đổi cursor thành `(lastCreatedAt,lastId)`.
7. Dùng seek predicate hai nhánh.
8. Xác minh duyệt hết 10 Orders không trùng/mất với dữ liệu tĩnh.
9. Giải thích vì sao unique tie-breaker cần thiết.

## 45. Bài thực hành C — JPQL và pageSize+1

1. Định nghĩa DTO `OrderCard`.
2. Viết query first page và after-cursor query.
3. Chọn pageSize=3 nhưng `setMaxResults(4)`.
4. Tính `hasNext`.
5. Bỏ bản ghi extra khỏi response.
6. Sinh nextCursor từ last returned item.
7. Tiếp tục đến trang cuối.
8. Đảm bảo trang cuối có hasNext=false và cursor null theo contract của ví dụ.
9. Thử lỗi dùng extra row làm cursor và ghi phần tử bị bỏ qua.

## 46. Bài thực hành D — Criteria API tương đương

1. Dùng `CriteriaBuilder` và `CriteriaQuery<OrderCard>`.
2. Tạo Root PurchaseOrder và Join Customer.
3. Tạo `createdAt`/`id` typed Paths.
4. Nếu có cursor, dựng `cb.or(cb.lessThan(...), cb.and(cb.equal(...),cb.lessThan(...)))`.
5. Thêm tenant/status filters.
6. `cq.orderBy(cb.desc(createdAt),cb.desc(id))`.
7. `setMaxResults(pageSize+1)`.
8. Đối chiếu IDs/trang với JPQL cho cùng dataset.
9. Thử một optional filter và bảo đảm query không cursor không chứa predicate giả.
10. So sánh SQL sinh ra trên provider thật.

## 47. Bài thực hành E — Chiều sort hỗn hợp

1. Thêm `priority: Integer` không null và immutable trong một model thử.
2. Sort `priority ASC,createdAt DESC,id ASC`.
3. Ghi dữ liệu có trùng priority và timestamp.
4. Tạo cursor ba trường.
5. Viết ba nhánh OR tương ứng.
6. Dùng Criteria API xây ba `Predicate`.
7. Duyệt hết tập kết quả.
8. Đảo một dấu so sánh có chủ đích để thấy lỗi.
9. Giải thích thuật toán lexicographic.

## 48. Bài thực hành F — Truy vấn trang trước

1. Dùng dữ liệu IDs 110..101.
2. Lấy ba trang theo DESC.
3. Từ trang thứ hai, lấy phần tử đầu làm beforeCursor.
4. Dùng điều kiện `createdAt > ... OR (... AND id > ...)`.
5. ORDER BY đảo thành `ASC,ASC`.
6. Giới hạn `pageSize+1`.
7. Lật danh sách content lại thành DESC.
8. Xác minh chính là trang liền trước.
9. Kiểm tra trường hợp trang đầu và số phần tử nhỏ hơn pageSize.

## 49. Bài thực hành G — NULLS LAST

1. Tạo entity thử có `shippedAt` nullable.
2. Sort bằng CASE để nhóm non-null trước NULL.
3. Với cursor non-null, dùng nhánh “ngày cũ hơn hoặc cùng ngày ID nhỏ hơn” cộng nhóm NULL.
4. Với cursor NULL, dùng `IS NULL AND id < :lastId`.
5. Kiểm tra không có row NULL bị mất khi chuyển nhóm.
6. So sánh SQL trên hai DBMS có quy tắc NULL placement khác nhau.
7. Đo hiệu năng khi ORDER BY có CASE.
8. Giải thích vì sao sort key NOT NULL dễ triển khai hơn.

## 50. Bài thực hành H — Cursor validation

1. Xây một cursor payload gồm version, sort, keys, filter fingerprint.
2. Encode theo format đã chọn.
3. Tạo chữ ký HMAC bằng key server-side hoặc cơ chế integrity được thư viện hỗ trợ.
4. Thử chỉnh sửa lastId trong token và xác nhận request bị từ chối.
5. Thử đổi filter status nhưng giữ token cũ.
6. Thử dùng cursor tenant 1 khi đang đăng nhập tenant 2.
7. Thử timestamp không parse được hoặc precision bị cắt.
8. Đặt max token size và expiry policy.
9. Không sử dụng Base64 đơn thuần như xác thực.

## 51. Bài thực hành I — JOIN to-many và EXISTS

1. Tạo Order có 10 Lines SKU A và nhiều Orders khác.
2. Query JOIN Lines rồi dùng pageSize+1.
3. Ghi duplicate roots hoặc số item trang không đúng.
4. Đổi sang EXISTS.
5. Xác minh mỗi Order chỉ có một vị trí trong kết quả.
6. Kết hợp tenant/status/seek filters và parentheses đúng.
7. So sánh execution plans.
8. Không mặc định EXISTS luôn nhanh hơn; đánh giá index và selectivity.

## 52. Bài thực hành J — Hai bước fetch graph

1. Page Order IDs dùng seek predicate.
2. Dùng pageSize+1 để xác định hasNext.
3. Chỉ chọn IDs của content, bỏ peek row.
4. Fetch Orders+Customer+Lines qua `WHERE id IN :ids`.
5. Không phân trang trên fetch query.
6. Reorder theo danh sách IDs.
7. Đảm bảo collection Lines đầy đủ.
8. Thử Order bị xóa giữa hai queries.
9. Đánh giá transaction/isolation policy phù hợp.
10. So sánh DTO projection với fetch graph.

## 53. Bài thực hành K — Index và hiệu năng

1. Tạo nhiều Orders với tenant/status/time phân phối thực tế.
2. Đặt index composite trên tenant/status/createdAt/id.
3. Chạy offset page 0, page sâu 10.000 và 100.000.
4. Chạy keyset cùng phạm vi bằng cursor thích hợp.
5. Ghi execution plans và rows examined.
6. So sánh SQL latency và endpoint latency.
7. Lặp lại khi thêm EXISTS child filter.
8. Thử index khác và đánh giá optimizer.
9. Không suy kết luận từ một lần chạy hoặc một dataset nhỏ.

## 54. Bài thực hành L — Dữ liệu thay đổi

1. Lấy trang đầu của danh sách theo createdAt DESC,id DESC.
2. Insert một Order mới đứng trước cursor.
3. Lấy trang tiếp theo bằng offset, ghi rủi ro trùng.
4. Lấy tiếp bằng keyset, đối chiếu.
5. Update createdAt của một Order chưa xem sang vị trí trước cursor.
6. Quan sát nguy cơ bỏ phần tử đó.
7. Update một Order đã xem sang vị trí sau cursor.
8. Quan sát nguy cơ thấy lại phần tử.
9. Đề xuất snapshot/idempotency policy cho batch processing.
10. Phân biệt “cursor ổn định với insert trước boundary” và “snapshot consistency”.

---

## 55. Checklist thiết kế trước khi đưa vào production

| Câu hỏi | Điều cần chốt |
|---|---|
| Item trong danh sách là root hay tuple/group? | Một item phải có bộ sort keys xác định |
| ORDER BY đã đầy đủ chưa? | Tổng thứ tự, unique tie-breaker |
| Tất cả sort keys có thể so sánh bằng JPQL không? | Type/nullable/collation/UUID |
| Có key NULL không? | Explicit NULL placement và branches |
| Dấu seek đúng theo từng chiều ASC/DESC chưa? | ASC `>`, DESC `<` khi đi tiếp |
| Cursor đủ tất cả sort keys chưa? | Không chỉ timestamp nếu có tie |
| Cursor được lấy từ last content item chưa? | Không lấy extra peek |
| pageSize có giới hạn không? | Tránh size 0/âm/quá lớn |
| Có lấy size+1 để xác định hasNext không? | Tránh count toàn bảng không cần |
| Có optional filters không? | Query variants/Criteria phù hợp |
| Tenant/permission filter từ nguồn tin cậy chưa? | Không tin token/client |
| Cursor có version/filter/sort binding chưa? | Ngăn reuse sai danh sách |
| Token có integrity hoặc encryption khi cần không? | Base64 không đủ |
| Timestamp precision có được giữ không? | Tránh skip/duplicate |
| Sort key có bất biến không? | Phân tích update/reordering |
| JOIN to-many có nhân root không? | EXISTS hoặc page roots trước |
| Có fetch collection cùng limit không? | Không làm trực tiếp |
| IDs fetch theo IN có cần reorder không? | Luôn xác định thứ tự rõ |
| Có snapshot yêu cầu không? | Isolation/high-water/snapshot job |
| Có truy vấn trang trước không? | Reverse comparison và reverse order |
| Có muốn nhảy trang N không? | Offset có thể phù hợp hơn |
| Có đúng composite index không? | EXPLAIN, đo plan |
| Có đo SQL rows và latency không? | Tránh tối ưu theo annotation |
| Có test ties, null và concurrent changes không? | Đầy đủ trường hợp biên |
| Có hỗ trợ cursor hết hạn và phiên bản cũ không? | API evolution rõ ràng |

---

## 56. Các hiểu lầm thường gặp

### 56.1. “Keyset chỉ cần WHERE id < lastId”

Đúng chỉ khi sort chính là ID DESC (hoặc ID kết hợp có semantics tương ứng). Nếu sort chính là createdAt DESC, phải dùng `(createdAt,id)` với predicate hai nhánh.

### 56.2. “Timestamp đủ unique nên không cần ID”

Thời gian có thể trùng. Không có tie-breaker, cursor timestamp-only có thể bỏ hoặc lặp các rows cùng timestamp.

### 56.3. “ASC hay DESC đều dùng dấu nhỏ hơn”

Sai. Để đi sau cursor: ASC dùng `>`; DESC dùng `<`. Khi hỗn hợp, từng khóa có dấu riêng.

### 56.4. “Dùng `<=` để không bỏ phần tử”

Dùng `<=` thường làm lặp last item đã trả. Cần điều kiện strict theo toàn bộ sort key.

### 56.5. “Cứ có cursor là không cần ORDER BY”

Sai. Cursor chỉ có ý nghĩa **trong một thứ tự được xác định**. Bỏ ORDER BY có thể khiến kết quả thay đổi tùy SQL plan.

### 56.6. “pageSize+1 là một bản ghi phụ không cần quan tâm”

Bản ghi extra rất quan trọng cho hasNext; nhưng **không được dùng làm nextCursor**, vì nó chưa được trả cho client.

### 56.7. “Keyset tự tránh N+1”

Không. Fetch plan/JPA associations là vấn đề độc lập. Cần DTO, fetch join to-one, batch hoặc two-step child loading.

### 56.8. “Keyset sửa luôn collection JOIN FETCH pagination”

Không. Nếu fetch collection và giới hạn SQL JOIN rows, vẫn có nguy cơ in-memory pagination/cắt collection. Page roots trước.

### 56.9. “Cursor chỉ là Base64 JSON nên an toàn”

Không. Base64 không chống sửa hay che dữ liệu. Cần validation, authorization và integrity/confidentiality theo nhu cầu.

### 56.10. “Cursor của status PAID dùng tiếp cho NEW cũng được”

Không. Cursor đánh dấu vị trí trong tập kết quả có filter/sort cụ thể. Đổi filter sẽ khiến vị trí không còn cùng ý nghĩa.

### 56.11. “LocalDateTime.now() làm cursor cũng tương đương createdAt”

Không. Cursor phải phản ánh đúng giá trị sort key thực sự của last returned row.

### 56.12. “Keyset luôn không có duplicate dù data thay đổi”

Không. Nếu sort key bị cập nhật, bản ghi có thể di chuyển qua boundary. Nếu cần duyệt chính xác một lần, cần snapshot hoặc xử lý idempotent.

### 56.13. “Keyset hỗ trợ nhảy trang 1.000 không cần biết gì”

Không tự nhiên. Cursor cần biết khóa boundary; offset phù hợp hơn cho direct numeric page navigation nếu workload cho phép.

### 56.14. “Criteria API nhanh hơn JPQL vì dùng Java”

Không. Provider cuối cùng vẫn sinh SQL; hiệu năng phụ thuộc query plan, indexes và dữ liệu.

### 56.15. “Chỉ cần test 100 Orders có timestamp khác nhau”

Không. Phải test **nhiều rows trùng sort key**, nulls và mixed directions để phát hiện lỗi thuật toán.

---

## 57. Câu hỏi ôn tập

1. Keyset pagination khác offset pagination về cách xác định trang sau ra sao?
2. Với `ORDER BY id DESC`, điều kiện seek trang tiếp theo là gì?
3. Với `ORDER BY id ASC`, dấu so sánh nào đúng?
4. Vì sao không dùng `<=` để đi tiếp?
5. Tại sao `createdAt` một mình thường không đủ làm cursor?
6. Unique tie-breaker có vai trò gì?
7. Với `createdAt DESC,id DESC`, seek predicate hai nhánh là gì?
8. Vì sao thiếu parentheses quanh OR có thể làm sai tenant/status filter?
9. Một cursor cần lưu những giá trị nào nếu ORDER BY gồm ba khóa?
10. Cách dựng lexicographic seek predicate tổng quát là gì?
11. Với sort `priority ASC,createdAt DESC,id ASC`, mỗi nhánh dùng dấu nào?
12. Vì sao tuple comparison không mặc nhiên portable qua JPQL?
13. Vì sao nên tách query first page và after-cursor?
14. `setFirstResult()` có cần cho keyset query không?
15. Vì sao query pageSize+1 giúp tính hasNext?
16. Cursor cần lấy từ bản ghi nào khi có extra peek?
17. Nếu fetched bằng đúng pageSize rows, làm sao biết hasNext?
18. Criteria API dùng methods nào cho so sánh, AND, OR?
19. Vì sao Criteria không tự tránh bug nếu orderBy khác seek?
20. Criteria `cb.construct` phù hợp với use case nào?
21. Vì sao một query JOIN Lines có thể làm hasNext sai?
22. EXISTS giúp giữ mỗi Order một vị trí logic ra sao?
23. Với two-step, vì sao fetch query không cần pagination?
24. Tại sao `IN :ids` không bảo đảm thứ tự?
25. Vì sao chỉ fetch IDs của content mà không fetch extra peek?
26. Keyset giúp giảm offset drift do insert mới ở đầu danh sách thế nào?
27. Trong trường hợp nào keyset vẫn có duplicate/missing vì mutable sort keys?
28. High-water timestamp có tương đương snapshot database không?
29. Thứ tự NULL của database có thể ảnh hưởng keyset ra sao?
30. Làm sao xây seek predicate khi cursor nằm trong nhóm NULLS LAST?
31. Vì sao `LocalDateTime` và precision ảnh hưởng correctness của cursor?
32. Nếu sort bằng LOWER(name), seek có cần dùng LOWER(name) không?
33. Vì sao collation của database quan trọng khi so sánh chuỗi?
34. Cursor được encode Base64 có tự chống sửa không?
35. Cursor nên gắn với những thông tin filter/sort gì?
36. Vì sao tenant ID không nên tin từ cursor?
37. Spring Data Pageable và scrolling APIs có thể khác nhau theo phiên bản thế nào?
38. Keyset có cần COUNT tổng số phần tử không?
39. Khi nào Count vẫn cần và đếm toàn tập hay phần còn lại?
40. Composite index theo tenant/status/createdAt/id giúp gì?
41. Vì sao EXPLAIN cần kiểm tra trên DB thực?
42. Khi nào keyset không đáng phức tạp hơn offset?
43. Nếu sort theo MIN(line.sku), cursor cần gì?
44. Vì sao aggregate sort key dễ thay đổi?
45. Truy vấn trang trước khác trang sau ở điều kiện và ORDER BY thế nào?
46. Vì sao không đảo cả query khi chỉ muốn xem trang trước?
47. Làm sao test một tập dữ liệu tĩnh không bỏ/lặp items?
48. Nên theo dõi những chỉ số gì khi so sánh offset và keyset?
49. Vì sao ID ngẫu nhiên dạng UUID không mặc nhiên là sortable cursor key portable?
50. Với hệ thống audit đòi hỏi duyệt đúng một lần, cần cơ chế gì ngoài keyset?

---

## 58. Bảng ghi nhớ

| Mục tiêu | JPQL/Criteria |
|---|---|
| Tiếp sau ID tăng | `WHERE id > :lastId ORDER BY id ASC` |
| Tiếp sau ID giảm | `WHERE id < :lastId ORDER BY id DESC` |
| Sau (time,id) DESC/DESC | `time < :t OR (time = :t AND id < :id)` |
| Sau (time,id) ASC/ASC | `time > :t OR (time = :t AND id > :id)` |
| ASC/DESC hỗn hợp | Lexicographic OR branches, mỗi khóa đúng chiều |
| Criteria so sánh giảm | `cb.lessThan(path,cursorValue)` |
| Criteria so sánh tăng | `cb.greaterThan(path,cursorValue)` |
| Criteria bằng nhau | `cb.equal(path,cursorValue)` |
| Ghép seek predicate | `cb.or(...,cb.and(...))` |
| Tính hasNext không COUNT | `setMaxResults(pageSize+1)` |
| Sinh cursor đúng | Key từ last returned item |
| Bảo đảm order ổn định | ORDER BY keys + unique ID |
| Filter child không nhân root | `WHERE EXISTS (subquery)` |
| Cần nested child collection | Page IDs rồi fetch child theo IDs |
| Không muốn N+1 ở list | DTO projection hoặc fetch plan tường minh |
| Cursor nullable key | NULL ordering và predicate riêng |
| Cursor API | Encode + validate + bind filters/sort/tenant |
| Truy vấn trang trước | Reverse seek comparison, reverse ORDER BY, reverse content |
| Cần trang số N tùy ý | Cân nhắc offset |
| Có dữ liệu mutable | Snapshot/consistency/idempotency |
| Tối ưu tốc độ | Index khớp filter/sort + EXPLAIN |

### Sơ đồ cuối

```text
                  REQUEST TRANG ĐẦU
                         |
                         v
                 FILTER + ORDER BY
                   (createdAt DESC,
                    id DESC)
                         |
                         v
                 setMaxResults(N+1)
                         |
                         v
                 N items + extra?
                         |
              +----------+----------+
              |                     |
         hasNext=false         hasNext=true
              |                     |
       nextCursor=null      Cursor từ item thứ N
                                    |
                                    v
                         REQUEST TRANG TIẾP
                                    |
                                    v
                         VALIDATE CURSOR
                         + tenant/filters/sort
                                    |
                                    v
                         SEEK PREDICATE:
                         time < :lastTime
                         OR (time=:lastTime
                             AND id < :lastId)
                                    |
                                    v
                          ORDER BY CŨ
                                    |
                                    v
                           N ITEMS + EXTRA
                                    |
                                    v
                              LẶP LẠI
```

**Nguyên tắc cuối bài:** thiết kế keyset pagination bằng JPQL hoặc Criteria không bắt đầu từ việc chọn một API có tên “cursor”, mà bắt đầu từ **thứ tự dữ liệu có thể xác định hoàn toàn**. Hãy sắp theo các khóa ổn định và unique, lưu đủ giá trị vào cursor, diễn đạt điều kiện **“đứng sau” theo thứ tự từ điển** với các nhánh `OR`/`AND` đúng chiều, và dùng `pageSize+1` để biết còn trang tiếp mà không nhất thiết COUNT. Với dữ liệu phức tạp, giữ filters/authorization và sort nhất quán, xử lý NULL/collation/timestamp chính xác, tránh phân trang trên rows bị JOIN collection nhân, và xác minh trên database thật. Keyset giúp đi tiếp hiệu quả và giảm một số lỗi offset drift, nhưng **không thay thế transaction isolation, snapshot hay chính sách xử lý bản ghi thay đổi đồng thời**.

