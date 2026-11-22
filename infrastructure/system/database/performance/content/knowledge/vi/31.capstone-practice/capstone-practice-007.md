# Khắc phục N+1 và đo số lượt truy vấn trong ứng dụng Java

Một endpoint Java có thể chỉ cần trả về danh sách 30 đơn hàng cùng tên khách hàng, nhưng ORM lại gửi 31 câu SQL: một câu lấy danh sách đơn và 30 câu lấy từng khách hàng. Đây là lỗi N+1. Mỗi câu riêng lẻ có thể chạy nhanh, nhưng tổng thời gian tăng theo số bản ghi, tạo thêm round trip qua mạng, giữ connection lâu hơn và làm database xử lý nhiều statement không cần thiết.

Trong DATABASE_PERFORMANCE, khắc phục N+1 là tối ưu đường truy cập dữ liệu từ ứng dụng đến database. Cần xác định quan hệ nào được tải lặp, chọn cách lấy dữ liệu phù hợp với use case, đo số statement và round trip trước/sau, sau đó kiểm chứng bằng dữ liệu có quy mô đại diện. Mục tiêu không phải gom mọi thứ vào một câu SQL thật lớn. Một truy vấn join quá rộng có thể nhân số hàng, tải nhiều cột và tiêu thụ bộ nhớ hơn một vài truy vấn có chủ đích.

Bài thực hành này sử dụng Java, JDBC và JPA/Hibernate làm ví dụ. Các nguyên tắc cũng áp dụng cho ORM hoặc data access framework khác: truy vấn phải phù hợp với dữ liệu cần hiển thị, số lần truy cập phải có giới hạn rõ ràng và hiệu năng cần được đo trên toàn bộ thao tác nghiệp vụ.

## 1. N+1 là gì?

N+1 xảy ra khi ứng dụng chạy một truy vấn ban đầu để lấy N đối tượng, rồi phát sinh thêm một truy vấn cho từng đối tượng hoặc từng quan hệ được truy cập. Tổng số truy vấn thường là:

\[
Q(N) = 1 + N
\]

Nếu mỗi đối tượng còn kích hoạt một truy vấn khác để lấy một quan hệ lồng nhau, số truy vấn có thể tăng theo nhiều tầng.

### 1.1. Ví dụ đơn hàng và khách hàng

Giả sử API cần trả về 50 đơn hàng, mỗi đơn hàng hiển thị mã đơn và tên khách hàng.

Truy vấn đầu:

~~~sql
SELECT id, customer_id, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Sau đó, khi code gọi order.getCustomer().getName(), ORM có thể phát sinh truy vấn riêng cho từng customer:

~~~sql
SELECT id, name
FROM customers
WHERE id = ?;
~~~

Nếu có 50 đơn hàng và mỗi lần truy cập customer đều gây một lần đọc, số statement là 1 + 50 = 51. Nếu có nhiều đơn cùng một customer, cache cấp một của persistence context có thể giảm số lần đọc lặp cho cùng một entity trong một transaction, nhưng không nên dựa vào điều đó để bảo đảm query count.

### 1.2. N+1 không chỉ xảy ra với quan hệ to-one

Các tình huống thường gặp:

- Danh sách đơn hàng và customer: một truy vấn danh sách, sau đó một truy vấn cho từng customer.
- Danh sách bài viết và comments: một truy vấn bài viết, sau đó một truy vấn comments cho mỗi bài.
- Danh sách nhân viên và phòng ban: truy vấn nhân viên, rồi truy vấn phòng ban khi serialize.
- GraphQL resolver: resolver cha lấy danh sách, resolver con gọi repository riêng cho từng phần tử.
- Mapping DTO: vòng lặp gọi service/repository để bổ sung từng thuộc tính.

Quan hệ collection thường tạo N+1 dễ nhận thấy hơn vì danh sách có thể chứa nhiều phần tử. Quan hệ to-one cũng có thể gây N+1 khi fetch type hoặc query plan khiến ORM tải quan hệ theo từng entity.

### 1.3. N+1 lồng nhau

Giả sử một trang hiển thị 20 đơn hàng, mỗi đơn có customer và mỗi customer có địa chỉ. Nếu code lần lượt truy cập hai quan hệ lazy, số truy vấn có thể gần:

\[
Q(N) = 1 + N + N
\]

Nếu mỗi đơn còn tải một collection riêng gồm nhiều dòng chi tiết, số câu lệnh có thể tăng thêm theo số đơn. Với nhiều tầng quan hệ, cần xem toàn bộ đường truy cập của use case thay vì chỉ sửa truy vấn đầu tiên.

## 2. Vì sao N+1 làm hệ thống chậm?

### 2.1. Round trip tăng

Mỗi statement có thể cần gửi lệnh qua driver và network, database phân tích/kiểm tra, thực thi và trả kết quả. Một câu SELECT theo primary key có thể chỉ tốn ít CPU nhưng 100 lần gửi/nhận vẫn có chi phí mạng và điều phối.

Nếu database ở máy khác hoặc qua proxy, round trip có thể đáng kể so với thời gian xử lý trong database. Độ trễ của từng lần gọi cộng dồn làm thời gian endpoint tăng.

### 2.2. Chi phí parse, plan và thực thi lặp

Prepared statement và plan cache có thể giảm chi phí chuẩn bị, nhưng không loại bỏ hoàn toàn việc thực thi nhiều statement. Database vẫn phải kiểm tra quyền, bind tham số, tìm dữ liệu, tạo kết quả và ghi nhận thống kê cho mỗi lần chạy.

### 2.3. Connection bị giữ lâu

Một request thực hiện hàng chục truy vấn tuần tự sẽ giữ connection lâu hơn. Khi traffic tăng, connection pool dễ đầy, request khác phải chờ acquire và p95/p99 tăng ở cả endpoint không có N+1.

### 2.4. Tăng tải database và cạnh tranh tài nguyên

N+1 làm tăng số lần truy cập index, buffer cache, CPU và I/O. Nếu các truy vấn riêng lẻ đọc cùng dữ liệu, cache có thể giúp giảm physical reads, nhưng database vẫn phải xử lý số statement và logical reads lớn hơn cần thiết.

### 2.5. Độ trễ tăng theo kích thước danh sách

Nếu số truy vấn tăng tuyến tính theo N, thời gian endpoint có thể tăng gần tuyến tính hoặc tệ hơn khi database bắt đầu bão hòa. Một endpoint chạy tốt với 5 bản ghi có thể chậm rõ rệt với 100 hoặc 500 bản ghi.

## 3. Nhận diện N+1 trong ứng dụng Java

### 3.1. Bật SQL logging trong môi trường phù hợp

Hibernate có thể ghi SQL được phát sinh. Với Spring Boot, cấu hình minh họa:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Không nên bật bind parameter logging rộng rãi trên production vì log có thể chứa email, token, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Dùng môi trường phát triển/test hoặc bật có thời hạn với masking và quyền truy cập phù hợp.

Tìm mẫu lặp:

~~~sql
SELECT ... FROM orders WHERE status = ?;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
...
~~~

Một truy vấn có cùng cấu trúc SQL nhưng chạy nhiều lần với các giá trị bind khác nhau là dấu hiệu cần điều tra. Tuy nhiên, truy vấn lặp không phải lúc nào cũng là N+1; có thể là các thao tác độc lập có chủ đích. Cần nối SQL với use case và call stack.

### 3.2. Xem truy vấn theo request

Log SQL toàn ứng dụng khó biết câu lệnh nào thuộc cùng một request. Nên gắn trace ID hoặc request ID vào log và tracing, đồng thời ghi:

- Endpoint hoặc operation.
- Tổng số statement trong request.
- Thời gian thực thi từng statement.
- Query fingerprint thay vì lưu nguyên giá trị nhạy cảm.
- Connection pool wait và thời gian giữ connection.
- Số hàng trả về nếu công cụ hỗ trợ.

OpenTelemetry hoặc APM có thể tạo span database cho từng lệnh. Khi một request có hàng chục span SQL cùng fingerprint, đó là tín hiệu mạnh để kiểm tra N+1.

### 3.3. Dùng Hibernate Statistics

Hibernate cung cấp Statistics API để quan sát số prepared statement, entity load/fetch, collection fetch và các hoạt động ORM khác. Có thể bật:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Trong ứng dụng có quyền truy cập SessionFactory:

~~~java
Statistics statistics = sessionFactory.getStatistics();

long before = statistics.getPrepareStatementCount();
// Thực hiện một use case cần đo trong môi trường kiểm thử.
long after = statistics.getPrepareStatementCount();

long preparedStatements = after - before;
~~~

Ví dụ chỉ minh họa cách lấy chênh lệch counter. Statistics thường có phạm vi SessionFactory và là counter tích lũy; nhiều request đồng thời có thể làm phép trừ bị lẫn hoạt động của request khác. Không reset global statistics trong production chỉ để đo một request. Dùng test cô lập, request-scoped instrumentation hoặc datasource proxy để đếm chính xác hơn.

prepare statement count không phải lúc nào cũng bằng số round trip thực tế. Driver có thể reuse prepared statement, batch nhiều thao tác hoặc thực hiện nhiều lần execute trên cùng statement. Cần hiểu metric của công cụ đang dùng.

## 4. Đo số statement và round trip ở tầng JDBC

Đo ở datasource hoặc JDBC proxy giúp quan sát những gì ứng dụng gửi qua JDBC, kể cả khi ORM hoặc repository ẩn chi tiết.

### 4.1. Datasource proxy

Thư viện datasource-proxy có thể bọc DataSource để đếm và ghi nhận query execution. Ví dụ khái niệm:

~~~java
DataSource monitoredDataSource =
    ProxyDataSourceBuilder.create(realDataSource)
        .name("application-db")
        .countQuery()
        .build();
~~~

Sau khi một use case hoàn tất trong test cô lập, có thể đọc query count từ QueryCountHolder theo API của phiên bản thư viện đang dùng. Cần kiểm tra đúng dependency và API version; không coi đoạn minh họa là cấu hình hoàn chỉnh cho mọi phiên bản.

Ưu điểm:

- Đếm câu lệnh được thực thi qua JDBC.
- Ghi nhận thời gian query và loại statement.
- Có thể tích hợp listener để phát hiện query lặp.
- Phù hợp để đặt query budget trong integration test.

Giới hạn:

- Không nhất thiết đếm được các round trip nội bộ của driver hoặc protocol.
- Batch execution có thể được ghi nhận khác với số row được cập nhật.
- Query chạy ngoài datasource đã bọc sẽ không được đếm.
- Instrumentation có overhead và cần cấu hình log an toàn.

### 4.2. P6Spy

P6Spy có thể ghi nhận SQL đi qua JDBC và thời gian thực thi. Đây là công cụ hữu ích để nhìn mẫu truy vấn lặp, nhưng log có thể chứa dữ liệu bind. Cần cấu hình masking, thời gian bật và retention phù hợp.

### 4.3. StatementInspector

Hibernate StatementInspector cho phép quan sát hoặc biến đổi SQL trước khi Hibernate gửi statement. Có thể dùng để gắn tag, đếm hoặc phát hiện mẫu SQL lặp trong môi trường kiểm thử.

Đây là điểm quan sát SQL do Hibernate tạo, không phải bộ đếm round trip tổng quát cho mọi truy cập JDBC. Nếu ứng dụng có nhiều datasource hoặc dùng JDBC trực tiếp, cần instrumentation ở mỗi đường truy cập.

## 5. Cách khắc phục N+1

Không có một chiến lược fetch phù hợp cho mọi quan hệ. Chọn theo số lượng hàng, quan hệ to-one/to-many, phân trang, kích thước kết quả và mục tiêu của endpoint.

Các lựa chọn thường dùng:

1. JOIN FETCH hoặc fetch join cho quan hệ cần lấy cùng lúc.
2. EntityGraph để khai báo fetch plan theo use case.
3. Batch fetching để gom nhiều lazy load vào một số truy vấn IN.
4. DTO projection để chỉ lấy cột cần thiết.
5. Hai bước có chủ đích: lấy trang ID trước, rồi tải dữ liệu liên quan cho các ID đó.
6. DataLoader hoặc batching ở tầng resolver/service khi truy cập theo key.

## 6. JOIN FETCH cho quan hệ to-one

Nếu endpoint luôn cần customer cùng order, có thể tải bằng một truy vấn:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        join fetch o.customer
        where o.status = :status
        order by o.createdAt desc
        """)
    List<Order> findWithCustomerByStatus(
        @Param("status") OrderStatus status
    );
}
~~~

Khi gọi repository, ORM lấy Order và Customer trong cùng kết quả join. Việc truy cập order.getCustomer().getName() không cần phát sinh truy vấn riêng nếu quan hệ đã được fetch.

### 6.1. INNER JOIN hay LEFT JOIN?

INNER JOIN chỉ trả order có customer phù hợp. Nếu quan hệ optional và cần giữ cả order chưa có customer, dùng LEFT JOIN FETCH. Chọn join theo ngữ nghĩa dữ liệu, không chỉ theo hiệu năng.

### 6.2. JOIN FETCH không phải luôn tốt

Join có thể nhân số hàng khi tải collection. Nếu một order có 10 order lines và 5 tags, join đồng thời hai collection có thể tạo tích 10 x 5 = 50 hàng cho một order. ORM phải khử trùng lặp entity và xử lý result set lớn.

Với quan hệ to-one, fetch join thường ít rủi ro nhân hàng hơn. Với collection, cần xem kích thước, số quan hệ và cách phân trang.

## 7. EntityGraph theo use case

EntityGraph cho phép chỉ định quan hệ cần fetch trong một phương thức repository, thay vì đặt mọi quan hệ thành EAGER ở entity.

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {"customer"})
    List<Order> findByStatusOrderByCreatedAtDesc(
        OrderStatus status
    );
}
~~~

EntityGraph mô tả fetch plan, còn cách ORM hiện thực có thể phụ thuộc provider và loại quan hệ. Sau khi thêm EntityGraph, vẫn phải xem SQL thực tế và query count để xác nhận N+1 đã được loại bỏ.

Không đặt toàn bộ quan hệ thành EAGER để “sửa” N+1. Điều đó có thể khiến mọi use case tải dữ liệu không cần thiết, tạo join rộng hoặc truy vấn phụ ngoài dự kiến. Hãy chọn fetch plan theo từng màn hình hoặc operation.

## 8. Batch fetching cho quan hệ lazy

Batch fetching gom nhiều lần tải lazy thành một số truy vấn dùng IN thay vì một truy vấn cho mỗi entity.

Ví dụ cấu hình Hibernate:

~~~java
@Entity
@BatchSize(size = 32)
class Customer {
    // fields and mappings
}
~~~

Hoặc cấu hình mặc định:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Khi code truy cập customer của nhiều order, Hibernate có thể tải một nhóm customer trong một câu SQL với nhiều ID:

~~~sql
SELECT id, name
FROM customers
WHERE id IN (?, ?, ?, ...);
~~~

Nếu có 100 customer cần tải và batch size là 32, số lần tải quan hệ có thể gần 4 thay vì 100, ngoài truy vấn ban đầu. Số thực tế phụ thuộc số ID duy nhất, cache, provider và cách truy cập.

### 8.1. Chọn batch size

Batch size quá nhỏ vẫn tạo nhiều truy vấn. Batch size quá lớn có thể tạo danh sách tham số lớn, SQL dài, memory pressure hoặc vượt giới hạn bind parameter của engine/driver.

Chọn giá trị bằng benchmark trên dữ liệu đại diện. Kiểm tra giới hạn bind parameter, kích thước packet và plan của truy vấn IN trên hệ quản trị đang dùng.

### 8.2. Batch fetching không giống JDBC batch write

Batch fetching là gom việc tải entity/collection để giảm số SELECT. JDBC batching thường gom nhiều INSERT/UPDATE/DELETE để giảm round trip khi ghi. Hai kỹ thuật giải quyết hai loại vấn đề khác nhau.

## 9. DTO projection: chỉ lấy dữ liệu cần hiển thị

Nếu endpoint chỉ cần mã đơn, tên khách hàng và tổng tiền, không nhất thiết phải tải entity đầy đủ cùng toàn bộ quan hệ. DTO projection cho phép truy vấn đúng các cột cần:

~~~java
public record OrderSummary(
    Long orderId,
    String customerName,
    BigDecimal totalAmount
) {}
~~~

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select new com.example.api.OrderSummary(
            o.id,
            c.name,
            o.totalAmount
        )
        from Order o
        join o.customer c
        where o.status = :status
        order by o.createdAt desc
        """)
    List<OrderSummary> findSummaries(
        @Param("status") OrderStatus status
    );
}
~~~

Projection tránh tải entity và quan hệ không cần thiết, giảm dữ liệu truyền từ database và công việc hydration của ORM. Cần dùng tên package DTO đúng với dự án.

Nếu quan hệ customer là optional, thay join bằng left join và xử lý customerName có thể null theo nghiệp vụ.

## 10. Hai bước có chủ đích cho collection lớn

Khi cần phân trang order nhưng mỗi order có nhiều lines, fetch join collection trực tiếp với Pageable có thể làm số hàng join tăng mạnh và phá vỡ giới hạn trang ở cấp entity.

Một cách phổ biến:

1. Lấy trang ID của order theo điều kiện và thứ tự.
2. Tải order cùng customer hoặc collection cần thiết bằng một truy vấn cho danh sách ID.
3. Khôi phục thứ tự theo danh sách ID ban đầu nếu IN query không bảo đảm thứ tự.

Ví dụ:

~~~java
@Query("""
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findPageIds(
    @Param("status") OrderStatus status,
    Pageable pageable
);

@Query("""
    select distinct o
    from Order o
    left join fetch o.customer
    left join fetch o.lines
    where o.id in :ids
    """)
List<Order> findGraphByIds(@Param("ids") Collection<Long> ids);
~~~

Query page có thể cần thêm một câu COUNT để tính tổng số trang. Câu COUNT là chi phí có chủ đích của pagination, không phải N+1. Nếu client không cần tổng số trang, có thể dùng Slice hoặc keyset pagination để tránh count toàn bộ.

Không join fetch nhiều collection lớn cùng lúc nếu chúng tạo tích hàng. Có thể tải từng collection theo batch hoặc truy vấn riêng theo danh sách ID.

### 10.1. Khôi phục thứ tự

SQL với điều kiện IN không bảo đảm trả kết quả theo thứ tự của danh sách ID. Nếu API cần thứ tự theo createdAt, hãy thêm ORDER BY phù hợp hoặc sắp xếp lại trong ứng dụng dựa trên thứ tự ID đã lấy.

### 10.2. Keyset pagination

Với dữ liệu lớn, OFFSET cao có thể khiến database phải đọc/bỏ qua nhiều hàng. Keyset pagination dùng khóa cuối của trang trước:

~~~sql
SELECT id, created_at
FROM orders
WHERE status = 'PAID'
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Cú pháp row comparison có hỗ trợ khác nhau theo engine; có thể viết thành điều kiện OR tương đương. Index phù hợp thường cần status, created_at và id theo thứ tự truy cập. Kiểm tra execution plan thực tế.

## 11. Xử lý N+1 ở GraphQL hoặc service layer

N+1 không chỉ do ORM lazy loading. Trong GraphQL, resolver của mỗi order có thể gọi CustomerService.findById riêng. Trong service layer, vòng lặp có thể gọi repository nhiều lần:

~~~java
for (Order order : orders) {
    Customer customer = customerService.findById(order.getCustomerId());
    summaries.add(toSummary(order, customer));
}
~~~

Có thể thay bằng batch lookup:

~~~java
Set<Long> customerIds = orders.stream()
    .map(Order::getCustomerId)
    .collect(Collectors.toSet());

Map<Long, Customer> customers =
    customerRepository.findAllById(customerIds).stream()
        .collect(Collectors.toMap(Customer::getId, Function.identity()));

List<OrderSummary> summaries = orders.stream()
    .map(order -> toSummary(
        order,
        customers.get(order.getCustomerId())
    ))
    .toList();
~~~

Số lần truy cập customer trở thành một truy vấn theo tập ID thay vì một truy vấn cho từng order. Với danh sách rất lớn, chia batch theo kích thước phù hợp.

Ở GraphQL, DataLoader hỗ trợ gom các key được resolver yêu cầu trong cùng một execution window. Cần bảo đảm loader có scope theo request để tránh rò rỉ dữ liệu giữa người dùng hoặc tenant.

## 12. Đo query count trước và sau khi sửa

Không thể xác nhận N+1 đã được sửa chỉ bằng việc nhìn code. Cần đo số statement cho một use case với số bản ghi đủ lớn.

### 12.1. Thiết lập phép đo cô lập

Một phép đo đáng tin cậy cần:

1. Tạo fixture có số lượng bản ghi đã biết.
2. Flush dữ liệu seed xuống database.
3. Clear persistence context để tránh entity đã nằm trong first-level cache.
4. Clear bộ đếm query sau phần setup.
5. Chạy đúng use case cần đo.
6. Đọc query count và thời gian.
7. Đối chiếu số query với số phần tử đầu vào.

Nếu dùng second-level cache hoặc query cache, cần quyết định rõ muốn đo cache nóng hay đường đi database thật. Đối với kiểm tra N+1, thường cần kiểm soát cache để mỗi test có điều kiện nhất quán.

### 12.2. Ví dụ kiểm thử với Hibernate Statistics

~~~java
@SpringBootTest
class OrderQueryCountTest {

    @Autowired
    private EntityManager entityManager;

    @Autowired
    private OrderService orderService;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void loadsOrderSummariesWithinQueryBudget() {
        entityManager.flush();
        entityManager.clear();

        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = sessionFactory.getStatistics();
        statistics.clear();

        List<OrderSummary> result =
            orderService.findPaidOrderSummaries();

        long statementCount =
            statistics.getPrepareStatementCount();

        assertThat(result).hasSize(50);
        assertThat(statementCount).isLessThanOrEqualTo(2);
    }
}
~~~

Đây là ví dụ cho một test chạy cô lập, không có request khác dùng cùng SessionFactory trong lúc đo. Nếu use case dùng pagination, câu COUNT có thể làm tổng là 2. Nếu có thêm truy vấn lấy dữ liệu phụ có chủ đích, điều chỉnh budget theo hợp đồng của use case.

Statistics là bộ đếm toàn SessionFactory. Trong test song song hoặc ứng dụng có nhiều request, phép đo có thể bị nhiễu. Có thể tắt parallel execution cho nhóm test này hoặc dùng datasource proxy với context đo riêng.

### 12.3. Kiểm tra số query không tăng theo N

Một cách mạnh hơn là chạy cùng use case với hai kích thước dữ liệu:

| Số order | N+1 chưa sửa | Fetch plan theo batch |
|---:|---:|---:|
| 10 | 11 query | 1-2 query |
| 50 | 51 query | 1-3 query |
| 100 | 101 query | 1-5 query |

Các số ở cột batch chỉ minh họa. Điều quan trọng là số query không tăng một lần cho mỗi entity. Nếu batch size cố định, số query có thể tăng theo số batch nhưng tăng chậm và có giới hạn rõ.

## 13. Đặt query budget trong integration test

Query budget là giới hạn số statement cho một use case. Ví dụ:

- Lấy danh sách 50 order summary: tối đa 2 statement nếu có query trang và count.
- Lấy chi tiết một order cùng customer và lines: tối đa 2-3 statement theo fetch plan.
- Tải 100 customer theo ID: tối đa một truy vấn cho batch đủ nhỏ hoặc một số batch đã định.

Không đặt một con số chung cho mọi endpoint. Budget cần phản ánh yêu cầu chức năng, pagination, consistency và chiến lược tải dữ liệu.

### 13.1. Tránh assertion quá mong manh

Nếu test chỉ assert chính xác bằng 1 query, một thay đổi hợp lệ như thêm query kiểm tra quyền hoặc COUNT có thể làm test thất bại dù không có N+1. Hãy chọn giữa:

- Exact count khi query shape là một phần hợp đồng rõ ràng.
- Upper bound khi có thể có thêm truy vấn hợp lệ.
- Kiểm tra số query không tăng tuyến tính khi N tăng.
- Kiểm tra query fingerprint lặp lại quá nhiều lần.

Query budget vẫn cần đủ chặt để phát hiện regression. Nếu đặt giới hạn quá rộng, test không còn giá trị.

### 13.2. Tách phần setup khỏi phần đo

Không tính truy vấn tạo fixture, cleanup hoặc transaction test vào query count của use case. Reset bộ đếm sau setup hoặc dùng listener có scope. Nếu dùng transaction test tự rollback, cần xác nhận flush và clear đã diễn ra trước khi đo.

## 14. Đo thời gian và số liệu database cùng lúc

Giảm query count không tự động bảo đảm endpoint nhanh hơn. Một JOIN FETCH có thể trả về nhiều hàng trùng, một truy vấn IN quá lớn có thể tạo plan kém, và DTO projection có thể quét nhiều dữ liệu nếu thiếu index.

Sau khi giảm số statement, đo:

- Tổng thời gian endpoint và p50/p95/p99.
- Số statement và số round trip quan sát được.
- Tổng thời gian SQL, không chỉ thời gian từng câu.
- Logical reads và physical reads.
- Số hàng được đọc/trả về.
- CPU database và ứng dụng.
- Kích thước result set và bộ nhớ hydration.
- Connection acquire time và usage duration.
- Lock wait hoặc transaction duration nếu có ghi.

### 14.1. Phân biệt statement count và physical I/O

Một SELECT có thể được phục vụ từ buffer cache, do đó không phát sinh physical read nhưng vẫn là một statement và có logical reads. Ngược lại, một statement scan lớn có thể đọc hàng nghìn page.

Query count đo số lần ứng dụng gửi lệnh; database I/O đo lượng page/block được truy cập. Hai chỉ số bổ sung cho nhau.

### 14.2. Dùng execution plan

Với truy vấn được sửa bằng JOIN hoặc IN, kiểm tra:

- Index được chọn có phù hợp predicate và join key không?
- Estimated rows có gần actual rows không?
- Có scan quá rộng hoặc nested loop lặp nhiều lần không?
- Có sort/hash spill hoặc memory grant lớn không?
- Có duplicate row do join collection không?
- Có partition pruning khi lọc theo partition key không?

Trong môi trường test, dùng EXPLAIN ANALYZE hoặc công cụ tương ứng để xem actual behavior. Trên production, chọn phương pháp thu thập plan an toàn, tránh thực thi lại query nặng chỉ để lấy số liệu.

## 15. Ví dụ thực hành: sửa endpoint danh sách đơn hàng

### 15.1. Phiên bản có N+1

~~~java
public List<OrderSummary> findPaidOrders() {
    List<Order> orders = orderRepository.findByStatus(
        OrderStatus.PAID
    );

    return orders.stream()
        .map(order -> new OrderSummary(
            order.getId(),
            order.getCustomer().getName(),
            order.getTotalAmount()
        ))
        .toList();
}
~~~

Nếu customer là LAZY, vòng map có thể phát sinh thêm một SELECT cho từng customer chưa được tải.

### 15.2. Phiên bản projection

~~~java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        c.name,
        o.totalAmount
    )
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderSummary> findSummariesByStatus(
    @Param("status") OrderStatus status
);
~~~

Service gọi repository projection:

~~~java
public List<OrderSummary> findPaidOrders() {
    return orderRepository.findSummariesByStatus(
        OrderStatus.PAID
    );
}
~~~

Truy vấn trả trực tiếp dữ liệu cần cho API, không tải entity customer riêng. Nếu endpoint cần phân trang, dùng Pageable hoặc thiết kế keyset pagination và tính cả query count phục vụ pagination.

### 15.3. Kết quả kỳ vọng

| Đặc điểm | Trước | Sau |
|---|---|---|
| Truy vấn lấy order | 1 | 1 |
| Truy vấn lấy customer | Có thể N | 0 truy vấn riêng |
| Tổng statement | 1 + N | Thường 1, có thể thêm count khi phân trang |
| Dữ liệu ORM hydrate | Entity và quan hệ lazy | DTO projection |
| Rủi ro | Query lặp theo số order | Cần kiểm tra join, filter và index |

Kết quả thực tế phải được xác nhận bằng SQL log, query counter và execution plan. Nếu join làm số hàng tăng hoặc cần lấy collection lớn, một phương án hai bước có thể phù hợp hơn.

## 16. Các lưu ý về transaction, cache và serialization

### 16.1. First-level cache có thể che N+1

Persistence context của JPA giữ một identity map. Nếu nhiều order cùng tham chiếu một customer đã được tải, ORM có thể không cần gửi lại SELECT cho customer đó trong cùng context.

Một test chỉ dùng vài customer lặp lại có thể báo query count thấp hơn dữ liệu production. Hãy tạo fixture có nhiều khóa liên quan khác nhau và clear persistence context trước phép đo.

### 16.2. Second-level cache

Second-level cache có thể giảm số lần truy vấn xuống database, nhưng không loại bỏ bản chất của đường truy cập N+1. Cache miss, eviction hoặc deployment mới có thể làm nhiều truy vấn xuất hiện lại. Đo cả cache hit/miss và kiểm tra kịch bản cache lạnh.

Không dùng cache như cách che lỗi query pattern nếu dữ liệu có tần suất thay đổi cao hoặc yêu cầu nhất quán nghiêm ngặt.

### 16.3. Lazy loading khi serialize JSON

Nếu controller trả entity trực tiếp, JSON serializer có thể gọi getter của quan hệ LAZY sau khi service đã hoàn tất. Khi đó SQL phát sinh trong giai đoạn serialize hoặc qua Open Session in View.

Hậu quả:

- SQL không xuất hiện ở vị trí code mà developer dự đoán.
- Có thể phát sinh N+1 khi duyệt collection.
- Transaction hoặc session bị giữ lâu hơn.
- API vô tình lộ dữ liệu hoặc cấu trúc entity không định dùng làm contract.

Ưu tiên trả DTO được xây dựng trong service/repository với fetch plan rõ ràng. Không dựa vào Open Session in View để tự động tải mọi quan hệ.

### 16.4. Batch size và giới hạn IN

Khi tải nhiều ID bằng IN, chia thành batch phù hợp giới hạn bind parameter và kích thước SQL của engine. Với hàng chục nghìn ID, không tạo một câu IN khổng lồ; dùng temporary table, table-valued parameter, staging table hoặc cơ chế bulk phù hợp hệ quản trị.

## 17. Các anti-pattern khi sửa N+1

- **Đổi mọi quan hệ sang EAGER:** tải dữ liệu không cần thiết ở nhiều use case.
- **JOIN FETCH tất cả collection:** nhân hàng, duplicate entity và tăng bộ nhớ.
- **Dùng DISTINCT mà không hiểu nguyên nhân:** có thể buộc sort/hash để khử trùng lặp, làm query nặng hơn.
- **Tăng batch size tùy tiện:** tạo danh sách tham số lớn hoặc vượt giới hạn driver.
- **Chỉ đo khi cache nóng:** che chi phí truy vấn khi cache miss.
- **Chỉ kiểm tra bằng danh sách 2-3 phần tử:** không thấy tăng trưởng theo N.
- **Đếm query toàn ứng dụng bằng global counter trong lúc nhiều request chạy:** kết quả bị nhiễu.
- **Bỏ qua COUNT query của pagination:** hiểu nhầm truy vấn có chủ đích là N+1.
- **Dùng SELECT *:** tải cột và entity không cần thiết.
- **Chỉ tối ưu query count:** một câu SQL scan toàn bảng vẫn có thể chậm hơn vài câu lookup nhỏ.
- **Trả entity trực tiếp cho serializer:** lazy loading có thể phát sinh SQL ngoài service.
- **Không kiểm tra tính đúng đắn:** join có thể thay đổi cardinality hoặc làm mất hàng khi chọn sai INNER/LEFT JOIN.

## 18. Quy trình khắc phục N+1

1. **Chọn use case:** xác định endpoint, service method hoặc GraphQL operation đang chậm.
2. **Tạo dữ liệu đại diện:** đủ số entity và quan hệ để thể hiện quy mô thực.
3. **Đo baseline:** query count, query fingerprint, endpoint latency và database reads.
4. **Tìm mẫu lặp:** liên hệ SQL với vòng lặp, getter lazy, mapper hoặc resolver.
5. **Xác định dữ liệu thực sự cần:** cột, quan hệ, collection và pagination.
6. **Chọn fetch strategy:** JOIN FETCH, EntityGraph, batch fetching, DTO projection hoặc hai bước theo ID.
7. **Kiểm tra ngữ nghĩa:** optional relation, duplicate, thứ tự, pagination và transaction.
8. **Đo lại query count:** xác nhận số statement không tăng tuyến tính theo N.
9. **Đọc execution plan:** kiểm tra index, rows, logical/physical reads, sort/hash và spill.
10. **Benchmark endpoint:** so sánh p50/p95/p99, CPU, memory, connection hold time và throughput.
11. **Thêm query budget:** tạo integration test để ngăn regression.
12. **Theo dõi sau release:** quan sát query fingerprint và số statement trong traffic thật.

Chỉ thay đổi một fetch strategy chính trong mỗi vòng đo nếu muốn biết tác động. Nếu đồng thời thêm index, đổi query, bật cache và tăng pool, sẽ khó xác định cải thiện đến từ đâu.

## 19. Checklist đo và sửa N+1

- [ ] Đã xác định use case và quan hệ gây truy vấn lặp.
- [ ] Đã quan sát SQL theo request hoặc trace ID.
- [ ] Đã phân biệt statement count, prepared statement count và network round trip.
- [ ] Dữ liệu test có đủ số entity và độ đa dạng khóa liên quan.
- [ ] Đã flush/clear persistence context trước phép đo khi cần.
- [ ] Đã kiểm soát second-level cache và query cache.
- [ ] Đã chọn fetch strategy theo use case, không đặt EAGER toàn cục.
- [ ] Đã xem xét JOIN FETCH, EntityGraph, batch fetching và DTO projection.
- [ ] Đã kiểm tra collection join, duplicate rows và pagination.
- [ ] Đã đo query count trước/sau và xác nhận không tăng tuyến tính theo N.
- [ ] Đã đo endpoint latency, logical/physical reads và execution plan.
- [ ] Đã kiểm tra connection usage duration và pool wait.
- [ ] Có query budget trong integration test.
- [ ] Test count không bị nhiễu bởi setup hoặc request đồng thời.
- [ ] DTO/response không kích hoạt lazy loading ngoài dự kiến.
- [ ] Đã kiểm tra kết quả nghiệp vụ, quyền truy cập và dữ liệu trả về.
- [ ] Đã theo dõi query fingerprint sau khi triển khai.

N+1 là vấn đề về cách ứng dụng truy cập dữ liệu: một tập đối tượng kéo theo nhiều truy vấn lặp theo số phần tử. Khắc phục đúng cần chọn fetch plan phù hợp với use case, đo số statement ở tầng JDBC/ORM, kiểm tra execution plan và so sánh latency trên dữ liệu đại diện. DTO projection, fetch join, EntityGraph, batch fetching hoặc truy vấn theo tập ID đều có thể hữu ích trong ngữ cảnh phù hợp. Hãy đặt query budget trong integration test để số lần truy cập không tăng tuyến tính theo danh sách và tiếp tục theo dõi p95/p99, reads cùng thời gian giữ connection sau khi thay đổi.
