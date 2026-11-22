# Phân trang theo độ lệch và thứ tự ổn định

## 1. Bài toán: danh sách dài không nên tải tất cả trong một lần

Một màn hình quản lý đơn hàng có thể lưu hàng trăm nghìn bản ghi, trong khi mỗi lần người dùng chỉ cần xem 20 hoặc 50 đơn. Tải toàn bộ entity rồi cắt danh sách bằng Java không phải là cách phân trang phù hợp:

```java
// Không nên: tải hết rồi mới cắt trang trong bộ nhớ.
List<PurchaseOrder> all = entityManager.createQuery(
    "from PurchaseOrder o order by o.createdAt desc",
    PurchaseOrder.class
).getResultList();

List<PurchaseOrder> page = all.subList(100, 120);
```

Phương pháp này đọc và materialize toàn bộ danh sách, giữ nhiều entity trong Persistence Context, tốn RAM, network và thời gian.

Giải pháp phổ biến là **phân trang theo độ lệch** (*offset pagination*):

- Chọn một số lượng bản ghi tối đa trên mỗi trang (`pageSize` hoặc `limit`).
- Bỏ qua số bản ghi ở trước (`offset`).
- Trả về phần kết quả theo một thứ tự đã được xác định.

Với một trang có chỉ số bắt đầu từ `0`:

\[
\text{offset} = \text{pageIndex} \times \text{pageSize}
\]

Ví dụ:

| Trang hiển thị | `pageIndex` (0-based) | `pageSize` | `offset` | Vị trí kết quả sau sắp xếp |
|---|---:|---:|---:|---|
| Trang 1 | 0 | 20 | 0 | 1–20 |
| Trang 2 | 1 | 20 | 20 | 21–40 |
| Trang 3 | 2 | 20 | 40 | 41–60 |
| Trang 6 | 5 | 20 | 100 | 101–120 |

Nhưng **LIMIT/OFFSET mà không có ORDER BY phù hợp** là một lỗi thiết kế: database không bắt buộc trả các hàng theo bất kỳ thứ tự mặc định nào. Ngay cả khi có ORDER BY, nếu các hàng có cùng giá trị sort thì vị trí giữa chúng vẫn có thể không xác định.

Bài học tập trung vào hai khía cạnh phải đi cùng nhau:

1. Cách dùng `setFirstResult()`, `setMaxResults()` và SQL `OFFSET/LIMIT` qua Hibernate.
2. Cách thiết kế **thứ tự ổn định, xác định** để tránh mất hoặc trùng bản ghi giữa các trang trong một tập dữ liệu không đổi, đồng thời hiểu giới hạn của offset pagination khi có thay đổi đồng thời.

## 2. OFFSET pagination hoạt động như thế nào?

Giả sử bảng `purchase_orders`:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

SQL phổ biến trên PostgreSQL/MySQL:

```sql
SELECT
    id,
    order_number,
    status,
    total_amount,
    created_at
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
```

Ý nghĩa:

1. Lọc những đơn `status = 'PAID'`.
2. Sắp xếp theo `created_at` mới nhất trước; nếu trùng ngày thì `id` lớn hơn trước.
3. Bỏ qua 40 hàng đầu **sau khi lọc và sắp xếp**.
4. Trả tối đa 20 hàng tiếp theo.

SQL chuẩn hoặc một số dialect khác có thể dùng:

```sql
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY
```

Về mặt ý định, cả hai thể hiện một trang từ vị trí 41 đến 60 của kết quả đã sắp xếp. Cú pháp thực tế do database dialect quyết định.

### Offset không phải ID

`OFFSET 40` **không có nghĩa** `WHERE id > 40`. Offset đếm **vị trí của hàng trong tập kết quả sau WHERE/ORDER BY**, bất kể giá trị khóa chính có liên tục hay không.

Ví dụ ID có thể là `1, 10, 100, 500` do xóa/nhập dữ liệu. Offset chỉ bỏ qua số hàng; nó không quan tâm chênh lệch giữa các ID.

### LIMIT không cam kết luôn đủ số hàng

Nếu sau `offset = 40` chỉ còn 7 hàng phù hợp điều kiện, query `LIMIT 20` chỉ trả 7. Nếu offset vượt tổng số bản ghi phù hợp, kết quả là danh sách rỗng.

## 3. Hibernate và JPA phân trang bằng API nào?

Jakarta Persistence định nghĩa các phương thức trên `Query`/`TypedQuery`:

```java
setFirstResult(int startPosition)
setMaxResults(int maxResult)
```

Ví dụ:

```java
List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.PAID)
.setFirstResult(40)
.setMaxResults(20)
.getResultList();
```

- `setFirstResult(40)`: bỏ qua 40 kết quả đầu, theo chỉ số bắt đầu từ 0.
- `setMaxResults(20)`: giới hạn tối đa 20 kết quả.
- `getResultList()`: thực thi query và trả các kết quả của trang.

HQL vẫn mô tả **điều kiện và thứ tự**, còn phần phân trang được đặt lên query object. Hibernate dùng dialect để chuyển thành SQL phù hợp với database.

### Cùng ý tưởng với Hibernate Session

```java
List<PurchaseOrder> orders = session.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    PurchaseOrder.class
)
.setParameter("status", OrderStatus.PAID)
.setFirstResult(40)
.setMaxResults(20)
.getResultList();
```

`EntityManager` là API Jakarta Persistence, còn `Session` là API Hibernate. Khi chỉ cần phân trang thông thường, dùng `setFirstResult`/`setMaxResults` là cách diễn đạt rõ và khá portable.

### HQL có cú pháp limit/offset không?

Các thế hệ HQL hiện đại có thể hỗ trợ mệnh đề giới hạn kết quả ngay trong query. Tuy nhiên, mức độ và cú pháp phụ thuộc phiên bản Hibernate; với ứng dụng cần giữ API Jakarta Persistence, `setFirstResult` và `setMaxResults` là lựa chọn dễ kiểm soát.

**Đừng vừa tự thêm `LIMIT/OFFSET` đặc thù dialect vào SQL/HQL vừa áp `setFirstResult`/`setMaxResults`** mà không biết hai cơ chế tương tác ra sao. Hãy chọn một cách phân trang rõ ràng cho một query.

## 4. Thứ tự ổn định là gì và vì sao quan trọng?

Trong SQL, các hàng thuộc quan hệ **không có thứ tự mặc định đáng tin cậy**. Nếu không có `ORDER BY`, database được quyền trả hàng theo kế hoạch truy vấn hiện tại. Index, mức độ song song, thống kê và phiên bản DB có thể làm thứ tự khác nhau.

Hai lần chạy:

```sql
SELECT id, order_number
FROM purchase_orders
WHERE status = 'PAID'
LIMIT 20 OFFSET 0;
```

không có hợp đồng rằng cùng 20 Order sẽ luôn xuất hiện khi dữ liệu không đổi.

### ORDER BY trên một cột chưa chắc đủ

Giả sử dữ liệu có các giá trị:

| id | created_at | status |
|---:|---|---|
| 105 | 2026-11-15 09:00:00 | PAID |
| 104 | 2026-11-15 09:00:00 | PAID |
| 103 | 2026-11-15 09:00:00 | PAID |
| 102 | 2026-11-15 08:50:00 | PAID |
| 101 | 2026-11-15 08:40:00 | PAID |

Với:

```sql
ORDER BY created_at DESC
```

ba hàng `105`, `104`, `103` **bằng nhau theo khóa sort**. Database được phép đặt chúng theo bất kỳ thứ tự nào trong nhóm.

Nếu `pageSize = 2`:

```text
Lần query trang 1:
  [105, 104]

Lần query trang 2 (database chọn thứ tự khác trong nhóm cùng timestamp):
  [104, 102]

Kết quả:
  104 có thể xuất hiện ở cả hai trang;
  103 có thể chưa xuất hiện ở trang nào.
```

Ví dụ này có thể xảy ra **ngay cả khi dữ liệu không thay đổi** vì sort key không phân biệt được ba hàng.

### Thêm khóa phụ duy nhất

```sql
ORDER BY created_at DESC, id DESC
```

Khi `id` là duy nhất và không NULL, thứ tự của mọi Order phù hợp được xác định đầy đủ:

```text
105, 104, 103, 102, 101

Trang 1, size=2: [105, 104]
Trang 2, size=2: [103, 102]
Trang 3, size=2: [101]
```

**Nguyên tắc:** một truy vấn offset pagination cần `ORDER BY` xác định **tổng thứ tự** (*total order*) trên những hàng được phân trang. Thường có thể đạt điều này bằng khóa sort nghiệp vụ cộng với primary key duy nhất làm tie-breaker.

## 5. Khóa sort chính và tie-breaker

Một trường sort nghiệp vụ có thể không duy nhất:

- `createdAt`: nhiều đơn được ghi cùng mili-giây.
- `status`: hàng nghìn đơn cùng trạng thái.
- `totalAmount`: nhiều đơn cùng giá.
- `customerName`: nhiều người có cùng tên.
- `updatedAt`: các bản ghi được cập nhật cùng một batch.

Thêm một khóa duy nhất cuối cùng:

```hql
order by o.createdAt desc, o.id desc
```

Hoặc:

```hql
order by o.totalAmount asc, o.id asc
```

Nếu entity có khóa chính ghép, cần đảm bảo tập trường tie-breaker tạo ra tính duy nhất trên miền dữ liệu đang phân trang; không nhất thiết một cột ID là đủ.

### Không dùng thứ tự của HashMap/HashSet hay thứ tự vật lý

Không dựa vào:

- Thứ tự insert trong bảng.
- Auto-increment ID mặc nhiên bằng thứ tự tạo thời gian.
- Thứ tự hàng của index scan khi không có ORDER BY.
- Thứ tự do Hibernate vừa trả ở một lần truy vấn.
- Thứ tự của collection Java nếu không được bảo đảm trong query.

Tính duy nhất của tie-breaker phải được diễn đạt trong `ORDER BY` của **chính truy vấn database**.

### Thứ tự ổn định không đồng nghĩa kết quả không thay đổi

Khóa unique giúp loại bỏ sự mơ hồ khi **so sánh các hàng có cùng sort key**. Nó không ngăn người khác thêm, xóa hoặc sửa dữ liệu giữa những lần truy vấn hai trang. Đây là hai vấn đề khác nhau và cần xử lý riêng.

## 6. Các dạng ORDER BY không đủ ổn định

| ORDER BY | Vấn đề | Phương án |
|---|---|---|
| Không có ORDER BY | Không có thứ tự được bảo đảm | Chọn field nghiệp vụ + khóa duy nhất |
| `status` | Rất nhiều bản ghi cùng status | `status, created_at DESC, id DESC` |
| `created_at DESC` | Timestamp thường trùng | `created_at DESC, id DESC` |
| `total_amount ASC` | Giá trị tiền dễ trùng | `total_amount ASC, id ASC` |
| `lower(customer_name)` | Tên chuẩn hóa có thể trùng | Thêm `id` của root |
| `random()` | Thứ tự thay đổi theo mỗi lần chạy | Không dùng cho pagination cần tính liên tục |
| `updated_at DESC` | Một update có thể chuyển hàng qua vị trí khác | Thêm ID; cân nhắc snapshot/keyset |
| Sort field nullable | Vị trí NULL tùy dialect/default | Xác định null ordering + ID |

### Hàm ngẫu nhiên không phù hợp phân trang thông thường

`ORDER BY random()` hoặc `ORDER BY rand()` tạo thứ tự khác mỗi lần gọi. Trang 2 không tiếp nối trang 1 theo một danh sách ổn định. Nếu nghiệp vụ cần danh sách ngẫu nhiên có thể phân trang, hãy gắn một seed/ranking ổn định cho phiên làm việc hoặc vật hóa thứ tự đã chọn.

## 7. Model Java minh họa

Giả sử:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount",
            precision = 18, scale = 2, nullable = false)
    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public OrderStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
```

Đoạn model dùng `Customer`, `OrderLine` và `ArrayList` minh họa; class thực tế cần mapping/import phù hợp. Điểm quan trọng là `createdAt` chưa duy nhất, còn `id` dùng làm tie-breaker.

Trong ví dụ, ta giả định ID của PurchaseOrder là duy nhất trong bảng. Nếu hệ thống multi-tenant dùng khóa ghép, điều kiện lọc tenant và cách sort phải phù hợp cấu trúc khóa thực tế.

## 8. Phân trang HQL bằng hàm service

Tạo request:

```java
public record OrderPageRequest(
    OrderStatus status,
    int pageIndex,
    int pageSize
) {}
```

Service đơn giản:

```java
public List<PurchaseOrder> findPage(
        EntityManager em,
        OrderPageRequest request) {

    if (request.pageIndex() < 0) {
        throw new IllegalArgumentException(
            "pageIndex must be >= 0"
        );
    }

    if (request.pageSize() < 1 || request.pageSize() > 100) {
        throw new IllegalArgumentException(
            "pageSize out of range"
        );
    }

    int offset = Math.multiplyExact(
        request.pageIndex(),
        request.pageSize()
    );

    return em.createQuery(
        "select o from PurchaseOrder o " +
        "where o.status = :status " +
        "order by o.createdAt desc, o.id desc",
        PurchaseOrder.class
    )
    .setParameter("status", request.status())
    .setFirstResult(offset)
    .setMaxResults(request.pageSize())
    .getResultList();
}
```

Những chi tiết đáng chú ý:

1. `pageIndex` bắt đầu từ 0.
2. `pageSize` phải dương và có giới hạn phù hợp API.
3. `Math.multiplyExact(...)` phát hiện overflow khi tính `pageIndex * pageSize`.
4. Query luôn có `ORDER BY` bao gồm một khóa duy nhất.
5. `status` là giá trị bind; không nối trực tiếp input vào HQL.
6. `getResultList()` trả danh sách rỗng nếu không có hàng ở offset tương ứng.

### Tại sao không dùng page * size một cách vô điều kiện?

Java `int` có giới hạn. Nếu giá trị page lớn đến mức phép nhân vượt `Integer.MAX_VALUE`, `pageIndex * pageSize` có thể overflow thành số âm hoặc kết quả sai.

`setFirstResult` dùng tham số `int`. Nếu API chấp nhận số trang rất lớn, cần giới hạn từ đầu; đây cũng là dấu hiệu nên xem xét **keyset/cursor pagination** thay vì offset khổng lồ.

Trong ví dụ, `Math.multiplyExact` sẽ ném `ArithmeticException` khi overflow. Lớp API nên chuyển tình huống này thành lỗi validation phù hợp thay vì trả lỗi server không rõ.

## 9. Từ Page API 1-based sang query 0-based

Một giao diện người dùng thường hiển thị “Trang 1, Trang 2, Trang 3” trong khi `setFirstResult` làm việc với offset bắt đầu từ 0.

Nếu HTTP API nhận:

```text
GET /orders?page=1&size=20
```

và quy ước page **1-based**, phải chuyển:

```java
int pageIndex = pageNumber - 1;
int offset = Math.multiplyExact(pageIndex, size);
```

Nếu API quy ước page **0-based**, không trừ 1.

**Không trộn hai cách đánh số** trong cùng ứng dụng. Các bug off-by-one thường làm trang đầu bỏ qua 20 hàng hoặc gọi trang 2 nhưng trả dữ liệu trang 3.

### Ví dụ

| HTTP page (1-based) | JPA offset (size = 10) |
|---:|---:|
| 1 | 0 |
| 2 | 10 |
| 3 | 20 |

Tài liệu API phải nêu rõ page bắt đầu từ 0 hay 1, giới hạn size, mặc định sort và semantics của những tham số lọc.

## 10. Không nhầm LIMIT với số hàng SQL sau JOIN

Phân trang theo danh sách entity root tương đối đơn giản nếu query chỉ lấy PurchaseOrder và không nhân kết quả.

Nhưng khi JOIN sang association một-nhiều:

```hql
select o
from PurchaseOrder o
join o.lines l
where l.sku = :sku
order by o.createdAt desc, o.id desc
```

Một Order có thể có nhiều dòng `OrderLine` khớp điều kiện. SQL JOIN có thể tạo **nhiều hàng cho cùng một Order**:

```text
Order#10  Line#1
Order#10  Line#2
Order#9   Line#3
Order#8   Line#4
```

Nếu database `LIMIT 2` trên các hàng JOIN, hai hàng đó có thể đều là Order#10. Kết quả sau khi hợp nhất entity có thể chỉ thấy **một Order** trong trang, dù yêu cầu size = 2.

### Cách xử lý

- Khi chỉ cần biết Order có ít nhất một line matching, ưu tiên `EXISTS`:

```hql
select o
from PurchaseOrder o
where exists (
    select 1
    from OrderLine l
    where l.order = o and l.sku = :sku
)
order by o.createdAt desc, o.id desc
```

- Nếu cần JOIN và kết quả root duy nhất, cân nhắc `SELECT DISTINCT o`, rồi xem SQL và cách Hibernate/dialect xử lý.
- Với truy vấn dữ liệu trang phức tạp, phân trang root IDs trước rồi tải entity/DTO theo các IDs ấy.

**Phải xác định đang phân trang hàng SQL hay phân trang entity/domain record.** Không mặc định chúng có quan hệ 1:1 khi JOIN to-many.

## 11. Vì sao collection FETCH JOIN dễ làm sai phân trang?

Ví dụ:

```hql
select o
from PurchaseOrder o
left join fetch o.lines
where o.status = :status
order by o.createdAt desc, o.id desc
```

Khi `o.lines` là collection, mỗi Order có thể xuất hiện nhiều lần ở result set SQL để Hibernate materialize những line tương ứng.

Nếu `setMaxResults(20)` được áp trực tiếp lên 20 hàng SQL, trang có thể chứa không đủ 20 Order, thậm chí cắt dở collection của Order cuối cùng. Vì thế Hibernate có thể phải xử lý pagination đặc biệt; tùy phiên bản, nó có thể **áp pagination trong bộ nhớ** sau khi tải một tập kết quả lớn, kèm cảnh báo.

Hệ quả:

- Một trang 20 Order có thể làm database trả hàng chục nghìn dòng.
- Heap và hydration tăng mạnh.
- Không đạt mục tiêu giới hạn dữ liệu tại DB.
- Query trở nên chậm khó dự đoán.

### Cấu hình fail-fast

Hibernate cung cấp cấu hình liên quan đến việc phân trang qua collection fetch, ví dụ property `hibernate.query.fail_on_pagination_over_collection_fetch` ở những phiên bản hỗ trợ. Bật fail-fast trong môi trường phù hợp có thể giúp phát hiện query nguy hiểm thay vì âm thầm phân trang trong bộ nhớ.

Phải kiểm tra tên property và behavior theo Hibernate version thực tế.

### Cách an toàn hơn: hai bước

1. Query trang ID của Order theo bộ lọc và thứ tự ổn định.
2. Query thứ hai lấy Order/lines cho **tập ID của trang** bằng fetch join, batch fetching hoặc projection phù hợp.

Ví dụ:

```java
List<Long> ids = em.createQuery(
    "select o.id from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    Long.class
)
.setParameter("status", status)
.setFirstResult(offset)
.setMaxResults(size)
.getResultList();

if (ids.isEmpty()) {
    return List.of();
}

List<PurchaseOrder> loaded = em.createQuery(
    "select distinct o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "where o.id in :ids",
    PurchaseOrder.class
)
.setParameter("ids", ids)
.getResultList();
```

**Chú ý:** Query thứ hai có `IN (:ids)` **không bảo đảm giữ thứ tự của list `ids`**. Nếu API cần thứ tự trang như query đầu, phải:

- Sắp xếp lại `loaded` theo vị trí trong `ids` ở Java; hoặc
- Dùng ORDER BY tương ứng trong query thứ hai nếu có đủ dữ liệu sort và không làm hỏng mapping.

Ví dụ sắp xếp theo vị trí trang:

```java
Map<Long, Integer> position = new HashMap<>();

for (int i = 0; i < ids.size(); i++) {
    position.put(ids.get(i), i);
}

loaded.sort(Comparator.comparingInt(
    o -> position.get(o.getId())
));
```

Đây là ví dụ tối thiểu. Trong thực tế, hãy kiểm tra transaction/isolation: dữ liệu có thể đổi giữa bước lấy IDs và bước tải chi tiết, kể cả trong cùng transaction tùy mức cô lập và hoạt động đồng thời.

## 12. Tại sao một ORDER BY duy nhất vẫn chưa đủ khi dữ liệu thay đổi?

Giả sử mỗi trang có ba Order, sắp xếp theo `created_at DESC, id DESC`:

```text
Tại thời điểm T1:
  [F, E, D, C, B, A]

Trang 1, OFFSET 0 LIMIT 3:
  [F, E, D]
```

Trước khi người dùng mở trang 2, có đơn mới `G` đứng đầu:

```text
Tại thời điểm T2:
  [G, F, E, D, C, B, A]

Trang 2, OFFSET 3 LIMIT 3:
  [D, C, B]
```

Order `D` **xuất hiện ở cả trang 1 và trang 2**, mặc dù cả hai query đều có `ORDER BY` tổng thứ tự hoàn toàn xác định.

Đây là điểm rất quan trọng:

> **Thứ tự xác định loại bỏ sự mơ hồ của những hàng có cùng sort key, nhưng không giữ cố định vị trí OFFSET khi tập dữ liệu thay đổi giữa các lần query.**

### Khi một hàng bị xóa

Tại T1:

```text
[F, E, D, C, B, A]

Trang 1: [F, E, D]
```

Trước T2, `E` bị xóa:

```text
[F, D, C, B, A]

Trang 2, OFFSET 3:
[B, A]
```

Order `C` đã bị bỏ qua: nó chuyển lên vị trí thứ ba sau khi E bị xóa, nhưng client bắt đầu query trang 2 từ offset 3 (vị trí thứ tư).

### Khi field sort bị cập nhật

Nếu `updatedAt` hoặc `priority` được dùng để sắp xếp và một Order đổi giá trị giữa hai trang, nó có thể di chuyển từ phía sau lên phía trước hoặc ngược lại. Sự dịch chuyển này cũng tạo duplicate/skip, kể cả không có INSERT/DELETE.

## 13. Ba mức “ổn định” cần phân biệt

| Mức | Mục tiêu | Biện pháp điển hình |
|---|---|---|
| **Thứ tự xác định** | Hai hàng cùng khóa chính sort không bị hoán đổi tùy ý | ORDER BY thêm unique tie-breaker |
| **Tập dữ liệu nhất quán trong một lần đọc** | Data và COUNT/chi tiết dựa trên snapshot phù hợp | Transaction isolation, cùng ranh giới đọc, kiểm tra DB |
| **Duyệt qua nhiều trang khi dữ liệu thay đổi** | Hạn chế duplicate/skip khi client gọi trang kế tiếp | Keyset/cursor, snapshot/versioned result hoặc thiết kế API tương ứng |

Không nên dùng từ “stable pagination” mà không nêu rõ yêu cầu thuộc mức nào. Với màn hình CRUD thông thường, thứ tự xác định cộng offset có thể đủ. Với xuất báo cáo hàng triệu dòng hoặc đồng bộ dữ liệu, cần tiêu chuẩn cao hơn.

## 14. Transaction isolation có giúp giữ trang nhất quán không?

Transaction và isolation quyết định những thay đổi nào của transaction khác có thể được nhìn thấy. Nhưng không có một quy tắc “mở transaction là mọi trang ổn định” cho tất cả hệ quản trị.

### READ COMMITTED

Ở nhiều DB dùng `READ COMMITTED`, mỗi statement có thể thấy dữ liệu đã commit trước khi statement bắt đầu. Nếu người dùng gọi trang 1 rồi trang 2 thành **hai HTTP request/transaction khác nhau**, rất dễ thấy tập dữ liệu thay đổi.

### REPEATABLE READ / snapshot isolation

Một transaction đọc trên snapshot nhất quán có thể giúp các query trong **cùng transaction** thấy tập dữ liệu ổn định theo semantics DB. Nhưng:

- Isolation behavior khác giữa PostgreSQL, MySQL, Oracle và SQL Server.
- Không phải mọi DB hoặc cấu hình gọi `REPEATABLE READ` đều có cùng hiện tượng/đảm bảo.
- Giữ transaction mở qua nhiều HTTP request có thể tăng chi phí connection/lock/MVCC và khó vận hành.
- Một transaction snapshot không tự bao trùm nhiều request nếu mỗi request có transaction riêng.

### Giải pháp cho xuất dữ liệu lớn

Với tác vụ export/batch cần tập dữ liệu cố định:

- Chạy toàn bộ quá trình trong một transaction snapshot phù hợp nếu quy mô cho phép.
- Chụp danh sách ID phù hợp ở một thời điểm rồi xử lý theo danh sách đó.
- Dùng bảng/staging snapshot hoặc job result được vật hóa cho export lâu.
- Dùng keyset với điều kiện cắt thời gian/ID và chính sách xử lý cập nhật/xóa rõ ràng.

**Không kéo dài database transaction qua nhiều phút hoặc nhiều HTTP request chỉ để giữ offset ổn định** nếu không đánh giá tác động đến connection pool, MVCC/vacuum, timeout và tài nguyên.

## 15. OFFSET pagination khác keyset/cursor pagination

Offset dựa trên **vị trí**:

```sql
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 1000;
```

Keyset dựa trên **khóa sort cuối của trang trước**:

```sql
WHERE
    created_at < :lastCreatedAt
    OR (
        created_at = :lastCreatedAt
        AND id < :lastId
    )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Nếu trang 1 kết thúc ở:

```text
created_at = 2026-11-15T09:00:00Z
id = 105
```

thì trang kế tiếp tìm những Order **đứng sau cặp khóa đó** theo thứ tự giảm dần, thay vì bỏ qua một số lượng hàng.

### Vì sao keyset hạn chế dịch chuyển?

Khi một bản ghi mới được chèn **trước khóa của trang đã xem**, con trỏ keyset vẫn tiếp tục từ hàng cuối cùng cũ. Nó không bị dời `OFFSET` bởi bản ghi mới đứng đầu.

Tuy nhiên, keyset không phải phép màu:

- Nếu field sort bị cập nhật, bản ghi có thể di chuyển qua cursor boundary.
- Nếu bản ghi bị xóa, tập kết quả thay đổi.
- Với sort phức tạp và NULL, predicate keyset phải được xây đúng.
- API không dễ nhảy thẳng tới “trang 500” chỉ với cursor.
- Có thể cần giới hạn snapshot/time-window để đáp ứng hợp đồng đọc nhất quán.

### Bảng so sánh

| Tiêu chí | Offset pagination | Keyset/cursor pagination |
|---|---|---|
| Chuyển trực tiếp đến trang N | Thuận tiện | Không tự nhiên, cần cursor/anchor |
| API `page/size` | Đơn giản | Thường dùng `cursor/size` |
| Dữ liệu mới chèn ở đầu danh sách | Dễ gây duplicate/skip | Ít bị ảnh hưởng nếu khóa sort phù hợp |
| Offset rất sâu | Database thường phải đi qua nhiều hàng | Có thể seek theo index hiệu quả hơn |
| Sort tùy ý | Dễ diễn đạt | Phải mã hóa toàn bộ sort keys vào cursor |
| Giữ nhất quán khi sort key đổi | Không tự giải quyết | Cũng không tự giải quyết mọi trường hợp |
| Hiển thị tổng trang | Dễ kết hợp COUNT | Thường không có total pages mặc định |

Trong bài này trọng tâm là offset; keyset được giới thiệu như phương án khi **sâu trang, dữ liệu thay đổi nhiều hoặc duyệt tuần tự** trở thành yêu cầu quan trọng.

## 16. Deep OFFSET: giới hạn hiệu năng khi trang rất sâu

Offset pagination đơn giản nhưng thường có chi phí tăng theo offset. Với query:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
```

database thường vẫn phải tìm/sắp xếp hoặc đi qua nhiều bản ghi phù hợp trước khi bỏ qua 200.000 hàng đầu. Index có thể giúp, nhưng `OFFSET` lớn vẫn có thể phải scan qua nhiều entry.

### Không thể suy từ cú pháp ra chi phí chính xác

Hiệu năng phụ thuộc:

- Filter selectivity.
- Index phù hợp sort/filter.
- Số hàng, độ rộng row, vùng dữ liệu đang nằm trong cache.
- Join cardinality.
- Optimizer và execution plan.
- Cách dialect áp pagination.
- Bản ghi cập nhật/xóa và thống kê DB.

Một index đúng có thể giúp offset nhỏ rất nhanh, nhưng không biến offset cực lớn thành thao tác `O(1)` trên mọi database.

### Quy tắc thực tế

- Trang ngắn, danh sách quản trị thông thường: OFFSET là lựa chọn hợp lý.
- Export/batch quét hàng triệu dòng: cân nhắc keyset hoặc streaming có ranh giới thích hợp.
- API feed cuộn vô hạn: cursor thường thích hợp hơn jump-to-page.
- Yêu cầu tìm trang bất kỳ theo số thứ tự: offset có lợi thế, nhưng cần giới hạn page và đánh giá chi phí.

## 17. Index phù hợp với WHERE và ORDER BY

Với query thường gặp:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

PostgreSQL index minh họa:

```sql
CREATE INDEX ix_orders_status_time_id
ON purchase_orders (status, created_at DESC, id DESC);
```

Ý tưởng:

- Cột `status` phục vụ điều kiện equality.
- `created_at DESC, id DESC` phục vụ thứ tự.
- Database có thể đi theo thứ tự index mà không cần sort toàn bộ kết quả trong một số execution plans.

### Index không phải cam kết optimizer luôn sử dụng

Database có thể chọn scan/sort khác nếu:

- Điều kiện status quá ít chọn lọc.
- Query trả tỷ lệ lớn của bảng.
- Index không cover những cột cần đọc.
- Thống kê chưa phù hợp.
- Có JOIN hoặc hàm trên sort key.
- Dữ liệu thực tế và parameter values khác nhau.

Hãy dùng `EXPLAIN`/`EXPLAIN ANALYZE` trên DB mục tiêu để kiểm chứng.

### Sort theo nhiều điều kiện khác nhau

Nếu API cho sort theo `totalAmount ASC` và `createdAt DESC`, một index không nhất thiết phục vụ tốt mọi kiểu sort. Chọn index dựa trên workload và những sort paths phổ biến; không tạo index cho mọi hoán vị tùy ý vì index cũng làm tăng chi phí write/storage.

## 18. COUNT query và dữ liệu trang là hai truy vấn khác nhau

Một API trả Page thường cần:

```json
{
  "items": [ /* các đơn ở trang hiện tại */ ],
  "pageIndex": 2,
  "pageSize": 20,
  "totalElements": 1538,
  "totalPages": 77
}
```

Truy vấn trang:

```hql
select o
from PurchaseOrder o
where o.status = :status
order by o.createdAt desc, o.id desc
```

Truy vấn đếm:

```hql
select count(o)
from PurchaseOrder o
where o.status = :status
```

HQL `COUNT` chỉ cần bộ lọc; **không cần ORDER BY**. Count query cũng không cần fetch association chỉ để hydrate entity.

### Không tính total bằng items.size()

Nếu trang 2 trả 20 Order, `items.size() = 20` không có nghĩa tổng chỉ có 20. Nếu trang cuối trả ít hơn size, có thể suy đoán không còn trang tiếp theo, nhưng vẫn chưa có tổng chính xác của toàn bộ tập kết quả nếu không đếm.

### Công thức totalPages

Với tổng `totalElements >= 0` và `pageSize > 0`:

\[
\text{totalPages}=
\left\lceil\frac{\text{totalElements}}{\text{pageSize}}\right\rceil
\]

Ví dụ 1.538 bản ghi với page size 20:

\[
\lceil 1538/20 \rceil = 77\text{ trang}
\]

Đừng dùng `totalElements + pageSize - 1` trên kiểu số nguyên mà không xét overflow. Với `long`:

```java
long totalPages =
    totalElements / pageSize +
    (totalElements % pageSize == 0 ? 0 : 1);
```

Quy tắc khi `totalElements = 0` thường là `totalPages = 0` trong nhiều API, nhưng có UI mong hiển thị một trang rỗng; nên định nghĩa ở contract.

## 19. COUNT và data query có thể khác nhau ngay khi cùng request

Giả sử service chạy:

1. Query `COUNT(*)` trả 100.
2. Một transaction khác thêm ba Order.
3. Query data page thấy 103 Order phù hợp.

Kết quả `totalElements = 100` nhưng dữ liệu trang phản ánh tập khác. Trong transaction `READ COMMITTED`, điều này có thể hợp lệ theo semantics database.

### Có cần bảo đảm total tuyệt đối chính xác?

Không phải use case nào cũng cần:

- Màn hình quản trị có thể chấp nhận count thay đổi đôi chút.
- Feed hoạt động có thể chỉ cần biết `hasNext`, không cần total.
- Báo cáo tài chính có thể yêu cầu snapshot nhất quán.

Nếu cần count và page cùng snapshot, xác định transaction/isolation phù hợp với DB và thực tế triển khai. **Chỉ gắn `@Transactional(readOnly = true)` không tự tạo snapshot lặp lại cho mọi database**.

### COUNT thường đắt với tập dữ liệu lớn

`COUNT(*)` sau nhiều join/filter có thể tốn nhiều I/O và CPU. Với infinite scroll, cân nhắc trả `Slice` hoặc `hasNext` thay vì count ở mỗi request.

## 20. Lấy size + 1 để xác định hasNext

Nếu chỉ cần biết còn trang sau hay không, có thể lấy thêm một hàng:

```java
int requestedSize = 20;

List<PurchaseOrder> fetched = em.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    PurchaseOrder.class
)
.setParameter("status", status)
.setFirstResult(offset)
.setMaxResults(requestedSize + 1)
.getResultList();

boolean hasNext = fetched.size() > requestedSize;

List<PurchaseOrder> visible = hasNext
    ? new ArrayList<>(fetched.subList(0, requestedSize))
    : fetched;
```

Ví dụ này minh họa cách tạo **slice**:

- Nếu nhận 21 hàng, chỉ hiển thị 20 và biết có trang tiếp.
- Nếu nhận tối đa 20 hàng, không có trang tiếp **tại thời điểm query**.
- Không cần chạy COUNT(*) cho mỗi request.

Cần validate `requestedSize + 1` để không overflow và chỉ dùng khi page size được giới hạn. Hơn nữa, `hasNext` có thể thay đổi khi dữ liệu được thêm/xóa sau đó.

### Slice khác Page

| Dạng response | Cần COUNT? | Trường kết quả |
|---|---|---|
| Page | Thường có | Items, page, size, totalElements, totalPages |
| Slice | Không bắt buộc | Items, page/cursor, size, hasNext |
| List thuần | Không | Items |

Chọn response theo UI contract, không bắt buộc mọi danh sách đều cần totalPages.

## 21. Truy vấn Page kết quả DTO thay vì hydrate entity graph

Nếu trang chỉ hiển thị mã đơn, trạng thái và tổng tiền, không cần trả toàn bộ PurchaseOrder entity.

DTO:

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) {}
```

HQL constructor projection:

```java
List<OrderSummary> items = em.createQuery(
    "select new com.example.orders.OrderSummary(" +
    "o.id, o.orderNumber, o.status, " +
    "o.totalAmount, o.createdAt) " +
    "from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    OrderSummary.class
)
.setParameter("status", OrderStatus.PAID)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
```

Lợi ích:

- Chỉ chọn những field cần cho trang.
- Giảm hydration và số managed entity trong Persistence Context.
- Không serialize lazy proxy/collection vô tình.
- Giảm nguy cơ N+1 do UI truy cập field association.
- API contract tách khỏi schema và entity lifecycle.

Nếu DTO cần customer name, có thể join to-one:

```hql
select new com.example.orders.OrderWithCustomerRow(
    o.id, o.orderNumber, c.name, o.totalAmount
)
from PurchaseOrder o
join o.customer c
where o.status = :status
order by o.createdAt desc, o.id desc
```

Join to-one thông thường không nhân số hàng root nếu mỗi Order chỉ có một Customer. Nhưng nếu dữ liệu/association optional, cần cân nhắc LEFT JOIN.

## 22. Criteria API: phân trang với Root và Order

Criteria API phù hợp khi API có nhiều bộ lọc tùy chọn.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);

Predicate byStatus = cb.equal(
    order.get("status"),
    OrderStatus.PAID
);

cq.select(order);
cq.where(byStatus);
cq.orderBy(
    cb.desc(order.get("createdAt")),
    cb.desc(order.get("id"))
);

List<PurchaseOrder> page = em.createQuery(cq)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
```

Ở đây `jakarta.persistence.criteria.Order` là biểu thức sắp xếp do `cb.desc(...)` tạo, không phải entity nghiệp vụ.

### Sắp xếp động nhưng giữ tie-breaker

Ví dụ API có sort field là enum:

```java
public enum OrderSortField {
    CREATED_AT,
    TOTAL_AMOUNT,
    ORDER_NUMBER
}
```

Hàm dựng:

```java
private jakarta.persistence.criteria.Order buildPrimarySort(
        CriteriaBuilder cb,
        Root<PurchaseOrder> root,
        OrderSortField sortField,
        boolean descending) {

    Expression<?> expression = switch (sortField) {
        case CREATED_AT -> root.get("createdAt");
        case TOTAL_AMOUNT -> root.get("totalAmount");
        case ORDER_NUMBER -> root.get("orderNumber");
    };

    return descending
        ? cb.desc(expression)
        : cb.asc(expression);
}
```

Sau đó:

```java
cq.orderBy(
    buildPrimarySort(cb, order, sortField, descending),
    cb.desc(order.get("id"))
);
```

Tie-breaker vẫn được thêm vào **mọi** phương án sort. Tuy nhiên, hướng sort ID phải có contract rõ: ví dụ tổng tiền tăng dần nhưng ID giảm dần là thứ tự hợp lệ nếu đã định nghĩa như vậy.

Không nhận chuỗi attribute name tùy ý từ client rồi gọi `root.get(userInput)`. Sử dụng allow-list field để tránh lộ field nội bộ và tránh query lỗi.

## 23. COUNT query bằng Criteria phải có Root riêng

Data query:

```java
CriteriaQuery<PurchaseOrder> dataQuery =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> dataRoot =
    dataQuery.from(PurchaseOrder.class);
```

Count query:

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);
Root<PurchaseOrder> countRoot =
    countQuery.from(PurchaseOrder.class);

countQuery.select(cb.count(countRoot));
countQuery.where(cb.equal(
    countRoot.get("status"),
    OrderStatus.PAID
));

long total = em.createQuery(countQuery)
    .getSingleResult();
```

Không gắn `Predicate` đã xây dựa trên `dataRoot` trực tiếp sang `countQuery` với root khác. Query trees có các root và path riêng; hãy xây lại predicate từ một helper nhận root tương ứng.

### Khi có JOIN to-many

Nếu count query join OrderLine:

```java
countQuery.select(
    cb.countDistinct(countRoot.get("id"))
);
```

để đếm số Order duy nhất thay vì số hàng JOIN; hoặc dùng EXISTS để giữ số row root không bị nhân.

Count query thường không cần `orderBy`, `fetch` hay projection DTO phức tạp.

## 24. Spring Data JPA: PageRequest và Sort

Nếu ứng dụng dùng Spring Data JPA, có thể phân trang qua `Pageable`/`PageRequest`:

```java
Pageable pageable = PageRequest.of(
    2,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<PurchaseOrder> page =
    orderRepository.findByStatus(OrderStatus.PAID, pageable);
```

`PageRequest.of(2, 20, ...)` dùng **chỉ số trang bắt đầu từ 0**: đây là trang thứ ba, offset 40.

Repository:

```java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
```

### Page và Slice trong Spring Data

- `Page<T>` thường cung cấp `getTotalElements()`, `getTotalPages()` và metadata trang; có thể cần count query.
- `Slice<T>` tập trung vào `hasNext()`, không bắt buộc có tổng số bản ghi.
- `List<T>` với Pageable có thể chỉ trả nội dung mà không metadata, tùy repository method.

### Không bỏ mặc sort mặc định

`PageRequest.of(page, size)` không có sort ổn định nếu repository query không khai báo ORDER BY phù hợp. Dùng `Sort` có tie-breaker hoặc một query ORDER BY cố định, và tránh kết hợp các cơ chế sort mâu thuẫn.

Khi dùng Spring Data custom query với projection hoặc JOIN to-many, cần xác minh count query đúng, pagination thực hiện ở database và kết quả root không bị nhân.

## 25. Sắp xếp theo field nullable: vị trí NULL phải được xác định

Giả sử màn hình sort theo ngày giao dự kiến:

```text
estimated_delivery_at: có thể NULL
```

Query:

```sql
ORDER BY estimated_delivery_at ASC, id ASC
```

Thứ tự của NULL theo ASC/DESC có thể **khác nhau giữa database** hoặc tùy cấu hình. Nếu yêu cầu nghiệp vụ “đơn chưa có ngày dự kiến luôn ở cuối”, phải thể hiện rõ:

```sql
ORDER BY
    CASE WHEN estimated_delivery_at IS NULL THEN 1 ELSE 0 END ASC,
    estimated_delivery_at ASC,
    id ASC;
```

Hoặc sử dụng `NULLS FIRST`/`NULLS LAST` khi HQL/dialect hỗ trợ đúng theo phiên bản.

### Vì sao phải thêm id?

Vẫn có nhiều đơn có cùng estimated delivery; các hàng cùng NULL cũng có thể rất nhiều. `id` tạo tie-breaker cuối cùng.

### Đánh đổi hiệu năng

`CASE WHEN ...` trong ORDER BY có thể khiến index bình thường không phục vụ sort như mong muốn. Nếu sort nullable là workload chính, có thể cần expression index hoặc schema/read model thích hợp trên database mục tiêu.

## 26. Collation, text sorting và thứ tự ổn định

Sort theo tên khách hàng:

```sql
ORDER BY lower(customer_name) ASC, id ASC
```

Khóa `lower(customer_name)` có thể bằng nhau cho nhiều người. Ngoài ra, cách so sánh text phụ thuộc:

- Collation của database và cột.
- Unicode normalization.
- Quy tắc chữ hoa/chữ thường và dấu.
- Bản nâng cấp DB/collation implementation.

Thêm ID bảo đảm hai hàng có cùng giá trị sort theo collation được phân biệt trong kết quả. Nhưng nếu **collation hoặc business sort rule thay đổi** giữa các lần query/deployment, thứ tự vẫn có thể đổi.

Để API ổn định lâu dài, định nghĩa rõ cách sort văn bản và kiểm thử trên database thực tế, đặc biệt với dữ liệu đa ngôn ngữ.

## 27. Sort theo association cần chú ý cardinality

Ví dụ sort Order theo tên Customer:

```hql
select o
from PurchaseOrder o
join o.customer c
where o.status = :status
order by c.name asc, o.id asc
```

Nếu mỗi Order có tối đa một Customer, sort này có thể hoạt động ổn định với tie-breaker `o.id`.

Nhưng sort theo field của collection to-many:

```hql
select o
from PurchaseOrder o
join o.lines l
order by l.sku, o.id
```

không xác định **một** sort key duy nhất cho mỗi Order nếu một đơn có nhiều line. Mỗi Order có thể sinh nhiều hàng SQL và xuất hiện nhiều vị trí.

Hãy xác định một aggregate rõ:

- `MIN(line.sku)` nếu muốn sort theo SKU nhỏ nhất.
- `MAX(line.quantity)` nếu muốn sort theo số lượng line lớn nhất.
- Tổng tiền/tổng số line bằng subquery/aggregate.

Sau khi group/select root đúng, mới thêm ID làm tie-breaker. Không sửa một query nhân hàng chỉ bằng việc thêm `id` vào ORDER BY.

## 28. Transaction và fetch plan của trang cần được thiết kế cùng nhau

Một use case danh sách có thể cần:

```text
Page<Orders>
  ├── orderNumber
  ├── status
  ├── createdAt
  ├── customerName
  └── lineCount
```

Không cần hydrate toàn bộ OrderLine collection để lấy `lineCount`. Một DTO query có join/aggregate/subquery count sẽ phù hợp hơn.

Trong Hibernate:

- To-one join có thể đơn giản, ít nguy cơ nhân root.
- To-many join cần kiểm tra cardinality.
- Collection fetch join + pagination có thể gây in-memory pagination.
- Batch fetching giúp tải association cho những Order trong page nếu cần chi tiết.
- EntityGraph giúp diễn đạt những association cần fetch, nhưng không tự giải quyết mọi pagination/fetch join issue.

**Fetch plan và pagination không phải hai quyết định độc lập**. Một fetch plan làm nhân hàng có thể thay đổi cơ chế LIMIT/OFFSET và tính đúng của page.

## 29. Thiết kế API response cho offset pagination

Một kiểu response thường gặp:

```java
public record PageResponse<T>(
    List<T> items,
    int pageIndex,
    int pageSize,
    long totalElements,
    long totalPages,
    boolean hasNext
) {}
```

Hoặc trả `SliceResponse` không có total:

```java
public record SliceResponse<T>(
    List<T> items,
    int pageIndex,
    int pageSize,
    boolean hasNext
) {}
```

### Những quyết định contract nên ghi rõ

- `pageIndex` bắt đầu từ 0 hay 1?
- Giá trị size mặc định và tối đa?
- Sort mặc định, có ID tie-breaker hay không?
- Có cho phép sort nhiều field không?
- Field nullable sắp NULL trước hay sau?
- Tổng số bản ghi có được bảo đảm cùng snapshot với items không?
- Nếu dữ liệu đổi giữa hai request, API chấp nhận duplicate/skip hay cần cursor?
- Khi vượt trang cuối: trả empty page hay một lỗi?

Không bắt buộc mỗi API chọn cùng cách, nhưng **phải nhất quán và có tài liệu**.

## 30. Không xem số trang lớn là yêu cầu miễn phí

Giả sử:

```text
GET /orders?page=100000&size=100
```

Offset là 10 triệu hàng. Ngay cả nếu database có thể thực hiện, request này có thể:

- Tốn nhiều CPU/I/O.
- Cạnh tranh tài nguyên với request thường.
- Vượt timeout.
- Truy vấn count lớn và sort lại.
- Tạo cơ hội lạm dụng tài nguyên.

API cần giới hạn hợp lý cho `size` và có thể giới hạn `page`/offset lớn. Nếu người dùng cần export hoặc xem toàn bộ dữ liệu, hãy cung cấp:

- API export/job riêng.
- Cursor/keyset pagination.
- Bộ lọc thu hẹp tập dữ liệu.
- Read model/index phù hợp.

Không tăng timeout vô hạn để bù cho offset quá sâu.

## 31. Keyset đơn giản với cặp (createdAt, id)

Dù trọng tâm bài là offset, hiểu phương án thay thế giúp ra quyết định tốt.

Với thứ tự:

```sql
ORDER BY created_at DESC, id DESC
```

Giả sử trang hiện tại kết thúc tại `(lastCreatedAt, lastId)`. Trang sau:

```hql
select o
from PurchaseOrder o
where o.status = :status
  and (
      o.createdAt < :lastCreatedAt
      or (
          o.createdAt = :lastCreatedAt
          and o.id < :lastId
      )
  )
order by o.createdAt desc, o.id desc
```

Lúc này:

```java
List<PurchaseOrder> next = em.createQuery(hql,
    PurchaseOrder.class)
.setParameter("status", status)
.setParameter("lastCreatedAt", lastCreatedAt)
.setParameter("lastId", lastId)
.setMaxResults(pageSize)
.getResultList();
```

Không có `setFirstResult(offset)` vì cursor xác định vị trí thông qua khóa sort.

### Tie-breaker cũng rất quan trọng với keyset

Nếu chỉ dùng `createdAt`, những Order có cùng thời điểm với hàng cuối có thể bị bỏ lỡ hoặc lặp khi chuyển trang. Cần đưa **mọi khóa tạo total order** vào cursor và điều kiện tiếp tục.

Nếu sort ASC/DESC trộn nhau, predicate phải được xây theo quy tắc lexicographic tương ứng. Không copy nguyên điều kiện `<` của ví dụ DESC để dùng cho ASC.

## 32. Spring Data và fetch count: tránh hiểu nhầm Page

Một method:

```java
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
```

thường thể hiện query dữ liệu và khả năng có count query. Nhưng:

- Spring Data có thể tối ưu bỏ qua count trong một số tình huống tùy implementation.
- Count query có thể cần định nghĩa tường minh khi JPQL custom query phức tạp.
- DISTINCT/fetch join/grouping cần xem lại semantics count.
- EntityGraph/fetch strategy vẫn có thể ảnh hưởng hiệu năng query dữ liệu.

Không nên suy luận rằng mọi lần gọi `Page` bắt buộc phát chính xác **hai** câu SQL; hãy quan sát logging/statistics theo phiên bản Spring Data JPA và query cụ thể.

Nếu chỉ cần hasNext, cân nhắc `Slice`. Nếu total là một thành phần nghiệp vụ quan trọng, thiết kế count query đúng và xác định yêu cầu consistency.

## 33. SQL log và query plan: kiểm tra pagination thực sự tại DB

Trong Spring Boot với Hibernate ORM 6, có thể bật logging:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Tùy phiên bản/logger, tên logger bind parameter có thể khác. Chỉ bật chi tiết khi cần và ở môi trường được kiểm soát, vì giá trị bind có thể chứa dữ liệu nhạy cảm.

### Điều cần thấy

Với query HQL và API:

```java
query.setFirstResult(40);
query.setMaxResults(20);
```

SQL nên thể hiện giới hạn tương ứng theo dialect, chẳng hạn:

```sql
SELECT ...
FROM purchase_orders o
WHERE o.status = ?
ORDER BY o.created_at DESC, o.id DESC
OFFSET ? ROWS FETCH NEXT ? ROWS ONLY;
```

Đây là hình dạng minh họa; DB có thể dùng `LIMIT/OFFSET` hoặc cú pháp khác.

### Nếu không có LIMIT/OFFSET ở SQL?

Hãy kiểm tra:

1. Query có fetch join collection không?
2. Hibernate có cảnh báo pagination in-memory không?
3. Có custom result transformer, distinct hoặc dialect issue không?
4. Bạn đang xem SQL đúng statement của request chưa?
5. Query có native pagination đã được viết trực tiếp và bị xử lý khác không?

Không chỉ kiểm tra list trả về có 20 phần tử; nó có thể đã tải nhiều hơn rồi cắt ở memory.

### EXPLAIN

Đo:

- Index scan hay sequential/table scan?
- Có sort lớn không?
- Số rows database phải duyệt đến trang sâu là bao nhiêu?
- Join cardinality có làm nhân row?
- `OFFSET 0` khác `OFFSET 100000` thế nào?
- Query count có đắt hơn query page không?

`EXPLAIN ANALYZE` có thể thực thi SQL thật, nên cẩn thận khi dùng với DML và môi trường production.

## 34. Kiểm thử thứ tự ổn định với nhiều hàng cùng sort key

Đừng chỉ seed dữ liệu có timestamp khác nhau; khi đó bug thiếu tie-breaker có thể không lộ ra.

Tạo 12 Order:

```text
createdAt = 2026-11-15T09:00:00Z cho cả 12 Order
id = 101..112
status = PAID
```

Query:

```hql
select o.id
from PurchaseOrder o
where o.status = :status
order by o.createdAt desc, o.id desc
```

Với pageSize = 5, kỳ vọng:

| Trang | IDs |
|---|---|
| 0 | 112, 111, 110, 109, 108 |
| 1 | 107, 106, 105, 104, 103 |
| 2 | 102, 101 |

### Kiểm tra trong test

- Mỗi ID chỉ xuất hiện ở một trang nếu dữ liệu không thay đổi.
- Gộp tất cả trang thu đúng 12 ID.
- Thứ tự tương ứng `createdAt DESC, id DESC`.
- Trang cuối có 2 kết quả.
- Trang 3 rỗng.

Nếu bỏ `id DESC`, database không có nghĩa vụ trả một thứ tự ổn định cho 12 hàng cùng timestamp. Việc test trên một DB hiện vẫn ra thứ tự “đẹp” không chứng minh query đã đúng.

## 35. Kiểm thử INSERT giữa hai lần đọc trang

Kịch bản với page size = 3:

1. Seed IDs A–F với timestamp/ID tạo thứ tự `[F,E,D,C,B,A]`.
2. Query trang 0, ghi nhận `[F,E,D]`.
3. Trong transaction khác, insert G đứng trước F theo thứ tự.
4. Query trang 1 bằng offset = 3.
5. Quan sát `[D,C,B]` và ghi nhận D bị lặp.

### Mục tiêu bài thực hành

Không phải “sửa” offset để nó luôn ổn định trong mọi trường hợp, mà là **chứng minh giới hạn khi có concurrent inserts** và quyết định:

- UI có chấp nhận danh sách thay đổi không?
- Có cần “lần tải mới nhất” được ưu tiên cho người dùng?
- Có nên chuyển sang cursor?
- Có nên tạo snapshot cho báo cáo?

Sau đó triển khai keyset theo `(createdAt,id)` và thử cùng tình huống. So sánh khả năng tiếp tục duyệt của hai API.

## 36. Kiểm thử DELETE và UPDATE sort key giữa hai trang

### DELETE

1. Seed `[F,E,D,C,B,A]`.
2. Đọc trang đầu `[F,E,D]`.
3. Xóa E ở transaction khác.
4. Đọc trang 2 bằng `OFFSET 3`, nhận `[B,A]`.
5. Ghi nhận C bị bỏ sót.

### UPDATE sort key

1. Seed Order với thứ tự theo `updatedAt DESC,id DESC`.
2. Đọc trang 1.
3. Thay đổi `updatedAt` của một Order ở trang sau để nó di chuyển lên đầu.
4. Đọc trang 2.
5. Kiểm tra trùng/thiếu.

### Kết luận

Unique tie-breaker bảo đảm các hàng phân biệt rõ trong **mỗi truy vấn trên một snapshot nhất định**. Nó không bảo đảm các hàng giữ cùng vị trí khi nội dung hoặc sort key thay đổi.

## 37. Hệ thống nhiều tenant: pagination phải giữ cùng bộ lọc quyền

Nếu bảng có `tenant_id`:

```sql
SELECT id, order_number
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :size OFFSET :offset;
```

Count query cũng phải có **cùng ranh giới tenant/security**:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND status = :status;
```

Nếu data query lọc tenant nhưng count query không lọc tenant, totalElements có thể vừa sai vừa làm lộ số lượng dữ liệu của tenant khác.

### Đừng tin sort/filter của client thay thế phân quyền

Tenant ID phải đến từ ngữ cảnh tin cậy được xác thực, không sử dụng trực tiếp query param tùy ý để mở rộng phạm vi. Bộ lọc authorization là điều kiện bắt buộc, không phải một điều kiện optional trong builder.

Nếu có soft delete, điều kiện `deletedAt IS NULL` hoặc restriction tương ứng cũng phải nhất quán giữa data/count, và được kiểm thử theo mapping/dialect.

## 38. Pagination với DISTINCT, GROUP BY và aggregate

Giả sử danh sách cần trả **khách hàng** và tổng số Order:

```hql
select c.id, c.name, count(o)
from Customer c
left join c.orders o
group by c.id, c.name
order by count(o) desc, c.id asc
```

Ở đây mỗi hàng kết quả là **một nhóm Customer**, không phải một Order. Offset/limit phân trang **các nhóm** sau GROUP BY.

### Tie-breaker vẫn cần thiết

Nhiều Customer có cùng số Order, nên `ORDER BY count(o) DESC` chưa đủ. Thêm `c.id` để phân biệt nhóm.

### Count tổng nhóm khác COUNT row gốc

Để tính totalElements của một trang **Customer groups**, không thể dùng `COUNT(o)` rồi coi đó là số Customer. Phải đếm **số nhóm** đúng với HAVING/WHERE trong data query. Với aggregate phức tạp, count query có thể cần count distinct customer ID hoặc một subquery/derived table theo khả năng HQL/native.

Không sao chép nguyên `count(o)` sang metadata Page mà không xác định **một phần tử trang là loại bản ghi nào**.

## 39. Query phân trang ổn định có thể dùng updatedAt không?

Hoàn toàn có thể:

```hql
order by o.updatedAt desc, o.id desc
```

Thứ tự này **xác định** khi snapshot không đổi. Nhưng `updatedAt` là trường mutable: một Order được update sẽ nhảy lên đầu danh sách.

Nếu màn hình muốn “hoạt động vừa thay đổi”, đây có thể là hành vi mong muốn. Nếu export cần duyệt mỗi Order đúng một lần, dùng sort key mutable có thể rủi ro.

### Một lựa chọn cho batch

Sort theo khóa bất biến, tăng dần:

```hql
order by o.id asc
```

Kết hợp keyset theo ID:

```hql
where o.id > :lastId
order by o.id asc
```

Tuy nhiên, việc dùng ID làm sort key không bảo đảm phản ánh **thứ tự commit** của các transaction; generated IDs có thể được cấp trước commit và dữ liệu có thể xuất hiện muộn. Với đồng bộ dữ liệu có yêu cầu completeness mạnh, cần mô hình change tracking/CDC hoặc snapshot riêng, không chỉ dựa vào ID.

## 40. Lỗi thường gặp khi xây pagination

### Lỗi 1: Không có ORDER BY

Kết quả trang có thể không xác định. Luôn sort theo khóa có ý nghĩa và tie-breaker.

### Lỗi 2: Chỉ ORDER BY createdAt

Timestamp trùng, hàng có thể hoán đổi qua các trang. Thêm unique ID hoặc composite key cuối cùng.

### Lỗi 3: Cho rằng tie-breaker ngăn mọi duplicate/skip

INSERT/DELETE/UPDATE giữa các query vẫn làm thay đổi vị trí offset. Muốn đọc ổn định hơn qua nhiều request, cân nhắc cursor/snapshot.

### Lỗi 4: Nhầm pageNumber với offset

`setFirstResult(3)` bỏ 3 hàng, không tự nhảy đến trang 3. Offset là `pageIndex * pageSize`.

### Lỗi 5: Trang 1-based bị đưa thẳng vào PageRequest 0-based

`PageRequest.of(1, 20)` là trang thứ hai. Quy đổi và tài liệu hóa contract API.

### Lỗi 6: Không validate pageSize hoặc offset overflow

Client có thể yêu cầu size cực lớn hoặc page quá sâu. Giới hạn size/page và dùng phép tính an toàn.

### Lỗi 7: Fetch join collection rồi phân trang root

SQL có thể nhân hàng và Hibernate có thể phân trang trong bộ nhớ. Tách query lấy IDs và query tải collection.

### Lỗi 8: Join to-many làm root trùng

Phân trang raw joined rows có thể cho thiếu entity. Dùng EXISTS, distinct phù hợp hoặc hai bước.

### Lỗi 9: Count query không cùng filter

TotalElements sai, thậm chí lộ dữ liệu tenant. Dùng cùng logic filter/security, nhưng root/predicate objects riêng theo Criteria.

### Lỗi 10: Sort động lấy tên cột nguyên từ client

Có thể truy cập field không mong muốn hoặc làm query lỗi. Dùng allow-list của các thuộc tính được phép.

### Lỗi 11: Không quy định NULL ordering

Sort theo nullable field có thể khác giữa DB. Xác định NULLS FIRST/LAST hoặc biểu thức CASE.

### Lỗi 12: Tin rằng OFFSET lớn vẫn nhanh vì có index

Index giúp, nhưng DB vẫn có thể phải đi qua nhiều row trước khi đến trang sâu. Đo EXPLAIN và latency.

### Lỗi 13: Dựa vào thứ tự của IN list trong query thứ hai

`WHERE id IN (:ids)` không giữ thứ tự IDs truyền vào. Sắp lại theo trang đã chọn hoặc ORDER BY tường minh.

### Lỗi 14: Count mọi lần dù UI chỉ cần hasNext

Count phức tạp có thể đắt. Dùng size+1/Slice khi đáp ứng contract.

### Lỗi 15: Chỉ thử với dữ liệu có sort key duy nhất

Không phát hiện tie-breaker bị thiếu. Seed nhiều hàng cùng timestamp/amount/name trong integration test.

## 41. Một ví dụ repository trả PageResponse

DTO:

```java
public record OrderSummary(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) {}

public record PageResponse<T>(
    List<T> items,
    int pageIndex,
    int pageSize,
    long totalElements,
    long totalPages,
    boolean hasNext
) {}
```

Repository:

```java
@Repository
public class OrderPageRepository {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public PageResponse<OrderSummary> findPaidOrders(
            int pageIndex,
            int pageSize) {

        if (pageIndex < 0) {
            throw new IllegalArgumentException("Invalid pageIndex");
        }
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid pageSize");
        }

        final int offset;
        try {
            offset = Math.multiplyExact(pageIndex, pageSize);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                "Page offset is too large", ex
            );
        }

        List<OrderSummary> items = em.createQuery(
            "select new com.example.orders.OrderSummary(" +
            "o.id, o.orderNumber, o.status, " +
            "o.totalAmount, o.createdAt) " +
            "from PurchaseOrder o " +
            "where o.status = :status " +
            "order by o.createdAt desc, o.id desc",
            OrderSummary.class
        )
        .setParameter("status", OrderStatus.PAID)
        .setFirstResult(offset)
        .setMaxResults(pageSize)
        .getResultList();

        long total = em.createQuery(
            "select count(o) from PurchaseOrder o " +
            "where o.status = :status",
            Long.class
        )
        .setParameter("status", OrderStatus.PAID)
        .getSingleResult();

        long totalPages =
            total / pageSize + (total % pageSize == 0 ? 0 : 1);

        boolean hasNext =
            (long) pageIndex + 1 < totalPages;

        return new PageResponse<>(
            items,
            pageIndex,
            pageSize,
            total,
            totalPages,
            hasNext
        );
    }
}
```

### Phân tích thiết kế

- `OrderSummary` là projection: không hydrate toàn bộ entity graph.
- HQL có thứ tự xác định: `createdAt DESC, id DESC`.
- Offset được tính với kiểm tra overflow.
- Page size có giới hạn.
- Count query dùng cùng predicate `status`, không có sort/fetch join.
- Tính `totalPages` bằng chia nguyên và phần dư.
- `hasNext` dựa trên metadata COUNT; nếu dữ liệu đổi giữa hai query, metadata có thể không hoàn toàn cùng snapshot.

**Mã là ví dụ tập trung vào pagination**, chưa bao gồm bộ lọc tenant, quyền truy cập, các trạng thái khác, cursor, exception translation và transaction isolation được lựa chọn rõ theo database. Khi áp dụng trong hệ thống thực, những quy tắc ấy cần bổ sung theo use case.

## 42. Khi nào nên giữ OFFSET, khi nào nên chuyển cách khác?

### Giữ OFFSET khi

- UI có số trang và cho phép nhảy trực tiếp tới trang N.
- Tập dữ liệu không quá lớn hoặc chỉ truy cập trang đầu.
- Người dùng chấp nhận dữ liệu thay đổi giữa các request.
- ORDER BY có khóa tổng thứ tự.
- Index và query plan đáp ứng yêu cầu latency.
- `totalElements`/`totalPages` có giá trị với nghiệp vụ.

### Cân nhắc keyset/cursor khi

- Dữ liệu rất lớn và người dùng duyệt tuần tự.
- Trang sâu làm query chậm.
- Feed cuộn vô hạn, không cần nhảy ngẫu nhiên theo số trang.
- Bản ghi mới thường được insert lên đầu danh sách.
- Muốn giảm duplicate/skip do dịch chuyển offset.
- Sort keys có thể tạo cursor rõ ràng và ổn định phù hợp nghiệp vụ.

### Cân nhắc snapshot/batch riêng khi

- Yêu cầu xuất toàn bộ dữ liệu đúng một lần theo một tập cố định.
- Tính nhất quán giữa mọi trang quan trọng hơn việc thấy dữ liệu mới nhất.
- Quy trình dài cần checkpoint/restart.
- Số lượng bản ghi quá lớn để duy trì một request/transaction.

Không cố biến một API Page đơn giản thành cơ chế đồng bộ dữ liệu mạnh nếu nó chưa được thiết kế cho mục tiêu đó.

## 43. Bài thực hành 1: trang đầu, giữa và cuối

Tạo 53 Order có `status = PAID`, cùng đủ trường sort.

Yêu cầu:

1. Phân trang `pageSize = 10`.
2. Kiểm tra `pageIndex = 0` trả 10 Order đầu.
3. `pageIndex = 2` trả 10 Order vị trí 21–30.
4. `pageIndex = 5` trả 3 Order cuối.
5. `pageIndex = 6` trả danh sách rỗng.
6. Count query trả 53 và totalPages = 6.
7. Kiểm tra API 1-based nếu giao diện sử dụng page numbers cho người dùng.

Không viết `OFFSET 20` rồi kết luận trang đang có ID từ 21 đến 30: các ID có thể không liên tục.

## 44. Bài thực hành 2: dữ liệu cùng timestamp

Seed:

```text
Order 101..120
Tất cả createdAt = 2026-11-15T09:00:00Z
status = PAID
```

So sánh:

```hql
order by o.createdAt desc
```

và:

```hql
order by o.createdAt desc, o.id desc
```

Đọc bốn trang, mỗi trang 5 Order.

### Kỳ vọng đúng

Query có ID tie-breaker phải trả lần lượt:

```text
Trang 0: 120 119 118 117 116
Trang 1: 115 114 113 112 111
Trang 2: 110 109 108 107 106
Trang 3: 105 104 103 102 101
```

Query không có ID tie-breaker không có hợp đồng bảo đảm kết quả đó, dù test tình cờ chạy đúng một vài lần.

## 45. Bài thực hành 3: tác động concurrent inserts

1. Query trang 1 theo `createdAt DESC, id DESC`.
2. Insert thêm nhiều Order mới có timestamp đứng trước tất cả Order cũ.
3. Query trang 2 dùng offset.
4. Ghi nhận duplicate/skip so với trang 1.
5. Thử cursor dựa trên `(createdAt,id)`.
6. Giải thích vì sao cursor giảm vấn đề dịch chuyển khi insert phía trước.

Phân biệt rõ kết quả của `ORDER BY` xác định với yêu cầu đọc nhất quán qua nhiều HTTP request.

## 46. Bài thực hành 4: phân trang với OrderLine

Tạo:

```text
Order 1: 5 lines
Order 2: 2 lines
Order 3: 0 lines
Order 4: 10 lines
```

Thực hiện:

1. Viết query JOIN FETCH lines rồi `setMaxResults(2)`.
2. Quan sát SQL, warning và số rows được đọc.
3. Chuyển sang query trang IDs trước, sau đó tải lines cho IDs.
4. Sắp xếp lại kết quả của query thứ hai theo ID list trang đầu.
5. Nếu chỉ cần count lines, viết projection/aggregate thay vì fetch toàn bộ collection.

Nếu dùng cấu hình fail-fast cho pagination over collection fetch, xác nhận test phát hiện query không phù hợp.

## 47. Bài thực hành 5: COUNT, Slice và deep OFFSET

Với một bảng đủ lớn:

1. Tạo index phù hợp `(status, created_at DESC, id DESC)`.
2. Đo trang 1, trang 100 và trang 10.000 bằng offset.
3. Đo COUNT trên cùng filter.
4. Thử cách lấy `size+1` để xác định `hasNext`.
5. Thử keyset theo cặp `(createdAt,id)`.
6. So sánh `EXPLAIN`, buffer reads và latency.
7. Nêu rõ bài toán nào cần totalPages, bài toán nào không.

Đừng chỉ so sánh số câu SQL; hãy đo công việc thực tế của database.

## 48. Câu hỏi tự kiểm tra

1. `OFFSET 40 LIMIT 20` nghĩa là từ ID 41 đến ID 60 hay vị trí kết quả 41 đến 60?
2. Tại sao query không có ORDER BY có thể trả kết quả trang khác nhau?
3. Vì sao `ORDER BY createdAt DESC` chưa chắc ổn định?
4. Thêm `id DESC` giải quyết vấn đề gì?
5. Tại sao unique tie-breaker không ngăn duplicate/skip do INSERT giữa hai trang?
6. `setFirstResult(20)` là trang thứ 20 hay bỏ qua 20 kết quả?
7. `PageRequest.of(1, 20)` là trang mấy theo 0-based?
8. Vì sao `Math.multiplyExact` hữu ích khi tính offset?
9. Khi JOIN sang collection, tại sao số hàng SQL có thể lớn hơn số Order?
10. Vì sao JOIN FETCH collection có thể khiến Hibernate phân trang trong bộ nhớ?
11. Tại sao query thứ hai `WHERE id IN (:ids)` không bảo đảm thứ tự IDs?
12. Khi nào dùng COUNT và khi nào dùng size+1/Slice?
13. Vì sao COUNT query phải có cùng filter tenant và soft delete?
14. READ COMMITTED có bảo đảm hai HTTP request thấy cùng snapshot không?
15. Keyset khác offset ở cách xác định vị trí tiếp tục ra sao?
16. Tại sao deep offset có thể chậm dù có index?
17. Trường sort nullable cần xác định điều gì?
18. Nếu sort theo field của collection to-many, vấn đề cardinality là gì?
19. Query sort theo updatedAt có ổn định trước các update đồng thời không?
20. Khi nào export nên dùng snapshot/batch thay vì API page thông thường?

**Gợi ý:** (1) vị trí, không phải ID; (2) SQL không bảo đảm thứ tự mặc định; (3) timestamp trùng; (4) total order; (5) vị trí offset dịch chuyển; (6) bỏ 20 kết quả; (7) trang thứ hai; (8) phát hiện overflow; (9) một Order có nhiều lines; (10) LIMIT trên joined rows có thể cắt collection/root; (11) IN không giữ thứ tự; (12) khi cần total so với chỉ hasNext; (13) tính đúng và bảo mật; (14) không; (15) theo khóa sort cuối; (16) phải đi qua nhiều hàng; (17) null ordering; (18) nhiều sort key cho cùng root; (19) không qua nhiều snapshot; (20) khi cần duyệt tập dữ liệu cố định.

## 49. Những nguyên tắc quan trọng cần nhớ

1. **OFFSET pagination lấy một cửa sổ theo vị trí trong kết quả đã sắp xếp.** `offset = pageIndex × pageSize` với pageIndex 0-based.
2. **Luôn có ORDER BY rõ ràng.** Không được tin vào thứ tự vật lý, thứ tự ID ngầm định hoặc một lần chạy “có vẻ đúng”.
3. **Thêm tie-breaker duy nhất để tạo total order.** `createdAt DESC, id DESC` là một mẫu dễ dùng nếu ID unique.
4. **Thứ tự xác định không đồng nghĩa snapshot bất biến.** INSERT/DELETE/UPDATE giữa hai request vẫn có thể gây duplicate/skip.
5. **HQL/Criteria sử dụng `setFirstResult` và `setMaxResults` thuận tiện.** Kiểm tra offset overflow và giới hạn page size.
6. **JOIN to-many và collection fetch join cần được xem xét trước khi phân trang.** Result set nhân hàng có thể làm sai số root hoặc buộc pagination trong memory.
7. **Count query là một bài toán riêng.** Dùng cùng filter nhưng bỏ sort/fetch; đếm đúng đơn vị phần tử trang.
8. **DTO projection và Slice có thể giảm chi phí.** Không phải màn hình nào cũng cần hydrate entity graph hoặc COUNT chính xác.
9. **Deep offset có chi phí tăng theo lượng dữ liệu phải đi qua.** Kiểm tra index, query plan và chuyển keyset/cursor khi phù hợp.
10. **Sort theo nullable/text/mutable field cần quy tắc rõ.** Null ordering, collation và thay đổi sort key đều ảnh hưởng trải nghiệm trang.
11. **Data/COUNT phải giữ cùng tenant/security scope.** Pagination không được lách ranh giới quyền truy cập.
12. **Kiểm thử bằng dữ liệu trùng sort key và concurrency.** Test trang đầu/trang cuối thôi chưa đủ để phát hiện sai lệch.

Khi thiết kế một danh sách Hibernate có phân trang, hãy bắt đầu bằng câu hỏi **“Một phần tử trang là gì?”** rồi xác định bộ lọc, `ORDER BY` tạo total order, kích thước trang, chi phí count và fetch plan. Nếu người dùng cần đi qua một tập dữ liệu liên tục đang thay đổi, cần cân nhắc cursor hoặc snapshot chứ không thể chỉ thêm `id` vào ORDER BY và coi mọi vấn đề đã được giải quyết.

### Tài liệu tham khảo chính thức

- [Hibernate ORM Query Language — Limits and offsets](https://docs.jboss.org/hibernate/orm/current/querylanguage/html_single/Hibernate_Query_Language.html)
- [Hibernate ORM User Guide — Query API](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#hql)
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM User Guide — Batch fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching-batch)
- [Jakarta Persistence API — Query](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/Query)
- [Jakarta Persistence API — TypedQuery](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/TypedQuery)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data JPA — Paging and Sorting](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [PostgreSQL documentation — LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html)
- [PostgreSQL documentation — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html)
