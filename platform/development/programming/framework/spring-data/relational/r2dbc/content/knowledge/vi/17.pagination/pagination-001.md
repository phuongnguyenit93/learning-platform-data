# Sắp xếp ổn định và thêm khóa phân biệt khi giá trị trùng nhau

## 1. Vì sao phân trang cần thứ tự ổn định?

Một truy vấn có thể trả về nhiều hàng thỏa cùng điều kiện. Khi ứng dụng hiển thị dữ liệu theo từng trang, database phải xác định hàng nào thuộc trang đầu, hàng nào thuộc trang tiếp theo. Việc phân trang chỉ đáng tin cậy khi thứ tự hàng được xác định rõ.

Ví dụ một màn hình hiển thị đơn hàng mới nhất trước:

~~~sql
SELECT id, order_number, created_at, status
FROM orders
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
~~~

Nếu nhiều đơn hàng có cùng giá trị created_at, database không có nghĩa vụ giữ chúng theo một thứ tự cụ thể. Những hàng có cùng giá trị sắp xếp có thể xuất hiện theo thứ tự khác nhau giữa các lần thực thi, tùy execution plan, index, dữ liệu và cách database xử lý truy vấn.

Khi trang đầu và trang thứ hai được lấy bằng hai truy vấn riêng, một hàng có thể bị lặp lại hoặc bị bỏ sót nếu các hàng đồng hạng đổi vị trí giữa hai lần chạy. Cách giải quyết là tạo một thứ tự **toàn phần (total order)** bằng cách thêm một hoặc nhiều khóa phân biệt, thường là khóa chính duy nhất, vào cuối danh sách ORDER BY.

Ví dụ:

~~~sql
SELECT id, order_number, created_at, status
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

created_at vẫn là tiêu chí nghiệp vụ chính. id là tiêu chí phụ để phân biệt những hàng có cùng thời điểm tạo. Nếu id là khóa chính duy nhất, mỗi hàng có một vị trí xác định trong thứ tự kết quả.

Trong Spring Data R2DBC, quy tắc này áp dụng như với SQL quan hệ nói chung. Dùng repository, R2dbcEntityTemplate hay DatabaseClient đều cần bảo đảm thứ tự truy vấn rõ ràng trước khi phân trang.

## 2. ORDER BY không có khóa phân biệt có thể gây vấn đề gì?

Giả sử bảng orders có dữ liệu:

| id | order_number | created_at |
|---:|---|---|
| 101 | ORD-101 | 2026-11-15 10:00:00 |
| 102 | ORD-102 | 2026-11-15 10:00:00 |
| 103 | ORD-103 | 2026-11-15 10:00:00 |
| 104 | ORD-104 | 2026-11-15 09:59:00 |
| 105 | ORD-105 | 2026-11-15 09:58:00 |

Truy vấn:

~~~sql
SELECT id, order_number, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 2 OFFSET 0;
~~~

Hai hàng đầu tiên đều có created_at bằng 10:00. SQL chỉ quy định hai hàng đó đứng trước các hàng có thời gian cũ hơn; nó không quy định id 101 phải đứng trước id 102.

Lần chạy thứ nhất có thể trả:

~~~text
101, 102
~~~

Một lần chạy khác có thể trả:

~~~text
102, 101
~~~

Nếu trang thứ hai dùng OFFSET 2, hàng 101 hoặc 102 có thể xuất hiện lần nữa hoặc bị bỏ qua khi thứ tự giữa các lần chạy thay đổi.

Vấn đề không nằm ở bản thân LIMIT/OFFSET. Vấn đề là tập hàng được phân trang không có một thứ tự duy nhất, ổn định để áp dụng vị trí offset.

Không nên dựa vào:

- Thứ tự vật lý của hàng trong bảng.
- Thứ tự ID tình cờ được database trả về khi không có ORDER BY.
- Thứ tự insert ban đầu.
- Thứ tự mà một execution plan cụ thể đang tạo ra.
- Việc truy vấn hiện tại luôn có vẻ trả cùng một thứ tự trên máy phát triển.

Chỉ ORDER BY mới xác định thứ tự kết quả theo hợp đồng SQL. Nếu các giá trị trong ORDER BY bằng nhau, những hàng đó vẫn đồng hạng.

## 3. Tạo thứ tự toàn phần bằng khóa phân biệt

### 3.1. Thêm khóa chính làm tiêu chí cuối

Một cách thông dụng là thêm khóa chính duy nhất vào cuối ORDER BY:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Thứ tự được xác định theo quy tắc từ trái sang phải:

1. So sánh created_at giảm dần.
2. Nếu created_at bằng nhau, so sánh id giảm dần.
3. Vì id là duy nhất, không còn hai hàng nào đồng hạng sau tiêu chí cuối.

Có thể dùng id tăng dần thay vì giảm dần:

~~~sql
ORDER BY created_at DESC, id ASC
~~~

Cả hai đều tạo thứ tự xác định nếu id duy nhất. Chọn chiều nào phụ thuộc vào cách ứng dụng muốn sắp xếp các hàng cùng thời điểm.

### 3.2. Khóa phân biệt cần thực sự duy nhất trong tập kết quả

Một trường chỉ có vẻ duy nhất trong dữ liệu hiện tại chưa chắc là khóa phân biệt an toàn. Ví dụ order_number có thể được unique theo tenant chứ không unique toàn bảng. Nếu query lọc đúng một tenant, cặp tenant_id + order_number có thể duy nhất; nếu query nhiều tenant, cần đưa đủ các thành phần khóa vào ORDER BY.

Ví dụ:

~~~sql
ORDER BY created_at DESC, tenant_id ASC, order_number ASC
~~~

Thứ tự cuối cùng phải phân biệt được mọi hàng trong tập kết quả. Cách đơn giản và thường rõ ràng nhất là dùng primary key duy nhất của bảng làm tie-breaker.

### 3.3. Có thể cần nhiều khóa phụ

Nếu khóa duy nhất là khóa tổng hợp (composite primary key), cần thêm đủ các cột khóa vào cuối ORDER BY:

~~~sql
ORDER BY created_at DESC, tenant_id ASC, local_id ASC
~~~

Giả sử primary key là (tenant_id, local_id), cặp đó phân biệt hàng trong bảng. Chỉ thêm tenant_id hoặc chỉ thêm local_id có thể chưa đủ.

### 3.4. Khóa phân biệt nên ổn định

Một tie-breaker tốt thường là:

- Không null.
- Duy nhất trong tập kết quả.
- Không thay đổi trong vòng đời bản ghi.
- Có index hoặc nằm trong primary key khi phù hợp.

Tránh dùng một trường nghiệp vụ có thể bị chỉnh sửa như tên hiển thị làm khóa phân biệt cuối cùng nếu không có thêm khóa duy nhất. Khi giá trị đó thay đổi, hàng có thể chuyển vị trí giữa các trang.

## 4. Thứ tự nhiều cột được đánh giá như thế nào?

SQL áp dụng các tiêu chí ORDER BY theo thứ tự từ trái sang phải. Tiêu chí sau chỉ được xét khi các tiêu chí trước bằng nhau.

Ví dụ:

~~~sql
ORDER BY status ASC, created_at DESC, id DESC
~~~

Có nghĩa:

1. Nhóm theo status tăng dần.
2. Trong cùng status, đơn mới hơn đứng trước.
3. Nếu status và created_at đều bằng nhau, id lớn hơn đứng trước.

Đây là cách xây dựng thứ tự xác định cho một danh sách có nhiều quy tắc nghiệp vụ.

Bảng sau minh họa:

| id | status | created_at |
|---:|---|---|
| 14 | ACTIVE | 2026-11-15 10:00 |
| 12 | ACTIVE | 2026-11-15 10:00 |
| 13 | ACTIVE | 2026-11-15 09:00 |
| 18 | INACTIVE | 2026-11-15 10:00 |
| 17 | INACTIVE | 2026-11-15 10:00 |

Với ORDER BY status ASC, created_at DESC, id DESC, thứ tự sẽ là:

1. ACTIVE, 10:00, id 14
2. ACTIVE, 10:00, id 12
3. ACTIVE, 09:00, id 13
4. INACTIVE, 10:00, id 18
5. INACTIVE, 10:00, id 17

Nếu bỏ id khỏi ORDER BY, các hàng trong cùng status và cùng created_at lại đồng hạng.

## 5. Chiều tăng/giảm của từng khóa cần nhất quán với yêu cầu

Không phải mọi cột đều phải cùng chiều. Có thể kết hợp ASC và DESC:

~~~sql
ORDER BY priority ASC, created_at DESC, id DESC
~~~

Ví dụ ưu tiên số nhỏ trước, sau đó trong cùng mức ưu tiên hiển thị bản ghi mới nhất trước, cuối cùng dùng id để phân biệt.

Khi viết điều kiện keyset pagination, chiều của từng cột sẽ ảnh hưởng toán tử so sánh. Với tiêu chí ASC, hàng kế tiếp có giá trị lớn hơn; với DESC, hàng kế tiếp có giá trị nhỏ hơn. Khi trộn nhiều chiều, phải tạo điều kiện lexicographic tương ứng cho từng nhánh.

Không nên thay đổi thứ tự cột hoặc chiều sắp xếp giữa các trang. Cursor của trang tiếp theo chỉ có ý nghĩa khi truy vấn dùng cùng bộ tiêu chí ORDER BY như trang trước.

## 6. Sắp xếp ổn định với R2dbcEntityTemplate

R2dbcEntityTemplate cho phép khai báo Sort trong Query. Với entity có property Java là createdAt và id, có thể viết:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(Criteria.where("status").is("ACTIVE"))
        .sort(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
        ))
        .limit(20)
        .offset(0);

Flux<Order> firstPage = template.select(query, Order.class);
~~~

Trong mapping API, tên property thường là tên thuộc tính Java; Spring Data dùng metadata để ánh xạ sang cột database. Ví dụ property createdAt có thể được ánh xạ sang cột created_at theo naming strategy hoặc @Column.

Điểm cần nhớ là tiêu chí id phải được thêm vào Sort. Nếu chỉ dùng:

~~~java
.sort(Sort.by(Sort.Order.desc("createdAt")))
~~~

thì các đơn hàng có cùng createdAt vẫn đồng hạng và thứ tự của chúng chưa được xác định đầy đủ.

Có thể đóng gói quy tắc sắp xếp vào một hằng số hoặc phương thức dùng chung để mọi query phân trang của cùng use case sử dụng cùng thứ tự:

~~~java
private static final Sort ORDER_PAGE_SORT = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
~~~

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"))
        .sort(ORDER_PAGE_SORT)
        .limit(pageSize)
        .offset(offset);
~~~

Điều này giảm nguy cơ trang đầu và trang tiếp theo vô tình dùng các tiêu chí sắp xếp khác nhau.

## 7. Derived query và Sort trong repository

Với query method, có thể khai báo Sort như một tham số:

~~~java
Flux<Order> findByStatus(String status, Sort sort);
~~~

Caller:

~~~java
Sort stableSort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);

return orderRepository.findByStatus("ACTIVE", stableSort);
~~~

Tên thuộc tính trong Sort là property Java của entity. Nếu entity khai báo:

~~~java
@Table("orders")
public record Order(
        @Id Long id,
        @Column("created_at") Instant createdAt,
        String status
) {}
~~~

thì Sort dùng createdAt chứ không phải tên cột created_at trong metadata-oriented query method.

Với Spring Data R2DBC, query method có thể nhận tham số Sort và trả Flux. Hãy kiểm tra khả năng cụ thể theo phiên bản Spring Data trong dự án, đặc biệt khi dùng query method tùy chỉnh hoặc các kiểu trả về đặc thù.

Không nên cho phép client truyền trực tiếp bất kỳ tên property nào vào Sort. Hãy chuyển sort key từ API thành danh sách property được cho phép và luôn thêm khóa phân biệt duy nhất ở cuối.

## 8. Sắp xếp với @Query

Khi viết SQL tường minh, ORDER BY phải chứa cả tiêu chí chính và tie-breaker:

~~~java
@Query("""
    SELECT id, order_number, created_at, status
    FROM orders
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
    """)
Flux<OrderSummary> findPage(
        @Param("status") String status,
        @Param("limit") int limit,
        @Param("offset") long offset
);
~~~

Ở đây tên cột là tên database, nên dùng created_at. Vì câu SQL đã khai báo ORDER BY tường minh, tham số Sort của caller không tự động thay đổi thứ tự trong câu query này.

Với query có phân trang, cần bảo đảm:

- ORDER BY luôn có khóa phân biệt cuối cùng.
- LIMIT và OFFSET được kiểm tra giá trị hợp lệ.
- Cùng một filter và sort được dùng cho các trang liên tiếp.
- Nếu cần tổng số bản ghi, count query dùng cùng điều kiện lọc.
- Tên cột và chiều sort đến từ SQL cố định hoặc allowlist.

Không nối chuỗi sort do client gửi vào @Query. Giá trị bind không thể thay tên cột hoặc từ khóa ASC/DESC. Nếu có nhiều kiểu sắp xếp, tạo các query tường minh hoặc xây dựng Sort từ allowlist.

## 9. OFFSET pagination và thứ tự xác định

OFFSET pagination thường có dạng:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

Ví dụ pageSize là 20:

| Trang | LIMIT | OFFSET |
|---:|---:|---:|
| 0 | 20 | 0 |
| 1 | 20 | 20 |
| 2 | 20 | 40 |
| 3 | 20 | 60 |

Thứ tự toàn phần bảo đảm rằng với cùng một trạng thái dữ liệu và cùng điều kiện lọc, các vị trí trong kết quả có ý nghĩa xác định. Điều đó tránh sự hoán đổi tùy ý giữa những hàng có cùng giá trị sort.

Tuy nhiên, thứ tự toàn phần không bảo đảm các trang lấy ở những thời điểm khác nhau nhìn thấy cùng một snapshot dữ liệu. Nếu có insert hoặc delete giữa hai request, OFFSET vẫn có thể dịch chuyển.

Ví dụ:

1. Request trang đầu lấy hàng 1 đến 20.
2. Một hàng mới được insert vào đầu danh sách.
3. Request trang hai dùng OFFSET 20.
4. Vì có thêm một hàng ở trước, hàng cuối của trang đầu có thể xuất hiện lại ở trang hai.

Một trường hợp khác là hàng bị xóa ở trước offset; một hàng có thể bị bỏ qua. Đây là vấn đề do dữ liệu thay đổi giữa các lần đọc, khác với vấn đề tie-breaker.

Do đó, có hai cấp độ cần phân biệt:

- **Deterministic ordering:** cùng một tập dữ liệu tạo ra cùng thứ tự hàng.
- **Snapshot consistency across requests:** các trang nhìn thấy cùng một trạng thái dữ liệu dù dữ liệu có thể thay đổi.

ORDER BY với khóa phân biệt giải quyết cấp độ thứ nhất. Muốn có snapshot nhất quán qua nhiều truy vấn, cần chính sách transaction/isolation hoặc cơ chế pagination phù hợp với yêu cầu ứng dụng.

## 10. Keyset pagination cũng cần thứ tự toàn phần

Keyset pagination (còn gọi là seek pagination) lấy trang tiếp theo dựa trên giá trị của hàng cuối trang trước, thay vì bỏ qua một số lượng hàng bằng OFFSET.

Ví dụ thứ tự:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Sau khi trang hiện tại kết thúc ở hàng có:

- created_at = 2026-11-15 10:00:00
- id = 120

trang tiếp theo cần lấy những hàng đứng sau vị trí đó trong thứ tự giảm dần:

~~~sql
SELECT id, order_number, created_at, status
FROM orders
WHERE status = :status
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Điều kiện có nghĩa:

- Lấy hàng có created_at nhỏ hơn thời điểm cuối trang trước; hoặc
- Nếu created_at bằng nhau, lấy hàng có id nhỏ hơn id cuối trang.

Khóa id là cần thiết. Nếu chỉ viết created_at < :lastCreatedAt, các hàng còn lại có cùng thời điểm với hàng cuối trang sẽ bị bỏ qua.

### 10.1. Vì sao cần mọi thành phần của sort key trong cursor?

Cursor phải chứa đủ giá trị của tất cả tiêu chí ORDER BY, bao gồm tie-breaker cuối cùng.

Với:

~~~sql
ORDER BY priority ASC, created_at DESC, id DESC
~~~

cursor cần lưu:

- priority của hàng cuối trang.
- created_at của hàng cuối trang.
- id của hàng cuối trang.

Nếu chỉ lưu created_at và id, ứng dụng không thể xác định đúng vị trí của hàng trong thứ tự có priority đứng trước.

### 10.2. Công thức tổng quát cho thứ tự nhiều cột

Giả sử ORDER BY có các cột K1, K2, ..., Kn. Điều kiện trang tiếp theo có dạng:

~~~text
K1 sau cursor
OR (K1 bằng cursor AND K2 sau cursor)
OR (K1 bằng cursor AND K2 bằng cursor AND K3 sau cursor)
...
OR (K1 ... K(n-1) bằng cursor AND Kn sau cursor)
~~~

"After cursor" có nghĩa lớn hơn với ASC và nhỏ hơn với DESC. Các nhánh bằng nhau phải so sánh chính xác theo semantics của database.

Với ba khóa có chiều ASC, DESC, DESC:

~~~sql
WHERE
       priority > :lastPriority
    OR (priority = :lastPriority
        AND created_at < :lastCreatedAt)
    OR (priority = :lastPriority
        AND created_at = :lastCreatedAt
        AND id < :lastId)
~~~

Sau đó dùng cùng ORDER BY:

~~~sql
ORDER BY priority ASC, created_at DESC, id DESC
~~~

Đây là cách mở rộng keyset cho sort nhiều cột. Cần viết đúng thứ tự điều kiện và toán tử so sánh cho từng chiều.

## 11. Keyset pagination với DatabaseClient

Ví dụ repository service nhận cursor:

~~~java
public record OrderCursor(
        Instant createdAt,
        Long id
) {}
~~~

Truy vấn trang đầu khi chưa có cursor:

~~~java
public Flux<OrderSummary> firstPage(String status, int pageSize) {
    return databaseClient.sql("""
            SELECT id, order_number, created_at, status
            FROM orders
            WHERE status = :status
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
        .bind("status", status)
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new OrderSummary(
                row.get("id", Long.class),
                row.get("order_number", String.class),
                row.get("created_at", Instant.class),
                row.get("status", String.class)
        ))
        .all();
}
~~~

Trang tiếp theo:

~~~java
public Flux<OrderSummary> nextPage(
        String status,
        OrderCursor cursor,
        int pageSize) {

    return databaseClient.sql("""
            SELECT id, order_number, created_at, status
            FROM orders
            WHERE status = :status
              AND (
                    created_at < :lastCreatedAt
                    OR (
                        created_at = :lastCreatedAt
                        AND id < :lastId
                    )
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :pageSize
            """)
        .bind("status", status)
        .bind("lastCreatedAt", cursor.createdAt())
        .bind("lastId", cursor.id())
        .bind("pageSize", pageSize)
        .map((row, metadata) -> new OrderSummary(
                row.get("id", Long.class),
                row.get("order_number", String.class),
                row.get("created_at", Instant.class),
                row.get("status", String.class)
        ))
        .all();
}
~~~

Ví dụ dùng DatabaseClient để thể hiện rõ predicate. Trong code thực tế, cần xác thực cursor, giới hạn pageSize và xử lý trường hợp không có hàng. Khi tạo cursor cho response tiếp theo, dùng createdAt và id của **hàng cuối cùng thực sự được trả về**, không dùng hàng đầu hoặc giá trị từ request chưa được xác minh.

Nếu database trả timestamp với độ chính xác khác với giá trị cursor được serialize, có thể xảy ra so sánh lệch. Cursor cần giữ đủ độ chính xác mà database/driver sử dụng; tránh cắt phần fractional seconds khi mã hóa rồi gửi lại.

## 12. Xử lý NULL trong khóa sắp xếp

Các cột nullable tạo thêm một vấn đề. Trong SQL, NULL không so sánh như giá trị thông thường. Thứ tự NULL có thể khác giữa các database hoặc tùy cú pháp NULLS FIRST/NULLS LAST.

Ví dụ:

~~~sql
ORDER BY shipped_at DESC NULLS LAST, id DESC
~~~

PostgreSQL hỗ trợ cú pháp NULLS FIRST/LAST. Các database khác có thể có cú pháp hoặc mặc định khác. Khi cần portable SQL, có thể dùng biểu thức CASE:

~~~sql
ORDER BY
    CASE WHEN shipped_at IS NULL THEN 1 ELSE 0 END ASC,
    shipped_at DESC,
    id DESC
~~~

Biểu thức CASE đưa các hàng không có shipped_at xuống cuối, sau đó sắp xếp thời gian giảm dần và dùng id làm tie-breaker.

Với keyset pagination, cursor phải tính cả nhóm NULL và giá trị sort thực tế. Điều kiện so sánh đơn giản:

~~~sql
shipped_at < :lastShippedAt
~~~

không hoạt động như mong đợi khi một trong hai phía là NULL. Cần xây dựng nhánh điều kiện riêng cho nhóm NULL, phù hợp với quy tắc NULLS FIRST/LAST đã chọn.

Nếu có thể, chọn một sort key không nullable cho cursor, hoặc dùng một cột tạo sẵn có giá trị mặc định phù hợp. Việc này làm predicate đơn giản và ít lỗi hơn.

## 13. Collation, chữ hoa/chữ thường và các giá trị trùng nhau

Hai chuỗi khác nhau về byte có thể được collation xem là bằng nhau khi sắp xếp, ví dụ không phân biệt chữ hoa/chữ thường hoặc dấu. Điều này cũng có thể tạo nhóm đồng hạng.

Ví dụ:

~~~sql
ORDER BY lower(customer_name) ASC, id ASC
~~~

Nếu nhiều tên có cùng giá trị sau khi chuyển thành chữ thường, id sẽ phân biệt các hàng. Tương tự, collation không phân biệt dấu có thể xem nhiều chuỗi là tương đương khi sort.

Khi dùng expression trong ORDER BY, keyset cursor phải dùng đúng expression và semantics tương tự. Ví dụ sort theo lower(name) thì cursor cần lưu giá trị normalized tương ứng hoặc predicate cần lặp lại expression đó:

~~~sql
WHERE
    lower(customer_name) > lower(:lastName)
    OR (
        lower(customer_name) = lower(:lastName)
        AND id > :lastId
    )
ORDER BY lower(customer_name) ASC, id ASC
~~~

Cú pháp và hành vi collation phụ thuộc database. Hãy xác định sort key theo đúng collation của query, không chỉ theo chuỗi Java trước khi gửi xuống database.

## 14. Thay đổi dữ liệu trong khi phân trang

Ngay cả khi ORDER BY có khóa phân biệt, dữ liệu có thể thay đổi giữa các request.

Các tình huống:

- Bản ghi mới được thêm vào trước vị trí offset.
- Bản ghi bị xóa khỏi trang trước.
- Một trường sắp xếp được cập nhật khiến hàng di chuyển.
- Trạng thái thay đổi làm hàng đi vào hoặc ra khỏi điều kiện WHERE.
- Một hàng được cập nhật timestamp và chuyển sang nhóm sort khác.

### 14.1. OFFSET pagination

OFFSET pagination phụ thuộc vào vị trí hàng trong toàn bộ kết quả tại thời điểm query chạy. Khi tập dữ liệu thay đổi, vị trí đó có thể dịch chuyển. Tie-breaker giải quyết sự mơ hồ do giá trị trùng, nhưng không đóng băng vị trí giữa hai request.

### 14.2. Keyset pagination

Keyset pagination tiếp tục từ giá trị sort key cuối cùng. Insert mới nằm trước cursor thường không làm các hàng phía sau bị dịch chuyển như OFFSET. Tuy nhiên:

- Một hàng mới được insert sau cursor có thể xuất hiện ở trang tiếp theo.
- Hàng bị xóa sẽ không còn được trả về.
- Hàng thay đổi sort key có thể nhảy qua cursor hoặc xuất hiện lặp tùy hướng thay đổi.
- Thay đổi filter có thể làm tập kết quả khác đi.

Keyset giảm ảnh hưởng của việc thêm dữ liệu ở đầu danh sách, nhưng không phải snapshot transaction cho toàn bộ hành trình phân trang.

### 14.3. Snapshot nhất quán

Nếu nghiệp vụ cần người dùng duyệt một tập dữ liệu bất biến trong nhiều trang, cần một chiến lược snapshot rõ ràng. Có thể cân nhắc:

- Giữ transaction với isolation phù hợp nếu vòng đời đọc ngắn và database cho phép.
- Chụp một mốc thời gian hoặc high-water mark ở trang đầu và thêm điều kiện giới hạn các bản ghi sau mốc đó.
- Dùng snapshot/export job tạo tập kết quả cố định.
- Dùng version hoặc trạng thái dữ liệu để kiểm soát những thay đổi có thể xuất hiện.

Không nên giữ transaction mở trong thời gian dài qua nhiều request HTTP nếu điều đó gây giữ connection, snapshot hoặc lock quá lâu. Chọn chiến lược theo yêu cầu nhất quán và đặc tính database.

## 15. Index hỗ trợ thứ tự phân trang

Một truy vấn phổ biến:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Có thể đánh giá index:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON orders (status, created_at DESC, id DESC);
~~~

Index này đặt cột lọc status trước, tiếp theo là các cột sắp xếp created_at và id. Nó có thể hỗ trợ lọc và trả hàng theo thứ tự, tùy query planner, cardinality, database và workload.

Đối với keyset pagination, index phù hợp với filter và sort key có thể giúp database tìm vùng tiếp theo hiệu quả hơn. Nhưng index không thay thế ORDER BY; chỉ ORDER BY mới bảo đảm thứ tự kết quả.

Không nên tạo index chỉ dựa trên một ví dụ. Hãy xem xét:

- Tần suất query và tỷ lệ đọc/ghi.
- Selectivity của điều kiện WHERE.
- Số lượng giá trị khác nhau trong cột lọc.
- Thứ tự cột trong composite index.
- Chiều sort và khả năng database scan index theo chiều ngược.
- Dung lượng index và chi phí cập nhật.
- Execution plan trên dữ liệu thực tế.

Dùng EXPLAIN hoặc công cụ tương ứng để kiểm tra database có sử dụng index như dự kiến không.

## 16. Giới hạn page size và kiểm tra tham số

Page size quá lớn có thể tạo result set nặng, giữ nhiều dữ liệu trong pipeline và làm tăng latency. Nên đặt giới hạn tối đa ở service/API.

Ví dụ:

~~~java
int normalizedPageSize = Math.max(1, Math.min(requestedSize, 100));
~~~

Với OFFSET:

- page index không được âm.
- page size phải dương.
- offset cần được tính bằng kiểu đủ lớn để tránh tràn số khi page index cao.
- Không cho client gửi offset tùy ý vượt giới hạn nghiệp vụ.

Với keyset:

- page size vẫn cần giới hạn.
- cursor phải được kiểm tra định dạng và phiên bản.
- cursor phải gắn với đúng filter/sort mà nó được tạo ra.
- cursor không được phép thay đổi tenant hoặc phạm vi authorization.
- Không tin các giá trị sort key do client tự sửa nếu cursor ảnh hưởng đến phạm vi dữ liệu.

Cursor có thể được serialize và ký (sign) để phát hiện chỉnh sửa nếu nó được gửi qua API công khai. Ký cursor bảo vệ tính toàn vẹn của token, nhưng không thay thế authorization.

## 17. Thiết kế cursor ổn định cho API

Một API keyset có thể trả:

~~~json
{
  "items": [
    {
      "id": 120,
      "orderNumber": "ORD-120",
      "createdAt": "2026-11-15T10:00:00Z"
    }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}
~~~

Cursor nên mã hóa ít nhất:

- Giá trị của từng sort key ở hàng cuối trang.
- Sort direction và tên sort key hoặc một mã phiên bản của sort.
- Filter hoặc dấu vân tay của filter nếu cần bảo đảm cursor dùng với cùng truy vấn.
- Phiên bản định dạng cursor để có thể thay đổi trong tương lai.

Không nhất thiết phải đưa toàn bộ filter vào token; có thể ràng buộc cursor với filter đã được lưu hoặc ký kèm fingerprint. Quan trọng là không dùng cursor từ truy vấn này cho một truy vấn có sort/filter khác.

Ví dụ object nội bộ:

~~~java
public record OrderPageCursor(
        int version,
        Instant lastCreatedAt,
        Long lastId
) {}
~~~

Khi trả trang kế tiếp, lấy cursor từ hàng cuối cùng:

~~~java
OrderSummary last = items.get(items.size() - 1);

OrderPageCursor next = new OrderPageCursor(
        1,
        last.createdAt(),
        last.id()
);
~~~

Nếu Flux được xử lý theo streaming và không materialize toàn bộ page, có thể giữ phần tử cuối trong một cấu trúc điều phối phù hợp. Không nên thu thập một tập rất lớn vào List chỉ để lấy cursor; page size cần được giới hạn.

## 18. Những lỗi thường gặp khi sắp xếp và phân trang

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Hàng lặp hoặc bị bỏ giữa các trang | ORDER BY không có khóa phân biệt hoặc dữ liệu thay đổi | Thêm khóa duy nhất; cân nhắc keyset/snapshot |
| Các hàng cùng timestamp đổi vị trí | Chỉ sort theo timestamp | Thêm primary key làm tie-breaker |
| Trang đầu và trang sau có thứ tự khác nhau | Mỗi query dùng Sort khác nhau hoặc không có ORDER BY | Dùng một quy tắc sort thống nhất |
| Keyset bỏ sót hàng có cùng sort value | Cursor predicate chỉ so sánh cột chính | Thêm nhánh so sánh tie-breaker |
| Keyset trả lặp hàng | Predicate sai chiều ASC/DESC hoặc cursor lấy sai hàng | Viết predicate lexicographic khớp ORDER BY và dùng hàng cuối |
| Không lấy được hàng có sort key NULL | So sánh NULL bằng < hoặc > | Xác định NULLS FIRST/LAST và thêm predicate riêng |
| Kết quả sort chuỗi khác mong đợi | Collation hoặc case/accent sensitivity | Kiểm tra collation và dùng expression nhất quán |
| OFFSET lớn ngày càng chậm | Database phải bỏ qua nhiều hàng | Cân nhắc keyset và index phù hợp |
| Sort động gây lỗi hoặc rủi ro SQL | Nối tên cột từ request vào SQL | Dùng allowlist property/identifier |
| Query đã có index nhưng vẫn chậm | Index không khớp filter/sort hoặc planner chọn plan khác | Dùng EXPLAIN và đo trên dữ liệu thực |
| Cursor không dùng được sau khi đổi filter | Cursor không gắn với query semantics | Ràng buộc cursor với filter/sort/version |
| Page size làm hệ thống quá tải | Không giới hạn số hàng mỗi request | Đặt page size tối đa |

## 19. Kiểm thử thứ tự và pagination

Không chỉ kiểm tra số hàng trong một trang. Cần kiểm tra tính đúng của toàn bộ chuỗi trang.

### 19.1. Kiểm thử các giá trị sort trùng nhau

Tạo dữ liệu có nhiều hàng cùng created_at:

| id | created_at |
|---:|---|
| 11 | 10:00 |
| 12 | 10:00 |
| 13 | 10:00 |
| 14 | 09:00 |

Với ORDER BY created_at DESC, id DESC và page size 2:

- Trang đầu phải là id 13, 12.
- Trang tiếp theo phải là id 11, 14.

Các hàng có cùng timestamp vẫn được phân tách theo id. Nếu chỉ ORDER BY created_at, test nên chứng minh không có bảo đảm thứ tự giữa 11, 12 và 13.

### 19.2. Kiểm thử không trùng và không thiếu trên snapshot tĩnh

Với dữ liệu không thay đổi:

1. Lấy tất cả trang theo cùng filter và sort.
2. Ghép ID từ mọi trang.
3. Xác nhận không có ID trùng.
4. Xác nhận tập ID bằng toàn bộ ID thỏa filter.
5. Xác nhận thứ tự ghép đúng với ORDER BY toàn phần.

### 19.3. Kiểm thử keyset với nhiều hàng đồng hạng

Tạo nhiều hàng có cùng sort key chính và đặt page size nhỏ hơn số hàng đồng hạng. Điều này giúp kiểm tra cursor có dùng tie-breaker hay không.

Ví dụ có năm hàng cùng created_at và page size 2. Các trang phải lần lượt lấy hết năm hàng mà không bỏ hàng nào hoặc trả lặp.

### 19.4. Kiểm thử cập nhật đồng thời

Tạo tình huống insert/delete/update giữa hai lần lấy trang để xác nhận hành vi phù hợp với chính sách nhất quán của ứng dụng. Với OFFSET, cần chấp nhận hoặc kiểm soát dịch chuyển vị trí; với keyset, kiểm tra các thay đổi sort key và filter có thể ảnh hưởng cursor.

### 19.5. Kiểm thử với database thực tế

Dùng Testcontainers hoặc database test cùng loại để xác nhận semantics ORDER BY, NULL, collation, precision timestamp, LIMIT/OFFSET và predicate keyset. H2 hoặc mock không nhất thiết phản ánh chính xác hành vi của PostgreSQL/MySQL/SQL Server đang dùng.

## 20. Quy trình thiết kế thứ tự cho một endpoint phân trang

Có thể áp dụng trình tự sau:

1. Xác định tiêu chí nghiệp vụ chính, ví dụ createdAt giảm dần.
2. Xác định các hàng có thể trùng giá trị ở tiêu chí chính.
3. Chọn khóa phân biệt duy nhất, thường là primary key, làm tiêu chí cuối.
4. Chốt chiều ASC/DESC cho từng tiêu chí.
5. Xác định semantics của NULL và collation.
6. Dùng cùng thứ tự cho mọi trang.
7. Chọn OFFSET khi cần nhảy tới trang theo số trang và tập dữ liệu phù hợp.
8. Chọn keyset khi cần duyệt tuần tự tập dữ liệu lớn hoặc giảm dịch chuyển do insert trước cursor.
9. Với keyset, lưu mọi sort key trong cursor và viết predicate theo thứ tự lexicographic.
10. Đánh giá index bằng query plan và workload.
11. Giới hạn page size và xác thực cursor/filter.
12. Kiểm thử giá trị trùng, NULL, concurrent writes và chuỗi trang hoàn chỉnh.

## 21. Kết luận

Phân trang cần một thứ tự xác định. ORDER BY chỉ theo một cột có thể vẫn để nhiều hàng đồng hạng nếu giá trị cột đó trùng nhau. Thêm một khóa phân biệt duy nhất, thường là primary key, vào cuối ORDER BY sẽ tạo thứ tự toàn phần và giúp xác định vị trí từng hàng trong kết quả.

Quy tắc này áp dụng cho repository query, R2dbcEntityTemplate, @Query và DatabaseClient. Với OFFSET pagination, thứ tự toàn phần ngăn các hàng đồng hạng tự đổi chỗ khi tập dữ liệu không đổi; nó không đóng băng dữ liệu giữa những request khác thời điểm. Với keyset pagination, cursor phải chứa toàn bộ sort key và predicate phải phản ánh chính xác thứ tự ASC/DESC, NULL và collation.

Khi thiết kế endpoint phân trang, hãy chốt sort key, tie-breaker, semantics dữ liệu, index và chính sách thay đổi đồng thời ngay từ đầu. Kiểm thử với nhiều hàng có giá trị trùng nhau và database thực tế sẽ giúp phát hiện những lỗi lặp hoặc bỏ sót bản ghi trước khi chúng xuất hiện trong giao diện người dùng.

