# Truy vấn lateral hoặc bảng suy ra trong phạm vi hỗ trợ

## 1. Bối cảnh: khi một JOIN thông thường chưa biểu đạt đủ bài toán

Trong Hibernate ORM, HQL (*Hibernate Query Language*) thường được dùng để truy vấn các entity và association thay vì viết tên bảng/cột SQL. Hầu hết nhu cầu cơ bản có thể giải quyết với `join`, `where`, `group by` và `order by`. Tuy nhiên, một số báo cáo, bảng tổng hợp và màn hình cần cấu trúc phức tạp hơn:

- Lấy **dòng có giá trị lớn nhất trong từng đơn hàng**, vẫn hiển thị đơn hàng không có dòng nào.
- Lấy **hai lần thanh toán mới nhất của từng khách hàng**.
- Tổng hợp doanh thu theo khách hàng trong một truy vấn con, rồi lọc hoặc kết hợp bảng kết quả tổng hợp với entity khác.
- Tạo một **bảng kết quả trung gian** từ phép nhóm, sau đó sử dụng các cột của bảng đó ở câu truy vấn bên ngoài.
- Cho truy vấn con trong JOIN tham chiếu **giá trị của từng hàng từ phía bên trái**.

Trong SQL, hai công cụ thường được nhắc tới là **derived table** (bảng suy ra từ subquery trong FROM/JOIN) và **LATERAL JOIN** (JOIN tới subquery tương quan). Hibernate HQL hiện đại hỗ trợ những ý tưởng này, nhưng chúng **không phải cú pháp JPQL truyền thống có thể dùng nguyên vẹn trên mọi provider**. Ngoài ra, bản dịch sang SQL và mức hỗ trợ của database phụ thuộc dialect, phiên bản Hibernate và cấu trúc câu truy vấn.

Mục tiêu bài học:

1. Nhận biết khác biệt giữa subquery trong `where`, **derived root**, **derived join** và **lateral join**.
2. Viết HQL với những projection alias cần thiết để truy cập cột của bảng suy ra.
3. Dùng `join lateral`/`left join lateral` cho bài toán *top N per parent*.
4. Hiểu **correlation scope**, loại JOIN và hành vi khi child không tồn tại.
5. Phân biệt cú pháp HQL với SQL PostgreSQL, SQL Server hoặc các database khác.
6. Biết khi nào Hibernate có thể dịch/emulate và khi nào cần phương án thay thế.
7. Hiểu rủi ro hiệu năng: số hàng, phép sắp xếp, index, plan và phân trang.
8. Tạo DTO projection có kiểu, tổ chức test trên database thật và xử lý lỗi thường gặp.

**Ngữ cảnh:** ví dụ dựa trên khả năng HQL của Hibernate ORM 6.6. Một số khả năng đã xuất hiện trong các phiên bản Hibernate 6 trước đó và tiếp tục phát triển ở phiên bản mới; không giả định cú pháp/API giống nhau trong Hibernate 5.x hoặc giữa mọi bản 6.x/7.x. Cần kiểm tra [Hibernate HQL Guide 6.6](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/) và Javadoc của version đang chạy.

## 2. Mô hình dữ liệu minh họa

Giả sử ứng dụng thương mại có một đơn đặt hàng (`PurchaseOrder`) và nhiều dòng chi tiết (`OrderLine`):

~~~text
Customer (khách hàng)
  1
  |
  * PurchaseOrder (đơn hàng)
       1
       |
       * OrderLine (dòng hàng)
~~~

Một PurchaseOrder có thể chưa có dòng hàng, ví dụ đơn nháp. Mỗi dòng hàng có số lượng, đơn giá và tên mặt hàng tại thời điểm đặt.

### 2.1. Entity PurchaseOrder

~~~java
package com.example.orders;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    // Các getter và nghiệp vụ tạo/sửa đơn được lược bỏ.
}
~~~

### 2.2. Entity OrderLine

~~~java
package com.example.orders;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_name", nullable = false, length = 160)
    private String productName;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false, precision = 18, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    // Các getter và phương thức nghiệp vụ được lược bỏ.
}
~~~

Enum minh họa:

~~~java
public enum OrderStatus {
    DRAFT, SUBMITTED, PAID, CANCELLED
}
~~~

**Lưu ý:** đây là các đoạn mapping tập trung vào query, không phải toàn bộ một dự án có thể chạy độc lập; còn cần cấu hình SessionFactory/EntityManagerFactory, schema, migration, service, transaction và dữ liệu thử nghiệm.

### 2.3. Dữ liệu giả định

| Đơn | Khách hàng | Trạng thái | Dòng hàng |
|---|---:|---|---|
| 101 | 7 | PAID | Java Book: 200 × 2; USB: 50 × 1; Keyboard: 350 × 1 |
| 102 | 7 | PAID | Monitor: 1000 × 1; Cable: 20 × 2 |
| 103 | 8 | DRAFT | Không có dòng |
| 104 | 9 | PAID | Laptop: 1500 × 1; Mouse: 25 × 3 |

Mỗi dòng có **thành tiền** = `quantity * unitPrice`.

Hai truy vấn quan trọng trong bài:

- **A.** Với mỗi khách hàng, tổng doanh thu của những đơn PAID là bao nhiêu?
- **B.** Với **mỗi đơn hàng**, dòng nào có thành tiền lớn nhất? Đơn không có dòng vẫn phải được hiển thị.

Bài A hợp với **derived root** (bảng tổng hợp không phụ thuộc root bên ngoài). Bài B hợp với **lateral join** vì cần chạy top-1 theo từng đơn.

## 3. Subquery ở WHERE chưa phải derived table

Trước khi thêm derived root, cần phân biệt với subquery truyền thống trong `where`.

~~~sql
select o
from PurchaseOrder o
where exists (
    select 1
    from OrderLine li
    where li.order = o
      and li.quantity >= :minQuantity
)
~~~

Đây là **correlated subquery ở WHERE**: query bên trong tham chiếu `o` của query ngoài. Nó trả lời điều kiện có/không cho từng order, nhưng không tạo bảng trung gian để lấy nhiều cột của một child trong phần `select`.

Ta cũng có thể viết:

~~~sql
select o.id, (
    select max(li.unitPrice)
    from OrderLine li
    where li.order = o
)
from PurchaseOrder o
~~~

Đây là scalar subquery trong SELECT. Nó phù hợp nếu chỉ cần một giá trị tổng hợp (ở đây giá đơn vị cao nhất), không cần trả đồng thời ID, tên hàng, số lượng của **chính cùng dòng đạt cực đại**.

**Khác biệt cốt lõi:** subquery trong `where` hoặc `select` có thể correlated trong phạm vi ngữ pháp cho phép. Nhưng một **derived root trong FROM** theo HQL phải **không correlated**; muốn subquery trong JOIN tham chiếu root đứng trước, dùng **lateral join**.

## 4. Derived table, derived root và derived join

**Bảng suy ra (derived table)** là bảng logic được tạo từ kết quả một truy vấn con. Trong HQL 6.6, một subquery trong `from` có thể làm **derived root**; trong `join`, nếu không correlated, nó có thể làm **derived join**.

Một hình dung:

~~~text
Query con: GROUP BY customerId
    +---------------------+
    | customerId | total  |
    +------------+--------+
    | 7          | 1490   |
    | 8          | 0      |
    | 9          | 1575   |
    +---------------------+
               |
               v
     Derived root "revenue"
               |
               v
 Query ngoài: WHERE, JOIN, ORDER BY,
             projection DTO
~~~

Dữ liệu trong bảng minh họa chỉ có tính diễn giải; nếu query con lọc PAID, khách hàng chỉ có đơn DRAFT có thể không xuất hiện. Tùy cách query viết, phải phân biệt không có hàng với tổng bằng 0.

### 4.1. Derived root: subquery độc lập trong FROM

Ví dụ tổng doanh thu theo khách hàng chỉ tính đơn PAID:

~~~sql
select sales.customerId, sales.totalAmount
from (
    select o.customerId as customerId,
           sum(li.quantity * li.unitPrice) as totalAmount
    from PurchaseOrder o
        join o.lines li
    where o.status = :paidStatus
    group by o.customerId
) as sales
where sales.totalAmount >= :minimumRevenue
order by sales.totalAmount desc, sales.customerId asc
~~~

Điểm cần đọc:

1. Phần trong ngoặc tạo tập hàng gồm hai cột được đặt alias: `customerId` và `totalAmount`.
2. `sales` là identification variable (alias) của **bảng suy ra**.
3. Query ngoài có thể truy cập `sales.customerId` và `sales.totalAmount` giống các cột logic.
4. Query con **không tham chiếu bất kỳ root nào được khai báo bên ngoài**.
5. Tham số `:paidStatus`/`:minimumRevenue` vẫn là value parameter; không nối trực tiếp dữ liệu người dùng vào HQL.

Đây là một dạng HQL extension, không nên coi là JPQL portable cho mọi provider.

### 4.2. Ví dụ Java: lấy tuple từ derived root

~~~java
import jakarta.persistence.Tuple;
import org.hibernate.Session;
import org.hibernate.query.SelectionQuery;

String hql = """
    select sales.customerId as customerId,
           sales.totalAmount as totalAmount
    from (
        select o.customerId as customerId,
               sum(li.quantity * li.unitPrice) as totalAmount
        from PurchaseOrder o
            join o.lines li
        where o.status = :paidStatus
        group by o.customerId
    ) sales
    where sales.totalAmount >= :minimumRevenue
    order by sales.totalAmount desc, sales.customerId
    """;

Session session = entityManager.unwrap(Session.class);
SelectionQuery<Tuple> query =
    session.createSelectionQuery(hql, Tuple.class);

List<Tuple> rows = query
    .setParameter("paidStatus", OrderStatus.PAID)
    .setParameter("minimumRevenue", new BigDecimal("500.00"))
    .getResultList();

for (Tuple row : rows) {
    Long customerId = row.get("customerId", Long.class);
    BigDecimal total = row.get("totalAmount", BigDecimal.class);
    // Đóng gói response hoặc ghi báo cáo.
}
~~~

`EntityManager.unwrap(Session.class)` ràng buộc code vào Hibernate provider. Nếu ứng dụng đã dùng Session native, gọi trực tiếp `session.createSelectionQuery` là đủ. Kiểu numeric aggregate cần phù hợp mapping thực tế; BigDecimal là ví dụ cho phép nhân integer và NUMERIC trong HQL.

### 4.3. Trả DTO thay cho Tuple

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record CustomerRevenue(
    Long customerId,
    BigDecimal totalAmount
) {}
~~~

HQL:

~~~sql
select new com.example.orders.CustomerRevenue(
    sales.customerId,
    sales.totalAmount
)
from (
    select o.customerId as customerId,
           sum(li.quantity * li.unitPrice) as totalAmount
    from PurchaseOrder o
    join o.lines li
    where o.status = :paidStatus
    group by o.customerId
) sales
where sales.totalAmount >= :minimumRevenue
order by sales.totalAmount desc, sales.customerId
~~~

`CustomerRevenue` là DTO, không được Hibernate dirty-check như managed entity. Constructor expression cần đúng tên package, số và kiểu tham số.

### 4.4. Derived root không được phép correlate tới query ngoài

Ví dụ sau biểu diễn **ý định sai**:

~~~sql
-- KHÔNG hợp lệ theo semantics derived root:
from PurchaseOrder o,
(
    select max(li.unitPrice) as highestPrice
    from OrderLine li
    where li.order = o
) best
~~~

Query trong ngoặc tham chiếu `o` từ FROM bên ngoài. Nó không phải derived root độc lập. Nếu muốn tham chiếu `o`, hãy dùng **lateral join** hoặc viết lại bằng scalar subquery trong SELECT/WHERE.

Kết luận quan trọng: **vị trí xuất hiện subquery trong FROM/JOIN và việc nó có correlation hay không quyết định loại cú pháp cần dùng.**

## 5. Derived join: subquery độc lập, ghép bằng ON

Không nhất thiết phải đặt bảng suy ra làm root chính. Có thể đặt nó ở phía phải của JOIN và nối bằng điều kiện.

Giả sử cần mỗi PurchaseOrder kèm tổng tiền được tính từ các dòng:

~~~sql
select o.id, totals.totalAmount
from PurchaseOrder o
left join (
    select li.order.id as orderId,
           sum(li.quantity * li.unitPrice) as totalAmount
    from OrderLine li
    group by li.order.id
) as totals
    on totals.orderId = o.id
where o.status = :status
order by o.id
~~~

Đọc theo từng phần:

- Root chính: `PurchaseOrder o`.
- Query con: tổng hợp **toàn bộ** các OrderLine theo orderId; query con không tham chiếu `o`.
- `totals` là alias của derived join.
- `on totals.orderId = o.id` nối hàng kết quả tổng hợp với từng Order.
- `left join` giữ lại Order không có dòng hàng; `totals.totalAmount` khi ấy có thể là `null`.

### 5.1. Vì sao không dùng WHERE thay cho ON khi cần giữ parent rỗng?

Nếu đổi thành:

~~~sql
select o.id, totals.totalAmount
from PurchaseOrder o
left join (
    select li.order.id as orderId,
           sum(li.quantity * li.unitPrice) as totalAmount
    from OrderLine li
    group by li.order.id
) totals on totals.orderId = o.id
where totals.totalAmount >= :minimum
~~~

thì những order không có dòng bị loại vì phép so sánh với `NULL` không đúng. Khi muốn giữ order không có dòng, cân nhắc:

~~~sql
where totals.totalAmount is null
   or totals.totalAmount >= :minimum
~~~

hoặc dùng `coalesce(totals.totalAmount, 0)` **nếu** nghiệp vụ thật sự xem “chưa có dòng” là tổng 0. Không được dùng `coalesce` bừa bãi nếu không có dòng và tổng thực bằng 0 mang hai ý nghĩa khác nhau.

### 5.2. Derived join không có phép LIMIT riêng cho từng order

Một lỗi thường gặp:

~~~sql
from PurchaseOrder o
left join (
    select li.order.id as orderId,
           li.id as lineId
    from OrderLine li
    order by li.unitPrice desc
    limit 1
) best on best.orderId = o.id
~~~

`limit 1` bên trong query con độc lập chọn **một dòng lớn nhất trên toàn bộ tập OrderLine** trước khi JOIN, không phải chọn một dòng cho **từng** order. Sau JOIN, phần lớn đơn có thể không có dòng nào khớp, dù chúng có nhiều OrderLine.

Muốn top-1 **trên mỗi** PurchaseOrder, query con phải biết order đang xét. Đó là mục đích của lateral join.

## 6. Lateral join: truy vấn con được quyền tham chiếu root đứng trước

**LATERAL** cho phép subquery ở phía phải của JOIN truy cập root/alias đã xuất hiện **trước nó** trong cùng FROM clause.

Hình dung:

~~~text
FROM PurchaseOrder o
      |
      | mỗi hàng o
      v
LEFT JOIN LATERAL (
    query trên OrderLine
    WHERE li.order = o
    ORDER BY thành tiền DESC
    LIMIT 1
) best
      |
      v
1 order + dòng hàng top-1 tương ứng
hoặc 1 order + NULL nếu không có dòng
~~~

HQL 6.6 cho phép `join lateral` và `left join lateral` với correlated subquery; không hỗ trợ **right lateral join** hoặc **full lateral join**. Tùy dialect, Hibernate có thể phát SQL native tương ứng hoặc **emulate** (mô phỏng), nhưng emulation không bao phủ mọi query shape và có thể kém hiệu quả. Vì vậy phải kiểm thử với DB thực tế.

### 6.1. Lateral top-1 OrderLine theo thành tiền

~~~sql
select o.id,
       best.lineId,
       best.productName,
       best.lineAmount
from PurchaseOrder o
left join lateral (
    select li.id as lineId,
           li.productName as productName,
           li.quantity * li.unitPrice as lineAmount
    from o.lines li
    order by li.quantity * li.unitPrice desc, li.id asc
    limit 1
) best
where o.status = :status
order by o.id
~~~

Điều quan trọng:

1. `o` được khai báo trước `left join lateral`.
2. `from o.lines li` là **correlated path**, tham chiếu collection của đơn hiện tại.
3. `order by ... desc, li.id asc` sắp theo thành tiền và có tie-breaker bằng ID.
4. `limit 1` giới hạn **bên trong** subquery correlated, tức top-1 cho mỗi order.
5. `left join lateral` giữ order không có dòng; các cột `best.*` là null với order đó.
6. `select` bên ngoài lấy các scalar projection, không fetch một entity graph đầy đủ.

Đây là **HQL**, không phải SQL PostgreSQL viết trực tiếp. Hibernate dịch HQL qua dialect sang SQL phù hợp database.

### 6.2. Kết quả minh họa

Với dữ liệu ở phần 2, nếu lọc cả đơn PAID và DRAFT trong một truy vấn không có `where` trạng thái:

| orderId | lineId | productName | lineAmount |
|---:|---:|---|---:|
| 101 | ID dòng Java Book | Java Book | 400.00 |
| 102 | ID dòng Monitor | Monitor | 1000.00 |
| 103 | null | null | null |
| 104 | ID dòng Laptop | Laptop | 1500.00 |

Với order 101, dòng Java Book có thành tiền 400.00 (200 × 2), nên **đó mới là dòng top-1** theo tiêu chí thành tiền. Giá trị chính xác của ID dòng do dữ liệu/thao tác insert quyết định.

### 6.3. Inner lateral và left lateral

**Inner lateral:**

~~~sql
from PurchaseOrder o
join lateral (
    select li.id as lineId
    from o.lines li
    order by li.id
    limit 1
) picked
~~~

Nếu order không có dòng, subquery không trả row, nên order đó bị loại khỏi kết quả.

**Left lateral:**

~~~sql
from PurchaseOrder o
left join lateral (
    select li.id as lineId
    from o.lines li
    order by li.id
    limit 1
) picked
~~~

Nếu không có dòng, order vẫn được giữ và `picked.lineId` là null.

### 6.4. Tại sao không dùng RIGHT/FULL LATERAL?

HQL mô hình hóa lateral join như phép join tới biểu thức phía phải **phụ thuộc root đã có phía trái**. Hibernate 6.6 hỗ trợ dạng inner/left, không cho right/full lateral theo tài liệu. Nếu cần một dạng FULL OUTER với hai bên độc lập, phải thiết kế lại query hoặc dùng SQL/CTE theo database; không đổi từ khóa một cách máy móc.
+## 7. Thực thi lateral query qua Hibernate Session và DTO

Nếu chỉ cần dữ liệu hiển thị, không cần tải đầy đủ Order và OrderLine vào persistence context. Một DTO dạng record biểu diễn đúng những field cần đọc:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderTopLine(
    Long orderId,
    Long lineId,
    String productName,
    BigDecimal lineAmount
) {}
~~~

Khi dùng `left join lateral`, `lineId`, `productName` và `lineAmount` có thể null vì đơn hàng không có dòng. Đừng dùng primitive `long` cho trường có thể null.

### 7.1. HQL với constructor projection

~~~java
import org.hibernate.Session;
import org.hibernate.query.SelectionQuery;

String hql = """
    select new com.example.orders.OrderTopLine(
        o.id, best.lineId, best.productName, best.lineAmount
    )
    from PurchaseOrder o
    left join lateral (
        select li.id as lineId,
               li.productName as productName,
               li.quantity * li.unitPrice as lineAmount
        from o.lines li
        order by li.quantity * li.unitPrice desc, li.id asc
        limit 1
    ) best
    where o.status = :status
    order by o.id
    """;

Session session = entityManager.unwrap(Session.class);

SelectionQuery<OrderTopLine> query =
    session.createSelectionQuery(hql, OrderTopLine.class);

List<OrderTopLine> cards = query
    .setParameter("status", OrderStatus.PAID)
    .getResultList();
~~~

Đây là Hibernate-specific HQL, không phải JPQL portable. `entityManager.unwrap(Session.class)` đòi hỏi provider Hibernate; khi Session được unwrap từ EntityManager do Spring/Jakarta EE quản lý, không tự đóng Session/transaction ngoài cơ chế quản lý đó.

### 7.2. Dùng Tuple nếu danh sách field động

~~~java
import jakarta.persistence.Tuple;

SelectionQuery<Tuple> query = session.createSelectionQuery(
    """
    select o.id as orderId,
           best.lineId as lineId,
           best.lineAmount as lineAmount
    from PurchaseOrder o
    left join lateral (
        select li.id as lineId,
               li.quantity * li.unitPrice as lineAmount
        from o.lines li
        order by li.quantity * li.unitPrice desc, li.id asc
        limit 1
    ) best
    """,
    Tuple.class
);

for (Tuple row : query.getResultList()) {
    Long orderId = row.get("orderId", Long.class);
    Long lineId = row.get("lineId", Long.class);
    BigDecimal lineAmount = row.get("lineAmount", BigDecimal.class);
}
~~~

`Tuple` hợp với báo cáo ad hoc; record DTO giúp ràng buộc cấu trúc kết quả khi API có hợp đồng ổn định. Tên alias và Java type phải khớp với SELECT. Đặc biệt, phép nhân `int * BigDecimal` và aggregate phải được ánh xạ sang numeric Java type phù hợp với Hibernate/JDBC version.

### 7.3. DTO không phải managed entity

`OrderTopLine` không tự tham gia dirty checking, cascade hoặc lazy loading. Nếu DTO chứa một trường kiểu entity như `PurchaseOrder order`, entity component có thể vẫn là managed. Khi mục tiêu chỉ là read model thuần, nên chọn giá trị scalar thay vì nhúng entity.

Nếu cần sửa đơn sau khi hiển thị, hãy nhận command DTO, nạp managed PurchaseOrder trong transaction cập nhật rồi áp dụng domain logic; không merge read DTO như thể entity.

## 8. Top-N theo mỗi parent: kết quả có thể nhiều hàng

Lateral join hữu ích hơn khi muốn lấy N dòng hàng cho mỗi đơn, chẳng hạn top 2:

~~~sql
select o.id as orderId,
       picked.lineId as lineId,
       picked.name as name,
       picked.amount as amount
from PurchaseOrder o
left join lateral (
    select li.id as lineId,
           li.productName as name,
           li.quantity * li.unitPrice as amount
    from o.lines li
    order by li.quantity * li.unitPrice desc, li.id asc
    limit 2
) picked
order by o.id, picked.amount desc, picked.lineId
~~~

Mỗi PurchaseOrder có thể xuất hiện 1–2 lần, hoặc một lần với các trường phía phải là null nếu không có dòng. Vì vậy **row kết quả không còn tương ứng duy nhất một Order**.

### 8.1. Có thể nhóm kết quả ở tầng Java

~~~java
public record TopLineRow(
    Long orderId,
    Long lineId,
    String name,
    BigDecimal amount
) {}
~~~

Sau khi truy vấn lấy list DTO:

~~~java
Map<Long, List<TopLineRow>> byOrder = rows.stream()
    .collect(Collectors.groupingBy(
        TopLineRow::orderId,
        LinkedHashMap::new,
        Collectors.toList()
    ));
~~~

Trong bước tạo DTO cha, loại hàng “child null” nếu `lineId == null`. Nếu không, response có thể chứa một child giả. Record DTO constructor không tự gom collection từ nhiều SQL rows thành một object lồng nhau.

### 8.2. ORDER BY trong subquery và outer query khác nhau

- `order by` **trong** lateral subquery quyết định dòng nào thuộc top-N của mỗi parent.
- `order by` **ngoài** quyết định thứ tự cuối cùng của kết quả gửi về application.
- `limit N` **trong** subquery giới hạn child cho mỗi parent.
- `setMaxResults(N)` **ngoài** hoặc limit ở outer query giới hạn **tổng số output rows**, không giới hạn N per parent.

Nếu một order có nhiều child, outer pagination có thể cắt ngang nhóm child của một parent. Đừng dùng `setFirstResult()/setMaxResults()` trên row kết quả top-N rồi diễn giải thành phân trang theo số đơn hàng.

### 8.3. Cách phân trang parent rồi lấy child

Một chiến lược dễ kiểm soát:

1. Query trước một page gồm PurchaseOrder IDs theo một thứ tự ổn định, ví dụ `createdAt, id`.
2. Lấy danh sách IDs đó.
3. Chạy lateral top-N giới hạn vào `o.id in :orderIds`.
4. Ghép kết quả theo ID và khôi phục thứ tự parent như page đầu.

Ví dụ query thứ hai:

~~~sql
select o.id, picked.lineId, picked.amount
from PurchaseOrder o
left join lateral (
    select li.id as lineId,
           li.quantity * li.unitPrice as amount
    from o.lines li
    order by li.quantity * li.unitPrice desc, li.id
    limit 2
) picked
where o.id in :pageIds
order by o.id, picked.amount desc, picked.lineId
~~~

Tránh truyền collection parameter rỗng nếu dialect/provider không hỗ trợ tốt; xử lý page trống ở Java. Cần hiểu transaction isolation nếu data có thể thay đổi giữa hai query. Nếu dùng keyset pagination, cursor phải phản ánh đầy đủ thứ tự sort của parent.

### 8.4. Ties: chọn một hay tất cả dòng đồng hạng?

~~~sql
order by li.quantity * li.unitPrice desc
limit 1
~~~

Nếu hai dòng có cùng thành tiền cao nhất, thứ tự không được bảo đảm. Thêm tie-breaker:

~~~sql
order by li.quantity * li.unitPrice desc, li.id asc
limit 1
~~~

Câu này chọn đúng một dòng đại diện. Nếu yêu cầu lấy **tất cả** dòng đồng hạng cao nhất, cần một thiết kế khác (rank/dense_rank, subquery với max, hoặc native SQL), không thể chỉ dựa vào limit 1.

## 9. Vị trí predicate: ON, WHERE và WHERE bên trong lateral

Xét truy vấn lấy top line có thành tiền tối thiểu:

~~~sql
select o.id, picked.lineId, picked.amount
from PurchaseOrder o
left join lateral (
    select li.id as lineId,
           li.quantity * li.unitPrice as amount
    from o.lines li
    order by li.quantity * li.unitPrice desc, li.id
    limit 1
) picked on picked.amount >= :minimumAmount
~~~

Khi top line nhỏ hơn ngưỡng, phía JOIN trở thành null nhưng parent vẫn được giữ.

Nếu đặt predicate ở outer WHERE:

~~~sql
where picked.amount >= :minimumAmount
~~~

những parent có child null hoặc top line dưới ngưỡng sẽ bị loại, khiến `left join` không còn tác dụng giữ mọi parent đối với điều kiện đó.

Còn nếu đưa predicate vào lateral subquery trước ORDER BY/LIMIT:

~~~sql
left join lateral (
    select li.id as lineId, li.unitPrice as price
    from o.lines li
    where li.productName like :namePattern
    order by li.unitPrice desc, li.id
    limit 1
) picked
~~~

nghĩa là “lấy dòng giá cao nhất **trong các dòng có tên khớp**”. Đây có thể là kết quả khác với “lấy dòng giá cao nhất của toàn bộ đơn rồi chỉ giữ nếu tên khớp”. Hãy diễn đạt rõ nghiệp vụ trước khi chuyển predicate.

## 10. Correlation scope: chỉ tham chiếu alias đã có trước

Ví dụ hợp lệ về ý tưởng:

~~~sql
from PurchaseOrder o
left join lateral (
    select li.id as lineId
    from o.lines li
    order by li.id
    limit 1
) picked
~~~

Ở đây `o` được khai báo trước lateral subquery. Ví dụ sai:

~~~sql
-- Không dùng được o khi o chưa được khai báo:
from lateral (
    select li.id as lineId
    from o.lines li
) picked,
PurchaseOrder o
~~~

Lateral **không** có quyền tham chiếu các alias được khai báo sau nó. Nếu cần hai root khác nhau trong subquery tương quan, phải bảo đảm chúng đều nằm trước subquery trong FROM và query shape được HQL/dialect hỗ trợ.

Một parent có thể có nhiều lateral joins:

~~~sql
select o.id,
       highValue.lineId as highValueId,
       highQuantity.lineId as highQuantityId
from PurchaseOrder o
left join lateral (
    select li.id as lineId
    from o.lines li
    order by li.quantity * li.unitPrice desc, li.id
    limit 1
) highValue
left join lateral (
    select li.id as lineId
    from o.lines li
    order by li.quantity desc, li.id
    limit 1
) highQuantity
~~~

Hai lateral joins có thể chọn những child khác nhau. Nhưng mỗi lateral subquery có thể gây thêm công việc cho optimizer; với dataset lớn, cân nhắc window query hoặc một derived table tổng hợp thay thế.

## 11. HQL và SQL của từng database không giống nhau

### 11.1. PostgreSQL có SQL LEFT JOIN LATERAL

Đây là **SQL PostgreSQL**, không phải HQL:

~~~sql
SELECT o.id,
       picked.id AS line_id,
       picked.product_name,
       picked.amount
FROM purchase_orders AS o
LEFT JOIN LATERAL (
    SELECT li.id,
           li.product_name,
           li.quantity * li.unit_price AS amount
    FROM order_lines AS li
    WHERE li.order_id = o.id
    ORDER BY li.quantity * li.unit_price DESC, li.id ASC
    LIMIT 1
) AS picked ON TRUE
ORDER BY o.id;
~~~

Lateral subquery có thể tham chiếu `o.id`. `ON TRUE` hoàn thiện điều kiện LEFT JOIN SQL khi correlation đã nằm trong subquery. Khi dùng HQL `from o.lines li`, Hibernate tạo điều kiện FK phù hợp.

### 11.2. SQL Server dùng APPLY

Trong SQL Server, truy vấn tương đương có thể viết:

~~~sql
SELECT o.id, picked.id AS line_id, picked.amount
FROM purchase_orders AS o
OUTER APPLY (
    SELECT TOP (1)
           li.id,
           li.quantity * li.unit_price AS amount
    FROM order_lines AS li
    WHERE li.order_id = o.id
    ORDER BY li.quantity * li.unit_price DESC, li.id
) AS picked
ORDER BY o.id;
~~~

- `OUTER APPLY` thường có semantics tương đương giữ parent như LEFT JOIN LATERAL.
- `CROSS APPLY` thường tương đương inner lateral.
- `TOP (1)` là cú pháp SQL Server trong ví dụ; không phải cú pháp HQL cần viết trong subquery.
- Cách Hibernate dịch SQL phụ thuộc dialect/version, không nên tự coi bản SQL minh họa là SQL Hibernate chắc chắn tạo ra.

### 11.3. Dialect, version và emulation

Không phải database nào cũng hỗ trợ native `LATERAL` hoặc `APPLY` theo cùng cú pháp và cùng giới hạn. Hibernate có thể emulation cho một số database/shape không hỗ trợ trực tiếp, nhưng tài liệu HQL cảnh báo emulation có thể **không hiệu quả** và **không hỗ trợ mọi hình dạng query**.

Đối với mỗi dự án, xác định:

- Hibernate ORM major/minor version.
- Dialect mà Hibernate thực sự sử dụng.
- Database engine và version.
- Sự hiện diện của ORDER BY/LIMIT trong correlated subquery.
- Loại JOIN (inner/left), số level correlation, phép nhóm và projection.
- SQL được sinh ra, số row, index và execution plan.

Không nên khẳng định “nếu HQL parse được thì mọi DB đều chạy hiệu quả”. Query có thể parse thành công rồi SQL bị DB từ chối, hoặc chạy được nhưng kém hiệu quả.
+## 12. Khi không dùng được LATERAL: các lựa chọn thay thế

Không phải bài toán nào cũng cần lateral join. Nếu database/dialect không hỗ trợ hoặc SQL dịch ra chạy chậm, hãy cân nhắc aggregate, correlated subquery, derived table với window function, CTE, hai truy vấn hoặc native SQL.

### 12.1. Chỉ cần một giá trị MAX: GROUP BY hoặc scalar subquery

Nếu chỉ hỏi “đơn giá lớn nhất của mỗi đơn”, không cần ID và tên của dòng đạt cực đại:

~~~sql
select o.id, max(li.unitPrice)
from PurchaseOrder o
left join o.lines li
group by o.id
order by o.id
~~~

Hoặc:

~~~sql
select o.id,
       (select max(li.unitPrice)
        from OrderLine li
        where li.order = o)
from PurchaseOrder o
~~~

Hai query này không yêu cầu lateral. Với order không có dòng, `max` có thể null. Nếu muốn cả tên và ID **của chính dòng có giá trị lớn nhất**, chỉ biết max là không đủ; phải xác định quy tắc xử lý tie và chọn một kỹ thuật khác.

### 12.2. Chỉ cần kiểm tra tồn tại: EXISTS

~~~sql
select o.id
from PurchaseOrder o
where exists (
    select 1
    from OrderLine li
    where li.order = o
      and li.quantity >= :minimumQuantity
)
~~~

`exists` thường diễn đạt đúng hơn nhu cầu yes/no, thay vì tạo derived/lateral table chỉ để xem có child hay không.

### 12.3. Window function và derived join: top-1 mỗi order

Hibernate HQL 6.6 hỗ trợ window expressions như `row_number() over (...)`. Có thể đánh số thứ tự của dòng theo từng order, rồi ghép hạng 1:

~~~sql
select o.id, ranked.lineId, ranked.name, ranked.amount
from PurchaseOrder o
left join (
    select li.order.id as orderId,
           li.id as lineId,
           li.productName as name,
           li.quantity * li.unitPrice as amount,
           row_number() over (
               partition by li.order.id
               order by li.quantity * li.unitPrice desc, li.id asc
           ) as rn
    from OrderLine li
) ranked
    on ranked.orderId = o.id and ranked.rn = 1
order by o.id
~~~

Câu này sử dụng **derived join không correlated**. Correlation diễn ra ở `on` của query ngoài, còn subquery trong ngoặc tự đánh số tất cả dòng. `left join` giữ order rỗng.

Nếu muốn top-3, đổi điều kiện `ranked.rn <= 3`. Để giữ **tất cả dòng đồng hạng**, cân nhắc `rank` hoặc `dense_rank` và định nghĩa tie semantics; `row_number` luôn gán thứ hạng số nguyên riêng cho từng row.

So với lateral, window query có thể cho database xử lý theo một phép phân vùng lớn thay vì nhiều index seeks. Nhưng nó cũng có thể cần sort nhiều hàng và bộ nhớ. Không mặc định window luôn nhanh hơn; cần đo plan/khối lượng dữ liệu.

### 12.4. CTE: đặt tên cho bảng tổng hợp

Hibernate HQL hiện đại có Common Table Expressions:

~~~sql
with revenueByCustomer as (
    select o.customerId as customerId,
           sum(li.quantity * li.unitPrice) as revenue
    from PurchaseOrder o
    join o.lines li
    where o.status = :status
    group by o.customerId
)
select r.customerId, r.revenue
from revenueByCustomer r
where r.revenue >= :minimum
order by r.revenue desc, r.customerId
~~~

CTE về cơ bản là một subquery được đặt tên, giúp chia query phức tạp thành phần có nghĩa. HQL CTE có khả năng và giới hạn phụ thuộc version/dialect. Không suy luận CTE bắt buộc được DB materialize hoặc sẽ nhanh hơn derived root; optimizer có thể inline.

Một CTE không correlated tự nó không giải bài toán “top-1 row cho từng parent” nếu chưa có chiến lược `row_number`/aggregate hoặc cơ chế khác.

### 12.5. Hai query rồi ghép ở Java

Một chiến lược đơn giản nếu chỉ cần dữ liệu của page nhỏ:

1. Query một page PurchaseOrder IDs theo sort ổn định.
2. Query tất cả OrderLine thuộc IDs đó và order theo orderId, amount desc, lineId.
3. Lấy tối đa N dòng trong từng nhóm ở Java.
4. Ghép DTO.

Cách này tránh lateral, có thể dễ bảo trì và chạy trên nhiều provider. Nhưng query child có thể tải rất nhiều row khi mỗi parent có hàng nghìn lines, nên cần đánh giá memory/network và giới hạn page.

### 12.6. Native SQL khi yêu cầu phụ thuộc database

Nếu ứng dụng chỉ hỗ trợ PostgreSQL và muốn tối ưu bằng SQL LATERAL chuyên biệt, native SQL có thể hợp lý. Nếu ứng dụng chỉ hỗ trợ SQL Server, APPLY cũng có thể hợp lý. Khi đó dùng tên bảng/cột thật và result mapping rõ ràng; không đưa chuỗi SQL native vào HQL `createSelectionQuery()`.

Sự phụ thuộc DB là một quyết định kiến trúc, không phải lỗi. Điều quan trọng là document và test version tương thích.

## 13. Kiểu dữ liệu và alias của bảng suy ra

### 13.1. Projection alias là “cột” của derived table

~~~sql
select d.customerId, d.total
from (
    select o.customerId as customerId,
           sum(li.quantity * li.unitPrice) as total
    from PurchaseOrder o
    join o.lines li
    group by o.customerId
) d
~~~

Outer query truy cập `d.customerId` và `d.total` vì query con đã khai báo alias. Không nên trông đợi một biểu thức `sum(...)` không có alias tự sinh tên `total`.

### 13.2. Alias bên trong không rò ra bên ngoài

Ví dụ sai về phạm vi:

~~~sql
select li.productName
from PurchaseOrder o
left join lateral (
    select li.productName as productName
    from o.lines li
    order by li.id
    limit 1
) picked
~~~

`li` chỉ tồn tại bên trong lateral subquery. Outer SELECT phải dùng `picked.productName`.

### 13.3. HQL dùng property, không dùng tên cột vật lý

Nếu entity field là `productName` và cột DB là `product_name`, viết `li.productName` trong HQL. Việc ánh xạ thành `product_name` thuộc Hibernate dialect/mapping. Với native SQL thì dùng tên cột DB.

### 13.4. NULL do LEFT JOIN

Sau `left join lateral`, field phía phải có thể null. Vì vậy:

- Dùng `Long`/`BigDecimal` dạng reference cho field nullable trong record DTO.
- Không dùng Java primitive `long` cho ID phía phải.
- Tránh `where picked.amount > ...` nếu muốn giữ parent không có child.
- Chỉ dùng `coalesce(picked.amount, 0)` nếu 0 phản ánh đúng ý nghĩa nghiệp vụ.
- Nếu cần biết “không có child” khác “child có amount 0”, hãy giữ `picked.lineId` và kiểm tra null.

### 13.5. Parameter binding

`:status`, `:minimum` và `:pageIds` là value parameters. Bind bằng `setParameter`/`setParameterList` theo API/version. Không ghép chuỗi dữ liệu người dùng vào HQL, kể cả khi query nằm sâu trong derived/lateral subquery.

Sort field động không thể thay bằng bind parameter tên cột; chỉ ghép tên attribute từ allowlist của ứng dụng.

## 14. Phân trang, fetch join và persistence context

`limit 2` trong lateral có nghĩa tối đa 2 child cho **mỗi** parent, còn `setMaxResults(20)` của outer SelectionQuery chỉ giới hạn **20 result rows**. Nếu mỗi Order có 2 child, 20 result rows có thể chỉ tương ứng 10 Order IDs.

Vì vậy, với API phân trang danh sách đơn hàng kèm top-N lines, thường nên:

1. Page parent IDs/summary trước với `order by` ổn định và tie-breaker.
2. Chạy lateral query cho `where o.id in :pageIds`.
3. Nhóm lại theo parent IDs và trả theo đúng thứ tự page ban đầu.

Một query DTO không cần tự tải managed OrderLine entities, giảm nguy cơ lazy loading/N+1 ở tầng ORM. Nhưng nếu sau query service lại gọi repository một lần cho mỗi DTO, vẫn có thể phát sinh N+1 ở tầng ứng dụng.

**Không dùng `join fetch` trong subquery** để cố “tối ưu”: fetch join dành cho entity graph có owner thích hợp; tài liệu HQL không cho phép fetch join trong subquery. Với query chỉ chọn DTO scalar, join thông thường đủ.

Nếu output DTO chứa entity `PurchaseOrder` thay vì chỉ ID, entity đó vẫn có thể là managed và nằm trong persistence context. Lateral không tự làm mọi thứ trở thành read-only hay detached.

## 15. Hiệu năng: một SQL statement vẫn có thể rất đắt

Lateral không nhất thiết tạo N+1 SQL round-trips từ ứng dụng: Hibernate có thể phát **một SQL statement** cho tất cả orders. Nhưng database có thể thực hiện correlated seeks/scans/sorts cho từng row parent trong execution plan.

Cần phân biệt:

- **N+1 từ ORM/application:** 1 SELECT parent rồi N SELECT child do lazy loading/repository loop.
- **Correlated work trong database:** một SQL statement thực hiện nested-loop/index lookup cho nhiều parent.

Giảm round-trip là có ích, nhưng không đảm bảo query tối ưu.

### 15.1. Chỉ số nên quan sát

- Số root rows và phân bố child counts.
- Số row output sau lateral.
- Index trên `order_lines.order_id`, biểu thức sắp xếp.
- Chi phí sort/temp memory, nested loop, repeated index scans.
- SQL Hibernate sinh ra: native LATERAL/APPLY hay emulation?
- Số round-trips, thời gian DB và thời gian mapping DTO.
- Outer pagination/count query và tính nhất quán giữa hai lượt đọc.

### 15.2. Index gợi ý theo workload

~~~sql
CREATE INDEX idx_order_lines_order_id
ON order_lines(order_id);
~~~

Khi sort thường xuyên theo `quantity * unit_price`, có thể xem expression index hoặc generated computed column `line_amount` ở DB hỗ trợ. Không giả định index trên riêng `quantity` tự giúp sort theo tích với unitPrice. Việc thêm index phải xét chi phí ghi và kích thước dữ liệu thực tế.

### 15.3. Derived root không chắc là bảng tạm vật lý

Database optimizer có thể inline derived table, push predicates hoặc materialize kết quả. CTE cũng có những lựa chọn tương tự tùy DB. Cấu trúc dấu ngoặc trong HQL không cho biết chính xác plan. Khi đánh giá, sử dụng `EXPLAIN` và benchmark trên dữ liệu gần production.
+## 16. Phạm vi phiên bản, JPQL compliance và dialect

### 16.1. Hibernate 5, Hibernate 6 và Hibernate 7

Đừng giả định code dùng derived root/lateral trong tài liệu Hibernate 6.6 chạy y nguyên trên Hibernate 5. Query language được mở rộng qua các phiên bản và có thể thay đổi cú pháp, parser, semantic checks hoặc SQL translation.

| Môi trường | Điều cần xác nhận |
|---|---|
| Hibernate 5.x | Tính năng HQL có sẵn trong đúng version; cân nhắc native SQL nếu thiếu |
| Hibernate 6.6 | Có hướng dẫn chính thức về derived roots, subqueries in joins và lateral joins |
| Hibernate 7.x+ | Đọc HQL guide/migration guide đúng phiên bản; không suy ra mọi overload/dialect tương đồng |
| Provider JPA khác Hibernate | HQL extension không mặc định được hỗ trợ |
| DB thiếu native LATERAL/APPLY | Hibernate có thể emulate nhưng không với mọi query shape và không chắc tối ưu |

### 16.2. HQL extension không tự trở thành JPQL portable

Ví dụ cấu hình:

~~~properties
hibernate.jpa.compliance.query=true
~~~

Khi bật strict JPQL compliance, các HQL features ngoài tập chuẩn có thể bị từ chối. Derived roots và lateral joins cần được xét như tính năng đặc thù HQL. Việc đổi interface Java từ `SelectionQuery` sang `TypedQuery` hoặc ngược lại không làm cú pháp thành portable.

Nếu portability giữa các JPA providers là yêu cầu quan trọng, cân nhắc aggregate/EXISTS/scalar subquery chuẩn JPQL hoặc thiết kế query adapter để cô lập phần HQL-specific.

### 16.3. Xác định tầng gây lỗi

~~~text
Java source / HQL string
      |
      v
Hibernate parser + semantic model
  alias / correlation / kiểu projection
      |
      v
SQL AST + Dialect
  native LATERAL / APPLY / emulation
      |
      v
JDBC -> Database
  SQL syntax / execution plan / indexes
      |
      v
Tuple / DTO result
~~~

Nếu HQL parser báo không hiểu `lateral`, đó là vấn đề khác với SQL sinh ra bị DB từ chối. Nếu query chạy đúng nhưng chậm, cần execution plan và số lượng hàng, không chỉ đổi từ khóa trong HQL.

## 17. Thử nghiệm với database mục tiêu

Vì Hibernate có thể dịch/emulate lateral khác nhau theo dialect, integration test là cần thiết khi ứng dụng phụ thuộc kết quả và hiệu năng của query. Unit test mock repository không kiểm chứng được SQL dialect hay optimizer.

### 17.1. Dataset tối thiểu

- Order A có ba lines thành tiền 100, 400, 250.
- Order B không có line.
- Order C có một line thành tiền 50.
- Order D có hai lines bằng tiền nhưng ID khác nhau.
- Một số đơn PAID/DRAFT để kiểm tra filter.
- Một đơn có nhiều lines để quan sát chi phí sorting.

### 17.2. Trường hợp cần kiểm chứng

| Trường hợp | Kết quả logic mong đợi |
|---|---|
| Inner lateral top-1 | Order B không xuất hiện |
| Left lateral top-1 | Order B xuất hiện, trường child null |
| Left lateral top-2 | Order A có tối đa hai output rows |
| ORDER BY có tie-breaker ID | Order D có lựa chọn ổn định |
| Derived join với tổng theo order | Order B có tổng null nếu không có nhóm |
| Derived join global `limit 1` | Chỉ một child trên toàn bộ tập, không phải top-1 per order |
| Condition trên child ở outer WHERE | Có thể làm mất order không có line |
| Predicate trong ON | Có thể giữ order với child null |
| Outer limit top-2 | Giới hạn rows, không phải số đơn |

Chạy query trong transaction rõ ràng và dùng dữ liệu đã commit để kết quả test không bị ảnh hưởng bởi state cũ của persistence context.

### 17.3. Mẫu repository đơn giản

~~~java
@Repository
public class HibernateOrderHighlightsReader {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<OrderTopLine> findTopLines(OrderStatus status) {
        Session session = entityManager.unwrap(Session.class);

        return session.createSelectionQuery(
            """
            select new com.example.orders.OrderTopLine(
                o.id, best.lineId, best.productName, best.lineAmount
            )
            from PurchaseOrder o
            left join lateral (
                select li.id as lineId,
                       li.productName as productName,
                       li.quantity * li.unitPrice as lineAmount
                from o.lines li
                order by li.quantity * li.unitPrice desc, li.id
                limit 1
            ) best
            where o.status = :status
            order by o.id
            """,
            OrderTopLine.class
        ).setParameter("status", status)
         .getResultList();
    }
}
~~~

Mẫu minh họa cần import `jakarta.persistence.EntityManager`, `PersistenceContext`, `org.hibernate.Session` và các annotation của Spring. Giả định Spring đã cấu hình Hibernate và transaction manager phù hợp. Không tự đóng Session được unwrap từ EntityManager do Spring quản lý.

`@Transactional(readOnly = true)` là hint/optimization của framework, không phải quyền DB đảm bảo tuyệt đối cấm thao tác ghi.

### 17.4. Quan sát SQL và execution plan

Trong môi trường test:

1. Bật SQL logging phù hợp Hibernate version.
2. Xem SQL sinh ra dùng LATERAL, APPLY hay emulation.
3. Kiểm tra số SQL statements, số rows và các trường được select.
4. Dùng `EXPLAIN` hoặc execution plan của DB đích.
5. So sánh lateral với window/CTE/aggregate trên dataset đại diện.
6. Không ghi bind values nhạy cảm vào log production nếu chưa có chính sách bảo vệ.

Không dùng kết quả benchmark trên DB in-memory khác production để khẳng định khả năng hay hiệu năng của PostgreSQL/SQL Server đang triển khai.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng tiếp cận |
|---|---|---|
| HQL parser không nhận `lateral` | Hibernate version hoặc strict JPQL compliance | Xem HQL guide/version/config |
| Derived root báo lỗi correlation | Subquery FROM tham chiếu alias ngoài | Chuyển sang lateral hoặc viết lại |
| Derived table không có `total` | Projection thiếu alias | Đặt `sum(...) as total` |
| Outer SELECT không nhận `li.id` | `li` là alias nội bộ | Dùng alias projection `picked.lineId` |
| Lateral không nhận outer alias | Alias được khai báo sau hoặc ngoài scope | Đặt root trước lateral |
| Chọn top-1 nhưng chỉ một parent có kết quả | Derived join với global LIMIT 1 | Dùng correlated lateral/window |
| Parent rỗng bị mất | Inner lateral hoặc outer WHERE lọc null | Left lateral và predicate phù hợp |
| Top-1 thay đổi giữa các lần chạy | Thiếu tie-breaker | Thêm `li.id` vào ORDER BY |
| Top-2 tạo duplicate order IDs | Một parent có nhiều result rows | Flat DTO/grouping đúng |
| Pagination trả ít parent | Giới hạn outer result rows | Page parent IDs trước |
| Query chạy trên Postgres nhưng DB khác báo lỗi | Dialect emulation/support | Xem SQL, dùng fallback |
| Query chạy được nhưng chậm | Repeated scan/sort, index thiếu, emulation | EXPLAIN/index/window alternative |
| DTO constructor không khớp | Kiểu/thứ tự/nullability projection | Sửa constructor và alias |
| HQL dùng `order_id` sai | Tên cột SQL thay cho Java attribute | Dùng `li.order.id` |
| Native SQL Server không chạy trên Postgres | `TOP/APPLY` khác `LIMIT/LATERAL` | Dùng SQL đúng DB hoặc HQL dialect |
| Count page không khớp | Join top-N nhân rows | Count parent riêng |
| Parent có no lines bị render child giả | Left join tạo row với child null | Lọc `lineId == null` khi nhóm |

## 19. Bài tập thực hành

### Bài 1 — Derived root

Viết HQL derived root tổng doanh thu theo `customerId` cho đơn PAID, sau đó lọc khách có doanh thu vượt `:minimum`.

**Gợi ý:** group by `o.customerId`, đặt alias `customerId`/`revenue`, outer query dùng `sales.revenue`.

### Bài 2 — Sai correlation

~~~sql
from PurchaseOrder o,
(
    select max(li.unitPrice) as highest
    from OrderLine li
    where li.order = o
) d
~~~

**Câu hỏi:** tại sao không phải derived root hợp lệ?

**Đáp án:** Subquery trong FROM tham chiếu `o` của root ngoài; derived root phải uncorrelated. Có thể dùng scalar subquery hoặc lateral.

### Bài 3 — Global LIMIT

Một derived join độc lập dùng `order by li.unitPrice desc limit 1`.

**Câu hỏi:** nó chọn top-1 mỗi order không?

**Đáp án:** Không. Nó chọn một dòng global trong subquery trước khi JOIN.

### Bài 4 — Không mất parent

Một Order không có lines vẫn phải xuất hiện.

**Câu hỏi:** dùng loại lateral nào?

**Đáp án:** `left join lateral`; DTO phía child phải cho phép null.

### Bài 5 — Top-2 và phân trang

Lateral dùng `limit 2`, query ngoài `setMaxResults(20)`.

**Câu hỏi:** có chắc API trả 20 orders không?

**Đáp án:** Không. 20 là số output rows, có thể có nhiều rows cho mỗi Order.

### Bài 6 — Tie-breaker

Hai OrderLine có cùng thành tiền.

**Câu hỏi:** `order by amount desc limit 1` có luôn chọn cùng một lineId?

**Đáp án:** Không có bảo đảm. Thêm khóa ổn định như `li.id asc`.

### Bài 7 — ON khác WHERE

Truy vấn left lateral nhưng có `where picked.amount > :minimum`.

**Câu hỏi:** vì sao Order không có lines bị loại?

**Đáp án:** WHERE trên giá trị null không thỏa điều kiện; cân nhắc đặt predicate trong ON hoặc xử lý null theo nghiệp vụ.

### Bài 8 — Strict JPQL

Ứng dụng bật `hibernate.jpa.compliance.query=true`.

**Câu hỏi:** có thể mặc định dùng `left join lateral` không?

**Định hướng:** Không. LATERAL là extension HQL; phải kiểm tra compliance setting và feature support.

### Bài 9 — Truy vấn chỉ cần MAX

Dashboard chỉ cần giá đơn vị cao nhất trên mỗi Order.

**Câu hỏi:** lateral có phải lựa chọn duy nhất?

**Đáp án:** Không. `max` + group by hoặc scalar correlated subquery đơn giản hơn.

### Bài 10 — Window alternative

DB không hỗ trợ lateral query shape mong muốn nhưng hỗ trợ window functions.

**Câu hỏi:** làm sao chọn top-1 per order?

**Định hướng:** derived join với `row_number() over(partition by orderId order by amount desc, lineId)` rồi lọc `rn = 1` ở ON.

### Bài 11 — SQL khác dialect

Một developer copy SQL PostgreSQL `LEFT JOIN LATERAL` sang SQL Server.

**Câu hỏi:** hướng thay thế?

**Định hướng:** `OUTER APPLY`/`CROSS APPLY` khi viết SQL Server native, hoặc để Hibernate dialect dịch HQL nếu hỗ trợ.

### Bài 12 — Plan chậm

Một lateral top-1 mất nhiều thời gian khi có 100.000 orders.

**Câu hỏi:** nên kiểm tra gì trước khi đổi sang window query?

**Định hướng:** index FK, expression sort, SQL được dịch/emulate, parent-child cardinality, execution plan, memory và latency trên DB thật.

## 20. Tổng kết

Ba hình thức quan trọng:

| Hình thức | Có được correlate tới root trước trong FROM? | Trường hợp phù hợp |
|---|---|---|
| **Derived root** | Không | Một bảng trung gian tổng hợp độc lập để query ngoài lọc/sort |
| **Derived join** không lateral | Không ở trong subquery; liên kết bằng ON | Ghép dữ liệu tổng hợp theo khóa với parent |
| **Lateral join** | Có, với root/alias đã khai báo trước | Top-N theo từng parent, correlated result |

Những điểm cần nhớ:

- Derived root phải **uncorrelated**; lateral cho phép subquery tương quan với phía trái.
- `limit 1` trong derived query độc lập là **global top-1**, không phải top-1 mỗi parent.
- Inner lateral có thể loại parent không có child; left lateral giữ parent với field child null.
- Alias trong projection của subquery quyết định những field outer query truy cập được.
- Lateral HQL là extension Hibernate, không tự portable như JPQL chuẩn.
- Hibernate có thể dịch hoặc emulate theo dialect, nhưng không đảm bảo mọi hình dạng truy vấn được hỗ trợ hoặc tối ưu.
- Với nhu cầu MAX/EXISTS, aggregate và scalar subquery thường đơn giản hơn.
- Với top-N, so sánh lateral, window, derived join/CTE và query tách theo page.
- Pagination, tie-breaker, nullability, type mapping và execution plan đều quan trọng.

Câu hỏi dẫn dắt: **“Subquery này tính một lần trên toàn tập dữ liệu, hay cần tham chiếu từng parent đang được xử lý?”** Nếu độc lập, cân nhắc derived root/join; nếu phụ thuộc parent, lateral có thể là công cụ thích hợp trong phạm vi hỗ trợ.

### Tài liệu chính thức

- [Hibernate ORM 6.6 — A Guide to Hibernate Query Language](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/) — derived roots, subqueries in joins, lateral, window functions và CTE.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — HQL, fetching và thực thi truy vấn.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — chọn hướng dẫn/Javadoc khớp version.
- [SelectionQuery API — Hibernate 6.6](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/query/SelectionQuery.html) — truy vấn đọc có kiểu.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — giới hạn JPQL portable.
- [PostgreSQL — Table Expressions](https://www.postgresql.org/docs/current/queries-table-expressions.html) — SQL LATERAL.
- [Microsoft SQL Server — FROM/APPLY](https://learn.microsoft.com/en-us/sql/t-sql/queries/from-transact-sql) — CROSS APPLY và OUTER APPLY.

> Khi triển khai, hãy đối chiếu Hibernate major/minor version, dialect, database engine/version và SQL thực sự được sinh ra. Kiểm thử trên database đích trước khi dựa vào một HQL lateral/derived query trong logic nghiệp vụ quan trọng.



