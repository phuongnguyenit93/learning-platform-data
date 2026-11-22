# Hàm cửa sổ, xếp hạng và tổng hợp theo nhóm cửa sổ trong HQL

## 1. Bài toán: tính toán trên nhóm dữ liệu nhưng vẫn giữ từng hàng

Một hệ thống bán hàng cần trả lời những câu hỏi như:

- Mỗi đơn hàng đứng thứ mấy theo tổng tiền trong các đơn của cùng một khách?
- Hai đơn có cùng tổng tiền có cùng hạng hay không?
- Tổng tiền tích lũy của một khách thay đổi như thế nào sau từng đơn?
- Trung bình ba đơn gần nhất của mỗi khách là bao nhiêu?
- Đơn hiện tại chênh lệch bao nhiêu so với đơn trước đó?
- Làm cách nào lấy **hai đơn lớn nhất của từng khách** mà không chạy một truy vấn riêng cho mỗi khách?

Truy vấn tổng hợp truyền thống với GROUP BY thường làm giảm nhiều hàng thành một hàng cho mỗi nhóm:

~~~hql
select o.customer.id, sum(o.totalAmount)
from PurchaseOrder o
where o.status = :paid
group by o.customer.id
~~~

Kết quả cho biết tổng tiền của từng khách nhưng **không còn từng đơn hàng**. Nếu cần cả mã đơn và tổng tiền của khách tương ứng trong một tập kết quả, ta có thể dùng **window function**:

~~~hql
select
    o.id,
    o.customer.id,
    o.totalAmount,
    sum(o.totalAmount) over (
        partition by o.customer.id
    )
from PurchaseOrder o
where o.status = :paid
~~~

Ở đây, mỗi PurchaseOrder vẫn xuất hiện dưới dạng một hàng kết quả. Biểu thức SUM OVER tính tổng dựa trên nhóm các đơn có cùng customer, rồi gắn kết quả đó với từng hàng.

**Ý tưởng cốt lõi:** GROUP BY thay đổi độ hạt của kết quả; window function thực hiện phép tính trên một tập hàng liên quan nhưng thông thường vẫn giữ độ hạt của các hàng đầu vào.

Bài học thuộc chương **HQL nâng cao** của module Hibernate ORM. Ví dụ sử dụng Java 17+, Jakarta Persistence, Hibernate ORM 6.x và PostgreSQL. Window function là phần mở rộng quan trọng của HQL hiện đại; không mặc định mọi JPQL provider hoặc mọi phiên bản Hibernate đều chấp nhận toàn bộ cú pháp này. Hãy kiểm chứng trên phiên bản Hibernate và dialect thực tế của dự án.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu ngữ nghĩa OVER, PARTITION BY, ORDER BY và window frame.
2. Phân biệt ROW_NUMBER, RANK và DENSE_RANK khi dữ liệu có giá trị bằng nhau.
3. Dùng COUNT, SUM, AVG, MIN và MAX dưới dạng windowed aggregate.
4. Tính running total, moving average và tỷ trọng của một hàng trong tổng nhóm.
5. Dùng LAG, LEAD, FIRST_VALUE và LAST_VALUE để so sánh các hàng liền kề.
6. Lấy top-N per group bằng một truy vấn lồng thay vì tải hết về Java.
7. Hiểu thứ tự xử lý WHERE, GROUP BY, HAVING và window expressions.
8. Tránh nhân bản hàng khi join collection, xử lý null, tie-breaker và window frame.
9. Tích hợp HQL window function với EntityManager, DTO/Tuple và Spring Data.
10. Đánh giá hiệu năng bằng SQL thực tế, EXPLAIN ANALYZE và kiểm thử dữ liệu biên.

## 2. Mô hình dữ liệu xuyên suốt

Ta dùng hai entity Customer và PurchaseOrder:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    protected Customer() {}

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
}
~~~

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

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
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public Instant getCreatedAt() { return createdAt; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}

enum OrderStatus {
    DRAFT, PAID, CANCELLED
}
~~~

Trong một project Java thực tế, mỗi public top-level class được đặt trong file riêng. Ví dụ giả định database có các cột tương ứng và migration đã được thực hiện.

Dữ liệu minh họa gồm các đơn đã thanh toán:

| order_id | customer_id | created_at | total_amount |
|---:|---:|---|---:|
| 201 | 1 | 2026-11-10 | 100.00 |
| 202 | 1 | 2026-11-11 | 100.00 |
| 203 | 1 | 2026-11-12 | 60.00 |
| 301 | 2 | 2026-11-10 | 90.00 |
| 302 | 2 | 2026-11-12 | 40.00 |

Trong phần này các đơn đều PAID để phép tính dễ kiểm chứng. Những ứng dụng thật phải quyết định rõ có tính đơn DRAFT, CANCELLED, REFUNDED, giao dịch hoàn tiền hay không. Không cộng tiền của nhiều currency vào cùng một tổng khi chưa có quy tắc chuyển đổi và thời điểm tỷ giá xác định.

### 2.1. HQL vẫn dùng tên entity và thuộc tính

Ví dụ:

~~~hql
select o.id, o.customer.id, o.totalAmount
from PurchaseOrder o
~~~

HQL dùng PurchaseOrder, customer, id và totalAmount, **không dùng trực tiếp** tên bảng purchase_orders hay cột total_amount. Hibernate dựa trên mapping để sinh SQL sử dụng bảng và cột thực.

### 2.2. Window partition không phải physical database partition

Từ PARTITION trong OVER chỉ có nghĩa chia tập kết quả thành **các nhóm logic phục vụ phép tính**. Nó không tạo bảng, không thay đổi partitioning vật lý của PostgreSQL và không liên quan trực tiếp đến chiến lược phân vùng dữ liệu trên disk.

## 3. Cú pháp OVER, PARTITION BY và ORDER BY

Hình dạng khái quát:

~~~hql
window_function(arguments) over (
    partition by <grouping-expression>
    order by <ordering-expression>
    <window-frame>
)
~~~

Tùy hàm, PARTITION BY, ORDER BY và frame có thể tùy chọn hoặc có ý nghĩa khác nhau. Không phải mọi hàm đều sử dụng window frame theo cách giống SUM hoặc FIRST_VALUE.

Ví dụ:

~~~hql
select
    o.id,
    o.customer.id,
    o.totalAmount,
    row_number() over (
        partition by o.customer.id
        order by o.createdAt asc, o.id asc
    )
from PurchaseOrder o
where o.status = :paid
~~~

Phân tích:

- **row_number()** tạo số thứ tự 1, 2, 3… trong từng partition.
- **over (...)** xác định tập hàng được hàm nhìn thấy.
- **partition by o.customer.id** chia các đơn theo khách hàng.
- **order by o.createdAt, o.id** xác định thứ tự của các đơn trong mỗi khách.
- **where o.status = :paid** giới hạn tập hàng đầu vào trước khi tính window.

### 3.1. Nếu không có PARTITION BY?

~~~hql
select
    o.id,
    row_number() over (order by o.createdAt, o.id)
from PurchaseOrder o
~~~

Toàn bộ tập kết quả sau lọc được xem như một partition. Số thứ tự không bắt đầu lại theo customer.

### 3.2. Nếu không có ORDER BY?

~~~hql
select o.id,
       count(o.id) over (partition by o.customer.id)
from PurchaseOrder o
~~~

COUNT theo toàn bộ partition không cần thứ tự. Ngược lại, ROW_NUMBER không có order xác định có thể đánh số theo thứ tự không ổn định. Với ranking và phép tính phụ thuộc chuỗi thời gian, **chọn ORDER BY rõ ràng và có tie-breaker**.

### 3.3. ORDER BY trong OVER khác ORDER BY của query

~~~hql
select
    o.id,
    o.customer.id,
    row_number() over (
        partition by o.customer.id
        order by o.createdAt, o.id
    )
from PurchaseOrder o
where o.status = :paid
order by o.customer.id desc, o.createdAt desc
~~~

ORDER BY bên trong OVER quyết định cách đánh số **trong từng khách**. ORDER BY ở cuối câu HQL quyết định **thứ tự hiển thị hàng kết quả**. Hai thứ tự không bắt buộc giống nhau. Không suy ra rằng ROW_NUMBER sẽ chạy theo thứ tự hàng đang hiển thị nếu thiếu ORDER BY bên trong OVER.

## 4. ROW_NUMBER: thứ tự duy nhất cho từng hàng trong nhóm

~~~hql
select
    o.customer.id,
    o.id,
    o.totalAmount,
    row_number() over (
        partition by o.customer.id
        order by o.totalAmount desc, o.id asc
    )
from PurchaseOrder o
where o.status = :paid
order by o.customer.id, o.totalAmount desc, o.id
~~~

Kết quả minh họa:

| customer_id | order_id | amount | row_number |
|---:|---:|---:|---:|
| 1 | 201 | 100.00 | 1 |
| 1 | 202 | 100.00 | 2 |
| 1 | 203 | 60.00 | 3 |
| 2 | 301 | 90.00 | 1 |
| 2 | 302 | 40.00 | 2 |

ROW_NUMBER phân biệt **từng hàng**, kể cả khi các giá trị totalAmount bằng nhau. Nhờ thêm o.id vào ORDER BY, hai đơn cùng giá trị 100.00 có thứ tự xác định. Nếu bỏ o.id, hai đơn có cùng số tiền có thể đổi chỗ giữa các lần chạy.

ROW_NUMBER phù hợp để:

- Chọn bản ghi mới nhất trong mỗi nhóm.
- Gán số thứ tự cho từng sự kiện của một tài khoản.
- Chọn đúng N hàng theo một quy tắc thứ tự.
- Loại bản ghi trùng dựa trên một business key, nếu đã xác định rõ hàng nào được giữ.

**Lưu ý:** ROW_NUMBER là giá trị tính tại thời điểm truy vấn; nó không phải ID bền vững của entity, không thay thế @Id và có thể đổi khi dữ liệu được thêm/sửa.

## 5. RANK và DENSE_RANK: xử lý các giá trị đồng hạng

Không phải báo cáo nào cũng muốn hai giao dịch cùng số tiền có thứ hạng khác nhau.

~~~hql
select
    o.customer.id,
    o.id,
    o.totalAmount,
    rank() over (
        partition by o.customer.id
        order by o.totalAmount desc
    ),
    dense_rank() over (
        partition by o.customer.id
        order by o.totalAmount desc
    )
from PurchaseOrder o
where o.status = :paid
order by o.customer.id, o.totalAmount desc, o.id
~~~

Với khách 1:

| order_id | amount | rank | dense_rank |
|---:|---:|---:|---:|
| 201 | 100.00 | 1 | 1 |
| 202 | 100.00 | 1 | 1 |
| 203 | 60.00 | 3 | 2 |

Khác biệt:

- **ROW_NUMBER:** 1, 2, 3 — không có đồng hạng.
- **RANK:** 1, 1, 3 — đồng hạng và bỏ qua thứ hạng 2.
- **DENSE_RANK:** 1, 1, 2 — đồng hạng nhưng không để khoảng trống trong chuỗi thứ hạng.

Hai đơn 201 và 202 được coi là peers (cùng giá trị ORDER BY của window RANK) vì cùng totalAmount=100.00.

### 5.1. Một lỗi logic quan trọng: đưa ID vào ORDER BY của RANK

Nếu viết:

~~~hql
rank() over (
    partition by o.customer.id
    order by o.totalAmount desc, o.id
)
~~~

thì o.id là duy nhất, nên hai đơn cùng tiền **không còn peer** trong cách xếp hạng đó. Kết quả có thể là 1, 2, 3 thay vì 1, 1, 3.

Hãy xác định ngữ nghĩa trước:

- Muốn **đồng hạng theo tiền**: chỉ sắp theo o.totalAmount trong RANK/DENSE_RANK.
- Muốn **chọn chính xác N hàng**: ROW_NUMBER với tie-breaker o.id.
- Muốn **hiển thị đồng hạng theo tiền nhưng sắp xếp hàng ổn định**: giữ ORDER BY window chỉ theo tiền và đặt ORDER BY cuối query thêm o.id.

### 5.2. Top N theo rank có thể nhiều hơn N hàng

Với các giá trị 100, 100, 60:

- ROW_NUMBER <= 2: đúng hai hàng.
- RANK <= 2: hai hàng 100; rank 3 không được lấy.
- DENSE_RANK <= 2: **ba hàng** vì lấy hai mức giá trị khác nhau, gồm cả 60.

Vì vậy cụm “top 2” phải nói rõ là **hai hàng**, **hai thứ hạng** hay **hai mức giá trị khác nhau**.

### 5.3. Các hàm xếp nhóm khác

Nhiều database và Hibernate HQL hiện đại còn hỗ trợ các analytic functions như NTILE, PERCENT_RANK và CUME_DIST. Ví dụ NTILE(4) phân phối các hàng của partition thành bốn nhóm theo thứ tự với kích thước gần nhau; PERCENT_RANK/CUME_DIST mô tả vị trí tương đối trong phân phối.

Chúng hữu ích để làm percentile band hoặc phân nhóm báo cáo. Nhưng cần phân biệt thống kê phân phối với quy tắc business ranking và kiểm tra hỗ trợ kiểu trả về/cú pháp của Hibernate version cùng dialect sử dụng.

## 6. Windowed aggregate: SUM, COUNT, AVG, MIN và MAX

GROUP BY thu gọn dữ liệu:

~~~hql
select o.customer.id, sum(o.totalAmount)
from PurchaseOrder o
where o.status = :paid
group by o.customer.id
~~~

Trong khi window aggregate giữ các đơn:

~~~hql
select
    o.id,
    o.customer.id,
    o.totalAmount,
    sum(o.totalAmount) over (
        partition by o.customer.id
    ),
    count(o.id) over (
        partition by o.customer.id
    ),
    avg(o.totalAmount) over (
        partition by o.customer.id
    )
from PurchaseOrder o
where o.status = :paid
order by o.customer.id, o.id
~~~

Với khách 1 có ba đơn 100, 100, 60:

| order_id | amount | total_by_customer | order_count | avg_amount |
|---:|---:|---:|---:|---:|
| 201 | 100.00 | 260.00 | 3 | 86.67… |
| 202 | 100.00 | 260.00 | 3 | 86.67… |
| 203 | 60.00 | 260.00 | 3 | 86.67… |

Mỗi hàng được gắn các chỉ số của partition mà nó thuộc về. COUNT(o.id) đếm số hàng có ID khác null; với entity ID không null, nó tương ứng số đơn còn lại sau WHERE và JOIN.

### 6.1. MIN/MAX trên partition

~~~hql
select
    o.id,
    o.totalAmount,
    min(o.totalAmount) over (partition by o.customer.id),
    max(o.totalAmount) over (partition by o.customer.id)
from PurchaseOrder o
where o.status = :paid
~~~

Phù hợp khi cần hiển thị giá trị của từng đơn cùng đơn nhỏ nhất/lớn nhất của khách.

### 6.2. Tỷ trọng một đơn trong tổng tiền khách

~~~hql
select
    o.id,
    o.totalAmount,
    o.totalAmount / nullif(
        sum(o.totalAmount) over (
            partition by o.customer.id
        ), 0
    )
from PurchaseOrder o
where o.status = :paid
~~~

Ý nghĩa là amount / total của khách. NULLIF tránh chia cho 0. Kiểu và độ chính xác phép chia cần được xác nhận theo numeric mapping và dialect. Nếu cần tỷ lệ phần trăm hiển thị, có thể nhân 100 và làm tròn trong DTO hoặc truy vấn theo quy tắc nghiệp vụ.

### 6.3. Null trong aggregate

Phần lớn aggregate như SUM/AVG bỏ qua giá trị NULL; COUNT(expression) chỉ đếm giá trị khác NULL. Nếu toàn bộ giá trị của một partition đều NULL, SUM/AVG có thể trả NULL; COUNT(expression) trả 0. Trong schema totalAmount non-null của ví dụ điều này không xảy ra, nhưng ở báo cáo từ dữ liệu tùy chọn phải dùng COALESCE một cách có chủ đích.

## 7. Window frame: không phải mọi hàng trong partition đều được tính

PARTITION BY xác định nhóm, ORDER BY xác định thứ tự, còn **window frame** xác định tập hàng cụ thể gần vị trí hiện tại mà các hàm có xét frame sẽ dùng.

Hình dạng:

~~~hql
over (
    partition by o.customer.id
    order by o.createdAt, o.id
    rows between unbounded preceding and current row
)
~~~

Những từ khóa phổ biến:

| Thành phần | Ý nghĩa |
|---|---|
| ROWS | Frame theo số hàng tương đối so với hàng hiện tại |
| RANGE | Frame theo giá trị/thứ tự và peer groups theo quy tắc của SQL |
| GROUPS | Frame theo nhóm các hàng đồng hạng trong thứ tự |
| UNBOUNDED PRECEDING | Từ đầu partition |
| n PRECEDING | n hàng/nhóm/đơn vị giá trị phía trước tùy frame unit |
| CURRENT ROW | Tại hàng/peer group hiện tại tùy frame unit |
| n FOLLOWING | Phía sau hàng hiện tại |
| UNBOUNDED FOLLOWING | Đến cuối partition |

Không phải mọi database/dialect đều hỗ trợ mọi frame unit hoặc offset theo cùng kiểu dữ liệu. Ví dụ dùng ROWS vì rõ và phù hợp với các phép tính theo hàng.

### 7.1. Quy tắc frame mặc định dễ gây bất ngờ

Với một window có ORDER BY nhưng không khai báo frame, nhiều database áp dụng frame mặc định tương đương:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

CURRENT ROW ở RANGE thường bao gồm cả các peers có cùng ORDER BY value. Vì vậy nếu hai đơn có cùng createdAt hoặc totalAmount, running SUM có thể **nhảy qua nhiều hàng một lúc**. Nếu muốn tích lũy từng hàng theo một thứ tự ổn định, khai báo **ROWS** rõ ràng và thêm ID làm tie-breaker.

### 7.2. ROWS và RANGE khác nhau thế nào?

Giả sử các đơn một khách có cùng ngày:

| id | created_at | amount |
|---:|---|---:|
| 201 | 2026-11-10 | 100 |
| 202 | 2026-11-10 | 50 |
| 203 | 2026-11-11 | 80 |

Nếu ORDER BY chỉ theo createdAt:

- ROWS UNBOUNDED PRECEDING CURRENT ROW có thể tích lũy 100, 150, 230 theo thứ tự thực thi giữa peers; thứ tự hai đơn ngày 10 không ổn định nếu thiếu tie-breaker.
- RANGE UNBOUNDED PRECEDING CURRENT ROW có thể cho **150 trên cả hai hàng ngày 10**, vì hai hàng là peers theo createdAt.

Để có running total từng đơn có thể lặp lại ổn định, dùng ORDER BY createdAt, id với ROWS. Để tính theo **ngày** như một đơn vị nghiệp vụ, có thể GROUP BY ngày trước rồi window trên tổng theo ngày.

## 8. Running total: tổng tiền tích lũy theo thời gian

~~~hql
select
    o.customer.id,
    o.id,
    o.createdAt,
    o.totalAmount,
    sum(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt asc, o.id asc
        rows between unbounded preceding and current row
    )
from PurchaseOrder o
where o.status = :paid
order by o.customer.id, o.createdAt, o.id
~~~

Với khách 1:

| order_id | amount | running_total |
|---:|---:|---:|
| 201 | 100.00 | 100.00 |
| 202 | 100.00 | 200.00 |
| 203 | 60.00 | 260.00 |

Với khách 2, tổng bắt đầu lại:

| order_id | amount | running_total |
|---:|---:|---:|
| 301 | 90.00 | 90.00 |
| 302 | 40.00 | 130.00 |

### 8.1. Bỏ PARTITION BY để tính tổng lũy kế toàn hệ thống

~~~hql
sum(o.totalAmount) over (
    order by o.createdAt, o.id
    rows between unbounded preceding and current row
)
~~~

Đây là một chuỗi lũy kế trên **toàn bộ tập hàng phù hợp**, không khởi động lại theo customer.

### 8.2. Tổng theo tháng khác tổng theo từng đơn

Nếu dashboard cần tổng tiền theo từng tháng rồi lũy kế, trước hết phải **gom dữ liệu về cấp tháng**. Không thể gọi running total theo từng đơn là “tổng tháng” chỉ vì hiển thị createdAt theo tháng.

Chiến lược:

1. Group các đơn theo customer + month, tính monthlyAmount.
2. Chạy SUM(monthlyAmount) OVER(PARTITION BY customer ORDER BY month) trên kết quả đã group.

Có thể biểu diễn bằng CTE/derived query ở HQL phiên bản hỗ trợ, hoặc dùng native SQL để làm rõ biểu thức date_trunc và kiểu dữ liệu tháng của PostgreSQL.

## 9. Moving average: trung bình của N hàng gần nhất

Để tính trung bình ba đơn gần nhất **bao gồm đơn hiện tại**:

~~~hql
select
    o.id,
    o.customer.id,
    o.totalAmount,
    avg(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
        rows between 2 preceding and current row
    )
from PurchaseOrder o
where o.status = :paid
~~~

Với khách có đơn tiền 100, 50, 80, 70 theo thứ tự:

| Đơn thứ | Amount | Trung bình frame |
|---:|---:|---:|
| 1 | 100 | 100.00 |
| 2 | 50 | 75.00 |
| 3 | 80 | 76.67… |
| 4 | 70 | 66.67… |

Ở đơn thứ 4, frame chứa ba đơn gần nhất 50, 80, 70 nên trung bình là 66.67…

**ROWS BETWEEN 2 PRECEDING AND CURRENT ROW** nghĩa là ba hàng cuối theo thứ tự, **không phải ba ngày cuối**. Nếu khách có mười đơn trong một ngày, frame vẫn là ba đơn, không phải tất cả đơn trong ba ngày.

### 9.1. Muốn sliding window theo thời gian thực?

Nếu yêu cầu là “tổng tiền trong bảy ngày trước thời điểm đơn”, đó là một frame theo **khoảng thời gian**, không phải số hàng. Có thể cân nhắc RANGE frame với interval trong database hỗ trợ, hoặc một truy vấn/aggregate khác, tùy Hibernate version và dialect. Không đổi ROWS 6 PRECEDING thành “bảy ngày” khi số đơn mỗi ngày không cố định.

### 9.2. Trung bình sau khi lọc dữ liệu

Nếu WHERE chỉ chọn đơn PAID, moving average sẽ nhìn thấy **các đơn PAID liền kề**, bỏ qua DRAFT/CANCELLED. Nếu muốn tính trên mọi đơn nhưng chỉ hiển thị hàng PAID, cần cấu trúc query lồng: window ở lớp trong, lọc output ở lớp ngoài. Đây là khác biệt semantics quan trọng.

## 10. LAG và LEAD: so sánh hàng trước/sau

Hàm LAG đọc biểu thức từ hàng trước trong thứ tự của partition; LEAD đọc từ hàng sau.

~~~hql
select
    o.customer.id,
    o.id,
    o.totalAmount,
    lag(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
    ),
    lead(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
    )
from PurchaseOrder o
where o.status = :paid
order by o.customer.id, o.createdAt, o.id
~~~

Khách 1:

| order_id | amount | previous_amount | next_amount |
|---:|---:|---:|---:|
| 201 | 100.00 | NULL | 100.00 |
| 202 | 100.00 | 100.00 | 60.00 |
| 203 | 60.00 | 100.00 | NULL |

Hàng đầu tiên không có hàng trước; hàng cuối cùng không có hàng sau nên kết quả có thể là NULL.

### 10.1. Chênh lệch với đơn trước

~~~hql
select
    o.id,
    o.totalAmount,
    o.totalAmount - lag(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
    )
from PurchaseOrder o
where o.status = :paid
~~~

Đối với đơn đầu tiên của mỗi khách, kết quả phép trừ là NULL. Nếu business muốn coi chênh lệch đầu kỳ bằng 0 thì dùng COALESCE có chủ đích; không tự coi NULL là zero khi NULL mang ý nghĩa “chưa có kỳ trước”.

### 10.2. LAG/LEAD không giống Java List.get(index - 1)

Database thực hiện tính toán sau khi đã áp dụng các filter/grouping của query. Nó không buộc ứng dụng phải tải toàn bộ lịch sử đơn rồi sắp xếp trong Java. Với dữ liệu lớn, lợi ích là đẩy phép tính cạnh nhau về database, dù database vẫn có thể cần sort partition.

## 11. FIRST_VALUE và LAST_VALUE: phải hiểu frame

FIRST_VALUE lấy giá trị của hàng đầu tiên trong frame; LAST_VALUE lấy giá trị của hàng cuối trong frame.

~~~hql
select
    o.id,
    first_value(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
        rows between unbounded preceding and unbounded following
    ),
    last_value(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
        rows between unbounded preceding and unbounded following
    )
from PurchaseOrder o
where o.status = :paid
~~~

Frame được khai báo từ đầu đến cuối partition để LAST_VALUE biểu diễn **giá trị của đơn cuối cùng**, không phải đơn hiện tại.

### 11.1. Bẫy LAST_VALUE với frame mặc định

Nếu viết:

~~~hql
last_value(o.totalAmount) over (
    partition by o.customer.id
    order by o.createdAt, o.id
)
~~~

frame mặc định có thể kết thúc ở hàng hiện tại/peer group. LAST_VALUE khi đó thường trả về giá trị của **hàng hiện tại hoặc peer cuối của nó**, chứ không phải giá trị của đơn cuối cùng trong toàn partition.

Muốn lấy giá trị của hàng cuối partition, hãy dùng frame kết thúc bằng UNBOUNDED FOLLOWING khi được database/dialect hỗ trợ.

### 11.2. FIRST_VALUE và MIN không đồng nghĩa

FIRST_VALUE(o.totalAmount) theo createdAt lấy tiền của đơn đầu tiên trong thời gian. MIN(o.totalAmount) lấy số tiền nhỏ nhất. Hai giá trị có thể khác nhau. Chọn hàm theo ngữ nghĩa business, không đổi qua lại chỉ vì cả hai đều trả một con số cho mỗi nhóm.

## 12. Thứ tự xử lý logic của query rất quan trọng

Một mô hình khái quát cho query SELECT:

~~~text
FROM / JOIN
    ↓
WHERE
    ↓
GROUP BY / Aggregate / HAVING
    ↓
Window expressions
    ↓
SELECT / DISTINCT
    ↓
ORDER BY ngoài
    ↓
OFFSET / FETCH / LIMIT
~~~

Đây là **thứ tự logic để suy luận kết quả**, không phải thứ tự vật lý mà optimizer bắt buộc phải thực thi từng bước.

Hệ quả:

- WHERE ảnh hưởng các hàng tham gia vào partition.
- GROUP BY nếu có làm thay đổi độ hạt của các hàng đầu vào window.
- Window expression thường không được phép xuất hiện trực tiếp trong WHERE của **cùng query block**.
- ORDER BY ngoài sắp xếp kết quả hiển thị; nó không tự quyết định ORDER BY trong OVER.
- LIMIT/OFFSET ngoài xảy ra sau khi các biểu thức window của query block được tính theo semantics SQL, nên không có nghĩa database chỉ phải window trên N hàng được hiển thị.

### 12.1. Không lọc ROW_NUMBER trực tiếp trong WHERE cùng cấp

Ví dụ không hợp lệ trong query block thông thường:

~~~hql
select o
from PurchaseOrder o
where row_number() over (
    partition by o.customer.id
    order by o.totalAmount desc
) <= 2
~~~

Window function không thuộc điều kiện WHERE ở cùng tầng. Cần **subquery/derived table hoặc CTE**: tính ROW_NUMBER ở lớp trong, rồi lọc giá trị vừa tính ở lớp ngoài.

## 13. Top N per group bằng HQL derived query

Yêu cầu: lấy **đúng hai đơn PAID có tổng tiền lớn nhất cho mỗi khách**. Nếu hai đơn có cùng số tiền, dùng ID tăng dần làm tie-breaker để chọn chính xác hai hàng.

Một dạng HQL hiện đại dùng derived root:

~~~hql
select
    ranked.customerId,
    ranked.orderId,
    ranked.amount,
    ranked.rowPos
from (
    select
        o.customer.id as customerId,
        o.id as orderId,
        o.totalAmount as amount,
        row_number() over (
            partition by o.customer.id
            order by o.totalAmount desc, o.id asc
        ) as rowPos
    from PurchaseOrder o
    where o.status = :paid
) ranked
where ranked.rowPos <= :topN
order by ranked.customerId, ranked.rowPos
~~~

Đây là **HQL mở rộng**, không phải một JPQL query bảo đảm portable với mọi provider. Khả năng sử dụng derived root trong FROM và window expression phụ thuộc Hibernate version; cần thử trên phiên bản ứng dụng.

Kết quả với topN=2:

| customer_id | order_id | amount | row_pos |
|---:|---:|---:|---:|
| 1 | 201 | 100.00 | 1 |
| 1 | 202 | 100.00 | 2 |
| 2 | 301 | 90.00 | 1 |
| 2 | 302 | 40.00 | 2 |

### 13.1. Vì sao không lấy tất cả về Java rồi group/sort?

Cách naive:

~~~java
List<PurchaseOrder> allPaidOrders = repository.findAllPaid();

Map<Long, List<PurchaseOrder>> topTwo = allPaidOrders.stream()
    .collect(Collectors.groupingBy(o -> o.getCustomer().getId(),
        Collectors.collectingAndThen(
            Collectors.toList(),
            list -> list.stream()
                .sorted(Comparator.comparing(
                    PurchaseOrder::getTotalAmount).reversed())
                .limit(2)
                .toList()
        )));
~~~

Code này cần tải mọi đơn PAID, có thể tạo một graph rất lớn trong heap, và có thể phát thêm query lazy cho customer. Với hàng triệu đơn, đẩy top-N-per-group về database thường hợp lý hơn.

### 13.2. Phân biệt top-N theo thứ tự và top-N theo hạng

Để **lấy tất cả đơn đồng hạng cao nhất**, dùng RANK hoặc DENSE_RANK trong lớp trong thay ROW_NUMBER. Nhưng số hàng có thể lớn hơn N. Business phải chọn:

- **ROW_NUMBER <= N**: tối đa N hàng mỗi nhóm.
- **RANK <= N**: thứ hạng theo vị trí có khoảng trống khi đồng hạng.
- **DENSE_RANK <= N**: N mức giá trị/hạng phân biệt, có thể trả nhiều hơn N hàng.

Không thêm ID vào ORDER BY window của RANK nếu muốn bảo toàn đồng hạng theo amount; chỉ thêm ID ở ORDER BY kết quả ngoài để giữ trình tự hiển thị.

### 13.3. SQL tương đương khi cần native query

PostgreSQL:

~~~sql
SELECT customer_id, order_id, amount, row_pos
FROM (
    SELECT
        o.customer_id,
        o.id AS order_id,
        o.total_amount AS amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.total_amount DESC, o.id ASC
        ) AS row_pos
    FROM purchase_orders o
    WHERE o.status = 'PAID'
) ranked
WHERE ranked.row_pos <= 2
ORDER BY customer_id, row_pos;
~~~

Native SQL dùng tên bảng/cột thật. Nếu HQL version chưa hỗ trợ derived root hoặc cú pháp window mong muốn, query native là một lựa chọn rõ ràng; phải bind parameter, ánh xạ kết quả và kiểm thử trên dialect mục tiêu.

## 14. GROUP BY trước window: tổng hợp ở hai cấp độ

Giả sử muốn:

1. Tổng tiền theo **trạng thái** của từng khách.
2. Tổng tiền của **mọi trạng thái** của khách ấy trên từng hàng tổng hợp.

Đây là bài toán hai độ hạt: đầu tiên group theo (customer, status), sau đó window trên những hàng đã group.

SQL PostgreSQL minh họa:

~~~sql
WITH grouped AS (
    SELECT
        customer_id,
        status,
        SUM(total_amount) AS subtotal
    FROM purchase_orders
    GROUP BY customer_id, status
)
SELECT
    customer_id,
    status,
    subtotal,
    SUM(subtotal) OVER (
        PARTITION BY customer_id
    ) AS customer_total
FROM grouped
ORDER BY customer_id, status;
~~~

HQL hiện đại có thể biểu diễn bài toán tương tự bằng derived query hoặc CTE khi version hỗ trợ:

~~~hql
select
    grouped.customerId,
    grouped.orderStatus,
    grouped.subtotal,
    sum(grouped.subtotal) over (
        partition by grouped.customerId
    )
from (
    select
        o.customer.id as customerId,
        o.status as orderStatus,
        sum(o.totalAmount) as subtotal
    from PurchaseOrder o
    group by o.customer.id, o.status
) grouped
order by grouped.customerId, grouped.orderStatus
~~~

Lưu ý:

- Window SUM ở lớp ngoài chạy trên **hàng tổng hợp**, không trực tiếp trên từng PurchaseOrder.
- Nếu muốn chỉ tính đơn PAID, phải đặt filter ở lớp đúng ngữ nghĩa.
- Nếu cần tỷ trọng từng trạng thái, có thể lấy subtotal chia customerTotal.
- Một số HQL extension về derived table/CTE thay đổi theo Hibernate version; đừng mặc định cú pháp native SQL và HQL luôn hoán đổi được.

### 14.1. Không nhầm hai dạng tổng hợp

~~~hql
sum(o.totalAmount) over (partition by o.customer.id)
~~~

trả tổng của khách trên **mỗi hàng đơn**.

~~~hql
select o.customer.id, sum(o.totalAmount)
from PurchaseOrder o
group by o.customer.id
~~~

trả **một hàng cho mỗi khách**. Chọn theo độ hạt của report cần hiển thị.

## 15. Tham số, điều kiện WHERE và nghiệp vụ thời gian

Truy vấn chạy trong một khoảng:

~~~hql
select
    o.id,
    o.customer.id,
    sum(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
        rows between unbounded preceding and current row
    )
from PurchaseOrder o
where o.status = :paid
  and o.createdAt >= :fromTime
  and o.createdAt < :toTime
~~~

Đây là running total **chỉ trong khoảng thời gian được chọn**, vì WHERE lọc dữ liệu trước window. Nó **không phải** tổng lũy kế từ ngày khách có đơn đầu tiên nếu fromTime nằm giữa lịch sử.

Nếu báo cáo muốn hiển thị các đơn của tháng 11 nhưng running total bắt đầu từ ngày đầu tiên của khách, phải tính window trên toàn bộ lịch sử phù hợp ở lớp trong rồi **lọc thời gian hiển thị ở lớp ngoài**. Tránh gọi cả hai phép tính bằng cùng tên cumulativeAmount.

### 15.1. Bind named parameters

~~~java
List<Tuple> result = entityManager.createQuery("""
    select
        o.id as orderId,
        o.totalAmount as amount,
        sum(o.totalAmount) over (
            partition by o.customer.id
            order by o.createdAt, o.id
            rows between unbounded preceding and current row
        ) as runningAmount
    from PurchaseOrder o
    where o.status = :paid
      and o.createdAt >= :fromTime
      and o.createdAt < :toTime
    order by o.customer.id, o.createdAt, o.id
    """, Tuple.class)
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("fromTime", fromTime)
    .setParameter("toTime", toTime)
    .getResultList();
~~~

HQL dùng attribute names; Hibernate bind enum và Instant theo mapping. Đừng ghép trực tiếp tham số user input vào HQL string.

### 15.2. Multi-tenant và phạm vi truy cập

Nếu dữ liệu là multi-tenant, điều kiện tenant phải được áp dụng **trước khi window** để tránh cộng dữ liệu của các tenant khác vào partition. Chỉ dùng customerId làm partition khi ID có semantics duy nhất trong scope được truy vấn. Một khóa partition có thể cần cả tenantId lẫn customerId:

~~~hql
partition by o.tenantId, o.customer.id
~~~

Đây là ví dụ với giả định PurchaseOrder có persistent attribute tenantId. Ngoài phép tính, service vẫn cần authorization và tenant isolation đầy đủ; PARTITION BY không phải cơ chế kiểm soát quyền.

## 16. Tích hợp với EntityManager và DTO/Tuple

Window queries thường chọn nhiều scalar expression nên trả kết quả DTO thay vì toàn bộ entity graph.

### 16.1. Typed Tuple

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.Tuple;
import java.math.BigDecimal;
import java.util.List;

List<Tuple> rows = entityManager.createQuery("""
    select
        o.id as orderId,
        o.customer.id as customerId,
        o.totalAmount as amount,
        row_number() over (
            partition by o.customer.id
            order by o.createdAt, o.id
        ) as rowNo,
        sum(o.totalAmount) over (
            partition by o.customer.id
            order by o.createdAt, o.id
            rows between unbounded preceding and current row
        ) as runningAmount
    from PurchaseOrder o
    where o.status = :paid
    order by o.customer.id, o.createdAt, o.id
    """, Tuple.class)
    .setParameter("paid", OrderStatus.PAID)
    .getResultList();

for (Tuple row : rows) {
    Long orderId = row.get("orderId", Long.class);
    Long customerId = row.get("customerId", Long.class);
    BigDecimal amount = row.get("amount", BigDecimal.class);
    Long rowNo = row.get("rowNo", Long.class);
    BigDecimal running = row.get("runningAmount", BigDecimal.class);
}
~~~

Kiểu Java mà Hibernate trả về cho từng hàm phụ thuộc chữ ký function, expression mapping và dialect. ROW_NUMBER thường dùng kiểu số nguyên đủ rộng như Long; trước khi khai báo DTO production, hãy xác nhận typed result trên Hibernate version sử dụng.

### 16.2. Constructor projection

Một DTO:

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;

public record OrderRunningTotal(
    Long orderId,
    Long customerId,
    BigDecimal amount,
    Long sequenceNo,
    BigDecimal runningAmount
) {}
~~~

HQL:

~~~hql
select new com.example.shop.dto.OrderRunningTotal(
    o.id,
    o.customer.id,
    o.totalAmount,
    row_number() over (
        partition by o.customer.id
        order by o.createdAt, o.id
    ),
    sum(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
        rows between unbounded preceding and current row
    )
)
from PurchaseOrder o
where o.status = :paid
~~~

Constructor expression yêu cầu thứ tự và kiểu của các biểu thức khớp với DTO constructor. Nếu dialect trả một numeric type khác dự kiến hoặc function type không suy luận được, cần điều chỉnh query/mapping và test runtime; không ép kiểu bằng Java cast mù quáng.

### 16.3. Spring service và transaction read-only

~~~java
@Service
public class OrderAnalyticsService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<OrderRunningTotal> findRunningTotals() {
        return entityManager.createQuery("""
            select new com.example.shop.dto.OrderRunningTotal(
                o.id,
                o.customer.id,
                o.totalAmount,
                row_number() over (
                    partition by o.customer.id
                    order by o.createdAt, o.id
                ),
                sum(o.totalAmount) over (
                    partition by o.customer.id
                    order by o.createdAt, o.id
                    rows between unbounded preceding and current row
                )
            )
            from PurchaseOrder o
            where o.status = :status
            order by o.customer.id, o.createdAt, o.id
            """, OrderRunningTotal.class)
            .setParameter("status", OrderStatus.PAID)
            .getResultList();
    }
}
~~~

Ví dụ giả định đã import Service, PersistenceContext, Transactional và EntityManager. Trả DTO tránh để web layer vô tình trigger lazy loading. readOnly=true là gợi ý transaction/flush optimization tùy framework, không phải biện pháp hạn chế quyền ghi ở database trong mọi cấu hình.

### 16.4. Chỉ trả đúng dữ liệu cần thiết

Nếu use case chỉ cần báo cáo scalar, việc SELECT PurchaseOrder entity rồi ánh xạ trong Java có thể tăng memory và first-level cache. Constructor projection/Tuple giúp Hibernate không phải hydrate mọi entity. Tuy nhiên kết quả window query có thể vẫn rất lớn; cần giới hạn theo filter, ngày, tenant hoặc sử dụng batch/streaming phù hợp.

## 17. Tương thích Hibernate, JPQL và database dialect

Một số điểm cần phân biệt:

| Tầng | Vai trò |
|---|---|
| HQL parser và semantic model | Nhận diện entity, thuộc tính, function và OVER |
| Hibernate SQL AST/translator | Dịch biểu thức window thành SQL dialect hỗ trợ |
| JDBC | Bind tham số, nhận các hàng kết quả |
| PostgreSQL | Thực thi window function, sắp xếp partition và tính aggregate |
| Jakarta Persistence API | Tạo Query/TypedQuery, quản lý kết quả và transaction |

HQL window function là tính năng của **Hibernate ORM hiện đại, đặc biệt dòng 6.x**. JPQL chuẩn của những phiên bản Jakarta Persistence được dùng phổ biến không nên được giả định có cùng toàn bộ cú pháp window/derived table như HQL. Đừng viết query rồi mong đổi sang provider khác không cần chỉnh sửa.

### 17.1. Khi nào dùng HQL?

HQL phù hợp nếu:

- Project đã cam kết dùng Hibernate.
- Cần truy vấn dựa trên entity/association thay vì tên bảng.
- Hàm window và derived root được phiên bản Hibernate mục tiêu hỗ trợ.
- Hình dạng SQL sinh ra đủ rõ, có test và plan phù hợp.

### 17.2. Khi nào dùng native SQL?

Native SQL đáng cân nhắc nếu:

- Cần PostgreSQL-specific frame, FILTER, NULL treatment hoặc function HQL version hiện tại chưa biểu diễn được.
- Cần materialized CTE, optimizer hint hay xử lý dữ liệu báo cáo đặc thù.
- Query phân tích phức tạp được nhóm database tối ưu trực tiếp bằng SQL.

Native query sử dụng tên bảng/cột vật lý. Khi trả về DTO, cần result mapping/constructor projection phù hợp; không mặc định native SQL tự hiểu entity property paths.

### 17.3. H2 không luôn đại diện PostgreSQL

Integration test window SQL nên chạy trên cùng DB/dialect dùng thực tế, ví dụ PostgreSQL trong Testcontainers. H2 có thể chấp nhận một phần cú pháp nhưng có khác biệt ở ORDER BY NULL, frame, kiểu dữ liệu và function. Test pass trên H2 không chứng minh query HQL sẽ sinh SQL đúng trên PostgreSQL.

## 18. Window functions khác Hibernate collection fetching

Hai chữ "window" trong SQL analytics không liên quan đến window phân trang UI, và OVER không phải FETCH JOIN.

Một câu:

~~~hql
select
    o.id,
    count(o.id) over (partition by o.customer.id)
from PurchaseOrder o
~~~

vẫn là scalar query trên PurchaseOrder. Nó không yêu cầu Hibernate tải collection o.items hoặc o.customer.orders.

Nếu đưa join collection vào:

~~~hql
select
    o.id,
    count(o.id) over (partition by o.customer.id)
from PurchaseOrder o
join o.items i
~~~

thì mỗi Order xuất hiện nhiều lần trước phép window, làm COUNT và ranking có thể **sai ngữ nghĩa**. Ví dụ một đơn có 5 items tạo 5 hàng đầu vào; count(o.id) over có thể đếm 5 lần thay vì 1 đơn.

### 18.1. Cách tránh nhân bản đầu vào window

- Chỉ query root PurchaseOrder khi phép tính ở cấp đơn.
- Nếu cần lọc đơn theo sự tồn tại của item, dùng EXISTS thay vì JOIN sinh duplicate.
- Nếu phải dùng JOIN cho báo cáo theo item, xác định độ hạt là item và tính window ở cấp item.
- Nếu cần aggregate items lên cấp order, GROUP BY trước trong query lồng rồi mới window trên các hàng order.

**Nguyên tắc:** window function không tự sửa cardinality sai do JOIN. Trước khi chọn PARTITION BY hãy xác định **mỗi hàng đầu vào đại diện cho thực thể/sự kiện nào**.

### 18.2. Vì sao không kết hợp collection fetch join và phân trang chỉ để lấy rank?

Một query fetch join items và phân trang PurchaseOrder có thể khiến Hibernate phải nạp mọi hàng joined rồi phân trang trong bộ nhớ. Window function không giải quyết vấn đề này. Nếu chỉ cần top-N/rank, chọn scalar projection; nếu cần chi tiết collection của N order, trước hết chọn N order ID rồi fetch association trong query thứ hai.

## 19. Giới hạn dữ liệu và chi phí thực thi

Window functions thường cần sắp xếp theo PARTITION BY và ORDER BY. Với tập dữ liệu rất lớn, database có thể phải sort nhiều hàng, dùng memory và spill ra disk.

Các yếu tố làm truy vấn chậm:

- Không có filter thời gian/status/tenant phù hợp.
- PARTITION BY trên key có rất nhiều hàng.
- ORDER BY theo biểu thức phức tạp hoặc không có index hỗ trợ.
- Nhiều window definitions khác nhau khiến optimizer phải sắp xếp nhiều lần.
- JOIN collection làm nhân số hàng trước window.
- Trả hàng triệu kết quả về application và map thành DTO không cần thiết.
- Câu query lồng ở top-N per group phải tính ranking trên rất nhiều hàng trước khi lọc.

### 19.1. Index hỗ trợ query

Nếu running total thường phân theo customer và thứ tự thời gian:

~~~sql
CREATE INDEX idx_orders_customer_created_id
ON purchase_orders(customer_id, created_at, id);
~~~

Nếu query chỉ lấy đơn PAID và database thường lọc theo status:

~~~sql
CREATE INDEX idx_orders_status_customer_created_id
ON purchase_orders(status, customer_id, created_at, id);
~~~

Với ranking theo tiền:

~~~sql
CREATE INDEX idx_orders_customer_amount_id
ON purchase_orders(customer_id, total_amount DESC, id);
~~~

Không tạo cả ba index theo thói quen; mỗi index tăng chi phí INSERT/UPDATE và storage. Chọn theo truy vấn thường xuyên, phân bố dữ liệu, filter và execution plan thực tế.

### 19.2. Index không biến mọi window query thành O(N nhỏ)

Index có thể giúp database đọc theo thứ tự và giảm sort, nhưng truy vấn tính rank/tổng cho **mọi đơn của mỗi khách** vẫn có thể phải xét nhiều hàng để trả kết quả. Lấy top-2 per group bằng ROW_NUMBER thường không tự tương đương “chỉ đọc hai hàng đầu của mỗi index partition” trên mọi plan.

Muốn giảm khối lượng xử lý:

- Lọc trước theo tenant/status/date nếu nghiệp vụ cho phép.
- Chỉ chọn thuộc tính cần cho report.
- Tách danh sách parent cần quan tâm nếu có giới hạn rõ ràng.
- Dùng bảng tổng hợp/materialized view cập nhật theo lịch khi report lớn và chấp nhận dữ liệu trễ.
- Xây read model hoặc pre-aggregation riêng cho dashboard có lưu lượng cao.

### 19.3. Pagination sau window

~~~hql
select
    o.id,
    row_number() over (
        partition by o.customer.id
        order by o.createdAt, o.id
    )
from PurchaseOrder o
order by o.id
~~~

Thêm setMaxResults(20) vào query kiểu này giới hạn kết quả trả về, **không bảo đảm database chỉ phải đánh số 20 hàng**. Cần xem plan: ORDER BY/window có thể yêu cầu xử lý nhiều dữ liệu trước khi LIMIT có hiệu lực.

Nếu chỉ cần trang danh sách, đừng tính window quá rộng khi không cần. Nếu cần top-N per group, dùng derived root và filter rank đúng nghĩa thay vì page chung.

## 20. Đo SQL thật và giải thích execution plan

### 20.1. Cấu hình logging khi học

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Chỉ bật bind TRACE ở môi trường an toàn vì có thể làm lộ thông tin khách hàng hoặc dữ liệu giao dịch. Không dùng logging parameter nhạy cảm mặc định ở production.

HQL:

~~~hql
select
    o.id,
    sum(o.totalAmount) over (
        partition by o.customer.id
        order by o.createdAt, o.id
        rows between unbounded preceding and current row
    )
from PurchaseOrder o
where o.status = :status
~~~

SQL minh họa:

~~~sql
SELECT
    o.id,
    SUM(o.total_amount) OVER (
        PARTITION BY o.customer_id
        ORDER BY o.created_at, o.id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
FROM purchase_orders o
WHERE o.status = ?;
~~~

Điểm khác: HQL dùng entity property totalAmount, customer.id, createdAt; SQL dùng cột total_amount, customer_id, created_at. SQL thật có thể có thêm join, alias hoặc xử lý kiểu dữ liệu tùy mapping.

### 20.2. PostgreSQL EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.id,
    SUM(o.total_amount) OVER (
        PARTITION BY o.customer_id
        ORDER BY o.created_at, o.id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM purchase_orders o
WHERE o.status = 'PAID'
ORDER BY o.customer_id, o.created_at, o.id;
~~~

Quan sát:

- Node WindowAgg xử lý phép window.
- Sort hoặc Incremental Sort có xuất hiện không.
- Actual rows, loops và Estimated rows.
- Buffers hit/read; có spill ra disk/tệp temporary không.
- Tổng execution time và số hàng trả về.
- Kế hoạch sử dụng index có phù hợp bộ lọc và ORDER BY không.

EXPLAIN ANALYZE thực thi truy vấn SELECT thật; chỉ chạy với dữ liệu phù hợp và theo chính sách môi trường. SQL window function có thể dùng nhiều memory tại database ngay cả khi ứng dụng chỉ nhận vài cột scalar.

### 20.3. Hibernate Statistics không đo toàn bộ window cost

Hibernate Statistics có số statement, entity load, query execution, nhưng **không tự cung cấp thời gian Sort/WindowAgg hoặc số hàng intermediate** trong database. Để tối ưu thực sự, cần kết hợp Hibernate SQL log với PostgreSQL EXPLAIN, pg_stat_statements/metrics DB và latency của endpoint.

## 21. Các lỗi thường gặp khi viết HQL window function

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Parser báo không hiểu OVER | Hibernate version/cú pháp HQL chưa hỗ trợ | Kiểm tra version; nâng cấp hoặc native SQL |
| Dùng tên bảng purchase_orders trong HQL | HQL truy vấn entity, không phải bảng vật lý | Dùng PurchaseOrder |
| Dùng total_amount trong HQL | Nhầm tên cột với persistent attribute | Dùng o.totalAmount |
| ROW_NUMBER thay đổi giữa các lần chạy | ORDER BY thiếu tie-breaker | Thêm o.id vào ROW_NUMBER ORDER BY |
| RANK không có đồng hạng dù số tiền bằng nhau | Đã thêm ID vào ORDER BY của RANK | Chỉ dùng khóa quyết định đồng hạng trong window rank |
| RANK nhảy từ 1 sang 3 | Đúng semantics khi có hai hàng đồng hạng 1 | Dùng DENSE_RANK nếu muốn hạng liên tục |
| Tổng lũy kế nhảy nhiều hàng cùng lúc | Frame mặc định RANGE gồm peer group | Khai báo ROWS và thứ tự ổn định |
| LAST_VALUE luôn giống giá trị hiện tại | Frame kết thúc tại current row/peers | Dùng UNBOUNDED FOLLOWING nếu cần cuối partition |
| Cùng khách bị cộng cả đơn CANCELLED | WHERE/filter nghiệp vụ sai | Lọc đúng tập đầu vào trước window |
| Tổng tiền của khách khác bị lẫn | PARTITION BY thiếu khóa tenant/customer | Xác định đúng partition keys và authorization |
| COUNT window lớn hơn số đơn thực tế | JOIN collection nhân các hàng order | Dùng root query/EXISTS hoặc aggregate trước |
| Không dùng được window trong WHERE | Window không khả dụng trong cùng query block tại WHERE | Derived query/CTE và filter lớp ngoài |
| Top-2 trả quá nhiều hàng | Dùng DENSE_RANK/RANK thay ROW_NUMBER | Xác định semantics top-N |
| HQL query DTO báo constructor type mismatch | Kiểu/alias/constructor không khớp | Kiểm tra typed result và Java DTO |
| Query chậm dù chỉ LIMIT 20 | Window/Sort xử lý nhiều hàng trước LIMIT | Giới hạn nguồn, index và xem execution plan |
| Native SQL chạy nhưng HQL không parse | Cú pháp DB-specific không thuộc grammar HQL | Dùng HQL đúng version hoặc native query |
| Running total trong tháng không cộng lịch sử trước tháng | WHERE lọc trước window | Tính toàn lịch sử trong query lồng, lọc hiển thị ngoài |

## 22. Kiểm thử window functions trên dữ liệu có chủ đích

Không chỉ test dữ liệu mỗi khách có một đơn. Những tình huống biên mới cho thấy rõ sự khác nhau giữa các hàm:

| Trường hợp | Cần kiểm tra |
|---|---|
| Khách A có 100, 100, 60 | ROW_NUMBER=1,2,3; RANK=1,1,3; DENSE_RANK=1,1,2 |
| Khách B có 90, 40 | Các thứ hạng bắt đầu lại từ 1 |
| Hai đơn cùng createdAt | Thứ tự có ID tie-breaker ổn định |
| Khách không có đơn | Không xuất hiện trong query root PurchaseOrder trừ khi query Customer theo outer join |
| Partition chỉ một hàng | COUNT=1, LAG/LEAD có thể NULL |
| Moving AVG với chưa đủ N hàng | Frame chỉ chứa những hàng thực có |
| LAST_VALUE | Frame full partition trả đúng hàng cuối |
| Có đơn CANCELLED | Filter thay đổi tập hàng vào window |
| Một đơn có nhiều OrderItem | Không vô tình đếm/nối nhiều lần khi analytics ở cấp order |
| Multi-tenant | Partition và filter không trộn dữ liệu tenant |
| Numeric lớn và precision | Tổng tiền không tràn/không bị làm tròn ngoài quy tắc |
| NULL amount hoặc NULL timestamp nếu mapping cho phép | Null handling và sort được xác định rõ |

### 22.1. Integration test với PostgreSQL

Một skeleton:

~~~java
@SpringBootTest
class HqlWindowFunctionIntegrationTest {
    @Autowired EntityManagerFactory emf;

    @Test
    void ranksOrdersWithinEachCustomer() {
        // Arrange: persist khách 1 với số tiền 100, 100, 60.
        // Persist khách 2 với số tiền 90, 40.
        // Commit fixture và dùng EntityManager mới.

        // Act: chạy HQL chọn ROW_NUMBER, RANK, DENSE_RANK.

        // Assert:
        // - Khách 1: row number 1,2,3.
        // - Khách 1: rank 1,1,3; dense rank 1,1,2.
        // - Khách 2: rank bắt đầu lại từ 1.
        // - Kết quả không phụ thuộc thứ tự INSERT ngoài ORDER BY.
    }
}
~~~

Skeleton này cần các import, fixture và transaction phù hợp. Dùng PostgreSQL Testcontainers hoặc database thật đại diện cho production để kiểm tra Hibernate translator và window frame; không mặc định H2 tương đương.

### 22.2. Test running total

Với khách 1 có các đơn theo thời gian 100, 100, 60:

~~~text
expected running totals = [100.00, 200.00, 260.00]
~~~

Thêm một đơn CANCELLED xen vào và xác định rõ có muốn tính đơn đó hay không. Nếu HQL lọc PAID ở WHERE, đơn CANCELLED không được tham gia bất kỳ window sum nào trong query.

### 22.3. Test kết quả khi filter ở hai lớp

Chạy hai query:

1. WHERE thời gian ở cùng query block với window.
2. Window chạy trong derived query trên lịch sử đầy đủ, WHERE thời gian ở query ngoài.

Assert running total khác nhau ở đơn đầu của khoảng được hiển thị. Đây là lỗi nghiệp vụ thường xuất hiện khi code báo cáo được tối ưu hoặc thêm filter từ UI mà không làm rõ semantics.

### 22.4. Test top-N với dữ liệu đồng hạng

Với hai đơn cùng 100 và đơn thứ ba 60:

- ROW_NUMBER <= 2 phải lấy đúng hai hàng.
- DENSE_RANK <= 2 phải lấy cả ba hàng.

Đây không phải lỗi SQL; đó là sự khác nhau giữa hai định nghĩa “top 2”. Test phải phản ánh yêu cầu business đã chọn.

## 23. Bài thực hành tổng hợp

### Bài A — Xếp hạng cơ bản

1. Tạo ít nhất ba khách; mỗi khách có 3–5 đơn PAID.
2. Cho hai đơn của một khách có cùng totalAmount.
3. Viết HQL chọn ROW_NUMBER, RANK và DENSE_RANK theo totalAmount DESC.
4. Giải thích tại sao hai đơn có cùng amount đồng hạng trong RANK nhưng không trong ROW_NUMBER.
5. Thêm o.id vào ORDER BY của ROW_NUMBER, không thêm vào RANK nếu muốn đồng hạng.

### Bài B — Tổng hợp theo partition

1. Tính SUM/COUNT/AVG theo customer nhưng vẫn giữ mỗi order.
2. So sánh với GROUP BY chỉ trả một hàng mỗi khách.
3. Tính tỷ trọng amount / customerTotal bằng NULLIF để tránh chia cho 0.
4. Kiểm tra tổng trên mỗi khách khác nhau và không bị rò rỉ giữa tenant.

### Bài C — Running total và moving average

1. Tính SUM theo createdAt/id với ROWS UNBOUNDED PRECEDING CURRENT ROW.
2. Tạo hai đơn cùng createdAt; thử bỏ ID tie-breaker rồi quan sát tính không ổn định.
3. So sánh ROWS và RANGE khi hai hàng có cùng sort key.
4. Tính AVG 3 đơn gần nhất bằng ROWS BETWEEN 2 PRECEDING AND CURRENT ROW.
5. Nêu khác biệt với yêu cầu “ba ngày gần nhất”.

### Bài D — LAG, LEAD và LAST_VALUE

1. Trả amount của đơn trước và sau trong cùng customer.
2. Tính delta với previousAmount.
3. Kiểm tra NULL ở hàng đầu/cuối.
4. Dùng LAST_VALUE với và không có full-partition frame.
5. Giải thích vì sao FIRST_VALUE không tương đương MIN.

### Bài E — Top N per group

1. Viết derived HQL query tính ROW_NUMBER ở lớp trong.
2. Chỉ lấy hàng có rowPos <= :topN ở lớp ngoài.
3. Đổi sang DENSE_RANK để hiểu trường hợp đồng hạng.
4. So sánh với phương án tải mọi đơn về Java rồi stream/group/sort.
5. Kiểm tra execution plan, số hàng DB xử lý và memory ứng dụng.

### Bài F — GROUP BY rồi WINDOW

1. Gom đơn theo customer/status, tính subtotal.
2. Dùng window SUM trên các subtotal để tính tổng theo customer.
3. Tính tỷ trọng mỗi trạng thái trong tổng.
4. So sánh ngữ nghĩa với window trên từng order.
5. Nếu HQL version thiếu derived root/CTE cần thiết, viết native SQL tương đương và ghi rõ lý do.

### Bài G — Kiểm thử và tối ưu

1. Bật Hibernate SQL logger trong môi trường test.
2. Chạy EXPLAIN ANALYZE cho running total và top-N.
3. Thêm index theo customer/createdAt/id, quan sát plan.
4. Tạo một khách có rất nhiều đơn để quan sát chi phí partition lớn.
5. Thử JOIN OrderItem trước window, xác định vì sao COUNT sai.
6. Chuyển sang EXISTS hoặc group trước window và xác nhận kết quả đúng.

## 24. Checklist thiết kế một báo cáo window function

Trước khi đưa query HQL analytics vào production, trả lời:

1. **Độ hạt đầu vào là gì?** Một hàng đại diện Order, OrderItem, Customer hay tổng theo tháng?
2. **Partition key là gì?** Customer, tenant, status, tháng hay tổ hợp của chúng?
3. **Sắp xếp theo gì?** Có tie-breaker để ROW_NUMBER/LAG/LEAD ổn định không?
4. **Đồng hạng có ý nghĩa không?** Dùng ROW_NUMBER, RANK hay DENSE_RANK?
5. **Frame là toàn partition hay một khoảng?** ROWS/RANGE/GROUPS khác nhau như thế nào?
6. **WHERE lọc trước hay sau window?** Có vô tình thay đổi tổng lũy kế không?
7. **Có join collection gây nhân bản hàng không?** Query đang tính ở cấp Order hay Item?
8. **Có dữ liệu NULL/currency/hoàn tiền cần xử lý riêng không?**
9. **Output là scalar/DTO hay entity?** Tránh hydrate graph không cần thiết.
10. **Hibernate version/dialect có hỗ trợ cú pháp không?** Có test trên DB thật?
11. **Dữ liệu có quá lớn không?** Có filter, index, read model hoặc pre-aggregation phù hợp?
12. **Có xác nhận SQL plan và latency p95/p99 không?** Đừng chỉ đánh giá từ một dataset nhỏ.

## 25. Nguyên tắc ghi nhớ

Window function làm phép tính trên những hàng liên quan mà không tự động gộp toàn bộ chúng thành một hàng như GROUP BY.

- **OVER** mở ra ngữ cảnh window.
- **PARTITION BY** chia dữ liệu thành các nhóm logic độc lập.
- **ORDER BY trong OVER** quyết định thứ tự cho ranking và phép tính theo chuỗi.
- **ROWS/RANGE/GROUPS frame** quyết định những hàng nào nằm trong phạm vi phép tính của các hàm có xét frame.
- **ROW_NUMBER** đánh số từng hàng; **RANK** có đồng hạng và bỏ số; **DENSE_RANK** có đồng hạng nhưng không bỏ số.
- **SUM/AVG/COUNT OVER** tính số liệu của partition nhưng vẫn giữ từng hàng đầu vào.
- **LAG/LEAD** cho phép so sánh với hàng trước/sau; **LAST_VALUE** cần frame đúng nếu muốn giá trị cuối cả partition.
- **Top-N per group** thường cần tính rank ở lớp query trong rồi lọc ở lớp ngoài.
- **WHERE và JOIN** quyết định tập hàng tham gia window; lọc sai tầng hoặc join collection sai độ hạt có thể làm toàn bộ kết quả không đúng.
- **Hibernate HQL nâng cao** dịch biểu thức window theo mapping entity sang SQL của database, nhưng vẫn cần kiểm chứng version, dialect và execution plan.

Tư duy hiệu quả khi thiết kế truy vấn HQL window là: **xác định một hàng đại diện cho gì, nhóm theo khóa nào, sắp xếp theo tiêu chí nào, phép tính nhìn thấy những hàng nào và kết quả cần giữ ở độ hạt nào**. Khi năm điều đó rõ ràng, bạn có thể triển khai báo cáo xếp hạng, running total và moving average ngay trong database, đồng thời tránh tải toàn bộ lịch sử vào bộ nhớ Java chỉ để tính toán thủ công.
