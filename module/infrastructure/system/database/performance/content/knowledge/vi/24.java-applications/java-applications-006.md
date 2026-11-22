# JPA hoặc Hibernate: nhận diện N+1 từ số lượng và mẫu truy vấn

Trong chương **Ứng dụng Java** của module **DATABASE_PERFORMANCE**, lỗi N+1 xảy ra khi ứng dụng chạy một truy vấn để lấy tập đối tượng gốc, sau đó phát sinh thêm một truy vấn cho mỗi đối tượng hoặc cho từng quan hệ được truy cập. Một request có thể chỉ trả về 20 đơn hàng nhưng tạo ra 21, 41 hoặc nhiều truy vấn SQL. Khi số đối tượng tăng, số lần round trip tới database tăng theo, làm độ trễ, CPU, I/O và mức cạnh tranh connection tăng dù từng câu SQL riêng lẻ rất nhanh.

Vì vậy, nhận diện N+1 cần dựa trên **số lượng truy vấn và mẫu SQL lặp lại**, không chỉ dựa vào thời gian của một câu lệnh. Cần quan sát một request hoặc một transaction hoàn chỉnh, đếm số statement thực tế, nhóm chúng theo fingerprint, đối chiếu bind parameter và xem số truy vấn tăng thế nào khi số bản ghi gốc tăng. Sau khi xác nhận nguyên nhân, có thể chọn fetch join, EntityGraph, batch fetching, projection hoặc một chiến lược tải dữ liệu khác phù hợp với hình dạng kết quả.

Mục tiêu tối ưu là giảm công việc database trên đường đọc của ứng dụng Java, đồng thời giữ đúng semantics, giới hạn bộ nhớ và hành vi phân trang. Không phải cứ gom mọi quan hệ vào một câu SQL là tốt; fetch quá nhiều dữ liệu có thể tạo kết quả nhân dòng, tốn memory và làm truy vấn chậm hơn.

## 1. N+1 là gì?

N+1 là mẫu truy cập dữ liệu gồm:

1. Một truy vấn lấy N đối tượng gốc.
2. Một truy vấn bổ sung được phát ra cho mỗi đối tượng khi ứng dụng truy cập một quan hệ hoặc thuộc tính cần tải.

Ví dụ, một trang hiển thị 30 đơn hàng và tên khách hàng của từng đơn. Ứng dụng chạy:

- 1 truy vấn lấy 30 đơn hàng.
- 30 truy vấn lấy khách hàng tương ứng.

Tổng cộng là 31 truy vấn. Nếu trang còn hiển thị các dòng hàng của từng đơn, có thể phát sinh thêm 30 truy vấn nữa, tổng cộng 61 truy vấn. Nếu mỗi dòng hàng lại truy cập sản phẩm, số truy vấn tiếp tục tăng theo số dòng hàng.

### 1.1. Mẫu SQL điển hình

Truy vấn gốc:

```sql
SELECT o.id, o.customer_id, o.created_at, o.status
FROM orders o
WHERE o.status = 'OPEN'
ORDER BY o.created_at DESC;
```

Sau đó Hibernate phát ra cùng một mẫu SQL nhiều lần, mỗi lần thay giá trị khóa:

```sql
SELECT c.id, c.name, c.email
FROM customers c
WHERE c.id = ?;
```

Log có thể cho thấy:

```text
SELECT ... FROM orders WHERE status = ?          -- 1 lần
SELECT ... FROM customers WHERE id = ?            -- 30 lần, bind id khác nhau
```

Đặc điểm quan trọng là SQL thứ hai có cùng cấu trúc nhưng được thực thi nhiều lần với các tham số khác nhau. Mỗi câu riêng lẻ có thể là primary-key lookup rất nhanh, nhưng tổng chi phí round trip và xử lý statement vẫn lớn.

### 1.2. Vì sao gọi là N+1?

Ký hiệu N là số đối tượng gốc được lấy. Một truy vấn gốc cộng N truy vấn bổ sung tạo thành N+1. Trong thực tế, có thể có nhiều quan hệ gây N+1:

\[
Q(N) = 1 + N \times K
\]

Trong đó K là số mẫu truy vấn bổ sung phát sinh trên mỗi đối tượng gốc trong trường hợp đơn giản. Công thức chỉ mô tả xu hướng; cache cấp một, cache cấp hai, batch fetching, dữ liệu trùng quan hệ và điều kiện truy cập có thể làm số statement thực tế khác đi.

Điểm cần nhận diện là **số truy vấn tăng gần tuyến tính theo số đối tượng**, trong khi một truy vấn gốc hoặc một số truy vấn theo batch có thể xử lý toàn bộ tập dữ liệu.

## 2. N+1 thường xuất hiện ở đâu trong JPA/Hibernate?

N+1 thường bắt đầu từ quan hệ entity được tải trễ (*lazy loading*) và bị kích hoạt khi code truy cập thuộc tính quan hệ trong vòng lặp.

### 2.1. Quan hệ `@ManyToOne`

Ví dụ entity đơn hàng:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    private Instant createdAt;
    private String status;

    // getters
}
```

Repository lấy danh sách đơn hàng:

```java
List<Order> orders = orderRepository.findByStatus("OPEN");
```

Sau đó service tạo dữ liệu trả về:

```java
List<OrderSummary> result = orders.stream()
    .map(order -> new OrderSummary(
        order.getId(),
        order.getCustomer().getName(),
        order.getCreatedAt()
    ))
    .toList();
```

Nếu `customer` chưa được tải và mỗi đơn tham chiếu một khách hàng khác nhau, lần gọi `getName()` có thể kích hoạt một câu SELECT cho từng khách hàng. Query root cộng các SELECT đó tạo thành N+1.

Nếu nhiều đơn hàng cùng tham chiếu một khách hàng, persistence context có thể tái sử dụng entity đã được nạp nên số query có thể thấp hơn N. Điều này không làm mẫu truy cập an toàn: khi dữ liệu production có nhiều khách hàng khác nhau, số truy vấn vẫn có thể tăng mạnh.

### 2.2. Quan hệ `@OneToMany` hoặc `@ManyToMany`

Ví dụ một đơn hàng có nhiều dòng hàng:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();
}
```

Khi code gọi `order.getItems().size()` hoặc lặp qua `order.getItems()`, Hibernate có thể tải collection riêng cho từng đơn hàng. Nếu lấy N đơn rồi truy cập collection của tất cả, mẫu truy vấn thường là một SELECT đơn hàng cộng N SELECT dòng hàng.

N+1 cũng có thể xuất hiện ở nhiều tầng: lấy đơn hàng, lấy dòng hàng cho mỗi đơn, rồi lấy sản phẩm cho mỗi dòng. Tổng số truy vấn khi đó có thể tăng theo số đơn và tổng số dòng hàng, không chỉ theo N của danh sách gốc.

### 2.3. Quan hệ `EAGER` cũng không bảo đảm chỉ có một truy vấn

JPA quy định fetch type mặc định của `@ManyToOne` và `@OneToOne` là `EAGER`, trong khi `@OneToMany` và `@ManyToMany` mặc định là `LAZY`. Tuy nhiên, `EAGER` chỉ biểu thị quan hệ phải được tải khi entity được trả về theo fetch plan; nó không bảo đảm Hibernate luôn tạo một câu JOIN duy nhất.

Trong một số truy vấn entity, Hibernate có thể tải entity gốc trước rồi chạy các SELECT bổ sung để đáp ứng quan hệ EAGER. Vì vậy, đổi `LAZY` thành `EAGER` một cách rộng rãi có thể chuyển vấn đề thành nhiều truy vấn khác hoặc tải thừa dữ liệu. Nên xác định fetch plan theo từng use case truy vấn.

## 3. Nhận diện N+1 bằng số lượng truy vấn

Đếm tổng số câu SQL trong một request là bước đầu tiên. Nhưng tổng số đơn lẻ chưa đủ để kết luận; cần gắn số query với số đối tượng gốc và nhóm câu lệnh theo mẫu.

### 3.1. So sánh số query ở các kích thước dữ liệu

Chạy cùng một use case với số đối tượng gốc khác nhau, ví dụ 1, 10, 50 và 100:

| Số đơn hàng | Query root | Query lấy customer | Tổng dự kiến nếu N+1 |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 10 | 1 | 10 | 11 |
| 50 | 1 | 50 | 51 |
| 100 | 1 | 100 | 101 |

Nếu tăng số đơn từ 10 lên 100 làm số truy vấn tăng từ 11 lên 101, đó là dấu hiệu mạnh của N+1. Nếu query count gần như cố định hoặc tăng theo số batch, có thể fetch plan đang hoạt động theo cách khác.

### 3.2. Đếm query theo request hoặc transaction

Số query phải được đo trong đúng ranh giới use case. Nếu chỉ đếm khi gọi repository, có thể bỏ sót truy vấn phát sinh sau đó khi mapper, serializer hoặc template truy cập quan hệ lazy.

Các vị trí cần quan sát:

- Khi service gọi repository để lấy entity.
- Khi mapper chuyển entity sang DTO.
- Khi controller chuẩn bị response.
- Khi JSON serializer gọi getter của entity.
- Khi template hoặc view render dữ liệu.
- Khi code trong transaction gọi thêm quan hệ hoặc collection.

Trong ứng dụng Spring, Open Session in View có thể giữ persistence context mở tới giai đoạn render response. Khi đó, truy vấn lazy có thể phát sinh sau khi service đã kết thúc, khiến log trong service không phản ánh đầy đủ số SQL của request. Hãy đo tới khi response được tạo xong và xác định rõ ranh giới transaction.

### 3.3. Nhóm theo fingerprint SQL

Một cách hữu ích là chuẩn hóa SQL để bỏ giá trị literal hoặc bind parameter, rồi nhóm các câu có cùng cấu trúc. Ví dụ:

```text
SELECT ... FROM orders WHERE status = ?
    count = 1

SELECT ... FROM customers WHERE id = ?
    count = 100
```

Fingerprint giúp tìm một mẫu SQL được gọi lặp lại. Có thể kết hợp với:

- Số lần gọi từng fingerprint.
- Tổng thời gian database của fingerprint.
- Thời gian trung bình và p95.
- Tổng rows returned/affected.
- Số bind value khác nhau.
- Trace/request id hoặc transaction id.

Không chỉ sắp xếp theo câu SQL chậm nhất. Một câu SELECT mất 0,5 ms nhưng chạy 2.000 lần có thể tạo tổng thời gian và round trip lớn hơn một câu mất 100 ms chạy một lần.

## 4. Nhận diện N+1 từ mẫu truy vấn

Các dấu hiệu thường gặp trong log hoặc trace:

1. Một câu SELECT lấy danh sách entity gốc.
2. Ngay sau đó là cùng một câu SELECT có điều kiện `WHERE id = ?` hoặc `WHERE parent_id = ?` lặp lại.
3. Bind parameter thay đổi theo từng entity hoặc collection.
4. Các SELECT lặp có thời gian riêng lẻ thấp nhưng tổng thời gian tăng theo số entity.
5. Số query trong request tăng gần tuyến tính khi page size hoặc số parent tăng.
6. Truy vấn lặp xuất hiện trong cùng một request/trace và cùng đường code mapper/serializer.

### 4.1. Phân biệt N+1 với truy vấn lặp có chủ đích

Không phải mọi SQL lặp đều là N+1. Một ứng dụng có thể cố ý thực hiện nhiều câu update theo từng khóa do nghiệp vụ hoặc API bên ngoài. Cần xác định quan hệ giữa truy vấn gốc và truy vấn bổ sung:

- Truy vấn bổ sung có lấy quan hệ của từng entity gốc không?
- Có phát sinh do getter hoặc collection access không?
- Có thể tải dữ liệu bằng một truy vấn join, projection hoặc batch không?
- Số lần gọi có tăng theo số entity được tải không?
- Có thể gom nhiều khóa vào một câu `IN` mà vẫn giữ đúng kết quả không?

Nếu câu lệnh lặp là một thao tác ghi nghiệp vụ bắt buộc cho mỗi đối tượng, nó không tự động là lỗi N+1 ORM. Nhưng vẫn cần đánh giá batch update hoặc bulk DML nếu semantics cho phép.

### 4.2. N+1 bị che bởi cache

Persistence context của Hibernate (first-level cache) giữ một instance cho mỗi entity identity trong một session. Nếu nhiều entity gốc cùng tham chiếu một entity đã được nạp, Hibernate có thể không phát thêm SELECT. Second-level cache cũng có thể phục vụ entity hoặc collection mà không cần query database.

Vì vậy, một bài test với dữ liệu nhỏ hoặc cache nóng có thể không tái hiện số query của production. Khi kiểm thử, cần dùng dữ liệu có đủ khóa khác nhau, xác định trạng thái cache và đo cả khi cache miss. Không tắt cache production chỉ để chứng minh N+1; hãy kiểm soát cache trong môi trường test.

## 5. Bật log và thống kê Hibernate

### 5.1. Log SQL

Với Spring Boot và Hibernate 6, có thể bật SQL log trong môi trường phát triển/test:

```properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
```

Dùng logger thay cho `show-sql` giúp đưa SQL vào hệ thống logging có timestamp và correlation context. `show-sql` thường ghi trực tiếp ra console và khó kiểm soát định dạng/đích log.

Để xem bind parameter trên Hibernate 6:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Trên Hibernate 5, logger bind thường là:

```properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
```

Bind logging có thể làm log rất lớn và chứa dữ liệu cá nhân, token, email hoặc thông tin nghiệp vụ. Chỉ bật có kiểm soát ở môi trường phù hợp, che dữ liệu nhạy cảm và tắt sau khi điều tra.

### 5.2. Hibernate Statistics

Có thể bật thống kê Hibernate:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Lấy thống kê từ `SessionFactory`:

```java
Statistics statistics = entityManagerFactory
    .unwrap(SessionFactory.class)
    .getStatistics();

statistics.clear();

// Thực hiện đúng use case cần đo ở đây.

long preparedStatements = statistics.getPrepareStatementCount();
long entityFetches = statistics.getEntityFetchCount();
long collectionFetches = statistics.getCollectionFetchCount();
long queryExecutions = statistics.getQueryExecutionCount();

log.info("preparedStatements={}, entityFetches={}, collectionFetches={}, queryExecutions={}",
    preparedStatements, entityFetches, collectionFetches, queryExecutions);
```

Các bộ đếm có phạm vi thống kê của `SessionFactory`, không mặc nhiên gắn riêng một request. Trong ứng dụng nhiều request đồng thời, gọi `clear()` rồi đo có thể xóa số liệu của request khác và tạo kết quả không đáng tin cậy. Hãy dùng thống kê này cho integration test hoặc môi trường thử nghiệm ít concurrency; ở production nên dùng instrumentation theo request/transaction hoặc datasource proxy có correlation phù hợp.

`getPrepareStatementCount()` đếm số statement được chuẩn bị theo thống kê Hibernate, không phải lúc nào cũng tương đương số round trip vật lý hoặc số query đã hoàn tất. Driver batching, cache và cơ chế thực thi có thể làm các khái niệm này khác nhau. Dùng nó như tín hiệu, rồi đối chiếu SQL log hoặc datasource instrumentation.

### 5.3. Đếm SQL bằng datasource instrumentation

Một datasource proxy hoặc công cụ quan sát JDBC có thể ghi nhận statement count, SQL fingerprint, thời gian execute và request context. Các lựa chọn thường gặp gồm datasource-proxy, P6Spy hoặc instrumentation của APM. Khi chọn, cần xem:

- Có đếm được prepared statement và batch execution không?
- Có nhóm SQL theo fingerprint mà không lưu toàn bộ bind value nhạy cảm không?
- Có gắn trace id, endpoint hoặc transaction không?
- Có phân biệt thời gian chờ connection, thời gian JDBC và thời gian database không?
- Overhead instrumentation có phù hợp với môi trường chạy không?

Một APM có thể cho thấy một request phát ra 101 database spans, trong đó 100 span cùng fingerprint `SELECT ... FROM customers WHERE id = ?`. Đây là bằng chứng trực quan cho mẫu N+1.

## 6. Tái hiện N+1 trong integration test

N+1 nên được phát hiện bằng test có dữ liệu đại diện thay vì chỉ dựa vào log khi người dùng gặp sự cố. Một test tốt tạo nhiều entity cha với quan hệ khác nhau, chạy use case và đo số statement.

Ví dụ ý tưởng với Spring Boot test:

```java
@DataJpaTest
class OrderQueryTest {
    @Autowired EntityManager entityManager;
    @Autowired OrderRepository orderRepository;
    @Autowired EntityManagerFactory entityManagerFactory;

    @Test
    void queryCountShouldNotGrowPerOrder() {
        for (long i = 1; i <= 20; i++) {
            Customer customer = new Customer("Customer " + i);
            entityManager.persist(customer);

            Order order = new Order(customer, "OPEN");
            entityManager.persist(order);
        }
        entityManager.flush();
        entityManager.clear();

        Statistics statistics = entityManagerFactory
            .unwrap(SessionFactory.class)
            .getStatistics();
        statistics.clear();

        List<Order> orders = orderRepository.findByStatus("OPEN");
        List<String> names = orders.stream()
            .map(order -> order.getCustomer().getName())
            .toList();

        assertThat(names).hasSize(20);
        assertThat(statistics.getPrepareStatementCount())
            .isLessThanOrEqualTo(2);
    }
}
```

Test trên là khung minh họa; cần bổ sung constructor, repository, transaction và thư viện assertion theo dự án. Ngưỡng `<= 2` chỉ đúng sau khi query đã được tối ưu để lấy customer bằng một fetch plan phù hợp. Với test N+1 ban đầu, số statement có thể gần 21.

Lưu ý:

- `flush()` và `clear()` sau khi tạo dữ liệu giúp không dùng các entity vừa persist trong persistence context.
- Dữ liệu nên có customer khác nhau để tránh first-level cache làm che số query.
- Không để setup query hoặc lazy load từ bước chuẩn bị lọt vào khoảng đo.
- Đo đúng thao tác sử dụng quan hệ; chỉ gọi repository lấy root mà không truy cập association có thể chưa kích hoạt N+1.
- Không dùng một con số tuyệt đối áp dụng cho mọi phiên bản Hibernate hoặc mọi query; kiểm tra fingerprint và xu hướng khi tăng N.

## 7. Chọn cách sửa N+1 theo nhu cầu dữ liệu

Không có một fetch strategy tối ưu cho tất cả use case. Hãy xác định dữ liệu nào thực sự cần trả về, số lượng parent, cardinality của association và có phân trang hay không.

| Cách xử lý | Cơ chế | Phù hợp khi | Rủi ro cần kiểm tra |
|---|---|---|---|
| `JOIN FETCH` | Join association trong query lấy entity | Cần association cho một use case cụ thể | Nhân dòng, duplicate root, pagination collection |
| `@EntityGraph` | Khai báo fetch graph theo repository method | Muốn tái sử dụng entity nhưng chỉ định graph theo query | Provider có thể chọn SQL khác dự kiến; kiểm tra plan |
| Batch fetching | Gom nhiều lazy association vào một query `IN` | Muốn giữ lazy loading nhưng giảm số query | Vẫn có nhiều batch; giới hạn IN và memory |
| DTO projection | Chỉ select các cột cần trả về | API/report chỉ cần dữ liệu đọc | Phải tự định nghĩa kết quả và mapping |
| Subselect fetching | Tải collection của nhóm parent bằng một subquery | Một use case tải cùng loại collection cho nhiều parent | Có thể đọc tập dữ liệu rộng; phụ thuộc Hibernate |
| Second-level cache | Tái sử dụng entity/collection giữa session | Dữ liệu ít thay đổi, cache phù hợp | Invalidation, stale data và không thay thế fetch plan |

## 8. Dùng JOIN FETCH khi cần quan hệ trong cùng kết quả

Với `ManyToOne` customer, có thể dùng fetch join:

```java
@Query("""
    select o
    from Order o
    join fetch o.customer
    where o.status = :status
    order by o.createdAt desc
    """)
List<Order> findWithCustomerByStatus(@Param("status") String status);
```

Hibernate có thể tạo một SQL join lấy đơn hàng và khách hàng trong cùng query. Khi service gọi `order.getCustomer().getName()`, association đã được tải nên không phát sinh một SELECT riêng cho mỗi đơn.

### 8.1. JOIN FETCH collection

Với collection, fetch join có thể làm số dòng SQL tăng. Ví dụ một đơn có 5 dòng hàng thì đơn đó xuất hiện 5 lần trong kết quả join ở tầng SQL. ORM phải khôi phục graph entity từ các dòng này.

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id = :id
    """)
Optional<Order> findWithItemsById(@Param("id") Long id);
```

`distinct` giúp yêu cầu kết quả entity root không lặp theo ngữ nghĩa JPQL; cách Hibernate xử lý distinct và SQL DISTINCT có thể khác theo phiên bản. Dù vậy, dữ liệu join vẫn có thể nhân dòng và truyền nhiều byte hơn. Với nhiều collection lớn, một query join duy nhất có thể tạo Cartesian multiplication rất tốn kém.

### 8.2. Không fetch join nhiều bag tùy tiện

Hibernate có thể báo `MultipleBagFetchException` khi cùng fetch nhiều bag collection trong một query. Ngay cả khi đổi collection sang `Set` hoặc cấu trúc khác để tránh exception, join nhiều collection vẫn có thể nhân số dòng theo tích cardinality.

Ví dụ một đơn có 4 item và 3 payment; join cả hai collection có thể tạo 12 dòng cho đơn đó. Thường nên fetch một collection, tải collection còn lại bằng batch/subselect hoặc query riêng theo danh sách khóa.

### 8.3. JOIN FETCH và phân trang

Fetch join collection kết hợp `LIMIT/OFFSET` có thể khiến phân trang không còn hoạt động ở cấp SQL như mong muốn. Hibernate có thể phải tải nhiều dòng rồi phân trang trong bộ nhớ hoặc phát cảnh báo tùy phiên bản/cấu hình. Điều này có thể làm truy vấn đọc nhiều dữ liệu hơn rất nhiều so với page size.

Các hướng xử lý:

1. Phân trang danh sách entity gốc trước, chỉ lấy ID và các cột sắp xếp.
2. Dùng query thứ hai fetch association cho danh sách ID của trang đó.
3. Dùng DTO projection để lấy đúng dữ liệu của trang trong một truy vấn có kiểm soát.
4. Dùng batch fetching cho collection khi cần giữ entity graph.

Ví dụ hai bước:

```java
Page<Long> pageIds = orderRepository.findPageIds(status, pageable);

List<Order> orders = orderRepository.findWithCustomerAndItemsByIdIn(
    pageIds.getContent()
);
```

Query thứ hai nên giữ thứ tự theo danh sách ID nếu API yêu cầu thứ tự trang; SQL `IN (...)` không bảo đảm thứ tự đầu vào. Có thể sắp xếp lại trong ứng dụng bằng map theo ID hoặc đưa thứ tự vào query. Cũng cần xử lý trường hợp dữ liệu thay đổi giữa hai query theo isolation semantics của transaction.

## 9. Dùng EntityGraph theo use case

EntityGraph cho phép chỉ định quan hệ cần tải cho một repository method mà không phải thay đổi fetch type mặc định của entity.

Ví dụ:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
    @EntityGraph(attributePaths = {"customer"})
    List<Order> findByStatus(String status);
}
```

Khi màn hình cần thêm `items`, có thể khai báo graph riêng:

```java
@EntityGraph(attributePaths = {"customer", "items"})
@Query("select o from Order o where o.id = :id")
Optional<Order> findDetailById(@Param("id") Long id);
```

EntityGraph mô tả fetch graph mong muốn cho provider. Nó không bảo đảm luôn tạo đúng một câu SQL JOIN duy nhất; Hibernate có thể dùng join hoặc secondary select tùy mapping, query và giới hạn. Luôn kiểm tra SQL log và query count sau khi áp dụng.

Dùng graph theo từng use case giúp tránh đặt mọi association thành EAGER trên entity. Danh sách chỉ cần tên khách không nhất thiết phải tải toàn bộ payment, audit history và item collection.

## 10. Batch fetching để giảm N+1

Batch fetching vẫn giữ quan hệ lazy, nhưng khi một association được truy cập, Hibernate có thể tải nhiều proxy hoặc collection chưa khởi tạo trong một query có điều kiện `IN`.

### 10.1. Cấu hình batch size

Có thể cấu hình mặc định:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Hoặc cấu hình theo entity/collection bằng annotation Hibernate:

```java
@Entity
@BatchSize(size = 32)
public class Customer {
    // fields
}
```

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderItem> items = new ArrayList<>();
```

Tên annotation và package phụ thuộc phiên bản Hibernate; `@BatchSize` là extension của Hibernate, không phải annotation chuẩn JPA.

### 10.2. Số query sau batch fetching

Nếu cần tải association cho 100 parent và batch size là 32, số query bổ sung lý tưởng có thể giảm gần:

\[
\left\lceil \frac{100}{32} \right\rceil = 4
\]

Tổng cộng có thể là 1 query root cộng 4 query batch thay vì 101 query. Đây vẫn là nhiều query nhưng số lượng tăng theo số batch, không còn một query cho mỗi parent.

Kết quả thực tế phụ thuộc các proxy/collection nào được truy cập, session chứa những entity nào, database parameter limit, dialect và cách Hibernate chọn batch. Hãy đo query count và kích thước `IN` trong môi trường thực tế.

### 10.3. Khi nào batch fetching phù hợp?

- Use case cần entity graph nhưng không muốn join collection làm nhân dòng.
- Nhiều entity cha cần tải cùng loại association.
- Quan hệ có thể truy cập lazy trong một transaction có ranh giới rõ.
- Có thể chấp nhận một số query theo batch thay vì một query duy nhất.

Batch fetching không phù hợp nếu chỉ một phần nhỏ association được truy cập nhưng batch lại tải nhiều dữ liệu không cần thiết, hoặc nếu query `IN` quá lớn làm plan kém. Hãy thử các batch size khác nhau và xem cả latency lẫn rows returned.

## 11. Dùng DTO projection để tránh tải entity không cần thiết

Nếu API chỉ cần một số trường, DTO projection thường là cách trực tiếp và dễ kiểm soát. Nó tránh việc tải entity graph rồi vô tình kích hoạt lazy association trong mapper.

Ví dụ JPQL constructor projection:

```java
public record OrderSummary(
    Long orderId,
    String customerName,
    Instant createdAt,
    BigDecimal totalAmount
) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        c.name,
        o.createdAt,
        o.totalAmount
    )
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderSummary> findSummariesByStatus(@Param("status") String status);
```

Truy vấn chỉ lấy các cột cần trả về và join customer ngay trong query. Vì kết quả là DTO, code không cần truy cập proxy entity customer sau khi query hoàn tất.

Với collection cần tổng hợp, có thể dùng `COUNT`, `SUM` hoặc subquery theo đúng grain. Phải kiểm tra duplicate và `GROUP BY` để bảo đảm mỗi DTO đại diện cho đúng một đơn hàng. Nếu cần phân trang, projection thường dễ kiểm soát hơn fetch join collection.

## 12. N+1 phát sinh trong mapper, serializer và Open Session in View

Một truy vấn có thể trông tối ưu ở repository nhưng vẫn tạo N+1 sau khi trả entity cho tầng khác.

### 12.1. Mapper truy cập lazy association

Ví dụ mapper:

```java
OrderResponse toResponse(Order order) {
    return new OrderResponse(
        order.getId(),
        order.getCustomer().getName(),
        order.getItems().stream()
            .map(item -> new ItemResponse(
                item.getProduct().getName(),
                item.getQuantity()
            ))
            .toList()
    );
}
```

Mapper có thể kích hoạt lazy load cho customer, items và product. Nếu gọi mapper cho từng order, các association có thể tạo nhiều SELECT. Đưa mapper vào cùng transaction không tự giải quyết N+1; nó chỉ cho phép lazy load tiếp tục chạy.

### 12.2. JSON serialization

Nếu controller trả trực tiếp entity, Jackson hoặc serializer khác có thể gọi getter và kích hoạt lazy load. Kết quả là SQL phát sinh trong lúc serialize response, làm khó xác định nơi gây query và có thể tạo N+1 ngoài transaction service.

Ưu tiên trả DTO đã được tạo trong ranh giới service/transaction. DTO làm rõ dữ liệu API cần và giúp tránh phụ thuộc vào persistence context trong quá trình serialization.

### 12.3. Open Session in View

Open Session in View giữ EntityManager/Session mở trong phần lớn vòng đời HTTP request. Điều này có thể khiến lazy loading tiếp tục hoạt động sau khi transaction service kết thúc. Nó tiện cho một số ứng dụng nhưng dễ che giấu truy vấn phát sinh ở view/serializer.

Không nên dựa vào OSIV để tự động tải mọi quan hệ. Hãy xác định fetch plan trong service/repository, chuyển sang DTO và quan sát query count toàn request. Nếu tắt OSIV, cần bảo đảm mọi dữ liệu cần thiết được tải trước khi transaction kết thúc; nếu không, ứng dụng có thể gặp `LazyInitializationException`.

## 13. Phân biệt N+1 với vấn đề truy vấn khác

| Dấu hiệu | N+1 | Truy vấn chậm đơn lẻ | Query trả quá nhiều dữ liệu |
|---|---|---|---|
| Số statement | Một root cộng nhiều statement cùng mẫu | Có thể chỉ một statement | Có thể một hoặc vài statement |
| Mẫu SQL | Cùng fingerprint lặp với bind khác nhau | Một plan tốn kém | SQL có thể đơn giản nhưng rows/bytes lớn |
| Tương quan với N | Query count tăng theo số entity | Thời gian phụ thuộc dữ liệu/plan | Rows và payload tăng theo dữ liệu |
| Hướng xử lý | Fetch plan, batch, projection | Index, SQL, stats, plan | Giảm cột/dòng, phân trang, streaming |

Một endpoint có thể mắc nhiều vấn đề cùng lúc. Ví dụ, N+1 tạo nhiều point lookup, mỗi lookup lại dùng index không phù hợp. Hãy phân biệt số lần gọi với chi phí của từng lần gọi, sau đó xử lý cả hai nếu cần.

## 14. Quy trình điều tra N+1 từ số lượng và mẫu truy vấn

1. **Chọn use case cụ thể:** endpoint, job hoặc thao tác service đang chậm.
2. **Tạo dữ liệu đại diện:** đủ số parent, association khác nhau và cardinality gần production.
3. **Đo số query toàn request:** dùng SQL log, Hibernate statistics, datasource proxy hoặc APM.
4. **Nhóm fingerprint:** tìm SELECT lặp lại cùng cấu trúc và bind key khác nhau.
5. **Liên kết với code:** xác định getter, collection, mapper hoặc serializer kích hoạt lazy loading.
6. **Thử nhiều N:** chạy với 1, 10, 50, 100 parent và xem query count có tăng tuyến tính không.
7. **Kiểm tra cache:** xác định first-level/second-level cache có làm che số query hay không.
8. **Chọn fetch strategy:** JOIN FETCH, EntityGraph, batch fetching hoặc DTO projection theo nhu cầu.
9. **Đo lại:** so query count, rows returned, bytes, DB time, application time và p95/p99.
10. **Kiểm tra tác động phụ:** pagination, duplicate root, memory, lock và truy vấn khác.
11. **Thêm regression test:** bảo đảm số query không tăng theo số entity ngoài dự kiến.

## 15. Ví dụ hoàn chỉnh: tối ưu danh sách đơn hàng

Giả sử màn hình hiển thị 50 đơn hàng, tên khách và số lượng dòng hàng. Entity có `ManyToOne customer` và `OneToMany items`.

### 15.1. Trước khi tối ưu

```java
List<Order> orders = orderRepository.findByStatus("OPEN");

return orders.stream()
    .map(order -> new OrderListItem(
        order.getId(),
        order.getCustomer().getName(),
        order.getItems().size()
    ))
    .toList();
```

Log cho thấy:

```text
SELECT ... FROM orders WHERE status = ?                 -- 1
SELECT ... FROM customers WHERE id = ?                  -- 50
SELECT ... FROM order_items WHERE order_id = ?          -- 50
```

Tổng 101 statement. Nếu một số đơn dùng chung customer, số query customer có thể thấp hơn 50; query collection vẫn có thể xuất hiện cho từng đơn.

### 15.2. Phương án DTO projection

Nếu màn hình chỉ cần ba trường trên, có thể dùng projection với aggregate:

```java
public record OrderListItem(
    Long orderId,
    String customerName,
    Long itemCount
) {}
```

```java
@Query("""
    select new com.example.api.OrderListItem(
        o.id,
        c.name,
        count(i.id)
    )
    from Order o
    join o.customer c
    left join o.items i
    where o.status = :status
    group by o.id, c.name
    order by o.id desc
    """)
List<OrderListItem> findOrderListItems(@Param("status") String status);
```

Query có thể trả kết quả đã join và đếm theo đơn trong một statement. Cần kiểm tra JPQL provider hỗ trợ record constructor theo phiên bản đang dùng, kiểu trả về của `count`, thứ tự sort và plan. Nếu `items` có thêm join khác làm nhân dòng, cần điều chỉnh aggregate hoặc dùng subquery để không đếm trùng.

### 15.3. Phương án fetch plan cho entity

Nếu use case cần thao tác entity và collection, có thể fetch customer cùng root và batch collection:

```java
@EntityGraph(attributePaths = {"customer"})
List<Order> findByStatus(String status);
```

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Khi mapper truy cập `items`, Hibernate có thể tải collection theo nhóm. Với 50 đơn, số query collection có thể giảm xuống khoảng hai batch thay vì 50, tùy session và provider. Cần xác nhận bằng SQL log.

### 15.4. So sánh trước và sau

| Chỉ số | Trước | Sau projection (mục tiêu đo) |
|---|---:|---:|
| Số statement | 101 | 1 |
| Root rows | 50 | Kết quả theo grain đơn hàng |
| Association fetch | 100 | Không có lazy fetch |
| Dữ liệu truyền | Có thể lặp customer/order columns | Chỉ các cột DTO cần |
| Mapping | Truy cập entity graph | Nhận DTO trực tiếp |

Đây là mục tiêu của ví dụ, không phải cam kết hiệu năng. Query projection có thể cần sort/hash aggregate và tạo nhiều dòng trung gian. Đo elapsed, CPU, logical reads và actual plan để xác nhận phương án thực sự tốt hơn.

## 16. Những sai lầm thường gặp

- **Chỉ xem thời gian của từng câu SQL:** bỏ qua tổng số round trip trong một request.
- **Chỉ nhìn tổng query count:** không nhóm fingerprint để tìm mẫu lặp theo từng entity.
- **Đổi mọi quan hệ sang EAGER:** có thể tải thừa hoặc vẫn phát sinh secondary select.
- **Fetch join mọi collection:** gây nhân dòng, Cartesian multiplication hoặc lỗi multiple bag.
- **Fetch join collection với phân trang:** có thể khiến Hibernate phân trang trong bộ nhớ hoặc đọc quá nhiều dữ liệu.
- **Bật batch size rồi không đo:** batch fetching giảm số query nhưng vẫn có thể tải quá nhiều association.
- **Dùng second-level cache để che N+1:** cache hit có thể giảm query nhưng không sửa fetch plan và invalidation vẫn có chi phí.
- **Đo khi persistence context đã chứa entity:** first-level cache làm số query thấp giả tạo.
- **Không đo giai đoạn serialization:** query lazy có thể phát sinh sau service/repository.
- **Dùng Hibernate Statistics toàn cục như số liệu theo request:** concurrency làm bộ đếm bị trộn giữa các request.
- **Bật bind logging lâu trên production:** có thể lộ dữ liệu nhạy cảm và tạo log volume lớn.
- **Chỉ tối ưu query count:** một query lớn có thể chậm hơn một vài query theo batch; cần đo cả rows, bytes, CPU và latency.

## 17. Checklist nhận diện và xử lý N+1

- [ ] Đã chọn đúng request/use case và đo toàn bộ vòng đời tạo response.
- [ ] Đã đếm statement thực tế, không chỉ đếm lời gọi repository.
- [ ] Đã nhóm SQL theo fingerprint và tìm mẫu lặp với bind key khác nhau.
- [ ] Đã so query count khi số entity gốc tăng từ nhỏ tới lớn.
- [ ] Đã xác định association hoặc getter kích hoạt lazy loading.
- [ ] Đã kiểm tra mapper, serializer và Open Session in View.
- [ ] Đã kiểm soát first-level cache và second-level cache trong phép đo.
- [ ] Đã chọn JOIN FETCH, EntityGraph, batch fetching hoặc DTO projection theo dữ liệu thực sự cần.
- [ ] Đã kiểm tra duplicate root, số dòng join và cardinality collection.
- [ ] Đã kiểm tra pagination, sort và giới hạn memory.
- [ ] Đã đo lại query count, DB time, application time, rows, bytes và p95/p99.
- [ ] Đã thêm integration test hoặc query-count regression test.
- [ ] Đã giới hạn SQL/bind logging và bảo vệ dữ liệu nhạy cảm.

N+1 trong JPA/Hibernate được nhận diện rõ nhất khi kết hợp số lượng statement với mẫu SQL lặp theo từng khóa và quan hệ của entity gốc. Hãy đo trên toàn request, thử với nhiều kích thước dữ liệu và xác định nơi lazy loading được kích hoạt. Sau đó chọn fetch join, EntityGraph, batch fetching hoặc DTO projection theo đúng dữ liệu cần trả về, rồi kiểm chứng cả query count lẫn lượng dữ liệu và thời gian thực thi để tránh thay N+1 bằng một truy vấn join quá lớn.
