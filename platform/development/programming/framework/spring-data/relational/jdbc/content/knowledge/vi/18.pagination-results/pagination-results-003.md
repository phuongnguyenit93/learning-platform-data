# `Page`, truy vấn `count` và tổng số kết quả

Trong **Spring Data Relational JDBC**, phân trang không chỉ là giới hạn số dòng SQL trả về. Khi method repository trả về `Page<T>`, ứng dụng còn nhận metadata về trang hiện tại và tổng số kết quả phù hợp với điều kiện truy vấn. Để biết tổng số, Spring Data JDBC có thể chạy thêm một câu `COUNT` bên cạnh câu `SELECT` lấy nội dung trang.

Ba kiểu kết quả thường cần phân biệt:

- **`Page<T>`**: nội dung trang, thông tin điều hướng và tổng số phần tử/tổng số trang. Có thể cần truy vấn `COUNT` bổ sung.
- **`Slice<T>`**: nội dung trang và thông tin còn trang tiếp theo hay không. Thường lấy thêm một phần tử (`pageSize + 1`) để xác định `hasNext()`, không cần tổng số toàn bộ.
- **`List<T>` kết hợp `Pageable`**: chỉ lấy phần dữ liệu trong phạm vi trang; không tạo `Page` metadata và không cần count query.

Chọn kiểu trả về theo thông tin thực sự cần ở giao diện hoặc use case. Nếu màn hình cần “trang 2 trên 14” và “có 273 kết quả”, dùng `Page`. Nếu chỉ cần nút “Tải thêm”, `Slice` thường tiết kiệm hơn. Nếu chỉ cần danh sách có giới hạn, `List` với `Pageable` tránh chi phí đếm tổng.

## 1. `Pageable` biểu diễn yêu cầu phân trang

`Pageable` là đối tượng mang số trang, kích thước trang, offset và thông tin sắp xếp. Spring Data dùng nó để tạo giới hạn truy vấn.

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
);
```

Các giá trị trong ví dụ:

| Thành phần | Giá trị | Ý nghĩa |
|---|---:|---|
| Page number | `0` | Trang đầu tiên; số trang bắt đầu từ 0 |
| Page size | `20` | Tối đa 20 phần tử trong một trang |
| Offset | `0` | Bỏ qua 0 phần tử trước khi lấy trang |
| Sort | `createdAt DESC, id ASC` | Sắp xếp mới nhất trước, dùng ID để phá hòa |

Offset được tính từ số trang và kích thước trang:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Ví dụ `PageRequest.of(2, 20)` yêu cầu trang thứ ba (theo cách đếm cho người dùng), tương ứng `OFFSET 40` và `LIMIT 20` trong SQL. Không nhầm số trang zero-based của API với số trang thường hiển thị từ 1 trên giao diện.

`Pageable` cũng chứa `Sort`, vì vậy không truyền thêm một tham số `Sort` cùng method đã có `Pageable`. Các API nhận `Pageable` mong đợi giá trị không `null`; nếu thực sự không muốn phân trang, dùng `Pageable.unpaged()` ở những API hỗ trợ.

## 2. Khai báo repository trả về `Page<T>`

Spring Data JDBC hỗ trợ method query trả về `Page<T>` cùng tham số `Pageable`. Ví dụ entity đơn giản:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @Column("created_at")
    private Instant createdAt;

    // constructors, getters, domain methods...
}
```

Repository:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface PurchaseOrderRepository extends
        CrudRepository<PurchaseOrder, Long>,
        PagingAndSortingRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(String status, Pageable pageable);
}
```

`PagingAndSortingRepository` cung cấp các abstraction phân trang/sắp xếp; `CrudRepository` cung cấp `save`, `findById`, `delete` và các thao tác CRUD. Trong các phiên bản Spring Data hiện đại, hai interface này là các contract riêng, nên khai báo cả hai nếu cần cả CRUD lẫn paging/sorting.

Gọi repository:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
);

Page<PurchaseOrder> page = purchaseOrderRepository.findByStatus("OPEN", pageable);

List<PurchaseOrder> orders = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Method `findByStatus` là **derived query**: Spring Data phân tích tên method để tạo điều kiện `status = ?`, sau đó áp dụng phân trang. Spring Data JDBC hiện giới hạn query derivation ở các property đơn giản trực tiếp trên aggregate root; không mặc định tạo JOIN để truy vấn property của aggregate khác hoặc entity con.

## 3. `Page` cung cấp metadata nào?

`Page<T>` kế thừa `Slice<T>` và bổ sung tổng số kết quả. Những phương thức thường dùng:

| Method | Ý nghĩa |
|---|---|
| `getContent()` | Danh sách phần tử trong trang hiện tại |
| `getNumber()` | Số trang hiện tại, bắt đầu từ 0 |
| `getSize()` | Kích thước trang được yêu cầu |
| `getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại |
| `getTotalElements()` | Tổng số phần tử khớp điều kiện trên toàn bộ kết quả |
| `getTotalPages()` | Tổng số trang theo kích thước trang |
| `hasNext()` / `hasPrevious()` | Có trang tiếp theo/trước đó không |
| `isFirst()` / `isLast()` | Có phải trang đầu/cuối không |
| `getSort()` | Thông tin sắp xếp được áp dụng |

Ví dụ có 237 đơn hàng khớp điều kiện, mỗi trang 20 phần tử:

| Metadata | Giá trị |
|---|---:|
| Trang hiện tại | 1 / 12 |
| Tổng số kết quả | 237 |
| Kích thước trang | 20 |
| Phạm vi đang hiển thị | 1–20 |

Số trang là phép làm tròn lên:

\[
\text{totalPages} = \left\lceil \frac{\text{totalElements}}{\text{pageSize}} \right\rceil
\]

Với 237 phần tử và page size 20, tổng số trang là 12. Trang cuối chỉ có 17 phần tử. Nếu không có kết quả, tổng số phần tử là 0 và tổng số trang là 0.

`getTotalElements()` không phải số phần tử trong trang hiện tại; dùng `getNumberOfElements()` cho số lượng content thực tế. Phân biệt hai giá trị này giúp tránh hiển thị sai “20 kết quả” khi thực tế hệ thống có hàng nghìn kết quả.

## 4. Vì sao `Page` có thể chạy thêm truy vấn `COUNT`?

Để trả `Page<T>`, framework cần biết:

1. Các hàng nào thuộc trang được yêu cầu.
2. Tổng số hàng khớp điều kiện, không bị giới hạn bởi `LIMIT/OFFSET`.

Vì thế, một request có thể tạo hai truy vấn logic:

```sql
-- Lấy nội dung của trang hiện tại
SELECT id, status, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id ASC
LIMIT :pageSize OFFSET :offset;

-- Đếm tổng số đơn hàng khớp điều kiện
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status;
```

Truy vấn `COUNT` phải dùng **cùng điều kiện lọc** với truy vấn lấy content. Nó không được áp dụng `LIMIT/OFFSET`, nếu không `totalElements` chỉ phản ánh số hàng của trang chứ không phải tổng kết quả.

Spring Data JDBC có thể suy ra count query từ query derived. Tài liệu mô tả `Page` có thể cần count query (*potentially a count query*); tùy trường hợp, framework có thể suy ra đủ metadata từ kết quả trang và không cần thực hiện count. Vì vậy không nên viết test hoặc tối ưu dựa trên giả định mọi lời gọi `Page` luôn phát đúng hai statement trong mọi trường hợp.

### Count phải đếm aggregate root, không đếm hàng JOIN bị nhân bản

Với mô hình có nhiều bảng, một phép JOIN có thể nhân bản hàng root. Ví dụ một đơn có ba dòng hàng, truy vấn JOIN `purchase_order` với `order_line` trả ba hàng cho cùng một đơn. Nếu cần đếm số **đơn hàng**, `COUNT(*)` trên JOIN có thể đếm thành ba.

Trong SQL tùy chỉnh, phải chọn cách đếm phù hợp với đối tượng mà API trả về:

```sql
-- Đếm số aggregate root, tránh bị nhân bản bởi child rows
SELECT COUNT(DISTINCT o.id)
FROM purchase_order o
JOIN order_line l ON l.order_id = o.id
WHERE l.product_id = :productId;
```

Hoặc dùng `EXISTS` nếu chỉ cần kiểm tra có child phù hợp:

```sql
SELECT COUNT(*)
FROM purchase_order o
WHERE EXISTS (
    SELECT 1
    FROM order_line l
    WHERE l.order_id = o.id
      AND l.product_id = :productId
);
```

Đếm đúng đối tượng là điều kiện để `totalElements` và `totalPages` có ý nghĩa.

## 5. Count query mặc định của derived query

Với method như:

```java
Page<PurchaseOrder> findByStatusAndCreatedAtAfter(
        String status,
        Instant from,
        Pageable pageable
);
```

Spring Data JDBC tạo query content dựa trên điều kiện:

```sql
WHERE status = :status
  AND created_at > :from
```

Count query được suy ra từ cùng predicate, bỏ phần giới hạn trang và sắp xếp:

```sql
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status
  AND created_at > :from;
```

Bạn không cần khai báo một method `countBy...` chỉ để `Page` hoạt động. Nếu muốn đếm độc lập ở một use case khác, repository có thể khai báo method `long countByStatus(String status)` hoặc dùng `count(...)` ở tầng thích hợp.

Ví dụ:

```java
public interface PurchaseOrderRepository extends
        CrudRepository<PurchaseOrder, Long>,
        PagingAndSortingRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatus(String status, Pageable pageable);

    long countByStatus(String status);
}
```

`countByStatus` là một truy vấn count độc lập; nó không cần tải entity rồi đếm trong Java. Với derived query, điều kiện vẫn phải tham chiếu property hợp lệ trên aggregate root theo giới hạn query derivation của Spring Data JDBC.

## 6. `Slice<T>` khi không cần tổng số kết quả

`Slice<T>` chỉ cần biết có phần tử tiếp theo hay không. Để xác định điều đó, Spring Data JDBC có thể lấy `pageSize + 1` hàng. Ví dụ page size là 20, framework đọc tối đa 21 hàng:

- Có 21 hàng → content giữ 20 hàng đầu và `hasNext()` là `true`.
- Có 20 hàng trở xuống → không có hàng thừa, `hasNext()` là `false`.

```java
Slice<PurchaseOrder> findByStatus(String status, Pageable pageable);
```

Ví dụ gọi:

```java
Slice<PurchaseOrder> slice = repository.findByStatus(
        "OPEN",
        PageRequest.of(0, 20, Sort.by("id").ascending())
);

List<PurchaseOrder> content = slice.getContent();
boolean hasNext = slice.hasNext();
```

`Slice` không cung cấp `getTotalElements()` hoặc `getTotalPages()` vì không có tổng số toàn bộ. Điều này phù hợp với feed, danh sách hoạt động, lịch sử cuộn hoặc giao diện “Tải thêm”.

## 7. `List<T>` với `Pageable`: giới hạn dữ liệu nhưng không đếm

Nếu method trả về `List<T>` và nhận `Pageable`, Spring Data vẫn áp dụng offset, limit và sort, nhưng không tạo `Page` metadata. Do đó count query không cần chạy:

```java
List<PurchaseOrder> findByStatus(String status, Pageable pageable);
```

Đây là lựa chọn tốt khi caller chỉ cần nội dung trang và đã tự quản lý điều hướng hoặc không cần biết có trang tiếp theo. Tuy nhiên, `List` không có `hasNext()`; nếu cần biết còn dữ liệu, chọn `Slice`.

### So sánh ba kiểu trả về

| Kiểu | Content | Biết còn trang tiếp? | Biết tổng số? | Count query |
|---|---|---|---|---|
| `Page<T>` | Có | Có | Có | Có thể cần |
| `Slice<T>` | Có | Có | Không | Không cần để xác định `hasNext()` |
| `List<T>` + `Pageable` | Có | Không | Không | Không |

Nếu count query là phần tốn kém nhất của request, chuyển `Page` sang `Slice` có thể giảm chi phí đáng kể. Nhưng chỉ làm vậy khi UI/business không thực sự cần tổng số.

## 8. Sorting ổn định để phân trang không bị trùng hoặc mất hàng

Phân trang dựa trên offset cần một thứ tự xác định. Nếu sắp xếp theo một cột không duy nhất, ví dụ `createdAt DESC`, nhiều đơn có cùng thời điểm có thể xuất hiện ở thứ tự khác nhau giữa hai request. Khi có insert/update đồng thời, người dùng có thể thấy một phần tử lặp lại ở hai trang hoặc bị bỏ qua.

Nên thêm một khóa phá hòa duy nhất:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        )
);
```

`id` giúp thứ tự xác định khi nhiều hàng có cùng `createdAt`. Sort property dùng **tên property Java** trong domain mapping, không phải tên cột SQL nếu hai tên khác nhau. Ví dụ property `createdAt` được map sang `created_at` thì dùng `Sort.by("createdAt")`.

Một sort ổn định không biến nhiều request trang thành một snapshot nhất quán. Nếu dữ liệu thay đổi giữa lúc client tải trang 0 và trang 1, offset vẫn có thể dịch chuyển. Nếu cần snapshot nhất quán, cần transaction/read isolation phù hợp hoặc thiết kế cursor/keyset theo một khóa thứ tự ổn định.

## 9. Offset pagination và chi phí ở trang sâu

SQL dạng `LIMIT/OFFSET` rất dễ dùng:

```sql
SELECT id, status, created_at
FROM purchase_order
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 200000;
```

Nhưng khi offset lớn, database vẫn có thể phải đọc/duyệt và loại bỏ rất nhiều hàng trước khi trả về trang cần thiết. Vì vậy trang đầu thường nhanh hơn nhiều so với trang rất sâu.

Các lựa chọn khi offset trở nên đắt:

- Dùng `Slice` để không cần count tổng nếu giao diện chỉ cần tiếp tục.
- Dùng keyset/seek pagination dựa trên giá trị cuối cùng của trang trước.
- Giới hạn số trang tối đa hoặc yêu cầu bộ lọc hẹp hơn.
- Tạo index phù hợp với điều kiện lọc và thứ tự sắp xếp.
- Dùng truy vấn chuyên biệt cho báo cáo thay vì tải aggregate đầy đủ.

Spring Data Commons có abstraction scrolling/keyset ở một số module và phiên bản, nhưng khả năng hỗ trợ phụ thuộc store implementation. Không nên giả định mọi kiểu `ScrollPosition` hoặc keyset API được Spring Data JDBC hỗ trợ giống nhau; hãy kiểm tra API của đúng nhánh đang dùng. Nếu cần keyset trong Spring Data JDBC, có thể triển khai custom repository query với điều kiện seek tường minh.

Ví dụ keyset SQL theo cặp `(created_at, id)` giảm dần/tăng dần tương ứng:

```sql
SELECT id, status, created_at
FROM purchase_order
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at DESC, id ASC
LIMIT :pageSize;
```

Điều kiện seek phải khớp chính xác thứ tự sort và xử lý null nhất quán. Keyset thích hợp cho “trang tiếp theo” nhưng không thuận tiện cho việc nhảy trực tiếp đến trang số 500 như offset pagination.

## 10. `@Query` trong Spring Data JDBC không tự hỗ trợ `Pageable`

Đây là điểm khác biệt cần chú ý nếu đã quen với Spring Data JPA. Tài liệu Spring Data JDBC hiện hành nêu rõ **string-based query được khai báo bằng `@Query` không hỗ trợ pagination và không nhận `Sort`, `PageRequest` hoặc `Limit` làm tham số đặc biệt**. Framework không viết lại câu SQL tùy chỉnh của bạn để thêm limit/offset.

Ví dụ sau không phải cách hợp lệ để yêu cầu Spring tự thêm phân trang vào SQL string:

```java
// Không dùng cách này với string-based @Query của Spring Data JDBC.
@Query("SELECT * FROM purchase_order WHERE status = :status")
List<PurchaseOrder> findByStatus(String status, Pageable pageable);
```

Ngoài ra, annotation `org.springframework.data.jdbc.repository.query.Query` của Spring Data JDBC **không có thuộc tính `countQuery`** như `@Query` của Spring Data JPA. Không sao chép ví dụ JPA có `countQuery = "SELECT COUNT..."` sang JDBC.

Nếu cần SQL phức tạp kèm phân trang và tổng số, có hai hướng thường dùng:

1. Viết custom repository implementation bằng `NamedParameterJdbcTemplate`, tự thêm `LIMIT/OFFSET` và viết câu `COUNT` với cùng predicate.
2. Với truy vấn theo mapping `Query` của Spring Data Relational, dùng `Query.with(pageable)` để giới hạn/sắp xếp, gọi `JdbcAggregateOperations.findAll(Query, Class)` lấy content và `count(Query, Class)` lấy tổng; tự dựng `PageImpl`.

### Hướng A: custom repository với SQL và count riêng

Ví dụ DTO cho màn hình danh sách:

```java
public record OrderSummary(Long id, String status, Instant createdAt) {}
```

SQL content và count phải dùng cùng điều kiện:

```sql
-- Content query
SELECT id, status, created_at
FROM purchase_order
WHERE status = :status
ORDER BY created_at DESC, id ASC
LIMIT :limit OFFSET :offset;

-- Count query
SELECT COUNT(*)
FROM purchase_order
WHERE status = :status;
```

Trong custom repository, thực hiện cả hai query và dựng `Page`:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("status", status)
        .addValue("limit", pageable.getPageSize())
        .addValue("offset", pageable.getOffset());

List<OrderSummary> content = namedParameterJdbcTemplate.query(
        contentSql,
        params,
        (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("status"),
                rs.getTimestamp("created_at").toInstant()
        )
);

Long total = namedParameterJdbcTemplate.queryForObject(
        countSql,
        new MapSqlParameterSource("status", status),
        Long.class
);

return new PageImpl<>(content, pageable, total == null ? 0 : total);
```

Đoạn code minh họa bên trong custom repository implementation; `contentSql` và `countSql` là hằng SQL đã khai báo, còn sort cần được chuyển thành danh sách cột/chiều sort **được whitelist**. Không nối trực tiếp tên cột do client gửi vào SQL vì giá trị sort không thể bind như một parameter thông thường và có thể tạo SQL injection. Với API chỉ cho phép một số sort, ánh xạ enum/field API sang SQL identifier cố định.

Nếu query JOIN một-nhiều, hãy đếm root bằng `COUNT(DISTINCT root.id)` hoặc `EXISTS` như đã trình bày; nếu không, tổng số có thể lớn hơn số DTO/root thực tế.

### Hướng B: `JdbcAggregateOperations` và `Query.with(Pageable)`

Với query dùng Criteria/metadata mapping, Spring Data JDBC cung cấp `JdbcAggregateOperations` có `findAll(Query, Class)` và `count(Query, Class)`. API phân trang trực tiếp `findAll(Query, Class, Pageable)` đã bị deprecated từ Spring Data Relational 4.0; hướng dẫn API hiện hành là kết hợp query có offset/limit với count riêng rồi tạo `Page`.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

public Page<PurchaseOrder> findOpenOrders(Pageable pageable) {
    Query filter = Query.query(Criteria.where("status").is("OPEN"));

    List<PurchaseOrder> content = aggregateOperations.findAll(
            filter.with(pageable),
            PurchaseOrder.class
    );

    long total = aggregateOperations.count(filter, PurchaseOrder.class);

    return new PageImpl<>(content, pageable, total);
}
```

`Query.with(pageable)` mang offset, limit và sort vào query. Dùng `filter` gốc cho count để tổng số không bị giới hạn theo trang. Đây là API query mapping của Spring Data Relational, khác với string-based `@Query` repository annotation.

## 11. Count query có thể là phần đắt nhất

Một query content có thể dùng index và dừng sau khi lấy đủ 20 hàng. Count query lại phải đếm tất cả hàng thỏa predicate, có thể phải quét một vùng dữ liệu lớn. Với bảng nhiều triệu hàng, `COUNT(*)` không phải lúc nào cũng rẻ, đặc biệt khi điều kiện lọc phức tạp hoặc có JOIN.

Các cách giảm chi phí:

- Nếu giao diện không cần tổng số, trả `Slice` hoặc `List` + `Pageable`.
- Tối ưu predicate và index cho điều kiện lọc.
- Với query JOIN, viết count query đếm đúng root, tránh join không cần thiết.
- Không yêu cầu count lặp lại ở các service/UI nếu có thể tái sử dụng kết quả trong cùng response.
- Với dashboard/báo cáo lớn, cân nhắc summary table/materialized view hoặc số liệu tổng hợp được cập nhật riêng.
- Nếu tổng số chỉ mang tính tham khảo và chấp nhận độ trễ, cân nhắc cache hoặc projection phù hợp; cần thể hiện rõ semantics cho người dùng.

Không dùng một giá trị count cache để thay thế tổng số chính xác trong nghiệp vụ cần kiểm soát quota/hạn mức nếu cache có thể stale. Phân trang giao diện và kiểm tra điều kiện nghiệp vụ là hai use case khác nhau.

## 12. Tính nhất quán giữa content query và count query

`Page` gồm content và total count, nhưng hai câu SQL có thể được thực thi thành hai statement. Nếu dữ liệu thay đổi giữa hai statement, content và total có thể không phản ánh cùng một snapshot tùy transaction/isolation level.

Ví dụ:

1. Content query lấy 20 đơn hàng.
2. Một transaction khác thêm 5 đơn hàng phù hợp.
3. Count query chạy sau đó và trả tổng mới.

Khi đó `Page` có content dựa trên thời điểm thứ nhất nhưng `totalElements` dựa trên thời điểm thứ hai. Với phần lớn màn hình danh sách, sai khác nhỏ trong thời gian ngắn có thể chấp nhận. Nếu cần snapshot nhất quán, hãy thiết kế transaction/read isolation phù hợp với database và use case, đồng thời cân nhắc chi phí giữ transaction.

Không nên mở transaction dài trong khi người dùng chuyển qua nhiều trang. Một request trang thường là một đơn vị đọc độc lập; nếu cần một snapshot xuyên nhiều request, phải có chiến lược snapshot/version/cursor riêng.

## 13. Kiểm thử phân trang và tổng số

Test cần xác nhận cả content và count:

```java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired PurchaseOrderRepository repository;

    @Test
    void returnsPageContentAndTotalCount() {
        repository.save(new PurchaseOrder("OPEN"));
        repository.save(new PurchaseOrder("OPEN"));
        repository.save(new PurchaseOrder("OPEN"));
        repository.save(new PurchaseOrder("CLOSED"));

        Page<PurchaseOrder> page = repository.findByStatus(
                "OPEN",
                PageRequest.of(0, 2, Sort.by("id").ascending())
        );

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
        assertThat(page.hasNext()).isTrue();
    }
}
```

Ví dụ cần có schema `purchase_order` tương ứng và constructor của `PurchaseOrder` cho phép tạo entity trạng thái. Các test nên bổ sung trường hợp:

- Trang cuối có ít hơn `pageSize` phần tử.
- Trang vượt quá tổng số kết quả trả content rỗng nhưng total vẫn đúng.
- Không có kết quả (`totalElements = 0`, `totalPages = 0`).
- Nhiều hàng có cùng giá trị sort; tie-breaker ID giữ thứ tự xác định.
- Filter khác nhau cho count và content không bị lệch.
- Count trên JOIN không đếm trùng aggregate root.
- `Slice` xác định `hasNext()` đúng và không cần total count.

Để chứng minh count query có thực sự được chạy hay không, dùng SQL logging hoặc datasource proxy/instrumentation đếm statement. Kết quả `Page` đúng không đủ chứng minh có đúng số query mong đợi vì framework có thể tối ưu bỏ count trong một số trường hợp.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `totalElements` chỉ bằng số phần tử trong trang | Caller tự đếm `content.size()` thay vì dùng Page metadata hoặc count query bị giới hạn | Dùng `Page<T>` với derived query hoặc count query không có limit/offset |
| `totalPages` sai | Count query dùng predicate khác content query | Đồng bộ điều kiện lọc và bind parameters |
| Tổng số lớn bất thường | Count trên JOIN một-nhiều bị nhân bản root | Dùng `COUNT(DISTINCT root.id)` hoặc `EXISTS` |
| Không có tổng số | Method trả `Slice` hoặc `List` | Dùng `Page` nếu thật sự cần total metadata |
| `@Query` không áp dụng Pageable | String-based Spring Data JDBC `@Query` không hỗ trợ pagination | Viết custom repository SQL + count hoặc dùng `JdbcAggregateOperations` với `Query.with(pageable)` |
| `countQuery` không được nhận diện | Nhầm annotation JDBC với Spring Data JPA | JDBC `@Query` không có thuộc tính `countQuery`; tự viết count trong custom implementation |
| Trang sâu chạy chậm | Offset lớn | Dùng keyset/seek, giới hạn trang sâu và thêm index |
| Hàng bị lặp/mất giữa các trang | Sort không duy nhất hoặc dữ liệu thay đổi giữa request | Thêm unique tie-breaker, cân nhắc cursor/snapshot |
| Sort property không tồn tại | Dùng tên cột SQL thay vì property Java hoặc field sai | Dùng domain property và kiểm tra mapping |
| Test H2 pass nhưng production chậm/lỗi | Khác dialect, execution plan hoặc index | Test với database/driver production bằng Testcontainers |

## 15. Quy trình chọn `Page`, `Slice` hoặc `List`

1. **Xác định UI/use case cần gì.** Có cần tổng số chính xác và số trang không?
2. **Nếu cần total:** khai báo method derived trả `Page<T>` và nhận `Pageable`; framework có thể tạo count query.
3. **Nếu chỉ cần biết còn dữ liệu:** dùng `Slice<T>` để lấy thêm một phần tử kiểm tra `hasNext()`.
4. **Nếu chỉ cần nội dung giới hạn:** dùng `List<T>` với `Pageable`, không tạo metadata/count.
5. **Nếu dùng SQL `@Query`:** nhớ string-based query không hỗ trợ `Pageable`/`Sort`/`Limit`; triển khai SQL limit/offset và count riêng hoặc dùng query mapping API.
6. **Chọn sort ổn định:** thêm khóa duy nhất làm tie-breaker.
7. **Đo chi phí count và offset:** kiểm tra execution plan, index, số statement và độ sâu trang.
8. **Kiểm thử tổng số:** đặc biệt với JOIN, filter, trang cuối, trang rỗng và dữ liệu thay đổi đồng thời.

### Bảng quyết định nhanh

| Yêu cầu | Return type / cách làm |
|---|---|
| Cần `totalElements` và `totalPages` | `Page<T>` |
| Chỉ cần `hasNext()` | `Slice<T>` |
| Chỉ cần một phần danh sách | `List<T>` + `Pageable` |
| Derived query đơn giản trên root property | Repository method + `Pageable` |
| SQL tùy chỉnh có JOIN/aggregation | Custom repository + content SQL và count SQL riêng |
| Query theo Criteria mapping | `Query.with(pageable)` + `findAll(Query, type)` + `count(Query, type)` + `PageImpl` |
| Dữ liệu rất lớn, offset sâu | Keyset/seek pagination hoặc cursor phù hợp |

**Điểm cốt lõi:** `Page` cung cấp tổng số kết quả nên có thể cần thêm truy vấn `COUNT`; `Slice` chỉ kiểm tra có trang tiếp theo; `List` + `Pageable` chỉ lấy nội dung giới hạn. Với Spring Data JDBC, derived repository query hỗ trợ `Pageable`, còn string-based `@Query` không tự hỗ trợ pagination và không có thuộc tính `countQuery` kiểu JPA. Khi cần SQL tùy chỉnh, hãy tự kiểm soát cả truy vấn content lẫn count và bảo đảm chúng dùng cùng điều kiện lọc.

## Tài liệu tham khảo chính thức

- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): `Page`, `Slice`, `Pageable`, `List` với phân trang và giới hạn của string-based `@Query`.
- [Spring Data Commons — Query Methods Details](https://docs.spring.io/spring-data/relational/reference/data-commons/repositories/query-methods-details.html): cách chọn `Page`, `Slice`, `List`, chi phí count và offset pagination.
- [Spring Data JDBC — `JdbcAggregateOperations` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): `findAll(Query, Class)`, `count(Query, Class)` và các API phân trang template đã deprecated từ 4.0.
- [Spring Data Relational — `Query` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html): `with(Pageable)`, `limit`, `offset` và `sort`.
- [Spring Data JDBC — `@Query` API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/query/Query.html): các thuộc tính annotation JDBC; không có `countQuery`.
- [Spring Data Commons — `Page` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html): metadata tổng số và điều hướng trang.
- [Spring Data Commons — `PageRequest` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html): tạo yêu cầu phân trang zero-based.
