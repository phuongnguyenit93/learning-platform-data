# Kiểm thử số câu SQL và phát hiện N+1 theo từng thao tác trong Hibernate

## 1. Vì sao phải kiểm thử số truy vấn thay vì chỉ kiểm tra kết quả?

Một endpoint danh sách đơn hàng có thể trả về đúng 50 records và vẫn có hiệu năng rất kém. Test thông thường:

```java
List<OrderDto> result = orderService.listOrders();
assertThat(result).hasSize(50);
```

chỉ xác nhận dữ liệu đầu ra. Nó không phát hiện rằng ứng dụng đã chạy 101 câu SELECT để tạo danh sách đó.

Vấn đề thường gặp là **N+1 selects**:

- Một câu query tải N entity gốc.
- Khi code duyệt các entity và truy cập association LAZY, Hibernate tải thêm dữ liệu theo từng entity.
- Số câu SQL tăng gần tuyến tính theo số bản ghi hoặc số association cần khởi tạo.

Một test hiệu năng đơn giản nhưng có giá trị có thể xác nhận rằng use case tải 50 orders chỉ phát một số lượng truy vấn cố định, hoặc tăng theo các batch đã được thiết kế, thay vì tăng một truy vấn cho mỗi order.

**Kiểm thử query count biến fetch plan thành một thuộc tính có thể kiểm chứng của use case.** Nó không thay thế kiểm tra execution plan hay benchmark, nhưng giúp phát hiện sớm hồi quy N+1 trong CI.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt SQL statement, Hibernate query execution, JDBC prepared statement và batch execution.
2. Dùng Hibernate Statistics để đo số statements, query executions và entity loads.
3. Dùng JDBC-level instrumentation để đếm SELECT/INSERT/UPDATE/DELETE theo từng thao tác.
4. Tạo dữ liệu test có cardinality phù hợp để làm lộ N+1.
5. Tách transaction seed, transaction của use case và phần đo truy vấn.
6. Kiểm thử N+1 ở to-one, to-many, association lồng nhau và JSON serialization.
7. Viết assertion có ngưỡng hợp lý, không phụ thuộc một con số tuyệt đối mong manh.
8. Kiểm thử JOIN FETCH, EntityGraph, DTO projection, batch fetching và pagination.
9. Tránh false negatives do L1/L2 cache, test transaction, parallel tests hoặc fixture dùng chung association.
10. Đưa query budgets vào CI và theo dõi hiệu năng theo từng use case.

## 2. N+1 nhìn từ một thao tác cụ thể

Giả sử một màn hình cần hiển thị danh sách đơn hàng cùng tên khách hàng. Entity:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @Column(name = "order_number")
    private String orderNumber;

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public String getOrderNumber() { return orderNumber; }
}

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

Repository tải orders:

```java
List<PurchaseOrder> findAllByOrderByIdAsc();
```

Mapper:

```java
List<OrderDto> map(List<PurchaseOrder> orders) {
    return orders.stream()
        .map(order -> new OrderDto(
            order.getId(),
            order.getOrderNumber(),
            order.getCustomer().getName()
        ))
        .toList();
}
```

Nếu Customer chưa được fetch, thao tác tạo DTO có thể phát SQL:

```sql
SELECT ... FROM purchase_orders ORDER BY id;

SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
-- tiếp tục cho các customer chưa được load
```

Với N orders tham chiếu N customers khác nhau, số query có thể gần 1 + N. Nếu nhiều orders dùng chung một customer, persistence context có thể tái sử dụng entity đã load và số query thấp hơn. Vì vậy fixture cần được thiết kế để kiểm tra đúng worst case mà use case có thể gặp.

### 2.1. Test kết quả đúng chưa đủ

Một test có thể pass cả khi:

- Repository chạy 1 SELECT và mapper chạy thêm 50 SELECT.
- Hibernate load 500 entities không cần thiết.
- Một JOIN tạo 20.000 SQL rows lặp.
- Page query fetch collection rồi phân trang trong memory.
- Serialization kích hoạt lazy loading sau khi service trả về.

Query-count tests giúp phát hiện một số vấn đề này, nhưng cần kết hợp assertions về dữ liệu, pagination, rows, cache và latency.

## 3. Định nghĩa rõ thứ đang đếm

Cụm từ “số câu SQL” có thể chỉ nhiều counters khác nhau. Trước khi đặt budget, cần xác định metric.

| Metric | Đếm gì? | Dùng để |
|---|---|---|
| Hibernate query execution count | Các query executions Hibernate thống kê | Theo dõi HQL/JPQL query activity |
| Hibernate prepared statement count | Prepared statements được Hibernate thống kê | Ước lượng hoạt động JDBC statement |
| JDBC statement executions | Các lần driver thực thi statement | Quan sát SQL qua JDBC instrumentation |
| JDBC batch executions | Các lần executeBatch | Đo batching |
| JDBC batch entries | Số parameter sets được đưa vào batch | Đếm lượng DML được gom |
| Entity load count | Entity được load vào persistence context | Phát hiện hydrate quá nhiều entity |
| Entity fetch count | Entity được fetch ngoài một số đường load ban đầu theo Statistics semantics | Quan sát secondary loads |
| Collection fetch count | Collection được khởi tạo bằng fetch operation | Phát hiện collection loading |
| Result rows | Số rows database trả | Phát hiện join multiplication/over-fetch |
| Request DB duration | Thời gian DB work trong một request | Đo latency, không chỉ query count |

**Không coi những counters này là tương đương.** Một HQL query có thể sinh nhiều SQL statements; một JDBC batch có nhiều DML entries nhưng một lần executeBatch; một JOIN có một statement nhưng trả hàng nghìn rows.

### 3.1. Query count khác round trips

Một JDBC proxy có thể đếm statement executions, nhưng network round trips còn phụ thuộc driver, protocol, batching, fetch size và database. Khi nói “2 SQL statements”, hãy xác định đang nói hai executions quan sát được qua JDBC hay hai query executions của Hibernate.

### 3.2. Query count khác độ phức tạp

Một SELECT có JOIN nhiều bảng, aggregate nặng và trả 100.000 rows có thể chậm hơn 5 SELECT nhỏ có index tốt. Mục tiêu của query-count test là phát hiện sự tăng bất thường theo cardinality, không phải bắt mọi use case chỉ được dùng một câu SQL.

## 4. Chọn công cụ đo

Có hai nhóm công cụ thường dùng.

### 4.1. Hibernate Statistics

Ưu điểm:

- Có sẵn trong Hibernate.
- Đo query executions, prepared statements, entity loads/fetches, collection loads/fetches và cache activity.
- Hữu ích trong integration tests để so sánh fetch plans.
- Không cần log bind values.

Hạn chế:

- Statistics thường ở cấp SessionFactory, không tự cô lập theo request.
- Bộ đếm có thể bị nhiễu bởi test/request khác chạy song song.
- Không phải mọi counter đều là số JDBC executions.
- clear() reset counters toàn SessionFactory, có thể ảnh hưởng monitoring khác.

### 4.2. JDBC-level instrumentation

Có thể dùng thư viện như datasource-proxy hoặc một DataSource wrapper để đếm statements theo thread/request/test:

- Đếm SELECT, INSERT, UPDATE, DELETE.
- Đo thời gian từng execution.
- Quan sát batch operations.
- Gắn thông tin test/request context.
- Có thể thu SQL text để phân loại, nhưng không cần thu bind values.

Ưu điểm là gần với JDBC execution hơn Hibernate query counters. Hạn chế là phải cấu hình đúng DataSource mà Spring sử dụng, kiểm soát async/thread context và phân biệt batch với từng statement.

### 4.3. Kết hợp hai tầng

Một quy trình hữu ích:

1. Hibernate Statistics cho entity/collection/query counters.
2. JDBC proxy cho số executions thực tế và thời gian.
3. SQL DEBUG trên dữ liệu synthetic khi cần hiểu query shape.
4. Database execution plan cho query chậm.

Không cần bật bind TRACE trên dữ liệu production để đo N+1.

## 5. Bật Hibernate Statistics trong Spring Boot

Trong test configuration:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.open-in-view=false
```

Hoặc cấu hình riêng cho test profile:

```yaml
spring:
  jpa:
    open-in-view: false
    properties:
      hibernate:
        generate_statistics: true
```

`hibernate.generate_statistics` bật thống kê của SessionFactory. Tùy phiên bản Hibernate, cấu hình này có thể có overhead; thường chỉ bật trong test/diagnostic profile nếu không cần metrics liên tục ở production.

### 5.1. Lấy Statistics từ EntityManagerFactory

```java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Component;

@Component
public class HibernateStatisticsAccess {

    private final Statistics statistics;

    public HibernateStatisticsAccess(EntityManagerFactory emf) {
        SessionFactory sessionFactory =
            emf.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public Statistics get() {
        return statistics;
    }
}
```

Trong test, có thể inject trực tiếp EntityManagerFactory và unwrap SessionFactory để đo. Không cần thêm component production nếu chỉ dùng trong test.

### 5.2. Các counters thường dùng

```java
Statistics stats = entityManagerFactory
    .unwrap(SessionFactory.class)
    .getStatistics();

long preparedStatements = stats.getPrepareStatementCount();
long queryExecutions = stats.getQueryExecutionCount();
long entityLoads = stats.getEntityLoadCount();
long entityFetches = stats.getEntityFetchCount();
long collectionLoads = stats.getCollectionLoadCount();
long collectionFetches = stats.getCollectionFetchCount();
long secondLevelCacheHits = stats.getSecondLevelCacheHitCount();
```

Tên và semantics counters cần đối chiếu với Hibernate version đang dùng. Các số này là số tích lũy từ SessionFactory, không mặc định chỉ thuộc method vừa gọi.

### 5.3. Reset và đọc counters

```java
stats.setStatisticsEnabled(true);
stats.clear();

OrderDetailDto dto = orderQueryService.getDetail(orderId);

long statements = stats.getPrepareStatementCount();
long loads = stats.getEntityLoadCount();
```

Đọc ngay sau operation để hạn chế những query phụ từ test assertions làm tăng số đo. Nếu test chạy song song hoặc nhiều request cùng dùng SessionFactory, stats.clear() không an toàn cho attribution theo từng test.

### 5.4. Statistics có thể hoạt động khi không bật SQL logger

Đây là ưu điểm quan trọng: có thể đo query count mà không in từng câu SQL hoặc parameter values. Khi assertion fail, chỉ log counters và query key đã được phê duyệt; sau đó tái hiện trên dữ liệu giả để xem SQL shape.

## 6. Test theo từng thao tác: định nghĩa operation boundary

Một “thao tác” nên tương ứng với use case mà người dùng gọi, ví dụ:

- GET /orders: lấy trang danh sách.
- GET /orders/{id}: lấy chi tiết.
- POST /orders: tạo đơn.
- PATCH /orders/{id}/status: cập nhật trạng thái.
- DELETE /orders/{id}: xóa mềm hoặc xóa vật lý theo policy.

Mỗi use case có query budget riêng. Không cộng query count của toàn bộ test suite rồi kết luận một endpoint có N+1.

### 6.1. Đo đúng entry point

Nếu muốn kiểm tra transaction boundary của Spring service, gọi bean được Spring inject qua proxy:

```java
@Autowired
private OrderQueryService orderQueryService;

@Test
void measuresDetailUseCase() {
    OrderDetailDto dto = orderQueryService.getDetail(orderId);
}
```

Không gọi new OrderQueryService(...) trong test; làm vậy bỏ qua proxy, transaction management và các interceptors của Spring.

### 6.2. Tránh outer test transaction khi đo commit behavior

Nếu test method được đánh dấu `@Transactional`, service method có thể tham gia cùng transaction đang mở. Khi service trả về, transaction chưa commit và flush/commit SQL có thể xảy ra sau lúc bạn đã đọc counters.

Để kiểm tra một use case thực tế qua Spring proxy:

- Không đặt outer @Transactional lên test method.
- Seed dữ liệu trong transaction riêng đã commit.
- Gọi service bean.
- Đọc counters ngay sau khi method transactional hoàn tất.
- Nếu cần assert raw database state, thực hiện trong transaction mới sau khi đã chụp số đo.

Với @DataJpaTest, Spring thường bọc test trong transaction và rollback cuối test. Có thể dùng TestTransaction để commit/end transaction có chủ đích, hoặc dùng @SpringBootTest với TransactionTemplate cho ranh giới rõ ràng.

### 6.3. Flush không đồng nghĩa commit

Trong test repository, entityManager.flush() buộc Hibernate gửi SQL pending tới database; nó không commit transaction. Nếu đang đo thao tác ghi trong một transaction test, cần quyết định đo đến flush hay đến commit. Với service proxy được gọi ngoài outer transaction, transaction interceptor thường commit/rollback trước khi method trả về.

## 7. Chuẩn bị fixture để N+1 không bị che

Dữ liệu test quyết định test có bắt được lỗi hay không.

### 7.1. Dùng association targets khác nhau

Nếu 100 orders đều tham chiếu cùng một Customer, Hibernate có thể load Customer một lần rồi tái sử dụng trong L1. Test có thể chỉ thấy 2 statements dù code mapper đang truy cập lazy association theo từng order.

Để kiểm tra N+1 to-one, tạo mỗi Order một Customer khác nhau.

### 7.2. Dùng collection có cardinality rõ

Để kiểm tra N+1 to-many:

- Tạo 10 orders.
- Mỗi order có 2–5 lines.
- Tất cả orders đều có collection được truy cập.
- Không để collection rỗng khiến mapper bỏ qua getter.
- Không dựa vào L2 cache từ lần seed.

### 7.3. Tạo dữ liệu lồng nhau đủ đa dạng

Đối với Order → Lines → Product:

- Tạo nhiều orders.
- Mỗi order có nhiều lines.
- Mỗi line tham chiếu Product khác nhau để làm lộ lazy loads.
- Nếu muốn test trường hợp product được chia sẻ, tạo một test riêng.

### 7.4. Tránh fixture chỉ có một bản ghi

Một test với 1 Order thường không phân biệt được:

- 1 query tải root + 1 query tải association.
- 1 query tải root và association bằng JOIN.

Cả hai đều có thể chỉ là 2 statements. Với 50 records, khác biệt giữa fetch plan tốt và N+1 trở nên rõ rệt.

### 7.5. Seed dữ liệu trước khi reset counters

Seed thường tạo INSERTs, lấy sequence values, flush và có thể phát SELECT phụ. Nếu reset Statistics trước seed, query count của use case bị cộng thêm fixture work và assertion trở nên sai.

Thứ tự nên là:

1. Seed/commit fixture.
2. Clear L1 context và evict L2 nếu cần.
3. Reset counters.
4. Gọi đúng use case.
5. Chụp counters.
6. Assert kết quả và budget.

## 8. Tách seed transaction và measured transaction

Ví dụ dùng TransactionTemplate:

```java
@SpringBootTest
class OrderQueryCountIT {

    @Autowired
    private TransactionTemplate transactionTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    private Long seedOrders(int count) {
        return transactionTemplate.execute(status -> {
            for (int i = 0; i < count; i++) {
                Customer customer = new Customer("Customer " + i);
                entityManager.persist(customer);

                PurchaseOrder order = new PurchaseOrder(
                    customer, "ORDER-" + i
                );
                entityManager.persist(order);
            }

            entityManager.flush();
            entityManager.clear();

            return findFirstOrderId();
        });
    }
}
```

Customer, PurchaseOrder constructors và findFirstOrderId() là phần fixture helper giả định. Trong code thực tế, cần tránh truy vấn lấy ID đầu tiên bằng cách lưu ID được sinh ra trong danh sách trước khi clear hoặc query lại sau khi commit.

### 8.1. Tại sao cần clear?

EntityManager.clear() detach tất cả entities trong persistence context hiện tại. Khi measured operation chạy trong persistence context mới, Hibernate không thể tái sử dụng các managed objects vừa được seed.

Nếu test method đang nằm trong một transaction khác, cần đảm bảo context đo thực sự mới; clear ở một context không làm clear context của transaction/service khác.

### 8.2. Evict second-level cache khi cần cold-cache test

```java
entityManagerFactory.getCache().evictAll();
```

Thao tác này evict entity/collection cache regions qua JPA Cache API ở phạm vi persistence unit. Query cache là cơ chế riêng và có API Hibernate-specific để evict query regions. Cần cân nhắc test chạy song song vì evict cache toàn cục có thể ảnh hưởng test khác.

Đơn giản hơn, có thể tắt L2 cache trong test profile nếu mục tiêu là đo fetch plan không phụ thuộc cache.

### 8.3. L1 và L2 có vai trò khác nhau

- **L1/persistence context:** cùng một EntityManager/Session; thường làm test bị reuse entity đã load.
- **L2 cache:** chia sẻ qua SessionFactory; có thể che secondary SELECT khi test chạy lần thứ hai.
- **Query cache:** cache kết quả query; có thể làm số SQL khác nhau giữa cold/warm run.

Test query plan nên có cold-context scenario; cache behavior có thể được test riêng.

## 9. Ví dụ test phát hiện N+1 ở to-one association

Giả sử service hiện tại tải orders rồi map Customer.name:

```java
@Service
public class OrderQueryService {

    private final PurchaseOrderRepository orders;

    public OrderQueryService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public List<OrderRowDto> list() {
        return orders.findAllByOrderByIdAsc().stream()
            .map(order -> new OrderRowDto(
                order.getId(),
                order.getCustomer().getName()
            ))
            .toList();
    }
}
```

DTO:

```java
public record OrderRowDto(Long id, String customerName) {}
```

Test bằng Hibernate Statistics:

```java
@SpringBootTest(properties = {
    "spring.jpa.open-in-view=false",
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class OrderQueryCountIT {

    @Autowired
    private OrderQueryService service;

    @Autowired
    private EntityManagerFactory emf;

    @Test
    void listShouldNotIssueOneCustomerQueryPerOrder() {
        seedOrdersWithDistinctCustomers(50);

        Statistics stats = emf.unwrap(SessionFactory.class)
            .getStatistics();

        stats.clear();

        List<OrderRowDto> result = service.list();

        long statements = stats.getPrepareStatementCount();

        assertThat(result).hasSize(50);
        assertThat(statements).isLessThanOrEqualTo(2);
    }
}
```

Ngưỡng 2 là kỳ vọng cho query gốc và một lần fetch bổ sung trong một mapping cụ thể; nếu repository, filters hoặc count logic phát thêm query hợp lệ, phải điều chỉnh budget theo thiết kế. Khi test ban đầu còn N+1, số statement có thể gần 51 và assertion sẽ fail.

### 9.1. Sửa bằng JOIN FETCH

Repository:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    order by o.id
    """)
List<PurchaseOrder> findAllWithCustomer();
```

Sau đó service dùng method này. Test giữ nguyên fixture và assertion query budget. Test xác nhận hành vi ở cấp use case, không gắn với một cách triển khai cụ thể.

### 9.2. Sửa bằng DTO projection

Nếu list chỉ cần ID và tên khách hàng, query có thể trả DTO trực tiếp:

```java
@Query("""
    select new com.example.orders.api.OrderRowDto(
        o.id, c.name
    )
    from PurchaseOrder o
    join o.customer c
    order by o.id
    """)
List<OrderRowDto> findRows();
```

Projection có thể chỉ cần một SELECT, đồng thời không hydrate entities/proxies. Query-count test giúp bảo vệ use case khi ai đó vô tình đổi repository sang entity loading và mapper lazy.

## 10. Ví dụ test N+1 ở to-many collection

Service:

```java
@Transactional(readOnly = true)
public List<OrderLineCountDto> lineCounts() {
    return orders.findAllByOrderByIdAsc().stream()
        .map(order -> new OrderLineCountDto(
            order.getId(),
            order.getLines().size()
        ))
        .toList();
}
```

Nếu mỗi collection chưa được load, SQL có thể là một query orders cộng một query collection cho mỗi order.

### 10.1. Fixture

Tạo 20 orders, mỗi order có ít nhất một line. Nếu chỉ có 3 orders có lines, code có thể tạo query khác nhau tùy cách collection được khởi tạo.

### 10.2. Test

```java
@Test
void collectionAccessShouldNotGrowLinearly() {
    seedOrdersWithLines(20, 3);

    Statistics stats = sessionFactory.getStatistics();
    stats.clear();

    List<OrderLineCountDto> result = service.lineCounts();

    long statements = stats.getPrepareStatementCount();

    assertThat(result).hasSize(20);
    assertThat(result).allMatch(row -> row.lineCount() == 3);
    assertThat(statements).isLessThanOrEqualTo(3);
}
```

Budget 3 có thể phù hợp nếu dùng root query cộng batch/collection query. Với fetch plan khác, xác định ngưỡng dựa trên SQL thực tế.

### 10.3. Sửa bằng batch fetching

Mapping:

```java
@OneToMany(mappedBy = "order")
@BatchSize(size = 16)
private List<OrderLine> lines = new ArrayList<>();
```

Với 20 owners và batch size 16, Hibernate có thể tải collection theo hai nhóm thay vì 20 truy vấn riêng, tùy access pattern và provider state. Query count test nên dùng ngưỡng phù hợp với số batch dự kiến, không giả định mọi phiên bản đều phát chính xác cùng số statements.

## 11. Phát hiện N+1 lồng nhau: Order → Lines → Product

Một query tải Orders, sau đó tải collection Lines theo từng Order, rồi tải Product theo từng Line có thể tạo nhiều tầng N+1.

### 11.1. Test data phải tránh target reuse vô tình

Nếu 100 lines cùng tham chiếu một Product, L1 cache có thể làm số Product loads thấp. Để phát hiện worst-case, tạo Product riêng cho mỗi line. Một test khác có thể kiểm tra trường hợp nhiều lines chia sẻ Product.

### 11.2. Test output và query count

```java
@Test
void orderDetailsShouldLoadLinesAndProductsInBoundedQueries() {
    Long orderId = seedOneOrderWithLinesAndDistinctProducts(40);

    Statistics stats = sessionFactory.getStatistics();
    stats.clear();

    OrderDetailDto dto = service.getDetail(orderId);

    long statements = stats.getPrepareStatementCount();

    assertThat(dto.lines()).hasSize(40);
    assertThat(dto.lines())
        .allMatch(line -> line.productName() != null);
    assertThat(statements).isLessThanOrEqualTo(3);
}
```

Trong implementation có query header + customer và query lines + product, thường có hai SELECT chính. Budget 3 có thể chừa overhead có chủ đích của filters; không nên để ngưỡng rộng đến mức che N+1.

### 11.3. Query count không tăng theo số lines

Chạy test cùng logic với 5, 20 và 100 lines. Nếu query count tăng từ 2 lên 21 rồi 101, có dấu hiệu Product đang được tải theo từng line. Nếu giữ gần 2 statements nhưng result rows tăng theo lines, đó là tăng dữ liệu tự nhiên của use case.

## 12. Kiểm thử theo cardinality: 1, 10, 100

Một assertion tuyệt đối đôi khi dễ bị ảnh hưởng bởi count query, sequence lookup, filters hoặc phiên bản Hibernate. Kiểm thử **độ tăng theo cardinality** giúp phát hiện xu hướng N+1.

| Số orders | Fetch plan tốt | N+1 to-one điển hình |
|---:|---:|---:|
| 1 | 1–2 statements | 2 |
| 10 | 1–2 statements | 11 |
| 100 | 1–2 statements | 101 |

### 12.1. Cách so sánh

1. Seed 1 order với customer riêng, reset counters, chạy use case, ghi count.
2. Seed 10 orders với 10 customers riêng, reset counters, chạy lại.
3. Seed 100 orders với 100 customers riêng, reset counters, chạy lại.
4. So sánh count và output.
5. Nếu có batch fetching, kỳ vọng count tăng theo số batches, ví dụ ceil(N / batchSize), chứ không theo N.

### 12.2. Đừng yêu cầu mọi count phải bằng nhau

Với batch fetching, số queries có thể tăng theo số batch. Với Page, count query có thể được gọi ở page size khác nhau. Với empty result, Hibernate có thể chỉ phát một query hoặc không chạy query phụ.

Điều cần bắt là **tăng tuyến tính không có chủ đích**. Có thể đặt upper bound theo batch size hoặc so chênh lệch giữa hai cardinalities.

### 12.3. Ví dụ assertion theo growth

Pseudocode:

```java
long countFor10 = measureListOperation(10);
long countFor100 = measureListOperation(100);

assertThat(countFor100 - countFor10)
    .isLessThanOrEqualTo(4);
```

Đây là ví dụ cho fetch plan kỳ vọng số query gần cố định. Nếu batch size 32, chênh lệch có thể tăng thêm vài batches và ngưỡng phải phản ánh thiết kế. Không copy con số 4 nếu query plan thực tế có count/child queries khác.

## 13. Dùng datasource-proxy để đếm JDBC statements

Hibernate Statistics tiện nhưng là counters toàn SessionFactory. Khi muốn đếm statements gần JDBC execution và phân loại SELECT/DML, có thể dùng datasource-proxy hoặc công cụ tương đương.

### 13.1. Khái niệm QueryCountHolder

Một số phiên bản datasource-proxy cung cấp `QueryCountHolder` và `QueryCount` để lấy counts:

```java
QueryCountHolder.clear();

OrderDetailDto dto = service.getDetail(orderId);

QueryCount count = QueryCountHolder.getGrandTotal();

long selects = count.getSelect();
long inserts = count.getInsert();
long updates = count.getUpdate();
long deletes = count.getDelete();
```

Các imports/API cụ thể phụ thuộc datasource-proxy version và cách cấu hình. Đoạn code minh họa giả định DataSource mà Spring Boot dùng đã được wrap bởi proxy có query-count listener.

### 13.2. Cấu hình proxy đúng DataSource

Chỉ thêm dependency không có nghĩa mọi query tự được đếm. Cần bảo đảm:

- EntityManagerFactory nhận DataSource đã được wrap.
- Spring transaction manager và Hibernate dùng cùng DataSource đó.
- Không có một DataSource thứ hai bypass proxy.
- Listener không log parameter values.
- Test collector được reset ở đúng thread/context.
- Async work được tính riêng hoặc có context propagation rõ.

### 13.3. Count theo operation/thread

Một request đồng bộ thường chạy trên một thread; thread-local query count có thể hữu ích. Với @Async, scheduler, reactive pipelines hoặc executor pools, query work có thể chạy ở thread khác và không tự cộng vào cùng counter. Dùng trace/request-scoped listener hoặc explicit test context propagation nếu cần đo toàn operation.

### 13.4. QueryCountHolder không phải API Hibernate

Đừng import QueryCountHolder từ Hibernate. Đây là API của thư viện datasource-proxy. Pin phiên bản và tham khảo tài liệu chính thức của thư viện trước khi copy code vào dự án.

### 13.5. Đếm batch riêng

Một batch có 50 INSERT entries có thể được proxy báo theo số query entries, số batch executions hoặc cả hai tùy listener. Khi test write path, xác định bạn muốn đo:

- Số loại SQL statements.
- Số parameter sets.
- Số executeBatch calls.
- Số rows bị tác động.

Không so batch count với Hibernate prepared statement count như thể chúng là cùng metric.

## 14. Tách SELECT khỏi DML theo từng thao tác

Một use case tạo đơn hàng có thể hợp lý khi thực hiện:

- SELECT để kiểm tra Customer.
- SELECT tải Product IDs hoặc tồn kho.
- INSERT Order.
- INSERT OrderLines.
- UPDATE inventory hoặc các bảng liên quan.

Nếu chỉ assert tổng prepared statement count, khó biết regression là do thêm một SELECT N+1 hay do số INSERT tăng theo số child entities như mong đợi.

| Loại | Ví dụ | Câu hỏi kiểm thử |
|---|---|---|
| SELECT | Load Customer/Product | Có N+1 không? |
| INSERT | Tạo Order/Lines | Có batching? Có insert thừa? |
| UPDATE | Dirty checking/version | Có update lặp không? |
| DELETE | Xóa vật lý/cascade | Có thao tác ngoài dự kiến? |
| BATCH | executeBatch | Có gom DML đúng không? |

### 14.1. Query budget cho write operation

Ví dụ tạo Order có 5 lines:

- 1 SELECT kiểm tra Customer.
- 1 SELECT tải Products hoặc inventory, tùy query design.
- 1 INSERT Order.
- N INSERT lines, có thể được batch.
- Các UPDATE inventory theo domain.

Không nên đặt “tối đa 3 SQL statements” cho thao tác này nếu domain bắt buộc ghi 5 lines. Hãy kiểm tra riêng SELECT budget và batching behavior.

### 14.2. Flush có thể phát DML ở cuối transaction

Hibernate dirty checking thường flush trước commit hoặc khi query cần auto-flush. Nếu đo counters trước khi transaction kết thúc, có thể bỏ sót DML cuối cùng. Gọi service qua proxy và đo sau khi transaction method hoàn tất, hoặc flush rõ ràng khi test repository-level unit of work.

## 15. Kiểm thử DTO projection để tránh entity loading không cần thiết

Một trang list chỉ cần order ID, number, customer name và count lines. DTO:

```java
public record OrderSummaryDto(
    Long id,
    String orderNumber,
    String customerName,
    long lineCount
) {}
```

JPQL:

```java
@Query("""
    select new com.example.orders.api.OrderSummaryDto(
        o.id,
        o.orderNumber,
        c.name,
        count(l.id)
    )
    from PurchaseOrder o
    join o.customer c
    left join o.lines l
    group by o.id, o.orderNumber, c.name
    order by o.id
    """)
List<OrderSummaryDto> findSummaries();
```

Test có thể xác nhận:

- Kết quả có đúng số rows.
- Mỗi DTO có customer name và count đúng.
- Query executions/statement count nằm trong budget.
- Entity load count thấp hoặc không tăng đáng kể so với entity-based implementation (tùy provider/projection).
- Không phát query phụ khi serialize DTO.

### 15.1. Projection không có nghĩa mọi query chỉ có một SQL

Page projection có thể có data query và count query. Query có filters/joins hoặc provider behavior khác có thể phát thêm statements. Test theo use case thực tế, không áp “một SELECT” một cách máy móc.

### 15.2. Test count query đúng

Nếu page query dùng GROUP BY, HAVING hoặc filter theo child association, count query phải đếm đúng root groups. Một query count ít SQL nhưng sai totalElements vẫn là bug.

## 16. Kiểm thử JOIN FETCH và EntityGraph

### 16.1. JOIN FETCH

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithCustomer(@Param("id") Long id);
```

Test đo:

```java
@Test
void detailFetchesCustomerWithoutSecondarySelect() {
    Long id = seedOrderWithCustomer();

    stats.clear();

    OrderDetailDto dto = service.getDetail(id);

    assertThat(dto.customerName()).isNotBlank();
    assertThat(stats.getPrepareStatementCount())
        .isLessThanOrEqualTo(2);
}
```

### 16.2. EntityGraph

```java
@EntityGraph(attributePaths = {"customer"})
Optional<PurchaseOrder> findDetailById(Long id);
```

Cùng test use case có thể dùng để bảo vệ query budget. Không assert generated SQL phải có đúng một JOIN cụ thể trừ khi đó là contract kỹ thuật chủ ý; provider có thể dùng secondary selects mà vẫn đạt budget.

### 16.3. Đo cả số rows và query count

EntityGraph chứa to-many có thể giảm statement count nhưng tạo row multiplication. Nếu performance critical, thêm datasource/database instrumentation để xem rows returned, query plan hoặc response timing.

## 17. Kiểm thử batch fetching

Mapping:

```java
@Entity
@BatchSize(size = 32)
public class Customer {
    @Id
    private Long id;
    private String name;
}
```

Hoặc cấu hình:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Test fixture 100 orders với 100 customers riêng:

1. Query orders.
2. Truy cập customer name của mỗi order trong cùng Session.
3. Đếm SELECT statements.
4. So sánh batch size 1 và 32.
5. Xác nhận số truy vấn giảm gần theo số batch.

Không assert chính xác ceil(100/32) nếu có additional query, IDs đã được load, cache, dialect bind limit hoặc Hibernate version behavior khác. Dùng upper bound có lý do và kiểm tra generated SQL trong local synthetic test khi cần.

### 17.1. Batch fetch không phải JDBC DML batching

`hibernate.default_batch_fetch_size` tối ưu **đọc lazy associations**. `hibernate.jdbc.batch_size` gom INSERT/UPDATE/DELETE. Hai cấu hình có tên gần giống nhưng mục đích khác nhau.

## 18. Kiểm thử FetchMode.SUBSELECT

```java
@OneToMany(mappedBy = "order")
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines;
```

Test:

- Tải một tập Orders theo cùng query.
- Truy cập collection của một Order.
- Đo số statements.
- Kiểm tra những collections được khởi tạo và tổng số OrderLines đã load.
- So với @BatchSize và query bulk children.

SUBSELECT có thể tải collections cho nhiều owners trong tập query ban đầu, kể cả khi code chỉ truy cập một phần. Vì vậy không chỉ assert statement count; hãy xác nhận lượng dữ liệu hydrate không vượt nhu cầu use case.

## 19. Pagination: kiểm thử N+1 và in-memory pagination

Một query:

```java
@Query("""
    select o from PurchaseOrder o
    left join fetch o.lines
    order by o.createdAt desc
    """)
Page<PurchaseOrder> findPageWithLines(Pageable pageable);
```

có nguy cơ phân trang trên joined rows thay vì root orders. Có thể tạo một SELECT nhưng trả quá nhiều rows hoặc Hibernate phải phân trang trong memory.

### 19.1. Fail sớm

Trong Hibernate 6, có thể bật:

```properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Cấu hình này giúp fail khi phát hiện pagination trên query có collection fetch trong những trường hợp Hibernate hỗ trợ phát hiện, thay vì âm thầm thực hiện in-memory pagination.

### 19.2. Kiểm thử chiến lược hai pha

- Pha 1: Page<Long> IDs theo thứ tự ổn định.
- Pha 2: tải headers/customer cho tập IDs.
- Pha 3: tải lines/product cho tập IDs.
- Group child DTO và trả theo thứ tự IDs.

Query count có thể là một số nhỏ cố định theo page, không tăng theo số parent. Đồng thời assert page content đủ số parent, child collections đầy đủ và thứ tự đúng.

### 19.3. Trang rỗng và tập IDs rỗng

Nếu page IDs rỗng, service phải trả page rỗng mà không gọi query IN với collection rỗng. Test riêng trường hợp page cuối hoặc filter không có kết quả.

### 19.4. Count query và dữ liệu đồng thời

Page query, count query và các query pha 2 có thể quan sát dữ liệu ở các thời điểm khác nhau tùy transaction isolation. Query-count test không chứng minh snapshot consistency; cần test riêng nếu use case đòi hỏi.

## 20. Kiểm thử OSIV và serialization

N+1 đôi khi chỉ xuất hiện khi JSON serializer truy cập entity associations.

### 20.1. Tắt OSIV trong integration test

```properties
spring.jpa.open-in-view=false
```

Gọi HTTP endpoint bằng MockMvc hoặc WebTestClient (tùy stack). Test method không nên giữ một transaction ngoài bao trùm request nếu mục tiêu là mô phỏng request thật.

### 20.2. Đo query count toàn request

Nếu dùng JDBC proxy với request-scoped listener, đo từ lúc request bắt đầu đến khi response serialization hoàn tất. Nếu dùng Hibernate Statistics toàn SessionFactory, cô lập test để không có request khác làm nhiễu.

### 20.3. Xác nhận DTO không kích hoạt SQL sau service

Service trả OrderDetailDto đã materialize; JSON serializer chỉ đọc fields DTO. Có thể chụp query count sau service và sau serialize, xác nhận serialize không làm count tăng.

### 20.4. Không để OSIV che lỗi

Nếu OSIV bật, endpoint có thể không ném LazyInitializationException nhưng vẫn phát N+1 ở controller/serializer. Một test chỉ kiểm tra HTTP 200 không đủ.

## 21. Test query count theo từng thao tác ghi

N+1 không chỉ có ở SELECT. Cascade, validation và lazy association trong write service cũng có thể phát nhiều queries.

### 21.1. Create operation

Một service tạo Order và nhiều OrderLines có thể cần:

- Load Customer.
- Load Products hoặc kiểm tra inventory.
- Insert Order.
- Insert Lines.
- Update inventory.

Đo SELECT riêng và DML riêng. Số INSERT tăng theo số lines là bình thường; N+1 SELECT tải từng Product có thể không.

### 21.2. Update operation

Ví dụ cập nhật status cho một Order:

- SELECT Order.
- Có thể SELECT association để validate transition.
- UPDATE Order với version.
- Có thể UPDATE audit/outbox rows.

Test cần assert status và version đúng, đồng thời kiểm tra query budget. Đừng ép một query nếu business cần validation từ database.

### 21.3. Delete operation

Nếu xóa entity có cascade, Hibernate có thể load collections hoặc phát nhiều DELETE/UPDATE statements. Với soft delete, query path và DML khác physical delete. Test phải đo đúng policy đã chọn và kiểm tra child rows.

### 21.4. Flush và commit

Với method @Transactional được gọi qua Spring proxy, SQL cuối cùng có thể phát ở commit trước khi caller nhận kết quả. Test đo sau khi service method trả về thường bao gồm flush/commit của transaction riêng. Nếu có outer test transaction, không còn đúng boundary đó.

## 22. Tránh test sai vì cache và persistence context

### 22.1. L1 cache làm giảm số queries

Trong cùng Session, cùng entity ID chỉ có một managed instance. Nếu fixture load Customer trước khi đo, mapper không phát SELECT thêm. Reset Statistics không xóa persistence context.

Cần EntityManager mới hoặc clear đúng context trước operation.

### 22.2. L2 cache làm giảm secondary selects

Nếu Customer đã cache, lazy proxy có thể được khởi tạo từ L2 mà không có SQL. Test có thể pass query budget dù fetch plan chưa được cải thiện.

Tắt L2 trong test query-plan hoặc evict regions trước từng run.

### 22.3. Query cache che SELECT

Nếu query cache được bật và result đã cached, query có thể không phát SQL như cold run. Kiểm tra cache hit/miss và tách cold/warm scenarios.

### 22.4. Không xóa cache toàn cục trong test song song

Cache.evictAll() và Statistics.clear() tác động toàn persistence unit/SessionFactory. Nếu tests chạy song song, chúng có thể làm test khác sai số. Tắt parallelism cho suite đo global counters hoặc dùng JDBC listener có scope riêng.

## 23. Thiết kế assertion không brittle

Một test query-count tốt phải bắt hồi quy nhưng không fail chỉ vì Hibernate đổi cách triển khai nội bộ không ảnh hưởng use case.

### 23.1. Ưu tiên upper bound có lý do

Tốt:

```java
assertThat(statementCount).isLessThanOrEqualTo(3);
```

khi có lý do rõ: 1 query header, 1 query lines và có thể 1 count/filter query.

Kém:

```java
assertThat(statementCount).isEqualTo(2);
```

nếu hệ thống có filters, interceptors hoặc count query hợp lệ và số 2 chỉ là chi tiết tình cờ của phiên bản hiện tại.

Tuy nhiên upper bound không được quá rộng. Nếu N+1 tạo 101 statements mà ngưỡng 150, test không bảo vệ được gì.

### 23.2. Assert tăng trưởng theo cardinality

Một fetch plan cố định có thể dùng 2–3 queries cho 10 hoặc 100 records. Batch fetch có thể tăng theo số batches. Test nên phản ánh complexity dự kiến:

- Constant: count(100) <= count(10) + smallAllowance.
- Batched: count(N) không vượt root queries + ceil(N/batchSize) + allowance.
- Per-parent: tăng gần N, thường là regression nếu không chủ ý.

### 23.3. Tách budget theo loại SQL

Ví dụ:
- SELECT <= 3.
- INSERT <= số entity được tạo (hoặc batch entries).
- UPDATE <= số aggregate transitions.
- DELETE <= số child rows theo policy.

Điều này giúp test failure chỉ rõ loại truy vấn tăng bất thường.

### 23.4. Không assert SQL string toàn bộ nếu không cần

SQL alias, whitespace, column order, dialect và Hibernate version có thể đổi. Query-count test nên assert behavior/metrics. Chỉ assert SQL shape cụ thể khi đó là contract quan trọng (ví dụ không được có pagination over collection fetch, có tenant predicate hoặc có index-friendly condition), và viết assertion đủ bền với alias/formatting.

### 23.5. Không bỏ qua output correctness

Một fetch plan có thể giảm query count bằng cách bỏ association hoặc filter sai. Luôn assert DTO fields, collection sizes, ordering, totals và authorization cùng với query budget.

## 24. Kiểm thử song song và tính cô lập

Hibernate Statistics là global theo SessionFactory. Nếu JUnit chạy hai tests đồng thời:

- Test A gọi stats.clear().
- Test B đang đo use case.
- Test A đọc counters trước khi B hoàn tất.

Kết quả không còn thuộc riêng test nào.

Các lựa chọn:

1. Chạy query-count suite tuần tự.
2. Dùng một application context/SessionFactory riêng cho test class cần đo.
3. Dùng datasource-proxy với request/test scoped listener.
4. Tạo fixture và đo trong test process riêng.
5. Tránh reset global counters trong khi traffic khác đang chạy.

Không dùng @DirtiesContext cho mọi test chỉ để reset statistics nếu chi phí khởi động Spring context quá lớn; hãy thiết kế instrumentation scope tốt hơn.

## 25. Kiểm thử bằng Testcontainers và database gần production

H2 hữu ích cho test nhanh nhưng có thể khác production database về:

- SQL dialect và syntax.
- Pagination/limit behavior.
- JDBC driver batching.
- Type mapping, UUID, JSON, timestamp.
- Query planner và index usage.
- Constraint/locking/isolation.
- Generated SQL và execution plans.

Với query-count tests, H2 có thể đủ để phát hiện N+1 cơ bản, nhưng performance-sensitive fetch plan nên có integration tests bằng Testcontainers hoặc database engine/version tương thích production.

### 25.1. Count tests không thay benchmark

Testcontainers giúp xác nhận hành vi với DB thật, nhưng không tự tạo workload/latency production. Benchmark cần dữ liệu có cardinality/selectivity thực tế, concurrency, warm/cold cache và network conditions phù hợp.

### 25.2. Cân nhắc dữ liệu fixture

Dùng dataset synthetic có số lượng và quan hệ rõ. Không cần copy PII production để test N+1. Dữ liệu giả phải đủ đa dạng để tránh L1/L2 reuse che truy vấn.

## 26. Đưa query budget vào CI

Một chiến lược thực tế:

- Unit tests: logic mapper/domain, không đo SQL.
- Repository integration tests: xác nhận query semantics, projections và fetch plans.
- Service integration tests: đo query count theo use case.
- API integration tests: kiểm tra serialization với OSIV off.
- Performance tests: đo latency/rows/throughput trên DB gần production.
- CI: chạy query-count suite ổn định, tuần tự hoặc với instrumentation cô lập.

### 26.1. Đặt budget gần use case

| Use case | Fixture | Budget minh họa |
|---|---|---|
| Order list DTO | 100 orders | Data + count query <= 2 |
| Order detail | 1 order, 100 lines | <= 3 SELECT |
| Order page with lines | 20 orders | Root page + headers + lines + count <= 4 |
| Customer list | 100 customers | <= 2 SELECT |
| Create order | 1 order, 5 lines | SELECT budget riêng; DML/batch theo 5 lines |
| Update order status | 1 order | <= 3 SELECT, <= 2 UPDATE |

Các con số là ví dụ. Budget thực tế cần dựa trên fetch plan, count query, filters, interceptors và database dialect.

### 26.2. Failure message phải hữu ích

Khi test fail, in:

- Operation/query key.
- Expected upper bound.
- Actual SELECT/DML/statement count.
- Cardinality fixture.
- Hibernate version/test profile.
- Có bật L2/query cache không.

Không in raw bind values hoặc entity data vào test failure. Nếu cần SQL text, chỉ thu trên fixture synthetic.

### 26.3. Khi thêm field vào DTO

Một thay đổi như thêm customer.address.city có thể làm mapper truy cập thêm lazy association. Query-count test của endpoint phải chạy lại và bắt hồi quy. Vì vậy test budget nên gắn với use case, không chỉ với repository method.

## 27. Quy trình điều tra khi query-count test fail

1. Xác định operation nào vượt budget.
2. Xem số SELECT, INSERT, UPDATE, DELETE riêng.
3. Kiểm tra test có outer transaction hoặc cache warm không.
4. Xác nhận fixture có đủ distinct associations và cardinality.
5. Bật SQL DEBUG trên dữ liệu synthetic trong test cô lập.
6. Nhóm SQL theo shape: query root, query collection, query to-one.
7. Xác định mapper/getter/serializer nào kích hoạt lazy loading.
8. Chọn fetch plan: DTO projection, JOIN FETCH, EntityGraph, batch hoặc query hai pha.
9. Chạy lại ở cardinality nhỏ/lớn.
10. Kiểm tra rows returned, ordering, count, authorization và response correctness.
11. Tắt debug verbosity và giữ lại regression test.
12. Nếu query count ổn nhưng latency vẫn cao, xem execution plan, index, locks và connection pool.

### 27.1. Không sửa bằng cách tăng budget vô điều kiện

Nếu test báo 51 statements, đổi ngưỡng từ 5 lên 60 chỉ làm mất tín hiệu. Hãy xác định mỗi query phụ có chủ đích không. Nếu là N+1, sửa fetch plan; nếu là một query bắt buộc theo batch, ghi rõ rationale và test complexity.

### 27.2. Không sửa bằng cách bật EAGER mọi quan hệ

EAGER có thể chuyển N+1 sang secondary selects hoặc tải dư dữ liệu. Query-count test có thể vẫn fail, hoặc pass nhưng result rows/memory tăng. Thiết kế theo use case thay vì đổi toàn cục.

## 28. Ví dụ helper đo Hibernate Statistics

Có thể tạo một helper test nhỏ:

```java
public final class HibernateQueryCounter {

    private final Statistics statistics;

    public HibernateQueryCounter(EntityManagerFactory emf) {
        this.statistics = emf
            .unwrap(SessionFactory.class)
            .getStatistics();
        this.statistics.setStatisticsEnabled(true);
    }

    public void reset() {
        statistics.clear();
    }

    public Snapshot snapshot() {
        return new Snapshot(
            statistics.getPrepareStatementCount(),
            statistics.getQueryExecutionCount(),
            statistics.getEntityLoadCount(),
            statistics.getEntityFetchCount(),
            statistics.getCollectionLoadCount(),
            statistics.getCollectionFetchCount()
        );
    }

    public record Snapshot(
        long preparedStatements,
        long queryExecutions,
        long entityLoads,
        long entityFetches,
        long collectionLoads,
        long collectionFetches
    ) {}
}
```

Sử dụng:

```java
counter.reset();

OrderDetailDto dto = service.getDetail(orderId);

HibernateQueryCounter.Snapshot snapshot = counter.snapshot();

assertThat(snapshot.preparedStatements())
    .isLessThanOrEqualTo(3);
assertThat(snapshot.collectionFetches())
    .isLessThanOrEqualTo(1);
```

Helper này không thread-safe theo từng test vì counters global. Dùng trong suite tuần tự hoặc đổi sang JDBC-scoped instrumentation nếu cần parallel tests.

## 29. Ví dụ helper đo datasource-proxy theo query categories

Một số phiên bản datasource-proxy có thể dùng QueryCountHolder:

```java
QueryCountHolder.clear();

OrderDetailDto dto = service.getDetail(orderId);

QueryCount count = QueryCountHolder.getGrandTotal();

assertThat(count.getSelect()).isLessThanOrEqualTo(3);
assertThat(count.getInsert()).isZero();
assertThat(count.getUpdate()).isZero();
assertThat(count.getDelete()).isZero();
```

Đoạn code giả định:

- DataSource của Spring đã được wrap bởi datasource-proxy.
- Query count listener đã được đăng ký.
- Test chạy trong scope mà QueryCountHolder sử dụng.
- Không có query phụ từ test framework chen vào cùng scope.
- Các API methods khớp với version thư viện.

Không gọi QueryCountHolder.clear() trong production traffic dùng chung nếu nó reset counters global/thread-local mà một consumer khác đang đọc.

### 29.1. Chỉ đếm query categories có thể chưa đủ

Một operation có thể chạy 1 SELECT rất nặng. Ngoài counts, đo duration và rows nếu tooling hỗ trợ. Đừng ghi parameter values chỉ để phân loại query.

## 30. Những trường hợp đặc biệt cần test riêng

### 30.1. Empty result

Nếu không có Orders, mapper không chạm association. Query count thường thấp hơn. Test empty result để xác nhận output và không gọi query phụ không cần thiết.

### 30.2. Nullable to-one

Với left join fetch, Order không có Customer vẫn phải xuất hiện nếu business cho phép. Test null association và response shape.

### 30.3. Shared targets

Nhiều Orders cùng Customer có thể giảm SELECT nhờ L1 reuse. Test riêng để hiểu workload phổ biến, nhưng đừng chỉ dựa vào fixture này để bắt worst-case N+1.

### 30.4. Large collections

Một Order có 10.000 lines có thể chỉ cần 2 queries nhưng memory/time rất lớn. Cần test pagination/chunking của child collection và response limits.

### 30.5. Lazy basic fields/bytecode enhancement

Nếu dùng lazy basic attributes hoặc bytecode enhancement, truy cập field có thể kích hoạt secondary select. Query-count test theo use case cũng có thể phát hiện dạng fetch phụ này.

### 30.6. Inheritance và secondary tables

Entity inheritance, @SecondaryTable, formulas hoặc generated attributes có thể làm một entity load tạo nhiều SQL hơn. Budget phải hiểu mapping thực tế, không giả định mọi entity luôn là một row/one SELECT.

### 30.7. Stored procedures và native queries

Một stored procedure có thể thực hiện nhiều database statements bên trong nhưng JDBC proxy chỉ thấy một CALL. Query count ở ứng dụng không tương đương số statements nội bộ database; dùng DB-side telemetry khi cần.

### 30.8. Cache hits

Một lần chạy cache warm có thể không phát SQL cho entity/collection đã cache. Test cold-cache và warm-cache như hai kịch bản riêng, không để kết quả phụ thuộc thứ tự test.

## 31. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test luôn báo 0 statements | Statistics chưa bật hoặc lấy nhầm SessionFactory | Kiểm tra generate_statistics, unwrap EMF đúng |
| Query count bao gồm INSERT seed | Reset counters trước khi seed hoàn tất | Seed/commit trước, reset sau |
| Test không bắt được N+1 | Fixture dùng chung một target entity | Tạo distinct customers/products |
| Test pass lần đầu, fail lần sau | L2/query cache làm số đo khác | Tách cold/warm scenarios và evict/tắt cache |
| Statistics bị nhiễu | Tests chạy song song hoặc requests khác | Chạy tuần tự hoặc JDBC scoped listener |
| Đo thiếu UPDATE cuối transaction | Đọc counter trước flush/commit | Đo sau service proxy transaction hoặc flush rõ |
| @Transactional test che boundary | Service tham gia outer test transaction | Không outer transaction hoặc dùng TestTransaction |
| Statement count ít nhưng query chậm | Một JOIN/result set quá lớn | Đo rows, bytes, plan và latency |
| Batch count không bằng statement count | executeBatch và batch entries khác nhau | Định nghĩa metric riêng |
| Count query làm budget fail | Page cần count query | Đặt budget theo data + count, cân nhắc Slice |
| JSON endpoint có nhiều query | Serializer chạm lazy entity | DTO hoàn chỉnh, OSIV off |
| Batch fetching vẫn tăng query | Batch size nhỏ hoặc access pattern khác | Tính batches và kiểm tra SQL |
| DTO projection vẫn có 2 queries | Page count query | Điều chỉnh budget, dùng Slice khi không cần total |
| Test H2 pass nhưng PostgreSQL fail | Dialect/driver/pagination khác | Testcontainers với DB gần production |
| Test query count pass nhưng dữ liệu sai | Fetch plan lọc thiếu child hoặc join duplicate | Assert content, counts, ordering và semantics |
| Test phụ thuộc thứ tự chạy | Shared cache/global Statistics | Reset có cô lập hoặc context riêng |
| SQL DEBUG làm test chậm | Logging IO/formatting overhead | Tắt SQL logs trong suite bình thường |
| Bật bind TRACE để tìm N+1 | Nhầm query shape với parameter values | Dùng SQL DEBUG/statistics, synthetic data khi thật cần |
| Nâng ngưỡng làm test pass | Che regression thay vì sửa | Điều tra slope/query pattern |
| clear() không reset query cache | Hibernate Statistics khác cache regions | Reset/evict đúng loại cache, hoặc tắt trong test |

## 32. Bài tập thực hành

**Bài 1 — Đo baseline.** Bật Hibernate Statistics, seed 10 Orders và ghi prepareStatementCount, queryExecutionCount, entityLoadCount.

**Bài 2 — Tạo N+1 to-one.** Mỗi Order có một Customer khác nhau; map Customer.name sau khi load Orders. So count với 1, 10 và 100 Orders.

**Bài 3 — Sửa JOIN FETCH.** Thêm fetch join Customer, chạy lại cùng fixture và xác nhận query count không tăng tuyến tính.

**Bài 4 — Tạo N+1 collection.** Duyệt order.getLines() cho mỗi Order. Quan sát collection fetches và statements.

**Bài 5 — Batch fetching.** Đặt batch size 16, đo 100 owners. Giải thích số query theo batch thay vì theo từng owner.

**Bài 6 — Association lồng nhau.** Tạo Order → Lines → Product với Product riêng từng line. Đo từng tầng fetch.

**Bài 7 — DTO projection.** Tạo Page<OrderSummaryDto> với customer name và line count; test query budget và total count.

**Bài 8 — Pagination collection.** Bật fail_on_pagination_over_collection_fetch, viết test query page có fetch join lines và xác nhận fail; sửa bằng page IDs.

**Bài 9 — Two-phase loading.** Tải IDs, headers và children; test thứ tự page, đầy đủ children và số statements.

**Bài 10 — L1 cache.** Load Customer trong cùng EntityManager trước khi đo. Quan sát vì sao N+1 có thể bị che.

**Bài 11 — L2 cache.** Bật cache, chạy hai lần. Tách test cold cache và warm cache.

**Bài 12 — OSIV.** Tắt spring.jpa.open-in-view, gọi endpoint trả DTO. Xác nhận serializer không phát SQL sau service boundary.

**Bài 13 — Write operation.** Tạo Order có 10 lines, đo SELECT riêng với INSERT/batch entries.

**Bài 14 — JDBC proxy.** Wrap DataSource bằng datasource-proxy, đếm SELECT/INSERT/UPDATE/DELETE theo một test operation.

**Bài 15 — Parallel tests.** Chạy hai test cùng reset Statistics để quan sát contamination; sau đó tuần tự hóa suite hoặc dùng listener scoped.

**Bài 16 — Testcontainers.** Chạy query-count test trên database cùng loại/version gần production và so với H2.

**Bài 17 — Regression.** Thêm customer.address.city vào DTO, xác nhận test query budget bắt fetch mới nếu mapper gây N+1.

**Bài 18 — Query budget.** Viết tài liệu budget cho list, detail, create, update, delete; nêu rõ metric và rationale từng ngưỡng.

## 33. Câu hỏi tự kiểm tra

**1. Vì sao assert số DTO trả về không phát hiện N+1?**

Vì kết quả có thể đúng dù Hibernate phát nhiều truy vấn phụ khi mapper truy cập lazy associations.

**2. getPrepareStatementCount() có phải network round trips không?**

Không nhất thiết; đó là counter Hibernate cho prepared statements, cần phân biệt với JDBC executions và batch calls.

**3. Vì sao phải seed dữ liệu trước khi reset Statistics?**

Để INSERT/SELECT của fixture không bị tính vào operation đang đo.

**4. Vì sao fixture nên tạo distinct Customers/Products?**

Để L1 cache không tái sử dụng cùng entity và che lazy loads theo từng parent.

**5. Vì sao test method không nên có outer @Transactional khi đo service transaction commit?**

Service có thể tham gia transaction test và commit/flush thực tế xảy ra sau khi method trả về.

**6. Hibernate Statistics có scope theo request không?**

Không mặc định; counters thường ở cấp SessionFactory nên có thể bị nhiễu bởi hoạt động khác.

**7. Khi nào nên dùng datasource-proxy?**

Khi cần quan sát JDBC executions, phân loại DML/SELECT hoặc attribution theo thread/request tốt hơn.

**8. Batch fetching có làm query count luôn cố định không?**

Không; count có thể tăng theo số batches, nhưng không tăng một query cho mỗi entity.

**9. Một JOIN FETCH có thể vẫn chậm dù chỉ một statement không?**

Có; join nhiều collections có thể tạo Cartesian product và trả hàng nghìn rows lặp.

**10. Vì sao test query count cần assert nội dung DTO?**

Để tránh một fetch plan nhanh nhưng thiếu fields, thiếu child rows hoặc sai thứ tự.

**11. Vì sao OSIV nên tắt trong một số integration tests?**

Để phát hiện mapper/serializer đang phụ thuộc lazy access ngoài service transaction.

**12. Có nên bật bind TRACE để phát hiện N+1 không?**

Thường không; SQL shape và query counters đủ để phát hiện số truy vấn. Bind TRACE chỉ dùng với dữ liệu synthetic khi cần điều tra parameter binding.

**13. Query count test có thay performance benchmark không?**

Không; benchmark còn đo latency, throughput, rows, memory, locks và database plan.

**14. Vì sao Page DTO có thể phát hai SELECT dù không có N+1?**

Spring Data có thể chạy data query và count query để tính total elements.

**15. Vì sao Statistics.clear() nguy hiểm trong test chạy song song?**

Nó reset counters chung của SessionFactory, ảnh hưởng số đo test khác.

## 34. Ghi nhớ

- **Kiểm thử N+1 theo từng use case** bằng query budget, không chỉ assert kết quả trả về.
- Phân biệt Hibernate query executions, prepared statements, JDBC executions, batch executions và rows returned.
- Hibernate Statistics là cách nhanh để đo ORM counters; datasource-proxy/JDBC instrumentation hữu ích khi cần đếm executions và phân loại SQL.
- Seed và commit fixture trước, reset counters sau, gọi service qua Spring proxy rồi đọc counters đúng boundary.
- Tạo fixture 1/10/100 records với association targets riêng để làm lộ lazy N+1; test shared targets và cache riêng.
- Test to-one, to-many, nested associations, pagination, DTO projection và serialization.
- Batch fetching có thể làm query count tăng theo số batch; kiểm tra complexity thay vì ép mọi test bằng một con số.
- Collection fetch join có thể giảm statements nhưng tạo Cartesian product hoặc phân trang trong memory; đo cả rows và tính đúng đắn.
- Không để L1/L2/query cache, outer test transaction hoặc parallel tests che hay làm nhiễu kết quả.
- Với write operations, đo SELECT riêng với INSERT/UPDATE/DELETE và batch entries; flush/commit có thể phát SQL cuối cùng.
- Dùng upper bounds và growth assertions có rationale, đồng thời luôn kiểm tra dữ liệu, ordering, authorization và count query.
- Query-count tests là regression guard; performance tests và database execution plans vẫn cần cho các use cases quan trọng.

### Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — Statistics](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#statistics)
- [Hibernate ORM 6.6 JavaDoc — Statistics](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/stat/Statistics.html)
- [Hibernate ORM 6.6 JavaDoc — SessionFactory](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/SessionFactory.html)
- [Hibernate ORM 6.6 User Guide — Fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM 6.6 User Guide — Batch fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching-batch)
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Data JPA Reference — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [datasource-proxy documentation](https://github.com/jdbc-observations/datasource-proxy)
- [Testcontainers for Java](https://java.testcontainers.org/)

