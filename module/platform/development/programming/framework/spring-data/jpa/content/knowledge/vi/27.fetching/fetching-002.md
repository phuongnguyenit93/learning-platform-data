# Nhận diện N+1 từ số câu SQL và hình dạng dữ liệu

## 1. N+1 query là gì?

N+1 là vấn đề hiệu năng xảy ra khi ứng dụng chạy một truy vấn để lấy danh sách entity cha, sau đó phát sinh thêm một truy vấn tương tự cho từng entity để tải dữ liệu liên quan.

Ví dụ: trang danh sách khách hàng hiển thị số đơn hàng của từng người. Ứng dụng lấy 100 khách hàng bằng một câu SELECT, rồi khi gọi `customer.getOrders().size()`, Hibernate tải collection đơn hàng riêng cho từng khách hàng.

Nếu không có cache hoặc cơ chế gom fetch, số câu SELECT có thể là:

- 1 câu lấy danh sách khách hàng.
- N câu lấy đơn hàng cho N khách hàng.
- Tổng cộng: 1 + N câu truy vấn.

Với N = 100, ứng dụng có thể phát 101 câu SELECT chỉ để hiển thị một trang. Nếu database ở máy chủ khác, chi phí round-trip thường lớn hơn nhiều so với thời gian xử lý Java.

N+1 không chỉ xảy ra với quan hệ OneToMany. Nó cũng có thể xuất hiện khi truy cập lazy ManyToOne hoặc OneToOne trên từng entity, hoặc khi một vòng lặp gọi repository method cho từng phần tử.

Điểm quan trọng: N+1 là một mẫu thực thi có thể nhận ra qua **số lượng câu SQL tăng theo số entity** và **hình dạng SQL lặp lại**, chứ không đơn thuần là “có nhiều query”.

## 2. Ví dụ tạo ra N+1 với JPA

### 2.1. Mapping entity

Giả sử mỗi khách hàng có nhiều đơn hàng:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
```

Entity đơn hàng:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
```

Collection `orders` được cấu hình LAZY. Hibernate thường chưa tải đơn hàng khi truy vấn Customer. Khi code truy cập collection lần đầu, Hibernate phát SQL để tải dữ liệu liên quan.

### 2.2. Đoạn code dễ tạo N+1

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Service:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<String> customerOrderCounts() {
        List<Customer> customers = repository.findAll();

        return customers.stream()
            .map(customer ->
                customer.getName() + ": " + customer.getOrders().size()
            )
            .toList();
    }
}
```

Nếu có N khách hàng và mỗi collection chưa được tải, luồng truy vấn thường là:

1. `findAll()` lấy danh sách Customer.
2. Lần đầu gọi `getOrders()` cho Customer thứ nhất: tải orders của customer đó.
3. Lần đầu gọi `getOrders()` cho Customer thứ hai: chạy một SELECT khác.
4. Tiếp tục cho từng Customer còn lại.

Với N khách hàng, có thể có 1 + N SELECT. Số đơn hàng của từng người không làm thay đổi số lần tải collection theo cách này; một collection được tải bằng một query riêng, dù collection có 0 hay nhiều phần tử.

Collection lazy cần được truy cập trong transaction; nếu persistence context đã đóng, Hibernate có thể ném `LazyInitializationException` lúc này.

## 3. Nhận diện qua số câu SQL

### 3.1. Đếm truy vấn theo một use case

Bắt đầu bằng cách xác định một thao tác cụ thể, ví dụ:

- Mở trang danh sách khách hàng.
- Xem chi tiết một đơn hàng.
- Tải danh sách sản phẩm cùng tên danh mục.
- Tạo response DTO có trường lấy từ quan hệ lazy.

Sau đó đo số SQL được phát ra trong phạm vi thao tác đó. Nếu số query tăng gần tuyến tính theo số entity cha, hãy kiểm tra N+1.

Ví dụ kết quả đo:

| Số Customer | Query lấy Customer | Query lấy Orders | Tổng SELECT |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 10 | 1 | 10 | 11 |
| 50 | 1 | 50 | 51 |
| 100 | 1 | 100 | 101 |

Bảng là ví dụ cho một collection lazy chưa được cache và được truy cập ở từng Customer. Đây không phải số liệu cố định cho mọi mapping/provider.

Một dấu hiệu mạnh là khi tăng số entity từ 10 lên 100, số query phụ cũng tăng từ 10 lên 100. Một query tổng hợp tốt thường giữ số câu SQL gần như không đổi khi số hàng trả về tăng, dù lượng dữ liệu và thời gian đọc vẫn có thể tăng.

### 3.2. Đừng chỉ nhìn tổng query count

Một request có thể hợp lệ khi chạy nhiều query khác nhau: lấy user hiện tại, quyền truy cập, cấu hình, dữ liệu chính và dữ liệu phụ. Tổng số query cao chưa đủ kết luận có N+1.

Hãy hỏi:

- Có một query lấy danh sách entity gốc không?
- Sau đó có cùng một câu SQL chạy lặp lại nhiều lần không?
- Mỗi lần lặp chỉ thay giá trị bind parameter như customer_id?
- Số lần lặp có gần bằng số entity được tải không?
- Việc truy cập property/association nào kích hoạt query?

Nếu có 1 query danh sách Customer và 100 query gần giống nhau lọc theo customer_id khác nhau, đó là dấu hiệu điển hình.

### 3.3. Phân biệt số query với số dòng trả về

Một query có thể trả hàng nghìn dòng nhưng vẫn chỉ là một statement. Ngược lại, 100 query mỗi query trả một vài dòng có thể gây nhiều round-trip.

Cần đo ít nhất:
- Số lần execute SQL.
- Tổng thời gian database.
- Thời gian chờ lấy connection.
- Số hàng trả về và kích thước dữ liệu.
- Thời gian mapping entity/DTO.
- Số query lặp lại theo cùng một mẫu.

N+1 thường là vấn đề số lần round-trip và overhead thực thi lặp, không phải chỉ tổng số dòng.

## 4. Nhận diện qua hình dạng SQL

### 4.1. Query đầu tiên lấy entity gốc

SQL đầu tiên có thể có dạng:

```sql
select
    c.id,
    c.name
from customer c
where c.name is not null;
```

Query này lấy N khách hàng. Chỉ nhìn câu SQL này sẽ chưa thấy vấn đề.

### 4.2. Query lặp lại lấy association

Sau đó Hibernate có thể phát nhiều câu tương tự:

```sql
select
    o.id,
    o.order_number,
    o.customer_id
from purchase_order o
where o.customer_id = ?;
```

Trong log, cùng một SQL xuất hiện nhiều lần với bind parameter khác nhau:

```text
/* query minh họa */
where o.customer_id = 10

/* cùng hình dạng SQL */
where o.customer_id = 11

/* cùng hình dạng SQL */
where o.customer_id = 12

/* ... tiếp tục cho từng customer */
```

Đặc điểm nhận diện:
- Cùng bảng và cùng danh sách cột.
- Cùng điều kiện WHERE.
- Chỉ giá trị bind parameter thay đổi.
- Câu SQL được thực thi lặp lại trong cùng request/use case.
- Số lần lặp tăng theo số entity cha được duyệt.

SQL log có thể hiển thị placeholder `?` ở mọi lần và bind value được ghi ở logger riêng. Vì vậy cần xem cả SQL statement và bind parameter nếu cần xác nhận mỗi lần query đang tải association của entity nào.

### 4.3. Nhận diện N+1 với ManyToOne

Giả sử danh sách Order cần hiển thị tên Customer. Mapping `@ManyToOne(fetch = LAZY)` có thể tạo query:

```sql
select
    o.id,
    o.order_number,
    o.customer_id
from purchase_order o;
```

Sau đó, khi code gọi `order.getCustomer().getName()`, Hibernate có thể tải Customer theo từng ID:

```sql
select c.id, c.name
from customer c
where c.id = ?;
```

Nếu danh sách có nhiều Order tham chiếu tới nhiều Customer khác nhau và proxy chưa được khởi tạo, các SELECT bổ sung có thể lặp theo từng Customer được truy cập. Nếu nhiều Order cùng tham chiếu một Customer và cùng persistence context, first-level cache có thể giảm số query cho ID đã được load; do đó số query thực tế phụ thuộc phân bố khóa ngoại và cache.

### 4.4. Hình dạng SQL có thể khác nhau

Không phải mọi N+1 đều tạo SQL giống hệt từng ký tự. SQL có thể khác do:
- Các association khác nhau.
- Entity inheritance hoặc discriminator.
- Filter/tenant condition.
- Batch fetching hoặc fetch mode.
- Provider/dialect và phiên bản Hibernate.
- Query được tạo từ repository, lazy proxy hoặc serialization.

Hãy so sánh normalized SQL shape: bảng, join, predicate, số placeholder và mục đích dữ liệu. Đừng chỉ tìm chuỗi SQL giống tuyệt đối.

## 5. Bật SQL log trong Spring Boot và Hibernate

### 5.1. Hiển thị SQL

Với Spring Boot:

```yaml
spring:
  jpa:
    show-sql: false

logging:
  level:
    org.hibernate.SQL: DEBUG
```

Dùng logger thay cho `show-sql` giúp kiểm soát log qua logging framework, lọc theo package và đưa log vào hệ thống quan sát. Không nên bật đồng thời nhiều cơ chế SQL logging nếu chúng làm một statement xuất hiện hai lần.

### 5.2. Hiển thị bind parameter với Hibernate 6

Để biết mỗi lần query lặp đang truyền ID nào:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Hibernate 6 dùng category `org.hibernate.orm.jdbc.bind` để log bind value. Với Hibernate 5, logger thường dùng là `org.hibernate.type.descriptor.sql.BasicBinder`. Tên logger phụ thuộc phiên bản, nên hãy dùng category tương ứng dependency thực tế.

Bind log có thể chứa tên, email, mã định danh hoặc dữ liệu nhạy cảm. Chỉ bật TRACE trong môi trường phát triển/test hoặc thời gian điều tra được kiểm soát; không để lộ giá trị bind trong log production nếu chưa có chính sách bảo vệ phù hợp.

### 5.3. Log SQL không phải công cụ đo duy nhất

SQL log hữu ích để nhìn hình dạng query nhưng không phải lúc nào cũng cung cấp:
- Thời gian database thực thi chính xác.
- Thời gian chờ connection.
- Số hàng thực tế đọc/ghi.
- Execution plan.
- Query fingerprint đã normalize.

Kết hợp log với datasource proxy, APM, Hibernate statistics và công cụ giám sát database để có bằng chứng đầy đủ hơn.

## 6. Dùng Hibernate Statistics để đếm statement

### 6.1. Bật statistics

Trong cấu hình Spring Boot:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Hibernate statistics có thể cung cấp số lần chuẩn bị statement, entity load, collection fetch và các số liệu khác.

Có thể lấy Statistics từ SessionFactory:

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();

long statements = statistics.getPrepareStatementCount();
long entityLoads = statistics.getEntityLoadCount();
long collectionFetches = statistics.getCollectionFetchCount();
```

Các import chính thuộc Hibernate:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
```

`getPrepareStatementCount()` là số prepared statement được Hibernate ghi nhận đã chuẩn bị trong phạm vi statistics. Nó là chỉ số hữu ích để so sánh trước/sau, nhưng không nhất thiết bằng số round-trip network hoặc số query mà mọi công cụ database quan sát được. Cần hiểu đúng metric và thời điểm reset.

### 6.2. Đo một use case trong test

Ví dụ test tích hợp:

```java
@SpringBootTest
class CustomerQueryTest {

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private CustomerService customerService;

    @Test
    void measuresStatementsForCustomerOrderCounts() {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();

        // Fixture phải được tạo và commit trước khi đo.
        statistics.clear();

        List<String> result =
            customerService.customerOrderCounts();

        assertThat(result).isNotEmpty();

        long statementCount =
            statistics.getPrepareStatementCount();

        System.out.println("Prepared statements: " + statementCount);
    }
}
```

Đây là khung minh họa; test cần chuẩn bị dữ liệu fixture trước khi reset statistics và bảo đảm service chạy qua transaction/persistence context như production.

Statistics của SessionFactory là số liệu dùng chung cho các thread. Nếu nhiều test hoặc request chạy song song, query khác có thể làm tăng count trong lúc đo. Để đo chính xác, chạy test cô lập hoặc dùng công cụ capture theo request/connection thay vì dựa vào counter toàn cục trong môi trường có concurrency.

### 6.3. Đo trước và sau khi sửa

Một phép đo có giá trị cần giữ nguyên:
- Cùng dataset và số entity.
- Cùng use case và input.
- Cùng transaction boundary.
- Cùng cache state.
- Cùng provider, dialect và cấu hình fetch.
- Cùng cách đếm statement.

Ví dụ trước sửa có 1 + 100 statement; sau sửa có 2 statement. Đây là bằng chứng mạnh rằng query fan-out đã được giảm cho dataset đó. Nhưng vẫn phải kiểm tra nội dung dữ liệu, số hàng trả về và thời gian thực tế.

## 7. Cache có thể che giấu N+1

### 7.1. First-level cache

Mỗi persistence context/EntityManager có first-level cache. Khi một entity có cùng ID đã được quản lý, truy cập lại entity đó trong cùng context thường không cần SELECT mới.

Vì vậy, nếu nhiều Order cùng tham chiếu một Customer, lần đầu có thể query Customer; các lần sau trong cùng persistence context dùng lại managed instance.

Điều này có thể làm số query nhỏ hơn số entity được duyệt nhưng không chứng minh thiết kế không có N+1. Khi dữ liệu thực tế có nhiều khóa ngoại khác nhau hoặc persistence context mới ở mỗi request, vấn đề có thể xuất hiện rõ hơn.

### 7.2. Second-level cache và query cache

Nếu ứng dụng bật second-level cache, một số entity/association có thể được lấy từ cache thay vì database. Query cache có thể ảnh hưởng cách truy vấn được thực hiện tùy cấu hình và provider.

Khi đo N+1:
- Kiểm tra cache có được bật không.
- Thực hiện test với cache state được kiểm soát.
- Phân biệt cache hit với việc query đã được thiết kế tốt.
- Đo cả tình huống cache lạnh và cache nóng nếu production có cả hai.

Không tắt cache toàn hệ thống chỉ để điều tra. Dùng test/profile cô lập hoặc xóa đúng cache region khi có thể.

### 7.3. Test cần flush và clear fixture

Nếu fixture được persist trong cùng persistence context, entity có thể đã được quản lý hoặc collection đã được khởi tạo. Điều đó khiến test không tái hiện N+1.

Trong test JPA, có thể:
1. Persist fixture.
2. Flush để ghi SQL fixture xuống database.
3. Clear persistence context để loại entity managed hiện tại.
4. Reset statistics.
5. Gọi use case cần đo.

Ví dụ:

```java
entityManager.flush();
entityManager.clear();
statistics.clear();

List<String> result =
    customerService.customerOrderCounts();
```

Nếu test dùng transaction của `@DataJpaTest`, hãy chú ý transaction fixture và transaction khi gọi service. Mục tiêu là bảo đảm query đo được thực sự đọc dữ liệu từ database thay vì dùng object còn nằm trong persistence context.

## 8. N+1 xuất hiện ở đâu trong vòng đời request?

### 8.1. Trong service loop

Dạng phổ biến:

```java
for (Customer customer : customers) {
    int count = customer.getOrders().size();
}
```

Mỗi lần truy cập collection lazy chưa khởi tạo có thể phát query. Tương tự, gọi `repository.findByCustomerId(id)` trong vòng lặp cũng tạo N+1 ở tầng ứng dụng, dù không có lazy association.

### 8.2. Trong DTO mapper

Mapper có thể vô tình truy cập quan hệ:

```java
CustomerResponse toResponse(Customer customer) {
    return new CustomerResponse(
        customer.getId(),
        customer.getName(),
        customer.getOrders().stream()
            .map(PurchaseOrder::getOrderNumber)
            .toList()
    );
}
```

Nếu mapper chạy cho từng Customer sau khi query danh sách, việc đọc `orders` có thể tạo N query. Đừng chỉ kiểm tra service; hãy xem mapper, getter, computed property và serializer.

### 8.3. Trong JSON serialization

Nếu controller trả entity, Jackson có thể gọi getter và truy cập association lazy khi serialize response. Khi Open EntityManager in View được bật, persistence context có thể còn mở tới giai đoạn render response, khiến query phát sinh sau khi service đã trả về.

Do đó, đo query chỉ trong service có thể bỏ sót N+1 phát sinh ở serialization. Đo toàn bộ request hoặc dùng DTO được materialize rõ ràng trong transaction để kiểm soát dữ liệu response.

Trả entity trực tiếp cũng có thể gây vòng tham chiếu JSON, tải dữ liệu ngoài dự kiến hoặc lộ field nội bộ. DTO projection giúp xác định rõ dữ liệu API cần trả.

### 8.4. Trong nested loop hoặc nhiều cấp quan hệ

Một trang có thể tải Customer rồi từng Order, sau đó từng OrderItem. Nếu mỗi cấp đều lazy và được truy cập theo vòng lặp, số query có thể thành N+1 hoặc dạng nhiều tầng như 1 + N + M.

Hãy đọc log theo thứ tự thời gian và nhóm query theo association. Một truy vấn lặp lại sau khi tải Order có thể là vấn đề riêng ở OrderItem, dù query Customer-Order đã được tối ưu.

## 9. Phân biệt N+1 với các query hợp lệ

Không phải query lặp nào cũng là lỗi. Một số trường hợp hợp lý:
- Mỗi thao tác cần đọc dữ liệu khác nhau và không thể gộp.
- Query được chạy theo từng partition/batch có chủ đích.
- Dữ liệu cần quyền hoặc transaction độc lập.
- Batch size được giới hạn vì một câu query lớn vượt giới hạn parameter.
- Mỗi query có điều kiện hoặc kết quả khác nhau thực sự.

Để kết luận N+1, xác định mối quan hệ giữa query đầu tiên, query lặp và vòng lặp truy cập dữ liệu. Hỏi xem có thể tải dữ liệu theo nhóm hoặc lấy projection đúng nhu cầu trong một số ít query hay không.

Một endpoint chạy 5 câu SQL cố định cho 5 phần dữ liệu khác nhau không nhất thiết là N+1. Endpoint chạy 1 query cha rồi 500 query con có cùng hình dạng và chỉ đổi khóa ngoại là dấu hiệu rất rõ.

## 10. Cách khắc phục và cách xác minh

### 10.1. JOIN FETCH cho quan hệ cần tải

Có thể yêu cầu tải Customer và Orders trong cùng query:

```java
@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    where c.name is not null
    order by c.name, c.id
    """)
List<Customer> findNamedWithOrders();
```

Fetch join tải association trong query. SQL thường có JOIN giữa customer và purchase_order thay vì phát thêm một SELECT cho từng customer.

Lưu ý:
- Dùng LEFT JOIN FETCH nếu vẫn cần Customer không có Order.
- JOIN FETCH (inner) loại Customer không có phần tử liên quan.
- JOIN collection làm số hàng SQL tăng theo số phần tử con.
- Không fetch quá nhiều collection lớn cùng lúc.
- Query trả entity có thể cần distinct để thể hiện ý định lấy root duy nhất; hành vi loại trùng còn phụ thuộc provider/version.

Sau khi sửa, log nên cho thấy một query join thay cho mẫu 1 + N query. Tuy nhiên, số hàng SQL có thể tăng đáng kể; hãy đo dữ liệu truyền về và thời gian mapping.

### 10.2. EntityGraph

Spring Data JPA hỗ trợ `@EntityGraph` để chỉ định association cần fetch cho một repository method:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(attributePaths = "orders")
    List<Customer> findByNameNotNull();
}
```

EntityGraph biểu đạt fetch plan ở mức repository. Provider quyết định cách thực hiện, có thể dùng join hoặc query bổ sung tùy mapping và dialect. Vì vậy, không giả định EntityGraph luôn tạo đúng một SQL; hãy xác minh số statement và hình dạng query trong log.

EntityGraph phù hợp khi cùng một entity có nhiều use case với nhu cầu tải association khác nhau. Tránh đặt tất cả quan hệ thành EAGER toàn cục chỉ để sửa một màn hình; điều đó có thể khiến các use case khác tải thừa dữ liệu.

### 10.3. DTO projection chỉ lấy dữ liệu cần dùng

Nếu màn hình chỉ cần tên khách hàng và số đơn, có thể dùng aggregate query:

```java
public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
```

```java
@Query("""
    select new com.example.CustomerOrderCount(
        c.id,
        c.name,
        count(o)
    )
    from Customer c
    left join c.orders o
    where c.name is not null
    group by c.id, c.name
    order by c.name, c.id
    """)
List<CustomerOrderCount> findNamedOrderCounts();
```

Query này trả kết quả tổng hợp trực tiếp, không cần tải collection orders rồi gọi `size()` cho từng Customer. Constructor expression phải khớp package, thứ tự và kiểu tham số DTO; kiểu kết quả của `count()` là Long.

Projection đặc biệt phù hợp với read API và báo cáo vì tránh hydrate entity/association không cần thiết.

### 10.4. Batch fetching

Nếu không thể join tất cả association, Hibernate có thể gom nhiều lazy load vào một câu query dùng IN.

Cấu hình toàn cục:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 25
```

Hoặc đặt trên association/entity bằng `@BatchSize`:

```java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@BatchSize(size = 25)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Thay vì một SELECT cho mỗi customer, Hibernate có thể tải collection cho một nhóm customer bằng điều kiện tương tự:

```sql
select ...
from purchase_order
where customer_id in (?, ?, ..., ?);
```

Batch fetching thường giảm số query từ 1 + N xuống khoảng 1 + số batch cần thiết, tùy số collection chưa khởi tạo, batch size, cache và provider. Nó giảm round-trip nhưng không nhất thiết loại bỏ hoàn toàn query phụ; vẫn cần đo SQL thực tế.

Đây là tính năng Hibernate-specific, không phải bảo đảm chung của Jakarta Persistence.

### 10.5. Subselect fetching

Hibernate có thể dùng `@Fetch(FetchMode.SUBSELECT)` cho collection để tải các collection của nhóm parent bằng một query subselect sau query cha:

```java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Cơ chế này có thể hữu ích khi một use case tải một nhóm Customer rồi cần collection của tất cả Customer đó. Tuy nhiên, nó phụ thuộc Hibernate, query context và cách collection được truy cập. Kiểm tra SQL, kích thước tập parent và bộ nhớ trước khi áp dụng rộng.

### 10.6. Chọn fetch strategy theo use case

| Cách | Khi phù hợp | Điều cần đo |
|---|---|---|
| JOIN FETCH | Cần association cho một use case và tập dữ liệu vừa phải | Số hàng join, dữ liệu trùng, pagination |
| EntityGraph | Muốn khai báo fetch plan theo repository method | SQL provider thực tế phát ra |
| DTO projection | Chỉ cần một tập field/aggregate cụ thể | Số cột, group/aggregate, mapping |
| Batch fetching | Cần lazy association nhưng muốn gom tải theo nhóm | Số batch và kích thước IN |
| SUBSELECT fetching | Cần cùng một collection cho một nhóm parent | Phạm vi parent và query subselect |

Không có một chiến lược tối ưu cho mọi association. Chọn theo dữ liệu, endpoint, số parent, kích thước collection và nhu cầu response.

## 11. N+1 và phân trang collection

Một lỗi phổ biến là thêm `JOIN FETCH` cho collection vào repository method trả `Page<Customer>`. Database phân trang trên hàng join, trong khi ứng dụng cần phân trang theo Customer. Một Customer có nhiều Order có thể chiếm nhiều hàng SQL và làm kết quả phân trang không đúng như mong muốn.

Hibernate có thể cảnh báo hoặc phải áp dụng pagination trong bộ nhớ tùy query/provider/version. Điều này có thể gây tải quá nhiều hàng.

Các cách xử lý:

1. Phân trang Customer trước bằng query chỉ lấy ID hoặc DTO root.
2. Chạy query thứ hai tải association cho danh sách ID của trang bằng `where c.id in :ids`.
3. Sắp xếp kết quả tải association lại theo thứ tự ID của trang vì `IN` không bảo đảm thứ tự.
4. Hoặc dùng DTO projection/aggregate query nếu response chỉ cần dữ liệu đọc.

Ví dụ hai bước:

```java
Page<Long> pageIds =
    customerRepository.findNamedIds(PageRequest.of(0, 20));

List<Customer> customers =
    customerRepository.findWithOrdersByIdIn(pageIds.getContent());
```

Repository:

```java
@Query("""
    select c.id
    from Customer c
    where c.name is not null
    order by c.name, c.id
    """)
Page<Long> findNamedIds(Pageable pageable);

@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    where c.id in :ids
    """)
List<Customer> findWithOrdersByIdIn(@Param("ids") Collection<Long> ids);
```

Ví dụ cần xử lý riêng trường hợp trang rỗng để tránh gọi query với danh sách ID rỗng; cũng cần giữ thứ tự trang ban đầu khi xây response. Count query cho page ID phải đếm đúng số Customer phù hợp.

## 12. Thiết kế test để bắt N+1

### 12.1. Tạo dữ liệu có nhiều parent

Test chỉ có một Customer không thể bộc lộ rõ N+1. Hãy tạo nhiều parent với số lượng association khác nhau, ví dụ 10 hoặc 20 Customer, mỗi người có một vài Order.

### 12.2. Flush, clear rồi mới đo

Một mẫu test:

```java
@DataJpaTest
class CustomerRepositoryNPlusOneTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void fetchPlanDoesNotIssueOneQueryPerCustomer() {
        // Tạo fixture trước phần đo.
        for (int i = 0; i < 10; i++) {
            Customer customer = new Customer("Customer " + i);
            entityManager.persist(customer);

            // Even an empty lazy collection needs one SELECT after clear() to confirm it has no rows.
        }

        entityManager.flush();
        entityManager.clear();

        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();
        statistics.clear();

        List<Customer> customers =
            customerRepository.findNamedWithOrders();

        customers.forEach(c -> c.getOrders().size());

        long statements =
            statistics.getPrepareStatementCount();

        assertThat(statements).isLessThan(10);
    }
}
```

Đây là khung test minh họa; constructor, trạng thái active, mapping và repository method cần phù hợp với entity thực tế. Trong test production-grade, hãy đặt fixture rõ ràng và assertion theo fetch plan dự kiến (ví dụ query content và count nếu có), thay vì chỉ chọn một ngưỡng rộng.

Statistics là counter dùng chung trong SessionFactory; tránh chạy song song test đo query count trên cùng context. Nếu test dùng cache, hãy kiểm soát cache state. Đừng để query fixture bị tính vào phép đo: reset statistics sau khi persist/flush/clear.

### 12.3. So sánh nhiều kích thước dữ liệu

Chạy cùng use case với 1, 10 và 100 parent. Nếu số statement tăng tuyến tính với parent count, còn khả năng N+1. Nếu số statement giữ gần như cố định hoặc tăng theo batch count đã dự kiến, fetch plan có thể đã cải thiện.

Cũng cần xác nhận:
- Số Customer trả về không đổi.
- Mỗi Customer có đúng danh sách Order.
- Customer không có Order vẫn xuất hiện nếu yêu cầu LEFT JOIN.
- Page metadata và sort không thay đổi.
- Không có lazy query phát sinh khi serialize response.
- Query count không bị giảm giả tạo chỉ vì cache nóng.

## 13. Quy trình điều tra N+1 trong môi trường thực tế

Có thể áp dụng quy trình sau:

1. **Chọn một request cụ thể:** xác định endpoint, input, số entity và dữ liệu liên quan.
2. **Thu SQL:** bật SQL logging có kiểm soát hoặc dùng datasource proxy/APM.
3. **Nhóm SQL theo hình dạng:** tìm câu SELECT lặp lại với cùng bảng, predicate và số placeholder.
4. **Đối chiếu bind values:** xem khóa ngoại hoặc ID thay đổi qua mỗi lần thực thi.
5. **Tìm điểm kích hoạt:** kiểm tra vòng lặp, mapper, getter lazy, serializer và repository call trong loop.
6. **Đếm baseline:** ghi lại statement count, thời gian, rows và connection wait.
7. **Chọn fetch strategy:** join fetch, EntityGraph, projection, batch fetching hoặc query riêng.
8. **Đo lại cùng điều kiện:** giữ nguyên fixture và cache state.
9. **Kiểm tra tính đúng:** so sánh kết quả, pagination, quyền truy cập và dữ liệu liên quan.
10. **Theo dõi sau triển khai:** xác nhận query count và latency trên dữ liệu gần production.

Không sửa N+1 chỉ bằng cách tăng connection pool. Điều đó có thể làm nhiều query chạy đồng thời hơn nhưng tổng số round-trip vẫn giữ nguyên, thậm chí làm database quá tải.

## 14. Lỗi thường gặp khi nhận diện

| Nhầm lẫn | Vì sao sai | Cách kiểm tra đúng |
|---|---|---|
| Thấy nhiều SELECT là kết luận N+1 | Có thể là các query độc lập có chủ đích | Tìm mẫu 1 query gốc + query lặp theo từng entity |
| Chỉ đếm SQL trong repository | Lazy load có thể phát sinh trong mapper/serialization | Đo toàn bộ use case/request |
| Chỉ nhìn câu SQL, không xem bind | Không biết mỗi lần query tải khóa nào | Xem bind log hoặc SQL capture có parameter |
| Test chỉ có một parent | Không thể thấy số query tăng theo N | Tạo nhiều parent và so sánh 1/10/100 |
| Cache nóng làm query count thấp | Cache che giấu việc tải lặp | Kiểm soát cache state và test cache lạnh |
| Dùng JOIN FETCH cho mọi quan hệ | Có thể tải quá nhiều hàng hoặc làm hỏng pagination | Chọn fetch theo use case và đo row count |
| Dùng EAGER toàn cục để sửa | Các endpoint khác có thể tải thừa dữ liệu | Dùng fetch plan theo use case |
| Batch fetching được xem là xóa N+1 | Vẫn có thể còn nhiều batch query | Đếm statement sau khi bật batch |
| Chỉ đo thời gian, không đếm query | Cache/DB load khác nhau làm số đo nhiễu | Kết hợp statement count, SQL shape và latency |
| Sửa xong nhưng không kiểm tra response | Có thể mất dữ liệu hoặc thay đổi semantics | So sánh nội dung và metadata trước/sau |

## 15. Checklist nhận diện và xử lý N+1

- [ ] Đã chọn một endpoint/use case và xác định số entity gốc.
- [ ] Đã thu SQL trong toàn bộ request, kể cả mapper và serialization.
- [ ] Có một query lấy danh sách entity gốc.
- [ ] Có query lặp lại với cùng hình dạng SQL.
- [ ] Bind parameter thay đổi theo ID/foreign key của từng entity.
- [ ] Số query phụ tăng theo số parent hoặc association được truy cập.
- [ ] Đã kiểm tra first-level cache và second-level cache.
- [ ] Đã đo statement count bằng Hibernate statistics hoặc SQL capture.
- [ ] Đã xác định property/getter/repository call kích hoạt query.
- [ ] Đã chọn fetch join, EntityGraph, DTO, batch hoặc subselect theo use case.
- [ ] Đã kiểm tra tác động tới pagination và số hàng join.
- [ ] Đã flush/clear fixture và kiểm soát cache khi test.
- [ ] Đã so sánh query count, latency và nội dung kết quả trước/sau.
- [ ] Đã kiểm tra trên database và provider gần với production.

## 16. Kết luận

Nhận diện N+1 cần kết hợp hai bằng chứng: số câu SQL tăng theo số entity và hình dạng SQL lặp lại với bind parameter thay đổi. Mẫu điển hình là một query lấy N entity cha, sau đó N query cùng cấu trúc tải association cho từng entity. Cần theo dõi toàn bộ request vì query có thể phát sinh trong service loop, DTO mapper hoặc JSON serialization.

SQL log cho biết hình dạng và thứ tự query; bind log cho biết ID nào được tải; Hibernate Statistics hoặc datasource proxy giúp đếm statement. Khi đo, phải kiểm soát fixture, transaction, persistence context và cache để tránh kết luận sai.

Có thể xử lý bằng JOIN FETCH, EntityGraph, DTO projection, batch fetching hoặc subselect fetching. Chọn theo kích thước dữ liệu và nhu cầu use case; đặc biệt cẩn thận khi phân trang collection. Sau khi sửa, hãy chạy lại cùng dữ liệu, so sánh số statement, latency, số hàng và nội dung response. Mục tiêu là giảm round-trip mà vẫn giữ đúng dữ liệu và semantics của API.