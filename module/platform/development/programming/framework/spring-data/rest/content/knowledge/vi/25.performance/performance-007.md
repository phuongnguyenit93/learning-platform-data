# Thiết kế chỉ mục cho các truy vấn tìm kiếm được công bố trong Spring Data REST

Spring Data REST có thể công bố các query method của repository thành search endpoint. Client gọi những endpoint này bằng query parameter, còn Spring Data chuyển lời gọi thành truy vấn ở tầng persistence. Khi dữ liệu tăng lên, truy vấn tìm kiếm có thể chậm nếu database phải quét quá nhiều hàng, sắp xếp lượng dữ liệu lớn hoặc join qua các cột chưa có chỉ mục phù hợp.

Thiết kế index cần bắt đầu từ **truy vấn thực tế mà API công bố**: điều kiện lọc, thứ tự sắp xếp, join, phân trang và tần suất đọc/ghi. Spring Data REST không tự tạo index chỉ vì repository có một phương thức tìm kiếm. Chỉ mục phải được thiết kế và triển khai trong database bằng migration hoặc cơ chế quản lý schema của ứng dụng.

## 1. Search endpoint và truy vấn ở database

Giả sử ứng dụng có repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    List<Order> findByCustomerIdAndStatus(
        Long customerId,
        OrderStatus status
    );

    List<Order> findByStatusAndCreatedAtAfterOrderByCreatedAtDesc(
        OrderStatus status,
        Instant createdAt
    );
}
~~~

Spring Data REST có thể công bố các query method được export dưới search resource. Client khám phá các liên kết search và gọi endpoint tương ứng, ví dụ:

~~~http
GET /orders/search/findByStatus?status=PAID
~~~

Hoặc:

~~~http
GET /orders/search/findByCustomerIdAndStatus?customerId=42&status=PAID
~~~

Request cuối cùng được chuyển thành truy vấn database theo query method. Database có thể cần:

- Lọc theo một hoặc nhiều cột.
- Join với bảng liên quan.
- Sắp xếp theo một hoặc nhiều cột.
- Đếm kết quả để phục vụ pagination.
- Đọc các cột cần thiết để tạo representation.

Index nên phục vụ các thao tác thực sự xuất hiện trong query plan. Không nên tạo một index cho mọi thuộc tính của entity chỉ vì thuộc tính đó có thể được đưa vào query parameter.

## 2. Bắt đầu từ workload của API

Trước khi tạo index, hãy thống kê các query method và cách client sử dụng chúng. Với mỗi search endpoint, ghi nhận:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Predicate | Cột nào xuất hiện trong WHERE? |
| Join | Truy vấn có nối bảng hoặc lọc theo association không? |
| Sort | Client thường sắp xếp theo cột nào? |
| Pagination | Có dùng page, size và sort không? |
| Selectivity | Điều kiện lọc thường trả về ít hay nhiều hàng? |
| Tần suất | Endpoint được gọi thường xuyên đến mức nào? |
| Data volume | Bảng có bao nhiêu hàng và tăng nhanh ra sao? |
| Write rate | Insert/update/delete xảy ra thường xuyên không? |

Ví dụ một endpoint tìm đơn hàng theo trạng thái và thời điểm tạo:

~~~http
GET /orders/search/findByStatusAndCreatedAtAfterOrderByCreatedAtDesc
    ?status=PAID
    &createdAt=2026-11-01T00:00:00Z
    &page=0
    &size=20
~~~

Truy vấn có thể tương đương về ý nghĩa với:

~~~sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at > ?
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
~~~

Một index trên `status` và `created_at` có thể hỗ trợ lọc và thứ tự sắp xếp. Việc database có sử dụng index đó hay không còn phụ thuộc cardinality, statistics, dữ liệu thực tế, kiểu truy vấn và optimizer.

## 3. Index đơn cột cho điều kiện lọc phổ biến

Index đơn cột hữu ích khi một cột thường xuyên được dùng trong predicate có tính chọn lọc đủ tốt.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_status
    ON orders (status);
~~~

Index này có thể hỗ trợ:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

Một số trường hợp phù hợp:

- Tìm theo mã định danh hoặc mã nghiệp vụ có tính duy nhất.
- Lọc theo email hoặc username.
- Tìm theo foreign key.
- Lọc theo một thuộc tính có nhiều giá trị phân biệt và thường xuyên được truy vấn.

Index không đảm bảo truy vấn luôn nhanh hơn. Nếu điều kiện trả về phần lớn hàng trong bảng, database có thể chọn sequential scan hoặc table scan vì đọc tuần tự rẻ hơn nhiều lần truy cập index và table.

### Cột có độ chọn lọc thấp

Một cột Boolean như `active` chỉ có hai giá trị. Index đơn trên cột này thường ít hữu ích nếu phần lớn bản ghi có cùng giá trị.

Ví dụ:

~~~sql
CREATE INDEX idx_people_active
    ON people (active);
~~~

Index trên có thể không giúp nhiều nếu 95% người dùng đều active. Nếu ứng dụng chủ yếu tìm những người active theo một điều kiện khác, composite index hoặc partial index có thể phù hợp hơn, tùy database và workload.

## 4. Composite index cho nhiều điều kiện

Khi query method lọc theo nhiều cột, composite index có thể phục vụ các predicate cùng lúc.

Ví dụ:

~~~java
List<Order> findByCustomerIdAndStatus(
    Long customerId,
    OrderStatus status
);
~~~

Query tương ứng:

~~~sql
SELECT *
FROM orders
WHERE customer_id = ?
  AND status = ?;
~~~

Một index phù hợp có thể là:

~~~sql
CREATE INDEX idx_orders_customer_status
    ON orders (customer_id, status);
~~~

Thứ tự cột trong composite B-tree index có ý nghĩa. Với nhiều database, index thường được khai thác hiệu quả khi query có điều kiện trên các cột đứng đầu index. Vì vậy, cần xem xét các query khác cũng dùng cùng prefix.

Ví dụ index:

~~~sql
CREATE INDEX idx_orders_customer_status_created
    ON orders (customer_id, status, created_at);
~~~

có thể hỗ trợ các truy vấn lọc theo:

- `customer_id`.
- `customer_id` và `status`.
- `customer_id`, `status` và một khoảng `created_at`.

Nhưng nó không phải lựa chọn tối ưu mặc định cho truy vấn chỉ lọc theo `status`, vì `status` không phải cột đầu tiên.

### Chọn thứ tự cột

Một cách bắt đầu thường dùng là đặt các cột equality filter ở đầu index, sau đó cân nhắc cột range và sort. Tuy nhiên, thứ tự cuối cùng phải dựa trên workload:

- Cột nào thường xuất hiện cùng nhau?
- Có query chỉ dùng một phần prefix hay không?
- Giá trị có cardinality và phân bố ra sao?
- Query cần range condition hay order by?
- Database optimizer có thể tận dụng index theo cách nào?

Không áp dụng một quy tắc thứ tự cột máy móc cho mọi database. Hãy đọc execution plan và tài liệu index của hệ quản trị đang sử dụng.

## 5. Kết hợp filter với ORDER BY

Spring Data REST cho phép client yêu cầu sắp xếp qua query parameter `sort` nếu repository và cấu hình hỗ trợ.

Ví dụ:

~~~http
GET /orders/search/findByStatus
    ?status=PAID
    &sort=createdAt,desc
    &page=0
    &size=20
~~~

Query có thể tương đương:

~~~sql
SELECT *
FROM orders
WHERE status = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

Index:

~~~sql
CREATE INDEX idx_orders_status_created_desc
    ON orders (status, created_at DESC);
~~~

có thể giúp database tìm các hàng có status phù hợp và đọc theo thứ tự created_at. Khả năng tận dụng chiều ASC/DESC phụ thuộc database, cấu trúc index và thứ tự sắp xếp của query.

Nếu endpoint thường xuyên sort theo nhiều cột, hãy kiểm tra thứ tự sort thực tế. Một index phục vụ `ORDER BY created_at DESC` chưa chắc phục vụ tốt `ORDER BY total ASC, created_at DESC`.

Cần có một thứ tự phụ ổn định, thường là ID, khi phân trang qua tập dữ liệu có nhiều hàng trùng giá trị sort. Ví dụ:

~~~http
GET /orders?sort=createdAt,desc&sort=id,desc&page=0&size=20
~~~

Index có thể được điều chỉnh theo thứ tự đó nếu query này là workload quan trọng.

## 6. Index cho truy vấn range và thời gian

Các derived query có thể sử dụng toán tử so sánh như `After`, `Before`, `GreaterThan`, `LessThan`, `Between`.

Ví dụ:

~~~java
List<Order> findByCreatedAtBetween(
    Instant start,
    Instant end
);
~~~

Query:

~~~sql
SELECT *
FROM orders
WHERE created_at BETWEEN ? AND ?;
~~~

Index đơn trên `created_at` có thể hỗ trợ range scan:

~~~sql
CREATE INDEX idx_orders_created_at
    ON orders (created_at);
~~~

Nếu truy vấn còn lọc theo trạng thái:

~~~sql
SELECT *
FROM orders
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC;
~~~

có thể thử composite index:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at DESC);
~~~

Dùng khoảng nửa mở `[start, end)` thường thuận tiện cho khoảng thời gian liên tiếp, tránh trùng ranh giới giữa hai ngày hoặc hai khoảng.

Hãy thống nhất múi giờ và kiểu dữ liệu thời gian giữa ứng dụng và database. Index không khắc phục được lỗi chuyển đổi timezone hoặc predicate không đúng semantics.

## 7. Index cho association và foreign key

Một query method có thể lọc theo thuộc tính của entity liên quan hoặc truy cập association:

~~~java
List<Order> findByCustomerEmail(String email);
~~~

Tùy mapping, Spring Data có thể tạo join từ orders sang customers:

~~~sql
SELECT o.*
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE c.email = ?;
~~~

Các index có thể cần xem xét:

~~~sql
CREATE INDEX idx_customers_email
    ON customers (email);

CREATE INDEX idx_orders_customer_id
    ON orders (customer_id);
~~~

Index trên `customers.email` hỗ trợ tìm customer theo email; index trên `orders.customer_id` có thể hỗ trợ join và truy vấn các order của customer.

Nhiều database không tự động tạo index cho mọi foreign key. Hãy kiểm tra schema thực tế và quy định của database đang dùng.

Nếu email là duy nhất theo nghiệp vụ, có thể cân nhắc unique constraint/index để vừa bảo đảm tính duy nhất vừa hỗ trợ tìm kiếm. Không tạo unique index nếu dữ liệu hợp lệ có thể chứa email trùng.

## 8. Index cho truy vấn prefix, substring và full-text

Không phải mọi kiểu tìm kiếm chuỗi đều dùng B-tree index theo cùng một cách.

### Exact match

~~~sql
WHERE email = ?
~~~

B-tree index trên email thường phù hợp.

### Prefix search

~~~sql
WHERE last_name LIKE 'Ngu%'
~~~

Một số database và collation có thể tận dụng B-tree index cho prefix search. Khả năng này phụ thuộc collation, operator class và database.

### Substring search

~~~sql
WHERE description LIKE '%spring%'
~~~

B-tree index thông thường thường không hiệu quả vì pattern bắt đầu bằng wildcard. Nếu cần tìm substring thường xuyên, hãy xem xét full-text index, trigram index hoặc search engine phù hợp.

### Full-text search

Nếu API cần tìm từ hoặc cụm từ trong nội dung dài, dùng cơ chế full-text của database thay vì tạo nhiều index B-tree cho từng chuỗi. Ví dụ PostgreSQL có thể dùng tsvector và GIN index; MySQL có FULLTEXT index. Cú pháp và semantics khác nhau theo database.

Query method derived như `Containing`, `StartingWith` hoặc `EndingWith` có thể tạo predicate LIKE tương ứng. Hãy xem SQL thực tế được sinh ra trước khi chọn index.

## 9. Pagination và chi phí truy vấn đếm

Khi search endpoint trả về `Page<T>`, Spring Data thường thực hiện truy vấn lấy dữ liệu và có thể thực hiện thêm truy vấn count để xác định tổng số trang.

Ví dụ:

~~~java
Page<Order> findByStatus(
    OrderStatus status,
    Pageable pageable
);
~~~

Client:

~~~http
GET /orders/search/findByStatus?status=PAID&page=0&size=20
~~~

Database có thể cần thực hiện cả:

~~~sql
SELECT *
FROM orders
WHERE status = ?
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
~~~

và:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = ?;
~~~

Index phù hợp cho predicate có thể hỗ trợ cả truy vấn dữ liệu và count, nhưng không phải lúc nào count cũng rẻ trên bảng lớn.

OFFSET lớn có thể khiến database phải đọc và bỏ qua nhiều hàng trước khi trả page tiếp theo. Với workload cần đi sâu vào tập dữ liệu lớn, hãy cân nhắc keyset pagination hoặc cursor-based API phù hợp. Spring Data REST và repository abstraction cần được cấu hình hoặc mở rộng tương ứng; không giả định mọi endpoint mặc định hỗ trợ cursor pagination.

## 10. Dùng JPA @Index và migration database

JPA cho phép mô tả index trong mapping entity bằng `@Table(indexes = ...)`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(
    name = "orders",
    indexes = {
        @Index(
            name = "idx_orders_status_created",
            columnList = "status, created_at"
        )
    }
)
public class Order {
    // fields
}
~~~

`columnList` phải khớp tên cột database, không nhất thiết là tên field Java. Nếu dùng naming strategy, schema naming hoặc column mapping riêng, hãy kiểm tra tên cột được tạo thực tế.

Annotation JPA mô tả schema cho công cụ tạo schema khi cấu hình tương ứng được bật. Trong môi trường production, thường nên quản lý index bằng migration có kiểm soát, ví dụ Flyway hoặc Liquibase, để việc tạo, đổi và rollback index có thể review và triển khai nhất quán.

Ví dụ migration SQL:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at DESC);
~~~

Không nên dựa vào `ddl-auto=update` để quản lý toàn bộ thay đổi index production mà không kiểm tra. Hãy xác nhận migration chạy đúng database engine và phiên bản đang dùng.

## 11. Đọc execution plan trước khi thêm index

Đừng đánh giá index chỉ bằng tên hoặc suy luận từ query method. Hãy xem database thực sự thực thi query như thế nào.

Với PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE status = 'PAID'
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

Với MySQL, dùng `EXPLAIN` hoặc `EXPLAIN ANALYZE` tùy phiên bản hỗ trợ.

Các thông tin cần xem:

- Sequential scan/table scan hay index scan được chọn.
- Số hàng ước tính và số hàng thực tế.
- Số hàng database phải đọc để trả về số hàng yêu cầu.
- Sort có phải thực hiện riêng hay được index cung cấp thứ tự.
- Join strategy và index trên các cột join.
- Buffer/page read và thời gian thực thi.
- Chênh lệch giữa estimated rows và actual rows.

Chạy plan với dữ liệu và điều kiện đại diện cho production. Một query trả về rất ít hàng trong môi trường development có thể có plan khác khi bảng production lớn hơn nhiều.

`EXPLAIN ANALYZE` thực sự thực thi câu query. Với truy vấn có side effect hoặc hệ thống production nhạy cảm, hãy kiểm tra an toàn và chạy trên môi trường phù hợp.

## 12. Index làm tăng chi phí ghi và dung lượng

Index giúp đọc nhanh hơn trong một số workload, nhưng mỗi index cũng phải được cập nhật khi dữ liệu thay đổi.

Chi phí cần cân nhắc:

- INSERT phải thêm entry vào các index liên quan.
- UPDATE cột được index có thể phải cập nhật index entry.
- DELETE phải loại bỏ entry tương ứng.
- Index chiếm dung lượng lưu trữ và bộ nhớ cache.
- Nhiều index tương tự nhau làm tăng chi phí bảo trì và có thể không mang lại lợi ích đáng kể.

Không tạo composite index trùng lặp hoặc index đơn cột đã được một index khác hỗ trợ đầy đủ nếu workload không chứng minh cần thiết. Kiểm tra index usage và query performance trước khi giữ index lâu dài.

Với bảng có write rate cao, chỉ nên giữ những index phục vụ query quan trọng hoặc constraint cần thiết.

## 13. Partial index và covering index

Một số database hỗ trợ **partial index**, chỉ index những hàng thỏa điều kiện. Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_orders_open_created
    ON orders (created_at DESC)
    WHERE status = 'OPEN';
~~~

Index này có thể nhỏ hơn index toàn bảng nếu chỉ một phần dữ liệu có status OPEN và truy vấn thường xuyên tìm nhóm đó. Predicate của query cần tương thích với điều kiện partial index để optimizer có thể sử dụng.

**Covering index** chứa đủ cột cần thiết cho một query để database có thể phục vụ một phần hoặc toàn bộ truy vấn từ index mà không cần đọc thêm table row, tùy engine.

Ví dụ một query chỉ cần id và created_at:

~~~sql
SELECT id, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Một số database cho phép khai báo cột include:

~~~sql
CREATE INDEX idx_orders_status_created_cover
    ON orders (status, created_at DESC)
    INCLUDE (id);
~~~

Cú pháp INCLUDE không có ở mọi database. Không thêm nhiều cột vào index chỉ để cố tạo covering index; index lớn hơn sẽ tốn storage và chi phí ghi.

## 14. Kiểm soát sort mà client được phép yêu cầu

Spring Data REST có thể cho client chọn sort qua query parameter. Nếu client được phép sort theo mọi thuộc tính, số tổ hợp query tăng lên và khó thiết kế index hiệu quả.

Ví dụ:

~~~http
GET /orders?sort=createdAt,desc&page=0&size=20
~~~

Ứng dụng nên xác định những sort order nào thực sự được hỗ trợ và có nhu cầu. Có thể dùng repository/service hoặc custom controller để giới hạn sort theo hợp đồng API.

Không tạo index cho mọi tổ hợp sort tùy ý. Hãy ưu tiên các trường hợp phổ biến, ổn định và có tác động hiệu năng đáng kể.

Đối với sort kết hợp filter, index cần được đánh giá trên toàn query. Một index chỉ phục vụ cột sort nhưng không hỗ trợ predicate có thể vẫn buộc database đọc nhiều hàng.

## 15. Quy trình thiết kế index cho search endpoint

1. Liệt kê query method được export và các request thực tế từ client.
2. Xác định predicate, join, sort, pagination và count query.
3. Thu thập số liệu về cardinality, phân bố dữ liệu, tần suất đọc và write rate.
4. Chạy execution plan với dữ liệu đại diện.
5. Đề xuất index đơn cột hoặc composite index theo query workload.
6. Kiểm tra thứ tự cột, range predicate, sort order và leftmost prefix.
7. Triển khai index bằng migration có review.
8. Đo lại execution plan, latency và chi phí ghi sau khi index được tạo.
9. Theo dõi index usage và loại bỏ index dư thừa bằng migration riêng khi có bằng chứng.
10. Kiểm tra pagination, association join và các query method khác bị ảnh hưởng bởi thay đổi.

## 16. Những điểm cần ghi nhớ

- Spring Data REST công bố query method thành search endpoint nhưng không tự tạo index cho database.
- Thiết kế index từ SQL và workload thực tế: WHERE, JOIN, ORDER BY, pagination và count.
- Composite index có thứ tự cột quan trọng; hãy xem query prefix và predicate thực tế.
- Equality filter thường được cân nhắc trước range/sort column, nhưng quyết định cuối cùng phải dựa trên execution plan.
- Index foreign key và cột join có thể giúp truy vấn association.
- B-tree phù hợp với nhiều exact match và range query; substring/full-text cần cơ chế index khác.
- Pagination có thể phát sinh count query; OFFSET lớn có thể tốn kém.
- JPA @Index mô tả schema, còn migration là cách kiểm soát thay đổi index production.
- Index làm tăng chi phí ghi và dung lượng; tránh tạo index trùng hoặc không được sử dụng.
- Dùng EXPLAIN/EXPLAIN ANALYZE và số liệu thực tế để xác nhận lợi ích.

## Nguồn tham khảo

- [Spring Data REST — Repository resources and query method resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Jakarta Persistence — @Index API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/index)
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html)
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)
- [MySQL — Optimization and Indexes](https://dev.mysql.com/doc/refman/8.4/en/optimization-indexes.html)
