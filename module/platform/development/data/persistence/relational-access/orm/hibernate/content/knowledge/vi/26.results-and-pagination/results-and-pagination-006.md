# Phân trang theo khóa để xử lý tập dữ liệu lớn

Khi bảng dữ liệu có hàng triệu hoặc hàng trăm triệu bản ghi, cách phân trang truyền thống bằng `OFFSET` và `LIMIT` thường trở nên tốn kém ở các trang sâu. Nếu người dùng yêu cầu trang thứ 50.000, database có thể phải đi qua rất nhiều hàng thỏa điều kiện trước khi trả về 20 hàng cuối cùng. Đồng thời, khi dữ liệu liên tục được thêm, xóa hoặc thay đổi, phân trang theo vị trí có thể gây **lặp hoặc bỏ sót** bản ghi giữa hai lần người dùng nhấn “Trang tiếp theo”.

**Phân trang theo khóa** (*keyset pagination*, còn gọi là *seek pagination* hoặc *cursor-based pagination* khi API dùng cursor) giải quyết phần lớn vấn đề này bằng cách:

1. Sắp xếp theo một **thứ tự xác định và ổn định**.
2. Ghi nhớ giá trị khóa sắp xếp của bản ghi cuối cùng đã trả.
3. Ở trang sau, dùng điều kiện `WHERE` để lấy những bản ghi **đứng sau khóa đó**.
4. Giới hạn chỉ số bản ghi cần lấy bằng `LIMIT` hoặc `setMaxResults()`.

Thay vì hỏi “bỏ qua 1.000.000 hàng”, ta hỏi “lấy 20 hàng tiếp theo sau khóa `(createdAt, id)`”. Với index phù hợp, database thường tìm tới vị trí khóa rồi đọc một lượng dữ liệu gần với kích thước trang.

Trong Hibernate/JPA, keyset pagination có thể triển khai bằng **HQL/JPQL**, **Criteria API** hoặc **native SQL**. Một số phiên bản Hibernate/Spring Data cũng cung cấp API hỗ trợ scrolling/keyset riêng; bài học tập trung trước hết vào thuật toán và hợp đồng dữ liệu vì chúng quyết định tính đúng đắn bất kể API nào được chọn.

## 1. Bài toán: OFFSET sâu ngày càng đắt

Giả sử một hệ thống bán hàng có bảng `purchase_orders`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL
);
~~~

Cần xem các đơn đã hoàn tất, mới nhất trước:

~~~sql
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND status = 'COMPLETED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

Trang đầu dùng `OFFSET 0`. Trang 2 dùng `OFFSET 20`. Với kích thước 20, trang có offset 1.000.000 thường biểu diễn:

~~~sql
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND status = 'COMPLETED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 1000000;
~~~

Ngay cả khi có index hữu ích, database vẫn có thể phải đi qua một lượng lớn hàng phù hợp để tìm đến vị trí thứ 1.000.001. Cách tính cụ thể tùy execution plan, nhưng **chi phí đọc/bỏ qua thường tăng theo offset**.

### 1.1. OFFSET biểu diễn vị trí, không biểu diễn danh tính bản ghi

`OFFSET 20` có nghĩa “bỏ qua 20 hàng đầu của kết quả **ở thời điểm truy vấn này**”. Nó không nói điều gì về những hàng đã xuất hiện trong trang trước.

Nếu một hàng mới được thêm vào đầu danh sách giữa hai request, vị trí các hàng cũ bị dịch xuống. Vì vậy, trang sau có thể chứa một hàng người dùng đã thấy.

### 1.2. Ví dụ lặp do insert mới

Giả sử sắp xếp giảm dần theo ID:

~~~text
Trước insert:
Trang 1 (limit 3) = [105, 104, 103]
Trang 2 (offset 3) = [102, 101, 100]

Sau khi trang 1 được đọc, thêm bản ghi 106:
Danh sách hiện tại = [106, 105, 104, 103, 102, 101, 100]

Trang 2 (offset 3) lúc này = [103, 102, 101]
~~~

Bản ghi **103 xuất hiện hai lần** ở hai trang. Nếu có xóa hoặc thay đổi vị trí sắp xếp, có thể xảy ra trường hợp bị bỏ sót.

### 1.3. Khi nào OFFSET vẫn phù hợp?

OFFSET không phải kỹ thuật sai. Nó phù hợp khi:

- Tập dữ liệu nhỏ hoặc số trang tối đa thấp.
- Người dùng cần nhảy trực tiếp tới trang 7, 50 hoặc 200.
- Cần UI kiểu số trang với tổng số trang.
- Chi phí scan/skip đã được đo và chấp nhận được.
- Truy vấn phục vụ báo cáo snapshot tương đối tĩnh.

Keyset đáng cân nhắc hơn với **infinite scroll**, timeline, feed, danh sách hoạt động, API “load more” hoặc batch duyệt rất nhiều bản ghi theo thứ tự.

## 2. Ý tưởng của keyset pagination

Với thứ tự:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

đặt cursor tại hàng cuối của trang trước:

~~~text
created_at = 2026-11-15T09:30:00Z
id         = 8901
~~~

Trang tiếp theo sẽ lấy những hàng **đứng sau cursor** trong thứ tự giảm dần:

~~~sql
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND status = 'COMPLETED'
  AND (
       created_at < :cursorCreatedAt
       OR (
           created_at = :cursorCreatedAt
           AND id < :cursorId
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Nếu có index phù hợp, database có thể dùng các giá trị `created_at` và `id` để tìm vùng kết quả tiếp theo thay vì bỏ qua một offset lớn.

### 2.1. Minh họa thứ tự

~~~text
Thứ tự giảm dần theo (createdAt, id)

(10:05, 205)   ┐
(10:04, 204)   │ Trang 1 — 3 bản ghi
(10:04, 201)   ┘ ← cursor = (10:04, 201)
----------------
(10:03, 199)   ┐
(10:03, 198)   │ Trang 2
(10:02, 197)   ┘
~~~

Query trang 2 phải lấy những hàng có timestamp nhỏ hơn 10:04, **hoặc** timestamp bằng 10:04 nhưng ID nhỏ hơn 201.

### 2.2. Cursor là ranh giới, không phải số trang

Một cursor thường chứa các giá trị sort key của một hàng cụ thể. Nó không biểu diễn “trang số 42” và không bảo đảm có thể nhảy ngẫu nhiên tới vị trí không có cursor.

Điểm mạnh của keyset là **đi tiếp tuần tự**. Điểm yếu là không tự cung cấp random access tới trang N nếu chưa có điểm neo.

### 2.3. Keyset và cursor không hoàn toàn đồng nghĩa

- **Keyset pagination** là thuật toán lấy những hàng sau/trước bộ khóa sắp xếp.
- **Cursor** là cách biểu diễn điểm neo của trang trong API, thường dưới dạng token opaque.
- Một API có cursor có thể dùng cách thực thi khác keyset, nhưng trong ứng dụng quan hệ, keyset là cách phổ biến để hiện thực cursor pagination.

## 3. Điều kiện bắt buộc: thứ tự toàn phần

Để keyset hoạt động đúng, `ORDER BY` phải tạo một thứ tự xác định. Nếu chỉ:

~~~sql
ORDER BY created_at DESC
~~~

thì các đơn hàng có cùng `created_at` không có vị trí ổn định tương đối với nhau.

Ví dụ:

| id | created_at |
| ---: | --- |
| 205 | 10:04:00 |
| 204 | 10:04:00 |
| 203 | 10:04:00 |
| 202 | 10:04:00 |

Nếu trang đầu dừng ở ID 204 nhưng cursor chỉ ghi timestamp 10:04:00, điều kiện:

~~~sql
WHERE created_at < :cursorCreatedAt
~~~

sẽ **bỏ qua** các bản ghi 203 và 202 dù chúng chưa được trả về.

### 3.1. Thêm khóa duy nhất làm tie-breaker

Cách thường dùng:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

`id` là khóa duy nhất, giúp mọi hàng có vị trí xác định ngay cả khi timestamp trùng nhau.

Với một bản ghi có khóa `(created_at, id)`, điều kiện tìm hàng sau là:

~~~sql
created_at < :cursorCreatedAt
OR (
    created_at = :cursorCreatedAt
    AND id < :cursorId
)
~~~

**Điều kiện WHERE phải tương thích với toàn bộ ORDER BY**, bao gồm cả hướng tăng/giảm của từng thành phần.

### 3.2. Có bắt buộc dùng primary key?

Không. Có thể dùng bất kỳ tổ hợp cột nào tạo **khóa sắp xếp duy nhất và ổn định** trong tập dữ liệu mục tiêu. ID thường là lựa chọn đơn giản vì đã unique và dễ tham chiếu.

Nếu hệ thống có composite primary key hoặc ID chỉ unique trong tenant, cursor phải mang đủ trường để phân biệt hàng trong scope tương ứng.

### 3.3. Không dùng khóa có giá trị NULL tùy tiện

Phép so sánh `<`, `>` với `NULL` trong SQL thường không tạo TRUE. Hơn nữa, database khác nhau có thứ tự NULL mặc định khác nhau.

Để đơn giản và đáng tin, các trường làm keyset sort nên **NOT NULL**. Nếu nghiệp vụ yêu cầu sort theo field nullable, cần định nghĩa rõ `NULLS FIRST/LAST`, biểu thức xử lý null, cursor encoding và predicate tương ứng; không thể chỉ thay `<` thành `>`.

## 4. Công thức cho thứ tự tăng và giảm

Cho bộ khóa gồm hai trường `(a, b)`, trong đó `b` là tie-breaker duy nhất.

### 4.1. Cả hai giảm dần

~~~sql
ORDER BY a DESC, b DESC
~~~

Hàng **sau cursor**:

~~~sql
WHERE a < :a
   OR (a = :a AND b < :b)
~~~

### 4.2. Cả hai tăng dần

~~~sql
ORDER BY a ASC, b ASC
~~~

Hàng **sau cursor**:

~~~sql
WHERE a > :a
   OR (a = :a AND b > :b)
~~~

### 4.3. Hướng hỗn hợp

~~~sql
ORDER BY a DESC, b ASC
~~~

Hàng **sau cursor**:

~~~sql
WHERE a < :a
   OR (a = :a AND b > :b)
~~~

Không thể dùng cùng một dấu so sánh cho mọi cột khi hướng sort khác nhau.

### 4.4. Nhiều khóa sắp xếp

Ví dụ:

~~~sql
ORDER BY total_amount DESC,
         created_at ASC,
         id ASC
~~~

Điều kiện lấy hàng đứng sau cursor:

~~~sql
WHERE total_amount < :amount
   OR (
       total_amount = :amount
       AND created_at > :createdAt
   )
   OR (
       total_amount = :amount
       AND created_at = :createdAt
       AND id > :id
   )
~~~

Đây là **so sánh thứ tự từ trái sang phải**, còn gọi là lexicographic comparison. Trường tiếp theo chỉ được xét khi toàn bộ trường trước đó bằng nhau.

### 4.5. Row-value comparison có thể ngắn hơn

Trên những database hỗ trợ so sánh tuple/row-value:

~~~sql
WHERE (created_at, id) < (:createdAt, :id)
ORDER BY created_at DESC, id DESC
~~~

có thể biểu đạt gọn cho **hai trường cùng hướng giảm dần**, với semantics NULL và kiểu dữ liệu phù hợp.

Tuy nhiên, khả năng SQL tuple comparison và cách Hibernate/dialect biểu diễn trong HQL khác nhau. Dạng `OR` tường minh dễ hiểu hơn và thường có khả năng tương thích tốt hơn. Với mixed directions, không thể máy móc dùng một dấu `<` cho cả tuple.

## 5. OFFSET so với keyset qua số hàng cần đọc

Một phép ước lượng giúp hiểu vấn đề:

| Bối cảnh | OFFSET pagination | Keyset pagination |
| --- | --- | --- |
| Trang đầu 20 hàng | Đọc giới hạn nhỏ | Đọc giới hạn nhỏ |
| Đi tiếp từ hàng thứ 1 triệu | Thường phải đi qua rất nhiều hàng trước đó | Có thể seek theo khóa rồi đọc tiếp nếu index phù hợp |
| Thêm hàng trước vị trí đã đọc | Dễ dịch vị trí, gây trùng | Cursor giữ ranh giới khóa cũ |
| Xóa hàng trước vị trí đã đọc | Dễ dịch vị trí, gây thiếu | Cursor ít nhạy với thay đổi ở phần đã đi qua |
| Nhảy thẳng trang 500 | Tự nhiên | Không có random access trực tiếp nếu không có mốc cursor |
| Tổng số trang | Dễ ghép COUNT | Thường dùng hasNext, không nhất thiết COUNT |
| Sắp xếp không duy nhất | Cũng bất ổn | Đặc biệt nguy hiểm, có thể mất hàng |
| Sắp xếp thay đổi thường xuyên | Có thể lặp/bỏ sót | Vẫn có thể lặp/bỏ sót nếu chính sort key đổi |
| Index phù hợp | Có ích, nhưng offset vẫn là chi phí | Là điều kiện quan trọng để seek hiệu quả |

Keyset **không bảo đảm thời gian O(page size) trong mọi trường hợp**. Filter kém chọn lọc, index không phù hợp, sort expression phức tạp, JOIN/aggregate hoặc execution plan xấu có thể làm database quét rất nhiều hàng.

## 6. Entity và schema dùng trong ví dụ Hibernate

Giả sử entity:

~~~java
package com.example.orders;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Version
    private Long version;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public OrderStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
~~~

~~~java
public enum OrderStatus {
    DRAFT, PAID, COMPLETED, CANCELLED
}
~~~

Dữ liệu ví dụ:

| id | created_at (UTC) | status | total_amount |
| ---: | --- | --- | ---: |
| 105 | 2026-11-15 10:10 | COMPLETED | 120 |
| 104 | 2026-11-15 10:08 | COMPLETED | 200 |
| 103 | 2026-11-15 10:08 | COMPLETED | 50 |
| 102 | 2026-11-15 10:05 | COMPLETED | 95 |
| 101 | 2026-11-15 10:00 | COMPLETED | 75 |

Bảng bỏ cột tenant cho gọn; trong mọi truy vấn thực tế bên dưới, bộ lọc `tenantId` vẫn là bắt buộc.

### 6.1. Index cho truy vấn mẫu

PostgreSQL:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
~~~

Index này thường hữu ích cho các query có equality filter trên `tenant_id`, `status` và duyệt theo `created_at DESC, id DESC`.

Nếu API có nhiều loại filter/sort khác nhau, một index không giải quyết mọi trường hợp. Cần đo trên dữ liệu thực tế và xem execution plan.

### 6.2. Vì sao createdAt thường nên bất biến?

Nếu timestamp tạo đơn được gán một lần và không sửa, một bản ghi ít có nguy cơ di chuyển qua ranh giới cursor khi người dùng phân trang. Nếu người dùng được phép chỉnh createdAt, một record có thể chuyển từ phía sau cursor sang phía trước hoặc ngược lại.

Keyset dùng một **sort key ổn định** cho trải nghiệm duyệt dữ liệu dễ dự đoán hơn. Với feed “cập nhật mới nhất”, nếu phải sort theo `updatedAt` thường xuyên thay đổi, cần chấp nhận semantics gần real-time hoặc áp dụng snapshot/consistency strategy.

## 7. HQL: trang đầu

Với đơn đã hoàn tất:

~~~java
String hql = """
    select new com.example.orders.OrderRow(
        o.id,
        o.createdAt,
        o.totalAmount
    )
    from PurchaseOrder o
    where o.tenantId = :tenantId
      and o.status = :status
    order by o.createdAt desc, o.id desc
    """;

List<OrderRow> rows = em.createQuery(hql, OrderRow.class)
    .setParameter("tenantId", tenantId)
    .setParameter("status", OrderStatus.COMPLETED)
    .setMaxResults(pageSize + 1)
    .getResultList();
~~~

DTO:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderRow(
    Long id,
    Instant createdAt,
    BigDecimal totalAmount
) {}
~~~

Ý nghĩa:

- Không cần `OFFSET` cho trang đầu.
- Các entity được lọc trong đúng tenant.
- Sort có tie-breaker `id`.
- Chỉ lấy các cột cần hiển thị.
- Lấy `pageSize + 1` thay vì đúng pageSize để biết có trang sau hay không.

### 7.1. Vì sao lấy thêm một hàng?

Nếu pageSize = 3, câu query trả về tối đa 4 hàng. Khi nhận 4 hàng, ta biết có ít nhất một bản ghi nằm sau ba hàng của trang hiện tại.

Ví dụ:

~~~text
Query trả: [105, 104, 103, 102]
API hiển thị: [105, 104, 103]
hasNext = true
nextCursor lấy từ hàng 103
~~~

**Cursor được tạo từ hàng cuối đã trả cho client**, không phải từ hàng thứ tư bị dùng làm sentinel. Nếu dùng hàng 102 làm cursor, client sẽ không bao giờ thấy hàng 102.

Nếu query chỉ trả tối đa 3 hàng, `hasNext = false`. Không cần chạy COUNT chỉ để biết có thêm dữ liệu.

### 7.2. Kiểm tra pageSize

Không đưa giá trị pageSize không kiểm soát trực tiếp vào query. Ví dụ cho phép 1–100:

~~~java
if (pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException(
        "pageSize phải nằm trong [1,100]");
}
~~~

Dùng `Math.addExact(pageSize, 1)` nếu muốn rõ về overflow; với giới hạn tối đa 100, cộng 1 là an toàn.

## 8. HQL: trang sau với điều kiện seek

Khi trang trước trả cursor:

~~~text
createdAt = 2026-11-15T10:08:00Z
id        = 103
~~~

trang sau:

~~~java
String hql = """
    select new com.example.orders.OrderRow(
        o.id,
        o.createdAt,
        o.totalAmount
    )
    from PurchaseOrder o
    where o.tenantId = :tenantId
      and o.status = :status
      and (
          o.createdAt < :afterCreatedAt
          or (
              o.createdAt = :afterCreatedAt
              and o.id < :afterId
          )
      )
    order by o.createdAt desc, o.id desc
    """;

List<OrderRow> rows = em.createQuery(hql, OrderRow.class)
    .setParameter("tenantId", tenantId)
    .setParameter("status", OrderStatus.COMPLETED)
    .setParameter("afterCreatedAt", cursorCreatedAt)
    .setParameter("afterId", cursorId)
    .setMaxResults(pageSize + 1)
    .getResultList();
~~~

Đây là JPQL/HQL thông thường, không cần `OFFSET` hay extension riêng để thực hiện seek.

### 8.1. Predicate nghiêm ngặt, không dùng <=

Không dùng:

~~~sql
created_at <= :cursorCreatedAt
~~~

vì có thể lấy lại hàng ở ranh giới hoặc bỏ sót những hàng trùng timestamp nếu không xét ID. Dùng phép so sánh nghiêm ngặt trên **toàn bộ bộ khóa** như trong ví dụ.

### 8.2. Không dựa vào ID tăng theo thời gian một cách mù quáng

Nếu sort chính là `createdAt DESC`, cursor **phải chứa createdAt**. Không thể chỉ dùng `id < :lastId` trừ khi chính thứ tự nghiệp vụ là `ORDER BY id DESC`.

ID sinh tăng không cam kết luôn tương ứng thời gian tạo trong môi trường distributed writers, imports, sequence caching hoặc các trường hợp transaction commit khác thứ tự.

## 9. Service hoàn chỉnh: first page và next page

Ta định nghĩa cursor key nội bộ:

~~~java
package com.example.orders;

import java.time.Instant;

public record OrderCursorKey(
    Instant createdAt,
    Long id
) {}
~~~

Response:

~~~java
package com.example.orders;

import java.util.List;

public record KeysetPage<T>(
    List<T> items,
    String nextCursor,
    boolean hasNext
) {}
~~~

Giao diện mã hóa/giải mã cursor:

~~~java
package com.example.orders;

public interface OrderCursorCodec {

    String encode(
        long tenantId,
        OrderStatus status,
        OrderCursorKey key
    );

    OrderCursorKey decodeAndValidate(
        String token,
        long tenantId,
        OrderStatus status
    );
}
~~~

Một service minh họa:

~~~java
package com.example.orders;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class OrderFeedService {

    @PersistenceContext
    private EntityManager em;

    private final OrderCursorCodec codec;

    public OrderFeedService(OrderCursorCodec codec) {
        this.codec = codec;
    }

    @Transactional(readOnly = true)
    public KeysetPage<OrderRow> list(
            long tenantId,
            OrderStatus status,
            int pageSize,
            String cursorToken) {

        if (tenantId <= 0 || status == null) {
            throw new IllegalArgumentException("Thiếu scope hợp lệ");
        }
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize không hợp lệ");
        }

        boolean firstPage =
            cursorToken == null || cursorToken.isBlank();

        OrderCursorKey after = firstPage
            ? null
            : codec.decodeAndValidate(cursorToken, tenantId, status);

        String hql = """
            select new com.example.orders.OrderRow(
                o.id, o.createdAt, o.totalAmount
            )
            from PurchaseOrder o
            where o.tenantId = :tenantId
              and o.status = :status
            """
            + (firstPage ? "" : """
                and (
                    o.createdAt < :afterCreatedAt
                    or (
                        o.createdAt = :afterCreatedAt
                        and o.id < :afterId
                    )
                )
                """)
            + """
                order by o.createdAt desc, o.id desc
                """;

        TypedQuery<OrderRow> query =
            em.createQuery(hql, OrderRow.class)
              .setParameter("tenantId", tenantId)
              .setParameter("status", status)
              .setMaxResults(pageSize + 1);

        if (after != null) {
            query.setParameter("afterCreatedAt", after.createdAt());
            query.setParameter("afterId", after.id());
        }

        List<OrderRow> fetched = query.getResultList();
        boolean hasNext = fetched.size() > pageSize;

        List<OrderRow> visible = hasNext
            ? List.copyOf(fetched.subList(0, pageSize))
            : List.copyOf(fetched);

        String nextCursor = null;

        if (hasNext && !visible.isEmpty()) {
            OrderRow last = visible.get(visible.size() - 1);
            nextCursor = codec.encode(
                tenantId,
                status,
                new OrderCursorKey(last.createdAt(), last.id())
            );
        }

        return new KeysetPage<>(visible, nextCursor, hasNext);
    }
}
~~~

Đây là ví dụ Spring + Jakarta Persistence; nếu không dùng Spring, thay phạm vi `@Transactional` bằng transaction handling phù hợp.

### 9.1. Đọc code theo từng bước

1. Validate tenant/status/pageSize.
2. Nếu có cursor, giải mã và xác minh cursor thuộc đúng scope.
3. Dựng query cố định với hoặc không có predicate seek.
4. Luôn bind dữ liệu bằng `setParameter()`.
5. Lấy tối đa `pageSize + 1` hàng.
6. Chỉ trả `pageSize` hàng cho client.
7. Tạo `nextCursor` từ **hàng cuối được trả**.
8. Nếu không còn hàng phía sau, trả `nextCursor = null` và `hasNext = false`.

### 9.2. Không coi tenantId từ request là đáng tin

Ví dụ để lộ `tenantId` như tham số method nhằm làm rõ SQL scope. Trong ứng dụng thật, tenant phải được lấy từ **ngữ cảnh xác thực/ủy quyền của server** thay vì tin trực tiếp dữ liệu client gửi.

Cursor có chứa tenant cũng không thay thế kiểm tra authorization. User không được chọn tenant khác chỉ bằng cách thay đổi token.

### 9.3. Vì sao tách codec thành interface?

Cursor thường đi qua HTTP và cần có hợp đồng mã hóa bảo mật, versioning, expiration và validation. Việc tách codec khỏi query giúp test độc lập logic seek và logic token, tránh trộn HMAC/JSON với persistence.

## 10. Thiết kế cursor token cho API

Một API có thể nhận:

~~~http
GET /orders?status=COMPLETED&pageSize=3
~~~

Response minh họa:

~~~json
{
  "items": [
    { "id": 105, "createdAt": "2026-11-15T10:10:00Z", "totalAmount": 120 },
    { "id": 104, "createdAt": "2026-11-15T10:08:00Z", "totalAmount": 200 },
    { "id": 103, "createdAt": "2026-11-15T10:08:00Z", "totalAmount": 50 }
  ],
  "hasNext": true,
  "nextCursor": "<opaque-signed-token>"
}
~~~

Client đi tiếp:

~~~http
GET /orders?status=COMPLETED&pageSize=3&after=<opaque-signed-token>
~~~

`nextCursor` nên được client coi là chuỗi opaque, không tự sửa timestamp/ID.

### 10.1. Thông tin cursor cần mang

Một payload nội bộ có thể có:

~~~json
{
  "v": 1,
  "sort": "createdAt:desc,id:desc",
  "tenantId": 42,
  "status": "COMPLETED",
  "createdAt": "2026-11-15T10:08:00Z",
  "id": 103,
  "expiresAt": "2026-11-15T11:08:00Z"
}
~~~

`v` là phiên bản schema cursor. Các trường `sort`, `tenantId`, `status` giúp server phát hiện token không thuộc query hiện tại. Với nhiều filter tùy chọn, nên chứa hoặc ký **fingerprint của bộ filter đã chuẩn hóa** (bao gồm sort và scope).

### 10.2. Base64 không phải mã hóa bảo mật

Token Base64URL chỉ biến bytes thành chuỗi URL-safe; nó **không giữ bí mật** nội dung. Người dùng có thể decode và đọc timestamp/ID nếu token là Base64 JSON.

Nếu payload có dữ liệu không được phép lộ, cần mã hóa được xác thực hoặc thiết kế token chỉ chứa thông tin không nhạy cảm. Dù dữ liệu không bí mật, vẫn nên bảo vệ tính toàn vẹn của cursor để ngăn sửa trường scope/sort.

### 10.3. Ký HMAC để chống sửa token

Một thiết kế thực tế:

~~~text
JSON payload
   ↓ UTF-8
Base64URL(payload) = body
   ↓
HMAC-SHA256(secret, body)
   ↓ Base64URL
token = body + "." + signature
~~~

Khi giải mã:

1. Giới hạn độ dài token.
2. Tách body và signature.
3. Kiểm tra chữ ký HMAC bằng so sánh thích hợp.
4. Parse JSON có giới hạn.
5. Kiểm tra `v` được hỗ trợ.
6. Kiểm tra hạn `expiresAt`.
7. Kiểm tra tenant/filter/sort trùng với request và principal hiện tại.
8. Kiểm tra ID/timestamp hợp lệ.
9. Chỉ sau đó mới dùng key trong truy vấn.

Không hardcode secret vào source repository; lấy từ cấu hình quản lý bí mật, hỗ trợ key rotation khi cần.

### 10.4. Ví dụ implementation phần ký HMAC

~~~java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

public final class CursorSigner {

    private final SecretKeySpec key;

    public CursorSigner(byte[] secret) {
        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException("Secret quá ngắn");
        }
        this.key = new SecretKeySpec(secret.clone(), "HmacSHA256");
    }

    private byte[] sign(String body) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            return mac.doFinal(
                body.getBytes(StandardCharsets.US_ASCII)
            );
        } catch (java.security.GeneralSecurityException ex) {
            throw new IllegalStateException("Không thể ký cursor", ex);
        }
    }

    public String encodeSignedJson(byte[] jsonUtf8) {
        String body = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(jsonUtf8);

        String signature = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(sign(body));

        return body + "." + signature;
    }

    public byte[] verifyAndDecode(String token) {
        if (token == null || token.length() > 4096) {
            throw new IllegalArgumentException("Cursor không hợp lệ");
        }

        String[] parts = token.split("\\.", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Cursor không hợp lệ");
        }

        try {
            byte[] actual = Base64.getUrlDecoder()
                .decode(parts[1]);
            byte[] expected = sign(parts[0]);

            if (!MessageDigest.isEqual(actual, expected)) {
                throw new IllegalArgumentException(
                    "Chữ ký cursor không hợp lệ");
            }

            return Base64.getUrlDecoder().decode(parts[0]);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                "Cursor không hợp lệ", ex);
        }
    }
}
~~~

Đoạn code minh họa phần **integrity/signing**, chưa phải toàn bộ `OrderCursorCodec`: ứng dụng còn phải serialize/deserialize JSON với schema chặt chẽ, kiểm tra expiration, version, scope, filter fingerprint và type constraints. `SecretKeySpec` sử dụng secret đã được cung cấp từ secret manager/config an toàn.

### 10.5. Token có thể chứa pageSize không?

Tùy hợp đồng API. Nếu muốn cho phép đổi pageSize giữa các request nhưng tiếp tục từ cùng key, không cần cố định pageSize trong token. Nếu UX/semantics yêu cầu nhất quán, có thể ràng buộc pageSize và từ chối thay đổi.

**Điều không được thay đổi âm thầm là logic sort và tập filter** khi dùng lại cursor. Nếu client đổi `status` nhưng tiếp tục từ khóa của status cũ, kết quả không còn biểu diễn tiếp nối của cùng truy vấn.

## 11. Criteria API: dựng predicate keyset

Criteria giúp thêm điều kiện seek vào một query builder có nhiều filter động.

Giả sử đã có:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<OrderRow> cq =
    cb.createQuery(OrderRow.class);
Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);
~~~

Dựng các predicate:

~~~java
List<Predicate> conditions = new ArrayList<>();

conditions.add(
    cb.equal(root.get("tenantId"), tenantId)
);
conditions.add(
    cb.equal(root.get("status"), OrderStatus.COMPLETED)
);

if (after != null) {
    Path<Instant> createdAt = root.get("createdAt");
    Path<Long> id = root.get("id");

    Predicate olderTime =
        cb.lessThan(createdAt, after.createdAt());

    Predicate sameTimeAndLowerId =
        cb.and(
            cb.equal(createdAt, after.createdAt()),
            cb.lessThan(id, after.id())
        );

    conditions.add(
        cb.or(olderTime, sameTimeAndLowerId)
    );
}
~~~

Hoàn thiện query:

~~~java
cq.select(cb.construct(
    OrderRow.class,
    root.get("id"),
    root.get("createdAt"),
    root.get("totalAmount")
));

cq.where(conditions.toArray(new Predicate[0]));

cq.orderBy(
    cb.desc(root.get("createdAt")),
    cb.desc(root.get("id"))
);

List<OrderRow> fetched = em.createQuery(cq)
    .setMaxResults(pageSize + 1)
    .getResultList();
~~~

Đoạn ví dụ giả định `after` là `OrderCursorKey` đã được xác thực, có hai trường NOT NULL. `Root`, `Path` và `Predicate` được tạo trên **cùng một CriteriaQuery**. Đừng lấy Predicate gắn với Root của query khác rồi tái sử dụng trực tiếp.

### 11.1. Khi Criteria hữu ích hơn HQL

Nếu trang tìm kiếm có nhiều filter tùy chọn:

- Tenant/security scope bắt buộc.
- Status.
- Customer.
- Khoảng thời gian.
- Khoảng số tiền.
- Category.
- Nhiều nhóm OR.
- Chính sách “chỉ xem đơn được phân quyền”.

Criteria/Specification có thể lắp predicate theo domain và thêm seek predicate một cách có cấu trúc. Tránh copy-paste chuỗi HQL biến thể.

### 11.2. Criteria không tự sửa logic keyset

Bạn vẫn phải viết dấu so sánh đúng với `ORDER BY`, xử lý ties, NULL, back navigation và filter fingerprint. Nếu predicate sai thì Criteria vẫn sinh SQL sai một cách hợp lệ.

### 11.3. Static metamodel

Khi dùng JPA static metamodel:

~~~java
Path<Instant> createdAt =
    root.get(PurchaseOrder_.createdAt);
Path<Long> id =
    root.get(PurchaseOrder_.id);
~~~

compiler có thể phát hiện nhiều lỗi refactor type/property tốt hơn so với `root.get("createdAt")`, với điều kiện annotation processor đã tạo metamodel đúng.

## 12. Native SQL: keyset với tuple comparison

Một native PostgreSQL query có thể viết:

~~~sql
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (created_at, id) < (:createdAt, :id)
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Đây là tuple/row-value comparison đối với các cột cùng hướng giảm. Nó ngắn hơn công thức OR, nhưng cần kiểm tra khả năng hỗ trợ và execution plan trên database mục tiêu.

### 12.1. Cú pháp LIMIT không portable cho mọi database

`LIMIT` phổ biến trong PostgreSQL/MySQL, nhưng SQL Server và Oracle có cách viết pagination riêng. Khi sử dụng Hibernate `setMaxResults()` trên HQL/Criteria hoặc native query, provider/dialect có thể hỗ trợ pagination theo khả năng; cần kiểm tra SQL cuối.

### 12.2. Bind sort key đúng kiểu

- Timestamp phải có cùng semantics/timezone/precision với cột.
- ID phải có kiểu tương thích.
- Enum status phải được bind theo cách cột lưu trữ.
- Không nội suy giá trị cursor trực tiếp vào SQL string.

Ví dụ sai:

~~~java
sql += " AND id < " + cursorFromClient;
~~~

Thay bằng bind parameters hoặc cursor đã xác thực, dù vẫn bind mọi giá trị.

## 13. Phân trang ngược: nút “Previous”

Đi tiếp tương đối dễ; đi ngược cần đảo điều kiện **và** đảo thứ tự truy vấn.

Giả sử thứ tự hiển thị chuẩn:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Muốn lấy những bản ghi **đứng trước** hàng đầu hiện tại (cursor `before`), điều kiện là:

~~~sql
WHERE created_at > :beforeCreatedAt
   OR (
       created_at = :beforeCreatedAt
       AND id > :beforeId
   )
~~~

Nhưng nếu vẫn sort DESC và LIMIT nhỏ, database có thể trả **các hàng xa cursor** thay vì những hàng ngay trước nó.

Cách đúng thường là:

1. Tìm những hàng đứng trước cursor.
2. Query chúng với **thứ tự ngược** để lấy những hàng gần cursor nhất.
3. `LIMIT pageSize + 1`.
4. Đảo lại danh sách visible rows trong memory để trả về thứ tự chuẩn DESC.

~~~sql
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
       created_at > :beforeCreatedAt
       OR (
           created_at = :beforeCreatedAt
           AND id > :beforeId
       )
  )
ORDER BY created_at ASC, id ASC
LIMIT :pageSizePlusOne;
~~~

Nếu nhận các hàng gần cursor nhất trong thứ tự ASC, đảo visible list để hiển thị DESC như trang bình thường.

### 13.1. Lấy cursor trước và sau từ đâu?

- **nextCursor:** khóa của hàng **cuối** trong trang visible, dùng predicate “đứng sau”.
- **previousCursor:** khóa của hàng **đầu** trong trang visible, dùng predicate “đứng trước”.

Token nên ghi rõ hướng hoặc API nên có tham số `after` và `before` tách biệt để tránh dùng nhầm.

### 13.2. Có nên gửi cả nextCursor và previousCursor?

Có thể, nếu UX cần nút Back/Forward. Nhưng phải định nghĩa semantics của hasPrevious chính xác và lấy sentinel theo hướng tương ứng.

Một API đơn giản có thể chỉ hỗ trợ “Load more”, vì việc giữ cursor lịch sử ở client đã đủ cho nút quay lại trang vừa xem mà không cần query ngược.

### 13.3. Không thể suy ra previous từ next bằng cách đổi dấu một cách máy móc

Ngoài dấu so sánh, còn cần đảo SQL ORDER BY và đảo lại kết quả trước khi trả. Với nhiều sort fields, các hướng phải được đảo đầy đủ, bao gồm NULL ordering.

## 14. Thay đổi dữ liệu giữa hai lần request

Keyset pagination thường **ít bị dịch vị trí hơn OFFSET**, nhưng không cung cấp một snapshot cố định qua mọi lần tải.

### 14.1. Insert mới trước cursor

Một đơn mới được tạo với `createdAt` lớn hơn cursor của trang hiện tại. Query `after` không kéo đơn mới đó vào các trang phía sau.

Đây là hành vi thường mong muốn của infinite scroll: dữ liệu mới xuất hiện ở đầu feed, người dùng có thể refresh đầu danh sách để thấy.

### 14.2. Insert mới phía sau cursor

Một bản ghi được backfill với `createdAt` cũ hơn cursor có thể xuất hiện ở trang tiếp theo, dù nó chưa tồn tại khi trang đầu được đọc.

Keyset không bảo đảm “tất cả hàng thuộc snapshot tại lần GET đầu”. Nó chỉ bảo đảm duyệt theo predicate từ khóa hiện tại.

### 14.3. Update khóa sắp xếp

Nếu `createdAt` hoặc một sort field có thể thay đổi, hàng đã thấy có thể chuyển tới phía sau cursor và **xuất hiện lại**; hàng chưa thấy có thể chuyển ra phía trước và **bị bỏ qua**.

Điều này không phải lỗi SQL. Nó là hệ quả việc tập dữ liệu và vị trí sắp xếp thay đổi giữa các request.

### 14.4. Delete

Nếu một hàng đã đọc bị xóa, cursor vẫn dùng khóa đã lưu. Keyset không cần hàng neo còn tồn tại trong DB để tiếp tục so sánh. Đây là một lợi thế so với cơ chế cursor lưu duy nhất ID rồi phải đọc lại anchor.

Nhưng nếu API chỉ lưu ID và phải query createdAt từ hàng đó, xóa anchor có thể làm việc tiếp nối thất bại. Vì vậy token nên mang **toàn bộ sort key cần thiết**.

### 14.5. Cần snapshot tuyệt đối thì sao?

Một vài lựa chọn, tùy hệ thống:

- Giới hạn dữ liệu theo mốc cố định, ví dụ `createdAt <= :capturedAt`, và đưa mốc vào cursor.
- Dùng một read model hoặc materialized snapshot có ID cố định.
- Sử dụng database snapshot/transaction phù hợp trong một phiên xử lý liên tục, nếu hạ tầng hỗ trợ và chi phí chấp nhận được.
- Với export/batch job, tạo danh sách IDs hoặc một snapshot table rồi duyệt dần.

**Mốc thời gian không phải snapshot đầy đủ**: nếu record cũ bị update/delete hoặc backfill với timestamp trước mốc, tập kết quả vẫn có thể thay đổi. Muốn semantics thật sự “đúng tập hàng tại thời điểm T”, cần một cơ chế snapshot/versioned data được thiết kế rõ.

### 14.6. @Version có giúp phân trang ổn định không?

`@Version` bảo vệ optimistic concurrency khi ghi một entity. Nó không tự đóng băng toàn bộ result set của một loạt SELECT trên nhiều HTTP requests. Đừng coi version field là giải pháp thay thế snapshot pagination.

## 15. Bộ lọc thay đổi giữa các trang

Giả sử trang đầu lọc:

~~~text
status=COMPLETED
createdAt DESC, id DESC
tenant=42
~~~

Client sau đó đổi status sang PAID nhưng vẫn gửi cursor của COMPLETED. Nếu server tiếp tục dùng timestamp/ID cũ, nó sẽ áp ranh giới khóa lên một tập hàng khác. Kết quả có thể hợp lệ về SQL nhưng sai logic “tiếp tục trang trước”.

Vì vậy cursor cần ràng buộc với:

- Tenant hoặc authorization scope.
- Bộ filter đã chuẩn hóa.
- Thứ tự sort và hướng sort.
- Nếu có, mốc snapshot/high-water mark.
- Version của định dạng cursor.

### 15.1. Fingerprint của filter

Một thiết kế:

~~~text
normalizedFilter =
    tenantId=42;status=COMPLETED;from=...;to=...;sort=createdAt:desc,id:desc

fingerprint = SHA-256(UTF-8(normalizedFilter))
~~~

Token ký HMAC chứa fingerprint đó. Khi request tiếp theo đến, server tính lại fingerprint từ filters đã xác thực và từ chối nếu khác.

**Canonicalization phải ổn định**: thứ tự field, ISO instant, timezone, normalization của chuỗi, giá trị mặc định và phiên bản sort cần đồng nhất. Nếu cùng một filter lúc thì dùng null, lúc thì dùng empty string, hai request có thể bị coi khác nhau không mong muốn.

### 15.2. Authorization scope có thể thay đổi độc lập

Ngay cả cursor đã ký hợp lệ, quyền user có thể bị thu hồi sau lần tải trước. Truy vấn mới vẫn phải kiểm tra quyền tại thời điểm hiện tại. Không dùng cursor như một “vé vượt quyền” dựa trên kết quả kiểm tra cũ.

## 16. Chỉ mục: điều kiện để keyset có lợi về hiệu năng

Với query:

~~~sql
WHERE tenant_id = ?
  AND status = ?
  AND (
       created_at < ?
       OR (created_at = ? AND id < ?)
  )
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

index ban đầu:

~~~sql
CREATE INDEX idx_orders_feed
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
~~~

Đây là ứng viên phù hợp vì:

- `tenant_id` và `status` là equality predicates.
- `created_at` và `id` là sort/seek keys.
- Thứ tự cột index tương thích với mẫu query phổ biến.

### 16.1. Quy tắc equality trước, sort/range sau

Một hướng thiết kế index thông dụng là đặt các equality filter có tính ổn định trước rồi đến sort keys. Nhưng không biến nó thành quy tắc tuyệt đối: cardinality, data distribution, query planner và nhiều sort/filter modes có thể làm index khác tốt hơn.

Nếu `status` là filter tùy chọn, index có `tenant_id, status, created_at, id` có thể không đáp ứng tốt truy vấn chỉ lọc tenant và sort createdAt. Có thể cần index khác hoặc điều chỉnh query patterns.

### 16.2. Index covering và cột INCLUDE

Trên database có `INCLUDE` như PostgreSQL, đôi khi có thể thêm các cột projection để hỗ trợ index-only scans:

~~~sql
CREATE INDEX idx_orders_feed_cover
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
)
INCLUDE (total_amount);
~~~

Không mặc định index-only scan luôn xảy ra; trên PostgreSQL còn phụ thuộc visibility map và điều kiện truy vấn. Index lớn hơn làm tăng chi phí ghi và storage. Chỉ thêm khi benchmark cho thấy lợi ích.

### 16.3. Một index không hỗ trợ mọi ORDER BY

Nếu API cho phép sort theo `totalAmount DESC`, cần đánh giá index cho mẫu đó. Dùng index `createdAt DESC, id DESC` không đảm bảo query sort theo amount có thể seek hiệu quả.

Thực tế nên giới hạn số sort modes hỗ trợ và thiết kế index theo workload quan trọng, không cho client chọn bất kỳ property nào trên entity.

### 16.4. Kiểm tra bằng EXPLAIN

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = 42
  AND status = 'COMPLETED'
  AND (
       created_at < TIMESTAMPTZ '2026-11-15 10:08:00+00'
       OR (
           created_at = TIMESTAMPTZ '2026-11-15 10:08:00+00'
           AND id < 103
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

Kiểm tra actual rows, index scan, rows removed by filter, buffers, sort và execution time. `EXPLAIN ANALYZE` thực thi SELECT, nên dùng dữ liệu/điều kiện an toàn; với DML, có thể có side effects.

### 16.5. OR predicate có thể ảnh hưởng optimizer

Dạng `created_at < x OR (created_at = x AND id < y)` đúng về semantics, nhưng SQL engine có thể tối ưu khác với tuple comparison. Trên DB hỗ trợ tuple comparison và index phù hợp, có thể benchmark hai dạng.

**Tối ưu cú pháp không được thay đổi thứ tự so sánh**, nhất là mixed directions và NULL semantics.

## 17. Phân trang qua JOIN: tránh làm mất tính duy nhất của root

Giả sử Order có nhiều OrderLine:

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
~~~

Nếu query:

~~~hql
select o
from PurchaseOrder o
join o.lines l
where l.quantity >= :minQuantity
order by o.createdAt desc, o.id desc
~~~

một Order có nhiều line khớp có thể xuất hiện nhiều lần ở SQL result set. Nếu áp `setMaxResults(pageSize + 1)` trước khi deduplicate root, số distinct Order của trang có thể thấp hơn mong muốn hoặc phân trang không đúng.

### 17.1. Dùng EXISTS cho điều kiện “có ít nhất một child”

~~~hql
select new com.example.orders.OrderRow(
    o.id, o.createdAt, o.totalAmount
)
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.status = :status
  and exists (
      select 1
      from OrderLine l
      where l.order = o
        and l.quantity >= :minQuantity
  )
  and (
      o.createdAt < :cursorCreatedAt
      or (
          o.createdAt = :cursorCreatedAt
          and o.id < :cursorId
      )
  )
order by o.createdAt desc, o.id desc
~~~

`EXISTS` là cách diễn đạt điều kiện tồn tại child mà không nhân root rows theo số child. Vẫn cần kiểm tra execution plan cho dữ liệu thực.

### 17.2. Không collection-fetch-join cùng keyset limit tùy tiện

Một truy vấn `join fetch o.lines` với pagination có thể khiến Hibernate áp limit trong memory để không cắt collection. Đây là vấn đề tương tự offset pagination với collection fetch join; keyset predicate không tự giải quyết.

Thường nên:

1. Query keyset trả **root IDs** của trang.
2. Query thứ hai fetch root và một collection cần thiết với `WHERE id IN :ids`.
3. Sắp kết quả cuối theo đúng thứ tự IDs đã chọn.
4. Nếu nhiều collection to-many, tách fetch queries hoặc dùng batch/subselect để tránh Cartesian product.

### 17.3. Hai bước fetch có thể thay đổi dữ liệu giữa bước

Nếu dùng nhiều query trong một transaction, các record có thể bị cập nhật giữa bước lấy IDs và bước fetch details tùy isolation. Với yêu cầu nhất quán mạnh, cần thiết kế transaction/snapshot thích hợp. Đây không phải vấn đề riêng keyset mà là một phần consistency của read model.

## 18. Ví dụ hai bước: page IDs rồi fetch entity

Bước 1 — keyset lấy IDs:

~~~java
List<Long> ids = em.createQuery("""
    select o.id
    from PurchaseOrder o
    where o.tenantId = :tenantId
      and o.status = :status
      and (
          o.createdAt < :afterCreatedAt
          or (
              o.createdAt = :afterCreatedAt
              and o.id < :afterId
          )
      )
    order by o.createdAt desc, o.id desc
    """, Long.class)
    .setParameter("tenantId", tenantId)
    .setParameter("status", status)
    .setParameter("afterCreatedAt", after.createdAt())
    .setParameter("afterId", after.id())
    .setMaxResults(pageSize + 1)
    .getResultList();
~~~

Đoạn này giả định `after != null`, tức đã qua trang đầu. Trang đầu bỏ predicate seek.

Bước 2 — chỉ fetch cho IDs visible:

~~~java
List<Long> visibleIds = ids.size() > pageSize
    ? ids.subList(0, pageSize)
    : ids;

if (visibleIds.isEmpty()) {
    return List.of();
}

List<PurchaseOrder> orders = em.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    where o.tenantId = :tenantId
      and o.id in :ids
    """, PurchaseOrder.class)
    .setParameter("tenantId", tenantId)
    .setParameter("ids", visibleIds)
    .getResultList();
~~~

`WHERE id IN :ids` không bảo đảm SQL trả về cùng thứ tự với `visibleIds`. Service cần sắp xếp lại theo thứ tự trang gốc, ví dụ dùng map `id → vị trí`.

### 18.1. Cursor phải lấy từ dữ liệu của bước 1

Nếu kết quả fetch entity thứ hai được trả theo thứ tự khác, không được lấy hàng cuối của danh sách chưa sắp lại làm cursor. Keyset cursor luôn gắn với **thứ tự của truy vấn trang root**.

Bước 1 ở ví dụ chỉ lấy ID; muốn tạo cursor `(createdAt,id)`, nên chọn cả `createdAt` ở bước 1 hoặc bảo đảm lấy đầy đủ sort key từ một nguồn nhất quán.

Một DTO nhỏ gồm ID và sort key thường là lựa chọn tốt hơn:

~~~java
public record OrderKey(Long id, Instant createdAt) {}
~~~

### 18.2. Vì sao không fetch mọi collection cùng lúc?

Nếu Order có 30 lines và 10 tags, một query join-fetch cả hai có thể tạo khoảng 300 tổ hợp hàng SQL cho mỗi Order. Hibernate còn có thể báo `MultipleBagFetchException` nếu hai collection đều có bag semantics.

Tải roots bằng keyset rồi fetch từng association phù hợp giúp kiểm soát kích thước result set và tránh mất lợi ích của giới hạn trang.

## 19. Count, totalPages và UI “Load more”

Keyset không cần tổng số bản ghi để tải trang kế tiếp.

Response có thể chỉ chứa:

~~~json
{
  "items": [],
  "hasNext": false,
  "nextCursor": null
}
~~~

Với infinite scroll, đó thường là hợp đồng đủ.

### 19.1. Nếu giao diện cần tổng số?

Có thể chạy query COUNT riêng:

~~~hql
select count(o)
from PurchaseOrder o
where o.tenantId = :tenantId
  and o.status = :status
~~~

Nhưng COUNT trên tập dữ liệu lớn hoặc filter phức tạp có thể đắt. Nó cũng phản ánh dữ liệu tại thời điểm query count, không nhất thiết chính xác với tất cả lần tải trang tiếp theo.

### 19.2. totalPages không tự phù hợp cursor pagination

Ngay cả khi biết `totalCount`, cursor pagination vẫn không cung cấp khả năng nhảy thẳng trang 500 chỉ từ số trang. Đừng trả một trường totalPages rồi hứa khả năng random navigation nếu API không hỗ trợ.

### 19.3. Nếu phải có “Trang 1, 2, 3 ...”?

Có thể:

- Dùng OFFSET cho các trang nông hoặc tập dữ liệu nhỏ.
- Dùng keyset cho “Load more” ở phần sâu.
- Cache một số checkpoint cursors để nhảy tới các mốc đã biết.
- Thiết kế phân trang theo một giá trị domain như ngày/tháng.

Mỗi cách có trade-off về consistency, storage, độ phức tạp và trải nghiệm.

## 20. Batch processing: keyset để quét dữ liệu lớn

Keyset không chỉ dành cho API. Nó hữu ích cho batch job:

~~~text
cursor = null

loop:
    rows = lấy 1000 rows sau cursor theo ID ASC
    nếu rows rỗng: dừng

    xử lý rows theo nghiệp vụ
    cursor = ID của hàng cuối
    lưu checkpoint an toàn
~~~

Với bảng có `id BIGINT` và duyệt tăng dần:

~~~sql
SELECT id
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND id > :lastId
ORDER BY id ASC
LIMIT 1000;
~~~

Ở đây có thể dùng **một khóa ID** vì chính ORDER BY chỉ có ID và ID là duy nhất trong scope.

### 20.1. Không đánh đồng cursor với checkpoint đã xử lý thành công

Đối với batch job có side effects, chỉ lưu checkpoint sau khi các bản ghi trong batch đã được xử lý bền vững theo contract. Nếu lưu cursor trước nhưng job chết khi đang xử lý, có thể bỏ mất việc xử lý các hàng còn lại.

Cần idempotency, transaction/outbox hoặc cơ chế retry theo nghiệp vụ.

### 20.2. “Exactly once” không tự đến từ keyset

Keyset giúp duyệt tập dữ liệu, không bảo đảm xử lý đúng một lần. Một batch có thể bị retry, consumer nhận trùng message hoặc crash giữa DB commit và external side effect.

Nên thiết kế operation idempotent và checkpoint/commit ordering thích hợp.

### 20.3. Hàng đổi điều kiện lọc

Nếu batch lọc `status = PENDING`, rồi tự cập nhật status thành PROCESSED, tập hàng thay đổi trong lúc scan. Với `id ASC` ổn định, điều này thường dễ kiểm soát hơn so với OFFSET. Tuy nhiên, nếu các worker khác cũng thay đổi điều kiện hoặc thêm ID thấp hơn checkpoint, có thể bỏ qua một số hàng; cần xác định semantics “sweep” và khả năng quét lại.

### 20.4. Workers song song

Nhiều worker dùng cùng predicate keyset mà không chia vùng/claim rows có thể xử lý trùng. Có thể phân vùng theo ID ranges, tenant, queue semantics, hoặc dùng locking/claim mechanism phù hợp. `SKIP LOCKED` là một chiến lược khác để chia việc, không phải chức năng tự có của keyset.

## 21. HQL, Criteria, native và framework scrolling API

Ba cách triển khai tương ứng:

| Cách | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| JPQL/HQL seek predicate | Sort cố định, query rõ ràng | Dễ kiểm tra; không cần extension riêng |
| JPA Criteria | Nhiều dynamic filters/sort được whitelist | Tái sử dụng predicate builder; vẫn cần logic keyset |
| Native SQL | Tối ưu tuple comparison, index/function DB-specific | Phụ thuộc schema và dialect; test trên DB thật |
| Hibernate-specific keyset/scroll API | Muốn dùng tiện ích provider có hỗ trợ trong version đang dùng | API, giới hạn và semantics phụ thuộc phiên bản |
| Spring Data scrolling/Window | Ứng dụng Spring Data có phiên bản hỗ trợ keyset scrolling | Cần sort ổn định, các thuộc tính keyset được trả/mapped đầy đủ |

### 21.1. Hibernate và Spring Data có API hỗ trợ ở một số version

Các phiên bản Hibernate/Spring Data hiện đại có các API hỗ trợ keyed results hoặc scrolling. Tuy nhiên, **đừng sao chép tên method từ phiên bản khác** vào ứng dụng mà chưa xác nhận dependency thực tế và tài liệu tương ứng.

Ngay cả khi framework tự sinh predicate, người dùng vẫn phải xác định:

- Sort duy nhất.
- Nullable key handling.
- Filter và authorization scope.
- Token/cursor semantics.
- Cách back navigation.
- Fetch plan và pagination collection.
- Chính sách khi dữ liệu thay đổi.

API hỗ trợ giảm boilerplate, không thay thiết kế dữ liệu.

### 21.2. Khi nào chọn implementation thủ công?

Nếu hệ thống có một hoặc vài sort modes cố định, HQL/Criteria thủ công thường minh bạch và dễ test. Khi có nhiều repository sử dụng cursor pagination, framework scrolling có thể giảm code lặp và rủi ro predicate sai, miễn là hiểu giới hạn phiên bản và loại query.

## 22. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `ORDER BY createdAt` không có tie-breaker | Hàng trùng timestamp bị bỏ sót hoặc lặp | Thêm ID duy nhất |
| Cursor chỉ chứa ID khi sort theo createdAt | Ranh giới không đúng thứ tự | Mang đủ sort keys |
| Dùng `<=` thay vì điều kiện strict | Lặp hàng cuối trang trước | Dùng so sánh lexicographic strict |
| Cả hai cột DESC nhưng dùng `>` ở trang sau | Đi sai hướng | Dùng `<` cho desc |
| Mixed ASC/DESC nhưng dùng tuple `<` máy móc | Trang sai | Viết OR-chain đúng từng hướng |
| Cursor lấy từ sentinel row thứ pageSize+1 | Bỏ mất sentinel | Lấy từ hàng cuối visible |
| Đổi filter giữa các trang vẫn nhận cursor cũ | Tiếp nối sai tập dữ liệu | Bind fingerprint filter/sort/scope |
| Base64 không ký token | Client sửa sort key/scope | Ký HMAC hoặc dùng server-side opaque token |
| Tin tenantId trong cursor thay authorization | Rò rỉ dữ liệu tenant khác | Scope bắt buộc từ server auth |
| Sort field nullable không xử lý NULL | Bỏ sót hoặc sai thứ tự | Sort key NOT NULL hoặc semantics NULL rõ |
| Update sort key khi đang duyệt | Hàng đổi vị trí, lặp/thiếu | Khóa sắp xếp ổn định hoặc snapshot |
| Không có index cho WHERE/ORDER BY | Keyset vẫn có thể quét nhiều | Thiết kế index và đo plan |
| Join to-many rồi LIMIT root | Duplicates/partial page | EXISTS hoặc page IDs trước |
| Fetch collection cùng pagination | In-memory pagination | Tách root pagination/fetch |
| Dùng COUNT bắt buộc cho mọi request | Thêm chi phí trên tập lớn | Dùng pageSize+1 nếu chỉ cần hasNext |
| Đòi nhảy tới trang N chỉ bằng cursor | Không có random access | Thiết kế UI/offset/checkpoint phù hợp |
| Batch checkpoint trước khi xử lý xong | Mất công việc khi crash | Lưu checkpoint sau xử lý bền vững |
| Không test concurrency | Bugs chỉ xuất hiện production | Test insert/delete/update giữa các request |

## 23. Checklist thiết kế keyset pagination

### Đúng về dữ liệu

- [ ] Chọn thứ tự sắp xếp có nghĩa nghiệp vụ.
- [ ] Thêm tie-breaker để đạt thứ tự toàn phần.
- [ ] Sort keys có giá trị NOT NULL hoặc NULL semantics được thiết kế đầy đủ.
- [ ] Cursor chứa mọi sort key cần cho predicate.
- [ ] Dấu so sánh khớp hướng ASC/DESC.
- [ ] Predicate strict, không lặp hàng neo.
- [ ] Cursor lấy từ hàng cuối visible, không phải sentinel.
- [ ] Đổi sort/filter thì bắt đầu lại hoặc từ chối cursor cũ.

### Đúng về bảo mật và API

- [ ] Tenant/authorization scope bắt buộc trong mọi query.
- [ ] Cursor token có kiểm tra tính toàn vẹn hoặc được lưu server-side.
- [ ] Có versioning và expiration policy phù hợp.
- [ ] Giới hạn độ dài cursor và pageSize.
- [ ] Không nội suy dữ liệu client vào SQL/HQL.
- [ ] Có error response rõ cho cursor sai/hết hạn.
- [ ] Nếu client cần previous page, direction semantics được định nghĩa rõ.

### Đúng về hiệu năng

- [ ] Có index cho equality filters + sort keys khi phù hợp.
- [ ] Đã xem SQL do Hibernate sinh ra.
- [ ] Đã chạy EXPLAIN trên DB mục tiêu.
- [ ] Không JOIN nhân rows trước LIMIT ngoài ý muốn.
- [ ] Không collection fetch join với pagination thiếu kiểm soát.
- [ ] DTO projection chỉ lấy các cột cần hiển thị.
- [ ] Có metrics latency, rows, statements trên dữ liệu đại diện.

### Đúng về vận hành

- [ ] Có contract cho insert/update/delete giữa các trang.
- [ ] Nếu cần snapshot, đã định nghĩa cơ chế snapshot thật.
- [ ] Batch jobs có checkpoint/idempotency đúng.
- [ ] Test first/middle/last/empty page.
- [ ] Test timestamp trùng nhau, filter mismatch và tenant mismatch.
- [ ] Test pageSize tối thiểu/tối đa và invalid cursors.

## 24. Bài tập thực hành

### Bài 1 — Tại sao OFFSET chậm?

Một bảng có 50 triệu Orders. Trang kích thước 25; UI muốn lấy `OFFSET 5_000_000`. Giải thích vì sao database có thể phải xử lý một lượng lớn hàng trước khi trả 25 hàng và vì sao keyset với index phù hợp có lợi.

### Bài 2 — Timestamp trùng nhau

Ba Order có cùng timestamp, ID lần lượt 105, 104, 103. Trang đầu trả 105 và 104. Nếu cursor chỉ có timestamp và query sau dùng `createdAt < :cursorTime`, hàng nào bị mất? Hãy viết cursor và điều kiện đúng.

### Bài 3 — Hướng tăng dần

Truy vấn sắp:

~~~sql
ORDER BY created_at ASC, id ASC
~~~

Cursor ở `(10:08, 104)`. Viết điều kiện `WHERE` để lấy những hàng sau cursor.

### Bài 4 — Mixed directions

Truy vấn:

~~~sql
ORDER BY total_amount DESC, created_at ASC, id ASC
~~~

Viết điều kiện lexicographic cho hàng sau cursor. Vì sao không thể dùng `(total_amount, created_at, id) < (...)` một cách máy móc?

### Bài 5 — pageSize + 1

Trang kích thước 3, SQL trả [105, 104, 103, 102]. Client phải nhận bao nhiêu item? `nextCursor` lấy ID nào? Điều gì sai nếu dùng 102?

### Bài 6 — HQL và Criteria

Viết một HQL và một Criteria query để lấy các đơn sau cursor `(createdAt, id)` theo thứ tự DESC. Nêu điểm giống nhau ở SQL cuối và khác nhau ở cách cấu thành predicate.

### Bài 7 — Previous page

Thứ tự chuẩn DESC. Từ hàng đầu trang hiện tại, hãy viết predicate lấy các hàng đứng trước và thứ tự SQL để lấy các hàng gần cursor nhất. Có cần đảo kết quả trước khi trả client không?

### Bài 8 — Cursor bảo mật

Một API đặt cursor bằng Base64URL(JSON). Client sửa tenantId trong JSON và gửi lại. Có thể có rủi ro gì? Nêu cách dùng HMAC, scope server-side và expiration.

### Bài 9 — Đổi bộ lọc

Client lấy trang đầu status=COMPLETED rồi gửi cursor đó cùng status=PAID. Server nên làm gì? Filter fingerprint có vai trò gì?

### Bài 10 — Dữ liệu đang thay đổi

Client đọc trang 1, sau đó một đơn mới có timestamp lớn hơn cursor được tạo. Khi đọc trang 2, keyset có trả đơn mới không? Nếu một đơn cũ đổi createdAt thì có thể xảy ra gì?

### Bài 11 — Index

Với query tenant/status equality, createdAt DESC và id DESC, hãy đề xuất composite index. Giải thích vì sao vẫn phải đo EXPLAIN khi filter/sort thay đổi.

### Bài 12 — JOIN to-many

Một Order có 10 lines. Nếu query JOIN lines rồi setMaxResults(5), có thể xảy ra vấn đề gì về số distinct Orders? Hãy đề xuất EXISTS hoặc hai bước query.

### Bài 13 — COUNT

Một feed chỉ cần nút Load More. Vì sao `LIMIT pageSize+1` thường đủ thay vì chạy COUNT? Nếu sản phẩm đòi totalPages thì cần thay đổi API/UX thế nào?

### Bài 14 — Export hàng triệu rows

Một job xuất Orders theo ID ASC, mỗi batch 1000. Hãy viết điều kiện seek và giải thích checkpoint, retry, idempotency. Nếu job đổi status của các rows khi xử lý thì OFFSET và keyset khác nhau ra sao?

### Bài 15 — Test integration

Thiết kế test có hai Order trùng timestamp, một insert trước cursor, một update sort key, một token sai chữ ký và một token từ tenant khác. Với mỗi case, xác định kết quả hoặc lỗi mong đợi.

### Gợi ý đáp án

- **Bài 1:** OFFSET sâu phải đi qua rất nhiều rows; keyset seek theo indexed keys thường đọc phần nhỏ hơn.
- **Bài 2:** ID 103 bị bỏ qua; cursor phải là (timestamp,104), với `createdAt < t OR (createdAt=t AND id<104)`.
- **Bài 3:** `createdAt > t OR (createdAt=t AND id>104)`.
- **Bài 4:** Amount nhỏ hơn, hoặc amount bằng và createdAt lớn hơn, hoặc cả hai bằng và ID lớn hơn.
- **Bài 5:** Hiển thị 105/104/103, cursor ID 103; 102 là sentinel và phải xuất hiện trang sau.
- **Bài 6:** Cả hai biểu diễn cùng lexicographic predicate; Criteria dùng cây Predicate, HQL dùng chuỗi truy vấn.
- **Bài 7:** Predicate `>` với DESC, query ASC để lấy gần cursor, sau đó reverse visible rows.
- **Bài 8:** Base64 không chống sửa; ký HMAC và bắt buộc tenant từ principal, validate filter/scope/time.
- **Bài 9:** Từ chối hoặc reset cursor; không dùng ranh giới của tập filter khác.
- **Bài 10:** Bản ghi mới đứng trước cursor thường không xuất hiện ở trang sau; đổi sort key có thể gây trùng/thiếu.
- **Bài 11:** Index `(tenant_id, status, created_at DESC, id DESC)`, đo theo workload thật.
- **Bài 12:** JOIN nhân rows có thể làm giới hạn SQL cắt số root; EXISTS hoặc page root IDs rồi fetch.
- **Bài 13:** Sentinel cho biết còn trang; totalPages cần count/chiến lược random access và contract phù hợp.
- **Bài 14:** `id > :lastId ORDER BY id ASC LIMIT 1000`; checkpoint sau xử lý bền vững; retry phải idempotent.
- **Bài 15:** Kiểm tra tính đúng của thứ tự, không skip các ties, semantics khi mutation và từ chối token giả/sai tenant.

---

## Tóm tắt

**Keyset pagination phân trang theo giá trị khóa sắp xếp thay vì vị trí OFFSET**, nên đặc biệt hữu ích khi phải đi sâu vào tập dữ liệu lớn hoặc tải tiếp theo kiểu infinite scroll. Thuật toán dựa trên ba điều kiện:

1. **Thứ tự toàn phần**, thường bằng sort field cộng ID duy nhất.
2. **Predicate seek khớp thứ tự ASC/DESC** và chứa mọi khóa trong cursor.
3. **Index phù hợp** cùng giới hạn trang, chẳng hạn `pageSize + 1` để biết còn trang sau.

Triển khai có thể dùng HQL, Criteria hoặc SQL native; lựa chọn ngôn ngữ không làm thay đổi các điều kiện đúng đắn. Cursor cần được bảo vệ, ràng buộc với tenant/filter/sort và không nên lộ quyền truy cập. Keyset giảm nhiều vấn đề dịch vị trí do insert/delete nhưng **không tự cung cấp snapshot bất biến**, không xóa chi phí của JOIN lớn và không hỗ trợ nhảy ngẫu nhiên tới trang N như OFFSET.

Khi thiết kế đúng khóa, cursor, fetch plan, index và cách xử lý dữ liệu đồng thời, keyset pagination là một trong những kỹ thuật quan trọng nhất để đọc tập dữ liệu quan hệ lớn bằng Hibernate một cách hiệu quả và có thể kiểm chứng.
