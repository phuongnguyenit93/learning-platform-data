# Tối ưu count query và phân trang sâu

Khi một màn hình danh sách cần hiển thị dữ liệu theo từng trang, ứng dụng thường phải giải quyết hai bài toán khác nhau:

- **Đếm tổng số kết quả:** để hiển thị tổng bản ghi, tổng số trang hoặc thông tin điều hướng chính xác.
- **Lấy một đoạn kết quả:** để chỉ tải một số bản ghi cần hiển thị thay vì đọc toàn bộ dữ liệu.

Trong Spring Data JDBC, kiểu trả về **Page<T>** cung cấp tổng số phần tử và tổng số trang, nên hạ tầng có thể thực hiện thêm count query. **Slice<T>** chỉ cần biết còn trang tiếp theo hay không; Spring Data JDBC lấy thêm một hàng ngoài page size để xác định **hasNext**. Trả về **List<T>** cùng **Pageable** cũng có thể lấy đúng đoạn dữ liệu mà không tạo metadata tổng số.

Khi offset ngày càng lớn, truy vấn kiểu LIMIT ... OFFSET ... có thể phải đi qua rất nhiều hàng trước khi trả về đoạn nhỏ ở cuối. Với luồng duyệt dữ liệu lớn theo thứ tự ổn định, **keyset pagination** (seek pagination) dùng giá trị của bản ghi cuối trang trước làm điểm bắt đầu cho trang tiếp theo. Database có thể tìm theo điều kiện khóa thay vì bỏ qua hàng nghìn kết quả.

Bài học này giải thích chi phí của count query, cách chọn Page/Slice/List, cách thiết kế count query đúng, nguyên nhân phân trang sâu chậm và cách chuyển sang keyset pagination với Spring Data JDBC.

## 1. Hai phần việc của một trang dữ liệu

Giả sử màn hình quản trị hiển thị các đơn hàng có trạng thái PAID, sắp xếp theo thời gian tạo mới nhất. Mỗi trang có 20 đơn hàng.

Một response dạng Page<Order> thường cần:

1. Truy vấn lấy 20 đơn hàng của trang hiện tại.
2. Truy vấn đếm tổng số đơn hàng thỏa điều kiện để tính tổng số phần tử và tổng số trang.

Ví dụ SQL khái niệm:

~~~sql
SELECT id, order_number, created_at, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

Truy vấn đếm:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Kết quả có thể là:

~~~text
content       = 20 orders
totalElements = 12,480
totalPages    = 624
number        = 0
size          = 20
hasNext       = true
~~~

Hai truy vấn có mục tiêu khác nhau. Truy vấn nội dung chỉ cần tìm một đoạn kết quả. Count query cần xác định số lượng tất cả các hàng phù hợp với điều kiện.

Nếu bảng có hàng triệu bản ghi, truy vấn lấy 20 hàng đầu có thể rất nhanh nhờ index, trong khi count query vẫn phải đọc nhiều entry để xác định số lượng phù hợp. Vì vậy, tối ưu truy vấn nội dung mà bỏ qua count query có thể chưa giải quyết được nút thắt thực tế.

## 2. Chọn Page, Slice hay List?

Spring Data JDBC hỗ trợ các kiểu kết quả phân trang thường dùng trong repository query methods.

| Kiểu trả về | Có dữ liệu trang | Có tổng số phần tử | Cách xác định trang tiếp |
| --- | --- | --- | --- |
| Page<T> | Có | Có | Dựa trên tổng số và thông tin trang |
| Slice<T> | Có | Không | hasNext |
| List<T> với Pageable | Có | Không | Ứng dụng tự điều phối |
| Stream<T> | Luồng dữ liệu | Không | Đọc tuần tự và đóng stream |

### 2.1. Page<T>: khi giao diện thật sự cần tổng số

Ví dụ repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.PagingAndSortingRepository;

public interface OrderRepository
        extends PagingAndSortingRepository<Order, Long> {

    Page<Order> findByStatus(String status, Pageable pageable);
}
~~~

Service:

~~~java
public Page<Order> findPaidOrders(int page, int size) {
    Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")
            )
    );

    return orderRepository.findByStatus("PAID", pageable);
}
~~~

Page<T> phù hợp khi giao diện cần hiển thị:

- Tổng số bản ghi.
- Tổng số trang.
- “Trang 3 trên 24”.
- Cho phép chuyển trực tiếp đến một số trang cụ thể.
- Báo cáo hoặc màn hình cần con số chính xác.

Đổi lại, count query có thể được thực hiện ngoài truy vấn lấy nội dung. Tài liệu Spring Data JDBC mô tả rằng query trả về Page có thể chạy count query để xác định tổng số; hạ tầng có thể tránh count trong một số trường hợp mà số hàng trả về đã đủ để suy ra tổng.

Đừng chọn Page theo thói quen nếu UI không sử dụng tổng số. Một con số tổng chính xác có thể có chi phí đáng kể.

### 2.2. Slice<T>: chỉ cần biết còn dữ liệu hay không

Nếu giao diện chỉ có nút “Tiếp theo”, không cần tổng số trang:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface OrderRepository
        extends PagingAndSortingRepository<Order, Long> {

    Slice<Order> findSliceByStatus(
            String status,
            Pageable pageable
    );
}
~~~

Spring Data JDBC lấy tối đa pageSize + 1 hàng. Với page size 20:

- Lấy tối đa 21 hàng.
- Nếu có 21 hàng, trả 20 hàng đầu và đặt hasNext = true.
- Nếu có tối đa 20 hàng, không còn trang tiếp theo.

Không cần đếm toàn bộ kết quả để trả lời câu hỏi “có trang tiếp theo không?”.

Slice vẫn sử dụng offset nếu đi cùng Pageable. Do đó, nó loại bỏ chi phí count query nhưng **không tự giải quyết chi phí của offset sâu**.

### 2.3. List<T> với Pageable: chỉ cần đoạn dữ liệu

Nếu ứng dụng không cần cả tổng số lẫn cờ hasNext, có thể trả về List:

~~~java
public interface OrderRepository
        extends PagingAndSortingRepository<Order, Long> {

    List<Order> findAllByStatus(
            String status,
            Pageable pageable
    );
}
~~~

Kiểu này chỉ tạo danh sách nội dung trang, không tạo metadata Page và không cần count query để dựng metadata đó.

Ứng dụng phải tự quyết định cách hiển thị điều hướng. Nếu muốn biết còn dữ liệu, hãy lấy thêm một hàng hoặc dùng Slice.

### 2.4. Stream<T>: xử lý tuần tự lượng dữ liệu lớn

Với query method trả về Stream<T>, Spring Data JDBC có thể đưa kết quả ra từng phần khi database trả dữ liệu. Điều này giúp giảm nhu cầu giữ toàn bộ kết quả trong bộ nhớ.

~~~java
@Query("SELECT * FROM orders WHERE status = :status")
Stream<Order> streamByStatus(String status);
~~~

Stream giữ connection database mở trong thời gian sử dụng. Phải đóng stream, tốt nhất bằng try-with-resources:

~~~java
try (Stream<Order> orders =
             repository.streamByStatus("PAID")) {

    orders.forEach(this::process);
}
~~~

Stream phù hợp cho batch processing tuần tự. Nó không phải cơ chế điều hướng trang cho giao diện và không loại bỏ chi phí của một query cần quét nhiều dữ liệu.

## 3. Count query thực sự làm gì?

Count query trả về số hàng phù hợp với điều kiện. Câu SQL đơn giản nhất:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Các dạng count phổ biến:

| Biểu thức | Ý nghĩa |
| --- | --- |
| COUNT(*) | Đếm tất cả hàng trong tập kết quả. |
| COUNT(id) | Đếm hàng có id khác NULL. |
| COUNT(DISTINCT customer_id) | Đếm số khách hàng duy nhất xuất hiện. |

Nếu id là primary key NOT NULL, COUNT(*) và COUNT(id) thường cho cùng kết quả. COUNT(column) bỏ qua các giá trị NULL của cột đó; không thay nó bằng COUNT(*) một cách tùy tiện.

### 3.1. Count query không cần ORDER BY

Sắp xếp không ảnh hưởng đến tổng số kết quả. Truy vấn đếm nên loại bỏ phần sắp xếp:

~~~sql
-- Không cần thiết cho count
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC;
~~~

Dạng nên dùng:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Không đưa LIMIT và OFFSET của trang vào count query nếu mục tiêu là đếm toàn bộ tập kết quả.

### 3.2. Count query phải giữ nguyên điều kiện lọc

Truy vấn nội dung:

~~~sql
SELECT id, order_number, total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

Count query tương ứng:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID'
  AND created_at >= :fromTime
  AND created_at < :toTime;
~~~

Nếu count query quên một điều kiện, ví dụ created_at < :toTime, tổng số hiển thị sẽ không khớp với tập dữ liệu mà người dùng đang duyệt.

Khi query có nhiều bộ lọc tùy chọn, hãy dùng chung logic tạo điều kiện cho truy vấn nội dung và count query để tránh hai câu SQL dần lệch nhau.

### 3.3. Khi query JOIN làm nhân bản hàng

Giả sử một đơn hàng có nhiều dòng hàng. JOIN orders với order_items sẽ tạo nhiều hàng cho một đơn hàng:

~~~sql
SELECT o.id, o.order_number, i.product_id
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE o.status = 'PAID';
~~~

Nếu một đơn hàng có 4 dòng hàng, kết quả JOIN có thể chứa 4 hàng cùng o.id. Khi muốn đếm số đơn hàng, COUNT(*) sẽ đếm dòng JOIN chứ không đếm aggregate root.

Dùng:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE o.status = 'PAID';
~~~

Nếu mục tiêu là đếm số dòng hàng, COUNT(*) lại có thể là biểu thức đúng. Count phải phản ánh chính xác đơn vị mà API đang phân trang: đơn hàng, khách hàng, sản phẩm hay dòng kết quả JOIN.

### 3.4. Count query có GROUP BY hoặc DISTINCT

Khi truy vấn trả về nhóm hoặc kết quả distinct, không thể luôn thay phần SELECT bằng COUNT(*) trên bảng gốc.

Ví dụ truy vấn trả về mỗi khách hàng một dòng:

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
~~~

Muốn đếm số nhóm khách hàng có doanh thu, có thể đếm tập kết quả con:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT customer_id
    FROM orders
    GROUP BY customer_id
) grouped_customers;
~~~

Tương tự, khi query có DISTINCT, set operation hoặc cấu trúc phức tạp, hãy đếm chính tập kết quả mà người dùng nhìn thấy.

## 4. Count query trong Spring Data JDBC

### 4.1. Repository derived query

Với derived query trả về Page<T>, Spring Data JDBC có thể suy ra truy vấn đếm từ điều kiện của query method:

~~~java
public interface ProductRepository
        extends PagingAndSortingRepository<Product, Long> {

    Page<Product> findByCategoryId(
            Long categoryId,
            Pageable pageable
    );

    Slice<Product> findSliceByCategoryId(
            Long categoryId,
            Pageable pageable
    );
}
~~~

Dùng Page khi cần tổng số. Dùng Slice khi chỉ cần biết còn dữ liệu. Cả hai method đều dùng điều kiện categoryId, nhưng metadata trả về khác nhau.

### 4.2. SQL tùy chỉnh bằng @Query

Spring Data JDBC có một giới hạn quan trọng: string-based query khai báo bằng @Query không hỗ trợ tự động nhận Pageable, Sort, PageRequest hoặc Limit làm tham số để framework viết lại SQL.

Ví dụ sau không phải cách phân trang hợp lệ cho string-based query trong Spring Data JDBC:

~~~java
@Query("SELECT * FROM orders WHERE status = :status")
Page<Order> findByStatus(
        String status,
        Pageable pageable
);
~~~

Nếu SQL tùy chỉnh cần phân trang, hãy viết rõ phần giới hạn và bind tham số trong SQL, hoặc triển khai custom repository fragment để quản lý cả truy vấn nội dung lẫn count query.

Ví dụ SQL:

~~~sql
SELECT id, order_number, created_at, total_amount
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
~~~

Count query:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = :status;
~~~

Cách dùng LIMIT và OFFSET trong SQL tùy chỉnh cần được kiểm thử với database đích. Nếu ứng dụng hỗ trợ nhiều dialect, không nên mặc định mọi cú pháp vendor-specific đều portable.

### 4.3. Dùng JdbcAggregateTemplate để tạo Page thủ công

JdbcAggregateTemplate cung cấp findAll(Query, Class) và count(Query, Class). Có thể dùng một query cơ sở chỉ chứa điều kiện lọc, sau đó tạo query nội dung với Pageable:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final JdbcAggregateTemplate template;

    public ProductSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public Page<Product> findActiveProducts(Pageable pageable) {
        Query filter = Query.query(
                Criteria.where("status").is("ACTIVE")
        );

        List<Product> content = template.findAll(
                filter.with(pageable),
                Product.class
        );

        long total = template.count(filter, Product.class);

        return new PageImpl<>(content, pageable, total);
    }
}
~~~

Ở đây:

- filter chỉ chứa điều kiện nghiệp vụ.
- filter.with(pageable) tạo query lấy nội dung theo offset, limit và sort.
- template.count(filter, Product.class) đếm toàn bộ aggregate phù hợp điều kiện.
- PageImpl kết hợp nội dung, thông tin trang và tổng số.

Đừng truyền query đã có offset/limit vào count nếu mục tiêu là tổng số của toàn bộ tập kết quả. Giữ query cơ sở chỉ chứa filter giúp hai phần rõ ràng.

Trong API hiện tại, overload findAll(Query, Class, Pageable) của JdbcAggregateOperations/JdbcAggregateTemplate đã được đánh dấu deprecated for removal. Cách trên dùng Query.with(Pageable) cùng findAll(Query, Class) và tự tạo Page.

### 4.4. Count query tùy chỉnh qua repository fragment

Với truy vấn phức tạp, một custom repository fragment giúp kiểm soát SQL rõ hơn:

~~~java
public interface OrderSearchRepository {
    Page<OrderSummary> searchPaidOrders(
            Instant fromTime,
            Instant toTime,
            Pageable pageable
    );
}
~~~

Implementation có thể dùng NamedParameterJdbcTemplate:

~~~java
@Repository
public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSearchRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public Page<OrderSummary> searchPaidOrders(
            Instant fromTime,
            Instant toTime,
            Pageable pageable
    ) {
        String from = """
                FROM orders
                WHERE status = :status
                  AND created_at >= :fromTime
                  AND created_at < :toTime
                """;

        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("status", "PAID")
                        .addValue("fromTime", fromTime)
                        .addValue("toTime", toTime);

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) " + from,
                parameters,
                Long.class
        );

        parameters
                .addValue("limit", pageable.getPageSize())
                .addValue("offset", pageable.getOffset());

        List<OrderSummary> content = jdbc.query(
                """
                SELECT id, order_number, created_at, total_amount
                """ + from + """
                ORDER BY created_at DESC, id DESC
                LIMIT :limit OFFSET :offset
                """,
                parameters,
                (rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getTimestamp("created_at").toInstant(),
                        rs.getBigDecimal("total_amount")
                )
        );

        return new PageImpl<>(
                content,
                pageable,
                count == null ? 0 : count
        );
    }
}
~~~

Đây là ví dụ minh họa cho một database hỗ trợ cú pháp LIMIT/OFFSET. Trong ứng dụng nhiều database, hãy dùng dialect phù hợp hoặc tách SQL theo vendor khi cần.

Đặc biệt, nếu cho phép client chọn sort động, không nối trực tiếp tên cột từ request vào SQL. Hãy ánh xạ sort property qua danh sách cột cho phép và hướng ASC/DESC hợp lệ.

## 5. Vì sao count query có thể chậm?

Count query không trả nhiều dữ liệu, nhưng điều đó không đồng nghĩa nó luôn rẻ.

Database phải xác định có bao nhiêu hàng thỏa điều kiện. Tùy query và execution plan, nó có thể:

- Quét toàn bộ bảng.
- Quét một index.
- Đọc nhiều index entry rồi kiểm tra hàng tương ứng.
- Thực hiện JOIN hoặc lọc phức tạp.
- Đếm các hàng distinct.
- Tính các nhóm sau GROUP BY.

Ví dụ:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID'
  AND created_at >= :fromTime;
~~~

Nếu không có index hữu ích, database có thể phải đọc rất nhiều hàng để xác định kết quả.

### 5.1. Index hỗ trợ count query

Với điều kiện lọc theo status và thời gian:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders(status, created_at);
~~~

Index này có thể hỗ trợ tìm các hàng phù hợp với điều kiện. Khả năng sử dụng index còn phụ thuộc độ chọn lọc, phân bố dữ liệu, thống kê và optimizer.

Không phải cứ thêm index là count sẽ nhanh. Nếu phần lớn bảng đều có status = 'PAID', optimizer có thể chọn scan khác. Index cũng làm tăng chi phí ghi và dung lượng lưu trữ.

### 5.2. Index covering

Nếu tất cả cột cần thiết cho một truy vấn có trong index, một số database có thể đếm hoặc lọc từ index mà không phải đọc toàn bộ row data. Cơ chế cụ thể phụ thuộc database engine, MVCC và execution plan.

Không nên giả định COUNT(*) luôn được trả về trong thời gian hằng số. Hãy đo trên database thật và dữ liệu gần production.

### 5.3. Tối ưu điều kiện lọc trước khi tối ưu COUNT

Một số điều chỉnh thường hữu ích:

- Đảm bảo điều kiện WHERE có thể dùng index.
- Tránh function không cần thiết trên cột được lọc nếu làm mất khả năng dùng index.
- Chỉ JOIN bảng thực sự cần cho điều kiện.
- Đếm đúng đơn vị dữ liệu.
- Tránh DISTINCT nếu query không cần.
- Không đưa ORDER BY vào count.
- Dùng điều kiện thời gian theo khoảng nửa mở, ví dụ created_at >= :from và created_at < :to.

Ví dụ, thay vì:

~~~sql
WHERE DATE(created_at) = :day
~~~

có thể dùng khoảng thời gian:

~~~sql
WHERE created_at >= :dayStart
  AND created_at < :nextDayStart
~~~

Cách thứ hai thường dễ tận dụng index trên created_at hơn, tùy database và biểu thức thực tế.

## 6. Khi không cần tổng số chính xác

Không phải màn hình nào cũng cần con số tổng chính xác.

Ví dụ một feed hoạt động chỉ có:

- Danh sách 20 sự kiện mới nhất.
- Nút “Xem thêm”.
- Không hiển thị “có 2.345.789 sự kiện”.

Trong trường hợp đó, Slice hoặc cursor pagination thường phù hợp hơn Page.

### 6.1. Dùng Slice để bỏ count query

~~~java
Slice<Event> findSliceByCategory(
        String category,
        Pageable pageable
);
~~~

Ứng dụng chỉ cần:

~~~java
Slice<Event> slice = repository.findSliceByCategory(
        "SYSTEM",
        PageRequest.of(
                0,
                50,
                Sort.by(
                        Sort.Order.desc("occurredAt"),
                        Sort.Order.desc("id")
                )
        )
);

boolean hasMore = slice.hasNext();
~~~

Không cần biết toàn bộ số sự kiện để hiển thị nút “Xem thêm”.

### 6.2. Dùng exists khi chỉ cần biết có hay không

Nếu chỉ cần kiểm tra có bản ghi phù hợp hay không, đừng gọi count rồi so sánh với 0.

Với JdbcAggregateTemplate:

~~~java
Query filter = Query.query(
        Criteria.where("status").is("PENDING")
);

boolean hasPendingOrders =
        template.exists(filter, Order.class);
~~~

exists diễn đạt đúng mục tiêu và cho phép persistence layer sử dụng chiến lược kiểm tra tồn tại phù hợp.

### 6.3. Cache tổng số

Nếu màn hình thật sự cần tổng số nhưng count query đắt và không cần cập nhật tức thời, có thể cache kết quả theo filter hoặc lưu summary counter.

Ví dụ:

- Cache số đơn hàng theo trạng thái.
- Bảng thống kê số sản phẩm theo danh mục.
- Materialized view cho báo cáo.
- Bộ đếm được cập nhật theo event hoặc batch.

Cần xác định:

- TTL hoặc quy tắc invalidation.
- Chấp nhận độ trễ bao lâu.
- Cách xử lý cập nhật đồng thời.
- Cách rebuild khi cache hoặc counter sai.
- Filter nào được hỗ trợ.

Không dùng một counter tổng duy nhất cho các query có filter tùy ý. Counter phải tương ứng với phạm vi dữ liệu mà API cần đếm.

### 6.4. Approximate count

Một số hệ quản trị cung cấp thống kê ước lượng số hàng. Có thể dùng cho dashboard hoặc công cụ quản trị nếu người dùng chấp nhận con số gần đúng.

Không dùng số ước lượng cho nghiệp vụ yêu cầu chính xác, ví dụ số lượng hóa đơn phải thanh toán hoặc số lượng quyền được cấp.

## 7. Vì sao OFFSET sâu chậm?

Giả sử người dùng yêu cầu trang 5.000, mỗi trang 20 hàng:

~~~sql
SELECT id, order_number, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 99980;
~~~

Database phải tìm vị trí sau 99.980 kết quả phù hợp rồi mới trả 20 hàng tiếp theo. Dù index hỗ trợ thứ tự, engine vẫn thường phải đi qua các entry bị bỏ qua.

Độ trễ có thể tăng theo offset:

~~~text
Page 0:       OFFSET 0        -> lấy 20 hàng
Page 10:      OFFSET 200      -> bỏ qua 200 hàng
Page 100:     OFFSET 2,000    -> bỏ qua 2.000 hàng
Page 5,000:   OFFSET 99,980   -> bỏ qua gần 100.000 hàng
Page 50,000:  OFFSET 999,980  -> bỏ qua gần 1 triệu hàng
~~~

Đây là lý do offset pagination phù hợp với các trang đầu và điều hướng ngẫu nhiên trong tập dữ liệu vừa phải, nhưng không phải lựa chọn tốt cho việc duyệt hàng triệu bản ghi.

### 7.1. Index không xóa được chi phí skip

Index có thể tránh việc sort toàn bộ tập kết quả hoặc giảm số lần đọc row, nhưng offset lớn vẫn yêu cầu database tiến qua nhiều entry trước vị trí cần trả về.

Vì vậy, thêm index có thể cải thiện truy vấn offset nhưng không loại bỏ bản chất của thao tác bỏ qua N kết quả.

### 7.2. Offset pagination có thể bị trùng hoặc thiếu dữ liệu

Giả sử trang đầu có các đơn hàng:

~~~text
A, B, C, D, E
~~~

Trang thứ hai dùng OFFSET 5. Trước khi người dùng tải trang hai, một đơn hàng mới được chèn lên đầu:

~~~text
NEW, A, B, C, D, E, F, G...
~~~

Trang thứ hai bắt đầu sau 5 hàng của tập kết quả mới, nên có thể trả về E lần nữa. Tùy thay đổi dữ liệu, một bản ghi cũng có thể bị bỏ qua.

Một thứ tự ổn định giúp kết quả có thứ tự xác định trong một snapshot, nhưng không bảo đảm các request ở các thời điểm khác nhau nhìn thấy cùng một tập dữ liệu.

### 7.3. Luôn dùng sort có tie-breaker duy nhất

Không nên chỉ sắp xếp theo một cột có thể trùng:

~~~sql
ORDER BY created_at DESC
~~~

Nếu nhiều đơn hàng có cùng created_at, thứ tự giữa chúng có thể thay đổi.

Dùng khóa phụ duy nhất:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

id giúp xác định thứ tự duy nhất giữa các hàng có cùng timestamp.

Quy tắc này hữu ích cho cả offset pagination và keyset pagination.

## 8. Keyset pagination là gì?

Keyset pagination (còn gọi là seek pagination) dùng giá trị sắp xếp của bản ghi cuối cùng ở trang hiện tại làm cursor cho truy vấn tiếp theo.

Thay vì nói:

> Bỏ qua 100.000 hàng rồi lấy 20 hàng tiếp theo.

Ứng dụng nói:

> Lấy 20 hàng đứng sau đơn hàng có created_at và id bằng các giá trị cursor này.

Giả sử thứ tự:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Bản ghi cuối trang hiện tại có:

~~~text
created_at = 2026-11-10T09:30:00Z
id         = 8120
~~~

Trang tiếp theo dùng điều kiện:

~~~sql
WHERE created_at < :cursorCreatedAt
   OR (
        created_at = :cursorCreatedAt
        AND id < :cursorId
   )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Database tìm các hàng có khóa nhỏ hơn cursor theo thứ tự đã định, thay vì phải đếm và bỏ qua toàn bộ hàng phía trước.

### 8.1. Ví dụ so sánh SQL

Offset:

~~~sql
SELECT id, created_at, order_number
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
~~~

Keyset:

~~~sql
SELECT id, created_at, order_number
FROM orders
WHERE status = 'PAID'
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

Điều kiện cursor cho phép database dùng index phù hợp để tìm vị trí tiếp theo. Hiệu quả thực tế phụ thuộc index, bộ lọc và execution plan.

### 8.2. Vì sao phải thêm ID vào cursor?

Nếu chỉ dùng created_at < :cursorCreatedAt, những hàng có cùng timestamp với bản ghi cuối trang có thể bị bỏ sót.

Ví dụ:

~~~text
created_at              id
----------------------  ----
2026-11-10 09:30:00     8122
2026-11-10 09:30:00     8121
2026-11-10 09:30:00     8120  <- cuối trang
2026-11-10 09:29:59     8119
~~~

Điều kiện đúng phải bao gồm cả khóa phụ:

~~~sql
created_at < :cursorCreatedAt
OR (
    created_at = :cursorCreatedAt
    AND id < :cursorId
)
~~~

Như vậy, các hàng có cùng timestamp nhưng ID nhỏ hơn vẫn được lấy ở trang tiếp theo.

## 9. Thiết kế cursor đúng cách

Cursor cần chứa tất cả giá trị cần để xác định vị trí tiếp tục.

Với thứ tự created_at DESC, id DESC, cursor có thể gồm:

~~~json
{
  "createdAt": "2026-11-10T09:30:00Z",
  "id": 8120
}
~~~

Trong API thực tế, có thể đóng gói thành chuỗi opaque token. Client chỉ gửi lại token nhận được, không tự sửa giá trị cursor.

### 9.1. Cursor phải gắn với filter và sort

Một cursor tạo ra cho danh sách status = PAID không nên được sử dụng cho danh sách status = CANCELLED.

Cursor có thể chứa:

- Giá trị khóa cuối cùng.
- Phiên bản định dạng cursor.
- Bộ lọc hoặc fingerprint của bộ lọc.
- Sort order.
- ID của tenant hoặc phạm vi dữ liệu nếu cần.
- High-water mark nếu API cần giới hạn một snapshot logic.

Server phải xác thực cursor và bảo đảm các điều kiện truy vấn vẫn giống với request ban đầu.

### 9.2. Cursor nên được ký

Nếu token chứa các giá trị mà client không được phép thay đổi, có thể ký token bằng HMAC hoặc cơ chế tương đương.

Base64 chỉ mã hóa biểu diễn, không bảo đảm tính toàn vẹn và không che giấu dữ liệu. Chữ ký giúp phát hiện token đã bị chỉnh sửa; nếu cursor chứa dữ liệu nhạy cảm, cần cân nhắc mã hóa riêng.

### 9.3. Cursor không nhất thiết là ID duy nhất

ID đơn lẻ chỉ đủ khi thứ tự chính là ID và thứ tự đó đáp ứng nghiệp vụ.

Nếu sort theo nhiều trường, cursor phải chứa toàn bộ các trường sort cùng tie-breaker duy nhất.

Ví dụ:

~~~text
ORDER BY priority DESC, created_at ASC, id ASC
~~~

Cursor cần priority, created_at và id. Điều kiện tiếp theo phải phản ánh đúng hướng sort của từng trường. Không thể dùng một điều kiện < id đơn giản cho thứ tự nhiều cột.

### 9.4. Tránh keyset trên cột nullable

So sánh với NULL trong SQL có semantics riêng. Điều kiện kiểu:

~~~sql
created_at < :cursorCreatedAt
~~~

không bao gồm hàng có created_at IS NULL.

Nếu trường sort có thể NULL, cần xác định quy tắc NULLS FIRST/LAST và viết điều kiện cursor phù hợp. Với keyset đơn giản, ưu tiên sort key NOT NULL và ổn định.

### 9.5. Không dùng cột sort thay đổi liên tục

Nếu một hàng đổi created_at, priority hoặc trường sort trong lúc người dùng đang duyệt, hàng đó có thể di chuyển qua vị trí cursor.

Điều này có thể dẫn đến bản ghi xuất hiện lại hoặc không xuất hiện trong luồng duyệt. Nên chọn sort key bất biến hoặc gần như bất biến, ví dụ thời điểm tạo và ID.

Keyset giúp giảm vấn đề dịch chuyển do insert trước cursor, nhưng không tự tạo snapshot nhất quán xuyên nhiều HTTP request.

## 10. Triển khai keyset bằng custom repository trong Spring Data JDBC

Spring Data JDBC cho phép dùng custom repository fragment và NamedParameterJdbcTemplate để thực hiện SQL seek phù hợp với use case.

Ví dụ DTO:

~~~java
import java.time.Instant;

public record OrderSummary(
        Long id,
        String orderNumber,
        Instant createdAt
) {
}

public record OrderCursor(
        Instant createdAt,
        Long id
) {
}

public record CursorPage<T>(
        List<T> content,
        OrderCursor nextCursor,
        boolean hasNext
) {
}
~~~

Interface:

~~~java
public interface OrderScrollRepository {
    CursorPage<OrderSummary> findNextPaidOrders(
            OrderCursor cursor,
            int pageSize
    );
}
~~~

Implementation:

~~~java
@Repository
public class OrderScrollRepositoryImpl
        implements OrderScrollRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderScrollRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public CursorPage<OrderSummary> findNextPaidOrders(
            OrderCursor cursor,
            int pageSize
    ) {
        if (pageSize < 1 || pageSize > 200) {
            throw new IllegalArgumentException(
                    "pageSize must be between 1 and 200"
            );
        }

        String sql;
        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("status", "PAID")
                        .addValue("limit", pageSize + 1);

        if (cursor == null) {
            sql = """
                    SELECT id, order_number, created_at
                    FROM orders
                    WHERE status = :status
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """;
        } else {
            sql = """
                    SELECT id, order_number, created_at
                    FROM orders
                    WHERE status = :status
                      AND (
                            created_at < :cursorCreatedAt
                            OR (
                                created_at = :cursorCreatedAt
                                AND id < :cursorId
                            )
                      )
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """;

            parameters
                    .addValue("cursorCreatedAt", cursor.createdAt())
                    .addValue("cursorId", cursor.id());
        }

        List<OrderSummary> fetched = jdbc.query(
                sql,
                parameters,
                (rs, rowNum) -> new OrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_number"),
                        rs.getTimestamp("created_at").toInstant()
                )
        );

        boolean hasNext = fetched.size() > pageSize;

        List<OrderSummary> content = hasNext
                ? List.copyOf(fetched.subList(0, pageSize))
                : fetched;

        OrderCursor nextCursor = null;

        if (hasNext && !content.isEmpty()) {
            OrderSummary last = content.get(content.size() - 1);

            nextCursor = new OrderCursor(
                    last.createdAt(),
                    last.id()
            );
        }

        return new CursorPage<>(
                content,
                nextCursor,
                hasNext
        );
    }
}
~~~

Điểm quan trọng:

1. Request đầu tiên không có cursor.
2. Mỗi truy vấn lấy pageSize + 1 hàng.
3. Hàng dư dùng để xác định hasNext.
4. Chỉ trả pageSize hàng cho client.
5. Cursor tiếp theo lấy từ hàng cuối cùng thực sự được trả về.
6. Request tiếp theo gửi cursor đó để tìm phần kết quả sau nó.

Trong ví dụ, thứ tự và điều kiện cursor đều là DESC. Nếu thay đổi sort direction, phải thay đổi toán tử so sánh tương ứng.

Đây là custom SQL cho bảng orders và DTO, không phải thao tác tải toàn bộ aggregate bằng repository. Nếu cần tải aggregate root đầy đủ cùng các thành phần được sở hữu, có thể dùng JdbcAggregateTemplate với Query hoặc viết custom repository mapping phù hợp.

## 11. Index cho keyset pagination

Keyset chỉ phát huy hiệu quả khi database có index phù hợp với filter và sort.

Với query:

~~~sql
WHERE status = :status
  AND (
      created_at < :cursorCreatedAt
      OR (
          created_at = :cursorCreatedAt
          AND id < :cursorId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Một index ứng viên:

~~~sql
CREATE INDEX idx_orders_status_created_id
    ON orders(status, created_at DESC, id DESC);
~~~

Index này có thể hỗ trợ:

- Lọc theo status.
- Tìm tiếp theo từ created_at và id.
- Trả kết quả theo thứ tự mong muốn.

### 11.1. Thứ tự cột index rất quan trọng

Với composite index:

~~~text
(status, created_at, id)
~~~

Điều kiện equality trên status thường giúp thu hẹp vùng index trước khi áp dụng điều kiện sort/cursor trên created_at và id.

Nếu query khác có điều kiện lọc theo tenant:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
~~~

Index có thể cần bắt đầu bằng các cột equality filter:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders(tenant_id, status, created_at DESC, id DESC);
~~~

Không có một index duy nhất tối ưu cho mọi filter/sort. Hãy thiết kế theo các query thực sự được sử dụng và đo execution plan.

### 11.2. Kiểm tra execution plan

Với PostgreSQL, có thể xem kế hoạch và số liệu thực thi:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, created_at
FROM orders
WHERE status = 'PAID'
  AND (
      created_at < TIMESTAMP '2026-11-10 09:30:00'
      OR (
          created_at = TIMESTAMP '2026-11-10 09:30:00'
          AND id < 8120
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Với MySQL, có thể dùng EXPLAIN hoặc EXPLAIN ANALYZE tùy phiên bản. Hãy xem:

- Index nào được chọn.
- Số hàng ước lượng và thực tế.
- Có sort bổ sung không.
- Có full table scan không.
- Chi phí đọc dữ liệu.
- Query count và query nội dung có kế hoạch khác nhau thế nào.

EXPLAIN ANALYZE thực thi query để thu thập số liệu. Dùng cẩn thận với câu lệnh ghi hoặc query nặng trên môi trường production.

Không chỉ so sánh thời gian chạy một lần. Hãy dùng dữ liệu có phân bố gần production và đo nhiều lần dưới workload thực tế.

## 12. Keyset có thay thế được Page không?

Không. Hai cơ chế phục vụ hai kiểu điều hướng khác nhau.

| Tiêu chí | Offset/Page | Keyset/Cursor |
| --- | --- | --- |
| Nhảy đến trang bất kỳ | Thuận tiện | Không tự hỗ trợ |
| Hiển thị tổng số trang | Có thể | Không tự cung cấp |
| Duyệt tuần tự dữ liệu lớn | Offset sâu có thể chậm | Phù hợp hơn khi có index |
| Cursor cần lưu | Page number/offset | Các sort key cuối cùng |
| Tác động của insert trước vị trí hiện tại | Có thể làm trùng/thiếu hàng | Ít bị dịch chuyển vị trí tiếp tục |
| Điều kiện sort | Cần thứ tự ổn định | Cần thứ tự ổn định và tie-breaker |
| Index phù hợp | Hữu ích | Rất quan trọng |
| Độ phức tạp API | Thấp | Cao hơn do cursor |

Chọn theo trải nghiệm và yêu cầu nghiệp vụ:

- Bảng quản trị nhỏ cần nhảy trang: Page.
- Danh sách cần nút “Tiếp theo”: Slice.
- Feed hoặc danh sách lớn duyệt tuần tự: keyset/cursor.
- Batch export: keyset hoặc stream, tùy yêu cầu connection và transaction.
- Dashboard cần tổng số chính xác: Page hoặc query count riêng.
- Dashboard chấp nhận số gần đúng: cache hoặc summary counter.

## 13. Phân trang sâu trong batch export

Một tác vụ export hàng triệu bản ghi không nên mặc định lặp qua page 0, 1, 2, ... bằng offset.

Ví dụ không hiệu quả:

~~~java
int page = 0;

while (true) {
    Page<Order> result = repository.findByStatus(
            "PAID",
            PageRequest.of(page, 1000)
    );

    export(result.getContent());

    if (!result.hasNext()) {
        break;
    }

    page++;
}
~~~

Vấn đề:

- Mỗi page có thể phát sinh count query.
- Offset tăng sau mỗi vòng.
- Database phải bỏ qua ngày càng nhiều hàng.
- Mỗi vòng tạo một request query mới.
- Dữ liệu thay đổi trong lúc export có thể làm kết quả thiếu/trùng.

Một chiến lược tốt hơn:

1. Xác định phạm vi export, ví dụ khoảng thời gian hoặc trạng thái.
2. Chọn sort key ổn định và duy nhất.
3. Lấy từng chunk theo cursor.
4. Ghi chunk ra file hoặc destination.
5. Cập nhật cursor/checkpoint sau khi chunk được xử lý thành công.
6. Tiếp tục từ cursor cuối cùng khi job chạy lại.

Nếu export cần một snapshot chính xác tại một thời điểm, keyset đơn thuần không bảo đảm snapshot xuyên nhiều transaction. Cần xác định high-water mark, snapshot isolation phù hợp hoặc cơ chế snapshot/CDC theo yêu cầu.

### 13.1. High-water mark

Có thể cố định phạm vi dữ liệu bằng một mốc ban đầu, ví dụ ID lớn nhất tại thời điểm bắt đầu:

~~~sql
SELECT MAX(id) FROM orders;
~~~

Sau đó, mọi chunk chỉ đọc:

~~~sql
WHERE id > :lastId
  AND id <= :initialMaxId
ORDER BY id ASC
LIMIT :limit;
~~~

Cách này giúp không đưa các bản ghi có ID lớn hơn mốc ban đầu vào export. Tuy nhiên, nó không bảo đảm snapshot hoàn chỉnh nếu các bản ghi cũ vẫn có thể được cập nhật/xóa trong lúc export. Cần hiểu semantics của ID và workload trước khi áp dụng.

## 14. Tính nhất quán giữa count query và content query

Một Page có thể cần hai câu SQL riêng:

1. Lấy nội dung trang.
2. Đếm tổng số kết quả.

Nếu dữ liệu thay đổi giữa hai lần thực thi, tổng số và nội dung có thể phản ánh hai thời điểm khác nhau.

Ví dụ:

~~~text
T1: Count query trả về 100 đơn hàng
T2: Một transaction khác thêm đơn hàng mới
T3: Content query đọc dữ liệu đã có 101 đơn hàng
~~~

Response có thể chứa nội dung thuộc trạng thái mới nhưng tổng số thuộc trạng thái cũ.

Nếu nghiệp vụ chấp nhận độ lệch nhỏ trong điều hướng thông thường, đây có thể là trade-off phù hợp.

Nếu cần cùng một snapshot:

- Đặt các truy vấn trong transaction phù hợp.
- Chọn isolation level bảo đảm snapshot cần thiết trên database đích.
- Đánh giá chi phí giữ transaction lâu.
- Với báo cáo dài, cân nhắc snapshot/reporting table hoặc cơ chế export chuyên dụng.

Không nên giả định chỉ vì hai query nằm trong cùng một method Java thì chúng luôn nhìn thấy cùng snapshot. Điều đó phụ thuộc transaction boundary và isolation level thực tế.

## 15. Bảo đảm sort ổn định và an toàn

Dù dùng Page, Slice hay Cursor, thứ tự phải xác định.

### 15.1. Luôn thêm tie-breaker

Ví dụ:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
~~~

Nếu chỉ sort theo createdAt, hai hàng có cùng thời điểm có thể xuất hiện theo thứ tự khác nhau giữa các lần query.

### 15.2. Whitelist sort property

Không nối trực tiếp sort từ request vào SQL:

~~~java
// Không làm như vậy:
String sql = "SELECT ... ORDER BY " + request.getSort();
~~~

Thay vào đó, ánh xạ tên sort mà API hỗ trợ:

~~~java
Map<String, String> allowedSorts = Map.of(
        "createdAt", "created_at",
        "orderNumber", "order_number",
        "totalAmount", "total_amount"
);
~~~

Chỉ chấp nhận các property có trong danh sách và validate hướng sort. Khi dùng repository abstraction, truyền Sort với property đã được kiểm soát.

### 15.3. Giới hạn page size

Không để client yêu cầu một page quá lớn:

~~~java
private Pageable normalize(Pageable pageable) {
    int size = Math.min(pageable.getPageSize(), 200);

    return PageRequest.of(
            pageable.getPageNumber(),
            size,
            pageable.getSort()
    );
}
~~~

Cần xử lý riêng trường hợp Pageable.unpaged() nếu API cho phép. Giới hạn page size giúp bảo vệ bộ nhớ, connection và database khỏi request vô tình tải quá nhiều dữ liệu.

## 16. Đo lường và chẩn đoán

Trước khi thay đổi pagination, hãy đo riêng từng phần.

Các chỉ số hữu ích:

- Thời gian query lấy content.
- Thời gian count query.
- Số hàng thực tế được trả về.
- Offset lớn nhất được yêu cầu.
- Tỷ lệ request dùng Page, Slice và Cursor.
- Số lượng hàng được quét/đọc theo execution plan.
- Tỷ lệ timeout.
- Tần suất cache hit của count nếu có.
- Tỷ lệ request đi đến trang sâu.

Có thể bật log SQL của Spring JDBC trong môi trường phát triển:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Khi thấy một trang chậm:

1. Xác định chậm ở content query hay count query.
2. Ghi lại filter, sort, limit và offset.
3. Chạy execution plan trên database tương ứng.
4. Kiểm tra index và thống kê.
5. So sánh trang đầu với trang sâu.
6. Kiểm tra có JOIN gây nhân bản kết quả không.
7. Đánh giá liệu UI thật sự cần total count.
8. Thử Slice hoặc keyset trên cùng dữ liệu.
9. Đo lại dưới workload gần production.

Không tối ưu count query trong khi thời gian chính lại nằm ở truy vấn lấy aggregate có nhiều collection được tải bằng các câu SQL bổ sung.

## 17. Những sai lầm thường gặp

**“Page chỉ chạy một câu SELECT.”** Không nhất thiết. Page cần tổng số và có thể phát sinh count query bổ sung.

**“Slice nhanh trong mọi trường hợp.”** Slice tránh count query nhưng vẫn có thể dùng OFFSET. Trang rất sâu vẫn có thể chậm.

**“List với Pageable tự có hasNext.”** Không. List chỉ chứa nội dung; ứng dụng phải tự xác định điều hướng nếu cần.

**“COUNT(*) luôn nhanh vì chỉ trả một số.”** Không. Database vẫn phải xác định số hàng phù hợp và có thể đọc nhiều dữ liệu.

**“COUNT(column) luôn tương đương COUNT(*).”** Không. COUNT(column) bỏ qua NULL.

**“JOIN xong cứ COUNT(*) là tổng số aggregate.”** Không. JOIN một-nhiều có thể nhân bản root; dùng COUNT(DISTINCT root.id) nếu cần đếm aggregate duy nhất.

**“Count query có thể bỏ bớt filter.”** Không nếu muốn tổng số khớp tập kết quả. Điều kiện count phải tương đương điều kiện nội dung.

**“Count query cần ORDER BY.”** Không. Sắp xếp không thay đổi số lượng hàng.

**“Có thể truyền Pageable vào mọi @Query.”** Không. String-based query trong Spring Data JDBC không hỗ trợ tự viết lại SQL để áp dụng Pageable/Sort/Limit; hãy viết SQL giới hạn rõ ràng hoặc dùng custom repository.

**“Tạo index là offset sâu sẽ nhanh như trang đầu.”** Không. Database vẫn cần đi qua các entry bị bỏ qua.

**“Sort theo timestamp là đủ.”** Không nếu timestamp có thể trùng. Thêm tie-breaker duy nhất như ID.

**“Keyset pagination tự cung cấp tổng số trang.”** Không. Keyset giải quyết việc tiếp tục từ vị trí hiện tại; nếu cần tổng số chính xác, count vẫn là một bài toán riêng.

**“Cursor chỉ cần ID.”** Chỉ đúng khi ID là toàn bộ thứ tự sắp xếp. Sort nhiều trường cần cursor chứa đủ các khóa.

**“Keyset hoạt động tốt với mọi sort field.”** Không. Sort key nullable hoặc thay đổi liên tục có thể gây khó khăn và kết quả thiếu ổn định.

**“Keyset bảo đảm snapshot xuyên nhiều request.”** Không. Nó giảm vấn đề dịch chuyển do offset, nhưng không thay thế transaction snapshot hoặc snapshot export.

**“Cache count không cần invalidation.”** Không. Cache có thể trả số cũ; phải xác định độ trễ được chấp nhận và cách rebuild.

## 18. Quy trình chọn chiến lược phân trang

Khi thiết kế endpoint danh sách, hãy trả lời:

1. UI có cần tổng số bản ghi chính xác không?
2. Người dùng có cần nhảy đến một trang bất kỳ không?
3. Tập dữ liệu có thể lớn đến mức nào?
4. Người dùng có thể đi đến trang rất sâu không?
5. Sort key có ổn định và duy nhất không?
6. Query có JOIN hoặc GROUP BY làm thay đổi đơn vị đếm không?
7. Count query có thực sự là nút thắt không?
8. Có index phù hợp cho filter và sort không?
9. Dữ liệu có thay đổi liên tục trong lúc duyệt không?
10. Có cần một snapshot nhất quán cho toàn bộ quá trình không?

Sơ đồ quyết định:

~~~mermaid
flowchart TD
    A["Thiết kế endpoint danh sách"] --> B{"Có cần tổng số chính xác?"}
    B -->|Có| C["Page + count query"]
    B -->|Không| D{"Chỉ cần biết còn kết quả?"}
    D -->|Có| E["Slice hoặc cursor"]
    D -->|Không| F["List + Pageable"]
    C --> G{"Offset có thể rất sâu?"}
    E --> G
    F --> G
    G -->|Không| H["Offset pagination + stable sort"]
    G -->|Có| I{"Duyệt tuần tự, không cần nhảy trang?"}
    I -->|Có| J["Keyset / cursor pagination"]
    I -->|Không| K["Thiết kế lại UX hoặc dùng snapshot/report"]
    J --> L["Index theo filter + sort keys"]
    H --> M["Đo count/content query riêng"]
    L --> M
~~~

## 19. Bài tập thực hành

Tạo aggregate Order có các field id, orderNumber, status, createdAt và totalAmount.

### Bài 1: So sánh Page và Slice

1. Tạo repository method trả Page<Order> theo status.
2. Tạo method trả Slice<Order> theo status.
3. Chạy với page size 20.
4. Bật SQL logging.
5. Quan sát số câu query và việc sử dụng count query.
6. So sánh metadata trả về.

### Bài 2: Tự viết count query

1. Tạo custom repository fragment cho tìm kiếm đơn hàng.
2. Viết content SQL với filter và sort.
3. Viết count SQL với cùng filter.
4. Đảm bảo count không có ORDER BY, LIMIT hoặc OFFSET.
5. So sánh tổng số với kết quả thực tế.
6. Thêm JOIN order_items và kiểm tra COUNT(DISTINCT order_id).

### Bài 3: Đo offset sâu

1. Seed ít nhất vài trăm nghìn đơn hàng.
2. Chạy truy vấn trang đầu.
3. Chạy truy vấn với offset 10.000, 100.000 và 500.000.
4. Ghi lại thời gian và execution plan.
5. Thử thêm index phù hợp.
6. So sánh số hàng đọc và thời gian.

### Bài 4: Triển khai keyset

1. Sắp xếp theo createdAt DESC, id DESC.
2. Tạo cursor gồm createdAt và id.
3. Viết truy vấn trang đầu.
4. Viết truy vấn trang tiếp theo dùng điều kiện cursor.
5. Lấy pageSize + 1 để xác định hasNext.
6. Trả cursor mới từ hàng cuối cùng được hiển thị.
7. Kiểm tra không trùng và không bỏ sót trong dữ liệu không thay đổi.

### Bài 5: Kiểm tra khi có cập nhật đồng thời

1. Đọc trang đầu.
2. Chèn một đơn hàng mới có timestamp mới hơn.
3. Tiếp tục bằng offset pagination.
4. Quan sát khả năng trùng hoặc thiếu hàng.
5. Lặp lại với keyset cursor.
6. Cập nhật một sort key của hàng đã đọc và đánh giá tác động.

### Bài 6: Đo index và count

1. Chạy count query trước khi có index.
2. Tạo index theo status và created_at.
3. Chạy lại count query.
4. Xem execution plan.
5. Đo cả query nội dung và count query.
6. Đánh giá chi phí ghi phát sinh do index.

## 20. Ghi nhớ

- Page<T> cung cấp tổng số phần tử và tổng số trang; count query có thể được thực hiện để tạo metadata đó.
- Slice<T> dùng pageSize + 1 để xác định có trang tiếp theo mà không cần tổng số.
- List<T> cùng Pageable chỉ trả nội dung đoạn dữ liệu, không tạo metadata tổng số.
- Count query phải giữ đúng filter và đếm đúng đơn vị dữ liệu mà API phân trang.
- Với JOIN một-nhiều, dùng COUNT(DISTINCT root.id) khi cần đếm aggregate root duy nhất.
- Count query không cần ORDER BY, LIMIT hoặc OFFSET nếu đang đếm toàn bộ tập kết quả.
- JdbcAggregateTemplate.count(Query, Class) có thể dùng để đếm theo điều kiện của Query.
- String-based @Query trong Spring Data JDBC không tự hỗ trợ tham số Pageable, Sort hoặc Limit; cần SQL giới hạn rõ ràng hoặc custom repository.
- Count có thể chậm dù chỉ trả một số; index và execution plan cần được đánh giá trên dữ liệu thực tế.
- OFFSET sâu có thể phải đi qua rất nhiều hàng bị bỏ qua và dễ bị ảnh hưởng bởi insert/delete giữa các request.
- Luôn dùng sort ổn định với tie-breaker duy nhất.
- Keyset pagination tiếp tục từ các sort key của bản ghi cuối trang, tránh chi phí bỏ qua offset lớn.
- Cursor phải chứa đủ sort keys, filter/sort context và được validate.
- Keyset phù hợp cho duyệt tuần tự; nó không tự cung cấp tổng số trang hoặc khả năng nhảy đến trang tùy ý.
- Index nên phản ánh equality filters, sort fields và tie-breaker của keyset query.
- Nếu cần snapshot nhất quán xuyên nhiều request hoặc export dài, cần thiết kế isolation/high-water mark/snapshot riêng.
- Chỉ cache hoặc ước lượng count khi nghiệp vụ chấp nhận độ trễ hoặc sai số và có chiến lược cập nhật phù hợp.

**Tối ưu phân trang bắt đầu bằng việc xác định UI thực sự cần thông tin gì.** Nếu cần tổng số chính xác, dùng Page và tối ưu count query. Nếu chỉ cần biết còn dữ liệu, dùng Slice. Nếu phải duyệt tập dữ liệu rất lớn theo thứ tự ổn định, dùng keyset pagination với cursor và index phù hợp. Tách hai bài toán count và lấy nội dung giúp tìm đúng nút thắt và chọn chiến lược phù hợp cho từng use case.

## Tài liệu tham khảo

- [Spring Data Relational 4.1.2 — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Relational 4.1.2 — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html)
- [Spring Data Relational 4.1.2 — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
- [Spring Data Relational 4.1.2 — ScrollDelegate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/support/ScrollDelegate.html)
- [Spring Data Commons 4.1.2 — Scrolling](https://docs.spring.io/spring-data/relational/reference/data-commons/repositories/scrolling.html)
