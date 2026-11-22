# Thiết kế thứ tự sắp xếp và chỉ mục cho keyset

## Mục tiêu

Keyset scrolling (cuộn theo khóa) là cách lấy dữ liệu theo từng cửa sổ bằng cách tiếp tục từ các giá trị sắp xếp của bản ghi cuối cùng đã đọc. Thay vì yêu cầu database bỏ qua hàng nghìn hoặc hàng triệu hàng bằng OFFSET, truy vấn tiếp theo dùng một điều kiện WHERE dựa trên khóa sắp xếp để đi tiếp từ vị trí đã biết.

Keyset chỉ hiệu quả khi thứ tự sắp xếp được thiết kế ổn định và database có index phù hợp. Trong Spring Data JPA, Scroll API biểu diễn mỗi nhóm kết quả bằng `Window<T>`, còn `ScrollPosition.keyset()` bắt đầu một lượt cuộn theo khóa.

Sau bài này, bạn có thể:

- Phân biệt offset scrolling và keyset scrolling.
- Thiết kế thứ tự sắp xếp xác định cho dữ liệu có giá trị trùng nhau.
- Hiểu điều kiện keyset dạng từ điển (lexicographic predicate).
- Dùng `Window<T>`, `ScrollPosition` và `WindowIterator`.
- Chọn các trường không null và có thứ tự ổn định.
- Thiết kế composite index khớp với điều kiện lọc và ORDER BY.
- Hiểu tác động của cập nhật đồng thời, projection và giới hạn của query method.
- Đo kiểm bằng execution plan và kiểm thử trên database thực tế.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA. Scroll API có từ Spring Data 3.1; hãy xác nhận version Spring Data do dự án đang dùng quản lý.

## 1. Vì sao OFFSET trở nên tốn kém?

Phân trang truyền thống thường dùng `Pageable` hoặc `LIMIT/OFFSET`. Ví dụ:

```sql
SELECT id, order_number, created_at, total
FROM orders
WHERE status = 'PAID'
ORDER BY created_at ASC, id ASC
LIMIT 100 OFFSET 500000;
```

Ứng dụng chỉ nhận 100 hàng, nhưng database có thể phải tìm, sắp xếp và đi qua một lượng lớn kết quả trước khi trả về phần bắt đầu ở offset 500.000. Chi phí thường tăng khi offset lớn, tùy index, query plan và database.

OFFSET cũng nhạy với thay đổi dữ liệu giữa các lần đọc. Nếu có bản ghi mới được chèn trước vị trí offset, trang tiếp theo có thể lặp hoặc bỏ qua bản ghi so với lần đọc trước. Xóa hoặc cập nhật bản ghi cũng có thể làm vị trí các hàng dịch chuyển.

OFFSET vẫn hữu ích khi cần nhảy tới một trang bất kỳ, tập dữ liệu nhỏ hoặc người dùng cần số trang/tổng số bản ghi. Với xử lý tuần tự dữ liệu lớn, keyset thường phù hợp hơn.

## 2. Keyset scrolling hoạt động như thế nào?

Keyset ghi nhớ các giá trị sắp xếp của hàng cuối cùng trong cửa sổ hiện tại. Query tiếp theo dùng các giá trị đó để tìm những hàng đứng sau nó theo cùng thứ tự.

Giả sử thứ tự là:

```sql
ORDER BY created_at ASC, id ASC
```

Sau khi đã đọc hàng cuối có:

- `created_at = 2026-01-10T09:30:00Z`
- `id = 420`

điều kiện tiếp theo về mặt logic là:

```sql
WHERE created_at > :lastCreatedAt
   OR (
       created_at = :lastCreatedAt
       AND id > :lastId
   )
ORDER BY created_at ASC, id ASC
LIMIT 100;
```

Điều kiện này có nghĩa:

1. Lấy các hàng có created_at lớn hơn thời điểm cuối.
2. Nếu created_at bằng nhau, lấy hàng có id lớn hơn ID cuối.
3. Sắp xếp theo đúng thứ tự đã định nghĩa và lấy cửa sổ kế tiếp.

Đây là so sánh từ điển trên nhiều khóa. Với ba trường sắp xếp tăng dần, dạng tổng quát là:

```text
k1 > v1
OR (k1 = v1 AND k2 > v2)
OR (k1 = v1 AND k2 = v2 AND k3 > v3)
```

Với chiều giảm dần, phép so sánh tương ứng đổi thành nhỏ hơn. Nếu trộn ASC và DESC, từng phép so sánh phải theo đúng chiều của trường đó. Spring Data tạo điều kiện tiếp tục từ keyset; không cần tự ghép chuỗi WHERE trong trường hợp Scroll API được hỗ trợ.

## 3. Thứ tự sắp xếp phải xác định và ổn định

Một thứ tự sắp xếp tốt cần xác định duy nhất vị trí của từng hàng. Chỉ sắp xếp theo `createdAt` thường chưa đủ vì nhiều đơn hàng có thể được tạo trong cùng một thời điểm.

Ví dụ không đủ xác định:

```sql
ORDER BY created_at ASC
```

Nếu hàng cuối cửa sổ có cùng created_at với nhiều hàng khác, database không bảo đảm thứ tự tương đối giữa các hàng có giá trị sort bằng nhau. Cursor không có đủ thông tin để phân biệt vị trí chính xác.

Thêm khóa duy nhất làm tiêu chí cuối:

```sql
ORDER BY created_at ASC, id ASC
```

`id` phân biệt các hàng có cùng created_at. Spring Data Keyset scrolling tự bổ sung primary key (hoặc các phần còn thiếu của composite primary key) vào thứ tự để bảo đảm keyset xác định. Khai báo ID tường minh trong method/query vẫn hữu ích vì nó làm rõ thứ tự nghiệp vụ và giúp thiết kế index dễ kiểm tra.

### 3.1. Chọn sort key

Các sort key thường phù hợp:

- Thời điểm tạo bất biến như `createdAt`.
- Mã tuần tự hoặc ID.
- Một giá trị nghiệp vụ không null, ít thay đổi.
- Nhiều trường kết hợp, có khóa duy nhất làm tie-breaker.

Hạn chế dùng trường thường xuyên bị sửa như `displayName`, `priority` hoặc `status` làm cursor chính nếu các hàng có thể đổi vị trí trong lúc cuộn. Khi sort key thay đổi, một hàng có thể di chuyển từ trước cursor ra sau cursor hoặc ngược lại, gây lặp hoặc bỏ qua trong một lượt xử lý nhiều query.

Nếu cần sắp xếp theo nhiều tiêu chí, xác định rõ thứ tự ưu tiên và chiều của từng trường. Đảm bảo tổ hợp cuối cùng là duy nhất; Spring Data tự bổ sung primary key khi cần.

### 3.2. Sort key phải không null

Keyset filtering yêu cầu các thuộc tính dùng để sắp xếp không nullable. So sánh với NULL có semantics riêng của SQL và khác nhau theo database; phép so sánh `>`, `<` hoặc `=` không đủ để tạo cursor đáng tin cậy cho giá trị null.

Ví dụ không phù hợp:

```sql
ORDER BY shipped_at ASC, id ASC
```

nếu `shipped_at` cho phép null.

Ưu tiên một trường không null:

```java
@Column(name = "created_at", nullable = false)
private Instant createdAt;
```

Đồng thời phải bảo đảm database thực sự có constraint `NOT NULL`. Thuộc tính `nullable = false` hỗ trợ mapping/schema generation; nếu schema được quản lý bằng Flyway hoặc Liquibase, migration cũng phải đặt constraint tương ứng.

Nếu nghiệp vụ cho phép ngày giao hàng chưa xác định, không dùng trường nullable đó làm keyset sort key. Có thể dùng createdAt và id, hoặc thiết kế một cột sort key không null khác. Không dựa vào nulls-first/nulls-last để khắc phục giới hạn keyset.

## 4. Ví dụ entity và composite index

Giả sử cần cuộn các đơn hàng đã thanh toán theo thời điểm tạo.

```java
@Entity
@Table(
    name = "orders",
    indexes = {
        @Index(
            name = "idx_orders_status_created_id",
            columnList = "status, created_at, id"
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal total;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Index khai báo trong `@Table(indexes = ...)` có thể được provider dùng khi tạo schema. Trong production, nếu schema được quản lý bằng migration, hãy tạo index trong Flyway/Liquibase để kiểm soát tên, thứ tự cột và cách triển khai.

Ví dụ migration SQL:

```sql
CREATE INDEX idx_orders_status_created_id
    ON orders (status, created_at, id);
```

Index gồm:

1. `status`: điều kiện lọc bằng.
2. `created_at`: khóa sắp xếp chính.
3. `id`: tie-breaker duy nhất.

Cấu trúc này phù hợp với query có điều kiện `status = ?` và thứ tự `created_at, id`. Đây là mẫu thiết kế phổ biến, không phải công thức áp dụng máy móc cho mọi database hoặc mọi phân bố dữ liệu.

## 5. Quy tắc thiết kế composite index

Một keyset query thường kết hợp điều kiện lọc và điều kiện tiếp tục từ cursor:

```sql
WHERE tenant_id = ?
  AND status = ?
  AND (
      created_at > ?
      OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
LIMIT 100;
```

Một điểm bắt đầu hợp lý cho index là:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (tenant_id, status, created_at, id);
```

### 5.1. Đưa các điều kiện equality vào phần đầu

Với truy vấn có các điều kiện equality ổn định như tenant_id và status, thường đặt chúng trước các cột sắp xếp:

```text
(tenant_id, status, created_at, id)
  equality   equality   order      tie-breaker
```

Khi hai cột đầu được cố định bằng equality, database có thể đi vào vùng index tương ứng rồi đọc theo created_at/id.

Nếu truy vấn không lọc tenant_id hoặc status, index có thể không tận dụng được hiệu quả như kỳ vọng do quy tắc leftmost-prefix của B-tree. Nếu nhiều query pattern khác nhau cần được tối ưu, có thể cần index khác cho từng pattern.

### 5.2. Thứ tự cột rất quan trọng

Các index sau không tương đương:

```sql
CREATE INDEX idx_a ON orders (status, created_at, id);
CREATE INDEX idx_b ON orders (created_at, id, status);
```

Index A ưu tiên truy vấn lọc status rồi đọc theo created_at/id. Index B ưu tiên thứ tự created_at/id và có thể kém phù hợp khi status là điều kiện lọc chính.

Không có một index tổng quát tối ưu cho mọi truy vấn. Hãy bắt đầu từ WHERE, JOIN và ORDER BY thực tế, sau đó xem execution plan.

### 5.3. ASC, DESC và hướng của index

Ví dụ:

```sql
ORDER BY created_at DESC, id DESC
```

Một số database có thể quét B-tree theo chiều ngược để phục vụ thứ tự đảo ngược đồng nhất. Với thứ tự trộn chiều như:

```sql
ORDER BY created_at DESC, id ASC
```

database có thể cần index khai báo hướng cột tương ứng hoặc có thể chọn plan khác. Cú pháp và khả năng tối ưu khác nhau theo database. Đừng giả định mọi index ASC đều phục vụ tốt mọi tổ hợp ASC/DESC; hãy kiểm tra bằng EXPLAIN.

### 5.4. Index covering và INCLUDE

Một số database hỗ trợ cột INCLUDE hoặc covering index. Nếu projection chỉ đọc thêm order_number và total, có thể cân nhắc đưa các cột này vào phần payload của index thay vì khóa sắp xếp.

Ví dụ với database hỗ trợ cú pháp INCLUDE:

```sql
CREATE INDEX idx_orders_status_created_id
    ON orders (status, created_at, id)
    INCLUDE (order_number, total);
```

INCLUDE không phải cú pháp SQL portable và không có ý nghĩa giống nhau trên mọi database. Index rộng hơn làm tăng dung lượng, chi phí INSERT/UPDATE và bảo trì. Chỉ thêm cột khi execution plan và số liệu cho thấy index covering có lợi.

## 6. Spring Data JPA Scroll API

Spring Data cung cấp Scroll API để lấy kết quả thành từng cửa sổ. Các kiểu quan trọng:

- `Window<T>`: một nhóm kết quả cùng thông tin để tiếp tục cuộn.
- `ScrollPosition`: vị trí bắt đầu hoặc tiếp tục.
- `ScrollPosition.keyset()`: vị trí đầu tiên của keyset scrolling.
- `WindowIterator<T>`: tiện ích duyệt qua nhiều Window mà không phải tự quản lý vòng lặp cursor.

Ví dụ repository dùng derived query:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Window<PurchaseOrder>
    findFirst100ByStatusOrderByCreatedAtAscIdAsc(
            OrderStatus status,
            ScrollPosition position
    );
}
```

Method name định nghĩa:

- `First100`: giới hạn mỗi Window tối đa 100 đơn hàng.
- `ByStatus`: lọc theo trạng thái.
- `OrderByCreatedAtAscIdAsc`: sắp xếp tăng dần theo thời điểm tạo và ID.
- `ScrollPosition`: nhận vị trí tiếp tục cuộn.

### 6.1. Duyệt bằng WindowIterator

```java
WindowIterator<PurchaseOrder> orders = WindowIterator.of(
        position -> repository
                .findFirst100ByStatusOrderByCreatedAtAscIdAsc(
                        OrderStatus.PAID,
                        position
                )
).startingAt(ScrollPosition.keyset());

while (orders.hasNext()) {
    PurchaseOrder order = orders.next();
    process(order);
}
```

`WindowIterator` lấy Window tiếp theo khi cần và quản lý ScrollPosition. Cách này phù hợp khi xử lý tuần tự từng entity và không cần giữ toàn bộ kết quả trong một List.

Nếu cần xử lý theo nhóm, có thể gọi repository trực tiếp và dùng Window API:

```java
Window<PurchaseOrder> window =
        repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
                OrderStatus.PAID,
                ScrollPosition.keyset()
        );

while (!window.isEmpty()) {
    window.forEach(this::process);

    if (window.isLast()) {
        break;
    }

    ScrollPosition nextPosition =
            window.positionAt(window.size() - 1);

    window = repository
            .findFirst100ByStatusOrderByCreatedAtAscIdAsc(
                    OrderStatus.PAID,
                    nextPosition
            );
}
```

Vị trí lấy từ phần tử cuối là exclusive: query kế tiếp bắt đầu sau phần tử đó, tránh đọc lại chính hàng cuối của Window trước.

### 6.2. ScrollPosition.keyset() là vị trí ban đầu

```java
ScrollPosition position = ScrollPosition.keyset();
```

Đây là vị trí bắt đầu cuộn, chưa áp dụng điều kiện tiếp tục từ một hàng cụ thể. Sau khi nhận Window, lấy position từ hàng cuối bằng `window.positionAt(window.size() - 1)`.

Không dùng `ScrollPosition.offset(0)` thay cho vị trí bắt đầu keyset. Offset và keyset là hai kiểu cuộn khác nhau.

## 7. Keyset query và điều kiện SQL

Với thứ tự `created_at ASC, id ASC`, Spring Data xây dựng điều kiện tiếp tục từ các giá trị sort của hàng cuối. Về mặt logic, query có dạng:

```sql
SELECT id, status, created_at, order_number, total
FROM orders
WHERE status = ?
  AND (
      created_at > ?
      OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
FETCH FIRST 100 ROWS ONLY;
```

Cú pháp giới hạn kết quả phụ thuộc database; SQL thực tế có thể dùng LIMIT, FETCH FIRST hoặc cú pháp tương ứng. Query được provider tạo ra có thể khác về dấu ngoặc và cấu trúc predicate nhưng phải thể hiện cùng semantics.

Điểm quan trọng là database có thể tìm tiếp từ giá trị keyset trong index thay vì bỏ qua một offset rất lớn. Hiệu quả phụ thuộc index phù hợp, query plan, cardinality và dữ liệu.

## 8. Projection phải chứa các sort key

Keyset scrolling cần đọc các giá trị sort để tạo ScrollPosition cho Window tiếp theo. Vì vậy, kết quả projection phải expose tất cả thuộc tính được dùng trong sort order và các trường khóa cần thiết.

Ví dụ interface projection:

```java
public interface OrderScrollView {
    Long getId();
    Instant getCreatedAt();
    String getOrderNumber();
    BigDecimal getTotal();
}
```

Repository:

```java
Window<OrderScrollView>
findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus status,
        ScrollPosition position
);
```

Projection có `createdAt` và `id`, là các trường cần để trích xuất keyset. Nếu projection chỉ trả `orderNumber` và `total`, Spring Data có thể không lấy được các giá trị sort và keyset extraction sẽ thất bại.

Nếu dùng DTO projection, cũng phải đưa sort fields vào constructor/result. Việc các trường này có xuất hiện trong API response hay không là quyết định riêng; có thể giữ chúng trong DTO nội bộ cho quá trình cuộn rồi map sang response khác.

## 9. Giới hạn của query method

Scroll API hỗ trợ derived query methods, Query by Example và Querydsl. Theo tài liệu Spring Data JPA hiện tại, scrolling với string-based query methods như phương thức khai báo bằng `@Query` chưa được hỗ trợ.

Vì vậy, ví dụ keyset ở trên dùng derived query:

```java
Window<PurchaseOrder>
findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus status,
        ScrollPosition position
);
```

Nếu query quá phức tạp để biểu diễn bằng derived method, các lựa chọn gồm:

- Query by Example hoặc Querydsl nếu phù hợp.
- Custom repository implementation dùng Criteria API/EntityManager.
- JDBC hoặc công cụ truy vấn khác nếu cần kiểm soát SQL chi tiết.

Khả năng hỗ trợ scrolling thay đổi theo version Spring Data. Kiểm tra tài liệu đúng version của dự án trước khi chọn API; không giả định một method `@Query` có thể nhận ScrollPosition và tự trở thành keyset query.

## 10. Keyset và thay đổi dữ liệu đồng thời

Keyset giảm ảnh hưởng của việc chèn/xóa hàng trước cursor so với OFFSET, vì query tiếp theo tìm từ giá trị sort cuối cùng. Tuy nhiên, keyset không tự tạo một snapshot nhất quán xuyên suốt nhiều Window.

Ví dụ:

1. Window đầu đọc đến `createdAt = 10:00, id = 500`.
2. Một đơn hàng cũ hơn được cập nhật createdAt thành 10:30.
3. Query tiếp theo tiếp tục sau cursor 10:00/500.
4. Đơn hàng vừa đổi thời gian có thể xuất hiện trong Window sau dù trước đó nó đã nằm trước cursor.

Tương tự, hàng có sort key thay đổi từ phía sau cursor về phía trước có thể không được đọc trong lượt hiện tại.

Để giảm vấn đề:

- Ưu tiên sort key bất biến như createdAt nếu nghiệp vụ cho phép.
- Thêm primary key làm tie-breaker.
- Xác định rõ có chấp nhận dữ liệu thay đổi trong lúc xử lý hay không.
- Nếu cần snapshot nhất quán, thiết kế transaction/isolation hoặc cơ chế snapshot/export riêng.
- Với batch job dài, cân nhắc chia transaction theo batch và ghi nhận tiến độ bền vững.

Giữ một transaction rất dài có thể làm tăng thời gian giữ snapshot, lock hoặc tài nguyên database. Hãy chọn ranh giới transaction theo yêu cầu nhất quán và khả năng khôi phục của job.

## 11. Keyset scrolling so với offset và Page

| Tiêu chí | Page/Offset | Keyset/Window |
|---|---|---|
| Tiếp tục từ vị trí | Số offset | Giá trị sort của hàng cuối |
| Trang sâu | Có thể tốn chi phí bỏ qua nhiều hàng | Thường hiệu quả hơn khi index phù hợp |
| Nhảy tới trang bất kỳ | Hỗ trợ tự nhiên | Không phải mục tiêu chính |
| Tổng số bản ghi | Page có thể chạy count query | Window không cung cấp tổng count |
| Thứ tự | Cần sort ổn định | Cần sort ổn định và keyset fields không null |
| Projection | Tùy query | Phải chứa sort keys |
| Dữ liệu thay đổi giữa các lần đọc | Offset dễ bị dịch vị trí | Ít bị dịch do hàng trước cursor được chèn/xóa, nhưng sort-key update vẫn có thể ảnh hưởng |
| Index | Hữu ích cho lọc/sắp xếp | Index khớp filter + sort đặc biệt quan trọng |

Chọn Page khi giao diện cần số trang/tổng số kết quả và người dùng cần điều hướng trực tiếp. Chọn keyset Window cho export, batch processing, feed hoặc tác vụ đọc tuần tự dữ liệu lớn.

## 12. Kiểm tra index bằng execution plan

Không thể kết luận index phù hợp chỉ từ tên cột. Hãy chạy EXPLAIN/EXPLAIN ANALYZE trên database gần production với dữ liệu có phân bố tương tự.

Ví dụ PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, created_at, total
FROM orders
WHERE status = 'PAID'
  AND (
      created_at > TIMESTAMP '2026-01-10 09:30:00'
      OR (
          created_at = TIMESTAMP '2026-01-10 09:30:00'
          AND id > 420
      )
  )
ORDER BY created_at ASC, id ASC
LIMIT 100;
```

Khi đọc plan, chú ý:

- Có dùng index scan hoặc index-only scan phù hợp không?
- Database có phải sort một lượng lớn hàng hay không?
- Bao nhiêu hàng được đọc để trả về 100 hàng?
- Filter nào được áp dụng tại index scan và filter nào còn lại?
- Buffer read và thời gian có ổn định khi cursor ở các vị trí khác nhau không?
- Index có được dùng khi tenant/status thay đổi không?

`EXPLAIN ANALYZE` thực thi query. Chạy trên môi trường kiểm thử hoặc dữ liệu phù hợp; tránh chạy query nặng tùy tiện trên production.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Keyset trả thiếu hoặc lặp hàng | Sort không xác định duy nhất hoặc sort key thay đổi | Dùng thứ tự ổn định và khóa duy nhất |
| Keyset cho kết quả bất thường với null | Sort property cho phép null | Dùng các sort key NOT NULL |
| Lỗi trích xuất keyset từ projection | Projection thiếu sort property | Expose tất cả sort fields và ID cần thiết |
| Query sâu vẫn chậm | Index không khớp filter/ORDER BY | Thiết kế composite index và xem EXPLAIN |
| Index không được chọn | Sai thứ tự cột hoặc query không khớp leftmost prefix | Đối chiếu WHERE, ORDER BY và phân bố dữ liệu |
| Sort theo nhiều hàng có cùng timestamp không ổn định | Chỉ sort theo createdAt | Thêm ID làm tie-breaker |
| Query method @Query không scroll được | String-based query scrolling chưa được hỗ trợ trong version đang dùng | Dùng derived query, QBE, Querydsl hoặc custom implementation |
| Window tiếp theo lặp hàng cuối | Dùng vị trí không đúng hoặc tự áp dụng inclusive cursor | Dùng positionAt phần tử cuối; ScrollPosition là exclusive |
| Hàng xuất hiện/mất khi job đang chạy | Sort key bị cập nhật giữa các Window | Ưu tiên sort key bất biến hoặc dùng snapshot phù hợp |
| Index làm ghi dữ liệu chậm | Quá nhiều hoặc index quá rộng | Đo write cost và chỉ giữ index có ích |

## 14. Checklist thiết kế keyset và index

- [ ] Chọn use case cần đọc tuần tự; xác định có thật sự cần tổng số bản ghi hay nhảy trang không.
- [ ] Định nghĩa thứ tự sắp xếp rõ ràng và ổn định.
- [ ] Có khóa duy nhất để phân biệt các hàng cùng sort key; Spring Data bổ sung primary key khi cần.
- [ ] Tất cả thuộc tính sort dùng cho keyset đều không null.
- [ ] Ưu tiên sort key ít thay đổi trong thời gian cuộn.
- [ ] Projection trả về toàn bộ sort fields và khóa cần thiết.
- [ ] Dùng `Window<T>` và `ScrollPosition.keyset()` hoặc `WindowIterator`.
- [ ] Kiểm tra version: string-based `@Query` scrolling có thể chưa được hỗ trợ.
- [ ] Thiết kế composite index theo filter equality và thứ tự sort.
- [ ] Xem xét ASC/DESC, leftmost prefix, cardinality và chi phí ghi index.
- [ ] Dùng EXPLAIN/EXPLAIN ANALYZE để xác nhận query plan.
- [ ] Kiểm thử khi có bản ghi trùng sort key, dữ liệu null và cập nhật đồng thời.
- [ ] Xác định transaction/snapshot và cách resume batch job khi lỗi.

## 15. Tài liệu tham khảo

- [Spring Data JPA Reference — Scrolling and Keyset Filtering](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.scrolling)
- [Spring Data Commons — ScrollPosition API](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/domain/ScrollPosition.html)
- [Spring Data JPA Reference — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)

## Kết luận

Keyset scrolling tiếp tục truy vấn từ các giá trị sắp xếp của hàng cuối cùng đã đọc, giúp tránh chi phí OFFSET lớn khi xử lý dữ liệu tuần tự. Để keyset hoạt động chính xác, cần một thứ tự ổn định, các sort key không null và projection chứa đủ trường để tạo cursor. Spring Data bổ sung primary key vào keyset khi cần để phân biệt các hàng có cùng giá trị sắp xếp.

Composite index nên phản ánh các điều kiện equality trong WHERE trước các cột ORDER BY, nhưng thứ tự cuối cùng phải được xác nhận bằng execution plan trên database thực tế. Ưu tiên sort key bất biến, thêm tie-breaker, kiểm tra cập nhật đồng thời và chọn transaction phù hợp. Khi các yếu tố này được thiết kế cùng nhau, keyset scrolling có thể xử lý tập dữ liệu lớn với chi phí truy vấn ổn định hơn.
