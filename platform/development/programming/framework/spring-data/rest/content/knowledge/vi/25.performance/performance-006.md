# Chi phí count query, Page, Slice và phân trang tập dữ liệu lớn

Phân trang giúp API trả dữ liệu theo từng phần thay vì tải toàn bộ collection. Trong Spring Data, **Page<T>**, **Slice<T>** và cơ chế scrolling giải quyết những nhu cầu khác nhau:

- **Page<T>** cung cấp nội dung hiện tại cùng tổng số bản ghi và tổng số trang. Để có tổng số chính xác, framework thường cần chạy thêm count query.
- **Slice<T>** cho biết còn trang tiếp theo hay không mà không cần tính tổng số bản ghi.
- **Keyset scrolling** dùng giá trị của các cột sắp xếp làm cursor để lấy phần dữ liệu tiếp theo, phù hợp với việc duyệt tuần tự tập dữ liệu lớn.

Chọn sai kiểu trả về hoặc kiểu phân trang có thể làm một endpoint tưởng như đơn giản trở thành nút thắt database. Hãy quyết định dựa trên thông tin client thực sự cần và cách người dùng duyệt dữ liệu.

## 1. Phân trang với Pageable

Spring Data dùng **Pageable** để mô tả trang cần lấy, kích thước trang và thứ tự sắp xếp.

Ví dụ repository:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
~~~

Service có thể tạo yêu cầu trang:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<Order> page = orderRepository.findByStatus(
    OrderStatus.PAID,
    pageable
);
~~~

Các chỉ số trang bắt đầu từ **0**. Trang đầu tiên là **PageRequest.of(0, 20)**, trang tiếp theo là **PageRequest.of(1, 20)**.

Với Spring Data REST, collection resource thường nhận các query parameter:

~~~http
GET /orders?page=0&size=20&sort=createdAt,desc&sort=id,desc
Accept: application/hal+json
~~~

- **page**: chỉ số trang bắt đầu từ 0.
- **size**: số phần tử yêu cầu trong một trang.
- **sort**: tên thuộc tính và chiều sắp xếp (**asc** hoặc **desc**); có thể truyền nhiều tiêu chí.

Sắp xếp theo nhiều thuộc tính giúp thứ tự ổn định. Ví dụ **createdAt** có thể trùng nhau, vì vậy thêm **id** làm tie-breaker để xác định thứ tự giữa các bản ghi có cùng thời điểm.

## 2. Page<T> cung cấp tổng số bản ghi

**Page<T>** mở rộng thông tin của một **Slice<T>** bằng metadata về toàn bộ tập kết quả:

- Nội dung của trang hiện tại.
- Số trang hiện tại và kích thước trang.
- Số phần tử trong trang.
- Tổng số phần tử phù hợp với điều kiện lọc.
- Tổng số trang.
- Trạng thái trang đầu/cuối.

Ví dụ:

~~~java
Page<Order> page = orderRepository.findByStatus(
    OrderStatus.PAID,
    PageRequest.of(0, 20)
);

long total = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

Thông tin **totalElements** và **totalPages** hữu ích khi giao diện cần hiển thị “1–20 trên 8.450 đơn hàng”, cho phép nhảy tới trang cuối hoặc hiển thị số trang chính xác.

Đổi lại, database phải tính tổng số dòng thỏa điều kiện. Với truy vấn phức tạp hoặc bảng lớn, count query có thể tốn thời gian đáng kể, đôi khi còn chậm hơn truy vấn lấy nội dung.

## 3. Vì sao Page thường phát sinh count query?

Truy vấn nội dung cần lấy một phần dữ liệu, thường bằng **LIMIT** và **OFFSET** hoặc cú pháp tương đương của database. Nhưng truy vấn đó không tự cho biết tổng số bản ghi phù hợp.

Vì vậy, Spring Data JPA thường thực hiện hai truy vấn:

1. **Content query** lấy các dòng của trang hiện tại.
2. **Count query** đếm tổng số dòng thỏa cùng điều kiện lọc.

Ví dụ về ý tưởng SQL:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
~~~

Count query tương ứng:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Count query không cần trả về các cột của entity hoặc áp dụng thứ tự sắp xếp. Nó chỉ cần đếm chính xác tập kết quả mà content query đại diện.

Không phải mọi lần gọi Page đều nhất thiết thực hiện count query trong mọi tình huống; Spring Data có thể suy luận tổng số trong một số trường hợp dựa trên nội dung trang. Tuy nhiên, khi client yêu cầu tổng số chính xác, hãy dự trù chi phí count query và đo trên dữ liệu thực tế.

## 4. Tối ưu count query bằng @Query

Với query method có điều kiện phức tạp, Spring Data có thể không suy ra count query tối ưu từ JPQL hoặc native query. Có thể khai báo riêng thuộc tính **countQuery** trong **@Query**.

Ví dụ:

~~~java
@Query(
    value = """
        select o
        from Order o
        where o.status = :status
          and o.createdAt >= :from
        """,
    countQuery = """
        select count(o)
        from Order o
        where o.status = :status
          and o.createdAt >= :from
        """
)
Page<Order> findRecentByStatus(
    @Param("status") OrderStatus status,
    @Param("from") Instant from,
    Pageable pageable
);
~~~

Content query có thể cần join để lấy dữ liệu, trong khi count query chỉ cần đếm entity gốc. Nếu join tới collection làm một order xuất hiện nhiều lần, hãy cân nhắc **count(distinct o.id)** để tránh đếm trùng.

Ví dụ:

~~~sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_items i ON i.order_id = o.id
WHERE i.product_id = ?;
~~~

Khi thiết kế count query:

- Giữ nguyên điều kiện lọc để tổng số khớp với content query.
- Loại bỏ **ORDER BY** vì không cần sắp xếp khi đếm.
- Không đưa **FETCH JOIN** không cần thiết vào count query.
- Kiểm tra join một-nhiều có làm nhân số dòng hay không.
- Dùng **COUNT(DISTINCT ...)** khi semantics truy vấn yêu cầu đếm entity duy nhất.
- Với native query, khai báo count query tương ứng rõ ràng nếu framework không thể suy ra chính xác.

Đừng tối ưu count query bằng cách bỏ điều kiện lọc hoặc đếm sai tập dữ liệu. Tổng số không chính xác sẽ làm metadata phân trang gây hiểu nhầm cho client.

## 5. Slice<T> tránh count query

Nếu giao diện chỉ cần biết “còn dữ liệu để xem tiếp không?”, **Slice<T>** thường phù hợp hơn **Page<T>**.

Ví dụ:

~~~java
import org.springframework.data.domain.Slice;

public interface OrderRepository extends JpaRepository<Order, Long> {

    Slice<Order> findByStatus(
        OrderStatus status,
        Pageable pageable
    );
}
~~~

Một Slice cung cấp nội dung trang và các thông tin như:

- **hasNext()** — có phần dữ liệu tiếp theo hay không.
- **hasPrevious()** — có phần trước hay không.
- **getNumberOfElements()** — số phần tử trong lát hiện tại.
- **getSize()** — kích thước trang được yêu cầu.

Để xác định **hasNext**, Spring Data thường lấy thêm một dòng so với kích thước yêu cầu. Ví dụ client yêu cầu 20 dòng, truy vấn có thể lấy tối đa 21 dòng. Nếu có dòng thứ 21, Slice biết rằng còn dữ liệu tiếp theo; dòng phụ này không được trả trong nội dung trang.

Cách này tránh truy vấn đếm toàn bộ kết quả. Slice không cung cấp **totalElements** hoặc **totalPages**, vì vậy giao diện không thể hiển thị tổng số chính xác nếu chỉ dựa trên Slice.

Dùng Slice cho danh sách cuộn vô hạn, nút “Tải thêm” hoặc giao diện chỉ cần nút Next/Previous.

## 6. Chọn Page hay Slice theo nhu cầu giao diện

| Nhu cầu | Kiểu phù hợp | Lý do |
|---|---|---|
| Hiển thị tổng số kết quả và tổng số trang | **Page<T>** | Cần metadata tổng số |
| Cho phép nhảy tới trang cuối | **Page<T>** | Cần biết tổng số trang |
| Nút “Tải thêm” hoặc infinite scroll | **Slice<T>** | Chỉ cần biết còn trang sau |
| Duyệt tuần tự dữ liệu rất lớn | Keyset scrolling | Tránh offset tăng dần |
| Xuất dữ liệu hàng loạt | Scrolling hoặc batch processing | Không tải toàn bộ tập dữ liệu vào memory |

Không nên dùng Page chỉ vì repository method mặc định dễ viết. Nếu giao diện không hiển thị tổng số và không cần nhảy trang, count query có thể là chi phí không cần thiết.

Ngược lại, không dùng Slice nếu sản phẩm yêu cầu hiển thị tổng số chính xác. Khi đó Page hoặc một chiến lược đếm riêng phù hợp hơn.

## 7. Chi phí của offset pagination trên tập dữ liệu lớn

Phân trang offset thường được biểu diễn bằng:

~~~sql
SELECT *
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 50 OFFSET 500000;
~~~

Database phải xác định và bỏ qua một lượng lớn dòng trước khi trả về trang sâu. Khi offset tăng, chi phí có thể tăng theo dù client chỉ nhận 50 dòng.

Offset pagination vẫn hữu ích khi:

- Dataset vừa phải.
- Người dùng cần nhảy tới trang bất kỳ.
- Có yêu cầu tổng số trang.
- Database có index phù hợp với điều kiện lọc và thứ tự sắp xếp.

Nhưng với bảng rất lớn hoặc luồng duyệt tuần tự, offset sâu thường không phải lựa chọn tốt. Nó cũng có thể tạo kết quả trùng hoặc bỏ sót khi dữ liệu được chèn/xóa giữa hai lần client yêu cầu trang.

## 8. Giữ thứ tự ổn định và tạo index phù hợp

Một truy vấn phân trang cần thứ tự xác định. Nếu chỉ sort theo **createdAt** mà nhiều bản ghi có cùng timestamp, database có thể trả thứ tự khác nhau giữa các lần gọi.

Thêm khóa duy nhất làm tiêu chí cuối:

~~~java
Pageable pageable = PageRequest.of(
    pageNumber,
    pageSize,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Index nên phù hợp với điều kiện lọc và thứ tự sắp xếp thường dùng. Ví dụ truy vấn thường lọc theo **status** và sắp xếp theo **created_at**, **id** có thể hưởng lợi từ index tổng hợp tương ứng:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON orders(status, created_at DESC, id DESC);
~~~

Đây chỉ là ví dụ; thứ tự cột index cần dựa trên selectivity, truy vấn thực tế và database engine. Dùng **EXPLAIN** hoặc công cụ phân tích execution plan để xác nhận database có sử dụng index như mong muốn.

Cũng cần giới hạn kích thước trang để client không yêu cầu hàng chục nghìn dòng trong một request.

## 9. Giới hạn page size trong Spring Data REST

Spring Data REST cho phép cấu hình kích thước trang mặc định và tối đa:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestRepositoryConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
~~~

Với cấu hình này:

- Nếu client không gửi **size**, server dùng kích thước mặc định 20.
- Client không thể yêu cầu một trang lớn hơn giới hạn 100 thông qua pageable resolver của Spring Data REST.

Chọn giới hạn dựa trên kích thước response, độ phức tạp entity, lazy loading, network và tải database. Một page size quá lớn có thể tăng memory, thời gian serialization và thời gian giữ connection.

Đối với custom controller, hãy áp dụng giới hạn tương tự cho **Pageable** đầu vào; không giả định giới hạn của Spring Data REST tự động áp dụng cho mọi controller MVC.

## 10. Keyset scrolling cho tập dữ liệu lớn

Keyset scrolling dùng các giá trị của hàng cuối cùng trong cửa sổ hiện tại làm cursor cho truy vấn kế tiếp.

Thay vì yêu cầu “bỏ qua 500.000 dòng”, client/server yêu cầu “lấy các dòng đứng sau khóa sắp xếp cuối cùng đã thấy”.

Ví dụ truy vấn theo **createdAt** và **id** giảm dần có thể dùng điều kiện tiếp tục tương đương:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Điều kiện so sánh phải khớp chiều sort. Với thứ tự tăng dần, toán tử tiếp tục sẽ đảo lại.

Spring Data hỗ trợ scrolling API với **Window<T>** và **ScrollPosition** trong các phiên bản phù hợp:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public interface OrderRepository extends Repository<Order, Long> {

    Window<Order> findFirst50ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus status,
        ScrollPosition position
    );
}
~~~

Bắt đầu một lượt keyset scroll:

~~~java
Window<Order> window =
    orderRepository.findFirst50ByStatusOrderByCreatedAtAscIdAsc(
        OrderStatus.PAID,
        ScrollPosition.keyset()
    );
~~~

Có thể lấy vị trí cuối cửa sổ để tiếp tục:

~~~java
if (!window.isEmpty() && window.hasNext()) {
    ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

    Window<Order> nextWindow =
        orderRepository.findFirst50ByStatusOrderByCreatedAtAscIdAsc(
            OrderStatus.PAID,
            nextPosition
        );
}
~~~

Cú pháp và khả năng scrolling phụ thuộc phiên bản Spring Data module. Hãy kiểm tra API của phiên bản dự án trước khi dùng.

Để keyset scrolling hoạt động ổn định:

- Thứ tự sắp xếp phải xác định và kết thúc bằng khóa duy nhất, thường là primary key.
- Các thuộc tính keyset cần có giá trị phù hợp, tránh null gây khó xác định vị trí tiếp theo.
- Projection/result phải cung cấp các giá trị cần thiết để tạo keyset.
- Index database nên hỗ trợ các cột lọc và sắp xếp.
- Cursor phải gắn với filter và sort của truy vấn; không dùng cursor cũ cho một truy vấn khác.

Keyset scrolling phù hợp với việc duyệt tuần tự, xử lý batch hoặc API cursor. Nó không tự cung cấp tổng số trang và không thuận tiện cho việc nhảy tới trang bất kỳ.

## 11. Thiết kế cursor API

Nếu muốn client dùng cursor thay vì page number, custom endpoint có thể nhận một cursor opaque:

~~~http
GET /orders?limit=50&cursor=eyJjcmVhdGVkQXQiOi...
~~~

Response có thể trả nội dung và cursor tiếp theo:

~~~json
{
  "items": [
    {
      "id": 1201,
      "status": "PAID"
    }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}
~~~

Cursor nên mã hóa hoặc ký các thông tin cần để tiếp tục truy vấn, chẳng hạn giá trị sort cuối cùng, filter, hướng sort và phiên bản cursor. Tránh cho client tự sửa trực tiếp giá trị nội bộ nếu điều đó có thể làm thay đổi phạm vi truy vấn.

Cần xử lý trường hợp dữ liệu thay đổi giữa hai lần gọi. Keyset giảm vấn đề dịch chuyển do offset, nhưng không tự tạo snapshot nhất quán cho toàn bộ quá trình duyệt. Nếu use case yêu cầu snapshot, cần thêm chiến lược transaction, watermark hoặc snapshot semantics phù hợp.

## 12. Kiểm tra hiệu năng phân trang

Đừng chỉ đo thời gian trả về của API. Hãy tách các thành phần:

1. Thời gian content query.
2. Thời gian count query nếu dùng Page.
3. Thời gian serialize entity và quan hệ.
4. Số lượng SQL statement phát sinh.
5. Kích thước response và memory.
6. Execution plan của truy vấn ở trang đầu và trang sâu.

Có thể bật SQL logging trong môi trường phát triển hoặc dùng datasource metrics để xác nhận Page phát sinh count query. Dùng database **EXPLAIN**/**EXPLAIN ANALYZE** để xem scan, index, join và sort.

Một bài test nên so sánh:

- Page đầu tiên và một trang có offset lớn.
- Page với Slice trên cùng điều kiện lọc.
- Count query tự sinh và count query tùy chỉnh.
- Offset pagination và keyset scrolling với cùng thứ tự sort.

Chỉ kết luận tối ưu sau khi đo trên dữ liệu có quy mô và phân bố gần với production.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Endpoint chậm dù chỉ trả 20 dòng | Count query tốn kém | Dùng Slice nếu không cần tổng số hoặc tối ưu **countQuery** |
| Tổng số phần tử lớn hơn số entity duy nhất | Join một-nhiều làm nhân bản dòng | Dùng count distinct phù hợp |
| Trang sâu chậm hơn nhiều | Offset lớn | Dùng keyset scrolling cho luồng duyệt tuần tự |
| Bản ghi lặp hoặc bị bỏ qua giữa các trang | Sort không duy nhất hoặc dữ liệu thay đổi | Thêm khóa duy nhất vào sort; cân nhắc cursor |
| Client yêu cầu page size quá lớn | Không giới hạn pageable | Cấu hình default/max page size |
| Count query có join/fetch không cần thiết | Count query được suy ra không tối ưu | Khai báo **countQuery** riêng |
| Keyset không tìm thấy vị trí tiếp theo | Sort thiếu khóa duy nhất hoặc keyset field có null | Bổ sung tie-breaker và chọn field phù hợp |
| Response quá nặng dù page size nhỏ | Entity serialize nhiều quan hệ | Dùng projection, excerpt hoặc DTO phù hợp |

## 14. Quy tắc lựa chọn

- Dùng **Page<T>** khi client thật sự cần tổng số phần tử hoặc tổng số trang.
- Dùng **Slice<T>** khi chỉ cần biết có dữ liệu tiếp theo hay không.
- Dùng offset pagination khi cần nhảy trang tùy ý và dataset có quy mô phù hợp.
- Dùng keyset scrolling/cursor khi cần duyệt tuần tự tập dữ liệu lớn.
- Khai báo **countQuery** riêng khi query tự sinh không hiệu quả hoặc không chính xác.
- Bảo đảm sort ổn định bằng một khóa duy nhất.
- Tạo index theo filter và sort thực tế; xác minh bằng execution plan.
- Giới hạn page size để bảo vệ database, memory và network.
- Đo riêng content query, count query và serialization trước khi tối ưu.

Tài liệu tham khảo chính thức:

- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
- [Spring Data JPA — Query Methods and Paging](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Data Commons — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
