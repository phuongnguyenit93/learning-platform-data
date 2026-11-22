# Tổng hợp dữ liệu bằng COUNT, SUM, AVG, MIN và MAX trong JPQL

Trong ứng dụng Java Persistence API (JPA), không phải truy vấn nào cũng cần tải toàn bộ entity rồi duyệt bằng Java. Những câu hỏi như “có bao nhiêu đơn hàng?”, “doanh thu của mỗi khách hàng là bao nhiêu?”, “giá trị đơn hàng trung bình là bao nhiêu?” hoặc “đơn gần nhất được đặt lúc nào?” nên thường được tính ở **database** bằng các **hàm tổng hợp** (*aggregate functions*).

JPQL (*Jakarta Persistence Query Language*) hỗ trợ năm hàm tổng hợp nền tảng:

- **`COUNT`** — đếm số phần tử/kết quả đáp ứng điều kiện.
- **`SUM`** — tính tổng các giá trị số.
- **`AVG`** — tính trung bình cộng các giá trị số.
- **`MIN`** — tìm giá trị nhỏ nhất theo thứ tự so sánh phù hợp.
- **`MAX`** — tìm giá trị lớn nhất.

Điểm khác biệt với SQL là JPQL truy vấn **entity và persistent attributes** của mô hình Java. Ví dụ:

```jpql
select count(o)
from SalesOrder o
where o.status = :status
```

`SalesOrder` là tên entity, `o.status` là thuộc tính của entity; provider ánh xạ chúng sang bảng/cột vật lý và thực thi SQL phù hợp. Không dùng tên bảng `sales_order` hoặc cột `order_status` ngay trong câu JPQL chỉ vì database dùng các tên đó.

Bài học thuộc chương **JPQL nâng cao** của module *Data Persistence Relational Access ORM JPA*. Ngoài cú pháp từng hàm, chúng ta sẽ phân tích **kiểu Java của kết quả**, **giá trị NULL**, **nhóm rỗng**, **JOIN làm nhân bản dòng**, **GROUP BY/HAVING**, **DTO projection**, **truy vấn con**, **phân trang kết quả tổng hợp**, và cách tránh tính sai tổng khi kết hợp nhiều quan hệ.

## 1. Vì sao tổng hợp ở database thay vì đọc entity rồi tính bằng Java?

Một cách làm ngây thơ:

```java
List<SalesOrder> orders = em.createQuery(
    "select o from SalesOrder o",
    SalesOrder.class
).getResultList();

long count = orders.size();

BigDecimal total = orders.stream()
    .map(SalesOrder::getTotalAmount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Với vài phần tử, cách này dễ hiểu. Nhưng khi bảng có hàng triệu đơn hàng:

1. Database có thể phải trả rất nhiều dòng và cột qua mạng.
2. JPA provider phải tạo các entity instances, áp dụng mapping và duy trì persistence context.
3. Bộ nhớ heap tăng theo số entity được tải.
4. Ứng dụng phải lặp và tính toán thay vì tận dụng query optimizer.
5. Nếu truy cập association lazy trong quá trình duyệt, có thể phát sinh nhiều truy vấn bổ sung (*N+1*).

Truy vấn tổng hợp:

```java
Long count = em.createQuery(
    "select count(o) from SalesOrder o",
    Long.class
).getSingleResult();

BigDecimal total = em.createQuery(
    "select sum(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();
```

Database thường chỉ trả **một giá trị kết quả** cho mỗi query tổng hợp không phân nhóm. Không cần materialize mọi `SalesOrder` chỉ để lấy số lượng hoặc tổng.

**Lưu ý:** Đây là lợi ích điển hình, không bảo đảm mọi aggregate query đều nhanh. `COUNT(DISTINCT ...)`, join qua nhiều bảng hoặc lọc không có index có thể vẫn tốn kém. Tối ưu phải dựa trên SQL thực tế, query plan và dữ liệu thật.

## 2. Mô hình thực hành xuyên suốt: Customer, SalesOrder, OrderLine

Giả sử một cửa hàng có:

- `Customer` — khách hàng.
- `SalesOrder` — đơn hàng của khách hàng.
- `OrderLine` — dòng hàng thuộc một đơn.
- `OrderStatus` — trạng thái đơn hàng.

Sơ đồ:

```text
+-------------------+          +--------------------+
| Customer          |          | SalesOrder         |
|-------------------|          |--------------------|
| id                | 1      N | id                 |
| customerName      |<---------| customer           |
| email             |          | orderNumber        |
| orders            |          | status             |
+-------------------+          | totalAmount        |
                               | discountAmount?    |
                               | placedAt           |
                               | lines              |
                               +--------------------+
                                           | 1
                                           |
                                           | N
                                +---------------------+
                                | OrderLine           |
                                |---------------------|
                                | id                  |
                                | order               |
                                | productSku          |
                                | quantity            |
                                | unitPrice           |
                                +---------------------+
```

### 2.1. Entity Customer

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "crm_customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String customerName;

    @Column(nullable = false, unique = true)
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
}
```

### 2.2. Enum và entity SalesOrder

```java
package com.example.shop.persistence;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
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

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", precision = 18, scale = 2,
            nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "discount_amount", precision = 18, scale = 2)
    private BigDecimal discountAmount;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected SalesOrder() {
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

### 2.3. Entity OrderLine

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "sales_order_line")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "product_sku", nullable = false)
    private String productSku;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", precision = 18, scale = 2,
            nullable = false)
    private BigDecimal unitPrice;

    protected OrderLine() {
    }
}
```

Ở đây:

- `SalesOrder` là **entity name** dùng trong JPQL.
- `sales_order` là **table name** dùng trong SQL.
- `o.totalAmount` là **persistent attribute** Java; SQL column là `total_amount`.
- `o.customer` là association tới Customer, thay vì tự viết `customer_id`.
- `o.lines` là collection của các OrderLine, có thể làm tăng số dòng khi JOIN.

### 2.4. Dữ liệu mẫu để tự tính và đối chiếu

Giả sử database chứa:

**Customer**

| ID | Khách hàng |
|---:|---|
| 1 | An |
| 2 | Bình |
| 3 | Chi |

**SalesOrder**

| ID | Customer ID | Status | totalAmount | discountAmount |
|---:|---:|---|---:|---:|
| 101 | 1 | PAID | 100.00 | 10.00 |
| 102 | 1 | PAID | 200.00 | NULL |
| 103 | 1 | NEW | 150.00 | 0.00 |
| 104 | 2 | PAID | 200.00 | 20.00 |

Khách hàng Chi chưa có đơn hàng. Giả sử mỗi đơn có số dòng hàng như sau:

| Order ID | Số OrderLine |
|---:|---:|
| 101 | 2 |
| 102 | 1 |
| 103 | 2 |
| 104 | 3 |

Kỳ vọng khi tính trên **SalesOrder, chưa JOIN lines**:

- Tổng số đơn: **4**.
- Số đơn `PAID`: **3**.
- Tổng `totalAmount` của tất cả đơn: **650.00**.
- Tổng `totalAmount` của các đơn `PAID`: **500.00**.
- Trung bình giá trị tất cả đơn: **162.5**.
- Min/Max `totalAmount`: **100.00 / 200.00**.
- Số đơn của An/Bình/Chi: **3 / 1 / 0**.
- Tổng đơn của An/Bình/Chi: **450.00 / 200.00 / NULL** nếu dùng `LEFT JOIN` và `SUM` không có giá trị cho Chi.
- Số hàng OrderLine trên tất cả đơn: **8**, nhưng số đơn vẫn chỉ là **4**.

Những giá trị này sẽ giúp thấy rõ các bẫy về `NULL`, nhóm không có phần tử và JOIN làm tăng số dòng.

## 3. COUNT: đếm entity hoặc giá trị không NULL

Câu đơn giản nhất:

```jpql
select count(o)
from SalesOrder o
```

Thực thi:

```java
Long orderCount = em.createQuery(
    "select count(o) from SalesOrder o",
    Long.class
).getSingleResult();
```

`COUNT` trong JPQL chuẩn trả về **`Long`**. Không khai báo `Integer.class` chỉ vì bảng có ít dòng, và đừng ép sang `int` nếu không kiểm soát overflow.

### 3.1. COUNT(entity variable)

```jpql
select count(o)
from SalesOrder o
where o.status = :status
```

`COUNT(o)` đếm các lần xuất hiện của entity `o` trong kết quả logic của truy vấn sau FROM/JOIN/WHERE. Nếu query không JOIN collection làm nhân bản đơn, đó là số đơn phù hợp.

Java:

```java
Long paidCount = em.createQuery(
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

Với dữ liệu mẫu: `paidCount == 3L`.

### 3.2. COUNT(attribute) bỏ qua NULL

```jpql
select count(o.discountAmount)
from SalesOrder o
```

Câu này **không đếm tất cả SalesOrder**. Nó đếm những dòng có `discountAmount` **khác NULL**.

Theo dữ liệu mẫu:

- `COUNT(o)` = 4.
- `COUNT(o.discountAmount)` = 3 vì một đơn có discountAmount = NULL.
- `discountAmount = 0.00` vẫn được đếm, vì 0 **khác NULL**.

Đó là khác biệt giữa “không có giá trị” và “giá trị bằng không”.

### 3.3. COUNT(*) trong SQL và COUNT(o) trong JPQL

Trong SQL thường viết:

```sql
SELECT COUNT(*)
FROM sales_order;
```

Khi diễn đạt bằng JPQL hướng entity, cách dễ hiểu và portable là:

```jpql
select count(o)
from SalesOrder o
```

Đừng máy móc sao chép `SELECT COUNT(*) FROM sales_order` vào `EntityManager.createQuery`. Hãy dùng tên entity và kiểu biểu thức mà JPQL/JPA version của dự án hỗ trợ.

### 3.4. COUNT với WHERE

Ví dụ đếm đơn được thanh toán trong khoảng thời gian nửa mở:

```jpql
select count(o)
from SalesOrder o
where o.status = :status
  and o.placedAt >= :startInclusive
  and o.placedAt < :endExclusive
```

`Instant` nên được bind với `Instant`:

```java
Long count = em.createQuery(
    """
    select count(o) from SalesOrder o
    where o.status = :status
      and o.placedAt >= :start
      and o.placedAt < :end
    """,
    Long.class
)
.setParameter("status", OrderStatus.PAID)
.setParameter("start", startInstant)
.setParameter("end", endInstant)
.getSingleResult();
```

Điều kiện nửa mở tránh chồng lặp khi hai khoảng thời gian liền nhau có chung mốc.

### 3.5. COUNT(DISTINCT ...)

Giả sử muốn đếm **số khách hàng đã phát sinh ít nhất một đơn**, không phải số đơn:

```jpql
select count(distinct c.id)
from SalesOrder o
join o.customer c
```

Với dữ liệu mẫu, kết quả là 2: An và Bình. Chi không có đơn nên không xuất hiện trong nguồn `SalesOrder o`.

`DISTINCT` áp dụng trước khi đếm, theo giá trị biểu thức được chọn.

Nếu muốn đếm số lượng giá trị `totalAmount` khác nhau:

```jpql
select count(distinct o.totalAmount)
from SalesOrder o
```

Dữ liệu mẫu có 100, 150, 200 => kết quả **3**, dù có 4 đơn. Hai đơn khác nhau cùng giá trị 200 chỉ góp một **giá trị phân biệt**.

Không dùng `COUNT(DISTINCT ...)` theo thói quen mà không xác định: **muốn đếm entity, dòng join hay các giá trị khác nhau?**

## 4. SUM: tính tổng dữ liệu số

`SUM` thường dùng cho doanh thu, số lượng, trọng lượng hoặc điểm.

```jpql
select sum(o.totalAmount)
from SalesOrder o
```

Java:

```java
BigDecimal total = em.createQuery(
    "select sum(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();
```

Với dữ liệu mẫu: `650.00`.

### 4.1. SUM theo điều kiện

Chỉ tính đơn đã thanh toán:

```jpql
select sum(o.totalAmount)
from SalesOrder o
where o.status = :paidStatus
```

Java:

```java
BigDecimal paidRevenue = em.createQuery(
    """
    select sum(o.totalAmount)
    from SalesOrder o
    where o.status = :paidStatus
    """,
    BigDecimal.class
)
.setParameter("paidStatus", OrderStatus.PAID)
.getSingleResult();
```

Với dữ liệu mẫu: 100 + 200 + 200 = **500.00**.

**Quan trọng về nghiệp vụ:** `SUM(totalAmount)` của đơn PAID không nhất thiết là “doanh thu kế toán”. Có thể cần loại đơn hoàn trả, xử lý phí vận chuyển, chiết khấu, thuế, múi giờ, currency và payment settlement. Hàm SUM thực hiện phép cộng theo dữ liệu lọc, không tự hiểu định nghĩa doanh thu của doanh nghiệp.

### 4.2. SUM bỏ qua NULL

```jpql
select sum(o.discountAmount)
from SalesOrder o
```

Với dữ liệu mẫu: 10 + 0 + 20 = **30.00**; giá trị NULL bị bỏ qua.

Nếu tất cả `discountAmount` là NULL hoặc không có đơn nào phù hợp, `SUM` sẽ trả `null`, không phải mặc định trả `BigDecimal.ZERO`.

### 4.3. SUM(DISTINCT ...) không phải khử trùng đơn hàng

```jpql
select sum(distinct o.totalAmount)
from SalesOrder o
```

Với các mức 100, 200, 150, 200, truy vấn chỉ cộng **100 + 150 + 200 = 450** do hai giá trị 200 được coi là trùng **về giá trị**.

Đây **không phải** cách sửa lỗi JOIN làm nhân bản một SalesOrder! Hai đơn hợp lệ có cùng số tiền là hai giao dịch khác nhau và thường đều phải góp vào tổng.

**Cảnh báo:** `SUM(DISTINCT amount)` chỉ đúng khi nghiệp vụ thật sự cần cộng mỗi **giá trị amount khác nhau một lần**. Nó không tương đương “cộng mỗi entity một lần”.

### 4.4. SUM và kiểu số

Nếu thuộc tính là `BigDecimal`, kỳ vọng kết quả `SUM` là `BigDecimal` theo quy tắc kiểu của JPQL. Nếu thuộc tính là `int`/`Integer`/`long`/`Long`, kết quả tổng đối với kiểu integral thông thường là `Long`. Nếu `BigInteger` thì tổng là `BigInteger`; với `float`/`double` thì thường là `Double`.

Chi tiết đầy đủ nằm ở bảng kiểu ở phần sau. Không mặc định mọi SUM trả Double hoặc tất cả numeric aggregate trả BigDecimal.

### 4.5. Có thể SUM(quantity * unitPrice) không?

Một số provider hỗ trợ tổng hợp trên biểu thức số học, chẳng hạn một biến thể `sum(i.quantity * i.unitPrice)`. Nhưng khi đặt mục tiêu **JPQL portable**, cần lưu ý ngữ pháp aggregate `SUM` của JPA truyền thống tập trung vào **state-valued path expression** — một thuộc tính số đã ánh xạ — và sự hỗ trợ biểu thức tính toán trực tiếp trong aggregate khác nhau theo phiên bản/provider.

Hướng dễ bảo trì nếu tính tiền dòng hàng thường xuyên:

- Có thuộc tính được lưu/ánh xạ hợp lệ `lineTotal` và dùng `sum(i.lineTotal)`.
- Thiết kế query SQL native/Criteria hoặc tính theo cách provider hỗ trợ rõ ràng nếu cần biểu thức động.
- Nếu `lineTotal` được lưu dư thừa, phải bảo vệ consistency với `quantity` và `unitPrice`.
- Không giả định `sum(i.quantity * i.unitPrice)` sẽ chạy giống nhau trên mọi JPA implementation.

Điểm học chính của bài này vẫn là `SUM` trên thuộc tính số persistent.

## 5. AVG: trung bình cộng và kiểu trả về Double

Cú pháp:

```jpql
select avg(o.totalAmount)
from SalesOrder o
```

Java:

```java
Double average = em.createQuery(
    "select avg(o.totalAmount) from SalesOrder o",
    Double.class
).getSingleResult();
```

Với dữ liệu mẫu: tổng 650 chia 4 = **162.5**.

### 5.1. Vì sao AVG(BigDecimal) lại nhận Double?

Theo quy tắc kiểu tổng hợp của JPQL, **`AVG` trả về `Double`**, kể cả khi thuộc tính đầu vào là kiểu số như `BigDecimal`. Vì vậy kiểu sau là không phù hợp để kỳ vọng portable:

```java
// Không nên giả định AVG trên BigDecimal trả BigDecimal.
BigDecimal avg = em.createQuery(
    "select avg(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();
```

Một DTO constructor chứa `avg(o.totalAmount)` cũng nên khai báo trường tương ứng là `Double`, trừ khi truy vấn/provider có chuyển kiểu tường minh phù hợp.

### 5.2. AVG loại các giá trị NULL

Ví dụ:

```jpql
select avg(o.discountAmount)
from SalesOrder o
```

Các giá trị là 10.00, NULL, 0.00, 20.00. Trung bình là:

```text
(10.00 + 0.00 + 20.00) / 3 = 10.0
```

Mẫu số là **số giá trị không NULL**, không phải tổng số 4 đơn.

Đó là lý do `AVG(nullableField)` không tương đương với `SUM(nullableField) / COUNT(allEntities)`.

### 5.3. Tài chính và precision của AVG

`Double` dùng biểu diễn floating-point nhị phân, có thể không biểu diễn chính xác mọi số thập phân tiền tệ. Nếu kết quả là **số tiền trung bình** cần làm tròn theo quy tắc kế toán, có thể cân nhắc:

1. Truy vấn `SUM(o.totalAmount)` nhận `BigDecimal`.
2. Truy vấn `COUNT(o.totalAmount)` nhận `Long`.
3. Dùng `BigDecimal.divide` với scale/rounding mode được quy định nghiệp vụ.

Ví dụ:

```java
BigDecimal sum = ...; // SUM trên BigDecimal.
Long count = ...;     // COUNT field non-null.

BigDecimal averageMoney = count == 0L
    ? null
    : sum.divide(
        BigDecimal.valueOf(count),
        2,
        RoundingMode.HALF_UP
    );
```

`RoundingMode` đến từ `java.math`. Đây là **chiến lược tính trung bình theo BigDecimal** ở Java nếu nghiệp vụ cần kiểm soát rounding, không thay đổi hợp đồng `AVG` chuẩn trả Double.

Có thể lấy cả SUM và COUNT trong **một query** để giảm số lần gọi database:

```jpql
select sum(o.totalAmount), count(o.totalAmount)
from SalesOrder o
where o.status = :status
```

Kết quả gồm `BigDecimal` và `Long` trong một dòng `Object[]` hoặc DTO phù hợp.

### 5.4. AVG(DISTINCT amount)

```jpql
select avg(distinct o.totalAmount)
from SalesOrder o
```

Đây là trung bình của **các mức amount khác nhau**, không phải trung bình của tất cả đơn. Hai đơn có cùng amount sẽ chỉ đóng góp một mức giá vào tập distinct.

Chỉ dùng khi đó là ngữ nghĩa mà nghiệp vụ yêu cầu.

## 6. MIN và MAX: nhỏ nhất, lớn nhất

Cú pháp:

```jpql
select min(o.totalAmount)
from SalesOrder o
```

```jpql
select max(o.totalAmount)
from SalesOrder o
```

Java:

```java
BigDecimal minAmount = em.createQuery(
    "select min(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();

BigDecimal maxAmount = em.createQuery(
    "select max(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();
```

Với dữ liệu mẫu: min = **100.00**, max = **200.00**.

### 6.1. MIN/MAX của giá trị thời gian

Ngoài số, các thuộc tính có kiểu so sánh phù hợp cũng thường dùng với MIN/MAX:

```jpql
select min(o.placedAt), max(o.placedAt)
from SalesOrder o
```

Đây là cách trả về thời điểm đặt đơn **sớm nhất** và **muộn nhất**, không phải lấy entity Order.

Nếu `placedAt` ánh xạ từ `Instant` trong Jakarta Persistence/provider có hỗ trợ, kết quả thường được đọc theo kiểu Java tương ứng. Cần bảo đảm hệ thống/JPA version có mapping thời gian phù hợp, và dùng timezone/clock thống nhất theo nghiệp vụ.

### 6.2. MIN/MAX trả giá trị, không trả cả entity

Câu:

```jpql
select max(o.totalAmount)
from SalesOrder o
```

trả số tiền lớn nhất, **không** trả `SalesOrder` có số tiền đó.

Nếu cần entity có amount lớn nhất, có thể dùng một truy vấn con:

```jpql
select o
from SalesOrder o
where o.totalAmount = (
    select max(o2.totalAmount)
    from SalesOrder o2
)
```

Cách này có thể trả **nhiều SalesOrder** nếu chúng cùng đạt mức tối đa, ví dụ hai đơn giá 200.00.

Nếu chỉ cần một đơn nhất theo tiêu chí phụ, sử dụng `ORDER BY` và `setMaxResults(1)`:

```java
List<SalesOrder> top = em.createQuery(
    """
    select o
    from SalesOrder o
    order by o.totalAmount desc, o.id asc
    """,
    SalesOrder.class
)
.setMaxResults(1)
.getResultList();
```

Hai chiến lược khác nhau:

- `MAX` + subquery trả **mọi entity đạt giá trị cực đại**.
- `ORDER BY ...` + limit trả **một phần tử được chọn theo thứ tự ổn định**.

### 6.3. MIN/MAX bỏ qua NULL

`MIN(o.discountAmount)` và `MAX(o.discountAmount)` bỏ qua các giá trị NULL. Với 10, NULL, 0, 20:

- Min discountAmount = 0.00.
- Max discountAmount = 20.00.

Nếu tất cả đều NULL, cả MIN và MAX trả `null`.

### 6.4. MIN/MAX trên String và thứ tự so sánh

Một số kiểu string/orderable có thể dùng với MIN/MAX khi được JPA/provider hỗ trợ theo kiểu dữ liệu và ngữ nghĩa so sánh. Tuy nhiên, thứ tự chữ cái phụ thuộc **collation** và database. Với tên khách hàng tiếng Việt, không nên mặc định `MIN(customerName)` chính là “tên đứng đầu theo bảng chữ cái tiếng Việt” nếu collation chưa được xác định.

Khi yêu cầu liên quan ngôn ngữ tự nhiên, accent/case, Unicode normalization hay business sorting, cần chọn collation/cơ chế sort có chủ đích.

## 7. Kiểu Java trả về của năm hàm tổng hợp

Một nguyên nhân thường gặp của lỗi runtime là khai báo sai `TypedQuery<T>` hoặc constructor DTO.

| Biểu thức JPQL | Kiểu thuộc tính đầu vào | Kiểu kết quả chuẩn thường mong đợi |
|---|---|---|
| `count(o)` | Entity/biểu thức phù hợp | `Long` |
| `count(o.discountAmount)` | `BigDecimal` nullable | `Long` |
| `sum(o.quantity)` | `int`/`Integer` | `Long` |
| `sum(o.longQuantity)` | `long`/`Long` | `Long` |
| `sum(o.bigCount)` | `BigInteger` | `BigInteger` |
| `sum(o.totalAmount)` | `BigDecimal` | `BigDecimal` |
| `sum(o.doubleAmount)` | `double`/`Double` hoặc `float` | `Double` |
| `avg(o.totalAmount)` | Các kiểu numeric phù hợp | `Double` |
| `min(o.totalAmount)` | `BigDecimal` | `BigDecimal` |
| `max(o.totalAmount)` | `BigDecimal` | `BigDecimal` |
| `min(o.placedAt)` | Thời gian có mapping phù hợp | Kiểu Java tương ứng của thuộc tính |
| `max(o.placedAt)` | Thời gian có mapping phù hợp | Kiểu Java tương ứng của thuộc tính |

`MIN` và `MAX` trả giá trị có kiểu tương ứng với state-valued path expression đầu vào, trong phạm vi loại attribute được hỗ trợ.

### 7.1. Vì sao SUM(int) không trả Integer?

Một cột quantity có từng giá trị nằm trong phạm vi `int` không đồng nghĩa **tổng** của hàng triệu row cũng nằm trong phạm vi `int`. JPA chọn `Long` cho SUM của các integral types thông thường để có không gian biểu diễn rộng hơn.

Nhưng `Long` vẫn có giới hạn. Với khối lượng rất lớn, cần đánh giá database numeric precision và dùng kiểu số/schema/query thích hợp; không coi `Long` là vô hạn.

### 7.2. Không ép sang Object rồi cast tùy tiện

Ví dụ nguy hiểm:

```java
Object result = em.createQuery(
    "select avg(o.totalAmount) from SalesOrder o"
).getSingleResult();

BigDecimal average = (BigDecimal) result; // Có thể ClassCastException.
```

Nên dùng:

```java
Double average = em.createQuery(
    "select avg(o.totalAmount) from SalesOrder o",
    Double.class
).getSingleResult();
```

Nếu provider/driver trả khác vì một extension hoặc native query, cần xử lý dựa trên hợp đồng thực tế. Với JPQL chuẩn, chọn kiểu theo các quy tắc aggregate trước khi viết DTO.

## 8. Quy tắc NULL của aggregate: điểm cực kỳ quan trọng

Trong SQL và JPQL, `NULL` không đồng nghĩa với 0. Các hàm aggregate có quy tắc riêng.

| Hàm | Các giá trị không NULL | Tập rỗng hoặc tất cả giá trị là NULL |
|---|---|---|
| `COUNT(expression)` | Đếm các giá trị không NULL | **`0L`** |
| `COUNT(entity)` | Đếm entity xuất hiện trong kết quả | **`0L`** |
| `SUM(expression)` | Tổng các giá trị không NULL | **`null`** |
| `AVG(expression)` | Trung bình các giá trị không NULL | **`null`** |
| `MIN(expression)` | Giá trị nhỏ nhất không NULL | **`null`** |
| `MAX(expression)` | Giá trị lớn nhất không NULL | **`null`** |

### 8.1. Ví dụ không có đơn CANCELLED

Giả sử dữ liệu mẫu chưa có đơn `CANCELLED`.

```java
Long count = em.createQuery(
    """
    select count(o)
    from SalesOrder o
    where o.status = :status
    """,
    Long.class
)
.setParameter("status", OrderStatus.CANCELLED)
.getSingleResult();

BigDecimal sum = em.createQuery(
    """
    select sum(o.totalAmount)
    from SalesOrder o
    where o.status = :status
    """,
    BigDecimal.class
)
.setParameter("status", OrderStatus.CANCELLED)
.getSingleResult();
```

Kết quả:

```text
count = 0
sum   = null
```

`SUM` không trả 0 theo mặc định khi không có dữ liệu. Phải tự quyết định **“không có dữ liệu” có nên trình bày là 0 hay không**.

### 8.2. COALESCE khi business muốn hiển thị 0

Có thể dùng `COALESCE` trong JPQL:

```jpql
select coalesce(sum(o.totalAmount), :zero)
from SalesOrder o
where o.status = :status
```

Bind `:zero` là `BigDecimal.ZERO` để thể hiện đúng kiểu mong muốn:

```java
BigDecimal total = em.createQuery(
    """
    select coalesce(sum(o.totalAmount), :zero)
    from SalesOrder o
    where o.status = :status
    """,
    BigDecimal.class
)
.setParameter("zero", BigDecimal.ZERO)
.setParameter("status", OrderStatus.CANCELLED)
.getSingleResult();
```

`COALESCE` trả giá trị đầu tiên khác NULL. Tùy provider/DB, type inference cho các biểu thức phức tạp hoặc literal numeric có thể khác nhau, nên bind đúng kiểu và kiểm thử query trong môi trường thật.

Trong nhiều trường hợp xử lý ở Java cũng rõ ràng:

```java
BigDecimal safeTotal =
    total != null ? total : BigDecimal.ZERO;
```

Tuy nhiên, nếu số liệu có ý nghĩa “chưa có dữ liệu đo” khác với “đã đo và bằng 0”, **không nên tự chuyển NULL thành 0** vì có thể làm sai ý nghĩa phân tích.

### 8.3. AVG và trường hợp không thể chia cho 0

Nếu dùng chiến lược tự tính:

```java
BigDecimal sum = ...;
Long count = ...;
```

hãy xử lý `count == 0` trước khi `sum.divide(...)`. Không dùng `BigDecimal.ZERO` làm mẫu số hoặc giả định `SUM` luôn khác NULL.

## 9. Aggregate không GROUP BY: một nhóm duy nhất

Câu:

```jpql
select count(o), sum(o.totalAmount), avg(o.totalAmount)
from SalesOrder o
where o.status = :status
```

là tổng hợp **toàn bộ các row thỏa điều kiện thành một nhóm logic**.

Nếu không có row phù hợp, truy vấn aggregate không GROUP BY vẫn cho ra **một dòng aggregate** trong trường hợp thông thường:

```text
COUNT = 0
SUM   = null
AVG   = null
```

Có thể lấy bằng `getSingleResult()`:

```java
Object[] row = em.createQuery(
    """
    select count(o), sum(o.totalAmount), avg(o.totalAmount)
    from SalesOrder o
    where o.status = :status
    """,
    Object[].class
)
.setParameter("status", OrderStatus.CANCELLED)
.getSingleResult();

Long count = (Long) row[0];
BigDecimal sum = (BigDecimal) row[1];
Double avg = (Double) row[2];
```

Điều này khác query `SELECT o` không có kết quả: `getSingleResult()` của query entity thông thường có thể ném `NoResultException`.

### 9.1. Query aggregate có GROUP BY nhưng không có nhóm

```jpql
select o.status, count(o)
from SalesOrder o
where o.status = :status
group by o.status
```

Nếu không có đơn nào thỏa `status`, query này có **không nhóm nào**, vì vậy `getResultList()` trả danh sách rỗng. Không có một row giả `(CANCELLED, 0)` được tự tạo.

Quy tắc nhớ:

- **Global aggregate, không GROUP BY:** thường một result row gồm aggregate; COUNT có thể 0.
- **GROUP BY:** một result row trên mỗi nhóm thực sự tồn tại; không có nhóm thì không có result row.
- **LEFT JOIN từ tập parent:** có thể tạo nhóm cho parent không có child (phần sau), nhưng đó là do nguồn parent vẫn có row.

## 10. GROUP BY: tổng hợp theo từng nhóm

Nếu muốn số lượng và tổng tiền **theo trạng thái đơn hàng**:

```jpql
select
    o.status,
    count(o),
    sum(o.totalAmount)
from SalesOrder o
group by o.status
```

Với dữ liệu mẫu, kết quả logic:

| Status | COUNT(o) | SUM(o.totalAmount) |
|---|---:|---:|
| PAID | 3 | 500.00 |
| NEW | 1 | 150.00 |

Không có hàng `CANCELLED` vì không có nhóm nào trong dữ liệu.

### 10.1. Quy tắc thuộc tính không nằm trong aggregate

Một truy vấn như:

```jpql
select o.status, o.orderNumber, count(o)
from SalesOrder o
group by o.status
```

không phải cách diễn đạt portable để lấy `orderNumber` bất kỳ của mỗi nhóm: `orderNumber` không được tổng hợp và không nằm trong GROUP BY. Một số database có quy tắc nới lỏng dựa trên functional dependency, nhưng không nên dựa vào đó khi viết JPQL chuẩn.

Hướng đúng là chọn:

- Chỉ `o.status` và các aggregate.
- Hoặc thêm những thuộc tính non-aggregate cần thiết vào GROUP BY nếu ngữ nghĩa nhóm phù hợp.
- Hoặc tạo subquery/DTO hoặc truy vấn khác nếu cần một entity đại diện cho nhóm.

### 10.2. GROUP BY nhiều thuộc tính

Tổng hợp theo khách hàng và trạng thái:

```jpql
select
    c.id,
    c.customerName,
    o.status,
    count(o),
    sum(o.totalAmount)
from SalesOrder o
join o.customer c
group by c.id, c.customerName, o.status
```

Có thể có nhóm:

```text
An, PAID -> count 2, sum 300.00
An, NEW  -> count 1, sum 150.00
Bình, PAID -> count 1, sum 200.00
```

Khách hàng Chi chưa có đơn và không xuất hiện vì query bắt đầu từ `SalesOrder o` và dùng INNER JOIN.

### 10.3. GROUP BY theo entity thay vì field

Một số JPQL cho phép GROUP BY theo entity variable trong giới hạn cụ thể, nhưng mức hỗ trợ và việc entity có các persistent field eager/Lob/serialized có thể làm query phức tạp hoặc khó portable.

Khi chỉ cần ID và tên, phương án rõ ràng là:

```jpql
group by c.id, c.customerName
```

và trả DTO scalar tương ứng, thay vì chọn cả entity `c` mà không thật sự cần managed object.

### 10.4. ORDER BY kết quả tổng hợp

```jpql
select o.status, count(o)
from SalesOrder o
group by o.status
order by count(o) desc
```

Đây là sắp xếp các **nhóm** theo số đơn giảm dần. Nếu nhiều nhóm cùng count, muốn kết quả ổn định hãy thêm tiêu chí khác:

```jpql
order by count(o) desc, o.status asc
```

Điều kiện ORDER BY vẫn phải hợp lệ theo JPQL và biểu thức/grouping của query.

## 11. HAVING: lọc sau khi đã nhóm

Câu hỏi “những khách hàng nào có ít nhất hai đơn?”:

```jpql
select
    c.id,
    c.customerName,
    count(o)
from Customer c
join c.orders o
group by c.id, c.customerName
having count(o) >= :minimumOrders
```

Bind:

```java
List<Object[]> rows = em.createQuery(
    """
    select c.id, c.customerName, count(o)
    from Customer c
    join c.orders o
    group by c.id, c.customerName
    having count(o) >= :minimumOrders
    """,
    Object[].class
)
.setParameter("minimumOrders", 2L)
.getResultList();
```

Theo dữ liệu mẫu, chỉ khách hàng An có ít nhất 2 đơn.

### 11.1. WHERE khác HAVING

| Mệnh đề | Lọc cái gì? | Ví dụ |
|---|---|---|
| `WHERE` | Row/association **trước khi nhóm** | Chỉ lấy đơn PAID |
| `GROUP BY` | Chia các row còn lại thành nhóm | Gom theo Customer |
| `HAVING` | Nhóm **sau khi tổng hợp** | Chỉ nhóm có COUNT >= 2 |

Ví dụ “khách có ít nhất hai đơn **PAID**”:

```jpql
select c.id, c.customerName, count(o)
from Customer c
join c.orders o
where o.status = :paidStatus
group by c.id, c.customerName
having count(o) >= 2
```

`WHERE` loại các đơn NEW trước khi COUNT. Khách hàng An còn hai đơn PAID nên thỏa. Bình có một đơn PAID nên không thỏa.

Ngược lại, nếu dùng `HAVING count(o) >= 2` nhưng không WHERE status, bạn đang tìm khách có ít nhất hai đơn **mọi trạng thái**, một mục tiêu khác.

### 11.2. HAVING theo SUM

Tìm khách có tổng giá trị đơn đã thanh toán từ 250:

```jpql
select c.id, c.customerName, sum(o.totalAmount)
from SalesOrder o
join o.customer c
where o.status = :paidStatus
group by c.id, c.customerName
having sum(o.totalAmount) >= :minimumRevenue
```

Bind `minimumRevenue` là `BigDecimal`:

```java
.setParameter("paidStatus", OrderStatus.PAID)
.setParameter("minimumRevenue", new BigDecimal("250.00"))
```

Không ép giá trị tiền thành Double chỉ vì thấy một phép tổng hợp.

### 11.3. Không dùng aggregate trong WHERE của cùng mức query

```jpql
-- Sai ngữ nghĩa dùng aggregate ở WHERE:
select c.id, count(o)
from Customer c join c.orders o
where count(o) >= 2
group by c.id
```

Sửa bằng `HAVING`:

```jpql
select c.id, count(o)
from Customer c join c.orders o
group by c.id
having count(o) >= 2
```

Nếu cần lọc theo aggregate của một query con độc lập, dùng subquery phù hợp trong WHERE (xem phần truy vấn con).

## 12. LEFT JOIN: khách không có đơn vẫn phải xuất hiện

Một báo cáo CRM thường cần hiển thị mọi khách hàng, kể cả người chưa từng đặt đơn.

Nếu viết:

```jpql
select c.id, c.customerName, count(o)
from Customer c
join c.orders o
group by c.id, c.customerName
```

`JOIN` mặc định là INNER JOIN. Khách hàng Chi không có order nên **không xuất hiện**.

Dùng `LEFT JOIN`:

```jpql
select c.id, c.customerName, count(o)
from Customer c
left join c.orders o
group by c.id, c.customerName
```

Kết quả:

| Customer | COUNT(o) |
|---|---:|
| An | 3 |
| Bình | 1 |
| Chi | 0 |

### 12.1. COUNT(o) khác COUNT(c) trong LEFT JOIN

Với khách hàng Chi, LEFT JOIN vẫn giữ một joined row về phía `Customer c`, còn `o` là NULL.

Vì thế:

```jpql
select c.id, count(o), count(c)
from Customer c
left join c.orders o
group by c.id
```

Đối với Chi, `COUNT(o) = 0` nhưng `COUNT(c) = 1` theo ngữ nghĩa joined rows.

Nếu mục tiêu là đếm đơn hàng, hãy dùng **`count(o)`** hoặc một thuộc tính Order non-null như `count(o.id)`, không `count(c)`.

Nếu một Customer có 3 Order, sau join `count(c)` có thể là 3, không phải “có một customer”. Một bản ghi parent có thể xuất hiện nhiều lần trong kết quả join.

### 12.2. SUM của khách không có đơn là NULL

```jpql
select c.id, c.customerName, count(o), sum(o.totalAmount)
from Customer c
left join c.orders o
group by c.id, c.customerName
```

Với Chi:

```text
COUNT(o)           = 0
SUM(o.totalAmount) = null
```

Nếu dashboard muốn hiển thị `0.00`, có thể dùng `COALESCE` hoặc chuyển `null` ở DTO mapper. Điều cần quyết định là “không có đơn” có được hiểu là “doanh thu 0” trong ngữ cảnh báo cáo không.

## 13. Bẫy LEFT JOIN + WHERE: biến thành hiệu ứng INNER JOIN

Muốn đếm **số đơn PAID của tất cả Customer**, kể cả người chưa có đơn PAID.

Một truy vấn dễ viết nhưng không đúng mục tiêu:

```jpql
select c.id, c.customerName, count(o)
from Customer c
left join c.orders o
where o.status = :paidStatus
group by c.id, c.customerName
```

Do `WHERE o.status = PAID` loại các joined rows có `o = NULL` hoặc order không PAID, khách hàng Chi bị loại khỏi kết quả. Câu này chỉ còn khách có ít nhất một đơn PAID.

Một hướng dùng **association JOIN ... ON**:

```jpql
select c.id, c.customerName, count(o)
from Customer c
left join c.orders o on o.status = :paidStatus
group by c.id, c.customerName
```

Với các provider hỗ trợ JPQL `JOIN ... ON` theo phiên bản tương ứng, điều kiện lọc status nằm **trong join**, nên Customer vẫn được giữ nếu không có order PAID.

Kết quả:

| Customer | COUNT(PAID order) |
|---|---:|
| An | 2 |
| Bình | 1 |
| Chi | 0 |

Có thể chọn thiết kế truy vấn con/correlated query khác nếu cần tương thích phiên bản cũ.

**Mẹo tư duy:** Với `LEFT JOIN`, điều kiện ở `ON` và `WHERE` không tương đương khi muốn giữ các parent không có child thỏa điều kiện.

## 14. JOIN làm nhân bản dòng: bẫy cộng tiền nhiều lần

Đây là lỗi quan trọng nhất khi sử dụng aggregate với mô hình một-nhiều.

Giả sử một `SalesOrder` có nhiều `OrderLine`. Truy vấn:

```jpql
select sum(o.totalAmount)
from SalesOrder o
join o.lines i
```

**Không còn chắc trả tổng giá trị đơn đúng.** Vì mỗi order được lặp lại một lần cho mỗi line trong joined rows.

Theo dữ liệu mẫu:

| Order | totalAmount | Số lines | totalAmount góp vào SUM sau JOIN |
|---:|---:|---:|---:|
| 101 | 100.00 | 2 | 200.00 |
| 102 | 200.00 | 1 | 200.00 |
| 103 | 150.00 | 2 | 300.00 |
| 104 | 200.00 | 3 | 600.00 |
| **Tổng** | **650.00** | **8** | **1300.00 (sai mục tiêu)** |

Câu `SUM(o.totalAmount)` sau join lines cộng **giá trị đơn theo mỗi dòng join**, không phải mỗi order một lần.

### 14.1. Đếm đơn có JOIN cũng có thể sai

```jpql
select count(o)
from SalesOrder o
join o.lines i
```

Với dữ liệu mẫu và giả định tất cả order đều có lines, kết quả logic là **8** thay vì **4**.

Nếu muốn đếm đơn **có ít nhất một line**, dùng:

```jpql
select count(distinct o)
from SalesOrder o
join o.lines i
```

Với dữ liệu mẫu: 4.

Hoặc không cần JOIN nếu chỉ đếm mọi SalesOrder:

```jpql
select count(o)
from SalesOrder o
```

### 14.2. Đừng chữa SUM sai bằng SUM(DISTINCT amount)

Một cách sửa sai phổ biến:

```jpql
select sum(distinct o.totalAmount)
from SalesOrder o
join o.lines i
```

Đây không khử trùng theo **ID đơn**, mà khử trùng theo **giá trị tiền**. Nếu hai đơn khác nhau cùng amount 200, chỉ một mức 200 được cộng. Kết quả có thể bằng **450.00**, vẫn sai so với 650.00.

Quy tắc:

- `COUNT(DISTINCT o)` có thể đếm các entity Order khác nhau.
- `SUM(DISTINCT o.totalAmount)` cộng **các mức tiền** khác nhau.
- Không có phép suy diễn đơn giản rằng SUM DISTINCT amount = SUM theo entity identity.

### 14.3. Cách đúng: tổng hợp ở đúng mức hạt dữ liệu

Nếu mục tiêu là tổng `SalesOrder.totalAmount` và không cần điều kiện trên lines, **không JOIN lines**:

```jpql
select sum(o.totalAmount)
from SalesOrder o
```

Nếu mục tiêu là tổng tiền của các đơn **có SKU X**, có thể dùng `EXISTS` thay vì JOIN làm tăng row:

```jpql
select sum(o.totalAmount)
from SalesOrder o
where exists (
    select i.id
    from OrderLine i
    where i.order = o
      and i.productSku = :sku
)
```

Subquery chỉ xác định **order có tồn tại line phù hợp**, không nhân bản mỗi order theo số line. Một order có ba dòng cùng SKU vẫn chỉ đóng góp totalAmount **một lần**.

### 14.4. Nếu cần tổng tiền ở mức OrderLine

Nếu mỗi OrderLine có `lineTotal` đã được ánh xạ/lưu hợp lệ, tổng theo dòng có thể là:

```jpql
select sum(i.lineTotal)
from OrderLine i
```

Nhưng mô hình đang dùng `quantity` và `unitPrice`, chưa có `lineTotal`. Để tính tích quantity × unitPrice trên mỗi dòng, cần quyết định cách biểu diễn portable theo JPA/provider, hoặc dùng native SQL phù hợp:

```sql
SELECT SUM(quantity * unit_price)
FROM sales_order_line;
```

Không trộn cú pháp SQL này vào JPQL `createQuery` rồi mặc định mọi provider chấp nhận cùng quy tắc.

## 15. Hai quan hệ collection JOIN: nguy cơ tích Descartes

Một entity có nhiều collection, ví dụ:

```text
Customer
  orders        -> 3 đơn
  addresses     -> 2 địa chỉ
```

Một query:

```jpql
select count(o)
from Customer c
join c.orders o
join c.addresses a
where c.id = :customerId
```

có thể tạo **3 × 2 = 6 joined rows** cho customer đó. `COUNT(o)` có thể thành 6 dù chỉ có 3 orders.

Ngay cả khi hai collection có dữ liệu hợp lệ độc lập, join chúng ở cùng mức có thể nhân bản các tổ hợp. `COUNT(DISTINCT o)` có thể giúp mục tiêu đếm order, nhưng **SUM(amount)** vẫn cần tránh nhân bản theo quan hệ khác.

Hướng xử lý:

1. Xác định **grain** của chỉ số: một order, một order line, một customer hay một payment?
2. Bắt đầu aggregate từ đúng entity grain.
3. Dùng `EXISTS` nếu chỉ cần kiểm tra một quan hệ thỏa điều kiện.
4. Tách những aggregate có grain khác nhau thành query riêng khi cần.
5. Nếu cần analytic nhiều nguồn lớn, cân nhắc SQL native với CTE/subquery được DB hỗ trợ, materialized view hoặc read model được thiết kế riêng.
6. So sánh kết quả với fixture có nhiều collection elements để không bỏ sót lỗi nhân số.

**Grain** là khái niệm quan trọng nhất để aggregate đúng: một row logic trong tập nguồn đại diện **cho điều gì**?

## 16. Correlated subquery: dùng aggregate để lọc entity

Aggregate không nhất thiết chỉ xuất hiện ở SELECT. Có thể dùng nó trong truy vấn con để lọc entity ở query ngoài.

### 16.1. Khách hàng có ít nhất hai đơn

```jpql
select c
from Customer c
where (
    select count(o)
    from SalesOrder o
    where o.customer = c
) >= :minimumOrders
```

Đây là **correlated subquery** vì `o.customer = c` tham chiếu biến `c` từ query ngoài.

Java:

```java
List<Customer> customers = em.createQuery(
    """
    select c from Customer c
    where (
        select count(o)
        from SalesOrder o
        where o.customer = c
    ) >= :minimumOrders
    """,
    Customer.class
)
.setParameter("minimumOrders", 2L)
.getResultList();
```

Với dữ liệu mẫu, khách hàng An thỏa.

### 16.2. Đơn có giá trị bằng MAX của khách đó

```jpql
select o
from SalesOrder o
where o.totalAmount = (
    select max(o2.totalAmount)
    from SalesOrder o2
    where o2.customer = o.customer
)
```

Truy vấn trả **những đơn có giá trị lớn nhất của từng Customer** trong nhóm các Customer đã có order.

Với An, max là 200.00; với Bình, max cũng là 200.00. Nếu một Customer có nhiều đơn bằng cùng max, câu này có thể trả nhiều đơn cho Customer đó.

### 16.3. Khách không có đơn

```jpql
select c
from Customer c
where (
    select count(o)
    from SalesOrder o
    where o.customer = c
) = 0
```

Có thể thay bằng cách trực quan hơn:

```jpql
select c
from Customer c
where c.orders is empty
```

Hai cách tương tự về ý định trong mô hình này, nhưng SQL và query plan có thể khác. Không nhất thiết phải dùng COUNT khi `NOT EXISTS` hoặc `IS EMPTY` diễn đạt rõ hơn.

### 16.4. Một cảnh báo về tính năng JPQL portable

Subquery trong `WHERE` và `HAVING` là cách phổ biến trong JPQL chuẩn. Khả năng dùng subquery ở **FROM** hoặc các biểu thức analytic phức tạp phụ thuộc phiên bản đặc tả/provider; không sao chép mọi mẫu SQL CTE/derived table vào JPQL mà không kiểm tra khả năng hỗ trợ.

## 17. DTO projection: một truy vấn trả nhiều aggregate có kiểu rõ ràng

Giả sử dashboard cần:

- Customer ID và tên.
- Tổng số đơn.
- Tổng giá trị đơn.
- Giá trị đơn trung bình.
- Đơn nhỏ nhất và lớn nhất.

Định nghĩa DTO record:

```java
package com.example.shop.readmodel;

import java.math.BigDecimal;

public record CustomerOrderStats(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal totalAmount,
    Double averageAmount,
    BigDecimal minAmount,
    BigDecimal maxAmount
) { }
```

JPQL constructor expression:

```jpql
select new com.example.shop.readmodel.CustomerOrderStats(
    c.id,
    c.customerName,
    count(o),
    sum(o.totalAmount),
    avg(o.totalAmount),
    min(o.totalAmount),
    max(o.totalAmount)
)
from Customer c
left join c.orders o
group by c.id, c.customerName
order by c.id
```

Java:

```java
List<CustomerOrderStats> stats = em.createQuery(
    """
    select new com.example.shop.readmodel.CustomerOrderStats(
        c.id,
        c.customerName,
        count(o),
        sum(o.totalAmount),
        avg(o.totalAmount),
        min(o.totalAmount),
        max(o.totalAmount)
    )
    from Customer c
    left join c.orders o
    group by c.id, c.customerName
    order by c.id
    """,
    CustomerOrderStats.class
).getResultList();
```

Với dữ liệu mẫu, kết quả logic:

| Customer | count | sum | avg | min | max |
|---|---:|---:|---:|---:|---:|
| An | 3 | 450.00 | 150.0 | 100.00 | 200.00 |
| Bình | 1 | 200.00 | 200.0 | 200.00 | 200.00 |
| Chi | 0 | NULL | NULL | NULL | NULL |

**Lưu ý:** Các fields `BigDecimal` và `Double` trong record là kiểu reference có thể nhận null. Nếu DTO khai báo primitive `double` cho `averageAmount`, nhóm Chi có thể làm constructor instantiation thất bại vì null không tự chuyển thành primitive an toàn.

### 17.1. Không tự đưa entity vào DTO nếu không cần

`CustomerOrderStats` là **DTO**, không phải managed entity. Thay đổi giá trị DTO không làm database UPDATE. Với API read-only, DTO thường tốt hơn việc tải Customer và toàn bộ orders rồi tính trong Java.

### 17.2. Có nên dùng COALESCE ngay trong constructor?

Có thể thiết kế một biến thể:

```jpql
select new com.example.shop.readmodel.CustomerOrderStats(
    c.id,
    c.customerName,
    count(o),
    coalesce(sum(o.totalAmount), :zero),
    avg(o.totalAmount),
    min(o.totalAmount),
    max(o.totalAmount)
)
from Customer c
left join c.orders o
group by c.id, c.customerName
```

Bind `zero` là `BigDecimal.ZERO`; lúc đó sum của Chi được hiển thị 0. Tuy nhiên average/min/max của Chi vẫn null theo ngữ nghĩa.

Khi hợp đồng API muốn quy đổi NULL thành 0, cân nhắc thực hiện rõ trong DTO/service để tách **dữ liệu thống kê** khỏi **cách biểu diễn UI**.

## 18. Tuple và Object[]: các cách nhận nhiều aggregate

Nếu không muốn tạo DTO ngay, có thể dùng `Object[]`:

```java
Object[] row = em.createQuery(
    """
    select count(o), sum(o.totalAmount), avg(o.totalAmount)
    from SalesOrder o
    """,
    Object[].class
).getSingleResult();

Long count = (Long) row[0];
BigDecimal sum = (BigDecimal) row[1];
Double average = (Double) row[2];
```

Nhược điểm là thứ tự cột dễ thay đổi và cast bị sai khi chỉnh query.

Với `Tuple`:

```java
import jakarta.persistence.Tuple;

Tuple row = em.createQuery(
    """
    select count(o) as orderCount,
           sum(o.totalAmount) as totalAmount,
           avg(o.totalAmount) as averageAmount
    from SalesOrder o
    """,
    Tuple.class
).getSingleResult();

Long count = row.get("orderCount", Long.class);
BigDecimal sum = row.get("totalAmount", BigDecimal.class);
Double avg = row.get("averageAmount", Double.class);
```

`Tuple` giúp truy cập kết quả theo alias và kiểu, nhưng DTO có contract ổn định thường dễ bảo trì hơn khi dữ liệu đi qua nhiều tầng application.

### 18.1. TypedQuery với chỉ một aggregate

```java
TypedQuery<Long> query = em.createQuery(
    "select count(o) from SalesOrder o",
    Long.class
);
```

Kết quả không thể khai báo `TypedQuery<SalesOrder>` vì `select count(o)` trả `Long`, không trả entity. Đây là lỗi thường gặp khi copy từ query `select o` sang aggregate nhưng không đổi kiểu kết quả.

## 19. Phân trang kết quả tổng hợp

Một dashboard có hàng chục nghìn khách hàng cần hiển thị top 20 khách theo tổng tiền đơn đã thanh toán.

```jpql
select c.id, c.customerName, sum(o.totalAmount)
from SalesOrder o
join o.customer c
where o.status = :paidStatus
group by c.id, c.customerName
order by sum(o.totalAmount) desc, c.id asc
```

Java:

```java
List<Object[]> topCustomers = em.createQuery(
    """
    select c.id, c.customerName, sum(o.totalAmount)
    from SalesOrder o
    join o.customer c
    where o.status = :paidStatus
    group by c.id, c.customerName
    order by sum(o.totalAmount) desc, c.id asc
    """,
    Object[].class
)
.setParameter("paidStatus", OrderStatus.PAID)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

**`setFirstResult`/`setMaxResults` áp dụng cho số result rows ở cấp query**, ở đây là **các nhóm Customer**, không phải trực tiếp số row SalesOrder.

### 19.1. Sắp xếp ổn định

Nếu hai Customer có tổng tiền bằng nhau, chỉ `order by sum(o.totalAmount) desc` không bảo đảm thứ tự giữa hai nhóm đó. Thêm `c.id asc` để tạo tie-breaker ổn định hơn.

### 19.2. Pagination không đồng nghĩa một truy vấn rẻ

Ngay cả khi chỉ lấy 20 nhóm, database có thể phải đọc và tổng hợp một lượng lớn SalesOrder trước khi sắp xếp/top-N. `LIMIT`/`OFFSET` do provider sinh không làm `GROUP BY` trở nên miễn phí.

Nên xem index, phân vùng dữ liệu, pre-aggregation hoặc materialized view khi báo cáo có lượng dữ liệu lớn và tần suất đọc cao.

### 19.3. COUNT tổng số nhóm để phân trang

Để hiển thị “tổng 500 khách hàng thỏa báo cáo”, không dùng trực tiếp:

```jpql
select count(o) from SalesOrder o
```

vì đó là tổng **đơn**, không phải tổng **khách**.

Trong nhiều trường hợp có thể dùng:

```jpql
select count(distinct o.customer.id)
from SalesOrder o
where o.status = :paidStatus
```

để đếm số Customer có ít nhất một đơn PAID. Tuy nhiên, nếu danh sách nhóm có điều kiện `HAVING sum(...) >= :minRevenue`, việc đếm số nhóm thỏa HAVING không phải lúc nào cũng diễn đạt gọn bằng COUNT DISTINCT thông thường; có thể cần query khác/native SQL, hoặc đọc aggregate group keys theo phương án phù hợp.

Đừng nhầm “số dòng gốc” với “số nhóm hiển thị”.

## 20. Hiệu năng aggregate: chỉ số, lọc và truy vấn thực tế

Dùng aggregate làm giảm nhu cầu tải entity nhưng không loại bỏ công việc database. Một query `SUM` hoặc `COUNT DISTINCT` có thể phải quét rất nhiều row.

### 20.1. Lọc trước khi nhóm khi đúng mục tiêu

```jpql
select o.status, count(o), sum(o.totalAmount)
from SalesOrder o
where o.placedAt >= :start
  and o.placedAt < :end
group by o.status
```

Nếu báo cáo chỉ cần dữ liệu của một tháng, `WHERE` giới hạn tập nguồn trước khi GROUP BY. Khi có index/phân vùng thời gian phù hợp, database có thể giảm lượng dữ liệu phải đọc.

### 20.2. Index phù hợp truy vấn

Một số index có thể cân nhắc tùy workload:

```sql
CREATE INDEX ix_sales_order_status_placed
ON sales_order(order_status, placed_at);

CREATE INDEX ix_sales_order_customer
ON sales_order(customer_id);

CREATE INDEX ix_order_line_order_sku
ON sales_order_line(order_id, product_sku);
```

Đây là **gợi ý định hướng**, không phải bộ index nên tạo nguyên xi. Index có chi phí disk, bộ nhớ và UPDATE/INSERT; thứ tự cột cần được đánh giá bằng execution plan trên DB thật.

### 20.3. DISTINCT có chi phí

`COUNT(DISTINCT o)` và `SUM(DISTINCT field)` thường yêu cầu xử lý khử trùng bằng hash/sort hoặc chiến lược DB. Nếu có thể tránh JOIN làm nhân bản ngay từ đầu, đôi khi nhanh và rõ ý nghĩa hơn so với JOIN nhiều row rồi DISTINCT.

### 20.4. COUNT có thể không phải O(1)

`COUNT(o)` không có nghĩa database luôn trả kết quả ngay mà không quét dữ liệu. Trên các hệ quản trị dùng MVCC, số row nhìn thấy phụ thuộc snapshot/transaction nên COUNT thường cần kiểm tra rows hoặc index phù hợp.

Tính nhanh hay chậm phải dựa trên thống kê, SQL do provider sinh, index, bộ lọc và isolation.

### 20.5. Đọc số liệu tổng hợp lặp lại nhiều lần

Dashboard refresh mỗi giây trên hàng triệu orders có thể cần:

- Bảng tổng hợp theo ngày/tháng/khách hàng.
- Materialized view hoặc read model.
- Incremental aggregation theo event.
- Cache với TTL và chiến lược invalidation.
- Background job tạo báo cáo.

Đổi từ JPQL sang native SQL không tự bảo đảm giải quyết hoàn toàn chi phí; cần thiết kế hệ thống đọc theo khối lượng dữ liệu và yêu cầu độ tươi.

## 21. Tính chính xác của số liệu: currency, rounding và trạng thái nghiệp vụ

### 21.1. Không cộng trực tiếp nhiều loại tiền khác nhau

Giả sử `SalesOrder` có `currency`, một đơn USD và một đơn VND. `SUM(totalAmount)` cho tất cả currency sẽ trả một con số toán học, nhưng nó **không mang ý nghĩa doanh thu hợp lệ**.

Nên:

- `GROUP BY o.currency` để báo tổng theo từng loại tiền.
- Hoặc quy đổi theo tỷ giá có timestamp/version phù hợp và lưu số liệu dùng để báo cáo.
- Định nghĩa rõ cách làm tròn, loại phí, điều chỉnh và hoàn tiền.

Ví dụ nếu entity có persistent attribute `currency`:

```jpql
select o.currency, sum(o.totalAmount)
from SalesOrder o
where o.status = :paidStatus
group by o.currency
```

Ví dụ giả định entity được bổ sung `currency`; không thể dùng `o.currency` với entity mẫu ban đầu nếu chưa có attribute này.

### 21.2. Đừng coi OrderStatus.PAID là revenue đã chốt

Đơn PAID có thể vẫn được hoàn tiền hoặc hủy sau đó. Nếu hệ thống có các bảng payment/refund riêng, “doanh thu thuần” có thể phải lấy từ ledger/settlement, không chỉ SUM totalAmount theo status.

Aggregate function thực hiện phép tính trên model đã đưa vào. **Định nghĩa số liệu** phải được xây dựng bởi domain, không do tên hàm quyết định.

### 21.3. BigDecimal và rounding

Đối với tiền, `BigDecimal` giúp tránh một số lỗi biểu diễn của `double` ở tầng Java. Tuy nhiên:

- Cột DB phải có precision/scale phù hợp.
- SUM có thể vượt giới hạn precision nếu dữ liệu rất lớn.
- AVG trả `Double` theo JPQL; nếu cần average money chính xác, có thể dùng SUM/COUNT và `BigDecimal.divide`.
- Phải chọn rounding mode được quy định nghiệp vụ, không chỉ `setScale(2)` theo thói quen.

### 21.4. Thời gian và múi giờ

Nếu thống kê doanh thu theo “ngày”, phải xác định ngày theo timezone nào. `Instant` UTC và giờ địa phương có thể khiến một đơn gần nửa đêm thuộc hai ngày khác nhau.

Bài toán “tổng theo ngày tại Asia/Ho_Chi_Minh” cần chuyển timezone và tạo khoảng `[start, end)` đúng cách, hoặc dùng cột ngày nghiệp vụ được chuẩn hóa. Không chỉ lấy ngày từ DB bằng hàm vendor-specific mà bỏ qua timezone.

## 22. Concurrency: kết quả aggregate phản ánh thời điểm đọc

Một câu `COUNT`/`SUM` trả kết quả phù hợp với trạng thái dữ liệu mà transaction/query nhìn thấy theo isolation và database.

Giả sử:

1. Request A query `COUNT(o)` được 100.
2. Request B tạo thêm order và commit.
3. Request A query lại `COUNT(o)` có thể thấy 101 hoặc 100 tùy isolation/snapshot.

Aggregate không tự khóa các row và ngăn dữ liệu thay đổi. Do đó:

- Không dùng `COUNT` rồi `persist` để bảo đảm “tối đa 10 đơn” nếu không có concurrency control.
- Không dùng `SUM(stock)` ngoài transaction như bảo đảm cuối cùng cho phép trừ tồn kho.
- Cần transaction isolation/locking/conditional update/constraint phù hợp với invariant.
- Với báo cáo, có thể chấp nhận eventual consistency và ghi rõ thời điểm snapshot.
- Với thống kê cần nhất quán giữa nhiều query, xem isolation và đơn vị transaction của các query đó.

**Ví dụ race condition:**

```text
Transaction A                 Transaction B
--------------------------    --------------------------
COUNT(order of customer)=9    COUNT(order of customer)=9
Tạo order thứ 10              Tạo order thứ 10
COMMIT                        COMMIT
```

Cả hai đều vượt qua kiểm tra trước đó. Nếu nghiệp vụ chỉ cho tối đa 10 đơn thì cần cơ chế bảo vệ khác; `COUNT` đơn lẻ không đủ.

## 23. Query aggregate và persistence context: một lưu ý về flush

Một entity managed bị sửa trong transaction:

```java
SalesOrder order = em.find(SalesOrder.class, orderId);
order.changeTotalAmount(new BigDecimal("500.00"));

BigDecimal sum = em.createQuery(
    "select sum(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();
```

Ví dụ giả định `SalesOrder` có domain method `changeTotalAmount` hợp lệ. Với flush mode `AUTO`, provider phải bảo đảm kết quả query phù hợp với quy tắc nhìn thấy thay đổi pending; provider có thể flush trước aggregate query hoặc dùng một cách khác.

Với `FlushModeType.COMMIT`, tác động của các thay đổi chưa flush lên query trước commit không được quy định hoàn toàn portable.

### 23.1. Không dựa vào aggregate như nguồn độc lập khỏi managed changes

```java
em.setFlushMode(FlushModeType.AUTO);
```

Trong transaction ghi, một aggregate query có thể làm provider tự flush các cập nhật khác trong persistence context và từ đó phát sinh constraint violation **ở câu query**, không phải tại `commit()`.

Đừng kết luận rằng query `SUM` chắc chắn “chỉ đọc” và không bao giờ gây SQL UPDATE nếu context đang có dirty entities cần đồng bộ theo flush mode.

### 23.2. Aggregate không trả managed entity

```java
Long count = em.createQuery(
    "select count(o) from SalesOrder o",
    Long.class
).getSingleResult();
```

`Long` là scalar; nó không được JPA dirty-check. Khác query `select o` trả `SalesOrder` managed instances.

### 23.3. Bulk UPDATE có thể làm số liệu và managed state lệch nhau

Nếu chạy bulk JPQL update, các entity đã loaded trong persistence context có thể giữ state cũ. Một aggregate query mới có thể đọc database state sau bulk, trong khi một Java entity đã managed còn field cũ. Cần xem `flush`/`clear`/`refresh` và transaction boundary đúng mục đích.

Không tự suy ra chỉ vì cùng EntityManager thì mọi thứ đã đồng bộ tuyệt đối sau bulk DML.

## 24. Multi-tenancy và authorization khi tổng hợp

Một thống kê “tổng doanh thu của shop” không chỉ là câu `SUM`. Trong ứng dụng nhiều tenant, phải giới hạn đúng tenant/merchant theo security context.

Giả sử `SalesOrder` có persistent attribute `tenantId`:

```jpql
select sum(o.totalAmount)
from SalesOrder o
where o.tenantId = :authorizedTenantId
  and o.status = :paidStatus
```

Không bind `authorizedTenantId` từ một tham số request chưa được xác thực hoặc để thiếu filter khi query aggregate. Kết quả tổng hợp vẫn có thể làm **lộ thông tin nhạy cảm giữa tenant**, dù không trả ra danh sách entity cụ thể.

Với hệ thống dùng provider-level filters, row-level security hoặc multi-tenant schema, cần xác định chính xác cơ chế nào được áp dụng với **mọi query**, kể cả native SQL, bulk DML và aggregate.

Đừng coi “chỉ trả một con số” là không có rủi ro truy cập dữ liệu.

## 25. JPQL aggregate so với native SQL

JPQL:

```jpql
select c.id, count(o), sum(o.totalAmount)
from Customer c
left join c.orders o
group by c.id
```

SQL tương đương khái niệm:

```sql
SELECT
    c.id,
    COUNT(o.id),
    SUM(o.total_amount)
FROM crm_customer c
LEFT JOIN sales_order o
    ON o.customer_id = c.id
GROUP BY c.id;
```

JPQL dùng **entity names, Java attributes và associations**; provider sinh SQL theo mapping/dialect. Không trộn table `sales_order` vào `FROM` của `EntityManager.createQuery`.

### 25.1. Khi nào native SQL có lợi?

- Báo cáo sử dụng window functions nâng cao.
- Derived tables/CTE hoặc recursive SQL cần cú pháp đặc thù.
- GROUPING SETS, ROLLUP, CUBE theo hệ quản trị.
- SUM trên biểu thức phức tạp hoặc các phép chuyển đổi database-specific.
- Pre-aggregation qua materialized view.
- Cần query plan/hint/index đặc thù.
- Phân tích đa bảng không được ánh xạ hoặc khó diễn đạt portable trong JPQL version đang dùng.

Khi đó có thể dùng `createNativeQuery` hoặc JDBC/read-only reporting layer, nhưng phải chấp nhận phụ thuộc tên bảng/cột và kiểu trả về driver.

### 25.2. Không giả định native SQL trả đúng kiểu JPQL

Trong native query, `COUNT(*)` có thể được driver/provider trả dưới một kiểu `Number` khác tùy database. Không copy nguyên kiểu `TypedQuery<Long>` của JPQL sang mọi native query mà không kiểm tra mapping kết quả.

Với JPQL chuẩn, dùng bảng kiểu aggregate ở phần 7. Với native SQL, dựa trên mapping/dialect/`SqlResultSetMapping`/kiểu JDBC thực tế.

## 26. Kiểm thử kết quả aggregate trên dữ liệu mẫu

Một integration test có giá trị nên tạo dữ liệu có:

- Ít nhất một nhóm có nhiều records.
- Ít nhất một nhóm không có child records.
- Ít nhất một trường nullable có cả NULL, 0 và giá trị khác 0.
- Ít nhất hai entity có giá trị amount bằng nhau.
- Ít nhất một association một-nhiều có nhiều children.
- Nhiều trạng thái đơn hàng.
- Những mốc thời gian sát ranh giới kỳ báo cáo.

### 26.1. Test COUNT

```java
Long count = em.createQuery(
    "select count(o) from SalesOrder o",
    Long.class
).getSingleResult();

assertEquals(4L, count);
```

Kỳ vọng 4 trên fixture chỉ có bốn orders. Nếu test tạo dữ liệu trong cùng transaction, cần hiểu flush mode và bảo đảm setup được đồng bộ phù hợp trước query.

### 26.2. Test COUNT(field nullable)

```java
Long withDiscountValue = em.createQuery(
    """
    select count(o.discountAmount)
    from SalesOrder o
    """,
    Long.class
).getSingleResult();

assertEquals(3L, withDiscountValue);
```

Với fixture có NULL, 0, 10, 20, kỳ vọng 3.

### 26.3. Test SUM và AVG

```java
BigDecimal total = em.createQuery(
    "select sum(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();

Double average = em.createQuery(
    "select avg(o.totalAmount) from SalesOrder o",
    Double.class
).getSingleResult();

assertEquals(0, total.compareTo(new BigDecimal("650.00")));
assertEquals(162.5, average, 0.000001);
```

Với BigDecimal, `compareTo` thường phù hợp khi test **giá trị số** bất kể scale; `equals` còn so sánh scale (ví dụ `650.0` và `650.00` không equals).

Với Double, dùng tolerance thích hợp thay vì so sánh floating point không có sai số.

### 26.4. Test MIN/MAX và giá trị NULL

```java
BigDecimal min = em.createQuery(
    "select min(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();

BigDecimal max = em.createQuery(
    "select max(o.totalAmount) from SalesOrder o",
    BigDecimal.class
).getSingleResult();
```

Kỳ vọng min = 100.00; max = 200.00.

Thêm test với `where o.status = :cancelled` không có row, xác nhận:

```text
COUNT = 0
SUM / AVG / MIN / MAX = null
```

### 26.5. Test LEFT JOIN và khách hàng không có order

```jpql
select c.id, count(o), sum(o.totalAmount)
from Customer c
left join c.orders o
group by c.id
```

Với Chi, assert count = 0 và sum = null. Đừng chỉ test An/Bình vì lỗi bỏ mất group rỗng có thể không lộ.

### 26.6. Test JOIN nhân bản

Chạy:

```jpql
select count(o)
from SalesOrder o
join o.lines i
```

Với tám OrderLine, truy vấn có thể trả 8. So sánh với:

```jpql
select count(distinct o)
from SalesOrder o
join o.lines i
```

kỳ vọng 4. Bài test này rất hữu ích để nhắc rằng `COUNT` là đếm **kết quả sau JOIN**, không tự hiểu “đếm order entity duy nhất”.

### 26.7. Test với database thật hay H2?

H2 và các database in-memory hữu ích cho test nhanh, nhưng kiểu số, precision, collation, timezone và execution plan có thể khác PostgreSQL/MySQL/Oracle. Với logic doanh thu quan trọng, nên có một lớp integration tests chạy cùng hệ quản trị/dialect như production (ví dụ qua Testcontainers) để kiểm tra mapping và SQL thực tế.

## 27. Các lỗi tư duy phổ biến

### 27.1. “COUNT trả Integer vì bảng ít dữ liệu”

**Sai.** JPQL `COUNT` trả `Long`. Không thiết kế result type dựa trên ước lượng số row.

### 27.2. “SUM luôn trả Double”

**Sai.** Với `BigDecimal`, SUM trả `BigDecimal`; với kiểu integral thông thường là `Long`. Xem bảng mapping kiểu.

### 27.3. “AVG(BigDecimal) trả BigDecimal”

**Sai theo kiểu JPQL chuẩn.** `AVG` trả `Double`. Nếu tiền trung bình cần chính xác theo decimal, tính SUM/COUNT và chia BigDecimal theo quy tắc rounding.

### 27.4. “COUNT(nullableField) bằng COUNT(entity)”

**Sai.** COUNT(field) bỏ qua NULL; COUNT(entity) đếm sự xuất hiện của entity.

### 27.5. “0 và NULL giống nhau trong aggregate”

**Sai.** Giá trị 0 vẫn được COUNT/AVG/SUM xử lý; NULL được bỏ qua bởi các aggregate thông thường.

### 27.6. “SUM không có row trả 0”

**Sai.** Global SUM trên tập rỗng trả `null`; COUNT trả 0.

### 27.7. “GROUP BY không có nhóm vẫn tạo hàng 0”

**Sai.** Query GROUP BY chỉ trả các nhóm thực sự tồn tại; không có nhóm thì getResultList rỗng.

### 27.8. “GROUP BY status có thể SELECT orderNumber tùy ý”

**Không portable/sai ngữ nghĩa.** Non-aggregate expressions cần tương thích với GROUP BY; muốn một order cụ thể thì dùng query/subquery khác.

### 27.9. “WHERE count(o) > 2 là đúng”

**Sai.** Dùng `HAVING count(o) > 2` sau GROUP BY hoặc aggregate subquery ở WHERE.

### 27.10. “LEFT JOIN luôn giữ parent nếu WHERE lọc child”

**Sai.** Predicate ở WHERE có thể loại joined NULL rows; nếu muốn giữ parent, cân nhắc điều kiện ở ON hoặc thiết kế subquery.

### 27.11. “COUNT(c) sau LEFT JOIN là số khách hàng”

**Không phải nếu c bị lặp vì join children.** Dùng COUNT child để đếm children, COUNT DISTINCT c nếu cần distinct parents, và hiểu join cardinality.

### 27.12. “SUM(orderAmount) sau JOIN lines vẫn là tổng tiền đơn”

**Sai.** Order có thể bị nhân số lần theo số lines, khiến tổng bị phóng đại.

### 27.13. “SUM(DISTINCT amount) khử trùng theo order ID”

**Sai.** DISTINCT áp dụng cho **giá trị amount**, có thể bỏ sót nhiều order hợp lệ cùng amount.

### 27.14. “MIN/MAX trả entity có giá trị nhỏ nhất/lớn nhất”

**Sai.** Chúng trả **giá trị aggregate**, muốn entity thì dùng subquery hoặc ORDER BY + pagination.

### 27.15. “MAX(amount) có nghĩa một order duy nhất”

**Sai.** Nhiều order có thể cùng giá trị max; query tìm entity đạt max có thể trả nhiều row.

### 27.16. “Cứ INNER JOIN từ SalesOrder là có mọi Customer”

**Sai.** Customer không có order sẽ không được liệt kê. Muốn mọi Customer, bắt đầu từ Customer và dùng LEFT JOIN phù hợp.

### 27.17. “COUNT DISTINCT luôn nhanh và không cần xem SQL plan”

**Sai.** DISTINCT có thể tốn hash/sort và không khắc phục mọi sai lệch grain.

### 27.18. “Aggregate JPQL không bao giờ flush dữ liệu pending”

**Sai.** Với FlushMode.AUTO, provider có thể tự flush để bảo đảm query nhìn thấy thay đổi phù hợp.

### 27.19. “Một aggregate query luôn trả managed entity”

**Sai.** Các scalar Long/BigDecimal/Double/DTO không được JPA quản lý như entity instances.

### 27.20. “SUM là doanh thu theo nghiệp vụ mặc định”

**Sai.** Phải xác định trạng thái PAID/REFUNDED, currency, thuế, chiết khấu, period và dữ liệu nguồn hợp lệ.

### 27.21. “Một COUNT trước INSERT bảo đảm quota không bị vượt”

**Sai.** Hai transaction có thể cùng đọc COUNT cũ rồi insert. Cần concurrency control thực sự.

### 27.22. “JPQL dùng trực tiếp table/column SQL”

**Sai.** `FROM SalesOrder o` và `o.totalAmount` là entity/attribute; `sales_order` và `total_amount` là tên SQL.

### 27.23. “Một GROUP BY query có thể phân trang mà không sắp xếp”

**Không nên.** Muốn phân trang ổn định, dùng ORDER BY có tie-breaker phù hợp.

### 27.24. “Không cần kiểm tra nhóm có 0 children”

**Sai.** Đây là nơi dễ sai nhất của LEFT JOIN, COUNT và SUM NULL; cần fixture nhóm rỗng.

## 28. Bài tập vận dụng có gợi ý

### Bài 1: Đếm tổng số đơn hàng

**Yêu cầu:** Đếm tất cả SalesOrder.

```jpql
select count(o) from SalesOrder o
```

**Gợi ý:** Kết quả nên nhận bằng `Long.class`, không phải `SalesOrder.class`.

### Bài 2: Đếm đơn đã thanh toán

**Yêu cầu:** Đếm đơn PAID.

```jpql
select count(o)
from SalesOrder o
where o.status = :status
```

**Gợi ý:** Bind `OrderStatus.PAID`, không nối chuỗi trực tiếp vào JPQL.

### Bài 3: Giá trị đơn trung bình

**Yêu cầu:** Tính AVG totalAmount.

```jpql
select avg(o.totalAmount)
from SalesOrder o
```

**Gợi ý:** Kiểu Java `Double`. Nếu không có đơn, AVG trả null.

### Bài 4: Tổng tiền theo trạng thái

**Yêu cầu:** Mỗi trạng thái có số đơn và tổng tiền.

```jpql
select o.status, count(o), sum(o.totalAmount)
from SalesOrder o
group by o.status
```

**Gợi ý:** Không xuất hiện nhóm CANCELLED nếu chưa có đơn CANCELLED.

### Bài 5: Khách hàng chưa có đơn

**Yêu cầu:** Trả mỗi Customer và số đơn, kể cả Chi.

```jpql
select c.id, c.customerName, count(o)
from Customer c
left join c.orders o
group by c.id, c.customerName
```

**Gợi ý:** Chi có COUNT(o) = 0.

### Bài 6: COUNT nullable field

Các discountAmount là 10, NULL, 0 và 20.

**Câu hỏi:** `COUNT(o.discountAmount)` bằng bao nhiêu?

**Gợi ý:** 3, vì giá trị 0 được đếm còn NULL bị bỏ qua.

### Bài 7: AVG nullable field

Cũng với dữ liệu bài 6, `AVG(discountAmount)` bằng bao nhiêu?

**Gợi ý:** (10 + 0 + 20) / 3 = 10.0; kiểu kết quả là Double.

### Bài 8: SUM theo khách hàng

**Yêu cầu:** Tổng giá trị đơn của từng Customer, kể cả người chưa có đơn.

```jpql
select c.id, c.customerName, sum(o.totalAmount)
from Customer c
left join c.orders o
group by c.id, c.customerName
```

**Gợi ý:** Với Chi, SUM trả null. Nếu cần hiển thị 0, dùng COALESCE hoặc DTO mapper.

### Bài 9: Ít nhất hai đơn PAID

**Yêu cầu:** Chỉ các Customer có >= 2 đơn PAID.

```jpql
select c.id, count(o)
from Customer c
join c.orders o
where o.status = :paid
group by c.id
having count(o) >= 2
```

**Gợi ý:** WHERE lọc PAID trước GROUP BY; HAVING chọn các nhóm thỏa số lượng.

### Bài 10: COUNT sau JOIN

Có 4 orders với lần lượt 2, 1, 2 và 3 lines.

**Câu hỏi:** `COUNT(o)` trong `from SalesOrder o join o.lines i` bằng bao nhiêu?

**Gợi ý:** 8 lần xuất hiện của o trong joined rows, không phải 4 orders.

### Bài 11: Sửa COUNT do JOIN

**Yêu cầu:** Đếm các order khác nhau có ít nhất một line.

```jpql
select count(distinct o)
from SalesOrder o
join o.lines i
```

**Gợi ý:** Kết quả 4 theo fixture nếu tất cả 4 đơn đều có line.

### Bài 12: Vì sao SUM DISTINCT không đúng?

Orders có totalAmount: 100, 200, 150, 200.

**Câu hỏi:** `SUM(DISTINCT totalAmount)` bằng bao nhiêu và vì sao không phải doanh thu?

**Gợi ý:** 450; hai order amount 200 hợp lệ nhưng bị distinct gộp theo giá trị.

### Bài 13: Dùng EXISTS để tránh nhân bản SUM

**Yêu cầu:** Tổng tiền của các order có ít nhất một line SKU `BOOK-01`.

```jpql
select sum(o.totalAmount)
from SalesOrder o
where exists (
    select i.id from OrderLine i
    where i.order = o
      and i.productSku = :sku
)
```

**Gợi ý:** Mỗi order thỏa điều kiện đóng góp totalAmount một lần.

### Bài 14: MIN/MAX theo thời gian

**Yêu cầu:** Lấy thời điểm đặt đơn sớm nhất và gần nhất.

```jpql
select min(o.placedAt), max(o.placedAt)
from SalesOrder o
```

**Gợi ý:** Kết quả là giá trị thời gian, không phải SalesOrder.

### Bài 15: Lấy Order có totalAmount lớn nhất

**Yêu cầu:** Trả mọi Order cùng đạt mức tiền cao nhất.

```jpql
select o
from SalesOrder o
where o.totalAmount = (
    select max(o2.totalAmount)
    from SalesOrder o2
)
```

**Gợi ý:** Có thể trả nhiều entity khi đồng hạng.

### Bài 16: Sắp xếp nhóm theo SUM

**Yêu cầu:** Top 10 Customer có tổng tiền PAID cao nhất.

```jpql
select c.id, sum(o.totalAmount)
from SalesOrder o join o.customer c
where o.status = :paid
group by c.id
order by sum(o.totalAmount) desc, c.id asc
```

**Gợi ý:** Gọi `setMaxResults(10)`, cẩn thận kiểu của tổng và index phù hợp.

### Bài 17: Query aggregate tập rỗng

Không có order CANCELLED.

**Câu hỏi:** Query không GROUP BY có `COUNT`, `SUM` và `AVG` trả gì?

**Gợi ý:** Một row với COUNT = 0, SUM = null, AVG = null.

### Bài 18: Query GROUP BY tập rỗng

Không có order CANCELLED.

```jpql
select o.status, count(o)
from SalesOrder o
where o.status = :cancelled
group by o.status
```

**Câu hỏi:** Có một row `(CANCELLED, 0)` không?

**Gợi ý:** Không. Không có nhóm, nên kết quả là danh sách rỗng.

### Bài 19: Tài chính và AVG

Cần giá trị tiền trung bình với rounding mode `HALF_UP` ở 2 chữ số sau dấu phẩy.

**Gợi ý:** Query `SUM(BigDecimal)` và `COUNT` rồi `BigDecimal.divide(count, 2, HALF_UP)`; đừng tự mặc định `AVG` đã cho BigDecimal chính xác theo rounding mode mong muốn.

### Bài 20: LEFT JOIN với điều kiện status

Cần đếm số đơn PAID của **mọi** Customer, kể cả Chi.

**Gợi ý:** Đặt status filter ở `ON` của `LEFT JOIN` thay vì `WHERE` để không loại Customer không có đơn PAID, trong những phiên bản JPQL/provider hỗ trợ join ON phù hợp.

### Bài 21: Lỗi TypedQuery

```java
TypedQuery<Integer> query = em.createQuery(
    "select count(o) from SalesOrder o",
    Integer.class
);
```

**Câu hỏi:** Vấn đề ở đâu?

**Gợi ý:** `COUNT` chuẩn trả `Long`. Dùng `TypedQuery<Long>` và `Long.class`.

### Bài 22: Bảo mật aggregate nhiều tenant

Một query thống kê SUM không có điều kiện tenant.

**Câu hỏi:** Vì sao vẫn nguy hiểm khi không trả entity cụ thể?

**Gợi ý:** Tổng doanh thu có thể lộ dữ liệu của tenant khác. Thêm filter/row-level security theo cơ chế đã được xác thực.

### Bài 23: Tính đúng theo kỳ báo cáo

Báo cáo có điều kiện `placedAt between :start and :end`.

**Câu hỏi:** Vì sao cần quan tâm timezone và ranh giới ngày?

**Gợi ý:** Với các kỳ liền nhau, dùng khoảng nửa mở `>= start` và `< end` theo timezone nghiệp vụ rõ ràng, tránh double-count đơn đúng mốc cuối ngày.

### Bài 24: Ràng buộc quota

Hai request đều `COUNT(order) = 9` rồi cùng tạo order thứ mười.

**Câu hỏi:** COUNT có giữ được quota tối đa 10 không?

**Gợi ý:** Không. Cần concurrency control/constraint trong transaction, không chỉ một aggregate query trước insert.

## 29. Quy trình chọn aggregate query đúng

Khi thiết kế một báo cáo dùng COUNT/SUM/AVG/MIN/MAX:

1. **Xác định chỉ số nghiệp vụ.** “Doanh thu” là tổng amount nào, trạng thái nào, currency nào?
2. **Xác định grain.** Một row logic là một Order, một OrderLine, một Payment hay một Customer?
3. **Chọn entity nguồn.** Dùng `FROM SalesOrder o` nếu tổng hợp theo order; không JOIN vô cớ.
4. **Xác định bộ lọc trước aggregate.** Dùng `WHERE` với status, tenant, khoảng thời gian và điều kiện cần thiết.
5. **Chọn hàm đúng.** COUNT để đếm; SUM để cộng; AVG trung bình; MIN/MAX cực trị.
6. **Chọn biểu thức.** COUNT(entity) khác COUNT(nullableField); DISTINCT áp dụng cho giá trị của biểu thức.
7. **Nếu cần nhóm,** thêm GROUP BY với các non-aggregate expressions thích hợp.
8. **Nếu cần lọc nhóm,** dùng HAVING thay vì dùng aggregate trực tiếp ở WHERE cùng cấp.
9. **Nếu cần giữ parent không có child,** dùng LEFT JOIN và chú ý COUNT(child), SUM null, điều kiện ON/WHERE.
10. **Kiểm tra JOIN cardinality.** Một-nhiều và nhiều-nhiều có thể nhân bản rows, làm COUNT/SUM sai.
11. **Chọn kiểu kết quả Java.** COUNT Long, SUM theo numeric input, AVG Double, MIN/MAX theo input.
12. **Định nghĩa NULL semantics.** 0 và không có dữ liệu có được xem như nhau trong API không?
13. **Chọn DTO và sorting/pagination.** Với grouped results, sắp xếp ổn định và không đếm nhầm row gốc thành số nhóm.
14. **Thiết kế concurrency/consistency.** Thống kê có chấp nhận snapshot tại thời điểm đọc không?
15. **Kiểm tra hiệu năng.** Quan sát SQL, execution plan, indexes, memory và lượng rows được quét.
16. **Kiểm thử với fixture khó.** Có nhóm rỗng, NULL, giá trị trùng nhau và entity có nhiều children.

Một sơ đồ lựa chọn:

```text
             Cần tính số liệu tổng hợp?
                       |
                       v
             Chỉ số ở grain nào?
             /         |         \
         Entity       Child       Payment/ledger
            |           |             |
            v           v             v
       FROM entity   FROM child   Nguồn nghiệp vụ
            |           |         phù hợp hơn
            +-----------+-------------+
                        |
                        v
             Cần lọc row trước?
                  /          \
                 Có          Không
                  |            |
                  v            |
                WHERE          |
                  +------------+
                        |
                        v
              Cần tổng hợp theo nhóm?
                  /           \
                Không         Có
                  |            |
                  v            v
          Global aggregate    GROUP BY
          COUNT/SUM/...       + COUNT/SUM/...
                  |            |
                  |            v
                  |          Lọc theo aggregate?
                  |            |
                  |          HAVING
                  |            |
                  +------------+
                        |
                        v
             JOIN có nhân bản grain?
                  /           \
                Có            Không
                 |              |
                 v              |
          Bỏ JOIN dư, EXISTS,   |
          tách query theo grain  |
                 |              |
                 +------+-------+
                        |
                        v
            Kiểm tra NULL + kiểu Java
                        |
                        v
           DTO / ORDER BY / pagination
                        |
                        v
               Test + đo SQL thật
```

## 30. Ghi nhớ cuối bài

| Hàm | Ý nghĩa | Kết quả chuẩn cần nhớ | Bẫy chính |
|---|---|---|---|
| `COUNT` | Đếm entity/biểu thức phù hợp | `Long`, bằng 0 nếu không có giá trị | COUNT(field) bỏ NULL; JOIN nhân bản |
| `SUM` | Cộng giá trị số | Phụ thuộc kiểu số, ví dụ BigDecimal hoặc Long | Tập rỗng trả NULL; JOIN làm cộng trùng |
| `AVG` | Trung bình cộng giá trị số | `Double` | Bỏ NULL; không mặc định chính xác như BigDecimal |
| `MIN` | Giá trị nhỏ nhất | Kiểu của thuộc tính phù hợp | Không trả entity; tập rỗng NULL |
| `MAX` | Giá trị lớn nhất | Kiểu của thuộc tính phù hợp | Có thể nhiều entity đồng hạng max |

Những quy tắc quan trọng nhất:

- **JPQL tổng hợp trên persistent attributes**, không trực tiếp trên tên cột SQL.
- **`GROUP BY` chia dữ liệu thành nhóm; `HAVING` lọc nhóm**, còn `WHERE` lọc dữ liệu trước tổng hợp.
- **`LEFT JOIN` giúp giữ parent không có child**; dùng `COUNT(child)` để nhận 0, nhưng `SUM(child.amount)` thường là null.
- **Các aggregate thông thường bỏ qua NULL**; COUNT trên tập rỗng là 0, SUM/AVG/MIN/MAX trên tập rỗng là null.
- **`AVG` trả Double** trong JPQL; nếu dùng tiền và cần rounding decimal, nên hiểu sự khác biệt với BigDecimal.
- **JOIN một-nhiều có thể làm COUNT hoặc SUM bị nhân bản**. Hãy xác định grain và đừng chữa SUM sai bằng `SUM(DISTINCT amount)`.
- **COUNT(DISTINCT entity) khác COUNT(DISTINCT value)**; DISTINCT hoạt động trên biểu thức mà bạn chọn.
- **Một query aggregate toàn cục có thể trả một row dù không có dữ liệu**, nhưng query có GROUP BY không tạo nhóm rỗng tự động.
- **MIN/MAX trả giá trị cực trị, không trả entity tương ứng**. Muốn entity, dùng subquery hoặc ORDER BY.
- **Aggregate không thay business semantics, concurrency control hay access control**. Định nghĩa rõ đơn vị tiền, trạng thái giao dịch, timezone và tenant.

**Kết luận:** Các hàm **`COUNT`, `SUM`, `AVG`, `MIN` và `MAX`** giúp JPQL tận dụng khả năng tổng hợp của database mà không phải tải toàn bộ entity để tính bằng Java. Để dùng đúng, điều quan trọng không chỉ là nhớ cú pháp, mà còn là **chọn đúng tập dữ liệu và mức hạt cần tổng hợp**, hiểu **NULL và kiểu trả về**, và kiểm soát **JOIN/GROUP BY/HAVING**. Một câu aggregate ngắn có thể trả số liệu sai nếu relationship làm nhân bản row; ngược lại, một truy vấn JPQL có ngữ nghĩa rõ ràng, DTO phù hợp và kiểm thử dữ liệu biên sẽ là nền tảng đáng tin cậy cho thống kê, dashboard và báo cáo trong ứng dụng JPA.
