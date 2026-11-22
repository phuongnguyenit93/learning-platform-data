# Phân trang bằng setFirstResult và setMaxResults trong JPA

Trong một ứng dụng sử dụng Jakarta Persistence (JPA), truy vấn toàn bộ hàng trăm nghìn đơn hàng hoặc sản phẩm chỉ để hiển thị 20 dòng trên một màn hình là cách làm tốn tài nguyên và không cần thiết. **Phân trang (pagination)** giúp giới hạn số kết quả ứng dụng nhận trong mỗi lần đọc, hỗ trợ giao diện danh sách, báo cáo, màn hình quản trị và API.

JPA cung cấp hai phương thức trên `Query` và `TypedQuery` để thực hiện **offset-based pagination**:

~~~java
query.setFirstResult(40);
query.setMaxResults(20);
~~~

Ở đây:

- `setFirstResult(40)`: bỏ qua **40 kết quả đầu tiên** trong thứ tự truy vấn.
- `setMaxResults(20)`: lấy **tối đa 20 kết quả** từ vị trí đó.
- Nếu danh sách có ít hơn 60 kết quả, trang trả về có thể chứa ít hơn 20 dòng.
- Nếu không còn kết quả ở vị trí bắt đầu, `getResultList()` trả danh sách rỗng.

Hai phương thức này không tự quyết định **thứ tự sắp xếp**, **tổng số bản ghi**, **số trang**, **quyền truy cập**, hay **độ ổn định khi dữ liệu thay đổi**. Để phân trang đúng, cần kết hợp chúng với `ORDER BY` có tính xác định, bộ lọc đồng nhất và một chiến lược đếm hoặc điều hướng trang phù hợp.

Bài học tập trung vào cách dùng `setFirstResult` và `setMaxResults` với JPQL, Criteria API, Native SQL và DTO projection; đồng thời giải thích các bẫy N+1, JOIN FETCH collection, DISTINCT, GROUP BY, hiệu năng của offset lớn, tính nhất quán giữa các trang và cách kiểm thử.

## 1. Phân trang giải quyết bài toán gì?

Giả sử database có 125 đơn hàng thỏa điều kiện:

~~~text
125 đơn hàng sau WHERE và ORDER BY
    |
    +-- Trang 1: hàng 0  -> 19
    +-- Trang 2: hàng 20 -> 39
    +-- Trang 3: hàng 40 -> 59
    +-- Trang 4: hàng 60 -> 79
    +-- Trang 5: hàng 80 -> 99
    +-- Trang 6: hàng 100 -> 119
    +-- Trang 7: hàng 120 -> 124 (chỉ có 5)
~~~

Một trang có kích thước `size = 20`; chỉ trang cuối có thể trả ít hơn 20.

Với quy ước **page index bắt đầu từ 0**:

| Trang hiển thị cho người dùng | `pageIndex` | `setFirstResult` | `setMaxResults` | Số hàng tối đa |
| --- | ---: | ---: | ---: | ---: |
| Trang 1 | 0 | 0 | 20 | 20 |
| Trang 2 | 1 | 20 | 20 | 20 |
| Trang 3 | 2 | 40 | 20 | 20 |
| Trang 4 | 3 | 60 | 20 | 20 |
| Trang 7 | 6 | 120 | 20 | 5 |

`setMaxResults(20)` vẫn bằng 20 ở trang cuối. Nó biểu diễn **giới hạn**, không biểu diễn số phần tử bắt buộc phải trả.

### Tại sao không tải hết rồi tự cắt List?

Không nên:

~~~java
List<PurchaseOrder> all = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

List<PurchaseOrder> page =
    all.subList(40, Math.min(60, all.size()));
~~~

Cách này đã khiến database gửi toàn bộ danh sách, JPA tạo nhiều managed entities và ứng dụng giữ chúng trong RAM. `subList` chỉ cắt ở phía Java **sau khi chi phí truy vấn/tải dữ liệu đã xảy ra**.

Cách đúng là áp dụng giới hạn ngay trên JPA query:

~~~java
List<PurchaseOrder> page = em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "ORDER BY o.id",
        PurchaseOrder.class)
    .setFirstResult(40)
    .setMaxResults(20)
    .getResultList();
~~~

Provider thường đưa phân trang xuống SQL theo dialect hoặc dùng cơ chế tương ứng; tuy nhiên cần xem SQL thực tế, nhất là với các truy vấn có fetch join collection hoặc các cấu trúc phức tạp.

## 2. Hai API chính và ý nghĩa tham số

Các lời gọi điển hình:

~~~java
TypedQuery<PurchaseOrder> q = em.createQuery(
    "SELECT o FROM PurchaseOrder o ORDER BY o.id",
    PurchaseOrder.class
);

q.setFirstResult(20);
q.setMaxResults(10);

List<PurchaseOrder> result = q.getResultList();
~~~

Hai phương thức:

~~~java
Query setFirstResult(int startPosition);
Query setMaxResults(int maxResult);
~~~

`TypedQuery<T>` có các phương thức tương ứng trả kiểu TypedQuery phù hợp để có thể chain.

### setFirstResult

`startPosition` là **vị trí bắt đầu tính từ 0** trong tập kết quả truy vấn đã sắp xếp:

- `0`: bắt đầu từ kết quả đầu tiên.
- `10`: bỏ qua mười kết quả đầu tiên.
- `100`: bắt đầu từ kết quả thứ 101 nếu đếm theo cách nói thông thường.

Không truyền số trang vào `setFirstResult` trừ khi kích thước trang chính xác bằng 1.

### setMaxResults

`maxResult` là **số kết quả tối đa muốn nhận**, không phải chỉ số của kết quả cuối:

- `10`: trả tối đa mười kết quả.
- `20`: trả tối đa hai mươi kết quả.
- `0`: giới hạn không có kết quả; về mặt API là một giá trị không âm hợp lệ, nhưng thường không hữu ích cho một trang UI.

Giá trị âm không hợp lệ và API có thể ném `IllegalArgumentException`.

### Giá trị mặc định

Nếu không gọi `setFirstResult`, query bắt đầu từ vị trí 0. Nếu không gọi `setMaxResults`, không có giới hạn trang có chủ đích của ứng dụng; `getMaxResults()` thông thường báo `Integer.MAX_VALUE` theo contract JPA.

Vì vậy, **không gọi setMaxResults không đồng nghĩa mặc định lấy 20 phần tử**. Một API công khai nên có giới hạn kích thước trang rõ ràng.

## 3. Công thức từ số trang sang offset

Với page index bắt đầu từ 0:

\[
\text{offset} = \text{pageIndex} \times \text{pageSize}
\]

Sau đó:

~~~java
query.setFirstResult(pageIndex * pageSize);
query.setMaxResults(pageSize);
~~~

Ví dụ:

~~~text
pageIndex = 3
pageSize  = 25

offset    = 3 * 25 = 75
limit     = 25

-> lấy tối đa 25 kết quả, bỏ qua 75 kết quả đầu.
~~~

### Giao diện đánh số trang từ 1

Người dùng thường thấy “Trang 1, 2, 3…”, trong khi code dễ dùng `pageIndex = 0, 1, 2…`.

Nếu request nhận `pageNumber` bắt đầu từ 1:

~~~java
int pageIndex = pageNumber - 1;
int offset = pageIndex * pageSize;
~~~

Phải validate `pageNumber >= 1` **trước khi trừ 1**. Không dùng nhầm `pageNumber * size`, vì trang hiển thị đầu tiên sẽ bỏ qua cả một trang dữ liệu.

### Offset không phải số thứ tự ID

`setFirstResult(100)` không có nghĩa “lấy Order có ID bắt đầu từ 100”. Nó có nghĩa **bỏ qua 100 hàng theo kết quả truy vấn**, bất kể các ID là 1, 4, 100, 1000 hay UUID.

Đây là lý do một truy vấn có ORDER BY quan trọng hơn cách đánh số ID của entity.

## 4. Tránh lỗi overflow khi nhân page với size

Biểu thức:

~~~java
int offset = pageIndex * pageSize;
~~~

có thể **tràn số int** nếu hai giá trị đầu vào lớn. Dù người dùng bình thường chỉ tải vài trang, API không nên tin input tùy ý.

Một helper an toàn:

~~~java
public static int offsetOf(
        int pageIndex,
        int pageSize) {

    if (pageIndex < 0) {
        throw new IllegalArgumentException(
            "pageIndex phải >= 0");
    }

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException(
            "pageSize phải trong [1, 100]");
    }

    long offset = (long) pageIndex * pageSize;

    if (offset > Integer.MAX_VALUE) {
        throw new IllegalArgumentException(
            "Offset vượt giới hạn JPA int");
    }

    return (int) offset;
}
~~~

### Tại sao tính bằng long?

JPA nhận một tham số `int` cho `setFirstResult`, nhưng phép nhân nên thực hiện bằng `long` trước để phát hiện vượt ngưỡng mà không bị overflow.

Không nên:

~~~java
long offset = (long) (pageIndex * pageSize);
~~~

vì phép nhân đã được tính ở `int` **trước khi ép sang long**. Hãy ép trước phép nhân:

~~~java
long offset = (long) pageIndex * pageSize;
~~~

### Giới hạn page size là quy tắc ứng dụng

`pageSize <= 100` chỉ là ví dụ policy của API. JPA không áp một mức 100 chung. Với xuất dữ liệu nội bộ, page size có thể khác nhưng vẫn cần cân bằng bộ nhớ, độ trễ, tải database và kích thước response.

## 5. ORDER BY là điều kiện thiết yếu của phân trang

Truy vấn:

~~~jpql
SELECT o FROM PurchaseOrder o
~~~

không hứa hẹn các hàng được trả theo thứ tự cố định. Database có thể thay đổi execution plan, dùng index khác hoặc phân phối kết quả khác khi dữ liệu đổi.

Nếu áp:

~~~java
query.setFirstResult(0).setMaxResults(20);
~~~

vào query không có ORDER BY, “20 dòng đầu tiên” **không được xác định ổn định**.

### Ví dụ đúng

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.placedAt DESC, o.id DESC
~~~

Ý nghĩa:

1. Đơn mới đặt xuất hiện trước.
2. Nếu hai đơn có cùng `placedAt`, đơn có ID lớn hơn đứng trước.
3. `id` là khóa duy nhất, tạo thứ tự tường minh cho các trường hợp hòa thời gian.

**Không phân trang theo một thứ tự chưa được xác định.**

## 6. Tie-breaker: vì sao sort theo ngày chưa đủ?

Giả sử có các đơn:

| ID | placedAt |
| ---: | --- |
| 101 | 2027-06-01 09:00 |
| 102 | 2027-06-01 09:00 |
| 103 | 2027-06-01 09:00 |
| 104 | 2027-06-01 08:59 |

Nếu query chỉ có:

~~~jpql
ORDER BY o.placedAt DESC
~~~

thì ba đơn đầu có cùng `placedAt`. DBMS không phải cam kết thứ tự giữa 101, 102 và 103. Khi phân trang kích thước 2, các lần query có thể trả nhóm cùng thời gian theo thứ tự khác, tạo nguy cơ trùng/bỏ sót giữa các trang.

Thêm:

~~~jpql
ORDER BY o.placedAt DESC, o.id DESC
~~~

để tạo thứ tự toàn phần khi ID là duy nhất.

### Tie-breaker không giải quyết mọi thay đổi concurrent

Ngay cả khi ORDER BY ổn định, một Order mới được chèn ở đầu giữa hai lần đọc vẫn có thể làm các offset bị dịch. Tie-breaker giải quyết **sự nhập nhằng của thứ tự trên cùng tập dữ liệu**, không biến các request riêng thành cùng một snapshot.

## 7. Mô hình entity ví dụ

Ta dùng mô hình đơn hàng:

~~~text
Customer (1) ------ (N) PurchaseOrder (1) ------ (N) OrderLine
  id                       id                         id
  name                     tenantId                   order_id
  email                    placedAt                   sku
                           status                     quantity
                           totalAmount                lineTotal
                           customer_id
~~~

Một `PurchaseOrder` thuộc một `Customer`. Mỗi đơn có thể có nhiều `OrderLine`. Trường `totalAmount` ở Order là **tổng được lưu/duy trì theo nghiệp vụ**, không phải giá được tự tính lại từ SKU hiện tại mỗi khi đọc.

### 7.1. Customer

~~~java
package com.example.shop;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### 7.2. Trạng thái đơn hàng

~~~java
package com.example.shop;

public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

### 7.3. PurchaseOrder

~~~java
package com.example.shop;

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

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false,
            precision = 18, scale = 2)
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Instant getPlacedAt() {
        return placedAt;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
~~~

### 7.4. OrderLine

~~~java
package com.example.shop;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "line_total", nullable = false,
            precision = 18, scale = 2)
    private BigDecimal lineTotal;

    protected OrderLine() {
    }
}
~~~

### Dữ liệu ví dụ

| Order ID | Tenant | Customer | placedAt | Status | totalAmount |
| ---: | ---: | --- | --- | --- | ---: |
| 105 | 10 | An | 2027-06-03 14:10 | PAID | 800.000 |
| 104 | 10 | Bình | 2027-06-03 14:08 | PAID | 350.000 |
| 103 | 10 | An | 2027-06-02 10:15 | PENDING | 200.000 |
| 102 | 10 | Chi | 2027-06-01 09:00 | PAID | 450.000 |
| 101 | 10 | Bình | 2027-06-01 09:00 | PAID | 150.000 |
| 901 | 20 | An | 2027-06-03 14:11 | PAID | 900.000 |

Với tenant=10, status=PAID, sắp theo `placedAt DESC, id DESC`, kết quả logic là:

~~~text
[105, 104, 102, 101]
~~~

Chọn `pageIndex=1`, `size=2`:

~~~text
offset=2, limit=2 -> [102, 101]
~~~

Order 901 **không xuất hiện** dù có thời điểm mới nhất, vì không thuộc tenant đang được phép truy cập.

## 8. Ví dụ JPQL TypedQuery đầy đủ

Tìm đơn PAID trong tenant hiện hành, mỗi trang 20 đơn:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import java.util.List;

public List<PurchaseOrder> findPaidOrders(
        EntityManager em,
        long tenantId,
        int pageIndex,
        int pageSize) {

    int offset = offsetOf(pageIndex, pageSize);

    TypedQuery<PurchaseOrder> query = em.createQuery(
        "SELECT o " +
        "FROM PurchaseOrder o " +
        "WHERE o.tenantId = :tenantId " +
        "AND o.status = :status " +
        "ORDER BY o.placedAt DESC, o.id DESC",
        PurchaseOrder.class
    );

    return query
        .setParameter("tenantId", tenantId)
        .setParameter("status", OrderStatus.PAID)
        .setFirstResult(offset)
        .setMaxResults(pageSize)
        .getResultList();
}
~~~

Phương thức `offsetOf(...)` ở mục 4. Trong trường hợp thực tế, `tenantId` phải được lấy từ ngữ cảnh xác thực đáng tin, không chỉ từ request do client tự khai báo.

### Vì sao dùng TypedQuery?

`TypedQuery<PurchaseOrder>` giúp kết quả Java có kiểu `PurchaseOrder`, tránh ép từng phần tử từ `Object`. Nó **không** tự giải quyết N+1, transaction hoặc pagination consistency.

### Vì sao dùng named parameter?

`:tenantId` và `:status` được bind bằng `setParameter(...)`. Giá trị từ request không được nối thẳng vào chuỗi JPQL. Cấu trúc sắp xếp phải được kiểm soát riêng, vì tên trường/ASC/DESC không phải một dữ liệu giá trị đơn thuần để bind tùy tiện.

### Có nên trả entity cho giao diện danh sách?

Có thể, nếu service cần thao tác tiếp trên managed entity. Nhưng nếu API chỉ hiển thị một số cột, **DTO projection** thường làm rõ contract và giảm nguy cơ lazy loading. Phần kế tiếp minh họa.

## 9. Phân trang DTO projection

Màn hình chỉ cần:

~~~text
Order ID | Ngày đặt | Trạng thái | Khách hàng | Tổng tiền
~~~

Không cần trả một object graph gồm Order, Customer và toàn bộ OrderLine.

Tạo DTO:

~~~java
package com.example.shop.dto;

import com.example.shop.OrderStatus;
import java.math.BigDecimal;
import java.time.Instant;

public record OrderListRow(
        Long id,
        Instant placedAt,
        OrderStatus status,
        String customerName,
        BigDecimal totalAmount) {
}
~~~

DTO dùng Java `record` (Java 16+); với dự án dùng Java cũ, thay bằng POJO có constructor tương thích.

JPQL constructor expression:

~~~java
TypedQuery<OrderListRow> query = em.createQuery(
    "SELECT NEW com.example.shop.dto.OrderListRow(" +
    "o.id, o.placedAt, o.status, c.name, o.totalAmount) " +
    "FROM PurchaseOrder o JOIN o.customer c " +
    "WHERE o.tenantId = :tenantId " +
    "AND o.status = :status " +
    "ORDER BY o.placedAt DESC, o.id DESC",
    OrderListRow.class
);

List<OrderListRow> page = query
    .setParameter("tenantId", tenantId)
    .setParameter("status", OrderStatus.PAID)
    .setFirstResult(offsetOf(pageIndex, pageSize))
    .setMaxResults(pageSize)
    .getResultList();
~~~

### DTO và phân trang bổ sung nhau

- `setFirstResult`/`setMaxResults` giới hạn **số hàng kết quả**.
- `SELECT NEW ...` giới hạn **những giá trị cần đưa vào kết quả Java**.
- `JOIN o.customer c` cho phép chọn `c.name` trực tiếp, không cần tạo một graph entity đầy đủ để serializer tự gọi `order.getCustomer()`.
- `ORDER BY o.placedAt DESC, o.id DESC` bảo đảm thứ tự có tie-breaker.

**DTO không phải managed entity.** Đổi `OrderListRow.totalAmount` (nếu DTO mutable) không kích hoạt dirty checking cập nhật PurchaseOrder trong database.

### DTO không làm truy vấn chậm trở nên nhanh một cách kỳ diệu

Nếu query JOIN nhiều collection hoặc có subquery/aggregate nặng, DTO vẫn phải chờ database hoàn thành công việc. Nhưng DTO giúp tránh việc tải các thuộc tính/association không cần và tạo contract đọc dữ liệu rõ.

## 10. Query.count và metadata của một trang

UI thường cần:

~~~text
Trang 3 / 7
Tổng cộng 125 đơn hàng
Có trang tiếp theo: Có
~~~

`setFirstResult` và `setMaxResults` **không tự trả tổng số hàng khớp bộ lọc**. Phải chạy một query COUNT riêng hoặc dùng cơ chế điều hướng không cần total.

Ví dụ:

~~~java
Long total = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.tenantId = :tenantId " +
        "AND o.status = :status",
        Long.class)
    .setParameter("tenantId", tenantId)
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
~~~

`COUNT(o)` trong JPQL trả `Long`. Không ép mặc định sang `Integer` vì giá trị có thể lớn hơn giới hạn int.

### Count query không cần ORDER BY

Một query chỉ trả tổng:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE ...
~~~

không cần sắp xếp toàn bộ Orders trước khi đếm. Không sao chép `ORDER BY` từ query trang sang count query nếu nó không phục vụ mục đích count.

### Không áp pagination lên count query

Nếu code:

~~~java
countQuery.setFirstResult(40);
countQuery.setMaxResults(20);
~~~

thì không còn ý nghĩa đếm toàn bộ kết quả lọc. Một aggregate count thường trả **một hàng**; phân trang hàng scalar ấy thậm chí có thể làm kết quả rỗng nếu offset lớn hơn 0.

**COUNT phải đếm toàn bộ tập dữ liệu khớp bộ lọc**, không chỉ số dòng của trang đang mở.

## 11. Tính totalPages và hasNext đúng

Giả sử:

~~~text
totalElements = 125
pageSize = 20
~~~

Số trang:

\[
\text{totalPages} = \left\lceil \frac{\text{totalElements}}{\text{pageSize}} \right\rceil
\]

Không nên cộng `size - 1` tùy tiện vào `long total` khi có thể vượt giới hạn long. Có thể tính bằng thương và số dư:

~~~java
public static long totalPages(
        long totalElements, int pageSize) {

    if (totalElements < 0) {
        throw new IllegalArgumentException(
            "totalElements phải không âm");
    }
    if (pageSize <= 0) {
        throw new IllegalArgumentException(
            "pageSize phải dương");
    }

    long pages = totalElements / pageSize;
    if (totalElements % pageSize != 0) {
        pages++;
    }
    return pages;
}
~~~

Kết quả:

~~~text
125 / 20 = 6 dư 5
totalPages = 7
~~~

Với `totalElements=0`, hàm trên trả `totalPages=0`. Một số UI muốn hiển thị “Trang 1/1” cho trang rỗng; đó là **quy ước UI**, nên tách khỏi cách tính số trang có dữ liệu.

### HasNext

Nếu có total:

~~~java
long offset = (long) pageIndex * pageSize;
boolean hasNext =
    offset + rows.size() < totalElements;
~~~

Nếu `rows` rỗng ở một page vượt phạm vi, điều kiện trên cần được hiểu theo metadata request. Có thể xử lý `hasNext` bằng vị trí cuối lý thuyết của trang khi mong muốn:

~~~java
boolean hasNext =
    offset + pageSize < totalElements;
~~~

Với page hợp lệ và dữ liệu không đổi, hai cách cho cùng kết quả khi trang đầy. Khi dữ liệu thay đổi giữa count và page hoặc request nằm ngoài phạm vi, cần định nghĩa API semantics rõ ràng.

## 12. DTO cho response phân trang

Một API có thể trả:

~~~json
{
  "content": [
    {
      "id": 105,
      "placedAt": "2027-06-03T07:10:00Z",
      "status": "PAID",
      "customerName": "An",
      "totalAmount": 800000.00
    }
  ],
  "pageIndex": 0,
  "pageSize": 20,
  "totalElements": 125,
  "totalPages": 7,
  "hasNext": true
}
~~~

Đây là **cấu trúc API minh họa**, không phải đối tượng JSON do JPA tự tạo.

Một Java record tổng quát:

~~~java
package com.example.shop.dto;

import java.util.List;

public record PageResult<T>(
        List<T> content,
        int pageIndex,
        int pageSize,
        long totalElements,
        long totalPages,
        boolean hasNext) {

    public PageResult {
        content = List.copyOf(content);
    }
}
~~~

Service:

~~~java
List<OrderListRow> rows =
    repository.findOrderRows(tenantId, status, page, size);
long total =
    repository.countOrderRows(tenantId, status);

long pages = totalPages(total, size);
long offset = (long) page * size;
boolean hasNext = offset + size < total;

PageResult<OrderListRow> response =
    new PageResult<>(
        rows, page, size, total, pages, hasNext);
~~~

Nếu `rows` và `total` được thực hiện trong hai câu SQL khác nhau, chúng có thể thấy **hai snapshot khác nhau** tùy transaction isolation. Bảng metadata không tự bảo đảm total luôn khớp chính xác với page ở một hệ thống đang có cập nhật concurrent.

## 13. Query có nhiều bộ lọc phải thống nhất với COUNT

Giả sử người dùng tìm:

~~~text
tenantId = 10
status = PAID
placedAt >= from
placedAt < to
customerName chứa "an"
~~~

Query trang phải áp dụng đủ các điều kiện ấy trước ORDER BY và pagination.

Nếu count query quên điều kiện `customerName`, giao diện có thể hiển thị:

~~~text
5 đơn trên trang hiện tại,
nhưng totalElements = 10.000
~~~

dù chỉ có 5 đơn thật sự phù hợp toàn bộ filter.

### Quy tắc

> Filter của query trang và filter của count query phải có cùng ngữ nghĩa; chỉ phần SELECT/ORDER BY/pagination khác nhau khi thích hợp.

Ví dụ hai JPQL:

~~~jpql
-- Query trang
SELECT NEW com.example.shop.dto.OrderListRow(
    o.id, o.placedAt, o.status, c.name, o.totalAmount
)
FROM PurchaseOrder o JOIN o.customer c
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND o.placedAt >= :fromInclusive
  AND o.placedAt < :toExclusive
  AND LOWER(c.name) LIKE :customerPattern
ORDER BY o.placedAt DESC, o.id DESC
~~~

~~~jpql
-- Query COUNT
SELECT COUNT(o)
FROM PurchaseOrder o JOIN o.customer c
WHERE o.tenantId = :tenantId
  AND o.status = :status
  AND o.placedAt >= :fromInclusive
  AND o.placedAt < :toExclusive
  AND LOWER(c.name) LIKE :customerPattern
~~~

Không cần JOIN Customer trong count query nếu bộ lọc/logic khác không nhắc đến Customer, nhưng ở ví dụ này nó cần cho điều kiện `c.name`.

### Phân biệt bộ lọc và fetch

Một JOIN để lọc Customer name không đồng nghĩa cần `JOIN FETCH` toàn bộ Customer. Với DTO projection, ta chỉ chọn `c.name`.

Không sao chép JOIN FETCH collection vào count query. Count cần đếm root entities, không cần khởi tạo object graph.

## 14. Một service paged DTO hoàn chỉnh bằng Criteria API

Khi bộ lọc tùy chọn tăng, Criteria API giúp dựng query trang và query đếm dựa trên cùng logic, nhưng vẫn cần tạo `Root` và `Predicate` riêng cho mỗi query.

Định nghĩa filter:

~~~java
package com.example.shop.dto;

import com.example.shop.OrderStatus;
import java.time.Instant;

public record OrderFilter(
        OrderStatus status,
        Instant fromInclusive,
        Instant toExclusive) {
}
~~~

Service sử dụng `CriteriaBuilder`:

~~~java
package com.example.shop;

import com.example.shop.dto.OrderFilter;
import com.example.shop.dto.OrderListRow;
import com.example.shop.dto.PageResult;
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class OrderPageService {

    private final EntityManager em;

    public OrderPageService(EntityManager em) {
        this.em = em;
    }

    public PageResult<OrderListRow> findPage(
            long tenantId,
            OrderFilter filter,
            int pageIndex,
            int pageSize) {

        int offset = offsetOf(pageIndex, pageSize);
        validate(tenantId, filter);

        CriteriaBuilder cb = em.getCriteriaBuilder();

        // Query nội dung trang.
        CriteriaQuery<OrderListRow> dataQuery =
            cb.createQuery(OrderListRow.class);
        Root<PurchaseOrder> o = dataQuery.from(
            PurchaseOrder.class);
        Join<PurchaseOrder, Customer> c =
            o.join("customer");

        dataQuery.select(cb.construct(
            OrderListRow.class,
            o.get("id"),
            o.get("placedAt"),
            o.get("status"),
            c.get("name"),
            o.get("totalAmount")
        ));

        dataQuery.where(
            createRestrictions(cb, o, tenantId, filter)
        );
        dataQuery.orderBy(
            cb.desc(o.get("placedAt")),
            cb.desc(o.get("id"))
        );

        List<OrderListRow> content =
            em.createQuery(dataQuery)
                .setFirstResult(offset)
                .setMaxResults(pageSize)
                .getResultList();

        // Query đếm, với Root/Predicate mới.
        CriteriaQuery<Long> countQuery =
            cb.createQuery(Long.class);
        Root<PurchaseOrder> countRoot =
            countQuery.from(PurchaseOrder.class);

        countQuery.select(cb.count(countRoot));
        countQuery.where(
            createRestrictions(
                cb, countRoot, tenantId, filter)
        );

        long total = em.createQuery(countQuery)
            .getSingleResult();

        long pages = totalPages(total, pageSize);
        boolean hasNext =
            (long) offset + pageSize < total;

        return new PageResult<>(
            content,
            pageIndex,
            pageSize,
            total,
            pages,
            hasNext
        );
    }

    private static Predicate createRestrictions(
            CriteriaBuilder cb,
            Root<PurchaseOrder> order,
            long tenantId,
            OrderFilter filter) {

        List<Predicate> predicates = new ArrayList<>();

        // Điều kiện quyền truy cập: không được bỏ qua.
        predicates.add(cb.equal(
            order.get("tenantId"), tenantId));

        if (filter.status() != null) {
            predicates.add(cb.equal(
                order.get("status"), filter.status()));
        }

        if (filter.fromInclusive() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                order.<Instant>get("placedAt"),
                filter.fromInclusive()));
        }

        if (filter.toExclusive() != null) {
            predicates.add(cb.lessThan(
                order.<Instant>get("placedAt"),
                filter.toExclusive()));
        }

        return cb.and(
            predicates.toArray(Predicate[]::new));
    }

    private static void validate(
            long tenantId,
            OrderFilter filter) {

        if (tenantId <= 0 || filter == null) {
            throw new IllegalArgumentException(
                "tenantId/filter không hợp lệ");
        }

        Instant from = filter.fromInclusive();
        Instant to = filter.toExclusive();

        if (from != null && to != null
                && !from.isBefore(to)) {
            throw new IllegalArgumentException(
                "Khoảng thời gian phải có from < to");
        }
    }

    private static int offsetOf(
            int pageIndex, int size) {

        if (pageIndex < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                "Chỉ số trang hoặc page size không hợp lệ");
        }

        long offset = (long) pageIndex * size;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Offset vượt giới hạn");
        }

        return (int) offset;
    }

    private static long totalPages(
            long total, int size) {

        return total / size +
            (total % size == 0 ? 0 : 1);
    }
}
~~~

### Phân tích thiết kế

1. `tenantId` là điều kiện **bắt buộc**, nằm trong cả data và count query.
2. Các thuộc tính của `OrderFilter` chỉ thêm restriction khi có giá trị.
3. `createRestrictions(...)` nhận `Root<PurchaseOrder>` do **chính query hiện tại** tạo.
4. Data query dùng DTO constructor, không fetch collection lines.
5. Count query chỉ đếm PurchaseOrder root và không ORDER BY.
6. `setFirstResult`/`setMaxResults` chỉ được áp dụng cho query trang.
7. Sắp xếp theo hai thuộc tính, trong đó ID là tie-breaker.
8. Input page và date range được validate trước khi chạy SQL.

**Không tái sử dụng cùng một Predicate object từ dataQuery cho countQuery.** Predicate tham chiếu tới Root/cây Criteria cụ thể. Chỉ tái sử dụng **hàm tạo logic**, sau đó dựng những node mới trên Root riêng.

### Giả định của ví dụ

Code dùng Java 17+ cho record và `Predicate[]::new`. Để code chạy trong dự án thực, cần EntityManager gắn với persistence context/transaction đúng cách và cấu hình JPA/provider phù hợp. Service chỉ đọc nhưng hai query không tự có snapshot giống nhau nếu hệ thống có cập nhật concurrent.

## 15. Khi query trả entity, có cần fetch graph không?

Một query trả:

~~~java
TypedQuery<PurchaseOrder> q =
    em.createQuery(
        "SELECT o FROM PurchaseOrder o " +
        "WHERE o.tenantId = :tenant " +
        "ORDER BY o.id",
        PurchaseOrder.class);
~~~

Mỗi PurchaseOrder có `customer` và `lines`. Các association có thể LAZY; query trang **không nhất thiết nạp chúng**.

Nếu UI gọi `order.getCustomer().getName()` cho 20 Order, nó có thể gây SELECT bổ sung. Giải pháp:

- Ưu tiên DTO nếu chỉ cần `customerName`.
- Hoặc dùng `JOIN FETCH o.customer` khi cần managed Order và Customer.
- Hoặc entity graph theo use case.
- Cân nhắc batch fetching nếu nhiều lazy associations cần nạp trong một context.

### Fetch to-one thường phù hợp hơn to-many khi phân trang

Với `@ManyToOne` một Order tham chiếu tối đa một Customer, JOIN tới Customer không nhân số Order root theo cách JOIN collection nhiều phần tử làm. Tuy nhiên vẫn cần xem optionality/INNER vs LEFT join và các điều kiện lọc.

Với `@OneToMany` lines, JOIN fetch có thể nhân hàng và làm phân trang sai hoặc rất tốn chi phí.

## 16. Bẫy lớn nhất: JOIN FETCH collection + setMaxResults

Query dễ viết:

~~~java
List<PurchaseOrder> page = em.createQuery(
        "SELECT DISTINCT o " +
        "FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "WHERE o.tenantId = :tenantId " +
        "ORDER BY o.id",
        PurchaseOrder.class)
    .setParameter("tenantId", tenantId)
    .setFirstResult(0)
    .setMaxResults(10)
    .getResultList();
~~~

Người viết mong **10 Order cùng tất cả OrderLine**, nhưng dữ liệu JOIN có thể như sau:

~~~text
Order#1 + Line#1
Order#1 + Line#2
Order#1 + Line#3
Order#2 + Line#4
Order#2 + Line#5
...
~~~

Một Order có thể tạo **nhiều hàng SQL**. Nếu database áp LIMIT vào hàng JOIN, câu SQL lấy 10 hàng có thể chỉ chứa 3 Order và cắt dở collection.

Provider có thể:

- Tự phân trang trong memory sau khi tải nhiều hàng.
- Cảnh báo hoặc từ chối để tránh kết quả không chính xác.
- Dùng chiến lược SQL khác tùy phiên bản/dialect.

Không được giả định mọi stack JPA hỗ trợ phân trang root entities hiệu quả và chính xác khi fetch join collection.

### SELECT DISTINCT không xóa bản chất fan-out

`DISTINCT o` có thể làm danh sách root entities không lặp, nhưng ở JDBC result set các cột line vẫn khiến nhiều hàng khác nhau. DISTINCT không biến mối quan hệ one-to-many thành one-to-one, cũng không đảm bảo LIMIT/OFFSET đã được áp dụng theo số root trước khi FETCH.

### Không dùng “tăng pageSize bù trừ” để chữa

Không thể biết chính xác cần bao nhiêu hàng JOIN để lấy 10 Order vì mỗi Order có số lines khác nhau. Dùng setMaxResults(100) rồi cắt lại 10 là cách không ổn định.

## 17. Giải pháp: phân trang ID trước, fetch collection sau

Khi service cần 20 Order root cùng lines:

**Bước 1: phân trang các ID Order.**

~~~java
List<Long> ids = em.createQuery(
        "SELECT o.id " +
        "FROM PurchaseOrder o " +
        "WHERE o.tenantId = :tenant " +
        "AND o.status = :status " +
        "ORDER BY o.placedAt DESC, o.id DESC",
        Long.class)
    .setParameter("tenant", tenantId)
    .setParameter("status", OrderStatus.PAID)
    .setFirstResult(offsetOf(pageIndex, pageSize))
    .setMaxResults(pageSize)
    .getResultList();
~~~

**Bước 2: fetch các entity cho tập ID đã chọn, không phân trang trên JOIN collection.**

~~~java
if (ids.isEmpty()) {
    return List.of();
}

List<PurchaseOrder> orders = em.createQuery(
        "SELECT DISTINCT o " +
        "FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "WHERE o.tenantId = :tenant " +
        "AND o.id IN :ids",
        PurchaseOrder.class)
    .setParameter("tenant", tenantId)
    .setParameter("ids", ids)
    .getResultList();
~~~

Lưu ý:

- Dùng `IN :ids` là một tập hợp, **không đảm bảo thứ tự trả về** theo danh sách IDs của bước 1.
- Nếu API cần giữ thứ tự, sắp xếp sau bằng thứ tự ID được ghi nhận.
- Tập ID có kích thước tối đa `pageSize`, tránh IN list cực lớn.
- Bước 1 phải có filter authorization đúng; bước 2 nên tiếp tục scope tenant để tránh nhầm lẫn logic.
- Trong thực tế cần kết hợp điều kiện status/date khi có khả năng bản ghi đổi giữa hai query và xác định consistency policy.

### Khôi phục thứ tự của trang

~~~java
Map<Long, PurchaseOrder> byId = new HashMap<>();
for (PurchaseOrder order : orders) {
    byId.put(order.getId(), order);
}

List<PurchaseOrder> ordered = new ArrayList<>();
for (Long id : ids) {
    PurchaseOrder order = byId.get(id);
    if (order != null) {
        ordered.add(order);
    }
}
~~~

Code này giả định có import `java.util.Map`, `HashMap`, `ArrayList`, `List`. Nếu dữ liệu thay đổi/xóa giữa bước 1 và bước 2, một ID có thể không còn được trả; **không giấu vấn đề bằng cách nhân đôi dữ liệu hay lấy thêm trang khác không nhất quán**.

## 18. Một loại JOIN khác: lọc theo collection nhưng không FETCH

Giả sử cần tìm những Order có OrderLine có `sku` thuộc một tập SKU:

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku IN :skus
ORDER BY o.id
~~~

Nếu một Order có hai lines khớp, query có thể tạo hai hàng tương ứng cùng Order. Khi áp `setFirstResult`/`setMaxResults`, phải xác định **đơn vị phân trang là Order hay matching line**.

### Nếu muốn mỗi Order xuất hiện một lần

Một cách:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku IN :skus
ORDER BY o.id
~~~

Khi không FETCH collection, provider/DBMS có thể thực hiện DISTINCT để trả tập Order duy nhất trước khi áp pagination. Nhưng cần kiểm tra SQL thực tế, especially khi ORDER BY phức tạp và JOIN nhiều quan hệ.

### Dùng EXISTS thường diễn đạt tốt hơn

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenant
  AND EXISTS (
      SELECT l.id
      FROM OrderLine l
      WHERE l.order = o
        AND l.sku IN :skus
  )
ORDER BY o.placedAt DESC, o.id DESC
~~~

Ở outer query, mỗi PurchaseOrder root chỉ xuất hiện một lần về mặt logic, tránh nhân hàng bởi JOIN lines. Đây là một lựa chọn hữu ích khi filter có ý nghĩa **“tồn tại ít nhất một phần tử con thỏa điều kiện”**.

**Không phải EXISTS luôn nhanh hơn JOIN.** Quyết định dựa vào query plan, index, cardinality và dữ liệu thực tế.

## 19. COUNT(DISTINCT ...) khi filter phải JOIN to-many

Giả sử query trang:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o JOIN o.lines l
WHERE o.tenantId = :tenant
  AND l.sku IN :skus
ORDER BY o.id
~~~

Count query sai:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o JOIN o.lines l
WHERE o.tenantId = :tenant
  AND l.sku IN :skus
~~~

Vì một Order có thể có nhiều lines khớp, `COUNT(o)` có thể lớn hơn số Order root khác nhau.

Cách đếm đúng số Order:

~~~jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o JOIN o.lines l
WHERE o.tenantId = :tenant
  AND l.sku IN :skus
~~~

Hoặc dùng cùng EXISTS filter:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.tenantId = :tenant
  AND EXISTS (
      SELECT l.id FROM OrderLine l
      WHERE l.order = o
        AND l.sku IN :skus
  )
~~~

### Một bài toán, hai số đếm khác nhau

| Muốn đếm | Biểu thức |
| --- | --- |
| Số Order có SKU phù hợp | `COUNT(DISTINCT o.id)` hoặc COUNT(o) với EXISTS |
| Số OrderLine phù hợp | `COUNT(l)` trên tập JOIN phù hợp |
| Số Customer có Order phù hợp | `COUNT(DISTINCT c.id)` |

Không áp `COUNT(DISTINCT ...)` máy móc mà chưa xác định entity đại diện cho một phần tử trang.

## 20. DISTINCT và ORDER BY: chọn thứ tự không nhập nhằng

Một query:

~~~jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
ORDER BY l.lineTotal DESC
~~~

có vấn đề ngữ nghĩa: một Order có nhiều lines với các `lineTotal` khác nhau. **Thứ tự Order theo lineTotal nào?** Đặc biệt khi DISTINCT loại trùng root, nhiều DBMS cũng yêu cầu các biểu thức ORDER BY có quy tắc tương thích SELECT DISTINCT.

### Hướng rõ ràng

Nếu muốn sắp theo **tổng tiền đơn** đã lưu:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenant
ORDER BY o.totalAmount DESC, o.id DESC
~~~

Nếu muốn sắp theo **max lineTotal của đơn**:

~~~jpql
SELECT o.id, MAX(l.lineTotal)
FROM PurchaseOrder o JOIN o.lines l
WHERE o.tenantId = :tenant
GROUP BY o.id
ORDER BY MAX(l.lineTotal) DESC, o.id DESC
~~~

Trường hợp thứ hai trả **projection theo nhóm**, không phải ngay một danh sách PurchaseOrder entity. Có thể phân trang ID theo metric, sau đó fetch entities nếu thực sự cần.

**Không chọn cột thuộc to-many relation làm sort key của root mà chưa định nghĩa phép tổng hợp hoặc quy tắc đại diện.**

## 21. Phân trang query GROUP BY/HAVING

Ví dụ hiển thị danh mục có ít nhất mười Product:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c JOIN c.products p
GROUP BY c.code
HAVING COUNT(p) >= :minCount
ORDER BY COUNT(p) DESC, c.code ASC
~~~

Nếu áp:

~~~java
query.setFirstResult(20);
query.setMaxResults(10);
~~~

thì phân trang **các hàng aggregate sau GROUP BY/HAVING**, không phân trang các Product đầu vào trước khi nhóm.

### Không dùng count Product làm tổng số nhóm

Nếu UI phân trang **các danh mục**, `totalElements` phải là số **danh mục thỏa HAVING**, không phải số Product.

Với:

~~~jpql
SELECT COUNT(p) FROM Product p
~~~

ta nhận tổng số Product, không phải tổng số dòng của query nhóm.

### Count group sau HAVING

Một số query group có thể diễn đạt total group count bằng correlated subquery:

~~~jpql
SELECT COUNT(c)
FROM Category c
WHERE (
    SELECT COUNT(p)
    FROM Product p
    WHERE p.category = c
) >= :minCount
~~~

Query này đếm số Category có ít nhất `minCount` Product theo một định nghĩa cụ thể. Với GROUP BY phức tạp hoặc nhiều HAVING conditions, Native SQL có CTE/derived table hoặc read model có thể hợp lý hơn.

### Giới hạn của JPQL portable

JPQL không có cùng cách dùng subquery trong FROM làm derived table như SQL tổng quát. Không sao chép nguyên:

~~~sql
SELECT COUNT(*)
FROM (SELECT ... GROUP BY ... HAVING ...) t
~~~

vào JPQL và giả định portable. Nếu cần, dùng native SQL với DBMS tương ứng.

## 22. Criteria API cũng hỗ trợ setFirstResult/setMaxResults

Criteria API xây cây truy vấn, rồi `EntityManager.createQuery(criteriaQuery)` trả `TypedQuery<T>`. Pagination thực hiện trên **TypedQuery sau khi cấu trúc Criteria hoàn thành**.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> o =
    cq.from(PurchaseOrder.class);

cq.select(o);
cq.where(cb.equal(
    o.get("tenantId"), tenantId));
cq.orderBy(
    cb.desc(o.get("placedAt")),
    cb.desc(o.get("id"))
);

List<PurchaseOrder> rows = em.createQuery(cq)
    .setFirstResult(offsetOf(pageIndex, pageSize))
    .setMaxResults(pageSize)
    .getResultList();
~~~

### CriteriaQuery không có nghĩa query đã thực thi

Các lệnh:

~~~java
cq.select(...);
cq.where(...);
cq.orderBy(...);
~~~

chỉ mô tả truy vấn. SQL được provider tạo/thực thi khi gọi các API như `getResultList()`. Không nên gọi `setFirstResult` trên một đối tượng CriteriaQuery như thể nó đã là TypedQuery; hai thuộc hai lớp API khác nhau.

### Criteria với DTO

~~~java
CriteriaQuery<OrderListRow> cq =
    cb.createQuery(OrderListRow.class);
Root<PurchaseOrder> o = cq.from(PurchaseOrder.class);
Join<PurchaseOrder, Customer> c = o.join("customer");

cq.select(cb.construct(
    OrderListRow.class,
    o.get("id"),
    o.get("placedAt"),
    o.get("status"),
    c.get("name"),
    o.get("totalAmount")
));
~~~

Sau đó vẫn dùng:

~~~java
em.createQuery(cq)
    .setFirstResult(offset)
    .setMaxResults(size)
    .getResultList();
~~~

Phân trang không phụ thuộc query được tạo từ chuỗi JPQL hay Criteria API.

## 23. Native SQL và phương thức pagination của Query

Với Native SQL:

~~~java
Query query = em.createNativeQuery(
    "SELECT id, sku, price " +
    "FROM products " +
    "WHERE tenant_id = ?1 " +
    "ORDER BY id ASC"
);

List<?> rows = query
    .setParameter(1, tenantId)
    .setFirstResult(40)
    .setMaxResults(20)
    .getResultList();
~~~

JPA Query API có hai phương thức phân trang tương tự. Tuy nhiên, **cách provider áp pagination lên SQL native** có thể phụ thuộc JPA provider, JDBC driver và DBMS dialect.

### Native SQL phải tự có thứ tự ổn định

Nếu SQL thiếu:

~~~sql
ORDER BY id
~~~

thì setFirstResult/setMaxResults không làm thứ tự tự ổn định.

### SQL vật lý có thể khác nhau

Provider có thể sinh:

~~~sql
-- PostgreSQL/MySQL-style, minh họa
SELECT ...
ORDER BY placed_at DESC, id DESC
LIMIT 20 OFFSET 40;
~~~

Hoặc:

~~~sql
-- SQL-standard / SQL Server-style, minh họa
SELECT ...
ORDER BY placed_at DESC, id DESC
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Một số DBMS/provider dùng `ROW_NUMBER()` hoặc cấu trúc SQL khác để phân trang. **Không viết logic ứng dụng phụ thuộc provider luôn dùng chính xác từ khóa LIMIT/OFFSET.**

### Tránh phân trang hai lần

Nếu SQL native đã có `LIMIT 20 OFFSET 40`, lại gọi:

~~~java
query.setFirstResult(40).setMaxResults(20);
~~~

có thể tạo phân trang hai tầng hoặc hành vi không mong muốn tùy provider.

Chọn **một cơ chế phân trang có chủ đích**: JPA API hoặc SQL native tự kiểm soát, rồi xác nhận trên stack thực tế.

## 24. Query chỉ có một kết quả: không dùng pagination để thay getSingleResult

Một câu:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.id = :id
~~~

đã có ngữ nghĩa tối đa một Order nếu `id` là primary key. Có thể dùng `getSingleResult()` hoặc API thích hợp với kết quả tùy chọn, không cần thiết phải `setMaxResults(1)` để làm code “chuẩn”.

Tuy nhiên, với một truy vấn **có thể nhiều hàng**, ví dụ tìm Order mới nhất:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenant
ORDER BY o.placedAt DESC, o.id DESC
~~~

ta có thể dùng:

~~~java
List<PurchaseOrder> latest = em.createQuery(
        jpql, PurchaseOrder.class)
    .setParameter("tenant", tenantId)
    .setMaxResults(1)
    .getResultList();

PurchaseOrder first = latest.isEmpty()
    ? null
    : latest.get(0);
~~~

Với API “lấy một phần tử đầu tiên theo sort”, `setMaxResults(1)` hợp lý nếu query có ORDER BY xác định. Nó **không kiểm tra uniqueness**; nếu business invariant yêu cầu đúng một row, cần cách khác để phát hiện trùng.

## 25. Trang rỗng và giới hạn cuối danh sách

Giả sử có 44 Order:

~~~text
pageSize=20
pageIndex=0 -> 20 Orders
pageIndex=1 -> 20 Orders
pageIndex=2 -> 4 Orders
pageIndex=3 -> 0 Orders
~~~

`getResultList()` của một SELECT trả danh sách rỗng khi không có hàng ở trang yêu cầu; không phải `null`.

### Không xem danh sách rỗng là lỗi database

API có thể trả:

~~~json
{
  "content": [],
  "pageIndex": 3,
  "pageSize": 20,
  "totalElements": 44,
  "totalPages": 3,
  "hasNext": false
}
~~~

hoặc dùng HTTP response convention khác. Đây là quyết định contract API.

### Có nên tự động chuyển page=3 về page=2?

Không có một quy tắc chung. Một API có thể:

- Trả trang rỗng kèm metadata.
- Trả lỗi “page out of range”.
- Điều hướng về trang cuối ở UI.

Nếu tự điều hướng, phải nói rõ cho client rằng pageIndex trả về có thể khác pageIndex được yêu cầu. Đừng âm thầm thay offset trong repository khiến API khó dự đoán.

## 26. Không cần COUNT: slice pagination bằng pageSize+1

Truy vấn COUNT có thể rất tốn chi phí với dữ liệu lớn và filter phức tạp. Nếu UI chỉ cần nút **“Xem tiếp”** thay vì “Trang 3/127”, có thể không chạy count.

Ý tưởng:

1. Với `pageSize = 20`, query lấy **tối đa 21** hàng.
2. Nếu trả 21, biết rằng còn ít nhất một hàng tiếp theo ở thời điểm truy vấn.
3. Chỉ đưa tối đa 20 hàng vào response.
4. Không cần totalElements chính xác.

~~~java
public record SliceResult<T>(
        List<T> content,
        int pageIndex,
        int pageSize,
        boolean hasNext) {
}
~~~

Ví dụ:

~~~java
int size = 20;
int offset = offsetOf(pageIndex, size);

List<OrderListRow> fetched = em.createQuery(
        jpql, OrderListRow.class)
    .setParameter("tenant", tenantId)
    .setFirstResult(offset)
    .setMaxResults(size + 1)
    .getResultList();

boolean hasNext = fetched.size() > size;

List<OrderListRow> content =
    List.copyOf(
        fetched.subList(0, Math.min(size, fetched.size()))
    );

SliceResult<OrderListRow> result =
    new SliceResult<>(content, pageIndex, size, hasNext);
~~~

`jpql` ở đây là chuỗi constructor projection có `ORDER BY` ổn định, được định nghĩa trong repository theo bộ lọc tương ứng.

### Vì sao khác với tải tất cả rồi subList?

Ở đây `subList` chỉ cắt **tối đa size+1 kết quả đã được giới hạn tại JPA query**. Ta không nạp toàn bộ database trước.

### Cẩn trọng với size = Integer.MAX_VALUE

`size + 1` có thể overflow. Một API có page size tối đa nhỏ như 100 sẽ tránh trường hợp này. Nếu viết helper tổng quát, kiểm tra `size < Integer.MAX_VALUE` trước khi tăng.

### Slice vẫn chịu nhược điểm OFFSET

Phương án này bỏ COUNT, nhưng vẫn dùng `setFirstResult(pageIndex*size)`. Với page rất sâu, database có thể phải quét/bỏ qua nhiều hàng, và dữ liệu thay đổi giữa các trang vẫn gây dịch offset. Những trường hợp đó có thể cần keyset pagination.

## 27. Vì sao offset lớn có thể chậm?

Một request:

~~~text
pageIndex = 50000
pageSize  = 20
offset    = 1.000.000
~~~

nghĩa là ứng dụng yêu cầu bỏ qua một triệu kết quả trước khi lấy tối đa 20.

Ngay cả với index phù hợp, database có thể vẫn cần **đi qua hoặc xác định rất nhiều hàng** để biết 20 hàng tiếp theo theo đúng thứ tự.

### Sơ đồ

~~~text
OFFSET 0:
    [đọc 20 hàng] -> trả 20

OFFSET 1.000.000:
    [đi qua 1.000.000 hàng]
    [đọc 20 hàng tiếp theo] -> trả 20
~~~

Thực thi vật lý phụ thuộc query plan và DBMS, nhưng chi phí skip tăng theo offset là một nhược điểm phổ biến của offset pagination.

### Index theo filter và order

Ví dụ query thường gặp:

~~~sql
WHERE tenant_id = ?
  AND status = ?
ORDER BY placed_at DESC, id DESC
~~~

Index ứng viên:

~~~sql
CREATE INDEX idx_orders_tenant_status_placed_id
ON purchase_orders(
    tenant_id,
    status,
    placed_at DESC,
    id DESC
);
~~~

Đây là **đề xuất minh họa**, không phải bảo đảm tối ưu cho mọi DBMS. Việc index có hiệu quả hay không còn phụ thuộc selectivity, kích thước hàng, INCLUDE/covering columns, stats, query plan và tỷ lệ read/write.

## 28. Keyset pagination: khi nào nên cân nhắc?

**Keyset (seek) pagination** không dùng vị trí số học để bỏ qua hàng, mà dùng **khóa sắp xếp cuối trang trước** làm cursor.

Với:

~~~jpql
ORDER BY o.placedAt DESC, o.id DESC
~~~

trang đầu có thể:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenant
ORDER BY o.placedAt DESC, o.id DESC
~~~

và:

~~~java
query.setMaxResults(20);
~~~

Giả sử phần tử cuối trang đầu là:

~~~text
placedAt = 2027-06-01T10:00:00Z
id = 500
~~~

Trang tiếp theo:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenant
  AND (
       o.placedAt < :lastPlacedAt
       OR (
           o.placedAt = :lastPlacedAt
           AND o.id < :lastId
       )
  )
ORDER BY o.placedAt DESC, o.id DESC
~~~

Áp:

~~~java
query.setMaxResults(20);
~~~

**Không dùng `setFirstResult(20)` ở trang tiếp theo** theo mô hình keyset này. Cursor thay cho offset.

### Lợi ích thường có

- Hiệu quả tốt hơn cho cuộn tiếp liên tục trên tập rất lớn khi có index phù hợp.
- Hạn chế một số lỗi dịch offset do hàng mới được chèn trước cursor.
- Không cần tính pageIndex cực lớn.

### Đánh đổi

- Không dễ nhảy thẳng tới “Trang 5.000”.
- Cursor phải chứa đầy đủ các sort keys cần thiết.
- Sort phải có tính xác định; key null cần quy tắc riêng.
- Khi sort field bị chỉnh sửa, vị trí bản ghi cũng có thể thay đổi.
- Cursor có thể cần được ký/mã hóa để client không sửa thông tin nhạy cảm.
- Tổng số kết quả không tự có.

### Khi nào OFFSET vẫn tốt?

Đối với trang quản trị có vài nghìn bản ghi, cần nhảy tới trang N, bộ lọc ổn định và tải dữ liệu vừa phải, `setFirstResult/setMaxResults` vẫn là giải pháp đơn giản, dễ dùng.

**Keyset không thay thế offset trong mọi tình huống; nó là một lựa chọn cho mục tiêu hiệu năng và điều hướng khác.**

## 29. Dữ liệu thay đổi giữa hai request: trùng và bỏ sót

Giả sử Order theo ID giảm dần:

~~~text
Ban đầu:
[100, 99, 98, 97, 96, 95]

pageSize = 3
Trang 1 -> [100, 99, 98]
~~~

Trước khi người dùng mở trang 2, một Order mới ID=101 được tạo:

~~~text
Sau INSERT:
[101, 100, 99, 98, 97, 96, 95]
~~~

Với OFFSET 3:

~~~text
Trang 2 -> [98, 97, 96]
~~~

Order 98 **bị lặp** giữa trang 1 và trang 2 dù có ORDER BY id DESC hoàn toàn xác định.

### Trường hợp DELETE

Nếu một hàng đứng trước offset bị xóa, các hàng còn lại dịch lên. Kết quả của trang sau có thể **bỏ qua** một ID chưa từng được người dùng thấy.

### Phân biệt hai lỗi

| Hiện tượng | Nguồn gốc |
| --- | --- |
| Cùng timestamp, DB trả thứ tự khác nhau | Thiếu tie-breaker trong ORDER BY |
| Có INSERT/DELETE giữa request, OFFSET dịch | Tập dữ liệu thay đổi giữa các lần phân trang |

Tie-breaker giải quyết vấn đề đầu tiên nhưng **không triệt tiêu vấn đề thứ hai**.

### Các giải pháp theo yêu cầu

- Chấp nhận eventual consistency cho feed/quản trị thông thường.
- Dùng keyset pagination khi phù hợp.
- Giữ snapshot/report version cho nghiệp vụ cần duyệt một tập cố định.
- Dùng transaction isolation/snapshot trong một tác vụ server-side dài khi phù hợp, nhưng không giữ một transaction DB mở suốt nhiều lần người dùng bấm trang trong thời gian dài.

## 30. Count query và page query có thể không cùng snapshot

Luồng điển hình:

~~~text
T1: SELECT COUNT(*) -> 125
T2: Transaction khác INSERT 5 Order -> COMMIT
T3: SELECT page -> dữ liệu đã có thêm 5 Order
~~~

Response có thể chứa `totalElements=125` nhưng `content` được lấy từ tập dữ liệu có 130 hàng tại T3.

### Trong cùng transaction có chắc nhất quán không?

Không mặc định. Mức isolation như READ COMMITTED có thể cho các statement đọc committed snapshot khác nhau (tùy DBMS). Muốn snapshot nhất quán cho một thao tác đọc nhiều query, cần chọn transaction/isolation phù hợp với hệ quản trị và yêu cầu nghiệp vụ.

### Không dùng @Transactional như phép màu

Spring `@Transactional(readOnly=true)` cho phép quản lý transaction và có thể tối ưu read behavior, nhưng **không tự bảo đảm REPEATABLE READ hoặc SERIALIZABLE**. JPA thuần cũng không định nghĩa một isolation mặc định đồng nhất trên mọi DBMS.

### Thiết kế API phải chấp nhận mức nhất quán hợp lý

Với trang quản trị thông thường, tổng số có thể là số liệu gần đúng tại thời điểm truy vấn. Với xuất báo cáo tài chính cần chốt sổ, phải xác định snapshot/kỳ dữ liệu hoặc read model versioned, không dựa vào request trang rời rạc.

## 31. Không thay filter/sort giữa các trang mà giữ offset cũ

Giả sử người dùng đang ở:

~~~text
pageIndex = 6
status = PAID
sort = placedAt DESC
~~~

Sau đó đổi filter:

~~~text
status = CANCELLED
~~~

Tập kết quả có thể chỉ còn 15 Order. Nếu UI vẫn gửi pageIndex=6, nó nhận trang rỗng và có thể nhầm là “không có Order CANCELLED”.

### Quy tắc giao diện

Khi filter hoặc sort thay đổi:

1. Thường nên reset pageIndex về 0.
2. Gửi filter/sort đầy đủ ở mỗi request.
3. Không tái sử dụng cursor của tập dữ liệu cũ với filter/sort mới.
4. Nếu URL lưu state, cập nhật query parameters tương ứng.

### Tại sao không để repository tự reset âm thầm?

Repository chỉ biết offset và query. UI/API cần quyết định cách chuyển trang theo tương tác người dùng. Nếu repository tự đổi pageIndex mà không nói, response metadata trở nên khó đoán và có thể gây điều hướng sai.

## 32. Sort động: chỉ chấp nhận các trường đã whitelist

Một API có thể hỗ trợ:

~~~text
sort=placedAt,desc
sort=totalAmount,asc
sort=id,desc
~~~

Không nên nối nguyên chuỗi sort do user nhập vào JPQL:

~~~java
String jpql =
    "SELECT o FROM PurchaseOrder o ORDER BY " + rawSort;
~~~

Đây là lỗi về bảo mật, tính đúng đắn và khả năng kiểm soát query.

### Enum sort

~~~java
public enum OrderSort {
    NEWEST,
    AMOUNT_ASC,
    AMOUNT_DESC
}
~~~

Ánh xạ từ enum sang những mảnh cố định:

~~~java
String orderBy = switch (sort) {
    case NEWEST ->
        "o.placedAt DESC, o.id DESC";
    case AMOUNT_ASC ->
        "o.totalAmount ASC, o.id ASC";
    case AMOUNT_DESC ->
        "o.totalAmount DESC, o.id DESC";
};
~~~

Đoạn này là ví dụ xây JPQL với các mảnh **cố định thuộc whitelist của ứng dụng**, không lấy trực tiếp tên cột hoặc cú pháp JPQL do client cung cấp.

### Luôn có tie-breaker

Hai Order có cùng totalAmount cần được sắp xếp bằng ID hoặc khóa duy nhất khác để tránh thứ tự nhập nhằng.

### Sort theo field nullable

Một field nullable có thể được DBMS đặt NULL đầu hoặc cuối khác nhau theo dialect. Nếu product requirement yêu cầu “NULL luôn cuối”, phải thiết kế CASE/order expression hoặc cơ chế provider/DB phù hợp; không mặc định ASC/DESC xử lý NULL giống nhau ở mọi database.

## 33. Giới hạn bảo mật: filter trước phân trang

Trong ứng dụng multi-tenant, không được:

~~~java
List<PurchaseOrder> page =
    queryAllTenants()
        .setFirstResult(offset)
        .setMaxResults(size)
        .getResultList();

return page.stream()
    .filter(o -> o.getTenantId().equals(currentTenant))
    .toList();
~~~

Cách này vừa có nguy cơ lộ dữ liệu nếu logic lọc sai, vừa làm trang có số item thất thường và offset/count không còn đúng đối với tenant.

**Đúng:** áp `WHERE o.tenantId = :tenantId` và mọi điều kiện authorization **trước khi phân trang trên database**.

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
ORDER BY o.placedAt DESC, o.id DESC
~~~

Count query cũng phải có điều kiện tenant giống query data.

### Tenant ID không được lấy tùy tiện từ client

Thông số tenant trong repository nên được xác định từ authentication/authorization context đáng tin, không chỉ dựa vào request JSON. Dù query trả DTO và không có field nhạy cảm, số lượng bản ghi cũng có thể là thông tin cần bảo vệ.

### Dữ liệu liên kết cần cùng phạm vi quyền

Nếu Customer có tenant riêng, FK và dữ liệu phải được thiết kế để không thể tham chiếu chéo tenant ngoài ý định. `WHERE o.tenantId=:tenantId` không tự chứng minh mọi association đã đúng owner/security policy.

## 34. Read-only transaction và DTO

Với Spring:

~~~java
@Transactional(readOnly = true)
public PageResult<OrderListRow> findOrders(...) {
    // Thực hiện data query và count query.
}
~~~

`readOnly=true` là một hint/cấu hình Spring-specific có thể ảnh hưởng flush mode hoặc connection behavior. Nó **không phải flag JPA chuẩn** và không bảo đảm mọi DBMS từ chối mọi write.

### Vì sao DTO hữu ích trong service read-only?

- Không cần đưa managed entities ra controller.
- Không có lazy collection bị serializer truy cập sau service.
- Giảm rủi ro dirty checking do sửa entity ngoài ý định.
- Chỉ chứa field được contract API cho phép.

### Nhưng dữ liệu cần bảo mật vẫn phải lọc

DTO có ít field không tự tạo authorization; vẫn cần tenant/ACL predicate và các giới hạn phù hợp.

## 35. EntityManager lifecycle và lazy loading trên trang

Với entity:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

Repository phân trang Orders rồi trả entity cho controller:

~~~java
return em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "ORDER BY o.id",
    PurchaseOrder.class
).setMaxResults(20).getResultList();
~~~

Nếu persistence context đã đóng, controller gọi `order.getLines()` có thể không initialize được collection. Trong Hibernate, điều này có thể phát sinh `LazyInitializationException`.

Nếu session vẫn mở nhờ Open Session in View, serializer có thể gây **N+1 SQL ngay trong quá trình trả JSON**. Do đó không nên xem phân trang 20 Order là toàn bộ chi phí nếu mỗi Order kéo theo các association.

### Đọc danh sách có kế hoạch rõ

Phù hợp:

~~~text
Repository:
  SELECT DTO đúng 20 Order rows
Service:
  ghép metadata page
Controller:
  serialize DTO, không lazy loading bất ngờ
~~~

Tránh:

~~~text
Repository:
  SELECT 20 Order entities
Controller:
  serialize toàn bộ object graph
  -> Query N+1/recursion/exception
~~~

## 36. Phân trang không tự làm batch processing an toàn

Đôi khi ứng dụng có một job xử lý nhiều triệu record và dùng:

~~~java
for (int page = 0; ; page++) {
    List<PurchaseOrder> batch =
        findPage(page, 1000);
    if (batch.isEmpty()) break;
    process(batch);
}
~~~

Nếu `process(batch)` **cập nhật status** và filter query chỉ lấy `PENDING`, tập kết quả bị thu hẹp sau mỗi batch. Offset trang sau có thể bỏ qua những Order chưa xử lý.

Ví dụ:

~~~text
Ban đầu PENDING: [1,2,3,4,5,6]
Page size=2
Page 0 -> [1,2] -> đổi sang PAID
Còn PENDING: [3,4,5,6]
Page 1 OFFSET 2 -> [5,6]
=> Bỏ sót [3,4]
~~~

### Chiến lược batch thích hợp

- Dùng keyset/cursor trên một khóa tiến lên, giữ bộ lọc và invariant rõ.
- Hoặc luôn đọc trang đầu `OFFSET 0` khi chính filter bị thay đổi, kết hợp idempotency/termination condition.
- Hoặc chia dữ liệu thành ranges ổn định theo ID.
- Hoặc dùng stream/cursor của DB theo quy tắc transaction/lifetime phù hợp.

**Offset pagination phù hợp cho giao diện người dùng nhưng không tự là chiến lược quét/ghi toàn bộ dữ liệu an toàn**.

### Persistence context memory

Một batch job load entity và giữ chúng trong EntityManager lâu có thể làm first-level cache phình to. Cần xem transaction size, flush/clear và ownership của objects; nhưng `clear()` detach entities, nên phải thực hiện có chủ đích, không gọi tùy tiện khi còn pending changes.

## 37. N+1 khi ánh xạ DTO từ entity sau query

Một kiểu code:

~~~java
List<PurchaseOrder> orders =
    findPagedOrders(pageIndex, pageSize);

List<OrderListRow> rows = orders.stream()
    .map(o -> new OrderListRow(
        o.getId(),
        o.getPlacedAt(),
        o.getStatus(),
        o.getCustomer().getName(),
        o.getTotalAmount()))
    .toList();
~~~

Nếu Order.customer LAZY, `getCustomer().getName()` có thể kích hoạt SELECT phụ cho từng Customer chưa loaded. Có phân trang 20 Order vẫn có thể có thêm gần 20 SELECT.

### Hai hướng tốt hơn

**Hướng A: trực tiếp DTO projection trong JPQL.**

~~~jpql
SELECT NEW com.example.shop.dto.OrderListRow(
    o.id, o.placedAt, o.status, c.name, o.totalAmount
)
FROM PurchaseOrder o JOIN o.customer c
...
~~~

**Hướng B: fetch join to-one nếu cần managed Order.**

~~~jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE ...
ORDER BY o.placedAt DESC, o.id DESC
~~~

Sau đó chuyển thành DTO trong transaction. Với to-one, điều này thường tránh fan-out của to-many, nhưng vẫn cần đo SQL và semantics trên provider cụ thể.

## 38. Không nhầm LIMIT/OFFSET của SQL với thứ tự logic

Trình tự diễn giải một truy vấn điển hình:

~~~text
FROM / JOIN
     |
     v
WHERE
     |
     v
GROUP BY / HAVING (nếu có)
     |
     v
SELECT
     |
     v
ORDER BY
     |
     v
OFFSET / LIMIT
     |
     v
ResultList
~~~

Đây là **sơ đồ ngữ nghĩa logic**, không mô tả kế hoạch thực thi vật lý mà DBMS bắt buộc phải tuân theo từng bước.

### Ví dụ COUNT

Nếu query:

~~~jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :status
~~~

thì COUNT tính trên tập Order đã được lọc, rồi trả một scalar. Không có lý do áp LIMIT/OFFSET kiểu phân trang root Orders để hy vọng COUNT chỉ đếm 20 Order.

### Ví dụ GROUP BY

Nếu query:

~~~jpql
SELECT o.status, COUNT(o)
FROM PurchaseOrder o
GROUP BY o.status
ORDER BY o.status
~~~

thì pagination áp trên **các nhóm status** được trả, không trên từng PurchaseOrder trước GROUP BY.

## 39. Tương tác với DISTINCT, UNION và native CTE

Trong JPQL chuẩn, các cấu trúc hỗ trợ phụ thuộc phiên bản Jakarta Persistence và provider; các tính năng SQL như CTE, UNION hoặc window function có thể không portable giữa các JPA stacks.

Với native SQL có CTE:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.id,
        o.placed_at,
        o.status,
        ROW_NUMBER() OVER (
            ORDER BY o.placed_at DESC, o.id DESC
        ) AS row_number
    FROM purchase_orders o
    WHERE o.tenant_id = ?
)
SELECT id, placed_at, status
FROM ranked_orders
WHERE row_number BETWEEN ? AND ?
ORDER BY row_number;
~~~

Đây là **native SQL minh họa** với window function. Nó tự xác định paging theo row_number; không nên tiếp tục gọi setFirstResult/setMaxResults mà không có lý do rõ.

### Khi nào cần native pagination phức tạp?

- DBMS hỗ trợ window functions và báo cáo cần ranking phức tạp.
- Truy vấn nhóm/CTE khó biểu diễn portable bằng JPQL.
- Yêu cầu hiệu năng đủ lớn để tối ưu theo dialect.

Nhưng với một danh sách Order đơn giản, `setFirstResult`/`setMaxResults` trên TypedQuery vẫn dễ đọc, ít phụ thuộc DBMS hơn.

## 40. Cách đọc log và EXPLAIN cho query phân trang

Trong môi trường test/development, quan sát:

- SQL có WHERE đúng tenant và filter không?
- Có ORDER BY ổn định không?
- Provider dùng LIMIT/OFFSET, FETCH hoặc cấu trúc khác?
- SQL có JOIN FETCH collection làm nhân row không?
- Có SELECT phụ từ các lazy associations trong lúc serialize không?
- Số row JDBC và số DTO/entity materialized là bao nhiêu?
- Query count có phải JOIN không cần thiết hay không?
- Offset lớn có scan/sort nhiều row không?

### Ví dụ query plan

Với:

~~~sql
EXPLAIN
SELECT id, placed_at, total_amount
FROM purchase_orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY placed_at DESC, id DESC
LIMIT 20 OFFSET 10000;
~~~

Ở PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` cho phép quan sát execution thực tế và buffer I/O, nhưng **ANALYZE thực thi câu query**, nên cần cân nhắc chi phí/side effects trước khi áp dụng lên workload nặng. Với SELECT phân trang, việc đo trên dữ liệu đại diện giúp hiểu vì sao offset lớn chậm.

### Index không thay thế tính đúng đắn

Một index tốt có thể giảm thời gian lấy trang, nhưng không sửa query thiếu ORDER BY, count sai do JOIN hoặc lộ dữ liệu tenant. Ưu tiên **đúng semantics**, sau đó tối ưu.

## 41. Bộ dữ liệu kiểm thử

Chuẩn bị các Order:

| ID | Tenant | status | placedAt |
| ---: | ---: | --- | --- |
| 1 | 10 | PAID | 2027-06-01T10:00:00Z |
| 2 | 10 | PAID | 2027-06-01T10:00:00Z |
| 3 | 10 | PAID | 2027-06-01T11:00:00Z |
| 4 | 10 | PENDING | 2027-06-02T08:00:00Z |
| 5 | 10 | PAID | 2027-06-03T08:00:00Z |
| 6 | 20 | PAID | 2027-06-04T08:00:00Z |

Filter:

~~~text
tenantId=10
status=PAID
ORDER BY placedAt DESC, id DESC
~~~

Tập kết quả đầy đủ:

~~~text
[5, 3, 2, 1]
~~~

Với pageSize=2:

~~~text
pageIndex=0 -> [5, 3]
pageIndex=1 -> [2, 1]
pageIndex=2 -> []
totalElements=4
totalPages=2
~~~

Hai Order ID 1 và 2 có cùng placedAt, vì thế tie-breaker ID DESC quyết định 2 đứng trước 1.

## 42. Các integration tests quan trọng

### Test trang đầu

~~~java
List<OrderListRow> first =
    findPage(tenantId, filter, 0, 2).content();

assertEquals(
    List.of(5L, 3L),
    first.stream().map(OrderListRow::id).toList());
~~~

### Test trang thứ hai

~~~java
List<OrderListRow> second =
    findPage(tenantId, filter, 1, 2).content();

assertEquals(
    List.of(2L, 1L),
    second.stream().map(OrderListRow::id).toList());
~~~

### Test tổng

~~~java
PageResult<OrderListRow> page =
    findPage(tenantId, filter, 0, 2);

assertEquals(4L, page.totalElements());
assertEquals(2L, page.totalPages());
assertTrue(page.hasNext());
~~~

Đây là các đoạn JUnit-style minh họa, giả sử test fixture và helper service đã được thiết lập, static imports assertions phù hợp và truy vấn được chạy bằng EntityManager/provider thật.

### Test thêm cho các trường hợp biên

1. Filter không có kết quả: content rỗng, total=0, totalPages=0.
2. Trang cuối thiếu item: lấy đúng số item còn lại.
3. Page ngoài phạm vi: content rỗng nhưng total vẫn phản ánh dữ liệu.
4. pageIndex âm: từ chối input.
5. pageSize bằng 0: từ chối theo policy API.
6. pageSize vượt giới hạn: từ chối.
7. pageIndex × pageSize vượt int: từ chối trước khi gọi JPA.
8. Hai hàng có cùng sort field: tie-breaker cho thứ tự xác định.
9. Tenant khác có hàng mới hơn: không lọt vào page/count.
10. Status/date filter thay đổi: query data và count nhất quán.
11. JOIN to-many nhiều matching lines: không đếm trùng root.
12. Query DTO không tạo N+1 lúc serialize.
13. Fetch join collection không được dùng trực tiếp cho page root ngoài chủ đích.

### Vì sao cần database integration test?

Mock query trả list có thể xác nhận ứng dụng đã gọi `setFirstResult(20)` và `setMaxResults(10)`, nhưng **không chứng minh** SQL sinh ra có ORDER BY đúng hoặc JOIN làm sai phân trang hay không. Chỉ integration test với provider/DBMS phù hợp mới phát hiện được nhiều vấn đề mapping, dialect và result cardinality.

## 43. Kiểm thử concurrency cho offset pagination

Một test riêng cho dữ liệu thay đổi có thể:

1. Transaction A đọc page 0 với sort ID DESC.
2. Transaction B INSERT Order có sort key mới nhất rồi COMMIT.
3. Transaction A hoặc request mới đọc page 1.
4. Quan sát ID có thể lặp hoặc bị bỏ qua theo isolation/snapshot.

Đây **không nhất thiết là một bug của JPA**. Nó là thuộc tính của offset-based pagination trên tập dữ liệu thay đổi.

### Test dùng transaction mới khi cần

Nếu mục tiêu xác minh trạng thái đã commit, đừng kiểm tra bằng một EntityManager còn giữ các entity managed từ trước hoặc dùng snapshot cũ mà không hiểu isolation. Thiết kế test với transaction boundaries rõ ràng.

### Không dùng Thread.sleep để đảm bảo thứ tự race

Với concurrency test, dùng barrier/latch hoặc cơ chế điều phối transaction có kiểm soát, tránh test phụ thuộc tốc độ máy.

## 44. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `setFirstResult(pageIndex)` | Trang thứ N chỉ bỏ N hàng, không phải N × size | Tính offset = pageIndex × pageSize |
| UI 1-based nhưng backend coi 0-based | Bỏ qua trang đầu | Chuẩn hóa quy ước page number |
| Tính offset bằng int rồi cast long | Overflow trước khi cast | Ép long trước phép nhân |
| size=0 hoặc âm | Trang vô nghĩa/lỗi API | Validate pageSize dương và có giới hạn |
| Offset âm | IllegalArgumentException | Validate pageIndex >= 0 |
| Không có ORDER BY | Các trang không có thứ tự ổn định | ORDER BY với tie-breaker duy nhất |
| Chỉ ORDER BY placedAt | Hòa timestamp tạo thứ tự nhập nhằng | Thêm ID/key duy nhất |
| Lọc tenant sau khi lấy page | Sai số item/count và rủi ro rò rỉ | Lọc trong WHERE trước pagination |
| Data filter khác count filter | Tổng trang sai | Tái sử dụng logic filter |
| Đặt setFirstResult lên count query | Count không còn ý nghĩa | Chỉ paginate data query |
| Dùng COUNT(o) sau JOIN to-many | Count trùng Order | COUNT DISTINCT hoặc EXISTS |
| JOIN FETCH lines và LIMIT trực tiếp | Cắt root/collection, pagination in memory | Page IDs trước rồi fetch |
| Thấy DISTINCT liền tin đã tránh fan-out | SQL vẫn nhân hàng theo collection | Xem cardinality và query plan |
| Gửi entity LAZY ra JSON | Lazy exception/N+1 trong serializer | DTO projection |
| Tải toàn bộ list rồi subList | Tốn RAM/I/O | Áp giới hạn tại Query |
| Chạy COUNT mọi request dù không cần total | COUNT đắt trên dataset lớn | Slice size+1 |
| Lấy trang sâu với OFFSET lớn | Database scan/skip nhiều rows | Keyset pagination hoặc index/report design |
| Đổi filter nhưng giữ page 99 | Trang rỗng gây hiểu sai | Reset page về 0 |
| Ghép raw ORDER BY từ input | Query injection/lỗi sort | Whitelist sort keys |
| Sort theo field to-many mơ hồ | Không biết Order đại diện theo line nào | Tổng hợp sort key hoặc query rõ |
| Page+count khác snapshot | Metadata có thể lệch | Isolation/snapshot/cursor policy |
| Job cập nhật filter rồi tăng offset | Bỏ sót hàng cần xử lý | Keyset hoặc batch theo ID ổn định |
| setMaxResults mặc định là pageSize | Query trả quá nhiều rows | Đặt giới hạn rõ ở mọi endpoint |
| Dùng Native SQL và JPA pagination đồng thời | Pagination hai tầng | Chỉ chọn một cơ chế |
| Count tổng Products cho trang Categories GROUP BY | totalElements sai đơn vị | Đếm số nhóm thỏa HAVING |
| Query không có giới hạn tenant/ACL | Lộ dữ liệu qua content và count | Scope authorization từ DB query |

## 45. Một checklist thiết kế API phân trang

Trước khi đưa một endpoint phân trang vào production:

1. **Định nghĩa page index:** 0-based hay 1-based ở API?
2. **Giới hạn size:** mặc định, tối thiểu, tối đa?
3. **Validate offset:** dùng phép nhân long và kiểm tra int range.
4. **Chọn đơn vị phân trang:** Order, OrderLine, Customer hay một hàng aggregate?
5. **Áp filter bắt buộc:** tenant/ACL và điều kiện nghiệp vụ trước pagination.
6. **Chuẩn hóa filter tùy chọn:** null, empty collection, date ranges.
7. **ORDER BY ổn định:** có ID/key duy nhất làm tie-breaker.
8. **Whitelist sort:** không đưa raw input vào JPQL/SQL.
9. **Chọn kiểu kết quả:** entity hay DTO projection?
10. **Kiểm tra quan hệ:** có JOIN to-many gây nhân hàng không?
11. **Tránh collection fetch join trực tiếp với pagination root.**
12. **Count đúng đơn vị:** COUNT root, COUNT DISTINCT hoặc count groups tùy query.
13. **Có thật cần total?** Nếu không, xem slice size+1.
14. **Xác định consistency:** data và count có cần một snapshot không?
15. **Đo offset sâu:** xem index và query plan.
16. **Cân nhắc keyset** nếu chỉ cuộn tiếp và dữ liệu rất lớn/thay đổi nhanh.
17. **Test trên DBMS thật:** ORDER BY, JOIN, COUNT, page cuối, input lỗi.
18. **Không để serializer tự lazy-load graph.**
19. **Giám sát hiệu năng:** statement count, query time, response size.
20. **Định nghĩa response contract:** page/size/total/hasNext/page out-of-range.

## 46. Bài tập thực hành

### Bài 1 — Tính offset

API dùng pageIndex bắt đầu 0, pageSize=25. Tính `setFirstResult` cho pageIndex=4.

**Gợi ý:** `4 × 25 = 100`; maxResults vẫn là 25.

### Bài 2 — Đánh số trang từ 1

UI truyền `pageNumber=3`, size=10. Backend cần truyền offset bao nhiêu?

**Gợi ý:** `(3-1)×10=20`.

### Bài 3 — Trang cuối

Có 62 bản ghi, size=20. PageIndex=3 trả tối đa bao nhiêu phần tử?

**Gợi ý:** hai phần tử; totalPages=4.

### Bài 4 — Tìm lỗi

~~~java
query.setFirstResult(pageIndex);
query.setMaxResults(size);
~~~

Điểm sai?

**Gợi ý:** setFirstResult cần offset, không phải pageIndex.

### Bài 5 — SQL không có ORDER BY

Một query có WHERE nhưng không ORDER BY. Có thể đảm bảo page 1 và page 2 không trùng dữ liệu ngay cả khi database không có insert/delete không?

**Gợi ý:** không có thứ tự xác định, kết quả có thể khác khi execution plan thay đổi.

### Bài 6 — Tie-breaker

Order được sort theo placedAt DESC, nhiều đơn có cùng thời điểm. Thêm trường nào để tạo thứ tự ổn định?

**Gợi ý:** khóa ID duy nhất với cùng chiều sắp xếp, ví dụ `o.id DESC`.

### Bài 7 — DTO và entity

Màn hình chỉ cần Order ID, status và customerName. Tại sao DTO projection thường phù hợp hơn trả PurchaseOrder entity?

**Gợi ý:** chỉ chọn field cần, tránh lazy loading/serialization graph và không expose managed state.

### Bài 8 — Count query

Trang có 15 Order nhưng có tổng 180 Order phù hợp filter. `setMaxResults(15)` tự trả total=180 không?

**Gợi ý:** không. Cần count query hoặc một cơ chế metadata khác.

### Bài 9 — Đếm sai do JOIN

Một Order có ba OrderLine khớp SKU filter. `COUNT(o)` sau JOIN có thể trả mấy cho Order đó?

**Gợi ý:** ba; nếu cần đếm Order, dùng `COUNT(DISTINCT o.id)` hoặc EXISTS.

### Bài 10 — Fetch join collection

Page size=10 nhưng query LEFT JOIN FETCH lines. Vì sao LIMIT 10 ở SQL có thể trả ít hơn 10 Orders?

**Gợi ý:** một Order tạo nhiều hàng SQL do có nhiều lines.

### Bài 11 — Hai bước

Trình bày hai bước fetch collection mà vẫn phân trang Order root chính xác.

**Gợi ý:** query IDs có offset/limit; query thứ hai FETCH lines theo IDs, rồi khôi phục thứ tự.

### Bài 12 — Slice

UI chỉ có nút “Xem tiếp”, không cần total. Với size=20, query cần lấy tối đa bao nhiêu dòng để biết hasNext?

**Gợi ý:** 21, sau đó chỉ trả 20 item.

### Bài 13 — Offset lớn

PageIndex=100000 và size=20. Offset là bao nhiêu và vì sao query có thể chậm?

**Gợi ý:** 2.000.000; DB có thể phải skip/scan rất nhiều hàng.

### Bài 14 — Keyset

Với `ORDER BY placedAt DESC, id DESC`, cursor cuối trang là (T, ID). Điều kiện lấy trang kế tiếp là gì?

**Gợi ý:** `placedAt < T OR (placedAt=T AND id<ID)`.

### Bài 15 — Data thay đổi

Người dùng đã xem trang 0, sau đó một Order mới được chèn ở đầu. Trang 1 dùng OFFSET có thể gặp gì?

**Gợi ý:** một Order đã xem có thể xuất hiện lại; tie-breaker không giải quyết dịch offset do INSERT.

### Bài 16 — Count và snapshot

Count query chạy trước, một transaction khác insert rồi commit, data query chạy sau. Tổng số và content có chắc cùng tập dữ liệu không?

**Gợi ý:** không, phụ thuộc isolation và thời điểm đọc.

### Bài 17 — Multi-tenant

Nếu lấy page toàn bộ Order rồi lọc tenant bằng Stream Java, điều gì sai?

**Gợi ý:** sai đơn vị phân trang/count và có nguy cơ lộ dữ liệu; filter trong WHERE từ database.

### Bài 18 — Job cập nhật

Một batch job phân trang các Order PENDING rồi đổi chúng thành PAID. Vì sao dùng pageIndex++ có thể bỏ sót Order?

**Gợi ý:** các Order đã cập nhật biến mất khỏi tập PENDING làm các offset bị dịch.

### Bài 19 — Dynamic sort

Người dùng gửi sort field tùy ý từ URL. Có nên nối chuỗi trực tiếp vào JPQL không?

**Gợi ý:** không. Ánh xạ input sang danh sách sort fields được phép và thêm tie-breaker.

### Bài 20 — Criteria API

Trong Criteria API, `setFirstResult` gọi trên `CriteriaQuery` hay `TypedQuery`?

**Gợi ý:** trên TypedQuery do `em.createQuery(criteriaQuery)` trả về.

### Bài 21 — Grouped pagination

Query GROUP BY Category trả mỗi Category một hàng. Khi lấy `setMaxResults(10)`, đang phân trang Product hay Category groups?

**Gợi ý:** các hàng nhóm Category của kết quả.

### Bài 22 — Native SQL

Một câu native SQL đã chứa LIMIT/OFFSET. Có nên tiếp tục thêm JPA `setFirstResult/setMaxResults` để “chắc chắn” phân trang không?

**Gợi ý:** không mặc định; tránh áp pagination hai lần.

### Bài 23 — Biên offset

Với `pageIndex = 2_000_000_000` và `size=100`, vì sao không dùng int multiplication?

**Gợi ý:** tràn int; tính long, kiểm tra với Integer.MAX_VALUE rồi từ chối request.

### Bài 24 — Query N+1 sau pagination

Query lấy 20 Orders nhưng controller gọi Customer getter từng Order. Vì sao số SELECT có thể lớn hơn 1?

**Gợi ý:** customer LAZY có thể nạp bằng SELECT phụ; dùng projection hoặc fetch plan to-one.

### Bài 25 — Định nghĩa trang không có dữ liệu

TotalElements=0, size=20. TotalPages nên bằng bao nhiêu theo công thức toán học đã dùng?

**Gợi ý:** 0; UI có thể chọn cách hiển thị “trang rỗng” riêng.

## 47. Bảng ghi nhớ nhanh

| Nhu cầu | Cách giải quyết |
| --- | --- |
| Bỏ qua N kết quả đầu | `setFirstResult(N)` |
| Lấy tối đa M kết quả | `setMaxResults(M)` |
| Trang 0-based | `offset = pageIndex × size` |
| Trang 1-based | `offset = (pageNumber - 1) × size` |
| Tránh overflow | Tính offset bằng long rồi kiểm tra int |
| Kết quả trang ổn định trên tập tĩnh | `ORDER BY sortKey, uniqueId` |
| Chỉ lấy vài field | `SELECT NEW ...DTO(...)` |
| TotalElements | Query COUNT riêng |
| TotalPages | `ceil(totalElements / pageSize)` |
| Không cần total chính xác | Slice lấy tối đa `size+1` |
| Filter theo to-many | DISTINCT root hoặc EXISTS |
| Count root sau JOIN to-many | `COUNT(DISTINCT root.id)` |
| Fetch collection + paging root | Page IDs rồi fetch collection |
| Lọc tenant | WHERE trước pagination ở data và count |
| Sort động | Whitelist và tie-breaker |
| Offset quá sâu | Xem keyset/cursor pagination |
| Query dữ liệu thay đổi | Chấp nhận drift hoặc snapshot/cursor policy |
| Dùng Criteria | Create TypedQuery rồi setFirstResult/setMaxResults |
| Dùng Native SQL | Query API với xác minh dialect/provider |
| Phân trang GROUP BY | Trang trên hàng nhóm, count nhóm |
| Batch job vừa đọc vừa cập nhật filter | Tránh tăng offset trên tập đang co lại |

## Kết luận

**`setFirstResult` và `setMaxResults` là hai phương thức nền tảng để phân trang theo offset trong JPA.** `setFirstResult` nhận vị trí bắt đầu tính từ 0, `setMaxResults` giới hạn số kết quả tối đa, và offset của page index bắt đầu 0 được tính bằng `pageIndex × pageSize`. Khi dùng trong ứng dụng, luôn validate page/size, tránh overflow và đặt `ORDER BY` với một khóa duy nhất làm tie-breaker để tập kết quả có thứ tự xác định.

Tuy nhiên, **phân trang đúng không chỉ là hai lời gọi API**. Data query và count query phải có bộ lọc tương đương, bao gồm tenant/authorization; count phải đếm đúng **đơn vị được phân trang**; DTO projection giúp chỉ tải dữ liệu cần thiết; JOIN to-many và đặc biệt JOIN FETCH collection có thể nhân hàng, làm hỏng pagination root hoặc khiến provider phân trang trong memory. Khi cần collection, một giải pháp thường hiệu quả là phân trang root IDs trước rồi fetch associations ở truy vấn thứ hai.

Cuối cùng, OFFSET có thể trở nên tốn kém ở những trang rất sâu và có thể trùng/bỏ sót khi dữ liệu thay đổi giữa request. Nếu chỉ cần “Xem tiếp”, có thể dùng slice `size+1` để bỏ COUNT; nếu cần cuộn trên dữ liệu lớn hoặc biến động nhanh, cân nhắc keyset pagination. Chọn đúng mô hình phụ thuộc mục tiêu giao diện, tải dữ liệu, tính nhất quán và khả năng của DBMS, nhưng nguyên tắc chung vẫn là **lọc đúng, sắp đúng, giới hạn đúng, đếm đúng và chỉ nạp những gì use case thực sự cần**.
