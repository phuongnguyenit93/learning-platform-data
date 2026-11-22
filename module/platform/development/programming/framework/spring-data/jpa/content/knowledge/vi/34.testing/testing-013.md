# Phát hiện N+1 và hồi quy số truy vấn

N+1 là vấn đề hiệu năng xảy ra khi ứng dụng chạy một truy vấn để lấy danh sách entity gốc, rồi tiếp tục chạy thêm một truy vấn cho từng entity khi truy cập quan hệ lazy. Với N bản ghi, số truy vấn có thể tăng từ 1 lên 1 + N. Endpoint vẫn trả dữ liệu đúng và có thể chạy nhanh với vài bản ghi, nhưng chậm rõ rệt khi dữ liệu tăng.

Kiểm thử hồi quy số truy vấn giúp phát hiện thay đổi làm số SQL tăng ngoài dự kiến. Để kiểm thử có ý nghĩa, cần tạo dữ liệu đủ đại diện, đo truy vấn trong đúng phạm vi nghiệp vụ, loại ảnh hưởng của cache và persistence context, rồi đặt giới hạn truy vấn phù hợp với fetch strategy đã chọn.

## 1. N+1 query là gì?

Giả sử ứng dụng có hai entity: `Order` và `Customer`. Mỗi đơn hàng tham chiếu đến một khách hàng bằng quan hệ lazy.

```java
@Entity
public class Order {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    // getter và các trường khác
}
```

Repository tải danh sách đơn hàng:

```java
List<Order> orders = orderRepository.findByStatus("OPEN");
```

Nếu service hoặc mapper lần lượt đọc `order.getCustomer().getName()`, Hibernate có thể phải tải customer riêng cho từng order:

```java
for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Với 5 order có 5 customer khác nhau, luồng SQL có thể là:

```sql
SELECT ... FROM orders WHERE status = 'OPEN';

SELECT ... FROM customer WHERE id = 101;
SELECT ... FROM customer WHERE id = 102;
SELECT ... FROM customer WHERE id = 103;
SELECT ... FROM customer WHERE id = 104;
SELECT ... FROM customer WHERE id = 105;
```

Tổng cộng có 6 truy vấn: một truy vấn gốc và năm truy vấn tải quan hệ. Nếu có 100 order với 100 customer khác nhau, tổng số có thể là 101.

N+1 không phải lúc nào cũng đúng bằng 1 + N. Nếu nhiều order tham chiếu cùng một customer, first-level cache trong persistence context có thể giúp Hibernate không tải lại cùng một entity nhiều lần. Batch fetching cũng có thể gom nhiều lần tải thành một số truy vấn `IN`. Tuy vậy, số SQL tăng theo số bản ghi hoặc theo nhóm nhỏ vẫn là dấu hiệu cần điều tra.

N+1 có thể xuất hiện với:

- Quan hệ `@ManyToOne` hoặc `@OneToOne` lazy.
- Collection `@OneToMany` hoặc `@ManyToMany` khi duyệt từng collection.
- Mapper chuyển entity sang DTO.
- Jackson hoặc JSON serializer khi trả entity trực tiếp.
- Template server-side truy cập thuộc tính lazy.
- Logic tính toán, logging hoặc `toString()` vô tình đọc quan hệ.

Vì vậy, không chỉ kiểm tra câu lệnh repository. Hãy kiểm tra toàn bộ đường đi từ lúc tải entity đến khi tạo response.

## 2. Nhận biết N+1 từ SQL và số liệu runtime

### 2.1. Bật log SQL khi phát triển

Với Spring Boot và Hibernate, có thể bật log câu SQL:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
```

Nếu cần xem bind parameter trong môi trường phát triển, Hibernate 6 có thể dùng:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Log SQL giúp nhận ra cùng một mẫu truy vấn được lặp lại với nhiều ID khác nhau. Không nên bật bind parameter ở production một cách tùy tiện vì giá trị có thể chứa dữ liệu cá nhân, thông tin nhạy cảm hoặc token.

Ví dụ dấu hiệu N+1 trong log:

```text
select ... from orders where status=?
select ... from customer where id=?
select ... from customer where id=?
select ... from customer where id=?
select ... from customer where id=?
```

Các câu truy vấn thứ hai lặp cùng cấu trúc nhưng khác tham số thường cho thấy ứng dụng đang tải quan hệ từng bản ghi.

### 2.2. Dùng Hibernate Statistics

Hibernate cung cấp `Statistics` để quan sát số câu lệnh chuẩn bị, số lần tải entity/collection, cache hit/miss và các thông tin khác.

Bật thống kê trong cấu hình:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Đọc thống kê trong code:

```java
import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Component;

@Component
public class HibernateQueryMetrics {

    private final Statistics statistics;

    public HibernateQueryMetrics(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public long preparedStatementCount() {
        return statistics.getPrepareStatementCount();
    }

    public long entityFetchCount() {
        return statistics.getEntityFetchCount();
    }

    public long collectionFetchCount() {
        return statistics.getCollectionFetchCount();
    }
}
```

Các chỉ số có ý nghĩa khác nhau:

- `getPrepareStatementCount()`: số lần Hibernate chuẩn bị JDBC statement trong phạm vi thống kê.
- `getEntityFetchCount()`: số lần fetch entity phát sinh ngoài các entity được lấy trực tiếp trong truy vấn chính.
- `getCollectionFetchCount()`: số lần fetch collection.
- Cache hit/miss cho biết dữ liệu được phục vụ từ cache hay phải tải thêm.

Statistics là số liệu ở phạm vi SessionFactory, có thể bao gồm hoạt động của nhiều request và test cùng lúc. Khi dùng để kiểm thử, hãy xóa thống kê trước vùng đo, chạy test tuần tự hoặc cô lập workload, và chỉ đo khoảng thời gian cần thiết.

### 2.3. Dùng datasource proxy hoặc công cụ quan sát SQL

Có thể đặt datasource proxy giữa ứng dụng và JDBC driver để đếm câu SQL, ghi thời gian thực thi và gom truy vấn theo request. Các thư viện như datasource-proxy hoặc P6Spy thường hữu ích khi cần quan sát cả SQL phát sinh từ Hibernate lẫn JDBC trực tiếp.

Công cụ ở tầng datasource có thể thấy câu SQL thực thi thực tế, kể cả câu lệnh không đi qua JPQL. Tuy nhiên, cần cấu hình lọc theo request/test và tránh ghi giá trị tham số nhạy cảm. Với hệ thống nhiều request đồng thời, không nên lấy tổng số SQL toàn ứng dụng làm query count của một endpoint.

## 3. Phân biệt N+1 với các truy vấn hợp lệ

Không phải nhiều câu SQL đều là N+1. Một nghiệp vụ có thể cần nhiều truy vấn có chủ đích, ví dụ:

- Một truy vấn lấy trang ID và một truy vấn lấy dữ liệu chi tiết.
- Một truy vấn lấy entity chính và một truy vấn lấy aggregate thống kê.
- Một truy vấn tải entity và một truy vấn tải collection theo batch.
- Các câu lệnh ghi dữ liệu hoặc kiểm tra ràng buộc trong một transaction.

Hãy xem xét cấu trúc và sự tăng trưởng của số truy vấn, không chỉ nhìn một con số tổng.

| Dấu hiệu | Khả năng |
|---|---|
| Một truy vấn gốc, sau đó cùng một mẫu SELECT chạy lặp với từng ID | N+1 |
| Số truy vấn gần như cố định khi số bản ghi tăng | Fetch plan có thể đã được tối ưu |
| Truy vấn quan hệ chạy theo từng nhóm ID trong mệnh đề `IN` | Batch fetching |
| Hai truy vấn có mục đích rõ ràng: lấy ID trang rồi tải quan hệ | Truy vấn phân trang hai bước |
| Một câu SQL trả số hàng rất lớn do join nhiều collection | Có thể là row multiplication; số query thấp vẫn có thể chậm |

N+1 là một vấn đề về số lần round-trip và cách tải dữ liệu. Một truy vấn duy nhất vẫn có thể chậm nếu join tạo ra quá nhiều hàng, đọc nhiều cột hoặc dùng execution plan kém.

## 4. Cách loại bỏ N+1

Chọn giải pháp theo dữ liệu endpoint thực sự cần. Không có một fetch strategy tốt nhất cho mọi truy vấn.

### 4.1. Dùng JOIN FETCH cho quan hệ cần thiết

Với quan hệ to-one cần hiển thị trong cùng một response, JPQL fetch join thường là lựa chọn trực tiếp:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        join fetch o.customer
        where o.status = :status
        """)
    List<Order> findWithCustomerByStatus(
            @Param("status") String status
    );
}
```

Service ánh xạ sang DTO trong transaction:

```java
public record OrderSummary(Long id, String customerName) {}

@Service
public class OrderQueryService {

    private final OrderRepository orderRepository;

    public OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> findOpenOrderSummaries() {
        return orderRepository.findWithCustomerByStatus("OPEN")
                .stream()
                .map(order -> new OrderSummary(
                        order.getId(),
                        order.getCustomer().getName()
                ))
                .toList();
    }
}
```

Truy vấn chính đã tải customer, nên mapper không cần phát sinh thêm một SELECT cho mỗi order.

Dùng `left join fetch` nếu quan hệ có thể không tồn tại và vẫn cần giữ entity gốc trong kết quả. Dùng `join fetch` khi quan hệ bắt buộc phải có theo yêu cầu truy vấn.

### 4.2. Dùng @EntityGraph

`@EntityGraph` mô tả thuộc tính cần tải cho một phương thức repository:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {"customer"})
    List<Order> findByStatus(String status);
}
```

Service có thể ánh xạ kết quả thành DTO trong transaction như ví dụ trên. EntityGraph giúp tách fetch plan khỏi JPQL dài, đặc biệt khi cùng entity có nhiều cách đọc khác nhau.

Có thể khai báo nhiều thuộc tính hoặc đường dẫn lồng nhau, ví dụ `attributePaths = {"customer", "items.product"}`. Hãy kiểm tra SQL được tạo và số hàng trả về; EntityGraph là yêu cầu fetch plan, không phải cam kết một câu SQL duy nhất trong mọi provider/tình huống.

### 4.3. Dùng DTO projection khi chỉ cần một số trường

Nếu response chỉ cần ID và tên khách hàng, có thể truy vấn thẳng DTO thay vì tải toàn bộ entity:

```java
public record OrderSummary(Long id, String customerName) {}
```

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        c.name
    )
    from Order o
    join o.customer c
    where o.status = :status
    """)
List<OrderSummary> findSummariesByStatus(
        @Param("status") String status
);
```

Projection thường phù hợp với endpoint danh sách, báo cáo và màn hình chỉ đọc. Nó giảm lượng cột/entity được tải và tránh serializer vô tình kích hoạt lazy loading.

Tên package trong JPQL constructor expression phải đúng package của record. Với interface projection, tên alias trong SELECT phải khớp getter/property mà Spring Data projection yêu cầu.

### 4.4. Dùng batch fetching khi không thể join tất cả quan hệ

Batch fetching gom việc tải nhiều proxy hoặc collection chưa khởi tạo vào một số truy vấn dùng mệnh đề `IN`.

Có thể cấu hình mặc định:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Hoặc chỉ định trên entity/collection bằng annotation Hibernate:

```java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
```

Với collection:

```java
@OneToMany(mappedBy = "order")
@BatchSize(size = 32)
private List<OrderItem> items = new ArrayList<>();
```

Nếu có 100 collection cần tải và batch size là 32, số truy vấn tải collection có thể giảm còn khoảng 4 thay vì 100. Con số thực tế phụ thuộc số collection cần tải, dữ liệu, dialect và cách provider tạo câu lệnh.

Batch fetching giảm N+1 nhưng không nhất thiết biến toàn bộ endpoint thành một truy vấn. Nó hữu ích khi join nhiều collection tạo ra quá nhiều hàng hoặc khi cần giữ cách truy cập lazy.

### 4.5. Cân nhắc SUBSELECT cho collection

Hibernate hỗ trợ `@Fetch(FetchMode.SUBSELECT)` cho một số collection mapping. Khi collection của các parent entity được tải, provider có thể dùng một truy vấn phụ dựa trên truy vấn parent thay vì một SELECT cho từng parent.

Đây là tính năng riêng Hibernate. Nó có thể hữu ích với một nhóm parent được tải cùng nhau, nhưng có thể tải nhiều collection hơn nhu cầu nếu persistence context chứa nhiều parent. Hãy đo SQL và bộ nhớ trước khi áp dụng.

## 5. N+1 khi kết hợp với phân trang

Fetch join quan hệ to-one thường phù hợp với phân trang. Fetch join collection cần cẩn trọng vì một parent có nhiều child làm nhân số hàng SQL. Điều này khiến việc áp dụng LIMIT/OFFSET trực tiếp trên kết quả join không còn tương đương phân trang theo parent.

Với Hibernate, fetch join collection kết hợp pagination có thể tạo cảnh báo hoặc buộc provider tải nhiều dữ liệu rồi phân trang trong bộ nhớ, tùy phiên bản và cấu hình. Không nên bỏ qua cảnh báo này trong production.

Một cách thường dùng là phân trang hai bước:

1. Truy vấn một trang ID của entity gốc theo điều kiện và thứ tự mong muốn.
2. Truy vấn entity cùng các quan hệ cần thiết bằng `where id in :ids`.
3. Khôi phục thứ tự theo danh sách ID ở bước đầu, vì `IN` không bảo đảm thứ tự kết quả.

Ví dụ repository:

```java
@Query("""
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findPageIds(
        @Param("status") String status,
        Pageable pageable
);

@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id in :ids
    """)
List<Order> findWithItemsByIdIn(@Param("ids") Collection<Long> ids);
```

Service lấy trang ID rồi tải chi tiết. Khi sắp xếp lại, dùng map theo ID hoặc duyệt danh sách ID ban đầu để dựng kết quả theo đúng thứ tự. Nếu trang ID rỗng, trả kết quả rỗng mà không chạy truy vấn chi tiết.

Cách hai bước thường tạo hai truy vấn chính cho một trang, bất kể trang có bao nhiêu parent. Đây là một số truy vấn có chủ đích, không phải N+1. Hãy xử lý cả trường hợp dữ liệu bị xóa hoặc thay đổi giữa hai truy vấn theo transaction isolation và yêu cầu nghiệp vụ.

## 6. Thiết kế kiểm thử hồi quy số truy vấn

Một kiểm thử query count tốt phải phát hiện được khi thay đổi mapping, mapper hoặc serializer làm phát sinh thêm SQL. Các nguyên tắc quan trọng:

- Tạo nhiều bản ghi gốc, ít nhất vài bản ghi; nên dùng quan hệ khác nhau để tránh L1 cache che giấu N+1.
- Đảm bảo dữ liệu test thực sự có quan hệ cần được tải.
- Chỉ bắt đầu đếm sau khi seed dữ liệu hoàn tất.
- Đo trong một request/service invocation cụ thể, không đếm toàn bộ hoạt động của ứng dụng.
- Dùng persistence context mới hoặc gọi service qua transaction riêng.
- Tắt L2/query cache trong test đo N+1, hoặc evict cache trước vùng đo.
- Chạy cùng điều kiện khi so sánh baseline và bản thay đổi.
- Đặt ngưỡng theo fetch plan có chủ đích, không cố định một con số tùy tiện cho mọi test.

### 6.1. Dùng Hibernate Statistics trong integration test

Ví dụ dưới đây giả định:

- Hibernate là JPA provider.
- Dữ liệu fixture đã được tạo và commit trước khi bắt đầu đo.
- `findOpenOrderSummaries()` dùng fetch join hoặc EntityGraph để tải customer.
- Phương thức service chạy transaction riêng và trả DTO.
- Test không chạy song song với test khác đang dùng cùng SessionFactory.

Cấu hình test:

```properties
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.cache.use_second_level_cache=false
spring.jpa.properties.hibernate.cache.use_query_cache=false
```

Integration test:

```java
import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderQueryCountTest {

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private OrderQueryService orderQueryService;

    @Test
    void shouldLoadOpenOrderSummariesWithoutNPlusOne() {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        Statistics statistics = sessionFactory.getStatistics();

        // Fixture đã được seed và commit trước điểm này.
        statistics.clear();

        orderQueryService.findOpenOrderSummaries();

        long statements = statistics.getPrepareStatementCount();

        // Fetch join/EntityGraph tải order và customer trong một SELECT.
        assertThat(statements).isEqualTo(1L);
    }
}
```

Đây là ví dụ cho service chỉ thực hiện một SELECT và không chạy truy vấn phụ. Nếu use case cần hai truy vấn có chủ đích, hãy đặt ngưỡng tương ứng. Không sao chép giá trị `1` cho mọi test.

Không đặt `@Transactional` bao quanh test theo cách khiến dữ liệu fixture, service và assertion cùng dùng một persistence context mà không kiểm soát. Nếu test transaction giữ L1 cache, lazy access có thể không phát sinh SQL như khi request thực tế. Hãy tạo fixture trong transaction riêng, commit, rồi gọi service qua proxy trong transaction riêng.

`Statistics` là dữ liệu toàn SessionFactory. Nếu test suite chạy song song, một test khác có thể làm tăng số đếm giữa `clear()` và assertion. Tắt parallel execution cho nhóm test này hoặc dùng bộ đếm ở datasource proxy có thể cô lập theo request/test.

### 6.2. Kiểm tra số truy vấn không tăng tuyến tính theo N

Một kiểm thử hồi quy mạnh hơn so sánh hành vi ở hai quy mô dữ liệu:

- Với 5 order, service dùng một truy vấn tải order và customer.
- Với 50 order, service vẫn dùng một truy vấn tương đương.
- Nếu query count tăng từ 1 lên 51, rất có thể một quan hệ lazy đang bị tải riêng cho từng order.

Nếu dùng batch fetching, số truy vấn có thể tăng theo số batch chứ không cố định. Ví dụ batch size 32 thì 5 và 20 order có thể cùng một batch, còn 50 order có thể cần thêm một batch. Khi đó, kiểm thử nên xác nhận mức tăng theo batch đã dự kiến, không áp đặt số truy vấn bằng một.

Dữ liệu test cần có đủ customer khác nhau. Nếu 50 order cùng trỏ đến một customer, L1 cache có thể chỉ cần một truy vấn customer và test không tái hiện tình huống xấu.

### 6.3. Kiểm thử cả response serialization

Nếu endpoint trả entity trực tiếp, truy vấn có thể chỉ xuất hiện khi Jackson serialize response. Một unit test gọi service sẽ không thấy những truy vấn này.

Với API, hãy thêm integration test qua MockMvc hoặc WebTestClient:

1. Tạo dữ liệu có nhiều quan hệ.
2. Gọi endpoint thật.
3. Để framework hoàn tất việc tạo response.
4. Đo SQL trong phạm vi request và kiểm tra nội dung JSON.
5. Chạy test với `spring.jpa.open-in-view=false` nếu kiến trúc yêu cầu service phải tải đủ dữ liệu.

DTO được tạo trong service giúp phần lớn SQL phát sinh trong transaction rõ ràng hơn. Dù vậy, vẫn cần đo toàn bộ request để phát hiện truy vấn do các component khác thực hiện.

## 7. Tránh kiểm thử query count dễ sai

| Cách kiểm thử | Vì sao dễ sai | Cách cải thiện |
|---|---|---|
| Chỉ gọi repository một lần với một entity | Không tạo đủ số bản ghi để thấy N+1 | Dùng nhiều parent và nhiều relation khác nhau |
| Đọc entity hai lần trong cùng EntityManager | Lần đọc sau có thể được phục vụ từ L1 | Dùng persistence context mới |
| Giữ L2/query cache bật | Cache hit có thể che giấu truy vấn lặp | Tắt cache hoặc evict trước khi đo |
| Đếm SQL toàn bộ test suite | Bao gồm setup, teardown và test khác | Reset counter ngay trước thao tác cần đo |
| Đếm toàn bộ ứng dụng đang có traffic | Request khác làm nhiễu kết quả | Correlate theo request hoặc chạy test cô lập |
| Chỉ kiểm tra thời gian chạy | Kết quả bị ảnh hưởng bởi máy, cache và tải hệ thống | Kết hợp query count, execution plan và latency |
| Khóa cứng số query không theo use case | Thay đổi hợp lệ có thể làm test thất bại | Ghi rõ các truy vấn dự kiến và lý do |
| Chỉ kiểm tra service khi endpoint trả entity | Bỏ sót truy vấn lúc serialize | Kiểm thử HTTP response hoàn chỉnh |

Query count là một chỉ số quan trọng nhưng không đại diện toàn bộ hiệu năng. Một câu SQL join lớn có thể chậm hơn hai câu SQL nhỏ. Luôn xem thêm số hàng trả về, lượng dữ liệu truyền qua mạng, index, execution plan và latency.

## 8. Công cụ quan sát trong môi trường thực tế

Khi điều tra endpoint chậm, nên kết hợp nhiều nguồn:

- **Hibernate SQL log:** xác định mẫu câu SQL và tham số trong môi trường phát triển.
- **Hibernate Statistics:** xem entity fetch, collection fetch, prepared statement và cache hit/miss.
- **Datasource proxy/P6Spy:** đếm và đo thời gian SQL ở tầng JDBC.
- **APM/tracing:** gắn thời gian database span với HTTP request hoặc job cụ thể.
- **Database slow query log:** tìm câu lệnh chậm và execution plan.
- **Metrics theo endpoint:** theo dõi p50/p95/p99, số SQL/request và lỗi timeout.

Không giữ SQL log chi tiết ở production nếu chưa có chính sách bảo vệ dữ liệu và giới hạn dung lượng log. Thay vào đó, ưu tiên metric và trace có sampling, đồng thời che giá trị bind parameter.

Khi có hồi quy, so sánh hai phiên bản với cùng dữ liệu và workload. Kiểm tra thay đổi ở entity mapping, `fetch`, EntityGraph, mapper, serializer, repository query và cache configuration.

## 9. Các lỗi thường gặp khi tối ưu

### 9.1. Chuyển mọi quan hệ sang EAGER

Đổi `LAZY` thành `EAGER` có thể làm truy vấn phụ biến mất trong một luồng nhưng tải dữ liệu không cần thiết ở các luồng khác. Eager không bảo đảm provider luôn tạo một JOIN duy nhất; provider có thể dùng nhiều SELECT.

Hãy chọn fetch plan theo use case bằng EntityGraph, fetch join hoặc projection.

### 9.2. Fetch join nhiều collection cùng lúc

Join hai collection lớn có thể nhân số hàng theo tích số phần tử của mỗi collection. Ví dụ một order có 10 item và 4 tag có thể tạo khoảng 40 hàng SQL cho cùng order trước khi provider hợp nhất entity.

Chọn projection, batch fetching hoặc tải collection theo truy vấn riêng. Đừng đánh đổi N+1 bằng một truy vấn khổng lồ không kiểm soát.

### 9.3. Dùng DISTINCT nhưng không đo SQL

`DISTINCT` có thể giúp loại entity gốc trùng trong kết quả JPQL, nhưng không nhất thiết loại bỏ chi phí hàng bị nhân trong SQL. Hãy xem câu SQL và số hàng database thực trả.

### 9.4. Bỏ qua serializer và toString()

Một getter được gọi trong JSON serializer, debugger, logger hoặc `toString()` có thể kích hoạt lazy loading. Tránh đưa quan hệ entity vào `toString()` và không serialize entity graph tùy tiện.

### 9.5. Tối ưu query count nhưng bỏ qua dữ liệu

Một fetch plan có thể giảm số câu SQL nhưng tải hàng nghìn cột hoặc hàng không cần thiết. Đánh giá tổng thể số query, số hàng, số byte, memory và latency.

## 10. Checklist phát hiện và ngăn hồi quy N+1

- [ ] Đã xác định endpoint/service và quan hệ lazy có khả năng phát sinh truy vấn.
- [ ] Đã kiểm tra SQL lặp lại theo từng entity hoặc collection.
- [ ] Fixture có nhiều parent và nhiều relation khác nhau.
- [ ] Đo query count sau khi seed dữ liệu và trong đúng phạm vi request/service.
- [ ] Persistence context mới được sử dụng cho vùng đo.
- [ ] L2/query cache được kiểm soát để không che giấu truy vấn.
- [ ] Fetch strategy được chọn theo dữ liệu cần trả về.
- [ ] Collection fetch join và pagination đã được đánh giá riêng.
- [ ] Có regression test kiểm tra query count ở quy mô dữ liệu khác nhau.
- [ ] API serialization được kiểm thử nếu response có liên quan lazy.
- [ ] Metrics/trace theo dõi SQL và latency sau triển khai.
- [ ] Query count được xem cùng row count, execution plan và dữ liệu truyền tải.

Phát hiện N+1 cần quan sát cả cấu trúc SQL lẫn cách số truy vấn thay đổi khi số entity tăng. Regression test có fixture đủ lớn, persistence context mới và cache được kiểm soát sẽ phát hiện vấn đề đáng tin cậy hơn. Khi tối ưu, hãy chọn fetch join, EntityGraph, projection hoặc batch fetching theo từng use case và đo cả số truy vấn lẫn lượng dữ liệu thực tế.

## Tài liệu tham khảo

- [Hibernate ORM User Guide – Fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM – Statistics API](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/stat/Statistics.html)
- [Spring Data JPA – EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Boot – Data access and JPA configuration](https://docs.spring.io/spring-boot/reference/data/sql.html)