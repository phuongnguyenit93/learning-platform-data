# Đánh giá hiệu năng và khả năng chẩn đoán

Một thiết kế MVC tốt cần đáp ứng hai câu hỏi: ứng dụng có xử lý khối lượng công việc dự kiến trong thời gian chấp nhận được không, và khi một request chậm hoặc thất bại, nhóm có đủ bằng chứng để tìm ra nguyên nhân không? Hai câu hỏi này liên quan chặt chẽ. Một endpoint có thể trả kết quả đúng trong môi trường phát triển nhưng chậm khi dữ liệu lớn; một hệ thống có thể có log và dashboard nhưng thiếu trace hoặc chỉ số phù hợp để phân biệt nghẽn database với nghẽn thread pool.

Đánh giá hiệu năng và khả năng chẩn đoán không phải là bước tối ưu hóa ở cuối dự án. Đây là một phần của review kiến trúc và thiết kế use case. Reviewer cần hiểu đường đi của request, workload thực tế, các phụ thuộc đồng bộ, cách truy vấn dữ liệu, cách quản lý tài nguyên và những tín hiệu vận hành được phát ra ở từng ranh giới.

Bài học này dùng một ứng dụng MVC quản lý sách làm ví dụ. Một trang tìm kiếm sách có thể phải đọc dữ liệu từ database, áp dụng bộ lọc, phân trang, ánh xạ sang View Model và render HTML. Khi trang chậm, nguyên nhân có thể nằm ở câu SQL, số lượng truy vấn, tải quan hệ ORM, template, kích thước response hoặc hàng đợi request. Mục tiêu của review là xác định được nguyên nhân bằng dữ liệu đo lường và chọn thay đổi phù hợp.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao hiệu năng và khả năng chẩn đoán là thuộc tính của toàn bộ request path.
- Xác định workload, latency budget và SLO phù hợp cho một use case MVC.
- Đọc các chỉ số latency percentile, throughput, error rate và saturation.
- Review truy vấn database, N+1, index, pagination, transaction và connection pool.
- Đánh giá cache, payload, rendering, executor và lời gọi dịch vụ bên ngoài.
- Phân biệt logs, metrics, traces và health checks.
- Thiết kế instrumentation có cardinality kiểm soát được.
- Xây dựng quy trình chẩn đoán từ triệu chứng đến nguyên nhân.
- Review hiệu năng bằng load test, profiling và dữ liệu production an toàn.
- Đưa ra nhận xét thiết kế có bằng chứng, mức độ ảnh hưởng và hướng sửa cụ thể.

## 2. Hiệu năng và khả năng chẩn đoán là yêu cầu thiết kế

Hiệu năng không chỉ là tốc độ của một câu lệnh hoặc một lớp Java. Người dùng trải nghiệm thời gian từ lúc gửi request đến khi nhận được response. Trong khoảng đó, ứng dụng có thể phải đi qua nhiều thành phần:

- Network, reverse proxy và load balancer.
- TLS, authentication và authorization filters.
- DispatcherServlet và quá trình binding/validation.
- Controller và Application Service.
- Domain Model và Repository.
- Database, cache hoặc dịch vụ bên ngoài.
- Ánh xạ DTO/View Model.
- Template rendering hoặc JSON serialization.
- Network trả response về client.

Một tầng có thể nhanh khi chạy riêng nhưng toàn bộ luồng vẫn chậm do chờ một phụ thuộc, xếp hàng hoặc tải quá nhiều dữ liệu.

Khả năng chẩn đoán (diagnosability) là mức độ dễ dàng xác định điều gì đã xảy ra, ở đâu, với request nào, trong điều kiện nào và vì sao. Hệ thống dễ chẩn đoán thường có:

- Tên sự kiện và field log ổn định.
- Metrics mô tả latency, throughput, lỗi và mức sử dụng tài nguyên.
- Trace liên kết các span qua các thành phần.
- Request/trace ID để nối dữ liệu.
- Error code và thông báo có ngữ nghĩa.
- Health/readiness status phản ánh đúng khả năng phục vụ.
- Dashboard và quy trình điều tra có thể lặp lại.

Nếu thiếu các tín hiệu này, nhóm thường phải tái hiện lỗi bằng phỏng đoán, bật log quá chi tiết hoặc truy cập trực tiếp production để tìm hiểu. Điều đó làm kéo dài thời gian khắc phục và tăng rủi ro vận hành.

## 3. Bắt đầu review từ workload và hành trình người dùng

Không thể đánh giá một endpoint là nhanh hay chậm nếu chưa biết nó được sử dụng thế nào. Trước khi đề xuất cache, index hoặc tăng số thread, hãy mô tả workload.

Với ứng dụng quản lý sách, các hành trình có thể gồm:

| Hành trình | Đặc điểm | Điều cần quan sát |
|---|---|---|
| Tìm kiếm danh sách sách | Đọc thường xuyên, có filter và pagination | p95 latency, query count, rows scanned |
| Xem chi tiết một sách | Đọc một aggregate và dữ liệu liên quan | DB round trips, response size |
| Nhập kho | Ghi dữ liệu, cần kiểm tra trạng thái và tồn kho | transaction duration, lock conflict |
| Cập nhật metadata | Ghi ít dữ liệu nhưng có thể có validation | error rate, commit latency |
| Xuất báo cáo | Đọc nhiều dữ liệu, có thể chạy lâu | queue time, memory, timeout |

Cần biết tần suất, số người dùng đồng thời, kích thước dữ liệu, thời điểm cao điểm và phân bố request. Một trang được mở 10 lần mỗi giờ có thể không cần tối ưu giống một endpoint được gọi hàng nghìn lần mỗi phút.

### 3.1. Mô tả workload bằng số liệu

Một workload profile nên ghi rõ:

- Request rate trung bình và lúc cao điểm.
- Số request đồng thời.
- Tỷ lệ đọc/ghi.
- Số bản ghi và tốc độ tăng dữ liệu.
- Kích thước request/response.
- Tỷ lệ cache hit dự kiến nếu có cache.
- Tỷ lệ lỗi và retry từ phụ thuộc.
- Các tác vụ nền chạy đồng thời.
- Mức tăng tải theo mùa hoặc theo chiến dịch.

Không nên lấy một con số request/giây duy nhất làm đại diện cho toàn hệ thống. Endpoint tìm kiếm, đăng nhập và nhập kho có chi phí cũng như giới hạn khác nhau.

### 3.2. Xác định SLO và latency budget

SLO (Service Level Objective) mô tả mục tiêu chất lượng dịch vụ trong một khoảng thời gian. Ví dụ minh họa:

| Chỉ số | Mục tiêu giả định |
|---|---|
| Tìm kiếm sách | p95 dưới 500 ms |
| Xem chi tiết | p95 dưới 300 ms |
| Nhập kho | p95 dưới 700 ms |
| Tỷ lệ lỗi server | Dưới 0,1% |
| Availability của API đọc | 99,9% theo cửa sổ tháng |

Các con số này chỉ là ví dụ. Mục tiêu thật cần dựa trên kỳ vọng người dùng, chi phí hạ tầng, workload và cam kết sản phẩm.

Latency budget chia thời gian cho các phần của request. Nếu mục tiêu p95 của trang tìm kiếm là 500 ms, nhóm có thể dành ngân sách cho network/edge, xử lý ứng dụng, database và rendering. Không nên cộng các p95 của từng thành phần để suy ra p95 toàn request vì percentile của các phân bố không cộng tuyến tính. Dùng trace và đo end-to-end để xác nhận.

### 3.3. Đừng dùng average để che giấu đuôi chậm

Average có thể trông tốt dù một tỷ lệ người dùng phải chờ lâu. Hãy xem:

- p50: trải nghiệm của request ở giữa phân bố.
- p90/p95: nhóm request chậm hơn phần lớn traffic.
- p99: đuôi chậm, hữu ích khi có spike hoặc contention.
- Max: có thể giúp tìm outlier nhưng rất nhạy với một mẫu đơn lẻ.

Khi review dashboard, cần biết metric được tổng hợp bằng histogram hay cách khác. Không tính percentile bằng cách lấy trung bình percentile từ nhiều instance nếu không có dữ liệu phân phối phù hợp.

## 4. Lần theo toàn bộ request path của MVC

Một request tìm kiếm sách có thể đi qua các bước:

~~~mermaid
flowchart TD
    Client["Browser / API Client"]
    Edge["Proxy / Load Balancer"]
    Filter["Security and Servlet Filters"]
    Dispatcher["DispatcherServlet"]
    Controller["BookController"]
    App["SearchBooks Use Case"]
    Query["Book Query / Repository"]
    DB[("Database")]
    Mapper["View Model Mapper"]
    View["Template Rendering"]
    Response["HTTP Response"]

    Client --> Edge --> Filter --> Dispatcher
    Dispatcher --> Controller --> App --> Query --> DB
    DB --> Mapper --> View --> Response
    Response --> Client
~~~

Khi trang chậm, reviewer nên xác định thời gian ở mỗi đoạn thay vì nhìn một tổng thời gian duy nhất.

Một cách phân rã khái niệm:

- **Queue time:** request chờ được xử lý.
- **Application time:** binding, validation, mapping và logic.
- **Dependency time:** chờ database, cache, HTTP service hoặc message system.
- **Rendering/serialization time:** tạo HTML/JSON.
- **Network time:** truyền dữ liệu giữa các thành phần.

Các khoảng thời gian có thể chồng lấp nếu ứng dụng có xử lý bất đồng bộ. Phân rã phải dựa trên instrumentation thực tế, không suy ra bằng cách trừ các số liệu không cùng phạm vi.

### 4.1. Đo ở ranh giới có ý nghĩa

Nên có phép đo end-to-end cho request và các span hoặc timer ở các phụ thuộc quan trọng. Không cần instrument từng getter hoặc mọi dòng code. Đo quá chi tiết làm tăng chi phí và tạo lượng dữ liệu khó sử dụng.

Các điểm đo hữu ích:

- HTTP server request duration.
- Application use case duration.
- Database query duration và số query.
- External dependency duration.
- Cache hit/miss.
- Template rendering duration nếu có vấn đề.
- Queue wait và executor active/queued tasks.

Tên operation cần ổn định. Dùng route template như /books/{bookId}, không dùng URL chứa ID thực làm nhãn metric.

## 5. Review Controller và Application Service

Controller nên xử lý giao thức: binding, validation, gọi use case và chọn response. Một Controller vừa phân tích request, truy vấn nhiều repository, gọi nhiều dịch vụ, tính toán báo cáo và dựng HTML sẽ khó đo và khó tối ưu.

Ví dụ một Controller có quá nhiều trách nhiệm:

~~~java
@GetMapping("/books")
public String search(
        @RequestParam String keyword,
        Model model) {

    List<BookJpaEntity> books =
        repository.findByTitleContaining(keyword);

    for (BookJpaEntity book : books) {
        book.setAuthorNames(
            authorRepository.findNamesByBookId(book.getId())
        );
    }

    model.addAttribute("books", books);
    model.addAttribute("total", books.size());
    return "books/list";
}
~~~

Đoạn code có thể tạo một truy vấn lấy danh sách và thêm một truy vấn cho mỗi sách để lấy tác giả. Controller cũng đang biết chi tiết JPA Entity và cách tải quan hệ.

Một thiết kế rõ hơn:

~~~java
@GetMapping("/books")
public String search(
        @Valid @ModelAttribute BookSearchRequest request,
        Model model) {

    BookSearchView result = searchBooks.handle(
        new BookSearchQuery(
            request.keyword(),
            request.page(),
            request.size()
        )
    );

    model.addAttribute("result", result);
    return "books/list";
}
~~~

Query service chịu trách nhiệm tải dữ liệu cần hiển thị bằng một projection hoặc số truy vấn có kiểm soát. Controller không cần biết cách tối ưu SQL.

BookSearchRequest, BookSearchQuery và BookSearchView là các kiểu hợp đồng minh họa; phần khai báo được lược bỏ để tập trung vào ranh giới giữa Controller và use case.

### 5.1. Tránh làm việc nặng trong request thread

Các tác vụ như xuất báo cáo lớn, xử lý tệp hoặc đồng bộ hàng nghìn bản ghi có thể giữ request thread quá lâu. Hãy xem xét job nền và trả job ID để client tra cứu trạng thái khi nghiệp vụ cho phép.

Không chuyển mọi thao tác sang async chỉ vì muốn endpoint phản hồi nhanh. Async vẫn tiêu thụ CPU, memory, connection và executor capacity; nó chỉ thay đổi cách giữ request/thread. Cần có timeout, giới hạn queue, xử lý lỗi và cơ chế quan sát job.

## 6. Review truy vấn database

Database thường là một trong những nguồn latency chính của ứng dụng MVC. Reviewer nên kiểm tra query count, query plan, index, số dòng đọc, lock và thời gian giữ connection.

### 6.1. Phát hiện N+1 query

N+1 xảy ra khi ứng dụng tải một danh sách bằng một query rồi phát sinh thêm một query cho mỗi phần tử khi đọc quan hệ lazy.

Ví dụ:

~~~java
List<BookJpaEntity> books = repository.findAll(pageable);

for (BookJpaEntity book : books) {
    String publisherName = book.getPublisher().getName();
    // render hoặc map dữ liệu
}
~~~

Nếu có 50 sách và mỗi sách tải publisher bằng một query riêng, request có thể phát ra 51 query. Nếu còn tải authors, categories hoặc stock movements, số query có thể tăng nhanh hơn.

Cách xử lý phụ thuộc use case:

- Projection chỉ lấy các cột cần thiết.
- Fetch join có giới hạn và phù hợp với phân trang.
- Entity graph cho quan hệ cần thiết.
- Batch fetching khi phù hợp.
- Query riêng lấy dữ liệu liên quan theo tập ID.
- Tách query model khỏi aggregate khi màn hình chỉ cần dữ liệu đọc.

Không thêm fetch join tất cả quan hệ vào mọi query. Fetch nhiều collection có thể tạo Cartesian product, trùng dòng, tăng memory và làm pagination sai hoặc tốn kém.

### 6.2. Lấy đúng dữ liệu bằng projection

Ví dụ interface projection của Spring Data:

~~~java
public interface BookListProjection {
    UUID getId();
    String getTitle();
    String getIsbn();
    String getPublisherName();
    Integer getStockQuantity();
}
~~~

Repository:

~~~java
public interface SpringDataBookRepository
        extends JpaRepository<BookJpaEntity, UUID> {

    @Query("""
        select b.id as id,
               b.title as title,
               b.isbn as isbn,
               p.name as publisherName,
               b.stockQuantity as stockQuantity
        from BookJpaEntity b
        join b.publisher p
        where b.status = :status
        """)
    Page<BookListProjection> findListByStatus(
        @Param("status") BookStatus status,
        Pageable pageable
    );
}
~~~

Projection giúp tránh tải cả aggregate và các quan hệ không cần cho trang danh sách. Query minh họa giả định publisher là quan hệ nhiều-một và JPQL hỗ trợ text block theo phiên bản Java đang dùng; alias của select phải khớp getter projection. Nếu mapping khác, điều chỉnh join hoặc dùng native query/query service riêng.

### 6.3. Index phải theo query thực tế

Một index hữu ích phụ thuộc vào điều kiện lọc, thứ tự sắp xếp, selectivity và workload. Ví dụ trang tìm kiếm thường lọc theo status và sắp xếp theo title hoặc createdAt. Có thể cần index kết hợp phù hợp, nhưng index không phải miễn phí: nó tăng chi phí ghi và dung lượng.

Review nên hỏi:

- Query có dùng index hay full table scan?
- Index có phù hợp với thứ tự cột trong predicate và order by không?
- Có quá nhiều index trùng lặp không?
- Query plan có thay đổi khi bảng lớn lên không?
- Statistics của database có đủ mới không?
- Tìm kiếm chứa wildcard đầu chuỗi có làm index B-tree không còn hiệu quả không?

Không tạo index chỉ vì một cột xuất hiện trong WHERE. Dùng EXPLAIN/EXPLAIN ANALYZE trên dữ liệu đại diện và đánh giá tác động trên workload ghi.

### 6.4. Phân trang là một phần của hợp đồng hiệu năng

Không nên trả toàn bộ danh mục sách trong một response. Pagination giới hạn số dòng, payload và chi phí render.

Offset pagination đơn giản:

~~~sql
SELECT id, isbn, title, stock_quantity
FROM books
WHERE status = 'ACTIVE'
ORDER BY title, id
LIMIT :page_size OFFSET :offset;
~~~

Khi offset lớn, database có thể phải đi qua nhiều dòng trước khi trả kết quả. Thứ tự sắp xếp cần ổn định và có tie-breaker, ví dụ id, để tránh kết quả nhảy giữa các trang.

Keyset pagination phù hợp với danh sách lớn hoặc cuộn liên tục:

~~~sql
SELECT id, isbn, title, stock_quantity
FROM books
WHERE status = 'ACTIVE'
  AND (title, id) > (:last_title, :last_id)
ORDER BY title, id
LIMIT :page_size;
~~~

Cú pháp so sánh tuple phụ thuộc database. Keyset pagination cần cursor dựa trên đúng thứ tự sắp xếp và xử lý trường hợp giá trị null nhất quán. Nó không thuận tiện cho việc nhảy trực tiếp tới một trang số bất kỳ.

### 6.5. Tránh giữ transaction lâu

Transaction nên bao quanh phần đọc/ghi cần tính nhất quán. Không giữ transaction database trong lúc chờ người dùng, gửi email hoặc gọi một API chậm nếu không có lý do rõ ràng.

Một luồng không tốt:

~~~java
@Transactional
public void confirmOrder(OrderId id) {
    Order order = orders.findById(id).orElseThrow();
    paymentClient.capture(order.paymentId());
    order.confirm();
    orders.save(order);
}
~~~

Nếu payment service chậm, transaction và connection database có thể bị giữ trong thời gian dài. Cách tổ chức phù hợp phụ thuộc nghiệp vụ thanh toán: có thể tạo trạng thái chờ, gọi phụ thuộc ngoài transaction, rồi xác nhận kết quả trong transaction riêng với idempotency và cơ chế xử lý thất bại. Không thể chỉ bỏ annotation transaction mà không xem lại tính nhất quán.

### 6.6. Lock và contention

Một query nhanh khi chạy đơn lẻ vẫn có thể chậm dưới tải vì nhiều transaction cùng khóa một hàng hoặc một tập dữ liệu.

Theo dõi:

- Lock wait time.
- Deadlock count.
- Optimistic locking conflict.
- Transaction duration.
- Số connection đang active và chờ.
- Các hàng nóng được cập nhật thường xuyên.

Nếu một cuốn sách có tồn kho được nhiều request xuất đồng thời, cần cơ chế bảo vệ cập nhật. Có thể dùng optimistic locking, pessimistic locking hoặc câu lệnh update có điều kiện. Chọn theo contention và yêu cầu nghiệp vụ, sau đó kiểm thử ở mức concurrency thực tế.

## 7. Review cache

Cache có thể giảm latency và tải database, nhưng cache chỉ đúng khi key, phạm vi dữ liệu, thời gian sống và invalidation được thiết kế rõ.

### 7.1. Cache dữ liệu ổn định và có tần suất đọc cao

Danh mục thể loại hoặc metadata ít thay đổi có thể phù hợp với cache. Tồn kho thay đổi liên tục hoặc dữ liệu cần độ mới cao phải có chính sách khác.

Trước khi thêm cache, hãy xác nhận bằng metrics rằng database hoặc phụ thuộc đang là nút thắt. Cache không sửa được query sai, N+1 hoặc thiếu index một cách bền vững.

### 7.2. Cache key phải chứa đủ ngữ cảnh

Nếu dữ liệu phụ thuộc tenant, locale, quyền hoặc filter, cache key phải bao gồm các yếu tố ảnh hưởng đến kết quả. Dùng một key chung có thể trả dữ liệu của tenant này cho tenant khác.

Ví dụ minh họa với Spring Cache:

~~~java
@Cacheable(
    cacheNames = "book-details",
    key = "#tenantId + ':' + #bookId"
)
public BookDetailView getBook(
        String tenantId,
        UUID bookId) {
    return queryBookDetail(tenantId, bookId);
}
~~~

Nếu kết quả phụ thuộc quyền truy cập theo từng actor, chỉ tenant ID có thể vẫn chưa đủ. Cần xác định chính xác những thuộc tính nào làm thay đổi kết quả và tránh cache dữ liệu cá nhân nhạy cảm ngoài chính sách.

### 7.3. Invalidation và dữ liệu cũ

Khi cập nhật sách, cache chi tiết có thể cần eviction hoặc refresh. Một TTL dài giảm tải nhưng tăng thời gian dữ liệu cũ; TTL ngắn tăng lượt truy vấn.

Các câu hỏi review:

- Cache được làm mới khi nào?
- Có chấp nhận stale data không và trong bao lâu?
- Nếu write thành công nhưng eviction thất bại thì sao?
- Có cache stampede khi nhiều request cùng miss không?
- Có giới hạn kích thước và eviction policy không?
- Cache có được tách theo tenant và môi trường không?

Cache-aside là một chiến lược phổ biến: đọc cache trước, miss thì tải từ nguồn chính rồi ghi cache. Khi ghi, ứng dụng cập nhật database và invalidates cache theo một thứ tự có chủ đích. Với hệ thống nhiều instance, cần hiểu phạm vi cache và cách đồng bộ invalidation.

### 7.4. Không cache mọi thứ

Cache làm tăng độ phức tạp, thêm trạng thái và khả năng stale. Đừng cache một truy vấn rẻ chỉ vì annotation dễ thêm. Đo hit rate, miss latency, eviction và tác động tới database trước và sau khi thay đổi.

## 8. Review payload và serialization

Một response lớn tiêu tốn thời gian serialize, bộ nhớ, băng thông và thời gian parse ở client.

Kiểm tra:

- Có trả cả object graph ORM không?
- Có trường nào client không dùng không?
- Có thể phân trang hoặc giới hạn số phần tử không?
- Có dữ liệu lặp lại giữa các dòng không?
- Có thể dùng projection hoặc DTO gọn hơn không?
- Có cần nén response không?
- Có tải nội dung tệp lớn đồng bộ qua Controller không?

DTO không chỉ là ranh giới bảo mật; nó còn giúp kiểm soát payload. Với API danh sách, chỉ trả các field cần cho danh sách. Trang chi tiết có thể gọi endpoint riêng để tải dữ liệu mở rộng.

Nén gzip hoặc Brotli có thể giảm băng thông nhưng tốn CPU và phụ thuộc cấu hình proxy/server/client. Đo kích thước trước và sau nén, đặc biệt với response đã được nén hoặc dữ liệu khó nén.

## 9. Review template rendering và View

Trong MVC server-side, thời gian render template là một phần của request. Một template lặp qua hàng nghìn dòng, thực hiện truy cập dữ liệu qua getter hoặc gọi helper có I/O có thể tạo chi phí đáng kể.

Reviewer nên kiểm tra:

- View nhận DTO đã chuẩn bị sẵn hay entity graph?
- Template có vòng lặp lớn hoặc lồng nhiều vòng không?
- Helper có truy cập database hoặc network không?
- Có lặp lại phép định dạng nặng trên từng phần tử không?
- Có render quá nhiều nội dung mà người dùng không nhìn thấy không?
- Có thể phân trang, lazy-load phần giao diện hoặc giảm nội dung không?

Không đặt truy vấn database trong template. View nên trình bày dữ liệu đã được chuẩn bị bởi application/query layer.

Với REST MVC, JSON serialization cũng có chi phí tương tự. Đo serialization time và response size nếu trace cho thấy phần controller/application đã nhanh nhưng response vẫn chậm.

## 10. Review thread, executor và connection pool

Spring MVC thường xử lý request đồng bộ trên servlet thread. Mỗi request đang chờ I/O vẫn chiếm một thread trong thời gian xử lý. Nếu traffic tăng và phụ thuộc chậm, request có thể xếp hàng, làm latency tăng ngay cả khi CPU chưa đầy.

### 10.1. Thread pool không phải giải pháp vô hạn

Tăng Tomcat max threads có thể cho phép nhiều request cùng chạy, nhưng cũng có thể làm tăng số truy vấn đồng thời và gây áp lực lên database. Thread pool, connection pool và năng lực phụ thuộc cần được cân bằng.

Theo dõi:

- Busy/active servlet threads.
- Request queue hoặc số request đang chờ.
- Executor active count và queue depth.
- Database connections active/idle/pending.
- CPU, heap, garbage collection và thread count.
- Timeout và rejected task.

Nếu servlet có 200 thread nhưng database chỉ có 20 connection, nhiều request có thể chờ connection. Tăng thread có thể làm queue dài hơn thay vì tăng throughput.

### 10.2. Đặt timeout ở mọi ranh giới I/O

HTTP client, database, cache và message client cần timeout phù hợp. Một lời gọi không timeout có thể giữ request thread hoặc worker vô thời hạn.

Timeout nên dựa trên latency budget và khả năng retry. Không đặt timeout của một dependency dài hơn toàn bộ SLO của request nếu request không còn đủ thời gian xử lý các bước còn lại.

### 10.3. Retry có giới hạn và có chủ đích

Retry có thể giúp vượt qua lỗi tạm thời, nhưng retry đồng loạt làm tăng tải khi hệ thống đang quá tải. Dùng số lần thử giới hạn, backoff có jitter và chỉ retry thao tác có thể lặp an toàn.

Với thao tác ghi như nhập kho hoặc thanh toán, cần idempotency key hoặc cơ chế phát hiện lệnh trùng. Không retry một POST không idempotent chỉ vì client chưa nhận response.

### 10.4. Bulkhead và backpressure

Tách executor cho công việc nền hoặc dependency có thể ngăn một nhóm tác vụ chiếm toàn bộ tài nguyên. Queue cần có giới hạn. Khi queue đầy, hệ thống phải từ chối hoặc điều tiết công việc theo chính sách rõ ràng thay vì nhận vô hạn và hết bộ nhớ.

Backpressure không chỉ dành cho reactive system. Mọi hệ thống có queue đều cần giới hạn khả năng nhận việc so với năng lực xử lý.

## 11. Đánh giá xử lý bất đồng bộ

Async MVC có thể giải phóng servlet thread trong khi tác vụ tiếp tục xử lý, nhưng không làm công việc biến mất. Tác vụ vẫn tiêu thụ executor thread, memory, connection và có thể tiếp tục sau khi client đã timeout.

Khi review async:

- Executor có giới hạn thread và queue không?
- Context xác thực, request ID và trace context có được truyền đúng không?
- Timeout của async request được xử lý thế nào?
- Client disconnect có hủy được công việc hay không?
- Exception từ worker được ánh xạ về response ra sao?
- Có nguy cơ gửi response hai lần hoặc ghi dữ liệu sau khi client đã bỏ request không?
- Công việc có nên trở thành background job bền vững thay vì task trong memory không?

Nếu công việc cần tiếp tục sau restart hoặc cần retry/audit, dùng job/message bền vững. Không coi Callable hoặc CompletableFuture là hàng đợi công việc có durability.

## 12. Khả năng chẩn đoán: chọn đúng tín hiệu

Logs, metrics và traces bổ sung cho nhau:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Logs | Điều gì đã xảy ra trong một sự kiện cụ thể? | ISBN bị từ chối, payment timeout |
| Metrics | Vấn đề xảy ra bao nhiêu lần và xu hướng thế nào? | p95 tăng, error rate tăng |
| Traces | Một request đi qua đâu và mất thời gian ở span nào? | Chờ database 420 ms |
| Health checks | Instance có thể sống và nhận traffic không? | Liveness, readiness |

Không có một tín hiệu nào thay thế được tất cả. Log chứa chi tiết nhưng không lý tưởng để tính latency percentile; metric tổng hợp tốt nhưng không chứa toàn bộ ngữ cảnh của một request; trace giúp theo dõi đường đi nhưng có thể được sampling.

### 12.1. Logs có cấu trúc

Log nên chứa event name, severity, service, timestamp và các field liên quan. Với request MVC, những field hữu ích gồm:

- request.id hoặc trace.id.
- http.request.method và route template.
- status code.
- duration.
- use case hoặc event name.
- error code/type khi có lỗi.
- business ID cần thiết và đã được phép ghi.

Không ghi password, token, cookie, authorization header hoặc toàn bộ request body. Tránh đưa ID biến thiên vào metric label; trong log có thể ghi ID theo chính sách bảo vệ dữ liệu.

Ví dụ một sự kiện request hoàn tất:

~~~json
{
  "@timestamp": "2026-11-19T10:21:03.412Z",
  "level": "INFO",
  "event.name": "http.request.completed",
  "request.id": "req-8f1c",
  "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http.request.method": "GET",
  "http.route": "/books",
  "http.response.status_code": 200,
  "duration_ms": 184
}
~~~

Route là template, không phải URL đầy đủ có query string hoặc giá trị nhạy cảm.

### 12.2. Metrics có cardinality thấp

Các metric quan trọng cho MVC:

- Request count theo route template, method và status class.
- Request duration histogram.
- Error rate theo loại lỗi.
- Database query duration và connection pool utilization.
- Cache hit/miss ratio.
- Executor active threads và queue depth.
- JVM CPU, heap, GC pause và thread count.
- External dependency duration/error rate.

Label nên có tập giá trị hữu hạn như route template, method, status class hoặc dependency name. Không dùng user ID, ISBN, book ID, order ID hay raw URL làm label vì số lượng chuỗi duy nhất có thể tăng không giới hạn và làm hệ thống metrics quá tải.

Một dashboard hữu ích thường hiển thị latency percentile, throughput, error rate và saturation cạnh nhau. Khi p95 tăng đồng thời DB pool pending tăng, hướng điều tra khác với trường hợp p95 tăng nhưng database bình thường và CPU rendering cao.

Với use case cần đo riêng, Micrometer Timer có thể ghi thời lượng và kết quả bằng các tag có tập giá trị giới hạn:

~~~java
public class SearchBooksService {
    private final MeterRegistry registry;
    private final BookSearchQueryHandler handler;

    public SearchBooksService(
            MeterRegistry registry,
            BookSearchQueryHandler handler) {
        this.registry = registry;
        this.handler = handler;
    }

    public BookSearchView handle(BookSearchQuery query) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return handler.handle(query);
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(
                Timer.builder("mvc.usecase.duration")
                    .tag("usecase", "book.search")
                    .tag("outcome", outcome)
                    .register(registry)
            );
        }
    }
}
~~~

Ví dụ giả định MeterRegistry, Timer và các kiểu query/view đã được cấu hình trong ứng dụng. Tag usecase và outcome có số giá trị hữu hạn; không thêm keyword tìm kiếm, book ID hoặc user ID làm tag. Nếu Spring Boot đã tự động ghi HTTP server metrics, timer này bổ sung thời lượng của use case ở một ranh giới khác, không thay thế hoặc nhân đôi metric HTTP.

Timer ghi count và tổng thời gian; để truy vấn percentile hoặc histogram ở backend, cần cấu hình phân phối phù hợp trong Micrometer registry/exporter. Không lấy trung bình các percentile cục bộ từ từng instance để đại diện cho percentile toàn hệ thống.

### 12.3. Distributed tracing

Trace mô tả một request qua nhiều span. Một trace của trang tìm kiếm có thể gồm:

~~~mermaid
flowchart LR
    HTTP["HTTP server span"]
    MVC["MVC controller span"]
    USECASE["SearchBooks use case"]
    DB["Database query span"]
    MAP["View mapping span"]
    RENDER["Template render span"]

    HTTP --> MVC --> USECASE --> DB
    USECASE --> MAP --> RENDER
~~~

Trace context nên được truyền theo chuẩn như W3C Trace Context. Nếu có gateway hoặc dịch vụ bên ngoài, các span cần cùng trace hoặc được liên kết theo đúng ngữ nghĩa.

Không tự tạo trace ID độc lập với tracing SDK. Khi sampling không giữ lại mọi trace, metrics và request ID vẫn cần đủ để phát hiện và khoanh vùng vấn đề.

### 12.4. Error code có ngữ nghĩa

Không gom mọi lỗi thành một thông báo Internal Server Error trong log và response. Phân biệt:

- Validation error: dữ liệu request sai.
- Business rule violation: hành động không hợp lệ trong trạng thái hiện tại.
- Not found: tài nguyên không tồn tại hoặc không hiển thị trong phạm vi quyền.
- Conflict: dữ liệu đã thay đổi hoặc vi phạm uniqueness/concurrency.
- Dependency failure: database hoặc dịch vụ bên ngoài lỗi.
- Unexpected failure: lỗi chưa dự kiến cần điều tra.

Error code ổn định giúp dashboard, client và support phân loại sự cố. Không đưa stack trace hoặc thông tin nội bộ vào response công khai.

## 13. Health check và readiness

Health check giúp nền tảng vận hành quyết định instance có đang sống và có thể nhận traffic không. Hai khái niệm thường gặp:

- **Liveness:** process còn hoạt động; nếu thất bại liên tục, nền tảng có thể khởi động lại instance.
- **Readiness:** instance đã sẵn sàng phục vụ request; nếu thất bại, nền tảng có thể tạm ngừng gửi traffic tới instance đó.

Không đưa mọi dependency vào liveness. Nếu database tạm thời mất kết nối và liveness thất bại, orchestrator có thể liên tục restart toàn bộ instance mà không giải quyết được nguyên nhân. Readiness có thể phản ánh dependency thiết yếu theo chính sách của hệ thống.

Health endpoint nên trả thông tin vừa đủ cho nền tảng vận hành. Không công khai hostname nội bộ, credentials, connection string hoặc chi tiết cấu hình nhạy cảm cho người dùng Internet.

Trong Spring Boot, Actuator có thể cung cấp health và metrics endpoint. Cần cấu hình quyền truy cập, exposure và probes phù hợp với môi trường triển khai; không expose mọi actuator endpoint công khai theo mặc định.

## 14. Thiết kế lỗi để dễ điều tra

Một lỗi tốt cho vận hành có ba lớp thông tin:

1. **Thông báo người dùng:** ngắn gọn, có thể hành động và không lộ chi tiết nội bộ.
2. **Error code:** ổn định để client/support phân loại.
3. **Diagnostic context:** request/trace ID, event, exception và dependency liên quan trong hệ thống nội bộ.

Ví dụ:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
            BookNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "BOOK_NOT_FOUND",
                "Không tìm thấy đầu sách được yêu cầu"
            ));
    }

    @ExceptionHandler(BookRuleViolation.class)
    ResponseEntity<ApiError> handleRuleViolation(
            BookRuleViolation exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "BOOK_STATE_CONFLICT",
                exception.getMessage()
            ));
    }
}

public record ApiError(String code, String message) {}
~~~

Ví dụ cần được điều chỉnh theo chính sách API. Với lỗi validation, có thể trả 400 và danh sách field error. Với lỗi nghiệp vụ, message chỉ nên chứa nội dung đã được phép công khai. Exception handler không nên log stack trace lặp lại nếu lỗi đã được ghi ở một tầng sở hữu rõ ràng.

### 14.1. Giữ nguyên nguyên nhân gốc

Khi chuyển exception kỹ thuật thành application exception, giữ cause để điều tra:

~~~java
try {
    paymentGateway.capture(paymentId);
} catch (PaymentGatewayException exception) {
    throw new PaymentCaptureFailedException(
        "Payment capture failed",
        exception
    );
}
~~~

Không làm mất exception gốc bằng cách chỉ tạo một RuntimeException mới với message. Cũng không ghi cùng stack trace ở mọi tầng. Chọn boundary có đủ ngữ cảnh để ghi một lần.

## 15. Quy trình chẩn đoán một request chậm

Giả sử nhân viên phản ánh trang tìm kiếm sách mất 3 giây, trong khi trước đây chỉ mất vài trăm mili giây.

Một quy trình có thể lặp lại:

### Bước 1: Xác định phạm vi

- Chỉ một route hay toàn hệ thống?
- Chỉ một tenant hoặc một nhóm người dùng?
- Chỉ khi tìm kiếm từ khóa dài hay cả khi mở trang mặc định?
- Bắt đầu từ thời điểm nào?
- Có deploy, thay đổi dữ liệu hoặc tăng traffic cùng thời điểm không?

Dùng timestamp, route template và request ID để chọn mẫu request phù hợp.

### Bước 2: Kiểm tra dashboard tổng quan

Xem p50/p95/p99, throughput, error rate, CPU, heap, GC, thread pool và DB connection pool. Xác định latency tăng cùng saturation nào.

### Bước 3: Mở trace đại diện

Tìm span chiếm nhiều thời gian nhất. Nếu database span chiếm 2,4 giây, tập trung query plan và lock. Nếu database chỉ 80 ms nhưng template rendering mất 1,8 giây, kiểm tra số dòng và logic View.

### Bước 4: Kiểm tra log cùng request/trace ID

Xem filter, validation, dependency timeout, retry, exception và kết quả. Không cần đọc log toàn hệ thống nếu đã khoanh vùng được một request.

### Bước 5: Kiểm tra dữ liệu và query plan

Tái hiện bằng dữ liệu có kích thước tương tự. Đếm số query, số rows scanned, index được dùng, lock wait và thời gian lấy connection. Không dùng dataset nhỏ trong môi trường phát triển để kết luận query sẽ nhanh ở production.

### Bước 6: Đề xuất thay đổi có giả thuyết

Ví dụ: “Trang danh sách tải 1 query sách và 50 query tác giả do lazy loading. Dùng projection lấy title và author names theo một query có join phù hợp sẽ giảm round trips.”

Một nhận xét tốt nêu rõ bằng chứng, tác động và cách xác minh sau sửa.

### Bước 7: Đo lại

Chạy lại cùng workload, cùng dữ liệu và cùng điều kiện tải. So sánh p95/p99, query count, CPU, DB load và response size. Xác nhận thay đổi không làm chậm thao tác ghi hoặc tăng memory quá mức.

## 16. Ví dụ review: trang tìm kiếm sách

Giả sử dashboard ghi nhận:

| Chỉ số | Trước điều tra |
|---|---:|
| Request rate | 35 request/giây |
| p50 latency | 220 ms |
| p95 latency | 2.8 s |
| p99 latency | 4.1 s |
| Error rate | 0.2% |
| DB pool active | Gần giới hạn |
| DB pool pending | Tăng vào giờ cao điểm |

Trace cho thấy request đọc danh sách sách trong 120 ms, sau đó phát sinh nhiều query tải tác giả và nhà xuất bản. Template render cũng duyệt toàn bộ 500 dòng vì endpoint không giới hạn page size.

Các vấn đề thiết kế:

1. Query model trả entity graph thay vì dữ liệu cần cho danh sách.
2. Quan hệ lazy tạo N+1 query.
3. Page size không bị giới hạn.
4. View render quá nhiều dòng.
5. DB connection bị giữ lâu hơn cần thiết.

Thay đổi đề xuất:

- Giới hạn page size và dùng pagination ổn định.
- Tạo projection cho danh sách gồm ID, title, authors text, publisher name và stock.
- Dùng một query phù hợp để tải dữ liệu liên quan.
- Giữ aggregate đầy đủ cho use case ghi, không dùng projection để thay đổi trạng thái.
- Đo lại query count và p95 dưới workload tương tự.

Ví dụ kết quả sau thay đổi (giả định):

| Chỉ số | Trước | Sau |
|---|---:|---:|
| p50 latency | 220 ms | 95 ms |
| p95 latency | 2.8 s | 310 ms |
| Query count/request | 52 | 2 |
| DB pool pending | Tăng giờ cao điểm | Gần 0 trong test |
| Rows render/request | 500 | 25 |

Đây là số liệu minh họa để giải thích cách trình bày bằng chứng, không phải cam kết hiệu năng của một implementation cụ thể. Khi đo thật, phải ghi lại môi trường, dataset, concurrency, cache state và thời gian chạy.

## 17. Kiểm thử và đo hiệu năng

### 17.1. Unit test không thay thế load test

Unit test xác nhận logic và bất biến. Nó không cho biết hệ thống xử lý được bao nhiêu request đồng thời hoặc DB pool có bị nghẽn không.

Các loại kiểm thử:

| Loại test | Mục tiêu |
|---|---|
| Unit test | Logic thuần và bất biến |
| Integration test | Mapping, query, transaction và dependency |
| Load test | Hiệu năng ở tải dự kiến |
| Stress test | Tìm điểm hệ thống bắt đầu suy giảm |
| Spike test | Phản ứng với tăng tải đột ngột |
| Soak test | Rò rỉ memory, queue hoặc suy giảm theo thời gian |
| Profiling | Tìm CPU hot path, allocation và lock contention |

### 17.2. Thiết kế load test có ý nghĩa

Load test nên mô phỏng:

- Tỷ lệ đọc/ghi gần thực tế.
- Dữ liệu có kích thước đại diện.
- Request có filter và page size đa dạng.
- Người dùng đồng thời và ramp-up.
- Cache warm/cold theo tình huống.
- Tác vụ nền chạy cùng lúc.
- Thời gian warm-up và thời gian đo ổn định.

Không dùng một request duy nhất chạy lặp trong khi cache đã warm để đại diện cho mọi traffic. Không chạy test phá tải trên production nếu chưa có kế hoạch và giới hạn rõ.

### 17.3. Profiling trước khi tối ưu

Profiler có thể cho biết CPU tiêu tốn ở đâu, allocation nào gây GC, thread nào đang block và lock nào gây contention. Dùng flame graph hoặc sampling profiler để tìm hot path trước khi viết lại code.

Tránh tối ưu dựa trên cảm giác. Một vòng lặp nhỏ có thể không đáng kể nếu 90% thời gian chờ database. Ngược lại, một mapper tạo hàng triệu object có thể gây GC pause khi xử lý báo cáo lớn.

### 17.4. Đặt regression guard

Sau khi có baseline, có thể đặt ngưỡng kiểm tra trong pipeline hoặc môi trường performance test:

- p95 không vượt ngưỡng đã thống nhất.
- Query count cho use case quan trọng không tăng bất thường.
- Response size không vượt giới hạn.
- Không xuất hiện N+1.
- Error rate và timeout không tăng.
- Bộ nhớ và CPU nằm trong giới hạn dự kiến.

Không nên làm build thất bại vì một con số benchmark nhiễu. Dùng môi trường ổn định, nhiều lần chạy và ngưỡng có biên độ phù hợp.

## 18. Checklist review hiệu năng

Khi review một use case MVC, hãy kiểm tra:

- Workload và mục tiêu p95/p99 đã được xác định chưa?
- Đã đo end-to-end hay chỉ benchmark một method?
- Có biết request chờ ở tầng nào không?
- Query có dùng index phù hợp không?
- Có N+1 hoặc tải entity graph thừa không?
- Có pagination và giới hạn page size không?
- Transaction có giữ connection trong lúc gọi dịch vụ ngoài không?
- Có cache thật sự cần thiết và có invalidation rõ không?
- Response có quá lớn hoặc serialize entity graph không?
- Template có vòng lặp lớn hoặc logic truy cập dữ liệu không?
- Thread pool, executor và DB pool có cân bằng không?
- Timeout, retry, queue limit và backpressure có được định nghĩa không?
- Load test dùng dữ liệu và workload đại diện chưa?
- Có baseline để so sánh trước/sau không?

## 19. Checklist review khả năng chẩn đoán

- Request có request ID/trace ID xuyên suốt không?
- Log có event name và field ổn định không?
- Có route template và status code không?
- Metrics có request rate, latency percentile, error rate và saturation không?
- Metric labels có cardinality thấp không?
- Trace có span cho database và dependency quan trọng không?
- Error code có ổn định và phân biệt lỗi nghiệp vụ/kỹ thuật không?
- Stack trace có được ghi ở một boundary phù hợp không?
- Health và readiness phản ánh đúng khả năng phục vụ không?
- Log có tránh token, PII và request body nhạy cảm không?
- Có dashboard và alert cho SLO quan trọng không?
- Có quy trình từ symptom đến trace, log, query plan và xác minh sau sửa không?

## 20. Những sai lầm thường gặp

### Chỉ đo thời gian ở Controller

Timer tổng không cho biết phần nào chậm. Thêm trace/span hoặc timer ở dependency quan trọng để phân rã latency.

### Chỉ xem average latency

Average che giấu tail latency. Theo dõi histogram và percentile với đúng cách tổng hợp.

### Tăng thread pool để xử lý mọi vấn đề

Tăng thread có thể làm tăng số request cạnh tranh DB connection và gây quá tải phụ thuộc. Đo queue và saturation trước khi thay cấu hình.

### Thêm cache trước khi đo

Cache có thể che query kém trong một thời gian nhưng thêm stale data, invalidation và cache stampede. Xác định bottleneck rồi mới chọn chiến lược.

### Tối ưu một query mà không xem transaction

Query nhanh vẫn có thể bị lock hoặc connection pool chờ. Đánh giá transaction duration, lock và concurrency.

### Đo trên dữ liệu nhỏ

Index, pagination và query plan có thể khác hoàn toàn khi bảng có hàng triệu dòng. Dùng dataset đại diện.

### Ghi quá nhiều log thay cho metrics/traces

Log mỗi query hoặc mỗi vòng lặp tạo log storm và chi phí cao. Dùng metrics cho xu hướng, trace cho đường đi, log cho sự kiện cụ thể.

### Dùng ID biến thiên làm metric label

User ID, book ID và raw URL làm cardinality tăng không giới hạn. Đưa ID vào log/trace khi phù hợp; metric dùng route template và nhóm giá trị hữu hạn.

### Bật liveness phụ thuộc tất cả dịch vụ

Một dependency tạm lỗi có thể làm instance bị restart liên tục. Phân biệt liveness với readiness và chọn dependency thiết yếu.

### Retry không giới hạn

Retry khuếch đại tải và có thể lặp side effect. Dùng timeout, giới hạn retry, backoff/jitter và idempotency.

### Chỉ kiểm thử tải ở cuối dự án

Thiết kế pool, query và payload sai có thể phải sửa sâu khi phát hiện muộn. Xây baseline cho use case quan trọng sớm trong vòng đời phát triển.

## 21. Mẫu nhận xét trong một design review

Một nhận xét có thể hành động nên có bốn phần:

1. **Quan sát:** điều gì trong thiết kế hoặc số liệu gây lo ngại?
2. **Tác động:** người dùng hoặc hệ thống sẽ bị ảnh hưởng thế nào?
3. **Bằng chứng:** trace, query count, metric, code path hoặc workload nào xác nhận?
4. **Đề xuất và xác minh:** thay đổi nào nên thực hiện và đo lại bằng cách nào?

Ví dụ:

~~~text
Finding: High - Search endpoint has an unbounded page size and loads
publisher/author relations lazily while rendering the list.

Impact: Large requests can create hundreds of database round trips,
hold connections longer and increase p95 latency during peak traffic.

Evidence: A representative trace shows 1 list query followed by
N author/publisher queries. The request renders up to 500 rows.

Recommendation: Cap page size, use a list projection and fetch the
required author/publisher data in a bounded query. Keep the full
aggregate for write use cases.

Verification: Run the same load profile and compare p95/p99,
query count, DB pool pending and response size.
~~~

Mức độ ưu tiên nên dựa trên xác suất, tác động, mức độ phơi nhiễm và khả năng khắc phục. Một vấn đề bảo mật hoặc nguy cơ mất dữ liệu có thể cần ưu tiên cao hơn một cải thiện latency nhỏ.

## 22. Quy trình đánh giá từ thiết kế đến production

1. **Trước khi triển khai:** xác định workload, use case quan trọng, SLO và latency budget.
2. **Trong design review:** lần theo request path, query, transaction, cache, pool và error boundary.
3. **Trong implementation:** thêm instrumentation ở ranh giới có ý nghĩa; giữ metric labels có cardinality thấp.
4. **Trong test:** kiểm tra query count, integration, load và stress với dữ liệu đại diện.
5. **Trước phát hành:** xác nhận dashboard, alert, health/readiness, timeout và rollback plan.
6. **Sau phát hành:** so sánh baseline, theo dõi SLO và kiểm tra các trace/log đại diện.
7. **Sau sự cố:** ghi nhận nguyên nhân gốc, tín hiệu đã thiếu và thay đổi giúp lần sau chẩn đoán nhanh hơn.

Hiệu năng và khả năng chẩn đoán cần được xem xét lại khi workload, schema, dependency hoặc cách triển khai thay đổi. Một thiết kế từng phù hợp có thể không còn phù hợp khi số lượng dữ liệu hoặc traffic tăng lên.

## 23. Kết luận

Đánh giá hiệu năng và khả năng chẩn đoán trong MVC phải bao phủ toàn bộ request path: từ filter, Controller, Application Service, Domain và Repository đến database, dependency, mapping và rendering. Reviewer cần bắt đầu từ workload và SLO, đo latency percentile, throughput, error rate và saturation, sau đó kiểm tra query, transaction, cache, payload, thread pool và các giới hạn tài nguyên.

Khả năng chẩn đoán cần logs, metrics, traces, error code và health checks có ngữ nghĩa rõ. Khi một request chậm, nhóm phải có thể lần từ triệu chứng đến span, query, resource hoặc tầng xử lý gây nghẽn, rồi xác minh cải thiện bằng cùng workload. Một design review tốt không chỉ nói “cần tối ưu” mà đưa ra bằng chứng, tác động, đề xuất và cách đo lại để thay đổi có thể được kiểm chứng.

