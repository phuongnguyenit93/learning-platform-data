# Tránh khởi động lại context chỉ để dọn dữ liệu nghiệp vụ

Spring Test có thể tái sử dụng `ApplicationContext` giữa nhiều test class có cấu hình tương đương. Cơ chế cache này giúp giảm đáng kể thời gian chạy, đặc biệt với `@SpringBootTest` có nhiều bean, auto-configuration và kết nối hạ tầng. Tuy nhiên, sau một test, database hoặc cache có thể còn dữ liệu do test tạo ra. Khi gặp trạng thái còn sót, một cách xử lý dễ nghĩ tới là đánh dấu context bằng `@DirtiesContext` để Spring đóng context hiện tại và tạo context mới.

Đây thường là cách dọn dẹp quá rộng. `ApplicationContext` quản lý bean và cấu hình; dữ liệu nghiệp vụ nằm trong database, cache, message broker, filesystem hoặc dịch vụ ngoài. Đóng context không tự động xóa các dữ liệu đó. Nếu mục tiêu chỉ là đưa dữ liệu test về trạng thái ban đầu, hãy dọn đúng nguồn dữ liệu bằng transaction rollback, SQL script, repository hoặc API cleanup phù hợp. Dành `@DirtiesContext` cho trường hợp trạng thái của chính context hoặc bean dùng chung đã bị thay đổi và không thể khôi phục an toàn.

## 1. Phân biệt ApplicationContext cache với dữ liệu nghiệp vụ

Trong một test Spring có thể tồn tại nhiều lớp trạng thái khác nhau:

| Loại trạng thái | Ví dụ | Cách dọn thường phù hợp |
| --- | --- | --- |
| Spring `ApplicationContext` | Bean definition, singleton bean, cấu hình, proxy, listener | Giữ context nếu còn hợp lệ; dùng `@DirtiesContext` khi context thực sự bị thay đổi không thể phục hồi |
| Dữ liệu database | Customer, Order, Invoice, bản ghi audit | Transaction rollback, xóa theo ID test, SQL cleanup hoặc schema/database riêng |
| Cache ứng dụng | Giá trị trong Caffeine, Redis hoặc Spring Cache | Evict key hoặc xóa namespace test |
| Message và event đã gửi | Message trong queue/topic, event lưu bền vững | Dùng queue/topic riêng, consumer group riêng hoặc API purge dành cho môi trường test |
| Tệp và object storage | File export, ảnh, object trên bucket | Thư mục tạm, prefix riêng hoặc xóa đúng object do test tạo |
| Trạng thái dịch vụ ngoài | Bản ghi trên payment sandbox, webhook hoặc hệ thống giả lập | API reset/cleanup, ID duy nhất hoặc sandbox riêng |

Spring Test context cache giữ các `ApplicationContext` có cấu hình tương đương để test sau có thể dùng lại. Cache này không phải cache dữ liệu nghiệp vụ. Khi context được đóng, các bean và tài nguyên gắn với context được hủy theo lifecycle; database bên ngoài, Redis, broker hoặc dịch vụ khác vẫn giữ trạng thái của chúng trừ khi có cơ chế cleanup riêng.

Ví dụ, một test tạo đơn hàng trong PostgreSQL rồi gọi `@DirtiesContext` sau method. Spring có thể đóng context và xóa nó khỏi context cache, nhưng hàng `orders` vẫn tồn tại trong database. Test sau tải context mới nhưng vẫn nhìn thấy đơn hàng cũ. Vì vậy, context restart không giải quyết đúng nguyên nhân của dữ liệu còn sót.

## 2. Chi phí của việc đánh dấu context dirty

`@DirtiesContext` yêu cầu Spring Test đánh dấu `ApplicationContext` hiện tại là không còn dùng được và loại nó khỏi cache theo chế độ được chỉ định. Khi một test khác cần cùng cấu hình, Spring phải tải context mới.

Một context khởi động lại có thể kéo theo:

- Quét component, xử lý configuration class và tạo bean definition.
- Khởi tạo datasource, connection pool, ORM, security filter, HTTP client và các bean singleton.
- Chạy migration, khởi động server nhúng hoặc tạo kết nối tới broker nếu cấu hình yêu cầu.
- Khởi tạo lại cache nội bộ của bean và các tài nguyên gắn với context.
- Tăng thời gian chạy và mức tiêu thụ CPU, bộ nhớ, socket hoặc connection trong pipeline.

Nếu một test class đánh dấu dirty sau mỗi method, nhiều test class có thể liên tục tải lại cùng một context. Một bộ test vốn có thể tái sử dụng context sẽ trở nên chậm và khó dự đoán hơn.

Ví dụ:

```java
@SpringBootTest
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
class OrderServiceIntegrationTest {

    @Test
    void createsOrder() {
        // ...
    }

    @Test
    void cancelsOrder() {
        // ...
    }
}
```

Ở chế độ `AFTER_METHOD`, context bị đánh dấu dirty sau mỗi test method. Nếu hai test chỉ tạo hoặc xóa các bản ghi Order, việc tải lại toàn bộ context là quá tốn kém và không xử lý trực tiếp dữ liệu trong database.

## 3. Khi nào `@DirtiesContext` thực sự phù hợp?

`@DirtiesContext` phù hợp khi test làm thay đổi trạng thái của chính `ApplicationContext` khiến test sau không còn nhận được môi trường đáng tin cậy. Ví dụ:

- Một test thay đổi cấu hình hoặc bean singleton dùng chung theo cách không thể reset.
- Một bean giữ trạng thái toàn cục và không có API đưa nó về trạng thái ban đầu.
- Test thay đổi cấu trúc context hoặc đăng ký tài nguyên động mà lifecycle không thể khôi phục.
- Một kiểm thử cố ý xác nhận hành vi khi context bị thay đổi, đóng hoặc cần được tạo mới.

Ví dụ một bean singleton có cấu hình mutable chỉ phục vụ tình huống legacy:

```java
@Component
class RuntimeFeatureRegistry {

    private final Map<String, Boolean> flags = new ConcurrentHashMap<>();

    void replaceAll(Map<String, Boolean> newFlags) {
        flags.clear();
        flags.putAll(newFlags);
    }

    boolean isEnabled(String name) {
        return flags.getOrDefault(name, false);
    }
}
```

Nếu test thay đổi registry dùng chung và không có cách khôi phục trạng thái đáng tin cậy, có thể cần context mới. Nhưng nếu bean có phương thức reset rõ ràng hoặc trạng thái có thể được lưu và phục hồi, hãy reset bean trong fixture để tiếp tục tái sử dụng context.

Không dùng `@DirtiesContext` chỉ vì:

- Một test đã insert hoặc update dữ liệu trong database.
- Một cache key chứa giá trị do test tạo.
- Một message đã được gửi vào queue test.
- Một mock có invocation history hoặc stub cần reset.
- Một file test được tạo trong thư mục tạm.

Các loại trạng thái đó có cách cleanup trực tiếp và thường không đòi hỏi đóng context.

## 4. Dùng transaction rollback để cô lập dữ liệu database

Với test tích hợp chạy đồng bộ trong cùng transaction, `@Transactional` là một trong những cách đơn giản nhất để tránh dữ liệu rò rỉ giữa các test. Spring Test thường mở transaction trước method test và rollback sau khi method kết thúc.

```java
@SpringBootTest
@Transactional
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrder() {
        Order order = repository.save(new Order("customer-42"));

        assertTrue(repository.findById(order.getId()).isPresent());
    }
}
```

Thay đổi database nằm trong transaction kiểm thử sẽ được rollback theo mặc định. Context vẫn có thể được giữ trong cache cho test tiếp theo; dữ liệu trong transaction được hoàn tác mà không cần khởi tạo lại toàn bộ bean.

Có thể dùng `@Rollback` để làm rõ chính sách:

```java
@Test
@Rollback(true)
void createsTemporaryOrder() {
    // Các thay đổi được rollback sau test
}
```

Nếu cần commit có chủ đích, có thể dùng `@Commit` hoặc `@Rollback(false)`, nhưng hãy nhớ rằng dữ liệu đã commit cần cleanup riêng nếu test dùng chung database.

### Giới hạn của transaction test

Rollback chỉ bao phủ các thay đổi tham gia transaction được Spring quản lý. Nó không tự hoàn tác:

- HTTP request đã gửi tới dịch vụ thanh toán hoặc API bên ngoài.
- Email đã gửi, message đã publish hoặc message broker đã nhận.
- Ghi file, object storage hoặc thay đổi trên Redis nếu thao tác đó không tham gia cùng transaction.
- Code chạy ở thread khác như tác vụ `@Async` theo mặc định.
- Transaction độc lập được mở với propagation `REQUIRES_NEW` và đã commit.
- Thay đổi do một process hoặc test khác ghi vào database dùng chung.

Vì vậy, đừng giả định `@Transactional` bảo đảm toàn bộ nghiệp vụ được làm sạch. Hãy xác định mỗi side effect nằm trong hay ngoài transaction và chọn cleanup tương ứng.

## 5. Dọn dữ liệu theo ID hoặc khóa riêng của test

Khi không thể dùng rollback, hãy tạo dữ liệu có định danh riêng để test có thể xóa đúng phần mình sở hữu. Ví dụ, mỗi test dùng một customer ID hoặc correlation key duy nhất:

```java
@SpringBootTest
class OrderApiIntegrationTest {

    @Autowired
    OrderRepository orderRepository;

    private final String customerId = "test-customer-order-api";

    @BeforeEach
    void prepare() {
        orderRepository.deleteByCustomerId(customerId);
    }

    @AfterEach
    void cleanUp() {
        orderRepository.deleteByCustomerId(customerId);
    }

    @Test
    void createsOrderForCustomer() {
        // Gửi request tạo đơn cho customerId của test
    }
}
```

Xóa trước test giúp test không phụ thuộc vào dữ liệu còn lại từ lần chạy trước. Xóa sau test giữ môi trường sạch cho các test tiếp theo. Cleanup nên idempotent: gọi nhiều lần vẫn an toàn và không lỗi khi bản ghi đã không còn.

Trong hệ thống có quan hệ khóa ngoại, xóa theo thứ tự phụ thuộc. Ví dụ, xóa `order_items` trước `orders` nếu database không cascade theo cấu hình mong muốn. Có thể dùng một method cleanup trong repository hoặc một service test-support để gom các thao tác xóa đúng thứ tự.

Nếu test chạy song song, ID cố định như `test-customer-order-api` có thể bị hai lần chạy cùng sử dụng. Khi đó hãy tạo namespace duy nhất cho từng test invocation, chẳng hạn UUID hoặc test run ID, rồi truyền ID đó qua mọi bản ghi và request liên quan.

## 6. Dùng `@Sql` để chuẩn bị và dọn dữ liệu

`@Sql` cho phép chạy SQL script ở các giai đoạn của test. Đây là lựa chọn hữu ích khi dữ liệu cần chuẩn bị có nhiều bảng hoặc cần một fixture cụ thể.

```java
@SpringBootTest
@Sql(
    scripts = "/sql/orders/insert-test-orders.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/orders/delete-test-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class OrderSearchIntegrationTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsOrdersForTestCustomer() {
        assertFalse(repository.findByCustomerId("test-customer-89").isEmpty());
    }
}
```

Script chuẩn bị:

```sql
INSERT INTO customers (id, name)
VALUES ('test-customer-89', 'Test Customer');

INSERT INTO orders (id, customer_id, status)
VALUES ('test-order-89', 'test-customer-89', 'PENDING');
```

Script cleanup:

```sql
DELETE FROM order_items WHERE order_id = 'test-order-89';
DELETE FROM orders WHERE id = 'test-order-89';
DELETE FROM customers WHERE id = 'test-customer-89';
```

Các ID trong ví dụ cần được dành riêng cho test đó. Nếu có thể chạy song song hoặc nhiều worker cùng dùng database, hãy sinh ID riêng cho mỗi lần chạy hoặc dùng database/schema riêng.

### Transaction mode của `@Sql`

`@SqlConfig` cho phép điều chỉnh transaction mode. Ở chế độ suy luận mặc định, Spring cố gắng dùng transaction đang hoạt động nếu có, hoặc tạo transaction phù hợp khi cần. `ISOLATED` yêu cầu script chạy trong transaction riêng và commit độc lập.

Ví dụ cấu hình:

```java
@Sql(
    scripts = "/sql/cleanup-test-data.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
```

Chỉ dùng transaction độc lập khi cần thiết, vì nó có thể commit cleanup ngay cả khi transaction test được rollback. Hãy hiểu rõ thứ tự listener và transaction manager của dự án, nhất là khi script chuẩn bị và cleanup chạy trong các transaction khác nhau.

## 7. Dùng repository hoặc service test-support để cleanup

Nếu cleanup cần quy tắc nghiệp vụ hoặc xóa nhiều aggregate, có thể tạo một thành phần hỗ trợ test. Nó có thể dùng repository thật trong context tích hợp:

```java
@TestComponent
class OrderTestDataCleaner {

    private final OrderRepository orders;
    private final OrderItemRepository items;

    OrderTestDataCleaner(
            OrderRepository orders,
            OrderItemRepository items) {
        this.orders = orders;
        this.items = items;
    }

    @Transactional
    void deleteOrdersForCustomer(String customerId) {
        items.deleteByCustomerId(customerId);
        orders.deleteByCustomerId(customerId);
    }
}
```

Test có thể gọi cleaner trong `@BeforeEach` và `@AfterEach`:

```java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @Autowired
    OrderTestDataCleaner cleaner;

    @BeforeEach
    void cleanBefore() {
        cleaner.deleteOrdersForCustomer("test-customer-135");
    }

    @AfterEach
    void cleanAfter() {
        cleaner.deleteOrdersForCustomer("test-customer-135");
    }
}
```

`@TestComponent` là một stereotype dành cho thành phần hỗ trợ kiểm thử trong Spring Boot; nếu dự án không dùng Spring Boot, có thể đăng ký class này trong test configuration bằng `@Bean`. Hãy đặt cleaner trong test source set để nó không bị đóng gói nhầm vào ứng dụng production.

Nếu method cleanup được gọi trong một test transaction đã rollback, cần hiểu transaction propagation. Nếu cleanup phải commit độc lập để xóa dữ liệu tồn tại trước test, có thể cần transaction riêng hoặc script `ISOLATED`. Không nên chỉ thêm `@Transactional` mà không xác định transaction nào sẽ commit.

## 8. Dọn cache ứng dụng thay vì restart context

Spring Cache và cache nội bộ của bean là trạng thái ứng dụng. Nếu một test làm cache chứa dữ liệu cũ, hãy evict đúng key hoặc xóa vùng cache dành riêng cho test.

Ví dụ dùng `CacheManager`:

```java
@SpringBootTest
class ProductCacheIntegrationTest {

    @Autowired
    CacheManager cacheManager;

    @AfterEach
    void clearProductCache() {
        Cache cache = cacheManager.getCache("products");
        if (cache != null) {
            cache.clear();
        }
    }
}
```

Nếu chỉ cần xóa một key:

```java
cache.evict(productId);
```

Trong cache phân tán như Redis, hãy cân nhắc dùng prefix/namespace riêng cho test. Tránh xóa toàn bộ Redis dùng chung nếu có test khác hoặc dịch vụ khác đang sử dụng. Với test song song, mỗi test nên dùng key duy nhất hoặc cache riêng để cleanup không xóa dữ liệu của test khác.

Nếu cache là một field mutable trong singleton bean mà không có API reset, có thể bổ sung phương thức xóa/refresh có ý nghĩa nghiệp vụ hoặc thiết kế cache abstraction có thể kiểm soát. Chỉ dùng `@DirtiesContext` khi trạng thái bean không thể được phục hồi an toàn bằng cách đó.

## 9. Dọn message broker và event đã gửi

Transaction database rollback không xóa message đã được publish lên Kafka, RabbitMQ hoặc một broker khác. Nếu test dùng broker thật hoặc Testcontainers, hãy thiết kế vùng dữ liệu riêng:

- Dùng topic hoặc queue dành riêng cho test class hoặc test run.
- Dùng consumer group riêng để tránh offset của test khác ảnh hưởng.
- Đưa test run ID vào message key hoặc payload để tìm và xác nhận message của test.
- Xóa queue/topic hoặc purge message theo khả năng của broker trong môi trường test riêng.
- Chờ consumer xử lý bằng điều kiện có timeout, không dùng `Thread.sleep()` tùy ý.

Ví dụ về tên topic có namespace:

```java
String topic = "orders-test-" + testRunId;
```

Không purge một topic dùng chung trong khi các test khác đang chạy. Cleanup message phải giới hạn trong tài nguyên mà test sở hữu. Nếu test chỉ cần xác nhận use case phát event, unit test có thể mock outbound port; integration test riêng mới cần broker thật.

## 10. Dọn file và tài nguyên ngoài context

Bean có thể tạo file hoặc object trong storage. Đóng `ApplicationContext` không đồng nghĩa mọi file đã tạo được xóa.

Với filesystem, dùng thư mục tạm của JUnit:

```java
class ReportExportTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void exportsReportToTemporaryDirectory() throws IOException {
        Path output = temporaryDirectory.resolve("report.pdf");

        // Gọi exporter ghi vào output

        assertTrue(Files.exists(output));
    }
}
```

JUnit quản lý vòng đời thư mục tạm và dọn sau test theo cấu hình. Với object storage, dùng bucket hoặc prefix riêng cho test và xóa đúng object sau khi hoàn tất. Với dịch vụ sandbox, hãy dùng API cleanup hoặc fixture riêng nếu nhà cung cấp hỗ trợ.

Nếu cleanup nằm trong `@AfterEach`, hãy làm cho thao tác có thể chạy nhiều lần và xử lý trường hợp tài nguyên chưa được tạo. Với quy trình nhiều bước có thể lỗi giữa chừng, lưu lại ID tài nguyên ngay khi tạo để cleanup có thể tìm thấy nó ngay cả khi test thất bại trước assertion cuối.

## 11. Dùng dữ liệu riêng cho mỗi test để hỗ trợ chạy song song

Cleanup chính xác bắt đầu từ việc sở hữu dữ liệu chính xác. Một test không nên xóa dữ liệu mà test khác đang dùng. Đây là vấn đề quan trọng khi JUnit chạy song song, CI chạy nhiều worker hoặc nhiều pipeline dùng chung database.

Một cách đơn giản là tạo test run ID:

```java
class TestRunIds {
    static String newId() {
        return "test-" + UUID.randomUUID();
    }
}
```

Trong mỗi test, dùng ID đó cho customer, order, cache key hoặc message correlation. Cleanup chỉ xóa những bản ghi có ID thuộc test hiện tại.

Nếu database hỗ trợ schema riêng, có thể tạo schema theo test run và cấu hình datasource trỏ tới schema đó. Với một số hệ quản trị, database riêng cho mỗi suite hoặc mỗi worker còn tạo isolation tốt hơn. Lựa chọn cụ thể phụ thuộc chi phí khởi tạo và cách migration được quản lý.

Tránh các lệnh cleanup quá rộng như:

```sql
DELETE FROM orders;
TRUNCATE TABLE customers CASCADE;
```

Các lệnh này có thể xóa dữ liệu của test khác hoặc môi trường dùng chung. Chỉ sử dụng truncate toàn bảng trong database/schema được cô lập hoàn toàn cho test và khi không có test đồng thời dùng chung tài nguyên đó.

## 12. Dùng `@BeforeEach` và `@AfterEach` có trách nhiệm

`@BeforeEach` và `@AfterEach` phù hợp cho setup/cleanup gắn với từng test method. Hãy giữ mỗi hook nhỏ và rõ ràng:

```java
@BeforeEach
void prepareFixture() {
    cleaner.removeByTestRunId(testRunId);
    fixture = fixtureFactory.createFor(testRunId);
}

@AfterEach
void cleanFixture() {
    cleaner.removeByTestRunId(testRunId);
}
```

Cleanup nên:

- Xóa đúng dữ liệu mà test sở hữu.
- An toàn khi dữ liệu chưa tồn tại hoặc đã bị xóa.
- Có thể chạy sau khi assertion thất bại.
- Không phụ thuộc vào thứ tự test.
- Không xóa dữ liệu của worker hoặc pipeline khác.
- Có timeout hợp lý nếu cần gọi dịch vụ ngoài.

Nếu setup tạo nhiều tài nguyên ở các bước khác nhau, có thể đăng ký cleanup ngay sau mỗi bước tạo thành công. Điều này giúp tránh rò rỉ tài nguyên khi bước tiếp theo thất bại. Với tài nguyên đơn giản, `try/finally` hoặc API quản lý resource có thể phù hợp hơn.

## 13. Context cache và `@DirtiesContext` có liên quan thế nào?

Spring Test dùng context cache để tái sử dụng context có cấu hình tương đương. `@DirtiesContext` đánh dấu context cần loại khỏi cache. Các chế độ của annotation xác định thời điểm loại context, chẳng hạn sau method hoặc sau class.

Ví dụ chỉ nên dùng khi test thật sự làm thay đổi context:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutableSingletonConfigurationTest {

    @Autowired
    RuntimeFeatureRegistry registry;

    @Test
    void replacesGlobalFeatureConfiguration() {
        registry.replaceAll(Map.of("new-flow", true));
    }
}
```

Nếu có thể khôi phục `RuntimeFeatureRegistry` trong `@AfterEach`, hãy ưu tiên khôi phục để giữ context. Nếu không thể, `AFTER_CLASS` thường giới hạn số lần reload tốt hơn việc đánh dấu dirty sau từng method, miễn là các test trong class có thể dùng chung trạng thái context một cách an toàn.

Hãy nhớ rằng annotation có thể được đặt ở cấp class hoặc method và có nhiều mode. Chọn phạm vi nhỏ nhất đáp ứng nhu cầu. Không gắn `@DirtiesContext` lên một base test class lớn nếu chỉ một test con làm thay đổi singleton; việc đó có thể khiến hàng loạt test khác phải tải lại context.

## 14. Phân biệt application cache với TestContext cache

Hai loại cache thường bị nhầm:

| Cache | Lưu gì? | Cách làm sạch |
| --- | --- | --- |
| Spring TestContext cache | `ApplicationContext` được tạo từ cấu hình test | Để Spring tái sử dụng; dùng `@DirtiesContext` khi context không còn hợp lệ |
| Cache ứng dụng | Kết quả nghiệp vụ, dữ liệu đọc, session hoặc object được cache | Evict key, clear namespace, TTL hoặc reset cache bean |

Ví dụ, `@Cacheable("products")` lưu kết quả `findProduct()` trong cache ứng dụng. `@DirtiesContext` có thể làm bean cache bị hủy nếu cache manager nằm trong context, nhưng nếu Redis là dịch vụ ngoài thì dữ liệu Redis vẫn còn. Khi context mới tạo cache manager và kết nối lại Redis, key cũ vẫn có thể được đọc.

Vì vậy, hãy gọi `Cache.evict()` hoặc `Cache.clear()` trên đúng cache manager, hoặc dùng namespace riêng cho test. Chỉ khi cấu hình cache manager hoặc bean singleton bị hỏng và không thể phục hồi mới cần làm mới context.

## 15. Khi nào nên dùng database/schema riêng hoặc Testcontainers?

Nếu nhiều test phụ thuộc dữ liệu phức tạp hoặc chạy song song, database riêng thường đáng tin cậy hơn việc dùng một database chung rồi xóa thủ công toàn bộ bảng.

Các lựa chọn thường gặp:

| Cách tổ chức | Ưu điểm | Điểm cần cân nhắc |
| --- | --- | --- |
| Transaction rollback | Nhanh, ít code cleanup | Không bao phủ side effect ngoài transaction, thread khác hoặc `REQUIRES_NEW` |
| Xóa theo ID test | Linh hoạt, chạy được với database dùng chung | Phải quản lý khóa duy nhất và thứ tự xóa |
| SQL script | Fixture rõ ràng, phù hợp nhiều bảng | Script gắn với schema và cần quản lý transaction mode |
| Schema/database riêng | Isolation tốt, hỗ trợ chạy song song | Tốn thời gian tạo, migration và cleanup |
| Testcontainers riêng cho suite/worker | Môi trường gần production, giảm chia sẻ dữ liệu | Tài nguyên container cần được quản lý lifecycle và giới hạn song song |

Testcontainers không tự giải quyết isolation nếu mọi test cùng ghi vào một container database và dùng chung bảng. Cần thêm transaction, ID riêng, schema riêng hoặc database riêng tùy nhu cầu.

## 16. Tránh reset context chỉ để reset Mockito mock

Trong Spring test, mock/spy bean có thể được reset bằng cơ chế tích hợp của Spring Test hoặc annotation tương ứng theo phiên bản Spring Boot/Spring Framework. Nếu một mock còn invocation history hoặc stubbing từ test trước, hãy dùng chính sách reset phù hợp.

Ví dụ với Spring Framework 6.2 và `@MockitoBean`:

```java
@SpringBootTest
class OrderNotificationIntegrationTest {

    @MockitoBean
    NotificationGateway notificationGateway;

    @Test
    void sendsNotificationAfterOrderIsCreated() {
        // ...
        verify(notificationGateway).send(any());
    }
}
```

Annotation `@MockitoBean` có các tùy chọn reset theo lifecycle trong các phiên bản hỗ trợ. Với Spring Boot cũ, dự án có thể dùng `@MockBean` và cơ chế reset tương ứng. Hãy chọn chính sách reset rõ ràng và tránh dùng `@DirtiesContext` chỉ để xóa lịch sử gọi của mock.

Reset mock không hoàn tác side effect của một adapter thật. Nếu test đã gửi HTTP request hoặc ghi database thật, reset mock không có tác dụng với dữ liệu bên ngoài.

## 17. Cleanup khi test thất bại giữa chừng

Một test có thể tạo customer thành công, tạo order thành công rồi thất bại khi gọi payment. Nếu cleanup chỉ dựa trên biến được gán sau toàn bộ quy trình, tài nguyên tạo trước lỗi có thể bị bỏ sót.

Hãy ghi nhận ID ngay sau khi tạo tài nguyên:

```java
class OrderWorkflowTest {

    private final Set<String> createdOrderIds = new HashSet<>();

    @AfterEach
    void cleanUp() {
        for (String orderId : createdOrderIds) {
            orderCleaner.deleteById(orderId);
        }
        createdOrderIds.clear();
    }

    @Test
    void createsOrderAndHandlesPaymentFailure() {
        String orderId = orderFixture.createOrder();
        createdOrderIds.add(orderId);

        // Tiếp tục bước payment có thể phát sinh lỗi
    }
}
```

Đây là mẫu minh họa; fixture factory có thể trả về một object quản lý tài nguyên và cung cấp `close()` để cleanup tự động. Nếu dùng JUnit `@TestInstance(PER_CLASS)` hoặc chia sẻ test instance, cần bảo đảm tập ID được reset giữa method và không bị truy cập đồng thời không an toàn.

Với tài nguyên bên ngoài, cleanup có thể thất bại do mạng hoặc dịch vụ tạm ngừng. Hãy log ID tài nguyên và lỗi cleanup để có thể điều tra hoặc chạy job dọn dữ liệu test riêng. Không được âm thầm bỏ qua cleanup failure nếu nó có thể làm ô nhiễm môi trường dùng chung.

## 18. Cách kiểm tra rằng context vẫn được tái sử dụng

Nếu nghi ngờ test đang khởi tạo lại context quá nhiều, có thể quan sát log của Spring Test hoặc thống kê context cache. Spring Test cung cấp log debug/trace cho quá trình tải context và có thể ghi thống kê cache khi bật logging phù hợp.

Ví dụ cấu hình log trong `application-test.properties` hoặc cấu hình logging test:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Thông tin cache giúp thấy context được hit hoặc miss và có bị tải lại hay không. Hãy dùng log này khi chẩn đoán; không cần giữ mức trace quá chi tiết trong mọi pipeline nếu nó làm log quá lớn.

Có thể theo dõi thời gian khởi tạo context và thời gian test riêng biệt. Nếu mỗi test method đều làm context reload, hãy tìm `@DirtiesContext`, cấu hình context khác nhau hoặc listener tùy chỉnh đang làm dirty context. Nếu context vẫn được cache nhưng dữ liệu còn sót, hãy sửa cleanup ở database/cache/broker tương ứng.

## 19. Ví dụ tổ chức test suite không cần restart context

Một suite có thể dùng chung context và dọn dữ liệu theo test run ID:

```java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @Autowired
    OrderRepository orders;

    @Autowired
    OrderItemRepository items;

    private String testRunId;

    @BeforeEach
    void setUp() {
        testRunId = "order-test-" + UUID.randomUUID();
    }

    @AfterEach
    void tearDown() {
        items.deleteByTestRunId(testRunId);
        orders.deleteByTestRunId(testRunId);
    }

    @Test
    void createsOrderForCurrentTestRun() {
        Order order = new Order(testRunId, "customer-42");
        orders.save(order);

        assertTrue(orders.existsByTestRunId(testRunId));
    }
}
```

Mỗi method có dữ liệu riêng; cleanup xóa đúng dữ liệu của method đó. Context vẫn có thể được tái sử dụng giữa các method và class có cấu hình tương đương.

Nếu repository cleanup được gọi qua transaction, hãy bảo đảm transaction đã commit để dữ liệu được xóa thật. Nếu test method có transaction bao ngoài và cleanup tham gia cùng transaction, cleanup có thể bị rollback cùng test; khi đó cần điều chỉnh cách quản lý transaction hoặc dùng cleanup ngoài transaction test.

## 20. Những lỗi thường gặp khi dọn dữ liệu test

- **Dùng `@DirtiesContext` để xóa bản ghi database:** context reload nhưng dữ liệu bên ngoài vẫn còn.
- **Cho rằng context đóng sẽ xóa Redis hoặc broker:** dịch vụ ngoài context vẫn giữ trạng thái của chúng.
- **Dùng rollback cho mọi side effect:** email, message, HTTP và thread khác không tự rollback cùng database.
- **Xóa toàn bảng trong database dùng chung:** test song song có thể mất dữ liệu của nhau.
- **Cleanup chỉ chạy sau test thành công:** lỗi giữa chừng để lại dữ liệu hoặc tài nguyên.
- **Cleanup không idempotent:** lần dọn thứ hai thất bại vì dữ liệu đã bị xóa.
- **Không xét thứ tự khóa ngoại:** cleanup lỗi vì bảng con vẫn tham chiếu bảng cha.
- **Dùng chung ID giữa các test:** test chạy song song ghi đè hoặc xóa dữ liệu của nhau.
- **Nhầm TestContext cache với cache ứng dụng:** restart context nhưng key Redis vẫn tồn tại.
- **Dùng `@DirtiesContext` quá rộng ở base class:** nhiều test không liên quan phải tải context mới.
- **Không kiểm tra transaction của cleanup:** lệnh delete tham gia transaction test rồi bị rollback.

## 21. Quy trình chọn cách cleanup phù hợp

Khi một test để lại trạng thái, hãy xác định nguồn của trạng thái đó trước:

1. **Database:** nếu thao tác nằm trong transaction test, dùng rollback; nếu cần commit hoặc chạy nhiều transaction, xóa theo ID hoặc dùng SQL cleanup.
2. **Cache:** evict key hoặc xóa namespace riêng của test.
3. **Message broker:** dùng queue/topic/consumer group riêng và cleanup đúng vùng dữ liệu của test.
4. **Filesystem/object storage:** dùng thư mục tạm hoặc prefix riêng và xóa đúng tài nguyên.
5. **Dịch vụ ngoài:** dùng sandbox, ID duy nhất và API cleanup được hỗ trợ.
6. **Bean singleton/context state:** reset bean hoặc khôi phục cấu hình; chỉ dùng `@DirtiesContext` khi không thể phục hồi an toàn.
7. **Chạy song song:** cấp namespace riêng cho từng test run, worker hoặc suite.
8. **Xác nhận hiệu quả:** quan sát dữ liệu sau cleanup và log context cache khi cần để bảo đảm test không tạo context mới chỉ vì dữ liệu nghiệp vụ.

Một chiến lược cleanup tốt giúp test độc lập, có thể chạy lặp và hỗ trợ chạy song song. `ApplicationContext` nên được giữ lại khi cấu hình và bean vẫn hợp lệ; dữ liệu nghiệp vụ nên được dọn ở chính nơi nó được lưu. Khi tách rõ hai vòng đời này, Spring Test có thể tận dụng context cache, bộ kiểm thử chạy nhanh hơn và lỗi do dữ liệu còn sót được xử lý tại đúng nguồn.
